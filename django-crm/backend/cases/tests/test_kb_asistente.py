"""Un articulo aprobado y publicado entra al corpus del asistente; despublicado, sale.

12/11/2026. Lo que se prueba es la cadena real: la API de /solutions -> la
señal -> la tarea -> el pedido HTTP al motor, con el motor doblado SOLO en su
borde HTTP (`requests.post`). Lo que el motor hace con el archivo (fragmentar,
vectorizar) lo prueba el motor; aca se comprueba que le llega por la MISMA
puerta que un Documento (`POST /corpus/documentos`) y que el estado vuelve a
la pantalla.
"""

import io
import zipfile

import pytest
import requests
from rest_framework import status

from cases import kb_asistente
from cases.models import Solution

URL = "http://motor.prueba"


class _Respuesta:
    def __init__(self, codigo, cuerpo):
        self.status_code = codigo
        self.ok = 200 <= codigo < 300
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


class MotorDoblado:
    """El motor, visto desde el backend: tres rutas del corpus."""

    def __init__(self):
        self.llamadas = []
        self.siguiente = 0
        self.falla_ingesta = None

    def __call__(self, url, **kw):
        ruta = url[len(URL):]
        self.llamadas.append((ruta, kw))
        if ruta == "/corpus/documentos":
            if self.falla_ingesta:
                return _Respuesta(400, {"error": self.falla_ingesta})
            self.siguiente += 1
            return _Respuesta(201, {
                "document_id": f"doc-{self.siguiente}", "estado": "pendiente",
                "fragmentos": 2,
                "roles_permitidos": [r for r in (kw["data"]["roles"] or "").split(",") if r],
            })
        if ruta.endswith("/aprobar"):
            return _Respuesta(200, {"aprobado": True})
        if ruta.endswith("/retirar"):
            return _Respuesta(200, {"retirado": True})
        return _Respuesta(404, {"error": "ruta desconocida"})

    def rutas(self):
        return [r for r, _ in self.llamadas]


@pytest.fixture
def motor(monkeypatch, empresa_del_motor, org_a):
    monkeypatch.setenv("ASISTENTE_URL", URL)
    empresa_del_motor(org_a, "empresa-prueba")
    doble = MotorDoblado()
    monkeypatch.setattr(requests, "post", doble)
    # Celery corre la tarea en el acto: lo que se prueba es la tarea, no el broker.
    for tarea in (kb_asistente.ingerir_articulo_en_asistente,
                  kb_asistente.retirar_articulo_del_asistente):
        monkeypatch.setattr(tarea, "delay", tarea)
    return doble


def _articulo(admin_client, **extra):
    datos = {"title": "Cómo reiniciar la ONT", "description": "Desenchufe 30 segundos.",
             "status": "approved", "roles_asistente": "soporte"}
    datos.update(extra)
    r = admin_client.post("/api/cases/solutions/", datos, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    return Solution.objects.get(id=r.data["id"])


@pytest.mark.django_db
class TestPublicarLoMeteEnElAsistente:
    def test_publicar_lo_ingiere_por_el_camino_de_documentos(
        self, admin_client, motor, django_capture_on_commit_callbacks
    ):
        sol = _articulo(admin_client)
        assert motor.llamadas == []  # aprobado pero sin publicar: afuera

        with django_capture_on_commit_callbacks(execute=True):
            r = admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        assert r.status_code == status.HTTP_200_OK

        assert motor.rutas() == ["/corpus/documentos", "/corpus/documentos/doc-1/aprobar"]
        _, kw = motor.llamadas[0]
        assert kw["data"]["tenant"] == "empresa-prueba"
        assert kw["data"]["roles"] == "soporte"
        nombre, contenido = kw["files"]["archivo"]
        assert nombre.endswith("-v1.docx")
        xml = zipfile.ZipFile(io.BytesIO(contenido)).read("word/document.xml").decode()
        assert "Cómo reiniciar la ONT" in xml and "Desenchufe 30 segundos." in xml

        # Y la pantalla lo ve: el estado llega por la API del articulo.
        d = admin_client.get(f"/api/cases/solutions/{sol.id}/").data
        assert d["estado_ingesta"] == "ok"
        assert d["corpus_document_id"] == "doc-1"
        assert d["ingesta_fragmentos"] == 2

    def test_despublicar_lo_retira(self, admin_client, motor, django_capture_on_commit_callbacks):
        sol = _articulo(admin_client)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/unpublish/")

        assert motor.rutas()[-1] == "/corpus/documentos/doc-1/retirar"
        sol.refresh_from_db()
        assert sol.estado_ingesta == "retirado"
        assert sol.corpus_document_id is None

        # Republicarlo es una version NUEVA: la retirada no revive.
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        sol.refresh_from_db()
        assert sol.corpus_document_id == "doc-2" and sol.version_corpus == 2

    def test_editar_uno_publicado_sube_version_y_retira_la_vieja(
        self, admin_client, motor, django_capture_on_commit_callbacks
    ):
        sol = _articulo(admin_client)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        with django_capture_on_commit_callbacks(execute=True):
            r = admin_client.patch(f"/api/cases/solutions/{sol.id}/",
                                   {"description": "Desenchufe 60 segundos."}, format="json")
        assert r.status_code == status.HTTP_200_OK
        assert motor.rutas()[-3:] == ["/corpus/documentos", "/corpus/documentos/doc-2/aprobar",
                                      "/corpus/documentos/doc-1/retirar"]
        sol.refresh_from_db()
        assert sol.corpus_document_id == "doc-2"

    def test_guardar_sin_cambios_no_reingiere(
        self, admin_client, motor, django_capture_on_commit_callbacks
    ):
        sol = _articulo(admin_client)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        antes = len(motor.llamadas)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.patch(f"/api/cases/solutions/{sol.id}/",
                               {"title": "Cómo reiniciar la ONT"}, format="json")
        assert len(motor.llamadas) == antes

    def test_un_borrador_nunca_llega(self, admin_client, motor, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            _articulo(admin_client, status="draft")
        assert motor.llamadas == []

    def test_el_error_del_motor_queda_visible(
        self, admin_client, motor, django_capture_on_commit_callbacks
    ):
        motor.falla_ingesta = "El documento declara rol(es) inexistente(s): soporte."
        sol = _articulo(admin_client)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        sol.refresh_from_db()
        assert sol.estado_ingesta == "error"
        assert "inexistente" in sol.ingesta_detalle
        assert sol.corpus_document_id is None

    def test_quien_solo_escribe_no_cambia_lo_que_dice_el_asistente(
        self, admin_client, user_client, user_profile, motor,
        django_capture_on_commit_callbacks,
    ):
        sol = _articulo(admin_client)
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(f"/api/cases/solutions/{sol.id}/publish/")
        # El autor (no admin) no puede cambiar el texto de uno publicado ni
        # a que agentes se le cita: es publicar por la puerta de al lado.
        Solution.objects.filter(id=sol.id).update(created_by=user_profile.user)
        # Puede escribir (un PATCH que no cambia nada pasa): el 403 de abajo
        # es por publicar, no por no poder tocar el articulo.
        ok = user_client.patch(f"/api/cases/solutions/{sol.id}/", {"status": "approved"},
                               format="json")
        assert ok.status_code == status.HTTP_200_OK, ok.data
        for cambio in ({"description": "otra cosa"}, {"roles_asistente": "ventas"}):
            r = user_client.patch(f"/api/cases/solutions/{sol.id}/", cambio, format="json")
            assert r.status_code == status.HTTP_403_FORBIDDEN, (cambio, r.status_code)
