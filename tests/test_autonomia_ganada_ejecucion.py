# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTONOMIA GANADA EJECUTA POR LA MISMA CADENA, Y SE PIERDE SOLA (31/10/2026)
================================================================================

PRD §2 y §8.17 (Ola 3), Fases C y D. Lo que se protege:

  C1  la frontera (aprobacion vinculante) acepta 'autonomia_ganada:<id>' SOLO
      si en ese instante la promocion vigente de esa empresa y esa herramienta
      es EXACTAMENTE esa; otra promocion, degradada, retirada o la base caida:
      no. Una aprobacion de una persona no consulta nada de esto;
  C2  ninguna persona puede firmar como la autonomia: la cola y la Bandeja
      rechazan el prefijo;
  C3  despues del turno, una propuesta irreversible de una herramienta con
      autonomia vigente se ejecuta por _aprobar_y_ejecutar_datos firmada por
      la promocion; sin autonomia, o si no es irreversible, no pasa nada;
  C4  si una guarda la frena, vuelve a la cola de una persona (liberar), no
      se vence: al cliente se le dijo que quedo pedido;
  C5  la respuesta del turno dice "quedo pedido", nunca "ya se hizo";
  D1  una ejecucion que falla o queda incierta degrada la autonomia;
  D2  una verificacion no confirmada tambien.

Sin base: la persistencia, la frontera y el ejecutor se sustituyen. La parte
con permisos reales esta en test_autonomia_ganada_base.py.

    py -3.13 tests/test_autonomia_ganada_ejecucion.py
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                  # noqa: E402
from nucleo.persistencia import autonomia_ganada as registro    # noqa: E402
from nucleo.seguridad import aprobacion                         # noqa: E402
from nucleo.seguridad.idempotencia import hash_de               # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


api._TOKEN_SERVICIO = None

# ---------------------------------------------------------------------------
print("\nC1 · la frontera acepta la autonomia solo si sigue vigente, y es esa")
ARGS = {"sn_onu": "HWTC00000001"}
ORG = "00000000-0000-0000-0000-000000000001"


def aprob(aprobador: str):
    huella = hash_de(ARGS)
    return aprobacion.Aprobacion(
        id="acc-1", tenant="rapilink", organization_id=ORG, herramienta="reiniciar_ont",
        argumentos=ARGS, huella=huella, origen="whatsapp:wamid.1", estado=aprobacion.APROBADA,
        aprobador=aprobador, aprobada_en=datetime.now(timezone.utc),
        sello=aprobacion.sello_de(tenant="rapilink", organization_id=ORG, herramienta="reiniciar_ont",
                                  origen="whatsapp:wamid.1", huella=huella, aprobador=aprobador))


consultas: list[tuple] = []
estado = {"v": {"autonoma": True, "estado": "activa", "promocion_id": "p1"}}


def vigente_falso(tenant, herramienta):
    consultas.append((tenant, herramienta))
    return estado["v"]


aprobacion._autonomia_vigente = vigente_falso
v = aprobacion.veredicto(aprob("autonomia_ganada:p1"), tenant="rapilink", herramienta="reiniciar_ont",
                         argumentos=ARGS)
comprobar(v.permitido and consultas == [("rapilink", "reiniciar_ont")],
          "la promocion vigente p1 firma: permitida, consultada en ESE instante", f"{v} {consultas}")
v = aprobacion.veredicto(aprob("autonomia_ganada:p0"), tenant="rapilink", herramienta="reiniciar_ont",
                         argumentos=ARGS)
comprobar(not v.permitido and v.codigo == aprobacion.AUTONOMIA_NO_VIGENTE,
          "una promocion vieja (p0) no firma aunque haya otra vigente", str(v))
for e in ({"autonoma": False, "estado": "degradada", "promocion_id": None},
          {"autonoma": False, "estado": "retirada", "promocion_id": None},
          {"autonoma": False, "estado": "desconocido", "promocion_id": None}):
    estado["v"] = e
    v = aprobacion.veredicto(aprob("autonomia_ganada:p1"), tenant="rapilink", herramienta="reiniciar_ont",
                             argumentos=ARGS)
    comprobar(not v.permitido and v.codigo == aprobacion.AUTONOMIA_NO_VIGENTE,
              f"{e['estado']}: no firma", str(v))
consultas.clear()
v = aprobacion.veredicto(aprob("Ana Perez"), tenant="rapilink", herramienta="reiniciar_ont", argumentos=ARGS)
comprobar(v.permitido and consultas == [], "una persona aprueba como siempre, sin consultar la autonomia",
          f"{v} {consultas}")
estado["v"] = {"autonoma": True, "estado": "activa", "promocion_id": "p1"}
import dataclasses                                               # noqa: E402

falsa = dataclasses.replace(aprob("autonomia_ganada:p1"), argumentos={"sn_onu": "OTRO"})
v = aprobacion.veredicto(falsa, tenant="rapilink", herramienta="reiniciar_ont", argumentos={"sn_onu": "OTRO"})
comprobar(not v.permitido and v.codigo == aprobacion.OTROS_ARGUMENTOS,
          "la autonomia NO salta las ataduras: otros argumentos siguen bloqueando", str(v))

