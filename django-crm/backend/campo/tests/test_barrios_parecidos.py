# -*- coding: utf-8 -*-
"""
================================================================================
 UN BARRIO CON UNA LETRA DE MAS O DE MENOS SE SUGIERE, NO SE CORRIGE
================================================================================

Pedido del usuario (13/10/2026): si al despachar se equivocan en una letra de
un barrio que ya esta, que se pueda llevar al correcto. Decidido SUGERIR y no
corregir solo: dos barrios reales pueden diferir en una letra, y una orden
mandada callada a la cuadrilla equivocada es peor que una en `sin_zona`.

  A  una letra cambiada, faltante o de mas se sugiere, con su zona
  B  lo ya mapeado no sugiere nada; lo muy distinto tampoco
  C  las tildes NO se igualan (la decision de `normalizar_localidad`)
  D  `GET /campo/zonas/conocidas/?q=` dice si coincide y a cual se parece
  E  en el reparto, una orden `sin_zona` trae el barrio mapeado parecido

    pytest campo/tests/test_barrios_parecidos.py
================================================================================
"""

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.zonas import AliasDeZona, ZonaOperativa, parecidas

pytestmark = pytest.mark.django_db


@pytest.fixture
def mapeados(org_a):
    norte = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    for b in ("CACARAMOA", "LA ESPERANZA", "BOGOTÁ"):
        AliasDeZona.objects.create(org=org_a, zona=norte, localidad=b)
    return norte


@pytest.mark.parametrize("escrito", ["CACARMOA", "cacaramoa ", "CACARAMMOA", "CACARAMOE"])
def test_a_una_letra_se_sugiere_con_su_zona(org_a, mapeados, escrito):
    s = parecidas(org_a, escrito)
    if escrito.strip().upper() == "CACARAMOA":
        assert s == []                    # ya esta: normaliza mayusculas y espacios
    else:
        assert s and s[0]["localidad"] == "CACARAMOA"
        assert s[0]["zona"] == "Norte"
        assert s[0]["zona_id"] == str(mapeados.id)


def test_b_lo_mapeado_y_lo_muy_distinto_no_sugieren(org_a, mapeados):
    assert parecidas(org_a, "LA ESPERANZA") == []
    assert parecidas(org_a, "VILLA DEL ROSARIO") == []


def test_c_las_tildes_no_se_igualan(org_a, mapeados):
    """«BOGOTA» no es «BOGOTÁ» para el mapeo: puede sugerirse, nunca coincidir."""
    from campo.zonas import zona_de

    assert zona_de(org_a, "BOGOTA") is None


def test_d_el_endpoint_dice_si_coincide_y_a_cual_se_parece(admin_client, mapeados):
    r = admin_client.get("/api/campo/zonas/conocidas/?q=CACARMOA").json()
    assert r["exacta"] is False
    assert r["parecidas"][0]["localidad"] == "CACARAMOA"
    assert {"localidad": "LA ESPERANZA", "zona": "Norte"} in r["localidades"]

    r = admin_client.get("/api/campo/zonas/conocidas/?q=cacaramoa").json()
    assert r["exacta"] is True and r["parecidas"] == []


def test_e_el_reparto_trae_el_parecido_de_una_orden_sin_zona(
        admin_client, org_a, mapeados):
    wt = WorkType.objects.create(org=org_a, codigo="c", nombre="C",
                                 labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    OrdenTrabajo.objects.create(org=org_a, numero=8001, tipo_trabajo_version=v,
                                cliente_nombre="X", zona="CACARMOA")
    r = admin_client.get("/api/campo/cuadrillas/reparto/?fecha=2026-10-14")
    assert r.status_code == 200, r.content
    fila = r.json()["sin_zona"][0]
    assert fila["parecida"]["localidad"] == "CACARAMOA"
