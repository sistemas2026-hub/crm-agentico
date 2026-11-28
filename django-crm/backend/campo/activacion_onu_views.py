# -*- coding: utf-8 -*-
"""
    GET  /api/campo/trabajos/<id>/onu/?serial=   como esta la ONU (solo lee) y el ultimo pedido
    POST /api/campo/trabajos/<id>/onu/activar/   pedir la activacion {serial, zona}

La ve y la pide el TECNICO de la orden (la misma puerta que el contrato y las IP
libres). Ver campo/activacion_onu.py.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated


class OnuDeLaOrdenView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo import activacion_onu as A
        from campo.contrato import configuracion_de
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        ultima = A.ultima(orden)
        cuerpo = {"encendido": bool(configuracion_de(orden.org).get("activar_onu")),
                  "ultima": ultima.como_dict() if ultima else None, "onu": None}
        serial = request.query_params.get("serial")
        if serial:
            try:
                cuerpo["onu"] = A.buscar(orden, serial)
            except A.NoSePuedeActivar as e:
                cuerpo["error"] = str(e)
        return Response(cuerpo)


class ActivarOnuView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo import activacion_onu as A
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        datos = request.data or {}
        try:
            a = A.pedir(orden, request.profile, serial=datos.get("serial"), zona=datos.get("zona"))
        except A.NoSePuedeActivar as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"activacion": a.como_dict()}, status=status.HTTP_202_ACCEPTED)
