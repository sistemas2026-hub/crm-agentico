# -*- coding: utf-8 -*-
"""
El ciclo del inventario: entrada -> bodega -> tecnico -> devolucion -> bodega.

QUE CUIDAN ESTAS PRUEBAS
------------------------
El modulo de materiales estaba construido desde la mitad hacia adelante: sabia
que hacer con el material que el tecnico YA tenia, y no habia forma de que lo
tuviera. Estas pruebas cubren el extremo que faltaba, y las tres que mas
importan son:

  A3  una serie devuelta se puede volver a despachar.
      Antes NO se podia, nunca: `ItemDeKit` tenia `unique(material, serie)`
      absoluto, asi que una ONT que volvia intacta de un cliente que cancelo
      quedaba inutilizable. Su propio comentario decia "sin haber vuelto" y la
      condicion no modelaba el haber vuelto.

  A4  una serie no puede estar en dos custodias a la vez.
      Es una invariante TEMPORAL --dos salidas consecutivas sin una entrada en
      medio-- y por eso no se expresa con un UniqueConstraint sobre el libro.
      La da `UbicacionDeActivo`, con una fila por activo.

  A5  RECONCILIACION: el puntero coincide con el libro.
      Es la que hace legitimo a `UbicacionDeActivo`. Este proyecto prohibe
      guardar un derivado; la excepcion se aceptó porque un puntero al presente
      es reconstruible y por lo tanto verificable. Sin esta prueba, esa tabla es
      un contador guardado con otro nombre y la prohibicion valia.

Y una que parece menor y no lo es: que la existencia de una bodega y el saldo de
un tecnico salgan de LA MISMA funcion. Es la propiedad que motivo descartar los
dos libros, y la unica forma de que no vuelva por la ventana.
"""

from decimal import Decimal

import pytest

from campo.inventario import ActivoSerializado, UbicacionDeActivo, UbicacionInventario
from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services import inventario as inv

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def otra_bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Norte"
    )


@pytest.fixture
def conector(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="CON-SC-APC", nombre="Conector SC/APC",
        clase=MaterialCatalogo.CONSUMIBLE, unidad="unidades",
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei HG8145V5",
        clase=MaterialCatalogo.SERIALIZADO, unidad="unidades",
    )


@pytest.fixture
def tecnico(user_profile):
    return user_profile


@pytest.fixture
def otro_tecnico(org_a, django_user_model):
    from common.models import Profile
    user = django_user_model.objects.create_user(
        email="tecnico2@test.com", password="testpass123"
    )
    return Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


# ---------------------------------------------------------------------------
# La existencia sale de UNA funcion, y sirve para cualquier ubicacion
# ---------------------------------------------------------------------------

def test_una_entrada_deja_existencia_en_la_bodega(org_a, bodega, conector):
    assert inv.existencia(bodega, conector) == Decimal("0")

    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100,
        ubicacion_destino=bodega, origen_ref="FAC-001",
    )

    assert inv.existencia(bodega, conector) == Decimal("100")


def test_la_entrada_no_tiene_origen_y_eso_es_la_frontera(org_a, bodega, conector):
    """Un null que significa algo: el material entra al sistema."""
    mov = inv.registrar_entrada(
        org=org_a, material=conector, cantidad=50, ubicacion_destino=bodega,
    )
    assert mov.ubicacion_origen is None
    assert mov.ubicacion_destino_id == bodega.id
    assert mov.tipo == MovimientoDeMaterial.ENTRADA


def test_despachar_mueve_la_existencia_de_la_bodega_al_tecnico(
    org_a, bodega, conector, tecnico
):
    """El numero que baja de un lado es el MISMO que sube del otro."""
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )

    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": conector, "cantidad": 30}], acta="K-001",
    )

    custodia = inv.ubicacion_de_tecnico(tecnico, org_a, crear=False)
    assert inv.existencia(bodega, conector) == Decimal("70")
    assert inv.existencia(custodia, conector) == Decimal("30")


