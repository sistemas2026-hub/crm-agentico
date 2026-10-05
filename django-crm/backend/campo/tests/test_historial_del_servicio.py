# -*- coding: utf-8 -*-
"""Las visitas anteriores al mismo servicio.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
El tecnico toca el timbre y el cliente le dice «ya llame tres veces». Hoy no
tiene con que contestar: la ficha le da el numero de ticket y nada mas, y el
propio comentario del codigo admite que ese numero «es lo que permite buscar el
historial» -- buscarlo EN OTRO LADO, o sea llamar al NOC. Es la llamada mas
frecuente de las que el tecnico enumero, y el dato ya estaba en la base.

LO QUE SE AFIRMA, Y QUE PASA SI SE ROMPE
----------------------------------------
1. **No se mezclan dos clientes.** Es la unica que puede hacer daño de verdad.
   Si el historial trajera visitas de otro abonado, el tecnico le diria al
   cliente «ya le cambiamos la ONT dos veces» cuando fue al vecino -- y el
   cliente le cree, porque se lo dice la empresa. Una respuesta equivocada es
   peor que ninguna: la otra la contesta el NOC.

2. **Sin identificador no se adivina.** Agrupar por nombre o direccion parece
   razonable y produce exactamente el defecto de arriba: «Beatriz Pinzon»,
   «BEATRIZ PINZON» y «B. Pinzon» son la misma persona, y dos «Juan Perez» no.

3. **No cruza empresas.** Dos ISPs pueden usar el mismo identificador de
   abonado, porque cada uno lo toma de SU WispHub. Sin el filtro por `org` el
   numero 1042 de una empresa traeria las visitas del 1042 de la otra.

4. **Lo que todavia no paso no es historial.** Una orden programada para el
   jueves no dice nada de lo que ya se hizo, y mostrarla como visita le haria
   contar al tecnico una vuelta que no ocurrio.

5. **Sin datos del cliente.** Son del mismo servicio que ya esta en la ficha:
   repetirlos no agrega nada y los multiplica por tres en algo que se sincroniza
   al telefono.
"""

from decimal import Decimal

import pytest

from campo.models import (
    AsignacionTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import historial_del_servicio as historial
from common.models import Profile

pytestmark = pytest.mark.django_db

ABONADO = "WH-1042"


@pytest.fixture
def tipo(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="hist_test", nombre="Reparación FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def tipo_b(org_b):
    wt = WorkType.objects.create(org=org_b, codigo="hist_test_b", nombre="Reparación FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"pasos": [], "campos": [], "evidencias": []},
    )


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.hist@test.com", password="testpass123", name="Carlos Gómez",
    )
    return Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)


_contador = [0]


def _mover(org, material, orden, tipo, cantidad, profile, serie=""):
    """Un movimiento de material con su clave idempotente propia.

    La base exige `(org, idempotency_key)` unica: el reenvio de una cola offline
    no puede duplicar un consumo. Dejarla vacia hace que el SEGUNDO movimiento de
    la prueba choque -- y el choque no aparece en SQLite con la misma forma, asi
    que esto se vio recien al correr contra PostgreSQL.
    """
    from decimal import Decimal as _D

    _contador[0] += 1
    return MovimientoDeMaterial.objects.create(
        org=org, material=material, orden=orden, tipo=tipo,
        cantidad=_D(str(cantidad)), profile=profile, serie=serie,
        idempotency_key=f"prueba-historial-{_contador[0]}",
    )


def _orden(org, version, numero, *, abonado=ABONADO, estado=OrdenTrabajo.CERRADA,
           cliente="Beatriz Pinzón", contexto=None):
    return OrdenTrabajo.objects.create(
        org=org,
        numero=numero,
        tipo_trabajo_version=version,
        cliente_nombre=cliente,
        cliente_direccion="Calle 50 # 10-20",
        cliente_telefono="+57 312 455 8901",
        cliente_id_abonado=abonado,
        estado_operativo=estado,
        contexto=contexto or {},
        revision=1,
    )


# --------------------------------------------------------------------------- #
# A. Lo que contesta
# --------------------------------------------------------------------------- #

