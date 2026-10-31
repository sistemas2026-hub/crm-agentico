"""
================================================================================
 AVISARLE UNA CAIDA A SUS CLIENTES  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================
Lo calcula y lo manda el motor; esto prueba el circuito de la PERSONA que lo
aprueba y el avance por lotes:

  A  que caidas se avisan: PON con alerta de fibra y activa. Un corte de
     energia no es una falla del ISP; una resuelta ya no se avisa;
  B  la vista previa son conteos (nunca la lista de servicios) para el puerto
     y la empresa de la situacion;
  C  aprobar deja escrito QUIEN (la fila y la linea de tiempo), arma la lista
     en ese momento, una sola vez por situacion, y arranca el envio despues
     del commit;
  D  cada vuelta manda un lote del tamaño de la empresa, suma lo que contesto
     el motor, conserva lo que quedo pendiente, termina cuando no queda nada,
     y se DETIENE si la situacion se resolvio;
  E  la pantalla: solo gestion, solo las caidas de la propia empresa.

    pytest operaciones/tests/test_aviso_de_caida.py
================================================================================
"""
from unittest import mock

import pytest
from django.utils import timezone

from operaciones import aviso_de_caida as A
from operaciones.aviso_de_caida_modelos import AvisoDeCaida
from operaciones.situaciones_modelos import (Riesgo, SituacionAfectado, SituacionEvento,
                                             SituacionOperativa, TipoAfectado, TipoEvento)

pytestmark = pytest.mark.django_db
S = SituacionOperativa
LISTA = "/api/operaciones/fallas-de-red/"


def _situacion(org, *, tipo_alerta="partial_los", pon="3/2/11", estado=S.DETECTADA, codigo="S-001"):
    ahora = timezone.now()
    s = S.objects.create(org=org, codigo=codigo, tipo=S.AFECTACION_PON,
                         titulo=f"Posible afectación del PON {pon}", estado=estado,
                         riesgo=Riesgo.ALTO, huella=f"afectacion_pon|pon:{pon}|{codigo}",
                         detectada_en=ahora, actualizada_en=ahora, senal_vista_en=ahora,
                         fuente_origen="smartolt")
    SituacionAfectado.objects.create(situacion=s, org=org, tipo=TipoAfectado.PON, identificador=pon,
                                     etiqueta="CTO 56", detectado_en=ahora, visto_en=ahora,
                                     datos={"afectados": 9, "tipo_alerta": tipo_alerta})
    return s


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "OTRA_EMPRESA_DEL_ENTORNO")
    with mock.patch("operaciones.areas_del_tenant.tenant_de_organizacion",
                    return_value="rapilink") as resolver:
        yield resolver


class _R:
    def __init__(self, datos, status=200):
        self._d, self.status_code, self.content = datos, status, b"x"

    def json(self):
        return self._d


AFECTADOS = {"servicios": ["101", "102", "103", "104", "105"], "equipos_en_falla": 7,
             "sin_cliente": 1, "fuera_de_estado": 1, "desde": "2026-10-30 07:16:44", "lote": 2}


# ---------------------------------------------------------------------------
# A · que caidas se avisan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alerta,estado,esperado", [
    ("partial_los", S.DETECTADA, None),
    ("los", S.EN_ATENCION, None),
    ("power", S.DETECTADA, "corte_de_energia"),
    ("offline", S.DETECTADA, "alerta_sin_aviso"),
    ("los", S.EN_VERIFICACION, "ya_no_esta_activa"),
])
def test_a_que_caidas_se_avisan(org_a, alerta, estado, esperado):
    assert A.por_que_no(_situacion(org_a, tipo_alerta=alerta, estado=estado)) == esperado


def test_a2_un_puerto_que_no_se_lee_no_se_avisa(org_a):
    assert A.por_que_no(_situacion(org_a, pon="3/?/11")) == "sin_puerto"


# ---------------------------------------------------------------------------
# B · la vista previa
# ---------------------------------------------------------------------------

def test_b_la_vista_previa_son_conteos_del_puerto_y_la_empresa(org_a, motor):
    s = _situacion(org_a)
    with mock.patch("requests.post", return_value=_R(AFECTADOS)) as post:
        v = A.vista_previa(s)
    assert post.call_args.args[0] == "http://motor:5000/avisos/caida/afectados"
    assert post.call_args.kwargs["json"] == {"tenant": "rapilink", "olt": "3", "board": "2", "port": "11"}
    assert v["clientes"] == 5 and v["sin_cliente"] == 1 and v["fuera_de_estado"] == 1
    assert "servicios" not in v and "101" not in str(v), "la pantalla no recibe la lista"


