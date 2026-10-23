# -*- coding: utf-8 -*-
"""Avisarle al tecnico que le devolvieron un trabajo.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
Medido el 04/10/2026: la app de campo no tiene push ni sincronizacion de fondo.
Es cien por ciento *pull*: el tecnico se entera de las cosas cuando abre la
orden. Por eso hoy la devolucion se le avisa **a mano por Google Chat**, que no
es una maña sino el unico canal que lo alcanza -- y que dice MENOS que lo que la
app ya sabe: que evidencia hay que volver a tomar esta en la ficha.

LO QUE SE AFIRMA, Y QUE PASA SI SE ROMPE
----------------------------------------
1. **El aviso sale DESPUES del commit.** `requerir_correccion` es atomica, y el
   proyecto tiene una decision congelada: ninguna transaccion abierta esperando a
   un tercero. Ademas da la garantia correcta: si la devolucion se deshace, el
   aviso no sale.

2. **Un webhook caido no rompe la devolucion.** El supervisor la hizo; que el
   mensaje no llegue es otro problema.

3. **No se avisa dos veces el mismo hecho.** Por clave primaria, no por un
   `select` previo -- ahi vive la carrera. Un tecnico que recibe el mismo aviso
   repetido apaga las notificaciones.

4. **Sin datos del cliente.** Un mensaje de chat sale del sistema y queda en una
   conversacion que nadie audita.
"""

from unittest import mock

import pytest
from django.db import transaction

