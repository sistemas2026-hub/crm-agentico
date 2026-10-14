# -*- coding: utf-8 -*-
"""
================================================================================
 CIERRE DEL TICKET DEL ISP POR UNA ORDEN DE CAMPO VALIDADA
================================================================================

QUE HACE, Y QUE NO
------------------
Ejecuta UNA cosa: cerrar en el sistema del ISP el ticket de una orden de campo
que una persona de la oficina acaba de VALIDAR, dejando escrito que se hizo y
quien lo valido. No decide si corresponde cerrarlo: eso lo decidio esa persona
del otro lado, y la orden solo la puede leer el CRM.

Hasta el 13/10/2026 lo que el tecnico registraba en la app quedaba solo en
Dexter, y el ticket del ISP se cerraba a mano en otro lado -- o no se cerraba.

POR QUE CERRAR, Y NO SOLO RESPONDER
-----------------------------------
Decision del usuario el 13/10/2026: validada la visita, el ticket se CIERRA,
aunque el sistema del ISP le avise al cliente -- el aviso no dice quien lo
cerro. Eso resuelve, para ESTE camino, lo que M06-E dejo indeterminado
(«no hay evidencia de si el ISP notifica al cliente»). El estado de cierre NO
vive aca: lo fija la herramienta del tenant marcada `cierra_ticket_operativo`,
porque los codigos de estado son del proveedor.

LA PUERTA, Y POR QUE ES UNA RUTA PROPIA
---------------------------------------
Mismo criterio que `cierre_por_propuesta`: la accion nace de una persona sobre
una fila concreta -- la orden validada --, asi que entra por `frontera.humana()`
con el id de esa orden como evidencia. Abrir la puerta humana desde la ruta
generica `/interno/herramienta` haria que cualquier servicio que mande un actor
entre por ahi, que es el bypass que `frontera.puerta` documenta como su limite.

Y como `humana()` no consulta el kill switch, se consulta AQUI: una validacion
de las 10:00 no tiene por que cerrar tickets a las 10:05 si a las 10:03 alguien
tiro el interruptor.

A LO SUMO UNA VEZ: la clave idempotente es la orden. Una doble validacion, o un
reintento del CRM, no publica dos veces el texto en el ticket.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar

CERRADO = "CERRADO"
BLOQUEADO_POR_INTERRUPTOR = "BLOQUEADO_POR_INTERRUPTOR"
SIN_HERRAMIENTA = "SIN_HERRAMIENTA_DE_CIERRE"
NO_EJECUTADA = "NO_EJECUTADA"
FALLO = "FALLO_AL_CERRAR"


class ResultadoCierreTicket:
    __slots__ = ("codigo", "motivo", "referencia")

    def __init__(self, codigo: str, motivo: str = "", referencia: str = ""):
        self.codigo = codigo
        self.motivo = motivo
        self.referencia = referencia

    @property
    def cerrado(self) -> bool:
        return self.codigo == CERRADO

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "motivo": self.motivo,
                "referencia": self.referencia, "cerrado": self.cerrado}


def _herramienta_de_cierre(config):
    return next((h for h in config.herramientas
                 if getattr(h, "cierra_ticket_operativo", False)), None)


def cerrar_ticket_de_orden(config, tenant: str, *, orden_id: str, ticket: str,
                           texto: str, actor: str) -> ResultadoCierreTicket:
    """Cierra el ticket de una orden validada. A lo sumo una vez por orden.

    `actor` es OBLIGATORIO: es quien valido. Sin persona responsable esta
    escritura no tiene por que existir, y no se adivina.
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguimiento.operativo import _firmado
    from nucleo.seguridad import frontera, idempotencia, interruptor

    orden_id = str(orden_id or "").strip()
    ticket = str(ticket or "").strip()
    actor = str(actor or "").strip()
    texto = str(texto or "").strip()
    if not orden_id or not ticket or not actor or not texto:
        return ResultadoCierreTicket(
            NO_EJECUTADA,
            "hacen falta la orden, el ticket, quien valido y el texto: sin "
            "eso no hay evidencia, ni responsable, ni que dejar escrito")

    herr = _herramienta_de_cierre(config)
    if herr is None:
        return ResultadoCierreTicket(
            SIN_HERRAMIENTA,
            "el tenant no declara ninguna herramienta con 'cierra_ticket_operativo'")

    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("cierre_validacion",
                  "no se pudo leer el interruptor: NO se cierra el ticket",
                  error=e)
        return ResultadoCierreTicket(
            BLOQUEADO_POR_INTERRUPTOR,
            f"no se pudo comprobar el interruptor ({type(e).__name__}): no se cierra")
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(
            tenant, actor=actor, recurso=f"herramienta:{herr.nombre}",
            motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoCierreTicket(
            BLOQUEADO_POR_INTERRUPTOR, f"{veredicto.estado}: {veredicto.motivo}")

    # Los fijos van SIEMPRE (el estado de cierre, la prioridad): el ejecutor
    # http no los mezcla solo, y sin ellos el proveedor responde 400.
    argumentos = dict(herr.argumentos_fijos or {})
    argumentos.update({"id_ticket": ticket, "respuesta": _firmado(texto, actor)})
    origen = f"orden_validada:{orden_id}"

    def _hacer():
        return ejecutor_http.ejecutar(herr, argumentos, tenant,
                                      variables_tenant=config.variables_tenant)

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor,
                             evidencia=origen, origen=origen):
            resultado = idempotencia.ejecutar(
                tenant, herr.nombre, argumentos, origen, _hacer)
    except Exception as e:                                   # noqa: BLE001
        registrar("cierre_validacion", "el cierre del ticket fallo", error=e)
        return ResultadoCierreTicket(FALLO, type(e).__name__, referencia=origen)

    if resultado.decision == "repetida":
        return ResultadoCierreTicket(CERRADO, "ya se habia cerrado antes",
                                     referencia=origen)
    if not resultado.ejecutada:
        return ResultadoCierreTicket(
            NO_EJECUTADA, resultado.codigo or resultado.decision or "",
            referencia=origen)
    return ResultadoCierreTicket(CERRADO, "", referencia=origen)
