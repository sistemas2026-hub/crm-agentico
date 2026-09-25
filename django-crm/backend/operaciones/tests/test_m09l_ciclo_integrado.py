# -*- coding: utf-8 -*-
"""
================================================================================
 M09-L  --  ciclo integrado del Supervisor NOC IA
================================================================================

El ciclo ya existia. Lo que este paso agrega es la capacidad de M03-G como
fuente de senal y una salida consolidada. Estas pruebas verifican las dos cosas
sin aflojar lo que ya estaba: que el Supervisor MIRA y PROPONE, y no toca nada.

La asimetria de M03-G se hereda y se comprueba aqui:

    con datos parciales SE PUEDE afirmar la sobrecarga
    con datos parciales NO SE PUEDE afirmar que no la hay

Una prueba que aceptara una senal de sobrecarga sobre duraciones desconocidas
estaria validando la falsa conclusion que M03-G existe para evitar.
================================================================================
"""

from __future__ import annotations

import socket
import threading
from datetime import date, datetime, time, timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from business_hours.models import BusinessCalendar
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from common.models import Activity, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import actividades as m02
from operaciones import auditoria, capacidad, habilidades, supervisor
from operaciones.models import (ActividadOperativa, DisponibilidadTecnico,
                                ProgramacionOrden, ProgramacionSemanal,
                                PropuestaSupervisor)
from operaciones.programacion import programar_orden

P = PropuestaSupervisor
CICLO = "/api/operaciones/supervisor/ciclo/"
_n = [3000]
_c = [0]


def _hoy():
    return timezone.localtime(timezone.now()).date()


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"l{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


def _calendario(org, abre=time(8, 0), cierra=time(16, 0)):
    cal = BusinessCalendar.objects.create(org=org, name="Default",
                                          timezone="UTC", is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday",
              "saturday", "sunday"):
        setattr(cal, f"{d}_open", abre)
        setattr(cal, f"{d}_close", cierra)
    cal.save()
    return cal          # 480 minutos cualquier dia


def _orden(org, duracion=None):
    _n[0] += 1
    wt = WorkType.objects.create(org=org, codigo=f"l_{_n[0]}", nombre="l")
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


def _jornada_cargada(org, actor, persona, minutos_por_ot, dia=None,
                     sin_duracion=0):
    """Programa OTs para 'persona' un dia. Devuelve el dia."""
    dia = dia or (_hoy() + timedelta(days=1))
    #  Un plan por semana y organizacion: la base lo impone
    #  (unique_programacion_semana_por_org), asi que se reutiliza el que haya.
    plan, _creado = ProgramacionSemanal.objects.get_or_create(
        org=org, semana_inicio=dia - timedelta(days=dia.weekday()),
        defaults={"estado": ProgramacionSemanal.BORRADOR})
    hora = 8
    for m in minutos_por_ot:
        o = _orden(org, duracion=m)
        AsignacionTrabajo.objects.create(orden=o, profile=persona,
                                         es_principal=True)
        programar_orden(org=org, orden=o, programacion=plan, actor=actor,
                        programada_para=timezone.make_aware(
                            datetime.combine(dia, time(hora, 0))))
        hora = min(hora + 1, 20)
    for _ in range(sin_duracion):
        o = _orden(org, duracion=None)
        AsignacionTrabajo.objects.create(orden=o, profile=persona,
                                         es_principal=True)
        programar_orden(org=org, orden=o, programacion=plan, actor=actor,
                        programada_para=timezone.make_aware(
                            datetime.combine(dia, time(hora, 0))))
        hora = min(hora + 1, 20)
    return dia


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _tipos(resumen):
    return {f["tipo"] for f in resumen["detalle"]}


# ==================================================== 1. ciclo vacío
@pytest.mark.django_db
def test_1_ciclo_sin_senales(org_a):
    r = supervisor.correr_ciclo(org_a)
    assert r["senales"] == 0 and r["propuestas"] == 0
    assert r["detalle"] == []
    assert r["organizacion"]["id"] == str(org_a.id)
    assert r["ahora"]
    assert P.objects.filter(org=org_a).count() == 0


