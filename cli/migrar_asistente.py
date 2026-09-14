# -*- coding: utf-8 -*-
"""
================================================================================
 EL MIGRADOR  --  aplica lo que falta, una vez, y lo anota
================================================================================

    py -3.13 cli/migrar_asistente.py --estado
    py -3.13 cli/migrar_asistente.py --aplicar
    py -3.13 cli/migrar_asistente.py --adoptar              (dry-run)
    py -3.13 cli/migrar_asistente.py --adoptar --escribir-baseline

Por que existe
--------------
"Aplicar las migraciones" era ejecutar los 40 archivos de 'supabase/', todos,
siempre. Eso tiene cuatro consecuencias y las cuatro se midieron:

  1. La SEGUNDA corrida falla. Cinco archivos hacen 'create policy' sin guarda
     y chocan con DuplicateObject (42710). Un despliegue que solo funciona
     sobre una base virgen no es un despliegue repetible.

  2. Un 'grant execute on all functions in schema asistente to app_backend'
     escrito el 11/08/2026 se vuelve a ejecutar hoy, y alcanza funciones que no
     existian cuando se escribio. Medido: las diez funciones del scheduler
     quedaban ejecutables por app_backend despues de una segunda pasada.

  3. Nadie puede decir que quedo aplicado en una base concreta.

  4. Editar un archivo ya aplicado no produce ningun sintoma.

La respuesta NO es volver idempotente cada archivo. Eso arregla el sintoma una
vez por archivo y deja el problema para el archivo siguiente. La respuesta es
que haya un registro y que el migrador lo respete.

NINGUN ARCHIVO HISTORICO SE TOCA. Los 40 quedan como estan, byte a byte; dejan
de re-ejecutarse porque el migrador los saltea.

Las garantias, una por una
--------------------------
  orden               por nombre de archivo, que en este repo es la fecha
  una transaccion     por archivo. Si falla, se deshace ESE archivo y no se
                      anota; los anteriores quedan aplicados y anotados
  un solo migrador    advisory lock de sesion sobre una clave fija
  no reejecuta        lo que esta en el ledger no se vuelve a correr
  checksum            si el contenido cambio desde que se aplico, se detiene
                      ANTES de tocar nada
  bootstrap           crea el schema y el ledger si no estan

Lo que este comando NO hace
---------------------------
No baja migraciones, no borra nada, no toca produccion sin que se lo pidan con
un host explicito, y no marca nada como aplicado por su cuenta: adoptar una
base que ya tiene el esquema exige '--escribir-baseline' y solo escribe lo que
pudo VERIFICAR contra el catalogo.
================================================================================
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import io
import os
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402

CARPETA = RAIZ / "supabase"
BOOTSTRAP = CARPETA / "ledger" / "bootstrap.sql"

# La clave del advisory lock. Es un numero fijo escrito a mano, no
# 'hashtext(...)': hashtext no esta documentado como estable entre versiones de
# PostgreSQL, y una clave que cambia con un upgrade deja de excluir justo
# cuando hay dos migradores porque alguien esta desplegando durante un upgrade.
CLAVE_LOCK = 7_242_026_091_400


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def archivos() -> list[Path]:
    """Los .sql de supabase/, en orden determinista. 'ledger/' queda afuera."""
    return [Path(p) for p in sorted(glob.glob(str(CARPETA / "*.sql")))]


def dsn_de_entorno() -> str:
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        raise SystemExit(f"[migrar] faltan {faltan} en el entorno.")
    return (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
            f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
            f"password={os.environ['DBPASSWORD']} sslmode=disable")


# -----------------------------------------------------------------------------
#  el ledger
# -----------------------------------------------------------------------------

def bootstrap(con) -> None:
    """Crea el schema y la tabla del ledger. Idempotente por construccion."""
    con.execute(io.open(BOOTSTRAP, encoding="utf-8").read())


def leer_ledger(con) -> dict[str, dict]:
    filas = con.execute(
        "select archivo, sha256, aplicada_en, origen, por_usuario "
        "from asistente.migraciones_aplicadas").fetchall()
    return {f[0]: {"sha256": f[1], "aplicada_en": f[2], "origen": f[3],
                   "por_usuario": f[4]} for f in filas}


def plan(con) -> tuple[list[Path], list[tuple[Path, str, str]], dict]:
    """
    Devuelve (pendientes, discrepancias, ledger).

    'discrepancias' son archivos anotados cuyo contenido YA NO coincide con el
    hash con que se aplicaron. Es un error, no una advertencia: significa que
    dos bases que dicen tener la misma migracion tienen cosas distintas.
    """
    anotadas = leer_ledger(con)
    pendientes, discrepancias = [], []
    for a in archivos():
        h = sha256(io.open(a, encoding="utf-8").read())
        if a.name not in anotadas:
            pendientes.append(a)
        elif anotadas[a.name]["sha256"] != h:
            discrepancias.append((a, anotadas[a.name]["sha256"], h))
    return pendientes, discrepancias, anotadas


# -----------------------------------------------------------------------------
#  aplicar
# -----------------------------------------------------------------------------

def aplicar(con, espera_lock: float) -> int:
    # El lock se toma ANTES de leer el plan: leer sin lock y aplicar despues
    # es exactamente la carrera que el lock existe para impedir.
    tomado = con.execute("select pg_try_advisory_lock(%s) as ok",
                         (CLAVE_LOCK,)).fetchone()[0]
    if not tomado:
        print(f"[migrar] otro migrador tiene el lock. Esperando hasta "
              f"{espera_lock:.0f}s y despues verifico el resultado.")
        limite = time.monotonic() + espera_lock
        while time.monotonic() < limite:
            time.sleep(0.2)
            tomado = con.execute("select pg_try_advisory_lock(%s) as ok",
                                 (CLAVE_LOCK,)).fetchone()[0]
            if tomado:
                break
        if not tomado:
            print("[migrar] el otro migrador sigue trabajando. No aplico nada.")
            return 3

    try:
        pendientes, discrepancias, _ = plan(con)

        if discrepancias:
            # Antes de tocar NADA. Un archivo que cambio despues de aplicado
            # significa que esta base y otra que corrio 'la misma' migracion
            # tienen cosas distintas, y no hay forma automatica de saber cual
            # es la buena.
            print("[migrar] HAY ARCHIVOS APLICADOS QUE CAMBIARON. No se "
                  "aplica nada.")
            for a, viejo, nuevo in discrepancias:
                print(f"    {a.name}")
                print(f"        anotado: {viejo}")
                print(f"        ahora:   {nuevo}")
            print("  Una migracion ya aplicada es historia, no un archivo "
                  "editable. Si el cambio es correcto, va en una migracion "
                  "nueva.")
            return 2

        if not pendientes:
            print("[migrar] 0 migraciones pendientes.")
            return 0

        print(f"[migrar] {len(pendientes)} pendiente(s):")
        for a in pendientes:
            texto = io.open(a, encoding="utf-8").read()
            h = sha256(texto)
            t0 = time.monotonic()
            try:
                # Una transaccion por archivo: si revienta, se deshace ESTE y
                # los anteriores quedan aplicados y anotados.
                with con.transaction():
                    con.execute(texto)
                    con.execute(
                        "insert into asistente.migraciones_aplicadas "
                        "(archivo, sha256, duro_ms, origen) "
                        "values (%s,%s,%s,'aplicada')",
                        (a.name, h, int((time.monotonic() - t0) * 1000)))
            except Exception as e:                               # noqa: BLE001
                print(f"  [FALLA] {a.name}: {type(e).__name__}: "
                      f"{str(e).splitlines()[0][:160]}")
                print("  La migracion se deshizo entera y NO quedo anotada. "
                      "Las anteriores si.")
                return 1
            print(f"  [ok] {a.name}  ({int((time.monotonic() - t0) * 1000)} ms)")
        print(f"[migrar] {len(pendientes)} aplicada(s).")
        return 0
    finally:
        con.execute("select pg_advisory_unlock(%s)", (CLAVE_LOCK,))


# -----------------------------------------------------------------------------
#  adoptar una base que ya tiene el esquema
# -----------------------------------------------------------------------------
# Lo que NO vale como evidencia: "el archivo corrio sin error". Muchos de estos
# archivos son idempotentes por accidente --'create table if not exists'-- y
# correrlos de nuevo no prueba que su contenido este aplicado, solo que no
# rompieron. Aca se miran los OBJETOS que el archivo declara, contra el
# catalogo.

_TABLA = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
                    r"asistente\.([a-z0-9_]+)", re.I)
_FUNCION = re.compile(r"create\s+(?:or\s+replace\s+)?function\s+"
                      r"asistente\.([a-z0-9_]+)", re.I)
_COLUMNA = re.compile(r"alter\s+table\s+(?:if\s+exists\s+)?asistente\."
                      r"([a-z0-9_]+)\s+add\s+column\s+(?:if\s+not\s+exists\s+)?"
                      r"([a-z0-9_]+)", re.I)
_INDICE = re.compile(r"create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
                     r"(?:if\s+not\s+exists\s+)?([a-z0-9_]+)", re.I)


def objetos_declarados(texto: str) -> dict[str, list]:
    return {
        "tablas": sorted(set(_TABLA.findall(texto))),
        "funciones": sorted(set(_FUNCION.findall(texto))),
        "columnas": sorted(set(_COLUMNA.findall(texto))),
        "indices": sorted(set(_INDICE.findall(texto))),
    }


def verificar_presente(con, decl: dict) -> tuple[bool, list[str]]:
    """True si TODO lo declarado existe. Devuelve lo que falta."""
    faltan: list[str] = []
    for t in decl["tablas"]:
        if not con.execute("select to_regclass(%s) is not null as hay",
                           (f"asistente.{t}",)).fetchone()[0]:
            faltan.append(f"tabla {t}")
    for f in decl["funciones"]:
        if not con.execute(
                "select exists(select 1 from pg_proc p join pg_namespace n "
                "on n.oid=p.pronamespace where n.nspname='asistente' "
                "and p.proname=%s) as hay", (f,)).fetchone()[0]:
            faltan.append(f"funcion {f}")
    for tabla, col in decl["columnas"]:
        if not con.execute(
                "select exists(select 1 from information_schema.columns "
                "where table_schema='asistente' and table_name=%s "
                "and column_name=%s) as hay", (tabla, col)).fetchone()[0]:
            faltan.append(f"columna {tabla}.{col}")
    for i in decl["indices"]:
        if not con.execute(
                "select exists(select 1 from pg_indexes where "
                "schemaname='asistente' and indexname=%s) as hay",
                (i,)).fetchone()[0]:
            faltan.append(f"indice {i}")
    return (not faltan), faltan


def adoptar(con, escribir: bool) -> int:
    pendientes, discrepancias, _ = plan(con)
    if discrepancias:
        print("[migrar] hay archivos aplicados que cambiaron; resolvelo antes "
              "de adoptar.")
        return 2
    if not pendientes:
        print("[migrar] no hay nada que adoptar: el ledger ya esta completo.")
        return 0

    verificados: list[tuple[Path, str]] = []
    ausentes: list[tuple[Path, list[str]]] = []
    sin_verificar: list[Path] = []

    print(f"[migrar] {len(pendientes)} archivo(s) sin anotar. Verificando "
          f"contra el catalogo:\n")
    for a in pendientes:
        texto = io.open(a, encoding="utf-8").read()
        decl = objetos_declarados(texto)
        total = sum(len(v) for v in decl.values())
        if total == 0:
            # No declara ningun objeto que se pueda buscar: son los archivos
            # que solo hacen GRANT, ALTER POLICY, UPDATE de datos. No se puede
            # decidir automaticamente y NO se marca.
            sin_verificar.append(a)
            print(f"  [NO VERIFICABLE] {a.name}")
            print(f"      no declara tablas, funciones, columnas ni indices "
                  f"que se puedan buscar en el catalogo")
            continue
        ok, faltan = verificar_presente(con, decl)
        if ok:
            resumen = ", ".join(
                f"{len(v)} {k}" for k, v in decl.items() if v)
            verificados.append((a, resumen))
            print(f"  [PRESENTE] {a.name}  ({resumen})")
        else:
            ausentes.append((a, faltan))
            print(f"  [AUSENTE] {a.name}")
            for f in faltan[:5]:
                print(f"      falta {f}")

    print(f"\n  presentes y verificables : {len(verificados)}")
    print(f"  ausentes                 : {len(ausentes)}")
    print(f"  NO verificables          : {len(sin_verificar)}")

    if ausentes:
        print("\n[migrar] hay archivos cuyos objetos NO estan en la base. Esa "
              "base no tiene el esquema completo: no es candidata a baseline, "
              "hay que aplicarlos con --aplicar.")
        return 1

    if sin_verificar:
        print("\n[migrar] los NO verificables quedan sin decidir. No se "
              "marcan solos: un archivo que solo hace GRANT no deja rastro "
              "que se pueda buscar, y darlo por aplicado 'porque los demas lo "
              "estan' es adivinar. Requieren decision humana archivo por "
              "archivo.")

    if not escribir:
        print("\n[migrar] DRY-RUN: no se escribio nada. Para anotar los "
              f"{len(verificados)} verificados, repetir con "
              f"--escribir-baseline.")
        return 0

    tomado = con.execute("select pg_try_advisory_lock(%s) as ok",
                         (CLAVE_LOCK,)).fetchone()[0]
    if not tomado:
        print("[migrar] otro migrador tiene el lock. No se escribe baseline.")
        return 3
    try:
        with con.transaction():
            for a, resumen in verificados:
                texto = io.open(a, encoding="utf-8").read()
                con.execute(
                    "insert into asistente.migraciones_aplicadas "
                    "(archivo, sha256, duro_ms, origen, nota) "
                    "values (%s,%s,0,'baseline',%s)",
                    (a.name, sha256(texto),
                     f"adoptada: verificado en el catalogo ({resumen})"))
        print(f"\n[migrar] {len(verificados)} archivo(s) anotados como "
              f"baseline.")
        if sin_verificar:
            print(f"  Quedan {len(sin_verificar)} SIN anotar, a la espera de "
                  f"una decision humana:")
            for a in sin_verificar:
                print(f"    {a.name}")
        return 0
    finally:
        con.execute("select pg_advisory_unlock(%s)", (CLAVE_LOCK,))


# -----------------------------------------------------------------------------

def estado(con) -> int:
    pendientes, discrepancias, anotadas = plan(con)
    print(f"  archivos en supabase/ : {len(archivos())}")
    print(f"  anotados en el ledger : {len(anotadas)}")
    print(f"  pendientes            : {len(pendientes)}")
    print(f"  con checksum distinto : {len(discrepancias)}")
    if pendientes:
        print("\n  pendientes:")
        for a in pendientes:
            print(f"    {a.name}")
    if discrepancias:
        print("\n  CAMBIARON DESPUES DE APLICADOS:")
        for a, viejo, nuevo in discrepancias:
            print(f"    {a.name}: {viejo[:12]}... -> {nuevo[:12]}...")
        return 2
    return 0 if not pendientes else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--estado", action="store_true")
    g.add_argument("--aplicar", action="store_true")
    g.add_argument("--adoptar", action="store_true")
    p.add_argument("--escribir-baseline", action="store_true",
                   help="con --adoptar: escribe de verdad. Sin esto, dry-run.")
    p.add_argument("--espera-lock", type=float, default=30.0)
    a = p.parse_args(argv)

    con = psycopg.connect(dsn_de_entorno(), autocommit=True)
    try:
        bootstrap(con)
        if a.estado:
            return estado(con)
        if a.aplicar:
            return aplicar(con, a.espera_lock)
        return adoptar(con, a.escribir_baseline)
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