def test_a1_devuelve_las_visitas_anteriores_a_este_servicio(org_a, tipo):
    _orden(org_a, tipo, 100)
    _orden(org_a, tipo, 101)
    actual = _orden(org_a, tipo, 102)

    visitas = historial.visitas_anteriores(actual)

    assert [v["numero"] for v in visitas] == [101, 100]


def test_a2_la_orden_actual_NO_aparece_en_su_propio_historial(org_a, tipo):
    actual = _orden(org_a, tipo, 200)

    assert historial.visitas_anteriores(actual) == []


def test_a3_se_cortan_en_tres(org_a, tipo):
    """Tres entran en la pantalla sin scroll. Un historial largo es una pantalla
    que nadie lee parado en una puerta."""
    for n in range(300, 307):
        _orden(org_a, tipo, n)
    actual = _orden(org_a, tipo, 307)

    assert len(historial.visitas_anteriores(actual)) == 3


def test_a4_dice_como_termino_en_palabras_del_tecnico(org_a, tipo):
    """`completada_campo` no le dice nada a quien esta en la puerta; «resuelto»
    si. La traduccion vive del lado del servidor para que la web y el telefono
    cuenten lo mismo."""
    _orden(org_a, tipo, 400, estado=OrdenTrabajo.CERRADA)
    _orden(org_a, tipo, 401, estado=OrdenTrabajo.CANCELADA)
    actual = _orden(org_a, tipo, 402)

    como = {v["numero"]: v["como_termino"] for v in historial.visitas_anteriores(actual)}
    assert como == {400: "resuelto", 401: "cancelado"}


def test_a5_dice_quien_fue_la_vez_pasada(org_a, tipo, tecnico):
    """Es un dato de un COMPAÑERO, no del cliente, y por eso si va: el tecnico
    que llega necesita saber a quien preguntarle. Es lo que hoy resuelve
    escribiendo al grupo."""
    anterior = _orden(org_a, tipo, 500)
    AsignacionTrabajo.objects.create(
        orden=anterior, profile=tecnico, rol="tecnico", es_principal=True
    )
    actual = _orden(org_a, tipo, 501)

    assert historial.visitas_anteriores(actual)[0]["quien"] == "Carlos Gómez"


# --------------------------------------------------------------------------- #
# B. Que material se uso, y si se cambio el equipo
# --------------------------------------------------------------------------- #

def test_b0_un_numero_entero_no_se_muestra_con_ceros_de_relleno():
    """La guarda del formato, sin base.

    Separada a proposito: es la que explica POR QUE existe `_cantidad`, y una
    prueba que necesita montar media base para afirmar que `43.000` se muestra
    como `43` esconde esa razon.
    """
    from decimal import Decimal as D

    assert historial._cantidad(D("43.000")) == "43"
    assert historial._cantidad(D("43.500")) == "43.5"
    assert historial._cantidad(D("0.250")) == "0.25"
    # Y no al reves: `normalize()` convertiria esto en `1E+2`.
    assert historial._cantidad(D("100.000")) == "100"
    assert historial._cantidad(D("0.000")) == "0"


def test_b1_suma_el_material_consumido_por_tipo(org_a, tipo, tecnico):
    anterior = _orden(org_a, tipo, 600)
    drop = MaterialCatalogo.objects.create(
        org=org_a, codigo="DROP", nombre="Cable drop", unidad="m",
        clase=MaterialCatalogo.BOBINA,
    )
    for cuanto in ("30.5", "12.5"):
        _mover(org_a, drop, anterior, MovimientoDeMaterial.CONSUMO, cuanto, tecnico)
    actual = _orden(org_a, tipo, 601)

    materiales = historial.visitas_anteriores(actual)[0]["materiales"]
    # «43», no «43.000». PostgreSQL devuelve el Decimal con la escala de la
    # columna, y en Colombia el punto es separador de MILES: «43.000 m» se lee
    # como cuarenta y tres mil metros de drop, y con ese numero el tecnico decide
    # cuanto llevar. En SQLite esto sale `43` y la diferencia no aparece.
    assert materiales == [
        {"material": "Cable drop", "cantidad": "43", "unidad": "m"}
    ]