from campo.avisos import (
    AvisoEnviado,
    CanalDeAvisos,
    ConfiguracionDeAvisos,
    DispositivoDeTecnico,
)
from campo.models import (
    AsignacionTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import transiciones
from common.models import Profile

# TRANSACCIONES DE VERDAD, Y NO ES UN DETALLE DE LA PRUEBA
# --------------------------------------------------------
# Todo este archivo depende de `transaction.on_commit`. Con la base envuelta en
# una transaccion que nunca se confirma --el modo normal de pytest-django-- esos
# callbacks NO corren nunca, y las pruebas pasarian en verde sin haber enviado
# nada: exactamente el tipo de prueba que este proyecto llama "en verde con el
# sintoma vivo".
#
# `transaction=True` hace commits reales. Es mas lento y es la unica forma de
# medir lo que estas pruebas dicen medir.
pytestmark = pytest.mark.django_db(transaction=True)


ESQUEMA = {
    "pasos": [],
    "campos": [],
    "evidencias": [
        {"id": "foto_medicion", "titulo": "Fotografía de la medición", "tipo": "foto"},
        {"id": "foto_cto", "titulo": "Fotografía de la caja CTO", "tipo": "foto"},
    ],
}


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.avisos@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def orden(org_a, tecnico):
    wt = WorkType.objects.create(org=org_a, codigo="avisos_test", nombre="Prueba")
    version = WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=ESQUEMA,
    )
    o = OrdenTrabajo.objects.create(
        org=org_a,
        numero=9301,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzón",
        cliente_direccion="Calle 50 # 10-20",
        cliente_telefono="+57 312 455 8901",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        # Son DOS maquinas: la operativa dice dónde está el trabajo y ésta dice
        # si alguien lo dio por bueno. Para devolverlo tiene que estar esperando
        # veredicto; desde `sin_evaluar` la transición se niega, y con razón.
        estado_validacion=OrdenTrabajo.PENDIENTE,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=tecnico[1], rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def canal(org_a):
    """Un canal de chat y el dominio de los enlaces.

    Son DOS cosas: el canal es uno de varios posibles; el dominio es de la
    empresa. Repetirlo en cada canal haría que un día el enlace del chat y el
    del correo apunten a lugares distintos.
    """
    ConfiguracionDeAvisos.objects.create(
        org=org_a, url_base_app="https://campo.rapilink.co"
    )
    return CanalDeAvisos.objects.create(
        org=org_a,
        tipo=CanalDeAvisos.GOOGLE_CHAT,
        nombre="Cuadrilla norte",
        destino="https://chat.googleapis.com/v1/spaces/XXX/messages?key=k",
        activo=True,
    )


def _devolver(orden, profile, requisitos=None, observacion=""):
    return transiciones.requerir_correccion(
        orden,
        requisitos or ["foto_medicion"],
        profile=profile,
        observacion=observacion,
    )


# --------------------------------------------------------------------------- #
# A. El aviso sale, y sale despues del commit
# --------------------------------------------------------------------------- #

def test_a_devolver_un_trabajo_publica_en_el_chat(orden, tecnico, canal):
    with mock.patch(
        "campo.services.avisos.enviar_por", return_value=True
    ) as publicar:
        _devolver(orden, tecnico[1])

    publicar.assert_called_once()
    assert AvisoEnviado.objects.filter(org=orden.org).count() == 1
    assert AvisoEnviado.objects.get().canales == ["google_chat"]


def test_b_el_aviso_NO_sale_dentro_de_la_transaccion(orden, tecnico, canal):
    """LA PRUEBA QUE SOSTIENE LA DECISION CONGELADA.

    Si el envio ocurriera dentro de `requerir_correccion` --que es atomica--,
    habria una transaccion de base abierta esperando a un webhook. Acá se
    comprueba que cuando el mensaje sale, ya no hay transaccion en curso.
    """
    visto = {}

    def _espiar(canal, *, asunto, texto):
        # `get_connection().in_atomic_block` dice si todavia estamos adentro.
        from django.db import connection

        visto["en_transaccion"] = connection.in_atomic_block
        return True

    with mock.patch("campo.services.avisos.enviar_por", side_effect=_espiar):
        _devolver(orden, tecnico[1])

    assert visto["en_transaccion"] is False


def test_c_si_la_devolucion_se_deshace_el_aviso_no_sale(orden, tecnico, canal):
    """La otra cara de `on_commit`, y la razon de fondo para usarlo.

    Avisar de algo que todavia se puede deshacer manda al tecnico a buscar una
    devolucion que no existe.
    """
    with mock.patch(
        "campo.services.avisos.enviar_por", return_value=True
    ) as publicar:
        try:
            with transaction.atomic():
                _devolver(orden, tecnico[1])
                raise RuntimeError("algo falló después")
        except RuntimeError:
            pass

    publicar.assert_not_called()


# --------------------------------------------------------------------------- #
# B. Un aviso que falla no rompe el hecho
# --------------------------------------------------------------------------- #

def test_d_un_webhook_caido_no_impide_devolver(orden, tecnico, canal):
    with mock.patch(
        "campo.services.avisos.enviar_por", side_effect=OSError("sin red")
    ):
        _devolver(orden, tecnico[1])

    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert orden.vuelta == 2


def test_e_sin_canal_configurado_la_devolucion_ocurre_igual(orden, tecnico):
    """Ninguna empresa nace con esto configurado: no avisar es el defecto."""
    _devolver(orden, tecnico[1])

    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert AvisoEnviado.objects.count() == 0


def test_f_un_canal_apagado_no_publica(orden, tecnico, canal):
    canal.activo = False
    canal.save(update_fields=["activo"])

    with mock.patch(
        "campo.services.avisos.enviar_por", return_value=True
    ) as publicar:
        _devolver(orden, tecnico[1])

    publicar.assert_not_called()


# --------------------------------------------------------------------------- #
# C. El mismo hecho se avisa una sola vez
# --------------------------------------------------------------------------- #

def test_g_dos_devoluciones_distintas_avisan_dos_veces(orden, tecnico, canal):
    """Devolver la vuelta 2 y la vuelta 3 son dos hechos."""
    with mock.patch(
        "campo.services.avisos.enviar_por", return_value=True
    ) as publicar:
        _devolver(orden, tecnico[1])
        orden.refresh_from_db()
        orden.estado_operativo = OrdenTrabajo.COMPLETADA_CAMPO
        orden.save(update_fields=["estado_operativo"])
        _devolver(orden, tecnico[1])

    assert publicar.call_count == 2
    assert AvisoEnviado.objects.count() == 2


def test_h_el_mismo_hecho_no_se_avisa_dos_veces(orden, tecnico, canal):
    """La guarda de idempotencia, probada sin pasar por la transicion.

    Se llama al despachador dos veces con la MISMA clave, que es lo que pasaria
    con un reintento o con dos supervisores a la vez.
    """
    from campo.services import avisos as serv

    with mock.patch.object(serv, "enviar_por", return_value=True) as publicar:
        for _ in range(2):
            serv._enviar_ahora(
                org=orden.org,
                clave=f"devolucion|{orden.id}|2",
                asunto="t",
                texto="x",
                enlace_a=orden.id,
                perfiles=[],
            )

    assert publicar.call_count == 1
    assert AvisoEnviado.objects.count() == 1


# --------------------------------------------------------------------------- #
# D. Que dice el mensaje, y que NO dice
# --------------------------------------------------------------------------- #

def test_i_el_mensaje_dice_QUE_hay_que_rehacer_con_su_titulo(orden, tecnico, canal):
    """La diferencia con el mensaje escrito a mano.

    «foto_medicion» es como se llama el campo; «Fotografía de la medición» es
    como se le dice a una persona. Y sale de la plantilla INMUTABLE de la orden.
    """
    textos = []
    with mock.patch(
        "campo.services.avisos.enviar_por",
        side_effect=lambda c, *, asunto, texto: textos.append(texto) or True,
    ):
        _devolver(
            orden,
            tecnico[1],
            requisitos=["foto_medicion"],
            observacion="La medición no coincide con la lectura de la OLT.",
        )

    mensaje = textos[0]
    assert "#9301" in mensaje
    assert "Fotografía de la medición" in mensaje
    assert "foto_medicion" not in mensaje
    assert "La medición no coincide" in mensaje


def test_j_el_mensaje_NO_lleva_datos_del_cliente(orden, tecnico, canal):
    """LA PRUEBA DE PRIVACIDAD.

    Un mensaje de chat sale del sistema y queda en una conversacion que nadie
    audita. Lleva el numero de la OT y un enlace: quien lo abre se autentica y
    ahi si ve la ficha.
    """
    textos = []
    with mock.patch(
        "campo.services.avisos.enviar_por",
        side_effect=lambda c, *, asunto, texto: textos.append(texto) or True,
    ):
        _devolver(orden, tecnico[1])

    mensaje = textos[0]
    assert "Beatriz" not in mensaje
    assert "Calle 50" not in mensaje
    assert "312 455 8901" not in mensaje


def test_k_el_enlace_sale_del_dominio_de_la_empresa(orden, tecnico, canal):
    textos = []
    with mock.patch(
        "campo.services.avisos.enviar_por",
        side_effect=lambda c, *, asunto, texto: textos.append(texto) or True,
    ):
        _devolver(orden, tecnico[1])

    assert f"https://campo.rapilink.co/ot/{orden.id}" in textos[0]


def test_l_sin_dominio_configurado_el_aviso_sale_igual_sin_enlace(
    orden, tecnico, canal
):
    """Un aviso sin enlace sigue sirviendo: dice que pasó algo y en qué OT."""
    config = ConfiguracionDeAvisos.objects.get(org=canal.org)
    config.url_base_app = ""
    config.save(update_fields=["url_base_app"])

    textos = []
    with mock.patch(
        "campo.services.avisos.enviar_por",
        side_effect=lambda c, *, asunto, texto: textos.append(texto) or True,
    ):
        _devolver(orden, tecnico[1])

    assert "#9301" in textos[0]
    assert "http" not in textos[0]


# --------------------------------------------------------------------------- #
# E. El registro del telefono
# --------------------------------------------------------------------------- #

RUTA = "/api/campo/dispositivo/"


def test_m_registrar_el_mismo_token_dos_veces_deja_UNA_fila(
    user_client, org_a, user_profile
):
    """La app lo manda en CADA arranque.

    Si cada envio creara una fila, el mismo telefono recibiria el aviso cinco
    veces -- que es exactamente lo que hace que la gente apague las
    notificaciones.
    """
    for _ in range(3):
        r = user_client.post(RUTA, {"token": "abc123"}, format="json")
        assert r.status_code in (200, 201), r.data

    assert DispositivoDeTecnico.objects.filter(org=org_a, token="abc123").count() == 1


def test_n_sin_token_se_rechaza(user_client):
    r = user_client.post(RUTA, {"token": "   "}, format="json")
    assert r.status_code == 400


def test_o_cerrar_sesion_da_de_baja_sin_borrar(user_client, org_a, user_profile):
    """Un telefono de cuadrilla pasa de mano en mano: el que entra no tiene por
    que recibir los avisos del que salio. Pero la fila queda, con su fecha."""
    user_client.post(RUTA, {"token": "abc123"}, format="json")

    r = user_client.delete(RUTA, {"token": "abc123"}, format="json")

    assert r.status_code == 200
    assert r.data["dados_de_baja"] == 1
    fila = DispositivoDeTecnico.objects.get(token="abc123")
    assert fila.activo is False


def test_p_sin_credencial_de_push_no_se_afirma_un_envio(orden, tecnico, canal):
    """HONESTIDAD SOBRE LO QUE NO SALIO.

    El proveedor ya existe --FCM, en `services/push_fcm.py`-- pero sin la
    credencial de la plataforma no se intenta nada. `canales` tiene que decir
    `["google_chat"]` y NO `["google_chat", "push"]`: afirmar un envio que no
    ocurrio es exactamente lo que el metodo del proyecto prohibe.

    Que una EMPRESA no tenga nada configurado es el estado normal; que la
    PLATAFORMA no tenga credencial es un despliegue a medias, y se ve en el log
    (`push_sin_proveedor`), no en una mentira en la base. El camino con
    credencial se mide en `test_push_al_telefono.py`.
    """
    DispositivoDeTecnico.objects.create(
        org=orden.org, profile=tecnico[1], token="tok-1", activo=True
    )

    with mock.patch("campo.services.avisos.enviar_por", return_value=True):
        _devolver(orden, tecnico[1])

    assert AvisoEnviado.objects.get().canales == ["google_chat"]



# --------------------------------------------------------------------------- #
# G. La notificación EN la plataforma, que es el hecho y no una entrega
# --------------------------------------------------------------------------- #

def test_q_devolver_escribe_una_notificacion_por_persona(orden, tecnico):
    """LO QUE FALTABA, Y YA EXISTIA EN LA CASA.

    `common/notifications.py` es el único punto de llamada de toda la plataforma
    y su encabezado dice «y futuras apps». Campo era la única parte que no lo
    usaba: se había ido a buscar un canal hacia afuera teniendo el mecanismo
    adentro.

    Con esto el supervisor la ve en su campanita y el técnico en su app, **sin
    que ninguna empresa configure nada**.
    """
    from common.models import Notification

    _devolver(orden, tecnico[1], observacion="No coincide con la OLT")

    notif = Notification.objects.get(recipient=tecnico[1])
    assert notif.verb == "trabajo_devuelto"
    assert notif.entity_name == "OT #9301"
    assert notif.data["rehacer"] == ["Fotografía de la medición"]
    assert notif.data["observacion"] == "No coincide con la OLT"
    assert notif.read_at is None


def test_r_la_notificacion_NO_lleva_datos_del_cliente(orden, tecnico):
    """Se sincroniza al teléfono y se queda ahí. El detalle del cliente ya vive
    en la ficha, detrás de la sesión."""
    from common.models import Notification

    _devolver(orden, tecnico[1])

    crudo = str(Notification.objects.get(recipient=tecnico[1]).data)
    assert "Beatriz" not in crudo
    assert "Calle 50" not in crudo
    assert "312 455 8901" not in crudo


def test_s_la_notificacion_es_PARTE_DEL_HECHO_y_se_deshace_con_el(orden, tecnico):
    """LA DIFERENCIA CON UNA ENTREGA, afirmada donde se puede romper.

    El envío por chat va después del commit —no se puede bloquear una fila
    esperando a un tercero—. La notificación va DENTRO: si la devolución se
    deshace, avisar de algo que no pasó manda al técnico a buscar una devolución
    que no existe.
    """
    from common.models import Notification

    try:
        with transaction.atomic():
            _devolver(orden, tecnico[1])
            raise RuntimeError("algo falló después")
    except RuntimeError:
        pass

    assert Notification.objects.count() == 0


def test_s2_la_notificacion_EXISTE_antes_del_commit(orden, tecnico):
    """LA PRUEBA QUE DISTINGUE, Y QUE FALTABA.

    `test_s` --que la notificación se deshace con el rollback-- NO alcanza:
    `on_commit` tampoco corre en un rollback, así que pasaba en verde con la
    notificación movida a `on_commit`. Lo midió una mutación el 04/10/2026.

    Lo que de verdad separa «parte del hecho» de «entrega» es esto: estando
    todavía DENTRO de la transacción, la notificación ya tiene que existir. Una
    entrega, no.
    """
    from common.models import Notification

    with transaction.atomic():
        _devolver(orden, tecnico[1])
        # Sin salir del bloque: si esto fuera un `on_commit`, acá no habría nada.
        assert Notification.objects.filter(recipient=tecnico[1]).count() == 1


def test_t_sin_canales_configurados_la_notificacion_llega_IGUAL(orden, tecnico):
    """La razón de fondo del cambio.

    Una empresa sin Workspace, sin Slack y sin correo configurado —el caso de
    Rapilink, medido el 04/10/2026— no recibía absolutamente nada. Ahora recibe
    lo que importa: la notificación vive en la plataforma y no depende de que
    alguien pegue una URL.
    """
    from common.models import Notification

    assert CanalDeAvisos.objects.count() == 0

    _devolver(orden, tecnico[1])

    assert Notification.objects.filter(recipient=tecnico[1]).count() == 1
