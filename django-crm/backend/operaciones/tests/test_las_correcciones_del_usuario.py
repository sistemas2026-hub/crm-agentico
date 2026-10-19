# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CORRECCIONES DEL USUARIO AL DIAGNOSTICO  --  18/10/2026
================================================================================

LO QUE AFIRMA
-------------
Las reglas que salieron de los cuatro casos que el usuario corrigio
(SPEC/objetivos/correcciones-al-diagnostico.md), sobre el EFECTO: el estado
de la propuesta, la pieza escrita y lo que el ciclo cuenta.

  - Sin la tarea de las correcciones NADA cambia de lo que pasa: se cuentan en
    sombra, y en la propuesta queda escrito que pasaria y por que.
  - Con la tarea, pasan: la accion ya autorizada (correccion 1), la energia
    descartada por el ticket (caso 3), y la falla que la serie propia vio
    fuera de rango aunque la medicion de ahora no (correccion 2).
  - Lo que frena se vuelve a medir cada tres horas, y una re-medicion que no
    midio no borra la que si.
  - El doble diagnostico informa y no decide, y del ticket solo saca numeros.
  - La lectura guarda las claves nuevas y su version, y solo se releen las
    que la lectura nueva puede mover.
  - El trabajo pedido de un cliente que ya existe es correctivo; el de uno
    nuevo, instalacion, y su barrio no es el del cliente ficticio.

