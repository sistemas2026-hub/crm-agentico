# -*- coding: utf-8 -*-
"""
================================================================================
 H-21 · EL SUPERVISOR UBICA CADA ASUNTO EN SU NIVEL  --  24/10/2026
================================================================================

Autorizada por el usuario el 24/10/2026 («autorizo la h-21»). Ficha:
supervisor-arma-la-jornada.md, «Niveles de respuesta y H-21».

  R  la regla, sin base: el grupo con mas tickets manda; menos de 3, Normal
     provisional; empate o grupo sin nivel, Normal; y un nivel ya medido se
     mueve solo con mas de la mitad y dos de ventaja (N13)
  C  el conteo: cada caso vota una vez; solo las propuestas que leen
     tickets; el asunto se corta como lo guarda WispHub («Asunto - Cliente»),
     como el escalamiento («Asunto · Cliente · #id») y como corta Case.name
  U  la escritura: lo leido y lo de las plantillas activas; lo de una persona
     no se toca; la vuelta siguiente no repite; un nivel medido no oscila
  E  cada empresa lo suyo: el Supervisor de una no toca ni ve lo de otra
  G  las dos puertas: sin la tarea delegada, sin el nivel 3, o sin poder
     comprobarlas, la SOMBRA (no escribe ni avisa); con las dos, escribe
  A  el aviso: uno por vuelta, a la conversacion de quien DELEGO aunque otra
     persona tenga una mas reciente; nombra solo asuntos de plantilla o con 3
     tickets o mas
  F  la ficha: tipo ACTUA, nivel 3, escribe solo esto, y lo que nombra existe

    pytest operaciones/tests/test_h21_nivel_de_los_asuntos.py
================================================================================
"""

import datetime as dt
import uuid
from collections import Counter

import pytest

from campo import niveles as N
from campo.models import WorkType
from cases.models import Case
from operaciones import nivel_de_los_asuntos as H
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones import tareas_delegadas as td
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

FALLA, OBRA, PEDIDO = pad.FALLA_DE_SERVICIO, pad.OBRA_DE_RED, pad.TRABAJO_PEDIDO


def _caso(org, asunto, grupo=None, *, tipo=None, sin_lectura=False):
    caso = Case.objects.create(
        org=org, name=asunto, status="Assigned", priority="Normal",
        is_active=True, provider="wisphub", area="soporte_tecnico",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}")
    if grupo or sin_lectura:
        _leer(org, caso, grupo, tipo=tipo, sin_lectura=sin_lectura)
    return caso


def _leer(org, caso, grupo, *, tipo=None, sin_lectura=False):
    pieza = {"fuente": pad.FUENTE_DE_LA_LECTURA, "id": str(caso.id),
             "dato": "lectura", "observado_en": "2026-10-24T08:00:00+00:00"}
    if not sin_lectura:
        pieza["grupo"] = grupo
    return P.objects.create(
        org=org, tipo_senal=tipo or P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.PROPUESTA, accion_propuesta="Revisar",
        motivo="x", prioridad=30, evidencia=[pieza])


def _varios(org, asunto, *grupos):
    for g in grupos:
        _caso(org, asunto, g)


def _plantilla(org, codigo, asuntos, activo=True):
    return WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor="correctivo", asuntos=list(asuntos),
                                   activo=activo)


def _fila(org, asunto):
    from campo.plantillas import normalizar_asunto
    return N.NivelDeAsunto.objects.get(org=org, normalizado=normalizar_asunto(asunto))


def _abrir_las_puertas(org, perfil, monkeypatch):
    """La tarea delegada y el nivel 3, por el camino real salvo el interruptor
    del motor, que en la base de pruebas no existe (como el armado)."""
    from operaciones import autonomia
    td.delegar(org, td.UBICAR_LOS_ASUNTOS, actor=perfil,
               pedido_textual="ubica cada asunto en su nivel")
    autonomia.cambiar(org, 3, actor=perfil, motivo="ubicar los asuntos",
                      criterios="sombra mirada")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))


# ---------------------------------------------------------------------------
# R · la regla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grupos,nivel", [
    ({FALLA: 4, OBRA: 1}, N.URGENTE),
    ({OBRA: 3}, N.NORMAL),
    ({PEDIDO: 12}, N.PROGRAMABLE),
    ({PEDIDO: 2, FALLA: 1, OBRA: 1}, N.PROGRAMABLE),
])
def test_r_el_grupo_con_mas_tickets_manda(grupos, nivel):
    assert H.decidir(Counter(grupos))[0] == nivel
    assert H.decidir(Counter(grupos))[2] is False


