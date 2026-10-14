# -*- coding: utf-8 -*-
"""
================================================================================
 QUIEN ES DE QUE AREA, SEGUN LA CONFIGURACION DE LA EMPRESA
================================================================================

PARA QUE EXISTE
---------------
El Supervisor NOC lee tickets de SOPORTE TECNICO. Hasta el 14/10/2026 leia
todos, y el cliente lo vio enseguida: "revise la lista de soporte tecnico en
los ticket y no salen los ticket de descuentos programados, esos son de
cartera".

Tenia razon, y el numero lo confirmo: de los tickets abiertos, una sola persona
concentraba 563 --509 de ellos de cartera-- mientras la de soporte tenia 76,
exactamente los 76 que la pantalla de Tickets muestra para esa area.

POR QUE NO SE GUARDA EL AREA EN EL CASO, que fue el primer camino que se
intento: el caso no la tiene (ni columna, ni 'case_type', ni campos
personalizados), la importacion la calcula y la descarta, y agregarsela dejaria
sin area a los ~1.300 casos ya importados -- que es justo la cola que hay que
filtrar hoy.

LA PIEZA YA EXISTIA, y la encontro el cliente preguntando lo obvio: "los
tickets en Dexter si estan divididos bien... ¿no puede el supervisor extraer de
esa area los ticket sin tanto rodeo?". La pantalla de Tickets le pregunta al
motor que personas son de cada area y filtra por 'assigned_to'. Esto hace lo
mismo para el Supervisor.

EL AREA SALE DE LA PERSONA, no del ticket, y eso no es un rodeo: es como la
empresa la configura. Se edita desde la interfaz, y el dia que entre alguien
nuevo a soporte el Supervisor lo respeta sin tocar codigo.
================================================================================
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

#:  El area que le toca al Supervisor NOC. En la configuracion de Rapilink los
#:  departamentos 'Soporte Tecnico' Y 'Operativo' apuntan los dos a esta misma
#:  area, asi que un solo nombre cubre las dos cosas que se pidieron.
AREA_DEL_SUPERVISOR = "soporte_tecnico"

#:  Cuanto vale la lectura antes de volver a preguntar. Las areas cambian
#:  cuando entra o sale alguien del equipo -- no en minutos.
SEGUNDOS_DE_CACHE = 15 * 60

#:  Mas que suficiente para una lectura local del motor, y corto para que un
#:  motor trabado no deje al ciclo esperando: el ciclo ya tarda seis minutos.
ESPERA_MAXIMA = 5


def _motor():
    """Donde vive el motor y con que se le habla. Igual que telemetria.py."""
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or ""
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, tenant, cabeceras


def area_por_persona() -> dict:
    """
    {profile_id: area} tal como lo declara la configuracion de la empresa.

    Devuelve {} cuando no se puede saber, y quien llama tiene que distinguir
    ESO de "nadie es de esa area": son cosas distintas y la diferencia decide
    si se lee un ticket ajeno.
    """
    from django.core.cache import cache

    clave = "areas_por_persona"
    try:
        guardado = cache.get(clave)
        if guardado is not None:
            return guardado
    except Exception:                                        # noqa: BLE001
        pass

    base, tenant, cabeceras = _motor()
    if not tenant:
        #  FAIL-CLOSED CON EL TENANT, igual que en el resto del proyecto: sin
        #  saber de que empresa es, preguntar por sus areas devolveria las de
        #  otra.
        logger.info("Supervisor: falta MOTOR_TENANT, no se consultan areas")
        return {}

    #  Se prueba el liviano y se cae al viejo, igual que la pantalla de
    #  Tickets: '/agentes/asignaciones' devuelve lo mismo y ademas sale a
    #  consultar al sistema externo, que aqui no hace falta.
    for ruta in ("/agentes/areas", "/agentes/asignaciones"):
        try:
            r = requests.get(f"{base}{ruta}", params={"tenant": tenant},
                             headers=cabeceras, timeout=ESPERA_MAXIMA)
        except Exception as e:                               # noqa: BLE001
            logger.info("Supervisor: no se pudieron leer las areas (%s)",
                        type(e).__name__)
            return {}
        if r.status_code == 404:
            continue
        if not r.ok:
            logger.info("Supervisor: el motor respondio %s a las areas",
                        r.status_code)
            return {}
        try:
            mapa = (r.json() or {}).get("areas_por_persona") or {}
        except Exception:                                    # noqa: BLE001
            return {}
        try:
            cache.set(clave, mapa, SEGUNDOS_DE_CACHE)
        except Exception:                                    # noqa: BLE001
            pass
        return mapa
    return {}


def responsables_de(area: str, mapa: dict | None = None) -> list:
    """
    Los perfiles que pertenecen a esa area.

    Lista vacia significa "no hay nadie de esa area" O "no se pudo preguntar".
    Quien llama no puede tratar las dos igual: filtrar por una lista vacia no
    filtra nada y traeria la cola entera -- que es exactamente lo que este
    modulo vino a evitar.
    """
    m = area_por_persona() if mapa is None else mapa
    objetivo = str(area or "").strip().lower()
    return [pid for pid, suya in (m or {}).items()
            if str(suya or "").strip().lower() == objetivo]
