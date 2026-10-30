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


def _es_actor_del_sistema(actor: str) -> bool:
    """Si `actor` es una identidad del sistema (`techo.ACTORES_DEL_SISTEMA`) y
    no una persona: «supervisor», «Supervisor de Dexter», «servicio:...»."""
    from nucleo.seguridad import techo as techos

    nombre = (actor or "").strip().lower()
    for sistema in techos.ACTORES_DEL_SISTEMA:
        if sistema.endswith(":"):
            if nombre.startswith(sistema):
                return True
        elif (nombre == sistema or nombre.startswith(sistema + " ")
              or nombre.startswith(sistema + ":")):
            return True
    return False


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
    #  UN ACTOR DEL SISTEMA NO ENTRA POR ACA (auditoria de frontera,
    #  30/10/2026, H2). Esta puerta abre `frontera.humana()`, que no consulta la
    #  etapa de Autonomia 2 ni la autorizacion de la herramienta: un «Supervisor»
    #  por aca seria lo automatico disfrazado de humano. El suyo es
    #  `cerrar_ticket_por_el_supervisor`, por la autonoma.
    if _es_actor_del_sistema(actor):
        return ResultadoCierreTicket(
            NO_EJECUTADA,
            "un actor del sistema no cierra por la puerta humana: el Supervisor "
            "cierra por la autonoma")

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
            #  CLAVE FIJA POR ORDEN. La clave por defecto incluye el hash de los
            #  argumentos, y el texto entra en ellos: si cambiaba entre dos
            #  intentos -- una foto mas, otro nombre -- era OTRA operacion y el
            #  ticket recibia el texto dos veces (auditoria de frontera,
            #  13/10/2026, H2). Fija, una huella distinta se RECHAZA.
            resultado = idempotencia.ejecutar(
                tenant, herr.nombre, argumentos, origen, _hacer,
                clave=f"{origen}|{herr.nombre}")
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


# =============================================================================
#  EL SUPERVISOR CIERRA SOLO  --  30/10/2026
# =============================================================================
#
#  SPEC/objetivos/revision-del-cierre.md. El usuario: «¿de que manera hacemos
#  para que el supervisor cierre solo?». Lo de arriba es la puerta HUMANA: una
#  persona valido y su nombre es la evidencia. Esto es la OTRA puerta, la
#  AUTONOMA: nadie lo pidio en el momento; el Supervisor reviso el cierre en
#  codigo (`campo/revision_del_cierre.py`) y lo dio por bueno.
#
#  POR QUE NO SE REUSA LA FUNCION DE ARRIBA CON actor="supervisor": esa abre
#  `frontera.humana()`, que no consulta la etapa de Autonomia 2 ni la
#  autorizacion de la herramienta. Un Supervisor por esa puerta seria lo
#  automatico disfrazado de humano: el agujero que `humana()` dice que existe
#  para no tener.
#
#  `frontera.autonoma()` consulta, en orden: el interruptor, el techo, la etapa
#  (AUTONOMIA_2_ACTIVA + el prerequisito B-7 medido contra la base) y la
#  autorizacion granular de ESTA herramienta. Cualquiera cerrada -> no sale,
#  y el resultado dice CUAL, para que la oficina sepa que falta.
#
#  LA MISMA CLAVE QUE LA PUERTA HUMANA (auditoria de frontera, 30/10/2026,
#  H3). La primera version usaba una propia, y la unica exclusion entre las dos
#  puertas era un `select` en el CRM (`_ya_cerrado`) que se escribe despues del
#  200: una persona validando mientras el Supervisor cerraba publicaba dos
#  veces (medido con una sonda: 2 POST al mismo ticket). Ahora las dos reclaman
#  `orden_validada:<orden>|<herramienta>` por clave primaria: la segunda,
#  quien sea, no publica. El `origen` sigue diciendo quien fue, para la
#  bitacora.
#
#  LA QUINTA COMPUERTA (H1). La herramienta de cierre declara
#  `aprobacion_humana` (M06-E, 22/09/2026: no se midio si el ISP le avisa al
#  cliente ni si el cierre se deshace). `frontera.exigir` la rechaza para un
#  permiso autonomo, pero lo hace DENTRO de la ejecucion: el intento quedaba
#  marcado como fallido y la orden ya no se podia reintentar. Se pregunta
#  ANTES de reclamar la clave, y el motivo lo dice.
#
#  INCIERTO NO ES «NO PUDO». En curso, fallida antes, o la clave usada con
#  otro texto (la otra puerta ya publico): no se sabe si el ISP lo cerro, y se
#  dice asi, para que alguien lo mire alla en vez de reintentar a ciegas.

