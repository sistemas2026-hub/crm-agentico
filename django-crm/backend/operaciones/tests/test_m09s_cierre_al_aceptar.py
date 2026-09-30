# -*- coding: utf-8 -*-
"""
================================================================================
 ACEPTAR UNA PROPUESTA CIERRA EL CASO  --  y las once formas de que no
================================================================================

LO QUE GUARDA ESTE ARCHIVO
--------------------------
Que aceptar NO sea lo mismo que cerrar. El cierre ocurre solo si, releidos los
datos en ese instante, las doce condiciones siguen valiendo -- y si el
interruptor de autonomia no esta tirado.

La frase que resume el riesgo: entre la propuesta y la aceptacion pueden pasar
dias. En ese rato el proveedor pudo reabrir el ticket, alguien pudo cerrar el
caso a mano, o pudo aparecer una orden de trabajo. Cerrar sin volver a mirar
seria sincronizar contra una foto vieja.

COMO SE PRUEBA LA LLAMADA AL MOTOR
----------------------------------
Se sustituye '_pedirle_al_motor', que es la unica salida al mundo de este
modulo. No se simula el motor entero: lo que hay que afirmar aca es que este
lado valida, reclama, registra y no cierra cuando no debe. Lo que el motor hace
con el kill switch, la puerta humana y la idempotencia se prueba en su propio
lado, y ademas se afirma aqui que cuando el motor dice que NO, el caso no se
mueve.
================================================================================
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from cases.models import Case, RespuestaExterna
from common.models import Activity
from conftest import rls_org
from operaciones import cierre_de_caso, supervisor
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

TIPO = PropuestaSupervisor.CASO_DESINCRONIZADO
_ticket = iter(range(70000, 79999))


# =============================================================================
#  andamio
# =============================================================================

def _caso(org, *, externo="Cerrado", status="New", cerro_hace_dias=3,
          leido_hace_horas=1, error_lectura=""):
    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status=status,
        priority="Normal", external_status=externo,
        external_ticket_id=str(next(_ticket)), provider="wisphub",
        external_fetch_error=error_lectura)
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - timedelta(days=12),
        external_status_at=ahora - timedelta(days=cerro_hace_dias),
        external_fetched_at=ahora - timedelta(hours=leido_hace_horas))
    caso.refresh_from_db()
    return caso


def _propuesta(org, caso, estado=PropuestaSupervisor.ACEPTADA):
    senales = [s for s in supervisor.detectar(org)
               if s.origen_id == str(caso.id) and s.tipo == TIPO]
    assert senales, "el detector no vio el caso: el andamio esta mal armado"
    p = supervisor.registrar_propuesta(org, senales[0],
                                       supervisor.analizar(senales[0]))
    if estado != p.estado:
        PropuestaSupervisor.objects.filter(pk=p.pk).update(estado=estado)
        p.refresh_from_db()
    return p


def _motor_dice(respuesta, registro=None):
    """Sustituye la unica salida al mundo. 'registro' cuenta las llamadas."""
    def falso(propuesta_id, id_caso):
        if registro is not None:
            registro.append((propuesta_id, id_caso))
        if isinstance(respuesta, Exception):
            raise respuesta
        return dict(respuesta)
    return falso


def _jefe(org, correo):
    """Un Jefe de Operaciones: el unico rol que puede revisar una propuesta."""
    from common.models import Profile, User

    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return u, Profile.objects.create(user=u, org=org, role="OPERACIONES",
                                     is_active=True)


def _cliente(u, org, perfil):
    """
    Un cliente con el JWT consciente de la organizacion.

    'force_authenticate' NO alcanza: el middleware resuelve 'request.org' del
    token, y sin eso 'HasOrgContext' responde 403 -- que es exactamente lo que
    hizo la primera version de estas pruebas.
    """
    from common.serializer import OrgAwareRefreshToken
    from rest_framework.test import APIClient

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, perfil).access_token}"))
    return c


def _cerro_de_verdad(caso):
    """Se mira la FILA, no lo que devolvio la funcion."""
    caso.refresh_from_db()
    return caso.status == "Closed"


OK_MOTOR = {"cerrado": True, "codigo": "CERRADO", "motivo": "",
            "referencia": "propuesta:x"}


# =============================================================================
#  §1  EL CAMINO QUE TIENE QUE FUNCIONAR
# =============================================================================

def test_1_wisphub_cerrado_y_dexter_abierto_genera_propuesta_de_cierre(org_a):
    """La propuesta pide cerrar, que es lo que se va a aceptar."""
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a))
    assert "cerrar el caso" in p.accion_propuesta.lower()
    assert p.nivel_autonomia_requerido == PropuestaSupervisor.NIVEL_RECOMENDAR


def test_2_aceptada_y_todo_en_orden_intenta_la_ejecucion(org_a, user_profile,
                                                          monkeypatch):
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True, r
    assert len(llamadas) == 1, "se llamo al motor una vez y solo una"
    assert llamadas[0] == (str(p.id), str(caso.id))


def test_3_el_cierre_deja_la_referencia_y_audita_el_caso(org_a, user_profile,
                                                         monkeypatch):
    """
    La trazabilidad, sobre la fila releida.

    'accion_propuesta_ref' guarda la clave de la operacion idempotente -- no un
    id inventado aca -- y la actividad se anota sobre el CASO con
    STATUS_CHANGED, que es el verbo que el CRM ya tiene para esto.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        cierre_de_caso.cerrar(p, actor=user_profile)
        p.refresh_from_db()

        assert p.accion_propuesta_ref == "propuesta:x"
        assert p.estado == PropuestaSupervisor.ACEPTADA, "el estado no cambia"

        #  Se filtra por el VERBO: el CRM ya emite un 'Created' al crear el
        #  caso, asi que contar todas las actividades del caso mediria el
        #  andamio y no el cierre.
        acts = Activity.objects.filter(entity_type="Case", entity_id=caso.id,
                                       action="STATUS_CHANGED")
        assert acts.count() == 1
        a = acts.first()
        assert a.user_id == user_profile.id
        assert a.metadata["propuesta"] == str(p.id)
        assert a.metadata["referencia"] == "propuesta:x"


