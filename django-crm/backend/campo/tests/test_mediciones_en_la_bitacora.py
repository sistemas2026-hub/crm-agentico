# -*- coding: utf-8 -*-
"""
Medir la señal y probar la conexión dejan rastro en la bitácora.

18/10/2026: las dos rutas devolvían el resultado al teléfono y no guardaban
nada. Se perdía cómo quedó el servicio DESPUÉS de la visita. Estas pruebas van
por la cadena real: el POST que hace la app y el GET de la bitácora que lee la
oficina. Lo único simulado es la llamada al equipo del cliente.
"""

from datetime import timedelta

import pytest

from campo.models import AsignacionTrabajo, EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

SENAL_BUENA = {"ok": True, "medido_en": "2026-10-18T19:00:00+00:00",
               "lectura": {"onu_signal_1490": -19.4, "onu_signal_1490_veredicto": "aceptable",
                           "onu_signal_1310": -23.1, "onu_status": "Online"}}


@pytest.fixture
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="med", nombre="Reparación")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=7101, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        contexto={"servicio": "WH-1", "sn_onu": "ZTEG1"})
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    return o


def _medir(client, orden, monkeypatch, resultado):
    monkeypatch.setattr("campo.views.telemetria.medir_senal", lambda o: resultado)
    return client.post(f"/api/campo/trabajos/{orden.id}/medir-senal/")


def _ping(client, orden, monkeypatch, resultado):
    monkeypatch.setattr("campo.views.probar_conexion", lambda o, paquetes: resultado)
    return client.post(f"/api/campo/trabajos/{orden.id}/probar-conexion/",
                       {"paquetes": 3}, format="json")


def _renglones(client, orden, tipo):
    r = client.get(f"/api/campo/trabajos/{orden.id}/seguimiento/")
    assert r.status_code == 200
    return [e for e in r.data["eventos"] if e["tipo"] == tipo]


def _tres(si):
    return {"ok": True, "respondieron": f"{si} de 3",
            "paquetes": [{"respondio": True}] * 3}


def test_1_la_senal_medida_queda_con_sus_niveles_en_palabras(user_client, orden, monkeypatch):
    assert _medir(user_client, orden, monkeypatch, SENAL_BUENA).status_code == 200

    [fila] = _renglones(user_client, orden, "senal_medida")
    assert fila["etiqueta"] == "Señal medida en el sitio"
    assert fila["datos"]["resultado"] == (
        "1490 nm: -19.4 (aceptable) · 1310 nm: -23.1 · estado Online")
    assert fila["quien"]
    # Los niveles crudos quedan guardados para comparar, y no se vuelcan.
    evento = EventoTrabajo.objects.get(orden=orden, tipo="senal_medida")
    assert evento.datos["lectura"]["onu_signal_1490"] == -19.4
    assert set(fila["datos"]) == {"resultado"}


def test_2_no_se_pudo_medir_tambien_se_anota_y_dice_por_que(user_client, orden, monkeypatch):
    _medir(user_client, orden, monkeypatch, {"ok": False, "motivo": "motor_no_responde"})
    [fila] = _renglones(user_client, orden, "senal_medida")
    assert fila["datos"]["resultado"] == "No se pudo medir: el sistema de medición no respondió"


def test_3_la_ficha_congelada_no_se_pisa(user_client, orden, monkeypatch):
    _medir(user_client, orden, monkeypatch, SENAL_BUENA)
    orden.refresh_from_db()
    assert orden.contexto == {"servicio": "WH-1", "sn_onu": "ZTEG1"}


def test_4_las_tres_tandas_de_una_prueba_son_un_renglon(user_client, orden, monkeypatch):
    for si in (3, 2, 3):
        assert _ping(user_client, orden, monkeypatch, _tres(si)).status_code == 200

    filas = _renglones(user_client, orden, "conexion_probada")
    assert len(filas) == 1
    assert filas[0]["datos"]["resultado"] == "Respondieron 8 de 9 paquetes"
    # En la base son tres hechos: la bitácora no se edita.
    assert EventoTrabajo.objects.filter(orden=orden, tipo="conexion_probada").count() == 3


def test_5_dos_pruebas_separadas_son_dos_renglones(user_client, orden, monkeypatch):
    _ping(user_client, orden, monkeypatch, _tres(3))
    EventoTrabajo.objects.filter(orden=orden, tipo="conexion_probada").update(
        created_at=EventoTrabajo.objects.get(orden=orden).created_at - timedelta(minutes=30))
    _ping(user_client, orden, monkeypatch, _tres(0))

    filas = _renglones(user_client, orden, "conexion_probada")
    assert [f["datos"]["resultado"] for f in filas] == [
        "Respondieron 3 de 3 paquetes", "Respondieron 0 de 3 paquetes"]


def test_6_una_tanda_que_fallo_se_dice_junto_a_las_que_respondieron(user_client, orden, monkeypatch):
    _ping(user_client, orden, monkeypatch, _tres(3))
    _ping(user_client, orden, monkeypatch, {"ok": False, "motivo": "sin_conteo"})
    [fila] = _renglones(user_client, orden, "conexion_probada")
    assert fila["datos"]["resultado"] == (
        "Respondieron 3 de 3 paquetes · No se pudo probar: no llegó el conteo de paquetes")


def test_7_si_la_bitacora_falla_el_tecnico_igual_recibe_la_medicion(user_client, orden, monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("base caida")
    monkeypatch.setattr("campo.services.mediciones.EventoTrabajo.objects.create", explota)

    r = _medir(user_client, orden, monkeypatch, SENAL_BUENA)

    assert r.status_code == 200
    assert r.json()["lectura"]["onu_signal_1490"] == -19.4
