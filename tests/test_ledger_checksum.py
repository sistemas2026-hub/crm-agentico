# -*- coding: utf-8 -*-
"""
================================================================================
 EL CHECKSUM CANONICO  --  el mismo hash en Windows y en Linux, y ninguno mas
================================================================================

    py -3.13 tests/test_ledger_checksum.py          (no necesita base; Docker opcional)

Por que existe
--------------
Los 40 blobs de 'supabase/' en git no tienen BOM ni un solo CR. Un checkout en
Windows con core.autocrlf=true les pone CRLF a 39. Si el hash dependiera de los
bytes crudos, una base migrada desde un contenedor Linux y verificada desde
Windows diria que 39 migraciones "cambiaron" -- y el migrador se detendria.

La primera version resolvia eso leyendo en modo texto, que normaliza en
silencio. Tambien convierte un CR suelto en LF sin avisar. El contrato
'sha256-utf8-lf-v1' lo hace explicito (ver cli/migrar_asistente.py):

    bytes -> sin BOM -> UTF-8 estricto -> CRLF a LF -> sin CR suelto -> SHA-256

Lo que se fija
--------------
  * LF, CRLF y mezcla dan el mismo hash; un caracter distinto da otro.
  * BOM, UTF-8 invalido y CR suelto se RECHAZAN, no se normalizan.
  * El nombre del archivo no entra al hash.
  * GOLDEN: dos hashes escritos a mano, calculados sobre los blobs de git.
    Tienen que salir iguales desde el arbol de trabajo de Windows (CRLF), desde
    el blob de git (LF), y desde Python en un contenedor Linux.
  * Los 40 archivos: hash del arbol == hash del blob.
================================================================================
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cli import migrar_asistente as mig                           # noqa: E402

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


def rechaza(crudo: bytes, que: str, contiene: str):
    try:
        h = mig.huella(crudo, "prueba.sql")
        revisar(False, que, f"ACEPTO y dio {h}")
    except mig.ContenidoNoCanonico as e:
        revisar(contiene in str(e), que, f"rechazo, pero con: {e}")


# Calculados con 'git show f60beda:supabase/<archivo> | sha256sum'. Los blobs no
# tienen CR ni BOM, asi que su sha256 crudo ES el hash canonico. Escritos a mano
# a proposito: si el algoritmo cambiara en silencio, esto lo delata aunque el
# resto de las comprobaciones siguieran siendo coherentes entre si.
GOLDEN = {
    "202609070900_bandeja_sin_inflar.sql":
        "6040ebd5f6931c48f748313900b3c2b508d17697aaf1ed11148248ef29126d35",
    "202608042055_schema.sql":
        "fbd02455470619090e079800f9ce5353aeff7a320f9ce00e5b4e2e766f9c938c",
}

SQL = ("-- una migracion de prueba, con acento: año\n"
       "create table asistente.prueba (\n"
       "  a int\n"
       ");\n")
LF = SQL.encode("utf-8")
CRLF = SQL.replace("\n", "\r\n").encode("utf-8")

# =============================================================================
titulo("finales de linea")
# =============================================================================
revisar(mig.huella(LF) == mig.huella(CRLF), "LF y CRLF dan el mismo hash")
mezcla = LF.split(b"\n", 1)[0] + b"\r\n" + LF.split(b"\n", 1)[1]
revisar(mig.huella(mezcla) == mig.huella(LF), "una mezcla de LF y CRLF tambien")
revisar(mig.huella(CRLF) == hashlib.sha256(LF).hexdigest(),
        "y ese hash es el SHA-256 de los bytes en LF, sin nada mas")
revisar(mig.huella(LF.replace(b"a int", b"b int")) != mig.huella(LF),
        "cambiar UN caracter del SQL cambia el hash")
revisar(mig.huella(LF + b"\n") != mig.huella(LF),
        "una linea en blanco agregada tambien: es contenido, no formato")
revisar(mig.huella(b"") == hashlib.sha256(b"").hexdigest(),
        "un archivo vacio tiene hash (el de cero bytes), no revienta")

# =============================================================================
titulo("rechazos explicitos")
# =============================================================================
rechaza(b"\xef\xbb\xbf" + LF, "BOM UTF-8: rechazado", "BOM")
rechaza(b"create table x (a int);\n\xff\xfe\n", "UTF-8 invalido: rechazado",
        "no es UTF-8 valido")
rechaza(b"select 1;\rselect 2;\n", "CR suelto en medio: rechazado", "CR suelto")
rechaza(b"select 1;\r", "CR suelto al final: rechazado", "CR suelto")
rechaza(b"select 1;\r\r\n", "CR seguido de CRLF: rechazado (queda un CR)", "CR suelto")
try:
    mig.huella(b"a\n\nb\rc", "x.sql")
except mig.ContenidoNoCanonico as e:
    revisar("linea 3" in str(e), "el rechazo dice en que linea", str(e))

# =============================================================================
titulo("el nombre del archivo no entra al hash")
# =============================================================================
tmp = Path(tempfile.mkdtemp(prefix="checksum-"))
(tmp / "202601010000_uno.sql").write_bytes(LF)
(tmp / "202612319999_otro_nombre.sql").write_bytes(CRLF)
t1, h1 = mig.leer_migracion(tmp / "202601010000_uno.sql")
t2, h2 = mig.leer_migracion(tmp / "202612319999_otro_nombre.sql")
revisar(h1 == h2, "mismo contenido con otro nombre y otros finales: mismo hash")
revisar(t1 == t2 and "\r" not in t2,
        "y el texto que se EJECUTA es el mismo canonico, sin CR")

# =============================================================================
titulo("GOLDEN: arbol de Windows, blob de git, Python en Linux")
# =============================================================================
for nombre, esperado in GOLDEN.items():
    arbol = (RAIZ / "supabase" / nombre).read_bytes()
    blob = subprocess.run(["git", "show", f"f60beda:supabase/{nombre}"],
                          capture_output=True, cwd=str(RAIZ)).stdout
    print(f"    {nombre}: CR en el arbol={arbol.count(b'\r')}  CR en el blob={blob.count(b'\r')}")
    revisar(mig.huella(arbol, nombre) == esperado,
            f"{nombre}: el arbol de trabajo da el golden")
    revisar(mig.huella(blob, nombre) == esperado and hashlib.sha256(blob).hexdigest() == esperado,
            f"{nombre}: el blob de git da el golden, y es su sha256 crudo")

# La pregunta correcta NO es "esta docker instalado" sino "esta la imagen".
# Los dos son distintos y el 24/09/2026 costo una falsa alarma: el runner de
# GitHub Actions SI trae docker, asi que este bloque entraba y `docker run`
# fallaba por una imagen que en CI nunca se construye. El resultado era esta
# prueba en ROJO afirmando algo que no habia medido -- exactamente lo que
# "NO_VERIFICABLE != FALLO" existe para impedir, cometido por una guarda.
IMAGEN = "dexter-backend:latest"


def _hay_imagen():
    """Docker instalado Y la imagen presente. Sin las dos, no se puede medir."""
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", IMAGEN],
                          capture_output=True).returncode == 0


if _hay_imagen():
    montaje = RAIZ.as_posix()
    programa = ("import sys; sys.path.insert(0, '/repo'); "
                "from cli import migrar_asistente as m; "
                "import platform; print(platform.system()); "
                + "; ".join(f"print(m.huella(open('/repo/supabase/{n}','rb').read()))"
                            for n in GOLDEN))
    r = subprocess.run(["docker", "run", "--rm", "-v", f"{montaje}:/repo",
                        IMAGEN, "python3", "-c", programa],
                       capture_output=True, text=True)
    lineas = (r.stdout or "").split()
    revisar(r.returncode == 0 and lineas[:1] == ["Linux"],
            "Python dentro de un contenedor Linux corre el mismo codigo",
            (r.stderr or "")[-300:])
    revisar(lineas[1:] == list(GOLDEN.values()),
            "y calcula los mismos golden sobre los mismos archivos",
            f"{lineas}")
else:
    falta = "sin Docker" if not shutil.which("docker") else f"sin la imagen {IMAGEN}"
    print(f"  [saltado] {falta}: NO SE PUDO MEDIR desde Linux, que no es lo mismo que pasar")

# =============================================================================
titulo("los 40 historicos: arbol == blob")
# =============================================================================
distintos = []
total = 0
for f in sorted((RAIZ / "supabase").glob("*.sql")):
    blob = subprocess.run(["git", "show", f"HEAD:supabase/{f.name}"],
                          capture_output=True, cwd=str(RAIZ)).stdout
    if not blob:
        continue
    total += 1
    if mig.huella(f.read_bytes(), f.name) != mig.huella(blob, f.name):
        distintos.append(f.name)
revisar(total >= 40 and not distintos,
        f"los {total} archivos versionados dan el mismo hash desde el arbol y desde git",
        f"distintos: {distintos}")

shutil.rmtree(tmp, ignore_errors=True)
print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] El hash es del contenido canonico, en cualquier plataforma.")
print("=" * 74)
