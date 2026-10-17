# -*- coding: utf-8 -*-
"""
================================================================================
 M02  --  actividades, pendientes y compromisos
================================================================================

La entidad ya existía. Lo que estas pruebas verifican es la capa que faltaba:
que se pueda crear, mover entre estados y consultar SIN romper las dos cosas
que ya estaban vivas alrededor -- la semántica de common.Activity y los cinco
detectores de M09 que leen esta tabla.

Se afirma sobre el EFECTO y sobre la persistencia real, no sobre HTTP 200.
================================================================================
"""

from __future__ import annotations

import socket
import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from common.models import Activity, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import actividades as act
from operaciones import auditoria, supervisor
from operaciones.models import (APROBADO, REQUIERE_CORRECCION, SIN_EVALUAR,
                                VALIDACION_PENDIENTE, ActividadOperativa,
                                PropuestaSupervisor)

A = ActividadOperativa
URL = "/api/operaciones/actividades/"
_c = [0]


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"m2_{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cli(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _crear(org, actor, **kw):
    kw.setdefault("titulo", "Revisar caja NAP 12")
    return act.crear(org=org, actor=actor, **kw)


# ==================================================== 1-3. crear
@pytest.mark.django_db
def test_1_crear_pendiente(org_a, actor):
    a = _crear(org_a, actor, tipo=A.PENDIENTE_T)
    assert a.estado_operativo == A.PENDIENTE
    assert a.estado_validacion == SIN_EVALUAR
    assert a.responsable is None
    assert a.vence_en is None
    assert a.completado_en is None and a.validado_en is None
    assert a.vuelta == 1


@pytest.mark.django_db
def test_2_crear_compromiso_con_y_sin_fecha(org_a, actor):
    cuando = timezone.now() + timedelta(days=2)
    con = _crear(org_a, actor, tipo=A.COMPROMISO, titulo="Llamar al cliente",
                 vence_en=cuando)
    assert con.tipo == A.COMPROMISO and con.vence_en == cuando

    #  Un compromiso sin fecha es legitimo y NO se le inventa una
    sin = _crear(org_a, actor, tipo=A.COMPROMISO, titulo="Confirmar materiales")
    assert sin.vence_en is None
    assert act.clasificar_vencimiento(sin) == act.SIN_VENCIMIENTO


@pytest.mark.django_db
def test_3_los_nueve_tipos(org_a, actor):
    for tipo, _etiqueta in A.TIPOS:
        a = _crear(org_a, actor, tipo=tipo, titulo=f"t {tipo}",
                   origen_tipo="manual", origen_id=f"x-{tipo}")
        assert a.tipo == tipo
    assert A.objects.filter(org=org_a).count() == len(A.TIPOS)

    with pytest.raises(act.ErrorActividad, match="no es un tipo"):
        _crear(org_a, actor, tipo="inventado")
    with pytest.raises(act.ErrorActividad, match="sin título"):
        _crear(org_a, actor, titulo="   ")


# ==================================================== 4-5, 18. responsable
@pytest.mark.django_db
def test_4_5_18_responsable(org_a, actor):
    a = _crear(org_a, actor)
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)

    #  5. sin responsable es un estado legitimo, no un error
    assert a.responsable is None

    a, cambio = act.asignar_responsable(a, actor=actor, responsable=p1)
    assert cambio and a.responsable == p1

    #  reasignar al mismo es un no-op: ni escribe ni audita
    n = Activity.objects.filter(entity_id=a.id, action="ASSIGN").count()
    a, cambio = act.asignar_responsable(a, actor=actor, responsable=p1)
    assert cambio is False
    assert Activity.objects.filter(entity_id=a.id, action="ASSIGN").count() == n

    #  18. cambio de responsable
    a, cambio = act.asignar_responsable(a, actor=actor, responsable=p2,
                                        motivo="rota de turno")
    assert cambio and a.responsable == p2

    #  quitarlo tambien es legitimo
    a, cambio = act.asignar_responsable(a, actor=actor, responsable=None)
    assert cambio and a.responsable is None


