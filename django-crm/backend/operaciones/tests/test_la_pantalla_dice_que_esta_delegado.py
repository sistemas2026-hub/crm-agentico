# -*- coding: utf-8 -*-
"""
===============================================================================
 QUE ESTA DELEGADO SE VE EN LA PANTALLA, NO SOLO HABLANDOLE AL CHAT
===============================================================================

POR QUE EXISTE ESTA PRUEBA  --  21/10/2026
------------------------------------------
'tareas_delegadas.py' dice en su propio encabezado que hacen falta DOS cosas y
que son distintas:

    LA TAREA     QUE se delego.
    EL NIVEL     CUANTO puede hacer solo.

    "Delegar una tarea con el nivel en 1 no cierra nada, y subir el nivel sin
     delegar la tarea tampoco."

El NIVEL se ve en la pantalla desde el 08/10/2026. La DELEGACION no se veia en
ninguna: se escribia y se leia unicamente hablandole al chat, y 'delegadas()' y
'algo_la_va_a_correr()' no tenian ningun lector en la interfaz. Para saber si
el Supervisor estaba realmente encendido habia que preguntarselo o abrir una
consola -- que es exactamente la falla que 'autonomia.cambiar' tuvo durante
semanas y que su propia prueba documenta: *no falla, no da error, simplemente
nadie lo llama nunca*.

LO QUE SE AFIRMA, Y POR QUE CADA UNA
------------------------------------
1. Que la ruta devuelve el CATALOGO ENTERO, no solo lo encendido. Media
   utilidad de la pantalla esta en ver lo que NO esta delegado.
2. Que una tarea delegada de verdad --por el servicio, no fabricando la fila--
   aparece encendida, con la frase con la que se pidio.
3. Que 'nivel_alcanza' mira el nivel EFECTIVO y no el configurado. Esta es la
   que mata la mutacion que importa: con el freno de mano puesto, una pantalla
   que leyera el configurado diria que la tarea esta habilitada justo cuando no
   puede actuar.
4. Que 'la_despierta_algo' dice NO mientras no este delegado el ciclo horario.
   Es la precondicion que estuvo en silencio hasta el 15/10 y dejo una tarea
   delegada, con nivel 3, sin que nada la corriera en cinco vueltas.
5. Que un 'exige_nivel' de 4 no alcanza NUNCA, aunque el nivel diera.
6. Que en la respuesta no viaja ni el nombre ni el correo de quien delego.

NO SE AFIRMA sobre los textos del catalogo ('que_hace', 'que_no_hace'): son
redaccion y cambian. Se afirma que viajan no vacios, que es lo que la pantalla
necesita.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from common.models import Org, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import autonomia, tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P

URL = "/api/operaciones/supervisor/autonomia/"


@pytest.fixture
def jefa(db):
    org = Org.objects.create(name="Org que delega")
    usuario = User.objects.create_user(email="jefa@delega.test",
                                       password="x12345678", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    return org, usuario, perfil


def _cli(org, usuario, perfil):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        "Bearer " + str(OrgAwareRefreshToken.for_user_and_org(
            usuario, org, perfil).access_token)))
    return c


def _sin_interruptor(monkeypatch, *, permite):
    """
    El interruptor se le pregunta al MOTOR por HTTP y aca no hay motor.

    Se reemplaza la lectura, no el resultado: lo que esta prueba mide es que la
    vista use el nivel efectivo, y el efectivo lo calcula 'nivel_efectivo' a
    partir de esto.
    """
    monkeypatch.setattr(
        autonomia, "_interruptor_de",
        lambda org: (permite, "" if permite else "freno puesto a mano"))


@pytest.mark.django_db
def test_la_ruta_devuelve_el_catalogo_entero_y_no_solo_lo_encendido(
        jefa, monkeypatch):
    org, usuario, perfil = jefa
    _sin_interruptor(monkeypatch, permite=True)

    r = _cli(org, usuario, perfil).get(URL)
    assert r.status_code == 200, r.content

    lista = r.json()["delegaciones"]
    #  Todas las del catalogo, ninguna de mas.
    assert {d["clave"] for d in lista} == set(td.CATALOGO)
    #  Y nada delegado todavia: esta empresa es nueva. Que la lista NO venga
    #  vacia con cero delegaciones es el punto -- se ve lo que falta encender.
    assert lista, "el catalogo llego vacio"
    assert all(d["delegada"] is False for d in lista)
    for d in lista:
        assert d["nombre"] and d["que_hace"], d["clave"]


@pytest.mark.django_db
def test_lo_que_se_delego_de_verdad_aparece_encendido(jefa, monkeypatch):
    org, usuario, perfil = jefa
    _sin_interruptor(monkeypatch, permite=True)

    #  Por el SERVICIO, no fabricando la fila: si 'delegar' cambiara de forma,
    #  esta prueba tiene que enterarse.
    td.delegar(org, td.PASAR_A_DESPACHO, actor=perfil,
               pedido_textual="pasa solo los que las reglas dejen pasar")

    lista = _cli(org, usuario, perfil).get(URL).json()["delegaciones"]
    por_clave = {d["clave"]: d for d in lista}

    encendida = por_clave[td.PASAR_A_DESPACHO]
    assert encendida["delegada"] is True
    assert encendida["delegada_en"], "sin fecha no se sabe desde cuando"
    assert encendida["con_estas_palabras"] == (
        "pasa solo los que las reglas dejen pasar")

    #  Y delegar UNA no enciende las demas. Es la regla que el catalogo repite
    #  en dos comentarios: "habilitar una cosa no puede habilitar la otra de
    #  rebote".
    otras = [d for c, d in por_clave.items() if c != td.PASAR_A_DESPACHO]
    assert all(d["delegada"] is False for d in otras)


@pytest.mark.django_db
def test_con_el_freno_puesto_la_tarea_NO_alcanza_el_nivel(jefa, monkeypatch):
    """
    LA QUE MATA LA MUTACION.

    El nivel configurado queda en 3 --alcanza de sobra para las tareas de
    accion-- y el interruptor se baja. 'nivel_efectivo' recorta a RECOMENDAR,
    asi que ninguna tarea de accion alcanza. Una vista que leyera
    'estado["configurado"]' en vez de 'estado["efectivo"]' pintaria las dos
    tareas como habilitadas con el freno de mano puesto: el peor resultado
    posible, porque lo que se mira en ese momento es si algo quedo activo.
    """
    org, usuario, perfil = jefa

    _sin_interruptor(monkeypatch, permite=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto del paso a despacho",
                      criterios="5 casos medidos a mano")

    #  Con el interruptor ARRIBA, una tarea de nivel 3 alcanza.
    arriba = {d["clave"]: d for d in
              _cli(org, usuario, perfil).get(URL).json()["delegaciones"]}
    de_accion = [c for c, f in td.CATALOGO.items()
                 if (f.get("exige_nivel") or 0) >= P.NIVEL_EJECUTAR_REVERSIBLE]
    assert de_accion, "el catalogo no tiene ninguna tarea de accion"
    assert all(arriba[c]["nivel_alcanza"] is True for c in de_accion)

    #  Se baja el freno. El configurado NO cambia --son dos controles-- y aun
    #  asi ninguna tarea de accion puede.
    _sin_interruptor(monkeypatch, permite=False)
    abajo_json = _cli(org, usuario, perfil).get(URL).json()
    assert abajo_json["configurado"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert abajo_json["recortado"] is True

    abajo = {d["clave"]: d for d in abajo_json["delegaciones"]}
    assert all(abajo[c]["nivel_alcanza"] is False for c in de_accion), (
        "con el freno puesto la pantalla dice que la tarea alcanza el nivel")


@pytest.mark.django_db
def test_sin_el_ciclo_horario_nada_la_despierta(jefa, monkeypatch):
    """
    La precondicion que estuvo en silencio hasta el 15/10/2026.

    Ese dia 'pasar_a_despacho_segun_las_reglas' estaba delegada y activa, el
    nivel en 3, y el ciclo horario devolvio 'empresas: 0' en las cinco corridas
    de 16:07 a 21:11 UTC. Nada en la pantalla ni en el chat decia por que.
    """
    org, usuario, perfil = jefa
    _sin_interruptor(monkeypatch, permite=True)

    td.delegar(org, td.PASAR_A_DESPACHO, actor=perfil)

    antes = {d["clave"]: d for d in
             _cli(org, usuario, perfil).get(URL).json()["delegaciones"]}
    sin_ciclo = antes[td.PASAR_A_DESPACHO]["la_despierta_algo"]
    assert sin_ciclo["si"] is False
    #  Y lo dice con texto, no con un falso suelto: la pantalla tiene que poder
    #  explicar que falta.
    assert sin_ciclo["por_que"], "dijo que no y no dijo por que"

    #  Delegado el ciclo, la misma tarea ya corre sola.
    td.delegar(org, td.CICLO_AUTOMATICO, actor=perfil)
    despues = {d["clave"]: d for d in
               _cli(org, usuario, perfil).get(URL).json()["delegaciones"]}
    assert despues[td.PASAR_A_DESPACHO]["la_despierta_algo"]["si"] is True


@pytest.mark.django_db
def test_un_nivel_4_no_alcanza_nunca(jefa, monkeypatch):
    """
    El nivel 4 es "siempre la aprueba una persona", y no se habilita subiendo
    el nivel. 'autonomia.puede' ya lo impone; la lista repite la regla porque
    llamar a 'puede' costaria una consulta al motor por tarea.

    EL NIVEL SE FUERZA, Y HAY QUE DECIR POR QUE  --  21/10/2026
    -----------------------------------------------------------
    La primera version de esta prueba subia el nivel con 'autonomia.cambiar' al
    tope de la etapa y daba por probada la regla. NO LA PROBABA: el tope de la
    etapa es 3 ('NIVEL_MAXIMO_ETAPA = NIVEL_EJECUTAR_REVERSIBLE'), asi que
    'efectivo >= 4' ya era falso por su cuenta y la mitad de la condicion que
    mira el nivel 4 nunca se ejecutaba.

    Se midio: con la regla BORRADA de la vista --'nivel_alcanza': (True and
    efectivo >= exige)-- las seis pruebas seguian en verde. Una prueba que
    sobrevive a que le borren lo que afirma proteger no protege nada; es
    exactamente lo que §6 llama *una prueba que dice que algo existe no prueba
    que funcione*.

    Por eso el nivel se fuerza a 4 reemplazando 'nivel_configurado': hoy
    ninguna empresa puede llegar ahi, y la regla es la guarda del dia que el
    tope de la etapa suba. Sin forzarlo no hay forma de ejercitarla.
    """
    org, usuario, perfil = jefa
    _sin_interruptor(monkeypatch, permite=True)
    #  'nivel_efectivo' lee esto y devuelve el configurado tal cual cuando el
    #  interruptor permite: asi el efectivo llega a 4 sin tocar la vista.
    monkeypatch.setattr(autonomia, "nivel_configurado",
                        lambda org: P.NIVEL_CRITICO)

    clave = next(iter(td.CATALOGO))
    monkeypatch.setitem(td.CATALOGO[clave], "exige_nivel", P.NIVEL_CRITICO)

    cuerpo = _cli(org, usuario, perfil).get(URL).json()
    #  El nivel efectivo SI llego a 4 -- si no, la prueba volveria a pasar por
    #  el motivo equivocado y nadie se enteraria.
    assert cuerpo["efectivo"] == P.NIVEL_CRITICO
    lista = {d["clave"]: d for d in cuerpo["delegaciones"]}
    assert lista[clave]["exige_nivel"] == P.NIVEL_CRITICO
    assert lista[clave]["nivel_alcanza"] is False


@pytest.mark.django_db
def test_no_viaja_quien_delego(jefa, monkeypatch):
    """
    El nombre y el correo de quien delego no salen en la respuesta.

    'delegadas()' devuelve el ID a proposito --"y nunca el nombre ni el correo:
    esto puede terminar en un log"--. La pantalla no necesita ninguno de los
    tres para decir si la tarea esta encendida, asi que no viaja ninguno.
    """
    org, usuario, perfil = jefa
    _sin_interruptor(monkeypatch, permite=True)

    td.delegar(org, td.PASAR_A_DESPACHO, actor=perfil,
               pedido_textual="encendelo")

    import json as _json
    crudo = _json.dumps(
        _cli(org, usuario, perfil).get(URL).json()["delegaciones"])
    assert "Jefa" not in crudo
    assert "jefa@delega.test" not in crudo
    assert "@" not in crudo
