# -*- coding: utf-8 -*-
"""El cliente firma el contrato del proveedor (26/11/2026). Ver
campo/contrato_del_proveedor.py.

  A  CONFIRMAR -- sin firma de Dexter; la cedula y el recibo TIENEN que estar
     subidos; la instalacion se pide en ese momento.
  B  ENCADENAR -- creada la instalacion, se pide preparar el contrato.
  C  PREPARAR -- lo que viaja al motor (los documentos con su titulo, quien
     confirmo) y como queda segun lo que conteste; «no se» no se reintenta solo.
  D  EL ENLACE -- solo con el contrato listo, no se guarda ni se cachea.
  E  LA FIRMA -- se lee en el proveedor y deja el contrato firmado.
  F  LA EMPRESA -- el interruptor exige crear la instalacion y validarla.
  G  LA REVISION DEL CIERRE -- dice como esta la firma.
"""
from datetime import datetime, timezone as tz

import pytest

from campo import contrato_del_proveedor as CP
from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
from campo.services import alta_en_el_isp
from campo.tests.test_fotos_al_ticket import _evidencia, _orden
from campo.tests.test_fotos_solo_en_la_plataforma import _con_esquema

pytestmark = pytest.mark.django_db

SERVIDORES = [{"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1", "vlan": 300}]


@pytest.fixture
def config(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, nit="900", servidores=SERVIDORES, crear_en_el_isp=True,
        validar_antes_de_activar=True, firma_en_el_proveedor=True)


@pytest.fixture
def orden(org_a, user_profile, tmp_path, settings):
    from campo.models import OrdenTrabajo

    settings.MEDIA_ROOT = str(tmp_path)
    o, _caso = _orden(org_a, user_profile, numero=611)
    _con_esquema(o)
    OrdenTrabajo.objects.filter(pk=o.pk).update(estado_operativo=OrdenTrabajo.EN_SITIO)
    o.refresh_from_db()
    return o


@pytest.fixture
def con_documentos(orden, tmp_path):
    return [_evidencia(orden, r, tmp_path) for r in ("cedula_por_delante", "recibo_publico")]


@pytest.fixture
def pedidos(monkeypatch):
    vistos = []
    monkeypatch.setattr(alta_en_el_isp, "pedir_alta",
                        lambda contrato, por=None, como_instalacion=False:
                        vistos.append({"como_instalacion": como_instalacion}) or True)
    return vistos


@pytest.fixture
def motor(monkeypatch):
    """Lo que se le pide al motor, y lo que contesta (se cambia en cada prueba)."""
    class Motor:
        def __init__(self):
            self.llamadas = []
            self.respuesta = ("preparado", {"estado": "preparado", "contrato_id": "4928",
                                            "usuario": "laura-gomez@empresa"})

        def __call__(self, contrato, ruta, cuerpo, espera):
            self.llamadas.append((ruta, cuerpo))
            r = self.respuesta
            return r(ruta) if callable(r) else r

    m = Motor()
    monkeypatch.setattr(alta_en_el_isp, "_llamar", m)
    return m


def _contrato(orden, user_profile, estado=ContratoDeServicio.INSTALACION, **kw):
    kw.setdefault("firma_en_el_proveedor", True)
    return ContratoDeServicio.objects.create(
        org=orden.org, orden=orden, numero=f"C-{orden.numero}", huella="h" * 64, estado=estado,
        firmado_por=user_profile, firmado_en=datetime(2026, 11, 26, 15, tzinfo=tz.utc),
        servicio_isp="8039", alta_como_instalacion=True,
        datos={"cliente": {"nombre": "LAURA", "apellido": "GOMEZ", "numero_documento": "1043",
                           "telefono": "300", "correo": "", "direccion": "CRA 21", "barrio": "X"},
               "plan": "PLAN FAMILIA", "ip_elegida": "172.16.9.40",
               "servidor": {"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"},
               "orden_numero": orden.numero}, **kw)


