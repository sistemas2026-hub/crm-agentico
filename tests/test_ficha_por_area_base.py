# -*- coding: utf-8 -*-
"""
================================================================================
 LA FICHA DEL CLIENTE SEGUN QUIEN MIRA  --  contra PostgreSQL, por la ruta real
================================================================================

    DBHOST=127.0.0.1 DBPORT=55547 DBUSER=postgres DBPASSWORD=... \\
        py -3.13 tests/test_ficha_por_area_base.py

12/11/2026. Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni
la de produccion. Lo unico sustituido es la llamada al sistema del ISP (no hay
red) y '_config_de' (una configuracion con dos areas inventadas). La
conversacion, la identidad del cliente y el area de cada persona salen de
PostgreSQL por las funciones REALES, con RLS forzada: el area de quien mira no
la manda quien llama, la lee el motor.

  A. un colaborador de un area que no declara la cedula no la recibe;
  B. gestion la recibe, y un area que la declara tambien;
  C. el area irresoluble (perfil sin fila, fila de otra empresa, area que la
     configuracion ya no tiene) cae al defecto, nunca a "todo";
  D. la respuesta mantiene la forma que la Bandeja lee.
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
BASE = "ficha_area_" + uuid.uuid4().hex[:6]
TENANT, OTRO = "empresa_prueba", "otra_empresa"
P_SIN, P_CON, P_FANTASMA, P_OTRA, P_NADIE = (str(uuid.uuid4()) for _ in range(5))
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


FILA_ISP = {"id_servicio": 5832, "nombre": "TITULAR PRUEBA", "cedula": "1234567890",
            "estado": "Activo", "telefono": "3001112233", "email": "x@y.z",
            "direccion": "CALLE 1 # 2-3", "plan_internet": {"id": 7, "nombre": "PLAN 100"},
            "saldo": "0.00", "fecha_corte": "2026-12-05", "coordenadas": "4.1,-74.1"}

print("=" * 74)
print(" LA FICHA DEL CLIENTE SEGUN QUIEN MIRA  --  contra PostgreSQL")
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
    fila_minima("organization", {"id": org, "name": "Org ficha"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, OTRO))
    os.environ["DBNAME"] = BASE

    from nucleo.canales import api                                 # noqa: E402
    from nucleo.config import cargar_config, editor                # noqa: E402
    from nucleo.persistencia import db                             # noqa: E402

    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    doc = cargar_config(yamls[0]).model_dump(mode="json")
    doc["areas"] = list(doc.get("areas") or []) + [
        {"nombre": "area_sin_cedula", "etiqueta": "A", "agentes": [],
         "ficha_cliente": ["nombre", "estado", "plan_internet", "telefono"]},
        {"nombre": "area_con_cedula", "etiqueta": "B", "agentes": [],
         "ficha_cliente": ["nombre", "cedula"]},
    ]
    CONFIG = editor._validar(TENANT, doc)
    api._config_de = lambda tenant: CONFIG
    api.ejecutor_http.ejecutar = (lambda h, args, tenant=None, variables_tenant=None:
                                  {"results": [dict(FILA_ISP)]} if str(args.get("id_servicio")) == "5832"
                                  else {"results": []})

    # El area de cada persona, por la funcion REAL de escritura.
    db.guardar_area_colaborador(TENANT, P_SIN, "area_sin_cedula")
    db.guardar_area_colaborador(TENANT, P_CON, "area_con_cedula")
    db.guardar_area_colaborador(TENANT, P_FANTASMA, "area_que_ya_no_existe")
    # La misma persona-clave en OTRA empresa con un area que da la cedula: no
    # puede filtrarse a esta (RLS).
    db.guardar_area_colaborador(OTRO, P_OTRA, "area_con_cedula")
    comprobar(db.areas_de_colaboradores(TENANT).get(P_SIN) == "area_sin_cedula",
              "el area se guarda y se lee por la base real")

    cid = str(q("""insert into asistente.conversations
                     (organization_id, canal, usuario_externo, estado, id_cliente)
                   values (%s, 'whatsapp', '573009998877', 'abierta', '5832') returning id""",
                (org,))[0][0])
    cliente = api.app.test_client()

    def ficha(rol=None, perfil=None):
        url = f"/conversaciones/{cid}/cliente?tenant={TENANT}"
        url += f"&rol={rol}" if rol else ""
        url += f"&perfil={perfil}" if perfil else ""
        resp = cliente.get(url)
        return resp.status_code, resp.get_json()

    print("\n== A. el area sin cedula ==")
    s, d = ficha("USER", P_SIN)
    comprobar(s == 200 and d["disponible"] and "cedula" not in d["cliente"],
              "un colaborador de un area sin cedula NO la recibe", str(d))
    comprobar(d["cliente"].get("telefono") == "3001112233" and "direccion" not in d["cliente"],
              "recibe lo que su area declara y nada mas")
    comprobar("cedula" in d["cliente"]["_ocultos"], "y la ficha dice que esta oculta")

    print("\n== B. gestion y el area que la declara ==")
    for rol in ("ADMIN", "SUPERVISOR", "OPERACIONES"):
        s, d = ficha(rol, P_SIN)
        comprobar(d["cliente"].get("cedula") == "1234567890" and d["cliente"]["_ocultos"] == [],
                  f"{rol} recibe la cedula aunque su area no la declare")
    s, d = ficha("USER", P_CON)
    comprobar(d["cliente"].get("cedula") == "1234567890", "un area que declara la cedula la recibe")

    print("\n== C. el area irresoluble ==")
    for perfil, que in ((P_NADIE, "perfil sin fila"), (P_OTRA, "fila de OTRA empresa (RLS)"),
                        (P_FANTASMA, "area que la configuracion ya no tiene"), (None, "sin perfil")):
        s, d = ficha("USER", perfil)
        comprobar(s == 200 and "cedula" not in d["cliente"] and "email" not in d["cliente"]
                  and "coordenadas" not in d["cliente"] and d["cliente"].get("telefono"),
                  f"{que}: defecto seguro (sin cedula, correo ni coordenadas)", str(d))

    print("\n== D. la forma que lee la Bandeja ==")
    s, d = ficha()
    comprobar(set(d) == {"disponible", "motivo", "cliente"} and d["disponible"] is True
              and d["cliente"].get("plan_internet") == "PLAN 100",
              "{disponible, motivo, cliente}; el plan anidado sigue llegando como nombre")
    v = cliente.get(f"/ficha-cliente/visibilidad?tenant={TENANT}&rol=USER&perfil={P_SIN}").get_json()
    comprobar(v["criterio"] == "area" and "cedula" in v["ocultos"],
              "la visibilidad del ticket lee la misma area de la base")
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
print("[OK] contra PostgreSQL, la ficha se filtra por el area que lee el motor.")
