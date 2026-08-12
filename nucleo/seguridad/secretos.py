# -*- coding: utf-8 -*-
"""
================================================================================
 SECRETOS  -  resolver el NOMBRE de una credencial a su valor, por empresa
================================================================================

Por que existe
--------------
La configuracion nunca guarda credenciales: guarda su nombre
('auth_ref: WISPHUB_API_KEY', 'token_ref: WHATSAPP_TOKEN'), y el validador
rechaza el archivo si detecta un valor con pinta de secreto (ver
nucleo/config/schema.py y ARQUITECTURA.md, "Variables de entorno").

Hasta ahora ese nombre se resolvia contra os.environ. Eso alcanza mientras haya
UN tenant: un proceso tiene una sola tanda de variables. Deja de alcanzar en
cuanto entran dos ISPs, porque cada uno trae su propia cuenta de WhatsApp
Business y su propia clave de WispHub -- y levantar un motor por empresa es lo
que la arquitectura multi-tenant existe para evitar.

ORDEN DE RESOLUCION: BASE PRIMERO, ENTORNO DESPUES
--------------------------------------------------
    1. asistente.tenant_secrets del tenant  (cifrado)
    2. os.environ                            (respaldo)

El respaldo no es transicional: es deliberado y se queda.

  - Lo que ya funciona por .env sigue funcionando sin migrar nada. La
    migracion es opcional y por secreto, no un corte.
  - Hay credenciales que NO deberian ser por tenant: la clave de la API del
    modelo es de la plataforma, no de la empresa. Esas se quedan en el entorno
    y este orden las deja ahi sin caso especial.
  - Un tenant puede pisar un valor de plataforma con el suyo propio, que es lo
    que hace falta el dia que un ISP traiga su propia cuenta de DeepSeek.

CIFRADO
-------
Fernet (AES-128-CBC + HMAC, de 'cryptography') con una clave maestra que vive
en SECRETOS_CLAVE_MAESTRA, en el entorno del servidor. Queda como la unica
credencial que sigue en el .env, y por diseño: en algun punto de la cadena algo
tiene que estar en claro, y es preferible que sea una sola llave rotable a que
sean N tokens de N empresas.

Que protege y que no:
  SI   un volcado de la base, una copia de seguridad filtrada, o alguien
       mirando tablas con el rol 'postgres' (que tiene BYPASSRLS, ver
       ARQUITECTURA.md).
  NO   a quien tenga a la vez la base Y el entorno del motor. Eso ya es acceso
       al servidor, y ahi el cifrado en reposo no es la defensa.

FALLA CERRADO
-------------
Cualquier problema al leer o descifrar levanta ErrorSecreto: nunca se devuelve
None silenciosamente y nunca se cae al entorno para tapar un fallo de la base.
Un secreto que no se puede resolver tiene que detener la operacion, no dejarla
seguir sin autenticacion -- es el mismo criterio de dos capas del PRD §7.4.
================================================================================
"""

from __future__ import annotations

import os

_CLAVE_ENV = "SECRETOS_CLAVE_MAESTRA"

# tenant -> {nombre: valor en claro}. La alternativa es una consulta y un
# descifrado por cada llamada a una herramienta, en el camino caliente del
# turno. Se vacia con olvidar(), igual que el cache de configuracion de
# nucleo/canales/api.py, para que un cambio desde la interfaz se vea en el
# turno siguiente sin reiniciar el proceso.
_CACHE: dict[str, dict[str, str]] = {}


class ErrorSecreto(RuntimeError):
    """No se pudo resolver una credencial. Nunca se sigue sin ella."""


def _cifrador():
    """El Fernet de la clave maestra. Import perezoso: el motor arranca aunque
    'cryptography' no este instalado, y solo falla cuando alguien pide un
    secreto cifrado -- mismo criterio que el cliente de OpenAI en
    requirements.txt."""
    clave = os.environ.get(_CLAVE_ENV)
    if not clave:
        raise ErrorSecreto(
            f"Falta '{_CLAVE_ENV}' en el entorno del motor. Es la clave que "
            f"descifra las credenciales por empresa. Generar una con: "
            f"py -3.13 -c \"from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())\"")
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise ErrorSecreto(
            "Falta el paquete 'cryptography' (pip install -r requirements.txt)."
        ) from e
    try:
        return Fernet(clave.encode() if isinstance(clave, str) else clave)
    except Exception as e:
        raise ErrorSecreto(
            f"'{_CLAVE_ENV}' no es una clave Fernet valida: {type(e).__name__}. "
            f"Tiene que ser la salida de Fernet.generate_key()."
        ) from e


