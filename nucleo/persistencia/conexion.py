# -*- coding: utf-8 -*-
"""
================================================================================
 CONEXION  --  una sola fuente para la cadena de Postgres
================================================================================

Por que existe
--------------
La plataforma son dos bases de codigo que nombran la misma conexion distinto:
el motor pedia DATABASE_URL (una cadena con todo adentro) y Django pide cinco
variables sueltas (DBHOST, DBPORT, DBNAME, DBUSER, DBPASSWORD, ver
django-crm/backend/crm/settings.py).

Eso dejaba la MISMA contraseña de la MISMA base escrita en dos archivos y en
dos formatos. El dia que se rota, hay que acordarse de los dos; si se
actualiza uno solo, media plataforma sigue andando y la otra media falla --
la peor forma de fallar, porque parece que funciono.

Aqui la fuente son las cinco variables, que son las que Django necesita de
todas formas, y la cadena se compone. El compose se las pasa a Django con sus
nombres y al motor por env_file, asi que nadie las escribe dos veces.

DATABASE_URL sigue funcionando como respaldo, para no romper una copia local
que todavia la tenga. Si estan las dos, mandan las partes: son las que ve el
CRM, y que el motor y el CRM apunten a bases distintas sin avisar es
exactamente lo que esto viene a evitar.
================================================================================
"""

from __future__ import annotations

import os
from urllib.parse import quote

_PARTES = ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")


def dsn() -> str:
    """
    postgresql://usuario:clave@host:puerto/base

    La contraseña se codifica: las de Supabase traen '+' y '/' con frecuencia,
    y sin codificar rompen la URL de formas que no se notan hasta que fallan.
    """
    if os.environ.get("DBHOST"):
        faltan = [v for v in _PARTES if not os.environ.get(v)]
        if faltan:
            raise SystemExit(
                f"Conexion incompleta: falta {', '.join(faltan)} en el entorno. "
                f"Se necesitan las cinco: {', '.join(_PARTES)}.")
        usuario = quote(os.environ["DBUSER"], safe="")
        clave = quote(os.environ["DBPASSWORD"], safe="")
        return (f"postgresql://{usuario}:{clave}"
                f"@{os.environ['DBHOST']}:{os.environ['DBPORT']}"
                f"/{os.environ['DBNAME']}")

    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    raise SystemExit(
        "No hay datos de conexion en el entorno. Definir DBHOST, DBPORT, "
        "DBNAME, DBUSER y DBPASSWORD en el .env (las mismas que usa el CRM).")
