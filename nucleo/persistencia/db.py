# -*- coding: utf-8 -*-
"""
================================================================================
 PERSISTENCIA  --  Postgres (Supabase), esquema asistente.*
================================================================================

Por que existe
--------------
Nada se guardaba en ningun lado: nucleo/canales/api.py mantenia sesion e
historial solo en memoria del proceso, perdidos en cada reinicio. Sin
persistencia no hay forma de saber "cuando fue el ultimo contacto con este
lead", que es el prerrequisito de cualquier agente proactivo (seguimiento
de ventas, recordatorios).

De SQLite a Postgres
--------------------
La version anterior escribia en un SQLite local y lo justificaba asi: "las
credenciales de Supabase en .env no son reales... DATABASE_URL tiene el
placeholder 'your-tenant-id' sin rellenar". Ese impedimento ya no existe --
el proyecto tiene su Supabase propio, con el esquema aplicado y el CRM en la
misma base-- asi que esto pasa a escribir donde siempre debio.

Las tablas de SQLite se habian escrito replicando a proposito las columnas
de asistente.conversations/messages, asi que la migracion fue de dialecto,
no de modelo. Dos diferencias reales:

  - El tenant deja de ser texto ('rapilink') y pasa a ser organization_id,
    un uuid que referencia public.organization -la tabla del CRM-. El slug
    se resuelve contra asistente.tenant_config.
  - SQLite tenia UNIQUE(tenant, canal, usuario_externo): una sola
    conversacion por usuario, para siempre. El esquema de Postgres permite
    varias y las distingue por 'estado', que es lo que hace falta para
    cerrar una conversacion y abrir otra despues. Aqui se reusa la
    conversacion ABIERTA mas reciente, y si no hay, se crea.

POR QUE SE BAJA A app_backend  (no es opcional)
-----------------------------------------------
El usuario que conecta (DBUSER, ver nucleo/persistencia/conexion.py) es
'postgres', y en esta instalacion tiene BYPASSRLS: verificado contra la base,
rolbypassrls = true. Con ese rol
las politicas de aislamiento NO se evaluan y un olvido de filtro expondria
las conversaciones de otro ISP.

Por eso cada operacion abre transaccion, hace 'set local role app_backend'
-que si esta sujeto a RLS- y fija app.current_tenant. El 'local' de ambos es
lo que impide que una peticion herede el tenant de otra si se reutiliza la
conexion.

El orden importa: el slug se resuelve ANTES de bajar de rol, porque leer
tenant_config ya requiere el tenant fijado y seria circular.

Que NO guarda
--------------
Igual que el resto del proyecto: nunca la respuesta cruda de una API de
negocio (WispHub, BottleCRM...) -- eso lo decide nucleo/seguridad/
listas_blancas.py antes de que el dato llegue aca. Lo que se guarda es la
conversacion (lo que el usuario escribio, lo que el asistente respondio),
igual que ya decidia el PRD para 'messages'.
================================================================================
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from nucleo.persistencia.conexion import dsn

# Cache de slug -> organization_id. El vinculo lo crea cli/cargar_config.py y
# no cambia en caliente: si cambiara, el proceso se reinicia igual.
_ORGS: dict[str, str] = {}


def _organizacion(cur, tenant: str) -> str:
    """
    slug -> organization_id, contra asistente.tenant_config.

    Se ejecuta como el usuario que conecta (con BYPASSRLS), a proposito: es
    la consulta que AVERIGUA que tenant fijar, asi que no puede depender de
    que ya este fijado.
    """
    if tenant in _ORGS:
        return _ORGS[tenant]
    cur.execute("select organization_id from asistente.tenant_config where slug = %s",
                (tenant,))
    fila = cur.fetchone()
    if not fila:
        raise RuntimeError(
            f"El tenant '{tenant}' no tiene configuracion cargada, asi que no "
            f"se sabe a que organizacion pertenece. "
            f"Cargarla con: py -3.13 cli/cargar_config.py tenants/{tenant}.config.yaml")
    org = fila[0] if not isinstance(fila, dict) else fila["organization_id"]
    _ORGS[tenant] = str(org)
    return _ORGS[tenant]


@contextmanager
def sesion(tenant: str):
    """
    Conexion con el tenant fijado y el rol degradado a app_backend.

    Entrega (cursor, organization_id). Commit al salir sin excepcion.
    """
    con = psycopg.connect(dsn(), connect_timeout=30, row_factory=dict_row)
    try:
        with con.cursor() as cur:
            org = _organizacion(cur, tenant)         # antes de bajar de rol
            cur.execute("set local role app_backend")
            cur.execute("select set_config('app.current_tenant', %s, true)", (org,))
            yield cur, org
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def registrar_mensaje(tenant: str, canal: str, usuario_externo: str,
                      rol_efectivo: str, rol: str, contenido: str) -> str:
    """
    Une una fila de conversacion (crea si no existe) con una fila de
    mensaje, y actualiza 'actualizado_en' -- es la unica señal que necesita
    un scheduler para saber "hace cuanto no le escribimos a este usuario".

    Devuelve el id de la conversacion: nucleo/seguimiento/escalamiento.py lo
    necesita para poder marcarla despues, y evita una consulta aparte para
    algo que esta funcion ya resolvio.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo))
        fila = cur.fetchone()

        if fila:
            conv = fila["id"]
            cur.execute(
                """update asistente.conversations
                   set actualizado_en = now(), rol_efectivo = %s
                   where id = %s""",
                (rol_efectivo, conv))
        else:
            cur.execute(
                """insert into asistente.conversations
                     (organization_id, canal, usuario_externo, rol_efectivo)
                   values (%s, %s, %s, %s) returning id""",
                (org, canal, usuario_externo, rol_efectivo))
            conv = cur.fetchone()["id"]

        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido)
               values (%s, %s, %s, %s)""",
            (org, conv, rol, contenido))

        return str(conv)


def ultima_actividad(tenant: str, canal: str | None = None) -> list[dict]:
    """
    Una fila por conversacion: usuario_externo + cuando fue la ultima vez
    que se le escribio o respondio. Insumo del detector de seguimientos.

    'actualizado_en' viene como datetime con zona horaria, no como texto:
    es timestamptz en la base y quien consume ya no tiene que parsearlo.
    """
    with sesion(tenant) as (cur, org):
        if canal:
            cur.execute(
                """select id, canal, usuario_externo, rol_efectivo, estado,
                          escalada_a_humano, motivo_escalamiento, caso_id, etiqueta,
                          actualizado_en
                   from asistente.conversations
                   where organization_id = %s and canal = %s
                   order by actualizado_en desc""",
                (org, canal))
        else:
            cur.execute(
                """select id, canal, usuario_externo, rol_efectivo, estado,
                          escalada_a_humano, motivo_escalamiento, caso_id, etiqueta,
                          actualizado_en
                   from asistente.conversations
                   where organization_id = %s
                   order by actualizado_en desc""",
                (org,))
        return [dict(f) for f in cur.fetchall()]


def mensajes_de(tenant: str, conversation_id: str) -> dict:
    """
    El encabezado de una conversacion puntual (para el detalle de la
    bandeja) mas su hilo de mensajes en orden. `conversacion` viene None si
    el id no existe o no es de este tenant -- el llamador decide si eso es
    un 404.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, canal, usuario_externo, rol_efectivo, estado,
                      escalada_a_humano, motivo_escalamiento, caso_id, etiqueta,
                      actualizado_en
               from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        conversacion = cur.fetchone()
        if not conversacion:
            return {"conversacion": None, "mensajes": []}

        cur.execute(
            """select rol, contenido, creado_en
               from asistente.messages
               where organization_id = %s and conversation_id = %s
               order by creado_en asc""",
            (org, conversation_id))
        return {"conversacion": dict(conversacion), "mensajes": [dict(f) for f in cur.fetchall()]}


