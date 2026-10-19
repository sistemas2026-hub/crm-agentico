# -*- coding: utf-8 -*-
"""
================================================================================
 LA MEDICION DESPUES DEL ARREGLO  --  18/10/2026
================================================================================

QUE HACE
--------
Cuando un tecnico reporta en campo que termino la orden de una FALLA DE
SERVICIO, el Supervisor vuelve a medir el equipo del cliente con la misma
herramienta del motor que usa la medicion de las fallas
('diagnosticar_servicio') y deja el resultado en la propuesta que llevo el
caso a Despacho, como pieza propia ('FUENTE'): si la señal quedo en rango,
si no quedo, o si no se pudo medir.

DE DONDE SALE
-------------
Correccion 2 del usuario, regla 3 (SPEC/objetivos/correcciones-al-
diagnostico.md): "cuando el tecnico reporte el arreglo, el Supervisor vuelve a
medir para confirmar que la señal quedo en rango".

INFORMA, NO DECIDE
------------------
No reabre el caso, no toca la orden y no le avisa a nadie fuera del panel: la
pieza queda en la propuesta, que es donde una persona mira el caso. Que hacer
con un arreglo que no dejo la señal en rango lo decide una persona. Lo eligio
el asistente al aplicar la correccion; volverlo una alerta es otro paso.

POR QUE ES UNA FASE DEL CICLO, Y NO PARTE DE CERRAR LA ORDEN
------------------------------------------------------------
Cerrar la orden en campo ('campo.transiciones') es una transaccion de la base,
y medir es una llamada a un sistema externo que tarda hasta diez segundos:
ninguna transaccion queda abierta mientras se espera afuera (CLAUDE.md §12).
Y la medicion tiene que reintentarse si el proveedor no contesta, que es lo
que el ciclo ya sabe hacer cada hora.

LO QUE NO HACE
--------------
- No llama al modelo: medir no es leer.
- No guarda un error del motor como medicion (mismo criterio que
  'medicion_de_fallas'): la orden espera a la vuelta siguiente.
- No mide una orden que se completo hace mas de 'HORAS_PARA_VERIFICAR': lo
  que se mida despues ya no habla del arreglo.
- No escribe en el log nada del caso ni del cliente: solo conteos.
================================================================================
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

#:  La fuente de la pieza que se deja en la propuesta.
FUENTE = "medicion_despues_del_arreglo"

#:  Hasta cuantas horas despues de completada la orden se la mide. Dos dias
#:  cubren un fin de semana con el proveedor caido; despues, lo que se mida ya
#:  no habla del arreglo sino de lo que paso despues.
HORAS_PARA_VERIFICAR = 48

#:  Cuantas ordenes se miden por vuelta. Va al final del ciclo, despues de lo
#:  que decide, y no tiene que comerse el reloj de nadie.
TOPE_POR_VUELTA = 5

#:  Cuanto se espera para volver a intentar una que el proveedor no pudo medir,
#:  y cuantas veces se intenta en total. CON TOPE --auditor independiente,
#:  19/10/2026--: sin el, una orden que nunca se puede medir (el equipo no esta
#:  en SmartOLT, o se cambio y el ISP tiene el serial viejo) se pedia cada hora
#:  durante dos dias --polling de un endpoint que el proveedor prohibe usar
#:  asi-- y cinco de esas ocupaban todas las plazas de la vuelta.
MINUTOS_PARA_REINTENTAR = 60
INTENTOS_MAXIMOS = 3


def ultima_verificacion(propuesta) -> dict | None:
    """La pieza de la medicion despues del arreglo, o None."""
    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE:
            return pieza
    return None


def quedo_en_rango(medicion) -> bool | None:
    """True si el equipo quedo en linea con la señal en rango; False si quedo
    fuera de rango o caido; None si la medicion no dice ninguna de las dos."""
    from operaciones import diagnostico_optico as optico

    m = medicion if isinstance(medicion, dict) else {}
    nivel = isinstance(m.get("senal_dbm"), (int, float))
    if m.get("estado") == optico.EN_LINEA and nivel:
        if m.get("senal") == optico.SENAL_BUENA:
            return True
        if m.get("senal") == optico.SENAL_DEBIL:
            return False
    if m.get("estado") == optico.CAIDO and m.get("causa_caida"):
        return False
    return None


def _intentos(pieza) -> int:
    n = (pieza or {}).get("intentos")
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 1


def _toca(pieza, orden_id: str, ahora) -> bool:
    """Si esta orden necesita medirse en esta vuelta."""
    if pieza is None or pieza.get("orden") != orden_id:
        return True
    if pieza.get("quedo_en_rango") is not None:
        return False
    if _intentos(pieza) >= INTENTOS_MAXIMOS:
        return False
    cuando = parse_datetime(str(pieza.get("observado_en") or ""))
    return (cuando is None
            or ahora - cuando >= timedelta(minutes=MINUTOS_PARA_REINTENTAR))


def candidatas(org, ahora) -> list:
    """
    [(propuesta, caso, id de la orden)] a medir: primero las que nunca se
    intentaron, despues los reintentos; en cada grupo, la orden completada hace
    mas tiempo primero. Solo la ultima orden completada de cada caso, y solo si
    la propuesta que lo llevo a Despacho lee una falla de servicio.

    NO SE MIDE UN CAMBIO DE EQUIPO  --  auditor independiente, 19/10/2026. Si
    la lectura dice que el ticket trae un trabajo ya autorizado (cambio de
    equipo o de router, la correccion 1), lo mas probable es que el ISP siga
    con el serial viejo: se mediria el equipo que se retiro.
    """
    from campo.models import OrdenTrabajo
    from operaciones import paso_a_despacho as pad

    desde = ahora - timedelta(hours=HORAS_PARA_VERIFICAR)
    ordenes = (OrdenTrabajo.objects
               .filter(org=org, origen_sistema="crm",
                       estado_operativo__in=(OrdenTrabajo.COMPLETADA_CAMPO,
                                             OrdenTrabajo.CERRADA),
                       completada_campo_en__gte=desde,
                       completada_campo_en__lte=ahora)
               .order_by("completada_campo_en")
               .values_list("id", "origen_ref", "completada_campo_en"))
    por_caso = {}
    for orden_id, caso_id, cuando in ordenes:
        #  La mas reciente de cada caso gana: una segunda visita es otro
        #  arreglo, y es el que hay que verificar.
        por_caso[str(caso_id)] = (str(orden_id), cuando)
    if not por_caso:
        return []

    propuestas = {}
    for p in (pad.propuestas_que_llevan_a_despacho(org)
              .filter(origen_id__in=list(por_caso))
              .order_by("created_at")):
        propuestas[str(p.origen_id)] = p

    salida = []
    for caso_id, p in propuestas.items():
        lectura = pad._ultima_lectura_con_grupo(p) or {}
        if lectura.get("grupo") != pad.FALLA_DE_SERVICIO:
            continue
        if lectura.get("accion_autorizada") == pad.SI:
            continue
        orden_id, cuando = por_caso[caso_id]
        pieza = ultima_verificacion(p)
        if not _toca(pieza, orden_id, ahora):
            continue
        reintento = pieza is not None and pieza.get("orden") == orden_id
        salida.append((reintento, cuando, p, orden_id))
    salida.sort(key=lambda x: (x[0], x[1]))
    return [(p, pad.caso_de(p), orden_id) for _, _, p, orden_id in salida]


def _texto(medicion: dict, veredicto, ahora, intentos: int = 1) -> str:
    from operaciones import medicion_de_fallas as mdf

    cuando = (f" ({timezone.localtime(ahora).strftime('%d/%m %H:%M')} "
              f"{timezone.get_current_timezone_name()})")
    base = f"medicion despues del arreglo{cuando}: {mdf._lo_que_dice(medicion)}"
    if veredicto is True:
        return f"{base}. La señal quedo en rango despues del arreglo."
    if veredicto is False:
        return (f"{base}. La señal NO quedo en rango despues del arreglo: lo "
                f"mira una persona.")
    if intentos >= INTENTOS_MAXIMOS:
        return (f"{base}. No se pudo medir en {intentos} intentos: no se "
                f"vuelve a pedir.")
    return f"{base}. Se vuelve a intentar en una hora."


def escribir(propuesta, medicion: dict, orden_id: str, ahora) -> bool:
    """Deja la medicion en la propuesta, reemplazando la anterior. Solo si la
    propuesta sigue llevando el caso a Despacho. Mismo patron que
    'armado_de_jornadas.guardar_localidad'."""
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    veredicto = quedo_en_rango(medicion)
    with transaction.atomic():
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado__in=(P.ACEPTADA, P.MODIFICADA))
                  .first())
        if fresca is None:
            return False
        anterior = ultima_verificacion(fresca)
        intentos = (_intentos(anterior) + 1
                    if anterior is not None and anterior.get("orden") == orden_id
                    else 1)
        pieza = sup._observacion(FUENTE, fresca.origen_id,
                                 _texto(medicion, veredicto, ahora, intentos),
                                 ahora)
        pieza.update(medicion)
        pieza["orden"] = orden_id
        pieza["quedo_en_rango"] = veredicto
        pieza["intentos"] = intentos
        resto = [x for x in (fresca.evidencia or [])
                 if not (isinstance(x, dict) and x.get("fuente") == FUENTE)]
        fresca.evidencia = [*resto, pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    return True


def verificar_los_arreglos(org, *, desatendido: bool = False, medir=None,
                           presupuesto_=None) -> dict:
    """
    Mide las ordenes de falla completadas en campo. Devuelve conteos.

    'medir' SE INYECTA, como en 'medicion_de_fallas': este modulo decide QUE se
    mide y que se guarda, no como se habla con el motor.
    """
    from operaciones import diagnostico_optico as optico
    from operaciones import medicion_de_fallas as mdf
    from operaciones import supervisor as sup

    medir = medir or mdf._medir_con_el_motor
    p = (presupuesto_ if presupuesto_ is not None else sup.presupuesto(
        tope=TOPE_POR_VUELTA,
        segundos=(optico.SEGUNDOS_MAXIMOS_DESATENDIDO if desatendido
                  else optico.SEGUNDOS_MAXIMOS_DE_DIAGNOSTICO)))
    informe = {"candidatas": 0, "medidas": 0, "quedaron_en_rango": 0,
               "no_quedaron": 0, "sin_medicion": 0, "sin_id_de_servicio": 0,
               "sin_presupuesto": 0, "errores": 0}

    ahora = timezone.now()
    cola = candidatas(org, ahora)
    informe["candidatas"] = len(cola)
    for i, (propuesta, caso, orden_id) in enumerate(cola):
        id_servicio = str(getattr(caso, "external_service_id", "") or "").strip()
        if not id_servicio:
            informe["sin_id_de_servicio"] += 1
            continue
        if not sup._hay_presupuesto(p):
            informe["sin_presupuesto"] = len(cola) - i
            break
        sup._gastar(p)
        try:
            respuesta = medir(org, id_servicio)
        except Exception as e:                                   # noqa: BLE001
            respuesta = {"error": type(e).__name__}
        medicion = mdf.de_la_respuesta(respuesta)
        if medicion is None:
            informe["errores"] += 1
            continue
        try:
            if escribir(propuesta, medicion, orden_id, timezone.now()):
                informe["medidas"] += 1
                veredicto = quedo_en_rango(medicion)
                informe["quedaron_en_rango" if veredicto is True
                        else "no_quedaron" if veredicto is False
                        else "sin_medicion"] += 1
        except Exception as e:                                   # noqa: BLE001
            informe["errores"] += 1
            logger.warning("Supervisor: no se pudo guardar la medicion despues "
                           "del arreglo (%s)", type(e).__name__)
    return informe
