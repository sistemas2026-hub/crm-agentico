# -*- coding: utf-8 -*-
"""
================================================================================
 AL DESPACHAR UN CASO, LO QUE EL SISTEMA YA SABE VIENE CARGADO
================================================================================

Pedido del usuario (13/10/2026): al despachar habia que escribir el barrio, como
se entra y que hay que hacer, con el barrio en la ficha del ISP y la lectura del
Supervisor ya hecha. `GET /campo/casos-despachables/<id>/ficha/` trae, para UN
caso aprobado:

  A  el barrio de la ficha del cliente (lo que el reparto mapea a una zona)
  B  la lectura del Supervisor de la propuesta ACEPTADA: hipotesis y
     recomendacion
  C  la descripcion del ticket TAPADA -- como se entra no se extrae solo
  D  un caso no aprobado, o de otra empresa, no existe (404)

La ficha del motor se sustituye: es la unica pieza externa.

    pytest campo/tests/test_ficha_despachable.py
================================================================================
"""

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


def _ruta(caso):
    return f"/api/campo/casos-despachables/{caso.id}/ficha/"


def _caso(org, **extra):
    from cases.models import Case

    campos = {"org": org, "name": "Internet intermitente", "status": "New",
              "priority": "Normal", "is_active": True,
              "description": ("Cliente reporta cortes. Vive en el apto 302, la "
                              "porteria pide cedula 1045678901, llamar al "
                              "300 123 4567 antes de ir.")}
    campos.update(extra)
    return Case.objects.create(**campos)


def _propuesta(org, caso, estado=None):
    from operaciones.diagnostico_de_ticket import ETIQUETA_LECTURA
    from operaciones.models import PropuestaSupervisor

    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=estado or PropuestaSupervisor.ACEPTADA,
        accion_propuesta="Revisar el conector de la roseta",
        motivo="Revisar el conector de la roseta. Puede ser la acometida.",
        evidencia=[{"fuente": "lectura_ticket", "dato": f"{ETIQUETA_LECTURA}"
                    "probable conector dañado (confianza media)",
                    "momento": "2026-10-13T03:00:00Z"}])


@pytest.fixture
def ficha_del_motor():
    contexto = {"cliente": {"localidad": "MARTHA GISELA", "nombre": "X"}}
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    return_value=contexto):
        yield


def test_a_b_c_trae_barrio_lectura_y_descripcion_tapada(
        admin_client, org_a, ficha_del_motor):
    caso = _caso(org_a)
    _propuesta(org_a, caso)

    r = admin_client.get(_ruta(caso))
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["localidad"] == "MARTHA GISELA"                         # A
    assert d["lectura"]["hipotesis"] == "probable conector dañado (confianza media)"
    assert d["lectura"]["recomendacion"] == "Revisar el conector de la roseta"  # B
    assert "apto 302" in d["descripcion"]                            # C: lo util
    assert "1045678901" not in d["descripcion"]                      # C: tapado
    assert "300 123 4567" not in d["descripcion"]


def test_d_un_caso_sin_propuesta_aceptada_no_existe(admin_client, org_a,
                                                    ficha_del_motor):
    from operaciones.models import PropuestaSupervisor

    caso = _caso(org_a)
    _propuesta(org_a, caso, estado=PropuestaSupervisor.RECHAZADA)
    assert admin_client.get(_ruta(caso)).status_code == 404
    otro = _caso(org_a)
    assert admin_client.get(_ruta(otro)).status_code == 404


def test_d2_un_caso_de_otra_empresa_no_existe(admin_client, org_a, org_b,
                                              ficha_del_motor):
    """El caso existe y esta aprobado, pero en OTRA empresa. Se crea con el
    contexto RLS de esa empresa -- sin eso la base ni siquiera deja crearlo --
    y se vuelve al de la sesion antes de pedirlo."""
    from conftest import set_rls_context

    set_rls_context(org_b)
    caso = _caso(org_b)
    _propuesta(org_b, caso)
    set_rls_context(org_a)
    assert admin_client.get(_ruta(caso)).status_code == 404


