# -*- coding: utf-8 -*-
"""
================================================================================
 M04-A (2/2)  --  detectores de plazo operativo
================================================================================

El servicio ya sabia calcular el plazo. Esto lo convierte en una senal que el
Supervisor puede proponer, y lo que se verifica es lo que un detector de SLA
hace mal cuando nadie mira:

  * proponer sobre un plazo que nadie declaro (SIN_PLAZO -> silencio);
  * repetir la propuesta cada ciclo porque el atraso crecio un minuto;
  * avisar con la misma antelacion un trabajo de 2 h y uno de 5 dias;
  * escribir "incumplio" donde solo se midio tiempo.

La ventana es min(24 h, 20% del plazo): un umbral fijo hace que todo trabajo
corto nazca ya avisado.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from business_hours.models import BusinessCalendar
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Profile, User
from operaciones import asistentes as A
from operaciones import sla, supervisor
from operaciones.capacidad import CLAVE_DURACION
from operaciones.models import PropuestaSupervisor as P

_n = [9700]
_c = [0]
MARTES_9 = datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("UTC"))


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"d{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _calendario(org, abre=time(8, 0), cierra=time(16, 0), tz="UTC", dias=None):
    cal = BusinessCalendar.objects.create(org=org, name="Default", timezone=tz,
                                          is_default=True)
    dias = dias or ("monday", "tuesday", "wednesday", "thursday", "friday",
                    "saturday", "sunday")
    for d in dias:
        setattr(cal, f"{d}_open", abre)
        setattr(cal, f"{d}_close", cierra)
    cal.save()
    return cal


def _orden(org, duracion=None, creada=MARTES_9, estado=OrdenTrabajo.ASIGNADA):
    _n[0] += 1
    wt = WorkType.objects.create(org=org, codigo=f"d_{_n[0]}", nombre="d")
    esquema = {"campos": [], "evidencias": []}
    if duracion is not None:
        esquema[CLAVE_DURACION] = duracion
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    o = OrdenTrabajo.objects.create(
        org=org, numero=_n[0], tipo_trabajo_version=v,
        cliente_nombre=f"C{_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=estado)
    OrdenTrabajo.objects.filter(pk=o.pk).update(created_at=creada)
    o.refresh_from_db()
    return o


def _senales(org, ahora, tipo):
    return [s for s in supervisor.detectar(org, ahora) if s.tipo == tipo]


# ============================================== emisión
@pytest.mark.django_db
def test_ot_vencida_genera_propuesta(org_a, actor):
    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5))

    rec = [r for r in salida["recomendaciones"]
           if r["senal_origen"] == P.ORDEN_SLA_VENCIDO and r["origen_id"] == str(o.id)]
    assert rec, "la orden vencida no produjo señal"
    r = rec[0]
    assert r["resultado"] == A.PROPUESTA
    assert r["propuesta_id"]
    assert r["habilidad"]["id"] == "H-11"
    assert r["habilidad"]["estado"] == "vigente"
    assert r["requiere_revision_humana"] is True

    prop = P.objects.get(id=r["propuesta_id"])
    assert prop.tipo_senal == P.ORDEN_SLA_VENCIDO
    assert prop.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR


@pytest.mark.django_db
def test_la_evidencia_explica_la_senal_de_vencida(org_a, actor):
    """Los siete hechos que piden explicar la propuesta."""
    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    s = _senales(org_a, MARTES_9 + timedelta(hours=5), P.ORDEN_SLA_VENCIDO)
    assert s
    texto = " ".join(x["dato"] for x in s[0].evidencia)

    assert f"#{o.numero}" in texto                  # la OT
    assert "plazo declarado: 120" in texto          # duracion objetivo
    assert "se cuenta desde" in texto               # ancla
    assert "limite:" in texto                       # limite
    assert "atraso:" in texto                       # minutos de atraso
    assert "calendario laboral usado" in texto      # calendario
    assert str(o.tipo_trabajo_version_id) in str(s[0].evidencia)   # tipo de trabajo


@pytest.mark.django_db
def test_ot_por_vencer_genera_propuesta_con_ventana(org_a, actor):
    _calendario(org_a)
    o = _orden(org_a, duracion=120)          # ventana = 24 min
    #  limite 11:00; a las 10:45 quedan 15 min < 24 min
    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(minutes=105))

    rec = [r for r in salida["recomendaciones"]
           if r["senal_origen"] == P.ORDEN_SLA_POR_VENCER and r["origen_id"] == str(o.id)]
    assert rec, "no aviso antes del limite"
    s = _senales(org_a, MARTES_9 + timedelta(minutes=105), P.ORDEN_SLA_POR_VENCER)[0]
    assert s.datos["minutos_restantes"] == 15
    assert s.datos["limite"]
    assert round(s.datos["ventana_horas"], 4) == 0.4       # 24 minutos
    assert s.datos["ventana_fraccion"] == 0.20
    assert rec[0]["habilidad"]["id"] == "H-12"


# ============================================== silencio
@pytest.mark.django_db
@pytest.mark.parametrize("caso,duracion,estado,ahora_delta", [
    ("a tiempo",             2400, OrdenTrabajo.ASIGNADA, timedelta(minutes=10)),
    ("sin plazo",            None, OrdenTrabajo.ASIGNADA, timedelta(days=30)),
    ("duracion invalida",    "90", OrdenTrabajo.ASIGNADA, timedelta(days=30)),
    ("terminada (cerrada)",   120, OrdenTrabajo.CERRADA,  timedelta(days=30)),
    ("terminada (cancelada)", 120, OrdenTrabajo.CANCELADA, timedelta(days=30)),
])
def test_no_hay_senal_de_sla_cuando_no_corresponde(org_a, caso, duracion,
                                                   estado, ahora_delta):
    """
    SIN_PLAZO, NO_APLICA y DATOS_INSUFICIENTES NO producen propuesta. Una
    recomendacion apoyada en un plazo que nadie declaro seria inventar el
    compromiso y despues reclamarlo.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=duracion, estado=estado)
    ahora = MARTES_9 + ahora_delta
    for tipo in (P.ORDEN_SLA_VENCIDO, P.ORDEN_SLA_POR_VENCER):
        s = [x for x in _senales(org_a, ahora, tipo) if x.origen_id == str(o.id)]
        assert not s, f"{caso}: emitio {tipo}"


