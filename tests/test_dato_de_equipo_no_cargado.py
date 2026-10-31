# -*- coding: utf-8 -*-
"""
================================================================================
 NO SE LE PIDE LA CEDULA A QUIEN YA ESTA VERIFICADO
================================================================================

Por que existe
--------------
Once herramientas declaran 'sn_onu' en 'inyectados_obligatorios'. Cuando la
cuenta no lo tiene cargado, la llamada no sale -- correcto, una consulta sin
filtro devolveria a todo el mundo con cara de exito. Lo que estaba mal era lo
que se le decia al modelo: SIEMPRE "pedile su numero de cedula y verifica la
identidad primero".

Esa instruccion sirve para UNA de las dos causas. Si la sesion no sabe quien
es el cliente, pedir la cedula lo arregla. Si ya lo sabe --verificada, con
id_cliente-- lo que falta es un dato del EQUIPO que el ISP nunca cargo, y que
el cliente no puede dar por mas cedulas que escriba.

Medido el 15/09/2026 con un cliente real sin 'sn_onu':

    cliente : no tengo internet
    agente  : Para revisar tu conexion necesito confirmar tu identidad.
              ¿Me pasas tu numero de cedula?          <- ya estaba verificado
    cliente : (la da)
    agente  : No pude encontrar tu cedula. ¿Me la confirmas o la escribes
              de nuevo?

Nunca se lo diagnostica y nunca se lo guia. Y no es un borde: 1.299 de 4.163
clientes activos no tienen el identificador cargado -- el 32%.

El nucleo no sabe que 'sn_onu' es un equipo ni tiene por que saberlo (ver
ARQUITECTURA.md). Lo que si puede distinguir, sin conocer a ningun tenant, es
si la identidad ya esta resuelta.

Lo que se fija
--------------
1. LOS DOS ESTADOS DICEN COSAS DISTINTAS. Es lo unico que importa: la version
   rota tenia UNA instruccion para las dos causas, asi que una prueba que solo
   comprobara "hay un mensaje" la habria dado por buena.

2. CON LA IDENTIDAD RESUELTA NO SE PIDE LA CEDULA. Ni con las palabras de la
   version rota ni insinuandolo.

3. SIN IDENTIDAD SIGUE PIDIENDOLA. El arreglo no puede romper el caso para el
   que la instruccion se escribio: ahi pedir la cedula es exactamente lo
   correcto.

4. FAIL-CLOSED SIN SESION: se trata como identidad no resuelta.

5. CADA CAUSA TIENE SU CODIGO. La auditoria tiene que poder contarlas aparte
   -- "cuantos clientes se quedaron sin diagnostico porque nadie cargo el
   serial" es una pregunta de operacion, no de depuracion.

Corre SIN BASE DE DATOS y sin red: la funcion es pura.

Uso
---
    py -3.13 tests/test_dato_de_equipo_no_cargado.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.modelo.motor import (falta_un_dato_de_la_sesion,      # noqa: E402
                                 CODIGOS_DE_BLOQUEO)

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    if not condicion:
        fallos.append(que)


def comprobar(seccion: str) -> None:
    print(f"\n--- {seccion} ---")


class SesionResuelta:
    verificado = True
    id_cliente = "6555"


class SesionSinIdentidad:
    verificado = False
    id_cliente = None


class SesionVerificadaSinCliente:
    """Verificada pero sin saber de quien: no alcanza para dar por resuelto."""
    verificado = True
    id_cliente = None


# ---------------------------------------------------------------------------
comprobar("1. las dos causas no pueden decir lo mismo")

equipo, cod_equipo = falta_un_dato_de_la_sesion(
    "consultar_estado_ont", ["sn_onu"], SesionResuelta())
identidad, cod_identidad = falta_un_dato_de_la_sesion(
    "ping_cliente", ["id_servicio"], SesionSinIdentidad())

afirmar(equipo["instruccion_interna"] != identidad["instruccion_interna"],
        "las dos causas producen LA MISMA instruccion -- es la version rota, "
        "que tenia un solo texto para ambas")
afirmar(cod_equipo != cod_identidad,
        "las dos causas comparten codigo: la auditoria no puede contarlas "
        "por separado")

print(f"  identidad sin resolver -> {cod_identidad}")
print(f"  dato del equipo        -> {cod_equipo}")

# ---------------------------------------------------------------------------
comprobar("2. con la identidad resuelta NO se pide la cedula")

texto = equipo["instruccion_interna"].lower()
for frase in ("pedile su numero de cedula", "pedile la cedula",
              "verifica la identidad primero"):
    afirmar(frase not in texto,
            f"con la identidad ya resuelta sigue mandando a pedir la cedula: "
            f"'{frase}'")

# Y que lo diga explicito, porque el modelo lo desobedecio cuando solo se lo
# insinuaba desde el prompt del tenant (mismo dia, otro bug).
afirmar("no le pidas la cedula" in texto,
        "no prohibe explicitamente pedir la cedula -- dejarselo deducir es lo "
        "que fallo la primera vez")

# Tampoco puede mandarlo a anunciar una averia inexistente.
afirmar("problema tecnico" in texto,
        "no le dice que NO anuncie un problema tecnico")

# ---------------------------------------------------------------------------
comprobar("3. sin identidad se sigue pidiendo la cedula")

afirmar("cedula" in identidad["instruccion_interna"].lower(),
        "el camino de identidad sin resolver dejo de pedir la cedula: el "
        "arreglo rompio el caso para el que la instruccion fue escrita")

# ---------------------------------------------------------------------------
comprobar("4. fail-closed")

afirmar(falta_un_dato_de_la_sesion("ping_cliente", ["id_servicio"], None)[1]
        == cod_identidad,
        "sin sesion no se trata como identidad sin resolver")
afirmar(falta_un_dato_de_la_sesion(
            "consultar_estado_ont", ["sn_onu"], SesionVerificadaSinCliente())[1]
        == cod_identidad,
        "una sesion verificada pero SIN id_cliente se da por resuelta -- "
        "verificado solo no alcanza para saber de quien son los datos")

# ---------------------------------------------------------------------------
comprobar("5. el codigo nuevo viaja como bloqueo, no como error")

afirmar(cod_equipo in CODIGOS_DE_BLOQUEO,
        f"'{cod_equipo}' no esta en CODIGOS_DE_BLOQUEO: la traza lo contaria "
        "como una falla del sistema y no como la proteccion funcionando")

# ---------------------------------------------------------------------------
comprobar("6. el dato que falta se nombra, para que el log sirva")

afirmar("sn_onu" in equipo["instruccion_interna"],
        "no nombra el campo que falta: quien lea la traza no sabe cual era")

# ---------------------------------------------------------------------------
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] Falta un dato del equipo y falta la identidad se tratan distinto.")
