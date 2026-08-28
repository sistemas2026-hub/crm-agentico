"""Endpoint publico de la solicitud de servicio.

Anonimo: no hay JWT, no hay sesion, no hay cookie. El token de la URL es la
unica credencial, y por eso cada peticion lo vuelve a verificar desde cero,
vuelve a cargar la fila por su hash y vuelve a fijar el contexto RLS antes de
tocar el ORM. Mismo criterio que `cases/csat_views.py`, que es el otro
endpoint anonimo del sistema: no se confia en nada que venga del cliente
salvo el token.

Dos operaciones:

  GET   -- lo que el formulario necesita para PRELLENARSE con lo que la
           persona ya le dijo a Dexter por WhatsApp, y para saber si esta
           solicitud ya se envio.
  POST  -- la solicitud completa, con las tres fotos y la firma.
"""

from __future__ import annotations

import os

from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.utils import timezone
from rest_framework import status as http
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasOrgContext
from common.portal_tokens import resolve_portal_org_by_hash
from common.tasks import set_rls_context
from solicitudes.models import SolicitudServicio
from solicitudes.tokens import SOLICITUD_TOKEN_TTL_DIAS, hash_token, solicitud_signer

# El formulario acepta hasta 5 MB por imagen. El limite se aplica ACA tambien,
# y no solo en el navegador: el navegador es del cliente, y este endpoint es
# publico. Sin esto, cualquiera con el link puede subir un archivo de un giga.
MAX_BYTES_IMAGEN = 5 * 1024 * 1024
IMAGENES = ("foto_cedula", "foto_recibo", "foto_solicitante")

# Los campos de texto que el formulario manda, y los unicos que se guardan.
# Lista blanca, no negra: un campo nuevo que aparezca en el POST se ignora en
# vez de escribirse solo. Mismo criterio que las listas blancas del motor.
CAMPOS_TEXTO = (
    "nombre", "apellido", "edad", "correo", "telefono",
    "tipo_documento", "numero_documento",
    "tipo_solicitud", "plan_interesado", "fecha_corte", "como_se_entero",
    "direccion", "barrio", "gps_lat", "gps_lng", "gps_precision_m",
)

# Sin estos no hay instalacion posible, asi que el envio se rechaza. El resto
# se guarda como venga -- ver el docstring del modelo sobre por que no se le
# discute el formato a quien esta escribiendo desde un celular.
OBLIGATORIOS = ("nombre", "apellido", "telefono", "numero_documento",
                "direccion", "barrio")


