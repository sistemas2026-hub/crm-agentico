# -*- coding: utf-8 -*-
"""
================================================================================
 EL REPARTO SE CORRIGE  --  23/10/2026
================================================================================

Fase 2.2 de SPEC/objetivos/supervisor-arma-la-jornada.md. Lo que el boton
Publicar hace distinto desde hoy, cada punto con su prueba:

  P  la prioridad: vencidas primero; entre las que no vencieron, alta, media
     y baja; dentro de cada una, la que vence antes (decision del usuario)
  F  la fecha: lo programado para un dia posterior no se reparte hoy, y el dia
     es el de la empresa, no el de UTC
  V  «empezada» es la vuelta real (`vueltas_empezadas`), la misma regla que
     `clasificar_ruta`; una devuelta a correccion vuelve a repartirse
  U  publicar relee bajo bloqueo: lo que se marco en camino, se cancelo o se
     asigno a mano despues de mirar no se toca; con la misma gente no se
     reasigna; lo que cambia de manos sube la revision
  A  lo que encontro la auditoria de la 2.2: el bloqueo tiene efecto con dos
     transacciones de verdad; la asignacion a mano de OTRA orden no frena esta;
     cambiar el lider no es «sin cambio»; una empezada que volvio de un
     bloqueo se nombra; la fecha se relee al publicar

    pytest campo/tests/test_el_reparto_se_corrige.py
================================================================================
"""

import datetime as dt
import zoneinfo

import pytest

from campo import reparto as R
from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services.transiciones import ejecutar_accion_operativa
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
REPARTO = "/api/campo/cuadrillas/reparto/"
BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


def plazo_falso(minutos_por_numero):
    """Un `plazo_de` que lee el riesgo de un dict por numero de orden."""
    def _plazo(orden, ahora=None, **kw):
        m = minutos_por_numero.get(orden.numero)
        if m is None:
            return {"minutos_restantes": None, "minutos_atraso": None}
        if m < 0:
            return {"minutos_restantes": None, "minutos_atraso": -m}
        return {"minutos_restantes": m, "minutos_atraso": None}
    return _plazo


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


def _orden(org, version, numero, *, estado=OrdenTrabajo.ASIGNADA,
           prioridad=OrdenTrabajo.PRIORIDAD_MEDIA, programada_para=None,
           iniciada_en=None):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=estado, zona="MARTHA GISELA", prioridad=prioridad,
        programada_para=programada_para, iniciada_en=iniciada_en,
    )


def _jornada(org, zonas, nombre="Cuadrilla 1", fecha=LUNES):
    c = Cuadrilla.objects.create(org=org, nombre=nombre)
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=fecha,
        labor=JornadaDeCuadrilla.INSTALACION,
    )
    j.zonas.set(zonas)
    return j


def _con_gente(org, jornada, profile):
    persona, _ = PersonaDeCampo.objects.get_or_create(
        org=org, profile=profile, defaults={"nombre": "Alguien"})
    IntegranteDeJornada.objects.create(
        org=org, jornada=jornada, persona=persona, rol="tecnico")
    return jornada


def _de(propuesta, nombre="Cuadrilla 1"):
    for a in propuesta["asignaciones"]:
        if a["cuadrilla"].nombre == nombre:
            return [o.numero for o in a["ordenes"]]
    return None


