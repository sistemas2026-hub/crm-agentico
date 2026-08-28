# -*- coding: utf-8 -*-
"""
================================================================================
 EL TICKET DEL SISTEMA OPERATIVO DEL ISP  --  responderlo y cerrarlo
================================================================================

Una conversacion escalada deja rastro en TRES lados y cada uno sirve para algo
distinto: el chat (lo que se hablo con el cliente), el caso del CRM (la cola
del equipo) y el ticket del sistema del ISP (la operacion, donde se factura el
trabajo y se mira el historico del servicio).

Hasta ahora ese tercero se abria y no se volvia a tocar: la persona respondia
en un lado y cerraba en otro, a mano, y los tres contaban historias distintas.

Que herramienta responde y cual cierra lo declara el tenant
('responde_ticket_operativo' / 'cierra_ticket_operativo' en
nucleo/config/schema.py). Son DOS y no una con un parametro de estado porque
los codigos de estado son del proveedor -- '2 = En Progreso', '4 = Cerrado' en
el primero, vaya a saber que en el siguiente -- y esos valores viven en la
config, nunca aca.

Nada de esto rompe un turno: si el sistema del ISP no responde, la respuesta al
cliente ya salio y el caso del CRM ya esta. Se loguea y sigue.
"""

from __future__ import annotations

from nucleo.herramientas import http as ejecutor_http


def _herramienta(config, atributo: str):
    return next((h for h in config.herramientas
                 if getattr(h, atributo, False)), None)


def _firmado(texto: str, autor: str) -> str:
    """
    El texto con el nombre de quien lo escribio adelante.

    Hace falta porque el proveedor firma toda respuesta con la cuenta de la
    API key -- verificado: quedan como 'Rapilink SAS - admin@...' sin importar
    quien las origino, y el campo del autor no se puede elegir. Sin el nombre
    adentro del texto, el historico del ticket dice que contesto el sistema.
    """
    autor = (autor or "").strip()
    return f"{autor}: {texto}" if autor else texto


def responder(config, tenant: str, ticket: str, texto: str, autor: str = "") -> bool:
    """
    Copia al ticket del ISP lo que se le acaba de responder al cliente.

    Devuelve si se pudo. El ticket queda en el estado que declare la
    herramienta del tenant -- normalmente 'en progreso': una respuesta no
    cierra nada por si sola.
    """
    return _ejecutar(config, tenant, "responde_ticket_operativo",
                     ticket, texto, autor)


def cerrar(config, tenant: str, ticket: str, texto: str, autor: str = "") -> bool:
    """
    Cierra el ticket del ISP dejando escrito con que se cerro.

    El texto no es opcional por diseño: un ticket que aparece cerrado sin una
    linea que diga por que obliga a quien lo audite a reconstruirlo desde el
    chat, que es justo lo que este registro existe para evitar.
    """
    return _ejecutar(config, tenant, "cierra_ticket_operativo",
                     ticket, texto, autor)


def _ejecutar(config, tenant: str, atributo: str, ticket: str,
              texto: str, autor: str) -> bool:
    herr = _herramienta(config, atributo)
    if herr is None or not ticket or not (texto or "").strip():
        return False
    # Los fijos van SIEMPRE, y aca hay que ponerlos a mano: el ejecutor http
    # no los mezcla -- lo hace motor.py antes de llamarlo, y este camino no
    # pasa por el modelo. Sin ellos la llamada sale sin el estado del ticket,
    # que el proveedor exige, y responde 400 (medido el 28/08/2026).
    argumentos = dict(herr.argumentos_fijos or {})
    argumentos.update({"id_ticket": str(ticket),
                       "respuesta": _firmado(texto, autor)})
    try:
        ejecutor_http.ejecutar(herr, argumentos, tenant)
        return True
    except Exception as e:
        print(f"[operativo] '{herr.nombre}' fallo sobre el ticket {ticket}: "
              f"{type(e).__name__}: {e}")
        return False
