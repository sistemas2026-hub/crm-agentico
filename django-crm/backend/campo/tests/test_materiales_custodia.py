# -*- coding: utf-8 -*-
"""
La custodia de materiales: lo que el técnico tiene, gasta y debe.

QUÉ CUIDAN ESTAS PRUEBAS
------------------------
Una sola idea, y es contraintuitiva: **un movimiento de material no se
rechaza**. Es un hecho que ya ocurrió en la calle. Lo que el servidor decide
no es si permitirlo, sino cómo clasificarlo para que alguien lo mire después.

Eso hace que las pruebas importantes sean las de los casos "malos": un consumo
sin saldo tiene que ENTRAR (y quedar marcado), no fallar. Una implementación
que devuelva 400 ahí parece más estricta y en realidad es peor, porque borra
el único registro de que el material se usó.

La excepción es la serie repetida: dos técnicos no instalaron la misma ONT.
"""

from decimal import Decimal

import pytest

from campo.models import (
    EntregaDeKit,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services.materiales import (
    kit_de,
    materiales_sin_cuadrar,
    registrar_movimiento,
    saldo_de,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC",
        categoria="Conectividad", clase=MaterialCatalogo.CONSUMIBLE,
        unidad="unidades",
    )


@pytest.fixture
def fibra(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="FIB-DROP", nombre="Fibra drop",
        categoria="Cableado", clase=MaterialCatalogo.BOBINA, unidad="m",
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei HG8145V5",
        categoria="Equipos", clase=MaterialCatalogo.SERIALIZADO, unidad="unidades",
    )


@pytest.fixture
def kit(org_a, user_profile, conector, fibra, ont):
    """Lo que la bodega le entregó al técnico esta mañana."""
    entrega = EntregaDeKit.objects.create(
        org=org_a, profile=user_profile, acta="K-2024-094",
    )
    ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=24)
    ItemDeKit.objects.create(entrega=entrega, material=fibra, cantidad=300)
    ItemDeKit.objects.create(
        entrega=entrega, material=ont, cantidad=1, serie="48575448A9B0C1"
    )
    return entrega


def consumir(org, profile, material, cantidad, clave, **extra):
    return registrar_movimiento(
        org=org, profile=profile, material=material,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=cantidad,
        idempotency_key=clave, **extra,
    )


class TestElSaldoSeCalcula:
    def test_1_recien_entregado_el_saldo_es_lo_entregado(
        self, org_a, user_profile, conector, kit
    ):
        assert saldo_de(user_profile, conector) == Decimal("24")

    def test_2_un_consumo_descuenta(self, org_a, user_profile, conector, kit):
        consumir(org_a, user_profile, conector, 4, "mov-1")

        assert saldo_de(user_profile, conector) == Decimal("20")

    def test_3_una_devolucion_tambien_descuenta_de_lo_que_lleva_encima(
        self, org_a, user_profile, conector, kit
    ):
        """Devolver a bodega saca el material de la camioneta, igual que usarlo."""
        registrar_movimiento(
            org=org_a, profile=user_profile, material=conector,
            tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=10,
            idempotency_key="dev-1",
        )

        assert saldo_de(user_profile, conector) == Decimal("14")

    def test_4_la_bobina_se_consume_con_decimales(
        self, org_a, user_profile, fibra, kit
    ):
        consumir(org_a, user_profile, fibra, "42.5", "mov-fibra")

        assert saldo_de(user_profile, fibra) == Decimal("257.5")

    def test_5_un_consumible_no_admite_fracciones(
        self, org_a, user_profile, conector, kit
    ):
        """Un conector y medio no existe. Se trunca hacia abajo: inventar media
        unidad de más es peor que perderla."""
        movimiento, _ = consumir(org_a, user_profile, conector, "2.7", "mov-frac")

        assert movimiento.cantidad == Decimal("2")
        assert saldo_de(user_profile, conector) == Decimal("22")


