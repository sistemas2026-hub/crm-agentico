# -*- coding: utf-8 -*-
"""
El consumo de material dentro de una orden de trabajo.

QUÉ CAMBIA RESPECTO DE LA FASE ANTERIOR
---------------------------------------
Antes un movimiento podía existir suelto. Ahora un **consumo** pertenece
siempre a un trabajo: es la única forma de saber después en qué se fue el
material. Sin eso el inventario cuadra pero no explica nada, y explicar es
justamente para lo que sirve.

Devolver a bodega y ajustar por conteo siguen sin necesitar orden, porque no
son consumo: son actos de jornada.

LO QUE SE RECHAZA SIGUE SIENDO POCO
-----------------------------------
La regla de la fase anterior no se toca: lo que ya pasó en la calle se guarda
aunque no cuadre. Lo que se rechaza es lo que no se puede interpretar como un
hecho — un consumo que no dice en qué trabajo, un equipo serializado sin su
número — porque guardarlo sería guardar una fila que nadie puede explicar
después.

Y las reglas de cantidad **no bloquean**, salvo que la empresa lo haya pedido
explícitamente. "Una instalación usa dos conectores" es verdad en una empresa
y falso en la siguiente.
"""

from decimal import Decimal

import pytest

from campo.models import (
    EntregaDeKit,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    ReglaDeConsumo,
    WorkType,
    WorkTypeVersion,
)
from campo.services.materiales import (
    ConsumoInvalido,
    evaluar_cantidad,
    registrar_movimiento,
    saldo_de,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades",
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei HG8145V5",
        clase=MaterialCatalogo.SERIALIZADO, unidad="unidades",
    )


