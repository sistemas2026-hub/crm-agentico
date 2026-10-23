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
import uuid

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


def _descripcion_ticket(s) -> str:
    """La descripcion del ticket, en el MISMO formato que los que ya existen.

    Copiado de un ticket real de WispHub (27/08/2026), no inventado:

        Instalacion Nueva - Andrea Leon | Tel: 3116138025 | correo@x |
        Calle 37#9-11 apto 1, Manuela Beltran | GPS: 10.90, -74.77 | Doc: CC 326911

    Es una sola linea con separadores ' | ' a proposito: asi se lee entera en
    el listado de WispHub sin abrir el ticket, que es como Operaciones los
    mira. Cambiar el formato obligaria a leerlos distinto segun de donde
    vinieron.
    """
    partes = [f"Instalacion Nueva - {s.nombre_completo or s.telefono}"]
    if s.telefono:
        partes.append(f"Tel: {s.telefono}")
    if s.correo:
        partes.append(s.correo)
    direccion = ", ".join(x for x in (s.direccion, s.barrio) if x)
    if direccion:
        partes.append(direccion)
    if s.tiene_gps:
        partes.append(f"GPS: {s.gps_lat}, {s.gps_lng}")
    else:
        partes.append("SIN GPS - verificar viabilidad en sitio")
    doc = " ".join(x for x in (s.tipo_documento, s.numero_documento) if x)
    if doc:
        partes.append(f"Doc: {doc}")
    if s.plan_interesado:
        partes.append(f"Plan: {s.plan_interesado}")
    return " | ".join(partes)


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
    herramienta = (os.environ.get("SOLICITUDES_HERRAMIENTA_TICKET", "")
                   or "crear_ticket_instalacion")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    # El asunto, el departamento y la prioridad NO se mandan desde aca: son
    # 'argumentos_fijos' de la herramienta, junto al id del cliente ficticio
    # del que cuelgan estos tickets. Lo unico que aporta el backend es la
    # descripcion, que es lo que cambia por solicitud.
    r = requests.post(
        f"{base}/interno/herramienta/{herramienta}",
        params={"tenant": tenant},
        json={"descripcion": _descripcion_ticket(s)},
        headers=cabeceras, timeout=45)
    r.raise_for_status()
    datos = (r.json() or {}).get("resultado") or {}
    if isinstance(datos, dict):
        return str(datos.get("id") or datos.get("id_ticket") or "")
    return ""


