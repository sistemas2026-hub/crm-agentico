# -*- coding: utf-8 -*-
"""
================================================================================
 LAS ORDENES CERRADAS  --  30/10/2026
================================================================================
La pestaña Cerradas de Programacion. Ver `campo/ordenes_cerradas.py`.

  C1  cerrada por una PERSONA desde la web: dice quien, el ticket del ISP, que
      hizo el tecnico y LA FOTO de lo que reviso el Supervisor al aprobar.
  C2  cerrada por el SUPERVISOR: «El Supervisor», con su foto.
  C3  el historial es de ESA orden: salio, llego, reporto, termino, la aprobo,
      el ticket; nada de otra orden. La que llego otro dia dice cuando.
  C4  el rango es el dia de la empresa: lo de ayer no sale hoy.
  C5  solo quien gestiona; un rango imposible es 400.
  C6  el log de la cuadrilla, en la pestaña Hoy, deja afuera lo terminado.

    pytest campo/tests/test_ordenes_cerradas.py
================================================================================
"""
import datetime as dt
import zoneinfo
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from campo import cierre_por_el_supervisor as CS
from campo import ordenes_cerradas as OC
from campo import revision_del_cierre as RC
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import cierre_en_isp

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


class _Respuesta:
    status_code = 200
    content = b"{}"

    def json(self):
        return {"cerrado": True, "referencia": "x"}


@pytest.fixture(autouse=True)
def _entorno(org_a, monkeypatch):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    monkeypatch.setenv("MOTOR_TENANT", "tenant-de-prueba")
    monkeypatch.delenv(cierre_en_isp.BANDERA, raising=False)
    monkeypatch.setattr(RC, "pendientes_de_medir", lambda org, ahora=None: set())


def _hoy():
    return timezone.now().astimezone(BOGOTA).date()


def _paso(o, estado, cuando, tipo="transicion"):
    ev = EventoTrabajo.objects.create(org=o.org, orden=o, tipo=tipo,
                                      datos={"nuevo_estado": estado})
    EventoTrabajo.objects.filter(pk=ev.pk).update(created_at=cuando)


@pytest.fixture
def terminada(org_a, user_profile):
    """Terminada hoy, con todo bien: la revision dice «Se puede cerrar»."""
    wt = WorkType.objects.create(org=org_a, codigo="sop", nombre="Soporte")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto de la ONT", "tipo": "foto", "obligatorio": True}]})
    base = timezone.now().astimezone(BOGOTA).replace(second=0, microsecond=0) - dt.timedelta(hours=2)
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=3, tipo_trabajo_version=v, zona="X",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE, completada_campo_en=base + dt.timedelta(minutes=60),
        contexto={"ticket": "94721"}, cliente_nombre="Cliente Prueba", cliente_direccion="Calle 1")
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico", es_principal=True)
    EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=o, requisito_id="foto_ont", vuelta=o.vuelta, sha256="s",
        storage_key="k/f", nombre_original="f.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    _paso(o, "en_camino", base)
    _paso(o, "en_sitio", base + dt.timedelta(minutes=20))
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=o, tipo="cierre_campo",
        datos={"definicion": [{"id": "servicio_validado"}],
               "respuestas": {"solucion": "Cambié el conector", "servicio_validado": True}})
    EventoTrabajo.objects.filter(pk=cierre.pk).update(created_at=base + dt.timedelta(minutes=55))
    _paso(o, "completada_campo", base + dt.timedelta(minutes=60))
    m = MaterialCatalogo.objects.create(org=org_a, codigo="CON", nombre="Conector", unidad="u")
    MovimientoDeMaterial.objects.create(
        org=org_a, material=m, orden=o, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), profile=user_profile, idempotency_key="oc-1")
    return o


def _aprobar_y_cerrar_desde_la_web(cliente, orden):
    with mock.patch("requests.post", return_value=_Respuesta()):
        r = cliente.post(f"/api/campo/trabajos/{orden.id}/validar/",
                         {"decision": "aprobar", "observacion": "ok"}, format="json")
        assert r.status_code == 200, r.content
        r = cliente.post(f"/api/campo/trabajos/{orden.id}/cerrar/", {}, format="json")
        assert r.status_code == 200, r.content


def test_c1_cerrada_por_una_persona_con_la_foto_de_la_revision(
        org_a, terminada, admin_client, admin_profile):
    admin_profile.user.name = "Laura Gómez"
    admin_profile.user.save(update_fields=["name"])
    _aprobar_y_cerrar_desde_la_web(admin_client, terminada)

    d = OC.del_rango(org_a, _hoy(), _hoy())

    assert d["cuentas"] == {"cerradas": 1, "por_una_persona": 1, "por_el_supervisor": 0,
                            "ticket_sin_cerrar": 0}
    f = d["ordenes"][0]
    assert (f["numero"], f["quien"], f["ticket"]["estado"], f["solucion"]) == (
        3, {"de": "persona", "nombre": "Laura Gómez"}, "cerrado", "Cambié el conector")
    assert f["revision"]["veredicto"] == RC.CERRAR
    assert {p["clave"] for p in f["revision"]["puntos"]} >= {"checklist", "servicio", "material"}
    assert (f["tiempos"]["traslado_min"], f["tiempos"]["en_sitio_min"]) == (20, 40)


