# -*- coding: utf-8 -*-
"""
===============================================================================
 UNA TAREA DELEGADA QUE NADIE VA A CORRER, Y EL CHAT LO DICE
===============================================================================

EL DEFECTO QUE ESTAS PRUEBAS MATAN  --  15/10/2026
--------------------------------------------------
Una tarea de accion necesita DOS cosas para andar sola:

    EL NIVEL   cuanto puede hacer el Supervisor por su cuenta.
    EL MIRAR   que algo lo despierte. Lo da 'CICLO_AUTOMATICO'; sin esa fila
               el ciclo horario ni recorre a la empresa.

'delegar_tarea' avisaba de la primera y callaba la segunda. Con el nivel en 3
contestaba 'ya_puede_actuar: true' y 'que_falta: ""' -- o sea "quedo andando"--
mientras el ciclo horario devolvia 'empresas: 0' en cada corrida.

MEDIDO, no supuesto. En el entorno local ese dia:
'pasar_a_despacho_segun_las_reglas' delegada y activa, nivel 3, y las cinco
corridas del ciclo entre 16:07 y 21:11 UTC registrando "ningun ciclo delegado,
no se recorre nada" con 'empresas: 0'. El panel del Supervisor clavado en su
ultimo hecho --11:10 a. m. de Bogota-- sin que nada dijera por que.

LO QUE ESTAS PRUEBAS NO HACEN: ensanchar la puerta del ciclo. Admitir ahi a
quien delego solo la accion seria "habilitar una cosa de rebote", que es lo que
el catalogo prohibe en su propio comentario. El ultimo test fija esa decision
al reves: comprueba que la puerta sigue admitiendo SOLO el ciclo.
"""
import pytest

from common.models import Org, Profile, User
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P


@pytest.fixture
def org_y_persona(db):
    org = Org.objects.create(name="Org del aviso")
    usuario = User.objects.create(email="jefa@aviso.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    return org, perfil


def _con_nivel_3(org, perfil, monkeypatch):
    from operaciones import autonomia, fuentes_adaptadores
    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia",
                        lambda: {"permitido": True, "estado": "activo",
                                 "motivo": ""})
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")


def _delegar(org, perfil, clave):
    from operaciones import chat_herramientas
    return chat_herramientas.ejecutar(
        org, "delegar_tarea", {"clave": clave, "pedido": "hacelo vos"},
        actor=perfil, conversacion_id=None)


# ===========================================================================
#  1. EL DEFECTO: permiso sin nadie que la invoque
# ===========================================================================

@pytest.mark.django_db
def test_con_el_nivel_en_3_y_sin_el_ciclo_el_chat_DICE_que_nada_la_corre(
        org_y_persona, monkeypatch):
    org, perfil = org_y_persona
    _con_nivel_3(org, perfil, monkeypatch)

    r = _delegar(org, perfil, td.PASAR_A_DESPACHO)

    #  El permiso SI esta: no se esta midiendo el nivel.
    assert r["ya_puede_actuar"] is True
    #  Y aun asi nada la va a correr -- que es exactamente lo que se callaba.
    assert r["algo_la_va_a_correr"] is False
    assert r["que_falta"], (
        "con permiso y sin nadie que la invoque, 'que_falta' vacio le dice a "
        "la persona que quedo andando")
    assert "Revisar solo" in r["que_falta"], (
        "tiene que NOMBRAR la tarea que falta, no decir 'algo falta'")


@pytest.mark.django_db
def test_el_cierre_de_desincronizados_tiene_el_mismo_aviso(
        org_y_persona, monkeypatch):
    """No es un parche para una tarea: toda tarea de accion lo necesita."""
    org, perfil = org_y_persona
    _con_nivel_3(org, perfil, monkeypatch)

    r = _delegar(org, perfil, td.CERRAR_DESINCRONIZADOS)

    assert r["ya_puede_actuar"] is True
    assert r["algo_la_va_a_correr"] is False
    assert "Revisar solo" in r["que_falta"]


# ===========================================================================
#  2. CON EL CICLO DELEGADO NO FALTA NADA
# ===========================================================================

@pytest.mark.django_db
def test_con_el_ciclo_ya_delegado_no_falta_nada(org_y_persona, monkeypatch):
    org, perfil = org_y_persona
    _con_nivel_3(org, perfil, monkeypatch)
    td.delegar(org, td.CICLO_AUTOMATICO, actor=perfil, pedido_textual="mira")

    r = _delegar(org, perfil, td.PASAR_A_DESPACHO)

    assert r["algo_la_va_a_correr"] is True
    assert r["que_falta"] == "", (
        "con el nivel y el ciclo puestos no falta nada, y decir que falta "
        "algo manda a una persona a buscar un problema que no existe")