def test_b2_un_corte_de_energia_ni_le_pregunta_al_motor(org_a, motor):
    with mock.patch("requests.post") as post, pytest.raises(A.NoAvisable) as e:
        A.vista_previa(_situacion(org_a, tipo_alerta="power"))
    assert e.value.codigo == "corte_de_energia" and post.call_count == 0


# ---------------------------------------------------------------------------
# C · aprobar
# ---------------------------------------------------------------------------

def test_c_aprobar_deja_escrito_quien_y_arranca_despues_del_commit(
        org_a, admin_profile, motor, django_capture_on_commit_callbacks):
    s = _situacion(org_a)
    with mock.patch("requests.post", return_value=_R(AFECTADOS)), \
            mock.patch("operaciones.tasks.avanzar_aviso_de_caida.apply_async") as vuelta:
        with django_capture_on_commit_callbacks(execute=True):
            aviso = A.aprobar(s, admin_profile)
    assert aviso.aprobado_por == admin_profile and aviso.servicios == AFECTADOS["servicios"]
    assert aviso.pendientes == AFECTADOS["servicios"] and aviso.lote == 2
    ev = SituacionEvento.objects.filter(situacion=s, tipo=TipoEvento.COORDINACION).get()
    assert ev.actor == admin_profile and ev.datos["clientes"] == 5
    assert vuelta.call_args.kwargs == {"args": [str(aviso.id), str(org_a.id)], "countdown": 0}


def test_c2_una_sola_vez_por_situacion_y_nunca_sin_clientes(org_a, admin_profile, motor):
    s = _situacion(org_a)
    with mock.patch("requests.post", return_value=_R(AFECTADOS)), \
            mock.patch("operaciones.tasks.avanzar_aviso_de_caida.apply_async"):
        A.aprobar(s, admin_profile)
        with pytest.raises(A.NoAvisable) as e:
            A.aprobar(s, admin_profile)
    assert e.value.codigo == "YA_APROBADO"
    otra = _situacion(org_a, codigo="S-002", pon="3/2/12")
    with mock.patch("requests.post", return_value=_R({**AFECTADOS, "servicios": []})), \
            pytest.raises(A.NoAvisable) as e:
        A.aprobar(otra, admin_profile)
    assert e.value.codigo == "SIN_CLIENTES" and not AvisoDeCaida.objects.filter(situacion=otra).exists()


def test_c3_un_aviso_apagado_se_dice_antes_y_no_se_aprueba(org_a, admin_profile, motor):
    s = _situacion(org_a)
    apagado = {**AFECTADOS, "no_listo": "apagado", "modo_prueba": False}
    with mock.patch("requests.post", return_value=_R(apagado)):
        v = A.vista_previa(s)
        assert v["no_listo"] == "apagado"
        with pytest.raises(A.NoAvisable) as e:
            A.aprobar(s, admin_profile)
    assert e.value.codigo == "AVISO_APAGADO"
    assert not AvisoDeCaida.objects.filter(situacion=s).exists(), "no se consume la aprobacion"


# ---------------------------------------------------------------------------
# D · el avance por lotes
# ---------------------------------------------------------------------------

def _aviso(org, profile, situacion, pendientes=("101", "102", "103")):
    return AvisoDeCaida.objects.create(
        org=org, situacion=situacion, aprobado_por=profile, aprobado_en=timezone.now(),
        olt="3", board="2", port="11", servicios=list(pendientes), pendientes=list(pendientes), lote=2)


def test_d_un_lote_por_vuelta_con_lo_que_contesto_el_motor(org_a, admin_profile, motor):
    s = _situacion(org_a)
    aviso = _aviso(org_a, admin_profile, s)
    contesta = {"enviados": 1, "descartados": 0, "motivos": {"isp_no_contesta": 1},
                "pendientes": ["102"], "reintentar_en": 900}
    with mock.patch("requests.post", return_value=_R(contesta)) as post:
        espera = A.avanzar(aviso)
    cuerpo = post.call_args.kwargs["json"]
    assert post.call_args.args[0] == "http://motor:5000/avisos/caida/lote"
    assert cuerpo["servicios"] == ["101", "102"] and cuerpo["situacion"] == str(s.id)
    assert cuerpo["autor"] == f"profile:{admin_profile.id}" and cuerpo["tenant"] == "rapilink"
    aviso.refresh_from_db()
    assert aviso.enviados == 1 and aviso.motivos == {"isp_no_contesta": 1}
    assert aviso.pendientes == ["102", "103"], "el pendiente del motor vuelve a la cola"
    assert espera == 900 and aviso.estado == AvisoDeCaida.EN_CURSO