@pytest.mark.django_db
def test_4b_responsable_de_otra_empresa_se_rechaza(org_a, org_b, actor):
    a = _crear(org_a, actor)
    _, ajeno = _persona(org_b)
    with pytest.raises(act.ErrorActividad, match="otra empresa"):
        act.asignar_responsable(a, actor=actor, responsable=ajeno)


# ==================================================== 6-9. estados
@pytest.mark.django_db
def test_6_iniciar_gestion(org_a, actor):
    a = _crear(org_a, actor)
    a = act.iniciar_gestion(a, actor=actor)
    assert a.estado_operativo == A.EN_GESTION


@pytest.mark.django_db
def test_7_poner_en_espera(org_a, actor):
    a = act.poner_en_espera(_crear(org_a, actor), actor=actor,
                            motivo="espera respuesta del cliente")
    assert a.estado_operativo == A.EN_ESPERA


@pytest.mark.django_db
def test_8_bloquear_exige_motivo(org_a, actor):
    a = _crear(org_a, actor)
    with pytest.raises(act.ErrorActividad, match="necesita su causa"):
        act.bloquear(a, actor=actor, motivo="   ")
    a = act.bloquear(a, actor=actor, motivo="falta material en bodega")
    assert a.estado_operativo == A.BLOQUEADA
    assert a.motivo_bloqueo == "falta material en bodega"

    #  y no se puede saltar el desbloqueo
    with pytest.raises(act.ErrorActividad, match="bloqueada"):
        act.iniciar_gestion(a, actor=actor)


@pytest.mark.django_db
def test_9_desbloquear_limpia_el_motivo(org_a, actor):
    a = act.bloquear(_crear(org_a, actor), actor=actor, motivo="falta permiso")
    a = act.desbloquear(a, actor=actor, motivo="permiso concedido")
    assert a.estado_operativo == A.EN_GESTION
    assert a.motivo_bloqueo == "", "quedó dicho que sigue bloqueada por algo"

    with pytest.raises(act.ErrorActividad, match="no está bloqueada"):
        act.desbloquear(a, actor=actor)


@pytest.mark.django_db
def test_9b_escalar_exige_motivo(org_a, actor):
    #  M05-B agrego destinatario y nivel como obligatorios. Esta prueba sigue
    #  afirmando lo suyo --que sin motivo no se escala-- y ahora pasa los tres.
    a = _crear(org_a, actor)
    with pytest.raises(act.ErrorActividad, match="necesita su motivo"):
        act.escalar(a, actor=actor, motivo="", escalado_a=actor,
                    nivel=A.NIVEL_1)
    a = act.escalar(a, actor=actor, motivo="supera el nivel 1",
                    escalado_a=actor, nivel=A.NIVEL_1)
    assert a.estado_operativo == A.ESCALADA


@pytest.mark.django_db
def test_9c_transiciones_invalidas(org_a, actor):
    """Cancelada es terminal de verdad: de ahí no se sale."""
    a = act.cancelar(_crear(org_a, actor), actor=actor, motivo="ya no aplica")
    for fn in (lambda: act.iniciar_gestion(a, actor=actor),
               lambda: act.completar(a, actor=actor),
               lambda: act.escalar(a, actor=actor, motivo="x",
                                   escalado_a=actor, nivel=A.NIVEL_1)):
        with pytest.raises(act.TransicionInvalida):
            fn()


# ==================================================== 10-12. completar/validar
@pytest.mark.django_db
def test_10_completar_sin_validacion(org_a, actor):
    a = act.completar(_crear(org_a, actor), actor=actor)
    assert a.estado_operativo == A.COMPLETADA
    assert a.completado_en is not None
    assert a.estado_validacion == SIN_EVALUAR


