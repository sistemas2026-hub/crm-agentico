# -*- coding: utf-8 -*-
"""
Plantillas de kit: la lista que se repite todas las mañanas.

QUE SE AFIRMA ACA
-----------------
Que son POR EMPRESA --la de una no aparece en la otra-- y que una plantilla NO
mueve material: solo describe lo que se suele entregar. Lo que de verdad salio
queda en el acta del despacho, y eso no cambia porque alguien edite la plantilla
despues.

La cuenta de "cuanto falta entregar" --lo que pide el kit menos lo que el tecnico
ya tiene encima-- se hace en la pantalla, que es donde vive la sugerencia, y por
eso no se prueba aca: no toca la base. Lo que si se prueba es la base sobre la que
esa cuenta se apoya, que es la custodia.
"""

from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import PlantillaDeKit
from campo.models import MaterialCatalogo
from campo.services import inventario as inv
from campo.services import inventario_operacion as op

pytestmark = pytest.mark.django_db

PLANTILLAS = "/api/campo/inventario/plantillas/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC", unidad="unidades"
    )


@pytest.fixture
def fibra(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="FIB-DROP", nombre="Fibra drop",
        clase=MaterialCatalogo.BOBINA, unidad="m",
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei",
        clase=MaterialCatalogo.SERIALIZADO,
    )


# ---------------------------------------------------------------------------
# Lo que define la funcion
# ---------------------------------------------------------------------------

def test_una_plantilla_se_arma_y_se_lee_con_sus_lineas(admin_client, org_a,
                                                        conector, fibra):
    r = admin_client.post(PLANTILLAS, {
        "nombre": "Kit instalación FTTH",
        "descripcion": "lo de una cuadrilla un día normal",
        "lineas": [
            {"material": "CON-SC-APC", "cantidad": "24"},
            {"material": "FIB-DROP", "cantidad": "300"},
        ],
    }, format="json")
    assert r.status_code == 201, r.content

    leidas = admin_client.get(PLANTILLAS).json()["plantillas"]
    assert len(leidas) == 1
    p = leidas[0]
    assert p["nombre"] == "Kit instalación FTTH"
    # Las lineas viajan con la plantilla: son pocas y chicas, y traerlas aparte
    # obligaria a una consulta por plantilla para pintar un desplegable.
    assert {l["material"] for l in p["lineas"]} == {"CON-SC-APC", "FIB-DROP"}
    assert [l for l in p["lineas"] if l["material"] == "FIB-DROP"][0]["clase"] == "bobina"


