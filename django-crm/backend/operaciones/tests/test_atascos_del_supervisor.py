"""
================================================================================
 LOS ATASCOS DEL SUPERVISOR  --  29/10/2026
================================================================================
`operaciones/atascos.py`: lo que el ciclo no pudo decidir, anotado con su tipo,
para medir cuantos atascos hay antes de decidir si un agente de IA los
resuelve. Lo que se afirma, siempre sobre la FILA que queda en la base:

  A  una fila por dia y atasco: la segunda vuelta suma; otro dia, otra fila;
     el dia es el de la empresa; un tipo fuera del catalogo no se anota; anotar
     nunca levanta.
  I  el informe cuenta dias y COSAS distintas, no filas.
  R  el reparto anota lo que no pudo ubicar, en la sombra tambien.
  C  una fase del ciclo que se cae es un atasco con su fase.
  K  el comando lo imprime.

Las fases del material, del paso a Despacho y de la lectura tienen sus
pruebas junto a las suyas: test_el_supervisor_carga_el_material,
test_el_paso_mira_todas_y_dice_por_que y test_rastro_de_la_lectura.

    pytest operaciones/tests/test_atascos_del_supervisor.py
================================================================================
"""
import datetime as dt
import io
import zoneinfo
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from operaciones import atascos
from operaciones.models import AtascoDelSupervisor

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


def _a_las(dia, hora, minuto=0):
    return dt.datetime.combine(dt.date(2026, 10, dia), dt.time(hora, minuto), tzinfo=BOGOTA)


