# -*- coding: utf-8 -*-
"""
Configuracion de gunicorn para el motor: lo que no cabe en la linea de comandos.

    gunicorn nucleo.canales.api:app --config python:nucleo.canales.gunicorn_conf ...

Hoy es una sola cosa: al salir el worker, esperar a los turnos en vuelo (ver
nucleo/canales/en_vuelo.py). El resto de las banderas sigue en el compose.

LOS TIEMPOS, Y SU ORDEN
-----------------------
  espera de turnos (<= 35 s)  <  graceful_timeout (40 s)  <  stop_grace_period (55 s)

gunicorn manda SIGKILL al worker cuando se cumplen 'graceful_timeout' segundos
desde el SIGTERM, y Docker se lo manda al contenedor a los 'stop_grace_period'.
Cada espera tiene que caber en la siguiente o la de adentro no sirve.

UN SOLO RELOJ PARA LAS DOS ESPERAS. El worker gthread primero espera a las
peticiones HTTP en curso (un /chat sincrono es un turno entero) y recien
despues llama a 'worker_exit'. Si la espera de turnos contara sus 35 s desde
ahi, un /chat de 20 s la dejaria morir a mitad por el SIGKILL de los 40 -- con
la linea "esperando" en el log y nunca la de "cortados". Por eso
'post_worker_init' anota la hora del SIGTERM, y 'worker_exit' espera solo lo
que queda hasta los 40, menos un margen para escribir el resumen.

Un turno con DeepSeek tarda 4,7-12 s (PRD 7.1); sin nadie en vuelo, 'esperar'
vuelve en el acto y el despliegue no se alarga.

El 'graceful_timeout' vive aca y no en el compose a proposito: si los dos
numeros estan en archivos distintos, se separan. tests/test_turnos_en_vuelo.py
comprueba que el compose no lo pise.
"""

from __future__ import annotations

import signal

graceful_timeout = 40

ESPERA_TURNOS_SEGUNDOS = 35

#: Lo que se le deja al worker para escribir el resumen y salir antes del
#: SIGKILL del arbitro.
MARGEN_SEGUNDOS = 3


def tope_de_espera(transcurrido: float) -> float:
    """Cuanto esperar a los turnos, sabiendo cuanto paso desde el SIGTERM."""
    return max(0.0, min(ESPERA_TURNOS_SEGUNDOS,
                        graceful_timeout - MARGEN_SEGUNDOS - transcurrido))


def post_worker_init(worker):
    """Envuelve el manejador del SIGTERM para anotar CUANDO llego.

    Corre despues de 'init_signals' (gunicorn/workers/base.py), asi que lo
    que se registra aca reemplaza al de gunicorn, que se sigue llamando.
    """
    from nucleo.canales import en_vuelo

    salir = worker.handle_exit

    def al_recibir_sigterm(sig, frame):
        en_vuelo.marcar_apagado()
        salir(sig, frame)

    worker.handle_exit = al_recibir_sigterm
    signal.signal(signal.SIGTERM, al_recibir_sigterm)
    # Lo que gunicorn pedia para su manejador: que el SIGTERM no corte las
    # llamadas al sistema de las peticiones en curso.
    if hasattr(signal, "siginterrupt"):          # no existe en Windows
        signal.siginterrupt(signal.SIGTERM, False)


def worker_exit(server, worker):
    from nucleo.canales import en_vuelo

    en_vuelo.esperar(tope_de_espera(en_vuelo.segundos_desde_el_apagado()))