@pytest.mark.django_db
def test_11_completar_no_es_cerrar(org_a, actor):
    """
    LA REGLA de §13: completada + validación pendiente sigue viva. Y una
    devolución no borra lo hecho: sube 'vuelta' y vuelve a gestión.
    """
    a = act.completar(_crear(org_a, actor), actor=actor,
                      requiere_validacion=True)
    assert a.estado_operativo == A.COMPLETADA
    assert a.estado_validacion == VALIDACION_PENDIENTE
    assert a.validado_en is None, "se dio por validada al completar"

    #  sigue visible para quien valida
    esperando = act.pendientes_relevantes(org_a, solo_abiertas=False)
    assert a.id in {x.id for x in esperando}

    #  devolución
    with pytest.raises(act.ErrorActividad, match="qué corregir"):
        act.validar(a, actor=actor, decision=REQUIERE_CORRECCION)
    a = act.validar(a, actor=actor, decision=REQUIERE_CORRECCION,
                    motivo="falta la foto del empalme")
    assert a.vuelta == 2
    assert a.estado_operativo == A.EN_GESTION
    assert a.completado_en is None and a.validado_en is None

    #  segunda vuelta, ahora aprobada
    a = act.completar(a, actor=actor, requiere_validacion=True)
    a = act.validar(a, actor=actor, decision=APROBADO)
    assert a.estado_validacion == APROBADO
    assert a.validado_en is not None and a.completado_en is not None


@pytest.mark.django_db
def test_11b_no_se_valida_lo_que_no_espera_validacion(org_a, actor):
    a = _crear(org_a, actor)
    with pytest.raises(act.ErrorActividad, match="no está esperando validación"):
        act.validar(a, actor=actor, decision=APROBADO)


@pytest.mark.django_db
def test_12_cancelar_no_es_completar(org_a, actor):
    a = _crear(org_a, actor)
    with pytest.raises(act.ErrorActividad, match="necesita su motivo"):
        act.cancelar(a, actor=actor, motivo="")
    a = act.cancelar(a, actor=actor, motivo="el cliente desistió")
    assert a.estado_operativo == A.CANCELADA
    assert a.completado_en is None, "una cancelación se contó como completada"
    #  no se borra: la fila sigue, con su rastro
    assert A.objects.filter(id=a.id).exists()
    ev = Activity.objects.filter(entity_id=a.id).order_by("-created_at").first()
    assert ev.metadata.get("motivo") == "el cliente desistió"
    assert ev.user_id == actor.id


# ==================================================== 13-15. dependencias
@pytest.mark.django_db
def test_13_14_dependencia_y_su_resolucion(org_a, actor):
    previa = _crear(org_a, actor, titulo="Conseguir permiso")
    a = _crear(org_a, actor, titulo="Instalar poste")
    a, cambio = act.establecer_dependencia(a, actor=actor, depende_de=previa)
    assert cambio and a.depende_de_id == previa.id
    assert a.bloqueada_por_dependencia is True

    #  no se puede completar mientras la otra no termine
    with pytest.raises(act.ErrorActividad, match="todavía no termina"):
        act.completar(a, actor=actor)

    #  14. resuelta la dependencia, avanza
    act.completar(previa, actor=actor)
    a.refresh_from_db()
    assert a.bloqueada_por_dependencia is False
    a = act.completar(a, actor=actor)
    assert a.estado_operativo == A.COMPLETADA


@pytest.mark.django_db
def test_15_ciclos_de_dependencia_se_rechazan(org_a, actor):
    a = _crear(org_a, actor, titulo="A")
    b = _crear(org_a, actor, titulo="B")
    c = _crear(org_a, actor, titulo="C")

    #  ciclo de largo 1
    with pytest.raises(act.DependenciaCiclica, match="de sí misma"):
        act.establecer_dependencia(a, actor=actor, depende_de=a)

    #  ciclo de largo 2:  a -> b, y b -> a
    act.establecer_dependencia(a, actor=actor, depende_de=b)
    with pytest.raises(act.DependenciaCiclica, match="círculo"):
        act.establecer_dependencia(b, actor=actor, depende_de=a)

    #  ciclo de largo 3:  a -> b -> c, y c -> a
    act.establecer_dependencia(b, actor=actor, depende_de=c)
    with pytest.raises(act.DependenciaCiclica, match="círculo"):
        act.establecer_dependencia(c, actor=actor, depende_de=a)

    #  y la cadena legítima sigue intacta
    a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
    assert (a.depende_de_id, b.depende_de_id, c.depende_de_id) == (b.id, c.id, None)


