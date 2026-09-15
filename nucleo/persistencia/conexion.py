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

# Quien abre la conexion, tal como se vera en pg_stat_activity.application_name.
# No es cosmetico: el 15/09/2026 tres sesiones quedaron 'idle in transaction'
# -una casi ocho dias- y bloquearon una migracion, y no se pudo saber que
# proceso las habia abierto porque TODAS llegan firmadas 'Supavisor', que es el
# pooler por el que pasan. Con esto, la proxima vez la respuesta esta en la
# misma consulta que detecta el problema.
#
# Se declara por entorno (DB_APPLICATION_NAME) y no se deduce del proceso: el
# motor y el reloj corren el mismo codigo desde la misma imagen, asi que
# adivinarlo daria el mismo nombre para los dos. El compose le pone
# 'dexter-motor' y 'dexter-reloj'; cada CLI pone el suyo al arrancar.
_APP_POR_DEFECTO = "dexter"

# Nombres de host que son inequivocamente locales: el servicio 'db' del
# compose de desarrollo, o localhost fuera de Docker. Cualquier otro valor de
# DBHOST es una base remota -- hoy, en la practica, siempre el Supabase de
# produccion, porque es el unico Postgres que corre fuera de un contenedor
# local (ver DESPLIEGUE.md, "Desarrollo local contra la base real").
_HOSTS_LOCALES = {"db", "localhost", "127.0.0.1"}

# Se avisa UNA vez por proceso, no en cada conexion: el motor abre una por
# turno (nucleo/persistencia/db.py), y repetir el aviso en cada mensaje lo
# volveria ruido que se deja de leer -- justo lo que no debe pasar con esta
# advertencia en particular.
_avisado_remoto = False


def nombre_de_aplicacion() -> str:
    """
    El valor que va a aparecer en pg_stat_activity.application_name.

    Vacio o sin definir cae a 'dexter': es preferible una firma generica a
    ninguna, porque sin ella la sesion es indistinguible del pooler.
    """
    return (os.environ.get("DB_APPLICATION_NAME") or "").strip() or _APP_POR_DEFECTO


def _firmada(url: str) -> str:
    """
    La misma cadena, con application_name puesto.

    Si quien configuro DATABASE_URL ya lo declaro, manda el suyo: es mas
    especifico que nuestro valor por defecto y no hay motivo para pisarlo.
    """
    if "application_name=" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}application_name={quote(nombre_de_aplicacion(), safe='')}"


def dsn() -> str:
    """
    postgresql://usuario:clave@host:puerto/base?application_name=...

    La contraseña se codifica: las de Supabase traen '+' y '/' con frecuencia,
    y sin codificar rompen la URL de formas que no se notan hasta que fallan.
    """
    global _avisado_remoto
    if os.environ.get("DBHOST"):
        faltan = [v for v in _PARTES if not os.environ.get(v)]
        if faltan:
            raise SystemExit(
                f"Conexion incompleta: falta {', '.join(faltan)} en el entorno. "
                f"Se necesitan las cinco: {', '.join(_PARTES)}.")

        host = os.environ["DBHOST"]
        if not _avisado_remoto and host not in _HOSTS_LOCALES:
            # No se puede distinguir en codigo "Supabase de produccion" de
            # "Supabase de otro entorno": el motor solo ve un host y cinco
            # credenciales. Avisar siempre que no sea local es la version
            # fail-safe -- ver DESPLIEGUE.md antes de asumir que es inofensivo.
            print(f"[conexion] DBHOST={host}: esto NO es la base local del "
                  f"compose. Cada escritura de este proceso (mensajes, "
                  f"tool_calls, config editada desde /agentes) va a esa base "
                  f"de verdad, no a una copia.")
            _avisado_remoto = True

        usuario = quote(os.environ["DBUSER"], safe="")
        clave = quote(os.environ["DBPASSWORD"], safe="")
        return _firmada(f"postgresql://{usuario}:{clave}"
                        f"@{os.environ['DBHOST']}:{os.environ['DBPORT']}"
                        f"/{os.environ['DBNAME']}")

    url = os.environ.get("DATABASE_URL")
    if url:
        return _firmada(url)

    raise SystemExit(
        "No hay datos de conexion en el entorno. Definir DBHOST, DBPORT, "
        "DBNAME, DBUSER y DBPASSWORD en el .env (las mismas que usa el CRM).")
