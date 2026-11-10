# -*- coding: utf-8 -*-
"""
================================================================================
 EL RELOJ CIERRA LAS VERIFICACIONES QUE EL CLIENTE NO VUELVE A ABRIR (10/11/2026)
================================================================================

Antes una verificacion pendiente (reiniciar el equipo y medir si volvio) solo
se resolvia en el turno siguiente del cliente. Si no volvia a escribir -- el
caso feliz--, la conversacion no se cerraba nunca sola y la herramienta perdia
la autonomia ganada. Se afirma el EFECTO, contra PostgreSQL real:

  - una vencida se mide con la sesion rearmada de lo guardado (identidad y
    serial), se resuelve, y la conversacion PUEDE cerrarse;
  - una que termina sin efecto escala la conversacion y degrada la autonomia;
  - una reciente no se toca: el turno del cliente tiene prioridad.

Lo unico sustituido: la medicion contra el proveedor (motor.medir_para_
verificar) y el registro de autonomia. La consulta, la evaluacion, la
escritura y la transicion son las reales.

    py -3.13 tests/test_verificaciones_vencidas_base.py
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

fallos: list[str] = []


def comprobar(condicion, que, detalle=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] necesita {faltan} y una base construida por el ledger")
    sys.exit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from base_local import exigir_base_local                          # noqa: E402
exigir_base_local(__file__)

from nucleo.config.schema import Comprobacion, Verificacion       # noqa: E402
from nucleo.modelo import motor                                   # noqa: E402
from nucleo.persistencia import autonomia_ganada as registro      # noqa: E402
from nucleo.relevo import transiciones as T                       # noqa: E402
from nucleo.seguimiento import verificaciones_vencidas as V       # noqa: E402

admin = psycopg.connect(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
                        dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
                        password=os.environ["DBPASSWORD"], autocommit=True,
                        row_factory=dict_row)
ORG = uuid.uuid4()
TEN = f"prueba-vv-{uuid.uuid4().hex[:8]}"


def sembrar_org():
    valores = {"id": str(ORG), "name": TEN, "api_key": f"k-{ORG}", "company_name": TEN}
    for f in admin.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='public' and table_name='organization' "
            "and is_nullable='NO' and column_default is null").fetchall():
        if f["column_name"] in valores:
            continue
        tipo = f["data_type"]
        valores[f["column_name"]] = (True if tipo == "boolean"
                                     else 0 if tipo in ("integer", "bigint", "smallint", "numeric")
                                     else "{}" if tipo in ("json", "jsonb", "ARRAY") else "")
    cols = ", ".join('"' + k + '"' for k in valores)
    admin.execute(f"insert into public.organization ({cols}) values ({', '.join(['%s'] * len(valores))})",
                  list(valores.values()))
    admin.execute("insert into asistente.tenant_config (organization_id, slug) values (%s, %s) "
                  "on conflict do nothing", (str(ORG), TEN))


def conversacion():
    return str(admin.execute(
        """insert into asistente.conversations
             (organization_id, canal, usuario_externo, estado, control,
              relevo_version, id_cliente, nombre_cliente, datos_sesion)
           values (%s, 'whatsapp', %s, 'abierta', 'ia', 1, '1234', 'Ana', %s)
           returning id""",
        (str(ORG), f"57300{uuid.uuid4().int % 10**7:07d}",
         json.dumps({"sn_onu": "HWTCAF721761"}))).fetchone()["id"])


def verificacion(cid, *, hace_minutos, intentos=0, max_intentos=3):
    return str(admin.execute(
        """insert into asistente.verificaciones_accion
             (organization_id, conversation_id, herramienta, espera_segundos,
              max_intentos, intentos, medicion_previa, estado, ejecutada_en)
           values (%s, %s, 'reiniciar_ont', 120, %s, %s, %s,
                   'VERIFICACION_PENDIENTE', now() - make_interval(mins => %s))
           returning id""",
        (str(ORG), cid, max_intentos, intentos,
         json.dumps({"consultar_estado_ont": {"last_status_change": "A"}}),
         hace_minutos)).fetchone()["id"])


def estado_de(vid):
    return admin.execute("select estado, intentos from asistente.verificaciones_accion "
                         "where id = %s", (vid,)).fetchone()


reiniciar = SimpleNamespace(nombre="reiniciar_ont", verificacion=Verificacion(
    espera_segundos=120, max_intentos=3, escalar_si_no_confirma="accion_sin_efecto",
    comprobaciones=[Comprobacion(herramienta="consultar_estado_ont",
                                 campo="last_status_change", regla="cambio")]))
config = SimpleNamespace(herramientas=[reiniciar], identidad=SimpleNamespace(slug=TEN),
                         variables_tenant={})

sesiones_vistas: list = []
despues = {"valor": "B"}


def falsa_medicion(cfg, verif, sesion, tenant, variables):
    sesiones_vistas.append(sesion)
    return {"consultar_estado_ont": {"last_status_change": despues["valor"]}}


degradadas: list = []
motor.medir_para_verificar = falsa_medicion
registro.degradar = lambda tenant, herr, motivo, evidencia=None: degradadas.append(herr) or {"ok": 1}

sembrar_org()
try:
    print("\nel caso feliz: el equipo reinicio y el cliente no volvio")
    c1 = conversacion()
    v1 = verificacion(c1, hace_minutos=60)
    r = T.cerrar(TEN, c1, por="plazo")
    comprobar(not r.aplicada and r.motivo == "verificacion_pendiente",
              "antes: la conversacion no se puede cerrar sola", r.motivo)

    informe = V.barrer(config, TEN)
    comprobar(estado_de(v1)["estado"] == "ACCION_CONFIRMADA",
              f"el reloj la mide y la confirma ({estado_de(v1)})")
    s = sesiones_vistas[-1]
    comprobar(getattr(s, "id_cliente", None) == "1234" and getattr(s, "sn_onu", None) == "HWTCAF721761",
              "con la sesion rearmada de lo que la conversacion guardo")
    comprobar(informe["confirmadas"] == 1, f"y lo informa ({informe})")
    r = T.cerrar(TEN, c1, por="plazo")
    comprobar(r.aplicada, f"despues: la conversacion ya se puede cerrar ({r.motivo})")

    print("\nsin efecto: pasa a una persona y la herramienta pierde la autonomia")
    despues["valor"] = "A"
    c2 = conversacion()
    v2 = verificacion(c2, hace_minutos=60, intentos=2, max_intentos=3)
    informe = V.barrer(config, TEN)
    comprobar(estado_de(v2)["estado"] == "ACCION_NO_CONFIRMADA",
              f"el ultimo intento sin cambio: no confirmada ({estado_de(v2)})")
    comprobar(degradadas == ["reiniciar_ont"], f"la autonomia se degrada ({degradadas})")
    fila = admin.execute("select control, escalada_a_humano from asistente.conversations "
                         "where id = %s", (c2,)).fetchone()
    comprobar(fila["control"] != "ia" and fila["escalada_a_humano"],
              f"y la conversacion queda en manos de una persona ({fila})")
    comprobar(informe["escaladas"] == 1, "lo informa")

    print("\nquedan intentos: sigue pendiente")
    c3 = conversacion()
    v3 = verificacion(c3, hace_minutos=60, intentos=0, max_intentos=3)
    V.barrer(config, TEN)
    comprobar(estado_de(v3) == {"estado": "VERIFICACION_PENDIENTE", "intentos": 1},
              f"no confirma todavia y suma un intento ({estado_de(v3)})")

    print("\nla reciente es del turno del cliente")
    c4 = conversacion()
    v4 = verificacion(c4, hace_minutos=5)
    antes = len(sesiones_vistas)
    V.barrer(config, TEN)
    comprobar(estado_de(v4) == {"estado": "VERIFICACION_PENDIENTE", "intentos": 0}
              and len(sesiones_vistas) == antes + 1,
              "vencida hace menos del margen: el reloj no la toca (solo midio la de arriba)")

    print("\nen seco no escribe")
    c5 = conversacion()
    v5 = verificacion(c5, hace_minutos=60)
    informe = V.barrer(config, TEN, simular=True)
    comprobar(estado_de(v5)["estado"] == "VERIFICACION_PENDIENTE" and "haria" in informe,
              f"--dry-run dice que haria y no mide ({informe})")
finally:
    admin.execute("delete from asistente.verificaciones_accion where organization_id = %s", (str(ORG),))
    admin.execute("delete from asistente.relevo_eventos where organization_id = %s", (str(ORG),))
    admin.execute("delete from asistente.conversations where organization_id = %s", (str(ORG),))

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s)")
    sys.exit(1)
print("\n[OK] Una verificacion que el cliente no vuelve a abrir la cierra el reloj.")
