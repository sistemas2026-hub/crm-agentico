# -*- coding: utf-8 -*-
"""El dinero de los tecnicos, para la oficina (26/11/2026). Ver `campo/dinero.py`.

    GET  /api/campo/dinero/            cuanto tiene cada tecnico por entregar
    POST /api/campo/dinero/recibir/    {tecnico_id, ordenes: [{orden_id, monto}]}

Solo gestion: recibir dinero es la oficina firmando que lo conto.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated


class DineroDeLosTecnicosView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo.dinero import por_tecnico

        _exigir_gestion(request)
        return Response(por_tecnico(request.profile.org))


class RecibirDineroView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        from campo.dinero import DineroCambio, DineroInvalido, por_tecnico, recibir

        _exigir_gestion(request)
        datos = request.data if isinstance(request.data, dict) else {}
        try:
            entregas = recibir(request.profile.org, request.profile,
                               str(datos.get("tecnico_id") or ""), datos.get("ordenes"))
        except DineroInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DineroCambio as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"recibidas": len(entregas), **por_tecnico(request.profile.org)})
