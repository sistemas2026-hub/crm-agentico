# -*- coding: utf-8 -*-
"""
===============================================================================
 QUE EL CICLO CORRA SOLO  --  y que corra para quien lo pidio, no para todos
===============================================================================

POR QUE ESTAS PRUEBAS Y NO OTRAS
--------------------------------
Hay dos formas de que esto falle en silencio, y las dos ya ocurrieron en este
repositorio con otras tareas periodicas. Ninguna da error:

    EL ORDEN DEL CONTEXTO. 'Case' y 'PropuestaSupervisor' tienen RLS forzada.
    Un worker de Celery no pasa por el middleware, asi que si el ciclo corre
    ANTES de 'set_rls_context' ve cero casos -- sin excepcion, sin log, sin
    nada. Es como 'purge_read_notifications' borro cero filas todas las noches
    durante meses. Una prueba que solo mire el resultado no lo distingue de
    "no habia casos".

    EL NOMBRE DE LA TAREA. El reloj agenda por CADENA
    ('operaciones.tasks.ciclo_del_supervisor'). Una letra de diferencia entre
    esa cadena y el nombre real de la tarea no rompe nada al desplegar: el
    reloj despierta cada hora, encola algo que nadie sabe ejecutar, y el
    sintoma es "el Supervisor no cierra nada" -- que manda a revisar el
    diagnostico, no el agendamiento.

De ahi las cinco afirmaciones de abajo. Ninguna comprueba que algo EXISTE:
cada una afirma un efecto, y cada una muere si se invierte la conducta que
dice sostener.
"""
import pytest

from common.models import Org, Profile, User
from operaciones import tareas_delegadas as td
from operaciones import tasks as tareas_periodicas


@pytest.fixture
def dos_empresas(db):
    """Dos empresas: una delega el ciclo, la otra no."""
    con = Org.objects.create(name="Empresa que delego")
    sin = Org.objects.create(name="Empresa que no delego")
    usuario = User.objects.create(email="jefa@ciclo.test", name="Jefa")
    perfil = Profile.objects.create(org=con, user=usuario, role="ADMIN",
                                    is_active=True)
    td.delegar(con, td.CICLO_AUTOMATICO, actor=perfil,
               pedido_textual="revisá solo cada vez que lleguen los tickets")
    return con, sin


# ===========================================================================
#  1. SIN DELEGACION NO SE RECORRE NADA
# ===========================================================================
#  La puerta aplicada a si misma. Si esto se rompe, el Supervisor empieza a
#  mirar la operacion de empresas que nunca lo pidieron.

@pytest.mark.django_db
def test_sin_delegacion_el_ciclo_no_corre_para_nadie(db, monkeypatch):
    Org.objects.create(name="Empresa sin delegar nada")
    corridas = []
    monkeypatch.setattr("operaciones.supervisor.correr_ciclo",
                        lambda org, *a, **k: corridas.append(org.id) or {})

    resultado = tareas_periodicas.ciclo_del_supervisor()

    #  EL EFECTO: no se llamo al ciclo. No "devolvio cero" -- no se llamo.
    assert corridas == []
    assert resultado == {"empresas": 0, "cerrados": 0}


# ===========================================================================
#  2. CORRE SOLO PARA QUIEN LO DELEGO
# ===========================================================================

@pytest.mark.django_db
def test_corre_para_la_empresa_que_delego_y_no_para_la_otra(dos_empresas,
                                                            monkeypatch):
    con, sin = dos_empresas
    corridas = []
    monkeypatch.setattr(
        "operaciones.supervisor.correr_ciclo",
        lambda org, *a, **k: corridas.append(org.id) or
        {"cierre_automatico": {"cerrados": 2}})

    resultado = tareas_periodicas.ciclo_del_supervisor()

    assert corridas == [con.id]
    assert sin.id not in corridas
    assert resultado == {"empresas": 1, "cerrados": 2}


# ===========================================================================
#  3. EL CONTEXTO DE AISLAMIENTO SE FIJA ANTES DEL CICLO
# ===========================================================================
#  LA PRUEBA QUE IMPORTA. Se afirma sobre el ORDEN, porque invertirlo no da
#  error: da cero casos para siempre. Se registran las dos llamadas en una
#  sola lista y se compara la secuencia -- intercambiar las dos lineas de
#  'tasks.py' pone esta prueba en rojo, que es justo lo que se le pide.

