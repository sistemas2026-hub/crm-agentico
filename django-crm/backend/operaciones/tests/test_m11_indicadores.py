# -*- coding: utf-8 -*-
"""
================================================================================
 M11  --  indicadores y reportes operativos
================================================================================

Un indicador equivocado es peor que ninguno: se lee, se cree y se decide sobre
él. Por eso lo que más se prueba aquí no son los conteos --que son fáciles--
sino las tres formas de mentir sin querer:

  * presentar un promedio calculado sobre la mitad de la población como si
    fuera de toda;
  * presentar 0% sobre cero casos como si fuera un logro;
  * dejar que consultar un indicador produzca trabajo de negocio.

Las tres tienen su prueba, y la del promedio se comprueba con cobertura
parcial DE VERDAD, no con un mock.
================================================================================
"""

from __future__ import annotations

import socket
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from business_hours.models import BusinessCalendar
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from cases.models import Case
from common.models import Activity, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import actividades as m02
from operaciones import capacidad, indicadores, supervisor
from operaciones.models import (ActividadOperativa, ProgramacionOrden,
                                ProgramacionSemanal, PropuestaSupervisor)
from operaciones.programacion import programar_orden

I = indicadores
A = ActividadOperativa
P = PropuestaSupervisor
URL_IND = "/api/operaciones/indicadores/"
URL_REP = "/api/operaciones/reportes/"
_n = [8000]
_c = [0]


def _hoy():
    return timezone.localtime(timezone.now()).date()


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"k{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


def _calendario(org):
    cal = BusinessCalendar.objects.create(org=org, name="Default",
                                          timezone="UTC", is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday",
              "saturday", "sunday"):
        setattr(cal, f"{d}_open", time(8, 0))
        setattr(cal, f"{d}_close", time(16, 0))
    cal.save()
    return cal


