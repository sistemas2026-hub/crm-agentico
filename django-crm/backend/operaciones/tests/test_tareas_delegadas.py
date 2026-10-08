# -*- coding: utf-8 -*-
"""
===============================================================================
 LO QUE UNA PERSONA LE DELEGA AL SUPERVISOR, DESDE EL CHAT
===============================================================================

LA DECISION QUE ESTAS PRUEBAS SOSTIENEN
---------------------------------------
El catalogo es CERRADO. El modelo entiende la frase y elige una tarea de una
lista que el codigo ya sabe hacer; no construye la tarea. La alternativa era
que de la frase saliera la accion, y entonces alguien escribiendo "cerra los
que esten cerrados en WispHub" --sin la parte del diagnostico-- habria hecho
que el Supervisor cerrara casos sin mirar el equipo. La garantia de un cliente
habria dependido de como estaba redactada una frase.

LAS CUATRO COSAS QUE SE AFIRMAN
-------------------------------
1. Una clave que no esta en el catalogo NO se puede delegar.
2. Delegar exige una PERSONA, y esa persona no sale de lo que diga el modelo.
3. Con la tarea delegada pero el nivel bajo, NO se cierra nada -- y el chat lo
   DICE, porque el silencio ahi deja a alguien creyendo que quedo andando.
4. Quitar la tarea detiene el cierre, y queda el registro de que existio.
"""
import pytest
from django.utils import timezone

from common.models import Org, Profile, User
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P
from operaciones.tareas_modelos import TareaDelegada


@pytest.fixture
def org_y_persona(db):
    org = Org.objects.create(name="Org de las tareas")
    usuario = User.objects.create(email="jefa@tareas.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    return org, perfil


# ===========================================================================
#  1. EL CATALOGO ES CERRADO
# ===========================================================================

@pytest.mark.django_db
def test_una_tarea_que_no_existe_no_se_puede_delegar(org_y_persona):
    org, perfil = org_y_persona
    with pytest.raises(td.ErrorTarea):
        td.delegar(org, "reiniciar_todas_las_onus", actor=perfil)
    assert TareaDelegada.objects.filter(org=org).count() == 0


@pytest.mark.django_db
def test_el_chat_no_puede_inventar_una_tarea(org_y_persona):
    """
    La herramienta del chat contesta un error legible, no una excepcion.

    Importa que sea legible: el modelo tiene que poder decirle a la persona
    "eso no lo se hacer" en vez de callarse o de intentar armarlo con otras
    herramientas.
    """
    from operaciones import chat_herramientas

    org, perfil = org_y_persona
    r = chat_herramientas.ejecutar(
        org, "delegar_tarea",
        {"clave": "cerrar_todo_lo_que_este_viejo"}, actor=perfil)
    assert r["error"] == "no_se_pudo_delegar"
    assert "no es una tarea" in r["detalle"]
    assert TareaDelegada.objects.filter(org=org).count() == 0


@pytest.mark.django_db
def test_una_clave_huerfana_en_la_base_no_habilita_nada(org_y_persona):
    #  Una tarea que se saco del catalogo pero quedo su fila: no habilita.
    #  'esta_delegada' mira el catalogo primero, asi que una clave vieja es
    #  inerte en vez de abrir una puerta que ya nadie mantiene.
    org, perfil = org_y_persona
    TareaDelegada.objects.create(
        org=org, clave="tarea_que_ya_no_existe", activa=True,
        delegada_por=perfil, delegada_en=timezone.now())
    assert td.esta_delegada(org, "tarea_que_ya_no_existe") is False


# ===========================================================================
#  2. DELEGAR EXIGE UNA PERSONA
# ===========================================================================

@pytest.mark.django_db
def test_sin_persona_no_se_delega(org_y_persona):
    org, _perfil = org_y_persona
    with pytest.raises(td.ErrorTarea):
        td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=None)
    assert TareaDelegada.objects.filter(org=org).count() == 0


