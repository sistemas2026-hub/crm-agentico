# -*- coding: utf-8 -*-
"""
================================================================================
 AUTONOMIA DEL SUPERVISOR  --  hasta donde puede llegar, y quien lo decide
================================================================================

LOS CINCO NIVELES YA EXISTIAN. ESTE MODULO NO LOS REDEFINE
----------------------------------------------------------
'PropuestaSupervisor.NIVELES' los declara desde M09 y estan en uso:

    0  observar
    1  recomendar
    2  coordinar
    3  ejecutar acciones reversibles, idempotentes y auditadas
    4  accion critica -- siempre una persona

Lo que faltaba no era el vocabulario sino DOS cosas: que el nivel fuera un dato
POR EMPRESA en vez de la constante 'NIVEL_MAXIMO_ETAPA' del codigo, y que
cambiarlo dejara rastro de quien y por que.

DOS NIVELES, Y LA DIFERENCIA ES LO IMPORTANTE
---------------------------------------------
    nivel CONFIGURADO   lo que una persona decidio para esta empresa.
    nivel EFECTIVO      lo que de verdad se puede hacer AHORA.

No son lo mismo porque el interruptor de autonomia del motor puede estar detenido.
Si lo esta, el nivel efectivo es 0 aunque el configurado sea 3: una empresa con el
interruptor apagado no ejecuta nada, y presentar el configurado como efectivo
haria que un tablero prometiera un alcance que no existe.

FAIL-CLOSED, Y HASTA DONDE EXACTAMENTE
--------------------------------------
  * sin fila de nivel     -> 0. Desplegar no concede alcance.
  * interruptor detenido  -> se recorta a RECOMENDAR (1), no a 0.
  * interruptor ILEGIBLE  -> lo mismo, y se dice por que. No poder leer el
                             control es tratado igual que no tenerlo: es el
                             criterio que el proyecto ya pago, porque la ruta de
                             configuracion falla ABIERTA por dos caminos medidos
                             y por eso este interruptor vive aparte y se lee sin
                             cache.

POR QUE A 1 Y NO A 0, que es la decision mas discutible de este modulo: el
interruptor gobierna la EJECUCION del motor contra sistemas externos. Observar y
recomendar no ejecutan nada. Bajar a 0 cuando el interruptor esta apagado dejaria
a la empresa sin diagnostico justo cuando algo anda mal -- se perderia la deteccion
por una barrera que existe para frenar ESCRITURAS. Lo que si se recorta, siempre,
es todo nivel que implique actuar (2 en adelante).

EL SUPERVISOR NO SE PUEDE SUBIR EL NIVEL
----------------------------------------
'cambiar()' exige un actor y lo valida, y la base vuelve a exigirlo con una
restriccion. Dos barreras para la misma cosa a proposito: la de codigo da un
mensaje util, la de la base sobrevive a un camino nuevo que se olvide de la
primera.

LO QUE ESTE MODULO NO HACE
--------------------------
No ejecuta nada y no habilita nada. Contesta "¿hasta donde?" y registra quien lo
decidio. Que una accion salga sigue dependiendo de la frontera del motor, su
techo, su idempotencia y su auditoria -- ocho pasos que no se tocan desde aqui.
================================================================================
"""

from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from operaciones.gobierno_modelos import NivelAutonomia
from operaciones.models import PropuestaSupervisor

P = PropuestaSupervisor

#  El estado del interruptor del motor que permite ejecutar. Es el valor que usa
#  'nucleo/seguridad/interruptor.py'; se nombra aqui porque esta tabla vive en
#  otro schema y no hay un modelo de Django que la represente.
INTERRUPTOR_ACTIVO = "activo"

#  Donde vive el interruptor. Es del motor, no de Django: se lee con SQL crudo
#  porque crear un modelo de Django sobre una tabla que mantiene otro sistema
#  seria una segunda definicion que se desincroniza.
TABLA_INTERRUPTOR = "asistente.interruptor_autonomia"


class ErrorAutonomia(Exception):
    """No se puede hacer ese cambio de nivel."""


# =============================================================================
#  LEER
# =============================================================================

