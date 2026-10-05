# -*- coding: utf-8 -*-
"""El golpecito en el hombro: que el telefono avise sin que nadie abra la app.

QUE SE AFIRMA, Y QUE PASA SI SE ROMPE
-------------------------------------
1. **Al telefono va el enlace RELATIVO.** El chat recibe `https://dominio/ot/x`
   porque lo abre un navegador; la app recibe `/ot/x` porque lo abre en su propia
   pantalla. Si al telefono le llegara el absoluto, tocar el aviso abriria el
   navegador y pediria iniciar sesion en la web: el tecnico se queda afuera de la
   orden que le acaban de devolver.

2. **Cada persona recibe el id de SU notificacion.** Con el, el aviso que llega
   por push y el que despues baja la sincronizacion son la misma fila. Sin el
   --o con el del compañero-- el telefono mostraria la misma notificacion dos
   veces, y la segunda sin leer.

3. **Un token muerto se da de baja; un fallo de red NO.** FCM distingue «este
   telefono no existe mas» de «no se pudo ahora», y confundirlos tiene costo en
   las dos direcciones: dar de baja por un 500 deja al tecnico sin avisos hasta
   que reinstale, y no dar de baja un `UNREGISTERED` hace que cada aviso futuro
   pague un viaje a Google para que lo rechacen.

4. **Todo valor de `data` es cadena.** FCM rechaza el mensaje ENTERO con un 400
   si hay un numero, una lista o un nulo ahi. El sintoma es «el push no llega» y
   no señala a la causa.

5. **Sin datos del cliente.** Un push se queda en la bandeja del sistema
   operativo, que es lo mas parecido a un lugar publico que tiene un telefono.

6. **Sin credencial no se intenta.** Ni una llamada. Un viaje que va a fallar
   seguro solo demora el aviso por los canales que si estan configurados.

COMO SE FINGE FCM, Y POR QUE ASI
--------------------------------
Se reemplaza `requests.post` y la credencial, no el modulo entero: lo que hay que
medir es **el cuerpo que sale**, y un doble del modulo lo haria desaparecer. Las
pruebas de `_cargar` usan una clave RSA de verdad, generada aca: una credencial
falsa no prueba que el JSON que Google entrega se pueda leer.
"""

import json
from unittest import mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from campo.avisos import AvisoEnviado, ConfiguracionDeAvisos, DispositivoDeTecnico
from campo.models import (
    AsignacionTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import avisos as servicio_avisos
from campo.services import push_fcm, transiciones
from common.models import Notification, Profile

# Ver el encabezado de `test_avisos_al_tecnico.py`: todo esto cuelga de
# `transaction.on_commit`, y sin commits reales esos callbacks no corren nunca.
pytestmark = pytest.mark.django_db(transaction=True)


ESQUEMA = {
    "pasos": [],
    "campos": [],
    "evidencias": [
        {"id": "foto_medicion", "titulo": "Fotografía de la medición", "tipo": "foto"},
        {"id": "foto_cto", "titulo": "Fotografía de la caja CTO", "tipo": "foto"},
    ],
}

CREDENCIAL = {"project_id": "dexter-app-d4b93"}


# --------------------------------------------------------------------------- #
# Andamiaje
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def sin_credencial_cacheada():
    """Cada prueba arranca sin credencial en memoria.

    Sin esto, la primera que configura una se la deja puesta a todas las que
    corren despues en el mismo proceso, y la prueba que afirma «sin credencial no
    sale nada» pasaria usando la de otra.
    """
    push_fcm._reiniciar_para_pruebas()
    yield
    push_fcm._reiniciar_para_pruebas()


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.push@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def companero(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="companero.push@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def orden(org_a, tecnico):
    wt = WorkType.objects.create(org=org_a, codigo="push_test", nombre="Prueba push")
    version = WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=ESQUEMA,
    )
    o = OrdenTrabajo.objects.create(
        org=org_a,
        numero=9401,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzón",
        cliente_direccion="Calle 50 # 10-20",
        cliente_telefono="+57 312 455 8901",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=tecnico[1], rol="tecnico", es_principal=True
    )
    ConfiguracionDeAvisos.objects.create(
        org=org_a, url_base_app="https://campo.rapilink.co"
    )
    return o


def _telefono(org, profile, token):
    return DispositivoDeTecnico.objects.create(
        org=org, profile=profile, token=token, plataforma="android", activo=True
    )


def _devolver(orden, profile, requisitos=None, observacion=""):
    return transiciones.requerir_correccion(
        orden,
        requisitos or ["foto_medicion"],
        profile=profile,
        observacion=observacion,
    )


class _Respuesta:
    """Lo minimo que `push_fcm` le pide a una respuesta de `requests`."""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("sin cuerpo")
        return self._payload


def _ok():
    return _Respuesta(200, {"name": "projects/x/messages/1"})


def _unregistered():
    return _Respuesta(
        404,
        {
            "error": {
                "status": "NOT_FOUND",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode": "UNREGISTERED",
                    }
                ],
            }
        },
    )