@pytest.mark.django_db
def test_el_actor_NO_es_un_argumento_que_el_modelo_pueda_proponer():
    """
    Lo que el modelo propone se filtra contra la lista blanca, y 'actor' no
    esta en ella.

    Si estuviera, bastaria con que alguien lo dictara en un mensaje para que la
    tarea quedara delegada a nombre de quien no la pidio. Es la misma regla que
    'inyectar_sesion' aplica en el motor.
    """
    from operaciones import chat_herramientas

    assert "actor" not in chat_herramientas.ARGUMENTOS["delegar_tarea"]
    assert "actor" not in chat_herramientas.ARGUMENTOS["quitar_tarea"]
    #  Y el despachador SI se lo pone, desde fuera de los argumentos.
    assert "delegar_tarea" in chat_herramientas.NECESITAN_ACTOR


@pytest.mark.django_db
def test_el_modelo_no_puede_colar_el_actor_por_los_argumentos(org_y_persona):
    """
    Medido por efecto: se le pasa un 'actor' entre los argumentos --como lo
    haria un mensaje que intente dictarlo-- y se comprueba que la tarea queda a
    nombre de la persona de la conversacion, no del que vino en el argumento.
    """
    from operaciones import chat_herramientas

    org, perfil = org_y_persona
    otro_usuario = User.objects.create(email="otro@tareas.test", name="Otro")
    otro = Profile.objects.create(org=org, user=otro_usuario, role="USER",
                                  is_active=True)

    chat_herramientas.ejecutar(
        org, "delegar_tarea",
        {"clave": td.CERRAR_DESINCRONIZADOS, "actor": otro},
        actor=perfil)

    fila = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert fila.delegada_por_id == perfil.id, (
        "la tarea quedo a nombre del actor que vino en los argumentos: ese "
        "campo tiene que salir de la conversacion verificada")


# ===========================================================================
#  3. DELEGAR NO ES AMPLIAR EL ALCANCE
# ===========================================================================

@pytest.mark.django_db
def test_delegar_con_el_nivel_bajo_no_cierra_y_el_chat_lo_DICE(org_y_persona):
    """
    El silencio aqui seria el peor resultado: la persona delega, el chat
    contesta "listo", y se va creyendo que quedo andando cuando no hace nada.
    """
    from operaciones import chat_herramientas

    org, perfil = org_y_persona
    r = chat_herramientas.ejecutar(
        org, "delegar_tarea",
        {"clave": td.CERRAR_DESINCRONIZADOS,
         "pedido": "cerra los que ya esten cerrados en wisphub si el equipo esta bien"},
        actor=perfil)

    assert r["delegada"] == td.CERRAR_DESINCRONIZADOS
    assert r["ya_puede_actuar"] is False
    assert "nivel de autonomía" in r["que_falta"]


@pytest.mark.django_db
def test_la_frase_con_la_que_se_pidio_queda_guardada(org_y_persona):
    #  No decide nada --lo que se ejecuta es la tarea del catalogo-- pero
    #  permite ver, meses despues, que creia estar pidiendo quien la delego.
    from operaciones import chat_herramientas

    org, perfil = org_y_persona
    frase = "todo ticket cerrado en wisphub y abierto en dexter, diagnosticalo y cerralo"
    chat_herramientas.ejecutar(
        org, "delegar_tarea",
        {"clave": td.CERRAR_DESINCRONIZADOS, "pedido": frase}, actor=perfil)

    fila = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert fila.pedido_textual == frase


# ===========================================================================
#  4. LA PUERTA, MEDIDA SOBRE EL CASO
# ===========================================================================

def _caso_desincronizado(org, ticket, servicio):
    from datetime import timedelta as t

    from cases.models import Case

    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id=ticket, provider="wisphub",
        external_service_id=servicio)
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - t(days=12),
        external_status_at=ahora - t(days=3),
        external_fetched_at=ahora - t(hours=1))
    caso.refresh_from_db()
    return caso


