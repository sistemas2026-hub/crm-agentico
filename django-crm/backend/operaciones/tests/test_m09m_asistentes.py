# -*- coding: utf-8 -*-
"""
================================================================================
 M09-M  --  asistentes operativos de Programación y Compromisos
================================================================================

Lo que se verifica no es que los asistentes "funcionen", sino las cuatro cosas
que podrían salir mal sin que nadie lo note:

  * que NO ejecuten nada (se mide sobre TODO lo que podrían tocar);
  * que NO inventen cuando falta un dato (DATOS_INSUFICIENTES, y sin propuesta);
  * que NO abran una segunda cola (la propuesta sigue siendo la de siempre);
  * que digan CON QUÉ HABILIDAD respaldan cada recomendación, y en qué estado
    está esa habilidad -- H-05 sigue BLOQUEADA y su detector sigue corriendo.
================================================================================
"""

from __future__ import annotations

import socket
import threading
from datetime import datetime, time, timedelta
from unittest import mock

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
from operaciones import asistentes, capacidad, habilidades, supervisor
from operaciones.models import (ActividadOperativa, DisponibilidadTecnico,
                                ProgramacionOrden, ProgramacionSemanal,
                                PropuestaSupervisor)
from operaciones.programacion import programar_orden

P = PropuestaSupervisor
A = asistentes
_n = [7000]
_c = [0]


def _hoy():
    return timezone.localtime(timezone.now()).date()


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"m{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


ASISTENTES = "/api/operaciones/asistentes/"


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
    wt = WorkType.objects.create(org=org, codigo=f"m_{_n[0]}", nombre="m")
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


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _identificadores(modulo) -> set[str]:
    """
    Todo nombre que el módulo USA de verdad: imports, llamadas y atributos.
    Leído del AST, no del texto -- un docstring que menciona lo que NO se creó
    no debe contar como si existiera.
    """
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(modulo))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
            for alias in nodo.names:
                nombres.add(alias.asname or alias.name.split(".")[0])
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres.update(nodo.module.split("."))
    return nombres


def _por_senal(salida, tipo):
    return [r for r in salida["recomendaciones"] if r["senal_origen"] == tipo]


# ============================================== 1. programación: recomendación
@pytest.mark.django_db
def test_1_recomendacion_valida_de_programacion(org_a, actor):
    """Una orden sin programar produce una recomendación completa y estructurada."""
    o = _orden(org_a, duracion=120)
    _, p1 = _persona(org_a)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)

    salida = A.asistir(org_a, A.PROGRAMACION)
    rec = _por_senal(salida, P.ORDEN_SIN_PROGRAMAR)
    assert len(rec) == 1
    r = rec[0]

    assert r["tipo"] == "programacion"
    assert r["origen_id"] == str(o.id)
    assert r["resultado"] == A.PROPUESTA
    assert r["propuesta_id"], "no creó la propuesta"
    assert r["requiere_revision_humana"] is True

    #  Las CUATRO cosas separadas, que es el punto del asistente
    assert r["observado"] and all(isinstance(x, str) for x in r["observado"])
    assert r["inferencia"], "sin inferencia declarada"
    assert r["recomendacion"], "sin recomendación"
    assert isinstance(r["datos_faltantes"], list)
    assert r["hallazgo"] in r["observado"]

    #  La habilidad que la sustenta, con su estado
    assert r["habilidad"]["id"] == habilidades.POR_SENAL[P.ORDEN_SIN_PROGRAMAR]
    assert r["habilidad"]["estado"] == habilidades.VIGENTE
    assert r["habilidad"]["referencia"].startswith("habilidad:")

    #  y quedó en la cola de siempre
    prop = P.objects.get(id=r["propuesta_id"])
    assert prop.tipo_senal == P.ORDEN_SIN_PROGRAMAR
    assert prop.estado == P.PROPUESTA
    assert prop.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR


