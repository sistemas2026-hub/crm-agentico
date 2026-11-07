"""La primera respuesta que llega por la Bandeja.

    POST /api/cases/<id>/primera-respuesta/      {"momento": "<ISO 8601>"}

POR QUE EXISTE (25/10/2026)
---------------------------
Un ticket que nace por WhatsApp se responde en la Bandeja, y esa respuesta la
guarda y la entrega el motor: este lado no se enteraba. El ticket figuraba
"sin primera respuesta" aunque una persona le hubiera escrito al cliente al
minuto. La copia que el motor deja en el ticket de WispHub tampoco vuelve: el
caso de un chat no esta atado a ese ticket por 'external_ticket_id', asi que
la importacion no le trae el hilo.

El motor llama aca cuando una persona contesta desde la Bandeja en una
conversacion con caso (nucleo/seguimiento/operativo.py::sellar_primera_respuesta).
La regla es la de siempre (cases/signals.py::sellar_primera_respuesta): la mas
temprana gana, nunca antes de que el caso exista.

QUIEN PUEDE: quien puede escribir el caso. No abre nada -- quien escribe ya
podia sellarla con cualquier comentario publico --, y es la identidad con la
que el motor ya crea y cierra estos casos.

QUE NO ACEPTA: un momento del futuro. El reloj del motor y el de aca pueden
diferir unos segundos; mas que eso es un dato roto, y sellar con el haria que
el ticket diga que lo respondieron despues de lo que de verdad fue.
"""

from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.access import assert_case_write_access, get_case_or_404
from cases.signals import sellar_primera_respuesta
from common.permissions import HasOrgContext

#: Cuanto puede adelantarse el reloj de quien llama.
TOLERANCIA_RELOJ = timedelta(minutes=2)


class CasePrimeraRespuestaView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request, pk, *args, **kwargs):
        caso = get_case_or_404(request.profile, pk)
        assert_case_write_access(request.profile, caso)

        crudo = (request.data or {}).get("momento")
        momento = parse_datetime(str(crudo)) if crudo else None
        if momento is None or timezone.is_naive(momento):
            return Response(
                {"error": True, "codigo": "MOMENTO_INVALIDO",
                 "errors": "'momento' tiene que ser una fecha ISO 8601 con zona."},
                status=status.HTTP_400_BAD_REQUEST)
        if momento > timezone.now() + TOLERANCIA_RELOJ:
            return Response(
                {"error": True, "codigo": "MOMENTO_FUTURO",
                 "errors": "'momento' no puede estar en el futuro."},
                status=status.HTTP_400_BAD_REQUEST)

        sellar_primera_respuesta(caso, momento)
        caso.refresh_from_db(fields=["first_response_at"])
        return Response(
            {"error": False,
             "first_response_at": caso.first_response_at.isoformat()
             if caso.first_response_at else None},
            status=status.HTTP_200_OK)
