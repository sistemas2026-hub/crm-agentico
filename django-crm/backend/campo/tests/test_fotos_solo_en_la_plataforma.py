# -*- coding: utf-8 -*-
"""
================================================================================
 LOS DOCUMENTOS DEL CLIENTE NO VIAJAN AL TICKET  --  25/11/2026
================================================================================
Decision del usuario sobre la cedula y el recibo que se fotografian en una
instalacion: *«solo en la plataforma, no al ticket»*.

Se marca en la PLANTILLA (`solo_en_la_plataforma`) y no se reconoce por el
nombre de la foto. Lo que se afirma es el EFECTO en los dos caminos por donde
una foto sale:

  A  el ticket del CRM (`fotos_al_ticket.adjuntar`): las filas que quedan
     adjuntas al caso.
  B  el ticket del ISP (`nota_al_isp.fotos_de_la_vuelta`): lo que se le
     manda al motor.
  C  el tope de ocho se cuenta DESPUES de sacar las privadas.
  D  si no se puede leer la plantilla, no sale ninguna.
  E  el editor de plantillas la escribe y la vuelve a leer.
================================================================================
"""
from __future__ import annotations

import pytest

from campo.tests.test_fotos_al_ticket import _adjuntos, _evidencia, _orden

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [],
    "campos": [],
    "evidencias": [
        {"id": "cedula_por_delante", "tipo": "foto", "titulo": "Cédula por delante",
         "obligatorio": True, "solo_en_la_plataforma": True},
        {"id": "recibo_publico", "tipo": "foto", "titulo": "Recibo público",
         "obligatorio": True, "solo_en_la_plataforma": True},
        {"id": "onu_instalada", "tipo": "foto", "titulo": "ONU instalada", "obligatorio": True},
        {"id": "medicion_de_potencia", "tipo": "foto", "titulo": "Medición", "obligatorio": True},
    ],
}


def _con_esquema(orden, esquema=ESQUEMA):
    """La orden pasa a una version NUEVA de su plantilla con este esquema.

    Una version publicada no se edita --ni por `save` ni por `update`: el
    modelo lo frena, y esta bien--. Asi que se hace lo que hace la pantalla:
    publicar la siguiente.
    """
    from campo.models import WorkTypeVersion

    actual = orden.tipo_trabajo_version
    nueva = WorkTypeVersion.objects.create(
        work_type=actual.work_type, version=actual.version + 1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    orden.tipo_trabajo_version = nueva
    orden.save(update_fields=["tipo_trabajo_version"])
    orden.refresh_from_db()
    return orden


def _con_fotos(orden, tmp_path, *requisitos):
    return [_evidencia(orden, r, tmp_path) for r in requisitos]


# --------------------------------------------------------------------------- A
def test_a1_al_ticket_del_CRM_van_las_de_la_instalacion_y_NO_los_documentos(
        org_a, user_profile, tmp_path, settings):
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=501)
    _con_esquema(orden)
    _con_fotos(orden, tmp_path, "cedula_por_delante", "recibo_publico",
               "onu_instalada", "medicion_de_potencia")

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["hecho"] is True and r["cuantas"] == 2, r
    nombres = sorted(a.attachment.name.rsplit("/", 1)[-1] for a in _adjuntos(caso))
    assert len(nombres) == 2
    assert all(n.startswith(("onu_instalada", "medicion_de_potencia")) for n in nombres), nombres
    assert not any("cedula" in n or "recibo" in n for n in nombres), nombres


def test_a2_EL_CONTROL_sin_la_marca_los_documentos_si_viajan(org_a, user_profile,
                                                            tmp_path, settings):
    """Si a1 pasara porque `adjuntar` no manda nada de nada, esta fallaria."""
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=502)
    sin_marca = {**ESQUEMA, "evidencias": [
        {k: v for k, v in e.items() if k != "solo_en_la_plataforma"} for e in ESQUEMA["evidencias"]]}
    _con_esquema(orden, sin_marca)
    _con_fotos(orden, tmp_path, "cedula_por_delante", "recibo_publico", "onu_instalada")

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["cuantas"] == 3 and _adjuntos(caso).count() == 3, r


# --------------------------------------------------------------------------- B
def test_b1_al_ticket_del_ISP_tampoco_salen_los_documentos(org_a, user_profile, tmp_path):
    from unittest import mock

    from campo.services import nota_al_isp, storage

    orden, _ = _orden(org_a, user_profile, numero=503)
    _con_esquema(orden)
    fotos = _con_fotos(orden, tmp_path, "cedula_por_delante", "recibo_publico",
                       "onu_instalada", "medicion_de_potencia")
    rutas = {f.storage_key: str(tmp_path / f.storage_key) for f in fotos}
    with mock.patch.object(storage.CampoStorage, "ruta_absoluta",
                           staticmethod(lambda k: rutas.get(k, ""))):
        salen = nota_al_isp.fotos_de_la_vuelta(orden)

    nombres = [f["nombre"] for f in salen]
    assert len(nombres) == 2, nombres
    assert all(n.startswith(("onu_instalada", "medicion_de_potencia")) for n in nombres), nombres


