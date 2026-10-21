# -*- coding: utf-8 -*-
"""
La vista previa del armado de la jornada  --  21/10/2026.

``GET /api/operaciones/jornada/vista-previa/?fecha=AAAA-MM-DD`` devuelve lo
que armaria el Supervisor ese dia, sin escribir nada. Ver
`operaciones.armado_de_jornadas.vista_previa`.

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
