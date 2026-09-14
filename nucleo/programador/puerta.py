# -*- coding: utf-8 -*-
"""
================================================================================
 LA PUERTA  --  lo unico que el proceso puede hacerle a la base
================================================================================

Aqui no hay SQL del scheduler. Hay nueve llamadas a funciones y nada mas.

Por que importa que este modulo sea aburrido
--------------------------------------------
Si en algun momento aparece aca un 'update asistente.job_schedule_state ...',
todo el diseño de la migracion de funciones deja de significar algo: las
invariantes dejan de estar garantizadas por la base y pasan a depender de que
este archivo siga bien escrito. Por eso los roles de runtime no tienen GRANT
sobre las tablas -- un SQL directo aca no fallaria en la revision, fallaria en
produccion, con un 'permission denied' y sin corromper nada.

El rol se pone por conexion
---------------------------
Cada fase asume su rol con 'set role' y no lo suelta: el coordinador nunca
tiene permiso de finalizar y el ejecutor nunca tiene permiso de reclamar, ni
por un instante. La membresia la da el operador sobre el usuario de login
('grant scheduler_coordinator to <usuario>'), no estas lineas.
================================================================================
"""

from __future__ import annotations

import contextlib
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from nucleo.persistencia import conexion

# Los tres roles de runtime. Cerrado a proposito: el rol nunca sale de una
# variable de entorno ni de un parametro de usuario.
COORDINADOR = "scheduler_coordinator"
EJECUTOR = "job_executor"
MONITOR = "monitor_ro"
_ROLES = (COORDINADOR, EJECUTOR, MONITOR)


@contextlib.contextmanager
def sesion(rol: str) -> Iterator[psycopg.Cursor]:
    """Una conexion con el rol puesto. Se cierra al salir, pase lo que pase."""
    if rol not in _ROLES:
        raise ValueError(f"rol desconocido: {rol!r}")
    con = psycopg.connect(conexion.dsn(), row_factory=dict_row)
    try:
        with con.cursor() as cur:
            cur.execute(f"set role {rol}")
            yield cur
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


# -----------------------------------------------------------------------------
#  coordinador
# -----------------------------------------------------------------------------

def vencidos(cur, limite: int = 100) -> list[dict]:
    cur.execute("select * from asistente.jobs_vencidos(now(), %s)", (limite,))
    return cur.fetchall()


def reclamar(cur, job_code: str, organization_id, slot, worker_id: str,
             inputs: dict | None = None) -> dict | None:
    """
    El turno reclamado, o None si no se pudo.

    None NO es un error: quiere decir que otro coordinador llego primero, que
    el lease seguia vivo, o que la lectura de 'vencidos' ya estaba vieja. Son
    tres formas normales de perder una carrera.
    """
    import json

    cur.execute("select * from asistente.job_claim(%s,%s,%s,%s,%s)",
                (job_code, organization_id, slot, worker_id,
                 json.dumps(inputs or {})))
    filas = cur.fetchall()
    return filas[0] if filas else None


# -----------------------------------------------------------------------------
#  ejecutor
# -----------------------------------------------------------------------------

def abrir_contexto(cur, attempt_id, capability: str):
    """
    Fija 'app.current_tenant' con la organizacion que salio del claim.

    No es una contencion: 'app.current_tenant' es un GUC USERSET y cualquier
    rol puede fijarlo. Lo que evita es que el ejecutor ELIJA el tenant -- lo
    deriva del turno que le tocó.
    """
    cur.execute("select asistente.job_abrir_contexto(%s,%s) as org",
                (attempt_id, capability))
    return cur.fetchone()["org"]


def latir(cur, attempt_id, capability: str):
    """El nuevo vencimiento del lease, o None si el turno ya no es tuyo."""
    cur.execute("select asistente.job_heartbeat(%s,%s) as hasta",
                (attempt_id, capability))
    return cur.fetchone()["hasta"]


def finalizar(cur, attempt_id, capability: str, outcome: str,
              error_code: str | None = None) -> str | None:
    """
    El desenlace REGISTRADO, que puede no ser el reportado: un
    'failed_retryable' en el ultimo intento se registra 'failed_terminal'.

    None quiere decir que el intento ya no era el vigente -- se llego tarde.
    """
    cur.execute("select asistente.job_finalize(%s,%s,%s,%s) as fin",
                (attempt_id, capability, outcome, error_code))
    return cur.fetchone()["fin"]


# -----------------------------------------------------------------------------
#  monitor
# -----------------------------------------------------------------------------

def salud(cur) -> list[dict]:
    """Agregados por job. Ni una columna que diga de quien son."""
    cur.execute("select * from asistente.job_salud(now())")
    return cur.fetchall()
