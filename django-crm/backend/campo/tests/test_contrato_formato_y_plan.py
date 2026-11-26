# -*- coding: utf-8 -*-
"""Como quedan escritos los datos del contrato, y que plan es (25/11/2026).

Las reglas, solas: sin pantalla, sin base. Que lleguen hasta el contrato lo
afirma `test_contrato_de_servicio.py` (secciones F, G y H), atravesando la API.

  A  EL DOCUMENTO, EL TELEFONO Y EL CORREO
  B  EL BARRIO PEGADO A LA DIRECCION -- una vez, aunque pase dos
  C  EL CLIENTE ENTERO -- con las costumbres de la empresa y sin ellas
  D  QUE PLAN ES -- uno solo o ninguno, nunca «el mas parecido»
  E  LOS SERVIDORES DEL PLAN Y EL DEL CORTE
  F  EL CATALOGO -- lo que dice el motor; y sin motor, None
"""
from types import SimpleNamespace

import pytest

from campo import contrato_formato as formato
from campo import contrato_plan as planes

CATALOGO = [
    {"nombre": "PLAN ELITE", "zonas": [20053, 20049]},
    {"nombre": "PLAN ULTRA", "zonas": [20053, 20049]},
    {"nombre": "PLAN FAMILIA", "zonas": [20053, 20049]},
    {"nombre": "PLAN HOGAR", "zonas": [20053, 20049]},
    {"nombre": "PLAN FIBRA OPTICA 200MB SV", "zonas": [32278]},
    {"nombre": "PLAN FIBRA OPTICA 150MB_SB", "zonas": [32278]},
]
SERVIDORES = [{"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"},
              {"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1"},
              {"id_zona": 32278, "nombre": "SERVIDOR SABANAGRANDE"}]
COSTUMBRES = {"datos_en_mayusculas": True, "barrio_en_la_direccion": True,
              "digitos_del_telefono": 10}


# =========================================================================== #
#  A. EL DOCUMENTO, EL TELEFONO Y EL CORREO
# =========================================================================== #
@pytest.mark.parametrize("crudo,tipo,esperado", [
    ("1.043.000.000", "CC", "1043000000"),
    ("CC 1.043.000.000", "CC", "1043000000"),          # «sin el CC»
    ("C.C. 1043000000 de Soledad", "CC", "1043000000"),
    (" 1043 000 000 ", "", "1043000000"),
    ("1043000000", "CC", "1043000000"),
    ("", "CC", ""),
    ("sin documento", "CC", ""),                       # no se inventa uno
    ("ab-123.456", "Pasaporte", "AB123456"),           # un pasaporte SI lleva letras
    ("ab 123456", "PA", "AB123456"),
])
def test_a1_el_documento_queda_solo(crudo, tipo, esperado):
    assert formato.documento(crudo, tipo) == esperado


@pytest.mark.parametrize("crudo,digitos,esperado", [
    ("+57 300 555 0101", 10, "3005550101"),            # sin el indicativo
    ("573005550101", 10, "3005550101"),
    ("(300) 555-0101", 10, "3005550101"),
    ("3005550101", 10, "3005550101"),
    ("300 555 0101 / 301 555 0202", 10, "3005550101"),  # dos numeros: el PRIMERO
    ("3005550101 3015550202", 10, "3005550101"),        # pegados: tambien el primero
    ("5550101", 10, "5550101"),                         # mas corto: se deja
    ("+57 300 555 0101", 0, "573005550101"),            # 0 = no recortar
    ("", 10, ""),
])
def test_a2_el_telefono_queda_con_los_digitos_del_pais(crudo, digitos, esperado):
    assert formato.telefono(crudo, digitos) == esperado


def test_a3_el_telefono_de_dos_numeros_NO_devuelve_el_segundo():
    """EL CONTROL: «los ultimos 10» de dos numeros pegados es el SEGUNDO.
    Si esta prueba pasara con `[-10:]`, no estaria probando nada."""
    crudo = "300 555 0101 / 301 555 0202"
    solo_digitos = "".join(ch for ch in crudo if ch.isdigit())
    assert solo_digitos[-10:] == "3015550202", "la trampa existe"
    assert formato.telefono(crudo, 10) != "3015550202"


