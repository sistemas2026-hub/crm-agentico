# -*- coding: utf-8 -*-
"""
================================================================================
 LA EVIDENCIA DE CADA ADOPCION, Y EL LEDGER COMO REGISTRO DE SOLO AGREGAR
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_ledger_evidencia.py

Por que existe
--------------
Una fila 'baseline_humano' decia archivo, momento, rol y motivo, pero no contra
que manifiesto se decidio, contra que servidor, ni quien autorizo. Seis meses
despues esa decision no se podia reconstruir. El paso 0002 del esquema agrega
'evidencia'; el 0003 vuelve el ledger de solo agregar.

  1. desde cero: los pasos del esquema, una vez cada uno
  2. baseline automatica: evidencia con manifiesto, servidor y comprobaciones
  3. baseline_humano: --autorizado-por obligatorio, y evidencia completa
  4. las constraints exigen evidencia aunque no se pase por la CLI
  5. solo agregar: UPDATE, DELETE y TRUNCATE fallan; INSERT y DDL no; y el
     limite medido: el owner puede desactivar el trigger
  6. ledger v1 -> v3 con el migrador v1 REAL (git archive del commit auditado):
     sin filas adoptadas actualiza sin tocar filas; con filas adoptadas se niega
     (exit 8) y queda en la version 1; re-adoptar mide la evidencia de nuevo;
     y uno PRE-versionado con una baseline recibe 0001 y queda en la version 1
  7. cuatro migradores actualizando el mismo ledger v1 a la vez
================================================================================
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def titulo(t):
    print()
    print("=" * 74)
    print(f"  {t}")
    print("=" * 74)


faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker") or not shutil.which("git"):
    print("  [saltado] hacen falta Docker (migraciones de Django) y git (el migrador v1)")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402

from cli import migrar_asistente as mig                           # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
PREFIJO = os.environ.get("DBNAME", "evidencia")
DJANGO, REF = PREFIJO + "_django", PREFIJO + "_ref"
IMAGEN = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")
# El migrador auditado ANTES de este cambio: construye ledgers version 1.
V1_COMMIT = "7c73b5a583192507de50e2b67815890e0e961600"
SCHEMA_DO = "202608042055_schema.sql"
MOTIVO = "revisado a mano en el entorno efimero de pruebas"
AUTORIZA = "Responsable de pruebas (acta efimera 0001)"
TRIGGERS = ["ma_sin_truncate", "ma_solo_agregar", "mle_sin_truncate", "mle_solo_agregar"]
NATURALEZA = "declarada por quien corrio el comando; la herramienta no la autentica"


def dsn(base):
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} "
            f"password={CLAVE} sslmode=disable")


def consultar(base, sql, params=None):
    with psycopg.connect(dsn(base), autocommit=True) as con:
        cur = con.execute(sql, params)
        return cur.fetchall() if cur.description else []


def error_sql(base, sql, params=None):
    """(sqlstate, primera linea) de la sentencia, en una transaccion que se deshace siempre."""
    with psycopg.connect(dsn(base)) as con:
        try:
            con.execute(sql, params)
        except psycopg.Error as e:
            con.rollback()
            return e.sqlstate, (str(e).splitlines() or [""])[0]
        con.rollback()
        return None, ""


def recrear(base, plantilla=None):
    from cli import base_desde_cero as cero                      # noqa: E402
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        cero.preparar_roles_de_despliegue(con)      # crm_user/motor_user: prerrequisito de despliegue
        for _ in range(40):
            con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname = any(%s) and pid <> pg_backend_pid()",
                        ([base, plantilla or base],))
            try:
                con.execute(f'drop database if exists "{base}"')
                con.execute(f'create database "{base}"' + (f' template "{plantilla}"' if plantilla else ""))
                return
            except (psycopg.errors.ObjectInUse, psycopg.errors.DuplicateDatabase):
                time.sleep(0.5)
        raise RuntimeError(f"no se pudo crear {base}")


TMP = Path(tempfile.mkdtemp(prefix="evidencia-"))
# El manifiesto lo genera esta suite contra SU referencia PostgreSQL 16; el versionado
# describe produccion (PG17) y su huella no corresponde a este servidor.
# Ver tests/manifiesto_de_laboratorio.py.
import manifiesto_de_laboratorio as lab                            # noqa: E402
ARCHIVOS = lab.archivos_de_adopcion(RAIZ)
MANIFIESTO: dict = {}
AUTO: set[str] = set()
PASOS = sorted(int(p.name[:4]) for p in (RAIZ / "supabase" / "ledger" / "esquema").glob("[0-9][0-9][0-9][0-9]_*.sql"))


def copiar(destino: Path, extra: dict[str, str] | None = None) -> Path:
    (destino / "supabase").mkdir(parents=True)
    shutil.copytree(RAIZ / "cli", destino / "cli", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(RAIZ / "supabase" / "ledger", destino / "supabase" / "ledger")
    for f in sorted((RAIZ / "supabase").glob("*.sql")):
        if f.name in ARCHIVOS:
            shutil.copy2(f, destino / "supabase" / f.name)
    for nombre, contenido in (extra or {}).items():
        (destino / "supabase" / nombre).write_text(contenido, encoding="utf-8")
    return destino


def entorno(base):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MIGRAR_PRUEBA_")}
    env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": base, "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    env.pop("PGOPTIONS", None)
    return env


def pasos(base):
    if not consultar(base, "select to_regclass('asistente.migraciones_ledger_esquema') is not null")[0][0]:
        return []
    return [f[0] for f in consultar(base, "select version from asistente.migraciones_ledger_esquema order by 1")]


def filas(base):
    return consultar(base, "select archivo, sha256, algoritmo, aplicada_en, duro_ms, origen, "
                           "por_usuario, nota from asistente.migraciones_aplicadas order by archivo")


def evidencias(base):
    return {a: (o, e) for a, o, e in consultar(
        base, "select archivo, origen, evidencia from asistente.migraciones_aplicadas")}


def hay_columna_evidencia(base):
    return consultar(base, "select count(*) from information_schema.columns where table_schema = "
                           "'asistente' and table_name = 'migraciones_aplicadas' "
                           "and column_name = 'evidencia'")[0][0] == 1


def triggers(base):
    return [f[0] for f in consultar(
        base, "select tgname from pg_trigger where not tgisinternal and tgrelid in "
              "(select oid from pg_class where relnamespace = 'asistente'::regnamespace "
              " and relname in ('migraciones_aplicadas', 'migraciones_ledger_esquema')) order by 1")]


def sin_ledger(base):
    """El esquema completo y SIN ledger: lo que hay en una base que se adopta."""
    consultar(base, "drop table if exists asistente.migraciones_aplicadas, "
                    "asistente.migraciones_ledger_esquema")
    consultar(base, "drop schema if exists asistente_ledger cascade")


def servidor(base):
    ext = {n: {"version": v, "schema": s} for n, v, s in consultar(
        base, "select e.extname, e.extversion, n.nspname from pg_extension e join pg_namespace n "
              "on n.oid = e.extnamespace where e.extname <> 'plpgsql'")}
    return {"server_version": consultar(base, "show server_version")[0][0],
            "server_version_num": int(consultar(base, "show server_version_num")[0][0]),
            "extensiones": ext}


try:
    MIG = copiar(TMP / "repo") / "cli" / "migrar_asistente.py"
    MIG_EXT = copiar(TMP / "repo_ext", {"202800000000_posterior.sql":
                                        "create table if not exists asistente.posterior (x int);\n"}
                     ) / "cli" / "migrar_asistente.py"

    # El migrador v1, sacado de git tal como fue auditado.
    V1 = TMP / "v1"
    (V1 / "supabase").mkdir(parents=True)
    arch = subprocess.run(["git", "archive", "--format=tar", V1_COMMIT, "cli", "supabase/ledger"],
                          capture_output=True, cwd=str(RAIZ))
    if arch.returncode != 0:
        raise RuntimeError(f"no se pudo sacar {V1_COMMIT[:7]} de git: {arch.stderr[-200:]!r}")
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as t:
        t.extractall(V1, filter="data")
    for f in sorted((RAIZ / "supabase").glob("*.sql")):
        if f.name in ARCHIVOS:
            shutil.copy2(f, V1 / "supabase" / f.name)
    MIG_V1 = V1 / "cli" / "migrar_asistente.py"

    def migrar(base, *args, migrador=MIG):
        r = subprocess.run([sys.executable, str(migrador), *args], capture_output=True,
                           text=True, env=entorno(base), timeout=600)
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    def lanzar(base, *args, migrador=MIG):
        return subprocess.Popen([sys.executable, str(migrador), *args], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=entorno(base))

    # =========================================================================
    titulo("preparando: base con solo Django, y la referencia")
    # =========================================================================
    recrear(DJANGO)
    with psycopg.connect(dsn(DJANGO), autocommit=True) as con:
        con.execute("create schema if not exists ext")
        con.execute("create extension if not exists pgcrypto with schema ext")
    host_cont = "host.docker.internal" if HOST in ("localhost", "127.0.0.1") else HOST
    r = subprocess.run([
        "docker", "run", "--rm", "-v", f"{(RAIZ / 'django-crm' / 'backend').as_posix()}:/app",
        "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={PUERTO}", "-e", f"DBNAME={DJANGO}",
        "-e", f"DBUSER={USUARIO}", "-e", "DBPASSWORD", "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
        "-e", "SECRET_KEY=solo-para-migrar-una-base-de-pruebas-local", "-e", "DEBUG=0",
        "-e", "ALLOWED_HOSTS=*", IMAGEN, "python3", "manage.py", "migrate", "--noinput"],
        capture_output=True, text=True, env=entorno(DJANGO))
    revisar(r.returncode == 0, "Django migra la base vacia", (r.stderr or "")[-300:])
    recrear(REF, DJANGO)
    codigo, salida = migrar(REF, "--aplicar")
    revisar(codigo == 0 and f"{len(ARCHIVOS)} aplicada(s)" in salida,
            f"referencia con los {len(ARCHIVOS)} archivos de adopcion", salida[-300:])
    # El manifiesto de ESTA referencia (PG16), en las tres copias que adoptan.
    COPIA_PPAL = TMP / "repo"
    MANIFIESTO = lab.generar(COPIA_PPAL, entorno(REF))
    lab.replicar(COPIA_PPAL, TMP / "repo_ext")
    AUTO = lab.automaticas(MANIFIESTO)
    # El migrador v1 se audita con SUS herramientas: su manifiesto lo genera su propio
    # generador, que no conoce acl_secuencias ni default_acl (son posteriores). Pedirle
    # que lea un manifiesto nuevo seria inventarle una capacidad que no tenia.
    MANIFIESTO_V1 = lab.generar(V1, entorno(REF))
    AUTO_V1 = lab.automaticas(MANIFIESTO_V1)
    revisar(AUTO_V1 <= AUTO and len(AUTO_V1) <= len(AUTO),
            f"manifiesto del migrador v1: {len(AUTO_V1)} automaticas (el nuevo ve {len(AUTO)}: "
            f"{sorted(AUTO - AUTO_V1) or 'las mismas'})")
    revisar(set(MANIFIESTO["migraciones"]) == ARCHIVOS,
            f"manifiesto de laboratorio: {len(MANIFIESTO['migraciones'])} archivos, {len(AUTO)} automaticas, "
            f"huella PostgreSQL {MANIFIESTO['referencia']['huella']['major']}")

    # =========================================================================
    titulo("1. desde cero: los pasos del esquema, una vez cada uno")
    # =========================================================================
    revisar(PASOS == [1, 2, 3] and pasos(REF) == PASOS, f"el ledger nuevo anota los pasos {PASOS}",
            f"{pasos(REF)}")
    revisar(hay_columna_evidencia(REF), "tiene la columna 'evidencia'")
    ev = evidencias(REF)
    revisar(len(ev) == len(ARCHIVOS) and all(o == "aplicada" and e is None for o, e in ev.values()),
            "las filas 'aplicada' no llevan evidencia")
    revisar(triggers(REF) == TRIGGERS, "y tiene los cuatro triggers de solo agregar", f"{triggers(REF)}")
    donde = consultar(REF, "select n.nspname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                           "where p.proname = 'solo_agregar'")
    revisar(donde == [("asistente_ledger",)],
            "la funcion del trigger vive en 'asistente_ledger', fuera de lo que compara el manifiesto",
            f"{donde}")

    def oids():
        return consultar(REF, "select conname, oid from pg_constraint where conrelid = "
                              "'asistente.migraciones_aplicadas'::regclass order by 1")

    antes = oids()
    codigo, salida = migrar(REF, "--aplicar")
    revisar(codigo == 0 and "0 migraciones pendientes" in salida and "esquema del ledger" not in salida,
            "otra corrida: 0 pendientes y ningun paso del esquema se repite", salida[-200:])
    revisar(pasos(REF) == PASOS and oids() == antes, "mismos pasos, y las constraints con el mismo oid")

    # =========================================================================
    titulo("2. baseline automatica: con que manifiesto, contra que servidor")
    # =========================================================================
    A = PREFIJO + "_a"
    recrear(A, REF)
    sin_ledger(A)
    codigo, salida = migrar(A, "--adoptar", "--escribir-baseline")
    revisar(codigo == 0 and f"{len(AUTO)} migracion(es) anotadas" in salida,
            f"adopta las {len(AUTO)} automaticas", f"exit {codigo}: {salida[-300:]}")
    ev = evidencias(A)
    revisar(set(ev) == AUTO and all(o == "baseline" and isinstance(e, dict) for o, e in ev.values()),
            "cada fila 'baseline' tiene evidencia")
    # El manifiesto que USO la adopcion es el de laboratorio, el de la copia del migrador.
    sha_man, blob = lab.identidad(COPIA_PPAL)
    srv = servidor(A)
    muestra = next(iter(ev.values()))[1] if ev else {}
    revisar(set(muestra) == {"formato", "manifiesto", "entorno", "verificacion", "autorizacion", "operacion"},
            "con sus seis partes", f"{sorted(muestra)}")
    man = muestra.get("manifiesto", {})
    revisar(man.get("sha256") == sha_man and man.get("calculado_sobre") == "archivo",
            "manifiesto: sha256 de los bytes del archivo usado", f"{man.get('sha256')} vs {sha_man}")
    revisar(man.get("git_blob") == blob,
            f"y el id de blob de git de esos mismos bytes ({blob[:12]}): con el artefacto versionado, "
            f"'git log --all --find-object' encuentra su commit",
            f"{man.get('git_blob')} vs {blob}")
    revisar(man.get("referencia") == MANIFIESTO["referencia"],
            "y la referencia del manifiesto, con su huella")
    revisar(muestra.get("entorno") == srv,
            "entorno: version exacta, server_version_num y extensiones, medidos en esta base",
            f"{muestra.get('entorno')} vs {srv}")
    malas = [a for a, (_o, e) in ev.items()
             if e["verificacion"] != {
                 "estado_en_manifiesto": "verificable_automaticamente",
                 "comprobaciones_totales": len(MANIFIESTO["migraciones"][a]["verificaciones"]),
                 "comprobaciones_coincidentes": len(MANIFIESTO["migraciones"][a]["verificaciones"]),
                 "efectos_sin_comprobacion": MANIFIESTO["migraciones"][a]["efectos_sin_comprobacion"]}]
    revisar(ev and not malas, "verificacion: estado y comprobaciones de cada archivo, segun su manifiesto",
            f"{malas[:3]}")
    revisar(all(e["autorizacion"] is None for _o, e in ev.values()),
            "autorizacion: null, porque no se declaro ninguna")
    op = muestra.get("operacion", {})
    revisar(set(op) == {"rol_sesion", "pid"} and op.get("rol_sesion") == USUARIO
            and isinstance(op.get("pid"), int),
            "operacion: rol de la sesion y pid del proceso, nada mas", f"{op}")
    revisar(len({json.dumps([e["entorno"], e["manifiesto"]], sort_keys=True) for _o, e in ev.values()}) == 1,
            "servidor y manifiesto, medidos una sola vez para toda la adopcion")

    A2 = PREFIJO + "_a2"
    recrear(A2, REF)
    sin_ledger(A2)
    codigo, salida = migrar(A2, "--adoptar", "--escribir-baseline", "--autorizado-por", AUTORIZA)
    ev2 = evidencias(A2)
    revisar(codigo == 0 and bool(ev2) and all(
        (e["autorizacion"] or {}).get("declarada_por") == AUTORIZA for _o, e in ev2.values()),
        "con --autorizado-por en una baseline automatica, queda declarada en cada fila", salida[-200:])

    # =========================================================================
    titulo("3. baseline_humano: --autorizado-por obligatorio")
    # =========================================================================
    aceptar = ["--adoptar", "--aceptar", SCHEMA_DO, "--motivo", MOTIVO]
    codigo, salida = migrar(A, *aceptar, "--escribir-baseline")
    revisar(codigo == 2 and "--autorizado-por" in salida and SCHEMA_DO not in evidencias(A),
            "sin --autorizado-por: exit 2 y no escribe", f"exit {codigo}: {salida[-200:]}")
    for malo, que in (("   ", "en blanco"), ("ab", "de 2 caracteres"), ("con\ttab", "con un caracter de control")):
        codigo, salida = migrar(A, *aceptar, "--autorizado-por", malo, "--escribir-baseline")
        revisar(codigo == 2 and SCHEMA_DO not in evidencias(A),
                f"--autorizado-por {que}: exit 2 y no escribe", f"exit {codigo}: {salida[-200:]}")
    codigo, salida = migrar(A, *aceptar, "--autorizado-por", AUTORIZA)
    revisar(codigo == 0 and SCHEMA_DO not in evidencias(A), "en solo lectura no escribe", salida[-200:])
    codigo, salida = migrar(A, *aceptar, "--autorizado-por", AUTORIZA, "--escribir-baseline")
    fila = evidencias(A).get(SCHEMA_DO)
    revisar(codigo == 0 and fila is not None and fila[0] == "baseline_humano",
            "con todo: origen 'baseline_humano'", f"exit {codigo}: {salida[-300:]}")
    if fila:
        e = fila[1]
        entrada = MANIFIESTO["migraciones"][SCHEMA_DO]
        revisar(e["autorizacion"] == {"declarada_por": AUTORIZA, "naturaleza": NATURALEZA},
                "autorizacion: la persona declarada, diciendo que no se autentica", f"{e['autorizacion']}")
        v = e["verificacion"]
        revisar(v["estado_en_manifiesto"] == "requiere_revision_humana"
                and v["comprobaciones_totales"] == v["comprobaciones_coincidentes"] == len(entrada["verificaciones"])
                and v["efectos_sin_comprobacion"] == entrada["efectos_sin_comprobacion"],
                f"verificacion: estado humano, {len(entrada['verificaciones'])} partes estaticas que "
                f"coincidieron y los {len(entrada['efectos_sin_comprobacion'])} efectos que nadie comprobo", f"{v}")
        revisar(e["manifiesto"]["sha256"] == sha_man and e["entorno"] == srv,
                "manifiesto y servidor, igual que en la baseline automatica")
        nota = consultar(A, "select nota from asistente.migraciones_aplicadas where archivo = %s",
                         (SCHEMA_DO,))[0][0]
        revisar(MOTIVO in nota and "motivo" not in e, "el motivo sigue en 'nota' y no se duplica en la evidencia",
                nota)
    host = socket.gethostname().lower()
    persistido = json.dumps(consultar(A, "select archivo, sha256, algoritmo, aplicada_en::text, duro_ms, origen, "
                                         "por_usuario, nota, evidencia from asistente.migraciones_aplicadas"),
                            ensure_ascii=False).lower()
    revisar(len(host) >= 3 and host not in persistido,
            f"el hostname de esta maquina no aparece en ninguna fila del ledger ({len(evidencias(A))} filas)")

    # =========================================================================
    titulo("4. las constraints exigen evidencia aunque no se pase por la CLI")
    # =========================================================================
    base_ev = next(e for o, e in evidencias(A).values() if o == "baseline")
    INS = ("insert into asistente.migraciones_aplicadas (archivo, sha256, duro_ms, origen, nota, evidencia) "
           "values ('209900000000_prueba.sql', repeat('0', 64), 0, %s, 'prueba', %s::jsonb)")
    for origen, evid, que in (
            ("baseline", None, "una baseline sin evidencia"),
            ("baseline", json.dumps({k: v for k, v in base_ev.items() if k != "entorno"}),
             "una evidencia sin 'entorno'"),
            ("baseline_humano", json.dumps({**base_ev, "autorizacion": None}),
             "una baseline_humano sin autorizacion declarada"),
            ("baseline", "[]", "una evidencia que no es un objeto")):
        estado, msg = error_sql(A, INS, (origen, evid))
        revisar(estado == "23514", f"rechaza {que} (check_violation)", f"{estado}: {msg}")
    estado, msg = error_sql(A, INS, ("aplicada", None))
    revisar(estado is None, "y una fila 'aplicada' sin evidencia entra (deshecha)", f"{estado}: {msg}")

    # =========================================================================
    titulo("5. solo agregar")
    # =========================================================================
    antes_f, antes_p = filas(A), pasos(A)
    for sql, que in (
            ("update asistente.migraciones_aplicadas set nota = nota || ' (editada)'", "UPDATE de las notas"),
            ("delete from asistente.migraciones_aplicadas where origen = 'baseline_humano'",
             "DELETE de la aceptacion humana"),
            ("truncate asistente.migraciones_aplicadas", "TRUNCATE del ledger"),
            ("update asistente.migraciones_ledger_esquema set archivo = archivo",
             "UPDATE del registro del esquema"),
            ("delete from asistente.migraciones_ledger_esquema where version = 3",
             "DELETE de un paso del esquema"),
            ("truncate asistente.migraciones_ledger_esquema", "TRUNCATE del registro del esquema")):
        estado, msg = error_sql(A, sql)
        revisar(estado == "LG002" and "solo agregar" in msg, f"{que}: SQLSTATE LG002", f"{estado}: {msg}")
    estado, msg = error_sql(A, "create role ledger_sonda nologin; "
                               "grant usage on schema asistente to ledger_sonda; "
                               "grant update, delete on asistente.migraciones_aplicadas to ledger_sonda; "
                               "set local role ledger_sonda; "
                               "update asistente.migraciones_aplicadas set nota = 'x'")
    revisar(estado == "LG002",
            "un rol que no es owner, con GRANT UPDATE, choca con LG002 y no con un error de permisos",
            f"{estado}: {msg}")
    revisar(filas(A) == antes_f and pasos(A) == antes_p, "el ledger quedo identico")

    INSERTA = PREFIJO + "_ins"
    recrear(INSERTA, REF)
    codigo, salida = migrar(INSERTA, "--aplicar", migrador=MIG_EXT)
    revisar(codigo == 0 and "1 aplicada(s)" in salida
            and "202800000000_posterior.sql" in {f[0] for f in filas(INSERTA)},
            "INSERT sigue funcionando: una migracion posterior se aplica y se anota", salida[-200:])
    estado, msg = error_sql(A, "alter table asistente.migraciones_aplicadas add column prueba_ddl integer")
    revisar(estado is None,
            "DDL sobre el ledger no esta bloqueado: los pasos futuros del esquema pueden correr (deshecho)",
            f"{estado}: {msg}")
    estado, msg = error_sql(A, "alter table asistente.migraciones_aplicadas disable trigger ma_solo_agregar; "
                               "delete from asistente.migraciones_aplicadas where origen = 'baseline_humano'")
    revisar(estado is None,
            "LIMITE, medido: el owner desactiva el trigger y borra. No protege contra el owner (deshecho)",
            f"{estado}: {msg}")
    revisar(filas(A) == antes_f, "y despues de todo, el ledger sigue identico")

    # =========================================================================
    titulo("6. ledger v1 -> v3")
    # =========================================================================
    esquema_v1 = sorted(p.name for p in (V1 / "supabase" / "ledger" / "esquema").glob("*.sql"))
    revisar(esquema_v1 == ["0001_ledger.sql"], f"el migrador de {V1_COMMIT[:7]} solo conoce el paso 0001",
            f"{esquema_v1}")

    V1A = PREFIJO + "_v1a"
    recrear(V1A, DJANGO)
    codigo, salida = migrar(V1A, "--aplicar", migrador=MIG_V1)
    revisar(codigo == 0 and pasos(V1A) == [1] and not hay_columna_evidencia(V1A),
            "6a. el migrador v1 construye un ledger version 1, sin evidencia", salida[-200:])
    antes = filas(V1A)
    codigo, salida = migrar(V1A, "--aplicar")
    revisar(codigo == 0 and "version 2" in salida and "version 3" in salida
            and "0 migraciones pendientes" in salida,
            "sin filas adoptadas, el migrador nuevo lo lleva a la version 3", salida[-300:])
    revisar(pasos(V1A) == PASOS and filas(V1A) == antes
            and all(e is None for _o, e in evidencias(V1A).values()) and triggers(V1A) == TRIGGERS,
            "sin tocar una fila: mismas filas, evidencia null, triggers puestos")

    V1B = PREFIJO + "_v1b"
    recrear(V1B, REF)
    sin_ledger(V1B)
    codigo, salida = migrar(V1B, "--adoptar", "--escribir-baseline", migrador=MIG_V1)
    c2, s2 = migrar(V1B, *aceptar, "--escribir-baseline", migrador=MIG_V1)
    adoptadas = len(AUTO_V1) + 1          # las automaticas SEGUN EL MANIFIESTO V1, mas la aceptada a mano
    revisar(codigo == 0 and c2 == 0 and pasos(V1B) == [1]
            and sum(1 for f in filas(V1B) if f[5] != "aplicada") == adoptadas,
            f"6b. el migrador v1 adopta: {adoptadas} filas sin evidencia en un ledger version 1",
            f"{codigo} {c2}: {s2[-200:]}")
    antes = filas(V1B)
    for que, args in (
            ("--aplicar", ["--aplicar"]),
            ("--adoptar --escribir-baseline", ["--adoptar", "--escribir-baseline", "--autorizado-por", AUTORIZA]),
            ("--aceptar", ["--adoptar", "--aceptar", "202609070900_bandeja_sin_inflar.sql", "--motivo", MOTIVO,
                           "--autorizado-por", AUTORIZA, "--escribir-baseline"])):
        codigo, salida = migrar(V1B, *args)
        revisar(codigo == 8 and f"{adoptadas} fila(s) adoptadas" in salida
                and "No se fabrica evidencia" in salida and "Traceback" not in salida,
                f"el migrador nuevo, {que}: exit 8, dice cuantas filas y por que", f"exit {codigo}: {salida[-400:]}")
    codigo, salida = migrar(V1B, "--estado")
    revisar(f"esquema version 1 de {PASOS[-1]}" in salida, f"--estado muestra 'version 1 de {PASOS[-1]}'",
            salida[:300])
    migrar(V1B, "--adoptar")
    revisar(pasos(V1B) == [1] and filas(V1B) == antes and not hay_columna_evidencia(V1B)
            and triggers(V1B) == [] and consultar(V1B, "select to_regnamespace('asistente_ledger') is null")[0][0],
            "despues de los cinco intentos: version 1, mismas filas, sin columna, sin triggers ni schema nuevo")
    revisar(consultar(V1B, "select count(*) from pg_locks where locktype = 'advisory' and database = "
                           "(select oid from pg_database where datname = current_database())")[0][0] == 0,
            "y nadie quedo con el lock")

    consultar(V1B, "delete from asistente.migraciones_aplicadas where origen <> 'aplicada'")
    codigo, salida = migrar(V1B, "--adoptar", "--escribir-baseline", "--autorizado-por", AUTORIZA)
    ev = evidencias(V1B)
    revisar(codigo == 0 and pasos(V1B) == PASOS and set(ev) == AUTO and all(isinstance(e, dict) for _o, e in ev.values()),
            "6c. el camino honesto: el owner quita las filas v1 y la adopcion se repite, con evidencia medida AHORA",
            f"exit {codigo}: {salida[-300:]}")
    codigo, salida = migrar(V1B, *aceptar, "--autorizado-por", AUTORIZA, "--escribir-baseline")
    revisar(codigo == 0 and evidencias(V1B).get(SCHEMA_DO, (None,))[0] == "baseline_humano",
            "y la aceptacion humana se repite con autorizacion declarada", salida[-200:])

    # Un ledger ANTERIOR al esquema versionado (sin migraciones_ledger_esquema),
    # con una baseline: 0001 se aplica y confirma, 0002 se niega.
    V1D = PREFIJO + "_v1d"
    recrear(V1D, DJANGO)
    primero = sorted(ARCHIVOS)[0]
    consultar(V1D, """
        create schema asistente;
        create table asistente.migraciones_aplicadas (
          archivo text primary key, sha256 text not null,
          aplicada_en timestamptz not null default now(), duro_ms integer not null,
          origen text not null default 'aplicada', por_usuario text not null default current_user,
          nota text,
          constraint ma_sha_hex check (sha256 ~ '^[0-9a-f]{64}$'),
          constraint ma_origen check (origen in ('aplicada', 'baseline')),
          constraint ma_duro check (duro_ms >= 0))""")
    consultar(V1D, "insert into asistente.migraciones_aplicadas (archivo, sha256, duro_ms, origen, nota) "
                   "values (%s, %s, 0, 'baseline', 'adoptada por la version sin esquema versionado')",
              (primero, mig.leer_migracion(RAIZ / "supabase" / primero)[1]))
    LEGADO = ("select archivo, sha256, aplicada_en, duro_ms, origen, por_usuario, nota "
              "from asistente.migraciones_aplicadas order by archivo")
    antes = consultar(V1D, LEGADO)
    revisar(pasos(V1D) == [], "6d. ledger pre-versionado: sin registro de esquema, con una baseline")
    codigo, salida = migrar(V1D, "--aplicar")
    revisar(codigo == 8 and "1 fila(s) adoptadas" in salida and "quedo en la version 1" in salida
            and "Traceback" not in salida,
            "--aplicar: exit 8, y dice que el ledger quedo en la version 1", f"exit {codigo}: {salida[-400:]}")
    revisar(pasos(V1D) == [1], "0001 se aplico y quedo confirmado: version 1", f"{pasos(V1D)}")
    revisar(consultar(V1D, LEGADO) == antes, "la fila historica quedo intacta")
    revisar(not hay_columna_evidencia(V1D), "0002 no dejo nada: sin columna 'evidencia' ni evidencia inventada")
    revisar(triggers(V1D) == [] and consultar(V1D, "select to_regnamespace('asistente_ledger') is null")[0][0],
            "0003 no corrio: sin triggers ni schema 'asistente_ledger'")
    revisar(consultar(V1D, "select count(*) from pg_locks where locktype = 'advisory' and database = "
                           "(select oid from pg_database where datname = current_database())")[0][0] == 0,
            "y el lock quedo liberado")

    # =========================================================================
    titulo("7. cuatro migradores actualizando el mismo ledger v1")
    # =========================================================================
    V1C = PREFIJO + "_v1c"
    recrear(V1C, DJANGO)
    codigo, _ = migrar(V1C, "--aplicar", migrador=MIG_V1)
    revisar(codigo == 0 and pasos(V1C) == [1], "ledger version 1, todo 'aplicada'")
    procesos = [lanzar(V1C, "--aplicar", "--espera-lock", "180") for _ in range(4)]
    resultados = [((p.communicate(timeout=300)[0] or ""), p.returncode) for p in procesos]
    todo = "\n".join(s for s, _c in resultados)
    revisar([c for _s, c in resultados] == [0] * 4, "los cuatro terminan en 0", f"{[c for _s, c in resultados]}")
    revisar(sum("version 2" in s for s, _c in resultados) == 1 and sum("version 3" in s for s, _c in resultados) == 1,
            "uno solo corre los pasos 2 y 3; los otros tres los encuentran hechos")
    revisar(pasos(V1C) == PASOS and not any(x in todo for x in ("Traceback", "duplicate key", "already exists")),
            "cada paso anotado una vez, sin colisiones", todo[-400:])

    os.environ.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": V1C, "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    os.environ.pop("PGOPTIONS", None)
    con = mig.conectar()
    try:
        try:
            mig.asegurar_ledger(con)
            revisar(False, "asegurar_ledger fuera de la seccion serializada se niega", "no se nego")
        except RuntimeError as e:
            revisar("fuera de la seccion" in str(e), "asegurar_ledger fuera de la seccion serializada se niega",
                    str(e))
    finally:
        con.close()
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Cada adopcion dice contra que se decidio, y el ledger no se reescribe.")
print("=" * 74)
