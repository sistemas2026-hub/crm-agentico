# -*- coding: utf-8 -*-
"""
Las vistas previas del Supervisor: lo que haria, sin escribir nada.

``GET /api/operaciones/jornada/vista-previa/?fecha=AAAA-MM-DD`` (21/10/2026)
devuelve lo que armaria ese dia. Ver
`operaciones.armado_de_jornadas.vista_previa`.

``GET /api/operaciones/ordenes/vista-previa/`` (23/10/2026) devuelve que
ordenes crearia ahora en la cola de Despacho, y por que no las otras. Ver
`operaciones.ordenes_de_despacho.decidir`.

Modulo propio y no `views.py`: ese archivo es de los de superficie de conflicto
alta (CLAUDE.md §2), y esto es una lectura sola.
"""

from __future__ import annotations

from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView

from operaciones.permissions import EsJefeDeOperaciones


class VistaPreviaDeLaJornadaView(APIView):
    """Lo que armaria el Supervisor. Sin `fecha`, hoy en la hora de la empresa."""

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        from campo.tasks import _ahora_local
        from operaciones.armado_de_jornadas import vista_previa

        texto = (request.query_params.get("fecha") or "").strip()
        if texto:
            try:
                fecha = date.fromisoformat(texto)
            except ValueError:
                return Response({"detail": "La fecha va como AAAA-MM-DD."},
                                status=400)
        else:
            fecha = _ahora_local(request.org).date()
        return Response(vista_previa(request.org, fecha))


class VistaPreviaDeLasOrdenesView(APIView):
    """Que ordenes crearia el Supervisor ahora. No crea ninguna, no guarda
    nada y no le pregunta al motor: todo sale de lo ya guardado."""

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        from operaciones.ordenes_de_despacho import decidir

        return Response(decidir(request.org))
