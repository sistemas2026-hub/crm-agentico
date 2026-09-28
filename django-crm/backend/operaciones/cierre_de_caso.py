# -*- coding: utf-8 -*-
"""
================================================================================
 CERRAR UN CASO PORQUE UNA PERSONA ACEPTO LA PROPUESTA  --  M09-S
================================================================================

EL CAMINO COMPLETO, Y DONDE ESTA CADA MITAD
-------------------------------------------
    detectar  ->  proponer  ->  REVISAR (una persona acepta)  ->  cerrar
                                        \\_ operaciones/supervisor.py::revisar
                                                     |
                                       este modulo valida y reclama
                                                     |
                                    motor: kill switch + humana + idempotencia
                                                     |
                                      PATCH /api/cases/<id>/  (vuelve a Django)

El trabajo esta partido en dos procesos y no es una eleccion de diseno: es lo
que los privilegios permiten. Medido contra produccion el 28/09/2026:

    crm_user (este proceso)  USAGE en el esquema 'asistente'  ->  NO
    app_backend (el motor)   privilegios sobre public."case"  ->  NINGUNO

O sea que el kill switch, la frontera y la idempotencia SOLO se consultan desde
el motor; y el caso SOLO se valida desde aca. Ninguna mitad puede saltarse la
otra porque ninguna alcanza lo del otro lado.

ACEPTAR NO ES CERRAR
--------------------
La decision humana se persiste PRIMERO y en su propia transaccion
('supervisor.revisar'). El cierre viene despues, fuera de ella. Si el cierre
falla, la propuesta sigue ACEPTADA y el caso sigue abierto: son dos hechos
distintos y el segundo puede no ocurrir. Meter la llamada de red dentro de la
transaccion de la revision tendria dos defectos a la vez -- la fila bloqueada
durante toda la llamada, y un rollback que borraria una decision que SI se tomo.

EL RECLAMO, Y POR QUE NO ES UN 'if'
-----------------------------------
Dos personas pueden aceptar propuestas distintas del mismo caso, o la misma
peticion puede llegar dos veces. El derecho a cerrar se gana con un UPDATE
condicional sobre la propuesta (de 'accion_propuesta_ref' vacia a 'en_curso'),
y se mira el rowcount: solo quien lo consigue llama al motor. Asi no hace falta
sostener ningun lock durante la llamada de red, y la idempotencia del motor
queda como segunda red -- no como la unica.
================================================================================
"""

from __future__ import annotations

import os

from django.db import transaction
from django.utils import timezone

from cases.models import Case
from common.models import Activity
from operaciones.models import PropuestaSupervisor
from operaciones.supervisor import (CERRADO_EN_PROVEEDOR, HORAS_LECTURA_FRESCA,
                                    CERRADO_EN_DEXTER)

#  Motivos por los que NO se cierra. Cada uno nombra la condicion que fallo: un
#  "no se pudo" sin causa obliga a adivinar, y lo que hay que saber es si el
#  caso cambio, si el dato esta viejo, o si el sistema esta detenido.
NO_ACEPTADA = "PROPUESTA_NO_ACEPTADA"
ORIGEN_NO_ES_CASO = "ORIGEN_NO_ES_UN_CASO"
CASO_NO_ENCONTRADO = "CASO_NO_ENCONTRADO"
OTRO_TENANT = "CASO_DE_OTRA_ORGANIZACION"
YA_CERRADO = "CASO_YA_CERRADO"
PROVEEDOR_NO_LO_CERRO = "EL_PROVEEDOR_NO_LO_REPORTA_CERRADO"
SIN_FECHA_DE_CIERRE = "SIN_FECHA_DE_CIERRE_DEL_PROVEEDOR"
LECTURA_VIEJA = "LECTURA_EXTERNA_FUERA_DE_FRESCURA"
LECTURA_CON_ERROR = "LA_ULTIMA_LECTURA_FALLO"
RESPUESTA_POSTERIOR = "HAY_RESPUESTA_POSTERIOR_AL_CIERRE"
TRABAJO_PENDIENTE = "HAY_TRABAJO_PENDIENTE_SOBRE_EL_CASO"
YA_EN_CURSO = "EL_CIERRE_YA_ESTA_EN_CURSO"
MOTOR_NO_RESPONDIO = "EL_MOTOR_NO_RESPONDIO"

