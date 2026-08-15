# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LOS MECANISMOS CONDICIONALES DE 'Herramienta'
================================================================================

Por que existe
--------------
La integracion de SmartOLT (agosto 2026) agrego varios mecanismos genericos a
'Herramienta' -- veredictos, mapeos, base_url_ref, exige_previas,
limite_por_conversacion -- todos verificados a mano contra la API real en su
momento, pero ninguno tenia una guarda que los protegiera de una regresion
futura. Esta prueba cubre esa deuda.

No hace falta red ni base de datos: son funciones puras sobre dicts y sobre
'Herramienta' ya validada. El caso real (SmartOLT: 'Last down cause' ->
'dying-gasp'/'ONT LOSi/LOBi alarm', 'onu_signal_1490' -> rango de G-GO-04) se
usa como ejemplo porque es el que motivo el mecanismo, no porque el nucleo
sepa que existe SmartOLT -- son datos de prueba, no configuracion del tenant.

Uso
---
    py -3.13 tests/test_condiciones_herramienta.py
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config.schema import Herramienta, Precondicion, RangoVeredicto  # noqa: E402
from nucleo.herramientas.http import (ErrorHerramientaHttp, _aplicar_mapeos,  # noqa: E402
                                      _aplicar_veredictos, base_url_de,
                                      url_de)
from nucleo.modelo.motor import _previas_no_cumplidas, _veces_ejecutada     # noqa: E402
from pydantic import ValidationError                                        # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def lanza(que: str, excepcion, fn) -> None:
    try:
        fn()
    except excepcion:
        print(f"  [ok]   {que}")
        return
    except Exception as e:
        print(f"  [FALLA] {que} -- lanzo {type(e).__name__}, no {excepcion.__name__}")
        fallos.append(que)
        return
    print(f"  [FALLA] {que} -- no lanzo nada")
    fallos.append(que)


def _herramienta(**overrides) -> Herramienta:
    base = dict(nombre="prueba", tipo="http", endpoint="/x/{sn_onu}",
               base_url="https://x.example.com", roles_permitidos=["soporte"])
    base.update(overrides)
    return Herramienta(**base)


print("veredictos (rangos numericos)")
h_veredicto = _herramienta(veredictos={
    "onu_signal_1490": [
        RangoVeredicto(desde=-25, hasta=-8, etiqueta="aceptable"),
        RangoVeredicto(hasta=-25.0001, etiqueta="problema"),
    ]
})

d = {"onu_signal_1490": -21.7}
_aplicar_veredictos(h_veredicto, d)
comprobar(d.get("onu_signal_1490_veredicto") == "aceptable",
         "un valor dentro del rango calcula la etiqueta correcta")

d2 = {"onu_signal_1490": -27.0}
_aplicar_veredictos(h_veredicto, d2)
comprobar(d2.get("onu_signal_1490_veredicto") == "problema",
         "un valor fuera del rango cae al siguiente tramo")

d3 = {"onu_signal_1490": "-"}
_aplicar_veredictos(h_veredicto, d3)
comprobar("onu_signal_1490_veredicto" not in d3,
         "un valor no numerico (ONU offline trae '-') se ignora sin romper")

d4 = {"otro_campo": 1}
_aplicar_veredictos(h_veredicto, d4)
comprobar("onu_signal_1490_veredicto" not in d4,
         "un dict sin el campo declarado no agrega nada")

print("\nveredictos (un nivel de anidamiento, notacion con punto)")
h_veredicto_anidado = _herramienta(veredictos={
    "Optical status.Rx optical power(dBm)": [
        RangoVeredicto(desde=-25, hasta=-8, etiqueta="aceptable"),
    ]
})
d5 = {"Optical status": {"Rx optical power(dBm)": -21.8}}
_aplicar_veredictos(h_veredicto_anidado, d5)
comprobar(d5["Optical status"].get("Rx optical power(dBm)_veredicto") == "aceptable",
         "el veredicto anidado se escribe DENTRO del objeto padre, no en el nivel superior")
comprobar("Rx optical power(dBm)_veredicto" not in d5,
         "y no se filtra una copia al nivel superior")

