# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- la escalada que NO decide el modelo
================================================================================

    py -3.13 tests/test_escalada_forzada.py

POR QUE EXISTE, Y POR QUE NO ES UN CASO DORADO
----------------------------------------------
El corredor de casos dorados llama a `motor.responder()` un turno a la vez, y
la escalada vive en `api.py::chat()`. Cero menciones de escalamiento en
`cli/evaluar.py` -- o sea que NINGUN caso dorado puede afirmar "y termino en
un ticket".

Ese hueco dejo pasar un bug real (25/08/2026): el flujo de cambio de WiFi
recogia el pedido del cliente, lo validaba, lo confirmaba... y moria en la
conversacion. Medido sobre 12 conversaciones: las 12 con escalada=False y sin
ticket, mientras el asistente le decia al cliente que "un colaborador humano
lo aplica". Los 5 casos dorados de WiFi estaban en verde todo ese tiempo,
afirmando cosas que eran ciertas.

Un conjunto de pruebas que no puede detectar el fallo que mas importa es el
que peor engaña, porque da confianza. Esto lo cubre, y sin llamar al modelo:
la decision es deterministica -- depende de la traza y de la config, nada mas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.seguimiento.forzado import (con_las_manos_vacias,
                                        escalada_forzada,
                                        motivos_por_hecho)  # noqa: E402
from nucleo.config.schema import Herramienta  # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


class ConfigFalsa:
    """Lo unico que mira la funcion es el catalogo de herramientas."""

    def __init__(self, herramientas):
        self.herramientas = herramientas


def herr(nombre, **kw):
    return Herramienta(nombre=nombre, tipo="interno",
                       roles_permitidos=["soporte"], **kw)


PEDIDO = herr("registrar_pedido", escalar_al_completar="pedido_para_ejecutar")
FRAGIL = herr("consultar_algo", escalar_si_falla="sin_datos_para_diagnosticar")
COMUN = herr("consultar_otra_cosa")
CFG = ConfigFalsa([PEDIDO, FRAGIL, COMUN])

print("=" * 70)
print(" ESCALADA FORZADA POR UNA HERRAMIENTA")
print("=" * 70)

print("\nel exito de una herramienta puede exigir una persona")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "registrar_pedido"}])
afirmar(motivo == "pedido_para_ejecutar",
        "una herramienta con 'escalar_al_completar' que sale bien fuerza la escalada")

motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_otra_cosa"}])
afirmar(motivo is None,
        "una que NO lo declara y sale bien no escala")

print("\nel fallo sigue funcionando como antes")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo",
                                    "codigo_error": "HTTP_500"}])
afirmar(motivo == "sin_datos_para_diagnosticar",
        "una herramienta con 'escalar_si_falla' que falla fuerza la escalada")

motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo"}])
afirmar(motivo is None,
        "esa MISMA herramienta, cuando sale bien, no escala")

# El caso al reves importa: una herramienta que declara 'escalar_al_completar'
# y FALLA no cumplio su proposito -- no hay ningun pedido tomado que entregar.
motivo, _ = escalada_forzada(CFG, [{"herramienta": "registrar_pedido",
                                    "codigo_error": "HTTP_500"}])
afirmar(motivo is None,
        "una con 'escalar_al_completar' que FALLA no escala: no tomo ningun pedido")

print("\nnada raro rompe la decision")
afirmar(escalada_forzada(CFG, [])[0] is None, "una traza vacia no escala")
afirmar(escalada_forzada(CFG, None)[0] is None, "una traza None no explota")
afirmar(escalada_forzada(CFG, [{"herramienta": "no_existe"}])[0] is None,
        "una herramienta que no esta en el catalogo se ignora")

print("\nprioridad dentro de una misma traza")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_otra_cosa"},
                                   {"herramienta": "registrar_pedido"}])
afirmar(motivo == "pedido_para_ejecutar",
        "se mira toda la traza, no solo la primera llamada")

print()
print("el motivo por hecho no entra en el menu del evaluador")
# El evaluador lee la conversacion y elige un motivo de una lista. Un motivo
# que significa "una herramienta ya registro el pedido" no se puede juzgar
# leyendo: si esta en la lista, lo elige apenas la conversacion SUENA a un
# pedido -- y como la escalada reemplaza la respuesta, corta el turno en el
# que el asistente estaba pidiendo la confirmacion. Visto el 28/08/2026.
afirmar(motivos_por_hecho(CFG) == {"pedido_para_ejecutar"},
        "se reconoce cual motivo lo decide un hecho y no un juicio")
afirmar("sin_datos_para_diagnosticar" not in motivos_por_hecho(CFG),
        "'escalar_si_falla' NO cuenta: un fallo si se puede juzgar leyendo")
afirmar(motivos_por_hecho(ConfigFalsa([])) == set(),
        "un tenant sin herramientas no deja al evaluador sin motivos")

print()
print("no se escala sin haber intentado nada")
# El modelo puede decidir escalar en el primer mensaje. Si no corrio ni una
# herramienta, el caso llega a la bandeja con la traza vacia: sin identidad,
# sin pedido y sin ticket. Paso dos veces el 28/08/2026, la segunda DESPUES de
# pedirselo por prompt -- por eso esto es codigo.
afirmar(con_las_manos_vacias([]),
        "una conversacion sin nada ejecutado esta con las manos vacias")
afirmar(con_las_manos_vacias([{"role": "user", "content": "hola"},
                              {"role": "assistant", "content": "hola"}]),
        "hablar no es hacer: solo mensajes sigue siendo manos vacias")
afirmar(not con_las_manos_vacias([{"role": "user", "content": "hola"},
                                  {"role": "tool", "name": "consultar_algo",
                                   "content": "{}"}]),
        "con una herramienta ejecutada, ya no")
afirmar(not con_las_manos_vacias([{"role": "tool", "name": "x", "content": ""}]),
        "cuenta la llamada aunque haya devuelto vacio: se intento igual")
afirmar(con_las_manos_vacias(None),
        "un historial None no explota")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: lo que obliga a escalar no depende del modelo.")
print("=" * 70)
