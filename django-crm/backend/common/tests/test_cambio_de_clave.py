# -*- coding: utf-8 -*-
"""
Cambiar una contraseña: la propia y la de alguien del equipo.

QUÉ CUIDAN ESTAS PRUEBAS
------------------------
Un endpoint que escribe contraseñas es de los pocos donde un error no se ve
hasta que ya pasó algo. Por eso lo que se afirma acá no es "responde 200", es
el **efecto**: que la clave vieja deje de servir, que la nueva sirva, que las
sesiones abiertas se caigan, y que quien no debía poder, no pudo.

La guarda que más importa es la multi-organización: la contraseña cuelga de la
cuenta, no del perfil, así que reiniciarla desde una empresa abriría la puerta
de la otra.
"""

import pytest
from rest_framework import status
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from common.audit_log import SecurityAuditLog
from common.models import Profile, User

MIA = "/api/auth/password/"


def de(user_id):
    return f"/api/user/{user_id}/password/"


@pytest.mark.django_db
class TestMiPropiaClave:
    def test_la_cambia_y_la_vieja_deja_de_servir(self, user_client, regular_user):
        r = user_client.post(
            MIA, {"actual": "testpass123", "nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_200_OK
        regular_user.refresh_from_db()
        assert regular_user.check_password("Tejado-Verde-91")
        assert not regular_user.check_password("testpass123")

    def test_sin_la_actual_no_se_cambia_nada(self, user_client, regular_user):
        """Una sesión abierta en un equipo prestado no alcanza."""
        r = user_client.post(
            MIA, {"actual": "la-que-no-es", "nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        regular_user.refresh_from_db()
        assert regular_user.check_password("testpass123")

    def test_una_clave_debil_se_rechaza_con_el_motivo(self, user_client, regular_user):
        r = user_client.post(
            MIA, {"actual": "testpass123", "nueva": "123456"}, format="json"
        )

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        # El motivo llega escrito: la pantalla lo muestra tal cual.
        assert str(r.data["errors"]).strip()
        regular_user.refresh_from_db()
        assert regular_user.check_password("testpass123")

    def test_no_se_permite_repetir_la_misma(self, user_client):
        r = user_client.post(
            MIA, {"actual": "testpass123", "nueva": "testpass123"}, format="json"
        )

        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_sin_sesion_no_se_llega(self, unauthenticated_client):
        r = unauthenticated_client.post(
            MIA, {"actual": "x", "nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_cambiarla_cierra_las_sesiones_abiertas(self, user_client, regular_user):
        """Cambiar la cerradura sin recoger las llaves no sirve de nada.

        El refresh vive catorce días; quien cambia su contraseña suele hacerlo
        porque cree que alguien más la tiene.
        """
        from common.serializer import OrgAwareRefreshToken

        profile = Profile.objects.get(user=regular_user)
        OrgAwareRefreshToken.for_user_and_org(regular_user, profile.org, profile)
        vivos = OutstandingToken.objects.filter(user=regular_user).count()
        assert vivos >= 1

        r = user_client.post(
            MIA, {"actual": "testpass123", "nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_200_OK
        en_lista_negra = BlacklistedToken.objects.filter(
            token__user=regular_user
        ).count()
        assert en_lista_negra == vivos
        assert r.data["sesiones_cerradas"] == vivos

    def test_queda_registrado(self, user_client, regular_user):
        user_client.post(
            MIA, {"actual": "testpass123", "nueva": "Tejado-Verde-91"}, format="json"
        )

        assert SecurityAuditLog.objects.filter(
            event_type="PASSWORD_CHANGED", user=regular_user
        ).exists()


@pytest.mark.django_db
class TestUnAdminLeDefineLaClaveAOtro:
    def test_el_admin_puede(self, admin_client, regular_user, user_profile):
        r = admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_200_OK
        regular_user.refresh_from_db()
        assert regular_user.check_password("Tejado-Verde-91")

    def test_un_miembro_no_puede(self, user_client, admin_user, admin_profile):
        r = user_client.post(
            de(admin_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_403_FORBIDDEN
        admin_user.refresh_from_db()
        assert admin_user.check_password("testpass123")

    def test_no_se_alcanza_a_alguien_de_otra_empresa(
        self, admin_client, user_b, profile_b
    ):
        """Ni siquiera para saber que existe: 404, no 403."""
        r = admin_client.post(de(user_b.id), {"nueva": "Tejado-Verde-91"}, format="json")

        assert r.status_code == status.HTTP_404_NOT_FOUND
        user_b.refresh_from_db()
        assert user_b.check_password("testpass123")

    def test_una_cuenta_compartida_con_otra_empresa_no_se_toca(
        self, admin_client, regular_user, user_profile, org_b
    ):
        """La guarda del archivo.

        La misma persona trabaja en dos empresas con una sola cuenta. Si el
        admin de la primera pudiera reiniciarle la clave, se estaría llevando
        el acceso a la segunda sin que nadie en la segunda se entere.
        """
        Profile.objects.create(
            user=regular_user, org=org_b, role="USER", is_active=True
        )

        r = admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_409_CONFLICT
        regular_user.refresh_from_db()
        assert regular_user.check_password("testpass123")

    def test_un_perfil_inactivo_en_otra_empresa_no_bloquea(
        self, admin_client, regular_user, user_profile, org_b
    ):
        """Si ya no trabaja allá, la puerta que se abre es una sola."""
        Profile.objects.create(
            user=regular_user, org=org_b, role="USER", is_active=False
        )

        r = admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_200_OK

    def test_el_admin_no_se_reinicia_la_suya_por_esta_puerta(
        self, admin_client, admin_user
    ):
        """Si pudiera, una sesión olvidada bastaría para quedarse con la cuenta.

        Para la propia está `/api/auth/password/`, que pide la actual.
        """
        r = admin_client.post(
            de(admin_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        admin_user.refresh_from_db()
        assert admin_user.check_password("testpass123")

    def test_una_clave_debil_tambien_se_rechaza_aca(
        self, admin_client, regular_user, user_profile
    ):
        r = admin_client.post(de(regular_user.id), {"nueva": "12345678"}, format="json")

        assert r.status_code == status.HTTP_400_BAD_REQUEST
        regular_user.refresh_from_db()
        assert regular_user.check_password("testpass123")

    def test_le_cierra_las_sesiones_a_esa_persona(
        self, admin_client, regular_user, user_profile
    ):
        from common.serializer import OrgAwareRefreshToken

        OrgAwareRefreshToken.for_user_and_org(
            regular_user, user_profile.org, user_profile
        )
        vivos = OutstandingToken.objects.filter(user=regular_user).count()

        r = admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert r.data["sesiones_cerradas"] == vivos
        assert BlacklistedToken.objects.filter(token__user=regular_user).count() == vivos

    def test_queda_registrado_quien_lo_hizo(
        self, admin_client, regular_user, user_profile, admin_user
    ):
        """No alcanza con saber a quién: este evento le da a alguien una llave
        ajena, y reconstruir qué pasó exige saber quién la usó."""
        admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        evento = SecurityAuditLog.objects.filter(
            event_type="PASSWORD_RESET", user=regular_user
        ).first()
        assert evento is not None
        assert admin_user.email in str(evento.description) + str(evento.metadata)


@pytest.mark.django_db
class TestUnaCredencialNoInteractivaNoLlega:
    """Un token de integración no puede tocar contraseñas, tenga el alcance que
    tenga: si pudiera, se convertiría en la cuenta de cualquiera."""

    def test_las_dos_rutas_estan_en_la_lista_de_credenciales(self):
        from common.scopes import check_request

        assert check_request(["*:write"], "POST", MIA) is not None
        assert (
            check_request(
                ["*:write"], "POST", "/api/user/11111111-1111-1111-1111-111111111111/password/"
            )
            is not None
        )

    def test_un_endpoint_normal_de_usuarios_sigue_abierto(self):
        from common.scopes import check_request

        assert check_request(["*:read"], "GET", "/api/users/") is None


@pytest.mark.django_db
class TestBorrarNoSeLlevaElHistorial:
    """Borrar un perfil arrastra sus asignaciones de campo por CASCADE.

    Una orden cerrada dejaría de saber quién la hizo, y eso no se recupera.
    Desactivar hace lo que casi siempre se quería sin romper lo que ya pasó.
    """

    def _url(self, user_id):
        return f"/api/user/{user_id}/"

    def test_una_cuenta_sin_trabajo_se_borra(
        self, admin_client, regular_user, user_profile
    ):
        """Un alta equivocada o una prueba sí se borra: no hay qué conservar."""
        r = admin_client.delete(self._url(regular_user.id))

        assert r.status_code == status.HTTP_200_OK
        assert not Profile.objects.filter(pk=user_profile.pk).exists()

    def test_con_ordenes_en_el_historial_se_niega(
        self, admin_client, regular_user, user_profile, org_a
    ):
        from campo.models import (
            AsignacionTrabajo,
            OrdenTrabajo,
            WorkType,
            WorkTypeVersion,
        )

        wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalación")
        version = WorkTypeVersion.objects.create(
            work_type=wt,
            version=1,
            schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"pasos": [], "campos": [], "evidencias": []},
        )
        orden = OrdenTrabajo.objects.create(
            org=org_a,
            numero=7001,
            tipo_trabajo_version=version,
            estado_operativo=OrdenTrabajo.ASIGNADA,
        )
        AsignacionTrabajo.objects.create(
            orden=orden, profile=user_profile, rol="tecnico", es_principal=True
        )

        r = admin_client.delete(self._url(regular_user.id))

        assert r.status_code == status.HTTP_409_CONFLICT
        assert "Desactivala" in str(r.data["errors"])
        # Y no se llevó nada por delante.
        assert Profile.objects.filter(pk=user_profile.pk).exists()
        assert AsignacionTrabajo.objects.filter(profile=user_profile).exists()

    def test_desactivar_sigue_siendo_el_camino(
        self, admin_client, regular_user, user_profile
    ):
        r = admin_client.post(
            f"/api/user/{regular_user.id}/status/", {"status": "Inactive"}, format="json"
        )

        assert r.status_code == status.HTTP_200_OK
        user_profile.refresh_from_db()
        assert user_profile.is_active is False


@pytest.mark.django_db
class TestLaSesionPropiaSobrevive:
    """Cambiar la propia contraseña no te echa del navegador donde la cambiaste.

    Si lo hiciera, el gesto correcto tendría un castigo, y la gente aprende
    rápido a no hacerlo. Las demás sesiones sí se caen: ese es el punto.
    """

    def test_la_sesion_presentada_queda_viva_y_las_otras_no(
        self, user_client, regular_user
    ):
        from common.serializer import OrgAwareRefreshToken

        profile = Profile.objects.get(user=regular_user)
        mia = OrgAwareRefreshToken.for_user_and_org(regular_user, profile.org, profile)
        otra = OrgAwareRefreshToken.for_user_and_org(regular_user, profile.org, profile)

        r = user_client.post(
            MIA,
            {
                "actual": "testpass123",
                "nueva": "Tejado-Verde-91",
                "refresh": str(mia),
            },
            format="json",
        )

        assert r.status_code == status.HTTP_200_OK
        negros = set(
            BlacklistedToken.objects.filter(token__user=regular_user).values_list(
                "token__jti", flat=True
            )
        )
        assert mia["jti"] not in negros
        assert otra["jti"] in negros

    def test_un_refresco_ajeno_no_conserva_nada(
        self, user_client, regular_user, admin_user, admin_profile
    ):
        """Presentar el token de otra persona no salva ninguna sesión.

        Ante cualquier duda se cierra de más: ese es el lado seguro del error.
        """
        from common.serializer import OrgAwareRefreshToken

        profile = Profile.objects.get(user=regular_user)
        mia = OrgAwareRefreshToken.for_user_and_org(regular_user, profile.org, profile)
        ajeno = OrgAwareRefreshToken.for_user_and_org(
            admin_user, admin_profile.org, admin_profile
        )

        user_client.post(
            MIA,
            {
                "actual": "testpass123",
                "nueva": "Tejado-Verde-91",
                "refresh": str(ajeno),
            },
            format="json",
        )

        assert BlacklistedToken.objects.filter(token__jti=mia["jti"]).exists()

    def test_cuando_un_admin_reinicia_la_clave_no_se_conserva_ninguna(
        self, admin_client, regular_user, user_profile
    ):
        from common.serializer import OrgAwareRefreshToken

        suya = OrgAwareRefreshToken.for_user_and_org(
            regular_user, user_profile.org, user_profile
        )

        admin_client.post(
            de(regular_user.id), {"nueva": "Tejado-Verde-91"}, format="json"
        )

        assert BlacklistedToken.objects.filter(token__jti=suya["jti"]).exists()
