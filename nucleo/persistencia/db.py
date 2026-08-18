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
from datetime import datetime, timedelta, timezone

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


def estado_de_conversacion_abierta(tenant: str, canal: str,
                                   usuario_externo: str) -> dict | None:
    """
    Lo que hay que saber de la conversacion ABIERTA de este usuario antes de
    atenderlo: si ya se escalo a una persona, y a quien se verifico que era.

    Devuelve None si no hay ninguna abierta -- entonces es un contacto nuevo y
    no hay nada que recordar.

    Existe porque ese estado vivia SOLO en memoria del motor
    (nucleo/canales/api.py::_sesiones) y se perdia en cada reinicio, con dos
    consecuencias que el cliente si notaba:

      - Una conversacion escalada volvia a ser atendida por el bot. Se le
        habia dicho "te paso con un companero" y el bot seguia conversando
        como si nada. Visto en produccion el 14/08/2026: escalada a las 00:08,
        contestando de nuevo a las 00:16, 00:25, 00:41...
      - Habia que pedirle la cedula otra vez. El mismo cliente se verifico
        tres veces en una tarde.
      - Una derivacion a un area (facturacion, soporte tecnico...) se
        perdia igual que la escalada: el reinicio devolvia al cliente al
        agente general, en la mitad de una conversacion ya derivada.

    'necesita_atencion_humana' decide si la pausa (mas abajo, en
    atender_turno()) tiene sentido: una conversacion escalada pero agendada
    sola (nucleo/seguimiento/agendamiento.py) no tiene a ningun humano al
    que esperar, y pausar el bot ahi lo dejaria mudo para siempre con ese
    cliente.

    Es la MISMA fila que reusa registrar_mensaje ('abierta' mas reciente), asi
    que lo que se lee aca es lo que despues se va a escribir.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, escalada_a_humano, caso_id, id_cliente, nombre_cliente,
                      rol_efectivo, necesita_atencion_humana, datos_sesion
               from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo))
        fila = cur.fetchone()
        if not fila:
            return None
        return {
            "conversation_id": str(fila["id"]),
            "escalada": bool(fila["escalada_a_humano"]),
            "necesita_atencion_humana": bool(fila["necesita_atencion_humana"]),
            "caso_id": str(fila["caso_id"]) if fila["caso_id"] else None,
            "id_cliente": fila["id_cliente"],
            "nombre_cliente": fila["nombre_cliente"],
            "rol_efectivo": fila["rol_efectivo"],
            # Los identificadores tecnicos capturados al verificar (ej. el
            # serial de la ONU). Sin esto, tras un reinicio del motor la
            # conversacion vuelve verificada pero sin con que consultar.
            "datos_sesion": fila["datos_sesion"] or {},
        }


def registrar_mensaje(tenant: str, canal: str, usuario_externo: str,
                      rol_efectivo: str, rol: str, contenido: str) -> tuple[str, str]:
    """
    Une una fila de conversacion (crea si no existe) con una fila de
    mensaje, y actualiza 'actualizado_en' -- es la unica señal que necesita
    un scheduler para saber "hace cuanto no le escribimos a este usuario".

    Devuelve (conversation_id, message_id): lo primero lo necesita
    nucleo/seguimiento/escalamiento.py para poder marcar la conversacion
    despues; lo segundo, marcar_ejemplo (este mismo archivo) para poder
    marcar UNA respuesta puntual como buen ejemplo -- evita una consulta
    aparte para algo que esta funcion ya resolvio.
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
               values (%s, %s, %s, %s) returning id""",
            (org, conv, rol, contenido))
        mensaje = cur.fetchone()["id"]

        return str(conv), str(mensaje)


def actualizar_contenido_mensaje(tenant: str, mensaje_id: str, contenido: str) -> None:
    """
    Corrige el contenido de un mensaje ya guardado. nucleo/canales/api.py
    necesita esto porque el aviso de escalada/agendamiento se agrega a
    'respuesta' DESPUES de llamar a registrar_mensaje() -- el bloque de
    escalamiento necesita el conversation_id que esa llamada devuelve, asi
    que persistir y decidir el aviso no pueden pasar en el mismo paso. Sin
    este ajuste posterior, el HTTP response que recibe el cliente trae el
    aviso pero lo que se lee despues en /conversaciones no.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.messages set contenido = %s
               where id = %s and organization_id = %s""",
            (contenido, mensaje_id, org))


def ultima_actividad(tenant: str, canal: str | None = None) -> list[dict]:
    """
    Una fila por conversacion: usuario_externo + cuando fue la ultima vez
    que se le escribio o respondio. Insumo del detector de seguimientos y de
    la bandeja.

    Trae dos datos que no estan en la tabla y que la bandeja necesita para ser
    legible de un vistazo:

      ultimo_mensaje / ultimo_rol
          Sin el texto del ultimo turno todas las filas se ven iguales y hay
          que abrir cada una para saber de que va.

      atendida
          Si algun humano ya escribio en el hilo, O si alguien la marco a
          mano como atendida sin responder por el chat (ver
          marcar_atendida() y supabase/12_atendida_manual.sql -- resuelto
          por telefono, en persona, etc.). Es la diferencia entre "nadie
          tomo esto" y "alguien esta en eso", que es lo que decide a cual
          entrar primero. 'escalada_a_humano' sola no alcanza: una escalada
          hace dos horas y ya contestada no necesita a nadie.

    'actualizado_en' viene como datetime con zona horaria, no como texto:
    es timestamptz en la base y quien consume ya no tiene que parsearlo.

    'id_cliente'/'nombre_cliente' (ver supabase/14_identidad_conversacion.sql)
    son NULL hasta que _ejecutar_confirmacion verifica al cliente -- antes de
    eso, la unica identidad que hay es 'usuario_externo' (el numero o BSUID
    crudo del canal).
    """
    columnas = """c.id, c.canal, c.usuario_externo, c.rol_efectivo, c.estado,
                  c.escalada_a_humano, c.necesita_atencion_humana,
                  c.motivo_escalamiento, c.caso_id, c.etiqueta, c.caso_manual,
                  c.actualizado_en, c.id_cliente, c.nombre_cliente,
                  ultimo.contenido as ultimo_mensaje,
                  ultimo.rol       as ultimo_rol,
                  (c.atendida_manual or exists (
                       select 1 from asistente.messages h
                        where h.conversation_id = c.id
                          and h.rol = 'humano')) as atendida"""
    desde = """from asistente.conversations c
               left join lateral (
                   select contenido, rol
                     from asistente.messages
                    where conversation_id = c.id and contenido is not null
                    order by creado_en desc
                    limit 1
               ) ultimo on true"""

    with sesion(tenant) as (cur, org):
        if canal:
            cur.execute(
                f"""select {columnas} {desde}
                    where c.organization_id = %s and c.canal = %s
                    order by c.actualizado_en desc""",
                (org, canal))
        else:
            cur.execute(
                f"""select {columnas} {desde}
                    where c.organization_id = %s
                    order by c.actualizado_en desc""",
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
                      escalada_a_humano, necesita_atencion_humana,
                      motivo_escalamiento, caso_id, etiqueta,
                      actualizado_en, conservar, conservar_motivo, conservar_por,
                      atendida_manual, atendida_por, id_cliente, nombre_cliente,
                      (atendida_manual or exists (
                           select 1 from asistente.messages h
                            where h.conversation_id = conversations.id
                              and h.rol = 'humano')) as atendida
               from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        conversacion = cur.fetchone()
        if not conversacion:
            return {"conversacion": None, "mensajes": []}

        cur.execute(
            """select m.id, m.rol, m.contenido, m.creado_en, e.caso as caso_marcado,
                      -- Los adjuntos de ESA burbuja, sin los bytes: la interfaz
                      -- los pide despues por su id (/media/<id>). Devolverlos
                      -- aca serian varios MB de base64 en cada carga del hilo.
                      coalesce((
                        select json_agg(json_build_object(
                                 'id', a.id, 'tipo', a.tipo, 'mime', a.mime,
                                 'bytes', a.bytes, 'descripcion', a.descripcion)
                               order by a.creado_en)
                        from asistente.media a
                        where a.mensaje_id = m.id
                          and a.organization_id = m.organization_id
                      ), '[]'::json) as adjuntos
               from asistente.messages m
               left join asistente.ejemplos_validados e
                 on e.mensaje_id = m.id and e.organization_id = m.organization_id
               where m.organization_id = %s and m.conversation_id = %s
               order by m.creado_en asc""",
            (org, conversation_id))
        return {"conversacion": dict(conversacion), "mensajes": [dict(f) for f in cur.fetchall()]}


def marcar_escalada(tenant: str, conversation_id: str, motivo: str,
                    caso_id: str | None, etiqueta: str | None,
                    necesita_atencion_humana: bool = True) -> None:
    """
    Registra que la conversacion paso a un humano: la marca escalada, guarda
    por que (una de escalamiento.activar_si) y el caso/etiqueta que resulto
    -- ver nucleo/seguimiento/escalamiento.py, el unico llamador. Filtra
    tambien por organization_id aunque 'id' ya es unico: mismo estilo
    defensivo que el resto de este archivo.

    'necesita_atencion_humana' es independiente de 'escalada_a_humano': toda
    escalada crea ticket y pausa el bot igual, pero no toda escalada exige
    que alguien del equipo entre ya mismo (ver supabase/13_necesita_atencion_humana.sql).
    Decide el filtro "Sin atender" del frontend, nada mas.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set escalada_a_humano = true, motivo_escalamiento = %s,
                   caso_id = %s, etiqueta = %s,
                   necesita_atencion_humana = %s, actualizado_en = now()
               where organization_id = %s and id = %s""",
            (motivo, caso_id, etiqueta, necesita_atencion_humana, org, conversation_id))


def marcar_caso(tenant: str, conversation_id: str, caso: str | None) -> None:
    """
    Guarda de QUE es esta conversacion (uno de 'manual.casos' del tenant, ver
    supabase/18_caso_conversacion.sql). Se llama en CADA turno, no solo al
    escalar: la clasificacion cambia mientras la conversacion se aclara -- un
    "me quede sin servicio" empieza sin caso, pasa por 'no_internet' y
    termina en 'sin_senal_tv' cuando el cliente dice que es la television. La
    ultima gana, que es la que describe de verdad el caso.

    No pisa con NULL: si un turno no trajo clasificacion (el evaluador fallo,
    o el tenant no declaro casos), se conserva la que ya habia en vez de
    borrarla. Perder una clasificacion buena por un turno mudo seria peor que
    no tenerla.

    Nunca lanza: esto es una etiqueta para la bandeja, no parte de la
    respuesta al cliente -- mismo criterio que registrar_llamada_herramienta.
    """
    if not caso:
        return
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.conversations
                      set caso_manual = %s, actualizado_en = now()
                    where organization_id = %s and id = %s""",
                (caso, org, conversation_id))
    except Exception as e:
        print(f"[persistencia] no se pudo guardar el caso de la conversacion "
              f"{conversation_id}: {type(e).__name__}: {e}")


