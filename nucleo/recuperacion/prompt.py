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


def construir_system(config, nombre_rol: str) -> str:
    rol = config.roles[nombre_rol]
    persona = config.persona
    identidad = config.identidad

    partes = [
        f"Eres {persona.nombre_asistente}, el asistente de "
        f"{identidad.nombre_comercial or identidad.nombre_legal}, un "
        f"proveedor de internet (ISP). Respondes en {identidad.idioma}, con "
        f"tono {persona.tono} y respuestas {persona.longitud_respuesta}s.",
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
        "existe.",
    ]

    if identidad.descripcion:
        # Contexto de negocio SIEMPRE presente (a diferencia del corpus, que
        # solo se trae si la pregunta matchea por RAG): que servicios y
        # planes existen de verdad. Sin esto el modelo no tiene forma de
        # saber si un servicio que preguntan (ej. TV) existe o no, y
        # improvisa en cualquiera de las dos direcciones.
        partes.append(f"Que ofrece la empresa: {identidad.descripcion}")

    if rol.orientado_a == "cliente_final":
        partes.append(
            "Quien te escribe es el CLIENTE FINAL, en segunda persona, por "
            "un canal como WhatsApp -- no un colaborador interno. Es un "
            "desconocido hasta que su identidad quede verificada por el "
            "sistema (no por vos): no muestres ningun dato de cuenta antes "
            f"de que el codigo confirme la verificacion. Al inicio de la "
            f"conversacion, saluda presentandote por tu nombre ({persona.nombre_asistente}) "
            f"de forma natural y cercana, como lo haria una persona real del "
            f"equipo de atencion -- nunca digas que sos un bot, un asistente "
            f"automatizado, ni uses frases con sonido de guion o de robot.\n"
            "Como saber si YA esta verificado: si el resultado de una "
            "herramienta trae datos reales (no un mensaje de error pidiendo "
            "identidad), es porque el codigo ya verifico antes de "
            "ejecutarla -- en ese caso mostra esos datos directo, NO vuelvas "
            "a pedir verificacion de nuevo.\n"
            "Nunca uses formato markdown (nada de **negrita**, _cursiva_, "
            "ni # titulos): este canal no lo renderiza, y quedan simbolos "
            "sueltos a la vista en vez de texto resaltado. Escribi en texto "
            "plano; si hace falta estructurar pasos, usa una lista numerada "
            "simple (1. 2. 3.) en lineas separadas, nunca asteriscos.")
    else:
        partes.append(
            "Quien te escribe es SIEMPRE un colaborador de la empresa, "
            "nunca el cliente final. Habla del cliente en tercera persona; "
            "no lo saludes a el, saluda a quien te escribe.")

    if rol.descripcion:
        partes.append(f"Tu rol especifico: {rol.descripcion}")

    if persona.instrucciones_adicionales:
        partes.append(persona.instrucciones_adicionales)

    if config.seguridad.reglas_absolutas:
        partes.append("Reglas que no podes romper bajo ninguna circunstancia:\n- "
                      + "\n- ".join(config.seguridad.reglas_absolutas))

    return "\n\n".join(partes)