def test_r2_el_motivo_dice_los_numeros():
    assert H.decidir(Counter({FALLA: 4, OBRA: 1})) == (
        N.URGENTE, "4 de 5 tickets fueron falla de servicio", False)


@pytest.mark.parametrize("total", [0, 1, 2])
def test_r3_con_menos_de_tres_es_normal_provisional(total):
    nivel, motivo, provisional = H.decidir(Counter({FALLA: total}) if total else Counter())
    assert (nivel, provisional) == (N.NORMAL, True)
    assert motivo.startswith("provisional")


def test_r4_con_tres_ya_no_es_provisional():
    assert H.decidir(Counter({FALLA: 3})) == (
        N.URGENTE, "3 de 3 tickets fueron falla de servicio", False)


def test_r5_un_empate_arriba_es_normal_y_lo_dice():
    nivel, motivo, provisional = H.decidir(Counter({FALLA: 2, PEDIDO: 2}))
    assert (nivel, provisional) == (N.NORMAL, False)
    assert "sin un grupo que domine" in motivo


def test_r6_un_grupo_sin_nivel_que_gana_es_normal():
    nivel, motivo, _ = H.decidir(Counter({pad.NADA_LO_MIDE: 3, FALLA: 1}))
    assert nivel == N.NORMAL
    assert "no tiene nivel" in motivo


@pytest.mark.parametrize("grupos,alcanza", [
    ({FALLA: 6, PEDIDO: 5}, False),          # 6 de 11: no le saca 2
    ({FALLA: 7, PEDIDO: 5}, True),           # mas de la mitad y 2 de ventaja
    ({FALLA: 5, PEDIDO: 3, OBRA: 3}, False), # 2 de ventaja pero no la mitad
    ({FALLA: 3}, True),
])
def test_r7_lo_que_alcanza_para_mover_un_nivel_medido(grupos, alcanza):
    assert H.alcanza_para_cambiar(Counter(grupos)) is alcanza


# ---------------------------------------------------------------------------
# C · el conteo
# ---------------------------------------------------------------------------

def test_c_cada_caso_vota_una_vez_con_su_lectura_mas_reciente(org_a):
    caso = _caso(org_a, "Sin Señal TV", PEDIDO)
    _leer(org_a, caso, FALLA)                      # la releyeron: ahora es falla
    _caso(org_a, "sin señal  tv", FALLA)           # el mismo asunto, otra forma

    conteo = H.tickets_por_asunto(org_a)

    assert list(conteo) == ["sin senal tv"]
    assert conteo["sin senal tv"]["grupos"] == Counter({FALLA: 2})


def test_c2_solo_cuentan_las_propuestas_que_leen_tickets(org_a):
    _caso(org_a, "No Tiene Internet", FALLA, tipo=P.CASO_ANTIGUO)
    _caso(org_a, "No Tiene Internet", sin_lectura=True)     # sin grupo todavia

    assert H.tickets_por_asunto(org_a) == {}


def test_c3_el_cliente_que_wisphub_pega_al_asunto_no_parte_el_asunto(org_a):
    """WispHub guarda «Asunto - Cliente» (skill wisphub-api). Tal cual, cada
    cliente era un asunto con un ticket, la regla no decidia nunca, y el
    nombre llegaba al chat (auditor independiente, 25/10/2026)."""
    _caso(org_a, "No Tiene Internet - Cliente Uno", FALLA)
    _caso(org_a, "No Tiene Internet - Cliente Dos", FALLA)
    _caso(org_a, "No Tiene Internet · Cliente Tres · #1a2b3c4d", FALLA)

    conteo = H.tickets_por_asunto(org_a)

    assert list(conteo) == ["no tiene internet"]
    assert conteo["no tiene internet"] == {"asunto": "No Tiene Internet",
                                           "grupos": Counter({FALLA: 3})}


def test_c4_el_asunto_de_la_plantilla_gana_al_corte(org_a):
    """Si la plantilla dice «Cambio De Plan - Upgrade», no se corta en el
    primer « - »; y un nombre cortado en 64 encuentra su plantilla."""
    largo = "Revision De Equipo Por Intermitencia En Horas De La Noche Y Madrugada"
    plantillas = {"cambio de plan - upgrade": "Cambio De Plan - Upgrade",
                  N.asunto_del_ticket(largo, {})[0]: largo}
    assert N.asunto_del_ticket("Cambio De Plan - Upgrade - Cliente Uno", plantillas) == (
        "cambio de plan - upgrade", "Cambio De Plan - Upgrade")
    assert N.asunto_del_ticket(largo[:64], plantillas)[1] == largo
    assert N.asunto_del_ticket("Otra Cosa - Cliente", plantillas) == ("otra cosa", "Otra Cosa")


