# -*- coding: utf-8 -*-
"""
================================================================================
 EL EJECUTOR  --  hace UN turno y reporta que paso
================================================================================

RECIBE DOS COSAS Y NADA MAS
---------------------------
    ejecutar(run_id, capability)

No recibe organizacion, ni job_code, ni una funcion, ni un nombre de modulo.
Todo lo demas sale de 'asistente.job_contexto(run_id, capability)', que lo lee
de las tablas y verifica los hashes antes de entregarlo.

Dos razones, y la segunda es la que importa:

  1. Entre el claim y el arranque pueden pasar minutos, un reinicio o un
     rescate. Lo que el coordinador tenia en memoria puede ser de otro intento.

  2. Si el ejecutor aceptara un callable o un nombre de modulo, el 'job_code'
     --que es un dato de una tabla que edita un operador-- se volveria codigo
     ejecutable. El 'job_code' se resuelve contra 'registro.py', que es un
     diccionario literal congelado al importar; si no esta, no se corre.

EL LATIDO VA EN SU PROPIA CONEXION
----------------------------------
Compartir la conexion con el trabajo seria imposible: mientras el trabajo tiene
una transaccion abierta, el latido no puede ejecutar nada. Y el latido tiene
que poder correr JUSTO cuando el trabajo esta tardando, que es cuando hace
falta.

QUE PASA CUANDO SE PIERDE EL LEASE
----------------------------------
El latido devuelve None y el ejecutor lo marca en un Event. El 'finalize' final
va a devolver None igual, porque el intento ya no es el vigente.

Lo que NO se hace es matar el hilo del trabajo. Matarlo a mitad de un POST al
proveedor deja el efecto hecho y el registro sin escribir, que es peor que la
duplicacion que se querria evitar. El contrato es at-least-once.

LA CAPABILITY NO SE ESCRIBE EN NINGUN LADO
------------------------------------------
No va al resultado, no va a los logs, no va a las metricas y no va al 'repr' de
'Turno'. Esta ultima parte esta puesta a mano --'__repr__' y '__str__'
redefinidos-- porque el 'repr' por defecto de un objeto que la tuviera como
atributo la imprimiria entera en cualquier traceback.
================================================================================
"""

from __future__ import annotations

import threading

from nucleo.programador import puerta, registro


class FalloTerminal(Exception):
    """Un fallo que reintentar no arregla. Cierra el turno sin gastar los
    intentos restantes."""

    def __init__(self, codigo: str, mensaje: str = ""):
        super().__init__(mensaje or codigo)
        self.codigo = codigo


class Turno:
    """
    Lo que el trabajo recibe. Todo derivado de la base, nada del coordinador.

    NO tiene la capability. A proposito: un objeto que la llevara como atributo
    la imprimiria en cualquier traceback.
    """

    def __init__(self, ctx: dict, perdido: threading.Event):
        self.run_id = ctx["run_id"]
        self.attempt_id = ctx["attempt_id"]
        self.attempt_number = ctx["attempt_number"]
        self.job_code = ctx["job_code"]
        self.organization_id = ctx["organization_id"]
        self.slot = ctx["scheduled_slot"]
        # La config CONGELADA, leida del historial y con el hash recalculado.
        # El trabajo corre contra ESTA, no contra la vigente.
        self.config_version = ctx["config_version"]
        self.config_hash = ctx["config_hash"]
        self.config = ctx["config"]
        # Las entradas canonicas. Con esto y la config se reconstruye el turno
        # entero: un hash solo no alcanza para reejecutarlo.
        self.inputs = ctx["inputs"]
        self.inputs_hash = ctx["inputs_hash"]
        self._perdido = perdido

    @property
    def lease_perdido(self) -> bool:
        """Si ya no tiene sentido seguir. Un trabajo largo deberia mirarlo
        entre partes; ninguno esta obligado."""
        return self._perdido.is_set()

    def __repr__(self) -> str:
        return (f"<Turno {self.job_code} intento {self.attempt_number} "
                f"slot {self.slot} config v{self.config_version}>")

    __str__ = __repr__


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
                # que todavia es valido. El mensaje no lleva la capability.
                print(f"[ejecutor] el latido fallo: {type(e).__name__}",
                      flush=True)
                continue
            if hasta is None:
                print("[ejecutor] lease perdido: el turno ya no es de este "
                      "worker", flush=True)
                self._perdido.set()
                return

    def parar(self) -> None:
        self._parar.set()


