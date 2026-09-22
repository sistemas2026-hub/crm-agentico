# -*- coding: utf-8 -*-
"""
Cerrar la jornada desde el teléfono.

Lo que se prueba acá es el contrato que la app va a consumir: qué devuelve el
día, qué impide cerrarlo, y que cerrar dos veces no genere dos actas.
"""

import pytest
from rest_framework import status

from campo.models import (
    ActaDeDevolucion,
    AsignacionTrabajo,
    EntregaDeKit,
    IncidenciaDeMaterial,
    ItemDeKit,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)

pytestmark = pytest.mark.django_db

MOVIMIENTOS = "/api/campo/materiales/movimientos/"
INCIDENCIAS = "/api/campo/materiales/incidencias/"
JORNADA = "/api/campo/jornada/"
CERRAR = "/api/campo/jornada/cerrar/"


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades",
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


def consumir(cliente, orden, cantidad="3", clave="c1"):
    return cliente.post(MOVIMIENTOS, {
        "clave": clave, "material": "CON-SC-APC", "tipo": "consumo",
        "cantidad": cantidad, "orden_id": str(orden.id),
    }, format="json")


def devolver(cliente, cantidad="7", clave="d1"):
    return cliente.post(MOVIMIENTOS, {
        "clave": clave, "material": "CON-SC-APC", "tipo": "devolucion",
        "cantidad": cantidad,
    }, format="json")


class TestComoVaElDia:
    def test_1_el_resumen_trae_las_ordenes_y_el_material(
        self, user_client, kit, orden
    ):
        consumir(user_client, orden)

        r = user_client.get(JORNADA)

        assert r.status_code == status.HTTP_200_OK
        assert r.data["resumen"]["ordenes"]["asignadas"] == 1
        assert r.data["resumen"]["material"]["recibido"] == "10"
        assert r.data["resumen"]["material"]["a_devolver"] == "7"

    def test_2_dice_si_se_puede_cerrar_y_por_que_no(
        self, user_client, kit, orden
    ):
        consumir(user_client, orden)
        devolver(user_client, cantidad="5")

        r = user_client.get(JORNADA)

        assert r.data["puede_cerrar"] is False
        assert len(r.data["motivos"]) == 1
        assert "Conector SC/APC" in r.data["motivos"][0]

    def test_3_con_todo_cuadrado_dice_que_si(self, user_client, kit, orden):
        consumir(user_client, orden)
        devolver(user_client)

        r = user_client.get(JORNADA)

        assert r.data["puede_cerrar"] is True
        assert r.data["motivos"] == []

    def test_4_sin_sesion_no_se_llega(self, unauthenticated_client):
        assert unauthenticated_client.get(JORNADA).status_code in (401, 403)


class TestRegistrarLoQueFalta:
    def test_5_una_incidencia_explica_la_diferencia(
        self, user_client, kit, orden
    ):
        consumir(user_client, orden)
        devolver(user_client, cantidad="5")

        r = user_client.post(INCIDENCIAS, {
            "clave": "inc-1", "material": "CON-SC-APC", "tipo": "danado",
            "cantidad": "2",
            "motivo": "Se dañaron al retirarlos de la caja terminal.",
        }, format="json")

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["resultados"][0]["estado"] == "registrada"
        assert user_client.get(JORNADA).data["puede_cerrar"] is True

    def test_6_sin_motivo_se_rechaza_esa_linea(self, user_client, kit):
        r = user_client.post(INCIDENCIAS, {
            "clave": "inc-1", "material": "CON-SC-APC", "tipo": "perdido",
            "cantidad": "2", "motivo": "   ",
        }, format="json")

        assert r.data["resultados"][0]["estado"] == "rechazada"
        assert IncidenciaDeMaterial.objects.count() == 0

    def test_7_reenviarla_no_la_duplica(self, user_client, kit):
        cuerpo = {
            "clave": "inc-1", "material": "CON-SC-APC", "tipo": "perdido",
            "cantidad": "2", "motivo": "Se cayeron de la escalera.",
        }

        user_client.post(INCIDENCIAS, cuerpo, format="json")
        r = user_client.post(INCIDENCIAS, cuerpo, format="json")

        assert r.data["resultados"][0]["duplicada"] is True
        assert IncidenciaDeMaterial.objects.count() == 1

    def test_8_un_lote_de_incidencias_entra_junto(self, user_client, kit):
        r = user_client.post(INCIDENCIAS, {"incidencias": [
            {"clave": "i1", "material": "CON-SC-APC", "tipo": "perdido",
             "cantidad": "1", "motivo": "Se perdió uno."},
            {"clave": "i2", "material": "CON-SC-APC", "tipo": "danado",
             "cantidad": "1", "motivo": "Se dañó otro."},
        ]}, format="json")

        assert len(r.data["resultados"]) == 2
        assert IncidenciaDeMaterial.objects.count() == 2


class TestCerrarLaJornada:
    def test_9_con_todo_cuadrado_cierra(self, user_client, kit, orden):
        consumir(user_client, orden)
        devolver(user_client)

        r = user_client.post(CERRAR, {}, format="json")

        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["estado"] == "confirmada"
        assert r.data["resumen"]["material"]["consumido"] == "3"

    def test_10_con_diferencias_sin_explicar_se_niega(
        self, user_client, kit, orden
    ):
        consumir(user_client, orden)
        devolver(user_client, cantidad="5")

        r = user_client.post(CERRAR, {}, format="json")

        assert r.status_code == status.HTTP_409_CONFLICT
        assert r.data["error"] == "JORNADA_INCOMPLETA"
        assert r.data["motivos"]
        assert ActaDeDevolucion.objects.count() == 0

    def test_11_cerrar_dos_veces_no_crea_dos_actas(
        self, user_client, kit, orden
    ):
        consumir(user_client, orden)
        devolver(user_client)

        primera = user_client.post(CERRAR, {}, format="json")
        segunda = user_client.post(CERRAR, {}, format="json")

        assert primera.data["acta_id"] == segunda.data["acta_id"]
        assert ActaDeDevolucion.objects.count() == 1

    def test_12_despues_de_cerrar_el_dia_devuelve_lo_congelado(
        self, user_client, kit, orden
    ):
        """No un cálculo nuevo: el acta es lo que se acordó ese día."""
        consumir(user_client, orden)
        devolver(user_client)
        user_client.post(CERRAR, {}, format="json")

        # Algo pasa después del cierre.
        user_client.post(MOVIMIENTOS, {
            "clave": "tardio", "material": "CON-SC-APC", "tipo": "ajuste",
            "cantidad": "5",
        }, format="json")

        r = user_client.get(JORNADA)

        assert r.data["estado"] == "confirmada"
        assert r.data["resumen"]["material"]["recibido"] == "10"
        assert r.data["puede_cerrar"] is False

    def test_13_la_jornada_de_otra_persona_no_se_ve(
        self, user_client, org_a, admin_profile, conector
    ):
        entrega = EntregaDeKit.objects.create(
            org=org_a, profile=admin_profile, acta="K-AJENO"
        )
        ItemDeKit.objects.create(entrega=entrega, material=conector, cantidad=99)

        r = user_client.get(JORNADA)

        assert r.data["resumen"]["material"]["recibido"] == "0"
