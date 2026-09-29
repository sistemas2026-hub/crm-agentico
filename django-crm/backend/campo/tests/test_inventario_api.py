# -*- coding: utf-8 -*-
"""
La API del inventario, y el rol de bodeguero.

LO QUE ESTAS PRUEBAS DEFIENDEN
------------------------------
Dos cosas que se veian iguales y no lo son:

  * un bodeguero DESPACHA y RECIBE material;
  * un supervisor ademas VALIDA ordenes de trabajo y cierra casos.

Antes el permiso era uno solo --ROLES_GESTION-- porque el primero no existia. Al
crearlo hay que probar las dos direcciones: que el bodeguero pueda lo suyo Y que
NO pueda lo que no le toca. Una prueba que solo comprueba lo primero deja pasar
un rol que puede todo.

Y el 409 del despacho imposible no es cosmetico: le dice a la pantalla si el
problema es un dato mal escrito (400, corregilo) o el estado del inventario (409,
mira donde esta el aparato). Con un 400 para las dos cosas, la pantalla tiene que
adivinar.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from campo.inventario import UbicacionInventario
from campo.models import MaterialCatalogo
from campo.services import inventario as inv
from common.serializer import OrgAwareRefreshToken
from common.models import Profile

pytestmark = pytest.mark.django_db

UBICACIONES = "/api/campo/inventario/ubicaciones/"
EXISTENCIAS = "/api/campo/inventario/existencias/"
CATALOGO = "/api/campo/inventario/catalogo/"
ENTRADAS = "/api/campo/inventario/entradas/"
DESPACHOS = "/api/campo/inventario/despachos/"
DEVOLUCIONES = "/api/campo/inventario/devoluciones/"


def _cliente(user, org, profile):
    c = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def bodeguero(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="bodega@test.com", password="testpass123"
    )
    profile = Profile.objects.create(
        user=user, org=org_a, role="BODEGA", is_active=True
    )
    return user, profile


@pytest.fixture
def cliente_bodeguero(org_a, bodeguero):
    user, profile = bodeguero
    return _cliente(user, org_a, profile)


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC",
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei",
        clase=MaterialCatalogo.SERIALIZADO,
    )


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def test_las_ubicaciones_se_listan(admin_client, bodega):
    r = admin_client.get(UBICACIONES)
    assert r.status_code == 200
    nombres = [u["nombre"] for u in r.json()["ubicaciones"]]
    assert "Bodega Central" in nombres


def test_el_catalogo_dice_que_material_es_serializado(admin_client, ont, conector):
    r = admin_client.get(CATALOGO)
    assert r.status_code == 200
    por_codigo = {m["codigo"]: m for m in r.json()["materiales"]}
    assert por_codigo["ONT-HG8145"]["es_serializado"] is True
    assert por_codigo["CON-SC-APC"]["es_serializado"] is False


def test_las_existencias_salen_por_ubicacion(admin_client, org_a, bodega, conector):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=40, ubicacion_destino=bodega,
    )
    r = admin_client.get(EXISTENCIAS, {"ubicacion": str(bodega.id)})
    assert r.status_code == 200
    filas = {f["codigo"]: f for f in r.json()["materiales"]}
    assert filas["CON-SC-APC"]["existencia"] == "40.000"


def test_sin_ubicacion_devuelve_todas(admin_client, org_a, bodega, conector):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=40, ubicacion_destino=bodega,
    )
    r = admin_client.get(EXISTENCIAS)
    assert r.status_code == 200
    assert len(r.json()["ubicaciones"]) >= 1


# ---------------------------------------------------------------------------
# Escritura: el ciclo por la API
# ---------------------------------------------------------------------------

def test_entrada_y_despacho_punta_a_punta(
    admin_client, org_a, bodega, conector, user_profile
):
    r = admin_client.post(ENTRADAS, {
        "material": "CON-SC-APC", "cantidad": "100",
        "ubicacion_destino": str(bodega.id), "origen_ref": "FAC-001",
    }, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["existencia"] == "100.000"

    r = admin_client.post(DESPACHOS, {
        "ubicacion_origen": str(bodega.id),
        "profile_destino": str(user_profile.id),
        "acta": "K-0412",
        "lineas": [{"material": "CON-SC-APC", "cantidad": "30"}],
    }, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["acta"] == "K-0412"
    assert len(r.json()["movimientos"]) == 1

    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    assert inv.existencia(bodega, conector) == Decimal("70")
    assert inv.existencia(custodia, conector) == Decimal("30")


def test_despachar_una_serie_ya_despachada_da_409(
    admin_client, org_a, bodega, ont, user_profile, otro_profile
):
    """409 y no 400: el dato esta bien, el estado del inventario no lo permite."""
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="HWT-1",
    )
    primero = admin_client.post(DESPACHOS, {
        "ubicacion_origen": str(bodega.id),
        "profile_destino": str(user_profile.id),
        "lineas": [{"material": "ONT-HG8145", "serie": "HWT-1"}],
    }, format="json")
    assert primero.status_code == 201, primero.content

    segundo = admin_client.post(DESPACHOS, {
        "ubicacion_origen": str(bodega.id),
        "profile_destino": str(otro_profile.id),
        "lineas": [{"material": "ONT-HG8145", "serie": "HWT-1"}],
    }, format="json")
    assert segundo.status_code == 409, segundo.content
    assert "dos manos" in segundo.json()["detail"]


def test_la_devolucion_vuelve_por_la_api(
    admin_client, org_a, bodega, conector, user_profile
):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 30}],
    )
    r = admin_client.post(DEVOLUCIONES, {
        "profile_origen": str(user_profile.id),
        "ubicacion_destino": str(bodega.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "12"}],
    }, format="json")
    assert r.status_code == 201, r.content
    assert inv.existencia(bodega, conector) == Decimal("82")


def test_una_devolucion_que_no_cuadra_abre_la_incidencia_POR_LA_API(
    admin_client, org_a, bodega, conector, user_profile
):
    """El camino completo, que estaba cortado en el ultimo tramo.

    `recibir_devolucion` abre una incidencia cuando la linea dice `esperado` y
    vuelve menos. La VISTA armaba la linea con material, cantidad y serie, y
    descartaba `esperado`: por la API web la incidencia NUNCA se abria. La
    pantalla lo mandaba, el serializador lo tiraba, y quien recibia veia un 201
    limpio sobre una devolucion a la que le faltaban tres conectores.

    Se afirma sobre el EFECTO --que la incidencia existe y que su cantidad es la
    diferencia-- y no sobre que la vista lea el campo: eso ya estaba "probado" por
    las pruebas del servicio, que pasaban con el hueco vivo porque llamaban al
    servicio directamente.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 18}], acta="ACTA-ESPERADO",
    )

    r = admin_client.post(DEVOLUCIONES, {
        "profile_origen": str(user_profile.id),
        "ubicacion_destino": str(bodega.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "15", "esperado": "18"}],
    }, format="json")

    assert r.status_code == 201, r.content
    incidencias = r.json()["incidencias"]
    assert len(incidencias) == 1, (
        f"volvieron 15 de 18 esperados y no se abrio ninguna incidencia: "
        f"{r.json()}"
    )
    i = incidencias[0]
    assert i["material"] == "CON-SC-APC"
    assert Decimal(i["cantidad"]) == Decimal("3")
    # Los dos numeros que la originaron viajan, para que la pantalla no tenga que
    # leerlos del texto del motivo.
    assert i["esperado"] == "18"
    assert i["recibido"] == "15"


