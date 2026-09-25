# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- reporte de comprobante de pago (nucleo/herramientas/pagos.py)
================================================================================

Corre sin base, sin red y sin modelo:

    py -3.13 tests/test_pagos_comprobante.py

Existe para demostrar, con ejecucion real (no solo lectura de codigo), lo que
la auditoria de Fase #7 identifico como riesgo central: que un reporte de
pago incompleto o que ni siquiera parece un comprobante NO puede terminar en
el mismo lugar (escalar_al_completar) que uno completo. Ver tambien la
seccion nueva de tests/test_escalada_forzada.py y tests/test_condiciones_herramienta.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.herramientas import pagos  # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


print("=" * 70)
print(" REPORTE DE COMPROBANTE DE PAGO")
print("=" * 70)

print("\nCASO 1 -- reporte completo: COMPROBANTE_RECIBIDO")
completo = pagos.procesar_reporte(None, {
    "valor_reportado": "50000", "fecha_comprobante": "2026-09-03",
    "referencia": "ABC123", "medio_pago": "Nequi",
    "nombre_cliente": "Juan Perez", "id_cliente_sesion": "6555"})
afirmar(completo["estado"] == pagos.COMPROBANTE_RECIBIDO,
        "valor + fecha + referencia -> COMPROBANTE_RECIBIDO")
afirmar(completo["faltantes"] == [], "y no falta nada que pedir")
afirmar("VALIDACIÓN DE PAGO" in completo["resumen"],
        "el resumen arranca con el encabezado que pide la Fase #7")
afirmar("Juan Perez" in completo["resumen"] and "6555" in completo["resumen"],
        "el cliente y su identificacion (de la SESION, no del modelo) estan en el resumen")
afirmar(pagos.ADVERTENCIA in completo["resumen"],
        "la advertencia exacta pedida por la Fase #7 esta completa, palabra por palabra")
afirmar("pago fue confirmado" not in completo["resumen"].lower()
        and "servicio sera reconectado" not in completo["resumen"].lower(),
        "el resumen nunca dice que el pago se confirmo ni que el servicio se reconecta")

print("\nCASO 2 -- solo valor, sin fecha NI referencia: COMPROBANTE_INCOMPLETO")
solo_valor = pagos.procesar_reporte(None, {"valor_reportado": "50000"})
afirmar(solo_valor["estado"] == pagos.COMPROBANTE_INCOMPLETO,
        "valor solo, sin fecha ni referencia, no alcanza")
afirmar("la fecha del pago o el numero de referencia" in solo_valor["faltantes"][0],
        "y dice exactamente que falta")

print("\nCASO 3 -- sin valor (aunque haya fecha y referencia): COMPROBANTE_INCOMPLETO")
sin_valor = pagos.procesar_reporte(None, {
    "fecha_comprobante": "2026-09-03", "referencia": "ABC123"})
afirmar(sin_valor["estado"] == pagos.COMPROBANTE_INCOMPLETO,
        "sin el valor pagado, tampoco alcanza -- es el dato imprescindible")
afirmar("el valor pagado" in sin_valor["faltantes"], "y lo dice explicito")

print("\nCASO 4 -- el cliente dice que la foto no se ve bien: COMPROBANTE_ILEGIBLE")
ilegible = pagos.procesar_reporte(None, {
    "valor_reportado": "50000", "fecha_comprobante": "2026-09-03", "legible": "no"})
afirmar(ilegible["estado"] == pagos.COMPROBANTE_ILEGIBLE,
        "'legible: no' pesa MAS que tener valor y fecha completos -- si el cliente dice "
        "que no se ve, no se sigue adelante con datos que el mismo puso en duda")

print("\nCASO 5 -- nada que sugiera un pago: NO_PARECE_COMPROBANTE")
vacio = pagos.procesar_reporte(None, {})
afirmar(vacio["estado"] == pagos.NO_PARECE_COMPROBANTE,
        "sin ningun dato, no se asume que es un reporte de pago")
afirmar(vacio["faltantes"] == [],
        "y no le pide nada puntual -- no hay de que partir")

print("\nnada revienta con entradas raras")
afirmar(pagos.procesar_reporte(None, {})["estado"] == pagos.NO_PARECE_COMPROBANTE,
        "argumentos vacios no explota")
raro = pagos.procesar_reporte(None, {"valor_reportado": None, "legible": None})
afirmar(raro["estado"] == pagos.NO_PARECE_COMPROBANTE,
        "valores None (no strings) no explotan")

print("\nel modelo NUNCA decide 'legible' por su cuenta -- solo si el cliente lo dijo")
# Ausente = el cliente no dijo nada del tema. Es el caso mas comun y tiene
# que comportarse igual que si 'legible' nunca hubiera existido como campo.
sin_mencion = pagos.procesar_reporte(None, {
    "valor_reportado": "50000", "fecha_comprobante": "2026-09-03"})
afirmar(sin_mencion["estado"] == pagos.COMPROBANTE_RECIBIDO,
        "sin mencionar legibilidad, el reporte se evalua solo por los datos que trae")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: un reporte de pago nunca se confunde con uno confirmado.")
print("=" * 70)
