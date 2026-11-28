# -*- coding: utf-8 -*-
"""
================================================================================
 REPORTE DE COMPROBANTE DE PAGO  --  el agente no confirma, junta y deriva
================================================================================

El asistente NO valida pagos. No los registra, no los aprueba, no reconecta
nada. Lo unico que hace es juntar en un formato prolijo lo que el CLIENTE
escribio sobre su comprobante y forzar que un colaborador humano lo revise --
esa persona es quien de verdad confirma el pago y lo registra en WispHub
(nucleo/config/schema.py, herramientas 'registrar_pago'/'agregar_promesa_pago',
sin tocar en esta fase).

POR QUE EL MODELO NUNCA "LEE" LA IMAGEN
----------------------------------------
No hay ningun camino de vision en este sistema (ver DESPLIEGUE.md, "El modelo
no ve las imagenes"). Cuando un cliente manda una foto SIN texto, el motor le
entrega al modelo el marcador '[El cliente envio una foto]' -- no el
contenido. Cuando la manda CON una leyenda, el modelo ve esa leyenda y nada
mas. Por eso esta herramienta no recibe "lo que dice la imagen": recibe lo que
el CLIENTE escribio en el chat sobre su pago, y el codigo nunca finge haber
visto algo que no vio. La descripcion de la herramienta (YAML del tenant) le
prohibe expresamente al modelo afirmar que "leyo" o "vio" el comprobante.

POR QUE EN CODIGO Y NO EN EL PROMPT
------------------------------------
Mismo criterio que wifi.py: un limite en codigo no tiene 'casi'. Si el reporte
esta incompleto, el codigo lo frena ANTES de que se dispare cualquier
escalada -- no depende de que el modelo se acuerde de no prometer nada.

LOS CUATRO ESTADOS
-------------------
  COMPROBANTE_RECIBIDO       hay valor y (fecha o referencia): pasa a un humano
  COMPROBANTE_INCOMPLETO     falta un dato imprescindible: se lo vuelve a pedir
  COMPROBANTE_ILEGIBLE       el CLIENTE dijo que la imagen no se ve bien
  NO_PARECE_COMPROBANTE      no hay ningun dato de pago en lo que se escribio

Ninguno de los cuatro significa "pago confirmado". Esa frase no existe en
ningun estado a proposito: el que confirma es el humano, en WispHub, no esta
funcion.
================================================================================
"""

from __future__ import annotations

COMPROBANTE_RECIBIDO = "COMPROBANTE_RECIBIDO"
COMPROBANTE_INCOMPLETO = "COMPROBANTE_INCOMPLETO"
COMPROBANTE_ILEGIBLE = "COMPROBANTE_ILEGIBLE"
NO_PARECE_COMPROBANTE = "NO_PARECE_COMPROBANTE"

ADVERTENCIA = (
    "El comprobante fue recibido y revisado preliminarmente por el agente. "
    "El pago NO ha sido confirmado. Validarlo antes de registrarlo."
)


def _estado_y_faltantes(valor: str, fecha: str, referencia: str,
                        medio: str, observaciones: str, ilegible: bool
                        ) -> tuple[str, list[str]]:
    """
    La regla completa, aislada de la construccion del resumen para poder
    probarla sola. Lista vacia de faltantes = no hace falta pedir nada mas.

    El cliente diciendo que la imagen no se ve bien pesa mas que cualquier
    otro dato: aunque haya escrito un valor y una fecha, si el la marco como
    ilegible, lo que hace falta es una foto nueva, no seguir para adelante
    con datos que el mismo puso en duda.
    """
    if ilegible:
        return COMPROBANTE_ILEGIBLE, ["una foto legible del comprobante"]

    if not (valor or fecha or referencia or medio or observaciones):
        return NO_PARECE_COMPROBANTE, []

    faltantes = []
    if not valor:
        faltantes.append("el valor pagado")
    if not (fecha or referencia):
        faltantes.append("la fecha del pago o el numero de referencia")
    if faltantes:
        return COMPROBANTE_INCOMPLETO, faltantes

    return COMPROBANTE_RECIBIDO, []


def procesar_reporte(herramienta, argumentos: dict) -> dict:
    """
    Junta lo que el cliente reporto sobre su pago y arma el resumen que va a
    leer un colaborador de cartera. NO llama a ninguna API, NO decide si el
    pago es real: eso es exactamente lo que esta funcion NUNCA hace.

    'nombre_cliente'/'id_cliente_sesion' llegan por 'inyectar_sesion' (ver el
    YAML de esta herramienta) -- el modelo nunca los propone, son datos de la
    sesion ya verificada. Sin eso, cualquiera podria hacer que el caso quede
    asociado a otro cliente con solo escribir un nombre distinto.
    """
    valor = (argumentos.get("valor_reportado") or "").strip()
    fecha = (argumentos.get("fecha_comprobante") or "").strip()
    referencia = (argumentos.get("referencia") or "").strip()
    medio = (argumentos.get("medio_pago") or "").strip()
    pagador = (argumentos.get("nombre_pagador") or "").strip()
    observaciones = (argumentos.get("observaciones") or "").strip()
    # 'legible' lo llena el modelo SOLO si el cliente dijo algo al respecto
    # (nunca una opinion propia -- no tiene con que opinar). Ausente = el
    # cliente no dijo nada del tema, que es lo mas comun.
    ilegible = str(argumentos.get("legible") or "").strip().lower() == "no"

    nombre_cliente = (argumentos.get("nombre_cliente") or "").strip()
    id_cliente = (argumentos.get("id_cliente_sesion") or "").strip()

    estado, faltantes = _estado_y_faltantes(
        valor, fecha, referencia, medio, observaciones, ilegible)

    # El resumen se arma siempre, aunque solo se USE cuando el estado es
    # COMPROBANTE_RECIBIDO (motor.py solo deja pasar 'resumen_desde' con
    # codigo_error=None, y las otras tres ramas SI lo llevan -- ver
    # _codigo_error_de_reporte_pago). Construirlo siempre, en vez de
    # ramificar, es mas simple y no tiene costo: si no se usa, no se lee.
    lineas = [
        "VALIDACIÓN DE PAGO",
        "",
        f"Cliente: {nombre_cliente or 'sin identificar'}",
        f"Identificación: {id_cliente or 'sin identificar'}",
        f"Valor reportado: {valor or 'no informado'}",
        f"Fecha del comprobante: {fecha or 'no informada'}",
        f"Referencia: {referencia or 'no informada'}",
        f"Medio de pago: {medio or 'no informado'}",
    ]
    if pagador:
        lineas.append(f"Nombre del pagador: {pagador}")
    if observaciones:
        lineas.append(f"Observaciones: {observaciones}")
    lineas += [
        f"Resultado de revisión preliminar: {estado}",
        "Comprobante: revisar los adjuntos de esta conversación.",
        "Estado: PENDIENTE DE VALIDACIÓN HUMANA",
        "",
        ADVERTENCIA,
    ]

    return {
        "estado": estado,
        # Frases listas para pedirle al cliente lo que falta -- mismo
        # criterio que 'problemas' en wifi.py: se le dicen TODAS juntas.
        "faltantes": faltantes,
        "resumen": "\n".join(lineas),
    }