# ==================================================== 2-4. señales integradas
@pytest.mark.django_db
def test_2_senales_de_m02(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    vencida = m02.crear(org=org_a, actor=actor, titulo="vencida",
                        vence_en=ahora - timedelta(hours=5))
    m02.asignar_responsable(vencida, actor=actor, responsable=p1)
    m02.crear(org=org_a, actor=actor, titulo="sin responsable")
    bloq = m02.crear(org=org_a, actor=actor, titulo="bloqueada")
    m02.asignar_responsable(bloq, actor=actor, responsable=p1)
    m02.bloquear(bloq, actor=actor, motivo="falta permiso")

    r = supervisor.correr_ciclo(org_a, ahora)
    tipos = _tipos(r)
    assert P.ACTIVIDAD_VENCIDA in tipos
    assert P.ACTIVIDAD_SIN_RESPONSABLE in tipos
    assert P.ACTIVIDAD_BLOQUEADA in tipos
    assert r["propuestas"] >= 3


@pytest.mark.django_db
def test_3_senales_de_m03(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    #  orden sin programar
    o = _orden(org_a, duracion=60)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    #  jornada sobrecargada: 3 x 200 = 600 > 480
    _jornada_cargada(org_a, actor, p1, [200, 200, 200])

    r = supervisor.correr_ciclo(org_a)
    assert P.ORDEN_SIN_PROGRAMAR in _tipos(r)
    #  M03-G llegó al ciclo: la sobrecarga se VE en el resumen
    assert len(r["capacidad"]["jornadas_sobrecargadas"]) == 1


@pytest.mark.django_db
def test_4_ciclo_combinado(org_a, actor):
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=3))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    _jornada_cargada(org_a, actor, p1, [300, 300])

    r = supervisor.correr_ciclo(org_a, ahora)
    assert P.ACTIVIDAD_VENCIDA in _tipos(r)          # M02
    assert r["capacidad"]["jornadas_sobrecargadas"]  # M03
    assert r["senales"] == len(r["detalle"])
    #  el detalle viene ordenado por prioridad
    prios = [(f["propuesta"] or {}).get("prioridad", 99) for f in r["detalle"]]
    assert prios == sorted(prios)


# ==================================================== 5-6. capacidad
@pytest.mark.django_db
def test_5_capacidad_determinada_produce_sobrecarga(org_a, actor):
    _calendario(org_a)                       # 480 min
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [280, 280])     # 560

    r = supervisor.correr_ciclo(org_a)
    obs = r["capacidad"]["jornadas_sobrecargadas"]
    assert len(obs) == 1
    assert obs[0]["capacidad_minutos"] == 480
    assert obs[0]["carga_minutos"] == 560
    assert obs[0]["exceso_minutos"] == 80
    assert obs[0]["es_cota_inferior"] is False

    #  SE VE, PERO NO SE PROPONE. H-05 --"Estimar riesgo operacional por
    #  capacidad"-- está BLOQUEADA, y el guarda de M09-K exige que toda señal
    #  tenga una habilidad que la explique. Proponer sin ficha sería darle al
    #  Jefe de Operaciones una recomendación que el sistema no puede justificar.
    assert P.objects.filter(
        org=org_a, origen_tipo="jornada").exclude(
        tipo_senal=P.DATO_INCOMPLETO).count() == 0
    assert "H-05" in r["capacidad"]["nota"]


@pytest.mark.django_db
def test_6_capacidad_indeterminada_no_inventa_sobrecarga(org_a, actor):
    """
    LA REGLA HEREDADA DE M03-G. Con duraciones faltantes y sin exceso
    demostrable, el ciclo NO afirma sobrecarga: emite 'dato_incompleto' y
    nombra las órdenes concretas a las que les falta el dato.
    """
    _calendario(org_a)                       # 480 min
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=2)   # 60 conocidos

    r = supervisor.correr_ciclo(org_a)
    tipos = _tipos(r)
    assert r["capacidad"]["jornadas_sobrecargadas"] == [], (
        "afirmó sobrecarga sin conocer todas las duraciones")
    assert P.DATO_INCOMPLETO in tipos
    assert r["datos_insuficientes"] >= 1

    fila = [f for f in r["detalle"] if f["tipo"] == P.DATO_INCOMPLETO][0]
    assert len(fila["datos"]["numeros_sin_duracion"]) == 2
    assert fila["datos"]["campo"] == "duracion_estimada_minutos"
    prop = P.objects.get(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                         origen_tipo="jornada")
    assert "COTA INFERIOR" in prop.motivo
    assert prop.nivel_autonomia_requerido == P.NIVEL_OBSERVAR


