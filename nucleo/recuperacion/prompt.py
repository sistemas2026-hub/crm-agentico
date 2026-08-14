# -*- coding: utf-8 -*-
"""
================================================================================
 CONSTRUCCION DEL SYSTEM PROMPT  -  por config, no por diccionario hardcodeado
================================================================================

Equivalente generico de construir_system(area) en soporte_wisphub.py, pero
armado desde 'Persona'/'Identidad'/'Rol' (nucleo/config/schema.py) en vez de
un diccionario Python por nombre de area. La diferencia que importa: la base
del prototipo original asume "quien te escribe es SIEMPRE un colaborador,
NUNCA el cliente final" -- lo contrario de lo que necesita un rol
'cliente_final'. Esa bifurcacion la decide 'Rol.orientado_a', no un nombre de
rol hardcodeado (eso violaria la regla de nucleo/tenants).

La verificacion de identidad se recuerda en el prompt como defensa en
profundidad, pero la garantia real la aplica el motor en codigo
(nucleo/seguridad/verificacion.py) ANTES de ejecutar una herramienta -- el
prompt no es lo unico que la exige.
================================================================================
"""

from __future__ import annotations

# De donde sale cada pieza. Texto para una PERSONA (a que pantalla ir), no
# una ruta que el codigo resuelva.
AJUSTES = "Ajustes -> Personalidad del asistente"
ORIGEN_CODIGO = "fijo en el codigo, no se edita"
GEN = "se genera segun 'orientado_a' del agente"


