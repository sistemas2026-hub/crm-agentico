# -*- coding: utf-8 -*-
"""
La identidad del ticket externo sobre 'case'  --  Fase 1.

    uv run pytest cases/tests/test_identidad_ticket_externo.py --no-cov -v

QUE FIJA
--------
Que un caso pueda decir, por si mismo y sin pasar por una conversacion, a que
ticket del sistema del ISP corresponde y de que servicio habla. Y que no pueda
decirlo a medias: 'provider' sin numero de ticket es una fila que ningun
importador va a poder emparejar nunca, y dos filas con el mismo ticket en la
misma org es lo que produce un sondeo en su primer reintento.

Las guardas viven en la base (UNIQUE parcial + CHECK), no en una validacion de
serializer, porque quien va a escribir estas columnas es un proceso de fondo
que no pasa por ningun serializer.
"""

from importlib import import_module

import pytest
from django.db import IntegrityError, transaction

from cases.models import (EXTERNAL_AUTHOR_DEXTER, EXTERNAL_AUTHOR_HUMAN,
                          EXTERNAL_AUTHOR_UNKNOWN, Case)

pytestmark = pytest.mark.django_db

BACKFILL = import_module("cases.migrations.0030_backfill_ticket_externo")


def _caso(org, autor, **extra):
    return Case.objects.create(
        name=extra.pop("name", "Caso de prueba"),
        status=extra.pop("status", "New"),
        priority="Normal",
        org=org,
        created_by=autor,
        **extra,
    )


# --- 1 y 2: los dos estados que SI son validos ---------------------------

def test_caso_nativo_sin_referencia_externa(org_a, admin_user):
    """Un caso que nacio en Dexter no tiene proveedor ni ticket, y esta bien."""
    c = _caso(org_a, admin_user)
    assert c.provider == ""
    assert c.external_ticket_id == ""
    assert c.external_service_id == ""
    assert c.external_created_by == ""
    assert c.external_created_by_type == ""
    assert c.external_status == ""
    assert c.external_status_at is None
    assert c.external_fetched_at is None
    assert c.external_fetch_error == ""


def test_referencia_wisphub_completa(org_a, admin_user):
    c = _caso(org_a, admin_user, provider="wisphub", external_ticket_id="91288",
              external_service_id="5832",
              external_created_by="SHEILA - licencia@rapilink-sas",
              external_created_by_type=EXTERNAL_AUTHOR_HUMAN,
              external_status="En Progreso")
    c.refresh_from_db()
    assert (c.provider, c.external_ticket_id) == ("wisphub", "91288")
    assert c.external_service_id == "5832"
    assert c.external_created_by_type == EXTERNAL_AUTHOR_HUMAN


# --- 3, 4, 5: el alcance exacto del UNIQUE -------------------------------

def test_no_se_repite_el_mismo_ticket_en_la_misma_org(org_a, admin_user):
    _caso(org_a, admin_user, provider="wisphub", external_ticket_id="91288")
    with pytest.raises(IntegrityError), transaction.atomic():
        _caso(org_a, admin_user, provider="wisphub", external_ticket_id="91288")


def test_el_mismo_ticket_en_OTRA_org_si_se_permite(org_a, org_b, admin_user, user_b):
    """La numeracion es del proveedor de CADA ISP: dos empresas distintas
    pueden tener, cada una, su ticket 91288. Sin 'org' en el UNIQUE, el
    segundo ISP que se conecte no podria importar la mitad de sus tickets."""
    _caso(org_a, admin_user, provider="wisphub", external_ticket_id="91288")
    otro = _caso(org_b, user_b, provider="wisphub", external_ticket_id="91288")
    assert otro.pk


def test_el_mismo_numero_con_OTRO_proveedor_si_se_permite(org_a, admin_user):
    _caso(org_a, admin_user, provider="wisphub", external_ticket_id="91288")
    otro = _caso(org_a, admin_user, provider="otro_isp", external_ticket_id="91288")
    assert otro.pk


def test_varios_casos_nativos_no_chocan_entre_si(org_a, admin_user):
    """El UNIQUE es PARCIAL por esto: sin la condicion, los casos nativos
    comparten la cadena vacia y el segundo no se podria crear."""
    for i in range(4):
        _caso(org_a, admin_user, name=f"Nativo {i}")
    assert Case.objects.filter(org=org_a, external_ticket_id="").count() == 4


# --- 6 y 7: los estados imposibles --------------------------------------

