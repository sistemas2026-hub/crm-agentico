# -*- coding: utf-8 -*-
"""
================================================================================
 SONDEO SEGURO DE APIs EXTERNAS  --  para el asistente de configuracion guiada
================================================================================

Por que existe
--------------
Todo el resto del proyecto llama a URLs YA VERIFICADAS y declaradas en el
YAML del tenant (Herramienta.endpoint) -- nunca a una URL que un humano
escriba en el momento. El asistente de configuracion guiada (CLAUDE.md: "la
proxima empresa que se conecte no deberia necesitar una sesion de codigo")
rompe esa regla A PROPOSITO: un colaborador ADMIN describe una API nueva, y
el codigo tiene que poder llamarla para sondearla -- antes de que exista
ninguna declaracion verificada.

Eso abre una superficie de ataque que el resto del proyecto no tiene: SSRF
(Server-Side Request Forgery). Sin este modulo, un ADMIN (o una cuenta ADMIN
comprometida) podria pedirle al asistente que "consulte" una URL interna --
el propio motor (http://motor:5000/agentes), el pooler de Postgres, o el
endpoint de metadata de la nube (169.254.169.254, que en AWS/GCP/Azure
expone credenciales del servidor sin autenticacion) -- y usar al servidor
como proxy hacia su propia red interna.

Que bloquea
-----------
- Solo https (nunca http, nunca file://, nunca otro esquema).
- Resuelve el host y RECHAZA si cualquiera de las IPs resueltas cae en un
  rango privado/interno/de enlace local (RFC 1918, loopback, link-local --
  que cubre el endpoint de metadata de la nube).

Limite conocido, dejado escrito a proposito (mismo criterio que
nucleo/seguridad/redaccion.py con los nombres propios): hay una ventana
entre resolver el host aca y que 'requests' lo vuelva a resolver por su
cuenta al conectar, en la que un ataque de DNS rebinding podria cambiar la
respuesta. Mitigacion completa (fijar la conexion a la IP ya verificada)
queda pendiente. El riesgo residual es bajo -- esto solo lo puede disparar
un ADMIN ya autenticado, no un cliente final ni un desconocido -- pero no es
cero, y conviene que quien lo endurezca despues sepa exactamente donde mirar.
================================================================================
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

TIMEOUT_SEGUNDOS = 15
_LIMITE_MUESTRA = 3  # filas de ejemplo que se devuelven -- nunca el volcado completo


class ErrorSondeo(Exception):
    """URL rechazada o pedido fallido -- motivo legible para mostrarle al ADMIN."""


# RFC 1918 (privadas), loopback, link-local/metadata de nube, CGNAT,
# benchmarking, y sus equivalentes IPv6. Bloquear de mas (una IP publica que
# cae aca por error) es un falso positivo tolerable; dejar pasar una interna
# no lo es -- mismo criterio fail-closed que el resto del proyecto.
_RANGOS_PROHIBIDOS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _verificar_url_publica(url: str) -> None:
    partes = urlparse(url)
    if partes.scheme != "https":
        raise ErrorSondeo("Solo se permiten URLs https -- rechazado.")
    host = partes.hostname
    if not host:
        raise ErrorSondeo("La URL no tiene un host valido.")
    try:
        resueltas = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ErrorSondeo(f"No se pudo resolver el host '{host}'.") from e
    for _familia, _tipo, _proto, _canon, direccion in resueltas:
        ip = ipaddress.ip_address(direccion[0])
        if any(ip in rango for rango in _RANGOS_PROHIBIDOS):
            raise ErrorSondeo(
                f"El host '{host}' resuelve a una direccion privada o interna "
                f"({ip}) -- bloqueado por seguridad.")


def _pedir(url: str, headers: dict, params: dict | None = None):
    _verificar_url_publica(url)
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as e:
        raise ErrorSondeo(f"No se pudo conectar: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise ErrorSondeo(f"La API respondio {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise ErrorSondeo("La respuesta no es JSON valido.") from e


def sondear(url: str, headers: dict, params: dict | None = None) -> dict:
    """
    Un pedido de solo lectura (GET) contra una URL EXTERNA arbitraria,
    despues de verificar que no apunta a una red privada o interna.

    Devuelve un RESUMEN, nunca la respuesta cruda completa: 'count' (el que
    declara la API, o el largo de la lista si no), 'campos_disponibles', y
    hasta 3 filas de muestra -- lo suficiente para ver la FORMA del dato sin
    que el resultado sea un volcado gigante (y sin arrastrar de mas: si la
    API trae password/PII en la muestra, eso es visible para un ADMIN
    sondeando su propio sistema, no se filtra distinto a como ya lo veria
    entrando a la API directamente).
    """
    datos = _pedir(url, headers, params)

    if isinstance(datos, dict) and isinstance(datos.get("results"), list):
        muestra = datos["results"][:_LIMITE_MUESTRA]
        return {"count": datos.get("count", len(datos["results"])),
               "campos_disponibles": sorted(muestra[0].keys()) if muestra else [],
               "muestra": muestra}
    if isinstance(datos, list):
        muestra = datos[:_LIMITE_MUESTRA]
        campos = sorted(muestra[0].keys()) if muestra and isinstance(muestra[0], dict) else []
        return {"count": len(datos), "campos_disponibles": campos, "muestra": muestra}
    if isinstance(datos, dict):
        return {"count": 1, "campos_disponibles": sorted(datos.keys()), "muestra": [datos]}
    raise ErrorSondeo("Formato de respuesta no reconocido (ni dict ni lista).")