Cada prueba siembra lo que NO tiene que pasar junto a lo que si: un verde con
la cola vacia no diria nada.
================================================================================
"""
import logging
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone

from operaciones import armado_de_jornadas as adj
from operaciones import diagnostico_de_ticket as dxt
from operaciones import medicion_de_fallas as mdf
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

BARRIO = "SOLEDAD CENTRO"


# =============================================================================
#  LOS DATOS
# =============================================================================

def _respuesta(estado, *, causa="", dbm=None):
    """La forma real de 'diagnosticar_servicio' (ver la prueba de la Fase 3)."""
    if dbm is None:
        senal = "sin_dato"
    else:
        senal = "buena" if -25.0 <= dbm <= -8.0 else "debil"
    return {"id_servicio": "3614", "equipo_registrado": True, "estado": estado,
            "causa_caida": causa if estado == "caido" else "",
            "senal_dbm": dbm, "senal": senal, "estado_config": "match",
            "motivo": ""}


EN_RANGO = _respuesta("en_linea", dbm=-23.0)
DEBIL = _respuesta("en_linea", dbm=-28.5)
SIN_ENERGIA = _respuesta("caido", causa="sin_energia")
SIN_MEDIR = {"id_servicio": "3614", "equipo_registrado": False,
             "estado": "desconocido", "causa_caida": "", "senal_dbm": None,
             "senal": "sin_dato", "estado_config": "",
             "motivo": "el proveedor optico no respondio"}


def _caso(org, **campos):
    from cases.models import Case

    datos = dict(
        org=org, name="Sin servicio", status="New", priority="Normal",
        is_active=True, provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=timezone.now(),
        description="Internet intermitente",
        #  Una cuenta con nombre de la empresa: la unica cuya "accion
        #  autorizada" cuenta (test_b3).
        external_created_by_type=pad.AUTOR_DE_LA_EMPRESA)
    datos.update(campos)
    return Case.objects.create(**datos)


def _lectura(grupo, **extra):
    pieza = {"fuente": dxt.FUENTE, "id": "x",
             "dato": "lectura del reclamo: intermitencia",
             "observado_en": timezone.now().isoformat(),
             "grupo": grupo, "labor": "", "labor_verificada": False,
             "labor_porque": "", "confianza": "media",
             "confianza_del_grupo": "alta"}
    pieza.update(extra)
    return pieza


def _pendiente(org, *, caso=None, grupo=pad.FALLA_DE_SERVICIO, medida=None,
               hace_horas=0, **lectura):
    """Una lectura pendiente; con 'medida', medida por el camino real hace
    'hace_horas'."""
    caso = caso or _caso(org)
    p = P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.PROPUESTA,
        accion_propuesta="Revisar el servicio", motivo="x", prioridad=30,
        evidencia=[_lectura(grupo, **lectura)])
    if medida is not None:
        cuando = timezone.now() - timedelta(hours=hace_horas)
        assert mdf.escribir(p, mdf.de_la_respuesta(medida), cuando)
        p.refresh_from_db()
    return p


def _medicion(estado="en_linea", senal="buena", dbm=-23.0, causa="",
              historial=()):
    return {"medido_con": pad.MEDIDO_CON, "estado": estado, "senal": senal,
            "senal_dbm": dbm, "causa_caida": causa, "motivo": "",
            "observado_en": timezone.now().isoformat(),
            "historial": list(historial)}


def _estado(p):
    return P.objects.get(pk=p.pk).estado


def _revision(p):
    return pad.ultima_revision(P.objects.get(pk=p.pk))


def _vuelta(org):
    return sup._pasar_a_despacho_los_que_las_reglas_habiliten(
        org, timezone.now())["despacho"]


def _puertas(monkeypatch, *, correcciones):
    """El paso delegado y la empresa autorizada; las correcciones, segun se
    diga. Una excepcion es "no se pudo comprobar"."""
    from operaciones import autonomia

    def delegada(org, clave):
        if clave == pad.TAREA_CORRECCIONES:
            if isinstance(correcciones, Exception):
                raise correcciones
            return correcciones
        return True

    monkeypatch.setattr(td, "esta_delegada", delegada)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})


# =============================================================================
#  A · EN EL CICLO: SOMBRA SIN LA TAREA, EFECTO CON ELLA
# =============================================================================

def test_a_sin_la_tarea_no_pasa_nada_nuevo_y_queda_escrito_que_pasaria(
        org_a, monkeypatch, caplog):
    _puertas(monkeypatch, correcciones=False)
    autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    sin_energia = _pendiente(org_a, medida=SIN_ENERGIA, energia_descartada="si")
    en_rango = _pendiente(org_a, medida=EN_RANGO)
    debil = _pendiente(org_a, medida=DEBIL)

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        reporte = _vuelta(org_a)

    assert _estado(debil) == P.ACEPTADA, (
        "sin el control, una vuelta vacia tambien seria verde")
    for p in (autorizada, sin_energia, en_rango):
        assert _estado(p) == P.PROPUESTA
    assert reporte["correcciones"] is False
    assert reporte["pasaron_por_las_correcciones"] == {}
    assert reporte["pasarian_con_las_correcciones"] == {
        pad.REGLA_ACCION_AUTORIZADA: 1, pad.REGLA_ENERGIA_DESCARTADA: 1}
    assert (pad.SOMBRA_DE_LA_REGLA[pad.REGLA_ACCION_AUTORIZADA]
            in _revision(autorizada)["porque"])
    assert (pad.SOMBRA_DE_LA_REGLA[pad.REGLA_ENERGIA_DESCARTADA]
            in _revision(sin_energia)["porque"])
    assert "Con las correcciones" not in _revision(en_rango)["porque"]
    assert "correcciones=en sombra" in caplog.text
    assert "pasarian con las correcciones={'accion_autorizada': 1" in caplog.text


def test_b_con_la_tarea_pasan_y_se_cuenta_por_cual(org_a, monkeypatch):
    _puertas(monkeypatch, correcciones=True)
    autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    sin_energia = _pendiente(org_a, medida=SIN_ENERGIA, energia_descartada="si")
    en_rango = _pendiente(org_a, medida=EN_RANGO)
    no_autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="no")
    #  Lo que llegue guardado distinto de la clave exacta no cuenta, aunque se
    #  le parezca: 'cerebro' lo normaliza al leerlo, y esto no depende de que
    #  lo haya hecho.
    con_tilde = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="sí")
    con_luz = _pendiente(org_a, medida=SIN_ENERGIA, energia_descartada="no")

    reporte = _vuelta(org_a)

    assert _estado(autorizada) == P.ACEPTADA
    assert _estado(sin_energia) == P.ACEPTADA
    for p in (en_rango, no_autorizada, con_tilde, con_luz):
        assert _estado(p) == P.PROPUESTA, p.evidencia[0]
    assert reporte["correcciones"] is True
    assert reporte["pasaron_por_las_correcciones"] == {
        pad.REGLA_ACCION_AUTORIZADA: 1, pad.REGLA_ENERGIA_DESCARTADA: 1}
    assert reporte["pasarian_con_las_correcciones"] == {}
    aceptada = P.objects.get(pk=autorizada.pk)
    assert "correccion 1 del usuario" in (aceptada.resultado or "")


def test_b2_pasado_el_tope_las_correcciones_tambien_cuentan_para_esperar(
        org_a, monkeypatch):
    """La rama del tope decide con 'evaluar' y no escribe: la que pasaria con
    las correcciones encendidas "espera el tope", no se queda con una persona."""
    _puertas(monkeypatch, correcciones=True)
    monkeypatch.setattr(sup, "TOPE_PASO_A_DESPACHO", 0)
    autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    _pendiente(org_a, medida=EN_RANGO)

    reporte = _vuelta(org_a)

    assert _estado(autorizada) == P.PROPUESTA, "con tope cero no pasa nadie"
    assert (reporte["esperan_el_tope"], reporte["se_quedaron"]) == (1, 1)


def test_b3_la_autorizacion_tiene_que_venir_de_la_empresa(org_a, monkeypatch):
    """Auditor de frontera, 19/10/2026: un ticket que creo Dexter desde
    WhatsApp, o que llego por la cuenta compartida, puede traer "se autoriza"
    escrito por el propio cliente."""
    _puertas(monkeypatch, correcciones=True)
    de_la_empresa = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    por_dexter = _pendiente(
        org_a, caso=_caso(org_a, external_created_by_type="dexter"),
        medida=EN_RANGO, accion_autorizada="si")
    sin_autor = _pendiente(
        org_a, caso=_caso(org_a, external_created_by_type="externo_desconocido"),
        medida=EN_RANGO, accion_autorizada="si")

    _vuelta(org_a)

    assert _estado(de_la_empresa) == P.ACEPTADA
    assert _estado(por_dexter) == P.PROPUESTA
    assert _estado(sin_autor) == P.PROPUESTA


def test_c_si_no_se_puede_comprobar_la_tarea_deciden_las_reglas_de_siempre(
        org_a, monkeypatch):
    _puertas(monkeypatch, correcciones=RuntimeError("la base no contesto"))
    autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    debil = _pendiente(org_a, medida=DEBIL)

    reporte = _vuelta(org_a)

    assert _estado(debil) == P.ACEPTADA
    assert _estado(autorizada) == P.PROPUESTA
    assert reporte["correcciones"] is False


def test_d_la_sombra_es_solo_de_lo_que_frenan_las_reglas(org_a, monkeypatch):
    """Si lo frena una puerta de la empresa, las correcciones no cambian nada,
    y decir "pasaria con las correcciones" seria falso."""
    from operaciones import autonomia

    monkeypatch.setattr(td, "esta_delegada", lambda o, clave: False)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    debil = _pendiente(org_a, medida=DEBIL)
    _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")

    reporte = _vuelta(org_a)

    assert _estado(debil) == P.PROPUESTA
    assert "Con las correcciones" not in _revision(debil)["porque"]
    assert reporte["pasarian_con_las_correcciones"] == {
        pad.REGLA_ACCION_AUTORIZADA: 1}


# =============================================================================
#  B · LO QUE FRENA SE VUELVE A MEDIR, Y LA SERIE DE 24 HORAS
# =============================================================================

def test_e_lo_que_frena_se_remide_a_las_ocho_horas_y_va_despues_de_lo_nuevo(
        org_a):
    viejo_en_rango = _pendiente(org_a, medida=EN_RANGO, hace_horas=9)
    reciente = _pendiente(org_a, medida=EN_RANGO, hace_horas=7)
    viejo_sin_energia = _pendiente(org_a, medida=SIN_ENERGIA, hace_horas=9)
    viejo_debil = _pendiente(org_a, medida=DEBIL, hace_horas=30)
    sin_medir = _pendiente(org_a)

    cola = [p.pk for p, _ in mdf.candidatas(org_a, timezone.now())]

    assert cola[0] == sin_medir.pk, "lo que nunca se midio va primero"
    assert set(cola[1:]) == {viejo_en_rango.pk, viejo_sin_energia.pk}
    assert reciente.pk not in cola and viejo_debil.pk not in cola


def test_f_en_sombra_la_remedicion_va_al_historial_y_no_decide(org_a):
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=4)
    ahora = timezone.now()

    assert mdf.escribir(p, mdf.de_la_respuesta(DEBIL), ahora)
    p.refresh_from_db()

    m = pad.ultima_medicion(p)
    assert (m["senal"], m["senal_dbm"]) == ("buena", -23.0), (
        "en sombra la medicion que decide no cambia")
    assert [h["senal_dbm"] for h in m["historial"]] == [-28.5]
    assert m["remedida_en"] == ahora.isoformat()
    assert not pad.evaluar(p, ahora).pasa
    d = pad.evaluar(p, ahora, correcciones=True)
    assert d.pasa and d.regla == pad.REGLA_REMEDICION
    #  Y la proxima re-medicion se cuenta desde la ultima, no desde la pieza.
    assert p.pk not in [x.pk for x, _ in mdf.candidatas(org_a, ahora)]


def test_g_la_remedicion_no_reemplaza_y_quitar_la_tarea_vuelve_a_la_fase_4(
        org_a, monkeypatch):
    """Auditor de frontera, 19/10/2026: con la tarea, la re-medicion
    reemplazaba a la pieza, y quitada la tarea --entre la medicion y el paso,
    o cuando sea-- la pieza nueva seguia decidiendo por la Fase 4."""
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=9)
    llamadas = []
    monkeypatch.setattr(mdf, "_medir_con_el_motor",
                        lambda org, servicio: llamadas.append(servicio) or DEBIL)

    _puertas(monkeypatch, correcciones=True)
    sup._medir_fallas_pendientes(org_a)
    _puertas(monkeypatch, correcciones=False)
    reporte = _vuelta(org_a)

    assert llamadas == ["3614"]
    assert _estado(p) == P.PROPUESTA, "sin la tarea decide la medicion de siempre"
    m = pad.ultima_medicion(P.objects.get(pk=p.pk))
    assert (m["senal"], [h["senal_dbm"] for h in m["historial"]]) == (
        "buena", [-28.5])
    assert reporte["pasarian_con_las_correcciones"] == {pad.REGLA_REMEDICION: 1}


def test_e2_las_remediciones_tienen_tope_porque_no_son_polling(org_a):
    """Auditor independiente, 19/10/2026: el proveedor prohibe usar este
    endpoint en polling, y la primera version re-medía cada tres horas
    mientras la propuesta viviera. Cuenta tambien la que no pudo medir."""
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=30)
    ahora = timezone.now()
    for i, respuesta in enumerate((SIN_MEDIR, DEBIL)):
        cuando = ahora - timedelta(hours=20 - 9 * i)
        assert p.pk in [x.pk for x, _ in mdf.candidatas(org_a, cuando)]
        mdf.escribir(p, mdf.de_la_respuesta(respuesta), cuando)
        p.refresh_from_db()

    assert pad.ultima_medicion(p)["remedida_veces"] == mdf.REMEDICIONES_MAXIMAS
    assert p.pk not in [x.pk for x, _ in mdf.candidatas(
        org_a, ahora + timedelta(hours=12))], "pasado el tope no se pide mas"


def test_h_una_remedicion_que_no_midio_no_borra_lo_que_si(org_a):
    """Sin esto, dos vueltas con el proveedor caido convertian una falla con la
    señal en rango en "no se pudo medir en dos vueltas", que pasa."""
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=4)
    for minutos in (0, 40):
        assert mdf.escribir(p, mdf.de_la_respuesta(SIN_MEDIR),
                            timezone.now() + timedelta(minutes=minutos))
        p.refresh_from_db()

    m = pad.ultima_medicion(p)
    assert (m["estado"], m["senal"]) == ("en_linea", "buena")
    assert "intentos_sin_medir" not in m and not m.get("historial")
    assert not pad.evaluar(p, timezone.now(), correcciones=True).pasa


@pytest.mark.parametrize("horas, pasa", [(10, True), (25, False)])
def test_i_la_intermitencia_que_vio_la_serie_pasa_solo_con_la_tarea(
        org_a, horas, pasa):
    """El caso 2 del usuario: de noche -23 (en rango) y de dia -28.5 (fuera).
    Medida de noche, re-medida de dia fuera de rango, y la ultima re-medicion
    otra vez de noche, en rango."""
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=horas + 1)
    ahora = timezone.now()
    mdf.escribir(p, mdf.de_la_respuesta(DEBIL), ahora - timedelta(hours=horas))
    mdf.escribir(p, mdf.de_la_respuesta(EN_RANGO), ahora)
    p.refresh_from_db()

    assert not pad.evaluar(p, ahora).pasa, "sin la tarea decide la Fase 4"
    d = pad.evaluar(p, ahora, correcciones=True)
    assert d.pasa is pasa
    if pasa:
        assert d.regla == pad.REGLA_INTERMITENCIA
        assert "(-28.5 dBm)" in d.porque and "(-23.0 dBm)" in d.porque


def test_j_la_serie_solo_cuenta_con_fecha_y_dentro_de_las_24_horas():
    ahora = timezone.now()

    def con(entrada):
        return pad.decidir(pad.FALLA_DE_SERVICIO, {},
                           medicion=_medicion(historial=[entrada]),
                           correcciones=True, ahora=ahora)

    def hace(h):
        return (ahora - timedelta(hours=h)).isoformat()

    debil = {"estado": "en_linea", "senal": "debil", "senal_dbm": -29.0}
    assert con({**debil, "observado_en": hace(23)}).pasa
    assert not con({**debil, "observado_en": hace(25)}).pasa
    assert not con({**debil, "observado_en": "2026-10-18T10:00:00"}).pasa, (
        "sin zona horaria no se sabe si es de hoy")
    assert not con({**debil, "observado_en": "ayer"}).pasa
    assert con({"estado": "caido", "causa_caida": "fibra",
                "observado_en": hace(2)}).pasa
    assert not con({"estado": "caido", "causa_caida": "sin_energia",
                    "observado_en": hace(2)}).pasa
    assert not pad.decidir(
        pad.FALLA_DE_SERVICIO, {}, correcciones=False, ahora=ahora,
        medicion=_medicion(historial=[{**debil, "observado_en": hace(2)}])).pasa


@pytest.mark.parametrize("delegada", [False, True],
                         ids=["sin_la_tarea", "con_la_tarea"])
def test_k_la_fase_de_medicion_guarda_la_remedicion_sin_mirar_la_tarea(
        org_a, monkeypatch, delegada):
    monkeypatch.setattr(
        td, "esta_delegada",
        lambda o, clave: delegada if clave == pad.TAREA_CORRECCIONES else True)
    llamadas = []

    def motor(org, id_servicio):
        llamadas.append(id_servicio)
        return DEBIL

    monkeypatch.setattr(mdf, "_medir_con_el_motor", motor)
    p = _pendiente(org_a, medida=EN_RANGO, hace_horas=9)

    informe = sup._medir_fallas_pendientes(org_a)["medicion"]

    assert llamadas == ["3614"]
    assert informe["remedidas"] == 1
    m = pad.ultima_medicion(P.objects.get(pk=p.pk))
    assert (m["senal"], [h["senal_dbm"] for h in m["historial"]]) == (
        "buena", [-28.5])


# =============================================================================
#  C · EL DOBLE DIAGNOSTICO
# =============================================================================

def test_l_del_ticket_solo_salen_niveles_que_una_onu_puede_dar():
    assert pad.niveles_reportados(
        "Niveles altos -28.24 dBm / -29.59dBm, a 2 km") == [-28.24, -29.59]
    #  Como los escribe el ISP: los dos antes de una sola unidad.
    assert pad.niveles_reportados(
        "el ticket reporta -23.01 / -23.38 dBm") == [-23.01, -23.38]
    assert pad.niveles_reportados("señal -23,1 DBM") == [-23.1]
    assert pad.niveles_reportados(
        "cel 3001234567, cc 1.234.567, -60 dBm, -3 dBm") == []
    assert pad.niveles_reportados("") == []


def test_m_el_doble_diagnostico_informa_y_no_decide():
    en_rango = _medicion(dbm=-23.57)

    coincide = pad.decidir(pad.FALLA_DE_SERVICIO, {}, medicion=en_rango,
                           niveles=[-23.38])
    difiere = pad.decidir(pad.FALLA_DE_SERVICIO, {}, medicion=en_rango,
                          niveles=[-28.24])
    sin = pad.decidir(pad.FALLA_DE_SERVICIO, {}, medicion=en_rango)
    debil = pad.decidir(pad.FALLA_DE_SERVICIO, {},
                        medicion=_medicion(senal="debil", dbm=-28.3),
                        niveles=[-28.24])

    assert (coincide.pasa, difiere.pasa, sin.pasa, debil.pasa) == (
        False, False, False, True)
    assert ("coincide con el nivel que reporta el ticket (-23.38 dBm)"
            in coincide.porque)
    assert "reporta otro nivel (-28.24 dBm)" in difiere.porque
    assert "Doble diagnostico" not in sin.porque
    assert "coincide" in debil.porque
    #  La clave del log no cambia de caso en caso: los niveles salen.
    otra = pad.decidir(pad.FALLA_DE_SERVICIO, {}, medicion=_medicion(dbm=-21.0),
                       niveles=[-21.4])
    clave = pad.motivo_para_el_registro({"porque": coincide.porque})
    assert clave == pad.motivo_para_el_registro({"porque": otra.porque})
    assert "dBm" not in clave


def test_n_el_doble_diagnostico_sale_del_ticket_sin_llevarse_nada_mas(
        org_a, monkeypatch):
    _puertas(monkeypatch, correcciones=False)
    caso = _caso(org_a, description=(
        "Zoraida Clientela 3001234567 reporta -23.38 dBm / -23.01 dBm"))
    p = _pendiente(org_a, caso=caso, medida=_respuesta("en_linea", dbm=-23.57))

    _vuelta(org_a)

    porque = _revision(p)["porque"]
    assert "coincide con el nivel que reporta el ticket (-23.38 dBm)" in porque
    for dato in ("Zoraida", "3001234567"):
        assert dato not in porque


# =============================================================================
#  D · LA LECTURA
# =============================================================================

def _veredicto(**extras):
    return SimpleNamespace(hipotesis="intermitencia", confianza="media",
                           falta=[], riesgo="", recomendacion="",
                           extras=extras)


def test_o_la_lectura_guarda_las_claves_nuevas_y_su_version():
    senal = SimpleNamespace(origen_id="c1", evidencia=[], datos={})
    dxt._anotar(senal, _veredicto(grupo=pad.FALLA_DE_SERVICIO,
                                  accion_autorizada="si",
                                  energia_descartada="no"),
                {"labor": "correctivo", "verificada": False}, timezone.now())
    pieza = next(x for x in senal.evidencia if "grupo" in x)
    assert (pieza["accion_autorizada"], pieza["energia_descartada"],
            pieza["version"]) == ("si", "no", dxt.VERSION_DE_LA_LECTURA)

    #  Lo que el modelo no dijo queda VACIO, no "no": la ausencia es un dato.
    otra = SimpleNamespace(origen_id="c2", evidencia=[], datos={})
    dxt._anotar(otra, _veredicto(grupo=pad.FALLA_DE_SERVICIO), {}, timezone.now())
    pieza = next(x for x in otra.evidencia if "grupo" in x)
    assert (pieza["accion_autorizada"], pieza["energia_descartada"]) == ("", "")


def test_p_las_claves_viajan_en_el_pedido_y_un_valor_inventado_se_descarta():
    from operaciones import cerebro

    pedido = cerebro._pedir_los_extras(pad.CAMPO_PARA_EL_MODELO)
    assert '"accion_autorizada": "si|no"' in pedido
    assert '"energia_descartada": "si|no"' in pedido

    #  'Sí' es 'si' en estas dos claves; una palabra que no es ninguna de las
    #  dos se descarta y se cita, porque sirve para calibrar.
    v = SimpleNamespace(extras={}, descartes=[])
    cerebro._validar_los_extras(
        {"accion_autorizada": "Sí", "energia_descartada": "quizas"},
        pad.CAMPO_PARA_EL_MODELO, v)
    assert v.extras == {"accion_autorizada": "si"}
    assert any("energia_descartada" in d and "(dijo 'quizas')" in d
               for d in v.descartes)

    #  Y SOLO EN ESTAS DOS: en el grupo, una forma parecida sigue siendo otra.
    v = SimpleNamespace(extras={}, descartes=[])
    cerebro._validar_los_extras({"grupo": "Obra_de_red"},
                                pad.CAMPO_PARA_EL_MODELO, v)
    assert v.extras == {}

    #  UNA FRASE NO SE CITA (revisor de PII, 19/10/2026): el modelo puede
    #  justificar la respuesta con el nombre o la direccion del cliente.
    v = SimpleNamespace(extras={}, descartes=[])
    cerebro._validar_los_extras(
        {"accion_autorizada": "si, la autorizo Zoraida Clientela en Calle 45"},
        pad.CAMPO_PARA_EL_MODELO, v)
    assert v.extras == {}
    assert len(v.descartes) == 1 and "Zoraida" not in v.descartes[0]
    assert "<texto libre de 45 caracteres>" in v.descartes[0]


def test_q_la_labor_se_clasifica_con_el_cliente_de_instalaciones(monkeypatch):
    contexto = {"contexto_disponible": True, "servicio": "999",
                "id_servicio_instalaciones": "999"}
    monkeypatch.setattr("campo.services.despacho.contexto_del_caso",
                        lambda caso_id: contexto)
    senal = SimpleNamespace(origen_id="c1")

    nueva = dxt._labor_de(None, senal, "instalacion de fibra")
    contexto["servicio"] = "3614"
    existente = dxt._labor_de(None, senal, "cambio de router")

    assert (nueva["labor"], nueva["verificada"]) == ("instalacion", True)
    assert existente.get("labor") != "instalacion"


def test_r_se_relee_por_version_solo_lo_que_la_lectura_nueva_puede_mover(org_a):
    v1_frena = _pendiente(org_a, medida=EN_RANGO)
    v2_frena = _pendiente(org_a, medida=EN_RANGO,
                          version=dxt.VERSION_DE_LA_LECTURA)
    v1_debil = _pendiente(org_a, medida=DEBIL)
    v1_sin_medir = _pendiente(org_a)
    trabajo_v1 = _pendiente(org_a, grupo=pad.TRABAJO_PEDIDO)

    assert dxt.le_falta_la_version(v1_frena)
    for p in (v2_frena, v1_debil, v1_sin_medir, trabajo_v1):
        assert not dxt.le_falta_la_version(p)
    #  Y el ciclo la pide, por el mismo criterio en los dos lugares.
    assert [s.origen_id for s in sup._las_que_esperan_relectura(org_a, [])] == [
        v1_frena.origen_id]


def test_r2_la_lectura_del_ciclo_la_lee_de_verdad(org_a, monkeypatch):
    """El SEGUNDO lugar que elige que leer ('_leer_tickets_abiertos'): sin el
    criterio de la version ahi, la propuesta se juntaba y se descartaba antes
    de llegar al modelo."""
    v1_frena = _pendiente(org_a, medida=EN_RANGO)
    debil = _pendiente(org_a, medida=DEBIL)
    #  EL RESUMEN YA CITA LA LECTURA: asi el unico camino a la relectura es la
    #  version. Con el motivo sin la hipotesis entraba igual por
    #  'el_juicio_ignora_la_lectura', y la prueba sobrevivia a la mutacion que
    #  devuelve este sitio a los dos criterios viejos (medido el 19/10).
    P.objects.filter(pk__in=[v1_frena.pk, debil.pk]).update(
        motivo='lectura del reclamo: intermitencia')
    leidas = []

    def diagnosticar(org, candidatas, **_):
        leidas.extend(str(s.origen_id) for s in candidatas)
        return {}

    monkeypatch.setattr(sup, "detectar", lambda org, ahora: [])
    monkeypatch.setattr(dxt, "diagnosticar", diagnosticar)

    sup._leer_tickets_abiertos(org_a, timezone.now())

    assert leidas == [v1_frena.origen_id]


def test_r3_al_delegar_se_relee_lo_que_se_leyo_en_sombra(org_a):
    """Auditor independiente, 19/10/2026: desplegado en sombra, las fallas
    frenadas se releian con las claves nuevas pero sin las instrucciones de
    las correcciones, y al delegar la tarea ya no se volvian a leer."""
    en_sombra = _pendiente(org_a, medida=EN_RANGO,
                           version=dxt.VERSION_DE_LA_LECTURA,
                           instrucciones=dxt.SIN_LAS_CORRECCIONES)
    con_ellas = _pendiente(org_a, medida=EN_RANGO,
                           version=dxt.VERSION_DE_LA_LECTURA,
                           instrucciones=dxt.CON_LAS_CORRECCIONES)

    assert not dxt.le_falta_la_version(en_sombra)
    assert dxt.le_falta_la_version(en_sombra, con_las_correcciones=True)
    assert not dxt.le_falta_la_version(con_ellas, con_las_correcciones=True)

    senal = SimpleNamespace(origen_id="c1", evidencia=[], datos={})
    dxt._anotar(senal, _veredicto(grupo=pad.FALLA_DE_SERVICIO), {},
                timezone.now(), con_las_correcciones=True)
    pieza = next(x for x in senal.evidencia if "grupo" in x)
    assert pieza["instrucciones"] == dxt.CON_LAS_CORRECCIONES


def test_r4_la_relectura_filtra_antes_de_cortar(org_a, monkeypatch):
    """Auditor independiente, 19/10/2026: el tope cortaba las mas viejas antes
    de filtrar, y con mas pendientes que el tope la que esperaba relectura
    detras no entraba nunca."""
    monkeypatch.setattr(sup, "TOPE_RELECTURA_SIN_SENAL", 2)
    for _ in range(2):
        _pendiente(org_a, medida=DEBIL)
    espera = _pendiente(org_a, medida=EN_RANGO)

    elegidas = [s.origen_id for s in sup._las_que_esperan_relectura(org_a, [])]

    assert elegidas == [espera.origen_id]


def test_r5_una_respuesta_rota_no_pisa_la_lectura(org_a, monkeypatch):
    """19/10/2026, en produccion: la relectura por version del 95531 volvio
    con una respuesta que no era un objeto, y la falla en rango quedo "sin
    grupo". Una respuesta rota no es una lectura: la anterior sigue valiendo."""
    from operaciones import cerebro

    p = _pendiente(org_a, medida=EN_RANGO)
    rota = SimpleNamespace(hipotesis="", confianza="", falta=[], riesgo="",
                           recomendacion="", extras={}, razonamiento=None,
                           descartes=[cerebro.DESCARTE_SIN_OBJETO])
    pedidas = []

    def concluir(org, **kwargs):
        pedidas.append(1)
        return rota

    monkeypatch.setattr(cerebro, "concluir", concluir)
    monkeypatch.setattr(sup, "detectar", lambda org, ahora: [])

    informe = sup._leer_tickets_abiertos(org_a, timezone.now())

    assert pedidas == [1], "la relectura por version la tenia que pedir"
    assert informe["tickets"]["respuestas_rotas"] == 1
    lectura = pad._ultima_lectura_con_grupo(P.objects.get(pk=p.pk))
    assert lectura["grupo"] == pad.FALLA_DE_SERVICIO
    assert pad.evaluar(P.objects.get(pk=p.pk), timezone.now()).grupo == (
        pad.FALLA_DE_SERVICIO)