def test_la_plantilla_de_una_empresa_no_existe_para_otra(admin_client, org_b_client,
                                                          org_a, conector):
    """La razon por la que esto es una tabla por organizacion.

    Lo que lleva un kit en una empresa no es lo que lleva en otra: depende del
    tipo de acometida y de como cada ISP arma sus cuadrillas.
    """
    admin_client.post(PLANTILLAS, {
        "nombre": "Kit A", "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json")

    assert org_b_client.get(PLANTILLAS).json()["plantillas"] == []


def test_una_plantilla_NO_mueve_material(admin_client, org_a, conector, bodega):
    """Es un borrador, no un despacho.

    Si crear la plantilla moviera algo, armar el kit del lunes descontaria stock
    sin que nadie se hubiera llevado nada.
    """
    inv.registrar_entrada(org=org_a, material=conector, cantidad=100,
                          ubicacion_destino=bodega, origen_ref="R-1")

    admin_client.post(PLANTILLAS, {
        "nombre": "Kit sin efecto",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json")

    assert inv.existencia(bodega, conector) == Decimal("100")


def test_editarla_reescribe_las_lineas_enteras(admin_client, org_a, conector, fibra):
    creada = admin_client.post(PLANTILLAS, {
        "nombre": "Kit", "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json").json()

    r = admin_client.put(f"{PLANTILLAS}{creada['id']}/", {
        "nombre": "Kit",
        "lineas": [{"material": "FIB-DROP", "cantidad": "500"}],
    }, format="json")
    assert r.status_code == 200, r.content

    p = admin_client.get(PLANTILLAS).json()["plantillas"][0]
    # El conector ya no esta: las lineas se reemplazan, no se parchean.
    assert [l["material"] for l in p["lineas"]] == ["FIB-DROP"]


def test_editar_una_plantilla_no_cambia_lo_que_ya_se_despacho(
    admin_client, org_a, conector, bodega, user_profile
):
    """Lo que salio quedo en el acta, y el acta no se reescribe sola.

    Es la razon por la que una plantilla no necesita versionarse: no es el
    registro de nada, es una ayuda para cargar el formulario.
    """
    inv.registrar_entrada(org=org_a, material=conector, cantidad=100,
                          ubicacion_destino=bodega, origen_ref="R-2")
    creada = admin_client.post(PLANTILLAS, {
        "nombre": "Kit", "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json").json()

    inv.despachar(org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
                  acta="K-PLANTILLA", lineas=[{"material": conector, "cantidad": 24}])
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)

    admin_client.put(f"{PLANTILLAS}{creada['id']}/", {
        "nombre": "Kit", "lineas": [{"material": "CON-SC-APC", "cantidad": "2"}],
    }, format="json")

    assert inv.existencia(custodia, conector) == Decimal("24")


def test_darla_de_baja_no_la_borra(admin_client, org_a, conector):
    creada = admin_client.post(PLANTILLAS, {
        "nombre": "Kit viejo",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json").json()

    r = admin_client.delete(f"{PLANTILLAS}{creada['id']}/")
    assert r.status_code == 200, r.content

    # Ya no se ofrece...
    assert admin_client.get(PLANTILLAS).json()["plantillas"] == []
    # ...pero sigue existiendo, y se puede ver pidiendo todas.
    todas = admin_client.get(PLANTILLAS, {"todas": "1"}).json()["plantillas"]
    assert [p["nombre"] for p in todas] == ["Kit viejo"]
    assert PlantillaDeKit.objects.filter(org=org_a).count() == 1


# ---------------------------------------------------------------------------
# Lo que se niega, y con que codigo
# ---------------------------------------------------------------------------

def test_dos_plantillas_con_el_mismo_nombre_da_409(admin_client, org_a, conector):
    """409 y no 400: el dato esta bien escrito, el nombre ya esta tomado."""
    cuerpo = {"nombre": "Kit FTTH",
              "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}]}
    assert admin_client.post(PLANTILLAS, cuerpo, format="json").status_code == 201
    r = admin_client.post(PLANTILLAS, cuerpo, format="json")
    assert r.status_code == 409, r.content
    assert "ya hay una plantilla" in r.json()["detail"].lower()


def test_una_plantilla_sin_materiales_no_se_guarda(admin_client, org_a):
    r = admin_client.post(PLANTILLAS, {"nombre": "Vacía", "lineas": []},
                          format="json")
    assert r.status_code == 409, r.content
    assert "sin materiales" in r.json()["detail"]


def test_el_mismo_material_dos_veces_lo_dice(admin_client, org_a, conector):
    """Y dice que hacer: poner la cantidad total en una sola linea."""
    r = admin_client.post(PLANTILLAS, {
        "nombre": "Kit repetido",
        "lineas": [
            {"material": "CON-SC-APC", "cantidad": "10"},
            {"material": "CON-SC-APC", "cantidad": "14"},
        ],
    }, format="json")
    assert r.status_code == 409, r.content
    assert "dos veces" in r.json()["detail"]


def test_una_linea_sin_cantidad_lo_dice_con_el_codigo(admin_client, org_a, conector):
    r = admin_client.post(PLANTILLAS, {
        "nombre": "Kit sin cantidad",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "0"}],
    }, format="json")
    assert r.status_code == 409, r.content
    assert "CON-SC-APC" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

def test_un_tecnico_raso_puede_LEER_las_plantillas(user_client, org_a, conector,
                                                    admin_client):
    """Saber que lleva un kit no mueve nada, y le sirve para planificar el dia."""
    admin_client.post(PLANTILLAS, {
        "nombre": "Kit", "lineas": [{"material": "CON-SC-APC", "cantidad": "24"}],
    }, format="json")

    r = user_client.get(PLANTILLAS)
    assert r.status_code == 200, r.content
    assert len(r.json()["plantillas"]) == 1


def test_un_tecnico_raso_NO_puede_armar_una(user_client, org_a, conector):
    """Armar el kit es decidir que se entrega: eso es gestion o bodega."""
    r = user_client.post(PLANTILLAS, {
        "nombre": "Kit propio",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "99"}],
    }, format="json")
    assert r.status_code == 403, r.content
