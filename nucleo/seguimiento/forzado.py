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


def con_las_manos_vacias(historial: list[dict]) -> bool:
    """
    True si el asistente todavia no ejecuto NINGUNA herramienta en toda la
    conversacion.

    Es un hecho de la traza, no una opinion: los resultados de herramientas
    viajan en el historial como mensajes de rol 'tool'.

    Sirve para frenar una escalada decidida por el modelo cuando no hay nada
    que entregar. Un caso que llega a la bandeja con la traza vacia le pide a
    una persona que empiece de cero -- y el asistente ni siquiera intento lo
    que sabe hacer.

    Hizo falta porque pedirselo al modelo NO alcanzo. El 28/08/2026 se le
    agrego la instruccion de no confundir un tramite con un pedido de hablar
    con alguien; funciono en la prueba y volvio a fallar en produccion tres
    horas despues, con el mismo mensaje y otra conversacion. El prompt es
    guia, la garantia es codigo (PRD 7.4).
    """
    return not any(m.get("role") == "tool" for m in (historial or []))


def motivos_por_hecho(config) -> set[str]:
    """
    Los motivos que NO puede elegir el modelo: los que declara una herramienta
    en 'escalar_al_completar'.

    Un motivo asi significa "una herramienta ya registro el pedido", y eso es
    un hecho de la traza -- mirando el texto no se puede saber. El evaluador
    corre igual en cada turno y ve la misma lista de motivos, asi que si el
    motivo esta en su menu lo va a elegir en cuanto la conversacion SUENE a
    un pedido, que es antes de que el pedido exista.

    Paso el 28/08/2026 con un cambio de clave de WiFi: el asistente le habia
    preguntado al cliente si confirmaba la clave, el evaluador escalo en ese
    mismo turno con 'pedido_para_ejecutar', y la escalada REEMPLAZA la
    respuesta (ver api.py) -- asi que la pregunta nunca le llego. El cliente
    leyo "tu pedido quedo registrado" sin haber confirmado nada, la
    herramienta que valida el pedido nunca corrio, y el caso le decia a quien
    lo tomara que faltaba la confirmacion del cliente.
    """
    motivos = {h.escalar_al_completar for h in (config.herramientas or [])
               if h.escalar_al_completar}
    # Lo mismo vale para el que sale de una comprobacion posterior: "la accion
    # no produjo su efecto" es una medicion, no algo que se pueda juzgar
    # leyendo la conversacion. Si estuviera en el menu, el evaluador lo
    # elegiria en cuanto el cliente dijera que sigue igual -- antes de que
    # nadie haya medido nada.
    motivos |= {h.verificacion.escalar_si_no_confirma
                for h in (config.herramientas or [])
                if getattr(h, "verificacion", None)
                and h.verificacion.escalar_si_no_confirma}
    return motivos


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

    La razon nombra a la herramienta porque termina siendo el RESUMEN del
    caso cuando el evaluador no dejo uno (ver api.py): sin el nombre, quien
    abre el caso lee una frase que podria ser de cualquier conversacion.
    """
    por_nombre = {h.nombre: h for h in config.herramientas}
    for llamada in registro_herramientas or []:
        herr = por_nombre.get(llamada.get("herramienta"))
        if herr is None:
            continue
        if llamada.get("codigo_error"):
            if herr.escalar_si_falla:
                return (herr.escalar_si_falla,
                        f"'{herr.nombre}' no pudo ejecutarse")
        # El espejo: la herramienta SALIO BIEN y su exito es, justamente, un
        # pedido que tiene que ejecutar una persona. Ver schema.py.
        elif herr.escalar_al_completar:
            return (herr.escalar_al_completar,
                    f"'{herr.nombre}' se completo y lo que registro tiene "
                    f"que aplicarlo una persona")
    return None, ""