# ============================================== 2. datos insuficientes
@pytest.mark.django_db
def test_2_datos_faltantes_se_nombran(org_a, actor):
    """
    Los datos que faltan se MIDEN sobre la fila. Una orden sin cuadrilla y sin
    duración lo declara campo por campo, en vez de callarlo.
    """
    o = _orden(org_a, duracion=None)          # sin duración declarada
    salida = A.asistir(org_a, A.PROGRAMACION)
    r = _por_senal(salida, P.ORDEN_SIN_PROGRAMAR)[0]

    campos = {f["campo"] for f in r["datos_faltantes"]}
    assert "asignaciones" in campos, "no dijo que no hay cuadrilla"
    assert "duracion_estimada_minutos" in campos, "no dijo que falta la duración"
    for f in r["datos_faltantes"]:
        assert f["por_que"], "un dato faltante sin explicar no sirve"
    assert salida["resumen"]["con_datos_faltantes"] >= 1


@pytest.mark.django_db
def test_2b_sin_analisis_no_se_inventa_recomendacion(org_a, actor):
    """
    LA REGLA. Si el Supervisor no sabe interpretar la señal, el asistente
    devuelve DATOS_INSUFICIENTES y NO crea propuesta. Se prueba DESARMANDO el
    análisis: sin esto, la prueba no sabría fallar.
    """
    o = _orden(org_a, duracion=120)
    n_antes = P.objects.filter(org=org_a).count()

    with mock.patch.object(supervisor, "analizar", return_value={}):
        salida = A.asistir(org_a, A.PROGRAMACION)

    assert salida["resumen"]["datos_insuficientes"] >= 1
    assert salida["resumen"]["propuestas_creadas"] == 0
    assert P.objects.filter(org=org_a).count() == n_antes, (
        "creó una propuesta sin análisis que la sostenga")
    r = _por_senal(salida, P.ORDEN_SIN_PROGRAMAR)[0]
    assert r["resultado"] == A.DATOS_INSUFICIENTES
    assert r["recomendacion"] == "", "rellenó una recomendación que no tenía"
    assert r["inferencia"] == ""
    #  pero lo observado NO se pierde: el hecho ocurrió
    assert r["observado"]


# ============================================== 3. ya programada
@pytest.mark.django_db
def test_3_una_orden_ya_programada_no_genera_recomendacion(org_a, actor):
    o = _orden(org_a, duracion=120)
    _, p1 = _persona(org_a)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)

    salida = A.asistir(org_a, A.PROGRAMACION)
    assert _por_senal(salida, P.ORDEN_SIN_PROGRAMAR) == [], (
        "recomendó programar algo ya programado")


# ============================================== 4. capacidad indeterminada
@pytest.mark.django_db
def test_4_capacidad_indeterminada_no_se_convierte_en_cero(org_a, actor):
    """
    Sin duración, la capacidad no es determinable. El asistente lo declara
    nombrando las órdenes concretas, y NO afirma que la jornada quepa.
    """
    _calendario(org_a)
    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=None)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)

    salida = A.asistir(org_a, A.PROGRAMACION)
    rec = [r for r in _por_senal(salida, P.DATO_INCOMPLETO)
           if r["origen_tipo"] == "jornada"]
    assert len(rec) == 1
    r = rec[0]
    assert r["datos_faltantes"][0]["campo"] == "duracion_estimada_minutos"
    assert f"#{o.numero}" in r["datos_faltantes"][0]["por_que"]
    assert "COTA INFERIOR" in r["inferencia"]
    #  ninguna recomendación afirma que la jornada quepa
    assert not any("cabe" in x["recomendacion"].lower()
                   for x in salida["recomendaciones"])