@pytest.mark.django_db
def test_6b_con_datos_parciales_la_sobrecarga_si_se_afirma(org_a, actor):
    """La otra mitad: si lo conocido ya no cabe, se concluye igual."""
    _calendario(org_a)                       # 480
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [500], sin_duracion=1)

    r = supervisor.correr_ciclo(org_a)
    obs = r["capacidad"]["jornadas_sobrecargadas"]
    assert len(obs) == 1
    assert obs[0]["es_cota_inferior"] is True, (
        "no avisó que el exceso es una cota inferior")
    assert obs[0]["exceso_minutos"] == 20


@pytest.mark.django_db
def test_6c_sin_calendario_no_hay_senal_de_capacidad(org_a, actor):
    """Sin jornada la capacidad no es determinable: no se inventa ninguna."""
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [600, 600])
    r = supervisor.correr_ciclo(org_a)
    assert r["capacidad"]["jornadas_sobrecargadas"] == []
    assert r["capacidad"]["jornadas_no_determinables"], (
        "no dijo que no se podía determinar")


# ==================================================== 7-8. evidencia
@pytest.mark.django_db
def test_7_evidencia_obligatoria(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)
    supervisor.correr_ciclo(org_a)

    assert P.objects.filter(org=org_a).exists()
    for prop in P.objects.filter(org=org_a):
        assert prop.evidencia, f"{prop.tipo_senal} sin evidencia"
        for obs in prop.evidencia:
            assert obs.get("dato"), obs
    #  y el servicio lo rechaza de frente
    vacia = supervisor.Senal(tipo=P.ACTIVIDAD_VENCIDA, origen_tipo="actividad",
                             origen_id="x", evidencia=[], datos={}, huella="h")
    with pytest.raises(ValueError, match="sin evidencia"):
        supervisor.registrar_propuesta(org_a, vacia, {"accion_propuesta": "x",
                                                      "motivo": "y",
                                                      "prioridad": 50})


@pytest.mark.django_db
def test_8_propuesta_creada_con_todo_lo_exigido(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)
    supervisor.correr_ciclo(org_a)

    prop = P.objects.get(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                         origen_tipo="jornada")
    assert prop.accion_propuesta and prop.motivo and prop.impacto
    assert prop.evidencia and prop.prioridad is not None
    assert prop.estado == P.PROPUESTA
    assert prop.expira_en > timezone.now()
    assert prop.revisado_por is None and prop.revisado_en is None
    #  no existe ningun "ejecutada=true"
    assert not hasattr(prop, "ejecutada")


# ==================================================== 9-11. deduplicación
@pytest.mark.django_db
def test_9_10_11_deduplicacion(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    dia = _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)

    def cuantas():
        return P.objects.filter(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                                origen_tipo="jornada").count()

    r1 = supervisor.correr_ciclo(org_a)
    assert r1["propuestas"] >= 1
    assert cuantas() == 1

    #  9. el mismo hecho no vuelve a proponerse
    r2 = supervisor.correr_ciclo(org_a)
    assert r2["repetidas"] >= 1
    assert cuantas() == 1
    #  pero SIGUE en el detalle: el hecho ocurre aunque la pregunta no se repita
    fila = [f for f in r2["detalle"]
            if f["origen_tipo"] == "jornada"][0]
    assert fila["resultado"] == "repetida" and fila["propuesta"] is None

    #  10. rechazada con la misma evidencia: tampoco vuelve
    prop = P.objects.get(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                         origen_tipo="jornada")
    prop.estado = P.RECHAZADA
    prop.save(update_fields=["estado"])
    r3 = supervisor.correr_ciclo(org_a)
    assert cuantas() == 1
    assert r3["repetidas"] >= 1

    #  11. con evidencia NUEVA (otro día, otra orden) sí vuelve a preguntar
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1,
                     dia=dia + timedelta(days=1))
    supervisor.correr_ciclo(org_a)
    assert cuantas() == 2


