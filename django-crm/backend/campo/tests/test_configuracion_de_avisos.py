# -*- coding: utf-8 -*-
"""La configuración de avisos, que la empresa edita desde su pantalla.

POR QUE ESTO EXISTE Y NO ALCANZABA CON UNA FILA
-----------------------------------------------
La primera versión de los avisos guardaba el webhook en una fila que **solo un
programador podía cargar**. La regla del proyecto no dice «configuración por
empresa»: dice *configuración editable desde la interfaz y persistida por tenant,
nunca un valor fijo en código **ni en un archivo que solo un desarrollador sabe
editar***. Una fila cargada por consola es la misma falla con otra cara.

Y el modelo nombraba un proveedor —el campo se llamaba `chat_webhook`—, así que
la empresa que usa Teams no entraba.

LO QUE SE AFIRMA
----------------
1. **Cualquier tipo, no solo Google Chat.** Y la lista de tipos la dice el
   backend, no el frontend: el día que se agregue uno aparece solo.
2. **El destino NO vuelve al navegador.** En un webhook esa URL es la credencial.
3. **Solo gestión configura.** Un técnico no decide a dónde sale la información
   de la empresa.
4. **Una empresa no ve ni toca los canales de otra.**
5. **Probar recorre el mismo camino que avisar.** Una prueba que usa otro camino
   prueba otra cosa.
"""

from unittest import mock

import pytest

from campo.avisos import CanalDeAvisos, ConfiguracionDeAvisos
from common.models import Org, Profile

pytestmark = pytest.mark.django_db

CANALES = "/api/campo/avisos/canales/"
WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAA/messages?key=secreto123456"


# --------------------------------------------------------------------------- #
# A. Cualquier proveedor, no solo el que se construyó primero
# --------------------------------------------------------------------------- #

def test_a_se_puede_cargar_google_chat(admin_client, org_a):
    r = admin_client.post(
        CANALES,
        {"tipo": "google_chat", "nombre": "Cuadrilla norte", "destino": WEBHOOK},
        format="json",
    )

    assert r.status_code == 201, r.data
    assert CanalDeAvisos.objects.filter(org=org_a, tipo="google_chat").count() == 1


def test_b_y_tambien_teams_slack_o_correo(admin_client, org_a):
    """La otra dirección, y es la que da sentido al cambio.

    Si solo entrara Google Chat, el modelo seguiría nombrando un proveedor.
    """
    casos = [
        ("teams", "https://empresa.webhook.office.com/webhookb2/xyz"),
        ("slack", "https://hooks.slack.com/services/T00/B00/xyz"),
        ("correo", "coordinacion@rapilink.co"),
    ]
    for tipo, destino in casos:
        r = admin_client.post(
            CANALES, {"tipo": tipo, "destino": destino}, format="json"
        )
        assert r.status_code == 201, (tipo, r.data)

    assert CanalDeAvisos.objects.filter(org=org_a).count() == 3


def test_c_los_tipos_los_dice_el_BACKEND(admin_client):
    """Para que agregar un proveedor sea una línea y no tocar el frontend."""
    r = admin_client.get(CANALES)

    valores = {t["valor"] for t in r.data["tipos"]}
    assert "google_chat" in valores
    assert "teams" in valores
    assert "correo" in valores


def test_d_un_tipo_inventado_se_rechaza(admin_client):
    r = admin_client.post(
        CANALES, {"tipo": "telepatia", "destino": WEBHOOK}, format="json"
    )
    assert r.status_code == 400


def test_e_un_webhook_sin_https_se_rechaza_al_guardar(admin_client):
    """Guardarlo igual haría que falle recién el día de la primera devolución."""
    r = admin_client.post(
        CANALES, {"tipo": "slack", "destino": "hooks.slack.com/xyz"}, format="json"
    )
    assert r.status_code == 400


def test_f_un_correo_sin_arroba_se_rechaza(admin_client):
    r = admin_client.post(
        CANALES, {"tipo": "correo", "destino": "coordinacion"}, format="json"
    )
    assert r.status_code == 400


def test_g_el_mismo_destino_dos_veces_es_409(admin_client):
    """409 y no 400: el dato está bien, el estado no lo permite. Avisar dos
    veces al mismo lugar es como se logra que dejen de leerlos."""
    admin_client.post(
        CANALES, {"tipo": "google_chat", "destino": WEBHOOK}, format="json"
    )

    r = admin_client.post(
        CANALES, {"tipo": "google_chat", "destino": WEBHOOK}, format="json"
    )

    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# B. El destino es una credencial y no vuelve
# --------------------------------------------------------------------------- #

