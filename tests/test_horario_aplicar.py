# -*- coding: utf-8 -*-
"""
EL SCRIPT QUE LLEVA EL HORARIO DE ATENCION A LA BASE (sin tocar la base).

Se afirma sobre la config de ANTES (la del YAML sin el horario) para ver el EFECTO:
que el resultado valida, que el prompt queda igual al del repo, que no pisa lo que la
base tiene y el repo no, que repetirlo no cambia nada, y que si alguien edito el prompt
desde /agentes aborta sin escribir.

    py -3.13 tests/test_horario_aplicar.py
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

from cli import aplicar_horario_de_atencion as A  # noqa: E402
from nucleo.config.schema import TenantConfig  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))

antes = copy.deepcopy(DOC)
antes["herramientas"] = [h for h in antes["herramientas"] if h["nombre"] not in A.HERRAMIENTAS]
for nombre in A.ROLES:
    rol = antes["roles"][nombre]
    rol["puede_consultar"].remove(A.HERRAMIENTA)
    del rol["campos_permitidos"][A.HERRAMIENTA]
prompt_yaml = antes["roles"][A.ROL_ROUTER]["descripcion"]
antes["roles"][A.ROL_ROUTER]["descripcion"] = (
    prompt_yaml.replace(A.NUEVO_NO_SE, A.ANCLA_NO_SE).replace(A.NUEVO_HORARIOS, A.ANCLA_HORARIOS))
afirmar(antes["roles"][A.ROL_ROUTER]["descripcion"] != prompt_yaml,
        "(el agregado del script es el que esta en el YAML: si no, esto no habria cambiado nada)")
antes["roles"]["soporte_tecnico_cliente"]["campos_permitidos"]["consultar_mi_servicio"].append("campo_solo_de_la_base")

print("\nEl script sobre la config de ANTES")
herramientas, campos = A.semilla("rapilink")
avisos = []
A.mutar(antes, herramientas, campos, avisos)
despues = TenantConfig.model_validate(antes)
nombres = {h.nombre for h in despues.herramientas}
afirmar(set(A.HERRAMIENTAS) <= nombres, "agrega las dos herramientas y la config resultante VALIDA")
afirmar({n for n, r in despues.roles.items() if A.HERRAMIENTA in r.puede_consultar} == set(A.ROLES),
        "se la da solo a los cuatro roles de cliente")
afirmar(not any("leer_calendario_laboral" in r.puede_consultar for r in despues.roles.values()),
        "la lectora no se la da a ningun agente")
afirmar(" ".join(despues.roles[A.ROL_ROUTER].descripcion.split()) == " ".join(prompt_yaml.split()),
        "el prompt del router queda IDENTICO al del YAML (el repo y la base dicen lo mismo)")
afirmar("campo_solo_de_la_base" in despues.roles["soporte_tecnico_cliente"].campos_permitidos["consultar_mi_servicio"],
        "no toca lo que la base tenia y el repo no")

antes2 = copy.deepcopy(antes)
avisos2 = []
A.mutar(antes2, herramientas, campos, avisos2)
afirmar(antes2 == antes and "prompt: ya estaba" in avisos2, "una segunda pasada no cambia nada (idempotente)")

print("\nSi alguien edito el prompt desde /agentes")
editado = copy.deepcopy(DOC)
editado["herramientas"] = [h for h in editado["herramientas"] if h["nombre"] not in A.HERRAMIENTAS]
editado["roles"][A.ROL_ROUTER]["descripcion"] = "Un prompt que alguien edito desde /agentes."
copia = copy.deepcopy(editado)
try:
    A.mutar(editado, herramientas, campos, [])
    aborto = False
except SystemExit:
    aborto = True
afirmar(aborto and editado == copia, "ABORTA sin escribir nada (ni herramientas ni permisos)")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] El script lleva el horario a la base sin pisar nada.")
