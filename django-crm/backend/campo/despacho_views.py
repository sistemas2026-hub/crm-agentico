# -*- coding: utf-8 -*-
"""
================================================================================
 LAS TRES PUERTAS QUE FALTABAN  --  crear, asignar, validar
================================================================================

El modulo campo tenia el ciclo del tecnico entero y ninguna forma de que el
trabajo entrara, se despachara o se aprobara. Lo unico que habia era el panel
de Django, que exige 'is_staff' -- la bandera de superusuario -- y que ademas
no filtra por empresa.

Estas tres usan la sesion del usuario, su rol y el mismo aislamiento por
organizacion que el resto de la API. Nadie necesita 'is_staff' para despachar
una cuadrilla.
================================================================================
"""

from __future__ import annotations

from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import Profile

from campo.models import OrdenTrabajo, WorkTypeVersion
from campo.permissions import IsCampoAuthenticated, ROLES_GESTION
from campo.serializers import (
    AsignarSerializer,
    CrearOrdenSerializer,
    OrdenTrabajoDetailSerializer,
    ValidarSerializer,
)
from campo.services.despacho import (
    ErrorDespacho, asignar, contexto_del_caso, crear_orden,
)
from campo.services.idempotencia import manejar_idempotencia
from campo.services.transiciones import (
    TransicionInvalidaError, aprobar, requerir_correccion,
)


def _exigir_gestion(request):
    """
    Despachar es de quien coordina, no de quien ejecuta.

    Se devuelve 403 y no 404: el usuario TIENE acceso a este modulo, lo que no
    tiene es este permiso. El 404 estricto se reserva para cruzar empresas, que
    es donde revelar la existencia del recurso ya seria demasiado.

    Un tecnico no puede crear, asignar ni aprobar -- en particular, no puede
    aprobarse a si mismo el trabajo que acaba de hacer.
    """
    rol = (getattr(request.profile, "role", "") or "").upper()
    if rol in ROLES_GESTION or request.user.is_superuser:
        return None
    return Response(
        {"error": "PERMISO_INSUFICIENTE",
         "detalle": f"Esta accion es de {sorted(ROLES_GESTION)}."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _orden_o_404(request, pk) -> OrdenTrabajo:
    org = getattr(request, "org", None)
    if not org:
        raise Http404
    orden = OrdenTrabajo.objects.select_related(
        "tipo_trabajo_version__work_type", "org").filter(pk=pk, org=org).first()
    if not orden:
        raise Http404("No existe esa orden.")
    return orden


class CrearOrdenView(APIView):
    """Alta de orden de trabajo, desde un caso del CRM o a mano."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        s = CrearOrdenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        org = request.org

        version = WorkTypeVersion.objects.select_related("work_type").filter(
            pk=d["work_type_version_id"], work_type__org=org).first()
        if version is None:
            # 404 y no 400: una plantilla de otra empresa no debe distinguirse
            # de una que no existe.
            raise Http404("No existe esa version de plantilla.")

        case_id = (d.get("case_id") or "").strip()
        contexto = {}
        activas = []
        if case_id:
            # La ficha tecnica del caso, congelada. Nunca rompe la creacion:
            # si el motor no responde, la orden nace sin snapshot y con la
            # razon anotada adentro.
            contexto = contexto_del_caso(case_id)
            # Que la UI pueda avisar "este caso ya tiene una orden activa". No
            # se bloquea: una segunda visita al mismo caso es legitima, y lo
            # que evita el duplicado accidental es la Idempotency-Key.
            activas = list(
                OrdenTrabajo.objects.filter(
                    org=org, origen_sistema="crm", origen_ref=case_id)
                .exclude(estado_operativo__in=[OrdenTrabajo.CERRADA,
                                               OrdenTrabajo.CANCELADA])
                .values_list("numero", flat=True))

        cliente = {
            "nombre": d.get("cliente_nombre") or (contexto.get("cliente") or {}).get("nombre") or "",
            "telefono": d.get("cliente_telefono") or "",
            "direccion": d.get("cliente_direccion") or "",
            "gps_lat": d.get("gps_lat"),
            "gps_lng": d.get("gps_lng"),
        }

        try:
            orden = crear_orden(
                org=org,
                profile=request.profile,
                version=version,
                cliente=cliente,
                origen_sistema="crm" if case_id else "manual",
                origen_tipo="case" if case_id else "",
                origen_ref=case_id,
                programada_para=d.get("programada_para"),
                contexto=contexto,
            )
        except ErrorDespacho as e:
            return Response({"error": "NO_SE_PUDO_CREAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        if d.get("tecnico_profile_id"):
            tecnico = Profile.objects.filter(
                pk=d["tecnico_profile_id"], org=org).first()
            if tecnico is None:
                raise Http404("No existe esa persona.")
            try:
                asignar(orden, tecnico, request.profile)
            except ErrorDespacho as e:
                return Response({"error": "NO_SE_PUDO_ASIGNAR", "detalle": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)
            orden.refresh_from_db()

        return Response(
            {"orden": OrdenTrabajoDetailSerializer(orden).data,
             "ordenes_activas_del_caso": activas,
             "server_time": timezone.now().isoformat()},
            status=status.HTTP_201_CREATED,
        )


class AsignarTrabajoView(APIView):
    """Pone o cambia al responsable principal. Siempre deja evento."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = AsignarSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        tecnico = Profile.objects.filter(
            pk=s.validated_data["profile_id"], org=request.org).first()
        if tecnico is None:
            raise Http404("No existe esa persona.")

        try:
            asignar(orden, tecnico, request.profile,
                    rol=s.validated_data["rol"] or "tecnico",
                    motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return Response({"error": "NO_SE_PUDO_ASIGNAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                         "server_time": timezone.now().isoformat()})


class ValidarTrabajoView(APIView):
    """Aprobar el trabajo, o devolverlo diciendo que hay que rehacer."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = ValidarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            if d["decision"] == "aprobar":
                orden = aprobar(orden, profile=request.profile,
                                observacion=d["observacion"])
            else:
                orden = requerir_correccion(
                    orden, requisitos=d["requisitos_a_corregir"],
                    profile=request.profile, observacion=d["observacion"])
        except TransicionInvalidaError as e:
            return Response({"error": "VALIDACION_INVALIDA", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                         "server_time": timezone.now().isoformat()})