def _confirmar(user_client, orden, monkeypatch, **extra):
    from campo import contrato as C

    monkeypatch.setattr(C, "_ip_automatica", lambda org, z: "172.16.9.40")
    return user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/", {
        "plan": "PLAN FAMILIA", "id_zona": 20053,
        "cliente": {"nombre": "Laura", "apellido": "Gomez", "numero_documento": "1043",
                    "direccion": "Cra 21"}, **extra}, format="json")


# =========================================================================== #
#  A. CONFIRMAR
# =========================================================================== #
def test_a1_SIN_los_documentos_no_se_confirma_y_dice_cuales_faltan(
        user_client, orden, config, pedidos, monkeypatch, tmp_path):
    _evidencia(orden, "cedula_por_delante", tmp_path)
    r = _confirmar(user_client, orden, monkeypatch)
    assert r.status_code == 400, r.content
    assert "Recibo público" in r.json()["detail"] and "Cédula" not in r.json()["detail"]
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()
    assert pedidos == []


def test_a2_CON_los_documentos_se_confirma_SIN_firma_y_se_pide_la_INSTALACION(
        user_client, orden, config, con_documentos, pedidos, monkeypatch):
    r = _confirmar(user_client, orden, monkeypatch)
    assert r.status_code == 201, r.content
    c = ContratoDeServicio.objects.get(orden=orden)
    assert c.firma_en_el_proveedor is True and c.estado == ContratoDeServicio.FIRMADO
    assert bool(c.pdf), "el PDF de Dexter se arma igual, sin recuadro de firma"
    assert pedidos == [{"como_instalacion": True}], "la instalación se pide AL CONFIRMAR"
    assert r.json()["contrato"]["firma_proveedor"]["activa"] is True


def test_a3_EL_CONTROL_con_el_interruptor_apagado_sigue_pidiendo_la_firma(
        user_client, orden, config, con_documentos, pedidos, monkeypatch):
    config.firma_en_el_proveedor = False
    config.save()
    r = _confirmar(user_client, orden, monkeypatch)
    assert r.status_code == 400 and "firma" in r.json()["detail"].lower(), r.content
    assert pedidos == []


def test_a5_si_la_instalacion_fallo_el_REINTENTO_tambien_la_pide_como_instalacion(
        user_client, orden, user_profile, config, pedidos):
    c = _contrato(orden, user_profile, estado=ContratoDeServicio.FIRMADO,
                  alta_estado=ContratoDeServicio.ALTA_FALLIDA, alta_intento=1)
    r = user_client.post(f"/api/campo/contratos/{c.id}/crear-en-el-isp/")
    assert r.status_code == 202, r.content
    assert pedidos == [{"como_instalacion": True}], "si no, crearía un cliente activo sin validar"


def test_a6_SIN_el_valor_de_la_instalacion_no_se_confirma_y_CON_el_viaja_al_crearla(
        user_client, orden, config, con_documentos, pedidos, monkeypatch):
    """Medido con la OT-22: el proveedor ignora el costo si se escribe despues
    de creado el cliente. Se anota antes de confirmar y viaja en el alta."""
    from campo.models import OrdenTrabajo
    from campo.tests.test_fotos_solo_en_la_plataforma import ESQUEMA

    _con_esquema(orden, {**ESQUEMA, "campos": [
        {"id": "valor_de_la_instalacion", "tipo": "decimal", "titulo": "Valor de la instalación",
         "dinero": True, "costo_de_instalacion": True}]})
    r = _confirmar(user_client, orden, monkeypatch)
    assert r.status_code == 400 and "Valor de la instalación" in r.json()["detail"], r.content
    assert pedidos == []
    OrdenTrabajo.objects.filter(pk=orden.pk).update(datos={"valor_de_la_instalacion": "50000"})
    r = _confirmar(user_client, orden, monkeypatch)
    assert r.status_code == 201, r.content
    c = ContratoDeServicio.objects.get(orden=orden)
    c.alta_como_instalacion = True
    assert alta_en_el_isp.datos_del_alta(c).get("costo_instalacion") == 50000