# ==================================================== 12-13. prioridad e impacto
@pytest.mark.django_db
def test_12_13_prioridad_e_impacto(org_a, actor):
    """
    La prioridad se calcula con la regla existente y se EXPLICA: los
    componentes viajan como evidencia, no como un número suelto.
    """
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    #  Dos actividades vencidas: la que lleva más tiempo debe quedar más urgente
    poco = m02.crear(org=org_a, actor=actor, titulo="vencida hace poco",
                     vence_en=ahora - timedelta(hours=2))
    mucho = m02.crear(org=org_a, actor=actor, titulo="vencida hace mucho",
                      vence_en=ahora - timedelta(hours=100))
    for a in (poco, mucho):
        m02.asignar_responsable(a, actor=actor, responsable=p1)

    supervisor.correr_ciclo(org_a, ahora)
    props = {x.origen_id: x for x in
             P.objects.filter(org=org_a, tipo_senal=P.ACTIVIDAD_VENCIDA)}
    assert len(props) == 2
    assert props[str(mucho.id)].prioridad < props[str(poco.id)].prioridad, (
        "la más vencida no quedó más urgente")

    for x in props.values():
        assert x.impacto, "sin impacto declarado"
        assert any("calculo_prioridad" in o.get("fuente", "")
                   for o in x.evidencia), "la prioridad no se explica"
        #  La prioridad NO autoriza ejecutar: son ejes distintos.
        assert x.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR


# ==================================================== 14-16. tenants
@pytest.mark.django_db
def test_14_15_16_aislamiento(org_a, org_b, actor):
    _calendario(org_a)
    _calendario(org_b)
    _, actor_b = _persona(org_b, "OPERACIONES")
    _, pa = _persona(org_a)
    _, pb = _persona(org_b)
    _jornada_cargada(org_a, actor, pa, [60], sin_duracion=1)
    _jornada_cargada(org_b, actor_b, pb, [60], sin_duracion=1)

    ra = supervisor.correr_ciclo(org_a)
    assert P.objects.filter(org=org_a).count() == ra["propuestas"]
    assert P.objects.filter(org=org_b).count() == 0, "escribió en el otro tenant"

    rb = supervisor.correr_ciclo(org_b)
    assert rb["organizacion"]["id"] == str(org_b.id)
    for f in ra["detalle"]:
        assert str(pb.id) not in f["origen_id"]

    #  y por HTTP, cada quien ve el suyo
    ug, g = _persona(org_a, "OPERACIONES")
    r = _cli(ug, org_a, g).post(CICLO, {}, format="json")
    assert r.status_code == 200
    assert r.data["resumen"]["organizacion"]["id"] == str(org_a.id)


# ==================================================== 17. revisión humana
@pytest.mark.django_db
def test_17_revision_humana(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)
    supervisor.correr_ciclo(org_a)
    prop = P.objects.get(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                         origen_tipo="jornada")

    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    r = cli.post(f"/api/operaciones/propuestas/{prop.id}/revisar/",
                 {"decision": P.RECHAZADA,
                  "comentario": "lo cubre otra cuadrilla"},
                 format="json")
    assert r.status_code == 200, r.data
    prop.refresh_from_db()
    assert prop.estado == P.RECHAZADA
    assert prop.revisado_por_id == g.id and prop.revisado_en is not None
    #  un técnico no revisa
    ut, t = _persona(org_a, "USER")
    assert _cli(ut, org_a, t).post(
        f"/api/operaciones/propuestas/{prop.id}/revisar/",
        {"decision": P.ACEPTADA}, format="json").status_code == 403


