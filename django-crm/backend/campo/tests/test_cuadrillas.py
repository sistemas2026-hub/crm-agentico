# -*- coding: utf-8 -*-
"""
================================================================================
 LA CUADRILLA Y SU JORNADA  --  que la composicion del martes no pise la del lunes
================================================================================

Lo que se afirma es el EFECTO: que un cambio de labor o de auxiliares deje el
dia anterior intacto, y que una persona no pueda contarse dos veces el mismo
dia. No que los modelos existan.
"""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from campo.cuadrillas import Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
MARTES = dt.date(2026, 10, 6)


@pytest.fixture
def cuadrilla(org_a):
    return Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")


def _jornada(org, cuadrilla, fecha, labor):
    return JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=cuadrilla, fecha=fecha, labor=labor
    )


def _persona(profile):
    """La `PersonaDeCampo` de esa cuenta, creandola si hace falta.

    El integrante de una jornada ya no es un `Profile`: un auxiliar sin
    celular no puede tener cuenta y aun asi integra la cuadrilla. Ver
    `campo.cuadrillas.PersonaDeCampo`.
    """
    from campo.cuadrillas import PersonaDeCampo
    persona, _ = PersonaDeCampo.objects.get_or_create(
        org=profile.org, profile=profile,
        defaults={"nombre": getattr(profile.user, "name", "") or "Sin nombre"},
    )
    return persona


def test_a_cambiar_de_labor_no_pisa_el_dia_anterior(org_a, cuadrilla):
    """El caso que motivo separar la jornada de la cuadrilla."""
    _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.INSTALACION)
    _jornada(org_a, cuadrilla, MARTES, JornadaDeCuadrilla.CORRECTIVO)

    labores = {
        j.fecha: j.labor
        for j in JornadaDeCuadrilla.objects.filter(cuadrilla=cuadrilla)
    }
    assert labores[LUNES] == JornadaDeCuadrilla.INSTALACION
    assert labores[MARTES] == JornadaDeCuadrilla.CORRECTIVO


def test_b_cambiar_el_auxiliar_no_reescribe_quien_fue_ayer(
    org_a, cuadrilla, admin_profile, user_profile
):
    lunes = _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.INSTALACION)
    martes = _jornada(org_a, cuadrilla, MARTES, JornadaDeCuadrilla.INSTALACION)

    IntegranteDeJornada.objects.create(
        org=org_a, jornada=lunes, persona=_persona(admin_profile), rol="ayudante"
    )
    IntegranteDeJornada.objects.create(
        org=org_a, jornada=martes, persona=_persona(user_profile), rol="ayudante"
    )

    #  Por la CUENTA de la persona, no por el id del integrante: desde que el
    #  integrante es una `PersonaDeCampo`, su id ya no es el del `Profile`.
    del_lunes = [i.persona.profile_id for i in lunes.integrantes.all()]
    del_martes = [i.persona.profile_id for i in martes.integrantes.all()]
    assert del_lunes == [admin_profile.id]
    assert del_martes == [user_profile.id]


def test_c_una_cuadrilla_tiene_UNA_jornada_por_dia(org_a, cuadrilla):
    """Dos filas del mismo dia harian ambiguo que labor tenia."""
    from django.db import IntegrityError

    _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.INSTALACION)
    with pytest.raises(IntegrityError):
        _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.CORRECTIVO)


def test_d_una_persona_no_puede_estar_en_dos_cuadrillas_el_mismo_dia(
    org_a, cuadrilla, admin_profile
):
    """El error que se nota recien a la mañana siguiente.

    Las dos cuadrillas contarian con esa persona al repartir trabajo, y una se
    quedaria corta sin que nadie lo vea hasta que alguien no aparece.
    """
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    uno = _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.INSTALACION)
    dos = _jornada(org_a, otra, LUNES, JornadaDeCuadrilla.CORRECTIVO)

    IntegranteDeJornada.objects.create(
        org=org_a, jornada=uno, persona=_persona(admin_profile), rol="tecnico"
    )

    repetido = IntegranteDeJornada(
        org=org_a, jornada=dos, persona=_persona(admin_profile), rol="ayudante"
    )
    with pytest.raises(ValidationError) as e:
        repetido.full_clean()
    assert "Cuadrilla 1" in str(e.value), "el mensaje tiene que decir DONDE está"


def test_e_la_misma_persona_SI_puede_estar_otro_dia(
    org_a, cuadrilla, admin_profile
):
    """La guarda es por día: nadie queda atado a una cuadrilla para siempre."""
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    lunes = _jornada(org_a, cuadrilla, LUNES, JornadaDeCuadrilla.INSTALACION)
    martes = _jornada(org_a, otra, MARTES, JornadaDeCuadrilla.CORRECTIVO)

    IntegranteDeJornada.objects.create(
        org=org_a, jornada=lunes, persona=_persona(admin_profile), rol="tecnico"
    )
    cambio = IntegranteDeJornada(
        org=org_a, jornada=martes, persona=_persona(admin_profile), rol="tecnico"
    )
    cambio.full_clean()          # no levanta
    cambio.save()

    assert IntegranteDeJornada.objects.filter(persona=_persona(admin_profile)).count() == 2


def test_f_dos_cuadrillas_no_pueden_llamarse_igual(org_a, cuadrilla):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