def cerrar_conversacion(tenant: str, conversation_id: str) -> None:
    """
    Marca la conversacion como 'cerrada' -- señal de bandeja, no un reinicio
    real: no toca la sesion en memoria del canal (historial, nivel de
    verificacion, ver nucleo/canales/api.py). El proximo mensaje del mismo
    usuario_externo abre una fila nueva (el 'where estado = 'abierta'' de
    registrar_mensaje ya no la encuentra), pero el modelo sigue teniendo el
    contexto completo -- misma logica que un ticket que se cierra y se
    reabre sin perder el historial.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set estado = 'cerrada', actualizado_en = now()
               where organization_id = %s and id = %s""",
            (org, conversation_id))


def identificar_cliente(tenant: str, conversation_id: str,
                        id_cliente: str, nombre: str | None,
                        datos: dict | None = None) -> None:
    """
    Guarda a QUIEN corresponde esta conversacion, resuelto por
    nucleo.modelo.motor._ejecutar_confirmacion -- no el identificador crudo
    del canal (eso ya vive en usuario_externo), sino el cliente real.

    Se llama en CADA turno una vez verificada la sesion (nucleo/canales/
    api.py::atender_turno): es un UPDATE idempotente, no hay costo en
    repetirlo. Antes de esto, Sesion.id_cliente vivia solo en memoria del
    proceso del motor y se perdia en cada reinicio -- /conversaciones nunca
    tenia con que mostrar un nombre, solo el BSUID o telefono crudo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set id_cliente = %s, nombre_cliente = %s,
                   datos_sesion = %s
               where organization_id = %s and id = %s""",
            (id_cliente, nombre, json.dumps(datos or {}), org, conversation_id))


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


