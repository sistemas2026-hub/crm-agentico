# -*- coding: utf-8 -*-
"""
================================================================================
 ¿EL TRASPASO OCURRIO DE VERDAD?  --  tres situaciones que no son la misma
================================================================================

El 02/09/2026, en una conversacion real, el evaluador se cayo por timeout:

    [escalamiento] fallo al evaluar: APITimeoutError: Request timed out.

Como devolvia None igual que cuando decide "no escalar", el turno siguio como
si nada: sin caso, sin ticket, sin escalada... y con el modelo diciendole al
cliente "tu caso ya quedo en manos de un colaborador humano". El texto del
tenant solo REEMPLAZA al del modelo dentro de la rama de escalada, asi que
cuando esa rama no corre, el modelo promete lo que quiera.

TRES SITUACIONES, Y NINGUNA ES LA OTRA
--------------------------------------
  ESCALAMIENTO_CONFIRMADO      hay caso o ticket persistido de verdad
  ESCALAMIENTO_NO_CONFIRMADO   se intento registrar y no quedo en ningun lado
  NO_DETERMINADO               el evaluador fallo: no sabemos si correspondia

'NO_DETERMINADO' NO significa "se escalo". Significa que nadie pudo decidir, y
por eso no se puede afirmar nada delante del cliente. Convertirlo en una
escalada seria esconder el problema: quedaria una conversacion marcada como
traspasada sin caso ni ticket detras, que es justo la mentira que esto viene
a cerrar.

SIN DEPENDENCIAS
----------------
Como forzado.py y verificacion_accion.py: la decision es deterministica y se
comprueba sin base, sin red y sin modelo. Ver tests/test_estado_escalada.py.
"""

from __future__ import annotations

CONFIRMADO = "ESCALAMIENTO_CONFIRMADO"
NO_CONFIRMADO = "ESCALAMIENTO_NO_CONFIRMADO"
NO_DETERMINADO = "NO_DETERMINADO"


def calcular(evaluador_fallo: bool, se_intento_escalar: bool,
             caso_creado: bool, ticket_creado: bool) -> tuple[str | None, str]:
    """
    (estado, por_que) del traspaso en este turno, o (None, "") si no hubo
    ninguno en juego -- que es el caso de la enorme mayoria de los turnos.

    El orden importa: lo que MANDA es si quedo algo registrado, no si el
    evaluador contesto. Un evaluador que responde perfecto y un CRM caido dan
    NO_CONFIRMADO, porque el cliente no puede enterarse de la diferencia.
    """
    if se_intento_escalar:
        if caso_creado or ticket_creado:
            donde = " y ".join(
                [x for x in ("caso en el CRM" if caso_creado else "",
                             "ticket en la operacion" if ticket_creado else "") if x])
            return CONFIRMADO, f"quedo registrado: {donde}"
        return NO_CONFIRMADO, "se intento y no quedo registrado en ningun lado"
    if evaluador_fallo:
        return NO_DETERMINADO, "el evaluador no respondio: no se pudo decidir si correspondia escalar"
    return None, ""


def promete_traspaso(texto: str, frases: list[str] | None) -> str | None:
    """
    La frase con la que el texto promete que una persona va a atender, o None.

    Se compara contra frases que declara el TENANT ('escalamiento.
    frases_de_traspaso'), no contra una lista del motor: "un compañero", "un
    asesor" o "el area de soporte" son las palabras de cada empresa, y el
    nucleo no las conoce. Sin frases declaradas no se revisa nada -- ninguna
    empresa estrena esta sustitucion sin pedirla.

    Solo se usa cuando el estado NO es CONFIRMADO. Esa restriccion es lo que
    la vuelve segura: en un turno normal ni se ejecuta, asi que no puede
    romper una conversacion sana por un falso positivo.
    """
    if not frases or not texto:
        return None
    plano = " ".join(texto.lower().split())
    for frase in frases:
        limpia = " ".join(str(frase).lower().split())
        if limpia and limpia in plano:
            return frase
    return None