# --------------------------------------------------------------------------- C
def test_c1_el_tope_de_ocho_se_cuenta_SIN_los_documentos(org_a, user_profile,
                                                        tmp_path, settings):
    """Diez fotos obligatorias: dos documentos y ocho de la instalacion. Si
    los documentos se sacaran DESPUES del tope, dos de la instalacion se
    quedarian afuera por culpa de fotos que igual no iban a viajar."""
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=504)
    ocho = [f"instalacion_{i}" for i in range(8)]
    _con_esquema(orden, {**ESQUEMA, "evidencias": ESQUEMA["evidencias"][:2] + [
        {"id": r, "tipo": "foto", "titulo": r, "obligatorio": True} for r in ocho]})
    #  Los documentos se suben PRIMERO, que es lo que hace un tecnico en el
    #  paso «Contrato y documentos».
    _con_fotos(orden, tmp_path, "cedula_por_delante", "recibo_publico", *ocho)

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["cuantas"] == 8, r
    nombres = [a.attachment.name.rsplit("/", 1)[-1] for a in _adjuntos(caso)]
    assert all(n.startswith("instalacion_") for n in nombres), nombres


# --------------------------------------------------------------------------- D
def test_d1_si_NO_SE_PUEDE_LEER_la_plantilla_no_sale_ninguna(org_a, user_profile,
                                                            tmp_path, settings):
    from types import SimpleNamespace
    from unittest import mock

    from campo import fotos_al_ticket
    from campo.services import nota_al_isp

    #  La lectura: una plantilla que no se entiende es «no se sabe», no «ninguna».
    rara = SimpleNamespace(tipo_trabajo_version=SimpleNamespace(
        esquema={"evidencias": "no soy una lista"}))
    assert fotos_al_ticket.requisitos_que_no_salen(rara) is None
    rara.tipo_trabajo_version.esquema = "ni siquiera un objeto"
    assert fotos_al_ticket.requisitos_que_no_salen(rara) is None

    #  Y el efecto: con «no se sabe», ningun camino manda fotos.
    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=505)
    _con_esquema(orden)
    _con_fotos(orden, tmp_path, "cedula_por_delante", "onu_instalada")
    with mock.patch.object(fotos_al_ticket, "requisitos_que_no_salen", lambda o: None):
        r = fotos_al_ticket.adjuntar(orden, profile=user_profile)
        assert nota_al_isp.fotos_de_la_vuelta(orden) == []
    assert r["hecho"] is False and r["motivo"] == "plantilla_ilegible", r
    assert _adjuntos(caso).count() == 0
    orden.refresh_from_db()
    assert not (orden.contexto or {}).get(fotos_al_ticket.CLAVE),         "y la vuelta NO queda marcada: cuando se arregle, se adjuntan"


def test_d2_las_fotos_de_un_REPORTE_marcadas_tambien_cuentan():
    """Una foto del reporte de bloqueo, marcada, tampoco sale."""
    from types import SimpleNamespace

    from campo.fotos_al_ticket import requisitos_que_no_salen

    orden = SimpleNamespace(tipo_trabajo_version=SimpleNamespace(esquema={
        **ESQUEMA, "seguimiento": {"bloqueo": {"evidencias": [
            {"id": "documento_del_vecino", "tipo": "foto", "titulo": "x",
             "solo_en_la_plataforma": True}]}}}))
    assert requisitos_que_no_salen(orden) == {
        "cedula_por_delante", "recibo_publico", "documento_del_vecino"}
    #  Solo `True` marca: un texto «false» no es un «si».
    orden.tipo_trabajo_version.esquema = {"evidencias": [
        {"id": "x", "solo_en_la_plataforma": "false"}]}
    assert requisitos_que_no_salen(orden) == set()


# --------------------------------------------------------------------------- E
def test_e1_el_editor_la_ESCRIBE_y_la_VUELVE_A_LEER():
    """Sin leerla de vuelta, el primer guardado desde el editor la borraria y
    la cedula volveria a viajar al ticket."""
    from campo import plantillas as P

    esquema = P.componer({
        "campos": [],
        "evidencias": [
            {"titulo": "Cédula por delante", "solo_en_la_plataforma": True},
            {"titulo": "ONU instalada"},
        ]})
    marcas = {e["titulo"]: e.get("solo_en_la_plataforma") for e in esquema["evidencias"]}
    assert marcas == {"Cédula por delante": True, "ONU instalada": None}, \
        "sin marcar, la clave ni se escribe"

    definicion, motivos = P.leer_definicion(esquema)
    assert motivos == []
    leidas = {e["titulo"]: e["solo_en_la_plataforma"] for e in definicion["evidencias"]}
    assert leidas == {"Cédula por delante": True, "ONU instalada": False}
    assert P.componer(definicion)["evidencias"] == esquema["evidencias"], \
        "ida y vuelta sin perder la marca"
