"""Lo que ve y hace una persona del equipo con las solicitudes.

Tres cosas, todas autenticadas (a diferencia de views.py, que es la parte
publica que abre el prospecto):

  * Ajustes: que dos equipos de WispHub reciben las solicitudes nuevas y las
    aprobadas. Se ELIGEN de una lista traida de WispHub, no se escriben: un id
    tipeado mal es un ticket a nombre de nadie.
  * La bandeja: las solicitudes que llegaron, con lo que hace falta para
    decidir si el servicio llega a esa direccion.
  * La decision: aprobar o rechazar. Aprobar mueve el ticket de WispHub a la
    cola del equipo que instala.

POR QUE LA DECISION VIVE ACA Y NO EN WISPHUB
--------------------------------------------
Antes se tomaba en WispHub reasignando el ticket a mano. Funcionaba, pero no
dejaba rastro de QUIEN decidio ni CUANDO: solo se veia el resultado. Y la
solicitud (con su PDF, sus coordenadas y su conversacion de origen) ya vive
aca, asi que quien decide tiene todo delante en vez de ir a buscarlo.

El ticket de WispHub se sigue moviendo igual -- ver 'reasignar_ticket_
instalacion' en la config del tenant, y OJO: eso es un PUT, no un PATCH.
"""

from __future__ import annotations

import os

from django.utils import timezone
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasOrgContext
from solicitudes.models import SolicitudServicio

# Los cuatro valores que definen a que equipo va cada cosa. Viven en la config
# del tenant (variables_tenant) y no en una tabla nuestra: son datos de la
# empresa, del mismo tipo que el subdominio de una API o el id de una cuenta.
VARIABLES = {
    "tecnico_solicitudes": "WISPHUB_TECNICO_SOLICITUDES",
    "email_solicitudes": "WISPHUB_EMAIL_TECNICO_SOLICITUDES",
    "tecnico_aprobadas": "WISPHUB_TECNICO_APROBADAS",
    "email_aprobadas": "WISPHUB_EMAIL_TECNICO_APROBADAS",
}


def _motor(ruta: str, metodo: str = "POST", **kw):
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    kw.setdefault("timeout", 30)
    return requests.request(metodo, f"{base}{ruta}", headers=cabeceras, **kw)


def _tenant() -> str:
    return os.environ.get("MOTOR_TENANT", "") or "rapilink"


class TecnicosView(APIView):
    """El personal de WispHub, para que el admin elija en vez de escribir."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request):
        try:
            r = _motor(f"/interno/herramienta/consultar_tecnicos",
                       params={"tenant": _tenant()}, json={})
            r.raise_for_status()
            crudo = (r.json() or {}).get("resultado") or {}
        except Exception as e:                      # noqa: BLE001
            return Response({"error": f"No se pudo leer el personal de WispHub: {e}"},
                            status=http.HTTP_502_BAD_GATEWAY)

        filas = crudo.get("results") if isinstance(crudo, dict) else crudo
        return Response({"tecnicos": [
            {"id": str(f.get("id")), "nombre": f.get("nombre") or "(sin nombre)",
             "email": f.get("email") or ""}
            for f in (filas or []) if f.get("id")
        ]})


class AjustesView(APIView):
    """Los dos equipos: el que valida y el que instala."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request):
        # OJO con el endpoint: '/configuracion' devuelve identidad, persona,
        # modelo y roles -- NO 'variables_tenant'. Leer de ahi dejaba los
        # cuatro campos vacios y la pantalla se veia como si no hubiera nada
        # configurado, con los valores correctos guardados.
        #
        # '/configuracion/variables' se agrego para esto: habia PUT y DELETE
        # pero no lectura, asi que ninguna pantalla podia mostrar lo que hay.
        try:
            r = _motor("/configuracion/variables", metodo="GET",
                       params={"tenant": _tenant()})
            r.raise_for_status()
            variables = (r.json() or {}).get("variables") or {}
        except Exception as e:                      # noqa: BLE001
            return Response({"error": f"No se pudo leer la configuracion: {e}"},
                            status=http.HTTP_502_BAD_GATEWAY)
        return Response({clave: variables.get(nombre, "")
                         for clave, nombre in VARIABLES.items()})

    def put(self, request):
        errores = []
        for clave, nombre in VARIABLES.items():
            if clave not in request.data:
                continue
            valor = str(request.data.get(clave) or "").strip()
            try:
                r = _motor(f"/configuracion/variables/{nombre}", metodo="PUT",
                           json={"valor": valor})
                r.raise_for_status()
            except Exception as e:                  # noqa: BLE001
                errores.append(f"{nombre}: {e}")
        if errores:
            return Response({"error": " | ".join(errores)},
                            status=http.HTTP_502_BAD_GATEWAY)
        return self.get(request)


