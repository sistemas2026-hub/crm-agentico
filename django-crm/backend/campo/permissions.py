# -*- coding: utf-8 -*-
"""Permisos del dominio campo dentro del tenant."""

from __future__ import annotations

from django.http import Http404
from rest_framework.permissions import BasePermission

ROLES_GESTION = {"ADMIN", "SUPERVISOR", "OPERACIONES"}


class IsCampoAuthenticated(BasePermission):
    """Verifica que el usuario tenga sesión válida con Profile y Org activa."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "profile", None)
            and getattr(request, "org", None)
        )


class PuedeAccederOrden(BasePermission):
    """
    Control de acceso a una orden específica:
    - Si la orden pertenece a otra organización -> 404 ESTRICTO (nunca 403).
    - Si el usuario es ADMIN o SUPERVISOR -> permitido.
    - Si el usuario es técnico -> debe estar asignado en AsignacionTrabajo de esa orden.
    """

    def has_object_permission(self, request, view, obj):
        org = getattr(request, "org", None)
        profile = getattr(request, "profile", None)

        if not org or not profile:
            raise Http404

        # Comprobar pertenencia de organización
        obj_org = getattr(obj, "org", None)
        if obj_org and obj_org.pk != org.pk:
            # 404 estricto: no confirmar existencia de UUIDs de otra empresa
            raise Http404

        # Supervisores y Administradores tienen acceso a todo dentro de su organización
        user_role = (profile.role or "").upper()
        if user_role in ROLES_GESTION or request.user.is_superuser:
            return True

        # Técnicos de campo: solo órdenes donde estén asignados
        orden = getattr(obj, "orden_trabajo", obj)  # Aplica a OrdenTrabajo y a EvidenciaTrabajo
        if hasattr(orden, "asignaciones"):
            esta_asignado = orden.asignaciones.filter(profile=profile).exists()
            if not esta_asignado:
                raise Http404
            return True

        return False
