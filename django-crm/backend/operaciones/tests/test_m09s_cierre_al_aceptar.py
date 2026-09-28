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


def test_9_una_actividad_pendiente_bloquea_el_cierre(org_a, user_profile,
                                                      monkeypatch):
    """Alguien todavia esta trabajando en el caso."""
    from operaciones.models import ActividadOperativa

    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        ActividadOperativa.objects.create(
            org=org_a, titulo="Confirmar con el cliente",
            responsable=user_profile, origen_tipo="case",
            origen_id=str(caso.id))
        r = cierre_de_caso.cerrar(p, actor=user_profile)

    assert r["motivo"] == cierre_de_caso.TRABAJO_PENDIENTE
    assert llamadas == []


def test_9b_una_actividad_ya_completada_no_bloquea(org_a, user_profile,
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

    assert r["cerrado"] is True, r


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
    assert p.accion_propuesta_ref == "", "el reclamo no se solto: no se podria reintentar"

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


def test_12_dos_cierres_a_la_vez_solo_llaman_al_motor_una_vez(org_a, user_profile,
                                                               monkeypatch):
    """
    EL RECLAMO, Y POR QUE NO ES UN 'if'.

    El derecho a cerrar se gana con un UPDATE condicional sobre la propuesta y
    se mira el rowcount. La segunda llamada no ejecuta nada.
    """
    llamadas = []
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        _motor_dice(OK_MOTOR, llamadas))
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        primera = cierre_de_caso.cerrar(p, actor=user_profile)
        #  Una segunda copia del objeto, como la que traeria otra peticion HTTP.
        otra = PropuestaSupervisor.objects.get(pk=p.pk)
        segunda = cierre_de_caso.cerrar(otra, actor=user_profile)

    assert primera["cerrado"] is True
    assert segunda["cerrado"] is False
    assert len(llamadas) == 1, f"el motor se llamo {len(llamadas)} veces"


def test_13_el_reclamo_no_se_puede_tomar_dos_veces(org_a, user_profile):
    """La mecanica del reclamo, aislada: el segundo intento devuelve False."""
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a))
        assert cierre_de_caso._reclamar(p) is True
        assert cierre_de_caso._reclamar(p) is False
        p.refresh_from_db()
        assert p.accion_propuesta_ref == cierre_de_caso.EN_CURSO


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


def test_15_si_la_red_se_corta_se_suelta_el_reclamo_para_reintentar(org_a,
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
    assert p.accion_propuesta_ref == "", "sin soltar el reclamo no hay reintento"
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
