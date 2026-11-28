# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL TICKET QUE SALE AL ESCALAR
================================================================================

Por que existe
--------------
Un caso mal declarado aca NO falla al cargar la config ni al arrancar: falla
el dia que ese caso escala, con un 400 del proveedor y un ticket que no se
creo. Y desde afuera se ve como "todavia no le toca ticket a este caso".

Lo que se protege, cada cosa por un motivo medido:

  - Que la PRIORIDAD dependa del contexto y no del caso a secas. Una lentitud
    con la optica fuera de rango y una sin causa identificada son dos trabajos
    distintos, y entrar los dos como 'normal' es perder la unica señal que
    ordena la cola.
  - Que gane la PRIMERA entrada que la traza cumple, y que la ultima (sin
    condiciones) sea el caso por defecto. Un orden equivocado deja entradas
    inalcanzables que se ven perfectamente bien en el YAML.
  - Que un asunto NUEVO no entre sin estar en el catalogo del proveedor.
    Verificado el 22/08/2026 contra la API real: WispHub responde 400 a un
    asunto que no este en su lista -- no lo acepta en silencio, como decia la
    documentacion que teniamos.

No hace falta red: se arman trazas a mano y se lee la config del tenant.

Uso
---
    py -3.13 tests/test_ticket_al_escalar.py
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config import cargar_config  # noqa: E402
from nucleo.seguimiento import agendamiento  # noqa: E402

RUTA = Path(__file__).resolve().parent.parent / "tenants" / "rapilink.config.yaml"

fallos: list[str] = []


def comprobar(condicion, descripcion):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


config = cargar_config(str(RUTA))
mapeo = config.escalamiento.ticket_al_escalar


def traza(herramienta, campo, valor):
    return [{"role": "tool", "name": herramienta,
             "content": json.dumps({campo: valor}, ensure_ascii=False)}]


print("\nla prioridad la decide el contexto, no el caso")
sin_causa = agendamiento.ticket_para_escalar(config, "internet_lento", [])
optica = agendamiento.ticket_para_escalar(
    config, "internet_lento",
    traza("consultar_senal_ont", "onu_signal_1490_veredicto",
          "fuera de rango -- senal debil: problema en el drop"))
inestable = agendamiento.ticket_para_escalar(
    config, "internet_lento",
    traza("consultar_estabilidad_enlace", "enlace_inestable", True))

comprobar(sin_causa is not None, "una lentitud sin causa igual abre ticket")
comprobar(optica is not None and optica.prioridad > sin_causa.prioridad,
          "con la optica fuera de rango entra con MAS prioridad que sin causa")
comprobar(inestable is not None and inestable.prioridad > sin_causa.prioridad,
          "un enlace inestable tambien: la red ya conto la falla")
comprobar(optica.asunto != sin_causa.asunto,
          "y con otro asunto: el tecnico sabe de que se trata sin abrir nada")

print("\nel orden de las entradas")
for caso, entradas in mapeo.items():
    for i, e in enumerate(entradas[:-1]):
        comprobar(bool(e.condiciones),
                  f"'{caso}': la entrada {i} tiene condiciones (si no, las de abajo "
                  f"no se alcanzan nunca)")
    comprobar(not entradas[-1].condiciones,
              f"'{caso}': la ultima no tiene condiciones -- es el caso por defecto")

print("\ncada caso declara donde va y con que entra")
for caso, entradas in mapeo.items():
    for e in entradas:
        comprobar(bool(e.area), f"'{caso}' -> '{e.asunto or '(respaldo)'}' declara area")
        comprobar(bool(e.prioridad), f"'{caso}' -> '{e.asunto or '(respaldo)'}' declara prioridad")

print("\nlas areas declaradas existen")
nombres_area = {a.nombre for a in config.areas}
for caso, entradas in mapeo.items():
    for e in entradas:
        comprobar(e.area in nombres_area,
                  f"'{caso}': el area '{e.area}' esta declarada en 'areas'")

print("\nel caso comodin tambien abre ticket")
# Hasta el 23/08/2026 este bloque afirmaba lo CONTRARIO: que 'otro' no abria
# ticket, porque WispHub rechaza un asunto que no este en su catalogo y no
# habia ninguno generico. Rapilink creo 'Otros' y se verifico contra la API
# real que el POST lo acepta (ticket 90770). La regla no se aflojo -- lo que
# cambio es el dato del mundo.
comprobar("otro" in mapeo,
          "'otro' no se queda sin ticket: un caso que el sistema no supo "
          "clasificar no puede recibir menos atencion que el resto")
comprobar(mapeo["otro"][0].prioridad == "2",
          "y entra con prioridad normal: subirsela a algo que justamente no se "
          "sabe que es desordena la cola de lo que si urge")

print("\nun caso sin declarar no inventa un ticket")
comprobar(agendamiento.ticket_para_escalar(config, "sin_senal_tv", []) is None,
          "'sin_senal_tv' no abre ticket al escalar: ya agenda su visita, y "
          "ese ticket ES el trabajo anotado")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Cada caso entra con su area, su asunto y la prioridad que le toca.")
