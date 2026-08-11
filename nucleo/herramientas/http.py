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
import time

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


def url_de(herramienta, argumentos: dict | None = None) -> str:
    """
    URL completa (base_url + endpoint) de una Herramienta. Publico por el
    mismo motivo que headers_de().

    'endpoint' puede traer marcadores '{clave}' (ej. '/clientes/{id_servicio}/
    ping/') para APIs que exigen el id en la RUTA, no en query/body -- WispHub
    hace esto en sus endpoints de accion (ping, agregar-cliente). Si se pasa
    'argumentos', cada marcador que matchea una clave la CONSUME (pop): asi
    ese valor no se manda ademas como parametro suelto.
    """
    if not herramienta.endpoint or not herramienta.base_url:
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no declara 'endpoint'/'base_url'.")
    endpoint = herramienta.endpoint
    if argumentos:
        for clave in list(argumentos):
            marcador = "{" + clave + "}"
            if marcador in endpoint:
                endpoint = endpoint.replace(marcador, str(argumentos.pop(clave)))
    return herramienta.base_url.rstrip("/") + endpoint


def ejecutar(herramienta, argumentos: dict) -> dict | list:
    """
    'herramienta' es una instancia de nucleo.config.schema.Herramienta con
    tipo='http'. 'argumentos' ya viene validado por el llamador -- este
    modulo no valida forma de negocio, solo ejecuta.
    """
    if herramienta.tipo != "http":
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no es tipo 'http' (es '{herramienta.tipo}').")

    # Copia: url_de() puede popear claves que van en la ruta, y el llamador
    # (nucleo/modelo/motor.py) no espera que su dict se mute por debajo.
    argumentos = dict(argumentos or {})
    url = url_de(herramienta, argumentos)
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


def ejecutar_asincrono(herramienta, argumentos: dict,
                       intentos: int = 10, espera_segundos: float = 1.5) -> dict | list:
    """
    Para APIs que no responden en el momento: WispHub, al menos en ping y en
    crear/borrar cliente, devuelve {'task_id': ...} (202) y hay que consultar
    aparte -- ver .claude/skills/wisphub-api/SKILL.md. Generico a proposito
    (no menciona WispHub en el codigo): cualquier API que siga el mismo
    patron tarea/resultado sirve, mientras publique el resultado en
    '<base_url>/tasks/<task_id>/' con una clave 'status'.

    Verificado en vivo (agosto 2026, ping_cliente): tarda ~3 segundos en la
    practica -- 10 intentos a 1.5s de por medio (15s) es margen de sobra, no
    un numero elegido al azar.
    """
    inicial = ejecutar(herramienta, argumentos)
    task_id = inicial.get("task_id") if isinstance(inicial, dict) else None
    if not task_id:
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}': se esperaba 'task_id' en la respuesta y no vino.")

    url_tarea = herramienta.base_url.rstrip("/") + f"/tasks/{task_id}/"
    headers = headers_de(herramienta)

    for _ in range(intentos):
        time.sleep(espera_segundos)
        r = requests.get(url_tarea, headers=headers, timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        cuerpo = r.json()
        tarea = cuerpo.get("task", cuerpo) if isinstance(cuerpo, dict) else {}
        estado = tarea.get("status")
        if estado == "SUCCESS":
            return tarea.get("result")
        if estado in ("FAILURE", "REVOKED"):
            raise ErrorHerramientaHttp(
                f"'{herramienta.nombre}': la tarea termino en estado '{estado}'.")

    raise ErrorHerramientaHttp(
        f"'{herramienta.nombre}': la tarea no termino despues de "
        f"{intentos * espera_segundos:.0f}s.")