def _orden(org, duracion=None):
    _n[0] += 1
    wt = WorkType.objects.create(org=org, codigo=f"k_{_n[0]}", nombre="k")
    esquema = {"campos": [], "evidencias": []}
    if duracion is not None:
        esquema[capacidad.CLAVE_DURACION] = duracion
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    return OrdenTrabajo.objects.create(
        org=org, numero=_n[0], tipo_trabajo_version=v,
        cliente_nombre=f"C{_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


def _programar(org, orden, actor, dia=None, hora=9):
    dia = dia or (_hoy() + timedelta(days=1))
    plan, _ = ProgramacionSemanal.objects.get_or_create(
        org=org, semana_inicio=dia - timedelta(days=dia.weekday()),
        defaults={"estado": ProgramacionSemanal.BORRADOR})
    return programar_orden(
        org=org, orden=orden, programacion=plan, actor=actor,
        programada_para=timezone.make_aware(datetime.combine(dia, time(hora, 0))))


def _caso(org, **kw):
    _c[0] += 1
    kw.setdefault("name", f"Caso {_c[0]}")
    kw.setdefault("status", "New")
    kw.setdefault("priority", "Normal")
    return Case.objects.create(org=org, **kw)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


# ==================================================== 1. casos
@pytest.mark.django_db
def test_1_conteo_de_casos(org_a):
    ahora = timezone.now()
    _caso(org_a, status="New", priority="High")
    _caso(org_a, status="New", priority="Low")
    _caso(org_a, status="Closed", priority="Normal", resolved_at=ahora)

    r = I.indicadores_casos(org_a, ahora=ahora)
    assert r["total"]["valor"] == 3 and r["total"]["estado"] == I.VALIDO
    assert r["cerrados"]["valor"] == 1
    assert r["abiertos"]["valor"] == 2
    assert r["por_estado"]["New"]["valor"] == 2
    assert r["por_prioridad"]["High"]["valor"] == 1
    #  un conteo sobre campo obligatorio no tiene cobertura parcial
    assert r["total"]["cobertura"] == 1.0


# ==================================================== 2-4. actividades
@pytest.mark.django_db
def test_2_3_4_conteo_de_actividades(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)

    vencida = m02.crear(org=org_a, actor=actor, titulo="vencida",
                        vence_en=ahora - timedelta(hours=5))
    m02.asignar_responsable(vencida, actor=actor, responsable=p1)

    bloq = m02.crear(org=org_a, actor=actor, titulo="bloqueada")
    m02.asignar_responsable(bloq, actor=actor, responsable=p1)
    m02.bloquear(bloq, actor=actor, motivo="falta permiso")

    m02.crear(org=org_a, actor=actor, titulo="sin dueño")

    prev = m02.crear(org=org_a, actor=actor, titulo="previa")
    dep = m02.crear(org=org_a, actor=actor, titulo="dependiente")
    m02.establecer_dependencia(dep, actor=actor, depende_de=prev)

    hecha = m02.crear(org=org_a, actor=actor, titulo="hecha")
    m02.completar(hecha, actor=actor, requiere_validacion=True)

    r = I.indicadores_actividades(org_a, ahora=ahora)
    assert r["total"]["valor"] == 6
    assert r["abiertas"]["valor"] == 5
    assert r["vencidas"]["valor"] == 1
    assert r["estado_bloqueada"]["valor"] == 1
    #  3, no 4: 'hecha' esta completada y 'sin_responsable' se cuenta sobre
    #  las ABIERTAS -- una actividad cerrada sin responsable ya no es una senal.
    assert r["sin_responsable"]["valor"] == 3
    assert r["con_dependencia_pendiente"]["valor"] == 1
    assert r["validacion_pendiente"]["valor"] == 1
    assert r["estado_completada"]["valor"] == 1

    #  el catálogo ENTERO, incluidos los tipos en cero
    assert set(r["por_tipo"]) == {t for t, _e in A.TIPOS}
    assert r["por_tipo"]["handoff"]["valor"] == 0, (
        "un tipo sin actividades tiene que aparecer en cero, no faltar")


# ==================================================== 5. compromisos
@pytest.mark.django_db
def test_5_compromisos_vencidos(org_a, actor):
    ahora = timezone.now()
    m02.crear(org=org_a, actor=actor, tipo=A.COMPROMISO, titulo="vencido",
              vence_en=ahora - timedelta(hours=4))
    m02.crear(org=org_a, actor=actor, tipo=A.COMPROMISO, titulo="pronto",
              vence_en=ahora + timedelta(hours=3))
    m02.crear(org=org_a, actor=actor, tipo=A.COMPROMISO, titulo="lejos",
              vence_en=ahora + timedelta(days=20))
    m02.crear(org=org_a, actor=actor, tipo=A.COMPROMISO, titulo="sin fecha")

    r = I.indicadores_compromisos(org_a, ahora)
    assert r["total"]["valor"] == 4
    assert r["vencidos"]["valor"] == 1
    assert r["por_vencer"]["valor"] == 1
    assert r["a_tiempo"]["valor"] == 1
    #  SIN fecha se cuenta aparte: no es "a tiempo"
    assert r["sin_fecha"]["valor"] == 1
    assert r["ventana_por_vencer_horas"] == 24


# ==================================================== 6-7. programación
@pytest.mark.django_db
def test_6_7_programacion(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    programada = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=programada, profile=p1,
                                     es_principal=True)
    _programar(org_a, programada, actor)

    sin_programar = _orden(org_a, duracion=60)
    AsignacionTrabajo.objects.create(orden=sin_programar, profile=p1,
                                     es_principal=True)
    _orden(org_a, duracion=30)          # sin cuadrilla y sin programar

    r = I.indicadores_programacion(org_a)
    assert r["ordenes_total"]["valor"] == 3
    assert r["ordenes_programadas"]["valor"] == 1
    assert r["ordenes_sin_programar"]["valor"] == 2
    assert r["lineas_vigentes"]["valor"] == 1
    assert r["planes_borrador"]["valor"] == 1
    assert r["ordenes_sin_cuadrilla"]["valor"] == 1
    assert r["asignaciones"]["valor"] == 2


# ==================================================== 8-9. capacidad
@pytest.mark.django_db
def test_8_capacidad_valida(org_a, actor):
    """Capacidad 480, carga 560: la sobrecarga es defendible y se cuenta."""
    _calendario(org_a)
    _, p1 = _persona(org_a)
    for m, h in ((280, 8), (280, 12)):
        o = _orden(org_a, duracion=m)
        AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
        _programar(org_a, o, actor, hora=h)

    cap = I.indicadores_programacion(org_a)["capacidad"]
    assert len(cap["jornadas_sobrecargadas"]) == 1
    s = cap["jornadas_sobrecargadas"][0]
    assert (s["capacidad_minutos"], s["carga_minutos"], s["exceso_minutos"]) \
        == (480, 560, 80)
    assert s["es_cota_inferior"] is False
    assert cap["jornadas_no_determinables"] == []


@pytest.mark.django_db
def test_9_capacidad_indeterminada_no_es_cero(org_a, actor):
    """
    Sin calendario la capacidad no se puede determinar. NO se reporta 0 ni se
    afirma que la jornada quepa: se cuenta como no determinable.
    """
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=600)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)

    cap = I.indicadores_programacion(org_a)["capacidad"]
    assert cap["jornadas_sobrecargadas"] == [], (
        "afirmó sobrecarga sin poder calcular la capacidad")
    assert len(cap["jornadas_no_determinables"]) == 1
    assert "INDETERMINADO no es cero" in cap["nota"]


