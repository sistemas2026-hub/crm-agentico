# -*- coding: utf-8 -*-
"""
DOS COSAS QUE EL SISTEMA NO PODIA SABER, Y AHORA SI.

1. QUE HORA ES. El prompt traia el dia pero nunca la hora, a proposito: la
   hora exacta cambia el prefijo cada minuto y rompe el cacheo del proveedor
   (RNF-03). El costo aparecio en produccion el 23/09/2026 a las 13:51 de
   Bogota: "Buenos dias" a un cliente que estaba almorzando. No desobedecio
   nada -- no tenia el dato. Ahora va la FRANJA, que cambia cuatro veces al
   dia en vez de 1.440.

2. POR QUE ESCALA. 'motivo' era opcional en el esquema que llena el modelo, y
   el mismo dia una conversacion escalo con {"motivo": null}. Ese campo elige
   el texto que el cliente recibe mientras espera (uno distinto por motivo):
   sin el, le llega el generico. Y la conversacion queda en la cola humana sin
   poder decir por que.

Las dos se afirman sin modelo, sin red y sin base: una es una funcion pura y
la otra es la forma del esquema.

    py -3.13 tests/test_saludo_y_motivo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from pathlib import Path  # noqa: E402

from nucleo.config import cargar_config  # noqa: E402
from nucleo.recuperacion.prompt import _hoy_en, franja_del_dia  # noqa: E402
from nucleo.seguimiento.escalamiento import _esquema_evaluacion  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")

# ── 1. la franja ────────────────────────────────────────────────────────────
print("\n--- los bordes del saludo, que es lo unico que importa aca ---")
BORDES = [(0, "madrugada"), (5, "madrugada"), (6, "mañana"), (11, "mañana"),
          (12, "tarde"), (18, "tarde"), (19, "noche"), (23, "noche")]
for hora, esperada in BORDES:
    afirmar(franja_del_dia(hora) == esperada, f"{hora:02d}:00 es {esperada}")

afirmar(franja_del_dia(13) == "tarde",
        "LAS 13:51 SON TARDE -- la hora exacta del 'Buenos dias' que se vio en "
        "produccion el 23/09/2026")

afirmar(len({franja_del_dia(h) for h in range(24)}) == 4,
        "cuatro franjas en el dia: cuatro cambios de prefijo, no 1.440 "
        "(RNF-03, el motivo por el que no va la hora exacta)")

print("\n--- y llega al prompt ---")
linea = _hoy_en("America/Bogota")
afirmar(any(f"es de {f}" in linea for f in ("madrugada", "mañana", "tarde", "noche")),
        f"la linea de fecha dice la franja: {linea[:64]!r}")
afirmar("Hoy es" in linea and "de 20" in linea,
        "sin perder el dia, que es para lo que existia (una factura de corte "
        "el 20 no esta vencida el 13)")
afirmar(not any(c.isdigit() and ":" in linea[i:i + 2]
                for i, c in enumerate(linea)),
        "y NO trae la hora exacta: eso es lo que rompia el cacheo")

print("\n--- una zona mal escrita no deja al modelo sin fecha ---")
afirmar("Hoy es" in _hoy_en("Zona/Inventada"),
        "cae a la del servidor en vez de quedarse sin referencia")

# ── 2. el motivo ────────────────────────────────────────────────────────────
print("\n--- la escalada no puede quedarse sin motivo ---")
esquema = _esquema_evaluacion(CONFIG)
parametros = esquema["function"]["parameters"]
requeridos = parametros["required"]

afirmar("motivo" in requeridos,
        "'motivo' es obligatorio: sin el, el cliente que espera recibe el "
        "texto generico en vez del suyo")
afirmar(set(requeridos) <= set(parametros["properties"]),
        "todo lo requerido existe como propiedad (un esquema imposible no lo "
        "rechaza el modelo: lo rechaza la API, y el turno se cae)")
for campo in ("escalar", "etiqueta", "resuelta"):
    afirmar(campo in requeridos, f"'{campo}' sigue siendo obligatorio")

opciones = parametros["properties"]["motivo"]["enum"]
afirmar(len(opciones) > 0,
        f"el menu de motivos no esta vacio ({len(opciones)} opciones): un enum "
        f"vacio con el campo obligatorio hace invalido el esquema entero")
afirmar(set(opciones) <= set(CONFIG.escalamiento.activar_si),
        "y todas las opciones son motivos que el tenant declaro")

print("\n--- cada motivo que el modelo puede elegir tiene su texto ---")
# Sin esto, obligar el motivo no arregla nada: el cliente seguiria recibiendo
# el generico, solo que por otra razon.
mensajes = CONFIG.escalamiento.mensajes_por_motivo or {}
sin_texto = [m for m in opciones if not (mensajes.get(m) or "").strip()]
afirmar(not sin_texto,
        f"ninguno se queda sin mensaje para el cliente (sin texto: {sin_texto})")

print("\n--- 'baja_servicio' se clasifica por CASO, no por motivo ---")
# Se vio el 23/09/2026: una baja escalo sin motivo. La tentacion era agregar
# un motivo 'baja'; no hace falta, y seria mezclar dos ejes. El caso dice DE
# QUE TRATA, el motivo dice POR QUE pasa a una persona.
casos = list(getattr(CONFIG.manual, "casos", {}) or {})
afirmar("baja_servicio" in casos,
        "el tenant ya nombra la baja en la taxonomia de casos")
afirmar("baja_servicio" not in CONFIG.escalamiento.activar_si,
        "y NO la duplica como motivo de escalada: son dos ejes distintos")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] El modelo sabe que hora es, y no puede escalar sin decir por que.")
