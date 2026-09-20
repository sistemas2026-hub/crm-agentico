# -*- coding: utf-8 -*-
"""
================================================================================
 M09-J  --  estado explicito y contexto operativo en los asistentes
================================================================================

M09-M dejo los dos asistentes funcionando. Lo que este bloque agrega es lo que
faltaba para poder LEER una recomendacion sin tener que abrir la fila:

  * el ESTADO de la actividad, en sus DOS ejes y sin aplanar;
  * el CONTEXTO del plan de la orden -- jornada, secuencia, novedades.

Lo que se verifica aca no es que los campos existan, sino las confusiones que
existen para evitar:

    ejecutado  !=  validado          (y donde de verdad ocurre: la dependencia)
    bloqueado  !=  no realizado      (la causa es lo que los separa)
    completada !=  cerrada
    plan leido !=  plan recalculado

Y que nada de esto convirtio al asistente en algo que escribe.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from business_hours.models import BusinessCalendar
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import actividades as m02
from operaciones import asistentes as A
from operaciones import capacidad
from operaciones.models import (ActividadOperativa, APROBADO,
                                NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal, PropuestaSupervisor,
                                REQUIERE_CORRECCION, VALIDACION_PENDIENTE)
from operaciones.programacion import programar_orden
from operaciones.supervisor import Senal

P = PropuestaSupervisor
ACT = ActividadOperativa
RUTA = "/api/operaciones/asistentes/"

_n = [9100]
_c = [0]


def _hoy():
    return timezone.localtime(timezone.now()).date()


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"j{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


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
    wt = WorkType.objects.create(org=org, codigo=f"j_{_n[0]}", nombre="j")
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
    #  Un dia de ESTA semana, siempre: 'programacion_sin_publicar' exige
    #  'semana_inicio <= hoy', y programar "manana" hace que la prueba dependa
    #  del dia en que se corra (en domingo, manana abre otra semana).
    dia = dia or _hoy()
    plan, _ = ProgramacionSemanal.objects.get_or_create(
        org=org, semana_inicio=dia - timedelta(days=dia.weekday()),
        defaults={"estado": ProgramacionSemanal.BORRADOR})
    return programar_orden(
        org=org, orden=orden, programacion=plan, actor=actor,
        programada_para=timezone.make_aware(datetime.combine(dia, time(hora, 0))))


def _de_actividad(salida):
    return [r for r in salida["recomendaciones"] if r["origen_tipo"] == "actividad"]


def _de_orden(salida):
    return [r for r in salida["recomendaciones"] if r["origen_tipo"] == "orden_trabajo"]


# ============================================== 1. los dos ejes, sin aplanar
@pytest.mark.django_db
def test_el_estado_viaja_en_dos_ejes_y_no_en_uno(org_a, actor):
    """
    'validacion_pendiente' NO es un octavo estado operativo. El modelo lo dice
    donde los declara, y el asistente tiene que reflejarlo igual: si los
    aplanara habria que elegir, y se perderia "completada + requiere
    correccion", que es lo que produce una devolucion.
    """
    a = m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    m02.bloquear(a, actor=actor, motivo="falta material en bodega")

    filas = _de_actividad(A.asistir(org_a, A.COMPROMISOS))
    assert filas, "la actividad bloqueada deberia producir alguna señal"
    e = filas[0]["estado"]

    #  dos claves distintas, no una
    assert e["operativo"] == ACT.BLOQUEADA
    assert e["operativo_etiqueta"] == "Bloqueada"
    assert "validacion" in e and "operativo" in e
    #  y la etiqueta sale del modelo, no de un catalogo copiado aca
    assert e["validacion_etiqueta"] == dict(
        __import__("operaciones.models", fromlist=["x"]).ESTADOS_VALIDACION
    )[e["validacion"]]


@pytest.mark.django_db
def test_bloqueada_no_es_no_realizada(org_a, actor):
    """
    Lo que separa "no se pudo, por esto" de "no se hizo" es la causa. Si el
    asistente no la trae, el lector no puede distinguirlas.
    """
    a = m02.crear(org=org_a, actor=actor, titulo="con causa")
    m02.bloquear(a, actor=actor, motivo="el cliente no autoriza el ingreso")

    filas = _de_actividad(A.asistir(org_a, A.COMPROMISOS))
    con_causa = [f for f in filas if f["estado"]["operativo"] == ACT.BLOQUEADA]
    assert con_causa
    assert con_causa[0]["estado"]["motivo_bloqueo"] == "el cliente no autoriza el ingreso"


@pytest.mark.django_db
def test_los_estados_que_el_supervisor_ve_se_reportan_tal_cual(org_a, actor):
    """
    Se recorren los estados NO finales y se comprueba que el asistente devuelve
    el mismo valor que tiene la fila -- sin traducir ni agrupar.
    """
    ahora = timezone.now()
    vistos = {}
    for titulo, mover in (
        ("pendiente", lambda x: None),
        ("en gestion", lambda x: m02.iniciar_gestion(x, actor=actor)),
        ("en espera", lambda x: m02.poner_en_espera(x, actor=actor)),
        ("escalada", lambda x: m02.escalar(x, actor=actor, motivo="sin respuesta")),
    ):
        a = m02.crear(org=org_a, actor=actor, titulo=titulo,
                      vence_en=ahora - timedelta(hours=3))
        mover(a)
        a.refresh_from_db()
        vistos[str(a.id)] = a.estado_operativo

    for fila in _de_actividad(A.asistir(org_a, A.COMPROMISOS, ahora)):
        esperado = vistos.get(fila["origen_id"])
        if esperado:
            assert fila["estado"]["operativo"] == esperado, fila["origen_id"]

    #  y el reparto del resumen cuenta lo mismo que se leyo
    salida = A.asistir(org_a, A.COMPROMISOS, ahora, registrar=False)
    reparto = salida["resumen"]["por_estado"]
    for fila in _de_actividad(salida):
        assert fila["estado"]["operativo"] in reparto
    assert sum(reparto.values()) == len(_de_actividad(salida))


# ============================================== 2. ejecutado != validado
@pytest.mark.django_db
def test_una_dependencia_completada_sin_validar_no_se_presenta_como_cerrada(
        org_a, actor):
    """
    LA confusion que este bloque existe para evitar.

    La previa esta COMPLETADA, asi que 'resuelta' es True -- y esta bien: es el
    eje operativo. Pero su validacion sigue pendiente y puede volver con
    'requiere_correccion'. Si el asistente solo dijera 'resuelta', quien lee la
    recomendacion creeria que ese camino ya esta cerrado.
    """
    previa = m02.crear(org=org_a, actor=actor, titulo="previa")
    siguiente = m02.crear(org=org_a, actor=actor, titulo="siguiente",
                          vence_en=timezone.now() - timedelta(hours=2))
    m02.establecer_dependencia(siguiente, actor=actor, depende_de=previa)
    m02.completar(previa, actor=actor, requiere_validacion=True)
    previa.refresh_from_db()
    assert previa.estado_validacion == VALIDACION_PENDIENTE

    salida = A.asistir(org_a, A.COMPROMISOS, registrar=False)
    deps = [d for f in salida["recomendaciones"] for d in f["dependencias"]
            if d["actividad"] == str(previa.id)]
    assert deps, "la dependencia deberia viajar en la recomendacion"
    d = deps[0]

    assert d["resuelta"] is True           # eje operativo
    assert d["validada"] is False          # eje de validacion
    assert d["ejecutada_sin_validar"] is True
    assert salida["resumen"]["dependencias_ejecutadas_sin_validar"] >= 1


@pytest.mark.django_db
def test_validada_de_verdad_no_cuenta_como_pendiente(org_a, actor):
    """El contrario del anterior: si se aprobo, deja de contarse. Sin esto, el
    contador anterior podria estar siempre encendido y no probaria nada."""
    previa = m02.crear(org=org_a, actor=actor, titulo="previa ok")
    siguiente = m02.crear(org=org_a, actor=actor, titulo="siguiente",
                          vence_en=timezone.now() - timedelta(hours=2))
    m02.establecer_dependencia(siguiente, actor=actor, depende_de=previa)
    m02.completar(previa, actor=actor, requiere_validacion=True)
    m02.validar(previa, actor=actor, decision=APROBADO)
    previa.refresh_from_db()
    assert previa.estado_validacion == APROBADO

    salida = A.asistir(org_a, A.COMPROMISOS, registrar=False)
    deps = [d for f in salida["recomendaciones"] for d in f["dependencias"]
            if d["actividad"] == str(previa.id)]
    assert deps
    assert deps[0]["validada"] is True
    assert deps[0]["ejecutada_sin_validar"] is False
    assert salida["resumen"]["dependencias_ejecutadas_sin_validar"] == 0


@pytest.mark.django_db
def test_una_devolucion_reabre_y_la_dependencia_deja_de_estar_resuelta(
        org_a, actor):
    """
    Medido, no supuesto: 'validar(REQUIERE_CORRECCION)' NO deja
    "completada + requiere correccion". Devuelve la actividad a EN_GESTION,
    limpia 'completado_en' y sube 'vuelta' -- lo dice el propio M02.

    Asi que el efecto sobre la dependencia es el contrario del que uno
    esperaria: deja de estar resuelta. Por eso este asistente no puede leer
    'resuelta' una vez y guardarsela: un camino que parecia cerrado se
    reabrio, y la recomendacion tiene que reflejarlo.
    """
    previa = m02.crear(org=org_a, actor=actor, titulo="devuelta")
    siguiente = m02.crear(org=org_a, actor=actor, titulo="siguiente",
                          vence_en=timezone.now() - timedelta(hours=2))
    m02.establecer_dependencia(siguiente, actor=actor, depende_de=previa)
    m02.completar(previa, actor=actor, requiere_validacion=True)

    antes = [d for f in A.asistir(org_a, A.COMPROMISOS, registrar=False)["recomendaciones"]
             for d in f["dependencias"] if d["actividad"] == str(previa.id)]
    assert antes and antes[0]["resuelta"] is True

    m02.validar(previa, actor=actor, decision=REQUIERE_CORRECCION,
                motivo="falta la foto del cierre")
    previa.refresh_from_db()
    assert previa.estado_operativo == ACT.EN_GESTION
    assert previa.completado_en is None

    despues = [d for f in A.asistir(org_a, A.COMPROMISOS, registrar=False)["recomendaciones"]
               for d in f["dependencias"] if d["actividad"] == str(previa.id)]
    assert despues
    d = despues[0]
    assert d["estado_validacion"] == REQUIERE_CORRECCION
    assert d["validada"] is False
    assert d["resuelta"] is False, "la devolucion reabrio el trabajo"
    #  y ya no es "ejecutada": el trabajo volvio a gestion
    assert d["ejecutada_sin_validar"] is False


# ============================================== 3. contexto del plan
@pytest.mark.django_db
def test_el_plan_se_lee_no_se_recalcula(org_a, actor):
    """
    Secuencia y prioridad salen de la fila. Un asistente que las recalcula
    mientras las describe deja de servir para contrastar el plan.

    Se prueba la funcion directamente, con una señal construida: una orden YA
    programada no dispara 'orden_sin_programar' -- y la señal de un plan en
    borrador es de la SEMANA ('programacion_semanal'), no de la orden. Montar
    el caso por el camino largo probaria el detector, no el contexto.
    """
    _calendario(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)
    NovedadOperativa.objects.create(
        org=org_a, tipo=NovedadOperativa.FALTA_MATERIAL, orden=o,
        descripcion="no hay ONT en bodega", registrada_por=actor)

    linea = ProgramacionOrden.objects.get(orden=o)
    ProgramacionOrden.objects.filter(pk=linea.pk).update(secuencia=7, prioridad=3)
    linea.refresh_from_db()

    senal = Senal(tipo=P.ORDEN_SIN_PROGRAMAR, origen_tipo="orden_trabajo",
                  origen_id=str(o.id))
    ctx = A._contexto_operativo(senal)

    plan = ctx["programacion"]
    assert plan["secuencia"] == 7
    assert plan["prioridad"] == 3
    assert plan["dia"] == str(linea.dia)
    assert plan["semana"] == str(linea.programacion.semana_inicio)
    assert plan["plan_publicado"] is False     # sigue en borrador

    #  Sin la novedad, "sigue sin ejecutarse" se lee como desidia cuando puede
    #  ser una falta de material que alguien ya reporto.
    novedades = ctx["novedades"]
    assert any(n["tipo"] == NovedadOperativa.FALTA_MATERIAL for n in novedades)
    assert any("ONT" in n["descripcion"] for n in novedades)


@pytest.mark.django_db
def test_el_contexto_llega_hasta_la_salida_del_asistente(org_a, actor):
    """
    El camino completo, con una orden SIN programar -- que es la que si produce
    una señal de 'orden_trabajo'. Sin plan vigente no hay clave 'programacion',
    y eso es correcto: no se inventa un plan que no existe.
    """
    _calendario(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    NovedadOperativa.objects.create(
        org=org_a, tipo=NovedadOperativa.BLOQUEO, orden=o,
        descripcion="calle cerrada por obra", registrada_por=actor)

    filas = _de_orden(A.asistir(org_a, A.PROGRAMACION, registrar=False))
    assert filas, "una orden sin programar deberia producir señal"
    ctx = filas[0]["contexto"]
    assert "programacion" not in ctx, "no hay plan: no debe inventarse uno"
    assert any(n["tipo"] == NovedadOperativa.BLOQUEO
               for n in ctx.get("novedades", []))


@pytest.mark.django_db
def test_una_orden_no_finge_tener_los_ejes_de_una_actividad(org_a, actor):
    """
    'estado' es None para una orden. Devolver un estado vacio inventaria una
    forma comun que no existe: una orden no tiene eje de validacion de
    actividad.
    """
    _calendario(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)

    for fila in _de_orden(A.asistir(org_a, A.PROGRAMACION, registrar=False)):
        assert fila["estado"] is None
    #  y al reves: una actividad no trae contexto de plan
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    for fila in _de_actividad(A.asistir(org_a, A.COMPROMISOS, registrar=False)):
        assert fila["contexto"] == {}


@pytest.mark.django_db
def test_si_la_fila_ya_no_existe_se_dice(org_a, actor):
    """Callar un dato que no se pudo leer produce una salida que parece
    completa. Se devuelve la nota, no None."""
    a = m02.crear(org=org_a, actor=actor, titulo="se va a borrar",
                  vence_en=timezone.now() - timedelta(hours=2))
    senales = [s for s in
               __import__("operaciones.supervisor", fromlist=["x"]).detectar(org_a)
               if s.origen_id == str(a.id)]
    assert senales
    ActividadOperativa.objects.filter(pk=a.pk).delete()

    estado = A._estado_de(senales[0])
    assert estado is not None
    assert estado["nota"] == "la actividad ya no existe"
    assert estado["ejecutada"] is None


# ============================================== 4. lo que NO debe pasar
@pytest.mark.django_db
def test_el_contexto_nuevo_no_ejecuta_nada(org_a, actor):
    """Se mide sobre TODO lo que estos campos nuevos leen."""
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=timezone.now() - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)
    NovedadOperativa.objects.create(
        org=org_a, tipo=NovedadOperativa.BLOQUEO, orden=o,
        descripcion="calle cerrada", registrada_por=actor)

    def foto():
        return (
            list(ActividadOperativa.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado_operativo", "estado_validacion",
                         "motivo_bloqueo", "updated_at")),
            list(ProgramacionOrden.objects.filter(org=org_a).order_by("id")
                 .values("id", "dia", "secuencia", "prioridad", "estado",
                         "updated_at")),
            list(ProgramacionSemanal.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado", "updated_at")),
            list(NovedadOperativa.objects.filter(org=org_a).order_by("id")
                 .values("id", "tipo", "descripcion", "updated_at")),
        )

    antes = foto()
    A.asistir(org_a, A.PROGRAMACION)
    A.asistir(org_a, A.COMPROMISOS)
    assert foto() == antes, "el asistente modificó datos operativos"


@pytest.mark.django_db
def test_el_estado_no_se_cuela_entre_organizaciones(org_a, org_b, actor):
    """El contexto y el estado se leen por fila; la fila es de una org."""
    actor_b = _persona(org_b, "OPERACIONES")[1]
    m02.crear(org=org_a, actor=actor, titulo="de A", vence_en=timezone.now() - timedelta(hours=2))
    m02.crear(org=org_b, actor=actor_b, titulo="de B", vence_en=timezone.now() - timedelta(hours=2))

    ids_b = {str(x) for x in
             ActividadOperativa.objects.filter(org=org_b).values_list("id", flat=True)}
    salida = A.asistir(org_a, A.COMPROMISOS, registrar=False)
    for fila in salida["recomendaciones"]:
        assert fila["origen_id"] not in ids_b
    assert salida["organizacion"]["id"] == str(org_a.id)


@pytest.mark.django_db
def test_la_ruta_sigue_exigiendo_permiso(org_a):
    """Los campos nuevos viajan por la misma ruta, con el mismo permiso."""
    u, p = _persona(org_a, "USER")          # no es Jefe de Operaciones
    r = _cli(u, org_a, p).post(RUTA, {"dominio": "compromiso"}, format="json")
    assert r.status_code in (401, 403), r.status_code


@pytest.mark.django_db
def test_la_api_devuelve_los_campos_nuevos(org_a, actor):
    """La vista no filtra: lo que produce el asistente es lo que sale."""
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    u, p = _persona(org_a, "OPERACIONES")
    r = _cli(u, org_a, p).post(RUTA, {"dominio": "compromiso"}, format="json")
    assert r.status_code == 200, r.data
    assert "por_estado" in r.data["resumen"]
    assert "dependencias_ejecutadas_sin_validar" in r.data["resumen"]
    for fila in r.data["recomendaciones"]:
        assert "estado" in fila and "contexto" in fila


@pytest.mark.django_db
def test_datos_insuficientes_no_gana_una_recomendacion_por_traer_estado(
        org_a, actor, monkeypatch):
    """
    Traer el estado no debe volver "suficiente" un caso que no lo es: si el
    Supervisor no sabe analizar la señal, sigue sin haber recomendacion ni
    propuesta, aunque ahora haya mas campos poblados.
    """
    from operaciones import supervisor
    monkeypatch.setattr(supervisor, "analizar", lambda senal: None)
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")

    antes = P.objects.filter(org=org_a).count()
    salida = A.asistir(org_a, A.COMPROMISOS)
    assert salida["resumen"]["datos_insuficientes"] > 0
    assert P.objects.filter(org=org_a).count() == antes
    for fila in salida["recomendaciones"]:
        assert fila["resultado"] == A.DATOS_INSUFICIENTES
        assert fila["recomendacion"] == ""
        #  pero el estado SI viaja: es observado, no inferido
        assert fila["estado"] is not None


@pytest.mark.django_db
def test_la_deduplicacion_sigue_valiendo_con_los_campos_nuevos(org_a, actor):
    """Segunda pasada: el hecho sigue, la propuesta no se repite."""
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    primera = A.asistir(org_a, A.COMPROMISOS)
    creadas = P.objects.filter(org=org_a).count()
    assert primera["resumen"]["propuestas_creadas"] > 0

    segunda = A.asistir(org_a, A.COMPROMISOS)
    assert P.objects.filter(org=org_a).count() == creadas
    assert segunda["resumen"]["repetidas"] > 0
    #  y la repetida conserva el estado: se sigue pudiendo leer
    for fila in segunda["recomendaciones"]:
        if fila["resultado"] == A.REPETIDA:
            assert fila["estado"] is not None


@pytest.mark.django_db
def test_toda_recomendacion_sigue_llevando_evidencia_y_revision(org_a, actor):
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    for fila in A.asistir(org_a, A.COMPROMISOS)["recomendaciones"]:
        assert fila["evidencia"], "una recomendacion sin evidencia"
        assert fila["requiere_revision_humana"] is True


@pytest.mark.django_db
def test_no_se_importo_ningun_servicio_de_escritura_nuevo(org_a):
    """
    El delta agrego lecturas. Se vuelve a medir con AST que no entro ningun
    servicio de escritura por la puerta de atras.
    """
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(A))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, ast.alias):
            nombres.add((nodo.asname or nodo.name).split(".")[0])
    assert nombres.isdisjoint({
        "programar_orden", "reprogramar_orden", "registrar_contingencia",
        "actualizar_secuencia", "secuenciar_jornada", "publicar_programacion",
        "asignar", "agregar_integrante", "cambiar_principal", "desasignar",
        "completar", "cancelar", "bloquear", "validar", "crear", "escalar",
        "requests", "httpx", "urllib", "celery", "apply_async", "shared_task",
    }), sorted(nombres & {"completar", "validar", "bloquear", "crear"})
