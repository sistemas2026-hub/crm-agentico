"""
EL MATERIAL QUE SE PRECARGA EN UN TIPO DE TRABAJO  --  26/11/2026

El usuario: «material utilizado, que sea precargado: en una instalación se
utilizan 2 conectores APC, una ONU, dos tensores, un precinto, dos chazos y dos
tornillos; las grapas y la fibra son variadas». Ver `campo/material_habitual.py`.

  A  la lista se guarda, se lee en su orden, y una línea sin cantidad es «la
     escribe el técnico»
  B  lo que no se puede guardar se rechaza con su porqué
  C  sacar un material de la lista no borra su regla
  D  por HTTP: escribe gestión, y la lista llega con la orden al teléfono
"""
import pytest

from campo import material_habitual as MH
from campo.models import (AsignacionTrabajo, MaterialCatalogo, OrdenTrabajo,
                          ReglaDeConsumo, WorkType, WorkTypeVersion)

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
    for codigo, nombre, clase in (("SCAPC", "Conector SC/APC", MaterialCatalogo.CONSUMIBLE),
                                  ("ONU", "ONU", MaterialCatalogo.SERIALIZADO),
                                  ("TENSOR", "Tensor", MaterialCatalogo.CONSUMIBLE),
                                  ("GRAPA", "Grapa", MaterialCatalogo.CONSUMIBLE),
                                  ("DROP", "Fibra drop", MaterialCatalogo.CONSUMIBLE)):
        MaterialCatalogo.objects.create(org=org_a, codigo=codigo, nombre=nombre,
                                        clase=clase, unidad="unidades")


INSTALACION = [{"codigo": "SCAPC", "cantidad": 2}, {"codigo": "ONU", "cantidad": 1},
               {"codigo": "TENSOR", "cantidad": 2}, {"codigo": "GRAPA", "cantidad": None},
               {"codigo": "DROP", "cantidad": "", "campo": " Metros de fibra usados "}]


# =========================================================================== #
#  A. GUARDAR Y LEER
# =========================================================================== #
def test_a1_la_lista_se_guarda_y_se_lee_EN_SU_ORDEN(org_a, tipo, catalogo):
    lista = MH.guardar(org_a, tipo, INSTALACION)
    assert [(x["codigo"], x["cantidad"]) for x in lista] == [
        ("SCAPC", 2), ("ONU", 1), ("TENSOR", 2), ("GRAPA", None), ("DROP", None)], \
        "sin cantidad = la escribe el técnico"
    assert lista[1]["clase"] == "serializado", "la app sabe que la ONU pide su serie"
    assert lista[4]["campo"] == "Metros de fibra usados" and lista[0]["campo"] == "", \
        "la fibra sale de lo que se escribió en ese campo (26/11/2026)"


def test_a2_reordenar_cambia_el_orden_y_no_duplica(org_a, tipo, catalogo):
    MH.guardar(org_a, tipo, INSTALACION)
    lista = MH.guardar(org_a, tipo, list(reversed(INSTALACION)))
    assert [x["codigo"] for x in lista] == ["DROP", "GRAPA", "TENSOR", "ONU", "SCAPC"]
    assert ReglaDeConsumo.objects.filter(org=org_a, work_type=tipo).count() == 5


def test_a3_la_cantidad_precargada_ES_la_habitual_que_ya_avisaba(org_a, tipo, catalogo):
    MH.guardar(org_a, tipo, INSTALACION)
    r = ReglaDeConsumo.objects.get(org=org_a, work_type=tipo, material__codigo="SCAPC")
    assert r.cantidad_habitual == 2 and r.precargar is True


def test_a4_otro_tipo_de_trabajo_no_ve_la_lista(org_a, tipo, catalogo):
    MH.guardar(org_a, tipo, INSTALACION)
    otro = WorkType.objects.create(org=org_a, codigo="correctivo", nombre="Correctivo")
    assert MH.de_tipo(org_a, otro) == []


