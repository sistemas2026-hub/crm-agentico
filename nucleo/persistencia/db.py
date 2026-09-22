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

import hashlib
import json
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum

import psycopg
from psycopg.rows import dict_row

from nucleo.persistencia.conexion import dsn
from nucleo.relevo import control as regla_control
from nucleo.relevo import historial as regla_historial
from nucleo.observabilidad.registro import id_interno, registrar

# Cache de slug -> organization_id. El vinculo lo crea cli/cargar_config.py y
# no cambia en caliente: si cambiara, el proceso se reinicia igual.
_ORGS: dict[str, str] = {}


class TenantSinConfiguracion(RuntimeError):
    """El slug no tiene fila en asistente.tenant_config. Mensaje escrito por
    Dexter: se puede mostrar (ver nucleo/canales/errores.py)."""


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
        raise TenantSinConfiguracion(
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
                                   usuario_externo: str,
                                   horas_inactividad: int | None = None) -> dict | None:
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
            """select id, escalada_a_humano, motivo_escalamiento,
                      caso_id, id_cliente, nombre_cliente,
                      rol_efectivo, necesita_atencion_humana, datos_sesion
               from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
                 and (%s::int is null
                      or actualizado_en > now() - (%s::int * interval '1 hour'))
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo, horas_inactividad, horas_inactividad))
        fila = cur.fetchone()
        if not fila:
            return None
        return {
            "conversation_id": str(fila["id"]),
            "escalada": bool(fila["escalada_a_humano"]),
            # POR QUE se escalo. Mientras la conversacion esta en pausa, cada
            # mensaje del cliente recibe el texto del tenant, y ese texto
            # depende del motivo: contestarle "entiendo tu molestia" a quien
            # pidio un tramite y no se quejo de nada suena a libreto y
            # desconcierta. Visto el 28/08/2026.
            "motivo_escalada": fila["motivo_escalamiento"],
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


# El '::int' de las dos consultas de abajo no es decoracion. Sin el, con
# 'horas_inactividad' en None -- que es su valor por defecto-- Postgres no
# puede inferir el tipo de un parametro que solo aparece dentro de un
# 'is null', y la consulta ENTERA falla con "could not determine data type of
# parameter $4".
#
# Se vio el 21/08/2026, y lo que fallaba era lo peor que podia fallar: el
# unico llamador que no pasa el valor es el turno de una conversacion
# PAUSADA. O sea que lo que el cliente escribia MIENTRAS ESPERABA a una
# persona era justo lo que no quedaba guardado, y quien tomaba el caso no lo
# veia nunca. El error se imprimia y el turno seguia, asi que desde afuera no
# se notaba nada.


def completar_medicion(tenant: str, mensaje_id: str, *, tokens_entrada: int,
                       tokens_salida: int, costo_usd: float,
                       llamadas_modelo: int) -> None:
    """
    Cierra la medicion de un turno, con lo que gasto DESPUES de componer la
    respuesta.

    El orden lo obliga: la respuesta se guarda apenas el modelo termina, y el
    evaluador de escalamiento --que es otra llamada al modelo-- corre unos
    150 renglones despues. Sin este cierre, el registro por mensaje contaba
    media llamada de las que el turno hizo de verdad, que es justo el numero
    que hace falta para saber por que un turno tardo.

    Nunca rompe: si esto falla, la respuesta ya se dio y ya se entrego. Lo
    unico que se pierde es la precision de una medida.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.messages
                   set tokens_entrada = %s, tokens_salida = %s,
                       costo_usd = %s, llamadas_modelo = %s
                   where organization_id = %s and id = %s""",
                (tokens_entrada, tokens_salida, round(costo_usd, 6),
                 llamadas_modelo, org, mensaje_id))
    except Exception as e:
        registrar("medicion", "no se pudo cerrar la del turno", error=e)


def historial_para_el_modelo(tenant: str, conversation_id: str,
                             limite: int = 20) -> list[dict]:
    """
    Los ultimos mensajes de una conversacion ABIERTA, con la forma que espera
    el modelo. Para volver a poner en contexto una conversacion cuyo historial
    se perdio al reiniciar el proceso.

    POR QUE HACE FALTA
    ------------------
    El historial vive en RAM (nucleo/canales/api.py::_sesiones). Cada
    despliegue lo borra, y hasta hoy no se rehidrataba -- la decision estaba
    tomada a proposito y escrita en _sesion_nueva: "cambia el costo de cada
    llamada y merece decidirse aparte".

    Ya hay con que decidirlo. Medido el 07/09/2026 con un cliente real: el
    motor se reinicio a mitad de una conversacion sobre television, y nueve
    minutos despues el cliente escribio "ya desconecte". El asistente contesto
    "Hola, buen dia" --saludando como si empezara--, dijo que "pasaron unas
    horas" (fueron nueve minutos) y hablo de una falla de INTERNET de hacia
    seis horas, porque sin historial se agarro del resumen de la conversacion
    anterior. Y antes de contestar hizo NUEVE busquedas en la documentacion
    intentando entender de que le hablaban: 8.2 de los 13.6 segundos que
    espero el cliente.

    QUE NO ENTRA, Y ESO ES LO IMPORTANTE
    ------------------------------------
    Las NOTAS INTERNAS (rol 'nota'). Son lo que el equipo se escribe entre
    si, y meterlas aca se las estaria dando al modelo para que las use al
    contestarle al cliente -- exactamente lo que ese rol existe para impedir.
    La garantia es este filtro mas el hecho de que agregar_nota_interna las
    guarda con un rol propio.

    EL TECHO
    --------
    'limite' mensajes, los ultimos. El historial en RAM crece sin techo
    durante una sesion viva, pero eso es gradual; volcar una conversacion de
    200 mensajes de golpe al reiniciar seria pagar de una vez un prompt que
    nadie decidio. Veinte alcanza para retomar el hilo.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                # La regla de que entra y como la decide nucleo/relevo/
                # historial.py, la MISMA que usa el camino en vivo. Antes esto
                # devolvia 'rol, contenido' a secas: lo que habia escrito una
                # persona volvia sin firma y la IA lo tomaba como propio (D8),
                # y la unica fila de legado con rol 'humano' ni siquiera entraba.
                # El filtro de rol va en el SQL para que el limite cuente solo
                # filas que el modelo va a ver: las notas no le roban lugar.
                """select rol, contenido, origen, autor_nombre, estado_entrega from (
                     select rol, contenido, origen, autor_nombre, estado_entrega, creado_en
                       from asistente.messages
                      where organization_id = %s and conversation_id = %s
                        and contenido is not null and contenido <> ''
                        and rol = any(%s)
                        and coalesce(estado_entrega, '') <> 'descartado'
                      order by creado_en desc limit %s
                   ) ultimos order by creado_en""",
                (org, conversation_id, list(regla_historial.ROLES_DEL_MODELO), limite))
            return regla_historial.construir(cur.fetchall())
    except Exception as e:
        # Igual que el resto de la rehidratacion: un fallo al leer no impide
        # atender. Se arranca sin memoria, que es lo que pasaba siempre.
        registrar("sesion", "no se pudo rehidratar el historial", error=e)
        return []


# =============================================================================
#  ORIGEN Y AUTOR DE UN MENSAJE  (supabase/202609161600_origen_de_mensajes.sql)
# =============================================================================
#  'rol' es el protocolo del modelo y del canal; 'origen' es quien produjo el
#  mensaje. La base admite origen NULL solo por el legado: TODA fila nueva lo
#  lleva, y eso se exige aca, en el unico lugar por donde se escribe
#  (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, I4).
ORIGENES = frozenset({"cliente", "ia", "humano", "sistema"})

# Que origenes tienen sentido para cada rol. Un 'user' que no es del lado
# cliente, o una nota que no escribio una persona, es un error de quien llama.
_ORIGENES_POR_ROL = {
    "user": frozenset({"cliente"}),
    "assistant": frozenset({"ia", "sistema", "humano"}),
    "nota": frozenset({"humano"}),
}


class AutorInvalido(ValueError):
    """Un mensaje de una persona sin autor identificable."""


class CanalNoAdmite(ValueError):
    """La conversacion es de un canal que no puede recibir este envio."""


def validar_origen(rol: str, origen: str) -> None:
    """Levanta ValueError si 'origen' falta, es desconocido o no corresponde
    al rol. Se llama antes de cualquier escritura."""
    if origen not in ORIGENES:
        raise ValueError(f"origen invalido o ausente: {origen!r}")
    if origen not in _ORIGENES_POR_ROL.get(rol, frozenset()):
        raise ValueError(f"origen {origen!r} no corresponde al rol {rol!r}")


def validar_autor(autor_nombre: str | None, autor_usuario_id: str | None) -> tuple[str, str]:
    """
    (nombre, usuario_id) normalizados, o AutorInvalido.

    Un mensaje humano sin autor no se guarda. Los dos datos: el id identifica
    a la persona aunque cambie de nombre; el nombre es lo que se firma y lo que
    ve el modelo. Los arma el proxy con la sesion autenticada, nunca el
    navegador.
    """
    nombre = (autor_nombre or "").strip()
    if not nombre:
        raise AutorInvalido("falta el nombre de quien escribe")
    try:
        usuario = str(uuid.UUID(str(autor_usuario_id)))
    except (ValueError, TypeError, AttributeError):
        raise AutorInvalido("falta o es invalido el id de quien escribe") from None
    return nombre, usuario


def registrar_mensaje(tenant: str, canal: str, usuario_externo: str,
                      rol_efectivo: str, rol: str, contenido: str,
                      horas_inactividad: int | None = None,
                      creado_en=None, latencia_ms: int | None = None,
                      tokens_entrada: int | None = None,
                      tokens_salida: int | None = None,
                      costo_usd: float | None = None,
                      llamadas_modelo: int | None = None,
                      modelo: str | None = None, *, origen: str) -> tuple[str, str]:
    """
    Une una fila de conversacion (crea si no existe) con una fila de
    mensaje, y actualiza 'actualizado_en' -- es la unica señal que necesita
    un scheduler para saber "hace cuanto no le escribimos a este usuario".

    Devuelve (conversation_id, message_id): lo primero lo necesita
    nucleo/seguimiento/escalamiento.py para poder marcar la conversacion
    despues; lo segundo, marcar_ejemplo (este mismo archivo) para poder
    marcar UNA respuesta puntual como buen ejemplo -- evita una consulta
    aparte para algo que esta funcion ya resolvio.

    'origen' es obligatorio y va sin valor por defecto a proposito: un
    llamador nuevo que lo olvide falla en el acto (TypeError), no guarda
    filas sin procedencia. Solo 'cliente' con 'user'; 'ia' o 'sistema' con
    'assistant'. Las personas escriben por agregar_mensaje_humano().
    """
    validar_origen(rol, origen)
    if origen == "humano":
        raise ValueError("los mensajes de personas van por agregar_mensaje_humano()")
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
                 and (%s::int is null
                      or actualizado_en > now() - (%s::int * interval '1 hour'))
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo, horas_inactividad, horas_inactividad))
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
            # 'creado_en' se puede FIJAR, y hace falta.
            #
            # Los dos mensajes de un turno --lo que escribio el cliente y la
            # respuesta-- se guardan los dos DESPUES de que el modelo termino
            # (ver nucleo/canales/api.py: motor.responder va antes). Con
            # now() por defecto, el mensaje del cliente quedaba sellado a la
            # hora en que se ACABO el turno, no a la que llego.
            #
            # Consecuencia medida el 07/09/2026: en la base, todos los turnos
            # mostraban 0.1s entre la pregunta y la respuesta. No era que
            # fuera rapido: era que los dos sellos eran el mismo instante, y
            # la espera real no estaba registrada en ningun lado.
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido,
                  creado_en, latencia_ms, tokens_entrada, tokens_salida,
                  costo_usd, modelo, llamadas_modelo, origen)
               values (%s, %s, %s, %s, coalesce(%s, now()), %s, %s, %s, %s, %s, %s, %s)
               returning id""",
            (org, conv, rol, contenido, creado_en, latencia_ms,
             tokens_entrada, tokens_salida, costo_usd, modelo,
             llamadas_modelo, origen))
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
          marcar_atendida() y supabase/202608131419_atendida_manual.sql -- resuelto
          por telefono, en persona, etc.). Es la diferencia entre "nadie
          tomo esto" y "alguien esta en eso", que es lo que decide a cual
          entrar primero. 'escalada_a_humano' sola no alcanza: una escalada
          hace dos horas y ya contestada no necesita a nadie.

    'actualizado_en' viene como datetime con zona horaria, no como texto:
    es timestamptz en la base y quien consume ya no tiene que parsearlo.

    'id_cliente'/'nombre_cliente' (ver supabase/202608131433_identidad_conversacion.sql)
    son NULL hasta que _ejecutar_confirmacion verifica al cliente -- antes de
    eso, la unica identidad que hay es 'usuario_externo' (el numero o BSUID
    crudo del canal).
    """
    columnas = """c.id, c.canal, c.usuario_externo, c.rol_efectivo, c.estado,
                  c.escalada_a_humano, c.necesita_atencion_humana,
                  c.motivo_escalamiento, c.caso_id, c.etiqueta, c.caso_manual,
                  c.actualizado_en, c.id_cliente, c.nombre_cliente,
                  c.escalada_en, c.resumen,
                  ultimo.contenido as ultimo_mensaje,
                  ultimo.rol       as ultimo_rol,
                  -- CUANDO fue ese ultimo mensaje. Distinto de
                  -- 'actualizado_en': esa columna la mueve cualquier cosa que
                  -- toque la fila, incluido cerrar la conversacion. Medido:
                  -- una cerrada hoy por inactividad quedaba con
                  -- actualizado_en de hoy y su ultimo mensaje de hace 26
                  -- dias, asi que ordenar "por actividad" la ponia arriba de
                  -- una con conversacion de verdad ayer.
                  ultimo.creado_en as ultimo_mensaje_en,
                  coalesce(insiste.n, 0) as mensajes_tras_escalar,
                  -- Aparte de 'atendida' (que lo mezcla con "un humano
                  -- escribio"): la bandeja necesita distinguir "alguien esta
                  -- en esto" de "esto ya se cerro a mano", y son pestañas
                  -- distintas.
                  c.atendida_manual, c.tomada_por, c.tomada_en,
                  -- B3.5 (D18): lo durable que necesita la proyeccion de la
                  -- bandeja (nucleo/relevo/proyeccion.py). El orden de la cola
                  -- sale de aca, no de un puntaje en la pantalla.
                  c.relevo_version, c.control, c.control_motivo,
                  c.asignada_a_usuario_id, c.asignada_a_nombre, c.asignada_en,
                  c.pendiente_interno_desde, c.estado_escalada,
                  -- La ultima vez que le respondio UNA PERSONA. Con esto se
                  -- sabe si el mensaje del cliente es posterior, que es la
                  -- diferencia entre "alguien espera respuesta" y "ya le
                  -- contestaron". 'humano' es el rol de legado; desde B2 una
                  -- respuesta de persona es rol 'assistant' con origen
                  -- 'humano'.
                  humana.creado_en as ultima_atencion_humana,
                  cliente.creado_en as ultimo_mensaje_cliente,
                  -- T19: si la evaluacion que quedo NO_DETERMINADO ya la
                  -- reviso alguien. Sin esto, una conversacion vieja pediria
                  -- revision para siempre.
                  exists (select 1 from asistente.relevo_eventos ev
                           where ev.organization_id = c.organization_id
                             and ev.conversation_id = c.id
                             and ev.tipo = 'evaluacion_revisada') as evaluacion_revisada,
                  (c.atendida_manual or exists (
                       select 1 from asistente.messages h
                        where h.conversation_id = c.id
                          and h.rol = 'humano')) as atendida"""
    # 'mensajes_tras_escalar': cuantas veces volvio a escribir el cliente
    # DESPUES de que su caso pasara a una persona. Es la señal de que se
    # cansa de esperar, y no se puede deducir de otra forma -- se intento
    # contando mensajes del cliente sin respuesta y da cero siempre, porque
    # el asistente le acusa recibo a cada uno mientras espera.
    desde = """from asistente.conversations c
               left join lateral (
                   select contenido, rol, creado_en
                     from asistente.messages
                    where conversation_id = c.id and contenido is not null
                      -- Una nota interna no es lo ultimo que se hablo con el
                      -- cliente: mostrarla en la lista haria creer que eso se
                      -- le dijo a el.
                      and rol <> 'nota'
                    order by creado_en desc
                    limit 1
               ) ultimo on true
               left join lateral (
                   select count(*) as n
                     from asistente.messages m
                    where m.conversation_id = c.id
                      and m.rol = 'user'
                      and c.escalada_en is not null
                      and m.creado_en > c.escalada_en
               ) insiste on true
               left join lateral (
                   select max(creado_en) as creado_en
                     from asistente.messages
                    where conversation_id = c.id
                      and (rol = 'humano' or (rol = 'assistant' and origen = 'humano'))
               ) humana on true
               left join lateral (
                   select max(creado_en) as creado_en
                     from asistente.messages
                    where conversation_id = c.id and rol = 'user'
               ) cliente on true"""

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
                      atendida_manual, atendida_por, tomada_por, tomada_en,
                      id_cliente, nombre_cliente, datos_sesion,
                      -- El control del relevo (B3): la pantalla recibe el
                      -- control EFECTIVO ya calculado (api.py), no la regla.
                      relevo_version, control, control_motivo,
                      asignada_a_usuario_id, asignada_a_nombre, aviso_relevo,
                      -- Lo que el modelo ya habia escrito al escalar y hasta
                      -- ahora solo viajaba a la descripcion del ticket. Es lo
                      -- que arma el resumen de arriba en el detalle: que
                      -- queria el cliente, que no se pudo comprobar y que
                      -- falta hacer.
                      escalada_en, resumen, escalada_no_comprobado,
                      escalada_siguiente_paso,
                      -- Cuando escribio el CLIENTE por ultima vez. No es lo
                      -- mismo que 'actualizado_en' ni que el ultimo mensaje
                      -- del hilo, y la diferencia es justamente el bug facil
                      -- de esta funcionalidad: la ventana de 24 h de WhatsApp
                      -- la abre el cliente, y solo el. Si esto mirara
                      -- cualquier mensaje, cada respuesta nuestra --o del
                      -- asistente-- renovaria la ventana en la pantalla
                      -- mientras Meta la considera cerrada, y el operador
                      -- descubriria la verdad recien cuando Enviar falla, que
                      -- es exactamente lo que se viene a evitar.
                      (select max(u.creado_en) from asistente.messages u
                        where u.conversation_id = conversations.id
                          and u.organization_id = conversations.organization_id
                          and u.rol = 'user') as ultimo_mensaje_cliente,
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
                      -- QUIEN produjo el mensaje, y su nombre si fue una
                      -- persona (D30). 'rol' es el protocolo del canal y NO
                      -- alcanza: desde B2 una respuesta humana es rol
                      -- 'assistant' con origen 'humano', igual que una de la
                      -- IA, asi que sin esta columna la pantalla no puede
                      -- distinguirlas y termina mostrando las dos como si las
                      -- hubiera escrito Dexter.
                      --
                      -- NULL es un valor con significado y se devuelve TAL
                      -- CUAL: son las filas anteriores al registro de origen.
                      -- No se rellena, ni por rol ni por nada -- afirmar quien
                      -- escribio algo que no sabemos es peor que no decirlo.
                      m.origen, m.autor_nombre,
                      -- Si le llego o no. NULL = no se sabe (otro canal, o
                      -- anterior al registro): la pantalla no dibuja nada.
                      m.estado_entrega, m.error_entrega,
                      -- La clave con la que se guardo: "Reintentar" la reusa
                      -- para no crear otra fila (D15).
                      m.clave_idempotencia,
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


