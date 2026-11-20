# -*- coding: utf-8 -*-
"""
================================================================================
 LA FOTO DE UN AVANCE: SE PIDE, SUBE, Y SE PUEDE VER
================================================================================

Pedido del usuario (15/10/2026): «en los avances, ¿por que no se puede adjuntar
imagen?». La app, la cola y el servidor ya sabian llevar la foto de un reporte,
pero el boton solo aparecia si la plantilla la pedia -- y ninguna la pedia, ni
habia donde configurarlo. Y al seguir el camino aparecio lo peor: aunque la
foto llegara, en produccion NADIE la podia ver. La unica URL que se emitia era
`/media/<key>`, que Django solo sirve con DEBUG.

  A  sin declarar, el avance y el bloqueo ofrecen una foto OPCIONAL
  B  EL CAMINO ENTERO: reporte -> registrar la foto colgada del reporte ->
     subir el binario -> confirmar -> la linea de tiempo la trae disponible ->
     el archivo se entrega con su contenido
  C  el archivo respeta el permiso de la orden: otra empresa y un tecnico NO
     asignado reciben 404; una foto que no termino de subir, tambien
  D  el editor de plantillas: las fotos de cada reporte se componen, se leen
     de vuelta, y lo que el editor muestra es lo que la app va a pedir

    pytest campo/tests/test_fotos_en_los_reportes.py
================================================================================
"""

import os

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from campo import plantillas as P
from campo.models import (AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services import seguimiento_campo as seg
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db

CONTENIDO = b"\xff\xd8\xff\xe0 FOTO DEL EMPALME"


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.fotos@test.com", password="x")
    return user, Profile.objects.create(user=user, org=org_a, role="USER",
                                        is_active=True)


@pytest.fixture
def otro_tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="otro.fotos@test.com", password="x")
    return user, Profile.objects.create(user=user, org=org_a, role="USER",
                                        is_active=True)


@pytest.fixture
def orden(org_a, tecnico):
    wt = WorkType.objects.create(org=org_a, codigo="corr", nombre="Correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        #  Una plantilla como las de hoy: NO declara nada de seguimiento.
        esquema={"pasos": [], "campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9301, tipo_trabajo_version=v,
        cliente_nombre="Cliente", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=tecnico[1],
                                     rol="tecnico_lider", es_principal=True)
    return o


def test_a_avance_y_bloqueo_ofrecen_foto_opcional_sin_declarar_nada(orden):
    avance = seg.formulario_de(orden, seg.AVANCE)["evidencias"]
    bloqueo = seg.formulario_de(orden, seg.BLOQUEO)["evidencias"]
    assert [e["id"] for e in avance] == ["foto_avance"]
    assert [e["id"] for e in bloqueo] == ["foto_bloqueo"]
    assert all(e["obligatorio"] is False for e in avance + bloqueo)
    assert seg.formulario_de(orden, seg.INICIO)["evidencias"] == []
    assert seg.formulario_de(orden, seg.CIERRE)["evidencias"] == []


def test_b_el_camino_entero_de_la_foto_de_un_avance(orden, tecnico, org_a):
    user, profile = tecnico
    c = _cliente(user, org_a, profile)

    # 1. El formulario que recibe la app ya pide la foto.
    r = c.get(f"/api/campo/trabajos/{orden.id}/seguimiento/")
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["formularios"]["avance"]["evidencias"]] \
        == ["foto_avance"]

    # 2. El reporte, como lo manda la cola del telefono.
    r = c.post(f"/api/campo/trabajos/{orden.id}/seguimiento/",
               {"momento": "avance", "respuestas": {"nota": "Empalme hecho"}},
               format="json", HTTP_IDEMPOTENCY_KEY="rep-1")
    assert r.status_code == 201, r.content
    evento_id = r.json()["id"]

    # 3. La foto, colgada de ESE reporte.
    r = c.post(f"/api/campo/trabajos/{orden.id}/evidencias/",
               {"requisito_id": "foto_avance", "evento_id": evento_id,
                "nombre": "avance.jpg", "mime_type": "image/jpeg",
                "bytes": len(CONTENIDO), "sha256": "f" * 64},
               format="json", HTTP_IDEMPOTENCY_KEY="ev-1")
    assert r.status_code == 200, r.content
    evidencia_id = r.json()["evidencia_id"]

    # 4. El binario llega y se confirma.
    ev = EvidenciaTrabajo.objects.get(pk=evidencia_id)
    ruta = os.path.join(settings.MEDIA_ROOT, ev.storage_key)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(CONTENIDO)
    r = c.post(f"/api/campo/evidencias/{evidencia_id}/confirmar/", {},
               format="json", HTTP_IDEMPOTENCY_KEY="conf-1")
    assert r.status_code == 200, r.content

    # 5. La linea de tiempo la trae en el avance, disponible.
    eventos = c.get(f"/api/campo/trabajos/{orden.id}/seguimiento/").json()["eventos"]
    avance = next(e for e in eventos if e["id"] == evento_id)
    assert [(f["id"], f["disponible"]) for f in avance["evidencias"]] \
        == [(evidencia_id, True)]
    assert "storage_key" not in avance["evidencias"][0]

    # 6. Y se puede VER: el archivo sale con su contenido.
    r = c.get(f"/api/campo/evidencias/{evidencia_id}/archivo/")
    assert r.status_code == 200
    assert b"".join(r.streaming_content) == CONTENIDO
    assert r["Content-Type"] == "image/jpeg"


