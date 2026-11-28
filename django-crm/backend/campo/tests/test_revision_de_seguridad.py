# -*- coding: utf-8 -*-
"""Las correcciones de las revisiones de frontera y de PII antes del push
(27/11/2026).

  A  LOS DOCUMENTOS NO VAN AL ANALISIS CON IA: la cedula y el recibo («solo en
     la plataforma») no se mandan al modelo ni dejan fila; si la plantilla no
     se puede leer, no va ninguna.
  B  «NO SE SABE» NO ES «FALLO»: un «bloqueado» que pudo haber salido queda por
     revisar, en el contrato y en las fotos.
  C  QUIEN DECIDIO: las fotos salen a nombre de quien finalizo o reenvio; la
     activacion de la ONU, a nombre de quien la pidio (el nombre, no el correo),
     y sin nadie no sale.
  D  LO MINIMO: activar manda solo lo que reconoce al cliente; el enlace viaja
     con eso para que el motor lo ate al contrato.
"""
from datetime import datetime, timezone as tz

import pytest

from campo import contrato_del_proveedor as CP
from campo.contrato import ContratoDeServicio
from campo.services import alta_en_el_isp
from campo.tests.test_fotos_al_ticket import _evidencia, _orden
from campo.tests.test_fotos_solo_en_la_plataforma import _con_esquema

pytestmark = pytest.mark.django_db