# ============================================== deduplicación
@pytest.mark.django_db
@pytest.mark.parametrize("tipo,delta", [
    (P.ORDEN_SLA_VENCIDO, timedelta(hours=5)),
    (P.ORDEN_SLA_POR_VENCER, timedelta(minutes=105)),
])
def test_deduplicacion(org_a, actor, tipo, delta):
    """
    Segunda pasada: el hecho sigue, la propuesta no se repite. Y a los diez
    minutos tampoco, aunque el atraso haya crecido -- la huella no lleva los
    minutos, justamente para eso.
    """
    _calendario(org_a)
    _orden(org_a, duracion=120)

    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + delta)
    n1 = P.objects.filter(org=org_a, tipo_senal=tipo).count()
    assert n1 == 1, f"no se creo la propuesta de {tipo}"

    segunda = A.asistir(org_a, A.PROGRAMACION, MARTES_9 + delta + timedelta(minutes=10))
    assert P.objects.filter(org=org_a, tipo_senal=tipo).count() == n1
    assert any(r["resultado"] == A.REPETIDA
               for r in segunda["recomendaciones"] if r["senal_origen"] == tipo)


# ============================================== la ventana
@pytest.mark.django_db
@pytest.mark.parametrize("minutos,horas_esperadas", [
    (120,    0.4),     # 2 h  -> 24 min
    (600,    2.0),     # 10 h -> 2 h
    (1440,   4.8),     # 24 h -> 4,8 h
    (7200,  24.0),     # 5 dias -> tope
    (14400, 24.0),     # 10 dias -> sigue el tope
])
def test_la_ventana_es_proporcional_con_tope(minutos, horas_esperadas):
    """min(24 h, 20% del plazo). Sin base de datos: es aritmetica pura."""
    assert round(sla.ventana_de_aviso(minutos), 4) == horas_esperadas


@pytest.mark.django_db
def test_el_limite_exacto_de_la_ventana(org_a):
    """
    Justo en el borde cuenta como 'por vencer': la comparacion es <=. Se prueba
    el instante exacto y uno anterior, que es donde un '<' se delataria.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=120)            # limite 11:00, ventana 24 min
    borde = MARTES_9 + timedelta(minutes=96)   # 10:36 -> faltan exactamente 24
    assert sla.plazo_de(o, borde)["estado"] == sla.VENCE_PRONTO
    antes = MARTES_9 + timedelta(minutes=95, seconds=59)
    assert sla.plazo_de(o, antes)["estado"] == sla.A_TIEMPO


@pytest.mark.django_db
def test_un_trabajo_largo_no_se_avisa_con_el_tope_todo_el_tiempo(org_a):
    """
    La razon de ser de la ventana proporcional, al reves: con el umbral fijo
    de 24 h que se usaba antes, una orden de 2 h estaba SIEMPRE avisada. Ahora
    no: a mitad de camino esta A_TIEMPO.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    assert sla.plazo_de(o, MARTES_9 + timedelta(minutes=30))["estado"] == sla.A_TIEMPO


