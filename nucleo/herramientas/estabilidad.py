# -*- coding: utf-8 -*-
"""
================================================================================
 ESTABILIDAD DEL ENLACE  --  cuenta el codigo, no el modelo
================================================================================

Por que existe
--------------
El caso que atiende es el del cliente que dice "a veces anda bien y a veces
no", al que todas las mediciones puntuales le dan perfectas porque se miden
justo cuando esta andando. La unica evidencia es el historial del equipo, y
contarlo -- cuantas caidas, en que ventana, cual causa domina -- es aritmetica:
exactamente donde un LLM se equivoca con el mismo tono seguro con el que acierta
(PRD 12.5: el modelo compone, el codigo calcula). Asi que esto devuelve la
conclusion ya hecha y el modelo solo la redacta.

Medido el 21/08/2026 contra la ONU de prueba: NUEVE caidas en un dia, ocho por
perdida de señal optica, con el equipo respondiendo 'Online' y 'Very good'
cada vez que se lo consultaba.

DE DONDE SALE, DESDE EL 10/11/2026
----------------------------------
Hasta ese dia leia la lista 'History' de get_onu_full_status_info. Tenia tres
defectos, los tres medidos o leidos en el codigo:

  - tardaba ~10 s (el proveedor pide no usar ese endpoint mas que para
    investigar un problema puntual) y traia solo los ULTIMOS 10 eventos;
  - la ventana de 24 h se contaba hacia atras desde la caida MAS RECIENTE del
    historial, no desde ahora: tres caidas de hace un mes salian como
    "inestable hoy";
  - no reintentaba con la forma hexadecimal del serial, asi que las ONUs
    registradas asi fallaban siempre.

Ahora lee get_onu_status_history (verificado en vivo el 13/10 y el 10/11/2026:
0,3-0,7 s, sale de la base de SmartOLT sin mandar comandos a la OLT). Sin
'from'/'to' devuelve las ultimas 24 h como transiciones:

    periods: [{status: online|los|power_fail|offline|login|unknown,
               from, to, seconds, cause: olt_reboot|null}, ...]
    summary: {known_seconds, online_percent, interruptions, seconds: {...}}

LA TRAMPA QUE ESTE ARCHIVO NO PUEDE OLVIDAR
-------------------------------------------
'online_percent' se calcula sobre 'known_seconds', no sobre la ventana: un
equipo del que SmartOLT no supo nada 21 dias aparecio con 99,99 % (skill
smartolt-api, 13/10/2026). Por eso aca no se usa ese porcentaje, y si lo que
SmartOLT sabe no cubre la mitad de la ventana, NO se afirma "estable": se dice
que no hay datos suficientes.

Y un periodo con 'cause: olt_reboot' no es una caida del enlace de este
cliente: se reinicio la OLT, se cayeron todos. No se cuenta.
================================================================================
"""

from __future__ import annotations

import requests

from nucleo.herramientas import http as ejecutor_http

TIMEOUT_SEGUNDOS = 20

# Cuanto miramos hacia atras. Un dia: es la ventana en la que un cliente
# todavia se acuerda de que "ayer andaba mal", y la que separa un enlace que
# se cae seguido de uno que se cayo una vez el mes pasado. Es la que el
# endpoint devuelve sin parametros.
VENTANA_HORAS = 24

# A partir de cuantas caidas en la ventana el enlace deja de ser "sano con un
# tropiezo" y pasa a ser un problema que hay que ir a ver. Tres es
# conservador a proposito: dos pueden ser un corte de luz y su recuperacion.
CAIDAS_PARA_INESTABLE = 3

# Por debajo de esta fraccion de la ventana con datos, no se afirma nada.
COBERTURA_MINIMA = 0.5

#: Como se nombra cada estado de caida. El codigo de SmartOLT no le dice nada
#: a quien lee ('power_fail'); esto si, y separa las dos causas que importan:
#: la luz de la casa contra la señal optica.
CAUSAS = {
    "los": "perdida de señal optica (LOS)",
    "power_fail": "el equipo se quedo sin energia",
    "offline": "fuera de linea, sin causa reportada",
    "login": "reconectandose a la red",
}

ESTADOS_SIN_CAIDA = {"online", "unknown"}


class ErrorEstabilidad(Exception):
    """No se pudo leer el historial de la ONU."""


