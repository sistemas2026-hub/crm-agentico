# -*- coding: utf-8 -*-
"""La instalacion que valida una persona (26/11/2026). Ver campo/instalacion.py.

El usuario: «cuando el tecnico manda finalizar trabajo entra en validacion
humana y si aprueba la instalacion se le informa al tecnico para que valide
servicio y entregue al cliente, y despues cierra el ticket».

  A  CUANDO SE CREA -- no al firmar: al finalizar, como INSTALACION, con el
     costo que cobro el tecnico y el serial de la ONU.
  B  APROBAR -- solo una persona, solo una instalacion que ya existe en el
     proveedor; activada, la orden queda aprobada y al tecnico le llega el aviso;
     el ticket NO se cierra.
  C  ENTREGAR -- el tecnico confirma: la orden se cierra y AHI el ticket.
  D  NADIE MAS -- ni «Aprobar» de Programacion ni el Supervisor automatico.
"""
import base64
import io
from datetime import datetime, timezone as tz

import pytest

from campo import instalacion
from campo import plantillas as P
from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import alta_en_el_isp

pytestmark = pytest.mark.django_db

SERVIDORES = [{"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1", "vlan": 300}]
DEFINICION = {"campos": [
    {"titulo": "Valor de la instalación", "tipo": "numero", "dinero": True,
     "costo_de_instalacion": True, "obligatorio": False},
    {"titulo": "Equipos o material extra", "tipo": "numero", "dinero": True, "obligatorio": False}],
    "evidencias": []}


def _firma_png() -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(img).line([(40, 200), (560, 90)], fill="black", width=4)
    b = io.BytesIO()
    img.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra",
                                 nombre="Instalación de fibra", labor="instalacion")
    return WorkTypeVersion.objects.create(work_type=wt, version=1, schema_version=1,
                                          estado=WorkTypeVersion.PUBLICADA,
                                          esquema=P.componer(DEFINICION))


@pytest.fixture
def config(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, nit="900", servidores=SERVIDORES, crear_en_el_isp=True,
        validar_antes_de_activar=True)


@pytest.fixture
def orden(org_a, user_profile, version):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=401, tipo_trabajo_version=version, cliente_nombre="LAURA",
        cliente_direccion="Cra 21 # 45-12", cliente_telefono="3000000000",
        origen_sistema="wisphub", origen_tipo="ticket", origen_ref="#91301",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico_lider",
                                     es_principal=True)
    return o


@pytest.fixture
def pedidos(monkeypatch):
    """Las altas que se pidieron, sin encolar nada."""
    vistos = []
    monkeypatch.setattr(alta_en_el_isp, "pedir_alta",
                        lambda contrato, por=None, como_instalacion=False:
                        vistos.append({"contrato": contrato.id, "como_instalacion": como_instalacion})
                        or True)
    return vistos


@pytest.fixture
def avisos(monkeypatch):
    from campo.services import avisos as A

    vistos = []
    monkeypatch.setattr(A, "avisar_instalacion_aprobada", lambda orden: vistos.append(orden.numero) or True)
    return vistos


@pytest.fixture
def tickets(monkeypatch):
    from campo.services import cierre_en_isp

    vistos = []
    monkeypatch.setattr(cierre_en_isp, "cerrar_ticket_al_validar",
                        lambda orden, profile, extra="": vistos.append(orden.numero) or {"estado": "cerrado"})
    return vistos


def _contrato(orden, user_profile, estado=ContratoDeServicio.FIRMADO, **kw):
    return ContratoDeServicio.objects.create(
        org=orden.org, orden=orden, numero=f"C-{orden.numero}", huella="h" * 64, estado=estado,
        firmado_por=user_profile, firmado_en=datetime(2026, 11, 26, 15, tzinfo=tz.utc),
        datos={"cliente": {"nombre": "LAURA", "apellido": "GOMEZ", "numero_documento": "1043",
                           "telefono": "300", "correo": "", "direccion": "CRA 21", "barrio": "X"},
               "plan": "PLAN FAMILIA", "ip_elegida": "172.16.9.40",
               "servidor": {"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"},
               "orden_numero": orden.numero}, **kw)


def _finalizada(orden):
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO, estado_validacion=OrdenTrabajo.PENDIENTE)
    orden.refresh_from_db()
    return orden


