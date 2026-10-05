# -*- coding: utf-8 -*-
"""Pedir material a bodega, desde el terreno."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.models import MaterialCatalogo, OrdenTrabajo, PedidoDeMaterial
from campo.permissions import IsCampoAuthenticated
from campo.services.avisos import avisar_pedido_de_material


class PedidosDeMaterialView(APIView):
    """``GET`` los pedidos de este tecnico. ``POST`` uno nuevo.

    EL CICLO QUE CIERRA
    -------------------
    El tecnico se queda sin conectores en la tercera instalacion y hasta hoy la
    aplicacion no tenia nada que ofrecerle: sacaba el otro telefono y escribia
    al grupo. Ahora pide desde donde ve lo que le queda.

    SOLO VE LOS SUYOS, y no es una restriccion de permisos sino de proposito:
    esta pantalla contesta «¿pedi esto o no?». Lo que bodega necesita --todos
    los pedidos de la empresa-- se atiende por el aviso que sale al crearlo.

    IDEMPOTENTE, Y HACE FALTA. El telefono reenvia sin señal, y dos pedidos
    iguales le harian pensar a bodega que hacen falta cuarenta conectores cuando
    hacen falta veinte.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        pedidos = (
            PedidoDeMaterial.objects.filter(
                org=request.org, profile=request.profile
            )
            .select_related("material", "orden")[:50]
        )
        return Response({"pedidos": [_como_se_ve(p) for p in pedidos]})

    def post(self, request):
        clave = (request.data.get("idempotency_key") or "").strip()
        if not clave:
            return Response(
                {"detail": "Falta la clave de idempotencia del pedido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        material = _material_de(request)
        if material is None:
            # 404 y no 403: una respuesta que distinga «no existe» de «no es
            # tuyo» le diria a cualquiera que ese material existe en otra
            # empresa.
            return Response(
                {"detail": "Ese material no existe en esta empresa."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            cantidad = Decimal(str(request.data.get("cantidad")))
        except (InvalidOperation, TypeError):
            return Response(
                {"detail": "La cantidad no es un número."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if cantidad <= 0:
            # Pedir cero o menos no es un pedido. Aceptarlo llenaria la lista de
            # bodega de filas que no piden nada.
            return Response(
                {"detail": "La cantidad tiene que ser mayor que cero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orden = None
        orden_id = (request.data.get("orden") or "").strip()
        if orden_id:
            orden = OrdenTrabajo.objects.filter(
                org=request.org, id=orden_id
            ).first()
            if orden is None:
                return Response(
                    {"detail": "Esa orden no existe en esta empresa."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            with transaction.atomic():
                pedido = PedidoDeMaterial.objects.create(
                    org=request.org,
                    profile=request.profile,
                    material=material,
                    cantidad=cantidad,
                    motivo=(request.data.get("motivo") or "").strip()[:255],
                    orden=orden,
                    idempotency_key=clave,
                )
        except IntegrityError:
            # Ya estaba: el telefono reenvio. Se devuelve el que hay, no un
            # error -- para la cola de la app esto TIENE que verse como exito o
            # lo reintenta para siempre.
            pedido = PedidoDeMaterial.objects.get(
                org=request.org, idempotency_key=clave
            )
            return Response(_como_se_ve(pedido), status=status.HTTP_200_OK)

        # El aviso va DESPUES del commit, como todo lo que sale del sistema: si
        # el pedido se deshace, bodega no se entera de algo que no paso.
        avisar_pedido_de_material(pedido)
        return Response(_como_se_ve(pedido), status=status.HTTP_201_CREATED)


def _material_de(request):
    """El material que pide, buscado por CODIGO o por id.

    POR CODIGO, Y NO ES UNA COMODIDAD. El telefono conoce el catalogo por
    `codigo`: es lo que viaja en el kit y lo que ya manda la cola de
    movimientos. Exigirle el UUID aca seria un segundo idioma para nombrar el
    mismo material, y el primer sintoma es un pedido que no se puede hacer
    porque la pantalla tiene el dato con el que no se puede preguntar.

    Se acepta el id igual: el CRM si lo tiene, y dejarlo afuera obligaria a una
    traduccion del lado que no hace falta.
    """
    crudo = (request.data.get("material") or "").strip()
    if not crudo:
        return None
    por_codigo = MaterialCatalogo.objects.filter(
        org=request.org, codigo=crudo
    ).first()
    if por_codigo is not None:
        return por_codigo
    try:
        return MaterialCatalogo.objects.filter(org=request.org, id=crudo).first()
    except (ValueError, ValidationError):
        # Un texto que no es un UUID no es un error del servidor: es un
        # material que no existe en esta empresa, y se contesta como tal.
        return None


def _como_se_ve(p: PedidoDeMaterial) -> dict:
    """Lo que la aplicacion necesita para dibujar un pedido. Nada mas."""
    return {
        "id": str(p.id),
        "material": p.material.nombre,
        "material_id": str(p.material_id),
        "material_codigo": p.material.codigo,
        "cantidad": _sin_ceros(p.cantidad),
        "unidad": p.material.unidad,
        "motivo": p.motivo,
        "estado": p.estado,
        "orden_numero": p.orden.numero if p.orden_id else None,
        "pedido_en": p.created_at.isoformat() if p.created_at else None,
    }


def _sin_ceros(valor) -> str:
    """«20», no «20.000». En Colombia el punto separa miles."""
    texto = str(valor)
    if "." not in texto:
        return texto
    return texto.rstrip("0").rstrip(".") or "0"