# ============================================== 5-9. compromisos
@pytest.mark.django_db
def test_5_recomendacion_valida_de_compromiso(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    c = m02.crear(org=org_a, actor=actor, tipo=ActividadOperativa.COMPROMISO,
                  titulo="Llamar al cliente",
                  vence_en=ahora + timedelta(hours=3))
    m02.asignar_responsable(c, actor=actor, responsable=p1)

    salida = A.asistir(org_a, A.COMPROMISOS, ahora)
    r = _por_senal(salida, P.COMPROMISO_POR_VENCER)[0]
    assert r["tipo"] == "compromiso"
    assert r["origen_id"] == str(c.id)
    assert r["recomendacion"] and r["inferencia"] and r["observado"]
    assert r["habilidad"]["estado"] == habilidades.VIGENTE
    assert r["propuesta_id"]


@pytest.mark.django_db
def test_6_compromiso_vencido(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    c = m02.crear(org=org_a, actor=actor, tipo=ActividadOperativa.COMPROMISO,
                  titulo="vencido", vence_en=ahora - timedelta(hours=6))
    m02.asignar_responsable(c, actor=actor, responsable=p1)

    salida = A.asistir(org_a, A.COMPROMISOS, ahora)
    r = _por_senal(salida, P.ACTIVIDAD_VENCIDA)[0]
    assert r["origen_id"] == str(c.id)
    #  no se atribuye culpa: la causa NO está registrada y se dice así
    assert "no está registrada" in r["inferencia"]
    assert r["riesgos"]


@pytest.mark.django_db
def test_7_actividad_bloqueada(org_a, actor):
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="bloqueada")
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    m02.bloquear(a, actor=actor, motivo="falta permiso del municipio")

    salida = A.asistir(org_a, A.COMPROMISOS)
    r = _por_senal(salida, P.ACTIVIDAD_BLOQUEADA)[0]
    assert "falta permiso del municipio" in r["inferencia"]
    #  el motivo existe, así que NO figura como dato faltante
    assert "motivo_bloqueo" not in {f["campo"] for f in r["datos_faltantes"]}


@pytest.mark.django_db
def test_8_dependencia_pendiente(org_a, actor):
    _, p1 = _persona(org_a)
    previa = m02.crear(org=org_a, actor=actor, titulo="Conseguir permiso")
    a = m02.crear(org=org_a, actor=actor, titulo="Instalar poste")
    for x in (previa, a):
        m02.asignar_responsable(x, actor=actor, responsable=p1)
    m02.establecer_dependencia(a, actor=actor, depende_de=previa)

    salida = A.asistir(org_a, A.COMPROMISOS)
    r = _por_senal(salida, P.DEPENDENCIA_PENDIENTE)[0]
    assert r["origen_id"] == str(a.id)
    assert len(r["dependencias"]) == 1
    assert r["dependencias"][0]["actividad"] == str(previa.id)
    assert r["dependencias"][0]["resuelta"] is False


@pytest.mark.django_db
def test_9_responsable_ausente(org_a, actor):
    """Sin responsable: es una señal, y el dato faltante se nombra."""
    a = m02.crear(org=org_a, actor=actor, titulo="sin dueño")

    salida = A.asistir(org_a, A.COMPROMISOS)
    r = _por_senal(salida, P.ACTIVIDAD_SIN_RESPONSABLE)[0]
    assert r["origen_id"] == str(a.id)
    campos = {f["campo"] for f in r["datos_faltantes"]}
    assert "responsable" in campos
    assert "vence_en" in campos, "no dijo que tampoco hay fecha comprometida"
    #  y NO inventa a quién asignársela
    assert "responsable_sugerido" not in r


# ============================================== 10. evidencia
@pytest.mark.django_db
def test_10_evidencia_vacia_se_rechaza(org_a, actor):
    a = m02.crear(org=org_a, actor=actor, titulo="x")
    A.asistir(org_a, A.COMPROMISOS)
    for prop in P.objects.filter(org=org_a):
        assert prop.evidencia, f"{prop.tipo_senal} sin evidencia"

    vacia = supervisor.Senal(tipo=P.ACTIVIDAD_VENCIDA, origen_tipo="actividad",
                             origen_id=str(a.id), evidencia=[], datos={},
                             huella="h")
    with pytest.raises(ValueError, match="sin evidencia"):
        supervisor.registrar_propuesta(org_a, vacia, {"accion_propuesta": "x",
                                                      "motivo": "y",
                                                      "prioridad": 50})


# ============================================== 11. deduplicación
@pytest.mark.django_db
def test_11_deduplicacion(org_a, actor):
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="sin dueño")

    s1 = A.asistir(org_a, A.COMPROMISOS)
    assert s1["resumen"]["propuestas_creadas"] >= 1
    n = P.objects.filter(org=org_a).count()

    s2 = A.asistir(org_a, A.COMPROMISOS)
    assert s2["resumen"]["repetidas"] >= 1
    assert s2["resumen"]["propuestas_creadas"] == 0
    assert P.objects.filter(org=org_a).count() == n, "duplicó la propuesta"
    #  el hecho sigue apareciendo aunque la pregunta no se repita
    r = _por_senal(s2, P.ACTIVIDAD_SIN_RESPONSABLE)[0]
    assert r["resultado"] == A.REPETIDA and r["propuesta_id"] is None

    #  y el ciclo completo tampoco la duplica: comparten el registrador
    supervisor.correr_ciclo(org_a)
    assert P.objects.filter(org=org_a).count() == n