def test_b2_una_devolucion_NO_cuenta_como_gastado(org_a, tipo, tecnico):
    """Sumarla diria que se puso el doble de drop del que se puso, y el tecnico
    que llega decidiria cuanto llevar con ese numero."""
    anterior = _orden(org_a, tipo, 700)
    drop = MaterialCatalogo.objects.create(
        org=org_a, codigo="DROP2", nombre="Cable drop", unidad="m",
        clase=MaterialCatalogo.BOBINA,
    )
    _mover(org_a, drop, anterior, MovimientoDeMaterial.CONSUMO, "30", tecnico)
    _mover(org_a, drop, anterior, MovimientoDeMaterial.DEVOLUCION, "5", tecnico)
    actual = _orden(org_a, tipo, 701)

    assert historial.visitas_anteriores(actual)[0]["materiales"][0]["cantidad"] == "30"
    # Y no «25»: la devolucion no se resta del consumo, se ignora.


def test_b3_dice_si_ya_se_cambio_el_equipo(org_a, tipo, tecnico):
    """«¿Ya le cambiaron la ONT?» es la pregunta que el tecnico hace distinto del
    resto. Un consumo con serie es un equipo que quedo en la casa."""
    con_equipo = _orden(org_a, tipo, 800)
    sin_equipo = _orden(org_a, tipo, 801)
    ont = MaterialCatalogo.objects.create(
        org=org_a, codigo="ONT", nombre="ONT ZTE", unidad="u",
        clase=MaterialCatalogo.SERIALIZADO,
    )
    drop = MaterialCatalogo.objects.create(
        org=org_a, codigo="DROP3", nombre="Cable drop", unidad="m",
        clase=MaterialCatalogo.BOBINA,
    )
    _mover(org_a, ont, con_equipo, MovimientoDeMaterial.CONSUMO, "1", tecnico,
           serie="ZTEGC0A1B2C3")
    _mover(org_a, drop, sin_equipo, MovimientoDeMaterial.CONSUMO, "20", tecnico)
    actual = _orden(org_a, tipo, 802)

    cambio = {v["numero"]: v["cambio_equipo"] for v in historial.visitas_anteriores(actual)}
    assert cambio == {800: True, 801: False}


# --------------------------------------------------------------------------- #
# C. Lo que NO puede pasar
# --------------------------------------------------------------------------- #

def test_c1_NO_mezcla_dos_abonados_distintos(org_a, tipo):
    """LA MAS IMPORTANTE DEL ARCHIVO.

    Si trajera visitas de otro abonado, el tecnico le diria al cliente «ya le
    cambiamos la ONT dos veces» cuando fue al vecino -- y el cliente le cree,
    porque se lo dice la empresa.
    """
    _orden(org_a, tipo, 900, abonado="WH-9999", cliente="Juan Pérez")
    _orden(org_a, tipo, 901, abonado=ABONADO)
    actual = _orden(org_a, tipo, 902, abonado=ABONADO)

    assert [v["numero"] for v in historial.visitas_anteriores(actual)] == [901]


def test_c2_el_MISMO_NOMBRE_con_otro_abonado_no_entra(org_a, tipo):
    """El caso que caza el atajo de agrupar por nombre: dos «Juan Pérez» no son
    la misma persona, y la unica forma de saberlo es el identificador."""
    _orden(org_a, tipo, 950, abonado="WH-OTRO", cliente="Beatriz Pinzón")
    actual = _orden(org_a, tipo, 951, abonado=ABONADO, cliente="Beatriz Pinzón")

    assert historial.visitas_anteriores(actual) == []


def test_c3_sin_identificador_no_se_adivina(org_a, tipo):
    _orden(org_a, tipo, 1000, abonado="")
    actual = _orden(org_a, tipo, 1001, abonado="")

    assert historial.visitas_anteriores(actual) == []


def test_c4_NO_cruza_empresas_con_el_mismo_numero_de_abonado(
    org_a, org_b, tipo, tipo_b
):
    """Cada empresa toma el identificador de SU WispHub: el 1042 de una no tiene
    nada que ver con el 1042 de la otra."""
    _orden(org_b, tipo_b, 1100, abonado=ABONADO, cliente="Otro cliente")
    actual = _orden(org_a, tipo, 1101, abonado=ABONADO)

    assert historial.visitas_anteriores(actual) == []


