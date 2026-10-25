# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR UBICA LA OBRA DE RED, SOLO  --  25/10/2026
================================================================================

Pedido del usuario: «hay que darle la capacidad de que el supervisor
identifique sin que uno tenga que estar mostrando». Lo que lo motivo: una obra
de Santa Sofia (Sabanagrande) abierta con la cuenta de la oficina iba a una
cuadrilla de Soledad. Afirma:

  B  buscar un barrio cargado en el texto: sin tildes ni signos, palabra
     entera, el nombre largo antes que el corto, lo que no cuenta (la
     oficina) no cuenta, y dos zonas = ambiguo
  R  la regla: una obra de red, por el barrio que nombra su ticket, y si no
     nombra ninguno NO SE SABE (no cae a la oficina); un cliente, siempre por
     su barrio, aunque su texto nombre otro (la auditoria del 25/10 midio que
     leer el texto de un cliente lo mandaba a otra zona)
  O  que es una obra: la lectura la puso en `obra_de_red`, y no es el ticket
     de un cliente dentro de un corte de red
  Z  de punta a punta, en «Ver qué crearía», en la demanda y en los barrios
     sin zona: con el texto del asunto o de la descripcion

    pytest operaciones/tests/test_el_supervisor_ubica_el_caso.py
================================================================================
"""
import pytest

from campo.zonas import AliasDeZona, ZonaOperativa
from cases.models import Case
from operaciones import armado_de_jornadas as adj
from operaciones import ordenes_de_despacho as O
from operaciones import paso_a_despacho as pad
from operaciones import ubicacion_del_caso as ub
from operaciones.tests import test_el_supervisor_crea_las_ordenes as _base
from operaciones.tests.test_el_supervisor_crea_las_ordenes import (
    A_LAS_3,
    CORTE,
    _caso,
)

pytestmark = pytest.mark.django_db

empresa = _base.empresa
plantillas = _base.plantillas

SAB, SOL = "zona-sabanagrande", "zona-soledad"
BUSCABLES = ub.preparar({"SANTA SOFIA": SAB, "VILLA MARIA": SOL, "MARIA": SAB,
                         "VIÑA DEL REY": SOL, "OFICINA": SOL, "LA PAZ": SOL})


# ---------------------------------------------------------------------------
# B · buscar el barrio en el texto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("Intervencio Santa Sofia Niveles Altos", "SANTA SOFIA"),
    ("Mantenimiento CTO 53-66 VIÑA DEL REY", "VIÑA DEL REY"),
    ("Mantenimiento CTO 53-66 Vina del Rey,", "VIÑA DEL REY"),   # sin tilde
    ("caja de SANTA SOFIAS", ""),                                # palabra entera
    ("Intervencion de la caja 11-43 de villa maria", "VILLA MARIA"),  # consume
    ("de Santa Sofia a Villa Maria", ""),                        # dos zonas
    #  Sacar SANTA SOFIA no pega «DE LA» con «PAZ» (auditoria, H9).
    ("Caja de la Santa Sofia Paz", "SANTA SOFIA"),
    ("No tiene internet", ""),
])
def test_b_buscar_el_barrio_en_el_texto(texto, esperado):
    assert ub.barrio_en_el_texto(texto, BUSCABLES) == esperado


def test_b2_lo_que_no_cuenta_no_cuenta():
    texto = "Material se recoge en la oficina. Intervencion Santa Sofia"
    assert ub.barrio_en_el_texto(texto, BUSCABLES) == ""          # dos zonas
    assert ub.barrio_en_el_texto(texto, BUSCABLES, sin={"OFICINA"}) == "SANTA SOFIA"


# ---------------------------------------------------------------------------
# R · la regla
# ---------------------------------------------------------------------------

def test_r_una_obra_por_el_barrio_que_nombra_su_ticket():
    assert ub.barrio_del_caso("OFICINA", "Intervencion Santa Sofia; recoger en la "
                              "oficina", es_obra=True, buscables=BUSCABLES) == (
        "SANTA SOFIA", ub.DEL_TICKET)


@pytest.mark.parametrize("texto", ["Censo de posteria",
                                   "de Santa Sofia a Villa Maria"])
def test_r2_una_obra_sin_barrio_en_el_ticket_no_se_sabe_donde_es(texto):
    #  NO cae al barrio de la cuenta: es el de la oficina, no el del trabajo.
    assert ub.barrio_del_caso("OFICINA", texto, es_obra=True,
                              buscables=BUSCABLES) == ("", "")


def test_r2b_si_el_ticket_nombra_solo_el_barrio_de_la_cuenta_lo_confirma():
    assert ub.barrio_del_caso("VILLA MARIA", "Caja de Villa Maria", es_obra=True,
                              buscables=BUSCABLES) == ("VILLA MARIA", ub.DEL_TICKET)


@pytest.mark.parametrize("del_cliente, esperado", [
    ("VILLA MARIA", ("VILLA MARIA", ub.DEL_CLIENTE)),
    ("BARRIO QUE NADIE CARGO", ("BARRIO QUE NADIE CARGO", ub.DEL_CLIENTE)),
    ("", ("", "")),
])
def test_r3_un_cliente_siempre_por_su_barrio(del_cliente, esperado):
    #  El texto nombra UN barrio de otra zona, sin ambiguedad: igual no cuenta.
    assert ub.barrio_del_caso(del_cliente, "Vive cerca de Santa Sofia",
                              es_obra=False, buscables=BUSCABLES) == esperado


# ---------------------------------------------------------------------------
# O · que es una obra
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grupo, es_corte, esperado", [
    (pad.OBRA_DE_RED, False, True),
    (pad.OBRA_DE_RED, True, False),       # el cliente de un corte de red
    (pad.FALLA_DE_SERVICIO, False, False),
    (pad.NI_CLIENTE_NI_RED, False, False),
    ("", False, False),
])
def test_o_que_es_una_obra(grupo, es_corte, esperado):
    assert ub.es_obra_de_red({"grupo": grupo}, es_corte=es_corte) is esperado


# ---------------------------------------------------------------------------
# Z · de punta a punta
# ---------------------------------------------------------------------------

@pytest.fixture
def dos_zonas(empresa):
    """SOLEDAD (la del fixture, con SOLEDAD CENTRO) mas OFICINA, y
    SABANAGRANDE con SANTA SOFIA."""
    soledad = ZonaOperativa.objects.get(org=empresa, nombre="SOLEDAD")
    AliasDeZona.objects.create(org=empresa, zona=soledad, localidad="OFICINA")
    sab = ZonaOperativa.objects.create(org=empresa, nombre="SABANAGRANDE")
    AliasDeZona.objects.create(org=empresa, zona=sab, localidad="SANTA SOFIA")
    return empresa


def _con_descripcion(caso, texto):
    Case.objects.filter(pk=caso.pk).update(description=texto)


def _por_caso(salida):
    return ({f["caso"]: f for f in salida["crear"]},
            {f["caso"]: f for f in salida["no_se_crea"]})


def test_z_la_obra_de_santa_sofia_sale_para_sabanagrande(dos_zonas, plantillas):
    obra = _caso(dos_zonas, asunto="Intervencio Santa Sofia Niveles Altos",
                 grupo=pad.OBRA_DE_RED, barrio="OFICINA")
    #  Un cliente de Soledad cuyo texto nombra Santa Sofia: sigue en Soledad.
    cliente = _caso(dos_zonas, asunto="No tiene internet")
    _con_descripcion(cliente, "Vive cerca de Santa Sofia")

    crear, _ = _por_caso(O.decidir(dos_zonas, A_LAS_3))

    o = crear[str(obra.id)]
    assert (o["barrio"], o["barrio_de"], o["zona"]) == (
        "SANTA SOFIA", ub.DEL_TICKET, "SABANAGRANDE")
    c = crear[str(cliente.id)]
    assert (c["barrio_de"], c["zona"]) == (ub.DEL_CLIENTE, "SOLEDAD")


def test_z2_el_barrio_puede_estar_en_la_descripcion(dos_zonas, plantillas):
    obra = _caso(dos_zonas, asunto="Corte de fibra", grupo=pad.OBRA_DE_RED,
                 barrio="OFICINA")
    _con_descripcion(obra, "Cambiar la caja de Santa Sofia, nivel alto")

    crear, _ = _por_caso(O.decidir(dos_zonas, A_LAS_3))

    assert crear[str(obra.id)]["zona"] == "SABANAGRANDE"


def test_z3_una_obra_que_no_dice_donde_es_no_se_crea_sola(dos_zonas, plantillas):
    obra = _caso(dos_zonas, asunto="Censo de posteria", grupo=pad.OBRA_DE_RED,
                 barrio="OFICINA")

    _, no = _por_caso(O.decidir(dos_zonas, A_LAS_3))

    assert no[str(obra.id)]["motivo"] == O.OBRA_SIN_BARRIO


def test_z4_el_cliente_de_un_corte_de_red_va_por_su_barrio(dos_zonas, plantillas):
    cliente = _caso(dos_zonas, asunto="No tiene internet", barrio="SANTA SOFIA",
                    medicion=CORTE)
    _con_descripcion(cliente, "Cliente se acercó a la oficina a reportar")

    crear, _ = _por_caso(O.decidir(dos_zonas, A_LAS_3))

    f = crear[str(cliente.id)]
    assert (f["zona"], f["barrio_de"], f["corte_de_red"]) == (
        "SABANAGRANDE", ub.DEL_CLIENTE, True)


def test_z5_la_demanda_cuenta_la_obra_donde_es(dos_zonas, plantillas):
    _caso(dos_zonas, asunto="Intervencio Santa Sofia Niveles Altos",
          grupo=pad.OBRA_DE_RED, barrio="OFICINA")
    _caso(dos_zonas, asunto="Censo de posteria", grupo=pad.OBRA_DE_RED,
          barrio="OFICINA")
    sab = ZonaOperativa.objects.get(org=dos_zonas, nombre="SABANAGRANDE")

    d = adj.demanda_de_despacho(dos_zonas, adj.propuestas_en_despacho(dos_zonas))

    assert d["por_zona"] == {str(sab.id): {"trabajos": 1}}
    assert d["obras_sin_barrio"] == 1


def test_z6_la_cuenta_de_una_obra_no_se_pide_cargar(dos_zonas, plantillas):
    _caso(dos_zonas, asunto="Intervencio Santa Sofia", grupo=pad.OBRA_DE_RED,
          barrio="CUENTA DE LA OFICINA")
    _caso(dos_zonas, asunto="No tiene internet", barrio="OTRO SIN CARGAR")

    sin_zona = adj._barrios_sin_zona(dos_zonas, adj.propuestas_en_despacho(dos_zonas))

    assert sin_zona == [{"barrio": "OTRO SIN CARGAR", "casos": 1}]


# ---------------------------------------------------------------------------
# I · el informe de solo lectura, para medir en produccion
# ---------------------------------------------------------------------------

def test_i_el_informe_muestra_lo_que_calculo_y_no_el_asunto(dos_zonas, plantillas):
    import io

    from django.core.management import call_command

    obra = _caso(dos_zonas, asunto="Intervencio Santa Sofia Niveles Altos",
                 grupo=pad.OBRA_DE_RED, barrio="OFICINA")
    _caso(dos_zonas, asunto="Algo raro", grupo=pad.NADA_LO_MIDE)
    salida = io.StringIO()

    call_command("informe_de_despacho", "--org", str(dos_zonas.id), stdout=salida)

    texto = salida.getvalue()
    assert obra.external_ticket_id in texto
    assert "SANTA SOFIA [ticket]" in texto and "SABANAGRANDE" in texto
    assert "sin labor, por grupo: nada_mide 1" in texto
    #  Ni el asunto ni el cliente: solo el numero del ticket y lo calculado.
    assert "Intervencio" not in texto and "Algo raro" not in texto
    assert "Zoraida" not in texto
