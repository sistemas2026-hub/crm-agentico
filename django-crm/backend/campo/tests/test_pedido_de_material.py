# -*- coding: utf-8 -*-
"""Pedir material a bodega desde la calle.

EL PROBLEMA
-----------
El tecnico se queda sin conectores en la tercera instalacion y la aplicacion no
tiene nada que ofrecerle: saca el otro telefono y escribe al grupo. La pantalla
de Materiales le dice lo que tiene, y ahi se corta.

POR QUE UN PEDIDO NO ES UN MOVIMIENTO
--------------------------------------
Esta escrito en `models.py` y ordena todo el inventario: «un movimiento de
material ES UN HECHO QUE YA OCURRIO EN LA CALLE, no una solicitud que el
servidor pueda aprobar». De ahi salen el append-only, el saldo calculado y el
descuadre que se acepta igual.

Un pedido es lo contrario: todavia no paso nada, alguien lo tiene que atender, y
puede decir que no. Meterlo en la misma tabla romperia la unica afirmacion que
sostiene a esa tabla, y el primer sintoma seria un saldo que cuenta material que
nadie entrego.

LO QUE SE AFIRMA
----------------
1. **Idempotente.** El telefono reenvia sin señal, y dos pedidos iguales le
   harian pensar a bodega que hacen falta cuarenta conectores cuando hacen falta
   veinte.
2. **El reenvio se ve como EXITO**, no como error: para la cola de la app un
   error es motivo de reintento, y lo reintentaria para siempre.
3. **No cruza empresas.**
4. **Avisa a bodega por los canales que la empresa ya configuro**, y ese aviso
   NO lleva datos del cliente.
5. **No crea movimientos.** El saldo del tecnico no se mueve por pedir.
"""

from decimal import Decimal
from unittest import mock

import pytest

from campo.models import (
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    PedidoDeMaterial,
    WorkType,
    WorkTypeVersion,
)

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/inventario/pedidos/"


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CONN-SC", nombre="Conector SC/APC",
        unidad="u", clase=MaterialCatalogo.CONSUMIBLE,
    )


@pytest.fixture
def orden(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="pedido_test", nombre="Instalación")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=9001, tipo_trabajo_version=v,
        cliente_nombre="Beatriz Pinzón",
        cliente_telefono="+57 312 455 8901",
        cliente_direccion="Calle 50 # 10-20",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
    )


def _pedir(cliente, material, **extra):
    cuerpo = {
        "material": str(material.id),
        "cantidad": "20",
        "idempotency_key": "clave-1",
    }
    cuerpo.update(extra)
    return cliente.post(RUTA, cuerpo, format="json")


# --------------------------------------------------------------------------- #
# A. El pedido
# --------------------------------------------------------------------------- #

def test_a1_un_tecnico_puede_pedir_material(user_client, conector):
    r = _pedir(user_client, conector)

    assert r.status_code == 201, r.data
    assert r.data["material"] == "Conector SC/APC"
    assert r.data["cantidad"] == "20"
    assert r.data["estado"] == "pendiente"


def test_a2_la_cantidad_sale_SIN_ceros_de_relleno(user_client, conector):
    """PostgreSQL devuelve el Decimal con la escala de la columna. En Colombia
    el punto separa MILES: «20.000 conectores» se lee como veinte mil."""
    r = _pedir(user_client, conector)

    assert r.data["cantidad"] == "20"


def test_a3_puede_decir_para_que_orden_es(user_client, conector, orden):
    r = _pedir(user_client, conector, orden=str(orden.id))

    assert r.data["orden_numero"] == 9001


def test_a4_el_motivo_es_opcional(user_client, conector):
    """Parado en una escalera, escribir un motivo es lo primero que se saltea.
    Exigirlo haria que el pedido no se haga."""
    r = _pedir(user_client, conector)

    assert r.status_code == 201
    assert r.data["motivo"] == ""


