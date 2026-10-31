# -*- coding: utf-8 -*-
"""
================================================================================
 UNA PLANTILLA NACE CON SUS ASUNTOS  --  21/10/2026
================================================================================

Pedido del usuario: «un boton funcional que permita crear y editar las
plantillas y que permita agregar los asuntos de esa plantilla». Hasta hoy se
creaba sin asuntos y habia que abrirla y publicarla para cargarlos; en
produccion, las 5 plantillas tenian 0.

Se afirma sobre el EFECTO, no sobre que el campo se guarde:

  A  creada con asuntos, Despacho la ELIGE para un ticket con ese asunto
     (escrito de otra forma: mayusculas, tildes, espacios)
  B  un asunto que ya es de otra plantilla se rechaza, y NO queda una
     plantilla creada a medias
  C  con asuntos y sin labor se rechaza (D7 de labores propias), al crear y
     al publicar; sin asuntos, sin labor sigue pudiendo crearse
  D  el plazo viaja desde el alta
  E  sin asuntos ni plazo, crear hace lo de siempre

    pytest campo/tests/test_plantilla_con_asuntos_al_crear.py
================================================================================
"""

import pytest

from campo import plantillas as P
from campo.despacho_pantalla_views import plantillas_que_se_ofrecen
from campo.models import WorkType

pytestmark = pytest.mark.django_db

LISTA = "/api/campo/plantillas/"
DEFINICION = {"campos": [{"titulo": "Que se hizo", "tipo": "texto"}],
              "evidencias": [{"titulo": "Trabajo terminado"}]}


def _crear(cliente, **extra):
    return cliente.post(LISTA, {"nombre": "Traslado", "labor": "correctivo",
                                "definicion": DEFINICION, **extra},
                        format="json")


def test_a_creada_con_asuntos_despacho_la_elige(admin_client, org_a):
    r = _crear(admin_client, asuntos=["Cambio De Domicilio", "Traslado"])
    assert r.status_code == 201, r.content
    assert r.json()["asuntos"] == ["Cambio De Domicilio", "Traslado"]

    elegida = P.plantilla_para_asunto(plantillas_que_se_ofrecen(org_a),
                                      "  cambio de DOMICÍLIO ")
    assert elegida is not None
    assert str(elegida.work_type_id) == r.json()["id"]


def test_b_un_asunto_de_otra_plantilla_no_deja_nada_a_medias(admin_client, org_a):
    assert _crear(admin_client, asuntos=["Cambio De Domicilio"]).status_code == 201
    r = admin_client.post(LISTA, {"nombre": "Otra", "labor": "correctivo",
                                  "definicion": DEFINICION,
                                  "asuntos": ["cambio de domicilio"]},
                          format="json")
    assert r.status_code == 400, r.content
    assert "Traslado" in r.json()["detalle"]
    assert not WorkType.objects.filter(org=org_a, nombre="Otra").exists()


def test_c_con_asuntos_y_sin_labor_no_se_crea(admin_client, org_a):
    r = _crear(admin_client, labor="", asuntos=["Cambio De Domicilio"])
    assert r.status_code == 400, r.content
    assert r.json()["error"] == "ASUNTOS_SIN_LABOR"
    assert not WorkType.objects.filter(org=org_a).exists()

    #  Sin asuntos, sin labor sigue siendo valido: se clasifica despues.
    assert _crear(admin_client, labor="").status_code == 201


def test_c2_y_publicar_tampoco_lo_deja(admin_client, org_a):
    tipo_id = _crear(admin_client, asuntos=["Cambio De Domicilio"]).json()["id"]
    r = admin_client.post(f"{LISTA}{tipo_id}/publicar/",
                          {"definicion": DEFINICION, "labor": ""}, format="json")
    assert r.status_code == 400, r.content
    assert WorkType.objects.get(pk=tipo_id).labor == "correctivo"


def test_d_el_plazo_viaja_desde_el_alta(admin_client, org_a):
    r = _crear(admin_client, plazo_dias=3)
    assert r.status_code == 201, r.content
    assert WorkType.objects.get(pk=r.json()["id"]).plazo_dias == 3


def test_e_sin_asuntos_ni_plazo_es_lo_de_siempre(admin_client, org_a):
    r = _crear(admin_client)
    assert r.status_code == 201, r.content
    tipo = WorkType.objects.get(pk=r.json()["id"])
    assert tipo.asuntos == [] and tipo.plazo_dias is None
