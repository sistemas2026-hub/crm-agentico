# -*- coding: utf-8 -*-
"""
================================================================================
 UN TICKET CREADO EN DEXTER NACE TAMBIEN EN EL SISTEMA DEL ISP  --  26/10/2026
================================================================================

Habia tres puertas de entrada y solo dos llegaban al sistema operativo del ISP:
la llamada (nace alla) y el chat escalado (el motor lo crea al escalar). "Nuevo
ticket" en Dexter quedaba solo aca, invisible para el tecnico, el despacho y la
facturacion. Ver SPEC/objetivos/ticket-de-dexter-tambien-en-wisphub.md.

LO QUE HACE, EN ORDEN
---------------------
El caso YA existe en el CRM (guardar primero, entregar despues). Esto:

  1. valida que el asunto sea uno de 'tickets_desde_dexter.asuntos' y que el
     servicio exista en el ISP -- antes de escribir nada afuera;
  2. crea el ticket con la MISMA herramienta que usa el escalamiento
     ('crea_ticket_operativo'), que ya esta verificada en produccion, a
     nombre del responsable del area si hay uno (como al escalar);
  3. ata el caso a ese ticket ('vincula_caso_externo'), para que la
     importacion lo reconozca y no lo traiga como un caso nuevo.

POR LA PUERTA HUMANA, con la persona que lleno el formulario como actor: no es
el sistema decidiendo solo, y una persona tiene que poder abrir un ticket con
la autonomia detenida. La operacion es UNA por caso ('origen' = el caso): un
reenvio no crea dos tickets, devuelve el que ya se creo.

SIN LA HERRAMIENTA DE VINCULO NO SE CREA NADA. Un ticket sin atar es peor que
no tenerlo: la importacion lo traeria duplicado.
================================================================================
"""

from __future__ import annotations

from types import SimpleNamespace

from nucleo.herramientas import http as ejecutor_http
from nucleo.modelo.motor import _ejecutar_tool
from nucleo.observabilidad.registro import id_interno, ref_sesion, registrar
from nucleo.seguimiento import agendamiento, importacion_io
from nucleo.seguridad import frontera

ORIGEN = "ticket_desde_dexter"


class TicketNoCreado(Exception):
    """Por que no se creo, con un codigo fijo que la pantalla traduce."""

    def __init__(self, codigo: str, http: int = 400):
        super().__init__(codigo)
        self.codigo = codigo
        self.http = http


def _herramienta(config, bandera: str):
    return next((h for h in config.herramientas if getattr(h, bandera, False)), None)


def asuntos(config) -> list[dict]:
    """Los asuntos que la pantalla ofrece. Vacio = apagado."""
    return [{"asunto": a.asunto, "area": a.area}
            for a in config.tickets_desde_dexter.asuntos]


def _servicio(servicio) -> str:
    s = str(servicio or "").strip()
    if not s.isdigit() or len(s) > 12:
        raise TicketNoCreado("SERVICIO_INVALIDO")
    return s


def titular(config, tenant: str, servicio) -> dict | None:
    """
    Nombre y estado del titular del servicio, para que quien llena el
    formulario confirme que es el cliente correcto. None si no existe.

    Solo nombre y estado: la ficha cruda trae cedula, telefono, GPS y cuatro
    contraseñas, y nada de eso hace falta para confirmar (ver
    importacion_io.resolver_servicios, que ya recorta asi).
    """
    s = _servicio(servicio)
    ficha = importacion_io.resolver_servicios(config, tenant)([s]).get(s)
    if not ficha:
        return None
    return {"nombre": ficha.get("nombre") or "", "estado": ficha.get("estado") or ""}


