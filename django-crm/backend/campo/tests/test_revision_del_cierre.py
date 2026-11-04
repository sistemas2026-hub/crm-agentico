# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR REVISA EL CIERRE DEL TECNICO  --  30/10/2026
================================================================================
SPEC/objetivos/revision-del-cierre.md. Ver `campo/revision_del_cierre.py`.

  V1  todo bien: «Se puede cerrar», y cada punto dice por que.
  V2  un «no» manda: el tecnico dice que el servicio NO quedo, o la señal NO
      quedo en rango, o falta una foto (y la sugiere para devolver).
  V3  un «no se sabe» pide revisar: sin material ni confirmacion de que no uso.
  V4  el reporte de una vuelta YA DEVUELTA no cuenta.
  V5  lo que no aplica: una plantilla que no pregunta por el servicio, una
      orden sin medicion, una orden que no esta esperando validacion.
  V6  Programacion trae la revision en la orden terminada, y nada en las otras.
  V7  INDICA, NO DECIDE: revisar no aprueba, no cierra y no toca la orden.
  V8  la medicion de otra empresa no entra.

    pytest campo/tests/test_revision_del_cierre.py
================================================================================
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from campo import dia_publicado as D
from campo import revision_del_cierre as RC
from campo.cuadrillas import Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla, PersonaDeCampo
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from operaciones.models import PropuestaSupervisor
from operaciones.verificacion_de_arreglos import FUENTE

pytestmark = pytest.mark.django_db

PREGUNTAS = [{"id": "solucion", "tipo": "texto"}, {"id": "servicio_validado", "tipo": "booleano"}]


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


@pytest.fixture
def orden(org, user_profile):
    wt = WorkType.objects.create(org=org, codigo="sop", nombre="Soporte",
                                 labor=JornadaDeCuadrilla.CORRECTIVO)
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto de la ONT", "tipo": "foto", "obligatorio": True}]})
    o = OrdenTrabajo.objects.create(
        org=org, numero=3, tipo_trabajo_version=v, zona="X",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE, completada_campo_en=timezone.now())
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    return o


def _foto(orden, requisito="foto_ont"):
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito, vuelta=orden.vuelta,
        sha256=f"{requisito}-{orden.vuelta}", storage_key=f"k/{requisito}",
        nombre_original=f"{requisito}.jpg", mime_type="image/jpeg", bytes=1024,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)


def _cierre(orden, servicio=True, definicion=PREGUNTAS, **extra):
    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="cierre_campo",
        datos={"definicion": definicion,
               "respuestas": {"solucion": "Cambié el conector", "servicio_validado": servicio},
               **extra})


def _consumo(orden, profile):
    m = MaterialCatalogo.objects.create(org=orden.org, codigo="CON", nombre="Conector",
                                        unidad="u")
    return MovimientoDeMaterial.objects.create(
        org=orden.org, material=m, orden=orden, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), profile=profile, idempotency_key=f"rc-{orden.id}")


def _medicion(orden, en_rango):
    return PropuestaSupervisor.objects.create(
        org=orden.org, origen_id="caso-1", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(orden.id), "quedo_en_rango": en_rango}])


def _claves(r):
    return {p["clave"]: p["ok"] for p in r["puntos"]}


