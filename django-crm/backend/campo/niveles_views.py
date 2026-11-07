# -*- coding: utf-8 -*-
"""
Los niveles de respuesta, desde Plantillas (24/10/2026). La regla vive en
`campo/niveles.py`; aca solo lo que es de HTTP.

    GET  /api/campo/niveles-de-respuesta/          los tres niveles, los
                                                   asuntos con el suyo, y si
                                                   el Supervisor los ubica
    PUT  /api/campo/niveles-de-respuesta/          guardar los niveles
    PUT  /api/campo/niveles-de-respuesta/asunto/   una persona pone un asunto
                                                   en un nivel

Leer, cualquiera de campo; escribir, la gestion (la misma regla que
Plantillas). La empresa es la de la sesion: ninguna ruta recibe un `org`.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import niveles as N
from campo.cuadrillas_views import _nombre_de
from campo.permissions import ROLES_GESTION, IsCampoAuthenticated


def _exigir_gestion(request):
    """403 si quien pide no es de gestion. La regla de `cuadrillas_views`, con
    su propio texto: aquel dice «para armar cuadrillas»."""
    rol = (getattr(request.profile, "role", "") or "").upper()
    if rol in ROLES_GESTION or request.user.is_superuser:
        return
    raise PermissionDenied(
        "Para cambiar los niveles de respuesta hace falta un rol de gestión.")


def _error(e: N.ErrorNivel):
    return Response({"error": e.codigo, "detalle": e.mensaje},
                    status=status.HTTP_400_BAD_REQUEST)


def _ubica_el_supervisor(org) -> bool:
    """Si alguien le delego al Supervisor que ubique los asuntos (H-21). Solo
    la tarea: el nivel de la empresa lo lee el motor y no se pregunta aca. Sin
    poder comprobarlo, no: la pantalla lo dice en vez de prometerlo."""
    from operaciones import tareas_delegadas as td
    try:
        return td.esta_delegada(org, td.UBICAR_LOS_ASUNTOS)
    except Exception:                                            # noqa: BLE001
        return False


def _todo(org) -> dict:
    return {"niveles": N.niveles_de(org), "asuntos": N.asuntos_con_nivel(org),
            "ubica_el_supervisor": _ubica_el_supervisor(org)}


class NivelesDeRespuestaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        return Response(_todo(request.org))

    def put(self, request):
        _exigir_gestion(request)
        try:
            N.guardar_niveles(request.org, (request.data or {}).get("niveles"))
        except N.ErrorNivel as e:
            return _error(e)
        return Response(_todo(request.org))


class NivelDeAsuntoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def put(self, request):
        _exigir_gestion(request)
        datos = request.data or {}
        try:
            N.decidir_por_persona(
                request.org, datos.get("asunto"), str(datos.get("nivel") or ""),
                profile=request.profile, nombre=_nombre_de(request.profile))
        except N.ErrorNivel as e:
            return _error(e)
        return Response(_todo(request.org))
