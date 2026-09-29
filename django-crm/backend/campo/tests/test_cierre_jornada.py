# -*- coding: utf-8 -*-
"""
Devolución, diferencias y cierre de jornada.

QUÉ CUIDAN ESTAS PRUEBAS
------------------------
Que la cuenta del día cierre, y que cuando no cierra se sepa por qué.

Tres ideas que vienen de las fases anteriores y acá se ponen a prueba juntas:

1. **Una devolución no corrige: es un hecho nuevo.** Devolver diez conectores
   no anula el consumo de ayer. Son dos cosas que pasaron, en ese orden.
2. **La diferencia no se absorbe: se nombra.** No hay ajuste silencioso que
   cuadre la cuenta; hay una incidencia con su motivo.
3. **Registrar nunca se bloquea; afirmar sí.** Se puede anotar cualquier cosa
   que haya pasado en la calle. Lo que no se puede es declarar cerrada una
   jornada que todavía se contradice a sí misma.
"""

from decimal import Decimal

import pytest

from campo.models import (
    ActaDeDevolucion,
    AsignacionTrabajo,
    EntregaDeKit,
    IncidenciaDeMaterial,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    TransferenciaDeMaterial,
    WorkType,
    WorkTypeVersion,
)
from campo.services.cierre_jornada import (
    CierreBloqueado,
    confirmar_acta,
    conciliacion_de,
    esperado_devolver,
    motivos_para_no_cerrar,
    registrar_incidencia,
    registrar_transferencia,
    resolver_transferencia,
    resumen_de_jornada,
    series_sin_devolver,
)
from campo.services.materiales import registrar_movimiento

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
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=4832, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def kit(org_a, user_profile, conector):
    entrega = EntregaDeKit.objects.create(
        org=org_a, profile=user_profile, acta="K-2024-094"
    )
    ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=10)
    return entrega


@pytest.fixture
def kit_con_equipo(org_a, user_profile, ont):
    entrega = EntregaDeKit.objects.create(
        org=org_a, profile=user_profile, acta="K-EQUIPO"
    )
    ItemDeKit.objects.create(
        entrega=entrega, material=ont, cantidad=1, serie="48575448A9B0C1"
    )
    return entrega


def consumir(org, profile, material, cantidad, clave, orden, serie=""):
    return registrar_movimiento(
        org=org, profile=profile, material=material,
        tipo=MovimientoDeMaterial.CONSUMO, cantidad=cantidad,
        idempotency_key=clave, orden=orden, serie=serie,
    )


def devolver(org, profile, material, cantidad, clave):
    return registrar_movimiento(
        org=org, profile=profile, material=material,
        tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=cantidad,
        idempotency_key=clave,
    )