# ============================================== calendario y tiempo
@pytest.mark.django_db
def test_el_detector_respeta_el_cambio_de_dia_calendario(org_a):
    """Con jornada 8-16 y 5 h de plazo desde las 9, el limite cae al dia siguiente."""
    _calendario(org_a, abre=time(8, 0), cierra=time(12, 0))
    o = _orden(org_a, duracion=300)
    #  El mismo martes a las 15:00 NO esta vencida: el limite es el miercoles.
    assert not _senales(org_a, MARTES_9 + timedelta(hours=6), P.ORDEN_SLA_VENCIDO)
    #  El miercoles a las 11 tampoco (limite 10:00 del miercoles)... si lo esta.
    s = _senales(org_a, datetime(2026, 9, 16, 11, 0, tzinfo=ZoneInfo("UTC")),
                 P.ORDEN_SLA_VENCIDO)
    assert s, "no detecto el vencimiento del dia siguiente"


@pytest.mark.django_db
def test_el_timezone_del_calendario_cambia_lo_que_el_detector_ve(org_a):
    cal = _calendario(org_a, tz="America/Bogota")
    o = _orden(org_a, duracion=120)
    con_bogota = sla.plazo_de(o, MARTES_9)["limite"]
    BusinessCalendar.objects.filter(pk=cal.pk).update(timezone="UTC")
    assert sla.plazo_de(o, MARTES_9)["limite"] != con_bogota


@pytest.mark.django_db
def test_reprogramar_no_reinicia_la_senal(org_a, actor):
    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    ahora = MARTES_9 + timedelta(hours=5)
    antes = _senales(org_a, ahora, P.ORDEN_SLA_VENCIDO)[0]

    OrdenTrabajo.objects.filter(pk=o.pk).update(
        programada_para=MARTES_9 + timedelta(days=7))
    despues = _senales(org_a, ahora, P.ORDEN_SLA_VENCIDO)[0]
    assert despues.datos["limite"] == antes.datos["limite"]
    assert despues.huella == antes.huella


@pytest.mark.django_db
def test_cambiar_el_plan_no_reinicia_la_senal(org_a, actor):
    from operaciones.models import ProgramacionSemanal
    from operaciones.programacion import programar_orden

    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    ahora = MARTES_9 + timedelta(hours=5)
    antes = _senales(org_a, ahora, P.ORDEN_SLA_VENCIDO)[0]

    dia = timezone.localtime(timezone.now()).date()
    plan, _ = ProgramacionSemanal.objects.get_or_create(
        org=org_a, semana_inicio=dia - timedelta(days=dia.weekday()),
        defaults={"estado": ProgramacionSemanal.BORRADOR})
    programar_orden(org=org_a, orden=o, programacion=plan, actor=actor,
                    programada_para=timezone.make_aware(
                        datetime.combine(dia, time(9, 0))))
    despues = _senales(org_a, ahora, P.ORDEN_SLA_VENCIDO)[0]
    assert despues.datos["limite"] == antes.datos["limite"]


# ============================================== semántica
@pytest.mark.django_db
def test_el_texto_describe_tiempo_y_no_conducta(org_a, actor):
    """
    'vencido' no es 'incumplimiento'; 'atraso' no es 'culpa'. Se revisa el
    texto que de verdad va a la cola, no el del codigo.
    """
    _calendario(org_a)
    _orden(org_a, duracion=120)
    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5))

    prohibidas = ("culpa", "culpable", "incumpli", "negligen", "responsable de",
                  "no atendio", "no atendió", "abandono", "desidia", "sancion")
    for p in P.objects.filter(org=org_a, tipo_senal__in=(
            P.ORDEN_SLA_VENCIDO, P.ORDEN_SLA_POR_VENCER)):
        texto = f"{p.accion_propuesta} {p.motivo} {p.impacto}".lower()
        for mala in prohibidas:
            assert mala not in texto, f"{mala!r} en: {texto[:120]}"


# ============================================== A-1 / A-2 y no-ejecución
@pytest.mark.django_db
def test_a1_conserva_el_sla_y_los_contadores(org_a, actor):
    _calendario(org_a)
    _orden(org_a, duracion=120)
    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5),
                       registrar=False)
    assert salida["resumen"]["sla_vencidas"] >= 1
    for clave in ("sla_vencidas", "sla_por_vencer", "sla_sin_plazo"):
        assert clave in salida["resumen"]
    for r in salida["recomendaciones"]:
        assert "sla" in r


