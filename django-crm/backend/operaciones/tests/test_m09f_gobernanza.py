# -*- coding: utf-8 -*-
"""
================================================================================
 M09-F  --  el ciclo humano de revisión, y las tres cosas que le faltaban
================================================================================

M09-D dejó el ciclo funcionando y M09-E lo validó contra datos reales. Este
paso cierra lo que ninguno de los dos miró, porque ninguno de los dos lo
preguntaba:

  1. MODIFICAR NO MODIFICABA NADA. 'revisar(decision="modificada")' ponía el
     estado en 'modificada' y guardaba el comentario, y ahí terminaba: el
     revisor no podía cambiar la prioridad, ni la acción, ni sugerir un
     responsable. Era una etiqueta, no una edición.

  2. NO HABÍA CONTROL DE CONCURRENCIA. 'revisar' leía el estado del objeto que
     ya tenía en memoria, comprobaba, y escribía -- sin bloqueo. Dos revisores
     con la misma propuesta abierta producían dos decisiones contradictorias y
     la última ganaba. Se demuestra abajo, y es el escenario textual del §12.

  3. 'cancelada' ERA UN ESTADO INALCANZABLE. Estaba declarado en ESTADOS desde
     M09-C y ninguna función lo asignaba nunca. Un estado que no puede ocurrir
     es una promesa que el modelo no cumple -- y la métrica "canceladas" que
     pide el diseño habría contado siempre cero sin que eso significara nada.

LA REGLA QUE ATRAVIESA TODO EL ARCHIVO
--------------------------------------
Una decisión humana no ejecuta nada. Se afirma con espías que CUENTAN, no
leyendo el código y concluyendo que no vio ninguna llamada.
================================================================================
"""

import threading
import uuid

import pytest
from django.db import connections
from django.utils import timezone

from conftest import rls_org
from operaciones import auditoria, supervisor
from operaciones.models import PropuestaSupervisor


# =============================================================================
#  utilidades
# =============================================================================

def _propuesta(org, **extra):
    """Una propuesta en estado inicial, con evidencia real (la exige la base)."""
    datos = dict(
        org=org,
        tipo_senal=PropuestaSupervisor.CASO_ANTIGUO,
        origen_tipo="case",
        origen_id=str(uuid.uuid4()),
        accion_propuesta="Revisar el caso y registrar el avance",
        motivo="Lleva 8 dias abierto sin resolucion registrada.",
        evidencia=[{
            "fuente": "case",
            "id": "c-1",
            "dato": "abierto desde 2026-09-09 (8 dias)",
            "observado_en": timezone.now().isoformat(),
        }],
        prioridad=42,
        impacto="El cliente sigue sin respuesta registrada",
        huella_condicion="huella-estable-1",
        expira_en=timezone.now() + timezone.timedelta(days=7),
    )
    datos.update(extra)
    return PropuestaSupervisor.objects.create(**datos)


def _perfil(org, correo, rol):
    from common.models import Profile, User
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role=rol, is_active=True)


# =============================================================================
#  §12  CONCURRENCIA  --  primero se demuestra el defecto, despues se cierra
# =============================================================================

def test_dos_revisores_con_la_misma_propuesta_abierta_no_producen_dos_decisiones(
        org_a, admin_profile):
    """
    EL ESCENARIO DEL §12, TAL CUAL.

        Revisor A abre la propuesta.
        Revisor B abre la misma propuesta.
        A acepta.
        B intenta rechazar.

    Dos peticiones HTTP hacen exactamente esto: cada una llama a
    'get_object_or_404' y se queda con SU PROPIA instancia en memoria. El
    'if propuesta.estado != PROPUESTA' de M09-D comprobaba esa copia, que para
    B seguía diciendo 'propuesta' aunque A ya hubiera aceptado en la base.

    Sin bloqueo, esta prueba falla: B rechaza encima de la aceptación de A y
    quedan dos renglones de auditoría contradictorios sobre la misma fila.
    """
    b_profile = _perfil(org_a, "revisor.b@prueba.local", "ADMIN")
    creada = _propuesta(org_a)

    # Las dos instancias, como las cargarían dos peticiones distintas.
    vista_por_a = PropuestaSupervisor.objects.get(id=creada.id)
    vista_por_b = PropuestaSupervisor.objects.get(id=creada.id)

    supervisor.revisar(vista_por_a, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA,
                       comentario="de acuerdo")

    with pytest.raises(supervisor.YaRevisada):
        supervisor.revisar(vista_por_b, actor=b_profile,
                           decision=PropuestaSupervisor.RECHAZADA,
                           comentario="no estoy de acuerdo")

    # La primera decisión es la que vale, y es la única.
    creada.refresh_from_db()
    assert creada.estado == PropuestaSupervisor.ACEPTADA
    assert creada.revisado_por_id == admin_profile.id

    decisiones = [
        h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, creada.id)
        if h.action in ("APPROVED", "REJECTED", "UPDATE")
    ]
    assert len(decisiones) == 1, (
        f"una propuesta con una sola decisión dejó {len(decisiones)} renglones")


