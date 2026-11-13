# -*- coding: utf-8 -*-
"""Material apartado para UNA orden: lo que lo hace seguro.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
`ReservaDeMaterial` acepta una `orden` desde siempre, el endpoint la acepta y el
servicio `materiales_de_orden` ya la lee para armar el bloque `comprometido` que
la app dibuja. Lo unico que faltaba era que el CRM mandara el campo.

Al ir a conectarlo (02/10/2026) aparecieron dos huecos que hacian que la funcion
fuera PEOR que no tenerla, porque el inventario empieza a mentir despacio:

  1. `consumir_reservas` elegia por ubicacion y material, la mas antigua primero,
     SIN mirar la orden. Un despacho de kit --que por decision congelada no
     nombra ninguna orden-- cerraba la reserva de un trabajo cualquiera.

  2. Nada liberaba una reserva cuando la orden se cancelaba o se cerraba.
     `vencer_reservas` solo toca las que tienen plazo, y es a proposito. Una
     reserva de una orden muerta bloqueaba material PARA SIEMPRE, y el sintoma
     --falta material que esta en la bodega-- no apunta a la causa.

Las dos direcciones se afirman en cada caso: una sola se cumpliria con una
implementacion que no consuma nunca, o que libere todo siempre.
"""

from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import ReservaDeMaterial
from campo.models import (
    AsignacionTrabajo,
    MaterialCatalogo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import inventario as inv
from campo.services import inventario_operacion as op
from campo.services import transiciones
from common.models import Profile

pytestmark = pytest.mark.django_db


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.reservas@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, nombre="Bodega Reservas", tipo="bodega", activa=True
    )


@pytest.fixture
def drop(org_a, bodega):
    """El material, CON existencia: `reservar` valida contra lo disponible, y sin
    entrada no se puede apartar nada."""
    material = MaterialCatalogo.objects.create(
        org=org_a, codigo="FIB-RES", nombre="Fibra drop", unidad="m"
    )
    inv.registrar_entrada(
        org=org_a, material=material, cantidad=1000, ubicacion_destino=bodega
    )
    return material


def _orden(org, profile, numero):
    wt, _ = WorkType.objects.get_or_create(
        org=org, codigo="res_test", defaults={"nombre": "Prueba"}
    )
    version, _ = WorkTypeVersion.objects.get_or_create(
        work_type=wt,
        version=1,
        defaults={
            "schema_version": 1,
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"pasos": [], "campos": [], "evidencias": []},
        },
    )
    o = OrdenTrabajo.objects.create(
        org=org,
        numero=numero,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon",
        cliente_direccion="Calle 50",
        estado_operativo=OrdenTrabajo.ASIGNADA,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=profile, rol="tecnico", es_principal=True
    )
    return o


def _abiertas(orden=None):
    qs = ReservaDeMaterial.objects.filter(resuelta_en__isnull=True)
    return qs.filter(orden=orden) if orden is not None else qs


# --------------------------------------------------------------------------- #
# A. Un despacho que no nombra una orden no toca lo apartado para una
# --------------------------------------------------------------------------- #

def test_a_un_despacho_de_kit_no_consume_la_reserva_de_un_trabajo(
    org_a, tecnico, bodega, drop
):
    """EL CASO QUE MOTIVO EL ARREGLO.

    El kit es a la custodia del tecnico y no a un trabajo --decision congelada,
    `EntregaDeKit` no tiene FK a la orden--. Asi que un despacho de kit no puede
    cumplir una promesa hecha para una orden concreta, y antes la cerraba.
    """
    orden = _orden(org_a, tecnico[1], 8101)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=100, orden=orden
    )

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=100
    )

    assert _abiertas(orden).count() == 1


def test_b_pero_si_consume_una_reserva_generica(org_a, tecnico, bodega, drop):
    """La otra direccion. Sin esto, no consumir NUNCA cumpliria la prueba de
    arriba y el defecto de la doble contabilidad volveria."""
    op.reservar(org=org_a, ubicacion=bodega, material=drop, cantidad=40)

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=40
    )

    assert _abiertas().count() == 0


def test_c_nombrando_la_orden_si_se_consume_la_suya(org_a, tecnico, bodega, drop):
    orden = _orden(org_a, tecnico[1], 8102)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=30, orden=orden
    )

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=30, orden=orden
    )

    assert _abiertas(orden).count() == 0


