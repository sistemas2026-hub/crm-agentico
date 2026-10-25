# -*- coding: utf-8 -*-
"""
================================================================================
 H-21 · EL SUPERVISOR UBICA CADA ASUNTO EN SU NIVEL DE RESPUESTA  (24/10/2026)
================================================================================

Habilidad H-21, AUTORIZADA por el usuario el 24/10/2026 («autorizo la h-21»).
Los niveles y el nivel de cada asunto viven en `campo/niveles.py`; esto es la
regla con la que el Supervisor los llena. Ficha: SPEC/objetivos/
supervisor-arma-la-jornada.md, «Niveles de respuesta y H-21».

NO ADIVINA POR EL NOMBRE
------------------------
Mira lo que ya mide: el GRUPO de la lectura de cada ticket
(`paso_a_despacho._ultima_lectura_con_grupo`, la misma lectura que decide si un
caso pasa a Despacho). Por asunto, cuenta cuantos tickets cayeron en cada grupo:

    el grupo con mas tickets: falla de servicio  ->  Urgente
                              obra de red        ->  Normal
                              trabajo pedido     ->  Programable
    menos de 3 tickets leidos                    ->  Normal, PROVISIONAL

Decisiones del 24 y 25/10/2026 (regla del usuario: elegir la mas recomendable,
anotarla y seguir), con su motivo en la ficha:

  N5   Si dos grupos empatan arriba, o gana uno sin nivel (nada lo mide, ni
       cliente ni red): Normal, no provisional, y el motivo lo dice.
  N6   UN ticket = UN caso: de cada caso cuenta su lectura con grupo mas
       reciente.
  N7   Los asuntos de las plantillas activas entran aunque no tengan tickets.
  N13  UN NIVEL YA MEDIDO NO SE MUEVE POR UN TICKET: para cambiarlo, el grupo
       nuevo tiene que tener mas de la mitad de los tickets y dos o mas de
       ventaja sobre el segundo (auditor, con sonda: con 5 y 5 el nivel
       saltaba en cada vuelta entre Normal, Urgente y Programable).
  N15  El asunto se corta como lo guarda WispHub (`campo.niveles.
       asunto_del_ticket`): si no, cada cliente era un asunto.
  N17  LAS DOS PUERTAS DE TODA ESCRITURA DEL SUPERVISOR: su tarea delegada
       propia (`tareas_delegadas.UBICAR_LOS_ASUNTOS`) y el nivel 3 de la
       empresa. Sin alguna, o sin poder comprobarlas, corre en SOMBRA: calcula
       y deja en el log cuantos ubicaria, sin escribir ni avisar.

LO QUE DECIDE UNA PERSONA NO SE TOCA. Lo garantiza la escritura
(`campo.niveles.ubicar_por_el_supervisor`), no esta regla.

UNA SOLA TRANSACCION, CON LA EMPRESA BLOQUEADA: dos vueltas a la vez (el reloj y
el boton) no avisan dos veces el mismo cambio, y si la base se cae a la mitad
no queda un cambio escrito que nunca se aviso.
================================================================================
"""

from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)

#: Menos tickets leidos que esto y el nivel es provisional (24/10/2026).
MINIMO_DE_TICKETS = 3
#: Ventaja minima sobre el segundo grupo para mover un nivel ya medido (N13).
VENTAJA_PARA_CAMBIAR = 2
#: La autonomia que exige escribir (la misma que el armado y el paso).
NIVEL_PARA_UBICAR = 3

#: El grupo que manda -> el nivel. Los otros dos grupos no tienen nivel.
NIVEL_POR_GRUPO = {
    "falla_de_servicio": "urgente",
    "obra_de_red": "normal",
    "trabajo_pedido": "programable",
}

TEXTO_DEL_GRUPO = {
    "falla_de_servicio": "falla de servicio",
    "obra_de_red": "obra de red",
    "trabajo_pedido": "trabajo pedido",
    "nada_lo_mide": "algo que nada mide",
    "ni_cliente_ni_red": "ni del cliente ni de la red",
}

UBICADO = "ubicado"
SOMBRA = "sombra"