def test_c5_lo_que_todavia_no_paso_no_es_historial(org_a, tipo):
    """Una orden programada para el jueves no dice nada de lo que ya se hizo."""
    _orden(org_a, tipo, 1200, estado=OrdenTrabajo.ASIGNADA)
    _orden(org_a, tipo, 1201, estado=OrdenTrabajo.EN_CAMINO)
    _orden(org_a, tipo, 1202, estado=OrdenTrabajo.CERRADA)
    actual = _orden(org_a, tipo, 1203)

    assert [v["numero"] for v in historial.visitas_anteriores(actual)] == [1202]


def test_c6_no_lleva_nombre_direccion_ni_telefono_del_cliente(org_a, tipo):
    """Son del mismo servicio que ya esta abierto en la ficha. Repetirlos no
    agrega nada y los multiplica por tres en algo que se sincroniza al
    telefono."""
    import json

    _orden(org_a, tipo, 1300)
    actual = _orden(org_a, tipo, 1301)

    entero = json.dumps(historial.visitas_anteriores(actual), ensure_ascii=False)
    for dato in ("Beatriz", "Pinzón", "Calle 50", "312 455 8901", ABONADO):
        assert dato not in entero, dato


# --------------------------------------------------------------------------- #
# D. El identificador sale de donde ya estaba decidido
# --------------------------------------------------------------------------- #

def test_d1_el_contexto_sirve_cuando_la_columna_esta_vacia(org_a, tipo):
    """Mismo criterio que `lazo_isp._id_servicio_de`, y a proposito: si dos
    partes del sistema decidieran distinto cual es el servicio de una orden, una
    estaria mostrando o escribiendo sobre el cliente equivocado."""
    con_columna = _orden(org_a, tipo, 1400, abonado="WH-77")
    con_contexto = _orden(org_a, tipo, 1401, abonado="", contexto={"servicio": "WH-77"})

    assert historial.id_de_servicio(con_columna) == "WH-77"
    assert historial.id_de_servicio(con_contexto) == "WH-77"


def test_d2_la_columna_le_gana_al_contexto(org_a, tipo):
    o = _orden(org_a, tipo, 1500, abonado="WH-REAL", contexto={"servicio": "WH-VIEJO"})

    assert historial.id_de_servicio(o) == "WH-REAL"


# --------------------------------------------------------------------------- #
# E. Por HTTP
# --------------------------------------------------------------------------- #

def test_e1_el_endpoint_distingue_sin_servicio_de_primera_visita(
    org_a, tipo, user_client, user_profile
):
    """`hay_servicio: false` es distinto de `visitas: []`.

    El primero dice «no se puede saber»; el segundo, «es la primera vez». El
    tecnico actua distinto: con el primero llama al NOC, con el segundo no.
    """
    sin = _orden(org_a, tipo, 1600, abonado="")
    AsignacionTrabajo.objects.create(
        orden=sin, profile=user_profile, rol="tecnico", es_principal=True
    )
    r = user_client.get(f"/api/campo/trabajos/{sin.id}/historial/")
    assert r.status_code == 200, r.data
    assert r.data == {"hay_servicio": False, "visitas": []}

    primera = _orden(org_a, tipo, 1601, abonado="WH-SOLO")
    AsignacionTrabajo.objects.create(
        orden=primera, profile=user_profile, rol="tecnico", es_principal=True
    )
    r = user_client.get(f"/api/campo/trabajos/{primera.id}/historial/")
    assert r.status_code == 200
    assert r.data == {"hay_servicio": True, "visitas": []}


def test_e2_una_orden_de_otra_empresa_responde_404(org_b, tipo_b, user_client):
    """404 y no 403: un 403 confirma que la orden existe."""
    ajena = _orden(org_b, tipo_b, 1700)

    r = user_client.get(f"/api/campo/trabajos/{ajena.id}/historial/")

    assert r.status_code == 404
