# -*- coding: utf-8 -*-
"""
================================================================================
 LA GUARDA DEL SCRIPT QUE ABRE EL CIERRE DEL SUPERVISOR  --  31/10/2026
================================================================================

    py -3.13 tests/test_abrir_cierre_del_supervisor.py

POR QUE ESTE SCRIPT TIENE GUARDA Y OTROS NO
-------------------------------------------
'cli/abrir_cierre_del_supervisor.py' escribe la configuracion de PRODUCCION, y
escribe justo el bit que deja al Supervisor ejecutar una accion sobre un
tercero. Un script asi no se prueba corriendolo contra la base: se prueba la
decision que toma --a que herramienta le pone que-- contra el catalogo real,
sin tocar nada.

QUE SE AFIRMA
-------------
Sobre el EFECTO de la mutacion sobre el documento, y contra el YAML REAL del
tenant, no uno inventado:

  A  elige la herramienta por su CAPACIDAD, no por su nombre
  B  deja los dos campos, y el resultado VALIDA contra el schema desplegado
  C  es idempotente: correrlo dos veces no duplica la exencion
  D  se niega cuando hay 0 o mas de 1 candidata (no adivina)
  E  se niega si la herramienta no declara 'aprobacion_humana'
  F  no toca ninguna OTRA herramienta

NO ABRE NINGUNA CONEXION. 'editor._editar' no se llama: lo que se prueba es
'_mutar', que es donde vive la decision.
================================================================================
"""

import copy
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import yaml                                                       # noqa: E402

from nucleo.config.schema import TenantConfig                     # noqa: E402
from nucleo.seguridad import frontera                             # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


def _cargar_script():
    ruta = RAIZ / "cli" / "abrir_cierre_del_supervisor.py"
    spec = importlib.util.spec_from_file_location("abrir_cierre", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


S = _cargar_script()
YAML_REAL = yaml.safe_load(
    (RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))


def documento_como_la_base() -> dict:
    """El YAML real, pero SIN los dos campos: asi esta la base antes de correrlo."""
    doc = copy.deepcopy(YAML_REAL)
    herr = S._la_del_cierre(doc)
    herr.pop("aprobacion_humana_salvo", None)
    herr.pop("nivel_autonomia", None)
    return doc


print("=" * 72)
print(" EL SCRIPT QUE ABRE EL CIERRE DEL SUPERVISOR  (sin base, sin red)")
print("=" * 72)

# =============================================================================
print("\n-- A: elige por capacidad, no por nombre --")
# =============================================================================
doc = documento_como_la_base()
elegida = S._la_del_cierre(doc)
comprobar("A1. encuentra la herramienta del cierre",
          elegida.get("nombre") == "cerrar_ticket_operativo",
          str(elegida.get("nombre")))
comprobar("A2. y la eligio por la capacidad", bool(elegida.get(S.CAPACIDAD)))

# =============================================================================
print("\n-- B: deja los dos campos, y el resultado valida --")
# =============================================================================
antes = {h["nombre"]: copy.deepcopy(h) for h in doc["herramientas"]
         if isinstance(h, dict) and h.get("nombre")}
S._mutar(doc)
quedo = S._la_del_cierre(doc)
comprobar("B1. deja la exencion",
          quedo.get("aprobacion_humana_salvo") == [frontera.CIERRE_DE_ORDEN_REVISADA],
          str(quedo.get("aprobacion_humana_salvo")))
comprobar("B2. deja el nivel 3", quedo.get("nivel_autonomia") == 3,
          str(quedo.get("nivel_autonomia")))
comprobar("B3. y NO le quita la marca de aprobacion humana",
          quedo.get("aprobacion_humana") is True)
try:
    TenantConfig.model_validate(doc)
    comprobar("B4. el documento resultante valida contra el schema", True)
except Exception as e:                                            # noqa: BLE001
    comprobar("B4. el documento resultante valida contra el schema", False,
              str(e)[:140])

# =============================================================================
print("\n-- C: idempotente --")
# =============================================================================
S._mutar(doc)
S._mutar(doc)
comprobar("C1. tres pasadas no duplican la exencion",
          S._la_del_cierre(doc).get("aprobacion_humana_salvo")
          == [frontera.CIERRE_DE_ORDEN_REVISADA],
          str(S._la_del_cierre(doc).get("aprobacion_humana_salvo")))

# =============================================================================
print("\n-- F: no toca ninguna OTRA herramienta --")
# =============================================================================
#  Va antes que D y E a proposito: usa el 'doc' ya mutado de arriba.
cambiadas = [n for n, h in antes.items()
             if h != next((x for x in doc["herramientas"]
                           if isinstance(x, dict) and x.get("nombre") == n), None)]
comprobar("F1. solo cambia la del cierre", cambiadas == ["cerrar_ticket_operativo"],
          str(cambiadas[:5]))

# =============================================================================
print("\n-- D: no adivina cuando hay 0 o mas de 1 --")
# =============================================================================
vacio = {"herramientas": []}
try:
    S._la_del_cierre(vacio)
    comprobar("D1. sin ninguna candidata se niega", False, "eligio igual")
except S.NoSePudo as e:
    comprobar("D1. sin ninguna candidata se niega", "hay 0" in str(e), str(e)[:80])

doble = copy.deepcopy(documento_como_la_base())
gemela = copy.deepcopy(S._la_del_cierre(doble))
gemela["nombre"] = "cerrar_ticket_operativo_bis"
doble["herramientas"].append(gemela)
try:
    S._la_del_cierre(doble)
    comprobar("D2. con dos candidatas se niega", False, "eligio una")
except S.NoSePudo as e:
    comprobar("D2. con dos candidatas se niega", "hay 2" in str(e), str(e)[:80])

# =============================================================================
print("\n-- E: no exime lo que no tiene la marca --")
# =============================================================================
#  Eximir una herramienta sin 'aprobacion_humana' no hace nada y deja escrito
#  que si. El schema tambien lo rechaza; esto falla antes, con el motivo.
sin_marca = documento_como_la_base()
S._la_del_cierre(sin_marca)["aprobacion_humana"] = False
try:
    S._mutar(sin_marca)
    comprobar("E1. sin la marca se niega", False, "la escribio igual")
except S.NoSePudo as e:
    comprobar("E1. sin la marca se niega", "no declara" in str(e), str(e)[:80])

# =============================================================================
print("\n-- G: el nombre de la exencion sale del codigo, no de una cadena --")
# =============================================================================
#  Si el script tuviera el nombre escrito a mano, un cambio en frontera lo
#  dejaria pidiendo una exencion que ya no existe -- y el sintoma seria
#  'APROBACION_HUMANA_REQUERIDA', que no apunta aca.
comprobar("G1. usa frontera.CIERRE_DE_ORDEN_REVISADA",
          S.EXENCION == frontera.CIERRE_DE_ORDEN_REVISADA, S.EXENCION)
comprobar("G2. y ese nombre existe en el catalogo de exenciones",
          S.EXENCION in frontera.EXENCIONES)

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