def test_s_releer_por_version_tiene_tope(org_a):
    from operaciones.razonamiento_modelos import (
        FuenteRazonamiento,
        RazonamientoSupervisor,
    )

    p = _pendiente(org_a, medida=EN_RANGO)

    def leida():
        RazonamientoSupervisor.objects.create(
            org=org_a, propuesta=p, fuente=FuenteRazonamiento.LECTURA_TICKET,
            registrado_en=timezone.now(), descartes=[])

    for _ in range(dxt.MAXIMAS_RELECTURAS + dxt.RELECTURAS_POR_VERSION - 1):
        leida()
    assert dxt.le_falta_la_version(p)
    leida()
    assert not dxt.le_falta_la_version(p)


def test_t_la_tarea_de_las_correcciones_es_propia_y_pide_nivel_3():
    assert pad.TAREA_CORRECCIONES == td.PASAR_CON_LAS_CORRECCIONES
    assert td.CATALOGO[pad.TAREA_CORRECCIONES]["exige_nivel"] == 3
    assert pad.TAREA_CORRECCIONES != pad.TAREA, (
        "encender las correcciones no puede encender el paso de rebote")
    from cases.models import EXTERNAL_AUTHOR_HUMAN
    assert pad.AUTOR_DE_LA_EMPRESA == EXTERNAL_AUTHOR_HUMAN


