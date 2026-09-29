# -*- coding: utf-8 -*-
"""
El lazo con el ISP: el serial instalado vuelve a WispHub.

LO QUE ESTAS PRUEBAS DEFIENDEN, y por que cada una
--------------------------------------------------
Este es el unico efecto EXTERNO del modulo de inventario: sale de Dexter y
escribe en el sistema de otra empresa. Las propiedades que hay que garantizar no
son las de un CRUD:

  APAGADO POR OMISION       falta una medicion grave --si el PUT parcial vacia
                            los demas campos del cliente-- y hasta entonces esto
                            NO sale a la red. La prueba lo comprueba, no lo
                            supone
  NUNCA REVIERTE            un fallo al avisar no puede tumbar el consumo. El
                            material se gasto en la calle y el registro tiene que
                            quedar: convertir un problema de red en material
                            perdido es peor que no avisar
  TRES DESENLACES           avisado / no correspondia / no se pudo. "No se pudo"
                            no es "no hacia falta", y un booleano los aplastaria
  SIN ADIVINAR EL CLIENTE   sin el id del cliente en el ISP no se escribe. Elegir
                            uno "parecido" seria escribirle al cliente equivocado
  CLAVE ESTABLE             derivada del movimiento. Un uuid por intento es un
                            identificador unico, no una clave idempotente

Y una que parece de detalle: el texto de una excepcion de red NO va al log,
porque trae la URL y la URL trae el id del cliente. Va el tipo.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from campo.inventario import UbicacionInventario
from campo.models import MaterialCatalogo, MovimientoDeMaterial, OrdenTrabajo
from campo.models import WorkType, WorkTypeVersion
from campo.services import inventario as inv
from campo.services import lazo_isp

pytestmark = pytest.mark.django_db


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


@pytest.fixture
def ont(org_a):
    return MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT-HG8145", nombre="ONT Huawei",
        clase=MaterialCatalogo.SERIALIZADO,
    )


@pytest.fixture
def orden_con_cliente(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="Instalacion")
    ver = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={}
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=ver,
        cliente_nombre="Cliente Prueba", cliente_direccion="Calle 1",
        cliente_id_abonado="5832",
    )


@pytest.fixture
def orden_sin_cliente(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth2", nombre="Instalacion 2")
    ver = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={}
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=7002, tipo_trabajo_version=ver,
        cliente_nombre="Sin abonado", cliente_direccion="Calle 2",
    )


def _consumo(org, material, orden, *, serie="HWT-INST-1",
             estado=MovimientoDeMaterial.ACEPTADO,
             tipo=MovimientoDeMaterial.CONSUMO):
    return MovimientoDeMaterial.objects.create(
        org=org, material=material, orden=orden, tipo=tipo,
        cantidad=Decimal("1"), serie=serie, estado=estado,
        idempotency_key=f"prueba-{serie}-{tipo}-{estado}",
    )


# ---------------------------------------------------------------------------
# Apagado por omisión
# ---------------------------------------------------------------------------

def test_apagado_por_omision_no_sale_a_la_red(org_a, ont, orden_con_cliente,
                                              monkeypatch):
    """Falta una medición grave, y hasta entonces esto no llama a nadie."""
    monkeypatch.delenv(lazo_isp.BANDERA, raising=False)
    mov = _consumo(org_a, ont, orden_con_cliente)

    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)

    assert r.estado == lazo_isp.ResultadoAviso.APAGADO
    post.assert_not_called()
    # El detalle dice QUÉ falta, no solo que está apagado: quien lo lea tiene que
    # poder saber qué hay que hacer para encenderlo.
    assert "PUT parcial" in r.detalle


def test_un_valor_que_no_es_uno_exacto_deja_apagado(org_a, ont,
                                                    orden_con_cliente,
                                                    monkeypatch):
    """`"true"`, `"si"` o `"0"` no encienden nada. Mismo criterio que
    RECONCILIADOR_HABILITADO: la bandera vale exactamente "1"."""
    for valor in ("true", "si", "yes", "0", "", "2"):
        monkeypatch.setenv(lazo_isp.BANDERA, valor)
        mov = _consumo(org_a, ont, orden_con_cliente,
                       serie=f"HWT-{valor or 'vacio'}")
        with patch("requests.post") as post:
            r = lazo_isp.intentar_avisar(mov)
        assert r.estado == lazo_isp.ResultadoAviso.APAGADO, valor
        post.assert_not_called()


# ---------------------------------------------------------------------------
# Qué se avisa y qué no
# ---------------------------------------------------------------------------

def test_un_consumo_aceptado_con_serie_y_cliente_se_avisa(
    org_a, ont, orden_con_cliente, monkeypatch
):
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente)

    with patch("requests.post") as post:
        post.return_value.status_code = 200
        r = lazo_isp.intentar_avisar(mov)

    assert r.salio, r.detalle
    llamada = post.call_args
    assert "/interno/herramienta/actualizar_sn_onu" in llamada.args[0]
    assert llamada.kwargs["json"] == {"id_servicio": "5832",
                                      "sn_onu": "HWT-INST-1"}
    # La clave idempotente viaja, y es estable.
    assert llamada.kwargs["headers"]["Idempotency-Key"] == \
        lazo_isp.clave_idempotente(mov)


def test_una_devolucion_no_se_avisa(org_a, ont, orden_con_cliente, monkeypatch):
    """Devolver un equipo no cambia qué tiene el cliente."""
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente,
                   tipo=MovimientoDeMaterial.DEVOLUCION)
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    post.assert_not_called()


def test_un_descuadre_no_se_avisa(org_a, ont, orden_con_cliente, monkeypatch):
    """Está sin explicar: avisarle al ISP de un dato sin explicar es propagarlo."""
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente,
                   estado=MovimientoDeMaterial.DESCUADRE)
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    assert "descuadre" in r.detalle
    post.assert_not_called()


def test_un_conflicto_no_se_avisa(org_a, ont, orden_con_cliente, monkeypatch):
    """Por definición no ocurrió: otro ya había consumido esa serie."""
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente,
                   estado=MovimientoDeMaterial.CONFLICTO)
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    post.assert_not_called()


def test_un_consumo_sin_serie_no_se_avisa(org_a, ont, orden_con_cliente,
                                          monkeypatch):
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente, serie="")
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    assert "no hay aparato" in r.detalle
    post.assert_not_called()


def test_sin_el_cliente_del_isp_NO_se_adivina(org_a, ont, orden_sin_cliente,
                                              monkeypatch):
    """La propiedad más peligrosa de todas.

    Sin el id del cliente en el ISP no hay a quién escribirle, y elegir uno
    «parecido» sería escribirle al cliente equivocado. Se nombra y no se sale.
    """
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_sin_cliente, serie="HWT-SIN-CLIENTE")
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    assert "a que cliente del ISP corresponde" in r.detalle
    post.assert_not_called()


def test_un_consumo_sin_orden_no_se_avisa(org_a, ont, monkeypatch):
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = MovimientoDeMaterial.objects.create(
        org=org_a, material=ont, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), serie="HWT-SIN-ORDEN",
        idempotency_key="prueba-sin-orden",
    )
    with patch("requests.post") as post:
        r = lazo_isp.intentar_avisar(mov)
    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    post.assert_not_called()


# ---------------------------------------------------------------------------
# Qué pasa cuando falla
# ---------------------------------------------------------------------------

def test_un_fallo_de_red_no_lanza_y_no_revierte_nada(
    org_a, ont, orden_con_cliente, monkeypatch
):
    """La propiedad que evita que un problema de red borre inventario."""
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente)

    with patch("requests.post", side_effect=OSError("timeout")):
        r = lazo_isp.intentar_avisar(mov)

    assert r.estado == lazo_isp.ResultadoAviso.FALLO
    # El movimiento sigue ahí, intacto: el consumo ocurrió en la calle.
    mov.refresh_from_db()
    assert mov.estado == MovimientoDeMaterial.ACEPTADO
    assert MovimientoDeMaterial.objects.filter(id=mov.id).exists()


def test_el_409_del_interruptor_no_es_un_fallo(org_a, ont, orden_con_cliente,
                                               monkeypatch):
    """«No se hizo a propósito» y «falló» piden reacciones distintas.

    El motor devuelve 409 cuando la autonomía está detenida. Contarlo como fallo
    haría que alguien investigara una red que está perfecta.
    """
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente)

    with patch("requests.post") as post:
        post.return_value.status_code = 409
        r = lazo_isp.intentar_avisar(mov)

    assert r.estado == lazo_isp.ResultadoAviso.NO_CORRESPONDE
    assert "detenidas" in r.detalle


def test_el_detalle_de_un_fallo_de_red_no_trae_el_texto_de_la_excepcion(
    org_a, ont, orden_con_cliente, monkeypatch
):
    """El texto de una excepción de red trae la URL, y la URL el id del cliente."""
    monkeypatch.setenv(lazo_isp.BANDERA, "1")
    mov = _consumo(org_a, ont, orden_con_cliente)

    with patch("requests.post",
               side_effect=OSError("https://api.wisphub.io/api/clientes/5832/")):
        r = lazo_isp.intentar_avisar(mov)

    assert r.detalle == "OSError"
    assert "5832" not in r.detalle
    assert "wisphub" not in r.detalle.lower()


# ---------------------------------------------------------------------------
# La clave idempotente
# ---------------------------------------------------------------------------

def test_la_clave_es_estable_entre_llamadas(org_a, ont, orden_con_cliente):
    """Dos veces el mismo movimiento, la misma clave. Eso es lo que la hace
    idempotente y no solo única."""
    mov = _consumo(org_a, ont, orden_con_cliente)
    assert lazo_isp.clave_idempotente(mov) == lazo_isp.clave_idempotente(mov)


def test_dos_movimientos_distintos_tienen_claves_distintas(
    org_a, ont, orden_con_cliente
):
    uno = _consumo(org_a, ont, orden_con_cliente, serie="HWT-A")
    otro = _consumo(org_a, ont, orden_con_cliente, serie="HWT-B")
    assert lazo_isp.clave_idempotente(uno) != lazo_isp.clave_idempotente(otro)


def test_la_clave_cabe_en_el_campo_de_idempotencia(org_a, ont,
                                                   orden_con_cliente):
    """El mismo límite que ya se cobró una vez en este módulo.

    `idempotency_key` es varchar(128) y la primera versión de la clave del
    inventario no cabía. Acá la clave viaja en una cabecera HTTP, pero el motor la
    guarda en `asistente.operaciones_externas.clave`, así que el límite importa
    igual.
    """
    mov = _consumo(org_a, ont, orden_con_cliente)
    assert len(lazo_isp.clave_idempotente(mov)) <= 128
