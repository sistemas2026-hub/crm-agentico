# -*- coding: utf-8 -*-
"""
================================================================================
 ZONAS OPERATIVAS  --  que un barrio sin mapear se note en vez de desaparecer
================================================================================

Se afirma sobre el EFECTO: que la misma localidad escrita de varias formas caiga
en la misma zona, que una sin mapear devuelva `None` --y no la primera zona que
aparezca-- y que una zona dada de baja deje de resolver.
"""

import datetime as dt

import pytest

from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla
from campo.zonas import AliasDeZona, ZonaOperativa, normalizar_localidad, zona_de

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="LA ESPERANZA")
    return z


@pytest.fixture
def sur(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Sur")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="EL CARMEN")
    return z


def test_a_un_barrio_resuelve_a_su_zona(org_a, norte):
    assert zona_de(org_a, "MARTHA GISELA").nombre == "Norte"
    assert zona_de(org_a, "LA ESPERANZA").nombre == "Norte"


def test_b_la_misma_localidad_escrita_distinto_cae_en_la_misma_zona(org_a, norte):
    """El texto llega del proveedor y viene de varias formas."""
    for forma in ("martha gisela", "  MARTHA   GISELA  ", "Martha Gisela"):
        assert zona_de(org_a, forma).nombre == "Norte", forma


def test_c_un_barrio_SIN_MAPEAR_devuelve_None(org_a, norte, sur):
    """El caso que importa: no puede caer en la primera zona que aparezca.

    Una orden sin zona no se puede repartir por zona, y devolver cualquiera la
    mandaria a la cuadrilla equivocada en vez de dejarla pendiente.
    """
    assert zona_de(org_a, "VILLA NUEVA") is None


def test_d_sin_localidad_tampoco_se_adivina(org_a, norte):
    assert zona_de(org_a, "") is None
    assert zona_de(org_a, "   ") is None
    assert zona_de(org_a, None) is None


def test_e_una_zona_dada_de_baja_deja_de_resolver(org_a, norte):
    """Sus jornadas viejas la siguen referenciando; lo que para es el reparto."""
    norte.activa = False
    norte.save()
    assert zona_de(org_a, "MARTHA GISELA") is None


def test_f_un_barrio_no_puede_estar_en_dos_zonas(org_a, norte, sur):
    """Si estuviera, el reparto dejaria de ser reproducible."""
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        AliasDeZona.objects.create(
            org=org_a, zona=sur, localidad="MARTHA GISELA"
        )


def test_g_la_zona_de_OTRA_empresa_no_resuelve(org_a, org_b, norte):
    assert zona_de(org_b, "MARTHA GISELA") is None


def test_h_una_jornada_puede_cubrir_varias_zonas(org_a, norte, sur):
    """Una cuadrilla cubre mas de una zona en un dia flojo."""
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set([norte, sur])

    assert {z.nombre for z in j.zonas.all()} == {"Norte", "Sur"}


def test_i_sin_zonas_NO_significa_todas(org_a):
    """Con zona dura, una cuadrilla sin zona no recibe trabajo por zona."""
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    assert j.zonas.count() == 0


def test_j_normalizar_no_quita_tildes(org_a):
    """A proposito: dos formas con y sin tilde son dos alias, no una.

    Decidirlo por el sistema esconderia el caso en vez de resolverlo.
    """
    assert normalizar_localidad(" bogotá  centro ") == "BOGOTÁ CENTRO"