def _publicar(client, jornada, *ordenes):
    r = client.post(REPARTO, {"asignaciones": [
        {"jornada": str(jornada.id), "ordenes": [str(o.id) for o in ordenes]},
    ]}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def _reasignadas(orden):
    return EventoTrabajo.objects.filter(
        orden=orden, tipo="reasignada_por_reparto").count()


# ---------------------------------------------------------------------------
# P · la prioridad
# ---------------------------------------------------------------------------

def test_p_vencidas_primero_despues_alta_media_baja(org_a, version, norte):
    _jornada(org_a, [norte])
    A, M, B = (OrdenTrabajo.PRIORIDAD_ALTA, OrdenTrabajo.PRIORIDAD_MEDIA,
               OrdenTrabajo.PRIORIDAD_BAJA)
    _orden(org_a, version, 10, prioridad=M)     # media, media hora
    _orden(org_a, version, 20, prioridad=A)     # alta, diez horas
    _orden(org_a, version, 30, prioridad=B)     # baja, cinco minutos
    _orden(org_a, version, 40, prioridad=M)     # media, vencida hace 10
    _orden(org_a, version, 50, prioridad=A)     # alta, vencida hace 5
    _orden(org_a, version, 60, prioridad=A)     # alta, sin plazo

    p = R.proponer(org_a, LUNES, tope=10, plazo_de=plazo_falso({
        10: 30, 20: 600, 30: 5, 40: -10, 50: -5}))

    #  Lo vencido arriba y por atraso, sin importar la prioridad; despues la
    #  alta (con plazo antes que sin plazo), la media y la baja, aunque la
    #  baja venza en cinco minutos.
    assert _de(p) == [40, 50, 20, 60, 10, 30]


def test_p2_una_prioridad_desconocida_pesa_como_media(org_a, version, norte):
    _jornada(org_a, [norte])
    _orden(org_a, version, 10, prioridad=OrdenTrabajo.PRIORIDAD_BAJA)
    rara = _orden(org_a, version, 20)
    OrdenTrabajo.objects.filter(pk=rara.pk).update(prioridad="urgente")
    _orden(org_a, version, 30, prioridad=OrdenTrabajo.PRIORIDAD_ALTA)

    p = R.proponer(org_a, LUNES, tope=10, plazo_de=plazo_falso({}))
    assert _de(p) == [30, 20, 10]


# ---------------------------------------------------------------------------
# F · la fecha programada
# ---------------------------------------------------------------------------

def test_f_lo_de_otro_dia_no_se_reparte_hoy(org_a, version, norte):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    _jornada(org_a, [norte])
    manana = _orden(org_a, version, 10, programada_para=dt.datetime(
        2026, 10, 6, 15, 0, tzinfo=BOGOTA))
    #  Las 10 de la noche del lunes en Bogota son las 3 de la mañana del
    #  martes en UTC: con el dia de UTC se iria a «otro dia».
    _orden(org_a, version, 20, programada_para=dt.datetime(
        2026, 10, 5, 22, 0, tzinfo=BOGOTA))
    _orden(org_a, version, 30, programada_para=dt.datetime(
        2026, 10, 4, 9, 0, tzinfo=BOGOTA))       # ayer: nadie la hizo
    _orden(org_a, version, 40)                    # sin programar

    p = R.proponer(org_a, LUNES, tope=10, plazo_de=plazo_falso({}))

    assert _de(p) == [20, 30, 40]
    assert p["otro_dia"] == [manana]


def test_f2_la_pantalla_las_nombra(admin_client, org_a, version, norte):
    _jornada(org_a, [norte])
    _orden(org_a, version, 10, programada_para=dt.datetime(
        2026, 10, 8, 15, 0, tzinfo=dt.timezone.utc))

    r = admin_client.get(REPARTO, {"fecha": LUNES.isoformat()})

    assert r.status_code == 200
    assert [o["numero"] for o in r.json()["otro_dia"]] == [10]
    assert r.json()["asignaciones"][0]["ordenes"] == []


# ---------------------------------------------------------------------------
# V · la vuelta empezada
# ---------------------------------------------------------------------------

def _evento(org, orden, tipo, cuando, datos=None):
    e = EventoTrabajo.objects.create(org=org, orden=orden, tipo=tipo,
                                     datos=datos or {})
    EventoTrabajo.objects.filter(pk=e.pk).update(created_at=cuando)


def _casos_de_vuelta(org, version):
    t0 = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)
    hora = dt.timedelta(hours=1)
    nueva = _orden(org, version, 1)
    #  Volvio de un bloqueo a asignada: ya habia salido.
    desde_bloqueo = _orden(org, version, 2, iniciada_en=t0)
    #  Devuelta a correccion: la vuelta anterior empezo, esta no.
    devuelta = _orden(org, version, 3, estado=OrdenTrabajo.CORRECCION_REQUERIDA,
                      iniciada_en=t0)
    _evento(org, devuelta, "marcar_en_camino", t0, {"nuevo_estado": "en_camino"})
    _evento(org, devuelta, "reapertura_correccion", t0 + hora)
    #  Devuelta y vuelta a salir: esta vuelta SI empezo.
    devuelta_y_salio = _orden(org, version, 4,
                              estado=OrdenTrabajo.CORRECCION_REQUERIDA,
                              iniciada_en=t0)
    _evento(org, devuelta_y_salio, "reapertura_correccion", t0 + hora)
    _evento(org, devuelta_y_salio, "marcar_en_camino", t0 + 2 * hora,
            {"nuevo_estado": "en_camino"})
    #  Dos devoluciones: el inicio entre las dos no cuenta para la ultima.
    dos_veces = _orden(org, version, 5, estado=OrdenTrabajo.CORRECCION_REQUERIDA,
                       iniciada_en=t0)
    _evento(org, dos_veces, "reapertura_correccion", t0 + hora)
    _evento(org, dos_veces, "marcar_llegada", t0 + 2 * hora,
            {"nuevo_estado": "en_sitio"})
    _evento(org, dos_veces, "reapertura_correccion", t0 + 3 * hora)
    return [nueva, desde_bloqueo, devuelta, devuelta_y_salio, dos_veces]


