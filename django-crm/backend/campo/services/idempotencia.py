# -*- coding: utf-8 -*-
"""Servicio de control de idempotencia para mutaciones offline y reintentos móviles."""

from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, OperationalError, transaction
from rest_framework import status
from rest_framework.response import Response

from campo.models import MutacionIdempotente

logger = logging.getLogger(__name__)


def calcular_hash_canonico(cuerpo: Any) -> str:
    """Calcula el hash SHA256 sobre una serialización JSON canónica (claves ordenadas, sin espacios)."""
    if cuerpo is None or cuerpo == "" or cuerpo == b"":
        canonica = "{}"
    elif isinstance(cuerpo, (dict, list)):
        canonica = json.dumps(cuerpo, sort_keys=True, separators=(",", ":"))
    elif isinstance(cuerpo, (bytes, bytearray)):
        try:
            parsed = json.loads(cuerpo.decode("utf-8"))
            canonica = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        except Exception:
            canonica = cuerpo.decode("utf-8", errors="ignore")
    else:
        canonica = str(cuerpo)

    return hashlib.sha256(canonica.encode("utf-8")).hexdigest()


#  EL SOBRE DEL REINTENTO DEGRADADO  --  06/11/2026, auditoria de frontera.
#
#  Guardar `None` aca parecia inocuo y no lo era: medido, el reintento salia
#  `Response(None, 201)`, que DRF renderiza como CERO bytes y sin
#  Content-Type. `api-helpers.js` hace `await response.json()` sobre eso y
#  lanza SyntaxError, que no trae `.status`, asi que la pantalla de Despacho
#  caia en su `fail(..., 502)`: el MISMO rojo sobre un trabajo que si salio
#  que este arreglo vino a matar, corrido del primer intento al reintento. La
#  app de campo lo sufria distinto: `resultados is! List` -> la cola marca
#  fallo y reintenta para siempre algo que el servidor ya aplico.
#
#  Un cuerpo honesto cuesta lo mismo y dice la verdad: la operacion se aplico,
#  la copia no esta. El frontend lee `r?.orden?.numero` -> undefined y escribe
#  «Orden despachada» sin numero, que es exacto.
SIN_COPIA = {
    "idempotencia": "RESPUESTA_NO_GUARDADA",
    "detalle": ("La operación se aplicó. No se pudo guardar la copia de la "
                "respuesta, así que este reintento no trae el detalle."),
}


class _Encoder(DjangoJSONEncoder):
    """DjangoJSONEncoder que no se rinde: lo que no sabe, lo escribe como texto.

    `default()` solo se llama para lo que el encoder base NO resolvio, asi que
    datetime, date, time, timedelta, Decimal, UUID y Promise siguen saliendo
    con su forma de siempre.
    """

    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def _para_guardar(datos):
    """
    `response.data` de DRF, listo para un JSONField.

    EL DEFECTO QUE ESTO CIERRA  --  reproducido el 06/11/2026
    ---------------------------------------------------------
    Despachar CON fecha devolvia 500 con la orden ya creada y el aviso ya en
    el telefono del tecnico:

        TypeError: Object of type datetime is not JSON serializable

    `response.data` todavia trae objetos Python. El renderer HTTP sabe
    convertirlos --por eso la respuesta viajaba bien-- pero
    `MutacionIdempotente.respuesta_json` es un JSONField sin encoder, y
    `json.dumps` no sabe. Un SerializerMethodField no pasa por la conversion
    de DRF, asi que basta UNO que devuelva un datetime crudo para tumbar la
    operacion entera: `_compromiso` devuelve seis.

    Va aca y no en ese serializer a proposito. El decorador envuelve a todos
    los endpoints de mutacion, y la regla que hace falta es una sola: lo que
    se guarda para poder repetir una respuesta NO puede tumbar la operacion
    que ya tuvo efecto. Arreglar un serializer deja la misma bomba armada
    para el proximo.

    DjangoJSONEncoder cubre datetime, date, time, timedelta, Decimal, UUID y
    Promise, que es lo que un serializer de DRF puede dejar pasar. El
    `json.loads` de vuelta es lo que hace que lo guardado sea JSON de verdad y
    no un texto, para que releerlo devuelva un objeto.

    SE DEGRADA EL CAMPO, NO EL CUERPO (auditoria de frontera, 06/11/2026).
    `DjangoJSONEncoder` a secas es todo-o-nada: un solo valor que no conoce
    --bytes, un set, un objeto de dominio-- descartaba la respuesta ENTERA, y
    un cuerpo vacio le miente al que reintenta tanto como un error. `_Encoder`
    cae a `str(o)` para lo que no sabe, asi que se pierde la forma de UN campo
    y se conserva todo lo demas: el numero de la orden, que es lo que la
    pantalla necesita.

    Importa porque esta clase de defecto ya reincidio tres veces sola: un UUID
    en M03-F-B, re-roto despues, y ahora los datetime.

    None solo si ni asi se puede: quien llama decide, y lo que decide es seguir.
    """
    if datos is None:
        return None
    try:
        return json.loads(json.dumps(datos, cls=_Encoder))
    except (TypeError, ValueError):
        return None


