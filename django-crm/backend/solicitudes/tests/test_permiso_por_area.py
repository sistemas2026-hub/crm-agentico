"""Quien ve y decide las solicitudes de instalacion (12/11/2026).

Hasta ese dia cualquier rol leia la bandeja, decidia y abria el PDF con la
foto de la cedula. Ahora: gestion, o una persona cuya AREA (la del motor) esta
en la lista que la empresa eligio. Sin ajuste o sin motor: solo gestion.
"""

from __future__ import annotations

import pytest
import requests
from django.core.cache import cache
from django.core.files.base import ContentFile

from operaciones import areas_del_tenant
#  La funcion REAL, tomada al importar: el conftest la reemplaza por {} en cada
#  prueba, y las del motor caido y del mapa verdadero necesitan la original.
from operaciones.areas_del_tenant import area_por_persona_de_org as AREAS_REALES
from solicitudes.models import AjustesDeInstalacion, SolicitudServicio
from solicitudes.tests.comun import Respuesta, cliente_de, persona, solicitud

AREA = "tecnica_de_prueba"


@pytest.fixture(autouse=True)
def _sin_cache():
    cache.clear()
    yield
    cache.clear()


def _areas(monkeypatch, mapa):
    monkeypatch.setattr(areas_del_tenant, "area_por_persona_de_org", lambda org_id: mapa)


def _elegir(org, *areas):
    AjustesDeInstalacion.objects.update_or_create(
        org=org, defaults={"areas_que_deciden": list(areas)})


# --- la bandeja ---------------------------------------------------------------

def test_area_en_la_lista_ve_la_bandeja(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): AREA})
    _elegir(org_a, AREA)
    solicitud(org_a)

    r = cliente_de(p).get("/api/solicitudes/bandeja/")

    assert r.status_code == 200
    assert len(r.json()["solicitudes"]) == 1


def test_el_area_se_compara_sin_mayusculas_ni_espacios(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): f"  {AREA.upper()} "})
    _elegir(org_a, AREA)

    assert cliente_de(p).get("/api/solicitudes/bandeja/").status_code == 200


def test_otra_area_no_ve_la_bandeja(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): "cartera"})
    _elegir(org_a, AREA)
    solicitud(org_a)

    r = cliente_de(p).get("/api/solicitudes/bandeja/")

    assert r.status_code == 403
    assert r.json()["codigo"] == "sin_permiso_instalaciones"
    assert "Ajustes → Instalaciones" in r.json()["error"]


def test_sin_ajuste_solo_gestion(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): AREA})       # tiene area, pero nadie la eligio
    jefe = persona(org_a, rol="OPERACIONES")

    assert cliente_de(p).get("/api/solicitudes/bandeja/").status_code == 403
    assert cliente_de(jefe).get("/api/solicitudes/bandeja/").status_code == 200


@pytest.mark.parametrize("rol", ["ADMIN", "SUPERVISOR", "OPERACIONES"])
def test_gestion_siempre_puede(org_a, rol):
    assert cliente_de(persona(org_a, rol=rol)).get("/api/solicitudes/bandeja/").status_code == 200


def test_motor_caido_solo_gestion(org_a, monkeypatch, empresa_del_motor):
    """El mapa REAL, con la red caida en el borde: no se sabe el area, no pasa."""
    p = persona(org_a)
    _elegir(org_a, AREA)
    empresa_del_motor(org_a, "empresa_prueba")
    monkeypatch.setattr(areas_del_tenant, "area_por_persona_de_org", AREAS_REALES)

    def caido(*a, **k):
        raise requests.ConnectionError("motor caido")

    monkeypatch.setattr(areas_del_tenant.requests, "get", caido)

    assert cliente_de(p).get("/api/solicitudes/bandeja/").status_code == 403
    assert cliente_de(persona(org_a, rol="ADMIN")).get(
        "/api/solicitudes/bandeja/").status_code == 200


def test_con_el_mapa_real_del_motor_pasa(org_a, monkeypatch, empresa_del_motor):
    """La cadena entera: el motor contesta su mapa y el permiso lo respeta."""
    p = persona(org_a)
    _elegir(org_a, AREA)
    empresa_del_motor(org_a, "empresa_prueba")
    monkeypatch.setattr(areas_del_tenant, "area_por_persona_de_org", AREAS_REALES)
    monkeypatch.setattr(areas_del_tenant.requests, "get",
                        lambda url, **k: Respuesta({"areas_por_persona": {str(p.id): AREA}}))

    assert cliente_de(p).get("/api/solicitudes/bandeja/").status_code == 200


