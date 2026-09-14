# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CARRERAS DEL LEDGER  --  las que la primera version no cubria
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_ledger_carreras.py

La prueba de "dos migradores" de test_ledger_migraciones.py corria con el
ledger YA creado. No cubria lo que la auditoria encontro abierto:

  1. bootstrap concurrente: varios migradores contra una base donde no existe
     ni el schema 'asistente' ni el ledger;
  2. una espera de lock vencida no deja NINGUN cambio previo;
  3. adopcion con escritura compitiendo contra '--aplicar';
  4. dos adopciones concurrentes;
  5. un cambio de catalogo mientras la adopcion espera el lock: la
     verificacion que cuenta es la de adentro;
  6. huella del servidor: version mayor, extversion y schema de extension
     distintos bloquean ANTES de verificar y sin crear el ledger;
  7. el lock no es reentrante;
  8. los modos de solo lectura no mutan la base;
  9. el esquema del ledger no hace DROP/ADD en cada comando, y converge un
     ledger creado por la version anterior.

Todo contra bases efimeras que la prueba crea, desde una base con solo Django.
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
import uuid
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
PREFIJO = os.environ.get("DBNAME", "carreras")
DJANGO = PREFIJO + "_django"
REF = PREFIJO + "_ref"
IMAGEN = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")
CLAVE_LOCK = 7_242_026_091_400


def dsn(base):
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} "
            f"password={CLAVE} sslmode=disable")


def consultar(base, sql, params=None):
    with psycopg.connect(dsn(base), autocommit=True) as con:
        cur = con.execute(sql, params)
        return cur.fetchall() if cur.description else []


def recrear(base, plantilla=None):
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        for _ in range(40):
            con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname = any(%s) and pid <> pg_backend_pid()",
                        ([base, plantilla or base],))
            try:
                con.execute(f'drop database if exists "{base}"')
                if plantilla:
                    con.execute(f'create database "{base}" template "{plantilla}"')
                else:
                    con.execute(f'create database "{base}"')
                return
            except (psycopg.errors.ObjectInUse, psycopg.errors.DuplicateDatabase):
                time.sleep(0.5)
        raise RuntimeError(f"no se pudo crear {base}")


TMP = Path(tempfile.mkdtemp(prefix="carreras-"))


