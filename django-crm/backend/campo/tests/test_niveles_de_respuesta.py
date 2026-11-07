# -*- coding: utf-8 -*-
"""
================================================================================
 LOS NIVELES DE RESPUESTA  --  24/10/2026
================================================================================

Ficha: supervisor-arma-la-jornada.md, «Niveles de respuesta y H-21».

  N  los niveles: sin filas, los de fabrica sin escribir; guardar escribe los
     tres y es todo o nada; nombre, plazo y prioridad se validan
  L  `nivel_del_asunto`: el contrato de cuatro claves, None si no hay, el
     asunto normalizado, y el plazo y la prioridad siguen al nivel
  P  lo que decide una persona no lo toca el Supervisor: en secuencia y con
     DOS TRANSACCIONES de verdad (la persona guarda entre la lectura y la
     escritura del Supervisor)
  H  por HTTP: leer cualquiera de campo, escribir la gestion, cada empresa
     lo suyo

    pytest campo/tests/test_niveles_de_respuesta.py
================================================================================
"""

import pytest

from campo import niveles as N

pytestmark = pytest.mark.django_db

URL = "/api/campo/niveles-de-respuesta/"
URL_ASUNTO = "/api/campo/niveles-de-respuesta/asunto/"
FABRICA = [
    {"codigo": "urgente", "nombre": "Urgente", "plazo_dias": 0, "prioridad": "alta"},
    {"codigo": "normal", "nombre": "Normal", "plazo_dias": 2, "prioridad": "media"},
    {"codigo": "programable", "nombre": "Programable", "plazo_dias": 5, "prioridad": "baja"},
]


# ---------------------------------------------------------------------------
# N · los niveles
# ---------------------------------------------------------------------------

def test_n_sin_filas_los_de_fabrica_y_leer_no_escribe(org_a):
    assert N.niveles_de(org_a) == FABRICA
    assert not N.NivelDeRespuesta.objects.exists()


def test_n2_guardar_escribe_los_tres_y_cambia_solo_lo_que_vino(org_a):
    salida = N.guardar_niveles(org_a, [{"codigo": "normal", "plazo_dias": 3,
                                        "nombre": "  Normal   de la casa "}])

    assert N.NivelDeRespuesta.objects.filter(org=org_a).count() == 3
    assert salida[1] == {"codigo": "normal", "nombre": "Normal de la casa",
                         "plazo_dias": 3, "prioridad": "media"}
    assert salida[0] == FABRICA[0] and salida[2] == FABRICA[2]


def test_n3_es_todo_o_nada(org_a):
    with pytest.raises(N.ErrorNivel):
        N.guardar_niveles(org_a, [{"codigo": "normal", "plazo_dias": 3},
                                  {"codigo": "urgente", "prioridad": "urgentisima"}])
    assert not N.NivelDeRespuesta.objects.exists()


@pytest.mark.parametrize("cambio,codigo", [
    ({"codigo": "normal", "plazo_dias": 61}, "PLAZO_INVALIDO"),
    ({"codigo": "normal", "plazo_dias": -1}, "PLAZO_INVALIDO"),
    ({"codigo": "normal", "plazo_dias": "dos"}, "PLAZO_INVALIDO"),
    ({"codigo": "normal", "plazo_dias": True}, "PLAZO_INVALIDO"),
    ({"codigo": "normal", "nombre": "   "}, "NOMBRE_VACIO"),
    ({"codigo": "normal", "nombre": "x" * 41}, "NOMBRE_LARGO"),
    ({"codigo": "normal", "prioridad": "critica"}, "PRIORIDAD_INVALIDA"),
    ({"codigo": "cuarto"}, "NIVEL_INVALIDO"),
])
def test_n4_lo_que_no_vale_se_rechaza(org_a, cambio, codigo):
    with pytest.raises(N.ErrorNivel) as e:
        N.guardar_niveles(org_a, [cambio])
    assert e.value.codigo == codigo


def test_n5_un_nivel_repetido_se_rechaza(org_a):
    with pytest.raises(N.ErrorNivel) as e:
        N.guardar_niveles(org_a, [{"codigo": "normal"}, {"codigo": "normal"}])
    assert e.value.codigo == "NIVEL_REPETIDO"


