"""El prospecto que registra el asistente nace con origen WhatsApp (12/11/2026).

POR QUE ACA Y NO EN EL ENDPOINT
-------------------------------
El Lead lo crea `solicitudes/views.py::SolicitudCrearView`, que es SOLO el
camino del asistente: la llamada del motor cuando cierra una venta por chat.
Ese endpoint escribe `source=datos.get("source") or "other"`, y la config del
tenant mapea `whatsapp -> other` porque el catalogo no tenia el valor. Cambiar
la config de cada empresa para arreglar un catalogo seria al reves: el valor
lo decide el sistema, no el modelo ni la empresa.

`solicitudes/` es de otro modulo, y el criterio vive mejor del lado del Lead:
una solicitud que nace atada a un prospecto prueba que ese prospecto vino del
asistente -- es la unica forma en que hoy se crea una solicitud con Lead.

LO QUE NO PISA
--------------
Solo reemplaza la ausencia de origen ('other', vacio o nulo). Un origen
concreto que alguien haya elegido se respeta.
"""

from __future__ import annotations

from django.db.models import Q

ORIGEN_DEL_ASISTENTE = "whatsapp"
SIN_ORIGEN = ("other", "")


def origen_del_asistente(sender, instance, created, **kwargs):
    if not created or not getattr(instance, "lead_id", None):
        return
    from leads.models import Lead

    (Lead.objects
     .filter(pk=instance.lead_id, org_id=instance.org_id)
     .filter(Q(source__in=SIN_ORIGEN) | Q(source__isnull=True))
     .update(source=ORIGEN_DEL_ASISTENTE))