# =========================================================================== #
#  A. CUANDO SE CREA
# =========================================================================== #
def test_a1_AL_FIRMAR_no_se_crea_nada_en_el_proveedor(user_client, orden, config, pedidos, monkeypatch):
    from campo import contrato as C

    monkeypatch.setattr(C, "_ip_automatica", lambda org, z: "172.16.9.40")
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/contrato/", {
        "plan": "PLAN FAMILIA", "id_zona": 20053, "firma_png_base64": _firma_png(),
        "cliente": {"nombre": "Laura", "numero_documento": "1043", "direccion": "Cra 21"}},
        format="json")
    assert r.status_code == 201, r.content
    assert pedidos == [], "con la validación encendida, el alta no sale al firmar"


def test_a2_AL_FINALIZAR_se_pide_COMO_INSTALACION(user_client, orden, config, user_profile, pedidos):
    c = _contrato(orden, user_profile)
    r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/", {}, format="json")
    assert r.status_code == 200, r.content
    assert pedidos == [{"contrato": c.id, "como_instalacion": True}]


def test_a3_sin_la_validacion_encendida_al_finalizar_no_se_pide(user_client, orden, config, user_profile,
                                                                 pedidos):
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(validar_antes_de_activar=False)
    _contrato(orden, user_profile)
    assert user_client.post(f"/api/campo/trabajos/{orden.id}/completar/", {}, format="json").status_code == 200
    assert pedidos == []


def test_a4_creada_queda_como_INSTALACION_y_lleva_el_costo_y_la_onu(orden, config, user_profile):
    from campo.activacion_onu import ActivacionDeOnu

    ids = {c["titulo"]: c["id"] for c in orden.tipo_trabajo_version.esquema["campos"]}
    OrdenTrabajo.objects.filter(pk=orden.pk).update(datos={
        ids["Valor de la instalación"]: 80000, ids["Equipos o material extra"]: 25000})
    ActivacionDeOnu.objects.create(org=orden.org, orden=orden, serial="FHTT12345678",
                                   estado="activada")
    orden.refresh_from_db()
    c = _contrato(orden, user_profile, alta_como_instalacion=True)
    d = alta_en_el_isp.datos_del_alta(c)
    assert d["costo_instalacion"] == 80000, "el costo es el dato marcado, no la suma del dinero"
    assert d["serial_onu"] == "FHTT12345678"
    alta_en_el_isp._creado(c, "7000", "creado")
    c.refresh_from_db()
    assert c.estado == ContratoDeServicio.INSTALACION and c.servicio_isp == "7000"


def test_a5_un_alta_de_cliente_normal_no_lleva_costo_y_queda_en_el_isp(orden, config, user_profile):
    c = _contrato(orden, user_profile)
    assert "costo_instalacion" not in alta_en_el_isp.datos_del_alta(c)
    alta_en_el_isp._creado(c, "9000", "creado")
    c.refresh_from_db()
    assert c.estado == ContratoDeServicio.EN_EL_ISP


# =========================================================================== #
#  B. APROBAR
# =========================================================================== #
def _url_aprobar(orden):
    return f"/api/campo/trabajos/{orden.id}/aprobar-instalacion/"


def test_b1_aprobar_PIDE_LA_ACTIVACION_despues_del_commit(admin_client, orden, config, user_profile,
                                                          django_capture_on_commit_callbacks, monkeypatch):
    from campo import tasks

    encolados = []
    monkeypatch.setattr(tasks.activar_cliente_en_el_isp, "delay",
                        lambda org_id, contrato_id: encolados.append(contrato_id))
    c = _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION,
                  servicio_isp="7000", alta_como_instalacion=True)
    with django_capture_on_commit_callbacks(execute=True):
        r = admin_client.post(_url_aprobar(orden), {}, format="json")
    assert r.status_code == 202, r.content
    c.refresh_from_db()
    assert c.activacion_estado == ContratoDeServicio.ACTIVACION_PEDIDA and c.activacion_intento == 1
    assert encolados == [str(c.id)]
    assert r.json()["contrato"]["instalacion"]["se_puede_activar"] is False, "en vuelo: no otra encima"
    assert admin_client.post(_url_aprobar(orden), {}, format="json").status_code == 409


@pytest.mark.parametrize("como, palabra", [
    ("sin_finalizar", "no finalizó"),
    ("sin_instalacion", "Todavía no hay una instalación"),
    ("ya_cliente", "ya es cliente"),
])
def test_b2_lo_que_NO_se_puede_aprobar_lo_dice(admin_client, orden, config, user_profile, como, palabra):
    if como != "sin_finalizar":
        _finalizada(orden)
    estado = {"sin_finalizar": ContratoDeServicio.INSTALACION,
              "sin_instalacion": ContratoDeServicio.FIRMADO,
              "ya_cliente": ContratoDeServicio.EN_EL_ISP}[como]
    _contrato(orden, user_profile, estado=estado, servicio_isp="7000")
    r = admin_client.post(_url_aprobar(orden), {}, format="json")
    assert r.status_code == 409 and palabra in r.json()["detail"]


