# -*- coding: utf-8 -*-
"""
================================================================================
 EL BOTON NO ESPERA AL CICLO: LO ENCOLA
================================================================================

DE DONDE SALE
-------------
Medido en produccion el 13/10/2026. El ciclo termino a las 23:58:38 y dejo sus
cuatro lecturas registradas; a las 00:02 --tres minutos y medio despues-- el
boton seguia diciendo "Analizando operacion...". La conexion se habia cortado
mucho antes.

O sea: el trabajo salia bien y la pantalla giraba para siempre. Es el peor de
los dos mundos, porque invita a apretar de nuevo algo que YA esta corriendo.

POR QUE APARECIO AHORA Y NO ANTES
----------------------------------
Esperar el ciclo dentro de la peticion funcionaba mientras el ciclo casi no
hacia nada. Ese mismo dia paso a LEER tickets --cada lectura es una consulta al
modelo mas las herramientas que use-- y la corrida se fue a varios minutos.
La mejora del ciclo rompio la pantalla: no habia ningun cambio en la pantalla
ese dia.

LO QUE AFIRMA
-------------
Que la vista contesta sin correr el ciclo, y que si la cola no esta lo DICE en
vez de callarlo. Lo segundo importa tanto como lo primero: un encolado que
falla en silencio deja a la persona esperando resultados de un ciclo que nunca
arranco -- el mismo sintoma que esto vino a arreglar, con otra causa.
================================================================================
"""

import pytest

pytestmark = pytest.mark.django_db


def test_la_vista_NO_corre_el_ciclo_en_la_peticion(admin_client, monkeypatch):
    """
    EL EFECTO, no el mecanismo: se afirma que 'correr_ciclo' no se ejecuta.

    Una prueba que mirara "se llamo a .delay()" pasaria igual si alguien dejara
    las dos cosas -- encolar Y correr-- que es justo la regresion mas probable.
    """
    from operaciones import supervisor, tasks

    corrio = {"si": False}

    def _no_deberia(*a, **k):
        corrio["si"] = True
        raise AssertionError("el ciclo se corrio dentro de la petición")

    encolados = []
    monkeypatch.setattr(supervisor, "correr_ciclo", _no_deberia)
    monkeypatch.setattr(tasks.ciclo_a_pedido, "delay",
                        lambda org_id: encolados.append(org_id) or _Tarea())

    r = admin_client.post("/api/operaciones/supervisor/ciclo/")

    assert not corrio["si"]
    assert r.status_code == 202, (
        f"se esperaba 202 (aceptado, todavía no hecho) y vino {r.status_code}")
    assert r.json().get("encolado") is True
    assert len(encolados) == 1, "no se encolo exactamente una corrida"


class _Tarea:
    id = "una-tarea"


def test_el_ciclo_encolado_corre_DESATENDIDO(monkeypatch):
    """
    EL PRESUPUESTO LARGO, porque ya nadie espera esta corrida.

    El tope corto --tres diagnosticos contra quince-- existe por una sola
    razon: que el boton conteste rapido. Desde que la corrida se encola, el
    boton contesta en el acto con el acuse y la persona se va a hacer otra
    cosa.

    MEDIDO el 14/10/2026: diez propuestas de desincronizados llevaban un dia
    sin diagnosticar --y por lo tanto sin poder cerrarse-- mientras cada vuelta
    a pedido miraba tres equipos y se iba.

    NO AFLOJA NINGUNA PUERTA: delegacion, techo de autonomia y diagnostico del
    equipo siguen iguales. Solo cambia cuantos equipos alcanza a mirar.
    """
    from common.models import Org
    from operaciones import supervisor, tasks

    visto = {}

    def _correr(org, ahora=None, *, desatendido=False):
        visto["desatendido"] = desatendido
        return {"senales": 0}

    monkeypatch.setattr(supervisor, "correr_ciclo", _correr)
    monkeypatch.setattr(tasks, "set_rls_context", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "clear_rls_context", lambda *a, **k: None)

    org = Org.objects.create(name="Una empresa")
    tasks.ciclo_a_pedido(str(org.id))

    assert visto.get("desatendido") is True, (
        "la corrida encolada usa el presupuesto corto: mira tres equipos y se "
        "va, dejando sin diagnosticar lo que no alcanza a cerrar")


def test_si_la_cola_no_esta_se_dice_en_voz_alta(admin_client, monkeypatch):
    """
    FAIL-CLOSED. Callar un encolado que fallo deja a la persona esperando
    resultados de un ciclo que nunca arranco.
    """
    from operaciones import tasks

    def _revienta(org_id):
        raise OSError("sin cola")

    monkeypatch.setattr(tasks.ciclo_a_pedido, "delay", _revienta)

    r = admin_client.post("/api/operaciones/supervisor/ciclo/")

    assert r.status_code == 503, (
        f"un encolado fallido devolvio {r.status_code}: eso se lee como exito")
    assert "no corrió nada" in r.json().get("error", "").lower()


def test_la_respuesta_sigue_trayendo_las_claves_que_la_pantalla_lee(
        admin_client, monkeypatch):
    """
    'resumen' viaja en null y NO se omite: sacarlo del contrato romperia a
    quien lo lea sin preguntar si existe.
    """
    from operaciones import tasks

    monkeypatch.setattr(tasks.ciclo_a_pedido, "delay",
                        lambda org_id: _Tarea())

    cuerpo = admin_client.post("/api/operaciones/supervisor/ciclo/").json()

    for clave in ("resumen", "shadow_mode", "acciones_ejecutadas"):
        assert clave in cuerpo, f"falta '{clave}', que la pantalla ya leia"
    assert cuerpo["resumen"] is None
    assert cuerpo["acciones_ejecutadas"] == 0