def test_v_la_misma_regla_que_clasificar_ruta(org_a, version):
    from operaciones.programacion import RUTA_CONTINGENCIA, clasificar_ruta

    ordenes = _casos_de_vuelta(org_a, version)
    empezadas = R.vueltas_empezadas(org_a, [o.id for o in ordenes])

    assert {o.numero for o in ordenes if o.id in empezadas} == {2, 4}
    for o in ordenes:
        assert (o.id in empezadas) == (clasificar_ruta(o) == RUTA_CONTINGENCIA), o.numero


def test_v2_otra_empresa_no(org_a, org_b, version):
    ordenes = _casos_de_vuelta(org_a, version)
    assert R.vueltas_empezadas(org_b, [o.id for o in ordenes]) == set()


def test_v3_la_devuelta_vuelve_al_reparto_y_la_que_salio_no(
        org_a, version, norte):
    _jornada(org_a, [norte])
    _casos_de_vuelta(org_a, version)

    p = R.proponer(org_a, LUNES, tope=10, plazo_de=plazo_falso({}))

    #  1 nueva, 3 devuelta, 5 devuelta dos veces: esperan a alguien. 2 y 4 ya
    #  salieron en esta vuelta.
    assert _de(p) == [1, 3, 5]


# ---------------------------------------------------------------------------
# U · publicar relee lo que cambio desde que se miro
# ---------------------------------------------------------------------------

def test_u_la_que_se_marco_en_camino_no_cambia_de_manos(
        admin_client, org_a, version, norte, admin_profile, user_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    #  Entre mirar y publicar, el tecnico sale para alla.
    ejecutar_accion_operativa(o, "marcar_en_camino", profile=user_profile)

    r = _publicar(admin_client, j, o)

    assert (r["publicadas"], r["ya_tenian"]) == (0, [10])
    assert [a.profile_id for a in o.asignaciones.all()] == [user_profile.id]
    assert _reasignadas(o) == 0


def test_u2_la_que_volvio_de_un_bloqueo_tampoco(
        admin_client, org_a, version, norte, admin_profile, user_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10, iniciada_en=dt.datetime(
        2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc))
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)

    r = _publicar(admin_client, j, o)

    assert (r["publicadas"], r["ya_tenian"]) == (0, [10])
    assert [a.profile_id for a in o.asignaciones.all()] == [user_profile.id]


def test_u3_la_que_se_cancelo_no_recibe_a_nadie(
        admin_client, org_a, version, norte, admin_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    ejecutar_accion_operativa(o, "cancelar", profile=admin_profile)

    r = _publicar(admin_client, j, o)

    assert (r["publicadas"], r["ya_no_esperan"]) == (0, [10])
    assert o.asignaciones.count() == 0


def test_u4_la_que_se_asigno_a_mano_despues_de_mirar_gana(
        admin_client, org_a, version, norte, admin_profile, user_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    EventoTrabajo.objects.create(org=org_a, orden=o, tipo="asignacion")

    r = _publicar(admin_client, j, o)

    assert (r["publicadas"], r["a_mano"]) == (0, [10])
    assert [a.profile_id for a in o.asignaciones.all()] == [user_profile.id]
    assert _reasignadas(o) == 0


def test_u5_con_la_misma_gente_no_se_reasigna(
        admin_client, org_a, version, norte, admin_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)

    primera = _publicar(admin_client, j, o)
    o.refresh_from_db()
    revision = o.revision
    segunda = _publicar(admin_client, j, o)
    o.refresh_from_db()

    assert primera["publicadas"] == 1
    assert (segunda["publicadas"], segunda["sin_cambio"]) == (0, [10])
    assert o.revision == revision
    assert _reasignadas(o) == 0
    assert o.asignaciones.count() == 1


def test_u6_lo_que_cambia_de_manos_sube_la_revision(
        admin_client, org_a, version, norte, admin_profile, user_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    nueva = _orden(org_a, version, 10)
    movida = _orden(org_a, version, 20)
    AsignacionTrabajo.objects.create(orden=movida, profile=user_profile,
                                     rol="tecnico", es_principal=True)

    r = _publicar(admin_client, j, nueva, movida)

    assert (r["publicadas"], r["reasignadas"]) == (2, [20])
    for o in (nueva, movida):
        antes = o.revision
        o.refresh_from_db()
        assert o.revision == antes + 1, o.numero
    assert [a.profile_id for a in movida.asignaciones.all()] == [admin_profile.id]


def test_u7_la_devuelta_a_correccion_si_se_publica(
        admin_client, org_a, version, norte, admin_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    devuelta = _casos_de_vuelta(org_a, version)[2]

    r = _publicar(admin_client, j, devuelta)

    assert r["publicadas"] == 1
    assert [a.profile_id for a in devuelta.asignaciones.all()] == [admin_profile.id]


# ---------------------------------------------------------------------------
# A · lo que encontro la auditoria de la 2.2
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_a_el_bloqueo_tiene_efecto_con_dos_transacciones(
        org_a, version, norte, admin_profile, user_profile):
    """El tecnico marca en camino y todavia no confirmo cuando se publica.

    Las pruebas U lo simulan en secuencia, y eso solo prueba que se relee la
    fila. Esta prueba el BLOQUEO: sin `select_for_update`, publicar lee la
    fila vieja (asignada), la mueve, y el tecnico queda en camino hacia una
    orden que ya es de otra cuadrilla.
    """
    import threading
    import time

    from django.db import connection, transaction

    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    listo, errores = threading.Event(), []

    def tecnico():
        try:
            with transaction.atomic():
                fresca = OrdenTrabajo.objects.get(pk=o.pk)
                ejecutar_accion_operativa(fresca, "marcar_en_camino",
                                          profile=user_profile)
                listo.set()
                time.sleep(2)
        except Exception as e:                                   # noqa: BLE001
            errores.append(repr(e))
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=tecnico)
    hilo.start()
    assert listo.wait(15)
    r = R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}])
    hilo.join()

    assert not errores
    assert (r["publicadas"], r["ya_tenian"]) == (0, [10])
    assert [a.profile_id for a in o.asignaciones.all()] == [user_profile.id]


