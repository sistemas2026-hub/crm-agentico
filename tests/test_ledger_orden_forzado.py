# -*- coding: utf-8 -*-
"""
================================================================================
 ADOPCION CONTRA --aplicar, EN LOS DOS ORDENES  --  forzados, no observados
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_ledger_orden_forzado.py

Por que existe
--------------
'test_ledger_carreras.py' lanzaba la adopcion y '--aplicar' a la vez y
aceptaba cualquiera de los dos resultados. En la corrida auditada salio un solo
orden: '--aplicar' tomo el lock primero (exit 6, base existente sin ledger) y la
adopcion despues. El otro orden no se ejercito. Que una prueba "contemple" un
interleaving que el scheduler nunca produjo no es evidencia.

Aca el orden lo impone la prueba con el gancho de 'cli/migrar_asistente.py'
(MIGRAR_PRUEBA_DIR / MIGRAR_PRUEBA_PAUSA):

  1. el PRIMERO arranca con pausa: toma el lock y se detiene DENTRO de la
     seccion, dejando un archivo de señal;
  2. recien entonces arranca el SEGUNDO, y la prueba espera a que registre
     'espera': intento el lock y lo encontro tomado;
  3. la prueba libera al primero.

La coordinacion es por condiciones (archivos de señal y el registro de orden),
no por sleeps. Y cada caso comprueba en 'orden.log' que el orden pedido fue el
que ocurrio: lock del primero < espera del segundo < lock del segundo.

  Caso A  adoptar primero  -> adoptar 0 con 33 filas; --aplicar 5 (hueco)
  Caso B  --aplicar primero -> --aplicar 6 sin crear el ledger; adoptar 0
En los dos: ningun archivo historico ejecutado y el catalogo sin cambios fuera
de las dos tablas del ledger.
================================================================================
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker para las migraciones de Django")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
PREFIJO = os.environ.get("DBNAME", "orden")
DJANGO, REF = PREFIJO + "_django", PREFIJO + "_ref"
IMAGEN = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")


def dsn(base):
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} "
            f"password={CLAVE} sslmode=disable")


def consultar(base, sql, params=None):
    with psycopg.connect(dsn(base), autocommit=True) as con:
        cur = con.execute(sql, params)
        return cur.fetchall() if cur.description else []


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


TMP = Path(tempfile.mkdtemp(prefix="orden-"))
# El manifiesto lo genera esta suite contra SU referencia PostgreSQL 16, no se toma
# el versionado (que describe produccion, PG17). Ver tests/manifiesto_de_laboratorio.py.
import manifiesto_de_laboratorio as lab                            # noqa: E402
ARCHIVOS = lab.archivos_de_adopcion(RAIZ)
MANIFIESTO: dict = {}
AUTO: set[str] = set()

COPIA = TMP / "repo"
(COPIA / "supabase").mkdir(parents=True)
shutil.copytree(RAIZ / "cli", COPIA / "cli", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(RAIZ / "supabase" / "ledger", COPIA / "supabase" / "ledger")
for f in sorted((RAIZ / "supabase").glob("*.sql")):
    if f.name in ARCHIVOS:
        shutil.copy2(f, COPIA / "supabase" / f.name)
MIG = COPIA / "cli" / "migrar_asistente.py"


def entorno(base, extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MIGRAR_PRUEBA_")}
    env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": base,
                "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    env.pop("PGOPTIONS", None)
    env.update(extra or {})
    return env


def lanzar(base, args, extra=None):
    return subprocess.Popen([sys.executable, str(MIG), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=entorno(base, extra))


def esperar(condicion, que, segundos=90):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    raise RuntimeError(f"no se cumplio a tiempo: {que}")


def eventos(d: Path):
    if not (d / "orden.log").exists():
        return []
    return [tuple(l.split()[1:]) for l in (d / "orden.log").read_text(encoding="utf-8").splitlines() if l.strip()]


def foto_catalogo(base):
    """Todo el catalogo de 'asistente' salvo las tablas del ledger, en un hash."""
    return consultar(base, """
        select md5(coalesce(string_agg(x, '|' order by x), '')) from (
          select 'rel:' || c.relname::text || ':' || c.relkind::text || ':' || coalesce(c.relacl::text, '') as x
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'asistente'
             and c.relname not like 'migraciones_%' and c.relname not like 'ma_%'
          union all
          select 'pol:' || tablename::text || ':' || policyname::text || ':' || coalesce(qual, '') || ':' || coalesce(with_check, '')
            from pg_policies where schemaname = 'asistente'
          union all
          select 'fun:' || p.proname::text || ':' || md5(pg_get_functiondef(p.oid)) || ':' || coalesce(p.proacl::text, '')
            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'asistente' and p.prokind = 'f'
        ) t""")[0][0]


def filas(base):
    if not consultar(base, "select to_regclass('asistente.migraciones_aplicadas') is not null")[0][0]:
        return None
    return {f[0]: f[1] for f in consultar(base, "select archivo, origen from asistente.migraciones_aplicadas")}


def forzar(base, primero, segundo, d: Path):
    """Arranca 'primero' con pausa, espera a que 'segundo' quede esperando, libera."""
    d.mkdir()
    p1 = lanzar(base, primero, {"MIGRAR_PRUEBA_DIR": str(d), "MIGRAR_PRUEBA_PAUSA": "1"})
    esperar(lambda: (d / f"pausa_{p1.pid}.dentro").exists(), "el primero entro a la seccion")
    p2 = lanzar(base, segundo, {"MIGRAR_PRUEBA_DIR": str(d)})
    esperar(lambda: (str(p2.pid), "espera") in eventos(d), "el segundo encontro el lock tomado")
    (d / f"pausa_{p1.pid}.seguir").write_text("", encoding="utf-8")
    s1, _ = p1.communicate(timeout=300)
    s2, _ = p2.communicate(timeout=300)
    return (p1.pid, p1.returncode, s1 or ""), (p2.pid, p2.returncode, s2 or ""), eventos(d)


def orden_correcto(ev, pid1, pid2):
    try:
        i_lock1 = ev.index((str(pid1), "lock"))
        i_esp2 = ev.index((str(pid2), "espera"))
        i_lock2 = ev.index((str(pid2), "lock"))
    except ValueError:
        return False
    return i_lock1 < i_esp2 < i_lock2


ADOPTAR = ["--adoptar", "--escribir-baseline", "--espera-lock", "180"]
APLICAR = ["--aplicar", "--espera-lock", "180"]

try:
    titulo("preparando: base con Django y referencia de los 40 archivos")
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
    r = subprocess.run([sys.executable, str(MIG), "--aplicar"], capture_output=True, text=True, env=entorno(REF))
    revisar(r.returncode == 0 and f"{len(ARCHIVOS)} aplicada(s)" in r.stdout,
            f"referencia con los {len(ARCHIVOS)} archivos de adopcion", r.stdout[-200:])
    # El manifiesto de ESTA referencia (PG16), dentro de la copia que usa el migrador.
    MANIFIESTO = lab.generar(COPIA, entorno(REF))
    AUTO = lab.automaticas(MANIFIESTO)
    revisar(set(MANIFIESTO["migraciones"]) == ARCHIVOS and MANIFIESTO["referencia"]["huella"]["major"]
            == int(consultar(REF, "show server_version_num")[0][0]) // 10000,
            f"manifiesto de laboratorio: {len(MANIFIESTO['migraciones'])} archivos, huella de ESTE servidor "
            f"(PostgreSQL {MANIFIESTO['referencia']['huella']['major']}), {len(AUTO)} automaticas")

    # -------------------------------------------------------------------------
    titulo("control: el gancho es inerte sin sus variables")
    # -------------------------------------------------------------------------
    inerte = TMP / "inerte"
    inerte.mkdir()
    r = subprocess.run([sys.executable, str(MIG), "--estado"], capture_output=True, text=True,
                       env=entorno(REF, {"MIGRAR_PRUEBA_PAUSA": "1"}))
    revisar(r.returncode == 0 and not any(inerte.iterdir()),
            "con MIGRAR_PRUEBA_PAUSA pero sin MIGRAR_PRUEBA_DIR no pausa ni escribe nada")
    base_remota = entorno(REF, {"MIGRAR_PRUEBA_DIR": str(inerte), "MIGRAR_PRUEBA_PAUSA": "1",
                                "DBHOST": "db.ejemplo.invalid"})
    sys.path.insert(0, str(COPIA))
    os.environ.update({k: v for k, v in base_remota.items() if k.startswith(("MIGRAR_PRUEBA_", "DBHOST"))})
    from cli import migrar_asistente as mig_copia                 # noqa: E402
    revisar(mig_copia._dir_de_prueba() is None,
            "con un DBHOST no local el gancho queda apagado aunque las variables esten")
    for k in ("MIGRAR_PRUEBA_DIR", "MIGRAR_PRUEBA_PAUSA"):
        os.environ.pop(k, None)
    os.environ["DBHOST"] = HOST

    # -------------------------------------------------------------------------
    titulo("Caso A: la ADOPCION toma el lock primero")
    # -------------------------------------------------------------------------
    A = PREFIJO + "_a"
    recrear(A, REF)
    consultar(A, "drop table asistente.migraciones_aplicadas, asistente.migraciones_ledger_esquema")
    antes = foto_catalogo(A)
    (pid1, c1, s1), (pid2, c2, s2), ev = forzar(A, ADOPTAR, APLICAR, TMP / "caso_a")
    print(f"       orden registrado: {ev}")
    revisar(orden_correcto(ev, pid1, pid2),
            "el orden ocurrio como se forzo: lock(adoptar) < espera(aplicar) < lock(aplicar)", f"{ev}")
    revisar(c1 == 0 and f"{len(AUTO)} migracion(es) anotadas" in s1,
            f"adoptar termina en 0 y anota las {len(AUTO)} automaticas", f"exit {c1}: {s1[-300:]}")
    revisar(c2 == 5 and "ANTERIORES A OTRAS YA ANOTADAS" in s2,
            "--aplicar termina en 5: las 7 no automaticas quedan como hueco", f"exit {c2}: {s2[-300:]}")
    revisar("[ok] 2026" not in s2 and "aplicada(s)" not in s2,
            "--aplicar no ejecuto ningun archivo historico")
    led = filas(A)
    revisar(led is not None and set(led) == AUTO and set(led.values()) == {"baseline"},
            f"ledger: exactamente las {len(AUTO)} automaticas, origen baseline",
            f"{None if led is None else (len(led), set(led.values()))}")
    revisar(foto_catalogo(A) == antes, "catalogo de 'asistente' identico fuera del ledger")

    # -------------------------------------------------------------------------
    titulo("Caso B: --aplicar toma el lock primero")
    # -------------------------------------------------------------------------
    B = PREFIJO + "_b"
    recrear(B, REF)
    consultar(B, "drop table asistente.migraciones_aplicadas, asistente.migraciones_ledger_esquema")
    antes = foto_catalogo(B)
    (pid1, c1, s1), (pid2, c2, s2), ev = forzar(B, APLICAR, ADOPTAR, TMP / "caso_b")
    print(f"       orden registrado: {ev}")
    revisar(orden_correcto(ev, pid1, pid2),
            "el orden ocurrio como se forzo: lock(aplicar) < espera(adoptar) < lock(adoptar)", f"{ev}")
    revisar(c1 == 6 and "YA TIENE el esquema" in s1,
            "--aplicar termina en 6: base existente sin ledger", f"exit {c1}: {s1[-300:]}")
    revisar("[ok] 2026" not in s1 and "esquema del ledger" not in s1,
            "--aplicar no ejecuto ningun archivo ni creo el ledger", s1[-300:])
    revisar(c2 == 0 and f"{len(AUTO)} migracion(es) anotadas" in s2,
            f"adoptar, al entrar despues, crea el ledger y anota las {len(AUTO)}", f"exit {c2}: {s2[-300:]}")
    led = filas(B)
    revisar(led is not None and set(led) == AUTO and set(led.values()) == {"baseline"},
            f"ledger: exactamente las {len(AUTO)} automaticas, origen baseline")
    revisar(foto_catalogo(B) == antes, "catalogo de 'asistente' identico fuera del ledger")

    # -------------------------------------------------------------------------
    titulo("los dos casos juntos")
    # -------------------------------------------------------------------------
    revisar(consultar(A, "select count(*) from asistente.migraciones_aplicadas")[0][0]
            == consultar(B, "select count(*) from asistente.migraciones_aplicadas")[0][0],
            "los dos ordenes llegan al MISMO ledger final")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Adopcion y --aplicar, en los dos ordenes forzados, llegan al mismo lugar.")
print("=" * 74)