@pytest.mark.django_db
def test_a2_conserva_el_sla(org_a, actor):
    from operaciones import actividades as m02

    _calendario(org_a)
    o = _orden(org_a, duracion=120)
    m02.crear(org=org_a, actor=actor, titulo="revisar",
              origen_tipo="orden_trabajo", origen_id=str(o.id),
              vence_en=MARTES_9 - timedelta(hours=2))
    salida = A.asistir(org_a, A.COMPROMISOS, MARTES_9 + timedelta(hours=5),
                       registrar=False)
    con_sla = [r for r in salida["recomendaciones"] if r["sla"]]
    assert con_sla, "A-2 dejo de seguir el vinculo hacia la orden"
    assert con_sla[0]["sla"]["estado"] == sla.VENCIDA


@pytest.mark.django_db
def test_los_detectores_no_escriben_en_ot_ni_en_case(org_a, actor):
    from cases.models import Case

    _calendario(org_a)
    _orden(org_a, duracion=120)

    def foto():
        return (list(OrdenTrabajo.objects.filter(org=org_a).order_by("id").values()),
                list(Case.objects.filter(org=org_a).order_by("id").values()))

    antes = foto()
    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5))
    A.asistir(org_a, A.COMPROMISOS, MARTES_9 + timedelta(hours=5))
    assert foto() == antes, "el detector modifico OT o Case"


@pytest.mark.django_db
def test_sin_efectos_externos_ni_bypass_de_autonomia(org_a, actor):
    """
    El modulo nuevo no llama a nadie, y las propuestas que crea siguen
    pidiendo revision humana en el nivel mas bajo.
    """
    import ast
    import inspect
    nombres = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(sla))):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
    assert nombres.isdisjoint({
        "requests", "httpx", "urllib", "celery", "apply_async", "shared_task",
        "save", "update", "delete", "create", "ejecutar_propuesta", "revisar",
    })

    _calendario(org_a)
    _orden(org_a, duracion=120)
    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5))
    for p in P.objects.filter(org=org_a, tipo_senal__in=(
            P.ORDEN_SLA_VENCIDO, P.ORDEN_SLA_POR_VENCER)):
        assert p.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR
        assert p.estado == P.PROPUESTA
        assert p.revisado_por_id is None


@pytest.mark.django_db
def test_la_migracion_0006_es_no_destructiva():
    """
    Una sola operacion, y es AlterField de 'choices': no toca datos, no crea
    ni borra columnas. 'sqlmigrate' la resuelve como '-- (no-op)'.
    """
    import ast
    import pathlib
    ruta = (pathlib.Path(__file__).resolve().parent.parent
            / "migrations" / "0006_m04a_senales_sla.py")
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    ops = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and getattr(nodo.targets[0], "id", "") == "operations":
            for op in nodo.value.elts:
                ops.append(op.func.attr if isinstance(op.func, ast.Attribute)
                           else getattr(op.func, "id", "?"))
    assert ops == ["AlterField"], ops
    for destructiva in ("RemoveField", "DeleteModel", "RunSQL", "RunPython",
                        "AlterModelTable", "RenameField"):
        assert destructiva not in ops


@pytest.mark.django_db
def test_las_catorce_originales_no_cambiaron():
    """
    Agregar H-11 y H-12 no puede alterar ninguna de las 14 fichas que M09-K ya
    dejo registradas: sus huellas son su identidad. Se comprueba que siguen
    siendo 14, que todas son de dominio o transversales conocidas, y que H-05
    sigue BLOQUEADA.
    """
    from operaciones import habilidades as H

    #  Las agregadas DESPUES de M09-M. Cada bloque que sume una la declara
    #  aqui y esta guarda sigue valiendo sin tocar numeros sueltos: lo que
    #  afirma es que las 14 ORIGINALES no cambiaron, no cuantas hay en total.
    AGREGADAS = ("H-11", "H-12", "H-13", "H-14", "H-15")
    originales = [i for i in H.IDS if i not in AGREGADAS]
    assert len(originales) == 14, originales
    assert len(H.HABILIDADES) == 14 + len(AGREGADAS)

    #  ninguna huella repetida entre las 16
    huellas = {i: H.HABILIDADES[i].huella() for i in H.IDS}
    assert len(set(huellas.values())) == len(huellas), "hay huellas repetidas"

    #  H-05 sigue bloqueada: M04-A no la toco
    assert H.HABILIDADES["H-05"].estado == H.BLOQUEADA

    #  las dos nuevas estan vigentes y apuntan a sus detectores reales
    assert H.HABILIDADES["H-11"].detector == "_ordenes_con_sla_vencido"
    assert H.HABILIDADES["H-12"].detector == "_ordenes_con_sla_por_vencer"
    assert H.POR_SENAL[P.ORDEN_SLA_VENCIDO] == "H-11"
    assert H.POR_SENAL[P.ORDEN_SLA_POR_VENCER] == "H-12"
