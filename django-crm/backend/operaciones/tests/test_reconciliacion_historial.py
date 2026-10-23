# -*- coding: utf-8 -*-
"""
================================================================================
 RECONCILIACION  --  el historial del chat sobrevive a la recarga
================================================================================

QUE SE ESTA PROBANDO, Y POR QUE EXISTE ESTE ARCHIVO
---------------------------------------------------
Dos ramas construyeron un chat del Supervisor. La desplegada hablaba con el
agente GENERICO del tenant y recuperaba el hilo del motor; la local habla con el
Supervisor DEDICADO y sus 15 herramientas, pero NO tenia forma de leer la
conversacion de vuelta -- se guardaba desde P5 y al recargar la pantalla
desaparecia de la vista.

Al adoptar la arquitectura dedicada habia que conservar esa propiedad. El
'GET /api/operaciones/supervisor/chat/' es lo unico que la reconciliacion
agrego al backend, y esto es lo que lo mide.

LAS CUATRO PROPIEDADES
----------------------
  1. El hilo VUELVE, con sus mensajes en orden cronologico.
  2. Vuelve el hilo de QUIEN PREGUNTA, nunca el de un companero ni el de otra
     empresa.
  3. Los roles llegan traducidos a 'user'/'assistant' -- el contrato que ya
     espera 'lib/supervisor/chat-sesion.js::aBurbujas', sin tocar ese archivo.
  4. Es LECTURA: no abre conversaciones, no escribe, y se puede pedir mil veces.
================================================================================
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import chat
from operaciones.chat_modelos import (ConversacionSupervisor, MensajeSupervisor,
                                      RolMensaje)

RUTA = "/api/operaciones/supervisor/chat/"


# =============================================================================
#  andamio
# =============================================================================

def _persona(org, correo, role="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


def _cliente(org, correo, role="OPERACIONES"):
    """Cliente autenticado + su perfil, que es lo que hace falta para el hilo."""
    from conftest import _make_authenticated_client

    u, p = _persona(org, correo, role)
    return _make_authenticated_client(u, org, p), p


@pytest.fixture
def jefe(org_a):
    return _cliente(org_a, "jefe.rec@prueba.local")


@pytest.fixture
def companero(org_a):
    return _cliente(org_a, "companero.rec@prueba.local")


@pytest.fixture
def jefe_b(org_b):
    return _cliente(org_b, "jefe.rec.b@prueba.local")


def _hilo(org, actor, pares, *, desde=None):
    """
    Una conversacion con mensajes reales, por el camino que los crea.

    'pares' es [(rol, texto), ...]. Los instantes se separan a mano para que el
    orden sea comprobable y no dependa de la resolucion del reloj.

    Un turno de ERROR lleva 'error' poblado porque la BASE lo exige
    ('mensaje_error_con_motivo'): sin motivo, un hueco en la conversacion seria
    indistinguible de un turno que nadie mando. Llenarlo aqui no es un atajo del
    andamio -- es la unica forma de crear uno.
    """
    c = chat.abrir(org, actor)
    t0 = desde or (timezone.now() - timezone.timedelta(minutes=30))
    for i, (rol, texto) in enumerate(pares):
        MensajeSupervisor.objects.create(
            org=org, conversacion=c, rol=rol, contenido=texto,
            error=("el modelo no contestó en 150 s"
                   if rol == RolMensaje.ERROR else ""),
            escrito_en=t0 + timezone.timedelta(minutes=i))
    c.ultimo_mensaje_en = t0 + timezone.timedelta(minutes=len(pares))
    c.save(update_fields=["ultimo_mensaje_en"])
    return c


# =============================================================================
#  §1  EL HILO VUELVE
# =============================================================================

def test_1_sin_conversacion_devuelve_vacio_y_no_crea_ninguna(org_a, jefe):
    cliente, _ = jefe

    r = cliente.get(RUTA)

    assert r.status_code == 200
    assert r.json() == {"conversacion_id": None, "mensajes": []}
    #  Y no se abrio un hilo porque alguien miro la pantalla.
    assert ConversacionSupervisor.objects.count() == 0


def test_2_el_hilo_vuelve_en_orden_cronologico(org_a, jefe):
    cliente, perfil = jefe
    _hilo(org_a, perfil, [
        (RolMensaje.HUMANO, "¿qué está pasando en el PON 3/1/4?"),
        (RolMensaje.SUPERVISOR, "12 ONT afectadas, hipótesis óptica."),
        (RolMensaje.HUMANO, "¿y qué evidencia tenés?"),
        (RolMensaje.SUPERVISOR, "la captura de SmartOLT de hace 4 minutos."),
    ])

    d = cliente.get(RUTA).json()

    assert [m["contenido"] for m in d["mensajes"]] == [
        "¿qué está pasando en el PON 3/1/4?",
        "12 ONT afectadas, hipótesis óptica.",
        "¿y qué evidencia tenés?",
        "la captura de SmartOLT de hace 4 minutos."]
    assert d["conversacion_id"]


def test_3_los_roles_llegan_en_el_contrato_que_espera_la_burbuja(org_a, jefe):
    """
    'aBurbujas' mapea 'user' -> usuario y 'assistant' -> supervisor, y descarta
    lo demas. Si la traduccion no se hiciera aca, la burbuja tiraria TODOS los
    mensajes y el hilo volveria vacio pareciendo que no hay historial.
    """
    cliente, perfil = jefe
    _hilo(org_a, perfil, [(RolMensaje.HUMANO, "hola"),
                          (RolMensaje.SUPERVISOR, "hola")])

    roles = [m["rol"] for m in cliente.get(RUTA).json()["mensajes"]]

    assert roles == ["user", "assistant"]
    assert "humano" not in roles and "supervisor" not in roles


def test_4_cada_mensaje_trae_id_y_cuando(org_a, jefe):
    cliente, perfil = jefe
    _hilo(org_a, perfil, [(RolMensaje.HUMANO, "hola")])

    m = cliente.get(RUTA).json()["mensajes"][0]

    assert m["id"] and m["creado_en"]
    assert set(m) == {"id", "rol", "contenido", "creado_en"}


# =============================================================================
#  §2  QUE NO VUELVE, Y ES A PROPOSITO
# =============================================================================

def test_5_los_turnos_de_herramienta_no_vuelven_pero_siguen_guardados(org_a,
                                                                      jefe):
    """
    El detalle interno del bucle lo necesita el modelo, no una persona. Lo que
    se afirma es lo de los DOS lados: no sale por la ruta, y sigue en la tabla.
    """
    cliente, perfil = jefe
    _hilo(org_a, perfil, [
        (RolMensaje.HUMANO, "¿qué está pasando?"),
        (RolMensaje.HERRAMIENTA, '{"situaciones": 1}'),
        (RolMensaje.SUPERVISOR, "hay una situación viva."),
    ])

    d = cliente.get(RUTA).json()

    assert [m["rol"] for m in d["mensajes"]] == ["user", "assistant"]
    assert '{"situaciones": 1}' not in str(d)
    #  Pero NO se borro: sigue en la base para la auditoría.
    assert MensajeSupervisor.objects.filter(
        org=org_a, rol=RolMensaje.HERRAMIENTA).count() == 1


def test_6_un_turno_con_ERROR_tampoco_se_disfraza_de_respuesta(org_a, jefe):
    """
    Mandarlo como 'assistant' lo haria leer como una respuesta del Supervisor,
    que es lo contrario de lo que es. Es una pérdida DECLARADA.
    """
    cliente, perfil = jefe
    _hilo(org_a, perfil, [
        (RolMensaje.HUMANO, "¿y ahora?"),
        (RolMensaje.ERROR, "el modelo no contestó"),
    ])

    d = cliente.get(RUTA).json()

    assert [m["rol"] for m in d["mensajes"]] == ["user"]
    assert "el modelo no contestó" not in str(d)
    #  Ni el contenido ni el motivo tecnico del fallo llegan al navegador.
    assert "150 s" not in str(d)
    guardado = MensajeSupervisor.objects.get(org=org_a, rol=RolMensaje.ERROR)
    assert guardado.error, "sigue guardado CON su motivo, para la auditoría"


# =============================================================================
#  §3  DE QUIEN ES EL HILO
# =============================================================================

def test_7_no_se_lee_la_conversacion_de_un_companero(org_a, jefe, companero):
    """
    Los dos son OPERACIONES en la MISMA empresa, así que el tenant no alcanza
    para separarlos: lo que separa es el filtro por 'actor'.
    """
    cli_jefe, p_jefe = jefe
    _, p_otro = companero
    _hilo(org_a, p_jefe, [(RolMensaje.HUMANO, "lo que preguntó el jefe")])
    _hilo(org_a, p_otro, [(RolMensaje.HUMANO, "lo que preguntó el compañero")])

    d = cli_jefe.get(RUTA).json()

    assert [m["contenido"] for m in d["mensajes"]] == ["lo que preguntó el jefe"]
    assert "compañero" not in str(d)


def test_8_no_se_cruza_entre_empresas(org_a, org_b, jefe, jefe_b):
    cli_a, p_a = jefe
    cli_b, p_b = jefe_b
    _hilo(org_a, p_a, [(RolMensaje.HUMANO, "pregunta de A")])
    _hilo(org_b, p_b, [(RolMensaje.HUMANO, "pregunta de B")])

    da = cli_a.get(RUTA).json()
    db = cli_b.get(RUTA).json()

    assert [m["contenido"] for m in da["mensajes"]] == ["pregunta de A"]
    assert [m["contenido"] for m in db["mensajes"]] == ["pregunta de B"]
    assert da["conversacion_id"] != db["conversacion_id"]


def test_9_sin_el_rol_de_gestion_no_se_lee_nada(org_a, user_client,
                                                user_profile):
    """Mismo permiso que el POST: el panorama operativo no es para cualquiera."""
    r = user_client.get(RUTA)

    assert r.status_code in (401, 403), r.status_code


def test_10_sin_sesion_tampoco(org_a, unauthenticated_client):
    r = unauthenticated_client.get(RUTA)
    assert r.status_code in (401, 403)


# =============================================================================
#  §4  ES LECTURA, Y TIENE TOPE
# =============================================================================

def test_11_el_GET_no_escribe_ni_una_fila(org_a, jefe):
    cliente, perfil = jefe
    c = _hilo(org_a, perfil, [(RolMensaje.HUMANO, "hola"),
                              (RolMensaje.SUPERVISOR, "hola")])
    antes = (ConversacionSupervisor.objects.count(),
             MensajeSupervisor.objects.count(),
             Activity.objects.count(),
             c.ultimo_mensaje_en)

    for _ in range(3):
        cliente.get(RUTA)

    c.refresh_from_db()
    assert (ConversacionSupervisor.objects.count(),
            MensajeSupervisor.objects.count(),
            Activity.objects.count(),
            c.ultimo_mensaje_en) == antes


def test_12_el_limite_lo_pone_el_servidor_no_el_navegador(org_a, jefe,
                                                          monkeypatch):
    """
    Un tope que solo vive del lado del cliente no es un tope: '?limite=99999'
    traeria la tabla entera.

    POR QUE SE BAJA EL TOPE EN VEZ DE CREAR 201 MENSAJES
    ----------------------------------------------------
    La primera version de esta prueba creaba 12 mensajes, pedia 99999 y afirmaba
    que volvian 12 -- mas 'TOPE_HISTORIAL == 200'. Sobrevivio a quitar el tope
    del servidor (medido: la mutacion 'm3_sin_tope_del_servidor' la dejo en
    verde), porque con 12 filas el recorte no cambia nada y afirmar que una
    constante EXISTE no prueba que se APLIQUE. Es el antipatron que CLAUDE.md §6
    nombra, cometido aqui.

    Bajando el tope a 3 y dejando 10 mensajes, el recorte tiene que verse en el
    resultado o la prueba cae.
    """
    from operaciones.views import ChatSupervisorView

    monkeypatch.setattr(ChatSupervisorView, "TOPE_HISTORIAL", 3)
    cliente, perfil = jefe
    _hilo(org_a, perfil, [(RolMensaje.HUMANO, f"m{i}") for i in range(10)])

    d = cliente.get(f"{RUTA}?limite=99999").json()

    #  El EFECTO: el navegador pidio 99999 y el servidor devolvio 3.
    assert len(d["mensajes"]) == 3
    assert [m["contenido"] for m in d["mensajes"]] == ["m7", "m8", "m9"]


def test_13_un_limite_pide_los_ULTIMOS_no_los_primeros(org_a, jefe):
    """
    Al abrir la burbuja interesa el final de la conversación. Devolver los
    primeros dejaría la pantalla en una charla de ayer.
    """
    cliente, perfil = jefe
    _hilo(org_a, perfil, [(RolMensaje.HUMANO, f"m{i}") for i in range(10)])

    d = cliente.get(f"{RUTA}?limite=3").json()

    assert [m["contenido"] for m in d["mensajes"]] == ["m7", "m8", "m9"]


def test_14_un_limite_ilegible_no_rompe_la_pantalla(org_a, jefe):
    cliente, perfil = jefe
    _hilo(org_a, perfil, [(RolMensaje.HUMANO, "hola")])

    r = cliente.get(f"{RUTA}?limite=ayer")

    assert r.status_code == 200
    assert len(r.json()["mensajes"]) == 1


def test_15_con_dos_hilos_vuelve_el_MAS_RECIENTE(org_a, jefe):
    cliente, perfil = jefe
    viejo = _hilo(org_a, perfil, [(RolMensaje.HUMANO, "lo de ayer")],
                  desde=timezone.now() - timezone.timedelta(days=1))
    nuevo = _hilo(org_a, perfil, [(RolMensaje.HUMANO, "lo de ahora")])

    d = cliente.get(RUTA).json()

    assert d["conversacion_id"] == str(nuevo.id)
    assert [m["contenido"] for m in d["mensajes"]] == ["lo de ahora"]
    assert str(viejo.id) != d["conversacion_id"]