@pytest.mark.django_db(transaction=True)
def test_dos_hilos_reales_compitiendo_dejan_una_sola_decision(org_a):
    """
    El mismo escenario, pero con dos conexiones de verdad peleándose la fila.

    La prueba de arriba demuestra la regla; esta demuestra que el bloqueo es
    de BASE y no de proceso: dos hilos, dos conexiones, un 'select for update'.
    Sin él, los dos entran a la vez y los dos escriben.
    """
    from common.models import Org

    org = Org.objects.create(name="Org concurrencia M09F")
    a = _perfil(org, "hilo.a@prueba.local", "ADMIN")
    b = _perfil(org, "hilo.b@prueba.local", "ADMIN")
    propuesta = _propuesta(org)

    partida = threading.Barrier(2)
    resultados = []

    def revisar_desde_hilo(actor_id, decision):
        try:
            partida.wait(timeout=10)
            from common.models import Profile
            actor = Profile.objects.get(id=actor_id)
            p = PropuestaSupervisor.objects.get(id=propuesta.id)
            supervisor.revisar(p, actor=actor, decision=decision,
                               comentario="decision concurrente")
            resultados.append(("ok", decision))
        except supervisor.YaRevisada:
            resultados.append(("rechazada_por_bloqueo", decision))
        except Exception as e:                      # pragma: no cover
            resultados.append(("error", f"{type(e).__name__}: {e}"))
        finally:
            connections.close_all()

    hilos = [
        threading.Thread(target=revisar_desde_hilo,
                         args=(a.id, PropuestaSupervisor.ACEPTADA)),
        threading.Thread(target=revisar_desde_hilo,
                         args=(b.id, PropuestaSupervisor.RECHAZADA)),
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)

    exitosas = [r for r in resultados if r[0] == "ok"]
    bloqueadas = [r for r in resultados if r[0] == "rechazada_por_bloqueo"]
    assert len(exitosas) == 1, f"esperaba 1 decisión, hubo {len(exitosas)}: {resultados}"
    assert len(bloqueadas) == 1, f"esperaba 1 bloqueada: {resultados}"

    propuesta.refresh_from_db()
    assert propuesta.estado in PropuestaSupervisor.ESTADOS_REVISADOS

    decisiones = [
        h for h in auditoria.historial(org, auditoria.ENTIDAD_PROPUESTA, propuesta.id)
        if h.action in ("APPROVED", "REJECTED", "UPDATE")
    ]
    assert len(decisiones) == 1, f"quedaron {len(decisiones)} decisiones auditadas"

    # limpieza: 'transaction=True' no revierte solo
    PropuestaSupervisor.objects.filter(org=org).delete()


# =============================================================================
#  §11  IDEMPOTENCIA  --  el doble clic
# =============================================================================

@pytest.mark.parametrize("primera,segunda", [
    (PropuestaSupervisor.ACEPTADA, PropuestaSupervisor.ACEPTADA),
    (PropuestaSupervisor.RECHAZADA, PropuestaSupervisor.RECHAZADA),
    (PropuestaSupervisor.ACEPTADA, PropuestaSupervisor.RECHAZADA),
    (PropuestaSupervisor.RECHAZADA, PropuestaSupervisor.ACEPTADA),
    (PropuestaSupervisor.MODIFICADA, PropuestaSupervisor.ACEPTADA),
])
def test_la_segunda_decision_no_ocurre_nunca(org_a, admin_profile, primera, segunda):
    """
    UNA REGLA, LA MISMA PARA LOS CINCO PARES: la primera decisión es la única.

    No se eligió 'la última gana' ni 'aceptar dos veces es idempotente y
    rechazar dos veces no'. Una sola regla, porque el revisor tiene que poder
    predecir qué pasó con un doble clic sin saber cuál de los dos botones
    apretó.
    """
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile, decision=primera,
                       comentario="primera decisión")

    with pytest.raises(supervisor.YaRevisada):
        supervisor.revisar(p, actor=admin_profile, decision=segunda,
                           comentario="segunda decisión")

    p.refresh_from_db()
    assert p.estado == primera
    assert p.resultado == "primera decisión"


def test_el_doble_clic_no_duplica_la_auditoria(org_a, admin_profile):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    for _ in range(4):
        with pytest.raises(supervisor.YaRevisada):
            supervisor.revisar(p, actor=admin_profile,
                               decision=PropuestaSupervisor.ACEPTADA,
                               comentario="ok")

    decisiones = [
        h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
        if h.action in ("APPROVED", "REJECTED", "UPDATE")
    ]
    assert len(decisiones) == 1


# =============================================================================
#  §4  MODIFICAR  --  ahora modifica, y no toca el hecho histórico
# =============================================================================

def test_modificar_cambia_los_campos_permitidos(org_a, admin_profile):
    p = _propuesta(org_a)
    otro = _perfil(org_a, "responsable@prueba.local", "OPERACIONES")

    supervisor.revisar(
        p, actor=admin_profile, decision=PropuestaSupervisor.MODIFICADA,
        comentario="la prioridad estaba baja para un cliente corporativo",
        cambios={
            "prioridad": 10,
            "accion_propuesta": "Escalar el caso al equipo corporativo",
            "impacto": "Cliente corporativo con SLA contractual",
            "responsable_sugerido": otro,
            "observaciones": "Hablado con el cliente el martes.",
        },
    )

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.MODIFICADA
    assert p.prioridad == 10
    assert p.accion_propuesta == "Escalar el caso al equipo corporativo"
    assert p.impacto == "Cliente corporativo con SLA contractual"
    assert p.responsable_sugerido_id == otro.id
    assert p.observaciones == "Hablado con el cliente el martes."


def test_modificar_conserva_la_propuesta_original_entera(org_a, admin_profile):
    """
    'No sobrescribir la propuesta original.'

    Lo que la IA recomendó queda guardado literal, no reconstruible a partir de
    la auditoría: es el término de comparación para decidir si el Supervisor
    recomienda bien, y esa medición es el objetivo entero del Shadow Mode.
    """
    p = _propuesta(org_a)
    accion_ia, motivo_ia, prioridad_ia = p.accion_propuesta, p.motivo, p.prioridad

    supervisor.revisar(
        p, actor=admin_profile, decision=PropuestaSupervisor.MODIFICADA,
        comentario="ajusto la redacción",
        cambios={"prioridad": 5, "accion_propuesta": "Otra cosa distinta"},
    )
    p.refresh_from_db()

    assert p.propuesta_original["accion_propuesta"] == accion_ia
    assert p.propuesta_original["motivo"] == motivo_ia
    assert p.propuesta_original["prioridad"] == prioridad_ia
    assert p.propuesta_original["modificada_por"] == str(admin_profile.id)
    assert p.propuesta_original["modificada_en"]


