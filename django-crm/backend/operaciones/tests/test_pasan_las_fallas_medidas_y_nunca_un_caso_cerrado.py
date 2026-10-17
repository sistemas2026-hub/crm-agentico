# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 3 · PASAN SOLAS LAS FALLAS MEDIDAS, Y NUNCA UN CASO CERRADO
================================================================================

LO QUE SE MIDIO EL 16/10/2026, Y LO QUE SE DECIDIO
--------------------------------------------------
- La regla 1 no podia dejar pasar nada: la lectura clasificaba el equipo con
  el endpoint liviano (Online u Offline, sin causa) y con claves que el
  clasificador no lee. Ahora decide la MEDICION de 'diagnosticar_servicio',
  la herramienta del motor que ya usa el cierre de desincronizados.
- Decidido por el usuario: pasa sola SOLO la falla con el equipo en linea y
  la señal fuera del rango de la guia (-25 a -8 dBm, el del motor). Una caida
  por LOS o LOF va a una persona: desde la OLT no se distingue una fibra
  cortada de un equipo desenchufado.
- El paso aceptaba casos ya cerrados (auditor de frontera). Decidido: un caso
  cerrado no pasa, y su propuesta se queda con el motivo escrito.
- Las fallas pendientes se vuelven a medir, en una fase propia y con tope.

