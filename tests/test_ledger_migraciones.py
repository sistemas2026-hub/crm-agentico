# -*- coding: utf-8 -*-
"""
================================================================================
 EL LEDGER  --  repetible, con lock acotado, y sin adivinar al adoptar
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=ledger_pruebas DBUSER=motor \\
      DBPASSWORD=motor py -3.13 tests/test_ledger_migraciones.py

Construye SUS PROPIAS bases desde cero. Toda la suite corre contra COPIAS del
repo en un directorio temporal: hay compuertas que editan archivos ya
aplicados, y sobre el arbol de trabajo una corrida que muere a mitad dejaria un
historico modificado bajo control de versiones.

  A  base vacia: todo pendiente
  B  primera corrida: se aplica y se anota todo
  C  segunda corrida: 0 pendientes, exit 0
  D  archivo editado despues de aplicado: exit 2 antes de tocar nada
  E  migracion que falla: se deshace entera, no se anota
  F  dos migradores a la vez: uno aplica, el otro ve 0 pendientes
  G  un archivo nuevo al final: se aplica solo ese
  H  un HUECO: archivo pendiente anterior a otro anotado -> exit 5, nada
  I  LF (Linux) y CRLF (Windows): mismo hash, cero discrepancias
  J  lock: matan al dueño -> el siguiente recupera en segundos
  K  lock: dueño vivo excede la espera -> exit 3, nombra al dueño, no aplica
  L  lock: una excepcion no deja el lock retenido (finally, en-proceso)
  M  espera fuera de rango -> exit 2
  N  manifiesto: se REGENERA desde una referencia limpia y coincide con el
     versionado, salvo la descripcion libre
  O  adopcion semantica: base equivalente -> verifica las automaticas, no
     escribe en dry-run, no decide datos ni DO
  P  adopcion con la base ALTERADA (politica, definicion de funcion, grant,
     default, predicado de indice) -> NO EQUIVALENTE, no escribe nada
  Q  escritura de baseline: solo las automaticas; las demas quedan como hueco
     y '--aplicar' se niega a ejecutarlas
  R  aceptacion humana individual: motivo obligatorio, partes estaticas
     verificadas, origen 'baseline_humano'
  S  archivos fuera del manifiesto: posteriores se toleran, intercalados no
================================================================================
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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


faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker para las migraciones de Django")
    raise SystemExit(0)

import psycopg                                                    # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = os.environ.get("DBNAME", "ledger_pruebas")
DJANGO = BASE + "_django"
REF = BASE + "_ref"
ADOPTA = BASE + "_adopta"
ADOPTA2 = BASE + "_adopta2"
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
        con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname in (%s, %s) and pid <> pg_backend_pid()",
                    (base, plantilla or base))
        con.execute(f'drop database if exists "{base}"')
        for _ in range(20):
            try:
                if plantilla:
                    con.execute(f'create database "{base}" template "{plantilla}"')
                else:
                    con.execute(f'create database "{base}"')
                return
            except psycopg.errors.ObjectInUse:
                con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                            "where datname = %s and pid <> pg_backend_pid()",
                            (plantilla,))
                time.sleep(0.5)
        raise RuntimeError(f"no se pudo crear {base} desde {plantilla}")


# --- copias del repo ----------------------------------------------------------
TMP = Path(tempfile.mkdtemp(prefix="ledger-"))


def copiar_repo(destino: Path, solo: set[str] | None = None,
                desde_git: bool = False) -> Path:
    """cli/ y supabase/ (con ledger/). 'solo' limita los .sql de nivel superior.
    'desde_git' escribe los .sql con los bytes del BLOB (LF), no del arbol."""
    (destino / "supabase").mkdir(parents=True)
    shutil.copytree(RAIZ / "cli", destino / "cli",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(RAIZ / "supabase" / "ledger", destino / "supabase" / "ledger")
    for f in sorted((RAIZ / "supabase").glob("*.sql")):
        if solo is not None and f.name not in solo:
            continue
        if desde_git:
            blob = subprocess.run(["git", "show", f"HEAD:supabase/{f.name}"],
                                  capture_output=True, cwd=str(RAIZ)).stdout
            (destino / "supabase" / f.name).write_bytes(blob)
        else:
            shutil.copy2(f, destino / "supabase" / f.name)
    return destino


COPIA = copiar_repo(TMP / "repo")
MIGRADOR = COPIA / "cli" / "migrar_asistente.py"


def entorno(base, extra=None):
    env = dict(os.environ)
    env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": base,
                "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    env.pop("PGOPTIONS", None)
    env.update(extra or {})
    return env


def migrar(*args, base=BASE, migrador=MIGRADOR, extra=None, timeout=600):
    r = subprocess.run([sys.executable, str(migrador), *args],
                       capture_output=True, text=True, timeout=timeout,
                       env=entorno(base, extra))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def lanzar(*args, base=BASE, migrador=MIGRADOR, extra=None):
    return subprocess.Popen([sys.executable, str(migrador), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=entorno(base, extra))


def anotadas(base=BASE):
    try:
        return {f[0]: f[1] for f in consultar(
            base, "select archivo, origen from asistente.migraciones_aplicadas")}
    except psycopg.errors.Error:
        return {}


def duenos_del_lock(base):
    return consultar(base,
                     "select a.pid, a.application_name from pg_locks l "
                     "join pg_stat_activity a on a.pid=l.pid "
                     "where l.locktype='advisory' and l.granted and l.objsubid=1 "
                     "and ((l.classid::bigint << 32) | l.objid::bigint) = %s",
                     (CLAVE_LOCK,))


def esperar_dueno(base, segundos=30):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        d = duenos_del_lock(base)
        if d:
            return d
        time.sleep(0.1)
    return []


# Un archivo "lento" cuyo sueño lo decide la SESION, no el contenido: el mismo
# archivo --mismo hash-- duerme 60 s en el migrador que se va a matar y 0 s en
# el que lo recupera.
LENTO = ("create table if not exists asistente.{tabla} (x int);\n"
         "select pg_sleep(coalesce(nullif(current_setting('prueba.dormir', true), "
         "'')::float, 0));\n")


# =============================================================================
titulo("preparando: base con Django, y sus copias")
# =============================================================================
recrear(DJANGO)
with psycopg.connect(dsn(DJANGO), autocommit=True) as con:
    con.execute("create schema if not exists ext")
    con.execute("create extension if not exists pgcrypto with schema ext")
host_cont = "host.docker.internal" if HOST in ("localhost", "127.0.0.1") else HOST
r = subprocess.run([
    "docker", "run", "--rm",
    "-v", f"{(RAIZ / 'django-crm' / 'backend').as_posix()}:/app",
    "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={PUERTO}",
    "-e", f"DBNAME={DJANGO}", "-e", f"DBUSER={USUARIO}", "-e", f"DBPASSWORD={CLAVE}",
    "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
    "-e", "SECRET_KEY=solo-para-migrar-una-base-de-pruebas-local",
    "-e", "DEBUG=0", "-e", "ALLOWED_HOSTS=*",
    IMAGEN, "python3", "manage.py", "migrate", "--noinput",
], capture_output=True, text=True)
revisar(r.returncode == 0, "migraciones de Django (exit 0)", (r.stderr or "")[-400:])
hay = consultar(DJANGO, "select to_regclass('public.organization') is not null")[0][0]
revisar(hay, "public.organization existe: de eso dependen los archivos de supabase/")
recrear(BASE, DJANGO)

N = len(list((COPIA / "supabase").glob("*.sql")))

# =============================================================================
titulo("A. base vacia")
# =============================================================================
codigo, salida = migrar("--estado")
revisar(codigo == 1 and f"pendientes            : {N}" in salida,
        f"--estado: {N} pendientes, exit 1", f"exit {codigo}: {salida[:300]}")

# =============================================================================
titulo("B. primera corrida")
# =============================================================================
codigo, salida = migrar("--aplicar")
revisar(codigo == 0 and f"{N} aplicada(s)" in salida,
        f"--aplicar: {N} aplicadas, exit 0", salida[-400:])
revisar(len(anotadas()) == N and set(anotadas().values()) == {"aplicada"},
        f"{N} filas con origen 'aplicada'")
alg = consultar(BASE, "select distinct algoritmo from asistente.migraciones_aplicadas")
revisar(alg == [("sha256-utf8-lf-v1",)], "todas con algoritmo 'sha256-utf8-lf-v1'",
        f"{alg}")

# La referencia para regenerar el manifiesto NO se toma de esta base: se
# construye en la compuerta N desde la base con solo Django y EXACTAMENTE los
# archivos que lista el manifiesto. Con el repo integrado (ledger + P2) esta base
# tiene mas migraciones que el manifiesto, y el generador rechaza con razon una
# referencia con anotadas de mas.

# =============================================================================
titulo("C. segunda corrida")
# =============================================================================
codigo, salida = migrar("--aplicar")
revisar(codigo == 0 and "0 migraciones pendientes" in salida
        and "DuplicateObject" not in salida,
        "0 pendientes, exit 0, sin DuplicateObject", salida[-300:])

# =============================================================================
titulo("D. archivo editado despues de aplicado")
# =============================================================================
victima = sorted((COPIA / "supabase").glob("*.sql"))[-1]
original = victima.read_bytes()
victima.write_bytes(original + b"\n-- una linea agregada despues de aplicar\n")
codigo, salida = migrar("--aplicar")
revisar(codigo == 2 and victima.name in salida and "anotado:" in salida,
        "exit 2, nombra el archivo y muestra los dos hashes", salida[-300:])
victima.write_bytes(original)
codigo, _ = migrar("--estado")
revisar(codigo == 0, "restaurado, --estado vuelve a 0", f"exit {codigo}")

# =============================================================================
titulo("E. migracion que falla")
# =============================================================================
rota = COPIA / "supabase" / "202700000000_rota.sql"
rota.write_text("create table asistente.tabla_que_si_entra (x int);\nselect 1/0;\n",
                encoding="utf-8")
codigo, salida = migrar("--aplicar")
revisar(codigo == 1 and "DivisionByZero" in salida, "exit 1 y dice por que",
        salida[-300:])
quedo = consultar(BASE, "select to_regclass('asistente.tabla_que_si_entra') is not null")[0][0]
revisar(not quedo, "la tabla que alcanzo a crear NO quedo")
revisar(rota.name not in anotadas() and len(anotadas()) == N,
        "no quedo anotada y las anteriores siguen")
rota.unlink()

# =============================================================================
titulo("F. dos migradores a la vez")
# =============================================================================
(COPIA / "supabase" / "202700000001_lento.sql").write_text(
    LENTO.format(tabla="solo_uno"), encoding="utf-8")
resultados = []
cerrojo = threading.Lock()


def competir():
    c, s = migrar("--aplicar", "--espera-lock", "60",
                  extra={"PGOPTIONS": "-c prueba.dormir=3"})
    with cerrojo:
        resultados.append((c, s))


hilos = [threading.Thread(target=competir) for _ in range(2)]
for h in hilos:
    h.start()
for h in hilos:
    h.join(timeout=120)
revisar(sorted(c for c, _ in resultados) == [0, 0], "los dos terminan en 0",
        f"{[c for c, _ in resultados]}")
revisar(sum("1 aplicada(s)" in s for _, s in resultados) == 1
        and sum("0 migraciones pendientes" in s for _, s in resultados) == 1,
        "uno aplica, el otro espera y ve 0 pendientes",
        f"{[s[-200:] for _, s in resultados]}")
revisar(any("el lock lo tiene otro migrador" in s for _, s in resultados),
        "el que espera dice que espera y a quien")

# =============================================================================
titulo("G. un archivo nuevo al final")
# =============================================================================
(COPIA / "supabase" / "202700000002_nuevo.sql").write_text(
    "create table if not exists asistente.recien_llegada (x int);\n", encoding="utf-8")
codigo, salida = migrar("--aplicar")
revisar(codigo == 0 and "1 aplicada(s)" in salida and "202700000002_nuevo" in salida,
        "se aplica solo el nuevo", salida[-300:])

# =============================================================================
titulo("H. un hueco: pendiente anterior a otra ya anotada")
# =============================================================================
viejo = COPIA / "supabase" / "202609999999_viejo.sql"
viejo.write_text("create table asistente.hueco_prueba (x int);\n", encoding="utf-8")
codigo, salida = migrar("--aplicar")
revisar(codigo == 5, "--aplicar termina en 5", f"exit {codigo}: {salida[-300:]}")
revisar(viejo.name in salida and "No se aplica nada" in salida,
        "nombra el archivo y no aplica", salida[-300:])
creada = consultar(BASE, "select to_regclass('asistente.hueco_prueba') is not null")[0][0]
revisar(not creada, "la tabla del archivo viejo NO se creo")
codigo, salida = migrar("--estado")
revisar(f"HUECO: {viejo.name}" in salida, "--estado lo muestra como HUECO", salida[-300:])
viejo.unlink()

# =============================================================================
titulo("I. LF y CRLF dan el mismo hash contra la misma base")
# =============================================================================
crlf = sum(1 for f in (COPIA / "supabase").glob("*.sql") if b"\r\n" in f.read_bytes())
print(f"       archivos con CRLF en la copia del arbol: {crlf}")
COPIA_LF = copiar_repo(TMP / "repo_lf",
                       solo={f.name for f in (RAIZ / "supabase").glob("*.sql")},
                       desde_git=True)
for extra_f in ("202700000001_lento.sql", "202700000002_nuevo.sql"):
    shutil.copy2(COPIA / "supabase" / extra_f, COPIA_LF / "supabase" / extra_f)
# Solo se cuentan los archivos que salieron de git. Los dos de prueba se
# copiaron de la copia del arbol, escritos con write_text en Windows: tienen
# CRLF, y justamente por eso sirven para mostrar que la mezcla no molesta.
de_git = {f.name for f in (RAIZ / "supabase").glob("*.sql")}
lf = sum(1 for f in (COPIA_LF / "supabase").glob("*.sql")
         if f.name in de_git and b"\r" in f.read_bytes())
revisar(lf == 0, f"los {len(de_git)} archivos sacados de los blobs de git no tienen un solo CR",
        f"{lf} con CR")
codigo, salida = migrar("--estado", migrador=COPIA_LF / "cli" / "migrar_asistente.py")
revisar(codigo == 0 and "con checksum distinto : 0" in salida,
        f"la base migrada desde el arbol ({crlf} archivos con CRLF) no ve NINGUNA "
        f"discrepancia leyendo los mismos archivos en LF", salida[:400])

# =============================================================================
titulo("J. matan al dueño del lock: el siguiente recupera")
# =============================================================================
(COPIA / "supabase" / "202700000003_lento_kill.sql").write_text(
    LENTO.format(tabla="tras_matar"), encoding="utf-8")
dueno = lanzar("--aplicar", extra={"PGOPTIONS": "-c prueba.dormir=60"})
visto = esperar_dueno(BASE)
revisar(bool(visto) and f"pid={dueno.pid}" in (visto[0][1] if visto else ""),
        "el primer migrador tiene el lock, identificable por su application_name",
        f"{visto}")
time.sleep(1)
dueno.kill()
dueno.wait(timeout=20)
t0 = time.monotonic()
codigo, salida = migrar("--aplicar", "--espera-lock", "45")
duro = time.monotonic() - t0
print(f"       el segundo termino en {duro:.1f}s (el muerto iba a dormir 60s)")
revisar(codigo == 0 and "1 aplicada(s)" in salida,
        "el segundo obtiene el lock y aplica el archivo que el muerto no termino",
        salida[-300:])
revisar(duro < 20,
        "en segundos, no en lo que le faltaba al muerto (client_connection_check_interval)",
        f"tardo {duro:.1f}s")
revisar(consultar(BASE, "select count(*) from asistente.migraciones_aplicadas "
                        "where archivo='202700000003_lento_kill.sql'")[0][0] == 1,
        "una sola fila para ese archivo")

# =============================================================================
titulo("K. dueño vivo excede la espera")
# =============================================================================
(COPIA / "supabase" / "202700000004_lento_espera.sql").write_text(
    LENTO.format(tabla="tras_esperar"), encoding="utf-8")
dueno = lanzar("--aplicar", extra={"PGOPTIONS": "-c prueba.dormir=12"})
esperar_dueno(BASE)
t0 = time.monotonic()
codigo, salida = migrar("--aplicar", "--espera-lock", "2")
duro = time.monotonic() - t0
revisar(codigo == 3, "el segundo termina en 3", f"exit {codigo}: {salida[-300:]}")
revisar(duro < 8, f"a los ~2 s de espera, no despues (tardo {duro:.1f}s)")
revisar("NO se obtuvo el lock" in salida and f"pid={dueno.pid}" in salida,
        "y nombra al dueño con su pid de proceso", salida[-400:])
revisar("202700000004_lento_espera.sql" not in anotadas(),
        "sin aplicar nada mientras tanto")
salida_dueno, _ = dueno.communicate(timeout=60)
revisar(dueno.returncode == 0 and "1 aplicada(s)" in salida_dueno,
        "el dueño termina normalmente", salida_dueno[-200:])

# =============================================================================
titulo("L. una excepcion no deja el lock retenido")
# =============================================================================
from cli import migrar_asistente as mig                           # noqa: E402

os.environ.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": BASE,
                   "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
os.environ.pop("PGOPTIONS", None)
carpeta_l = TMP / "falla_l"
carpeta_l.mkdir()
(carpeta_l / "202800000000_falla.sql").write_text("select 1/0;\n", encoding="utf-8")
con = mig.conectar()
try:
    codigo = mig.aplicar(con, 5, carpeta=carpeta_l)
    retenidos = con.execute("select count(*) from pg_locks where locktype='advisory' "
                            "and pid = pg_backend_pid()").fetchone()[0]
    revisar(codigo == 1 and retenidos == 0,
            "tras una migracion fallida, la MISMA sesion sigue viva y sin el lock",
            f"exit {codigo}, locks retenidos {retenidos}")

    original_plan = mig.plan

    def explota(*a, **k):
        raise RuntimeError("una excepcion de Python, no de SQL")

    mig.plan = explota
    try:
        mig.aplicar(con, 5, carpeta=carpeta_l)
        revisar(False, "la excepcion sube", "no subio")
    except RuntimeError:
        revisar(True, "la excepcion sube, sin tragarse")
    finally:
        mig.plan = original_plan
    retenidos = con.execute("select count(*) from pg_locks where locktype='advisory' "
                            "and pid = pg_backend_pid()").fetchone()[0]
    revisar(retenidos == 0, "y el 'finally' solto el lock en la misma sesion",
            f"{retenidos} retenidos")
finally:
    con.close()

# =============================================================================
titulo("M. espera fuera de rango")
# =============================================================================
codigo, salida = migrar("--aplicar", "--espera-lock", "700")
revisar(codigo == 2 and "entre 0 y 600" in salida, "exit 2 sin intentar nada",
        salida[-200:])

# =============================================================================
titulo("N. el manifiesto se regenera y coincide con el versionado")
# =============================================================================
versionado_p = RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json"
revisar(versionado_p.exists(), "hay un manifiesto versionado en el repo")
versionado = (json.loads(versionado_p.read_bytes().decode("utf-8"))
              if versionado_p.exists() else {"migraciones": {}})
archivos_man = set(versionado.get("migraciones", {}))
COPIA_REF = copiar_repo(TMP / "repo_ref", solo=archivos_man)
MIG_REF = COPIA_REF / "cli" / "migrar_asistente.py"
generado_p = TMP / "manifiesto_regenerado.json"
recrear(REF, DJANGO)
codigo, salida = migrar("--aplicar", base=REF, migrador=MIG_REF)
revisar(codigo == 0 and f"{len(archivos_man)} aplicada(s)" in salida,
        f"la referencia se construye con exactamente los {len(archivos_man)} archivos "
        f"del manifiesto", salida[-300:])
codigo, salida = migrar("--estado", base=REF, migrador=MIG_REF)
revisar(codigo == 0, "la referencia esta completa segun el ledger", salida[:300])
r = subprocess.run([sys.executable, str(COPIA_REF / "cli" / "manifiesto_adopcion.py"),
                    "--generar", "--salida", str(generado_p)],
                   capture_output=True, text=True, env=entorno(REF))
revisar(r.returncode == 0, "se genera contra la referencia", (r.stdout + r.stderr)[-300:])
generado = (json.loads(generado_p.read_bytes().decode("utf-8"))
            if generado_p.exists() else {})
comparable_g = json.loads(json.dumps(generado))
comparable_v = json.loads(json.dumps(versionado))
for d in (comparable_g, comparable_v):
    d.get("referencia", {}).pop("descripcion", None)
revisar(comparable_g == comparable_v and bool(generado),
        "regenerado == versionado: el manifiesto es reproducible",
        "difieren -- el manifiesto versionado no sale de esta referencia")

rehusado = subprocess.run([sys.executable, str(COPIA_REF / "cli" / "manifiesto_adopcion.py"),
                           "--generar", "--salida", str(TMP / "no.json")],
                          capture_output=True, text=True, env=entorno(BASE))
revisar(rehusado.returncode != 0,
        "y se NIEGA a generar desde una base que no es una referencia limpia",
        (rehusado.stdout + rehusado.stderr)[-200:])

est: dict[str, int] = {}
for e in versionado["migraciones"].values():
    est[e["estado"]] = est.get(e["estado"], 0) + 1
print(f"       estados en el manifiesto: {est}")
AUTO = {a for a, e in versionado["migraciones"].items()
        if e["estado"] == "verificable_automaticamente"}

# =============================================================================
titulo("O. adopcion de una base equivalente")
# =============================================================================
recrear(ADOPTA, REF)
consultar(ADOPTA, "delete from asistente.migraciones_aplicadas")
codigo, salida = migrar("--adoptar", base=ADOPTA, migrador=MIG_REF)
revisar(codigo == 0, "dry-run exit 0", salida[-400:])
revisar(salida.count("[VERIFICADA]") == len(AUTO) and "[NO EQUIVALENTE]" not in salida,
        f"las {len(AUTO)} automaticas verifican, ninguna difiere",
        f"verificadas={salida.count('[VERIFICADA]')}")
revisar(anotadas(ADOPTA) == {}, "no escribio ni una fila")
revisar("ADOPCION INCOMPLETA" in salida and "202609070900_bandeja_sin_inflar.sql" in salida
        and "MIGRACION_DE_DATOS_NO_REPETIBLE" in salida,
        "bandeja_sin_inflar figura como migracion de datos y la adopcion se declara "
        "incompleta", salida[-600:])

# =============================================================================
titulo("P. adopcion de una base ALTERADA")
# =============================================================================
auto_man = {a: e for a, e in versionado["migraciones"].items() if a in AUTO}


def buscar(tipo, condicion):
    for a in sorted(auto_man):
        for v in auto_man[a]["verificaciones"]:
            if v["clave"][0] == tipo and condicion(v):
                return a, v
    return None, None


objetivos: dict[str, str] = {}
with psycopg.connect(dsn(ADOPTA), autocommit=True) as con:
    a, v = buscar("politicas", lambda v: any(p[2] != "INSERT" and p[3]
                                             for p in v["esperado"].values()))
    if v:
        _, esq, tab = v["clave"]
        nombre = next(n for n, p in v["esperado"].items() if p[2] != "INSERT" and p[3])
        con.execute(f'alter policy "{nombre}" on "{esq}"."{tab}" using (false)')
        objetivos["politica USING"] = a

    a, v = buscar("funcion", lambda v: bool(v["esperado"]))
    if v:
        _, esq, _nom = v["clave"]
        firma = sorted(v["esperado"])[0]
        con.execute(f'alter function "{esq}".{firma} cost 777')
        objetivos["definicion de funcion"] = a

    a, v = buscar("acl_tabla", lambda v: v["esperado"].get("existe"))
    if v:
        _, esq, tab = v["clave"]
        con.execute("do $$ begin if not exists (select 1 from pg_roles where "
                    "rolname='intruso_prueba') then create role intruso_prueba nologin; "
                    "end if; end $$")
        con.execute(f'grant select on "{esq}"."{tab}" to intruso_prueba')
        objetivos["grant"] = a

    a, v = buscar("tabla", lambda v: any(c[2] and not c[3] for c in
                                         v["esperado"].get("columnas", {}).values()))
    if v:
        _, esq, tab = v["clave"]
        col = next(n for n, c in v["esperado"]["columnas"].items() if c[2] and not c[3])
        con.execute(f'alter table "{esq}"."{tab}" alter column "{col}" drop default')
        objetivos["default de columna"] = a

    def indice_libre(v):
        d = v["esperado"].get("definicion")
        if not d or " WHERE " in d or "UNIQUE" in d:
            return False
        return not con.execute(
            "select exists(select 1 from pg_constraint where conindid = "
            "to_regclass(format('%%I.%%I', %s::text, %s::text)))",
            (v["clave"][1], v["clave"][2])).fetchone()[0]

    a, v = buscar("indice", indice_libre)
    if v:
        _, esq, idx = v["clave"]
        con.execute(f'drop index "{esq}"."{idx}"')
        con.execute(v["esperado"]["definicion"] + " WHERE false")
        objetivos["predicado de indice"] = a

print(f"       alteraciones: {objetivos}")
revisar(len(objetivos) == 5, "se pudieron aplicar las cinco alteraciones",
        f"solo {sorted(objetivos)}")
codigo, salida = migrar("--adoptar", base=ADOPTA, migrador=MIG_REF)
revisar(codigo == 1, "dry-run termina en 1: la base no es equivalente", f"exit {codigo}")
for que, archivo in objetivos.items():
    linea = next((ln for ln in salida.splitlines()
                  if "[NO EQUIVALENTE]" in ln and archivo in ln), None)
    revisar(linea is not None, f"{que}: '{archivo}' sale NO EQUIVALENTE", salida[-500:])
codigo, salida = migrar("--adoptar", "--escribir-baseline", base=ADOPTA, migrador=MIG_REF)
revisar(codigo == 1 and anotadas(ADOPTA) == {},
        "con --escribir-baseline tampoco escribe NADA: ni las que si verificaban",
        f"exit {codigo}, filas {len(anotadas(ADOPTA))}")

# =============================================================================
titulo("Q. escritura de baseline y el hueco que deja")
# =============================================================================
recrear(ADOPTA2, REF)
consultar(ADOPTA2, "delete from asistente.migraciones_aplicadas")
codigo, salida = migrar("--adoptar", "--escribir-baseline", base=ADOPTA2, migrador=MIG_REF)
led = anotadas(ADOPTA2)
revisar(codigo == 0 and set(led) == AUTO and set(led.values()) == {"baseline"},
        f"escribe exactamente las {len(AUTO)} automaticas, origen 'baseline'",
        f"exit {codigo}, escribio {len(led)}: {salida[-300:]}")
notas = consultar(ADOPTA2, "select count(*) from asistente.migraciones_aplicadas "
                           "where nota like 'adoptada: %% comprobaciones de catalogo%%'")[0][0]
revisar(notas == len(led), "cada fila dice cuantas comprobaciones pasaron",
        f"{notas} de {len(led)}")
codigo, salida = migrar("--aplicar", base=ADOPTA2, migrador=MIG_REF)
revisar(codigo == 5 and "202609070900_bandeja_sin_inflar.sql" in salida,
        "--aplicar se NIEGA (exit 5): no re-ejecuta bandeja_sin_inflar ni ninguna "
        "migracion sin decidir", f"exit {codigo}: {salida[-300:]}")
revisar(set(anotadas(ADOPTA2)) == AUTO, "y no anoto nada")

# =============================================================================
titulo("R. aceptacion humana individual")
# =============================================================================
DO_FILE = "202608042055_schema.sql"
e_do = versionado["migraciones"].get(DO_FILE, {})
revisar(e_do.get("estado") == "requiere_revision_humana",
        f"'{DO_FILE}' (bloque DO) no es automatica", f"{e_do.get('estado')}")
MOTIVO = "revisado a mano en el entorno efimero de pruebas"
codigo, salida = migrar("--adoptar", "--aceptar", DO_FILE, "--motivo", "corto",
                        "--escribir-baseline", base=ADOPTA2, migrador=MIG_REF)
revisar(codigo == 2 and DO_FILE not in anotadas(ADOPTA2),
        "un motivo de menos de 20 caracteres se rechaza", salida[-200:])

pol = next((v for v in e_do.get("verificaciones", []) if v["clave"][0] == "politicas"
            and any(p[2] != "INSERT" and p[3] for p in v["esperado"].values())), None)
if pol:
    _, esq, tab = pol["clave"]
    nombre, p = next((n, p) for n, p in pol["esperado"].items() if p[2] != "INSERT" and p[3])
    consultar(ADOPTA2, f'alter policy "{nombre}" on "{esq}"."{tab}" using (false)')
    codigo, salida = migrar("--adoptar", "--aceptar", DO_FILE, "--motivo", MOTIVO,
                            "--escribir-baseline", base=ADOPTA2, migrador=MIG_REF)
    revisar(codigo == 1 and DO_FILE not in anotadas(ADOPTA2),
            "si sus partes ESTATICAS no coinciden, la aceptacion humana se rechaza",
            salida[-300:])
    consultar(ADOPTA2, f'alter policy "{nombre}" on "{esq}"."{tab}" using ({p[3]})')
else:
    revisar(False, "el archivo con DO tiene una politica verificable para alterar")

codigo, salida = migrar("--adoptar", "--aceptar", DO_FILE, "--motivo", MOTIVO,
                        base=ADOPTA2, migrador=MIG_REF)
revisar(codigo == 0 and DO_FILE not in anotadas(ADOPTA2), "en dry-run no escribe",
        salida[-200:])
codigo, salida = migrar("--adoptar", "--aceptar", DO_FILE, "--motivo", MOTIVO,
                        "--escribir-baseline", base=ADOPTA2, migrador=MIG_REF)
fila = consultar(ADOPTA2, "select origen, nota from asistente.migraciones_aplicadas "
                          "where archivo=%s", (DO_FILE,))
revisar(codigo == 0 and bool(fila) and fila[0][0] == "baseline_humano"
        and f"ACEPTACION HUMANA por {USUARIO}" in fila[0][1],
        "con motivo y partes estaticas correctas: origen 'baseline_humano', con quien "
        "y por que", f"exit {codigo}: {fila} {salida[-200:]}")

# =============================================================================
titulo("S. archivos fuera del manifiesto")
# =============================================================================
recrear(ADOPTA, REF)
consultar(ADOPTA, "delete from asistente.migraciones_aplicadas")
COPIA_EXT = copiar_repo(TMP / "repo_ext", solo=archivos_man)
(COPIA_EXT / "supabase" / "202800000000_posterior.sql").write_text(
    "create table if not exists asistente.posterior (x int);\n", encoding="utf-8")
codigo, salida = migrar("--adoptar", base=ADOPTA,
                        migrador=COPIA_EXT / "cli" / "migrar_asistente.py")
revisar(codigo == 0 and "posteriores al manifiesto" in salida
        and salida.count("[VERIFICADA]") == len(AUTO),
        "uno POSTERIOR se tolera: queda fuera y pendiente para --aplicar", salida[-400:])
(COPIA_EXT / "supabase" / "202608000000_intercalado.sql").write_text(
    "create table if not exists asistente.intercalado (x int);\n", encoding="utf-8")
codigo, salida = migrar("--adoptar", base=ADOPTA,
                        migrador=COPIA_EXT / "cli" / "migrar_asistente.py")
revisar(codigo == 1 and "No se adopta" in salida and anotadas(ADOPTA) == {},
        "uno INTERCALADO antes del final del manifiesto: no se adopta nada", salida[-300:])

shutil.rmtree(TMP, ignore_errors=True)
print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Repetible, con lock acotado, y la adopcion no adivina.")
print("=" * 74)
