# -*- coding: utf-8 -*-
"""
================================================================================
 ESCALAMIENTO -- pasar una conversacion a un humano
================================================================================

'escalamiento.activar_si' (nucleo/config/schema.py) existia en la
configuracion desde antes de este modulo, pero nada lo ejecutaba: ninguna
conversacion se marcaba escalada_a_humano. Sus valores por defecto
(frustracion_detectada, tres_fallos_seguidos, solicitud_explicita,
duda_de_identidad) son condiciones SEMANTICAS, no palabras clave -- por eso
quien las evalua es el modelo, no una comparacion de texto por codigo.

Una sola llamada al modelo por turno hace las cuatro cosas (evaluar() abajo):
si corresponde escalar, que etiqueta de conversaciones.etiquetas describe el
tema, si la conversacion ya llego a su fin (el cliente se despidio o
confirmo que su problema se resolvio) -- api.py usa esto ultimo para cerrar
la conversacion en la bandeja -- y un resumen corto del caso para cuando
escala. Se combinan para no duplicar el costo de una llamada aparte por
cada una.

El resumen va PRIMERO en la descripcion del ticket, antes de la
transcripcion completa (ver escalar()): quien toma el caso en BottleCRM lo
lee de entrada, sin tener que leer toda la conversacion para entender de
que se trata -- eso es lo que hacia perder tiempo antes.

Al escalar (escalar()), se crea el ticket real en BottleCRM via su API REST
(nucleo/herramientas/http.py:ejecutar(), el mismo ejecutor generico que ya
usan las herramientas de WispHub -- sin cliente HTTP nuevo) y se guarda el
resultado en asistente.conversations (nucleo/persistencia/db.py).

Generico a proposito: no sabe que tenant es, ni que "rapilink" existe --
todo lo que necesita (condiciones, taxonomia, credenciales del CRM) viene
de la config que le pasan.
================================================================================
"""

from __future__ import annotations

import json

from nucleo.herramientas import http as herramientas_http
from nucleo.modelo import cliente
from nucleo.persistencia import db as persistencia
from nucleo.seguimiento import forzado
from nucleo.seguimiento.nombres import nombre_del_caso

NOMBRE_HERRAMIENTA_TAGS_LISTAR = "listar_tags_crm"
NOMBRE_HERRAMIENTA_TAGS_CREAR = "crear_tag_crm"
NOMBRE_HERRAMIENTA_CASO_CREAR = "crear_caso_soporte"


def _herramienta(config, nombre: str):
    return next((h for h in config.herramientas if h.nombre == nombre), None)


def _cuando_escalar(config) -> str:
    """
    Que se le dice al evaluador sobre cuando poner escalar=true.

    La frase extra solo aparece si el tenant tiene motivos que decide un
    hecho (una herramienta que recoge un pedido). Sin ellos seria ruido, y
    peor: le hablaria de un camino que en ese tenant no existe.

    Nace de una falla del 28/08/2026. Un cliente escribio TODO en un solo
    mensaje -- nombre, cedula, clave vieja y clave nueva -- y el evaluador
    escalo en ese mismo turno, con la traza vacia: sin verificar identidad,
    sin tomar el pedido y sin ticket. El caso llego a la bandeja con una sola
    linea de conversacion, y al cliente le llego "entiendo tu molestia" a un
    mensaje donde no se habia quejado de nada.

    El error de fondo es de categoria: leyo un TRAMITE como un pedido de
    hablar con una persona. Son cosas distintas y hay que decirselo, porque
    el motivo que si le correspondia no esta en su menu a proposito (lo
    dispara el hecho, no el juicio -- ver forzado.motivos_por_hecho).
    """
    base = "true si corresponde escalar a un humano ahora mismo."
    if not forzado.motivos_por_hecho(config):
        return base
    return (base + " NO pongas true porque el cliente pida un tramite que al "
            "final aplica una persona: mientras el asistente esta juntando "
            "los datos de ese pedido, la conversacion NO necesita a nadie, y "
            "cuando el pedido queda tomado la escalada se dispara sola, con "
            "su propio motivo. Pedir un cambio NO es pedir hablar con "
            "alguien. Ponelo en true solo por algo que el asistente no puede "
            "resolver ni recoger.")