def tasa_escalamiento(tenant: str, dias: int) -> dict:
    """
    Cuantas conversaciones de los ultimos N dias terminaron escaladas, y por
    que motivo -- agregado en SQL (count()), no traido fila por fila para
    contarlo en Python (mismo principio que PRD.md 12.5: el codigo calcula).

    Nace de medir si 'escalamiento.intentar_resolver_antes' (la vuelta extra
    antes de pasar a un humano, agregada el 15/08/2026) esta funcionando en
    la poblacion real y no solo en las dos conversaciones que se revisaron a
    mano ese dia. Mismo concepto que la 'tasa de escalada' que reporta
    Intercom Fin como metrica de primera clase -- ver investigacion de
    agosto 2026 sobre el rubro.

    Cuenta TODA conversacion en el periodo (escalada o no), asi que el
    'total' de abajo incluye las que el asistente resolvio solo -- es lo que
    hace que la proporcion tenga sentido. No filtra por rol: en Rapilink hoy
    solo hay roles 'cliente_final' con posibilidad de escalar (ver
    nucleo/canales/api.py::atender_turno, que ya restringe la evaluacion a
    'orientado_a == cliente_final'), asi que toda fila que llega con
    'escalada_a_humano' es de un cliente.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select escalada_a_humano, motivo_escalamiento,
                      nullif(trim(coalesce(escalada_siguiente_paso, '')), '')
                          is not null as con_siguiente_paso,
                      count(*) as n
                 from asistente.conversations
                where organization_id = %s
                  and creado_en >= now() - (%s || ' days')::interval
                group by escalada_a_humano, motivo_escalamiento,
                         con_siguiente_paso""",
            (org, dias))
        filas = [dict(f) for f in cur.fetchall()]

    total = sum(f["n"] for f in filas)
    escaladas = sum(f["n"] for f in filas if f["escalada_a_humano"])
    por_motivo: dict[str, int] = {}
    # Cuantas de las escaladas llegan con el relevo escrito. Hacer el campo
    # obligatorio en el esquema del evaluador (08/09/2026) garantiza que la
    # CLAVE exista, no que traiga contenido: con escalar=true y el campo
    # vacio el esquema queda conforme y quien toma el caso sigue sin saber
    # que le falta hacer. Esto es lo que distingue "mejoro el formato" de
    # "mejoro el contenido". Linea base para comparar: 0 de 52.
    con_paso = 0
    # Desglosado POR MOTIVO y no solo en total, porque no a todas las escaladas
    # se les exige relevo: a una forzada por una herramienta no hay de donde
    # sacarselo, y meterlas en el mismo denominador haria ver mal al evaluador
    # aunque este funcionando bien. Quien clasifica es el CLI, que si conoce
    # la config del tenant (forzado.motivos_que_no_elige_el_modelo); aca solo
    # se cuenta -- este modulo no deberia tener que saber que motivo es de
    # quien.
    relevo_por_motivo: dict[str, dict[str, int]] = {}
    for f in filas:
        if f["escalada_a_humano"]:
            motivo = f["motivo_escalamiento"] or "(sin motivo registrado)"
            por_motivo[motivo] = por_motivo.get(motivo, 0) + f["n"]
            casilla = relevo_por_motivo.setdefault(motivo, {"con": 0, "sin": 0})
            casilla["con" if f["con_siguiente_paso"] else "sin"] += f["n"]
            if f["con_siguiente_paso"]:
                con_paso += f["n"]

    return {"total": total, "escaladas": escaladas,
            "tasa": (escaladas / total) if total else 0.0,
            "con_siguiente_paso": con_paso,
            "sin_siguiente_paso": escaladas - con_paso,
            "relevo_por_motivo": relevo_por_motivo,
            "por_motivo": por_motivo}


def preguntas_sin_respuesta(tenant: str, dias: int,
                            incluir_revisadas: bool = False) -> list[dict]:
    """
    Preguntas que el asistente no pudo responder con el corpus (el RAG no
    encontro ningun fragmento por encima del umbral de similitud) en los
    ultimos N dias -- agregado en SQL, no traido fila por fila (mismo
    principio que PRD.md SS12.5).

    asistente.unanswered_queries se llena sola desde hace meses (ver
    nucleo/recuperacion/busqueda.py) pero nadie la habia leido -- es la
    primera funcion que lo hace. Cada fila es, segun su propio comentario en
    el esquema, "un hueco en la documentacion del cliente".

    Se agrupa por texto EXACTO normalizado (minusculas, sin espacios de
    mas): agarra duplicados literales, no reformulaciones del mismo tema
    ("no tengo señal en el tv" vs "se me fue la señal" quedan separadas).
    Agrupar por significado exigiria clustering semantico -- una version
    futura, no esta. Ordenado por cuantas veces se repitio la MISMA
    pregunta: la que mas se repite es la que mas vale la pena escribir en
    el manual primero.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select lower(trim(pregunta)) as pregunta_normalizada,
                      count(*) as n,
                      min(mejor_similitud) as peor_similitud,
                      max(creado_en) as ultima_vez,
                      (array_agg(pregunta order by creado_en desc))[1]
                        as pregunta_ejemplo,
                      (array_agg(rol_solicitante order by creado_en desc))[1]
                        as rol_ejemplo,
                      -- El ultimo conteo de fragmentos que ese rol podia ver.
                      -- Un 0 dice que el fallo fue de PERMISOS y no de
                      -- recuperacion: no se arregla calibrando el umbral.
                      (array_agg(chunks_elegibles order by creado_en desc))[1]
                        as elegibles
                 from asistente.unanswered_queries
                where organization_id = %s
                  and creado_en >= now() - (%s || ' days')::interval
                  and (%s or not revisada)
                group by pregunta_normalizada
                order by n desc, ultima_vez desc""",
            (org, dias, incluir_revisadas))
        return [dict(f) for f in cur.fetchall()]


def marcar_escalada(tenant: str, conversation_id: str, motivo: str,
                    caso_id: str | None, etiqueta: str | None,
                    necesita_atencion_humana: bool = True,
                    resumen: str = "", no_comprobado: str = "",
                    siguiente_paso: str = "",
                    nombre_caso: str = "", descripcion_caso: str = "") -> None:
    """
    Registra que la conversacion paso a un humano: la marca escalada, guarda
    por que (una de escalamiento.activar_si) y el caso/etiqueta que resulto
    -- ver nucleo/seguimiento/escalamiento.py, el unico llamador. Filtra
    tambien por organization_id aunque 'id' ya es unico: mismo estilo
    defensivo que el resto de este archivo.

    'necesita_atencion_humana' es independiente de 'escalada_a_humano': toda
    escalada crea ticket y pausa el bot igual, pero no toda escalada exige
    que alguien del equipo entre ya mismo (ver supabase/202608131420_necesita_atencion_humana.sql).
    Decide el filtro "Sin atender" del frontend, nada mas.

    'escalada_en' se sella una sola vez (coalesce): si la misma conversacion
    vuelve a pasar por aca --se re-evalua al retomar-- el reloj no se
    reinicia. Lo que la cola necesita saber es desde cuando espera esta
    persona, no cuando fue la ultima vez que el motor lo confirmo.

    'resumen': el modelo ya lo redacta al evaluar la escalada, y hasta hoy
    solo iba a la descripcion del ticket. Guardarlo aca no cuesta una llamada
    mas y es lo que deja que la bandeja diga de que se trata cada caso sin
    abrirlo. No cierra la conversacion -- eso lo hace guardar_resumen(), que
    es otra cosa: aquel resume una conversacion TERMINADA. Si mas tarde se
    cierra, aquel reemplaza a este, que es lo correcto: es mas completo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set escalada_a_humano = true, motivo_escalamiento = %s,
                   caso_id = %s, etiqueta = %s,
                   necesita_atencion_humana = %s, actualizado_en = now(),
                   escalada_en = coalesce(escalada_en, now()),
                   resumen = coalesce(nullif(%s, ''), resumen),
                   escalada_no_comprobado = coalesce(nullif(%s, ''),
                                                     escalada_no_comprobado),
                   escalada_siguiente_paso = coalesce(nullif(%s, ''),
                                                      escalada_siguiente_paso)
               where organization_id = %s and id = %s""",
            (motivo, caso_id, etiqueta, necesita_atencion_humana,
             (resumen or "").strip(), (no_comprobado or "").strip(),
             (siguiente_paso or "").strip(), org, conversation_id))

        # B4: si el CRM no devolvio caso, la intencion queda ENCOLADA en la
        # misma transaccion que la marca de escalada. Antes de esto el except
        # de escalar() la mandaba al log y se perdia: la conversacion quedaba
        # escalada, visible en la bandeja, y sin caso -- y nadie se enteraba
        # hasta que alguien lo buscaba a mano.
        #
        # La clave se deriva de (conversacion, tipo): reintentar la misma
        # escalada no encola dos veces el mismo efecto. Y 'datos_intencion'
        # lleva solo lo minimo para rehacerlo, nunca el texto del cliente.
        if not caso_id:
            encolar_sincronizacion(
                cur, org, conversation_id, tipo="crear_caso",
                clave=f"crear_caso:{conversation_id}",
                datos={"motivo": motivo, "etiqueta": etiqueta,
                       # El nombre canonico es la idempotencia: lleva el
                       # conversation_id y es unico por organizacion. Sin el,
                       # el reconciliador no puede preguntar si ya existe.
                       "nombre_caso": (nombre_caso or "").strip(),
                       "descripcion": (descripcion_caso or "").strip()})


