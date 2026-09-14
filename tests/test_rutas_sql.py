# -*- coding: utf-8 -*-
"""
================================================================================
 LAS RUTAS QUE PUEDEN EJECUTAR supabase/*.sql  --  una sola escribe
================================================================================

    py -3.13 tests/test_rutas_sql.py                                (estatico)
    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_rutas_sql.py                            (+ con base)

Por que existe
--------------
La auditoria encontro que 'cli/migraciones.py --aplicar' seguia ejecutando
archivos enteros por fuera del ledger. Mientras exista una segunda via, "cada
migracion una sola vez" no es una garantia global.

  1. ESTATICO. Se buscan en cli/, nucleo/ y django-crm/backend todos los modulos
     que LEEN el contenido de migraciones. El conjunto tiene que ser exactamente
     el del inventario (supabase/ledger/analisis/INVENTARIO_RUTAS_SQL.md). En
     cada uno se sigue, por el AST, a donde va el texto leido: solo
     cli/migrar_asistente.py puede pasarlo a execute(). Y nada en compose,
     Dockerfiles, scripts ni CI ejecuta archivos de supabase/.
  2. cli/migraciones.py: '--aplicar' se niega con exit 2 antes de conectarse, no
     escribe aunque falte un objeto, y el modo informativo nunca dice "ok": solo
     FALTA o NO VERIFICABLE.
  3. cli/base_desde_cero.py: un nombre de base malicioso se rechaza sin tocar
     nada; la contraseña no aparece en el comando de docker ni en la salida; no
     existe '--clave'.
================================================================================
"""

from __future__ import annotations

import ast
import os
import re
import secrets
import shutil
import subprocess
import sys
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


# Los modulos que leen contenido de migraciones, segun el inventario.
LECTORES_ESPERADOS = {
    "cli/migrar_asistente.py",        # ejecuta, por el ledger
    "cli/manifiesto_adopcion.py",     # clasifica y hashea; no ejecuta
    "cli/migraciones.py",             # informativo; no ejecuta
}
UNICO_QUE_EJECUTA = "cli/migrar_asistente.py"

# Llamadas que devuelven el CONTENIDO de un archivo de migracion.
FUENTES = {"leer_migracion", "read_text", "read_bytes", "bytes_canonicos"}

# =============================================================================
titulo("1. estatico: quien lee migraciones y a donde va el texto")
# =============================================================================


def _nombre(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _menciona_supabase(nodo) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and "supabase" in n.value
               for n in ast.walk(nodo))


