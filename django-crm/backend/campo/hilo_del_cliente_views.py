# -*- coding: utf-8 -*-
"""
Las tres lecturas que unen el ticket, la orden y el cliente (12/11/2026).
Ver `campo/hilo_del_cliente.py`: aca solo se decide QUIEN pregunta y se
responde; las reglas viven alla.

  GET casos/<uuid>/ordenes/        el bloque «Campo» del ticket
  GET trabajos/<uuid>/hilo/        la pagina de la orden (lo que no es bitacora
                                   ni material, que ya tienen su ruta)
  GET clientes/<servicio>/         la ficha del cliente: tickets, ordenes,
                                   solicitudes

Solo lectura las tres. El aislamiento entre empresas es el de siempre: un
caso u orden de otra empresa responde 404, nunca 403.
"""
from __future__ import annotations

from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import hilo_del_cliente as hilo
from campo.permissions import IsCampoAuthenticated


class OrdenesDelCasoView(APIView):
    """Las visitas de un ticket. Lo pide quien puede abrir el ticket: la misma
    regla del detalle del caso (`cases.access`), no una nueva."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from cases.access import assert_case_read_access, get_case_or_404

        caso = get_case_or_404(request.profile, pk)
        assert_case_read_access(request.profile, caso)
        return Response({
            "caso_id": str(caso.id),
            "servicio": (caso.external_service_id or "").strip() or None,
            "ordenes": hilo.ordenes_del_caso(caso, request.profile, request.user),
        })


class HiloDeOrdenView(APIView):
    """De que ticket y servicio es una orden, quien va y que evidencias tiene.
    El permiso es el de toda orden (`views._obtener_orden_o_404`): la gestion
    la ve; un tecnico, solo si la tiene asignada; otra empresa, 404."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        return Response(hilo.hilo_de_la_orden(orden))


class FichaDelClienteView(APIView):
    """Lo que el CRM sabe de un servicio del ISP. Cada parte con su regla: los
    tickets, los que la persona puede abrir; las ordenes, las visibles; las
    solicitudes, solo la gestion."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, servicio):
        servicio = str(servicio or "").strip()
        if not hilo.SERVICIO_VALIDO.match(servicio):
            raise Http404
        return Response(hilo.ficha_del_cliente(
            request.org, servicio, request.profile, request.user))
