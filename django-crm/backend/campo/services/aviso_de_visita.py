"""
================================================================================
 EL AVISO AL CLIENTE DE QUE SU VISITA QUEDO PROGRAMADA  --  30/10/2026
================================================================================
PRD §8.17, Ola 2. Al publicar el dia (el Supervisor o el ciclo de la
madrugada), por cada orden publicada se le pide al motor el aviso
`visita_programada`. El motor decide si sale: el interruptor del aviso, el
horario de la empresa (una publicacion de las 3 a. m. espera a la manana), la
baja del cliente y UNA sola vez por clave. Aca solo se arma el pedido.

La clave es la orden Y la fecha: si la visita se reprograma a otro dia, el
cliente recibe el aviso nuevo; si se vuelve a publicar el mismo dia, no.

El telefono va CRUDO, como esta en la orden: lo normaliza el motor con el
indicativo de la empresa (nucleo/seguimiento/destino.py). El numero no se
guarda en ningun lado nuevo.
================================================================================
"""
from __future__ import annotations

import zoneinfo

from django.db import transaction

EVENTO = "visita_programada"


def _zona(org):
    nombre = (getattr(org, "timezone", "") or "UTC").strip() or "UTC"
    try:
        return zoneinfo.ZoneInfo(nombre)
    except Exception:                                            # noqa: BLE001
        return zoneinfo.ZoneInfo("UTC")


def _hora(instante, zona) -> str:
    local = instante.astimezone(zona)
    return f"{local.hour}:{local.minute:02d}"


def pedido(orden, fecha, tenant: str) -> dict:
    """Lo que se le manda al motor (POST /avisos/evento) por esta orden y fecha."""
    nombre = (orden.cliente_nombre or "").strip()
    contexto = {
        "cliente_nombre": nombre.split(" ")[0] if nombre else "",
        "cliente_nombre_completo": nombre,
        #  La direccion NO viaja: junto con la hora de la visita diria donde y
        #  cuando hay alguien esperando a un tecnico (revisor de PII).
        "fecha_visita": fecha.strftime("%d/%m/%Y"),
    }
    #  La franja que se le prometio al cliente, en la hora de SU empresa. Sin
    #  franja no se inventa una: la plantilla usa el respaldo de la empresa.
    if orden.ventana_inicio and orden.ventana_fin:
        zona = _zona(orden.org)
        contexto["franja"] = f"{_hora(orden.ventana_inicio, zona)} a {_hora(orden.ventana_fin, zona)}"
    return {
        "tenant": tenant,
        "evento": EVENTO,
        "clave": f"visita:{orden.id}:{fecha.isoformat()}",
        #  Solo un caso tiene conversacion detras; un ticket del ISP no.
        "caso_id": (orden.origen_ref or None) if orden.origen_tipo == "case" else None,
        "telefono": orden.cliente_telefono or "",
        "contexto": contexto,
    }


def por_que_no_avisar(orden, fecha) -> str | None:
    """None si la visita sigue en pie para esa fecha; si no, por que.

    El aviso puede salir horas despues de publicar (una publicacion de noche
    espera a la manana), y en el medio la orden pudo cancelarse o moverse. Se
    repiten las reglas con las que publicar decide (campo/reparto.py): que la
    orden siga esperando a alguien, que siga asignada, que no se haya pasado
    a otro dia, y que la fecha no haya pasado en el reloj de la empresa.
    """
    from campo import reparto

    if orden.estado_operativo not in reparto.ESTADOS_QUE_ESPERAN:
        return "ya_no_espera"
    if not orden.asignaciones.exists():
        return "sin_asignar"
    zona = reparto._zona_de(orden.org)
    if reparto._para_otro_dia(orden, fecha, zona):
        return "reprogramada"
    from django.utils import timezone
    if fecha < timezone.now().astimezone(zona).date():
        return "fecha_pasada"
    return None


def pedir_despues_del_commit(org, ordenes_por_fecha: dict) -> None:
    """Encola un pedido por orden, recien cuando la publicacion quedo escrita.
    Si la transaccion se deshace, no sale nada."""
    from campo.tasks import avisar_visita_al_cliente

    pares = [(str(orden_id), fecha.isoformat())
             for fecha, ids in ordenes_por_fecha.items() for orden_id in ids]
    if not pares:
        return

    def encolar():
        for orden_id, fecha in pares:
            avisar_visita_al_cliente.delay(orden_id, str(org.id), fecha)

    transaction.on_commit(encolar)
