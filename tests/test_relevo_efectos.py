# -*- coding: utf-8 -*-
"""
================================================================================
 D25  --  despues de una intervencion, la IA no EMPIEZA nuevos efectos
================================================================================

    py -3.13 tests/test_relevo_efectos.py          (sin base)

SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D25 (C13). La carrera real con PostgreSQL
(el modelo frenado, una persona interviene, el modelo pide la herramienta) esta
en tests/test_relevo_transiciones_base.py, seccion 11.

  1. El despacho REAL del motor (motor.responder con el modelo guionado): con
     el autorizador del turno negando, una herramienta que escribe no llega al
     proveedor, queda en la traza como bloqueo CAMBIO_DE_CONTROL y no fuerza
     una escalada; una lectura SI corre; una propuesta con aprobacion humana
     no se guarda. Sin autorizador (fuera de un turno) todo sigue como antes.
  2. INVENTARIO de api.atender_turno: cada efecto que escribe despues de la
     respuesta (visita agendada sola, ticket y caso de la escalada, cierre por
     confirmacion) pregunta a _efecto_del_turno ANTES de empezar. Un efecto
     nuevo que se saltee la pregunta hace fallar esta suite.
================================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                             # noqa: E402
from nucleo.modelo import cliente, motor                            # noqa: E402
from nucleo.relevo import autorizacion                              # noqa: E402
from nucleo.seguimiento import forzado                              # noqa: E402
from nucleo.seguridad.verificacion import Sesion                    # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


class ModeloGuionado:
    def __init__(self, guion):
        self.guion, self.turnos = guion, []

    def __call__(self, referencia_modelo, mensajes, tools=None, temperatura=0.1, timeout=None, **resto):
        i = min(len(self.turnos), len(self.guion) - 1)
        texto, llamadas = self.guion[i]
        self.turnos.append(texto)
        if tools is None:
            return cliente.Respuesta(contenido=texto, llamadas=[])
        return cliente.Respuesta(contenido=texto,
                                 llamadas=[cliente.Llamada(nombre=n, argumentos=a) for n, a in llamadas])


def correr(rol, guion, autorizador):
    """(registro, llamadas_http, propuestas_guardadas, preguntas_al_autorizador)"""
    http, propuestas, preguntas = [], [], []

    def _http(herramienta, argumentos, tenant=None, *a, **k):
        http.append(herramienta.nombre)
        return {"ok": True}
    reemplazos = {
        (motor.cliente, "chat"): ModeloGuionado(guion),
        (motor.ejecutor_http, "ejecutar"): _http,
        (motor.catalogo_habilidades, "indice_de"): lambda *a, **k: [],
        (motor.persistencia, "leer_cache"): lambda *a, **k: None,
        (motor.persistencia, "guardar_cache"): lambda *a, **k: None,
        (motor.persistencia, "guardar_accion_propuesta"):
            lambda *a, **k: propuestas.append(a) or "accion-1",
    }
    orig = {k: getattr(*k) for k in reemplazos}
    for (m, n), f in reemplazos.items():
        setattr(m, n, f)
    sesion = Sesion(verificado=True, nivel=2, id_cliente="5832", nombre="CLIENTE DE PRUEBA",
                    sn_onu="AAAA00000000", identificador_canal="3001234567")
    try:
        if autorizador is None:
            _, registro, _ = motor.responder(CONFIG, rol, "hola", [], sesion)
        else:
            def contado(que):
                preguntas.append(que)
                return autorizador(que)
            with autorizacion.autorizando(contado):
                _, registro, _ = motor.responder(CONFIG, rol, "hola", [], sesion)
    finally:
        for (m, n), f in orig.items():
            setattr(m, n, f)
    return registro, http, propuestas, preguntas


ARGS_CANCELAR = {"numero_documento": "1000000000", "nombre_confirmado": "CLIENTE DE PRUEBA",
                 "motivo": "ya no la necesito"}

print("=" * 74)
print(" D25: la IA no empieza efectos despues de una intervencion")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. el despacho real del motor ==")
guion = [("", [("consultar_solicitud_por_cedula", {"numero_documento": "1000000000"}),
               ("cancelar_solicitud_servicio", ARGS_CANCELAR)]),
         ("Listo.", [])]
registro, http, _, preguntas = correr("ventas", guion, None)
comprobar(http.count("cancelar_solicitud_servicio") == 1,
          f"sin autorizador (fuera de un turno) la escritura sale como siempre ({http})")

registro, http, _, preguntas = correr("ventas", guion, lambda que: False)
cancelar = [r for r in registro if r["herramienta"] == "cancelar_solicitud_servicio"]
comprobar("cancelar_solicitud_servicio" not in http,
          f"con el control cambiado, la escritura NO llega al proveedor ({http})")
comprobar(http.count("consultar_solicitud_por_cedula") == 1,
          "la lectura SI corre: no cambia nada afuera")
comprobar(preguntas == ["cancelar_solicitud_servicio"],
          f"solo la escritura le pregunta al autorizador, justo antes ({preguntas})")
comprobar(bool(cancelar) and cancelar[0]["codigo_error"] == "CAMBIO_DE_CONTROL" and cancelar[0]["es_bloqueo"],
          "queda en la traza como bloqueo CAMBIO_DE_CONTROL, no como fallo del proveedor")
comprobar("CAMBIO_DE_CONTROL" in forzado.CODIGOS_MOTOR_GUARD,
          "y no cuenta como fallo que fuerce una escalada")

registro, http, propuestas, _ = correr(
    "soporte", [("", [("crear_ticket", {"asunto": "x", "descripcion": "y"})]), ("Listo.", [])],
    lambda que: False)
comprobar(propuestas == [] and any(r["codigo_error"] == "CAMBIO_DE_CONTROL" for r in registro),
          f"una accion con aprobacion humana tampoco deja propuesta guardada ({len(propuestas)})")

registro, http, propuestas, _ = correr(
    "soporte", [("", [("crear_ticket", {"asunto": "x", "descripcion": "y"})]), ("Listo.", [])], None)
comprobar(len(propuestas) == 1, "sin autorizador, la misma accion SI deja su propuesta (control positivo)")

# proponer_herramienta escribe en la base, y su rol (configuracion_guiada) lee
# la base al armar el turno: sin base no se puede correr entero. Se afirma sobre
# el fuente de la rama del despacho, igual que el inventario de la seccion 2.
fuente_motor = (RAIZ / "nucleo" / "modelo" / "motor.py").read_text(encoding="utf-8")
for rama, efecto in (("elif herramienta.propone_herramienta:", "_ejecutar_propuesta("),
                     ("elif herramienta.aprobacion_humana:", "_ejecutar_propuesta_de_accion(")):
    tramo = fuente_motor[fuente_motor.index(rama):]
    tramo = tramo[:tramo.index(efecto)]
    comprobar("_cancelada_por_cambio_de_control(" in tramo,
              f"la rama '{rama}' pregunta antes de {efecto[:-1]}")

# ---------------------------------------------------------------------------
print("\n== 1b. las reglas de autorizacion.py ==")
A = {"conversation_id": "c1", "relevo_version": 5}
comprobar(autorizacion.regla_turno(A, {"conversation_id": "c1", "control_efectivo": "ia", "relevo_version": 5},
                                   exigir_ia=True), "AUTONOMO_IA: misma conversacion, ia y misma version -> si")
comprobar(not autorizacion.regla_turno(A, {"conversation_id": "c1", "control_efectivo": "humano",
                                           "relevo_version": 6}, exigir_ia=True),
          "AUTONOMO_IA: humano y otra version -> no")
comprobar(not autorizacion.regla_turno(A, {"conversation_id": "c1", "control_efectivo": "humano",
                                           "relevo_version": 6}, exigir_ia=False),
          "AUTOMATICO_EN_PAUSA: una toma mueve la version -> no")
V = {"estado": "abierta", "control_efectivo": "humano", "relevo_version": 6, "originada": True, "invalidada": False}
comprobar(autorizacion.regla_escalada(V), "SYNC_ESCALADA: tomada despues (version 6) -> si")
comprobar(not autorizacion.regla_escalada({**V, "invalidada": True}), "SYNC_ESCALADA: devuelta o cerrada despues -> no")
comprobar(not autorizacion.regla_escalada({**V, "estado": "cerrada"}), "SYNC_ESCALADA: conversacion cerrada -> no")
comprobar(not autorizacion.regla_escalada({**V, "control_efectivo": "ia"}), "SYNC_ESCALADA: control ia -> no")
comprobar(not autorizacion.regla_escalada({**V, "originada": False}),
          "SYNC_ESCALADA: sin el evento de ESA escalada -> no")
comprobar(not autorizacion.regla_escalada(None), "SYNC_ESCALADA: conversacion inexistente -> no")
comprobar(set(autorizacion.INVALIDAN_ESCALADA) == {"devuelta_a_ia", "cerrada"},
          "invalidan una escalada: devolver y cerrar; tomar, soltar y reasignar no")

# ---------------------------------------------------------------------------
print("\n== 2. inventario de los efectos de atender_turno ==")
from nucleo.canales import api                                      # noqa: E402

arbol = ast.parse((RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8"))
turno = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "atender_turno")

# Lo que escribe afuera (o cierra la conversacion) despues de la respuesta.
EFECTOS = {("agendamiento", "agendar"), ("escalamiento", "escalar"),
           ("operativo", "cerrar_todo"), ("persistencia", "cerrar_conversacion"),
           ("supervisor", "revisar")}
llamadas = []
for n in ast.walk(turno):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
        llamadas.append((n.lineno, n.func.value.id, n.func.attr))
preguntas = sorted(l for l, _, nombre in
                   [(n.lineno, None, getattr(n.func, "id", None)) for n in ast.walk(turno)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
                   if nombre == "_efecto_del_turno")
efectos = sorted((l, f"{m}.{f}") for l, m, f in llamadas if (m, f) in EFECTOS)
comprobar(len(efectos) >= 5, f"se encontraron los efectos del turno ({efectos})")
fuente = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8").splitlines()
for linea, nombre in efectos:
    # La pregunta tiene que estar ANTES y cerca: en el mismo bloque de decision
    # (a lo sumo 70 lineas arriba, y el supervisor detras del cierre, que ya
    # pregunto).
    previas = [p for p in preguntas if linea - 70 <= p <= linea]
    if nombre == "supervisor.revisar":
        previas = previas or [p for p in preguntas if linea - 40 <= p <= linea]
        comprobar(bool(previas) and any("if cerrada" in fuente[i] for i in range(linea - 4, linea)),
                  f"{nombre} (l.{linea}) solo corre si el cierre, que pregunto, ocurrio")
        continue
    comprobar(bool(previas), f"{nombre} (l.{linea}) pregunta a _efecto_del_turno antes de empezar")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Despues de una intervencion, la IA no empieza nada que escriba.")
