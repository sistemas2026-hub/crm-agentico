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


#  EL MINIMO QUE WISPHUB ACEPTA ES 3, MEDIDO -- no documentado.
#
#  Verificado en vivo el 25/09/2026 contra id_servicio 5832: 'pings' 1 y 2
#  devuelven HTTP 400; 3, 4, 5 y 10 responden. Por eso la app no puede pedir
#  los paquetes de a uno para irlos mostrando: la tanda mas chica es de tres.
#
#  TANDAS, Y NO UNA SOLA LLAMADA DE DIEZ. Una de diez tarda ~18 s y el tecnico
#  mira una rueda girar sin saber si el primero volvio. En tandas los primeros
#  aparecen a los ~5 s. Se pagan tres llamadas en vez de una; a cambio, quien
#  esta parado en la casa ve caer los paquetes.
MINIMO_POR_TANDA = 3
TANDAS = (3, 3, 4)
PAQUETES = sum(TANDAS)


def probar_conexion(orden, *, paquetes: int = PAQUETES,
                    timeout: int = 120) -> dict:
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
            json={"id_servicio": servicio,
                  "pings": max(MINIMO_POR_TANDA, int(paquetes or PAQUETES))},
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
        # Texto tal como lo manda WispHub ('10 de 10', '0 de 10'), no un
        # numero: esta medido que convertirlo invita a compararlo, y un ping no
        # es un veredicto. Ver el encabezado de este modulo.
        "respondieron": str(respondieron),
        "paquetes": _paquetes(resultado),
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


def _paquetes(resultado) -> list:
    """
    Cada intento por separado: numero, si volvio, y cuanto tardo.

    Uno por uno y no un promedio, y con DIEZ en vez de tres. Un promedio
    esconde justamente lo que le interesa a quien esta parado en la casa: si
    el enlace es intermitente o esta caido parejo. Y con tres muestras esa
    diferencia no se dibuja -- esta medido que el mismo equipo sano devuelve
    1, 2 y 3 de 3 en corridas seguidas, asi que una racha corta no se
    distingue de un patron. Con diez, si.

    Se arma aca y no se reenvia el crudo: 'ping-N' trae 'host', que es la IP
    del cliente, y ya se filtro una vez por mandar el objeto entero.
    """
    salida = []
    for n in range(1, PAQUETES + 1):
        crudo = _buscar(resultado, f"ping-{n}")
        if not isinstance(crudo, dict):
            continue
        recibidos = str(crudo.get("received") or "0").strip()
        salida.append({
            "n": n,
            # 'respondio' es el dato duro; la pantalla decide como lo pinta.
            "respondio": recibidos not in ("", "0"),
            "rtt": str(crudo.get("avg-rtt") or ""),
            "perdida": str(crudo.get("packet-loss") or ""),
        })
    return salida
