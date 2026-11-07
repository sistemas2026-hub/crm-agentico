# -*- coding: utf-8 -*-
"""
Lo que decide la oficina y el técnico no puede deducir.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
Ocho datos que la orden no sabía decir y la aplicación dibujaba de ejemplo:
prioridad, zona, resumen, la franja prometida al cliente, cuándo vence el
compromiso, cómo se entra al inmueble, el identificador del abonado y qué
requisitos de seguridad tiene el trabajo (tanda 2 de
`SPEC/BACKEND_CAMPO_DATOS.md`).

Dos cosas se cuidan acá. La primera: que viajen. La segunda, más importante:
que una orden que no los trae **siga siendo válida**, porque hay miles ya
creadas y ninguna los tiene.
"""

import pytest
from django.utils import timezone

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.despacho import crear_orden

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
def orden_completa(org_a, user_profile, version):
    """Una orden despachada con todo lo que la oficina sabe."""
    inicio = timezone.now().replace(hour=9, minute=30, second=0, microsecond=0)
    orden = crear_orden(
        org=org_a,
        profile=user_profile,
        version=version,
        cliente={
            "nombre": "Talleres Unidos",
            "direccion": "Zona Industrial Cra 50 #18-04",
            "detalle_acceso": "Galpón 3, portería lateral",
            "id_abonado": "WH-10984214",
        },
        despacho={
            "prioridad": OrdenTrabajo.PRIORIDAD_ALTA,
            "zona": "Industrial Sur",
            "resumen": "Reubicación de acometida exterior",
            "ventana_inicio": inicio,
            "ventana_fin": inicio.replace(hour=11),
            "sla_vence_en": inicio.replace(hour=13),
            "requisitos_seguridad": ["trabajo_en_altura"],
        },
    )
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return orden


def test_1_el_detalle_entrega_lo_que_decidio_la_oficina(user_client, orden_completa):
    d = user_client.get(f"/api/campo/trabajos/{orden_completa.id}/").json()

    assert d["prioridad"] == "alta"
    assert d["zona"] == "Industrial Sur"
    assert d["resumen"] == "Reubicación de acometida exterior"
    assert d["requisitos_seguridad"] == ["trabajo_en_altura"]


def test_2_como_se_entra_al_inmueble_viaja_con_el_cliente(user_client, orden_completa):
    """Con la dirección sola, el técnico llega al edificio y no al galpón."""
    cliente = user_client.get(f"/api/campo/trabajos/{orden_completa.id}/").json()["cliente"]

    assert cliente["detalle_acceso"] == "Galpón 3, portería lateral"
    assert cliente["id_abonado"] == "WH-10984214"


def test_3_la_franja_prometida_no_es_lo_mismo_que_la_hora_programada(
    user_client, orden_completa
):
    """
    Tres fechas distintas, y la aplicación las muestra distinto: cuándo se
    agendó, qué franja se le prometió al abonado y cuándo vence el compromiso.
    """
    compromiso = user_client.get(
        f"/api/campo/trabajos/{orden_completa.id}/"
    ).json()["compromiso"]

    assert compromiso["ventana_inicio"] is not None
    assert compromiso["ventana_fin"] is not None
    assert compromiso["sla_vence_en"] is not None
    assert compromiso["ventana_inicio"] < compromiso["ventana_fin"]
    assert compromiso["ventana_fin"] < compromiso["sla_vence_en"]


def test_4_tambien_viajan_en_el_listado(user_client, orden_completa):
    """La lista ordena y agrupa con esto; no puede pedir el detalle de cada fila."""
    fila = user_client.get("/api/campo/trabajos/").json()["results"][0]

    assert fila["prioridad"] == "alta"
    assert fila["zona"] == "Industrial Sur"
    assert fila["compromiso"]["ventana_inicio"] is not None
    assert fila["cliente"]["detalle_acceso"] == "Galpón 3, portería lateral"


def test_5_una_orden_sin_nada_de_esto_sigue_siendo_valida(
    user_client, org_a, user_profile, version
):
    """
    Lo que más importa de la tanda: hay miles de órdenes ya creadas y ninguna
    trae estos campos. Ninguna puede romperse.
    """
    orden = crear_orden(
        org=org_a, profile=user_profile, version=version,
        cliente={"nombre": "Cliente viejo", "direccion": "Calle 1"},
    )
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)

    d = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()

    assert d["prioridad"] == "media", "sin prioridad declarada, la del medio"
    assert d["zona"] == ""
    assert d["resumen"] == ""
    assert d["requisitos_seguridad"] == []
    assert d["compromiso"]["ventana_inicio"] is None
    assert d["cliente"]["detalle_acceso"] == ""


