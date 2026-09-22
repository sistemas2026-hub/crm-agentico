# -*- coding: utf-8 -*-
"""
================================================================================
 M09-D  --  lo que este paso agrega, y lo que este paso arregla
================================================================================

'test_m09_supervisor.py' ya cubre el Shadow Mode base y sigue pasando. Acá va
lo del paso M09-D:

  1. LA DEDUPLICACION ARREGLADA. Antes miraba solo 'estado=propuesta', asi que
     una recomendacion RECHAZADA volvia identica al ciclo siguiente. La prueba
     que lo demuestra es la del rechazo -- las demas pasaban igual con el
     defecto adentro.

  2. 'orden_sin_programar' CON LA CONDICION CORREGIDA. Nueve escenarios, uno
     por estado, porque la condicion anterior ('programada_para IS NULL')
     habria propuesto programar ordenes que ya estaban en el plan.

  3. Las dos señales nuevas: 'programacion_sin_publicar' y 'dato_incompleto'.

  4. El rol del revisor, ahora que Profile.ROLES lo ofrece.

  5. CERO EFECTOS EXTERNOS, contados con un espia -- no deducidos de que nadie
     vio una llamada.
================================================================================
"""

import uuid
from datetime import date, timedelta

import pytest
from django.utils import timezone

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from common.utils import ROLES
from conftest import rls_org
from operaciones import supervisor
from operaciones.models import (
    ActividadOperativa,
    ProgramacionOrden,
    ProgramacionSemanal,
    PropuestaSupervisor,
)
from operaciones.permissions import EsJefeDeOperaciones


# =============================================================================
#  utilidades
# =============================================================================

@pytest.fixture
def tipo_version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="INST", nombre="Instalación")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1, estado="publicada",
        esquema={"requisitos": []}, schema_hash="x" * 64,
        publicada_en=timezone.now(),
    )


def _orden(org, tipo_version, *, numero, estado=OrdenTrabajo.ASIGNADA,
           programada_para=None, iniciada_en=None):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=tipo_version,
        origen_sistema="prueba", origen_tipo="manual", origen_ref=str(numero),
        cliente_nombre="Cliente de prueba", datos={},
        estado_operativo=estado,
        programada_para=programada_para, iniciada_en=iniciada_en,
    )


def _plan(org, *, estado=ProgramacionSemanal.BORRADOR, semana=None,
          publicada_en=None):
    return ProgramacionSemanal.objects.create(
        org=org,
        semana_inicio=semana or (timezone.localtime().date() - timedelta(days=2)),
        estado=estado, publicada_en=publicada_en,
    )


def _linea(org, plan, orden, *, estado=ProgramacionOrden.PLANIFICADA):
    return ProgramacionOrden.objects.create(
        org=org, programacion=plan, orden=orden,
        dia=plan.semana_inicio, zona="centro", estado=estado,
    )


def _tipos(org):
    return [s.tipo for s in supervisor.detectar(org)]


# =============================================================================
#  1. DEDUPLICACION  --  el defecto que este paso arregla
# =============================================================================

@pytest.fixture
def actividad_bloqueada(org_a, user_profile):
    return ActividadOperativa.objects.create(
        org=org_a, titulo="Cambiar el ONT", responsable=user_profile,
        estado_operativo=ActividadOperativa.BLOQUEADA,
        motivo_bloqueo="falta material",
    )


def _propuesta_de(org, tipo):
    senales = [s for s in supervisor.detectar(org) if s.tipo == tipo]
    assert senales, f"la señal {tipo} tenía que dispararse"
    return supervisor.registrar_propuesta(
        org, senales[0], supervisor.analizar(senales[0]))


def test_una_propuesta_rechazada_NO_vuelve_al_ciclo_siguiente(
        org_a, actividad_bloqueada, admin_profile):
    """EL DEFECTO DE M09-C.1. Con la dedup vieja, este test falla."""
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA,
                       comentario="ya está pedido el material")

    resumen = supervisor.correr_ciclo(org_a)

    assert resumen["propuestas"] == 0, (
        "una recomendación rechazada volvió a proponerse con los mismos hechos")
    assert PropuestaSupervisor.objects.filter(
        org=org_a, tipo_senal=PropuestaSupervisor.ACTIVIDAD_BLOQUEADA
    ).count() == 1


def test_una_propuesta_aceptada_tampoco_vuelve(org_a, actividad_bloqueada,
                                               admin_profile):
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA)
    assert supervisor.correr_ciclo(org_a)["propuestas"] == 0


def test_si_la_CONDICION_cambia_si_vuelve_a_proponerse(
        org_a, actividad_bloqueada, admin_profile):
    """
    Una decisión se toma sobre unos hechos. Con hechos distintos, la pregunta
    es otra -- y volver a preguntarla es correcto.
    """
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA)

    actividad_bloqueada.motivo_bloqueo = "el cliente no está en el domicilio"
    actividad_bloqueada.save(update_fields=["motivo_bloqueo"])

    assert supervisor.correr_ciclo(org_a)["propuestas"] == 1