print("\nmapeos (texto exacto)")
h_mapeo = _herramienta(mapeos={
    "ONU details.Last down cause": {
        "dying-gasp": "sin energia electrica",
        "ONT LOSi/LOBi alarm": "falla optica",
    }
})
d6 = {"ONU details": {"Last down cause": "dying-gasp", "Run state": "online"}}
_aplicar_mapeos(h_mapeo, d6)
comprobar(d6["ONU details"].get("Last down cause_interpretado") == "sin energia electrica",
         "una causa mapeada calcula la etiqueta interpretada")

d7 = {"ONU details": {"Last down cause": "una causa nueva no documentada"}}
_aplicar_mapeos(h_mapeo, d7)
comprobar("Last down cause_interpretado" not in d7["ONU details"],
         "una causa SIN entrada en el mapeo se deja sin interpretar (no se inventa)")

print("\nRangoVeredicto: validacion")
lanza("un rango sin 'desde' NI 'hasta' se rechaza (no significa nada)", ValidationError,
     lambda: RangoVeredicto(etiqueta="x"))

print("\nbase_url / base_url_ref: resolucion y fail-closed")
h_literal = _herramienta(base_url="https://fijo.example.com")
comprobar(base_url_de(h_literal) == "https://fijo.example.com",
         "base_url literal se devuelve tal cual, sin variables_tenant")

h_ref = _herramienta(base_url=None, base_url_ref="ALGUN_SUBDOMINIO")
comprobar(base_url_de(h_ref, {"ALGUN_SUBDOMINIO": "https://variable.example.com"})
         == "https://variable.example.com",
         "base_url_ref se resuelve contra variables_tenant")
lanza("base_url_ref sin la variable cargada falla cerrado", ErrorHerramientaHttp,
     lambda: base_url_de(h_ref, {}))

lanza("declarar base_url Y base_url_ref a la vez se rechaza en el schema", ValidationError,
     lambda: _herramienta(base_url="https://a.example.com", base_url_ref="B"))
lanza("no declarar ninguno de los dos se rechaza en el schema", ValidationError,
     lambda: _herramienta(base_url=None))

print("\nurl_de: guarda contra un marcador de ruta sin resolver")
h_ruta = _herramienta(endpoint="/api/onu/x/{sn_onu}")
comprobar(url_de(h_ruta, {"sn_onu": "ABC123"}) == "https://x.example.com/api/onu/x/ABC123",
         "con el argumento presente, la URL se arma normal")
lanza("sin el argumento, se rechaza en vez de mandar '{sn_onu}' literal", ErrorHerramientaHttp,
     lambda: url_de(h_ruta, {}))

print("\nexige_previas: la llamada MAS RECIENTE decide, no la primera")
h_reinicio = _herramienta(exige_previas=[
    Precondicion(herramienta="consultar_senal", campo="veredicto", valor="aceptable"),
    Precondicion(herramienta="ping", campo="ping-exitoso", valor=True),
])

historial_vacio: list[dict] = []
comprobar(set(_previas_no_cumplidas(h_reinicio, historial_vacio))
         == {"consultar_senal", "ping"},
         "sin ninguna llamada previa, faltan las dos precondiciones")

historial_favorable = [
    {"role": "tool", "name": "consultar_senal", "content": '{"veredicto": "aceptable"}'},
    {"role": "tool", "name": "ping", "content": '{"ping-exitoso": true}'},
]
comprobar(_previas_no_cumplidas(h_reinicio, historial_favorable) == [],
         "con las dos llamadas favorables, no falta nada")

historial_desmejora = [
    {"role": "tool", "name": "consultar_senal", "content": '{"veredicto": "aceptable"}'},
    {"role": "tool", "name": "consultar_senal", "content": '{"veredicto": "problema"}'},
    {"role": "tool", "name": "ping", "content": '{"ping-exitoso": true}'},
]
comprobar(_previas_no_cumplidas(h_reinicio, historial_desmejora) == ["consultar_senal"],
         "si la señal empeoro DESPUES de una lectura buena, la ultima manda -- no cumple")

