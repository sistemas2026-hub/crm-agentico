# -*- coding: utf-8 -*-
"""
================================================================================
 EL MIGRADOR  --  aplica lo que falta, una vez, y lo anota
================================================================================

    py -3.13 cli/migrar_asistente.py --estado                     (solo lectura)
    py -3.13 cli/migrar_asistente.py --aplicar [--espera-lock SEGUNDOS]
    py -3.13 cli/migrar_asistente.py --adoptar                    (solo lectura)
    py -3.13 cli/migrar_asistente.py --adoptar --escribir-baseline
    py -3.13 cli/migrar_asistente.py --adoptar --aceptar ARCHIVO --motivo TEXTO \\
        --autorizado-por QUIEN

Por que existe
--------------
"Aplicar las migraciones" era ejecutar los 40 archivos de 'supabase/', todos,
siempre. Medido: la segunda corrida falla (cinco 'create policy' sin guarda,
DuplicateObject 42710), un 'grant ... on all functions' de agosto alcanza
funciones de hoy, nadie sabe que quedo aplicado en una base concreta, y editar
un archivo ya aplicado no da ningun sintoma.

La respuesta no es volver idempotente cada archivo: es un registro que el
migrador respete. NINGUN ARCHIVO HISTORICO SE TOCA.

Este es el UNICO camino que escribe migraciones de 'supabase/'. 'cli/migraciones.py'
es informativo y su '--aplicar' se niega; 'cli/base_desde_cero.py' delega aca.
El inventario de rutas esta en supabase/ledger/analisis/INVENTARIO_RUTAS_SQL.md.

================================================================================
 CONTRATO DEL CHECKSUM  (algoritmo 'sha256-utf8-lf-v1')
================================================================================
  1. leer los BYTES del archivo, sin decodificar;
  2. si empieza con EF BB BF (BOM UTF-8)          -> RECHAZO: ContenidoNoCanonico
  3. decodificar como UTF-8 estricto; si falla     -> RECHAZO: ContenidoNoCanonico
  4. reemplazar cada secuencia CR LF (0D 0A) por LF (0A);
  5. si queda algun CR (0D) suelto                 -> RECHAZO: ContenidoNoCanonico
  6. SHA-256 de esos bytes canonicos, en hex minuscula (64 caracteres).

El nombre del archivo NO entra al hash; es la clave primaria del ledger. Lo que
se EJECUTA es exactamente el texto canonico que se hashea.

================================================================================
 LA SECCION SERIALIZADA
================================================================================
Todo lo que escribe --crear el ledger, decidir que falta, verificar una
adopcion, ejecutar un archivo, anotar una fila-- ocurre DENTRO de una unica
seccion protegida por un advisory lock de sesion, tomado UNA vez:

    lock -> base existente sin ledger? -> esquema del ledger -> plan
         -> (aplicar | verificar + anotar) -> soltar

Antes del lock no hay CREATE, ALTER, DROP ni INSERT. Una espera vencida no deja
ningun rastro: ni el schema 'asistente' se crea.

  clave        bigint fijo 7_242_026_091_400 ('hashtext' no esta documentado
               como estable entre versiones).
  espera       '--espera-lock', por defecto 30 s, acotado a [0, 600]. Fuera de
               ese rango: exit 2, sin conectarse.
  al vencer    exit 3, nombrando al dueño: pid, usuario, application_name.
  reentrada    PROHIBIDA. Los advisory locks de sesion cuentan: tomarlo dos
               veces y soltarlo una deja la sesion con el lock. Entrar a la
               seccion teniendolo ya levanta LockReentrante.
  liberacion   en 'finally', verificando que la sesion ya no lo tiene. Si el
               proceso muere, PostgreSQL lo suelta al cerrar la conexion; con
               client_connection_check_interval=2000 el servidor lo detecta en
               <= 2 s aunque este en medio de una sentencia larga.

Lo que el lock NO cubre: DDL hecho a mano por alguien que no pasa por este
migrador. Serializa migradores, no personas con psql.

================================================================================
 EL ESQUEMA DEL LEDGER, VERSIONADO
================================================================================
Las tablas del ledger se crean con los pasos de 'supabase/ledger/esquema/', en
orden, cada uno en su transaccion y anotado en
'asistente.migraciones_ledger_esquema'. Un paso ya anotado no se vuelve a
ejecutar: un comando normal no hace DROP ni ADD de nada.

  0001  las dos tablas.
  0002  'evidencia' (jsonb) en cada fila adoptada: manifiesto, servidor,
        comprobaciones y quien DECLARO autorizar. Un ledger v1 que ya tiene
        filas adoptadas no se actualiza (exit 8): no se fabrica evidencia.
  0003  solo agregar: UPDATE, DELETE y TRUNCATE sobre las dos tablas fallan
        (SQLSTATE LG002). Contra errores operativos, no contra el owner.
Detalle: supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md.

================================================================================
 CODIGOS DE SALIDA
================================================================================
  0  todo en orden (incluido "0 pendientes")
  1  una migracion fallo (deshecha, no anotada) / adopcion no equivalente
  2  checksum distinto en una migracion aplicada, o uso invalido
  3  no se obtuvo el lock dentro de la espera
  4  un archivo no cumple el contrato canonico
  5  HUECO: una migracion pendiente anterior a otra ya anotada
  6  base EXISTENTE sin ledger: hay que adoptarla, no aplicarle migraciones
  7  la huella del servidor (version mayor, extensiones) no es la del manifiesto
  8  el esquema del ledger no se puede actualizar sin una decision (nada cambio)
================================================================================
"""

