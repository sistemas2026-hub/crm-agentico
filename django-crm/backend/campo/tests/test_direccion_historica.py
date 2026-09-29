# -*- coding: utf-8 -*-
"""
La migracion que le pone direccion a los movimientos que ya estaban.

POR QUE SE PRUEBA LA LOGICA Y NO "QUE LA MIGRACION EXISTE"
---------------------------------------------------------
Una migracion de datos es codigo que corre UNA vez, en produccion, sobre filas
que nadie volvio a mirar. Si esta mal, el error queda escrito. Por eso la logica
vive en una funcion --`rellenar(Movimiento, Ubicacion)`-- y esta prueba la
ejecuta con los modelos reales y filas de verdad, en vez de comprobar que el
archivo de migracion este en su carpeta.

Lo que se afirma es el EFECTO: que despues de correrla, la existencia de la
custodia del tecnico refleje el consumo que antes no restaba de ninguna parte.
"""

import importlib
from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv

pytestmark = pytest.mark.django_db

#: El modulo de la migracion, importado por su nombre: no es un identificador
#: valido de Python (empieza con un numero) asi que no se puede escribir un
#: `from ... import`.
_MIGRACION = importlib.import_module(
    "campo.migrations.0011_direccion_de_los_movimientos_historicos"
)


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-HIST", nombre="Conector historico"
    )


def _movimiento_viejo(org, profile, material, tipo, cantidad, clave):
    """Como los escribia la app antes del 28/09/2026: sin direccion."""
    return MovimientoDeMaterial.objects.create(
        org=org, profile=profile, material=material, tipo=tipo,
        cantidad=Decimal(str(cantidad)), idempotency_key=clave,
        ubicacion_origen=None, ubicacion_destino=None,
    )


def test_un_consumo_viejo_pasa_a_restar_de_la_custodia(org_a, user_profile,
                                                       conector):
    """Antes del arreglo ese consumo no restaba de ninguna ubicacion.

    Si la migracion no corriera, el consumo dejaria de contar en cualquier cuenta
    --antes contaba en `saldo_de`, que sumaba por tipo-- y eso seria perder
    informacion en silencio.
    """
    bodega = UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega historica")
    inv.registrar_entrada(org=org_a, material=conector, cantidad=100,
                          ubicacion_destino=bodega, origen_ref="HIST")
    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=user_profile, acta="ACTA-HIST",
                  lineas=[{"material": conector, "cantidad": 30}])
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)

    _movimiento_viejo(org_a, user_profile, conector,
                      MovimientoDeMaterial.CONSUMO, 12, "viejo-consumo")

    # Sin direccion, la custodia sigue diciendo 30: el consumo no resto.
    assert inv.existencia(custodia, conector) == Decimal("30")

    recuento = _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)

    assert recuento["consumo"] == 1
    assert inv.existencia(custodia, conector) == Decimal("18")


def test_una_devolucion_vieja_tambien(org_a, user_profile, conector):
    _movimiento_viejo(org_a, user_profile, conector,
                      MovimientoDeMaterial.DEVOLUCION, 5, "viejo-dev")

    _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)

    mov = MovimientoDeMaterial.objects.get(idempotency_key="viejo-dev")
    assert mov.ubicacion_origen is not None
    assert mov.ubicacion_origen.tipo == UbicacionInventario.TECNICO
    # El destino queda vacio A PROPOSITO: a que bodega llego no lo dice la fila,
    # y nadie firmo esa recepcion.
    assert mov.ubicacion_destino is None


def test_un_ajuste_viejo_no_se_toca(org_a, user_profile, conector):
    """Su direccion no esta en la fila, y suponerla seria inventarla.

    La cantidad de un ajuste viejo es positiva y `saldo_de` la sumaba, pero eso
    era una convencion del codigo, no un dato: nadie escribio si ese conteo
    agregaba o quitaba. Queda sin direccion y visible.
    """
    _movimiento_viejo(org_a, user_profile, conector,
                      MovimientoDeMaterial.AJUSTE, 3, "viejo-ajuste")

    recuento = _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)

    assert recuento.get("ajuste", 0) == 0
    mov = MovimientoDeMaterial.objects.get(idempotency_key="viejo-ajuste")
    assert mov.ubicacion_origen is None and mov.ubicacion_destino is None


def test_correrla_dos_veces_no_cambia_nada(org_a, user_profile, conector):
    """Idempotente: una fila que ya tiene direccion no entra en el filtro."""
    _movimiento_viejo(org_a, user_profile, conector,
                      MovimientoDeMaterial.CONSUMO, 7, "viejo-dos-veces")

    primera = _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)
    segunda = _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)

    assert primera["consumo"] == 1
    assert segunda["consumo"] == 0
    assert UbicacionInventario.objects.filter(
        org=org_a, tipo=UbicacionInventario.TECNICO, profile=user_profile
    ).count() == 1


def test_un_movimiento_que_ya_tenia_direccion_se_respeta(org_a, user_profile,
                                                         conector):
    bodega = UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega intacta")
    entrada = inv.registrar_entrada(org=org_a, material=conector, cantidad=50,
                                    ubicacion_destino=bodega, origen_ref="INT")

    _MIGRACION.rellenar(MovimientoDeMaterial, UbicacionInventario)

    entrada.refresh_from_db()
    assert entrada.ubicacion_destino_id == bodega.id
    assert entrada.ubicacion_origen is None
