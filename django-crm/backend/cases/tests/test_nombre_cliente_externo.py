# -*- coding: utf-8 -*-
"""
================================================================================
 LA RUTA QUE ESCRIBE EL NOMBRE DEL CLIENTE
================================================================================

POR QUE ESTA RUTA EXISTE, Y QUE GUARDA ESTE ARCHIVO
---------------------------------------------------
El nombre del cliente vive en WispHub y solo el motor sabe hablarle; la tabla
'case' es del CRM. El primer intento fue un comando del motor haciendo el
UPDATE directo, y estaba roto por dos caminos medidos en produccion el
25/09/2026: 'app_backend' no tiene privilegios sobre public."case", y la RLS de
esa tabla compara contra 'app.current_org' mientras el motor fija
'app.current_tenant' -- habria dicho "0 actualizados" sin error.

Asi que el motor pide y el CRM escribe. Lo que se guarda aqui es que esa puerta
sea angosta: un campo, sin sobrescribir, sin cruzar organizaciones, y sin poder
usarse para tocar nada mas.

LO QUE SE AFIRMA
----------------
El EFECTO sobre la fila, no la presencia del mecanismo. Cada prueba de "no
toca X" relee la fila y compara X contra su valor anterior.
================================================================================
"""

import uuid

import pytest
from rest_framework.test import APIClient

from cases.models import Case
from common.models import Activity

pytestmark = pytest.mark.django_db

RUTA = "/api/importacion/casos/nombre-cliente/"
NOMBRE = "JUAN DAVID BARRIOS BARRIOS"
SERVICIO = "6580"


# =============================================================================
#  andamio
# =============================================================================

@pytest.fixture
def cliente_a(admin_client):
    return admin_client


def _caso(org, **extra):
    datos = dict(
        org=org,
        name="Sin servicio de internet",
        status="New",
        priority="Normal",
        provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=SERVICIO,
    )
    datos.update(extra)
    return Case.objects.create(**datos)


def _pedir(cliente, **cuerpo):
    base = {"external_service_id": SERVICIO, "external_client_name": NOMBRE}
    base.update(cuerpo)
    return cliente.post(RUTA, base, format="json")


# =============================================================================
#  §1  EL CAMINO QUE HACE FALTA
# =============================================================================

def test_el_crm_persiste_el_nombre_que_le_manda_el_motor(cliente_a, org_a):
    caso = _caso(org_a)

    r = _pedir(cliente_a)
    assert r.status_code == 200, r.content
    assert r.json() == {"actualizados": 1, "ya_tenian": 0, "sin_nombre": False}

    caso.refresh_from_db()
    assert caso.external_client_name == NOMBRE


def test_un_servicio_con_varios_casos_los_toma_todos(cliente_a, org_a):
    """
    El motor manda el SERVICIO, no el caso: no conoce los ids de los casos.

    Medido: 16 servicios de produccion tienen mas de un caso. Si la ruta
    resolviera solo uno, el backfill quedaria a medias sin decirlo.
    """
    casos = [_caso(org_a) for _ in range(3)]

    r = _pedir(cliente_a)
    assert r.json()["actualizados"] == 3

    for c in casos:
        c.refresh_from_db()
        assert c.external_client_name == NOMBRE


def test_un_servicio_sin_casos_pendientes_no_es_un_error(cliente_a, org_a):
    """Volver a correr el backfill no puede fallar. Contesta cero y sigue."""
    r = _pedir(cliente_a)
    assert r.status_code == 200
    assert r.json() == {"actualizados": 0, "ya_tenian": 0, "sin_nombre": False}


# =============================================================================
#  §2  IDEMPOTENCIA  --  no sobrescribe, nunca
# =============================================================================

def test_un_nombre_que_ya_estaba_no_se_sobrescribe(cliente_a, org_a):
    """
    LA GARANTIA CENTRAL.

    Un nombre puesto a mano, o por una corrida anterior, no lo pisa el
    backfill. Se informa como 'ya_tenian' para que el comando lo pueda contar.
    """
    caso = _caso(org_a, external_client_name="NOMBRE PUESTO A MANO")

    r = _pedir(cliente_a)
    assert r.json() == {"actualizados": 0, "ya_tenian": 1, "sin_nombre": False}

    caso.refresh_from_db()
    assert caso.external_client_name == "NOMBRE PUESTO A MANO"


def test_correr_dos_veces_deja_el_mismo_resultado(cliente_a, org_a):
    caso = _caso(org_a)

    primera = _pedir(cliente_a).json()
    segunda = _pedir(cliente_a).json()

    assert primera == {"actualizados": 1, "ya_tenian": 0, "sin_nombre": False}
    assert segunda == {"actualizados": 0, "ya_tenian": 1, "sin_nombre": False}
    caso.refresh_from_db()
    assert caso.external_client_name == NOMBRE