class TestLaCuentaDelDia:
    def test_1_esperado_es_lo_entregado_menos_lo_usado(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Recibidos 10, consumidos 3, esperado devolver 7."""
        consumir(org_a, user_profile, conector, 3, "c1", orden)

        assert esperado_devolver(user_profile, conector) == Decimal("7")

    def test_2_la_devolucion_no_corrige_el_consumo_lo_acompana(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Devolver no anula nada: los dos hechos quedan, en su orden."""
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")

        assert MovimientoDeMaterial.objects.count() == 2
        consumo = MovimientoDeMaterial.objects.get(tipo="consumo")
        assert consumo.cantidad == Decimal("3"), "el consumo no se tocó"

    def test_3_devolviendo_lo_esperado_la_cuenta_queda_en_cero(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")

        fila = conciliacion_de(user_profile, org_a)[0]
        assert fila["esperado_devolver"] == Decimal("7")
        assert fila["devuelto"] == Decimal("7")
        assert fila["diferencia"] == Decimal("0")

    def test_4_devolver_de_menos_deja_diferencia(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")

        fila = conciliacion_de(user_profile, org_a)[0]
        assert fila["diferencia"] == Decimal("2")

    def test_5_el_resumen_es_determinista(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Dos llamadas seguidas dan lo mismo: esto es lo que alguien firma."""
        consumir(org_a, user_profile, conector, 3, "c1", orden)

        primero = resumen_de_jornada(user_profile, org_a)
        segundo = resumen_de_jornada(user_profile, org_a)

        assert primero == segundo
        assert primero["material"]["recibido"] == "10"
        assert primero["material"]["consumido"] == "3"
        assert primero["material"]["a_devolver"] == "7"

    def test_6_el_resumen_cuenta_las_ordenes_del_dia(
        self, org_a, user_profile, conector, kit, orden
    ):
        resumen = resumen_de_jornada(user_profile, org_a)

        assert resumen["ordenes"]["asignadas"] == 1
        assert resumen["ordenes"]["completadas"] == 0
        assert resumen["ordenes"]["pendientes"] == 1

    def test_7_una_orden_completada_cuenta_como_tal(
        self, org_a, user_profile, conector, kit, orden
    ):
        orden.estado_operativo = OrdenTrabajo.COMPLETADA_CAMPO
        orden.save()

        resumen = resumen_de_jornada(user_profile, org_a)

        assert resumen["ordenes"]["completadas"] == 1
        assert resumen["ordenes"]["pendientes"] == 0


class TestLaDiferenciaSeNombra:
    def test_8_una_incidencia_explica_el_faltante_y_lo_cuadra(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")

        registrar_incidencia(
            org=org_a, profile=user_profile, material=conector,
            tipo=IncidenciaDeMaterial.DANADO, cantidad=2,
            motivo="Se dañaron al retirarlos de la caja terminal.",
            idempotency_key="inc-1",
        )

        fila = conciliacion_de(user_profile, org_a)[0]
        assert fila["diferencia"] == Decimal("0")
        assert fila["incidencias"] == Decimal("2")

    def test_9_una_incidencia_sin_motivo_se_rechaza(
        self, org_a, user_profile, conector, kit
    ):
        """Lo único que se rechaza acá, y no por rigor administrativo: sin esa
        frase el faltante aparece en el conteo del mes que viene y ya no hay a
        quién preguntarle."""
        with pytest.raises(CierreBloqueado):
            registrar_incidencia(
                org=org_a, profile=user_profile, material=conector,
                tipo=IncidenciaDeMaterial.PERDIDO, cantidad=1, motivo="   ",
                idempotency_key="inc-vacia",
            )

        assert IncidenciaDeMaterial.objects.count() == 0

    def test_10_la_incidencia_es_idempotente(
        self, org_a, user_profile, conector, kit
    ):
        primera, nueva1 = registrar_incidencia(
            org=org_a, profile=user_profile, material=conector,
            tipo=IncidenciaDeMaterial.PERDIDO, cantidad=1,
            motivo="Se cayó del portaequipajes.", idempotency_key="inc-1",
        )
        segunda, nueva2 = registrar_incidencia(
            org=org_a, profile=user_profile, material=conector,
            tipo=IncidenciaDeMaterial.PERDIDO, cantidad=1,
            motivo="Se cayó del portaequipajes.", idempotency_key="inc-1",
        )

        assert nueva1 is True and nueva2 is False
        assert primera.pk == segunda.pk
        assert IncidenciaDeMaterial.objects.count() == 1

    def test_11_los_cinco_tipos_estan_disponibles(self):
        tipos = {t[0] for t in IncidenciaDeMaterial.TIPOS}

        assert tipos == {
            "perdido", "danado", "usado_sin_registrar",
            "entregado_a_otro", "otro",
        }


class TestLosEquiposNoSePierdenDeVista:
    def test_12_un_equipo_entregado_y_no_resuelto_se_lista(
        self, org_a, user_profile, ont, kit_con_equipo
    ):
        """Un equipo con número no puede quedar 'en algún lado'."""
        assert series_sin_devolver(user_profile, org_a) == ["48575448A9B0C1"]

    def test_13_instalado_deja_de_estar_pendiente(
        self, org_a, user_profile, ont, kit_con_equipo, orden
    ):
        consumir(org_a, user_profile, ont, 1, "c1", orden, serie="48575448A9B0C1")

        assert series_sin_devolver(user_profile, org_a) == []

    def test_14_devuelto_tambien(
        self, org_a, user_profile, ont, kit_con_equipo
    ):
        registrar_movimiento(
            org=org_a, profile=user_profile, material=ont,
            tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=1,
            idempotency_key="d1", serie="48575448A9B0C1",
        )

        assert series_sin_devolver(user_profile, org_a) == []

    def test_15_o_justificado_con_una_incidencia(
        self, org_a, user_profile, ont, kit_con_equipo
    ):
        registrar_incidencia(
            org=org_a, profile=user_profile, material=ont,
            tipo=IncidenciaDeMaterial.DANADO, cantidad=1,
            serie="48575448A9B0C1",
            motivo="Llegó con la carcasa partida; queda en revisión.",
            idempotency_key="inc-1",
        )

        assert series_sin_devolver(user_profile, org_a) == []


class TestLasTransferenciasNoEvaporanInventario:
    def test_16_pendiente_no_mueve_nada(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        """Entre que uno entrega y el otro acepta, el material sigue siendo de
        quien lo entregó."""
        registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )

        assert esperado_devolver(user_profile, conector) == Decimal("10")
        assert esperado_devolver(admin_profile, conector) == Decimal("0")

    def test_17_aceptada_mueve_el_saldo_de_los_dos(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        transferencia, _ = registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )

        resolver_transferencia(transferencia=transferencia, acepta=True)

        assert esperado_devolver(user_profile, conector) == Decimal("6")
        assert esperado_devolver(admin_profile, conector) == Decimal("4")

    def test_18_rechazada_lo_deja_donde_estaba(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        transferencia, _ = registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )

        resolver_transferencia(transferencia=transferencia, acepta=False)

        assert esperado_devolver(user_profile, conector) == Decimal("10")
        assert esperado_devolver(admin_profile, conector) == Decimal("0")

    def test_19_aceptar_dos_veces_no_duplica(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        transferencia, _ = registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )

        resolver_transferencia(transferencia=transferencia, acepta=True)
        _, cambio = resolver_transferencia(transferencia=transferencia, acepta=True)

        assert cambio is False
        assert esperado_devolver(user_profile, conector) == Decimal("6")

    def test_20_proponerla_dos_veces_tampoco(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )
        registrar_transferencia(
            org=org_a, entrega=user_profile, recibe=admin_profile,
            material=conector, cantidad=4, idempotency_key="t1",
        )

        assert TransferenciaDeMaterial.objects.count() == 1


class TestAfirmarQueLaJornadaCerro:
    def test_21_con_todo_cuadrado_se_puede_cerrar(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")

        assert motivos_para_no_cerrar(user_profile, org_a) == []

        acta, nueva = confirmar_acta(org=org_a, profile=user_profile)

        assert nueva is True
        assert acta.estado == ActaDeDevolucion.CONFIRMADA

    def test_22_una_diferencia_sin_explicar_lo_impide(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")

        motivos = motivos_para_no_cerrar(user_profile, org_a)

        assert len(motivos) == 1
        assert "faltan" in motivos[0].lower()
        with pytest.raises(CierreBloqueado):
            confirmar_acta(org=org_a, profile=user_profile)

    def test_23_explicada_deja_cerrar(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")
        registrar_incidencia(
            org=org_a, profile=user_profile, material=conector,
            tipo=IncidenciaDeMaterial.PERDIDO, cantidad=2,
            motivo="Se cayeron de la escalera y no se encontraron.",
            idempotency_key="inc-1",
        )

        assert motivos_para_no_cerrar(user_profile, org_a) == []

    def test_24_un_equipo_sin_localizar_lo_impide(
        self, org_a, user_profile, ont, kit_con_equipo
    ):
        motivos = motivos_para_no_cerrar(user_profile, org_a)

        assert any("48575448A9B0C1" in m for m in motivos)
        assert any("dónde está" in m for m in motivos)

    def test_25_un_conflicto_sin_resolver_tambien(
        self, org_a, user_profile, ont, kit_con_equipo, orden
    ):
        consumir(org_a, user_profile, ont, 1, "c1", orden, serie="48575448A9B0C1")
        consumir(org_a, user_profile, ont, 1, "c2", orden, serie="48575448A9B0C1")

        motivos = motivos_para_no_cerrar(user_profile, org_a)

        assert any("conflicto" in m for m in motivos)

    def test_26_los_motivos_se_leen_no_se_decodifican(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Lo que los hace útiles es que alguien sepa qué le falta hacer."""
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")

        motivo = motivos_para_no_cerrar(user_profile, org_a)[0]

        assert "Conector SC/APC" in motivo
        assert "2" in motivo
        assert "unidades" in motivo


class TestElActaSeCongela:
    def test_27_al_confirmar_guarda_los_numeros(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")

        acta, _ = confirmar_acta(org=org_a, profile=user_profile)

        assert acta.resumen["material"]["recibido"] == "10"
        assert acta.resumen["material"]["consumido"] == "3"
        assert acta.confirmada_en is not None

    def test_28_y_no_cambia_si_despues_pasa_algo_mas(
        self, org_a, user_profile, conector, kit, orden
    ):
        """Un acta es lo que dos personas acordaron ese día."""
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")
        acta, _ = confirmar_acta(org=org_a, profile=user_profile)
        congelado = dict(acta.resumen)

        registrar_movimiento(
            org=org_a, profile=user_profile, material=conector,
            tipo=MovimientoDeMaterial.AJUSTE, cantidad=5,
            idempotency_key="aj-tardio",
        )
        acta.refresh_from_db()

        assert acta.resumen == congelado

    def test_29_confirmar_dos_veces_devuelve_la_misma_acta(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 7, "d1")

        primera, nueva1 = confirmar_acta(org=org_a, profile=user_profile)
        segunda, nueva2 = confirmar_acta(org=org_a, profile=user_profile)

        assert nueva1 is True and nueva2 is False
        assert primera.pk == segunda.pk
        assert ActaDeDevolucion.objects.count() == 1

    def test_30_el_acta_recoge_las_incidencias_del_dia(
        self, org_a, user_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")
        registrar_incidencia(
            org=org_a, profile=user_profile, material=conector,
            tipo=IncidenciaDeMaterial.PERDIDO, cantidad=2,
            motivo="Se cayeron de la escalera.", idempotency_key="inc-1",
        )

        acta, _ = confirmar_acta(org=org_a, profile=user_profile)

        assert acta.incidencias.count() == 1


class TestCadaUnoCierraLoSuyo:
    def test_31_el_kit_de_otro_tecnico_no_entra_en_mi_cuenta(
        self, org_a, user_profile, admin_profile, conector, kit
    ):
        assert esperado_devolver(user_profile, conector) == Decimal("10")
        assert esperado_devolver(admin_profile, conector) == Decimal("0")
        assert conciliacion_de(admin_profile, org_a) == []

    def test_32_ni_el_de_otra_empresa(
        self, org_a, org_b, user_profile, conector, kit
    ):
        material_ajeno = MaterialCatalogo.objects.create(
            org=org_b, codigo="CON-SC-APC", nombre="Conector de otra empresa",
            clase=MaterialCatalogo.CONSUMIBLE,
        )
        entrega_ajena = EntregaDeKit.objects.create(
            org=org_b, profile=user_profile, acta="K-AJENO"
        )
        ItemDeKit.objects.create(
            entrega=entrega_ajena, material=material_ajeno, cantidad=99
        )

        codigos = {f["material"].id for f in conciliacion_de(user_profile, org_a)}

        assert material_ajeno.id not in codigos

    def test_33_mi_incidencia_no_cuadra_la_cuenta_de_otro(
        self, org_a, user_profile, admin_profile, conector, kit, orden
    ):
        consumir(org_a, user_profile, conector, 3, "c1", orden)
        devolver(org_a, user_profile, conector, 5, "d1")
        registrar_incidencia(
            org=org_a, profile=admin_profile, material=conector,
            tipo=IncidenciaDeMaterial.PERDIDO, cantidad=2,
            motivo="Incidencia de otra persona.", idempotency_key="inc-otro",
        )

        fila = conciliacion_de(user_profile, org_a)[0]

        assert fila["diferencia"] == Decimal("2"), "sigue sin explicarse"
