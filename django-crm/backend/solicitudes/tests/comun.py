"""Lo que comparten las pruebas de solicitudes (12/11/2026).

Los dobles van EN EL BORDE: la llamada HTTP al motor (``requests``). Nada de
la logica de solicitudes se sustituye.
"""

from __future__ import annotations

import datetime as dt
import uuid

from django.utils import timezone
from rest_framework.test import APIClient

from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from solicitudes.models import SolicitudServicio


def persona(org, rol="USER", correo=None):
    user = User.objects.create_user(email=correo or f"{uuid.uuid4().hex[:8]}@prueba.test",
                                    password="x")
    return Profile.objects.create(user=user, org=org, role=rol, is_active=True)


def cliente_de(perfil):
    c = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(perfil.user, perfil.org, perfil)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


def solicitud(org, **extra):
    datos = dict(org=org, token_hash=uuid.uuid4().hex,
                 expira_en=timezone.now() + dt.timedelta(days=3),
                 nombre="Ana", apellido="Prueba", telefono="3001234567",
                 numero_documento="123", direccion="Calle 1", barrio="CENTRO",
                 estado=SolicitudServicio.ENVIADA, enviada_en=timezone.now())
    datos.update(extra)
    return SolicitudServicio.objects.create(**datos)


class Respuesta:
    """Lo minimo de requests.Response que leen los llamadores."""

    def __init__(self, cuerpo=None, estado=200):
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.status_code = estado
        self.ok = 200 <= estado < 300
        self.content = b"{}"

    def json(self):
        return self._cuerpo

    def raise_for_status(self):
        if not self.ok:
            import requests
            #  Como requests: el error lleva la respuesta adentro.
            raise requests.HTTPError(f"{self.status_code}", response=self)
