"""Mentions in a Bandeja internal note (30/10/2026).

``POST /api/notifications/mencion-conversacion/`` with
``{conversation_id, texto}``.

The conversation lives in the assistant (motor), not in Django, so there is no
model to hang a comment hook on: the SvelteKit server calls this right after
the motor saved the note. It reuses the ticket mention rules
(``cases.notifications``): ``@name`` is the local part of an active profile's
email in the caller's org, the author is never notified of their own mention,
and the same person is not notified twice for the same conversation within a
minute.

What it writes: one ``Notification`` per mentioned profile, verb
``conversacion.mencion``, link ``/conversaciones/<uuid>``. The excerpt is the
note text, truncated; recipients are staff of the same org, the same people
who can already read the note.

Rules:
    - The actor and the org come from the session (``request.profile``),
      never from the body.
    - ``conversation_id`` must be a UUID; the link is built from it, nothing
      from the body is copied into ``link``.
"""

import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.notifications import (
    EXCERPT_LENGTH,
    MENTION_RATE_LIMIT_SECONDS,
    parse_mentions,
    resolve_mentions,
)
from common.models import Notification

VERB = "conversacion.mencion"


def _excerpt(texto: str) -> str:
    texto = (texto or "").strip()
    if len(texto) <= EXCERPT_LENGTH:
        return texto
    return texto[: EXCERPT_LENGTH - 1].rstrip() + "…"


class MencionConversacionView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        actor = request.profile
        try:
            conversation_id = uuid.UUID(str(request.data.get("conversation_id") or ""))
        except (ValueError, TypeError):
            return Response(
                {"error": "conversation_id inválido"}, status=status.HTTP_400_BAD_REQUEST
            )
        texto = str(request.data.get("texto") or "")

        corte = timezone.now() - timedelta(seconds=MENTION_RATE_LIMIT_SECONDS)
        avisados = []
        for perfil in resolve_mentions(parse_mentions(texto), actor.org_id):
            if perfil.id == actor.id:
                continue
            reciente = Notification.objects.filter(
                recipient=perfil, verb=VERB, entity_id=conversation_id, created_at__gte=corte
            ).exists()
            if reciente:
                continue
            Notification.objects.create(
                org=actor.org,
                recipient=perfil,
                verb=VERB,
                actor=actor,
                entity_type="Conversacion",
                entity_id=conversation_id,
                entity_name="Conversación de la Bandeja",
                link=f"/conversaciones/{conversation_id}",
                data={"comment_excerpt": _excerpt(texto)},
            )
            avisados.append(str(perfil.id))
        return Response({"avisados": len(avisados)}, status=status.HTTP_200_OK)
