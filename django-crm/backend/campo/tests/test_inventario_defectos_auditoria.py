# -*- coding: utf-8 -*-
"""
Los defectos que encontro la pasada adversarial del 28/09/2026, MEDIDOS.

POR QUE ESTAS PRUEBAS EXISTEN ANTES DEL ARREGLO
-----------------------------------------------
Un auditor independiente reporto cinco defectos graves y todos tenian la misma
forma: el modulo de inventario es internamente coherente y asume que el resto del
sistema se movio con el, y el resto del sistema no se toco. Antes de arreglar nada
hay que MEDIR que los defectos existen -- si no, se arregla una hipotesis.

Cada prueba de aca falla HOY y describe el defecto ejecutandolo. Cuando el arreglo
entre, pasan a verde y se quedan como la guarda de que no vuelve.

Y las tres son aritmetica sobre datos, no grep sobre texto. Eso es lo que la
guarda anterior (test_inventario_una_sola_verdad) no hacia, y por eso no cazo
nada de esto: comprobaba que `existencia()` estuviera definida una sola vez, no
que dos caminos dieran el mismo numero.
"""

from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import ReservaDeMaterial
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv
from campo.services import inventario_operacion as op
from campo.services.materiales import registrar_movimiento, saldo_de

pytestmark = pytest.mark.django_db


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
def orden(org_a):
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    ver = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={}
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=8001, tipo_trabajo_version=ver,
        cliente_nombre="Prueba", cliente_direccion="Calle 1",
    )


# ---------------------------------------------------------------------------
# DEFECTO 1 -- el consumo del tecnico no sale de ninguna ubicacion
# ---------------------------------------------------------------------------

def test_defecto1_el_consumo_del_tecnico_baja_la_existencia_de_su_custodia(
    org_a, bodega, conector, user_profile, orden
):
    """EL MAS GRAVE, y el que ya esta en produccion.

    `registrar_movimiento` --el que usa la app del tecnico-- no escribe
    `ubicacion_origen` ni `ubicacion_destino`. Asi que un consumo no resta de la
    custodia, y la existencia de una custodia SOLO SUBE: la pantalla muestra
    material que esta dentro de las paredes de las casas de los clientes.

    Medido: se despacha 100, el tecnico consume 100, y la custodia sigue
    diciendo 100.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 100}],
    )
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    assert inv.existencia(custodia, conector) == Decimal("100")

    # El tecnico los consume en la calle y la app lo sincroniza.
    registrar_movimiento(
        org=org_a, profile=user_profile, material=conector,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=100,
        idempotency_key="consumo-del-tecnico", orden=orden,
    )

    # La app del tecnico dice 0. La pantalla de inventario tiene que decir lo
    # mismo: son la misma pregunta.
    assert saldo_de(user_profile, conector) == Decimal("0")
    assert inv.existencia(custodia, conector) == Decimal("0"), (
        "la custodia sigue mostrando material que ya se instalo en casas de "
        "clientes: el consumo no resto de ninguna ubicacion"
    )


def test_defecto1_la_valorizacion_no_cuenta_material_ya_instalado(
    org_a, bodega, conector, user_profile, orden
):
    """La consecuencia en plata: el valorizado de la empresa nunca baja."""
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega, referencia="F-DEF1",
        lineas=[{"material": conector, "cantidad": 100, "costo_unitario": "1000"}],
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 100}],
    )
    registrar_movimiento(
        org=org_a, profile=user_profile, material=conector,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=100,
        idempotency_key="consumo-valorizado", orden=orden,
    )
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    v = op.valorizacion(custodia)
    assert v["total"] == "0.00", (
        f"la custodia se valoriza en {v['total']} de material que ya esta "
        f"instalado en casas de clientes"
    )


# ---------------------------------------------------------------------------
# DEFECTO 2 -- saldo_de y existencia no son la misma cuenta
# ---------------------------------------------------------------------------

def test_defecto2_un_ajuste_de_conteo_mueve_los_dos_numeros_igual(
    org_a, bodega, conector, user_profile
):
    """`existencia` respeta la direccion del ajuste; `saldo_de` hace `+ ajustado`.

    Un conteo que le QUITA material al tecnico le AGRANDA el cupo segun
    `saldo_de` -- y `clasificar()` usa ese numero para decidir si un consumo es
    descuadre. O sea que un ajuste a la baja desactiva la clasificacion.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 50}],
    )
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)

    conteo = op.abrir_conteo(org=org_a, ubicacion=custodia,
                             contado_por=user_profile)
    op.anotar_conteo(conteo, material=conector, cantidad=48,
                     motivo="faltaban dos")
    op.cerrar_conteo(conteo, profile=user_profile)

    assert inv.existencia(custodia, conector) == Decimal("48")
    assert saldo_de(user_profile, conector) == Decimal("48"), (
        f"existencia dice 48 y saldo_de dice "
        f"{saldo_de(user_profile, conector)}: el ajuste tiene el signo al revés "
        f"en una de las dos cuentas"
    )


# ---------------------------------------------------------------------------
# DEFECTO 3 -- la reserva nunca se resuelve
# ---------------------------------------------------------------------------

