# -*- coding: utf-8 -*-
"""
================================================================================
 BORRADOR DE RESPUESTA: LA IA PROPONE, UNA PERSONA DECIDE
================================================================================

    py -3.13 tests/test_borrador.py

Corre sin base y sin modelo: se sustituye cliente.chat por uno que anota lo
que recibe. Lo que se protege no es la calidad del texto -- eso no se afirma
sobre una redaccion -- sino el MECANISMO que la hace segura:

  - el modelo no recibe herramientas: no puede ejecutar nada
  - las notas internas le llegan marcadas como contexto, no como del cliente
  - la guardia de salida bloquea una fuga: ese texto NO se devuelve
  - sin nada del cliente no se gasta una llamada
  - el endpoint no da borrador si la conversacion la atiende la IA
  - y no escribe nada: ni mensaje, ni nota, ni envio

POR QUE NO cli/evaluar.py: ese instrumento llama motor.responder(), y el
borrador no pasa por ahi (CLAUDE.md §6, "un instrumento solo mide el camino
que recorre"). Correrlo no diria nada sobre esto.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.seguimiento import borrador                             # noqa: E402
from nucleo.seguridad import salida                                 # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
CFG = cargar_config(yamls[0])

pedidos: list[dict] = []
respuesta = {"texto": "Hola, ya reviso tu servicio. ¿Me confirmas si la luz LOS está en rojo?"}


def chat_falso(referencia, mensajes, tools=None, **k):
    pedidos.append({"referencia": referencia, "mensajes": mensajes, "tools": tools})
    return SimpleNamespace(contenido=respuesta["texto"], llamadas=[],
                           tokens_entrada=0, tokens_salida=0)


HILO = [
    {"rol": "user", "contenido": "no tengo internet desde ayer"},
    {"rol": "assistant", "contenido": "Te paso con un compañero."},
    {"rol": "nota", "contenido": "(Ana) reinicié la ONT, sigue igual"},
]

reales = (borrador.cliente.chat, borrador.consumo.anotar)
borrador.cliente.chat = chat_falso
borrador.consumo.anotar = lambda *a, **k: None
try:
    print()
    print("=" * 78)
    print("  BORRADOR DE RESPUESTA: LA IA PROPONE, UNA PERSONA DECIDE")
    print("=" * 78)

    texto = borrador.redactar(CFG, rol=None, mensajes=HILO)
    comprobar(texto == respuesta["texto"], "devuelve la propuesta del modelo")
    p = pedidos[-1]
    comprobar(not p["tools"], "el modelo NO recibe herramientas: no puede ejecutar nada")
    comprobar(p["mensajes"][0]["role"] == "system"
              and "No prometas" in p["mensajes"][0]["content"],
              "la instrucción dice que no prometa lo que no está confirmado")
    notas = [m for m in p["mensajes"] if "NOTA INTERNA" in m["content"]]
    comprobar(len(notas) == 1 and "no es del cliente" in notas[0]["content"],
              "la nota interna llega marcada como contexto del equipo, no del cliente")

    pedidos.clear()
    try:
        borrador.redactar(CFG, rol=None, mensajes=[HILO[2]])
        comprobar(False, "sin nada del cliente no hay borrador")
    except borrador.BorradorNoDisponible:
        comprobar(not pedidos, "sin nada del cliente: no hay borrador y no se gasta la llamada")

    # El tratamiento lo garantiza el codigo (30/10/2026: el modelo real
    # propuso «¿podés…?» a una empresa que habla de tú).
    if CFG.persona.normalizar_tratamiento == "tu":
        respuesta["texto"] = "¿Podés confirmarme si la luz está en rojo?"
        comprobar("Puedes" in borrador.redactar(CFG, rol=None, mensajes=HILO),
                  "el borrador sale con el tratamiento de la empresa, no con el del modelo")

    respuesta["texto"] = f"Te cuento: {salida.PATRONES_INTERNOS[0]}"
    try:
        borrador.redactar(CFG, rol=None, mensajes=HILO)
        comprobar(False, "una fuga no se devuelve")
    except borrador.BorradorNoDisponible as e:
        comprobar("internos" in str(e), "la guardia de salida bloquea la fuga: el texto NO se devuelve")
    respuesta["texto"] = "Ya lo reviso."

    # ---- el endpoint ------------------------------------------------------
    escrituras: list = []
    conv_humana = {"estado": "abierta", "relevo_version": 3, "control": "humano",
                   "rol_efectivo": None}
    conv = {"c": conv_humana}
    reales_api = (api.persistencia.mensajes_de, api._config_de, api._TOKEN_SERVICIO,
                  api.persistencia.agregar_mensaje_humano, api.persistencia.agregar_nota_interna)
    api.persistencia.mensajes_de = lambda t, i: {"conversacion": conv["c"], "mensajes": HILO}
    api._config_de = lambda t: CFG
    api._TOKEN_SERVICIO = None
    api.persistencia.agregar_mensaje_humano = lambda *a, **k: escrituras.append("mensaje")
    api.persistencia.agregar_nota_interna = lambda *a, **k: escrituras.append("nota")
    try:
        with api.app.test_client() as c:
            r = c.post("/conversaciones/c1/borrador", json={"tenant": "t"})
            comprobar(r.status_code == 200 and (r.get_json() or {}).get("borrador") == "Ya lo reviso.",
                      f"el endpoint devuelve el borrador ({r.status_code})")
            comprobar(not escrituras, "y no escribe nada: ni mensaje ni nota")
            conv["c"] = {**conv_humana, "control": "ia"}
            r = c.post("/conversaciones/c1/borrador", json={"tenant": "t"})
            comprobar(r.status_code == 409, f"con la IA atendiendo: 409 ({r.status_code})")
            conv["c"] = None
            r = c.post("/conversaciones/c1/borrador", json={"tenant": "t"})
            comprobar(r.status_code == 404, f"una que no existe: 404 ({r.status_code})")
    finally:
        (api.persistencia.mensajes_de, api._config_de, api._TOKEN_SERVICIO,
         api.persistencia.agregar_mensaje_humano, api.persistencia.agregar_nota_interna) = reales_api
finally:
    borrador.cliente.chat, borrador.consumo.anotar = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
