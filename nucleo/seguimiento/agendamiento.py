# -*- coding: utf-8 -*-
"""
================================================================================
 AGENDAMIENTO AUTOMATICO -- agenda una visita tecnica sin pasar por un humano
================================================================================

Hoy, cuando un especialista tecnico (ej. soporte_tecnico_cliente) decide
escalar una falla de TV, siempre pasa por un humano en BottleCRM -- aunque
el checklist del manual ya haya quedado completo y lo unico que haria esa
persona sea releer la conversacion y llamar a 'agendar_visita_tecnica' con
los mismos datos que el chat ya reunio.

Este modulo hace esa misma relectura, con el manual real como referencia
(mismo patron que nucleo/seguimiento/supervisor.py: RAG-grounded, para
juzgar contra el procedimiento documentado, no contra la opinion general
del modelo). Solo corre para los casos que el tenant declaro
explicitamente en 'escalamiento.agendamiento_automatico' -- ver
nucleo/config/schema.py:Escalamiento. Apagado por defecto.

FALLA CERRADA, siempre: cualquier duda, dato faltante o error tecnico cae
al camino de hoy (escalar a un humano). Nunca se resuelve una duda a favor
de agendar -- despachar un tecnico es mas costoso que abrir un ticket.

SEGUNDA CAPA (PRD 7.4): el modelo decide SI corresponde agendar y compone
una descripcion legible; el CODIGO valida que los datos minimos esten
presentes y ejecuta la escritura real contra WispHub -- nunca via
tool-calling del modelo. Mismo principio que ya aplica
escalamiento.escalar() al crear el ticket de BottleCRM en codigo.
================================================================================
"""

from __future__ import annotations

import json

from nucleo.modelo import cliente
from nucleo.modelo.motor import _buscar_campo, _ejecutar_tool
from nucleo.persistencia import db as persistencia
from nucleo.seguimiento import reparto
from nucleo.recuperacion import busqueda


# La herramienta con la que se lee la carga de casos. Es el mismo nombre
# que ya usa el catalogo del tenant para consultar casos.
NOMBRE_HERRAMIENTA_CASOS = "consultar_casos_bottlecrm"


def _esquema_verificacion(config) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "verificar_agendamiento",
            "description": (
                "Revisa si el checklist del manual para este caso quedo "
                "completo en la conversacion, y si corresponde agendar una "
                "visita tecnica sin pasar por un humano."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "checklist_completo": {
                        "type": "boolean",
                        "description": "true si cada punto del "
                            "procedimiento (ver el manual mas abajo) fue "
                            "preguntado Y recibio una respuesta suficiente "
                            "en la conversacion. false si falta alguno.",
                    },
                    "corresponde_agendar": {
                        "type": "boolean",
                        "description": "Solo tiene sentido si "
                            "checklist_completo=true. true si, con todo "
                            "dentro de lo recomendado, la falla persiste "
                            "(posible falla real del servicio). false si el "
                            "procedimiento explica el problema por una "
                            "causa del lado del cliente -- en ese caso NO "
                            "corresponde agendar nada, se sigue orientando "
                            "al cliente.",
                    },
                    "pregunta_faltante": {
                        "type": "string",
                        "description": "Solo si checklist_completo=false: "
                            "la UNICA pregunta puntual que falta para "
                            "completarlo (no un resumen de todo lo que "
                            "falta, un solo punto concreto).",
                    },
                    "descripcion_visita": {
                        "type": "string",
                        "description": "Solo si corresponde_agendar=true: "
                            "2-3 frases describiendo el caso para el "
                            "tecnico que va a la visita -- que se "
                            "confirmo, que no se explica por causas del "
                            "cliente. Solo lo que la conversacion confirmo "
                            "de verdad, nunca inventado.",
                    },
                },
                "required": ["checklist_completo"],
            },
        },
    }


