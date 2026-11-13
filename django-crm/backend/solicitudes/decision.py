"""Decidir una solicitud, y todo lo que esa decision tiene que mover afuera.

POR QUE EXISTE (12/11/2026)
---------------------------
La auditoria del menu (§2 «Instalaciones», §4 item 4) encontro tres cosas:

  * RECHAZAR NO CERRABA NADA. 'SIN_FACTIBILIDAD' quedaba anotado aca, el
    ticket de WispHub seguia abierto (alguien podia salir a instalar) y al
    prospecto nadie le decia el motivo, que la nota estaba escrita para el.
  * «SE PUEDE REINTENTAR» ERA FALSO. DecidirView respondia 409 a todo lo que no
    estuviera ENVIADA, asi que una aprobada con la reasignacion fallida quedaba
    huerfana.
  * EL LEAD NO SEGUIA A SU SOLICITUD: el prospecto quedaba 'assigned' para
    siempre, aprobado, rechazado o cancelado.

Este modulo es el unico lugar donde una solicitud cambia de decision, y el
unico que sabe que quedo pendiente con un tercero.

LAS REGLAS DE SIEMPRE DEL MODULO, QUE NO CAMBIAN
-----------------------------------------------
  * Lo que decidio una persona no se deshace porque un tercero no responda: se
    guarda primero, los efectos van despues, y lo que falla queda anotado.
  * Ninguna transaccion abierta mientras se espera al motor.
  * Lo pendiente se CALCULA de los sellos (ticket_reasignado_en,
    ticket_cerrado_en, aviso_cliente_estado), no del texto del fallo.

IDEMPOTENCIA, Y LO QUE NO PUEDE PROMETER
---------------------------------------
  * La decision se toma con un UPDATE condicionado a 'enviada': dos clics (o
    dos personas) a la vez deciden UNA vez; el segundo recibe 409.
  * Los efectos sobre el ticket llevan 'Idempotency-Key' al motor con el
    numero de intento: el mismo intento reenviado no sale dos veces; uno nuevo
    despues de un fallo medido si sale. Si la respuesta se perdio en el camino,
    nadie sabe si WispHub lo aplico -- mismo limite que nucleo/seguridad/
    idempotencia.py, y cerrar o mover dos veces un ticket no daña a nadie.
  * El aviso al cliente lleva una clave FIJA por solicitud: el motor lo
    reserva una sola vez (mensajes_automaticos.enviar -> 'ya_enviado'). Ningun
    reintento de aca puede mandarle dos avisos por un rechazo.
"""

from __future__ import annotations

import logging
import os

from django.utils import timezone

from solicitudes.models import SolicitudServicio

logger = logging.getLogger(__name__)

#: El autor de lo que decide Dexter solo. Es lo que se lee en la bandeja.
AUTOR_DEXTER = "Dexter (pre-factibilidad)"

#: El momento del catalogo de mensajes del motor (nucleo/config/
#: mensajes_catalogo.py). La plantilla la elige cada empresa.
EVENTO_RECHAZO = "solicitud_sin_factibilidad"
ETIQUETA_EVENTO = "Solicitud sin factibilidad"

#: Lo que el motor contesta cuando el aviso no sale, dicho para una persona.
#: El backend traduce; la pantalla solo representa (CLAUDE.md §12).
POR_QUE_NO_SALIO = {
    "apagado": (f"falta la plantilla del aviso «{ETIQUETA_EVENTO}»: se elige y se "
                "enciende en Ajustes → WhatsApp → Mensajes automáticos"),
    "plantilla_desactivada": f"la plantilla del aviso «{ETIQUETA_EVENTO}» está desactivada",
    "plantilla_no_aprobada": f"la plantilla del aviso «{ETIQUETA_EVENTO}» no está aprobada por Meta",
    "plantilla_no_coincide": (f"la plantilla del aviso «{ETIQUETA_EVENTO}» no pide los "
                              "mismos datos que se le configuraron"),
    "canal_apagado": "el canal de WhatsApp de la empresa está apagado",
    "sin_indicativo": "falta el indicativo del país de la empresa",
    "sin_movil": "la solicitud no tiene un número de celular válido",
    "sin_numero": "la solicitud no tiene un número de celular válido",
    "de_baja": "el cliente pidió no recibir avisos",
    "fuera_de_prueba": "el aviso está en modo prueba y este número no está en la lista",
    "meta_no_contesta": "Meta no contestó; se puede reintentar",
    "rechazado": "Meta rechazó el mensaje",
    "incierto": "no se pudo confirmar si el mensaje salió",
    "motor_no_contesta": "el asistente no contestó; se puede reintentar",
    "sin_empresa": "la organización no tiene empresa en el asistente",
}


