# -*- coding: utf-8 -*-
"""
================================================================================
 EJECUTOR DE HERRAMIENTAS TIPO 'http'
================================================================================

Genérico a propósito: no sabe qué API está llamando, ni qué tenant es, ni qué
significan los datos que devuelve. Solo sabe ejecutar lo que una
'Herramienta' (nucleo/config/schema.py) declara: endpoint, método, y cómo
resolver la clave desde el entorno.

Lo que decide (qué endpoint, qué filtros, qué campos se muestran despues) es
config. Lo que este modulo hace es mecanico: no interpreta la respuesta, no
filtra campos (eso es nucleo/seguridad/listas_blancas.py) y no decide si el
tenant puede o no llamarlo (eso lo resuelve el motor antes de invocar esto).
================================================================================
"""

from __future__ import annotations

import os

import requests

TIMEOUT_SEGUNDOS = 15


class ErrorHerramientaHttp(Exception):
    """Fallo al resolver credenciales o al llamar al endpoint."""


def headers_de(herramienta) -> dict:
    """Header de autenticacion de una Herramienta. Publico porque
    nucleo/herramientas/agregado.py tambien lo necesita, con su propio manejo
    de errores (no puede usar 'ejecutar()' porque esa levanta en cualquier
    HTTP 400 en vez de devolver un error que el modelo pueda corregir)."""
    if not herramienta.auth_ref:
        return {}
    clave = os.environ.get(herramienta.auth_ref)
    if not clave:
        raise ErrorHerramientaHttp(
            f"Falta la variable '{herramienta.auth_ref}' en el entorno. La "
            f"configuracion guarda el NOMBRE del secreto, no su valor: "
            f"agregalo al .env.")
    return {"Authorization": f"{herramienta.auth_esquema} {clave}"}


def url_de(herramienta) -> str:
    """URL completa (base_url + endpoint) de una Herramienta. Publico por el
    mismo motivo que headers_de()."""
    if not herramienta.endpoint or not herramienta.base_url:
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no declara 'endpoint'/'base_url'.")
    return herramienta.base_url.rstrip("/") + herramienta.endpoint


def ejecutar(herramienta, argumentos: dict) -> dict | list:
    """
    'herramienta' es una instancia de nucleo.config.schema.Herramienta con
    tipo='http'. 'argumentos' ya viene validado por el llamador -- este
    modulo no valida forma de negocio, solo ejecuta.
    """
    if herramienta.tipo != "http":
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no es tipo 'http' (es '{herramienta.tipo}').")

    url = url_de(herramienta)
    headers = headers_de(herramienta)

    if herramienta.metodo == "GET":
        r = requests.get(url, headers=headers, params=argumentos, timeout=TIMEOUT_SEGUNDOS)
    else:
        r = requests.request(herramienta.metodo, url, headers=headers,
                             json=argumentos, timeout=TIMEOUT_SEGUNDOS)
    r.raise_for_status()
    crudo = r.json()

    if herramienta.extraer_de and isinstance(crudo, dict) and herramienta.extraer_de in crudo:
        return crudo[herramienta.extraer_de]
    return crudo