def test_e_si_el_motor_no_responde_la_ficha_sale_igual_sin_barrio(
        admin_client, org_a):
    caso = _caso(org_a)
    _propuesta(org_a, caso)
    with mock.patch("campo.services.despacho.contexto_del_caso",
                    side_effect=RuntimeError("motor caido")):
        r = admin_client.get(_ruta(caso))
    assert r.status_code == 200, r.content
    assert r.json()["localidad"] == ""
    assert r.json()["lectura"]["recomendacion"]       # lo que vive en el CRM llega


# =============================================================================
#  POR QUE PASO SOLO  --  17/10/2026
# =============================================================================
#  Desde la Fase 4 pasan solas fallas que la medicion no confirma del todo, y
#  el aviso para quien despacha no llegaba a esta pantalla (auditor
#  independiente de la Fase 4, hallazgo 2).

def test_f_si_paso_solo_la_ficha_dice_por_que(admin_client, org_a,
                                               ficha_del_motor):
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
    porque = ("falla de servicio CONFIRMADA por la medicion del equipo: perdio "
              "la señal optica (LOS/LOF). Puede ser la fibra o un equipo "
              "desenchufado: el despachador lo confirma con el cliente")
    sup.revisar(p, actor=None, automatico=True,
                decision=PropuestaSupervisor.ACEPTADA,
                comentario=f"{pad.PREFIJO_DEL_PASE}{porque}")

    r = admin_client.get(_ruta(caso))

    assert r.status_code == 200, r.content
    assert r.json()["lectura"]["por_que_paso"] == porque


def test_g_si_la_acepto_una_persona_no_dice_que_paso_solo(
        admin_client, admin_profile, org_a, ficha_del_motor):
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA)
    #  Aunque la nota empiece igual que la del pase: lo que decide es QUIEN
    #  acepto, no como empieza el texto.
    sup.revisar(p, actor=admin_profile, decision=PropuestaSupervisor.ACEPTADA,
                comentario=f"{pad.PREFIJO_DEL_PASE}lo revise yo: hay que ir")

    r = admin_client.get(_ruta(caso))

    assert r.status_code == 200, r.content
    assert r.json()["lectura"]["por_que_paso"] == ""


# =============================================================================
#  EL CORTE DE RED  --  19/10/2026
# =============================================================================
#  La marca viajaba solo en 'por_que_paso', que esta vacio si la acepto una
#  persona: el despachador veia los casos sueltos y armaba una orden por
#  cliente (auditor independiente).

def _con_la_medicion(propuesta, caso, en_los):
    from django.utils import timezone

    from operaciones import medicion_de_fallas as mdf
    from operaciones import paso_a_despacho as pad

    propuesta.evidencia = [*propuesta.evidencia, {
        "fuente": pad.FUENTE_MEDICION, "id": str(caso.id), "dato": "medicion",
        "observado_en": timezone.now().isoformat(),
        **mdf.de_la_respuesta({
            "id_servicio": "3614", "equipo_registrado": True,
            "estado": "caido", "causa_caida": "fibra", "senal_dbm": None,
            "senal": "sin_dato", "estado_config": "match", "motivo": "",
            "puerto": "3/2/11", "onus_en_los_a_la_vez": en_los})}]
    propuesta.save(update_fields=["evidencia"])
    return propuesta


def test_h_el_corte_de_red_llega_aunque_la_acepte_una_persona(
        admin_client, admin_profile, org_a, ficha_del_motor):
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor

    marcado, suelto = _caso(org_a), _caso(org_a)
    for caso, en_los in ((marcado, 3), (suelto, 1)):
        p = _con_la_medicion(
            _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA),
            caso, en_los)
        sup.revisar(p, actor=admin_profile,
                    decision=PropuestaSupervisor.ACEPTADA,
                    comentario="lo revise yo: hay que ir")

    lectura = admin_client.get(_ruta(marcado)).json()["lectura"]
    assert lectura["por_que_paso"] == ""
    assert ("CORTE DE RED: 3 equipos del puerto 3/2/11"
            in lectura["corte_de_red"])
    assert admin_client.get(_ruta(suelto)).json()["lectura"]["corte_de_red"] == ""