def _cargar(tenant: str) -> dict[str, str]:
    """Todos los secretos del tenant, descifrados. Un tenant sin fila en
    tenant_secrets devuelve {} -- no es un error: significa que todavia usa el
    entorno para todo."""
    from nucleo.persistencia import db

    try:
        with db.sesion(tenant) as (cur, _org):
            cur.execute(
                "select nombre, valor_cifrado from asistente.tenant_secrets")
            filas = cur.fetchall()
    except Exception as e:
        raise ErrorSecreto(
            f"No se pudieron leer los secretos de '{tenant}': "
            f"{type(e).__name__}: {e}") from e

    if not filas:
        return {}

    f = _cifrador()
    salida = {}
    for fila in filas:
        nombre = fila["nombre"] if isinstance(fila, dict) else fila[0]
        cifrado = fila["valor_cifrado"] if isinstance(fila, dict) else fila[1]
        try:
            salida[nombre] = f.decrypt(cifrado.encode()).decode()
        except Exception as e:
            # Se nombra CUAL fallo: con varios secretos, "no se pudo descifrar"
            # a secas no dice cual hay que volver a cargar. El valor no se
            # incluye nunca en el mensaje.
            raise ErrorSecreto(
                f"No se pudo descifrar '{nombre}' de '{tenant}' "
                f"({type(e).__name__}). Suele significar que la clave maestra "
                f"cambio: hay que volver a cargar ese secreto.") from e
    return salida


def obtener(tenant: str | None, nombre: str) -> str | None:
    """
    El valor de la credencial 'nombre' para 'tenant'. None si no esta en
    ninguno de los dos lados -- quien llama decide si eso es un error (lo es
    casi siempre) y con que mensaje.

    'tenant' puede ser None para lo que no pertenece a ninguna empresa (una
    utilidad de cli/, un arranque): en ese caso solo se mira el entorno.
    """
    if tenant:
        if tenant not in _CACHE:
            _CACHE[tenant] = _cargar(tenant)
        valor = _CACHE[tenant].get(nombre)
        if valor:
            return valor
    return os.environ.get(nombre)


def guardar(tenant: str, nombre: str, valor: str,
            descripcion: str | None = None) -> None:
    """
    Cifra y escribe un secreto del tenant. Es lo que va a llamar la pantalla de
    ajustes cuando el cliente cargue su token.

    'pista' guarda los ultimos 4 caracteres en claro para que la interfaz pueda
    mostrar "...a3f9" y el operador confirme que cargo el correcto sin tener que
    descifrar ni mostrar el secreto entero.
    """
    if not valor:
        raise ErrorSecreto(f"El valor de '{nombre}' esta vacio.")

    from nucleo.persistencia import db

    cifrado = _cifrador().encrypt(valor.encode()).decode()
    pista = valor[-4:] if len(valor) >= 8 else None

    with db.sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.tenant_secrets
                 (organization_id, nombre, valor_cifrado, descripcion, pista)
               values (%s, %s, %s, %s, %s)
               on conflict (organization_id, nombre) do update
                 set valor_cifrado = excluded.valor_cifrado,
                     descripcion   = coalesce(excluded.descripcion,
                                              asistente.tenant_secrets.descripcion),
                     pista         = excluded.pista,
                     actualizado_en = now()""",
            (org, nombre, cifrado, descripcion, pista))

    olvidar(tenant)


def listar(tenant: str) -> list[dict]:
    """Que secretos tiene cargados el tenant, SIN sus valores. Para la pantalla
    de ajustes: nombre, para que sirve, cuando se cargo y los ultimos 4
    caracteres."""
    from nucleo.persistencia import db

    with db.sesion(tenant) as (cur, _org):
        cur.execute(
            """select nombre, descripcion, pista, actualizado_en
               from asistente.tenant_secrets order by nombre""")
        return [dict(f) for f in cur.fetchall()]


def borrar(tenant: str, nombre: str) -> bool:
    """Saca un secreto del tenant. Vuelve a resolverse contra el entorno, si
    ahi existe."""
    from nucleo.persistencia import db

    with db.sesion(tenant) as (cur, org):
        cur.execute(
            """delete from asistente.tenant_secrets
               where organization_id = %s and nombre = %s""", (org, nombre))
        borrado = cur.rowcount > 0

    olvidar(tenant)
    return borrado


def olvidar(tenant: str | None = None) -> None:
    """Descarta lo cacheado para que la proxima resolucion relea de la base.
    Sin argumento, vacia todo."""
    if tenant is None:
        _CACHE.clear()
    else:
        _CACHE.pop(tenant, None)
