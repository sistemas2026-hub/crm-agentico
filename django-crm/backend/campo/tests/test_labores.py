# -*- coding: utf-8 -*-
"""
================================================================================
 LABORES PROPIAS POR EMPRESA  --  FASE 1: el catalogo, sin cambio de conducta
================================================================================

Ficha: SPEC/objetivos/labores-propias-por-empresa.md. Se afirma sobre el
EFECTO:

  A  la siembra deja las tres de siempre en TODA empresa, tambien en una sin
     configuracion de reparto ni plantillas (si no, toda validacion rechazaria
     y el ciclo de la madrugada fallaria); copia los nombres que la empresa ya
     habia puesto y los asuntos de sus plantillas
  B  sin filas, leer devuelve las de fabrica y NO escribe
  C  `labor_valida` es la unica validacion: lo que las vistas aceptan y
     rechazan sale de ahi -- una labor de la empresa pasa, una dada de baja o
     inventada no
  D  nada cambia de conducta: mismas tres, mismo orden, mismos nombres; el
     renombre del 20/10 sigue funcionando y ahora escribe `Labor.nombre`
  E  un asunto va en una sola labor: lo garantiza la base
  F  el informe es de solo lectura
  G  lo que encontro el auditor independiente (20/10/2026): los cuatro
     lugares que validaban sin prueba, el codigo con espacios, el admin, el
     renombre parcial y la tabla que todavia no existe

    pytest campo/tests/test_labores.py
================================================================================
"""

import importlib

import pytest
from django.apps import apps as registro
from django.core.management import call_command
from django.db import IntegrityError, transaction

from campo import labores as L
from campo.cuadrillas import ConfiguracionDeReparto, Cuadrilla
from campo.models import WorkType

pytestmark = pytest.mark.django_db

DE_FABRICA = [{"id": "instalacion", "texto": "Instalacion"},
              {"id": "correctivo", "texto": "Correctivo"},
              {"id": "trabajos", "texto": "Trabajos"}]
CONFIG = "/api/campo/cuadrillas/configuracion/"
TIPOS = "/api/campo/tipos-de-trabajo/"
LO_DE_SIEMPRE = {"activo": False, "hora_local": 3, "tope_por_cuadrilla": 8,
                 "copia_la_jornada": True}


def _sembrar():
    """La siembra de la migracion 0036, sobre los datos de la prueba."""
    m = importlib.import_module("campo.migrations.0036_labores_por_empresa")
    m.sembrar(registro, None)


def _tipo(org, codigo, labor="", asuntos=()):
    return WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor=labor, asuntos=list(asuntos))


# ---------------------------------------------------------------------------
# A · la siembra
# ---------------------------------------------------------------------------

def test_a_una_empresa_sin_configuracion_ni_plantillas_recibe_las_tres(org_a):
    assert not ConfiguracionDeReparto.objects.filter(org=org_a).exists()
    assert not WorkType.objects.filter(org=org_a).exists()

    _sembrar()

    filas = L.Labor.objects.filter(org=org_a)
    assert sorted(filas.values_list("codigo", flat=True)) == [
        "correctivo", "instalacion", "trabajos"]
    assert all(filas.values_list("de_fabrica", flat=True))
    assert L.labores_de(org_a) == DE_FABRICA


def test_a2_copia_los_nombres_que_la_empresa_ya_habia_puesto(org_a):
    ConfiguracionDeReparto.objects.create(
        org=org_a, nombres_de_labor={"correctivo": "Correctivos y traslados"})
    _sembrar()
    assert L.Labor.objects.get(org=org_a, codigo="correctivo").nombre == \
        "Correctivos y traslados"