#  Lo que el motor contesta cuando no cerro por el interruptor. Se reconoce para
#  poder decirselo distinto a la persona: "el sistema esta detenido" no es lo
#  mismo que "el caso cambio".
BLOQUEADO_POR_INTERRUPTOR = "BLOQUEADO_POR_INTERRUPTOR"

#  Marca del reclamo. No es un estado de la propuesta: es una referencia en
#  curso, y por eso vive en 'accion_propuesta_ref' y no en 'estado'. No se
#  inventan estados nuevos de PropuestaSupervisor.
EN_CURSO = "en_curso"

#  Estados de actividad que NO frenan un cierre. Todo lo demas si: una actividad
#  viva sobre el caso significa que alguien todavia esta trabajando en el.
ACTIVIDAD_TERMINAL = ("completada", "cancelada")


class NoSeCerro(Exception):
    """El cierre no ocurrio. Trae el motivo, que es lo que hay que registrar."""

    def __init__(self, motivo: str, detalle: str = ""):
        self.motivo = motivo
        self.detalle = detalle
        super().__init__(f"{motivo}: {detalle}" if detalle else motivo)


def _estado_externo(caso) -> str:
    return (getattr(caso, "external_status", "") or "").strip().lower()


def validar(propuesta: PropuestaSupervisor, caso: Case, *, ahora=None) -> None:
    """
    Las doce condiciones, todas sobre datos releidos. Levanta NoSeCerro.

    Se valida ACA y no en el motor porque este es el unico proceso que puede
    leer el caso. Y se valida JUSTO ANTES de cerrar y no al proponer: entre la
    propuesta y la aceptacion pueden pasar dias, y en ese rato el proveedor pudo
    reabrir el ticket o alguien pudo cerrar el caso a mano.
    """
    ahora = ahora or timezone.now()

    # 3. la propuesta esta aceptada
    if propuesta.estado != PropuestaSupervisor.ACEPTADA:
        raise NoSeCerro(NO_ACEPTADA, f"esta en '{propuesta.estado}'")

    # 4 y 5. el origen es ESTE caso
    if propuesta.origen_tipo != "case":
        raise NoSeCerro(ORIGEN_NO_ES_CASO, f"origen_tipo='{propuesta.origen_tipo}'")
    if str(propuesta.origen_id) != str(caso.id):
        raise NoSeCerro(CASO_NO_ENCONTRADO,
                        "la propuesta no apunta a este caso")

    # 2. misma organizacion. Dos capas, como en el resto del CRM: el filtro
    #    explicito ademas de la RLS.
    if propuesta.org_id != caso.org_id:
        raise NoSeCerro(OTRO_TENANT, "la propuesta y el caso son de empresas distintas")

    # 6 y 7. el caso sigue abierto
    if caso.status == CERRADO_EN_DEXTER:
        raise NoSeCerro(YA_CERRADO, "alguien lo cerro antes")
    if caso.resolved_at is not None:
        raise NoSeCerro(YA_CERRADO, f"ya tiene resolved_at ({caso.resolved_at:%Y-%m-%d})")

    # 8. el proveedor sigue diciendo que esta cerrado. Si reabrio el ticket,
    #    cerrar aca seria sincronizar al reves.
    if _estado_externo(caso) not in CERRADO_EN_PROVEEDOR:
        raise NoSeCerro(PROVEEDOR_NO_LO_CERRO,
                        f"el proveedor lo reporta como "
                        f"'{caso.external_status or '(vacio)'}'")

    # 9. se sabe cuando cerro alla
    if caso.external_status_at is None:
        raise NoSeCerro(SIN_FECHA_DE_CIERRE, "no consta cuando lo cerro el proveedor")

    # una lectura que fallo no sostiene nada, aunque haya traido un estado
    if (getattr(caso, "external_fetch_error", "") or "").strip():
        raise NoSeCerro(LECTURA_CON_ERROR, caso.external_fetch_error[:120])

    # 10. la lectura es fresca, con la MISMA regla que usa el detector
    if caso.external_fetched_at is None:
        raise NoSeCerro(LECTURA_VIEJA, "no consta cuando se leyo")
    horas = (ahora - caso.external_fetched_at).total_seconds() / 3600
    if horas > HORAS_LECTURA_FRESCA:
        raise NoSeCerro(
            LECTURA_VIEJA,
            f"la ultima lectura del proveedor tiene {horas:.0f} h y el limite "
            f"es {HORAS_LECTURA_FRESCA} h")

    # 11. el proveedor no se contradice consigo mismo
    posterior = caso.respuestas_externas.filter(
        creada_en_proveedor__gt=caso.external_status_at).exists()
    if posterior:
        raise NoSeCerro(
            RESPUESTA_POSTERIOR,
            "el proveedor registro una respuesta despues de la fecha en que "
            "dice haberlo cerrado")

    # 12. no hay trabajo vivo sobre el caso. Se usan las relaciones que YA
    #     existen ('origen_tipo'/'origen_id'); no se inventa ninguna.
    from campo.models import OrdenTrabajo
    from operaciones.models import ActividadOperativa

    actividades = (ActividadOperativa.objects
                   .filter(org_id=caso.org_id, origen_tipo="case",
                           origen_id=str(caso.id))
                   .exclude(estado_operativo__in=ACTIVIDAD_TERMINAL)
                   .count())
    if actividades:
        raise NoSeCerro(TRABAJO_PENDIENTE,
                        f"{actividades} actividad(es) sin terminar")

    ordenes = (OrdenTrabajo.objects
               .filter(org_id=caso.org_id, origen_tipo="case",
                       origen_ref=str(caso.id))
               .exclude(estado_operativo__in=("cerrada", "cancelada"))
               .count())
    if ordenes:
        raise NoSeCerro(TRABAJO_PENDIENTE,
                        f"{ordenes} orden(es) de trabajo sin cerrar")