#: El actor de la puerta autonoma: no es una persona, y no se finge que lo sea.
SUPERVISOR = "supervisor"

#: Lo que firma el texto del ticket. El ISP firma con la API key; esto dice
#: que lo cerro el Supervisor y no una persona de la oficina.
FIRMA_DEL_SUPERVISOR = "Supervisor de Dexter"

#: Una compuerta de la puerta autonoma lo freno. El motivo dice cual.
NO_AUTORIZADA = "NO_AUTORIZADA_PARA_EL_SUPERVISOR"

#: No se sabe si el ISP lo cerro: hay que mirarlo alla.
INCIERTO = "ESTADO_INCIERTO"


def cerrar_ticket_por_el_supervisor(config, tenant: str, *, orden_id: str,
                                    ticket: str, texto: str) -> ResultadoCierreTicket:
    """Cierra el ticket de una orden que el Supervisor reviso y dio por buena.
    Por la puerta AUTONOMA. A lo sumo una vez por orden."""
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguimiento.operativo import _firmado
    from nucleo.seguridad import frontera, idempotencia
    from nucleo.seguridad import techo as techos

    orden_id = str(orden_id or "").strip()
    ticket = str(ticket or "").strip()
    texto = str(texto or "").strip()
    if not orden_id or not ticket or not texto:
        return ResultadoCierreTicket(
            NO_EJECUTADA, "hacen falta la orden, el ticket y el texto")

    herr = _herramienta_de_cierre(config)
    if herr is None:
        return ResultadoCierreTicket(
            SIN_HERRAMIENTA,
            "el tenant no declara ninguna herramienta con 'cierra_ticket_operativo'")

    argumentos = dict(herr.argumentos_fijos or {})
    argumentos.update({"id_ticket": ticket,
                       "respuesta": _firmado(texto, FIRMA_DEL_SUPERVISOR)})
    origen = f"orden_cerrada_por_el_supervisor:{orden_id}"
    clave = f"orden_validada:{orden_id}|{herr.nombre}"

    def _hacer():
        return ejecutor_http.ejecutar(herr, argumentos, tenant,
                                      variables_tenant=config.variables_tenant)

    try:
        #  El nivel y el efecto salen del CATALOGO, como en el motor: nadie que
        #  llame puede bajarse la exigencia.
        with frontera.autonoma(tenant, herr.nombre, origen=origen, actor=SUPERVISOR,
                               nivel_requerido=techos.nivel_requerido_de(herr),
                               efecto_externo=frontera.efecto_externo(herr)):
            if getattr(herr, "aprobacion_humana", False):
                raise frontera.AccionExternaNoAutorizada(
                    herr.nombre, frontera.APROBACION_REQUERIDA,
                    f"'{herr.nombre}' declara aprobacion humana (M06-E): el "
                    f"Supervisor no la ejecuta solo hasta que se mida si el ISP "
                    f"le avisa al cliente y se levante esa marca")
            resultado = idempotencia.ejecutar(
                tenant, herr.nombre, argumentos, origen, _hacer, clave=clave)
    except frontera.AccionExternaNoAutorizada as e:
        return ResultadoCierreTicket(NO_AUTORIZADA, f"{e.codigo}: {e.motivo}",
                                     referencia=origen)
    except Exception as e:                                   # noqa: BLE001
        registrar("cierre_validacion", "el cierre del Supervisor fallo", error=e)
        return ResultadoCierreTicket(FALLO, type(e).__name__, referencia=origen)

    if resultado.decision == "repetida":
        return ResultadoCierreTicket(CERRADO, "ya se habia cerrado antes",
                                     referencia=origen)
    if not resultado.ejecutada:
        codigo = resultado.codigo or resultado.decision or ""
        if codigo in (idempotencia.EN_CURSO, idempotencia.FALLIDA_PREVIA,
                      idempotencia.CLAVE_REUTILIZADA):
            return ResultadoCierreTicket(
                INCIERTO, f"{codigo}: no se sabe si el ISP lo cerro; hay que "
                          f"mirarlo en su sistema", referencia=origen)
        return ResultadoCierreTicket(NO_EJECUTADA, codigo, referencia=origen)
    return ResultadoCierreTicket(CERRADO, "", referencia=origen)