def _motivos_a_juicio(config, rol_cfg=None) -> list[str]:
    """Los motivos que el evaluador SI puede elegir leyendo la conversacion.

    Dos filtros sobre el mismo menu, por dos razones distintas:

      * Los que decide un HECHO se sacan siempre (forzado.motivos_por_hecho):
        mirando el texto no se pueden saber.
      * Los que NO SON DE ESTE ROL se sacan si el rol lo declara
        ('Rol.motivos_escalada'). El evaluador ve el mismo menu en cada turno,
        y si un motivo esta ahi lo va a elegir en cuanto la conversacion se le
        parezca -- aunque no tenga sentido para quien esta hablando.

    El segundo filtro nace de un caso real (28/08/2026). Un prospecto escribio
    "hola / quiero instalar / barrio centro". 'consultar_planes_venta' corrio
    bien y encontro cobertura, o sea que la respuesta de venta ya estaba
    lista -- y el evaluador escalo con 'sin_datos_para_diagnosticar', un
    motivo de soporte tecnico que en una venta no significa nada. Como la
    escalada REEMPLAZA la respuesta, el cliente nunca leyo que habia cobertura
    ni cuales eran los planes: leyo "entiendo tu molestia", sin haberse
    quejado de nada.
    """
    por_hecho = forzado.motivos_por_hecho(config)
    del_rol = set(getattr(rol_cfg, "motivos_escalada", None) or [])
    return [m for m in config.escalamiento.activar_si
            if m not in por_hecho and (not del_rol or m in del_rol)]