@pytest.mark.django_db
def test_sin_tarea_delegada_NO_se_cierra_aunque_el_nivel_lo_permita(
        org_y_persona, monkeypatch):
    """
    LA PUERTA NUEVA, medida sobre el caso en la base.

    El nivel dice CUANTO puede hacer el Supervisor; la tarea dice QUE le
    pidieron. Sin esta puerta, subir el nivel para habilitar cualquier otra
    cosa encenderia tambien el cierre de casos, en silencio.
    """
    from cases.models import Case
    from operaciones import (autonomia, chat_herramientas, cierre_de_caso,
                             fuentes_adaptadores, supervisor)

    org, perfil = org_y_persona
    caso = _caso_desincronizado(org, "990001", "9901")

    llamadas = []
    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia",
                        lambda: {"permitido": True, "estado": "activo",
                                 "motivo": ""})
    def _motor(propuesta_id, caso_id):
        #  EL CASO LO CIERRA EL MOTOR, no este codigo: el doble escribe el
        #  estado porque eso es lo que pasa del otro lado de la frontera. Un
        #  doble que devolviera "cerrado" sin cerrar nada haria pasar una
        #  prueba sobre un efecto que no ocurre.
        llamadas.append(caso_id)
        Case.objects.filter(id=caso_id).update(status="Closed",
                                               resolved_at=timezone.now())
        return {"cerrado": True, "referencia": "idem:prueba"}

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _motor)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: {
                            "estado": "en_linea", "causa_caida": "",
                            "senal": "buena", "senal_dbm": -20.55,
                            "estado_config": "match"})
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")

    #  Todo autorizado MENOS la tarea.
    assert td.esta_delegada(org, td.CERRAR_DESINCRONIZADOS) is False
    supervisor.correr_ciclo(org)
    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", "nadie se lo pidio: no se cierra"
    assert llamadas == []

    #  Y ahora SI se lo piden.
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               pedido_textual="cerralos vos")
    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "Closed", (
        "con la tarea delegada y el nivel en 3, el caso tiene que cerrarse")


@pytest.mark.django_db
def test_quitar_la_tarea_detiene_el_cierre_y_deja_el_registro(org_y_persona):
    org, perfil = org_y_persona
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)
    assert td.esta_delegada(org, td.CERRAR_DESINCRONIZADOS) is True

    td.quitar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)
    assert td.esta_delegada(org, td.CERRAR_DESINCRONIZADOS) is False

    #  LA FILA SIGUE: borrarla haria imposible contestar "¿esto estuvo delegado
    #  alguna vez?", que es la pregunta del dia que un caso aparezca cerrado y
    #  nadie recuerde haberlo pedido.
    fila = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert fila.activa is False
    assert fila.quitada_por_id == perfil.id
    assert fila.quitada_en is not None
    assert fila.delegada_por_id == perfil.id, "no se pierde quien la delego"


@pytest.mark.django_db
def test_volver_a_delegar_la_pone_a_nombre_de_quien_la_pide_ahora(
        org_y_persona):
    #  Dejar el actor viejo haria que la auditoria culpara a quien la delego
    #  hace meses por algo que reactivo otra persona hoy.
    org, perfil = org_y_persona
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)
    td.quitar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)

    otro_usuario = User.objects.create(email="otra@tareas.test", name="Otra")
    otra = Profile.objects.create(org=org, user=otro_usuario, role="ADMIN",
                                  is_active=True)
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=otra)

    fila = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert fila.activa is True
    assert fila.delegada_por_id == otra.id


@pytest.mark.django_db
def test_el_catalogo_dice_que_NO_hace_cada_tarea(org_y_persona):
    #  El modelo tiene que poder decir qué no va a pasar. Sin esa frase lo
    #  completaria por su cuenta, que es justo lo que no debe hacer con algo
    #  que va a actuar solo.
    from operaciones import chat_herramientas

    org, _perfil = org_y_persona
    r = chat_herramientas.ejecutar(org, "tareas_disponibles", {})
    assert r["tareas"], "el catalogo no puede estar vacio"
    for t in r["tareas"]:
        assert t["que_no_hace"].strip(), f"{t['clave']} no dice que NO hace"
        assert t["que_hace"].strip()
