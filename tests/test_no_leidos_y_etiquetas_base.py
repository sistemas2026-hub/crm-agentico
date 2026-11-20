# -*- coding: utf-8 -*-
"""
================================================================================
 NO LEIDOS Y ETIQUETAS DEL EQUIPO  --  contra PostgreSQL, por las rutas reales
================================================================================

    DBHOST=127.0.0.1 DBPORT=55461 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_no_leidos_y_etiquetas_base.py

11/11/2026. Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni
la de produccion: las dos migraciones nuevas entran por el mismo camino que en
el despliegue. Lo que corre sin base (la suma por chat, el fail-closed de las
claves) esta en tests/test_no_leidos_y_etiquetas.py.

  A. LA MIGRACION. Una conversacion que ya existia nace LEIDA (si no, la cola
     entera amaneceria en negrita); una nueva cuenta todos los mensajes del
     cliente; la columna nueva es nullable y no tiene default.
  B. LA CUENTA (db.ultima_actividad). Solo mensajes del cliente posteriores a
     leida_hasta; una cerrada cuenta 0; marcar leida no mueve actualizado_en
     ni relevo_version.
  C. LA MARCA ES DEL CHAT. «Leida» marca la pedida y las otras ABIERTAS del
     mismo numero, no las de otro numero ni las de otra empresa. «No leida»
     vuelve a contar el ultimo mensaje del cliente, y sin ninguno no inventa.
     Y por la ruta: GET /conversaciones?por_numero=1 suma por chat.
  D. LAS ETIQUETAS SON DEL CHAT. Un cliente que vuelve (conversacion nueva del
     mismo numero) las conserva; otra empresa con el mismo numero no las ve;
     sin empresa fijada, app_backend ve cero filas (RLS forzada); quien y
     cuando quedan guardados.
================================================================================
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}: NO se comprobo nada contra la base.")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker (cli/base_desde_cero.py corre las migraciones de Django)")
    raise SystemExit(0)

from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)

import psycopg                                                      # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "noleidos_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"
ANA = ("7c9e6679-7425-40de-944b-e07fc1f90ae7", "Ana Perez")
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


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


def conv(org, numero, *, dias=1, canal="whatsapp", estado="abierta"):
    return str(q("""insert into asistente.conversations
                      (organization_id, canal, usuario_externo, estado, creado_en, actualizado_en)
                    values (%s, %s, %s, %s, now() - make_interval(days => %s),
                            now() - make_interval(days => %s)) returning id""",
                 (org, canal, numero, estado, dias, dias))[0][0])


def mensaje(org, cid, rol, *, minutos, origen=None):
    origen = origen or {"user": "cliente", "assistant": "ia"}.get(rol, "ia")
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         values (%s, %s, %s, 'x', %s, now() - make_interval(mins => %s))""",
      (org, cid, rol, origen, minutos))


def no_leidos(db, cid):
    return next((f["no_leidos"] for f in db.ultima_actividad(TENANT) if str(f["id"]) == cid), None)