def agregar_mensaje_humano(tenant: str, conversation_id: str,
                           contenido: str) -> dict | None:
    """
    Un agente humano responde directo en el hilo, sin pasar por el modelo --
    para una conversacion ya escalada (marcar_escalada le puso caso_id), que
    a partir de ahi la sigue una persona, no el bot. 'rol' se guarda como
    'assistant' a proposito: es el mismo lado del canal que el cliente ya
    viene viendo, humano o bot no cambia esa columna, solo quien redacto.

    Devuelve None si la conversacion no existe o no es de este tenant -- el
    llamador (nucleo/canales/api.py) decide si eso es un 404.

    Si existe, devuelve {'canal', 'usuario_externo'}: es POR DONDE hay que
    hacerle llegar el mensaje al cliente. Guardarlo en la base no se lo entrega
    a nadie -- una respuesta que se ve en la bandeja pero nunca sale es peor
    que un error visible, porque el agente cree que ya atendio.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select canal, usuario_externo from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        fila = cur.fetchone()
        if not fila:
            return None

        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido)
               values (%s, %s, 'assistant', %s)""",
            (org, conversation_id, contenido))
        cur.execute(
            """update asistente.conversations set actualizado_en = now()
               where id = %s""",
            (conversation_id,))
        return {"canal": fila["canal"], "usuario_externo": fila["usuario_externo"]}