def test_n6_los_bordes_del_plazo_valen(org_a):
    salida = N.guardar_niveles(org_a, [{"codigo": "urgente", "plazo_dias": 0},
                                       {"codigo": "programable", "plazo_dias": 60}])
    assert [n["plazo_dias"] for n in salida] == [0, 2, 60]


# ---------------------------------------------------------------------------
# L · nivel_del_asunto
# ---------------------------------------------------------------------------

def test_l_sin_ubicar_o_vacio_es_none(org_a):
    assert N.nivel_del_asunto(org_a, "No Tiene Internet") is None
    assert N.nivel_del_asunto(org_a, "") is None
    assert N.nivel_del_asunto(org_a, None) is None


def test_l2_el_contrato_y_el_asunto_normalizado(org_a, admin_profile):
    N.decidir_por_persona(org_a, "Cambio De Domicilio", N.PROGRAMABLE,
                          profile=admin_profile, nombre="Ana")

    assert N.nivel_del_asunto(org_a, "cambio de  DOMICILIO") == {
        "nivel": "programable", "plazo_dias": 5, "prioridad": "baja", "por": "persona"}


def test_l2b_con_el_nombre_del_caso_tal_cual(org_a):
    """La 2.3 le pasa `caso.name`, que WispHub guarda como «Asunto - Cliente»:
    se corta igual que lo cuenta H-21."""
    N.ubicar_por_el_supervisor(org_a, "No Tiene Internet", N.URGENTE,
                               motivo="x", tickets=4, provisional=False)
    assert N.nivel_del_asunto(org_a, "No Tiene Internet - Cliente Uno")["nivel"] == "urgente"
    assert N.nivel_del_asunto(org_a, "No Tiene Internet · Cliente · #1a2b3c4d")["nivel"] == "urgente"


def test_l2c_un_normal_provisional_no_es_una_decision(org_a):
    """Con menos de 3 tickets el Supervisor deja Normal «por ahora»: eso no
    reemplaza el plazo de la plantilla (auditor independiente, 25/10/2026)."""
    N.ubicar_por_el_supervisor(org_a, "Instalacion Nueva", N.NORMAL,
                               motivo="provisional: ningún ticket leído",
                               tickets=0, provisional=True)
    assert N.nivel_del_asunto(org_a, "Instalacion Nueva") is None

    N.ubicar_por_el_supervisor(org_a, "Instalacion Nueva", N.NORMAL,
                               motivo="3 de 3", tickets=3, provisional=False)
    assert N.nivel_del_asunto(org_a, "Instalacion Nueva")["nivel"] == "normal"


def test_l3_el_plazo_y_la_prioridad_siguen_al_nivel(org_a):
    N.ubicar_por_el_supervisor(org_a, "No Tiene Internet", N.URGENTE,
                               motivo="x", tickets=4, provisional=False)
    N.guardar_niveles(org_a, [{"codigo": "urgente", "plazo_dias": 1,
                               "prioridad": "media"}])

    assert N.nivel_del_asunto(org_a, "No Tiene Internet") == {
        "nivel": "urgente", "plazo_dias": 1, "prioridad": "media", "por": "supervisor"}


def test_l4_otra_empresa_no_lo_ve(org_a, org_b):
    N.ubicar_por_el_supervisor(org_a, "No Tiene Internet", N.URGENTE,
                               motivo="x", tickets=4, provisional=False)
    assert N.nivel_del_asunto(org_b, "No Tiene Internet") is None


# ---------------------------------------------------------------------------
# P · la persona gana
# ---------------------------------------------------------------------------

def test_p_en_secuencia_el_supervisor_no_pisa_a_la_persona(org_a, admin_profile):
    assert N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="provisional",
                                      tickets=1, provisional=True) == N.NUEVO
    N.decidir_por_persona(org_a, "Megas", N.URGENTE, profile=admin_profile,
                          nombre="Ana")

    assert N.ubicar_por_el_supervisor(org_a, "Megas", N.PROGRAMABLE, motivo="y",
                                      tickets=9, provisional=False) == N.DE_UNA_PERSONA
    f = N.NivelDeAsunto.objects.get(org=org_a)
    assert (f.nivel, f.por, f.motivo, f.decidido_por_id) == (
        N.URGENTE, N.POR_PERSONA, "Lo eligió Ana", admin_profile.id)


