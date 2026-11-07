# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE PASA EN CAMPO VUELVE AL TICKET  --  02/11/2026
================================================================================
El usuario, con dos pantallas abiertas: *"ya ese ticket se cerro en supervisor
pero en ticket de dexter sigue abierto y sin ningun diagnostico... deberian
ser uno solo, no duplicar"*.

Tenia razon y el defecto era exactamente ese. La orden SI sabe de que ticket
nacio (`origen_sistema="crm"` + `origen_ref`), pero el enlace era **de una
sola via**: al completarse o cerrarse, nadie tocaba el ticket. Quedaba "Nuevo"
con el plazo vencido hacia semanas mientras en Supervisor figuraba cerrado.

No eran dos tickets duplicados: era **un trabajo partido en dos registros que
no se hablaban**.

QUE HACE ESTE MODULO
--------------------
Cuando una orden se cierra, en el ticket que la origino:

  1. deja una NOTA con lo que hizo el tecnico --su reporte, lo que midio y
     cuantas evidencias dejo--, que es el "diagnostico" que el usuario no
     encontraba;
  2. deja una entrada en la LINEA DE TIEMPO (`Activity`), para que se vea
     cuando y por quien;
  3. CIERRA el ticket.

UNA SOLA VEZ, Y ESO NO ES UN DETALLE
------------------------------------
Una orden se puede cerrar dos veces --un reintento, una conciliacion, dos
pestañas-- y el ticket no puede terminar con dos notas iguales ni con dos
cierres. La marca vive en la propia orden (`contexto["devuelto_al_ticket"]`)
y se reclama **antes** de escribir: es la misma leccion que `operaciones_externas`
dejo escrita para las mutaciones externas.

LO QUE NO HACE, A PROPOSITO
---------------------------
**No toca el ticket del ISP.** Cerrar en WispHub es otra cosa, con su propia
frontera y su propio fallo (`FALLO_AL_CERRAR`, visible en Cerradas). Mezclarlos
haria que un fallo alla dejara el ticket del CRM abierto, que es el problema
que esto viene a resolver.

**No reabre nada.** Si el ticket ya estaba cerrado, se respeta: se deja la
nota igual --el trabajo se hizo y tiene que constar-- pero no se le cambia el
estado a alguien que ya decidio.

**No tumba el cierre de la orden.** Si esto falla, la orden queda cerrada y se
anota el motivo por tipo. Un ticket sin actualizar es un problema; una orden
que no se puede cerrar porque el CRM tuvo un hipo es uno peor.
================================================================================
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Donde queda la marca de que ya se devolvio, dentro de `OrdenTrabajo.contexto`.
CLAVE = "devuelto_al_ticket"

#: El verbo de la linea de tiempo. Es uno de los que `Activity` ya conoce: el
#: hecho que se cuenta es que el ticket cambio de estado.
ACCION = "STATUS_CHANGED"

#: Tope de la nota: `Comment.comment` es un CharField de 255.
MAX_NOTA = 255