@pytest.fixture
def tipo_instalacion(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def tipo_reparacion(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="reparacion", nombre="Reparacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def orden(org_a, tipo_instalacion):
    return OrdenTrabajo.objects.create(
        org=org_a, numero=4832, tipo_trabajo_version=tipo_instalacion,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )


@pytest.fixture
def orden_reparacion(org_a, tipo_reparacion):
    return OrdenTrabajo.objects.create(
        org=org_a, numero=4833, tipo_trabajo_version=tipo_reparacion,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )


@pytest.fixture
def kit(org_a, user_profile, conector, ont):
    entrega = EntregaDeKit.objects.create(
        org=org_a, profile=user_profile, acta="K-2024-094"
    )
    ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=24)
    ItemDeKit.objects.create(
        entrega=entrega, material=ont, cantidad=1, serie="48575448A9B0C1"
    )
    return entrega


def consumir(org, profile, material, cantidad, clave, orden, **extra):
    return registrar_movimiento(
        org=org, profile=profile, material=material,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=cantidad,
        idempotency_key=clave, orden=orden, **extra,
    )


class TestTodoConsumoTieneSuTrabajo:
    def test_1_el_consumo_normal_queda_atado_a_la_orden(
        self, org_a, user_profile, conector, kit, orden
    ):
        movimiento, _ = consumir(org_a, user_profile, conector, 1, "m1", orden)

        assert movimiento.orden_id == orden.id
        assert movimiento.estado == MovimientoDeMaterial.ACEPTADO
        assert saldo_de(user_profile, conector) == Decimal("23")

    def test_2_un_consumo_sin_orden_se_rechaza(
        self, org_a, user_profile, conector, kit
    ):
        """Sin trabajo no se puede explicar después en qué se fue el material."""
        with pytest.raises(ConsumoInvalido) as error:
            consumir(org_a, user_profile, conector, 1, "m1", None)

        assert "trabajo" in str(error.value).lower()
        assert MovimientoDeMaterial.objects.count() == 0

    def test_3_una_devolucion_si_puede_no_tener_orden(
        self, org_a, user_profile, conector, kit
    ):
        """Devolver a bodega es un acto de jornada, no de trabajo."""
        movimiento, _ = registrar_movimiento(
            org=org_a, profile=user_profile, material=conector,
            tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=5,
            idempotency_key="dev-1",
        )

        assert movimiento.pk is not None
        assert movimiento.orden_id is None

    def test_4_un_ajuste_por_conteo_tampoco(
        self, org_a, user_profile, conector, kit
    ):
        movimiento, _ = registrar_movimiento(
            org=org_a, profile=user_profile, material=conector,
            tipo=MovimientoDeMaterial.AJUSTE, cantidad=2,
            idempotency_key="aj-1",
        )

        assert movimiento.pk is not None


class TestLosEquiposLlevanSuNumero:
    def test_5_un_serializado_exige_la_serie(
        self, org_a, user_profile, ont, kit, orden
    ):
        """Sin el número no se sabe cuál se instaló, ni se lo encuentra después
        si el cliente reclama."""
        with pytest.raises(ConsumoInvalido) as error:
            consumir(org_a, user_profile, ont, 1, "m1", orden)

        assert "serie" in str(error.value).lower()
        assert MovimientoDeMaterial.objects.count() == 0

    def test_6_una_serie_en_blanco_no_alcanza(
        self, org_a, user_profile, ont, kit, orden
    ):
        with pytest.raises(ConsumoInvalido):
            consumir(org_a, user_profile, ont, 1, "m1", orden, serie="   ")

    def test_7_con_la_serie_entra_normal(
        self, org_a, user_profile, ont, kit, orden
    ):
        movimiento, _ = consumir(
            org_a, user_profile, ont, 1, "m1", orden, serie="48575448A9B0C1"
        )

        assert movimiento.estado == MovimientoDeMaterial.ACEPTADO
        assert movimiento.serie == "48575448A9B0C1"
        assert movimiento.orden_id == orden.id

    def test_8_la_misma_serie_en_dos_ordenes_es_conflicto(
        self, org_a, user_profile, ont, kit, orden, orden_reparacion
    ):
        """El caso que el pedido nombra: un serial usado en dos OT."""
        consumir(org_a, user_profile, ont, 1, "m1", orden, serie="48575448A9B0C1")

        segundo, _ = consumir(
            org_a, user_profile, ont, 1, "m2", orden_reparacion,
            serie="48575448A9B0C1",
        )

        assert segundo.estado == MovimientoDeMaterial.CONFLICTO
        assert segundo.orden_id == orden_reparacion.id

    def test_9_y_no_descuenta_dos_veces(
        self, org_a, user_profile, ont, kit, orden, orden_reparacion
    ):
        consumir(org_a, user_profile, ont, 1, "m1", orden, serie="48575448A9B0C1")
        consumir(
            org_a, user_profile, ont, 1, "m2", orden_reparacion,
            serie="48575448A9B0C1",
        )

        assert saldo_de(user_profile, ont) == Decimal("0")

    def test_10_un_consumible_no_necesita_serie(
        self, org_a, user_profile, conector, kit, orden
    ):
        movimiento, _ = consumir(org_a, user_profile, conector, 3, "m1", orden)

        assert movimiento.serie == ""


class TestLasReglasDeCantidadSonDeLaEmpresa:
    def test_11_sin_regla_configurada_no_hay_aviso(
        self, org_a, conector, orden
    ):
        avisos, exige, bloquea = evaluar_cantidad(
            org=org_a, material=conector, orden=orden, cantidad=Decimal("99"),
        )

        assert avisos == []
        assert exige is False
        assert bloquea is False

    def test_12_pasarse_de_lo_habitual_avisa_pero_no_bloquea(
        self, org_a, user_profile, conector, kit, orden
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
        )

        movimiento, _ = consumir(org_a, user_profile, conector, 3, "m1", orden)

        assert movimiento.pk is not None, "el material ya se gastó"
        assert movimiento.estado == MovimientoDeMaterial.ACEPTADO
        avisos = movimiento.datos.get("avisos", [])
        assert any("habitual" in a for a in avisos)

    def test_13_el_aviso_dice_los_dos_numeros(
        self, org_a, user_profile, conector, kit, orden
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
        )

        movimiento, _ = consumir(org_a, user_profile, conector, 3, "m1", orden)

        texto = " ".join(movimiento.datos.get("avisos", []))
        assert "1" in texto and "3" in texto

    def test_14_si_la_empresa_lo_pide_hay_que_escribir_por_que(
        self, org_a, user_profile, conector, kit, orden
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
            exige_motivo_sobre_habitual=True,
        )

        with pytest.raises(ConsumoInvalido) as error:
            consumir(org_a, user_profile, conector, 3, "m1", orden)

        assert "por qué" in str(error.value).lower()

    def test_15_con_el_motivo_escrito_entra(
        self, org_a, user_profile, conector, kit, orden
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
            exige_motivo_sobre_habitual=True,
        )

        movimiento, _ = consumir(
            org_a, user_profile, conector, 3, "m1", orden,
            motivo_tecnico="El poste estaba a 40 metros, hubo que rehacer dos empalmes.",
        )

        assert movimiento.pk is not None
        assert "poste" in movimiento.motivo_tecnico

    def test_16_el_motivo_del_tecnico_no_se_mezcla_con_el_del_servidor(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Cuando hay que reconstruir qué pasó, importa quién dijo cada cosa."""
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
        )

        movimiento, _ = consumir(
            org_a, user_profile, conector, 90, "m1", orden,
            motivo_tecnico="Se reventó la bobina.",
        )

        assert movimiento.motivo_tecnico == "Se reventó la bobina."
        assert "24" in movimiento.motivo, "el servidor explica el descuadre"
        assert "bobina" not in movimiento.motivo

    def test_17_el_maximo_solo_bloquea_si_la_empresa_lo_encendio(
        self, org_a, user_profile, conector, kit, orden
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1, maximo=5,
        )

        movimiento, _ = consumir(org_a, user_profile, conector, 10, "m1", orden)

        assert movimiento.pk is not None, "sin bloqueo configurado, entra"
        assert any("maximo" in a.lower() for a in movimiento.datos.get("avisos", []))

    def test_18_con_el_bloqueo_encendido_si_se_rechaza(
        self, org_a, user_profile, conector, kit, orden
    ):
        """La única política que rechaza, y viene apagada."""
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, maximo=5, bloquea_sobre_maximo=True,
        )

        with pytest.raises(ConsumoInvalido):
            consumir(org_a, user_profile, conector, 10, "m1", orden)

        assert MovimientoDeMaterial.objects.count() == 0

    def test_19_la_regla_del_tipo_de_trabajo_le_gana_a_la_general(
        self, org_a, user_profile, conector, kit, orden_reparacion, tipo_reparacion
    ):
        """Cambiar una ONT gasta distinto que instalar desde cero."""
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
        )
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, work_type=tipo_reparacion.work_type,
            cantidad_habitual=6,
        )

        movimiento, _ = consumir(
            org_a, user_profile, conector, 4, "m1", orden_reparacion
        )

        assert movimiento.datos.get("avisos", []) == [], (
            "4 está por debajo de los 6 habituales de una reparación"
        )

    def test_20_y_la_general_aplica_donde_no_hay_especifica(
        self, org_a, user_profile, conector, kit, orden, tipo_reparacion
    ):
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, cantidad_habitual=1,
        )
        ReglaDeConsumo.objects.create(
            org=org_a, material=conector, work_type=tipo_reparacion.work_type,
            cantidad_habitual=6,
        )

        movimiento, _ = consumir(org_a, user_profile, conector, 4, "m1", orden)

        assert any("habitual" in a for a in movimiento.datos.get("avisos", []))

    def test_21_la_regla_de_otra_empresa_no_aplica(
        self, org_a, org_b, user_profile, conector, kit, orden
    ):
        material_ajeno = MaterialCatalogo.objects.create(
            org=org_b, codigo="CON-SC-APC", nombre="Conector de otra empresa",
            clase=MaterialCatalogo.CONSUMIBLE,
        )
        ReglaDeConsumo.objects.create(
            org=org_b, material=material_ajeno, cantidad_habitual=1,
            bloquea_sobre_maximo=True, maximo=1,
        )

        movimiento, _ = consumir(org_a, user_profile, conector, 10, "m1", orden)

        assert movimiento.pk is not None


class TestElAislamientoSigueVigente:
    def test_22_el_tecnico_no_consume_del_kit_de_otro(
        self, org_a, user_profile, admin_profile, conector, kit, orden
    ):
        """El de al lado tiene 24; el que no recibió nada arranca en cero y su
        consumo entra como descuadre, no contra el kit ajeno."""
        movimiento, _ = consumir(org_a, admin_profile, conector, 2, "m1", orden)

        assert movimiento.estado == MovimientoDeMaterial.DESCUADRE
        assert saldo_de(user_profile, conector) == Decimal("24")
        assert saldo_de(admin_profile, conector) == Decimal("-2")

    def test_23_una_orden_de_otra_empresa_no_es_una_orden_valida(
        self, org_a, org_b, user_profile, conector, kit
    ):
        """El servicio recibe la orden ya resuelta; la vista la busca dentro de
        la organización, así que una ajena llega como None y se rechaza."""
        with pytest.raises(ConsumoInvalido):
            consumir(org_a, user_profile, conector, 1, "m1", None)
