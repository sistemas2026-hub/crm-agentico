# -*- coding: utf-8 -*-
"""
La silueta de una coordenada NO deja reconstruir la coordenada. Y mide bien.

    py -3.13 tests/test_medir_coordenadas.py

POR QUE EXISTE ESTA PRUEBA
--------------------------
'cli/medir_coordenadas.py' se corre contra WispHub en produccion y su salida
termina pegada en una conversacion. Dos cosas tienen que ser ciertas a la vez,
y las dos se rompen en silencio:

  1. NO PUEDE FILTRAR UN DOMICILIO. Un digito que se escape deja de ser una
     silueta y pasa a ser el dato.
  2. TIENE QUE DISTINGUIR LAS FORMAS. Una silueta que colapsa dos formatos
     distintos en el mismo texto no sirve para decidir el parseo -- que es lo
     unico para lo que se corre.

La 2 ya fallo una vez, el 05/11/2026, y por eso esta escrita: 'forma_de'
sustituia digitos por 'D' y DESPUES letras por 'a', y la segunda pasada pisaba
las 'D' de la primera. '10.9185,-74.7668' salia 'aa.aaaa,-aa.aaaa', igual que
un texto de puras letras. La funcion mentia justo sobre lo que existe para
mostrar, y ninguna prueba lo habria visto porque no habia ninguna.
"""
import importlib.util
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "medir_coordenadas", RAIZ / "cli" / "medir_coordenadas.py")
mc = importlib.util.module_from_spec(_spec)
sys.modules["medir_coordenadas"] = mc
_spec.loader.exec_module(mc)

fallos = []


def ok(condicion, mensaje):
    print(f"  [{'ok' if condicion else 'FALLA'}]   {mensaje}")
    if not condicion:
        fallos.append(mensaje)


print("\n1 · La silueta no deja reconstruir el domicilio")

#  Coordenadas inventadas con la FORMA de unas reales de la costa.
REAL = "10.9185,-74.7668"
silueta = mc.forma_de(REAL)
ok(not re.search(r"\d", silueta),
   f"ningun digito sobrevive: {silueta!r}")
ok(silueta == "DD.DDDD,-DD.DDDD",
   f"y los digitos son 'D', no otra cosa: {silueta!r}")
#  EL DEFECTO DEL 05/11/2026, en una sola linea: si las dos pasadas se
#  encadenan mal, esto da 'aa.aaaa,-aa.aaaa'.
ok("a" not in silueta,
   "un numero NO se disfraza de letra (el bug de las dos pasadas)")

print("\n2 · Formas distintas siguen siendo distintas")

distintas = {
    "10.9185,-74.7668": "DD.DDDD,-DD.DDDD",          # sin espacio
    "10.9185, -74.7668": "DD.DDDD, -DD.DDDD",        # con espacio
    "10,9185,-74,7668": "DD,DDDD,-DD,DDDD",          # coma decimal
    "(10.9185, -74.7668)": "(DD.DDDD, -DD.DDDD)",    # entre parentesis
    "0,0": "D,D",                                     # el vacio de WispHub
    "None": "aaaa",                                   # el string None
}
for crudo, esperada in distintas.items():
    ok(mc.forma_de(crudo) == esperada,
       f"{crudo!r} -> {mc.forma_de(crudo)!r}")
ok(len(set(distintas.values())) == len(distintas),
   "las seis formas dan seis siluetas distintas: ninguna colapsa con otra")

print("\n3 · Lo vacio y lo que PARECE vacio y no lo es")

for vacio in ("", "   ", "None", "null", "-", "n/a", "0,0", "0.0,0.0"):
    ok(not mc.esta_cargada(vacio), f"{vacio!r} no cuenta como cargada")
#  '0,0' ES UNA COORDENADA VALIDA (Golfo de Guinea) y por eso va arriba: una
#  guarda que solo pregunte "esta vacio?" la dejaria pasar y el mapa pondria
#  un pin en el Atlantico con toda confianza.
ok(mc.esta_cargada(REAL), "una coordenada de verdad SI cuenta como cargada")
ok(mc.esta_cargada("-74.7668,10.9185"),
   "y al reves tambien: 'cargada' no juzga el orden, solo que haya dato")

print("\n4 · Los componentes: dos, o ninguno")

ok(mc.numeros_de("10.9185,-74.7668") == (10.9185, -74.7668),
   "los dos numeros salen en orden")
ok(mc.numeros_de("10,9185,-74,7668") is None,
   "con coma decimal salen CUATRO numeros -> None, no los dos primeros")
ok(mc.numeros_de("10.9185") is None, "uno solo -> None")
ok(mc.numeros_de("") is None and mc.numeros_de(None) is None,
   "vacio y None -> None, sin reventar")
#  Que no se quede con los dos primeros de una lista mas larga es lo que hace
#  que el script DIGA que la forma es rara, en vez de inventar un punto.
ok(mc.numeros_de("1,2,3") is None,
   "tres numeros -> None: el script informa la rareza, no la resuelve solo")

print("\n5 · Tipos que no son cadena")

ok(mc.forma_de(None) == "<null JSON>", "null del JSON se nombra")
ok(mc.forma_de("") == "<cadena vacia>", "la cadena vacia se nombra aparte")
ok(mc.forma_de(0) == "<int>", "un numero suelto dice su tipo, no su valor")
ok(not mc.esta_cargada(None) and not mc.esta_cargada(0),
   "ni None ni un int cuentan como cargada")

if fallos:
    print(f"\n  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    raise SystemExit(1)

print("\n[OK] La silueta no filtra el domicilio y distingue las formas que "
      "deciden el parseo.\n")