def test_defecto3_despachar_lo_reservado_libera_la_reserva(
    org_a, bodega, conector, user_profile
):
    """Si no, el mismo material se descuenta dos veces y para siempre.

    Se reservan 10, se despachan esos 10. `existencia` baja a 90 y `reservado`
    tendria que bajar a 0 -- si no, `libre` dice 80 cuando hay 90.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    op.reservar(org=org_a, ubicacion=bodega, material=conector, cantidad=10)
    assert op.libre(bodega, conector) == Decimal("90")

    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": conector, "cantidad": 10}],
    )

    assert inv.existencia(bodega, conector) == Decimal("90")
    assert op.reservado(bodega, conector) == Decimal("0"), (
        "la reserva sigue activa despues de despacharse: el mismo material "
        "queda descontado dos veces, y el error es permanente"
    )
    assert op.libre(bodega, conector) == Decimal("90")


# ---------------------------------------------------------------------------
# DEFECTO 4 -- la clave del despacho sale de una fila creada en la misma llamada
# ---------------------------------------------------------------------------

def test_defecto4_dos_despachos_identicos_no_duplican_material(
    org_a, bodega, conector, user_profile
):
    """La clave lleva `entrega.id`, y la entrega se crea en esa misma llamada.

    Asi que la clave es nueva en cada intento: no hay idempotencia. Un doble clic
    o el reintento de un proxy despacha dos veces. Con serie queda tapado por
    `_comprobar_serie_libre`; todo lo NO serializado --que es la mayoria del
    volumen-- queda expuesto.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    lineas = [{"material": conector, "cantidad": 50}]

    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=user_profile, lineas=lineas, acta="K-1")
    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=user_profile, lineas=lineas, acta="K-1")

    # El mismo acta dos veces es el mismo hecho: la segunda no puede descontar.
    assert inv.existencia(bodega, conector) == Decimal("50"), (
        f"la bodega quedo en {inv.existencia(bodega, conector)}: el segundo "
        f"despacho del mismo acta descontó otra vez"
    )


# ---------------------------------------------------------------------------
# DEFECTO 5 -- las claves estables COLISIONAN entre operaciones distintas
# ---------------------------------------------------------------------------

def test_defecto5_dos_entradas_iguales_en_dias_distintos_entran_las_dos(
    org_a, bodega, conector
):
    """La clave de una entrada no lleva nada que distinga una de la siguiente.

    Llegan 10 conectores el lunes y otros 10 el miercoles, sin remision. La clave
    es identica -> la segunda entrada NO ENTRA, y el material esta sobre la mesa.
    Eso rompe la regla de que un hecho ya ocurrido no se rechaza.
    """
    inv.registrar_entrada(org=org_a, material=conector, cantidad=10,
                          ubicacion_destino=bodega)
    inv.registrar_entrada(org=org_a, material=conector, cantidad=10,
                          ubicacion_destino=bodega)
    assert inv.existencia(bodega, conector) == Decimal("20"), (
        f"la bodega quedo en {inv.existencia(bodega, conector)}: la segunda "
        f"entrada se perdio por colision de clave idempotente"
    )


# ---------------------------------------------------------------------------
# DEFECTO 9 -- el puntero del activo no sigue al consumo
# ---------------------------------------------------------------------------

def test_defecto9_al_instalar_una_ont_el_puntero_deja_de_decir_la_custodia(
    org_a, bodega, user_profile, orden
):
    """`_mover_activo` tiene cinco llamadores y el consumo no es uno.

    Consecuencia: la pantalla dice que la ONT esta en la custodia del tecnico
    cuando esta en la casa de un cliente, y `cuadra_con_el_libro` es False para
    TODO serial instalado -- el indicador que existe para detectar el defecto se
    satura y deja de significar algo.
    """
    ont = MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-DEF9", nombre="ONT",
        clase=MaterialCatalogo.SERIALIZADO,
    )
    inv.registrar_entrada(org=org_a, material=ont, cantidad=1,
                          ubicacion_destino=bodega, serie="DEF9-1")
    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=user_profile,
                  lineas=[{"material": ont, "serie": "DEF9-1"}])

    registrar_movimiento(
        org=org_a, profile=user_profile, material=ont,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=1, serie="DEF9-1",
        idempotency_key="consumo-ont-def9", orden=orden,
    )

    activo = inv.activo_de(org_a, ont, "DEF9-1", crear=False)
    pos = inv.posicion_de(activo)
    recalc, _ = inv.posicion_recalculada(activo)
    assert (pos.ubicacion_id if pos else None) == (recalc.id if recalc else None), (
        "el puntero y el libro no coinciden para un serial instalado: el puntero "
        "dice la custodia y el libro dice fuera de custodia"
    )

# ---------------------------------------------------------------------------
# DEFECTO 10 -- reservar valida sin bloquear
# ---------------------------------------------------------------------------
#
# Vive en `test_inventario_concurrencia_postgres.py` y no aca, por una razon que
# se midio: una carrera necesita que los dos hilos VEAN los datos, y las pruebas
# de este archivo corren dentro de una transaccion que nunca se commitea
# (`django_db` a secas). Contra PostgreSQL real los dos hilos abrian su propia
# conexion, no veian la entrada de 100 unidades, y las dos reservas se rechazaban
# por falta de material: la prueba fallaba sin probar nada sobre el bloqueo --
# que es justo el error que este archivo existe para no cometer.
#
# El modo correcto es `django_db(transaction=True)`, y ese archivo ya lo declara
# a nivel de modulo con su motivo escrito.
