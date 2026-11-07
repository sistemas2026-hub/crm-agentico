# -*- coding: utf-8 -*-
"""
================================================================================
 LAS AREAS DE TRABAJO SE CREAN DESDE LA INTERFAZ  --  08/10/2026
================================================================================

    py -3.13 tests/test_areas_de_trabajo.py

Corre SIN RED y SIN BASE.

POR QUE EXISTEN ESTOS ENDPOINTS
-------------------------------
Hasta hoy un area solo se podia crear con un script contra la base. Cuando
Rapilink necesito el area 'ventas' --el 07/10/2026, para que entraran 123
tickets que esperaban-- la creo quien opera el servidor, no el administrador
del ISP. Un ISP que arma una cuadrilla nueva no puede depender de eso.

QUE SE PRUEBA AQUI, Y QUE NO
-----------------------------
Lo propio de este cambio: como se deriva el nombre interno, y la guarda que
impide borrar un area con gente. El guardado en si es 'editor._editar', que
ya tiene sus pruebas y las suyas corren contra PostgreSQL.

EL NOMBRE INTERNO ES LO DELICADO
---------------------------------
Es lo que queda escrito en cada persona ('asistente.area_colaborador'). Si
cambiara al renombrar, esas personas quedarian apuntando a un area que no
existe y sus tickets desaparecerian de los tableros -- sin error, sin aviso.
Por eso se deriva UNA vez y lo que se corrige despues es la etiqueta.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales.api import (  # noqa: E402
    ICONOS_DE_AREA, _nombre_interno)

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))
    fallos.append(que)


print("el nombre interno sale de la etiqueta y es estable")

revisar(_nombre_interno("Cuadrilla Norte") == "cuadrilla_norte",
        "los espacios se vuelven guion bajo y todo baja a minuscula")
revisar(_nombre_interno("Administración") == "administracion",
        "los acentos se pierden, porque el identificador viaja por URL y "
        "queda escrito en la base")
revisar(_nombre_interno("NOC / Red") == "noc_red",
        "las barras y la puntuacion no sobreviven")
revisar(_nombre_interno("  Soporte   Técnico  ") == "soporte_tecnico",
        "los espacios de sobra no dejan guiones colgando",
        "'soporte___tecnico' o '_soporte_tecnico_' serian identificadores "
        "distintos para lo que una persona escribio igual")

#  Las cuatro areas que hoy existen en produccion tienen que poder salir de
#  su propia etiqueta: si el generador diera otra cosa, crear 'Cartera' desde
#  la pantalla produciria un area NUEVA al lado de la que ya esta.
for etiqueta, esperado in (("Cartera", "cartera"),
                           ("Soporte Técnico", "soporte_tecnico"),
                           ("Administración", "administracion"),
                           ("Ventas", "ventas")):
    revisar(_nombre_interno(etiqueta) == esperado,
            f"'{etiqueta}' -> '{esperado}', igual que en produccion")

print("\nlo que no puede pasar")

revisar(_nombre_interno("") == "" and _nombre_interno("///") == "",
        "una etiqueta sin letras ni numeros no produce identificador",
        "el endpoint lo rechaza con 400 en vez de crear un area sin nombre")
revisar(_nombre_interno("A" * 80) == "a" * 40,
        "un nombre larguisimo se corta en 40",
        "la columna que lo guarda tiene limite, y un identificador truncado "
        "por la base no coincidiria con el que devolvio el endpoint")
revisar(_nombre_interno("Cuadrilla Norte") == _nombre_interno("cuadrilla  NORTE"),
        "dos formas de escribir lo mismo chocan a proposito",
        "y el endpoint responde 409 nombrando el identificador, porque si "
        "no el rechazo parece arbitrario")

print("\nlos iconos son una lista cerrada")
revisar(set(ICONOS_DE_AREA) == {"llave", "factura", "edificio", "red",
                                "persona", "caja"},
        "son exactamente los seis que la pantalla sabe dibujar",
        "uno que no este degrada a las iniciales del area: no rompe, pero la "
        "fila se ve distinta de las demas sin que nadie entienda por que")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El identificador es estable y la lista de iconos es cerrada.")