@pytest.mark.parametrize("campo,valor", [
    ("evidencia", [{"fuente": "inventada", "dato": "lo que me conviene",
                    "observado_en": "2020-01-01T00:00:00Z"}]),
    ("tipo_senal", PropuestaSupervisor.ACTIVIDAD_VENCIDA),
    ("huella_condicion", "otra-huella"),
    ("origen_id", "otro-origen"),
    ("origen_tipo", "actividad"),
    ("estado", PropuestaSupervisor.ACEPTADA),
    ("accion_propuesta_ref", "accion-123"),
    ("nivel_autonomia_requerido", 4),
    ("org", None),
])
def test_ningun_campo_fuera_de_la_lista_blanca_se_puede_tocar(
        org_a, admin_profile, campo, valor):
    """
    La EVIDENCIA es el hecho observado; la DECISIÓN es lo que un humano opina
    de él. Un revisor que pudiera editar la evidencia podría fabricar el hecho
    que justifica su propia decisión -- y entonces la evidencia dejaría de
    servir para lo único que sirve.

    Y se RECHAZA, no se filtra en silencio: ignorar un campo que el revisor
    creyó estar cambiando es peor que negarse, porque el revisor se va
    convencido de que lo cambió.
    """
    p = _propuesta(org_a)
    antes = {c: getattr(p, c) for c in
             ("evidencia", "tipo_senal", "huella_condicion", "origen_id",
              "origen_tipo", "estado", "accion_propuesta_ref",
              "nivel_autonomia_requerido")}

    with pytest.raises(ValueError) as e:
        supervisor.revisar(p, actor=admin_profile,
                           decision=PropuestaSupervisor.MODIFICADA,
                           comentario="intento cambiarlo", cambios={campo: valor})
    assert campo in str(e.value)

    # Nada se escribió: ni el campo prohibido, ni el estado.
    p.refresh_from_db()
    for c, v in antes.items():
        assert getattr(p, c) == v, f"'{c}' cambió pese al rechazo"
    assert p.estado == PropuestaSupervisor.PROPUESTA


def test_una_modificacion_valida_tampoco_toca_la_evidencia(org_a, admin_profile):
    """El camino que SÍ se permite tampoco puede rozar el hecho observado."""
    p = _propuesta(org_a)
    evidencia_ia = list(p.evidencia)
    huella_ia, senal_ia, origen_ia = p.huella_condicion, p.tipo_senal, p.origen_id

    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.MODIFICADA,
                       comentario="solo subo la prioridad",
                       cambios={"prioridad": 1})
    p.refresh_from_db()

    assert p.prioridad == 1
    assert p.evidencia == evidencia_ia
    assert p.huella_condicion == huella_ia
    assert p.tipo_senal == senal_ia
    assert p.origen_id == origen_ia
    assert p.accion_propuesta_ref == ""
    assert p.nivel_autonomia_requerido <= PropuestaSupervisor.NIVEL_MAXIMO_ETAPA


def test_un_campo_inventado_tampoco_pasa(org_a, admin_profile):
    p = _propuesta(org_a)
    with pytest.raises(ValueError) as e:
        supervisor.revisar(p, actor=admin_profile,
                           decision=PropuestaSupervisor.MODIFICADA,
                           comentario="x", cambios={"ejecutar_ahora": True})
    assert "ejecutar_ahora" in str(e.value)


def test_el_responsable_sugerido_no_puede_ser_de_otra_organizacion(
        org_a, org_b, admin_profile):
    """La edición humana no es una puerta lateral al aislamiento entre tenants."""
    with rls_org(org_b):
        ajeno = _perfil(org_b, "ajeno@prueba.local", "OPERACIONES")

    p = _propuesta(org_a)
    with pytest.raises(ValueError) as e:
        supervisor.revisar(p, actor=admin_profile,
                           decision=PropuestaSupervisor.MODIFICADA,
                           comentario="x",
                           cambios={"responsable_sugerido": ajeno})
    assert "otra organización" in str(e.value)
    p.refresh_from_db()
    assert p.responsable_sugerido_id is None
    assert p.estado == PropuestaSupervisor.PROPUESTA


def test_la_auditoria_de_modificar_registra_antes_y_despues(org_a, admin_profile):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.MODIFICADA,
                       comentario="subo la prioridad",
                       cambios={"prioridad": 7})

    fila = [h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
            if h.action == "UPDATE"][0]
    cambios = fila.metadata.get("cambios", {})
    assert cambios["prioridad"]["antes"] == 42
    assert cambios["prioridad"]["despues"] == 7


def test_aceptar_y_rechazar_no_admiten_cambios(org_a, admin_profile):
    """Editar es MODIFICAR. Aceptar con edición encubierta no es aceptar."""
    for decision in (PropuestaSupervisor.ACEPTADA, PropuestaSupervisor.RECHAZADA):
        p = _propuesta(org_a)
        with pytest.raises(ValueError) as e:
            supervisor.revisar(p, actor=admin_profile, decision=decision,
                               comentario="x", cambios={"prioridad": 3})
        assert "modificar" in str(e.value).lower()
        p.refresh_from_db()
        assert p.estado == PropuestaSupervisor.PROPUESTA


def test_la_ia_no_puede_sugerir_un_responsable(org_a):
    """
    M09-C lo prohíbe: el Supervisor no nombra personas. 'responsable_sugerido'
    lo pone un humano al modificar, o no lo pone nadie.
    """
    p = _propuesta(org_a)
    assert p.responsable_sugerido_id is None
    campos_que_escribe_la_ia = supervisor.CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR
    assert "responsable_sugerido" not in campos_que_escribe_la_ia
    assert "observaciones" not in campos_que_escribe_la_ia


