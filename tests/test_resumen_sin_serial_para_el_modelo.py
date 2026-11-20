# -*- coding: utf-8 -*-
"""
EL MODELO NO RECIBE EL SERIAL DEL EQUIPO EN EL RESUMEN DE UNA ACCION (09/11/2026).

Dos mensajes en 30 dias le dijeron a un cliente "reinicio remoto de tu equipo (HWTC...)":
el resultado de proponer 'reiniciar_ont' traia el resumen para quien aprueba
("Reiniciar la ONT <serial>") y la instruccion interna lo repetia entre parentesis. Ese
resultado lo arma el motor, asi que no pasa por la lista blanca ni por 'nunca_revelar'.

Se afirma sobre el EFECTO, pasando por la funcion real de proponer:
  1. lo que recibe el modelo, en las tres salidas (pendiente, ya propuesta, en curso),
     no contiene el serial en NINGUNA parte;
  2. lo que se guarda para quien aprueba SI lo contiene (el aprobador lo necesita);
  3. un argumento que puso el modelo (no inyectado) sigue en el resumen;
  4. sin plantilla utilizable queda el nombre de la accion, nunca el valor inyectado.

    py -3.13 tests/test_resumen_sin_serial_para_el_modelo.py
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.config import cargar_config  # noqa: E402
from nucleo.modelo import motor  # noqa: E402
from nucleo.persistencia import db as persistencia  # noqa: E402

FALLOS = []
SERIAL = "HWTC1A2B3C4D"


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


cfg = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
reiniciar = next(h for h in cfg.herramientas if h.nombre == "reiniciar_ont")
afirmar("sn_onu" in reiniciar.inyectados_obligatorios and "{sn_onu}" in (reiniciar.plantilla_resumen or ""),
        "(partida) el reinicio inyecta el serial y su plantilla lo nombra: si no, esto no probaria nada")


def proponer(ya_existia=False, autonomia=False):
    guardado = {}

    def guardar(tenant, nombre, argumentos, resumen, *a, **k):
        guardado["resumen"] = resumen
        return "acc-1", ya_existia

    sustitutos = [
        (motor, "_resolver_argumentos", lambda h, s, a: {"sn_onu": SERIAL}),
        (motor, "_politica_de", lambda *a, **k: None),
        (motor, "_contexto_de_revalidacion", lambda *a, **k: {}),
        (motor, "_tiene_autonomia_ganada", lambda *a, **k: autonomia),
        (persistencia, "guardar_accion_propuesta", guardar),
    ]
    originales = [(o, a, getattr(o, a)) for o, a, _ in sustitutos]
    for o, a, f in sustitutos:
        setattr(o, a, f)
    try:
        salida = motor._ejecutar_propuesta_de_accion(
            reiniciar, None, {}, "rapilink", "cliente_final", "bot",
            config=cfg, historial=[], origen="wamid.PRUEBA")
    finally:
        for o, a, f in originales:
            setattr(o, a, f)
    return salida, guardado


print("\n1. lo que recibe el modelo no lleva el serial, salga por donde salga")
for nombre, kw in (("pendiente de aprobacion", {}), ("ya estaba propuesta", {"ya_existia": True}),
                   ("autonomia ganada (en curso)", {"autonomia": True})):
    salida, guardado = proponer(**kw)
    afirmar(SERIAL not in json.dumps(salida, ensure_ascii=False), f"{nombre}: ni el resumen ni la instruccion lo traen")
    afirmar(bool(salida.get("accion_id")) and "instruccion_interna" in salida,
            f"{nombre}: la propuesta sigue completa (id e instruccion)")

print("\n2. quien aprueba SI lo ve")
afirmar(SERIAL in guardado["resumen"], "el resumen guardado para el aprobador conserva el serial")

print("\n3. un argumento del modelo se queda")
falsa = SimpleNamespace(nombre="registrar_algo", plantilla_resumen="Registrar la factura {id}",
                        inyectados_obligatorios=["sn_onu"])
afirmar(motor._resumen_para_el_modelo(falsa, {"id": 999001, "sn_onu": SERIAL}) == "Registrar la factura 999001",
        "lo que el modelo pidio sigue en el resumen")

print("\n4. sin plantilla utilizable, el nombre de la accion")
sin_plantilla = SimpleNamespace(nombre="reiniciar_ont", plantilla_resumen=None, inyectados_obligatorios=["sn_onu"])
r = motor._resumen_para_el_modelo(sin_plantilla, {"sn_onu": SERIAL})
afirmar(SERIAL not in r and "reiniciar" in r, f"sin plantilla: '{r}'")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] El modelo sabe que se pidio un reinicio, no el serial del equipo.")