class _CredencialFalsa:
    token = "ya29.falso"

    def refresh(self, pedido):
        return None


def _con_fcm(respuestas):
    """Finge la credencial y `requests.post`. Devuelve el espia del POST.

    `respuestas` puede ser una respuesta --para todas las llamadas-- o una lista
    que se consume en orden, que es como se prueban dos telefonos con suertes
    distintas.
    """
    if not isinstance(respuestas, list):
        lado = lambda *a, **k: respuestas  # noqa: E731
    else:
        cola = list(respuestas)
        lado = lambda *a, **k: cola.pop(0)  # noqa: E731

    return (
        mock.patch.dict(
            "os.environ", {push_fcm.VARIABLE: json.dumps(CREDENCIAL)}, clear=False
        ),
        mock.patch.object(
            push_fcm, "_cargar", return_value=(_CredencialFalsa(), "dexter-app-d4b93")
        ),
        mock.patch.object(push_fcm.requests, "post", side_effect=lado),
    )


def _mandar(orden, tecnico, respuestas=None, observacion="", requisitos=None):
    """Devuelve el trabajo con FCM fingido y entrega el espia del POST."""
    entorno, credencial, post = _con_fcm(respuestas or _ok())
    with entorno, credencial, post as espia:
        _devolver(orden, tecnico[1], requisitos=requisitos, observacion=observacion)
    return espia


def _cuerpos(espia):
    return [llamada.kwargs["json"]["message"] for llamada in espia.call_args_list]


# --------------------------------------------------------------------------- #
# A. Que sale, exactamente
# --------------------------------------------------------------------------- #

def test_a1_al_telefono_le_llega_el_enlace_RELATIVO_no_el_del_dominio(orden, tecnico):
    """EL QUE MAS IMPORTA.

    El absoluto abriria el navegador y pediria iniciar sesion en la web. El
    dominio esta configurado --la fixture lo pone-- justamente para que esta
    prueba falle si alguien reusa el enlace del chat.
    """
    _telefono(orden.org, tecnico[1], "tok-rel")
    espia = _mandar(orden, tecnico)

    mensaje = _cuerpos(espia)[0]
    assert mensaje["data"]["enlace"] == f"/ot/{orden.id}"
    assert "campo.rapilink.co" not in mensaje["data"]["enlace"]


def test_a2_el_push_lleva_el_id_de_LA_notificacion_de_esa_persona(orden, tecnico):
    _telefono(orden.org, tecnico[1], "tok-id")
    espia = _mandar(orden, tecnico)

    notificacion = Notification.objects.get(recipient=tecnico[1])
    assert _cuerpos(espia)[0]["data"]["id"] == str(notificacion.id)