def test_la_devolucion_vuelve_a_sumar_en_la_bodega(
    org_a, bodega, conector, tecnico
):
    """Lo que faltaba del ciclo: antes el material devuelto no volvia a existir."""
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": conector, "cantidad": 30}],
    )
    antes_bodega = inv.existencia(bodega, conector)

    inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 12}],
    )

    custodia = inv.ubicacion_de_tecnico(tecnico, org_a, crear=False)
    assert antes_bodega == Decimal("70")
    assert inv.existencia(bodega, conector) == Decimal("82")
    assert inv.existencia(custodia, conector) == Decimal("18")


def test_la_existencia_puede_ser_negativa_y_se_ve(org_a, bodega, conector):
    """Un negativo es justo lo que hay que poder ver, no lo que hay que tapar."""
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=10, ubicacion_destino=bodega,
    )
    MovimientoDeMaterial.objects.create(
        org=org_a, material=conector, tipo=MovimientoDeMaterial.BAJA,
        cantidad=Decimal("25"), ubicacion_origen=bodega,
        idempotency_key="baja-de-prueba",
    )
    assert inv.existencia(bodega, conector) == Decimal("-15")


# ---------------------------------------------------------------------------
# A3 -- la serie devuelta se vuelve a despachar
# ---------------------------------------------------------------------------

def test_a3_una_serie_devuelta_se_puede_volver_a_despachar(
    org_a, bodega, ont, tecnico, otro_tecnico
):
    """El defecto que el constraint viejo hacia imposible.

    Caso real: se despacha una ONT, el cliente cancela, la ONT vuelve intacta.
    Antes el segundo despacho daba IntegrityError y el aparato quedaba muerto.
    """
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="HWTCA6FB5263",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "HWTCA6FB5263"}],
    )
    inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": ont, "serie": "HWTCA6FB5263"}],
        notas="el cliente cancelo, vuelve sin instalar",
    )

    # Y ahora se le entrega a OTRA persona. Esto es lo que antes no se podia.
    entrega, movs = inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=otro_tecnico,
        lineas=[{"material": ont, "serie": "HWTCA6FB5263"}],
    )

    assert len(movs) == 1
    custodia2 = inv.ubicacion_de_tecnico(otro_tecnico, org_a, crear=False)
    assert inv.existencia(custodia2, ont) == Decimal("1")
    assert inv.existencia(bodega, ont) == Decimal("0")


# ---------------------------------------------------------------------------
# A4 -- una serie no puede estar en dos custodias
# ---------------------------------------------------------------------------

def test_a4_la_misma_serie_no_se_despacha_dos_veces_sin_devolucion(
    org_a, bodega, ont, tecnico, otro_tecnico
):
    """La garantia. Y se rechaza ANTES de escribir, porque todavia no paso."""
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="HWTCA6FB5263",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "HWTCA6FB5263"}],
    )

    with pytest.raises(inv.DespachoInvalido) as e:
        inv.despachar(
            org=org_a, ubicacion_origen=bodega, profile_destino=otro_tecnico,
            lineas=[{"material": ont, "serie": "HWTCA6FB5263"}],
        )

    # El mensaje dice DONDE esta y que hacer, no solo que no se puede.
    assert "no puede estar en dos manos" in str(e.value)
    assert "Custodia de" in str(e.value) or "custodia" in str(e.value).lower()

    # Y el rechazo no dejo basura: sigue habiendo UN despacho de esa serie.
    despachos = MovimientoDeMaterial.objects.filter(
        org=org_a, serie="HWTCA6FB5263", tipo=MovimientoDeMaterial.DESPACHO
    )
    assert despachos.count() == 1


def test_a4_una_serie_tiene_UNA_posicion(org_a, bodega, ont, tecnico):
    """Un activo, una fila. Es la garantia declarativa que da la tabla."""
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="SER-UNICA",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "SER-UNICA"}],
    )
    activo = ActivoSerializado.objects.get(org=org_a, material=ont, serie="SER-UNICA")
    assert UbicacionDeActivo.objects.filter(activo=activo).count() == 1


def test_un_serializado_sin_serie_no_se_despacha(org_a, bodega, ont, tecnico):
    """Sin el numero no se puede saber QUE aparato se entrego."""
    with pytest.raises(inv.DespachoInvalido) as e:
        inv.despachar(
            org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
            lineas=[{"material": ont, "cantidad": 1}],
        )
    assert "serializado" in str(e.value)


