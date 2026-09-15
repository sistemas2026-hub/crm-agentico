# -*- coding: utf-8 -*-
"""
================================================================================
 P2 INTEGRADO E INERTE  --  que estar en el repo no es estar encendido
================================================================================

    py -3.13 tests/test_p2_inerte.py                         (estatico, sin base)
    DBHOST=... DBNAME=<base construida por el ledger> ... \\
        py -3.13 tests/test_p2_inerte.py                     (ademas, la base)

Por que existe
--------------
La rama 'integracion/p2-inerte' junta el ledger y el scheduler persistente.
Integrarlo "inerte" es una afirmacion con cinco partes, y cada una se mide:

  1. Importar el paquete no arranca nada: ni hilos, ni procesos, ni conexiones.
  2. Ningun entrypoint existente lo alcanza: ni el motor, ni el reloj, ni
     Django, ni un CMD de Dockerfile, ni un 'command:' de compose.
  3. Solo 'nucleo/programador/' llama a las funciones que reclaman, ejecutan o
     finalizan turnos. Nada mas en el repo -- ni una URL, ni un comando, ni el
     frontend -- puede encenderlo por accidente.
  4. Ninguna migracion siembra un job: el catalogo nace vacio.
  5. Sobre una base construida por el ledger: catalogo y estado vacios, y la
     segunda pasada del migrador no tiene nada pendiente.

La comprobacion de alcance es ESTATICA sobre el AST (el grafo de imports), no
importando los entrypoints: importar el motor real para probar que no importa
algo exigiria credenciales y red, y una prueba que las necesita no se corre.
================================================================================
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
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


PAQUETE = "nucleo.programador"
FUNCIONES_QUE_ACTUAN = ("job_claim", "jobs_vencidos", "job_finalize",
                        "job_contexto", "job_heartbeat")

# =============================================================================
titulo("1. importar el paquete no arranca nada")
# =============================================================================
programa = r'''
import sys, threading, subprocess
sys.path.insert(0, sys.argv[1])
import psycopg
llamadas = []
def prohibido(nombre):
    def f(*a, **k):
        llamadas.append(nombre)
        raise RuntimeError("prohibido al importar: " + nombre)
    return f
psycopg.connect = prohibido("psycopg.connect")
subprocess.Popen = prohibido("subprocess.Popen")
antes = threading.active_count()
import importlib, pkgutil
import nucleo.programador as p
modulos = [m.name for m in pkgutil.iter_modules(p.__path__)]
for m in modulos:
    importlib.import_module("nucleo.programador." + m)
print("MODULOS", ",".join(sorted(modulos)))
print("HILOS", antes, threading.active_count())
print("LLAMADAS", ",".join(llamadas) or "-")
'''
r = subprocess.run([sys.executable, "-c", programa, str(RAIZ)],
                   capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
salida = r.stdout
revisar(r.returncode == 0, "se importan todos los modulos del paquete sin error",
        (r.stderr or "")[-400:])
m = re.search(r"HILOS (\d+) (\d+)", salida)
revisar(bool(m) and m.group(1) == m.group(2),
        "no se creo ningun hilo", salida)
revisar("LLAMADAS -" in salida,
        "no se intento ninguna conexion a la base ni ningun proceso", salida)
print(f"       {next((l for l in salida.splitlines() if l.startswith('MODULOS')), '')}")

# =============================================================================
titulo("2. ningun entrypoint existente alcanza el paquete")
# =============================================================================
def modulo_de(ruta: Path) -> str:
    rel = ruta.relative_to(RAIZ).with_suffix("")
    partes = list(rel.parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


fuentes: dict[str, Path] = {}
for carpeta in ("nucleo", "cli"):
    for f in (RAIZ / carpeta).rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        fuentes[modulo_de(f)] = f


def imports_de(ruta: Path, modulo: str) -> set[str]:
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    salida_ = set()
    paquete = modulo.rsplit(".", 1)[0] if ruta.name != "__init__.py" else modulo
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                salida_.add(a.name)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if nodo.level:
                raiz = paquete.split(".")
                raiz = raiz[:len(raiz) - (nodo.level - 1)] if nodo.level > 1 else raiz
                base = ".".join(raiz + ([base] if base else []))
            salida_.add(base)
            for a in nodo.names:
                salida_.add(f"{base}.{a.name}")
    return salida_


def alcanzables(desde: str) -> set[str]:
    vistos, pila = set(), [desde]
    while pila:
        actual = pila.pop()
        if actual in vistos or actual not in fuentes:
            continue
        vistos.add(actual)
        for imp in imports_de(fuentes[actual], actual):
            partes = imp.split(".")
            for i in range(len(partes), 0, -1):
                candidato = ".".join(partes[:i])
                if candidato in fuentes:
                    pila.append(candidato)
                    break
    return vistos


entrypoints = [m for m in ("nucleo.canales.api", "nucleo.reloj") if m in fuentes]
entrypoints += sorted(m for m, f in fuentes.items()
                      if m.startswith("cli.") and "__main__" in f.read_text(encoding="utf-8")
                      and m != "cli.salud_scheduler")
revisar("nucleo.canales.api" in entrypoints and "nucleo.reloj" in entrypoints,
        "el motor y el reloj estan entre los entrypoints analizados", f"{entrypoints[:5]}")
contaminados = {}
for ep in entrypoints:
    alcance = alcanzables(ep)
    toca = sorted(m for m in alcance if m == PAQUETE or m.startswith(PAQUETE + "."))
    if toca:
        contaminados[ep] = toca
revisar(not contaminados,
        f"ninguno de los {len(entrypoints)} entrypoints (motor, reloj y CLIs) importa "
        f"nucleo.programador, ni directa ni transitivamente",
        f"{contaminados}")
print(f"       analizados: {', '.join(entrypoints)}")

sal = fuentes.get("cli.salud_scheduler")
if sal:
    usa = imports_de(sal, "cli.salud_scheduler")
    texto = sal.read_text(encoding="utf-8")
    revisar(not any(fn in texto for fn in FUNCIONES_QUE_ACTUAN) and "puerta.salud" in texto,
            "la unica CLI que importa el paquete es el monitor, y solo lee job_salud")

modulos_prog = [f for m, f in fuentes.items() if m.startswith(PAQUETE)]
con_main = [f.name for f in modulos_prog if "__main__" in f.read_text(encoding="utf-8")]
revisar(not con_main,
        "ningun modulo de nucleo/programador tiene un bloque __main__ ejecutable",
        f"{con_main}")

callers_correr = []
for m, f in fuentes.items():
    if m.startswith(PAQUETE):
        continue
    t = f.read_text(encoding="utf-8")
    if re.search(r"\b(un_tick|correr)\s*\(", t) and "coordinador" in t:
        callers_correr.append(m)
revisar(not callers_correr,
        "nadie fuera del paquete llama a coordinador.correr ni a un_tick",
        f"{callers_correr}")

candidatos = [RAIZ / "Dockerfile", RAIZ / "django-crm" / "Dockerfile",
              RAIZ / "django-crm" / "docker" / "backend" / "entrypoint.sh",
              *RAIZ.glob("docker-compose*.yml"), *RAIZ.glob("*.sh")]
infra = [p for p in candidatos if p.is_file()]
menciones = {p.name: [l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines()
                      if re.search(r"programador|coordinador|un_tick|job_claim", l)]
             for p in infra}
menciones = {k: v for k, v in menciones.items() if v}
revisar(not menciones,
        f"ningun Dockerfile, compose ni script de arranque ({len(infra)} archivos) "
        f"menciona el scheduler nuevo", f"{menciones}")

# =============================================================================
titulo("3. solo el paquete llama a las funciones que actuan")
# =============================================================================
extensiones = ("*.py", "*.ts", "*.js", "*.svelte", "*.sql", "*.yml", "*.yaml")
fuera = {}
for ext in extensiones:
    for f in RAIZ.rglob(ext):
        partes = set(f.parts)
        if partes & {"node_modules", "__pycache__", ".git", ".svelte-kit", "htmlcov"}:
            continue
        rel = f.relative_to(RAIZ).as_posix()
        if rel.startswith(("nucleo/programador/", "tests/", "supabase/202609141300_scheduler_funciones.sql",
                           "supabase/ledger/")):
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Se buscan INVOCACIONES ('asistente.job_claim(' o 'job_claim(' dentro
        # de un select), no el nombre suelto: 'cli/base_desde_cero.py' lista los
        # nombres para verificar que existan, y eso no enciende nada.
        hits = [fn for fn in FUNCIONES_QUE_ACTUAN
                if re.search(rf"asistente\.{fn}\s*\(|select\s[^;]*\b{fn}\s*\(", t, re.I)]
        if hits:
            fuera[rel] = hits
revisar(not fuera,
        "ni Django, ni el frontend, ni el motor, ni ninguna CLI llaman a "
        "job_claim / jobs_vencidos / job_contexto / job_heartbeat / job_finalize",
        f"{fuera}")
urls = [f.relative_to(RAIZ).as_posix() for f in (RAIZ / "django-crm").rglob("urls.py")
        if "node_modules" not in f.parts
        and re.search(r"job_|programador|scheduler", f.read_text(encoding="utf-8", errors="replace"))]
revisar(not urls, "ninguna URL de Django toca el scheduler", f"{urls}")

# =============================================================================
titulo("4. ninguna migracion siembra un job")
# =============================================================================
siembra = []
for f in (RAIZ / "supabase").rglob("*.sql"):
    t = f.read_text(encoding="utf-8", errors="replace").lower()
    if re.search(r"insert\s+into\s+(?:asistente\.)?job_catalogo", t) or \
       re.search(r"insert\s+into\s+(?:asistente\.)?job_schedule_state", t):
        siembra.append(f.relative_to(RAIZ).as_posix())
revisar(not siembra, "ningun .sql de supabase/ inserta en job_catalogo ni en job_schedule_state",
        f"{siembra}")

# =============================================================================
titulo("5. la base construida por el ledger")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan}")
else:
    import psycopg                                                # noqa: E402
    dsn = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
           f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
           f"password={os.environ['DBPASSWORD']} sslmode=disable")
    with psycopg.connect(dsn) as con:
        cat = con.execute("select count(*) from asistente.job_catalogo").fetchone()[0]
        est = con.execute("select count(*) from asistente.job_schedule_state").fetchone()[0]
        runs = con.execute("select count(*) from asistente.job_run").fetchone()[0]
    revisar(cat == 0 and est == 0 and runs == 0,
            "job_catalogo, job_schedule_state y job_run vacios",
            f"catalogo={cat} estado={est} turnos={runs}")
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "migrar_asistente.py"), "--aplicar"],
                       capture_output=True, text=True)
    revisar(r.returncode == 0 and "0 migraciones pendientes" in r.stdout,
            "otra pasada del migrador: 0 pendientes, exit 0",
            f"exit {r.returncode}: {r.stdout[-300:]}")

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] Integrado e inerte: esta en el repo y no esta encendido.")
print("=" * 74)
