# -*- coding: utf-8 -*-
"""Abstracción desacoplada de almacenamiento de evidencias de campo."""

from __future__ import annotations

import os
import uuid
from django.conf import settings


class CampoStorage:
    """Proveedor base desacoplado para subida y lectura segura de evidencias."""

    @classmethod
    def generar_storage_key(cls, org_id: str, orden_id: str, requisito_id: str, nombre_original: str) -> str:
        ext = os.path.splitext(nombre_original)[1].lower() or ".jpg"
        unique_id = uuid.uuid4().hex[:12]
        return f"campo/{org_id}/{orden_id}/{requisito_id}_{unique_id}{ext}"

    @classmethod
    def create_upload(cls, org_id: str, orden_id: str, requisito_id: str, nombre_original: str) -> dict:
        """
        Emite la storage_key y la URL de subida.
        En entorno local/dev apunta a la ruta de subida directa de Django;
        en producción con S3/Supabase Storage emite la presigned PUT URL.
        """
        key = cls.generar_storage_key(org_id, orden_id, requisito_id, nombre_original)
        # Para el MVP servimos endpoint directo de subida con token de subida
        upload_url = f"/api/campo/evidencias/upload-directo/?key={key}"
        return {
            "storage_key": key,
            "upload": {
                "method": "PUT",
                "url": upload_url,
                "expires_in": 900,
            },
        }

    @classmethod
    def upload_para_key(cls, storage_key: str) -> dict:
        """
        Reemite la URL de subida para una storage_key QUE YA EXISTE.

        'create_upload' genera siempre una key nueva (uuid), asi que servia
        para la primera vez y no para renovar: una URL firmada vence a los 15
        minutos (expires_in), y un movil que perdio conexion, quedo sin bateria
        o se guardo para "cuando haya senal" vuelve con la suya vencida. Sin
        esto, el unico camino era pedir otra evidencia -- y eso reemplazaba la
        storage_key, dejando huerfano lo que ya estuviera subido.

        Renovar sobre la MISMA key es lo que permite reintentar sin duplicar ni
        perder nada.
        """
        return {
            "storage_key": storage_key,
            "upload": {
                "method": "PUT",
                "url": f"/api/campo/evidencias/upload-directo/?key={storage_key}",
                "expires_in": 900,
            },
        }

    @classmethod
    def verify_upload(cls, storage_key: str) -> bool:
        """Comprueba que el archivo exista en el backend de storage."""
        if not storage_key:
            return False
        ruta = os.path.join(settings.MEDIA_ROOT, storage_key)
        return os.path.exists(ruta)

    @classmethod
    def create_download_url(cls, storage_key: str) -> str:
        """Emite URL segura de descarga o visualización."""
        if not storage_key:
            return ""
        return f"/media/{storage_key}"