def test_p2_nuevo_igual_y_cambio(org_a):
    r1 = N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="a",
                                    tickets=1, provisional=True)
    cuando = N.NivelDeAsunto.objects.get(org=org_a).decidido_en
    r2 = N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="b",
                                    tickets=2, provisional=True)
    f = N.NivelDeAsunto.objects.get(org=org_a)
    assert (r1, r2, f.motivo, f.tickets, f.decidido_en) == (N.NUEVO, N.IGUAL, "b", 2, cuando)

    r3 = N.ubicar_por_el_supervisor(org_a, "Megas", N.URGENTE, motivo="c",
                                    tickets=5, provisional=False)
    f.refresh_from_db()
    assert (r3, f.nivel, f.provisional) == (N.CAMBIO, N.URGENTE, False)
    assert f.decidido_en > cuando


@pytest.mark.django_db(transaction=True)
def test_p3_dos_transacciones_la_persona_guarda_mientras_el_supervisor_escribe(
        org_a, admin_profile):
    """El Supervisor leyo «del Supervisor» y va a escribir; una persona
    guarda en el medio y todavia no confirmo. Sin `por='supervisor'` en el
    filtro del UPDATE, el Supervisor esperaria y escribiria encima."""
    import threading
    import time

    from django.db import connection, transaction

    N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="provisional",
                               tickets=1, provisional=True)
    listo, errores = threading.Event(), []

    def persona():
        try:
            with transaction.atomic():
                N.decidir_por_persona(org_a, "Megas", N.URGENTE,
                                      profile=admin_profile, nombre="Ana")
                listo.set()
                time.sleep(2)
        except Exception as e:                                   # noqa: BLE001
            errores.append(repr(e))
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=persona)
    hilo.start()
    assert listo.wait(15)
    r = N.ubicar_por_el_supervisor(org_a, "Megas", N.PROGRAMABLE, motivo="9 de 9",
                                   tickets=9, provisional=False)
    hilo.join()

    assert not errores
    assert r == N.DE_UNA_PERSONA
    f = N.NivelDeAsunto.objects.get(org=org_a)
    assert (f.nivel, f.por) == (N.URGENTE, N.POR_PERSONA)


@pytest.mark.django_db(transaction=True)
def test_p4_dos_transacciones_el_supervisor_crea_la_fila_mientras_la_persona_guarda(
        org_a, admin_profile):
    """El Supervisor inserta la fila y todavia no confirmo; la persona guarda
    en ese momento. Antes, un IntegrityError (500 por HTTP). Ahora la persona
    espera, se encuentra con la fila y gana igual."""
    import threading
    import time

    from django.db import connection, transaction

    listo, errores = threading.Event(), []

    def supervisor():
        try:
            with transaction.atomic():
                N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="x",
                                           tickets=1, provisional=True)
                listo.set()
                time.sleep(2)
        except Exception as e:                                   # noqa: BLE001
            errores.append(repr(e))
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=supervisor)
    hilo.start()
    assert listo.wait(15)
    N.decidir_por_persona(org_a, "Megas", N.URGENTE, profile=admin_profile, nombre="Ana")
    hilo.join()

    assert not errores
    f = N.NivelDeAsunto.objects.get(org=org_a)
    assert (f.nivel, f.por) == (N.URGENTE, N.POR_PERSONA)


def test_p5_una_persona_de_una_empresa_no_toca_otra(org_a, org_b, admin_profile):
    N.ubicar_por_el_supervisor(org_b, "Megas", N.PROGRAMABLE, motivo="de b",
                               tickets=5, provisional=False)
    N.decidir_por_persona(org_a, "Megas", N.URGENTE, profile=admin_profile, nombre="Ana")

    b = N.NivelDeAsunto.objects.get(org=org_b)
    assert (b.nivel, b.por) == (N.PROGRAMABLE, N.POR_SUPERVISOR)
    assert N.NivelDeAsunto.objects.filter(org=org_a, por=N.POR_PERSONA).count() == 1


