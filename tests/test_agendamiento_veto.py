# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL AGENDAMIENTO AUTOMATICO -- evidencia, veto, y lo que ve el cliente
================================================================================

Por que existe
--------------
Dos bugs reales, los dos INVISIBLES desde la respuesta del asistente, que es
lo que los hace peligrosos:

1. Una caida que afecta a varios vecinos del mismo puerto se ve, desde la ONU
   de UNO de ellos, identica a su propia fibra cortada ('sin señal optica').
   Esa causa es justamente la evidencia que hace saltar el checklist y agendar
   sola: sin un veto, treinta reportes de la MISMA caida despachan treinta
   tecnicos a treinta casas por una falla que no esta en ninguna de ellas.

2. La descripcion de 'consultar_incidente_red' le manda al modelo usar
   'clientes_caidos_a_la_vez' y 'desde_por_tiempos' -- y la lista blanca los
   borraba antes de que llegara a verlos, dejando la regla en letra muerta.
   Nadie se entera: "8 afectados desde las 12:16" suena igual de razonable que
   el dato correcto.

Ninguno de los dos se ve leyendo lo que el asistente contesta. Se ven aca.

No hace falta red ni base de datos: son funciones puras sobre el historial y
sobre la config del tenant ya validada.

Uso
---
    py -3.13 tests/test_agendamiento_veto.py
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config import cargar_config
from nucleo.seguimiento import agendamiento
from nucleo.seguridad import listas_blancas

RUTA = Path(__file__).resolve().parent.parent / "tenants" / "rapilink.config.yaml"

fallos: list[str] = []


def comprobar(condicion, descripcion):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


config = cargar_config(str(RUTA))
rol = config.roles["soporte_tecnico_cliente"]


def turno(nombre, crudo):
    """Un turno de herramienta tal como queda en el historial: YA filtrado por
    la lista blanca del rol. Filtrarlo es el punto -- probar con el dato crudo
    esconde exactamente el bug 2."""
    visto = listas_blancas.filtrar_campos(rol, nombre, crudo)
    return {"role": "tool", "name": nombre,
            "content": json.dumps(visto, ensure_ascii=False)}, visto


FIBRA = {"ONU details": {"Last down cause_interpretado": "sin señal optica"},
         "ONU WAN Interfaces": {"MAC address": ""}}
INCIDENTE = {"es_incidente_de_red": True, "tipo_alerta": "LOS",
             "clientes_afectados": 8, "porcentaje_afectado": 12,
             "desde": "12:16", "zona": "Z", "caja": "C", "motivo": "m",
             "clientes_caidos_a_la_vez": 7, "desde_por_tiempos": "07:16"}

t_fibra, _ = turno("diagnosticar_falla_ont", FIBRA)
t_masivo, visto_cliente = turno("consultar_incidente_red", INCIDENTE)
t_aislado, _ = turno("consultar_incidente_red", {"es_incidente_de_red": False})

print("\n--- la evidencia de red alcanza para agendar sin el checklist ---")
comprobar(agendamiento.evidencia_ya_alcanza(config, "no_internet", [t_fibra, t_aislado]),
          "fibra cortada y caida aislada: se agenda sin repreguntar")
comprobar(not agendamiento.evidencia_ya_alcanza(config, "no_internet", []),
          "sin ninguna medicion, la evidencia no alcanza")

print("\n--- el veto le gana a la evidencia ---")
comprobar(agendamiento.veto_de_agendamiento(config, "no_internet", [t_fibra, t_masivo]),
          "la misma fibra cortada NO agenda si la caida es compartida")
comprobar(not agendamiento.veto_de_agendamiento(config, "no_internet", [t_fibra, t_aislado]),
          "una caida aislada no veta nada")
comprobar(not agendamiento.veto_de_agendamiento(config, "no_internet", [t_fibra]),
          "sin consultar incidentes no se veta: el camino normal ya es el conservador")

print("\n--- una herramienta que fallo no prueba nada, en ningun sentido ---")
t_error = {"role": "tool", "name": "consultar_incidente_red",
           "content": json.dumps({"error": "timeout"})}
comprobar(not agendamiento.veto_de_agendamiento(config, "no_internet", [t_fibra, t_error]),
          "un error al consultar incidentes no cuenta como 'no hay incidente'")

print("\n--- lo que el CLIENTE puede ver de un incidente de red ---")
comprobar("es_incidente_de_red" in visto_cliente,
          "sabe que la caida es general (es lo que le explica que no es su equipo)")
comprobar("desde_por_tiempos" in visto_cliente,
          "y desde cuando, contado por tiempos reales y no por el agrupado de SmartOLT")
for interno in ("clientes_afectados", "clientes_caidos_a_la_vez",
                "porcentaje_afectado", "zona", "caja"):
    comprobar(interno not in visto_cliente,
              f"'{interno}' NO le llega al cliente: es panorama interno de la red")

print("\n--- el colaborador SI recibe los dos numeros por tiempos (bug 2) ---")
visto_soporte = listas_blancas.filtrar_campos(
    config.roles["soporte"], "consultar_incidente_red", INCIDENTE)
for campo in ("clientes_caidos_a_la_vez", "desde_por_tiempos"):
    comprobar(campo in visto_soporte,
              f"'{campo}' sobrevive la lista blanca -- la descripcion manda usarlo")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El agendamiento automatico agenda donde debe y se frena donde debe.")