def test_d_lo_especifico_se_cumple_antes_que_lo_generico(
    org_a, tecnico, bodega, drop
):
    """Mismo criterio que ya regia para la serie, por la misma razon.

    Hay una reserva generica MAS ANTIGUA y una de la orden. Despachando contra la
    orden tiene que cerrarse la suya: cerrar la generica dejaria viva la promesa
    del trabajo que se esta despachando, que es justo la que se acaba de cumplir.
    """
    op.reservar(org=org_a, ubicacion=bodega, material=drop, cantidad=10)
    orden = _orden(org_a, tecnico[1], 8103)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=10, orden=orden
    )

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=10, orden=orden
    )

    assert _abiertas(orden).count() == 0
    assert _abiertas().filter(orden__isnull=True).count() == 1


def test_e_la_reserva_de_otra_orden_no_se_toca(org_a, tecnico, bodega, drop):
    mia = _orden(org_a, tecnico[1], 8104)
    ajena = _orden(org_a, tecnico[1], 8105)
    op.reservar(org=org_a, ubicacion=bodega, material=drop, cantidad=20, orden=mia)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=20, orden=ajena
    )

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=20, orden=mia
    )

    assert _abiertas(mia).count() == 0
    assert _abiertas(ajena).count() == 1


def test_f_una_reserva_mas_grande_se_reduce_en_vez_de_cerrarse(
    org_a, tecnico, bodega, drop
):
    """Lo que ya valia para las genericas sigue valiendo con orden: una reserva
    de 50 de la que salieron 10 sigue comprometiendo 40."""
    orden = _orden(org_a, tecnico[1], 8106)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=50, orden=orden
    )

    op.consumir_reservas(
        org=org_a, ubicacion=bodega, material=drop, cantidad=10, orden=orden
    )

    viva = _abiertas(orden).get()
    assert viva.cantidad == Decimal("40.000")


# --------------------------------------------------------------------------- #
# B. Una orden que termina suelta lo que tenia apartado
# --------------------------------------------------------------------------- #

def test_g_cancelar_una_orden_libera_su_reserva(org_a, tecnico, bodega, drop):
    """SIN ESTO, EL MATERIAL QUEDA BLOQUEADO PARA SIEMPRE.

    `vencer_reservas` solo toca las que tienen plazo --a proposito-- y nadie mas
    vuelve a mirarlas. El sintoma, meses despues, es que falta material que esta
    en la bodega, comprometido para un trabajo que no existe.
    """
    orden = _orden(org_a, tecnico[1], 8107)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=70, orden=orden
    )

    transiciones.ejecutar_accion_operativa(
        orden, "cancelar", profile=tecnico[1], metadatos={"motivo": "El cliente desistió"}
    )

    assert _abiertas(orden).count() == 0
    suelta = ReservaDeMaterial.objects.get(orden=orden)
    assert suelta.desenlace == ReservaDeMaterial.LIBERADA
    # Se libera, no se borra: la fila explica por que se solto.
    assert "se solto" in suelta.motivo


def test_h_y_queda_escrito_en_la_bitacora(org_a, tecnico, bodega, drop):
    """Es un efecto sobre el inventario: quien lea la orden dentro de un año
    tiene que poder ver que al cancelarla se soltaron reservas."""
    from campo.models import EventoTrabajo

    orden = _orden(org_a, tecnico[1], 8108)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=5, orden=orden
    )
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=5, orden=orden
    )

    transiciones.ejecutar_accion_operativa(
        orden, "cancelar", profile=tecnico[1]
    )

    evento = EventoTrabajo.objects.filter(orden=orden).order_by("-created_at").first()
    assert evento.datos.get("reservas_liberadas") == 2


def test_i_una_transicion_normal_NO_libera_nada(org_a, tecnico, bodega, drop):
    """La otra direccion, y es la que importa: liberar siempre seria peor que no
    liberar nunca. Marcar que vas en camino no suelta el material del trabajo."""
    orden = _orden(org_a, tecnico[1], 8109)
    op.reservar(
        org=org_a, ubicacion=bodega, material=drop, cantidad=15, orden=orden
    )

    transiciones.ejecutar_accion_operativa(
        orden, "marcar_en_camino", profile=tecnico[1]
    )

    assert _abiertas(orden).count() == 1


