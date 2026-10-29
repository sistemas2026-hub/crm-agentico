"""La encuesta por WhatsApp al cerrar un caso, del lado del CRM (28/10/2026).

El CRM solo PIDE: que el caso siga cerrado, a quien, y con quien lo tenia.
Decide el motor (apagada, sin chat, de baja...). Lo que se afirma es lo que
le llega al motor -- y que un motor caido no rompe el cierre.

'apply_async' se reemplaza por una version que la corre en el acto y anota la
espera: medido el 28/10/2026, en este entorno de pruebas Celery NO corre en
linea (intenta el broker y la señal se lo traga), asi que sin esto la prueba
del cierre no ejecutaba la tarea y pasaba en verde por no hacer nada.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from cases.models import Case
from cases.tasks import enviar_encuesta_whatsapp


class _Resp:
    def __init__(self, status=200, cuerpo=None):
        self.status_code = status
        self._c = cuerpo or {"enviada": True, "motivo": None}
        self.content = b"x"

    def json(self):
        return self._c


ESPERAS: list = []


@pytest.fixture(autouse=True)
def en_el_acto(monkeypatch):
    """La tarea agendada corre en el momento; la espera queda anotada."""
    ESPERAS.clear()

    def agendar(args=None, countdown=None, **kw):
        ESPERAS.append(countdown)
        return enviar_encuesta_whatsapp(*args)

    monkeypatch.setattr(enviar_encuesta_whatsapp, "apply_async", agendar)


@pytest.fixture
def motor(monkeypatch):
    """El motor configurado, con requests.post espiado."""
    import requests

    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000/")
    monkeypatch.setenv("ASISTENTE_TENANT", "empresa")
    monkeypatch.setenv("MOTOR_SERVICE_TOKEN", "tok-servicio")
    pedidos = []

    def post(url, json=None, headers=None, timeout=None):
        pedidos.append({"url": url, "json": json, "headers": headers})
        return _Resp()

    monkeypatch.setattr(requests, "post", post)
    return pedidos


@pytest.fixture
def caso_abierto(org_a, admin_profile):
    caso = Case.objects.create(org=org_a, name="Sin internet", status="Assigned",
                               priority="Normal", area="soporte_tecnico")
    caso.assigned_to.add(admin_profile)
    return caso


@pytest.mark.django_db
class TestEncuestaAlCerrar:
    def test_cerrar_el_caso_le_pide_la_encuesta_al_motor(self, motor, caso_abierto, admin_profile):
        caso_abierto.status = "Closed"
        caso_abierto.closed_on = timezone.localdate()
        caso_abierto.save()
        pedidos = [p for p in motor if p["url"].endswith("/encuesta")]
        assert len(pedidos) == 1
        # Se pide EN EL ACTO, con la hora del cierre: la espera la aplica el motor.
        assert ESPERAS == [0]
        p = pedidos[0]
        assert p["json"]["cerrado_en"]
        assert p["url"] == f"http://motor:5000/casos/{caso_abierto.id}/encuesta"
        assert p["headers"] == {"X-Servicio-Token": "tok-servicio"}
        assert p["json"]["tenant"] == "empresa"
        assert p["json"]["responsable_id"] == str(admin_profile.id)
        assert p["json"]["responsable_nombre"]
        assert p["json"]["area"] == "soporte_tecnico"

    def test_otro_cambio_de_estado_no_pide_nada(self, motor, caso_abierto):
        caso_abierto.status = "Pending"
        caso_abierto.save()
        assert not [p for p in motor if p["url"].endswith("/encuesta")]

    def test_un_caso_reabierto_antes_de_la_espera_no_la_pide(self, motor, caso_abierto, org_a):
        caso_abierto.status = "New"
        caso_abierto.save()
        assert enviar_encuesta_whatsapp(str(caso_abierto.id), str(org_a.id)) is None
        assert not [p for p in motor if p["url"].endswith("/encuesta")]

    def test_sin_asistente_configurado_no_sale_nada(self, monkeypatch, caso_abierto, org_a):
        import requests

        monkeypatch.delenv("ASISTENTE_URL", raising=False)
        llamadas = []
        monkeypatch.setattr(requests, "post", lambda *a, **k: llamadas.append(a))
        Case.objects.filter(pk=caso_abierto.pk).update(status="Closed")
        assert enviar_encuesta_whatsapp(str(caso_abierto.id), str(org_a.id)) is None
        assert llamadas == []

    def test_un_motor_caido_no_rompe_el_cierre(self, monkeypatch, caso_abierto):
        import requests

        monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
        monkeypatch.setenv("ASISTENTE_TENANT", "empresa")

        def cae(*a, **k):
            raise requests.ConnectionError("motor caido")

        monkeypatch.setattr(requests, "post", cae)
        caso_abierto.status = "Closed"
        caso_abierto.closed_on = timezone.localdate()
        caso_abierto.save()
        caso_abierto.refresh_from_db()
        assert caso_abierto.status == "Closed"
        assert ESPERAS == [0]  # la tarea si corrio, y no rompio nada

    def test_sin_responsable_va_vacio_no_inventado(self, motor, org_a):
        caso = Case.objects.create(org=org_a, name="x", status="Closed", priority="Normal")
        enviar_encuesta_whatsapp(str(caso.id), str(org_a.id))
        p = [x for x in motor if x["url"].endswith("/encuesta")][-1]
        assert p["json"]["responsable_id"] is None and p["json"]["area"] is None

    def test_todavia_no_vuelve_a_preguntar_cuando_dice_el_motor_y_con_tope(
            self, monkeypatch, caso_abierto):
        """La espera de la empresa (29/10/2026): el motor dice en cuantos
        segundos volver; se vuelve a preguntar, y no para siempre."""
        import requests

        from cases.tasks import ENCUESTA_MAX_VUELTAS

        monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
        monkeypatch.setenv("ASISTENTE_TENANT", "empresa")
        pedidos = []

        def post(url, json=None, headers=None, timeout=None):
            pedidos.append(json)
            return _Resp(cuerpo={"enviada": False, "motivo": "todavia_no", "reintentar_en": 300})

        monkeypatch.setattr(requests, "post", post)
        caso_abierto.status = "Closed"
        caso_abierto.closed_on = timezone.localdate()
        caso_abierto.save()
        assert ESPERAS == [0] + [300] * ENCUESTA_MAX_VUELTAS
        assert len(pedidos) == 1 + ENCUESTA_MAX_VUELTAS
        # Todas las vueltas llevan la MISMA hora de cierre: la espera no se corre.
        assert len({p["cerrado_en"] for p in pedidos}) == 1

    def test_reabierto_entre_vueltas_no_la_pide_mas(self, monkeypatch, caso_abierto, org_a):
        import requests

        monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
        monkeypatch.setenv("ASISTENTE_TENANT", "empresa")
        pedidos = []

        def post(url, json=None, headers=None, timeout=None):
            pedidos.append(json)
            # Mientras el motor hace esperar, alguien reabre el caso.
            Case.objects.filter(pk=caso_abierto.pk).update(status="New")
            return _Resp(cuerpo={"enviada": False, "motivo": "todavia_no", "reintentar_en": 60})

        monkeypatch.setattr(requests, "post", post)
        caso_abierto.status = "Closed"
        caso_abierto.closed_on = timezone.localdate()
        caso_abierto.save()
        assert len(pedidos) == 1, "la segunda vuelta mira el caso, lo ve abierto y no pregunta"
