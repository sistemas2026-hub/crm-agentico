"""
================================================================================
 EL INFORME DE JORNADAS CUENTA LO QUE SE REPITE, Y NO ESCRIBE NADA  --  17/10/2026
================================================================================
Lo pidio el usuario antes de que el Supervisor arme jornadas solo: "analiza
bien esa ventana de cuadrilla y dime que se repite". Se afirma sobre la salida
del comando, con datos armados para que cada conteo sea uno solo posible.
================================================================================
"""
import io
from datetime import timedelta

import pytest
from django.core.management import call_command

from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    PersonaDeCampo,
)
from campo.zonas import ZonaOperativa

pytestmark = pytest.mark.django_db


def _jornada(org, cuadrilla, fecha, zonas=(), gente=(), labor="correctivo",
             notas=""):
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=cuadrilla, fecha=fecha, labor=labor, notas=notas)
    j.zonas.set(zonas)
    for persona in gente:
        IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                           rol="tecnico")
    return j


def _correr(org, dias=7):
    salida = io.StringIO()
    call_command("informe_de_jornadas", "--org", str(org.id), "--dias", str(dias),
                 stdout=salida)
    return salida.getvalue()


def _fila(salida, seccion, empieza):
    """La primera fila de la seccion 'seccion' que empieza con 'empieza'."""
    bloque = salida.split(f"\n{seccion}.", 1)[1].split("\n\n", 1)[0]
    for linea in bloque.splitlines():
        if linea.startswith(empieza):
            return linea
    raise AssertionError(f"no hay fila {empieza!r} en la seccion {seccion}:\n{bloque}")


@pytest.fixture
def armado(org_a, admin_profile):
    """
    Norte trabaja tres dias seguidos con la misma gente, dos en SOLEDAD y uno
    en MALAMBO. Sur trabaja uno, en SABANAGRANDE. Ninguna jornada tiene lider
    del dia, para que la gente sea solo la de los integrantes.
    """
    from campo.tasks import _ahora_local

    hoy = _ahora_local(org_a).date()
    soledad = ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")
    malambo = ZonaOperativa.objects.create(org=org_a, nombre="MALAMBO")
    sabanagrande = ZonaOperativa.objects.create(org=org_a, nombre="SABANAGRANDE")
    norte = Cuadrilla.objects.create(org=org_a, nombre="Norte", lider=admin_profile)
    norte.zonas_habituales.set([soledad])
    sur = Cuadrilla.objects.create(org=org_a, nombre="Sur")
    ana = PersonaDeCampo.objects.create(org=org_a, nombre="Ana")
    beto = PersonaDeCampo.objects.create(org=org_a, nombre="Beto")
    carla = PersonaDeCampo.objects.create(org=org_a, nombre="Carla")
    _jornada(org_a, norte, hoy - timedelta(days=2), [soledad], [ana, beto],
             notas="Llamar a Zoraida al 3113683499")
    _jornada(org_a, norte, hoy - timedelta(days=1), [soledad], [ana, beto])
    _jornada(org_a, norte, hoy, [malambo], [ana, beto])
    _jornada(org_a, sur, hoy - timedelta(days=2), [sabanagrande], [carla],
             labor="instalacion")
    return hoy


def test_a_cuenta_lo_de_cada_cuadrilla(org_a, armado):
    salida = _correr(org_a)

    assert "4 jornadas en 3 dias" in salida
    norte = _fila(salida, "1", "Norte")
    assert "correctivo (3)" in norte and "SOLEDAD (2)" in norte
    assert "Ana (3)" in norte and "Beto (3)" in norte
    assert "instalacion (1)" in _fila(salida, "1", "Sur")


def test_b_cuenta_quien_va_con_quien(org_a, armado):
    salida = _correr(org_a)

    fila = _fila(salida, "2", "Ana + Beto")
    assert fila.split()[3] == "3", fila
    assert "Norte (3)" in fila


def test_c_cuenta_cuanto_se_repite_el_dia(org_a, armado):
    fila = _fila(_correr(org_a), "3", "Norte")

    #  misma gente, mismas zonas, misma labor
    assert "2 de 2" in fila and "1 de 2" in fila, fila


def test_d_cada_zona_dice_cuantos_dias_y_quien_la_tiene_habitual(org_a, armado):
    salida = _correr(org_a)

    soledad = _fila(salida, "5", "SOLEDAD")
    assert soledad.split()[1] == "2" and "Norte (2)" in soledad
    assert soledad.rstrip().endswith("Norte")
    assert _fila(salida, "5", "SABANAGRANDE").rstrip().endswith("ninguna")


def test_e_no_saca_las_notas_ni_escribe_nada(org_a, armado):
    antes = JornadaDeCuadrilla.objects.count()

    salida = _correr(org_a)

    assert "Zoraida" not in salida and "3113683499" not in salida
    assert JornadaDeCuadrilla.objects.count() == antes


def test_f_no_mezcla_otra_empresa_y_respeta_el_rango(org_a, org_b, armado):
    from conftest import set_rls_context

    set_rls_context(org_b)
    ajena = Cuadrilla.objects.create(org=org_b, nombre="Ajena")
    _jornada(org_b, ajena, armado, [], [PersonaDeCampo.objects.create(
        org=org_b, nombre="Desconocido")])
    set_rls_context(org_a)

    salida = _correr(org_a, dias=1)

    assert "Ajena" not in salida and "Desconocido" not in salida
    assert "1 jornadas en 1 dias" in salida, "con --dias 1 solo entra hoy"


def test_g_sin_jornadas_lo_dice(org_a):
    assert "no hay ninguna jornada armada" in _correr(org_a)
