# -*- coding: utf-8 -*-
"""
===============================================================================
 EL ALCANCE DEL SUPERVISOR SE OPERA DESDE LA INTERFAZ, NO DESDE UNA CONSOLA
===============================================================================

POR QUE EXISTE ESTA PRUEBA
--------------------------
Porque hasta el 08/10/2026 'autonomia.cambiar' no tenia NINGUN llamador. La
funcion estaba escrita, probada y sin forma de invocarse: el nivel solo se
podia tocar abriendo una terminal en el servidor. Se descubrio al ir a encender
el cierre automatico de casos, cuando hubo que decirle a una persona "anda a la
pantalla de autonomia" y esa pantalla no existia.

Es la variante de "codigo construido no es codigo que corre" que mas cuesta
ver: no falla, no da error, simplemente nadie lo llama nunca.

LAS TRES COSAS QUE SE AFIRMAN
-----------------------------
1. Que la ruta EXISTE y contesta. Medido pidiendola, no leyendo 'urls.py'.
2. Que subir el alcance sigue exigiendo motivo y criterios, aunque ahora se
   pida desde un navegador. La puerta no se ablanda por tener boton.
3. Que PARAR no exige criterios. La asimetria es deliberada: quien ve humo no
   deberia tener que redactar un informe antes de apagar el fuego.
"""
import pytest
from django.urls import reverse

from common.models import Org, Profile, User
from operaciones.models import PropuestaSupervisor as P


@pytest.fixture
def jefa(db):
    org = Org.objects.create(name="Org de la autonomia")
    usuario = User.objects.create(email="jefa@autonomia.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    return org, usuario, perfil


@pytest.mark.django_db
def test_la_ruta_existe_y_tiene_nombre():
    #  Se resuelve por NOMBRE: si alguien borra la ruta, esto falla aqui y no
    #  con un 404 silencioso dentro de otra prueba.
    assert reverse("operaciones:supervisor-autonomia")


@pytest.mark.django_db
def test_subir_el_nivel_sigue_exigiendo_motivo_y_criterios(jefa):
    from operaciones import autonomia

    org, _usuario, perfil = jefa

    #  Sin criterios: se niega, con el mensaje del servicio.
    with pytest.raises(autonomia.ErrorAutonomia):
        autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                          motivo="porque si", criterios="")
    #  Sin motivo: igual.
    with pytest.raises(autonomia.ErrorAutonomia):
        autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                          motivo="", criterios="5 casos medidos")
    #  Sin persona: igual, y este es el que importa -- el Supervisor no puede
    #  ampliarse su propio alcance.
    with pytest.raises(autonomia.ErrorAutonomia):
        autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=None,
                          motivo="x", criterios="y")

    #  Con los tres: entra.
    fila = autonomia.cambiar(
        org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
        motivo="cierre automatico de casos ya cerrados en el proveedor",
        criterios="5 servicios medidos: 3 cierre seguro, 1 revisar, 1 sin dato")
    assert fila.nivel == P.NIVEL_EJECUTAR_REVERSIBLE
    assert autonomia.nivel_configurado(org) == P.NIVEL_EJECUTAR_REVERSIBLE


@pytest.mark.django_db
def test_parar_NO_exige_criterios_pero_SI_motivo(jefa, monkeypatch):
    """
    La asimetria, que es una decision y no un descuido.

    Ampliar el alcance tiene que demostrar que se midio algo. Parar no tiene
    que demostrar nada: quien ve algo raro deberia poder frenar en el acto.
    Pero el motivo si se exige, porque un freno sin dueño ni explicacion no se
    puede discutir despues.
    """
    from operaciones import autonomia, fuentes_adaptadores

    org, _usuario, perfil = jefa
    movidas = []

    def falso(*, detener, actor, motivo):
        movidas.append({"detener": detener, "actor": actor, "motivo": motivo})
        return {"estado": "detenido" if detener else "activo"}

    monkeypatch.setattr(fuentes_adaptadores,
                        "mover_interruptor_de_autonomia", falso)

    #  Sin motivo: se niega.
    with pytest.raises(autonomia.ErrorAutonomia):
        autonomia.mover_interruptor(org, detener=True, actor=perfil, motivo="")
    assert movidas == []

    #  Con motivo y SIN criterios: sale.
    r = autonomia.mover_interruptor(
        org, detener=True, actor=perfil, motivo="algo raro en la bandeja")
    assert r["estado"] == "detenido"
    assert len(movidas) == 1
    #  Y el actor viaja como ID, nunca como nombre ni correo: esto termina en
    #  el log del motor.
    assert movidas[0]["actor"] == str(perfil.id)
    assert "Jefa" not in movidas[0]["actor"]
    assert "@" not in movidas[0]["actor"]


