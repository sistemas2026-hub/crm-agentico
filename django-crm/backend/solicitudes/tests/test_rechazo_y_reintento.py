"""Rechazar cierra el bucle; reintentar existe de verdad; el Lead sigue (12/11/2026).

El motor se dobla EN EL BORDE ('requests.post') con el contrato que el motor
real cumple y que importa aca: /interno/herramienta no repite una mutacion con
la misma 'Idempotency-Key', y /avisos/evento no manda dos veces la misma clave
(contesta 'ya_enviado'). La logica de solicitudes corre entera.
"""

from __future__ import annotations

import pytest
import requests

from leads.models import Lead
from solicitudes.models import SolicitudServicio
from solicitudes.tests.comun import Respuesta, cliente_de, persona, solicitud


class MotorFalso:
    def __init__(self):
        self.efectos = []          # (herramienta, cuerpo) que SI se ejecutaron
        self.claves_vistas = []    # Idempotency-Key de cada pedido
        self.avisos = []           # cuerpos de /avisos/evento
        self.enviados = set()      # claves de aviso ya mandadas
        self.herramienta_falla = False
        self.aviso_responde = None  # p. ej. {"enviado": False, "motivo": "apagado"}
        self._ejecutadas = set()

    def post(self, url, params=None, json=None, headers=None, timeout=None, **k):
        if url.endswith("/avisos/evento"):
            self.avisos.append(json)
            if self.aviso_responde is not None:
                return Respuesta(self.aviso_responde)
            if json["clave"] in self.enviados:
                return Respuesta({"enviado": False, "motivo": "ya_enviado"})
            self.enviados.add(json["clave"])
            return Respuesta({"enviado": True, "motivo": None})
        if "/interno/herramienta/" in url:
            clave = (headers or {}).get("Idempotency-Key")
            self.claves_vistas.append(clave)
            if self.herramienta_falla:
                return Respuesta({"error": "herramienta_fallo"}, 502)
            if clave and clave in self._ejecutadas:
                return Respuesta({"resultado": {}})       # 'repetida': no sale de nuevo
            if clave:
                self._ejecutadas.add(clave)
            self.efectos.append((url.rsplit("/", 1)[-1], json))
            return Respuesta({"resultado": {}})
        raise AssertionError(f"pedido inesperado al motor: {url}")


@pytest.fixture
def motor(monkeypatch, empresa_del_motor, org_a):
    m = MotorFalso()
    monkeypatch.setattr(requests, "post", m.post)
    empresa_del_motor(org_a, "empresa_prueba")
    return m


@pytest.fixture
def jefe(org_a):
    return cliente_de(persona(org_a, rol="OPERACIONES"))


def _rechazar(c, s, nota="Todavía no tenemos red en su sector"):
    return c.post(f"/api/solicitudes/{s.id}/decidir/", {"aprueba": False, "nota": nota},
                  format="json")


# --- rechazo -----------------------------------------------------------------

def test_rechazar_cierra_el_ticket_y_avisa_al_cliente(org_a, motor, jefe):
    lead = Lead.objects.create(org=org_a, title="Solicitud", phone="573001234567",
                               status="in process")
    s = solicitud(org_a, ticket_wisphub="95001", telefono="573001234567", lead=lead)

    r = _rechazar(jefe, s)

    assert r.status_code == 200
    s.refresh_from_db()
    assert s.estado == SolicitudServicio.SIN_FACTIBILIDAD
    # el ticket: una sola ejecucion, con clave de idempotencia
    cierres = [e for e in motor.efectos if e[0] == "cerrar_ticket_operativo"]
    assert len(cierres) == 1
    assert cierres[0][1]["id_ticket"] == "95001"
    assert "Todavía no tenemos red en su sector" in cierres[0][1]["respuesta"]
    assert motor.claves_vistas[0] == f"solicitud:{s.id}:cierre:0"
    assert s.ticket_cerrado_en is not None
    # el aviso: clave fija, el telefono de la solicitud y el motivo
    assert len(motor.avisos) == 1
    aviso = motor.avisos[0]
    assert aviso["evento"] == "solicitud_sin_factibilidad"
    assert aviso["clave"] == f"solicitud:{s.id}:sin_factibilidad"
    assert aviso["telefono"] == "573001234567"
    assert aviso["contexto"]["motivo_factibilidad"] == "Todavía no tenemos red en su sector"
    assert "direccion" not in str(aviso["contexto"]).lower()
    assert r.json()["aviso_cliente"]["estado"] == "enviado"
    assert r.json()["pendientes"] == []
    # el prospecto
    lead.refresh_from_db()
    assert lead.status == "closed"


def test_decidir_dos_veces_cierra_y_avisa_una_sola_vez(org_a, motor, jefe):
    s = solicitud(org_a, ticket_wisphub="95002")

    assert _rechazar(jefe, s).status_code == 200
    segunda = _rechazar(jefe, s, nota="otra nota")

    assert segunda.status_code == 409
    assert len([e for e in motor.efectos if e[0] == "cerrar_ticket_operativo"]) == 1
    assert len(motor.avisos) == 1
    s.refresh_from_db()
    assert s.nota_revision == "Todavía no tenemos red en su sector"


