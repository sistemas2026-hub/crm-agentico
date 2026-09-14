# -*- coding: utf-8 -*-
"""
================================================================================
 EL LEDGER  --  lo que tiene que ser cierto para que un despliegue se repita
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=ledger_pruebas DBUSER=motor \\
      DBPASSWORD=motor py -3.13 tests/test_ledger_migraciones.py

La prueba construye SU PROPIA base desde cero --no reutiliza ninguna-- porque
la mitad de lo que mide es qué pasa en la primera corrida contra qué pasa en la
segunda, y eso sobre una base heredada no se puede afirmar.

Lo que se mide:

  A. Base vacia: todo pendiente, nada anotado.
  B. Primera corrida: se aplican los N, se anotan los N.
  C. Segunda corrida: CERO pendientes, exit 0. (Antes: 5 DuplicateObject.)
  D. Un archivo editado despues de aplicado: se detiene ANTES de tocar nada.
  E. Una migracion que falla: se deshace entera, no queda anotada, y las
     anteriores siguen aplicadas.
  F. Dos migradores a la vez: uno aplica, el otro no aplica nada.
  G. Un archivo nuevo despues de todo: se aplica solo el nuevo.
  H. Adopcion de una base existente: dry-run no escribe, clasifica cada
     archivo, y los NO verificables no se marcan solos.

Requiere Docker para el paso de Django (crea public.organization). Sin Docker,
se salta con un mensaje y no falla en silencio.
================================================================================
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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

import psycopg                                                    # noqa: E402

HOST = os.environ["DBHOST"]
PUERTO = os.environ["DBPORT"]
USUARIO = os.environ["DBUSER"]
CLAVE = os.environ["DBPASSWORD"]
BASE = os.environ.get("DBNAME", "ledger_pruebas")
IMAGEN = os.environ.get("IMAGEN_DJANGO", "dexter-backend:latest")


def dsn(base=BASE):
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} "
            f"password={CLAVE} sslmode=disable")


def migrar(*args, carpeta=None, entorno=None):
    """Corre el migrador como PROCESO. Devuelve (exit, salida)."""
    env = dict(os.environ)
    env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": BASE,
                "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    if entorno:
        env.update(entorno)
    r = subprocess.run(
        [sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), *args],
        capture_output=True, text=True, env=env,
        cwd=str(carpeta or RAIZ))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def anotadas():
    with psycopg.connect(dsn()) as con:
        try:
            return {f[0]: f[1] for f in con.execute(
                "select archivo, sha256 from asistente.migraciones_aplicadas"
            ).fetchall()}
        except psycopg.errors.Error:
            return {}


# -----------------------------------------------------------------------------
titulo("preparando: base vacia + Django")
# -----------------------------------------------------------------------------
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker para las migraciones de Django")
    raise SystemExit(0)

with psycopg.connect(dsn("postgres"), autocommit=True) as con:
    con.execute(f'drop database if exists "{BASE}"')
    con.execute(f'create database "{BASE}"')
with psycopg.connect(dsn(), autocommit=True) as con:
    con.execute("create schema if not exists ext")
    con.execute("create extension if not exists pgcrypto with schema ext")
print(f"  base '{BASE}' creada, con pgcrypto en 'ext'")

host_cont = "host.docker.internal" if HOST in ("localhost", "127.0.0.1") else HOST
r = subprocess.run([
    "docker", "run", "--rm",
    "-v", f"{(RAIZ / 'django-crm' / 'backend').as_posix()}:/app",
    "-e", f"DBHOST={host_cont}", "-e", f"DBPORT={PUERTO}",
    "-e", f"DBNAME={BASE}", "-e", f"DBUSER={USUARIO}",
    "-e", f"DBPASSWORD={CLAVE}",
    "-e", "DJANGO_SETTINGS_MODULE=crm.settings",
    "-e", "SECRET_KEY=solo-para-migrar-una-base-de-pruebas",
    "-e", "DEBUG=0", "-e", "ALLOWED_HOSTS=*",
    IMAGEN, "python3", "manage.py", "migrate", "--noinput",
], capture_output=True, text=True)
revisar(r.returncode == 0, "las migraciones de Django corren (exit 0)",
        (r.stderr or "")[-400:])
with psycopg.connect(dsn()) as con:
    hay = con.execute("select to_regclass('public.organization') is not null "
                      "as hay").fetchone()[0]
revisar(hay, "y crean public.organization, que es de lo que dependen los "
             "archivos de supabase/")

N = len(sorted((RAIZ / "supabase").glob("*.sql")))

# -----------------------------------------------------------------------------
titulo("A. base vacia: todo pendiente")
# -----------------------------------------------------------------------------
codigo, salida = migrar("--estado")
revisar(codigo == 1, "con pendientes, --estado termina en 1", f"exit {codigo}")
revisar(f"pendientes            : {N}" in salida,
        f"los {N} archivos figuran como pendientes", salida[:300])
revisar("anotados en el ledger : 0" in salida, "y ninguno anotado")

# -----------------------------------------------------------------------------
titulo("B. primera corrida")
# -----------------------------------------------------------------------------
codigo, salida = migrar("--aplicar")
revisar(codigo == 0, "aplica y termina en 0", salida[-500:])
revisar(f"{N} aplicada(s)" in salida, f"dice haber aplicado las {N}")
led = anotadas()
revisar(len(led) == N, f"y hay {N} filas en el ledger", f"hay {len(led)}")
with psycopg.connect(dsn()) as con:
    origenes = {f[0] for f in con.execute(
        "select distinct origen from asistente.migraciones_aplicadas").fetchall()}
    duros = con.execute(
        "select count(*) from asistente.migraciones_aplicadas "
        "where duro_ms > 0").fetchone()[0]
revisar(origenes == {"aplicada"}, "todas con origen 'aplicada'", f"{origenes}")
revisar(duros > 0, "y con duracion medida", f"{duros} con duro_ms > 0")

# -----------------------------------------------------------------------------
titulo("C. segunda corrida  --  la que fallaba")
# -----------------------------------------------------------------------------
codigo, salida = migrar("--aplicar")
revisar(codigo == 0 and "0 migraciones pendientes" in salida,
        "segunda corrida: 0 pendientes, exit 0",
        f"exit {codigo}: {salida[-400:]}")
revisar("DuplicateObject" not in salida and "42710" not in salida,
        "sin DuplicateObject: los cinco archivos con 'create policy' sin "
        "guarda no se vuelven a ejecutar",
        salida[-400:])
codigo, _ = migrar("--estado")
revisar(codigo == 0, "y --estado termina en 0", f"exit {codigo}")

# -----------------------------------------------------------------------------
titulo("D. un archivo editado despues de aplicado")
# -----------------------------------------------------------------------------
victima = sorted((RAIZ / "supabase").glob("*.sql"))[-1]
original = io.open(victima, encoding="utf-8").read()
try:
    io.open(victima, "w", encoding="utf-8").write(
        original + "\n-- una linea agregada despues de aplicar\n")
    codigo, salida = migrar("--aplicar")
    revisar(codigo == 2, "se detiene con exit 2", f"exit {codigo}")
    revisar("CAMBIARON" in salida and victima.name in salida,
            "y nombra el archivo que cambio", salida[-400:])
    revisar("anotado:" in salida and "ahora:" in salida,
            "mostrando los dos hashes")
    codigo2, _ = migrar("--estado")
    revisar(codigo2 == 2, "--estado tambien lo ve", f"exit {codigo2}")
finally:
    io.open(victima, "w", encoding="utf-8", newline="").write(original)
codigo, _ = migrar("--estado")
revisar(codigo == 0, "restaurado el archivo, vuelve a estar todo en orden",
        f"exit {codigo}")

# -----------------------------------------------------------------------------
titulo("E. una migracion que falla")
# -----------------------------------------------------------------------------
# Se trabaja sobre una COPIA de la carpeta: el repo no se toca.
tmp = Path(tempfile.mkdtemp(prefix="ledger-"))
copia = tmp / "repo"
shutil.copytree(RAIZ / "supabase", copia / "supabase")
shutil.copytree(RAIZ / "cli", copia / "cli")
rota = copia / "supabase" / "202699999999_rota.sql"
rota.write_text(
    "create table asistente.tabla_que_si_entra (x int);\n"
    "select 1/0;\n", encoding="utf-8")

env = dict(os.environ)
env.update({"DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": BASE,
            "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
r = subprocess.run([sys.executable, str(copia / "cli" / "migrar_asistente.py"),
                    "--aplicar"], capture_output=True, text=True, env=env)
salida = (r.stdout or "") + (r.stderr or "")
revisar(r.returncode == 1, "termina en 1", f"exit {r.returncode}: {salida[-300:]}")
revisar("DivisionByZero" in salida or "division by zero" in salida,
        "y dice por que fallo", salida[-300:])
with psycopg.connect(dsn()) as con:
    quedo = con.execute("select to_regclass('asistente.tabla_que_si_entra') "
                        "is not null as hay").fetchone()[0]
revisar(not quedo,
        "la tabla que la migracion alcanzo a crear NO quedo: se deshizo entera",
        "quedo la tabla -- la transaccion por archivo no esta funcionando")
revisar(rota.name not in anotadas(),
        "y la migracion fallida NO quedo anotada")
revisar(len(anotadas()) == N,
        f"las {N} anteriores siguen aplicadas y anotadas",
        f"hay {len(anotadas())}")

# -----------------------------------------------------------------------------
titulo("F. dos migradores a la vez")
# -----------------------------------------------------------------------------
# Un archivo nuevo, lento a proposito, y dos migradores compitiendo por el.
lento = copia / "supabase" / "202699999998_lento.sql"
rota.unlink()
lento.write_text(
    "create table if not exists asistente.solo_uno (x int);\n"
    "select pg_sleep(2);\n", encoding="utf-8")

resultados: list[tuple[int, str]] = []
cerrojo = threading.Lock()


def competir():
    r = subprocess.run(
        [sys.executable, str(copia / "cli" / "migrar_asistente.py"),
         "--aplicar", "--espera-lock", "20"],
        capture_output=True, text=True, env=env)
    with cerrojo:
        resultados.append((r.returncode, (r.stdout or "") + (r.stderr or "")))


hilos = [threading.Thread(target=competir) for _ in range(2)]
for h in hilos:
    h.start()
for h in hilos:
    h.join(timeout=90)

aplicaron = [x for x in resultados if "1 aplicada(s)" in x[1]]
nada = [x for x in resultados if "0 migraciones pendientes" in x[1]]
revisar(len(resultados) == 2, "los dos migradores terminaron",
        f"{len(resultados)}")
revisar(len(aplicaron) == 1,
        "exactamente UNO aplico la migracion",
        f"aplicaron {len(aplicaron)}: {[x[1][-200:] for x in aplicaron]}")
revisar(len(nada) == 1,
        "y el otro espero el lock y vio que ya no habia nada pendiente",
        f"{[x[1][-300:] for x in resultados]}")
revisar(all(c == 0 for c, _ in resultados),
        "los dos terminan en 0: perder la carrera no es un error",
        f"{[c for c, _ in resultados]}")
with psycopg.connect(dsn()) as con:
    veces = con.execute(
        "select count(*) from asistente.migraciones_aplicadas "
        "where archivo = %s", (lento.name,)).fetchone()[0]
revisar(veces == 1, "y el ledger tiene UNA sola fila para ese archivo",
        f"{veces}")

# -----------------------------------------------------------------------------
titulo("G. un archivo nuevo despues de todo")
# -----------------------------------------------------------------------------
nuevo = copia / "supabase" / "202699999997_nuevo.sql"
nuevo.write_text("create table if not exists asistente.recien_llegada (x int);\n",
                 encoding="utf-8")
r = subprocess.run([sys.executable, str(copia / "cli" / "migrar_asistente.py"),
                    "--aplicar"], capture_output=True, text=True, env=env)
salida = (r.stdout or "") + (r.stderr or "")
revisar(r.returncode == 0 and "1 aplicada(s)" in salida,
        "se aplica SOLO el archivo nuevo", f"exit {r.returncode}: {salida[-300:]}")
revisar(nuevo.name in salida and lento.name not in salida.split("pendiente")[-1],
        "y las anteriores no se vuelven a nombrar")

# -----------------------------------------------------------------------------
titulo("H. adoptar una base que ya tiene el esquema")
# -----------------------------------------------------------------------------
# Se vacia el ledger para simular la base de produccion: esquema completo, cero
# registro. Es exactamente el estado que hay que poder adoptar.
with psycopg.connect(dsn(), autocommit=True) as con:
    con.execute("delete from asistente.migraciones_aplicadas")

codigo, salida = migrar("--adoptar")
revisar(codigo == 0, "el dry-run termina en 0", f"exit {codigo}")
revisar(len(anotadas()) == 0,
        "y NO escribio ni una fila", f"escribio {len(anotadas())}")
revisar("[PRESENTE]" in salida, "clasifica los que puede verificar")
revisar("[NO VERIFICABLE]" in salida,
        "y marca aparte los que no dejan objetos buscables",
        salida[-500:])
revisar("DRY-RUN" in salida, "lo dice explicitamente")

presentes = salida.count("[PRESENTE]")
noverif = salida.count("[NO VERIFICABLE]")
ausentes = salida.count("[AUSENTE]")
print(f"       presentes={presentes} no-verificables={noverif} "
      f"ausentes={ausentes}")
revisar(ausentes == 0,
        "ningun archivo figura como ausente: el esquema esta completo",
        f"{ausentes} ausentes")

codigo, salida = migrar("--adoptar", "--escribir-baseline")
revisar(codigo == 0, "con --escribir-baseline termina en 0", salida[-300:])
led = anotadas()
revisar(len(led) == presentes,
        f"anota los {presentes} verificados y SOLO esos",
        f"anoto {len(led)}")
revisar(len(led) < N,
        f"los {noverif} no verificables quedan sin anotar, esperando una "
        f"decision humana",
        f"anoto {len(led)} de {N} -- si anotara los {N} estaria adivinando")
with psycopg.connect(dsn()) as con:
    orig = {f[0] for f in con.execute(
        "select distinct origen from asistente.migraciones_aplicadas").fetchall()}
    notas = con.execute(
        "select count(*) from asistente.migraciones_aplicadas "
        "where nota is not null").fetchone()[0]
revisar(orig == {"baseline"}, "todas marcadas con origen 'baseline'", f"{orig}")
revisar(notas == len(led), "y con la nota de que se verifico", f"{notas}")

codigo, salida = migrar("--estado")
revisar(codigo == 1 and f"pendientes            : {noverif}" in salida,
        "despues del baseline quedan pendientes exactamente los no "
        "verificables", salida[:400])

shutil.rmtree(tmp, ignore_errors=True)

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El ledger hace repetible el despliegue y no adivina nada.")
print("=" * 74)