def test_a4_el_correo_va_en_minusculas_y_sin_espacios():
    assert formato.correo("  Laura.Pineda@Example.COM ") == "laura.pineda@example.com"
    assert formato.correo("") == ""


# =========================================================================== #
#  B. EL BARRIO PEGADO A LA DIRECCION
# =========================================================================== #
def test_b1_el_barrio_va_pegado_al_final():
    assert (formato.direccion_con_barrio("CRA 3B # 54-20", "VILLA DEL SOL")
            == "CRA 3B # 54-20 VILLA DEL SOL")


@pytest.mark.parametrize("ya_pegada", [
    "CRA 3B # 54-20 VILLA DEL SOL",
    "CRA 3B # 54-20, Villa del Sol",          # con coma y otra escritura
    "CRA 3B # 54-20 - VILLA DEL SÓL",         # con tilde de mas
])
def test_b2_UNA_SOLA_VEZ_aunque_ya_viniera_pegado(ya_pegada):
    """El telefono devuelve la direccion del borrador, que ya lo trae. Pegarlo
    otra vez es «... VILLA DEL SOL VILLA DEL SOL» en un contrato firmado."""
    r = formato.direccion_con_barrio(ya_pegada, "VILLA DEL SOL")
    assert r == "CRA 3B # 54-20 VILLA DEL SOL"
    assert formato.direccion_con_barrio(r, "VILLA DEL SOL") == r, "y otra pasada da lo mismo"


def test_b3_si_el_tecnico_CORRIGE_el_barrio_el_viejo_no_se_queda():
    r = formato.direccion_con_barrio("CRA 3B # 54-20 VILLA DEL SOL", "LAS NIEVES",
                                     barrio_anterior="VILLA DEL SOL")
    assert r == "CRA 3B # 54-20 LAS NIEVES"


def test_b4_sin_barrio_la_direccion_queda_como_estaba():
    assert formato.direccion_con_barrio("CRA 3B # 54-20", "") == "CRA 3B # 54-20"


def test_b5_una_direccion_que_ES_el_barrio_no_queda_vacia_ni_doble():
    assert formato.direccion_con_barrio("VILLA DEL SOL", "VILLA DEL SOL") == "VILLA DEL SOL"


def test_b6_saber_si_la_direccion_ya_lo_trae():
    assert formato.direccion_ya_trae_el_barrio("CRA 3B # 54-20 VILLA DEL SOL", "Villa del Sol")
    assert not formato.direccion_ya_trae_el_barrio("CRA 3B # 54-20", "VILLA DEL SOL")
    assert not formato.direccion_ya_trae_el_barrio("CRA 3B # 54-20", "")


# =========================================================================== #
#  C. EL CLIENTE ENTERO
# =========================================================================== #
CLIENTE = {"nombre": " laura  marcela ", "apellido": "Pineda Ortega",
           "tipo_documento": "cc", "numero_documento": "CC 1.234.500.001",
           "telefono": "+57 300 555 0101", "correo": "Laura.Pineda@Example.com",
           "direccion": "Cra 3B # 54-20", "barrio": "Villa del Sol"}


def test_c1_con_las_costumbres_de_la_empresa_queda_como_ella_lo_escribe():
    c = formato.cliente_con_formato(CLIENTE, COSTUMBRES)
    assert c == {"nombre": "LAURA MARCELA", "apellido": "PINEDA ORTEGA",
                 "tipo_documento": "CC", "numero_documento": "1234500001",
                 "telefono": "3005550101", "correo": "laura.pineda@example.com",
                 "direccion": "CRA 3B # 54-20 VILLA DEL SOL", "barrio": "VILLA DEL SOL"}


def test_c2_SIN_costumbres_no_se_le_impone_el_formato_de_otra_empresa():
    """Mayusculas, barrio pegado y recorte de telefono son de UNA empresa. Otra
    que no las cargo conserva su escritura; lo que no varia (documento solo
    numeros, correo en minusculas) se hace igual."""
    c = formato.cliente_con_formato(CLIENTE, formato.SIN_COSTUMBRES)
    assert c["nombre"] == "laura marcela" and c["apellido"] == "Pineda Ortega"
    assert c["direccion"] == "Cra 3B # 54-20" and c["barrio"] == "Villa del Sol"
    assert c["telefono"] == "573005550101"
    assert c["numero_documento"] == "1234500001"
    assert c["correo"] == "laura.pineda@example.com"