@pytest.mark.django_db
def test_15b_dependencia_de_otra_empresa_se_rechaza(org_a, org_b, actor):
    a = _crear(org_a, actor)
    _, actor_b = _persona(org_b, "OPERACIONES")
    ajena = _crear(org_b, actor_b, titulo="de la otra empresa")
    with pytest.raises(act.ErrorActividad, match="otra empresa"):
        act.establecer_dependencia(a, actor=actor, depende_de=ajena)


# ==================================================== 16-17. vencimientos
@pytest.mark.django_db
def test_16_17_clasificacion_de_vencimiento(org_a, actor):
    ahora = timezone.now()
    casos = [
        (ahora - timedelta(hours=3), act.VENCIDA),
        (ahora + timedelta(hours=2), act.VENCE_PRONTO),
        (ahora + timedelta(days=30), act.A_TIEMPO),
        (None, act.SIN_VENCIMIENTO),
    ]
    for vence, esperado in casos:
        a = _crear(org_a, actor, vence_en=vence, titulo=f"t {esperado}")
        assert act.clasificar_vencimiento(a, ahora) == esperado, esperado

    #  una cerrada no está "vencida" aunque su fecha haya pasado
    vieja = _crear(org_a, actor, vence_en=ahora - timedelta(days=5))
    vieja = act.completar(vieja, actor=actor)
    assert act.clasificar_vencimiento(vieja, ahora) == act.CERRADA

    #  la ventana es EXPLÍCITA: con 1 hora, lo de 2 horas ya no vence pronto
    a2 = _crear(org_a, actor, vence_en=ahora + timedelta(hours=2))
    assert act.clasificar_vencimiento(a2, ahora, ventana_horas=1) == act.A_TIEMPO


@pytest.mark.django_db
def test_17b_cambiar_vencimiento_queda_auditado(org_a, actor):
    nueva = timezone.now() + timedelta(days=3)
    a = _crear(org_a, actor)
    a, cambio = act.cambiar_vencimiento(a, actor=actor, vence_en=nueva,
                                        motivo="el cliente pidió otra fecha")
    assert cambio and a.vence_en == nueva
    a, cambio = act.cambiar_vencimiento(a, actor=actor, vence_en=nueva)
    assert cambio is False, "reescribió la misma fecha"

    ev = Activity.objects.filter(entity_id=a.id, action="UPDATE").first()
    assert ev.metadata["nueva"] == nueva.isoformat()
    assert ev.metadata["anterior"] is None


# ==================================================== 19. auditoría
@pytest.mark.django_db
def test_19_auditoria_completa(org_a, actor):
    """Cada operación deja su hecho en common.Activity, con actor y momento."""
    _, p1 = _persona(org_a)
    a = _crear(org_a, actor, titulo="Cambiar ONT")
    act.asignar_responsable(a, actor=actor, responsable=p1)
    a = act.iniciar_gestion(a, actor=actor)
    a = act.bloquear(a, actor=actor, motivo="sin equipo en bodega")
    a = act.desbloquear(a, actor=actor, motivo="llegó el equipo")
    act.cambiar_vencimiento(a, actor=actor,
                            vence_en=timezone.now() + timedelta(days=1))
    a = act.completar(a, actor=actor, requiere_validacion=True)
    a = act.validar(a, actor=actor, decision=APROBADO)

    eventos = list(auditoria.historial(
        org_a, auditoria.ENTIDAD_ACTIVIDAD, a.id).order_by("created_at"))
    acciones = [e.action for e in eventos]
    assert acciones == ["CREATE", "ASSIGN", "STATUS_CHANGED", "STATUS_CHANGED",
                        "STATUS_CHANGED", "UPDATE", "STATUS_CHANGED",
                        "APPROVED"], acciones
    for e in eventos:
        assert e.org_id == org_a.id
        assert e.user_id == actor.id
        assert e.entity_type == auditoria.ENTIDAD_ACTIVIDAD
        assert e.created_at is not None

    bloqueo = [e for e in eventos if e.metadata.get("estado_nuevo") == A.BLOQUEADA][0]
    assert bloqueo.metadata["estado_anterior"] == A.EN_GESTION
    assert bloqueo.metadata["motivo"] == "sin equipo en bodega"


