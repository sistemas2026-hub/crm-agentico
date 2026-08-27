"""Los dos efectos que ya producia el formulario del sitio web: correo y ticket.

Regla que manda sobre todo lo demas: **una solicitud completa no se pierde
porque un tercero este caido.** Cuando esto corre, la persona ya llenó veinte
campos, sacó tres fotos y firmó con el dedo. Si Gmail no responde o WispHub
tarda, eso no puede deshacerse: la solicitud ya esta guardada y con su PDF: lo
unico que queda pendiente es avisarle a alguien, y eso se reintenta.

Por eso cada paso va en su propio try, ninguno corta al siguiente, y lo que
falle queda escrito en 'fallo_integracion' para que se vea en la plataforma en
vez de desaparecer en un log.

El ticket de WispHub NO se crea desde aca. La credencial vive solo en el motor
-- copiarla al backend habria dejado la misma clave en dos servicios, que es
lo que despues se desincroniza sin que nadie sepa cual es la buena. El motor
expone POST /interno/herramienta/<nombre> para esto, y solo ejecuta las
herramientas declaradas con 'invocable_por_servicio'.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

# A donde llega hoy la solicitud. Es el mismo buzon que ya figura como
# 'email_tecnico' en los tickets "Instalacion Nueva" de WispHub, asi que el
# correo nuevo aterriza donde Operaciones ya mira.
DESTINO_POR_DEFECTO = "info.rapilinksas@gmail.com"


def _destino() -> list[str]:
    crudo = (getattr(settings, "SOLICITUDES_EMAIL_DESTINO", "")
             or os.environ.get("SOLICITUDES_EMAIL_DESTINO", "")
             or DESTINO_POR_DEFECTO)
    return [x.strip() for x in crudo.split(",") if x.strip()]


def _cuerpo(s) -> str:
    lineas = [
        f"Nueva solicitud de servicio - {s.nombre_completo or s.telefono}",
        "",
        f"Radicado : {s.id}",
        f"Enviada  : {timezone.localtime(s.enviada_en):%d/%m/%Y %H:%M}",
        "",
        f"Plan     : {s.plan_interesado or '-'}",
        f"Telefono : {s.telefono or '-'}",
        f"Correo   : {s.correo or '-'}",
        f"Documento: {s.tipo_documento} {s.numero_documento}".strip(),
        "",
        f"Direccion: {s.direccion or '-'}",
        f"Barrio   : {s.barrio or '-'}",
    ]
    if s.tiene_gps:
        lineas += [f"GPS      : {s.gps_lat}, {s.gps_lng}",
                   f"Mapa     : https://www.google.com/maps?q={s.gps_lat},{s.gps_lng}"]
    else:
        lineas += ["GPS      : SIN COORDENADAS -- hay que verificar la "
                   "viabilidad en sitio."]
    lineas += ["", "El expediente completo (documentos y firma) va adjunto en PDF."]
    return "\n".join(lineas)


def _enviar_correo(s) -> None:
    correo = EmailMessage(
        subject=f"Solicitud de servicio - {s.nombre_completo or s.telefono}",
        body=_cuerpo(s),
        to=_destino(),
    )
    if s.pdf:
        s.pdf.open("rb")
        try:
            correo.attach(f"solicitud-{s.id}.pdf", s.pdf.read(), "application/pdf")
        finally:
            s.pdf.close()
    correo.send(fail_silently=False)


def _crear_ticket_wisphub(s) -> str:
    """Le pide al motor que cree el ticket. Devuelve el id, o '' si no vino."""
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    herramienta = os.environ.get("SOLICITUDES_HERRAMIENTA_TICKET", "") or "crear_ticket"

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    # El asunto se escribe EXACTAMENTE como los que ya existen ("Instalacion
    # Nueva"): quien filtra la bandeja de WispHub por ese texto tiene que
    # seguir encontrando estos. Ojo -- el catalogo de asuntos de WispHub trae
    # el typo "Instatalacion Nueva" como valor distinto (ver la skill
    # wisphub-api); no es este.
    detalle = _cuerpo(s)
    r = requests.post(
        f"{base}/interno/herramienta/{herramienta}",
        params={"tenant": tenant},
        json={"asunto": "Instalacion Nueva",
              "descripcion": detalle,
              "prioridad": "media"},
        headers=cabeceras, timeout=45)
    r.raise_for_status()
    datos = (r.json() or {}).get("resultado") or {}
    if isinstance(datos, dict):
        return str(datos.get("id") or datos.get("id_ticket") or "")
    return ""


def entregar(s) -> None:
    """Correo y ticket. Nunca lanza: la solicitud ya esta a salvo."""
    fallos = []

    try:
        _enviar_correo(s)
        s.correo_enviado_en = timezone.now()
    except Exception as e:                          # noqa: BLE001
        fallos.append(f"correo: {type(e).__name__}: {e}")

    try:
        s.ticket_wisphub = _crear_ticket_wisphub(s)
    except Exception as e:                          # noqa: BLE001
        fallos.append(f"ticket: {type(e).__name__}: {e}")

    if fallos:
        # Se ACUMULA con lo que ya hubiera (puede venir un fallo del PDF desde
        # la vista): si el PDF no salio y ademas no se pudo mandar el correo,
        # quien mire la solicitud tiene que ver las dos cosas, no la ultima.
        previo = (s.fallo_integracion + " | ") if s.fallo_integracion else ""
        s.fallo_integracion = (previo + " | ".join(fallos))[:1000]

    s.save(update_fields=["correo_enviado_en", "ticket_wisphub",
                          "fallo_integracion", "updated_at"])