def analizar(ruta: Path) -> tuple[bool, list[str]]:
    """
    (lee_migraciones, ejecuciones_del_texto)

    Lee migraciones si llama a 'leer_migracion' o si lee con read_text/read_bytes
    un path que menciona 'supabase'. Se "contaminan" los nombres asignados desde
    esas lecturas y los que se desempaquetan de estructuras que los contienen
    (plan(), pendientes, datos...), y se reporta cada execute() que recibe uno.
    """
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False, []
    lee = False
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            nom = _nombre(n)
            if nom == "leer_migracion":
                lee = True
            if nom in ("read_text", "read_bytes") and _menciona_supabase(n.func):
                lee = True
    if not lee:
        return lee, []

    ejecuciones = []
    for fn in [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        contaminados: set[str] = set()
        cambio = True
        while cambio:
            cambio = False
            for n in ast.walk(fn):
                objetivos, fuente = [], None
                if isinstance(n, ast.Assign):
                    objetivos, fuente = n.targets, n.value
                elif isinstance(n, (ast.For, ast.comprehension)):
                    objetivos, fuente = [n.target], n.iter
                else:
                    continue
                sucio = False
                for s in ast.walk(fuente):
                    if isinstance(s, ast.Call) and _nombre(s) in FUENTES | {"plan", "validar_dentro"}:
                        sucio = True
                    if isinstance(s, ast.Name) and s.id in contaminados:
                        sucio = True
                if not sucio:
                    continue
                for t in objetivos:
                    for nn in ast.walk(t):
                        if isinstance(nn, ast.Name) and nn.id not in contaminados:
                            contaminados.add(nn.id)
                            cambio = True
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and _nombre(n) == "execute" and n.args:
                if any(isinstance(s, ast.Name) and s.id in contaminados for s in ast.walk(n.args[0])):
                    ejecuciones.append(f"{fn.name}:{n.lineno}")
    return lee, ejecuciones


carpetas = [RAIZ / "cli", RAIZ / "nucleo", RAIZ / "django-crm" / "backend"]
lectores, ejecutores = {}, {}
for base in carpetas:
    for f in base.rglob("*.py"):
        partes = set(f.parts)
        if partes & {"node_modules", "__pycache__", "tests", "migrations", ".venv"}:
            continue
        rel = f.relative_to(RAIZ).as_posix()
        lee, ejec = analizar(f)
        if lee:
            lectores[rel] = ejec
        if ejec:
            ejecutores[rel] = ejec

print(f"       leen migraciones: {sorted(lectores)}")
print(f"       pasan el texto a execute(): {ejecutores}")
revisar(set(lectores) == LECTORES_ESPERADOS,
        "el conjunto de modulos que leen migraciones es exactamente el del inventario",
        f"sobran {sorted(set(lectores) - LECTORES_ESPERADOS)}, "
        f"faltan {sorted(LECTORES_ESPERADOS - set(lectores))}")
revisar(set(ejecutores) == {UNICO_QUE_EJECUTA},
        "SOLO cli/migrar_asistente.py pasa texto de migraciones a execute()",
        f"{ejecutores}")
revisar(any(e.startswith("aplicar:") for e in ejecutores.get(UNICO_QUE_EJECUTA, []))
        and any(e.startswith("asegurar_ledger:") for e in ejecutores.get(UNICO_QUE_EJECUTA, [])),
        "y lo hace en 'aplicar' y 'asegurar_ledger', dentro de la seccion serializada",
        f"{ejecutores.get(UNICO_QUE_EJECUTA)}")

# mutacion: la deteccion tiene que ver una ejecucion directa si aparece
muestra = RAIZ / "tests" / "_ruta_de_prueba_tmp.py"
muestra.write_text(
    "from pathlib import Path\n"
    "def mala(cur):\n"
    "    for f in sorted(Path('supabase').glob('*.sql')):\n"
    "        sql = (Path('supabase') / f.name).read_text(encoding='utf-8')\n"
    "        cur.execute(sql)\n", encoding="utf-8")
try:
    _lee, _ej = analizar(muestra)
    revisar(_lee and _ej, "la deteccion SI encuentra un execute() de un .sql leido de supabase/ "
                          "(control de la propia prueba)", f"lee={_lee} ej={_ej}")
finally:
    muestra.unlink()

no_python = [p for p in [*RAIZ.glob("docker-compose*.yml"), RAIZ / "Dockerfile",
                         RAIZ / "django-crm" / "Dockerfile", *RAIZ.glob("*.sh"),
                         *(RAIZ / "django-crm" / "docker").rglob("*"),
                         *(RAIZ / ".github").rglob("*"), *(RAIZ / "django-crm" / ".github").rglob("*")]
             if p.is_file()]
def ejecuta_supabase(linea: str) -> bool:
    """
    Una linea de infraestructura que EJECUTA archivos de supabase/: psql con
    -f o redireccion, o un montaje en docker-entrypoint-initdb.d. Los comentarios
    no cuentan -- la primera version de esta prueba marco como ruta un comentario
    de docker-compose.yml que solo NOMBRA 'supabase/202608042055_schema.sql'.
    """
    s = linea.strip()
    if not s or s.startswith("#"):
        return False
    if "supabase" not in s:
        return False
    return bool(re.search(r"\bpsql\b|initdb|docker-entrypoint", s)
                or re.search(r"(?:^|\s)-f\s+\S*supabase", s)
                or re.search(r"<\s*\S*supabase", s))


revisar(ejecuta_supabase("psql -h db -f supabase/202608042055_schema.sql")
        and ejecuta_supabase("- ./supabase:/docker-entrypoint-initdb.d:ro")
        and ejecuta_supabase("cat x | psql < supabase/a.sql")
        and not ejecuta_supabase("# 'asistente' (supabase/202608042055_schema.sql) necesita vector"),
        "la deteccion de infraestructura distingue una ejecucion de un comentario "
        "(control de la propia prueba)")

peligrosas = []
for p in no_python:
    t = p.read_text(encoding="utf-8", errors="replace")
    for i, linea in enumerate(t.splitlines(), 1):
        if ejecuta_supabase(linea):
            peligrosas.append(f"{p.relative_to(RAIZ).as_posix()}:{i}: {linea.strip()[:100]}")
revisar(not peligrosas,
        f"ningun compose, Dockerfile, script ni workflow ({len(no_python)} archivos) "
        f"ejecuta archivos de supabase/", f"{peligrosas}")

# Los hooks de git merecen una regla propia. 'post-merge' no ejecutaba SQL, pero
# le INDICABA a quien hace 'git pull' que aplicara las migraciones con
# 'docker exec ... psql ... < supabase/...sql': la ruta que se saltea el ledger,
# entregada como instruccion. Los nombres de archivo le llegaban por variable,
# asi que la linea con psql no decia 'supabase' y la regla de arriba no la veia.
def invoca_psql(linea: str) -> bool:
    """Una INVOCACION de psql (con opciones o redireccion), no una mencion.
    La primera version marcaba la propia advertencia 'NO con psql: ...'."""
    s = linea.strip()
    return (not s.startswith("#")) and bool(re.search(r"\bpsql\s+-|\bpsql\b[^\n]*<", s))


revisar(invoca_psql("echo \"$M\" | sed 's|^|    docker exec -i crm-agentico-db-1 psql -U postgres -d crm_db < |'")
        and not invoca_psql('echo "  Siempre por el ledger. NO con psql: psql se saltea el checksum,"'),
        "la regla de hooks detecta la instruccion vieja y no marca la advertencia nueva "
        "(control de la propia prueba)")

hooks_con_psql = []
for p in sorted((RAIZ / ".githooks").glob("*")):
    if not p.is_file():
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    if "supabase" in t:
        hooks_con_psql += [f"{p.name}:{i}: {l.strip()[:90]}"
                           for i, l in enumerate(t.splitlines(), 1) if invoca_psql(l)]
revisar(not hooks_con_psql,
        "ningun hook de git manda a aplicar migraciones con psql",
        f"{hooks_con_psql}")
post_merge = (RAIZ / ".githooks" / "post-merge").read_text(encoding="utf-8", errors="replace")
revisar("cli/migrar_asistente.py --aplicar" in post_merge,
        "y el aviso de post-merge remite al ledger")

inventario = (RAIZ / "supabase" / "ledger" / "analisis" / "INVENTARIO_RUTAS_SQL.md")
texto_inv = inventario.read_text(encoding="utf-8") if inventario.exists() else ""
revisar(all(l in texto_inv for l in LECTORES_ESPERADOS | {"cli/base_desde_cero.py"}),
        "el inventario documenta cada ruta")

# =============================================================================
titulo("2 y 3. sin base: migraciones.py y base_desde_cero.py")
# =============================================================================
sin_db = {k: v for k, v in os.environ.items()
          if k not in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")}
r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migraciones.py"), "--aplicar"],
                   capture_output=True, text=True, env=sin_db)
revisar(r.returncode == 2 and "migrar_asistente.py" in r.stdout,
        "migraciones.py --aplicar: exit 2 y remite al ledger, sin siquiera conectarse",
        f"exit {r.returncode}: {r.stdout[-200:]}")

sys.path.insert(0, str(RAIZ))
from cli import base_desde_cero as cero                           # noqa: E402

marca = secrets.token_hex(16)
os.environ["DBPASSWORD_ORIGINAL_PRUEBA"] = os.environ.get("DBPASSWORD", "")
cmd = cero.comando_django("base_x", "localhost", "5432", "usuario_x")
revisar("DBPASSWORD" in cmd and not any("DBPASSWORD=" in a for a in cmd),
        "el comando de docker pasa '-e DBPASSWORD' SIN valor", f"{cmd}")
revisar(not any(marca in a for a in cmd), "y no contiene la contraseña")

for maliciosa in ('x"; drop database postgres; --', "Mayus", "con espacio", "a" * 70, "1arranca"):
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", maliciosa],
                       capture_output=True, text=True, env={**sin_db, "DBPASSWORD": marca})
    revisar(r.returncode == 2 and "nombre de base invalido" in r.stdout and marca not in r.stdout + r.stderr,
            f"--base {maliciosa[:30]!r}: rechazado antes de conectarse", r.stdout[-150:])

