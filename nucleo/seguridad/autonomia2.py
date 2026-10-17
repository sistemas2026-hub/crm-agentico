"""
================================================================================
 AUTONOMIA 2  --  EL PREREQUISITO DE DESPLIEGUE
================================================================================

DOS COMPUERTAS QUE NO SON EL KILL SWITCH
----------------------------------------
El kill switch es un corte de emergencia: lo mueve un operador cuando algo va
mal. Estas dos son otra cosa -- dicen si el sistema esta en condiciones de
ejecutar autonomamente, y ninguna de las dos lo modifica.

  1. EL INTERRUPTOR DE ETAPA  ('AUTONOMIA_2_ACTIVA')
     Una sola variable de entorno, apagada por omision. Es el OFF -> ON del
     requisito 14: se enciende sin tocar codigo, y hasta que se encienda no se
     ejecuta nada solo. Falla cerrado -- cualquier valor que no sea un si
     explicito es NO.

  2. EL PREREQUISITO B-7  (se MIDE, no se declara)
     B-7 cerro NO-GO por una razon concreta y medida: el secreto de firma de
     JWT vive en un GUC de la base que 'crm_user' puede leer, y con el se firma
     un token 'service_role' que tiene BYPASSRLS sobre 129 de 135 tablas. O
     sea: mientras ese GUC exista, el privilegio que B-7 quita se recupera con
     un SELECT y un HMAC.

     Por eso este modulo NO pregunta por una bandera 'B7_GO' que alguien pueda
     poner en true de memoria. Pregunta a la base si el vector sigue abierto:

         current_setting('app.settings.jwt_secret', true)

     Si devuelve algo, el escalamiento indirecto es posible y se contesta
     B7_REQUERIDO. Si no devuelve nada, ese vector esta cerrado.

     Es la misma leccion de todo este proyecto: una prueba que afirma que un
     mecanismo EXISTE no prueba que funcione. Una bandera que dice "B-7 esta
     listo" no prueba que lo este; la ausencia del secreto si es medible.

     LIMITE, dicho aca y no escondido: esto mide UN vector, el que B-7 dejo
     abierto y documentado. No prueba que B-7 este cerrado del todo -- eso
     incluye ademas rotar el secreto y cambiar DBUSER, cosas que esta consulta
     no puede ver. Es un prerequisito NECESARIO, no suficiente, y el informe lo
     dice con esas palabras.

ESTO NO TOCA EL KILL SWITCH
---------------------------
Ni lo lee ni lo mueve. El requisito 8 es explicito: B7_REQUERIDO es un
prerequisito de despliegue/autorizacion, no un estado del interruptor.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

import os
from dataclasses import dataclass

# Codigos de bloqueo. Viajan a la bitacora y a la traza.
B7_REQUERIDO = "B7_REQUERIDO"
ETAPA_APAGADA = "AUTONOMIA_2_NO_ACTIVA"
B7_DESCONOCIDO = "B7_NO_COMPROBABLE"

#  El unico interruptor de etapa. Un solo nombre, facil de encontrar.
VAR_ETAPA = "AUTONOMIA_2_ACTIVA"

_SI = ("1", "true", "si", "sí", "yes", "on")


@dataclass(frozen=True)
class Veredicto:
    permitido: bool
    codigo: str
    motivo: str


def etapa_activa(entorno: dict | None = None) -> bool:
    """El OFF -> ON del requisito 14. Apagado por omision, falla cerrado."""
    entorno = os.environ if entorno is None else entorno
    return str(entorno.get(VAR_ETAPA, "")).strip().lower() in _SI


def veredicto_b7() -> Veredicto:
    """
    ¿Sigue abierto el vector de escalamiento que dejo B-7?

    Se MIDE contra la base. Tres salidas, y las tres bloquean menos una:
      - el GUC trae un valor   -> B7_REQUERIDO (el vector esta abierto)
      - el GUC esta vacio/nulo -> permitido
      - no se pudo preguntar   -> B7_DESCONOCIDO (bloquea: "no se pudo
                                  comprobar" no es "adelante")
    """
    from nucleo.persistencia import db as persistencia
    try:
        valor = persistencia.secreto_jwt_en_base()
    except BaseException as e:                                   # noqa: BLE001
        registrar("autonomia2", "no se pudo comprobar B-7: se BLOQUEA la ejecucion autonoma",
                  error=e)
        return Veredicto(False, B7_DESCONOCIDO,
                         f"no se pudo comprobar el prerequisito de B-7: "
                         f"{type(e).__name__}")
    if (valor or "").strip():
        return Veredicto(
            False, B7_REQUERIDO,
            "el secreto de firma de JWT sigue en un GUC legible de la base: "
            "con el se firma un token service_role con BYPASSRLS, o sea que el "
            "privilegio que B-7 retira se recupera por otra via. No se ejecuta "
            "autonomamente hasta que B-7 cierre.")
    return Veredicto(True, "b7_ok",
                     "el GUC con el secreto de firma ya no esta en la base")


def veredicto(entorno: dict | None = None) -> Veredicto:
    """
    Las dos compuertas, en orden. La barata primero.

    No se comprueba B-7 si la etapa esta apagada: seria una consulta a la base
    en cada llamada para contestar algo que ya se sabe.
    """
    if not etapa_activa(entorno):
        return Veredicto(
            False, ETAPA_APAGADA,
            f"Autonomia 2 no esta activada ({VAR_ETAPA} apagada). La "
            f"infraestructura esta lista; encenderla es una decision, no un "
            f"efecto secundario de desplegar.")
    return veredicto_b7()