class TestUnConsumoNuncaSeRechaza:
    def test_6_sin_saldo_el_consumo_ENTRA_y_queda_marcado(
        self, org_a, user_profile, conector, kit
    ):
        """La prueba que define el diseño.

        El técnico usó 30 conectores y el acta decía 24. Rechazarlo no
        devuelve los 6 a la camioneta: solo borra el registro de que se
        usaron.
        """
        movimiento, era_nuevo = consumir(org_a, user_profile, conector, 30, "mov-más")

        assert era_nuevo is True
        assert movimiento.pk is not None, "el movimiento se guarda igual"
        assert movimiento.estado == MovimientoDeMaterial.DESCUADRE
        assert movimiento.cantidad == Decimal("30")

    def test_7_el_descuadre_se_explica_en_palabras(
        self, org_a, user_profile, conector, kit
    ):
        """Alguien en la oficina lo va a leer para decidir qué hacer."""
        movimiento, _ = consumir(org_a, user_profile, conector, 30, "mov-más")

        assert "30" in movimiento.motivo
        assert "24" in movimiento.motivo
        assert movimiento.motivo.strip()

    def test_8_y_el_saldo_queda_en_negativo_a_proposito(
        self, org_a, user_profile, conector, kit
    ):
        """Taparlo con un max(0, ...) haría desaparecer el descuadre de la
        pantalla sin haberlo resuelto."""
        consumir(org_a, user_profile, conector, 30, "mov-más")

        assert saldo_de(user_profile, conector) == Decimal("-6")

    def test_9_un_material_sin_kit_tambien_entra_como_descuadre(
        self, org_a, user_profile, conector
    ):
        """Pasa de verdad: material que se entregó sin acta."""
        movimiento, _ = consumir(org_a, user_profile, conector, 3, "mov-sin-kit")

        assert movimiento.estado == MovimientoDeMaterial.DESCUADRE
        assert movimiento.cantidad == Decimal("3")


class TestElSerializadoSeInstalaUnaSolaVez:
    def test_10_la_primera_instalacion_entra_normal(
        self, org_a, user_profile, ont, kit
    ):
        movimiento, _ = consumir(
            org_a, user_profile, ont, 1, "mov-ont", serie="48575448A9B0C1"
        )

        assert movimiento.estado == MovimientoDeMaterial.ACEPTADO

    def test_11_la_segunda_entra_como_conflicto_y_no_se_pierde(
        self, org_a, user_profile, ont, kit
    ):
        """Dos técnicos no instalaron la misma ONT: alguien se equivocó de
        serie, y hay que poder ver las dos versiones para saber cuál es."""
        consumir(org_a, user_profile, ont, 1, "mov-ont", serie="48575448A9B0C1")

        segundo, era_nuevo = consumir(
            org_a, user_profile, ont, 1, "mov-ont-2", serie="48575448A9B0C1"
        )

        assert era_nuevo is True
        assert segundo.pk is not None
        assert segundo.estado == MovimientoDeMaterial.CONFLICTO
        assert "48575448A9B0C1" in segundo.motivo

    def test_12_un_conflicto_no_descuenta_del_saldo(
        self, org_a, user_profile, ont, kit
    ):
        """No ocurrió: descontarlo castigaría a quien no hizo nada malo."""
        consumir(org_a, user_profile, ont, 1, "mov-ont", serie="48575448A9B0C1")
        consumir(org_a, user_profile, ont, 1, "mov-ont-2", serie="48575448A9B0C1")

        assert saldo_de(user_profile, ont) == Decimal("0")


class TestLaColaOfflinePuedeReintentar:
    def test_13_la_misma_clave_no_descuenta_dos_veces(
        self, org_a, user_profile, conector, kit
    ):
        """Un reintento de la cola no es un consumo nuevo."""
        primero, era_nuevo_1 = consumir(org_a, user_profile, conector, 4, "mov-1")
        segundo, era_nuevo_2 = consumir(org_a, user_profile, conector, 4, "mov-1")

        assert era_nuevo_1 is True
        assert era_nuevo_2 is False
        assert primero.pk == segundo.pk
        assert saldo_de(user_profile, conector) == Decimal("20")
        assert MovimientoDeMaterial.objects.count() == 1

    def test_14_dos_consumos_distintos_del_mismo_material_si_suman(
        self, org_a, user_profile, conector, kit
    ):
        """Dos trabajos seguidos gastan conectores dos veces. Solo la clave
        distingue un reintento de un consumo nuevo, y la pone el teléfono."""
        consumir(org_a, user_profile, conector, 4, "mov-1")
        consumir(org_a, user_profile, conector, 4, "mov-2")

        assert saldo_de(user_profile, conector) == Decimal("16")

    def test_15_un_movimiento_que_llega_tarde_se_guarda_con_su_hora_de_campo(
        self, org_a, user_profile, conector, kit
    ):
        """Media jornada sin señal: lo que importa es cuándo pasó, no cuándo
        llegó."""
        from django.utils import timezone
        from datetime import timedelta

        hace_ocho_horas = timezone.now() - timedelta(hours=8)
        movimiento, _ = consumir(
            org_a, user_profile, conector, 4, "mov-viejo",
            ocurrido_en=hace_ocho_horas,
        )

        assert movimiento.ocurrido_en == hace_ocho_horas
        assert movimiento.created_at > movimiento.ocurrido_en