# --- el motor --------------------------------------------------------------------

def _base() -> str:
    return (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")


def _cabeceras(clave_idem: str | None = None) -> dict:
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    if clave_idem:
        cabeceras["Idempotency-Key"] = clave_idem
    return cabeceras


def _clave(s, accion: str) -> str:
    return f"solicitud:{s.id}:{accion}:{s.intentos_integracion}"


def _falla(e: Exception) -> str:
    """El fallo dicho sin datos de nadie: tipo, codigo HTTP y el codigo fijo
    que devuelve el motor. Nunca str(e) entero (puede traer la URL o el
    cuerpo)."""
    respuesta = getattr(e, "response", None)
    if respuesta is None:
        return type(e).__name__
    codigo = ""
    try:
        codigo = str((respuesta.json() or {}).get("error") or "")[:40]
    except Exception:                                   # noqa: BLE001
        pass
    return f"HTTP {respuesta.status_code}" + (f" {codigo}" if codigo else "")


def _anotar_fallo(s, que: str) -> None:
    previo = (s.fallo_integracion + " | ") if s.fallo_integracion else ""
    s.fallo_integracion = (previo + que)[:1000]
    s.intentos_integracion = min(s.intentos_integracion + 1, 32000)
    s.save(update_fields=["fallo_integracion", "intentos_integracion", "updated_at"])


# --- los efectos ----------------------------------------------------------------

def reasignar(s) -> bool:
    """Mueve el ticket de WispHub al equipo que instala. True si quedo hecho."""
    if not s.ticket_wisphub or s.ticket_reasignado_en:
        return True
    import requests

    from solicitudes.entrega import _tenant_del_motor

    if s.decision_automatica:
        detalle = f"Factibilidad confirmada por {AUTOR_DEXTER}. {s.prefactibilidad_motivo}"
    else:
        detalle = f"Factibilidad confirmada. {s.nota_revision}".strip()
    detalle += f"\n\n{s.nombre_completo} | {s.direccion}, {s.barrio}"
    if s.tiene_gps:
        detalle += f" | GPS: {s.gps_lat}, {s.gps_lng}"
    try:
        r = requests.post(f"{_base()}/interno/herramienta/reasignar_ticket_instalacion",
                          params={"tenant": _tenant_del_motor(s)},
                          json={"id_ticket": s.ticket_wisphub, "descripcion": detalle[:400]},
                          headers=_cabeceras(_clave(s, "reasignacion")), timeout=45)
        r.raise_for_status()
    except Exception as e:                              # noqa: BLE001
        _anotar_fallo(s, f"reasignacion: {_falla(e)}")
        return False
    s.ticket_reasignado_en = timezone.now()
    s.save(update_fields=["ticket_reasignado_en", "updated_at"])
    return True


def cerrar_ticket(s) -> bool:
    """Cierra el ticket de WispHub de una solicitud rechazada o cancelada."""
    if not s.ticket_wisphub or s.ticket_cerrado_en:
        return True
    from solicitudes.entrega import cerrar_ticket_wisphub

    if s.estado == SolicitudServicio.SIN_FACTIBILIDAD:
        quien = AUTOR_DEXTER if s.decision_automatica else (_nombre_de(s.revisada_por) or "el equipo")
        texto = (f"Solicitud de instalacion SIN FACTIBILIDAD. Lo decidio {quien}.\n\n"
                 f"Motivo: \"{s.nota_revision}\"")
        motivo = s.nota_revision
    else:
        texto, motivo = None, s.motivo_cancelacion
    try:
        cerrar_ticket_wisphub(s, motivo, texto=texto, clave_idem=_clave(s, "cierre"))
    except Exception as e:                              # noqa: BLE001
        _anotar_fallo(s, f"cierre ticket: {_falla(e)}")
        return False
    s.ticket_cerrado_en = timezone.now()
    s.save(update_fields=["ticket_cerrado_en", "updated_at"])
    return True


def avisar_rechazo(s, vuelta: int = 0) -> dict | None:
    """Le pide al motor el aviso al prospecto. Devuelve lo que contesto.

    Si el motor dice 'todavia_no' (fuera del horario de la empresa), queda
    'esperando' y se reagenda por Celery. La clave es FIJA: el motor no lo
    manda dos veces aunque se pida diez.
    """
    if s.estado != SolicitudServicio.SIN_FACTIBILIDAD:
        return None
    if s.aviso_cliente_estado in (SolicitudServicio.AVISO_ENVIADO,
                                  SolicitudServicio.AVISO_NO_APLICA):
        return None
    from common import avisos_al_cliente
    from operaciones import areas_del_tenant

    tenant = areas_del_tenant.tenant_de(s.org_id)
    if not tenant:
        datos = {"enviado": False, "motivo": "sin_empresa"}
    else:
        nombre = (s.nombre or "").strip()
        cuerpo = {
            "tenant": tenant,
            "evento": EVENTO_RECHAZO,
            "clave": f"solicitud:{s.id}:sin_factibilidad",
            "telefono": s.telefono or "",
            "contexto": {"cliente_nombre": nombre.split(" ")[0] if nombre else "",
                         "cliente_apellidos": (s.apellido or "").strip(),
                         "cliente_nombre_completo": s.nombre_completo,
                         "motivo_factibilidad": s.nota_revision},
        }
        datos = avisos_al_cliente.pedir(_base(), cuerpo, f"rechazo solicitud={s.id}")
        if datos is None:
            datos = {"enviado": False, "motivo": "motor_no_contesta"}

    motivo = str(datos.get("motivo") or "")
    if datos.get("enviado") or motivo == "ya_enviado":
        s.aviso_cliente_estado, s.aviso_cliente_motivo = SolicitudServicio.AVISO_ENVIADO, ""
        s.aviso_cliente_en = s.aviso_cliente_en or timezone.now()
    elif motivo == "todavia_no":
        s.aviso_cliente_estado, s.aviso_cliente_motivo = SolicitudServicio.AVISO_ESPERANDO, motivo
        espera = avisos_al_cliente.reagendar_en(datos, vuelta)
        if espera is not None:
            try:
                from solicitudes.tasks import avisar_rechazo_al_cliente

                avisar_rechazo_al_cliente.apply_async(
                    args=[str(s.id), str(s.org_id), vuelta + 1], countdown=espera)
            except Exception as e:                      # noqa: BLE001
                logger.warning("solicitudes: no se pudo reagendar el aviso (%s)",
                               type(e).__name__)
    else:
        s.aviso_cliente_estado = SolicitudServicio.AVISO_NO_ENVIADO
        s.aviso_cliente_motivo = motivo[:80]
    s.save(update_fields=["aviso_cliente_estado", "aviso_cliente_motivo",
                          "aviso_cliente_en", "updated_at"])
    return datos


# --- el Lead -----------------------------------------------------------------------

#: Lo que el prospecto pasa a ser segun su solicitud. 'instalada' no existe
#: como estado de la solicitud (no sabe que orden la instalo): aprobar es
#: cerrar la venta, y ahi pasa a 'converted'.
ESTADO_DEL_LEAD = {
    SolicitudServicio.ENVIADA: "in process",
    SolicitudServicio.APROBADA: "converted",
    SolicitudServicio.SIN_FACTIBILIDAD: "closed",
    SolicitudServicio.CANCELADA: "closed",
}


def sincronizar_lead(s) -> None:
    """El prospecto sigue a su solicitud. Por UPDATE del ORM y sin pasar por
    'leads/' (lo cambia el estado, no el resto de la ficha). Nunca rompe a quien
    llama: es un reflejo, no la decision."""
    destino = ESTADO_DEL_LEAD.get(s.estado)
    if not destino or not s.lead_id:
        return
    try:
        from django.db.models import Q

        from leads.models import Lead

        qs = Lead.objects.filter(pk=s.lead_id, org_id=s.org_id)
        if s.estado == SolicitudServicio.ENVIADA:
            #  Enviar no deshace un desenlace: solo avanza lo que estaba sin tocar.
            qs = qs.filter(Q(status__in=["assigned", ""]) | Q(status__isnull=True))
        qs.exclude(status=destino).update(status=destino, updated_at=timezone.now())
    except Exception as e:                              # noqa: BLE001
        logger.warning("solicitudes: no se pudo mover el prospecto (%s)", type(e).__name__)


# --- decidir y reintentar -------------------------------------------------------------

def _nombre_de(perfil) -> str:
    #  'name' y no 'get_full_name()': el User de este CRM no lo tiene, y la
    #  bandeja lo llamaba -- toda solicitud ya revisada rompia el listado con
    #  AttributeError (encontrado por las pruebas, 12/11/2026).
    user = getattr(perfil, "user", None)
    if user is None:
        return ""
    return (getattr(user, "name", "") or "").strip() or user.email or ""


def decidir(s, *, aprueba: bool, nota: str, autor=None, automatica: bool = False,
            motivo_auto: str = "") -> bool:
    """Toma la decision UNA vez y ejecuta sus efectos. False si ya no estaba
    'enviada' (otro la decidio primero)."""
    ahora = timezone.now()
    tomados = (SolicitudServicio.objects
               .filter(pk=s.pk, estado=SolicitudServicio.ENVIADA)
               .update(estado=(SolicitudServicio.APROBADA if aprueba
                               else SolicitudServicio.SIN_FACTIBILIDAD),
                       revisada_por=autor, revisada_en=ahora, nota_revision=nota,
                       decision_automatica=automatica,
                       prefactibilidad_motivo=(motivo_auto or s.prefactibilidad_motivo)[:300],
                       aviso_cliente_estado=("" if aprueba else SolicitudServicio.AVISO_PENDIENTE),
                       updated_at=ahora))
    if not tomados:
        return False
    s.refresh_from_db()
    sincronizar_lead(s)
    if aprueba:
        reasignar(s)
    else:
        cerrar_ticket(s)
        avisar_rechazo(s)
    return True


def pendientes(s) -> list[str]:
    """Lo que falta hacer afuera, calculado de los sellos."""
    falta = []
    if s.estado == SolicitudServicio.APROBADA and s.ticket_wisphub and not s.ticket_reasignado_en:
        falta.append("reasignacion")
    if (s.estado in (SolicitudServicio.SIN_FACTIBILIDAD, SolicitudServicio.CANCELADA)
            and s.ticket_wisphub and not s.ticket_cerrado_en):
        falta.append("cierre")
    if (s.estado == SolicitudServicio.SIN_FACTIBILIDAD
            and s.aviso_cliente_estado in (SolicitudServicio.AVISO_PENDIENTE,
                                           SolicitudServicio.AVISO_NO_ENVIADO)):
        falta.append("aviso")
    return falta


def reintentar(s) -> list[str]:
    """Reejecuta lo pendiente. Devuelve lo que SIGUE pendiente despues."""
    falta = pendientes(s)
    if "reasignacion" in falta:
        reasignar(s)
    if "cierre" in falta:
        cerrar_ticket(s)
    if "aviso" in falta:
        avisar_rechazo(s)
    s.refresh_from_db()
    return pendientes(s)


def para_pantalla(s) -> dict:
    """Lo que la bandeja muestra de lo que paso despues de decidir."""
    motivo = s.aviso_cliente_motivo or ""
    if motivo.startswith("dato_faltante:"):
        texto = f"falta el dato «{motivo.split(':', 1)[1]}» que pide la plantilla"
    else:
        texto = POR_QUE_NO_SALIO.get(motivo, motivo)
    return {
        "pendientes": pendientes(s),
        "ticket_reasignado_en": (s.ticket_reasignado_en.isoformat()
                                 if s.ticket_reasignado_en else None),
        "ticket_cerrado_en": (s.ticket_cerrado_en.isoformat()
                              if s.ticket_cerrado_en else None),
        "aviso_cliente": {
            "estado": s.aviso_cliente_estado or "",
            "motivo": motivo,
            "texto": texto,
            "en": s.aviso_cliente_en.isoformat() if s.aviso_cliente_en else None,
        },
        "decision_automatica": bool(s.decision_automatica),
        "prefactibilidad_motivo": s.prefactibilidad_motivo or "",
        "revisada_por": (AUTOR_DEXTER if s.decision_automatica
                         else _nombre_de(s.revisada_por)),
    }
