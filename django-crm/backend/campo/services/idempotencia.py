# -*- coding: utf-8 -*-
"""Servicio de control de idempotencia para mutaciones offline y reintentos móviles."""

from __future__ import annotations

import hashlib
import json
from functools import wraps
from django.db import IntegrityError, OperationalError, transaction
from rest_framework import status
from rest_framework.response import Response

from campo.models import MutacionIdempotente


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
            datos_respuesta = response.data if hasattr(response, "data") else None
            MutacionIdempotente.objects.filter(pk=mutacion.pk).update(
                estado=MutacionIdempotente.COMPLETADA,
                status_code=status_code,
                respuesta_json=datos_respuesta,
            )
        else:
            # Fallo de servidor: no cachear
            MutacionIdempotente.objects.filter(pk=mutacion.pk).delete()

        return response

    return wrapper
