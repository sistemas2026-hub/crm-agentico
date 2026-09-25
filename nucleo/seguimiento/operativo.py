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
from nucleo.observabilidad.registro import id_interno, registrar


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


def _permiso(tenant: str, herramienta: str, actor: str, evidencia: str):
    """
    Que puerta de la frontera le corresponde a esta escritura  --  paso 10.14A.

    Delega en frontera.puerta(), que aplica la misma regla en todo el nucleo:
    con actor identificado entra por la puerta humana (el interruptor no frena
    el trabajo de un operador); sin actor, por la autonoma (consulta el
    interruptor).

    Esta es la separacion que pedia el punto 7: no se declara "humana" porque
    la funcion reciba texto, sino porque llega con un responsable. Sin
    responsable no hay autoria humana que demostrar -- y entonces no se asume.
    """
    from nucleo.seguridad import frontera

    return frontera.puerta(tenant, herramienta, actor=actor,
                           evidencia=evidencia, origen="operativo")


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
        with _permiso(tenant, herr.nombre, autor, f"ticket:{ticket}"):
            ejecutor_http.ejecutar(herr, argumentos, tenant)
        return True
    except Exception as e:
        registrar("operativo", "fallo la herramienta sobre el ticket",
                  herramienta=herr.nombre, ticket=ticket, error=e)
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
        # Cerrar el caso del CRM NUNCA lo pide una persona por esta via: lo
        # decide 'cerrar_todo' cuando el cliente confirma, o el barrido de
        # vencidas. Es autonoma, y pasa por el interruptor.
        with _permiso(tenant, herr.nombre, "", f"caso:{caso_id}"):
            ejecutor_http.ejecutar(herr, argumentos, tenant)
        return True
    except Exception as e:
        registrar("operativo", "no se pudo cerrar el caso", caso_id=id_interno(caso_id), error=e)
        return False


def cerrar_todo(config, tenant: str, conversacion: dict, texto: str,
                autor: str = "", *, por: str = "cliente") -> dict:
    """
    Termina un caso en los TRES lados donde dejo rastro: el ticket del ISP, el
    caso del CRM y la conversacion.

    Devuelve que se pudo cerrar y que no, sin abandonar a la primera falla: un
    CRM caido no es motivo para dejar ademas el ticket del ISP abierto. Lo que
    no cierre queda en el log y se vuelve a intentar la proxima pasada, porque
    la conversacion recien se cierra si el caso tambien se cerro -- si no,
    seguiria apareciendo como pendiente sin que nadie la mire.

    'por' dice cual de los caminos de §6 es este, y por lo tanto que queda
    escrito en la conversacion (B6): 'cliente' cuando el cliente confirmo
    (T15a/T15b, la transicion distingue cual segun 'atendida_manual') y
    'plazo' cuando lo cierra el barrido (T16, desenlace 'sin_respuesta_cliente').
    Sin ese dato el cierre no diria por que, que es lo que B6 vino a arreglar.
    """
    from nucleo.relevo import transiciones

    hecho = {"ticket": False, "caso": False, "conversacion": False}
    if conversacion.get("ticket_operativo"):
        hecho["ticket"] = cerrar(config, tenant,
                                 conversacion["ticket_operativo"], texto, autor)
    if conversacion.get("caso_id"):
        hecho["caso"] = cerrar_caso_crm(config, tenant, conversacion["caso_id"])
    if hecho["caso"] or not conversacion.get("caso_id"):
        try:
            r = transiciones.cerrar(tenant, conversacion["id"], por=por,
                                    config=config)
            # 'ya_cerrada' cuenta como cerrada: alguien se adelanto, y el
            # resultado es el que se buscaba. Lo que NO cuenta es una negativa
            # con motivo ('accion_viva', 'verificacion_pendiente'): ahi la
            # conversacion sigue abierta a proposito y el barrido tiene que
            # volver a pasar.
            hecho["conversacion"] = r.aplicada or r.motivo == "ya_cerrada"
            if not hecho["conversacion"]:
                registrar("operativo", "el cierre no procedio",
                          conversation_id=id_interno(conversacion["id"]),
                          motivo=r.motivo)
        except Exception as e:
            registrar("operativo", "no se pudo cerrar la conversacion",
                      conversation_id=id_interno(conversacion["id"]), error=e)
    return hecho


