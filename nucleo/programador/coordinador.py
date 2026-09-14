# -*- coding: utf-8 -*-
"""
================================================================================
 EL COORDINADOR  --  el tick, y por que no duerme al final
================================================================================

EL DEFECTO QUE ESTO VIENE A ARREGLAR
------------------------------------
El reloj viejo hacia, literalmente:

    while True:
        time.sleep(3600)
        una_pasada()

Dos cosas, las dos medidas:

  1. ATRASO ACUMULADO. El ciclo dura lo que dure el trabajo, y recien despues
     empieza a contar la hora. Medido sobre 20 ciclos reales: +33,7 segundos
     por ciclo, 13,5 minutos por dia. Al mes, el barrido "horario" corre a una
     hora del dia distinta de la que corria al principio.

  2. HAMBRE. El sueño arranca al desplegar. Nueve despliegues en 2 h 43 min
     --lo normal en un dia de trabajo-- dieron CERO barridos en cuatro horas:
     cada despliegue reiniciaba el contador antes de que llegara a la hora.

El tick de aca no duerme "una hora despues de terminar": duerme hasta el
PROXIMO borde de la grilla. Si un tick tarda 50 segundos, el siguiente sale
igual en su borde. Si tarda mas que el intervalo entero, el siguiente sale de
inmediato y se cuenta como atraso -- no se saltea ni se encola.

Y el estado NO vive en este proceso. Vive en la base. Un despliegue a mitad de
tick no pierde nada: el turno queda reclamado con su lease, el lease vence, y
el proximo coordinador --este o su reemplazo-- lo rescata.

QUE HACE UN TICK
----------------
Pregunta que vence, reclama hasta donde le alcance el presupuesto, y entrega
cada turno reclamado al ejecutor. Cierra la cuenta con un embudo: todo lo que
'jobs_vencidos' devolvio esta o trabajado o omitido con motivo.
================================================================================
"""

from __future__ import annotations

import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from nucleo.programador import ejecutor, embudo, metricas, puerta

# El tick del coordinador NO es el intervalo de los jobs. Es cada cuanto mira
# si algo vencio. Un job horario con un tick de 60 s arranca, como mucho, 60 s
# despues de su borde -- y el borde no se corre, que es lo que importa.
TICK_SEGUNDOS = 60

# Cuanto puede durar un tick antes de cortar y dejar el resto para el que
# sigue. Sin esto, un tick que reclama 500 turnos lentos se come los bordes
# siguientes y vuelve el atraso acumulado por otra puerta.
PRESUPUESTO_SEGUNDOS = 45.0

# Cuantos turnos reclama un tick como maximo.
TOPE_POR_TICK = 200


def worker_id() -> str:
    """
    Quien dice ser este proceso. Va al log y a 'job_attempt.worker_id'.

    Lleva el host y un sufijo aleatorio por arranque: dos replicas del mismo
    contenedor tienen el mismo hostname, y sin el sufijo serian indistinguibles
    justo en el caso en que hay que distinguirlas.
    """
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


def _hasta_el_proximo_borde(ahora: float, tick: int) -> float:
    """
    Cuanto falta para el proximo borde de la grilla.

    Nunca devuelve 0: un borde exacto duerme un tick entero, no cero. Con cero,
    un tick que termina exactamente en el borde entraria en un bucle cerrado
    sin dormir.
    """
    resto = ahora % tick
    return tick - resto if resto else float(tick)