class TestLoQueVeLaPantalla:
    def test_16_el_kit_trae_una_fila_por_material_con_su_saldo(
        self, org_a, user_profile, conector, fibra, ont, kit
    ):
        consumir(org_a, user_profile, conector, 8, "mov-1")

        filas = kit_de(user_profile, org_a)
        por_codigo = {f["material"].codigo: f for f in filas}

        assert len(filas) == 3
        assert por_codigo["CON-SC-APC"]["recibido"] == Decimal("24")
        assert por_codigo["CON-SC-APC"]["consumido"] == Decimal("8")
        assert por_codigo["CON-SC-APC"]["disponible"] == Decimal("16")
        assert por_codigo["ONT-HG8145"]["series"] == ["48575448A9B0C1"]

    def test_17_el_kit_trae_el_acta_de_donde_salio(
        self, org_a, user_profile, conector, kit
    ):
        filas = kit_de(user_profile, org_a)

        assert filas[0]["acta"] == "K-2024-094"

    def test_18_lo_que_no_cuadra_se_puede_listar(
        self, org_a, user_profile, conector, ont, kit
    ):
        """Aceptar sin dejar rastro sería peor que rechazar."""
        consumir(org_a, user_profile, conector, 4, "mov-ok")
        consumir(org_a, user_profile, conector, 90, "mov-descuadre")
        consumir(org_a, user_profile, ont, 1, "mov-ont", serie="48575448A9B0C1")
        consumir(org_a, user_profile, ont, 1, "mov-ont-2", serie="48575448A9B0C1")

        pendientes = list(materiales_sin_cuadrar(user_profile, org_a))
        estados = {m.estado for m in pendientes}

        assert len(pendientes) == 2
        assert estados == {
            MovimientoDeMaterial.DESCUADRE,
            MovimientoDeMaterial.CONFLICTO,
        }

    def test_19_el_kit_de_uno_no_es_el_del_otro(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        """El aislamiento vale también acá: la custodia es de una persona."""
        assert kit_de(user_profile, org_a) != []
        assert kit_de(admin_profile, org_a) == []
        assert saldo_de(admin_profile, conector) == Decimal("0")


class TestElConsumoSeAtaAlTrabajo:
    def test_20_un_consumo_puede_decir_en_que_orden_se_uso(
        self, org_a, user_profile, conector, kit
    ):
        wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")
        version = WorkTypeVersion.objects.create(
            work_type=wt, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"pasos": [], "campos": [], "evidencias": []},
        )
        orden = OrdenTrabajo.objects.create(
            org=org_a, numero=4832, tipo_trabajo_version=version,
            estado_operativo=OrdenTrabajo.ASIGNADA,
        )

        movimiento, _ = consumir(
            org_a, user_profile, conector, 4, "mov-ot", orden=orden
        )

        assert movimiento.orden_id == orden.id
        assert orden.movimientos_material.count() == 1

    def test_21_una_devolucion_de_jornada_no_necesita_orden(
        self, org_a, user_profile, conector, kit
    ):
        movimiento, _ = registrar_movimiento(
            org=org_a, profile=user_profile, material=conector,
            tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=12,
            idempotency_key="dev-jornada",
        )

        assert movimiento.orden_id is None
        assert movimiento.estado == MovimientoDeMaterial.ACEPTADO