def test_j_una_orden_sin_reservas_no_escribe_la_clave(org_a, tecnico):
    """Cero no se escribe: una bitacora con `reservas_liberadas: 0` en cada
    cancelacion es ruido que tapa las que si soltaron algo."""
    from campo.models import EventoTrabajo

    orden = _orden(org_a, tecnico[1], 8110)

    transiciones.ejecutar_accion_operativa(
        orden, "cancelar", profile=tecnico[1]
    )

    evento = EventoTrabajo.objects.filter(orden=orden).order_by("-created_at").first()
    assert "reservas_liberadas" not in evento.datos


# --------------------------------------------------------------------------- #
# C. Apartar para una orden desde el CRM: por numero, que es lo que hay en mano
# --------------------------------------------------------------------------- #

RESERVAS = "/api/campo/inventario/reservas/"


def test_k_se_aparta_por_NUMERO_de_orden(admin_client, org_a, tecnico, bodega, drop):
    """El id existia y nadie lo mandaba.

    Quien aparta material es la bodega, y lo que la bodega tiene en la mano es el
    numero impreso en la orden, no un UUID de 36 caracteres.
    """
    orden = _orden(org_a, tecnico[1], 8201)

    r = admin_client.post(
        RESERVAS,
        {
            "ubicacion": str(bodega.id),
            "material": drop.codigo,
            "cantidad": 25,
            "orden_numero": "8201",
        },
        format="json",
    )

    # 201: la reserva es un recurso nuevo. La primera version de esta prueba
    # esperaba 200 y el que estaba mal era yo, no el endpoint.
    assert r.status_code == 201, r.data
    assert _abiertas(orden).count() == 1


def test_l_sin_orden_sigue_reservando_contra_la_bodega(admin_client, org_a,
                                                       bodega, drop):
    """Vacio es el caso NORMAL: la mayoria de las reservas no son de un trabajo.

    Si exigir la orden fuera el precio de tener la funcion, la funcion rompe lo
    que ya andaba.
    """
    r = admin_client.post(
        RESERVAS,
        {
            "ubicacion": str(bodega.id),
            "material": drop.codigo,
            "cantidad": 5,
            "orden_numero": "",
        },
        format="json",
    )

    # 201: la reserva es un recurso nuevo. La primera version de esta prueba
    # esperaba 200 y el que estaba mal era yo, no el endpoint.
    assert r.status_code == 201, r.data
    assert _abiertas().filter(orden__isnull=True).count() == 1


def test_m_un_numero_que_no_existe_se_dice(admin_client, org_a, bodega, drop):
    r = admin_client.post(
        RESERVAS,
        {
            "ubicacion": str(bodega.id),
            "material": drop.codigo,
            "cantidad": 5,
            "orden_numero": "99999",
        },
        format="json",
    )

    assert r.status_code == 404


def test_n_no_se_aparta_para_una_orden_YA_TERMINADA(admin_client, org_a, tecnico,
                                                    bodega, drop):
    """LA PUERTA QUE FALTABA.

    Sin esto se podria apartar material para un trabajo cancelado, y ese material
    quedaria bloqueado hasta que alguien lo note: la transicion que lo soltaria ya
    ocurrio. El sintoma --falta material que esta en la bodega-- no apunta nunca a
    la causa.
    """
    orden = _orden(org_a, tecnico[1], 8202)
    transiciones.ejecutar_accion_operativa(
        orden, "cancelar", profile=tecnico[1]
    )

    r = admin_client.post(
        RESERVAS,
        {
            "ubicacion": str(bodega.id),
            "material": drop.codigo,
            "cantidad": 5,
            "orden_numero": "8202",
        },
        format="json",
    )

    assert r.status_code == 409
    assert "termino" in r.data["detail"]
    assert _abiertas(orden).count() == 0


def test_o_un_numero_que_no_es_numero_no_rompe(admin_client, org_a, bodega, drop):
    r = admin_client.post(
        RESERVAS,
        {
            "ubicacion": str(bodega.id),
            "material": drop.codigo,
            "cantidad": 5,
            "orden_numero": "OT-1843",
        },
        format="json",
    )

    assert r.status_code == 400