def test_a3_dos_tecnicos_reciben_cada_uno_SU_id_y_no_el_del_otro(
    orden, tecnico, companero
):
    """La prueba que caza el atajo de mandar un solo id a todos.

    Un id compartido haria que el telefono del segundo espeje la notificacion
    del primero: la leeria, y la suya seguiria sin leer para siempre.
    """
    AsignacionTrabajo.objects.create(
        orden=orden, profile=companero[1], rol="tecnico", es_principal=False
    )
    _telefono(orden.org, tecnico[1], "tok-uno")
    _telefono(orden.org, companero[1], "tok-dos")

    espia = _mandar(orden, tecnico)

    por_token = {m["token"]: m["data"]["id"] for m in _cuerpos(espia)}
    esperado = {
        "tok-uno": str(Notification.objects.get(recipient=tecnico[1]).id),
        "tok-dos": str(Notification.objects.get(recipient=companero[1]).id),
    }
    assert por_token == esperado
    assert esperado["tok-uno"] != esperado["tok-dos"]


def test_a4_todo_valor_de_data_es_cadena(orden, tecnico):
    """FCM rechaza el mensaje ENTERO con 400 si hay un entero o una lista.

    `rehacer` es una lista y `vuelta` un entero, asi que el contenido viaja
    serializado. Afirmar sobre los TIPOS y no sobre las claves es lo que hace que
    esto siga valiendo cuando alguien agregue un campo mas.
    """
    _telefono(orden.org, tecnico[1], "tok-tipos")
    espia = _mandar(orden, tecnico, observacion="Falta la foto del empalme")

    datos = _cuerpos(espia)[0]["data"]
    no_cadenas = {k: type(v).__name__ for k, v in datos.items() if not isinstance(v, str)}
    assert no_cadenas == {}


def test_a5_el_contenido_viaja_serializado_y_se_puede_volver_a_leer(orden, tecnico):
    """Lo que el telefono espeja tiene que ser USABLE, no solo presente.

    El telefono inserta sin pisar --para no perder un «leida» que no subio-- asi
    que si la fila nace a medias se queda a medias: la sincronizacion posterior NO
    la completa. De ahi que el push lleve el contenido entero.
    """
    _telefono(orden.org, tecnico[1], "tok-contenido")
    espia = _mandar(
        orden,
        tecnico,
        observacion="Falta la foto del empalme",
        requisitos=["foto_medicion", "foto_cto"],
    )

    contenido = json.loads(_cuerpos(espia)[0]["data"]["datos"])
    assert contenido["observacion"] == "Falta la foto del empalme"
    # Alfabetico, y no en el orden en que los pidio el supervisor:
    # `requerir_correccion` guarda `sorted(set(requisitos))`, que deduplica y
    # deja un orden estable entre corridas. Se afirma el orden REAL --no uno
    # conveniente-- porque esto es lo que el tecnico va a leer.
    assert contenido["rehacer"] == [
        "Fotografía de la caja CTO",
        "Fotografía de la medición",
    ]
    assert contenido["orden_numero"] == orden.numero


def test_a6_el_canal_de_android_es_el_que_declara_el_manifest(orden, tecnico):
    """Un id que no coincide no da error: Android manda el aviso a un canal
    «Miscellaneous» sin sonido, y el tecnico no se entera de nada."""
    _telefono(orden.org, tecnico[1], "tok-canal")
    espia = _mandar(orden, tecnico)

    android = _cuerpos(espia)[0]["android"]
    assert android["notification"]["channel_id"] == "avisos_de_campo"
    assert android["priority"] == "high"


def test_a7_el_push_registra_que_llego(orden, tecnico):
    _telefono(orden.org, tecnico[1], "tok-registro")
    _mandar(orden, tecnico)

    assert "push" in AvisoEnviado.objects.get(org=orden.org).canales


# --------------------------------------------------------------------------- #
# B. Privacidad
# --------------------------------------------------------------------------- #

def test_b1_el_push_no_lleva_nombre_direccion_ni_telefono_del_cliente(orden, tecnico):
    _telefono(orden.org, tecnico[1], "tok-pii")
    espia = _mandar(orden, tecnico, observacion="Falta la foto del empalme")

    entero = json.dumps(_cuerpos(espia)[0], ensure_ascii=False)
    for dato in ("Beatriz", "Pinzón", "Calle 50", "312 455 8901"):
        assert dato not in entero, dato


# --------------------------------------------------------------------------- #
# C. Un token muerto, y uno que solo falló
# --------------------------------------------------------------------------- #