def test_a4_la_pantalla_sabe_que_se_firma_en_el_proveedor(user_client, orden, config):
    r = user_client.get(f"/api/campo/trabajos/{orden.id}/contrato/")
    assert r.status_code == 200 and r.json()["firma_en_el_proveedor"] is True


# =========================================================================== #
#  B. ENCADENAR
# =========================================================================== #
def test_b1_creada_la_instalacion_se_pide_preparar_el_contrato(
        orden, user_profile, config, monkeypatch, django_capture_on_commit_callbacks):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.preparar_contrato_del_proveedor, "delay",
                        lambda org, cid: encolados.append(cid))
    c = _contrato(orden, user_profile, estado=ContratoDeServicio.FIRMADO)
    with django_capture_on_commit_callbacks(execute=True):
        alta_en_el_isp._creado(c, "8039", "creado")
    c.refresh_from_db()
    assert c.estado == ContratoDeServicio.INSTALACION
    assert c.firma_proveedor_estado == ContratoDeServicio.FIRMA_PROVEEDOR_PEDIDA
    assert c.firma_proveedor_intento == 1 and encolados == [str(c.id)]


def test_b2_EL_CONTROL_sin_firma_en_el_proveedor_no_se_pide_nada(
        orden, user_profile, config, monkeypatch, django_capture_on_commit_callbacks):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.preparar_contrato_del_proveedor, "delay",
                        lambda org, cid: encolados.append(cid))
    c = _contrato(orden, user_profile, estado=ContratoDeServicio.FIRMADO,
                  firma_en_el_proveedor=False)
    with django_capture_on_commit_callbacks(execute=True):
        alta_en_el_isp._creado(c, "8039", "creado")
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "" and encolados == []


# =========================================================================== #
#  C. PREPARAR
# =========================================================================== #
def _pedido(orden, user_profile, **kw):
    return _contrato(orden, user_profile, firma_proveedor_estado="pedida",
                     firma_proveedor_intento=1, **kw)


def test_c1_viajan_los_documentos_con_su_titulo_y_queda_LISTO(
        orden, user_profile, config, con_documentos, motor):
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    ruta, cuerpo = motor.llamadas[0]
    assert ruta == "preparar-contrato-proveedor"
    assert [d["titulo"] for d in cuerpo["archivos"]] == ["Cédula por delante", "Recibo público"]
    import base64
    assert base64.b64decode(cuerpo["archivos"][0]["base64"]) == b"\xff\xd8\xff-una-foto"
    assert cuerpo["id_servicio"] == "8039" and cuerpo["intento"] == 1 and cuerpo["actor"]
    assert set(cuerpo["datos"]["cliente"]) == {"nombre", "apellido", "documento"}, \
        "para reconocer la instalación viaja lo mínimo"
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "lista" and c.contrato_proveedor == "4928"
    assert c.usuario_proveedor == "laura-gomez@empresa"
    d = c.como_dict()["firma_proveedor"]
    assert d["puede_firmar"] is True and "laura-gomez" not in str(d), \
        "el usuario del cliente no viaja a la pantalla"


def test_c2_NO_SE_SABE_queda_por_revisar_y_NO_se_vuelve_a_pedir_solo(
        orden, user_profile, config, con_documentos, motor):
    motor.respuesta = ("no_se_sabe", {"estado": "no_se_sabe"})
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "por_revisar" and "Míralo" in c.firma_proveedor_detalle
    assert CP.pedir(c) is False, "solo no se vuelve a pedir: duplicaría los documentos"
    assert CP.pedir(c, por=user_profile) is True, "una persona, después de mirar, sí"


def test_c3_FALLO_con_el_aviso_del_panel_y_se_puede_volver_a_pedir(
        orden, user_profile, config, con_documentos, motor):
    motor.respuesta = ("fallo", {"estado": "fallo", "avisos": ["El archivo es muy pequeño."],
                                 "motivo": "el panel no guardo el contrato (paso 1: no redirigio)"})
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "fallida"
    assert c.firma_proveedor_avisos == ["El archivo es muy pequeño."]
    assert "(el panel no guardo el contrato (paso 1: no redirigio))" in c.firma_proveedor_detalle, \
        "la razón del motor queda dicha"
    assert CP.pedir(c) is True and c.firma_proveedor_intento == 2, "cada pedido, un número nuevo"