def test_d2_termina_cuando_no_queda_nada(org_a, admin_profile, motor):
    aviso = _aviso(org_a, admin_profile, _situacion(org_a), pendientes=("101",))
    with mock.patch("requests.post", return_value=_R({"enviados": 0, "descartados": 1, "motivos": {},
                                                      "pendientes": [], "reintentar_en": None})):
        assert A.avanzar(aviso) is None
    aviso.refresh_from_db()
    assert aviso.estado == AvisoDeCaida.TERMINADO and aviso.descartados == 1 and aviso.terminado_en


def test_d3_una_situacion_resuelta_detiene_el_envio_sin_mandar_nada(org_a, admin_profile, motor):
    s = _situacion(org_a)
    aviso = _aviso(org_a, admin_profile, s)
    S.objects.filter(id=s.id).update(estado=S.EN_VERIFICACION)
    aviso.refresh_from_db()
    with mock.patch("requests.post") as post:
        assert A.avanzar(aviso) is None
    aviso.refresh_from_db()
    assert aviso.estado == AvisoDeCaida.DETENIDO and post.call_count == 0


def test_d4_motor_caido_vuelve_despues_y_un_rechazo_detiene(org_a, admin_profile, motor):
    aviso = _aviso(org_a, admin_profile, _situacion(org_a))
    with mock.patch("requests.post", side_effect=ConnectionError("caido")):
        assert A.avanzar(aviso) == A.ESPERA_SI_EL_MOTOR_NO_CONTESTA_S
    aviso.refresh_from_db()
    assert aviso.pendientes == ["101", "102", "103"] and aviso.estado == AvisoDeCaida.EN_CURSO
    with mock.patch("requests.post", return_value=_R({"error": "NO_CONFIGURADO"}, status=400)):
        assert A.avanzar(aviso) is None
    aviso.refresh_from_db()
    assert aviso.estado == AvisoDeCaida.DETENIDO


# ---------------------------------------------------------------------------
# E · la pantalla
# ---------------------------------------------------------------------------

def test_e_la_lista_trae_las_caidas_vivas_de_la_empresa_con_su_aviso(
        admin_client, org_a, org_b, admin_profile):
    viva = _situacion(org_a)
    _situacion(org_a, codigo="S-002", pon="3/2/12", estado=S.EN_VERIFICACION)
    _situacion(org_b, codigo="S-003")
    _aviso(org_a, admin_profile, viva)
    r = admin_client.get(LISTA)
    assert r.status_code == 200, r.content
    fallas = r.json()["fallas"]
    assert [f["id"] for f in fallas] == [str(viva.id)]
    f = fallas[0]
    assert f["puerto"] == "3/2/11" and f["equipos"] == 9 and f["por_que_no"] is None
    assert f["aviso"]["clientes"] == 3 and f["aviso"]["estado"] == AvisoDeCaida.EN_CURSO
    assert "101" not in str(f), "la pantalla no recibe la lista de servicios"


def test_e2_preparar_y_aprobar_por_la_pantalla(admin_client, org_a, motor,
                                               django_capture_on_commit_callbacks):
    s = _situacion(org_a)
    url = f"{LISTA}{s.id}/aviso/"
    with mock.patch("requests.post", return_value=_R(AFECTADOS)), \
            mock.patch("operaciones.tasks.avanzar_aviso_de_caida.apply_async"):
        r = admin_client.post(url, {"accion": "preparar"}, format="json")
        assert r.status_code == 200 and r.json()["clientes"] == 5
        with django_capture_on_commit_callbacks(execute=True):
            r = admin_client.post(url, {"accion": "aprobar"}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["aviso"]["clientes"] == 5
    r = admin_client.post(url, {"accion": "aprobar"}, format="json")
    assert r.status_code == 409 and r.json()["error"] == "YA_APROBADO"


def test_e3_solo_gestion_y_solo_la_propia_empresa(user_client, admin_client, org_b, motor):
    assert user_client.get(LISTA).status_code == 403
    ajena = _situacion(org_b, codigo="S-009")
    r = admin_client.post(f"{LISTA}{ajena.id}/aviso/", {"accion": "preparar"}, format="json")
    assert r.status_code == 404
