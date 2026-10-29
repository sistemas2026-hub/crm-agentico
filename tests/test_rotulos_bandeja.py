# -*- coding: utf-8 -*-
"""
================================================================================
 LOS ROTULOS DE LA BANDEJA LLEGAN A LA PANTALLA
================================================================================

    py -3.13 tests/test_rotulos_bandeja.py

Corre sin base y sin red: se sustituye '_config_de', la persistencia y el
guardado del editor por nombre, y las peticiones se hacen con el cliente de
prueba de Flask. El mutador que corre en el PUT es el REAL, sobre el documento
del primer tenant -- lo unico que se saltea es la transaccion.

POR QUE EXISTE  (29/10/2026)
----------------------------
La Bandeja mostraba los motivos, etiquetas y casos como su clave con espacios:
«frustracion detectada», «informacion a confirmar», sin tildes. Los rotulos
viven en 'conversaciones.rotulos' y tienen que hacer TRES saltos para verse:
el editor los guarda, el GET de configuracion los devuelve para el formulario,
y la lista de conversaciones los lleva a la cola. Una prueba del editor sola
no ve si el tercero se cae -- y ese es el que el usuario mira.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config, editor                     # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def documento() -> dict:
    """El volcado del primer tenants/*.config.yaml. No se nombra ninguno."""
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    return cargar_config(yamls[0]).model_dump(mode="json")


TENANT = "prueba"
estado = {"doc": documento()}
estado["doc"].setdefault("conversaciones", {})["rotulos"] = {}


def _config_de(_tenant):
    return editor._validar(TENANT, estado["doc"])


def _guardar(tenant, rotulos):
    """El editor real sin la transaccion: muta el documento y lo valida."""
    if not isinstance(rotulos, dict):
        raise editor.ErrorEdicion("los rótulos tienen que venir como un mapa.")
    editor._mutar_rotulos_bandeja(estado["doc"], rotulos)
    return editor._validar(tenant, estado["doc"])


reales = (api._config_de, editor.guardar_rotulos_bandeja,
          api.persistencia.ultima_actividad, api.persistencia.salud_canal_whatsapp,
          api.olvidar_config)
api._config_de = _config_de
editor.guardar_rotulos_bandeja = _guardar
api.persistencia.ultima_actividad = lambda tenant, canal=None: []
api.persistencia.salud_canal_whatsapp = lambda tenant: None
api.olvidar_config = lambda tenant: None

try:
    print()
    print("=" * 78)
    print("  LOS ROTULOS DE LA BANDEJA LLEGAN A LA PANTALLA")
    print("=" * 78)
    motivo = estado["doc"]["escalamiento"]["activar_si"][0]

    with api.app.test_client() as c:
        r = c.get(f"/configuracion/bandeja/rotulos?tenant={TENANT}")
        datos = r.get_json() or {}
        comprobar(r.status_code == 200, f"el GET responde (devolvio {r.status_code})")
        comprobar(motivo in datos.get("claves", {}).get("motivos", []),
                  "y trae las claves que admiten rotulo, por familia")

        r = c.put("/configuracion/bandeja/rotulos",
                  json={"tenant": TENANT, "rotulos": {motivo: "Con tilde: acción"}})
        comprobar(r.status_code == 200, f"el PUT guarda (devolvio {r.status_code})")
        comprobar((r.get_json() or {}).get("rotulos", {}).get(motivo) == "Con tilde: acción",
                  "y devuelve lo guardado")

        r = c.put("/configuracion/bandeja/rotulos",
                  json={"tenant": TENANT, "rotulos": {"no_existe_xyz": "Algo"}})
        comprobar(r.status_code == 400, f"una clave inventada se rechaza (devolvio {r.status_code})")
        comprobar(estado["doc"]["conversaciones"]["rotulos"].get(motivo) == "Con tilde: acción",
                  "y el rechazo no borra lo que habia")

        # El salto que ve el usuario: la cola.
        r = c.get(f"/conversaciones?tenant={TENANT}")
        cola = r.get_json() or {}
        comprobar(r.status_code == 200, f"la lista de conversaciones responde (devolvio {r.status_code})")
        comprobar(cola.get("rotulos", {}).get(motivo) == "Con tilde: acción",
                  "y LLEVA los rotulos a la cola, que es donde se leen")

        r = c.put("/configuracion/bandeja/rotulos", json={"rotulos": {}})
        comprobar(r.status_code == 400, "sin tenant no se escribe nada")
finally:
    (api._config_de, editor.guardar_rotulos_bandeja,
     api.persistencia.ultima_actividad, api.persistencia.salud_canal_whatsapp,
     api.olvidar_config) = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
