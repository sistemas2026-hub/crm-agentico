# -*- coding: utf-8 -*-
"""
La API de Fase 2 y 3, y los codigos que devuelve.

POR QUE LAS PRUEBAS MIRAN EL CODIGO HTTP Y NO SOLO EL CUERPO
------------------------------------------------------------
    400  el dato esta mal escrito                 -> corregilo
    409  el estado del inventario no lo permite   -> mira el numero o el aparato

Con 400 para las dos cosas la pantalla no puede distinguir "escribiste mal la
cantidad" de "no queda material libre", y termina mostrando "no se pudo" para
todo. La distincion es la que hace que un mensaje sirva.
"""

from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import Proveedor, ReservaDeMaterial
from campo.models import MaterialCatalogo
from campo.services import inventario as inv
from campo.services import inventario_operacion as op

pytestmark = pytest.mark.django_db

LIBRE = "/api/campo/inventario/libre/"
RESERVAS = "/api/campo/inventario/reservas/"
TRASLADOS = "/api/campo/inventario/traslados/"
CONTEOS = "/api/campo/inventario/conteos/"
PROVEEDORES = "/api/campo/inventario/proveedores/"
COMPRAS = "/api/campo/inventario/compras/"
VALORIZACION = "/api/campo/inventario/valorizacion/"
REPORTES = "/api/campo/inventario/reportes/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def bodega_norte(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Norte"
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC", unidad="unidades"
    )


@pytest.fixture
def con_cien(org_a, bodega, conector):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    return conector


# ---------------------------------------------------------------------------
# Reservas y libre
# ---------------------------------------------------------------------------

def test_libre_devuelve_las_tres_cifras_juntas(admin_client, org_a, bodega,
                                               con_cien):
    """"Quedan 70" sin decir que hay 100 y 30 comprometidos no se entiende."""
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)

    r = admin_client.get(LIBRE, {"ubicacion": str(bodega.id)})
    assert r.status_code == 200
    fila = r.json()["materiales"][0]
    assert fila["existencia"] == "100.000"
    assert fila["reservado"] == "30"
    assert fila["libre"] == "70"


def test_reservar_por_la_api(admin_client, org_a, bodega, con_cien):
    r = admin_client.post(RESERVAS, {
        "ubicacion": str(bodega.id), "material": "CON-SC-APC", "cantidad": "25",
        "motivo": "instalaciones de mañana",
    }, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["libre_ahora"] == "75"


def test_reservar_mas_de_lo_libre_da_409(admin_client, org_a, bodega, con_cien):
    """409 y no 400: el dato esta bien, el material no alcanza."""
    admin_client.post(RESERVAS, {
        "ubicacion": str(bodega.id), "material": "CON-SC-APC", "cantidad": "90",
    }, format="json")
    r = admin_client.post(RESERVAS, {
        "ubicacion": str(bodega.id), "material": "CON-SC-APC", "cantidad": "30",
    }, format="json")
    assert r.status_code == 409, r.content
    assert "quedan 10" in r.json()["detail"]


def test_liberar_por_la_api_no_borra_la_reserva(admin_client, org_a, bodega,
                                                con_cien):
    reserva = op.reservar(org=org_a, ubicacion=bodega, material=con_cien,
                          cantidad=30)
    r = admin_client.post(
        f"{RESERVAS}{reserva.id}/liberar/", {"motivo": "se cayo la orden"},
        format="json")
    assert r.status_code == 200, r.content
    assert r.json()["libre_ahora"] == "100"
    assert ReservaDeMaterial.objects.filter(org=org_a).count() == 1


def test_las_reservas_se_listan_por_ubicacion(admin_client, org_a, bodega,
                                              con_cien):
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=12)
    r = admin_client.get(RESERVAS, {"ubicacion": str(bodega.id)})
    assert r.status_code == 200
    assert len(r.json()["reservas"]) == 1
    assert r.json()["reservas"][0]["cantidad"] == "12.000"


# ---------------------------------------------------------------------------
# Traslados
# ---------------------------------------------------------------------------

def test_trasladar_por_la_api(admin_client, org_a, bodega, bodega_norte,
                              con_cien):
    r = admin_client.post(TRASLADOS, {
        "ubicacion_origen": str(bodega.id),
        "ubicacion_destino": str(bodega_norte.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "20"}],
        "motivo": "reparto",
    }, format="json")
    assert r.status_code == 201, r.content
    assert inv.existencia(bodega, con_cien) == Decimal("80")
    assert inv.existencia(bodega_norte, con_cien) == Decimal("20")


def test_trasladar_al_mismo_sitio_da_409(admin_client, org_a, bodega, con_cien):
    r = admin_client.post(TRASLADOS, {
        "ubicacion_origen": str(bodega.id),
        "ubicacion_destino": str(bodega.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "5"}],
    }, format="json")
    assert r.status_code == 409, r.content


# ---------------------------------------------------------------------------
# Conteo fisico
# ---------------------------------------------------------------------------