def _esquema_evaluacion(config, rol_cfg=None) -> dict:
    propiedades = {
        "escalar": {
            "type": "boolean",
            "description": _cuando_escalar(config),
        },
        "motivo": {
            "type": "string",
            # Los motivos que decide un HECHO se le sacan del menu: si los ve,
            # los elige en cuanto la conversacion suene a eso, que es antes de
            # que el hecho ocurra (ver forzado.motivos_por_hecho y el caso que
            # lo motivo). Siguen en 'activar_si' porque son parte del
            # vocabulario del tenant; lo que cambia es quien los puede elegir.
            #
            # Si un tenant declarara TODOS sus motivos por hecho, dejarlo sin
            # opciones haria invalido el esquema entero -- ahi vale mas un
            # evaluador impreciso que un evaluador roto.
            "enum": (_motivos_a_juicio(config, rol_cfg)
                     or list(config.escalamiento.activar_si)),
            "description": "Por que escala. Ignoralo si escalar=false.",
        },
        "etiqueta": {
            "type": "string",
            "enum": list(config.conversaciones.etiquetas),
            "description": "De que trata la conversacion, de esta lista.",
        },
        # Distinto de 'resuelta', y la diferencia costo un cierre indebido:
        # 'resuelta' mide "esto PARECE terminado" y se pone en true tambien
        # cuando el cliente se despide o cuando el asistente acaba de
        # contestarle bien. Esta mide una sola cosa, y es un hecho: si el
        # ultimo mensaje del cliente le dice que si a la pregunta de cerrar.
        #
        # Visto el 28/08/2026: se le pregunto "¿te queda algo pendiente?", el
        # cliente contesto "espera, tambien queria saber si tengo factura
        # pendiente" -- o sea que NO-- y la conversacion se cerro igual,
        # porque el asistente le respondio bien y todo volvio a "parecer
        # resuelto".
        "confirma_cierre": {
            "type": "boolean",
            "description": "true SOLO si el ultimo mensaje del cliente "
                "responde que SI a la pregunta de si se puede cerrar su "
                "caso ('si', 'dale', 'ya esta', 'nada mas'). false si "
                "trae cualquier otra cosa: una pregunta nueva, un tema "
                "distinto, o un pedido pendiente. Ante la duda, false.",
        },
        "resuelta": {
            "type": "boolean",
            "description": "true si el cliente confirmo que su "
                "problema ya se resolvio o se esta despidiendo "
                "(gracias, listo, ya quedo, chau) y la "
                "conversacion no necesita seguir abierta. false "
                "en cualquier otro caso, incluido mientras el "
                "problema sigue sin resolver.",
        },
        "resumen": {
            "type": "string",
            "description": "2-3 frases resumiendo el caso para "
                "quien lo va a atender: que reporto el cliente, "
                "que ya se probo/descarto, y en que quedo "
                "pendiente. Ignoralo si escalar=false. Va antes "
                "de la transcripcion completa en el ticket, asi "
                "que tiene que alcanzar por si solo, sin tener "
                "que leer el resto para entenderlo.",
        },
        # Los dos campos que convierten el traspaso en un relevo y no en un
        # "aca te dejo esto". La traza ya dice QUE se midio y con que
        # resultado (ver _que_se_probo), pero no dice lo unico que quien
        # toma el caso no puede deducir sin volver a hacerlo todo: hasta
        # donde llego el diagnostico y por que se detuvo ahi.
        #
        # Opcionales a proposito: el evaluador corre en CADA turno y la
        # mayoria no escala. Exigirlos siempre seria pagar dos campos de
        # redaccion por turno para tirarlos.
        "no_se_pudo_comprobar": {
            "type": "string",
            "description": "Solo si escalar=true. Que quedo SIN "
                "comprobar y por que: un dato que el cliente no "
                "supo dar, una herramienta que fallo, algo que "
                "no se puede medir desde los sistemas. Es lo "
                "primero que necesita quien retome, porque es "
                "justo donde tiene que empezar. Si se pudo "
                "comprobar todo, dilo asi.",
        },
        "siguiente_paso": {
            "type": "string",
            "description": "Solo si escalar=true. Que le queda "
                "por hacer a la persona que tome el caso, en una "
                "frase concreta. No repitas lo que el asistente "
                "ya hizo. Si la conclusion es que hace falta ir "
                "al domicilio, dilo; si falta una revision que "
                "solo se hace desde adentro, dilo.",
        },
        # Solo tiene sentido cuando el caso no encajo en ninguno de los del
        # manual. Es el lazo que hace que el catalogo mejore con el uso: el
        # asistente propone el nombre que le habria correspondido, y una
        # persona decide si vale la pena crearlo.
        #
        # Se pide un NOMBRE CORTO y no una explicacion porque va a terminar
        # siendo una categoria de verdad, y una categoria con una frase adentro
        # no sirve para agrupar nada.
        "asunto_sugerido": {
            "type": "string",
            "description": "Solo si escalar=true Y el caso quedo como "
                "'otro'. Que nombre de categoria le habria "
                "correspondido a este caso, corto y en el estilo de "
                "un catalogo (ej. 'Traslado De Domicilio', "
                "'Consulta De Cobertura'). Si no sabes, dejalo "
                "vacio -- inventar una categoria es peor que no "
                "proponer ninguna.",
        },
        "necesita_humano": {
            "type": "boolean",
            "description": "Solo si escalar=true. true si hace "
                "falta que una persona del equipo atienda esto "
                "AHORA (el cliente sigue esperando una "
                "respuesta puntual). false si el caso ya quedo "
                "resuelto por otra via o registrado para "
                "seguimiento y no necesita que nadie entre de "
                "inmediato. Depende del caso, no hay una regla "
                "fija.",
        },
    }

    # Solo se ofrece si hay algun caso declarado -- un enum vacio no es un
    # valor valido de JSON Schema para ningun proveedor, y sin casos no hay
    # nada para el modelo que elegir.
    #
    # Obligatorio, con 'otro' como salida segura -- mismo criterio que
    # 'etiqueta'. La primera version lo dejaba opcional con una redaccion
    # cautelosa ("solo si encaja con claridad, no adivines"): en pruebas en
    # vivo (agosto 2026), con el contexto real de la conversacion (prompt +
    # RAG + varios turnos), el modelo casi nunca lo completaba -- pero en
    # una prueba aislada, con el mismo texto, si lo hacia bien. La cautela
    # de la redaccion lo volvia demasiado facil de saltear. 'etiqueta', con
    # la misma forma (enum + obligatorio) pero redactada como categorizacion
    # de rutina, si se completaba siempre.
    if config.manual.casos:
        propiedades["caso_manual"] = {
            "type": "string",
            "enum": list(config.manual.casos),
            "description": "A cual de estos casos del manual corresponde "
                "esta conversacion. Usa 'otro' si ninguno encaja bien -- "
                "pero elige siempre uno, no lo dejes vacio. Un "
                "verificador aparte lo usa para saber si este caso "
                "puntual tiene agendamiento automatico de visita "
                "tecnica habilitado, sin pasar por un humano.",
        }
        requeridos = ["escalar", "etiqueta", "resuelta", "caso_manual"]
    else:
        requeridos = ["escalar", "etiqueta", "resuelta"]

    return {
        "type": "function",
        "function": {
            "name": "evaluar_conversacion",
            "description": (
                "Evalua si esta conversacion necesita pasar a un humano AHORA, "
                "y que tema la describe mejor."
            ),
            "parameters": {
                "type": "object",
                "properties": propiedades,
                "required": requeridos,
            },
        },
    }


