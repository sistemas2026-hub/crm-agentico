# -*- coding: utf-8 -*-
"""
================================================================================
 MOVER UNA ORDEN DE UN TECNICO A OTRO  --  14/11/2026
================================================================================

El control de Programacion («Mover a otro tecnico») necesitaba un camino que
de verdad le QUITE la orden al anterior. `asignar()` no sirve: baja al
anterior de `es_principal` y le deja la fila en `asignaciones`
(`campo/services/despacho.py:217`), y toda la autorizacion intra-tenant de
campo mide pertenencia a `asignaciones`, NUNCA `es_principal`:

    campo/views.py:88                `asignaciones.filter(profile=...).exists()`
    campo/services/transiciones.py:140   la misma consulta, bajo lock

Medido por el auditor de frontera el 14/11/2026 contra Postgres real: despues
de mover la orden a B, el tecnico A la marco en camino, en sitio y la
COMPLETO. La bitacora quedo con `trabajo_completado_campo` a nombre de A
sobre una orden cuyo principal es B.

QUE SE AFIRMA ACA, Y POR QUE ASI
--------------------------------
El punto A no afirma que la fila desaparecio: afirma que el anterior YA NO
PUEDE, por HTTP, con su propia sesion. Una prueba que mire `asignaciones`
sobrevive a que manana la autorizacion pase a mirar otra cosa; el 404 no.

    pytest campo/tests/test_mover_la_orden.py
================================================================================
"""

import datetime as dt

import pytest

from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services.despacho import ErrorDespacho, mover_la_orden
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    return z


@pytest.fixture
def destino(org_a, django_user_model):
    """Una tercera persona: a ella se mueve la orden."""
    from common.models import Profile

    u = django_user_model.objects.create_user(
        email="destino@ejemplo.test", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    #  `activa` nace en True, pero se deja explicito: la guarda B5 lo apaga
    #  y sin esta linea no se veria contra que esta midiendo.
    PersonaDeCampo.objects.create(org=org_a, profile=p, nombre="Nicolas Mora",
                                  activa=True)
    return p


def _orden(org, version, numero=901, *, estado=OrdenTrabajo.ASIGNADA):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=estado, zona="MARTHA GISELA",
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA,
    )


def _de(orden, profile, *, principal=True, rol="tecnico"):
    AsignacionTrabajo.objects.create(orden=orden, profile=profile,
                                     rol=rol, es_principal=principal)
    return orden


def _jornada(org, zonas, profile, nombre="Cuadrilla #1"):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=LUNES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set(zonas)
    persona, _ = PersonaDeCampo.objects.get_or_create(
        org=org, profile=profile, defaults={"nombre": "Alguien"})
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona,
                                       rol="tecnico")
    return j


# ---------------------------------------------------------------------------
# A · EL HUECO QUE ESTO CIERRA: el anterior deja de poder
# ---------------------------------------------------------------------------

def test_a_el_tecnico_anterior_YA_NO_PUEDE_tocar_la_orden(
        org_a, version, user_profile, destino, user_client, admin_profile):
    o = _de(_orden(org_a, version), user_profile)
    url = f"/api/campo/trabajos/{o.id}/acciones/"

    #  Antes de mover: puede. Si esto no pasara, el 404 de abajo no
    #  significaria nada -- podria estar fallando por cualquier otra causa.
    antes = user_client.post(url, {"accion": "marcar_en_camino"}, format="json")
    assert antes.status_code == 200, antes.content

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo")

    despues = user_client.post(url, {"accion": "marcar_llegada"}, format="json")
    assert despues.status_code == 404, despues.content


def test_a2_y_el_nuevo_queda_como_responsable(
        org_a, version, user_profile, destino, admin_profile):
    o = _de(_orden(org_a, version), user_profile)

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo")

    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id
    assert not o.asignaciones.filter(profile=user_profile).exists()


def test_a3_queda_escrito_quien_la_tenia_y_por_que(
        org_a, version, user_profile, destino, admin_profile):
    o = _de(_orden(org_a, version), user_profile)

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo a media jornada")

    #  El motivo es lo unico que despues explica por que un trabajo cambio de
    #  manos. Sin el, la bitacora dice QUE paso y no POR QUE.
    tipos = set(EventoTrabajo.objects.filter(orden=o).values_list("tipo", flat=True))
    assert "reasignacion" in tipos
    ev = EventoTrabajo.objects.get(orden=o, tipo="reasignacion")
    assert ev.datos["anterior"] == str(user_profile.id)
    assert ev.datos["nuevo"] == str(destino.id)
    assert ev.datos["motivo"] == "Se enfermo a media jornada"


