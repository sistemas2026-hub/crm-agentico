# -*- coding: utf-8 -*-
"""
================================================================================
 LA SEÑAL QUE TERMINA EN UNA CUADRILLA MANEJANDO HASTA UNA CASA
================================================================================

Que cubre y por que
-------------------
`CASO_REQUIERE_VISITA` nace el 09/10/2026 con la pantalla de despacho. Las
demas señales dicen que algo esta ATRASADO o DESALINEADO; esta dice que hay
trabajo fisico que hacer, y es la unica que termina en una orden y en alguien
manejando treinta kilometros.

Por eso lo que se verifica no es que proponga, sino QUE NO PROPONE:

  - un equipo SANO no genera señal -- que no sea falla de red no quiere decir
    que no haya trabajo, pero eso lo decide una persona
  - SIN ENERGIA tampoco: el problema es el corte de luz en la casa
  - lo que salio del TEXTO tampoco: pedirle a alguien que mande una cuadrilla
    porque un asunto decia cierta palabra seria pedirle que confie en lo que
    nadie verifico
  - un caso que no se pudo consultar NO es un caso sano

Y que lo que si propone llegue con su evidencia: quien acepta esto manda a
alguien a una casa, y tiene que poder ver contra que.

    pytest operaciones/tests/test_senal_requiere_visita.py
================================================================================
"""

import pytest

from operaciones import supervisor
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


def _caso(org, nombre="Sin internet", servicio="6580"):
    from cases.models import Case

    return Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal",
        is_active=True, external_service_id=servicio,
    )


def _contexto(**equipo):
    """Un snapshot como el que arma `contexto_del_caso`."""
    base = {
        "contexto_disponible": True,
        "capturado_en": "2026-10-09T03:00:00Z",
        "servicio": "6580",
        "cliente": {"nombre": "Alguien"},
    }
    if equipo:
        base["equipo"] = equipo
    return base


def _con_ficha(monkeypatch, contexto):
    monkeypatch.setattr(supervisor, "_casos_que_necesitan_visita",
                        supervisor._casos_que_necesitan_visita)
    import campo.services.despacho as desp
    monkeypatch.setattr(desp, "contexto_del_caso", lambda cid: contexto)


# ---------------------------------------------------------------------------
# A · lo que SÍ propone
# ---------------------------------------------------------------------------

def test_a_caido_por_fibra_propone_visita(org_a, monkeypatch):
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="caido", causa_caida="fibra"))

    senales = supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert len(senales) == 1
    assert senales[0].tipo == PropuestaSupervisor.CASO_REQUIERE_VISITA
    assert senales[0].datos["labor_sugerida"] == "correctivo"


def test_b_la_senal_llega_con_su_EVIDENCIA(org_a, monkeypatch):
    """Quien acepta esto manda a alguien a una casa."""
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="caido", causa_caida="fibra"))

    senal = supervisor._casos_que_necesitan_visita(org_a, _ahora())[0]
    assert len(senal.evidencia) >= 3
    textos = " ".join(str(e) for e in senal.evidencia)
    assert "caido" in textos
    assert "6580" in textos            # el servicio en el proveedor
    assert "optica" in textos          # el porqué de la clasificación


def test_c_viaja_la_hora_de_la_MEDICION(org_a, monkeypatch):
    """Al congelarse, una medición deja de ser una medición y pasa a ser un
    registro de lo que se veía en un momento."""
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="caido", causa_caida="fibra"))

    senal = supervisor._casos_que_necesitan_visita(org_a, _ahora())[0]
    assert senal.datos["medido_en"] == "2026-10-09T03:00:00Z"


def test_d_senal_debil_tambien_propone(org_a, monkeypatch):
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="en_linea", senal="debil", senal_dbm=-27.4))

    senales = supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert senales[0].datos["labor_sugerida"] == "correctivo"


# ---------------------------------------------------------------------------
# B · lo que NO propone, que es lo que importa
# ---------------------------------------------------------------------------

def test_e_un_equipo_SANO_no_genera_senal(org_a, monkeypatch):
    """Que no sea una falla de red no quiere decir que no haya trabajo.

    El cliente puede pedir una reubicación. Pero eso lo decide una persona, no
    una medición que no lo vio.
    """
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="en_linea", senal="buena", senal_dbm=-21.8))

    assert supervisor._casos_que_necesitan_visita(org_a, _ahora()) == []