# ==================================================== 18. concurrencia
@pytest.mark.django_db(transaction=True)
def test_18_ciclos_concurrentes(org_a):
    """
    Dos ciclos a la vez sobre la misma organización. Se MIDE cuántas propuestas
    quedan para el mismo hecho: la deduplicación existente es leer-y-escribir,
    sin constraint única detrás, así que esto comprueba el efecto real en vez
    de suponerlo.
    """
    _, act_p = _persona(org_a, "OPERACIONES")
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, act_p, p1, [60], sin_duracion=1)

    barrera = threading.Barrier(2)
    fallos = []

    def corre():
        try:
            barrera.wait(timeout=10)
            supervisor.correr_ciclo(org_a)
        except Exception as e:
            fallos.append(f"{type(e).__name__}: {e}")
        finally:
            connection.close()

    hs = [threading.Thread(target=corre) for _ in range(2)]
    for h in hs: h.start()
    for h in hs: h.join(timeout=60)

    assert not fallos, fallos
    por_huella = {}
    for x in P.objects.filter(org=org_a):
        k = (x.tipo_senal, x.origen_id, x.huella_condicion)
        por_huella[k] = por_huella.get(k, 0) + 1
    repetidas = {k: v for k, v in por_huella.items() if v > 1}
    assert not repetidas, (
        f"dos ciclos simultáneos dejaron propuestas duplicadas: {repetidas}")


# ==================================================== 19. efectos externos
@pytest.mark.django_db
def test_19_sin_efectos_externos(org_a, actor):
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    _jornada_cargada(org_a, actor, p1, [300, 300], sin_duracion=1)

    salidas = []
    original = socket.socket.connect

    def espia(self, addr, *a2, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("pg-l", "127.0.0.1", "localhost", "::1"):
            salidas.append(host)
        return original(self, addr, *a2, **k)

    socket.socket.connect = espia
    try:
        try:
            s = socket.socket(); s.settimeout(1)
            s.connect(("example.invalid", 80))
        except Exception:
            pass
        assert salidas, "el espía no dispara: su cero no probaría nada"
        salidas.clear()
        r = supervisor.correr_ciclo(org_a, ahora)
        assert r["senales"] > 0, "el ciclo no hizo nada: su cero no diría nada"
    finally:
        socket.socket.connect = original

    assert salidas == [], f"hubo llamadas externas: {salidas}"


# ==================================================== 20. no ejecuta
@pytest.mark.django_db
def test_20_el_ciclo_no_ejecuta_nada(org_a, actor):
    """
    Lo único que el ciclo puede escribir son propuestas y su auditoría. Se
    comprueba sobre TODO lo que podría tocar.
    """
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    _jornada_cargada(org_a, actor, p1, [300, 300], sin_duracion=1)

    def foto():
        return (
            list(ActividadOperativa.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado_operativo", "estado_validacion",
                         "responsable_id", "vence_en", "updated_at")),
            list(OrdenTrabajo.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado_operativo", "programada_para",
                         "revision", "updated_at")),
            list(ProgramacionOrden.objects.filter(org=org_a).order_by("id")
                 .values("id", "dia", "secuencia", "prioridad", "estado",
                         "updated_at")),
            list(ProgramacionSemanal.objects.filter(org=org_a).order_by("id")
                 .values("id", "estado", "updated_at")),
            list(AsignacionTrabajo.objects.filter(orden__org=org_a)
                 .order_by("id").values("id", "profile_id", "es_principal")),
            DisponibilidadTecnico.objects.filter(org=org_a).count(),
        )

    antes = foto()
    r = supervisor.correr_ciclo(org_a, ahora)
    assert r["propuestas"] > 0, "el ciclo no propuso nada: no probaría nada"
    assert foto() == antes, "el ciclo modificó datos operativos"

    #  y ninguna propuesta pide más autonomía de la que hay
    for prop in P.objects.filter(org=org_a):
        assert prop.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR
        assert prop.estado == P.PROPUESTA


