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

from django.http import HttpResponse
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
            # Si HAY expediente, no donde esta. La ruta cruda de /media/ no
            # se entrega: ese PDF trae documento de identidad, recibo y firma,
            # y se sirve autenticado (ver ExpedienteView). La pantalla arma el
            # enlace con el id, que ya viene arriba.
            "tiene_pdf": bool(s.pdf),
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


class ExpedienteView(APIView):
    """El PDF del expediente, servido con la misma llave que la bandeja.

    NO se sirve por /media/. Ese PDF trae la foto del documento de identidad,
    el recibo de servicios con la direccion, la foto del solicitante, la firma
    y las coordenadas -- "lo mas sensible que pasa por el sistema", dice el
    propio modulo que lo arma. Publicarlo bajo una ruta estatica lo deja
    legible para cualquiera que tenga el link, y ese link viaja en la respuesta
    de la bandeja, queda en el historial del navegador y en los logs del proxy.

    Encontrado el 08/09/2026: el enlace del expediente daba 404 porque
    /media/ solo se sirve con DEBUG. El arreglo obvio -- activarlo en
    produccion-- habria convertido una funcionalidad rota en una fuga de
    documentos de identidad.

    El filtro por 'org' no es decorativo: sin el, un id de solicitud de otra
    empresa se leeria igual. Es la misma frontera que ya aplica BandejaView.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request, solicitud_id: str):
        org = request.profile.org
        s = SolicitudServicio.objects.filter(org=org, id=solicitud_id).first()
        if s is None:
            return Response({"error": "No existe esa solicitud."},
                            status=http.HTTP_404_NOT_FOUND)
        if not s.pdf:
            # Distinto de "no existe la solicitud": el expediente no se armo
            # (ver 'fallo_integracion'). Decirlo con precision evita que
            # alguien busque el archivo donde nunca estuvo.
            return Response(
                {"error": "Esta solicitud no tiene expediente generado.",
                 "fallo": s.fallo_integracion or ""},
                status=http.HTTP_404_NOT_FOUND)

        try:
            s.pdf.open("rb")
            contenido = s.pdf.read()
        except Exception as e:                       # noqa: BLE001
            return Response({"error": f"No se pudo leer el expediente: {e}"},
                            status=http.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            try:
                s.pdf.close()
            except Exception:                        # noqa: BLE001
                pass

        respuesta = HttpResponse(contenido, content_type="application/pdf")
        # 'inline' y no 'attachment': quien decide sobre la solicitud lo mira,
        # no lo archiva. Descargarlo a la maquina de cada quien multiplica las
        # copias de un documento de identidad.
        respuesta["Content-Disposition"] = (
            f'inline; filename="expediente-{s.id}.pdf"')
        return respuesta


def _plano(texto: str) -> str:
    """Sin tildes, sin mayusculas, sin espacios de mas. Para comparar nombres
    escritos por una persona en un chat contra los de un formulario."""
    import unicodedata
    t = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


class BuscarSolicitudView(APIView):
    """Busca por cedula una solicitud ENVIADA, para poder cancelarla.

    DEVUELVE EL NOMBRE ENMASCARADO, y eso es el nucleo de la seguridad de todo
    este flujo. Una cedula no es un secreto -- es un dato bastante publico-- y
    con ella sola cualquiera podria cancelarle la instalacion a otro. La
    proteccion es que el cliente CONFIRME el nombre.

    Si aca se devolviera el nombre completo, el agente podria "confirmarlo"
    solo, sin preguntarle nada a nadie: veria el dato y lo daria por
    confirmado. Enmascarado no puede -- tiene que pedirselo a la persona, y la
    comparacion la hace el codigo al cancelar (ver CancelarSolicitudView).

    Mismo espiritu que verificar_identidad_por_cedula + confirmar_identidad,
    que es el patron de dos pasos que este proyecto ya tiene probado.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        org = request.profile.org
        documento = str(request.data.get("numero_documento") or "").strip()
        if not documento:
            return Response({"error": "Falta 'numero_documento'."},
                            status=http.HTTP_400_BAD_REQUEST)

        s = (SolicitudServicio.objects
             .filter(org=org, numero_documento=documento,
                     estado=SolicitudServicio.ENVIADA)
             .order_by("-enviada_en").first())
        if s is None:
            # Se responde lo mismo exista o no la cedula en otra solicitud: si
            # el mensaje distinguiera "no hay ninguna" de "hay una pero ya esta
            # aprobada", esta ruta serviria para averiguar por quien tiene
            # tramite abierto probando cedulas.
            return Response({"encontrada": False,
                             "instruccion_interna":
                                 "No hay ninguna solicitud enviada con esa "
                                 "cedula. Puede ser que la haya enviado con "
                                 "otro documento, o que todavia no complete el "
                                 "formulario -- en ese caso no hay nada que "
                                 "cancelar aca: toma la informacion y cerra el "
                                 "caso como siempre."})

        partes = _plano(s.nombre_completo).split()
        pista = " ".join(p[0].upper() + "*" * (len(p) - 1) for p in partes)
        return Response({
            "encontrada": True,
            "estado": s.estado,
            "plan": s.plan_interesado,
            "barrio": s.barrio,
            "nombre_pista": pista,
            "instruccion_interna":
                f"Hay una solicitud enviada. NO le leas la pista '{pista}' como "
                "si fuera el nombre: pedile que te diga el nombre completo con "
                "el que la registro, y pasalo tal cual en 'nombre_confirmado' "
                "al cancelar. Si no coincide, la cancelacion se rechaza.",
        })