# ==================================================== 20. concurrencia
@pytest.mark.django_db(transaction=True)
def test_20_completar_y_cancelar_a_la_vez(org_a):
    """
    Dos personas cierran la misma actividad de formas distintas. Con el lock
    una gana y la otra recibe TransicionInvalida -- nunca las dos.
    """
    _, act_p = _persona(org_a, "OPERACIONES")
    a = _crear(org_a, act_p)
    barrera = threading.Barrier(2)
    errores, oks = [], []

    def corre(fn, etiqueta):
        try:
            barrera.wait(timeout=10)
            fn()
            oks.append(etiqueta)
        except Exception as e:
            errores.append(type(e).__name__)
        finally:
            connection.close()

    hs = [
        threading.Thread(target=corre,
                         args=(lambda: act.completar(a, actor=act_p), "completar")),
        threading.Thread(target=corre,
                         args=(lambda: act.cancelar(a, actor=act_p, motivo="x"),
                               "cancelar")),
    ]
    for h in hs: h.start()
    for h in hs: h.join(timeout=30)

    a.refresh_from_db()
    assert len(oks) == 1, f"las dos pasaron: {oks}"
    assert errores == ["TransicionInvalida"], errores
    assert a.estado_operativo in (A.COMPLETADA, A.CANCELADA)


# ==================================================== 21. idempotencia
@pytest.mark.django_db
def test_21_idempotencia(org_a):
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    cuerpo = {"titulo": "Revisar NAP", "tipo": "tarea",
              "origen_tipo": "case", "origen_id": "C-1"}

    r1 = cli.post(URL, cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="m2-21")
    r2 = cli.post(URL, cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="m2-21")
    assert r1.status_code == 201 and r2.status_code == 201
    assert A.objects.filter(org=org_a).count() == 1, "el replay creó dos"

    r3 = cli.post(URL, {"titulo": "Otra cosa"}, format="json",
                  HTTP_IDEMPOTENCY_KEY="m2-21")
    assert r3.status_code == 409
    assert r3.data["error"] == "IDEMPOTENCY_KEY_REUSED"
    assert A.objects.filter(org=org_a).count() == 1


@pytest.mark.django_db
def test_21b_duplicados_por_origen(org_a, actor):
    """§23: no dos actividades vivas iguales para el mismo origen."""
    _crear(org_a, actor, tipo=A.TAREA, origen_tipo="case", origen_id="C-9")
    with pytest.raises(act.ActividadDuplicada):
        _crear(org_a, actor, tipo=A.TAREA, origen_tipo="case", origen_id="C-9")

    #  otro TIPO sobre el mismo origen sí es legítimo
    otra = _crear(org_a, actor, tipo=A.COMPROMISO, origen_tipo="case",
                  origen_id="C-9")
    assert otra.id
    #  y cerrada la primera, se puede volver a abrir una igual
    primera = A.objects.get(org=org_a, tipo=A.TAREA, origen_id="C-9")
    act.cancelar(primera, actor=actor, motivo="ya no aplica")
    assert _crear(org_a, actor, tipo=A.TAREA, origen_tipo="case",
                  origen_id="C-9").id