def evaluar(config, rol: str, historial: list[dict]) -> dict | None:
    """
    Le pregunta al modelo si esta conversacion necesita un humano ahora, que
    etiqueta le corresponde, si ya llego a su fin, y (si escala) un resumen
    corto del caso. Nunca elige algo fuera de escalamiento.activar_si /
    conversaciones.etiquetas -- el esquema se lo impide (enum).

    Usa el mismo modelo que ya esta respondiendole a este rol
    (llm.overrides['rol:<rol>'], igual que motor.py) en vez de
    modelo_por_defecto: ese campo es el respaldo local (qwen3, ~18GB) que
    ningun rol usa en la practica porque los 5 estan redirigidos a DeepSeek
    -- usarlo aca habria fallado con 'model not found' en cualquier
    instalacion que no tenga ese modelo bajado.

    Devuelve None si no hay nada configurado para evaluar contra, o si el
    modelo no llamo la funcion en este turno (se reintenta en el proximo,
    no es un fallo: el modelo puede simplemente no haber tenido motivo).

    Corre con TIMEOUT_SECUNDARIO y no con el generoso por defecto: esta
    llamada ocurre DESPUES de que la respuesta del cliente ya se calculo y
    se guardo, pero ANTES de devolverle el HTTP (ver atender_turno en
    nucleo/canales/api.py). Sin acotarla, una demora del proveedor deja al
    cliente mirando un "fetch failed" por una respuesta que ya existia --
    paso en produccion el 21/08/2026. Si se agota, se abandona esta vuelta
    y se reintenta en el turno siguiente, que es exactamente lo que ya
    hacia el caso "el modelo no llamo la funcion".
    """
    if not config.escalamiento.activar_si or not config.conversaciones.etiquetas:
        return None

    referencia_modelo = config.llm.overrides.get(f"rol:{rol}", config.llm.modelo_por_defecto)
    mensajes = historial + [{
        "role": "user",
        "content": (
            "(Instruccion del sistema, no del cliente) Evalua la conversacion "
            "de arriba llamando a evaluar_conversacion. No respondas con texto."
        ),
    }]
    try:
        respuesta = cliente.chat(
            referencia_modelo, mensajes,
            tools=[_esquema_evaluacion(config, config.roles.get(rol))],
            timeout=cliente.TIMEOUT_SECUNDARIO)
    except Exception as e:
        # SE PROPAGA, no se devuelve None. Un fallo del evaluador y una
        # decision de "no escalar" son cosas distintas, y colapsarlas en el
        # mismo valor fue exactamente el bug del 02/09/2026: el turno siguio
        # como si el evaluador hubiera dicho que no, y el modelo le prometio
        # al cliente un colaborador que nadie registro. Quien llama decide que
        # hacer con el fallo -- api.py ya lo captura.
        print(f"[escalamiento] fallo al evaluar: {type(e).__name__}: {e}")
        raise

    for llamada in respuesta.llamadas:
        if llamada.nombre == "evaluar_conversacion":
            return llamada.argumentos
    return None


