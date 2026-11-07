# -*- coding: utf-8 -*-
"""
================================================================================
 UN ADJUNTO SE ABRE, Y SOLO EL DE LA PROPIA EMPRESA  --  07/11/2026
================================================================================
El usuario, con las fotos del tecnico ya listadas en el ticket del CRM:

    «en dexter salen adjuntado los archivos pero no permiten ver»

404 en `/media/attachments/2026/11/dano_encontrado-2.jpg`. `crm/urls.py`
sirve `/media/` SOLO con DEBUG, asi que en produccion NINGUN adjunto del CRM
se podia abrir -- no solo las fotos de campo. Las fotos solo lo hicieron
visible.

QUE AFIRMA ESTA GUARDA
----------------------
  · que el archivo SALGA, con sus bytes -- no que la vista exista
  · que el de OTRA empresa conteste 404, y no 403: un 403 ya confirma que el
    archivo existe
  · que sin sesion no salga nada
  · que un archivo que el navegador ejecutaria se DESCARGUE en vez de
    mostrarse: la extension la eligio quien subio, no puede decidir esto
  · que la respuesta no entre en una cache compartida
  · y que el serializer deje de emitir la URL que no funciona
================================================================================
"""
from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = pytest.mark.django_db

BYTES = b"\xff\xd8\xff\xe0 no es un jpg de verdad, pero son bytes"


def _adjunto(profile, nombre="dano_encontrado-2.jpg", datos=BYTES):
    """Un adjunto colgado de un ticket de la empresa del perfil."""
    from cases.models import Case
    from common.utils import create_attachment

    caso = Case.objects.create(org=profile.org, name="Problema de TV",
                               status="New", priority="Normal")
    return create_attachment(SimpleUploadedFile(nombre, datos), caso, profile)


def _url(adjunto):
    return f"/api/attachments/{adjunto.id}/archivo/"


# ---------------------------------------------------------------------------
#  QUE SALGA
# ---------------------------------------------------------------------------

def test_el_archivo_SALE_con_sus_bytes(user_client, user_profile):
    adjunto = _adjunto(user_profile)

    r = user_client.get(_url(adjunto))

    assert r.status_code == 200, r.status_code
    assert b"".join(r.streaming_content) == BYTES


def test_una_imagen_se_muestra_EN_LINEA(user_client, user_profile):
    adjunto = _adjunto(user_profile)

    r = user_client.get(_url(adjunto))

    assert r["Content-Type"] == "image/jpeg"
    assert "attachment;" not in r.get("Content-Disposition", "")


def test_la_respuesta_NO_queda_en_una_cache_compartida(user_client,
                                                       user_profile):
    adjunto = _adjunto(user_profile)

    r = user_client.get(_url(adjunto))

    assert "no-store" in r["Cache-Control"]
    assert "private" in r["Cache-Control"]
    assert r["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------------
#  QUE NO SALGA
# ---------------------------------------------------------------------------

def test_el_de_OTRA_empresa_contesta_404(org_b_client, user_profile):
    """404 y no 403: un 403 ya cuenta que el archivo existe."""
    adjunto = _adjunto(user_profile)

    r = org_b_client.get(_url(adjunto))

    assert r.status_code == 404, r.status_code


def test_sin_sesion_no_sale_nada(unauthenticated_client, user_profile):
    adjunto = _adjunto(user_profile)

    r = unauthenticated_client.get(_url(adjunto))

    assert r.status_code in (401, 403), r.status_code
    assert BYTES not in r.content


def test_una_fila_SIN_ARCHIVO_en_disco_contesta_404(user_client,
                                                    user_profile):
    import os

    adjunto = _adjunto(user_profile)
    os.remove(adjunto.attachment.path)

    r = user_client.get(_url(adjunto))

    assert r.status_code == 404


def test_un_id_que_no_existe_contesta_404(user_client):
    import uuid

    r = user_client.get(f"/api/attachments/{uuid.uuid4()}/archivo/")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
#  LO QUE EL NAVEGADOR EJECUTARIA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", ["pagina.html", "dibujo.svg",
                                    "script.js", "cualquiera.xyz"])
def test_lo_que_el_navegador_ejecutaria_SE_DESCARGA(user_client,
                                                    user_profile, nombre):
    """XSS con la sesion del usuario adentro, si se mostrara en linea."""
    adjunto = _adjunto(user_profile, nombre=nombre, datos=b"<script>x</script>")

    r = user_client.get(_url(adjunto))

    assert r.status_code == 200
    assert r["Content-Type"] == "application/octet-stream", r["Content-Type"]
    assert r["Content-Disposition"].startswith("attachment;"), \
        r["Content-Disposition"]


# ---------------------------------------------------------------------------
#  LA URL QUE SE EMITE
# ---------------------------------------------------------------------------

def test_el_serializer_YA_NO_emite_la_url_de_media(user_profile):
    """`/media/...` es la que contestaba 404 en produccion."""
    from common.serializer import AttachmentsSerializer

    adjunto = _adjunto(user_profile)

    camino = AttachmentsSerializer(adjunto).data["file_path"]

    assert camino == f"/api/attachments/{adjunto.id}/archivo/", camino
    assert "/media/" not in camino


def test_la_url_que_emite_el_serializer_ES_LA_QUE_RESPONDE(user_client,
                                                           user_profile):
    """Que las dos existan no prueba que sean la misma. Esta lo prueba."""
    from common.serializer import AttachmentsSerializer

    adjunto = _adjunto(user_profile)
    camino = AttachmentsSerializer(adjunto).data["file_path"]

    r = user_client.get(camino)

    assert r.status_code == 200
    assert b"".join(r.streaming_content) == BYTES