def test_una_mezcla_de_puestos_y_vacios_solo_llena_los_vacios(cliente_a, org_a):
    vacio = _caso(org_a)
    puesto = _caso(org_a, external_client_name="OTRO NOMBRE")

    r = _pedir(cliente_a)
    assert r.json() == {"actualizados": 1, "ya_tenian": 1, "sin_nombre": False}

    vacio.refresh_from_db()
    puesto.refresh_from_db()
    assert vacio.external_client_name == NOMBRE
    assert puesto.external_client_name == "OTRO NOMBRE"


def test_sin_nombre_del_proveedor_no_se_escribe_nada(cliente_a, org_a):
    """
    El proveedor no dio nombre. No es un error del llamante y no se escribe.

    Guardar la cadena vacia seria peor que no hacer nada: el dia que alguien
    reintente, el caso ya no figuraria como pendiente.
    """
    caso = _caso(org_a)

    r = _pedir(cliente_a, external_client_name="")
    assert r.status_code == 200, r.content
    assert r.json()["sin_nombre"] is True
    assert r.json()["actualizados"] == 0

    caso.refresh_from_db()
    assert caso.external_client_name == ""


def test_un_nombre_de_solo_espacios_cuenta_como_sin_nombre(cliente_a, org_a):
    caso = _caso(org_a)
    assert _pedir(cliente_a, external_client_name="   ").json()["sin_nombre"] is True
    caso.refresh_from_db()
    assert caso.external_client_name == ""


# =============================================================================
#  §3  AISLAMIENTO ENTRE ORGANIZACIONES
# =============================================================================

def test_no_toca_el_caso_de_otra_organizacion(cliente_a, org_a, org_b):
    """
    El mismo id_servicio en dos empresas son dos clientes distintos.

    'external_service_id' es el id en el sistema del proveedor, y dos ISP
    distintos pueden tener el numero 6580 cada uno. Escribir cruzado pondria el
    nombre del cliente de una empresa en el caso de la otra.
    """
    mio = _caso(org_a)
    ajeno = _caso(org_b)

    r = _pedir(cliente_a)
    assert r.json()["actualizados"] == 1

    mio.refresh_from_db()
    ajeno.refresh_from_db()
    assert mio.external_client_name == NOMBRE
    assert ajeno.external_client_name == ""


