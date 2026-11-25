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


# ---------------------------------------------------------------------------
# La API: crear zonas y mapear localidades
# ---------------------------------------------------------------------------

ZONAS = "/api/campo/zonas/"


def test_k_crear_una_zona_y_mapearle_barrios(admin_client):
    r = admin_client.post(ZONAS, {"nombre": "Norte"}, format="json")
    assert r.status_code == 201, r.content
    zid = r.json()["id"]

    m = admin_client.put(
        f"{ZONAS}{zid}/localidades/",
        {"localidades": ["martha gisela", "LA ESPERANZA"]},
        format="json",
    )
    assert m.status_code == 200, m.content
    # Se guardan normalizadas: asi el mismo barrio no entra dos veces.
    assert sorted(m.json()["localidades"]) == ["LA ESPERANZA", "MARTHA GISELA"]


def test_l_mapear_dos_veces_deja_lo_mismo(admin_client):
    zid = admin_client.post(ZONAS, {"nombre": "Norte"},
                            format="json").json()["id"]
    cuerpo = {"localidades": ["MARTHA GISELA", "martha gisela"]}
    admin_client.put(f"{ZONAS}{zid}/localidades/", cuerpo, format="json")
    r = admin_client.put(f"{ZONAS}{zid}/localidades/", cuerpo, format="json")

    assert r.json()["localidades"] == ["MARTHA GISELA"], "no se duplica"


def test_m_un_barrio_de_otra_zona_se_rechaza_diciendo_cual(admin_client):
    """Si estuviera en dos, el reparto dejaria de ser reproducible."""
    norte = admin_client.post(ZONAS, {"nombre": "Norte"},
                              format="json").json()["id"]
    sur = admin_client.post(ZONAS, {"nombre": "Sur"},
                            format="json").json()["id"]
    admin_client.put(f"{ZONAS}{norte}/localidades/",
                     {"localidades": ["MARTHA GISELA"]}, format="json")

    r = admin_client.put(f"{ZONAS}{sur}/localidades/",
                         {"localidades": ["MARTHA GISELA"]}, format="json")
    assert r.status_code == 409
    assert "Norte" in r.json()["detail"], "tiene que decir en cual esta"


def test_n_quitar_un_barrio_es_mandar_la_lista_sin_el(admin_client):
    zid = admin_client.post(ZONAS, {"nombre": "Norte"},
                            format="json").json()["id"]
    admin_client.put(f"{ZONAS}{zid}/localidades/",
                     {"localidades": ["A", "B"]}, format="json")
    r = admin_client.put(f"{ZONAS}{zid}/localidades/",
                         {"localidades": ["A"]}, format="json")
    assert r.json()["localidades"] == ["A"]


def test_o_dos_zonas_no_se_llaman_igual(admin_client):
    admin_client.post(ZONAS, {"nombre": "Norte"}, format="json")
    r = admin_client.post(ZONAS, {"nombre": "Norte"}, format="json")
    assert r.status_code == 409


def test_p_un_tecnico_no_puede_tocar_zonas(user_client):
    r = user_client.post(ZONAS, {"nombre": "La mia"}, format="json")
    assert r.status_code == 403
    assert user_client.get(ZONAS).status_code == 200, "pero SI puede mirarlas"


# ---------------------------------------------------------------------------
# ELIMINAR UNA ZONA  --  pedido del usuario, 25/11/2026
# ---------------------------------------------------------------------------
# Dos desenlaces, y se afirma sobre el EFECTO de cada uno: la que nadie cubrio
# desaparece con sus barrios; la que tiene jornadas deja de verse pero la
# jornada conserva su zona. En los dos, sus barrios quedan libres.

def test_q_eliminar_una_zona_sin_jornadas_la_borra_con_sus_barrios(
    admin_client, org_a, norte
):
    r = admin_client.delete(f"{ZONAS}{norte.id}/")
    assert r.status_code == 200, r.content
    assert r.json()["eliminada"] is True
    assert r.json()["dada_de_baja"] is False
    assert r.json()["barrios_liberados"] == 2

    assert not ZonaOperativa.objects.filter(id=norte.id).exists()
    assert not AliasDeZona.objects.filter(org=org_a).exists()
    assert zona_de(org_a, "MARTHA GISELA") is None, "el barrio deja de resolver"
    todas = admin_client.get(ZONAS, {"todas": "1"}).json()["zonas"]
    assert todas == [], "tampoco queda como zona dada de baja"


