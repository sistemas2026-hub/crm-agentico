"""La recepcion del kit en la app (`campo/recepcion_del_kit.py`).

    GET  /api/campo/kit/recepcion/                     lo que tiene por confirmar y por escanear
    POST /api/campo/kit/recepcion/<id>/confirmar/       {"conforme": true} o {"conforme": false,
                                                         "diferencias": [{codigo, recibido, motivo}]}
    POST /api/campo/kit/recepcion/escanear/            {"serie": "..."}

Cualquier sesion de campo, y solo sobre lo suyo: cada funcion recibe la persona
de la sesion."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import recepcion_del_kit as R
from campo.permissions import IsCampoAuthenticated


def _rechazo(e):
    return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RecepcionView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        return Response(R.pendiente_de(request.profile, request.profile.org))


class ConfirmarEntregaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        datos = request.data or {}
        try:
            return Response(R.confirmar(
                request.profile, request.profile.org, pk,
                conforme=bool(datos.get("conforme")),
                diferencias=datos.get("diferencias") or []))
        except R.RecepcionInvalida as e:
            return _rechazo(e)


class EscanearEquipoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        try:
            return Response(R.escanear(request.profile, request.profile.org,
                                       (request.data or {}).get("serie")))
        except R.RecepcionInvalida as e:
            return _rechazo(e)
