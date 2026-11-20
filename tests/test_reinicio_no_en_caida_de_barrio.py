# -*- coding: utf-8 -*-
"""
================================================================================
 UN REINICIO NO SE PROPONE EN MEDIO DE UNA CAIDA DEL BARRIO  (30/10/2026)
================================================================================

Por que existe
--------------
La bateria de flujos lo medía 0/10 (SPEC/DEXTER_ESTADO_ACTUAL.md, validacion de
produccion): con la ONU en linea y el ping sin respuesta, el agente reiniciaba
el equipo de UNA casa sin haber mirado si el PON entero estaba caido. En una
caida general eso es mandar a reiniciar treinta casas por una falla que no esta
en ninguna -- y es el momento en que mas gente hace falta.

La garantia va en codigo (PRD §7.4), no en el orden del prompt: 'reiniciar_ont'
declara 'consultar_incidente_red' entre sus 'exige_previas', con
'es_incidente_de_red: false'. Como el motor vuelve a medir las previas al
aprobar (motor.previas_frescas), la caida se comprueba dos veces: cuando la IA
propone y cuando una persona aprueba.

PRD §8.17, Ola 1, decision 2.

Uso
---
    py -3.13 tests/test_reinicio_no_en_caida_de_barrio.py
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config.schema import Herramienta              # noqa: E402
from nucleo.modelo.motor import _previas_no_cumplidas     # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def tool(nombre: str, contenido) -> dict:
    return {"role": "tool", "name": nombre, "content": json.dumps(contenido)}


config = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
crudo = next(h for h in config["herramientas"] if h["nombre"] == "reiniciar_ont")
reinicio = Herramienta.model_validate(crudo)

# El diagnostico que hoy habilita el reinicio: senal buena y equipo que contesta.
SENAL = tool("consultar_senal_ont", {"onu_signal_1490_veredicto": "aceptable"})
PING = tool("ping_cliente", {"total": 2, "resultados": [{"ping-exitoso": "3 de 3"}]})
CAIDA = tool("consultar_incidente_red", {"es_incidente_de_red": True,
                                         "desde_por_tiempos": "2026-10-30 07:16:00"})
SIN_CAIDA = tool("consultar_incidente_red", {"es_incidente_de_red": False})

print("\nla config del tenant lo declara")
comprobar(any(p.herramienta == "consultar_incidente_red"
              and p.campo == "es_incidente_de_red" and p.valor is False
              for p in reinicio.exige_previas),
          "reiniciar_ont exige consultar_incidente_red con es_incidente_de_red: false")
comprobar({"consultar_senal_ont", "ping_cliente"}
          <= {p.herramienta for p in reinicio.exige_previas},
          "y conserva las dos previas que ya tenia (senal y ping)")

print("\nel motor lo hace cumplir")
comprobar("consultar_incidente_red" in _previas_no_cumplidas(reinicio, [SENAL, PING]),
          "senal y ping buenos, SIN haber mirado la red -> no se reinicia")
comprobar("consultar_incidente_red" in _previas_no_cumplidas(reinicio, [SENAL, PING, CAIDA]),
          "con una caida compartida en el PON -> no se reinicia")
comprobar(_previas_no_cumplidas(reinicio, [SENAL, PING, SIN_CAIDA]) == [],
          "sin caida compartida -> el reinicio queda habilitado, como antes")
comprobar(_previas_no_cumplidas(reinicio, [CAIDA, SENAL, PING, SIN_CAIDA]) == [],
          "si la caida termino y se volvio a mirar, manda la medicion mas reciente")
comprobar("consultar_incidente_red" in _previas_no_cumplidas(reinicio, [SIN_CAIDA, SENAL, PING, CAIDA]),
          "y al reves: una caida que empezo despues frena el reinicio")

print("\nlos roles que reinician pueden mirar la red")
roles = config["roles"]
que_reinician = [n for n, r in roles.items()
                 if isinstance(r, dict) and "reiniciar_ont" in (r.get("puede_consultar") or [])]
# Sin esto, una clave mal escrita deja este bloque sin ningun caso y en verde.
comprobar(len(que_reinician) > 0, f"hay roles que reinician: {que_reinician}")
for nombre in que_reinician:
    rol = roles[nombre]
    comprobar("consultar_incidente_red" in (rol.get("puede_consultar") or []),
              f"'{nombre}' tiene reiniciar_ont y tambien consultar_incidente_red")
    comprobar("es_incidente_de_red" in ((rol.get("campos_permitidos") or {})
                                        .get("consultar_incidente_red") or []),
              f"'{nombre}' ve el campo es_incidente_de_red (sin el, la previa nunca se cumple)")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un reinicio no se propone en medio de una caida del barrio.")
