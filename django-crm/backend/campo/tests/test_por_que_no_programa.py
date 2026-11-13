# -*- coding: utf-8 -*-
"""El diagnostico de «el Supervisor no programa esta labor».

Afirma sobre el EFECTO --que la salida NOMBRE la puerta que de verdad esta
cerrada-- y no sobre que el comando exista. Un diagnostico que corre y no
acusa a nadie es peor que ninguno: manda a buscar al lugar equivocado.

Y la ultima prueba es la que mas vale: que NO ESCRIBA NADA. Este comando se
corre contra produccion.
"""
import io

import pytest
from django.core.management import call_command

from campo.cuadrillas import (
    ConfiguracionDeReparto,
    Cuadrilla,
    JornadaDeCuadrilla,
)
from campo.zonas import ZonaOperativa

pytestmark = pytest.mark.django_db


def _correr(org, **extra) -> str:
    salida = io.StringIO()
    call_command("por_que_no_programa", org=str(org.id), stdout=salida, **extra)
    return salida.getvalue()


def _correr_sin_org(**extra) -> str:
    salida = io.StringIO()
    call_command("por_que_no_programa", stdout=salida, **extra)
    return salida.getvalue()


def _cuadrilla(org, nombre, labor, *, zona=None, activa=True):
    c = Cuadrilla.objects.create(org=org, nombre=nombre, labor_habitual=labor,
                                 activa=activa)
    if zona is not None:
        c.zonas_habituales.add(zona)
    return c


# =========================================================================== #
#  LAS PUERTAS
# =========================================================================== #
def test_el_ciclo_apagado_se_nombra(org_a):
    ConfiguracionDeReparto.objects.create(org=org_a, activo=False)
    salida = _correr(org_a)

    assert "APAGADO" in salida, salida
    assert "SE CORTA EN" in salida


def test_copia_la_jornada_en_no_se_nombra(org_a):
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True,
                                          copia_la_jornada=False)
    salida = _correr(org_a)

    assert "copia_la_jornada" in salida
    assert "no arma jornadas" in salida, salida


def test_SIN_CUADRILLA_DE_ESA_LABOR_se_nombra(org_a):
    """LA PUERTA QUE EL USUARIO REPORTO, y la que nada deja en rojo.

    Una instalacion nueva no trae barrio, asi que se le cuenta a las zonas de
    las cuadrillas cuya labor habitual es la de instalacion. Sin ninguna, esos
    casos no entran en NINGUNA zona y la demanda sale sin instalaciones.
    """
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Centro", activa=True)
    _cuadrilla(org_a, "Cuadrilla 1", "correctivo", zona=zona)

    salida = _correr(org_a)

    assert "ninguna cuadrilla activa tiene 'instalacion'" in salida, salida
    assert "NINGUNA zona" in salida


def test_una_cuadrilla_INACTIVA_no_cuenta(org_a):
    #  La consulta filtra `activa=True`: una cuadrilla de instalacion dada de
    #  baja deja el camino igual de cortado, y eso no se ve en la pantalla.
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Centro", activa=True)
    _cuadrilla(org_a, "Instalacion 1", "instalacion", zona=zona, activa=False)

    salida = _correr(org_a)

    assert "ninguna cuadrilla activa tiene 'instalacion'" in salida, salida


def test_la_cuadrilla_esta_pero_SIN_ZONA(org_a):
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    _cuadrilla(org_a, "Instalacion 1", "instalacion")

    salida = _correr(org_a)

    assert "no tienen zona habitual activa" in salida, salida


def test_el_grupo_instalacion_nueva_sin_labor_se_nombra(org_a):
    #  `labor_por_grupo` con la clave en vacio: la tabla de la empresa pisa el
    #  valor de fabrica y el grupo queda sin labor.
    ConfiguracionDeReparto.objects.create(
        org=org_a, activo=True,
        labor_por_grupo={"instalacion_nueva": "una-que-no-existe"})
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Centro", activa=True)
    _cuadrilla(org_a, "Instalacion 1", "instalacion", zona=zona)

    salida = _correr(org_a)

    #  `labor_de_cada_grupo` vuelve al valor de fabrica cuando la labor
    #  guardada no es valida, asi que la fila SIGUE estando: lo que se afirma
    #  es que el informe dice cual quedo, no que se rompa.
    assert "instalacion_nueva" in salida
    assert "SE CORTA EN" in salida, salida


def test_la_demanda_vacia_se_nombra(org_a):
    #  Sin casos en Despacho no hay nada que programar, y el informe lo dice
    #  en vez de dejar a alguien buscando una cuadrilla mal configurada.
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Centro", activa=True)
    _cuadrilla(org_a, "Instalacion 1", "instalacion", zona=zona)

    salida = _correr(org_a)

    assert "NI UN caso de 'instalacion'" in salida, salida


def test_otra_labor_se_puede_diagnosticar(org_a):
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    salida = _correr(org_a, labor="correctivo")

    assert "'correctivo'" in salida
    assert "'instalacion'" not in salida.split("POR QUE NO SE PROGRAMA")[1][:200]


# =========================================================================== #
#  LO QUE NO TIENE QUE PASAR
# =========================================================================== #
def test_NO_ESCRIBE_NADA(org_a):
    """Se corre contra produccion: una jornada creada por un diagnostico es
    trabajo que nadie pidio, y `planear_el_dia` arma el plan en memoria."""
    ConfiguracionDeReparto.objects.create(org=org_a, activo=True)
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Centro", activa=True)
    _cuadrilla(org_a, "Instalacion 1", "instalacion", zona=zona)

    antes = (JornadaDeCuadrilla.objects.count(), Cuadrilla.objects.count(),
             ZonaOperativa.objects.count(), ConfiguracionDeReparto.objects.count())
    _correr(org_a)
    assert (JornadaDeCuadrilla.objects.count(), Cuadrilla.objects.count(),
            ZonaOperativa.objects.count(),
            ConfiguracionDeReparto.objects.count()) == antes


def test_una_org_que_no_existe_falla_limpio(org_a):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("por_que_no_programa",
                     org="00000000-0000-0000-0000-000000000099",
                     stdout=io.StringIO())


def test_sin_fila_de_configuracion_igual_corre(org_a):
    #  Con los valores de fabrica: `activo` es False por defecto, asi que el
    #  informe tiene que decir eso y no reventar por la fila ausente.
    salida = _correr(org_a)

    assert "valores de fabrica" in salida, salida
    assert "APAGADO" in salida


def test_SIN_pasar_la_org_igual_corre(org_a):
    """Sin `--org` se recorren todas, y la cabecera NOMBRA la empresa.

    Pedir el UUID obligaba a sacarlo con otro comando antes de poder
    diagnosticar nada. Con una sola empresa, ese paso no existe.
    """
    ConfiguracionDeReparto.objects.create(org=org_a, activo=False)
    salida = _correr_sin_org()

    assert org_a.name in salida, salida
    assert "APAGADO" in salida


def test_sin_org_recorre_LAS_DOS(org_a, org_b):
    #  Que nombre a las dos y no se quede en la primera: con dos empresas, un
    #  informe que habla de una sola manda a mirar la configuracion equivocada.
    ConfiguracionDeReparto.objects.create(org=org_a, activo=False)
    ConfiguracionDeReparto.objects.create(org=org_b, activo=False)
    salida = _correr_sin_org()

    assert org_a.name in salida and org_b.name in salida, salida
