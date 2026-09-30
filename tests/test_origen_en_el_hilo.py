# -*- coding: utf-8 -*-
"""
================================================================================
 D30 -- EL HILO PROYECTA EL ORIGEN DURABLE  (sin base)
================================================================================

    py -3.13 tests/test_origen_en_el_hilo.py

QUE PROTEGE
-----------
Que `db.mensajes_de()` -- la unica funcion que le sirve el hilo a la pantalla --
devuelva `origen` y `autor_nombre`, y que los devuelva TAL CUAL.

Sin esas dos columnas la interfaz solo tiene `rol`, y `rol` no alcanza: desde
B2 una respuesta escrita por una persona es rol 'assistant' con origen
'humano', exactamente igual que una de la IA. La pantalla terminaba mostrando
las dos como si las hubiera escrito Dexter -- y a las filas historicas, cuyo
origen nadie registro, tambien.

Afirmar quien escribio algo que no sabemos es peor que no decirlo. Por eso la
prueba central de este archivo no es que el dato viaje, sino que un NULL
SIGA SIENDO NULL.

POR QUE SIN BASE
----------------
`mensajes_de` abre `sesion(tenant)` y hace `cur.execute` + `cur.fetchall()`.
Se sustituye la sesion por un doble que devuelve filas preparadas: asi se
prueba el camino real de lectura -- la consulta que se emite y la conversion a
dict -- sin PostgreSQL y sin tocar ninguna base. Lo que necesita un motor de
verdad (el CHECK de la columna) ya vive en tests/test_origen_mensajes_base.py.
================================================================================
"""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db                                   # noqa: E402

fallos = []


def afirmar(condicion, mensaje):
    if condicion:
        print("  OK   " + mensaje)
    else:
        fallos.append(mensaje)
        print("  FALLA " + mensaje)


# ── el doble ────────────────────────────────────────────────────────────────
# Dos execute: el encabezado de la conversacion y el hilo. Se guardan las
# consultas para poder mirarlas, y se devuelven las filas que se le pidan.
class _Cursor:
    def __init__(self, conversacion, mensajes):
        self._conversacion = conversacion
        self._mensajes = mensajes
        self.consultas = []
        self._toca_mensajes = False

    def execute(self, sql, params=None):
        self.consultas.append(sql)
        self._toca_mensajes = "from asistente.messages m" in sql

    def fetchone(self):
        return self._conversacion

    def fetchall(self):
        return self._mensajes if self._toca_mensajes else []


def _sesion(cursor):
    @contextmanager
    def falsa(tenant):
        yield cursor, "org-de-prueba"
    return falsa


def leer(mensajes):
    """Corre mensajes_de() contra el doble y devuelve el hilo ya convertido."""
    cur = _Cursor({"id": "c1", "canal": "whatsapp"}, mensajes)
    real = db.sesion
    db.sesion = _sesion(cur)
    try:
        return db.mensajes_de("rapilink", "c1"), cur
    finally:
        db.sesion = real


print(__doc__)

# ── 1. la consulta nombra las dos columnas ──────────────────────────────────
_, cur = leer([])
hilo = [q for q in cur.consultas if "from asistente.messages m" in q]
afirmar(len(hilo) == 1, "la consulta del hilo se emite una sola vez")
sql = hilo[0] if hilo else ""
# Sin comentarios: la columna tiene que estar en el SELECT, no nombrada de paso
# en una explicacion.
sin_comentarios = re.sub(r"--[^\n]*", "", sql)
afirmar("m.origen" in sin_comentarios, "el SELECT del hilo pide m.origen")
afirmar("m.autor_nombre" in sin_comentarios, "el SELECT del hilo pide m.autor_nombre")

# ── 2. no hay relleno de ningun tipo sobre origen ───────────────────────────
# coalesce(m.origen, ...) o un case que lo sustituya serian inferencia.
afirmar(
    not re.search(r"coalesce\s*\(\s*m\.origen", sin_comentarios, re.I),
    "no hay coalesce sobre m.origen: un NULL no se rellena en el SQL",
)
afirmar(
    not re.search(r"case\s+when[^)]*m\.origen", sin_comentarios, re.I),
    "no hay case/when que reinterprete m.origen",
)

# ── 3. los cinco origenes del contrato llegan tal cual ──────────────────────
FILAS = [
    {"id": "m1", "rol": "user", "contenido": "sigo sin internet",
     "origen": "cliente", "autor_nombre": None},
    {"id": "m2", "rol": "assistant", "contenido": "reinicio el equipo",
     "origen": "ia", "autor_nombre": None},
    {"id": "m3", "rol": "assistant", "contenido": "voy a verlo yo",
     "origen": "humano", "autor_nombre": "Ana Perez"},
    {"id": "m4", "rol": "assistant", "contenido": "conversacion reasignada",
     "origen": "sistema", "autor_nombre": None},
    {"id": "m5", "rol": "nota", "contenido": "llamar despues de las 6",
     "origen": "humano", "autor_nombre": "Ana Perez"},
    # La fila historica: nadie registro su origen y nadie puede saberlo.
    {"id": "m6", "rol": "assistant", "contenido": "de antes del registro",
     "origen": None, "autor_nombre": None},
]
datos, _ = leer(FILAS)
hilo = datos["mensajes"]
afirmar(len(hilo) == 6, "llegan las seis filas")

por_id = {m["id"]: m for m in hilo}
afirmar(por_id["m1"]["origen"] == "cliente", "cliente: origen='cliente'")
afirmar(por_id["m2"]["origen"] == "ia", "IA: origen='ia'")
afirmar(por_id["m3"]["origen"] == "humano", "humano: origen='humano'")
afirmar(por_id["m3"]["autor_nombre"] == "Ana Perez",
        "humano: viaja el nombre durable de quien escribio")
afirmar(por_id["m4"]["origen"] == "sistema", "sistema: origen='sistema'")
afirmar(por_id["m5"]["rol"] == "nota" and por_id["m5"]["origen"] == "humano",
        "nota interna: rol='nota' con origen='humano'")

# ── 4. LA PRUEBA CENTRAL: el NULL sigue siendo NULL ─────────────────────────
historica = por_id["m6"]
afirmar(historica["origen"] is None,
        "historica: el origen NULL se devuelve como None, sin rellenar")
afirmar(historica["origen"] not in ("ia", "humano", "sistema", "cliente"),
        "historica: NO se le atribuye ninguno de los cuatro origenes")
afirmar(historica["autor_nombre"] is None,
        "historica: tampoco se le inventa un autor")
# Y el rol no se usa para adivinar: es 'assistant', igual que la de la IA.
afirmar(historica["rol"] == "assistant" and por_id["m2"]["rol"] == "assistant"
        and historica["origen"] != por_id["m2"]["origen"],
        "dos filas con el MISMO rol quedan distinguidas por su origen")

# ── 5. autor_nombre ausente no rompe nada ───────────────────────────────────
afirmar(all("autor_nombre" in m for m in hilo),
        "todas las filas traen la clave autor_nombre, aunque valga None")
afirmar(sum(1 for m in hilo if m["autor_nombre"] is None) == 4,
        "las cuatro filas sin persona detras traen autor_nombre None")

print()
if fallos:
    print("FALLARON %d:" % len(fallos))
    for f in fallos:
        print("   - " + f)
    sys.exit(1)
print("D30: el hilo proyecta origen y autor, y un NULL sigue siendo NULL.")