def _reclamar(propuesta: PropuestaSupervisor) -> bool:
    """
    Gana el derecho a cerrar, o devuelve False.

    La condicion va en el UPDATE y no en un 'if': entre leer y escribir puede
    entrar otra peticion, y quien decide es la base. 'accion_propuesta_ref'
    vacia es "nadie lo intento todavia".
    """
    filas = (PropuestaSupervisor.objects
             .filter(pk=propuesta.pk, estado=PropuestaSupervisor.ACEPTADA,
                     accion_propuesta_ref="")
             .update(accion_propuesta_ref=EN_CURSO,
                     updated_at=timezone.now()))
    return filas == 1


def _pedirle_al_motor(propuesta_id: str, id_caso: str) -> dict:
    """
    Le pide al motor que ejecute el cierre. El motor pone el kill switch, la
    puerta humana y la idempotencia; este proceso no puede ninguna de las tres.
    """
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    r = requests.post(
        f"{base}/interno/propuesta/{propuesta_id}/cerrar-caso",
        params={"tenant": tenant}, json={"id_caso": str(id_caso)},
        headers=cabeceras, timeout=60)
    #  No se usa raise_for_status: el 409 es una respuesta con significado --
    #  "no se cerro, y este es el motivo" -- y perderlo obligaria a adivinar.
    try:
        cuerpo = r.json() or {}
    except ValueError:
        cuerpo = {}
    cuerpo.setdefault("codigo", f"HTTP_{r.status_code}")
    return cuerpo


