# -*- coding: utf-8 -*-
"""
================================================================================
 TURNOS EN VUELO  --  que un despliegue no se coma un mensaje a medio atender
================================================================================

El webhook de WhatsApp registra el wamid como visto, le contesta 200 a Meta y
recien despues atiende el mensaje, en un hilo aparte (ver la nota de ACK en
nucleo/canales/api.py::whatsapp_webhook). Meta no reintenta un mensaje al que
ya se le contesto 200, y el texto del cliente solo vive en la memoria de ese
hilo hasta que el turno lo guarda.

Medido el 31/10/2026 con el gunicorn de produccion: llega el SIGTERM de un
despliegue, el worker sale EN EL ACTO y el hilo daemon muere a mitad del turno.
Al cliente no le llega nada, el log no dice nada, y la base solo tiene el
wamid marcado como visto. Con el autodeploy pasa en cada push que encuentre un
turno andando.

Que hace esto
-------------
'lanzar' arranca el hilo y lo anota; al terminar --bien o mal-- se borra solo.
'esperar' lo llama gunicorn al salir el worker (nucleo/canales/gunicorn_conf.py)
y espera a los anotados hasta un tope. Lo que no termino a tiempo queda
NOMBRADO en el log: se corta igual, pero deja de ser un silencio.

Tres cosas que la primera version hacia mal (auditoria independiente del mismo
dia), y por que la forma de abajo:

  - Miraba UNA foto de los hilos. Un turno que al terminar lanza su traza
    dejaba a la traza afuera, y el log decia "todos terminaron" con ella viva.
    Ahora 'esperar' vuelve a mirar hasta que no quede nadie o se acabe el tope.
  - El nombre del hilo iba al log como texto, y la redaccion lo tapaba cuando
    la huella traia siete digitos seguidos (~11 % de las veces). Ahora cada
    hilo se anota con su 'ref' -- una Referencia o un id interno, que el
    registro deja pasar --, y el nombre queda para depurar.
  - 'apagando()' existe para que un trabajo que todavia no empezo su efecto
    (la autonomia ganada duerme unos segundos antes de actuar) no lo empiece
    con el proceso saliendo.

Por que los hilos siguen siendo daemon
--------------------------------------
Un hilo no-daemon tambien retrasaria la salida, pero sin tope ni rastro: el
interprete lo espera en silencio hasta que gunicorn manda el SIGKILL. Aca la
espera es explicita, acotada y dice que corto.

Que NO resuelve
---------------
Un turno mas largo que el tope, o un proceso que muere sin SIGTERM (OOM, un
SIGKILL), sigue perdiendo su mensaje. Para eso hace falta guardar el mensaje
ANTES de contestarle a Meta, que es otra decision (PRD 8.17).
================================================================================
"""

from __future__ import annotations

import threading
import time

from nucleo.observabilidad.registro import registrar

_en_vuelo: dict[threading.Thread, object] = {}
_candado = threading.Lock()
_apagado = threading.Event()
_apagado_desde: list[float] = []


def lanzar(objetivo, *args, nombre: str, ref=None) -> threading.Thread:
    """
    Corre 'objetivo(*args)' en un hilo propio, anotado hasta que termine.

    'ref' es lo que nombra al hilo en el log si hay que cortarlo: la huella del
    mensaje (ref_proveedor) o el id interno de la conversacion, nunca un dato
    de cliente. Sin 'ref' se usa 'nombre', que tiene que ser texto fijo.
    """
    def correr():
        try:
            objetivo(*args)
        finally:
            with _candado:
                _en_vuelo.pop(threading.current_thread(), None)

    hilo = threading.Thread(target=correr, name=nombre, daemon=True)
    with _candado:
        _en_vuelo[hilo] = ref if ref is not None else nombre
    hilo.start()
    return hilo


def marcar_apagado() -> None:
    """El proceso empezo a salir. Se anota la hora UNA vez: la primera."""
    with _candado:
        if not _apagado_desde:
            _apagado_desde.append(time.monotonic())
    _apagado.set()


def apagando() -> bool:
    """True desde que llego el SIGTERM. Para no EMPEZAR un efecto saliendo."""
    return _apagado.is_set()


def segundos_desde_el_apagado() -> float:
    with _candado:
        return time.monotonic() - _apagado_desde[0] if _apagado_desde else 0.0


def esperar(tope_segundos: float) -> dict:
    """
    Espera a los turnos en vuelo -- y a los que ellos lancen mientras tanto --
    hasta 'tope_segundos' en total.

    Avisa ANTES de esperar: si gunicorn mata el proceso en el medio, en el log
    queda cuantos habia, que es lo que hace falta para saber que algo se
    perdio.
    """
    marcar_apagado()
    limite = time.monotonic() + max(0.0, tope_segundos)
    vistos: dict[threading.Thread, object] = {}
    avisado = False
    while True:
        with _candado:
            vivos = dict(_en_vuelo)
        vistos.update(vivos)
        if not vivos or time.monotonic() >= limite:
            break
        if not avisado:
            registrar("motor", "apagado: esperando turnos en vuelo", cuantos=len(vivos),
                      tope_s=round(tope_segundos, 1))
            avisado = True
        for hilo in vivos:
            hilo.join(max(0.0, limite - time.monotonic()))
    cortados = [ref for hilo, ref in vistos.items() if hilo.is_alive()]
    cuentas = {"habia": len(vistos), "terminaron": len(vistos) - len(cortados),
               "cortados": cortados}
    if cortados:
        registrar("motor", "apagado: turnos cortados sin terminar", habia=len(vistos),
                  terminaron=len(vistos) - len(cortados), cortados=cortados)
    elif vistos:
        registrar("motor", "apagado: todos los turnos en vuelo terminaron",
                  habia=len(vistos))
    return cuentas