def guardar_ticket_operativo(tenant: str, conversation_id: str,
                             ticket: str) -> None:
    """
    Deja anotado que ticket abrio esta conversacion en el sistema del ISP.

    Ese numero ya se escribia dentro de la descripcion del caso del CRM, pero
    como texto suelto: servia para leerlo y para nada mas. Guardado aca se
    puede responder y cerrar ese ticket desde el codigo cuando la persona
    responde o el caso termina (ver nucleo/seguimiento/operativo.py).

    Nunca rompe el turno: el ticket YA se creo, y no poder anotarlo no es
    motivo para tumbar la respuesta al cliente.
    """
    if not ticket:
        return
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.conversations set ticket_operativo = %s
                   where organization_id = %s and id = %s""",
                (str(ticket), org, conversation_id))
    except Exception as e:
        registrar("persistencia", "no se pudo anotar el ticket operativo", ticket=ticket,
                  conversation_id=id_interno(conversation_id), error=e)


def atendida_por_humano(tenant: str, conversation_id: str) -> bool:
    """
    Si alguien del equipo ya le respondio al cliente en esta conversacion.

    Misma definicion que usa la bandeja: la marca explicita, o un mensaje
    escrito por una persona.

    Decide si un "ok" del cliente puede cerrar el caso. Sin esto, el 28/08/2026
    un cliente contesto "ok" al aviso del propio asistente --"tu pedido quedo
    registrado"-- y se cerro todo: la conversacion, el caso y el ticket, con el
    cambio de clave sin hacer y sin que ninguna persona hubiera escrito nunca.
    Un "ok" a nadie no confirma nada.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select (c.atendida_manual or exists (
                             select 1 from asistente.messages h
                              where h.conversation_id = c.id
                                and h.rol = 'humano')) as atendida
                   from asistente.conversations c
                   where c.organization_id = %s and c.id = %s""",
                (org, conversation_id))
            fila = cur.fetchone()
            return bool(fila and fila["atendida"])
    except Exception as e:
        registrar("persistencia", "no se pudo saber si la atendio una persona", error=e)
        # Fail-closed: ante la duda NO se cierra. Un caso abierto de mas lo
        # cierra alguien; uno cerrado de menos deja al cliente sin el cambio.
        return False


def guardar_verificacion_pendiente(tenant: str, conversation_id: str,
                                   herramienta: str, pendiente: dict) -> None:
    """
    Anota que una accion quedo sin comprobar. Ver
    supabase/202609021130_verificacion_accion.sql.

    Nunca rompe el turno: la accion YA se ejecuto, y no poder anotarla no es
    motivo para tumbarle la respuesta al cliente. Lo que se pierde si esto
    falla es la comprobacion, y queda dicho en el log.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.verificaciones_accion
                     (organization_id, conversation_id, herramienta,
                      espera_segundos, max_intentos, medicion_previa)
                   values (%s, %s, %s, %s, %s, %s)""",
                (org, conversation_id, herramienta,
                 int(pendiente.get("espera_segundos") or 0),
                 int(pendiente.get("max_intentos") or 1),
                 json.dumps(pendiente.get("medicion_previa"), ensure_ascii=False)))
    except Exception as e:
        registrar("verificacion", "no se pudo anotar la pendiente", herramienta=herramienta,
                  conversation_id=id_interno(conversation_id), error=e)


def verificacion_pendiente_de(tenant: str, conversation_id: str) -> dict | None:
    """
    La verificacion sin resolver de esta conversacion, si la hay.

    Devuelve tambien 'vencida': si ya paso el plazo y por lo tanto medir de
    nuevo significa algo. El candado de cierre mira la fila entera; quien va a
    medir mira 'vencida'.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select id, herramienta, espera_segundos, max_intentos,
                          intentos, medicion_previa, ejecutada_en,
                          (now() >= ejecutada_en
                           + make_interval(secs => espera_segundos)) as vencida
                     from asistente.verificaciones_accion
                    where organization_id = %s and conversation_id = %s
                      and estado = 'VERIFICACION_PENDIENTE'
                    order by ejecutada_en
                    limit 1""",
                (org, conversation_id))
            fila = cur.fetchone()
            return dict(fila) if fila else None
    except Exception as e:
        registrar("verificacion", "no se pudo leer la pendiente", error=e)
        return None


def resolver_verificacion(tenant: str, verificacion_id: str, estado: str,
                          por_que: str, medicion_posterior: dict | None,
                          intentos: int) -> None:
    """
    Guarda el resultado de haber medido. Si el estado sigue siendo pendiente
    solo sube el contador de intentos y la ultima medicion -- el plazo se
    cuenta desde la ejecucion, no desde el ultimo intento.
    """
    from nucleo.seguimiento import verificacion_accion

    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.verificaciones_accion
                      set estado = %s, por_que = %s, medicion_posterior = %s,
                          intentos = %s,
                          verificada_en = case when %s then now() else null end
                    where organization_id = %s and id = %s""",
                (estado, por_que[:400],
                 json.dumps(medicion_posterior, ensure_ascii=False),
                 intentos, estado in verificacion_accion.TERMINALES,
                 org, verificacion_id))
    except Exception as e:
        registrar("verificacion", "no se pudo guardar el resultado", error=e)


def ticket_operativo_de(tenant: str, conversation_id: str) -> str | None:
    """El ticket del sistema del ISP que abrio esta conversacion, si abrio uno."""
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select ticket_operativo from asistente.conversations
                   where organization_id = %s and id = %s""",
                (org, conversation_id))
            fila = cur.fetchone()
            return fila["ticket_operativo"] if fila else None
    except Exception as e:
        registrar("persistencia", "no se pudo leer el ticket operativo", error=e)
        return None


def marcar_caso(tenant: str, conversation_id: str, caso: str | None,
                etiqueta: str = "") -> None:
    """
    Guarda de QUE es esta conversacion (uno de 'manual.casos' del tenant, ver
    supabase/202608180923_caso_conversacion.sql). Se llama en CADA turno, no solo al
    escalar: la clasificacion cambia mientras la conversacion se aclara -- un
    "me quede sin servicio" empieza sin caso, pasa por 'no_internet' y
    termina en 'sin_senal_tv' cuando el cliente dice que es la television. La
    ultima gana, que es la que describe de verdad el caso.

    No pisa con NULL: si un turno no trajo clasificacion (el evaluador fallo,
    o el tenant no declaro casos), se conserva la que ya habia en vez de
    borrarla. Perder una clasificacion buena por un turno mudo seria peor que
    no tenerla.

    'etiqueta' viaja junto porque sale de la MISMA llamada al evaluador y
    tenia el mismo problema, medido el 15/09/2026: se guardaba solo dentro de
    marcar_escalada, asi que una conversacion que el asistente resolvia solo
    la calculaba y la tiraba. Resultado sobre 178 conversaciones reales -- 62
    sin etiquetar (34.8%), mientras 'caso_manual' si estaba en casi todas. Es
    exactamente el agujero que este mismo comentario describe arriba para
    'caso_manual', un campo mas tarde.

    Importa para algo concreto: un supervisor no puede priorizar lo que no
    sabe nombrar, y con dos de cada tres conversaciones sin nombre no hay
    tablero que sirva.

    Se guarda con 'coalesce' y no a secas: una escalada posterior escribe la
    suya via marcar_escalada, y un turno mudo no puede borrar la que ya habia
    -- mismo criterio que 'caso'.

    Nunca lanza: esto es una etiqueta para la bandeja, no parte de la
    respuesta al cliente -- mismo criterio que registrar_llamada_herramienta.
    """
    if not caso and not (etiqueta or "").strip():
        return
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.conversations
                      set caso_manual = coalesce(nullif(%s, ''), caso_manual),
                          etiqueta = coalesce(nullif(%s, ''), etiqueta),
                          actualizado_en = now()
                    where organization_id = %s and id = %s""",
                (caso or "", (etiqueta or "").strip(), org, conversation_id))
    except Exception as e:
        registrar("persistencia", "no se pudo guardar el caso de la conversacion",
                  conversation_id=id_interno(conversation_id), error=e)


def conversaciones_sin_respuesta(tenant: str, horas: int) -> list[dict]:
    """
    Las conversaciones escaladas donde el cliente lleva 'horas' sin escribir.

    Se cuenta desde el ULTIMO mensaje DEL CLIENTE, no desde el ultimo mensaje
    de la conversacion: si se midiera contra este, cada respuesta que manda el
    equipo estiraria el plazo, y una conversacion donde solo escribe el equipo
    no se cerraria nunca -- que es exactamente la que hay que cerrar.

    Una conversacion sin ningun mensaje del cliente (raro, pero posible si se
    creo desde otra pantalla) cuenta desde que se creo, para que tampoco quede
    colgada para siempre.
    """
    if not horas or horas <= 0:
        return []
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select c.id, c.caso_id, c.ticket_operativo, c.usuario_externo,
                      c.nombre_cliente
               from asistente.conversations c
               where c.organization_id = %s
                 and c.escalada_a_humano
                 and c.estado <> 'cerrada'
                 -- Solo las que YA atendio alguien del equipo. Una que nadie
                 -- toco todavia no esta esperando al cliente: esta esperando
                 -- al equipo, y cerrarla por tiempo enterraria trabajo sin
                 -- hacer con cara de trabajo terminado. Misma definicion de
                 -- "atendida" que usa la bandeja, unas lineas mas arriba.
                 and (c.atendida_manual or exists (
                        select 1 from asistente.messages h
                         where h.conversation_id = c.id and h.rol = 'humano'))
                 and coalesce(
                       (select max(m.creado_en) from asistente.messages m
                         where m.conversation_id = c.id and m.rol = 'user'),
                       c.creado_en) < now() - make_interval(hours => %s)
               order by c.actualizado_en""",
            (org, int(horas)))
        return [dict(f) for f in cur.fetchall()]


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

    'datos_sesion' se FUSIONA (||), no se reemplaza. Antes se pisaba entero, y
    eso alcanzaba mientras esta fuera la unica funcion que lo escribia. Ya no
    lo es: guardar_estado_routing() escribe ahi las areas visitadas, y con un
    reemplazo la primera verificacion posterior a una derivacion las borraba
    -- justo el dato que existe para que el cliente no rebote entre areas.

    CONTRATO, y no es un detalle: 'datos' tiene que traer TODOS los campos de
    identidad, con None incluido, no solo los que tienen valor. Con la fusion,
    una clave omitida NO se borra: conserva el valor anterior. Si una segunda
    verificacion en la misma conversacion resuelve a otro cliente que no tiene
    'sn_onu', omitirlo dejaria el serial del cliente ANTERIOR pegado a la
    identidad del nuevo -- y las herramientas que identifican la ONU por ese
    serial diagnosticarian el equipo de otra persona, sin ningun error a la
    vista. Mandandolo como None, el '||' lo sobrescribe. Quien llama arma el
    diccionario en nucleo/canales/api.py::atender_turno.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set id_cliente = %s, nombre_cliente = %s,
                   datos_sesion = datos_sesion || %s::jsonb
               where organization_id = %s and id = %s""",
            (id_cliente, nombre, json.dumps(datos or {}), org, conversation_id))


def guardar_estado_routing(tenant: str, conversation_id: str,
                           datos: dict | None = None) -> None:
    """
    El estado de routing que tiene que sobrevivir a un reinicio del motor --
    hoy solo las areas por las que ya paso la conversacion (ver
    Sesion.CAMPOS_ROUTING_PERSISTIBLES).

    Va por su propia puerta y no por identificar_cliente() porque se escribe
    en otro momento: al DERIVAR, que ocurre antes de que nadie verifique nada.
    Colgarlo de la verificacion habria dejado sin anti-rebote justo a las
    conversaciones que todavia no tienen identidad resuelta.

    Misma columna ('datos_sesion') y misma fusion con '||': las dos puertas
    escriben claves distintas del mismo JSONB y ninguna puede pisar a la otra.
    Sin columna nueva ni migracion -- ver el comentario de
    supabase/202608151253_datos_sesion.sql sobre por que esa columna es JSONB.
    """
    if not datos:
        return                      # nada que guardar: no se toca la fila
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.conversations
               set datos_sesion = datos_sesion || %s::jsonb
               where organization_id = %s and id = %s""",
            (json.dumps(datos), org, conversation_id))


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
                           contenido: str, autor: str, *,
                           autor_usuario_id: str,
                           clave_idempotencia: str | None = None,
                           solo_canal: str | None = None) -> dict | None:
    """
    Un agente humano responde directo en el hilo, sin pasar por el modelo --
    para una conversacion ya escalada (marcar_escalada le puso caso_id), que
    a partir de ahi la sigue una persona, no el bot. 'rol' se guarda como
    'assistant' a proposito: es el mismo lado del canal que el cliente ya
    viene viendo, humano o bot no cambia esa columna, solo quien redacto.

    Devuelve None si la conversacion no existe o no es de este tenant -- el
    llamador (nucleo/canales/api.py) decide si eso es un 404.

    Si existe, devuelve {'canal', 'usuario_externo', 'ticket_operativo'}: por
    donde hay que hacerle llegar el mensaje al cliente, y en que ticket del
    sistema del ISP hay que copiarlo. Guardarlo en la base no se lo entrega a
    nadie -- una respuesta que se ve en la bandeja pero nunca sale es peor que
    un error visible, porque el agente cree que ya atendio.

    El ticket viaja aca y no en una consulta aparte porque es la misma fila:
    pedirla dos veces para leer una columna mas es una ida a la base por cada
    respuesta que escribe una persona.

    AUTOR, ORIGEN E IDEMPOTENCIA (B2)
    ---------------------------------
    'autor' (nombre) y 'autor_usuario_id' son obligatorios: sin ellos,
    AutorInvalido y nada se escribe. La fila queda con origen = 'humano'.

    'clave_idempotencia' la genera quien compone el mensaje. Si ya existe una
    fila con esa clave en esta conversacion, NO se inserta otra: se devuelve
    la existente con 'existente': True y su 'estado_entrega', y quien llama
    decide si reintentar la entrega (solo si fallo). Antes, cada "Reintentar"
    insertaba una copia del mensaje.

    'solo_canal': si la conversacion no es de ese canal, CanalNoAdmite ANTES
    de insertar. La plantilla lo usa: guardaba la fila y recien despues
    descubria que la conversacion no era de WhatsApp (D16).
    """
    nombre, usuario = validar_autor(autor, autor_usuario_id)
    clave = (clave_idempotencia or "").strip() or None
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select canal, usuario_externo, ticket_operativo
               from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        fila = cur.fetchone()
        if not fila:
            return None
        if solo_canal is not None and fila["canal"] != solo_canal:
            raise CanalNoAdmite(
                f"la conversacion es del canal '{fila['canal']}', no '{solo_canal}'")

        # 'pendiente' solo si hay a donde entregarlo. En el simulador o la API
        # no hay entrega que esperar, y dejarlo en NULL es lo honesto: la
        # pantalla no dibuja un estado que nunca va a cambiar.
        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido,
                  estado_entrega, origen, autor_usuario_id, autor_nombre,
                  clave_idempotencia)
               values (%s, %s, 'assistant', %s, %s, 'humano', %s, %s, %s)
               on conflict (organization_id, conversation_id, clave_idempotencia)
                 where clave_idempotencia is not null
               do nothing
               returning id""",
            (org, conversation_id, contenido,
             "pendiente" if fila["canal"] == "whatsapp" else None,
             usuario, nombre, clave))
        insertada = cur.fetchone()
        if insertada is None:
            # La clave ya estaba: es un reintento del MISMO mensaje.
            cur.execute(
                """select id, estado_entrega from asistente.messages
                   where organization_id = %s and conversation_id = %s
                     and clave_idempotencia = %s""",
                (org, conversation_id, clave))
            previa = cur.fetchone()
            return {**dict(fila), "mensaje_id": previa["id"], "existente": True,
                    "estado_entrega": previa["estado_entrega"]}
        mensaje_id = insertada["id"]
        autor = nombre
        # Y queda marcada como atendida por una persona. No es cosmetico:
        # dos reglas dependen de saberlo -- el cierre por confirmacion del
        # cliente (que no vale si nadie le contesto todavia) y el barrido por
        # plazo vencido (que solo cierra lo que alguien ya atendio).
        #
        # El mensaje se guarda con rol 'assistant' a proposito, asi que la
        # marca tiene que ir aparte: sin esto, responder desde el ticket no
        # dejaba ninguna huella de que hubo una persona atras.
        cur.execute(
            """update asistente.conversations
               set actualizado_en = now(), atendida_manual = true,
                   atendida_por = coalesce(nullif(%s, ''), atendida_por)
               where id = %s""",
            (autor or "", conversation_id))
        # La fila entera, no dos campos elegidos a mano: agregarle una columna
        # al select y olvidarse de este return deja al llamador sin el dato y
        # sin ningun error -- paso el 28/08/2026 con 'ticket_operativo', y la
        # copia al ticket del ISP no se hacia sin que nada lo dijera.
        #
        # 'mensaje_id' se suma aparte: quien llama tiene que poder sellar el
        # wamid en ESTA fila cuando WhatsApp le responda, y sin el id habria
        # que adivinar cual de los mensajes de la conversacion es.
        return {**dict(fila), "mensaje_id": mensaje_id, "existente": False,
                "estado_entrega": "pendiente" if fila["canal"] == "whatsapp" else None}