def merece_un_intento(config, motivo: str, ya_se_intento: bool) -> bool:
    """
    True si esta escalada se pospone una vuelta para que el asistente intente
    resolverlo el mismo.

    El criterio es del TENANT ('escalamiento.intentar_resolver_antes', ver
    nucleo/config/schema.py), no del codigo: aca solo se aplica. Y se aplica
    UNA sola vez -- 'ya_se_intento' es la memoria de que esta conversacion ya
    tuvo su oportunidad, y con eso puesto siempre devuelve False.

    Ese techo no es un detalle: sin el, un cliente que sigue enojado y al que
    nunca se le pudo resolver nada quedaria dando vueltas con el bot para
    siempre, que es exactamente lo que la escalada existe para evitar. Un
    agente que insiste con alguien que ya explotó dos veces empeora las cosas.

    Que se pospone y que no lo decide el motivo, no la intensidad: un cliente
    que PIDE hablar con una persona ('solicitud_explicita') nunca deberia
    estar en esta lista, por mas calmado que suene.
    """
    if ya_se_intento or not motivo:
        return False
    return motivo in (config.escalamiento.intentar_resolver_antes or [])


def _resolver_tag(config, nombre_tag: str) -> str | None:
    """
    id de la etiqueta en BottleCRM, creandola si hace falta.

    Verificado en vivo (agosto 2026): a diferencia de otras pantallas del
    CRM (que resuelven una etiqueta por nombre solas via get_or_create_tags),
    POST /api/cases/ exige uuid en 'tags' y rechaza un nombre con
    'is not a valid UUID'. POST /api/tags/ si crea por nombre, pero rechaza
    un nombre duplicado con 400 -- por eso primero se busca en la lista
    existente y solo se crea si de verdad no esta.
    """
    listar = _herramienta(config, NOMBRE_HERRAMIENTA_TAGS_LISTAR)
    if not listar:
        return None
    existentes = herramientas_http.ejecutar(listar, {})
    for t in existentes:
        if isinstance(t, dict) and t.get("slug") == nombre_tag:
            return t.get("id")

    crear = _herramienta(config, NOMBRE_HERRAMIENTA_TAGS_CREAR)
    if not crear:
        return None
    creado = herramientas_http.ejecutar(crear, {"name": nombre_tag})
    return creado.get("id") if isinstance(creado, dict) else None


_ROL_LEGIBLE = {"user": "Cliente", "assistant": "Asistente"}


def _con_la_respuesta_real(historial: list[dict], respuesta: str) -> list[dict]:
    """
    El historial, con el ultimo turno del asistente cambiado por lo que el
    cliente de verdad recibio.

    Hace falta porque en un turno que termina en traspaso esas dos cosas NO
    son la misma: el modelo contesta primero, la escalada se evalua despues, y
    su texto REEMPLAZA al del modelo (ver api.py). El borrador del modelo no
    llega a ningun lado -- pero era el que viajaba al caso.

    Lo noto el usuario el 28/08/2026 comparando las dos pantallas: en el
    simulador el cliente leia "tu pedido quedo registrado" y en el ticket, ese
    mismo turno, el asistente le explicaba en que bandas se aplica el cambio y
    con que clave reconectar. Quien atienda el caso tiene que saber que le
    dijeron al cliente, no lo que se escribio y se tiro: contestar dando por
    hecho algo que el cliente nunca leyo es peor que no contestar.

    Sin respuesta que poner, se devuelve el historial tal cual.
    """
    if not (respuesta or "").strip():
        return historial
    copia = list(historial)
    for i in range(len(copia) - 1, -1, -1):
        if copia[i].get("role") == "assistant" and copia[i].get("content"):
            copia[i] = {**copia[i], "content": respuesta.strip()}
            break
    return copia