# ==================================================== 10. supervisor
@pytest.mark.django_db
def test_10_propuestas_del_supervisor(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=3))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    supervisor.correr_ciclo(org_a, ahora)

    #  Se consulta con la hora de AHORA, no con la de antes del ciclo: la
    #  ventana es [desde, hasta) y las propuestas se crearon despues de 'ahora'.
    r = I.indicadores_supervisor(org_a, ahora=timezone.now())
    assert r["senales_vigentes"]["valor"] > 0
    assert r["propuestas_total"]["valor"] > 0
    assert r["propuestas_propuesta"]["valor"] > 0
    assert P.ACTIVIDAD_VENCIDA in r["senales_por_tipo"]
    #  el catálogo entero de tipos, incluidos los que están en cero
    assert set(r["propuestas_por_tipo_senal"]) == {t for t, _e in P.TIPOS_SENAL}

    #  tasa de revisión: nadie revisó todavía
    assert r["tasa_revision"]["valor"] == 0.0
    assert r["tasa_revision"]["estado"] == I.VALIDO


# ==================================================== 11-13. cobertura y SLA
@pytest.mark.django_db
def test_11_12_cobertura_parcial_de_first_response(org_a):
    """
    EL CASO DE §C, con cobertura parcial DE VERDAD: 1 de 3 casos tiene
    'first_response_at'. El promedio NO se presenta como válido.
    """
    ahora = timezone.now()
    desde = ahora - timedelta(days=2)
    creado = ahora - timedelta(days=1)

    con_dato = _caso(org_a)
    Case.objects.filter(pk=con_dato.pk).update(
        created_at=creado, first_response_at=creado + timedelta(hours=2))
    for _ in range(2):
        c = _caso(org_a)
        Case.objects.filter(pk=c.pk).update(created_at=creado)

    r = I.indicadores_casos(org_a, desde, ahora, ahora)
    frt = r["primera_respuesta_horas"]
    assert frt["estado"] == I.DATOS_INSUFICIENTES, (
        "presentó un promedio sobre 1 de 3 como si fuera de todos")
    assert frt["con_dato"] == 1 and frt["denominador"] == 3
    assert frt["cobertura"] == round(1 / 3, 4)
    assert frt["valor"] is not None, "ocultó el valor en vez de etiquetarlo"
    assert "no se imputa" in frt["motivo"]

    #  y los conteos del mismo bloque SÍ son válidos: no hay nada que falte
    assert r["total"]["estado"] == I.VALIDO


@pytest.mark.django_db
def test_11b_sin_poblacion_es_no_aplica_no_cero(org_a):
    """0 sobre 0 no es 0%: es NO_APLICA. Un 0% sobre nada parece un logro."""
    ahora = timezone.now()
    r = I.indicadores_casos(org_a, ahora - timedelta(days=1), ahora, ahora)
    frt = r["primera_respuesta_horas"]
    assert frt["estado"] == I.NO_APLICA
    assert frt["valor"] is None
    assert frt["cobertura"] is None
    assert "no es un resultado" in frt["motivo"]


