"""El material del dia (`campo/material_del_dia.py`), para Programacion.

    GET  /api/campo/material-del-dia/?fecha=AAAA-MM-DD   la propuesta, no escribe
    GET  /api/campo/material-del-dia/configuracion/      kit por labor, bodega por cuadrilla
    PUT  /api/campo/material-del-dia/configuracion/      cambiar lo que viene

Solo quien gestiona: muestra el material de todas las cuadrillas y cambia de
donde carga cada una."""

import datetime as dt

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import material_del_dia as M
from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated


class MaterialDelDiaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        _exigir_gestion(request)
        try:
            fecha = dt.date.fromisoformat((request.query_params.get("fecha") or "").strip())
        except ValueError:
            return Response({"detail": "Falta la fecha (AAAA-MM-DD)."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(M.propuesta(request.profile.org, fecha))


class ConfiguracionDeMaterialView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        _exigir_gestion(request)
        return Response(M.configuracion(request.profile.org))

    def put(self, request):
        _exigir_gestion(request)
        try:
            return Response(M.guardar_configuracion(request.profile.org, request.data or {}))
        except M.ConfiguracionInvalida as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
