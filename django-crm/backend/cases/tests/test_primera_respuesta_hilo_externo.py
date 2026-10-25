"""
UNA RESPUESTA EN WISPHUB CUENTA COMO PRIMERA RESPUESTA.

Hasta el 25/10/2026 la primera respuesta solo la sellaba un comentario publico
escrito en Dexter. Los tickets que nacen por telefono se abren y se trabajan en
WispHub, y su hilo llegaba aca por la importacion -- se guardaba y no contaba:
el ticket figuraba "sin primera respuesta" para siempre.

Se prueba por el camino REAL -- el endpoint que usa la importacion --, no
llamando a la senal: lo que importa es que el hilo que llega selle el caso.

Run with: pytest cases/tests/test_primera_respuesta_hilo_externo.py -v
"""

from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as registro
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from cases.models import Case, RespuestaExterna
from common.models import Comment

MIGRACION = import_module("cases.migrations.0034_primera_respuesta_desde_el_hilo_externo")

AHORA = timezone.now().replace(microsecond=0)


def _caso(org, autor, hace_horas=10, ticket="91865"):
    caso = Case.objects.create(
        name="Sin internet", status="New", priority="Normal", org=org,
        created_by=autor, provider="wisphub", external_ticket_id=ticket,
        external_service_id="5832", external_status="Nuevo")
    Case.objects.filter(pk=caso.pk).update(created_at=AHORA - timedelta(hours=hace_horas))
    caso.refresh_from_db()
    return caso


def _hilo(cliente, caso, *filas):
    return cliente.post(
        f"/api/importacion/casos/{caso.pk}/respuestas/",
        {"provider": "wisphub", "respuestas": list(filas)}, format="json")


def _fila(huella, hace_horas, usuario="tecnico.uno"):
    return {"huella": huella, "autor_nombre": "Tecnico Uno", "autor_usuario": usuario,
            "cuerpo": "Se reviso la ONU",
            "creada_en_proveedor": (AHORA - timedelta(hours=hace_horas)).isoformat()}


def _primera(caso):
    caso.refresh_from_db()
    return caso.first_response_at