def verificar(config, tenant: str, rol: str, historial: list[dict]) -> dict | None:
    """
    Le pide al modelo que revise, contra el manual real, si el checklist de
    este caso quedo completo y si corresponde agendar. Nunca rompe el turno:
    un fallo (RAG caido, el modelo no respondio con la funcion) devuelve
    None, y quien llama cae al camino de escalar a un humano -- ver el
    docstring del modulo, "falla cerrada, siempre".

    Usa la transcripcion COMPLETA, no un resumen corto: un resumen de 2-3
    frases (como el que ya arma escalamiento.evaluar()) puede omitir justo
    el campo que falto, y es exactamente lo que hay que poder detectar.
    """
    pregunta = " ".join(
        m.get("content", "") for m in historial
        if m.get("role") == "user" and m.get("content"))[:2000]
    try:
        fragmentos, _ = busqueda.recuperar(config, tenant, rol, pregunta) \
            if pregunta.strip() else ([], None)
    except Exception as e:
        print(f"[agendamiento] no se pudo consultar el manual: "
              f"{type(e).__name__}: {e}")
        fragmentos = []

    if not fragmentos:
        # Sin el procedimiento real no hay contra que verificar el
        # checklist -- no se inventa un criterio general aca (a diferencia
        # del supervisor, que si puede opinar sin manual). Cae al camino de
        # siempre.
        print("[agendamiento] no se encontro el procedimiento del manual "
              "para este caso, se cae al camino humano")
        return None

    cuerpo_manual = "\n\n".join(f.citar() for f in fragmentos)
    referencia_modelo = config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto)
    mensajes = historial + [{
        "role": "user",
        "content": (
            "(Instruccion del sistema, no del cliente) Revisa la "
            "conversacion de arriba contra el procedimiento real de abajo "
            "y evaluala llamando a verificar_agendamiento. No respondas "
            "con texto.\n\n"
            "PROCEDIMIENTO DEL MANUAL para este caso:\n\n"
            f"{cuerpo_manual}"
        ),
    }]
    try:
        # TIMEOUT_SECUNDARIO, mismo motivo que escalamiento.evaluar(): esto
        # corre despues de que la respuesta del cliente ya se calculo, pero
        # antes de devolverle el HTTP. Si tarda, se abandona esta vuelta.
        respuesta = cliente.chat(
            referencia_modelo, mensajes, tools=[_esquema_verificacion(config)],
            timeout=cliente.TIMEOUT_SECUNDARIO)
    except Exception as e:
        print(f"[agendamiento] fallo al verificar: {type(e).__name__}: {e}")
        return None

    for llamada in respuesta.llamadas:
        if llamada.nombre == "verificar_agendamiento":
            return llamada.argumentos
    return None


def evidencia_ya_alcanza(config, caso: str, historial: list[dict]) -> str | None:
    """
    Si la traza ya prueba, por si sola, que corresponde una visita.

    Devuelve el motivo legible (para el log) o None si hay que pasar por el
    verificador del manual, que es el camino normal.

    Por que existe: el verificador contrasta la conversacion contra el
    procedimiento que el RAG recupere, y ese procedimiento esta escrito para
    una persona que atiende -- no para un agente que ya midio la OLT. Visto
    el 21/08/2026, una falla sin señal optica no llegaba a agendar nunca
    porque el checklist recuperado exigia "¿que mensaje aparece en el
    dispositivo?", una pregunta que no tiene respuesta cuando no hay ninguna
    conexion de la cual leer un mensaje.

    Solo se salta el verificador donde la evidencia viene de la RED y no del
    relato del cliente. Cada condicion la declara el tenant
    ('escalamiento.evidencia_suficiente') con la misma forma que
    'Herramienta.exige_previas'; sin declararlas, todo sigue pasando por el
    verificador.
    """
    return _primera_que_cumple(
        (config.escalamiento.evidencia_suficiente or {}).get(caso), historial)