COMO SE PRUEBA
--------------
La respuesta del motor se arma con la FORMA REAL de
'nucleo/herramientas/diagnostico_servicio.diagnosticar': las mismas claves, y
la señal clasificada con su regla (fuera de -25 a -8 es 'debil'). La medicion
entra por el camino real --'medicion_de_fallas'-- y el paso decide con lo que
quedo guardado. Sobre el EFECTO: el estado de la propuesta, la pieza escrita y
las llamadas al motor. Nunca sobre los contadores del informe.
================================================================================
"""

import json
import logging
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from operaciones import diagnostico_de_ticket as dxt
from operaciones import medicion_de_fallas as mdf
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

TOPE = 3


# =============================================================================
#  LA FORMA REAL DE LA RESPUESTA DEL MOTOR
# =============================================================================

def _respuesta(estado, *, causa="", dbm=None):
    """
    Lo que devuelve 'diagnosticar' cuando pudo medir, clave por clave. La
    señal se clasifica con la regla del motor ('_clasificar_senal'): fuera de
    -25 a -8 es 'debil'. La causa solo viaja si esta caido.
    """
    if dbm is None:
        senal = "sin_dato"
    else:
        senal = "buena" if -25.0 <= dbm <= -8.0 else "debil"
    return {
        "id_servicio": "3614",
        "equipo_registrado": True,
        "estado": estado,
        "causa_caida": causa if estado == "caido" else "",
        "senal_dbm": dbm,
        "senal": senal,
        "estado_config": "match",
        "ultima_caida": "2026-10-16 08:12:00",
        "ultima_conexion": "2026-10-16 08:40:00",
        "motivo": "",
    }


def _sin_resolver(motivo):
    """Lo que devuelve 'diagnosticar' cuando no pudo medir ('_sin_resolver')."""
    return {"id_servicio": "3614", "equipo_registrado": False,
            "estado": "desconocido", "causa_caida": "", "senal_dbm": None,
            "senal": "sin_dato", "estado_config": "", "motivo": motivo}


# =============================================================================
#  LOS DATOS
# =============================================================================

def _caso(org, **campos):
    """Un caso abierto, con una copia fresca y en curso de WispHub."""
    from cases.models import Case

    datos = dict(
        org=org, name="Sin servicio", status="New", priority="Normal",
        is_active=True, provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=timezone.now())
    datos.update(campos)
    return Case.objects.create(**datos)


def _lectura(grupo, *, confianza_del_grupo="alta", **extra):
    pieza = {"fuente": dxt.FUENTE, "id": "x",
             "dato": "lectura del reclamo: no tiene servicio",
             "observado_en": timezone.now().isoformat(),
             "grupo": grupo, "labor": "", "labor_verificada": False,
             "labor_porque": "", "confianza": "media",
             "confianza_del_grupo": confianza_del_grupo}
    pieza.update(extra)
    return pieza


def _pendiente(org, *, hace_min=10, caso=None, grupo=pad.FALLA_DE_SERVICIO,
               medida=None, **lectura):
    """
    Una lectura pendiente. Con 'medida', ademas una medicion guardada por el
    camino real ('medicion_de_fallas.escribir').
    """
    caso = caso or _caso(org)
    p = P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.PROPUESTA,
        accion_propuesta="Revisar el servicio", motivo="x", prioridad=30,
        evidencia=[_lectura(grupo, **lectura)])
    P.objects.filter(pk=p.pk).update(
        created_at=timezone.now() - timedelta(minutes=hace_min))
    p.refresh_from_db()
    if medida is not None:
        mdf.escribir(p, mdf.de_la_respuesta(medida), timezone.now())
        p.refresh_from_db()
    return p


def _estado(p):
    return P.objects.get(pk=p.pk).estado


def _revision(p):
    """El motivo escrito por el paso, o None."""
    return pad.ultima_revision(P.objects.get(pk=p.pk))


def _medicion(p):
    return pad.ultima_medicion(P.objects.get(pk=p.pk))


def _vuelta(org):
    return sup._pasar_a_despacho_los_que_las_reglas_habiliten(org, timezone.now())


class _Motor:
    """El motor, sustituido: contesta lo que se le diga y anota a quien."""

    def __init__(self, respuesta=None):
        self.respuesta = respuesta or _respuesta("en_linea", dbm=-27.0)
        self.llamadas = []

    def __call__(self, org, id_servicio):
        self.llamadas.append(id_servicio)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


def _medir(org, motor, tope=TOPE):
    return mdf.medir_fallas_pendientes(
        org, medir=motor, presupuesto_=sup.presupuesto(tope=tope, segundos=600))


@pytest.fixture
def puertas_abiertas(monkeypatch):
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    monkeypatch.setattr(sup, "TOPE_PASO_A_DESPACHO", TOPE)


# =============================================================================
#  (a) UN CASO CERRADO NO PASA, Y SE QUEDA CON SU MOTIVO
# =============================================================================

_HACE_73_H = timedelta(hours=sup.HORAS_LECTURA_FRESCA + 1)


@pytest.mark.parametrize(
    "campos, dice",
    [
        pytest.param(dict(status="Closed"), "cerrado en Dexter", id="closed_en_dexter"),
        pytest.param(dict(resolved_at=timezone.now()), "cerrado en Dexter",
                     id="resuelto_en_dexter"),
        pytest.param(dict(external_status="Cerrado"), "cerrado en WispHub",
                     id="cerrado_en_wisphub"),
        pytest.param(dict(external_status=""), "no figura en curso",
                     id="sin_estado_en_wisphub"),
        pytest.param(dict(external_fetched_at=None), "no consta cuando",
                     id="copia_sin_fecha"),
        pytest.param("vieja", f"mas de {sup.HORAS_LECTURA_FRESCA} h",
                     id="copia_de_73_horas"),
        pytest.param(dict(external_fetch_error="timeout"), "fallo",
                     id="copia_con_error"),
        pytest.param(dict(is_active=False), "inactivo", id="caso_inactivo"),
        pytest.param(dict(status="Rejected"), "no esta abierto en Dexter",
                     id="rechazado_en_dexter"),
        pytest.param(dict(status="Duplicate"), "no esta abierto en Dexter",
                     id="duplicado_en_dexter"),
        pytest.param("fusionado", "fusionado", id="caso_fusionado"),
    ],
)
def test_a_un_caso_que_no_esta_abierto_no_pasa_y_dice_por_que(
        org_a, puertas_abiertas, campos, dice):
    if campos == "vieja":
        campos = dict(external_fetched_at=timezone.now() - _HACE_73_H)
    if campos == "fusionado":
        campos = dict(merged_into=_caso(org_a))
    cerrado = _pendiente(org_a, hace_min=20, caso=_caso(org_a, **campos),
                         medida=_respuesta("en_linea", dbm=-27.0))
    control = _pendiente(org_a, hace_min=10,
                         medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert _estado(control) == P.ACEPTADA, (
        "sin el control, una vuelta vacia tambien seria verde")
    assert _estado(cerrado) == P.PROPUESTA, "un caso que no esta abierto paso"
    pieza = _revision(cerrado)
    assert pieza is not None and dice in pieza["porque"], pieza


def test_a2_con_la_copia_de_71_horas_todavia_pasa(org_a, puertas_abiertas):
    """El borde del limite, del otro lado: falla cerrado, no de mas."""
    p = _pendiente(
        org_a,
        caso=_caso(org_a, external_fetched_at=timezone.now()
                   - timedelta(hours=sup.HORAS_LECTURA_FRESCA - 1)),
        medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA


# =============================================================================
#  (b) LA MEDICION DECIDE: SOLO PASA LA SEÑAL FUERA DE RANGO EN LINEA
# =============================================================================

@pytest.mark.parametrize("dbm", [-26.0, -7.0], ids=["-26_dbm", "-7_dbm"])
def test_b_en_linea_con_la_senal_fuera_de_rango_pasa(org_a, puertas_abiertas, dbm):
    p = _pendiente(org_a, medida=_respuesta("en_linea", dbm=dbm))

    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA
    fila = P.objects.get(pk=p.pk)
    assert f"{dbm} dBm" in (fila.resultado or ""), (
        "el nivel medido tiene que quedar en la aceptacion: es contra lo que "
        "se decidio")


@pytest.mark.parametrize(
    "respuesta, dice",
    [
        pytest.param(_respuesta("en_linea", dbm=-21.0), "se contradicen",
                     id="en_linea_en_rango"),
        pytest.param(_respuesta("caido", causa="sin_energia"), "si tiene luz",
                     id="dying_gasp"),
    ],
)
def test_b2_la_falla_que_la_medicion_contradice_se_queda_y_dice_que_hacer(
        org_a, puertas_abiertas, respuesta, dice):
    """Las dos unicas salidas que frenan desde la Fase 4 (16/10/2026)."""
    queda = _pendiente(org_a, hace_min=20, medida=respuesta)
    control = _pendiente(org_a, hace_min=10,
                         medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert _estado(control) == P.ACEPTADA
    assert _estado(queda) == P.PROPUESTA
    pieza = _revision(queda)
    assert pieza is not None and dice in pieza["porque"], pieza


@pytest.mark.parametrize(
    "respuesta, dice",
    [
        pytest.param(_respuesta("en_linea"), "no trajo el nivel",
                     id="en_linea_sin_senal"),
        pytest.param(_respuesta("caido", causa="fibra"), "desenchufado",
                     id="los_lof"),
        pytest.param(_respuesta("caido", causa="otra"), "no es falta de energia",
                     id="caido_otra_causa"),
        pytest.param(_respuesta("caido"), "respuesta incompleta",
                     id="caido_sin_datos"),
    ],
)
def test_b2b_toda_otra_falla_PASA_y_la_aceptacion_dice_por_que(
        org_a, puertas_abiertas, respuesta, dice):
    """
    Decidido el 16/10/2026 con los 64 pendientes a la vista: nada contradice
    el reclamo, asi que pasa, y el despachador confirma con el cliente.
    """
    control = _pendiente(org_a, hace_min=20,
                         medida=_respuesta("en_linea", dbm=-21.0))
    pasa = _pendiente(org_a, hace_min=10, medida=respuesta)

    _vuelta(org_a)

    assert _estado(control) == P.PROPUESTA, "el equipo en rango sigue quedandose"
    assert _estado(pasa) == P.ACEPTADA
    assert dice in (P.objects.get(pk=pasa.pk).resultado or "")
    assert _revision(pasa) is None


def test_b3_una_lectura_vieja_verificada_y_sin_medicion_no_pasa(
        org_a, puertas_abiertas):
    """
    La regla vieja dejaba pasar una labor verificada. Ya no decide la labor:
    sin la medicion de 'diagnosticar', la falla espera a medirse.
    """
    p = _pendiente(org_a, labor="correctivo", labor_verificada=True,
                   labor_porque="el equipo esta caido por perdida de señal")

    _vuelta(org_a)

    assert _estado(p) == P.PROPUESTA
    assert "falta la medicion" in _revision(p)["porque"]


def test_b4_la_lectura_vieja_con_equipo_sano_no_tapa_lo_que_se_midio(
        org_a, puertas_abiertas):
    """
    Las lecturas viejas traen la frase de equipo sano. El bloque que la
    reemplazaba por "sin interpretar" taparia cada motivo medido.
    """
    p = _pendiente(org_a, labor_porque="el equipo esta en linea y sano, asi "
                   "que esto NO es una falla de red",
                   medida=_respuesta("en_linea", dbm=-21.0))

    _vuelta(org_a)

    assert "se contradicen" in _revision(p)["porque"]


# =============================================================================
#  (c) LA RE-MEDICION: FASE PROPIA, CON TOPE, SIN EL MODELO
# =============================================================================

def test_c_una_falla_pendiente_sin_medir_se_mide_y_queda_escrita(org_a):
    caso = _caso(org_a, external_service_id="8811")
    p = _pendiente(org_a, caso=caso)
    motor = _Motor(_respuesta("caido", causa="fibra"))

    _medir(org_a, motor)

    assert motor.llamadas == ["8811"], "se midio otro servicio, o ninguno"
    m = _medicion(p)
    assert m["medido_con"] == pad.MEDIDO_CON
    assert (m["estado"], m["causa_caida"]) == ("caido", "fibra")
    assert m["dato"].startswith("medicion del equipo")


def test_c2_como_mucho_el_tope_por_vuelta_la_mas_nueva_primero(org_a):
    viejas = [_pendiente(org_a, hace_min=100 - i) for i in range(TOPE + 2)]
    motor = _Motor()

    _medir(org_a, motor)

    assert len(motor.llamadas) == TOPE, "la re-medicion no respeto el tope"
    medidas = [p for p in viejas if _medicion(p) is not None]
    assert medidas == viejas[-TOPE:], "no se midio primero la mas nueva"


def test_c3_lo_que_no_hay_que_medir_no_se_mide(org_a):
    concluyente = _pendiente(org_a, medida=_respuesta("en_linea", dbm=-21.0))
    reciente = _pendiente(org_a, medida=_sin_resolver("sin respuesta"))
    cerrado = _pendiente(org_a, caso=_caso(org_a, status="Closed"))
    otro_grupo = _pendiente(org_a, grupo=pad.TRABAJO_PEDIDO)
    motor = _Motor()

    _medir(org_a, motor)

    assert motor.llamadas == [], motor.llamadas
    assert _medicion(cerrado) is None and _medicion(otro_grupo) is None
    assert _medicion(concluyente)["estado"] == "en_linea"
    assert _medicion(reciente)["estado"] == "desconocido"


def test_c4_una_que_no_se_pudo_medir_se_reintenta_al_dia(org_a):
    p = _pendiente(org_a, medida=_sin_resolver("sin respuesta"))
    fila = P.objects.get(pk=p.pk)
    for pieza in fila.evidencia:
        if pieza.get("fuente") == pad.FUENTE_MEDICION:
            pieza["observado_en"] = (timezone.now() - timedelta(
                hours=mdf.HORAS_PARA_REINTENTAR + 1)).isoformat()
    fila.save(update_fields=["evidencia"])
    motor = _Motor()

    _medir(org_a, motor)

    assert len(motor.llamadas) == 1
    assert _medicion(p)["estado"] == "en_linea"


def test_c5_sin_id_de_servicio_se_anota_sin_llamar_al_motor(org_a):
    p = _pendiente(org_a, caso=_caso(org_a, external_service_id=""))
    motor = _Motor()

    _medir(org_a, motor)

    assert motor.llamadas == []
    assert "id de servicio" in _medicion(p)["motivo"]


def test_c6_medir_no_llama_al_modelo(org_a, monkeypatch):
    from operaciones import cerebro
    from operaciones.models import RazonamientoSupervisor

    llamadas = []
    monkeypatch.setattr(cerebro, "concluir",
                        lambda *a, **k: llamadas.append("concluir"))
    monkeypatch.setattr(cerebro, "razonar",
                        lambda *a, **k: llamadas.append("razonar"),
                        raising=False)
    antes = RazonamientoSupervisor.objects.count()
    p = _pendiente(org_a)

    _medir(org_a, _Motor())

    assert _medicion(p) is not None, "sin la medicion, la prueba no dice nada"
    assert llamadas == [], llamadas
    assert RazonamientoSupervisor.objects.count() == antes


def test_c7_el_presupuesto_nace_con_la_hora_de_la_fase(org_a, monkeypatch):
    """
    Cuando la fase corre, la lectura ya tardo hasta veinte minutos. Un
    presupuesto creado con la hora del ciclo naceria vencido y no mediria
    nada, sin un error.
    """
    p = _pendiente(org_a)
    motor = _Motor()
    monkeypatch.setattr(mdf, "_medir_con_el_motor", motor)

    sup._medir_fallas_pendientes(org_a, desatendido=True)

    assert len(motor.llamadas) == 1 and _medicion(p) is not None


def test_c8_lo_que_se_guarda_es_vocabulario_cerrado(org_a):
    """
    De la respuesta se guardan claves fijas: ni el serial, ni nada que el paso
    no use. Y un error del motor --cuyo detalle es 'str(e)' y trae la URL con
    el identificador del equipo-- no se guarda: desde el 16/10/2026 no es una
    medicion.
    """
    sucia = dict(_respuesta("caido", causa="fibra"))
    sucia["sn_onu"] = "ZTEG12345678"
    sucia["estado"] = "caido"
    con_error = {"error": "MOTOR_NO_DISPONIBLE",
                 "detalle": "http://motor:5000/x?sn=ZTEG12345678"}
    uno = _pendiente(org_a, hace_min=20)
    dos = _pendiente(org_a, hace_min=10)

    _medir(org_a, _Motor(sucia))
    P.objects.filter(pk=uno.pk).update(evidencia=[_lectura(pad.FALLA_DE_SERVICIO)])
    _medir(org_a, _Motor(con_error))

    for p in (uno, dos):
        texto = json.dumps(P.objects.get(pk=p.pk).evidencia, ensure_ascii=False)
        assert "ZTEG12345678" not in texto and "motor:5000" not in texto, texto
    assert _medicion(dos)["causa_caida"] == "fibra"
    assert _medicion(uno) is None, "un error del motor no es una medicion"


# =============================================================================
#  (d) LA FASE DE PASO NO LLAMA AL MOTOR, Y LA MEDICION CORRE EN EL CICLO
# =============================================================================

def test_d_el_paso_no_llama_a_ninguna_herramienta_del_motor(
        org_a, puertas_abiertas, monkeypatch):
    from campo.services import despacho
    from operaciones import chat_herramientas

    def _prohibido(*a, **k):
        raise AssertionError("la fase de paso llamo al motor")

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio", _prohibido)
    monkeypatch.setattr(despacho, "contexto_del_caso", _prohibido)
    monkeypatch.setattr(mdf, "_medir_con_el_motor", _prohibido)
    p = _pendiente(org_a, medida=_respuesta("en_linea", dbm=-27.0))

    informe = _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA
    assert informe["despacho"]["fallaron"] == 0


def test_d2_en_el_ciclo_la_falla_se_mide_y_pasa_en_la_misma_vuelta(
        org_a, puertas_abiertas, monkeypatch):
    """
    La medicion es una FASE del ciclo, entre la lectura y el paso. Aunque la
    lectura no tenga nada nuevo que leer --cuando sale temprano--, la falla
    vieja se mide y pasa en la misma vuelta.
    """
    monkeypatch.setattr(sup, "_correr_ciclo", lambda org, ahora: {})
    monkeypatch.setattr(sup, "_atender_desincronizados",
                        lambda org, ahora, desatendido=False: {})
    monkeypatch.setattr(sup, "_leer_tickets_abiertos",
                        lambda org, ahora, desatendido=False: {"tickets": {}})
    motor = _Motor(_respuesta("en_linea", dbm=-27.0))
    monkeypatch.setattr(mdf, "_medir_con_el_motor", motor)
    p = _pendiente(org_a)

    resumen = sup.correr_ciclo(org_a, desatendido=True)

    assert "fases_que_fallaron" not in resumen, resumen
    assert motor.llamadas == ["3614"]
    assert _estado(p) == P.ACEPTADA


def test_d3_en_sombra_el_log_dice_cuantas_pasarian_por_grupo(
        org_a, monkeypatch, caplog):
    """
    Decidido el 16/10: se enciende en sombra, con la tarea sin delegar. La
    linea del log tiene que separar las fallas de los trabajos pedidos, que
    con la tarea quitada tambien se frenan.
    """
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: False)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    falla = _pendiente(org_a, hace_min=20, medida=_respuesta("en_linea", dbm=-27.0))
    trabajo = _pendiente(org_a, hace_min=10, grupo=pad.TRABAJO_PEDIDO)

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        _vuelta(org_a)

    assert _estado(falla) == P.PROPUESTA and _estado(trabajo) == P.PROPUESTA
    linea = next((r.getMessage() for r in caplog.records
                  if "paso a Despacho" in r.getMessage()), "")
    sombra = linea.split("pasarian por grupo=")[-1]
    assert "'falla_de_servicio': 1" in sombra and "'trabajo_pedido': 1" in sombra, (
        linea)


# =============================================================================
#  LA PIEZA NUEVA NO SE CONFUNDE CON UNA LECTURA
# =============================================================================

def test_la_medicion_no_es_una_lectura_ni_una_hipotesis(org_a):
    """
    'ya_leidos' busca 'diagnostico_del_ticket' con 'icontains' en toda la
    evidencia, y la pantalla de Despacho muestra como hipotesis lo que empieza
    con "lectura del reclamo: ". Una medicion no es ninguna de las dos.
    """
    assert dxt.FUENTE not in pad.FUENTE_MEDICION
    p = P.objects.create(
        org=org_a, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(_caso(org_a).id), estado=P.PROPUESTA,
        accion_propuesta="x", motivo="x", prioridad=30,
        evidencia=[sup._observacion("caso", "x", "caso en el CRM",
                                    timezone.now())])
    mdf.escribir(p, mdf.de_la_respuesta(_respuesta("caido", causa="fibra")),
                 timezone.now())

    fila = P.objects.get(pk=p.pk)
    assert dxt.le_falta_lectura(fila)
    assert not P.objects.filter(pk=p.pk, evidencia__icontains=dxt.FUENTE).exists()
    assert not pad.ultima_medicion(fila)["dato"].startswith("lectura del reclamo")


# =============================================================================
#  LO QUE ENCONTRO EL REVISOR DE PII EL 16/10
# =============================================================================

CLIENTE = "Zoraida Clientela"
SERIAL = "ZTEG12345678"
_URL = f"http://motor:5000/x?sn={SERIAL}"
_CLAVES_DE_LA_MEDICION = {"fuente", "id", "dato", "observado_en", "medido_con",
                          "estado", "causa_caida", "senal", "senal_dbm",
                          "motivo"}


def test_e_el_pase_no_copia_al_feed_el_texto_del_modelo(org_a, puertas_abiertas):
    """
    'accion_propuesta' la redacta el modelo leyendo el ticket, y 'Activity' la
    ve cualquier usuario de la empresa. El pase automatico figura con un
    nombre fijo.
    """
    from common.models import Activity

    p = _pendiente(org_a, medida=_respuesta("en_linea", dbm=-27.0))
    P.objects.filter(pk=p.pk).update(
        accion_propuesta=f"Llamar a {CLIENTE} al 3113683499")

    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA
    fila = Activity.objects.get(entity_id=p.pk, metadata__tarea=pad.TAREA)
    assert fila.entity_name == pad.NOMBRE_DEL_PASE
    assert CLIENTE not in f"{fila.entity_name} {fila.description}"


def test_e2_la_pieza_lleva_solo_sus_claves(org_a):
    sucia = dict(_respuesta("caido", causa="fibra"))
    sucia["sn_onu"] = SERIAL
    p = _pendiente(org_a)

    _medir(org_a, _Motor(sucia))

    assert set(_medicion(p)) == _CLAVES_DE_LA_MEDICION


def test_e3_un_motivo_o_un_error_con_forma_rara_no_se_guarda_tal_cual(org_a):
    """
    Hoy el motor manda frases fijas. Si un dia mandara 'str(e)', la URL con el
    serial no puede terminar en la propuesta. Y un error, desde el 16/10/2026,
    no se guarda en absoluto.
    """
    con_url = _pendiente(org_a, hace_min=30)
    normal = _pendiente(org_a, hace_min=20)

    #  Se mide primero la mas nueva: una por vuelta, en ese orden.
    _medir(org_a, _Motor(_sin_resolver("el proveedor optico no respondio")), tope=1)
    _medir(org_a, _Motor(_sin_resolver(f"fallo: {_URL}")), tope=1)
    #  Un error no deja pieza: la que lo recibe sigue primera en la cola.
    con_error = _pendiente(org_a, hace_min=10)
    errores = [_medir(org_a, _Motor({"error": _URL, "detalle": _URL}), tope=1),
               _medir(org_a, _Motor(RuntimeError(_URL)), tope=1)]

    for p in (con_url, normal, con_error):
        texto = json.dumps(P.objects.get(pk=p.pk).evidencia, ensure_ascii=False)
        assert SERIAL not in texto and "motor:5000" not in texto, texto
    assert _medicion(normal)["motivo"] == "el proveedor optico no respondio", (
        "un motivo fijo del motor tiene que pasar tal cual")
    assert _medicion(con_url)["motivo"] == mdf._MOTIVO_GENERICO
    assert _medicion(con_error) is None
    assert [e["errores"] for e in errores] == [1, 1]


def test_e4_el_motivo_de_un_caso_cerrado_no_lleva_datos_del_cliente(
        org_a, puertas_abiertas, caplog):
    """Ni en la propuesta, ni en la linea de log."""
    caso = _caso(org_a, status="Closed", name=f"Sin internet, {CLIENTE}",
                 external_client_name=CLIENTE,
                 description="Tel 3113683499, la casa azul")
    p = _pendiente(org_a, caso=caso, medida=_respuesta("en_linea", dbm=-27.0))

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        _vuelta(org_a)

    pieza = json.dumps(_revision(p), ensure_ascii=False).lower()
    linea = " ".join(r.getMessage() for r in caplog.records).lower()
    for dato in (CLIENTE, "zoraida", "3113683499", "casa azul"):
        assert dato.lower() not in pieza, dato
        assert dato.lower() not in linea, dato


def test_e5_la_clave_del_log_no_abre_una_por_cada_nivel(
        org_a, puertas_abiertas, caplog):
    """'claves y conteos, nunca un caso': el nivel queda en la propuesta."""
    uno = _pendiente(org_a, hace_min=20, medida=_respuesta("en_linea", dbm=-21.0))
    dos = _pendiente(org_a, hace_min=10, medida=_respuesta("en_linea", dbm=-19.5))

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        _vuelta(org_a)

    assert "-21.0 dBm" in _revision(uno)["porque"]
    assert "-19.5 dBm" in _revision(dos)["porque"]
    linea = next(r.getMessage() for r in caplog.records
                 if "paso a Despacho" in r.getMessage())
    motivos = linea.split("por que se quedaron=")[1].split(" · ")[0]
    assert "dBm" not in motivos, motivos
    assert "': 2" in motivos, motivos


# =============================================================================
#  LO QUE ENCONTRO EL AUDITOR DE FRONTERA EL 16/10
# =============================================================================

def test_f_pasado_el_tope_un_caso_cerrado_no_espera_se_queda_con_su_motivo(
        org_a, puertas_abiertas):
    """
    La rama del tope solo decide, y tambien mira el caso: un caso cerrado no
    "espera la vuelta que viene", se queda con su motivo escrito.
    """
    abiertas = [_pendiente(org_a, hace_min=100 - i,
                           medida=_respuesta("en_linea", dbm=-27.0))
                for i in range(TOPE)]
    cerrado = _pendiente(org_a, hace_min=1, caso=_caso(org_a, status="Closed"),
                         medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert all(_estado(p) == P.ACEPTADA for p in abiertas), (
        "sin el tope lleno, la prueba no mira la rama del tope")
    assert _estado(cerrado) == P.PROPUESTA
    pieza = _revision(cerrado)
    assert pieza is not None and "cerrado en Dexter" in pieza["porque"], pieza


def test_f2_debil_sin_el_numero_pasa_sin_afirmar_confirmada(org_a, puertas_abiertas):
    sin_numero = dict(_respuesta("en_linea", dbm=-27.0))
    sin_numero["senal_dbm"] = None
    p = _pendiente(org_a, medida=sin_numero)

    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA
    resultado = P.objects.get(pk=p.pk).resultado or ""
    assert "no trajo el nivel" in resultado and "CONFIRMADA" not in resultado

def test_f3_un_nan_no_vuelve_a_pedir_la_medicion_cada_vuelta(org_a):
    """El motor clasifica un NaN como 'debil'. Se guarda sin numero, y no pasa."""
    con_nan = dict(_respuesta("en_linea", dbm=-27.0))
    con_nan["senal_dbm"] = float("nan")
    p = _pendiente(org_a)
    motor = _Motor(con_nan)

    _medir(org_a, motor)
    _medir(org_a, motor)

    assert len(motor.llamadas) == 1, "se volvio a pedir lo que ya estaba medido"
    m = _medicion(p)
    assert m["senal_dbm"] is None and m["senal"] == "sin_dato"
    assert "fuera del rango" not in m["dato"], (
        "la pieza afirma 'fuera del rango' sin el numero que lo sostenga")


def test_f4_la_frase_mas_comun_del_motor_se_guarda_tal_cual(org_a, puertas_abiertas):
    frase = ("el equipo de este servicio no esta registrado en SmartOLT, asi "
             "que no se puede diagnosticar su estado optico")
    p = _pendiente(org_a, medida=_sin_resolver(frase))

    _vuelta(org_a)

    assert _medicion(p)["motivo"] == frase
    #  La primera vuelta sin medir espera (17/10/2026): la frase llega a
    #  quien lee por que se queda.
    assert "no esta registrado en SmartOLT" in _revision(p)["porque"]

# =============================================================================
#  LO QUE ENCONTRO EL AUDITOR INDEPENDIENTE EL 16/10
# =============================================================================

def _envejecer_medicion(p, horas):
    fila = P.objects.get(pk=p.pk)
    for pieza in fila.evidencia:
        if pieza.get("fuente") == pad.FUENTE_MEDICION:
            pieza["observado_en"] = (timezone.now() - timedelta(hours=horas)).isoformat()
    fila.save(update_fields=["evidencia"])


def test_g_caido_sin_causa_ni_senal_pasa_y_no_se_vuelve_a_medir(
        org_a, puertas_abiertas):
    """
    Un 200 del proveedor sin datos sale del motor como 'caido' sin causa ni
    señal. No contradice el reclamo: pasa (Fase 4), y una aceptada no se mide
    de nuevo.
    """
    p = _pendiente(org_a, medida=_respuesta("caido"))

    _vuelta(org_a)
    assert _estado(p) == P.ACEPTADA
    assert "respuesta incompleta" in (P.objects.get(pk=p.pk).resultado or "")

    _envejecer_medicion(p, mdf.HORAS_PARA_REINTENTAR + 1)
    motor = _Motor()
    _medir(org_a, motor)

    assert motor.llamadas == [], "una aceptada no se vuelve a medir"

def test_g2_una_concluyente_no_se_vuelve_a_medir_aunque_sea_vieja(org_a):
    p = _pendiente(org_a, medida=_respuesta("en_linea", dbm=-21.0))
    _envejecer_medicion(p, mdf.HORAS_PARA_REINTENTAR + 1)
    motor = _Motor()

    _medir(org_a, motor)

    assert motor.llamadas == [], "se volvio a medir una medicion concluyente"


def test_g3_primero_las_que_nunca_se_midieron_despues_los_reintentos(org_a):
    nunca = _pendiente(org_a, hace_min=100,
                       caso=_caso(org_a, external_service_id="1111"))
    reintento = _pendiente(org_a, hace_min=10,
                           caso=_caso(org_a, external_service_id="2222"),
                           medida=_sin_resolver("sin respuesta"))
    _envejecer_medicion(reintento, mdf.HORAS_PARA_REINTENTAR + 1)
    motor = _Motor()

    _medir(org_a, motor, tope=1)

    assert motor.llamadas == ["1111"], motor.llamadas
    assert _medicion(nunca)["estado"] == "en_linea"


@pytest.mark.parametrize("estado", ["Assigned", "Pending"])
def test_g4_un_caso_asignado_o_pendiente_si_pasa(org_a, puertas_abiertas, estado):
    p = _pendiente(org_a, caso=_caso(org_a, status=estado),
                   medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA


def test_g5_desatendida_la_fase_mide_con_el_tope_largo(org_a, monkeypatch):
    """
    El reloj y el boton corren desatendidos: el tope es el de 15, no el de 3.
    Con cuatro candidatas, se miden las cuatro.
    """
    from operaciones import diagnostico_optico as optico

    assert optico.TOPE_DIAGNOSTICOS_POR_CICLO < 4 <= optico.TOPE_DIAGNOSTICOS_DESATENDIDO
    for i in range(4):
        _pendiente(org_a, hace_min=10 + i)
    motor = _Motor()
    monkeypatch.setattr(mdf, "_medir_con_el_motor", motor)

    sup._medir_fallas_pendientes(org_a, desatendido=True)

    assert len(motor.llamadas) == 4, motor.llamadas


def test_g6_no_se_escribe_en_una_propuesta_que_ya_se_decidio(org_a):
    p = _pendiente(org_a)
    P.objects.filter(pk=p.pk).update(estado=P.ACEPTADA)

    escribio = mdf.escribir(p, mdf.de_la_respuesta(_respuesta("en_linea", dbm=-27.0)),
                            timezone.now())

    assert escribio is False
    assert _medicion(p) is None


def test_g7_el_techo_se_lee_una_vez_por_vuelta(org_a, monkeypatch):
    """Cada lectura del techo es una llamada al motor."""
    from operaciones import autonomia, tareas_delegadas

    lecturas = []

    def _techo(o, nivel):
        lecturas.append(nivel)
        return {"puede": True, "motivo": ""}

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede", _techo)
    for i in range(3):
        _pendiente(org_a, hace_min=10 + i, medida=_respuesta("en_linea", dbm=-27.0))

    _vuelta(org_a)

    assert len(lecturas) == 1, lecturas


def test_g8_la_pieza_dice_cuando_se_midio(org_a):
    import re

    p = _pendiente(org_a, medida=_respuesta("en_linea", dbm=-21.0))

    assert re.search(r"\(\d\d/\d\d \d\d:\d\d \S+\)", _medicion(p)["dato"]), (
        _medicion(p)["dato"])


def test_g9_un_serial_suelto_no_entra_al_motivo(org_a):
    p = _pendiente(org_a)

    _medir(org_a, _Motor(_sin_resolver("no se encontro la ONU ZTEGC1234567 en SmartOLT")))

    assert "ZTEGC1234567" not in json.dumps(_medicion(p), ensure_ascii=False)


# =============================================================================
#  LO QUE ENCONTRO EL AUDITOR DE FRONTERA EL 16/10/2026 (FASE 4)
# =============================================================================

def test_h_un_estado_que_no_se_entiende_no_pasa_y_se_vuelve_a_medir(
        org_a, puertas_abiertas):
    """
    Si el motor cambiara su vocabulario ("online" en vez de "en_linea"), o
    dejara de escribir el estado, cada falla pasaria como "no se pudo medir",
    con el equipo en rango inclusive. Un estado que no se entiende no decide
    nada, y se vuelve a medir.
    """
    raro = dict(_respuesta("en_linea", dbm=-21.0))
    raro["estado"] = "online"
    sin_estado = dict(_respuesta("en_linea", dbm=-21.0))
    del sin_estado["estado"]
    p = _pendiente(org_a, hace_min=20, medida=raro)
    q = _pendiente(org_a, hace_min=10, medida=sin_estado)

    _vuelta(org_a)

    for x in (p, q):
        assert _estado(x) == P.PROPUESTA, "paso con un estado que no se entiende"
        assert "no reconoce" in _revision(x)["porque"]
    _envejecer_medicion(p, mdf.HORAS_PARA_REINTENTAR + 1)
    motor = _Motor()
    _medir(org_a, motor)
    assert len(motor.llamadas) == 1, "un estado no reconocido no se volvio a medir"


def test_h2_un_error_del_motor_no_deja_medicion_y_la_falla_espera(
        org_a, puertas_abiertas):
    """
    Con el motor caido, "no se pudo medir" quedaba guardado y la falla pasaba
    en la vuelta siguiente sin volver a medirse, con el equipo en rango
    inclusive. Un error de infraestructura no es una medicion: no se escribe,
    y la falla espera a que se pueda medir.
    """
    p = _pendiente(org_a)
    caido = _Motor({"error": "MOTOR_NO_DISPONIBLE",
                    "detalle": "http://motor:5000/x"})

    informe = _medir(org_a, caido)
    assert informe["errores"] == 1 and _medicion(p) is None
    _vuelta(org_a)
    assert _estado(p) == P.PROPUESTA
    assert "falta la medicion" in _revision(p)["porque"]

    sano = _Motor(_respuesta("en_linea", dbm=-21.0))
    _medir(org_a, sano)
    _vuelta(org_a)

    assert sano.llamadas == ["3614"], "con el motor sano se tiene que medir"
    assert _estado(p) == P.PROPUESTA, "el equipo en rango paso tras el motor caido"
    assert "se contradicen" in _revision(p)["porque"]


def test_h3_un_error_guardado_por_la_fase_3_no_pasa_y_se_mide_ya(
        org_a, puertas_abiertas):
    """
    Hasta el 16/10 un error del motor se guardaba como "no se pudo medir", y
    esas piezas siguen en las propuestas vivas. Con la regla de la Fase 4
    pasarian sin que nadie haya medido nada: se tratan como falta de medicion,
    y se piden en la vuelta siguiente, no a las 24 horas.
    """
    p = _pendiente(org_a)
    mdf.escribir(p, {"medido_con": pad.MEDIDO_CON, "estado": "desconocido",
                     "causa_caida": "", "senal": "sin_dato", "senal_dbm": None,
                     "motivo": "el motor contesto MOTOR_NO_DISPONIBLE"},
                 timezone.now())

    _vuelta(org_a)
    assert _estado(p) == P.PROPUESTA, "paso con un error guardado como medicion"
    assert "falta la medicion" in _revision(p)["porque"]

    motor = _Motor(_respuesta("caido", causa="fibra"))
    _medir(org_a, motor)
    assert motor.llamadas == ["3614"], "un error guardado se vuelve a medir ya"
    _vuelta(org_a)
    assert _estado(p) == P.ACEPTADA


# =============================================================================
#  "NO SE PUDO MEDIR" TIENE QUE REPETIRSE EN DOS VUELTAS SEGUIDAS  --  17/10/2026
# =============================================================================
#  Con una sola vuelta, una caida de SmartOLT o de WispHub mandaba a Despacho
#  todas las fallas de esa vuelta, las del equipo sano incluidas (auditor
#  independiente, hallazgo 1 de la Fase 4). Lo decidio el usuario.

def _hasta_la_vuelta_siguiente(p):
    _envejecer_medicion(p, mdf.MINUTOS_PARA_REINTENTAR_SIN_MEDIR / 60 + 0.1)


def test_m1_la_primera_vez_espera_y_la_segunda_vuelta_seguida_pasa(
        org_a, puertas_abiertas):
    p = _pendiente(org_a)
    caido = _Motor(_sin_resolver("el proveedor optico no respondio"))

    _medir(org_a, caido)
    assert _medicion(p)["intentos_sin_medir"] == 1
    _vuelta(org_a)
    assert _estado(p) == P.PROPUESTA, "paso con una sola vuelta sin medir"
    assert "vuelve a intentar" in _revision(p)["porque"]

    _medir(org_a, caido)
    assert caido.llamadas == ["3614"], (
        "un segundo clic en Correr ciclo no es la vuelta siguiente")

    _hasta_la_vuelta_siguiente(p)
    _medir(org_a, caido)
    assert caido.llamadas == ["3614", "3614"], "no se reintento en la vuelta siguiente"
    assert _medicion(p)["intentos_sin_medir"] == 2
    _vuelta(org_a)
    assert _estado(p) == P.ACEPTADA
    assert "dos vueltas seguidas" in (P.objects.get(pk=p.pk).resultado or "")


def test_m2_si_en_la_segunda_vuelta_se_puede_medir_decide_la_medicion(
        org_a, puertas_abiertas):
    """El caso que motivo esto: el proveedor caido una vuelta y el equipo sano."""
    p = _pendiente(org_a)
    _medir(org_a, _Motor(_sin_resolver("el proveedor optico no respondio")))
    _hasta_la_vuelta_siguiente(p)

    _medir(org_a, _Motor(_respuesta("en_linea", dbm=-21.0)))
    _vuelta(org_a)

    assert _estado(p) == P.PROPUESTA, "el equipo sano paso a Despacho"
    assert "se contradicen" in _revision(p)["porque"]


def test_m3_la_cuenta_es_de_vueltas_SEGUIDAS(org_a):
    """Otro resultado en el medio empieza la cuenta de nuevo."""
    p = _pendiente(org_a)
    raro = dict(_respuesta("en_linea", dbm=-21.0))
    raro["estado"] = "online"

    for respuesta in (_sin_resolver("x"), raro, _sin_resolver("x")):
        mdf.escribir(p, mdf.de_la_respuesta(respuesta), timezone.now())

    assert _medicion(p)["intentos_sin_medir"] == 1
    mdf.escribir(p, mdf.de_la_respuesta(_sin_resolver("x")), timezone.now())
    assert _medicion(p)["intentos_sin_medir"] == 2
