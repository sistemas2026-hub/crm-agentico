# -*- coding: utf-8 -*-
"""
================================================================================
 EL COMPARADOR DE CONFIG DICE LA VERDAD EN LAS DOS DIRECCIONES
================================================================================

Por que existe
--------------
cli/diferencias_config.py nace para cazar la falla que mas veces se repitio
entre el 08 y el 09/09/2026: el repo declara algo y produccion no lo tiene.
Cuatro de los diecinueve arreglos de esos dos dias fueron eso.

Pero una herramienta de deteccion tiene DOS formas de ser inutil, y la
segunda es la peligrosa:

  - no detecta lo que deberia            -> vuelve la falla original
  - detecta cosas que estan bien         -> nadie la vuelve a mirar

La primera version cayo en la segunda. 'localidades' esta vacia en el YAML
y tiene 128 entradas en la base --como debe ser, se cargan desde la
pantalla-- y el informe la marcaba como diferencia peligrosa. De 5 alertas,
4 eran inventadas. Un informe con 80% de falsos positivos no se lee dos
veces, y entonces tampoco se ve el 20% que si importa.

Por eso este archivo prueba las dos cosas con el mismo peso: que encuentra
las cuatro fallas reales, Y que se queda callado ante lo que es normal.

Corre SIN BASE DE DATOS: comparar() es una funcion pura sobre dos dicts.

Uso
---
    py -3.13 tests/test_diferencias_config.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util                                                # noqa: E402

# cli/ no es un paquete importable: se carga el modulo por ruta, igual que
# hace tests/test_editor_config.py con su objetivo.
_ruta = Path(__file__).resolve().parents[1] / "cli" / "diferencias_config.py"
_spec = importlib.util.spec_from_file_location("diferencias_config", _ruta)
dc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dc)

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def rutas(dif: dict, cajon: str) -> set[str]:
    return {f["ruta"] for f in dif[cajon]}


PELIGRO = "repo_no_aplicado"
NORMAL = "solo_en_base"


print("== 1. las cuatro fallas medidas el 08-09/09/2026 ==")

# 1a. El campo esta en el repo y NO en la base. Es literalmente lo que paso
#     con 'auth_ref' en buscar_solicitud: 403 en vivo, y el agente leyendo
#     ese 403 como falla propia y escalando por tres_fallos_seguidos.
dif = dc.comparar(
    {"herramientas": [{"nombre": "buscar_solicitud",
                       "auth_ref": "BOTTLECRM_API_TOKEN"}]},
    {"herramientas": [{"nombre": "buscar_solicitud"}]})
afirmar("herramientas[buscar_solicitud].auth_ref" in rutas(dif, PELIGRO),
        "una credencial que el repo declara y la base no tiene se marca "
        "como peligrosa")

# 1b. El campo existe de los dos lados con valor distinto -- 'invocable_por
#     _servicio' estaba en el archivo en True y en la base en False.
dif = dc.comparar(
    {"herramientas": [{"nombre": "cerrar_ticket_operativo",
                       "invocable_por_servicio": True}]},
    {"herramientas": [{"nombre": "cerrar_ticket_operativo",
                       "invocable_por_servicio": False}]})
afirmar("herramientas[cerrar_ticket_operativo].invocable_por_servicio"
        in rutas(dif, PELIGRO),
        "una bandera con distinto valor de cada lado tambien")

# 1c. La herramienta entera nunca se aplico. Es el caso de las herramientas
#     de la oferta: escritas, commiteadas, y el agente improvisando igual lo
#     que la empresa vende porque produccion no las tenia.
dif = dc.comparar(
    {"herramientas": [{"nombre": "consultar_servicios_ofrecidos"}]},
    {"herramientas": []})
afirmar("herramientas[consultar_servicios_ofrecidos]" in rutas(dif, PELIGRO),
        "una herramienta entera que falta en la base")

# 1d. Un permiso que el repo da y la base no. La lista no se compara como
#     bloque ('15 vs 15 elementos' no le sirve a nadie): se dice QUE falta.
dif = dc.comparar(
    {"herramientas": [{"nombre": "consultar_mi_servicio",
                       "roles_permitidos": ["cliente_final", "ventas"]}]},
    {"herramientas": [{"nombre": "consultar_mi_servicio",
                       "roles_permitidos": ["cliente_final"]}]})
fila = next(f for f in dif[PELIGRO]
            if f["ruta"].endswith("roles_permitidos"))
afirmar(fila["faltan"] == ["ventas"],
        "de una lista se reporta el elemento que falta, no '2 vs 1 elementos'")


print("\n== 2. lo que es NORMAL no se marca (el falso positivo que la mato) ==")

# La seccion vacia en el YAML a proposito y llena en la base. Sin esto, el
# informe abre con 128 localidades y 100 canales como si algo estuviera mal.
dif = dc.comparar(
    {"localidades": [], "parrilla_canales": []},
    {"localidades": [{"nombre": "Baranoa"}, {"nombre": "Sabanagrande"}],
     "parrilla_canales": [{"nombre": "Caracol"}]})
afirmar(dif[PELIGRO] == [],
        "una seccion que el YAML trae vacia y la pantalla llena NO es "
        "una diferencia peligrosa")

# Y ademas se RESUME. Las dos son campos que el esquema declara propiedad de
# la base (TenantConfig.SINCRONIZADOS): que difieran no es una noticia, es la
# definicion del campo. Contra produccion eran 228 filas informativas que
# enterraban la unica que habia que mirar.
afirmar(len(dif[NORMAL]) == 2,
        "un campo sincronizado ocupa UNA linea, no una por elemento")
afirmar(all(f.get("sincronizado") for f in dif[NORMAL]),
        "y queda marcado como tal, para poder distinguirlo en el --json")
afirmar(any("2 en la base" in str(f["base"]) for f in dif[NORMAL]),
        "el resumen dice CUANTOS hay -- 'parrilla: 100 en la base' es como se "
        "ve de un vistazo que la parrilla sigue cargada")

# El campo sincronizado que esta vacio de los dos lados no dice nada y no se
# reporta: una linea que aparece siempre deja de leerse.
dif = dc.comparar({"localidades": []}, {"localidades": []})
afirmar(dif[NORMAL] == [],
        "un sincronizado vacio en los dos lados no ocupa una linea")

# Y en la direccion contraria: un sincronizado NUNCA acusa al repo, aunque el
# archivo trajera algo que la base no tiene. Es propiedad de la base en las
# dos direcciones -- el exportador no lo baja y la carga no lo pisa.
dif = dc.comparar({"localidades": [{"nombre": "Vieja"}]}, {"localidades": []})
afirmar(dif[PELIGRO] == [],
        "un sincronizado no se marca como peligroso ni con el archivo lleno "
        "y la base vacia")

# Un valor escalar que solo existe en la base -- la tarifa, el razonamiento
# del modelo: se ajustan desde la interfaz y el archivo no se entera.
dif = dc.comparar({"llm": {"razonamiento": None}},
                  {"llm": {"razonamiento": "disabled"}})
afirmar(dif[PELIGRO] == [] and "llm.razonamiento" in rutas(dif, NORMAL),
        "un ajuste hecho desde la interfaz sobre un campo vacio en el YAML "
        "es informativo, no una alerta")

# Y una herramienta que solo existe en la base: alguien la creo desde
# /agentes. El repo no la tiene y eso es correcto hasta que se exporte.
dif = dc.comparar({"herramientas": []},
                  {"herramientas": [{"nombre": "creada_desde_la_interfaz"}]})
afirmar(dif[PELIGRO] == [],
        "una herramienta creada desde la interfaz no acusa al repo")


print("\n== 3. las listas se emparejan por NOMBRE, no por posicion ==")
# Mover una herramienta dentro del YAML no es un cambio de configuracion. Con
# indices numericos, reordenar dos herramientas de 40 campos aparece como
# ochenta diferencias que hay que leer enteras para no encontrar nada.
dif = dc.comparar(
    {"herramientas": [{"nombre": "a", "url": "/a"}, {"nombre": "b", "url": "/b"}]},
    {"herramientas": [{"nombre": "b", "url": "/b"}, {"nombre": "a", "url": "/a"}]})
afirmar(dif[PELIGRO] == [] and dif[NORMAL] == [],
        "reordenar la lista de herramientas no produce ninguna diferencia")

# Y una lista de valores simples con los mismos elementos en otro orden
# tampoco acusa al repo -- 'puede_consultar' aparecio asi en la corrida real.
dif = dc.comparar({"roles": {"ventas": {"puede_consultar": ["x", "y"]}}},
                  {"roles": {"ventas": {"puede_consultar": ["y", "x"]}}})
afirmar(dif[PELIGRO] == [],
        "una lista de permisos reordenada no es una diferencia peligrosa")


print("\n== 4. no se confunde 'no existe' con 'existe y esta vacio' ==")
# Son dos estados distintos y el informe los dice distinto. Un campo AUSENTE
# en la base es la falla original; un campo presente en None puede ser un
# valor por defecto legitimo.
dif = dc.comparar({"herramientas": [{"nombre": "t", "extraer_de": "casos"}]},
                  {"herramientas": [{"nombre": "t"}]})
fila = next(f for f in dif[PELIGRO] if f["ruta"].endswith("extraer_de"))
afirmar(fila["base"] == "<no existe>",
        "un campo que la base no tiene se reporta como '<no existe>', no "
        "como null")


print("\n== 5. 'version' no se compara ==")
# config_version sube en cada carga: SIEMPRE difiere y nunca significa nada.
# Compararlo seria una linea de ruido fija en cada corrida.
dif = dc.comparar({"version": 1, "identidad": {"nombre": "x"}},
                  {"version": 129, "identidad": {"nombre": "x"}})
afirmar(dif[PELIGRO] == [] and dif[NORMAL] == [],
        "dos configs identicas con distinta version no tienen diferencias")


print("\n== 6. dos configs iguales no producen NADA ==")
# El caso que hace que la herramienta sirva para encadenar: sin diferencias,
# salida limpia y codigo 0.
igual = {"herramientas": [{"nombre": "a", "roles_permitidos": ["x"]}],
         "roles": {"ventas": {"puede_consultar": ["a"]}},
         "llm": {"razonamiento": "disabled"}}
dif = dc.comparar(igual, dict(igual))
afirmar(dif[PELIGRO] == [] and dif[NORMAL] == [],
        "sin diferencias, ninguno de los dos cajones tiene nada")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El comparador encuentra la deriva real y se calla ante lo normal.")