def test_h_el_webhook_NO_vuelve_al_navegador(admin_client):
    """LA PRUEBA DE SEGURIDAD.

    Cualquiera con esa URL publica en el espacio de la empresa. La pantalla
    necesita distinguir un canal de otro, no leer la credencial.
    """
    admin_client.post(
        CANALES,
        {"tipo": "google_chat", "nombre": "Norte", "destino": WEBHOOK},
        format="json",
    )

    r = admin_client.get(CANALES)
    cuerpo = str(r.data)

    assert "secreto123456" not in cuerpo
    assert "chat.googleapis.com" not in cuerpo
    # Pero sí lo suficiente para reconocerlo.
    assert r.data["canales"][0]["nombre"] == "Norte"
    assert r.data["canales"][0]["pista"].startswith("…")


def test_i_un_correo_SI_se_muestra_entero(admin_client):
    """No es una credencial: esconderlo haría imposible saber a quién le llega."""
    admin_client.post(
        CANALES, {"tipo": "correo", "destino": "coord@rapilink.co"}, format="json"
    )

    r = admin_client.get(CANALES)

    assert r.data["canales"][0]["pista"] == "coord@rapilink.co"


# --------------------------------------------------------------------------- #
# C. Quién puede tocar esto
# --------------------------------------------------------------------------- #

def test_j_un_tecnico_NO_puede_configurar(user_client):
    """Un técnico no decide a dónde sale la información de la empresa."""
    r = user_client.post(
        CANALES, {"tipo": "google_chat", "destino": WEBHOOK}, format="json"
    )

    assert r.status_code == 403
    assert CanalDeAvisos.objects.count() == 0


def test_k_pero_SI_puede_mirar_y_la_respuesta_lo_dice(user_client):
    """Ver qué canales hay no mueve nada, y `puede_configurar` le dice a la
    pantalla si dibujar los botones o no."""
    r = user_client.get(CANALES)

    assert r.status_code == 200
    assert r.data["puede_configurar"] is False


# --------------------------------------------------------------------------- #
# D. Una empresa no toca la de al lado
# --------------------------------------------------------------------------- #

def test_l_no_se_ven_los_canales_de_otra_empresa(admin_client, org_a,
                                                 django_user_model):
    otra = Org.objects.create(name="Otro ISP", is_active=True)
    CanalDeAvisos.objects.create(
        org=otra, tipo="google_chat", destino="https://chat.googleapis.com/otra"
    )

    r = admin_client.get(CANALES)

    assert r.data["canales"] == []


def test_m_no_se_puede_apagar_el_canal_de_otra_empresa(admin_client):
    otra = Org.objects.create(name="Otro ISP", is_active=True)
    ajeno = CanalDeAvisos.objects.create(
        org=otra, tipo="google_chat", destino="https://chat.googleapis.com/otra"
    )

    r = admin_client.patch(
        f"{CANALES}{ajeno.id}/", {"activo": False}, format="json"
    )

    assert r.status_code == 404
    ajeno.refresh_from_db()
    assert ajeno.activo is True


# --------------------------------------------------------------------------- #
# E. El botón de probar
# --------------------------------------------------------------------------- #

def test_n_probar_usa_EL_MISMO_camino_que_un_aviso(admin_client, org_a):
    """Si la prueba usara otro camino, probaría otra cosa.

    Se verifica que la prueba llama a `enviar_por`, que es exactamente lo que
    usa una devolución de verdad.
    """
    canal = CanalDeAvisos.objects.create(
        org=org_a, tipo="google_chat", destino=WEBHOOK
    )

    with mock.patch(
        "campo.services.avisos.enviar_por", return_value=True
    ) as enviar:
        r = admin_client.post(f"{CANALES}{canal.id}/probar/", {}, format="json")

    assert r.status_code == 200
    assert r.data["llego"] is True
    enviar.assert_called_once()


def test_o_un_webhook_caido_devuelve_200_diciendo_que_no_llego(admin_client, org_a):
    """200 y no 500: la PRUEBA se ejecutó bien, su resultado es el cuerpo.

    Con un 500 la pantalla diría «falló la página» cuando lo que falló fue el
    webhook de la empresa — y mandaría a buscar el problema en el lugar
    equivocado.
    """
    canal = CanalDeAvisos.objects.create(
        org=org_a, tipo="google_chat", destino=WEBHOOK
    )

    with mock.patch("campo.services.avisos.enviar_por", return_value=False):
        r = admin_client.post(f"{CANALES}{canal.id}/probar/", {}, format="json")

    assert r.status_code == 200
    assert r.data["llego"] is False
    canal.refresh_from_db()
    assert canal.ultimo_error != ""
    assert canal.probado_en is not None


