# -*- coding: utf-8 -*-
"""
================================================================================
 LA PUERTA COMUN DE LOS AVISOS PROACTIVOS  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================

Un aviso proactivo es Dexter escribiendole a un cliente que no pregunto: su
visita es hoy, se le abrio un ticket. Quien detecta el hecho (el CRM al
publicar el dia, el motor al crear un ticket) llama aca con el evento, una
CLAVE que identifica el hecho, y lo que sepa del cliente. Esto decide:

  1. CUANDO: dentro del horario de la empresa (horario_avisos). Afuera, no
     sale y contesta 'todavia_no' con los segundos que faltan -- quien llama
     reagenda, igual que con la espera de la encuesta.
  2. A QUIEN: el chat del caso si es de un canal real; si no, el telefono del
     ISP normalizado (nucleo/seguimiento/destino.py).
  3. SI SALE: mensajes_automaticos.enviar -- interruptor del aviso, modo
     prueba, baja (Ley 1581), plantilla aprobada, y UNA sola vez por clave.

No reintenta por su cuenta y no guarda el numero.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nucleo.canales.canal import REALES
from nucleo.seguimiento import destino as destinos


def _segundos_hasta_el_horario(config, ahora: datetime) -> int:
    """0 si 'ahora' esta dentro del horario; si no, cuanto falta para abrirlo."""
    h = config.horario_avisos
    local = ahora.astimezone(ZoneInfo(config.identidad.zona_horaria))
    if h.desde <= local.hour < h.hasta:
        return 0
    apertura = local.replace(hour=h.desde, minute=0, second=0, microsecond=0)
    if local.hour >= h.hasta:
        apertura += timedelta(days=1)
    return int((apertura - local).total_seconds())


def avisar(config, tenant: str, evento: str, clave: str, *, caso_id: str | None,
           telefono_crudo: str | None, contexto: dict | None, ahora: datetime,
           conversacion_de, ya_escribio, de_baja, enviar) -> dict:
    """{'enviado', 'motivo'[, 'reintentar_en']}. Las consultas y el envio se
    inyectan: conversacion_de(caso_id) -> {canal, usuario_externo} | None,
    ya_escribio(numero) -> bool, de_baja(identificador) -> bool,
    enviar = mensajes_automaticos.enviar."""
    espera = _segundos_hasta_el_horario(config, ahora)
    if espera:
        return {"enviado": False, "motivo": "todavia_no", "reintentar_en": espera}

    conversacion = conversacion_de(caso_id) if caso_id else None
    del_chat = None
    if conversacion and conversacion.get("canal") in REALES:
        del_chat = conversacion.get("usuario_externo")
        #  La baja se pide desde el chat, y se guarda con el identificador del
        #  chat tal cual -- un numero o un BSUID. Si ese pidio la baja, no se
        #  le escribe tampoco al movil del ISP: es la misma persona.
        if del_chat and de_baja(del_chat):
            return {"enviado": False, "motivo": "de_baja"}
    numero, por_que = destinos.elegir(config, conversacion=del_chat, telefono_crudo=telefono_crudo,
                                      ya_escribio=ya_escribio)
    if not numero:
        return {"enviado": False, "motivo": por_que}
    return enviar(config, tenant, evento, numero, contexto, clave)
