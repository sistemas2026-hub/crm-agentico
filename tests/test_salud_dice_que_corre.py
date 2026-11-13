# -*- coding: utf-8 -*-
"""
================================================================================
 /salud DICE QUE CODIGO CORRE  --  y la trampa de los saltos de linea
================================================================================

    py -3.13 tests/test_salud_dice_que_corre.py

QUE SE PRUEBA
-------------
Que la huella sirva para la unica pregunta por la que existe: *¿este arbol es
el que esta corriendo?* Eso se rompe de DOS maneras opuestas, y las dos tienen
su seccion:

  * que NO se mueva cuando el codigo cambia  -> diria "si" sobre un deploy que
                                                no salio
  * que SI se mueva cuando el codigo no cambio -> diria "no" sobre un deploy
                                                que si salio, para siempre

LA SEGUNDA ES LA PELIGROSA, y no es hipotetica: este repositorio se trabaja en
Windows --arbol con CRLF-- y la imagen se construye desde git, que entrega LF.
Sin normalizar, la huella local y la desplegada no coinciden NUNCA. La
herramienta contestaria "no esta desplegado" sobre el mismo codigo, siempre, y
un instrumento que da siempre el mismo resultado no se nota roto: se nota
aburrido, y se deja de mirar.

COMO SE MIDE
------------
Sobre arboles de mentira en un directorio temporal, apuntando `_NUCLEO` ahi: se
calcula la huella, se cambia UNA cosa, se vuelve a calcular. Lo que se afirma
es la comparacion entre dos numeros reales, no que exista una funcion.

Y `/salud` se llama de verdad, por el cliente de pruebas de Flask, con la app
real importada. No se lee el codigo de la ruta.
================================================================================
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.observabilidad import version                        # noqa: E402

FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(titulo: str) -> None:
    print()
    print("-" * 78)
    print(f"  {titulo}")
    print("-" * 78)


def huella_de(archivos: dict[str, bytes]) -> str:
    """La huella de un arbol inventado. `archivos` es {ruta relativa: bytes}."""
    carpeta = pathlib.Path(tempfile.mkdtemp(prefix="huella_"))
    try:
        for relativa, contenido in archivos.items():
            destino = carpeta / relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
        anterior, cache = version._NUCLEO, version._huella
        try:
            version._NUCLEO = carpeta
            version._huella = None
            return version.huella()
        finally:
            version._NUCLEO, version._huella = anterior, cache
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


BASE = {
    "motor.py": b"def responder():\n    return 1\n",
    "seguridad/frontera.py": b"PERMITIDO = False\n",
}


# =============================================================================
seccion("1 . se mueve cuando el codigo se movio")

original = huella_de(BASE)
afirmar(len(original) == 12 and original.isalnum(),
        f"la huella es un numero corto y legible ({original})")

otro_contenido = dict(BASE)
otro_contenido["motor.py"] = b"def responder():\n    return 2\n"
afirmar(huella_de(otro_contenido) != original,
        "cambiar UNA linea de UN archivo cambia la huella")

#  EL CASO QUE MAS IMPORTA DE ESTA SECCION: una guarda de seguridad invertida.
#  Si la huella no se moviera por esto, diria que el fix esta desplegado
#  estando el codigo viejo arriba.
invertida = dict(BASE)
invertida["seguridad/frontera.py"] = b"PERMITIDO = True\n"
afirmar(huella_de(invertida) != original,
        "invertir una guarda de seguridad cambia la huella")

con_archivo_nuevo = dict(BASE)
con_archivo_nuevo["seguimiento/nuevo.py"] = b"x = 1\n"
afirmar(huella_de(con_archivo_nuevo) != original,
        "agregar un archivo cambia la huella")

sin_uno = {"motor.py": BASE["motor.py"]}
afirmar(huella_de(sin_uno) != original,
        "borrar un archivo cambia la huella")

#  LA RUTA ENTRA EN LA HUELLA: el mismo contenido en otro lado es otro motor.
#
#  UN SOLO ARCHIVO EN CADA ARBOL, Y ESO NO ES PEREZA. La version anterior de
#  esta afirmacion movia un archivo dentro del arbol de dos, y PASABA SIN
#  MEDIR NADA: mover 'motor.py' a 'seguridad/motor.py' tambien cambia el ORDEN
#  en que se recorren los archivos, asi que la huella se movia igual aunque la
#  ruta no entrara en el hash. Lo encontro una pasada de mutacion el
#  12/11/2026 -- sacar la ruta del hash dejaba esta prueba en verde.
#
#  Con UN archivo por arbol la secuencia de contenidos es identica y lo unico
#  distinto es el nombre. Si la ruta no entrara, estas dos huellas serian
#  iguales.
solo_a = huella_de({"motor.py": b"x = 1\n"})
solo_b = huella_de({"relevo.py": b"x = 1\n"})
afirmar(solo_a != solo_b,
        "el MISMO contenido en otra ruta da otra huella",
        f"a={solo_a}  b={solo_b}")


# =============================================================================
seccion("2 . NO se mueve cuando el codigo no se movio")

#  LA TRAMPA DE WINDOWS, y el motivo por el que esta prueba existe. El mismo
#  codigo con CRLF y con LF tiene que dar LA MISMA huella: si no, el arbol
#  local y la imagen no coinciden jamas.
con_crlf = {r: c.replace(b"\n", b"\r\n") for r, c in BASE.items()}
afirmar(huella_de(con_crlf) == original,
        "CRLF y LF dan la MISMA huella -- si no, local y desplegado nunca "
        "coincidirian",
        f"LF={original}  CRLF={huella_de(con_crlf)}")

#  Correr el codigo no es cambiarlo. Lo que protege esto es el GLOB: si alguien
#  lo abriera a `*`, la huella empezaria a moverse con cada import.
#
#  Antes habia ademas un filtro explicito de `__pycache__` en version.py. La
#  pasada de mutacion del 12/11/2026 mostro que no filtraba nada --ningun
#  `.pyc` entra por un glob de `*.py`-- y se saco: un mecanismo que no hace
#  nada se lee como una garantia. Esta afirmacion es la que de verdad cubre
#  el caso.
con_cache = dict(BASE)
con_cache["__pycache__/motor.cpython-313.pyc"] = b"\x00binario\x00"
afirmar(huella_de(con_cache) == original,
        "un __pycache__ no cambia la huella: importar no es modificar")

#  Y es estable: dos lecturas del mismo arbol dan lo mismo.
afirmar(huella_de(BASE) == original,
        "dos calculos del mismo arbol dan el mismo numero")


# =============================================================================
seccion("3 . la ruta real la publica")

import os                                                        # noqa: E402

os.environ.setdefault("PUERTO_API", "5000")
from nucleo.canales import api                                   # noqa: E402

cliente = api.app.test_client()
r = cliente.get("/salud")
cuerpo = r.get_json() or {}
print(f"  /salud -> HTTP {r.status_code} {cuerpo}")

afirmar(r.status_code == 200, f"/salud sigue contestando 200 ({r.status_code})")
afirmar(cuerpo.get("estado") == "ok",
        "sigue diciendo 'ok' -- quien ya la usa como latido no se entera de "
        "este cambio")
afirmar(bool(cuerpo.get("codigo")),
        "y ahora dice QUE codigo corre", str(cuerpo))

#  LO QUE CONTESTA ES LA HUELLA DE ESTE ARBOL, no un valor cualquiera. Sin
#  esto, devolver la cadena "ok" en `codigo` pasaria la afirmacion de arriba.
afirmar(cuerpo.get("codigo") == version.huella(),
        "y es la huella de ESTE arbol, no un texto fijo",
        f"ruta={cuerpo.get('codigo')}  arbol={version.huella()}")

#  SOBRE ALGO, y no sobre cero archivos: una huella de un arbol vacio tambien
#  seria un hash valido, estable y completamente inutil.
afirmar(version.cuantos_archivos() > 50,
        f"se calcula sobre el motor entero ({version.cuantos_archivos()} "
        f"archivos)")


# =============================================================================
print()
print("=" * 78)
if FALLOS:
    print(f"  {len(FALLOS)} FALLO(S):")
    for f in FALLOS:
        print(f"    - {f}")
    sys.exit(1)
print("  TODO EN VERDE -- se puede preguntar que codigo esta corriendo")
print("=" * 78)