# ---------------------------------------------------------------------------
# A5 -- la reconciliacion, que es la que hace legitimo el puntero
# ---------------------------------------------------------------------------

def test_a5_el_puntero_coincide_con_el_libro(
    org_a, bodega, otra_bodega, ont, tecnico, otro_tecnico
):
    """Recalcula la posicion de CADA activo desde sus movimientos y compara.

    Si esta prueba no existiera, `UbicacionDeActivo` seria un dato guardado que
    nadie puede verificar -- o sea justo lo que este proyecto prohibe.
    """
    # Un ciclo largo, con varias series y varios destinos.
    for serie in ("A-1", "A-2", "A-3"):
        inv.registrar_entrada(
            org=org_a, material=ont, cantidad=1,
            ubicacion_destino=bodega, serie=serie,
        )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "A-1"},
                {"material": ont, "serie": "A-2"}],
    )
    inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=otra_bodega,
        lineas=[{"material": ont, "serie": "A-2"}],
    )
    inv.despachar(
        org=org_a, ubicacion_origen=otra_bodega, profile_destino=otro_tecnico,
        lineas=[{"material": ont, "serie": "A-2"}],
    )

    desajustes = []
    for activo in ActivoSerializado.objects.filter(org=org_a):
        guardada = inv.posicion_de(activo)
        recalculada, mov = inv.posicion_recalculada(activo)
        id_guardada = guardada.ubicacion_id if guardada else None
        id_recalc = recalculada.id if recalculada else None
        if id_guardada != id_recalc:
            desajustes.append(
                f"{activo.serie}: el indice dice {id_guardada} y el libro "
                f"dice {id_recalc}"
            )

    assert not desajustes, "el puntero no cuadra con el libro:\n" + "\n".join(desajustes)


def test_a5_cada_posicion_tiene_su_movimiento_detras(org_a, bodega, ont, tecnico):
    """Una fila sin el hecho que la justifica es un defecto detectable."""
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="CON-JUSTIFICACION",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "CON-JUSTIFICACION"}],
    )
    for pos in UbicacionDeActivo.objects.filter(activo__org=org_a):
        assert pos.movimiento_id is not None, (
            f"{pos.activo.serie} tiene posicion pero ningun movimiento la explica"
        )


# ---------------------------------------------------------------------------
# La historia de una serie: la pregunta que justifica el modulo
# ---------------------------------------------------------------------------

def test_la_historia_de_una_serie_se_lee_en_orden(
    org_a, bodega, ont, tecnico
):
    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="HIST-1", origen_ref="FAC-77",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "HIST-1"}], acta="K-9",
    )
    inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": ont, "serie": "HIST-1"}],
    )

    historia = inv.historia_de(org_a, ont, "HIST-1")
    tipos = [h["tipo"] for h in historia]
    assert tipos == ["entrada", "despacho", "devolucion"]
    assert historia[0]["desde"] is None          # entra al sistema
    assert historia[0]["hacia"] == "Bodega Central"
    assert historia[1]["desde"] == "Bodega Central"
    assert "Custodia de" in historia[1]["hacia"]
    assert historia[2]["hacia"] == "Bodega Central"


# ---------------------------------------------------------------------------
# Aislamiento por organizacion
# ---------------------------------------------------------------------------

def test_una_empresa_no_ve_el_inventario_de_otra(org_a, org_b, bodega, conector):
    """Sin esto, todo lo anterior es cosmetico."""
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    bodega_b = UbicacionInventario.objects.create(
        org=org_b, tipo=UbicacionInventario.BODEGA, nombre="Bodega de la otra"
    )
    material_b = MaterialCatalogo.objects.create(
        org=org_b, codigo="CON-SC-APC", nombre="Conector de la otra",
    )
    assert inv.existencia(bodega_b, material_b) == Decimal("0")
    assert inv.existencias_de(bodega_b) == []


# ---------------------------------------------------------------------------
# El limite del esquema, que SQLite no impone y Postgres si
# ---------------------------------------------------------------------------