# ---------------------------------------------------------------------------
print("\nC2 · ninguna persona firma como la autonomia")
comprobar(api._aprobador_reservado("autonomia_ganada:p1") and api._aprobador_reservado("  AUTONOMIA_GANADA:x")
          and not api._aprobador_reservado("Ana Perez"), "el prefijo esta reservado (sin importar mayusculas)")
api.persistencia.accion_propuesta_de = lambda tenant, i: {"id": i, "estado": "pendiente",
                                                         "conversation_id": "c-1", "herramienta": "reiniciar_ont"}
api._config_de = lambda tenant: SimpleNamespace(herramientas=[])
aprobadas: list[tuple] = []
api._aprobar_y_ejecutar = lambda config, tenant, i, quien: aprobadas.append(quien) or (api.jsonify({}), 200)
r = api.app.test_client().post("/acciones/propuestas/acc-1/aprobar",
                               json={"tenant": "rapilink", "revisado_por": "autonomia_ganada:p1"})
comprobar(r.status_code == 400 and aprobadas == [], "la cola rechaza firmar como la autonomia",
          f"{r.status_code} {aprobadas}")
r = api.app.test_client().post("/acciones/propuestas/acc-1/aprobar",
                               json={"tenant": "rapilink", "revisado_por": "Ana Perez"})
comprobar(aprobadas == ["Ana Perez"], "y una persona aprueba como siempre", str(aprobadas))

# ---------------------------------------------------------------------------
print("\nC3 · despues del turno, solo la irreversible con autonomia vigente se ejecuta")
llamadas: list[tuple] = []
api._aprobar_y_ejecutar_datos = lambda config, tenant, i, quien, al_bloquear="vencer": (
    llamadas.append((tenant, i, quien, al_bloquear)) or ({"ok": True}, 200))
REINICIO = SimpleNamespace(nombre="reiniciar_ont", aprobacion_humana=True, irreversible=True)
TICKET = SimpleNamespace(nombre="crear_ticket", aprobacion_humana=True, irreversible=False)
registro.vigente = lambda tenant, h: {"id": "p1", "estado": "activa"} if h == "reiniciar_ont" else None
r = api._ejecutar_si_es_autonoma(SimpleNamespace(), "rapilink", "acc-9", REINICIO)
comprobar(r == {"ok": True} and llamadas == [("rapilink", "acc-9", "autonomia_ganada:p1", "liberar")],
          "con autonomia vigente: la misma cadena, firmada por la promocion, liberando si una guarda frena",
          str(llamadas))
llamadas.clear()
registro.vigente = lambda tenant, h: {"id": "p1", "estado": "activa"}     # aunque la tuviera
comprobar(api._ejecutar_si_es_autonoma(SimpleNamespace(), "rapilink", "acc-9", TICKET) is None and llamadas == [],
          "una que no es irreversible no entra a este camino, aunque figure promovida")
registro.vigente = lambda tenant, h: {"id": "p1", "estado": "degradada"}
comprobar(api._ejecutar_si_es_autonoma(SimpleNamespace(), "rapilink", "acc-9", REINICIO) is None and llamadas == [],
          "sin autonomia vigente: queda en la cola, no se ejecuta")


def base_caida(tenant, h):
    raise SystemExit("No hay datos de conexion")


registro.vigente = base_caida
comprobar(api._ejecutar_si_es_autonoma(SimpleNamespace(), "rapilink", "acc-9", REINICIO) is None and llamadas == [],
          "con la base caida: falla cerrado, no se ejecuta")

# ---------------------------------------------------------------------------
print("\nC4 y D1 · si una guarda la frena vuelve a una persona; si falla, se degrada")
import importlib                                                # noqa: E402

api2 = importlib.reload(api)
api2._TOKEN_SERVICIO = None
quedo: list[tuple] = []
api2.persistencia.reservar_accion = lambda tenant, i, quien: {
    "ok": True, "accion": {"id": i, "herramienta": "reiniciar_ont", "conversation_id": "c-1",
                           "argumentos": ARGS}}
api2.persistencia.accion_propuesta_de = lambda tenant, i: {"id": i, "estado": "ejecutando",
                                                          "herramienta": "reiniciar_ont", "argumentos": ARGS}
api2.persistencia.liberar_accion = lambda tenant, i, codigo: quedo.append(("liberada", codigo))
api2.persistencia.vencer_accion = lambda tenant, i, codigo, conv: quedo.append(("vencida", codigo))
api2.persistencia.resolver_ejecucion_de_accion = lambda *a, **k: quedo.append(("resuelta", k.get("codigo_error")))
api2.persistencia.guardar_verificacion_pendiente = lambda *a, **k: None
api2.revalidacion.revalidar = lambda *a, **k: SimpleNamespace(desenlace="cumple", codigo="", detalle="")
api2._confirmar_efecto = lambda *a, **k: (None, None)
degradadas: list[tuple] = []
api2._degradar_autonomia = lambda tenant, h, motivo, ev: degradadas.append((h, motivo))
CONFIG = SimpleNamespace(herramientas=[SimpleNamespace(nombre="reiniciar_ont", aprobacion_humana=True,
                                                       irreversible=True, politica=None)])
