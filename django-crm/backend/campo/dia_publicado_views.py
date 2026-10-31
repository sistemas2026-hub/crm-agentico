"""``GET /api/campo/dia-publicado/?fecha=AAAA-MM-DD``: lo que quedo publicado
ese dia (`campo/dia_publicado.py`). Solo lee, y solo quien gestiona: muestra
el trabajo de todas las cuadrillas y el nombre de cada tecnico."""

import datetime as dt

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import dia_publicado
from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated


class CerradasView(APIView):
    """``GET /api/campo/cerradas/?desde=AAAA-MM-DD&hasta=AAAA-MM-DD``: las
    ordenes cerradas en esos dias (`campo/ordenes_cerradas.py`), para la
    pestaña Cerradas de Programacion. Solo quien gestiona; hasta 31 dias."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo import ordenes_cerradas

        _exigir_gestion(request)
        try:
            desde = dt.date.fromisoformat((request.query_params.get("desde") or "").strip())
            hasta = dt.date.fromisoformat((request.query_params.get("hasta") or "").strip())
        except ValueError:
            return Response({"detail": "Faltan las fechas (AAAA-MM-DD)."},
                            status=status.HTTP_400_BAD_REQUEST)
        if hasta < desde or (hasta - desde).days > 31:
            return Response({"detail": "El rango va de un dia a 31."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(ordenes_cerradas.del_rango(request.profile.org, desde, hasta))


class DiaPublicadoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        _exigir_gestion(request)
        crudo = (request.query_params.get("fecha") or "").strip()
        try:
            fecha = dt.date.fromisoformat(crudo)
        except ValueError:
            return Response({"detail": "Falta la fecha (AAAA-MM-DD)."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(dia_publicado.del_dia(request.profile.org, fecha))
