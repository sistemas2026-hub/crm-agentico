# -*- coding: utf-8 -*-
"""
================================================================================
 LA ACCION DEL TECNICO RELEE LA ORDEN BAJO BLOQUEO  --  23/10/2026
================================================================================

Lo heredado de la fase 2.2 en la fila 3.1 de
SPEC/objetivos/supervisor-arma-la-jornada.md, cada punto con su prueba:

  B  la accion del tecnico (`AccionesTrabajoView` -> `ejecutar_accion_operativa`)
     relee la orden con `select_for_update` y la rechaza si quien la marca ya
     no esta asignado. Se prueba con DOS TRANSACCIONES DE VERDAD: publicar
     mueve la orden y todavia no confirmo cuando el tecnico marca en camino.
     Por HTTP la respuesta es 404, la que la app ya trata como «la orden no
     existe o fue reasignada» (terminal, sin reintento).
  E  la transicion se calcula sobre la fila releida, no sobre la que leyo la
     vista: un «en camino» viejo no hace retroceder una orden en sitio.
  G  la gestion sigue pudiendo actuar sobre una orden que no tiene asignada.
  P  `pendientes_de_ayer` mira la vuelta real (`reparto.vueltas_empezadas`),
     no el evento `trabajo_iniciado`, que ningun codigo de produccion escribe.

    pytest campo/tests/test_la_accion_relee_la_asignacion.py
================================================================================
"""

import datetime as dt

import pytest
from django.utils import timezone

from campo import pendientes_de_ayer
from campo import reparto as R
from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services.transiciones import (OrdenYaNoAsignadaError,
                                         TransicionInvalidaError,
                                         ejecutar_accion_operativa)
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)


def _acciones(orden):
    return f"/api/campo/trabajos/{orden.id}/acciones/"


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


def _orden(org, version, numero, *, estado=OrdenTrabajo.ASIGNADA, iniciada_en=None):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=estado, zona="MARTHA GISELA",
        prioridad=OrdenTrabajo.PRIORIDAD_MEDIA, iniciada_en=iniciada_en,
    )


def _de(orden, profile):
    AsignacionTrabajo.objects.create(orden=orden, profile=profile,
                                     rol="tecnico", es_principal=True)
    return orden


def _jornada_de(org, zonas, profile):
    c = Cuadrilla.objects.create(org=org, nombre="Otra cuadrilla")
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=c, fecha=LUNES, labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set(zonas)
    persona, _ = PersonaDeCampo.objects.get_or_create(
        org=org, profile=profile, defaults={"nombre": "Alguien"})
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    return j


def _publicar_sin_confirmar(org, jornada, orden, salida):
    """Publica dentro de una transaccion que tarda en confirmar.

    Devuelve (hilo, listo): `listo` se enciende cuando publicar ya bloqueo la
    orden y le cambio las manos, y la transaccion sigue abierta 2 s mas.
    """
    import threading
    import time

    from django.db import connection, transaction

    listo = threading.Event()

    def supervisor():
        from conftest import _apply_rls_context

        try:
            with transaction.atomic():
                #  El hilo abre su propia conexion: sin el contexto de la
                #  empresa, la notificacion que publicar escribe desde el
                #  27/10/2026 (aviso al telefono, en `common`, con RLS) se
                #  rechaza y la publicacion entera se deshace. En produccion
                #  lo fijan el middleware y el ciclo del Supervisor.
                _apply_rls_context(org.id)
                salida["publicar"] = R.publicar(
                    org, [{"jornada": str(jornada.id), "ordenes": [str(orden.id)]}])
                listo.set()
                time.sleep(2)
        except Exception as e:                                       # noqa: BLE001
            salida["error"] = repr(e)
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=supervisor)
    hilo.start()
    assert listo.wait(15)
    return hilo


def _sin_tocar(orden, profile_nuevo):
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.ASIGNADA
    assert orden.iniciada_en is None
    assert [a.profile_id for a in orden.asignaciones.all()] == [profile_nuevo.id]
    assert not EventoTrabajo.objects.filter(orden=orden, tipo__startswith="accion_").exists()


# ---------------------------------------------------------------------------
# B · la accion relee bajo bloqueo y vuelve a preguntar de quien es
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_b_dos_transacciones_publicar_mueve_la_orden_mientras_el_tecnico_la_marca(
        org_a, version, norte, admin_profile, user_profile):
    """El tecnico leyo su orden; publicar la mueve y todavia no confirmo.

    Sin el bloqueo, la accion lee la fila vieja (asignada a el), espera al
    guardar, y escribe «en camino» sobre una orden que ya es de otra
    cuadrilla. Con el bloqueo espera a que publicar confirme, relee, y no
    escribe nada.
    """
    o = _de(_orden(org_a, version, 10), user_profile)
    leida = OrdenTrabajo.objects.get(pk=o.pk)        # lo que leyo la vista
    j = _jornada_de(org_a, [norte], admin_profile)
    salida = {}

    hilo = _publicar_sin_confirmar(org_a, j, o, salida)
    with pytest.raises(OrdenYaNoAsignadaError):
        ejecutar_accion_operativa(leida, "marcar_en_camino", profile=user_profile,
                                  exigir_asignado=True)
    hilo.join()

    assert "error" not in salida, salida
    assert salida["publicar"]["publicadas"] == 1
    _sin_tocar(o, admin_profile)