def test_v1_todo_bien_se_puede_cerrar_y_dice_por_que(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    _medicion(orden, True)

    r = RC.revisar(orden)

    assert (r["veredicto"], r["texto"]) == (RC.CERRAR, "Se puede cerrar")
    assert _claves(r) == {"checklist": True, "reporte": True, "servicio": True,
                          "medicion": True, "material": True}
    assert r["solucion"] == "Cambié el conector"
    assert r["evidencias"] == [{"id": "foto_ont", "titulo": "Foto de la ONT"}]
    assert r["sugeridas"] == []


def test_v2_un_no_manda(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    _cierre(orden, servicio=False)
    r = RC.revisar(orden)
    assert r["veredicto"] == RC.NO_CERRAR
    assert "El técnico dice que el servicio NO quedó funcionando." in [
        p["texto"] for p in r["puntos"] if p["ok"] is False]

    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").delete()
    _cierre(orden)
    _medicion(orden, False)
    assert RC.revisar(orden)["veredicto"] == RC.NO_CERRAR

    PropuestaSupervisor.objects.all().delete()
    EvidenciaTrabajo.objects.all().delete()
    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["checklist"], r["sugeridas"]) == (
        RC.NO_CERRAR, False, ["foto_ont"])


def test_v3_un_no_se_sabe_pide_revisar(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["material"]) == (RC.REVISAR, None)

    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").delete()
    _cierre(orden, sin_material_confirmado=True)
    assert RC.revisar(orden)["veredicto"] == RC.CERRAR

    _medicion(orden, None)
    assert RC.revisar(orden)["veredicto"] == RC.REVISAR


def test_v4_el_reporte_de_una_vuelta_ya_devuelta_no_cuenta(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    viejo = _cierre(orden)
    EventoTrabajo.objects.filter(pk=viejo.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=2))
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="reapertura_correccion",
                                 datos={})

    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["reporte"]) == (RC.NO_CERRAR, False)
    assert "servicio" not in _claves(r), "sin el cierre de esta vuelta no hay que preguntar"


def test_v5_lo_que_no_aplica(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    _cierre(orden, definicion=[{"id": "solucion", "tipo": "texto"}])
    r = RC.revisar(orden)
    assert set(_claves(r)) == {"checklist", "reporte", "material"}
    assert r["veredicto"] == RC.CERRAR

    for estado, validacion in ((OrdenTrabajo.EN_SITIO, OrdenTrabajo.SIN_EVALUAR),
                               (OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.APROBADO),
                               (OrdenTrabajo.CERRADA, OrdenTrabajo.APROBADO)):
        orden.estado_operativo, orden.estado_validacion = estado, validacion
        assert RC.revisar(orden) is None


def test_v6_programacion_trae_la_revision_en_la_terminada(org, orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    import zoneinfo

    hoy = timezone.now().astimezone(zoneinfo.ZoneInfo("America/Bogota")).date()
    c = Cuadrilla.objects.create(org=org, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=hoy,
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=org, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    otra = OrdenTrabajo.objects.create(
        org=org, numero=4, tipo_trabajo_version=orden.tipo_trabajo_version, zona="X",
        estado_operativo=OrdenTrabajo.EN_SITIO)
    AsignacionTrabajo.objects.create(orden=otra, profile=user_profile, rol="tecnico",
                                     es_principal=True)

    filas = {f["numero"]: f for f in D.del_dia(org, hoy)["cuadrillas"][0]["ordenes"]}

    assert filas[3]["revision"]["veredicto"] == RC.CERRAR
    assert filas[3]["vuelta"] == 1, "la clave de la decision de la persona"
    assert filas[4]["revision"] is None


def test_v7_indica_no_decide(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    antes = (orden.estado_operativo, orden.estado_validacion, orden.revision)
    eventos = EventoTrabajo.objects.filter(orden=orden).count()

    assert RC.revisar(orden)["veredicto"] == RC.CERRAR

    orden.refresh_from_db()
    assert (orden.estado_operativo, orden.estado_validacion, orden.revision) == antes
    assert EventoTrabajo.objects.filter(orden=orden).count() == eventos


def test_v8_la_medicion_de_otra_empresa_no_cuenta(org, orden, user_profile, org_b):
    """Aunque una propuesta de OTRA empresa nombrara esta orden, su medicion no
    entra en la revision. Se crea con el contexto de esa empresa (RLS), como la
    escribiria su propio ciclo.

    Mide RLS y el filtro `org=` JUNTOS: con RLS activo la mutacion que quita el
    filtro sobrevive (medido el 30/10/2026), porque la fila ya no se ve. El
    filtro queda para los roles que saltan RLS (CLAUDE.md §5)."""
    from conftest import set_rls_context

    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    set_rls_context(org_b)
    PropuestaSupervisor.objects.create(
        org=org_b, origen_id="caso-ajeno", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(orden.id), "quedo_en_rango": False}])
    #  La prueba no puede pasar porque la fila no exista: existe.
    assert PropuestaSupervisor.objects.filter(org=org_b).count() == 1
    set_rls_context(org)

    r = RC.revisar(orden)
    assert ("medicion" not in _claves(r), r["veredicto"]) == (True, RC.CERRAR)