def nivel_configurado(org) -> int:
    """
    El nivel que una persona decidio para esta empresa. 0 si nadie decidio.

    Se lee de la fila MAS RECIENTE del historial. Sin filas es 0 -- fail-closed:
    el alcance se concede, no se hereda.
    """
    fila = (NivelAutonomia.objects.filter(org=org)
            .order_by("-cambiado_en", "-created_at").first())
    return int(fila.nivel) if fila is not None else P.NIVEL_OBSERVAR


def _interruptor_de(org) -> tuple[bool, str]:
    """
    Si el interruptor del motor permite actuar. Devuelve (permite, motivo).

    SE LEE SIN CACHE Y FALLA CERRADO. Las dos cosas son la leccion que el
    proyecto ya pago: la ruta de configuracion falla ABIERTA por dos caminos
    medidos, y por eso este control vive en su propia tabla y se consulta en el
    momento. Si no se puede leer, no se asume que permite.
    """
    #  EL 'atomic' ES UN SAVEPOINT, Y NO ES OPCIONAL (medido el 02/10/2026)
    #  --------------------------------------------------------------------
    #  Esta tabla vive en el schema del MOTOR, que Django no construye: puede no
    #  existir. Y en PostgreSQL, una consulta que falla dentro de una transaccion
    #  la deja ABORTADA -- todo lo que venga despues revienta con
    #  'InFailedSqlTransaction', aunque no tenga nada que ver.
    #
    #  La primera version de esta funcion atrapaba la excepcion y devolvia
    #  "no se pudo leer", creyendo que con eso alcanzaba. No alcanzaba: cinco
    #  pruebas se cayeron DESPUES de llamar aqui, por una transaccion envenenada.
    #  En produccion eso habria tumbado la peticion entera -- un control que no
    #  se puede leer tiene que degradar, no arrastrar.
    #
    #  'transaction.atomic()' abre un savepoint: si la consulta falla, se vuelve
    #  solo hasta ahi y la transaccion de afuera sigue sirviendo.
    #  SE LE PREGUNTA AL MOTOR, QUE ES EL DUEÑO DE ESA TABLA (08/10/2026)
    #  -------------------------------------------------------------------
    #  La lectura directa no funcionaba y no era un bug: 'crm_user' no tiene
    #  acceso al schema del motor. Medido en produccion -- la tabla EXISTE
    #  ('pg_tables' la ve) y el schema no es visible para ese usuario
    #  ('information_schema.schemata' devuelve 0). Resultado: ProgrammingError
    #  siempre, interruptor permanentemente ilegible, y nivel efectivo 0 para
    #  cualquier empresa pasara lo que pasara. El fail-closed tapaba el
    #  problema en vez de mostrarlo: todo "funcionaba", nada se ejecutaba.
    #
    #  No se arregla con un GRANT. La separacion de identidades de base se
    #  tomo despues del incidente del 18/08/2026, y la frontera ya tiene su
    #  forma de cruzarse: por HTTP. 'fuentes_adaptadores' documenta el sentido
    #  contrario con las mismas palabras -- el motor no lee ninguna tabla del
    #  CRM, y cuando necesita una la pide.
    #  Import local: 'fuentes_adaptadores' importa modelos, y a nivel de modulo
    #  esto seria un ciclo.
    from operaciones import fuentes_adaptadores

    try:
        estado_motor = fuentes_adaptadores.estado_de_autonomia()
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de un error de red trae la URL.
        return False, (f"no se pudo leer el interruptor de autonomia "
                       f"({type(e).__name__}): no poder leer el control es lo "
                       f"mismo que no tenerlo")
    if estado_motor["permitido"]:
        return True, ""
    return False, (estado_motor["motivo"]
                   or f"el interruptor de autonomia esta en "
                      f"'{estado_motor['estado'] or 'desconocido'}'")


