# -*- coding: utf-8 -*-
"""
El listado de trabajos entrega todas las órdenes, no las primeras cien.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
`TrabajosListView` cortaba duro en 100 filas y devolvía `next_cursor: null`
siempre (hallazgo del inventario del 22/09/2026). Para una cuadrilla con más
trabajo que eso, la orden 101 no existía: no aparecía en la lista, no se podía
abrir y el técnico no tenía forma de enterarse.

Lo que estas pruebas cuidan es que la paginación sea **estable**: que ninguna
orden se pierda entre páginas ni salga dos veces. Sin desempate por id, dos
órdenes creadas en el mismo instante se intercambian y una desaparece.
"""

import pytest

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def ciento_cinco(org_a, user_profile, version):
    """Más órdenes que el límite por página, todas del mismo técnico."""
    ordenes = []
    for numero in range(1, 106):
        o = OrdenTrabajo.objects.create(
            org=org_a, numero=numero, tipo_trabajo_version=version,
            cliente_nombre=f"Cliente {numero}",
            cliente_direccion="Calle 1",
            estado_operativo=OrdenTrabajo.ASIGNADA,
        )
        AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                         rol="tecnico", es_principal=True)
        ordenes.append(o)
    return ordenes


def _numeros(payload):
    return [o["numero"] for o in payload["results"]]


def test_1_la_orden_101_existe(user_client, ciento_cinco):
    """La prueba que más importa: antes, 5 de estas 105 no existían."""
    primera = user_client.get("/api/campo/trabajos/").json()
    assert len(primera["results"]) == 100
    assert primera["next_cursor"] is not None, "hay más y la respuesta no lo dice"

    segunda = user_client.get(
        f"/api/campo/trabajos/?cursor={primera['next_cursor']}"
    ).json()

    assert len(segunda["results"]) == 5
    assert segunda["next_cursor"] is None, "no hay más y la respuesta promete otra página"

    vistos = _numeros(primera) + _numeros(segunda)
    assert len(set(vistos)) == 105, "alguna orden salió dos veces o ninguna"
    assert set(vistos) == set(range(1, 106))


def test_2_la_ultima_pagina_no_promete_otra(user_client, org_a, user_profile, version):
    """Con menos órdenes que el límite, no hay cursor que seguir."""
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=1, tipo_trabajo_version=version,
        cliente_nombre="Único", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)

    payload = user_client.get("/api/campo/trabajos/").json()
    assert len(payload["results"]) == 1
    assert payload["next_cursor"] is None


def test_3_se_puede_pedir_una_pagina_mas_chica(user_client, ciento_cinco):
    """Una página chica sirve para el primer arranque sin señal buena."""
    payload = user_client.get("/api/campo/trabajos/?limite=10").json()

    assert len(payload["results"]) == 10
    assert payload["next_cursor"] is not None


def test_4_nadie_puede_pedir_la_tabla_entera(user_client, ciento_cinco):
    """
    El techo es duro: una respuesta gigante no entra en el teléfono y la
    sincronización se reintenta encima de sí misma.
    """
    payload = user_client.get("/api/campo/trabajos/?limite=99999").json()

    assert len(payload["results"]) <= 200


def test_5_un_cursor_roto_se_rechaza_en_vez_de_devolver_cualquier_cosa(
    user_client, ciento_cinco
):
    """Devolver la primera página ante un cursor inválido escondería el error."""
    r = user_client.get("/api/campo/trabajos/?cursor=esto-no-es-un-cursor")

    assert r.status_code == 400


def test_6_recorrer_todas_las_paginas_no_repite_ni_pierde(user_client, ciento_cinco):
    """El recorrido completo, como lo hace la aplicación al sincronizar."""
    vistos = []
    cursor = None

    for _ in range(20):  # tope de seguridad: no debería dar más de 11 vueltas
        url = "/api/campo/trabajos/?limite=10"
        if cursor:
            url += f"&cursor={cursor}"
        payload = user_client.get(url).json()
        vistos.extend(_numeros(payload))
        cursor = payload["next_cursor"]
        if cursor is None:
            break

    assert cursor is None, "el recorrido no terminó"
    assert len(vistos) == 105
    assert len(set(vistos)) == 105