bloqueo = sorted(api2.motor.CODIGOS_DE_BLOQUEO)[0]
api2.motor.ejecutar_accion_irreversible = lambda config, fila, tenant: ({"error": "x"}, bloqueo, None)
datos, codigo = api2._aprobar_y_ejecutar_datos(CONFIG, "rapilink", "acc-9", "autonomia_ganada:p1",
                                               al_bloquear="liberar")
comprobar(quedo == [("liberada", bloqueo)] and datos["estado"] == "pendiente" and codigo == 409,
          "autonoma frenada por una guarda: vuelve a la cola de una persona", f"{quedo} {datos}")
quedo.clear()
datos, codigo = api2._aprobar_y_ejecutar_datos(CONFIG, "rapilink", "acc-9", "Ana Perez")
comprobar(quedo == [("vencida", bloqueo)], "aprobada por una persona y frenada: se vence como siempre", str(quedo))
quedo.clear()
api2.motor.ejecutar_accion_irreversible = lambda config, fila, tenant: ({"error": "502"}, "HTTP_502", None)
datos, codigo = api2._aprobar_y_ejecutar_datos(CONFIG, "rapilink", "acc-9", "autonomia_ganada:p1",
                                               al_bloquear="liberar")
comprobar(("resuelta", "HTTP_502") in quedo and degradadas and degradadas[0][0] == "reiniciar_ont",
          "una ejecucion que fallo degrada la autonomia (condicion 4)", f"{quedo} {degradadas}")
degradadas.clear()
api2.motor.ejecutar_accion_irreversible = lambda config, fila, tenant: ({"ok": True}, None, None)
datos, codigo = api2._aprobar_y_ejecutar_datos(CONFIG, "rapilink", "acc-9", "autonomia_ganada:p1")
comprobar(codigo == 200 and degradadas == [], "una que salio bien no degrada nada", f"{codigo} {degradadas}")
with api2.app.app_context():
    r = api2._aprobar_y_ejecutar(CONFIG, "rapilink", "acc-9", "Ana Perez")
comprobar(isinstance(r, tuple) and r[1] == 200, "el envoltorio Flask de siempre sigue devolviendo (respuesta, codigo)")

# ---------------------------------------------------------------------------
print("\nD2 · una verificacion no confirmada tambien degrada")
api3 = importlib.reload(api)
degradadas3: list[tuple] = []
api3._degradar_autonomia = lambda tenant, h, motivo, ev: degradadas3.append((h, motivo))
from nucleo.seguimiento import verificacion_accion             # noqa: E402

pend = {"id": "v-1", "herramienta": "reiniciar_ont", "intentos": 0, "max_intentos": 3,
        "medicion_previa": {}, "vencida": True}
api3.persistencia.verificacion_pendiente_de = lambda tenant, conv: pend
api3.persistencia.resolver_verificacion = lambda *a, **k: None
api3.motor.medir_para_verificar = lambda *a, **k: {}
for resultado, debe in ((verificacion_accion.NO_CONFIRMADA, True), (verificacion_accion.CONFIRMADA, False)):
    degradadas3.clear()
    api3.verificacion_accion.evaluar = lambda *a, r=resultado: (r, "x")
    CONF_V = SimpleNamespace(herramientas=[SimpleNamespace(
        nombre="reiniciar_ont", verificacion=SimpleNamespace(comprobaciones=[1], escalar_si_no_confirma=""))],
        identidad=SimpleNamespace(slug="rapilink"), variables_tenant={})
    try:
        api3._resolver_verificacion_pendiente(CONF_V, "rapilink", {"conversacion_id": "c-1", "sesion": None})
    except Exception as e:                                          # noqa: BLE001
        comprobar(False, f"_resolver_verificacion_pendiente corre ({resultado})", repr(e))
    comprobar(bool(degradadas3) == debe, f"{resultado}: {'degrada' if debe else 'no degrada'}", str(degradadas3))

# ---------------------------------------------------------------------------
print("\nC5 · el turno dice 'quedo pedido', nunca 'ya se hizo'")
from nucleo.modelo import motor                                  # noqa: E402

registro.vigente = lambda tenant, h: {"id": "p1", "estado": "activa"}
comprobar(motor._tiene_autonomia_ganada("rapilink", REINICIO) is True
          and motor._tiene_autonomia_ganada("rapilink", TICKET) is False,
          "solo la irreversible con autonomia vigente cuenta como autonoma")
registro.vigente = base_caida
comprobar(motor._tiene_autonomia_ganada("rapilink", REINICIO) is False, "y con la base caida, no")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La autonomia ganada pasa por la misma cadena, nadie firma por ella, y se pierde sola.")