# =============================================================================
#  §2  LAS DOCE CONDICIONES  --  cada una impide el cierre por su cuenta
# =============================================================================

def test_17_una_propuesta_no_aceptada_no_cierra_nada(org_a, user_profile,
                                                      monkeypatch):
    """
    LA PRUEBA MAS IMPORTANTE DEL ARCHIVO.

    Una propuesta en estado 'propuesta' -- emitida y sin revisar -- no cierra
    nada, y el motor NO se llama ni una vez. Si esto falla, el Supervisor cierra
    casos sin que nadie lo haya decidido.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is False
    assert r["motivo"] == cierre_de_caso.NO_ACEPTADA
    assert llamadas == [], "se llamo al motor con una propuesta sin aceptar"
    assert not _cerro_de_verdad(caso)


@pytest.mark.parametrize("estado", [
    PropuestaSupervisor.RECHAZADA,
    PropuestaSupervisor.CANCELADA,
    PropuestaSupervisor.EXPIRADA,
])
def test_17b_ningun_otro_estado_autoriza_el_cierre(org_a, user_profile,
                                                    monkeypatch, estado):
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a), estado=estado)
        r = cierre_de_caso.cerrar(p, actor=user_profile)
    assert r["cerrado"] is False and llamadas == []


def test_4_un_caso_ya_cerrado_no_se_vuelve_a_cerrar(org_a, user_profile,
                                                     monkeypatch):
    """Alguien lo cerro a mano entre la propuesta y la aceptacion."""
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        Case.objects.filter(pk=caso.pk).update(
            status="Closed", resolved_at=timezone.now())
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.YA_CERRADO
    assert llamadas == []


def test_5_si_el_proveedor_reabrio_el_ticket_no_se_cierra(org_a, user_profile,
                                                          monkeypatch):
    """
    Cerrar aca seria sincronizar AL REVES.

    Es el caso que justifica releer: la propuesta se emitio cuando el ticket
    estaba cerrado alla, y ya no lo esta.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        Case.objects.filter(pk=caso.pk).update(external_status="Nuevo")
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.PROVEEDOR_NO_LO_CERRO
    assert llamadas == []
    assert not _cerro_de_verdad(caso)


def test_6_sin_fecha_de_cierre_del_proveedor_no_se_cierra(org_a, user_profile,
                                                           monkeypatch):
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        Case.objects.filter(pk=caso.pk).update(external_status_at=None)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.SIN_FECHA_DE_CIERRE
    assert llamadas == []


