# -*- coding: utf-8 -*-
"""
================================================================================
 El proceso que corre T20  (B4)
================================================================================

    python -m nucleo.relevo.worker_reconciliador --once
    python -m nucleo.relevo.worker_reconciliador --once --dry-run
    python -m nucleo.relevo.worker_reconciliador            (daemon)

POR QUE UN PROCESO APARTE
-------------------------
El 'motor-reloj' corre cada ~60 minutos y los plazos que la cola tiene que
cumplir son de 10 y 15 (§14.1 Q4). Bajar ese reloj para esto moveria TODAS las
tareas periodicas del motor -- el cierre de vencidas, la importacion, el
barrido operativo-- que no piden esa frecuencia y que cuestan bastante mas que
una consulta a un indice parcial.

Asi que T20 vive aparte, cada 5 minutos, y en cada vuelta mira solo lo que ya
vencio. Un ciclo sin trabajo elegible es una consulta y nada mas.

EL INTERRUPTOR
--------------
'RECONCILIADOR_HABILITADO' tiene que valer exactamente '1'. Propio, y no el del
reloj general: encender uno no puede encender el otro por descuido, y este toca
sistemas externos.

En daemon se lee UNA VEZ, al arrancar, igual que el reloj general: el entorno
de un proceso ya arrancado no cambia solo, y consultarlo en cada vuelta
prometeria una capacidad que no existe. '--once' si lo lee en el momento, para
poder hacer un smoke dentro del contenedor sin tocar lo que Dokploy guarda.

Encenderlo en produccion es el gate G7, y no se hace desde aca.
"""

from __future__ import annotations

import os
import sys
import time

from nucleo.observabilidad.registro import registrar
from nucleo.relevo import reconciliador

#: Cada cuanto trabaja. Es la cadencia que §3.6 pide (1 a 5 minutos).
INTERVALO_SEGUNDOS = reconciliador.CADENCIA_SEGUNDOS

#: Cuantos trabajos por vuelta y por tenant. Un tope bajo a proposito: la cola
#: se vacia en varias vueltas de cinco minutos en vez de en una sola que
#: mantiene abiertas decenas de conexiones a sistemas externos.
POR_VUELTA = 50


def encendido() -> bool:
    return os.environ.get("RECONCILIADOR_HABILITADO", "0").strip() == "1"


def _tenants() -> list[str]:
    from nucleo.reloj import tenants_conocidos
    return list(tenants_conocidos())


def _ejecutor_de(tenant: str):
    """
    Con que se ejecuta cada efecto en este tenant.

    Devuelve None cuando el tenant no tiene con que hacerlo -- sin catalogo o
    sin la herramienta del caso. Un tenant asi NO se procesa: tomar sus
    trabajos solo para fallarlos les gastaria los intentos y los dejaria en
    'fallida_definitiva' por una razon que no es suya.
    """
    from nucleo.canales.api import _config_de
    from nucleo.herramientas import http as herramientas_http
    from nucleo.relevo import efectos_externos
    from nucleo.seguimiento import escalamiento

    try:
        config = _config_de(tenant)
    except Exception as e:
        registrar("reconciliador", "sin configuracion: el tenant no se procesa",
                  tenant=tenant, error=e)
        return None

    herramienta = next((h for h in config.herramientas
                        if h.nombre == escalamiento.NOMBRE_HERRAMIENTA_CASO_CREAR), None)
    if not herramienta:
        registrar("reconciliador", "el tenant no tiene la herramienta de crear caso",
                  tenant=tenant)
        return None

    def crear(nombre: str, datos: dict):
        respuesta = herramientas_http.ejecutar(herramienta, {
            "name": nombre,
            "description": (datos or {}).get("descripcion") or nombre,
            "status": "New", "case_type": "Question", "priority": "Normal",
        })
        return respuesta.get("id") if isinstance(respuesta, dict) else None

    def buscar_por_nombre(nombre: str):
        # El caso se busca por su nombre exacto, que lleva el conversation_id y
        # es unico por organizacion. Si el catalogo del tenant no declara una
        # herramienta de busqueda, esto devuelve None y el efecto se reintenta
        # entero mas tarde -- nunca se crea a ciegas.
        buscador = next((h for h in config.herramientas
                         if getattr(h, "busca_caso", False)), None)
        if not buscador:
            return None
        respuesta = herramientas_http.ejecutar(buscador, {"name": nombre})
        if isinstance(respuesta, dict):
            filas = respuesta.get("results") or respuesta.get("cases") or []
            for fila in filas:
                if isinstance(fila, dict) and fila.get("name") == nombre:
                    return fila.get("id")
        return None

    return efectos_externos.ejecutor(config, tenant,
                                     crear=crear, buscar_por_nombre=buscar_por_nombre)


