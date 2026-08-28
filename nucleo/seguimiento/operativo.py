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

from datetime import datetime, timedelta

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


def cerrar_caso_crm(config, tenant: str, caso_id: str) -> bool:
    """
    Cierra el caso en el CRM, que es lo que ademas le devuelve el control al
    asistente: el turno siguiente comprueba contra el CRM si el caso sigue
    abierto (ver escalamiento.caso_sigue_abierto), no confia en la marca.

    Sin esto, cerrar el ticket del ISP y la conversacion dejaria el caso vivo
    en la cola del equipo y al bot en pausa para siempre.
    """
    herr = _herramienta(config, "cierra_caso")
    if herr is None or not caso_id:
        return False
    argumentos = dict(herr.argumentos_fijos or {})
    # Las fechas que se calculan en el momento, igual que hace motor.py con
    # las herramientas que llama el modelo. Aca hace falta porque cerrar un
    # caso suele exigir la fecha de cierre, y esa no se puede dejar fija en el
    # YAML: seria el dia en que alguien la escribio.
    for campo, dias in (herr.fechas_automaticas or {}).items():
        fecha = datetime.now() + timedelta(days=dias)
        argumentos[campo] = fecha.strftime(herr.formato_fechas_automaticas)
    argumentos["id_caso"] = str(caso_id)
    try:
        ejecutor_http.ejecutar(herr, argumentos, tenant)
        return True
    except Exception as e:
        print(f"[operativo] no se pudo cerrar el caso {caso_id}: "
              f"{type(e).__name__}: {e}")
        return False


def cerrar_todo(config, tenant: str, conversacion: dict, texto: str,
                autor: str = "") -> dict:
    """
    Termina un caso en los TRES lados donde dejo rastro: el ticket del ISP, el
    caso del CRM y la conversacion.

    Devuelve que se pudo cerrar y que no, sin abandonar a la primera falla: un
    CRM caido no es motivo para dejar ademas el ticket del ISP abierto. Lo que
    no cierre queda en el log y se vuelve a intentar la proxima pasada, porque
    la conversacion recien se cierra si el caso tambien se cerro -- si no,
    seguiria apareciendo como pendiente sin que nadie la mire.
    """
    from nucleo.persistencia import db as persistencia

    hecho = {"ticket": False, "caso": False, "conversacion": False}
    if conversacion.get("ticket_operativo"):
        hecho["ticket"] = cerrar(config, tenant,
                                 conversacion["ticket_operativo"], texto, autor)
    if conversacion.get("caso_id"):
        hecho["caso"] = cerrar_caso_crm(config, tenant, conversacion["caso_id"])
    if hecho["caso"] or not conversacion.get("caso_id"):
        try:
            persistencia.cerrar_conversacion(tenant, conversacion["id"])
            hecho["conversacion"] = True
        except Exception as e:
            print(f"[operativo] no se pudo cerrar la conversacion "
                  f"{conversacion['id']}: {type(e).__name__}: {e}")
    return hecho


# Cada cuanto se revisan los plazos. No hace falta mas fino: el plazo se mide
# en horas, asi que una pasada por hora se pasa como mucho 59 minutos del
# vencimiento -- y cerrar un caso una hora despues no le cambia la vida a
# nadie, mientras que revisar cada minuto son 60 consultas por hora para no
# encontrar nada.
INTERVALO_BARRIDO_SEGUNDOS = 3600


def cerrar_vencidas(config, tenant: str) -> dict:
    """
    Cierra las conversaciones escaladas donde el cliente dejo de contestar.

    'escalamiento.cerrar_sin_respuesta_horas' del tenant manda: en 0 --el valor
    por defecto-- esto no hace nada. Una empresa que no lo pidio no deberia
    encontrarse casos cerrados solos.

    Cerrar aca no pierde nada: si el cliente escribe despues, su mensaje abre
    una conversacion nueva y el asistente lo atiende normal (ver
    cerrar_conversacion en persistencia). Lo que se cierra es la espera, no el
    vinculo.
    """
    from nucleo.persistencia import db as persistencia

    horas = config.escalamiento.cerrar_sin_respuesta_horas
    resumen = {"revisadas": 0, "cerradas": 0}
    if not horas or horas <= 0:
        return resumen

    texto = (config.escalamiento.texto_cierre_sin_respuesta or "").strip() or (
        f"Se cierra por falta de respuesta del cliente: pasaron {horas} horas "
        f"desde su ultimo mensaje.")
    try:
        pendientes = persistencia.conversaciones_sin_respuesta(tenant, horas)
    except Exception as e:
        print(f"[operativo] no se pudieron listar las vencidas de '{tenant}': "
              f"{type(e).__name__}: {e}")
        return resumen

    resumen["revisadas"] = len(pendientes)
    for conv in pendientes:
        hecho = cerrar_todo(config, tenant, conv, texto)
        if hecho["conversacion"]:
            resumen["cerradas"] += 1
        print(f"[operativo] vencida {str(conv['id'])[:8]}: ticket="
              f"{hecho['ticket']} caso={hecho['caso']} conversacion="
              f"{hecho['conversacion']}")
    return resumen