# ==================================================== 22-23. tenant y permisos
@pytest.mark.django_db
def test_22_aislamiento_entre_tenants(org_a, org_b, actor):
    _, actor_b = _persona(org_b, "OPERACIONES")
    mia = _crear(org_a, actor, titulo="de A")
    ajena = _crear(org_b, actor_b, titulo="de B")

    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)

    r = cli.get(URL)
    ids = {x["id"] for x in r.data["resultados"]}
    assert str(mia.id) in ids and str(ajena.id) not in ids

    #  el detalle de la otra empresa no existe para mí
    assert cli.get(f"{URL}{ajena.id}/").status_code == 404
    r = cli.post(f"{URL}{ajena.id}/transicion/", {"accion": "iniciar"},
                 format="json")
    assert r.status_code == 404
    ajena.refresh_from_db()
    assert ajena.estado_operativo == A.PENDIENTE, "la tocó desde otro tenant"

    #  el cliente no puede elegir la organización
    r = cli.post(URL, {"titulo": "intento", "org": str(org_b.id),
                       "organization_id": str(org_b.id)}, format="json")
    assert r.status_code == 201
    assert A.objects.get(id=r.data["actividad"]["id"]).org_id == org_a.id


@pytest.mark.django_db
def test_23_permisos(org_a, actor):
    a = _crear(org_a, actor)
    ut, t = _persona(org_a, "USER")
    cli = _cli(ut, org_a, t)
    assert cli.get(URL).status_code == 403
    assert cli.post(URL, {"titulo": "x"}, format="json").status_code == 403
    assert cli.post(f"{URL}{a.id}/transicion/", {"accion": "iniciar"},
                    format="json").status_code == 403
    a.refresh_from_db()
    assert a.estado_operativo == A.PENDIENTE

    ug, g = _persona(org_a, "OPERACIONES")
    assert _cli(ug, org_a, g).get(URL).status_code == 200


# ==================================================== 24. Activity intacta
@pytest.mark.django_db
def test_24_common_activity_conserva_su_semantica(org_a, actor):
    """
    M02 ESCRIBE en Activity hechos en pasado; no la usa como agenda.

    Se comprueba lo que el propio auditoria.py advierte que es el riesgo: un
    'entity_type' o un 'action' sin declarar se guarda igual y queda
    divergiendo en silencio.
    """
    validos_accion = {v for v, _ in Activity.ACTION_CHOICES}
    validos_entidad = {v for v, _ in Activity.ENTITY_TYPE_CHOICES}

    a = _crear(org_a, actor)
    act.asignar_responsable(a, actor=actor, responsable=_persona(org_a)[1])
    a = act.iniciar_gestion(a, actor=actor)
    a = act.completar(a, actor=actor, requiere_validacion=True)
    act.validar(a, actor=actor, decision=APROBADO)

    filas = Activity.objects.filter(org=org_a)
    assert filas.exists()
    for e in filas:
        assert e.action in validos_accion, f"verbo no declarado: {e.action}"
        assert e.entity_type in validos_entidad, e.entity_type
        assert e.entity_type == auditoria.ENTIDAD_ACTIVIDAD

    #  Activity no lleva estado ni vencimiento: no es una agenda
    campos = {f.name for f in Activity._meta.get_fields()}
    for prohibido in ("estado_operativo", "vence_en", "responsable",
                      "depende_de", "motivo_bloqueo"):
        assert prohibido not in campos, (
            f"common.Activity ganó '{prohibido}': se está volviendo una agenda")

    #  y lo que falta hacer NO se busca en Activity
    assert A.objects.filter(org=org_a).count() == 1