def test_c4_el_motor_no_contesta_sigue_pedida_y_al_tope_por_revisar(
        orden, user_profile, config, con_documentos, motor):
    motor.respuesta = (None, {})
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "pedida"
    CP.rendirse(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "por_revisar"


def test_c5_sin_los_documentos_en_disco_no_se_llama_al_motor(
        orden, user_profile, config, motor, tmp_path):
    _evidencia(orden, "cedula_por_delante", tmp_path)
    _evidencia(orden, "recibo_publico", tmp_path, con_archivo=False)
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    c.refresh_from_db()
    assert motor.llamadas == [] and c.firma_proveedor_estado == "fallida"


def test_c6_una_lectura_que_no_se_pudo_hacer_sigue_pedida(
        orden, user_profile, config, con_documentos, motor):
    motor.respuesta = ("no_se_pudo_comprobar", {"estado": "no_se_pudo_comprobar"})
    c = _pedido(orden, user_profile)
    CP.preparar(c)
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "pedida"


def test_c7_el_TECNICO_vuelve_a_intentar_lo_que_el_proveedor_rechazo(
        user_client, orden, user_profile, config, monkeypatch, django_capture_on_commit_callbacks):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.preparar_contrato_del_proveedor, "delay",
                        lambda org, cid: encolados.append(cid))
    c = _contrato(orden, user_profile, firma_proveedor_estado="fallida", firma_proveedor_intento=1)
    with django_capture_on_commit_callbacks(execute=True):
        r = user_client.post(f"/api/campo/contratos/{c.id}/preparar-contrato-proveedor/")
    assert r.status_code == 202, r.content
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "pedida" and c.firma_proveedor_intento == 2
    assert encolados == [str(c.id)]


def test_c8_lo_que_NO_SE_SABE_no_lo_reintenta_el_tecnico_si_la_oficina(
        user_client, admin_client, orden, user_profile, config, monkeypatch):
    from campo import tasks

    monkeypatch.setattr(tasks.preparar_contrato_del_proveedor, "delay", lambda org, cid: None)
    c = _contrato(orden, user_profile, firma_proveedor_estado="por_revisar", firma_proveedor_intento=1)
    r = user_client.post(f"/api/campo/contratos/{c.id}/preparar-contrato-proveedor/")
    assert r.status_code == 403 and "oficina" in r.json()["detail"], r.content
    c.refresh_from_db()
    assert c.firma_proveedor_estado == "por_revisar"
    r = admin_client.post(f"/api/campo/contratos/{c.id}/preparar-contrato-proveedor/")
    assert r.status_code == 202, r.content


# =========================================================================== #
#  H. LAS FOTOS DEL TRABAJO, AL FINALIZAR
# =========================================================================== #
def _preparado(orden, user_profile, **kw):
    return _contrato(orden, user_profile, firma_proveedor_estado="firmada",
                     contrato_proveedor="4928", usuario_proveedor="laura-gomez@empresa", **kw)


def test_h1_al_finalizar_se_piden_las_fotos_aunque_crear_este_apagado(
        orden, user_profile, config, monkeypatch, django_capture_on_commit_callbacks):
    from campo import instalacion, tasks

    config.crear_en_el_isp = False
    config.save()
    encolados = []
    monkeypatch.setattr(tasks.subir_fotos_del_trabajo, "delay", lambda org, cid: encolados.append(cid))
    c = _preparado(orden, user_profile)
    with django_capture_on_commit_callbacks(execute=True):
        instalacion.al_finalizar(orden, user_profile)
    c.refresh_from_db()
    assert c.fotos_proveedor_estado == "pedidas" and encolados == [str(c.id)]


