# -*- coding: utf-8 -*-
"""
================================================================================
 EL TABLERO DE CAPACIDAD  --  contra PostgreSQL, por las rutas reales
================================================================================

    DBHOST=127.0.0.1 DBPORT=55471 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_tablero_capacidad_base.py

30/10/2026. SPEC/objetivos/tablero-de-capacidad.md (C1-C6), PRD §2 y §8.17.

Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni la de
produccion. Siembra una conversacion por cada desenlace que el tablero tiene
que distinguir y afirma el NUMERO EXACTO de cada metrica -- no que "algo
salga". Lo que se protege, en una linea cada uno:

  - una conversacion donde una persona escribio, tomo, intervino, recibio la
    escalada o tuvo que aprobar una accion NUNCA cuenta como resuelta sin
    persona (C3);
  - solo cuentan los canales reales: el simulador y el asistente interno no
    mueven ningun numero (C2), y otra empresa tampoco;
  - recontacto es el MISMO numero que vuelve dentro de la ventana, no despues;
  - una visita evitada es un reinicio CONFIRMADO sin visita del mismo cliente
    en los dias siguientes -- ni uno sin efecto, ni uno seguido de visita;
  - sin minutos declarados por la empresa no hay minutos ahorrados: null con
    el motivo, nunca un valor por defecto (C5);
  - un periodo anterior a que exista 'messages.origen' se recorta y lo dice (C4);
  - la tasa de escalada vieja deja de contar el simulador (C6).
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
BASE = "capacidad_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"
ANA = ("7c9e6679-7425-40de-944b-e07fc1f90ae7", "Ana Perez")
LUIS = ("0f8fad5b-d9cb-469f-a165-70867728950e", "Luis Rojas")
AHORA = datetime.now(timezone.utc)

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)
def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


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


def hace(dias: float = 0, minutos: float = 0) -> datetime:
    return AHORA - timedelta(days=dias, minutes=minutos)


def conversacion(org, numero, *, nacio: datetime, dura_min: float = 10,
                 canal: str = "whatsapp", cerrada: bool = True, **columnas) -> str:
    """Una conversacion con un mensaje del cliente al nacer y uno de la IA
    'dura_min' minutos despues (el fin de la atencion)."""
    cid = str(q("""insert into asistente.conversations
                     (organization_id, canal, usuario_externo, creado_en, actualizado_en)
                   values (%s, %s, %s, %s, %s) returning id""",
                (org, canal, numero, nacio, nacio))[0][0])
    mensaje(org, cid, "user", "cliente", nacio)
    mensaje(org, cid, "assistant", "ia", nacio + timedelta(minutes=dura_min))
    # En UNA sentencia: 'cerrada_por_tipo' solo se admite en una cerrada
    # (conversations_cierre_solo_si_cerrada).
    if cerrada:
        columnas = {"estado": "cerrada", **columnas}
    if columnas:
        sets = ", ".join(f"{k} = %s" for k in columnas)
        q(f"update asistente.conversations set {sets} where id = %s", [*columnas.values(), cid])
    return cid


def mensaje(org, cid, rol, origen, cuando):
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         values (%s, %s, %s, 'x', %s, %s)""", (org, cid, rol, origen, cuando))


def evento(org, cid, tipo, operador=None):
    if operador:
        q("""insert into asistente.relevo_eventos
               (organization_id, conversation_id, tipo, actor_tipo, actor_usuario_id, actor_nombre)
             values (%s, %s, %s, 'operador', %s, %s)""", (org, cid, tipo, *operador))
    else:
        q("""insert into asistente.relevo_eventos (organization_id, conversation_id, tipo, actor_tipo)
             values (%s, %s, %s, 'sistema')""", (org, cid, tipo))


def verificacion(org, cid, herramienta, estado, cuando):
    q("""insert into asistente.verificaciones_accion
           (organization_id, conversation_id, herramienta, ejecutada_en, espera_segundos,
            max_intentos, estado)
         values (%s, %s, %s, %s, 120, 3, %s)""", (org, cid, herramienta, cuando, estado))


def llamada(org, cid, herramienta, cuando, exito=True):
    q("""insert into asistente.tool_calls (organization_id, conversation_id, herramienta, exito, creado_en)
         values (%s, %s, %s, %s, %s)""", (org, cid, herramienta, exito, cuando))


