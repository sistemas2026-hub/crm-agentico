# -*- coding: utf-8 -*-
"""EL PRECINTO DEL CLIENTE Y LA MARCA DE LA CAJA, AL PROVEEDOR  --  27/11/2026.

El usuario: el precinto que el tecnico le pone al cliente va en «Usuario
Antena» del cliente en WispHub, y la marca de la caja en «Password Antena»
(«CTO 3 VILLA VALENTINA»; si la caja no tiene marca, «CAJA NO MARCADA»). Cada
empresa marca en SU plantilla cual dato es cual (`al_proveedor`); a que campo
del proveedor va lo dice la config del motor.

  A  LA PLANTILLA: la marca se valida, no se repite, y vuelve al editar.
  B  QUE VIAJA: el precinto y la marca, o «caja sin marca» si dijo «No».
  C  LA CADENA: lo anotado en la orden llega en el pedido al motor.
"""
import copy

import pytest

from campo import instalacion
from campo import plantillas as P
from campo.contrato import ContratoDeServicio
from campo.services import alta_en_el_isp
from campo.tests.test_instalacion_validada import _contrato, config, orden, version  # noqa: F401

pytestmark = pytest.mark.django_db


def _definicion():
    return {"campos": [
        {"id": "la_caja_esta_marcada", "titulo": "¿La caja está marcada?", "tipo": "seleccion",
         "opciones": ["Sí", "No"], "obligatorio": True, "paso": "Puerto y acceso",
         "al_proveedor": "caja_marcada"},
        {"id": "numero_de_la_caja", "titulo": "Marca de la caja", "tipo": "texto",
         "obligatorio": False, "paso": "Puerto y acceso", "al_proveedor": "marca_de_la_caja"},
        {"id": "precinto_del_cliente", "titulo": "Precinto del cliente", "tipo": "texto",
         "obligatorio": True, "paso": "Instalación", "escaneable": True,
         "al_proveedor": "precinto_del_cliente"},
    ], "evidencias": [{"id": "fachada", "titulo": "Fachada", "obligatorio": True}]}


# --------------------------------------------------------------------------- #
#  A. LA PLANTILLA
# --------------------------------------------------------------------------- #
def test_a1_la_marca_se_compone_y_vuelve_al_editar():
    e = P.componer(_definicion())
    assert {c["id"]: c.get("al_proveedor") for c in e["campos"]} == {
        "la_caja_esta_marcada": "caja_marcada", "numero_de_la_caja": "marca_de_la_caja",
        "precinto_del_cliente": "precinto_del_cliente"}
    vuelta, motivos = P.leer_definicion(e)
    assert vuelta is not None and not motivos
    #  Los DATOS y sus marcas (el editor ademas le pone las fotos de reportes
    #  por defecto, que esta definicion de prueba no trae).
    assert P.componer(vuelta)["campos"] == e["campos"], "abrir y volver a publicar no la borra"


@pytest.mark.parametrize("cambio,codigo", [
    #  Una marca que no existe, o en un tipo de dato que no la puede llevar.
    (lambda d: d["campos"][2].update(al_proveedor="color"), "AL_PROVEEDOR_INVALIDO"),
    (lambda d: d["campos"][0].update(al_proveedor="precinto_del_cliente"), "AL_PROVEEDOR_INVALIDO"),
    #  Dos datos con la misma marca: no se sabria cual va.
    (lambda d: d["campos"][1].update(al_proveedor="precinto_del_cliente"), "AL_PROVEEDOR_REPETIDO"),
    #  «¿Esta marcada?» sin la opcion «No» no puede decir que no lo esta.
    (lambda d: d["campos"][0].update(opciones=["Sí", "Tal vez"]), "CAJA_MARCADA_SIN_NO"),
])
def test_a2_lo_que_no_se_acepta(cambio, codigo):
    d = copy.deepcopy(_definicion())
    cambio(d)
    with pytest.raises(P.ErrorPlantilla) as e:
        P.componer(d)
    assert e.value.codigo == codigo