# =============================================================================
#  §5 + §7  RECHAZAR, Y LA DEDUPLICACION QUE YA EXISTIA
# =============================================================================

def test_rechazar_conserva_todo_y_registra_el_motivo(org_a, admin_profile):
    p = _propuesta(org_a)
    evidencia_ia = list(p.evidencia)

    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA,
                       comentario="ese caso lo cerramos por teléfono ayer")
    p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.RECHAZADA
    assert p.evidencia == evidencia_ia
    assert p.revisado_por_id == admin_profile.id
    assert p.revisado_en is not None
    assert "teléfono" in p.resultado

    fila = [h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
            if h.action == "REJECTED"][0]
    assert fila.metadata["motivo"] == "ese caso lo cerramos por teléfono ayer"
    assert fila.metadata["estado_anterior"] == PropuestaSupervisor.PROPUESTA
    assert fila.metadata["estado_nuevo"] == PropuestaSupervisor.RECHAZADA


def test_rechazada_la_misma_evidencia_no_vuelve_a_proponerse(org_a, admin_profile):
    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id="caso-fijo", evidencia=[{
            "fuente": "case", "id": "caso-fijo", "dato": "abierto",
            "observado_en": timezone.now().isoformat()}],
        huella="condicion-identica",
    )
    p = _propuesta(org_a, origen_id="caso-fijo", huella_condicion="condicion-identica")
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA, comentario="no")

    assert supervisor._ya_propuesta(org_a, senal) is True


def test_una_condicion_nueva_si_puede_volver_a_proponerse(org_a, admin_profile):
    p = _propuesta(org_a, origen_id="caso-fijo", huella_condicion="condicion-vieja")
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA, comentario="no")

    senal_nueva = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id="caso-fijo", evidencia=[{
            "fuente": "case", "id": "caso-fijo", "dato": "ahora ademas bloqueado",
            "observado_en": timezone.now().isoformat()}],
        huella="condicion-NUEVA",
    )
    assert supervisor._ya_propuesta(org_a, senal_nueva) is False


def test_una_propuesta_expirada_si_puede_volver_a_proponerse(org_a):
    """Expirar significa que nadie la miró. Volver a preguntar es lo correcto."""
    p = _propuesta(org_a, origen_id="caso-fijo", huella_condicion="h",
                   expira_en=timezone.now() - timezone.timedelta(days=1))
    assert supervisor.expirar_vencidas(org_a) == 1
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.EXPIRADA

    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id="caso-fijo", evidencia=[{
            "fuente": "case", "id": "x", "dato": "sigue abierto",
            "observado_en": timezone.now().isoformat()}],
        huella="h")
    assert supervisor._ya_propuesta(org_a, senal) is False


# =============================================================================
#  §6  LOS TRES FINALES NO SON SINONIMOS
# =============================================================================

def test_expirar_solo_alcanza_a_las_que_nadie_reviso(org_a, admin_profile):
    revisada = _propuesta(org_a, expira_en=timezone.now() - timezone.timedelta(days=1))
    supervisor.revisar(revisada, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    sin_revisar = _propuesta(org_a, expira_en=timezone.now() - timezone.timedelta(days=1))

    assert supervisor.expirar_vencidas(org_a) == 1
    revisada.refresh_from_db()
    sin_revisar.refresh_from_db()
    assert revisada.estado == PropuestaSupervisor.ACEPTADA   # una decisión no expira
    assert sin_revisar.estado == PropuestaSupervisor.EXPIRADA


def test_expirar_no_es_rechazar(org_a):
    p = _propuesta(org_a, expira_en=timezone.now() - timezone.timedelta(days=1))
    supervisor.expirar_vencidas(org_a)
    p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.EXPIRADA
    assert p.revisado_por_id is None      # nadie decidió: nadie firma
    assert p.revisado_en is None
    fila = [h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
            if h.metadata.get("estado_nuevo") == PropuestaSupervisor.EXPIRADA][0]
    assert fila.user_id is None
    assert fila.action != "REJECTED"


def test_cancelar_existe_y_no_es_ninguno_de_los_otros_dos(org_a):
    """
    CANCELADA = la condición desapareció antes de que nadie la mirara.

    Hasta M09-F el estado estaba declarado y no lo escribía nadie. Que el caso
    se cierre solo no es un rechazo (nadie opinó) ni una expiración (no se
    venció el plazo: dejó de tener sentido).
    """
    p = _propuesta(org_a)
    supervisor.cancelar(p, motivo="el caso se cerró por otra vía")
    p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.CANCELADA
    assert p.revisado_por_id is None
    assert p.evidencia                      # el historial no se borra
    fila = [h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
            if h.metadata.get("estado_nuevo") == PropuestaSupervisor.CANCELADA][0]
    assert fila.metadata["motivo"] == "el caso se cerró por otra vía"


def test_cancelar_exige_motivo(org_a):
    p = _propuesta(org_a)
    with pytest.raises(ValueError):
        supervisor.cancelar(p, motivo="")


def test_cancelar_no_pisa_una_decision_humana(org_a, admin_profile):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    with pytest.raises(supervisor.YaRevisada):
        supervisor.cancelar(p, motivo="el caso se cerró")
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA


def test_una_cancelada_puede_volver_a_proponerse(org_a):
    p = _propuesta(org_a, origen_id="caso-fijo", huella_condicion="h")
    supervisor.cancelar(p, motivo="se cerró solo")
    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id="caso-fijo", evidencia=[{
            "fuente": "case", "id": "x", "dato": "volvio a abrirse",
            "observado_en": timezone.now().isoformat()}],
        huella="h")
    assert supervisor._ya_propuesta(org_a, senal) is False


# =============================================================================
#  §14  DECISION NO ES EJECUCION
# =============================================================================

