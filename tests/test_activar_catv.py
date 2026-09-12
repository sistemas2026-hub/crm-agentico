# -*- coding: utf-8 -*-
"""
================================================================================
 ENCENDER LA TV DEL CLIENTE  --  lo que el codigo garantiza alrededor
================================================================================

    py -3.13 tests/test_activar_catv.py

QUE CUBRE ESTE ARCHIVO Y QUE NO
-------------------------------
'activar_catv' es una ESCRITURA contra el equipo de un cliente real. Hay dos
preguntas distintas sobre ella y se prueban en lugares distintos:

  CUANDO corresponde encender        decision del modelo, leyendo el arbol de
                                     diagnostico -> caso dorado "el puerto de
                                     TV apagado lo enciende el agente, no un
                                     humano" (precondicion manual: exige el
                                     puerto en 'Disabled', ver el comentario
                                     del caso)

  QUE PASA cuando lo pide            garantias del motor -> ESTE archivo

Poner la primera aca seria mentira: con el modelo guionado, la decision la
escribo yo.

PERO EL CODIGO GARANTIZA MAS DE LO QUE PARECIA, y eso es lo que se fija aca.
'activar_catv' declara 'exige_previas': el motor NO la deja correr salvo que
la traza pruebe DOS cosas -- que la descripcion real del plan mencione TV, y
que el puerto diga 'Disabled'. O sea que encender no depende solo del criterio
del modelo: si el puerto esta en 'Enabled' y lo pide igual, el motor lo frena.

Eso es mas fuerte que el caso dorado C4, que afirma que el modelo no lo
intenta. Aca lo intenta a proposito y no pasa nada.

POR QUE IMPORTA EL LIMITE
-------------------------
'limite_por_conversacion: 1'. Encender un puerto que ya se encendio no arregla
nada y vuelve a escribir sobre el equipo de alguien. El modelo puede pedirlo de
nuevo -- lo pide cuando el cliente insiste en que sigue sin ver nada-- y lo
unico que lo frena es el motor.

Y el limite cuenta EJECUCIONES, no intentos: un pedido que la guarda freno no
gasta la oportunidad. Eso ya costo un incidente con 'reiniciar_ont' el
21/08/2026 -- el modelo lo intento antes de tiempo, la guarda lo bloqueo con
razon, y cuando el reinicio SI correspondia salio 'LIMITE_DE_CONVERSACION'.

No toca la red: el ejecutor HTTP se sustituye. Ningun equipo se enciende desde
aca.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.modelo import cliente, motor                           # noqa: E402
from nucleo.seguridad.verificacion import Sesion                   # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
ROL = "soporte_tecnico_cliente"


class ModeloGuionado:
    """Pide lo que le digan, turno por turno. Ver test_guia_tv_obligatoria."""

    def __init__(self, guion):
        self.guion = guion
        self.turnos = []

    def __call__(self, referencia_modelo, mensajes, tools=None,
                 temperatura=0.1, timeout=None, **resto):
        i = min(len(self.turnos), len(self.guion) - 1)
        texto, llamadas = self.guion[i]
        self.turnos.append(texto)
        if tools is None:
            return cliente.Respuesta(contenido=texto, llamadas=[])
        return cliente.Respuesta(
            contenido=texto,
            llamadas=[cliente.Llamada(nombre=n, argumentos=a) for n, a in llamadas])


def correr(guion, catv="Disabled"):
    """
    Devuelve (herramientas_intentadas, ejecutadas, llamadas_http).

    'catv' es lo que contesta la OLT. Es el dato del que cuelga la
    precondicion, asi que es el unico parametro que hace falta variar.
    """
    doble = ModeloGuionado(guion)
    http_hechas = []
    respuestas = {
        # 'exige_previas' exige que la descripcion REAL del plan mencione TV:
        # el nombre no alcanza -- 'PLAN HOGAR' incluye TV sin decirlo.
        "consultar_plan_tv": {"descripcion": "PLAN FIBRA 100MB + TV DIGITAL"},
        "consultar_estado_catv": {"catv": catv},
        "activar_catv": {"status": True, "response": "CATV enabled"},
    }

    def _http(herramienta, argumentos, tenant=None, *a, **k):
        http_hechas.append(herramienta.nombre)
        return respuestas.get(herramienta.nombre, {"ok": True})

    # 'consultar_plan_tv' declara cache: sin esto la prueba pide la base solo
    # para leer una cache vacia. Devolver None es "no cacheado", que es
    # justo lo que hace falta para que se ejecute la llamada.
    originales = (motor.cliente.chat, motor.ejecutor_http.ejecutar,
                  motor.catalogo_habilidades.indice_de,
                  motor.persistencia.leer_cache, motor.persistencia.guardar_cache)
    motor.cliente.chat = doble
    motor.ejecutor_http.ejecutar = _http
    motor.catalogo_habilidades.indice_de = lambda *a, **k: []
    motor.persistencia.leer_cache = lambda *a, **k: None
    motor.persistencia.guardar_cache = lambda *a, **k: None
    try:
        _, registro, _ = motor.responder(
            CONFIG, ROL, "no me aparecen los canales",
            [], Sesion(verificado=True, nivel=1, id_cliente="5832",
                       nombre="CLIENTE DE PRUEBA", sn_onu="AAAA00000000",
                       identificador_canal="3001234567"))
    finally:
        (motor.cliente.chat, motor.ejecutor_http.ejecutar,
         motor.catalogo_habilidades.indice_de,
         motor.persistencia.leer_cache, motor.persistencia.guardar_cache) = originales

    intentadas = [r["herramienta"] for r in registro]
    ejecutadas = [r["herramienta"] for r in registro
                  if not r.get("es_bloqueo") and not r.get("codigo_error")]
    return intentadas, ejecutadas, http_hechas


print("=" * 74)
print(" ENCENDER LA TV  --  se ejecuta cuando se pide, y una sola vez")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. como esta declarada: enciende, no apaga ==")
# Un POST contra el endpoint equivocado apagaria la TV del cliente en vez de
# encenderla, y el sintoma seria identico al que vino a resolver.
h = next(x for x in CONFIG.herramientas if x.nombre == "activar_catv")
comprobar(h.endpoint.endswith("/enable_catv/{sn_onu}"),
          f"apunta a enable_catv, no a disable ({h.endpoint})")
comprobar(h.metodo == "POST", "es POST: escribe")
comprobar(h.requiere_confirmacion is True,
          "exige confirmacion del cliente antes de escribir")
comprobar(h.limite_por_conversacion == 1,
          "y una sola vez por conversacion")
for rol in ("soporte_tecnico_cliente", "soporte"):
    comprobar("activar_catv" in CONFIG.roles[rol].puede_consultar,
              f"esta en el catalogo de {rol}")

# ---------------------------------------------------------------------------
print("\n== 2. cuando el modelo la pide, SE EJECUTA ==")
# La guarda de confirmacion no puede volverse un bloqueo silencioso: el
# cliente queda sin TV y en la traza no se ve por que.
# El motor exige que la traza PRUEBE las dos cosas antes de dejarla escribir:
# que el plan incluya TV y que el puerto este apagado. Asi que el guion las
# pide en orden, como lo hace el agente real.
PREVIAS = [("", [("consultar_plan_tv", {"id_plan": "173064"})]),
           ("", [("consultar_estado_catv", {})])]

intentadas, ejecutadas, http = correr(PREVIAS + [
    ("", [("activar_catv", {})]),
    ("Ya quedo activada. Ahora hay que volver a buscar los canales.", []),
])
comprobar("activar_catv" in ejecutadas,
          "con el plan confirmado y el puerto en Disabled, corre de verdad")
comprobar(http.count("activar_catv") == 1,
          f"y sale UNA escritura al proveedor ({http.count('activar_catv')})")

# ---------------------------------------------------------------------------
print("\n== 2b. con el puerto ENCENDIDO, el motor la bloquea ==")
# Esto es mas fuerte que el caso dorado C4, que afirma que el modelo no lo
# intenta. Aca lo intenta A PROPOSITO y el codigo lo frena igual: la
# precondicion exige catv='Disabled' y el puerto dice 'Enabled'.
intentadas, ejecutadas, http = correr(PREVIAS + [
    ("", [("activar_catv", {})]),
    ("Del lado nuestro la señal sale bien.", []),
], catv="Enabled")
comprobar("activar_catv" in intentadas,
          "el modelo la pidio igual (es lo que hay que poder frenar)")
comprobar("activar_catv" not in ejecutadas,
          "pero el motor NO la ejecuto: la precondicion exige 'Disabled'")
comprobar("activar_catv" not in http,
          "al equipo del cliente no le llego ninguna escritura")

# ---------------------------------------------------------------------------
print("\n== 3. la segunda vez NO se ejecuta ==")
# El cliente insiste en que sigue sin ver nada y el modelo lo vuelve a pedir.
# Encender lo que ya esta encendido no arregla nada y escribe otra vez sobre
# el equipo de alguien.
intentadas, ejecutadas, http = correr(PREVIAS + [
    ("", [("activar_catv", {})]),
    ("", [("activar_catv", {})]),
    ("Del lado nuestro ya quedo. Probemos la sintonizacion.", []),
])
comprobar(intentadas.count("activar_catv") == 2,
          "el modelo la pidio dos veces (que es lo que pasa en vivo)")
comprobar(ejecutadas.count("activar_catv") == 1,
          "pero se EJECUTO una sola: el limite la freno")
comprobar(http.count("activar_catv") == 1,
          f"y al equipo del cliente le llego una sola escritura "
          f"({http.count(chr(39)+chr(39)) if False else http.count('activar_catv')})")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print("[OK] Se enciende cuando se pide, y una sola vez.")
