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
#  AUDITORIA B1 (04/11/2026): crear o editar un agente decide que datos ve y si
#  verifica identidad. El CRM ya lo restringe a ADMIN; el motor lo vuelve a
#  exigir, con el autor de la sesion, como al promover o cambiar criticidad.
ADMIN = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
         "autor_rol": "ADMIN"}
r = http.post("/agentes", json={"tenant": "t", "nombre": "nuevo", "descripcion": "x", "herramientas": []})
comprobar(r.status_code == 400 and pedidos == [], "crear sin quien lo hace: no llega al editor",
          str(r.status_code))
r = http.post("/agentes", json={"tenant": "t", "nombre": "nuevo", "descripcion": "x", "herramientas": [],
                                **ADMIN, "autor_rol": "SUPERVISOR"})
comprobar(r.status_code == 403 and pedidos == [], "crear sin ser ADMIN: no", str(r.status_code))
r = http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": [],
                                     **ADMIN, "autor_rol": "USER"})
comprobar(r.status_code == 403 and pedidos == [], "editar sin ser ADMIN: no", str(r.status_code))
http.post("/agentes", json={"tenant": "t", "nombre": "nuevo", "descripcion": "x", **ADMIN,
                            "orientado_a": "cliente_final", "herramientas": [],
                            "atiende": "saldo y facturas", "conectar_al_router": True,
                            "exige_verificacion": False, "nunca_revelar": ["el costo"]})
comprobar(pedidos[-1] == {"accion": "crear", "extras": {
    "atiende": "saldo y facturas", "conectar_al_router": True,
    "exige_verificacion": False, "nunca_revelar": ["el costo"]}},
    "POST /agentes: atiende, router, verificacion y lo que nunca revela llegan al editor",
    str(pedidos[-1]))
http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": [], **ADMIN})
comprobar(pedidos[-1] == {"accion": "editar", "extras": {}},
          "PUT sin esos datos: no viaja ninguno (lo que habia no se borra)", str(pedidos[-1]))
http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": [], **ADMIN,
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

print("\nlos motivos de escalada, de la ruta al editor y del catalogo a la pantalla")
http.put("/agentes/nuevo", json={"tenant": "t", "descripcion": "x", "herramientas": [], **ADMIN,
                                 "motivos_escalada": ["solicitud_explicita"]})
comprobar(pedidos[-1]["extras"] == {"motivos_escalada": ["solicitud_explicita"]},
          "PUT con motivos: llegan al editor", str(pedidos[-1]))
cat = http.get("/agentes/catalogo?tenant=t").get_json() or {}
motivos = cat.get("motivos_escalada") or []
comprobar(motivos and [m["clave"] for m in motivos] == list(CONFIG.escalamiento.activar_si)
          and all("rotulo" in m for m in motivos),
          "el catalogo trae los motivos de la empresa, en su orden y con su rotulo", str(motivos[:2]))
agentes = (http.get("/agentes?tenant=t").get_json() or {}).get("agentes", [])
comprobar(all("motivos_escalada" in x for x in agentes if not x.get("automatico")),
          "cada agente dice sus motivos (vacio = todos)")

print("\nsi una accion es critica: solo ADMIN, y llega al editor")
cambios: list = []
editor.guardar_criticidad = lambda tenant, herramienta, critica: cambios.append(
    (herramienta, critica)) or CONFIG
AUTOR = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}
r = http.put("/agentes/herramientas/reiniciar_ont/critica",
             json={"tenant": "t", "critica": True, "autor_rol": "SUPERVISOR", **AUTOR})
comprobar(r.status_code == 403 and cambios == [], "quien no es ADMIN no la cambia", str(r.status_code))
r = http.put("/agentes/herramientas/reiniciar_ont/critica", json={"tenant": "t", "critica": True, **AUTOR,
                                                                  "autor_rol": "ADMIN"})
comprobar(r.status_code == 200 and cambios == [("reiniciar_ont", True)], "ADMIN la cambia",
          f"{r.status_code} {cambios}")
r = http.put("/agentes/herramientas/reiniciar_ont/critica", json={"tenant": "t", "critica": "no", **AUTOR,
                                                                  "autor_rol": "ADMIN"})
comprobar(r.status_code == 400 and len(cambios) == 1, "un valor que no es si/no no se adivina",
          str(r.status_code))
r = http.put("/agentes/herramientas/reiniciar_ont/critica", json={"tenant": "t", "critica": False,
                                                                  "autor_rol": "ADMIN"})
comprobar(r.status_code == 400 and len(cambios) == 1, "sin quien lo decide, no", str(r.status_code))

print("\nvolver a declararla critica APAGA en la base la autonomia dada sin evidencia (M1, 04/11/2026)")
#  Antes solo la dejaba sin efecto quien leia la config nueva: un proceso con
#  la config en cache (el reloj) o el ultimo metro, que no recibe la
#  herramienta, la seguian viendo vigente. Ahora queda escrito en la base.
from nucleo.persistencia import autonomia_ganada as registro_ag  # noqa: E402
from nucleo.seguridad import autonomia_ganada as seg_ag          # noqa: E402

usan = seg_ag.agentes_que_la_usan(CONFIG, "reiniciar_ont")
degradadas: list = []
filas: dict = {}
registro_ag.vigente = lambda tenant, herramienta, rol=None: filas.get(rol)
registro_ag.degradar = lambda tenant, herramienta, motivo, evidencia=None: degradadas.append(
    (herramienta, evidencia)) or {"id": "d1"}
if usan:
    filas = {usan[0]: {"id": "p5", "estado": "activa", "evidencia": {"no_critica": True}, "rol": usan[0]}}
    r = http.put("/agentes/herramientas/reiniciar_ont/critica",
                 json={"tenant": "t", "critica": True, "autor_rol": "ADMIN", **AUTOR})
    comprobar(r.status_code == 200 and len(degradadas) == 1 and degradadas[0][0] == "reiniciar_ont"
              and "p5" in str(degradadas[0][1]),
              "critica con una promocion activa sin evidencia: se degrada", f"{r.status_code} {degradadas}")
    comprobar(r.get_json().get("autonomia_apagada") is True, "y la respuesta lo dice")
    degradadas.clear()
    filas = {usan[0]: {"id": "p6", "estado": "activa", "evidencia": {"aprobadas": 20}, "rol": usan[0]}}
    http.put("/agentes/herramientas/reiniciar_ont/critica",
             json={"tenant": "t", "critica": True, "autor_rol": "ADMIN", **AUTOR})
    comprobar(degradadas == [], "una ganada CON evidencia no se toca: vale igual siendo critica")
    filas = {usan[0]: {"id": "p7", "estado": "activa", "evidencia": {"no_critica": True}, "rol": usan[0]}}
    http.put("/agentes/herramientas/reiniciar_ont/critica",
             json={"tenant": "t", "critica": False, "autor_rol": "ADMIN", **AUTOR})
    comprobar(degradadas == [], "declararla NO critica no degrada nada")
    filas = {None: {"id": "g1", "estado": "activa", "evidencia": {"no_critica": True}}}
    http.put("/agentes/herramientas/reiniciar_ont/critica",
             json={"tenant": "t", "critica": True, "autor_rol": "ADMIN", **AUTOR})
    comprobar(len(degradadas) == 1 and "g1" in str(degradadas[0][1]),
              "la general sin evidencia tambien", str(degradadas))
else:
    print("  (ningun agente usa esa accion en este tenant: se saltea)")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s)")
    sys.exit(1)
print("\n[OK] Lo que el formulario de agentes manda llega al editor, y el catalogo dice que hace cada una.")
