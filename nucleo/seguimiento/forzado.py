# -*- coding: utf-8 -*-
"""
================================================================================
 ESCALADA POR HECHO  --  la que no decide el modelo
================================================================================

Modulo propio y sin dependencias a proposito: 'api.py' arrastra la base y el
motor entero, y esto tiene que poder comprobarse sin levantar nada. Es la
unica forma de que este camino tenga guarda -- el corredor de casos dorados
llama a motor.responder() y nunca pasa por la escalada (cero menciones de
escalamiento en cli/evaluar.py), asi que un fallo aca no lo ve nadie.

Ver tests/test_escalada_forzada.py y el bug que lo motivo.
"""

from __future__ import annotations


def escalada_forzada(config, registro_herramientas: list[dict]) -> tuple[str | None, str]:
    """
    (motivo, por_que) cuando una herramienta OBLIGA a escalar, o (None, "").

    Escalamiento POR HECHO, no por juicio: no le pregunta al modelo. Vive
    aparte de chat() para poder comprobarlo sin levantar nada -- la unica
    forma de que este camino tenga guarda, porque el corredor de casos
    dorados llama a motor.responder() y nunca pasa por aca (cero menciones de
    escalamiento en cli/evaluar.py). Ese hueco dejo pasar un bug real: el
    flujo de WiFi recogia el pedido y no se lo entregaba a nadie, con los 5
    casos dorados en verde.

    Gana la primera herramienta de la traza que lo pida, y un fallo tiene
    prioridad sobre un exito dentro de la misma llamada.
    """
    por_nombre = {h.nombre: h for h in config.herramientas}
    for llamada in registro_herramientas or []:
        herr = por_nombre.get(llamada.get("herramienta"))
        if herr is None:
            continue
        if llamada.get("codigo_error"):
            if herr.escalar_si_falla:
                return herr.escalar_si_falla, "no pudo ejecutarse"
        # El espejo: la herramienta SALIO BIEN y su exito es, justamente, un
        # pedido que tiene que ejecutar una persona. Ver schema.py.
        elif herr.escalar_al_completar:
            return (herr.escalar_al_completar,
                    "se completo y su resultado necesita una persona")
    return None, ""