def test_t2_delegarla_sin_el_paso_dice_que_falta(org_a, admin_profile,
                                                 monkeypatch):
    """Auditor de frontera, 19/10/2026: contestaba "ya puede actuar" sin el
    paso a Despacho delegado, y la persona se iba creyendo que quedo andando."""
    from operaciones import autonomia
    from operaciones import chat_herramientas as ch

    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    nombre_del_paso = td.CATALOGO[td.PASAR_A_DESPACHO]["nombre"]

    r = ch.delegar_tarea(org_a, clave=pad.TAREA_CORRECCIONES,
                         pedido="aplica mis correcciones", actor=admin_profile)
    assert r["ya_puede_actuar"] is False
    assert nombre_del_paso in r["que_falta"]

    td.delegar(org_a, td.PASAR_A_DESPACHO, actor=admin_profile)
    r = ch.delegar_tarea(org_a, clave=pad.TAREA_CORRECCIONES,
                         actor=admin_profile)
    assert nombre_del_paso not in r["que_falta"]


def test_t3_las_instrucciones_de_las_correcciones_van_solo_con_la_tarea(
        org_a, monkeypatch):
    """Auditor de frontera, 19/10/2026: le cambian al modelo la forma de leer,
    y un grupo movido pasa por la Fase 4 sin la sombra."""
    from operaciones import cerebro

    vistas = []

    def concluir(org, *, instrucciones, entrada, campos_extra, cierre):
        vistas.append(instrucciones)
        raise RuntimeError("basta con ver el pedido")

    monkeypatch.setattr(cerebro, "concluir", concluir)
    for delegada in (False, True):
        monkeypatch.setattr(
            td, "esta_delegada",
            lambda o, clave, d=delegada: d if clave == pad.TAREA_CORRECCIONES
            else True)
        caso = _caso(org_a)
        senal = SimpleNamespace(tipo=P.TICKET_SIN_DIAGNOSTICO,
                                origen_id=str(caso.id), evidencia=[], datos={})
        dxt.diagnosticar(org_a, [senal], tope=1)

    assert len(vistas) == 2
    assert all(v.startswith(dxt.INSTRUCCIONES) for v in vistas)
    assert ["YA AUTORIZADO" in v for v in vistas] == [False, True]


