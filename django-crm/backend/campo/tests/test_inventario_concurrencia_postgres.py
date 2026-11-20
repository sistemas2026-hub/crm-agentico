# -*- coding: utf-8 -*-
"""
A4 contra PostgreSQL de verdad: dos despachos de la misma serie, a la vez.

POR QUE ESTA PRUEBA EXISTE APARTE DE LA DE test_inventario_ciclo
---------------------------------------------------------------
Esa prueba comprueba A4 de forma SECUENCIAL: se despacha, y el segundo despacho
se rechaza. Es correcta y no alcanza, porque la garantia depende de un
`select_for_update` sobre la posicion del activo, y **SQLite no implementa
bloqueo de fila**: ahi la comprobacion pasa por el orden de las operaciones, no
por el bloqueo. O sea que la suite podia estar verde con la carrera abierta.

Es la misma familia de defecto que ya se cobro en este modulo el 28/09/2026: la
clave idempotente no cabia en su varchar(128) y las pruebas pasaban porque
SQLite no impone la longitud. Dos veces el mismo patron -- **el motor de la
prueba no es el motor de produccion** -- y por eso este proyecto exige probar
persistencia contra PostgreSQL real.

QUE SE AFIRMA, Y QUE NO
-----------------------
Se afirma sobre el EFECTO: que al terminar haya UN despacho aceptado de esa serie
y una sola posicion. No sobre cual de los dos hilos gano, que es indistinto y
depende del planificador -- una prueba que exigiera un ganador concreto fallaria
por lo que no importa.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection

from campo.inventario import ActivoSerializado, UbicacionDeActivo, UbicacionInventario
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv
from campo.services import inventario_operacion as op
from common.models import Profile

pytestmark = pytest.mark.django_db(transaction=True)

SERIE = "CONC-HWT-0001"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Concurrente"
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-CONC", nombre="ONT de concurrencia",
        clase=MaterialCatalogo.SERIALIZADO,
    )


@pytest.fixture
def dos_tecnicos(org_a, django_user_model):
    personas = []
    for i in (1, 2):
        u = django_user_model.objects.create_user(
            email=f"conc{i}@test.com", password="testpass123"
        )
        personas.append(
            Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
        )
    return personas


@pytest.mark.postgres_only
def test_a4_dos_despachos_concurrentes_de_la_misma_serie(
    org_a, bodega, ont, dos_tecnicos
):
    if connection.vendor != "postgresql":
        pytest.skip(
            "A4 depende de select_for_update, que SQLite no implementa: en SQLite "
            "esta prueba pasaria sin probar el bloqueo. NO SE PUDO MEDIR."
        )

    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega, serie=SERIE
    )
    uno, otro = dos_tecnicos

    def despachar_a(tecnico):
        try:
            inv.despachar(
                org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
                lineas=[{"material": ont, "serie": SERIE}],
            )
            return "ok"
        except inv.DespachoInvalido:
            return "rechazado"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(despachar_a, [uno, otro]))

    # Uno gana y el otro se rechaza. Cual de los dos, es indistinto.
    assert sorted(resultados) == ["ok", "rechazado"], (
        f"los dos despachos terminaron asi: {resultados}. Si los dos dicen 'ok', "
        f"la misma ONT quedo en dos manos y el bloqueo no funciono."
    )

    aceptados = MovimientoDeMaterial.objects.filter(
        org=org_a, serie=SERIE, tipo=MovimientoDeMaterial.DESPACHO
    ).count()
    assert aceptados == 1, f"hay {aceptados} despachos de la misma serie"

    activo = ActivoSerializado.objects.get(org=org_a, material=ont, serie=SERIE)
    assert UbicacionDeActivo.objects.filter(activo=activo).count() == 1

    # Y el indice tiene que cuadrar con el libro despues de la carrera: es
    # justo el momento en que un puntero mal escrito quedaria mintiendo.
    pos = inv.posicion_de(activo)
    recalc, _ = inv.posicion_recalculada(activo)
    assert (pos.ubicacion_id if pos else None) == (recalc.id if recalc else None)


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-CONC", nombre="Conector de concurrencia",
        clase=MaterialCatalogo.CONSUMIBLE,
    )


@pytest.mark.postgres_only
def test_dos_reservas_concurrentes_no_pueden_pasarse_del_stock(
    org_a, bodega, conector
):
    """La segunda carrera del modulo, y la que faltaba: reservar.

    `_comprobar_serie_libre` razonaba sobre su carrera desde el principio;
    `reservar` no. Dos despachadores reservan 60 de 100 al mismo tiempo: los dos
    leen `libre = 100`, los dos pasan la validacion, `reservado` queda en 120 y
    `libre` en -20. Es exactamente el caso que la tabla de reservas existe para
    evitar -- prometerle material a un tecnico que no lo va a encontrar.

    No hay fila de stock que bloquear --`libre` es una suma sobre dos tablas-- asi
    que el candado va sobre la fila de la UBICACION, que es lo unico estable que
    todas las reservas de esa bodega comparten.
    """
    if connection.vendor != "postgresql":
        pytest.skip(
            "la carrera depende de select_for_update, que SQLite no implementa: "
            "ahi las dos reservas se ordenarian solas. NO SE PUDO MEDIR."
        )

    inv.registrar_entrada(org=org_a, material=conector, cantidad=100,
                          ubicacion_destino=bodega)

    def reservar_60(_):
        try:
            op.reservar(org=org_a, ubicacion=bodega, material=conector,
                        cantidad=60)
            return "ok"
        except op.ReservaInvalida:
            return "rechazada"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(reservar_60, [1, 2]))

    # Una gana y la otra se rechaza. Cual, es indistinto.
    assert sorted(resultados) == ["ok", "rechazada"], (
        f"las dos reservas terminaron asi: {resultados}. `reservado` quedo en "
        f"{op.reservado(bodega, conector)} sobre una existencia de 100."
    )
    assert op.libre(bodega, conector) >= 0