# ============================================== 12. concurrencia
@pytest.mark.django_db(transaction=True)
def test_12_dos_asistentes_simultaneos(org_a):
    """
    El asistente es una frontera NUEVA de creación de propuestas, así que se
    mide de verdad. Se serializa con el mismo lock de organización de M09-L.
    """
    _, act_p = _persona(org_a, "OPERACIONES")
    m02.crear(org=org_a, actor=act_p, titulo="sin dueño")

    barrera = threading.Barrier(2)
    fallos = []

    def corre():
        try:
            barrera.wait(timeout=10)
            A.asistir(org_a, A.COMPROMISOS)
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
    assert not {k: v for k, v in por_huella.items() if v > 1}, (
        f"dos asistentes simultáneos duplicaron: {por_huella}")


# ============================================== 13. tenant
@pytest.mark.django_db
def test_13_aislamiento_entre_tenants(org_a, org_b, actor):
    _, actor_b = _persona(org_b, "OPERACIONES")
    mia = m02.crear(org=org_a, actor=actor, titulo="de A")
    ajena = m02.crear(org=org_b, actor=actor_b, titulo="de B")

    salida = A.asistir(org_a, A.COMPROMISOS)
    ids = {r["origen_id"] for r in salida["recomendaciones"]}
    assert str(mia.id) in ids and str(ajena.id) not in ids
    assert salida["organizacion"]["id"] == str(org_a.id)
    assert P.objects.filter(org=org_b).count() == 0, "escribió en el otro tenant"

    #  por HTTP, cada quien el suyo
    ug, g = _persona(org_a, "OPERACIONES")
    r = _cli(ug, org_a, g).post(ASISTENTES, {"dominio": "compromiso"},
                                format="json")
    assert r.status_code == 200
    assert r.data["organizacion"]["id"] == str(org_a.id)


# ============================================== 14. sin capacidad de ejecutar
@pytest.mark.django_db
def test_14_el_asistente_no_tiene_con_que_ejecutar(org_a, actor):
    """
    El interruptor de autonomía vive en el motor, no aquí -- lo dice el propio
    'habilidades.py'. Así que la pregunta correcta no es si algo lo apaga, sino
    si hay algo que apagar: se comprueba que el módulo NO importa ningún
    servicio de escritura operativa, y que una pasada no cambia nada.
    """
    usados = _identificadores(asistentes)
    #  Ningún servicio de escritura operativa, ningún sistema externo, ninguna
    #  cola. Se miran identificadores reales, no el texto del archivo.
    assert usados.isdisjoint({
        "programar_orden", "reprogramar_orden", "registrar_contingencia",
        "actualizar_secuencia", "secuenciar_jornada", "publicar_programacion",
        "asignar", "agregar_integrante", "cambiar_principal",
        "retirar_integrante", "desasignar", "completar", "cancelar",
        "bloquear", "validar", "crear",
        "requests", "httpx", "urllib", "celery", "apply_async", "shared_task",
    }), sorted(usados & {"programar_orden", "asignar", "completar", "requests"})

    #  tampoco puede aprobar sus propias propuestas ni subirse el nivel
    assert usados.isdisjoint({"revisar", "ACEPTADA", "ejecutar_propuesta"})

    #  y ningún sistema externo, ni siquiera nombrado en una cadena
    import inspect
    fuente = inspect.getsource(asistentes).lower()
    for externo in ("wisphub", "smartolt", "whatsapp"):
        assert externo not in fuente, externo