def _releida(org, *, nuevo=pad.TRABAJO_PEDIDO, medida=EN_RANGO,
             previo=pad.FALLA_DE_SERVICIO, version_previa=None):
    """Una propuesta leida antes como 'previo' y releida con la version nueva
    como 'nuevo'."""
    extra = {} if version_previa is None else {"version": version_previa}
    p = _pendiente(org, grupo=previo, medida=medida, **extra)
    evidencia = [*P.objects.get(pk=p.pk).evidencia,
                 _lectura(nuevo, version=dxt.VERSION_DE_LA_LECTURA)]
    P.objects.filter(pk=p.pk).update(evidencia=evidencia)
    return P.objects.get(pk=p.pk)


def test_y_una_relectura_no_saca_a_una_falla_frenada_sin_la_tarea(
        org_a, monkeypatch):
    """Auditor de frontera, 19/10/2026: releida con la version nueva como
    trabajo pedido, la falla que la medicion frenaba pasaba por la Fase 4 en la
    misma vuelta, sin la tarea y sin aparecer en la sombra."""
    _puertas(monkeypatch, correcciones=False)
    releida = _releida(org_a)
    #  Controles: la guarda es angosta.
    nuevo = _pendiente(org_a, grupo=pad.TRABAJO_PEDIDO,
                       version=dxt.VERSION_DE_LA_LECTURA)
    sin_medir = _releida(org_a, medida=None)

    reporte = _vuelta(org_a)

    assert _estado(releida) == P.PROPUESTA
    assert _estado(nuevo) == P.ACEPTADA, "un ticket nuevo se lee como se lee"
    assert _estado(sin_medir) == P.ACEPTADA, "sin medicion que frene, no aplica"
    assert reporte["pasarian_con_las_correcciones"] == {pad.REGLA_RELECTURA: 1}
    assert (pad.SOMBRA_DE_LA_REGLA[pad.REGLA_RELECTURA]
            in _revision(releida)["porque"])