@pytest.mark.django_db(transaction=True)
def test_b2_por_http_la_misma_carrera_da_404_y_no_escribe(
        org_a, version, norte, admin_profile, user_profile, user_client):
    """La misma carrera por la ruta real: la vista ve la orden asignada (la
    lectura de arriba no bloquea), la accion espera, relee y contesta 404 --
    lo que la app ya da por «reasignada», sin reintentar."""
    o = _de(_orden(org_a, version, 11), user_profile)
    j = _jornada_de(org_a, [norte], admin_profile)
    salida = {}

    hilo = _publicar_sin_confirmar(org_a, j, o, salida)
    r = user_client.post(_acciones(o), {"accion": "marcar_en_camino"}, format="json",
                         HTTP_IDEMPOTENCY_KEY="carrera-b2")
    hilo.join()

    assert "error" not in salida, salida
    assert r.status_code == 404, r.content
    assert r.json()["error"] == "ORDEN_REASIGNADA"
    _sin_tocar(o, admin_profile)
    #  El reintento con la misma clave contesta lo mismo: la app no lo va a
    #  reintentar, pero si lo hiciera no hay una segunda version de la verdad.
    r2 = user_client.post(_acciones(o), {"accion": "marcar_en_camino"}, format="json",
                          HTTP_IDEMPOTENCY_KEY="carrera-b2")
    assert r2.status_code == 404


def test_b3_el_tecnico_asignado_sigue_marcando_su_orden(org_a, version, user_profile, user_client):
    o = _de(_orden(org_a, version, 12), user_profile)

    r = user_client.post(_acciones(o), {"accion": "marcar_en_camino"}, format="json")

    assert r.status_code == 200, r.content
    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.EN_CAMINO and o.iniciada_en is not None


# ---------------------------------------------------------------------------
# E · la transicion se calcula sobre la fila releida
# ---------------------------------------------------------------------------

def test_e_un_en_camino_viejo_no_hace_retroceder_una_orden_en_sitio(org_a, version, user_profile):
    o = _de(_orden(org_a, version, 20), user_profile)
    vieja = OrdenTrabajo.objects.get(pk=o.pk)        # leida cuando estaba asignada
    ejecutar_accion_operativa(OrdenTrabajo.objects.get(pk=o.pk), "marcar_llegada",
                              profile=user_profile, exigir_asignado=True)

    with pytest.raises(TransicionInvalidaError):
        ejecutar_accion_operativa(vieja, "marcar_en_camino", profile=user_profile,
                                  exigir_asignado=True)

    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.EN_SITIO


def test_e2_el_objeto_que_se_paso_queda_como_la_fila(org_a, version, user_profile):
    """Quien pasa la orden la sigue usando: el objeto queda con el estado nuevo."""
    o = _de(_orden(org_a, version, 21), user_profile)
    revision = o.revision

    devuelta = ejecutar_accion_operativa(o, "marcar_en_camino", profile=user_profile)

    assert devuelta is o
    assert (o.estado_operativo, o.revision) == (OrdenTrabajo.EN_CAMINO, revision + 1)
    assert o.iniciada_en is not None


# ---------------------------------------------------------------------------
# G · la gestion actua sobre ordenes que no tiene asignadas
# ---------------------------------------------------------------------------

def test_g_la_gestion_marca_una_orden_que_no_tiene_asignada(
        org_a, version, user_profile, admin_client):
    o = _de(_orden(org_a, version, 30), user_profile)

    r = admin_client.post(_acciones(o), {"accion": "marcar_en_camino"}, format="json")

    assert r.status_code == 200, r.content
    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.EN_CAMINO


# ---------------------------------------------------------------------------
# P · pendientes_de_ayer mira la vuelta real
# ---------------------------------------------------------------------------

def _listadas(salida):
    return {f["numero"] for lista in salida.values() for f in lista}


def test_p_una_empezada_que_volvio_a_asignada_se_explica(org_a, version, user_profile):
    """Fue en camino, se bloqueo y la destrabaron a «asignada»: el reparto la
    deja quieta por empezada, y aca tiene que aparecer con su por que."""
    _de(_orden(org_a, version, 40,
               iniciada_en=timezone.now() - dt.timedelta(days=1)), user_profile)

    assert _listadas(pendientes_de_ayer.revisar(org_a)) == {40}


def test_p2_el_evento_trabajo_iniciado_no_cuenta(org_a, version, user_profile):
    """Nadie lo escribe en produccion; una orden que nadie toco no esta
    pendiente aunque una prueba vieja le fabrique el evento."""
    o = _de(_orden(org_a, version, 41), user_profile)
    EventoTrabajo.objects.create(org=org_a, orden=o, tipo="trabajo_iniciado")

    assert _listadas(pendientes_de_ayer.revisar(org_a)) == set()


def test_p3_una_devuelta_a_correccion_sin_volver_a_salir_no_esta_empezada(
        org_a, version, user_profile):
    """`iniciada_en` se escribe una sola vez: a secas, una devuelta a
    correccion contaria como empezada para siempre. La vuelta nueva empieza
    cuando el tecnico vuelve a salir."""
    from operaciones.programacion import EVENTO_REAPERTURA

    o = _de(_orden(org_a, version, 42, estado=OrdenTrabajo.CORRECCION_REQUERIDA,
                   iniciada_en=timezone.now() - dt.timedelta(days=3)), user_profile)
    EventoTrabajo.objects.create(org=org_a, orden=o, tipo=EVENTO_REAPERTURA)

    assert _listadas(pendientes_de_ayer.revisar(org_a)) == set()