def resumir_historial(respuesta: dict) -> dict:
    """
    La conclusion a partir de la respuesta de get_onu_status_history. Pura: no
    llama a nadie, y por eso es lo que prueban las pruebas.

    Devuelve SIEMPRE 'enlace_inestable' (bool) para que quien lea nunca tenga
    que interpretar una ausencia; cuando no se puede afirmar, lo dice en
    'motivo' en vez de devolver un false que se leeria como "esta estable".
    """
    cuerpo = respuesta.get("response") if isinstance(respuesta.get("response"), dict) else respuesta
    periodos = [p for p in (cuerpo.get("periods") or []) if isinstance(p, dict)]
    resumen = cuerpo.get("summary") if isinstance(cuerpo.get("summary"), dict) else {}

    try:
        conocidos = float(resumen.get("known_seconds") or 0)
    except (TypeError, ValueError):
        conocidos = 0.0
    if conocidos < VENTANA_HORAS * 3600 * COBERTURA_MINIMA:
        return {"enlace_inestable": False,
                "ventana_horas": VENTANA_HORAS,
                "motivo": "el sistema de red no tiene datos de buena parte de la "
                          "ventana: no se puede decir si el enlace estuvo estable"}

    # Una caida es pasar de 'online' a un estado de caida. Los periodos
    # seguidos de caida (LOS y despues offline) son UNA caida, no dos.
    caidas, causas, ultima = 0, {}, None
    anterior = None
    for p in sorted(periodos, key=lambda x: str(x.get("from") or "")):
        estado = str(p.get("status") or "").strip().lower()
        if p.get("cause") == "olt_reboot":
            anterior = estado
            continue
        if estado not in ESTADOS_SIN_CAIDA and anterior == "online":
            caidas += 1
            causa = CAUSAS.get(estado, estado or "sin causa reportada")
            causas[causa] = causas.get(causa, 0) + 1
            ultima = p.get("from") or ultima
        anterior = estado

    if not caidas and anterior and anterior not in ESTADOS_SIN_CAIDA:
        # Caido desde antes de la ventana y sin volver: no hubo "caidas" que
        # contar, pero "sin caidas" se leeria como sano. Es una caida que sigue.
        return {"enlace_inestable": False,
                "caidas_en_ventana": 0,
                "ventana_horas": VENTANA_HORAS,
                "motivo": "el equipo esta caido desde antes de la ventana y no "
                          "volvio: no es un enlace inestable, es una caida que "
                          f"sigue ({CAUSAS.get(anterior, anterior)})"}
    if not caidas:
        return {"enlace_inestable": False,
                "caidas_en_ventana": 0,
                "ventana_horas": VENTANA_HORAS,
                "motivo": "sin caidas registradas en la ventana"}

    dominante, veces = max(causas.items(), key=lambda kv: kv[1])
    salida = {
        "enlace_inestable": caidas >= CAIDAS_PARA_INESTABLE,
        "caidas_en_ventana": caidas,
        "ventana_horas": VENTANA_HORAS,
        "causa_dominante": dominante,
        "veces_la_causa_dominante": veces,
    }
    if ultima:
        # Con la zona que declara la respuesta: SmartOLT escribe la hora en la
        # de la cuenta, sin offset (skill smartolt-api, 15/08/2026).
        zona = cuerpo.get("timezone")
        salida["ultima_caida"] = f"{ultima} ({zona})" if zona else str(ultima)
    return salida


def resumir(herramienta, argumentos: dict, tenant: str | None = None,
            variables_tenant: dict | None = None) -> dict:
    """Cuantas veces se cayo el enlace de este cliente en las ultimas 24 h,
    por que, y si eso alcanza para llamarlo inestable."""
    argumentos = dict(argumentos or {})
    identificador = argumentos.get("sn_onu")
    if not identificador:
        return {"enlace_inestable": False,
                "motivo": "no hay una ONU identificada para este cliente"}

    base_url = ejecutor_http.base_url_de(herramienta, variables_tenant).rstrip("/")
    headers = ejecutor_http.headers_de(herramienta, tenant)

    def pedir(serial):
        try:
            return requests.get(f"{base_url}/api/onu/get_onu_status_history/{serial}",
                                headers=headers, timeout=TIMEOUT_SEGUNDOS)
        except requests.RequestException as e:
            # El tipo y no el texto: el de requests trae la URL con el serial.
            raise ErrorEstabilidad(f"no se pudo consultar el historial: "
                                   f"{type(e).__name__}") from e

    respuesta = pedir(identificador)
    # La forma hexadecimal del serial, como el ejecutor generico: solo si el
    # proveedor rechazo el identificador (medido el 10/11/2026: una ONU en LOS
    # dio 400 con la forma corta).
    if ejecutor_http.es_rechazo_de_identificador(respuesta.status_code):
        otra = ejecutor_http.alternativas_de(herramienta, argumentos).get("sn_onu")
        if otra:
            respuesta = pedir(otra)
    if respuesta.status_code == 429:
        raise ejecutor_http.LimiteDelProveedor(respuesta)
    if respuesta.status_code != 200:
        raise ErrorEstabilidad(
            f"el proveedor respondio {respuesta.status_code} al pedir el historial")
    try:
        cuerpo = respuesta.json() or {}
    except ValueError as e:
        raise ErrorEstabilidad("el historial no vino en JSON") from e
    return resumir_historial(cuerpo)
