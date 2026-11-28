# -*- coding: utf-8 -*-
"""
La guarda de las pruebas que siembran empresas: solo contra una base local.

Una prueba que inserta en asistente.tenant_config crea una empresa y una
organizacion. Contra produccion, si se corta antes de limpiar, esa empresa
queda: el reloj la lista en cada vuelta y el CRM la muestra como organizacion
activa. Paso con cuatro (ver tests/test_base_local.py).

Local es lo que no sale de la maquina: localhost, el socket (DBHOST vacio), y
un nombre sin punto -- el servicio de un compose o un contenedor de descarte
(db, pg-b7, pg-deploy-311). Un nombre con dominio o una IP de red no lo son.

No hay variable para saltearla: sembrar empresas falsas en una base real no
tiene un caso legitimo. Quien necesite medir produccion, lo hace en solo
lectura y sin estas pruebas.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

_LOCALES = {"", "localhost", "127.0.0.1", "::1", "host.docker.internal"}


def es_local(host: str) -> bool:
    host = (host or "").strip().lower()
    return host in _LOCALES or "." not in host


def host_de(dsn: str) -> str:
    """El host de un DSN, en forma URL (postgres://u:p@host:5432/db) o
    clave=valor (host=... port=...)."""
    dsn = (dsn or "").strip()
    if "://" in dsn:
        return urlsplit(dsn).hostname or ""
    for parte in dsn.split():
        if parte.startswith("host="):
            return parte[len("host="):]
    return ""


def exigir_base_local(prueba: str, dsn: str | None = None) -> None:
    """Corta la prueba (exit 0, OMITIDA) si la base no es local. Llamarla
    ANTES de abrir la primera conexion.

    Mira DBHOST, salvo que la prueba se conecte con un DSN propio (por ejemplo
    RELOJ_PG_ADMIN): entonces mira el host de ese DSN, que es el que va a usar.
    """
    host = host_de(dsn) if dsn is not None else os.environ.get("DBHOST", "")
    if es_local(host):
        return
    print(f"[{os.path.basename(prueba)}] OMITIDA: la base configurada ({host}) no es "
          f"local y esta prueba siembra empresas en ella. Correrla contra una base "
          f"de descarte (cli/base_desde_cero.py).", flush=True)
    raise SystemExit(0)