def cerrar(propuesta: PropuestaSupervisor, *, actor=None, ahora=None) -> dict:
    """
    El camino entero, despues de que una persona acepto.

    Devuelve {cerrado, motivo, referencia}. NO levanta por un cierre que no
    ocurrio: que el caso no se cierre es un resultado posible y hay que poder
    contarlo. Si levanta, es por algo que nadie previo.
    """
    ahora = ahora or timezone.now()

    #  El caso se relee con la fila bloqueada, y se valida sobre ESA copia. El
    #  lock se suelta al cerrar la transaccion, ANTES de la llamada de red: lo
    #  que protege contra la doble ejecucion es el reclamo, no el lock.
    try:
        with transaction.atomic():
            caso = (Case.objects
                    .select_for_update()
                    .filter(id=propuesta.origen_id, org_id=propuesta.org_id)
                    .first())
            if caso is None:
                raise NoSeCerro(CASO_NO_ENCONTRADO,
                                "no existe, o es de otra organizacion")
            validar(propuesta, caso, ahora=ahora)

            if not _reclamar(propuesta):
                raise NoSeCerro(
                    YA_EN_CURSO,
                    "otra peticion ya tiene el cierre de esta propuesta")
    except NoSeCerro as no:
        _anotar(propuesta, caso=None, motivo=no.motivo, detalle=no.detalle,
                actor=actor)
        return {"cerrado": False, "motivo": no.motivo, "detalle": no.detalle,
                "referencia": ""}

    #  --- fuera de la transaccion: aca ocurre la llamada de red --------------
    try:
        respuesta = _pedirle_al_motor(str(propuesta.id), str(caso.id))
    except Exception as e:                                    # noqa: BLE001
        #  El motor no contesto. NO se sabe si el cierre salio o no: puede haber
        #  llegado y perderse la respuesta. Se suelta el reclamo para que se
        #  pueda reintentar, y la idempotencia del motor es lo que garantiza que
        #  un reintento no cierre dos veces.
        _soltar_reclamo(propuesta)
        _anotar(propuesta, caso=caso, motivo=MOTOR_NO_RESPONDIO,
                detalle=f"{type(e).__name__}: {e}", actor=actor)
        return {"cerrado": False, "motivo": MOTOR_NO_RESPONDIO,
                "detalle": f"{type(e).__name__}", "referencia": ""}

    referencia = str(respuesta.get("referencia") or "")
    if not respuesta.get("cerrado"):
        motivo = str(respuesta.get("codigo") or "") or "NO_EJECUTADA"
        #  Se suelta el reclamo: no se ejecuto nada, asi que reintentar es
        #  legitimo. La excepcion es el interruptor, donde reintentar en bucle
        #  no aporta -- pero tampoco hace dano, y dejar la propuesta trabada
        #  obligaria a tocarla a mano cuando se levante.
        _soltar_reclamo(propuesta)
        _anotar(propuesta, caso=caso, motivo=motivo,
                detalle=str(respuesta.get("motivo") or ""), actor=actor)
        return {"cerrado": False, "motivo": motivo,
                "detalle": str(respuesta.get("motivo") or ""),
                "referencia": referencia}

    #  Cerrado. Se guarda la referencia de la operacion --que es la clave
    #  idempotente, no un id inventado-- y se relee el caso para auditar lo que
    #  de verdad quedo, no lo que se pidio.
    PropuestaSupervisor.objects.filter(pk=propuesta.pk).update(
        accion_propuesta_ref=referencia[:128], updated_at=timezone.now())
    caso.refresh_from_db()

    Activity.objects.create(
        org_id=caso.org_id, user=actor, action="STATUS_CHANGED",
        entity_type="Case", entity_id=caso.id, entity_name=str(caso)[:255],
        description="Cerrado al aceptar una propuesta del Supervisor NOC IA",
        metadata={"propuesta": str(propuesta.id),
                  "estado_nuevo": caso.status,
                  "closed_on": caso.closed_on.isoformat() if caso.closed_on else "",
                  "referencia": referencia,
                  "external_status": caso.external_status or ""})

    return {"cerrado": True, "motivo": "", "detalle": "",
            "referencia": referencia, "estado": caso.status}


def _soltar_reclamo(propuesta: PropuestaSupervisor) -> None:
    """Devuelve la propuesta a 'nadie lo intento', solo si sigue en curso."""
    PropuestaSupervisor.objects.filter(
        pk=propuesta.pk, accion_propuesta_ref=EN_CURSO
    ).update(accion_propuesta_ref="", updated_at=timezone.now())


def _anotar(propuesta, *, caso, motivo: str, detalle: str, actor) -> None:
    """
    Deja el intento fallido en la bitacora del CRM.

    Va a common.Activity sobre la PROPUESTA y no sobre el caso: el caso no
    cambio, y anotarle un hecho a una fila que no se movio es como se llega a
    una bitacora en la que no se puede confiar. Asi queda legible el estado
    'aceptada, ejecucion fallida' sin inventar un estado nuevo.
    """
    Activity.objects.create(
        org_id=propuesta.org_id, user=actor, action="UPDATE",
        entity_type="PropuestaSupervisor", entity_id=propuesta.id,
        entity_name=str(propuesta.tipo_senal)[:255],
        description="El cierre autorizado no se ejecuto",
        metadata={"motivo": motivo, "detalle": detalle[:500],
                  "caso": str(caso.id) if caso is not None else "",
                  "resultado": "aceptada, ejecucion fallida"})