def test_r_los_barrios_de_la_eliminada_se_pueden_dar_a_otra(
    admin_client, norte, sur
):
    """Sin esto el mapeo daria 409 nombrando una zona que ya no existe."""
    admin_client.delete(f"{ZONAS}{norte.id}/")

    r = admin_client.put(f"{ZONAS}{sur.id}/localidades/",
                         {"localidades": ["EL CARMEN", "MARTHA GISELA"]},
                         format="json")
    assert r.status_code == 200, r.content
    assert sorted(r.json()["localidades"]) == ["EL CARMEN", "MARTHA GISELA"]


def test_s_una_zona_con_jornadas_no_se_borra_se_da_de_baja(
    admin_client, org_a, norte, sur
):
    """Las jornadas viejas explican por que una cuadrilla fue a donde fue."""
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set([norte])

    r = admin_client.delete(f"{ZONAS}{norte.id}/")
    assert r.status_code == 200, r.content
    assert r.json()["eliminada"] is False
    assert r.json()["dada_de_baja"] is True
    assert r.json()["jornadas"] == 1

    # La jornada conserva su zona: es lo que el borrado le habria quitado.
    assert [z.nombre for z in j.zonas.all()] == ["Norte"]
    # Deja de verse y de resolver...
    assert [z["nombre"] for z in admin_client.get(ZONAS).json()["zonas"]] == ["Sur"]
    assert zona_de(org_a, "MARTHA GISELA") is None
    # ...y sus barrios quedan libres para otra zona.
    r = admin_client.put(f"{ZONAS}{sur.id}/localidades/",
                         {"localidades": ["EL CARMEN", "MARTHA GISELA"]},
                         format="json")
    assert r.status_code == 200, r.content


def test_t_eliminar_la_saca_de_las_zonas_habituales_de_la_cuadrilla(
    admin_client, org_a, norte, sur
):
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    c.zonas_habituales.set([norte, sur])

    admin_client.delete(f"{ZONAS}{norte.id}/")

    assert [z.nombre for z in c.zonas_habituales.all()] == ["Sur"]


def test_u_la_dada_de_baja_al_eliminar_tambien_sale_de_lo_habitual(
    admin_client, org_a, norte
):
    """Una zona que ya no se ve no puede seguir armando el dia de nadie."""
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    c.zonas_habituales.set([norte])
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set([norte])

    admin_client.delete(f"{ZONAS}{norte.id}/")

    assert list(c.zonas_habituales.all()) == []
    assert ZonaOperativa.objects.get(id=norte.id).activa is False


def test_v_crear_de_nuevo_una_eliminada_con_historia_la_trae_de_vuelta(
    admin_client, org_a, norte
):
    """El nombre sigue ocupado por la zona dada de baja: sin esto, 409."""
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set([norte])
    admin_client.delete(f"{ZONAS}{norte.id}/")

    r = admin_client.post(ZONAS, {"nombre": "Norte"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["id"] == str(norte.id), "es la misma zona, no una gemela"
    assert r.json()["activa"] is True
    assert r.json()["localidades"] == [], "vuelve sin barrios: quedaron libres"
    assert ZonaOperativa.objects.filter(org=org_a, nombre="Norte").count() == 1


def test_w_un_tecnico_no_puede_eliminar_zonas(user_client, org_a, norte):
    r = user_client.delete(f"{ZONAS}{norte.id}/")
    assert r.status_code == 403
    assert ZonaOperativa.objects.filter(id=norte.id, activa=True).exists()
    assert AliasDeZona.objects.filter(zona=norte).count() == 2


def test_x_la_zona_de_OTRA_empresa_no_se_elimina(org_b_client, norte):
    r = org_b_client.delete(f"{ZONAS}{norte.id}/")
    assert r.status_code == 404
    assert ZonaOperativa.objects.filter(id=norte.id, activa=True).exists()
    assert AliasDeZona.objects.filter(zona=norte).count() == 2

