# -*- coding: utf-8 -*-
"""Que areas mira el Supervisor: deja de ser una tupla del codigo.

MEDIDO EN PRODUCCION EL 13/11/2026, sobre los casos ABIERTOS de Rapilink:

    cartera 350 · soporte_tecnico 65 · operativo 62 · ventas 41 · administracion 18

Los 41 de 'ventas' incluyen TODAS las instalaciones nuevas --el departamento
Ventas de WispHub va a esa area por `importacion_tickets.destinos`-- y
quedaban fuera de la mirada del Supervisor, que tenia dos areas fijas en
`AREAS_DEL_SUPERVISOR`. No llegaban a Despacho, la demanda del dia salia con
CERO instalaciones, y la cuadrilla de instalacion salia con la labor de la
mayoria de su zona. Sin un error, sin un log, sin nada en rojo.

LO QUE SE AFIRMA ACA es el EFECTO sobre el filtro --que un caso de 'ventas'
pase de ajeno a propio cuando la empresa agrega el area-- y no que el campo
exista. Un test que mirara el campo sobreviviria intacto a que
`criterio_de_area` siguiera leyendo la tupla vieja.
"""
import pytest

from campo.cuadrillas import ConfiguracionDeReparto
from cases.models import Case
from operaciones import areas_del_tenant as A

pytestmark = pytest.mark.django_db

URL = "/api/campo/cuadrillas/configuracion/"


def _caso(org, area):
    return Case.objects.create(org=org, name=f"Ticket de {area}", area=area)


def _propios(org):
    """Los casos que el Supervisor SI mira, por el criterio real."""
    criterio = A.criterio_de_area(mapa={}, org=org)
    return set(Case.objects.filter(org=org).filter(criterio.propio)
               .values_list("area", flat=True))


def _elegir(org, areas):
    fila, _ = ConfiguracionDeReparto.objects.get_or_create(org=org)
    fila.areas_del_supervisor = areas
    fila.save()
    return fila


# =========================================================================== #
#  A · EL EFECTO SOBRE EL FILTRO
# =========================================================================== #
def test_a1_sin_elegir_nada_mira_LAS_DE_SIEMPRE(org_a):
    """Desplegar esto no le cambia la conducta a ninguna empresa."""
    for area in ("soporte_tecnico", "operativo", "ventas", "cartera"):
        _caso(org_a, area)

    assert _propios(org_a) == {"soporte_tecnico", "operativo"}


def test_a2_AGREGANDO_VENTAS_el_caso_de_ventas_pasa_a_propio(org_a):
    """LA PRUEBA QUE IMPORTA. Es el cambio que Rapilink necesita."""
    for area in ("soporte_tecnico", "operativo", "ventas", "cartera"):
        _caso(org_a, area)
    antes = _propios(org_a)

    _elegir(org_a, ["soporte_tecnico", "operativo", "ventas"])

    assert "ventas" not in antes, "el control: antes no estaba"
    assert _propios(org_a) == {"soporte_tecnico", "operativo", "ventas"}
    assert "cartera" not in _propios(org_a), (
        "lo que no se eligio sigue afuera: esto no abre la puerta a todo")


def test_a3_el_caso_de_ventas_deja_de_ser_AJENO(org_a):
    #  No alcanza con que entre en 'propio': mientras siga marcado ajeno, el
    #  Supervisor lo cancela igual. Son dos consultas distintas.
    _caso(org_a, "ventas")
    criterio = A.criterio_de_area(mapa={}, org=org_a)
    assert Case.objects.filter(org=org_a).filter(criterio.ajeno).exists()

    _elegir(org_a, ["soporte_tecnico", "operativo", "ventas"])
    criterio = A.criterio_de_area(mapa={}, org=org_a)
    assert not Case.objects.filter(org=org_a).filter(criterio.ajeno).exists()


def test_a4_cada_empresa_la_suya(org_a, org_b):
    _caso(org_a, "ventas")
    _caso(org_b, "ventas")
    _elegir(org_a, ["ventas"])

    assert _propios(org_a) == {"ventas"}
    assert _propios(org_b) == set(), (
        "la empresa B no eligio ventas: su caso sigue afuera")


# =========================================================================== #
#  B · LO QUE NO PUEDE PASAR
# =========================================================================== #
def test_b1_una_lista_VACIA_no_apaga_al_supervisor(org_a):
    """Fail-SAFE hacia la conducta de siempre, no hacia el silencio.

    Devolver () dejaria al Supervisor sin mirar NADA, y el sintoma --«no
    propone»-- no señalaria a esta configuracion.
    """
    _elegir(org_a, [])
    assert A.areas_que_mira(org_a) == A.AREAS_DE_FABRICA