def test_f_SIN_ENERGIA_no_manda_a_nadie(org_a, monkeypatch):
    """Mandar una cuadrilla es mandarla a mirar cómo alguien espera que vuelva
    la luz."""
    _caso(org_a)
    _con_ficha(monkeypatch,
               _contexto(estado="caido", causa_caida="sin_energia"))

    assert supervisor._casos_que_necesitan_visita(org_a, _ahora()) == []


def test_g_lo_que_salio_del_TEXTO_no_propone(org_a, monkeypatch):
    """Sería pedirle a alguien que confíe en lo que nadie verificó.

    La clasificación por texto marca `verificada: False`, y esta señal solo
    propone lo que la medición sostiene.
    """
    _caso(org_a)
    #  Sin equipo: la clasificación no puede concluir por medición.
    _con_ficha(monkeypatch, _contexto())

    assert supervisor._casos_que_necesitan_visita(org_a, _ahora()) == []


def test_h_un_caso_que_NO_SE_PUDO_CONSULTAR_no_es_un_caso_sano(
    org_a, monkeypatch
):
    """No se propone, y tampoco se afirma que esté bien."""
    _caso(org_a)
    import campo.services.despacho as desp
    monkeypatch.setattr(
        desp, "contexto_del_caso",
        lambda cid: {"contexto_disponible": False, "motivo": "ConnectTimeout"},
    )

    assert supervisor._casos_que_necesitan_visita(org_a, _ahora()) == []


def test_i_si_la_consulta_REVIENTA_no_se_lleva_a_los_demas(
    org_a, monkeypatch
):
    _caso(org_a, "Uno", servicio="1")
    import campo.services.despacho as desp

    def explota(cid):
        raise RuntimeError("el motor no responde")

    monkeypatch.setattr(desp, "contexto_del_caso", explota)
    #  No lanza: devuelve vacío y los demás detectores siguen corriendo.
    assert supervisor._casos_que_necesitan_visita(org_a, _ahora()) == []


def test_j_un_caso_SIN_SERVICIO_no_se_mira(org_a, monkeypatch):
    """Nació de una conversación y nunca va a tener servicio asociado: no hay
    contra qué identificador preguntar."""
    _caso(org_a, "De un chat", servicio="")
    import campo.services.despacho as desp
    pedidos = []
    monkeypatch.setattr(desp, "contexto_del_caso",
                        lambda cid: pedidos.append(cid) or _contexto())

    supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert pedidos == []


def test_k_un_caso_CERRADO_no_se_mira(org_a, monkeypatch):
    from cases.models import Case

    Case.objects.create(org=org_a, name="Cerrado", status="Closed",
                        priority="Normal", is_active=True,
                        external_service_id="6580")
    import campo.services.despacho as desp
    pedidos = []
    monkeypatch.setattr(desp, "contexto_del_caso",
                        lambda cid: pedidos.append(cid) or _contexto())

    supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert pedidos == []


# ---------------------------------------------------------------------------
# C · el tope
# ---------------------------------------------------------------------------

def test_l_hay_un_TOPE_de_casos_por_ciclo(org_a, monkeypatch):
    """Cada caso cuesta una llamada al motor, que a su vez habla con WispHub y
    SmartOLT. Sin tope, doscientos casos abiertos son doscientos viajes."""
    for n in range(supervisor.TOPE_CASOS_A_DIAGNOSTICAR + 5):
        _caso(org_a, f"Caso {n}", servicio=str(6000 + n))

    import campo.services.despacho as desp
    pedidos = []
    monkeypatch.setattr(desp, "contexto_del_caso",
                        lambda cid: pedidos.append(cid) or _contexto())

    supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert len(pedidos) == supervisor.TOPE_CASOS_A_DIAGNOSTICAR


# ---------------------------------------------------------------------------
# D · el detector está enchufado
# ---------------------------------------------------------------------------

def test_m_el_detector_esta_REGISTRADO(org_a):
    """«Código construido no es código que corre».

    El reloj de tareas colgaba de un bloque que gunicorn nunca ejecutaba y la
    reconciliación estaba probada y sin llamador: ninguno dio error ni alerta.
    """
    import inspect

    fuente = inspect.getsource(supervisor.detectar)
    assert "_casos_que_necesitan_visita" in fuente


def _ahora():
    from django.utils import timezone

    return timezone.now()
