# -*- coding: utf-8 -*-
"""
================================================================================
 EL PISO DE POTENCIA LO PONE LA EMPRESA, NO EL NUCLEO  --  12/11/2026
================================================================================
`SENAL_MINIMA_DBM = -25.0` estuvo fijo en `nucleo/herramientas/
diagnostico_servicio.py` mientras `nucleo/config/schema.py` declaraba, en dos
lugares, que ese dato es del tenant -- y mientras el campo
`TenantConfig.umbral_rx_dbm` ya existia sin que nadie lo leyera.

EL EFECTO, MEDIDO EN PRODUCCION EL 12/11/2026
---------------------------------------------
La pantalla de revision de cierre de una orden real dijo:

    «La medida al salir (-21 dBm) esta dentro de lo que la empresa considera
     bueno (-27 a -8)»

Rapilink habia editado su plantilla de campo a **-27**. El motor seguia en
**-25**. Una ONT a -26 dBm era «debil» para el diagnostico y «buena» para la
revision de campo, el mismo dia y en la misma empresa. Nadie lo reporto
porque las dos pantallas no se miran juntas.

POR QUE ESTA GUARDA Y NO LA DE ARQUITECTURA
-------------------------------------------
`test_nucleo_sin_tenants.py` paso en verde todo ese tiempo, y tiene razon
segun lo que mide: busca slugs, ramas por tenant y URLs de servicios. Un
NUMERO fijo que deberia ser configuracion no se parece a ninguna de las tres.
Esta guarda mide la otra forma del mismo problema.

LO QUE AFIRMA, Y EN QUE ORDEN IMPORTA
-------------------------------------
  1. con la empresa configurada, manda SU numero -- no el del codigo
  2. sin configurar, sigue habiendo veredicto (el respaldo), porque apagarlo
     en el mismo deploy dejaria a todas las empresas sin diagnostico
  3. un umbral ilegible no tumba el diagnostico: cae al respaldo
  4. el techo NO sale de la config, y eso es deliberado

Se corre sola:  py -3.13 tests/test_umbral_de_senal_por_empresa.py
================================================================================
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.herramientas import diagnostico_servicio as diag  # noqa: E402

FALLAS: list[str] = []


def afirmar(condicion, mensaje: str) -> None:
    if condicion:
        print(f"  [ok] {mensaje}")
    else:
        print(f"  [FALLA] {mensaje}")
        FALLAS.append(mensaje)


class _ConfigFalsa:
    def __init__(self, umbral):
        self.umbral_rx_dbm = umbral


def _con_umbral(umbral, *, revienta: bool = False):
    """Sustituye `nucleo.config.fuente` por uno que devuelve ese umbral.

    Se parchea el modulo en `sys.modules` porque `piso_de_la_empresa` lo
    importa adentro de la funcion, a proposito: asi no hay import circular.
    """
    falso = types.ModuleType("nucleo.config.fuente")

    def cargar(_tenant):
        if revienta:
            raise RuntimeError("la base no responde")
        return _ConfigFalsa(umbral)

    falso.cargar = cargar
    return falso


def _poner(modulo):
    sys.modules["nucleo.config.fuente"] = modulo


def _sacar():
    sys.modules.pop("nucleo.config.fuente", None)


print(__doc__)

# ---------------------------------------------------------------------------
#  1) MANDA EL NUMERO DE LA EMPRESA
# ---------------------------------------------------------------------------
print("\n1) el piso sale de la configuracion de la empresa")

_poner(_con_umbral(-27.0))
piso = diag.piso_de_la_empresa("rapilink")
afirmar(piso == -27.0,
        f"con umbral_rx_dbm=-27.0 el piso es -27.0 (dio {piso})")

#  EL CASO EXACTO DEL 12/11/2026. -26 dBm cae entre los dos numeros, que es
#  justo donde el bug se veia: para el motor era «debil» y para campo «buena».
afirmar(diag._clasificar_senal(-26.0, piso) == "buena",
        "-26.0 dBm es BUENA para una empresa cuyo piso es -27 "
        "(con el piso fijo de -25 daba «debil»: el bug del 12/11)")

afirmar(diag._clasificar_senal(-28.0, piso) == "debil",
        "-28.0 dBm sigue siendo debil: el piso acota, no desaparece")

#  Y con OTRA empresa, otro numero. Si esta falla, el piso volvio a ser uno
#  solo para todos.
_poner(_con_umbral(-22.0))
piso_b = diag.piso_de_la_empresa("otra-empresa")
afirmar(piso_b == -22.0,
        f"otra empresa con -22.0 obtiene -22.0 (dio {piso_b})")
afirmar(diag._clasificar_senal(-24.0, piso_b) == "debil",
        "-24.0 dBm es DEBIL para la empresa de piso -22, "
        "y seria «buena» con el piso de la otra: dos empresas, dos reglas")

# ---------------------------------------------------------------------------
#  2) SIN CONFIGURAR, SIGUE HABIENDO VEREDICTO
# ---------------------------------------------------------------------------
print("\n2) sin umbral cargado cae al respaldo, no se queda mudo")

_poner(_con_umbral(None))
piso_none = diag.piso_de_la_empresa("sin-cargar")
afirmar(piso_none == diag.SENAL_MINIMA_DBM,
        f"umbral_rx_dbm=None usa el respaldo {diag.SENAL_MINIMA_DBM} "
        f"(dio {piso_none})")
afirmar(diag._clasificar_senal(-20.0, piso_none) == "buena",
        "y el diagnostico sigue dando veredicto: apagarlo en el mismo deploy "
        "dejaria sin diagnostico a todas las empresas a la vez")

afirmar(diag.piso_de_la_empresa(None) == diag.SENAL_MINIMA_DBM,
        "sin tenant tampoco revienta: respaldo")

# ---------------------------------------------------------------------------
#  3) UN PROBLEMA DE LECTURA NO TUMBA EL DIAGNOSTICO
# ---------------------------------------------------------------------------
print("\n3) si la configuracion no se puede leer, cae al respaldo")

_poner(_con_umbral(None, revienta=True))
piso_roto = diag.piso_de_la_empresa("rapilink")
afirmar(piso_roto == diag.SENAL_MINIMA_DBM,
        f"la base caida devuelve el respaldo, no una excepcion "
        f"(dio {piso_roto})")

_poner(_con_umbral("no es un numero"))
piso_basura = diag.piso_de_la_empresa("rapilink")
afirmar(piso_basura == diag.SENAL_MINIMA_DBM,
        f"un umbral que no es un numero cae al respaldo (dio {piso_basura})")

_sacar()

# ---------------------------------------------------------------------------
#  4) EL TECHO NO SALE DE LA CONFIG, Y ES DELIBERADO
# ---------------------------------------------------------------------------
print("\n4) el techo lo pone el equipo, no el tendido")

afirmar(diag.SENAL_MAXIMA_DBM == -8.0,
        "el techo sigue siendo -8.0 en codigo: es saturacion del receptor, "
        "no depende de la planta de la empresa")
afirmar(diag._clasificar_senal(-5.0, -27.0) == "debil",
        "-5.0 dBm es debil aunque la empresa baje su piso: "
        "el piso configurable no abre el techo")

# ---------------------------------------------------------------------------
#  5) LA REGLA PURA SIGUE SIENDO LA DE ANTES
# ---------------------------------------------------------------------------
print("\n5) sin piso explicito, la regla no cambio")

afirmar(diag._clasificar_senal(None) == "sin_dato",
        "sin numero no hay juicio")
afirmar(diag._clasificar_senal(-20.55) == "buena",
        "-20.55 dBm sigue siendo buena con el respaldo")
afirmar(diag._clasificar_senal(-27.0) == "debil",
        "-27.0 dBm sigue siendo debil con el respaldo: "
        "quien no configuro nada no ve ningun cambio de conducta")

print()
if FALLAS:
    print(f"FALLARON {len(FALLAS)}:")
    for f in FALLAS:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] El piso de potencia lo pone cada empresa, y sin configurar "
      "nadie se queda sin veredicto.")