def test_c1_unregistered_da_de_baja_el_telefono(orden, tecnico):
    telefono = _telefono(orden.org, tecnico[1], "tok-muerto")
    _mandar(orden, tecnico, respuestas=_unregistered())

    telefono.refresh_from_db()
    assert telefono.activo is False


def test_c2_un_token_muerto_no_cuenta_como_entregado(orden, tecnico):
    _telefono(orden.org, tecnico[1], "tok-muerto-2")
    _mandar(orden, tecnico, respuestas=_unregistered())

    assert "push" not in AvisoEnviado.objects.get(org=orden.org).canales


def test_c3_invalid_argument_tambien_da_de_baja(orden, tecnico):
    telefono = _telefono(orden.org, tecnico[1], "tok-mal-formado")
    respuesta = _Respuesta(
        400, {"error": {"details": [{"errorCode": "INVALID_ARGUMENT"}]}}
    )
    _mandar(orden, tecnico, respuestas=respuesta)

    telefono.refresh_from_db()
    assert telefono.activo is False


def test_c4_un_500_NO_da_de_baja_el_telefono(orden, tecnico):
    """LA OTRA DIRECCION, y la que hace daño silencioso.

    Un 500 es de Google, no del telefono. Darlo de baja por eso deja al tecnico
    sin avisos hasta que reinstale la aplicacion, y nadie va a relacionar las dos
    cosas.
    """
    telefono = _telefono(orden.org, tecnico[1], "tok-vivo")
    _mandar(orden, tecnico, respuestas=_Respuesta(500, {"error": {"status": "INTERNAL"}}))

    telefono.refresh_from_db()
    assert telefono.activo is True


def test_c5_un_404_sin_errorCode_no_da_de_baja(orden, tecnico):
    """Un 404 tambien lo devuelve un proyecto equivocado, y eso se arregla en la
    configuracion: dar de baja los telefonos escondería la causa."""
    telefono = _telefono(orden.org, tecnico[1], "tok-proyecto")
    _mandar(orden, tecnico, respuestas=_Respuesta(404, {"error": {"status": "NOT_FOUND"}}))

    telefono.refresh_from_db()
    assert telefono.activo is True


def test_c6_con_un_telefono_muerto_y_otro_vivo_solo_se_baja_el_muerto(
    orden, tecnico, companero
):
    AsignacionTrabajo.objects.create(
        orden=orden, profile=companero[1], rol="tecnico", es_principal=False
    )
    muerto = _telefono(orden.org, tecnico[1], "tok-aaa-muerto")
    vivo = _telefono(orden.org, companero[1], "tok-bbb-vivo")

    # El orden de la consulta no esta garantizado, asi que se contesta por token
    # en vez de por posicion: una prueba que depende del orden de un `filter`
    # falla el dia que alguien agregue un `order_by`.
    def _por_token(*a, **k):
        token = k["json"]["message"]["token"]
        return _unregistered() if token == "tok-aaa-muerto" else _ok()

    entorno, credencial, _ = _con_fcm(_ok())
    with entorno, credencial, mock.patch.object(
        push_fcm.requests, "post", side_effect=_por_token
    ):
        _devolver(orden, tecnico[1])

    muerto.refresh_from_db()
    vivo.refresh_from_db()
    assert (muerto.activo, vivo.activo) == (False, True)
    # Llego a uno: el aviso cumplio su proposito.
    assert "push" in AvisoEnviado.objects.get(org=orden.org).canales


# --------------------------------------------------------------------------- #
# D. A quien NO se le manda
# --------------------------------------------------------------------------- #