def mover_interruptor(org, *, detener: bool, actor, motivo: str) -> dict:
    """
    Tira o levanta el freno de mano. Devuelve {estado}.

    NO TOCA EL NIVEL, y no mezclarlos es el punto: el nivel dice QUE CLASE de
    cosas puede hacer el Supervisor, y el interruptor dice si puede hacer
    alguna. Si reactivar subiera el nivel, devolveria en silencio un alcance
    que alguien habia decidido recortar.

    EXIGE MOTIVO PERO NO CRITERIOS, al reves que 'cambiar'. La asimetria es
    deliberada: ampliar el alcance tiene que demostrar que se midio algo; PARAR
    no tiene que demostrar nada, porque quien ve humo no deberia tener que
    redactar un informe antes de apagar el fuego.

    El actor viaja como ID y nunca como nombre: esto termina en el log del
    motor.
    """
    from operaciones import fuentes_adaptadores

    if actor is None:
        raise ErrorAutonomia(
            "mover el interruptor necesita la persona que lo decide")
    if not (motivo or "").strip():
        raise ErrorAutonomia(
            "mover el interruptor necesita su motivo: un freno sin explicacion "
            "no se puede discutir despues")
    try:
        return fuentes_adaptadores.mover_interruptor_de_autonomia(
            detener=detener, actor=str(actor.id), motivo=motivo.strip())
    except Exception as e:                                       # noqa: BLE001
        raise ErrorAutonomia(str(e)) from None


def _interruptor_por_sql(org) -> tuple[bool, str]:
    """
    La lectura directa de la tabla. YA NO SE USA desde '_interruptor_de'.

    Se conserva porque sigue siendo valida el dia que el CRM y el motor
    compartan identidad de base, y porque su comentario sobre el savepoint es
    una cicatriz que no conviene perder.
    """
    #  EL 'atomic' ES UN SAVEPOINT, Y NO ES OPCIONAL (medido el 02/10/2026)
    #  --------------------------------------------------------------------
    #  Esta tabla vive en el schema del MOTOR, que Django no construye: puede no
    #  existir. Y en PostgreSQL, una consulta que falla dentro de una transaccion
    #  la deja ABORTADA -- todo lo que venga despues revienta con
    #  'InFailedSqlTransaction', aunque no tenga nada que ver.
    #
    #  La primera version de esta funcion atrapaba la excepcion y devolvia
    #  "no se pudo leer", creyendo que con eso alcanzaba. No alcanzaba: cinco
    #  pruebas se cayeron DESPUES de llamar aqui, por una transaccion envenenada.
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    f"select estado from {TABLA_INTERRUPTOR} "
                    f"where organization_id = %s "
                    f"order by creado_en desc limit 1", [str(org.id)])
                fila = cur.fetchone()
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de un error de base trae el SQL, y el SQL de
        #  esta consulta lleva el id de la organizacion.
        return False, (f"no se pudo leer el interruptor de autonomia "
                       f"({type(e).__name__}): no poder leer el control es lo "
                       f"mismo que no tenerlo")
    if fila is None:
        return False, ("esta empresa no tiene fila en el interruptor de "
                       "autonomia: sin registro, no se actua")
    estado = str(fila[0] or "")
    if estado != INTERRUPTOR_ACTIVO:
        return False, f"el interruptor de autonomia esta en '{estado}'"
    return True, ""


def nivel_efectivo(org) -> dict:
    """
    Hasta donde se puede llegar AHORA, con el porque.

    Devuelve el configurado, el efectivo y el motivo del recorte si hubo. Los tres
    juntos: un tablero que muestre solo el efectivo no deja ver que alguien
    configuro 3 y algo lo esta bajando a 0, que es justo lo que hay que mirar.
    """
    configurado = nivel_configurado(org)
    permite, motivo = _interruptor_de(org)

    #  El interruptor gobierna la EJECUCION. Observar y recomendar no son
    #  ejecutar, asi que no se recortan: un Supervisor con el interruptor apagado
    #  sigue pudiendo mirar y sugerir -- lo que no puede es actuar. Confundir las
    #  dos cosas dejaria a la empresa sin diagnostico justo cuando mas lo
    #  necesita.
    if permite or configurado <= P.NIVEL_RECOMENDAR:
        return {"configurado": configurado,
                "efectivo": configurado,
                "recortado": False,
                "motivo": "" if permite else
                          (motivo + " -- no recorta observar/recomendar, que no "
                                    "son ejecutar"),
                "interruptor_permite": permite}

    return {"configurado": configurado,
            "efectivo": P.NIVEL_RECOMENDAR,
            "recortado": True,
            "motivo": motivo,
            "interruptor_permite": permite}