def test_h2_sin_contrato_preparado_no_se_piden(orden, user_profile, config):
    c = _contrato(orden, user_profile)          # sin usuario del proveedor
    assert CP.pedir_fotos(c) is False and c.fotos_proveedor_estado == ""


def test_h3_viajan_SOLO_las_del_trabajo_con_su_titulo_y_al_usuario_de_ese_contrato(
        orden, user_profile, config, motor, tmp_path):
    for r in ("cedula_por_delante", "recibo_publico", "onu_instalada", "medicion_de_potencia"):
        _evidencia(orden, r, tmp_path)
    motor.respuesta = ("subido", {"estado": "subido"})
    c = _preparado(orden, user_profile, fotos_proveedor_estado="pedidas", fotos_proveedor_intento=1)
    CP.subir_fotos(c)
    ruta, cuerpo = motor.llamadas[0]
    assert ruta == "subir-fotos-del-trabajo"
    assert [a["titulo"] for a in cuerpo["archivos"]] == ["ONU instalada", "Medición"], \
        "la cédula y el recibo ya subieron con el contrato"
    assert cuerpo["usuario"] == "laura-gomez@empresa" and cuerpo["id_servicio"] == "8039"
    c.refresh_from_db()
    assert c.fotos_proveedor_estado == "subidas"
    assert c.como_dict()["firma_proveedor"]["fotos"] == "subidas"


@pytest.mark.parametrize("respuesta,esperado", [
    (("no_se_sabe", {"estado": "no_se_sabe"}), "por_revisar"),
    (("fallo", {"estado": "fallo", "motivo": "paso 1: no redirigio"}), "fallidas"),
    ((None, {}), "pedidas"),
    (("no_se_pudo_comprobar", {"estado": "no_se_pudo_comprobar"}), "pedidas"),
])
def test_h4_como_quedan_segun_el_motor(orden, user_profile, config, motor, tmp_path,
                                       respuesta, esperado):
    _evidencia(orden, "onu_instalada", tmp_path)
    motor.respuesta = respuesta
    c = _preparado(orden, user_profile, fotos_proveedor_estado="pedidas", fotos_proveedor_intento=1)
    CP.subir_fotos(c)
    c.refresh_from_db()
    assert c.fotos_proveedor_estado == esperado
    if esperado == "fallidas":
        assert "(paso 1: no redirigio)" in c.fotos_proveedor_detalle


def test_h5_VOLVER_A_SUBIR_las_fotos_el_tecnico_si_fallaron_la_oficina_si_no_se_sabe(
        user_client, admin_client, orden, user_profile, config, monkeypatch,
        django_capture_on_commit_callbacks):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.subir_fotos_del_trabajo, "delay", lambda org, cid: encolados.append(cid))
    c = _preparado(orden, user_profile, fotos_proveedor_estado="fallidas", fotos_proveedor_intento=1)
    with django_capture_on_commit_callbacks(execute=True):
        r = user_client.post(f"/api/campo/contratos/{c.id}/subir-fotos/")
    assert r.status_code == 202, r.content
    c.refresh_from_db()
    assert c.fotos_proveedor_estado == "pedidas" and c.fotos_proveedor_intento == 2
    assert encolados == [str(c.id)]
    ContratoDeServicio.objects.filter(pk=c.pk).update(fotos_proveedor_estado="por_revisar")
    r = user_client.post(f"/api/campo/contratos/{c.id}/subir-fotos/")
    assert r.status_code == 403, r.content
    with django_capture_on_commit_callbacks(execute=True):
        r = admin_client.post(f"/api/campo/contratos/{c.id}/subir-fotos/")
    assert r.status_code == 202, r.content
    ContratoDeServicio.objects.filter(pk=c.pk).update(fotos_proveedor_estado="subidas")
    r = admin_client.post(f"/api/campo/contratos/{c.id}/subir-fotos/")
    assert r.status_code == 409


# =========================================================================== #
#  D. EL ENLACE
# =========================================================================== #
ENLACE = "http://portal.example/login-panel/AAAA.BBBB.CCCC/"