def test_6_una_prioridad_inventada_no_entra(admin_client, org_a, version):
    """
    La prioridad ordena la jornada. Si se acepta cualquier texto, ordenar deja
    de significar algo.
    """
    r = admin_client.post(
        "/api/campo/trabajos/crear/",
        data={
            "work_type_version_id": str(version.id),
            "cliente_nombre": "Cliente",
            "cliente_direccion": "Calle 1",
            "prioridad": "urgentisima",
        },
        format="json",
        headers={"Idempotency-Key": "clave-prioridad-invalida"},
    )

    assert r.status_code == 400


def test_7_el_despacho_crea_la_orden_con_los_campos_que_le_mandan(
    admin_client, org_a, version
):
    """El camino completo: entra por la API y queda guardado."""
    r = admin_client.post(
        "/api/campo/trabajos/crear/",
        data={
            "work_type_version_id": str(version.id),
            "cliente_nombre": "María Fernández",
            "cliente_direccion": "Cra. 48 # 12-30",
            "cliente_detalle_acceso": "Apto 402, timbre 402",
            "prioridad": "alta",
            "zona": "Norte Urbano",
            "resumen": "Instalación nueva de fibra",
            "requisitos_seguridad": ["trabajo_en_altura"],
        },
        format="json",
        headers={"Idempotency-Key": "clave-despacho-completo"},
    )

    assert r.status_code == 201, r.content
    orden = OrdenTrabajo.objects.get(id=r.json()["orden"]["id"])
    assert orden.prioridad == "alta"
    assert orden.zona == "Norte Urbano"
    assert orden.resumen == "Instalación nueva de fibra"
    assert orden.cliente_detalle_acceso == "Apto 402, timbre 402"
    assert orden.requisitos_seguridad == ["trabajo_en_altura"]


def _del_ticket(org, user_profile, version, nombre_del_ticket):
    from cases.models import Case

    caso = Case.objects.create(org=org, name=nombre_del_ticket, status="New",
                               priority="Normal", is_active=True)
    orden = crear_orden(org=org, profile=user_profile, version=version,
                        cliente={"nombre": "Talleres Unidos", "direccion": "Calle 1"},
                        origen_sistema="crm", origen_tipo="case",
                        origen_ref=str(caso.id))
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return orden


def test_7_el_asunto_del_ticket_viaja_en_la_lista_y_en_el_detalle(
    user_client, org_a, user_profile, version, orden_completa
):
    """
    La tarjeta de la app, como la de Programación (29/10/2026, el usuario: «la
    tarjeta quedó bien, ¿en la app debe salir así también?»): el asunto del
    ticket es el título. Sin el cliente que el nombre del ticket trae pegado, y
    vacío —no inventado— si la orden no nació de un ticket.
    """
    del_ticket = _del_ticket(org_a, user_profile, version,
                             "No Tiene Internet - Talleres Unidos")

    filas = {f["id"]: f for f in user_client.get("/api/campo/trabajos/").json()["results"]}
    detalle = user_client.get(f"/api/campo/trabajos/{del_ticket.id}/").json()

    assert filas[str(del_ticket.id)]["asunto"] == "No Tiene Internet"
    assert detalle["asunto"] == "No Tiene Internet"
    assert filas[str(orden_completa.id)]["asunto"] == "", "sin ticket no hay asunto"


def test_8_la_lista_lee_los_asuntos_de_una_vez_y_no_uno_por_orden(
    user_client, org_a, user_profile, version
):
    """Una página trae hasta 100 órdenes: una consulta por orden la frenaría."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for n in range(3):
        _del_ticket(org_a, user_profile, version, f"Cambio De Clave - Cliente {n}")

    with CaptureQueriesContext(connection) as q:
        filas = user_client.get("/api/campo/trabajos/").json()["results"]

    assert [f["asunto"] for f in filas] == ["Cambio De Clave"] * 3
    assert sum(1 for c in q.captured_queries if 'FROM "case"' in c["sql"]) == 1