#  `None` NO esta en la lista: la columna es `not null` y la base lo
#  rechaza antes de llegar al lector. Un caso de prueba que no puede
#  ocurrir mide la prueba, no el codigo.
@pytest.mark.parametrize("basura", ["ventas", 7, [1, 2], [""], ["  "]])
def test_b2_una_configuracion_ILEGIBLE_vuelve_a_las_de_fabrica(org_a, basura):
    fila, _ = ConfiguracionDeReparto.objects.get_or_create(org=org_a)
    fila.areas_del_supervisor = basura
    fila.save()

    assert A.areas_que_mira(org_a) == A.AREAS_DE_FABRICA


def test_b3_sin_org_no_adivina(org_a):
    assert A.areas_que_mira(None) == A.AREAS_DE_FABRICA


def test_b4_los_espacios_no_cuentan_como_area(org_a):
    _caso(org_a, "ventas")
    _elegir(org_a, ["  ventas  "])

    assert A.areas_que_mira(org_a) == ("ventas",)
    assert _propios(org_a) == {"ventas"}


# =========================================================================== #
#  C · LA PANTALLA
# =========================================================================== #
def test_c1_el_get_dice_cuales_mira_hoy(admin_client, org_a):
    datos = admin_client.get(URL).json()

    assert datos["areas_del_supervisor"] == list(A.AREAS_DE_FABRICA), (
        "la lista EFECTIVA, no una vacia que se leeria como «ninguna»")
    assert datos["areas_de_fabrica"] == list(A.AREAS_DE_FABRICA)
    assert set(A.AREAS_DE_FABRICA) <= set(datos["areas_conocidas"])


def test_c2_se_eligen_desde_la_pantalla_y_quedan(admin_client, org_a):
    r = admin_client.put(URL, {"activo": True, "hora_local": 3,
                               "tope_por_cuadrilla": 10,
                               "areas_del_supervisor": ["soporte_tecnico",
                                                        "operativo", "ventas"]},
                         format="json")
    assert r.status_code == 200, r.content
    assert r.json()["areas_del_supervisor"] == ["soporte_tecnico", "operativo",
                                                "ventas"]
    assert admin_client.get(URL).json()["areas_del_supervisor"] == [
        "soporte_tecnico", "operativo", "ventas"]


def test_c3_no_mandarlas_NO_las_borra(admin_client, org_a):
    #  Una pantalla vieja que no conoce el campo no puede dejar al Supervisor
    #  mirando otra cosa. Mismo criterio que la tabla de labores.
    admin_client.put(URL, {"activo": True, "hora_local": 3,
                           "tope_por_cuadrilla": 10,
                           "areas_del_supervisor": ["ventas"]}, format="json")
    admin_client.put(URL, {"activo": True, "hora_local": 3,
                           "tope_por_cuadrilla": 10}, format="json")

    assert admin_client.get(URL).json()["areas_del_supervisor"] == ["ventas"]


def test_c4_una_lista_vacia_vuelve_a_las_de_fabrica(admin_client, org_a):
    admin_client.put(URL, {"activo": True, "hora_local": 3,
                           "tope_por_cuadrilla": 10,
                           "areas_del_supervisor": ["ventas"]}, format="json")
    admin_client.put(URL, {"activo": True, "hora_local": 3,
                           "tope_por_cuadrilla": 10,
                           "areas_del_supervisor": []}, format="json")

    assert admin_client.get(URL).json()["areas_del_supervisor"] == list(
        A.AREAS_DE_FABRICA)


def test_c5_repetidas_se_guardan_una_vez(admin_client, org_a):
    r = admin_client.put(URL, {"activo": True, "hora_local": 3,
                               "tope_por_cuadrilla": 10,
                               "areas_del_supervisor": ["ventas", "ventas"]},
                         format="json")
    assert r.json()["areas_del_supervisor"] == ["ventas"]


@pytest.mark.parametrize("malo", ["ventas", {"a": 1}, [1], [None]])
def test_c6_un_valor_malo_se_rechaza_con_400(admin_client, org_a, malo):
    r = admin_client.put(URL, {"activo": True, "hora_local": 3,
                               "tope_por_cuadrilla": 10,
                               "areas_del_supervisor": malo}, format="json")
    assert r.status_code == 400, r.content


def test_c7_quien_no_gestiona_no_las_cambia(user_client, org_a):
    assert user_client.put(URL, {"activo": True, "hora_local": 3,
                                 "tope_por_cuadrilla": 10,
                                 "areas_del_supervisor": ["ventas"]},
                           format="json").status_code in (403, 404)