def decidir(grupos: Counter) -> tuple[str, str, bool]:
    """(nivel, motivo, provisional) para un asunto con estos tickets por grupo.

    Pura: no lee la base. Es lo que prueban las pruebas de la regla.
    """
    from campo.niveles import NORMAL

    total = sum(grupos.values())
    if total < MINIMO_DE_TICKETS:
        de = "ningún ticket leído" if not total else (
            "1 ticket leído" if total == 1 else f"{total} tickets leídos")
        return NORMAL, f"provisional: {de}", True
    arriba = grupos.most_common(2)
    grupo, n = arriba[0]
    if len(arriba) > 1 and arriba[1][1] == n:
        a, b = sorted((arriba[0][0], arriba[1][0]))
        return (NORMAL,
                f"sin un grupo que domine: {n} {TEXTO_DEL_GRUPO.get(a, a)} y "
                f"{n} {TEXTO_DEL_GRUPO.get(b, b)} de {total}", False)
    texto = TEXTO_DEL_GRUPO.get(grupo, grupo)
    nivel = NIVEL_POR_GRUPO.get(grupo)
    if nivel is None:
        return (NORMAL,
                f"{n} de {total} tickets fueron {texto}: ese grupo no tiene nivel",
                False)
    return nivel, f"{n} de {total} tickets fueron {texto}", False


def alcanza_para_cambiar(grupos: Counter) -> bool:
    """Si estos tickets alcanzan para MOVER un nivel ya medido (N13): el grupo
    con mas tickets tiene mas de la mitad y dos o mas de ventaja."""
    total = sum(grupos.values())
    arriba = grupos.most_common(2)
    if not total or not arriba:
        return False
    primero = arriba[0][1]
    segundo = arriba[1][1] if len(arriba) > 1 else 0
    return primero * 2 > total and primero - segundo >= VENTAJA_PARA_CAMBIAR


def tickets_por_asunto(org, plantillas: dict | None = None) -> dict:
    """{asunto: {"asunto": como se ve, "grupos": Counter}}.

    De cada caso, su lectura con grupo MAS RECIENTE (N6), de las propuestas
    que leen tickets (`paso_a_despacho.tipos_que_llevan_a_despacho`), en
    cualquier estado: una propuesta rechazada tambien leyo su ticket. El asunto
    se corta como lo guarda WispHub (N15).

    Se leen de a una (`iterator`) y solo las que traen una lectura: la
    historia de propuestas crece sin techo y esto corre cada hora.
    """
    from campo.niveles import asunto_del_ticket, asuntos_de_las_plantillas
    from cases.models import Case
    from operaciones import paso_a_despacho as pad
    from operaciones.models import PropuestaSupervisor

    if plantillas is None:
        plantillas = asuntos_de_las_plantillas(org)
    grupo_del_caso = {}
    for p in (PropuestaSupervisor.objects
              .filter(org=org, origen_tipo="case",
                      tipo_senal__in=pad.tipos_que_llevan_a_despacho(),
                      evidencia__icontains=pad.FUENTE_DE_LA_LECTURA)
              .order_by("created_at", "id")
              .only("origen_id", "evidencia")
              .iterator(chunk_size=500)):
        lectura = pad._ultima_lectura_con_grupo(p)
        grupo = str((lectura or {}).get("grupo") or "")
        if grupo:
            grupo_del_caso[str(p.origen_id)] = grupo
    salida: dict = {}
    if not grupo_del_caso:
        return salida
    for caso_id, nombre in (Case.objects.filter(org=org, id__in=list(grupo_del_caso))
                            .values_list("id", "name")):
        clave, visto = asunto_del_ticket(nombre, plantillas)
        if not clave:
            continue
        fila = salida.setdefault(clave, {"asunto": visto, "grupos": Counter()})
        fila["grupos"][grupo_del_caso[str(caso_id)]] += 1
    return salida