def test_a3_los_asuntos_de_cada_labor_son_los_de_sus_plantillas(org_a):
    _tipo(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    _tipo(org_a, "tv", "correctivo", ["Punto De Tv Adicional"])
    #  Sin labor no aporta a ninguna (D7).
    _tipo(org_a, "suelta", "", ["Visita General"])
    _sembrar()

    asuntos = dict(L.AsuntoDeLabor.objects.filter(org=org_a)
                   .values_list("normalizado", "labor__codigo"))
    assert asuntos == {"cambio de domicilio": "correctivo",
                       "punto de tv adicional": "correctivo"}


def test_a4_es_idempotente(org_a):
    _tipo(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    _sembrar()
    _sembrar()
    assert L.Labor.objects.filter(org=org_a).count() == 3
    assert L.AsuntoDeLabor.objects.filter(org=org_a).count() == 1


# ---------------------------------------------------------------------------
# B · leer no escribe
# ---------------------------------------------------------------------------

def test_b_sin_filas_devuelve_las_de_fabrica_y_no_escribe(org_a):
    ConfiguracionDeReparto.objects.create(
        org=org_a, nombres_de_labor={"trabajos": "Retiros y varios"})
    lista = L.labores_de(org_a)
    assert [l["id"] for l in lista] == ["instalacion", "correctivo", "trabajos"]
    assert lista[2]["texto"] == "Retiros y varios"
    assert L.labor_valida(org_a, "correctivo")
    assert not L.Labor.objects.filter(org=org_a).exists()


# ---------------------------------------------------------------------------
# C · labor_valida es la unica validacion
# ---------------------------------------------------------------------------

def test_c_valida_las_de_la_empresa_y_rechaza_lo_demas(org_a):
    L.sembrar_de_fabrica(org_a)
    L.Labor.objects.create(org=org_a, codigo="traslados", nombre="Traslados")
    L.Labor.objects.create(org=org_a, codigo="vieja", nombre="Vieja", activa=False)

    assert L.labor_valida(org_a, "correctivo")
    assert L.labor_valida(org_a, "traslados")
    assert not L.labor_valida(org_a, "vieja")          # dada de baja
    assert not L.labor_valida(org_a, "inventada")      # no existe
    assert not L.labor_valida(org_a, "")               # vacio no es una labor


def test_c2_otra_empresa_no_presta_sus_labores(org_a, org_b):
    L.sembrar_de_fabrica(org_a)
    L.sembrar_de_fabrica(org_b)
    L.Labor.objects.create(org=org_b, codigo="traslados", nombre="Traslados")
    assert not L.labor_valida(org_a, "traslados")


def test_c3_la_vista_de_tipos_acepta_una_labor_de_la_empresa(admin_client, org_a):
    L.sembrar_de_fabrica(org_a)
    L.Labor.objects.create(org=org_a, codigo="traslados", nombre="Traslados")
    tipo = _tipo(org_a, "traslado")
    r = admin_client.patch(f"{TIPOS}{tipo.id}/", {"labor": "traslados"},
                           format="json")
    assert r.status_code == 200, r.content
    assert WorkType.objects.get(pk=tipo.pk).labor == "traslados"


@pytest.mark.parametrize("labor", ["inventada", "vieja"])
def test_c4_y_rechaza_una_inventada_o_dada_de_baja(admin_client, org_a, labor):
    L.sembrar_de_fabrica(org_a)
    L.Labor.objects.create(org=org_a, codigo="vieja", nombre="Vieja", activa=False)
    tipo = _tipo(org_a, "traslado", "correctivo")
    r = admin_client.patch(f"{TIPOS}{tipo.id}/", {"labor": labor}, format="json")
    assert r.status_code == 400, r.content
    assert WorkType.objects.get(pk=tipo.pk).labor == "correctivo"


def test_c5_la_tabla_de_grupos_tampoco_acepta_una_dada_de_baja(admin_client, org_a):
    L.sembrar_de_fabrica(org_a)
    L.Labor.objects.create(org=org_a, codigo="vieja", nombre="Vieja", activa=False)
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "labor_por_grupo": {
        "falla_de_servicio": "vieja"}}, format="json")
    assert r.status_code == 400, r.content


def test_c6_la_labor_habitual_de_una_cuadrilla_pasa_por_la_misma(
        admin_client, org_a):
    L.sembrar_de_fabrica(org_a)
    L.Labor.objects.create(org=org_a, codigo="traslados", nombre="Traslados")
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #9")
    ok = admin_client.patch(f"/api/campo/cuadrillas/{c.id}/",
                            {"labor_habitual": "traslados"}, format="json")
    mal = admin_client.patch(f"/api/campo/cuadrillas/{c.id}/",
                             {"labor_habitual": "inventada"}, format="json")
    assert ok.status_code == 200, ok.content
    assert mal.status_code == 400, mal.content
    assert Cuadrilla.objects.get(pk=c.pk).labor_habitual == "traslados"


# ---------------------------------------------------------------------------
# D · sin cambio de conducta
# ---------------------------------------------------------------------------

def test_d_sembradas_se_leen_igual_que_antes(org_a):
    antes = L.labores_de(org_a)
    _sembrar()
    assert L.labores_de(org_a) == antes == DE_FABRICA