def test_que_avance_una_MAGNITUD_no_la_hace_volver(org_a, user_profile,
                                                   admin_profile):
    """
    Un caso no deja de ser el mismo porque hoy lleve un día más. Si la huella
    llevara la magnitud, toda propuesta rechazada volvería al día siguiente.
    """
    from cases.models import Case

    caso = Case.objects.create(org=org_a, name="Sin internet",
                               status="New", priority="High")
    Case.objects.filter(pk=caso.pk).update(
        created_at=timezone.now() - timedelta(days=9))

    p = _propuesta_de(org_a, PropuestaSupervisor.CASO_ANTIGUO)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA)

    # Pasan tres días más: la magnitud cambia, la condición no.
    despues = timezone.now() + timedelta(days=3)
    assert supervisor.correr_ciclo(org_a, ahora=despues)["propuestas"] == 0


def test_una_propuesta_expirada_SI_puede_volver(org_a, actividad_bloqueada):
    """Expirar significa que nadie la miró. Volver a preguntar es correcto."""
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    PropuestaSupervisor.objects.filter(pk=p.pk).update(
        estado=PropuestaSupervisor.EXPIRADA)

    assert supervisor.correr_ciclo(org_a)["propuestas"] == 1


def test_el_ciclo_repetido_con_la_misma_evidencia_no_duplica(
        org_a, actividad_bloqueada):
    supervisor.correr_ciclo(org_a)
    segundo = supervisor.correr_ciclo(org_a)
    assert segundo["propuestas"] == 0
    assert segundo["repetidas"] >= 1


def test_el_historial_no_se_borra_al_deduplicar(org_a, actividad_bloqueada,
                                                admin_profile):
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA)
    supervisor.correr_ciclo(org_a)
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.RECHAZADA
    assert p.revisado_por_id == admin_profile.id


# =============================================================================
#  2. ORDEN_SIN_PROGRAMAR  --  los nueve escenarios
# =============================================================================

def test_A_ot_asignada_sin_plan_SI_produce_senal(org_a, tipo_version):
    _orden(org_a, tipo_version, numero=101)
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR in _tipos(org_a)


def test_B_ot_en_plan_BORRADOR_no_produce_senal_de_orden(org_a, tipo_version):
    """
    Ya hay un plan en curso. Proponer 'programar' sería ruido: de un plan sin
    publicar habla 'programacion_sin_publicar', que es otra señal y otro dueño.
    """
    o = _orden(org_a, tipo_version, numero=102)
    _linea(org_a, _plan(org_a), o)
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR not in _tipos(org_a)


def test_C_ot_en_plan_PUBLICADO_no_propone_programar_sino_dato_incompleto(
        org_a, tipo_version):
    """El falso positivo que la condición anterior habría producido."""
    o = _orden(org_a, tipo_version, numero=103)
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                 publicada_en=timezone.now())
    _linea(org_a, plan, o)

    tipos = _tipos(org_a)
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR not in tipos
    assert PropuestaSupervisor.DATO_INCOMPLETO in tipos


def test_D_ot_con_programada_para_no_produce_senal(org_a, tipo_version):
    _orden(org_a, tipo_version, numero=104,
           programada_para=timezone.now() + timedelta(days=1))
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR not in _tipos(org_a)


@pytest.mark.parametrize("estado", [
    OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO,
    OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA,
    OrdenTrabajo.CANCELADA, OrdenTrabajo.CORRECCION_REQUERIDA,
])
def test_EFG_una_ot_que_ya_no_esta_asignada_no_produce_senal(
        org_a, tipo_version, estado):
    """
    E · iniciada · F · completada · G · cancelada, y las demás.

    Las tres OT de producción están así: 'en_sitio' y 'completada_campo' con
    'programada_para' vacío. La condición vieja habría propuesto programarlas.
    """
    _orden(org_a, tipo_version, numero=200 + len(estado), estado=estado,
           iniciada_en=timezone.now() - timedelta(hours=2))
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR not in _tipos(org_a)


def test_H_una_linea_de_plan_CANCELADA_no_cuenta_como_programacion(
        org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=108)
    _linea(org_a, _plan(org_a), o, estado=ProgramacionOrden.CANCELADA)
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR in _tipos(org_a)


def test_I_una_linea_REPROGRAMADA_tampoco_cuenta(org_a, tipo_version):
    """Una línea reprogramada ya fue reemplazada: no compromete nada."""
    o = _orden(org_a, tipo_version, numero=109)
    _linea(org_a, _plan(org_a), o, estado=ProgramacionOrden.REPROGRAMADA)
    assert PropuestaSupervisor.ORDEN_SIN_PROGRAMAR in _tipos(org_a)


