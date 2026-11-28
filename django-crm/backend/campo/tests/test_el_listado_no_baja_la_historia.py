# -*- coding: utf-8 -*-
"""
================================================================================
 EL LISTADO DEL TELEFONO NO BAJA LA HISTORIA ENTERA  --  21/11/2026
================================================================================
EL USUARIO
----------
    «la app demora mucho en sincronizar y eso que tiene conexion wifi (...)
     sale siempre sincronizando (...) a las horas es que sincronizan»

LO QUE SE LEYO EN EL CODIGO (no medido en el telefono)
-------------------------------------------------------
Cada pasada de la app baja el listado de ordenes y, POR CADA UNA, pide su
detalle, una detras de otra (`sync_queue_service.dart::_descargarOrdenesAsignadas`).
Lo hace DOS veces por pasada --al empezar y al terminar-- y lo que el tecnico
escribio no empieza a subir hasta que la primera termina.

Y este listado le devolvia TODAS las ordenes que alguna vez tuvo asignadas, en
cualquier estado: las cerradas de hace un mes tambien. El costo de sincronizar
crecia con la antiguedad del tecnico, no con su trabajo del dia: con 200
ordenes en la historia son mas de 400 pedidos por pasada antes y despues de
mandar una foto.

LO QUE SE MIDE ACA
------------------
Que lo TERMINADO hace dias ya no viaja, y que nada de lo que el tecnico puede
tener entre manos se cae del listado. La app suelta sola lo que el servidor
deja de listarle (`soltarOrdenesQueYaNoSonMias`), y protege lo que tenga algo
sin subir.
================================================================================
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

RUTA = "/api/campo/trabajos/"


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


def _orden(org, version, profile, numero, estado, *, hace_dias=0):
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre=f"Cliente {numero}", cliente_direccion="Calle 1",
        estado_operativo=estado)
    AsignacionTrabajo.objects.create(orden=o, profile=profile, rol="tecnico",
                                     es_principal=True)
    if hace_dias:
        #  `updated_at` es `auto_now`: solo un `update` lo deja en el pasado.
        OrdenTrabajo.objects.filter(pk=o.pk).update(
            updated_at=timezone.now() - dt.timedelta(days=hace_dias))
    return o


def _numeros(cliente, ruta=RUTA):
    return sorted(o["numero"] for o in cliente.get(ruta).json()["results"])


def test_lo_cerrado_y_lo_cancelado_hace_dias_ya_no_viaja(
        user_client, org_a, user_profile, version):
    _orden(org_a, version, user_profile, 1, OrdenTrabajo.ASIGNADA)
    _orden(org_a, version, user_profile, 2, OrdenTrabajo.CERRADA, hace_dias=30)
    _orden(org_a, version, user_profile, 3, OrdenTrabajo.CANCELADA, hace_dias=30)

    assert _numeros(user_client) == [1]


def test_lo_que_termino_HOY_sigue_en_el_telefono(
        user_client, org_a, user_profile, version):
    """La pantalla de la jornada cuenta lo que hizo en el dia."""
    _orden(org_a, version, user_profile, 1, OrdenTrabajo.CERRADA)
    _orden(org_a, version, user_profile, 2, OrdenTrabajo.CANCELADA, hace_dias=1)

    assert _numeros(user_client) == [1, 2]


def test_el_borde_justo_antes_del_corte_se_queda_justo_despues_se_va(
        user_client, org_a, user_profile, version):
    from campo.views import DIAS_DE_TERMINADAS_EN_EL_LISTADO as DIAS

    _orden(org_a, version, user_profile, 1, OrdenTrabajo.CERRADA,
           hace_dias=DIAS - 1)
    _orden(org_a, version, user_profile, 2, OrdenTrabajo.CERRADA,
           hace_dias=DIAS + 1)

    assert _numeros(user_client) == [1]


@pytest.mark.parametrize("estado", [
    OrdenTrabajo.ASIGNADA, OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO,
    OrdenTrabajo.BLOQUEADA, OrdenTrabajo.CORRECCION_REQUERIDA,
    OrdenTrabajo.COMPLETADA_CAMPO,
])
def test_NADA_de_lo_que_sigue_abierto_se_cae_por_viejo(
        user_client, org_a, user_profile, version, estado):
    """Una orden detenida hace un mes, o devuelta y sin corregir, es justo la
    que el tecnico tiene que seguir viendo. Y la completada en campo todavia
    puede volverle devuelta."""
    _orden(org_a, version, user_profile, 1, estado, hace_dias=40)

    assert _numeros(user_client) == [1]


def test_quien_PIDE_un_estado_lo_recibe_entero(
        user_client, org_a, user_profile, version):
    """El recorte es del listado que la app baja para trabajar. Quien pide
    las cerradas a proposito las quiere todas."""
    _orden(org_a, version, user_profile, 1, OrdenTrabajo.CERRADA, hace_dias=30)

    assert _numeros(user_client, RUTA + "?estado=cerrada") == [1]


def test_y_se_puede_pedir_la_historia_completa(
        user_client, org_a, user_profile, version):
    _orden(org_a, version, user_profile, 1, OrdenTrabajo.ASIGNADA)
    _orden(org_a, version, user_profile, 2, OrdenTrabajo.CERRADA, hace_dias=30)

    assert _numeros(user_client, RUTA + "?historia=completa") == [1, 2]


def test_el_detalle_de_una_vieja_se_sigue_pudiendo_abrir(
        user_client, org_a, user_profile, version):
    """Sale del LISTADO, no deja de existir: un telefono que todavia la tiene
    con algo sin subir tiene que poder terminar de mandarlo."""
    o = _orden(org_a, version, user_profile, 1, OrdenTrabajo.CERRADA,
               hace_dias=30)

    assert user_client.get(f"{RUTA}{o.id}/").status_code == 200


def test_la_paginacion_no_promete_una_pagina_de_viejas(
        user_client, org_a, user_profile, version):
    """El cursor se calcula sobre lo que queda: si todo lo que seguia era
    historia, no hay pagina siguiente que pedir."""
    for n in range(1, 4):
        _orden(org_a, version, user_profile, n, OrdenTrabajo.ASIGNADA)
    for n in range(4, 10):
        _orden(org_a, version, user_profile, n, OrdenTrabajo.CERRADA,
               hace_dias=30)

    payload = user_client.get(RUTA + "?limite=3").json()

    assert len(payload["results"]) == 3
    assert payload["next_cursor"] is None