def ejecutar(run_id, capability: str, lease_segundos: float = 300.0) -> dict:
    """
    Corre UN turno de punta a punta. Devuelve que paso, sin levantar.

    El resultado NUNCA contiene la capability ni su hash: lo unico que
    identifica al turno ahi adentro es 'run_id', que no es un secreto.
    """
    perdido = threading.Event()
    resultado: dict = {"run_id": str(run_id)}

    # --- 1. derivar el turno de la base --------------------------------------
    try:
        with puerta.sesion(puerta.EJECUTOR) as cur:
            ctx = puerta.contexto(cur, run_id, capability)
    except Exception as e:                                       # noqa: BLE001
        # HISTORIAL_CONFIG_CORRUPTO / INPUTS_CORRUPTOS llegan por aca. No se
        # trabaja: no hay version degradada correcta de "no se contra que
        # tengo que correr".
        resultado["error"] = f"{type(e).__name__}: {_primera_linea(e)}"
        resultado["registrado"] = None
        resultado["nota"] = "no se pudo derivar el contexto del turno"
        return resultado

    if ctx is None:
        resultado["registrado"] = None
        resultado["nota"] = "el intento ya no era el vigente al arrancar"
        return resultado

    ctx["run_id"] = run_id
    resultado["intento"] = ctx["attempt_number"]
    resultado["job_code"] = ctx["job_code"]

    # --- 2. resolver el handler contra el registro CERRADO -------------------
    try:
        trabajo = registro.resolver(ctx["job_code"])
    except registro.JobSinImplementacion as e:
        # El turno ya esta reclamado, asi que hay que cerrarlo. Terminal: que
        # este despliegue no sepa hacer el job no se arregla reintentando.
        resultado["error"] = str(e)
        resultado["registrado"] = _cerrar(ctx["attempt_id"], capability,
                                          "failed_terminal",
                                          "JOB_SIN_IMPLEMENTACION", resultado)
        return resultado

    # --- 3. trabajar ---------------------------------------------------------
    latido = _Latido(ctx["attempt_id"], capability, lease_segundos / 3.0,
                     perdido)
    outcome, codigo = "succeeded", None
    turno = Turno(ctx, perdido)
    latido.start()
    try:
        salida = trabajo(turno)
        if isinstance(salida, dict):
            resultado["trabajo"] = salida
    except FalloTerminal as e:
        outcome, codigo = "failed_terminal", e.codigo
        resultado["error"] = str(e)
    except KeyboardInterrupt:
        latido.parar()
        raise
    except BaseException as e:                                   # noqa: BLE001
        # SystemExit incluido a proposito: hay modulos del motor que lo
        # levantan cuando falta un dato de conexion, y eso no puede matar al
        # ejecutor -- es un turno que fallo, nada mas.
        outcome = "failed_retryable"
        codigo = type(e).__name__[:64]
        resultado["error"] = f"{type(e).__name__}: {_primera_linea(e)}"
    finally:
        latido.parar()

    resultado["reportado"] = outcome
    resultado["registrado"] = _cerrar(ctx["attempt_id"], capability, outcome,
                                      codigo, resultado)
    registrado = resultado["registrado"]
    if registrado is None and "error_al_registrar" not in resultado:
        resultado["nota"] = ("se llego tarde: otro worker ya tenia el turno, "
                             "el trabajo de este intento no cuenta")
    elif registrado is not None and registrado != outcome:
        resultado["nota"] = (f"se reporto '{outcome}' y se registro "
                             f"'{registrado}': era el ultimo intento")
    return resultado


def _cerrar(attempt_id, capability, outcome, codigo, resultado) -> str | None:
    try:
        with puerta.sesion(puerta.EJECUTOR) as cur:
            return puerta.finalizar(cur, attempt_id, capability, outcome,
                                    codigo)
    except Exception as e:                                       # noqa: BLE001
        # No se pudo registrar el desenlace. El turno queda con el lease
        # vencido y el coordinador lo va a rescatar: at-least-once.
        resultado["error_al_registrar"] = f"{type(e).__name__}"
        return None


def _primera_linea(e: BaseException) -> str:
    """El mensaje, sin cuerpos largos. Un traceback de psycopg trae el SQL
    entero, y el SQL de este subsistema lleva la capability como parametro."""
    return str(e).splitlines()[0][:200] if str(e) else ""
