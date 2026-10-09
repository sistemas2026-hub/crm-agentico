# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR AVISA EN EL CHAT LO QUE CERRO, SIN QUE NADIE PREGUNTE
===============================================================================

QUE RESUELVE
------------
Hasta el 09/10/2026 el Supervisor cerraba casos solo y no lo contaba en
ningun lado donde una persona estuviera mirando. Quedaba escrito en la
propuesta y en la auditoria --que es lo correcto para el registro-- pero
enterarse exigia ir a buscarlo. Quien delego la tarea desde el chat se iba sin
saber si habia pasado algo.

Ahora, cuando el ciclo cierra casos, deja un mensaje en LA MISMA conversacion
donde se delego la tarea.

A QUIEN SE LE ESCRIBE, Y A QUIEN NO
-----------------------------------
A quien delego la tarea, nunca a otro. Hay dos formas de encontrarlo, en este
orden:

  1. La conversacion guardada en la tarea ('TareaDelegada.conversacion_id').
     Ese dato viaja desde el chat por el mismo camino verificado que el actor
     -- nunca como algo que el modelo pueda dictar en un mensaje.

  2. Si no hay ninguna --la tarea se delego antes del 09/10/2026, cuando ese
     campo no existia-- la ULTIMA conversacion de la persona que la delego, y
     se guarda para que el respaldo corra una sola vez.

Lo que NO se hace es buscar "la ultima conversacion" a secas: esa puede ser de
otra persona, que veria aparecer cierres que no autorizo. El filtro es por
quien delego, no por fecha.

El respaldo no se agrego por prolijidad: sin el, las tareas ya delegadas no
recibirian aviso NUNCA, y el arreglo obvio --volver a delegarlas-- no
funciona. El chat ve que ya estan activas y contesta "no hace falta", que es
lo correcto de su parte. Medido en vivo el 09/10/2026.

ESTO NO ES UNA NOTIFICACION, ES UN RENGLON DE LA CONVERSACION
--------------------------------------------------------------
El mensaje se guarda con rol 'supervisor', igual que cualquier respuesta suya.
Eso tiene una consecuencia buena y hay que saberla: entra en el historial que
el modelo lee en el turno siguiente. Si despues preguntas "¿que cerraste?", el
Supervisor no necesita volver a consultarlo -- ya esta en la conversacion.

Y UNA MALA, que se acota aqui: un aviso por hora llenaria el historial de
ruido y empujaria afuera lo que importa. Por eso solo se escribe CUANDO HUBO
CIERRES. Una corrida que no cerro nada no deja mensaje; si alguien quiere
saber que el ciclo corrio igual, eso esta en el log y en el panel de
actividad, que es donde corresponde.

NO LEVANTA NUNCA
----------------
Avisar es lo ultimo que pasa y lo menos importante: los casos YA se cerraron,
y eso esta guardado. Si la conversacion se borro, si la base falla, si el
texto no se puede armar -- se registra y se sigue. Un cierre correcto no se
puede perder porque no se pudo contar.

SIN DATOS DE CLIENTE MAS ALLA DE LO QUE EL CHAT YA MUESTRA. Se nombra el caso
por su numero de ticket del proveedor, que es lo que una persona usa para
buscarlo, y nunca el nombre ni el documento del abonado.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#  CUANTOS CASOS SE NOMBRAN UNO POR UNO antes de resumir. Con el atraso de hoy
#  --noventa casos-- una lista completa seria un muro de texto que nadie lee, y
#  encima entra en el historial del modelo. Diez alcanzan para reconocer lo que
#  paso; el total siempre se dice.
TOPE_DETALLADOS = 10


def _linea(cierre: dict) -> str:
    """Un renglon por caso: el ticket y por que se cerro."""
    ref = str(cierre.get("referencia") or cierre.get("caso") or "").strip()
    porque = str(cierre.get("porque") or "").strip()
    #  El porque viene redactado desde 'diagnostico_optico.porque_del_cierre',
    #  que es quien sabe si fue por señal optica o por ping. Aqui no se
    #  reinterpreta: repetirlo con otras palabras seria una segunda version de
    #  la misma afirmacion, y tarde o temprano dirian cosas distintas.
    return f"- {ref or 'caso sin referencia'}: {porque}" if porque else f"- {ref}"