def test_d1_sin_credencial_no_se_hace_ni_una_llamada(orden, tecnico):
    """Afirmar sobre el EFECTO --cero llamadas-- y no sobre que haya un `if`.

    DOS MUTACIONES SOBREVIVEN A ESTA PRUEBA, Y NINGUNA ES UN HUECO
    --------------------------------------------------------------
    Medido el 04/10/2026: borrar el `if not push_fcm.esta_configurado()` de
    `avisos.py` la deja en verde, y borrar el `if credencial is None` de
    `push_fcm` tambien. Son DOS guardas para la misma garantia, y cada una
    alcanza sola: para que salga una llamada sin credencial hay que borrar las
    dos a la vez, que no es una edicion, son dos.

    La redundancia no es descuido. La de `avisos.py` esta para no pagar un parseo
    de clave RSA por telefono; la de `push_fcm` esta porque es la funcion que
    hace el POST y no puede depender de que la llamen bien. Lo que esta prueba
    afirma --cero llamadas-- sigue valiendo bajo cualquier edicion de una sola.
    """
    _telefono(orden.org, tecnico[1], "tok-sin-cred")

    with mock.patch.dict("os.environ", {}, clear=False) as _:
        import os

        os.environ.pop(push_fcm.VARIABLE, None)
        with mock.patch.object(push_fcm.requests, "post") as post:
            _devolver(orden, tecnico[1])

    post.assert_not_called()
    assert "push" not in AvisoEnviado.objects.get(org=orden.org).canales


def test_d2_el_telefono_de_OTRA_empresa_no_recibe(orden, tecnico, org_b):
    """El mismo perfil no existe en dos empresas, pero un token repetido si
    podria: el aislamiento lo da `org`, y es lo que se mide."""
    _telefono(orden.org, tecnico[1], "tok-propio")
    ajeno = DispositivoDeTecnico.objects.create(
        org=org_b, profile=tecnico[1], token="tok-ajeno", activo=True
    )

    espia = _mandar(orden, tecnico)

    tokens = {m["token"] for m in _cuerpos(espia)}
    assert tokens == {"tok-propio"}
    ajeno.refresh_from_db()
    assert ajeno.activo is True


def test_d6_dar_de_baja_un_token_muerto_no_toca_el_de_otra_empresa(
    orden, tecnico, org_b, companero
):
    """EL CASO QUE EXISTE PRECISAMENTE PORQUE EL BINARIO ES UNO SOLO.

    Todas las empresas instalan el mismo APK, asi que un tecnico que trabaja para
    dos ISPs tiene **el mismo token** registrado dos veces, una por empresa. Si la
    baja no filtrara por `org`, un `UNREGISTERED` en una empresa dejaria sin
    avisos al mismo telefono en la otra --y nadie relacionaria las dos cosas--.

    Medido: la mutacion «dar de baja sin filtrar por empresa» sobrevivia a
    `test_d2`, porque ahi ningun envio devuelve token muerto y el `update` nunca
    corria. Una prueba que no ejecuta la linea no la protege.
    """
    compartido = "tok-el-mismo-telefono"
    propio = _telefono(orden.org, tecnico[1], compartido)
    ajeno = DispositivoDeTecnico.objects.create(
        org=org_b, profile=companero[1], token=compartido, activo=True
    )

    _mandar(orden, tecnico, respuestas=_unregistered())

    propio.refresh_from_db()
    ajeno.refresh_from_db()
    assert (propio.activo, ajeno.activo) == (False, True)


def test_d3_un_telefono_desactivado_no_recibe(orden, tecnico):
    _telefono(orden.org, tecnico[1], "tok-activo")
    apagado = _telefono(orden.org, tecnico[1], "tok-apagado")
    apagado.activo = False
    apagado.save(update_fields=["activo"])

    espia = _mandar(orden, tecnico)

    assert {m["token"] for m in _cuerpos(espia)} == {"tok-activo"}


def test_d4_un_perfil_que_no_esta_asignado_no_recibe(orden, tecnico, companero):
    _telefono(orden.org, tecnico[1], "tok-asignado")
    _telefono(orden.org, companero[1], "tok-no-asignado")

    espia = _mandar(orden, tecnico)

    assert {m["token"] for m in _cuerpos(espia)} == {"tok-asignado"}


def test_d5_sin_telefonos_registrados_no_se_intenta(orden, tecnico):
    entorno, credencial, _ = _con_fcm(_ok())
    with entorno, credencial, mock.patch.object(push_fcm.requests, "post") as post:
        _devolver(orden, tecnico[1])

    post.assert_not_called()


# --------------------------------------------------------------------------- #
# E. No puede romper la devolucion
# --------------------------------------------------------------------------- #

