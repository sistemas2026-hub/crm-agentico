# -*- coding: utf-8 -*-
"""
================================================================================
 REGISTRO  --  lo que el motor escribe en su log, sin datos de clientes
================================================================================

    from nucleo.observabilidad.registro import registrar, ref_sesion, ref_proveedor

    registrar("whatsapp", "fallo al atender un mensaje",
              sesion=ref_sesion(de), wamid=ref_proveedor(wamid), error=e)
    -> [whatsapp] fallo al atender un mensaje sesion=ses-3f9a0c1d2b7e wamid=prv-81c2... error=OperationalError sqlstate=57P01 donde=persistencia/db.py:812

Por que existe (D20, 16/09/2026)
--------------------------------
El log del motor persiste -- lo guarda Docker, lo lee cualquiera con acceso al
servidor -- y durante meses cada mensaje entrante de WhatsApp escribia ahi el
telefono completo del cliente, el wamid entero y, en los errores, el texto
crudo de la excepcion. Ese texto es lo mas traicionero: un error de PostgreSQL
trae el valor que fallo ('Key (usuario_externo)=(573001234567) already exists',
'invalid input syntax for type uuid: "..."'), uno de requests trae la URL, y
nadie lo ve al escribir el print porque el valor aparece recien cuando falla.

Se habian corregido prints de a uno (cd7c4f5) y quedaban decenas. Parchear
linea por linea deja la proxima regresion a un f-string de distancia. Por eso
hay UNA puerta:

  1. el evento es TEXTO FIJO. Nada se interpola en el mensaje: lo que varia va
     en campos con nombre (lo exige tests/test_registro_sin_pii.py sobre el
     codigo, no solo sobre la salida).
  2. cada campo pasa por _valor_seguro. Un texto con pinta de telefono, de
     wamid, con espacios o largo se reemplaza por <redactado>, aunque quien
     llamo se haya equivocado de variable.
  3. una excepcion nunca se imprime con str(e): sale su tipo, el sqlstate o el
     codigo HTTP si los tiene, y DONDE se lanzo (archivo:linea). Con eso se
     diagnostica; con el texto se filtran datos.

Correlacion sin PII
-------------------
Para seguir un caso por el log se usan los identificadores INTERNOS
(conversation_id, message_id, tenant): son UUIDs y slugs, no dicen nada de la
persona. Cuando no hay uno interno -- al principio del webhook, antes de que
exista la conversacion -- se usa:

  ref_sesion(id)      HMAC-SHA256 con una clave del servidor. NO un sha256
                      plano: un telefono tiene poca entropia (unos 10^10
                      numeros posibles en Colombia) y su hash plano se revierte
                      probandolos todos en minutos. Con HMAC, sin la clave no.
  ref_proveedor(id)   sha256 corto. Para identificadores que emite Meta
                      (wamid, media_id): son aleatorios y largos, asi que su
                      huella no se puede revertir por enumeracion, y se puede
                      recalcular en SQL para ubicar la fila:
                        left(encode(sha256(convert_to(wamid,'UTF8')),'hex'),12)

La clave del HMAC se DERIVA (HKDF, contexto 'dexter/log-ref/v1') de
REGISTRO_CLAVE_HMAC si existe, o si no de SECRETOS_CLAVE_MAESTRA: ninguna de
las dos se usa directamente. Sin ninguna se usa una clave aleatoria del
proceso: la referencia sigue siendo irreversible y sirve para correlacionar
dentro de esa vida del proceso, y el prefijo 'sesx-' avisa que no es estable
entre reinicios. Nunca se cae a un hash plano, y nunca se deja de atender por
falta de clave: es una degradacion del log, no del servicio.

Las referencias son SOLO para buscar en el log. ref_proveedor en particular es
una huella corta que puede colisionar: nunca se usa como clave de base, como
identidad de negocio ni para autorizar nada.
================================================================================
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sys
import traceback
from pathlib import Path

REDACTADO = "<redactado>"

# Un texto de campo pasa tal cual solo si es corto, sin espacios y de
# caracteres de identificador: estados, codigos, slugs, nombres de herramienta,
# UUIDs. Todo lo demas es "texto libre" y en un log no se puede saber de quien.
_IDENTIFICADOR = re.compile(r"^[A-Za-z0-9_.:/-]{1,64}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Siete digitos seguidos ya pueden ser un telefono local o una cedula.
_DIGITOS = re.compile(r"\d{7,}")
_REFERENCIA = re.compile(r"^(ses|sesx|prv)-[0-9a-f]{12}$")

_RAIZ_NUCLEO = Path(__file__).resolve().parent.parent


class Referencia(str):
    """Un valor ya anonimizado por este modulo: pasa sin volver a revisarse."""


# Separacion de dominio. La clave con que se firman las referencias del log NO
# es la clave maestra ni la variable dedicada tal cual: es una derivada HKDF
# (RFC 5869) con este contexto. Asi la misma maestra que descifra credenciales
# no se usa, directamente, para una segunda finalidad; y si el formato de las
# referencias cambia, se sube la version del contexto y las viejas no casan
# con las nuevas por accidente.
CONTEXTO_CLAVE = b"dexter/log-ref/v1"
_SAL_HKDF = b"dexter/observabilidad/registro"


def hkdf_sha256(ikm: bytes, sal: bytes, info: bytes, largo: int = 32) -> bytes:
    """HKDF-SHA256, RFC 5869: extraer y expandir. Solo biblioteca estandar."""
    prk = hmac.new(sal or bytes(32), ikm, hashlib.sha256).digest()
    salida, bloque, n = b"", b"", 1
    while len(salida) < largo:
        bloque = hmac.new(prk, bloque + info + bytes([n]), hashlib.sha256).digest()
        salida += bloque
        n += 1
    return salida[:largo]


def _clave() -> tuple[bytes, str]:
    origen = os.environ.get("REGISTRO_CLAVE_HMAC") or os.environ.get("SECRETOS_CLAVE_MAESTRA")
    if origen:
        return hkdf_sha256(origen.encode(), _SAL_HKDF, CONTEXTO_CLAVE), "ses"
    return _CLAVE_DEL_PROCESO, "sesx"


_CLAVE_DEL_PROCESO = secrets.token_bytes(32)


def ref_sesion(valor) -> Referencia | None:
    """Referencia estable e irreversible de un identificador de PERSONA
    (telefono, BSUID, id_sesion). HMAC, nunca hash plano."""
    if not valor:
        return None
    clave, prefijo = _clave()
    return Referencia(f"{prefijo}-" + hmac.new(clave, str(valor).encode("utf-8"),
                                               hashlib.sha256).hexdigest()[:12])


def ref_proveedor(valor) -> Referencia | None:
    """Huella corta de un identificador ALEATORIO del proveedor (wamid,
    media_id). Recalculable en SQL; ver el docstring del modulo.

    SOLO observabilidad: 48 bits pueden colisionar, y eso no importa mientras
    nadie la use como clave, identidad o permiso. Para ids de poca entropia
    (secuenciales, telefonos) va ref_sesion, que es HMAC."""
    if not valor:
        return None
    return Referencia("prv-" + hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:12])


def id_interno(valor) -> str | None:
    """Un id interno (UUID, entero) como texto, o None. Para correlacionar."""
    return None if valor is None or valor == "" else str(valor)


def _donde(e: BaseException) -> str | None:
    """archivo:linea del ultimo cuadro de la traza que es codigo del nucleo."""
    ultimo = None
    for cuadro in traceback.extract_tb(e.__traceback__):
        try:
            relativo = Path(cuadro.filename).resolve().relative_to(_RAIZ_NUCLEO)
        except (ValueError, OSError):
            continue
        ultimo = f"{relativo.as_posix()}:{cuadro.lineno}"
    return ultimo


def error_seguro(e: BaseException) -> dict:
    """Lo que se puede decir de una excepcion sin su texto."""
    datos: dict = {"error": type(e).__name__}
    sqlstate = getattr(e, "sqlstate", None)
    if isinstance(sqlstate, str):
        datos["sqlstate"] = sqlstate
    diag = getattr(e, "diag", None)
    for campo in ("constraint_name", "table_name"):
        valor = getattr(diag, campo, None) if diag is not None else None
        if isinstance(valor, str):
            datos[campo] = valor
    for campo in ("codigo", "http_status", "operacion"):
        valor = getattr(e, campo, None)
        if isinstance(valor, (int, str)) and not isinstance(valor, bool):
            datos[campo] = valor
    respuesta = getattr(e, "response", None)
    status = getattr(respuesta, "status_code", None)
    if isinstance(status, int) and "http_status" not in datos:
        datos["http_status"] = status
    donde = _donde(e)
    if donde:
        datos["donde"] = donde
    return datos


def _valor_seguro(valor) -> str:
    if valor is None or isinstance(valor, (bool, int, float)):
        return str(valor)
    if isinstance(valor, Referencia):
        return str(valor) if _REFERENCIA.match(valor) else REDACTADO
    if isinstance(valor, str):
        if _UUID.match(valor):
            return valor
        if (not _IDENTIFICADOR.match(valor) or _DIGITOS.search(valor)
                or "://" in valor or valor.lower().startswith("wamid")):
            return REDACTADO
        return valor
    if isinstance(valor, (list, tuple, set, frozenset)):
        elementos = sorted(valor, key=str) if isinstance(valor, (set, frozenset)) else valor
        return "[" + ",".join(_valor_seguro(v) for v in elementos) + "]"
    if isinstance(valor, dict):
        return "{" + ",".join(f"{_valor_seguro(k)}:{_valor_seguro(v)}"
                              for k, v in valor.items()) + "}"
    # Cualquier otro objeto se describe por su tipo: su repr puede traer datos.
    return f"<{type(valor).__name__}>"


# 'componente' y 'evento' son SOLO posicionales (la '/'): asi un campo que se
# llame 'evento' o 'componente' es un campo mas y no choca con el parametro.
# Sin esto, _contar_relevo(evento=...) tiraba TypeError justo dentro de la
# compuerta que tiene que fallar cerrado.
def formatear(componente: str, evento: str, /, **campos) -> str:
    partes = [f"[{componente}] {evento}"]
    for clave, valor in campos.items():
        if isinstance(valor, BaseException):
            for k, v in error_seguro(valor).items():
                partes.append(f"{k}={_valor_seguro(v)}")
            continue
        partes.append(f"{clave}={_valor_seguro(valor)}")
    return " ".join(partes)


def registrar(componente: str, evento: str, /, **campos) -> None:
    """
    Escribe una linea de log. 'evento' es texto fijo; lo variable, en campos.

    NUNCA LEVANTA (D26). Se llama desde adentro de los 'except' de caminos que
    tienen que fallar cerrado -- la compuerta del relevo, el webhook, la
    entrega--, y un log que revienta ahi cambia el flujo por culpa de la
    observabilidad. Si un valor no se puede formatear (un __str__ que tira, un
    set que no se puede ordenar) sale una linea fija con el componente y el
    tipo del problema; si ni siquiera se puede escribir (stdout cerrado), se
    pierde la linea y el flujo sigue igual.
    """
    try:
        linea = formatear(componente, evento, **campos)
    except Exception as e:                                    # noqa: BLE001
        linea = (f"[registro] no se pudo formatear una linea de "
                 f"'{_valor_seguro(componente)}' ({type(e).__name__})")
    try:
        print(linea, file=sys.stdout, flush=True)
    except Exception:                                         # noqa: BLE001
        pass