from __future__ import annotations

import argparse
import contextlib
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
ESQUEMA_LEDGER = CARPETA / "ledger" / "esquema"

ALGORITMO = "sha256-utf8-lf-v1"
CLAVE_LOCK = 7_242_026_091_400
ESPERA_MAXIMA = 600.0
REINTENTO_LOCK = 0.25
TABLAS_DEL_LEDGER = ("migraciones_aplicadas", "migraciones_ledger_esquema")

SALIDA_OK, SALIDA_FALLO, SALIDA_CHECKSUM, SALIDA_LOCK, SALIDA_CONTENIDO = 0, 1, 2, 3, 4
SALIDA_HUECO, SALIDA_BASE_EXISTENTE, SALIDA_HUELLA, SALIDA_LEDGER = 5, 6, 7, 8

# Los que levantan los pasos de supabase/ledger/esquema/.
SQLSTATE_LEDGER_NO_ACTUALIZABLE = "LG001"
SQLSTATE_SOLO_AGREGAR = "LG002"


class ContenidoNoCanonico(ValueError):
    """El archivo no cumple el contrato 'sha256-utf8-lf-v1'."""


class LockReentrante(RuntimeError):
    """Se intento entrar a la seccion serializada teniendo ya el lock."""


class LockNoObtenido(RuntimeError):
    def __init__(self, espera: float, duenos: list[dict]):
        super().__init__(f"no se obtuvo el lock en {espera:.0f}s")
        self.espera = espera
        self.duenos = duenos


class LedgerNoActualizable(RuntimeError):
    """Un paso del esquema del ledger se nego (SQLSTATE LG001). No cambio nada."""


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
#  lectura, sin mutar nada
# -----------------------------------------------------------------------------

def ledger_existe(con) -> bool:
    return con.execute("select to_regclass('asistente.migraciones_aplicadas') "
                       "is not null").fetchone()[0]


def version_del_ledger(con) -> int:
    if not con.execute("select to_regclass('asistente.migraciones_ledger_esquema') "
                       "is not null").fetchone()[0]:
        return 0
    return con.execute("select coalesce(max(version), 0) from "
                       "asistente.migraciones_ledger_esquema").fetchone()[0]