def test_e1_si_FCM_explota_la_devolucion_ocurrio_igual(orden, tecnico):
    """El supervisor hizo la devolucion. Que el aviso no llegue es otro problema."""
    import requests as libreria

    _telefono(orden.org, tecnico[1], "tok-explota")
    entorno, credencial, _ = _con_fcm(_ok())
    with entorno, credencial, mock.patch.object(
        push_fcm.requests, "post", side_effect=libreria.ConnectionError("sin red")
    ):
        _devolver(orden, tecnico[1])

    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.REQUIERE_CORRECCION
    assert Notification.objects.filter(recipient=tecnico[1]).count() == 1


def test_e2_el_push_sale_FUERA_de_la_transaccion(orden, tecnico):
    """La decision congelada: ninguna transaccion abierta esperando a un tercero.

    Un viaje a Google con filas bloqueadas es el mismo defecto que el webhook, y
    peor: son N viajes, uno por telefono.
    """
    visto = {}

    def _espiar(*a, **k):
        from django.db import connection

        visto["en_transaccion"] = connection.in_atomic_block
        return _ok()

    _telefono(orden.org, tecnico[1], "tok-transaccion")
    entorno, credencial, _ = _con_fcm(_ok())
    with entorno, credencial, mock.patch.object(
        push_fcm.requests, "post", side_effect=_espiar
    ):
        _devolver(orden, tecnico[1])

    assert visto["en_transaccion"] is False


def test_e3_el_token_no_aparece_en_el_log(orden, tecnico, caplog):
    """Un token identifica un telefono y vive en el log mucho mas que en la base.

    SE REVISAN LOS CAMPOS DE `extra`, NO SOLO EL TEXTO
    --------------------------------------------------
    `caplog.text` trae el mensaje formateado y NADA de lo que viaja en `extra`,
    que es justamente como este proyecto pasa campos estructurados --y como se
    filtraria un token--. Medido: la mutacion «registrar el token en el log»
    sobrevivio a la version que solo miraba `caplog.text`. Por eso se recorre
    cada registro y todos sus valores.
    """
    import logging

    secreto = "tok-secretisimo-123456"
    _telefono(orden.org, tecnico[1], secreto)
    with caplog.at_level(logging.DEBUG):
        _mandar(orden, tecnico, respuestas=_unregistered())

    assert secreto not in caplog.text
    for registro in caplog.records:
        assert secreto not in registro.getMessage()
        for clave, valor in registro.__dict__.items():
            assert secreto not in str(valor), f"el token salio en {clave}"


# --------------------------------------------------------------------------- #
# F. La credencial: leerla de verdad
# --------------------------------------------------------------------------- #