# ---------------------------------------------------------------------------
# B · lo que NO se mueve
# ---------------------------------------------------------------------------

def test_b_una_orden_ya_completada_en_campo_no_se_mueve(
        org_a, version, user_profile, destino, admin_profile):
    """El trabajo YA lo hizo alguien. Moverla se lo atribuye a otro: la
    revision del cierre, la devolucion al ticket y la marca de agua de las
    fotos nombran al principal (`campo/marca_de_agua.py:256`,
    `campo/devolver_al_ticket.py:94`)."""
    o = _de(_orden(org_a, version, estado=OrdenTrabajo.COMPLETADA_CAMPO),
            user_profile)

    with pytest.raises(ErrorDespacho):
        mover_la_orden(o, destino, admin_profile, motivo="x")

    o.refresh_from_db()
    assert o.tecnico_principal.id == user_profile.id


def test_b2_pero_una_EN_CAMINO_si_se_mueve(
        org_a, version, user_profile, destino, admin_profile):
    """Es el caso que motivo el control: el tecnico se enfermo yendo."""
    o = _de(_orden(org_a, version, estado=OrdenTrabajo.EN_CAMINO), user_profile)

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo")

    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id


def test_b3_una_cerrada_tampoco(
        org_a, version, user_profile, destino, admin_profile):
    o = _de(_orden(org_a, version, estado=OrdenTrabajo.CERRADA), user_profile)

    with pytest.raises(ErrorDespacho):
        mover_la_orden(o, destino, admin_profile, motivo="x")


def test_b4_a_alguien_que_no_es_persona_de_campo_no_se_mueve(
        org_a, version, user_profile, admin_profile, django_user_model):
    """Medido el 14/11/2026: el endpoint de asignar aceptaba un perfil de
    bodega e inactivo con 200, y la orden quedaba con un responsable que no la
    va a ver nunca. La pantalla solo ofrece a quienes salen ese dia, pero una
    lista en el navegador no es una garantia (CLAUDE.md §4)."""
    from common.models import Profile

    u = django_user_model.objects.create_user(
        email="bodega@ejemplo.test", password="x")
    nadie = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    o = _de(_orden(org_a, version), user_profile)

    with pytest.raises(ErrorDespacho):
        mover_la_orden(o, nadie, admin_profile, motivo="x")

    o.refresh_from_db()
    assert o.tecnico_principal.id == user_profile.id


def test_b5_a_alguien_dado_de_baja_tampoco(
        org_a, version, user_profile, destino, admin_profile):
    PersonaDeCampo.objects.filter(org=org_a, profile=destino).update(activa=False)
    o = _de(_orden(org_a, version), user_profile)

    with pytest.raises(ErrorDespacho):
        mover_la_orden(o, destino, admin_profile, motivo="x")


# ---------------------------------------------------------------------------
# C · mover a quien ya la tiene
# ---------------------------------------------------------------------------

def test_c_moverla_a_quien_ya_la_tiene_no_hace_nada(
        org_a, version, user_profile, admin_profile):
    """El doble clic, y dos personas moviendola al mismo destino desde dos
    pantallas. No deja evento, porque no paso nada."""
    o = _de(_orden(org_a, version), user_profile)

    r = mover_la_orden(o, user_profile, admin_profile, motivo="x")

    assert r["movida"] is False
    assert not EventoTrabajo.objects.filter(orden=o, tipo="reasignacion").exists()
    o.refresh_from_db()
    assert o.asignaciones.filter(profile=user_profile).count() == 1


# ---------------------------------------------------------------------------
# D · la cuadrilla
# ---------------------------------------------------------------------------

def test_d_los_ayudantes_se_quedan(
        org_a, version, user_profile, destino, admin_profile, django_user_model):
    """Se mueve el RESPONSABLE, no la cuadrilla entera: sacar al ayudante
    tambien seria una decision que nadie pidio."""
    from common.models import Profile

    u = django_user_model.objects.create_user(
        email="ayudante@ejemplo.test", password="x")
    ayudante = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    o = _de(_orden(org_a, version), user_profile)
    _de(o, ayudante, principal=False, rol="ayudante")

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo")

    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id
    assert o.asignaciones.filter(profile=ayudante).exists()
    assert not o.asignaciones.filter(profile=user_profile).exists()


