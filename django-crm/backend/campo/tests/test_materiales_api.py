# -*- coding: utf-8 -*-
"""
La API de materiales, vista desde el teléfono.

QUÉ CUIDAN ESTAS PRUEBAS
------------------------
Que el camino que de verdad va a ocurrir —media jornada sin señal, un lote de
movimientos al reconectar, y un reintento porque la primera respuesta se
perdió— termine con el inventario diciendo la verdad una sola vez.

El caso que más importa es el reintento. No es un caso raro: es lo normal.
Un teléfono manda el lote, el servidor lo guarda, la respuesta se pierde en el
camino y la app vuelve a mandar exactamente lo mismo. Si eso descuenta dos
veces, el kit de todos los técnicos queda mal para siempre y nadie sabe por
qué.
"""

import pytest
from rest_framework import status

from campo.models import (
    EntregaDeKit,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)

pytestmark = pytest.mark.django_db

KIT = "/api/campo/kit/"
MOVIMIENTOS = "/api/campo/materiales/movimientos/"


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
        categoria="Equipos", clase=MaterialCatalogo.SERIALIZADO,
        unidad="unidades",
    )


@pytest.fixture
def kit(org_a, user_profile, conector, fibra, ont):
    entrega = EntregaDeKit.objects.create(
        org=org_a, profile=user_profile, acta="K-2024-094"
    )
    ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=24)
    ItemDeKit.objects.create(entrega=entrega, material=fibra, cantidad=300)
    ItemDeKit.objects.create(
        entrega=entrega, material=ont, cantidad=1, serie="48575448A9B0C1"
    )
    return entrega


def mover(cliente, **campos):
    cuerpo = {"tipo": "consumo", **campos}
    return cliente.post(MOVIMIENTOS, cuerpo, format="json")


class TestElKitQueSeLleva:
    def test_1_lista_lo_recibido_con_su_saldo(self, user_client, kit):
        r = user_client.get(KIT)

        assert r.status_code == status.HTTP_200_OK
        por_codigo = {m["codigo"]: m for m in r.data["materiales"]}
        assert por_codigo["CON-SC-APC"]["recibido"] == "24"
        assert por_codigo["CON-SC-APC"]["disponible"] == "24"
        assert por_codigo["CON-SC-APC"]["unidad"] == "unidades"

    def test_2_los_seriales_viajan(self, user_client, kit):
        r = user_client.get(KIT)

        equipos = next(m for m in r.data["materiales"] if m["codigo"] == "ONT-HG8145")
        assert equipos["series"] == ["48575448A9B0C1"]
        assert equipos["clase"] == "serializado"

    def test_3_trae_el_acta_de_donde_salio(self, user_client, kit):
        r = user_client.get(KIT)

        assert r.data["materiales"][0]["acta"] == "K-2024-094"

    def test_4_sin_kit_entregado_responde_vacio_y_no_falla(self, user_client):
        r = user_client.get(KIT)

        assert r.status_code == status.HTTP_200_OK
        assert r.data["materiales"] == []

    def test_5_sin_sesion_no_se_llega(self, unauthenticated_client):
        assert unauthenticated_client.get(KIT).status_code in (401, 403)