def _transcripcion_legible(historial: list[dict]) -> str:
    """
    Solo lo que de verdad se dijeron cliente y asistente -- para la
    descripcion del ticket que lee un humano. 'historial' trae mucho mas
    que eso (el prompt del sistema, el bloque de contexto del RAG con el
    manual completo, las respuestas crudas de las herramientas): pasarlo
    entero convertia la descripcion del caso en un volcado de la ingenieria
    de prompt en vez de un resumen legible del caso.
    """
    lineas = [
        f"{_ROL_LEGIBLE[m['role']]}: {m['content']}"
        for m in historial
        if m.get("role") in _ROL_LEGIBLE and m.get("content")
    ]
    return "\n".join(lineas)


# El codigo con el que motor.py frena una herramienta que se pidio antes de
# verificar la identidad. Mismo string que nucleo/seguridad/salida.py trata
# como plomeria interna que nunca debe llegarle al cliente.
_GATE_IDENTIDAD = "IDENTIDAD_NO_VERIFICADA"


def _que_se_probo(historial: list[dict]) -> str:
    """
    Lo que el asistente MIDIO y EJECUTO, en orden, sacado de la traza.

    Existe porque un resumen en prosa no le alcanza a quien tiene que
    resolver el caso: necesita saber que ya se probo, para no repetirselo al
    cliente, y con que resultado. Eso es dato duro -- vive en el historial de
    herramientas, no hay que pedirselo al modelo ni que la persona lo deduzca
    leyendo veinte mensajes.

    Generico a proposito: nombra la herramienta y si respondio o fallo, sin
    interpretar los campos. Cuales importan lo sabe el tenant, no el nucleo, y
    la transcripcion queda abajo para el detalle.
    """
    lineas = []
    for msg in historial:
        if msg.get("role") != "tool" or not msg.get("name"):
            continue
        try:
            dato = json.loads(msg.get("content") or "null")
        except (TypeError, ValueError):
            dato = None
        if isinstance(dato, dict) and dato.get("error") == _GATE_IDENTIDAD:
            # No se lista. No es un fallo: es el gate de seguridad frenando
            # ANTES de llamar a nada, y es normal que el modelo pruebe una
            # herramienta antes de tener con que verificar (motor.py lo
            # excluye por lo mismo de la traza que se guarda).
            #
            # Listarlo lo pintaba como una X roja al lado de la MISMA
            # herramienta que un renglon mas abajo aparece en verde, y quien
            # abre el caso se va a averiguar que fallo en un sistema donde no
            # fallo nada. Lo pregunto el usuario el 28/08/2026 mirando un
            # ticket real: "el consultar servicio que sale que no se pudo,
            # ¿cual es?".
            continue
        if isinstance(dato, dict) and dato.get("error"):
            # Un fallo importa tanto como un exito: dice que NO se pudo ver, y
            # quien retome no tiene que volver a intentarlo a ciegas.
            linea = "  - " + msg["name"] + ": no se pudo -- " + str(dato["error"])
        else:
            valor = json.dumps(dato, ensure_ascii=False) if dato is not None else ""
            linea = "  - " + msg["name"] + ": " + valor
        lineas.append(linea[:160])
    if not lineas:
        return ""
    vistas, unicas = set(), []
    for l in lineas:
        if l not in vistas:
            vistas.add(l)
            unicas.append(l)
    return "QUE YA SE PROBO (no hace falta repetirlo):" + chr(10) + chr(10).join(unicas) + chr(10) + chr(10)