# Cada cuanto se revisan los plazos. No hace falta mas fino: el plazo se mide
# en horas, asi que una pasada por hora se pasa como mucho 59 minutos del
# vencimiento -- y cerrar un caso una hora despues no le cambia la vida a
# nadie, mientras que revisar cada minuto son 60 consultas por hora para no
# encontrar nada.
INTERVALO_BARRIDO_SEGUNDOS = 3600


def cerrar_inactivas_de_ia(config, tenant: str, simular: bool = False, *,
                           backlog: bool = False,
                           lote: int | None = None) -> dict:
    """
    Cierra las que atendio SOLO el asistente y quedaron mudas.

    DOS COHORTES, Y ESA ES LA GUARDA
    --------------------------------
    'cierre_inactivas_ia.rollout_cutoff' parte el mundo en dos:

      flujo normal  ultima actividad >= corte. Se cierra solo.
      backlog       ultima actividad <  corte. NO se toca hasta que alguien
                    encienda 'backfill_habilitado', y entonces de a
                    'backfill_lote' por pasada.

    La primera version de esta guarda era un tope por pasada, sin frontera.
    Estaba mal de dos formas medidas: ordenaba por mas antigua primero --o
    sea, cerraba el backlog PRIMERO, justo lo que el tope queria evitar-- y
    con el reloj corriendo cada 60 minutos un tope de 10 son 240 cierres por
    dia: las 147 historicas se iban en 0,6 dias. Ir mas despacio no era la
    respuesta; la frontera si.

    SIN CORTE NO CIERRA NADA
    ------------------------
    Ni flujo ni backlog. Desplegar este codigo no puede empezar a cerrar
    conversaciones sin que alguien haya elegido desde cuando.

    EL INTERRUPTOR ES PROPIO
    ------------------------
    'cierre_inactivas_ia.habilitado' apaga ESTE trabajo. Frenarlo apagando el
    reloj entero se llevaria puestos los otros dos, que son legitimos.

    EL PLAZO SIGUE SIENDO 'limites.horas_inactividad_cierra'
    --------------------------------------------------------
    Es el momento exacto en que la conversacion deja de reutilizarse: a
    partir de ahi cerrarla no le quita nada a nadie, y antes le costaria al
    cliente reverificar identidad y perder el serial de la ONU.

    EL DESENLACE ES 'sin_respuesta_cliente', NO 'resuelto'
    ------------------------------------------------------
    Lo fija la transicion (por='plazo'). Es lo unico que se sabe: el
    asistente contesto y el cliente no volvio.

    EL BACKLOG NO CORRE CON EL RELOJ, NUNCA
    ---------------------------------------
    'backlog=False' es el default y es lo que llama el reloj: solo flujo
    normal. Aunque 'backfill_habilitado' este en true, una pasada automatica
    NO consume lote -- si lo hiciera, con el reloj cada 60 minutos y lote 10
    serian 240 cierres por dia y el backlog se iria en menos de un dia, que es
    justo lo que las cohortes existen para evitar.

    'backlog=True' es la ejecucion explicita, a mano:

        python -m nucleo.reloj --backfill-inactivas-ia --limit 10

    Toma como maximo el lote, mas antiguas primero, con las MISMAS guardas que
    el flujo normal y la misma transicion. No toca ninguna conversacion nueva.

    'backfill_lote' es un TECHO DURO: el '--limit' del comando puede bajarlo,
    nunca subirlo. Con la config en 10, '--limit 3' toma 3 y '--limit 50' toma
    10. Un limite que el comando puede pisar no es un limite.

    Los dos interruptores siguen valiendo: sin 'backfill_habilitado' el
    comando tampoco hace nada. Uno autoriza, el otro ejecuta -- y hacen falta
    los dos, porque el comando se puede teclear por costumbre y la
    autorizacion es una decision que quedo escrita en la config.

    'simular' informa las DOS cohortes por separado y no cierra nada.
    """
    from nucleo.persistencia import db as persistencia

    ajustes = getattr(config, "cierre_inactivas_ia", None)
    horas = getattr(config.limites, "horas_inactividad_cierra", None)
    corte = getattr(ajustes, "rollout_cutoff", None) if ajustes else None

    resumen = {"revisadas": 0, "cerradas": 0, "horas": horas,
               "simulado": simular, "nuevas_elegibles": 0,
               "backlog_elegible": 0, "backfill_que_cerraria": 0,
               "backfill_habilitado": bool(getattr(ajustes, "backfill_habilitado", False))}

    if not ajustes or not ajustes.habilitado:
        resumen["motivo"] = "apagado: cierre_inactivas_ia.habilitado esta en false"
        return resumen
    if not horas or horas <= 0:
        resumen["motivo"] = "el tenant no declara limites.horas_inactividad_cierra"
        return resumen
    if corte is None:
        resumen["motivo"] = ("sin cierre_inactivas_ia.rollout_cutoff no se cierra "
                             "nada: hay que elegir desde cuando cuenta la regla")
        return resumen

    lote_config = getattr(ajustes, "backfill_lote", 10)
    try:
        nuevas = persistencia.conversaciones_ia_inactivas(
            tenant, horas, corte=corte, cohorte="normal")
        # 'backfill_lote' ES UN TECHO DURO, no un valor por defecto.
        #
        # El '--limit' del comando solo puede BAJARLO. La primera version
        # dejaba que lo pisara --"quien lo teclea esta mirando"-- y eso
        # convierte el limite de la config en una sugerencia: un '--limit 500'
        # tecleado de apuro se lleva el backlog entero, y la unica barrera
        # seria la persona que acaba de escribir el numero.
        #
        # La config se decide una vez, queda en git y se revisa; el comando se
        # teclea. El techo va del lado que se revisa.
        tope = min(int(lote), lote_config) if lote else lote_config
        candidatas_backlog = persistencia.conversaciones_ia_inactivas(
            tenant, horas, corte=corte, cohorte="backlog", limite=tope)
        # Cuantas hay en total en el backlog, no solo el lote: es el numero
        # que dice cuanto falta, y sin el no se sabe si esto avanza.
        backlog_total = persistencia.conversaciones_ia_inactivas(
            tenant, horas, corte=corte, cohorte="backlog")
    except Exception as e:
        registrar("operativo", "no se pudieron listar las inactivas de la IA",
                  tenant=tenant, error=e)
        return resumen

    resumen["nuevas_elegibles"] = len(nuevas)
    resumen["backlog_elegible"] = len(backlog_total)
    resumen["modo"] = "backlog" if backlog else "normal"

    # Cuantas tomaria la PROXIMA tanda manual. Es informativo y se calcula
    # siempre, tambien en la pasada del reloj: el seco tiene que poder decir
    # cuanto falta y cuanto se llevaria el proximo comando, sin que eso
    # signifique que la pasada las va a cerrar.
    resumen["backfill_que_cerraria"] = (
        len(candidatas_backlog) if resumen["backfill_habilitado"] else 0)

    if backlog:
        # Ejecucion explicita: SOLO el backlog. No se mezclan las cohortes ni
        # aca -- una corrida a mano que ademas cierre las nuevas hace que el
        # informe no diga lo que hizo.
        if not resumen["backfill_habilitado"]:
            resumen["motivo"] = ("el backfill esta apagado: poner "
                                 "cierre_inactivas_ia.backfill_habilitado en true")
            return resumen
        a_cerrar = list(candidatas_backlog)
    else:
        # El reloj. Nunca consume lote del backlog, aunque este autorizado.
        a_cerrar = list(nuevas)
    resumen["revisadas"] = len(a_cerrar)

    if simular:
        resumen["serian"] = [id_interno(c["id"]) for c in a_cerrar]
        return resumen

    for conv in a_cerrar:
        # Mismo camino que el barrido de escaladas. Estas no tienen ticket ni
        # caso --lo exige la consulta-- asi que 'cerrar_todo' solo cierra la
        # conversacion y el texto no se usa.
        hecho = cerrar_todo(config, tenant, conv, "", por="plazo")
        if hecho["conversacion"]:
            resumen["cerradas"] += 1
        registrar("operativo", "inactiva de la IA",
                  conversation_id=id_interno(conv["id"]),
                  conversacion=hecho["conversacion"])
    return resumen


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
        registrar("operativo", "no se pudieron listar las vencidas", tenant=tenant, error=e)
        return resumen

    resumen["revisadas"] = len(pendientes)
    for conv in pendientes:
        hecho = cerrar_todo(config, tenant, conv, texto, por="plazo")
        if hecho["conversacion"]:
            resumen["cerradas"] += 1
        registrar("operativo", "vencida", conversation_id=id_interno(conv["id"]),
                  ticket=hecho["ticket"], caso=hecho["caso"], conversacion=hecho["conversacion"])
    return resumen