def marcar_escalada(tenant: str, conversation_id: str, motivo: str,
                    caso_id: str | None, etiqueta: str | None) -> None:
    """
    Registra que la conversacion paso a un humano: la marca escalada, guarda
    por que (una de escalamiento.activar_si) y el caso/etiqueta que resulto
    -- ver nucleo/seguimiento/escalamiento.py, el unico llamador. Filtra
    tambien por organization_id aunque 'id' ya es unico: mismo estilo
    defensivo que el resto de este archivo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set escalada_a_humano = true, motivo_escalamiento = %s,
                   caso_id = %s, etiqueta = %s, actualizado_en = now()
               where organization_id = %s and id = %s""",
            (motivo, caso_id, etiqueta, org, conversation_id))


def caso_de_conversacion(tenant: str, conversation_id: str) -> str | None:
    """
    El caso del CRM al que se derivo esta conversacion, o None si no se
    derivo. Lo usa nucleo/canales/api.py para saber contra que caso preguntar
    si el humano ya termino, y asi poder despausar al asistente.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select caso_id from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        fila = cur.fetchone()
        return str(fila["caso_id"]) if fila and fila["caso_id"] else None


def agregar_mensaje_humano(tenant: str, conversation_id: str, contenido: str) -> bool:
    """
    Un agente humano responde directo en el hilo, sin pasar por el modelo --
    para una conversacion ya escalada (marcar_escalada le puso caso_id), que
    a partir de ahi la sigue una persona, no el bot. 'rol' se guarda como
    'assistant' a proposito: es el mismo lado del canal que el cliente ya
    viene viendo, humano o bot no cambia esa columna, solo quien redacto.

    Devuelve False si la conversacion no existe o no es de este tenant -- el
    llamador (nucleo/canales/api.py) decide si eso es un 404.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select 1 from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        if not cur.fetchone():
            return False

        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido)
               values (%s, %s, 'assistant', %s)""",
            (org, conversation_id, contenido))
        cur.execute(
            """update asistente.conversations set actualizado_en = now()
               where id = %s""",
            (conversation_id,))
        return True


def registrar_llamada_herramienta(tenant: str, conversation_id: str, rol: str,
                                  llamada: dict) -> None:
    """
    Una fila de asistente.tool_calls por herramienta que el agente invoco
    este turno -- ver nucleo/modelo/motor.py:responder(), que arma 'llamada'
    (ya con los parametros enmascarados, nunca el dato crudo del cliente).
    Es la base de "ver proceso" en /conversaciones: que hizo el agente, en
    que orden, si fallo.

    Nunca rompe el turno: mismo criterio que registrar_mensaje. Perder una
    fila de auditoria no puede tumbar la atencion al cliente.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.tool_calls
                     (organization_id, conversation_id, herramienta, parametros,
                      rol_solicitante, exito, n_registros, codigo_error,
                      duracion_ms, es_escritura)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (org, conversation_id, llamada["herramienta"],
                 json.dumps(llamada["parametros"], ensure_ascii=False),
                 rol, llamada["exito"], llamada["n_registros"],
                 llamada["codigo_error"], llamada["duracion_ms"],
                 llamada["es_escritura"]))
    except Exception as e:
        print(f"[persistencia] no se pudo guardar la llamada a herramienta: {e}")


def herramientas_de(tenant: str, conversation_id: str) -> list[dict]:
    """
    El registro de herramientas que uso el agente en una conversacion, en
    orden -- lo que muestra el panel "Ver proceso" en el detalle de
    /conversaciones.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select herramienta, parametros, exito, n_registros, codigo_error,
                      duracion_ms, es_escritura, creado_en
               from asistente.tool_calls
               where organization_id = %s and conversation_id = %s
               order by creado_en asc""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]
