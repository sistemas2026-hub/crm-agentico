# -*- coding: utf-8 -*-
"""EL MATERIAL Y EL CIERRE VAN DESPUES DE APROBAR, Y LA CIERRA EL TECNICO  --  27/11/2026.

El usuario, al terminar la prueba vigilada de la OT-502: «enviar a validación»
sin el material ni el reporte de cierre; «después de aprobar se registra el
material y el cierre, y ahí finaliza»; y la oficina no tendría que tocar
«Cerrar»: en Programación aparecía «Lista para cerrar», y ese cierre no toca
el proveedor, así que dejaba el ticket abierto.

  A  FINALIZAR -- sin el reporte de cierre de esta vuelta no se cierra; con
     él, la nota que cierra el ticket lleva el reporte y el material.
  B  EL «CERRAR» DE LA OFICINA -- no cierra una instalación que valida una
     persona; cualquier otra orden aprobada, sí.
  C  LA REVISIÓN -- antes de aprobar, que falten el reporte y el material no
     es una falta en estas instalaciones.
"""
import pytest

from campo.contrato import ContratoDeServicio
from campo.models import EventoTrabajo, OrdenTrabajo
from campo.revision_del_cierre import revisar
from campo.services import cierre_en_isp
from campo.tests.test_instalacion_validada import (  # noqa: F401
    _contrato, _finalizada, config, orden, version)

pytestmark = pytest.mark.django_db


def _aprobada(orden, user_profile):
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.EN_EL_ISP,
              servicio_isp="7000")
    OrdenTrabajo.objects.filter(pk=orden.pk).update(estado_validacion=OrdenTrabajo.APROBADO)
    orden.refresh_from_db()
    return orden


@pytest.fixture
def cierres(monkeypatch):
    vistos = []
    monkeypatch.setattr(cierre_en_isp, "cerrar_ticket_al_validar",
                        lambda orden, profile, extra="": vistos.append(extra) or {"estado": "cerrado"})
    monkeypatch.setattr(cierre_en_isp, "resumen_de",
                        lambda orden, quien, encabezado="": "MATERIAL Y CANTIDAD: 2 CON-APC")
    return vistos


# --------------------------------------------------------------------------- #
#  A. FINALIZAR
# --------------------------------------------------------------------------- #
def test_a1_sin_el_reporte_de_cierre_NO_se_finaliza(user_client, orden, config, user_profile,
                                                    cierres):
    _aprobada(orden, user_profile)
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/instalacion-entregada/", {},
                         format="json")
    assert r.status_code == 409 and "Material y cierre" in r.json()["detail"]
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO and cierres == []


def test_a2_con_el_reporte_se_cierra_y_la_nota_lleva_el_material(user_client, orden, config,
                                                                 user_profile, cierres):
    _aprobada(orden, user_profile)
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="cierre_campo", datos={})
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/instalacion-entregada/", {},
                         format="json")
    assert r.status_code == 200, r.content
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA
    assert cierres and cierres[0].startswith("Instalación validada, activada y entregada")
    assert "MATERIAL Y CANTIDAD: 2 CON-APC" in cierres[0]


def test_a3_el_reporte_de_una_vuelta_ANTERIOR_no_cuenta(user_client, orden, config, user_profile,
                                                        cierres):
    _aprobada(orden, user_profile)
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="cierre_campo", datos={})
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="reapertura_correccion", datos={})
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/instalacion-entregada/", {},
                         format="json")
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
#  B. EL «CERRAR» DE LA OFICINA
# --------------------------------------------------------------------------- #
def test_b1_la_oficina_no_cierra_una_instalacion_que_valida_una_persona(
        admin_client, orden, config, user_profile):
    _aprobada(orden, user_profile)
    r = admin_client.post(f"/api/campo/trabajos/{orden.id}/cerrar/", {"observacion": "x"},
                          format="json", HTTP_IDEMPOTENCY_KEY=f"cerrar|{orden.id}|1")
    assert r.status_code == 409 and r.json()["error"] == "LA_CIERRA_EL_TECNICO"
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO


def test_b2_sin_la_validacion_de_una_persona_la_oficina_si_cierra(
        admin_client, orden, config, user_profile):
    _aprobada(orden, user_profile)
    config.validar_antes_de_activar = False
    config.save()
    r = admin_client.post(f"/api/campo/trabajos/{orden.id}/cerrar/", {"observacion": "x"},
                          format="json", HTTP_IDEMPOTENCY_KEY=f"cerrar|{orden.id}|1")
    assert r.status_code == 200, r.content


# --------------------------------------------------------------------------- #
#  C. LA REVISIÓN QUE VE QUIEN APRUEBA
# --------------------------------------------------------------------------- #
#  Se prueba la regla de los dos puntos y no `revisar` entero: el resto de la
#  revision usa la busqueda `contains`, que la base de pruebas (SQLite) no tiene.
def test_c1_antes_de_aprobar_el_reporte_y_el_material_se_piden_al_finalizar(
        orden, config, user_profile):
    from campo.revision_del_cierre import _reporte_y_material

    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION)
    reporte, material = _reporte_y_material(orden, None)
    assert reporte["ok"] is None and "al finalizar" in reporte["texto"]
    assert material["ok"] is None and "al finalizar" in material["texto"]


def test_c2_en_otra_orden_falta_el_reporte_sigue_siendo_una_falta(orden, config, user_profile):
    from campo.revision_del_cierre import _reporte_y_material

    config.validar_antes_de_activar = False
    config.save()
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION)
    reporte, _ = _reporte_y_material(orden, None)
    assert reporte["ok"] is False


def test_c3_con_el_cierre_ya_registrado_cuenta_como_siempre(orden, config, user_profile):
    from campo.revision_del_cierre import _reporte_y_material

    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.EN_EL_ISP)
    cierre = EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="cierre_campo",
                                          datos={"sin_material_confirmado": True})
    reporte, material = _reporte_y_material(orden, cierre)
    assert reporte["ok"] is True and material["ok"] is True