def agentes_de_colaborador(tenant: str, profile_id: str) -> list[str]:
    """
    Que agentes tiene asignados este empleado del CRM (ver
    supabase/15_agentes_por_colaborador.sql). Lista vacia = ninguno, y quien
    llama debe tratarlo como "no accede", nunca como "accede a todos":
    fail-closed, igual que roles_permitidos en el corpus.

    'profile_id' es el perfil del CRM (public.profile), no un cliente final
    -- las filas de clientes lo tienen en NULL y no aparecen aca.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select rol from asistente.tenant_users
               where organization_id = %s and profile_id = %s and activo
               order by rol""",
            (org, profile_id))
        return [f["rol"] for f in cur.fetchall()]


def asignaciones_de_agentes(tenant: str) -> dict[str, list[str]]:
    """
    Todas las asignaciones del tenant: {profile_id: [agente, ...]}.

    Para la pantalla de asignacion, que cruza esto contra la lista de usuarios
    del CRM (esa la trae el frontend de la API de Django, no de aca: el motor
    no lee las tablas del CRM).
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select profile_id, rol from asistente.tenant_users
               where organization_id = %s and profile_id is not null and activo
               order by profile_id, rol""",
            (org,))
        salida: dict[str, list[str]] = {}
        for f in cur.fetchall():
            salida.setdefault(str(f["profile_id"]), []).append(f["rol"])
        return salida


def asignar_agentes(tenant: str, profile_id: str, roles: list[str]) -> list[str]:
    """
    Deja a este colaborador con EXACTAMENTE los agentes de 'roles'.

    Borra y reinserta en una sola transaccion en vez de calcular el delta: la
    pantalla manda el estado completo de los checkboxes, asi que el delta seria
    reconstruir lo que el llamador ya sabe. Y borrar de verdad (no 'activo =
    false') mantiene la tabla legible -- una asignacion quitada no es historia
    que haga falta conservar, a diferencia de una conversacion.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.tenant_users
               where organization_id = %s and profile_id = %s""",
            (org, profile_id))
        for rol in roles:
            cur.execute(
                """insert into asistente.tenant_users
                     (organization_id, profile_id, rol)
                   values (%s, %s, %s)""",
                (org, profile_id, rol))
        return list(roles)


def dar_de_baja(tenant: str, usuario_externo: str, canal: str = "whatsapp",
                motivo: str | None = None) -> None:
    """Registra que este numero no quiere mensajes proactivos. Idempotente:
    pedir baja dos veces no es un error."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.canal_bajas
                 (organization_id, canal, usuario_externo, motivo)
               values (%s,%s,%s,%s)
               on conflict (organization_id, canal, usuario_externo)
                 do update set creado_en = now(), motivo = excluded.motivo""",
            (org, canal, usuario_externo, motivo))


def dar_de_alta(tenant: str, usuario_externo: str, canal: str = "whatsapp") -> bool:
    """Revierte la baja. Devuelve si habia una."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.canal_bajas
               where organization_id = %s and canal = %s and usuario_externo = %s""",
            (org, canal, usuario_externo))
        return cur.rowcount > 0