@pytest.mark.django_db
def test_fija_el_contexto_antes_de_correr_el_ciclo(dos_empresas, monkeypatch):
    con, _ = dos_empresas
    pasos = []
    monkeypatch.setattr("operaciones.tasks.set_rls_context",
                        lambda org_id: pasos.append(("contexto", str(org_id))))
    monkeypatch.setattr("operaciones.tasks.clear_rls_context",
                        lambda: pasos.append(("limpieza", "")))
    monkeypatch.setattr(
        "operaciones.supervisor.correr_ciclo",
        lambda org, *a, **k: pasos.append(("ciclo", str(org.id))) or {})

    tareas_periodicas.ciclo_del_supervisor()

    assert pasos == [("contexto", str(con.id)),
                     ("ciclo", str(con.id)),
                     ("limpieza", "")]


# ===========================================================================
#  4. UNA EMPRESA QUE FALLA NO DEJA SIN REVISAR A LAS DEMAS
# ===========================================================================
#  Y el contexto se limpia igual. Si la limpieza quedara dentro del 'try', un
#  fallo dejaria la ultima empresa puesta en la conexion del worker, y la
#  tarea siguiente --cualquiera de las otras 12-- arrancaria creyendo que es
#  de esa empresa.

@pytest.mark.django_db
def test_un_fallo_no_detiene_al_resto_y_el_contexto_se_suelta(db, monkeypatch):
    primera = Org.objects.create(name="AAA la que falla")
    segunda = Org.objects.create(name="BBB la que anda")
    usuario = User.objects.create(email="jefa2@ciclo.test", name="Jefa")
    for org in (primera, segunda):
        perfil = Profile.objects.create(
            org=org, user=usuario, role="ADMIN", is_active=True)
        td.delegar(org, td.CICLO_AUTOMATICO, actor=perfil)

    limpiezas = []
    monkeypatch.setattr("operaciones.tasks.clear_rls_context",
                        lambda: limpiezas.append(1))

    vistas = []

    def ciclo(org, *a, **k):
        vistas.append(org.id)
        if org.id == primera.id:
            raise RuntimeError("SmartOLT no contesto")
        return {"cierre_automatico": {"cerrados": 1}}

    monkeypatch.setattr("operaciones.supervisor.correr_ciclo", ciclo)

    resultado = tareas_periodicas.ciclo_del_supervisor()

    #  LAS DOS se intentaron, y la segunda se conto.
    assert set(vistas) == {primera.id, segunda.id}
    assert resultado == {"empresas": 1, "cerrados": 1}
    #  Y se solto el contexto pese al fallo.
    assert limpiezas == [1]


# ===========================================================================
#  5. EL RELOJ AGENDA EL NOMBRE REAL DE LA TAREA
# ===========================================================================
#  "Codigo construido no es codigo que corre". El reloj agenda una CADENA, y
#  una cadena que no corresponde a ninguna tarea registrada no falla al
#  desplegar: falla cada hora, en silencio. Se compara contra el nombre que la
#  tarea se da a si misma, asi que un typo en cualquiera de los dos lados
#  rompe esta prueba.

def test_el_reloj_agenda_la_tarea_con_su_nombre_real():
    from crm.celery import app

    entrada = app.conf.beat_schedule.get("ciclo-del-supervisor")
    assert entrada is not None, (
        "el ciclo no esta en beat_schedule: el reloj no lo va a despertar")
    assert entrada["task"] == tareas_periodicas.ciclo_del_supervisor.name


def test_el_reloj_lo_despierta_cada_hora():
    """Cada hora, no cada cinco minutos ni una vez al dia."""
    from crm.celery import app

    horario = app.conf.beat_schedule["ciclo-del-supervisor"]["schedule"]
    #  'crontab(minute=7)' = todos los dias, todas las horas, minuto 7.
    assert horario.minute == {7}
    assert len(horario.hour) == 24, (
        "el ciclo tiene que correr todas las horas: un caso que aparece a la "
        "noche no puede esperar al dia siguiente")
