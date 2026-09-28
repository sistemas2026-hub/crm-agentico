# -*- coding: utf-8 -*-
"""
================================================================================
 EL GATE DECIDE RAPIDO  --  y con la base caida decide QUE NO
================================================================================

    py -3.13 tests/test_timeout_interruptor.py

POR QUE EXISTE
--------------
La verificacion previa a produccion (15/09/2026) midio que, con la base caida,
UNA lectura del interruptor tardaba:

    30,1 s   contra un host que no responde
    60,2 s   contra un puerto cerrado en 'localhost'

El veredicto era el correcto -- bloquear -- pero el costo no. Y una accion
bloqueada toca la base mas de una vez (la lectura del estado, y despues la fila
de auditoria del bloqueo), asi que el turno entero se colgaba minutos en vez de
fallar rapido.

Eso choca con algo que DESPLIEGUE.md ya documenta: cuando el motor tarda de
mas, el proxy corta la conexion y el cliente ve un error por una respuesta que
si existia. Aca el retraso ocurre ANTES de la respuesta, que es peor.

LAS DOS MITADES, Y LAS DOS HACEN FALTA
--------------------------------------
Un timeout corto que ademas devolviera "segui" seria una regresion de
seguridad, no una mejora: cortar la base pasaria a ser la forma de saltear el
interruptor. Por eso cada comprobacion de tiempo va con su comprobacion de
veredicto al lado.

CORRE SIN BASE DE DATOS
-----------------------
A, B y E miden contra un extremo MUERTO a proposito -- un puerto donde no
escucha nadie -- asi que no necesitan Postgres: lo que se ejercita es
exactamente el camino de fallo. C y D sustituyen la respuesta de la base (no el
gate) para probar los dos veredictos con la base viva.
================================================================================
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia                # noqa: E402
from nucleo.seguridad import interruptor                          # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


def seccion(titulo: str) -> None:
    print(f"\n--- {titulo} ---")


# Un puerto alto donde no escucha nadie. No se usa 'localhost' a secas para la
# medicion principal: un nombre de doble pila resuelve a ::1 y a 127.0.0.1, y
# libpq gasta el timeout COMPLETO en cada direccion -- el peor caso es el
# doble, y la cota de abajo lo contempla.
EXTREMO_MUERTO = {"DBHOST": "127.0.0.1", "DBPORT": "15499", "DBNAME": "nada",
                  "DBUSER": "nadie", "DBPASSWORD": "nada"}

TOPE = 2 * persistencia.SEGUNDOS_CONEXION_GATE + 2      # margen razonable


class BaseCaida:
    """Apunta el motor a un extremo muerto, y lo deja como estaba al salir."""

    def __enter__(self):
        self._previo = {k: os.environ.get(k) for k in EXTREMO_MUERTO}
        os.environ.update(EXTREMO_MUERTO)
        return self

    def __exit__(self, *e):
        for k, v in self._previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def cronometrar(fn, *a, **k):
    t0 = time.monotonic()
    salida = fn(*a, **k)
    return salida, time.monotonic() - t0


# ===========================================================================
seccion("0. el timeout del gate es corto, y el general NO se toco")

afirmar(persistencia.SEGUNDOS_CONEXION == 30,
        f"el timeout general sigue en 30 s ({persistencia.SEGUNDOS_CONEXION})")
afirmar(1 <= persistencia.SEGUNDOS_CONEXION_GATE <= 3,
        f"el del gate esta entre 1 y 3 s ({persistencia.SEGUNDOS_CONEXION_GATE})")

# Que SOLO el camino del interruptor lo use. Si manana alguien se lo pone a una
# consulta de conversacion, un turno sano empieza a fallar cuando la base tarda
# un segundo de mas -- y eso no se veria en ninguna otra prueba.
# Se mira por AST y no por texto. La primera version de esta comprobacion
# partia el archivo por la cadena "def " y las CONSTANTES del modulo --que
# viven entre dos funciones-- quedaban atribuidas a la funcion anterior:
# reportaba '_organizacion' como usuaria del timeout del gate, que es falso.
# Un falso positivo en una prueba de seguridad es justo lo que no puede pasar.
import ast                                                        # noqa: E402

arbol = ast.parse((RAIZ / "nucleo" / "persistencia" / "db.py")
                  .read_text(encoding="utf-8"))
funciones_con_gate = set()
for nodo in ast.walk(arbol):
    if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name) and n.id == "SEGUNDOS_CONEXION_GATE":
            funciones_con_gate.add(nodo.name)

#  Las tres de Autonomia 2 se AGREGAN a la lista declarandolo, no relajando la
#  comprobacion: sigue siendo un conjunto exacto, y una funcion nueva que se
#  ponga el timeout del gate sin pasar por aca va a hacer fallar esta prueba.
#
#  Por que pertenecen al gate: 'nivel_autonomia' y 'autorizacion_herramienta'
#  se leen ANTES de cada efecto autonomo -- son parte de la misma decision que
#  'estado_autonomia', y alguien esta esperando del otro lado.
#  'secreto_jwt_en_base' comprueba el prerequisito de B-7 en el mismo camino.
#  'registrar_ejecucion_autonoma' escribe la bitacora de esa decision: no
#  decide, pero corre dentro del mismo tramo y colgarse ahi dejaria la accion
#  en el aire igual.
afirmar(funciones_con_gate == {"estado_autonomia",
                               "estado_autonomia_de_organizacion",
                               "registrar_auditoria",
                               # Autonomia 2 -- ver el comentario de arriba.
                               "nivel_autonomia",
                               "autorizacion_herramienta",
                               "secreto_jwt_en_base",
                               "registrar_ejecucion_autonoma",
                               # M06-B: la constancia de un intento RECHAZADO
                               # de mover el techo. Mismo criterio que la
                               # bitacora: corre en el tramo del rechazo.
                               "registrar_intento_techo"},
        f"solo las funciones del gate lo usan ({sorted(funciones_con_gate)})")

# EL TOPE DE SENTENCIA SE PONE CON set_config(), NUNCA CON UN 'SET' CON %s.
#
# SET es una sentencia de utilidad y NO acepta parametros: Postgres responde
# 'syntax error at or near "$1"'. La primera version de este cambio lo escribia
# asi, y el efecto era el peor posible -- TODA lectura del interruptor fallaba
# contra una base real y, como el gate falla cerrado, ninguna accion autonoma
# habria funcionado en ningun tenant. Ninguna prueba sin base podia verlo: el
# extremo muerto de mas abajo ni siquiera llega a mandar una sentencia.
#
# Esta comprobacion es de texto a proposito. No reemplaza a una verificacion
# contra PostgreSQL real -- la cubre para que no vuelva por descuido.
fuente_db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
# Sin las lineas de comentario: la explicacion de ARRIBA cita la forma
# equivocada para que se entienda por que esta prohibida, y buscarla en el
# archivo entero se encontraba a si misma. Documentar un error no puede hacer
# fallar la guarda que lo vigila.
codigo = " ".join(l for l in fuente_db.splitlines()
                  if not l.lstrip().startswith("#"))
plano = " ".join(codigo.split())
afirmar("set local statement_timeout = %s" not in plano
        and "set statement_timeout = %s" not in plano,
        "el tope de sentencia NO se manda con un SET parametrizado "
        "(Postgres lo rechaza: SET no acepta parametros)")
afirmar("set_config('statement_timeout'" in plano,
        "se pone con set_config(), que si acepta parametros")

# ===========================================================================
seccion("A y B. base caida: bloquea, y responde rapido")

with BaseCaida():
    v, cuanto = cronometrar(interruptor.veredicto, "cualquiera")
    print(f"          medido: {cuanto:.1f}s  (tope de esta prueba: {TOPE}s)")
    afirmar(not v.permitido,
            f"A · con la base caida NO se permite la accion (estado={v.estado})")
    afirmar(v.estado == interruptor.DESCONOCIDO,
            f"   y el estado se informa como desconocido, no como activo "
            f"({v.estado})")
    afirmar(cuanto <= TOPE,
            f"B · responde en {cuanto:.1f}s, dentro del tope de {TOPE}s")
    afirmar(cuanto < 30,
            f"   y muy por debajo de los 30 s del timeout general -- que es la "
            f"regresion que esta prueba cuida ({cuanto:.1f}s)")

    vo, cuanto_org = cronometrar(
        interruptor.veredicto_de_organizacion,
        "00000000-0000-0000-0000-000000000000")
    print(f"          medido: {cuanto_org:.1f}s  (lectura por organizacion)")
    afirmar(not vo.permitido,
            "   la lectura del scheduler (por organizacion) tambien bloquea")
    afirmar(cuanto_org <= TOPE,
            f"   y tambien responde a tiempo ({cuanto_org:.1f}s)")

    _, cuanto_aud = cronometrar(interruptor.anotar_bloqueo,
                                "cualquiera", "actor", "recurso", "motivo")
    print(f"          medido: {cuanto_aud:.1f}s  (auditoria del bloqueo)")
    afirmar(cuanto_aud <= TOPE,
            f"   y anotar el bloqueo no cuesta mas que decidirlo "
            f"({cuanto_aud:.1f}s)")

# ===========================================================================
seccion("C y D. base disponible: permite si esta activo, bloquea si no")
# Se sustituye lo que CONTESTA la base, no el gate: el camino del codigo es el
# real, incluida la traduccion de fila a veredicto.

original = persistencia.estado_autonomia
try:
    persistencia.estado_autonomia = lambda t: {
        "estado": "activo", "estado_anterior": None, "actor": "migracion",
        "motivo": "", "creado_en": None}
    v = interruptor.veredicto("cualquiera")
    afirmar(v.permitido and v.estado == interruptor.ACTIVO,
            f"C · base disponible y 'activo': se permite ({v.estado})")

    persistencia.estado_autonomia = lambda t: {
        "estado": "detenido", "estado_anterior": "activo",
        "actor": "operaciones", "motivo": "incidente en curso",
        "creado_en": None}
    v = interruptor.veredicto("cualquiera")
    afirmar(not v.permitido and v.estado == interruptor.DETENIDO,
            f"D · base disponible y 'detenido': se bloquea ({v.estado})")
    afirmar(v.motivo == "incidente en curso",
            f"   con el motivo de quien lo movio ('{v.motivo}')")
finally:
    persistencia.estado_autonomia = original

# ===========================================================================
seccion("E. un error de lectura NUNCA se convierte en autorizacion")


class FallaDeLectura(Exception):
    pass


class TablaQueNoExiste(Exception):
    sqlstate = "42P01"


original = persistencia.estado_autonomia
try:
    for excepcion, texto in (
            (FallaDeLectura("se corto la conexion a mitad"), "una conexion cortada"),
            (TimeoutError("connection timeout expired"), "un timeout"),
            (PermissionError("permission denied for table"), "un permiso denegado")):
        def _revienta(t, _e=excepcion):
            raise _e

        persistencia.estado_autonomia = _revienta
        v = interruptor.veredicto("cualquiera")
        afirmar(not v.permitido,
                f"E · {texto} BLOQUEA, no autoriza (estado={v.estado})")

    # SIN EXCEPCIONES  --  corregido el 17/09/2026 (paso 10.10)
    # Hasta esa fecha este bloque afirmaba lo contrario: que "la tabla no existe"
    # PERMITIA, como unica excepcion declarada del fail-closed. El argumento era
    # que es el unico caso en que se sabe que nadie pudo tirar el interruptor.
    # Se quito porque convierte "el control no esta instalado" en "esta
    # autorizado" -- y una base restaurada sin esa migracion quedaba con la
    # autonomia permitida sin que nadie lo decidiera.
    persistencia.estado_autonomia = lambda t: (_ for _ in ()).throw(
        TablaQueNoExiste("relation does not exist"))
    v = interruptor.veredicto("cualquiera")
    afirmar(not v.permitido,
            f"   y 'la tabla no existe todavia' TAMBIEN bloquea -- no hay "
            f"excepciones al fail-closed (estado={v.estado})")
    afirmar(v.estado == interruptor.SIN_INSTALAR,
            f"   con su estado propio, distinto de 'desconocido' ({v.estado})")
finally:
    persistencia.estado_autonomia = original

# ===========================================================================
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] El gate decide rapido, y con la base caida decide que no.")
