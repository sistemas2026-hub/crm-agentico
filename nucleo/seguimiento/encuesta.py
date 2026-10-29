# -*- coding: utf-8 -*-
"""
================================================================================
 LA ENCUESTA DE SATISFACCION POR WHATSAPP  --  28/10/2026
================================================================================

El CRM ya tenia encuestas, por correo y solo con un contacto con correo: en un
ISP cuyos clientes viven en el sistema del ISP y hablan por WhatsApp, no salia
ninguna. Esto la manda por el canal real.

ENVIAR  (lo pide el CRM, un rato despues de cerrar el caso)
------
  1. apagada, canal apagado, sin chat o el numero dio de baja -> no se manda;
     en modo prueba ('solo_a'), solo a esos numeros;
  2. la plantilla tiene que estar APROBADA y pedir los valores que se le dan;
  3. se RESERVA la fila antes de mandar: si el caso ya tenia una encuesta, no
     sale otra (guardar primero, entregar despues; una por caso);
  4. se manda; con el wamid de Meta queda 'enviada'. Si Meta la rechaza queda
     'fallida', y tampoco se reintenta sola.

RESPONDER  (lo llama el webhook, ANTES del turno)
---------
El boton tocado llega con 'context.id' = el wamid de la plantilla. Si ese
mensaje es una encuesta, se guarda la nota y el que llama le agradece -- y el
mensaje NO va al modelo: "Excelente" no es una pregunta. Si no es una encuesta
(un boton de otra plantilla), sigue al turno como texto, como cualquier otro.

La baja (Ley 1581) bloquea lo PROACTIVO: la encuesta es proactiva, se respeta.
La respuesta no: si el cliente toca el boton, se registra.
================================================================================
"""

from __future__ import annotations

from nucleo.canales import whatsapp
from nucleo.observabilidad.registro import id_interno, registrar
from nucleo.persistencia import db as persistencia
from nucleo.persistencia import encuestas
from nucleo.seguimiento import mensajes_automaticos as mensajes

#: El momento del catalogo: su plantilla, sus datos y si esta encendida viven
#: en mensajes_automaticos['encuesta_cierre'], como cualquier otro aviso.
EVENTO = "encuesta_cierre"


def enviar(config, tenant: str, caso_id: str, *, responsable_id: str | None = None,
           responsable_nombre: str | None = None, area: str | None = None,
           ticket_numero: str | None = None) -> dict:
    """{'enviada': bool, 'motivo': str|None}. Nunca levanta por una decision; si por la base."""
    cfg = config.encuesta_whatsapp
    m = config.mensajes_automaticos.get(EVENTO)
    if not m or not m.activo:
        return {"enviada": False, "motivo": "apagada"}
    if m.plantilla in (config.plantillas_desactivadas or []):
        return {"enviada": False, "motivo": "plantilla_desactivada"}
    if not whatsapp.activo(config):
        return {"enviada": False, "motivo": "canal_apagado"}

    destino = encuestas.destino_del_caso(tenant, caso_id)
    if not destino or destino.get("canal") != "whatsapp" or not destino.get("usuario_externo"):
        return {"enviada": False, "motivo": "sin_chat"}
    numero = destino["usuario_externo"]
    if mensajes.fuera_de_prueba(m, numero):
        return {"enviada": False, "motivo": "fuera_de_prueba"}
    if persistencia.esta_de_baja(tenant, numero, "whatsapp"):
        return {"enviada": False, "motivo": "de_baja"}

    try:
        aprobadas = whatsapp.plantillas_aprobadas(config, tenant)
    except Exception as e:                                       # noqa: BLE001
        registrar("encuesta", "no se pudieron leer las plantillas", tenant=tenant, error=e)
        return {"enviada": False, "motivo": "meta_no_contesta"}
    elegida = next((p for p in aprobadas if p.get("nombre") == m.plantilla
                    and (p.get("estado") or "").upper() == "APPROVED"), None)
    if elegida is None:
        return {"enviada": False, "motivo": "plantilla_no_aprobada"}
    if elegida.get("variables") != len(m.datos) or elegida.get("formato_variables") == "mixto":
        return {"enviada": False, "motivo": "plantilla_no_coincide"}
    completo = " ".join((destino.get("nombre_cliente") or "").split())
    try:
        valores = mensajes.valores(config, EVENTO, {
            "cliente_nombre": completo.split(" ")[0] if completo else "",
            "cliente_nombre_completo": completo,
            "responsable": responsable_nombre or "",
            "ticket_numero": ticket_numero or ""})
    except mensajes.DatoFaltante as e:
        return {"enviada": False, "motivo": f"dato_faltante:{e.dato}"}

    encuesta_id = encuestas.reservar(
        tenant, caso_id, str(destino["id"]), m.plantilla, cfg.vigencia_horas,
        responsable_id=responsable_id, responsable_nombre=responsable_nombre, area=area)
    if encuesta_id is None:
        return {"enviada": False, "motivo": "ya_enviada"}

    try:
        wamid = whatsapp.enviar_plantilla_aprobada(
            config, tenant, numero, elegida["nombre"], valores,
            elegida.get("idioma") or "es", plantilla=elegida)
    except whatsapp.ErrorWhatsApp as e:
        encuestas.marcar_fallida(tenant, encuesta_id)
        registrar("encuesta", "Meta rechazo la encuesta", tenant=tenant,
                  caso_id=id_interno(caso_id), error=e)
        return {"enviada": False, "motivo": "rechazada"}
    except Exception as e:                                       # noqa: BLE001
        #  Sin respuesta NO es "no salio": queda reservada y no se reintenta.
        #  Si salio, el cliente la tiene; su respuesta no se podra atar (no
        #  hay wamid), y eso es menos malo que mandarsela dos veces.
        registrar("encuesta", "no se pudo confirmar el envio de la encuesta",
                  tenant=tenant, caso_id=id_interno(caso_id), error=e)
        return {"enviada": False, "motivo": "incierto"}
    encuestas.marcar_enviada(tenant, encuesta_id, wamid)
    registrar("encuesta", "encuesta enviada", tenant=tenant, caso_id=id_interno(caso_id))
    return {"enviada": True, "motivo": None}


def puntaje_de(cfg, opcion: str) -> int | None:
    """El puntaje del boton: el texto exacto, o sin distinguir mayusculas."""
    if opcion in cfg.opciones:
        return int(cfg.opciones[opcion])
    sin = (opcion or "").strip().casefold()
    return next((int(p) for o, p in cfg.opciones.items() if o.strip().casefold() == sin), None)


def responder_boton(config, tenant: str, entrante: dict) -> dict | None:
    """
    None si el boton no responde a una encuesta (sigue al turno). Si responde,
    el resultado de encuestas.responder: registrada, o por que no.
    """
    contexto = entrante.get("contexto")
    if not contexto or entrante.get("tipo") not in ("button", "interactive"):
        return None
    opcion = (entrante.get("texto") or "").strip()
    r = encuestas.responder(tenant, contexto, opcion, puntaje_de(config.encuesta_whatsapp, opcion))
    if not r["encuesta"]:
        return None
    registrar("encuesta", "respuesta de encuesta", tenant=tenant,
              caso_id=id_interno(r["caso_id"]), registrada=r["registrada"], motivo=r["motivo"])
    return r