def leer_ledger(con) -> dict[str, dict]:
    if not ledger_existe(con):
        return {}
    filas = con.execute(
        "select archivo, sha256, aplicada_en, origen, por_usuario "
        "from asistente.migraciones_aplicadas").fetchall()
    return {f[0]: {"sha256": f[1], "aplicada_en": f[2], "origen": f[3],
                   "por_usuario": f[4]} for f in filas}


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


def huecos(pendientes, anotadas) -> list[Path]:
    if not anotadas:
        return []
    ultima = max(anotadas)
    return [ruta for ruta, _t, _s in pendientes if ruta.name < ultima]


def tablas_sin_ledger(con) -> list[str]:
    """
    Relaciones de 'asistente' que no son del ledger, cuando el ledger no tiene
    ninguna fila. Si hay alguna, esta base ya tiene el esquema --se construyo a
    mano o con la herramienta vieja-- y aplicarle los archivos historicos es
    exactamente lo que la adopcion existe para evitar.
    """
    if leer_ledger(con):
        return []
    return [f[0] for f in con.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'asistente' and c.relkind in ('r','p','v','m') "
        "and c.relname <> all(%s) order by 1", (list(TABLAS_DEL_LEDGER),)).fetchall()]


def huella_servidor(con) -> dict:
    """La version mayor de PostgreSQL y cada extension instalada (sin plpgsql)."""
    num = int(con.execute("show server_version_num").fetchone()[0])
    extensiones = {
        f[0]: {"version": f[1], "schema": f[2]}
        for f in con.execute(
            "select e.extname, e.extversion, n.nspname from pg_extension e "
            "join pg_namespace n on n.oid = e.extnamespace "
            "where e.extname <> 'plpgsql' order by 1").fetchall()}
    return {"server_version_num": num, "major": num // 10000,
            "extensiones": extensiones}


def comparar_huella(esperada: dict, actual: dict) -> list[str]:
    """
    Lo que impide comparar definiciones de catalogo. Una extension de MAS en la
    base adoptada no bloquea (Supabase trae muchas); una que falta, o con otra
    version u otro schema, si.
    """
    malas: list[str] = []
    if esperada.get("major") != actual.get("major"):
        malas.append(f"PostgreSQL mayor: manifiesto {esperada.get('major')}, "
                     f"servidor {actual.get('major')}")
    for nombre, esp in sorted(esperada.get("extensiones", {}).items()):
        act = actual.get("extensiones", {}).get(nombre)
        if act is None:
            malas.append(f"extension {nombre}: falta en el servidor")
            continue
        if act["version"] != esp["version"]:
            malas.append(f"extension {nombre}: version manifiesto {esp['version']}, "
                         f"servidor {act['version']}")
        if act["schema"] != esp["schema"]:
            malas.append(f"extension {nombre}: schema manifiesto {esp['schema']}, "
                         f"servidor {act['schema']}")
    return malas


# -----------------------------------------------------------------------------
#  el lock y la seccion
# -----------------------------------------------------------------------------

def quien_tiene_el_lock(con) -> list[dict]:
    filas = con.execute(
        "select a.pid, a.usename, a.application_name, a.client_addr::text, "
        "       a.backend_start, a.state "
        "  from pg_locks l join pg_stat_activity a on a.pid = l.pid "
        " where l.locktype = 'advisory' and l.granted and l.objsubid = 1 "
        "   and ((l.classid::bigint << 32) | l.objid::bigint) = %s",
        (CLAVE_LOCK,)).fetchall()
    return [dict(zip(("pid", "usuario", "aplicacion", "cliente",
                      "conectado_desde", "estado"), f)) for f in filas]


def tengo_el_lock(con) -> bool:
    return con.execute(
        "select exists(select 1 from pg_locks where locktype = 'advisory' "
        "and granted and objsubid = 1 and pid = pg_backend_pid() "
        "and ((classid::bigint << 32) | objid::bigint) = %s)",
        (CLAVE_LOCK,)).fetchone()[0]