def esta_de_baja(tenant: str, usuario_externo: str, canal: str = "whatsapp") -> bool:
    """Si este numero pidio no recibir mensajes proactivos.

    Se consulta ANTES de cualquier envio que inicie el sistema. Nunca antes de
    responderle a alguien que escribio: la baja bloquea la interrupcion, no la
    atencion -- ver supabase/10_bajas_canal.sql."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select 1 from asistente.canal_bajas
               where organization_id = %s and canal = %s and usuario_externo = %s""",
            (org, canal, usuario_externo))
        return cur.fetchone() is not None


def leer_cache(tenant: str, herramienta: str, clave: str,
               vigencia_dias: int | None) -> dict | list | None:
    """Respuesta cacheada de una herramienta 'http' con cache=true (ver
    nucleo/config/schema.py:Herramienta y nucleo/modelo/motor.py), o None si
    no hay entrada o vencio. 'vigencia_dias' None = no vence nunca."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select respuesta, actualizado_en from asistente.herramientas_cache
               where organization_id = %s and herramienta = %s and clave = %s""",
            (org, herramienta, clave))
        fila = cur.fetchone()
        if not fila:
            return None
        if vigencia_dias is not None:
            vencio = fila["actualizado_en"] < datetime.now(timezone.utc) - timedelta(days=vigencia_dias)
            if vencio:
                return None
        return fila["respuesta"]


def guardar_cache(tenant: str, herramienta: str, clave: str, respuesta) -> None:
    """Guarda (o refresca) una entrada de cache. Nunca rompe el turno: un
    fallo aca no puede tumbar la respuesta que ya se le va a dar al
    cliente -- mismo criterio que registrar_llamada_herramienta."""
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.herramientas_cache
                     (organization_id, herramienta, clave, respuesta, actualizado_en)
                   values (%s, %s, %s, %s, now())
                   on conflict (organization_id, herramienta, clave)
                   do update set respuesta = excluded.respuesta, actualizado_en = now()""",
                (org, herramienta, clave, json.dumps(respuesta, ensure_ascii=False)))
    except Exception as e:
        print(f"[persistencia] no se pudo guardar la cache de '{herramienta}': {e}")


def guardar_media(tenant: str, conversation_id: str, media_id: str, tipo: str,
                  contenido: bytes, mime: str | None = None,
                  descripcion: str | None = None,
                  mensaje_id: str | None = None) -> str | None:
    """
    Una foto o audio del cliente, ya comprimido (ver nucleo/canales/media.py).

    Devuelve el id de la fila, o None si ese 'media_id' ya estaba guardado --
    un reintento del webhook no duplica el archivo. Ver
    supabase/09_multimedia.sql para por que vive en Postgres y no en un almacen
    de objetos.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.media
                 (organization_id, conversation_id, mensaje_id, media_id, tipo,
                  mime, contenido, bytes, descripcion)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (organization_id, media_id) do nothing
               returning id""",
            (org, conversation_id, mensaje_id, media_id, tipo, mime,
             contenido, len(contenido), descripcion))
        fila = cur.fetchone()
        return str(fila["id"]) if fila else None


def media_de(tenant: str, conversation_id: str) -> list[dict]:
    """
    Los adjuntos de una conversacion, SIN los bytes.

    El contenido se pide aparte (media_bytes) porque una lista de diez fotos
    en la respuesta de la bandeja serian varios MB de JSON en base64 que nadie
    pidio: la interfaz muestra las miniaturas por su id.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, media_id, tipo, mime, bytes, descripcion, mensaje_id,
                      creado_en
               from asistente.media
               where organization_id = %s and conversation_id = %s
               order by creado_en""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]


def media_bytes(tenant: str, media_uuid: str) -> tuple[bytes, str] | None:
    """(contenido, mime) de un adjunto, para servirlo. None si no existe o no
    es de este tenant -- el filtro por organizacion lo hace la politica de
    aislamiento, no un if."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select contenido, mime from asistente.media
               where organization_id = %s and id = %s""",
            (org, media_uuid))
        fila = cur.fetchone()
        if not fila:
            return None
        return bytes(fila["contenido"]), fila["mime"] or "application/octet-stream"


