"""Tareas de solicitudes (12/11/2026).

Una sola: volver a pedir el aviso de rechazo cuando el motor contesto
'todavia_no' (se rechazo fuera del horario de avisos de la empresa). Mismo
patron que el aviso de visita (campo/tasks.py::avisar_visita_al_cliente): la
tarea vuelve a mirar la solicitud antes de pedir, y el motor no manda dos
avisos con la misma clave.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def avisar_rechazo_al_cliente(solicitud_id, org_id, vuelta=0):
    from common.tasks import clear_rls_context, set_rls_context
    from solicitudes.decision import avisar_rechazo
    from solicitudes.models import SolicitudServicio

    set_rls_context(org_id)
    try:
        s = SolicitudServicio.objects.filter(id=solicitud_id, org_id=org_id).first()
    finally:
        clear_rls_context()
    if s is None:
        logger.info("avisar_rechazo_al_cliente: la solicitud ya no existe")
        return None
    return avisar_rechazo(s, vuelta=int(vuelta or 0))