def copiar_repo(destino: Path, solo: set[str] | None = None) -> Path:
    (destino / "supabase").mkdir(parents=True)
    shutil.copytree(RAIZ / "cli", destino / "cli", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(RAIZ / "supabase" / "ledger", destino / "supabase" / "ledger")
    for f in sorted((RAIZ / "supabase").glob("*.sql")):
        if solo is None or f.name in solo:
            shutil.copy2(f, destino / "supabase" / f.name)
    return destino


MANIFIESTO = json.loads((RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json")
                        .read_bytes().decode("utf-8"))
ARCHIVOS_MAN = set(MANIFIESTO["migraciones"])
AUTO = {a for a, e in MANIFIESTO["migraciones"].items()
        if e["estado"] == "verificable_automaticamente"}
COPIA = copiar_repo(TMP / "todo")
COPIA_MAN = copiar_repo(TMP / "manifiesto", solo=ARCHIVOS_MAN)
MIG = COPIA / "cli" / "migrar_asistente.py"
MIG_MAN = COPIA_MAN / "cli" / "migrar_asistente.py"


def entorno(base, extra=None):
    env = dict(os.environ)
    env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": base,
                "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    env.pop("PGOPTIONS", None)
    env.update(extra or {})
    return env


def migrar(base, *args, migrador=MIG, timeout=600):
    r = subprocess.run([sys.executable, str(migrador), *args], capture_output=True,
                       text=True, env=entorno(base), timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def lanzar(base, *args, migrador=MIG):
    return subprocess.Popen([sys.executable, str(migrador), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=entorno(base))


def terminar(procesos, timeout=300):
    salida = []
    for p in procesos:
        out, _ = p.communicate(timeout=timeout)
        salida.append((p.returncode, out or ""))
    return salida


def hay_schema(base):
    return consultar(base, "select count(*) from pg_namespace where nspname='asistente'")[0][0] > 0


def hay_ledger(base):
    return consultar(base, "select to_regclass('asistente.migraciones_aplicadas') is not null")[0][0]


def filas(base):
    if not hay_ledger(base):
        return {}
    return {f[0]: f[1] for f in consultar(base, "select archivo, origen from "
                                                "asistente.migraciones_aplicadas")}


def sin_ledger(base):
    """Una base con el esquema completo y SIN ledger: lo que hay en produccion."""
    consultar(base, "drop table if exists asistente.migraciones_aplicadas, "
                    "asistente.migraciones_ledger_esquema")


def esperar_conectado(base, pid_proceso, segundos=20):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if consultar("postgres", "select count(*) from pg_stat_activity where datname=%s "
                                 "and application_name like %s",
                     (base, f"migrar_asistente pid={pid_proceso} %"))[0][0]:
            return True
        time.sleep(0.1)
    return False


class LockAjeno:
    """Una sesion que toma el lock del migrador en ESA base y lo retiene."""

    def __init__(self, base):
        self.con = psycopg.connect(dsn(base), autocommit=True)
        self.con.execute("select pg_advisory_lock(%s)", (CLAVE_LOCK,))

    def soltar(self):
        self.con.execute("select pg_advisory_unlock(%s)", (CLAVE_LOCK,))
        self.con.close()


N = len(list((COPIA / "supabase").glob("*.sql")))

try:
    # =========================================================================
    titulo("preparando: base con solo Django, y la referencia del manifiesto")
    # =========================================================================
    recrear(DJANGO)
    with psycopg.connect(dsn(DJANGO), autocommit=True) as con:
        con.execute("create schema if not exists ext")
        con.execute("create extension if not exists pgcrypto with schema ext")
    host_cont = "host.docker.internal" if HOST in ("localhost", "127.0.0.1") else HOST
    r = subprocess.run([
        "docker", "run", "--rm", "-v", f"{(RAIZ / 'django-crm' / 'backend').as_posix()}:/app",
        "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={PUERTO}", "-e", f"DBNAME={DJANGO}",
        "-e", f"DBUSER={USUARIO}", "-e", "DBPASSWORD",
        "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
        "-e", "SECRET_KEY=solo-para-migrar-una-base-de-pruebas-local",
        "-e", "DEBUG=0", "-e", "ALLOWED_HOSTS=*",
        IMAGEN, "python3", "manage.py", "migrate", "--noinput"],
        capture_output=True, text=True, env=entorno(DJANGO))
    revisar(r.returncode == 0, "Django migra la base vacia", (r.stderr or "")[-300:])
    revisar(not hay_schema(DJANGO), "y la base con solo Django no tiene schema 'asistente'")

    recrear(REF, DJANGO)
    codigo, salida = migrar(REF, "--aplicar", migrador=MIG_MAN)
    revisar(codigo == 0 and f"{len(ARCHIVOS_MAN)} aplicada(s)" in salida,
            f"referencia con los {len(ARCHIVOS_MAN)} archivos del manifiesto", salida[-300:])

    # =========================================================================
    titulo("1. cinco migradores a la vez sobre una base sin asistente ni ledger")
    # =========================================================================
    B1 = PREFIJO + "_b1"
    recrear(B1, DJANGO)
    procesos = [lanzar(B1, "--aplicar", "--espera-lock", "180") for _ in range(5)]
    resultados = terminar(procesos)
    codigos = [c for c, _ in resultados]
    revisar(codigos == [0] * 5, "los cinco terminan en 0", f"{codigos}")
    aplicaron = [s for _, s in resultados if f"{N} aplicada(s)" in s]
    nada = [s for _, s in resultados if "0 migraciones pendientes" in s]
    revisar(len(aplicaron) == 1 and len(nada) == 4,
            "uno crea el ledger y aplica todo; los otros cuatro esperan y ven 0 pendientes",
            f"aplicaron={len(aplicaron)} nada={len(nada)}")
    todo = "\n".join(s for _, s in resultados)
    revisar(not any(x in todo for x in ("duplicate key", "UniqueViolation", "Traceback",
                                        "DuplicateTable", "already exists")),
            "ni una colision de CREATE SCHEMA/TABLE, ni una excepcion", todo[-400:])
    revisar(len(filas(B1)) == N and set(filas(B1).values()) == {"aplicada"},
            f"ledger con {N} filas 'aplicada'")
    version = consultar(B1, "select count(*), max(version) from asistente.migraciones_ledger_esquema")[0]
    revisar(version == (1, 1), "el esquema del ledger quedo anotado UNA vez, version 1",
            f"{version}")

    # =========================================================================
    titulo("2. espera vencida: ningun cambio previo")
    # =========================================================================
    B2 = PREFIJO + "_b2"
    recrear(B2, DJANGO)
    ajeno = LockAjeno(B2)
    t0 = time.monotonic()
    codigo, salida = migrar(B2, "--aplicar", "--espera-lock", "2")
    duro = time.monotonic() - t0
    ajeno.soltar()
    revisar(codigo == 3 and "NO se obtuvo el lock" in salida, "exit 3 al vencer",
            f"exit {codigo}: {salida[-200:]}")
    revisar(duro < 10, f"a los ~2 s (tardo {duro:.1f}s)")
    revisar(not hay_schema(B2) and not hay_ledger(B2),
            "la base sigue SIN schema 'asistente' y sin ledger: nada se creo antes del lock")

    B2b = PREFIJO + "_b2b"
    recrear(B2b, REF)
    sin_ledger(B2b)
    ajeno = LockAjeno(B2b)
    codigo, salida = migrar(B2b, "--adoptar", "--escribir-baseline", "--espera-lock", "2",
                            migrador=MIG_MAN)
    ajeno.soltar()
    revisar(codigo == 3 and not hay_ledger(B2b) and "[VERIFICADA]" not in salida,
            "adopcion con espera vencida: exit 3, sin verificar y sin crear el ledger",
            f"exit {codigo}: {salida[-200:]}")

    # =========================================================================
    titulo("3. adopcion con escritura contra --aplicar, a la vez")
    # =========================================================================
    B3 = PREFIJO + "_b3"
    recrear(B3, REF)
    sin_ledger(B3)
    politicas_antes = consultar(B3, "select count(*) from pg_policies where schemaname='asistente'")[0][0]
    p_adopta = lanzar(B3, "--adoptar", "--escribir-baseline", "--espera-lock", "180", migrador=MIG_MAN)
    p_aplica = lanzar(B3, "--aplicar", "--espera-lock", "180", migrador=MIG_MAN)
    (c_adopta, s_adopta), (c_aplica, s_aplica) = terminar([p_adopta, p_aplica])
    print(f"       adoptar exit={c_adopta}  aplicar exit={c_aplica}")
    revisar(c_adopta == 0, "la adopcion termina en 0", s_adopta[-300:])
    revisar(c_aplica in (5, 6),
            "--aplicar se niega: 6 si llego primero (base existente sin ledger) o 5 si "
            "llego despues (hueco)", f"exit {c_aplica}: {s_aplica[-300:]}")
    revisar("aplicada(s)" not in s_aplica and "[ok] 2026" not in s_aplica,
            "--aplicar no ejecuto ningun archivo historico", s_aplica[-300:])
    revisar(set(filas(B3)) == AUTO and set(filas(B3).values()) == {"baseline"},
            f"el ledger tiene exactamente las {len(AUTO)} automaticas, origen baseline",
            f"{len(filas(B3))} filas, origenes {set(filas(B3).values())}")
    politicas_despues = consultar(B3, "select count(*) from pg_policies where schemaname='asistente'")[0][0]
    revisar(politicas_antes == politicas_despues, "y el catalogo no cambio (mismas politicas)",
            f"{politicas_antes} -> {politicas_despues}")

    # =========================================================================
    titulo("4. dos adopciones a la vez")
    # =========================================================================
    B4 = PREFIJO + "_b4"
    recrear(B4, REF)
    sin_ledger(B4)
    resultados = terminar([lanzar(B4, "--adoptar", "--escribir-baseline", "--espera-lock", "180",
                                  migrador=MIG_MAN) for _ in range(2)])
    todo = "\n".join(s for _, s in resultados)
    revisar([c for c, _ in resultados] == [0, 0], "las dos terminan en 0",
            f"{[c for c, _ in resultados]}")
    revisar("UniqueViolation" not in todo and "duplicate key" not in todo and "Traceback" not in todo,
            "sin colision de clave primaria ni excepcion", todo[-400:])
    revisar(set(filas(B4)) == AUTO, f"el ledger tiene las {len(AUTO)} automaticas, una vez cada una",
            f"{len(filas(B4))}")
    revisar(sum(f"{len(AUTO)} migracion(es) anotadas" in s for _, s in resultados) == 1,
            "una sola anota las automaticas; la otra, al entrar, ya no las tiene pendientes")

    # =========================================================================
    titulo("5. un cambio de catalogo mientras la adopcion espera el lock")
    # =========================================================================
    B5 = PREFIJO + "_b5"
    recrear(B5, REF)
    sin_ledger(B5)
    codigo, salida = migrar(B5, "--adoptar", migrador=MIG_MAN)
    revisar(codigo == 0 and salida.count("[VERIFICADA]") == len(AUTO),
            "antes del cambio, la verificacion de solo lectura pasa entera")

    objetivo = None
    for a in sorted(AUTO):
        for v in MANIFIESTO["migraciones"][a]["verificaciones"]:
            if v["clave"][0] == "politicas":
                nombre = next((n for n, p in v["esperado"].items() if p[2] != "INSERT" and p[3]), None)
                if nombre:
                    objetivo = (a, v["clave"][1], v["clave"][2], nombre)
                    break
        if objetivo:
            break
    revisar(objetivo is not None, "hay una politica de una migracion automatica para alterar")

    ajeno = LockAjeno(B5)
    p = lanzar(B5, "--adoptar", "--escribir-baseline", "--espera-lock", "60", migrador=MIG_MAN)
    revisar(esperar_conectado(B5, p.pid), "la adopcion esta conectada y esperando el lock")
    time.sleep(1.0)
    archivo, esq, tab, pol = objetivo
    consultar(B5, f'alter policy "{pol}" on "{esq}"."{tab}" using (false)')
    ajeno.soltar()
    (codigo, salida), = terminar([p])
    revisar(codigo == 1, "al entrar verifica DE NUEVO y termina en 1", f"exit {codigo}: {salida[-300:]}")
    revisar(any("[NO EQUIVALENTE]" in l and archivo in l for l in salida.splitlines()),
            f"'{archivo}' sale NO EQUIVALENTE", salida[-400:])
    revisar(filas(B5) == {}, "y no se escribio ninguna fila, tampoco de las que verificaban")

    B5b = PREFIJO + "_b5b"
    recrear(B5b, REF)
    sin_ledger(B5b)
    e_do = MANIFIESTO["migraciones"]["202608042055_schema.sql"]
    pol_do = next(v for v in e_do["verificaciones"] if v["clave"][0] == "politicas"
                  and any(pp[2] != "INSERT" and pp[3] for pp in v["esperado"].values()))
    n_do = next(n for n, pp in pol_do["esperado"].items() if pp[2] != "INSERT" and pp[3])
    ajeno = LockAjeno(B5b)
    p = lanzar(B5b, "--adoptar", "--escribir-baseline", "--aceptar", "202608042055_schema.sql",
               "--motivo", "prueba de carrera en base efimera, sin decision real",
               "--espera-lock", "60", migrador=MIG_MAN)
    revisar(esperar_conectado(B5b, p.pid), "la aceptacion humana esta esperando el lock")
    time.sleep(1.0)
    consultar(B5b, f'alter policy "{n_do}" on "{pol_do["clave"][1]}"."{pol_do["clave"][2]}" using (false)')
    ajeno.soltar()
    (codigo, salida), = terminar([p])
    revisar(codigo == 1 and "202608042055_schema.sql" not in filas(B5b),
            "la aceptacion humana tambien re-verifica adentro y no escribe", salida[-300:])

    # =========================================================================
    titulo("6. huella del servidor distinta")
    # =========================================================================
    huella = MANIFIESTO["referencia"]["huella"]
    print(f"       huella del manifiesto: PostgreSQL {huella['major']}, "
          f"extensiones {huella['extensiones']}")
    ext_version = next(iter(sorted(huella["extensiones"])))
    ext_schema = "pgcrypto" if "pgcrypto" in huella["extensiones"] else ext_version
    casos = {
        "version mayor": lambda h: h.update(major=h["major"] - 1),
        f"extversion de {ext_version}": lambda h: h["extensiones"][ext_version].update(version="0.0.1"),
        f"schema de {ext_schema}": lambda h: h["extensiones"][ext_schema].update(schema="extensions"),
    }
    B6 = PREFIJO + "_b6"
    recrear(B6, REF)
    sin_ledger(B6)
    for que, cambio in casos.items():
        copia = copiar_repo(TMP / f"huella_{uuid.uuid4().hex[:6]}", solo=ARCHIVOS_MAN)
        m = json.loads(json.dumps(MANIFIESTO))
        cambio(m["referencia"]["huella"])
        (copia / "supabase" / "ledger" / "manifiesto_adopcion.json").write_bytes(
            json.dumps(m, sort_keys=True, indent=1, ensure_ascii=False).encode("utf-8"))
        migr = copia / "cli" / "migrar_asistente.py"
        for modo in (["--adoptar"], ["--adoptar", "--escribir-baseline"]):
            codigo, salida = migrar(B6, *modo, migrador=migr)
            etiqueta = "escritura" if len(modo) == 2 else "solo lectura"
            revisar(codigo == 7 and "HUELLA" in salida and "[VERIFICADA]" not in salida,
                    f"{que} ({etiqueta}): exit 7, sin una sola verificacion",
                    f"exit {codigo}: {salida[-300:]}")
        revisar(not hay_ledger(B6), f"{que}: el ledger NO se creo")
    codigo, salida = migrar(B6, "--adoptar", migrador=MIG_MAN)
    revisar(codigo == 0, "con la huella verdadera, la misma base se verifica normalmente",
            salida[-200:])

    # =========================================================================
    titulo("7. el lock no es reentrante")
    # =========================================================================
    from cli import migrar_asistente as mig                       # noqa: E402

    os.environ.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": B1, "DBUSER": USUARIO,
                       "DBPASSWORD": CLAVE})
    con = mig.conectar()
    try:
        try:
            with mig.seccion_serializada(con, 5):
                mig.aplicar(con, 5)
            revisar(False, "entrar a la seccion teniendo el lock levanta LockReentrante", "no levanto")
        except mig.LockReentrante:
            revisar(True, "entrar a la seccion teniendo el lock levanta LockReentrante")
        revisar(not mig.tengo_el_lock(con), "y al salir la sesion ya no tiene el lock")
    finally:
        con.close()

    # =========================================================================
    titulo("8. los modos de solo lectura no mutan la base")
    # =========================================================================
    B8 = PREFIJO + "_b8"
    recrear(B8, REF)
    sin_ledger(B8)
    antes = consultar(B8, "select count(*) from pg_class c join pg_namespace n on "
                          "n.oid=c.relnamespace where n.nspname='asistente'")[0][0]
    c1, s1 = migrar(B8, "--estado", migrador=MIG_MAN)
    c2, s2 = migrar(B8, "--adoptar", migrador=MIG_MAN)
    despues = consultar(B8, "select count(*) from pg_class c join pg_namespace n on "
                            "n.oid=c.relnamespace where n.nspname='asistente'")[0][0]
    revisar(not hay_ledger(B8) and antes == despues,
            "--estado y --adoptar sin escribir no crean el ledger ni ningun objeto",
            f"{antes} -> {despues}")
    revisar("BASE EXISTENTE SIN LEDGER" in s1, "--estado avisa que la base es existente sin ledger",
            s1[-300:])
    codigo, salida = migrar(B8, "--aplicar", migrador=MIG_MAN)
    revisar(codigo == 6 and not hay_ledger(B8),
            "--aplicar sobre esa base: exit 6 y tampoco crea el ledger", salida[-300:])

    # =========================================================================
    titulo("9. esquema del ledger versionado, y convergencia del ledger viejo")
    # =========================================================================
    def oids():
        return consultar(B1, "select conname, oid from pg_constraint where conrelid = "
                             "'asistente.migraciones_aplicadas'::regclass order by 1")

    o1 = oids()
    for _ in range(2):
        migrar(B1, "--aplicar")
    o2 = oids()
    revisar(o1 == o2 and len(o1) >= 5,
            "dos --aplicar mas: las constraints del ledger conservan su oid (no hubo DROP/ADD)",
            f"{o1} -> {o2}")
    revisar(consultar(B1, "select count(*) from asistente.migraciones_ledger_esquema")[0][0] == 1,
            "y el esquema sigue con un solo paso anotado")

    B9 = PREFIJO + "_b9"
    recrear(B9, DJANGO)
    consultar(B9, """
        create schema asistente;
        create table asistente.migraciones_aplicadas (
          archivo text primary key, sha256 text not null,
          aplicada_en timestamptz not null default now(), duro_ms integer not null,
          origen text not null default 'aplicada', por_usuario text not null default current_user,
          nota text,
          constraint ma_sha_hex check (sha256 ~ '^[0-9a-f]{64}$'),
          constraint ma_origen check (origen in ('aplicada', 'baseline')),
          constraint ma_duro check (duro_ms >= 0))""")
    codigo, salida = migrar(B9, "--aplicar")
    revisar(codigo == 0 and f"{N} aplicada(s)" in salida and "version 1" in salida,
            "un ledger VIEJO vacio converge a la version 1 y la cadena se aplica", salida[-300:])
    defs = dict(consultar(B9, "select conname, pg_get_constraintdef(oid) from pg_constraint "
                              "where conrelid='asistente.migraciones_aplicadas'::regclass"))
    cols = {f[0] for f in consultar(B9, "select column_name from information_schema.columns "
                                        "where table_schema='asistente' and table_name='migraciones_aplicadas'")}
    revisar("baseline_humano" in defs.get("ma_origen", "") and "ma_nota_base" in defs
            and "ma_algoritmo" in defs and "algoritmo" in cols,
            "con algoritmo, ma_origen con baseline_humano, ma_nota_base y ma_algoritmo", f"{defs}")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Bootstrap, verificacion y escritura quedan en una sola seccion.")
print("=" * 74)