class SolicitudCrearView(APIView):
    """Crea el Lead y su solicitud, y devuelve el link con token.

    La llama el MOTOR, no una persona: es lo que corre cuando el asistente
    cierra una venta por WhatsApp. Autenticada con el PAT del CRM, igual que
    el resto de lo que el motor consulta aca.

    Las dos cosas se crean juntas y en una transaccion a proposito. Con dos
    llamadas separadas -una al lead, otra a la solicitud- un fallo en la
    segunda deja un prospecto registrado al que el asistente no le puede dar
    ningun link, y nadie se entera hasta que el cliente pregunta.

    Devolver el link ACA es ademas lo que garantiza que no se entregue sin
    registro: el token va firmado, asi que el modelo no puede fabricarlo ni
    adivinarlo. Antes eso se sostenia sacando la URL del prompt; ahora se
    sostiene solo.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        from leads.models import Lead
        from solicitudes.tokens import firmar, hash_token, link_de, vencimiento

        org = request.profile.org
        datos = request.data

        titulo = str(datos.get("title") or "").strip()
        telefono = str(datos.get("phone") or "").strip()
        if not titulo or not telefono:
            return Response({"error": "Faltan 'title' y 'phone'."},
                            status=http.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            lead = Lead.objects.create(
                org=org, title=titulo, phone=telefono,
                first_name=str(datos.get("first_name") or "")[:255],
                city=str(datos.get("city") or "")[:255],
                description=str(datos.get("description") or ""),
                status=str(datos.get("status") or "assigned"),
                source=str(datos.get("source") or "other"),
                opportunity_amount=(datos.get("opportunity_amount") or None),
            )
            # El token se firma sobre el id del lead: asi el link queda atado a
            # ESTE prospecto y no a un identificador suelto que despues nadie
            # sabe de donde salio.
            crudo = firmar(lead.id)
            solicitud = SolicitudServicio.objects.create(
                org=org, lead=lead, token_hash=hash_token(crudo),
                expira_en=vencimiento(),
                telefono=telefono,
                plan_interesado=str(datos.get("plan_interesado") or "")[:160],
                barrio=str(datos.get("city") or "")[:160],
            )

        # Fuera de la transaccion: es el registro que permite resolver la
        # organizacion de una peticion anonima, y que falle no puede deshacer
        # una solicitud ya creada.
        from common.portal_tokens import register_portal_token
        register_portal_token(crudo, org.id, "solicitud", solicitud.id)

        return Response({"lead_id": str(lead.id), "solicitud_id": str(solicitud.id),
                         "link": link_de(crudo)}, status=http.HTTP_201_CREATED)


def _planes_de(localidad: str) -> list:
    """Los planes que se ofrecen en esa localidad, segun el catalogo curado.

    Se le preguntan al motor (POST /interno/herramienta/consultar_planes_venta)
    en vez de reenviar lo que el modelo dijo en la conversacion: un plan que ya
    no se vende, o un precio viejo, no puede colarse en un formulario que la
    persona despues firma. El catalogo del tenant es la unica fuente.

    NUNCA lanza. Si el motor no responde, se devuelve vacio y el formulario cae
    a un campo de texto libre con lo que ya traia: una solicitud que se puede
    enviar vale mas que una lista perfecta.
    """
    if not localidad:
        return []
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(f"{base}/interno/herramienta/consultar_planes_venta",
                          params={"tenant": tenant},
                          json={"localidad": localidad},
                          headers=cabeceras, timeout=20)
        r.raise_for_status()
        return list(((r.json() or {}).get("resultado") or {}).get("planes") or [])
    except Exception as e:                          # noqa: BLE001
        print(f"[solicitudes] no se pudieron leer los planes de "
              f"{localidad!r}: {type(e).__name__}: {e}")
        return []


def _cargar(token: str):
    """(solicitud, estado_http, error). Exactamente uno de los dos lados."""
    try:
        solicitud_signer().unsign(token, max_age=SOLICITUD_TOKEN_TTL_DIAS * 24 * 3600)
    except SignatureExpired:
        return None, 410, "El enlace de la solicitud vencio."
    except BadSignature:
        return None, 400, "El enlace de la solicitud no es valido."

    h = hash_token(token)
    # Antes de leer la fila hay que saber de que organizacion es: bajo RLS con
    # contexto vacio no se ve nada. El registro de tokens es lo unico que se
    # puede consultar sin contexto.
    org_id = resolve_portal_org_by_hash(h, "solicitud")
    if org_id:
        set_rls_context(org_id)

    solicitud = SolicitudServicio.objects.filter(token_hash=h).first()
    if solicitud is None:
        return None, 410, "El enlace de la solicitud ya no es valido."
    if timezone.now() >= solicitud.expira_en:
        return None, 410, "El enlace de la solicitud vencio."
    set_rls_context(solicitud.org_id)
    return solicitud, None, None


class SolicitudPublicaView(APIView):
    """Lo que abre el interesado desde el link que le paso Dexter."""

    permission_classes = (AllowAny,)
    authentication_classes: list = []
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request, token: str):
        solicitud, estado, err = _cargar(token)
        if solicitud is None:
            return Response({"error": err}, status=estado)

        # Primera apertura: se anota. Es la mitad de la metrica que antes no
        # existia -- cuantos abren el formulario contra cuantos lo terminan.
        if solicitud.abierta_en is None:
            solicitud.abierta_en = timezone.now()
            solicitud.save(update_fields=["abierta_en", "updated_at"])

        return Response({
            "ya_enviada": solicitud.estado == SolicitudServicio.ENVIADA,
            "enviada_en": (solicitud.enviada_en.isoformat()
                           if solicitud.enviada_en else None),
            # Los planes que se ofrecen EN SU ZONA. Se piden al motor, que los
            # resuelve del catalogo curado del tenant -- no se reenvia lo que
            # el modelo dijo en la conversacion: eso es como se cuela un plan
            # que ya no se vende, o un precio viejo, en un formulario que la
            # persona firma.
            #
            # Si el motor no responde, la lista viene vacia y el formulario
            # cae a un campo de texto libre con lo que ya venia. Una solicitud
            # que se puede enviar vale mas que una lista perfecta.
            "planes_disponibles": _planes_de(solicitud.barrio),
            # Lo que la persona ya le dijo a Dexter. Volver a preguntarselo
            # seria la forma mas rapida de que abandone.
            "prellenado": {
                campo: getattr(solicitud, campo)
                for campo in CAMPOS_TEXTO
            },
        })

    def post(self, request, token: str):
        solicitud, estado, err = _cargar(token)
        if solicitud is None:
            return Response({"error": err}, status=estado)

        # Una solicitud enviada no se re-envia. Si hiciera falta corregir algo,
        # eso es una conversacion con el equipo comercial, no un segundo PDF
        # que nadie sabe cual de los dos vale.
        if solicitud.estado == SolicitudServicio.ENVIADA:
            return Response(
                {"error": "Esta solicitud ya fue enviada.",
                 "enviada_en": solicitud.enviada_en.isoformat()},
                status=http.HTTP_409_CONFLICT)

        datos = request.data
        faltan = [c for c in OBLIGATORIOS if not str(datos.get(c) or "").strip()]
        if faltan:
            return Response({"error": "Faltan datos obligatorios.",
                             "campos": faltan}, status=http.HTTP_400_BAD_REQUEST)

        if not (str(datos.get("autoriza_habeas_data")).lower() in ("true", "1", "on")):
            return Response(
                {"error": "Hace falta autorizar el tratamiento de datos "
                          "personales para poder continuar."},
                status=http.HTTP_400_BAD_REQUEST)

        imagenes = {}
        for nombre in IMAGENES:
            archivo = request.FILES.get(nombre)
            if archivo is None:
                return Response({"error": f"Falta la imagen '{nombre}'."},
                                status=http.HTTP_400_BAD_REQUEST)
            if archivo.size > MAX_BYTES_IMAGEN:
                return Response(
                    {"error": f"La imagen '{nombre}' pesa mas de 5 MB."},
                    status=http.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
            imagenes[nombre] = archivo.read()

        firma = request.FILES.get("firma")
        firma_bytes = firma.read() if firma is not None else b""
        if not firma_bytes:
            return Response({"error": "Falta la firma."},
                            status=http.HTTP_400_BAD_REQUEST)

        for campo in CAMPOS_TEXTO:
            if campo in datos:
                setattr(solicitud, campo, str(datos.get(campo) or "").strip())

        solicitud.autoriza_habeas_data = True
        solicitud.autoriza_centrales_riesgo = (
            str(datos.get("autoriza_centrales_riesgo")).lower() in ("true", "1", "on"))
        # El TEXTO que acepto, no solo que acepto. Ver el modelo.
        solicitud.texto_autorizaciones = str(datos.get("texto_autorizaciones") or "")
        solicitud.autorizaciones_en = timezone.now()
        solicitud.estado = SolicitudServicio.ENVIADA
        solicitud.enviada_en = timezone.now()

        # El PDF se arma ANTES de cerrar la transaccion, pero el correo y el
        # ticket de WispHub van DESPUES de guardar y fuera de ella: son dos
        # sistemas de terceros, y una solicitud completa no se puede perder
        # porque uno de ellos este caido. Ver el comentario de
        # 'fallo_integracion' en el modelo.
        from solicitudes.pdf import armar_expediente

        try:
            solicitud.pdf.save(
                f"solicitud-{solicitud.id}.pdf",
                armar_expediente(solicitud, imagenes, firma_bytes),
                save=False)
        except Exception as e:                      # noqa: BLE001
            solicitud.fallo_integracion = f"PDF: {type(e).__name__}: {e}"[:500]

        with transaction.atomic():
            solicitud.save()

        from solicitudes.entrega import entregar

        entregar(solicitud)

        return Response({
            "ok": True,
            "enviada_en": solicitud.enviada_en.isoformat(),
            "mensaje": "Recibimos tu solicitud. Te contactamos para "
                       "coordinar la instalacion.",
        }, status=http.HTTP_201_CREATED)
