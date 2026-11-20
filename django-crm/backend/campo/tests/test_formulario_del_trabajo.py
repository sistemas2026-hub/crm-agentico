# -*- coding: utf-8 -*-
"""
Lo que el técnico llenó en el formulario del trabajo llega a la oficina.

18/10/2026: `orden.datos` y las fotos del checklist se guardaban y ninguna
pantalla de la web los mostraba. Viajan ahora con la bitácora
(`GET /seguimiento/`), que el panel de la orden ya pide entera. Estas pruebas
pasan por esa vista, no solo por el servicio: un dato que el servicio calcula
y la vista no manda es justo el hueco que se está cerrando.
"""

import pytest
from rest_framework.test import APIClient

from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [],
    "campos": [
        {"id": "potencia_rx", "titulo": "Potencia Rx", "tipo": "decimal",
         "reglas": {"required": True}},
        {"id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
         "permite_otro": True,
         "reglas": {"options": ["Conector sucio", "Otro"]}},
        {"id": "cliente_conforme", "titulo": "Cliente conforme", "tipo": "booleano"},
        {"id": "observaciones", "titulo": "Observaciones", "tipo": "texto"},
    ],
    "evidencias": [
        {"id": "foto_ont", "titulo": "Foto de la ONT", "obligatorio": True},
        {"id": "foto_roseta", "titulo": "Foto de la roseta"},
    ],
}


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.form@test.com", password="testpass123")
    return user, Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


@pytest.fixture
def orden(org_a, tecnico):
    wt = WorkType.objects.create(org=org_a, codigo="soporte", nombre="Soporte")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA, schema_hash="h1")
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        datos={"potencia_rx": -19.5, "que_encontro": "Otro",
               "que_encontro_otro": "Roseta quemada", "cliente_conforme": False,
               "campo_de_antes": "valor viejo"})
    AsignacionTrabajo.objects.create(
        orden=o, profile=tecnico[1], rol="tecnico", es_principal=True)
    return o


def _foto(orden, requisito, estado="recibido", evento=None, sha="a"):
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        nombre_original="f.jpg", mime_type="image/jpeg", sha256=sha * 64,
        estado_archivo=estado, evento=evento)


def _leer(orden, tecnico):
    user, prof = tecnico
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, orden.org, prof)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    r = c.get(f"/api/campo/trabajos/{orden.id}/seguimiento/")
    assert r.status_code == 200
    return r.data["formulario_del_trabajo"]


def test_1_cada_campo_con_su_titulo_en_el_orden_de_la_plantilla(orden, tecnico):
    campos = _leer(orden, tecnico)["campos"]
    assert [(c["titulo"], c["valor"]) for c in campos[:4]] == [
        ("Potencia Rx", -19.5),
        ("Qué encontró", "Otro: Roseta quemada"),
        ("Cliente conforme", False),
        ("Observaciones", None),
    ]


def test_2_el_texto_de_otro_no_es_una_fila_aparte(orden, tecnico):
    ids = [c["id"] for c in _leer(orden, tecnico)["campos"]]
    assert "que_encontro_otro" not in ids


def test_3_un_falso_es_una_respuesta_y_un_vacio_no(orden, tecnico):
    por_id = {c["id"]: c for c in _leer(orden, tecnico)["campos"]}
    assert por_id["cliente_conforme"]["sin_responder"] is False
    assert por_id["observaciones"]["sin_responder"] is True
    assert por_id["potencia_rx"]["obligatorio"] is True


def test_4_lo_escrito_con_una_plantilla_anterior_no_desaparece(orden, tecnico):
    viejo = [c for c in _leer(orden, tecnico)["campos"] if c.get("fuera_de_la_plantilla")]
    assert [(c["id"], c["valor"]) for c in viejo] == [("campo_de_antes", "valor viejo")]


def test_5_las_fotos_del_checklist_por_requisito_y_sin_las_de_un_reporte(orden, tecnico):
    llegada = _foto(orden, "foto_ont", sha="a")
    _foto(orden, "foto_ont", estado="pendiente", sha="b")
    evento = EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                          tipo="avance_campo", datos={})
    _foto(orden, "foto_roseta", evento=evento, sha="c")

    fotos = {f["requisito_id"]: f for f in _leer(orden, tecnico)["fotos"]}

    ont = fotos["foto_ont"]
    assert ont["titulo"] == "Foto de la ONT" and ont["obligatorio"] is True
    assert [f["disponible"] for f in ont["fotos"]] == [True, False]
    assert ont["fotos"][0]["id"] == str(llegada.id)
    assert ont["sin_foto"] is False
    # La de la roseta cuelga de un reporte: se ve en la bitácora, no acá.
    assert fotos["foto_roseta"]["fotos"] == []
    assert fotos["foto_roseta"]["sin_foto"] is True


def test_6_una_foto_que_no_termino_de_subir_no_cuenta_como_tomada(orden, tecnico):
    _foto(orden, "foto_ont", estado="subiendo")
    ont = next(f for f in _leer(orden, tecnico)["fotos"] if f["requisito_id"] == "foto_ont")
    assert ont["sin_foto"] is True
