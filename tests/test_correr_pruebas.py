# -*- coding: utf-8 -*-
"""
================================================================================
 EL CORREDOR DE PRUEBAS TIENE QUE SABER QUE ESTA MIRANDO
================================================================================

Por que existe
--------------
`cli/correr_pruebas.py` es el que dice si el repositorio esta en verde, y
existe para hacer UNA distincion que D1 nombra explicitamente: **FALLO no es lo
mismo que NO SE PUDO CORRER**. Si esa distincion se rompe, el numero que reporta
deja de significar algo -- y nadie lo nota, porque el corredor es justamente lo
que se mira en vez de abrir los logs.

El 26/09/2026 se rompia de las dos maneras, medido sobre una corrida real de las
150 pruebas:

  1. Cinco pruebas decian "Conexion incompleta: falta DBNAME" --o sea, no se
     pudieron medir-- y el corredor las contaba como FALLO. Su patron conocia
     un mensaje de la capa de conexion y no el otro.
  2. El motivo que imprimia era, en nueve de catorce fallos, **una linea de
     OK**: estas pruebas van imprimiendo cada comprobacion y cierran con la
     ultima que paso, asi que "las 31 escrituras estan clasificadas, sin sobras
     ni faltas" se reportaba como la razon de un rojo. Un motivo que describe
     algo que salio BIEN es peor que ninguno: manda a buscar donde no esta.

Lo que se prueba aca son las dos funciones puras que deciden eso, invocadas de
verdad -- no una copia. Sin base, sin subprocesos y en milisegundos.

Uso
---
    py -3.13 tests/test_correr_pruebas.py
================================================================================
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

#: Se carga por ruta y no con 'import': el modulo es un CLI y al importarlo por
#: nombre ejecutaria su bloque de arranque.
_spec = importlib.util.spec_from_file_location(
    "correr_pruebas_bajo_prueba", RAIZ / "cli" / "correr_pruebas.py")
corredor = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(corredor)
except SystemExit:          # el CLI decide salir cuando nadie le pasa argumentos
    pass

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


print("=" * 74)
print(" EL CORREDOR DISTINGUE UN FALLO DE UN 'NO SE PUDO CORRER'")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n1. los dos mensajes de la capa de conexion son falta de entorno")

for mensaje in ("No hay datos de conexion en el entorno. Definir DBHOST, DBPORT...",
                "Conexion incompleta: falta DBNAME en el entorno. Se necesitan las cinco: "
                "DBHOST, DBPORT, DBNAME, DBUSER, DBPASSWORD.",
                "could not connect to server: Connection refused",
                'connection to server at "localhost" failed'):
    comprobar(bool(corredor._FALTA_ENTORNO.search(mensaje)),
              f"se reconoce: {mensaje[:52]}...")

# Y no cualquier cosa: un fallo de verdad NO puede leerse como falta de entorno,
# porque entonces se contaria como salteado y el rojo desapareceria del informe.
for mensaje in ("  [FALLA] la cifra de escaladas viaja igual",
                "AssertionError: esperaba 3 y dio 10",
                "  [FALLA] el umbral efectivo se acota al del cierre"):
    comprobar(not corredor._FALTA_ENTORNO.search(mensaje),
              f"NO se confunde con entorno: {mensaje.strip()[:48]}...")

# ---------------------------------------------------------------------------
print("\n2. el motivo es el fallo, no la ultima linea que quedo impresa")

salida_tipica = [
    "  [ok]   las 31 escrituras estan clasificadas, sin sobras ni faltas",
    "  [FALLA] la cifra de escaladas viaja igual",
    "  [ok]   ninguna herramienta de escritura quedo sin clase de riesgo",
    "======================================================================",
    "  - las otras 24 escrituras NO son irreversibles",
]
motivo = corredor._primer_motivo_legible(salida_tipica)
comprobar("[FALLA]" in motivo and "escaladas" in motivo,
          "con un [FALLA] en el medio, el motivo es ESE y no la ultima linea",
          f"dio {motivo!r}")

comprobar("31 escrituras" not in motivo and "24 escrituras" not in motivo,
          "y nunca una comprobacion que PASO: eso manda a buscar donde no esta")

# Un traceback: el encabezado no explica nada, la excepcion si.
traza = ["Traceback (most recent call last):",
         '  File "x.py", line 3, in <module>',
         "TypeError: '>' not supported between instances of 'NoneType' and 'int'"]
comprobar("TypeError" in corredor._primer_motivo_legible(traza),
          "en un traceback el motivo es la excepcion, no el encabezado",
          f"dio {corredor._primer_motivo_legible(traza)!r}")

# Solo lineas de OK: mejor vacio que un motivo falso. Quien llama pone el codigo
# de salida, que no explica pero tampoco miente.
comprobar(corredor._primer_motivo_legible(
              ["  [ok]   algo bien", "  - otra cosa bien", "===="]) == "",
          "si no hay ninguna linea de fallo, el motivo queda VACIO")

comprobar(corredor._primer_motivo_legible([]) == "",
          "y una salida vacia no revienta")

# El timeout tambien es un motivo legible, y no un fallo de la prueba.
comprobar("colgo" in corredor._primer_motivo_legible(["se colgo: mas de 180s"]),
          "un cuelgue se reporta como lo que es")

# ==========================================================================
#  UN FALLO PROPIO LE GANA A LA FRASE DE ENTORNO  (hallado el 27/09/2026)
# ==========================================================================
#  La cuarta pasada del auditor midio esto rompiendo una afirmacion de ESTA
#  prueba: salia con 1, y el corredor la contaba como "no se pudo correr" y
#  salia con 0. La causa: '_FALTA_ENTORNO' se busca sobre la salida ENTERA, y
#  los ejemplos de esta prueba imprimen esas frases a proposito.
#
#  O sea que la guarda del instrumento que dice si el repo esta en verde era la
#  unica que el instrumento no podia reportar en rojo, y el workflow de CI
#  quedaba verde con ella caida.
#
#  Se afirma por EFECTO --como clasifica una salida concreta-- y no por la
#  presencia del patron.

def _veredicto(salida: str) -> str:
    """
    Corre 'corredor.correr' DE VERDAD sobre un archivo temporal que imprime
    'salida' y sale con 1.

    La primera version de este ayudante REIMPLEMENTABA la regla, y por eso
    sobrevivio a la mutacion que volvia el orden atras: afirmaba sobre una
    copia del mecanismo y no sobre el mecanismo. El metodo de CLAUDE.md 6 lo
    dice con esas palabras -- el instrumento tiene que recorrer el camino que
    mide.
    """
    import tempfile

    cuerpo = (
        'import sys' + chr(10) +
        'print(' + repr(salida) + ')' + chr(10) +
        'sys.exit(1)' + chr(10)
    )
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / 'test_falso_para_medir.py'
        archivo.write_text(cuerpo, encoding='utf-8')
        paso, _motivo, _tardo = corredor.correr(archivo, 60)
    if paso is None:
        return 'SALTEADA'
    return 'FALLO' if paso is False else 'PASO'


#  Lo que la version anterior clasificaba mal: corrio, fallo, y MENCIONA la
#  frase de entorno porque su ejemplo la imprime.
comprobar(_veredicto('  [FALLA] algo real' + chr(10) +
                     '   imprime: Conexion incompleta: falta DBNAME' + chr(10) +
                     'FALLAS (1)') == 'FALLO',
          'un fallo propio NO se degrada a salteado por mencionar el entorno')

comprobar(_veredicto('  ROJO  algo que alguien tiene que ver' + chr(10) +
                     'could not connect to server') == 'FALLO',
          'y tampoco si el veredicto propio dice ROJO')

comprobar(_veredicto('[FALLA] 2 comprobacion(es) no pasaron.' + chr(10) +
                     'Definir DBHOST') == 'FALLO',
          'ni cuando el rojo viene con el conteo')

#  Y lo que SI tiene que seguir siendo salteado: sin veredicto propio.
comprobar(_veredicto('Traceback (most recent call last):' + chr(10) +
                     'RuntimeError: Conexion incompleta: falta DBNAME')
          == 'SALTEADA',
          'una prueba que NO pudo correr sigue contando como no medida')

comprobar(_veredicto('No hay datos de conexion') == 'SALTEADA',
          'y el caso sin traceback tambien')

#  El discriminador es ESTRECHO a proposito: 'Traceback' y 'Exception' no
#  alcanzan, porque una prueba que no pudo correr tambien los imprime. Si
#  alguien los agrega, esto se pone rojo.
#  Y EL MOTIVO DICE QUE FALTO, no siempre "Postgres". Antes una guarda que
#  necesitaba bash --la del entrypoint-- se reportaba como "pide Postgres", que
#  manda a revisar credenciales de base por un problema que no es ese.
def _motivo_de(salida: str) -> str:
    import tempfile

    cuerpo = ("import sys" + chr(10) + "print(" + repr(salida) + ")" + chr(10)
              + "sys.exit(1)" + chr(10))
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / "test_falso_para_medir.py"
        archivo.write_text(cuerpo, encoding="utf-8")
        _paso, motivo, _tardo = corredor.correr(archivo, 60)
    return motivo


comprobar("Postgres" in _motivo_de("Conexion incompleta: falta DBNAME"),
          "si falto la base, el motivo nombra Postgres")

comprobar("Postgres" not in _motivo_de(
              "NO SE PUDO CORRER: falta una dependencia del entorno (bash)"),
          "si falto OTRA dependencia, el motivo NO dice Postgres")

comprobar("dependencia del entorno" in _motivo_de(
              "NO SE PUDO CORRER: falta una dependencia del entorno (bash)"),
          "y dice que fue una dependencia del entorno")

#  UNA PRUEBA PUEDE PEDIR MAS TIEMPO, PERO NO PUEDE DESACTIVAR LA DETECCION.
#
#  Existe porque una prueba que vive al borde del tope da un rojo INTERMITENTE, y
#  eso ensena a ignorar los rojos. El permiso es por prueba y con el motivo al
#  lado; el techo absoluto lo pone el corredor.
def _tope(texto: str, por_defecto: int = 180) -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / "test_falso_para_medir.py"
        archivo.write_text(texto, encoding="utf-8")
        return corredor.tope_de(archivo, por_defecto)


comprobar(_tope("print('hola')") == 180,
          "una prueba que no declara nada usa el tope por defecto")

comprobar(_tope("TOPE_DE_TIEMPO = 420" + chr(10) + "print('hola')") == 420,
          "una prueba que declara TOPE_DE_TIEMPO obtiene ese tope")

comprobar(_tope("TOPE_DE_TIEMPO = 99999" + chr(10) + "print('x')")
          == corredor._TOPE_MAXIMO,
          f"y no puede pasar del techo del corredor ({corredor._TOPE_MAXIMO}s): "
          f"si no, 'TOPE_DE_TIEMPO = 99999' seria apagar la deteccion de "
          f"cuelgues escribiendo una linea")

comprobar(_tope("TOPE_DE_TIEMPO = 30" + chr(10) + "print('x')") == 180,
          "y tampoco puede pedir MENOS que el default, que seria fabricar un "
          "cuelgue ajeno")

#  Y que la marca no se dispare desde un comentario o un docstring: tiene que ser
#  una asignacion de verdad, al principio de linea.
comprobar(_tope("#  TOPE_DE_TIEMPO = 420" + chr(10) + "print('x')") == 180,
          "la marca en un comentario NO cuenta")

comprobar(_tope("texto = 'TOPE_DE_TIEMPO = 420'" + chr(10) + "print('x')") == 180,
          "ni dentro de una cadena")

#  Y EL ENGANCHE: que 'main' se lo pase a 'correr' de verdad.
#
#  Las afirmaciones de arriba llaman a 'tope_de' directamente, asi que seguian
#  VERDES con el tope desconectado de 'main' -- medido. Es la septima vez hoy que
#  una guarda propia afirma sobre la pieza y no sobre el camino, asi que va la
#  comprobacion estructural.
import ast as _ast

_FUENTE_CORREDOR = (Path(corredor.__file__)).read_text(encoding="utf-8")
_ARBOL_CORREDOR = _ast.parse(_FUENTE_CORREDOR)

_llamadas_correr = [
    n for n in _ast.walk(_ARBOL_CORREDOR)
    if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
    and n.func.id == "correr"]
comprobar(len(_llamadas_correr) == 1,
          f"hay UN solo sitio que ejecuta una prueba "
          f"(hay {len(_llamadas_correr)})")

_con_tope = [
    n for n in _llamadas_correr
    if any(isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)
           and c.func.id == "tope_de" for a in n.args for c in _ast.walk(a))]
comprobar(len(_con_tope) == len(_llamadas_correr),
          f"y le pasa el tope declarado por la prueba, no el fijo "
          f"(con tope: {len(_con_tope)} de {len(_llamadas_correr)})")

comprobar(not corredor._VEREDICTO_PROPIO_EN_ROJO.search(
              'Traceback (most recent call last):' + chr(10) + 'Exception: x'),
          'Traceback y Exception NO cuentan como veredicto propio en rojo')

print("\n" + "=" * 74)
if fallos:
    print(f"[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] El corredor separa lo que fallo de lo que no se pudo medir, y dice por que.")