@pytest.mark.django_db
def test_13_sla_no_inventa_reglas(org_a):
    """
    El SLA sale de los campos que 'Case' ya define. Un caso sin objetivo
    declarado se cuenta como NO CALCULABLE, no como cumplido.
    """
    ahora = timezone.now()
    desde = ahora - timedelta(days=2)
    creado = ahora - timedelta(days=1)

    sin_objetivo = _caso(org_a)
    Case.objects.filter(pk=sin_objetivo.pk).update(
        created_at=creado, sla_first_response_hours=0, sla_resolution_hours=0)
    normal = _caso(org_a)
    Case.objects.filter(pk=normal.pk).update(created_at=creado)

    r = I.indicadores_sla(org_a, desde, ahora, ahora)
    assert r["casos_en_periodo"]["valor"] == 2
    assert r["no_calculable"]["valor"] == 1, (
        "contó como cumplido un caso sin objetivo declarado")
    assert r["cumplimiento"]["denominador"] == 2
    assert r["cumplimiento"]["con_dato"] == 1
    assert r["cumplimiento"]["estado"] == I.DATOS_INSUFICIENTES


# ==================================================== 14. tenant
@pytest.mark.django_db
def test_14_aislamiento_entre_tenants(org_a, org_b, actor):
    _, actor_b = _persona(org_b, "OPERACIONES")
    m02.crear(org=org_a, actor=actor, titulo="de A")
    for _ in range(5):
        m02.crear(org=org_b, actor=actor_b, titulo="de B")
    _caso(org_a); _caso(org_b); _caso(org_b)

    ra = I.indicadores(org_a)
    rb = I.indicadores(org_b)
    assert ra["actividades"]["total"]["valor"] == 1
    assert rb["actividades"]["total"]["valor"] == 5
    assert ra["casos"]["total"]["valor"] == 1
    assert rb["casos"]["total"]["valor"] == 2
    assert ra["organizacion"]["id"] == str(org_a.id)

    #  por HTTP, cada quien el suyo
    ug, g = _persona(org_a, "OPERACIONES")
    r = _cli(ug, org_a, g).get(URL_IND)
    assert r.status_code == 200
    assert r.data["actividades"]["total"]["valor"] == 1


# ==================================================== 15-16. filtros y periodo
@pytest.mark.django_db
def test_15_16_filtros_y_periodo(org_a):
    ahora = timezone.now()
    viejo = _caso(org_a)
    Case.objects.filter(pk=viejo.pk).update(created_at=ahora - timedelta(days=30))
    reciente = _caso(org_a)
    Case.objects.filter(pk=reciente.pk).update(created_at=ahora - timedelta(hours=2))

    r = I.indicadores_casos(org_a, ahora - timedelta(days=1), ahora, ahora)
    assert r["total"]["valor"] == 2, "el total no depende del periodo"
    assert r["en_periodo"]["valor"] == 1, "el periodo no filtró"
    assert r["en_periodo"]["periodo"]["desde"]

    ancho = I.indicadores_casos(org_a, ahora - timedelta(days=60), ahora, ahora)
    assert ancho["en_periodo"]["valor"] == 2

    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    r = cli.get(URL_IND, {"desde": (ahora - timedelta(days=1)).isoformat(),
                          "hasta": ahora.isoformat()})
    assert r.status_code == 200
    assert r.data["casos"]["en_periodo"]["valor"] == 1
    assert cli.get(URL_IND, {"desde": "ayer"}).status_code == 400
    assert cli.get(URL_REP, {"reporte": "inventado"}).status_code == 400