def test_proveedor_sin_numero_de_ticket_se_rechaza(org_a, admin_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        _caso(org_a, admin_user, provider="wisphub", external_ticket_id="")


def test_numero_de_ticket_sin_proveedor_se_rechaza(org_a, admin_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        _caso(org_a, admin_user, provider="", external_ticket_id="91288")


# --- 8: el puente hacia el cliente y la ONU ------------------------------

def test_el_servicio_se_guarda_sin_depender_de_una_conversacion(org_a, admin_user):
    """
    'external_service_id' es la unica arista que la Fase 0 midio al 100 %
    (1.162/1.162 tickets traen servicio.id_servicio). Con el guardado aca, un
    caso llega al cliente y de ahi a la ONU sin que haya existido un chat.
    """
    c = _caso(org_a, admin_user, provider="wisphub", external_ticket_id="92060",
              external_service_id="3545")
    c.refresh_from_db()
    assert c.external_service_id == "3545"
    # Y se puede buscar por el, que es para lo que existe el indice.
    assert Case.objects.filter(org=org_a, external_service_id="3545").count() == 1


def test_el_servicio_puede_ir_solo_en_un_caso_nativo(org_a, admin_user):
    """No se le exige proveedor: una conversacion conoce el id_servicio aunque
    nunca haya abierto un ticket."""
    c = _caso(org_a, admin_user, external_service_id="5832")
    c.refresh_from_db()
    assert (c.provider, c.external_ticket_id, c.external_service_id) == ("", "", "5832")


# --- 9 y 10: el backfill -------------------------------------------------

class _CursorFalso:
    """Se hace pasar por el cursor de Postgres para el backfill.

    Devuelve una fila en la consulta a information_schema (o sea: 'el esquema
    del motor existe') y las filas dadas en la consulta de conversaciones.
    """

    def __init__(self, filas):
        self._filas = filas
        self._pregunta = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self._pregunta = "esquema" if "information_schema" in sql else "filas"

    def fetchone(self):
        return (1,) if self._pregunta == "esquema" else None

    def fetchall(self):
        return self._filas


class _ConexionFalsa:
    vendor = "postgresql"

    def __init__(self, filas):
        self._filas = filas

    def cursor(self):
        return _CursorFalso(self._filas)


class _EditorFalso:
    def __init__(self, filas):
        self.connection = _ConexionFalsa(filas)


class _AppsFalso:
    def get_model(self, _app, _modelo):
        return Case


def _correr_backfill(filas):
    BACKFILL.adelante(_AppsFalso(), _EditorFalso(filas))


def test_backfill_copia_los_deterministas(org_a, admin_user):
    uno = _caso(org_a, admin_user, name="Escalado 1")
    dos = _caso(org_a, admin_user, name="Escalado 2")

    _correr_backfill([
        (uno.pk, "91288", "5832", org_a.id),
        (dos.pk, "91309", "", org_a.id),
    ])

    uno.refresh_from_db()
    dos.refresh_from_db()
    assert (uno.provider, uno.external_ticket_id, uno.external_service_id) == \
        ("wisphub", "91288", "5832")
    assert uno.external_created_by_type == EXTERNAL_AUTHOR_DEXTER
    # Lo sabemos por NUESTRO registro, no porque el proveedor lo haya dicho:
    # el campo con lo que dijo el proveedor queda vacio hasta que se lea.
    assert uno.external_created_by == ""
    assert uno.external_fetched_at is None
    assert (dos.provider, dos.external_ticket_id, dos.external_service_id) == \
        ("wisphub", "91309", "")


def test_backfill_no_pisa_una_referencia_que_ya_estaba(org_a, admin_user):
    c = _caso(org_a, admin_user, provider="wisphub", external_ticket_id="99999")
    _correr_backfill([(c.pk, "91288", "5832", org_a.id)])
    c.refresh_from_db()
    assert c.external_ticket_id == "99999"


def test_backfill_ignora_un_caso_de_otra_org(org_a, org_b, admin_user, user_b):
    """Escribir la referencia de un ISP sobre el caso de otro es justo lo que
    el 'org' del UNIQUE existe para impedir; el backfill no lo intenta."""
    ajeno = _caso(org_b, user_b)
    _correr_backfill([(ajeno.pk, "91288", "5832", org_a.id)])
    ajeno.refresh_from_db()
    assert ajeno.external_ticket_id == ""


def test_backfill_sobrevive_a_un_caso_que_ya_no_existe(org_a, admin_user):
    import uuid
    vivo = _caso(org_a, admin_user)
    _correr_backfill([
        (uuid.uuid4(), "90990", "", org_a.id),   # caso borrado
        (vivo.pk, "91288", "5832", org_a.id),
    ])
    vivo.refresh_from_db()
    assert vivo.external_ticket_id == "91288", "una fila huerfana corto el backfill"


def test_backfill_no_parsea_el_numero_de_la_descripcion(org_a, admin_user):
    """
    Los 13 numeros que solo viven dentro del parrafo NO se recuperan.

    Se puede -- los 28 casos que lo mencionan parsean y no colisionan -- y aun
    asi no se hace: la columna existe para no volver a parsear un parrafo, y
    estrenarla parseando uno seria sembrar de nuevo el problema que vino a
    resolver. Quedan como legado, sin referencia externa, que es un estado
    valido.
    """
    legado = _caso(org_a, admin_user,
                   description="Se abrio el Ticket operativo #91288 en el sistema.")
    _correr_backfill([])            # ninguna conversacion lo referencia
    legado.refresh_from_db()
    assert legado.external_ticket_id == ""
    assert legado.provider == ""

    fuente = __import__("inspect").getsource(BACKFILL)
    assert "description" not in fuente, "el backfill mira la descripcion"
    assert "re.compile" not in fuente and "import re" not in fuente


def test_backfill_sin_esquema_del_motor_no_falla(org_a, admin_user):
    """Sobre SQLite -- y en un CRM instalado sin el motor al lado -- no hay
    nada que copiar, y eso no es un error."""
    c = _caso(org_a, admin_user)

    class _SinPostgres:
        vendor = "sqlite"

        def cursor(self):
            raise AssertionError("no deberia consultar nada")

    class _Editor:
        connection = _SinPostgres()

    BACKFILL.adelante(_AppsFalso(), _Editor())
    c.refresh_from_db()
    assert c.external_ticket_id == ""


def test_backfill_se_puede_revertir(org_a, admin_user):
    c = _caso(org_a, admin_user)
    _correr_backfill([(c.pk, "91288", "5832", org_a.id)])

    BACKFILL.atras(_AppsFalso(), _EditorFalso([]))
    c.refresh_from_db()
    assert (c.provider, c.external_ticket_id, c.external_service_id) == ("", "", "")
    assert c.external_created_by_type == ""


def test_revertir_no_borra_lo_que_leyo_un_importador(org_a, admin_user):
    """Una fila con 'external_fetched_at' la escribio el sondeo, no esta
    migracion: revertir el backfill no puede llevarsela por delante."""
    from django.utils import timezone
    c = _caso(org_a, admin_user, provider="wisphub", external_ticket_id="92060",
              external_created_by_type=EXTERNAL_AUTHOR_UNKNOWN,
              external_fetched_at=timezone.now())
    BACKFILL.atras(_AppsFalso(), _EditorFalso([]))
    c.refresh_from_db()
    assert c.external_ticket_id == "92060"


# --- 11: la migracion no cambia nada de lo que ya funcionaba -------------

def test_los_campos_nuevos_no_llegan_a_la_interfaz(org_a, admin_user):
    """
    Fase 1 es solo esquema. Ningun serializer expone ni acepta estos campos,
    asi que ninguna pantalla los muestra y ninguna peticion los escribe --
    quien los va a escribir es un proceso de fondo, en la Fase 2.
    """
    from cases.serializer import CaseCreateSerializer, CaseSerializer

    nuevos = {"provider", "external_ticket_id", "external_service_id",
              "external_status", "external_status_at", "external_fetched_at",
              "external_fetch_error", "external_created_by",
              "external_created_by_type"}
    for serializador in (CaseSerializer, CaseCreateSerializer):
        expuestos = set(serializador.Meta.fields)
        assert not (nuevos & expuestos), (
            f"{serializador.__name__} expone {sorted(nuevos & expuestos)}")


def test_un_caso_normal_se_crea_y_se_cierra_igual_que_antes(org_a, admin_user):
    c = _caso(org_a, admin_user, status="New")
    c.status = "Closed"
    c.save(update_fields=["status"])
    c.refresh_from_db()
    assert c.status == "Closed"
    # El estado de Dexter se movio y el del proveedor no existe: son campos
    # distintos con dueños distintos, que es toda la decision de la Fase 1.
    assert c.external_status == ""