def test_h2_si_paso_solo_marcado_la_marca_no_se_repite(
        admin_client, org_a, ficha_del_motor):
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor

    caso = _caso(org_a)
    p = _con_la_medicion(
        _propuesta(org_a, caso, estado=PropuestaSupervisor.PROPUESTA), caso, 3)
    marca = pad.texto_del_corte_de_red(pad.ultima_medicion(p))
    sup.revisar(p, actor=None, automatico=True,
                decision=PropuestaSupervisor.ACEPTADA,
                comentario=f"{pad.PREFIJO_DEL_PASE}falla CONFIRMADA. {marca}")

    lectura = admin_client.get(_ruta(caso)).json()["lectura"]
    assert marca in lectura["por_que_paso"]
    assert lectura["corte_de_red"] == ""


# ---------------------------------------------------------------------------
# I · el formulario lleno  --  19/10/2026
# ---------------------------------------------------------------------------
# Pedido del usuario: al tocar «Despachar», plantilla, fecha y prioridad
# elegidas segun lo que vio el Supervisor. La ficha trae los tres datos.

def _plantilla(org, codigo, nombre, *, asuntos=(), plazo=None):
    from campo.models import WorkType, WorkTypeVersion
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=nombre,
                                   labor="trabajos", asuntos=list(asuntos),
                                   plazo_dias=plazo)
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "foto", "tipo": "foto"}]})


def test_i_la_plantilla_viene_por_el_asunto_del_ticket(
        admin_client, org_a, ficha_del_motor):
    _plantilla(org_a, "router", "Cambio de router",
               asuntos=["Cambio De Router Wifi"])
    traslado = _plantilla(org_a, "traslado", "Traslado",
                          asuntos=["Cambio De Domicilio"], plazo=3)
    #  Sin mayusculas, con tilde de mas y doble espacio: es el mismo asunto.
    caso = _caso(org_a, name="cambio de  domicílio")
    _propuesta(org_a, caso)

    d = admin_client.get(_ruta(caso)).json()
    assert d["plantilla_sugerida"] == str(traslado.id)


def test_i2_un_asunto_que_ninguna_declara_no_propone_plantilla(
        admin_client, org_a, ficha_del_motor):
    _plantilla(org_a, "reconexion", "Reconexion", asuntos=["Reconexion"])
    caso = _caso(org_a)
    _propuesta(org_a, caso)
    assert admin_client.get(_ruta(caso)).json()["plantilla_sugerida"] is None


def test_i3_una_plantilla_dada_de_baja_no_se_propone(
        admin_client, org_a, ficha_del_motor):
    from campo.models import WorkType
    v = _plantilla(org_a, "traslado", "Traslado", asuntos=["Cambio De Domicilio"])
    WorkType.objects.filter(pk=v.work_type_id).update(activo=False)
    caso = _caso(org_a, name="Cambio De Domicilio")
    _propuesta(org_a, caso)
    assert admin_client.get(_ruta(caso)).json()["plantilla_sugerida"] is None


def test_j_trae_la_creacion_y_la_prioridad_del_supervisor(
        admin_client, org_a, ficha_del_motor):
    from operaciones.models import PropuestaSupervisor
    caso = _caso(org_a)
    p = _propuesta(org_a, caso)
    PropuestaSupervisor.objects.filter(pk=p.pk).update(prioridad=14)

    d = admin_client.get(_ruta(caso)).json()
    assert d["prioridad_supervisor"] == 14
    assert d["creado"].startswith(caso.created_at.date().isoformat())


def test_k_la_lista_de_plantillas_trae_el_plazo(admin_client, org_a):
    _plantilla(org_a, "traslado", "Traslado", plazo=3)
    p = admin_client.get("/api/campo/plantillas-de-trabajo/").json()["plantillas"][0]
    assert p["plazo_dias"] == 3
