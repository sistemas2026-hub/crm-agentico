# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE QUEDO EMPEZADO Y SIN CERRAR  --  y POR QUE
================================================================================

QUE PREGUNTA CONTESTA
---------------------
Un trabajo que alguien empezo y no cerro no vuelve al reparto: quien fue al
sitio y hablo con el cliente sabe algo que el reparto no. Pero que se quede con
su cuadrilla NO quiere decir que nadie tenga que mirarlo -- al reves: si lleva
dias sin avanzar, es justo lo que hay que mirar primero.

La pregunta entonces no es "¿esta abierto?" sino "¿POR QUE sigue abierto?", y
tiene tres respuestas distintas que no se pueden mezclar:

    BLOQUEADO        hay un `BloqueoDeTrabajo` abierto. Se sabe quien lo
                     detiene (Bodega, el cliente, el NOC...), que categoria y
                     que necesita para seguir.
    EN_CURSO         sin bloqueo, y el seguimiento lo da AL DIA: esta
                     reportando como deberia. No molesta a nadie.
    SIN_EXPLICACION  sin bloqueo, y el seguimiento lo da VENCIDO. Hubo
                     contacto reciente y aun asi no reporto. NADIE DIJO POR
                     QUE, y eso es lo unico que de verdad hay que preguntar.

El tercero es el que justifica este modulo. Los otros dos ya se sabian; lo que
no existia era separarlos, y sin separarlos "12 trabajos abiertos" es un numero
que no dice si hay un problema o si todo va bien.

NO INVENTA NADA
---------------
Las tres respuestas salen de datos que ya existen: `BloqueoDeTrabajo` (con su
quien/categoria/necesita) y `services/salud_seguimiento.calcular()`. Reconstruir
cualquiera de los dos criterios aca los pondria a vivir en dos lados, y uno de
los dos se quedaria viejo -- que es exactamente el defecto que la fase C del
seguimiento encontro en el frontend.
"""

from __future__ import annotations

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import EventoTrabajo, OrdenTrabajo
from campo.reparto import ESTADOS_QUE_ESPERAN, EVENTO_INICIO
from campo.services import salud_seguimiento

BLOQUEADO = "bloqueado"
EN_CURSO = "en_curso"
SIN_EXPLICACION = "sin_explicacion"


#  QUIEN LO DETIENE NO ES UN CAMPO MIENTRAS ESTA ABIERTO.
#
#  `BloqueoDeTrabajo.QUIENES` (NOC, Bodega, el cliente...) vive en
#  `resuelto_por_rol`, o sea quien lo RESOLVIO: en un bloqueo abierto esta
#  vacio por definicion. Lo que si describe un bloqueo vivo es su `categoria`
#  --lo que el tecnico eligio en el formulario de SU empresa-- mas
#  `requiere_noc`. Inventar aca un "quien" a partir de la categoria seria
#  adivinar: las categorias las define cada tenant y no se pueden mapear desde
#  plataforma.


def revisar(org, *, ahora=None) -> dict:
    """Los trabajos empezados que siguen abiertos, agrupados por POR QUE.

        {
          "bloqueados":      [{orden, numero, quien, categoria, necesita}],
          "en_curso":        [{orden, numero}],
          "sin_explicacion": [{orden, numero, minutos_sin_reportar}],
        }

    Solo mira los EMPEZADOS: una orden que nadie toco no esta atrasada, esta
    esperando, y de esa se encarga el reparto.
    """
    empezadas = set(
        EventoTrabajo.objects
        .filter(org=org, tipo=EVENTO_INICIO)
        .values_list("orden_id", flat=True)
    )
    if not empezadas:
        return {"bloqueados": [], "en_curso": [], "sin_explicacion": []}

    abiertas = list(
        OrdenTrabajo.objects
        .filter(org=org, id__in=empezadas,
                estado_operativo__in=ESTADOS_QUE_ESPERAN)
        .order_by("numero")
    )

    # Un solo viaje por los bloqueos abiertos, no uno por orden.
    bloqueos = {
        b.orden_id: b
        for b in BloqueoDeTrabajo.objects
        .filter(org=org, orden_id__in=[o.id for o in abiertas],
                resuelto_en__isnull=True)
        .order_by("abierto_en")
    }

    salida = {"bloqueados": [], "en_curso": [], "sin_explicacion": []}
    config = salud_seguimiento.configuracion_de(org)

    for orden in abiertas:
        bloqueo = bloqueos.get(orden.id)
        if bloqueo is not None:
            salida["bloqueados"].append({
                "orden": str(orden.id),
                "numero": orden.numero,
                "categoria": bloqueo.categoria,
                # Lo que hace falta para poder seguir: es lo accionable, y sin
                # esto el supervisor tiene que abrir la orden para saberlo.
                "necesita": bloqueo.necesita or bloqueo.motivo,
                # Si ademas DETUVO el trabajo, o solo quedo anotado: un
                # bloqueo puede existir sin frenar nada --el tecnico avisa que
                # algo lo demora y sigue con lo que puede-- y tratarlos igual
                # haria parecer detenido lo que esta avanzando.
                "detuvo_el_trabajo": bloqueo.detuvo_el_trabajo,
                "requiere_noc": bloqueo.requiere_noc,
            })
            continue

        salud = salud_seguimiento.calcular(orden, ahora=ahora, config=config)
        # La clave es "tipo", no "estado": `estado_operativo` y
        # `estado_validacion` ya son dos ejes, y la salud del seguimiento se
        # llamo distinto justamente para no parecer un tercero.
        if salud.get("tipo") == salud_seguimiento.VENCIDO:
            salida["sin_explicacion"].append({
                "orden": str(orden.id),
                "numero": orden.numero,
                "minutos_vencido": salud.get("minutos_vencido"),
                "motivo": salud.get("motivo", ""),
            })
        else:
            salida["en_curso"].append({
                "orden": str(orden.id),
                "numero": orden.numero,
            })

    return salida