def test_c3_pasarlo_DOS_VECES_da_lo_mismo():
    una = formato.cliente_con_formato(CLIENTE, COSTUMBRES)
    dos = formato.cliente_con_formato(una, COSTUMBRES, barrio_anterior=una["barrio"])
    assert dos == una


def test_c4_no_cambia_el_diccionario_que_recibe():
    original = dict(CLIENTE)
    formato.cliente_con_formato(CLIENTE, COSTUMBRES)
    assert CLIENTE == original


# =========================================================================== #
#  B2. LAS ABREVIATURAS DE LA DIRECCION
# =========================================================================== #
REGLAS = [{"como_lo_escriben": ["CLL", "CL", "CALL"], "como_queda": "CALLE"},
          {"como_lo_escriben": ["KRA", "KR", "CR", "Carrera"], "como_queda": "CRA"}]


@pytest.mark.parametrize("crudo,esperado", [
    ("cll 48 # 3A-15", "CALLE 48 # 3A-15"),
    ("Kra 12 # 40-08", "CRA 12 # 40-08"),
    ("CR. 21 # 45-12", "CRA 21 # 45-12"),            # con el punto
    ("Carrera 2 Este # 18-09", "CRA 2 Este # 18-09"),
    ("Clara 3", "Clara 3"),                          # solo palabras enteras
    ("Mz D casa 11", "Mz D casa 11"),                # lo que no esta en las reglas, igual
    ("", ""),
])
def test_b7_cada_palabra_queda_como_la_escribe_la_empresa(crudo, esperado):
    assert formato.abreviar(crudo, REGLAS) == esperado


def test_b8_abreviar_dos_veces_da_lo_mismo_y_sin_reglas_no_cambia_nada():
    una = formato.abreviar("cll 48 kra 2", REGLAS)
    assert formato.abreviar(una, REGLAS) == una == "CALLE 48 CRA 2"
    assert formato.abreviar("cll 48", []) == "cll 48"


def test_b9_el_cliente_entero_con_abreviaturas_y_barrio_pegado():
    c = formato.cliente_con_formato(
        {**CLIENTE, "direccion": "cll 54 # 3B-20", "barrio": "La Carrera"},
        {**COSTUMBRES, "abreviaturas_de_direccion": REGLAS})
    assert c["direccion"] == "CALLE 54 # 3B-20 LA CARRERA" and c["barrio"] == "LA CARRERA"


# =========================================================================== #
#  D. QUE PLAN ES
# =========================================================================== #
@pytest.mark.parametrize("texto,esperado", [
    ("PLAN FAMILIA", "PLAN FAMILIA"),                          # el nombre exacto
    ("FAMILIA 200MB - $89.900", "PLAN FAMILIA"),               # como lo trae el ticket
    ("Familia 200 megas", "PLAN FAMILIA"),
    ("plan hogar 100MB - $59.900", "PLAN HOGAR"),
    ("ELITE", "PLAN ELITE"),
    ("Ultra 400 Mb $ 119.900", "PLAN ULTRA"),
    ("FIBRA OPTICA 200MB SV", "PLAN FIBRA OPTICA 200MB SV"),
    ("200 megas SV", "PLAN FIBRA OPTICA 200MB SV"),
    ("Plan fibra óptica 150 MB SB", "PLAN FIBRA OPTICA 150MB_SB"),
])
def test_d1_reconoce_el_plan_por_lo_que_lo_distingue(texto, esperado):
    assert planes.reconocer(texto, CATALOGO)["nombre"] == esperado


@pytest.mark.parametrize("texto", [
    "Fibra 300 Mb",                 # no es de nadie
    "FIBRA OPTICA",                 # es de dos
    "200MB",                        # la velocidad sola no nombra un plan
    "HOGAR o FAMILIA",              # nombra dos
    "$89.900",                      # un precio solo
    "",
])
def test_d2_si_no_es_UNO_SOLO_no_adivina(texto):
    assert planes.reconocer(texto, CATALOGO) is None