class TestRegistrarLoQueSeGasto:
    def test_6_un_consumo_descuenta_del_kit(self, user_client, kit):
        r = mover(user_client, clave="mov-1", material="CON-SC-APC", cantidad="4")

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["resultados"][0]["estado"] == "aceptado"

        kit_ahora = user_client.get(KIT).data["materiales"]
        conector = next(m for m in kit_ahora if m["codigo"] == "CON-SC-APC")
        assert conector["disponible"] == "20"
        assert conector["consumido"] == "4"

    def test_7_la_fibra_se_gasta_en_metros_con_decimales(self, user_client, kit):
        r = mover(user_client, clave="mov-f", material="FIB-DROP", cantidad="42.5")

        assert r.status_code == status.HTTP_201_CREATED
        kit_ahora = user_client.get(KIT).data["materiales"]
        fibra = next(m for m in kit_ahora if m["codigo"] == "FIB-DROP")
        assert fibra["disponible"] == "257.5"

    def test_8_un_lote_entra_completo_en_una_sola_peticion(self, user_client, kit):
        """Lo que hace una cuadrilla al reconectar después de media jornada."""
        r = user_client.post(
            MOVIMIENTOS,
            {"movimientos": [
                {"clave": "m1", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "4"},
                {"clave": "m2", "material": "FIB-DROP", "tipo": "consumo",
                 "cantidad": "30"},
                {"clave": "m3", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "2"},
            ]},
            format="json",
        )

        assert r.status_code == status.HTTP_201_CREATED
        assert len(r.data["resultados"]) == 3
        assert {x["clave"] for x in r.data["resultados"]} == {"m1", "m2", "m3"}
        assert MovimientoDeMaterial.objects.count() == 3

    def test_9_se_puede_decir_en_que_trabajo_se_uso(
        self, user_client, kit, org_a, user_profile
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

        r = mover(
            user_client, clave="mov-ot", material="CON-SC-APC",
            cantidad="4", orden_id=str(orden.id),
        )

        assert r.status_code == status.HTTP_201_CREATED
        assert MovimientoDeMaterial.objects.get().orden_id == orden.id

    def test_10_una_devolucion_de_jornada_no_necesita_trabajo(
        self, user_client, kit
    ):
        r = mover(
            user_client, clave="dev-1", material="CON-SC-APC",
            cantidad="12", tipo="devolucion",
        )

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["resultados"][0]["estado"] == "aceptado"


class TestElReintentoNoDuplica:
    def test_11_la_misma_clave_dos_veces_descuenta_una(self, user_client, kit):
        """El caso normal, no el raro: la respuesta se pierde y la app
        reintenta exactamente lo mismo."""
        primero = mover(user_client, clave="mov-1", material="CON-SC-APC",
                        cantidad="4")
        segundo = mover(user_client, clave="mov-1", material="CON-SC-APC",
                        cantidad="4")

        assert primero.status_code == status.HTTP_201_CREATED
        assert segundo.status_code == status.HTTP_201_CREATED
        assert segundo.data["resultados"][0]["duplicado"] is True
        assert primero.data["resultados"][0]["id"] == segundo.data["resultados"][0]["id"]

        assert MovimientoDeMaterial.objects.count() == 1
        kit_ahora = user_client.get(KIT).data["materiales"]
        conector = next(m for m in kit_ahora if m["codigo"] == "CON-SC-APC")
        assert conector["disponible"] == "20"

    def test_12_un_lote_reenviado_entero_tampoco_duplica(self, user_client, kit):
        lote = {"movimientos": [
            {"clave": "m1", "material": "CON-SC-APC", "tipo": "consumo",
             "cantidad": "4"},
            {"clave": "m2", "material": "FIB-DROP", "tipo": "consumo",
             "cantidad": "30"},
        ]}

        user_client.post(MOVIMIENTOS, lote, format="json")
        user_client.post(MOVIMIENTOS, lote, format="json")

        assert MovimientoDeMaterial.objects.count() == 2

    def test_13_un_lote_a_medias_completa_lo_que_falta(self, user_client, kit):
        """El reintento trae lo viejo y lo nuevo junto: lo viejo se reconoce y
        lo nuevo entra. Si no, la app tendría que llevar la cuenta de qué llegó
        y qué no, que es justo lo que no puede saber."""
        user_client.post(
            MOVIMIENTOS,
            {"movimientos": [
                {"clave": "m1", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "4"},
            ]},
            format="json",
        )

        r = user_client.post(
            MOVIMIENTOS,
            {"movimientos": [
                {"clave": "m1", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "4"},
                {"clave": "m2", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "6"},
            ]},
            format="json",
        )

        por_clave = {x["clave"]: x for x in r.data["resultados"]}
        assert por_clave["m1"]["duplicado"] is True
        assert por_clave["m2"]["duplicado"] is False
        assert MovimientoDeMaterial.objects.count() == 2

        kit_ahora = user_client.get(KIT).data["materiales"]
        conector = next(m for m in kit_ahora if m["codigo"] == "CON-SC-APC")
        assert conector["disponible"] == "14"


class TestLoQueNoCuadraEntraIgual:
    def test_14_un_consumo_sin_saldo_responde_201_y_no_400(self, user_client, kit):
        """La prueba que define el contrato. El material ya se usó: negarse a
        guardarlo borraría el único registro que existe de eso."""
        r = mover(user_client, clave="mov-mas", material="CON-SC-APC",
                  cantidad="30")

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["resultados"][0]["estado"] == "descuadre"
        assert r.data["resultados"][0]["motivo"].strip()
        assert MovimientoDeMaterial.objects.count() == 1

    def test_15_el_descuadre_aparece_al_consultar_el_kit(self, user_client, kit):
        """Aceptar sin dejar rastro sería peor que rechazar."""
        mover(user_client, clave="mov-mas", material="CON-SC-APC", cantidad="30")

        r = user_client.get(KIT)

        assert len(r.data["sin_cuadrar"]) == 1
        assert r.data["sin_cuadrar"][0]["estado"] == "descuadre"
        assert r.data["sin_cuadrar"][0]["material"] == "CON-SC-APC"

    def test_16_una_serie_ya_instalada_entra_como_conflicto(self, user_client, kit):
        mover(user_client, clave="ont-1", material="ONT-HG8145", cantidad="1",
              serie="48575448A9B0C1")

        r = mover(user_client, clave="ont-2", material="ONT-HG8145",
                  cantidad="1", serie="48575448A9B0C1")

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["resultados"][0]["estado"] == "conflicto"
        assert "48575448A9B0C1" in r.data["resultados"][0]["motivo"]

    def test_17_un_lote_con_un_descuadre_guarda_los_demas(self, user_client, kit):
        """Que uno no cuadre no puede tirar el trabajo de toda la jornada."""
        r = user_client.post(
            MOVIMIENTOS,
            {"movimientos": [
                {"clave": "ok", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "4"},
                {"clave": "mal", "material": "CON-SC-APC", "tipo": "consumo",
                 "cantidad": "90"},
                {"clave": "ok2", "material": "FIB-DROP", "tipo": "consumo",
                 "cantidad": "10"},
            ]},
            format="json",
        )

        estados = {x["clave"]: x["estado"] for x in r.data["resultados"]}
        assert estados["ok"] == "aceptado"
        assert estados["mal"] == "descuadre"
        assert estados["ok2"] == "aceptado"
        assert MovimientoDeMaterial.objects.count() == 3


class TestLoQueSiSeRechaza:
    def test_18_un_material_que_no_existe(self, user_client, kit):
        """No hay hecho que preservar si no se sabe de qué material habla."""
        r = mover(user_client, clave="x", material="NO-EXISTE", cantidad="1")

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.data["error"] == "MATERIAL_DESCONOCIDO"
        assert "NO-EXISTE" in r.data["codigos"]
        assert MovimientoDeMaterial.objects.count() == 0

    def test_19_los_codigos_desconocidos_se_nombran_todos_de_una_vez(
        self, user_client, kit
    ):
        """Para que la app no descubra el siguiente en el reintento."""
        r = user_client.post(
            MOVIMIENTOS,
            {"movimientos": [
                {"clave": "a", "material": "NO-1", "tipo": "consumo", "cantidad": "1"},
                {"clave": "b", "material": "NO-2", "tipo": "consumo", "cantidad": "1"},
            ]},
            format="json",
        )

        assert sorted(r.data["codigos"]) == ["NO-1", "NO-2"]

    def test_20_una_cantidad_negativa(self, user_client, kit):
        """Para devolver está el tipo 'devolucion': explícito y legible en un
        listado, en vez de un signo que hay que interpretar."""
        r = mover(user_client, clave="neg", material="CON-SC-APC", cantidad="-5")

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert MovimientoDeMaterial.objects.count() == 0

    def test_21_un_tipo_de_movimiento_inventado(self, user_client, kit):
        r = mover(user_client, clave="raro", material="CON-SC-APC",
                  cantidad="1", tipo="regalado")

        assert r.status_code == status.HTTP_400_BAD_REQUEST


class TestElKitEsDeCadaUno:
    def test_22_el_material_de_otra_empresa_no_se_puede_mover(
        self, user_client, kit, org_b
    ):
        """Mismo código, otra organización: para este técnico no existe."""
        MaterialCatalogo.objects.create(
            org=org_b, codigo="AJENO-1", nombre="Material de otra empresa",
            clase=MaterialCatalogo.CONSUMIBLE,
        )

        r = mover(user_client, clave="x", material="AJENO-1", cantidad="1")

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.data["error"] == "MATERIAL_DESCONOCIDO"

    def test_23_el_kit_de_otro_tecnico_no_se_ve(
        self, user_client, org_a, admin_profile, conector
    ):
        entrega = EntregaDeKit.objects.create(
            org=org_a, profile=admin_profile, acta="K-AJENO"
        )
        ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=50)

        r = user_client.get(KIT)

        assert r.data["materiales"] == []

    def test_24_una_orden_ajena_no_ata_el_movimiento_pero_tampoco_lo_pierde(
        self, user_client, kit, org_b
    ):
        """El material se gastó igual: se guarda sin atar, en vez de fallar."""
        wt = WorkType.objects.create(org=org_b, codigo="ftth", nombre="Instalación")
        version = WorkTypeVersion.objects.create(
            work_type=wt, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"pasos": [], "campos": [], "evidencias": []},
        )
        ajena = OrdenTrabajo.objects.create(
            org=org_b, numero=9999, tipo_trabajo_version=version,
            estado_operativo=OrdenTrabajo.ASIGNADA,
        )

        r = mover(user_client, clave="mov-ajeno", material="CON-SC-APC",
                  cantidad="2", orden_id=str(ajena.id))

        assert r.status_code == status.HTTP_201_CREATED
        movimiento = MovimientoDeMaterial.objects.get()
        assert movimiento.orden_id is None
        assert movimiento.cantidad == 2
