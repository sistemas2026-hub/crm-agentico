# -*- coding: utf-8 -*-
"""
================================================================================
 MENSAJES AUTOMATICOS: UN SOLO CAMINO PARA TODOS LOS AVISOS  --  28/10/2026
================================================================================

Dexter reemplaza al CRM que mandaba los avisos por WhatsApp. Cada momento
(ticket creado, pago confirmado, recordatorio...) tiene en la config de la
empresa su plantilla y QUE dato va en cada {{n}}; el catalogo de momentos y de
datos esta en nucleo/config/mensajes_catalogo.py.

Quien dispara (el cierre de un caso, el registro de un pago, la tarea diaria)
solo dice: este evento, a este numero, con estos datos, por este motivo. Lo
demas es comun y esta aca:

  1. apagado / canal apagado / sin numero          -> no sale
     en MODO PRUEBA ('solo_a') y no es uno de esos numeros -> no sale, y no
     reserva: cuando se abra a todos, ese motivo todavia puede salir
  2. al CLIENTE, si pidio no recibir avisos         -> no sale (Ley 1581)
  3. la plantilla tiene que estar APROBADA y pedir tantos valores como datos
     hay; un dato vacio cae a su respaldo, y sin respaldo no sale
     (Meta rechaza un valor vacio -- mejor no mandar que mandar a medias)
  4. se RESERVA el motivo antes de mandar: el mismo motivo no lo dispara dos
     veces (un reintento, una tarea que corre de nuevo)
  5. se manda; Meta lo rechaza -> 'fallido'; sin respuesta -> queda reservado
     y no se reintenta: mandarlo dos veces es peor que no saber si salio.

Nunca levanta por una decision; si por la base (falla cerrado: sin poder
comprobar la baja o reservar, no se manda).
================================================================================
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from nucleo.canales import whatsapp
from nucleo.config.mensajes_catalogo import EVENTOS, RESPALDOS_POR_DEFECTO
from nucleo.observabilidad.registro import registrar
from nucleo.persistencia import db as persistencia
from nucleo.persistencia import mensajes_automaticos as registro_envios


class DatoFaltante(ValueError):
    """Un dato que la plantilla pide, vacio y sin respaldo."""

    def __init__(self, dato: str):
        super().__init__(dato)
        self.dato = dato


def _limpio(valor) -> str:
    """Meta rechaza saltos de linea y tabuladores en un valor, y mas de cuatro
    espacios seguidos: se aplanan."""
    return " ".join(str(valor if valor is not None else "").split())


def fuera_de_prueba(m, numero: str | None) -> bool:
    """
    True si el momento esta en MODO PRUEBA ('solo_a' con numeros) y este no es
    uno de ellos (29/10/2026). Se compara solo por los digitos: el remitente
    de WhatsApp llega sin '+'. Un destino que no es un numero (un BSUID) no
    esta en la lista, y no sale: en prueba, ante la duda, a nadie.
    """
    if not getattr(m, "solo_a", None):
        return False
    return "".join(ch for ch in str(numero or "") if ch.isdigit()) not in m.solo_a


def contexto_comun(config, contexto: dict | None) -> dict:
    """Lo que todo momento tiene: la empresa y la fecha de hoy (en su zona)."""
    identidad = config.identidad
    try:
        hoy = datetime.now(ZoneInfo(identidad.zona_horaria))
    except Exception:                                            # noqa: BLE001
        hoy = datetime.now()
    base = {"empresa": identidad.nombre_comercial or identidad.nombre_legal,
            "fecha": hoy.strftime("%d/%m/%Y")}
    return {**base, **(contexto or {})}


def valores(config, evento: str, contexto: dict | None) -> list[str]:
    """Los valores de la plantilla de 'evento', en orden. DatoFaltante si uno
    queda vacio sin respaldo."""
    m = config.mensajes_automaticos.get(evento)
    datos = list(m.datos) if m else []
    respaldos = {**RESPALDOS_POR_DEFECTO, **(config.respaldos_mensajes or {})}
    ctx = contexto_comun(config, contexto)
    salida = []
    for dato in datos:
        v = _limpio(ctx.get(dato)) or _limpio(respaldos.get(dato))
        if not v:
            raise DatoFaltante(dato)
        salida.append(v)
    return salida


def plantilla_aprobada(config, tenant: str, nombre: str) -> dict | None:
    """La ficha de la plantilla si esta APROBADA en Meta; None si no."""
    return next((p for p in whatsapp.plantillas_aprobadas(config, tenant)
                 if p.get("nombre") == nombre and (p.get("estado") or "").upper() == "APPROVED"),
                None)


def enviar(config, tenant: str, evento: str, para: str | None, contexto: dict | None,
           clave: str) -> dict:
    """{'enviado': bool, 'motivo': str|None}. Ver el encabezado del modulo."""
    if evento not in EVENTOS:
        return {"enviado": False, "motivo": "evento_desconocido"}
    m = config.mensajes_automaticos.get(evento)
    if not m or not m.activo:
        return {"enviado": False, "motivo": "apagado"}
    if m.plantilla in (config.plantillas_desactivadas or []):
        return {"enviado": False, "motivo": "plantilla_desactivada"}
    if not whatsapp.activo(config):
        return {"enviado": False, "motivo": "canal_apagado"}
    numero = _limpio(para)
    if not numero:
        return {"enviado": False, "motivo": "sin_numero"}
    if fuera_de_prueba(m, numero):
        return {"enviado": False, "motivo": "fuera_de_prueba"}
    if EVENTOS[evento]["destinatario"] == "cliente" and persistencia.esta_de_baja(tenant, numero, "whatsapp"):
        return {"enviado": False, "motivo": "de_baja"}

    try:
        ficha = plantilla_aprobada(config, tenant, m.plantilla)
    except Exception as e:                                       # noqa: BLE001
        registrar("mensajes", "no se pudieron leer las plantillas", tenant=tenant, evento=evento, error=e)
        return {"enviado": False, "motivo": "meta_no_contesta"}
    if ficha is None:
        return {"enviado": False, "motivo": "plantilla_no_aprobada"}
    if ficha.get("variables") != len(m.datos) or ficha.get("formato_variables") == "mixto":
        return {"enviado": False, "motivo": "plantilla_no_coincide"}
    try:
        vals = valores(config, evento, contexto)
    except DatoFaltante as e:
        return {"enviado": False, "motivo": f"dato_faltante:{e.dato}"}

    reserva = registro_envios.reservar(tenant, evento, clave, m.plantilla)
    if reserva is None:
        return {"enviado": False, "motivo": "ya_enviado"}
    try:
        wamid = whatsapp.enviar_plantilla_aprobada(
            config, tenant, numero, ficha["nombre"], vals, ficha.get("idioma") or "es", plantilla=ficha)
    except whatsapp.ErrorWhatsApp as e:
        registro_envios.marcar(tenant, reserva, "fallido")
        registrar("mensajes", "Meta rechazo el aviso", tenant=tenant, evento=evento, error=e)
        return {"enviado": False, "motivo": "rechazado"}
    except Exception as e:                                       # noqa: BLE001
        registrar("mensajes", "no se pudo confirmar el aviso", tenant=tenant, evento=evento, error=e)
        return {"enviado": False, "motivo": "incierto"}
    registro_envios.marcar(tenant, reserva, "enviado", wamid)
    registrar("mensajes", "aviso enviado", tenant=tenant, evento=evento)
    return {"enviado": True, "motivo": None}