def manejar_idempotencia(vista_func):
    """
    Decorador para endpoints que aceptan la cabecera 'Idempotency-Key'.
    Garantiza una sola ejecución atómica ante reintentos o concurrencia.
    """

    @wraps(vista_func)
    def wrapper(view_instance, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        if not key:
            # Si no envía Idempotency-Key, procesa normalmente
            return vista_func(view_instance, request, *args, **kwargs)

        key = str(key).strip()
        org = getattr(request, "org", None)
        if not org:
            return Response(
                {"error": "FALTA_CONTEXTO_ORG", "detalle": "No hay organización autenticada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload_a_hashear = request.data if hasattr(request, "data") else request.body
        request_hash = calcular_hash_canonico(payload_a_hashear)
        method = request.method.upper()
        endpoint = request.path

        # 1. Chequeo y bloqueo atómico
        try:
            with transaction.atomic():
                existente = (
                    MutacionIdempotente.objects.select_for_update()
                    .filter(org=org, idempotency_key=key)
                    .first()
                )

                if existente:
                    # Si el payload, método o endpoint difiere con la misma clave: CONFLICTO
                    if (
                        existente.request_hash != request_hash
                        or existente.http_method != method
                        or existente.endpoint != endpoint
                    ):
                        return Response(
                            {
                                "error": "IDEMPOTENCY_KEY_REUSED",
                                "detalle": "La misma Idempotency-Key fue reutilizada con un payload o método diferente.",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    if existente.estado == MutacionIdempotente.PROCESANDO:
                        return Response(
                            {
                                "error": "OPERACION_EN_CURSO",
                                "detalle": "La operación con esta clave se está procesando actualmente.",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    if existente.estado == MutacionIdempotente.COMPLETADA:
                        resp = Response(
                            existente.respuesta_json,
                            status=existente.status_code or status.HTTP_200_OK,
                        )
                        resp["Idempotent-Replay"] = "true"
                        return resp

                # Crear registro en estado PROCESANDO
                mutacion = MutacionIdempotente.objects.create(
                    org=org,
                    idempotency_key=key,
                    http_method=method,
                    endpoint=endpoint,
                    request_hash=request_hash,
                    estado=MutacionIdempotente.PROCESANDO,
                )
        except (IntegrityError, OperationalError):
            # Carrera de concurrencia: otra petición paralela acaba de crear o bloquear el registro
            return Response(
                {
                    "error": "OPERACION_EN_CURSO",
                    "detalle": "Conflicto concurrente: la operación ya está siendo procesada.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 2. Ejecutar la vista de negocio
        try:
            response = vista_func(view_instance, request, *args, **kwargs)
        except Exception:
            # Si la vista lanza excepción no capturada, marcar como fallida y relanzar
            MutacionIdempotente.objects.filter(pk=mutacion.pk).delete()
            raise

        # 3. Almacenar resultado completado
        status_code = getattr(response, "status_code", 200)
        # Solo almacenar éxito o respuestas de negocio válidas (evita cachear errores 500)
        if status_code < 500:
            crudos = response.data if hasattr(response, "data") else None
            datos_respuesta = _para_guardar(crudos)
            #  GUARDAR NO PUEDE TUMBAR LO QUE YA PASO. Hasta el 06/11/2026
            #  este update corria crudo: un datetime en la respuesta lanzaba
            #  TypeError DESPUES de que la orden estaba creada y el tecnico
            #  avisado, y quien despachaba veia rojo sobre un trabajo que ya
            #  habia salido. La operacion ya tuvo efecto: lo unico que se
            #  puede perder a esta altura es la copia para repetirla.
            #
            #  Y se marca COMPLETADA aunque la copia no se pueda guardar.
            #  Dejarla en PROCESANDO --lo que pasaba al relanzar-- condena a
            #  esa clave a contestar 409 «la operacion se esta procesando»
            #  para siempre, porque ya no hay nadie que la vaya a terminar:
            #  el supervisor quedaba trabado sin salida. Repetir una respuesta
            #  vacia es peor que no tenerla, pero mucho mejor que repetir el
            #  efecto o trabar la clave.
            #  CADA INTENTO EN SU PROPIO SAVEPOINT. Una consulta que falla
            #  dentro de una transaccion la deja ROTA, y Django rechaza toda
            #  consulta posterior con TransactionManagementError: sin el
            #  `atomic()` de aca, el respaldo de abajo no podia correr.
            #
            #  DONDE HACE FALTA, medido el 06/11/2026: hoy lo exige la
            #  topologia de PRUEBA --`pytest.mark.django_db` envuelve cada
            #  prueba en un atomic--, no la de produccion: `ATOMIC_REQUESTS`
            #  no esta definido en `crm/settings.py` y es False en
            #  `test_settings.py`, asi que en el servidor no hay transaccion
            #  exterior en este punto. Se deja puesto igual: es la defensa
            #  correcta el dia que alguien active ATOMIC_REQUESTS, y entonces
            #  el defecto volveria sin que nada lo señale.
            try:
                with transaction.atomic():
                    MutacionIdempotente.objects.filter(pk=mutacion.pk).update(
                        estado=MutacionIdempotente.COMPLETADA,
                        status_code=status_code,
                        respuesta_json=datos_respuesta,
                    )
            except Exception as exc:                             # noqa: BLE001
                #  EL MENSAJE LLEVA LOS DATOS ADENTRO, no en `extra`: medido
                #  el 06/11/2026, `crm/settings.py::LOGGING` no define logger
                #  raiz ni `campo`, asi que el record cae en `lastResort` --
                #  stderr, solo el mensaje-- y todo `extra` se pierde. Un log
                #  sin endpoint ni clave no sirve justo cuando alguien tiene
                #  que explicar por que el supervisor vio lo que vio.
                logger.warning(
                    "idempotencia: no se pudo guardar la respuesta "
                    "(endpoint=%s status=%s clave=%s error=%s)",
                    endpoint, status_code, mutacion.pk, type(exc).__name__,
                    exc_info=True)
                try:
                    with transaction.atomic():
                        MutacionIdempotente.objects.filter(
                            pk=mutacion.pk).update(
                            estado=MutacionIdempotente.COMPLETADA,
                            status_code=status_code,
                            respuesta_json=SIN_COPIA,
                        )
                except Exception as exc2:                        # noqa: BLE001
                    #  Los DOS intentos fallaron: la fila queda 'procesando' y
                    #  esa clave va a contestar 409 hasta que alguien la mire.
                    #  Pasa si lo que falla es la base misma, no el contenido.
                    logger.warning(
                        "idempotencia: la clave queda SIN COMPLETAR y va a "
                        "dar 409 (endpoint=%s clave=%s error=%s)",
                        endpoint, mutacion.pk, type(exc2).__name__,
                        exc_info=True)
        else:
            # Fallo de servidor: no cachear
            MutacionIdempotente.objects.filter(pk=mutacion.pk).delete()

        return response

    return wrapper