def test_d2_el_renombre_del_20_10_escribe_labor_nombre(admin_client, org_a):
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": "Correctivos y traslados"}}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["nombres_de_labor"] == {"correctivo": "Correctivos y traslados"}
    #  Una sola fuente del nombre: la tabla. La columna vieja no se escribe.
    assert L.Labor.objects.get(org=org_a, codigo="correctivo").nombre == \
        "Correctivos y traslados"
    assert not (ConfiguracionDeReparto.objects.get(org=org_a)
                .nombres_de_labor or {})
    #  Y volver al de fabrica.
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": ""}}, format="json")
    assert r.json()["nombres_de_labor"] == {}


# ---------------------------------------------------------------------------
# E · un asunto, una labor
# ---------------------------------------------------------------------------

def test_e_un_asunto_no_puede_estar_en_dos_labores_de_la_empresa(org_a):
    L.sembrar_de_fabrica(org_a)
    correctivo = L.Labor.objects.get(org=org_a, codigo="correctivo")
    trabajos = L.Labor.objects.get(org=org_a, codigo="trabajos")
    L.AsuntoDeLabor.objects.create(org=org_a, labor=correctivo,
                                   asunto="Cambio De Domicilio")
    with pytest.raises(IntegrityError), transaction.atomic():
        #  Mismo asunto, otra forma de escribirlo: es el mismo.
        L.AsuntoDeLabor.objects.create(org=org_a, labor=trabajos,
                                       asunto="cambio de  domicílio")


# ---------------------------------------------------------------------------
# F · el informe no escribe
# ---------------------------------------------------------------------------

def test_f_el_informe_es_de_solo_lectura(org_a, capsys):
    _tipo(org_a, "traslado", "correctivo", ["Cambio De Domicilio"])
    _tipo(org_a, "suelta", "", ["Visita General"])
    call_command("informe_de_labores")
    salida = capsys.readouterr().out
    assert "plantillas SIN labor con asuntos: 1" in salida
    assert "TOTAL choques: 0" in salida
    assert not L.Labor.objects.filter(org=org_a).exists()


# ---------------------------------------------------------------------------
# G · lo que encontro el auditor independiente
# ---------------------------------------------------------------------------
#  Las pruebas de C cubrian dos de los seis lugares que validan. Una labor
#  creada por la empresa que uno de los otros cuatro rechazara seguiria en
#  verde: cada uno se prueba aca con una labor PROPIA.

JORNADA = "/api/campo/cuadrillas/jornada/"
PLANTILLAS = "/api/campo/plantillas/"
DEFINICION = {"campos": [{"titulo": "Que se hizo", "tipo": "texto"}],
              "evidencias": [{"titulo": "Trabajo terminado"}]}


def _propias(org):
    L.sembrar_de_fabrica(org)
    L.Labor.objects.create(org=org, codigo="traslados", nombre="Traslados")
    L.Labor.objects.create(org=org, codigo="vieja", nombre="Vieja", activa=False)


def test_g1_la_jornada_acepta_una_labor_propia_y_muestra_su_nombre(
        admin_client, org_a):
    _propias(org_a)
    L.renombrar_de_fabrica(org_a, "correctivo", "Correctivos y traslados")
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #9")
    ok = admin_client.post(JORNADA, {"cuadrilla": str(c.id), "fecha": "2026-10-21",
                                     "labor": "traslados", "integrantes": []},
                           format="json")
    mal = admin_client.post(JORNADA, {"cuadrilla": str(c.id), "fecha": "2026-10-22",
                                      "labor": "vieja", "integrantes": []},
                            format="json")
    assert ok.status_code in (200, 201), ok.content
    assert mal.status_code == 400, mal.content
    assert ok.json()["labor_nombre"] == "Traslados"

    #  El nombre que se ve es el de la EMPRESA, tambien en la lista: antes
    #  salia de la tupla fija y decia «Correctivo» aunque se hubiera cambiado.
    admin_client.post(JORNADA, {"cuadrilla": str(c.id), "fecha": "2026-10-22",
                                "labor": "correctivo", "integrantes": []},
                      format="json")
    lista = admin_client.get(JORNADA, {"fecha": "2026-10-22"}).json()["jornadas"]
    assert [j["labor_nombre"] for j in lista] == ["Correctivos y traslados"]


