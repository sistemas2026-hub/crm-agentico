# -*- coding: utf-8 -*-
"""
================================================================================
 EL TICKET SE ENTERA DE QUE ALGUIEN SALIO  --  06/11/2026
================================================================================
El usuario, probando: marco "En camino" desde la app, vio el cambio en
Programacion y el ticket de Dexter seguia igual que cuando se abrio -- solo
"Ticket creado" y "Asignado a CESAR MORON".

Programacion lee el ESTADO de la orden, asi que ahi se ve. El ticket no
leia nada: lo que pasa en campo llegaba recien al cerrar
(`devolver_al_ticket`, 02/11). Quien mira el ticket no sabia si el tecnico
habia salido, llegado, o si no habia pasado nada.

QUE HACE
--------
Deja en el ticket del CRM una nota interna y una entrada en la linea de
tiempo, por cada avance: sale, llega. Hermano de `devolver_al_ticket`, que
hace lo mismo al cerrar.

POR QUE UN MODULO APARTE Y NO UNA FUNCION ALLA
-----------------------------------------------
`devolver_al_ticket` CIERRA el ticket, y su marca de "ya se hizo" es una sola
(`contexto["devuelto_al_ticket"]`): una orden se cierra una vez. Esto avisa
VARIAS veces --una por avance y por vuelta-- y no cierra nada. Meterlos juntos
obligaria a esa marca a significar dos cosas, y el dia que una cambie de
reglas la otra se arrastra.

LO QUE NO HACE
--------------
**No cierra ni cambia el estado del ticket.** Un tecnico que sale no resuelve
nada todavia.

**No le escribe al cliente.** La nota es `is_internal=True`, como la del
cierre: es para quien atiende el ticket. Lo que el cliente recibe se decide
aparte y no se decide aca.

**No tumba la accion.** Si esto falla, el tecnico igual quedo "en camino" y la
app ya le contesto. Un ticket sin la nota es un problema; un boton que no
responde en la calle es uno peor.
================================================================================
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: El verbo de la linea de tiempo. Uno de los que `Activity` ya conoce.
ACCION = "updated"

#: Donde se anota que este aviso ya salio, dentro de `OrdenTrabajo.contexto`.
#: Un diccionario y no una lista: la pregunta es "¿ya avise ESTO?", y una
#: lista obligaria a recorrerla.
CLAVE = "avisos_al_ticket"

#: Tope de la nota.
#:
#:  YA NO ES EL DE LA COLUMNA  --  07/11/2026. `Comment.comment` era un
#:  CharField(255) y por eso este numero valia 255. El usuario vio el costo en
#:  la OT #188: el reporte llegaba entero a WispHub y en Dexter terminaba en
#:  «MATERIAL Y...», o sea que la seccion que dice QUE SE GASTO caia completa.
#:  La columna pasa a `text` en la misma entrega (common/0047).
#:
#:  PERO NO SE QUITA EL TOPE. Sin ninguno, un reporte largo convierte un
#:  renglon de bitacora en una pagina y la linea de tiempo deja de leerse. Y
#:  el detalle entero sigue viviendo en la orden: esta nota es un aviso. 2000
#:  entra el reporte completo que se midio (~350 con material y evidencias)
#:  con margen de sobra, y sigue siendo un parrafo, no un documento.
MAX_NOTA = 2000


def recortar(texto: str, tope: int = MAX_NOTA) -> str:
    """El texto que entra en la nota, cortado donde termina una palabra.

    POR QUE EXISTE  --  06/11/2026. `Comment.comment` es un CharField(255) y
    el reporte de campo entero no entra: el de la OT #184 media ~300. Cortar
    en seco dejaba la nota terminando a mitad de palabra, y peor: a mitad de
    un dato ("CONECTOR AP"), que se lee como si fuera el dato completo.

    El detalle entero vive en la orden y en el ticket del ISP; esta nota es un
    aviso. Por eso termina en «…», que dice que hay mas.
    """
    texto = (texto or "").strip()
    if len(texto) <= tope:
        return texto
    recorte = texto[:tope - 1]
    espacio = recorte.rfind(" ")
    #  Si no hay ningun espacio --una sola palabra larguisima-- se corta en
    #  seco igual: mejor eso que devolver vacio.
    if espacio > tope // 2:
        recorte = recorte[:espacio]
    return recorte.rstrip(" ,;.") + "\u2026"


def _clave_de(momento: str, vuelta) -> str:
    """Identifica el aviso: momento y vuelta.

    LA VUELTA ENTRA, por la misma razon que en las notas al ISP: una orden
    devuelta y rehecha vuelve a salir y a llegar, y esos avances son nuevos.
    Sin la vuelta, el segundo viaje no se avisaria.
    """
    return f"{momento}:{vuelta}"


def avisar(orden, texto: str, momento: str, profile=None) -> dict:
    """Deja la nota en el ticket del CRM. Nunca levanta.

    `{"hecho": bool, "motivo": str}`.
    """
    from django.db import transaction

    from cases.models import Case
    from common.models import Activity, Comment
    from django.contrib.contenttypes.models import ContentType

    case_id = (orden.origen_ref or "").strip()
    if orden.origen_sistema != "crm" or not case_id:
        return {"hecho": False, "motivo": "sin_ticket"}

    texto = (texto or "").strip()
    if not texto:
        return {"hecho": False, "motivo": "sin_texto"}

    try:
        with transaction.atomic():
            from campo.models import OrdenTrabajo

            #  LA MARCA SE RECLAMA PRIMERO, bajo bloqueo: dos pedidos a la vez
            #  --un doble toque en la app, un reintento de la cola-- no pueden
            #  dejar dos notas iguales.
            fila = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
            contexto = dict(fila.contexto or {})
            avisos = dict(contexto.get(CLAVE) or {})
            clave = _clave_de(momento, fila.vuelta)
            if avisos.get(clave):
                return {"hecho": False, "motivo": "ya_avisado"}

            caso = Case.objects.select_for_update().filter(
                org=fila.org, pk=case_id).first()
            if caso is None:
                return {"hecho": False, "motivo": "ticket_no_encontrado"}

            Comment.objects.create(
                org=fila.org,
                content_type=ContentType.objects.get_for_model(Case),
                object_id=caso.pk,
                comment=recortar(texto),
                commented_by=profile,
                #  INTERNA, como la del cierre: es para quien atiende el
                #  ticket, no un mensaje al cliente.
                is_internal=True,
            )
            Activity.objects.create(
                #  EL PROFILE, NO SU USER. `Activity.user` es FK a
                #  Profile: pasarle el User revienta con
                #  "must be a Profile instance". Medido el 06/11/2026.
                user=profile,
                action=ACCION,
                entity_type="Case",
                entity_id=caso.pk,
                entity_name=str(caso)[:255],
                metadata={"fuente": "campo", "momento": momento,
                          "orden": str(fila.id), "orden_numero": fila.numero,
                          "vuelta": fila.vuelta},
                org_id=fila.org_id,
            )

            avisos[clave] = True
            contexto[CLAVE] = avisos
            fila.contexto = contexto
            #  SOLO `contexto`, como `devolver_al_ticket`: agregar
            #  `updated_at` aca da ValueError en este modelo. Lo tapaba
            #  el `except` y la guarda fallaba sin motivo visible.
            fila.save(update_fields=["contexto"])
    except Exception as e:                                       # noqa: BLE001
        #  Por tipo, sin `str(e)`: el mensaje puede traer datos de la fila.
        logger.warning("avisar_al_ticket: no se pudo (%s)", type(e).__name__)
        return {"hecho": False, "motivo": type(e).__name__}

    return {"hecho": True, "motivo": ""}