def test_d1_con_el_contrato_listo_da_el_enlace_sin_guardarlo(
        user_client, orden, user_profile, config, motor):
    c = _contrato(orden, user_profile, firma_proveedor_estado="lista",
                  contrato_proveedor="4928", usuario_proveedor="laura-gomez@empresa")
    motor.respuesta = ("listo", {"estado": "listo", "enlace": ENLACE})
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/enlace-de-firma/")
    assert r.status_code == 200 and r.json() == {"enlace": ENLACE}
    assert r["Cache-Control"] == "no-store"
    assert motor.llamadas[-1] == ("enlace-de-firma",
                                  {"usuario": "laura-gomez@empresa", "id_servicio": "8039"})
    c.refresh_from_db()
    guardado = str({f.name: getattr(c, f.name) for f in c._meta.fields})
    assert "AAAA" not in guardado, "el enlace no queda en el contrato"


def test_d2_sin_el_contrato_listo_no_hay_enlace(user_client, orden, user_profile, config, motor):
    _contrato(orden, user_profile, firma_proveedor_estado="pedida")
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/enlace-de-firma/")
    assert r.status_code == 409 and motor.llamadas == []


def test_d3_algo_que_no_es_un_enlace_web_no_sale(user_client, orden, user_profile, config, motor):
    _contrato(orden, user_profile, firma_proveedor_estado="lista", contrato_proveedor="4928",
              usuario_proveedor="u@e")
    motor.respuesta = ("listo", {"estado": "listo", "enlace": "javascript:alert(1)"})
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/enlace-de-firma/")
    assert r.status_code == 409


# =========================================================================== #
#  E. LA FIRMA
# =========================================================================== #
@pytest.mark.parametrize("firmado,esperado", [(True, "firmada"), (False, "lista")])
def test_e1_se_lee_en_el_proveedor(user_client, orden, user_profile, config, motor,
                                   firmado, esperado):
    c = _contrato(orden, user_profile, firma_proveedor_estado="lista", contrato_proveedor="4928",
                  usuario_proveedor="u@e")
    motor.respuesta = ("listo", {"estado": "listo", "firmado": firmado})
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/comprobar-firma/")
    assert r.status_code == 200
    assert motor.llamadas[-1] == ("firma-en-el-proveedor", {"contrato_id": "4928"})
    c.refresh_from_db()
    assert c.firma_proveedor_estado == esperado
    assert bool(c.firmado_en_el_proveedor_en) is firmado
    assert r.json()["contrato"]["firma_proveedor"]["firmado"] is firmado


# =========================================================================== #
#  F. LA EMPRESA
# =========================================================================== #
def test_f1_el_interruptor_exige_crear_y_validar(admin_client, org_a):
    ConfiguracionDeContrato.objects.create(org=org_a, nit="900", servidores=SERVIDORES)
    r = admin_client.put("/api/campo/contrato/configuracion/",
                         {"firma_en_el_proveedor": True}, format="json")
    assert r.status_code == 400 and "Crear al cliente" in r.json()["detail"]
    r = admin_client.put("/api/campo/contrato/configuracion/",
                         {"firma_en_el_proveedor": True, "crear_en_el_isp": True,
                          "validar_antes_de_activar": True}, format="json")
    assert r.status_code == 200 and r.json()["firma_en_el_proveedor"] is True


# =========================================================================== #
#  G. LA REVISION DEL CIERRE
# =========================================================================== #
@pytest.mark.parametrize("estado,ok,texto", [
    ("firmada", True, "firmó"), ("lista", None, "todavía no"),
    ("fallida", False, "no quedó listo"), ("pedida", None, "preparando")])
def test_g1_el_punto_del_contrato_dice_como_esta_la_firma(orden, user_profile, config,
                                                           estado, ok, texto):
    from campo.revision_del_cierre import _de_la_instalacion

    _contrato(orden, user_profile, firma_proveedor_estado=estado, contrato_proveedor="4928")
    punto = next(p for p in _de_la_instalacion(orden) if p["clave"] == "contrato")
    assert punto["ok"] is ok and texto in punto["texto"], punto