def test_7_una_lectura_fuera_de_frescura_no_sostiene_un_cierre(org_a, user_profile,
                                                                monkeypatch):
    """
    Con la MISMA regla que el detector (HORAS_LECTURA_FRESCA).

    Hoy esta condicion excluye a toda la produccion, y es correcto: mientras la
    sincronizacion este bloqueada, lo que hay son datos viejos.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a,
                     leido_hace_horas=supervisor.HORAS_LECTURA_FRESCA + 2)
        #  El detector tampoco lo ve, asi que la propuesta se arma a mano sobre
        #  un caso fresco y despues se envejece la lectura.
        fresco = _caso(org_a)
        p = _propuesta(org_a, fresco)
        PropuestaSupervisor.objects.filter(pk=p.pk).update(origen_id=str(caso.id))
        p.refresh_from_db()
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.LECTURA_VIEJA
    assert llamadas == []


def test_7b_una_lectura_que_fallo_no_es_una_lectura(org_a, user_profile,
                                                     monkeypatch):
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        Case.objects.filter(pk=caso.pk).update(
            external_fetch_error="HTTPError: 502 Bad Gateway")
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.LECTURA_CON_ERROR
    assert llamadas == []


def test_8_una_respuesta_posterior_al_cierre_lo_impide(org_a, user_profile,
                                                        monkeypatch):
    """
    El proveedor se contradice consigo mismo: dice que cerro y registra una
    respuesta despues. Era un hueco declarado en M09-R; aca ya bloquea.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a, cerro_hace_dias=3)
        p = _propuesta(org_a, caso)
        RespuestaExterna.objects.create(
            org=org_a, case=caso, provider="wisphub", huella=f"h{caso.pk}",
            autor_nombre="tecnico", cuerpo="el cliente volvio a llamar",
            creada_en_proveedor=caso.external_status_at + timedelta(hours=6))
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.RESPUESTA_POSTERIOR
    assert llamadas == []
    assert not _cerro_de_verdad(caso)


def test_8b_una_respuesta_ANTERIOR_al_cierre_no_lo_impide(org_a, user_profile,
                                                           monkeypatch):
    """
    El contraste que hace util a la de arriba: casi todos los tickets tienen
    respuestas, y si cualquiera bloqueara, nunca se cerraria nada. Medido: 551
    respuestas guardadas sobre 177 casos.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a, cerro_hace_dias=3)
        p = _propuesta(org_a, caso)
        RespuestaExterna.objects.create(
            org=org_a, case=caso, provider="wisphub", huella=f"h{caso.pk}",
            autor_nombre="tecnico", cuerpo="se atendio",
            creada_en_proveedor=caso.external_status_at - timedelta(hours=2))
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True, r


def test_9_una_actividad_abierta_NO_bloquea_el_cierre(org_a, user_profile,
                                                      monkeypatch):
    """
    LA REGLA QUE SE QUITO, Y POR QUE.

    La primera version de este flujo vetaba el cierre si habia una actividad
    abierta sobre el caso. Era una regla nueva sin respaldo: nada en el CRM la
    declara, y el docstring de ActividadOperativa dice lo contrario en la otra
    direccion -- "cerrar la actividad no cierra el caso". De la direccion que
    importaba aca no dice nada.

    Y el fondo: el caso se cierra porque EL PROVEEDOR YA LO CERRO. Una actividad
    de seguimiento abierta no contradice eso.

    El conteo se conserva como DATO en el resultado, porque quien decide puede
    querer saberlo. Contar no es vetar.
    """
    from operaciones.models import ActividadOperativa

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        ActividadOperativa.objects.create(
            org=org_a, titulo="Confirmar con el cliente",
            responsable=user_profile, origen_tipo="case",
            origen_id=str(caso.id))
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True, r
    #  Y el dato viaja, para que la pantalla pueda mostrarlo si algun dia se
    #  decide que importa.
    assert r["actividades_abiertas"] == 1
    assert r["ordenes_abiertas"] == 0


def test_9b_una_orden_de_trabajo_abierta_tampoco_bloquea(org_a, user_profile,
                                                          monkeypatch):
    """Mismo criterio. Se cuenta y no se veta."""
    import uuid as _uuid

    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        sufijo = _uuid.uuid4().hex[:8]
        tipo = WorkType.objects.create(org=org_a, nombre="Visita " + sufijo,
                                       codigo="vis_" + sufijo)
        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"campos": [], "evidencias": []})
        OrdenTrabajo.objects.create(
            org=org_a, numero=9501, tipo_trabajo_version=version,
            cliente_nombre="Cliente", cliente_direccion="Calle 1",
            origen_tipo="case", origen_ref=str(caso.id))
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True, r
    assert r["ordenes_abiertas"] == 1


def test_9c_una_actividad_completada_no_se_cuenta(org_a, user_profile,
                                                   monkeypatch):
    from operaciones.models import ActividadOperativa

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        ActividadOperativa.objects.create(
            org=org_a, titulo="Ya se hizo", responsable=user_profile,
            origen_tipo="case", origen_id=str(caso.id),
            estado_operativo=ActividadOperativa.COMPLETADA)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True
    assert r["actividades_abiertas"] == 0


def test_16_un_caso_de_otra_organizacion_no_se_toca(org_a, org_b, user_profile,
                                                     monkeypatch):
    """
    'origen_id' es texto libre: podria apuntar a un caso de otra empresa. Dos
    capas -- el filtro por org y la RLS -- y el efecto que se afirma es que el
    caso ajeno no se mueve.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_b):
        ajeno = _caso(org_b)
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a))
        PropuestaSupervisor.objects.filter(pk=p.pk).update(origen_id=str(ajeno.id))
        p.refresh_from_db()
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is False
    assert r["motivo"] == cierre_de_caso.CASO_NO_ENCONTRADO
    assert llamadas == []
    assert not _cerro_de_verdad(ajeno)