def test_d3_EL_PRECIO_NO_ELIGE_el_plan():
    """EL CONTROL de d1: «FAMILIA 200MB» trae la velocidad del plan de SV. Si
    la regla contara coincidencias sueltas, empataria o ganaria el otro."""
    r = planes.reconocer("FAMILIA 200MB - $89.900", CATALOGO)
    assert r["nombre"] == "PLAN FAMILIA" and r["zonas"] == [20053, 20049]


def test_d4_un_plan_y_su_promocion_no_se_confunden():
    catalogo = [{"nombre": "PLAN HOGAR", "zonas": [1]},
                {"nombre": "PLAN HOGAR PROMO", "zonas": [2]}]
    assert planes.reconocer("HOGAR PROMO 100MB", catalogo)["nombre"] == "PLAN HOGAR PROMO"
    assert planes.reconocer("HOGAR 100MB", catalogo)["nombre"] == "PLAN HOGAR"


@pytest.mark.parametrize("catalogo", [None, []])
def test_d5_sin_catalogo_no_reconoce_nada(catalogo):
    assert planes.reconocer("PLAN FAMILIA", catalogo) is None


def test_d6_el_plan_y_el_corte_salen_del_ticket_cuando_no_hay_solicitud():
    orden = SimpleNamespace(caso=SimpleNamespace(description=(
        "Instalacion Nueva - Laura Pineda | Tel: 3005550101 | Cra 3B # 54-20, VILLA DEL SOL"
        " | Doc: CC 1234500001 | Plan: FAMILIA 200MB - $89.900 | Corte: CORTE 30"
        " | Medio: UN VECINO | Solicitud N° 003651")))
    assert planes.dato_del_ticket(orden, "Plan") == "FAMILIA 200MB - $89.900"
    assert planes.dato_del_ticket(orden, "Corte") == "CORTE 30"
    assert planes.dato_del_ticket(orden, "Vlan") == ""
    assert planes.dato_del_ticket(SimpleNamespace(caso=None), "Plan") == ""


def test_d7_una_etiqueta_que_solo_TERMINA_igual_no_se_confunde():
    """«Explan: X» no es «Plan: X»: la etiqueta empieza donde empieza un campo."""
    orden = SimpleNamespace(caso=SimpleNamespace(description="Nota | Subplan: OTRO | Corte: 15"))
    assert planes.dato_del_ticket(orden, "Plan") == ""


# =========================================================================== #
#  E. LOS SERVIDORES DEL PLAN Y EL DEL CORTE
# =========================================================================== #
def test_e1_un_plan_de_corte_ofrece_sus_dos_servidores_y_no_el_tercero():
    r = planes.servidores_del_plan(CATALOGO[2], SERVIDORES)
    assert [s["id_zona"] for s in r] == [20053, 20049]


def test_e2_un_plan_de_un_solo_servidor_ofrece_uno():
    r = planes.servidores_del_plan(CATALOGO[4], SERVIDORES)
    assert [s["id_zona"] for s in r] == [32278]


def test_e3_sin_plan_reconocido_se_ofrecen_todos():
    assert planes.servidores_del_plan(None, SERVIDORES) == SERVIDORES


def test_e4_un_plan_sin_zonas_va_en_cualquiera():
    assert planes.servidores_del_plan({"nombre": "X", "zonas": []}, SERVIDORES) == SERVIDORES


def test_e5_si_la_empresa_NO_CARGO_el_servidor_del_plan_no_se_ofrecen_los_otros():
    """Falla cerrado: ofrecer «los que hay» es dejar que un cliente quede
    creado en un servidor donde su plan no va."""
    solo_cortes = SERVIDORES[:2]
    assert planes.servidores_del_plan(CATALOGO[4], solo_cortes) == []


@pytest.mark.parametrize("corte,esperado", [
    ("CORTE 30", 20049),
    ("CORTE 15", 20053),
    ("corte 30", 20049),
    ("30", 20049),
    ("Sabanagrande", 32278),
    ("CORTE 20", None),             # ninguno
    ("CORTE", None),                # los dos
    ("1", None),                    # «SERVIDOR 1» esta en los dos
    ("", None),
])
def test_e6_el_corte_del_ticket_sugiere_un_servidor_solo_si_es_uno(corte, esperado):
    assert planes.servidor_del_corte(corte, SERVIDORES) == esperado


