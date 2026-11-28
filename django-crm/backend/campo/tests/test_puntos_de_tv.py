"""
LOS PUNTOS DE TV DE UN TIPO DE TRABAJO  --  26/11/2026

El usuario: «unos botones preguntando cuantos puntos de TV; 1 punto lleva 2
conectores coaxiales, 2 puntos 6 conectores y un spliter de dos; preguntar si
utilizo el cable de la empresa y cuantos metros; como maximo 5». Ver
`campo/puntos_de_tv.py`. La cuenta la hace la app; aca se prueba lo que la
empresa guarda y lo que viaja.
"""
import pytest

from campo import puntos_de_tv as TV
from campo.models import (AsignacionTrabajo, MaterialCatalogo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tipo(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra",
                                 nombre="Instalación de fibra", labor="instalacion")
    WorkTypeVersion.objects.create(work_type=wt, version=1, schema_version=1,
                                   estado=WorkTypeVersion.PUBLICADA,
                                   esquema={"campos": [], "evidencias": []})
    return wt


@pytest.fixture
def catalogo(org_a):
    for codigo, nombre, unidad in (("CONCOAX", "Conector coaxial RG6", "unidades"),
                                   ("SPL2", "Spliter 2 salidas", "unidades"),
                                   ("SPL3", "Spliter 3 salidas", "unidades"),
                                   ("SPL4", "Spliter 4 salidas", "unidades"),
                                   ("RG6", "Cable coaxial RG6", "metros")):
        MaterialCatalogo.objects.create(org=org_a, codigo=codigo, nombre=nombre, unidad=unidad)


RAPILINK = {"activo": True, "conector": "CONCOAX", "conectores_por_punto": 2,
            "conectores_de_entrada": 2, "maximo_de_puntos": 5, "cable": "RG6",
            "spliters": [{"codigo": "SPL4", "salidas": 4}, {"codigo": "spl2", "salidas": 2},
                         {"codigo": "SPL3", "salidas": "3"}, {"codigo": "", "salidas": ""}]}


def test_a1_se_guarda_y_viaja_con_los_spliters_ordenados_por_salidas(org_a, tipo, catalogo):
    TV.guardar(org_a, tipo, RAPILINK)
    d = TV.de_tipo(org_a, tipo)
    assert d["conector"] == {"codigo": "CONCOAX", "nombre": "Conector coaxial RG6"}
    assert (d["conectores_por_punto"], d["conectores_de_entrada"], d["maximo_de_puntos"]) == (2, 2, 5)
    assert d["cable"]["codigo"] == "RG6"
    assert [(s["codigo"], s["salidas"]) for s in d["spliters"]] == [("SPL2", 2), ("SPL3", 3), ("SPL4", 4)], \
        "con el código como está en el catálogo, y la fila vacía ignorada"


def test_a2_apagado_o_sin_configurar_no_viaja_nada(org_a, tipo, catalogo):
    assert TV.de_tipo(org_a, tipo) is None
    TV.guardar(org_a, tipo, {**RAPILINK, "activo": False})
    assert TV.de_tipo(org_a, tipo) is None
    assert TV.para_el_editor(org_a, tipo)["conector"] == "CONCOAX", "el editor sí lo ve, apagado"


@pytest.mark.parametrize("cambio,dice", [
    ({"conector": ""}, "Falta el conector"),
    ({"conector": "NOEXISTE"}, "no están en el catálogo"),
    ({"spliters": [{"codigo": "SPL2", "salidas": 2}, {"codigo": "spl2", "salidas": 2}]}, "dos veces"),
    ({"spliters": [{"codigo": "SPL2", "salidas": 1}]}, "va de 2 a 32"),
    ({"maximo_de_puntos": 0}, "va de 1 a 10"),
    ({"conectores_por_punto": "dos"}, "número entero"),
    ({"conectores_de_entrada": True}, "no se entiende"),
])
def test_b1_lo_mal_escrito_se_rechaza(org_a, tipo, catalogo, cambio, dice):
    with pytest.raises(TV.PuntosDeTvInvalido, match=dice):
        TV.guardar(org_a, tipo, {**RAPILINK, **cambio})


def test_c1_por_http_escribe_gestion_y_lo_ve_el_editor(admin_client, user_client, tipo, catalogo):
    url = f"/api/campo/plantillas/{tipo.id}/puntos-de-tv/"
    assert user_client.put(url, RAPILINK, format="json").status_code == 403
    r = admin_client.put(url, RAPILINK, format="json")
    assert r.status_code == 200, r.content
    assert admin_client.get(f"/api/campo/plantillas/{tipo.id}/").json()["puntos_de_tv"]["conector"] == "CONCOAX"
    r = admin_client.put(url, {**RAPILINK, "cable": "NOEXISTE"}, format="json")
    assert r.status_code == 400 and "NOEXISTE" in r.json()["detalle"]


def test_c2_LLEGA_CON_LA_ORDEN_al_telefono(user_client, user_profile, org_a, tipo, catalogo):
    TV.guardar(org_a, tipo, RAPILINK)
    o = OrdenTrabajo.objects.create(org=org_a, numero=601, tipo_trabajo_version=tipo.versions.first(),
                                    cliente_nombre="CLIENTE", estado_operativo=OrdenTrabajo.ASIGNADA,
                                    revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico_lider", es_principal=True)
    d = user_client.get(f"/api/campo/trabajos/{o.id}/").json()
    assert d["tipo"]["puntos_de_tv"]["maximo_de_puntos"] == 5
    assert [s["salidas"] for s in d["tipo"]["puntos_de_tv"]["spliters"]] == [2, 3, 4]
