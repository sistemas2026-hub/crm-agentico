# -*- coding: utf-8 -*-
"""
Fase 2 y 3: reservas, conteo fisico, traslados, compras y valorizacion.

LO QUE DEFIENDEN ESTAS PRUEBAS
------------------------------
Las tres cuentas nuevas --reservado, libre, valorizacion-- son las que mas facil
se convertirian en columnas. Cada una tiene su prueba de que sale de una suma y
de que el numero cambia cuando cambian los hechos, no cuando alguien actualiza un
contador.

Y las dos decisiones que mas facil se romperian sin querer:

  el conteo no corrige, PRODUCE UN AJUSTE. Un conteo que sobreescribiera el saldo
    perderia la diferencia, que es lo unico interesante que tiene
  lo que no se puede valorizar SE NOMBRA. Un total que se come en silencio lo que
    no sabe valorizar es la forma mas rapida de que alguien decida con un numero
    que parece completo
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from campo.inventario import UbicacionInventario
from campo.inventario_operacion import (
    Compra,
    ConteoFisico,
    Proveedor,
    ReservaDeMaterial,
)
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv
from campo.services import inventario_operacion as op

pytestmark = pytest.mark.django_db


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
def camioneta(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.VEHICULO, nombre="Camioneta 1"
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC", unidad="unidades"
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei",
        clase=MaterialCatalogo.SERIALIZADO,
    )


@pytest.fixture
def con_cien(org_a, bodega, conector):
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega
    )
    return conector


# ===========================================================================
# FASE 2 -- RESERVAS
# ===========================================================================

def test_reservar_baja_lo_libre_pero_no_la_existencia(org_a, bodega, con_cien):
    """El material sigue EN la bodega: alguien puede verlo ahi."""
    assert inv.existencia(bodega, con_cien) == Decimal("100")
    assert op.libre(bodega, con_cien) == Decimal("100")

    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)

    # La existencia NO cambia: el libro de movimientos dice la verdad sobre lo
    # que hay fisicamente, y eso es lo que promete.
    assert inv.existencia(bodega, con_cien) == Decimal("100")
    assert op.reservado(bodega, con_cien) == Decimal("30")
    assert op.libre(bodega, con_cien) == Decimal("70")


def test_no_se_puede_reservar_mas_de_lo_libre(org_a, bodega, con_cien):
    """Una promesa que no se puede cumplir es peor que no hacerla."""
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=80)

    with pytest.raises(op.ReservaInvalida) as e:
        op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)

    # El mensaje dice los tres numeros: sin ellos, quien lo lee tiene que ir a
    # buscar por que no alcanza.
    assert "quedan 20" in str(e.value)
    assert "100" in str(e.value) and "80" in str(e.value)


def test_una_serie_no_se_reserva_dos_veces(org_a, bodega, ont):
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="RES-1",
    )
    op.reservar(org=org_a, ubicacion=bodega, material=ont, serie="RES-1")

    with pytest.raises(op.ReservaInvalida) as e:
        op.reservar(org=org_a, ubicacion=bodega, material=ont, serie="RES-1")
    assert "ya esta reservada" in str(e.value)


def test_liberar_no_borra_la_fila(org_a, bodega, con_cien):
    """La pregunta "por que faltaron ONT el martes" se contesta con esto."""
    r = op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)
    op.liberar(r, motivo="la orden se cayo")

    assert op.libre(bodega, con_cien) == Decimal("100")
    # Sigue existiendo, con su desenlace y su motivo.
    r.refresh_from_db()
    assert r.resuelta_en is not None
    assert r.desenlace == ReservaDeMaterial.LIBERADA
    assert "la orden se cayo" in r.motivo
    assert ReservaDeMaterial.objects.filter(org=org_a).count() == 1


def test_una_reserva_vencida_deja_de_bloquear(org_a, bodega, con_cien):
    """Un plazo vencido es un desenlace, no un limbo."""
    op.reservar(
        org=org_a, ubicacion=bodega, material=con_cien, cantidad=40,
        vence_en=timezone.now() - timedelta(hours=1),
    )
    assert op.libre(bodega, con_cien) == Decimal("60")

    vencidas = op.vencer_reservas(org_a)

    assert len(vencidas) == 1
    assert vencidas[0].desenlace == ReservaDeMaterial.VENCIDA
    assert op.libre(bodega, con_cien) == Decimal("100")


def test_una_reserva_SIN_plazo_no_se_vence_sola(org_a, bodega, con_cien):
    """El control de la prueba de arriba.

    Vencer una reserva sin plazo seria romper una promesa por una regla que nadie
    declaro.
    """
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=40)
    assert op.vencer_reservas(org_a) == []
    assert op.libre(bodega, con_cien) == Decimal("60")


# ===========================================================================
# FASE 2 -- TRASLADOS
# ===========================================================================

def test_trasladar_mueve_de_una_bodega_a_otra(org_a, bodega, bodega_norte, con_cien):
    op.trasladar(
        org=org_a, ubicacion_origen=bodega, ubicacion_destino=bodega_norte,
        lineas=[{"material": con_cien, "cantidad": 25}], motivo="reparto semanal",
    )
    assert inv.existencia(bodega, con_cien) == Decimal("75")
    assert inv.existencia(bodega_norte, con_cien) == Decimal("25")


def test_trasladar_a_la_misma_ubicacion_se_rechaza(org_a, bodega, con_cien):
    with pytest.raises(inv.DespachoInvalido) as e:
        op.trasladar(
            org=org_a, ubicacion_origen=bodega, ubicacion_destino=bodega,
            lineas=[{"material": con_cien, "cantidad": 5}],
        )
    assert "no es un traslado" in str(e.value)


def test_trasladar_una_serie_mueve_su_posicion(org_a, bodega, camioneta, ont):
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="TRAS-1",
    )
    op.trasladar(
        org=org_a, ubicacion_origen=bodega, ubicacion_destino=camioneta,
        lineas=[{"material": ont, "serie": "TRAS-1"}],
    )
    activo = inv.activo_de(org_a, ont, "TRAS-1", crear=False)
    assert inv.posicion_de(activo).ubicacion_id == camioneta.id
    # Y el indice cuadra con el libro, que es lo que lo hace confiable.
    recalc, _ = inv.posicion_recalculada(activo)
    assert recalc.id == camioneta.id


def test_no_se_traslada_una_serie_que_no_esta_en_el_origen(
    org_a, bodega, bodega_norte, camioneta, ont
):
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="TRAS-2",
    )
    with pytest.raises(inv.DespachoInvalido) as e:
        op.trasladar(
            org=org_a, ubicacion_origen=bodega_norte,
            ubicacion_destino=camioneta,
            lineas=[{"material": ont, "serie": "TRAS-2"}],
        )
    assert "TRAS-2" in str(e.value)


# ===========================================================================
# FASE 2 -- CONTEO FISICO
# ===========================================================================

def test_el_conteo_produce_un_ajuste_y_no_reescribe_el_saldo(
    org_a, bodega, con_cien, user_profile
):
    """La diferencia entra al libro, con su motivo. No desaparece."""
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega, contado_por=user_profile)
    op.anotar_conteo(conteo, material=con_cien, cantidad=95,
                     motivo="faltaban cinco en el estante")

    lineas, ajustes = op.cerrar_conteo(conteo, profile=user_profile)

    assert len(ajustes) == 1
    ajuste = ajustes[0]
    assert ajuste.tipo == MovimientoDeMaterial.AJUSTE
    assert ajuste.cantidad == Decimal("5")
    # Falta material -> SALE de la bodega. La direccion importa: un ajuste sin
    # direccion no se puede sumar.
    assert ajuste.ubicacion_origen_id == bodega.id
    assert ajuste.ubicacion_destino is None
    assert "contado 95" in ajuste.motivo and "el sistema decia 100" in ajuste.motivo
    assert "faltaban cinco" in ajuste.motivo

    # Y la existencia queda en lo contado, POR EL AJUSTE y no por un UPDATE.
    assert inv.existencia(bodega, con_cien) == Decimal("95")

    # Lo que el sistema decia queda congelado en la linea.
    assert lineas[0].existencia_sistema == Decimal("100")


def test_un_sobrante_entra_a_la_bodega(org_a, bodega, con_cien, user_profile):
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    op.anotar_conteo(conteo, material=con_cien, cantidad=108,
                     motivo="aparecieron ocho de una devolucion sin registrar")
    _, ajustes = op.cerrar_conteo(conteo, profile=user_profile)

    assert ajustes[0].ubicacion_destino_id == bodega.id
    assert ajustes[0].ubicacion_origen is None
    assert inv.existencia(bodega, con_cien) == Decimal("108")


def test_una_linea_que_cuadra_no_genera_movimiento(org_a, bodega, con_cien):
    """El conteo dice tambien lo que estaba bien, y eso es informacion."""
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    op.anotar_conteo(conteo, material=con_cien, cantidad=100)
    lineas, ajustes = op.cerrar_conteo(conteo)

    assert ajustes == []
    assert lineas[0].ajuste is None
    assert lineas[0].existencia_sistema == Decimal("100")


def test_una_diferencia_sin_motivo_lo_dice_en_el_ajuste(
    org_a, bodega, con_cien
):
    """Lo que falta se nombra, incluso cuando lo que falta es la explicacion."""
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    op.anotar_conteo(conteo, material=con_cien, cantidad=90)
    _, ajustes = op.cerrar_conteo(conteo)
    assert "SIN MOTIVO DECLARADO" in ajustes[0].motivo


def test_no_hay_dos_conteos_abiertos_de_la_misma_bodega(org_a, bodega):
    op.abrir_conteo(org=org_a, ubicacion=bodega)
    with pytest.raises(op.ConteoInvalido) as e:
        op.abrir_conteo(org=org_a, ubicacion=bodega)
    assert "dos conteos abiertos producen dos verdades" in str(e.value)


def test_un_conteo_cerrado_no_se_puede_seguir_anotando(org_a, bodega, con_cien):
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    op.anotar_conteo(conteo, material=con_cien, cantidad=100)
    op.cerrar_conteo(conteo)
    with pytest.raises(op.ConteoInvalido) as e:
        op.anotar_conteo(conteo, material=con_cien, cantidad=90)
    assert "reescribiria la historia" in str(e.value)


def test_un_conteo_vacio_no_se_cierra(org_a, bodega):
    """Cerrarlo dejaria constancia de que se conto cuando no."""
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    with pytest.raises(op.ConteoInvalido) as e:
        op.cerrar_conteo(conteo)
    assert "no dice nada sobre la bodega" in str(e.value)


# ===========================================================================
# FASE 3 -- COMPRAS, COSTO Y VALORIZACION
# ===========================================================================

def test_una_compra_entra_al_mismo_libro_con_su_costo(
    org_a, bodega, conector, user_profile
):
    prov = Proveedor.objects.create(org=org_a, nombre="Fibras del Norte")
    compra, movs = op.registrar_compra(
        org=org_a, ubicacion_destino=bodega, proveedor=prov,
        referencia="FAC-8891", recibida_por=user_profile,
        lineas=[{"material": conector, "cantidad": 200, "costo_unitario": "1500.00"}],
    )

    assert inv.existencia(bodega, conector) == Decimal("200")
    assert movs[0].tipo == MovimientoDeMaterial.ENTRADA
    assert movs[0].costo_unitario == Decimal("1500.0000")
    assert movs[0].compra_id == compra.id


def test_el_costo_es_promedio_ponderado_y_se_declara(org_a, bodega, conector):
    """Dos lotes a distinto precio dan el ponderado, no el ultimo ni el primero."""
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 100, "costo_unitario": "1000"}],
        referencia="F1",
    )
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 300, "costo_unitario": "2000"}],
        referencia="F2",
    )
    # (100*1000 + 300*2000) / 400 = 1750
    assert op.costo_promedio(org_a, conector) == Decimal("1750.0000")


def test_sin_costo_conocido_devuelve_None_y_no_cero(org_a, bodega, con_cien):
    """Cero diria que es gratis, que es distinto de no saberlo."""
    assert op.costo_promedio(org_a, con_cien) is None


def test_la_valorizacion_nombra_lo_que_no_puede_valorizar(
    org_a, bodega, conector, ont
):
    """Un total que se come en silencio lo que no sabe es un total que miente."""
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 100, "costo_unitario": "1500"}],
        referencia="F-VAL",
    )
    # La ONT entra SIN costo: un equipo retirado de un cliente no se compro.
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="SIN-COSTO-1",
    )

    v = op.valorizacion(bodega)

    assert v["total"] == "150000.00"
    assert len(v["sin_costo_conocido"]) == 1
    assert v["sin_costo_conocido"][0]["codigo"] == "ONT-HG8145"
    # Y lo DICE, no lo esconde en una nota al pie que nadie lee.
    assert "1 material(es) sin costo conocido no entran en el total" in v["advertencia"]


def test_sin_material_sin_costo_no_hay_advertencia(org_a, bodega, conector):
    """El control: cuando se puede valorizar todo, no se avisa de nada."""
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 10, "costo_unitario": "100"}],
        referencia="F-OK",
    )
    v = op.valorizacion(bodega)
    assert v["sin_costo_conocido"] == []
    assert v["advertencia"] == ""


def test_una_factura_no_se_registra_dos_veces_del_mismo_proveedor(org_a, bodega,
                                                                 conector):
    from django.db.utils import IntegrityError
    prov = Proveedor.objects.create(org=org_a, nombre="Fibras del Sur")
    op.registrar_compra(
        org=org_a, ubicacion_destino=bodega, proveedor=prov, referencia="F-777",
        lineas=[{"material": conector, "cantidad": 10, "costo_unitario": "1"}],
    )
    with pytest.raises(IntegrityError):
        op.registrar_compra(
            org=org_a, ubicacion_destino=bodega, proveedor=prov, referencia="F-777",
            lineas=[{"material": conector, "cantidad": 10, "costo_unitario": "1"}],
        )


# ===========================================================================
# REPORTES
# ===========================================================================

def test_el_consumo_se_agrupa_por_material(org_a, bodega, con_cien, ont,
                                           user_profile):
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=user_profile,
        lineas=[{"material": con_cien, "cantidad": 40}],
    )
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    for cant in (10, 15):
        MovimientoDeMaterial.objects.create(
            org=org_a, profile=user_profile, material=con_cien,
            tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal(str(cant)),
            ubicacion_origen=custodia,
            idempotency_key=f"consumo-prueba-{cant}",
        )

    filas = op.consumo_por_material(org_a)
    assert len(filas) == 1
    assert filas[0]["codigo"] == "CON-SC-APC"
    assert filas[0]["consumido"] == "25.000"


def test_un_conflicto_no_cuenta_como_consumo(org_a, bodega, con_cien,
                                             user_profile):
    """Por definicion no ocurrio: alguien mas ya habia consumido esa serie."""
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a)
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=con_cien,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("7"),
        estado=MovimientoDeMaterial.CONFLICTO,
        ubicacion_origen=custodia, idempotency_key="conflicto-prueba",
    )
    assert op.consumo_por_material(org_a) == []


def test_los_descuadres_se_listan_con_su_motivo(org_a, bodega, con_cien,
                                                user_profile):
    """Una lista se puede resolver; un contador se mira una vez y se ignora."""
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a)
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=con_cien,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("3"),
        estado=MovimientoDeMaterial.DESCUADRE,
        motivo="no tenia saldo de este material",
        ubicacion_origen=custodia, idempotency_key="descuadre-prueba",
    )
    filas = op.descuadres_abiertos(org_a)
    assert len(filas) == 1
    assert filas[0]["estado"] == "descuadre"
    assert filas[0]["motivo"] == "no tenia saldo de este material"
    assert filas[0]["persona"]


def test_el_consumo_por_tecnico_no_calcula_eficiencia(org_a, bodega, con_cien,
                                                      user_profile):
    """Se devuelve el dato crudo a proposito.

    Dos tecnicos con distinto tipo de trabajo no son comparables por metros de
    fibra, y un numero que parece comparable se usa como si lo fuera.
    """
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a)
    MovimientoDeMaterial.objects.create(
        org=org_a, profile=user_profile, material=con_cien,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("12"),
        ubicacion_origen=custodia, idempotency_key="por-tecnico-1",
    )
    filas = op.consumo_por_tecnico(org_a)
    assert len(filas) == 1
    assert filas[0]["materiales"] == [{"codigo": "CON-SC-APC", "consumido": "12.000"}]
    # Ninguna clave que insinue un ranking.
    assert "eficiencia" not in filas[0] and "promedio" not in filas[0]


# ===========================================================================
# Aislamiento
# ===========================================================================

def test_las_reservas_no_cruzan_organizaciones(org_a, org_b, bodega, con_cien):
    op.reservar(org=org_a, ubicacion=bodega, material=con_cien, cantidad=30)
    bodega_b = UbicacionInventario.objects.create(
        org=org_b, tipo=UbicacionInventario.BODEGA, nombre="Bodega de la otra"
    )
    material_b = MaterialCatalogo.objects.create(
        org=org_b, codigo="CON-SC-APC", nombre="Conector de la otra"
    )
    assert op.reservado(bodega_b, material_b) == Decimal("0")
    assert op.reservas_de(bodega_b) == []
    assert op.consumo_por_material(org_b) == []
    assert op.descuadres_abiertos(org_b) == []
