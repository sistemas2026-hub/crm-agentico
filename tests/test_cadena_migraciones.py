# -*- coding: utf-8 -*-
"""
================================================================================
 LA CADENA DE MIGRACIONES  --  las 43 adoptadas, intactas; lo nuevo, despues
================================================================================

    py -3.13 tests/test_cadena_migraciones.py          (estatico, sin base ni Docker)

POR QUE EXISTE
--------------
La adopcion del 15/09/2026 fijo en el ledger de produccion 43 archivos con su
sha256 (supabase/ledger/manifiesto_adopcion.json). Las suites del manifiesto
suponian que supabase/ tendria para siempre esos 43 (mas P2): la primera
migracion normal de Dexter (B2, 16/09/2026) las rompia por existir.

Aflojarlas a ">= 43" o ignorar lo que sobra habria perdido la garantia. Esta
suite separa las dos cosas que hay que proteger:

  CADENA ADOPTADA  exactamente los 43 del manifiesto, ni uno menos ni uno
                   distinto, cada uno con los MISMOS bytes canonicos que se
                   adoptaron (el migrador los compara contra el ledger en
                   produccion; aca se detecta antes, sin base).

  POSTERIORES      P2 y lo nuevo. Nombre con formato valido, contenido que el
                   migrador acepta, prefijo de 12 digitos unico en toda la
                   carpeta, y orden ESTRICTAMENTE posterior a todo lo ya
                   aplicado en produccion (43 + P2): una migracion con fecha
                   vieja seria un "hueco" y el migrador la rechazaria
                   (cli/migrar_asistente.py::huecos), o peor, entraria a la
                   cadena adoptada por nombre.
================================================================================
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import manifiesto_de_laboratorio as lab                             # noqa: E402
from cli import migrar_asistente as mig                             # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


NOMBRE = re.compile(r"^\d{12}_[a-z0-9_]+\.sql$")
MANIFIESTO = RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json"


def revisar_carpeta(raiz: Path) -> list[str]:
    """Todas las comprobaciones sobre una carpeta. Devuelve los fallos, para
    poder correrla tambien sobre copias mutadas."""
    problemas: list[str] = []
    carpeta = raiz / "supabase"
    todos = sorted(p.name for p in carpeta.glob("*.sql"))
    manifiesto = json.loads(MANIFIESTO.read_bytes().decode("utf-8"))["migraciones"]

    # --- cadena adoptada ---------------------------------------------------
    adopcion = lab.archivos_de_adopcion(raiz)
    if len(adopcion) != 43:
        problemas.append(f"la cadena adoptada tiene {len(adopcion)} archivos, no 43")
    if adopcion != set(manifiesto):
        problemas.append(f"la cadena adoptada no es la del manifiesto: {sorted(adopcion ^ set(manifiesto))}")
    for nombre in sorted(set(manifiesto) & set(todos)):
        try:
            sha = mig.huella((carpeta / nombre).read_bytes(), nombre)
        except mig.ContenidoNoCanonico as e:
            problemas.append(f"{nombre} ya no es canonico: {e}")
            continue
        if sha != manifiesto[nombre]["sha256"]:
            problemas.append(f"{nombre} cambio de contenido despues de adoptado")
    faltan = set(manifiesto) - set(todos)
    if faltan:
        problemas.append(f"faltan archivos adoptados: {sorted(faltan)}")

    # --- posteriores -------------------------------------------------------
    posteriores = lab.archivos_posteriores(raiz)
    if not set(lab.P2) <= set(posteriores):
        problemas.append("P2 no esta entre las posteriores")
    ya_en_produccion = max(set(manifiesto) | set(lab.P2))
    for nombre in posteriores:
        if not NOMBRE.match(nombre):
            problemas.append(f"{nombre}: nombre invalido (AAAAMMDDHHMM_descripcion.sql, minusculas)")
        if nombre in lab.P2:
            continue
        if nombre <= ya_en_produccion:
            problemas.append(f"{nombre}: ordena antes de {ya_en_produccion}, que ya esta aplicado "
                             f"en produccion (seria un hueco)")
        try:
            mig.huella((carpeta / nombre).read_bytes(), nombre)
        except mig.ContenidoNoCanonico as e:
            problemas.append(f"{nombre}: el migrador no lo aceptaria: {e}")

    prefijos: dict[str, list[str]] = {}
    for nombre in todos:
        prefijos.setdefault(nombre[:12], []).append(nombre)
    repetidos = {k: v for k, v in prefijos.items() if len(v) > 1}
    if repetidos:
        problemas.append(f"prefijos repetidos: {repetidos}")
    return problemas


print("=" * 74)
print(" LA CADENA DE MIGRACIONES")
print("=" * 74)

print("\n== el repo tal cual ==")
problemas = revisar_carpeta(RAIZ)
comprobar(problemas == [], "cadena adoptada exacta y posteriores validas", "; ".join(problemas))
print(f"          adoptadas: {len(lab.archivos_de_adopcion(RAIZ))}  "
      f"posteriores: {lab.archivos_posteriores(RAIZ)}")

# ---------------------------------------------------------------------------
# Mutaciones: cada una tiene que ser detectada. Sin esto, la suite podria
# estar en verde por no mirar nada.
# ---------------------------------------------------------------------------
import shutil      # noqa: E402
import tempfile    # noqa: E402

print("\n== mutaciones que tienen que fallar ==")


def copia() -> Path:
    destino = Path(tempfile.mkdtemp(prefix="cadena-"))
    (destino / "supabase").mkdir()
    for p in (RAIZ / "supabase").glob("*.sql"):
        shutil.copy2(p, destino / "supabase" / p.name)
    return destino


def mutacion(que: str, hacer, espera: str) -> None:
    d = copia()
    try:
        hacer(d / "supabase")
        encontrados = revisar_carpeta(d)
        comprobar(any(espera in x for x in encontrados), que, f"se esperaba '{espera}', hubo {encontrados}")
    finally:
        shutil.rmtree(d, ignore_errors=True)


una_adoptada = sorted(lab.archivos_de_adopcion(RAIZ))[5]
mutacion("borrar una adoptada",
         lambda c: (c / una_adoptada).unlink(), "faltan archivos adoptados")
mutacion("cambiar el contenido de una adoptada",
         lambda c: (c / una_adoptada).write_bytes((c / una_adoptada).read_bytes() + b"\n-- x\n"),
         "cambio de contenido")
mutacion("colar un archivo con fecha vieja (entra a la cadena por nombre)",
         lambda c: (c / "202608010000_colado.sql").write_text("select 1;\n", encoding="utf-8"),
         "no es la del manifiesto")
mutacion("migracion nueva antes de P2 (hueco en produccion)",
         lambda c: (c / "202609141250_entre_p2.sql").write_text("select 1;\n", encoding="utf-8"),
         "seria un hueco")
mutacion("migracion nueva con BOM",
         lambda c: (c / "209901010000_con_bom.sql").write_bytes(b"\xef\xbb\xbfselect 1;\n"),
         "no lo aceptaria")
mutacion("migracion nueva con nombre invalido",
         lambda c: (c / "209901010000_Mayus-cula.sql").write_text("select 1;\n", encoding="utf-8"),
         "nombre invalido")
mutacion("dos migraciones con el mismo prefijo",
         lambda c: [(c / "209901010000_a.sql").write_text("select 1;\n", encoding="utf-8"),
                    (c / "209901010000_b.sql").write_text("select 2;\n", encoding="utf-8")],
         "prefijos repetidos")

d = copia()
try:
    (d / "supabase" / "209901010000_nueva_valida.sql").write_text("select 1;\n", encoding="utf-8")
    comprobar(revisar_carpeta(d) == [], "una migracion nueva valida, despues de todo, se admite")
finally:
    shutil.rmtree(d, ignore_errors=True)

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Las 43 adoptadas siguen intactas y lo posterior entra en orden.")