def test_dos_personas_a_la_vez_deciden_una_sola_vez(org_a, motor):
    """La carrera: las dos leyeron la solicitud 'enviada' antes de decidir. El
    409 de la vista no la ve (las dos pasaron ese control); la ve el UPDATE
    condicionado de decision.decidir."""
    from solicitudes import decision

    s = solicitud(org_a, ticket_wisphub="95010")
    una = SolicitudServicio.objects.get(pk=s.pk)
    otra = SolicitudServicio.objects.get(pk=s.pk)

    assert decision.decidir(una, aprueba=False, nota="no hay red") is True
    assert decision.decidir(otra, aprueba=True, nota="") is False

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.SIN_FACTIBILIDAD
    assert len(motor.avisos) == 1
    assert [e[0] for e in motor.efectos] == ["cerrar_ticket_operativo"]


def test_sin_plantilla_el_rechazo_queda_y_la_pantalla_dice_que_falta(org_a, motor, jefe):
    motor.aviso_responde = {"enviado": False, "motivo": "apagado"}
    s = solicitud(org_a, ticket_wisphub="95003")

    r = _rechazar(jefe, s)

    assert r.status_code == 200
    s.refresh_from_db()
    assert s.estado == SolicitudServicio.SIN_FACTIBILIDAD
    assert s.ticket_cerrado_en is not None
    datos = r.json()["aviso_cliente"]
    assert datos["estado"] == "no_enviado"
    assert "falta la plantilla" in datos["texto"]
    assert "Solicitud sin factibilidad" in datos["texto"]
    assert r.json()["pendientes"] == ["aviso"]


def test_reintentar_el_aviso_no_manda_dos(org_a, motor, jefe):
    motor.aviso_responde = {"enviado": False, "motivo": "apagado"}
    s = solicitud(org_a, ticket_wisphub="95004")
    _rechazar(jefe, s)

    # el administrador configuro la plantilla
    motor.aviso_responde = None
    r = jefe.post(f"/api/solicitudes/{s.id}/reintentar/", {}, format="json")
    assert r.status_code == 200
    assert r.json()["aviso_cliente"]["estado"] == "enviado"
    assert r.json()["pendientes"] == []

    # un reintento mas: no hay nada pendiente, y el motor no mando nada nuevo
    otra = jefe.post(f"/api/solicitudes/{s.id}/reintentar/", {}, format="json")
    assert otra.status_code == 409
    assert len(motor.enviados) == 1
    assert {a["clave"] for a in motor.avisos} == {f"solicitud:{s.id}:sin_factibilidad"}


# --- reintento de la integracion ------------------------------------------------

def test_aprobada_con_reasignacion_fallida_se_reintenta(org_a, motor, jefe):
    lead = Lead.objects.create(org=org_a, title="Solicitud", phone="1", status="in process")
    s = solicitud(org_a, ticket_wisphub="95005", lead=lead)
    motor.herramienta_falla = True

    r = jefe.post(f"/api/solicitudes/{s.id}/decidir/", {"aprueba": True, "nota": ""},
                  format="json")

    assert r.status_code == 200
    assert r.json()["pendientes"] == ["reasignacion"]
    assert "reasignacion: HTTP 502 herramienta_fallo" in r.json()["fallo"]
    lead.refresh_from_db()
    assert lead.status == "converted"

    motor.herramienta_falla = False
    r = jefe.post(f"/api/solicitudes/{s.id}/reintentar/", {}, format="json")

    assert r.status_code == 200
    assert r.json()["pendientes"] == []
    s.refresh_from_db()
    assert s.ticket_reasignado_en is not None
    assert [e[0] for e in motor.efectos] == ["reasignar_ticket_instalacion"]
    # el intento nuevo lleva otra clave: el fallido no bloquea al siguiente
    assert motor.claves_vistas == [f"solicitud:{s.id}:reasignacion:0",
                                   f"solicitud:{s.id}:reasignacion:1"]


def test_reintentar_sin_nada_pendiente_es_409(org_a, motor, jefe):
    s = solicitud(org_a, ticket_wisphub="95006")
    jefe.post(f"/api/solicitudes/{s.id}/decidir/", {"aprueba": True, "nota": ""}, format="json")

    r = jefe.post(f"/api/solicitudes/{s.id}/reintentar/", {}, format="json")

    assert r.status_code == 409
    assert len(motor.efectos) == 1


def test_reintentar_tambien_es_por_area(org_a, motor):
    s = solicitud(org_a, ticket_wisphub="95007", estado=SolicitudServicio.APROBADA)
    r = cliente_de(persona(org_a)).post(f"/api/solicitudes/{s.id}/reintentar/", {},
                                         format="json")
    assert r.status_code == 403
    assert motor.efectos == []


def test_la_cancelacion_sella_el_cierre_y_cierra_el_prospecto(org_a, motor, jefe):
    lead = Lead.objects.create(org=org_a, title="Solicitud", phone="1", status="in process")
    s = solicitud(org_a, ticket_wisphub="95008", lead=lead, numero_documento="999")

    r = jefe.post("/api/solicitudes/cancelar/",
                  {"numero_documento": "999", "nombre_confirmado": "ana prueba",
                   "motivo": "consegui otro operador mas barato"}, format="json")

    assert r.status_code == 200
    s.refresh_from_db()
    assert s.ticket_cerrado_en is not None
    assert "consegui otro operador" in motor.efectos[0][1]["respuesta"]
    lead.refresh_from_db()
    assert lead.status == "closed"


def test_bandeja_muestra_el_prospecto_y_lo_pendiente(org_a, motor, jefe):
    lead = Lead.objects.create(org=org_a, title="Solicitud", phone="1", status="assigned")
    solicitud(org_a, lead=lead)

    fila = jefe.get("/api/solicitudes/bandeja/").json()["solicitudes"][0]

    assert fila["lead_id"] == str(lead.id)
    assert fila["pendientes"] == []
    assert fila["decision_automatica"] is False