def _credencial_de_verdad():
    """Una cuenta de servicio con la forma EXACTA que entrega Google.

    Con una clave RSA real: `from_service_account_info` la parsea, y una falsa
    pasaria la prueba sin probar que el archivo de Google se puede leer.
    """
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = llave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return {
        "type": "service_account",
        "project_id": "dexter-app-d4b93",
        "private_key_id": "abc123",
        "private_key": pem,
        "client_email": "fcm@dexter-app-d4b93.iam.gserviceaccount.com",
        "client_id": "1",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_f1_la_credencial_se_puede_pegar_como_JSON_en_una_variable():
    """Es la forma que importa: un contenedor recibe variables, no archivos."""
    datos = _credencial_de_verdad()
    with mock.patch.dict(
        "os.environ", {push_fcm.VARIABLE: json.dumps(datos)}, clear=False
    ):
        credencial, proyecto = push_fcm._cargar()

    assert credencial is not None
    assert proyecto == "dexter-app-d4b93"


def test_f2_la_credencial_tambien_se_puede_dar_como_ruta_a_un_archivo(tmp_path):
    ruta = tmp_path / "cuenta.json"
    ruta.write_text(json.dumps(_credencial_de_verdad()), encoding="utf-8")

    with mock.patch.dict("os.environ", {push_fcm.VARIABLE: str(ruta)}, clear=False):
        credencial, proyecto = push_fcm._cargar()

    assert credencial is not None
    assert proyecto == "dexter-app-d4b93"


def test_f3_una_credencial_sin_project_id_se_rechaza():
    """Sin proyecto la URL de FCM queda malformada y el 404 no señala la causa."""
    datos = _credencial_de_verdad()
    datos.pop("project_id")
    with mock.patch.dict(
        "os.environ", {push_fcm.VARIABLE: json.dumps(datos)}, clear=False
    ):
        credencial, proyecto = push_fcm._cargar()

    assert credencial is None
    assert proyecto == ""


def test_f4_una_credencial_rota_no_lanza_y_no_deja_la_clave_en_el_log(caplog):
    import logging

    with mock.patch.dict(
        "os.environ", {push_fcm.VARIABLE: '{"project_id": "x", "private_key"'}, clear=False
    ):
        with caplog.at_level(logging.DEBUG):
            credencial, _ = push_fcm._cargar()

    assert credencial is None
    assert "private_key" not in caplog.text


def test_f5_esta_configurado_dice_la_verdad_en_los_dos_sentidos():
    import os

    with mock.patch.dict("os.environ", {}, clear=False):
        os.environ.pop(push_fcm.VARIABLE, None)
        assert push_fcm.esta_configurado() is False

    with mock.patch.dict("os.environ", {push_fcm.VARIABLE: "   "}, clear=False):
        # Una variable declarada y vacia es el caso real de un `.env` a medio
        # llenar, y tiene que contar como «no configurado».
        assert push_fcm.esta_configurado() is False

    with mock.patch.dict("os.environ", {push_fcm.VARIABLE: "{}"}, clear=False):
        assert push_fcm.esta_configurado() is True


# --------------------------------------------------------------------------- #
# G. El registro del telefono
# --------------------------------------------------------------------------- #

def test_g2_un_telefono_dado_de_baja_vuelve_a_servir_si_se_registra_otra_vez(
    org_a, user_client, user_profile
):
    """El caso real, y el que se rompe facil.

    A FCM se le cae el token, esto lo da de baja, y el tecnico abre la app otra
    vez. Si la baja fuera definitiva se quedaria sin avisos para siempre y nadie
    relacionaria las dos cosas. Que el registro *reviva* la fila es lo que cierra
    el ciclo.

    Que registrar dos veces no duplique ya se mide en
    `test_avisos_al_tecnico.py::test_m`; aca se mide lo otro.
    """
    telefono = _telefono(org_a, user_profile, "tok-revive")
    telefono.activo = False
    telefono.save(update_fields=["activo"])

    r = user_client.post(
        "/api/campo/dispositivo/",
        {"token": "tok-revive", "plataforma": "android"},
        format="json",
    )
    assert r.status_code in (200, 201), r.data

    telefono.refresh_from_db()
    assert telefono.activo is True


def test_g3_el_servicio_de_avisos_llama_al_proveedor_una_vez_por_telefono(
    orden, tecnico
):
    """Dos telefonos de la misma persona --el de la empresa y el propio-- reciben
    los dos. Un `break` despues del primero dejaria la mitad sin avisar."""
    _telefono(orden.org, tecnico[1], "tok-uno-de-dos")
    _telefono(orden.org, tecnico[1], "tok-dos-de-dos")

    espia = _mandar(orden, tecnico)

    assert {m["token"] for m in _cuerpos(espia)} == {
        "tok-uno-de-dos",
        "tok-dos-de-dos",
    }


def test_g4_el_servicio_no_toca_el_telefono_cuando_no_hay_devolucion(orden, tecnico):
    """Una guarda contra el error opuesto: avisar de mas.

    `_notificar_a_telefonos` es publico dentro del modulo y nada impide llamarlo
    con una lista vacia de perfiles; tiene que contestar `False` sin salir a la
    red.
    """
    _telefono(orden.org, tecnico[1], "tok-nadie")
    entorno, credencial, _ = _con_fcm(_ok())
    with entorno, credencial, mock.patch.object(push_fcm.requests, "post") as post:
        llego = servicio_avisos._notificar_a_telefonos(
            org=orden.org, perfiles=[], titulo="x", texto="y", enlace="/ot/1"
        )

    assert llego is False
    post.assert_not_called()
