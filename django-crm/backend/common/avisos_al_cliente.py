"""
================================================================================
 PEDIRLE AL MOTOR UN AVISO PARA EL CLIENTE  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================
Los avisos proactivos (visita programada, ticket creado...) los DECIDE el
motor: interruptor, horario de la empresa, baja, plantilla, una sola vez por
clave. El CRM solo detecta el hecho y pide. Esto es el pedido, igual para
todos: la URL del motor, su token de servicio, y si el motor contesta cuando
volver ('reintentar_en': fuera del horario, o el ISP no contesto), en cuantos
segundos reagendar. Cada tarea vuelve a mirar su hecho antes de pedir de nuevo.

Un motor caido no rompe nada: el aviso no sale y queda en el log.
================================================================================
"""
import logging
import os

logger = logging.getLogger(__name__)

#: Cuantas veces se reagenda un aviso que el motor dejo para mas tarde. Las
#: esperas se parten en tramos de ESPERA_MAXIMA_S (una noche son ~14), y el
#: tope evita una tarea viva para siempre.
MAX_VUELTAS = 40
#: Por debajo del visibility_timeout de Redis (3600 s por defecto): una tarea
#: con una espera mas larga se reentrega cada hora, y a las 7:00 despertaban
#: una docena de copias del mismo aviso (auditor independiente, 31/10/2026).
ESPERA_MAXIMA_S = 45 * 60


def pedir(url, cuerpo, que):
    """POST /avisos/evento. Lo que contesto el motor, o None si no contesto."""
    import requests

    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(f"{url.rstrip('/')}/avisos/evento", json=cuerpo,
                          headers=cabeceras, timeout=30)
        datos = r.json() if r.content else {}
    except Exception:  # noqa: BLE001 -- un motor caido no rompe a quien pidio
        logger.warning("aviso al cliente: el motor no contesto (%s)", que)
        return None
    logger.info("aviso al cliente: %s http=%s enviado=%s motivo=%s",
                que, r.status_code, datos.get("enviado"), datos.get("motivo"))
    return datos


def reagendar_en(datos, vuelta):
    """Segundos hasta volver a pedir, o None si no hay que volver."""
    if not isinstance(datos, dict) or datos.get("reintentar_en") is None:
        return None
    if vuelta >= MAX_VUELTAS:
        return None
    try:
        return min(max(int(datos.get("reintentar_en")), 5), ESPERA_MAXIMA_S)
    except (TypeError, ValueError):
        return 60