@pytest.mark.parametrize("decision", [
    PropuestaSupervisor.ACEPTADA,
    PropuestaSupervisor.MODIFICADA,
    PropuestaSupervisor.RECHAZADA,
])
def test_ninguna_decision_deja_referencia_de_ejecucion(org_a, admin_profile, decision):
    p = _propuesta(org_a)
    cambios = {"prioridad": 9} if decision == PropuestaSupervisor.MODIFICADA else None
    supervisor.revisar(p, actor=admin_profile, decision=decision,
                       comentario="motivo", cambios=cambios)
    p.refresh_from_db()
    assert p.accion_propuesta_ref == ""
    assert "ejecutada" not in dict(PropuestaSupervisor.ESTADOS)


def test_el_unico_camino_a_la_ejecucion_sigue_levantando(org_a, admin_profile):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    with pytest.raises(supervisor.EjecucionNoPermitida):
        supervisor.ejecutar_propuesta(p)


# =============================================================================
#  §8  PERMISOS  --  medidos por HTTP, no leyendo la clase de permiso
# =============================================================================
#  Se prueba contra las RUTAS y no contra EsJefeDeOperaciones.has_permission
#  porque lo que protege al sistema es lo que contesta el servidor. Una prueba
#  sobre la clase afirma que el mecanismo EXISTE; esta afirma que FUNCIONA --
#  la distincion que CLAUDE.md registra como leccion cara.

def _cliente(user, org, profile):
    from conftest import _make_authenticated_client
    return _make_authenticated_client(user, org, profile)


def _cliente_con_rol(org, rol, correo):
    from common.models import Profile, User
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    p = Profile.objects.create(user=u, org=org, role=rol, is_active=True)
    return _cliente(u, org, p), p


RUTA_LISTA = "/api/operaciones/propuestas/"


@pytest.mark.parametrize("rol,puede", [
    ("ADMIN", True),
    ("SUPERVISOR", True),
    ("OPERACIONES", True),
    ("USER", False),
])
def test_quien_puede_consultar_la_lista(org_a, rol, puede):
    cli, _ = _cliente_con_rol(org_a, rol, f"lista.{rol.lower()}@prueba.local")
    r = cli.get(RUTA_LISTA)
    assert (r.status_code == 200) is puede, f"{rol} -> {r.status_code}"


@pytest.mark.parametrize("rol,puede", [
    ("ADMIN", True),
    ("SUPERVISOR", True),
    ("OPERACIONES", True),
    ("USER", False),
])
@pytest.mark.parametrize("decision", [
    PropuestaSupervisor.ACEPTADA,
    PropuestaSupervisor.RECHAZADA,
    PropuestaSupervisor.MODIFICADA,
])
def test_quien_puede_aceptar_modificar_y_rechazar(org_a, rol, puede, decision):
    cli, _ = _cliente_con_rol(
        org_a, rol, f"dec.{rol.lower()}.{decision}@prueba.local")
    p = _propuesta(org_a)
    cuerpo = {"decision": decision, "comentario": "un motivo"}
    if decision == PropuestaSupervisor.MODIFICADA:
        cuerpo["cambios"] = {"prioridad": 11}

    r = cli.post(f"{RUTA_LISTA}{p.id}/revisar/", cuerpo, format="json")
    assert (r.status_code == 200) is puede, f"{rol}/{decision} -> {r.status_code}"

    p.refresh_from_db()
    assert (p.estado == decision) is puede


@pytest.mark.parametrize("rol,puede", [
    ("ADMIN", True), ("SUPERVISOR", True), ("OPERACIONES", True),
    ("USER", False),
])
def test_quien_puede_cancelar(org_a, rol, puede):
    cli, _ = _cliente_con_rol(org_a, rol, f"can.{rol.lower()}@prueba.local")
    p = _propuesta(org_a)
    r = cli.post(f"{RUTA_LISTA}{p.id}/cancelar/",
                 {"motivo": "el caso se cerró"}, format="json")
    assert (r.status_code == 200) is puede


def test_sin_sesion_no_se_puede_nada(org_a, unauthenticated_client):
    p = _propuesta(org_a)
    assert unauthenticated_client.get(RUTA_LISTA).status_code in (401, 403)
    assert unauthenticated_client.get(
        f"{RUTA_LISTA}{p.id}/").status_code in (401, 403)
    assert unauthenticated_client.post(
        f"{RUTA_LISTA}{p.id}/revisar/",
        {"decision": "aceptada"}, format="json").status_code in (401, 403)
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.PROPUESTA


def test_operaciones_revisa_pero_no_administra(org_a):
    """
    Revisar no es administrar.

    'Profile.save()' deriva is_organization_admin = (role == "ADMIN"), asi que
    un Jefe de Operaciones pasa el guardia de revision SIN quedar administrador
    de la organizacion. Es la propiedad que hace que el rol sirva.
    """
    _, perfil = _cliente_con_rol(org_a, "OPERACIONES", "jefe.ops@prueba.local")
    assert perfil.is_organization_admin is False