def test_y2_con_la_tarea_la_relectura_decide_y_se_cuenta(org_a, monkeypatch):
    _puertas(monkeypatch, correcciones=True)
    releida = _releida(org_a)

    reporte = _vuelta(org_a)

    assert _estado(releida) == P.ACEPTADA
    assert reporte["pasaron_por_las_correcciones"] == {pad.REGLA_RELECTURA: 1}


def test_z_la_remedicion_no_se_cuenta_si_la_fase_4_ya_lo_pasaba(org_a):
    """Auditor de frontera, 19/10/2026: se le ponia 'remedicion' a un pase de
    la Fase 4, e inflaba 'pasaron por las correcciones'."""
    p = _releida(org_a, version_previa=dxt.VERSION_DE_LA_LECTURA)
    mdf.escribir(p, mdf.de_la_respuesta(DEBIL), timezone.now())
    p.refresh_from_db()

    d = pad.evaluar(p, timezone.now(), correcciones=True)

    assert d.pasa and d.regla == ""


# =============================================================================
#  E · LA LABOR DEL TRABAJO PEDIDO
# =============================================================================

@pytest.fixture
def soledad(org_a):
    from campo.zonas import AliasDeZona, ZonaOperativa

    z = ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad=BARRIO)
    return z


def _en_despacho(org, grupo, *, localidad=None, **lectura):
    caso = _caso(org, status="Assigned")
    evidencia = [_lectura(grupo, **lectura)]
    if localidad is not None:
        evidencia.append({"fuente": adj.FUENTE_LOCALIDAD, "id": str(caso.id),
                          "dato": "barrio",
                          "observado_en": timezone.now().isoformat(),
                          **localidad})
    P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.ACEPTADA, revisado_en=timezone.now(),
        accion_propuesta="Revisar el servicio", motivo="x", prioridad=30,
        evidencia=evidencia)
    return caso