# ==================================================== 17. sin datos
@pytest.mark.django_db
def test_17_sin_datos_no_revienta_y_no_miente(org_a):
    r = I.indicadores(org_a)
    assert r["actividades"]["total"]["valor"] == 0
    assert r["casos"]["total"]["valor"] == 0
    assert r["programacion"]["ordenes_total"]["valor"] == 0
    assert r["supervisor"]["propuestas_total"]["valor"] == 0
    #  las derivadas sobre cero población son NO_APLICA, no 0
    assert r["casos"]["primera_respuesta_horas"]["estado"] == I.NO_APLICA
    assert r["sla"]["cumplimiento"]["estado"] == I.NO_APLICA
    assert r["programacion"]["capacidad"]["jornadas_evaluadas"] == 0


# ==================================================== 18. no crea nada
@pytest.mark.django_db
def test_18_generar_indicadores_no_crea_datos_de_negocio(org_a, actor):
    """
    Consultar no produce trabajo. Se mide sobre TODO lo que M11 podría tocar --
    y NO se usa el contador de common.Activity como única prueba: se comprueba
    fila por fila de las entidades específicas.
    """
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)
    _caso(org_a)

    def foto():
        return (
            list(ActividadOperativa.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado_operativo", "responsable_id", "updated_at")),
            list(OrdenTrabajo.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado_operativo", "programada_para",
                         "revision", "updated_at")),
            list(ProgramacionOrden.objects.filter(org=org_a).order_by("id")
                 .values("id", "dia", "secuencia", "estado", "updated_at")),
            list(P.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado", "revisado_por_id")),
            list(Case.objects.filter(org=org_a).order_by("id")
                 .values("id", "status", "resolved_at")),
            Activity.objects.filter(org=org_a).count(),
        )

    antes = foto()
    I.indicadores(org_a, ahora=ahora)
    for nombre in I.REPORTES:
        rep = I.reporte(org_a, nombre, ahora=ahora)
        assert rep["reporte"] == nombre
    assert foto() == antes, "generar indicadores creó o cambió datos"

    #  en particular, NO corrió el ciclo del Supervisor
    assert P.objects.filter(org=org_a).count() == 0


# ==================================================== 19. sin segunda cola
@pytest.mark.django_db
def test_19_no_hay_segunda_cola_ni_tabla_de_kpi(org_a):
    from django.apps import apps
    modelos = {m.__name__ for m in apps.get_app_config("operaciones").get_models()}
    #  02/10/2026: entran 'FuenteEstado' y 'FuenteSnapshot' con la capa de
    #  fuentes del Supervisor (bloque P2). NO son una cola nueva ni una segunda
    #  nocion de caso: una guarda el ESTADO de la ultima consulta a cada fuente
    #  --si se pudo preguntar, cuando, que tan viejo es el dato-- y la otra un
    #  resumen acotado para poder comparar un ciclo con el anterior.
    #
    #  Existen porque hoy "no hay nada" y "no se pudo preguntar" terminan en el
    #  mismo numero: de los 15 detectores del Supervisor, solo 2 habian disparado
    #  en produccion y los otros 13 leen tablas vacias devolviendo [].
    #
    #  El conjunto sigue siendo EXACTO a proposito: un modelo nuevo obliga a
    #  venir aqui y declararlo.
    #  02/10/2026, bloque P3: entran las cuatro de Situacion Operativa. NO son
    #  una cola nueva ni una segunda nocion de caso -- son la agrupacion
    #  sostenida de señales, que hoy no existia en ninguna parte: una situacion
    #  puede tener cero tickets y seguir siendo valida, que es el punto.
    #
    #  El conjunto sigue siendo EXACTO: un modelo nuevo obliga a venir aqui.
    assert modelos == {"ActividadOperativa", "DisponibilidadTecnico",
                       "ProgramacionSemanal", "ProgramacionOrden",
                       "NovedadOperativa", "PropuestaSupervisor",
                       "FuenteEstado", "FuenteSnapshot",
                       "SituacionOperativa", "SituacionAfectado",
                       "SituacionEvento", "SituacionRelacion",
                       #  02/10/2026, paso P4. 'DecisionSupervisor' guarda que
                       #  decidio una persona y QUE RESULTADO tuvo -- lo segundo
                       #  no existia en ninguna parte, y sin el las metricas de
                       #  aceptacion miden obediencia y no acierto.
                       #  'NivelAutonomia' hace del nivel 0-4 un dato POR EMPRESA
                       #  con su historial, en vez de la constante
                       #  'NIVEL_MAXIMO_ETAPA' del codigo. Los cinco niveles NO se
                       #  redefinen: son los de 'PropuestaSupervisor.NIVELES'.
                       "DecisionSupervisor", "NivelAutonomia",
                       #  05/10/2026, paso P5. El chat del Supervisor. NO
                       #  reemplaza 'asistente.conversations' del motor: esa es
                       #  la conversacion de WhatsApp con un CLIENTE FINAL, con
                       #  su ventana de 24 h, su relevo IA-humano y su cierre por
                       #  plazo. Esto es un colaborador hablando con el
                       #  Supervisor, y referencia una SituacionOperativa -- que
                       #  vive de este lado de la frontera, porque el motor no
                       #  lee las tablas del CRM.
                       "ConversacionSupervisor", "MensajeSupervisor",
                       #  05/10/2026, paso P8.2. 'AprendizajeSupervisor' guarda lo que se supo
                       #  DESPUES, con su evidencia y quien lo concluyo. No es una segunda cola
                       #  de propuestas ni una tabla de KPI: no se consulta para decidir nada,
                       #  se escribe cuando alguien ya sabe que paso. Y es APPEND-ONLY, asi que
                       #  tampoco es un estado que se pueda editar.
                       #
                       #  'OrigenAprendizaje' no tiene 'supervisor': el agente no puede concluir
                       #  sobre su propio acierto, ni por el servicio ni por el ORM.
                       "AprendizajeSupervisor",
                       #  07/10/2026. 'RazonamientoSupervisor' es la constancia de lo que el
                       #  cerebro concluyo, y el ESTADO PREVIO contra el cual compararlo. NO es
                       #  una cola: no se consulta para decidir nada, nadie la lee para proponer
                       #  y ningun detector depende de ella -- si desapareciera, el ciclo
                       #  produciria exactamente las mismas propuestas. Y NO es una tabla de KPI:
                       #  no guarda ningun indicador calculado, guarda la lectura cruda de la que
                       #  un indicador podria salir despues. Es APPEND-ONLY, como
                       #  'AprendizajeSupervisor'.
                       #
                       #  POR QUE NO FUE UN CAMPO DE 'PropuestaSupervisor': un campo nuevo
                       #  obligaria a agregarlo a 'CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR', que es la
                       #  garantia que 'test_m09f' vigila y la que mantiene fuera a
                       #  'observaciones' y 'responsable_sugerido' desde M09-C. Una tabla aparte
                       #  da lo mismo sin pagar con gobernanza.
                       #
                       #  Tampoco es una segunda nocion de caso: apunta a una propuesta o a una
                       #  situacion que ya existen, y la restriccion
                       #  'razonamiento_apunta_a_algo' impide que exista sin una de las dos.
                       "RazonamientoSupervisor",
                       #  07/10/2026. 'EstiloSupervisor' es la MITAD EDITABLE del prompt del
                       #  Supervisor: tono, largo y que mostrar, por empresa y con historial.
                       #  NO es una cola ni una tabla de KPI: no se consulta para decidir nada,
                       #  solo se lee al componer el prompt de un turno. Y NO guarda el nucleo
                       #  --las garantias siguen en codigo-- porque el chat usa 'razonar' y no
                       #  'concluir', asi que ahi el "jamas inventas" lo sostiene el texto.
                       #
                       #  Entra por §3.3 de CLAUDE.md: lo que varia por empresa es configuracion
                       #  editable, no un valor fijo en codigo. Append-only, como las demas.
                       "EstiloSupervisor"}

    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(indicadores))
    usados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            usados.add(nodo.attr)
    #  ninguna escritura: ni create, ni save, ni update, ni delete
    assert usados.isdisjoint({"create", "save", "update", "delete",
                              "bulk_create", "get_or_create",
                              "correr_ciclo", "registrar_propuesta",
                              "asistir", "registrar"}), sorted(
        usados & {"create", "save", "update", "delete", "correr_ciclo"})