def _resumen(orden) -> str:
    """La nota, en el idioma de quien lee el ticket. Nunca pasa de `MAX_NOTA`.

    Lo primero es lo que el tecnico hizo, porque es lo que el ticket no tenia.
    Lo demas se agrega mientras entre; lo que no entra se recorta al final, no
    al principio."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _solucion

    partes = []
    hecho = (_solucion(_cierre_de_esta_vuelta(orden)) or "").strip()
    partes.append(f"Campo: {hecho}" if hecho else "Campo: trabajo cerrado")

    quien = [a.profile for a in orden.asignaciones.all() if a.es_principal]
    nombre = getattr(getattr(quien[0], "user", None), "name", "") if quien else ""
    if nombre:
        partes.append(f"Técnico: {nombre}")

    cuantas = orden.evidencias.count()
    if cuantas:
        partes.append(f"{cuantas} evidencia{'s' if cuantas != 1 else ''}")

    partes.append(f"OT #{orden.numero}")

    #  Y QUE SE VALIDO  --  07/11/2026
    #
    #  El usuario cerro una orden y comparo los dos tickets. En WispHub quedo
    #  «SE VALIDA TICKET» con los puntos revisados; en Dexter, solo «Campo: se
    #  tensiono cable · Tecnico: ... · 4 evidencias».
    #  El mismo acto, dos historias: quien abriera el ticket en Dexter no se
    #  enteraba de que alguien habia revisado, ni de que miro.
    #
    #  VA AL FINAL Y SOLO SI ENTRA: lo primero sigue siendo lo que el tecnico
    #  hizo, que es lo que el ticket no tenia.
    linea = _lo_que_se_valido(orden)
    texto = " · ".join(partes)
    if linea and len(texto) + len(linea) + 3 <= MAX_NOTA:
        texto = texto + " · " + linea
    return texto if len(texto) <= MAX_NOTA else texto[: MAX_NOTA - 1] + "…"


def _lo_que_se_valido(orden) -> str:
    """La revision en una linea, o `''` si no hubo.

    DE DONDE SALE. De la FOTO que `revision_del_cierre.guardar_foto` dejo en
    la bitacora al aprobar, no de recalcular la revision: despues de aprobada
    ya no se revisa, y recalcularla diria otra cosa -- es el mismo motivo por
    el que esa foto existe. Si no hay foto (una orden cerrada sin pasar por la
    revision) no se escribe nada: mejor callar que afirmar que alguien reviso.

    SE REUSA `texto_de_la_revision`, el mismo que va al ISP, para que los dos
    tickets digan lo mismo. Escribir aca una segunda version del texto es
    garantizar que dentro de un mes digan cosas distintas otra vez.

    SIN LA FRASE «SE VALIDA TICKET», que es la que el equipo reconoce EN
    WISPHUB y alli va sola en su renglon. Aca la nota es un renglon de
    bitacora, no la respuesta del ticket.
    """
    try:
        from campo.models import EventoTrabajo
        from campo.revision_del_cierre import FOTO
        from campo.services.nota_al_isp import texto_de_la_revision

        ev = (EventoTrabajo.objects
              .filter(orden=orden, tipo=FOTO)
              .order_by("-created_at").first())
        completo = texto_de_la_revision((ev.datos or {}) if ev else None)
    except Exception as e:                                       # noqa: BLE001
        #  Por tipo, sin `str(e)`: el mensaje puede traer datos de la fila. Y
        #  sin levantar: una nota incompleta no puede impedir un cierre.
        logger.warning("Campo: no se pudo leer la revision (%s)",
                       type(e).__name__)
        return ""
    if not completo:
        return ""
    #  `texto_de_la_revision` devuelve «SE VALIDA TICKET\nRevision: ...».
    partes_t = completo.split("\n", 1)
    return (partes_t[1] if len(partes_t) > 1 else partes_t[0]).strip()


def devolver(orden, profile=None) -> dict:
    """Devuelve al ticket lo que paso en campo. Ver el encabezado.

    `{"hecho": bool, "motivo": str}`. `hecho=False` con su motivo cuando no
    habia nada que hacer (no nacio de un ticket, ya se devolvio) o cuando no se
    pudo. Nunca levanta: quien cierra la orden no se puede caer por esto.
    """
    from django.db import transaction
    from django.utils import timezone

    from cases.models import Case
    from common.models import Activity, Comment
    from django.contrib.contenttypes.models import ContentType

    case_id = (orden.origen_ref or "").strip()
    if orden.origen_sistema != "crm" or not case_id:
        return {"hecho": False, "motivo": "sin_ticket"}

    try:
        with transaction.atomic():
            #  LA MARCA SE RECLAMA PRIMERO, bajo bloqueo: dos cierres a la vez
            #  no pueden dejar dos notas.
            from campo.models import OrdenTrabajo

            fila = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
            contexto = dict(fila.contexto or {})
            if contexto.get(CLAVE):
                return {"hecho": False, "motivo": "ya_devuelto"}

            caso = Case.objects.select_for_update().filter(
                org=fila.org, pk=case_id).first()
            if caso is None:
                return {"hecho": False, "motivo": "ticket_no_encontrado"}

            Comment.objects.create(
                org=fila.org,
                content_type=ContentType.objects.get_for_model(Case),
                object_id=caso.pk,
                comment=_resumen(fila),
                commented_by=profile,
                #  INTERNA: es el reporte del técnico para quien atiende el
                #  ticket, no un mensaje al cliente. Lo que el cliente recibe
                #  se decide aparte, y no se decide acá.
                is_internal=True,
            )
            #  EL CIERRE SOLO SI SEGUIA ABIERTO: a quien ya cerro no se le
            #  cambia su decision, pero la nota queda igual.
            cerrado = False
            if caso.status != "Closed":
                caso.status = "Closed"
                caso.closed_on = timezone.localdate()
                if not caso.resolved_at:
                    caso.resolved_at = timezone.now()
                caso.save(update_fields=["status", "closed_on", "resolved_at",
                                         "updated_at"])
                cerrado = True

            Activity.objects.create(
                #  EL PROFILE, NO SU USER  --  06/11/2026
                #
                #  `Activity.user` es FK a Profile. Con `profile.user`
                #  esto levantaba ValueError ("must be a Profile
                #  instance") y el `except` de abajo se lo tragaba: la
                #  nota quedaba y la entrada en la LINEA DE TIEMPO no.
                #  Nadie lo vio porque el cierre seguia funcionando.
                #  Se encontro al escribir el aviso del avance, que
                #  copio esta misma linea.
                user=profile,
                action=ACCION,
                entity_type="Case",
                entity_id=caso.pk,
                entity_name=str(caso)[:255],
                metadata={
                    "fuente": "campo",
                    "orden": str(fila.id),
                    "orden_numero": fila.numero,
                    "cerro_el_ticket": cerrado,
                },
                org_id=fila.org_id,
            )

            contexto[CLAVE] = {
                "cuando": timezone.now().isoformat(),
                "caso": str(caso.pk),
                "cerro_el_ticket": cerrado,
            }
            fila.contexto = contexto
            fila.save(update_fields=["contexto"])
        return {"hecho": True, "motivo": "cerrado" if cerrado else "ya_estaba_cerrado"}
    except Exception as e:                                       # noqa: BLE001
        #  El tipo y no el texto: un mensaje puede arrastrar datos de cliente.
        logger.warning("Campo: no se pudo devolver al ticket (%s)",
                       type(e).__name__)
        return {"hecho": False, "motivo": f"error:{type(e).__name__}"}
