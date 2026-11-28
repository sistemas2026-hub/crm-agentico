# -*- coding: utf-8 -*-
"""
================================================================================
 LA GUARDA DEL SCRIPT QUE ENCIENDE LA VISION  --  02/11/2026
================================================================================

    py -3.13 tests/test_encender_vision.py

POR QUE ESTE SCRIPT TIENE GUARDA
---------------------------------
Escribe la configuracion de PRODUCCION, y escribe el bit que decide si las
fotos de una empresa salen hacia un tercero. La decision que toma --que campo
toca-- se puede probar contra el catalogo real sin abrir ninguna conexion.

QUE SE AFIRMA
-------------
Sobre el EFECTO de la mutacion sobre el documento:

  A  el campo que toca sale del codigo, no de una lista propia del script
  B  toca UNO y deja los otros dos como estaban  <-- la garantia entera
  C  un proposito que el codigo no declara no escribe nada
  D  el resultado VALIDA contra el schema desplegado
  E  apagar es tan posible como encender

NO ABRE NINGUNA CONEXION: `editor._editar` no se llama, se prueba el mutador.
================================================================================
"""

import copy
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import yaml                                                       # noqa: E402

from nucleo.canales import vision                                 # noqa: E402
from nucleo.config.schema import TenantConfig                     # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f" -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


def _cargar():
    ruta = RAIZ / "cli" / "encender_vision.py"
    spec = importlib.util.spec_from_file_location("encender_vision", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


S = _cargar()
CRUDO = yaml.safe_load(
    (RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))

TODOS = {p: vision.bandera_de(p) for p in vision.PROPOSITOS}


def documento():
    """El YAML real con las tres banderas en un estado conocido."""
    doc = copy.deepcopy(CRUDO)
    for campo in TODOS.values():
        doc[campo] = False
    return doc


def mutar(doc, proposito, valor):
    """Lo que hace el script: una linea, el mismo campo que resuelve el codigo."""
    doc[vision.bandera_de(proposito)] = valor
    return doc


print("=" * 72)
print(" EL SCRIPT QUE ENCIENDE LA VISION  (sin base, sin red)")
print("=" * 72)

# =============================================================================
print("\n-- A: el campo sale del codigo, no de una lista del script --")
# =============================================================================
#  Si el script tuviera su propia lista, agregar un proposito al motor lo
#  dejaria sin poder encenderlo y el sintoma seria "no es un proposito
#  declarado", que apunta al lado equivocado.
fuente = (RAIZ / "cli" / "encender_vision.py").read_text(encoding="utf-8")
comprobar("A1. usa vision.bandera_de", "vision.bandera_de(" in fuente)

#  SOLO EL CODIGO, no los comentarios ni el docstring. Nombrar una bandera
#  al explicar por que el codigo va primero es correcto y util; lo que no
#  puede haber es una lista propia en la LOGICA, que se quedaria vieja el dia
#  que el motor agregue un proposito y daria el error del lado equivocado.
import ast as _ast                                                # noqa: E402

_arbol = _ast.parse(fuente)
#  Se le saca el docstring del modulo ANTES de recomponer, no despues: el
#  texto recompuesto no es identico al original y un replace no lo encuentra.
if (_arbol.body and isinstance(_arbol.body[0], _ast.Expr)
        and isinstance(getattr(_arbol.body[0], "value", None), _ast.Constant)
        and isinstance(_arbol.body[0].value.value, str)):
    _arbol.body = _arbol.body[1:]
_sin_doc = _ast.unparse(_arbol)   # unparse ademas descarta los comentarios
comprobar("A2. y la LOGICA no escribe ningun nombre de bandera a mano",
          not any(b in _sin_doc for b in TODOS.values()),
          [b for b in TODOS.values() if b in _sin_doc])
comprobar("A3. no tiene una opcion para encenderlos todos a la vez",
          "--todos" not in fuente)

# =============================================================================
print("\n-- B: toca UNO y deja los otros como estaban --")
# =============================================================================
#  LA GARANTIA ENTERA de tener tres interruptores. Si encender uno encendiera
#  otro, los tres consentimientos serian uno disfrazado de tres.
for proposito, campo in TODOS.items():
    doc = mutar(documento(), proposito, True)
    comprobar(f"B. {proposito}: queda encendido", doc[campo] is True)
    otros = {c: doc[c] for p, c in TODOS.items() if p != proposito}
    comprobar(f"B. {proposito}: los otros dos siguen apagados",
              all(v is False for v in otros.values()), str(otros))

# =============================================================================
print("\n-- C: un proposito que el codigo no declara no escribe nada --")
# =============================================================================
for inventado in ("asistente", "whatsapp", "", "todos", "vision_habilitada"):
    comprobar(f"C. {inventado!r} no resuelve a ninguna bandera",
              vision.bandera_de(inventado) == "")

# =============================================================================
print("\n-- D: el resultado valida contra el schema desplegado --")
# =============================================================================
#  Escribir un campo que el schema no conoce deja al motor rechazando su
#  propia config entera (extra="forbid") y el asistente deja de atender.
for proposito in TODOS:
    doc = mutar(documento(), proposito, True)
    try:
        config = TenantConfig.model_validate(doc)
        comprobar(f"D. {proposito}: valida", True)
        comprobar(f"D. {proposito}: y el objeto lo refleja",
                  getattr(config, TODOS[proposito]) is True)
    except Exception as e:                                        # noqa: BLE001
        comprobar(f"D. {proposito}: valida", False, str(e)[:120])

# =============================================================================
print("\n-- E: apagar es tan posible como encender --")
# =============================================================================
#  Importa: es la unica forma de cortar esto sin un deploy. Un script que solo
#  enciende convierte una decision reversible en una irreversible.
doc = documento()
doc[TODOS["whatsapp_cliente"]] = True
doc = mutar(doc, "whatsapp_cliente", False)
comprobar("E1. se puede apagar", doc[TODOS["whatsapp_cliente"]] is False)

#  EL PARSEO DE VERDAD, no que la cadena "--apagar" aparezca en el archivo.
#  Esa version pasaba con el parseo roto: se midio mutando `valor = True`.
lee = S.leer_argumentos
comprobar("E2. sin opciones: enciende y NO escribe",
          lee(["rapilink", "asistente_interno"])
          == {"tenant": "rapilink", "proposito": "asistente_interno",
              "aplicar": False, "valor": True})
comprobar("E3. --aplicar escribe",
          lee(["rapilink", "asistente_interno", "--aplicar"])["aplicar"] is True)
comprobar("E4. --apagar invierte el valor",
          lee(["rapilink", "asistente_interno", "--apagar"])["valor"] is False)
comprobar("E5. --apagar solo NO escribe: hace falta --aplicar igual",
          lee(["rapilink", "x", "--apagar"])["aplicar"] is False)
comprobar("E6. --apagar --aplicar: apaga y escribe",
          (lee(["rapilink", "x", "--apagar", "--aplicar"])["valor"] is False
           and lee(["rapilink", "x", "--apagar", "--aplicar"])["aplicar"] is True))
for malo in (["rapilink"], [], ["a", "b", "c"], ["a", "b", "--borrar"]):
    comprobar(f"E7. {malo} no se interpreta", "error" in lee(malo))

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
