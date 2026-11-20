"""Quien puede ver y decidir las solicitudes de instalacion.

POR QUE EXISTE (12/11/2026)
---------------------------
La bandeja, la decision y el expediente en PDF --foto de la cedula, recibo de
servicios, foto del solicitante, firma y GPS de la vivienda-- solo pedian
estar autenticado y tener organizacion. Cualquier rol las leia. Lo encontro la
auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md §2, «Instalaciones»).

QUIEN DECIDE NO ES UN ROL, ES UN AREA
------------------------------------
Dato del dueño: en la primera empresa la factibilidad la decide el area de
atencion que se ocupa del soporte tecnico. Esa area no es un rol de Django
(ADMIN, SUPERVISOR, OPERACIONES, USER, BODEGA): es el area que la empresa le
pone a cada persona en el motor ('asistente.area_colaborador'), la misma que
ya usan la cola de Tickets ('cases/access.py::area_de') y el Supervisor.

Por eso el permiso es:  gestion (ROLES_GESTION)  O  una persona cuya area
esta en la lista que la empresa eligio en Ajustes -> Instalaciones. Ningun
nombre de area vive en este archivo: es configuracion (CLAUDE.md §3.3).

FALLA CERRADO, Y POR TRES CAMINOS
--------------------------------
  * sin ajuste (o lista vacia)  -> solo gestion
  * el motor no contesta        -> el mapa persona->area llega vacio -> solo
                                   gestion. 'area_por_persona_de_org' devuelve
                                   {} tanto si no sabe como si nadie tiene area,
                                   y para un permiso las dos significan lo mismo.
  * la persona no tiene area    -> solo gestion
Nunca "no se pudo saber, entonces pasa".
"""

from __future__ import annotations

from rest_framework import status as http
from rest_framework.response import Response

from campo.permissions import ROLES_GESTION

#: Lo que ve quien no puede, y lo que la pantalla muestra tal cual. Dice QUE
#: hacer, no solo que no se puede: quien lo lee es alguien que hasta ayer
#: entraba a esta bandeja.
MENSAJE_SIN_PERMISO = (
    "Decidir la factibilidad de las instalaciones es de las áreas que la empresa "
    "eligió en Ajustes → Instalaciones, y de administración, supervisión y "
    "operaciones. Si te toca hacerlo, pedile a un administrador que agregue tu área."
)

SIN_PERMISO = "sin_permiso_instalaciones"


def _normal(texto) -> str:
    return str(texto or "").strip().lower()


def es_gestion(profile) -> bool:
    if profile is None:
        return False
    user = getattr(profile, "user", None)
    if user is not None and getattr(user, "is_superuser", False):
        return True
    return _normal(getattr(profile, "role", "")).upper() in ROLES_GESTION


def areas_que_deciden(org) -> set:
    """Las areas que la empresa eligio, normalizadas. Vacio si no eligio."""
    from solicitudes.models import AjustesDeInstalacion

    if org is None:
        return set()
    fila = AjustesDeInstalacion.objects.filter(org=org).first()
    return fila.areas_normalizadas() if fila is not None else set()


def puede_decidir(profile) -> tuple[bool, str]:
    """(puede, por que). El 'por que' es para la prueba y el log, no la pantalla."""
    if profile is None:
        return False, "sin_perfil"
    if es_gestion(profile):
        return True, "gestion"
    areas = areas_que_deciden(getattr(profile, "org", None))
    if not areas:
        return False, "sin_ajuste"
    #  Se pregunta por el modulo (no por un nombre importado) para que el
    #  doble de pruebas del conftest y la cache del modulo valgan igual aca.
    from operaciones import areas_del_tenant

    mapa = areas_del_tenant.area_por_persona_de_org(profile.org_id) or {}
    suya = _normal(mapa.get(str(profile.id)))
    if not suya:
        #  Sin mapa (motor caido) o sin area para esta persona: no se sabe que
        #  sea de un area que decide, y no saber no es permiso.
        return False, "sin_area"
    if suya in areas:
        return True, "area"
    return False, "otra_area"


def negado(request):
    """La respuesta 403 si quien pide no puede; None si puede."""
    puede, _ = puede_decidir(getattr(request, "profile", None))
    if puede:
        return None
    return Response({"error": MENSAJE_SIN_PERMISO, "codigo": SIN_PERMISO},
                    status=http.HTTP_403_FORBIDDEN)