def test_el_ciclo_de_un_conteo_por_la_api(admin_client, org_a, bodega, con_cien):
    abierto = admin_client.post(CONTEOS, {"ubicacion": str(bodega.id)},
                                format="json")
    assert abierto.status_code == 201, abierto.content
    cid = abierto.json()["id"]

    anotado = admin_client.post(f"{CONTEOS}{cid}/anotar/", {
        "material": "CON-SC-APC", "cantidad": "93",
        "motivo": "faltaban siete",
    }, format="json")
    assert anotado.status_code == 201, anotado.content

    cerrado = admin_client.post(f"{CONTEOS}{cid}/cerrar/", {}, format="json")
    assert cerrado.status_code == 200, cerrado.content
    cuerpo = cerrado.json()
    assert cuerpo["ajustes"] == 1
    linea = cuerpo["lineas"][0]
    assert linea["contado"] == "93.000"
    assert linea["segun_sistema"] == "100.000"
    assert linea["diferencia"] == "-7.000"
    assert linea["ajuste"] is not None

    # El saldo quedo en lo contado, y por un movimiento.
    assert inv.existencia(bodega, con_cien) == Decimal("93")


def test_dos_conteos_abiertos_dan_409(admin_client, org_a, bodega):
    admin_client.post(CONTEOS, {"ubicacion": str(bodega.id)}, format="json")
    r = admin_client.post(CONTEOS, {"ubicacion": str(bodega.id)}, format="json")
    assert r.status_code == 409, r.content


# ---------------------------------------------------------------------------
# FASE 3
# ---------------------------------------------------------------------------

def test_crear_proveedor_y_registrar_una_compra(admin_client, org_a, bodega,
                                                conector):
    p = admin_client.post(PROVEEDORES, {
        "nombre": "Fibras del Norte", "identificacion": "900123456-7",
    }, format="json")
    assert p.status_code == 201, p.content

    c = admin_client.post(COMPRAS, {
        "ubicacion_destino": str(bodega.id),
        "proveedor": p.json()["id"],
        "referencia": "FAC-8891",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "200",
                    "costo_unitario": "1500"}],
    }, format="json")
    assert c.status_code == 201, c.content
    assert inv.existencia(bodega, conector) == Decimal("200")


def test_la_misma_factura_dos_veces_da_409(admin_client, org_a, bodega, conector):
    p = admin_client.post(PROVEEDORES, {"nombre": "Fibras del Sur"},
                          format="json")
    cuerpo = {
        "ubicacion_destino": str(bodega.id),
        "proveedor": p.json()["id"],
        "referencia": "F-777",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "10",
                    "costo_unitario": "1"}],
    }
    assert admin_client.post(COMPRAS, cuerpo, format="json").status_code == 201
    r = admin_client.post(COMPRAS, cuerpo, format="json")
    assert r.status_code == 409, r.content
    assert "ya se registró" in r.json()["detail"]


def test_la_valorizacion_avisa_de_lo_que_no_puede_valorizar(
    admin_client, org_a, bodega, conector
):
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega, referencia="F-V",
        lineas=[{"material": conector, "cantidad": 100, "costo_unitario": "1500"}],
    )
    otro = MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-X", nombre="ONT sin costo"
    )
    inv.registrar_entrada(org=org_a, material=otro, cantidad=3,
                          ubicacion_destino=bodega)

    r = admin_client.get(VALORIZACION, {"ubicacion": str(bodega.id)})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == "150000.00"
    assert len(cuerpo["sin_costo_conocido"]) == 1
    assert "no entran en el total" in cuerpo["advertencia"]


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

def test_los_tres_reportes_responden(admin_client, org_a, bodega, con_cien):
    for cual in ("consumo", "tecnicos", "descuadres"):
        r = admin_client.get(REPORTES, {"de": cual})
        assert r.status_code == 200, (cual, r.content)
        assert r.json()["de"] == cual
        assert isinstance(r.json()["filas"], list)


def test_un_reporte_que_no_existe_lo_dice_y_lista_los_que_hay(admin_client):
    """Un 400 mudo obliga a adivinar el nombre correcto."""
    r = admin_client.get(REPORTES, {"de": "inventado"})
    assert r.status_code == 400
    assert "consumo, tecnicos, descuadres" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Permisos y aislamiento
# ---------------------------------------------------------------------------

def test_un_tecnico_raso_no_puede_reservar(user_client, org_a, bodega, con_cien):
    r = user_client.post(RESERVAS, {
        "ubicacion": str(bodega.id), "material": "CON-SC-APC", "cantidad": "5",
    }, format="json")
    assert r.status_code == 403, r.content


def test_un_tecnico_raso_SI_puede_leer_un_reporte(user_client, org_a):
    """Saber en que se fue el material no mueve nada."""
    r = user_client.get(REPORTES, {"de": "consumo"})
    assert r.status_code == 200, r.content


def test_otra_empresa_no_ve_las_reservas(org_b_client, org_a, bodega, con_cien):
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)
    # La ubicacion es de org_a: para org_b no existe.
    r = org_b_client.get(RESERVAS, {"ubicacion": str(bodega.id)})
    assert r.status_code == 404, r.content
