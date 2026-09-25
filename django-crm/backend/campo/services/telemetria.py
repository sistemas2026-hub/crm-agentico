# -*- coding: utf-8 -*-
"""
Probar la conexion del cliente desde el terreno, en vivo.

POR QUE NO ALCANZA CON LA FICHA
-------------------------------
La orden ya trae la senal optica que el motor leyo al despacharla, y eso es lo
correcto para llevar al sitio: viaja congelada y se ve sin señal. Pero el
tecnico parado en la casa necesita otra cosa -- saber si AHORA hay comunicacion
con el equipo, despues de haber movido un conector o cambiado una roseta. Una
lectura de hace tres horas no responde esa pregunta.

Por eso esto es una ACCION y no un dato: se pide, se espera, y la respuesta
vale para el instante en que se pidio.

LO QUE UN PING NO PRUEBA
------------------------
Que el equipo conteste no significa que el cliente tenga internet, y que no
contesten los tres intentos no significa que el servicio este caido. Esta
medido dos veces en este proyecto: el mismo equipo sano devolvio '1 de 3',
'2 de 3' y '3 de 3' en corridas seguidas (15/08/2026), y un reinicio real y
confirmado dejo el ping igual antes y despues (02/09/2026). Por eso la
respuesta viaja con el conteo crudo y SIN veredicto: la pantalla muestra lo
que paso, no dictamina.

SIN SEÑAL SE RECHAZA, NUNCA SE ENCOLA
-------------------------------------
Mismo criterio que RefrescarFichaView dejo escrito para su propio caso: un
ping encolado le llega al tecnico cuando ya se fue del sitio, que es peor que
no ofrecerlo. La cola de la aplicacion es para lo que CAMBIA el mundo y puede
esperar; una medicion que no se puede tomar ahora no se toma.
"""
from __future__ import annotations

import os

import requests


class SinServicioParaPing(Exception):
    """La orden no tiene con que preguntar: no hay identificador del servicio."""


def _motor():
    """Donde vive el motor y con que se le habla. Igual que despacho.py."""
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, tenant, cabeceras


def servicio_de(orden) -> str:
    """
    El identificador del servicio en el sistema del ISP, sacado de la ficha
    que se congelo al despachar.

    Sale de ahi y no de una consulta nueva a proposito: es el numero que
    quedo atado a ESTE trabajo. Volver a resolverlo ahora podria dar otro
    --un cliente puede tener mas de un servicio-- y el tecnico estaria
    midiendo el equipo equivocado sin enterarse.
    """
    contexto = orden.contexto or {}
    return str(contexto.get("servicio") or "").strip()


def probar_conexion(orden, *, timeout: int = 60) -> dict:
    """
    Le pide al motor un ping en vivo al equipo del cliente de 'orden'.

    Devuelve siempre un diccionario con 'ok'. Cuando 'ok' es False, 'motivo'
    dice por que -- y esa distincion es el punto: "no se pudo medir" no es lo
    mismo que "se midio y no respondio". La primera se reintenta; la segunda
    es un dato del equipo.

    La credencial de WispHub vive solo en el motor, asi que esto no le pega a
    la API del proveedor: entra por la ruta interna, que exige token de
    servicio y que la herramienta este declarada 'invocable_por_servicio'.
    """
    servicio = servicio_de(orden)
    if not servicio:
        raise SinServicioParaPing(
            "La orden no tiene identificado el servicio del cliente.")

    base, tenant, cabeceras = _motor()
    try:
        r = requests.post(
            f"{base}/interno/herramienta/ping_cliente",
            params={"tenant": tenant},
            # 'id_servicio' viaja como argumento y no por la sesion: por la
            # ruta interna la sesion es None a proposito. La herramienta lo
            # acepta porque el tenant lo declaro en
            # 'argumentos_sobrescribibles', que es lista blanca.
            json={"id_servicio": servicio},
            headers=cabeceras,
            timeout=timeout,
        )
    except Exception as e:                                   # noqa: BLE001
        # El motor no contesto. No se sabe nada del equipo del cliente.
        return {"ok": False, "motivo": "motor_no_responde",
                "detalle": type(e).__name__}

    if r.status_code == 403:
        # La herramienta existe y el tenant no la declaro invocable por un
        # servicio. Es un error de configuracion, no del equipo -- y se dice
        # asi para que nadie lo lea como "el cliente no responde".
        return {"ok": False, "motivo": "ping_no_habilitado"}
    if r.status_code != 200:
        return {"ok": False, "motivo": "motor_rechazo",
                "detalle": str(r.status_code)}

    try:
        resultado = (r.json() or {}).get("resultado")
    except ValueError:
        return {"ok": False, "motivo": "respuesta_ilegible"}

    if resultado is None:
        return {"ok": False, "motivo": "respuesta_vacia"}

    respondieron = _buscar(resultado, "ping-exitoso")
    if not respondieron:
        # La llamada salio y no trajo el conteo. No se inventa un '0 de 3':
        # eso seria afirmar que el equipo no respondio, y lo que pasa es que
        # no se sabe.
        return {"ok": False, "motivo": "sin_conteo"}

    return {
        "ok": True,
        # Texto tal como lo manda WispHub ('3 de 3', '0 de 3'), no un numero:
        # esta medido que convertirlo invita a compararlo, y un ping no es un
        # veredicto. Ver el encabezado de este modulo.
        "respondieron": str(respondieron),
        "latencias": _latencias(resultado),
    }


def _buscar(dato, campo: str):
    """
    El valor de 'campo' dentro de la respuesta, en la forma en que haya
    quedado.

    La respuesta de un ping no es un objeto plano: WispHub devuelve
    [{'ping-1': {...}}, ..., {'ping-exitoso': '3 de 3'}], y la lista blanca
    del motor la normaliza a {'total': N, 'resultados': [...]}. Buscar solo en
    el primer nivel encuentra 'total' y 'resultados', nunca 'ping-exitoso'.

    Es la misma funcion que el motor ya tiene (`_buscar_campo`), repetida acá
    y no importada porque este backend no importa el motor: se hablan por
    HTTP. Costo un bug real en agosto de 2026 -- la precondicion de
    'reiniciar_ont' nunca podia cumplirse y desde afuera se veia igual que
    "el modelo no quiere hacerlo".
    """
    if isinstance(dato, dict):
        if campo in dato:
            return dato[campo]
        for anidado in dato.values():
            if isinstance(anidado, (dict, list)):
                encontrado = _buscar(anidado, campo)
                if encontrado is not None:
                    return encontrado
    elif isinstance(dato, list):
        for item in dato:
            encontrado = _buscar(item, campo)
            if encontrado is not None:
                return encontrado
    return None


def _latencias(resultado) -> list:
    """
    El tiempo de ida y vuelta de cada intento, si vino.

    Se devuelven los TRES por separado y no un promedio: promediar tres
    muestras de las que una puede no haber respondido esconde justamente lo
    que le interesa a quien esta parado en la casa -- si el enlace es
    intermitente o esta caido parejo.
    """
    valores = []
    for n in (1, 2, 3):
        rtt = _buscar(resultado, f"ping-{n}")
        if isinstance(rtt, dict) and rtt.get("avg-rtt"):
            valores.append(str(rtt["avg-rtt"]))
    return valores