def test_u_el_trabajo_pedido_es_correctivo_salvo_el_de_un_cliente_nuevo(
        org_a, soledad):
    existente = {"localidad": BARRIO, "motivo": "", "cliente_nuevo": False}
    _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad=existente)
    _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad=existente,
                 labor="instalacion", labor_verificada=True)
    #  "instalacion" por el texto, sin verificar: no alcanza.
    _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad=existente,
                 labor="instalacion", labor_verificada=False)
    _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad={
        "localidad": "", "motivo": adj.MOTIVO_INSTALACION_NUEVA,
        "cliente_nuevo": True})
    _en_despacho(org_a, pad.FALLA_DE_SERVICIO, localidad={
        "localidad": "", "motivo": "caso_sin_servicio", "cliente_nuevo": False})

    d = adj.demanda_de_despacho(org_a, adj.propuestas_en_despacho(org_a))

    assert d["por_zona"] == {str(soledad.id): {"correctivo": 2,
                                               "instalacion": 1}}
    assert (d["instalaciones_sin_barrio"], d["sin_barrio"]) == (1, 1)


def test_u2_las_instalaciones_sin_barrio_van_a_las_zonas_de_instalacion(
        org_a, soledad, admin_profile):
    """Auditor independiente, 19/10/2026: sin barrio no entraban en ninguna
    zona, ningun caso pedia instalacion, y la cuadrilla de instalacion salia
    de correctivo con las ordenes de instalacion sin cuadrilla."""
    from campo.cuadrillas import Cuadrilla
    from campo.zonas import ZonaOperativa

    norte = ZonaOperativa.objects.create(org=org_a, nombre="NORTE")
    cerrada = ZonaOperativa.objects.create(org=org_a, nombre="VIEJA",
                                           activa=False)
    instalacion = Cuadrilla.objects.create(
        org=org_a, nombre="#1", lider=admin_profile, labor_habitual="instalacion")
    instalacion.zonas_habituales.set([soledad, cerrada])
    correctivo = Cuadrilla.objects.create(
        org=org_a, nombre="#2", lider=admin_profile, labor_habitual="correctivo")
    correctivo.zonas_habituales.set([soledad, norte])
    existente = {"localidad": BARRIO, "motivo": "", "cliente_nuevo": False}
    for _ in range(2):
        _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad=existente)
    for _ in range(3):
        _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad={
            "localidad": "", "motivo": adj.MOTIVO_INSTALACION_NUEVA,
            "cliente_nuevo": True})

    d = adj.demanda_de_despacho(org_a, adj.propuestas_en_despacho(org_a))

    assert d["por_zona"] == {str(soledad.id): {"correctivo": 2,
                                               "instalacion": 3}}, (
        "solo las zonas activas de las cuadrillas de instalacion")
    assert (d["contados"], d["instalaciones_sin_barrio"],
            d["zonas_con_instalaciones_sin_barrio"]) == (2, 3, 1)