# ==================================================== 25-26. M09
@pytest.mark.django_db
def test_25_los_detectores_de_m09_consumen_m02(org_a, actor):
    """Las cinco señales que M09 ya tenía escritas, alimentadas por M02."""
    ahora = timezone.now()
    _, p1 = _persona(org_a)

    vencida = _crear(org_a, actor, titulo="vencida",
                     vence_en=ahora - timedelta(hours=5))
    act.asignar_responsable(vencida, actor=actor, responsable=p1)

    sin_dueno = _crear(org_a, actor, titulo="sin responsable")

    bloqueada = _crear(org_a, actor, titulo="bloqueada")
    act.asignar_responsable(bloqueada, actor=actor, responsable=p1)
    act.bloquear(bloqueada, actor=actor, motivo="falta permiso del municipio")

    compromiso = _crear(org_a, actor, tipo=A.COMPROMISO, titulo="compromiso",
                        vence_en=ahora + timedelta(hours=3))
    act.asignar_responsable(compromiso, actor=actor, responsable=p1)

    previa = _crear(org_a, actor, titulo="previa")
    dependiente = _crear(org_a, actor, titulo="dependiente")
    act.asignar_responsable(previa, actor=actor, responsable=p1)
    act.asignar_responsable(dependiente, actor=actor, responsable=p1)
    act.establecer_dependencia(dependiente, actor=actor, depende_de=previa)

    senales = supervisor.detectar(org_a, ahora)
    por_tipo = {}
    for s in senales:
        por_tipo.setdefault(s.tipo, []).append(s)

    assert PropuestaSupervisor.ACTIVIDAD_VENCIDA in por_tipo
    assert PropuestaSupervisor.ACTIVIDAD_SIN_RESPONSABLE in por_tipo
    assert PropuestaSupervisor.ACTIVIDAD_BLOQUEADA in por_tipo
    assert PropuestaSupervisor.COMPROMISO_POR_VENCER in por_tipo
    assert PropuestaSupervisor.DEPENDENCIA_PENDIENTE in por_tipo

    ids_sin_dueno = {s.origen_id for s in
                     por_tipo[PropuestaSupervisor.ACTIVIDAD_SIN_RESPONSABLE]}
    assert str(sin_dueno.id) in ids_sin_dueno

    bloq = por_tipo[PropuestaSupervisor.ACTIVIDAD_BLOQUEADA][0]
    assert "falta permiso del municipio" in bloq.datos["motivo"]


@pytest.mark.django_db
def test_26_detectar_no_ejecuta_nada(org_a, actor):
    """
    El Supervisor mira; no mueve. Se comprueba sobre el EFECTO: tras detectar,
    ninguna actividad cambió de estado ni apareció auditoría nueva.
    """
    ahora = timezone.now()
    a = _crear(org_a, actor, vence_en=ahora - timedelta(hours=2))
    b = _crear(org_a, actor, titulo="bloqueada")
    act.bloquear(b, actor=actor, motivo="falta material")

    antes = list(A.objects.filter(org=org_a).order_by("id").values(
        "id", "estado_operativo", "estado_validacion", "responsable_id",
        "vence_en", "updated_at"))
    n_audit = Activity.objects.filter(org=org_a).count()

    senales = supervisor.detectar(org_a, ahora)
    assert senales, "el instrumento no detectó nada: su cero no probaría nada"

    despues = list(A.objects.filter(org=org_a).order_by("id").values(
        "id", "estado_operativo", "estado_validacion", "responsable_id",
        "vence_en", "updated_at"))
    assert antes == despues, "detectar modificó actividades"
    assert Activity.objects.filter(org=org_a).count() == n_audit