def agregar_nota_interna(tenant: str, conversation_id: str, contenido: str,
                         autor: str, *, autor_usuario_id: str) -> str | None:
    """
    Una nota que el equipo se deja a si mismo. NO se le envia a nadie.

    POR QUE ES UN ROL PROPIO Y NO UN MENSAJE MARCADO
    ------------------------------------------------
    La garantia de que una nota no salga al cliente tiene que ser
    ESTRUCTURAL, no una bandera que alguien puede olvidar mirar. Con rol
    'nota' no existe ningun camino que la entregue: las dos rutas de envio
    (texto y multimedia) llaman a agregar_mensaje_humano(), que escribe rol
    'assistant' y despues entrega. Esta funcion no entrega nada porque no
    tiene con que.

    Tampoco entra al historial que ve el modelo: ese historial vive en
    memoria (nucleo/canales/api.py::_sesiones) y se arma con lo que pasa por
    el turno, no leyendo esta tabla. Una nota no pasa por ningun turno.

    Y NO marca la conversacion como atendida: escribir una nota no es
    haberle contestado a quien espera. Es la diferencia entre dejar
    anotado algo y hacerse cargo del caso.

    Devuelve el id de la nota, o None si la conversacion no existe.

    Autor obligatorio, como en agregar_mensaje_humano (AutorInvalido). El
    contenido conserva el prefijo "(autor)" que la pantalla ya muestra; el
    autor ademas queda en sus columnas (origen = 'humano').
    """
    nombre, usuario = validar_autor(autor, autor_usuario_id)
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido,
                  origen, autor_usuario_id, autor_nombre)
               select %s, %s, 'nota', %s, 'humano', %s, %s
                where exists (select 1 from asistente.conversations
                               where organization_id = %s and id = %s)
               returning id""",
            (org, conversation_id, f"({nombre}) {contenido}",
             usuario, nombre, org, conversation_id))
        fila = cur.fetchone()
        return fila["id"] if fila else None


# Lo que se guarda cuando WhatsApp respondio bien pero sin decir con que id:
# no se puede confirmar la entrega ni casar un acuse, y tampoco es un fallo.
SIN_IDENTIFICADOR = ("WhatsApp aceptó la petición pero no devolvió el id del "
                     "mensaje: no se puede confirmar la entrega.")


class ResultadoEntrega(str, Enum):
    ACTUALIZADO = "actualizado"
    YA_APLICADO = "ya_aplicado"
    REGRESIVO = "regresivo"
    NO_ENCONTRADO = "no_encontrado"


def adquirir_salida_whatsapp(tenant: str, clave: str, *, proposito: str,
                              mensaje_id: str | None = None,
                              conversation_id: str | None = None) -> bool:
    """Adquiere una sola vez el derecho durable a hacer el POST a Meta."""
    if not (clave or "").strip():
        raise ValueError("la salida de WhatsApp necesita clave de idempotencia")
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.whatsapp_salidas
                 (organization_id, clave_idempotencia, mensaje_id,
                  conversation_id, proposito)
               values (%s, %s, %s, %s, %s)
               on conflict (organization_id, clave_idempotencia) do nothing
               returning clave_idempotencia""",
            (org, clave, mensaje_id, conversation_id, proposito))
        return cur.fetchone() is not None


def salida_whatsapp(tenant: str, clave: str) -> dict | None:
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select estado, wamid, error from asistente.whatsapp_salidas
               where organization_id = %s and clave_idempotencia = %s""", (org, clave))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def resolver_salida_whatsapp(tenant: str, clave: str, resultado: str,
                              wamid: str | None = None,
                              error: str | None = None) -> bool:
    """Sella una salida sin message asociado (avisos automaticos/proactivos)."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.whatsapp_salidas
               set estado = %s, wamid = %s, error = %s,
                   estado_entrega = case when %s::text is not null then 'enviado' end,
                   resuelto_en = clock_timestamp()
               where organization_id = %s and clave_idempotencia = %s
                 and estado = 'adquirido'""",
            (resultado, wamid, error, wamid, org, clave))
        escrita = cur.rowcount == 1
        if escrita and wamid:
            cur.execute(
                """select estado, error from asistente.whatsapp_acuses_pendientes
                   where organization_id = %s and wamid = %s for update""", (org, wamid))
            acuse = cur.fetchone()
            if acuse:
                cur.execute(
                    """update asistente.whatsapp_salidas
                       set estado_entrega = %s,
                           error_entrega = coalesce(%s, error_entrega)
                       where organization_id = %s and clave_idempotencia = %s""",
                    (acuse["estado"], acuse["error"], org, clave))
                cur.execute(
                    """delete from asistente.whatsapp_acuses_pendientes
                       where organization_id = %s and wamid = %s""", (org, wamid))
        return escrita


def _aplicar_acuse_pendiente(cur, org: str, mensaje_id: str, wamid: str) -> None:
    cur.execute(
        """select estado, error from asistente.whatsapp_acuses_pendientes
           where organization_id = %s and wamid = %s for update""", (org, wamid))
    acuse = cur.fetchone()
    if not acuse:
        return
    cur.execute(
        """update asistente.messages
           set estado_entrega = %s, error_entrega = coalesce(%s, error_entrega)
           where organization_id = %s and id = %s""",
        (acuse["estado"], acuse["error"], org, mensaje_id))
    cur.execute(
        """delete from asistente.whatsapp_acuses_pendientes
           where organization_id = %s and wamid = %s""", (org, wamid))


def marcar_envio(tenant: str, mensaje_id: str, wamid: str | None,
                 error: str | None = None, *, clave_salida: str | None = None,
                 resultado: str | None = None) -> bool:
    """
    Cierra el circuito del envio: o salio (y quedo su wamid, con el que
    despues se casan los acuses), o no salio y se guarda por que.

    Se separa del insert a proposito. Guardar y entregar son dos cosas, y el
    orden --guardar primero-- existe para que un fallo de entrega nunca borre
    lo que la persona escribio. Este es el segundo paso de ese mismo criterio.

    Devuelve True solo si la fila quedo escrita. Nunca lanza, pero TAMPOCO
    oculta: quien llama recibe False y decide. Medido el 16/09/2026 en
    produccion: esta funcion fallaba en TODAS las llamadas desde que existe
    (el 'case when %s is null' no tiene tipo para psycopg 3 y PostgreSQL lo
    rechaza con IndeterminateDatatype), se tragaba el error, y ningun mensaje
    humano paso nunca de 'pendiente'. Un exito que no quedo guardado no es un
    exito: la devolucion a la IA (T6 del contrato del relevo) depende de este
    valor.

    El estado lo decide Python y no el SQL, para no depender de que el servidor
    infiera el tipo de un parametro suelto:
      - con error ............. 'fallido'  (la pantalla ofrece reintentar)
      - con wamid ............. 'enviado'  (los acuses lo pueden alcanzar)
      - sin error y sin wamid . 'pendiente' con SIN_IDENTIFICADOR. NO 'fallido':
        Meta no lo rechazo y pudo haberlo entregado, y 'fallido' ofreceria
        reintentar -- el cliente recibiria el mensaje dos veces.

    'error' tiene que venir ya saneado por quien llama: se guarda y se muestra
    tal cual, y nunca puede ser la respuesta cruda de una API externa.
    """
    if resultado == "incierto":
        estado = "desconocido"
    elif error is not None:
        estado = "fallido"
    elif wamid:
        estado = "enviado"
    else:
        estado, error = "pendiente", SIN_IDENTIFICADOR
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.messages
                   set wamid = coalesce(%s::text, wamid),
                       estado_entrega = %s::text,
                       error_entrega = %s::text
                   where organization_id = %s and id = %s""",
                (wamid, estado, error, org, mensaje_id))
            escrita = cur.rowcount == 1
            if escrita and wamid:
                _aplicar_acuse_pendiente(cur, org, mensaje_id, wamid)
            if clave_salida:
                cur.execute(
                    """update asistente.whatsapp_salidas
                       set estado = %s, wamid = %s, error = %s,
                           resuelto_en = clock_timestamp()
                       where organization_id = %s and clave_idempotencia = %s
                         and estado = 'adquirido'""",
                    (resultado or ("aceptado" if wamid else "rechazado"),
                     wamid, error, org, clave_salida))
    except Exception as e:
        registrar("entrega", "NO se pudo anotar el envio", mensaje=id_interno(mensaje_id),
                  estado=estado, error=e)
        return False
    if not escrita:
        registrar("entrega", "NO se anoto el envio: la fila no existe o no es de esta empresa",
                  mensaje=id_interno(mensaje_id), estado=estado)
    return escrita


# El orden en que puede avanzar un mensaje. Los acuses de Meta NO llegan
# ordenados -- un 'delivered' puede entrar despues de un 'read'-- y sin esto
# un mensaje ya leido volveria a decir "entregado".
_RANGO_ENTREGA = {"pendiente": 0, "enviado": 1, "entregado": 2, "leido": 3,
                  "fallido": 4}


def marcar_entrega(tenant: str, wamid: str, estado: str,
                   error: str | None = None) -> ResultadoEntrega:
    """
    Un acuse de WhatsApp, aplicado al mensaje que lo produjo.

    'fallido' es el rango mas alto y por eso pisa a cualquier otro: si Meta
    dice que no se pudo entregar, eso es lo ultimo que se sabe del mensaje
    aunque antes hubiera dicho 'enviado'.

    Si la salida aun no existe, conserva el mejor acuse tenant-scoped para que
    marcar_envio lo reconcilie atomicamente, y devuelve no_encontrado: no
    afirma haber actualizado una salida que todavia no pudo correlacionar.
    """
    rango = _RANGO_ENTREGA.get(estado)
    if rango is None:
        return ResultadoEntrega.NO_ENCONTRADO
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select estado_entrega from asistente.messages
               where organization_id = %s and wamid = %s for update""", (org, wamid))
        fila = cur.fetchone()
        tabla = "messages"
        if not fila:
            cur.execute(
                """select estado_entrega from asistente.whatsapp_salidas
                   where organization_id = %s and wamid = %s for update""", (org, wamid))
            fila = cur.fetchone()
            tabla = "whatsapp_salidas"
        if fila:
            actual = _RANGO_ENTREGA.get(fila["estado_entrega"], 0)
            if rango == actual:
                return ResultadoEntrega.YA_APLICADO
            if rango < actual:
                return ResultadoEntrega.REGRESIVO
            cur.execute(
                f"""update asistente.{tabla}
                    set estado_entrega = %s,
                        error_entrega = coalesce(%s, error_entrega)
                    where organization_id = %s and wamid = %s""",
                (estado, error, org, wamid))
            return ResultadoEntrega.ACTUALIZADO

        cur.execute(
            """insert into asistente.whatsapp_acuses_pendientes
                 (organization_id, wamid, estado, precedencia, error)
               values (%s, %s, %s, %s, %s)
               on conflict (organization_id, wamid) do update
                 set estado = excluded.estado,
                     precedencia = excluded.precedencia,
                     error = coalesce(excluded.error,
                                      asistente.whatsapp_acuses_pendientes.error),
                     actualizado_en = clock_timestamp()
               where excluded.precedencia >
                     asistente.whatsapp_acuses_pendientes.precedencia""",
            (org, wamid, estado, rango, error))
        return ResultadoEntrega.NO_ENCONTRADO


def agentes_de_colaborador(tenant: str, profile_id: str) -> list[str]:
    """
    Que agentes tiene asignados este empleado del CRM (ver
    supabase/202608132036_agentes_por_colaborador.sql). Lista vacia = ninguno, y quien
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


def areas_de_colaboradores(tenant: str) -> dict[str, str]:
    """{profile_id: nombre de area} de todo el tenant."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select profile_id, area from asistente.area_colaborador
               where organization_id = %s""",
            (org,))
        return {str(f["profile_id"]): f["area"] for f in cur.fetchall()}


def guardar_area_colaborador(tenant: str, profile_id: str, area: str) -> None:
    """Un area vacia borra la fila: no todo el mundo pertenece a un area
    operativa (un administrador del sistema, por ejemplo), y guardar la cadena
    vacia haria que la pantalla mostrara un area en blanco como si fuera una."""
    with sesion(tenant) as (cur, org):
        if not (area or "").strip():
            cur.execute(
                """delete from asistente.area_colaborador
                   where organization_id = %s and profile_id = %s""",
                (org, profile_id))
            return
        cur.execute(
            """insert into asistente.area_colaborador
                   (organization_id, profile_id, area)
               values (%s, %s, %s)
               on conflict (organization_id, profile_id) do update
                   set area = excluded.area, actualizado_en = now()""",
            (org, profile_id, area.strip()))


def identidades_externas(tenant: str, sistema: str) -> dict[str, dict]:
    """
    Quien es cada colaborador dentro de un sistema externo:
    {profile_id: {"identificador": ..., "nombre_visible": ...}}.

    Se devuelve el nombre junto al identificador porque una pantalla que solo
    tiene el id no puede mostrar nada util, y volver a preguntarle a la API
    externa seria una llamada por persona.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select profile_id, identificador, nombre_visible
               from asistente.identidades_externas
               where organization_id = %s and sistema = %s""",
            (org, sistema))
        return {str(f["profile_id"]): {"identificador": f["identificador"],
                                       "nombre_visible": f["nombre_visible"] or ""}
                for f in cur.fetchall()}


