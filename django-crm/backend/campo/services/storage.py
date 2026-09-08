# -*- coding: utf-8 -*-
"""Abstracción desacoplada de almacenamiento de evidencias de campo."""

from __future__ import annotations

import os
import uuid

from django.conf import settings


class CampoStorage:
    """Proveedor base desacoplado para subida y lectura segura de evidencias.

    El cliente movil consume 'upload.url' y no sabe que hay debajo. Hoy hay un
    solo backend -- el disco local bajo MEDIA_ROOT, con la subida atendida por
    la propia API -- y manana puede haber S3, R2 o Supabase Storage emitiendo
    una URL prefirmada al proveedor. Lo unico que la app necesita saber es que
    hace un PUT contra lo que le devolvieron.
    """

    # Limites de la subida. Viven aca, junto al resto del almacenamiento, y no
    # en la vista: son propiedad de lo que se puede guardar, no de una ruta.
    MAX_BYTES = getattr(settings, "CAMPO_EVIDENCIA_MAX_BYTES", 25 * 1024 * 1024)
    MIME_PERMITIDOS = getattr(settings, "CAMPO_EVIDENCIA_MIME_PERMITIDOS", (
        "image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf",
    ))

    @classmethod
    def generar_storage_key(cls, org_id: str, orden_id: str, requisito_id: str, nombre_original: str) -> str:
        ext = os.path.splitext(nombre_original)[1].lower() or ".jpg"
        unique_id = uuid.uuid4().hex[:12]
        return f"campo/{org_id}/{orden_id}/{requisito_id}_{unique_id}{ext}"

    @classmethod
    def descriptor_subida(cls, evidencia_id) -> dict:
        """
        Como sube el cliente ESTA evidencia.

        Indexado por 'evidencia_id' y NO por la storage_key. La version
        anterior emitia '/api/campo/evidencias/upload-directo/?key=<ruta>', que
        ademas de no existir (nunca se registro la ruta, asi que el circuito
        quedaba cortado) le habria pedido al servidor escribir donde dijera el
        cliente: una ruta arbitraria por query string, con el path traversal
        como problema a resolver despues.

        Con el id, la storage_key la resuelve el servidor leyendo la fila. No
        hay ruta que sanear porque no hay ruta que el cliente pueda proponer.

        Cuando el backend sea S3/R2, este metodo devuelve la URL prefirmada del
        proveedor y la vista local deja de existir; la app no cambia.
        """
        return {
            "method": "PUT",
            "url": f"/api/campo/evidencias/{evidencia_id}/subir/",
            "expires_in": 900,
        }

    @classmethod
    def ruta_absoluta(cls, storage_key: str) -> str | None:
        """
        Donde vive el archivo en disco, o None si la key se sale de MEDIA_ROOT.

        La key sale de la base y no del cliente, asi que esto es defensa en
        profundidad: si alguna vez una fila quedara con '../..' escrito, el
        archivo no se escribe ni se lee fuera del arbol de medios.
        """
        if not storage_key:
            return None
        raiz = os.path.realpath(settings.MEDIA_ROOT)
        destino = os.path.realpath(os.path.join(raiz, storage_key))
        if destino != raiz and not destino.startswith(raiz + os.sep):
            return None
        return destino

    @classmethod
    def guardar(cls, storage_key: str, contenido: bytes) -> bool:
        """Escribe el binario exactamente donde 'verify_upload' lo va a buscar."""
        destino = cls.ruta_absoluta(storage_key)
        if destino is None:
            return False
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as f:
            f.write(contenido)
        return True

    @classmethod
    def verify_upload(cls, storage_key: str) -> bool:
        """Comprueba que el archivo exista en el backend de storage."""
        destino = cls.ruta_absoluta(storage_key)
        return bool(destino) and os.path.exists(destino)

    @classmethod
    def create_download_url(cls, storage_key: str) -> str:
        """Emite URL segura de descarga o visualización."""
        if not storage_key:
            return ""
        return f"/media/{storage_key}"