# =========================================================================== #
#  B. LO QUE NO SE GUARDA
# =========================================================================== #
@pytest.mark.parametrize("lineas,dice", [
    ([{"codigo": "NOEXISTE", "cantidad": 1}], "no están en el catálogo"),
    ([{"codigo": "SCAPC", "cantidad": 1}, {"codigo": "scapc", "cantidad": 2}], "dos veces"),
    ([{"codigo": "SCAPC", "cantidad": 0}], "mayor que cero"),
    ([{"codigo": "SCAPC", "cantidad": -2}], "mayor que cero"),
    ([{"codigo": "SCAPC", "cantidad": "dos"}], "no es un número"),
    ([{"codigo": "SCAPC", "cantidad": True}], "no se entiende"),
    ([{"cantidad": 1}], "le falta el material"),
    ("SCAPC", "no se entiende"),
    ([{"codigo": "DROP", "campo": "x" * 121}], "demasiado largo"),
    ([{"codigo": "SCAPC"}] * 31, "más de 30"),
])
def test_b1_lo_mal_escrito_se_rechaza_y_no_toca_nada(org_a, tipo, catalogo, lineas, dice):
    MH.guardar(org_a, tipo, [{"codigo": "TENSOR", "cantidad": 2}])
    with pytest.raises(MH.MaterialHabitualInvalido, match=dice):
        MH.guardar(org_a, tipo, lineas)
    assert [x["codigo"] for x in MH.de_tipo(org_a, tipo)] == ["TENSOR"]


# =========================================================================== #
#  C. SACAR UN MATERIAL NO BORRA SU REGLA
# =========================================================================== #
def test_c1_lo_que_sale_de_la_lista_conserva_su_regla_para_avisar(org_a, tipo, catalogo):
    MH.guardar(org_a, tipo, INSTALACION)
    r = ReglaDeConsumo.objects.get(org=org_a, work_type=tipo, material__codigo="SCAPC")
    r.maximo = 6
    r.save(update_fields=["maximo"])
    MH.guardar(org_a, tipo, [{"codigo": "ONU", "cantidad": 1}])
    r.refresh_from_db()
    assert r.precargar is False and r.maximo == 6, "el máximo que alguien puso sigue avisando"
    assert [x["codigo"] for x in MH.de_tipo(org_a, tipo)] == ["ONU"]


# =========================================================================== #
#  D. POR HTTP
# =========================================================================== #
def _url(tipo):
    return f"/api/campo/plantillas/{tipo.id}/material-habitual/"


def test_d1_gestion_la_guarda_y_la_ve_el_editor(admin_client, tipo, catalogo):
    r = admin_client.put(_url(tipo), {"lineas": INSTALACION}, format="json")
    assert r.status_code == 200, r.content
    assert [x["codigo"] for x in r.json()["material_habitual"]][:2] == ["SCAPC", "ONU"]
    d = admin_client.get(f"/api/campo/plantillas/{tipo.id}/").json()
    assert [x["codigo"] for x in d["material_habitual"]] == ["SCAPC", "ONU", "TENSOR", "GRAPA", "DROP"]


def test_d2_un_tecnico_no_la_cambia(user_client, admin_client, tipo, catalogo):
    admin_client.put(_url(tipo), {"lineas": INSTALACION}, format="json")
    r = user_client.put(_url(tipo), {"lineas": []}, format="json")
    assert r.status_code == 403
    assert len(user_client.get(_url(tipo)).json()["material_habitual"]) == 5


def test_d3_un_error_se_le_dice_a_quien_edita(admin_client, tipo, catalogo):
    r = admin_client.put(_url(tipo), {"lineas": [{"codigo": "NOEXISTE"}]}, format="json")
    assert r.status_code == 400
    assert "NOEXISTE" in r.json()["detalle"]


def test_d4_LA_LISTA_LLEGA_CON_LA_ORDEN_al_telefono(user_client, user_profile, org_a, tipo, catalogo):
    MH.guardar(org_a, tipo, INSTALACION)
    o = OrdenTrabajo.objects.create(org=org_a, numero=501,
                                    tipo_trabajo_version=tipo.versions.first(),
                                    cliente_nombre="CLIENTE", estado_operativo=OrdenTrabajo.ASIGNADA,
                                    revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico_lider",
                                     es_principal=True)
    r = user_client.get(f"/api/campo/trabajos/{o.id}/")
    assert r.status_code == 200, r.content
    lista = r.json()["tipo"]["material_habitual"]
    assert [(x["codigo"], x["cantidad"]) for x in lista][:3] == [("SCAPC", 2), ("ONU", 1), ("TENSOR", 2)]
