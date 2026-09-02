# -*- coding: utf-8 -*-
"""
================================================================================
 ¿LA ACCION HIZO LO QUE DIJO?  --  verificacion posterior, decidida en codigo
================================================================================

Una herramienta de escritura confirma que el COMANDO SE MANDO, no que produjo
ningun efecto. 'reiniciar_ont' es el ejemplo exacto: el proveedor responde
"Device reboot command sent" en medio segundo, y el equipo tarda minutos en
volver -- si es que vuelve.

Hasta ahora el unico que podia notar la diferencia era el modelo, leyendo la
palabra "sent". Este modulo la decide con mediciones: una ANTES de actuar y
otra DESPUES, comparadas por una regla declarada en la config del tenant.

CUATRO ESTADOS, Y NINGUNO ES UN JUICIO
--------------------------------------
  VERIFICACION_PENDIENTE  se ejecuto, todavia no se pudo comprobar
  ACCION_CONFIRMADA       las mediciones prueban el efecto tecnico esperado
  ACCION_NO_CONFIRMADA    se midio y el efecto no aparecio
  NO_VERIFICABLE          no se pudo medir (el instrumento no respondio)

'NO_VERIFICABLE' NO es 'ACCION_NO_CONFIRMADA', y la diferencia importa: una
dice que la accion fallo, la otra que no sabemos. Tratarlas igual es lo que
lleva a mandar un tecnico porque SmartOLT estaba caido.

Y una linea que conviene tener presente rio abajo: ACCION_CONFIRMADA significa
"el reinicio ocurrio y el equipo volvio", NO "el cliente ya tiene internet".
Eso ultimo no lo puede medir ningun endpoint -- lo sabe el cliente, y hay que
preguntarselo.

SIN DEPENDENCIAS A PROPOSITO
----------------------------
Igual que forzado.py: la decision es deterministica, asi que se comprueba sin
base de datos, sin red y sin modelo. Ver tests/test_verificacion_accion.py.
"""

from __future__ import annotations

PENDIENTE = "VERIFICACION_PENDIENTE"
CONFIRMADA = "ACCION_CONFIRMADA"
NO_CONFIRMADA = "ACCION_NO_CONFIRMADA"
NO_VERIFICABLE = "NO_VERIFICABLE"

#: Estados en los que la verificacion ya termino y no hay que volver a medir.
TERMINALES = (CONFIRMADA, NO_CONFIRMADA, NO_VERIFICABLE)


def buscar_campo(dato, campo: str):
    """
    Busca 'campo' a cualquier profundidad de la respuesta de una herramienta.

    Copia deliberada de la misma busqueda que hace nucleo/modelo/motor.py para
    'exige_previas'. Se repite en vez de importarse porque importar de motor.py
    arrastraria el cliente del modelo entero, y este modulo existe justamente
    para poder comprobarse sin nada de eso.

    Hace falta porque la forma de las respuestas no es una sola: 'ping_cliente'
    devuelve una lista de diccionarios ([{'ping-1': {...}}, ...,
    {'ping-exitoso': '3 de 3'}]) y buscar solo en el primer nivel no encuentra
    nada. Costo un bug real en agosto de 2026 -- la precondicion del reinicio
    no podia cumplirse nunca y parecia que el modelo no queria ejecutarlo.
    """
    if isinstance(dato, dict):
        if campo in dato:
            return dato[campo]
        for anidado in dato.values():
            encontrado = buscar_campo(anidado, campo)
            if encontrado is not None:
                return encontrado
    elif isinstance(dato, list):
        for elemento in dato:
            encontrado = buscar_campo(elemento, campo)
            if encontrado is not None:
                return encontrado
    return None


def _cumple(comprobacion, valor_antes, valor_despues) -> bool | None:
    """
    Si esta comprobacion pasa. None = no se pudo medir.

    Dos reglas, y cada una existe por lo que su instrumento SI puede decir:

    'cambio'  -- el valor de despues tiene que ser distinto al de antes.
                 Para un campo discreto (el sello de la ultima vez que el
                 equipo cambio de estado) eso prueba que el reinicio ocurrio
                 de verdad. No mira el contenido, solo que se movio: asi no
                 hace falta interpretar formatos ni zonas horarias -- se
                 compara la misma fuente contra si misma.

    'valores' -- el valor de despues tiene que estar en una lista cerrada.
                 Para un instrumento con ruido (el ping del proveedor devuelve
                 '1 de 3', '2 de 3' o '3 de 3' en corridas seguidas sobre el
                 MISMO equipo sano, medido el 15/08/2026) sirve para preguntar
                 lo unico que no es ruido: si contesta o no contesta.
    """
    if valor_despues is None:
        return None
    if comprobacion.regla == "cambio":
        if valor_antes is None:
            # Sin medicion previa no hay contra que comparar. No es un fallo
            # de la accion: es que no se pudo verificar.
            return None
        return str(valor_despues) != str(valor_antes)
    if comprobacion.regla == "valores":
        return str(valor_despues) in [str(v) for v in (comprobacion.valores or [])]
    return None


def evaluar(comprobaciones, antes: dict, despues: dict,
            intento: int, max_intentos: int) -> tuple[str, str]:
    """
    (estado, por_que) a partir de las dos mediciones.

    'antes' y 'despues' son {nombre_de_herramienta: respuesta cruda o None}.
    Un None significa que esa medicion no se pudo tomar.

    El orden de las salidas no es casual:

      1. Si algo NO SE PUDO MEDIR, el resultado es NO_VERIFICABLE aunque otra
         comprobacion haya pasado. Confirmar a medias es afirmar de mas.
      2. Si todo lo medido pasa, CONFIRMADA.
      3. Si algo no pasa y quedan intentos, sigue PENDIENTE -- el equipo puede
         estar todavia arrancando, y volver a medir en el proximo turno es
         gratis comparado con mandar un tecnico de mas.
      4. Sin intentos, NO_CONFIRMADA.
    """
    if not comprobaciones:
        return NO_VERIFICABLE, "la herramienta no declara como comprobarse"

    faltaron, fallaron = [], []
    for c in comprobaciones:
        valor_antes = buscar_campo(antes.get(c.herramienta), c.campo)
        valor_despues = buscar_campo(despues.get(c.herramienta), c.campo)
        resultado = _cumple(c, valor_antes, valor_despues)
        if resultado is None:
            faltaron.append(f"{c.herramienta}.{c.campo}")
        elif not resultado:
            fallaron.append(f"{c.herramienta}.{c.campo}={valor_despues!r}")

    if faltaron:
        return NO_VERIFICABLE, "no se pudo medir " + ", ".join(faltaron)
    if not fallaron:
        return CONFIRMADA, "todas las comprobaciones dieron el efecto esperado"
    if intento < max_intentos:
        return PENDIENTE, (f"intento {intento} de {max_intentos}: todavia no "
                           + ", ".join(fallaron))
    return NO_CONFIRMADA, "no se cumplio " + ", ".join(fallaron)
