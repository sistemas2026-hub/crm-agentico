# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR AVISA EN EL CHAT LO QUE CERRO
===============================================================================

QUE SOSTIENEN ESTAS PRUEBAS
---------------------------
El Supervisor cierra casos cuando nadie esta mirando. Hasta el 09/10/2026 eso
quedaba escrito en la propuesta y en la auditoria --correcto para el registro,
inutil para enterarse-- y quien delego la tarea desde el chat se iba sin saber
si habia pasado algo.

Las cuatro cosas que se afirman, y ninguna comprueba que algo EXISTA:

1. Con cierres, aparece un mensaje en LA conversacion donde se delego.
2. Sin cierres, NO aparece ninguno -- un aviso por hora diciendo "nada" seria
   ruido, y ademas entra en el historial que el modelo lee despues.
3. Si no hay conversacion, no se le escribe a cualquiera.
4. Un fallo al avisar NO deshace el cierre ni tumba la corrida.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from common.models import Org, Profile, User
from operaciones import aviso_al_chat, tareas_delegadas as td
from operaciones.chat_modelos import (ConversacionSupervisor,
                                      MensajeSupervisor, RolMensaje)


@pytest.fixture
def org_persona_y_chat(db):
    org = Org.objects.create(name="Org del aviso")
    usuario = User.objects.create(email="jefa@aviso.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    #  'abierta_en' y 'ultimo_mensaje_en' son obligatorias y sin default:
    #  el modelo exige saber cuando empezo la conversacion y cuando se
    #  hablo por ultima vez, que es lo que ordena la bandeja.
    ahora = timezone.now()
    conv = ConversacionSupervisor.objects.create(
        org=org, actor=perfil, abierta_en=ahora, ultimo_mensaje_en=ahora)
    return org, perfil, conv


CIERRES = [
    {"referencia": "94595", "porque": "el equipo esta en linea con señal buena"},
    {"referencia": "94376", "porque": "respondio los 3 paquetes del ping"},
]


# ===========================================================================
#  1. CON CIERRES, EL AVISO LLEGA DONDE SE PIDIO
# ===========================================================================

@pytest.mark.django_db
def test_avisa_en_la_conversacion_donde_se_delego(org_persona_y_chat):
    org, perfil, conv = org_persona_y_chat
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               conversacion_id=conv.id)

    assert aviso_al_chat.avisar_cierres(org, CIERRES) is True

    m = MensajeSupervisor.objects.filter(conversacion=conv).first()
    assert m is not None, "no se escribio el aviso"
    #  LO ESCRIBE EL SUPERVISOR, no una persona: quien lea la conversacion
    #  despues tiene que poder distinguir quien dijo que.
    assert m.rol == RolMensaje.SUPERVISOR
    #  Y DICE QUE CERRO, con el ticket que una persona usa para buscarlo.
    assert "2" in m.contenido
    assert "94595" in m.contenido and "94376" in m.contenido
    #  Y CON QUE LO VERIFICO: cerrar por señal optica y cerrar por ping no son
    #  la misma afirmacion, y el aviso no las puede fundir.
    assert "ping" in m.contenido


# ===========================================================================
#  2. SIN CIERRES NO SE ESCRIBE NADA
# ===========================================================================

@pytest.mark.django_db
def test_una_corrida_sin_cierres_no_deja_mensaje(org_persona_y_chat):
    """
    El ciclo corre cada hora. Si avisara siempre, en un dia dejaria 24
    mensajes de "no cerre nada" -- y no es solo ruido visual: esos mensajes
    entran en el historial que el modelo lee en el turno siguiente y empujan
    afuera lo que importa.
    """
    org, perfil, conv = org_persona_y_chat
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               conversacion_id=conv.id)

    assert aviso_al_chat.avisar_cierres(org, []) is False
    assert MensajeSupervisor.objects.filter(conversacion=conv).count() == 0


# ===========================================================================
#  3. SIN CONVERSACION NO SE LE ESCRIBE A CUALQUIERA
# ===========================================================================