def test_c2_cerrada_por_el_supervisor(org_a, terminada):
    revision = RC.revisar(terminada, pendientes=set())
    assert CS._aprobar_y_cerrar(terminada, revision, {"estado": "cerrado"})
    EventoTrabajo.objects.create(org=org_a, orden=terminada, tipo=cierre_en_isp.EVENTO_CERRADO,
                                 datos={"ticket": "94721"})

    f = OC.del_rango(org_a, _hoy(), _hoy())["ordenes"][0]

    assert f["quien"] == {"de": "supervisor", "nombre": "El Supervisor"}
    assert f["revision"]["veredicto"] == RC.CERRAR


def test_c3_el_historial_es_de_esa_orden(org_a, terminada, admin_client):
    otra = OrdenTrabajo.objects.create(org=org_a, numero=99, tipo_trabajo_version=terminada.tipo_trabajo_version,
                                       estado_operativo=OrdenTrabajo.EN_CAMINO, zona="X")
    _paso(otra, "en_camino", timezone.now())
    _aprobar_y_cerrar_desde_la_web(admin_client, terminada)

    textos = [h["texto"] for h in OC.del_rango(org_a, _hoy(), _hoy())["ordenes"][0]["historial"]]

    assert textos[:4] == ["Salió hacia la orden", "Llegó (20 min de camino)", "Reportó cierre",
                          "Terminó en campo (40 min en sitio)"], textos
    assert any(t.endswith("la aprobó") for t in textos)
    assert "Ticket cerrado en el sistema del ISP" in textos
    assert textos.count("Salió hacia la orden") == 1, "nada de la OT #99"


def test_c3b_la_que_llego_otro_dia_dice_cuando_habia_llegado(org_a, terminada, admin_client):
    """Lo que antes decia el log de la cuadrilla («había llegado el 15/10»)
    ahora lo dice el historial de la orden."""
    vieja = timezone.now().astimezone(BOGOTA).replace(second=0, microsecond=0) - dt.timedelta(days=15)
    EventoTrabajo.objects.filter(orden=terminada, datos__nuevo_estado__in=["en_camino", "en_sitio"]).update(
        created_at=vieja)
    _aprobar_y_cerrar_desde_la_web(admin_client, terminada)

    textos = [h["texto"] for h in OC.del_rango(org_a, _hoy(), _hoy())["ordenes"][0]["historial"]]

    assert f"Terminó en campo (había llegado el {vieja.strftime('%d/%m %H:%M')})" in textos, textos


def test_c4_el_rango_es_el_dia_de_la_empresa(org_a, terminada, admin_client):
    _aprobar_y_cerrar_desde_la_web(admin_client, terminada)
    ayer = timezone.now() - dt.timedelta(days=1)
    OrdenTrabajo.objects.filter(pk=terminada.pk).update(cerrada_en=ayer)

    assert OC.del_rango(org_a, _hoy(), _hoy())["ordenes"] == []
    assert len(OC.del_rango(org_a, _hoy() - dt.timedelta(days=1), _hoy())["ordenes"]) == 1


def test_c5_solo_quien_gestiona_y_un_rango_posible(admin_client, user_client):
    hoy = _hoy().isoformat()
    assert admin_client.get(f"/api/campo/cerradas/?desde={hoy}&hasta={hoy}").status_code == 200
    assert user_client.get(f"/api/campo/cerradas/?desde={hoy}&hasta={hoy}").status_code in (403, 404)
    viejo = (_hoy() - dt.timedelta(days=40)).isoformat()
    assert admin_client.get(f"/api/campo/cerradas/?desde={viejo}&hasta={hoy}").status_code == 400
    assert admin_client.get("/api/campo/cerradas/?desde=x&hasta=y").status_code == 400


def test_c6_el_log_de_la_cuadrilla_deja_afuera_lo_terminado(org_a, terminada, user_profile):
    from campo import dia_publicado as D
    from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                                  JornadaDeCuadrilla, PersonaDeCampo)

    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=org_a, cuadrilla=c, fecha=_hoy(),
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=org_a, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=org_a, jornada=j, persona=persona, rol="tecnico")
    abierta = OrdenTrabajo.objects.create(org=org_a, numero=12, tipo_trabajo_version=terminada.tipo_trabajo_version,
                                          estado_operativo=OrdenTrabajo.EN_CAMINO, zona="X")
    AsignacionTrabajo.objects.create(orden=abierta, profile=user_profile, rol="tecnico", es_principal=True)
    _paso(abierta, "en_camino", timezone.now())

    c0 = D.del_dia(org_a, _hoy())["cuadrillas"][0]
    textos = [e["texto"] for e in c0["log"]]

    assert "Salió hacia OT #12" in textos
    assert not any("#3" in t for t in textos), textos
    assert c0["resumen_del_dia"]["hechas"] == 1, "lo terminado sigue contando en el avance"