@pytest.mark.django_db
def test_14b_una_pasada_no_ejecuta_nada(org_a, actor):
    """Se mide sobre TODO lo que el asistente podría tocar."""
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    #  'dia' explícito, y no el de por defecto (mañana): con mañana, esta
    #  prueba dependía del día de la semana. 'programacion_sin_publicar' exige
    #  'semana_inicio <= hoy', y en DOMINGO mañana es lunes, así que el plan
    #  cae en una semana que todavía no empezó, no hay señal de programación y
    #  la aserción de abajo falla -- 6 de 7 días en verde, 1 en rojo, por el
    #  calendario y no por el código. Con un día de ESTA semana, el lunes que
    #  la abre siempre es <= hoy.
    _programar(org_a, o, actor, dia=_hoy())

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
    s1 = A.asistir(org_a, A.PROGRAMACION, ahora)
    s2 = A.asistir(org_a, A.COMPROMISOS, ahora)
    assert s1["resumen"]["recomendaciones"] > 0
    assert s2["resumen"]["recomendaciones"] > 0
    assert foto() == antes, "el asistente modificó datos operativos"

    for prop in P.objects.filter(org=org_a):
        assert prop.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR
        assert prop.estado == P.PROPUESTA
        assert prop.revisado_por_id is None


# ============================================== 15. efectos externos
@pytest.mark.django_db
def test_15_sin_efectos_externos(org_a, actor):
    ahora = timezone.now()
    _calendario(org_a)
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)

    salidas = []
    original = socket.socket.connect

    def espia(self, addr, *a2, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("pg-m9m", "127.0.0.1", "localhost", "::1"):
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
        s1 = A.asistir(org_a, A.PROGRAMACION, ahora)
        s2 = A.asistir(org_a, A.COMPROMISOS, ahora)
        assert s1["resumen"]["recomendaciones"] > 0
        assert s2["resumen"]["recomendaciones"] > 0
    finally:
        socket.socket.connect = original

    assert salidas == [], f"hubo llamadas externas: {salidas}"


# ============================================== 16. revisión humana
@pytest.mark.django_db
def test_16_revision_humana_obligatoria(org_a, actor):
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    salida = A.asistir(org_a, A.COMPROMISOS)
    assert all(r["requiere_revision_humana"] for r in salida["recomendaciones"])

    prop = P.objects.filter(org=org_a).first()
    assert prop.estado == P.PROPUESTA and prop.revisado_por_id is None

    ug, g = _persona(org_a, "OPERACIONES")
    r = _cli(ug, org_a, g).post(
        f"/api/operaciones/propuestas/{prop.id}/revisar/",
        {"decision": P.ACEPTADA}, format="json")
    assert r.status_code == 200, r.data
    prop.refresh_from_db()
    assert prop.revisado_por_id == g.id

    #  un técnico ni revisa ni corre el asistente
    ut, t = _persona(org_a, "USER")
    cli_t = _cli(ut, org_a, t)
    assert cli_t.post(ASISTENTES, {"dominio": "compromiso"},
                      format="json").status_code == 403
    assert cli_t.post(f"/api/operaciones/propuestas/{prop.id}/revisar/",
                      {"decision": P.RECHAZADA}, format="json").status_code == 403


# ============================================== 17-18. sin sistemas paralelos
@pytest.mark.django_db
def test_17_18_no_hay_segunda_cola_ni_task(org_a, actor):
    """
    §E y §C: la propuesta sigue siendo PropuestaSupervisor, y no aparece ningún
    modelo nuevo. Se lee la app REAL, no la memoria de quien lo escribió.
    """
    from django.apps import apps
    modelos = {m.__name__ for m in apps.get_app_config("operaciones").get_models()}
    assert modelos == {"ActividadOperativa", "DisponibilidadTecnico",
                       "ProgramacionSemanal", "ProgramacionOrden",
                       "NovedadOperativa", "PropuestaSupervisor"}, modelos

    #  Se miran los IDENTIFICADORES del código, no el texto del archivo: los
    #  docstrings nombran justamente lo que NO se creó, y un 'in fuente' los
    #  contaría como si existieran.
    assert _identificadores(asistentes).isdisjoint({
        "AssistantTask", "AIRecommendation", "AssistantQueue", "Task",
        "acciones_propuestas", "revisiones_supervisor"})

    #  y lo que produce vive en la cola de siempre
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    salida = A.asistir(org_a, A.COMPROMISOS)
    creadas = [r for r in salida["recomendaciones"] if r["propuesta_id"]]
    assert creadas
    for r in creadas:
        assert P.objects.filter(id=r["propuesta_id"], org=org_a).exists()


# ============================================== habilidades
@pytest.mark.django_db
def test_habilidades_ni_nuevas_ni_ocultas(org_a, actor):
    """
    §D: ninguna habilidad nueva. Y cada recomendación declara con cuál se
    sostiene Y en qué estado está -- H-05 sigue BLOQUEADA.
    """
    #  Eran 14 en M09-M. M04-A agrega H-11 y H-12 (plazo operativo de una
    #  orden) CON autorizacion explicita; las 14 originales no se tocaron y sus
    #  huellas de M09-K siguen valiendo.
    #  M04-A agrego H-11/H-12 y M05-A agrega H-13, las tres con autorizacion explicita.
    #  M09-M dejo 14. Despues se agregaron, con autorizacion explicita: H-11/H-12 (M04-A), H-13 (M05-A) y H-14 (M05-B).
    assert len(habilidades.HABILIDADES) == 18, "se creó una habilidad no prevista"
    assert habilidades.HABILIDADES["H-05"].estado == habilidades.BLOQUEADA

    _, p1 = _persona(org_a)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)
    _programar(org_a, o, actor)
    DisponibilidadTecnico.objects.create(
        org=org_a, profile=p1, fecha=_hoy() + timedelta(days=1),
        hora_inicio=time(8, 0), hora_fin=time(16, 0), disponible=False,
        motivo="incapacidad")

    salida = A.asistir(org_a, A.PROGRAMACION)
    riesgo = _por_senal(salida, P.ORDEN_EN_RIESGO)
    assert riesgo, "no llegó la señal de riesgo operacional"
    r = riesgo[0]
    assert r["habilidad"]["id"] == "H-05"
    assert r["habilidad"]["estado"] == habilidades.BLOQUEADA
    #  y el riesgo de apoyarse en una ficha bloqueada se DICE
    assert any("BLOQUEADA" in x for x in r["riesgos"]), (
        "no avisó que la habilidad que la sustenta está bloqueada")
    assert salida["resumen"]["con_habilidad_bloqueada"] >= 1

    for rec in salida["recomendaciones"]:
        assert rec["habilidad"]["id"], f"{rec['senal_origen']} sin ficha"