def test_a6_se_pide_por_CODIGO_que_es_lo_que_el_telefono_tiene(
    user_client, conector
):
    """EL TELEFONO NO TIENE EL UUID.

    El kit que baja la aplicacion identifica el material por `codigo` --es lo
    que viaja en `local_kit` y lo que ya manda la cola de movimientos--. Exigir
    el UUID aca dejaria la pantalla con el dato con el que no se puede
    preguntar: el boton existiria y el pedido nunca se podria hacer.
    """
    r = user_client.post(
        RUTA,
        {"material": "CONN-SC", "cantidad": "20", "idempotency_key": "por-codigo"},
        format="json",
    )

    assert r.status_code == 201, r.data
    assert r.data["material"] == "Conector SC/APC"
    assert r.data["material_codigo"] == "CONN-SC"


def test_a7_un_material_que_no_existe_responde_404_no_un_500(user_client):
    """Un texto que no es un UUID entra al `filter(id=...)` y revienta la
    consulta. El tecnico veria «error del servidor» por haber pedido algo que
    simplemente no esta en el catalogo."""
    r = user_client.post(
        RUTA,
        {"material": "no-existe", "cantidad": "20", "idempotency_key": "k"},
        format="json",
    )

    assert r.status_code == 404


def test_a5_solo_ve_los_SUYOS(user_client, conector, org_a, django_user_model):
    """Esta pantalla contesta «¿pedi esto o no?». Lo que bodega necesita se
    atiende por el aviso, no por esta lista."""
    from common.models import Profile

    otro_user = django_user_model.objects.create_user(
        email="otro.tecnico@test.com", password="testpass123"
    )
    otro = Profile.objects.create(
        user=otro_user, org=org_a, role="USER", is_active=True
    )
    PedidoDeMaterial.objects.create(
        org=org_a, profile=otro, material=conector,
        cantidad=Decimal("5"), idempotency_key="de-otro",
    )
    _pedir(user_client, conector)

    r = user_client.get(RUTA)

    assert len(r.data["pedidos"]) == 1
    assert r.data["pedidos"][0]["cantidad"] == "20"


# --------------------------------------------------------------------------- #
# B. Idempotencia
# --------------------------------------------------------------------------- #

def test_b1_el_mismo_pedido_dos_veces_es_UNA_fila(user_client, conector, org_a):
    """Dos pedidos iguales le harian pensar a bodega que hacen falta cuarenta
    conectores cuando hacen falta veinte."""
    _pedir(user_client, conector)
    _pedir(user_client, conector)

    assert PedidoDeMaterial.objects.filter(org=org_a).count() == 1


def test_b2_el_reenvio_se_ve_como_EXITO_no_como_error(user_client, conector):
    """Para la cola de la app un error es motivo de reintento. Un 409 la
    dejaria reintentando para siempre."""
    _pedir(user_client, conector)

    r = _pedir(user_client, conector)

    assert r.status_code == 200
    assert r.data["estado"] == "pendiente"


def test_b3_sin_clave_no_se_acepta(user_client, conector):
    """Sin clave no hay forma de saber si es un reenvio. Aceptarlo seria
    garantizar el duplicado."""
    r = user_client.post(
        RUTA,
        {"material": str(conector.id), "cantidad": "20"},
        format="json",
    )

    assert r.status_code == 400


def test_b4_dos_pedidos_DISTINTOS_son_dos_filas(user_client, conector, org_a):
    """El contrapeso: que no se dupliquen no puede lograrse quedandose con uno
    solo. Un tecnico pide dos veces en el dia y las dos valen."""
    _pedir(user_client, conector, idempotency_key="clave-1")
    _pedir(user_client, conector, idempotency_key="clave-2")

    assert PedidoDeMaterial.objects.filter(org=org_a).count() == 2


# --------------------------------------------------------------------------- #
# C. Lo que no se acepta
# --------------------------------------------------------------------------- #