def encuesta(org, caso, *, puntaje=None, dias=2):
    q("""insert into asistente.encuestas_whatsapp
           (organization_id, caso_id, plantilla, estado, enviada_en, vence_en, puntaje, respondida_en)
         values (%s, %s, 'encuesta', %s, %s, %s, %s, %s)""",
      (org, caso, "respondida" if puntaje else "enviada", hace(dias), hace(dias - 3),
       puntaje, hace(dias - 1) if puntaje else None))


print("=" * 74)
print(" EL TABLERO DE CAPACIDAD")
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

    org = str(uuid.uuid4())
    otra = str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org capacidad"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE

    from nucleo.canales import api                                 # noqa: E402
    from nucleo.canales import canal                               # noqa: E402
    from nucleo.observabilidad import capacidad as tablero         # noqa: E402
    from nucleo.persistencia import capacidad as medicion          # noqa: E402
    from nucleo.persistencia import db                             # noqa: E402

    # ------------------------------------------------------------------
    # Once cerradas en canal real. Duraciones asimetricas a proposito:
    # 10,15,20,25,30,35,40,50,60,70,200 -> mediana 35, promedio 50.5. Una
    # implementacion que promedie en vez de tomar la mediana falla.
    # ------------------------------------------------------------------
    sola = conversacion(org, "573000000001", nacio=hace(6), dura_min=10)
    vuelve = conversacion(org, "573000000002", nacio=hace(5, 20), dura_min=20)
    tarde = conversacion(org, "573000000003", nacio=hace(6, 30), dura_min=30)
    escribio = conversacion(org, "573000000004", nacio=hace(4), dura_min=40)
    tomada = conversacion(org, "573000000005", nacio=hace(4), dura_min=50, tomada_por=ANA[0])
    intervenida = conversacion(org, "573000000006", nacio=hace(4), dura_min=60)
    escalada = conversacion(org, "573000000007", nacio=hace(4), dura_min=70, escalada_a_humano=True)
    con_accion = conversacion(org, "573000000008", nacio=hace(5), dura_min=200)
    inactiva = conversacion(org, "573000000012", nacio=hace(5), dura_min=15,
                            cerrada_por_tipo="inactividad")
    a_mano = conversacion(org, "573000000013", nacio=hace(5), dura_min=25, atendida_manual=True)
    sin_eco = conversacion(org, "573000000014", nacio=hace(6), dura_min=35)

    mensaje(org, escribio, "assistant", "humano", hace(4, -5))
    evento(org, tomada, "tomada", ANA)
    evento(org, intervenida, "intervencion", LUIS)
    q("""insert into asistente.acciones_propuestas
           (organization_id, conversation_id, herramienta, resumen, propuesto_por, estado)
         values (%s, %s, 'reiniciar_ont', 'Reiniciar', 'ia', 'pendiente')""", (org, con_accion))
    # Una nota interna dos dias despues: ni corre el fin (la mediana seguiria
    # en 35) ni vuelve "con persona" a la conversacion.
    mensaje(org, sola, "nota", "humano", hace(4))

    # El mismo numero vuelve: a las 48 h del fin de 'vuelve' (cuenta) y a las
    # 96 h del fin de 'tarde' (no cuenta). A 'sin_eco' le escribe un OPERADOR
    # a las 24 h, en una conversacion nueva sin ningun mensaje del cliente: eso
    # no es un recontacto.
    fin_vuelve = hace(5, 20) + timedelta(minutes=20)
    fin_tarde = hace(6, 30) + timedelta(minutes=30)
    fin_sin_eco = hace(6) + timedelta(minutes=35)
    conversacion(org, "573000000002", nacio=fin_vuelve + timedelta(hours=48), cerrada=False)
    conversacion(org, "573000000003", nacio=fin_tarde + timedelta(hours=96), cerrada=False)
    al_dia = fin_sin_eco + timedelta(hours=24)
    del_operador = str(q("""insert into asistente.conversations
                              (organization_id, canal, usuario_externo, creado_en, actualizado_en)
                            values (%s, 'whatsapp', '573000000014', %s, %s) returning id""",
                         (org, al_dia, al_dia))[0][0])
    mensaje(org, del_operador, "assistant", "humano", al_dia)

    # Lo que NO tiene que contar: canal interno, simulador, otra empresa,
    # abierta, y una cerrada de antes del periodo (con su persona).
    conversacion(org, "573000000009", nacio=hace(3), canal=canal.API)
    conversacion(org, "573000000010", nacio=hace(3), canal=canal.WHATSAPP_SIMULADO)
    conversacion(otra, "573000000001", nacio=hace(3))
    conversacion(org, "573000000011", nacio=hace(3), cerrada=False)
    vieja = conversacion(org, "573000000015", nacio=hace(40))
    evento(org, vieja, "tomada", ("1b4e28ba-2fa1-11d2-883f-0016d3cca427", "Otra Persona"))

    # Visitas (ventana de 7 dias): reinicios confirmados hace 12 dias, ventana
    # cerrada. Cuentan como evitadas v1 (nada despues), v6 (la visita fallo) y
    # v7 (la visita fue ANTES del reinicio). No cuentan: v2 (visita exitosa del
    # mismo cliente en otra conversacion), v5 (la visita la agendo el codigo:
    # queda en ticket_operativo, no en tool_calls), v3 (sin efecto), v4
    # (simulador). v8 es de hace 2 dias: su ventana sigue abierta.
    def reinicio(numero, cuando, estado="ACCION_CONFIRMADA", canal_=canal.WHATSAPP):
        cid = conversacion(org, numero, nacio=cuando, canal=canal_, cerrada=False)
        verificacion(org, cid, "reiniciar_ont", estado, cuando)
        return cid

    reinicio("573000000020", hace(12))
    reinicio("573000000021", hace(12))
    otra_conv = conversacion(org, "573000000021", nacio=hace(10), cerrada=False)
    llamada(org, otra_conv, "agendar_visita_internet", hace(10))
    reinicio("573000000022", hace(12), estado="ACCION_SIN_EFECTO")
    reinicio("573000000023", hace(12), canal_=canal.WHATSAPP_SIMULADO)
    v5 = reinicio("573000000024", hace(12))
    q("update asistente.conversations set ticket_operativo = '90999' where id = %s", (v5,))
    v6 = reinicio("573000000025", hace(12))
    llamada(org, v6, "agendar_visita_internet", hace(10), exito=False)
    v7 = reinicio("573000000026", hace(12))
    llamada(org, v7, "agendar_visita_internet", hace(13))
    reinicio("573000000027", hace(2))

    encuesta(org, "caso-1", puntaje=5)
    encuesta(org, "caso-2", puntaje=3)
    encuesta(org, "caso-3")
    encuesta(org, "caso-4", puntaje=1, dias=40)
    encuesta(otra, "caso-9", puntaje=1)

    # ==================================================================
    print("\n== A. la medicion cruda, en SQL ==")
    m = medicion.medir(TENANT, hace(30), AHORA, canales=canal.REALES,
                       acciones_que_evitan_visita=["reiniciar_ont"],
                       herramientas_de_visita=["agendar_visita_tecnica", "agendar_visita_internet"],
                       ventana_recontacto_horas=72, dias_sin_visita=7)
    comprobar(m["cerradas"] == 11, f"11 cerradas en canal real y en el periodo ({m['cerradas']})")
    comprobar(m["resueltas_sin_persona"] == 4,
              f"4 sin persona: escribio, tomo, intervino, escalada, accion y a mano NO cuentan; "
              f"la nota interna tampoco desmiente 'sola' ({m['resueltas_sin_persona']})")
    comprobar(m["por_inactividad"] == 1,
              f"la cerrada por inactividad va aparte, no como resuelta ({m['por_inactividad']})")
    comprobar(m["evaluables_recontacto"] == 11,
              f"las 11 ya cumplieron sus 72 h ({m['evaluables_recontacto']})")
    comprobar(m["recontactos"] == 1,
              f"1 recontacto: no el de 96 h, ni la conversacion que abrio un operador ({m['recontactos']})")
    comprobar(m["recontactos_sin_persona"] == 1 and m["evaluables_sin_persona"] == 4,
              f"y es de una resuelta sin persona ({m['recontactos_sin_persona']}/{m['evaluables_sin_persona']})")
    comprobar(m["reinicios_confirmados"] == 5 and m["reinicios_en_ventana"] == 1,
              f"5 reinicios con la ventana cerrada y 1 todavia en ventana "
              f"({m['reinicios_confirmados']}, {m['reinicios_en_ventana']})")
    comprobar(m["visitas_evitadas"] == 3,
              f"3 evitadas: ni la visita del mismo cliente, ni la que agendo el codigo ({m['visitas_evitadas']})")
    comprobar(abs((m["minutos_hasta_resolucion"] or 0) - 35.0) < 0.01,
              f"mediana 35 min: no el promedio (50.5) ni corrida por la nota ({m['minutos_hasta_resolucion']})")
    comprobar(m["encuestas_respondidas"] == 2 and m["encuestas_enviadas"] == 3,
              f"2 respondidas de 3 enviadas en el periodo, sin la otra empresa ni la vieja "
              f"({m['encuestas_respondidas']}/{m['encuestas_enviadas']})")
    comprobar(abs((m["satisfaccion_promedio"] or 0) - 4.0) < 0.01,
              f"satisfaccion promedio 4.0 ({m['satisfaccion_promedio']})")
    comprobar(m["personas_que_atendieron"] == 2,
              f"2 personas atendieron en el periodo, no la de la conversacion vieja ({m['personas_que_atendieron']})")

    # ==================================================================
    print("\n== B. el tablero: tasas y minutos, calculados en codigo ==")
    t = tablero.componer(m, minutos_por_conversacion=12, minutos_por_visita=90, personas_del_equipo=4)
    comprobar(t["resolucion_sin_persona"]["tasa"] == round(4 / 11, 4),
              f"4/11 ({t['resolucion_sin_persona']})")
    comprobar(t["recontacto"]["tasa_sin_persona"] == 0.25,
              f"recontacto de las resueltas sin persona 1/4 ({t['recontacto']})")
    comprobar(t["minutos_ahorrados"]["total"] == 4 * 12 + 3 * 90,
              f"minutos: 4x12 + 3x90 = 318 ({t['minutos_ahorrados']})")
    comprobar(t["casos_por_persona"]["valor"] == 2.75,
              f"norte: 11 casos / 4 personas declaradas = 2.75 ({t['casos_por_persona']})")

    sin_declarar = tablero.componer(m, None, None, None)
    comprobar(sin_declarar["minutos_ahorrados"]["total"] is None
              and bool(sin_declarar["minutos_ahorrados"].get("motivo"))
              and sin_declarar["casos_por_persona"]["valor"] is None
              and bool(sin_declarar["casos_por_persona"].get("motivo")),
              "sin minutos ni personas declarados: null con el motivo, nunca un default",
              str(sin_declarar))
    sin_acciones = tablero.componer({**m, "visitas_evitadas": None}, 12, 90, 4)
    comprobar("acciones" in (sin_acciones["minutos_ahorrados"].get("motivo") or ""),
              "con minutos pero sin acciones declaradas, el total dice por que no suma visitas",
              str(sin_acciones["minutos_ahorrados"]))

    vacio = tablero.componer({**m, "cerradas": 0, "resueltas_sin_persona": 0,
                              "evaluables_recontacto": 0, "evaluables_sin_persona": 0},
                             None, None, None)
    comprobar(vacio["resolucion_sin_persona"]["tasa"] is None
              and vacio["recontacto"]["tasa"] is None,
              "sin cerradas: null, no una division por cero ni un 0 inventado")

    # ==================================================================
    print("\n== C. la ruta HTTP ==")
    api._TOKEN_SERVICIO = None
    http = api.app.test_client()
    cuerpo = http.get(f"/reportes/capacidad?tenant={TENANT}&dias=30").get_json() or {}
    comprobar(cuerpo.get("resolucion_sin_persona", {}).get("tasa") == round(4 / 11, 4),
              "GET /reportes/capacidad devuelve la misma tasa", str(cuerpo)[:400])
    comprobar("aviso" not in cuerpo, "30 dias no cruzan la fecha de corte: sin aviso")
    largo = http.get(f"/reportes/capacidad?tenant={TENANT}&dias=90").get_json() or {}
    comprobar(bool(largo.get("aviso")) and largo.get("desde", "") >= tablero.CORTE.isoformat(),
              "90 dias se recortan a la fecha de corte y lo dicen", str(largo)[:300])
    comprobar(http.get("/reportes/capacidad").status_code == 400, "sin tenant: 400")
    comprobar("573000000" not in str(cuerpo), "la respuesta no trae ningun numero de cliente")

    # ==================================================================
    print("\n== E. lo que declara la empresa se edita desde la interfaz (§3.3) ==")
    #  La config tiene que vivir en la base para que el editor la toque: se
    #  siembra la del YAML, como hace cli/cargar_config.py en un alta.
    import yaml                                                     # noqa: E402
    import json                                                     # noqa: E402
    from nucleo.config.schema import TenantConfig                   # noqa: E402
    semilla = TenantConfig(**yaml.safe_load(
        (RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))).model_dump(mode="json")
    q("update asistente.tenant_config set config = %s::jsonb where organization_id = %s",
      (json.dumps(semilla), org))
    api.olvidar_config(TENANT)
    #  La guarda de alineacion del editor protege la base de PRODUCCION de una
    #  copia local adelantada. Esta base es efimera y se borra al terminar.
    os.environ["PERMITIR_CONFIG_SIN_DESPLEGAR"] = "1"
    antes = http.get(f"/reportes/capacidad?tenant={TENANT}&dias=30").get_json() or {}
    comprobar(antes.get("declarado") == {"minutos_por_conversacion": None, "minutos_por_visita": None,
                                         "personas_del_equipo": None},
              "sin declarar: el tablero lo dice y la pantalla no tiene que adivinar", str(antes.get("declarado")))
    r = http.put("/configuracion/capacidad", json={"tenant": TENANT, "minutos_por_conversacion": 12,
                                                   "minutos_por_visita": 90, "personas_del_equipo": 4})
    comprobar(r.status_code == 200, f"PUT /configuracion/capacidad guarda ({r.status_code} {r.get_data(as_text=True)[:200]})")
    despues = http.get(f"/reportes/capacidad?tenant={TENANT}&dias=30").get_json() or {}
    comprobar(despues.get("minutos_ahorrados", {}).get("total") == 4 * 12 + 3 * 90
              and despues.get("casos_por_persona", {}).get("valor") == 2.75,
              "y el tablero ya lo usa: 318 minutos y 2.75 casos por persona", str(despues)[:300])
    faltante = http.put("/configuracion/capacidad", json={"tenant": TENANT, "minutos_por_visita": 60})
    comprobar(faltante.status_code == 400, "si falta una clave se rechaza: 'no vino' no es 'borralo'")
    sigue = http.get(f"/reportes/capacidad?tenant={TENANT}&dias=30").get_json() or {}
    comprobar((sigue.get("declarado") or {}).get("minutos_por_conversacion") == 12,
              "y lo declarado sigue intacto")
    malo = http.put("/configuracion/capacidad", json={"tenant": TENANT, "minutos_por_conversacion": -5,
                                                      "minutos_por_visita": None, "personas_del_equipo": None})
    comprobar(malo.status_code == 400, "un numero negativo lo rechaza el esquema")
    nulo = http.put("/configuracion/capacidad", json={"tenant": TENANT, "minutos_por_conversacion": None,
                                                      "minutos_por_visita": None, "personas_del_equipo": None})
    fila = q("select config->'capacidad' from asistente.tenant_config where organization_id = %s", (org,))[0][0]
    #  El editor reescribe el modelo entero (D7), asi que la clave queda en null
    #  y no ausente: se afirma sobre el VALOR.
    comprobar(nulo.status_code == 200 and (fila or {}).get("minutos_por_conversacion") is None
              and (fila or {}).get("acciones_que_evitan_visita") == ["reiniciar_ont"],
              "null borra lo declarado y deja intacto lo demas de 'capacidad'", str(fila))

    # ==================================================================
    print("\n== D. la tasa de escalada vieja deja de contar el simulador ==")
    esc = db.tasa_escalamiento(TENANT, 7)
    reales = q("""select count(*) from asistente.conversations
                  where organization_id = %s and canal = 'whatsapp'
                    and creado_en >= now() - interval '7 days'""", (org,))[0][0]
    comprobar(esc["total"] == reales,
              f"total = conversaciones de canal real de 7 dias ({esc['total']} vs {reales})")

finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f"drop database if exists {BASE} with (force)")
    except Exception as e:                                           # noqa: BLE001
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El tablero de capacidad mide lo que dice que mide.")