print("=" * 74)
print(" NO LEIDOS Y ETIQUETAS DEL EQUIPO  --  contra PostgreSQL")
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
    fila_minima("organization", {"id": org, "name": "Org leidos"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE
    from nucleo.canales import api                                 # noqa: E402
    from nucleo.config import cargar_config, editor                # noqa: E402
    from nucleo.persistencia import db                             # noqa: E402

    # ======================================================================
    print("\n== A. la migracion ==")
    col = q("""select is_nullable, column_default from information_schema.columns
               where table_schema = 'asistente' and table_name = 'conversations'
                 and column_name = 'leida_hasta'""")
    comprobar(col == [("YES", None)], f"leida_hasta existe, nullable y sin default ({col})")
    rls = q("""select relrowsecurity, relforcerowsecurity from pg_class
               where oid = 'asistente.etiquetas_de_chat'::regclass""")
    comprobar(rls == [(True, True)], f"etiquetas_de_chat con RLS habilitada y FORZADA ({rls})")
    ledger = q("""select archivo, origen from asistente.migraciones_aplicadas
                  where archivo in ('202611111200_conversaciones_leida_hasta.sql',
                                    '202611111201_etiquetas_de_chat.sql') order by archivo""")
    comprobar([o for _, o in ledger] == ["aplicada", "aplicada"],
              f"las dos entraron por el ledger, en orden ({ledger})")

    # Una conversacion "de antes": se simula volviendo leida_hasta a NULL y
    # corriendo el SQL de la migracion, que es idempotente (add column if not
    # exists + update where null). Asi se mide lo que hace sobre filas viejas.
    vieja = conv(org, "573100000001", dias=3)
    for m in (300, 200, 100):
        mensaje(org, vieja, "user", minutos=m)
    q("update asistente.conversations set leida_hasta = null where id = %s", (vieja,))
    comprobar(no_leidos(db, vieja) == 3, "sin marca (NULL) cuentan todos los mensajes del cliente")
    sql = (RAIZ / "supabase" / "202611111200_conversaciones_leida_hasta.sql").read_text(encoding="utf-8")
    with psycopg.connect(dsn(BASE)) as con:
        con.execute(sql)
    comprobar(no_leidos(db, vieja) == 0,
              "la migracion deja las existentes LEIDAS: la cola no amanece en negrita")
    nueva = conv(org, "573100000002")
    mensaje(org, nueva, "user", minutos=5)
    mensaje(org, nueva, "assistant", minutos=4)
    mensaje(org, nueva, "user", minutos=3)
    comprobar(no_leidos(db, nueva) == 2,
              "una conversacion nueva cuenta los mensajes del CLIENTE, no los del asistente")

    # ======================================================================
    print("\n== B. la cuenta y lo que NO toca ==")
    antes = q("select actualizado_en, relevo_version from asistente.conversations where id = %s", (nueva,))[0]
    rl = db.marcar_leida(TENANT, nueva, True)
    comprobar(rl and rl["aplicada"] and no_leidos(db, nueva) == 0, "marcar leida deja 0")
    despues = q("select actualizado_en, relevo_version from asistente.conversations where id = %s", (nueva,))[0]
    comprobar(antes == despues, "leer no mueve actualizado_en (la cola ordena por ahi) ni relevo_version",
              f"{antes} -> {despues}")
    mensaje(org, nueva, "user", minutos=0)
    comprobar(no_leidos(db, nueva) == 1, "lo que escribe despues el cliente vuelve a contar")
    cerrada = conv(org, "573100000003", estado="cerrada")
    mensaje(org, cerrada, "user", minutos=1)
    comprobar(no_leidos(db, cerrada) == 0, "una cerrada cuenta 0 aunque tenga mensajes sin leer")

    # LA CARRERA DEL TURNO (11/11/2026, auditoria H3). El mensaje del cliente se
    # guarda DESPUES del turno con creado_en = cuando LLEGO. Si alguien abrio el
    # chat mientras el modelo pensaba, leida_hasta quedaba POSTERIOR al mensaje
    # y este nacia «leido» sin que nadie lo hubiera visto. Por la funcion REAL
    # (db.registrar_mensaje), con el mismo orden que api.atender_turno.
    print("\n== B2. un mensaje del cliente que llega durante el turno no nace leido ==")
    from datetime import datetime, timedelta, timezone             # noqa: E402
    NC = "573100000020"
    carrera, _ = db.registrar_mensaje(TENANT, "whatsapp", NC, "cliente_final", "user", "hola",
                                      creado_en=datetime.now(timezone.utc) - timedelta(minutes=10),
                                      origen="cliente")
    llego_en = datetime.now(timezone.utc) - timedelta(seconds=5)   # llega el mensaje, empieza el turno
    db.marcar_leida(TENANT, carrera, True)                          # alguien abre el chat mientras tanto
    comprobar(no_leidos(db, carrera) == 0, "abrir el chat deja 0")
    version = q("select relevo_version from asistente.conversations where id = %s", (carrera,))[0][0]
    cid, _ = db.registrar_mensaje(TENANT, "whatsapp", NC, "cliente_final", "user", "sigo sin internet",
                                  creado_en=llego_en, origen="cliente")
    comprobar(cid == carrera, "el mensaje cae en la misma conversacion")
    comprobar(no_leidos(db, carrera) == 1,
              f"EL EFECTO: el mensaje guardado despues del turno CUENTA como no leido ({no_leidos(db, carrera)})")
    marca = q("select leida_hasta, relevo_version from asistente.conversations where id = %s", (carrera,))[0]
    comprobar(marca[0] == llego_en - timedelta(milliseconds=1) and marca[1] == version,
              "la marca queda justo antes del mensaje, sin mover relevo_version", f"{marca} / {llego_en}")
    db.registrar_mensaje(TENANT, "whatsapp", NC, "cliente_final", "assistant", "ya reviso",
                         creado_en=llego_en - timedelta(seconds=1), origen="ia")
    comprobar(q("select leida_hasta from asistente.conversations where id = %s", (carrera,))[0][0]
              == llego_en - timedelta(milliseconds=1),
              "una respuesta del asistente no toca la marca")
    db.marcar_leida(TENANT, carrera, True)
    leida = q("select leida_hasta from asistente.conversations where id = %s", (carrera,))[0][0]
    db.registrar_mensaje(TENANT, "whatsapp", NC, "cliente_final", "user", "gracias", origen="cliente")
    comprobar(q("select leida_hasta from asistente.conversations where id = %s", (carrera,))[0][0] == leida
              and no_leidos(db, carrera) == 1,
              "sin carrera (el mensaje es posterior a la marca) la marca no se mueve y cuenta igual")

    # ======================================================================
    print("\n== C. la marca es del chat ==")
    N = "573100000010"
    a = conv(org, N, dias=3)
    b = conv(org, N, dias=1)
    c_cerrada = conv(org, N, dias=5, estado="cerrada")
    ajena = conv(otra, N, dias=1)
    otro_numero = conv(org, "573100000011")
    for cid, o in ((a, org), (b, org), (c_cerrada, org), (ajena, otra), (otro_numero, org)):
        mensaje(o, cid, "user", minutos=10)
    q("update asistente.conversations set leida_hasta = null where id = any(%s::uuid[])",
      ([a, b, c_cerrada, ajena, otro_numero],))
    mensaje(org, a, "user", minutos=2)          # el ultimo del chat cae en 'a'

    http = api.app.test_client()
    api._TOKEN_SERVICIO = None
    cuerpo = http.get(f"/conversaciones?tenant={TENANT}&por_numero=1").get_json()
    chat = next((f for f in cuerpo["conversaciones"] if f.get("usuario_externo") == N and f["canal_operativo"]), {})
    comprobar(chat.get("no_leidos") == 3,
              f"por la ruta, el chat suma sus abiertas (a: 2 + b: 1 = 3), sin la cerrada ({chat.get('no_leidos')})")

    r = http.post(f"/conversaciones/{b}/leida", json={"tenant": TENANT, "leida": True})
    comprobar(r.status_code == 200 and sorted(r.get_json()["conversaciones"]) == sorted([a, b]),
              "«leida» desde una marca las DOS abiertas del chat", str(r.get_json()))
    comprobar(no_leidos(db, a) == 0 and no_leidos(db, b) == 0, "y el chat queda en 0")
    marca = dict(q("select id::text, leida_hasta from asistente.conversations where id = any(%s::uuid[])",
                   ([c_cerrada, ajena, otro_numero],)))
    comprobar(all(v is None for v in marca.values()),
              "no toca la cerrada del chat, ni el mismo numero en OTRA empresa, ni otro numero")

    r = http.post(f"/conversaciones/{b}/leida", json={"tenant": TENANT, "leida": False})
    comprobar(r.status_code == 200 and r.get_json()["conversaciones"] == [a],
              "«no leida» vuelve a contar en la abierta donde cayo el ultimo mensaje del cliente",
              str(r.get_json()))
    comprobar(no_leidos(db, a) == 1 and no_leidos(db, b) == 0,
              "exactamente ese mensaje: el chat vuelve a negrita con 1")

    t21 = conv(org, "573100000012")
    mensaje(org, t21, "assistant", minutos=1, origen="humano")
    r = http.post(f"/conversaciones/{t21}/leida", json={"tenant": TENANT, "leida": False})
    comprobar(r.status_code == 409 and r.get_json().get("codigo") == "sin_mensajes_del_cliente",
              "sin ningun mensaje del cliente, «no leida» no inventa uno (409)")

    r = http.post(f"/conversaciones/{ajena}/leida", json={"tenant": TENANT, "leida": True})
    comprobar(r.status_code == 404 and q("select leida_hasta from asistente.conversations where id = %s",
                                         (ajena,))[0][0] is None,
              "una conversacion de otra empresa es 404 y no se toca")

    # ======================================================================
    print("\n== D. las etiquetas son del chat ==")
    doc = cargar_config(next(p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
                             if not p.name.startswith("tenant.config.example"))).model_dump(mode="json")
    doc["conversaciones"]["etiquetas_del_equipo"] = [
        {"clave": "vip", "nombre": "Cliente VIP", "color": "violeta"},
        {"clave": "moroso", "nombre": "Moroso", "color": "rojo"}]
    cfg = editor._validar(TENANT, doc)
    api._config_de = lambda tenant: cfg

    r = http.put(f"/conversaciones/{a}/etiquetas",
                 json={"tenant": TENANT, "etiquetas": ["moroso", "vip"],
                       "autor": ANA[1], "autor_usuario_id": ANA[0]})
    comprobar(r.status_code == 200 and r.get_json()["etiquetas"] == ["vip", "moroso"],
              "se guardan en el orden del catalogo", str(r.get_json()))
    guardada = q("""select claves, cambiada_por_usuario_id::text, cambiada_por_nombre, cambiada_en is not null
                    from asistente.etiquetas_de_chat where organization_id = %s and usuario_externo = %s""",
                 (org, N))
    comprobar(guardada == [(["vip", "moroso"], ANA[0], ANA[1], True)],
              "una fila por chat, con quien y cuando", str(guardada))

    vuelve = conv(org, N, dias=0)
    mensaje(org, vuelve, "user", minutos=0)
    filas = {str(f["id"]): f for f in db.ultima_actividad(TENANT)}
    comprobar(filas[vuelve]["etiquetas_del_equipo"] == ["vip", "moroso"]
              and filas[c_cerrada]["etiquetas_del_equipo"] == ["vip", "moroso"],
              "una conversacion NUEVA del mismo numero (y la cerrada) traen las del chat")
    comprobar(db.mensajes_de(TENANT, vuelve)["conversacion"]["etiquetas_del_equipo"] == ["vip", "moroso"],
              "y el encabezado de la conversacion tambien")
    comprobar(filas[otro_numero]["etiquetas_del_equipo"] == [], "otro numero no las tiene")
    ajenas = [f for f in db.ultima_actividad("otra_empresa") if str(f["id"]) == ajena]
    comprobar(ajenas and ajenas[0]["etiquetas_del_equipo"] == [],
              "el mismo numero en OTRA empresa no las ve")

    r = http.put(f"/conversaciones/{vuelve}/etiquetas",
                 json={"tenant": TENANT, "etiquetas": ["vip", "no_existe"],
                       "autor": ANA[1], "autor_usuario_id": ANA[0]})
    comprobar(r.status_code == 400 and q("select claves from asistente.etiquetas_de_chat "
                                         "where organization_id = %s and usuario_externo = %s",
                                         (org, N))[0][0] == ["vip", "moroso"],
              "una clave fuera del catalogo: 400 y la fila queda como estaba")

    # Borrar una del catalogo no la borra de la tabla: deja de mostrarse.
    doc["conversaciones"]["etiquetas_del_equipo"] = [{"clave": "vip", "nombre": "Cliente VIP",
                                                      "color": "violeta"}]
    cfg_sin = editor._validar(TENANT, doc)
    api._config_de = lambda tenant: cfg_sin
    cuerpo = http.get(f"/conversaciones?tenant={TENANT}&por_numero=1").get_json()
    chat = next((f for f in cuerpo["conversaciones"] if f.get("usuario_externo") == N and f["canal_operativo"]), {})
    comprobar(chat.get("etiquetas_del_equipo") == ["vip"]
              and q("select claves from asistente.etiquetas_de_chat where organization_id = %s "
                    "and usuario_externo = %s", (org, N))[0][0] == ["vip", "moroso"],
              "una borrada del catalogo no se muestra, pero queda en la tabla", str(chat.get("etiquetas_del_equipo")))
    api._config_de = lambda tenant: cfg

    # RLS: app_backend sin empresa fijada ve CERO filas, no todas.
    with psycopg.connect(dsn(BASE)) as con:
        con.execute("set local role app_backend")
        n = con.execute("select count(*) from asistente.etiquetas_de_chat").fetchone()[0]
    comprobar(n == 0, f"app_backend sin empresa fijada ve 0 etiquetas ({n})")
    with psycopg.connect(dsn(BASE)) as con:
        con.execute("set local role app_backend")
        con.execute("select set_config('app.current_tenant', %s, true)", (otra,))
        n_otra = con.execute("select count(*) from asistente.etiquetas_de_chat").fetchone()[0]
        try:
            con.execute("""insert into asistente.etiquetas_de_chat (organization_id, canal, usuario_externo)
                           values (%s, 'whatsapp', '573100009999')""", (org,))
            cruzo = True
        except psycopg.errors.InsufficientPrivilege:
            # 42501 "new row violates row-level security policy": la politica,
            # no cualquier otro error, es la que lo frena.
            cruzo = False
    comprobar(n_otra == 0 and not cruzo,
              f"con OTRA empresa fijada no ve las de esta ni puede escribirle una ({n_otra}, {cruzo})")

    sin_numero = str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                          values (%s, 'whatsapp', '') returning id""", (org,))[0][0])
    r = http.put(f"/conversaciones/{sin_numero}/etiquetas",
                 json={"tenant": TENANT, "etiquetas": ["vip"], "autor": ANA[1], "autor_usuario_id": ANA[0]})
    comprobar(r.status_code == 409 and not q("select 1 from asistente.etiquetas_de_chat where usuario_externo = ''"),
              "una conversacion sin numero no se etiqueta (409) y no queda una fila con clave vacia")
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:                                           # noqa: BLE001
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Los no leidos se cuentan por chat desde una marca compartida, y las etiquetas siguen al numero.")