_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _hoy_en(zona: str) -> str:
    """
    Que dia es hoy, en la zona horaria del tenant.

    NO ES UN ADORNO. Sin esto el modelo no puede comparar una fecha contra el
    presente, y eso lo lleva a inventar. Visto en produccion (14/08/2026): a
    una clienta con una factura pendiente y fecha de corte el 20/08 le dijo
    que esa deuda "puede estar limitando tu servicio". Ella tuvo que
    corregirlo dos veces -- "hoy apenas es 13"-- y recien ahi acepto que
    tenia razon. Sabia razonarlo; le faltaba el dato.

    SOLO EL DIA, sin hora: el prompt se arma en cada turno, y si trajera la
    hora cambiaria cada minuto, rompiendo el cacheo de prefijo del proveedor
    en todas las llamadas (RNF-03). Con granularidad de dia, el prompt es
    identico durante toda la jornada. Lo que se pierde es responder "¿estan
    abiertos AHORA?"; para eso puede decir el horario y que la persona
    juzgue.

    Los nombres van escritos a mano y no por locale: un contenedor no suele
    traer el locale español instalado, y strftime devolveria 'Friday'.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ahora = datetime.now(ZoneInfo(zona))
    except (ZoneInfoNotFoundError, ValueError):
        # Zona mal escrita en la config: mejor la fecha del servidor que
        # ninguna. Sin esto el modelo vuelve a quedarse sin referencia.
        print(f"[prompt] zona horaria desconocida '{zona}', se usa la del servidor")
        ahora = datetime.now()

    return (f"Hoy es {_DIAS[ahora.weekday()]} {ahora.day} de "
            f"{_MESES[ahora.month - 1]} de {ahora.year}. Usalo para cualquier "
            f"cuenta con fechas -- si una fecha de corte, de vencimiento o de "
            f"cita todavia no llego, NO hables de ella como si ya hubiera "
            f"pasado.")


def construir_system(config, nombre_rol: str) -> str:
    """El system prompt completo, tal cual lo recibe el modelo."""
    return "\n\n".join(p["texto"] for p in piezas_del_system(config, nombre_rol))


def piezas_del_system(config, nombre_rol: str) -> list[dict]:
    """
    Las mismas partes que construir_system(), pero cada una con su titulo y
    DONDE se edita. Es lo que le permite a la pantalla de agentes contestar
    "por que dijo eso" sin que nadie tenga que reconstruir el prompt de
    memoria cruzando cuatro secciones de la configuracion.

    Una sola fuente a proposito: construir_system() se arma desde esto, no al
    reves ni en paralelo. Dos funciones que generan "el mismo" prompt divergen
    en el primer cambio, y el dia que diverjan la pantalla estaria mintiendo
    justo cuando alguien la consulta para depurar.

    'origen' es texto para una persona, no una ruta que el codigo resuelva:
    dice a que pantalla ir. 'editable' distingue lo que se cambia desde la
    plataforma de lo que esta fijo en codigo o se genera solo -- un bloque
    generado (a quien le habla el agente) no tiene donde editarse porque no
    lo escribio nadie, y ese es justamente el punto.
    """
    rol = config.roles[nombre_rol]
    persona = config.persona
    identidad = config.identidad

    piezas: list[dict] = []

    def agregar(titulo: str, origen: str, texto: str, editable: bool = True):
        if texto and texto.strip():
            piezas.append({"titulo": titulo, "origen": origen,
                           "texto": texto, "editable": editable})

    agregar(
        "Identidad y tono", AJUSTES,
        f"Eres {persona.nombre_asistente}, el asistente de "
        f"{identidad.nombre_comercial or identidad.nombre_legal}, un "
        f"proveedor de internet (ISP). Respondes en {identidad.idioma}, con "
        f"tono {persona.tono} y respuestas {persona.longitud_respuesta}s.")

    agregar(
        "No inventar", ORIGEN_CODIGO,
        "No inventes datos: si una herramienta no te da un dato, decilo "
        "explicitamente en vez de completarlo. Tampoco inventes un "
        "procedimiento, un paso a seguir, ni el nombre de una herramienta "
        "que no tenes en tu lista -- tu unica fuente de procedimientos es "
        "lo que te llega en este prompt (guias del corpus, tus "
        "herramientas reales), nunca tu propio criterio de que 'suena "
        "razonable'. Esto vale incluso para un servicio real de la "
        "empresa: si no tenes una guia cargada para ese caso puntual, no "
        "improvises pasos -- decilo ('no tengo el procedimiento para esto "
        "todavia') y ofrece pasar el caso a un colaborador humano. Y si "
        "preguntan por algo que la empresa directamente no ofrece, decilo "
        "con la misma honestidad ('ese servicio no lo ofrecemos') en vez "
        "de fabricar una respuesta o simular que consultaste algo que no "
        "existe.", editable=False)

    # Contexto de negocio SIEMPRE presente (a diferencia del corpus, que solo
    # se trae si la pregunta matchea por RAG): que servicios y planes existen
    # de verdad. Sin esto el modelo no tiene forma de saber si un servicio que
    # preguntan (ej. TV) existe o no, y improvisa en cualquier direccion.
    agregar("Que ofrece la empresa", AJUSTES,
            f"Que ofrece la empresa: {identidad.descripcion}"
            if identidad.descripcion else "")

    # Esta pieza NO la escribe nadie: la decide 'orientado_a'. Es lo que
    # impide que alguien cree un agente de cara al cliente y se olvide de
    # decirle que quien escribe es un desconocido hasta verificarse.
    if rol.orientado_a == "cliente_final":
        agregar(
            "A quien le hablas", GEN,
            "Quien te escribe es el CLIENTE FINAL, en segunda persona, por "
            "un canal como WhatsApp -- no un colaborador interno. Es un "
            "desconocido hasta que su identidad quede verificada por el "
            "sistema (no por vos): no muestres ningun dato de cuenta antes "
            f"de que el codigo confirme la verificacion. Al inicio de la "
            f"conversacion, saluda presentandote por tu nombre ({persona.nombre_asistente}) "
            f"de forma natural y cercana, como lo haria una persona real del "
            f"equipo de atencion -- nunca digas que sos un bot, un asistente "
            f"automatizado, ni uses frases con sonido de guion o de robot.\n"
            "VERIFICACION PRIMERO, SIEMPRE: apenas el cliente cuenta cual es "
            "su problema, tu SIGUIENTE mensaje tiene que pedir la "
            "verificacion de identidad (ej. numero de cedula, con la "
            "herramienta correspondiente) -- ANTES de hacer cualquier "
            "pregunta de diagnostico (cuantos televisores tiene, si las "
            "luces del equipo estan normales, etc.), aunque esas preguntas "
            "en si no muestren ningun dato de la cuenta. No arranques el "
            "diagnostico y despues pidas la cedula: el orden es verificar, "
            "y RECIEN AHI seguir con el problema. Unica excepcion: si el "
            "canal ya la trae verificada de antes (ver el punto de abajo), "
            "no hace falta volver a pedirla.\n"
            "Como saber si YA esta verificado: hay dos senales, y "
            "cualquiera de las dos alcanza por si sola, no hace falta "
            "esperar a la otra. (1) Si confirmar_identidad te devuelve "
            "verificado:true, la sesion QUEDO VERIFICADA en ese mismo "
            "momento -- no existe ninguna otra herramienta ni ningun otro "
            "paso que 'cierre' la verificacion, y podes seguir de "
            "inmediato con el problema del cliente en ese mismo mensaje. "
            "(2) Si el resultado de CUALQUIER OTRA herramienta trae datos "
            "reales (no un mensaje de error pidiendo identidad), es porque "
            "el codigo ya verifico antes de ejecutarla -- en ese caso "
            "mostra esos datos directo. En ninguno de los dos casos "
            "vuelvas a pedir verificacion de nuevo, ni digas que falta un "
            "paso o que el canal no lo permite.\n"
            "Nunca uses formato markdown (nada de **negrita**, _cursiva_, "
            "ni # titulos): este canal no lo renderiza, y quedan simbolos "
            "sueltos a la vista en vez de texto resaltado. Escribi en texto "
            "plano; si hace falta estructurar pasos, usa una lista numerada "
            "simple (1. 2. 3.) en lineas separadas, nunca asteriscos.",
            editable=False)
    else:
        agregar(
            "A quien le hablas", GEN,
            "Quien te escribe es SIEMPRE un colaborador de la empresa, "
            "nunca el cliente final. Habla del cliente en tercera persona; "
            "no lo saludes a el, saluda a quien te escribe.", editable=False)

    agregar("Tu rol especifico", "este mismo agente",
            f"Tu rol especifico: {rol.descripcion}" if rol.descripcion else "")

    agregar("Instrucciones adicionales", AJUSTES,
            persona.instrucciones_adicionales)

    agregar("Reglas absolutas",
            "configuracion del tenant (seguridad.reglas_absolutas)",
            "Reglas que no podes romper bajo ninguna circunstancia:\n- "
            + "\n- ".join(config.seguridad.reglas_absolutas)
            if config.seguridad.reglas_absolutas else "")

    # ULTIMA a proposito, ver _hoy_en(). Es la unica pieza que cambia con el
    # tiempo: dejandola al final, todo lo de arriba es un prefijo identico
    # entre turnos y el proveedor lo puede cachear.
    agregar("Fecha de hoy", GEN, _hoy_en(identidad.zona_horaria), editable=False)

    return piezas
