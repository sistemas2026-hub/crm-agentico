# -*- coding: utf-8 -*-
"""
================================================================================
 CIERRE DE UN CASO POR UNA PROPUESTA ACEPTADA  --  M09-S
================================================================================

QUE HACE, Y QUE NO
------------------
Ejecuta UNA cosa: el cierre de un caso del CRM que una persona autorizo al
aceptar una propuesta de 'caso_desincronizado'. No decide si corresponde
cerrarlo -- eso ya se decidio del otro lado, y las validaciones sobre el caso
las hace quien SI puede leerlo.

POR QUE EL TRABAJO ESTA PARTIDO EN DOS LADOS
--------------------------------------------
No es una eleccion de diseno, es lo que los privilegios permiten. Medido contra
produccion el 28/09/2026:

  crm_user (Django)   USAGE en el esquema 'asistente'  ->  NO
                      leer el interruptor              ->  NO
                      escribir en ejecucion_autonoma   ->  NO
  app_backend (motor) privilegios sobre public."case"  ->  NINGUNO
                      (y la RLS de esa tabla compara contra 'app.current_org',
                       una variable que este lado no fija)

O sea: el kill switch, la frontera y la idempotencia SOLO se pueden consultar
desde aca; el caso SOLO se puede validar desde alla. Cada mitad hace lo unico
que puede hacer, y ninguna de las dos se puede saltar la otra.

LA PUERTA ES 'humana()', Y ESO TIENE UNA CONSECUENCIA
-----------------------------------------------------
La accion nace de una persona que acepto una propuesta concreta, asi que entra
por 'frontera.humana()' con el id de esa propuesta como evidencia -- que es
justo el ejemplo de evidencia fuerte que esa funcion documenta.

Pero 'humana()' NO consulta el kill switch, a proposito y para todo el sistema:
exigirle una autorizacion de autonomia dejaria sin operar al panel el dia que se
revoque una herramienta. Para ESTE camino eso no alcanza: una propuesta aceptada
a las 10:00 no tiene por que ejecutarse a las 10:05 si a las 10:03 alguien tiro
el interruptor. Asi que el kill switch se consulta AQUI, explicitamente, antes
de abrir la puerta -- sin cambiar 'humana()' ni afectar a ningun otro flujo.

Es el mismo criterio que M06-A tomo para las irreversibles en 'critica()', y por
el mismo motivo.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar

#  Codigos de resultado. Viajan al llamador y a la bitacora; el llamador decide
#  que le dice a la persona, pero no puede inventar un estado que no este aca.
CERRADO = "CERRADO"
BLOQUEADO_POR_INTERRUPTOR = "BLOQUEADO_POR_INTERRUPTOR"
SIN_HERRAMIENTA = "SIN_HERRAMIENTA_DE_CIERRE"
NO_EJECUTADA = "NO_EJECUTADA"
FALLO = "FALLO_AL_CERRAR"


class ResultadoCierre:
    """
    Lo que paso, en una forma que el llamador pueda registrar tal cual.

    'referencia' es lo que va a 'PropuestaSupervisor.accion_propuesta_ref': la
    clave de la operacion idempotente, no un id inventado aca.
    """

    __slots__ = ("codigo", "motivo", "referencia", "respuesta")

    def __init__(self, codigo: str, motivo: str = "", referencia: str = "",
                 respuesta=None):
        self.codigo = codigo
        self.motivo = motivo
        self.referencia = referencia
        self.respuesta = respuesta

    @property
    def cerrado(self) -> bool:
        return self.codigo == CERRADO

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "motivo": self.motivo,
                "referencia": self.referencia, "cerrado": self.cerrado}


def _herramienta_de_cierre(config):
    """
    La que el tenant declara con 'cierra_caso'. Se busca por la BANDERA y no por
    el nombre: es como ya la encuentra 'nucleo/relevo/worker_reconciliador.py',
    y un tenant puede llamarla distinto.
    """
    return next((h for h in config.herramientas
                 if getattr(h, "cierra_caso", False)), None)


def cerrar_caso_de_propuesta(config, tenant: str, *, propuesta_id: str,
                             id_caso: str, actor: str = "") -> ResultadoCierre:
    """
    Cierra el caso que una propuesta aceptada autorizo. A lo sumo una vez.

    'propuesta_id' no es decorativo: es la evidencia que exige la puerta humana
    Y el origen estable de la idempotencia. El mismo id en un reintento no
    vuelve a ejecutar -- excluye por clave primaria, no por un select previo.
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor

    propuesta_id = str(propuesta_id or "").strip()
    id_caso = str(id_caso or "").strip()
    if not propuesta_id or not id_caso:
        return ResultadoCierre(
            NO_EJECUTADA,
            "hacen falta la propuesta y el caso: sin las dos no hay ni "
            "evidencia ni operacion que identificar")

    herr = _herramienta_de_cierre(config)
    if herr is None:
        return ResultadoCierre(
            SIN_HERRAMIENTA,
            "el tenant no declara ninguna herramienta con 'cierra_caso'")

    #  EL KILL SWITCH, ANTES DE ABRIR LA PUERTA
    #  ----------------------------------------
    #  Va aca y no dentro de 'humana()' porque 'humana()' sirve a todo el panel
    #  y no debe empezar a exigir autonomia. Falla CERRADO: si no se puede leer
    #  el interruptor, no se cierra. "No se pudo comprobar" no es "adelante".
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("cierre_propuesta",
                  "no se pudo leer el interruptor: NO se cierra el caso",
                  propuesta=propuesta_id, error=e)
        return ResultadoCierre(
            BLOQUEADO_POR_INTERRUPTOR,
            f"no se pudo comprobar el interruptor de autonomia "
            f"({type(e).__name__}): no se cierra")
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(
            tenant, actor=actor or f"propuesta:{propuesta_id}",
            recurso=f"herramienta:{herr.nombre}",
            motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoCierre(
            BLOQUEADO_POR_INTERRUPTOR,
            f"{veredicto.estado}: {veredicto.motivo}")

    #  Los argumentos RESUELTOS, que son los que se firman en la idempotencia.
    #  'status' y 'closed_on' salen de la declaracion de la herramienta
    #  ('argumentos_fijos' y 'fechas_automaticas'), NO de quien llama: lo unico
    #  que aporta el llamador es de que caso se trata. Por eso
    #  'argumentos_sobrescribibles' de esa herramienta es exactamente [id_caso].
    from datetime import datetime, timedelta

    argumentos = dict(herr.argumentos_fijos or {})
    for campo, dias in (herr.fechas_automaticas or {}).items():
        fecha = datetime.now() + timedelta(days=dias)
        argumentos[campo] = fecha.strftime(herr.formato_fechas_automaticas)
    argumentos["id_caso"] = id_caso

    origen = f"propuesta:{propuesta_id}"
    evidencia = origen

    def _hacer():
        #  La puerta se abre DENTRO de la operacion idempotente, no al reves: si
        #  la operacion ya estaba hecha, no hace falta ningun permiso porque no
        #  se va a ejecutar nada.
        with frontera.humana(tenant, herr.nombre, actor=actor or origen,
                             evidencia=evidencia, origen=origen):
            return ejecutor_http.ejecutar(
                herr, argumentos, tenant,
                variables_tenant=config.variables_tenant)

    try:
        resultado = idempotencia.ejecutar(
            tenant, herr.nombre, argumentos, origen, _hacer)
    except Exception as e:                                   # noqa: BLE001
        #  La excepcion se vuelve a levantar tal cual por idempotencia.ejecutar,
        #  y la operacion queda 'fallida' con su error. El caso NO se cierra, y
        #  quien llamo tiene que poder distinguir esto de un bloqueo.
        registrar("cierre_propuesta", "el cierre del caso fallo",
                  propuesta=propuesta_id, error=e)
        return ResultadoCierre(FALLO, f"{type(e).__name__}: {e}",
                               referencia=origen)

    #  'repetida' NO es un fallo: significa que esta misma propuesta ya cerro
    #  este caso antes y el registro devolvio lo que contesto el CRM la primera
    #  vez. Tratarlo como error haria que un reintento inofensivo se viera como
    #  un cierre roto. Es la misma distincion que hace 'Resultado.hubo_respuesta'.
    if resultado.decision == "repetida":
        return ResultadoCierre(CERRADO, "ya se habia ejecutado antes",
                               referencia=origen, respuesta=resultado.respuesta)

    if not resultado.ejecutada:
        #  El registro lo impidio: en curso, la clave se reuso con otros
        #  argumentos, fallo antes sin autorizacion de reintento, o el control
        #  no esta instalado. Se devuelve SU codigo tal cual en vez de
        #  traducirlo, para que el motivo no se pierda por el camino.
        return ResultadoCierre(
            NO_EJECUTADA, resultado.codigo or resultado.decision or "",
            referencia=origen)

    return ResultadoCierre(CERRADO, "", referencia=origen,
                           respuesta=resultado.respuesta)