def test_b3_un_TECNICO_no_aprueba(user_client, orden, config, user_profile):
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="7000")
    assert user_client.post(_url_aprobar(orden), {}, format="json").status_code == 403


def test_b4_ACTIVADA_la_orden_queda_aprobada_y_avisa_al_tecnico_SIN_cerrar_el_ticket(
        orden, config, user_profile, admin_profile, avisos, tickets):
    c = _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION,
                  servicio_isp="7000", activacion_estado=ContratoDeServicio.ACTIVACION_PEDIDA,
                  activado_por=admin_profile)
    instalacion._aplicar(c, "activado", {"estado": "activado", "id_cliente": "7000"})
    c.refresh_from_db()
    orden.refresh_from_db()
    assert c.estado == ContratoDeServicio.EN_EL_ISP and c.activado_en is not None
    assert orden.estado_validacion == OrdenTrabajo.APROBADO
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO, "no se cierra: falta la entrega"
    assert avisos == [orden.numero], "al técnico le llega «valida el servicio y entrega»"
    assert tickets == [], "el ticket NO se cierra al aprobar"


def test_b5_si_FALLA_queda_dicho_por_que_y_se_puede_volver_a_aprobar(orden, config, user_profile,
                                                                     admin_profile):
    c = _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION,
                  servicio_isp="7000", activacion_estado=ContratoDeServicio.ACTIVACION_PEDIDA,
                  activado_por=admin_profile, activacion_intento=1)
    instalacion._aplicar(c, "fallo", {"estado": "fallo", "motivo": "Invalid parameters: x"})
    c.refresh_from_db()
    assert c.activacion_estado == ContratoDeServicio.ACTIVACION_FALLIDA
    assert "rechazó" in c.activacion_detalle and "Invalid parameters" in c.activacion_detalle
    assert c.como_dict()["instalacion"]["se_puede_activar"] is True
    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.PENDIENTE


def test_b6_POR_REVISAR_tambien_deja_volver_a_aprobar(orden, config, user_profile, admin_profile):
    c = _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION,
                  servicio_isp="7000", activacion_estado=ContratoDeServicio.ACTIVACION_EN_CURSO,
                  activado_por=admin_profile, activacion_intento=1)
    instalacion.rendirse(c)
    c.refresh_from_db()
    assert c.activacion_estado == ContratoDeServicio.ACTIVACION_POR_REVISAR
    assert c.como_dict()["instalacion"]["se_puede_activar"] is True


# =========================================================================== #
#  C. ENTREGAR
# =========================================================================== #
def _url_entregar(orden):
    return f"/api/campo/trabajos/{orden.id}/instalacion-entregada/"


def test_c1_ANTES_de_aprobar_no_se_entrega(user_client, orden, config, user_profile, tickets):
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="7000")
    r = user_client.post(_url_entregar(orden), {}, format="json")
    assert r.status_code == 409 and "Todavía no está aprobada" in r.json()["detail"]
    assert tickets == []


def test_c2_ENTREGADA_se_cierra_la_orden_y_AHI_el_ticket(user_client, orden, config, user_profile, tickets):
    from campo.models import EventoTrabajo

    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.EN_EL_ISP, servicio_isp="7000")
    OrdenTrabajo.objects.filter(pk=orden.pk).update(estado_validacion=OrdenTrabajo.APROBADO)
    #  27/11/2026: el material y el cierre van DESPUES de aprobar, y sin el
    #  reporte de cierre no se finaliza (`test_cierre_despues_de_aprobar`).
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="cierre_campo", datos={})
    r = user_client.post(_url_entregar(orden), {}, format="json")
    assert r.status_code == 200, r.content
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.CERRADA
    assert tickets == [orden.numero]
    again = user_client.post(_url_entregar(orden), {}, format="json")
    assert again.status_code == 200 and again.json().get("ya_estaba") is True and tickets == [orden.numero]


# =========================================================================== #
#  D. NADIE MAS LA APRUEBA
# =========================================================================== #
def test_d1_APROBAR_DE_PROGRAMACION_no_aprueba_una_instalacion(admin_client, orden, config, user_profile,
                                                                tickets):
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="7000")
    r = admin_client.post(f"/api/campo/trabajos/{orden.id}/validar/",
                          {"decision": "aprobar", "observacion": ""}, format="json")
    assert r.status_code == 409 and r.json()["error"] == "ES_UNA_INSTALACION"
    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.PENDIENTE and tickets == []