# ==================================================== 21-22. habilidades
@pytest.mark.django_db
def test_21_22_habilidades_y_conocimiento(org_a, actor):
    """
    §14: no se creó ninguna habilidad. Las 14 siguen siendo 14, cada señal
    conserva la suya, y NO se emitió ninguna señal sin ficha.
    """
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)
    supervisor.correr_ciclo(org_a, ahora)

    #  Eran 14 hasta M09-M. M04-A agrega H-11 y H-12 (plazo operativo de
    #  una orden) con autorizacion explicita. Las 14 originales NO se
    #  tocaron: lo verifica 'test_las_catorce_originales_no_cambiaron'.
    #  M04-A agrego H-11/H-12 y M05-A agrega H-13, las tres con autorizacion explicita.
    #  M09-M dejo 14. Despues se agregaron, con autorizacion explicita: H-11/H-12 (M04-A), H-13 (M05-A) y H-14 (M05-B).
    #  M09-N (22/09/2026) agrega H-15 (caso cerrado en el proveedor y abierto
    #  en el CRM), tambien con autorizacion explicita.
    assert len(habilidades.HABILIDADES) == 19, "se creó una habilidad no prevista"

    #  Toda señal emitida tiene ficha: es el guarda de M09-K, comprobado
    #  también sobre lo que este ciclo produjo de verdad.
    for prop in P.objects.filter(org=org_a):
        assert prop.tipo_senal in habilidades.POR_SENAL, prop.tipo_senal
        assert prop.conocimiento_version.startswith("habilidad:"), (
            f"{prop.tipo_senal} sin referencia de habilidad")

    #  H-05 sigue BLOQUEADA: M03-G levantó la mitad de su bloqueo (la capacidad
    #  ya es medible) pero desbloquearla es una decisión, no un efecto lateral.
    h05 = habilidades.HABILIDADES["H-05"]
    assert h05.estado == habilidades.BLOQUEADA


# ==================================================== 23. auditoría
@pytest.mark.django_db
def test_23_auditoria(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [60], sin_duracion=1)
    supervisor.correr_ciclo(org_a)
    prop = P.objects.get(org=org_a, tipo_senal=P.DATO_INCOMPLETO,
                         origen_tipo="jornada")

    ev = list(auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, prop.id))
    assert ev, "la propuesta no dejó auditoría"
    creacion = ev[-1]
    assert creacion.action == "CREATE"
    #  el autor es la IA: 'user' vacío a propósito, para no confundirla con
    #  una persona en la bitácora
    assert creacion.user_id is None
    assert creacion.metadata["tipo_senal"] == P.DATO_INCOMPLETO
    assert creacion.entity_type == auditoria.ENTIDAD_PROPUESTA


# ==================================================== API
@pytest.mark.django_db
def test_api_el_ciclo_manual_devuelve_resumen_y_detalle(org_a, actor):
    _calendario(org_a)
    _, p1 = _persona(org_a)
    _jornada_cargada(org_a, actor, p1, [300, 300], sin_duracion=1)
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)

    r = cli.post(CICLO, {}, format="json")
    assert r.status_code == 200
    res = r.data["resumen"]
    for k in ("senales", "propuestas", "repetidas", "sin_analisis",
              "expiradas", "datos_insuficientes", "por_tipo", "organizacion",
              "ahora", "detalle", "capacidad"):
        assert k in res, k
    #  La sobrecarga se VE en el resumen aunque no se proponga
    assert res["capacidad"]["jornadas_sobrecargadas"]
    assert "H-05" in res["capacidad"]["nota"]
    fila = [f for f in res["detalle"] if f["origen_tipo"] == "jornada"][0]
    for k in ("tipo", "origen_tipo", "origen_id", "evidencia", "resultado",
              "propuesta"):
        assert k in fila, k
    for k in ("accion_propuesta", "motivo", "prioridad", "impacto",
              "nivel_autonomia_requerido", "estado", "conocimiento_version"):
        assert k in fila["propuesta"], k

    #  un técnico no corre el ciclo
    ut, t = _persona(org_a, "USER")
    assert _cli(ut, org_a, t).post(CICLO, {}, format="json").status_code == 403


@pytest.mark.django_db
def test_api_no_hay_segundo_ciclo(org_a):
    """§11: se reutiliza el ciclo que ya existía; no se creó otro."""
    from operaciones import urls as rutas
    nombres = [p.name for p in rutas.urlpatterns]
    assert nombres.count("ciclo") == 1
    assert not [n for n in nombres if n and "ciclo" in n and n != "ciclo"]