def test_d2_si_el_destino_ya_era_ayudante_sube_y_el_otro_sale(
        org_a, version, user_profile, destino, admin_profile):
    o = _de(_orden(org_a, version), user_profile)
    _de(o, destino, principal=False, rol="ayudante")

    mover_la_orden(o, destino, admin_profile, motivo="Se enfermo")

    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id
    assert not o.asignaciones.filter(profile=user_profile).exists()
    assert o.asignaciones.count() == 1


def test_d3_una_orden_sin_nadie_tambien_se_puede_asignar(
        org_a, version, destino, admin_profile):
    o = _orden(org_a, version)

    r = mover_la_orden(o, destino, admin_profile, motivo="La tomo Nicolas")

    assert r["movida"] is True
    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id


# ---------------------------------------------------------------------------
# E · por HTTP, con sus permisos
# ---------------------------------------------------------------------------

def _url(o):
    return f"/api/campo/trabajos/{o.id}/mover/"


def test_e_quien_gestiona_la_mueve(
        org_a, version, user_profile, destino, admin_client):
    o = _de(_orden(org_a, version), user_profile)

    r = admin_client.post(_url(o), {"profile_id": str(destino.id),
                                    "motivo": "Se enfermo"}, format="json")

    assert r.status_code == 200, r.content
    o.refresh_from_db()
    assert o.tecnico_principal.id == destino.id


def test_e2_quien_no_gestiona_no_la_mueve(
        org_a, version, user_profile, destino, user_client):
    o = _de(_orden(org_a, version), user_profile)

    r = user_client.post(_url(o), {"profile_id": str(destino.id),
                                   "motivo": "x"}, format="json")

    assert r.status_code in (403, 404), r.content
    o.refresh_from_db()
    assert o.tecnico_principal.id == user_profile.id


def test_e3_una_orden_de_OTRA_empresa_no_se_toca(
        org_b, version, destino, admin_client, org_a):
    """La orden es de org_b; quien pide es de org_a."""
    wt = WorkType.objects.create(org=org_b, codigo="ftth", nombre="FTTH",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    ajena = OrdenTrabajo.objects.create(
        org=org_b, numero=902, tipo_trabajo_version=v,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona="X",
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA)

    r = admin_client.post(_url(ajena), {"profile_id": str(destino.id),
                                        "motivo": "x"}, format="json")

    assert r.status_code == 404, r.content


def test_e4_sin_motivo_no_se_mueve(
        org_a, version, user_profile, destino, admin_client):
    o = _de(_orden(org_a, version), user_profile)

    r = admin_client.post(_url(o), {"profile_id": str(destino.id),
                                    "motivo": "  "}, format="json")

    assert r.status_code == 400, r.content
    o.refresh_from_db()
    assert o.tecnico_principal.id == user_profile.id


def test_e5_la_respuesta_dice_si_le_llego_el_aviso(
        org_a, version, norte, user_profile, destino, admin_client):
    """`avisar_asignacion` sale solo si la persona es NUEVA en la orden
    (`despacho.py:229`, decision propia con su prueba en
    `test_aviso_al_asignar.py`). La pantalla no puede afirmar «le llega el
    aviso» sin saberlo: lo dice la respuesta."""
    _jornada(org_a, [norte], destino)
    o = _de(_orden(org_a, version), user_profile)
    _de(o, destino, principal=False, rol="ayudante")

    r = admin_client.post(_url(o), {"profile_id": str(destino.id),
                                    "motivo": "x"}, format="json")

    assert r.status_code == 200, r.content
    #  Ya estaba en la orden: no es una visita nueva para el, no hay aviso.
    assert r.json()["aviso"] is False


def test_e6_a_una_persona_de_OTRA_empresa_no_se_mueve(
        org_a, version, user_profile, admin_client, profile_b):
    """El aislamiento por empresa, medido por su EFECTO y no por la linea que
    lo produce: hoy lo corta `_profile_o_404` antes que nada, y manana podria
    cortarlo `_misma_empresa`. Lo que no puede cambiar es que la orden siga
    siendo de quien la tenia."""
    o = _de(_orden(org_a, version), user_profile)

    r = admin_client.post(_url(o), {"profile_id": str(profile_b.id),
                                    "motivo": "x"}, format="json")

    assert r.status_code == 404, r.content
    o.refresh_from_db()
    assert o.tecnico_principal.id == user_profile.id
