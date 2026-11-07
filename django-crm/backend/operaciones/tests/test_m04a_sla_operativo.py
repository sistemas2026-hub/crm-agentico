# -*- coding: utf-8 -*-
"""
================================================================================
 M04-A  --  SLA operativo derivado de una orden de trabajo
================================================================================

El plazo NO se guarda: se calcula. Lo que se verifica aca no es que el numero
salga, sino las cuatro cosas que un SLA mal hecho arruina en silencio:

  * que la ausencia de dato NO se lea como cero (SIN_PLAZO != A_TIEMPO);
  * que reprogramar NO regale plazo, y cambiar el plan NO lo reinicie;
  * que el calendario laboral sea el MISMO que usa 'cases' -- no una copia;
  * que "vencida" sea un hecho medible y no un juicio.

TIEMPO CONGELADO
----------------
Ninguna prueba depende del reloj: 'ahora' se inyecta siempre. Una suite de SLA
que mira 'timezone.now()' pasa en verde toda la manana y falla a las 18:01, y
el fallo no dice por que.
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
from operaciones import actividades as m02
from operaciones import asistentes as A
from operaciones import sla
from operaciones.capacidad import CLAVE_DURACION

_n = [9500]
_c = [0]

#  Un martes a las 09:00 UTC. Fijo, para que ningun resultado dependa del dia
#  en que se corra la suite.
MARTES_9 = datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("UTC"))


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"s{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _calendario(org, abre=time(8, 0), cierra=time(16, 0), tz="UTC", dias=None):
    """Calendario laboral. Por defecto 8-16 todos los dias, UTC."""
    cal = BusinessCalendar.objects.create(org=org, name="Default", timezone=tz,
                                          is_default=True)
    dias = dias or ("monday", "tuesday", "wednesday", "thursday", "friday",
                    "saturday", "sunday")
    for d in dias:
        setattr(cal, f"{d}_open", abre)
        setattr(cal, f"{d}_close", cierra)
    cal.save()
    return cal


def _orden(org, duracion=None, creada=None, estado=OrdenTrabajo.ASIGNADA,
           con_version=True):
    _n[0] += 1
    version = None
    if con_version:
        wt = WorkType.objects.create(org=org, codigo=f"s_{_n[0]}", nombre="s")
        esquema = {"campos": [], "evidencias": []}
        if duracion is not None:
            esquema[CLAVE_DURACION] = duracion
        version = WorkTypeVersion.objects.create(
            work_type=wt, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    o = OrdenTrabajo.objects.create(
        org=org, numero=_n[0], tipo_trabajo_version=version,
        cliente_nombre=f"C{_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=estado)
    if creada is not None:
        #  'created_at' es auto_now_add: se fija con UPDATE para poder anclar
        #  la prueba en un instante conocido.
        OrdenTrabajo.objects.filter(pk=o.pk).update(created_at=creada)
        o.refresh_from_db()
    return o


# ============================================== 1-4. los cuatro estados vivos
@pytest.mark.django_db
def test_1_duracion_valida_produce_plazo_calculado(org_a):
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    p = sla.plazo_de(o, MARTES_9)

    assert p["minutos_objetivo"] == 120
    assert p["ancla"] == MARTES_9.isoformat()
    assert p["limite"] is not None
    #  8-16 y creada a las 9: dos horas habiles caen a las 11 del mismo dia.
    assert p["limite"].startswith("2026-09-15T11:00")
    assert p["datos_faltantes"] == []


@pytest.mark.django_db
def test_2_a_tiempo(org_a):
    """
    Hace falta un plazo LARGO para ver A_TIEMPO, y eso es un hallazgo del
    bloque, no un detalle de la prueba: la ventana de aviso por defecto son las
    24 h que M09 usa para compromisos, asi que CUALQUIER orden con un plazo de
    pocas horas nace ya en VENCE_PRONTO. Se reutiliza ese umbral a proposito
    --inventar uno nuevo aqui seria decidir sin datos-- y queda anotado como
    decision pendiente.

    40 horas habiles sobre una jornada de 8 h son cinco dias: ahi si hay
    margen mayor que la ventana.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=2400, creada=MARTES_9)
    p = sla.plazo_de(o, MARTES_9 + timedelta(minutes=10))
    assert p["estado"] == sla.A_TIEMPO
    assert p["minutos_restantes"] > 24 * 60
    assert p["minutos_atraso"] == 0


