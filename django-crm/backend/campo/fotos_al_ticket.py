# -*- coding: utf-8 -*-
"""
================================================================================
 LAS FOTOS DEL TECNICO SE VEN EN EL TICKET  --  07/11/2026
================================================================================
El usuario, probando la OT #186: «en dexter sale bien hasta donde dice
evidencia en... no muestra las fotos».

La nota del reporte decia «Evidencias en Dexter: 4» y quien leia el ticket
tenia que irse a buscarlas a otra pantalla. Las fotos ya estaban en el
servidor desde que el tecnico las subio -- lo que faltaba era que el ticket
las mostrara.

POR QUE `Attachments` Y NO `CommentFiles`
------------------------------------------
Los dos existen. `Attachments` cuelga del Case por GenericForeignKey y la
pantalla del ticket YA lo lista (`tickets/[id]/+page.svelte`: `{#if
attachments.length}`). `CommentFiles` cuelga de un comentario y esa pantalla
no lo mira: adjuntar ahi habria sido escribir filas que nadie ve, que es la
forma mas cara de no arreglar nada.

LO QUE NO HACE
--------------
**No vuelve a subir nada.** Lee el archivo que ya esta en disco por
`CampoStorage.ruta_absoluta`, que es quien tapa el path traversal.

**No tumba el reporte.** Si esto falla, el tecnico igual reporto y la nota
igual se escribio. Un ticket sin las fotos es un problema; un boton que no
contesta en la calle es uno peor.

**No manda nada a WispHub.** Ese lado es otro trabajo: el endpoint del ISP
toma un archivo por respuesta y todavia no se midio en vivo.
================================================================================
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: Donde se anota que las fotos de esta vuelta ya se adjuntaron, dentro de
#: `OrdenTrabajo.contexto`. Hermano de `avisar_al_ticket.CLAVE`: misma razon
#: --un diccionario y no una lista, porque la pregunta es "¿ya adjunte ESTO?"--
#: y mismo tratamiento de la vuelta.
CLAVE = "fotos_al_ticket"

#: Tope por vuelta. Una orden con muchas evidencias no puede convertir un
#: reporte en veinte escrituras y veinte archivos copiados: el ticket se
#: vuelve ilegible y el disco crece el doble. Las que no entran siguen
#: estando en la orden, que es donde viven de verdad.
MAX_POR_VUELTA = 8


def _clave_de(vuelta) -> str:
    """LA VUELTA ENTRA, por lo mismo que en las notas: una orden devuelta y
    rehecha trae fotos NUEVAS, y son las que hay que mostrar."""
    return f"v{vuelta}"


def _nombre(evidencia, i: int) -> str:
    """Como se llama el archivo en el ticket.

    EL REQUISITO ADELANTE, no el nombre que trajo el telefono: quien abre el
    ticket quiere saber cual foto es ("dano_encontrado"), no "IMG_20261107
    _105412.jpg". El original va detras por si hace falta cruzarlo.
    """
    base = (evidencia.requisito_id or "foto").strip() or "foto"
    ext = os.path.splitext(evidencia.nombre_original or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        ext = ".jpg"
    return f"{base}-{i}{ext}"


def adjuntar(orden, profile=None) -> dict:
    """Copia las evidencias de esta vuelta al ticket del CRM. Nunca levanta.

    `{"hecho": bool, "cuantas": int, "motivo": str}`.
    """
    from django.core.files.base import ContentFile
    from django.db import transaction

    from cases.models import Case

    case_id = (orden.origen_ref or "").strip()
    if orden.origen_sistema != "crm" or not case_id:
        return {"hecho": False, "cuantas": 0, "motivo": "sin_ticket"}

    #  `create_attachment` escribe `created_by` y `org` DESDE EL PROFILE, y
    #  sin el revienta por AttributeError dentro del bucle: ocho intentos, un
    #  log por foto y ninguna adjunta. Se corta antes y se dice, que es la
    #  diferencia entre "no habia a quien atribuirlo" y "fallo ocho veces".
    if profile is None or getattr(profile, "org_id", None) is None:
        return {"hecho": False, "cuantas": 0, "motivo": "sin_profile"}

    try:
        from campo.models import OrdenTrabajo
        from campo.services.storage import CampoStorage
        from common.utils import create_attachment

        #  LA MARCA SE RECLAMA PRIMERO, bajo bloqueo, y en su propia
        #  transaccion: dos pedidos a la vez --un reintento de la cola de la
        #  app-- no pueden adjuntar dos veces las mismas fotos.
        with transaction.atomic():
            fila = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
            contexto = dict(fila.contexto or {})
            hechas = dict(contexto.get(CLAVE) or {})
            clave = _clave_de(fila.vuelta)
            if hechas.get(clave):
                return {"hecho": False, "cuantas": 0, "motivo": "ya_adjuntas"}

            caso = Case.objects.filter(org=fila.org, pk=case_id).first()
            if caso is None:
                return {"hecho": False, "cuantas": 0,
                        "motivo": "ticket_no_encontrado"}

            hechas[clave] = True
            contexto[CLAVE] = hechas
            fila.contexto = contexto
            #  SOLO `contexto`: agregar `updated_at` aca da ValueError en este
            #  modelo. Mismo motivo que en `avisar_al_ticket`.
            fila.save(update_fields=["contexto"])

        #  Y RECIEN AHORA SE COPIAN LOS ARCHIVOS, FUERA DE LA TRANSACCION.
        #  Leer y escribir ocho archivos con la fila bloqueada deja el lock
        #  tomado mientras se hace E/S, y es la misma regla que prohibe
        #  esperar una operacion externa con una transaccion abierta
        #  (CLAUDE.md §12).
        #
        #  CONSECUENCIA ACEPTADA: si el proceso muere entre la marca y la
        #  copia, esas fotos no se adjuntan y no se reintentan. Se eligio
        #  sobre la alternativa --marcar al final-- porque esa duplica las
        #  fotos en el ticket cada vez que algo falla a mitad de camino, y una
        #  foto de menos se ve; ocho repetidas, tambien, pero no se pueden
        #  sacar desde la pantalla.
        cuantas = 0
        evidencias = list(orden.evidencias
                          .filter(vuelta=orden.vuelta, evento__isnull=True)
                          .order_by("recibida_en_servidor")[:MAX_POR_VUELTA])
        for i, ev in enumerate(evidencias, start=1):
            try:
                ruta = CampoStorage.ruta_absoluta(ev.storage_key)
                #  DEFENSA REDUNDANTE, Y SE DEJA A SABIENDAS. Quitar este
                #  `if` NO cambia la conducta: `open(None)` o un archivo que
                #  no esta levantan, y el `except` de abajo los convierte en
                #  el mismo "esta foto no, las otras si". Medido el
                #  07/11/2026: la mutacion que lo borra sobrevive a las diez
                #  guardas, y es correcto que sobreviva -- no hay efecto que
                #  afirmar.
                #
                #  Se conserva porque un archivo faltante es lo ESPERADO (un
                #  borrado manual, una subida a medias) y pasar por una
                #  excepcion lo registraria como un fallo en el log, mezclado
                #  con los que si lo son.
                if not ruta or not os.path.exists(ruta):
                    continue
                with open(ruta, "rb") as f:
                    datos = f.read()
                create_attachment(ContentFile(datos, name=_nombre(ev, i)),
                                  caso, profile)
                cuantas += 1
            except Exception as e:                               # noqa: BLE001
                #  Una foto que no se pudo copiar no se lleva a las otras.
                logger.warning("fotos al ticket: una no se pudo (%s)",
                               type(e).__name__)
    except Exception as e:                                       # noqa: BLE001
        #  Por tipo, sin `str(e)`: el mensaje puede traer la ruta del archivo.
        logger.warning("fotos al ticket: no se pudo (%s)", type(e).__name__)
        return {"hecho": False, "cuantas": 0, "motivo": type(e).__name__}

    return {"hecho": cuantas > 0, "cuantas": cuantas, "motivo": ""}