# =========================================================================== #
#  F. EL CATALOGO
# =========================================================================== #
class _Respuesta:
    def __init__(self, cuerpo, ok=True, estado=200):
        self._cuerpo, self.ok, self.status_code = cuerpo, ok, estado

    def json(self):
        if isinstance(self._cuerpo, Exception):
            raise self._cuerpo
        return self._cuerpo


@pytest.fixture(autouse=True)
def _sin_catalogo_recordado():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _con_motor(monkeypatch, respuesta, pedidos=None):
    def _get(url, **kw):
        if pedidos is not None:
            pedidos.append((url, kw.get("params")))
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(planes.requests, "get", _get)


def test_f1_el_catalogo_es_lo_que_la_empresa_vende_segun_el_motor(
        org_a, empresa_del_motor, monkeypatch):
    empresa_del_motor(org_a, "empresa-uno")
    pedidos = []
    _con_motor(monkeypatch, _Respuesta({"planes_venta": [
        {"nombre_wisphub": "PLAN FAMILIA", "zonas": [20053, 20049]},
        {"nombre_wisphub": "PLAN FAMILIA", "zonas": [1]},          # repetido: se ignora
        {"nombre_wisphub": "", "zonas": [2]},                      # sin nombre: se ignora
        {"nombre_wisphub": "PLAN LIBRE", "zonas": []},
    ]}), pedidos)

    assert planes.catalogo_de(org_a) == [
        {"nombre": "PLAN FAMILIA", "zonas": [20053, 20049]},
        {"nombre": "PLAN LIBRE", "zonas": []}]
    assert pedidos[0][0].endswith("/configuracion/planes-venta")
    assert pedidos[0][1] == {"tenant": "empresa-uno"}, "el de ESA organización, no otro"


def test_f2_sin_empresa_en_el_motor_no_pregunta_y_no_sabe(org_a, monkeypatch):
    pedidos = []
    _con_motor(monkeypatch, _Respuesta({"planes_venta": [{"nombre_wisphub": "X"}]}), pedidos)
    assert planes.catalogo_de(org_a) is None
    assert pedidos == [], "sin saber de qué empresa es, no se le pide nada al motor"


@pytest.mark.parametrize("respuesta", [
    ConnectionError("sin red"),
    _Respuesta({}, ok=False, estado=500),
    _Respuesta(ValueError("no es json")),
])
def test_f3_si_el_motor_no_contesta_es_None_y_no_una_lista_vacia(
        org_a, empresa_del_motor, monkeypatch, respuesta):
    """None = «no se pudo saber». Una lista vacia diria «no vende ninguno», y
    quien firma trataria igual las dos cosas por error."""
    empresa_del_motor(org_a, "empresa-uno")
    _con_motor(monkeypatch, respuesta)
    assert planes.catalogo_de(org_a) is None


def test_f4_una_falla_NO_se_recuerda(org_a, empresa_del_motor, monkeypatch):
    """Si el motor fallo una vez, la siguiente pregunta vuelve a preguntar."""
    empresa_del_motor(org_a, "empresa-uno")
    _con_motor(monkeypatch, ConnectionError("sin red"))
    assert planes.catalogo_de(org_a) is None
    _con_motor(monkeypatch, _Respuesta({"planes_venta": [{"nombre_wisphub": "PLAN A"}]}))
    assert planes.catalogo_de(org_a) == [{"nombre": "PLAN A", "zonas": []}]


def test_f5_el_catalogo_de_una_empresa_no_se_le_da_a_otra(
        org_a, org_b, empresa_del_motor, monkeypatch):
    empresa_del_motor(org_a, "empresa-uno")
    empresa_del_motor(org_b, "empresa-dos")
    por_empresa = {"empresa-uno": [{"nombre_wisphub": "PLAN DE UNO"}],
                   "empresa-dos": [{"nombre_wisphub": "PLAN DE DOS"}]}
    monkeypatch.setattr(planes.requests, "get", lambda url, **kw: _Respuesta(
        {"planes_venta": por_empresa[kw["params"]["tenant"]]}))

    assert planes.catalogo_de(org_a)[0]["nombre"] == "PLAN DE UNO"
    assert planes.catalogo_de(org_b)[0]["nombre"] == "PLAN DE DOS", \
        "recordar el de la primera no puede contestarle a la segunda"
