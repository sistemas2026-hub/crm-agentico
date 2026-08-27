"""El token que viaja en el link de la solicitud.

Mismo mecanismo que el de CSAT (`cases/tasks.py`), y a proposito: es el unico
patron de pagina publica anonima que ya esta probado en este proyecto, y
copiarlo es mas seguro que inventar otro. Tres piezas:

1. Un ``TimestampSigner`` con sal propia. La firma vence sola, asi que un link
   viejo deja de servir sin que nadie tenga que salir a limpiarlo.
2. En la base se guarda el SHA-256 del token, nunca el token. Una filtracion
   de la base no entrega links validos.
3. El hash se registra ademas en ``PortalAccessToken`` (``common.portal_tokens``),
   que es como una peticion anonima -sin JWT, sin sesion- averigua a que
   organizacion pertenece la fila antes de poder leerla: bajo RLS con contexto
   vacio esa fila no se ve.

La sal es distinta de la de CSAT y no es un detalle: con la misma sal, un token
de encuesta valdria como token de solicitud y al reves.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.core.signing import TimestampSigner
from django.utils import timezone

# Cuanto vive el link. 30 dias, igual que CSAT: alcanza de sobra para que
# alguien junte la cedula y un recibo, y no deja links validos para siempre
# dando vueltas en un WhatsApp reenviado.
SOLICITUD_TOKEN_TTL_DIAS = 30

_SAL = "solicitudes.servicio.v1"


def solicitud_signer() -> TimestampSigner:
    """El firmador, compartido por quien crea el link y quien lo verifica."""
    return TimestampSigner(salt=_SAL)


def hash_token(token: str) -> str:
    """SHA-256 en hexadecimal. Lo unico que toca la base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def firmar(identificador: str) -> str:
    """Token firmado a partir de un identificador (el id del Lead, o un uuid)."""
    return solicitud_signer().sign(str(identificador))


def vencimiento():
    return timezone.now() + timedelta(days=SOLICITUD_TOKEN_TTL_DIAS)


def link_de(token: str) -> str:
    """La URL que se le pasa a la persona."""
    from common.links import frontend_url

    return frontend_url(f"/solicitud/{token}")
