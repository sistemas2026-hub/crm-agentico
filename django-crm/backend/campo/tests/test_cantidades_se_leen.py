# -*- coding: utf-8 -*-
"""Las cantidades de los avisos se leen como numeros, no como miles.

EL DEFECTO, VISTO EN LA APP (09/11/2026)
----------------------------------------
El usuario, mirando la pantalla de material del tecnico:

    «sale habia -1.000 faltan 2.000; ese numero se ve muy grande para decir
     1 y 2»

Las cantidades son ``Decimal`` con tres decimales --la columna es
``numeric(12,3)``--, asi que ``Decimal("2.000")`` interpolado directo en un
mensaje sale ``"2.000"``. **En Colombia el punto separa miles**: el tecnico
lee dos mil donde hay dos, y lo lee parado en la calle decidiendo si el kit le
alcanza.

`a_texto` ya existia para esto --la usa el cierre de jornada, por el mismo
motivo escrito ahi-- pero cuatro mensajes interpolaban el Decimal crudo.

POR QUE ESTAS PRUEBAS MIRAN EL TEXTO Y NO EL NUMERO
---------------------------------------------------
Porque el numero nunca estuvo mal: lo que estaba mal era lo que una persona
LEIA. Una prueba sobre `faltante == Decimal("2")` hubiera pasado con el
defecto vivo.
"""
from decimal import Decimal

import pytest

from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services.materiales import a_texto, clasificar


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a,
        codigo="CON-SC-APC",
        nombre="Conector SC/APC",
        clase=MaterialCatalogo.CONSUMIBLE,
        unidad="unidades",
    )


class TestComoSeEscribeUnaCantidad:
    """`a_texto` sola, sin base: es la que decide."""

    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (Decimal("2.000"), "2"),
            (Decimal("1.000"), "1"),
            (Decimal("-1.000"), "-1"),
            (Decimal("0.000"), "0"),
            #  Un decimal de verdad NO se pierde: 2,5 m de cable son 2,5.
            (Decimal("2.500"), "2.5"),
            (Decimal("0.250"), "0.25"),
            #  Y mil sigue siendo mil.
            (Decimal("1000.000"), "1000"),
            (None, "0"),
        ],
    )
    def test_1_sin_ceros_de_relleno_y_sin_perder_decimales(self, valor, esperado):
        assert a_texto(valor) == esperado


@pytest.mark.django_db
class TestElAvisoQueLeeElTecnico:
    """El mensaje del descuadre, que es donde el usuario lo vio."""

    def test_2_el_descuadre_dice_2_y_no_2000(
        self, org_a, user_profile, conector
    ):
        #  Sin kit entregado el saldo es cero, asi que consumir 2 descuadra.
        estado, detalle = clasificar(
            org=org_a,
            profile=user_profile,
            material=conector,
            tipo=MovimientoDeMaterial.CONSUMO,
            cantidad=Decimal("2.000"),
        )

        assert estado == MovimientoDeMaterial.DESCUADRE
        #  EL DEFECTO: antes decia «Se registraron 2.000 unidades ... habia
        #  0.000 ... Faltan 2.000».
        assert "2.000" not in detalle, detalle
        assert "0.000" not in detalle, detalle
        assert "Se registraron 2 " in detalle, detalle
        assert "había 0" in detalle, detalle
        assert "Faltan 2." in detalle, detalle

    def test_3_una_cantidad_con_decimales_los_conserva(
        self, org_a, user_profile, conector
    ):
        """Recortar ceros no puede volverse recortar el dato: 2,5 sigue
        siendo 2,5, y ese es el caso del cable por metro."""
        _, detalle = clasificar(
            org=org_a,
            profile=user_profile,
            material=conector,
            tipo=MovimientoDeMaterial.CONSUMO,
            cantidad=Decimal("2.500"),
        )

        assert "Se registraron 2.5 " in detalle, detalle
