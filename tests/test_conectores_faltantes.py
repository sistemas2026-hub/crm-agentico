# -*- coding: utf-8 -*-
"""
================================================================================
 CONECTORES: LO QUE FALTA, MIRANDO LO QUE YA ESTA  --  12/11/2026
================================================================================

    py -3.13 tests/test_conectores_faltantes.py

Hasta el 12/11/2026 'catalogo.preparar' listaba como faltantes TODOS los
secretos del conector, cargados o no (auditoria del menu, §2). Se prueba por
HTTP (POST /conectores/<id>/preparar), con 'secretos.listar' y la config
sustituidos: la decision --que falta-- corre real.

Tambien el PUT /agentes/areas/<nombre> con 'ficha_cliente' (pedido del agente
G): la forma se valida en la ruta, y un rechazo del esquema es un 400 con su
motivo, no el 404 de "no existe el area" que daba antes por heredar de
ValueError.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import yaml                                                         # noqa: E402

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config, editor                     # noqa: E402
from nucleo.config.schema import TenantConfig                       # noqa: E402
from nucleo.seguridad import secretos                               # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
DOC = cargar_config(yamls[0]).model_dump(mode="json")
ID = "smartolt"
CONECTOR = yaml.safe_load((RAIZ / "conectores" / f"{ID}.yaml").read_text(encoding="utf-8"))
DECLARADOS = [s["nombre"] for s in CONECTOR["secretos"]]
VARIABLES = [v["nombre"] for v in CONECTOR["variables"]]
AREA = next(iter(CONECTOR["areas"]))
ROL = next(iter(DOC["roles"]))

#  Las variables del tenant de prueba, SIN las del conector: el esquema exige
#  que existan las que nombran sus herramientas, asi que no se vacian.
BASE_VARIABLES = {k: v for k, v in (DOC.get("variables_tenant") or {}).items() if k not in VARIABLES}
estado = {"cargados": [], "variables": dict(BASE_VARIABLES)}


def _config(_t):
    doc = dict(DOC)
    doc["variables_tenant"] = dict(estado["variables"])
    return TenantConfig(**doc)


def _listar(_t):
    if estado["cargados"] is None:
        raise RuntimeError("la base no contesta")
    return [{"nombre": n} for n in estado["cargados"]]


reales = (api._config_de, secretos.listar, editor._editar)
api._config_de = _config
secretos.listar = _listar

try:
    with api.app.test_client() as c:
        def preparar():
            r = c.post(f"/conectores/{ID}/preparar", json={"tenant": "prueba", "areas": {AREA: ROL}})
            return r.status_code, r.get_json() or {}

        print("\n-- secretos --")
        estado["cargados"] = []
        st, d = preparar()
        comprobar(st == 200 and d["faltan_secretos"] == DECLARADOS and d["credenciales_listas"] is False,
                  f"sin nada cargado faltan todos los del conector ({st})")
        comprobar(d["secretos"] == DECLARADOS, "'secretos' sigue listando los declarados (compatibilidad)")

        estado["cargados"] = DECLARADOS + ["OTRO_QUE_NO_ES_DEL_CONECTOR"]
        st, d = preparar()
        comprobar(d["faltan_secretos"] == [] and d["credenciales_listas"] is True,
                  "EFECTO: con todos cargados no falta ninguno y dice «listas»")

        estado["cargados"] = None
        st, d = preparar()
        comprobar(st == 200 and d["faltan_secretos"] == DECLARADOS and d["credenciales_listas"] is False,
                  "si no se pudo leer, NO afirma «listas»: faltan todos (no se sabe)")

        print("\n-- variables --")
        estado["cargados"] = []
        st, d = preparar()
        comprobar(d["faltan_variables"] == VARIABLES, "sin variables cargadas faltan las del conector")
        estado["variables"] = {**BASE_VARIABLES, VARIABLES[0]: "https://algo.ejemplo"}
        st, d = preparar()
        comprobar(VARIABLES[0] not in d["faltan_variables"],
                  "una variable ya cargada en la config no figura como faltante")

        print("\n-- variables: quien las usa --")
        estado["variables"] = dict(BASE_VARIABLES)
        r = c.get("/configuracion/variables?tenant=prueba")
        d = r.get_json() or {}
        cfg = _config(None)
        con_ref = next((h for h in cfg.herramientas if h.base_url_ref and h.base_url_ref in BASE_VARIABLES), None)
        comprobar(r.status_code == 200 and d.get("variables") == BASE_VARIABLES,
                  f"el GET sigue devolviendo las variables tal cual ({r.status_code})")
        if con_ref:
            comprobar(con_ref.nombre in d.get("usos", {}).get(con_ref.base_url_ref, []),
                      f"EFECTO: '{con_ref.base_url_ref}' figura usada por '{con_ref.nombre}' (su base_url_ref)")
        else:
            comprobar(False, "el tenant de prueba no tiene ninguna herramienta con base_url_ref cargada")
        comprobar(isinstance(d.get("faltan"), dict), "y trae 'faltan' (vacio si todo esta)")

        print("\n-- areas: ficha_cliente --")
        capturado = {}

        def _editar_que_captura(tenant, mutar):
            doc = {"areas": [{"nombre": "soporte", "etiqueta": "Soporte"}]}
            mutar(doc)
            capturado["doc"] = doc
            return None

        editor._editar = _editar_que_captura
        r = c.put("/agentes/areas/soporte", json={"tenant": "t", "ficha_cliente": [" nombre ", "telefono", ""]})
        comprobar(r.status_code == 200 and capturado["doc"]["areas"][0]["ficha_cliente"] == ["nombre", "telefono"],
                  f"una lista de campos llega al documento, limpia ({r.status_code})")
        r = c.put("/agentes/areas/soporte", json={"tenant": "t", "ficha_cliente": None})
        comprobar(r.status_code == 200 and "ficha_cliente" not in capturado["doc"]["areas"][0],
                  "null la quita: vuelve al defecto seguro del motor")
        capturado.clear()
        r = c.put("/agentes/areas/soporte", json={"tenant": "t", "ficha_cliente": "cedula"})
        comprobar(r.status_code == 400 and not capturado, "un texto suelto no es una lista: 400 sin tocar nada")

        def _editar_que_rechaza(tenant, mutar):
            raise editor.ErrorEdicion("areas: ficha_cliente nombra campos que no existen (cédula)")

        editor._editar = _editar_que_rechaza
        r = c.put("/agentes/areas/soporte", json={"tenant": "t", "ficha_cliente": ["cédula"]})
        comprobar(r.status_code == 400 and "no existen" in (r.get_json() or {}).get("error", ""),
                  f"un rechazo del esquema es 400 con su motivo, no 404 ({r.status_code})")
finally:
    api._config_de, secretos.listar, editor._editar = reales

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo en verde.")
