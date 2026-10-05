# -*- coding: utf-8 -*-
"""El golpecito en el hombro: una notificacion al telefono, por FCM HTTP v1.

POR QUE FCM Y NO OTRA COSA
--------------------------
En Android no hay alternativa. Un telefono con la app cerrada solo despierta por
el canal del sistema operativo, y en Android ese canal es Firebase Cloud
Messaging. Supabase no lo reemplaza --sus Realtime y Edge Functions necesitan un
socket abierto, o sea la app en primer plano, que es justo el caso en que el
tecnico ya esta mirando--. Lo mismo vale para WebSockets, SSE o un `poll`: todos
piden proceso vivo.

POR QUE LA CREDENCIAL ES DE LA PLATAFORMA Y NO DEL TENANT
---------------------------------------------------------
Esto NO es una excepcion a la regla de CLAUDE.md §3.3. La credencial de FCM no
identifica a una empresa: identifica al **binario** de la app. Hay un solo APK
--`com.dexter.campo`-- y todos los tecnicos de todas las empresas lo instalan;
el aislamiento por empresa lo da `DispositivoDeTecnico.org`, que es una fila por
telefono. Poner la credencial en `tenant_config` seria una perilla que nadie
puede girar: dos empresas no pueden tener proyectos de Firebase distintos para
el mismo paquete de Android.

El dia que un ISP quiera su app con su marca --otro `applicationId`, otra ficha
en Play-- eso cambia, y entonces si es configuracion por empresa. Ese dia la
decision se toma con ese caso adelante, no antes.

LO QUE ESTO NO PROMETE
----------------------
`aceptado != entregado != leido`, igual que WhatsApp. Un 200 de FCM significa
que Google acepto el mensaje, no que el telefono lo mostro: puede estar sin
senal, con la bateria en ahorro o con los avisos apagados. Por eso la
notificacion **tambien** se escribe en la plataforma (`common/notifications.py`)
dentro de la transaccion, y esa es la que vale como registro. El push es la
capa que avisa sin abrir la app, nunca la fuente de verdad.

UN TOKEN MUERTO SE DA DE BAJA, NO SE REINTENTA
----------------------------------------------
Un token deja de servir al reinstalar, al limpiar datos o por decision de
Google, y FCM lo dice con `UNREGISTERED`. Si no se diera de baja, cada aviso
futuro pagaria un viaje a Google para que lo rechace, y `AvisoEnviado` contaria
intentos que no podian funcionar. Por eso esta funcion devuelve TRES resultados
y no un booleano.

PRIVACIDAD
----------
El texto que llega aca ya paso por quien lo redacto (`campo/avisos.py`): no
lleva nombre, direccion ni telefono del cliente. Esta funcion no agrega nada:
manda el titulo, el texto y el enlace interno a la orden, y nada mas. El `token`
no se registra en el log ni completo ni truncado.
"""

from __future__ import annotations

import json
import logging
import os
import threading

from django.utils import timezone

import requests
from google.auth.transport.requests import Request as PedidoDeGoogle
from google.oauth2 import service_account

log = logging.getLogger(__name__)

#: De donde sale la credencial. Puede ser la ruta a un archivo JSON o el JSON
#: completo pegado como valor. Las dos formas existen porque un contenedor en
#: Dokploy recibe variables, no archivos; y un desarrollador en su maquina
#: prefiere un archivo que no termina en el historial del shell.
VARIABLE = "FCM_CUENTA_DE_SERVICIO"

ALCANCE = "https://www.googleapis.com/auth/firebase.messaging"
SEGUNDOS_DE_ESPERA = 10

#: Tiene que coincidir con `default_notification_channel_id` del
#: AndroidManifest.xml de la app. Si no coincide, Android no falla: mete el
#: aviso en un canal "Miscellaneous" sin sonido y el tecnico no se entera.
CANAL_ANDROID = "avisos_de_campo"

#: Los tres resultados posibles. Son cadenas y no un Enum porque cruzan al log y
#: a una comparacion en `avisos.py`, y ahi un Enum solo agrega ceremonia.
ENTREGADO = "entregado"
TOKEN_MUERTO = "token_muerto"
FALLO = "fallo"

_candado = threading.Lock()
_credencial = None
_proyecto = ""


def esta_configurado() -> bool:
    """Si hay credencial. Se pregunta ANTES de intentar, para no mentir en el log.

    Sin credencial el sistema sigue funcionando entero: la notificacion se
    escribe en la plataforma, el canal externo publica, y lo unico que falta es
    el golpecito en el hombro. Fallar ruidoso aca apagaria una devolucion por no
    tener una variable de entorno, y eso es exactamente lo que el encabezado de
    `avisos.py` dice que no puede pasar.
    """
    return bool((os.environ.get(VARIABLE) or "").strip())


