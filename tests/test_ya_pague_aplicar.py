# -*- coding: utf-8 -*-
"""
EL PARRAFO "YA PAGUE" LLEGA A LA BASE SIN PISAR NADA (sin tocar la base).

Se afirma sobre la config de ANTES (el prompt sin el parrafo) para ver el EFECTO: que valida,
que el prompt queda igual al del repo, que no toca lo que solo la base tiene, que repetirlo
no cambia nada, y que si alguien edito el prompt aborta sin escribir.

    py -3.13 tests/test_ya_pague_aplicar.py
"""
import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import yaml  # noqa: E402

from cli import aplicar_ya_pague as A  # noqa: E402
from nucleo.config.schema import TenantConfig  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
nuevo = A.parrafo("rapilink")
completo = DOC["roles"][A.ROL]["descripcion"]

print("\nEl parrafo que sale del repo")
afirmar(nuevo.startswith(A.MARCA) and "reportar_comprobante_pago" in nuevo and nuevo.count("\n\n") == 0,
        "es UN parrafo, empieza en la marca y nombra la herramienta que existe")
afirmar("quieres que un colaborador" in nuevo and "AHI MISMO" in nuevo,
        "dice que NO se pregunte si quiere un colaborador y que se pidan los datos en el mismo mensaje")

print("\nEl script sobre la config de ANTES")
antes = copy.deepcopy(DOC)
sin = completo.replace(A.ANCLA + "\n" + nuevo, A.ANCLA, 1)
afirmar(sin != completo and A.MARCA not in sin, "(la config de antes no tiene el parrafo)")
antes["roles"][A.ROL]["descripcion"] = sin
antes["roles"]["soporte_tecnico_cliente"]["campos_permitidos"]["consultar_mi_servicio"].append("solo_de_la_base")
avisos = []
A.mutar(antes, nuevo, avisos)
despues = TenantConfig.model_validate(antes)
afirmar(" ".join(despues.roles[A.ROL].descripcion.split()) == " ".join(completo.split()),
        "el prompt queda IDENTICO al del repo (repo y base dicen lo mismo)")
afirmar("solo_de_la_base" in despues.roles["soporte_tecnico_cliente"].campos_permitidos["consultar_mi_servicio"],
        "no toca lo que la base tenia y el repo no")
copia = copy.deepcopy(antes)
avisos2 = []
A.mutar(antes, nuevo, avisos2)
afirmar(antes == copia and avisos2 == ["prompt: ya estaba"], "una segunda pasada no cambia nada (idempotente)")

print("\nSi alguien edito el prompt desde /agentes")
editado = copy.deepcopy(DOC)
editado["roles"][A.ROL]["descripcion"] = "Un prompt que alguien edito."
copia = copy.deepcopy(editado)
try:
    A.mutar(editado, nuevo, [])
    aborto = False
except SystemExit:
    aborto = True
afirmar(aborto and editado == copia, "ABORTA sin escribir nada")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] El parrafo llega a la base sin pisar nada.")