# ---------------------------------------------------------------------------
# H · por HTTP
# ---------------------------------------------------------------------------

def test_h_leer_cualquiera_de_campo(user_client):
    r = user_client.get(URL)
    assert r.status_code == 200
    assert r.json() == {"niveles": FABRICA, "asuntos": [], "ubica_el_supervisor": False}


def test_h2_escribir_es_de_la_gestion(user_client, org_a):
    r = user_client.put(URL, {"niveles": [{"codigo": "normal", "plazo_dias": 3}]},
                        format="json")
    assert r.status_code == 403
    assert "niveles de respuesta" in r.json()["detail"]
    assert user_client.put(URL_ASUNTO, {"asunto": "Megas", "nivel": "urgente"},
                           format="json").status_code == 403
    assert not N.NivelDeRespuesta.objects.exists()
    assert not N.NivelDeAsunto.objects.exists()


def test_h3_la_gestion_guarda_los_niveles(admin_client, org_a):
    r = admin_client.put(URL, {"niveles": [{"codigo": "normal", "plazo_dias": 3}]},
                         format="json")
    assert r.status_code == 200, r.content
    assert r.json()["niveles"][1]["plazo_dias"] == 3

    r = admin_client.put(URL, {"niveles": [{"codigo": "normal", "plazo_dias": 99}]},
                         format="json")
    assert r.status_code == 400 and r.json()["error"] == "PLAZO_INVALIDO"


def test_h4_una_persona_ubica_un_asunto_con_su_nombre(admin_client, admin_user, org_a):
    r = admin_client.put(URL_ASUNTO, {"asunto": "Cambio De Domicilio",
                                      "nivel": "programable"}, format="json")
    assert r.status_code == 200, r.content
    [a] = r.json()["asuntos"]
    assert (a["asunto"], a["nivel"], a["por"]) == ("Cambio De Domicilio", "programable",
                                                   "persona")
    esperado = (admin_user.name or admin_user.email).strip()
    assert a["decidido_por"] == esperado

    r = admin_client.put(URL_ASUNTO, {"asunto": "Megas", "nivel": "cuarto"},
                         format="json")
    assert r.status_code == 400 and r.json()["error"] == "NIVEL_INVALIDO"


def test_h5_cada_empresa_ve_lo_suyo(admin_client, org_b_client, org_a):
    admin_client.put(URL_ASUNTO, {"asunto": "Megas", "nivel": "urgente"}, format="json")
    admin_client.put(URL, {"niveles": [{"codigo": "normal", "plazo_dias": 9}]},
                     format="json")

    r = org_b_client.get(URL)
    assert r.json() == {"niveles": FABRICA, "asuntos": [], "ubica_el_supervisor": False}


def test_h7_los_asuntos_de_las_plantillas_aparecen_aunque_nadie_los_ubico(
        admin_client, org_a):
    """Sin el Supervisor ubicandolos, una persona tiene que poder ponerlos: no
    se puede elegir lo que no aparece."""
    from campo.models import WorkType
    WorkType.objects.create(org=org_a, codigo="soporte", nombre="Soporte",
                            labor="correctivo", asuntos=["Verificacion De Megas"])
    [a] = admin_client.get(URL).json()["asuntos"]
    assert (a["asunto"], a["nivel"], a["por"]) == ("Verificacion De Megas", None, None)

    r = admin_client.put(URL_ASUNTO, {"asunto": "Verificacion De Megas",
                                      "nivel": "normal"}, format="json")
    [a] = r.json()["asuntos"]
    assert (a["nivel"], a["por"]) == ("normal", "persona")


def test_h6_dice_si_el_supervisor_ubica_los_asuntos(admin_client, admin_profile, org_a):
    from operaciones import tareas_delegadas as td
    td.delegar(org_a, td.UBICAR_LOS_ASUNTOS, actor=admin_profile)
    assert admin_client.get(URL).json()["ubica_el_supervisor"] is True
