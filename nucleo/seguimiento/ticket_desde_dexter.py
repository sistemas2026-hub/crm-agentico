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

  1. valida que el asunto sea uno de 'tickets_desde_dexter.asuntos' (o, desde
     el 28/10/2026, del catalogo completo del ISP si la empresa lo pidio) y
     que el servicio exista en el ISP -- antes de escribir nada afuera;
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

EL ADJUNTO (27/10/2026), si viene, va DESPUES de atar, al ticket ya creado
('adjunta_archivo_ticket'). Si falla, el ticket ya existe y el resultado lo
dice ('adjunto': False): el archivo es una comodidad, no el ticket. Lo que se
sube al ISP puede quedar publico (ver la herramienta en la config del tenant),
asi que el nombre original no viaja: va uno aleatorio con su extension.
================================================================================
"""

from __future__ import annotations

import base64
import binascii
import time
import uuid
from pathlib import PurePath
from types import SimpleNamespace

from nucleo.herramientas import http as ejecutor_http
from nucleo.modelo.motor import _ejecutar_tool
from nucleo.observabilidad.registro import id_interno, ref_sesion, registrar
from nucleo.seguimiento import agendamiento, importacion_io
from nucleo.seguridad import frontera

ORIGEN = "ticket_desde_dexter"
# El mismo tope que el CRM para un adjunto (common/utils.py,
# ATTACHMENT_MAX_BYTES): lo que el CRM acepto, aca no se rechaza.
ADJUNTO_MAX_BYTES = 25 * 1024 * 1024
CATALOGO_VIGENCIA_S = 3600
_CATALOGOS: dict[str, tuple[float, list[str]]] = {}


class TicketNoCreado(Exception):
    """Por que no se creo, con un codigo fijo que la pantalla traduce."""

    def __init__(self, codigo: str, http: int = 400):
        super().__init__(codigo)
        self.codigo = codigo
        self.http = http


def _herramienta(config, bandera: str):
    return next((h for h in config.herramientas if getattr(h, bandera, False)), None)


def _cadenas(dato) -> list[str]:
    """Toda cadena que venga dentro de una lista, en orden y sin repetir."""
    vistas, salida = set(), []

    def recorrer(x, en_lista=False):
        if isinstance(x, dict):
            for v in x.values():
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v, en_lista=True)
        elif en_lista and isinstance(x, str) and x.strip() and x.strip() not in vistas:
            vistas.add(x.strip())
            salida.append(x.strip())

    recorrer(dato)
    return salida


def _catalogo(config, tenant: str | None) -> list[str] | None:
    """
    TODOS los asuntos del proveedor (28/10/2026). [] si la empresa no lo
    pidio; None si lo pidio y el proveedor no contesto -- y no hay copia.

    Se guarda una hora en la RAM del proceso: es un catalogo, cambia cuando
    el ISP agrega un asunto, y la pantalla lo pide cada vez que se abre.
    """
    if not config.tickets_desde_dexter.catalogo_del_proveedor or not tenant:
        return []
    herr = _herramienta(config, "lista_asuntos_ticket")
    if herr is None:
        return []
    guardado = _CATALOGOS.get(tenant)
    if guardado and time.monotonic() - guardado[0] < CATALOGO_VIGENCIA_S:
        return guardado[1]
    try:
        lista = _cadenas(ejecutor_http.ejecutar(
            herr, {}, tenant, variables_tenant=config.variables_tenant))
    except Exception as e:                                       # noqa: BLE001
        registrar("ticket_desde_dexter", "no se pudo leer el catalogo de asuntos",
                  tenant=tenant, error=e)
        return guardado[1] if guardado else None
    _CATALOGOS[tenant] = (time.monotonic(), lista)
    return lista


def asuntos(config, tenant: str | None = None) -> list[dict]:
    """
    Los asuntos que la pantalla ofrece. Vacio = apagado.

    Primero los FRECUENTES de la config, con su area; despues el resto del
    catalogo del proveedor en orden alfabetico, con el area por defecto. Si
    el proveedor no contesta, quedan los frecuentes: la pantalla sigue.
    """
    td = config.tickets_desde_dexter
    salida = [{"asunto": a.asunto, "area": a.area, "frecuente": True} for a in td.asuntos]
    ya = {a.asunto for a in td.asuntos}
    resto = sorted((a for a in (_catalogo(config, tenant) or []) if a not in ya),
                   key=lambda a: a.casefold())
    salida += [{"asunto": a, "area": td.area_por_defecto, "frecuente": False} for a in resto]
    return salida


def _elegir(config, tenant: str, asunto: str):
    """El asunto con su area y prioridad, o TicketNoCreado si no se ofrece."""
    td = config.tickets_desde_dexter
    elegido = next((a for a in td.asuntos if a.asunto == (asunto or "")), None)
    if elegido is not None:
        return elegido
    lista = _catalogo(config, tenant)
    if lista is None:
        raise TicketNoCreado("ISP_NO_CONTESTA", 502)
    if (asunto or "") in lista:
        return SimpleNamespace(asunto=asunto, area=td.area_por_defecto,
                               prioridad=td.prioridad_por_defecto)
    raise TicketNoCreado("ASUNTO_NO_PERMITIDO")


def _servicio(servicio) -> str:
    s = str(servicio or "").strip()
    if not s.isdigit() or len(s) > 12:
        raise TicketNoCreado("SERVICIO_INVALIDO")
    return s


def _adjunto(archivo) -> dict | None:
    """
    El archivo como lo pide 'argumentos_archivo' ({nombre, tipo, base64}), ya
    validado, o None si no vino. Se valida ANTES de escribir nada afuera: un
    base64 roto no tiene que dejar un ticket creado y el archivo perdido.
    """
    if not archivo:
        return None
    if not isinstance(archivo, dict) or not isinstance(archivo.get("base64"), str):
        raise TicketNoCreado("ADJUNTO_INVALIDO")
    try:
        crudo = base64.b64decode(archivo["base64"], validate=True)
    except (binascii.Error, ValueError):
        raise TicketNoCreado("ADJUNTO_INVALIDO")
    if not crudo:
        raise TicketNoCreado("ADJUNTO_INVALIDO")
    if len(crudo) > ADJUNTO_MAX_BYTES:
        raise TicketNoCreado("ADJUNTO_MUY_GRANDE")
    extension = PurePath(str(archivo.get("nombre") or "")).suffix.lower()
    if not extension[1:].isalnum() or len(extension) > 8:
        extension = ""
    return {"nombre": f"adjunto-{uuid.uuid4().hex}{extension}",
            "tipo": str(archivo.get("tipo") or "application/octet-stream")[:100],
            "base64": archivo["base64"]}


def _adjuntar(config, tenant, caso_id, servicio, id_ticket, adjunto, autor) -> bool:
    """Sube el adjunto al ticket ya creado. False si no se pudo (y se registra)."""
    herramienta = _herramienta(config, "adjunta_archivo_ticket")
    if herramienta is None:
        registrar("ticket_desde_dexter", "sin herramienta para adjuntar: el archivo queda en el CRM",
                  caso_id=id_interno(caso_id))
        return False
    try:
        with frontera.puerta(tenant, herramienta.nombre, actor=autor,
                             evidencia=f"caso:{caso_id}", origen=ORIGEN):
            _ejecutar_tool(
                herramienta, SimpleNamespace(id_cliente=servicio), {}, tenant,
                variables_tenant=config.variables_tenant,
                sobrescribir={"id_ticket": str(id_ticket), "archivo_ticket": adjunto},
                origen=f"{ORIGEN}:{caso_id}:adjunto", aprobada_por_humano=True)
        return True
    except Exception as e:                                       # noqa: BLE001
        registrar("ticket_desde_dexter", "el ticket se creo pero el archivo no se adjunto",
                  caso_id=id_interno(caso_id), error=e)
        return False


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
          descripcion: str, autor: str, archivo: dict | None = None) -> dict:
    """
    Crea el ticket del caso en el ISP, ata el caso a el, y le adjunta el
    archivo si vino uno.

    Devuelve {'id_ticket', 'vinculado'}, mas 'adjunto' (bool) si vino archivo.
    'vinculado' en False significa que el ticket SI se creo pero el caso no
    quedo atado (otro caso ya tenia ese ticket, el CRM no contesto): la
    pantalla lo dice, porque es justo el caso que la importacion podria
    duplicar. Lanza TicketNoCreado si no se creo.
    """
    adjunto = _adjunto(archivo)
    elegido = _elegir(config, tenant, asunto)
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
    resultado = {"id_ticket": str(id_ticket), "vinculado": vinculado}
    if adjunto is not None:
        resultado["adjunto"] = _adjuntar(config, tenant, caso_id, s, id_ticket, adjunto, autor)
    return resultado