# -----------------------------------------------------------------------------
#  gancho de PRUEBA para forzar interleavings
# -----------------------------------------------------------------------------
# Las carreras entre dos migradores no se pueden probar confiando en el
# scheduler del sistema operativo: una corrida observa un orden y el otro queda
# sin ejercitar. Este gancho deja que una prueba FUERCE el orden.
#
# Inerte salvo que se cumplan las dos condiciones:
#   * MIGRAR_PRUEBA_DIR apunta a un directorio existente, y
#   * DBHOST es un host local (una variable perdida en produccion no puede
#     colgar un despliegue).
# Con eso registra en <dir>/orden.log cada 'espera' y cada 'lock' con el pid, y
# si ademas MIGRAR_PRUEBA_PAUSA=1, al obtener el lock crea <dir>/pausa_<pid>.dentro
# y espera a que exista <dir>/pausa_<pid>.seguir (hasta 120 s) antes de seguir.

_HOSTS_DE_PRUEBA = {"localhost", "127.0.0.1", "host.docker.internal"}


def _dir_de_prueba() -> Path | None:
    d = os.environ.get("MIGRAR_PRUEBA_DIR")
    if not d or os.environ.get("DBHOST") not in _HOSTS_DE_PRUEBA:
        return None
    p = Path(d)
    return p if p.is_dir() else None


def _gancho(evento: str) -> None:
    d = _dir_de_prueba()
    if d is None:
        return
    with open(d / "orden.log", "a", encoding="utf-8") as f:
        f.write(f"{time.time_ns()} {os.getpid()} {evento}\n")
    if evento == "lock" and os.environ.get("MIGRAR_PRUEBA_PAUSA") == "1":
        (d / f"pausa_{os.getpid()}.dentro").write_text("", encoding="utf-8")
        limite = time.monotonic() + 120
        while not (d / f"pausa_{os.getpid()}.seguir").exists():
            if time.monotonic() >= limite:
                raise RuntimeError("gancho de prueba: nunca llego la señal para seguir")
            time.sleep(0.02)


@contextlib.contextmanager
def seccion_serializada(con, espera: float):
    """
    La unica forma de escribir. Toma el lock una vez, y lo suelta al salir pase
    lo que pase. Levanta LockReentrante si la sesion ya lo tenia y
    LockNoObtenido si vence la espera -- en ese caso no se hizo NADA.
    """
    if tengo_el_lock(con):
        raise LockReentrante(
            "la sesion ya tiene el lock del migrador: entrar de nuevo lo dejaria "
            "tomado dos veces y un solo 'unlock' no lo soltaria")
    limite = time.monotonic() + espera
    avisado = False
    while not con.execute("select pg_try_advisory_lock(%s)", (CLAVE_LOCK,)).fetchone()[0]:
        if not avisado:
            duenos = quien_tiene_el_lock(con)
            print(f"[migrar] el lock lo tiene otro migrador "
                  f"{[(d['pid'], d['aplicacion']) for d in duenos]}. Espero hasta "
                  f"{espera:.0f}s. Yo soy '{nombre_de_aplicacion()}'.", flush=True)
            _gancho("espera")
            avisado = True
        if time.monotonic() >= limite:
            raise LockNoObtenido(espera, quien_tiene_el_lock(con))
        time.sleep(REINTENTO_LOCK)
    try:
        _gancho("lock")
        yield
    finally:
        try:
            con.execute("select pg_advisory_unlock(%s)", (CLAVE_LOCK,))
            if tengo_el_lock(con):
                print("[migrar] AVISO: la sesion sigue con el lock despues de "
                      "soltarlo; se suelta todo.", flush=True)
                con.execute("select pg_advisory_unlock_all()")
        except psycopg.Error as e:
            print(f"[migrar] no se pudo soltar el lock explicitamente "
                  f"({type(e).__name__}); se libera al cerrarse la conexion.",
                  flush=True)


