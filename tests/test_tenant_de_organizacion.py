# -*- coding: utf-8 -*-
"""
La inversa organizacion -> tenant, y sobre todo cuando NO contesta.

POR QUE EXISTE
--------------
La plataforma multi-ISP (PRD 8.13) necesita que el frontend sepa de que empresa
son los datos a partir de QUIEN inicio sesion. Hasta el 24/09/2026 eso salia de
una variable de entorno, asi que la instalacion entera servia a una sola
empresa: con dos, cada lectura le habria servido a un ISP los datos del otro.

LO QUE SE AFIRMA
----------------
No que la funcion exista -- eso no prueba nada. Que ante una organizacion
desconocida devuelva **nada** en vez de un tenant, que es la unica propiedad
que importa: un default aca es exactamente la fuga que el aislamiento por
organizacion existe para impedir, y ademas silenciosa.

Corre SIN base: se le pasa un cursor falso. La consulta contra Postgres real ya
la ejercitan las pruebas que usan `sesion()`; lo que esta guarda vigila es la
DECISION, que es donde puede colarse un `or 'rapilink'`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.persistencia.db import slug_de_organizacion, _SLUGS  # noqa: E402

fallas = []


def afirmar(condicion, que):
    if condicion:
        print(f"  ok     {que}")
    else:
        print(f"  FALLA  {que}")
        fallas.append(que)


class CursorFalso:
    """Devuelve lo que se le diga, y cuenta cuantas veces le preguntaron."""

    def __init__(self, fila):
        self.fila = fila
        self.consultas = 0

    def execute(self, *_a, **_k):
        self.consultas += 1

    def fetchone(self):
        return self.fila


print("== la inversa contesta cuando hay tenant ==")
_SLUGS.clear()
cur = CursorFalso({"slug": "rapilink"})
afirmar(slug_de_organizacion(cur, "org-1") == "rapilink",
        "una organizacion con asistente devuelve su slug")

print("\n== y NO inventa uno cuando no lo hay ==")
_SLUGS.clear()
afirmar(slug_de_organizacion(CursorFalso(None), "org-sin-asistente") is None,
        "una organizacion sin tenant configurado devuelve None, no un default")

_SLUGS.clear()
sin_consultar = CursorFalso({"slug": "rapilink"})
afirmar(slug_de_organizacion(sin_consultar, "") is None
        and sin_consultar.consultas == 0,
        "con la organizacion vacia ni siquiera consulta: falla cerrado antes")

_SLUGS.clear()
afirmar(slug_de_organizacion(CursorFalso({"slug": "x"}), None) is None,
        "con None tampoco")

print("\n== el cache no mezcla empresas ==")
_SLUGS.clear()
slug_de_organizacion(CursorFalso({"slug": "primera"}), "org-A")
afirmar(slug_de_organizacion(CursorFalso({"slug": "segunda"}), "org-B") == "segunda",
        "la segunda organizacion recibe SU slug, no el de la primera")

# Que el cache sirva para algo: la segunda vez no vuelve a preguntar. Se afirma
# sobre el efecto -- cuantas consultas hizo -- y no sobre el diccionario.
repetida = CursorFalso({"slug": "primera"})
slug_de_organizacion(repetida, "org-A")
afirmar(repetida.consultas == 0,
        "una organizacion ya resuelta no vuelve a consultar la base")

print()
if fallas:
    print(f"[FALLA] {len(fallas)} comprobacion(es) no pasaron.")
    sys.exit(1)
print("[OK] Sin organizacion no hay tenant, y ninguna empresa recibe el de otra.")