def guardar_identidad_externa(tenant: str, profile_id: str, sistema: str,
                              identificador: str, nombre_visible: str = "") -> None:
    """
    Deja a este colaborador con ESTA identidad en ese sistema. Un identificador
    vacio la borra: es como se dice "esta persona ya no tiene cuenta alla", y
    sin eso la unica forma de deshacer una asignacion equivocada seria por SQL.
    """
    with sesion(tenant) as (cur, org):
        if not (identificador or "").strip():
            cur.execute(
                """delete from asistente.identidades_externas
                   where organization_id = %s and profile_id = %s and sistema = %s""",
                (org, profile_id, sistema))
            return
        cur.execute(
            """insert into asistente.identidades_externas
                   (organization_id, profile_id, sistema, identificador, nombre_visible)
               values (%s, %s, %s, %s, %s)
               on conflict (organization_id, profile_id, sistema) do update
                   set identificador = excluded.identificador,
                       nombre_visible = excluded.nombre_visible,
                       actualizado_en = now()""",
            (org, profile_id, sistema, identificador.strip(), (nombre_visible or "").strip()))


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
    atencion -- ver supabase/202608121843_bajas_canal.sql."""
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
        registrar("persistencia", "no se pudo guardar la cache", herramienta=herramienta, error=e)


def registrar_marca_tv_desconocida(tenant: str, conversation_id: str,
                                   marca: str) -> None:
    """
    Anota una marca de televisor que el cliente nombro y no tiene guia propia.

    La marca se guarda TAL CUAL la escribio: 'Sansung', 'LG smart', 'kalley'.
    Quien despues cree la guia necesita ver como la nombra la gente, no como
    deberia llamarse -- si diez clientes escriben 'Sansung', eso es un dato
    sobre el mundo, no un error que haya que tapar. La version normalizada va
    en una columna APARTE, solo para agrupar.

    Una fila por marca y conversacion, no una por mencion: dentro de una misma
    conversacion la marca puede repetirse varias veces (el agente vuelve a
    preguntar, se reintenta la sintonizacion) y sin eso una sola conversacion
    llena la cola de trabajo con la misma marca. Las menciones repetidas suben
    'veces', que es lo que permite priorizar cual guia escribir primero.

    Nunca rompe el turno: si falla, el cliente ya recibio su guia general y
    perder la anotacion es mucho menos grave que perder la respuesta.
    """
    limpia = (marca or "").strip()
    if not limpia or not conversation_id:
        return
    normalizada = " ".join(
        unicodedata.normalize("NFKD", limpia.lower())
        .encode("ascii", "ignore").decode().split())
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.marcas_tv_desconocidas
                     (organization_id, marca, marca_normalizada, conversation_id)
                   values (%s, %s, %s, %s)
                   on conflict (organization_id, marca_normalizada, conversation_id)
                     where conversation_id is not null
                   do update set veces = asistente.marcas_tv_desconocidas.veces + 1,
                                 visto_por_ultima_vez = now()""",
                (org, limpia, normalizada, conversation_id))
    except Exception as e:                            # noqa: BLE001
        registrar("guias-tv", "no se pudo anotar la marca desconocida",
                  conversation_id=id_interno(conversation_id), error=e)


def guardar_media(tenant: str, conversation_id: str, media_id: str, tipo: str,
                  contenido: bytes, mime: str | None = None,
                  descripcion: str | None = None,
                  mensaje_id: str | None = None) -> str | None:
    """
    Una foto o audio del cliente, ya comprimido (ver nucleo/canales/media.py).

    Devuelve el id de la fila, o None si ese 'media_id' ya estaba guardado --
    un reintento del webhook no duplica el archivo. Ver
    supabase/202608121842_multimedia.sql para por que vive en Postgres y no en un almacen
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


def conversacion_de_caso(tenant: str, caso_id: str) -> dict | None:
    """
    De donde salio un caso del CRM: por que canal entro, con que etiqueta y
    por que se paso a una persona.

    El CRM no guarda nada de esto -- para el, un caso escalado es un caso mas,
    sin origen. Quien lo abre ve una conversacion transcrita y no puede saber
    si entro por el canal de mensajeria o por la API, ni cual fue el motivo
    que disparo la escalada. Aca si esta, porque es la misma fila que se marco
    al escalar (ver marcar_escalada).

    Devuelve None cuando el caso no lo creo el asistente: un ticket cargado a
    mano no tiene conversacion detras, y eso no es un error.

    SI devuelve 'id_cliente' y el serial del equipo. Este comentario decia lo
    contrario -- que eran identificadores tecnicos y que una pantalla no los
    necesitaba -- y era cierto mientras la pantalla solo mostraba el caso.
    Dejo de serlo cuando el ticket tiene que ofrecerle al colaborador un
    enlace directo al cliente en los sistemas externos.
    Y son JUSTO estos los que hay que usar, no el nombre ni la cedula: armar
    un enlace a partir del nombre abre el perfil de cualquier homonimo. El
    identificador es lo unico que no se parece a otro.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, canal, etiqueta, motivo_escalamiento, nombre_cliente,
                      escalada_a_humano, necesita_atencion_humana, creado_en,
                      id_cliente, datos_sesion
               from asistente.conversations
               where organization_id = %s and caso_id = %s
               limit 1""",
            (org, caso_id))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def identidad_de_conversacion(tenant: str, conversation_id: str) -> dict | None:
    """
    A QUE cliente del sistema externo apunta esta conversacion. Nada mas.

    Existe para no leer el hilo entero cuando lo unico que hace falta es el
    identificador: 'mensajes_de()' trae todos los mensajes y sus adjuntos, y
    quien necesita saber a que cliente consultarle la ficha no necesita nada
    de eso.

    Devuelve solo identificadores -- ninguno de los datos personales que la
    ficha traera despues. Esos se leen en vivo del sistema del ISP y no se
    guardan aca (PRD: las respuestas crudas de la API externa no se
    persisten), asi que esta fila no puede tenerlos aunque se quisiera.

    None si la conversacion no existe o es de otra empresa -- el filtro por
    organizacion lo hace la politica de aislamiento, no un if.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, id_cliente, nombre_cliente, usuario_externo,
                      datos_sesion, escalada_a_humano, control, estado,
                      asignada_a_usuario_id
               from asistente.conversations
               where organization_id = %s and id = %s
               limit 1""",
            (org, conversation_id))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def salud_canal_whatsapp(tenant: str, minutos: int = 60) -> dict:
    """
    Si el canal de WhatsApp esta funcionando, medido sobre lo que YA paso.

    QUE MIDE, Y POR QUE ESTO Y NO OTRA COSA
    ---------------------------------------
    Cuenta los envios de la ultima ventana y CUANTOS DE ELLOS TIENEN ACUSE de
    Meta. Un envio que falla se ve solo: la burbuja queda marcada en el hilo y
    con su boton de reintento, asi que quien atiende se entera. Lo que NO se
    ve es que los envios salgan bien y los acuses dejen de volver -- el
    servicio parece sano y nadie sabe si al cliente le llego nada.

    Esa falla exacta ocurrio: el seguimiento de entregas estuvo roto DIEZ DIAS
    (D17) sin que ninguna pantalla lo dijera. Este contador existe por eso.

    No hace ninguna llamada a Meta: no hay endpoint de salud que preguntarle,
    y un "99.99%" inventado seria peor que no decir nada. Se mide lo que pasó.

    Devuelve los tres numeros crudos y NINGUN veredicto: que significa cada
    combinacion lo decide quien los muestra, en un solo lugar y con pruebas
    (ver lib/conversaciones/canal.js).
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select
                     count(*) as enviados,
                     count(*) filter (where estado_entrega is not null) as con_acuse,
                     count(*) filter (where error is not null
                                         or estado in ('rechazado', 'incierto')) as fallidos
                   from asistente.whatsapp_salidas
                   where organization_id = %s
                     and adquirido_en > now() - make_interval(mins => %s)""",
                (org, int(minutos)))
            fila = cur.fetchone() or {}
            return {"ventana_minutos": int(minutos),
                    "enviados": int(fila.get("enviados") or 0),
                    "con_acuse": int(fila.get("con_acuse") or 0),
                    "fallidos": int(fila.get("fallidos") or 0)}
    except Exception as e:
        # No poder medir la salud del canal no puede tumbar la cola. Se
        # devuelve None en 'enviados' para que la pantalla diga "no se pudo
        # medir" en vez de "todo bien", que es lo que diria un cero.
        registrar("canal", "no se pudo medir la salud de whatsapp", error=e)
        return {"ventana_minutos": int(minutos), "enviados": None,
                "con_acuse": None, "fallidos": None}


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


def media_bytes_por_media_id(tenant: str, media_id: str) -> tuple[bytes, str] | None:
    """
    Igual que media_bytes(), pero busca por la columna 'media_id' (texto, la
    unica que unique(organization_id, media_id) garantiza), no por 'id' (la
    clave primaria, generada por Postgres con gen_random_uuid()).

    Existe porque son dos identificadores DISTINTOS con la misma forma de
    UUID -- 'id' no se conoce hasta despues del INSERT, y un archivo que el
    motor genera (nucleo/herramientas/informes.py) necesita poder referenciar
    su propio identificador ANTES de que la fila exista (se genera durante
    motor.responder(), se inserta recien en nucleo/canales/api.py, una vez
    resuelto conversation_id -- ver el docstring de responder()). Para eso el
    UUID lo elige el codigo, no Postgres, y viaja en 'media_id'.

    Para una foto recibida de WhatsApp, en cambio, 'media_id' es el id de
    Meta y el que arma la URL de descarga sigue siendo 'id' (ver
    media_bytes() y GET /media/<id_media>) -- no se toca ese camino.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select contenido, mime from asistente.media
               where organization_id = %s and media_id = %s""",
            (org, media_id))
        fila = cur.fetchone()
        if not fila:
            return None
        return bytes(fila["contenido"]), fila["mime"] or "application/octet-stream"


def purgar_media(tenant: str, dias: int) -> int:
    """
    Borra los adjuntos mas viejos que 'dias'. Devuelve cuantos.

    Existe porque la retencion de multimedia es MAS CORTA que la de las
    conversaciones a proposito (ver supabase/202608121842_multimedia.sql): el texto es
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
    ningun lado mas. Ver supabase/202608121844_conservar_conversacion.sql.

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


def registrar_estado_escalada(tenant: str, conversation_id: str, estado: str,
                             detalle: str, necesita_atencion: bool = False) -> None:
    """
    Deja escrito como termino el traspaso, y --si hace falta-- marca que la
    conversacion necesita a una persona.

    'necesita_atencion' se usa cuando el evaluador fallo (NO_DETERMINADO): no
    se sabe si correspondia escalar, asi que NO se toca 'escalada_a_humano'
    --eso pausaria al bot y afirmaria un traspaso que no ocurrio-- pero la
    conversacion queda marcada para que alguien la mire. Es el registro real
    mas barato que existe: una escritura, sin CRM ni sistema externo de por
    medio, y la bandeja la muestra igual.

    Nunca rompe el turno: la respuesta al cliente ya se decidio, y no poder
    anotar esto no es motivo para tumbarla.
    """
    try:
        with sesion(tenant) as (cur, org):
            if necesita_atencion:
                cur.execute(
                    """update asistente.conversations
                       set estado_escalada = %s, escalada_detalle = %s,
                           necesita_atencion_humana = true, actualizado_en = now()
                       where organization_id = %s and id = %s""",
                    (estado, detalle[:400], org, conversation_id))
            else:
                cur.execute(
                    """update asistente.conversations
                       set estado_escalada = %s, escalada_detalle = %s
                       where organization_id = %s and id = %s""",
                    (estado, detalle[:400], org, conversation_id))
    except Exception as e:
        registrar("escalamiento", "no se pudo anotar el estado", estado=estado,
                  conversation_id=id_interno(conversation_id), error=e)


def control_de_conversacion_abierta(tenant: str, canal: str,
                                    usuario_externo: str) -> dict | None:
    """
    Quien controla la conversacion ABIERTA de este usuario, leido de la base en
    cada turno. None si no hay ninguna abierta (un contacto nuevo: no hay nada
    que controlar). LEVANTA si la base no responde: quien llama falla cerrado y
    no corre el modelo -- la memoria del proceso nunca decide el control.

    Devuelve {'conversation_id', 'control_efectivo', 'control_motivo',
    'relevo_version'}.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, relevo_version, control, control_motivo,
                      escalada_a_humano, necesita_atencion_humana
               from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo))
        fila = cur.fetchone()
    if not fila:
        return None
    return {"conversation_id": str(fila["id"]),
            "control_efectivo": regla_control.control_efectivo(fila),
            "control_motivo": fila["control_motivo"],
            "relevo_version": fila["relevo_version"]}


def descartar_respuesta_ia(tenant: str, mensaje_id: str) -> bool:
    """
    Marca una respuesta de la IA que quedo guardada y NO se le envio al cliente
    porque el control cambio antes del envio (D24). La fila se conserva --es
    auditoria: la IA la calculo y se pago-- pero con estado_entrega
    'descartado' no entra al historial del modelo ni al resumen.

    Solo toca filas 'assistant' de origen 'ia' que todavia no tienen wamid: una
    respuesta que Meta ya acepto no se puede descartar.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.messages
               set estado_entrega = 'descartado', error_entrega = 'cambio_de_control'
               where organization_id = %s and id = %s
                 and rol = 'assistant' and origen = 'ia' and wamid is null""",
            (org, mensaje_id))
        return cur.rowcount > 0


def vigencia_de_escalada(tenant: str, conversation_id: str, version: int,
                         invalidan: tuple[str, ...]) -> dict | None:
    """
    Si la escalada que dejo la conversacion en relevo_version 'version' sigue
    vigente (nucleo/relevo/autorizacion.py, SYNC_ESCALADA). None si la
    conversacion no existe. LEVANTA si la base no responde: quien llama falla
    cerrado.

    'invalidada' mira los eventos POSTERIORES a esa escalada, por la version
    que cada evento guarda en 'datos': una toma o una reasignacion suben la
    version y no invalidan; una devolucion o un cierre, si.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select c.estado, c.relevo_version, c.control, c.control_motivo,
                      c.escalada_a_humano, c.necesita_atencion_humana,
                      exists(select 1 from asistente.relevo_eventos e
                              where e.organization_id = c.organization_id
                                and e.conversation_id = c.id and e.tipo = 'escalada'
                                and (e.datos->>'version')::int = %s) as originada,
                      exists(select 1 from asistente.relevo_eventos e
                              where e.organization_id = c.organization_id
                                and e.conversation_id = c.id and e.tipo = any(%s)
                                and (e.datos->>'version')::int > %s) as invalidada
               from asistente.conversations c
               where c.organization_id = %s and c.id = %s""",
            (int(version), list(invalidan), int(version), org, conversation_id))
        fila = cur.fetchone()
    if not fila:
        return None
    return {"estado": fila["estado"], "control_efectivo": regla_control.control_efectivo(fila),
            "relevo_version": fila["relevo_version"], "originada": bool(fila["originada"]),
            "invalidada": bool(fila["invalidada"])}


def control_efectivo_de(tenant: str, conversation_id: str) -> str | None:
    """
    Quien controla la conversacion hoy ('ia' | 'humano'), por la regla unica de
    nucleo/relevo/control.py. None si no existe o no es de este tenant. La usan
    las guardas del backend; ninguna ruta deriva el control por su cuenta.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select relevo_version, control, escalada_a_humano, necesita_atencion_humana
               from asistente.conversations
               where organization_id = %s and id = %s""",
            (org, conversation_id))
        fila = cur.fetchone()
    return regla_control.control_efectivo(fila) if fila else None


def marcar_atendida(tenant: str, conversation_id: str, por: str | None) -> bool:
    """
    Marca una conversacion escalada como atendida SIN pasar por el chat --
    el colaborador la resolvio por telefono, en persona, o por otro canal.
    No es lo mismo que responder de verdad (eso ya marca 'atendida' solo,
    via el exists de ultima_actividad()): esto es el camino manual para
    cuando responder por el chat no corresponde. Ver
    supabase/202608131419_atendida_manual.sql.

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
       supabase/202608121844_conservar_conversacion.sql.

    2. Tener alguna respuesta marcada como ejemplo valido. Esas alimentan el
       manual de procedimientos (supabase/202608121018_ejemplos_validados.sql) y cuelgan
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

    Ver supabase/202608121841_webhook_eventos.sql para por que esto vive en la base y no
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
                                  llamada: dict, profile_id: str | None = None) -> None:
    """
    Una fila de asistente.tool_calls por herramienta que el agente invoco
    este turno -- ver nucleo/modelo/motor.py:responder(), que arma 'llamada'
    (ya con los parametros enmascarados, nunca el dato crudo del cliente).
    Es la base de "ver proceso" en /conversaciones: que hizo el agente, en
    que orden, si fallo.

    'profile_id' es quien ejecuto -- el perfil del CRM, cuando el turno vino
    de la app web con profile_id (ver POST /chat). None en canales de
    cliente final (WhatsApp): ahi no hay un colaborador que identificar.

    Nunca rompe el turno: mismo criterio que registrar_mensaje. Perder una
    fila de auditoria no puede tumbar la atencion al cliente.
    """
    registrar_llamadas_herramienta(tenant, conversation_id, rol, [llamada],
                                   profile_id=profile_id)