@pytest.mark.django_db
def test_3_vence_pronto(org_a):
    """
    Dentro de la ventana, que es PROPORCIONAL: 20% del plazo con tope de 24 h.

    Con 120 min de plazo la ventana son 24 min, asi que a una hora del limite
    todavia es A_TIEMPO. La version anterior de esta prueba usaba el umbral
    fijo de 24 h heredado de M09 y afirmaba lo contrario; quedo obsoleta al
    cambiar la ventana, y se actualiza al comportamiento nuevo.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)   # limite 11:00, ventana 24 min

    #  a una hora del limite: todavia hay margen
    lejos = sla.plazo_de(o, MARTES_9 + timedelta(minutes=60))
    assert lejos["estado"] == sla.A_TIEMPO
    assert lejos["minutos_restantes"] == 60

    #  a quince minutos: dentro de la ventana
    cerca = sla.plazo_de(o, MARTES_9 + timedelta(minutes=105))
    assert cerca["estado"] == sla.VENCE_PRONTO
    assert cerca["minutos_restantes"] == 15
    assert round(cerca["ventana_horas"], 4) == 0.4
    assert cerca["ventana_fraccion"] == 0.20

    #  y una ventana explicita gana sobre la proporcional: el umbral se
    #  declara, no se adivina.
    p2 = sla.plazo_de(o, MARTES_9 + timedelta(minutes=105), ventana_horas=0)
    assert p2["estado"] == sla.A_TIEMPO
    assert p2["ventana_fraccion"] is None


@pytest.mark.django_db
def test_4_vencida_con_minutos_de_atraso(org_a):
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    p = sla.plazo_de(o, MARTES_9 + timedelta(minutes=185))
    assert p["estado"] == sla.VENCIDA
    assert p["minutos_atraso"] == 65
    assert p["minutos_restantes"] == 0
    #  y el texto describe el hecho, sin repartir culpas
    texto = sla.resumen(p).lower()
    assert "vencida" in texto
    for juicio in ("culpa", "incumpl", "responsable de", "negligen"):
        assert juicio not in texto


# ============================================== 5-6. ausencia de datos
@pytest.mark.django_db
def test_5_sin_tipo_de_trabajo_es_datos_insuficientes(org_a):
    """
    No se pudo llegar al dato. Distinto de 'no hay plazo declarado'.

    La orden NO se guarda: 'tipo_trabajo_version' es NOT NULL con PROTECT, asi
    que la base ya impide que exista una orden sin tipo. El guard cubre el otro
    camino real -- un objeto en memoria, o una relacion que no se pudo
    resolver -- y se prueba ahi, que es donde puede ocurrir.
    """
    o = OrdenTrabajo(org=org_a, numero=999001, tipo_trabajo_version=None,
                     cliente_nombre="C", cliente_direccion="Calle 1")
    o.created_at = MARTES_9
    p = sla.plazo_de(o, MARTES_9)
    assert p["estado"] == sla.DATOS_INSUFICIENTES
    assert p["minutos_objetivo"] is None
    assert p["limite"] is None
    campos = {f["campo"] for f in p["datos_faltantes"]}
    assert "tipo_trabajo_version" in campos


@pytest.mark.django_db
@pytest.mark.parametrize("valor", [None, 0, -30, "90", 90.5, True])
def test_6_duracion_invalida_es_sin_plazo_y_nunca_cero(org_a, valor):
    """
    LA prueba que impide el error clasico: tratar la ausencia como 0 minutos,
    que convertiria toda orden sin duracion en 'vencida desde que nacio'.

    Se recorren tambien los casi-validos: texto "90", 90.5 y True -- este
    ultimo porque bool es subclase de int en Python y valdria 1 minuto.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=valor, creada=MARTES_9)
    p = sla.plazo_de(o, MARTES_9 + timedelta(days=30))

    assert p["estado"] == sla.SIN_PLAZO, f"con {valor!r}"
    assert p["estado"] != sla.VENCIDA
    assert p["minutos_objetivo"] is None
    assert p["limite"] is None
    campos = {f["campo"] for f in p["datos_faltantes"]}
    assert CLAVE_DURACION in campos


# ============================================== 7-9. calendario y timezone
@pytest.mark.django_db
def test_7_el_plazo_respeta_el_calendario_laboral(org_a):
    """4 h habiles sobre una jornada de 8-12 no caben en un solo dia."""
    _calendario(org_a, abre=time(8, 0), cierra=time(12, 0))
    o = _orden(org_a, duracion=300, creada=MARTES_9)   # 5 horas
    p = sla.plazo_de(o, MARTES_9)
    #  De 9 a 12 hay 3 h; las 2 restantes se pasan al dia siguiente desde las 8.
    assert p["limite"].startswith("2026-09-16T10:00"), p["limite"]
    assert p["calendario"] == "Default"


