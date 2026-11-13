# -*- coding: utf-8 -*-
"""
================================================================================
 LA FICHA DEL CLIENTE POR SU SERVICIO, CONTRA POSTGRES REAL  --  12/11/2026
================================================================================

    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_ficha_cliente_por_servicio_base.py

Construye una base efimera desde cero (cli/base_desde_cero.py), siembra DOS
organizaciones y atraviesa la ruta GET /clientes/<id_servicio>/ficha hasta la
base, con el rol degradado y la RLS de verdad. Sin las variables se saltea con
exit 0.

Lo que se protege (auditoria del menu §4 item 5, ficha del cliente):

  - las conversaciones del cliente se encuentran SOLO por `id_cliente`: el
    mismo numero de telefono sin cliente verificado no entra;
  - una empresa no ve las conversaciones de otra con el mismo servicio;
  - solo metadatos: ni mensajes, ni el numero del canal, ni el nombre;
  - la ficha de la persona sale recortada (sin criterio por area cargado: sin
    cedula, telefono, direccion ni coordenadas), y la IP y el router nunca;
  - un servicio con caracteres raros se rechaza antes de tocar la base.
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
BASE = "ficha_" + uuid.uuid4().hex[:6]
TENANT_A, TENANT_B = "empresa_a", "empresa_b"
SERVICIO = "4986"

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
print(" LA FICHA DEL CLIENTE POR SU SERVICIO")
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

    def conv(tenant, tel, id_cliente=None, canal="whatsapp", hace_dias=0, estado="abierta"):
        return str(q("""insert into asistente.conversations
                          (organization_id, canal, usuario_externo, nombre_cliente,
                           id_cliente, estado, creado_en)
                        values (%s, %s, %s, %s, %s, %s, now() - make_interval(days => %s))
                        returning id""",
                     (orgs[tenant], canal, tel, "Ana Pérez", id_cliente, estado,
                      hace_dias))[0][0])

    vieja = conv(TENANT_A, "573001", SERVICIO, hace_dias=10, estado="cerrada")
    nueva = conv(TENANT_A, "573001", SERVICIO, hace_dias=1)
    conv(TENANT_A, "573001", None)                 # mismo numero, sin verificar
    conv(TENANT_A, "573009", "7777")               # otro cliente
    simulada = conv(TENANT_A, "sim-1", SERVICIO, canal="whatsapp-simulado")
    ajena = conv(TENANT_B, "573001", SERVICIO)     # otra empresa, mismo servicio

    print("\n-- persistencia: solo por id_cliente, solo de la empresa --")
    filas = db.conversaciones_de_cliente(TENANT_A, SERVICIO)
    ids = [str(f["id"]) for f in filas]
    comprobar(ids[:1] == [simulada] and set(ids) == {vieja, nueva, simulada},
              f"las tres de ese servicio, la mas nueva primero ({len(ids)})", str(ids))
    comprobar(ids.index(nueva) < ids.index(vieja), "orden por fecha de creacion, descendente")
    comprobar(ajena not in ids, "la de la otra empresa con el mismo servicio no entra")
    comprobar(not ({"usuario_externo", "nombre_cliente", "contenido", "datos_sesion"} & set(filas[0])),
              "solo metadatos: ni numero, ni nombre, ni mensajes", str(sorted(filas[0])))
    comprobar([str(f["id"]) for f in db.conversaciones_de_cliente(TENANT_B, SERVICIO)] == [ajena],
              "y la otra empresa ve solo la suya")
    q("""insert into asistente.conversations (organization_id, canal, usuario_externo, id_cliente)
         select %s, 'whatsapp', 'r' || g, %s from generate_series(1, 70) g""",
      (orgs[TENANT_A], "5555"))
    comprobar(len(db.conversaciones_de_cliente(TENANT_A, "5555", limite=500))
              == db.CONVERSACIONES_DE_CLIENTE_TOPE, "pedir mas no pasa el tope")

    print("\n-- la ruta: ficha recortada, IP y router nunca --")
    from nucleo.canales import api                                  # noqa: E402

    vistos = {}

    def contexto_falso(config, tenant, identidad):
        vistos["identidad"] = identidad
        return {"cliente": {"nombre": "Ana Pérez", "estado": "Activo", "plan": "ELITE",
                            "cedula": "1234567890", "telefono": "3001112222",
                            "direccion": "Calle 1", "coordenadas": "10.4,-75.5"},
                "ip": "10.0.0.9", "router": "http://10.0.0.9",
                "equipo": {"estado": "Online"}, "sn_onu": "ZTEG123",
                "identidad": {"servicio": SERVICIO, "origen": "case"}}

    api._config_de = lambda tenant: object()
    api.contexto_tecnico = contexto_falso
    with api.app.test_client() as c:
        r = c.get(f"/clientes/{SERVICIO}/ficha?tenant={TENANT_A}&rol=USER&perfil=p1")
        d = r.get_json() or {}
        comprobar(r.status_code == 200, f"responde 200 ({r.status_code})")
        comprobar([x["id"] for x in d.get("conversaciones") or []][:1] == [simulada]
                  and len(d["conversaciones"]) == 3, "trae las conversaciones del servicio")
        por_id = {x["id"]: x for x in d["conversaciones"]}
        comprobar(por_id[simulada]["canal_operativo"] is False
                  and por_id[nueva]["canal_operativo"] is True,
                  "y dice cual es de un canal real y cual de prueba")
        comprobar(vistos.get("identidad", {}).get("id_servicio") == SERVICIO,
                  "el contexto se arma con el servicio de la URL (misma funcion que el ticket)")
        ctx = d.get("contexto") or {}
        comprobar("ip" not in ctx and "router" not in ctx, "la IP y el router no salen")
        comprobar(ctx.get("equipo") == {"estado": "Online"}, "el estado del equipo si")
        texto = r.get_data(as_text=True)
        comprobar(all(x not in texto for x in ("1234567890", "3001112222", "Calle 1", "10.4,-75.5")),
                  "sin criterio por area cargado, la ficha no lleva datos personales")
        comprobar(ctx.get("cliente", {}).get("plan") == "ELITE", "lo que no es dato personal si")
        comprobar(c.get(f"/clientes/a%20b/ficha?tenant={TENANT_A}").status_code == 400,
                  "un servicio con espacios se rechaza")
        comprobar(c.get(f"/clientes/{SERVICIO}/ficha").status_code == 400, "sin tenant, 400")
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