# --- la decision y el expediente ------------------------------------------------

def test_otra_area_no_decide_y_no_cambia_nada(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): "cartera"})
    _elegir(org_a, AREA)
    s = solicitud(org_a)

    r = cliente_de(p).post(f"/api/solicitudes/{s.id}/decidir/",
                           {"aprueba": False, "nota": "no llega"}, format="json")

    assert r.status_code == 403
    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA


def test_area_en_la_lista_decide(org_a, monkeypatch):
    p = persona(org_a)
    _areas(monkeypatch, {str(p.id): AREA})
    _elegir(org_a, AREA)
    s = solicitud(org_a)

    r = cliente_de(p).post(f"/api/solicitudes/{s.id}/decidir/",
                           {"aprueba": True, "nota": ""}, format="json")

    assert r.status_code == 200
    s.refresh_from_db()
    assert s.estado == SolicitudServicio.APROBADA


def test_el_expediente_tambien_es_por_area(org_a, monkeypatch):
    p = persona(org_a)
    _elegir(org_a, AREA)
    s = solicitud(org_a)
    s.pdf.save("exp.pdf", ContentFile(b"%PDF-1.4 cedula"), save=True)

    _areas(monkeypatch, {str(p.id): "cartera"})
    negado = cliente_de(p).get(f"/api/solicitudes/{s.id}/expediente/")
    assert negado.status_code == 403
    assert b"cedula" not in negado.content

    _areas(monkeypatch, {str(p.id): AREA})
    permitido = cliente_de(p).get(f"/api/solicitudes/{s.id}/expediente/")
    assert permitido.status_code == 200
    assert permitido.content.startswith(b"%PDF")


# --- los ajustes ---------------------------------------------------------------

def test_solo_admin_elige_las_areas(org_a, monkeypatch):
    monkeypatch.setattr(requests, "request", lambda *a, **k: Respuesta({"areas": []}))
    usuario = persona(org_a)
    admin = persona(org_a, rol="ADMIN")

    r = cliente_de(usuario).put("/api/solicitudes/ajustes/decision/",
                                {"areas_que_deciden": [AREA]}, format="json")
    assert r.status_code == 403
    assert not AjustesDeInstalacion.objects.filter(org=org_a).exists()

    r = cliente_de(admin).put("/api/solicitudes/ajustes/decision/",
                              {"areas_que_deciden": [AREA, AREA.upper(), ""]}, format="json")
    assert r.status_code == 200
    assert r.json()["areas_que_deciden"] == [AREA]
    assert r.json()["prefactibilidad_activa"] is False


def test_los_ajustes_ofrecen_las_areas_del_motor(org_a, monkeypatch, empresa_del_motor):
    empresa_del_motor(org_a, "empresa_prueba")
    pedidas = []

    def motor(metodo, url, **k):
        pedidas.append((metodo, url, k.get("params")))
        return Respuesta({"areas": [{"nombre": AREA, "etiqueta": "Técnica"}]})

    monkeypatch.setattr(requests, "request", motor)
    r = cliente_de(persona(org_a)).get("/api/solicitudes/ajustes/decision/")

    assert r.status_code == 200
    assert r.json()["areas_disponibles"] == [{"nombre": AREA, "etiqueta": "Técnica"}]
    assert pedidas[0][1].endswith("/agentes/areas")
    assert pedidas[0][2] == {"tenant": "empresa_prueba"}


def test_guardar_los_equipos_manda_la_empresa_y_es_de_admin(org_a, monkeypatch,
                                                            empresa_del_motor):
    """El PUT al motor exige 'tenant' en el cuerpo y no lo llevaba."""
    empresa_del_motor(org_a, "empresa_prueba")
    cuerpos = []

    def motor(metodo, url, **k):
        if metodo == "PUT":
            cuerpos.append(k.get("json"))
        return Respuesta({"variables": {}})

    monkeypatch.setattr(requests, "request", motor)
    datos = {"tecnico_solicitudes": "11", "tecnico_aprobadas": "22"}

    assert cliente_de(persona(org_a)).put("/api/solicitudes/ajustes/", datos,
                                          format="json").status_code == 403
    assert cuerpos == []

    r = cliente_de(persona(org_a, rol="ADMIN")).put("/api/solicitudes/ajustes/", datos,
                                                     format="json")
    assert r.status_code == 200
    assert {"tenant": "empresa_prueba", "valor": "11"} in cuerpos
    assert all(c["tenant"] == "empresa_prueba" for c in cuerpos)
