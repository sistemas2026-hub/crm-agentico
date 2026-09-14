# -*- coding: utf-8 -*-
"""
================================================================================
 EL EJECUTOR  --  hace UN turno y reporta que paso
================================================================================

Recibe un turno ya reclamado (no lo elige), abre el contexto del tenant que
salio del claim, mantiene vivo el lease mientras trabaja, y reporta el
desenlace. No decide que le toca y no tiene permiso para reclamar.

EL LATIDO VA EN SU PROPIA CONEXION
----------------------------------
Compartir la conexion con el trabajo seria imposible: mientras el trabajo tiene
una transaccion abierta, el latido no puede ejecutar nada. Y el latido tiene
que poder correr JUSTO cuando el trabajo esta tardando, que es cuando hace
falta. Dos conexiones.

QUE PASA CUANDO SE PIERDE EL LEASE
----------------------------------
El latido devuelve None y el ejecutor lo marca en un Event. El trabajo lo mira
si quiere -- un trabajo largo y particionado deberia-- y de todas formas el
'finalize' final va a devolver None, porque el intento ya no es el vigente.

Lo que NO se hace es matar el hilo del trabajo. Matar un hilo a mitad de un
POST al proveedor deja el efecto hecho y el registro sin escribir, que es peor
que la duplicacion que se querria evitar. El contrato es at-least-once, no
exactly-once, y esto es una de las razones por las que lo es.

CADA TRABAJO DECIDE SI SU FALLO ES REINTENTABLE
-----------------------------------------------
Un timeout del proveedor lo es. Una config invalida no: reintentarla cuatro
veces con backoff no la va a arreglar y solo retrasa el turno siguiente. Por
eso el trabajo puede levantar 'FalloTerminal' y el resto de las excepciones se
tratan como reintentables.
================================================================================
"""

from __future__ import annotations

import threading
from typing import Callable

from nucleo.programador import puerta


class FalloTerminal(Exception):
    """Un fallo que reintentar no arregla. No consume los intentos restantes:
    cierra el turno."""

    def __init__(self, codigo: str, mensaje: str = ""):
        super().__init__(mensaje or codigo)
        self.codigo = codigo


class Turno:
    """Lo que el trabajo recibe. Solo lo que necesita saber."""

    def __init__(self, claim: dict, organization_id, perdido: threading.Event):
        self.job_code = claim.get("job_code")
        self.run_id = claim["run_id"]
        self.attempt_number = claim["attempt_number"]
        self.slot = claim["slot"]
        self.organization_id = organization_id
        # La config CONGELADA. El trabajo tiene que usar esta version, no la
        # vigente: es el turno el que decide contra que reglas corre.
        self.config_version = claim["config_version"]
        self.config_hash = claim["config_hash"]
        self.inputs = claim["inputs"]
        self._perdido = perdido

    @property
    def lease_perdido(self) -> bool:
        """Si ya no tiene sentido seguir. Un trabajo largo deberia mirarlo
        entre partes; ninguno esta obligado."""
        return self._perdido.is_set()


class _Latido(threading.Thread):
    """Renueva el lease hasta que le digan que pare o hasta perderlo."""

    def __init__(self, attempt_id, capability: str, cada_segundos: float,
                 perdido: threading.Event):
        super().__init__(name="latido-scheduler", daemon=True)
        self._attempt_id = attempt_id
        self._cap = capability
        self._cada = max(cada_segundos, 1.0)
        self._perdido = perdido
        self._parar = threading.Event()

    def run(self) -> None:
        while not self._parar.wait(self._cada):
            try:
                with puerta.sesion(puerta.EJECUTOR) as cur:
                    hasta = puerta.latir(cur, self._attempt_id, self._cap)
            except Exception as e:                               # noqa: BLE001
                # Un fallo de red al latir NO es perder el lease: el lease
                # sigue vivo en la base unos minutos mas. Se reintenta en la
                # vuelta siguiente. Darlo por perdido aca abandonaria trabajo
                # que todavia es valido.
                print(f"[ejecutor] el latido fallo: {type(e).__name__}: {e}",
                      flush=True)
                continue
            if hasta is None:
                print("[ejecutor] lease perdido: el turno ya no es de este "
                      "worker", flush=True)
                self._perdido.set()
                return

    def parar(self) -> None:
        self._parar.set()


def ejecutar(claim: dict, trabajo: Callable[[Turno], dict | None],
             lease_segundos: float = 300.0) -> dict:
    """
    Corre UN turno reclamado de punta a punta.

    Devuelve que paso, sin levantar: un turno que falla es un resultado, no una
    excepcion del proceso. La unica excepcion que sube es KeyboardInterrupt.
    """
    perdido = threading.Event()
    # Se late tres veces por lease. Con una sola, cualquier hipo de red lo
    # pierde; con muchas mas, es carga por nada.
    latido = _Latido(claim["attempt_id"], claim["capability"],
                     lease_segundos / 3.0, perdido)

    resultado: dict = {"run_id": str(claim["run_id"]),
                       "intento": claim["attempt_number"]}
    outcome, codigo = "succeeded", None
    try:
        with puerta.sesion(puerta.EJECUTOR) as cur:
            org = puerta.abrir_contexto(cur, claim["attempt_id"],
                                        claim["capability"])
        if org is None:
            # Se perdio el turno antes de empezar. No se trabaja.
            resultado["registrado"] = None
            resultado["nota"] = "el intento ya no era el vigente al arrancar"
            return resultado

        turno = Turno(claim, org, perdido)
        latido.start()
        try:
            salida = trabajo(turno)
            if isinstance(salida, dict):
                resultado["trabajo"] = salida
        except FalloTerminal as e:
            outcome, codigo = "failed_terminal", e.codigo
            resultado["error"] = str(e)
        except KeyboardInterrupt:
            raise
        except BaseException as e:                               # noqa: BLE001
            # SystemExit incluido a proposito: hay modulos del motor que lo
            # levantan cuando falta un dato de conexion, y eso no puede matar
            # al ejecutor -- es un turno que fallo, nada mas.
            outcome = "failed_retryable"
            codigo = type(e).__name__[:64]
            resultado["error"] = f"{type(e).__name__}: {e}"
    finally:
        latido.parar()

    try:
        with puerta.sesion(puerta.EJECUTOR) as cur:
            registrado = puerta.finalizar(cur, claim["attempt_id"],
                                          claim["capability"], outcome, codigo)
    except Exception as e:                                       # noqa: BLE001
        # No se pudo registrar el desenlace. El turno queda con el lease
        # vencido y el coordinador lo va a rescatar: at-least-once.
        resultado["registrado"] = None
        resultado["error_al_registrar"] = f"{type(e).__name__}: {e}"
        return resultado

    resultado["reportado"] = outcome
    resultado["registrado"] = registrado
    if registrado is None:
        resultado["nota"] = ("se llego tarde: otro worker ya tenia el turno, "
                             "el trabajo de este intento no cuenta")
    elif registrado != outcome:
        resultado["nota"] = (f"se reporto '{outcome}' y se registro "
                             f"'{registrado}': era el ultimo intento")
    return resultado