def test_la_propuesta_no_afirma_que_la_orden_este_atrasada(org_a, tipo_version):
    _orden(org_a, tipo_version, numero=110)
    p = _propuesta_de(org_a, PropuestaSupervisor.ORDEN_SIN_PROGRAMAR)
    texto = (p.motivo + " " + p.accion_propuesta).lower()
    assert "atrasad" not in texto or "no se afirma" in texto


# =============================================================================
#  3. PROGRAMACION_SIN_PUBLICAR
# =============================================================================

def test_un_plan_en_borrador_de_una_semana_que_ya_empezo_produce_senal(org_a):
    _plan(org_a)
    assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR in _tipos(org_a)


def test_un_plan_PUBLICADO_no_produce_senal(org_a):
    _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
          publicada_en=timezone.now())
    assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR not in _tipos(org_a)


def test_un_plan_CERRADO_no_produce_senal(org_a):
    _plan(org_a, estado=ProgramacionSemanal.CERRADA)
    assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR not in _tipos(org_a)


def test_un_borrador_de_una_semana_FUTURA_no_produce_senal(org_a):
    _plan(org_a, semana=timezone.localtime().date() + timedelta(days=7))
    assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR not in _tipos(org_a)


def test_la_publicacion_no_se_infiere_de_que_existan_lineas(org_a, tipo_version):
    """Un borrador también tiene líneas. Confundirlas sería inferir."""
    plan = _plan(org_a)
    _linea(org_a, plan, _orden(org_a, tipo_version, numero=120))
    assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR in _tipos(org_a)


def test_la_senal_de_plan_cita_estado_y_publicada_en(org_a):
    _plan(org_a)
    p = _propuesta_de(org_a, PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR)
    datos = " ".join(o["dato"] for o in p.evidencia)
    assert "borrador" in datos and "publicada_en" in datos


def test_el_supervisor_no_publica_el_plan(org_a):
    plan = _plan(org_a)
    supervisor.correr_ciclo(org_a)
    plan.refresh_from_db()
    assert plan.estado == ProgramacionSemanal.BORRADOR
    assert plan.publicada_en is None


# =============================================================================
#  4. DATO_INCOMPLETO  --  no es un comodín
# =============================================================================

def test_dato_incompleto_nombra_el_campo_y_el_objeto(org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=130)
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                 publicada_en=timezone.now())
    _linea(org_a, plan, o)

    p = _propuesta_de(org_a, PropuestaSupervisor.DATO_INCOMPLETO)
    datos = " ".join(ob["dato"] for ob in p.evidencia)
    assert "programada_para" in datos
    assert any(ob["fuente"] == "orden_trabajo" for ob in p.evidencia)
    assert any(ob["fuente"] == "programacion_semanal" for ob in p.evidencia)


def test_dato_incompleto_es_nivel_0(org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=131)
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                 publicada_en=timezone.now())
    _linea(org_a, plan, o)
    p = _propuesta_de(org_a, PropuestaSupervisor.DATO_INCOMPLETO)
    assert p.nivel_autonomia_requerido == PropuestaSupervisor.NIVEL_OBSERVAR


def test_dato_incompleto_no_se_emite_sobre_un_plan_en_borrador(org_a,
                                                               tipo_version):
    """Un borrador no compromete nada: no hay inconsistencia que reportar."""
    o = _orden(org_a, tipo_version, numero=132)
    _linea(org_a, _plan(org_a), o)
    assert PropuestaSupervisor.DATO_INCOMPLETO not in _tipos(org_a)


def test_dato_incompleto_no_aparece_sin_un_campo_faltante(org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=133,
               programada_para=timezone.now() + timedelta(days=1))
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                 publicada_en=timezone.now())
    _linea(org_a, plan, o)
    assert PropuestaSupervisor.DATO_INCOMPLETO not in _tipos(org_a)


def test_dato_incompleto_no_nombra_a_nadie(org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=134)
    plan = _plan(org_a, estado=ProgramacionSemanal.PUBLICADA,
                 publicada_en=timezone.now())
    _linea(org_a, plan, o)
    p = _propuesta_de(org_a, PropuestaSupervisor.DATO_INCOMPLETO)
    texto = (p.motivo + " " + p.accion_propuesta).lower()
    for prohibido in ("incumpl", "negligen", "culpa", "olvid", "no quiso"):
        assert prohibido not in texto


# =============================================================================
#  5. EL REVISOR
# =============================================================================