def registrar_llamadas_herramienta(tenant: str, conversation_id: str, rol: str,
                                   llamadas: list[dict],
                                   profile_id: str | None = None) -> None:
    """
    TODA la traza del turno en UNA ida a la base.

    Antes era una insercion por herramienta, y cada una es una ida y vuelta a
    Postgres. Medido el 07/09/2026 contra la base de produccion: 1.054 ms de
    mediana por viaje. Un turno de diagnostico llama a cinco herramientas, asi
    que la traza costaba casi SEIS SEGUNDOS -- y se pagaban ANTES de mandarle
    la respuesta al cliente, que ya estaba escrita.

    Visto en una conversacion real:

        22:25:24.4  el cliente escribe
        22:25:26.7  la respuesta esta lista      (2.3s de modelo y APIs)
        22:25:27.7  se guarda derivar_a_area
        ...
        22:25:33.5  se guarda consultar_senal_ont
                    -> recien aca sale el mensaje

    Con executemany son 5 filas en un viaje. Sigue sin romper el turno si
    falla: perder auditoria no puede tumbar la atencion.
    """
    if not llamadas:
        return
    try:
        with sesion(tenant) as (cur, org):
            cur.executemany(
                """insert into asistente.tool_calls
                     (organization_id, conversation_id, herramienta, parametros,
                      rol_solicitante, exito, n_registros, codigo_error,
                      duracion_ms, es_escritura, profile_id, es_bloqueo)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(org, conversation_id, l["herramienta"],
                  json.dumps(l["parametros"], ensure_ascii=False),
                  rol, l["exito"], l["n_registros"], l["codigo_error"],
                  l["duracion_ms"], l["es_escritura"], profile_id,
                  bool(l.get("es_bloqueo"))) for l in llamadas])
    except Exception as e:
        registrar("persistencia", "no se pudo guardar la traza", error=e)


def herramientas_de(tenant: str, conversation_id: str) -> list[dict]:
    """
    El registro de herramientas que uso el agente en una conversacion, en
    orden -- lo que muestra el panel "Ver proceso" en el detalle de
    /conversaciones.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select herramienta, parametros, exito, n_registros, codigo_error,
                      duracion_ms, es_escritura, es_bloqueo, creado_en
               from asistente.tool_calls
               where organization_id = %s and conversation_id = %s
               order by creado_en asc""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]


def eventos_de_relevo(tenant: str, conversation_id: str) -> list[dict]:
    """
    Quien tuvo esta conversacion, en orden -- el registro del relevo.

    Los eventos se escriben en cada transicion desde que existe el relevo
    (B3.3) y hasta ahora NADIE los leia: la pantalla mostraba el estado
    ACTUAL --quien la lleva-- pero no como se llego ahi. Una reasignacion y
    una devolucion a la IA se veian igual desde afuera: la conversacion
    simplemente aparecia en otras manos.

    Solo lectura y tenant-scoped, mismo criterio que herramientas_de. 'datos'
    sale tal cual: lo que hay ahi son versiones del relevo, nombres de quienes
    actuaron y motivos que escribio el equipo -- nunca texto del cliente ni
    respuestas de un sistema externo. El esquema de cada tipo esta declarado
    en nucleo/relevo/transiciones.py (ESQUEMAS) y la base lo valida.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select tipo, actor_tipo, actor_usuario_id, actor_nombre,
                      datos, creado_en
               from asistente.relevo_eventos
               where organization_id = %s and conversation_id = %s
               order by creado_en asc, id asc""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]


# =============================================================================
#  B4 -- la cola de efectos externos (contrato §3.6)
# =============================================================================

#: Cuanto espera cada reintento, en segundos. Creciente, y con tope: pasados
#: estos, el trabajo es 'fallida_definitiva' y lo mira una persona. No es
#: exponencial puro -- lo que se gana pasada la media hora es despreciable
#: frente a que alguien lo vea.
ESPERAS_REINTENTO = (30, 120, 600, 1800)
MAX_INTENTOS_SINCRONIZACION = len(ESPERAS_REINTENTO)


def encolar_sincronizacion(cur, org: str, conversation_id: str, *, tipo: str,
                           clave: str, datos: dict, datos_version: int = 1) -> str | None:
    """
    Anota que un efecto externo HAY QUE hacerlo. Recibe el cursor: va en la
    MISMA transaccion que la transicion que lo necesita, para que no exista un
    estado donde la conversacion quedo escalada y la intencion se perdio.

    'datos' es la intencion, no el resultado: exactamente lo que habia que
    hacer cuando se decidio. El reconciliador no lo reconstruye con la config
    actual, que pudo cambiar entre el intento y el reintento.

    Devuelve el id, o None si esa clave ya estaba encolada -- la misma
    transicion reintentada no encola dos veces el mismo efecto.
    """
    cur.execute(
        """insert into asistente.sincronizaciones_externas
             (organization_id, conversation_id, tipo, estado, datos_version,
              datos_intencion, proximo_intento_en, clave_idempotencia)
           values (%s, %s, %s, 'pendiente', %s, %s::jsonb, now(), %s)
           on conflict (organization_id, clave_idempotencia) do nothing
           returning id""",
        (org, conversation_id, tipo, datos_version,
         json.dumps(datos or {}, ensure_ascii=False), clave))
    fila = cur.fetchone()
    return str(fila["id"]) if fila else None


def sincronizaciones_elegibles(tenant: str, limite: int = 50) -> list[dict]:
    """
    Lo que el reconciliador puede tomar AHORA: pendientes cuya hora llego.

    'desconocida' y 'fallida_definitiva' no salen nunca de aca -- son
    terminales y esperan a una persona, no a un reloj. Es la diferencia entre
    una cola de reintentos y una de revision, y mezclarlas es justo lo que el
    gate Q2 prohibe para crear_ticket.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, conversation_id, tipo, estado, datos_version,
                      datos_intencion, intentos, referencia_externa,
                      clave_idempotencia
               from asistente.sincronizaciones_externas
               where organization_id = %s
                 and estado = 'pendiente'
                 and proximo_intento_en <= now()
               order by proximo_intento_en asc
               limit %s
               for update skip locked""",
            (org, limite))
        return [dict(f) for f in cur.fetchall()]


def tomar_sincronizacion(tenant: str, sincronizacion_id: str) -> bool:
    """
    Reserva un trabajo antes de salir a la red. Devuelve False si otro proceso
    llego primero: el 'and estado = pendiente' es el candado, y sin el dos
    reconciliadores podrian crear dos casos para la misma conversacion.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.sincronizaciones_externas
               set estado = 'en_curso', intentos = intentos + 1,
                   actualizado_en = now()
               where organization_id = %s and id = %s and estado = 'pendiente'""",
            (org, sincronizacion_id))
        return cur.rowcount == 1


def resolver_sincronizacion(tenant: str, sincronizacion_id: str, *, estado: str,
                            referencia: str | None = None,
                            error_clase: str | None = None,
                            error_codigo: str | None = None) -> bool:
    """
    Sella el desenlace de un intento.

    'pendiente' vuelve a la cola con su espera calculada por el numero de
    intentos; el resto es terminal. La espera se calcula en SQL contra la
    columna de intentos y no con un valor de Python para que dos procesos que
    resuelvan el mismo trabajo no se pisen la hora.
    """
    esperas = ", ".join(str(s) for s in ESPERAS_REINTENTO)
    with sesion(tenant) as (cur, org):
        cur.execute(
            f"""update asistente.sincronizaciones_externas
                set estado = %s,
                    referencia_externa = coalesce(%s, referencia_externa),
                    ultimo_error_clase = %s,
                    ultimo_error_codigo = %s,
                    proximo_intento_en = case
                      when %s = 'pendiente' then
                        now() + make_interval(secs =>
                          (array[{esperas}])[least(greatest(intentos, 1), {len(ESPERAS_REINTENTO)})])
                      else null end,
                    actualizado_en = now()
                where organization_id = %s and id = %s""",
            (estado, referencia, error_clase, error_codigo, estado,
             org, sincronizacion_id))
        return cur.rowcount == 1


def sincronizaciones_de(tenant: str, conversation_id: str) -> list[dict]:
    """
    Que le falta a ESTA conversacion, para el panel de la bandeja.

    Sin 'datos_intencion': lo que la pantalla necesita es que quedo sin hacer y
    si alguien tiene que mirarlo, no los parametros con los que se iba a hacer.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, tipo, estado, intentos, ultimo_error_clase,
                      ultimo_error_codigo, referencia_externa,
                      proximo_intento_en, creado_en, actualizado_en
               from asistente.sincronizaciones_externas
               where organization_id = %s and conversation_id = %s
               order by creado_en asc""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]


def acciones_sobre_el_equipo(tenant: str, conversation_id: str) -> list[dict]:
    """
    Que se le hizo al equipo del cliente en esta conversacion, y si funciono.

    SIN las mediciones. 'medicion_previa' y 'medicion_posterior' se guardan
    crudas a proposito --para poder rehacer la conclusion a mano si alguna vez
    el estado no se entiende-- y son respuestas del sistema externo: no salen
    de la base por esta puerta, igual que herramientas_de no devuelve el dato
    consultado. Lo que la pantalla necesita es el veredicto y su motivo, que
    los escribe Dexter.

    Ojo con 'ACCION_CONFIRMADA': significa que la accion produjo el efecto
    tecnico que el sistema PUEDE medir --en reiniciar_ont, que el equipo
    reinicio y volvio-- y no que el cliente tenga internet. Eso no lo dice
    ningun endpoint; lo sabe el cliente y hay que preguntarselo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, herramienta, ejecutada_en, estado, por_que,
                      intentos, max_intentos, verificada_en
               from asistente.verificaciones_accion
               where organization_id = %s and conversation_id = %s
               order by ejecutada_en desc""",
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
                      d.aprobado_por, d.aprobado_en,
                      (select count(*) from asistente.document_chunks c
                        where c.document_id = d.id and c.vigente) as n_fragmentos
               from asistente.documents d
               where d.organization_id = %s
               -- Los pendientes PRIMERO: son los que piden una decision, y
               -- una lista que los mezcla alfabeticamente los esconde entre
               -- los veinte que ya estan resueltos.
               order by (d.estado = 'pendiente') desc, d.codigo, d.version desc""",
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


def guardar_herramienta_propuesta(tenant: str, descripcion_pedido: str,
                                  sondeo: dict, herramienta_propuesta: dict,
                                  propuesto_por: str) -> str:
    """
    Un borrador de Herramienta que el rol 'configuracion_guiada' arma
    despues de sondear una API real (nucleo/herramientas/sondeo.py). Nunca
    se activa sola -- ver aprobar_herramienta_propuesta(). Devuelve el id
    para que el turno pueda mencionarselo al ADMIN.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.herramientas_propuestas
                 (organization_id, descripcion_pedido, sondeo,
                  herramienta_propuesta, propuesto_por)
               values (%s, %s, %s, %s, %s)
               returning id""",
            (org, descripcion_pedido, json.dumps(sondeo, ensure_ascii=False),
             json.dumps(herramienta_propuesta, ensure_ascii=False), propuesto_por))
        return str(cur.fetchone()["id"])


def herramientas_propuestas_de(tenant: str, estado: str | None = None) -> list[dict]:
    """'estado=None' trae todas (pendiente/aprobada/rechazada); pasar un
    estado puntual filtra en la consulta -- mismo patron que revisiones_de()."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, descripcion_pedido, sondeo, herramienta_propuesta,
                      propuesto_por, estado, motivo_rechazo, revisado_por,
                      creado_en, revisado_en
               from asistente.herramientas_propuestas
               where organization_id = %s
                 and (%s::text is null or estado = %s)
               order by creado_en desc""",
            (org, estado, estado))
        return [dict(f) for f in cur.fetchall()]


def herramienta_propuesta_de(tenant: str, propuesta_id: str) -> dict | None:
    """Una propuesta puntual -- para aprobar_herramienta_propuesta(), que
    necesita el 'herramienta_propuesta' completo antes de escribirlo al
    catalogo real."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, descripcion_pedido, sondeo, herramienta_propuesta,
                      propuesto_por, estado, motivo_rechazo, revisado_por,
                      creado_en, revisado_en
               from asistente.herramientas_propuestas
               where organization_id = %s and id = %s""",
            (org, propuesta_id))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def resolver_herramienta_propuesta(tenant: str, propuesta_id: str, estado: str,
                                   revisado_por: str, motivo_rechazo: str | None = None) -> bool:
    """Aprobar o rechazar una propuesta -- la unica forma en que una de
    estas pasa de 'pendiente' a algo que una persona confirmo. Devuelve
    False si el id no existe o no es de este tenant."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.herramientas_propuestas
               set estado = %s, revisado_por = %s, revisado_en = now(),
                   motivo_rechazo = %s
               where organization_id = %s and id = %s""",
            (estado, revisado_por, motivo_rechazo, org, propuesta_id))
        return cur.rowcount > 0


def clave_de_equivalencia(conversation_id: str | None, herramienta: str,
                          argumentos: dict) -> str | None:
    """
    Hash de (conversacion, herramienta, argumentos en forma canonica) (§3.4).

    Sirve para una sola cosa: que la IA no proponga dos veces lo mismo mientras
    la primera sigue viva. Canonica = claves ordenadas y separadores fijos, o
    el mismo pedido escrito en otro orden daria otro hash y pasaria como
    distinto.

    Sin conversacion no hay clave: una accion de legado no se compara con nada,
    y darle una la haria colisionar con las demas de legado.
    """
    if not conversation_id:
        return None
    canonico = json.dumps(argumentos or {}, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"))
    crudo = f"{conversation_id}|{herramienta}|{canonico}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def guardar_accion_propuesta(tenant: str, herramienta: str, argumentos: dict,
                             resumen: str, rol_solicitante: str,
                             propuesto_por: str,
                             conversation_id: str | None = None,
                             vigencia_minutos: int | None = None
                             ) -> tuple[str, bool]:
    """
    Una escritura real (crear/editar algo en un sistema externo) que quedo
    pendiente porque su Herramienta declara requiere_confirmacion -- ver
    nucleo/modelo/motor.py, el punto donde se intercepta antes de llegar a
    _ejecutar_tool(). 'argumentos' guarda los valores REALES (no
    enmascarados, a diferencia de tool_calls): sin ellos no se podria
    ejecutar la accion al aprobar.

    Devuelve (id, ya_existia). 'ya_existia' es True cuando habia una propuesta
    EQUIVALENTE viva y se devuelve esa en vez de crear otra (T12): misma
    conversacion, misma herramienta, mismos argumentos. Sin eso, un cliente que
    insiste tres veces deja tres tickets para el mismo problema, y quien
    aprueba no tiene como saber que son el mismo.

    La deduplicacion la sostiene el INDICE, no una consulta previa: comprobar
    antes y escribir despues deja una ventana entre las dos, y ocho hilos
    concurrentes la encuentran.

    'vigencia_minutos' sale de la herramienta (§3.7). Si no la declara, la fila
    nace sin 'vence_en' -- fabricar un plazo seria inventar una decision que
    nadie tomo. Sin vence_en no vence; con el, aprobar despues es imposible.
    """
    clave = clave_de_equivalencia(conversation_id, herramienta, argumentos)
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.acciones_propuestas
                 (organization_id, herramienta, argumentos, resumen,
                  rol_solicitante, propuesto_por, conversation_id, vence_en,
                  clave_equivalencia)
               values (%s, %s, %s, %s, %s, %s, %s,
                       case when %s::int is null then null
                            else now() + make_interval(mins => %s::int) end,
                       %s)
               on conflict (organization_id, clave_equivalencia)
                 where estado in ('pendiente', 'ejecutando')
                 do nothing
               returning id""",
            (org, herramienta, json.dumps(argumentos, ensure_ascii=False),
             resumen, rol_solicitante, propuesto_por, conversation_id,
             vigencia_minutos, vigencia_minutos, clave))
        fila = cur.fetchone()
        if fila is not None:
            return str(fila["id"]), False

        # La equivalente viva gano la carrera (o ya estaba). No se crea otra y
        # se devuelve la que existe: el modelo tiene que recibir ESA, no una
        # copia -- si recibiera una nueva, hablaria de una accion que nadie va
        # a aprobar (T12).
        cur.execute(
            """select id from asistente.acciones_propuestas
               where organization_id = %s and clave_equivalencia = %s
                 and estado in ('pendiente', 'ejecutando')""",
            (org, clave))
        existente = cur.fetchone()
        if existente is None:
            # Carrera perdida contra algo que ya no esta vivo: el conflicto
            # existio y para cuando se fue a leer, la otra ya se resolvio.
            # Reintentar aca seria abrir un bucle; el turno lo informa.
            raise RuntimeError("no se pudo guardar la accion propuesta")
        if conversation_id:
            registrar_evento_de_accion(
                cur, org, str(existente["id"]), "accion_propuesta_duplicada",
                motivo="ya habia una propuesta equivalente viva",
                actor_tipo="sistema", conversation_id=conversation_id)
        return str(existente["id"]), True