def ubicar_los_asuntos(org, *, escribir: bool = True) -> dict:
    """Pasa la regla por todos los asuntos de la empresa. Con `escribir`,
    escribe lo que es del Supervisor; sin, solo cuenta (la sombra). Devuelve:

        {"cambios": [{"asunto", "antes", "nivel", "motivo", "provisional",
                      "tickets", "de_plantilla"}],
         "igual": n, "se_mantiene": n, "de_una_persona": n}

    `antes` es None para un asunto que entra por primera vez. `se_mantiene`
    cuenta los niveles medidos que la regla moveria pero no alcanza (N13).
    """
    from campo import niveles as N

    plantillas = N.asuntos_de_las_plantillas(org)
    leidos = tickets_por_asunto(org, plantillas)
    guardados = {f["normalizado"]: f for f in N.NivelDeAsunto.objects.filter(org=org)
                 .values("normalizado", "nivel", "por", "provisional")}
    salida = {"cambios": [], "igual": 0, "se_mantiene": 0, "de_una_persona": 0}
    for clave in sorted(set(leidos) | set(plantillas)):
        datos = leidos.get(clave) or {}
        grupos = datos.get("grupos") or Counter()
        asunto = plantillas.get(clave) or datos.get("asunto") or clave
        nivel, motivo, provisional = decidir(grupos)
        antes = guardados.get(clave)
        if antes and antes["por"] != N.POR_SUPERVISOR:
            salida["de_una_persona"] += 1
            continue
        if (antes and not antes["provisional"] and antes["nivel"] != nivel
                and not alcanza_para_cambiar(grupos)):
            salida["se_mantiene"] += 1
            continue
        if antes and antes["nivel"] == nivel and not escribir:
            salida["igual"] += 1
            continue
        r = (N.ubicar_por_el_supervisor(org, asunto, nivel, motivo=motivo,
                                        tickets=sum(grupos.values()),
                                        provisional=provisional)
             if escribir else (N.CAMBIO if antes else N.NUEVO))
        if r in (N.NUEVO, N.CAMBIO):
            salida["cambios"].append({
                "asunto": asunto, "antes": antes["nivel"] if antes else None,
                "nivel": nivel, "motivo": motivo, "provisional": provisional,
                "tickets": sum(grupos.values()), "de_plantilla": clave in plantillas})
        elif r == N.IGUAL:
            salida["igual"] += 1
        else:
            salida["de_una_persona"] += 1
    return salida


def _puertas(org) -> str:
    """Por que NO puede escribir, o "" si puede. Las dos puertas de toda
    escritura del Supervisor (N17); no poder comprobarlas es no tenerlas."""
    from operaciones import autonomia, tareas_delegadas

    try:
        if not tareas_delegadas.esta_delegada(org, tareas_delegadas.UBICAR_LOS_ASUNTOS):
            return ("nadie le delego al Supervisor que ubique los asuntos: se le "
                    "pide desde su chat")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar si la tarea esta delegada ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(org, NIVEL_PARA_UBICAR) or {}
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo leer la autonomia de la empresa ({type(e).__name__})"
    if not veredicto.get("puede"):
        #  TEXTO FIJO: el motivo del interruptor arrastra lo que una persona
        #  escribio al moverlo, y esto va a un log.
        return "la empresa no tiene autorizado que el Supervisor ubique los asuntos"
    return ""


def fase(org, ahora=None) -> dict:
    """La fase del ciclo. SON CONTEOS: el detalle queda en cada asunto y en el
    aviso. Con las dos puertas, escribe y avisa en el chat; sin alguna, la
    sombra: cuenta lo que haria y lo deja en el log, sin nombrar asuntos."""
    from django.db import transaction

    from common.models import Org
    from operaciones import aviso_al_chat

    porque = _puertas(org)
    if porque:
        r = ubicar_los_asuntos(org, escribir=False)
        logger.info("Supervisor: niveles de los asuntos · sombra · %s · "
                    "ubicaria %s, se mantienen %s", porque, len(r["cambios"]),
                    r["se_mantiene"])
        return {"niveles_de_los_asuntos": {
            "modo": SOMBRA, "porque": porque, "ubicaria": len(r["cambios"])}}
    with transaction.atomic():
        Org.objects.select_for_update().get(pk=org.pk)
        r = ubicar_los_asuntos(org)
        avisado = aviso_al_chat.avisar_niveles(org, r["cambios"], ahora=ahora)
    return {"niveles_de_los_asuntos": {
        "modo": UBICADO, "ubicados": len(r["cambios"]),
        "de_una_persona": r["de_una_persona"], "se_mantienen": r["se_mantiene"],
        "avisado": bool(avisado)}}