# =============================================================================
#  §3  EL INTERRUPTOR, LA CONCURRENCIA Y LOS FALLOS
# =============================================================================

def test_10_si_el_interruptor_esta_detenido_no_se_cierra(org_a, user_profile,
                                                         monkeypatch):
    """
    El kill switch lo comprueba el MOTOR -- este proceso no puede leerlo, no
    tiene USAGE en el esquema 'asistente'. Lo que se afirma aca es la reaccion:
    el caso no se mueve, la decision humana se conserva, y el motivo queda.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _motor_dice(
        {"cerrado": False, "codigo": cierre_de_caso.BLOQUEADO_POR_INTERRUPTOR,
         "motivo": "detenido: parada de emergencia", "referencia": ""}))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)
        p.refresh_from_db()

    assert r["cerrado"] is False
    assert r["motivo"] == cierre_de_caso.BLOQUEADO_POR_INTERRUPTOR
    assert not _cerro_de_verdad(caso)
    assert p.estado == PropuestaSupervisor.ACEPTADA, "se perdio la decision humana"
    assert p.accion_propuesta_ref == "", "sin cierre no hay referencia que guardar"

    anotado = Activity.objects.filter(entity_type="PropuestaSupervisor",
                                      entity_id=p.id).first()
    assert anotado is not None
    assert anotado.metadata["resultado"] == "aceptada, ejecucion fallida"
    assert anotado.metadata["motivo"] == cierre_de_caso.BLOQUEADO_POR_INTERRUPTOR


def test_11_una_propuesta_no_se_puede_aceptar_dos_veces(org_a, user_profile):
    """La segunda revision no decide: 'revisar' relee la fila bloqueada."""
    with rls_org(org_a):
        caso = _caso(org_a)
        senal = [s for s in supervisor.detectar(org_a)
                 if s.origen_id == str(caso.id) and s.tipo == TIPO][0]
        p = supervisor.registrar_propuesta(org_a, senal,
                                           supervisor.analizar(senal))
        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="primera")
        otra = PropuestaSupervisor.objects.get(pk=p.pk)
        with pytest.raises(Exception):
            supervisor.revisar(otra, actor=user_profile,
                               decision=PropuestaSupervisor.RECHAZADA,
                               comentario="segunda")
        p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.ACEPTADA
    assert not _cerro_de_verdad(caso)


def test_12_dos_cierres_de_la_misma_propuesta_no_cierran_dos_veces(
        org_a, user_profile, monkeypatch):
    """
    QUIEN PROTEGE AHORA, Y QUIEN NO.

    Este modulo tuvo un "reclamo" propio -- un UPDATE condicional sobre
    accion_propuesta_ref -- y se saco: era redundante con
    asistente.operaciones_externas, que excluye por clave primaria, compara el
    hash de los argumentos resueltos y falla cerrado. El reclamo local no hacia
    ninguna de las tres, y encima le daba dos significados a un campo que tenia
    uno.

    Lo que se pierde, dicho sin adornos: las dos llamadas SALEN. Lo que no pasa
    es que el caso se cierre dos veces -- la segunda recibe del motor el
    resultado de la primera. Esta prueba afirma eso, no que se llame una vez.
    """
    llamadas = []
    #  La segunda vez el motor contesta lo que contesto la primera, que es lo
    #  que hace de verdad cuando la clave ya esta registrada como exitosa.
    respuestas = [OK_MOTOR,
                  {"cerrado": True, "codigo": "CERRADO",
                   "motivo": "ya se habia ejecutado antes",
                   "referencia": "propuesta:x"}]

    def motor(propuesta_id, id_caso):
        llamadas.append((propuesta_id, id_caso))
        return dict(respuestas[min(len(llamadas) - 1, 1)])

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", motor)
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        primera = cierre_de_caso.cerrar(p, actor=user_profile)
        otra = PropuestaSupervisor.objects.get(pk=p.pk)
        segunda = cierre_de_caso.cerrar(otra, actor=user_profile)
        p.refresh_from_db()

    assert primera["cerrado"] is True
    assert segunda["cerrado"] is True, "la segunda no es un error: ya estaba hecho"
    assert len(llamadas) == 2, (
        "las dos llamadas salen; la idempotencia esta del otro lado")
    #  Y el campo conserva UN solo significado: la referencia de la ejecucion.
    assert p.accion_propuesta_ref == "propuesta:x"


def test_13_el_campo_de_referencia_tiene_un_solo_significado(
        org_a, user_profile, monkeypatch):
    """
    accion_propuesta_ref guarda la referencia de la ejecucion y nada mas.

    Nunca vale un marcador de "en curso": ese uso existio y se quito. Un campo
    con dos semanticas es lo que este proyecto evita en otros sitios, y aca no
    hacia falta porque el registro del motor ya distingue "en curso" de "hecha".
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        assert p.accion_propuesta_ref == "", "nace vacio"
        cierre_de_caso.cerrar(p, actor=user_profile)
        p.refresh_from_db()

    assert p.accion_propuesta_ref == "propuesta:x"
    assert "en_curso" not in p.accion_propuesta_ref
    assert not hasattr(cierre_de_caso, "_reclamar"), (
        "el reclamo local volvio: la concurrencia la pone la idempotencia "
        "del motor")