def veto_de_agendamiento(config, caso: str, historial: list[dict]) -> str | None:
    """
    Si la traza dice que agendar una visita seria un ERROR, aunque todo lo
    demas de al derecho. Devuelve el motivo legible o None.

    El caso que lo motiva: una caida que afecta a varios clientes del mismo
    puerto. Vista desde la ONU de UNO, se ve identica a su fibra cortada
    -- misma causa 'sin señal optica', que es justamente la evidencia que
    hace saltar el checklist y agendar sola. Con treinta personas
    reportando la misma caida, eso son treinta tecnicos despachados a
    treinta casas por una falla que esta en la red y no en ninguna de
    ellas.

    Va en CODIGO y no en el prompt por lo de siempre (PRD 7.4): el prompt
    ya le pide al modelo que no lo trate como falla puntual, pero lo que
    escribe el ticket es esta ruta, no el modelo. Si el veto vive donde se
    ejecuta la escritura, no hay redaccion que se lo saltee.

    Fail-closed al reves que 'evidencia_suficiente': ante la duda NO veta
    (una condicion que no matchea deja el camino normal), porque el camino
    normal ya es el conservador -- pasa por el verificador del manual.
    """
    return _primera_que_cumple(
        (config.escalamiento.no_agendar_si or {}).get(caso), historial)


def ticket_para_escalar(config, caso: str, historial: list[dict]):
    """
    Que herramienta crea el ticket operativo al pasar este caso a una persona.

    Gana la PRIMERA entrada cuyas condiciones cumpla la traza; una entrada sin
    condiciones es el caso por defecto y por eso el esquema la obliga a ir
    ultima. Devuelve el nombre de la herramienta, o None si el tenant no
    declaro ticket para este caso (que es lo normal: se declara a proposito).

    Por que el asunto depende de la traza y no del caso a secas: el asunto es
    lo primero que lee quien toma el trabajo, antes de abrir la descripcion.
    Una lentitud sin causa identificada y una con la optica fuera de rango se
    atienden distinto, y en el catalogo del ISP ya son dos asuntos separados
    -- usar el que corresponde es gratis y evita que el tecnico llegue con la
    idea equivocada.
    """
    for entrada in (config.escalamiento.ticket_al_escalar or {}).get(caso) or []:
        if not entrada.condiciones:
            return entrada
        if _primera_que_cumple(entrada.condiciones, historial):
            return entrada
    return None


def _primera_que_cumple(condiciones, historial: list[dict]) -> str | None:
    """La primera condicion que la traza de ESTA conversacion satisface.

    'exige_previas' de una herramienta hace lo mismo sobre el mismo
    historial; esto lo separa para poder usarlo tambien desde el
    agendamiento, sin que ninguno de los dos sepa del otro.
    """
    for cond in (condiciones or []):
        for msg in historial:
            if msg.get("role") != "tool" or msg.get("name") != cond.herramienta:
                continue
            try:
                dato = json.loads(msg.get("content") or "null")
            except (TypeError, ValueError):
                continue
            # Una herramienta que fallo no prueba nada, ni a favor ni en
            # contra: se ignora y se sigue buscando.
            if isinstance(dato, dict) and dato.get("error"):
                continue
            if cond.acepta(_buscar_campo(dato, cond.campo)):
                return f"{cond.herramienta}.{cond.campo}"
    return None


def asunto_fijo_de(config, herramienta: str) -> str:
    """
    El asunto con el que una herramienta de agendamiento entra al sistema
    operativo, leido de su propia declaracion.

    Existe porque hay DOS caminos que abren un ticket y solo uno pasaba su
    asunto al caso del CRM. Cuando la visita se agenda sola, nadie elige un
    asunto en el turno: lo trae fijo la herramienta que corresponde al caso
    (escalamiento.agendamiento_automatico es un mapa caso -> herramienta,
    justamente para que cada caso entre con el suyo). Sin leerlo de ahi, ese
    caso quedaba en la bandeja titulado "Consulta" -- el titulo mas pobre de
    todos le tocaba justo al que YA tiene un tecnico en camino.

    Se lee de la config y no se deduce del caso: el asunto pertenece al
    catalogo del ISP, y el motor no tiene por que conocer ese vocabulario.
    """
    for herr in config.herramientas:
        if herr.nombre == herramienta:
            return (herr.argumentos_fijos or {}).get("asunto", "") or ""
    return ""