def test_la_organizacion_no_se_puede_elegir_desde_el_cuerpo(cliente_a, org_a, org_b):
    """
    'org' no esta entre los campos aceptados, asi que mandarla es un rechazo.

    La org sale de la credencial, no del payload: dejarla en el cuerpo seria
    darle al llamante la forma de escribir en otro tenant.
    """
    ajeno = _caso(org_b)

    r = cliente_a.post(RUTA, {"external_service_id": SERVICIO,
                              "external_client_name": NOMBRE,
                              "org": str(org_b.id)}, format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "CAMPO_NO_PERMITIDO"

    ajeno.refresh_from_db()
    assert ajeno.external_client_name == ""


def test_el_token_de_otra_org_no_alcanza_mis_casos(org_a, org_b_client):
    mio = _caso(org_a)

    r = org_b_client.post(RUTA, {"external_service_id": SERVICIO,
                                 "external_client_name": NOMBRE}, format="json")
    assert r.status_code == 200
    assert r.json()["actualizados"] == 0

    mio.refresh_from_db()
    assert mio.external_client_name == ""


# =============================================================================
#  §4  AUTENTICACION
# =============================================================================

def test_sin_credencial_no_se_entra(org_a):
    caso = _caso(org_a)

    r = APIClient().post(RUTA, {"external_service_id": SERVICIO,
                                "external_client_name": NOMBRE}, format="json")
    assert r.status_code in (401, 403), r.content

    caso.refresh_from_db()
    assert caso.external_client_name == ""


# =============================================================================
#  §5  LA PUERTA ES ANGOSTA
# =============================================================================

@pytest.mark.parametrize("prohibido", [
    {"status": "Closed"},
    {"name": "otro asunto"},
    {"account": str(uuid.uuid4())},
    {"priority": "High"},
    {"external_status": "Cerrado"},
    {"assigned_to": str(uuid.uuid4())},
    {"closed_on": "2026-01-01"},
    {"custom_fields": {"x": 1}},
])
def test_no_acepta_ningun_otro_campo(cliente_a, org_a, prohibido):
    """
    Un campo de mas se RECHAZA, no se ignora.

    Ignorarlo dejaria al llamante creyendo que lo escribio. Y el conjunto
    importa: si esta ruta aceptara 'status', seria una segunda via para cerrar
    un caso sin que nadie lo decida.
    """
    caso = _caso(org_a)

    r = _pedir(cliente_a, **prohibido)
    assert r.status_code == 400, r.content
    assert r.json()["error"] == "CAMPO_NO_PERMITIDO"

    caso.refresh_from_db()
    assert caso.external_client_name == "", "escribio pese a rechazar"


def test_no_modifica_ningun_otro_campo_del_caso(cliente_a, org_a):
    """
    Se compara la fila ENTERA antes y despues.

    No una lista de campos que alguien se acordo de mirar: todos, menos el que
    la ruta escribe y la marca de tiempo. Un 'save()' completo agregado despues
    -- que arrastraria cualquier valor cargado en memoria -- no pasa esto.
    """
    caso = _caso(org_a, external_created_by="SHEILA - licencia@rapilink-sas",
                 external_status="Nuevo", description="Reportado por telefono.")
    antes = Case.objects.filter(id=caso.id).values().first()

    assert _pedir(cliente_a).status_code == 200

    despues = Case.objects.filter(id=caso.id).values().first()
    cambiaron = {k for k in antes if antes[k] != despues[k]}
    assert cambiaron == {"external_client_name", "updated_at"}, cambiaron


def test_falta_el_servicio_y_se_rechaza(cliente_a):
    r = cliente_a.post(RUTA, {"external_client_name": NOMBRE}, format="json")
    assert r.status_code == 400
    assert r.json()["error"] == "CAMPO_REQUERIDO"


def test_un_nombre_larguisimo_se_recorta(cliente_a, org_a):
    caso = _caso(org_a)
    assert _pedir(cliente_a, external_client_name="Z" * 400).status_code == 200
    caso.refresh_from_db()
    assert len(caso.external_client_name) == 255


# =============================================================================
#  §6  AUDITORIA
# =============================================================================

def test_queda_registrado_en_la_bitacora_del_crm(cliente_a, org_a):
    """
    Se escribe en common.Activity, que es la bitacora que ya existe.

    'Case' y 'UPDATE' ya estan declarados en sus choices: no hace falta una
    tabla nueva, y un tercer sistema de auditoria solo agregaria un lugar mas
    donde buscar.
    """
    caso = _caso(org_a)
    antes = Activity.objects.filter(entity_type="Case").count()

    assert _pedir(cliente_a).status_code == 200

    filas = Activity.objects.filter(entity_type="Case", entity_id=caso.id)
    assert Activity.objects.filter(entity_type="Case").count() == antes + 1
    fila = filas.first()
    assert fila.action == "UPDATE"
    assert fila.org_id == org_a.id
    assert fila.metadata["external_service_id"] == SERVICIO
    assert fila.metadata["campo"] == "external_client_name"
    assert fila.created_at is not None


def test_la_bitacora_no_guarda_una_segunda_copia_del_nombre(cliente_a, org_a):
    """
    El nombre ya quedo en la fila del caso.

    Repetirlo en el metadata seria una segunda copia del dato personal en otra
    tabla, que nadie pidio y que nadie recuerda borrar.
    """
    _caso(org_a)
    assert _pedir(cliente_a).status_code == 200

    fila = Activity.objects.filter(entity_type="Case").first()
    assert NOMBRE not in str(fila.metadata)
    assert NOMBRE not in (fila.description or "")
    assert NOMBRE not in (fila.entity_name or "")


def test_un_servicio_sin_cambios_no_ensucia_la_bitacora(cliente_a, org_a):
    """Cero escrituras, cero filas de auditoria. No se anota lo que no paso."""
    _caso(org_a, external_client_name="YA ESTABA")
    antes = Activity.objects.filter(entity_type="Case").count()

    assert _pedir(cliente_a).json()["actualizados"] == 0
    assert Activity.objects.filter(entity_type="Case").count() == antes


# =============================================================================
#  §7  LA LECTURA QUE ALIMENTA EL BACKFILL
# =============================================================================

def test_la_lista_de_casos_externos_dice_si_falta_el_nombre_sin_decir_cual(cliente_a, org_a):
    """
    El backfill necesita saber a QUIEN le falta, no como se llama.

    Esa vista promete, en su propio docstring, no devolver nada del cliente.
    Asi que viaja un booleano y el id del servicio -- que es un identificador,
    no un dato personal-- y el nombre no.
    """
    _caso(org_a, external_ticket_id="90001")
    _caso(org_a, external_ticket_id="90002", external_client_name=NOMBRE)

    r = cliente_a.get("/api/importacion/casos-externos/?provider=wisphub")
    assert r.status_code == 200, r.content

    por_ticket = {c["external_ticket_id"]: c for c in r.json()["casos"]}
    assert por_ticket["90001"]["tiene_nombre_cliente"] is False
    assert por_ticket["90002"]["tiene_nombre_cliente"] is True
    assert por_ticket["90001"]["external_service_id"] == SERVICIO

    #  Y el nombre NO viaja, en ninguna fila ni en ninguna clave.
    assert "external_client_name" not in por_ticket["90002"]
    assert NOMBRE not in r.content.decode()