def test_no_existe_ninguna_ruta_de_ejecucion():
    """
    §14: no hay transición automática a ejecución. Se comprueba sobre el
    ruteador entero, no sobre la memoria de quien lo escribió.

    EL INVENTARIO ESTÁ FIJADO A PROPÓSITO
    -------------------------------------
    La lista es exacta y no un `issubset`: cualquier ruta nueva hace fallar esta
    prueba, y eso es lo buscado. Agregar una ruta al módulo obliga a venir acá y
    declarar que no ejecuta nada.

    'disponibilidad' entró en el paso A-3.3: registra que una persona no está
    disponible. NO ejecuta nada contra ningún sistema externo, no reprograma y
    no reasigna -- M03 es el dueño de ese efecto. Su propia suite lo verifica
    (tests/test_a33_disponibilidad.py) y la vista responde 405 a DELETE, PUT y
    PATCH.

    'programacion-publicar' entró en el paso M03-C: pasa un plan semanal de
    'borrador' a 'publicada'. Publicar NO es ejecutar -- no toca ninguna orden,
    no cambia 'programada_para', no crea asignaciones y no llama a ningún
    sistema externo. Lo que cambia es que el plan deja de ser un borrador, que
    es justo lo que la señal 'programacion_sin_publicar' lleva midiendo sin que
    nadie pudiera apagarla. Su propia suite lo verifica
    (tests/test_m03c_publicacion.py), incluida una prueba que afirma sobre el
    EFECTO: después de publicar, ninguna orden cambió.

    'programacion-jornada' entró en el paso M03-E2, y es la más fácil de
    declarar: es un **GET**. Lee las líneas vigentes de un día o un plan y
    cuenta los empates de secuencia. No escribe nada -- ni una fila, ni un
    evento--, no reordena, no recompacta y no resuelve ningún empate: decidir
    qué hacer con un duplicado es la decisión E-1, que sigue abierta. Su propia
    suite lo verifica afirmando sobre el efecto: tras la lectura, ninguna línea
    cambió.

    'linea-secuencia' entró en el paso M03-E4: cambia el ORDEN PROPUESTO de una
    línea de plan. No ejecuta nada contra ningún sistema externo, no despacha,
    no reasigna y no mueve trabajo -- cambiar la secuencia NO es reprogramar.
    Su propia suite afirma sobre el efecto que no toca 'programada_para', ni el
    día, ni el plan, ni la zona, ni la prioridad, ni ninguna otra línea.

    'jornada-secuenciar' entró en el paso M03-E5-B: aplica el orden propuesto
    de un día ENTERO en una sola transacción. Es la misma escritura que
    'linea-secuencia' repetida N veces y con un lote común -- no ejecuta nada
    contra ningún sistema externo, no despacha, no reasigna y no mueve trabajo.
    Su propia suite afirma sobre el efecto que no toca 'programada_para', ni el
    estado operativo, ni la asignación, ni la prioridad.

    'capacidad-jornada' entró en el paso M03-G, y es de las fáciles de declarar:
    es un **GET**. Deriva, para un día, cuánto tiempo operativo hay, cuánto está
    comprometido y si eso se pasa. No escribe una sola fila -- no hay modelo de
    capacidad, no hay tabla y no hay migración: el número se calcula cuando se
    pregunta, porque guardarlo sería garantizar que quede viejo. No reprograma,
    no reasigna, no retira a nadie, no cancela y no llama a ningún sistema
    externo. Detectar una sobrecarga NO es resolverla: produce un resultado
    legible, y proponer qué hacer con él será de M09. Su propia suite afirma
    sobre el efecto (tests/test_m03g_capacidad.py): tras consultar tres veces,
    ni la orden ni la línea de plan cambiaron -- 'updated_at' incluido.

    'actividades', 'actividad-detalle' y 'actividad-transicion' entraron en el
    paso M02. Las dos primeras son **GET**. La tercera escribe, y aun así no
    ejecuta: mueve una ActividadOperativa entre sus propios estados -- asignar,
    iniciar, bloquear, completar, validar, cancelar-- y deja el hecho en
    common.Activity. No despacha, no reprograma, no llama a WispHub ni a
    SmartOLT, no manda WhatsApp y no toca ninguna orden de trabajo ni ningún
    plan: su efecto entero vive dentro de la propia tabla del módulo. Las
    transiciones son EXPLÍCITAS por nombre y contra una máquina de estados
    declarada -- no hay PATCH sobre 'estado_operativo', que es lo que habría
    hecho representable cualquier salto. Nada se cierra ni se asigna solo: el
    Supervisor podrá proponer, ejecutar es de una persona. Su propia suite lo
    verifica (tests/test_m02_actividades.py), incluida una prueba de 0 efectos
    externos con el espía probado antes de creerle su cero.

    'asistente' entró en el paso M09-M. Escribe, y aun así no ejecuta: lo único
    que produce son filas de PropuestaSupervisor -- la MISMA cola, el mismo
    registrador ('supervisor.registrar_propuesta'), la misma deduplicación y la
    misma revisión humana. No hay cola nueva ni entidad de recomendación. No
    programa, no asigna, no cierra, no cancela, no toca disponibilidad y no
    llama a ningún sistema externo: 'operaciones/asistentes.py' no importa un
    solo servicio de escritura operativa --ni 'programacion', ni 'actividades',
    ni 'despacho'-- así que no tiene con qué, y su propia suite lo afirma sobre
    el EFECTO (tests/test_m09m_asistentes.py): tras una pasada completa, ni una
    orden, ni una línea de plan, ni una actividad cambiaron. Tampoco crea
    habilidades ni eleva autonomía: toda propuesta sale con
    'nivel_autonomia_requerido <= 1' y estado 'propuesta'.

    'indicadores' y 'reportes' entraron en el paso M11, y son las dos más
    fáciles de declarar: son **GET**. Derivan cifras de filas que ya existen y
    no escriben ninguna -- no hay tabla de KPI, no hay caché persistente, no
    crean actividad de negocio y no corren el ciclo del Supervisor: leen las
    señales sin registrarlas. 'operaciones/indicadores.py' no importa un solo
    servicio de escritura, y su propia suite lo afirma sobre el EFECTO
    (tests/test_m11_indicadores.py): tras generar los cinco reportes, ni una
    actividad, ni una orden, ni una propuesta cambiaron, y no apareció ninguna
    fila nueva.
    """
    from operaciones import urls as rutas_operaciones
    nombres = {p.name for p in rutas_operaciones.urlpatterns}
    assert nombres == {"propuestas", "propuesta-detalle", "propuesta-revisar",
                       "propuesta-cancelar", "ciclo", "disponibilidad",
                       "programacion-publicar", "programacion-jornada",
                       "linea-secuencia", "jornada-secuenciar",
                       "capacidad-jornada", "actividades",
                       "actividad-detalle", "actividad-transicion",
                       "asistente", "indicadores", "reportes"}
    for prohibida in ("ejecutar", "aplicar", "despachar", "propuesta-ejecutar"):
        assert prohibida not in nombres