def crear(config, tenant: str, caso_id: str, servicio, asunto: str,
          descripcion: str, autor: str) -> dict:
    """
    Crea el ticket del caso en el ISP y ata el caso a el.

    Devuelve {'id_ticket', 'vinculado'}. 'vinculado' en False significa que el
    ticket SI se creo pero el caso no quedo atado (otro caso ya tenia ese
    ticket, el CRM no contesto): la pantalla lo dice, porque es justo el caso
    que la importacion podria duplicar. Lanza TicketNoCreado si no se creo.
    """
    elegido = next((a for a in config.tickets_desde_dexter.asuntos
                    if a.asunto == (asunto or "")), None)
    if elegido is None:
        raise TicketNoCreado("ASUNTO_NO_PERMITIDO")
    s = _servicio(servicio)
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise TicketNoCreado("FALTA_DESCRIPCION")
    if not (autor or "").strip():
        raise TicketNoCreado("FALTA_AUTOR")
    if not caso_id:
        raise TicketNoCreado("FALTA_CASO")
    crea = _herramienta(config, "crea_ticket_operativo")
    vincula = _herramienta(config, "vincula_caso_externo")
    proveedor = config.importacion_tickets.proveedor
    if crea is None or vincula is None or not proveedor:
        raise TicketNoCreado("NO_CONFIGURADO", 503)

    # Que el servicio exista ANTES de escribir afuera: un ticket sobre un
    # numero mal tipeado le cae al tecnico como trabajo de otro cliente.
    try:
        existe = titular(config, tenant, s)
    except Exception as e:                                       # noqa: BLE001
        registrar("ticket_desde_dexter", "no se pudo leer el servicio",
                  servicio=ref_sesion(s), error=e)
        raise TicketNoCreado("ISP_NO_CONTESTA", 502)
    if existe is None:
        raise TicketNoCreado("SERVICIO_NO_EXISTE", 404)

    sobrescribir = {"asunto": elegido.asunto, "asuntos_default": elegido.asunto}
    if elegido.prioridad:
        sobrescribir["prioridad"] = elegido.prioridad
    externa = getattr(config, "identidad_externa", None)
    if elegido.area and externa:
        quien = agendamiento.responsable_de(tenant, elegido.area, externa.sistema)
        if quien:
            sobrescribir["tecnico"] = quien[0]

    # Quien lo abrio, al pie: el proveedor firma todo con la cuenta de la API,
    # y el tecnico tiene que saber a quien preguntarle (igual que las copias
    # de la Bandeja, ver operativo._firmado).
    texto = f"{descripcion}\n\n-- Creado en Dexter por {autor.strip()}"

    try:
        with frontera.puerta(tenant, crea.nombre, actor=autor,
                             evidencia=f"caso:{caso_id}", origen=ORIGEN):
            respuesta = _ejecutar_tool(
                crea, SimpleNamespace(id_cliente=s),
                {"servicio": s, "descripcion": texto}, tenant,
                variables_tenant=config.variables_tenant,
                sobrescribir=sobrescribir,
                origen=f"{ORIGEN}:{caso_id}", aprobada_por_humano=True)
    except Exception as e:                                       # noqa: BLE001
        registrar("ticket_desde_dexter", "no se pudo crear el ticket",
                  caso_id=id_interno(caso_id), error=e)
        raise TicketNoCreado("NO_SE_CREO", 502)
    id_ticket = respuesta.get("id_ticket") if isinstance(respuesta, dict) else None
    if not id_ticket:
        raise TicketNoCreado("SIN_ID_DE_TICKET", 502)

    argumentos = dict(vincula.argumentos_fijos or {})
    argumentos.update({"id_caso": str(caso_id), "provider": proveedor,
                       "external_ticket_id": str(id_ticket),
                       "external_service_id": s})
    if elegido.area:
        argumentos["area"] = elegido.area
    vinculado = False
    try:
        with frontera.puerta(tenant, vincula.nombre, actor=autor,
                             evidencia=f"caso:{caso_id}", origen=ORIGEN):
            ejecutor_http.ejecutar(vincula, argumentos, tenant)
        vinculado = True
    except Exception as e:                                       # noqa: BLE001
        registrar("ticket_desde_dexter", "el ticket se creo pero el caso no quedo atado",
                  caso_id=id_interno(caso_id), error=e)
    return {"id_ticket": str(id_ticket), "vinculado": vinculado}