@pytest.mark.django_db
def test_sin_conversacion_guardada_usa_la_de_quien_delego(org_persona_y_chat):
    """
    EL RESPALDO, y por que no es un atajo.

    'conversacion_id' empezo a guardarse el 09/10/2026. Las tareas delegadas
    antes lo tienen vacio, y sin esto no recibirian aviso NUNCA. El arreglo
    obvio --volver a delegarlas-- no funciona: el chat ve que ya estan activas
    y contesta "no hace falta", que es lo correcto de su parte. Medido en vivo
    ese mismo dia.

    Se le escribe a QUIEN DELEGO, que es quien autorizo estos cierres.
    """
    org, perfil, conv = org_persona_y_chat
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)

    assert aviso_al_chat.avisar_cierres(org, CIERRES) is True
    assert MensajeSupervisor.objects.filter(conversacion=conv).count() == 1

    #  Y QUEDA GUARDADA: el respaldo corre una vez por tarea, no cada hora.
    #  Sin esto el aviso saltaria a la conversacion mas reciente en cada
    #  corrida, y el hilo quedaria partido en pedazos.
    from operaciones.tareas_modelos import TareaDelegada
    fila = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert fila.conversacion_id == conv.id


@pytest.mark.django_db
def test_no_se_le_escribe_a_quien_no_delego(db):
    """
    LA LINEA QUE EL RESPALDO NO CRUZA. Buscar "la ultima conversacion" a secas
    le mostraria a otra persona cierres que no autorizo. El filtro es por
    quien delego, no por fecha -- y esta guarda muere si alguien lo cambia.
    """
    org = Org.objects.create(name="Org de dos personas")
    ahora = timezone.now()

    jefa = Profile.objects.create(
        org=org, role="ADMIN", is_active=True,
        user=User.objects.create(email="jefa2@aviso.test", name="Jefa"))
    otro = Profile.objects.create(
        org=org, role="ADMIN", is_active=True,
        user=User.objects.create(email="otro@aviso.test", name="Otro"))

    #  La conversacion MAS RECIENTE es la del otro, a proposito.
    ConversacionSupervisor.objects.create(
        org=org, actor=jefa, abierta_en=ahora,
        ultimo_mensaje_en=ahora - timedelta(hours=2))
    del_otro = ConversacionSupervisor.objects.create(
        org=org, actor=otro, abierta_en=ahora, ultimo_mensaje_en=ahora)

    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=jefa)
    aviso_al_chat.avisar_cierres(org, CIERRES)

    assert MensajeSupervisor.objects.filter(conversacion=del_otro).count() == 0, (
        "se le escribio a quien no delego la tarea: veria cierres que no "
        "autorizo")


@pytest.mark.django_db
def test_sin_ninguna_conversacion_no_se_inventa_una(db):
    """Quien delego nunca abrio el chat: no hay donde avisar, y se calla."""
    org = Org.objects.create(name="Org sin chat")
    perfil = Profile.objects.create(
        org=org, role="ADMIN", is_active=True,
        user=User.objects.create(email="sinchat@aviso.test", name="Sin chat"))
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)

    assert aviso_al_chat.avisar_cierres(org, CIERRES) is False
    assert MensajeSupervisor.objects.count() == 0


@pytest.mark.django_db
def test_si_la_conversacion_se_borro_no_levanta(org_persona_y_chat):
    """La retencion vence las conversaciones al año; la tarea sigue viva."""
    org, perfil, conv = org_persona_y_chat
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               conversacion_id=conv.id)
    conv.delete()

    assert aviso_al_chat.avisar_cierres(org, CIERRES) is False


# ===========================================================================
#  4. UN AVISO QUE FALLA NO DESHACE UN CIERRE
# ===========================================================================

@pytest.mark.django_db
def test_un_fallo_al_avisar_no_levanta(org_persona_y_chat, monkeypatch):
    """
    Los casos YA estan cerrados cuando esto corre. Si avisar levantara, una
    base lenta o un chat roto tumbarian la corrida DESPUES de haber cerrado --
    y el ciclo siguiente encontraria los casos cerrados sin saber por que
    fallo el anterior.
    """
    org, perfil, conv = org_persona_y_chat
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               conversacion_id=conv.id)

    def explota(*a, **k):
        raise RuntimeError("la base se cayo")

    monkeypatch.setattr(MensajeSupervisor.objects, "create", explota)

    #  No levanta, y lo dice devolviendo False.
    assert aviso_al_chat.avisar_cierres(org, CIERRES) is False


# ===========================================================================
#  5. CON MUCHOS CIERRES NO SE ESCRIBE UN MURO
# ===========================================================================