# =============================================================================
#  §9  AISLAMIENTO ENTRE ORGANIZACIONES
# =============================================================================

def test_el_jefe_de_a_no_ve_una_propuesta_de_b(org_a, org_b, admin_client):
    with rls_org(org_b):
        ajena = _propuesta(org_b)

    r = admin_client.get(f"{RUTA_LISTA}{ajena.id}/")
    assert r.status_code == 404, "404 y no 403: un 403 confirma que el id existe"


def test_el_jefe_de_a_no_puede_revisar_una_propuesta_de_b(org_a, org_b, admin_client):
    with rls_org(org_b):
        ajena = _propuesta(org_b)

    r = admin_client.post(f"{RUTA_LISTA}{ajena.id}/revisar/",
                          {"decision": "aceptada"}, format="json")
    assert r.status_code == 404

    with rls_org(org_b):
        ajena.refresh_from_db()
        assert ajena.estado == PropuestaSupervisor.PROPUESTA
        assert ajena.revisado_por_id is None


def test_el_jefe_de_a_no_puede_cancelar_una_propuesta_de_b(org_a, org_b, admin_client):
    with rls_org(org_b):
        ajena = _propuesta(org_b)
    r = admin_client.post(f"{RUTA_LISTA}{ajena.id}/cancelar/",
                          {"motivo": "x"}, format="json")
    assert r.status_code == 404
    with rls_org(org_b):
        ajena.refresh_from_db()
        assert ajena.estado == PropuestaSupervisor.PROPUESTA


def test_la_lista_solo_trae_lo_propio(org_a, org_b, admin_client):
    mia = _propuesta(org_a)
    with rls_org(org_b):
        _propuesta(org_b)

    r = admin_client.get(RUTA_LISTA)
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()["resultados"]}
    assert str(mia.id) in ids
    assert r.json()["count"] == PropuestaSupervisor.objects.filter(org=org_a).count()


def test_la_rls_de_la_tabla_esta_puesta_y_forzada():
    """
    Las dos capas, no una.

    El filtro de aplicación ya se probó arriba. Esto comprueba la otra: que la
    tabla tiene RLS habilitada Y FORZADA, y su política de aislamiento. Es la
    diferencia con las tablas 'campo_*' que M09-E reportó sin RLS -- aquí sí
    está, y conviene que quede medido y no supuesto.
    """
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("""
            select c.relrowsecurity, c.relforcerowsecurity,
                   (select count(*) from pg_policies p
                     where p.tablename = 'operaciones_propuesta_supervisor')
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public'
               and c.relname = 'operaciones_propuesta_supervisor'
        """)
        habilitada, forzada, politicas = cur.fetchone()
    assert habilitada is True
    assert forzada is True
    assert politicas >= 1


# =============================================================================
#  §10  AUDITORIA  --  nada cambia en silencio
# =============================================================================

@pytest.mark.parametrize("decision,verbo", [
    (PropuestaSupervisor.ACEPTADA, "APPROVED"),
    (PropuestaSupervisor.RECHAZADA, "REJECTED"),
    (PropuestaSupervisor.MODIFICADA, "UPDATE"),
])
def test_cada_decision_deja_las_ocho_cosas(org_a, admin_profile, decision, verbo):
    p = _propuesta(org_a)
    cambios = {"prioridad": 3} if decision == PropuestaSupervisor.MODIFICADA else None
    supervisor.revisar(p, actor=admin_profile, decision=decision,
                       comentario="porque sí", cambios=cambios)

    fila = [h for h in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, p.id)
            if h.action == verbo][0]

    assert fila.user_id == admin_profile.id                  # actor
    assert fila.org_id == org_a.id                           # organización
    assert str(fila.entity_id) == str(p.id)                  # propuesta
    assert fila.entity_type == auditoria.ENTIDAD_PROPUESTA
    assert fila.metadata["estado_anterior"] == PropuestaSupervisor.PROPUESTA
    assert fila.metadata["estado_nuevo"] == decision
    assert fila.created_at is not None                       # fecha/hora
    assert fila.metadata["motivo"] == "porque sí"            # motivo
    assert fila.metadata["sin_ejecucion"] is True

    p.refresh_from_db()
    assert p.evidencia                                       # evidencia intacta


def test_ninguna_transicion_ocurre_sin_dejar_rastro(org_a, admin_profile):
    """
    Se recorren los CUATRO finales posibles y se exige un renglón por cada uno.
    Si mañana alguien agrega un quinto estado y olvida auditarlo, esto lo caza.
    """
    casos = []

    aceptada = _propuesta(org_a)
    supervisor.revisar(aceptada, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    casos.append((aceptada, PropuestaSupervisor.ACEPTADA))

    rechazada = _propuesta(org_a)
    supervisor.revisar(rechazada, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA, comentario="no")
    casos.append((rechazada, PropuestaSupervisor.RECHAZADA))

    expirada = _propuesta(org_a, expira_en=timezone.now() - timezone.timedelta(days=1))
    supervisor.expirar_vencidas(org_a)
    casos.append((expirada, PropuestaSupervisor.EXPIRADA))

    cancelada = _propuesta(org_a)
    supervisor.cancelar(cancelada, motivo="el caso se cerró solo")
    casos.append((cancelada, PropuestaSupervisor.CANCELADA))

    for propuesta, estado_final in casos:
        propuesta.refresh_from_db()
        assert propuesta.estado == estado_final
        filas = [h for h in auditoria.historial(
            org_a, auditoria.ENTIDAD_PROPUESTA, propuesta.id)
            if h.metadata.get("estado_nuevo") == estado_final]
        assert len(filas) == 1, f"'{estado_final}' dejó {len(filas)} renglones"


def test_el_historial_sale_por_la_api(org_a, admin_client, admin_profile):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.MODIFICADA,
                       comentario="subo prioridad", cambios={"prioridad": 8})

    r = admin_client.get(f"{RUTA_LISTA}{p.id}/")
    assert r.status_code == 200
    datos = r.json()
    assert datos["propuesta_original"]["prioridad"] == 42
    assert datos["prioridad"] == 8
    assert any(h["accion"] == "UPDATE" for h in datos["historial"])
    assert datos["accion_propuesta_ref"] == ""