def test_a2_la_asignacion_a_mano_de_otra_orden_no_frena_esta(
        org_a, version, norte, admin_profile, user_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    ajena = _orden(org_a, version, 1)
    AsignacionTrabajo.objects.create(orden=ajena, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    EventoTrabajo.objects.create(org=org_a, orden=ajena, tipo="asignacion")
    libre = _orden(org_a, version, 2)

    r = R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(libre.id)]}])

    assert (r["publicadas"], r["a_mano"]) == (1, [])


def test_a3_misma_gente_con_otro_lider_si_se_reasigna(
        org_a, version, norte, admin_profile, user_profile):
    from campo.cuadrillas import destinatarios

    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    _con_gente(org_a, j, user_profile)
    j.lider = user_profile
    j.save(update_fields=["lider"])
    assert {(q["profile"].id, q["es_principal"])
            for q in destinatarios(j)["reciben"]} == {
        (user_profile.id, True), (admin_profile.id, False)}
    o = _orden(org_a, version, 10)
    #  La misma gente, con el principal en la otra persona.
    AsignacionTrabajo.objects.create(orden=o, profile=admin_profile,
                                     rol="tecnico", es_principal=True)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=False)

    r = R.publicar(org_a, [{"jornada": str(j.id), "ordenes": [str(o.id)]}])

    assert (r["publicadas"], r["sin_cambio"], r["reasignadas"]) == (1, [], [10])
    assert {a.profile_id for a in o.asignaciones.filter(es_principal=True)} == {
        user_profile.id}


def test_a4_la_empezada_que_volvio_de_un_bloqueo_se_nombra(
        admin_client, org_a, version, norte, admin_profile, user_profile):
    """Por el camino real: en camino, bloqueo, se destraba a «asignada»."""
    from campo.services import bloqueos

    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    ejecutar_accion_operativa(o, "marcar_en_camino", profile=user_profile)
    b, _, _ = bloqueos.bloquear(o, profile=user_profile, respuestas={
        "motivo": "cliente ausente", "necesita_de_noc": "reagendar"})
    o.refresh_from_db()
    bloqueos.resolver(b, profile=admin_profile, que_se_hizo="se reagenda",
                      volver_a=OrdenTrabajo.ASIGNADA)
    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.ASIGNADA

    p = R.proponer(org_a, LUNES, tope=10, plazo_de=plazo_falso({}))
    assert p["empezadas"] == [o]
    assert _de(p) == []
    pantalla = admin_client.get(REPARTO, {"fecha": LUNES.isoformat()}).json()
    assert [x["numero"] for x in pantalla["empezadas"]] == [10]

    r = _publicar(admin_client, j, o)
    assert (r["publicadas"], r["ya_tenian"]) == (0, [10])


def test_a5_la_que_programaron_para_otro_dia_despues_de_mirar_no_se_asigna(
        admin_client, org_a, version, norte, admin_profile):
    j = _con_gente(org_a, _jornada(org_a, [norte]), admin_profile)
    o = _orden(org_a, version, 10)
    #  Se miro el lunes; antes de publicar, alguien la paso al jueves.
    OrdenTrabajo.objects.filter(pk=o.pk).update(programada_para=dt.datetime(
        2026, 10, 8, 15, 0, tzinfo=dt.timezone.utc))

    r = _publicar(admin_client, j, o)

    assert (r["publicadas"], r["otro_dia"]) == (0, [10])
    assert o.asignaciones.count() == 0
