# -*- coding: utf-8 -*-
"""
================================================================================
 LA EVIDENCIA DE UNA ACCION  --  contra PostgreSQL (31/10/2026)
================================================================================

    DBHOST=127.0.0.1 DBPORT=55471 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_autonomia_ganada_base.py

Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni la de
produccion. nucleo/persistencia/autonomia_ganada.medir cuenta lo que decide si
una accion gana autonomia (PRD §2). Afirma el NUMERO EXACTO:

  - revisada es lo que una persona decidio; vencida y cancelada NO cuentan
    (nadie la miro, e inflarian la tasa sin evidencia);
  - la ventana se mide por cuando se DECIDIO, no por cuando nacio;
  - otra herramienta y otra empresa no mueven nada;
  - cada estado de verificacion en su conteo.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                      # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "autonomia_" + uuid.uuid4().hex[:6]
AHORA = datetime.now(timezone.utc)
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)
def q(sentencia, params=None):
    with psycopg.connect(f"host={HOST} port={PUERTO} dbname={BASE} user={USUARIO} password={CLAVE} "
                         f"sslmode=disable connect_timeout=15", autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def q_sin_disparadores(sentencia, params=None):
    with psycopg.connect(f"host={HOST} port={PUERTO} dbname={BASE} user={USUARIO} password={CLAVE} "
                         f"sslmode=disable connect_timeout=15", autocommit=True) as con:
        con.execute("set session_replication_role = replica")
        con.execute(sentencia, params)


def fila_minima(tabla: str, fijos: dict) -> None:
    cols = q("""select column_name, data_type, character_maximum_length from information_schema.columns
                where table_schema = 'public' and table_name = %s
                  and is_nullable = 'NO' and column_default is null""", (tabla,))
    valores = dict(fijos)
    por_tipo = {"uuid": lambda: str(uuid.uuid4()), "boolean": lambda: False,
                "integer": lambda: 0, "bigint": lambda: 0, "smallint": lambda: 0,
                "jsonb": lambda: "{}", "json": lambda: "{}",
                "timestamp with time zone": lambda: "now", "date": lambda: "2026-01-01"}
    for nombre, tipo, largo in cols:
        if nombre not in valores:
            valor = por_tipo.get(tipo, lambda: "x" + uuid.uuid4().hex[:8])()
            valores[nombre] = valor[:largo] if largo and isinstance(valor, str) else valor
    nombres = list(valores)
    q(f"insert into public.{tabla} ({', '.join(nombres)}) values ({', '.join(['%s'] * len(nombres))})",
      [valores[n] for n in nombres])


def hace(dias: float) -> datetime:
    return AHORA - timedelta(days=dias)


def conversacion(org, canal="whatsapp") -> str:
    return str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                    values (%s, %s, %s) returning id""", (org, canal, "57300" + uuid.uuid4().hex[:7]))[0][0])


def propuesta(org, estado, *, herramienta="reiniciar_ont", nacio=None, decidida=None,
              canal="whatsapp", rol="soporte_tecnico_cliente", revisado_por="Ana Perez", huella=None):
    #  Historia sembrada: una vinculante (con huella) solo puede NACER pendiente
    #  por disparador. Para escribir su desenlace de una vez, la siembra apaga
    #  los disparadores SOLO en esta sesion de la base efimera.
    sembrar = q_sin_disparadores if huella else q
    sembrar("""insert into asistente.acciones_propuestas
           (organization_id, conversation_id, herramienta, resumen, propuesto_por, estado,
            creado_en, revisado_en, motivo_rechazo, rol_solicitante, revisado_por, hash_argumentos,
            origen)
         values (%s, %s, %s, 'Reiniciar', 'ia', %s, %s, %s, %s, %s, %s, %s, %s)""",
      (org, conversacion(org, canal), herramienta, estado, nacio or hace(3), decidida,
       "x" if estado in ("cancelada", "rechazada") else None, rol,
       revisado_por if decidida else None, huella, f"prueba:{uuid.uuid4()}" if huella else None))


