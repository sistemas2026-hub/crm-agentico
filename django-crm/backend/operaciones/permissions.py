# -*- coding: utf-8 -*-
"""
Quién puede revisar una propuesta del Supervisor.

EL REVISOR ES EL JEFE DE OPERACIONES
------------------------------------
No se inventa un sistema de roles nuevo. 'campo/permissions.py' ya definió
ROLES_GESTION = {ADMIN, SUPERVISOR, OPERACIONES} para el dominio de campo, y
este módulo reusa exactamente ese conjunto: el Jefe de Operaciones es un perfil
con rol OPERACIONES (o ADMIN/SUPERVISOR, que lo cubren por arriba).

LA IA NO PUEDE CAMBIAR SU PROPIO REVISOR NI SU AUTONOMÍA
--------------------------------------------------------
Todo lo que el Supervisor escribe pasa por 'operaciones/supervisor.py', que no
tiene ninguna función que toque Profile, permisos, roles ni el interruptor de
autonomía. La única forma de mover una propuesta de estado es
'supervisor.revisar', que exige un 'actor' que no puede ser None -- así que una
transición sin persona detrás no es representable.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework.permissions import BasePermission

# El mismo conjunto que campo/permissions.py. Se importa en vez de copiarse:
# dos listas de roles que deberían ser iguales terminan divergiendo.
from campo.permissions import ROLES_GESTION


class EsJefeDeOperaciones(BasePermission):
    """
    Sesión válida, con Profile y Org, y con rol de gestión.

    message se deja explícito porque un 403 sin motivo en una pantalla de
    revisión manda a buscar el problema en el sitio equivocado.
    """

    message = (
        "Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede revisar "
        "las propuestas del Supervisor NOC IA."
    )

    def has_permission(self, request, view):
        profile = getattr(request, "profile", None)
        org = getattr(request, "org", None)
        if not (request.user and request.user.is_authenticated and profile and org):
            return False
        return getattr(profile, "role", None) in ROLES_GESTION


def misma_organizacion(obj, request):
    """
    404 y no 403 cuando el objeto es de otra organización.

    Mismo criterio que campo.permissions.PuedeAccederOrden: un 403 confirma que
    el id existe, y eso ya es información que no corresponde dar.
    """
    org = getattr(request, "org", None)
    if not org or getattr(obj, "org_id", None) != org.id:
        raise Http404
    return True
