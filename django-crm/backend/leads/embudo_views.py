"""Las dos lecturas del embudo de ventas (12/11/2026).

  GET /api/leads/embudo/?dias=30            el embudo de la organizacion
  GET /api/leads/embudo/?desde=AAAA-MM-DD&hasta=AAAA-MM-DD
  GET /api/leads/<id>/solicitud/            lo que paso con el link de un prospecto

El calculo vive en `leads/embudo.py`; aca solo se valida, se autoriza y se
responde. Ninguna de las dos escribe nada.

QUIEN PUEDE VER EL EMBUDO
-------------------------
Administracion y los roles de gestion (ADMIN, SUPERVISOR, OPERACIONES): es la
lectura comercial de TODA la organizacion, con el nombre de cada prospecto
detenido. El listado de prospectos ya le muestra a un USER solo los suyos
(`LeadListView`), y este tablero no puede ser la puerta lateral que le muestre
los de todos. Falla cerrado: un rol que no esta en la lista recibe 403, no un
embudo vacio que parezca "no hubo ventas".

La ficha de un prospecto usa la MISMA regla que la ficha misma
(`LeadDetailView.assert_lead_access`): quien puede abrir el Lead puede ver que
paso con su solicitud, y nadie mas.
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasOrgContext, is_org_admin
from leads import embudo
from leads.models import Lead

#: Los periodos fijos que ofrece la pantalla. Un rango libre va por desde/hasta.
PERIODOS_DIAS = (7, 30, 90)
#: Un rango mas largo que esto es un informe historico, no un embudo operativo.
MAXIMO_DIAS = 366
#: Los roles de gestion, los mismos de campo/permissions.py. Se repiten aca y
#: no se importan: `leads` no depende del modulo de campo para autorizar.
ROLES_EMBUDO = frozenset({"ADMIN", "SUPERVISOR", "OPERACIONES"})


def puede_ver_embudo(profile) -> bool:
    if profile is None or not getattr(profile, "is_active", False):
        return False
    return is_org_admin(profile) or getattr(profile, "role", None) in ROLES_EMBUDO


def _zona(org):
    try:
        return zoneinfo.ZoneInfo((getattr(org, "timezone", "") or "UTC").strip() or "UTC")
    except Exception:                                            # noqa: BLE001
        return zoneinfo.ZoneInfo("UTC")


def _dia(valor: str, campo: str) -> date:
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(f"'{campo}' tiene que ser una fecha AAAA-MM-DD.") from None


def periodo(params, org, ahora=None) -> tuple[datetime, datetime]:
    """[desde, hasta) en la zona de la organizacion. ValueError si no se entiende.

    Un valor que no se entiende se RECHAZA, no se cambia por el de omision:
    contestar 30 dias a quien pidio otra cosa es un numero de otro periodo con
    el titulo del que pidio.
    """
    zona = _zona(org)
    ahora = ahora or timezone.now()
    desde_txt, hasta_txt = params.get("desde"), params.get("hasta")
    if desde_txt or hasta_txt:
        if not (desde_txt and hasta_txt):
            raise ValueError("Un rango necesita 'desde' y 'hasta'.")
        d, h = _dia(desde_txt, "desde"), _dia(hasta_txt, "hasta")
        if h < d:
            raise ValueError("'hasta' no puede ser anterior a 'desde'.")
        if (h - d).days + 1 > MAXIMO_DIAS:
            raise ValueError(f"El rango no puede pasar de {MAXIMO_DIAS} días.")
        # 'hasta' es el ultimo dia INCLUIDO: el limite es la medianoche siguiente.
        return (datetime.combine(d, time.min, tzinfo=zona),
                datetime.combine(h + timedelta(days=1), time.min, tzinfo=zona))
    crudo = params.get("dias") or "30"
    try:
        dias = int(crudo)
    except (TypeError, ValueError):
        raise ValueError("'dias' tiene que ser 7, 30 o 90.") from None
    if dias not in PERIODOS_DIAS:
        raise ValueError("'dias' tiene que ser 7, 30 o 90.")
    hoy = ahora.astimezone(zona).date()
    return (datetime.combine(hoy - timedelta(days=dias - 1), time.min, tzinfo=zona),
            datetime.combine(hoy + timedelta(days=1), time.min, tzinfo=zona))


class EmbudoView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request):
        if not puede_ver_embudo(request.profile):
            return Response({"error": "El embudo de ventas es de administración y gestión."},
                            status=http.HTTP_403_FORBIDDEN)
        org = request.profile.org
        try:
            desde, hasta = periodo(request.query_params, org)
        except ValueError as e:
            return Response({"error": str(e)}, status=http.HTTP_400_BAD_REQUEST)
        return Response(embudo.calcular(org, desde, hasta))


class SolicitudDelLeadView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request, pk):
        lead = get_object_or_404(Lead, id=pk, org=request.profile.org)
        if not (is_org_admin(request.profile) or request.user.is_superuser):
            permitidos = {p.id for p in lead.assigned_to.all()}
            if request.profile.user_id == lead.created_by_id:
                permitidos.add(request.profile.id)
            if request.profile.id not in permitidos:
                raise PermissionDenied("No tiene permiso para ver este prospecto.")
        return Response({"solicitudes": embudo.de_un_lead(request.profile.org, lead)})