# ============================================== API
@pytest.mark.django_db
def test_api_los_dos_asistentes(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="vencida",
                  vence_en=ahora - timedelta(hours=2))
    m02.asignar_responsable(a, actor=actor, responsable=p1)
    o = _orden(org_a, duracion=120)
    AsignacionTrabajo.objects.create(orden=o, profile=p1, es_principal=True)

    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)

    for dominio, senal in (("programacion", P.ORDEN_SIN_PROGRAMAR),
                           ("compromiso", P.ACTIVIDAD_VENCIDA)):
        r = cli.post(ASISTENTES, {"dominio": dominio}, format="json")
        assert r.status_code == 200, r.data
        assert r.data["asistente"] == dominio
        for k in ("organizacion", "ahora", "resumen", "recomendaciones"):
            assert k in r.data, k
        rec = [x for x in r.data["recomendaciones"]
               if x["senal_origen"] == senal][0]
        for k in ("hallazgo", "observado", "inferencia", "recomendacion",
                  "evidencia", "datos_faltantes", "riesgos", "habilidad",
                  "requiere_revision_humana", "resultado"):
            assert k in rec, k

    #  un dominio que no existe se rechaza
    r = cli.post(ASISTENTES, {"dominio": "inventado"}, format="json")
    assert r.status_code == 400 and r.data["error"] == "ASISTENTE_DESCONOCIDO"


@pytest.mark.django_db
def test_api_idempotencia(org_a, actor):
    m02.crear(org=org_a, actor=actor, titulo="sin dueño")
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)

    r1 = cli.post(ASISTENTES, {"dominio": "compromiso"}, format="json",
                  HTTP_IDEMPOTENCY_KEY="m9m-1")
    r2 = cli.post(ASISTENTES, {"dominio": "compromiso"}, format="json",
                  HTTP_IDEMPOTENCY_KEY="m9m-1")
    assert r1.status_code == 200 and r2.status_code == 200
    assert P.objects.filter(org=org_a,
                            tipo_senal=P.ACTIVIDAD_SIN_RESPONSABLE).count() == 1