# ==================================================== reportes
@pytest.mark.django_db
def test_reportes_traen_el_sobre_completo(org_a, actor):
    ahora = timezone.now()
    _calendario(org_a)
    m02.crear(org=org_a, actor=actor, titulo="x")
    _caso(org_a)

    for nombre in I.REPORTES:
        r = I.reporte(org_a, nombre, ahora=ahora)
        for k in ("reporte", "organizacion", "generado_en", "periodo",
                  "filtros", "fuentes", "metricas", "datos_insuficientes",
                  "cobertura_completa", "observaciones"):
            assert k in r, f"{nombre}: falta {k}"
        assert r["fuentes"], nombre
        assert isinstance(r["datos_insuficientes"], list)

    with pytest.raises(ValueError, match="no es un reporte"):
        I.reporte(org_a, "inventado")


@pytest.mark.django_db
def test_el_reporte_junta_lo_que_no_se_pudo_calcular(org_a):
    """
    Quien lee tiene que ver de una vez qué parte del reporte no se puede usar,
    sin inspeccionar indicador por indicador.
    """
    ahora = timezone.now()
    r = I.reporte(org_a, I.DIARIO, ahora=ahora)
    assert r["cobertura_completa"] is False
    rutas = {x["indicador"] for x in r["datos_insuficientes"]}
    assert any("primera_respuesta_horas" in x for x in rutas)
    assert any("cumplimiento" in x for x in rutas)
    for x in r["datos_insuficientes"]:
        assert x["estado"] in (I.DATOS_INSUFICIENTES, I.NO_APLICA)
        assert x["motivo"]