@pytest.fixture
def orden(org_a, user_profile, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    o, _ = _orden(org_a, user_profile, numero=711)
    return _con_esquema(o)


@pytest.fixture
def motor(monkeypatch):
    class Motor:
        def __init__(self):
            self.llamadas, self.respuesta = [], ("subido", {"estado": "subido"})

        def __call__(self, contrato, ruta, cuerpo, espera):
            self.llamadas.append((ruta, cuerpo))
            return self.respuesta

    m = Motor()
    monkeypatch.setattr(alta_en_el_isp, "_llamar", m)
    return m


def _contrato(orden, profile, **kw):
    kw.setdefault("firma_en_el_proveedor", True)
    return ContratoDeServicio.objects.create(
        org=orden.org, orden=orden, numero=f"C-{orden.numero}", huella="h" * 64,
        estado=ContratoDeServicio.INSTALACION, firmado_por=profile,
        firmado_en=datetime(2026, 11, 27, 15, tzinfo=tz.utc), servicio_isp="8039",
        contrato_proveedor="4928", usuario_proveedor="laura-gomez@empresa",
        datos={"cliente": {"nombre": "LAURA", "apellido": "GOMEZ", "numero_documento": "1043",
                           "telefono": "300", "correo": "l@x.com", "direccion": "CRA 21",
                           "barrio": "X"},
               "plan": "PLAN FAMILIA", "ip_elegida": "172.16.9.40",
               "gps": {"lat": 10.9, "lng": -74.8},
               "servidor": {"id_zona": 20053, "nombre": "S1"}, "orden_numero": orden.numero},
        **kw)


# =========================================================================== #
#  A. LOS DOCUMENTOS NO VAN AL ANALISIS CON IA
# =========================================================================== #
def test_a1_la_cedula_no_se_manda_al_modelo_ni_deja_fila(orden, tmp_path, monkeypatch):
    from campo import inspeccion_visual as IV
    from campo import tasks
    from campo.models import AnalisisDeEvidencia

    llamadas = []
    monkeypatch.setattr(IV, "_esta_habilitado", lambda t: llamadas.append(t) or True)
    ev = _evidencia(orden, "cedula_por_delante", tmp_path)
    r = IV.analizar(ev)
    assert r["motivo"] == IV.MOTIVO_DOCUMENTO and llamadas == [], "ni siquiera se pregunta al motor"
    assert tasks._mirar_y_anotar(ev)["motivo"] == IV.MOTIVO_DOCUMENTO
    assert not AnalisisDeEvidencia.objects.filter(evidencia=ev).exists(), "no deja fila"


def test_a2_EL_CONTROL_una_foto_del_trabajo_si_sigue_al_analisis(orden, tmp_path, monkeypatch):
    from campo import inspeccion_visual as IV

    ev = _evidencia(orden, "onu_instalada", tmp_path)
    assert IV.analizar(ev)["motivo"] != IV.MOTIVO_DOCUMENTO, "sigue el camino de siempre"


def test_a3_si_la_plantilla_no_se_puede_leer_no_va_ninguna(orden, tmp_path, monkeypatch):
    from campo import fotos_al_ticket
    from campo import inspeccion_visual as IV

    monkeypatch.setattr(fotos_al_ticket, "requisitos_que_no_salen", lambda o: None)
    ev = _evidencia(orden, "onu_instalada", tmp_path)
    assert IV.es_documento_privado(ev) is True


def test_a4_la_pasada_de_las_que_faltan_no_cuenta_los_documentos(orden, tmp_path, monkeypatch):
    from campo import tasks

    miradas = []
    monkeypatch.setattr(tasks, "_mirar_estas", lambda evs: miradas.extend(e.requisito_id for e in evs)
                        or len(evs))
    from campo.models import EvidenciaTrabajo

    for r in ("cedula_por_delante", "recibo_publico", "onu_instalada"):
        ev = _evidencia(orden, r, tmp_path)
        EvidenciaTrabajo.objects.filter(pk=ev.pk).update(estado_archivo=EvidenciaTrabajo.RECIBIDO)
    tasks.mirar_las_que_faltan(orden)
    assert miradas == ["onu_instalada"], miradas


# =========================================================================== #
#  B. «NO SE SABE» NO ES «FALLO»
# =========================================================================== #
def test_b1_un_bloqueado_que_pudo_salir_deja_el_contrato_por_revisar(orden, user_profile, motor,
                                                                    tmp_path):
    for r in ("cedula_por_delante", "recibo_publico"):
        _evidencia(orden, r, tmp_path)
    motor.respuesta = ("bloqueado", {"estado": "bloqueado", "emitido": True})
    c = _contrato(orden, user_profile, firma_proveedor_estado="pedida", firma_proveedor_intento=1)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "por_revisar"
    assert CP.pedir(c) is False, "y el tecnico no lo puede reenviar solo"


def test_b2_EL_CONTROL_un_bloqueado_que_no_salio_sigue_fallida(orden, user_profile, motor, tmp_path):
    for r in ("cedula_por_delante", "recibo_publico"):
        _evidencia(orden, r, tmp_path)
    motor.respuesta = ("bloqueado", {"estado": "bloqueado", "emitido": False})
    c = _contrato(orden, user_profile, firma_proveedor_estado="pedida", firma_proveedor_intento=1)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "fallida"


def test_b3_lo_mismo_en_las_fotos(orden, user_profile, motor, tmp_path):
    _evidencia(orden, "onu_instalada", tmp_path)
    motor.respuesta = ("bloqueado", {"estado": "bloqueado", "emitido": True})
    c = _contrato(orden, user_profile, fotos_proveedor_estado="pedidas", fotos_proveedor_intento=1)
    CP.subir_fotos(c)
    c.refresh_from_db()
    assert c.fotos_proveedor_estado == "por_revisar"


# =========================================================================== #
#  C. QUIEN DECIDIO
# =========================================================================== #
def test_c1_las_fotos_salen_a_nombre_de_quien_las_pidio(orden, user_profile, admin_profile, motor,
                                                         tmp_path, django_capture_on_commit_callbacks,
                                                         monkeypatch):
    from campo import tasks
    from campo.services.ubicacion_al_isp import _nombre_de

    monkeypatch.setattr(tasks.subir_fotos_del_trabajo, "delay", lambda org, cid: None)
    _evidencia(orden, "onu_instalada", tmp_path)
    c = _contrato(orden, user_profile)
    with django_capture_on_commit_callbacks(execute=True):
        assert CP.pedir_fotos(c, por=admin_profile) is True
    CP.subir_fotos(c)
    assert motor.llamadas[0][1]["actor"] == _nombre_de(admin_profile) != _nombre_de(user_profile)


def test_c2_la_onu_sin_quien_la_pidio_no_sale_y_con_el_va_su_nombre(orden, user_profile, monkeypatch):
    from campo import activacion_onu as AO
    from campo.activacion_onu import ActivacionDeOnu
    from campo.services.ubicacion_al_isp import _nombre_de

    _contrato(orden, user_profile)
    pedidos = []
    monkeypatch.setattr(AO, "_contrato_y_vlan", lambda o: (o.contratos.first(), None, None)
                        if hasattr(o, "contratos") else (ContratoDeServicio.objects.get(orden=o), None, None))
    monkeypatch.setattr(AO, "_llamar", lambda org, ruta, cuerpo, espera: pedidos.append(cuerpo) or
                        {"estado": "en_curso"})
    sin = ActivacionDeOnu.objects.create(org=orden.org, orden=orden, serial="ZTEG1", zona="Z",
                                         pedida_por=None, estado=ActivacionDeOnu.PEDIDA)
    AO.ejecutar(sin)
    sin.refresh_from_db()
    assert sin.estado == ActivacionDeOnu.NO_SALIO and pedidos == []
    con = ActivacionDeOnu.objects.create(org=orden.org, orden=orden, serial="ZTEG2", zona="Z",
                                         pedida_por=user_profile, estado=ActivacionDeOnu.PEDIDA)
    AO.ejecutar(con)
    assert pedidos and pedidos[0]["actor"] == _nombre_de(user_profile)
    assert "@" not in pedidos[0]["actor"], "el nombre, nunca el correo"


# =========================================================================== #
#  D. LO MINIMO
# =========================================================================== #
def test_d1_activar_manda_solo_lo_que_reconoce_al_cliente(orden, user_profile, motor):
    from campo import instalacion

    motor.respuesta = ("en_curso", {"estado": "en_curso"})
    c = _contrato(orden, user_profile, activacion_estado="pedida", activacion_intento=1,
                  activado_por=user_profile)
    instalacion.pedir(c)
    datos = motor.llamadas[0][1]["datos"]
    assert set(datos["cliente"]) == {"nombre", "apellido", "documento"}
    assert "coordenadas" not in datos and "nota" not in datos


def test_d2_el_enlace_viaja_con_lo_que_lo_ata_al_contrato(orden, user_profile, motor):
    motor.respuesta = ("listo", {"estado": "listo", "enlace": "http://portal.example/x/"})
    c = _contrato(orden, user_profile, firma_proveedor_estado="lista")
    assert CP.enlace(c) == "http://portal.example/x/"
    cuerpo = motor.llamadas[0][1]
    assert cuerpo["usuario"] == "laura-gomez@empresa" and cuerpo["id_servicio"] == "8039"
    assert set(cuerpo["datos"]["cliente"]) == {"nombre", "apellido", "documento"}