def un_tick(trabajos: dict[str, Callable[[ejecutor.Turno], dict | None]],
            reg: metricas.Registro | None = None,
            presupuesto: float = PRESUPUESTO_SEGUNDOS,
            tope: int = TOPE_POR_TICK,
            wid: str | None = None) -> dict:
    """
    Una pasada: preguntar, reclamar, ejecutar. Devuelve el informe del embudo.

    No levanta. Un tick que falla es un tick que se informa; el bucle sigue.
    """
    reg = reg if reg is not None else metricas.Registro()
    wid = wid or worker_id()
    arranque = time.monotonic()
    emb = embudo.Embudo("tick")
    hechos: list[dict] = []

    try:
        with puerta.sesion(puerta.COORDINADOR) as cur:
            candidatos = puerta.vencidos(cur, limite=tope)
    except Exception as e:                                       # noqa: BLE001
        print(f"[coord] no se pudo preguntar que vence: "
              f"{type(e).__name__}: {e}", flush=True)
        reg.contar("tick_fallido")
        return {**emb.informe(), "error": f"{type(e).__name__}: {e}"}

    emb.recibir(len(candidatos))
    for c in candidatos:
        if time.monotonic() - arranque > presupuesto:
            emb.omitir("presupuesto")
            reg.contar("omitidos", motivo="presupuesto", job_code=c["job_code"])
            continue
        if emb.alcanzados >= tope:
            emb.omitir("tope_de_tick")
            reg.contar("omitidos", motivo="tope_de_tick", job_code=c["job_code"])
            continue

        trabajo = trabajos.get(c["job_code"])
        if trabajo is None:
            # El catalogo declara un job que este despliegue no sabe hacer. No
            # es un error del turno: es un despliegue viejo, o uno nuevo con un
            # job que todavia no esta en esta imagen. No se reclama.
            emb.omitir("job_deshabilitado")
            reg.contar("omitidos", motivo="sin_implementacion",
                       job_code=c["job_code"])
            continue

        try:
            with puerta.sesion(puerta.COORDINADOR) as cur:
                claim = puerta.reclamar(cur, c["job_code"],
                                        c["organization_id"], c["slot"], wid)
        except Exception as e:                                   # noqa: BLE001
            emb.omitir("error")
            reg.contar("omitidos", motivo="error", job_code=c["job_code"])
            print(f"[coord] el claim de '{c['job_code']}' fallo: "
                  f"{type(e).__name__}: {e}", flush=True)
            continue

        if claim is None:
            # Se perdio la carrera. Cual de los tres motivos fue, la base no lo
            # dice y no vale la pena preguntarselo: los tres significan lo
            # mismo para este proceso -- no es suyo.
            emb.omitir("otro_coordinador")
            reg.contar("omitidos", motivo="otro_coordinador",
                       job_code=c["job_code"])
            continue

        claim = dict(claim)
        claim["job_code"] = c["job_code"]
        emb.alcanzar()
        reg.contar("reclamados", job_code=c["job_code"], motivo=c["motivo"])

        r = ejecutor.ejecutar(claim, trabajo)
        hechos.append(r)
        registrado = r.get("registrado")
        reg.contar("ejecutados", job_code=c["job_code"],
                   resultado=str(registrado or "sin_registrar"))

    informe = emb.informe()
    informe["turnos"] = hechos
    informe["duro_seg"] = round(time.monotonic() - arranque, 2)
    if not emb.cuadra:
        # No mata el tick. Pero se grita: significa que entraron candidatos que
        # no figuran en ninguna salida.
        reg.contar("embudo_descuadrado")
        print(f"[coord] EMBUDO DESCUADRADO {emb.descuadre:+d}: {emb}",
              flush=True)
    return informe


def correr(trabajos: dict[str, Callable[[ejecutor.Turno], dict | None]],
           tick: int = TICK_SEGUNDOS, vueltas: int | None = None) -> None:
    """
    El bucle. Duerme hasta el borde, no un intervalo despues de trabajar.

    'vueltas' existe para las pruebas. En produccion se llama sin ella.
    """
    wid = worker_id()
    reg = metricas.Registro()
    print(f"[coord] coordinador arriba: {wid}, tick de {tick}s", flush=True)
    hechas = 0
    while vueltas is None or hechas < vueltas:
        espera = _hasta_el_proximo_borde(time.time(), tick)
        time.sleep(espera)
        inicio = datetime.now(timezone.utc)
        try:
            informe = un_tick(trabajos, reg, wid=wid)
        except KeyboardInterrupt:
            raise
        except BaseException as e:                               # noqa: BLE001
            # La ultima red. Nada puede matar el bucle -- es la leccion
            # completa del reloj que estuvo un mes muerto sin un solo log.
            print(f"[coord] el tick entero fallo: {type(e).__name__}: {e}",
                  flush=True)
            hechas += 1
            continue
        duro = (datetime.now(timezone.utc) - inicio).total_seconds()
        if duro > tick:
            # El tick tardo mas que el intervalo. No se encola nada: el
            # siguiente sale de inmediato y esto queda dicho en el log.
            print(f"[coord] el tick tardo {duro:.1f}s, mas que el tick de "
                  f"{tick}s: el siguiente sale sin espera", flush=True)
            reg.contar("tick_excedido")
        print(f"[coord] {informe['etapa']}: recibidos={informe['recibidos']} "
              f"alcanzados={informe['alcanzados']} "
              f"omitidos={informe['omitidos']} en {informe['duro_seg']}s",
              flush=True)
        print(f"[coord] metricas: {reg}", flush=True)
        hechas += 1