@pytest.mark.django_db
def test_8_el_plazo_salta_los_dias_no_laborables(org_a):
    """Con el fin de semana cerrado, un plazo del viernes cae el lunes."""
    _calendario(org_a, abre=time(8, 0), cierra=time(16, 0),
                dias=("monday", "tuesday", "wednesday", "thursday", "friday"))
    viernes = datetime(2026, 9, 18, 15, 0, tzinfo=ZoneInfo("UTC"))
    o = _orden(org_a, duracion=120, creada=viernes)   # 1 h el viernes + 1 h
    p = sla.plazo_de(o, viernes)
    assert p["limite"].startswith("2026-09-21T"), p["limite"]   # lunes


@pytest.mark.django_db
def test_9_el_timezone_del_calendario_manda(org_a):
    """
    El mismo instante UTC con un calendario en Bogota da OTRO limite: las
    ventanas 8-16 son locales. Si el modulo ignorara el timezone, los dos
    calendarios darian lo mismo -- y este assert lo detecta.
    """
    cal = _calendario(org_a, tz="America/Bogota")
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    con_bogota = sla.plazo_de(o, MARTES_9)["limite"]

    BusinessCalendar.objects.filter(pk=cal.pk).update(timezone="UTC")
    con_utc = sla.plazo_de(o, MARTES_9)["limite"]

    assert con_bogota != con_utc, "el timezone del calendario no se esta usando"