def test_v_la_instalacion_nueva_se_guarda_sin_barrio_y_marcada(org_a, soledad):
    caso = _en_despacho(org_a, pad.TRABAJO_PEDIDO)

    r = adj.completar_localidades(
        adj.propuestas_en_despacho(org_a), ahora=timezone.now(),
        leer=lambda caso_id: ("", adj.MOTIVO_INSTALACION_NUEVA))

    pieza = adj.localidad_guardada(P.objects.get(origen_id=str(caso.id)))
    assert (pieza["localidad"], pieza["cliente_nuevo"]) == ("", True)
    assert "cliente nuevo" in pieza["dato"]
    assert r["sin_dato"] == 1


def test_w_una_pieza_de_antes_sin_la_marca_se_pide_una_vez_mas(org_a, soledad):
    """Las de antes del 18/10 no saben si el caso es de un cliente nuevo, y si
    lo es, su barrio es el del cliente ficticio."""
    vieja = _en_despacho(org_a, pad.TRABAJO_PEDIDO,
                         localidad={"localidad": "OFICINA", "motivo": ""})
    _en_despacho(org_a, pad.TRABAJO_PEDIDO, localidad={
        "localidad": BARRIO, "motivo": "", "cliente_nuevo": False})
    preguntas = []

    def leer(caso_id):
        preguntas.append(str(caso_id))
        return "", adj.MOTIVO_INSTALACION_NUEVA

    for _ in range(2):
        adj.completar_localidades(adj.propuestas_en_despacho(org_a),
                                  ahora=timezone.now(), leer=leer)

    assert preguntas == [str(vieja.id)], "una sola vez, y solo la de antes"


# =============================================================================
#  F · EL INFORME, CASO POR CASO
# =============================================================================

def test_x_el_informe_dice_cuales_pasarian_con_las_correcciones(org_a):
    """Por el camino real: la tarea no esta delegada en la base."""
    autorizada = _pendiente(org_a, medida=EN_RANGO, accion_autorizada="si")
    _pendiente(org_a, medida=EN_RANGO)

    out = StringIO()
    call_command("informe_de_pendientes", "--org", str(org_a.id), stdout=out)
    salida = out.getvalue()

    ticket = pad.caso_de(autorizada).external_ticket_id
    fila = next(f for f in salida.splitlines() if f.startswith(ticket))
    assert "PASA (accion_autorizada)" in fila
    assert ("correcciones: en sombra · pasarian con ellas=1 "
            "{'accion_autorizada': 1}") in salida


def test_x2_el_informe_dice_con_que_se_leyo_y_que_se_re_midio(org_a):
    """19/10/2026: el informe decia que el 95394 pasaria con la re-medicion, y
    no mostraba en cuanto habia dado. Sin el numero no se puede decidir."""
    import re

    remedida = _pendiente(org_a, medida=EN_RANGO, hace_horas=9,
                          version=dxt.VERSION_DE_LA_LECTURA,
                          instrucciones=dxt.CON_LAS_CORRECCIONES)
    mdf.escribir(remedida, mdf.de_la_respuesta(DEBIL), timezone.now())
    vieja = _pendiente(org_a, medida=EN_RANGO)

    out = StringIO()
    call_command("informe_de_pendientes", "--org", str(org_a.id), stdout=out)

    def fila(p):
        ticket = pad.caso_de(p).external_ticket_id
        linea = next(f for f in out.getvalue().splitlines()
                     if f.startswith(ticket))
        return re.split(r"\s{2,}", linea.strip())

    #  columnas: ... medicion(5) re-medida(6) ... leidas(9) lectura(10)
    assert fila(remedida)[5] == "en linea/buena -23.0dBm", (
        "la medicion que decide sin las correcciones no cambia")
    assert fila(remedida)[6].startswith("1x · debil -28.5 · ")
    assert fila(remedida)[10] == f"v{dxt.VERSION_DE_LA_LECTURA}+corr"
    assert (fila(vieja)[6], fila(vieja)[10]) == ("-", "v1")
