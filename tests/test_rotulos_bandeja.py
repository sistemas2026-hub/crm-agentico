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


def _guardar_casos(tenant, casos, rotulos=None):
    """guardar_casos_manual real sin la transaccion."""
    editor._mutar_casos_manual(estado["doc"], casos)
    editor._fundir_rotulos_de_casos(estado["doc"], rotulos or {})
    return editor._validar(tenant, estado["doc"])


def _guardar(tenant, rotulos):
    """El editor real sin la transaccion: muta el documento y lo valida."""
    if not isinstance(rotulos, dict):
        raise editor.ErrorEdicion("los rótulos tienen que venir como un mapa.")
    editor._mutar_rotulos_bandeja(estado["doc"], rotulos)
    return editor._validar(tenant, estado["doc"])


def _guardar_reincidencia(tenant, dias):
    """guardar_reincidencia real sin la transaccion."""
    real = editor._editar
    try:
        editor._editar = lambda t, mutar: (mutar(estado["doc"]), editor._validar(t, estado["doc"]))[1]
        return real_reincidencia(tenant, dias)
    finally:
        editor._editar = real


real_reincidencia = editor.guardar_reincidencia
editor.guardar_reincidencia = _guardar_reincidencia
real_casos = editor.guardar_casos_manual
editor.guardar_casos_manual = _guardar_casos
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

        # Lo que falta rotular, para el aviso de Ajustes.
        r = c.get(f"/configuracion/bandeja/rotulos?tenant={TENANT}")
        sin = (r.get_json() or {}).get("sin_rotulo", {})
        comprobar(motivo not in sin.get("motivos", []),
                  "sin_rotulo no cuenta el motivo que ya tiene rotulo")
        comprobar(len(sin.get("motivos", [])) == len(estado["doc"]["escalamiento"]["activar_si"]) - 1,
                  "y cuenta todos los demas")

        # Un caso nuevo desde /manual nace con lo que la persona escribio.
        casos = list(estado["doc"]["manual"]["casos"]) + ["problema_de_tv"]
        r = c.put("/manual/casos", json={"tenant": TENANT, "casos": casos,
                                         "rotulos": {"problema_de_tv": "Problema de TV"}})
        comprobar(r.status_code == 200, f"/manual/casos guarda con rotulos (devolvio {r.status_code})")
        comprobar((r.get_json() or {}).get("rotulos", {}).get("problema_de_tv") == "Problema de TV",
                  "y el caso nuevo vuelve con su rotulo")
        r = c.get(f"/conversaciones?tenant={TENANT}")
        comprobar((r.get_json() or {}).get("rotulos", {}).get("problema_de_tv") == "Problema de TV",
                  "y llega a la cola")
        r = c.put("/manual/casos", json={"tenant": TENANT, "casos": casos[:-1]})
        comprobar(r.status_code == 200 and "problema_de_tv" not in (r.get_json() or {}).get("rotulos", {}),
                  "una pantalla que no manda rotulos guarda igual, y el caso borrado se lleva el suyo")

        # Los dias de reincidencia: se guardan, vuelven, y fuera de rango no.
        r = c.put("/configuracion/bandeja/reincidencia", json={"tenant": TENANT, "dias": 15})
        comprobar(r.status_code == 200 and (r.get_json() or {}).get("reincidencia_dias") == 15,
                  f"reincidencia: 15 dias se guardan (devolvio {r.status_code})")
        r = c.put("/configuracion/bandeja/reincidencia", json={"tenant": TENANT, "dias": 900})
        comprobar(r.status_code == 400, "y 900 se rechaza")
        r = c.get(f"/configuracion/bandeja/rotulos?tenant={TENANT}")
        comprobar((r.get_json() or {}).get("reincidencia_dias") == 15,
                  "y la pantalla de ajustes los lee")

    # El aviso de cargar_config, para quien agrega un motivo en el YAML.
    import io
    from contextlib import redirect_stdout
    from cli.cargar_config import avisar_claves_sin_rotulo
    salida = io.StringIO()
    with redirect_stdout(salida):
        lineas = avisar_claves_sin_rotulo(editor._validar(TENANT, estado["doc"]))
    comprobar(bool(lineas) and "[aviso]" in salida.getvalue(),
              "cargar_config avisa las claves sin rotulo")
    # Y no frena: es un aviso. Si levantara, la linea de arriba ya habria
    # cortado la prueba antes de llegar aca.
finally:
    editor.guardar_casos_manual = real_casos
    editor.guardar_reincidencia = real_reincidencia
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