def redactar(cerrados: list[dict]) -> str:
    """
    El texto del aviso. Funcion aparte y pura, para poder probarla sin base.

    NO LO ESCRIBE EL MODELO, y es deliberado: esto afirma que unos casos se
    cerraron. Pedirle a un modelo que redacte un hecho consumado es darle la
    oportunidad de matizarlo, y lo que hay que decir aqui es exactamente lo
    que paso.
    """
    n = len(cerrados)
    if n == 1:
        cabeza = "Cerré 1 caso que el proveedor ya tenía cerrado:"
    else:
        cabeza = f"Cerré {n} casos que el proveedor ya tenía cerrados:"

    lineas = [_linea(c) for c in cerrados[:TOPE_DETALLADOS]]
    if n > TOPE_DETALLADOS:
        lineas.append(f"- …y {n - TOPE_DETALLADOS} más.")

    return "\n".join([cabeza, *lineas])


def avisar_cierres(org, cerrados: list[dict], *, ahora=None) -> bool:
    """
    Deja el aviso en la conversación donde se delegó la tarea.

    Devuelve si se escribió. No levanta: ver el encabezado.
    """
    if not cerrados:
        return False

    try:
        from django.utils import timezone

        from operaciones import tareas_delegadas as td
        from operaciones.chat_modelos import (ConversacionSupervisor,
                                              MensajeSupervisor, RolMensaje)
        from operaciones.tareas_modelos import TareaDelegada

        #  LA CONVERSACION DE LA TAREA QUE PRODUJO EL CIERRE. Es
        #  'CERRAR_DESINCRONIZADOS' y no la del ciclo: el ciclo solo despierta
        #  al Supervisor, y quien autorizo CERRAR es quien tiene que
        #  enterarse de que cerro.
        fila = (TareaDelegada.objects
                .filter(org=org, clave=td.CERRAR_DESINCRONIZADOS, activa=True)
                .first())
        if fila is None:
            logger.info("Supervisor: %s cierres y la tarea no esta delegada",
                        len(cerrados))
            return False

        conversacion = None
        if fila.conversacion_id:
            conversacion = ConversacionSupervisor.objects.filter(
                org=org, id=fila.conversacion_id).first()

        #  EL RESPALDO: LA ULTIMA CONVERSACION DE QUIEN LA DELEGO  --  09/10
        #  ----------------------------------------------------------------
        #  'conversacion_id' se empezo a guardar el 09/10/2026. Las tareas
        #  delegadas ANTES lo tienen vacio, y sin respaldo el aviso no saldria
        #  nunca para ellas. El arreglo obvio --"volve a delegarla"-- no
        #  funciona: el chat ve que ya esta activa y contesta "no hace falta",
        #  que es lo correcto de su parte. Medido en vivo ese mismo dia.
        #
        #  NO ES "CUALQUIER CONVERSACION", y la diferencia es toda: es la
        #  ultima de LA PERSONA QUE DELEGO LA TAREA. Esa persona autorizo
        #  estos cierres; contarle lo que se cerro no le revela nada que no
        #  haya habilitado. Escribirle a otro si seria un problema, y por eso
        #  el filtro es por 'actor' y no por fecha a secas.
        #
        #  Y SE GUARDA para la proxima: asi el respaldo corre una sola vez por
        #  tarea, y a partir de ahi el aviso va siempre a la misma
        #  conversacion en vez de saltar a la mas reciente cada hora.
        if conversacion is None and fila.delegada_por_id:
            conversacion = (ConversacionSupervisor.objects
                            .filter(org=org, actor_id=fila.delegada_por_id,
                                    archivada=False)
                            .order_by("-ultimo_mensaje_en")
                            .first())
            if conversacion is not None:
                fila.conversacion_id = conversacion.id
                fila.save(update_fields=["conversacion_id", "updated_at"])
        if conversacion is None:
            #  Ni la guardada ni ninguna de quien delego. Pasa si la
            #  conversacion se borro --la retencion las vence al año-- o si la
            #  tarea se delego desde fuera del chat y esa persona nunca abrio
            #  una. Es un caso normal, no un error, y no se busca a otro
            #  destinatario.
            logger.info("Supervisor: %s cierres sin conversacion donde avisar",
                        len(cerrados))
            return False

        MensajeSupervisor.objects.create(
            conversacion=conversacion,
            org=org,
            rol=RolMensaje.SUPERVISOR,
            contenido=redactar(cerrados),
            escrito_en=ahora or timezone.now(),
        )
        return True
    except Exception:                                            # noqa: BLE001
        #  LOS CASOS YA ESTAN CERRADOS. Que el aviso falle no puede volver
        #  atras eso ni tumbar la corrida: se registra con traza y se sigue.
        logger.exception("Supervisor: no se pudo avisar el cierre en el chat")
        return False