def test_d2_EL_SUPERVISOR_AUTOMATICO_ni_la_cierra_ni_la_devuelve(orden, config, user_profile):
    from django.utils import timezone

    from campo import cierre_por_el_supervisor as S

    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="7000")
    revision = {"veredicto": "no_cerrar", "sugeridas": ["x"], "puntos": []}
    assert S._intentar(orden, revision, timezone.now()) == "salteada"
    assert S.atender_la_que_no_cierra(orden, revision) == "nada"


def test_d3_sin_la_validacion_encendida_NO_es_una_instalacion_validada(orden, config, user_profile):
    _contrato(orden, user_profile)
    assert instalacion.requiere_validacion_humana(orden) is True
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(validar_antes_de_activar=False)
    assert instalacion.requiere_validacion_humana(orden) is False


def test_d4_POR_ACTIVAR_lista_la_instalacion_con_su_contrato(admin_client, user_client, orden, config,
                                                             user_profile, monkeypatch):
    #  La revision del cierre usa una consulta JSON que SQLite no tiene (las
    #  pruebas de la revision corren contra PostgreSQL): aca se ve que VIAJA.
    from campo import revision_del_cierre

    monkeypatch.setattr(revision_del_cierre, "revisar", lambda orden: {"veredicto": "revisar"})
    _contrato(_finalizada(orden), user_profile, estado=ContratoDeServicio.INSTALACION, servicio_isp="7000")
    r = admin_client.get("/api/campo/instalaciones/por-activar/")
    assert r.status_code == 200, r.content
    fila = r.json()["instalaciones"][0]
    assert fila["numero"] == 401 and fila["espera"] == "validacion"
    assert fila["contrato"]["estado"] == "instalacion" and fila["revision"] == {"veredicto": "revisar"}
    assert user_client.get("/api/campo/instalaciones/por-activar/").status_code == 403


def test_d5_la_configuracion_guarda_el_interruptor(admin_client, config):
    r = admin_client.put("/api/campo/contrato/configuracion/", {"validar_antes_de_activar": False},
                         format="json")
    assert r.status_code == 200 and r.json()["validar_antes_de_activar"] is False


# =========================================================================== #
#  E. LO QUE REVISA DEXTER DE UNA INSTALACION
# =========================================================================== #
def _puntos(orden):
    from campo.revision_del_cierre import _de_la_instalacion

    return {p["clave"]: p for p in _de_la_instalacion(orden)}


def test_e1_SIN_CONTRATO_no_es_una_instalacion_validada_y_no_suma_puntos(orden, config):
    assert _puntos(orden) == {}, "sin contrato vigente no aplica: nada que mirar aqui"


def test_e2_contrato_firmado_dinero_anotado_y_la_onu(orden, config, user_profile):
    from campo.activacion_onu import ActivacionDeOnu

    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(activar_onu=True)
    ids = {c["titulo"]: c["id"] for c in orden.tipo_trabajo_version.esquema["campos"]}
    OrdenTrabajo.objects.filter(pk=orden.pk).update(datos={
        ids["Valor de la instalación"]: 80000, ids["Equipos o material extra"]: 25000})
    orden.refresh_from_db()
    _contrato(orden, user_profile)
    p = _puntos(orden)
    assert p["contrato"]["ok"] is True
    assert p["dinero"]["ok"] is True and "$105.000" in p["dinero"]["texto"]
    assert p["onu"]["ok"] is None, "sin activación desde la app: que la persona la mire"
    ActivacionDeOnu.objects.create(org=orden.org, orden=orden, serial="FHTT1", estado="activada",
                                   olt="3", placa="3", puerto="15")
    p = _puntos(orden)
    assert p["onu"]["ok"] is True and "OLT 3 · placa 3 · puerto 15" in p["onu"]["texto"]


def test_e3_lo_que_FALTA_queda_en_duda_y_un_documento_cambiado_tambien(orden, config, user_profile):
    _contrato(orden, user_profile)
    ContratoDeServicio.objects.filter(orden=orden).update(
        datos={**ContratoDeServicio.objects.get(orden=orden).datos, "documento_cambiado": True})
    p = _puntos(orden)
    assert p["dinero"]["ok"] is None and "no anotó" in p["dinero"]["texto"]
    assert p["contrato"]["ok"] is None and "revisa la cédula" in p["contrato"]["texto"]
    assert "onu" not in p, "con «Activar ONU» apagado no se pregunta por la ONU"


def test_e4_en_una_empresa_SIN_la_validacion_no_cambia_nada(orden, config, user_profile):
    ConfiguracionDeContrato.objects.filter(pk=config.pk).update(validar_antes_de_activar=False)
    _contrato(orden, user_profile)
    assert _puntos(orden) == {}