# ============================================== 10-11. lo que NO reinicia
@pytest.mark.django_db
def test_10_reprogramar_no_extiende_el_plazo(org_a):
    """
    Regla 4. El ancla es 'created_at', que nadie puede mover. Si el ancla
    fuera 'programada_para', mover la orden al martes le regalaria plazo nuevo
    y el indicador mediria la diligencia de quien reprograma.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    antes = sla.plazo_de(o, MARTES_9 + timedelta(hours=5))
    assert antes["estado"] == sla.VENCIDA

    OrdenTrabajo.objects.filter(pk=o.pk).update(
        programada_para=MARTES_9 + timedelta(days=7))
    o.refresh_from_db()
    despues = sla.plazo_de(o, MARTES_9 + timedelta(hours=5))

    assert despues["limite"] == antes["limite"], "reprogramar movio el plazo"
    assert despues["estado"] == sla.VENCIDA
    assert despues["minutos_atraso"] == antes["minutos_atraso"]


@pytest.mark.django_db
def test_11_cambiar_el_plan_no_reinicia_el_plazo(org_a, actor):
    """Regla 5: el plan es de M03; el plazo no cuelga de el."""
    from operaciones.models import ProgramacionSemanal
    from operaciones.programacion import programar_orden

    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    antes = sla.plazo_de(o, MARTES_9 + timedelta(hours=5))

    dia = timezone.localtime(timezone.now()).date()
    plan, _ = ProgramacionSemanal.objects.get_or_create(
        org=org_a, semana_inicio=dia - timedelta(days=dia.weekday()),
        defaults={"estado": ProgramacionSemanal.BORRADOR})
    programar_orden(org=org_a, orden=o, programacion=plan, actor=actor,
                    programada_para=timezone.make_aware(
                        datetime.combine(dia, time(9, 0))))
    o.refresh_from_db()

    despues = sla.plazo_de(o, MARTES_9 + timedelta(hours=5))
    assert despues["limite"] == antes["limite"]
    assert despues["minutos_atraso"] == antes["minutos_atraso"]


@pytest.mark.django_db
def test_11b_una_orden_terminada_no_tiene_plazo_corriendo(org_a):
    """NO_APLICA no es A_TIEMPO ni VENCIDA: el recorrido termino."""
    _calendario(org_a)
    for estado in (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA):
        o = _orden(org_a, duracion=120, creada=MARTES_9, estado=estado)
        p = sla.plazo_de(o, MARTES_9 + timedelta(days=30))
        assert p["estado"] == sla.NO_APLICA, estado
        #  el limite se sigue informando: sirve para mirar hacia atras
        assert p["limite"] is not None


@pytest.mark.django_db
def test_11c_el_calculo_es_determinista(org_a):
    """Dos llamadas con el mismo 'ahora' dan exactamente lo mismo."""
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    a = sla.plazo_de(o, MARTES_9 + timedelta(minutes=30))
    b = sla.plazo_de(o, MARTES_9 + timedelta(minutes=30))
    assert a == b


@pytest.mark.django_db
def test_11d_no_escribe_nada_en_la_base(org_a):
    """Derivado, no almacenado. Se mide sobre la fila entera."""
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)

    def foto():
        return list(OrdenTrabajo.objects.filter(org=org_a).order_by("id")
                    .values())

    antes = foto()
    for t in (0, 60, 5000):
        sla.plazo_de(o, MARTES_9 + timedelta(minutes=t))
    assert foto() == antes, "el calculo de SLA modifico la orden"


# ============================================== 12-13. supervisor
@pytest.mark.django_db
def test_12_datos_incompletos_no_generan_propuesta(org_a, actor):
    """
    Una orden sin duracion no produce una propuesta apoyada en un plazo
    inventado. Se comprueba sobre la cola real, no sobre la salida.
    """
    from operaciones.models import PropuestaSupervisor as P

    _calendario(org_a)
    _orden(org_a, duracion=None, creada=MARTES_9)
    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9)

    for r in salida["recomendaciones"]:
        if (r["sla"] or {}).get("estado") in (sla.SIN_PLAZO, sla.DATOS_INSUFICIENTES):
            #  puede haber propuesta por OTRA razon (sin programar), pero
            #  ninguna puede afirmar un plazo que no existe
            assert r["sla"]["limite"] is None
            assert r["sla"]["minutos_objetivo"] is None
    #  y ninguna propuesta de la cola afirma un plazo: se mira 'evidencia',
    #  que es donde de verdad guarda sus hechos (no existe campo 'datos').
    for p in P.objects.filter(org=org_a):
        texto = str(p.evidencia or []) + " " + (p.motivo or "")
        assert "minutos_objetivo" not in texto
        assert "limite" not in texto


@pytest.mark.django_db
def test_13_la_deduplicacion_sigue_valiendo_con_sla(org_a, actor):
    from operaciones.models import PropuestaSupervisor as P

    _calendario(org_a)
    _orden(org_a, duracion=120, creada=MARTES_9)
    primera = A.asistir(org_a, A.PROGRAMACION, MARTES_9)
    creadas = P.objects.filter(org=org_a).count()
    assert primera["resumen"]["propuestas_creadas"] > 0

    segunda = A.asistir(org_a, A.PROGRAMACION, MARTES_9)
    assert P.objects.filter(org=org_a).count() == creadas
    assert segunda["resumen"]["repetidas"] > 0


# ============================================== 14-15. A-1 y A-2
@pytest.mark.django_db
def test_14_a1_expone_el_sla_de_la_orden(org_a, actor):
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(hours=5),
                       registrar=False)
    filas = [r for r in salida["recomendaciones"]
             if r["origen_tipo"] == "orden_trabajo" and r["origen_id"] == str(o.id)]
    assert filas, "la orden deberia producir alguna señal"
    s = filas[0]["sla"]
    assert s is not None
    assert s["estado"] == sla.VENCIDA
    assert s["minutos_objetivo"] == 120
    assert s["minutos_atraso"] > 0
    assert s["explicacion"].startswith("vencida")
    assert salida["resumen"]["sla_vencidas"] >= 1


@pytest.mark.django_db
def test_15_a2_expone_el_sla_cuando_el_compromiso_cuelga_de_una_orden(org_a, actor):
    """
    El vinculo es 'origen_tipo'/'origen_id' de M02 -- por convencion, no por
    clave foranea. Se comprueba que A-2 lo sigue.
    """
    _calendario(org_a)
    o = _orden(org_a, duracion=120, creada=MARTES_9)
    a = m02.crear(org=org_a, actor=actor, titulo="revisar la orden",
                  origen_tipo="orden_trabajo", origen_id=str(o.id),
                  vence_en=MARTES_9 - timedelta(hours=2))

    salida = A.asistir(org_a, A.COMPROMISOS, MARTES_9 + timedelta(hours=5),
                       registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas, "la actividad vencida deberia producir señal"
    s = filas[0]["sla"]
    assert s is not None, "A-2 no siguio el vinculo hacia la orden"
    assert s["estado"] == sla.VENCIDA
    assert s["minutos_objetivo"] == 120


@pytest.mark.django_db
def test_15b_un_compromiso_sin_orden_no_inventa_sla(org_a, actor):
    """Lo contrario del anterior: sin vinculo, 'sla' es None, no un plazo."""
    _calendario(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="suelta",
                  vence_en=MARTES_9 - timedelta(hours=2))
    salida = A.asistir(org_a, A.COMPROMISOS, MARTES_9, registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas
    assert filas[0]["sla"] is None


@pytest.mark.django_db
def test_15c_el_sla_no_convierte_al_asistente_en_ejecutor(org_a, actor):
    """El modulo nuevo tampoco importa servicios de escritura."""
    import ast
    import inspect
    nombres = set()
    for mod in (sla, A):
        for nodo in ast.walk(ast.parse(inspect.getsource(mod))):
            if isinstance(nodo, ast.Name):
                nombres.add(nodo.id)
            elif isinstance(nodo, ast.Attribute):
                nombres.add(nodo.attr)
    assert nombres.isdisjoint({
        "programar_orden", "reprogramar_orden", "asignar", "completar",
        "cancelar", "bloquear", "validar", "crear", "escalar", "save",
        "update", "delete", "requests", "httpx", "celery", "shared_task",
    }), sorted(nombres & {"save", "update", "delete", "completar", "crear"})