# --------------------------------------------------------------------------- #
#  B. QUE VIAJA
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("datos,esperado", [
    ({"la_caja_esta_marcada": "Sí", "numero_de_la_caja": "  CTO 3   VILLA VALENTINA ",
      "precinto_del_cliente": " 9308 "},
     {"precinto_del_cliente": "9308", "marca_de_la_caja": "CTO 3 VILLA VALENTINA"}),
    #  «No» manda sobre una marca escrita por error.
    ({"la_caja_esta_marcada": "No", "numero_de_la_caja": "CTO 3", "precinto_del_cliente": "9308"},
     {"precinto_del_cliente": "9308", "caja_sin_marca": True}),
    #  «Sí» sin marca escrita: de la caja no se dice nada.
    ({"la_caja_esta_marcada": "Sí", "precinto_del_cliente": "9308"},
     {"precinto_del_cliente": "9308"}),
    ({}, {}),
])
def test_b1_el_precinto_y_la_caja(datos, esperado):
    assert instalacion.lo_que_va_al_proveedor(P.componer(_definicion()), datos) == esperado


def test_b2_sin_marcas_en_la_plantilla_no_viaja_nada():
    d = _definicion()
    for c in d["campos"]:
        c.pop("al_proveedor")
    assert instalacion.lo_que_va_al_proveedor(
        P.componer(d), {"precinto_del_cliente": "9308", "numero_de_la_caja": "CTO 3"}) == {}


# --------------------------------------------------------------------------- #
#  C. LA CADENA: de la orden al pedido al motor
# --------------------------------------------------------------------------- #
def test_c1_lo_anotado_en_la_orden_llega_al_motor_al_aprobar(orden, user_profile, config,
                                                            monkeypatch):
    from campo.models import OrdenTrabajo, WorkTypeVersion

    #  Una version PUBLICADA no se edita (a proposito): una version nueva con
    #  las marcas, y la orden apuntando a ella.
    v = orden.tipo_trabajo_version
    nueva = WorkTypeVersion.objects.create(
        work_type=v.work_type, version=v.version + 1, schema_version=v.schema_version,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={**(v.esquema or {}), "campos": P.componer(_definicion())["campos"]})
    OrdenTrabajo.objects.filter(pk=orden.pk).update(tipo_trabajo_version=nueva, datos={
        "la_caja_esta_marcada": "No", "numero_de_la_caja": "", "precinto_del_cliente": "9308"})
    orden.refresh_from_db()
    llamadas = []
    monkeypatch.setattr(alta_en_el_isp, "_llamar", lambda contrato, ruta, cuerpo, espera: (
        llamadas.append((ruta, cuerpo)) or ("completado", {"estado": "completado"})))
    c = _contrato(orden, user_profile, estado=ContratoDeServicio.EN_EL_ISP, servicio_isp="8039",
                  activado_por=user_profile, completar_estado="pedido", completar_intento=1)
    instalacion.completar(c)
    ruta, cuerpo = llamadas[0]
    assert ruta == "completar-cliente"
    assert cuerpo["valores"] == {"precinto_del_cliente": "9308", "caja_sin_marca": True}
    c.refresh_from_db()
    assert c.completar_estado == ContratoDeServicio.COMPLETAR_HECHO


# --------------------------------------------------------------------------- #
#  D. LA TARJETA DE «POR ACTIVAR» DICE EL CLIENTE DEL CONTRATO
#     (la OT-501 decia «MARIO SABANAGRANDE», el cliente de paso)
# --------------------------------------------------------------------------- #
def test_d1_por_activar_muestra_al_cliente_del_contrato(admin_client, orden, user_profile, config):
    from campo.models import OrdenTrabajo
    from campo.tests.test_instalacion_validada import _finalizada

    OrdenTrabajo.objects.filter(pk=orden.pk).update(cliente_nombre="MARIO SABANAGRANDE")
    _finalizada(orden)
    _contrato(orden, user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="8043")
    r = admin_client.get("/api/campo/instalaciones/por-activar/")
    assert r.status_code == 200
    fila = r.json()["instalaciones"][0]
    assert fila["cliente"] == "LAURA GOMEZ", fila["cliente"]