@pytest.mark.django_db
def test_al_delegar_el_ciclo_no_falta_nada(org_y_persona):
    """
    Delegar el ciclo no deja nada pendiente: lo corre celery-beat cada hora.

    OJO CON LO QUE ESTO **NO** MIDE  --  medido el 15/10/2026. No distingue
    si 'CICLO_AUTOMATICO' se exige a si mismo: la respuesta se calcula DESPUES
    de delegar, asi que su propia fila ya esta y 'esta_delegada' contesta True
    por cualquiera de los dos caminos. Con la bandera invertida a mano, estas
    dos afirmaciones siguieron en verde. Lo que si lo mide es el test de abajo,
    que pregunta ANTES de delegar -- el unico punto donde la diferencia existe.
    """
    org, perfil = org_y_persona

    r = _delegar(org, perfil, td.CICLO_AUTOMATICO)

    assert r["algo_la_va_a_correr"] is True
    assert r["que_falta"] == ""


@pytest.mark.django_db
def test_el_ciclo_no_se_exige_a_si_mismo(org_y_persona):
    """
    Preguntar por el ciclo SIN que este delegado: la respuesta tiene que ser
    que si lo va a correr algo, porque lo corre celery-beat.

    Si se exigiera a si mismo, la unica forma de que el chat dijera "esto va
    a correr" seria que ya estuviera delegado -- y entonces, al ofrecerlo a
    una empresa que todavia no lo tiene, el chat contestaria que ni delegandolo
    serviria. Es la unica prueba del banco que ve esa bandera.
    """
    org, _ = org_y_persona

    assert td.esta_delegada(org, td.CICLO_AUTOMATICO) is False
    r = td.algo_la_va_a_correr(org, td.CICLO_AUTOMATICO)

    assert r["si"] is True, (
        "el ciclo lo despierta celery-beat, no otra tarea delegada")
    assert r["por_que"] == ""


# ===========================================================================
#  3. CUANDO FALTAN LOS DOS, SE DICEN LOS DOS
# ===========================================================================

@pytest.mark.django_db
def test_cuando_faltan_los_DOS_se_dicen_los_DOS(org_y_persona):
    """
    El caso de una empresa que recien empieza: nivel de entrada y nada
    delegado.

    Con un 'if/elif' el segundo faltante no se veria NUNCA en este caso, que
    es justo el mas comun. Por eso se arman como lista.
    """
    org, perfil = org_y_persona   # sin tocar el nivel: queda en el de entrada

    r = _delegar(org, perfil, td.PASAR_A_DESPACHO)

    assert r["ya_puede_actuar"] is False
    assert r["algo_la_va_a_correr"] is False
    assert "nivel de autonomía" in r["que_falta"], "falta el del nivel"
    assert "Revisar solo" in r["que_falta"], "falta el de quién la corre"


# ===========================================================================
#  4. FALLA DICIENDO QUE NO
# ===========================================================================

@pytest.mark.django_db
def test_una_clave_fuera_del_catalogo_contesta_que_NO_la_corre(org_y_persona):
    org, _ = org_y_persona
    r = td.algo_la_va_a_correr(org, "tarea_que_no_existe")
    assert r["si"] is False, (
        "fail-closed: un falso 'ya quedó andando' es el resultado que esto "
        "existe para evitar")


@pytest.mark.django_db
def test_toda_tarea_del_catalogo_declara_si_necesita_que_mire(org_y_persona):
    """
    LA QUE ATRAPA A LA TAREA QUE SE AGREGUE MANANA.

    La clave ausente cae del lado peligroso: 'necesita_que_mire' sin declarar
    se lee como "se corre a si misma", y el aviso no saldria. Que el catalogo
    la EXIJA convierte ese olvido en un test rojo.
    """
    for clave, ficha in td.CATALOGO.items():
        assert "necesita_que_mire" in ficha, (
            f"'{clave}' no declara si necesita que el Supervisor mire")
        assert isinstance(ficha["necesita_que_mire"], bool)


# ===========================================================================
#  5. LA DECISION QUE NO SE TOMO: ensanchar la puerta del ciclo
# ===========================================================================

@pytest.mark.django_db
def test_la_puerta_del_ciclo_sigue_admitiendo_SOLO_el_ciclo(
        org_y_persona, monkeypatch):
    """
    Con la accion delegada y el ciclo NO, el ciclo horario no recorre a la
    empresa -- y esta bien que no lo haga.

    Es el sintoma medido ('empresas: 0') convertido en guarda. Si alguien
    "arregla" el aviso ensanchando esta puerta, delegar que pase casos a
    Despacho habilitaria de rebote que el Supervisor se despierte cada hora,
    que es otra autorizacion y se pide aparte.
    """
    from operaciones import tasks

    org, perfil = org_y_persona
    _con_nivel_3(org, perfil, monkeypatch)
    td.delegar(org, td.PASAR_A_DESPACHO, actor=perfil, pedido_textual="pasa")

    r = tasks.ciclo_del_supervisor()

    assert r["empresas"] == 0, (
        "delegar la acción no autoriza al Supervisor a despertarse solo")

    #  Y con el ciclo delegado SI la recorre: la puerta no esta rota, esta
    #  pidiendo la fila que corresponde.
    td.delegar(org, td.CICLO_AUTOMATICO, actor=perfil, pedido_textual="mira")
    assert tasks.ciclo_del_supervisor()["empresas"] == 1