def escalar(config, tenant: str, usuario_externo: str, conversation_id: str,
           historial: list[dict], motivo: str, etiqueta: str,
           resumen: str = "", necesita_humano: bool = True,
           no_se_pudo_comprobar: str = "", siguiente_paso: str = "",
           asignar_a: str = "", asunto: str = "", nombre_cliente: str = "",
           respuesta_al_cliente: str = "") -> bool:
    """
    Crea el ticket en BottleCRM y marca la conversacion como escalada.

    Devuelve si el caso quedo creado. Quien llama LO NECESITA: al cliente se
    le dice "tu caso ya quedo con un compañero", y esa frase tiene que ser
    cierta. Antes esta funcion devolvia None pasara lo que pasara y el aviso
    salia igual -- el 28/08/2026 un cliente pidio un cambio de clave de WiFi,
    el CRM rechazo el caso con un 400, y se le contesto que su pedido habia
    quedado registrado cuando no existia en ningun lado.

    Nunca rompe el turno: un fallo (CRM caido, token vencido, lo que sea) se
    loguea y devuelve False -- mismo criterio que ya usa registrar_mensaje. El
    proximo turno vuelve a intentar evaluar() porque la conversacion sigue
    sin caso_id.
    """
    herramienta_caso = _herramienta(config, NOMBRE_HERRAMIENTA_CASO_CREAR)
    if not herramienta_caso:
        print(f"[escalamiento] '{NOMBRE_HERRAMIENTA_CASO_CREAR}' no esta "
              f"configurada para '{tenant}', no se crea el ticket.")
        return False

    try:
        tag_id = _resolver_tag(config, etiqueta)
        transcripcion = _transcripcion_legible(
            _con_la_respuesta_real(historial, respuesta_al_cliente))

        # El resumen va PRIMERO y nunca se recorta (es corto por diseno,
        # 2-3 frases via el esquema de evaluar_conversacion). El limite de
        # 4000 caracteres de BottleCRM se le aplica a la TRANSCRIPCION, no
        # al conjunto -- si se cortara desde el final del texto combinado
        # (como se hacia antes), un resumen largo o una transcripcion corta
        # podian dejar el resumen mismo afuera.
        # Los adjuntos se nombran EN EL CASO, no solo en la transcripcion.
        # La transcripcion ya trae un "[El cliente envio una foto]" (lo unico
        # que ve el modelo), asi que quien lee el caso sabe que existe pero no
        # donde mirarla: los bytes viven en asistente.media, ligados a la
        # conversacion, y la unica pista era deducir que el id del nombre del
        # caso es esa conversacion. Cuando la foto es la prueba de que una
        # visita tecnica NO hace falta (el equipo estaba desenchufado), que se
        # pierda por no encontrarla cuesta un camion.
        nota_adjuntos = ""
        try:
            adjuntos = persistencia.media_de(tenant, conversation_id)
        except Exception as e:
            print(f"[escalamiento] no se pudieron leer los adjuntos: {e}")
            adjuntos = []
        if adjuntos:
            detalle = ", ".join(sorted({a["tipo"] for a in adjuntos}))
            nota_adjuntos = (
                f"ADJUNTOS: el cliente envio {len(adjuntos)} archivo(s) "
                f"({detalle}). Se ven en la bandeja de conversaciones, "
                f"abriendo esta misma conversacion ({conversation_id}). "
                f"Se conservan 30 dias.\n\n")

        encabezado = f"RESUMEN: {resumen.strip()}\n\n" if resumen.strip() else ""
        # Antes de la transcripcion: es lo primero que necesita quien toma
        # el caso, y le ahorra leerla entera para saber que ya se intento.
        encabezado += _que_se_probo(historial)
        # Y despues de los hechos, lo que los hechos NO dicen. El orden
        # importa: primero lo medido (dato duro, sale de la traza), despues
        # lo que quedo abierto (interpretacion del modelo). Al reves, quien
        # lee toma la interpretacion como si fuera una medicion.
        if no_se_pudo_comprobar.strip():
            encabezado += ("NO SE PUDO COMPROBAR (empezar por aca): "
                          + no_se_pudo_comprobar.strip() + chr(10) + chr(10))
        if siguiente_paso.strip():
            encabezado += ("SIGUIENTE PASO: " + siguiente_paso.strip()
                          + chr(10) + chr(10))
        encabezado += nota_adjuntos
        if encabezado:
            encabezado += f"{'-' * 40}\n\n"
        espacio_transcripcion = max(4000 - len(encabezado), 0)
        cuerpo = encabezado + transcripcion[-espacio_transcripcion:]

        payload = {
            # El nombre es lo UNICO que se ve en la cola antes de abrir el
            # caso, asi que tiene que decir de que se trata. Decia
            # "WhatsApp <numero> - <id>": el canal y un identificador, o sea
            # nada -- quien abria la cola tenia que entrar en cada uno para
            # saber cual atender primero.
            #
            # El id se conserva al final porque el nombre tiene que ser UNICO
            # por organizacion (verificado: uno repetido da 400) y dos clientes
            # bien pueden tener el mismo problema el mismo dia. La pantalla lo
            # separa con el mismo formato.
            "name": nombre_del_caso(asunto, nombre_cliente or usuario_externo,
                                    conversation_id),
            "description": cuerpo,
            "status": "New",
            "case_type": "Question",
            "priority": "Normal",
        }
        if tag_id:
            payload["tags"] = [tag_id]
        # A quien se le asigna. NO es cosmetico: el CRM le muestra a quien no
        # es administrador solo los casos que creo, tiene asignados o sigue.
        # Un caso sin dueño no queda "para todos" -- queda invisible para el
        # equipo y visible solo para un admin.
        if asignar_a:
            payload["assigned_to"] = [asignar_a]

        respuesta = herramientas_http.ejecutar(herramienta_caso, payload)
        caso_id = respuesta.get("id") if isinstance(respuesta, dict) else None

        # Se marca aunque el CRM no haya devuelto id: la conversacion igual
        # aparece escalada en la bandeja, y sin esto el proximo mensaje del
        # cliente vuelve a escalar y duplica el ticket de la operacion.
        persistencia.marcar_escalada(tenant, conversation_id, motivo, caso_id,
                                     etiqueta, necesita_humano)
        if not caso_id:
            print(f"[escalamiento] el CRM acepto el caso de {conversation_id} "
                  f"pero no devolvio id -- no queda en la cola de nadie")
        return bool(caso_id)
    except Exception as e:
        print(f"[escalamiento] fallo al escalar la conversacion "
              f"{conversation_id}: {type(e).__name__}: {e}")
        return False