def test_13b_si_el_motor_dice_repetida_el_resultado_es_cerrado(org_a, user_profile,
                                                                monkeypatch):
    """
    Idempotencia: la misma propuesta dos veces no cierra dos veces, y la segunda
    NO es un error. El motor devuelve lo que el CRM contesto la primera vez.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _motor_dice(
        {"cerrado": True, "codigo": "CERRADO",
         "motivo": "ya se habia ejecutado antes", "referencia": "propuesta:x"}))
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a))
        r = cierre_de_caso.cerrar(p, actor=user_profile)
    assert r["cerrado"] is True


def test_14_un_error_del_endpoint_deja_el_caso_abierto(org_a, user_profile,
                                                        monkeypatch):
    """
    'aceptada, ejecucion fallida'. Sin inventar un estado nuevo de propuesta.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _motor_dice(
        {"cerrado": False, "codigo": "FALLO_AL_CERRAR",
         "motivo": "HTTPError: 400 Closed date is required", "referencia": ""}))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)
        p.refresh_from_db()

    assert r["cerrado"] is False
    assert not _cerro_de_verdad(caso)
    assert p.estado == PropuestaSupervisor.ACEPTADA
    anotado = Activity.objects.filter(entity_type="PropuestaSupervisor",
                                      entity_id=p.id).first()
    assert anotado.metadata["resultado"] == "aceptada, ejecucion fallida"
    assert "400" in anotado.metadata["detalle"]


def test_15_si_la_red_se_corta_el_caso_queda_abierto_y_se_puede_reintentar(org_a,
                                                                    user_profile,
                                                                    monkeypatch):
    """
    LO QUE NO SE PUEDE PROMETER, dicho aca y no escondido.

    Si la peticion salio y la respuesta se perdio, NADIE sabe si el cierre se
    aplico. Se suelta el reclamo para poder reintentar, y lo que garantiza que
    un reintento no cierre dos veces es la idempotencia del motor -- no este
    modulo.
    """
    import requests

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(requests.ConnectionError("se corto")))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)
        p.refresh_from_db()

    assert r["cerrado"] is False
    assert r["motivo"] == cierre_de_caso.MOTOR_NO_RESPONDIO
    assert not _cerro_de_verdad(caso)
    assert p.accion_propuesta_ref == "", "no se cerro: no hay referencia que guardar"
    assert p.estado == PropuestaSupervisor.ACEPTADA


# =============================================================================
#  §4  LA GARANTIA DE FONDO
# =============================================================================

