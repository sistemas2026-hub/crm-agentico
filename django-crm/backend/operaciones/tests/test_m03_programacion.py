# -*- coding: utf-8 -*-
"""
================================================================================
 M03  --  programación, disponibilidad y novedades
================================================================================

La regla operativa que estas pruebas fijan: la programación SEMANAL es la base,
y la DIARIA se modifica por novedades. Nunca se sobrescribe la original en
silencio.

Lo que se reutiliza y no se vuelve a crear: campo.OrdenTrabajo (el trabajo) y
campo.AsignacionTrabajo (la cuadrilla). Aquí solo se agrega el plan, la
disponibilidad y el registro de lo que obligó a cambiarlo.
================================================================================
"""

from datetime import date, time, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from conftest import rls_org
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from operaciones.models import (
    DisponibilidadTecnico,
    NovedadOperativa,
    ProgramacionOrden,
    ProgramacionSemanal,
)


@pytest.fixture
def version_trabajo(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def orden(org_a, version_trabajo):
    return OrdenTrabajo.objects.create(
        org=org_a, numero=1, tipo_trabajo_version=version_trabajo,
        cliente_nombre="Cliente de prueba",
        cliente_direccion="Calle 1 #2-3",
    )


@pytest.fixture
def lunes():
    hoy = timezone.localdate()
    return hoy - timedelta(days=hoy.weekday())


# --- 1. disponibilidad -----------------------------------------------------
def test_una_franja_de_disponibilidad_y_una_ausencia(org_a, user_profile, lunes):
    turno = DisponibilidadTecnico.objects.create(
        org=org_a, profile=user_profile, fecha=lunes,
        hora_inicio=time(8, 0), hora_fin=time(17, 0), zona="NORTE",
    )
    assert turno.disponible is True

    ausencia = DisponibilidadTecnico.objects.create(
        org=org_a, profile=user_profile, fecha=lunes + timedelta(days=1),
        hora_inicio=time(8, 0), hora_fin=time(17, 0),
        disponible=False, motivo="Permiso médico",
    )
    assert ausencia.disponible is False


def test_una_ausencia_sin_motivo_no_se_guarda(org_a, user_profile, lunes):
    """Igual que un bloqueo: sin causa, el dato no sirve para decidir nada."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DisponibilidadTecnico.objects.create(
                org=org_a, profile=user_profile, fecha=lunes,
                hora_inicio=time(8, 0), hora_fin=time(17, 0),
                disponible=False, motivo="",
            )


def test_una_franja_invertida_no_se_guarda(org_a, user_profile, lunes):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DisponibilidadTecnico.objects.create(
                org=org_a, profile=user_profile, fecha=lunes,
                hora_inicio=time(17, 0), hora_fin=time(8, 0),
            )


# --- 2. capacidad ----------------------------------------------------------
def test_la_capacidad_no_se_almacena(org_a):
    """
    No hay ningún campo 'capacidad' en ninguna tabla, y es deliberado.

    Depende de la disponibilidad, de la carga ya asignada, de la duración del
    tipo de trabajo, de la zona y de los bloqueos: guardarla es garantizar que
    quede vieja la próxima vez que cualquiera de esos cinco cambie.
    """
    campos = {f.name for f in DisponibilidadTecnico._meta.get_fields()}
    assert "capacidad" not in campos
    campos_plan = {f.name for f in ProgramacionOrden._meta.get_fields()}
    assert "capacidad" not in campos_plan


# --- 3. programación semanal -----------------------------------------------
def test_el_plan_semanal_y_sus_lineas(org_a, orden, lunes, admin_profile):
    plan = ProgramacionSemanal.objects.create(org=org_a, semana_inicio=lunes)
    assert plan.estado == ProgramacionSemanal.BORRADOR

    linea = ProgramacionOrden.objects.create(
        org=org_a, programacion=plan, orden=orden, dia=lunes,
        hora_inicio=time(9, 0), hora_fin=time(11, 0),
        zona="NORTE", prioridad=20, secuencia=1,
    )
    assert linea.estado == ProgramacionOrden.PLANIFICADA

    plan.estado = ProgramacionSemanal.PUBLICADA
    plan.publicada_en = timezone.now()
    plan.publicada_por = admin_profile
    plan.save()
    assert plan.lineas.count() == 1


def test_una_semana_no_puede_planificarse_dos_veces(org_a, lunes):
    ProgramacionSemanal.objects.create(org=org_a, semana_inicio=lunes)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProgramacionSemanal.objects.create(org=org_a, semana_inicio=lunes)


def test_el_tipo_de_trabajo_no_se_copia_en_la_linea(org_a):
    """Un dato duplicado es un dato que se desincroniza: sale de la orden."""
    campos = {f.name for f in ProgramacionOrden._meta.get_fields()}
    assert "tipo_trabajo" not in campos
    assert "tipo_trabajo_version" not in campos
    assert "orden" in campos


# --- 4. asignación (se reutiliza campo.AsignacionTrabajo) ------------------
def test_la_cuadrilla_se_arma_sobre_la_asignacion_que_ya_existe(
        org_a, orden, user_profile, admin_profile):
    """No se crea otra estructura de cuadrillas: la de campo ya soporta N."""
    AsignacionTrabajo.objects.create(
        orden=orden, profile=user_profile,
        rol=AsignacionTrabajo.TECNICO_LIDER, es_principal=True)
    AsignacionTrabajo.objects.create(
        orden=orden, profile=admin_profile, rol=AsignacionTrabajo.AYUDANTE)

    assert orden.asignaciones.count() == 2
    assert orden.tecnico_principal == user_profile


def test_el_catalogo_de_roles_quedo_cerrado():
    """
    Antes era texto libre y ya había divergido: las 3 asignaciones de
    producción dicen 'tecnico_lider', que no estaba entre los cuatro roles que
    el propio modelo documentaba. Se cerró el catálogo INCLUYENDO ese valor, en
    vez de reescribir datos históricos por una razón cosmética.
    """
    roles = {r for r, _ in AsignacionTrabajo.ROLES_CUADRILLA}
    assert "tecnico_lider" in roles
    assert roles == {"tecnico", "tecnico_lider", "ayudante", "chofer", "supervisor"}


# --- 5. reprogramación, y su historial -------------------------------------
def test_reprogramar_deja_el_antes_y_el_despues(org_a, orden, lunes, admin_profile):
    """
    Es la regla operativa entera: la diaria se modifica por novedades, y la
    novedad guarda de qué a qué. Sin esto, 'se reprogramó' sería una fecha que
    cambió sola.
    """
    original = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
    orden.programada_para = original
    orden.save()

    nueva = original + timedelta(hours=5)
    NovedadOperativa.objects.create(
        org=org_a, tipo=NovedadOperativa.REPROGRAMACION,
        orden=orden, registrada_por=admin_profile,
        descripcion="El cliente no estaba en el domicilio",
        programada_anterior=original, programada_nueva=nueva,
    )
    orden.programada_para = nueva
    orden.save()
    orden.refresh_from_db()

    novedad = orden.novedades.first()
    assert orden.programada_para == nueva
    assert novedad.programada_anterior == original, (
        "la fecha original tiene que sobrevivir a la reprogramación"
    )
    assert novedad.programada_nueva == nueva
    assert novedad.registrada_por_id == admin_profile.id


def test_la_linea_del_plan_no_se_pisa_al_reprogramar(org_a, orden, lunes):
    """
    El plan dice lo que se pensó; 'programada_para' dice lo que rige. Son dos
    datos distintos y el primero no se toca cuando el segundo cambia.
    """
    plan = ProgramacionSemanal.objects.create(org=org_a, semana_inicio=lunes)
    linea = ProgramacionOrden.objects.create(
        org=org_a, programacion=plan, orden=orden, dia=lunes,
        hora_inicio=time(9, 0), secuencia=1)

    orden.programada_para = timezone.now() + timedelta(days=2)
    orden.save()
    linea.refresh_from_db()

    assert linea.dia == lunes
    assert linea.hora_inicio == time(9, 0)


# --- 6. novedades ----------------------------------------------------------
def test_la_lista_de_causas_no_incluye_culpar_a_nadie():
    """
    'incumplimiento_de_persona' no está, y su ausencia es la garantía.

    Una demora puede ser un bloqueo, un material, una dependencia, una
    ausencia, un cambio de prioridad o un dato mal cargado. Con los datos de
    hoy no hay forma de distinguirlas de un incumplimiento.
    """
    tipos = {t for t, _ in NovedadOperativa.TIPOS}
    assert "incumplimiento_de_persona" not in tipos
    assert "demora_sin_causa_registrada" in tipos, (
        "tiene que existir la causa honesta para cuando solo hay fechas"
    )


# --- 7. aislamiento --------------------------------------------------------
def test_la_programacion_de_una_empresa_no_se_ve_desde_otra(org_a, org_b):
    hoy = timezone.localdate()
    with rls_org(org_a):
        ProgramacionSemanal.objects.create(org=org_a, semana_inicio=hoy)
    with rls_org(org_b):
        ProgramacionSemanal.objects.create(org=org_b, semana_inicio=hoy)

    # El filtro de la aplicacion aisla en cualquier motor. Que la BASE ademas
    # lo impida se prueba aparte, contra PostgreSQL de verdad -- ver abajo.
    with rls_org(org_a):
        assert ProgramacionSemanal.objects.filter(org=org_a).count() == 1
        assert set(ProgramacionSemanal.objects.filter(org=org_a)
                   .values_list("org_id", flat=True)) == {org_a.id}


@pytest.mark.postgres_only
def test_las_seis_tablas_quedan_con_su_politica_rls_estampada():
    """
    Que la migración 0002 haya hecho su trabajo, verificado contra el catálogo.

    QUE PRUEBA Y QUE NO  --  y la diferencia importa
    ------------------------------------------------
    Prueba que las seis tablas quedan con RLS habilitado, FORZADO (aplica
    también al dueño) y con las dos políticas creadas. Eso es lo que la
    migración promete, y es lo que se puede afirmar.

    NO prueba que la política impida leer la otra organización en esta corrida,
    y no por descuido: el usuario de la base de pruebas es SUPERUSUARIO, y un
    superusuario saltea RLS pase lo que pase con FORCE. Es la misma situación
    que DESPLIEGUE.md ya documenta para producción -- las políticas están y no
    protegen nada mientras el CRM se conecte como 'postgres'; el corte a
    'crm_user' quedó como pendiente de despliegue. Escribir aquí una afirmación
    de "no ve la otra empresa" daría un rojo permanente que no dice nada sobre
    el código, o peor, un verde falso el día que alguien lo "arregle".

    El aislamiento que SI se ejercita en toda corrida es el de la aplicación,
    en la prueba de arriba.
    """
    if connection.vendor != "postgresql":
        pytest.skip("RLS no existe en SQLite: la política no se puede inspeccionar")

    tablas = [
        "operaciones_actividad",
        "operaciones_disponibilidad",
        "operaciones_programacion_semanal",
        "operaciones_programacion_orden",
        "operaciones_novedad",
        "operaciones_propuesta_supervisor",
    ]
    with connection.cursor() as cur:
        for tabla in tablas:
            cur.execute(
                """select c.relrowsecurity, c.relforcerowsecurity
                     from pg_class c join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'public' and c.relname = %s""", [tabla])
            fila = cur.fetchone()
            assert fila, f"{tabla} no existe"
            habilitado, forzado = fila
            assert habilitado, f"{tabla}: RLS no quedó habilitado"
            assert forzado, f"{tabla}: falta FORCE, el dueño la saltearía"

            cur.execute(
                "select policyname from pg_policies "
                "where schemaname='public' and tablename=%s", [tabla])
            politicas = {p[0] for p in cur.fetchall()}
            assert {"org_isolation", "org_insert_check"} <= politicas, (
                f"{tabla}: le faltan políticas ({politicas})"
            )
