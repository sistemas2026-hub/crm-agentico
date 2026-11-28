# -*- coding: utf-8 -*-
"""
================================================================================
 BUSCAR EN EL CONTENIDO DE LOS MENSAJES, CONTRA POSTGRES REAL
================================================================================

    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_busqueda_mensajes_base.py

Construye una base efimera desde cero (cli/base_desde_cero.py, el mismo ledger
que produccion), siembra DOS organizaciones y corre db.buscar_en_mensajes con
el rol degradado y la RLS de verdad. Sin las variables se saltea con exit 0 --
y eso ya escondio regresiones: correrla con base.

POR QUE EXISTE  (11/11/2026)
----------------------------
El buscador de la Bandeja pasa a mirar el contenido de TODOS los mensajes. Lo
que se protege:

  - que encuentre lo escrito, sin importar mayusculas;
  - que '%' y '_' se busquen LITERALES: sin escape, «50%» encontraria
    cualquier mensaje con un 50, y «a_b» cualquier «axb»;
  - que una empresa no vea los mensajes de otra -- con la RLS y el filtro
    explicito, buscar lo mismo desde la otra devuelve 0;
  - el tope de 30, los mas recientes primero;
  - que las notas internas lleguen marcadas, y que un rol que el hilo no
    muestra no aparezca.

Y MIDE cuanto tarda sobre un volumen sembrado (ILIKE sin indice: recorre los
mensajes de la empresa). El numero se imprime: es el que decide si hace falta
un indice de trigramas, que pide una extension y es otra decision.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import sys
import time
import uuid
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
BASE = "busq_" + uuid.uuid4().hex[:6]
TENANT_A, TENANT_B = "empresa_a", "empresa_b"
#: Cuantos mensajes de relleno se siembran para medir. Del orden de un ISP con
#: un año de conversaciones; el numero real de la empresa se mide aparte.
VOLUMEN = int(os.environ.get("BUSQUEDA_VOLUMEN", "200000"))

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


print("=" * 74)
print(" BUSCAR EN EL CONTENIDO DE LOS MENSAJES")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    orgs = {}
    for t in (TENANT_A, TENANT_B):
        orgs[t] = str(uuid.uuid4())
        fila_minima("organization", {"id": orgs[t], "name": f"Org {t}"})
        q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (orgs[t], t))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402

    def conv(tenant, tel, nombre=None, estado="abierta", canal="whatsapp"):
        return str(q("""insert into asistente.conversations
                          (organization_id, canal, usuario_externo, nombre_cliente, estado)
                        values (%s, %s, %s, %s, %s) returning id""",
                     (orgs[tenant], canal, tel, nombre, estado))[0][0])

    def msj(tenant, c, contenido, rol="user", hace_min=0):
        origen = {"user": "cliente", "assistant": "ia", "nota": "humano"}.get(rol)
        return str(q("""insert into asistente.messages
                          (organization_id, conversation_id, rol, contenido, origen, creado_en)
                        values (%s, %s, %s, %s, %s, now() - make_interval(mins => %s))
                        returning id""",
                     (orgs[tenant], c, rol, contenido, origen, hace_min))[0][0])

    ana = conv(TENANT_A, "573001", "Ana Pérez")
    beto = conv(TENANT_A, "573002", None, estado="cerrada")
    m_poste = msj(TENANT_A, ana, "Buenas, el POSTE CAÍDO frente a mi casa dejó todo sin señal", hace_min=5)
    msj(TENANT_A, ana, "Gracias por avisar, ya lo reportamos", rol="assistant", hace_min=4)
    m_nota = msj(TENANT_A, beto, "Nota: revisar el poste caído de la calle 8", rol="nota", hace_min=3)
    m_pct = msj(TENANT_A, beto, "Me cobraron el 50% de recargo", hace_min=2)
    msj(TENANT_A, beto, "Me cobraron el 5000 de recargo", hace_min=2)
    m_guion = msj(TENANT_A, beto, "mi usuario es ana_b en la app", hace_min=1)
    msj(TENANT_A, beto, "mi usuario es anaxb en la app", hace_min=1)
    msj(TENANT_A, beto, "poste caído -- resultado de herramienta", rol="tool", hace_min=0)
    largo = ("Antes de esto hablamos mucho del plan y la factura del mes pasado. " * 4
             + "Y lo importante: la ONU parpadea en rojo desde ayer. "
             + "Despues seguimos con otras cosas que no vienen al caso. " * 4)
    m_largo = msj(TENANT_A, ana, largo, hace_min=6)
    # La OTRA empresa escribio lo mismo.
    otra = conv(TENANT_B, "573001", "Ana de la otra")
    msj(TENANT_B, otra, "el poste caído frente a mi casa", hace_min=1)

    print("\n-- coincidencia --")
    res = db.buscar_en_mensajes(TENANT_A, "poste caído")
    ids = [str(x["mensaje_id"]) for x in res]
    comprobar(ids == [m_nota, m_poste],
              f"encuentra las dos, la mas reciente primero, sin importar mayusculas ({len(ids)})")
    comprobar(res[0]["es_nota"] is True and res[0]["rol"] == "nota", "la nota llega marcada")
    comprobar(res[1]["es_nota"] is False and str(res[1]["conversation_id"]) == ana,
              "el mensaje del cliente dice de que conversacion es")
    comprobar(res[1]["nombre_cliente"] == "Ana Pérez" and res[1]["usuario_externo"] == "573001"
              and res[1]["estado"] == "abierta",
              "con la identidad visible y el estado de su conversacion")
    comprobar("contenido" not in res[0], "el mensaje entero no viaja: solo el fragmento")
    comprobar(all("herramienta" not in x["fragmento"] for x in res),
              "un rol que el hilo no muestra ('tool') no aparece")

    r_largo = db.buscar_en_mensajes(TENANT_A, "onu parpadea")
    frag = r_largo[0]["fragmento"] if r_largo else ""
    comprobar(r_largo and str(r_largo[0]["mensaje_id"]) == m_largo and "ONU parpadea" in frag,
              "en un mensaje largo, el fragmento contiene la coincidencia", frag)
    comprobar(frag.startswith("…") and frag.endswith("…") and len(frag) <= db.FRAGMENTO_LARGO + 2,
              f"y es un recorte de ~{db.FRAGMENTO_LARGO} con «…» donde se corto ({len(frag)})", frag)

    print("\n-- escape de comodines --")
    r = db.buscar_en_mensajes(TENANT_A, "50%")
    comprobar([str(x["mensaje_id"]) for x in r] == [m_pct],
              f"'50%' encuentra el 50% y no el 5000 ({len(r)})")
    r = db.buscar_en_mensajes(TENANT_A, "ana_b")
    comprobar([str(x["mensaje_id"]) for x in r] == [m_guion],
              f"'ana_b' encuentra ana_b y no anaxb ({len(r)})")
    comprobar(db.buscar_en_mensajes(TENANT_A, "\\%") == [],
              "una barra invertida tampoco es un escape abierto")

    print("\n-- aislamiento entre empresas --")
    rb = db.buscar_en_mensajes(TENANT_B, "poste caído")
    comprobar(len(rb) == 1 and str(rb[0]["conversation_id"]) == otra,
              "la otra empresa encuentra SOLO lo suyo")
    comprobar(db.buscar_en_mensajes(TENANT_B, "50%") == [] and db.buscar_en_mensajes(TENANT_B, "ONU") == [],
              "y lo que solo escribio la primera le devuelve 0")
    comprobar(db.buscar_en_mensajes(TENANT_A, "Ana de la otra") == []
              and db.buscar_en_mensajes(TENANT_A, "frente a mi casa") != []
              and all(str(x["conversation_id"]) != otra
                      for x in db.buscar_en_mensajes(TENANT_A, "frente a mi casa")),
              "y al reves: la primera no ve ninguna fila de la segunda")

    # La cita de una REACCION (11/11/2026, revisor de PII H2): el mensaje al
    # que reacciono el cliente se busca SOLO en su propio chat. Va aca porque
    # esta base ya tiene dos empresas y dos chats de la misma; armar otra
    # efimera para tres consultas costaria un ledger entero.
    print("\n-- la cita de una reaccion, solo del propio chat --")
    m_bot = msj(TENANT_A, ana, "¿Te registro la solicitud?", rol="assistant", hace_min=0)
    q("update asistente.messages set wamid = 'wamid.ANA' where id = %s", (m_bot,))
    comprobar(db.contenido_de_wamid(TENANT_A, "wamid.ANA", "whatsapp", "573001")
              == "¿Te registro la solicitud?",
              "desde el chat de Ana, la cita aparece")
    comprobar(db.contenido_de_wamid(TENANT_A, "wamid.ANA", "whatsapp", "573002") is None,
              "desde OTRO chat de la misma empresa, no")
    comprobar(db.contenido_de_wamid(TENANT_B, "wamid.ANA", "whatsapp", "573001") is None,
              "desde la otra empresa con el mismo numero, tampoco")
    comprobar(db.contenido_de_wamid(TENANT_A, "wamid.ANA", "web", "573001") is None,
              "ni con el mismo numero en otro canal")
    comprobar(db.contenido_de_wamid(TENANT_A, None, "whatsapp", "573001") is None
              and db.contenido_de_wamid(TENANT_A, "wamid.ANA", "whatsapp", "") is None,
              "sin wamid o sin remitente no se busca nada")

    print("\n-- tope --")
    muchos = conv(TENANT_A, "573099", "Carla")
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         select %s, %s, 'user', 'repetido numero ' || g, 'cliente', now() - make_interval(secs => g)
         from generate_series(1, 45) g""", (orgs[TENANT_A], muchos))
    r = db.buscar_en_mensajes(TENANT_A, "repetido numero")
    comprobar(len(r) == 30, f"de 45 coincidencias devuelve 30 ({len(r)})")
    comprobar(r and r[0]["fragmento"] == "repetido numero 1" and r[-1]["fragmento"] == "repetido numero 30",
              "las 30 mas recientes, en orden")
    comprobar(len(db.buscar_en_mensajes(TENANT_A, "repetido numero", limite=500)) == 30,
              "y pedir mas no pasa el tope")

    # LA VISTA, ANTES DEL TOPE (11/11/2026, auditoria H2). La pantalla corta
    # por vista; hasta hoy lo hacia DESPUES de que la base cortara en 30, y
    # con 30 coincidencias del simulador mas recientes que la de un cliente
    # decia «Ningun mensaje contiene X» habiendo uno real.
    print("\n-- la vista de canales se aplica antes del tope --")
    simulada = conv(TENANT_A, "sim-1", "Prueba", canal="whatsapp-simulado")
    api_int = conv(TENANT_A, "bateria-1", None, canal="api")
    dora = conv(TENANT_A, "573777", "Dora")
    m_real = msj(TENANT_A, dora, "la fibra quedo colgando del arbol", hace_min=60)
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         select %s, case when g %% 2 = 0 then %s::uuid else %s::uuid end, 'user',
                'prueba ' || g || ': la fibra quedo colgando', 'cliente', now() - make_interval(secs => g)
         from generate_series(1, 40) g""", (orgs[TENANT_A], simulada, api_int))
    r_todos = db.buscar_en_mensajes(TENANT_A, "fibra quedo colgando", vista="todos")
    comprobar(len(r_todos) == 30 and m_real not in [str(x["mensaje_id"]) for x in r_todos],
              "con 'todos' los 30 mas recientes son de prueba (el escenario del defecto)")
    r_op = db.buscar_en_mensajes(TENANT_A, "fibra quedo colgando", vista="operativo")
    comprobar([str(x["mensaje_id"]) for x in r_op] == [m_real],
              f"EL EFECTO: con 'operativo' aparece el mensaje real ({len(r_op)})")
    r_pr = db.buscar_en_mensajes(TENANT_A, "fibra quedo colgando", vista="pruebas")
    comprobar(len(r_pr) == 30 and {str(x["conversation_id"]) for x in r_pr} == {simulada, api_int},
              f"con 'pruebas', 30 y solo de canales de prueba ({len(r_pr)})")
    comprobar(db.buscar_en_mensajes(TENANT_B, "fibra quedo colgando", vista="pruebas") == []
              and db.buscar_en_mensajes(TENANT_B, "fibra quedo colgando", vista="operativo") == [],
              "y la otra empresa no ve ninguna de las dos vistas")
    try:
        db.buscar_en_mensajes(TENANT_A, "fibra quedo colgando", vista="reales")
        comprobar(False, "una vista desconocida se rechaza")
    except ValueError:
        comprobar(True, "una vista desconocida se rechaza")

    print(f"\n-- cuanto tarda, con {VOLUMEN:,} mensajes sembrados en la empresa --".replace(",", "."))
    relleno = conv(TENANT_A, "573500", "Relleno")
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         select %s, %s, case when g %% 2 = 0 then 'user' else 'assistant' end,
                'Mensaje de relleno ' || g || ': el internet anda lento desde la mañana, '
                || 'ya reinicie el router y sigue igual, me pueden ayudar por favor',
                case when g %% 2 = 0 then 'cliente' else 'ia' end,
                now() - make_interval(mins => g)
         from generate_series(1, %s) g""", (orgs[TENANT_A], relleno, VOLUMEN))
    q("analyze asistente.messages")

    def medir(termino: str, veces: int = 5) -> tuple[float, int]:
        tiempos = []
        n = 0
        for _ in range(veces):
            t0 = time.perf_counter()
            n = len(db.buscar_en_mensajes(TENANT_A, termino))
            tiempos.append((time.perf_counter() - t0) * 1000)
        return statistics.median(tiempos), n

    # La linea de base: abrir la sesion (conexion, rol degradado, tenant) y
    # un 'select 1'. Cada busqueda la paga entera, como cualquier lectura de
    # este modulo; restarla es lo que dice cuanto cuesta la CONSULTA.
    base_ms = []
    for _ in range(5):
        t0 = time.perf_counter()
        with db.sesion(TENANT_A) as (cur, _org):
            cur.execute("select 1")
        base_ms.append((time.perf_counter() - t0) * 1000)
    print(f"  [medido] abrir la sesion + select 1: mediana {statistics.median(base_ms):.0f} ms de 5")
    for termino, que in (("onu parpadea", "rara (1 coincidencia, recorre todo)"),
                         ("internet anda lento", "frecuente (corta en 30)"),
                         ("no existe en ningun mensaje", "sin coincidencias (recorre todo)")):
        ms, n = medir(termino)
        print(f"  [medido] «{que}»: mediana {ms:.0f} ms de 5, {n} resultado(s)")
    # La vista por defecto de la Bandeja es 'operativo': el filtro por canal
    # entra al CTE, y su costo tambien se mide.
    tiempos_op = []
    for _ in range(5):
        t0 = time.perf_counter()
        db.buscar_en_mensajes(TENANT_A, "no existe en ningun mensaje", vista="operativo")
        tiempos_op.append((time.perf_counter() - t0) * 1000)
    print(f"  [medido] «sin coincidencias, vista operativo»: mediana {statistics.median(tiempos_op):.0f} ms de 5")
    # El plan, con el MISMO rol degradado y la RLS de la consulta real: como
    # superusuario la RLS no corre y el numero mentiria. Se afirma que los
    # mensajes se recorren UNA vez: el join directo los recorria una vez por
    # conversacion (4 x 256 ms el 11/11/2026). Con el filtro de la vista
    # 'operativo' (la de entrada de la Bandeja) adentro del CTE, que es el
    # caso mas caro.
    with db.sesion(TENANT_A) as (cur, org):
        cur.execute("""explain (analyze, buffers, format text)
                       with hallados as materialized (
                         select m.id, m.conversation_id, m.creado_en from asistente.messages m
                         where m.organization_id = %s and m.rol = any(%s)
                           and m.contenido ilike %s escape '\\'
                           and m.conversation_id = any(array(select cv.id from asistente.conversations cv
                                where cv.organization_id = %s and cv.canal = any(%s::text[])))
                         order by m.creado_en desc, m.id limit 30)
                       select h.id from hallados h
                       join asistente.conversations c
                         on c.id = h.conversation_id and c.organization_id = %s
                       order by h.creado_en desc, h.id""",
                    (org, list(db.ROLES_BUSCABLES), "%no existe en ningun mensaje%",
                     org, ["whatsapp"], org))
        plan = [list(f.values())[0] for f in cur.fetchall()]
    print("  [plan] " + "\n  [plan] ".join(plan))
    recorridos = [l for l in plan if "Scan on messages" in l]
    comprobar(len(recorridos) == 1 and "loops=1)" in recorridos[0],
              "los mensajes se recorren una sola vez, no una por conversacion", "\n".join(recorridos))
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:
        print(f"  [aviso] no se pudo borrar {BASE}: {type(e).__name__}")

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