def puede(org, nivel_requerido: int) -> dict:
    """
    Si una accion que exige ese nivel esta dentro del alcance vigente.

    Devuelve el veredicto con su motivo, no un booleano suelto: quien llama tiene
    que poder decir POR QUE no, y "falso" no explica nada.
    """
    estado = nivel_efectivo(org)
    #  El nivel 4 nunca alcanza por configuracion: es "siempre una persona". Se
    #  comprueba aparte para que subir el nivel a 4 no se lea como habilitarlo.
    if int(nivel_requerido) >= P.NIVEL_CRITICO:
        return {"puede": False, "efectivo": estado["efectivo"],
                "motivo": "el nivel 4 es accion critica: siempre la aprueba una "
                          "persona, sin importar el nivel configurado"}
    if int(nivel_requerido) > estado["efectivo"]:
        return {"puede": False, "efectivo": estado["efectivo"],
                "motivo": (f"requiere nivel {nivel_requerido} y el efectivo es "
                           f"{estado['efectivo']}"
                           + (f": {estado['motivo']}" if estado["motivo"] else ""))}
    return {"puede": True, "efectivo": estado["efectivo"], "motivo": ""}


# =============================================================================
#  CAMBIAR
# =============================================================================

def cambiar(org, nivel: int, *, actor, motivo: str, criterios: str,
            ahora=None) -> NivelAutonomia:
    """
    Cambia el nivel. Exige persona, motivo y criterios.

    POR QUE LOS TRES SON OBLIGATORIOS
    ---------------------------------
    Subir el alcance de un sistema que va a actuar sobre la red de clientes es la
    decision mas consecuente que se puede tomar sobre el Supervisor. Sin actor no
    se sabe quien respondio por ella; sin motivo no se puede discutir despues; sin
    criterios no se sabe QUE se midio para decidirlo -- y este proyecto ya tiene
    escrito que una decision sin medicion se reabre sola cada sesion.

    EL SUPERVISOR NO PUEDE LLAMAR A ESTO SIN ACTOR, y por eso el actor no tiene
    default. La base lo vuelve a exigir con una restriccion.
    """
    ahora = ahora or timezone.now()
    nivel = int(nivel)

    if actor is None:
        raise ErrorAutonomia(
            "un cambio de nivel de autonomia necesita la persona que lo decide: "
            "el Supervisor no puede ampliarse su propio alcance")
    if nivel < P.NIVEL_OBSERVAR or nivel > P.NIVEL_CRITICO:
        raise ErrorAutonomia(
            f"nivel {nivel} fuera de rango: los niveles son "
            f"{P.NIVEL_OBSERVAR} a {P.NIVEL_CRITICO}")
    if not (motivo or "").strip():
        raise ErrorAutonomia("un cambio de nivel necesita su motivo")
    if not (criterios or "").strip():
        raise ErrorAutonomia(
            "un cambio de nivel necesita los criterios con los que se decidio: "
            "sin que se midio, no se puede revisar despues")
    if getattr(actor, "org_id", None) != getattr(org, "id", None):
        #  Una persona de otra empresa no gobierna esta. Se comprueba aqui porque
        #  la base no puede: 'actor' y 'org' son dos claves ajenas sueltas.
        raise ErrorAutonomia(
            "la persona que cambia el nivel tiene que pertenecer a esa empresa")

    anterior = nivel_configurado(org)
    return NivelAutonomia.objects.create(
        org=org, nivel=nivel, nivel_anterior=anterior, actor=actor,
        cambiado_en=ahora, motivo=motivo.strip(), criterios=criterios.strip())


def historial(org, limite: int = 50) -> list[dict]:
    """El historial de cambios, lo mas reciente primero. Sin datos de cliente."""
    filas = (NivelAutonomia.objects.filter(org=org)
             .select_related("actor")
             .order_by("-cambiado_en")[:max(1, min(int(limite), 200))])
    return [{
        "nivel": f.nivel,
        "nivel_anterior": f.nivel_anterior,
        "cambiado_en": f.cambiado_en.isoformat(),
        #  El id del perfil, NO su nombre: esto puede terminar en un log.
        "actor_id": str(f.actor_id) if f.actor_id else None,
        "motivo": f.motivo,
        "criterios": f.criterios,
    } for f in filas]