def test_c5_otra_empresa_no_cuenta(org_a, org_b):
    _varios(org_b, "No Tiene Internet", FALLA, FALLA, FALLA)
    assert H.tickets_por_asunto(org_a) == {}


# ---------------------------------------------------------------------------
# U · la escritura
# ---------------------------------------------------------------------------

def test_u_ubica_lo_leido_y_lo_de_las_plantillas(org_a):
    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA, OBRA)
    _varios(org_a, "Cambio De Domicilio", PEDIDO, PEDIDO, PEDIDO)
    _plantilla(org_a, "soporte", ["Verificacion De Megas"])
    _plantilla(org_a, "vieja", ["Asunto De Una Plantilla Apagada"], activo=False)

    r = H.ubicar_los_asuntos(org_a)

    assert {(c["asunto"], c["nivel"], c["antes"]) for c in r["cambios"]} == {
        ("No Tiene Internet", N.URGENTE, None),
        ("Cambio De Domicilio", N.PROGRAMABLE, None),
        ("Verificacion De Megas", N.NORMAL, None),
    }
    fila = _fila(org_a, "no tiene internet")
    assert (fila.por, fila.motivo, fila.tickets, fila.provisional) == (
        N.POR_SUPERVISOR, "3 de 4 tickets fueron falla de servicio", 4, False)
    megas = _fila(org_a, "Verificacion De Megas")
    assert (megas.nivel, megas.provisional, megas.tickets) == (N.NORMAL, True, 0)
    assert not N.NivelDeAsunto.objects.filter(normalizado__contains="apagada").exists()


def test_u2_la_vuelta_siguiente_no_repite_y_un_provisional_si_cambia(org_a):
    _varios(org_a, "Sin Señal TV", FALLA, OBRA)                 # 2: provisional
    assert [c["nivel"] for c in H.ubicar_los_asuntos(org_a)["cambios"]] == [N.NORMAL]

    r = H.ubicar_los_asuntos(org_a)
    assert r["cambios"] == [] and r["igual"] == 1

    _varios(org_a, "Sin Señal TV", FALLA)                       # 2 de 3: urgente
    [c] = H.ubicar_los_asuntos(org_a)["cambios"]
    assert (c["antes"], c["nivel"]) == (N.NORMAL, N.URGENTE)
    assert _fila(org_a, "sin señal tv").provisional is False


def test_u3_un_nivel_medido_no_oscila_con_cada_ticket(org_a):
    """Con 5 y 5 el nivel saltaba en cada vuelta entre Normal, Urgente y
    Programable, con un aviso cada vez (auditor, con sonda). Ahora un ticket
    no lo mueve; una ventaja clara si."""
    _varios(org_a, "Megas", *([FALLA] * 5 + [PEDIDO] * 5))
    H.ubicar_los_asuntos(org_a)
    assert _fila(org_a, "Megas").nivel == N.NORMAL               # empate

    niveles = []
    for g in (FALLA, PEDIDO, FALLA, PEDIDO):                    # 6-5, 6-6, 7-6, 7-7
        _varios(org_a, "Megas", g)
        r = H.ubicar_los_asuntos(org_a)
        assert r["cambios"] == []
        niveles.append(_fila(org_a, "Megas").nivel)
    assert niveles == [N.NORMAL] * 4

    _varios(org_a, "Megas", FALLA, FALLA, FALLA)               # 10 de 17, +3
    [c] = H.ubicar_los_asuntos(org_a)["cambios"]
    assert (c["antes"], c["nivel"]) == (N.NORMAL, N.URGENTE)


def test_u4_lo_que_decidio_una_persona_no_se_toca(org_a, admin_profile):
    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    N.decidir_por_persona(org_a, "No Tiene Internet", N.PROGRAMABLE,
                          profile=admin_profile, nombre="Ana")

    r = H.ubicar_los_asuntos(org_a)

    assert r["cambios"] == [] and r["de_una_persona"] == 1
    fila = _fila(org_a, "no tiene internet")
    assert (fila.nivel, fila.por, fila.decidido_por_nombre) == (
        N.PROGRAMABLE, N.POR_PERSONA, "Ana")


# ---------------------------------------------------------------------------
# E · cada empresa lo suyo (campo no tiene RLS: el filtro por org es todo)
# ---------------------------------------------------------------------------

