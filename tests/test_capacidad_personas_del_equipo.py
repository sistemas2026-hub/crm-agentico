# -*- coding: utf-8 -*-
"""
================================================================================
 CAPACIDAD: LAS PERSONAS DEL EQUIPO SALEN DE /team SI NADIE LAS DECLARO
================================================================================

    py -3.13 tests/test_capacidad_personas_del_equipo.py

12/11/2026. 'capacidad.personas_del_equipo' se declaraba a mano aunque el CRM
ya sabe cuantas personas activas tienen un area de atencion. La capa servidor
del frontend las cuenta y las manda en 'personas_equipo'; el motor las usa
SOLO si la empresa no declaro otro numero, y dice de donde salio el que uso.

Lo que se afirma es la DECISION de la ruta (que numero llega a componer() y que
origen se informa). La medicion y el calculo se prueban contra PostgreSQL en
tests/test_tablero_capacidad_base.py; aca se sustituyen.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.config.schema import TenantConfig                       # noqa: E402
from nucleo.observabilidad import capacidad as tablero              # noqa: E402
from nucleo.persistencia import capacidad as medicion               # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
DOC = cargar_config(yamls[0]).model_dump(mode="json")
estado = {"declarado": None}
recibido = {}


def _config(_t):
    doc = dict(DOC)
    doc["capacidad"] = {**(DOC.get("capacidad") or {}), "personas_del_equipo": estado["declarado"]}
    return TenantConfig(**doc)


def _componer(m, mc, mv, personas):
    recibido["personas"] = personas
    return {}


reales = (api._config_de, medicion.medir, tablero.componer)
api._config_de = _config
medicion.medir = lambda *a, **k: {}
tablero.componer = _componer

try:
    with api.app.test_client() as c:
        def pedir(extra=""):
            r = c.get(f"/reportes/capacidad?tenant=prueba&dias=30{extra}")
            return r.status_code, r.get_json() or {}

        estado["declarado"] = None
        st, d = pedir("&personas_equipo=5")
        comprobar(st == 200 and recibido["personas"] == 5,
                  f"sin declarar, el calculo usa las personas contadas en /team ({st})")
        comprobar(d.get("personas_origen") == "equipo" and d.get("personas_usadas") == 5,
                  "y dice que salieron del equipo")
        comprobar(d["declarado"]["personas_del_equipo"] is None,
                  "lo declarado sigue vacio: el conteo no se escribe en la config")

        estado["declarado"] = 3
        st, d = pedir("&personas_equipo=5")
        comprobar(recibido["personas"] == 3 and d.get("personas_origen") == "declarado",
                  "EFECTO: lo declarado manda sobre el conteo (es la correccion manual)")

        estado["declarado"] = None
        for malo in ("", "&personas_equipo=0", "&personas_equipo=-2", "&personas_equipo=dos"):
            st, d = pedir(malo)
            comprobar(st == 200 and recibido["personas"] is None and d.get("personas_origen") is None,
                      f"sin conteo valido ('{malo or 'ausente'}') no se inventa un numero")
finally:
    api._config_de, medicion.medir, tablero.componer = reales

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo en verde.")
