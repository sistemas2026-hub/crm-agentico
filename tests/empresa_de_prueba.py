# -*- coding: utf-8 -*-
"""Sembrar una empresa de mentira en `public.organization`, sin saber su forma.

POR QUE EXISTE  --  medido el 13/11/2026
----------------------------------------
`insert into public.organization (name) values ('ISP A')` pasa contra la base
de produccion y **falla contra un esquema recien migrado por Django**:

    null value in column "created_at" violates not-null constraint

No es un bug de la prueba ni de la migracion: `auto_now_add=True` llena esa
columna en PYTHON, no en la base, asi que produccion tiene un default que las
migraciones del repo no crean. Decidido el 12/11/2026 --y no se reabre-- que el
esquema de produccion NO se toca por esto: la aplicacion de Django no se usa.
Entonces el arreglo vive aca, del lado de las pruebas.

Eso es lo que mantenia a las **88 pruebas de base afuera del CI** (D1 de
CLAUDE.md): con la base levantada, 38 de 88 morian por el entorno y no por un
defecto. Ver la cabecera de `.github/workflows/pruebas.yml`.

POR QUE UN SOLO MODULO, Y NO LA LISTA DE COLUMNAS EN CADA PRUEBA
---------------------------------------------------------------
Cuando se escribio esto ya habia **cuatro** soluciones distintas al mismo
problema, en cuatro archivos:

  * `test_alertas.py`      le pregunta al esquema (la mejor, y es de donde sale esto)
  * `test_b4_sincronizaciones.py` le pregunta al esquema, con otros rellenos
  * `test_encuestas_base.py`     22 columnas escritas a mano
  * `test_m06f_integracion_postgres.py`  23 escritas a mano -- una mas que la anterior

Las dos ultimas pasan hoy y se rompen el dia que `organization` gane una
columna obligatoria. Que las listas ya difieran entre si (`correo_solicitudes`
esta en una y no en la otra) es la prueba de que derivan solas.

LO QUE NO HACE
--------------
No crea la tabla ni abre conexiones: recibe un cursor ya abierto, porque cada
prueba de base tiene su propia forma de conectarse (`crudo()`, `sql()`, un
cursor de psycopg suelto) y unificar eso es otro trabajo.
"""
from __future__ import annotations

#: Relleno por tipo, como EXPRESION SQL --no como parametro--: asi el insert se
#: arma sin tocar la lista de valores que pasa cada prueba.
_RELLENO = {
    "timestamp with time zone": "now()",
    "timestamp without time zone": "now()",
    "date": "current_date",
    "boolean": "false",
    "uuid": "gen_random_uuid()",
    "jsonb": "'{}'::jsonb",
    "json": "'{}'::json",
    "ARRAY": "'{}'",
    "integer": "0",
    "bigint": "0",
    "smallint": "0",
    "numeric": "0",
    "double precision": "0",
    "real": "0",
}

_CONSULTA = """
select column_name, data_type, character_maximum_length
  from information_schema.columns
 where table_schema = 'public' and table_name = 'organization'
   and is_nullable = 'NO' and column_default is null
   and column_name <> all(%s)
 order by column_name
"""


def _filas(cur, ya_tengo) -> list[tuple[str, str, int | None]]:
    """Normaliza las filas, que llegan de tres formas distintas.

    `cur` puede ser un cursor O UNA CONEXION: `test_ejecuciones_con_base` y
    `test_eventos_cursor_con_base` pasan la conexion, y
    `psycopg.Connection.execute()` devuelve un cursor nuevo en vez de la
    conexion --que no tiene `fetchall`--. La primera version leia
    `cur.fetchall()` y reventaba con `'Connection' object has no attribute
    'fetchall'`; se vio recien al CORRER las pruebas, porque la prueba del
    propio modulo solo le pasaba un cursor.

    Y las filas vienen de `dict_row` en unas pruebas y de tuplas en otras.
    """
    devuelto = cur.execute(_CONSULTA, (list(ya_tengo),))
    fuente = devuelto if hasattr(devuelto, "fetchall") else cur
    salida = []
    for f in fuente.fetchall():
        if isinstance(f, dict):
            salida.append((f["column_name"], f["data_type"],
                           f["character_maximum_length"]))
        else:
            salida.append((f[0], f[1], f[2]))
    return salida


def extras(cur, *, ya_tengo=("name",)) -> tuple[str, str]:
    """Las columnas obligatorias que faltan, listas para pegar en el insert.

    Devuelve `(", col_a, col_b", ", now(), 'x'")` --con la coma adelante-- o
    `("", "")` cuando la tabla no exige nada mas, que es el caso de las cuatro
    pruebas que se arman su propia `organization` minima.

        c, v = extras(cur)
        cur.execute(f"insert into public.organization (name{c}) "
                    f"values (%s{v}) returning id", (nombre,))

    `ya_tengo` son las columnas que la prueba escribe ella misma, y por eso
    quedan fuera del relleno. **`id` NO esta ahi por defecto, a proposito**:
    tambien es `not null` sin default en el esquema que arma Django --el UUID
    lo pone Django en Python, igual que `created_at`-- y la primera version de
    este modulo lo excluia. El insert fallaba por `id` en vez de por
    `created_at`: el mismo defecto una columna mas adelante, y lo encontro una
    prueba que insertaba de verdad en vez de mirar el texto del SQL. Quien
    fije el id de antemano pasa `ya_tengo=("id", "name")`.
    """
    columnas, valores = [], []
    for nombre, tipo, largo in _filas(cur, ya_tengo):
        relleno = _RELLENO.get(tipo)
        if relleno is None:
            #  Texto. Un `''` chocaria con la restriccion UNIQUE de `api_key`
            #  en cuanto haya dos empresas de prueba, asi que cada una recibe
            #  un valor propio, recortado a lo que la columna admite.
            n = min(int(largo or 36), 36)
            relleno = f"left(gen_random_uuid()::text, {n})"
        columnas.append(nombre)
        valores.append(relleno)
    if not columnas:
        return "", ""
    return ("".join(f", {c}" for c in columnas),
            "".join(f", {v}" for v in valores))