def perfil_del_area(tenant: str, area: str, config=None) -> str | None:
    """
    A quien del area se le asigna el caso: al que MENOS tiene abierto.

    Antes, con dos o mas personas, esto devolvia None y el caso quedaba sin
    dueño -- y un caso sin dueño no lo ve el equipo, solo un administrador.
    Preferir eso a elegir a dedo era un piso razonable, pero deja trabajo
    huerfano.

    Ahora reparte (ver nucleo/seguimiento/reparto.py): equilibra solo y sigue
    la disponibilidad sin contador aparte. Si no se puede leer la carga, el
    reparto degrada a un orden estable en vez de fallar: peor que repartir
    parejo es no asignar.
    """
    if not area:
        return None
    try:
        areas = persistencia.areas_de_colaboradores(tenant)
    except Exception as e:
        print(f"[escalamiento] no se pudo resolver quien atiende '{area}': "
              f"{type(e).__name__}: {e}")
        return None
    perfiles = [p for p, a in areas.items() if a == area]
    if not perfiles:
        print(f"[escalamiento] el area '{area}' no tiene a nadie: el caso queda "
              f"sin asignar, a la vista del administrador")
        return None
    if len(perfiles) == 1:
        return perfiles[0]

    carga = _carga_de_casos(config, tenant) if config is not None else {}
    elegido = reparto.elegir_menos_cargado(perfiles, carga)
    print(f"[escalamiento] el area '{area}' tiene {len(perfiles)} personas; "
          f"le toca a {elegido} (abiertos: "
          f"{ {p: carga.get(p, 0) for p in perfiles} })")
    return elegido


def _carga_de_casos(config, tenant: str) -> dict[str, int]:
    """
    Cuantos casos ABIERTOS tiene cada persona, preguntandole al CRM con la
    herramienta que el tenant ya declaro para leer casos.

    Best-effort: ante cualquier fallo devuelve vacio, y entonces el reparto
    cae en el orden estable. No se deja de asignar por no poder contar.
    """
    herramienta = next((h for h in config.herramientas
                        if h.nombre == NOMBRE_HERRAMIENTA_CASOS), None)
    if herramienta is None:
        return {}
    try:
        # Sin filtro de estado: se traen todos y se descartan los cerrados
        # aca. Filtrar por "abierto" en la API dejaba afuera lo que la persona
        # tiene EN ESPERA, y eso tambien la ocupa -- quien tiene ocho casos sin
        # empezar figuraba tan libre como quien no tiene ninguno.
        crudo = _ejecutar_tool(herramienta, None, {}, tenant,
                               config.variables_tenant)
    except Exception as e:
        print(f"[escalamiento] no se pudo leer la carga de casos: "
              f"{type(e).__name__}: {e}")
        return {}
    filas = crudo.get("cases") if isinstance(crudo, dict) else crudo
    if filas is None and isinstance(crudo, dict):
        filas = crudo.get("results")
    cerrados = {e.lower() for e in (config.escalamiento.estados_cerrados or [])}
    abiertos = [f for f in (filas or [])
                if isinstance(f, dict)
                and str(f.get("status") or "").lower() not in cerrados]
    return reparto.contar_por_responsable(abiertos, "assigned_to")