def verificacion(org, estado, *, herramienta="reiniciar_ont", cuando=None, canal="whatsapp"):
    q("""insert into asistente.verificaciones_accion
           (organization_id, conversation_id, herramienta, ejecutada_en, espera_segundos, max_intentos, estado)
         values (%s, %s, %s, %s, 120, 3, %s)""",
      (org, conversacion(org, canal), herramienta, cuando or hace(3), estado))


print("=" * 74)
print(" LA EVIDENCIA DE UNA ACCION")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)

    org, otra = str(uuid.uuid4()), str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org autonomia"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, "rapilink"))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE

    from nucleo.persistencia import autonomia_ganada as medicion   # noqa: E402

    # Dentro de la ventana (decididas hace 3 dias):
    for estado in ("ejecutada_ok", "ejecutada_ok", "ejecutada_ok", "aprobada"):
        propuesta(org, estado, decidida=hace(3))
    propuesta(org, "rechazada", decidida=hace(2))
    propuesta(org, "ejecutada_fallo", decidida=hace(2))
    propuesta(org, "desconocida", decidida=hace(2))
    # Nadie las miro: no son evidencia.
    propuesta(org, "vencida", decidida=hace(2))
    propuesta(org, "cancelada", decidida=hace(2))
    propuesta(org, "pendiente")
    # Nacio hace 40 dias pero se DECIDIO hace 5: cuenta.
    propuesta(org, "ejecutada_ok", nacio=hace(40), decidida=hace(5))
    # Nacio hace 5 pero se decidio hace 35 (imposible en la vida real, pero
    # prueba que manda 'revisado_en'): NO cuenta.
    propuesta(org, "ejecutada_ok", nacio=hace(5), decidida=hace(35))
    # Fuera de la ventana, otra herramienta, otra empresa:
    propuesta(org, "rechazada", decidida=hace(45))
    propuesta(org, "rechazada", herramienta="cambiar_tipo_onu", decidida=hace(2))
    propuesta(otra, "rechazada", decidida=hace(2))
    # NO son evidencia (auditor de frontera, 31/10/2026): la Bandeja (la propone
    # y la aprueba la misma persona), el simulador, y lo que firmo la autonomia.
    propuesta(org, "ejecutada_ok", decidida=hace(2), rol="bandeja")
    propuesta(org, "ejecutada_ok", decidida=hace(2), canal="simulador-whatsapp")
    propuesta(org, "ejecutada_ok", decidida=hace(2), revisado_por="autonomia_ganada:p1", huella="h-equipo-1")
    propuesta(org, "ejecutada_ok", decidida=hace(0.5 / 24), revisado_por="autonomia_ganada:p1",
              huella="h-equipo-2")
    # Lo que firmo la autonomia no suma a favor, pero SI en contra: su falla cuenta.
    propuesta(org, "ejecutada_fallo", decidida=hace(2), revisado_por="autonomia_ganada:p1",
              huella="h-equipo-3")

    for estado in ("ACCION_CONFIRMADA", "ACCION_CONFIRMADA", "ACCION_NO_CONFIRMADA",
                   "NO_VERIFICABLE", "VERIFICACION_PENDIENTE"):
        verificacion(org, estado)
    verificacion(org, "ACCION_NO_CONFIRMADA", cuando=hace(45))
    verificacion(org, "ACCION_NO_CONFIRMADA", herramienta="cambiar_tipo_onu")
    verificacion(otra, "ACCION_NO_CONFIRMADA")
    verificacion(org, "ACCION_NO_CONFIRMADA", canal="simulador-whatsapp")

    from nucleo.canales import canal as canales                       # noqa: E402
    m = medicion.medir("rapilink", "reiniciar_ont", hace(30), AHORA, canales=canales.REALES)
    print()
    comprobar(m["revisadas"] == 8, "revisadas: 4 aprobadas + rechazada + fallo + incierta + la que nacio "
              "antes y se decidio adentro = 8 (sin vencida, cancelada, pendiente, Bandeja, simulador ni lo "
              "que firmo la autonomia)", str(m))
    comprobar(m["rechazadas"] == 1, "rechazadas: 1 (la de afuera, la de otra herramienta y la de otra "
              "empresa no)", str(m))
    comprobar(m["fallidas"] == 3, "fallidas: ejecutada_fallo + desconocida + la que fallo SOLA "
              "(lo autonomo no suma a favor, pero si en contra)", str(m))
    comprobar(m["degradaciones"] == 0, "sin degradaciones todavia", str(m))
    comprobar((m["confirmadas"], m["no_confirmadas"], m["no_verificables"], m["pendientes"]) == (2, 1, 1, 1),
              "verificaciones: 2 confirmadas, 1 no confirmada, 1 no verificable, 1 pendiente", str(m))
    vacia = medicion.medir("otra_empresa", "reiniciar_ont", hace(30), AHORA, canales=canales.REALES)
    comprobar(vacia["revisadas"] == 1 and vacia["no_confirmadas"] == 1,
              "la otra empresa ve solo lo suyo", str(vacia))

    # ------------------------------------------------------------------
    # FASE B: promover, retirar, degradar, vigente -- con los permisos reales
    # ------------------------------------------------------------------
    print()
    from nucleo.persistencia import db                                  # noqa: E402
    from nucleo.seguridad import autonomia_ganada as ag                 # noqa: E402

    leer = medicion.vigente
    comprobar(ag.vigente("rapilink", "reiniciar_ont", leer=leer)["estado"] == "sin_registro",
              "sin fila, no es autonoma")
    medicion.promover("rapilink", "reiniciar_ont", "Ana · u-1", "promovida", {"evidencia": {"revisadas": 40}})
    v = ag.vigente("rapilink", "reiniciar_ont", leer=leer)
    comprobar(v["autonoma"] and v["promocion_id"], "promovida con el rol del runtime (app_backend, lo unico que asume motor_user): autonoma", str(v))
    comprobar(ag.vigente("otra_empresa", "reiniciar_ont", leer=leer)["autonoma"] is False,
              "la promocion de una empresa no le da autonomia a otra")
    comprobar(ag.vigente("rapilink", "cambiar_tipo_onu", leer=leer)["autonoma"] is False,
              "ni a otra herramienta")

    # El runtime (app_backend) NO puede escribir 'activa'.
    try:
        with db.sesion("rapilink") as (cur, org):
            cur.execute("""insert into asistente.autonomia_ganada (organization_id, herramienta, estado, actor)
                           values (%s, 'cambiar_tipo_onu', 'activa', 'motor')""", (org,))
        comprobar(False, "app_backend no puede insertar una promocion")
    except Exception as e:                                              # noqa: BLE001
        comprobar("permission denied" in str(e).lower() or "privilegio" in str(e).lower(),
                  "app_backend no puede insertar directo (solo por las funciones)", type(e).__name__)
    try:
        with db.sesion("rapilink") as (cur, org):
            cur.execute("update asistente.autonomia_ganada set estado = 'activa'")
        comprobar(False, "nadie edita la historia")
    except Exception as e:                                              # noqa: BLE001
        comprobar("permission denied" in str(e).lower(), "nadie edita la historia (sin UPDATE)",
                  type(e).__name__)

    # El runtime SI puede degradar, solo lo activo, solo lo suyo.
    d = medicion.degradar("rapilink", "reiniciar_ont", "una verificacion no confirmo",
                          {"verificacion": "ACCION_NO_CONFIRMADA"})
    comprobar(d is not None and d["estado"] == "degradada" and d["actor"] == "codigo",
              "degradar: la baja el codigo, con su motivo", str(d))
    comprobar(ag.vigente("rapilink", "reiniciar_ont", leer=leer)["autonoma"] is False,
              "degradada: deja de ser autonoma desde la proxima consulta")
    comprobar(medicion.degradar("rapilink", "reiniciar_ont", "otra vez", {}) is None,
              "degradar lo que ya no esta activa no agrega ruido")
    comprobar(medicion.medir("rapilink", "reiniciar_ont", hace(30), hace(-1), canales=canales.REALES)
              ["degradaciones"] == 1, "la degradacion queda en la evidencia de la ventana")
    try:
        with db.sesion("rapilink") as (cur, org):
            cur.execute("select asistente.autonomia_ganada_degradar(%s, 'reiniciar_ont', 'x', '{}'::jsonb)",
                        (otra,))
        comprobar(False, "no se degrada la autonomia de otra empresa")
    except Exception:                                                   # noqa: BLE001
        comprobar(True, "no se degrada la autonomia de otra empresa")
    medicion.promover("rapilink", "reiniciar_ont", "Ana · u-1", "otra vez", {})
    try:
        medicion.promover("rapilink", "reiniciar_ont", "Ana · u-1", "doble clic", {})
        comprobar(False, "la base rechaza una segunda promocion activa")
    except Exception as e:                                              # noqa: BLE001
        comprobar("ya es autonoma" in str(e), "la base rechaza una segunda promocion activa",
                  type(e).__name__)
    medicion.retirar("rapilink", "reiniciar_ont", "Luis · u-2", "la quito para revisar")
    v = medicion.vigente("rapilink", "reiniciar_ont")
    comprobar(v["estado"] == "retirada" and v["actor"] == "Luis · u-2",
              "retirada por una persona: la ultima fila manda", str(v))
    historia = q("select estado from asistente.autonomia_ganada where organization_id = %s order by creado_en",
                 (org,))

    # Los frenos de la ejecucion autonoma, contados en la base.
    print()
    verificacion(org, "VERIFICACION_PENDIENTE", cuando=hace(0.2))         # ~5 h: sin resolver
    verificacion(org, "VERIFICACION_PENDIENTE", cuando=hace(0.01))        # 15 min: todavia no
    comprobar(medicion.verificaciones_sin_resolver("rapilink", "reiniciar_ont", 1, hace(30)) == 2,
              "sin resolver: las pendientes con mas de 1 h (la de hace 3 dias y la de hace 5 h)")
    comprobar(medicion.verificaciones_sin_resolver("rapilink", "reiniciar_ont", 1, hace(0.3)) == 1,
              "desde la promocion: las de antes no cuentan (solo la de hace 5 h)")
    comprobar(medicion.ejecuciones_autonomas("rapilink", "reiniciar_ont", horas=1) == 1,
              "ejecuciones autonomas en la ultima hora: 1")
    comprobar(medicion.ejecuciones_autonomas("rapilink", "reiniciar_ont", horas=96) == 3,
              "en 4 dias: 3 (dos que salieron bien y una que fallo)")
    comprobar(medicion.ejecuciones_autonomas("rapilink", "reiniciar_ont", horas=96,
                                             hash_argumentos="h-equipo-1") == 1,
              "del mismo equipo (misma huella): 1")

    # T20: una ejecucion huerfana ('ejecutando' de hace rato) degrada la autonomia.
    medicion.promover("rapilink", "reiniciar_ont", "Ana · u-1", "para probar T20", {})
    q_sin_disparadores("""insert into asistente.acciones_propuestas
                            (organization_id, conversation_id, herramienta, resumen, propuesto_por, estado,
                             creado_en, revisado_en, revisado_por, hash_argumentos, origen)
                          values (%s, %s, 'reiniciar_ont', 'Reiniciar', 'ia', 'ejecutando', %s, %s,
                                  'autonomia_ganada:p9', 'h-huerfana', 'prueba:huerfana')""",
                       (org, conversacion(org), hace(1), hace(1)))
    barridas = db.barrer_acciones_ejecutando("rapilink", 30)
    comprobar(len(barridas) == 1 and medicion.vigente("rapilink", "reiniciar_ont")["estado"] == "degradada",
              "T20: una ejecucion que quedo huerfana degrada la autonomia de su herramienta",
              str(medicion.vigente("rapilink", "reiniciar_ont")))
    comprobar([h[0] for h in historia] == ["activa", "degradada", "activa", "retirada"],
              "la historia completa queda: nada se borra", str(historia))
finally:
    try:
        with psycopg.connect(f"host={HOST} port={PUERTO} dbname=postgres user={USUARIO} password={CLAVE} "
                             f"sslmode=disable", autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception:                                                  # noqa: BLE001
        pass

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] La evidencia de una accion se cuenta exacta, por empresa y por cuando se decidio.")
