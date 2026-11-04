# -*- coding: utf-8 -*-
"""
Las novedades de la cuadrilla, por HTTP (30/10/2026). Ver `campo/novedades.py`
y SPEC/objetivos/novedad-de-cuadrilla.md.

    GET  /api/campo/novedades/?fecha=AAAA-MM-DD   las del dia: quien gestiona
                                                  ve todas; el tecnico, las suyas
    POST /api/campo/novedades/                    avisar una; `Idempotency-Key`
                                                  obligatoria (la cola offline)
    POST /api/campo/novedades/<id>/resolver/      «Ya seguí»: quien la aviso o
                                                  quien gestiona

El aislamiento: todo filtra por la empresa de quien pide; una de otra empresa
da 404, nunca 403.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import novedades as N
from campo.permissions import ROLES_GESTION, IsCampoAuthenticated


def _gestiona(request) -> bool:
    rol = (getattr(request.profile, "role", "") or "").upper()
    return rol in ROLES_GESTION or bool(getattr(request.user, "is_superuser", False))


class NovedadesView(APIView):
    """Leer las del dia, o avisar una."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo import reparto as R

        org = request.profile.org
        crudo = (request.query_params.get("fecha") or "").strip()
        try:
            fecha = (dt.date.fromisoformat(crudo) if crudo
                     else timezone.now().astimezone(R._zona_de(org)).date())
        except ValueError:
            return Response({"detail": "La fecha va como AAAA-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)
        qs = (N.NovedadDeCuadrilla.objects.filter(org=org, fecha=fecha)
              .select_related("jornada__cuadrilla", "profile__user"))
        if not _gestiona(request):
            qs = qs.filter(profile=request.profile)
        ahora = timezone.now()
        return Response({"fecha": fecha.isoformat(),
                         "novedades": [N.a_json(n, ahora) for n in qs]})

    def post(self, request):
        org = request.profile.org
        avisada = request.data.get("avisada_en")
        avisada_en = parse_datetime(str(avisada)) if avisada else None
        if avisada and (avisada_en is None or timezone.is_naive(avisada_en)):
            return Response({"detail": "La hora va con su zona horaria."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            n, creada = N.avisar(
                org, request.profile,
                tipo=str(request.data.get("tipo") or ""),
                afecta=str(request.data.get("afecta") or ""),
                texto=str(request.data.get("texto") or ""),
                avisada_en=avisada_en,
                clave=request.headers.get("Idempotency-Key", ""))
        except N.NovedadInvalida as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(N.a_json(n),
                        status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)


class ResolverNovedadView(APIView):
    """«Ya seguí»."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        n = N.resolver(request.profile.org, pk, request.profile,
                       puede_cualquiera=_gestiona(request))
        if n is None:
            return Response({"detail": "No existe."}, status=status.HTTP_404_NOT_FOUND)
        return Response(N.a_json(n))