def test_e_el_supervisor_de_una_empresa_no_pisa_a_otra(org_a, org_b):
    N.ubicar_por_el_supervisor(org_b, "Megas", N.PROGRAMABLE, motivo="de b",
                               tickets=5, provisional=False)
    N.ubicar_por_el_supervisor(org_a, "Megas", N.NORMAL, motivo="provisional",
                               tickets=1, provisional=True)
    assert N.ubicar_por_el_supervisor(org_a, "Megas", N.URGENTE, motivo="de a",
                                      tickets=4, provisional=False) == N.CAMBIO

    b = N.NivelDeAsunto.objects.get(org=org_b)
    assert (b.nivel, b.motivo) == (N.PROGRAMABLE, "de b")


def test_e2_las_plantillas_de_otra_empresa_no_entran(org_a, org_b):
    _plantilla(org_b, "ajena", ["Asunto De Otra Empresa"])

    H.ubicar_los_asuntos(org_a)

    assert not N.NivelDeAsunto.objects.filter(org=org_a).exists()


# ---------------------------------------------------------------------------
# G · las dos puertas
# ---------------------------------------------------------------------------

def _conversacion(org, profile, minutos_atras=0):
    from django.utils import timezone
    from operaciones.chat_modelos import ConversacionSupervisor
    t = timezone.now() - dt.timedelta(minutes=minutos_atras)
    return ConversacionSupervisor.objects.create(
        org=org, actor=profile, abierta_en=t, ultimo_mensaje_en=t)


def _apagar_las_otras_fases(monkeypatch):
    """Solo H-21: las demas fases no son de esta prueba (y algunas le
    preguntan al motor). El mismo recorte que las pruebas del feriado."""
    monkeypatch.setattr(sup, "_el_cerebro_corre", lambda: False)
    for fase in ("_atender_desincronizados", "_leer_tickets_abiertos",
                 "_medir_fallas_pendientes",
                 "_pasar_a_despacho_los_que_las_reglas_habiliten",
                 "_armar_la_jornada_del_dia", "_verificar_los_arreglos"):
        monkeypatch.setattr(sup, fase, lambda *a, **k: {})
    monkeypatch.setattr(sup, "retirar_alertas_de_casos_en_despacho",
                        lambda *a, **k: 0)


def test_g_sin_la_tarea_delegada_es_sombra(org_a, admin_profile, monkeypatch):
    from operaciones import autonomia
    from operaciones.chat_modelos import MensajeSupervisor

    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    _conversacion(org_a, admin_profile)
    td.delegar(org_a, td.CICLO_AUTOMATICO, actor=admin_profile)
    autonomia.cambiar(org_a, 3, actor=admin_profile, motivo="x", criterios="y")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    _apagar_las_otras_fases(monkeypatch)

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]

    assert (r["modo"], r["ubicaria"]) == (H.SOMBRA, 1)
    assert "delego" in r["porque"]
    assert not N.NivelDeAsunto.objects.exists()
    assert not MensajeSupervisor.objects.exists()


def test_g2_sin_el_nivel_3_de_la_empresa_es_sombra(org_a, admin_profile, monkeypatch):
    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    td.delegar(org_a, td.UBICAR_LOS_ASUNTOS, actor=admin_profile)
    monkeypatch.setattr("operaciones.autonomia._interruptor_de", lambda org: (True, ""))
    _apagar_las_otras_fases(monkeypatch)

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]

    assert r["modo"] == H.SOMBRA and "no tiene autorizado" in r["porque"]
    assert not N.NivelDeAsunto.objects.exists()


def test_g3_sin_poder_comprobar_la_tarea_es_sombra(org_a, admin_profile, monkeypatch):
    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    _abrir_las_puertas(org_a, admin_profile, monkeypatch)

    def no_se_puede(*a, **k):
        raise RuntimeError("la base no responde")
    monkeypatch.setattr(td, "esta_delegada", no_se_puede)
    _apagar_las_otras_fases(monkeypatch)

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]

    assert r["modo"] == H.SOMBRA and "no se pudo comprobar" in r["porque"]
    assert not N.NivelDeAsunto.objects.exists()


# ---------------------------------------------------------------------------
# A · el aviso en el chat
# ---------------------------------------------------------------------------