# Estados en los que BottleCRM considera un caso terminado. 'Closed' es el
# unico que cases/signals.py trata como resuelto (RESOLVED_STATUSES); los
# demas siguen siendo trabajo abierto.
ESTADOS_CERRADOS = ("Closed", "Rejected", "Duplicate")


def caso_sigue_abierto(config, caso_id: str) -> bool:
    """
    Un GET al caso del CRM para saber si el humano ya lo resolvio.

    Existe para que el bot pueda PAUSARSE de verdad: sin esto, despues de
    escalar el asistente le sigue contestando al cliente al que se le acaba de
    decir que lo iba a atender una persona. El prompt puede pedirle que no lo
    haga, pero eso es guia y no garantia (PRD 7.4) -- la misma razon por la
    que el filtro de campos y la confirmacion de acciones sensibles viven en
    codigo.

    FAIL-SAFE: cualquier error de red, credencial o forma de la respuesta se
    interpreta como "sigue abierto". Nunca se asume resuelto sin confirmarlo:
    equivocarse hacia el lado de la pausa deja a un cliente esperando a una
    persona que ya viene; hacia el otro, lo deja hablando con un bot que le
    dijeron que no lo iba a atender.
    """
    if not caso_id:
        return False

    herramienta = _herramienta(config, NOMBRE_HERRAMIENTA_CASO_CREAR)
    if herramienta is None:
        return True

    try:
        import requests

        url = f"{herramienta.base_url.rstrip('/')}{herramienta.endpoint}{caso_id}/"
        r = requests.get(url, timeout=10,
                         headers=herramientas_http.headers_de(
                             herramienta, config.identidad.slug))
        r.raise_for_status()
        cuerpo = r.json()
        caso = cuerpo.get("cases_obj", cuerpo) if isinstance(cuerpo, dict) else {}
        return caso.get("status") not in ESTADOS_CERRADOS
    except Exception as e:
        print(f"[escalamiento] no se pudo verificar el caso {caso_id}, "
              f"se mantiene pausado: {type(e).__name__}: {e}")
        return True