def una_vuelta(*, seco: bool = False) -> dict:
    """Una pasada por todos los tenants. Devuelve el conteo agregado."""
    total: dict[str, int] = {}
    for tenant in _tenants():
        if seco:
            try:
                pendientes = len(reconciliador.db.sincronizaciones_elegibles(tenant, POR_VUELTA))
            except Exception as e:
                registrar("reconciliador", "no se pudo leer la cola", tenant=tenant, error=e)
                continue
            registrar("reconciliador", "dry-run: trabajos elegibles",
                      tenant=tenant, elegibles=pendientes)
            total["elegibles"] = total.get("elegibles", 0) + pendientes
            continue

        # El barrido de acciones va PRIMERO y fuera del if: no toca ningun
        # sistema externo, asi que un tenant sin ejecutor --sin catalogo, sin
        # la herramienta del caso-- igual tiene que poder cerrar lo que quedo
        # colgado. Dejarlo dentro del if lo condicionaria a algo que no
        # necesita, y esas acciones quedarian 'ejecutando' para siempre.
        for estado, n in reconciliador.barrer_acciones(tenant, POR_VUELTA).items():
            total[estado] = total.get(estado, 0) + n

        ejecutar = _ejecutor_de(tenant)
        if ejecutar is None:
            continue
        for estado, n in reconciliador.correr(tenant, ejecutar, POR_VUELTA).items():
            total[estado] = total.get(estado, 0) + n
    return total


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    desconocidos = [a for a in argv if a not in ("--once", "--dry-run")]
    if desconocidos:
        registrar("reconciliador", "argumentos desconocidos: solo --once y --dry-run")
        return 2
    una_vez = "--once" in argv
    seco = "--dry-run" in argv
    if seco and not una_vez:
        registrar("reconciliador", "--dry-run solo tiene sentido junto con --once.")
        return 2

    if una_vez:
        if not encendido():
            registrar("reconciliador", "RECONCILIADOR_HABILITADO=0: no se hace nada.")
            return 0
        registrar("reconciliador", "pasada suelta", **una_vuelta(seco=seco))
        return 0

    registrar("reconciliador", "worker iniciado")
    # Texto fijo por estado, y no un campo: 'RECONCILIADOR_HABILITADO=0' es lo
    # que se busca en el log del contenedor para saber si arranco apagado.
    # Mismo criterio que el reloj general (y lo exige test_registro_sin_pii).
    if encendido():
        registrar("reconciliador", "RECONCILIADOR_HABILITADO=1")
    else:
        registrar("reconciliador", "RECONCILIADOR_HABILITADO=0")
    if not encendido():
        # Inerte pero vivo: un proceso que imprime y termina lo reinicia Docker
        # una y otra vez. Mismo criterio que el reloj general.
        registrar("reconciliador", "worker inerte: no se procesa ningun efecto. Para "
                                   "encenderlo, RECONCILIADOR_HABILITADO=1 (redespliega).")
        while True:
            time.sleep(INTERVALO_SEGUNDOS)

    registrar("reconciliador", "worker activo", intervalo_seg=INTERVALO_SEGUNDOS)
    while True:
        # Duerme PRIMERO: al desplegar, el proceso no dispara en el segundo
        # cero contra sistemas externos que quiza siguen levantandose.
        time.sleep(INTERVALO_SEGUNDOS)
        try:
            conteo = una_vuelta()
            if conteo:
                registrar("reconciliador", "vuelta completa", **conteo)
        except Exception as e:
            # Una vuelta que falla no puede matar el worker: la siguiente
            # vuelve a intentarlo en cinco minutos.
            registrar("reconciliador", "fallo una vuelta completa", error=e)


if __name__ == "__main__":
    raise SystemExit(main())