def _foto_recibida(orden, estado=EvidenciaTrabajo.RECIBIDO):
    ev = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id="foto_x",
        storage_key=f"campo/test/{orden.id}/x.jpg", nombre_original="x.jpg",
        mime_type="image/jpeg", bytes=len(CONTENIDO), sha256="1" * 64,
        estado_archivo=estado)
    ruta = os.path.join(settings.MEDIA_ROOT, ev.storage_key)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(CONTENIDO)
    return ev


def test_c_el_archivo_respeta_el_permiso_de_la_orden(
        orden, tecnico, otro_tecnico, org_a, admin_client, org_b_client):
    ev = _foto_recibida(orden)
    ruta = f"/api/campo/evidencias/{ev.id}/archivo/"

    assert _cliente(tecnico[0], org_a, tecnico[1]).get(ruta).status_code == 200
    assert admin_client.get(ruta).status_code == 200          # gestion ve todo
    # Un tecnico de la misma empresa, pero NO asignado: 404, igual que la orden.
    ajeno = _cliente(otro_tecnico[0], org_a, otro_tecnico[1])
    assert ajeno.get(ruta).status_code == 404
    assert ajeno.get(f"/api/campo/evidencias/{ev.id}/url/").status_code == 404
    # Otra empresa: 404, nunca 403.
    assert org_b_client.get(ruta).status_code == 404


def test_c2_una_foto_que_no_termino_de_subir_no_se_entrega(orden, admin_client):
    ev = _foto_recibida(orden, estado=EvidenciaTrabajo.SUBIENDO)
    assert admin_client.get(f"/api/campo/evidencias/{ev.id}/archivo/").status_code == 404


def test_c3_lo_que_no_es_imagen_se_descarga_no_se_muestra(orden, admin_client):
    ev = _foto_recibida(orden)
    ev.mime_type = "text/html"
    ev.save(update_fields=["mime_type"])
    r = admin_client.get(f"/api/campo/evidencias/{ev.id}/archivo/")
    assert r.status_code == 200
    assert r["Content-Type"] == "application/octet-stream"
    assert r["Content-Disposition"].startswith("attachment")


def test_d_el_editor_compone_y_lee_las_fotos_de_cada_reporte():
    base = P.definicion_de_base(P.CATALOGO_BASE[0])
    # Quien adopta ve lo que la app va a pedir.
    assert [e["titulo"] for e in base["fotos_de_reportes"]["avance"]] == ["Foto del avance"]
    assert base["fotos_de_reportes"]["inicio"] == []

    base["fotos_de_reportes"] = {
        "inicio": [{"titulo": "Fachada"}],
        "avance": [{"titulo": "Empalme"}, {"titulo": "Caja NAP"}],
        "bloqueo": [],
        "cierre": [],
    }
    esquema = P.componer(base)
    seg_ = esquema["seguimiento"]
    assert [e["titulo"] for e in seg_["avance"]["evidencias"]] == ["Empalme", "Caja NAP"]
    assert all(e["obligatorio"] is False for e in seg_["avance"]["evidencias"])
    # Vacio se ESCRIBE: si no, volveria la foto por defecto y el editor mentiria.
    assert seg_["bloqueo"] == {"evidencias": []}

    definicion, motivos = P.leer_definicion(esquema)
    assert motivos == []
    assert [e["titulo"] for e in definicion["fotos_de_reportes"]["avance"]] \
        == ["Empalme", "Caja NAP"]
    assert definicion["fotos_de_reportes"]["bloqueo"] == []
    # Y releer + recomponer no cambia nada: los ids se conservan.
    assert P.componer(definicion)["seguimiento"] == seg_


def test_d2_lo_que_el_editor_no_maneja_se_dice():
    _, motivos = P.leer_definicion(
        {"campos": [{"id": "a", "titulo": "A", "tipo": "texto", "reglas": {}}],
         "seguimiento": {"avance": {"campos": [{"id": "x"}]}}})
    assert any("datos propios" in m for m in motivos)

    base = P.definicion_de_base(P.CATALOGO_BASE[0])
    base["fotos_de_reportes"] = {"avance": [{"titulo": f"F{i}"} for i in range(6)]}
    with pytest.raises(P.ErrorPlantilla):
        P.componer(base)
    base["fotos_de_reportes"] = {"almuerzo": []}
    with pytest.raises(P.ErrorPlantilla):
        P.componer(base)