def test_p_un_tecnico_no_puede_probar(user_client, org_a):
    """Probar publica un mensaje en el espacio de la empresa: es una acción."""
    canal = CanalDeAvisos.objects.create(
        org=org_a, tipo="google_chat", destino=WEBHOOK
    )

    r = user_client.post(f"{CANALES}{canal.id}/probar/", {}, format="json")

    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# F. El dominio de los enlaces
# --------------------------------------------------------------------------- #

def test_q_el_dominio_se_guarda_aparte_de_los_canales(admin_client, org_a):
    """Es de la empresa, no de un canal: repetirlo haría que un día el enlace
    del chat y el del correo apunten a lugares distintos."""
    r = admin_client.put(
        CANALES, {"url_base_app": "https://campo.rapilink.co"}, format="json"
    )

    assert r.status_code == 200
    assert ConfiguracionDeAvisos.objects.get(org=org_a).url_base_app == (
        "https://campo.rapilink.co"
    )


def test_r_vaciar_el_dominio_es_legitimo(admin_client, org_a):
    """Sin dominio el aviso sale igual, sin enlace. No es un error."""
    admin_client.put(
        CANALES, {"url_base_app": "https://campo.rapilink.co"}, format="json"
    )

    r = admin_client.put(CANALES, {"url_base_app": ""}, format="json")

    assert r.status_code == 200
    assert ConfiguracionDeAvisos.objects.get(org=org_a).url_base_app == ""


def test_s_un_dominio_sin_https_se_rechaza(admin_client):
    r = admin_client.put(
        CANALES, {"url_base_app": "campo.rapilink.co"}, format="json"
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# T. El telefono al que llama el tecnico
# --------------------------------------------------------------------------- #

def test_t1_el_telefono_de_soporte_se_guarda_y_se_lee(admin_client, org_a):
    """Hasta hoy ese numero vivia en la agenda personal de cada tecnico: uno
    nuevo no lo tenia, y el dia que cambiaba no se enteraba nadie."""
    r = admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "https://campo.rapilink.co",
         "telefono_soporte": "+57 300 111 2233"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["telefono_soporte"] == "+57 300 111 2233"

    r = admin_client.get("/api/campo/avisos/canales/")
    assert r.data["telefono_soporte"] == "+57 300 111 2233"


def test_t2_vaciarlo_es_legitimo(admin_client, org_a):
    """Sin numero la app no dibuja el boton, en vez de ofrecer una llamada que
    no va a ningun lado."""
    admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "", "telefono_soporte": "+57 300 111 2233"},
        format="json",
    )

    r = admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "", "telefono_soporte": ""},
        format="json",
    )

    assert r.status_code == 200
    assert r.data["telefono_soporte"] == ""


def test_t3_un_texto_SIN_NINGUN_DIGITO_se_rechaza(admin_client, org_a):
    """No se valida la FORMA --un plan de numeracion no es igual en dos paises,
    y rechazar un numero raro le quitaria al tecnico la unica forma de llamar--
    pero «llamar a Juan» no es un telefono, es un renglon escrito por error."""
    r = admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "", "telefono_soporte": "llamar a Juan"},
        format="json",
    )

    assert r.status_code == 400


def test_t4_guardar_el_dominio_NO_borra_el_telefono(admin_client, org_a):
    """Son la misma fila. Mandarlos por separado haria que guardar uno borre el
    otro, y el tecnico se quedaria sin el numero sin que nadie lo tocara."""
    admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "https://a.co", "telefono_soporte": "+57 300 111 2233"},
        format="json",
    )

    r = admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "https://b.co", "telefono_soporte": "+57 300 111 2233"},
        format="json",
    )

    assert r.data["url_base_app"] == "https://b.co"
    assert r.data["telefono_soporte"] == "+57 300 111 2233"


def test_t5_el_bootstrap_lo_lleva_al_telefono(admin_client, user_client, org_a):
    """Viaja SIEMPRE --aunque este vacio-- para que la app distinga «esta
    empresa no lo configuro» de «el servidor viejo no lo manda»."""
    r = user_client.get("/api/campo/bootstrap/")
    assert r.status_code == 200
    assert "telefono_soporte" in r.data["organizacion"]
    assert r.data["organizacion"]["telefono_soporte"] == ""

    admin_client.put(
        "/api/campo/avisos/canales/",
        {"url_base_app": "", "telefono_soporte": "+57 300 111 2233"},
        format="json",
    )

    r = user_client.get("/api/campo/bootstrap/")
    assert r.data["organizacion"]["telefono_soporte"] == "+57 300 111 2233"
