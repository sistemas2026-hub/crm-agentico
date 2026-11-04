# -*- coding: utf-8 -*-
"""
================================================================================
 EL FORMULARIO DE AGENTES, POR LA RUTA DEL MOTOR  --  02/11/2026
================================================================================

Lo que el formulario manda ademas desde el 02/11/2026 -- que temas atiende,
si se conecta al router, si verifica identidad, que nunca revela -- tiene que
llegar al editor por POST/PUT /agentes, y el catalogo tiene que decir que hace
cada herramienta. La logica del editor la cubre tests/test_editor_config.py;
esto cubre el SALTO, que es donde un dato se pierde con todo lo demas en verde
(CLAUDE.md §6).

    py -3.13 tests/test_agentes_formulario.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                  # noqa: E402
from nucleo.config import editor                                # noqa: E402
from nucleo.config.fuente import cargar_config                  # noqa: E402

fallos: list[str] = []


def comprobar(cond: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if cond else '[FALLA]'} {que}" + (f" ({detalle})" if not cond else ""))
    if not cond:
        fallos.append(que)


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
CONFIG = cargar_config(yamls[0])
api._config_de = lambda tenant: CONFIG
api._TOKEN_SERVICIO = None
api.olvidar_config = lambda tenant: None
http = api.app.test_client()

print("\nlos datos nuevos del formulario llegan al editor")
pedidos: list[dict] = []


def crear_falso(tenant, nombre, area, cargo, descripcion, orientado_a, herramientas, extras=None):
    pedidos.append({"accion": "crear", "extras": extras})
    raise editor.ErrorEdicion("solo se mira lo que llego")


def editar_falso(tenant, nombre, area, cargo, descripcion, orientado_a, herramientas, extras=None):
    pedidos.append({"accion": "editar", "extras": extras})
    raise editor.ErrorEdicion("solo se mira lo que llego")


editor.crear_rol = crear_falso
editor.editar_rol = editar_falso
http.post("/agentes", json={"tenant": "t", "nombre": "nuevo", "descripcion": "x",
                            "orientado_a": "cliente_final", "herramientas": [],
                            "atiende": "saldo y facturas", "conectar_al_router": True,
                            "exige_verificacion": False, "nunca_revelar": ["el costo"]})
comprobar(pedidos[-1] == {"accion": "crear", "extras": {
    "atiende": "saldo y facturas", "conectar_al_router": True,
    "exige_verificacion": False, "nunca_revelar": ["el costo"]}},
    "POST /agentes: atiende, router, verificacion y lo que nunca revela llegan al editor",
    str(pedidos[-1]))
http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": []})
comprobar(pedidos[-1] == {"accion": "editar", "extras": {}},
          "PUT sin esos datos: no viaja ninguno (lo que habia no se borra)", str(pedidos[-1]))
http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": [],
                                 "conectar_al_router": "si", "nunca_revelar": "no es lista"})
comprobar(pedidos[-1]["extras"] == {},
          "un valor con otro tipo no se adivina: no viaja", str(pedidos[-1]))

print("\nel catalogo dice que hace cada herramienta")
r = http.get("/agentes/catalogo?tenant=t")
herramientas = (r.get_json() or {}).get("herramientas", [])
comprobar(r.status_code == 200 and herramientas and all(
    {"escribe", "pide_aprobacion", "critica", "deriva", "de_sistema"} <= set(h) for h in herramientas),
    "GET /agentes/catalogo trae, por herramienta, si escribe, pide aprobacion, es critica, "
    "deriva o es del sistema")

print("\nla edicion abre con lo que el agente ya tiene")
agentes = (http.get("/agentes?tenant=t").get_json() or {}).get("agentes", [])
de_cliente = [x for x in agentes if x.get("orientado_a") == "cliente_final"]
comprobar(agentes and all({"atiende", "exige_verificacion", "nunca_revelar", "en_el_router"} <= set(x)
                          for x in agentes if not x.get("automatico")),
          "GET /agentes trae atiende, verificacion, lo que nunca revela y si esta en el router")
comprobar(any(x["en_el_router"] for x in de_cliente) or not de_cliente,
          "al menos un agente de clientes figura conectado al router")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s)")
    sys.exit(1)
print("\n[OK] Lo que el formulario de agentes manda llega al editor, y el catalogo dice que hace cada una.")