def purgar_media(tenant: str, dias: int) -> int:
    """
    Borra los adjuntos mas viejos que 'dias'. Devuelve cuantos.

    Existe porque la retencion de multimedia es MAS CORTA que la de las
    conversaciones a proposito (ver supabase/09_multimedia.sql): el texto es
    barato y util para depurar, una foto pesa y puede mostrar la casa, la
    cedula o una cara. Se llama desde una tarea programada, no desde el turno.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.media
               where organization_id = %s
                 and creado_en < now() - make_interval(days => %s)""",
            (org, dias))
        return cur.rowcount


def marcar_conservar(tenant: str, conversation_id: str, conservar: bool,
                     motivo: str | None = None,
                     por: str | None = None) -> bool:
    """
    Saca (o vuelve a meter) una conversacion en la purga por retencion.

    Distinto de marcar un ejemplo: eso dice "esta respuesta fue buena" y
    alimenta el manual; esto dice "no la borres todavia" y no aparece en
    ningun lado mas. Ver supabase/11_conservar_conversacion.sql.

    Devuelve False si la conversacion no existe o no es de este tenant.

    Al desmarcar se limpian motivo y autor: dejarlos colgados haria creer que
    la conversacion sigue protegida cuando ya no lo esta.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set conservar = %s,
                   conservar_motivo = case when %s then %s else null end,
                   conservar_por    = case when %s then %s else null end
               where organization_id = %s and id = %s""",
            (conservar, conservar, motivo, conservar, por, org, conversation_id))
        return cur.rowcount > 0


def marcar_atendida(tenant: str, conversation_id: str, por: str | None) -> bool:
    """
    Marca una conversacion escalada como atendida SIN pasar por el chat --
    el colaborador la resolvio por telefono, en persona, o por otro canal.
    No es lo mismo que responder de verdad (eso ya marca 'atendida' solo,
    via el exists de ultima_actividad()): esto es el camino manual para
    cuando responder por el chat no corresponde. Ver
    supabase/12_atendida_manual.sql.

    Solo prende la marca -- no hay 'desmarcar' a proposito: si alguien la
    marco por error, la forma de corregirlo es responder de verdad (que ya
    la deja atendida por el otro camino) o escalar de nuevo, no un boton que
    vuelva a poner "sin atender" un caso que ya se resolvio.

    Devuelve False si la conversacion no existe o no es de este tenant.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set atendida_manual = true, atendida_por = %s
               where organization_id = %s and id = %s""",
            (por, org, conversation_id))
        return cur.rowcount > 0


def borrar_conversacion(tenant: str, conversation_id: str) -> dict | None:
    """
    SOLO PARA PRUEBAS: borra una conversacion de un tiro -- mensajes,
    llamadas a herramientas y adjuntos se van en cascada (on delete
    cascade, igual que purgar_conversaciones). A diferencia de la purga
    automatica, esto NO respeta 'conservar' ni ejemplos marcados: es una
    accion manual y deliberada (el boton de "reiniciar" del entrenamiento
    por WhatsApp real, para reescribirle al bot sin arrastrar el contexto
    de la prueba anterior -- sacar cuando termine esa etapa).

    Devuelve {'usuario_externo', 'canal'} de lo borrado (para que el
    llamador limpie tambien el estado en memoria del proceso, ver
    nucleo/canales/api.py:_sesiones), o None si no existia.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.conversations
               where organization_id = %s and id = %s
               returning usuario_externo, canal""",
            (org, conversation_id))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def purgar_conversaciones(tenant: str, dias: int) -> int:
    """
    Borra las conversaciones mas viejas que 'dias'. Devuelve cuantas.

    Los mensajes, las llamadas a herramientas y los adjuntos se van en cascada
    con ellas -- estan declarados 'on delete cascade'.

    DOS EXCEPCIONES, por dos razones distintas:

    1. 'conservar' -- alguien dijo explicitamente "no borres esto todavia": un
       reclamo, un incidente, algo que puede terminar en disputa. Ver
       supabase/11_conservar_conversacion.sql.

    2. Tener alguna respuesta marcada como ejemplo valido. Esas alimentan el
       manual de procedimientos (supabase/05_ejemplos_validados.sql) y cuelgan
       en cascada, asi que sin la excepcion la purga nocturna destruiria en
       silencio el material que alguien marco a mano.

    No son lo mismo y por eso son dos condiciones: un ejemplo dice "esta
    respuesta fue buena", conservar dice "no la borres". Una conversacion
    puede necesitar lo segundo siendo justo lo que NO hay que imitar.

    Se limpia el evento de webhook por separado (no cuelga de la conversacion)
    y con un plazo mucho mas corto: los reintentos de la plataforma ocurren en
    minutos, guardar identificadores un ano no sirve para nada.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.conversations c
               where c.organization_id = %s
                 and c.actualizado_en < now() - make_interval(days => %s)
                 and not c.conservar
                 and not exists (
                   select 1 from asistente.ejemplos_validados e
                   where e.conversation_id = c.id)""",
            (org, dias))
        borradas = cur.rowcount

        # Los identificadores de webhook no cuelgan de ninguna conversacion:
        # se limpian aparte, a 7 dias, que es margen de sobra sobre los
        # reintentos de la plataforma.
        cur.execute(
            """delete from asistente.webhook_eventos
               where organization_id = %s
                 and visto_en < now() - interval '7 days'""",
            (org,))
        return borradas