def test_c1_cantidad_cero_o_negativa_no_es_un_pedido(user_client, conector):
    """Llenaria la lista de bodega de filas que no piden nada."""
    for malo in ("0", "-5"):
        r = _pedir(user_client, conector, cantidad=malo)
        assert r.status_code == 400, malo


def test_c2_una_cantidad_que_no_es_numero_se_rechaza(user_client, conector):
    r = _pedir(user_client, conector, cantidad="muchos")

    assert r.status_code == 400


def test_c3_un_material_de_OTRA_EMPRESA_responde_404(user_client, org_b):
    """404 y no 403: una respuesta que distinga «no existe» de «no es tuyo» le
    diria a cualquiera que ese material existe en otra empresa."""
    ajeno = MaterialCatalogo.objects.create(
        org=org_b, codigo="CONN-B", nombre="Conector de otra empresa",
        unidad="u", clase=MaterialCatalogo.CONSUMIBLE,
    )

    r = _pedir(user_client, ajeno)

    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# D. Lo que un pedido NO hace
# --------------------------------------------------------------------------- #

def test_d1_pedir_NO_mueve_el_saldo(user_client, conector, org_a):
    """LA AFIRMACION QUE SOSTIENE AL INVENTARIO ENTERO.

    Un movimiento es un hecho que ya ocurrio; un pedido es que todavia no paso
    nada. Si pedir creara un movimiento, el saldo contaria material que nadie
    entrego -- y el descuadre de fin de mes seria imposible de explicar.
    """
    _pedir(user_client, conector)

    assert MovimientoDeMaterial.objects.filter(org=org_a).count() == 0


def test_d2_el_pedido_nace_PENDIENTE(user_client, conector):
    """Nadie lo atendio todavia. Nacer «atendido» seria afirmar una entrega que
    no ocurrio."""
    r = _pedir(user_client, conector)

    assert r.data["estado"] == "pendiente"


# --------------------------------------------------------------------------- #
# E. El aviso a bodega
# --------------------------------------------------------------------------- #

def test_e1_avisa_por_los_canales_de_la_empresa(user_client, conector):
    """Bodega ya recibe los avisos por donde los configuro. Construirle una
    pantalla aparte seria pedirle que mire dos lugares, y la que mira menos es
    siempre la nueva."""
    from campo.services import avisos

    with mock.patch.object(avisos, "_despachar") as despachar:
        _pedir(user_client, conector)

    despachar.assert_called_once()
    texto = despachar.call_args.kwargs["texto"]
    assert "Conector SC/APC" in texto
    assert "20" in texto


def test_e2_el_aviso_NO_lleva_datos_del_cliente(user_client, conector, orden):
    """A bodega no le hace falta saber a quien se le instala para sacar veinte
    conectores de una caja, y este mensaje sale del sistema."""
    from campo.services import avisos

    with mock.patch.object(avisos, "_despachar") as despachar:
        _pedir(user_client, conector, orden=str(orden.id))

    entero = str(despachar.call_args.kwargs)
    for dato in ("Beatriz", "Pinzón", "Calle 50", "312 455 8901"):
        assert dato not in entero, dato


def test_e3_un_REENVIO_no_vuelve_a_avisar(user_client, conector):
    """Bodega no tiene por que enterarse dos veces del mismo pedido."""
    from campo.services import avisos

    _pedir(user_client, conector)
    with mock.patch.object(avisos, "_despachar") as despachar:
        _pedir(user_client, conector)

    despachar.assert_not_called()


def test_e4_si_el_aviso_falla_el_pedido_EXISTE_igual(user_client, conector, org_a):
    """El hecho es la fila, no el mensaje. Un chat caido no puede dejar al
    tecnico sin material."""
    from campo.services import avisos

    with mock.patch.object(
        avisos, "_despachar", side_effect=RuntimeError("chat caido")
    ):
        try:
            _pedir(user_client, conector)
        except RuntimeError:
            pass

    assert PedidoDeMaterial.objects.filter(org=org_a).count() == 1