def test_los_roles_del_permiso_existen_en_el_catalogo():
    """
    El hueco de M09-C.1: el permiso aceptaba OPERACIONES y SUPERVISOR, y el
    catálogo de choices sólo ofrecía ADMIN y USER.
    """
    from campo.permissions import ROLES_GESTION

    declarados = {valor for valor, _ in ROLES}
    assert ROLES_GESTION <= declarados, (
        f"el permiso exige {ROLES_GESTION - declarados} y Profile.ROLES no los ofrece")


@pytest.mark.parametrize("rol,puede", [
    ("ADMIN", True), ("SUPERVISOR", True), ("OPERACIONES", True),
    ("USER", False),
])
def test_quien_puede_revisar(rf, org_a, regular_user, rol, puede):
    from common.models import Profile

    perfil = Profile.objects.create(user=regular_user, org=org_a, role=rol,
                                    is_active=True)
    peticion = rf.get("/api/operaciones/propuestas/")
    peticion.user = regular_user
    peticion.profile = perfil
    peticion.org = org_a
    assert EsJefeDeOperaciones().has_permission(peticion, None) is puede


def test_un_perfil_OPERACIONES_no_es_administrador(org_a, regular_user):
    """Revisar no es administrar: el Jefe de Operaciones no queda org-admin."""
    from common.models import Profile

    p = Profile.objects.create(user=regular_user, org=org_a,
                               role="OPERACIONES", is_active=True)
    assert p.is_organization_admin is False


def test_no_se_creo_un_segundo_mecanismo_de_autorizacion():
    """EsJefeDeOperaciones decide con ROLES_GESTION, que importa de campo."""
    import inspect

    from campo.permissions import ROLES_GESTION
    from operaciones import permissions as permisos_operaciones

    fuente = inspect.getsource(permisos_operaciones)
    assert "ROLES_GESTION" in fuente
    assert permisos_operaciones.ROLES_GESTION is ROLES_GESTION


# =============================================================================
#  6. CERO EFECTOS EXTERNOS  --  contados, no deducidos
# =============================================================================

def test_el_ciclo_no_toca_ningun_sistema_externo(org_a, tipo_version,
                                                 actividad_bloqueada,
                                                 monkeypatch):
    llamadas = []

    import requests

    for metodo in ("get", "post", "put", "patch", "delete", "request"):
        monkeypatch.setattr(
            requests, metodo,
            lambda *a, **k: llamadas.append(a[:1]) or (_ for _ in ()).throw(
                AssertionError("el Supervisor intentó una llamada externa")),
            raising=False,
        )

    _orden(org_a, tipo_version, numero=140)
    _plan(org_a)
    resumen = supervisor.correr_ciclo(org_a)

    assert llamadas == []
    assert resumen["propuestas"] >= 1


def test_el_ciclo_no_modifica_la_orden_ni_el_plan(org_a, tipo_version):
    o = _orden(org_a, tipo_version, numero=141)
    plan = _plan(org_a)
    antes_o = (o.estado_operativo, o.programada_para, o.iniciada_en)
    antes_p = (plan.estado, plan.publicada_en)

    supervisor.correr_ciclo(org_a)

    o.refresh_from_db()
    plan.refresh_from_db()
    assert (o.estado_operativo, o.programada_para, o.iniciada_en) == antes_o
    assert (plan.estado, plan.publicada_en) == antes_p


def test_el_ciclo_no_cierra_ningun_caso(org_a):
    from cases.models import Case

    caso = Case.objects.create(org=org_a, name="Sin internet", status="New",
                               priority="High")
    Case.objects.filter(pk=caso.pk).update(
        created_at=timezone.now() - timedelta(days=30))

    supervisor.correr_ciclo(org_a)

    caso.refresh_from_db()
    assert caso.status == "New"
    assert caso.resolved_at is None
    assert caso.closed_on is None


def test_ninguna_propuesta_supera_el_nivel_1(org_a, tipo_version,
                                             actividad_bloqueada):
    _orden(org_a, tipo_version, numero=142)
    _plan(org_a)
    supervisor.correr_ciclo(org_a)

    niveles = set(PropuestaSupervisor.objects.filter(org=org_a)
                  .values_list("nivel_autonomia_requerido", flat=True))
    assert niveles <= {PropuestaSupervisor.NIVEL_OBSERVAR,
                       PropuestaSupervisor.NIVEL_RECOMENDAR}


# =============================================================================
#  7. TENANT
# =============================================================================

def test_las_senales_nuevas_no_cruzan_organizaciones(org_a, org_b, tipo_version):
    with rls_org(org_a):
        _plan(org_a)
    with rls_org(org_b):
        assert PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR not in _tipos(org_b)


def test_la_huella_queda_guardada(org_a, actividad_bloqueada):
    p = _propuesta_de(org_a, PropuestaSupervisor.ACTIVIDAD_BLOQUEADA)
    assert p.huella_condicion
    assert "falta material" in p.huella_condicion