class CancelarSolicitudView(APIView):
    """Cancela una solicitud ENVIADA. El nombre se verifica ACA, no en el prompt.

    Tres candados, y el del medio es el que importa:

      * solo estado ENVIADA -- una APROBADA ya tiene equipo asignado y una
        instalacion en curso; eso lo decide una persona, no esta ruta.
      * el nombre confirmado tiene que coincidir con el de la solicitud. Sin
        esta comparacion en codigo, "confirmar el nombre" seria una
        instruccion del prompt, y este proyecto ya midio lo que valen las
        instrucciones que nadie hace cumplir.
      * filtro por org, como toda consulta.

    El motivo se guarda LITERAL. Lo pidio asi el negocio y tiene razon: leido
    en conjunto dice si las ventas se caen por precio, por demora o por la
    competencia, y un resumen perderia justo eso.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        org = request.profile.org
        documento = str(request.data.get("numero_documento") or "").strip()
        confirmado = str(request.data.get("nombre_confirmado") or "").strip()
        motivo = str(request.data.get("motivo") or "").strip()
        faltan = [c for c, v in (("numero_documento", documento),
                                 ("nombre_confirmado", confirmado),
                                 ("motivo", motivo)) if not v]
        if faltan:
            return Response({"error": f"Faltan datos: {', '.join(faltan)}."},
                            status=http.HTTP_400_BAD_REQUEST)

        s = (SolicitudServicio.objects
             .filter(org=org, numero_documento=documento,
                     estado=SolicitudServicio.ENVIADA)
             .order_by("-enviada_en").first())
        if s is None:
            return Response({"error": "No hay ninguna solicitud enviada con esa cedula."},
                            status=http.HTTP_404_NOT_FOUND)

        if _plano(confirmado) != _plano(s.nombre_completo):
            return Response(
                {"error": "El nombre no coincide con el de la solicitud.",
                 "instruccion_interna":
                     "No canceles nada. Pedile de nuevo el nombre completo tal "
                     "cual lo registro. Si insiste y no coincide, no es su "
                     "solicitud: pasalo con un colaborador humano."},
                status=http.HTTP_409_CONFLICT)

        s.estado = SolicitudServicio.CANCELADA
        s.motivo_cancelacion = motivo
        s.cancelada_en = timezone.now()
        s.save(update_fields=["estado", "motivo_cancelacion", "cancelada_en",
                              "updated_at"])

        # El ticket de WispHub queda vivo si nadie lo cierra, y alguien saldria
        # a instalar. Va DESPUES de guardar y fuera de la transaccion, mismo
        # criterio que el resto del modulo: si el tercero no responde, la
        # cancelacion no se deshace -- queda anotada para reintentar.
        fallo = ""
        if s.ticket_wisphub:
            from solicitudes.entrega import cerrar_ticket_wisphub
            try:
                cerrar_ticket_wisphub(s, motivo)
            except Exception as e:                   # noqa: BLE001
                fallo = f"cierre ticket: {type(e).__name__}: {e}"
                previo = (s.fallo_integracion + " | ") if s.fallo_integracion else ""
                s.fallo_integracion = (previo + fallo)[:1000]
                s.save(update_fields=["fallo_integracion", "updated_at"])

        return Response({"estado": s.estado,
                         "cancelada_en": s.cancelada_en.isoformat(),
                         "ticket_wisphub": s.ticket_wisphub,
                         "fallo": fallo})