def test_aceptar_por_si_solo_no_cierra_ningun_caso(org_a, user_profile):
    """
    'revisar' NO ejecuta. Se afirma releyendo la fila del caso, no buscando la
    ausencia de una llamada: "no vimos ninguna ejecucion" es una afirmacion
    sobre lo que alguien no vio.

    El dia que 'revisar' empiece a cerrar por su cuenta, esta prueba falla -- y
    es la que hay que mirar, porque significaria que el cierre dejo de pasar por
    las doce validaciones.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        antes = Case.objects.filter(id=caso.id).values().first()
        senal = [s for s in supervisor.detectar(org_a)
                 if s.origen_id == str(caso.id) and s.tipo == TIPO][0]
        p = supervisor.registrar_propuesta(org_a, senal,
                                           supervisor.analizar(senal))
        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="de acuerdo")
        despues = Case.objects.filter(id=caso.id).values().first()

    assert antes == despues, "aceptar movio el caso sin pasar por las validaciones"


# =============================================================================
#  §5  LA VISTA  --  el unico punto donde aceptar dispara el cierre
# =============================================================================

def test_la_vista_cierra_al_aceptar_y_devuelve_el_resultado(org_a, monkeypatch):
    """
    EL PUNTO A y B, comprobados desde el borde de HTTP.

    A. 'supervisor.revisar' corre primero y en su propia transaccion, asi que la
       decision humana esta persistida antes de que se intente cerrar.
    B. El cierre pasa DESPUES y fuera de esa transaccion. Se comprueba por el
       efecto observable: la propuesta queda ACEPTADA y el caso cerrado, y el
       cuerpo trae los tres campos que la pantalla necesita.

    Sin esta prueba, el punto 3 del bloque quedaba sin verificar: las 25 de
    arriba prueban 'cierre_de_caso.cerrar' directamente, no que alguien lo llame.
    """
    from rest_framework.test import APIClient

    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))

    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)

        u, perfil = _jefe(org_a, "jefe.m09s@test.com")
        cli = _cliente(u, org_a, perfil)
        r = cli.post(f"/api/operaciones/propuestas/{p.id}/revisar/",
                     {"decision": PropuestaSupervisor.ACEPTADA,
                      "comentario": "de acuerdo, cerrar"}, format="json")

    assert r.status_code == 200, r.data
    #  Los tres campos del contrato con el frontend.
    assert r.data["ejecutada"] is True, r.data
    assert r.data["motivo"] == ""
    assert "detalle" in r.data

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA
    assert len(llamadas) == 1, "la vista no disparo el cierre"
    assert perfil.id is not None


def test_la_vista_conserva_la_decision_si_el_cierre_falla(org_a, monkeypatch):
    """
    EL PUNTO C, desde HTTP. La decision vale aunque el cierre no ocurra.

    Y la respuesta lo dice con un motivo en CLAVE, no en prosa: de eso depende
    que la pantalla distinga "esta detenido" de "cambio la condicion".
    """
    from rest_framework.test import APIClient

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _motor_dice(
        {"cerrado": False, "codigo": cierre_de_caso.BLOQUEADO_POR_INTERRUPTOR,
         "motivo": "detenido: parada de emergencia", "referencia": ""}))

    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
        u, perfil2 = _jefe(org_a, "jefe2.m09s@test.com")
        cli = _cliente(u, org_a, perfil2)
        r = cli.post(f"/api/operaciones/propuestas/{p.id}/revisar/",
                     {"decision": PropuestaSupervisor.ACEPTADA,
                      "comentario": "de acuerdo"}, format="json")

    assert r.status_code == 200, r.data
    assert r.data["ejecutada"] is False
    assert r.data["motivo"] == cierre_de_caso.BLOQUEADO_POR_INTERRUPTOR

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA, "se perdio la decision"
    assert not _cerro_de_verdad(caso)


def test_una_propuesta_de_otro_tipo_no_intenta_ningun_cierre(org_a, monkeypatch):
    """
    La vista solo cierra para 'caso_desincronizado'. Aceptar cualquier otra
    propuesta no dispara nada, y 'ejecutada' sigue siendo False -- que es la
    verdad: el Supervisor observa y recomienda, y esta es la unica accion que
    ejecuta.
    """
    from rest_framework.test import APIClient

    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))

    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
        #  Se le cambia el tipo: lo que se prueba es el filtro de la vista.
        PropuestaSupervisor.objects.filter(pk=p.pk).update(
            tipo_senal=PropuestaSupervisor.CASO_ANTIGUO)
        u, perfil3 = _jefe(org_a, "jefe3.m09s@test.com")
        cli = _cliente(u, org_a, perfil3)
        r = cli.post(f"/api/operaciones/propuestas/{p.id}/revisar/",
                     {"decision": PropuestaSupervisor.ACEPTADA,
                      "comentario": "de acuerdo"}, format="json")

    assert r.status_code == 200, r.data
    assert r.data["ejecutada"] is False
    assert r.data["motivo"] == ""
    assert llamadas == [], "intento cerrar una propuesta que no es de cierre"
    assert not _cerro_de_verdad(caso)

# =============================================================================
#  §7  LO QUE EL CIERRE NO TOCA, Y EL NIVEL QUE NO DECIDE
# =============================================================================

def test_18_el_cierre_no_llama_a_wisphub_por_ningun_lado(org_a, user_profile,
                                                          monkeypatch):
    """
    La unica salida al mundo es el motor. WispHub no se entera.

    NO se sustituye '_pedirle_al_motor': se espia 'requests' entero, que es la
    capa por donde tendria que salir cualquier llamada a un tercero. Asi la
    prueba no cree en el disenio -- mide las URL que de verdad se pidieron.

    Sin esto, la garantia "el cierre no modifica WispHub" se sostenia en que
    nadie habia escrito esa llamada, que es exactamente el tipo de afirmacion
    que este repositorio no acepta: se afirma sobre el efecto, no sobre la
    ausencia observada al leer el codigo.
    """
    import requests

    urls = []

    def _espia(verbo):
        def falso(url, *a, **kw):
            urls.append((verbo, url))

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return dict(OK_MOTOR)
            return R()
        return falso

    for verbo in ("post", "get", "patch", "put", "delete", "request"):
        monkeypatch.setattr(requests, verbo, _espia(verbo), raising=False)

    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["cerrado"] is True, r
    assert len(urls) == 1, f"se esperaba UNA sola llamada saliente: {urls}"

    verbo, url = urls[0]
    assert verbo == "post", verbo
    #  Va al motor, y a la ruta del cierre por propuesta.
    assert f"/interno/propuesta/{p.id}/cerrar-caso" in url, url
    #  Y a nada mas. Se comprueba contra el proveedor por nombre y por dominio.
    for prohibido in ("wisphub", "api.wisphub", "smartolt"):
        assert prohibido not in url.lower(), f"salio hacia {prohibido}: {url}"


@pytest.mark.parametrize("nivel", [0, 1, 2, 3, 4])
def test_19_el_nivel_de_autonomia_no_veta_una_decision_humana(org_a, user_profile,
                                                               monkeypatch, nivel):
    """
    'nivel_autonomia_requerido' NO es un permiso, y esta prueba lo fija.

    El campo dice "que nivel HABRIA hecho falta para ejecutarla sola": es
    contrafactico sobre la autonomia, no una condicion sobre lo que una persona
    puede autorizar. La autorizacion humana la da 'frontera.humana()', que pide
    actor y evidencia y no consulta ni techo ni interruptor de autonomia.

    Se decidio el 29/09/2026 NO convertirlo en permiso, y el motivo es medible:
    las 108 propuestas 'caso_desincronizado' vivas en produccion son de nivel 0
    --se crearon antes de que el detector pasara a 'recomendar'-- y una regla
    "nivel 0 no cierra" las habria dejado sin salida para siempre, porque
    'ESTADOS_QUE_BLOQUEAN' impide que el detector las vuelva a proponer.

    Se recorren los cinco niveles a proposito: la prueba tiene que fallar el dia
    que alguien introduzca el veto por CUALQUIERA de ellos, no solo por el 0.
    """
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        PropuestaSupervisor.objects.filter(pk=p.pk).update(
            nivel_autonomia_requerido=nivel)
        p.refresh_from_db()

        r = cierre_de_caso.cerrar(p, actor=user_profile)

    #  El motor esta sustituido, asi que el PATCH real no ocurre: lo que se
    #  afirma es que el nivel no impidio LLEGAR a pedirselo. Que el caso
    #  quede Closed de verdad lo prueban test_2 y test_3 con el motor real.
    assert r["cerrado"] is True, f"nivel {nivel} bloqueo una decision humana: {r}"
    assert r["motivo"] == "", r


def test_20_una_propuesta_aceptada_con_cierre_fallido_no_tiene_vuelta(
        org_a, user_profile, monkeypatch):
    """
    ACEPTADA != CERRADA, y no hay reintento. Se afirma el estado final entero.

    Decision del 29/09/2026 (alternativa D): la propuesta queda como historico.
    No se reabre, no se repropone y no existe un endpoint de reintento. Esta
    prueba fija las cuatro mitades de esa decision juntas, porque cada una por
    separado se puede romper sin que las otras se enteren.
    """
    monkeypatch.setattr(
        cierre_de_caso, "_pedirle_al_motor",
        _motor_dice({"cerrado": False, "codigo": "FALLO_AL_CERRAR",
                     "motivo": "el CRM devolvio 500", "referencia": ""}))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        r = cierre_de_caso.cerrar(p, actor=user_profile)

        #  1. no se cerro, y el motivo viaja en clave
        assert r["cerrado"] is False
        assert r["motivo"] == "FALLO_AL_CERRAR"
        #  2. el caso quedo como estaba
        assert not _cerro_de_verdad(caso)
        #  3. la decision humana NO se revirtio
        p.refresh_from_db()
        assert p.estado == PropuestaSupervisor.ACEPTADA
        #  4. queda la trazabilidad, sobre la propuesta y no sobre el caso
        act = Activity.objects.filter(entity_type="PropuestaSupervisor",
                                      entity_id=p.id).order_by("-created_at").first()
        assert act is not None
        assert act.metadata["motivo"] == "FALLO_AL_CERRAR"
        assert act.metadata["resultado"] == "aceptada, ejecucion fallida"
        assert act.user_id == user_profile.id

        #  5. y no vuelve sola: su estado esta entre los que frenan al detector
        assert p.estado in PropuestaSupervisor.ESTADOS_QUE_BLOQUEAN, (
            "si 'aceptada' dejara de bloquear, el detector repondria la "
            "propuesta y eso SERIA un reintento automatico")

# =============================================================================
#  §8  EL ESTADO DEL CASO VIAJA A LA BANDEJA, Y NO ES EL DE LA PROPUESTA
# =============================================================================

def test_21_el_contexto_dice_si_el_caso_del_origen_ya_cerro(org_a):
    """
    'origen_cerrado' es un DATO del caso, no un estado nuevo de la propuesta.

    La bandeja de pendientes lo necesita para no mostrar como trabajo operativo
    algo que ya no lo es. Se afirma sobre los dos lados -- abierto y cerrado --
    porque una version que devolviera siempre False pasaria una prueba que solo
    mirara el caso abierto.
    """
    from operaciones import contexto_propuesta

    with rls_org(org_a):
        abierto = _caso(org_a, status="New")
        p_abierto = _propuesta(org_a, abierto, estado=PropuestaSupervisor.PROPUESTA)

        cerrado = _caso(org_a, status="New")
        p_cerrado = _propuesta(org_a, cerrado, estado=PropuestaSupervisor.PROPUESTA)
        #  Se cierra DESPUES de crear la propuesta: es el escenario real -- el
        #  caso lo cerro otra via y la propuesta quedo sin revisar.
        Case.objects.filter(pk=cerrado.pk).update(status="Closed")

        ctx = contexto_propuesta.contexto_de(org_a, [p_abierto, p_cerrado])

    assert ctx[str(p_abierto.id)]["origen_cerrado"] is False
    assert ctx[str(p_cerrado.id)]["origen_cerrado"] is True
    #  Y lo que NO cambia: el estado de la propuesta sigue siendo el suyo. Un
    #  caso cerrado no inventa una decision que nadie tomo.
    p_cerrado.refresh_from_db()
    assert p_cerrado.estado == PropuestaSupervisor.PROPUESTA


def test_22_la_bandeja_recibe_el_dato_por_el_serializer(org_a):
    """
    Que el contexto lo calcule no sirve si el serializer no lo entrega.

    Es la falla que este repositorio ya vio cuatro veces: el dato existe de un
    lado de la frontera y del otro no. Se afirma sobre la carga util.
    """
    from operaciones import contexto_propuesta
    from operaciones.serializers import PropuestaListaSerializer

    with rls_org(org_a):
        caso = _caso(org_a, status="New")
        p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
        Case.objects.filter(pk=caso.pk).update(status="Closed")

        ctx = contexto_propuesta.contexto_de(org_a, [p])
        datos = PropuestaListaSerializer(p, context={"contexto": ctx}).data

    assert "origen_cerrado" in datos, "el serializer no entrega el dato"
    assert datos["origen_cerrado"] is True
    assert datos["estado"] == PropuestaSupervisor.PROPUESTA