def test_a_el_texto_nombra_solo_asuntos_de_verdad():
    from operaciones import aviso_al_chat as A
    nombres = {N.URGENTE: "Urgente", N.NORMAL: "Normal", N.PROGRAMABLE: "Programable"}
    texto = A.redactar_niveles([
        {"asunto": "Sin Señal TV", "antes": None, "nivel": N.URGENTE, "tickets": 5,
         "motivo": "4 de 5 tickets fueron falla de servicio", "provisional": False},
        {"asunto": "Megas", "antes": N.NORMAL, "nivel": N.PROGRAMABLE, "tickets": 3,
         "motivo": "3 de 3 tickets fueron trabajo pedido", "provisional": False},
        {"asunto": "Verificacion", "antes": None, "nivel": N.NORMAL, "tickets": 0,
         "de_plantilla": True, "motivo": "provisional: ningún ticket leído",
         "provisional": True},
        {"asunto": "Un Asunto Raro Juan Perez", "antes": None, "nivel": N.NORMAL,
         "tickets": 1, "motivo": "provisional: 1 ticket leído", "provisional": True},
    ], nombres)
    assert "«Sin Señal TV»: Urgente, porque 4 de 5 tickets fueron falla de servicio." in texto
    assert "«Megas»: de Normal a Programable, porque 3 de 3 tickets" in texto
    assert "«Verificacion»: Normal, por ahora (ningún ticket leído)." in texto
    assert "Juan Perez" not in texto
    assert "1 asunto con pocos tickets y sin plantilla" in texto
    assert "no lo vuelvo a tocar" in texto


def test_a2_el_ciclo_lo_cuenta_una_vez_a_quien_delego(org_a, admin_profile,
                                                      user_profile, monkeypatch):
    """Otra persona de la empresa con una conversacion MAS reciente no recibe
    el aviso: es de quien delego (auditor independiente, 25/10/2026: sacar el
    filtro por persona no lo cazaba ninguna prueba)."""
    from operaciones.chat_modelos import MensajeSupervisor

    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    vieja = _conversacion(org_a, admin_profile, minutos_atras=60)
    nueva = _conversacion(org_a, admin_profile, minutos_atras=5)
    ajena = _conversacion(org_a, user_profile, minutos_atras=1)
    td.delegar(org_a, td.CICLO_AUTOMATICO, actor=admin_profile)
    _abrir_las_puertas(org_a, admin_profile, monkeypatch)
    _apagar_las_otras_fases(monkeypatch)

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]

    assert (r["modo"], r["ubicados"], r["avisado"]) == (H.UBICADO, 1, True)
    [m] = MensajeSupervisor.objects.filter(conversacion=nueva)
    assert "«No Tiene Internet»: Urgente, porque 3 de 3 tickets" in m.contenido
    assert not MensajeSupervisor.objects.filter(conversacion__in=[vieja, ajena]).exists()

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]     # nada cambio
    assert (r["ubicados"], r["avisado"]) == (0, False)
    assert MensajeSupervisor.objects.filter(conversacion=nueva).count() == 1


def test_a3_sin_la_revision_delegada_ubica_igual_y_no_escribe(org_a, admin_profile,
                                                              monkeypatch):
    from operaciones.chat_modelos import MensajeSupervisor

    _varios(org_a, "No Tiene Internet", FALLA, FALLA, FALLA)
    _conversacion(org_a, admin_profile)
    _abrir_las_puertas(org_a, admin_profile, monkeypatch)
    _apagar_las_otras_fases(monkeypatch)

    r = sup.correr_ciclo(org_a)["niveles_de_los_asuntos"]

    assert (r["ubicados"], r["avisado"]) == (1, False)
    assert _fila(org_a, "No Tiene Internet").nivel == N.URGENTE
    assert not MensajeSupervisor.objects.exists()


# ---------------------------------------------------------------------------
# F · la ficha
# ---------------------------------------------------------------------------

def test_f_la_ficha_dice_lo_que_hace_el_codigo():
    import importlib

    from operaciones import habilidades
    h = habilidades.HABILIDADES["H-21"]
    assert (h.tipo, h.nivel, h.estado) == (habilidades.ACTUA, P.NIVEL_EJECUTAR_REVERSIBLE,
                                           habilidades.VIGENTE)
    assert h.herramientas_escritura == (
        "ORM: campo.NivelDeAsunto, solo las filas que decidio el Supervisor",
        "ORM: operaciones.MensajeSupervisor, el aviso a quien delego")
    assert td.CATALOGO[td.UBICAR_LOS_ASUNTOS]["exige_nivel"] == H.NIVEL_PARA_UBICAR == 3
    #  Cada funcion que nombra el procedimiento existe: si alguien la
    #  renombra, la ficha queda mintiendo.
    for paso in h.procedimiento:
        ruta = paso.rsplit("(", 1)[1].rstrip(").")
        modulo, funcion = ruta.rsplit(".", 1)
        nombre = modulo if modulo.startswith("campo.") else f"operaciones.{modulo}"
        assert callable(getattr(importlib.import_module(nombre), funcion)), paso