# ==================================================== 27. efectos externos
@pytest.mark.django_db
def test_27_sin_efectos_externos(org_a, actor):
    salidas = []
    original = socket.socket.connect

    def espia(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("pg-m2", "127.0.0.1", "localhost", "::1"):
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

        _, p1 = _persona(org_a)
        a = _crear(org_a, actor, vence_en=timezone.now() + timedelta(days=1))
        act.asignar_responsable(a, actor=actor, responsable=p1)
        a = act.iniciar_gestion(a, actor=actor)
        a = act.bloquear(a, actor=actor, motivo="falta equipo")
        a = act.desbloquear(a, actor=actor)
        a = act.completar(a, actor=actor, requiere_validacion=True)
        act.validar(a, actor=actor, decision=APROBADO)
        act.pendientes_relevantes(org_a)
        supervisor.detectar(org_a)
    finally:
        socket.socket.connect = original

    assert salidas == [], f"hubo llamadas externas: {salidas}"


# ==================================================== API
@pytest.mark.django_db
def test_api_ciclo_completo_por_http(org_a):
    ug, g = _persona(org_a, "OPERACIONES")
    _, p1 = _persona(org_a)
    cli = _cli(ug, org_a, g)

    r = cli.post(URL, {"titulo": "Cambiar ONT", "tipo": "compromiso",
                       "origen_tipo": "case", "origen_id": "C-77"},
                 format="json")
    assert r.status_code == 201
    aid = r.data["actividad"]["id"]
    assert r.data["actividad"]["vencimiento"] == act.SIN_VENCIMIENTO
    assert r.data["actividad"]["responsable"] is None

    t = f"{URL}{aid}/transicion/"
    assert cli.post(t, {"accion": "asignar", "responsable_id": str(p1.id)},
                    format="json").data["resultado"] == "aplicado"
    assert cli.post(t, {"accion": "asignar", "responsable_id": str(p1.id)},
                    format="json").data["resultado"] == "sin_cambios"
    assert cli.post(t, {"accion": "iniciar"}, format="json").status_code == 200

    r = cli.post(t, {"accion": "bloquear"}, format="json")
    assert r.status_code == 400, "bloqueó sin motivo"
    r = cli.post(t, {"accion": "bloquear", "motivo": "falta equipo"},
                 format="json")
    assert r.data["actividad"]["estado_operativo"] == "bloqueada"
    assert r.data["actividad"]["motivo_bloqueo"] == "falta equipo"

    cli.post(t, {"accion": "desbloquear", "motivo": "llegó"}, format="json")
    r = cli.post(t, {"accion": "completar", "requiere_validacion": True},
                 format="json")
    assert r.data["actividad"]["estado_validacion"] == VALIDACION_PENDIENTE

    r = cli.post(t, {"accion": "validar"}, format="json")
    assert r.status_code == 400 and r.data["error"] == "FALTA_DECISION"
    r = cli.post(t, {"accion": "validar", "decision": APROBADO}, format="json")
    assert r.data["actividad"]["estado_validacion"] == APROBADO
    assert r.data["actividad"]["validado_en"] is not None

    r = cli.get(f"{URL}{aid}/")
    assert r.status_code == 200
    assert len(r.data["historial"]) >= 6
    assert r.data["historial"][0]["accion"] == "APPROVED"


@pytest.mark.django_db
def test_api_lista_y_resumen(org_a, actor):
    ahora = timezone.now()
    _, p1 = _persona(org_a)
    _crear(org_a, actor, titulo="vencida", vence_en=ahora - timedelta(hours=2))
    b = _crear(org_a, actor, titulo="bloqueada")
    act.bloquear(b, actor=actor, motivo="sin material")
    c = _crear(org_a, actor, titulo="con dueño")
    act.asignar_responsable(c, actor=actor, responsable=p1)

    ug, g = _persona(org_a, "OPERACIONES")
    r = _cli(ug, org_a, g).get(URL)
    assert r.status_code == 200
    res = r.data["resumen"]
    assert res["total"] == 3
    assert res["sin_responsable"] == 2
    assert res["bloqueadas"] == 1
    assert res["por_vencimiento"][act.VENCIDA] == 1
    assert res["por_vencimiento"][act.SIN_VENCIMIENTO] == 2


@pytest.mark.django_db
def test_api_no_hay_patch_sobre_el_estado(org_a, actor):
    """
    Las transiciones son explícitas. Un PATCH sobre 'estado_operativo' haría
    representable cualquier salto y la máquina de estados no significaría nada.
    """
    a = _crear(org_a, actor)
    ug, g = _persona(org_a, "OPERACIONES")
    cli = _cli(ug, org_a, g)
    for metodo, url in ((cli.patch, f"{URL}{a.id}/"),
                        (cli.put, f"{URL}{a.id}/"),
                        (cli.delete, f"{URL}{a.id}/")):
        assert metodo(url, {"estado_operativo": "completada"},
                      format="json").status_code == 405
    a.refresh_from_db()
    assert a.estado_operativo == A.PENDIENTE