@pytest.mark.django_db
def test_mover_el_interruptor_NO_cambia_el_nivel(jefa, monkeypatch):
    #  Son dos controles distintos. Si reactivar subiera el nivel, devolveria
    #  en silencio un alcance que alguien habia decidido recortar.
    from operaciones import autonomia, fuentes_adaptadores

    org, _usuario, perfil = jefa
    monkeypatch.setattr(
        fuentes_adaptadores, "mover_interruptor_de_autonomia",
        lambda **kw: {"estado": "detenido" if kw["detener"] else "activo"})

    autonomia.cambiar(org, P.NIVEL_COORDINAR, actor=perfil,
                      motivo="piloto", criterios="medido")
    antes = autonomia.nivel_configurado(org)

    autonomia.mover_interruptor(org, detener=True, actor=perfil,
                                motivo="freno de prueba")
    assert autonomia.nivel_configurado(org) == antes

    autonomia.mover_interruptor(org, detener=False, actor=perfil,
                                motivo="se reanuda")
    assert autonomia.nivel_configurado(org) == antes


@pytest.mark.django_db
def test_si_el_motor_no_responde_el_freno_lo_dice_y_no_miente(jefa, monkeypatch):
    #  Lo que NO puede pasar: que la pantalla diga "detenido" cuando el
    #  interruptor no se movio. Un freno que miente es peor que no tenerlo.
    from operaciones import autonomia, fuentes_adaptadores

    org, _usuario, perfil = jefa

    def explota(**kw):
        raise fuentes_adaptadores.MotorNoDisponible("no se pudo preguntar")

    monkeypatch.setattr(fuentes_adaptadores,
                        "mover_interruptor_de_autonomia", explota)

    with pytest.raises(autonomia.ErrorAutonomia):
        autonomia.mover_interruptor(org, detener=True, actor=perfil,
                                    motivo="freno")


@pytest.mark.django_db
def test_el_interruptor_ilegible_impide_ejecutar_pero_no_observar(
        jefa, monkeypatch):
    """
    Lo que se midio en produccion el 08/10/2026, fijado como prueba.

    Con el interruptor ilegible el nivel efectivo se recorta por mas que el
    configurado diga 3: deja de poder EJECUTAR, y sigue pudiendo observar y
    recomendar. Es correcto -- no poder leer el control es lo mismo que no
    tenerlo-- y es la razon por la que la lectura paso a ir por HTTP: leyendo la
    tabla directo fallaba SIEMPRE, y entonces ningun nivel servia de nada.

    El recorte NO lleva a 0, y la primera version de esta prueba lo exigia mal.
    Bajar a 0 seria dejar de mirar porque no se puede leer un freno, que es
    otra cosa y seria peor.
    """
    from operaciones import autonomia, fuentes_adaptadores

    org, _usuario, perfil = jefa
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")

    def explota():
        raise fuentes_adaptadores.MotorNoDisponible("no se pudo preguntar")

    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia", explota)

    estado = autonomia.nivel_efectivo(org)
    assert estado["configurado"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert estado["interruptor_permite"] is False
    assert "no se pudo leer" in estado["motivo"]

    #  SE AFIRMA SOBRE LO QUE IMPIDE, no sobre el numero. El recorte deja el
    #  efectivo en 1 y no en 0, y eso es correcto: el interruptor frena
    #  EJECUTAR, no observar ni recomendar. Una prueba que exigiera 0 estaria
    #  pidiendo que el Supervisor deje de mirar porque no se puede leer un
    #  freno, que es otra cosa y seria peor.
    assert estado["efectivo"] < P.NIVEL_EJECUTAR_REVERSIBLE
    assert autonomia.puede(org, P.NIVEL_EJECUTAR_REVERSIBLE)["puede"] is False
    #  Y lo que NO se recorta: seguir observando y recomendando.
    assert autonomia.puede(org, P.NIVEL_RECOMENDAR)["puede"] is True