def informar_lock(e: LockNoObtenido, que: str) -> int:
    print(f"[migrar] NO se obtuvo el lock en {e.espera:.0f}s. {que}", flush=True)
    for d in e.duenos:
        print(f"    lo tiene: pid={d['pid']} usuario={d['usuario']} "
              f"aplicacion='{d['aplicacion']}' cliente={d['cliente']} "
              f"conectado_desde={d['conectado_desde']} estado={d['estado']}",
              flush=True)
    if not e.duenos:
        print("    (el dueño lo solto justo al vencer la espera: reintentar)", flush=True)
    return SALIDA_LOCK


def informar_ledger(e: LedgerNoActualizable, que: str) -> int:
    print(f"[migrar] EL ESQUEMA DEL LEDGER NO SE PUEDE ACTUALIZAR. {que}", flush=True)
    print(f"    {e}", flush=True)
    return SALIDA_LEDGER


def pasos_del_ledger() -> list[tuple[int, Path]]:
    pasos = []
    for p in sorted(ESQUEMA_LEDGER.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        pasos.append((int(p.name[:4]), p))
    return pasos


def asegurar_ledger(con) -> None:
    """Lleva el esquema del ledger a su ultima version. SOLO dentro de la seccion."""
    if not tengo_el_lock(con):
        raise RuntimeError("asegurar_ledger fuera de la seccion serializada")
    actual = version_del_ledger(con)
    for numero, ruta in pasos_del_ledger():
        if numero <= actual:
            continue
        texto, sha = leer_migracion(ruta)
        try:
            with con.transaction():
                con.execute(texto)
                con.execute("insert into asistente.migraciones_ledger_esquema "
                            "(version, archivo, sha256) values (%s,%s,%s)",
                            (numero, ruta.name, sha))
        except psycopg.Error as e:
            if e.sqlstate != SQLSTATE_LEDGER_NO_ACTUALIZABLE:
                raise
            raise LedgerNoActualizable(
                f"{ruta.name}: {e.diag.message_primary}. {e.diag.message_hint or ''}"
            ) from None
        print(f"[migrar] esquema del ledger -> version {numero} ({ruta.name})",
              flush=True)


def validar_dentro(con, carpeta):
    """Plan con las verificaciones que abortan cualquier escritura. (codigo|None, plan)"""
    pendientes, discrepancias, invalidos, anotadas = plan(con, carpeta)
    if invalidos:
        print("[migrar] HAY ARCHIVOS QUE NO CUMPLEN EL CONTRATO CANONICO. "
              "No se escribe nada.", flush=True)
        for _ruta, msg in invalidos:
            print(f"    {msg}", flush=True)
        return SALIDA_CONTENIDO, None
    if discrepancias:
        print("[migrar] HAY ARCHIVOS APLICADOS QUE CAMBIARON. No se escribe nada.",
              flush=True)
        for ruta, viejo, nuevo in discrepancias:
            print(f"    {ruta.name}\n        anotado: {viejo}\n        ahora:   {nuevo}",
                  flush=True)
        return SALIDA_CHECKSUM, None
    return None, (pendientes, anotadas)


# -----------------------------------------------------------------------------
#  aplicar
# -----------------------------------------------------------------------------

def aplicar(con, espera: float, carpeta: Path | None = None) -> int:
    try:
        with seccion_serializada(con, espera):
            existentes = tablas_sin_ledger(con)
            if existentes:
                print(f"[migrar] esta base YA TIENE el esquema ({len(existentes)} "
                      f"relaciones en 'asistente', p. ej. {existentes[:5]}) y el "
                      f"ledger no tiene ninguna fila. No se aplica nada ni se crea "
                      f"el ledger: se adopta con --adoptar.", flush=True)
                return SALIDA_BASE_EXISTENTE
            asegurar_ledger(con)
            codigo, datos = validar_dentro(con, carpeta)
            if codigo is not None:
                return codigo
            pendientes, anotadas = datos
            if not pendientes:
                print("[migrar] 0 migraciones pendientes.", flush=True)
                return SALIDA_OK
            huecos_ = huecos(pendientes, anotadas)
            if huecos_:
                print("[migrar] HAY MIGRACIONES PENDIENTES ANTERIORES A OTRAS YA "
                      "ANOTADAS. No se aplica nada.", flush=True)
                for ruta in huecos_:
                    print(f"    {ruta.name}", flush=True)
                print(f"  ultima anotada: {max(anotadas)}. Se resuelven con "
                      f"--adoptar, no con --aplicar.", flush=True)
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
                except Exception as e:                           # noqa: BLE001
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
    except LockNoObtenido as e:
        return informar_lock(e, "No se aplico nada ni se creo nada.")
    except LedgerNoActualizable as e:
        return informar_ledger(e, "No se aplico nada.")


def estado(con, carpeta: Path | None = None) -> int:
    """Solo lectura: no crea el ledger ni toma el lock."""
    pendientes, discrepancias, invalidos, anotadas = plan(con, carpeta)
    existe = ledger_existe(con)
    print(f"  algoritmo             : {ALGORITMO}")
    ultima = max((n for n, _ruta in pasos_del_ledger()), default=0)
    print(f"  ledger                : {'existe' if existe else 'NO existe'}"
          f" (esquema version {version_del_ledger(con)} de {ultima})")
    print(f"  archivos en supabase/ : {len(archivos(carpeta))}")
    print(f"  anotados en el ledger : {len(anotadas)}")
    print(f"  pendientes            : {len(pendientes)}")
    print(f"  con checksum distinto : {len(discrepancias)}")
    print(f"  no canonicos          : {len(invalidos)}")
    existentes = tablas_sin_ledger(con)
    if existentes:
        print(f"  BASE EXISTENTE SIN LEDGER: {len(existentes)} relaciones en "
              f"'asistente' -- se adopta, no se aplica")
    for ruta, _, _ in pendientes:
        print(f"    pendiente: {ruta.name}")
    for ruta, viejo, nuevo in discrepancias:
        print(f"    CAMBIO: {ruta.name}: {viejo[:12]}... -> {nuevo[:12]}...")
    for _ruta, msg in invalidos:
        print(f"    NO CANONICO: {msg}")
    for ruta in huecos(pendientes, anotadas):
        print(f"    HUECO: {ruta.name}")
    en_carpeta = {r.name for r in archivos(carpeta)}
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
                   help="con --adoptar: escribe de verdad. Sin esto, solo lectura.")
    p.add_argument("--aceptar", metavar="ARCHIVO",
                   help="con --adoptar: aceptacion humana de UNA migracion")
    p.add_argument("--motivo", help="obligatorio con --aceptar")
    p.add_argument("--autorizado-por", metavar="QUIEN",
                   help="obligatorio con --aceptar: persona o referencia (acta, ticket) "
                        "que autorizo. Es una identidad DECLARADA por quien corre el "
                        "comando; la herramienta no la autentica.")
    p.add_argument("--espera-lock", type=float, default=30.0,
                   help=f"segundos, entre 0 y {ESPERA_MAXIMA:.0f}")
    a = p.parse_args(argv)

    if not 0 <= a.espera_lock <= ESPERA_MAXIMA:
        print(f"[migrar] --espera-lock tiene que estar entre 0 y "
              f"{ESPERA_MAXIMA:.0f} segundos; vino {a.espera_lock}.")
        return SALIDA_CHECKSUM

    con = conectar()
    try:
        if a.estado:
            return estado(con)
        if a.aplicar:
            return aplicar(con, a.espera_lock)
        from cli import manifiesto_adopcion                     # noqa: E402
        return manifiesto_adopcion.adoptar(con, a.escribir_baseline,
                                           a.espera_lock, a.aceptar, a.motivo,
                                           autorizado_por=a.autorizado_por)
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