# =============================================================================
#  §11 + §12 por HTTP  --  el doble clic real
# =============================================================================

def test_el_segundo_post_contesta_409_y_no_cambia_nada(org_a, admin_client):
    p = _propuesta(org_a)
    ruta = f"{RUTA_LISTA}{p.id}/revisar/"

    primera = admin_client.post(ruta, {"decision": "aceptada"}, format="json")
    assert primera.status_code == 200

    segunda = admin_client.post(
        ruta, {"decision": "rechazada", "comentario": "me arrepentí"},
        format="json")
    assert segunda.status_code == 409
    assert segunda.json()["estado_actual"] == PropuestaSupervisor.ACEPTADA

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA


def test_modificar_sin_cambios_se_rechaza_en_la_entrada(org_a, admin_client):
    p = _propuesta(org_a)
    r = admin_client.post(f"{RUTA_LISTA}{p.id}/revisar/",
                          {"decision": "modificada", "comentario": "x"},
                          format="json")
    assert r.status_code == 400
    assert "cambios" in r.json()


def test_por_http_tampoco_se_puede_editar_la_evidencia(org_a, admin_client):
    p = _propuesta(org_a)
    r = admin_client.post(
        f"{RUTA_LISTA}{p.id}/revisar/",
        {"decision": "modificada", "comentario": "x",
         "cambios": {"evidencia": []}}, format="json")
    assert r.status_code == 400
    p.refresh_from_db()
    assert p.evidencia
    assert p.estado == PropuestaSupervisor.PROPUESTA


def test_por_http_no_se_puede_sugerir_un_responsable_de_otra_organizacion(
        org_a, org_b, admin_client):
    with rls_org(org_b):
        ajeno = _perfil(org_b, "ajeno.http@prueba.local", "OPERACIONES")
    p = _propuesta(org_a)

    r = admin_client.post(
        f"{RUTA_LISTA}{p.id}/revisar/",
        {"decision": "modificada", "comentario": "x",
         "cambios": {"responsable_sugerido": str(ajeno.id)}}, format="json")
    assert r.status_code == 400
    p.refresh_from_db()
    assert p.responsable_sugerido_id is None


# =============================================================================
#  §13  CERO EFECTOS EXTERNOS  --  contados, no deducidos
# =============================================================================

@pytest.fixture
def espia_requests(monkeypatch):
    """
    Cuenta CUALQUIER salida HTTP. Levanta ademas de contar: una prueba que solo
    cuenta puede terminar en verde con la llamada ya hecha.
    """
    import requests
    import requests.sessions
    llamadas = []

    def _trampa(nombre):
        def _f(*a, **k):
            llamadas.append((nombre, str(a[:1])[:120]))
            raise AssertionError(f"salida externa: {nombre} {a[:1]}")
        return _f

    for m in ("get", "post", "put", "patch", "delete", "request", "head",
              "options"):
        monkeypatch.setattr(requests, m, _trampa(m))
    for m in ("get", "post", "put", "patch", "delete", "request", "head",
              "options", "send"):
        monkeypatch.setattr(requests.sessions.Session, m, _trampa(f"Session.{m}"))
    return llamadas


def test_aceptar_no_llama_a_nadie(org_a, admin_profile, espia_requests):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA, comentario="ok")
    assert espia_requests == []


def test_modificar_no_llama_a_nadie(org_a, admin_profile, espia_requests):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.MODIFICADA,
                       comentario="ok", cambios={"prioridad": 12})
    assert espia_requests == []


def test_rechazar_no_llama_a_nadie(org_a, admin_profile, espia_requests):
    p = _propuesta(org_a)
    supervisor.revisar(p, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA, comentario="no")
    assert espia_requests == []


def test_expirar_no_llama_a_nadie(org_a, espia_requests):
    _propuesta(org_a, expira_en=timezone.now() - timezone.timedelta(days=1))
    assert supervisor.expirar_vencidas(org_a) == 1
    assert espia_requests == []


def test_cancelar_no_llama_a_nadie(org_a, espia_requests):
    p = _propuesta(org_a)
    supervisor.cancelar(p, motivo="se cerró solo")
    assert espia_requests == []


def test_el_ciclo_completo_por_http_no_llama_a_nadie(org_a, admin_client,
                                                     espia_requests):
    """La ruta entera, con espía puesto: detectar, proponer, auditar."""
    r = admin_client.post("/api/operaciones/supervisor/ciclo/", {}, format="json")
    assert r.status_code == 200
    assert r.json()["acciones_ejecutadas"] == 0
    assert r.json()["shadow_mode"] is True
    assert espia_requests == []


def test_el_espia_si_detecta_una_llamada(espia_requests):
    """
    LA PRUEBA DE LA PRUEBA.

    Sin esto, "0 llamadas" podría significar "el espía no está puesto". Se
    desarma la guarda a propósito y se comprueba que el espía grita.
    """
    import requests
    with pytest.raises(AssertionError):
        requests.get("http://ejemplo.invalido/")
    assert len(espia_requests) == 1
