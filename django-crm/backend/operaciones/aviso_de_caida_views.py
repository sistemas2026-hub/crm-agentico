"""
"FALLAS DE RED": las caidas de PON vivas y el aviso a sus clientes (30/10/2026).

Hasta hoy ninguna pantalla mostraba las situaciones de red: solo las veia el
Supervisor por chat. Para que una PERSONA apruebe avisarle una caida a sus
clientes (PRD §8.17) tiene que poder verla. Ver operaciones/aviso_de_caida.py.

Solo gestion (EsJefeDeOperaciones), y una situacion de otra empresa es 404.
"""
from rest_framework import status as http
from rest_framework.response import Response
from rest_framework.views import APIView

from operaciones import aviso_de_caida as A
from operaciones.aviso_de_caida_modelos import AvisoDeCaida
from operaciones.permissions import EsJefeDeOperaciones
from operaciones.situaciones_modelos import SituacionOperativa, TipoAfectado

S = SituacionOperativa

#: Codigo -> http. Lo que no esta aca es un 400.
HTTP_DE = {"YA_APROBADO": http.HTTP_409_CONFLICT, "CARGANDO": http.HTTP_202_ACCEPTED,
           "MOTOR_NO_CONTESTA": http.HTTP_502_BAD_GATEWAY,
           "NO_CONFIGURADO": http.HTTP_503_SERVICE_UNAVAILABLE}


def _fila(s) -> dict:
    pon = next((a for a in s.afectados.all() if a.tipo == TipoAfectado.PON), None)
    datos = (pon.datos or {}) if pon else {}
    try:
        aviso = s.aviso_de_caida
    except AvisoDeCaida.DoesNotExist:
        aviso = None
    return {"id": str(s.id), "codigo": s.codigo, "titulo": s.titulo, "estado": s.estado,
            "riesgo": s.riesgo, "detectada_en": s.detectada_en.isoformat(),
            "puerto": pon.identificador if pon else "", "caja": pon.etiqueta if pon else "",
            "equipos": datos.get("afectados"), "tipo_alerta": datos.get("tipo_alerta") or "",
            "por_que_no": A.por_que_no(s), "aviso": A.resumen(aviso)}


class FallasDeRedView(APIView):
    """GET: las caidas de PON vivas de la empresa, con su aviso si lo hay."""

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        #  Las vivas, y las que tienen un aviso en curso o que termino hace
        #  menos de un dia: el "ya volvio" sale cuando la situacion YA no esta
        #  viva, y sin esto nadie veria su avance ni por que se detuvo.
        reciente = timezone.now() - timedelta(hours=24)
        fallas = (S.objects.filter(org=request.org, tipo=S.AFECTACION_PON)
                  .filter(Q(estado__in=A.VIVOS)
                          | Q(aviso_de_caida__estado=AvisoDeCaida.EN_CURSO)
                          | Q(aviso_de_caida__terminado_en__gte=reciente))
                  .prefetch_related("afectados").select_related("aviso_de_caida__aprobado_por__user")
                  .distinct().order_by("-detectada_en"))
        return Response({"fallas": [_fila(s) for s in fallas]})


class AvisoDeCaidaView(APIView):
    """POST {accion: 'preparar' | 'aprobar'} sobre una caida."""

    permission_classes = [EsJefeDeOperaciones]

    def post(self, request, situacion_id):
        s = (S.objects.filter(id=situacion_id, org=request.org)
             .prefetch_related("afectados").first())
        if s is None:
            return Response({"error": "NO_EXISTE"}, status=http.HTTP_404_NOT_FOUND)
        accion = (request.data or {}).get("accion") if isinstance(request.data, dict) else None
        try:
            if accion == "preparar":
                return Response(A.vista_previa(s))
            if accion == "aprobar":
                aviso = A.aprobar(s, getattr(request, "profile", None))
                return Response({"aviso": A.resumen(aviso)}, status=http.HTTP_201_CREATED)
        except A.NoAvisable as e:
            return Response({"error": e.codigo}, status=HTTP_DE.get(e.codigo, http.HTTP_400_BAD_REQUEST))
        return Response({"error": "ACCION_DESCONOCIDA"}, status=http.HTTP_400_BAD_REQUEST)
