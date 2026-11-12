# -*- coding: utf-8 -*-
"""
================================================================================
 LA ORDEN QUEDA UNIDA A SU TICKET  --  12/11/2026
================================================================================
Auditoria del menu §2 «Tickets»: «Ticket ↔ orden de campo cortado». La orden
nombraba su caso solo por texto. Desde campo/0049 hay un FK `caso`:

  A  `crear_orden` lo escribe cuando la orden nace de un caso de la empresa
  B  un `origen_ref` de OTRA empresa no une (aislamiento): queda NULL
  C  un texto que no es id, o un origen que no es caso, no une
  D  el relleno de 0049 sobre filas existentes: une las suyas, no las ajenas,
     y no depende de que la sesion tenga el contexto RLS puesto
  E  borrar el ticket no borra la orden (SET_NULL)

    pytest campo/tests/test_orden_unida_al_caso.py
================================================================================
"""
import importlib
import itertools
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from cases.models import Case
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import despacho as D
from conftest import clear_rls_context, rls_org, set_rls_context

pytestmark = pytest.mark.django_db

_n = itertools.count(9000)


def _version(org):
    tipo = WorkType.objects.get_or_create(org=org, codigo="t", defaults={
        "nombre": "T", "labor": "correctivo"})[0]
    return WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]


def _crear(org, ref, tipo="case"):
    return D.crear_orden(org=org, profile=None, version=_version(org),
                         cliente={"nombre": "Cliente"}, origen_sistema="crm",
                         origen_tipo=tipo, origen_ref=ref)


def _caso(org, nombre="No tiene internet"):
    return Case.objects.create(org=org, name=nombre, status="New", priority="Normal")


def test_a_crear_orden_desde_un_caso_lo_une(org_a):
    caso = _caso(org_a)
    orden = _crear(org_a, str(caso.pk))
    orden.refresh_from_db()
    assert orden.caso_id == caso.pk
    assert list(caso.ordenes_de_campo.all()) == [orden]


def test_b_el_caso_de_otra_empresa_no_se_une(org_a, org_b):
    with rls_org(org_b):
        ajeno = _caso(org_b)
    orden = _crear(org_a, str(ajeno.pk))
    orden.refresh_from_db()
    assert orden.caso_id is None
    # El texto se conserva tal cual: lo que no se hace es UNIR.
    assert orden.origen_ref == str(ajeno.pk)


def test_b2_aunque_la_rls_no_lo_tape_como_en_produccion(org_a, org_b):
    """Produccion conecta con un rol que SALTEA la RLS (DESPLIEGUE.md): ahi el
    unico filtro de empresa es el del codigo. Se reproduce creando la orden de
    A con la sesion parada en B, donde el caso de B SI es visible."""
    with rls_org(org_b):
        ajeno = _caso(org_b)
        orden = _crear(org_a, str(ajeno.pk))
        orden.refresh_from_db()
    assert orden.caso_id is None


@pytest.mark.parametrize("ref,tipo", [("caso-1", "case"), ("", "case"),
                                      (None, "case")])
def test_c_lo_que_no_es_un_caso_no_une(org_a, ref, tipo):
    orden = _crear(org_a, ref or "", tipo)
    orden.refresh_from_db()
    assert orden.caso_id is None


def test_c2_un_origen_manual_con_id_de_caso_no_une(org_a):
    caso = _caso(org_a)
    orden = D.crear_orden(org=org_a, profile=None, version=_version(org_a),
                          cliente={"nombre": "C"}, origen_sistema="manual",
                          origen_tipo="", origen_ref=str(caso.pk))
    orden.refresh_from_db()
    assert orden.caso_id is None


def _orden_vieja(org, ref):
    """Una orden como estaban antes de 0049: con el texto y sin el FK."""
    return OrdenTrabajo.objects.create(
        org=org, numero=next(_n), tipo_trabajo_version=_version(org),
        origen_sistema="crm", origen_tipo="case", origen_ref=ref,
        cliente_nombre="X", cliente_direccion="Y")


def test_d_el_relleno_une_las_suyas_y_no_las_ajenas_sin_contexto(org_a, org_b):
    rellenar = importlib.import_module(
        "campo.migrations.0049_orden_unida_al_caso").rellenar
    caso_a = _caso(org_a)
    with rls_org(org_b):
        caso_b = _caso(org_b)
        propia_b = _orden_vieja(org_b, str(caso_b.pk))
    propia_a = _orden_vieja(org_a, str(caso_a.pk))
    cruzada = _orden_vieja(org_a, str(caso_b.pk))      # texto de otra empresa
    basura = _orden_vieja(org_a, "no-es-un-id")

    #  Sin contexto RLS, como corre `migrate`: si el relleno no fijara el de
    #  cada empresa, bajo un rol que RLS ata no veria ningun caso.
    clear_rls_context()
    rellenar(django_apps, SimpleNamespace(connection=connection))
    set_rls_context(org_a)

    unidas = dict(OrdenTrabajo.objects.filter(
        pk__in=[propia_a.pk, propia_b.pk, cruzada.pk, basura.pk]
    ).values_list("pk", "caso_id"))
    assert unidas[propia_a.pk] == caso_a.pk
    assert unidas[propia_b.pk] == caso_b.pk
    assert unidas[cruzada.pk] is None
    assert unidas[basura.pk] is None


def test_e_borrar_el_ticket_no_borra_la_orden(org_a):
    caso = _caso(org_a)
    orden = _crear(org_a, str(caso.pk))
    caso.delete()
    orden.refresh_from_db()
    assert orden.caso_id is None
