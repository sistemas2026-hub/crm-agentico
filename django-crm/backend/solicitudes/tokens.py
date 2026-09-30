"""El token que viaja en el link de la solicitud.

Mismo mecanismo que los links de factura del portal (`Invoice.public_token`),
y no el de CSAT: un identificador ALEATORIO, guardado en la base solo como su
SHA-256. Sin firma.

POR QUE SIN FIRMA
-----------------
La primera version lo firmaba con `TimestampSigner`, copiando CSAT. Funcionaba,
pero el link quedaba asi:

    /solicitud/2817e61d-e865-4c28-b359-abb033ece316:1x1lhH:94jNxae6mXUc848...

Casi 90 caracteres de token, para mandarle eso por WhatsApp a alguien. Y las
dos cosas que la firma aporta ya las daba la base:

  * que el token no se pueda fabricar  -> son 128 bits al azar; y aunque se
    fabricara uno, no existe la fila.
  * que venza                          -> 'expira_en' se comprueba en cada
    lectura (ver views.py::_cargar).

O sea que la firma solo agregaba 50 caracteres. Sacandola, el link queda:

    /solicitud/k7m2p9x4qw8r3ntY6bZa

De paso deja de exponer el id interno del prospecto en un enlace que se
reenvia por chat, que era la otra mitad del problema.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

# Cuanto vive el link. 30 dias: alcanza de sobra para que alguien junte la
# cedula y un recibo, y no deja enlaces validos para siempre dando vueltas en
# un WhatsApp reenviado.
SOLICITUD_TOKEN_TTL_DIAS = 30

# 22 caracteres de un alfabeto de 57 son ~128 bits.
_LARGO = 22
# Sin 'l', 'I', '1', '0' ni 'O': son los que se confunden si alguien alguna vez
# tiene que dictar uno por telefono.
_ALFABETO = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def nuevo_token() -> str:
    """Un token nuevo, sin relacion con ningun dato de la solicitud."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO))


def hash_token(token: str) -> str:
    """SHA-256 en hexadecimal. Lo unico que toca la base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tiene_forma_de_token(token: str) -> bool:
    """
    Si vale la pena siquiera ir a buscarlo.

    Evita una consulta por cada bot que prueba rutas al azar, y NO es una
    validacion de seguridad: la que decide es la fila que existe o no existe.

    Acepta TAMBIEN el formato viejo ('valor:fecha:firma'), que es mas largo.
    Los links firmados que ya estan en manos de alguien siguen guardados por
    su hash, asi que funcionan igual -- rechazarlos por la forma habria roto
    cada solicitud en curso el dia del cambio, sin ningun motivo. Cuando
    venzan (30 dias) esta rama deja de hacer falta.
    """
    if not token:
        return False
    if len(token) == _LARGO and all(c in _ALFABETO for c in token):
        return True
    return token.count(":") == 2 and len(token) <= 200


# Alias historico: hasta el 02/09/2026 esto firmaba el id del Lead. Se conserva
# el nombre para no romper a quien lo llame, pero ya no firma nada.
def firmar(identificador: str = "") -> str:
    return nuevo_token()


def vencimiento():
    return timezone.now() + timedelta(days=SOLICITUD_TOKEN_TTL_DIAS)


def link_de(token: str) -> str:
    """La URL que se le pasa a la persona."""
    from common.links import frontend_url

    return frontend_url(f"/solicitud/{token}")