print("\nexige_previas: la forma REAL del dato filtrado, no solo un dict plano")
# Esto es lo que 'listas_blancas.filtrar_campos' deja en el historial cuando la
# herramienta devuelve una LISTA (ping_cliente): {'total', 'resultados'}, con
# el campo buscado adentro de una de las filas. La version anterior de esta
# prueba usaba un dict plano inventado ({'ping-exitoso': true}) y por eso NO
# detecto el bug real -- la precondicion de reiniciar_ont estuvo rota en
# produccion sin que esta guarda dijera nada. Ver _buscar_campo en motor.py.
h_real = _herramienta(exige_previas=[
    Precondicion(herramienta="ping", campo="ping-exitoso", valor="3 de 3"),
])
historial_forma_real = [
    {"role": "tool", "name": "ping", "content": json.dumps({
        "total": 4,
        "resultados": [
            {"ping-1": {"received": "1", "packet-loss": "0"}},
            {"ping-2": {"received": "1", "packet-loss": "0"}},
            {"ping-3": {"received": "1", "packet-loss": "0"}},
            {"ping-exitoso": "3 de 3"},
        ],
    })},
]
comprobar(_previas_no_cumplidas(h_real, historial_forma_real) == [],
         "encuentra el campo dentro de {total, resultados} (forma real de una lista filtrada)")

historial_forma_real_fallo = [
    {"role": "tool", "name": "ping", "content": json.dumps({
        "total": 4,
        "resultados": [
            {"ping-1": {"status": "timeout"}},
            {"ping-exitoso": "0 de 3"},
        ],
    })},
]
comprobar(_previas_no_cumplidas(h_real, historial_forma_real_fallo) == ["ping"],
         "y NO se cumple cuando el valor anidado es distinto ('0 de 3')")

print("\nexige_previas: 'valores' cuando el dato real no es estable")
# 'ping-exitoso' de WispHub devolvio '1 de 3', '2 de 3' y '3 de 3' en tres
# corridas seguidas contra el mismo equipo sano (15/08/2026). Exigir un unico
# valor dejaba la precondicion cumpliendose una de cada tres veces.
h_varios = _herramienta(exige_previas=[
    Precondicion(herramienta="ping", campo="ping-exitoso",
                 valores=["1 de 3", "2 de 3", "3 de 3"]),
])
for valor, deberia_cumplir in [("3 de 3", True), ("1 de 3", True), ("0 de 3", False)]:
    hist = [{"role": "tool", "name": "ping",
             "content": json.dumps({"ping-exitoso": valor})}]
    cumple = _previas_no_cumplidas(h_varios, hist) == []
    comprobar(cumple is deberia_cumplir,
             f"'{valor}' {'cumple' if deberia_cumplir else 'NO cumple'} la precondicion")

lanza("declarar 'valor' Y 'valores' a la vez se rechaza", ValidationError,
     lambda: Precondicion(herramienta="x", campo="y", valor=1, valores=[1]))
lanza("no declarar ninguno de los dos se rechaza", ValidationError,
     lambda: Precondicion(herramienta="x", campo="y"))

print("\nexige_previas: casos de borde de la busqueda anidada")
h_json_roto = _herramienta(exige_previas=[
    Precondicion(herramienta="consultar_senal", campo="veredicto", valor="aceptable"),
    Precondicion(herramienta="ping", campo="ping-exitoso", valor=True),
])
h_reinicio = h_json_roto
historial_json_roto = [
    {"role": "tool", "name": "consultar_senal", "content": "no es json valido"},
    {"role": "tool", "name": "ping", "content": '{"ping-exitoso": true}'},
]
comprobar(_previas_no_cumplidas(h_reinicio, historial_json_roto) == ["consultar_senal"],
         "un content que no parsea como JSON no cuenta como cumplido")

print("\nlimite_por_conversacion: cuenta llamadas por nombre de herramienta")
h_limitada = _herramienta(nombre="reiniciar_ont", limite_por_conversacion=1)
comprobar(_veces_ejecutada(h_limitada, []) == 0,
         "sin historial, cero ejecuciones")
historial_una_vez = [{"role": "tool", "name": "reiniciar_ont", "content": "{}"}]
comprobar(_veces_ejecutada(h_limitada, historial_una_vez) == 1,
         "una llamada previa a la MISMA herramienta cuenta")
historial_otra_herramienta = [{"role": "tool", "name": "otra_herramienta", "content": "{}"}]
comprobar(_veces_ejecutada(h_limitada, historial_otra_herramienta) == 0,
         "una llamada a OTRA herramienta no cuenta")


if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Todos los mecanismos condicionales se comportan como se espera.")