@pytest.mark.django_db
class TestElHiloSellaLaPrimeraRespuesta:
    def test_una_respuesta_del_equipo_sella_con_su_hora(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user, hace_horas=10)
        r = _hilo(admin_client, caso, _fila("a", hace_horas=8), _fila("b", hace_horas=3))
        assert r.status_code == 200, r.content
        assert _primera(caso) == AHORA - timedelta(hours=8)

    def test_respondida_antes_de_importarse_cuenta_desde_que_llego(
        self, admin_client, org_a, admin_user
    ):
        caso = _caso(org_a, admin_user, hace_horas=2)
        _hilo(admin_client, caso, _fila("a", hace_horas=5))
        assert _primera(caso) == caso.created_at

    def test_sin_usuario_del_proveedor_no_cuenta(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        _hilo(admin_client, caso, _fila("a", hace_horas=4, usuario=""))
        assert _primera(caso) is None

    def test_sin_fecha_no_se_inventa_un_momento(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        fila = _fila("a", hace_horas=4)
        fila["creada_en_proveedor"] = None
        _hilo(admin_client, caso, fila)
        assert _primera(caso) is None

    def test_una_respuesta_anterior_que_llega_tarde_corre_el_sello(
        self, admin_client, org_a, admin_user, admin_profile
    ):
        """El comentario de aca sello primero; despues llego el hilo de
        WispHub, con una respuesta anterior. Gana la mas temprana."""
        caso = _caso(org_a, admin_user, hace_horas=10)
        Comment.objects.create(comment="Ya lo estamos viendo",
                               content_type=ContentType.objects.get_for_model(Case),
                               object_id=caso.id,
                               commented_by=admin_profile, org=org_a)
        sello_del_comentario = _primera(caso)
        assert sello_del_comentario is not None
        _hilo(admin_client, caso, _fila("a", hace_horas=9))
        assert _primera(caso) == AHORA - timedelta(hours=9)

    def test_una_respuesta_posterior_no_mueve_el_sello(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user, hace_horas=10)
        _hilo(admin_client, caso, _fila("a", hace_horas=9))
        _hilo(admin_client, caso, _fila("b", hace_horas=1))
        assert _primera(caso) == AHORA - timedelta(hours=9)

    def test_reenviar_el_mismo_hilo_no_cambia_nada(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        _hilo(admin_client, caso, _fila("a", hace_horas=4))
        antes = _primera(caso)
        r = _hilo(admin_client, caso, _fila("a", hace_horas=4))
        assert r.json()["ya_estaban"] == 1
        assert _primera(caso) == antes


@pytest.mark.django_db
class TestLaMigracionCompletaLoQueYaEstaba:
    def test_sella_con_la_mas_temprana_y_respeta_los_bordes(self, org_a, admin_user):
        con_hilo = _caso(org_a, admin_user, hace_horas=10)
        antes_de_existir = _caso(org_a, admin_user, hace_horas=2, ticket="91866")
        sin_usuario = _caso(org_a, admin_user, hace_horas=10, ticket="91867")

        def fila(caso, huella, hace_horas, usuario="tecnico.uno"):
            return RespuestaExterna(
                org=org_a, case=caso, provider="wisphub", huella=huella,
                autor_usuario=usuario,
                creada_en_proveedor=AHORA - timedelta(hours=hace_horas))

        #  bulk_create no dispara senales: son las filas que ya estaban en la
        #  base antes de que la senal existiera.
        RespuestaExterna.objects.bulk_create([
            fila(con_hilo, "a", 3), fila(con_hilo, "b", 7),
            fila(antes_de_existir, "c", 5),
            fila(sin_usuario, "d", 4, usuario=""),
        ])
        assert _primera(con_hilo) is None

        MIGRACION.adelante(registro, None)

        assert _primera(con_hilo) == AHORA - timedelta(hours=7)
        assert _primera(antes_de_existir) == antes_de_existir.created_at
        assert _primera(sin_usuario) is None

        # Correrla otra vez no cambia nada.
        MIGRACION.adelante(registro, None)
        assert _primera(con_hilo) == AHORA - timedelta(hours=7)


@pytest.mark.django_db
class TestElHiloAjenoNoMaquillaElIndicador:
    def test_quien_no_puede_escribir_el_caso_guarda_el_hilo_pero_no_sella(
        self, user_client, org_a, admin_user
    ):
        """La ruta de importacion acepta a cualquiera de la organizacion. El
        hilo se guarda igual; el sello no, si quien lo manda no podria haberlo
        sellado comentando."""
        caso = _caso(org_a, admin_user)
        r = _hilo(user_client, caso, _fila("a", hace_horas=4))
        assert r.status_code == 200, r.content
        assert RespuestaExterna.objects.filter(case=caso).count() == 1
        assert _primera(caso) is None


def _bandeja(cliente, caso, momento):
    cuerpo = {} if momento is None else {"momento": momento}
    return cliente.post(f"/api/cases/{caso.pk}/primera-respuesta/", cuerpo, format="json")


@pytest.mark.django_db
class TestLaBandejaAvisaLaPrimeraRespuesta:
    def test_sella_con_el_momento_que_manda_el_motor(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user, hace_horas=10)
        momento = AHORA - timedelta(hours=6)
        r = _bandeja(admin_client, caso, momento.isoformat())
        assert r.status_code == 200, r.content
        assert _primera(caso) == momento

    def test_una_posterior_no_corre_la_que_ya_estaba(self, admin_client, org_a, admin_user):
        caso = _caso(org_a, admin_user, hace_horas=10)
        _bandeja(admin_client, caso, (AHORA - timedelta(hours=6)).isoformat())
        _bandeja(admin_client, caso, (AHORA - timedelta(hours=1)).isoformat())
        assert _primera(caso) == AHORA - timedelta(hours=6)

    def test_quien_no_puede_escribir_el_caso_no_sella(self, user_client, org_a, admin_user):
        caso = _caso(org_a, admin_user)
        r = _bandeja(user_client, caso, (AHORA - timedelta(hours=1)).isoformat())
        assert r.status_code == 403
        assert _primera(caso) is None

    @pytest.mark.parametrize("momento, codigo", [
        (None, "MOMENTO_INVALIDO"),
        ("ayer", "MOMENTO_INVALIDO"),
        ("2026-10-25T09:00:00", "MOMENTO_INVALIDO"),   # sin zona
        ((AHORA + timedelta(hours=1)).isoformat(), "MOMENTO_FUTURO"),
    ])
    def test_un_momento_roto_se_rechaza_y_no_sella(
        self, admin_client, org_a, admin_user, momento, codigo
    ):
        caso = _caso(org_a, admin_user)
        r = _bandeja(admin_client, caso, momento)
        assert r.status_code == 400
        assert r.json()["codigo"] == codigo
        assert _primera(caso) is None