def test_g2_la_tabla_de_grupos_acepta_una_propia_y_el_reparto_la_usa(
        admin_client, org_a):
    _propias(org_a)
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "labor_por_grupo": {
        "falla_de_servicio": "traslados"}}, format="json")
    assert r.status_code == 200, r.content
    from campo.cuadrillas import labor_de_cada_grupo
    assert labor_de_cada_grupo(org_a)["falla_de_servicio"] == "traslados"

    #  Dada de baja despues de guardada: vuelve al de fabrica, no inclina
    #  jornadas hacia una labor que ya no sale.
    L.Labor.objects.filter(org=org_a, codigo="traslados").update(activa=False)
    assert labor_de_cada_grupo(org_a)["falla_de_servicio"] == \
        ConfiguracionDeReparto.LABOR_POR_GRUPO_DE_FABRICA["falla_de_servicio"]


def test_g3_la_plantilla_se_crea_y_publica_con_una_propia(admin_client, org_a):
    _propias(org_a)
    r = admin_client.post(PLANTILLAS, {"nombre": "Traslado", "labor": "traslados",
                                       "definicion": DEFINICION}, format="json")
    assert r.status_code == 201, r.content
    tipo_id = r.json()["id"]
    assert WorkType.objects.get(pk=tipo_id).labor == "traslados"

    mal = admin_client.post(f"{PLANTILLAS}{tipo_id}/publicar/",
                            {"definicion": DEFINICION, "labor": "vieja"},
                            format="json")
    assert mal.status_code == 400, mal.content
    assert WorkType.objects.get(pk=tipo_id).labor == "traslados"


@pytest.mark.parametrize("con_filas", [False, True], ids=["sin_filas", "sembrada"])
def test_g4_un_codigo_con_espacios_no_es_la_labor(org_a, con_filas):
    """Quien lo guarda tal cual (la tabla de grupos) dejaria ' correctivo '
    escrito, y el reparto compara exacto: no emparejaria nunca."""
    if con_filas:
        L.sembrar_de_fabrica(org_a)
    assert L.labor_valida(org_a, "correctivo")
    assert not L.labor_valida(org_a, " correctivo ")
    assert not L.labor_valida(org_a, "correctivo ")


def test_g5_y_la_tabla_de_grupos_lo_rechaza(admin_client, org_a):
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "labor_por_grupo": {
        "falla_de_servicio": " correctivo "}}, format="json")
    assert r.status_code == 400, r.content


def test_g6_el_admin_de_django_valida_la_labor(org_a):
    from campo.admin import WorkTypeAdminForm
    _propias(org_a)
    tipo = _tipo(org_a, "traslado", "correctivo")
    for labor, pasa in (("traslados", True), ("inventada", False),
                        ("vieja", False), ("", True)):
        form = WorkTypeAdminForm(instance=tipo, data={
            "org": org_a.pk, "codigo": tipo.codigo, "nombre": tipo.nombre,
            "labor": labor, "activo": True, "asuntos": "[]"})
        form.is_valid()
        assert ("labor" not in form.errors) is pasa, (labor, form.errors)


def test_g7_el_renombre_reemplaza_la_tabla_entera(admin_client, org_a):
    """Como antes de la Fase 1: el que no viene vuelve al de fabrica. Si no,
    la pantalla mandaria «sin cambio» y el nombre viejo seguiria."""
    admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": "Correctivos y traslados", "trabajos": "Retiros"}},
        format="json")
    r = admin_client.put(CONFIG, {**LO_DE_SIEMPRE, "nombres_de_labor": {
        "correctivo": "Correctivos y traslados"}}, format="json")
    assert r.json()["nombres_de_labor"] == {"correctivo": "Correctivos y traslados"}
    assert L.Labor.objects.get(org=org_a, codigo="trabajos").nombre == "Trabajos"

    #  Y sin la clave no se toca nada.
    r = admin_client.put(CONFIG, LO_DE_SIEMPRE, format="json")
    assert r.json()["nombres_de_labor"] == {"correctivo": "Correctivos y traslados"}


def test_g8_sin_la_tabla_lee_las_de_fabrica_y_la_transaccion_sigue(org_a):
    """El worker de Celery no espera a `migrate`: puede leer antes de que
    `campo_labor` exista. Tiene que caer a las de fabrica Y dejar usable la
    transaccion de quien llamo (si no, lo siguiente del armado revienta con
    «current transaction is aborted»)."""
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("ALTER TABLE campo_labor RENAME TO campo_labor_ausente")
    assert L.labores_de(org_a) == DE_FABRICA
    assert L.labor_valida(org_a, "correctivo")
    assert not L.labor_valida(org_a, "traslados")
    assert WorkType.objects.filter(org=org_a).count() == 0
