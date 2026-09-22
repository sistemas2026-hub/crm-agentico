# -*- coding: utf-8 -*-
"""
Cambiar una contraseña: la propia, o la de alguien del equipo.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
La API sabía crear una cuenta con contraseña y sabía verificarla al entrar,
pero no sabía cambiarla. Ni la propia ni la de nadie. La única salida era
``manage.py changepassword`` en el servidor, o sea: una persona con acceso a
producción por cada olvido. Eso no es una función faltante de la interfaz, es
una función que no existía en ninguna capa.

LAS DOS PUERTAS, Y POR QUÉ SON DOS
----------------------------------
``MiClaveView`` es para uno mismo y **exige la contraseña actual**. No porque
el servidor dude de quién es —el token ya lo dijo— sino porque una sesión
abierta en un equipo prestado no debería alcanzar para quedarse con la cuenta.
Pedir la actual convierte "tengo el teléfono" en "además la sé".

``ClaveDeUsuarioView`` es para un administrador sobre otra persona de su
organización, y **no pide la actual** porque el administrador no la conoce:
ese es justamente el caso que resuelve. A cambio carga dos guardas que la otra
no necesita.

LA GUARDA QUE IMPORTA: UNA CUENTA NO ES DE UNA ORGANIZACIÓN
-----------------------------------------------------------
Un ``User`` puede tener ``Profile`` en varias organizaciones. La contraseña
cuelga del ``User``, no del ``Profile``: quien la cambia no abre una puerta,
abre todas las de esa cuenta. Si el administrador de la empresa A pudiera
reiniciarle la clave a alguien que también trabaja en la empresa B, se estaría
llevando el acceso a B sin que nadie en B se entere.

Es la misma regla que ya estaba escrita al dar de alta (``user_views.py``: una
cuenta que ya existía se reutiliza tal cual y el administrador que invita no
manda sobre su clave). Acá se sostiene igual: si la cuenta vive en más de una
organización, este endpoint se niega y lo dice.

AL CAMBIAR UNA CONTRASEÑA SE CIERRAN LAS SESIONES
-------------------------------------------------
Cambiar la clave y dejar vivos los tokens de refresco es cambiar la cerradura
dejando las copias de la llave circulando: el ``refresh`` dura catorce días y
sigue emitiendo accesos. Quien cambia una contraseña casi siempre lo hace
porque cree que alguien más la tiene; el gesto tiene que valer para eso.

Lo que queda vivo hasta una hora son los ``access`` ya emitidos, que son sin
estado. Es el mismo límite aceptado en ``LogoutView`` y por las mismas
razones: matarlos exige una lista negra consultada en cada petición.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from common import swagger_params
from common.audit_log import audit_log
from common.models import Profile
from common.permissions import HasOrgContext, is_org_admin


def _jti_de(refresco, user):
    """El identificador del token de refresco presentado, si es de ``user``.

    Devuelve ``None`` ante cualquier duda —token ilegible, vencido, de otra
    cuenta—, y ante ``None`` no se conserva ninguna sesión. El error seguro es
    cerrar de más.
    """
    if not refresco:
        return None
    try:
        token = RefreshToken(refresco)
    except TokenError:
        return None
    if str(token.get("user_id", "")) != str(user.id):
        return None
    return token.get("jti")


def _cerrar_sesiones(user, conservar_jti=None) -> int:
    """Invalida los tokens de refresco de ``user``. Devuelve cuántos cerró.

    ``conservar_jti`` deja viva una sola sesión: la de quien está haciendo el
    cambio. Cambiar la propia contraseña y quedar expulsado del navegador donde
    se acaba de cambiar es un castigo por hacer lo correcto, y empuja a la
    gente a no cambiarla. Las demás sí se cierran, que es el punto: si alguien
    más tenía la clave, su sesión se cae.

    Cuando un administrador le define la clave a otra persona no se conserva
    nada, porque ninguna de esas sesiones es suya.

    Los ``access`` ya emitidos siguen valiendo hasta una hora: ver el
    encabezado del módulo. Lo que esto corta es la capacidad de emitir nuevos.
    """
    cerradas = 0
    for token in OutstandingToken.objects.filter(user=user):
        if conservar_jti and token.jti == conservar_jti:
            continue
        _, creado = BlacklistedToken.objects.get_or_create(token=token)
        if creado:
            cerradas += 1
    return cerradas


def _revisar(nueva, user):
    """Devuelve el motivo por el que ``nueva`` no sirve, o ``None``.

    Usa los validadores configurados en ``AUTH_PASSWORD_VALIDATORS``, que es lo
    que ya se aplica en el resto de Django, para que la regla sea una sola y no
    dos opiniones distintas según por dónde se entre.
    """
    if not nueva:
        return "Escribe la contraseña nueva."
    try:
        validate_password(nueva, user=user)
    except ValidationError as error:
        return " ".join(error.messages)
    return None


_RESPUESTA = inline_serializer(
    name="CambioDeClaveResponse",
    fields={
        "error": serializers.BooleanField(),
        "message": serializers.CharField(),
        "sesiones_cerradas": serializers.IntegerField(),
    },
)


class MiClaveView(APIView):
    """``POST /api/auth/password/`` — cambiar la contraseña propia."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["users"],
        description=(
            "Cambia la contraseña de quien hace la petición. Exige la actual y "
            "cierra las demás sesiones de la cuenta."
        ),
        request=inline_serializer(
            name="CambioDeClavePropiaRequest",
            fields={
                "actual": serializers.CharField(),
                "nueva": serializers.CharField(),
                "refresh": serializers.CharField(
                    required=False,
                    help_text=(
                        "Token de refresco de esta sesión. Si se envía, esta "
                        "sesión no se cierra; las demás sí."
                    ),
                ),
            },
        ),
        responses={200: _RESPUESTA},
    )
    def post(self, request, format=None):
        user = request.user
        actual = request.data.get("actual") or ""
        nueva = request.data.get("nueva") or ""

        if not user.check_password(actual):
            # Sin distinguir "no la sabés" de "no tenés una": una cuenta creada
            # por Google o por enlace mágico lleva una clave aleatoria que nadie
            # conoce, y su salida es que un administrador le defina una.
            return Response(
                {
                    "error": True,
                    "errors": (
                        "La contraseña actual no coincide. Si entras con Google "
                        "o con un enlace de acceso, pídele a un administrador "
                        "que te defina una."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        motivo = _revisar(nueva, user)
        if motivo:
            return Response(
                {"error": True, "errors": motivo},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if actual == nueva:
            return Response(
                {"error": True, "errors": "La contraseña nueva es igual a la actual."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # La sesión desde la que se hace el cambio se conserva, si el cliente
        # la presenta. Es opcional a propósito: sin ella se cierran todas, que
        # es el lado seguro del error.
        conservar = _jti_de(request.data.get("refresh"), user)

        with transaction.atomic():
            user.set_password(nueva)
            user.save(update_fields=["password"])
            cerradas = _cerrar_sesiones(user, conservar_jti=conservar)

        audit_log.password_changed(
            user, getattr(getattr(request, "profile", None), "org", None), request
        )
        return Response(
            {
                "error": False,
                "message": "Contraseña actualizada.",
                "sesiones_cerradas": cerradas,
            },
            status=status.HTTP_200_OK,
        )


class ClaveDeUsuarioView(APIView):
    """``POST /api/user/<pk>/password/`` — un admin le define una clave a otra
    persona de su organización.

    ``pk`` es el id del **User**, igual que el resto de ``/user/<pk>/...``.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    @extend_schema(
        tags=["users"],
        parameters=swagger_params.organization_params,
        description=(
            "Define una contraseña nueva para otra persona de la organización. "
            "Solo administradores. Se niega si la cuenta también pertenece a "
            "otra organización."
        ),
        request=inline_serializer(
            name="CambioDeClaveAjenaRequest",
            fields={"nueva": serializers.CharField()},
        ),
        responses={200: _RESPUESTA},
    )
    def post(self, request, pk, format=None):
        if not (is_org_admin(request.profile) or request.user.is_superuser):
            return Response(
                {"error": True, "errors": "Permission Denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile = get_object_or_404(
            Profile, user__id=pk, org=request.profile.org
        )

        if profile.id == request.profile.id:
            # Para la propia hay una puerta que pide la actual, y tiene que
            # seguir siendo la única: si un admin pudiera reiniciarse la suya
            # desde acá, una sesión abierta y olvidada bastaría para quedarse
            # con la cuenta.
            return Response(
                {
                    "error": True,
                    "errors": (
                        "Para cambiar tu propia contraseña usa la opción de tu "
                        "perfil: pide la contraseña actual."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        otras = (
            Profile.objects.filter(user_id=profile.user_id, is_active=True)
            .exclude(org=request.profile.org)
            .exists()
        )
        if otras:
            return Response(
                {
                    "error": True,
                    "errors": (
                        "Esta cuenta también pertenece a otra organización. La "
                        "contraseña es de la cuenta, no de tu empresa: "
                        "cambiarla daría acceso a la otra. Puedes desactivar a "
                        "la persona aquí, pero su contraseña la cambia ella."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        nueva = request.data.get("nueva") or ""
        motivo = _revisar(nueva, profile.user)
        if motivo:
            return Response(
                {"error": True, "errors": motivo},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            profile.user.set_password(nueva)
            profile.user.save(update_fields=["password"])
            cerradas = _cerrar_sesiones(profile.user)

        audit_log.password_reset(
            profile.user,
            request.profile.org,
            reset_by=request.user.email,
            request=request,
        )
        return Response(
            {
                "error": False,
                "message": "Contraseña actualizada.",
                "sesiones_cerradas": cerradas,
            },
            status=status.HTTP_200_OK,
        )