def _completar_ticket(s) -> None:
    """Le pone al ticket las fechas estimadas y le adjunta el PDF.

    Va por PATCH y no en la creacion porque el POST de WispHub IGNORA las
    fechas estimadas: medido el 09/09/2026, el ticket 92156 salio con las dos
    vacias aunque el motor las mandaba. OPTIONS las lista en actions.POST y
    hasta las marca requeridas -- solo se habia probado la escritura por PATCH.

    De paso resuelve otra rareza: con el archivo SOLO, ese endpoint devuelve
    500. Necesita al menos un campo normal al lado, y las fechas lo son.

    QUE PDF SE ADJUNTA -- 'SOLICITUDES_ADJUNTO_TICKET'

        expediente  (por defecto)  el PDF completo del formulario
        orden                      solo la hoja operativa

    LO QUE HAY QUE SABER ANTES DE ELEGIR, porque no se puede deshacer: lo que
    queda en 'archivo_ticket' es PUBLICO. Medido el 09/09/2026 -- se descarga
    de avisos.wisphub.io/media/ con un GET sin ninguna credencial. El
    expediente trae documento de identidad, recibo de servicios, foto del
    solicitante, firma y GPS del domicilio; ahi eso queda al alcance de
    cualquiera que tenga o adivine la URL, y no hay forma de borrarlo desde la
    API.

    Con 'orden' va solo lo operativo (a donde ir, con quien, que plan) mas el
    link al expediente, que exige sesion. El tecnico ve a donde ir y quien
    necesite la cedula hace clic y el CRM le pide login.

    Lo eligio el cliente el 09/09/2026, con el riesgo sobre la mesa y medido:
    quiere el expediente completo en el ticket, para que el tecnico no dependa
    de entrar al CRM. Queda en una variable de entorno y no fijo en codigo
    justamente para poder volver atras sin un despliegue de codigo.

    Si la solicitud no tiene expediente armado, se cae a la orden en vez de
    dejar el ticket sin nada.

    El nombre es aleatorio en los dos casos. No es control de acceso -- lo que
    protege de verdad es el CONTENIDO, y con 'expediente' esa proteccion no
    existe-- pero evita que las URLs se puedan enumerar.

    El PDF viaja en base64 porque el puente con el motor es JSON. El motor lo
    decodifica y lo manda como archivo -- ver 'argumentos_archivo' en
    nucleo/config/schema.py.
    """
    import base64
    import requests

    from common.links import frontend_url
    from solicitudes.pdf import armar_orden_instalacion

    que = (os.environ.get("SOLICITUDES_ADJUNTO_TICKET", "") or "expediente").lower()

    if que == "expediente" and s.pdf:
        s.pdf.open("rb")
        try:
            pdf = s.pdf.read()
        finally:
            s.pdf.close()
        nombre = f"expediente-{uuid.uuid4().hex}.pdf"
    else:
        # El link va AL PDF, no a una pantalla. Decia '/instalaciones/<id>' y
        # esa ruta no existe: la bandeja es '/instalaciones' a secas, con
        # pestañas. Al abrirlo desde el ticket, el CRM pedia elegir
        # organizacion y despues dejaba al tecnico en 'Hoy', sin ningun
        # expediente a la vista (reportado el 09/09/2026).
        pdf = armar_orden_instalacion(
            s, url_expediente=frontend_url(f"/api/solicitudes/{s.id}/expediente"))
        nombre = f"orden-instalacion-{uuid.uuid4().hex}.pdf"

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    herramienta = (os.environ.get("SOLICITUDES_HERRAMIENTA_COMPLETAR", "")
                   or "completar_ticket_instalacion")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    r = requests.post(
        f"{base}/interno/herramienta/{herramienta}",
        params={"tenant": tenant},
        json={"id_ticket": s.ticket_wisphub,
              "archivo_ticket": {"nombre": nombre,
                                 "tipo": "application/pdf",
                                 "base64": base64.b64encode(pdf).decode()}},
        headers=cabeceras, timeout=60)
    r.raise_for_status()


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

    # La orden de instalacion va DESPUES y en su propio try: si el adjunto
    # falla, el ticket ya existe y el trabajo puede salir igual -- la orden es
    # una comodidad para el tecnico, no la solicitud. Mismo criterio que el
    # resto del modulo: lo que se pudo hacer no se deshace porque un paso
    # posterior falle.
    if s.ticket_wisphub:
        try:
            _completar_ticket(s)
        except Exception as e:                      # noqa: BLE001
            fallos.append(f"completar ticket: {type(e).__name__}: {e}")

    if fallos:
        # Se ACUMULA con lo que ya hubiera (puede venir un fallo del PDF desde
        # la vista): si el PDF no salio y ademas no se pudo mandar el correo,
        # quien mire la solicitud tiene que ver las dos cosas, no la ultima.
        previo = (s.fallo_integracion + " | ") if s.fallo_integracion else ""
        s.fallo_integracion = (previo + " | ".join(fallos))[:1000]

    s.save(update_fields=["correo_enviado_en", "ticket_wisphub",
                          "fallo_integracion", "updated_at"])


def cerrar_ticket_wisphub(s, motivo: str) -> None:
    """Responde el ticket de instalacion con el motivo y lo cierra.

    Existe porque cancelar solo en el CRM deja el ticket vivo en WispHub: el
    equipo saldria a instalar algo que el cliente ya cancelo. La cancelacion no
    esta completa hasta que el otro lado se entera.

    Va por el mismo puente que la creacion -- una herramienta del motor, no una
    llamada a WispHub desde aca-- para que el token y el contrato de esa API
    vivan en un solo lugar. Y la herramienta es configurable por la misma razon
    que la de crear: el nombre lo elige el catalogo del tenant, no este codigo.

    Lanza si falla. Quien llama decide que hacer -- hoy CancelarSolicitudView
    lo anota en 'fallo_integracion' y sigue: la cancelacion ya esta guardada y
    no se deshace porque un tercero no responda.
    """
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    herramienta = (os.environ.get("SOLICITUDES_HERRAMIENTA_CERRAR_TICKET", "")
                   or "cerrar_ticket_operativo")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    # El motivo va TAL CUAL lo escribio el cliente, entre comillas y con quien
    # lo dijo: quien lea el ticket despues tiene que poder distinguir lo que
    # dijo la persona de lo que interpretamos nosotros.
    texto = (f"El cliente cancelo la solicitud de instalacion.\n\n"
             f"Motivo, en sus palabras: \"{motivo}\"")
    r = requests.post(
        f"{base}/interno/herramienta/{herramienta}",
        params={"tenant": tenant},
        json={"id_ticket": s.ticket_wisphub, "respuesta": texto},
        headers=cabeceras, timeout=45)
    r.raise_for_status()