def test_sin_esperado_no_se_supone_un_faltante(
    admin_client, org_a, bodega, conector, user_profile
):
    """Devolver 12 de 18 es legitimo: al tecnico le quedan 6 y sigue trabajando.

    La contraparte de la prueba anterior, y la razon por la que el campo es
    opcional: si la ausencia de `esperado` abriera una incidencia, habria una por
    cada devolucion parcial y nadie las mirarian mas.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 18}], acta="ACTA-SIN-ESPERADO",
    )

    r = admin_client.post(DEVOLUCIONES, {
        "profile_origen": str(user_profile.id),
        "ubicacion_destino": str(bodega.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "12"}],
    }, format="json")

    assert r.status_code == 201, r.content
    assert r.json()["incidencias"] == []


def test_la_historia_de_una_serie_se_consulta(
    admin_client, org_a, bodega, ont, user_profile
):
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="HIST-9",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": ont, "serie": "HIST-9"}],
    )
    r = admin_client.get("/api/campo/inventario/serie/HIST-9/")
    assert r.status_code == 200, r.content
    activo = r.json()["activos"][0]
    assert [h["tipo"] for h in activo["historia"]] == ["entrada", "despacho"]
    assert "Custodia de" in activo["donde_esta"]
    # El indice y el libro tienen que coincidir, y la API lo DICE en vez de
    # elegir uno en silencio.
    assert activo["cuadra_con_el_libro"] is True


# ---------------------------------------------------------------------------
# F9 -- el rol de bodeguero, en las DOS direcciones
# ---------------------------------------------------------------------------

def test_f9_el_bodeguero_puede_despachar(
    cliente_bodeguero, org_a, bodega, conector, user_profile
):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=50, ubicacion_destino=bodega,
    )
    r = cliente_bodeguero.post(DESPACHOS, {
        "ubicacion_origen": str(bodega.id),
        "profile_destino": str(user_profile.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "5"}],
    }, format="json")
    assert r.status_code == 201, r.content


def test_f9_el_bodeguero_NO_puede_validar_una_orden(
    cliente_bodeguero, org_a
):
    """La otra mitad de F9. Sin esta, el rol nuevo puede todo."""
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    ver = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={}
    )
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=9001, tipo_trabajo_version=ver,
        cliente_nombre="Prueba", cliente_direccion="Calle 1",
    )
    r = cliente_bodeguero.post(
        f"/api/campo/trabajos/{orden.id}/validar/", {}, format="json"
    )
    assert r.status_code == 403, (
        f"un bodeguero validó una orden de trabajo (status {r.status_code}): "
        f"el rol nuevo no puede heredar lo que puede un supervisor"
    )


def test_un_tecnico_raso_no_puede_despachar(
    user_client, org_a, bodega, conector, user_profile
):
    """El material sale de la bodega por decision de la oficina, no del tecnico."""
    r = user_client.post(DESPACHOS, {
        "ubicacion_origen": str(bodega.id),
        "profile_destino": str(user_profile.id),
        "lineas": [{"material": "CON-SC-APC", "cantidad": "5"}],
    }, format="json")
    assert r.status_code == 403, r.content


def test_una_empresa_no_ve_las_ubicaciones_de_otra(org_b_client, bodega):
    """Aislamiento. Sin esto, todo lo anterior es cosmetico."""
    r = org_b_client.get(UBICACIONES)
    assert r.status_code == 200
    nombres = [u["nombre"] for u in r.json()["ubicaciones"]]
    assert "Bodega Central" not in nombres


@pytest.fixture
def otro_profile(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tec2@test.com", password="testpass123"
    )
    return Profile.objects.create(
        user=user, org=org_a, role="USER", is_active=True
    )