def acciones_propuestas_de(tenant: str, estado: str | None = None) -> list[dict]:
    """
    'estado=None' trae todas -- mismo patron que herramientas_propuestas_de().

    SIN 'argumentos'. A diferencia de tool_calls, ahi estan los valores REALES
    y sin enmascarar (ver guardar_accion_propuesta): el telefono, la cedula, la
    direccion con los que se iba a escribir afuera. Para revisar una accion
    alcanza el resumen --que existe justamente para eso-- y quien la necesita
    completa para ejecutarla usa accion_propuesta_de(), que es otro camino y
    otra decision.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, herramienta, resumen, rol_solicitante,
                      propuesto_por, estado, motivo_rechazo, revisado_por,
                      resultado_ejecucion, codigo_error, creado_en, revisado_en
               from asistente.acciones_propuestas
               where organization_id = %s
                 and (%s::text is null or estado = %s)
               order by creado_en desc""",
            (org, estado, estado))
        return [dict(f) for f in cur.fetchall()]


def accion_propuesta_de(tenant: str, accion_id: str) -> dict | None:
    """Una propuesta puntual -- para ejecutarla al aprobar, que necesita
    'herramienta'+'argumentos' completos."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, herramienta, argumentos, resumen, rol_solicitante,
                      propuesto_por, estado, motivo_rechazo, revisado_por,
                      resultado_ejecucion, codigo_error, creado_en, revisado_en,
                      conversation_id, vence_en, clave_equivalencia
               from asistente.acciones_propuestas
               where organization_id = %s and id = %s""",
            (org, accion_id))
        fila = cur.fetchone()
        return dict(fila) if fila else None


def resolver_accion_propuesta(tenant: str, accion_id: str, estado: str,
                              revisado_por: str, motivo_rechazo: str | None = None,
                              resultado_ejecucion: dict | None = None,
                              codigo_error: str | None = None) -> bool:
    """Aprobar o rechazar una accion. Si se aprueba y se ejecuta, el
    llamador pasa 'resultado_ejecucion' (lo que devolvio la API real) en la
    MISMA actualizacion -- para que 'aprobada' y 'ya se sabe que paso'
    queden juntos, nunca una fila 'aprobada' que en realidad todavia no se
    intento ejecutar. Devuelve False si el id no existe o no es de este
    tenant."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = %s, revisado_por = %s, revisado_en = now(),
                   motivo_rechazo = %s, resultado_ejecucion = %s, codigo_error = %s
               where organization_id = %s and id = %s""",
            (estado, revisado_por, motivo_rechazo,
             json.dumps(resultado_ejecucion, ensure_ascii=False) if resultado_ejecucion is not None else None,
             codigo_error, org, accion_id))
        return cur.rowcount > 0


# =============================================================================
#  G3 -- el legado de acciones propuestas (contrato §11.4, X24, I6, I12)
# =============================================================================

def es_accion_de_legado(accion: dict) -> bool:
    """
    Si esta accion NO tiene con que revalidarse.

    El criterio es UNO SOLO y sale del contrato: sin `conversation_id` no hay
    contexto actual contra el cual comprobar que lo que se iba a hacer todavia
    tiene sentido (§3.7), asi que aprobarla es ejecutar a ciegas argumentos
    congelados -- lo que X24 prohibe.

    NO se mira la edad ni el tipo. Una accion de hace un minuto sin
    conversacion es igual de inejecutable que una de hace un mes: el problema
    nunca fue el tiempo, fue que no hay nada contra que revalidar. Y una regla
    por edad ademas se vuelve falsa sola, en silencio, el dia que alguien
    cambie el plazo.

    Hoy la columna no existe --llega en B5-- asi que esto es True para todas.
    Cuando exista, la misma funcion deja pasar las que la tengan, sin tocarla.
    """
    return not (accion or {}).get("conversation_id")


def registrar_evento_de_accion(cur, org, accion_id: str, tipo: str, *,
                               motivo: str | None = None,
                               actor_tipo: str = "operador",
                               actor_nombre: str | None = None,
                               conversation_id: str | None = None,
                               datos: dict | None = None) -> None:
    """
    Un evento en el expediente de una accion.

    Recibe el cursor en vez de abrir su propia sesion: I12 exige que el evento
    y el cambio de estado entren en la MISMA transaccion. Con una sesion propia
    existiria el estado intermedio donde la accion ya esta cancelada y nadie
    registro quien ni por que.
    """
    cur.execute(
        """insert into asistente.acciones_eventos
             (organization_id, accion_id, conversation_id, tipo, motivo,
              actor_tipo, actor_nombre, datos)
           values (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (org, accion_id, conversation_id, tipo, motivo, actor_tipo,
         actor_nombre, json.dumps(datos or {}, ensure_ascii=False)))


def ultima_promesa_registrada(tenant: str, id_factura: str):
    """
    Cuando fue la ultima promesa que DEXTER dejo registrada sobre esta factura,
    o None si no hay ninguna.

    Devuelve None cuando consulto y no hay. LEVANTA si no pudo consultar -- y
    esa diferencia es el punto: quien llama distingue "no hay promesa" de "no
    pude averiguarlo", y lo segundo impide proponer. Tragarse el error aqui
    haria que una base caida pareciera un cliente sin historial.

    SOLO VE LO DE DEXTER. Una promesa que un agente cargo a mano en el panel
    de facturacion es invisible: esa API no permite consultarlas. Es una
    cobertura parcial, dicha y no disimulada.

    'aprobada' entra ademas de 'ejecutada_ok': entre que alguien aprueba y que
    el efecto se resuelve hay una ventana, y en esa ventana la promesa ya se
    decidio. Contarla como inexistente dejaria proponer una segunda.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select max(coalesce(revisado_en, creado_en)) as cuando
                 from asistente.acciones_propuestas
                where organization_id = %s
                  and estado in ('aprobada', 'ejecutando', 'ejecutada_ok', 'desconocida')
                  and argumentos ->> 'id_factura' = %s""",
            (org, str(id_factura)))
        fila = cur.fetchone()
        return fila["cuando"] if fila else None


def cancelar_accion_propuesta(tenant: str, accion_id: str, motivo: str,
                              cancelada_por: str) -> tuple[str | None, bool]:
    """
    Cancela una accion pendiente y deja su evento, en una sola transaccion.

    Devuelve (estado, la_cancelo_esta_llamada):

        (None, False)         no existe, o es de otro tenant
        ('cancelada', True)   la cancelo esta llamada
        ('cancelada', False)  ya estaba cancelada por alguien mas
        (<otro>, False)       ya estaba resuelta de otra forma

    Los dos booleanos importan y por eso el estado solo no alcanza: devolver
    'cancelada' a secas hacia indistinguible "la cancele" de "ya lo estaba", y
    el endpoint respondia 200 a la segunda. Dos operadores sobre la misma lista
    es lo normal, y el segundo tiene que enterarse de que llego tarde.

    'cancelada' NO es 'rechazada'. Rechazada es "alguien la evaluo y dijo que
    no"; cancelada es "quedo obsoleta y nadie la va a evaluar". Las dos evitan
    la ejecucion, pero en un registro que existe para auditar decir cual fue es
    el registro entero.
    """
    with sesion(tenant) as (cur, org):
        # El 'and estado' del UPDATE es el candado: dos operadores cancelando a
        # la vez, o un doble clic, escriben una sola vez y el segundo se entera.
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = 'cancelada', motivo_rechazo = %s,
                   revisado_por = %s, revisado_en = now()
               where organization_id = %s and id = %s and estado = 'pendiente'
               returning id""",
            (motivo, cancelada_por, org, accion_id))
        if cur.fetchone() is None:
            cur.execute(
                """select estado from asistente.acciones_propuestas
                   where organization_id = %s and id = %s""", (org, accion_id))
            fila = cur.fetchone()
            return (fila["estado"], False) if fila else (None, False)

        registrar_evento_de_accion(
            cur, org, accion_id, "accion_cancelada", motivo=motivo,
            actor_nombre=cancelada_por)
        return "cancelada", True


def registrar_aprobacion_rechazada(tenant: str, accion_id: str, motivo: str,
                                   intentada_por: str | None) -> None:
    """
    Deja constancia de que alguien intento aprobar una accion de legado.

    Un 409 se responde y se pierde. Un intento repetido contra el legado es
    algo que deberia poder verse -- si pasa seguido, lo que falta es explicar
    mejor por que esas acciones no se aprueban, no repetir el rechazo.
    """
    with sesion(tenant) as (cur, org):
        registrar_evento_de_accion(
            cur, org, accion_id, "accion_aprobacion_rechazada", motivo=motivo,
            actor_tipo="operador" if intentada_por else "sistema",
            actor_nombre=intentada_por)


# =============================================================================
#  B5 -- aprobar una accion, en los cuatro pasos de §9.3
# =============================================================================
#  1. reservar   transaccion corta y CONDICIONADA. Quien obtiene la fila sigue.
#  2. revalidar  fuera de transaccion (§3.7). Lo hace el llamador.
#  3. ejecutar   fuera de transaccion. Lo hace el llamador.
#  4. resolver   transaccion corta con el desenlace.
#
#  Los pasos 2 y 3 NO estan aca a proposito: mantener una transaccion abierta
#  mientras se espera una API deja sesiones 'idle in transaction' detras del
#  pooler, y eso ya se midio una vez (X23). El estado 'ejecutando' existe
#  justamente para cubrir ese hueco sin lock: dice "alguien la tomo" sin que
#  nadie tenga una transaccion abierta.

def reservar_accion(tenant: str, accion_id: str, reservada_por: str) -> dict:
    """
    Paso 1: toma la accion para ejecutarla, o explica por que no se puede.

    Devuelve {'ok': True, 'accion': fila} o {'ok': False, 'motivo': <codigo>}.

    Las tres condiciones viajan DENTRO del UPDATE y no antes: comprobarlas en
    una consulta aparte deja una ventana entre la comprobacion y la escritura,
    y dos operadores que aprueban a la vez la encuentran. Solo el que obtiene
    la fila sigue; el otro recibe 'ya_no_pendiente' y no ejecuta nada.

    Motivos posibles:
        no_existe          otro tenant, o nunca existio
        de_legado          sin conversation_id (X24). No se reserva jamas.
        vencida            paso su vence_en -- se marca 'vencida' al pasar
        conversacion_cerrada
        ya_no_pendiente    alguien llego primero
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, estado, conversation_id, vence_en, herramienta,
                      argumentos,
                      (vence_en is not null and vence_en <= now()) as expirada,
                      (select estado from asistente.conversations c
                        where c.id = a.conversation_id) as estado_conversacion
               from asistente.acciones_propuestas a
               where organization_id = %s and id = %s""",
            (org, accion_id))
        previa = cur.fetchone()
        if previa is None:
            return {"ok": False, "motivo": "no_existe"}
        if not previa["conversation_id"]:
            return {"ok": False, "motivo": "de_legado", "estado": previa["estado"]}

        # Vencida: se marca al pasar por aca. No hay proceso que venza acciones
        # solo --§11.4 lo prohibe para el legado y no hace falta para el resto--
        # asi que el momento de descubrirlo es cuando alguien la toca.
        if previa["expirada"] and previa["estado"] == "pendiente":
            cur.execute(
                """update asistente.acciones_propuestas
                   set estado = 'vencida', revisado_en = now()
                   where organization_id = %s and id = %s and estado = 'pendiente'""",
                (org, accion_id))
            if cur.rowcount:
                registrar_evento_de_accion(
                    cur, org, accion_id, "accion_vencida",
                    motivo="paso su plazo de vigencia antes de que alguien la aprobara",
                    actor_tipo="sistema",
                    conversation_id=str(previa["conversation_id"]))
            return {"ok": False, "motivo": "vencida"}

        cur.execute(
            """update asistente.acciones_propuestas a
               set estado = 'ejecutando', revisado_por = %s, revisado_en = now()
               where a.organization_id = %s and a.id = %s
                 and a.estado = 'pendiente'
                 and (a.vence_en is null or a.vence_en > now())
                 and a.conversation_id is not null
                 and exists (select 1 from asistente.conversations c
                              where c.id = a.conversation_id
                                and c.organization_id = a.organization_id
                                and c.estado = 'abierta')
               returning a.id, a.herramienta, a.argumentos, a.conversation_id""",
            (reservada_por, org, accion_id))
        fila = cur.fetchone()
        if fila is None:
            if (previa["estado_conversacion"] or "") != "abierta":
                return {"ok": False, "motivo": "conversacion_cerrada"}
            return {"ok": False, "motivo": "ya_no_pendiente",
                    "estado": previa["estado"]}
        return {"ok": True, "accion": dict(fila)}