def evento_ya_visto(tenant: str, wamid: str, canal: str = "whatsapp") -> bool:
    """
    True si este webhook ya se proceso. False la primera vez -- y en esa misma
    llamada lo deja registrado.

    La deteccion y el registro van en UNA sentencia ('on conflict do nothing')
    a proposito: consultar primero y escribir despues deja una ventana en la
    que dos reintentos simultaneos leen "no visto" los dos y contestan los dos.
    Con el insert atomico, solo uno gana la clave primaria.

    Ver supabase/08_webhook_eventos.sql para por que esto vive en la base y no
    en memoria del proceso.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.webhook_eventos (organization_id, wamid, canal)
               values (%s, %s, %s)
               on conflict (organization_id, wamid) do nothing""",
            (org, wamid, canal))
        return cur.rowcount == 0


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


def marcar_ejemplo(tenant: str, conversation_id: str, mensaje_id: str,
                   caso: str, marcado_por: str | None) -> None:
    """
    Marca una respuesta del agente como buen ejemplo del caso/proceso
    indicado -- base del manual de procedimientos (ver /manual). 'caso' ya
    llega validado contra tenant_config.manual.casos (nucleo/canales/api.py,
    el unico llamador): esta funcion no vuelve a chequear la lista.

    Upsert por 'mensaje_id' (unique en la tabla): volver a marcar la misma
    burbuja actualiza el caso en vez de duplicar fila -- una burbuja
    solo pertenece a un caso a la vez.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.ejemplos_validados
                 (organization_id, conversation_id, mensaje_id, caso, marcado_por)
               values (%s, %s, %s, %s, %s)
               on conflict (mensaje_id) do update
                 set caso = excluded.caso, marcado_por = excluded.marcado_por,
                     creado_en = now()""",
            (org, conversation_id, mensaje_id, caso, marcado_por))


def desmarcar_ejemplo(tenant: str, mensaje_id: str) -> None:
    """Deshace un marcado -- ej. si se eligio el caso equivocado por error."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.ejemplos_validados
               where organization_id = %s and mensaje_id = %s""",
            (org, mensaje_id))


def ejemplos_por_caso(tenant: str, caso: str | None = None) -> list[dict]:
    """
    Los ejemplos marcados, con el mensaje del cliente que los disparo (el
    'user' inmediato anterior en la misma conversacion) -- lo que necesita
    /manual para mostrar pregunta y respuesta juntas, agrupadas por caso.

    'caso=None' trae todos los casos juntos (el frontend los agrupa); pasar
    un caso puntual filtra en la consulta en vez de traer de mas.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select e.id, e.caso, e.marcado_por, e.creado_en,
                      e.conversation_id, e.mensaje_id,
                      m.contenido as respuesta,
                      (select contenido from asistente.messages mu
                        where mu.conversation_id = m.conversation_id
                          and mu.rol = 'user' and mu.creado_en <= m.creado_en
                        order by mu.creado_en desc limit 1) as pregunta
               from asistente.ejemplos_validados e
               join asistente.messages m on m.id = e.mensaje_id
               where e.organization_id = %s
                 and (%s::text is null or e.caso = %s)
               order by e.caso, e.creado_en desc""",
            (org, caso, caso))
        return [dict(f) for f in cur.fetchall()]