def _cargar():
    """La credencial y el proyecto, una sola vez por proceso.

    Se cachea porque `from_service_account_info` parsea y valida una clave RSA en
    cada llamada, y esto corre una vez por telefono notificado. El refresco del
    token de acceso lo maneja la propia credencial: dura una hora y se renueva
    sola cuando `refresh` la encuentra vencida.
    """
    global _credencial, _proyecto
    if _credencial is not None:
        return _credencial, _proyecto

    with _candado:
        # Re-chequeo adentro del candado: dos hilos pueden haber pasado el if de
        # arriba al mismo tiempo, y parsear la clave dos veces no rompe nada pero
        # tampoco sirve.
        if _credencial is not None:
            return _credencial, _proyecto

        crudo = (os.environ.get(VARIABLE) or "").strip()
        if not crudo:
            return None, ""

        try:
            if crudo.startswith("{"):
                datos = json.loads(crudo)
            else:
                with open(crudo, "r", encoding="utf-8") as f:
                    datos = json.load(f)
            credencial = service_account.Credentials.from_service_account_info(
                datos, scopes=[ALCANCE]
            )
        except (OSError, ValueError, KeyError, TypeError) as e:
            # El contenido NO se registra: es una clave privada. Solo el tipo de
            # error, que ya distingue "no existe el archivo" de "el JSON esta
            # cortado" de "le falta private_key".
            log.error("fcm_credencial_invalida", extra={"clase": type(e).__name__})
            return None, ""

        _credencial = credencial
        _proyecto = str(datos.get("project_id") or "")
        if not _proyecto:
            log.error("fcm_credencial_sin_proyecto")
            _credencial = None
            return None, ""
        return _credencial, _proyecto


def _reiniciar_para_pruebas() -> None:
    """Olvida la credencial cacheada.

    Existe para las pruebas: sin esto, la primera que configura una credencial se
    la deja puesta a todas las que corren despues en el mismo proceso, y una
    prueba que afirma «sin credencial no sale nada» pasaria usando la de otra.
    """
    global _credencial, _proyecto
    with _candado:
        _credencial = None
        _proyecto = ""


def mandar_a_un_telefono(
    token: str,
    titulo: str,
    texto: str,
    enlace: str,
    *,
    aviso_id: str = "",
    verbo: str = "",
    contenido: dict | None = None,
) -> str:
    """Un mensaje a un telefono. Devuelve ENTREGADO, TOKEN_MUERTO o FALLO.

    El `enlace` viaja en `data` y no en `notification` a proposito: `data` es lo
    que la app recibe entero --tambien con la app cerrada, cuando el usuario toca
    el aviso-- y es lo que le permite abrir la orden en vez de la pantalla de
    inicio. En `notification` Android solo mira titulo y cuerpo.

    `aviso_id` es el id de la notificacion de ESA persona en la plataforma. Con
    el, el aviso que llega por push y el que despues baja la sincronizacion son
    la misma fila; sin el, el telefono mostraria la misma notificacion dos veces
    --una por push, otra al sincronizar-- y la segunda sin leer. Se manda vacio
    cuando no hay fila que espejar, y entonces el telefono solo lo muestra.
    """
    credencial, proyecto = _cargar()
    if credencial is None:
        log.info("fcm_sin_credencial")
        return FALLO

    cuerpo = {
        "message": {
            "token": token,
            "notification": {"title": titulo, "body": texto},
            # Todo valor tiene que ser CADENA. FCM rechaza el mensaje entero
            # con un 400 si hay un numero, una lista o un nulo aca, y por eso
            # `contenido` --que trae listas y enteros-- viaja serializado.
            "data": {
                "enlace": enlace or "",
                "clase": "aviso_de_campo",
                "id": aviso_id or "",
                "verbo": verbo or "",
                "titulo": titulo or "",
                "creada_en": timezone.now().isoformat(),
                "datos": json.dumps(contenido or {}, ensure_ascii=False),
            },
            "android": {
                # `high` para que llegue con el telefono en reposo. Un aviso de
                # trabajo devuelto que aparece dos horas tarde no sirve: el
                # tecnico ya se fue del barrio.
                "priority": "high",
                "notification": {"channel_id": CANAL_ANDROID},
            },
        }
    }

    try:
        credencial.refresh(PedidoDeGoogle())
    except Exception as e:  # noqa: BLE001 -- la libreria lanza de todo
        log.warning("fcm_token_de_acceso_fallo", extra={"clase": type(e).__name__})
        return FALLO

    try:
        r = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{proyecto}/messages:send",
            json=cuerpo,
            headers={"Authorization": f"Bearer {credencial.token}"},
            timeout=SEGUNDOS_DE_ESPERA,
        )
    except requests.RequestException as e:
        log.warning("fcm_no_alcanzado", extra={"clase": type(e).__name__})
        return FALLO

    if 200 <= r.status_code < 300:
        return ENTREGADO

    if _es_token_muerto(r):
        log.info("fcm_token_muerto")
        return TOKEN_MUERTO

    # El cuerpo de error de FCM no trae datos nuestros, pero tampoco hace falta
    # entero: el codigo mas el `status` de Google ya dicen que hacer.
    log.warning("fcm_rechazado", extra={"codigo": r.status_code})
    return FALLO


def _es_token_muerto(respuesta) -> bool:
    """Si FCM dice que este token no va a servir nunca mas.

    Se mira el `errorCode` de los detalles y NO solo el 404, porque FCM devuelve
    400 INVALID_ARGUMENT para un token con la forma mal --que tampoco hay que
    reintentar-- y 404 NOT_FOUND tambien para un proyecto equivocado, que si hay
    que arreglar en vez de dar de baja al telefono.
    """
    try:
        error = (respuesta.json() or {}).get("error") or {}
    except ValueError:
        return False

    for detalle in error.get("details") or []:
        if detalle.get("errorCode") in {"UNREGISTERED", "INVALID_ARGUMENT"}:
            return True
    return False