def test_con_muchos_cierres_se_resume():
    """
    Sin base: 'redactar' es pura a proposito. Con el atraso de hoy --noventa
    casos-- una lista completa seria un muro que nadie lee y que ademas entra
    en el historial del modelo. El TOTAL siempre se dice.
    """
    muchos = [{"referencia": str(90000 + i), "porque": "ping completo"}
              for i in range(25)]
    texto = aviso_al_chat.redactar(muchos)

    assert "25" in texto
    #  Se cuentan los renglones de CASO, no todos los que empiezan con
    #  guion: el “…y N más” tambien es uno, y contarlo daba 11 contra un
    #  tope de 10. La primera version de esta prueba fallaba por eso -- el
    #  codigo estaba bien y la cuenta mal.
    de_caso = [l for l in texto.splitlines()
               if l.startswith('- ') and 'más' not in l]
    assert len(de_caso) == aviso_al_chat.TOPE_DETALLADOS
    assert '…y 15 más.' in texto


# ===========================================================================
#  6. LAS CLAVES QUE LEE EL AVISO SON LAS QUE EL CIERRE PRODUCE
# ===========================================================================
#  LA TRAMPA QUE ESTA GUARDA EVITA, y que este repositorio ya pago: las cinco
#  pruebas de arriba le pasan al aviso un diccionario escrito a mano. Si
#  'cerrar_si_corresponde' no pusiera esas claves --o las renombrara-- esas
#  pruebas seguirian en verde y el chat diria "caso sin referencia" en cada
#  renglon, para siempre.
#
#  Paso de verdad mientras se escribia esto: 'referencia' NO viajaba. El
#  cierre devolvia 'caso_id', que es un UUID y no sirve para que una persona
#  busque el ticket.
#
#  Se afirma contra el productor REAL, no contra una copia: se corre un cierre
#  con el llamado al motor reemplazado, y se comprueba que el diccionario que
#  sale trae lo que el aviso lee.

@pytest.mark.django_db
def test_el_cierre_produce_las_claves_que_el_aviso_lee(org_persona_y_chat,
                                                       monkeypatch):
    from operaciones import cierre_de_caso, diagnostico_optico as diag
    from operaciones.models import PropuestaSupervisor as P

    org, perfil, _conv = org_persona_y_chat
    #  LA PUERTA DE LA TAREA DELEGADA. Sin esto 'cerrar_si_corresponde'
    #  devuelve 'cerrado: False' con su motivo, y la prueba no llegaba a
    #  mirar las claves -- se salteaba. Una guarda que se saltea no mide
    #  nada, que es peor que una en rojo: parece verde.
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)

    propuesta = P.objects.create(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO, origen_tipo="case",
        origen_id="11111111-1111-4111-8111-111111111111",
        accion_propuesta="Cerrar el caso en Dexter",
        motivo="el proveedor ya lo cerro", prioridad=30,
        nivel_autonomia_requerido=diag.NIVEL_PARA_CERRAR,
        evidencia=[{"fuente": "diagnostico", "id": "x",
                    "dato": "diagnostico del equipo: respondio los 3 paquetes",
                    "observado_en": timezone.now().isoformat()}])

    #  El motor contesta que cerro, con su referencia. Es el unico punto que
    #  se reemplaza: todo lo demas --la aceptacion, la validacion, el armado
    #  del resultado-- corre de verdad.
    monkeypatch.setattr(
        cierre_de_caso, "cerrar",
        lambda p, **k: {"cerrado": True, "motivo": "",
                        "referencia": "94595", "detalle": ""})
    monkeypatch.setattr(diag, "_puede_cerrar_hoy",
                        lambda *a, **k: {"puede": True, "motivo": ""},
                        raising=False)

    r = diag.cerrar_si_corresponde(
        org, propuesta, autorizacion={"puede": True, "motivo": ""})

    #  SIN 'skip'. Si el cierre no ocurre, esta prueba tiene que ponerse en
    #  ROJO y decir por que: saltearse es como estar en verde, y entonces la
    #  clave que esta guarda vigila podria desaparecer sin que nadie lo note.
    assert r.get("cerrado") is True, (
        f"el cierre no ocurrio y la guarda no pudo mirar las claves: "
        f"{r.get('motivo')}")

    for clave in ("referencia", "porque"):
        assert clave in r, (
            f"'{clave}' no viaja en el resultado del cierre, y el aviso del "
            f"chat la lee: cada renglon quedaria incompleto sin que nada falle")
    assert r["referencia"] == "94595"
