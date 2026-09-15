# -*- coding: utf-8 -*-
"""
================================================================================
 EL ARTEFACTO OFICIAL  --  el manifiesto versionado, contra la imagen de produccion
================================================================================

    py -3.13 tests/test_manifiesto_oficial_pg17.py

Por que existe
--------------
'supabase/ledger/manifiesto_adopcion.json' describe PRODUCCION: PostgreSQL
17.6, pgcrypto en 'extensions', ACL con MAINTAIN. Certificarlo contra el
PostgreSQL 16 de las suites rapidas seria comparar catalogos entre versiones
mayores, que es justo lo que la compuerta de huella impide. Por eso esta suite
levanta la IMAGEN EXACTA de produccion (por digest), una sola vez, y ahi:

  1. compuerta: 17.6/170006, pg_trgm 1.6 y vector 0.8.2 en public, pgcrypto 1.3
     en extensions, y el 'postgres' de la imagen sin superusuario
  2. prerrequisitos del entorno (crm_user, motor_user), sin secretos
  3. la referencia: los 43 de adopcion por el ledger, P2 fuera
  4. el hardening de public, FUERA del ledger, con los bytes exactos de 960408d
  5. regenerar con el generador real y exigir BYTE A BYTE:
         regenerado == supabase/ledger/manifiesto_adopcion.json
  6. lo que el artefacto declara: 43 archivos, 207 verificaciones, 36
     automaticas + 6 de datos + 1 humana, las mismas siete no automaticas, P2
     ausente, huella PG17 (no PG16)
  7. las capacidades nuevas del motor estan realmente usadas: acl_tablas,
     acl_secuencias, default_acl, la ACL de organization y los cinco
     comentarios canonicos
  8. SMOKE de adopcion real: sobre una copia de esa referencia sin ledger, el
     migrador adopta con ESE manifiesto -- 43 filas, 0 pendientes y ni un solo
     archivo historico re-ejecutado

Las suites rapidas de PG16 prueban el MECANISMO (adopcion, carreras, huecos,
evidencia, checksums, compuerta de huella) con un manifiesto de laboratorio;
ver tests/manifiesto_de_laboratorio.py.
================================================================================
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

IMG = "supabase/postgres@sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00"
COMMIT_HARDENING = "960408d"
HARDENING = (("postgres", "supabase/seguridad/revocar_data_api_postgres.sql"),
             ("supabase_admin", "supabase/seguridad/revocar_data_api_supabase_admin.sql"))
OFICIAL = RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json"
P2 = ("202609141200_scheduler_persistente.sql", "202609141300_scheduler_funciones.sql")
A1 = "202609141100_match_chunks_firma_5_obsoleta.sql"
ROLES_OP = "202609141110_roles_operativos_public.sql"
COMENTARIOS = "202609141120_comentarios_catalogo_canonicos.sql"
HUELLA = {"pg_trgm": ("1.6", "public"), "vector": ("0.8.2", "public"), "pgcrypto": ("1.3", "extensions")}
NO_AUTOMATICAS = {
    "202608042055_schema.sql": "requiere_revision_humana",
    "202608211448_diagnostico_recuperacion.sql": "migracion_de_datos_no_repetible",
    "202609061400_bloqueos_en_traza.sql": "migracion_de_datos_no_repetible",
    "202609061700_cola_priorizada.sql": "migracion_de_datos_no_repetible",
    "202609070900_bandeja_sin_inflar.sql": "migracion_de_datos_no_repetible",
    "202609071900_tomar_caso.sql": "migracion_de_datos_no_repetible",
    "202609080802_historial_de_config.sql": "migracion_de_datos_no_repetible",
}
MOTIVO = "referencia efimera de esta suite: se adopta para comprobar el artefacto, sin decision real"
AUTORIZA = "suite del artefacto oficial (base efimera)"

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 74}\n  {t}\n{'=' * 74}", flush=True)


if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402
from psycopg import sql                                           # noqa: E402

from cli import base_desde_cero as cero                           # noqa: E402

NOMBRE = f"dexter-manifiesto-oficial-{secrets.token_hex(3)}"
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PUERTO = str(s.getsockname()[1])
CLAVE = secrets.token_urlsafe(24)
TMP = Path(tempfile.mkdtemp(prefix="oficial-"))


def dsn(usuario, base="postgres"):
    return (f"host=127.0.0.1 port={PUERTO} dbname={base} user={usuario} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None, usuario="supabase_admin", base="postgres"):
    with psycopg.connect(dsn(usuario, base), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def entorno(base):
    e = {k: v for k, v in os.environ.items() if not k.startswith("MIGRAR_PRUEBA_")}
    e.pop("PGOPTIONS", None)
    e.update({"DBHOST": "127.0.0.1", "DBPORT": PUERTO, "DBNAME": base, "DBUSER": "postgres",
              "DBPASSWORD": CLAVE, "PYTHONUNBUFFERED": "1"})
    return e


def limpiar(t: str) -> str:
    return (t or "").replace(CLAVE, "<clave>")


def arrancar():
    subprocess.run(["docker", "rm", "-f", NOMBRE], capture_output=True)
    r = subprocess.run(["docker", "run", "-d", "--name", NOMBRE, "-e", "POSTGRES_PASSWORD",
                        "-p", f"127.0.0.1:{PUERTO}:5432", IMG],
                       capture_output=True, text=True, env={**os.environ, "POSTGRES_PASSWORD": CLAVE})
    if r.returncode != 0:
        raise RuntimeError(f"docker run: {r.stderr[-400:]}")
    limite = time.monotonic() + 900
    while time.monotonic() < limite:
        try:
            if q("select rolsuper from pg_roles where rolname = 'postgres'") == [(False,)]:
                time.sleep(3)
                q("select 1")
                return
        except psycopg.Error:
            pass
        time.sleep(2)
    raise RuntimeError("el servidor de la imagen no quedo listo")


def catalogo(base):
    """Todo el catalogo de 'asistente' y 'public' salvo el ledger, en un hash."""
    return q("""
        select md5(coalesce(string_agg(x, '|' order by x), '')) from (
          select 'rel:' || n.nspname || '.' || c.relname || ':' || c.relkind::text || ':' || coalesce(c.relacl::text, '') as x
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname in ('asistente', 'public') and c.relkind in ('r','v','m','p','S')
             and c.relname not like 'migraciones_%'
          union all
          select 'fun:' || n.nspname || '.' || p.proname || ':' || md5(pg_get_functiondef(p.oid))
            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'asistente' and p.prokind = 'f'
          union all
          select 'com:' || n.nspname || '.' || c.relname || ':' || coalesce(obj_description(c.oid, 'pg_class'), '')
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'asistente' and c.relkind = 'r'
        ) t""", usuario="postgres", base=base)[0][0]


def filas_ledger(base):
    return {a: o for a, o in q("select archivo, origen from asistente.migraciones_aplicadas",
                               usuario="postgres", base=base)}


try:
    titulo("1. la imagen exacta de produccion")
    arrancar()
    img = subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", NOMBRE],
                         capture_output=True, text=True).stdout.strip()
    revisar(img == IMG, "el contenedor corre la imagen fijada por digest", img)
    revisar(q("select current_setting('server_version_num')")[0][0] == "170006", "PostgreSQL 17.6 / 170006")
    revisar(q("select rolsuper, rolbypassrls, rolcreaterole from pg_roles where rolname='postgres'")[0]
            == (False, True, True), "'postgres': sin superusuario, con BYPASSRLS y CREATEROLE, como produccion")
    for ext, (version, esquema) in HUELLA.items():
        if not q("select 1 from pg_extension where extname = %s", (ext,)):
            q(f"create extension {ext} with schema {esquema} version '{version}'", usuario="postgres")
    exts = {n: (v, e) for n, v, e in q("select e.extname, e.extversion, n.nspname from pg_extension e "
                                       "join pg_namespace n on n.oid = e.extnamespace")}
    for ext, esperado in HUELLA.items():
        revisar(exts.get(ext) == esperado, f"huella: {ext} {esperado[0]} en {esperado[1]}", f"{exts.get(ext)}")

    titulo("2. prerrequisitos del entorno")
    with psycopg.connect(dsn("supabase_admin"), autocommit=True) as con:
        creados = cero.preparar_roles_de_despliegue(con)
    revisar(sorted(creados) == ["crm_user", "motor_user"],
            f"crm_user y motor_user preparados sin secretos; 'postgres' ya venia en la imagen: {sorted(creados)}")

    titulo("3. la referencia: los 43 de adopcion, P2 fuera")
    COPIA = TMP / "repo"
    (COPIA / "supabase").mkdir(parents=True)
    shutil.copytree(RAIZ / "cli", COPIA / "cli", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(RAIZ / "supabase" / "ledger", COPIA / "supabase" / "ledger")
    for p in sorted((RAIZ / "supabase").glob("*.sql")):
        if p.name not in P2:
            shutil.copy2(p, COPIA / "supabase" / p.name)
    nombres = sorted(p.name for p in (COPIA / "supabase").glob("*.sql"))
    oficial = json.loads(OFICIAL.read_bytes().decode("utf-8"))
    revisar(nombres == sorted(oficial["migraciones"]) and len(nombres) == 43,
            f"la carpeta tiene los mismos 43 archivos que el artefacto ({len(nombres)})",
            f"{set(nombres) ^ set(oficial['migraciones'])}")
    r = subprocess.run(cero.comando_django("postgres", "127.0.0.1", PUERTO, "postgres"),
                       capture_output=True, text=True, env=entorno("postgres"), timeout=1800)
    if not revisar(r.returncode == 0, "Django migra como postgres", limpiar(r.stderr)[-500:]):
        raise SystemExit(1)
    mig_py = COPIA / "cli" / "migrar_asistente.py"
    r = subprocess.run([sys.executable, str(mig_py), "--aplicar"], capture_output=True, text=True,
                       env=entorno("postgres"), timeout=1800)
    salida = limpiar((r.stdout or "") + (r.stderr or ""))
    if not revisar(r.returncode == 0 and "43 aplicada(s)" in salida, "el ledger aplica 43/43", salida[-600:]):
        raise SystemExit(1)
    revisar(sorted(filas_ledger("postgres")) == nombres and not [a for a in filas_ledger("postgres") if a in P2],
            "el ledger anota los 43 y P2 no aparece")

    titulo(f"4. el hardening de public, fuera del ledger (bytes exactos de {COMMIT_HARDENING})")
    for usuario, ruta in HARDENING:
        texto = subprocess.run(["git", "-C", str(RAIZ), "show", f"{COMMIT_HARDENING}:{ruta}"],
                               capture_output=True, text=True, encoding="utf-8").stdout
        with psycopg.connect(dsn(usuario), autocommit=True) as con:
            con.execute(texto)
        print(f"       aplicado {ruta.split('/')[-1]} como {usuario}")
    efectivos = q("""
        select r.rol, count(*) filter (where c.relkind in ('r','v','m','p','f')
                 and has_table_privilege(r.rol, c.oid, 'SELECT,INSERT,UPDATE,DELETE'))
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        cross join (values ('anon'), ('authenticated')) r(rol)
        where n.nspname = 'public' group by 1 order by 1""", usuario="postgres")
    revisar(all(n == 0 for _r, n in efectivos), f"anon y authenticated quedan sin acceso a public: {efectivos}")
    revisar(len(filas_ledger("postgres")) == 43, "y el ledger sigue en 43 filas: el hardening no entro a la cadena")

    titulo("5. regenerado == artefacto versionado, byte a byte")
    regenerado = TMP / "regenerado.json"
    r = subprocess.run([sys.executable, str(COPIA / "cli" / "manifiesto_adopcion.py"), "--generar",
                        "--salida", str(regenerado), "--descripcion", oficial["referencia"]["descripcion"]],
                       capture_output=True, text=True, env=entorno("postgres"), timeout=900)
    revisar(r.returncode == 0 and regenerado.exists(), "se regenera contra esta referencia",
            limpiar((r.stdout or "") + (r.stderr or ""))[-400:])
    iguales = regenerado.read_bytes() == OFICIAL.read_bytes()
    if not iguales:
        a, b = json.loads(regenerado.read_bytes().decode("utf-8")), oficial
        difs = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        dif_mig = sorted({m for m in set(a["migraciones"]) | set(b["migraciones"])
                          if a["migraciones"].get(m) != b["migraciones"].get(m)})[:6]
        porque = f"claves distintas: {difs}; migraciones distintas: {dif_mig}"
    else:
        porque = ""
    revisar(iguales, "el artefacto versionado sale EXACTAMENTE de esta referencia (bytes identicos)", porque)

    titulo("6. lo que declara el artefacto")
    verifs = sum(len(e["verificaciones"]) for e in oficial["migraciones"].values())
    estados: dict[str, int] = {}
    for e in oficial["migraciones"].values():
        estados[e["estado"]] = estados.get(e["estado"], 0) + 1
    revisar(len(oficial["migraciones"]) == 43, f"43 archivos ({len(oficial['migraciones'])})")
    revisar(verifs == 207, f"207 verificaciones ({verifs})")
    revisar(estados == {"verificable_automaticamente": 36, "migracion_de_datos_no_repetible": 6,
                        "requiere_revision_humana": 1}, f"36 automaticas, 6 de datos, 1 humana: {estados}")
    no_auto = {a: e["estado"] for a, e in oficial["migraciones"].items()
               if e["estado"] != "verificable_automaticamente"}
    revisar(no_auto == NO_AUTOMATICAS, "las mismas siete no automaticas de siempre", f"{no_auto}")
    revisar(not [a for a in oficial["migraciones"] if a in P2], "P2 no esta en el artefacto")
    huella = oficial["referencia"]["huella"]
    revisar(huella["major"] == 17 and huella["server_version_num"] == 170006
            and huella["extensiones"]["pgcrypto"]["schema"] == "extensions",
            f"huella PG17.6 con pgcrypto en extensions (no PG16 ni 'ext'): major {huella['major']}, "
            f"pgcrypto en {huella['extensiones']['pgcrypto']['schema']}")

    titulo("7. las capacidades nuevas del motor, usadas por el artefacto")
    claves = {a: [tuple(v["clave"]) for v in e["verificaciones"]] for a, e in oficial["migraciones"].items()}
    revisar(claves.get(ROLES_OP) == [("schema", "public"), ("acl_tablas", "public"), ("acl_secuencias", "public"),
                                     ("default_acl", "postgres", "public"), ("acl_tabla", "public", "organization")],
            "roles operativos: schema, acl_tablas, acl_secuencias, default_acl y la ACL de organization",
            f"{claves.get(ROLES_OP)}")
    revisar(len(claves.get(COMENTARIOS, [])) == 5
            and all(c[0].startswith("comentario_") for c in claves[COMENTARIOS]),
            "comentarios canonicos: las cinco claves de comentario", f"{claves.get(COMENTARIOS)}")
    revisar(claves.get(A1) == [("funcion", "asistente", "match_chunks")], f"A1: {claves.get(A1)}")
    org = next(v["esperado"] for v in oficial["migraciones"]["202608042055_schema.sql"]["verificaciones"]
               if v["clave"] == ["acl_tabla", "public", "organization"])
    revisar(any(a.startswith("crm_user=") for a in org["acl"]) and any(a.startswith("motor_user=") for a in org["acl"])
            and not any(a.startswith(("anon=", "authenticated=")) for a in org["acl"]),
            f"organization declara crm_user y motor_user, y ya no anon/authenticated: {org['acl']}")

    titulo("8. smoke: adopcion real con el artefacto oficial")
    q("select pg_terminate_backend(pid) from pg_stat_activity where datname = 'postgres' "
      "and pid <> pg_backend_pid()")
    q(sql.SQL("create database {} template postgres owner postgres").format(sql.Identifier("adopta")))
    antes = catalogo("adopta")
    q("drop table if exists asistente.migraciones_aplicadas, asistente.migraciones_ledger_esquema; "
      "drop schema if exists asistente_ledger cascade", usuario="postgres", base="adopta")
    revisar(not q("select to_regclass('asistente.migraciones_aplicadas') is not null", usuario="postgres",
                  base="adopta")[0][0], "la copia de la referencia queda sin ledger, como una base a adoptar")
    # El migrador que usa el ARTEFACTO VERSIONADO: la copia del repo tal cual.
    r = subprocess.run([sys.executable, str(mig_py), "--adoptar", "--escribir-baseline",
                        "--autorizado-por", AUTORIZA], capture_output=True, text=True,
                       env=entorno("adopta"), timeout=900)
    salida = limpiar((r.stdout or "") + (r.stderr or ""))
    revisar(r.returncode == 0 and "36 migracion(es) anotadas" in salida,
            "adopta las 36 automaticas con el manifiesto versionado", f"exit {r.returncode}: {salida[-500:]}")
    for archivo in sorted(NO_AUTOMATICAS):
        r = subprocess.run([sys.executable, str(mig_py), "--adoptar", "--aceptar", archivo, "--motivo", MOTIVO,
                            "--autorizado-por", AUTORIZA, "--escribir-baseline"], capture_output=True, text=True,
                           env=entorno("adopta"), timeout=900)
        if r.returncode != 0:
            revisar(False, f"aceptacion humana de {archivo}", limpiar((r.stdout or "") + (r.stderr or ""))[-400:])
            break
    led = filas_ledger("adopta")
    revisar(len(led) == 43 and set(led) == set(oficial["migraciones"]),
            f"el ledger queda con las 43 filas ({len(led)})")
    revisar(sorted({o for o in led.values()}) == ["baseline", "baseline_humano"],
            f"todas adoptadas, ninguna 'aplicada': {sorted(set(led.values()))}")
    r = subprocess.run([sys.executable, str(mig_py), "--estado"], capture_output=True, text=True,
                       env=entorno("adopta"), timeout=300)
    revisar("pendientes            : 0" in r.stdout and "HUECO" not in r.stdout,
            "--estado: 0 pendientes y sin hueco", limpiar(r.stdout)[-300:])
    revisar(catalogo("adopta") == antes,
            "y ni un solo archivo historico se re-ejecuto: el catalogo quedo igual que antes de adoptar")
finally:
    subprocess.run(["docker", "rm", "-f", NOMBRE], capture_output=True)
    shutil.rmtree(TMP, ignore_errors=True)

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: el manifiesto versionado sale exactamente de la referencia PG17 y adopta las 43 sin re-ejecutar nada")