r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", "ok",
                    "--clave", marca], capture_output=True, text=True, env=sin_db)
revisar(r.returncode == 2 and "--clave" in r.stderr and marca not in r.stdout,
        "'--clave' no existe: la contraseña no se acepta por argumento", r.stderr[-150:])

# =============================================================================
#  con base
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan or not shutil.which("docker"):
    print(f"\n  [saltado] la parte con base necesita {faltan or 'Docker'}")
else:
    import psycopg                                                # noqa: E402

    HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
    USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
    BASE = os.environ.get("DBNAME", "rutas") + "_cero"

    def admin():
        return psycopg.connect(host=HOST, port=PUERTO, dbname="postgres", user=USUARIO,
                               password=CLAVE, sslmode="disable", autocommit=True)

    titulo("2. migraciones.py sobre una base real")
    rol = f"cero_prueba_{secrets.token_hex(4)}"
    clave_rol = secrets.token_urlsafe(24)
    with admin() as con:
        con.execute(f'create role "{rol}" login superuser password %s'.replace("%s", "'" + clave_rol + "'"))
        n_bases = con.execute("select count(*) from pg_database").fetchone()[0]
    try:
        env_rol = {**sin_db, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": rol,
                   "DBPASSWORD": clave_rol}
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                            "--usuario", rol], capture_output=True, text=True, env=env_rol, timeout=900)
        salida = (r.stdout or "") + (r.stderr or "")
        print(f"       base_desde_cero con un rol de contraseña aleatoria: exit {r.returncode} "
              f"en {time.monotonic() - t0:.0f}s")
        revisar(r.returncode == 0, "base_desde_cero construye la base con ese rol", salida[-400:])
        revisar(clave_rol not in salida, "la contraseña del rol NO aparece en la salida")
        revisar("DBPASSWORD=" not in salida, "ni un 'DBPASSWORD=' en el comando impreso")

        with admin() as con:
            pass
        env_db = {**sin_db, "DBHOST": HOST, "DBPORT": PUERTO, "DBNAME": BASE, "DBUSER": USUARIO,
                  "DBPASSWORD": CLAVE}
        r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migraciones.py")],
                           capture_output=True, text=True, env=env_db)
        revisar(r.returncode == 3, "informativo sobre una base completa: exit 3, NO 0",
                f"exit {r.returncode}: {r.stdout[-300:]}")
        revisar("estan aplicadas" not in r.stdout and "[ok]" not in r.stdout,
                "nunca afirma 'aplicadas' ni marca nada como ok", r.stdout[-300:])
        revisar("[NO VERIFICABLE] 202609070900_bandeja_sin_inflar.sql" in r.stdout,
                "bandeja_sin_inflar sale NO VERIFICABLE (antes salia '[ok] 0 objetos')")

        with psycopg.connect(host=HOST, port=PUERTO, dbname=BASE, user=USUARIO, password=CLAVE,
                             sslmode="disable", autocommit=True) as con:
            con.execute("alter table asistente.tool_calls drop column es_bloqueo")
        r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migraciones.py")],
                           capture_output=True, text=True, env=env_db)
        revisar(r.returncode == 1 and "[FALTA] 202609061400_bloqueos_en_traza.sql" in r.stdout,
                "con una columna borrada: exit 1 y FALTA en el archivo que la declara",
                r.stdout[-300:])
        r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migraciones.py"), "--aplicar"],
                           capture_output=True, text=True, env=env_db)
        with psycopg.connect(host=HOST, port=PUERTO, dbname=BASE, user=USUARIO, password=CLAVE,
                             sslmode="disable") as con:
            sigue = con.execute("select count(*) from information_schema.columns where "
                                "table_schema='asistente' and table_name='tool_calls' "
                                "and column_name='es_bloqueo'").fetchone()[0]
        revisar(r.returncode == 2 and sigue == 0,
                "--aplicar con base y un faltante real: exit 2 y la columna sigue sin existir",
                f"exit {r.returncode}, columnas {sigue}")

        titulo("3. nombre malicioso contra un servidor real")
        r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"),
                            "--base", 'x"; drop database postgres; --'],
                           capture_output=True, text=True, env={**env_db})
        with admin() as con:
            n_despues = con.execute("select count(*) from pg_database").fetchone()[0]
            existe_postgres = con.execute("select count(*) from pg_database where datname='postgres'").fetchone()[0]
        revisar(r.returncode == 2 and existe_postgres == 1,
                "rechazado con exit 2; la base 'postgres' sigue ahi", f"exit {r.returncode}")
        revisar(n_despues == n_bases + 1,
                "y la unica base nueva es la que se construyo a proposito",
                f"{n_bases} -> {n_despues}")
    finally:
        with admin() as con:
            con.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname=%s", (BASE,))
            con.execute(f'drop database if exists "{BASE}"')
            try:
                con.execute(f'reassign owned by "{rol}" to "{USUARIO}"')
                con.execute(f'drop owned by "{rol}"')
            except psycopg.Error:
                pass
            con.execute(f'drop role if exists "{rol}"')

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Una sola ruta escribe migraciones, y las herramientas no filtran nada.")
print("=" * 74)