@pytest.fixture
def empresa(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


def _filas(org):
    return list(AtascoDelSupervisor.objects.filter(org=org).order_by("dia", "tipo", "sujeto"))


# ---------------------------------------------------------------------------
# A · anotar
# ---------------------------------------------------------------------------

def test_a_la_segunda_vuelta_suma_y_otro_dia_es_otra_fila(empresa):
    assert atascos.anotar(empresa, atascos.FASE_MATERIAL, "kit_sin_elegir", "trabajos",
                          "ningún kit", ahora=_a_las(28, 7))
    atascos.anotar(empresa, atascos.FASE_MATERIAL, "kit_sin_elegir", "trabajos",
                   "ningún kit  se parece", ahora=_a_las(28, 8))
    atascos.anotar(empresa, atascos.FASE_MATERIAL, "kit_sin_elegir", "trabajos",
                   "ningún kit", ahora=_a_las(29, 7))

    hoy, manana = _filas(empresa)
    assert (str(hoy.dia), hoy.veces, hoy.motivo) == ("2026-10-28", 2, "ningún kit se parece")
    assert (hoy.primera_vez, hoy.ultima_vez) == (_a_las(28, 7), _a_las(28, 8))
    assert (str(manana.dia), manana.veces) == ("2026-10-29", 1)


def test_a2_el_dia_es_el_de_la_empresa(empresa):
    """23:30 en Bogota es el 04:30 UTC del dia siguiente: el atasco es del dia
    en que la empresa lo vio. En UTC, que es como llega la hora del ciclo."""
    ahora = _a_las(28, 23, 30).astimezone(dt.timezone.utc)
    assert str(ahora.date()) == "2026-10-29"
    atascos.anotar(empresa, atascos.FASE_CICLO, "fase_caida", "x", ahora=ahora)
    assert str(_filas(empresa)[0].dia) == "2026-10-28"


def test_a3_un_tipo_fuera_del_catalogo_no_se_anota(empresa):
    assert not atascos.anotar(empresa, atascos.FASE_CICLO, "un_tipo_inventado", "x")
    assert _filas(empresa) == []


def test_a4_anotar_nunca_levanta(empresa, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("la base no contesta")

    monkeypatch.setattr(atascos, "_sumar", rompe)
    assert atascos.anotar(empresa, atascos.FASE_CICLO, "fase_caida", "x") is False


def test_a5_cada_tipo_del_catalogo_tiene_una_clase_conocida():
    assert {clase for clase, _ in atascos.TIPOS.values()} <= set(atascos.CLASES)


# ---------------------------------------------------------------------------
# I · el informe
# ---------------------------------------------------------------------------

def test_i_cuenta_dias_y_cosas_distintas_no_filas(empresa, org_b):
    for dia in (27, 28):
        for hora in (7, 8):
            atascos.anotar(empresa, atascos.FASE_MATERIAL, "kit_sin_elegir", "trabajos",
                           "ningún kit", ahora=_a_las(dia, hora))
    for c in ("c-1", "c-2"):
        atascos.anotar(empresa, atascos.FASE_MATERIAL, "bodega_sin_elegir", c, "no sé",
                       ahora=_a_las(28, 7))
    atascos.anotar(empresa, atascos.FASE_LECTURA, "ia_error", "caso-1", "TimeoutError",
                   ahora=_a_las(28, 7))
    #  Fuera del rango y de otra empresa: no cuentan.
    atascos.anotar(empresa, atascos.FASE_LECTURA, "ia_error", "caso-2", "x",
                   ahora=_a_las(20, 7))
    atascos.anotar(org_b, atascos.FASE_LECTURA, "ia_error", "caso-3", "x",
                   ahora=_a_las(28, 7))

    r = atascos.informe(empresa, dt.date(2026, 10, 27), dt.date(2026, 10, 29))

    assert r["dias_con_atascos"] == 2
    kit = next(t for t in r["por_tipo"] if t["tipo"] == "kit_sin_elegir")
    assert (kit["clase"], kit["dias"], kit["sujetos"], kit["veces"]) == (atascos.NO_DECIDE,
                                                                         2, 1, 4)
    #  Dos cuadrillas el mismo dia: UN dia, dos cosas.
    bodega = next(t for t in r["por_tipo"] if t["tipo"] == "bodega_sin_elegir")
    assert (bodega["dias"], bodega["sujetos"], bodega["veces"]) == (1, 2, 2)
    clases = {c["clase"]: c for c in r["por_clase"]}
    #  La labor sin kit y dos cuadrillas sin bodega: tres cosas, no cuatro filas.
    assert (clases[atascos.NO_DECIDE]["dias"], clases[atascos.NO_DECIDE]["sujetos"],
            clases[atascos.NO_DECIDE]["veces"]) == (2, 3, 6)
    assert (clases[atascos.IA]["sujetos"], clases[atascos.IA]["veces"]) == (1, 1)
    assert [c["clase"] for c in r["por_clase"]] == [atascos.NO_DECIDE, atascos.IA]


# ---------------------------------------------------------------------------
# R · el reparto
# ---------------------------------------------------------------------------

def test_r_el_reparto_anota_lo_que_no_pudo_ubicar_aunque_este_en_sombra(empresa, monkeypatch):
    from operaciones import publicacion_del_reparto as pub

    detalle = {"cabe": {}, "sobrantes": ["o-3"], "sin_cuadrilla": ["o-2"], "sin_zona": ["o-4"],
               "sin_clasificar": ["o-1"],
               "no_reciben": [(SimpleNamespace(cuadrilla_id="c-1"), pub.SIN_CUENTA),
                              (SimpleNamespace(cuadrilla_id="c-2"), pub.AUSENTE)]}
    monkeypatch.setattr(pub, "cuando", lambda org, ahora: (dt.date(2026, 10, 28), "", ""))
    monkeypatch.setattr(pub, "propuesta", lambda org, hoy, ahora: {
        "asignaciones": [], "trabajan_hoy": set(), "publicaria": 0, "libera": 0,
        "sobrantes": 1, "sin_cuadrilla": 1, "sin_zona": 1, "sin_nadie_con_cuenta": 1,
        "con_ausentes": 1, "detalle": detalle})

    r = pub.publicar_el_reparto(empresa, _a_las(28, 6))["reparto_del_dia"]

    assert r["modo"] == pub.SOMBRA
    assert {(a.fase, a.tipo, a.sujeto) for a in _filas(empresa)} == {
        ("reparto del dia", "orden_sin_labor", "o-1"),
        ("reparto del dia", "orden_sin_cuadrilla", "o-2"),
        ("reparto del dia", "orden_sobrante", "o-3"),
        ("reparto del dia", "orden_sin_zona", "o-4"),
        ("reparto del dia", "cuadrilla_sin_cuenta", "c-1"),
        ("reparto del dia", "cuadrilla_ausente", "c-2"),
    }
    assert {str(a.dia) for a in _filas(empresa)} == {"2026-10-28"}, "el dia de la vuelta"


# ---------------------------------------------------------------------------
# C · el ciclo
# ---------------------------------------------------------------------------

def test_c_una_fase_que_se_cae_es_un_atasco_con_su_fase(empresa, monkeypatch):
    from operaciones import supervisor as sup

    def nada(*a, **k):
        return {}

    def rompe(*a, **k):
        raise RuntimeError("se cayo con datos del cliente")

    monkeypatch.setattr(sup, "_correr_ciclo", nada)
    for fase in ("_atender_desincronizados", "_leer_tickets_abiertos",
                 "_medir_fallas_pendientes", "_pasar_a_despacho_los_que_las_reglas_habiliten",
                 "_ubicar_los_asuntos", "_crear_las_ordenes", "_publicar_el_reparto",
                 "_cargar_el_material", "_verificar_los_arreglos"):
        monkeypatch.setattr(sup, fase, nada)
    monkeypatch.setattr(sup, "retirar_alertas_de_casos_en_despacho", lambda *a, **k: 0)
    monkeypatch.setattr(sup, "_armar_la_jornada_del_dia", rompe)

    resumen = sup.correr_ciclo(empresa, _a_las(28, 7))

    assert resumen["fases_que_fallaron"] == [{"fase": "armado de la jornada del dia",
                                              "error": "RuntimeError"}]
    (a,) = _filas(empresa)
    assert (a.fase, a.tipo, a.sujeto, a.motivo) == ("ciclo", "fase_caida",
                                                    "armado de la jornada del dia",
                                                    "RuntimeError")


# ---------------------------------------------------------------------------
# K · el comando
# ---------------------------------------------------------------------------

def test_k_el_comando_imprime_por_clase_y_por_tipo(empresa):
    from django.utils import timezone

    ahora = timezone.now()
    for labor in ("trabajos", "trabajos", "obras"):
        atascos.anotar(empresa, atascos.FASE_MATERIAL, "kit_sin_elegir", labor,
                       "ningún kit se parece a «Trabajos»: no carga material", ahora=ahora)

    salida = io.StringIO()
    call_command("informe_de_atascos", org=str(empresa.id), dias=3, stdout=salida)
    texto = salida.getvalue()

    assert "1 de 3 días con atascos" in texto
    assert "la regla no sabe decidir" in texto
    assert ("[no_decide] material del dia · kit_sin_elegir · ningún kit se parece a "
            "«Trabajos»: no carga material") in texto
    assert "días 1 · cosas 2 · vueltas 3" in texto


def test_k2_sin_nada_anotado_lo_dice(empresa):
    salida = io.StringIO()
    call_command("informe_de_atascos", org=str(empresa.id), stdout=salida)
    assert "Nada anotado en esos días." in salida.getvalue()