def test_la_clave_idempotente_cabe_en_el_campo(org_a, bodega, ont, tecnico):
    """Un defecto que las pruebas casi no cazan, y por que esta prueba existe.

    `idempotency_key` es varchar(128). La primera version de `_clave()`
    concatenaba las partes en claro --cuatro UUID mas el prefijo, ~134
    caracteres-- y esta suite pasaba entera: corre sobre SQLite, que NO impone la
    longitud de un varchar. En PostgreSQL real revento al sembrar datos:

        DataError: value too long for type character varying(128)

    Esta prueba afirma sobre el LIMITE y no sobre el motor, asi que caza el
    defecto en cualquiera de los dos.
    """
    from campo.models import MovimientoDeMaterial as M
    largo_declarado = M._meta.get_field("idempotency_key").max_length

    inv.registrar_entrada(
        org=org_a, material=ont, cantidad=1, ubicacion_destino=bodega,
        serie="SERIE-PARA-MEDIR-LA-CLAVE", origen_ref="FAC-CON-REFERENCIA-LARGA",
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": ont, "serie": "SERIE-PARA-MEDIR-LA-CLAVE"}],
        acta="ACTA-CON-UN-NOMBRE-BASTANTE-LARGO-TAMBIEN",
    )

    largas = [
        (m.idempotency_key, len(m.idempotency_key))
        for m in M.objects.filter(org=org_a)
        if len(m.idempotency_key) > largo_declarado
    ]
    assert not largas, (
        f"hay claves mas largas que el campo ({largo_declarado}): {largas}"
    )


# ---------------------------------------------------------------------------
# F8 -- lo que falta se nombra, no se absorbe
# ---------------------------------------------------------------------------

def test_f8_recibir_menos_de_lo_esperado_abre_incidencia(
    org_a, bodega, conector, tecnico
):
    """La diferencia es un hecho aparte, con su motivo.

    Es la decision del brief §2.4: "faltan 3 conectores" y "se dañaron 3 al
    retirarlos" son cosas distintas, y absorber la diferencia en un ajuste
    silencioso borra la pregunta antes de que alguien la haga.
    """
    from campo.models import IncidenciaDeMaterial

    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": conector, "cantidad": 30}],
    )

    movs, incidencias = inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 25, "esperado": 30}],
        notas="el tecnico dice que no sabe",
    )

    assert len(incidencias) == 1, "la diferencia de 5 no abrio incidencia"
    inc = incidencias[0]
    assert inc.cantidad == Decimal("5")
    assert "se esperaban 30" in inc.motivo and "volvieron 25" in inc.motivo
    # La nota de quien recibio viaja en el motivo: sin ella la incidencia dice
    # que falta algo y no lo que se dijo en el momento.
    assert "no sabe" in inc.motivo

    # Y la devolucion registra lo que LLEGO, no lo que se esperaba: el
    # movimiento no se infla para que cuadre.
    assert len(movs) == 1 and movs[0].cantidad == Decimal("25")
    assert inv.existencia(bodega, conector) == Decimal("95")

    assert IncidenciaDeMaterial.objects.filter(org=org_a).count() == 1


def test_f8_sin_esperado_no_se_adivina_un_faltante(
    org_a, bodega, conector, tecnico
):
    """Devolver parte de lo que se tiene es legitimo y no abre nada.

    Al tecnico le quedan 5 y sigue trabajando. Abrir una incidencia por cada
    devolucion parcial es la forma mas rapida de que nadie las mire.
    """
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": conector, "cantidad": 30}],
    )
    movs, incidencias = inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 25}],
    )
    assert incidencias == []
    assert len(movs) == 1


def test_f8_devolver_todo_lo_esperado_no_abre_incidencia(
    org_a, bodega, conector, tecnico
):
    """El control de la prueba de arriba: cuando cuadra, no pasa nada."""
    inv.registrar_entrada(
        org=org_a, material=conector, cantidad=100, ubicacion_destino=bodega,
    )
    inv.despachar(
        org=org_a, ubicacion_origen=bodega, profile_destino=tecnico,
        lineas=[{"material": conector, "cantidad": 30}],
    )
    _, incidencias = inv.recibir_devolucion(
        org=org_a, profile_origen=tecnico, ubicacion_destino=bodega,
        lineas=[{"material": conector, "cantidad": 30, "esperado": 30}],
    )
    assert incidencias == []
