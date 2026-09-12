# -*- coding: utf-8 -*-
"""
================================================================================
 ESTABILIDAD DEL ENLACE  --  cuenta el codigo, no el modelo
================================================================================

Por que existe
--------------
La OLT guarda los ultimos ciclos de caida de cada ONU: cuando se autorizo,
cuando se cayo, y por que. Es la mejor evidencia que tenemos de un enlace
inestable -- ese cliente que dice "a veces anda bien y a veces no" y al que
todas las mediciones puntuales le dan perfectas, porque se miden justo cuando
esta andando.

El dato ya llegaba en el diagnostico profundo y se tiraba: la lista de
eventos no esta en ninguna lista blanca, asi que el modelo nunca la vio.
Abrirle la lista tampoco era la solucion. Contar diez eventos, filtrar por
ventana de tiempo y decidir cual causa domina es aritmetica, y es exactamente
donde un LLM se equivoca con el mismo tono seguro con el que acierta
(PRD 12.5: el modelo compone, el codigo calcula).

Asi que esto devuelve la conclusion ya hecha -- cuantas caidas, en que
ventana, cual fue la causa dominante y un veredicto-- y el modelo solo la
redacta.

Medido el 21/08/2026 contra la ONU de prueba: NUEVE caidas en un dia, ocho de
ellas por perdida de señal optica. Ese mismo equipo respondia 'Online' y con
señal 'Very good' cuando se lo consultaba, asi que por el camino normal el
diagnostico daba todo sano.

Una trampa de este dato, y es la razon de que el veredicto mire el historial
y no solo la ultima causa: 'Last down cause' refleja UNICAMENTE el evento mas
reciente. En la misma medicion, la ultima causa era 're-register' -- que no
dice nada-- y tapaba las ocho alarmas opticas del mismo dia.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta

import requests

from nucleo.herramientas import http as ejecutor_http

TIMEOUT_SEGUNDOS = 40

# Cuanto miramos hacia atras. Un dia: es la ventana en la que un cliente
# todavia se acuerda de que "ayer andaba mal", y la que separa un enlace que
# se cae seguido de uno que se cayo una vez el mes pasado.
VENTANA_HORAS = 24

# A partir de cuantas caidas en la ventana el enlace deja de ser "sano con un
# tropiezo" y pasa a ser un problema que hay que ir a ver. Tres es
# conservador a proposito: dos pueden ser un corte de luz y su recuperacion.
CAIDAS_PARA_INESTABLE = 3


class ErrorEstabilidad(Exception):
    """No se pudo leer el historial de la ONU."""


def _a_fecha(valor):
    """Las marcas vienen como '2026-08-21 14:13:33-05:00'. Devuelve None ante
    cualquier forma inesperada: un evento que no se puede fechar no se cuenta,
    que es mejor que contarlo mal."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    for recorte in (texto, texto[:25], texto[:19]):
        try:
            return datetime.fromisoformat(recorte)
        except ValueError:
            continue
    return None


def _eventos(historial) -> list[dict]:
    """El proveedor devuelve el historial como diccionario indexado por
    numero ('10', '09', ...) o como lista, segun el endpoint. Se aceptan las
    dos formas: asumir una sola es como se rompen estas integraciones."""
    if isinstance(historial, dict):
        return [v for _, v in sorted(historial.items()) if isinstance(v, dict)]
    if isinstance(historial, list):
        return [v for v in historial if isinstance(v, dict)]
    return []


def resumir(herramienta, argumentos: dict, tenant: str | None = None,
            variables_tenant: dict | None = None) -> dict:
    """
    Cuantas veces se cayo el enlace de este cliente en la ultima ventana, por
    que, y si eso alcanza para llamarlo inestable.

    Devuelve SIEMPRE 'enlace_inestable' (bool) para que quien lea nunca tenga
    que interpretar una ausencia. Si no hay con que consultar, lo dice en
    'motivo' en vez de devolver un false que se leeria como "esta estable".
    """
    identificador = (argumentos or {}).get("sn_onu")
    if not identificador:
        return {"enlace_inestable": False,
                "motivo": "no hay una ONU identificada para este cliente"}

    base_url = ejecutor_http.base_url_de(herramienta, variables_tenant).rstrip("/")
    headers = ejecutor_http.headers_de(herramienta, tenant)

    ruta = f"{base_url}/api/onu/get_onu_full_status_info/{identificador}"
    try:
        respuesta = requests.get(ruta, headers=headers, timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as e:
        raise ErrorEstabilidad(f"no se pudo consultar el historial: {e}") from e
    if respuesta.status_code != 200:
        raise ErrorEstabilidad(
            f"el proveedor respondio {respuesta.status_code} al pedir el historial")

    completo = (respuesta.json() or {}).get("full_status_json") or {}
    eventos = _eventos(completo.get("History"))
    if not eventos:
        return {"enlace_inestable": False,
                "motivo": "el equipo no reporta historial de caidas"}

    corte = None
    ahora = None
    fechas = [f for f in (_a_fecha(e.get("Offline at")) for e in eventos) if f]
    if fechas:
        ahora = max(fechas)
        corte = ahora - timedelta(hours=VENTANA_HORAS)

    en_ventana, causas = [], {}
    for e in eventos:
        cuando = _a_fecha(e.get("Offline at"))
        if cuando is None or (corte is not None and cuando < corte):
            continue
        en_ventana.append(e)
        causa = (e.get("Cause") or "").strip() or "sin causa reportada"
        causas[causa] = causas.get(causa, 0) + 1

    if not en_ventana:
        return {"enlace_inestable": False,
                "caidas_en_ventana": 0,
                "ventana_horas": VENTANA_HORAS,
                "motivo": "sin caidas registradas en la ventana"}

    dominante, veces = max(causas.items(), key=lambda kv: kv[1])
    salida = {
        "enlace_inestable": len(en_ventana) >= CAIDAS_PARA_INESTABLE,
        "caidas_en_ventana": len(en_ventana),
        "ventana_horas": VENTANA_HORAS,
        "causa_dominante": dominante,
        "veces_la_causa_dominante": veces,
    }
    ultima = _a_fecha(en_ventana[-1].get("Offline at")) if en_ventana else None
    if ultima:
        salida["ultima_caida"] = ultima.isoformat()
    return salida
