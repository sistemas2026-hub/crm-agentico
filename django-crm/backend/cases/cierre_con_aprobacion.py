"""
Un cierre que una regla frena deja una solicitud, y aprobarla lo completa.

POR QUE EXISTE  --  12/11/2026
------------------------------
Las reglas `pre_close` se quedan: el dueño lo decidio ese dia, estan activas
en produccion y el equipo las usa. Lo que no podia seguir es lo que pasaba
cuando una frenaba un cierre:

  * El motor (Dexter) cierra el caso con un PATCH {status: Closed}. El CRM
    respondia 400 con un texto en ingles y NO dejaba ningun rastro: ni una
    solicitud en Tickets -> Aprobaciones, ni una actividad en el caso. Del
    lado del motor, `nucleo/relevo/efectos_externos.py::cerrar_caso` lo
    dejaba en 'permanente', "esperando a alguien" -- y ese alguien no tenia
    donde enterarse. La bandeja de aprobaciones solo se llenaba si una
    persona apretaba un boton que ninguna pantalla monta.
  * Y si alguien SI pedia la aprobacion a mano y otra persona la aprobaba,
    el caso seguia abierto: habia que volver a cerrarlo. Para el motor eso
    nunca pasaba, porque ya habia dejado de intentarlo.

Lo que hace ahora, en el mismo lugar para cualquiera que cierre (el motor
con su token o una persona desde la pantalla):

  1. El intento frenado CREA la solicitud (o reusa la que ya esta pendiente
     para ese caso y esa regla: un reintento no la duplica), con quien la
     pidio, por que, y la fecha de cierre que se pidio.
  2. Aprobarla CIERRA el caso en la misma transaccion, con esa fecha. Si el
     caso ya estaba cerrado no se toca: un cierre aprobado dos veces no
     reescribe 'closed_on' (medido en test_cierre_idempotente.py: un cierre a
     ciegas corre la fecha y con ella toda metrica de resolucion).
  3. Rechazarla deja el caso abierto. Lo que el motor hace con eso vive en
     efectos_externos.py: lee el caso, ve la solicitud rechazada y cierra su
     accion como rechazada, en vez de quedarse esperando para siempre.

POR QUE ACA Y NO EN EL MOTOR NI EN UNA SEÑAL
--------------------------------------------
Es lo mas simple que ya existe: la vista de aprobar ya toma el candado de la
fila y ya registra la actividad; agregarle el cierre en la misma transaccion
hace que "aprobado" y "cerrado" no puedan quedar desparejos. Una señal
post_save haria lo mismo desde cualquier escritura del modelo (incluida una
migracion de datos), que es mas de lo pedido; y que lo hiciera el reconciliador
del motor dejaria el cierre de un caso que pidio una PERSONA esperando a un
proceso que en produccion puede estar apagado (RECONCILIADOR_HABILITADO).

La validacion del serializer (`CaseCreateSerializer.validate`) sigue en su
lugar como segunda capa: si por algun camino llega un cierre sin pasar por
aca, sigue frenado.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

#: El codigo que viaja en el cuerpo del 400. Lo lee una maquina (el motor no:
#: el motor LEE EL CASO despues, que es la evidencia; ver efectos_externos.py),
#: pero deja escrito que este 400 no es "el pedido estaba mal".
CODIGO_CIERRE_REQUIERE_APROBACION = "cierre_requiere_aprobacion"

#: Quien pidio el cierre. 'agente' = un token de acceso personal (asi entra
#: Dexter al CRM), 'persona' = una sesion de la pantalla.
ORIGEN_AGENTE = "agente"
ORIGEN_PERSONA = "persona"

#: Como se muestra en la bandeja una solicitud que pidio el asistente. Es el
#: nombre del producto, no el de una empresa.
NOMBRE_DEL_ASISTENTE = "Dexter"


def mensaje_cierre_requiere_aprobacion(regla_nombre: str, *, pedida: bool) -> str:
    """El texto que ve quien intento cerrar. En español (antes llegaba en ingles)."""
    base = (
        f"Este caso necesita una aprobación antes de cerrarse "
        f"(regla «{regla_nombre}»)."
    )
    if pedida:
        return base + (
            " Ya quedó pedida: la ve quien aprueba en Tickets → Aprobaciones, "
            "y al aprobarla el caso se cierra solo."
        )
    return base


def origen_del_pedido(request) -> str:
    """'agente' si entro con un token de acceso personal, 'persona' si no.

    Se mira la credencial, nunca algo que mande el cliente: un cuerpo que
    dijera "soy Dexter" lo podria escribir cualquiera.
    """
    from common.models import PersonalAccessToken

    if getattr(request, "_pat", None) is not None:
        return ORIGEN_AGENTE
    if isinstance(getattr(request, "auth", None), PersonalAccessToken):
        return ORIGEN_AGENTE
    return ORIGEN_PERSONA


def solicitante_visible(approval) -> str | None:
    """'Dexter' si la pidio el asistente; None para que la pantalla use el correo."""
    if getattr(approval, "origen", "") == ORIGEN_AGENTE:
        return NOMBRE_DEL_ASISTENTE
    return None


def regla_que_frena(case, datos) -> object | None:
    """La regla que frena ESTE cierre, o None si el cierre puede seguir.

    Mismas condiciones que `CaseCreateSerializer.validate`, para que las dos
    capas no puedan decir cosas distintas:

      * solo la TRANSICION a Cerrado (un caso ya cerrado se edita sin volver
        a aprobar);
      * la regla se evalua con la prioridad y el tipo que trae ESTE pedido,
        para que nadie lo saque de la regla y lo cierre en el mismo PATCH;
      * pasa si hay una aprobacion 'approved' de esa regla para el caso.
    """
    from cases.approvals import Approval, find_matching_rule

    datos = datos or {}
    nuevo = datos.get("status", case.status)
    if nuevo != "Closed" or case.status == "Closed":
        return None

    guardado = (case.priority, case.case_type)
    case.priority = datos.get("priority", case.priority)
    case.case_type = datos.get("case_type", case.case_type)
    try:
        regla = find_matching_rule(case, trigger_event="pre_close")
    finally:
        case.priority, case.case_type = guardado
    if regla is None:
        return None
    if Approval.objects.filter(case_id=case.pk, rule=regla, state="approved").exists():
        return None
    return regla


def pedir_aprobacion(case, regla, perfil, *, fecha_cierre, origen: str):
    """Crea la solicitud de este cierre, o devuelve la que ya estaba pendiente.

    IDEMPOTENTE POR (caso, regla, pendiente). El motor reintenta, y una
    persona puede apretar Cerrar dos veces: ninguno de los dos puede dejar dos
    filas esperando la misma decision. El candado de fila evita la carrera de
    dos pedidos simultaneos que vean "no hay ninguna" al mismo tiempo.

    Devuelve (approval, creada).
    """
    from cases.approval_views import _record
    from cases.approvals import Approval

    with transaction.atomic():
        existente = (
            Approval.objects.select_for_update()
            .filter(case=case, rule=regla, state="pending")
            .order_by("-created_at")
            .first()
        )
        if existente is not None:
            cambios = []
            # Una solicitud pedida a mano y despues frenada por un intento de
            # cierre pasa a completarse sola: alguien ya intento cerrar.
            if not existente.cerrar_al_aprobar:
                existente.cerrar_al_aprobar = True
                cambios.append("cerrar_al_aprobar")
            if existente.fecha_cierre_pedida is None and fecha_cierre:
                existente.fecha_cierre_pedida = fecha_cierre
                cambios.append("fecha_cierre_pedida")
            if cambios:
                existente.save(update_fields=[*cambios, "updated_at"])
            return existente, False

        quien = NOMBRE_DEL_ASISTENTE if origen == ORIGEN_AGENTE else "Una persona"
        nota = (
            f"{quien} intentó cerrar este caso y la regla «{regla.name}» pide "
            "una aprobación antes. Al aprobarla el caso se cierra solo."
        )
        approval = Approval.objects.create(
            org_id=case.org_id,
            case=case,
            rule=regla,
            requested_by=perfil,
            note=nota,
            origen=origen,
            cerrar_al_aprobar=True,
            fecha_cierre_pedida=fecha_cierre,
        )
        _record(
            case,
            "APPROVAL_REQUESTED",
            {
                "approval_id": str(approval.id),
                "rule_id": str(regla.id),
                "rule_name": regla.name,
                "origen": origen,
                "motivo": "cierre_frenado",
            },
            actor=perfil,
        )
        return approval, True


def frenar_si_hace_falta(request, case, datos):
    """Para las vistas que cierran: un Response 400 si una regla frena el cierre.

    None = puede seguir. Si la fecha de cierre falta o no se entiende, no se
    pide nada: el serializer va a rechazar el pedido por esa razon, y una
    solicitud nacida de un pedido invalido seria una solicitud de nada.
    """
    regla = regla_que_frena(case, datos)
    if regla is None:
        return None
    crudo = (datos or {}).get("closed_on") or case.closed_on
    fecha = crudo if hasattr(crudo, "year") else parse_date(str(crudo or ""))
    if fecha is None:
        return None

    approval, _ = pedir_aprobacion(
        case,
        regla,
        request.profile,
        fecha_cierre=fecha,
        origen=origen_del_pedido(request),
    )
    return Response(
        {
            "error": True,
            "errors": {
                "status": [mensaje_cierre_requiere_aprobacion(regla.name, pedida=True)]
            },
            "codigo": CODIGO_CIERRE_REQUIERE_APROBACION,
            "approval_id": str(approval.id),
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def completar_cierre(approval) -> bool:
    """Cierra el caso de una solicitud recien aprobada. True si lo cerro.

    Va DENTRO de la transaccion de la aprobacion (la vista ya tiene la fila
    bloqueada): aprobado y cerrado no pueden quedar desparejos.

    NO REESCRIBE UN CIERRE. Si el caso ya esta cerrado --alguien lo cerro por
    otro camino, o se aprobo dos veces por alguna via-- no se toca nada, ni
    siquiera 'closed_on'. Es la misma regla que efectos_externos.cerrar_caso:
    leer primero y escribir solo si sigue abierto.
    """
    from cases.models import Case

    if not approval.cerrar_al_aprobar:
        return False
    case = Case.objects.select_for_update().get(pk=approval.case_id)
    if case.status == "Closed":
        return False
    case.status = "Closed"
    case.closed_on = approval.fecha_cierre_pedida or timezone.localdate()
    # La regla ya quedo satisfecha por esta misma aprobacion; el salto evita
    # que Case.clean() la vuelva a evaluar si algun camino llama full_clean().
    case._approval_gate_skip = True
    case.save()
    return True


def aprobacion_de_cierre(case) -> dict | None:
    """La ultima solicitud `pre_close` del caso: id y estado, nada mas.

    Es lo que el motor necesita para no quedarse esperando para siempre: con
    'pending' espera, con 'rejected' cierra su accion como rechazada, con
    'approved' el caso ya deberia estar cerrado. Sin nota ni motivo: son texto
    libre de personas y no le hacen falta para decidir.
    """
    from cases.approvals import Approval

    a = (
        Approval.objects.filter(case_id=case.pk, rule__trigger_event="pre_close")
        .order_by("-created_at")
        .only("id", "state", "cerrar_al_aprobar", "created_at")
        .first()
    )
    if a is None:
        return None
    return {"id": str(a.id), "estado": a.state, "cerrar_al_aprobar": a.cerrar_al_aprobar}