def liberar_accion(tenant: str, accion_id: str, motivo: str) -> bool:
    """
    Devuelve una accion reservada a 'pendiente' (§9.3 paso 2).

    Es para UN solo caso: la revalidacion no se pudo correr --API caida,
    timeout-- asi que no se sabe si la condicion se cumple. Como no se ejecuto
    nada, la accion vuelve a estar disponible y el operador ve "no se pudo
    comprobar, reintentar".

    NO se usa cuando la revalidacion corre y falla: eso es 'vencida', porque la
    condicion se comprobo y no se cumple. La diferencia es la misma de siempre:
    no saber no es lo mismo que saber que no.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = 'pendiente', revisado_por = null, revisado_en = null,
                   codigo_error = %s
               where organization_id = %s and id = %s and estado = 'ejecutando'""",
            (motivo[:200], org, accion_id))
        return cur.rowcount > 0


def vencer_accion(tenant: str, accion_id: str, codigo: str,
                  conversation_id: str | None = None) -> bool:
    """
    La revalidacion corrio y su condicion NO se cumple (§3.7): la accion ya no
    aplica y no se va a ejecutar. 'codigo' dice cual condicion fallo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = 'vencida', revisado_en = now(), codigo_error = %s
               where organization_id = %s and id = %s
                 and estado in ('ejecutando', 'pendiente')""",
            (codigo[:200], org, accion_id))
        if not cur.rowcount:
            return False
        registrar_evento_de_accion(
            cur, org, accion_id, "accion_vencida", motivo=codigo[:500],
            actor_tipo="sistema", conversation_id=conversation_id)
        return True


def resolver_ejecucion_de_accion(tenant: str, accion_id: str, *,
                                 resultado: dict | None, codigo_error: str | None,
                                 incierto: bool = False,
                                 aprobada_por: str | None = None,
                                 conversation_id: str | None = None) -> bool:
    """
    Paso 4: el desenlace de la ejecucion, con su evento (I12).

        codigo_error None      -> ejecutada_ok
        incierto               -> desconocida       (unknown != failed)
        resto                  -> ejecutada_fallo

    'desconocida' es terminal y NO se reintenta sola (§9.3 paso 5): el pedido
    pudo haber llegado al sistema externo. Reintentar a ciegas un ticket que
    quiza ya existe manda dos visitas tecnicas al mismo cliente.

    La condicion 'estado = ejecutando' es lo que hace que una doble aprobacion
    no pueda escribir dos veces: la segunda no reservo, asi que nunca llega
    aca, y si llegara no encontraria fila.
    """
    if incierto:
        estado, tipo = "desconocida", "accion_desconocida"
    elif codigo_error:
        estado, tipo = "ejecutada_fallo", "accion_aprobada"
    else:
        estado, tipo = "ejecutada_ok", "accion_aprobada"

    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = %s, revisado_en = now(),
                   resultado_ejecucion = %s, codigo_error = %s
               where organization_id = %s and id = %s and estado = 'ejecutando'""",
            (estado, json.dumps(resultado, ensure_ascii=False) if resultado is not None else None,
             (codigo_error or None) and codigo_error[:200], org, accion_id))
        if not cur.rowcount:
            return False
        registrar_evento_de_accion(
            cur, org, accion_id, tipo,
            motivo=(codigo_error or None) and codigo_error[:500],
            actor_tipo="operador" if aprobada_por else "sistema",
            actor_nombre=aprobada_por, conversation_id=conversation_id,
            datos={"desenlace": estado})
        return True


def vincular_accion_a_conversacion(tenant: str, accion_id: str,
                                   conversation_id: str,
                                   vigencia_minutos: int | None = None) -> str:
    """
    Le pone conversacion, vigencia y clave de equivalencia a una accion recien
    propuesta.

    POR QUE EN DOS PASOS Y NO AL INSERTAR: durante el turno todavia NO existe
    el conversation_id -- la conversacion se crea o se reusa recien al
    persistir el turno, en api.py. Es el mismo problema que ya tenian
    'tool_calls' y los archivos generados, y se resuelve igual: el motor
    escribe lo que sabe, y api.py completa cuando el id existe.

    La ventana entre los dos pasos es segura y NO hay que taparla: mientras la
    accion no tiene conversacion se la trata como de legado, asi que NO SE
    PUEDE APROBAR (X24). Falla cerrado, que es el lado correcto -- y nadie
    puede aprobar en ese lapso porque el operador todavia no la vio.

    Devuelve 'vinculada', 'duplicada' (ya habia una equivalente viva: esta se
    cancela en vez de quedar como segunda propuesta del mismo pedido) o
    'no_encontrada'.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select herramienta, argumentos, estado
               from asistente.acciones_propuestas
               where organization_id = %s and id = %s""",
            (org, accion_id))
        fila = cur.fetchone()
        if fila is None:
            return "no_encontrada"

        clave = clave_de_equivalencia(conversation_id, fila["herramienta"],
                                      fila["argumentos"] or {})
        try:
            cur.execute(
                """update asistente.acciones_propuestas
                   set conversation_id = %s, clave_equivalencia = %s,
                       vence_en = case when %s::int is null then null
                                       else creado_en + make_interval(mins => %s::int) end
                   where organization_id = %s and id = %s
                     and conversation_id is null""",
                (conversation_id, clave, vigencia_minutos, vigencia_minutos,
                 org, accion_id))
        except psycopg.errors.UniqueViolation:
            # Ya hay una equivalente viva en esta conversacion: el cliente
            # pidio dos veces lo mismo. La segunda se cancela --con su motivo,
            # como cualquier cancelacion-- en vez de quedar viva sin
            # conversacion, que la volveria indistinguible del legado.
            cur.execute(
                """update asistente.acciones_propuestas
                   set estado = 'cancelada',
                       motivo_rechazo = 'duplicada: ya habia una propuesta '
                                        'equivalente viva en esta conversacion',
                       revisado_en = now()
                   where organization_id = %s and id = %s and estado = 'pendiente'""",
                (org, accion_id))
            if cur.rowcount:
                registrar_evento_de_accion(
                    cur, org, accion_id, "accion_propuesta_duplicada",
                    motivo="ya habia una propuesta equivalente viva",
                    actor_tipo="sistema", conversation_id=conversation_id)
            return "duplicada"
        return "vinculada" if cur.rowcount else "no_encontrada"


def barrer_acciones_ejecutando(tenant: str, minutos: int, limite: int = 50) -> list[dict]:
    """
    T20 (c): las `ejecutando` que quedaron colgadas pasan a `desconocida`.

    Se llega a este estado de una sola forma: el proceso murio entre la reserva
    (§9.3 paso 1) y el desenlace (paso 4). Y eso significa que el pedido PUDO
    haber salido -- la unica respuesta honesta es que no se sabe.

    POR QUE 'desconocida' Y NO 'pendiente': devolverla a la cola seria
    invitarla a ejecutarse otra vez, y nadie puede demostrar que la primera no
    llego. Un ticket duplicado son dos visitas tecnicas al mismo cliente, y eso
    no se deshace. X21 lo prohibe expresamente: el reconciliador nunca
    reejecuta una accion por su cuenta.

    El UPDATE es la transicion completa --seleccionar y escribir en un solo
    paso, condicionado a que siga 'ejecutando'-- asi que dos reconciliadores
    corriendo a la vez no pueden resolver la misma fila dos veces: el segundo
    no la encuentra.

    'minutos' NO se elige aca: viene de §14.1 Q4, que lo fijo como default de
    plataforma y no como configuracion por tenant.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = 'desconocida', revisado_en = now(),
                   codigo_error = 'ejecutando_huerfana'
               where id in (
                 select id from asistente.acciones_propuestas
                  where organization_id = %s and estado = 'ejecutando'
                    and revisado_en < now() - make_interval(mins => %s::int)
                  order by revisado_en
                  limit %s
                  for update skip locked)
               returning id, conversation_id""",
            (org, minutos, limite))
        barridas = [dict(f) for f in cur.fetchall()]
        for fila in barridas:
            registrar_evento_de_accion(
                cur, org, str(fila["id"]), "accion_desconocida",
                motivo=f"quedo 'ejecutando' mas de {minutos} min: el proceso murio "
                       f"entre la reserva y el desenlace, y no se sabe si el "
                       f"efecto llego a ocurrir",
                actor_tipo="sistema",
                conversation_id=str(fila["conversation_id"]) if fila["conversation_id"] else None)
        return barridas


def barrer_acciones_vencidas(tenant: str, limite: int = 50) -> list[dict]:
    """
    T20 (d): las `pendiente` que pasaron su plazo -> `vencida`, con evento.

    Es lo mismo que hace reservar_accion() al tropezarse con una, pero sin
    esperar a que alguien la toque: una propuesta vencida que sigue figurando
    como 'pendiente' invita a aprobarla, y quien lo intente recibe un 409 que
    parece una falla del sistema.

    NO alcanza a las de legado: no tienen vence_en, asi que el filtro las deja
    fuera solo. Es lo que §11.4 pide --nada de vencerlas para que
    desaparezcan-- y conviene que sea por construccion y no por una condicion
    aparte que alguien pueda borrar.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.acciones_propuestas
               set estado = 'vencida', revisado_en = now(),
                   codigo_error = coalesce(codigo_error, 'plazo_cumplido')
               where id in (
                 select id from asistente.acciones_propuestas
                  where organization_id = %s and estado = 'pendiente'
                    and vence_en is not null and vence_en <= now()
                  order by vence_en
                  limit %s
                  for update skip locked)
               returning id, conversation_id""",
            (org, limite))
        vencidas = [dict(f) for f in cur.fetchall()]
        for fila in vencidas:
            registrar_evento_de_accion(
                cur, org, str(fila["id"]), "accion_vencida",
                motivo="paso su plazo de vigencia sin que nadie la aprobara",
                actor_tipo="sistema",
                conversation_id=str(fila["conversation_id"]) if fila["conversation_id"] else None)
        return vencidas


def acciones_de_conversacion(tenant: str, conversation_id: str) -> list[dict]:
    """
    Las acciones de una conversacion, para la pantalla del hilo.

    SIN 'argumentos', igual que la lista general: son los valores reales sin
    enmascarar. El resumen existe para que quien aprueba lea "Crear ticket 'No
    tiene internet' para el servicio 1234" en vez del JSON crudo.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, herramienta, resumen, estado, motivo_rechazo,
                      revisado_por, codigo_error, creado_en, revisado_en,
                      vence_en,
                      (vence_en is not null and vence_en <= now()) as expirada
               from asistente.acciones_propuestas
               where organization_id = %s and conversation_id = %s
               order by creado_en desc""",
            (org, conversation_id))
        return [dict(f) for f in cur.fetchall()]


def eventos_de_accion(tenant: str, accion_id: str) -> list[dict]:
    """El expediente de una accion, en orden. Solo lectura y tenant-scoped."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select tipo, motivo, actor_tipo, actor_nombre, datos, creado_en
               from asistente.acciones_eventos
               where organization_id = %s and accion_id = %s
               order by creado_en asc, id asc""",
            (org, accion_id))
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


def guardar_resumen(tenant: str, conversation_id: str, resumen: str) -> None:
    """Deja el resumen en la conversacion y la marca cerrada, en un solo paso.

    Nunca rompe el turno si falla: perder un resumen es feo, no poder
    contestarle a un cliente es peor.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.conversations
                   set resumen = %s, estado = 'cerrada', actualizado_en = now()
                   where organization_id = %s and id = %s""",
                (resumen, org, conversation_id))
    except Exception as e:
        registrar("resumen", "no se pudo guardar", conversation_id=id_interno(conversation_id),
                  error=e)


def conversacion_vencida(tenant: str, canal: str, usuario_externo: str,
                         horas_inactividad: int | None):
    """
    La conversacion de este usuario que quedo ABIERTA pero ya paso el plazo de
    inactividad, con sus mensajes -- para resumirla y cerrarla.

    Devuelve None si no hay ninguna, o si el tenant no configuro el plazo.
    """
    if not horas_inactividad:
        return None
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, resumen from asistente.conversations
               where organization_id = %s and canal = %s and usuario_externo = %s
                 and estado = 'abierta'
                 and actualizado_en <= now() - (%s * interval '1 hour')
               order by actualizado_en desc limit 1""",
            (org, canal, usuario_externo, horas_inactividad))
        fila = cur.fetchone()
        if not fila:
            return None
        # El insumo del resumen pasa por la MISMA regla que el historial del
        # modelo (nucleo/relevo/historial.py). Antes eran todas las filas, y
        # todo lo que no era 'user' se volvia 'assistant': una nota interna
        # entraba al resumen como si el asistente se la hubiera dicho al
        # cliente, y ese resumen es contexto del modelo en la conversacion
        # siguiente (D12). Las notas se excluyen en el SQL y otra vez en la
        # regla.
        cur.execute(
            """select rol, contenido, origen, autor_nombre, estado_entrega from asistente.messages
               where organization_id = %s and conversation_id = %s
                 and rol = any(%s)
               order by creado_en""",
            (org, fila["id"], list(regla_historial.ROLES_DEL_MODELO)))
        mensajes = regla_historial.construir(cur.fetchall())
    return {"conversation_id": str(fila["id"]),
            "resumen_previo": fila["resumen"],
            "historial": mensajes}


def resumen_anterior(tenant: str, canal: str,
                     usuario_externo: str) -> tuple[str, float] | None:
    """
    El resumen de la ultima conversacion CERRADA de este usuario, Y CUANTAS
    HORAS HACE que se cerro.

    Las horas no son un adorno. Este resumen entra al contexto del turno
    nuevo (nucleo/canales/api.py), y sin fecha una conversacion de hace dos
    horas y una de hace un mes le llegan al modelo EXACTAMENTE IGUAL. Medido
    en produccion el 07/09/2026: ante un "Hola", el asistente contesto "veo
    que estuvimos hablando HACE UN MOMENTO sobre un problema de internet" --
    la conversacion era del 12/08, veintiseis dias antes. El resumen era
    correcto; lo unico falso era el cuando, que es lo unico que no se le
    habia dicho.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select resumen,
                          extract(epoch from (now() - actualizado_en)) / 3600
                            as horas
                     from asistente.conversations
                   where organization_id = %s and canal = %s and usuario_externo = %s
                     and estado = 'cerrada' and resumen is not null
                   order by actualizado_en desc limit 1""",
                (org, canal, usuario_externo))
            fila = cur.fetchone()
            return (fila["resumen"], float(fila["horas"] or 0)) if fila else None
    except Exception as e:
        registrar("resumen", "no se pudo leer el anterior", error=e)
        return None
