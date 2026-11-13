# -*- coding: utf-8 -*-
"""
================================================================================
 EVENTOS DE CONSUMO  --  cada llamada de IA, sin depender del turno
================================================================================

POR QUE EXISTE, SEPARADO DE consumo.py
---------------------------------------
'consumo.py' acumula el gasto de UN TURNO en un ContextVar y lo vuelca al
cerrar. Funciona bien para la conversacion, y tiene una consecuencia que la
auditoria del 05/10/2026 midio: lo que corre FUERA de ese turno no se cuenta.

Vision y la transcripcion corren antes de 'atender_turno' --en api.py, lineas
8296-8297, contra la 8330 donde el turno abre el acumulador-- asi que para
ellas el ContextVar es None y anotar() no hace nada. No era un olvido: era
estructural.

Este modulo no necesita turno. Se le dice que paso y lo escribe. Por eso
Vision puede registrar su evento desde donde esta hoy, sin que haya que mover
el orden del turno ni tocar su logica.

EL ORIGEN, Y POR QUE ES UN ContextVar APARTE
---------------------------------------------
Las evaluaciones y las pruebas llaman al modelo de verdad y gastan saldo de
verdad. Hasta ahora no se contaban en ningun lado, y eso dejaba una eleccion
incomoda: contarlas --y que el tope del tenant saltara por trabajo que nadie
facturo-- o no contarlas, y no saber cuanto costaron. Medido: el saldo del
proveedor bajo $6.78 mientras el sistema calculaba $2.37.

Con 'origen' se puede hacer lo correcto: se registra TODO y el tope mira solo
'production'.

Vive en su propio ContextVar y no dentro de la ficha del turno porque Vision
--que es justo lo que no tiene turno-- igual necesita saber de donde viene.
El canal real lo marca al entrar; el corredor de casos dorados, al arrancar;
y lo que no marque nada queda en 'test', que es el default conservador: si
algo no se declaro, no puede afectar la factura de una empresa.

NUNCA ROMPE EL TURNO
--------------------
Mismo criterio que consumo.py: si la base falla, se anota el fallo y se sigue.
Perder una fila de consumo es molesto; perder la respuesta de un cliente por
una estadistica, no se hace.
================================================================================
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar

from nucleo.observabilidad.registro import registrar
from nucleo.persistencia.db import sesion

#: Los servicios que pueden gastar. Se nombran aca para que el codigo y el
#: 'check' de la tabla usen las mismas palabras.
CONVERSACION = "conversation"
VISION = "vision"
TRANSCRIPCION = "transcription"
EMBEDDINGS = "embeddings"
TTS = "tts"
SERVICIOS = (CONVERSACION, VISION, TRANSCRIPCION, EMBEDDINGS, TTS)

#: De donde vino la llamada.
PRODUCCION = "production"
EVALUACION = "evaluation"
PRUEBA = "test"
ORIGENES = (PRODUCCION, EVALUACION, PRUEBA)

#: El origen del trabajo en curso. 'test' por defecto, y es deliberado: lo que
#: no se declara no puede entrar en la factura de una empresa. El canal real
#: marca 'production' al recibir un mensaje; el corredor marca 'evaluation'.
_origen: ContextVar[str] = ContextVar("origen_consumo", default=PRUEBA)


@contextmanager
def origen(cual: str):
    """
    Marca de donde viene todo lo que se gaste aca adentro.

    Se usa con 'with' y repone el valor anterior al salir, asi que anida sin
    pisar nada -- un turno dentro de una evaluacion sigue siendo evaluacion.
    """
    if cual not in ORIGENES:
        cual = PRUEBA
    testigo = _origen.set(cual)
    try:
        yield cual
    finally:
        _origen.reset(testigo)


def fijar_origen(cual: str) -> None:
    """
    Marca el origen para el resto de ESTE contexto, sin bloque 'with'.

    Existe para el webhook: el mensaje entrante se atiende en su propio hilo,
    de punta a punta, y envolver sus 120 lineas en un 'with' obligaria a
    reindentarlas enteras para esto. Un ContextVar fijado en un hilo no se
    filtra a otro, asi que declararlo una vez al entrar alcanza y no
    contamina a nadie.

    Donde SI conviene el 'with' es en lo que anida --una evaluacion que corre
    turnos adentro-- porque ahi hay que reponer el valor al salir.
    """
    _origen.set(cual if cual in ORIGENES else PRUEBA)


def origen_actual() -> str:
    """De donde viene lo que se esta gastando ahora."""
    return _origen.get()


def anotar_evento(tenant: str, servicio: str, proveedor: str, modelo: str, *,
                  entrada: int = 0, entrada_cache: int = 0, salida: int = 0,
                  razonamiento: int = 0, caracteres: int = 0,
                  costo_usd: float = 0.0, hay_tarifa: bool = False,
                  conversacion_id=None, mensaje_id=None,
                  metadatos: dict | None = None) -> bool:
    """
    Una llamada de IA que ya ocurrio. Devuelve si se pudo escribir.

    NUNCA LEVANTA. El valor de retorno existe para las pruebas y para quien
    quiera saber si quedo registrado; el camino del cliente lo ignora.

    'entrada_cache' es un SUBCONJUNTO de 'entrada', no se suma aparte: asi lo
    reporta el proveedor y asi lo cobra. Se recorta al total por las dudas --
    la tabla tiene un check que lo exige, y un evento rechazado por un dato
    mal armado seria peor que uno con la cifra acotada.
    """
    if servicio not in SERVICIOS:
        registrar("consumo", "servicio desconocido: el evento no se registra",
                  tenant=tenant, servicio=servicio)
        return False

    entrada = max(0, int(entrada or 0))
    salida = max(0, int(salida or 0))
    entrada_cache = min(max(0, int(entrada_cache or 0)), entrada)
    #  Sin tarifa el costo es 0 y punto: la tabla no guarda estimados, y un
    #  numero inventado se veria igual de real en el panel que uno correcto.
    costo = float(costo_usd or 0.0) if hay_tarifa else 0.0

    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.consumo_eventos
                     (organization_id, servicio, proveedor, modelo, origen,
                      conversation_id, message_id,
                      input_tokens, cached_input_tokens, output_tokens,
                      reasoning_tokens, caracteres,
                      costo_usd, hay_tarifa, metadatos)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (org, servicio, proveedor, modelo, origen_actual(),
                 conversacion_id, mensaje_id,
                 entrada, entrada_cache, salida,
                 max(0, int(razonamiento or 0)), max(0, int(caracteres or 0)),
                 round(costo, 8), bool(hay_tarifa),
                 json.dumps(metadatos or {}, ensure_ascii=False)))
        return True
    except Exception as fallo:      # noqa: BLE001 -- ver el encabezado
        registrar("consumo", "no se pudo registrar el evento de consumo",
                  tenant=tenant, servicio=servicio, error=fallo)
        return False


def resumen(tenant: str, dias: int = 30) -> dict:
    """
    El desglose que el panel no podia dar: por origen, servicio, proveedor y
    modelo. Devuelve un dict vacio si no se puede leer -- el panel dibuja lo
    que haya, y una consulta de estadisticas no deja a nadie sin atender.
    """
    vacio = {"por_origen": [], "por_servicio": [], "por_modelo": [],
             "sin_tarifa": []}
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select origen, count(*) n, sum(costo_usd) costo,
                          sum(input_tokens) entrada, sum(output_tokens) salida
                     from asistente.consumo_eventos
                    where organization_id = %s
                      and creado_en > now() - make_interval(days => %s)
                    group by origen order by 3 desc nulls last""",
                (org, dias))
            por_origen = [dict(f) for f in cur.fetchall()]

            cur.execute(
                """select servicio, origen, count(*) n, sum(costo_usd) costo,
                          sum(input_tokens) entrada, sum(output_tokens) salida,
                          sum(caracteres) caracteres
                     from asistente.consumo_eventos
                    where organization_id = %s
                      and creado_en > now() - make_interval(days => %s)
                    group by servicio, origen order by 4 desc nulls last""",
                (org, dias))
            por_servicio = [dict(f) for f in cur.fetchall()]

            cur.execute(
                """select proveedor, modelo, count(*) n, sum(costo_usd) costo,
                          bool_and(hay_tarifa) con_tarifa
                     from asistente.consumo_eventos
                    where organization_id = %s
                      and creado_en > now() - make_interval(days => %s)
                    group by proveedor, modelo order by 4 desc nulls last""",
                (org, dias))
            por_modelo = [dict(f) for f in cur.fetchall()]

            #  Lo que se gasto y no se sabe cuanto costo. Es la cifra que hay
            #  que mirar antes de creerle al total.
            cur.execute(
                """select proveedor, modelo, count(*) n,
                          sum(input_tokens + output_tokens) tokens
                     from asistente.consumo_eventos
                    where organization_id = %s
                      and hay_tarifa = false
                      and creado_en > now() - make_interval(days => %s)
                    group by proveedor, modelo order by 3 desc""",
                (org, dias))
            sin_tarifa = [dict(f) for f in cur.fetchall()]

        def _n(filas):
            return [{k: (float(v) if k == "costo" and v is not None
                         else int(v) if isinstance(v, int) or (
                             k in ("n", "entrada", "salida", "caracteres", "tokens")
                             and v is not None)
                         else v)
                     for k, v in f.items()} for f in filas]

        return {"por_origen": _n(por_origen), "por_servicio": _n(por_servicio),
                "por_modelo": _n(por_modelo), "sin_tarifa": _n(sin_tarifa)}
    except Exception as fallo:      # noqa: BLE001
        registrar("consumo", "no se pudo leer el resumen de consumo",
                  tenant=tenant, error=fallo)
        return vacio