@pytest.mark.django_db
def test_las_observaciones_dicen_lo_que_los_numeros_no_prueban(org_a):
    ahora = timezone.now()
    pend = I.reporte(org_a, I.PENDIENTES, ahora=ahora)
    assert any("NO significa que alguien" in o for o in pend["observaciones"])
    prog = I.reporte(org_a, I.PROGRAMACION, ahora=ahora)
    assert any("no es cero" in o for o in prog["observaciones"])
    sup = I.reporte(org_a, I.SUPERVISOR, ahora=ahora)
    assert any("acciones_propuestas" in o for o in sup["observaciones"]), (
        "no separó el histórico del motor de PropuestaSupervisor")


# ==================================================== API y permisos
@pytest.mark.django_db
def test_api_permisos_y_forma(org_a, actor):
    _calendario(org_a)
    m02.crear(org=org_a, actor=actor, titulo="x")
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)

    r = cli.get(URL_IND)
    assert r.status_code == 200
    for k in ("organizacion", "generado_en", "periodo", "casos", "sla",
              "actividades", "compromisos", "programacion", "supervisor"):
        assert k in r.data, k

    r = cli.get(URL_REP, {"reporte": "programacion"})
    assert r.status_code == 200 and r.data["reporte"] == "programacion"
    assert cli.get(URL_REP).data["reporte"] == "diario"

    #  un técnico no consulta indicadores
    ut, t = _persona(org_a, "USER")
    assert _cli(ut, org_a, t).get(URL_IND).status_code == 403
    assert _cli(ut, org_a, t).get(URL_REP).status_code == 403


@pytest.mark.django_db
def test_sin_efectos_externos(org_a, actor):
    _calendario(org_a)
    m02.crear(org=org_a, actor=actor, titulo="x")
    _caso(org_a)

    salidas = []
    original = socket.socket.connect

    def espia(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("pg-m11", "127.0.0.1", "localhost", "::1"):
            salidas.append(host)
        return original(self, addr, *a, **k)

    socket.socket.connect = espia
    try:
        try:
            s = socket.socket(); s.settimeout(1)
            s.connect(("example.invalid", 80))
        except Exception:
            pass
        assert salidas, "el espía no dispara: su cero no probaría nada"
        salidas.clear()
        I.indicadores(org_a)
        for nombre in I.REPORTES:
            I.reporte(org_a, nombre)
    finally:
        socket.socket.connect = original

    assert salidas == [], f"hubo llamadas externas: {salidas}"