class BandejaView(APIView):
    """Las solicitudes que llegaron, para decidir sobre ellas."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request):
        org = request.profile.org
        estado = request.query_params.get("estado") or ""
        qs = SolicitudServicio.objects.filter(org=org)
        if estado:
            qs = qs.filter(estado=estado)
        else:
            # Por defecto, lo que espera una decision. Es para lo que se abre
            # esta pantalla; el resto se filtra a proposito.
            qs = qs.filter(estado=SolicitudServicio.ENVIADA)

        return Response({"solicitudes": [{
            "id": str(s.id),
            "estado": s.estado,
            "nombre": s.nombre_completo,
            "documento": f"{s.tipo_documento} {s.numero_documento}".strip(),
            "telefono": s.telefono,
            "correo": s.correo,
            "direccion": s.direccion,
            "barrio": s.barrio,
            "plan": s.plan_interesado,
            "gps": ({"lat": s.gps_lat, "lng": s.gps_lng,
                     "precision_m": s.gps_precision_m} if s.tiene_gps else None),
            # El PDF con la cedula, el recibo y la firma. Es lo que mira quien
            # decide, asi que la bandeja lo enlaza en vez de esconderlo.
            "pdf": (s.pdf.url if s.pdf else None),
            "enviada_en": s.enviada_en.isoformat() if s.enviada_en else None,
            "ticket_wisphub": s.ticket_wisphub,
            "fallo_integracion": s.fallo_integracion,
        } for s in qs.order_by("-enviada_en")[:200]]})


class DecidirView(APIView):
    """Aprobar o rechazar una solicitud.

    Aprobar mueve el ticket de WispHub a la cola del equipo que instala. Si esa
    llamada falla, la decision NO se pierde: queda guardada con el fallo
    anotado, y se puede reintentar. Mismo criterio que el resto de este modulo
    -- lo que ya decidio una persona no se deshace porque un tercero no
    responda.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request, solicitud_id: str):
        org = request.profile.org
        s = SolicitudServicio.objects.filter(org=org, id=solicitud_id).first()
        if s is None:
            return Response({"error": "No existe esa solicitud."},
                            status=http.HTTP_404_NOT_FOUND)
        if s.estado not in (SolicitudServicio.ENVIADA,):
            return Response(
                {"error": f"Esta solicitud ya esta en estado '{s.get_estado_display()}'."},
                status=http.HTTP_409_CONFLICT)

        aprueba = str(request.data.get("aprueba")).lower() in ("true", "1", "si")
        nota = str(request.data.get("nota") or "").strip()
        if not aprueba and not nota:
            # Un rechazo sin motivo no le sirve a nadie: ni al cliente, que
            # va a preguntar por que, ni a quien lo lea dentro de tres meses.
            return Response({"error": "Para rechazar hace falta anotar el motivo."},
                            status=http.HTTP_400_BAD_REQUEST)

        s.estado = (SolicitudServicio.APROBADA if aprueba
                    else SolicitudServicio.SIN_FACTIBILIDAD)
        s.revisada_por = request.profile
        s.revisada_en = timezone.now()
        s.nota_revision = nota

        if aprueba and s.ticket_wisphub:
            detalle = (f"Factibilidad confirmada. {nota}".strip() + "\n\n"
                       f"{s.nombre_completo} | {s.direccion}, {s.barrio}")
            if s.tiene_gps:
                detalle += f" | GPS: {s.gps_lat}, {s.gps_lng}"
            try:
                r = _motor("/interno/herramienta/reasignar_ticket_instalacion",
                           params={"tenant": _tenant()},
                           json={"id_ticket": s.ticket_wisphub,
                                 "descripcion": detalle[:400]}, timeout=45)
                r.raise_for_status()
            except Exception as e:                  # noqa: BLE001
                previo = (s.fallo_integracion + " | ") if s.fallo_integracion else ""
                s.fallo_integracion = (previo + f"reasignacion: {e}")[:1000]

        s.save(update_fields=["estado", "revisada_por", "revisada_en",
                              "nota_revision", "fallo_integracion", "updated_at"])
        return Response({"estado": s.estado,
                         "revisada_en": s.revisada_en.isoformat(),
                         "fallo": s.fallo_integracion or ""})