def responsable_de(tenant: str, area: str, sistema: str,
                   carga_externa: dict[str, int] | None = None) -> tuple[str, str] | None:
    """
    A nombre de quien se abre el trabajo de un area: (identificador, nombre)
    en el sistema externo.

    Devuelve None -- y entonces se usa el asignado fijo de la herramienta --
    en dos casos, y los dos a proposito:

      nadie      el area no tiene gente con identidad en ese sistema. El
                 ticket sale igual, a nombre del fijo: dejar de abrirlo seria
                 perder el trabajo por un dato de configuracion.
      varios     dos o mas personas del area podrian recibirlo y no hay forma
                 de elegir sin inventar una regla. Se avisa por log en vez de
                 tomar una al azar: un ticket asignado arbitrariamente parece
                 correcto y no lo es.

    El dia que un area tenga varias personas hara falta declarar cual es la
    responsable. Hasta entonces esto no adivina.
    """
    try:
        areas = persistencia.areas_de_colaboradores(tenant)
        identidades = persistencia.identidades_externas(tenant, sistema)
    except Exception as e:
        print(f"[agendamiento] no se pudo resolver el responsable de '{area}': "
              f"{type(e).__name__}: {e}")
        return None

    candidatos = [
        (identidades[p]["identificador"], identidades[p].get("nombre_visible") or "")
        for p, a in areas.items()
        if a == area and p in identidades and identidades[p].get("identificador")
    ]
    if not candidatos:
        print(f"[agendamiento] el area '{area}' no tiene a nadie con identidad "
              f"en '{sistema}': el ticket va al asignado fijo")
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    # Varios: le toca al que menos tiene abierto. Ver reparto.py -- mismo
    # criterio que para el caso del CRM, y por los mismos motivos.
    por_id = {c[0]: c for c in candidatos}
    elegido = reparto.elegir_menos_cargado(list(por_id), carga_externa or {})
    print(f"[agendamiento] el area '{area}' tiene {len(candidatos)} personas; "
          f"el ticket le toca a {por_id[elegido][1] or elegido}")
    return por_id[elegido]


def agendar(config, tenant: str, sesion, nombre_herramienta: str,
           descripcion: str, area: str = "", asunto: str = "",
           prioridad: str = "") -> str | None:
    """
    Ejecuta la herramienta de agendamiento DIRECTO, en codigo -- nunca via
    tool-calling del modelo (el especialista que atiende al cliente ni
    siquiera tiene esta herramienta en su catalogo). El modelo ya opino (en
    verificar()) que corresponde; esto es la segunda capa que arma los
    argumentos reales y confirma que no falta nada antes de escribir contra
    WispHub.

    Devuelve el id del ticket creado, o None si no se pudo -- nunca lanza:
    un fallo aca tiene que caer al camino humano, no romper el turno.
    """
    herramienta = next((h for h in config.herramientas if h.nombre == nombre_herramienta), None)
    if herramienta is None:
        print(f"[agendamiento] '{nombre_herramienta}' no esta configurada "
              f"para '{tenant}', no se agenda.")
        return None

    servicio = getattr(sesion, "id_cliente", None) if sesion is not None else None
    descripcion = (descripcion or "").strip()
    if not servicio or not descripcion:
        print(f"[agendamiento] faltan datos minimos (servicio={bool(servicio)}, "
              f"descripcion={bool(descripcion)}), no se agenda.")
        return None

    try:
        # A nombre de quien. Solo si el tenant declaro un sistema externo y
        # este ticket dijo de que area es.
        sobrescribir = {}
        cfg = getattr(config, "identidad_externa", None)
        if area and cfg:
            quien = responsable_de(tenant, area, cfg.sistema)
            if quien:
                sobrescribir["tecnico"] = quien[0]
                print(f"[agendamiento] el ticket se abre a nombre de "
                      f"{quien[1] or quien[0]} (area '{area}')")
        # 'asuntos_default' viaja junto a 'asunto': WispHub exige los dos y
        # los valida contra la misma lista. Mandar uno solo da 400.
        if asunto:
            sobrescribir["asunto"] = asunto
            sobrescribir["asuntos_default"] = asunto
        if prioridad:
            sobrescribir["prioridad"] = prioridad

        respuesta = _ejecutar_tool(
            herramienta, sesion, {"servicio": servicio, "descripcion": descripcion},
            tenant, sobrescribir=sobrescribir)
        # 'id_ticket', no 'id' -- _ejecutar_tool devuelve la respuesta CRUDA
        # de WispHub (sin pasar por listas_blancas.filtrar_campos, que no
        # renombra nada), y el campo real del ticket es 'id_ticket' (ver
        # campos_permitidos.agendar_visita_tecnica en el config del tenant).
        return respuesta.get("id_ticket") if isinstance(respuesta, dict) else None
    except Exception as e:
        print(f"[agendamiento] fallo al ejecutar '{nombre_herramienta}': "
              f"{type(e).__name__}: {e}")
        return None
