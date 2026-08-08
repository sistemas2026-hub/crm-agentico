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
        "explicitamente en vez de completarlo.",
    ]

    if rol.orientado_a == "cliente_final":
        partes.append(
            "Quien te escribe es el CLIENTE FINAL, en segunda persona, por "
            "un canal como WhatsApp -- no un colaborador interno. Es un "
            "desconocido hasta que su identidad quede verificada por el "
            "sistema (no por vos): no muestres ningun dato de cuenta antes "
            "de que el codigo confirme la verificacion. Identificate como "
            "asistente automatizado al inicio de la conversacion.\n"
            "Como saber si YA esta verificado: si el resultado de una "
            "herramienta trae datos reales (no un mensaje de error pidiendo "
            "identidad), es porque el codigo ya verifico antes de "
            "ejecutarla -- en ese caso mostra esos datos directo, NO vuelvas "
            "a pedir verificacion de nuevo.")
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
