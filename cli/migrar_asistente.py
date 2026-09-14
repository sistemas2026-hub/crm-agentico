# -*- coding: utf-8 -*-
"""
================================================================================
 EL MIGRADOR  --  aplica lo que falta, una vez, y lo anota
================================================================================

    py -3.13 cli/migrar_asistente.py --estado
    py -3.13 cli/migrar_asistente.py --aplicar [--espera-lock SEGUNDOS]
    py -3.13 cli/migrar_asistente.py --adoptar                (dry-run)
    py -3.13 cli/migrar_asistente.py --adoptar --escribir-baseline

Por que existe
--------------
"Aplicar las migraciones" era ejecutar los 40 archivos de 'supabase/', todos,
siempre. Medido: la segunda corrida falla (cinco 'create policy' sin guarda,
DuplicateObject 42710), un 'grant ... on all functions' de agosto alcanza
funciones de hoy, nadie sabe que quedo aplicado en una base concreta, y editar
un archivo ya aplicado no da ningun sintoma.

La respuesta no es volver idempotente cada archivo: es un registro que el
migrador respete. NINGUN ARCHIVO HISTORICO SE TOCA.

================================================================================
 CONTRATO DEL CHECKSUM  (algoritmo 'sha256-utf8-lf-v1')
================================================================================
El hash NO depende de la plataforma ni de la normalizacion implicita de Python.
Se calcula asi, en este orden, sobre el contenido y nunca sobre la ruta:

  1. leer los BYTES del archivo, sin decodificar;
  2. si empieza con EF BB BF (BOM UTF-8)          -> RECHAZO: ContenidoNoCanonico
  3. decodificar como UTF-8 estricto; si falla     -> RECHAZO: ContenidoNoCanonico
  4. reemplazar cada secuencia CR LF (0D 0A) por LF (0A);
  5. si queda algun CR (0D) suelto                 -> RECHAZO: ContenidoNoCanonico
  6. SHA-256 de esos bytes canonicos, en hex minuscula (64 caracteres).

El nombre del archivo NO entra al hash; es la clave primaria del ledger. Mover
el mismo contenido a otro nombre es otra migracion.

Por que asi, medido y no supuesto:
  * los 40 blobs versionados en git no tienen BOM ni un solo CR;
  * un checkout en Windows con core.autocrlf=true les pone CRLF a 39 de ellos.
Sin el paso 4, una base migrada desde un contenedor Linux y verificada desde
Windows diria que 39 migraciones "cambiaron". El paso 4 es explicito --antes lo
hacia en silencio el modo texto de Python, que ademas convierte un CR suelto
en LF sin avisar; eso es lo que el paso 5 impide.

Lo que se EJECUTA es exactamente el texto canonico: el mismo contenido que se
hashea. No hay una version para hashear y otra para correr.

================================================================================
 CONTRATO DEL LOCK
================================================================================
  clave        advisory lock de SESION, bigint fijo 7_242_026_091_400. Escrito a
               mano: 'hashtext' no esta documentado como estable entre versiones.
  quien espera cualquier migrador que no lo obtiene al primer intento. Reintenta
               cada 250 ms.
  cuanto       '--espera-lock', por defecto 30 s, acotado a [0, 600]. Fuera de
               ese rango: exit 2, no se conecta.
  al vencer    exit 3, SIN aplicar nada, informando quien lo tiene: pid del
               backend, usuario, application_name, desde cuando. Cada migrador
               se conecta con application_name 'migrar_asistente pid=.. host=..'
               para que esa identificacion sirva de algo.
  liberacion   en 'finally', con verificacion del valor que devuelve
               pg_advisory_unlock. Si el proceso muere --kill, OOM, red-- el
               lock de sesion lo libera PostgreSQL al cerrarse la conexion.
  muerte       con una sentencia larga en curso, un backend NO se entera de
               que su cliente murio hasta que intenta mandarle algo: sin mas,
               un migrador matado a mitad de un archivo de 10 minutos retiene
               el lock 10 minutos. La conexion fija
               client_connection_check_interval=2000, asi que el servidor lo
               detecta en <= 2 s, aborta la transaccion y suelta el lock.
               (Se suma a PGOPTIONS, no lo reemplaza.)

Codigos de salida
-----------------
  0  todo en orden (incluido "0 pendientes")
  1  una migracion fallo: se deshizo entera y no quedo anotada
  2  checksum distinto en una migracion ya aplicada, o uso invalido
  3  no se obtuvo el lock dentro de la espera
  4  un archivo no cumple el contrato canonico (BOM, UTF-8 invalido, CR suelto)
  5  hay un HUECO: una migracion pendiente anterior a otra ya anotada

================================================================================
 LOS HUECOS  --  por que '--aplicar' se niega a correr migraciones "del pasado"
================================================================================
Un archivo pendiente cuyo nombre ordena ANTES que el ultimo ya anotado no se
ejecuta. Nunca, sin bandera que lo fuerce. Dos formas de llegar a eso, y las dos
son peligrosas:

  * alguien agrego una migracion con fecha vieja despues de que otras mas
    nuevas ya corrieron: aplicarla ahora da un orden distinto al de una base
    construida desde cero;
  * una ADOPCION quedo incompleta: las migraciones que no se pudieron verificar
    --datos, SQL dinamico-- quedan pendientes entre otras ya anotadas. Si
    '--aplicar' las corriera, re-ejecutaria sobre una base existente justo lo
    que la adopcion existe para no re-ejecutar.
================================================================================
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import socket
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402

CARPETA = RAIZ / "supabase"
BOOTSTRAP = CARPETA / "ledger" / "bootstrap.sql"

ALGORITMO = "sha256-utf8-lf-v1"
CLAVE_LOCK = 7_242_026_091_400
ESPERA_MAXIMA = 600.0
REINTENTO_LOCK = 0.25

SALIDA_OK, SALIDA_FALLO, SALIDA_CHECKSUM, SALIDA_LOCK, SALIDA_CONTENIDO = 0, 1, 2, 3, 4
SALIDA_HUECO = 5


class ContenidoNoCanonico(ValueError):
    """El archivo no cumple el contrato 'sha256-utf8-lf-v1'."""


# -----------------------------------------------------------------------------
#  el checksum canonico
# -----------------------------------------------------------------------------

def bytes_canonicos(crudo: bytes, nombre: str = "<bytes>") -> bytes:
    """Los pasos 2 a 5 del contrato. Levanta ContenidoNoCanonico."""
    if crudo.startswith(b"\xef\xbb\xbf"):
        raise ContenidoNoCanonico(
            f"{nombre}: empieza con BOM UTF-8 (EF BB BF). El contrato exige "
            f"UTF-8 sin BOM.")
    try:
        crudo.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise ContenidoNoCanonico(
            f"{nombre}: no es UTF-8 valido (byte {e.start}: "
            f"{crudo[e.start:e.start + 4].hex()}).") from None
    canon = crudo.replace(b"\r\n", b"\n")
    pos = canon.find(b"\r")
    if pos != -1:
        linea = canon.count(b"\n", 0, pos) + 1
        raise ContenidoNoCanonico(
            f"{nombre}: CR suelto en la linea {linea}. Solo se admiten LF y "
            f"CRLF; un CR aislado no se normaliza porque no hay forma "
            f"inequivoca de saber que queria decir.")
    return canon


def huella(crudo: bytes, nombre: str = "<bytes>") -> str:
    return hashlib.sha256(bytes_canonicos(crudo, nombre)).hexdigest()


def leer_migracion(ruta: Path) -> tuple[str, str]:
    """(texto canonico que se ejecuta, sha256). Levanta ContenidoNoCanonico."""
    canon = bytes_canonicos(ruta.read_bytes(), ruta.name)
    return canon.decode("utf-8"), hashlib.sha256(canon).hexdigest()


def archivos(carpeta: Path | None = None) -> list[Path]:
    """Los .sql de supabase/, en orden determinista. 'ledger/' queda afuera."""
    base = carpeta or CARPETA
    return [Path(p) for p in sorted(glob.glob(str(base / "*.sql")))]


# -----------------------------------------------------------------------------
#  conexion
# -----------------------------------------------------------------------------

def nombre_de_aplicacion() -> str:
    return f"migrar_asistente pid={os.getpid()} host={socket.gethostname()}"[:63]


def conectar() -> psycopg.Connection:
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        raise SystemExit(f"[migrar] faltan {faltan} en el entorno.")
    opciones = (os.environ.get("PGOPTIONS", "")
                + " -c client_connection_check_interval=2000").strip()
    return psycopg.connect(
        host=os.environ["DBHOST"], port=os.environ["DBPORT"],
        dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
        password=os.environ["DBPASSWORD"], sslmode="disable",
        application_name=nombre_de_aplicacion(), options=opciones,
        autocommit=True)


# -----------------------------------------------------------------------------
#  el ledger
# -----------------------------------------------------------------------------

def bootstrap(con) -> None:
    texto, _ = leer_migracion(BOOTSTRAP)
    con.execute(texto)


def leer_ledger(con) -> dict[str, dict]:
    filas = con.execute(
        "select archivo, sha256, algoritmo, aplicada_en, origen, por_usuario "
        "from asistente.migraciones_aplicadas").fetchall()
    return {f[0]: {"sha256": f[1], "algoritmo": f[2], "aplicada_en": f[3],
                   "origen": f[4], "por_usuario": f[5]} for f in filas}


def plan(con, carpeta: Path | None = None):
    """
    (pendientes, discrepancias, invalidos, ledger)

    pendientes    [(ruta, texto, sha)] sin anotar
    discrepancias [(ruta, sha_anotado, sha_actual)] ya aplicadas que cambiaron
    invalidos     [(ruta, mensaje)] que no cumplen el contrato canonico
    """
    anotadas = leer_ledger(con)
    pendientes, discrepancias, invalidos = [], [], []
    for ruta in archivos(carpeta):
        try:
            texto, sha = leer_migracion(ruta)
        except ContenidoNoCanonico as e:
            invalidos.append((ruta, str(e)))
            continue
        fila = anotadas.get(ruta.name)
        if fila is None:
            pendientes.append((ruta, texto, sha))
        elif fila["sha256"] != sha:
            discrepancias.append((ruta, fila["sha256"], sha))
    return pendientes, discrepancias, invalidos, anotadas


# -----------------------------------------------------------------------------
#  el lock
# -----------------------------------------------------------------------------

def quien_tiene_el_lock(con) -> list[dict]:
    """Los backends que tienen la clave, con lo necesario para encontrarlos."""
    filas = con.execute(
        "select a.pid, a.usename, a.application_name, a.client_addr::text, "
        "       a.backend_start, a.state, a.query_start "
        "  from pg_locks l join pg_stat_activity a on a.pid = l.pid "
        " where l.locktype = 'advisory' and l.granted and l.objsubid = 1 "
        "   and ((l.classid::bigint << 32) | l.objid::bigint) = %s",
        (CLAVE_LOCK,)).fetchall()
    return [dict(zip(("pid", "usuario", "aplicacion", "cliente",
                      "conectado_desde", "estado", "consulta_desde"), f))
            for f in filas]


def tomar_lock(con, espera: float) -> bool:
    limite = time.monotonic() + espera
    primera = True
    while True:
        if con.execute("select pg_try_advisory_lock(%s)", (CLAVE_LOCK,)
                       ).fetchone()[0]:
            return True
        if primera:
            duenos = quien_tiene_el_lock(con)
            print(f"[migrar] el lock lo tiene otro migrador "
                  f"{[(d['pid'], d['aplicacion']) for d in duenos]}. "
                  f"Espero hasta {espera:.0f}s. Yo soy '{nombre_de_aplicacion()}'.",
                  flush=True)
            primera = False
        if time.monotonic() >= limite:
            return False
        time.sleep(REINTENTO_LOCK)


def soltar_lock(con) -> None:
    try:
        soltado = con.execute("select pg_advisory_unlock(%s)", (CLAVE_LOCK,)
                              ).fetchone()[0]
        if not soltado:
            print("[migrar] AVISO: pg_advisory_unlock devolvio false -- el lock "
                  "no estaba tomado por esta sesion.", flush=True)
    except psycopg.Error as e:
        # Si la conexion ya se cayo, PostgreSQL libero el lock de sesion al
        # cerrarla. No hay nada mas que hacer, pero se dice.
        print(f"[migrar] no se pudo soltar el lock explicitamente "
              f"({type(e).__name__}); se libera al cerrarse la conexion.",
              flush=True)


# -----------------------------------------------------------------------------
#  aplicar
# -----------------------------------------------------------------------------

def aplicar(con, espera: float, carpeta: Path | None = None) -> int:
    if not tomar_lock(con, espera):
        duenos = quien_tiene_el_lock(con)
        print(f"[migrar] NO se obtuvo el lock en {espera:.0f}s. No se aplico "
              f"nada.", flush=True)
        for d in duenos:
            print(f"    lo tiene: pid={d['pid']} usuario={d['usuario']} "
                  f"aplicacion='{d['aplicacion']}' cliente={d['cliente']} "
                  f"conectado_desde={d['conectado_desde']} "
                  f"estado={d['estado']}", flush=True)
        if not duenos:
            print("    (el dueño solto el lock justo al vencer la espera: "
                  "reintentar)", flush=True)
        return SALIDA_LOCK

    try:
        pendientes, discrepancias, invalidos, anotadas = plan(con, carpeta)

        if invalidos:
            print("[migrar] HAY ARCHIVOS QUE NO CUMPLEN EL CONTRATO CANONICO. "
                  "No se aplica nada.", flush=True)
            for ruta, msg in invalidos:
                print(f"    {msg}", flush=True)
            return SALIDA_CONTENIDO

        if discrepancias:
            print("[migrar] HAY ARCHIVOS APLICADOS QUE CAMBIARON. No se "
                  "aplica nada.", flush=True)
            for ruta, viejo, nuevo in discrepancias:
                print(f"    {ruta.name}\n        anotado: {viejo}\n"
                      f"        ahora:   {nuevo}", flush=True)
            print("  Una migracion ya aplicada es historia, no un archivo "
                  "editable. Si el cambio es correcto, va en una migracion "
                  "nueva.", flush=True)
            return SALIDA_CHECKSUM

        if not pendientes:
            print("[migrar] 0 migraciones pendientes.", flush=True)
            return SALIDA_OK

        huecos_ = huecos(pendientes, anotadas)
        if huecos_:
            print("[migrar] HAY MIGRACIONES PENDIENTES ANTERIORES A OTRAS YA "
                  "ANOTADAS. No se aplica nada.", flush=True)
            for ruta in huecos_:
                print(f"    {ruta.name}", flush=True)
            print(f"  ultima anotada: {max(anotadas)}. Ver 'LOS HUECOS' en el "
                  f"docstring: se resuelven con --adoptar, no con --aplicar.",
                  flush=True)
            return SALIDA_HUECO

        print(f"[migrar] {len(pendientes)} pendiente(s):", flush=True)
        for ruta, texto, sha in pendientes:
            t0 = time.monotonic()
            try:
                with con.transaction():
                    con.execute(texto)
                    con.execute(
                        "insert into asistente.migraciones_aplicadas "
                        "(archivo, sha256, algoritmo, duro_ms, origen) "
                        "values (%s,%s,%s,%s,'aplicada')",
                        (ruta.name, sha, ALGORITMO,
                         int((time.monotonic() - t0) * 1000)))
            except Exception as e:                               # noqa: BLE001
                print(f"  [FALLA] {ruta.name}: {type(e).__name__}: "
                      f"{str(e).splitlines()[0][:160] if str(e) else ''}",
                      flush=True)
                print("  La migracion se deshizo entera y NO quedo anotada. "
                      "Las anteriores si.", flush=True)
                return SALIDA_FALLO
            print(f"  [ok] {ruta.name}  ({int((time.monotonic() - t0) * 1000)} ms)",
                  flush=True)
        print(f"[migrar] {len(pendientes)} aplicada(s).", flush=True)
        return SALIDA_OK
    finally:
        soltar_lock(con)


def huecos(pendientes, anotadas) -> list[Path]:
    if not anotadas:
        return []
    ultima = max(anotadas)
    return [ruta for ruta, _t, _s in pendientes if ruta.name < ultima]


def estado(con) -> int:
    pendientes, discrepancias, invalidos, anotadas = plan(con)
    print(f"  algoritmo             : {ALGORITMO}")
    print(f"  archivos en supabase/ : {len(archivos())}")
    print(f"  anotados en el ledger : {len(anotadas)}")
    print(f"  pendientes            : {len(pendientes)}")
    print(f"  con checksum distinto : {len(discrepancias)}")
    print(f"  no canonicos          : {len(invalidos)}")
    for ruta, _, _ in pendientes:
        print(f"    pendiente: {ruta.name}")
    for ruta, viejo, nuevo in discrepancias:
        print(f"    CAMBIO: {ruta.name}: {viejo[:12]}... -> {nuevo[:12]}...")
    for ruta, msg in invalidos:
        print(f"    NO CANONICO: {msg}")
    for ruta in huecos(pendientes, anotadas):
        print(f"    HUECO: {ruta.name}")
    # Informativo, no cambia el codigo de salida: una migracion aplicada cuyo
    # archivo ya no esta en esta carpeta. Pasa al cambiar de rama; si pasa en
    # la rama desplegada, alguien borro historia.
    en_carpeta = {r.name for r in archivos()}
    sin_archivo = sorted(set(anotadas) - en_carpeta)
    print(f"  anotadas sin archivo  : {len(sin_archivo)}")
    for nombre in sin_archivo:
        print(f"    ANOTADA SIN ARCHIVO: {nombre}")
    if invalidos:
        return SALIDA_CONTENIDO
    if discrepancias:
        return SALIDA_CHECKSUM
    return SALIDA_OK if not pendientes else SALIDA_FALLO


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--estado", action="store_true")
    g.add_argument("--aplicar", action="store_true")
    g.add_argument("--adoptar", action="store_true")
    p.add_argument("--escribir-baseline", action="store_true",
                   help="con --adoptar: escribe de verdad. Sin esto, dry-run.")
    p.add_argument("--aceptar", metavar="ARCHIVO",
                   help="con --adoptar: aceptacion humana de UNA migracion")
    p.add_argument("--motivo", help="obligatorio con --aceptar")
    p.add_argument("--espera-lock", type=float, default=30.0,
                   help=f"segundos, entre 0 y {ESPERA_MAXIMA:.0f}")
    a = p.parse_args(argv)

    if not 0 <= a.espera_lock <= ESPERA_MAXIMA:
        print(f"[migrar] --espera-lock tiene que estar entre 0 y "
              f"{ESPERA_MAXIMA:.0f} segundos; vino {a.espera_lock}.")
        return SALIDA_CHECKSUM

    con = conectar()
    try:
        bootstrap(con)
        if a.estado:
            return estado(con)
        if a.aplicar:
            return aplicar(con, a.espera_lock)
        from cli import manifiesto_adopcion                     # noqa: E402
        return manifiesto_adopcion.adoptar(con, a.escribir_baseline,
                                           a.espera_lock, a.aceptar, a.motivo)
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
