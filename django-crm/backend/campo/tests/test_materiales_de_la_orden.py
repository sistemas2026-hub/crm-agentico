# -*- coding: utf-8 -*-
"""Que material toco una orden, y sobre todo QUE NO.

LO QUE ESTAS PRUEBAS DEFIENDEN
------------------------------
La pestaña Materiales de una orden es solo lectura y no calcula nada. El riesgo
no es que muestre poco: es que muestre material que NO es de esa orden y alguien
lo lea como si lo fuera.

Tres formas de mentir, y una prueba para cada una:

  1. mezclar el KIT DEL DIA con el material de la orden. `EntregaDeKit` no tiene
     FK a la orden --el despacho es a la custodia del tecnico-- asi que 150 m de
     drop para la jornada se leerian como 150 m para esta casa;
  2. traer movimientos de OTRA orden del mismo tecnico;
  3. traer movimientos de otra EMPRESA.

La tercera se afirma con 0 filas, no con "no aparece en la lista": un aislamiento
que se comprueba mirando si el codigo esta en la respuesta pasa igual cuando la
consulta trae todo y la pantalla filtra.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import ReservaDeMaterial
from campo.models import (
    AsignacionTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import inventario as inv
from campo.services.materiales_de_orden import materiales_de_orden
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db


def _ruta(orden, extra=""):
    return f"/api/campo/trabajos/{orden.id}/materiales/{extra}"


def _cliente(user, org, profile):
    c = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


def _version(org, codigo="ftth_instalacion"):
    wt = WorkType.objects.create(org=org, codigo=codigo, nombre="Instalacion FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


def _orden(org, version, numero, profile=None, estado=OrdenTrabajo.EN_SITIO):
    orden = OrdenTrabajo.objects.create(
        org=org,
        numero=numero,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon",
        cliente_direccion="Calle 50 # 10-20",
        estado_operativo=estado,
        revision=1,
    )
    if profile is not None:
        AsignacionTrabajo.objects.create(
            orden=orden, profile=profile, rol="tecnico", es_principal=True
        )
    return orden


@pytest.fixture
def supervisor(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="super@test.com", password="testpass123"
    )
    profile = Profile.objects.create(
        user=user, org=org_a, role="SUPERVISOR", is_active=True
    )
    return user, profile


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tec@test.com", password="testpass123"
    )
    profile = Profile.objects.create(
        user=user, org=org_a, role="USER", is_active=True
    )
    return user, profile


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def drop(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a,
        codigo="FIB-DROP",
        nombre="Fibra drop",
        clase=MaterialCatalogo.CONSUMIBLE,
        unidad="metros",
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a,
        codigo="CON-SC-APC",
        nombre="Conector SC/APC",
        clase=MaterialCatalogo.CONSUMIBLE,
        unidad="unidades",
    )


@pytest.fixture
def escena(org_a, supervisor, tecnico, bodega, drop, conector):
    """Una orden con las cuatro cosas: reserva, consumo, devolucion y un ajuste.

    Se construye con los servicios de verdad --`registrar_entrada`, `despachar`--
    y no insertando filas a mano: una escena armada por fuera del libro puede
    quedar en un estado que el sistema real nunca produce, y entonces la prueba
    defiende algo que no existe.
    """
    _, prof_tec = tecnico
    version = _version(org_a)
    orden = _orden(org_a, version, 5001, prof_tec)

    inv.registrar_entrada(
        org=org_a, material=drop, cantidad=Decimal("500"), ubicacion_destino=bodega,
        origen_ref="FAC-1",
    )
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=Decimal("50"), ubicacion_destino=bodega,
        origen_ref="FAC-2",
    )
    # Lo que sale a la calle: el kit del dia, a la CUSTODIA del tecnico. No lleva
    # orden, y es justamente el dato que no debe aparecer como de esta orden.
    inv.despachar(
        org=org_a,
        ubicacion_origen=bodega,
        profile_destino=prof_tec,
        lineas=[
            {"material": drop, "cantidad": Decimal("150")},
            {"material": conector, "cantidad": Decimal("10")},
        ],
        acta="ACTA-KIT-1",
    )

    custodia = inv.ubicacion_de_tecnico(prof_tec, org_a)

    # Comprometido PARA esta orden.
    ReservaDeMaterial.objects.create(
        org=org_a, ubicacion=bodega, material=conector, cantidad=Decimal("4"),
        orden=orden, reservada_por=prof_tec,
    )

    # Consumido en esta orden.
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=prof_tec, material=drop, orden=orden,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("37.5"),
        ubicacion_origen=custodia, idempotency_key="k-consumo-drop",
    )
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=prof_tec, material=conector, orden=orden,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("2"),
        ubicacion_origen=custodia, idempotency_key="k-consumo-con",
    )
    # Devuelto.
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=prof_tec, material=conector, orden=orden,
        tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=Decimal("3"),
        ubicacion_origen=custodia, ubicacion_destino=bodega,
        idempotency_key="k-devol-con",
    )
    # Otro movimiento atado a la orden, y con novedad: el descuadre no se
    # esconde, que es lo que alguien tiene que mirar.
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=prof_tec, material=drop, orden=orden,
        tipo=MovimientoDeMaterial.AJUSTE, cantidad=Decimal("1"),
        estado=MovimientoDeMaterial.DESCUADRE, motivo="Sobro un metro medido",
        ubicacion_destino=custodia, idempotency_key="k-ajuste-drop",
    )
    return {
        "orden": orden,
        "version": version,
        "custodia": custodia,
        "bodega": bodega,
        "tecnico": prof_tec,
    }


# --------------------------------------------------------------------------- #
# A. Los bloques, separados y con su significado
# --------------------------------------------------------------------------- #

def test_a_los_cuatro_bloques_llegan_separados(escena):
    d = materiales_de_orden(escena["orden"])

    assert [x["material"]["codigo"] for x in d["comprometido"]] == ["CON-SC-APC"]
    assert sorted(x["material"]["codigo"] for x in d["consumido"]) == [
        "CON-SC-APC", "FIB-DROP",
    ]
    assert [x["material"]["codigo"] for x in d["devuelto"]] == ["CON-SC-APC"]
    assert [x["tipo"] for x in d["otros"]] == ["ajuste"]
    assert d["hay_algo"] is True


def test_b_las_cantidades_salen_tal_como_se_registraron(escena):
    """37,5 m no se redondea ni se suma con nada: es la fila que alguien escribio."""
    d = materiales_de_orden(escena["orden"])
    consumo_drop = [x for x in d["consumido"] if x["material"]["codigo"] == "FIB-DROP"]
    assert len(consumo_drop) == 1
    assert Decimal(consumo_drop[0]["cantidad"]) == Decimal("37.5")
    assert consumo_drop[0]["material"]["unidad"] == "metros"


def test_c_un_descuadre_se_cuenta_y_no_se_esconde(escena):
    d = materiales_de_orden(escena["orden"])
    assert d["con_novedad"] == 1
    ajuste = d["otros"][0]
    assert ajuste["estado"] == "descuadre"
    assert "Sobro un metro" in ajuste["motivo"]


def test_d_la_reserva_consumida_sigue_apareciendo_con_su_desenlace(escena, org_a):
    """Una reserva no se borra al usarse: se marca. La ficha puede contar la historia."""
    r = ReservaDeMaterial.objects.get(orden=escena["orden"])
    from django.utils import timezone
    r.resuelta_en = timezone.now()
    r.desenlace = ReservaDeMaterial.CONSUMIDA
    r.save(update_fields=["resuelta_en", "desenlace", "updated_at"])

    d = materiales_de_orden(escena["orden"])
    assert len(d["comprometido"]) == 1
    assert d["comprometido"][0]["pendiente"] is False
    assert d["comprometido"][0]["desenlace"] == "consumida"


# --------------------------------------------------------------------------- #
# E-F. Lo que NO puede aparecer
# --------------------------------------------------------------------------- #

def test_e_el_kit_del_dia_no_es_material_de_esta_orden(escena):
    """El despacho de la mañana NO aparece entre lo de la orden.

    Son 150 m para la jornada. Si salieran como material de esta orden, la ficha
    diria que en una casa se usaron 150 m cuando se usaron 37,5.
    """
    d = materiales_de_orden(escena["orden"])

    todas = d["comprometido"] + d["consumido"] + d["devuelto"] + d["otros"]
    cantidades = {Decimal(x["cantidad"]) for x in todas}
    assert Decimal("150") not in cantidades
    assert Decimal("10") not in cantidades

    # Y el bloque de custodia no existe salvo que se pida.
    assert "custodia_del_tecnico" not in d


def test_f_la_custodia_se_pide_aparte_y_el_dato_dice_que_no_es_de_la_orden(escena):
    d = materiales_de_orden(escena["orden"], incluir_custodia=True)
    kit = d["custodia_del_tecnico"]

    # La aclaracion viaja en el dato, no solo en la pantalla: cualquiera puede
    # cambiar un titulo en el frontend.
    assert kit["es_de_esta_orden"] is False
    assert kit["acta"] == "ACTA-KIT-1"
    codigos = sorted(i["material"]["codigo"] for i in kit["items"])
    assert codigos == ["CON-SC-APC", "FIB-DROP"]
    # Y sigue estando fuera de los bloques de la orden.
    assert all(
        Decimal(x["cantidad"]) != Decimal("150")
        for x in d["consumido"] + d["devuelto"] + d["otros"]
    )


def test_g_un_movimiento_de_otra_orden_no_aparece(escena, org_a, drop):
    otra = _orden(org_a, escena["version"], 5002, escena["tecnico"])
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=escena["tecnico"], material=drop, orden=otra,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("99"),
        ubicacion_origen=escena["custodia"], idempotency_key="k-otra-orden",
    )

    d = materiales_de_orden(escena["orden"])
    assert all(Decimal(x["cantidad"]) != Decimal("99") for x in d["consumido"])

    # Y al revés: la otra orden ve lo suyo y nada de la primera.
    d2 = materiales_de_orden(otra)
    assert len(d2["consumido"]) == 1
    assert Decimal(d2["consumido"][0]["cantidad"]) == Decimal("99")
    assert d2["comprometido"] == []


def test_h_una_orden_de_otra_empresa_devuelve_cero_filas(escena, org_b, django_user_model):
    """El aislamiento se afirma con CERO, no con 'no aparece en la lista'."""
    user = django_user_model.objects.create_user(
        email="otra@empresa.com", password="testpass123"
    )
    prof_b = Profile.objects.create(
        user=user, org=org_b, role="SUPERVISOR", is_active=True
    )
    version_b = _version(org_b, codigo="ftth_b")
    orden_b = _orden(org_b, version_b, 7001, prof_b)

    d = materiales_de_orden(orden_b)
    assert d["comprometido"] == []
    assert d["consumido"] == []
    assert d["devuelto"] == []
    assert d["otros"] == []
    assert d["hay_algo"] is False
    assert d["con_novedad"] == 0


def test_i_una_orden_sin_material_no_miente_diciendo_que_hay(org_a, supervisor):
    version = _version(org_a)
    orden = _orden(org_a, version, 5003)
    d = materiales_de_orden(orden)
    assert d["hay_algo"] is False
    assert "custodia_del_tecnico" not in d


def test_j_sin_tecnico_principal_la_custodia_no_revienta(org_a):
    version = _version(org_a)
    orden = _orden(org_a, version, 5004)  # sin asignacion
    d = materiales_de_orden(orden, incluir_custodia=True)
    assert d["custodia_del_tecnico"]["tecnico"] is None
    assert d["custodia_del_tecnico"]["items"] == []
    assert d["custodia_del_tecnico"]["es_de_esta_orden"] is False


# --------------------------------------------------------------------------- #
# K-N. Por la API, que es como la va a leer la pantalla
# --------------------------------------------------------------------------- #

def test_k_el_supervisor_lee_la_pestana_por_la_api(escena, org_a, supervisor):
    user, prof = supervisor
    r = _cliente(user, org_a, prof).get(_ruta(escena["orden"]))
    assert r.status_code == 200, r.data
    assert len(r.data["consumido"]) == 2
    assert r.data["con_novedad"] == 1


def test_l_la_custodia_solo_llega_si_se_pide(escena, org_a, supervisor):
    user, prof = supervisor
    c = _cliente(user, org_a, prof)

    sin = c.get(_ruta(escena["orden"]))
    assert "custodia_del_tecnico" not in sin.data

    con = c.get(_ruta(escena["orden"], "?custodia=1"))
    assert con.data["custodia_del_tecnico"]["es_de_esta_orden"] is False


def test_m_el_tecnico_asignado_ve_su_orden(escena, org_a, tecnico):
    user, prof = tecnico
    r = _cliente(user, org_a, prof).get(_ruta(escena["orden"]))
    assert r.status_code == 200


def test_n_otra_empresa_recibe_404_y_nunca_403(escena, org_b, django_user_model):
    """404 estricto: un 403 confirmaria que ese UUID existe en algun lado."""
    user = django_user_model.objects.create_user(
        email="curiosa@empresa.com", password="testpass123"
    )
    prof_b = Profile.objects.create(
        user=user, org=org_b, role="ADMIN", is_active=True
    )
    r = _cliente(user, org_b, prof_b).get(_ruta(escena["orden"]))
    assert r.status_code == 404


def test_o_un_tecnico_no_asignado_recibe_404(escena, org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="ajeno@test.com", password="testpass123"
    )
    prof = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    r = _cliente(user, org_a, prof).get(_ruta(escena["orden"]))
    assert r.status_code == 404


def test_p_la_ruta_es_solo_lectura(escena, org_a, supervisor):
    """Mover inventario entra por inventario/, donde esta la frontera."""
    user, prof = supervisor
    c = _cliente(user, org_a, prof)
    for metodo in (c.post, c.patch, c.put, c.delete):
        r = metodo(_ruta(escena["orden"]), {}, format="json")
        assert r.status_code == 405, f"{metodo.__name__} devolvio {r.status_code}"