def documentos_de(tenant: str) -> list[dict]:
    """
    Los documentos del corpus de este tenant -- para la pantalla que muestra
    que hay publicado (distinto de /manual/ejemplos, que muestra material
    CRUDO todavia sin redactar). 'n_fragmentos' cuenta solo los vigentes: un
    documento 'obsoleto' no tiene ninguno (ver cli/cargar_corpus.py,
    _cargar_obsoleto -- solo guarda la fila de metadatos, nunca fragmenta ni
    vectoriza).

    'roles_permitidos' viaja para que esa misma pantalla pueda mostrar y
    editar a quien se le recupera cada documento (PUT
    /corpus/documentos/<id>/roles) sin una consulta aparte.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select d.id, d.codigo, d.titulo, d.version, d.estado,
                      d.fecha_vigencia, d.creado_en, d.roles_permitidos,
                      (select count(*) from asistente.document_chunks c
                        where c.document_id = d.id and c.vigente) as n_fragmentos
               from asistente.documents d
               where d.organization_id = %s
               order by d.codigo, d.version desc""",
            (org,))
        return [dict(f) for f in cur.fetchall()]


def fragmentos_de(tenant: str, document_id: str) -> list[dict]:
    """
    El texto vigente de un documento, en orden -- lo que de verdad puede
    recuperar match_chunks() hoy. 'metadata' trae al menos 'seccion' (el
    numero, ej. '5.8'; ver nucleo/ingesta/docx.py) para que la pantalla
    agrupe fragmentos consecutivos del mismo numeral sin una consulta
    aparte.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select orden, contenido, metadata
               from asistente.document_chunks
               where organization_id = %s and document_id = %s and vigente
               order by orden""",
            (org, document_id))
        return [dict(f) for f in cur.fetchall()]


def guardar_revision_supervisor(tenant: str, conversation_id: str,
                                es_buen_ejemplo: bool, caso: str | None,
                                justificacion: str,
                                aporte_sugerido: str | None) -> None:
    """
    El veredicto del supervisor sobre una conversacion ya cerrada (ver
    nucleo/seguimiento/supervisor.py, el unico llamador). 'on conflict do
    nothing': el disparador (conversacion marcada 'resuelta') solo pasa una
    vez por conversacion real, asi que una segunda fila para el mismo id
    seria un reintento, no una revision nueva -- se descarta en silencio en
    vez de pisar el veredicto original.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.revisiones_supervisor
                 (organization_id, conversation_id, es_buen_ejemplo, caso,
                  justificacion, aporte_sugerido)
               values (%s, %s, %s, %s, %s, %s)
               on conflict (conversation_id) do nothing""",
            (org, conversation_id, es_buen_ejemplo, caso, justificacion,
             aporte_sugerido))


def revisiones_de(tenant: str, estado: str | None = None) -> list[dict]:
    """
    Las revisiones del supervisor, con el mensaje del cliente que abrio la
    conversacion como referencia rapida -- lo que necesita /manual para
    mostrar de que se trataba sin abrir la conversacion completa.

    'estado=None' trae todas (pendiente/aprobado/descartado); pasar un
    estado puntual filtra en la consulta.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select r.id, r.conversation_id, r.es_buen_ejemplo, r.caso,
                      r.justificacion, r.aporte_sugerido, r.estado,
                      r.revisado_por, r.creado_en, r.revisado_en,
                      c.usuario_externo,
                      (select contenido from asistente.messages m
                        where m.conversation_id = r.conversation_id
                          and m.rol = 'user'
                        order by m.creado_en asc limit 1) as primer_mensaje
               from asistente.revisiones_supervisor r
               join asistente.conversations c on c.id = r.conversation_id
               where r.organization_id = %s
                 and (%s::text is null or r.estado = %s)
               order by r.creado_en desc""",
            (org, estado, estado))
        return [dict(f) for f in cur.fetchall()]


def actualizar_estado_revision(tenant: str, revision_id: str, estado: str,
                               revisado_por: str | None) -> bool:
    """Aprobar o descartar una revision del supervisor -- la unica forma en
    que una de estas pasa de 'pendiente' a algo que una persona confirmo.
    Devuelve False si el id no existe o no es de este tenant."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.revisiones_supervisor
               set estado = %s, revisado_por = %s, revisado_en = now()
               where organization_id = %s and id = %s""",
            (estado, revisado_por, org, revision_id))
        return cur.rowcount > 0
