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

LA FICHA DEL ISP, SOLO SI HACE FALTA  --  30/10/2026
Quien detecta el hecho no siempre tiene el telefono: el CRM, al atar un caso
a su ticket, solo sabe el numero de servicio. Entonces pasa 'servicio' y el
motor -- que es quien tiene la credencial del ISP -- lee nombre y telefono de
la ficha (ficha_de). Se lee DESPUES del horario y solo si falta algo: con el
chat real del caso y el nombre en mano, el ISP no se toca. Lo leido vive en
memoria: no se guarda, no se registra, y el telefono no viaja en los datos de
la plantilla. Si el ISP no contesta, no sale y pide volver (REINTENTO_ISP_S).
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nucleo.canales.canal import REALES
from nucleo.seguimiento import destino as destinos

#: Cuanto esperar para volver a leer la ficha si el ISP no contesto.
REINTENTO_ISP_S = 15 * 60


def partes_del_nombre(nombre: str | None) -> dict:
    """El nombre del ISP como lo lee un cliente: 'BEATRIZ PINZON' -> 'Beatriz'.

    Solo se acomoda si viene TODO en mayusculas (asi lo guardan muchos ISP); un
    nombre ya escrito con cuidado ('María de los Ángeles') no se toca."""
    limpio = " ".join(str(nombre or "").split())
    if not limpio:
        return {}
    if limpio == limpio.upper():
        limpio = limpio.title()
    primero, _, resto = limpio.partition(" ")
    return {"cliente_nombre": primero, "cliente_apellidos": resto,
            "cliente_nombre_completo": limpio}


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
           conversacion_de, ya_escribio, de_baja, enviar,
           servicio: str | None = None, ficha_de=None) -> dict:
    """{'enviado', 'motivo'[, 'reintentar_en']}. Las consultas y el envio se
    inyectan: conversacion_de(caso_id) -> {canal, usuario_externo} | None,
    ya_escribio(numero) -> bool, de_baja(identificador) -> bool,
    enviar = mensajes_automaticos.enviar, ficha_de(servicio) -> {nombre,
    telefono} | None (lee el ISP; puede lanzar)."""
    espera = _segundos_hasta_el_horario(config, ahora)
    if espera:
        return {"enviado": False, "motivo": "todavia_no", "reintentar_en": espera}

    contexto = dict(contexto or {})
    conversacion = conversacion_de(caso_id) if caso_id else None
    del_chat = None
    if conversacion and conversacion.get("canal") in REALES:
        del_chat = conversacion.get("usuario_externo")
        #  La baja se pide desde el chat, y se guarda con el identificador del
        #  chat tal cual -- un numero o un BSUID. Si ese pidio la baja, no se
        #  le escribe tampoco al movil del ISP: es la misma persona.
        if del_chat and de_baja(del_chat):
            return {"enviado": False, "motivo": "de_baja"}
    falta_destino = not del_chat and not telefono_crudo
    falta_nombre = not contexto.get("cliente_nombre")
    if servicio and ficha_de and (falta_destino or falta_nombre):
        try:
            ficha = ficha_de(servicio) or {}
        except Exception:                                       # noqa: BLE001
            if falta_destino:
                return {"enviado": False, "motivo": "isp_no_contesta",
                        "reintentar_en": REINTENTO_ISP_S}
            ficha = {}
        if falta_destino:
            telefono_crudo = ficha.get("telefono")
        for k, v in partes_del_nombre(ficha.get("nombre")).items():
            contexto.setdefault(k, v)
    numero, por_que = destinos.elegir(config, conversacion=del_chat, telefono_crudo=telefono_crudo,
                                      ya_escribio=ya_escribio)
    if not numero:
        return {"enviado": False, "motivo": por_que}
    return enviar(config, tenant, evento, numero, contexto, clave)
