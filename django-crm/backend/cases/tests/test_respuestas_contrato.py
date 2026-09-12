# -*- coding: utf-8 -*-
"""
El contrato del endpoint del hilo, limite por limite.

    uv run pytest cases/tests/test_respuestas_contrato.py --no-cov -v

POR QUE EXISTE
--------------
La auditoria pidio que los topes esten DOCUMENTADOS Y PROBADOS, no implicitos
en el ancho de una columna. Un limite que solo existe como 'max_length' se
descubre cuando PostgreSQL devuelve DataError, y eso ya paso: fue uno de los
cinco 500.

LA TABLA
--------
    respuestas por lote      200        MAX_RESPUESTAS    rechaza
    huella                    64 chars  LARGO_HUELLA      rechaza
    autor_nombre             160 chars  (columna)         recorta
    autor_usuario            160 chars  (columna)         recorta
    cuerpo                20.000 chars  TOPE_CUERPO       recorta
    archivos                0..32.767   MAX_ARCHIVOS      rechaza
    cuerpo del request       2,5 MB     Django            rechaza antes de llegar

RECHAZAR O RECORTAR NO ES ARBITRARIO
------------------------------------
Se RECHAZA lo que indica que quien llama entendio mal el contrato: una huella
que no es un sha256, un contador que no es un numero. Son errores de programa y
callarlos deja al llamante creyendo que escribio lo que mando.

Se RECORTA el texto libre de una persona -- nombre y cuerpo -- donde el exceso
no es error de nadie y perder el final es mejor que perder la respuesta entera.
"""

import pytest

from cases.models import Case, RespuestaExterna

pytestmark = pytest.mark.django_db

NULO = chr(0)
CAMPANA = chr(7)
INVERTIR = chr(0x202E)


def _url(caso):
    return f"/api/importacion/casos/{caso.id}/respuestas/"


def _respuesta(**extra):
    base = {
        "huella": "a" * 64,
        "autor_nombre": "JULIO MORENO",
        "autor_usuario": "tecnico3@rapilink-sas",
        "cuerpo": "Se reviso la acometida.",
        "creada_en_proveedor": "2026-09-12T09:34:25-05:00",
        "archivos": 0,
    }
    base.update(extra)
    return base


@pytest.fixture
def importado(admin_user, org_a):
    return Case.objects.create(
        name="No Tiene Internet", status="New", priority="Normal",
        org=org_a, created_by=admin_user, provider="wisphub",
        external_ticket_id="92321", external_service_id="2987",
        external_status="Nuevo", description="Reportado por telefono.")


# --- los numeros viven en constantes con nombre -----------------------------

def test_los_topes_declarados_son_los_que_se_aplican():
    from cases import importacion_views as v

    assert v.MAX_RESPUESTAS == 200
    assert v.LARGO_HUELLA == 64
    assert v.TOPE_CUERPO == 20_000
    assert v.MAX_ARCHIVOS == 32_767


# --- lo que se recorta ------------------------------------------------------

def test_el_nombre_y_el_usuario_del_autor_se_recortan(admin_client, importado):
    """La columna mide 160. Mas largo se recorta; no da DataError."""
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(autor_nombre="N" * 500,
                                   autor_usuario="U" * 500)]},
        format="json")
    assert r.status_code == 200, r.content
    fila = RespuestaExterna.objects.get()
    assert len(fila.autor_nombre) == 160
    assert len(fila.autor_usuario) == 160


def test_el_cuerpo_se_recorta_al_tope(admin_client, importado):
    from cases.importacion_views import TOPE_CUERPO

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo="x" * 100_000)]},
        format="json")
    assert r.status_code == 200, r.content
    assert len(RespuestaExterna.objects.get().cuerpo) == TOPE_CUERPO


# --- los bordes exactos -----------------------------------------------------

def test_archivos_en_el_limite_exacto(admin_client, importado):
    from cases.importacion_views import MAX_ARCHIVOS

    ok = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(archivos=MAX_ARCHIVOS)]},
        format="json")
    assert ok.status_code == 200, ok.content

    pasado = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(huella="b" * 64, archivos=MAX_ARCHIVOS + 1)]},
        format="json")
    assert pasado.status_code == 400, pasado.content


def test_la_huella_en_el_limite_exacto(admin_client, importado):
    ok = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(huella="a" * 64)]},
        format="json")
    assert ok.status_code == 200, ok.content

    pasado = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(huella="a" * 65)]},
        format="json")
    assert pasado.status_code == 400, pasado.content


def test_un_booleano_no_pasa_por_numero_de_archivos(admin_client, importado):
    """'True' vale 1 en Python, y "cuantos archivos trae" no es si o no.

    Sin la comprobacion explicita de bool, 'archivos: true' se guardaria como
    un archivo que no existe.
    """
    for valor in (True, False):
        r = admin_client.post(
            _url(importado),
            {"provider": "wisphub", "respuestas": [_respuesta(archivos=valor)]},
            format="json")
        assert r.status_code == 400, f"archivos={valor!r} entro: {r.content}"
    assert RespuestaExterna.objects.count() == 0
    # Los DOS, y no solo True. Con 'fila.get("archivos") or 0' el False se
    # convertia en 0 antes de la comprobacion de tipo: True se rechazaba y
    # False entraba. Dos booleanos con destinos distintos es peor que aceptar
    # los dos, porque nadie lo espera.


# --- texto de una persona real ----------------------------------------------

@pytest.mark.parametrize("texto", [
    "Se revisó la acometida — está en 1490 nm",     # acentos y guion largo
    "日本語のテキスト",                                # fuera del alfabeto latino
    "linea uno\nlinea dos\r\nlinea tres",            # saltos de linea reales
    "con\ttabulacion",
    NULO + CAMPANA,                                  # el NUL se quita, la campana no
    INVERTIR + " texto invertido",                   # override de direccion
    "",                                              # vacio
])
def test_unicode_y_caracteres_de_control_no_rompen(admin_client, importado, texto):
    """El texto del proveedor lo escribio una persona y trae de todo.

    No se sanea al guardar: eso destruiria el dato y ademas no protege a quien
    lo lea por la API. Lo que se exige aca es que NADA de esto produzca una
    excepcion -- se guarda o se rechaza, nunca un 500.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo=texto)]},
        format="json")
    assert r.status_code in (200, 400), (
        f"texto={texto!r} devolvio {r.status_code}: {r.content[:200]}")


# --- superficie de archivos --------------------------------------------------

def test_los_archivos_son_un_numero_y_nunca_una_url(admin_client, importado):
    """No hay superficie para una URL maliciosa: de los adjuntos entra CUANTOS.

    Esta prueba fija esa decision. El dia que alguien quiera guardar los
    enlaces, falla y obliga a pensar en SSRF y en descarga de contenido ajeno
    ANTES de hacerlo.
    """
    from cases.importacion_views import CAMPOS_RESPUESTA

    assert CAMPOS_RESPUESTA == {"huella", "autor_nombre", "autor_usuario",
                                "cuerpo", "creada_en_proveedor", "archivos"}
    campo = RespuestaExterna._meta.get_field("archivos")
    assert campo.get_internal_type() == "PositiveSmallIntegerField"

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(archivos="http://evil.example/x.pdf")]},
        format="json")
    assert r.status_code == 400, r.content


# --- el barrido -------------------------------------------------------------

def test_ningun_rechazo_sale_como_excepcion_de_base(admin_client, importado):
    """Barrido: toda entrada hostil termina en 200 o en 400 con codigo propio.

    Los cinco 500 que encontro la auditoria eran excepciones de base que se
    escapaban: ValueError de int(), DataError de smallint, DataError de
    varchar(64), ValidationError de fecha. Van juntos aca para que ninguno
    vuelva por un camino nuevo.
    """
    hostiles = [
        {"archivos": "no soy un numero"}, {"archivos": [1, 2]},
        {"archivos": {"a": 1}}, {"archivos": 999999}, {"archivos": -1},
        {"archivos": 1.5}, {"archivos": True},
        {"huella": "z" * 500}, {"huella": None}, {"huella": 12345},
        {"creada_en_proveedor": "no es una fecha"},
        {"creada_en_proveedor": "2026-13-45T99:99:99"},
        {"creada_en_proveedor": 12345}, {"creada_en_proveedor": {"a": 1}},
        {"creada_en_proveedor": "2026-09-12T09:34:25"},   # sin zona
        {"cuerpo": "x" * 500_000}, {"autor_nombre": "N" * 5000},
    ]
    for extra in hostiles:
        r = admin_client.post(
            _url(importado),
            {"provider": "wisphub", "respuestas": [_respuesta(**extra)]},
            format="json")
        assert r.status_code in (200, 400), (
            f"{extra} devolvio {r.status_code}: {r.content[:200]}")
        if r.status_code == 400:
            assert "error" in r.json(), f"{extra} no trajo codigo de error"


def test_el_byte_nulo_se_quita_y_el_resto_del_texto_sobrevive(admin_client,
                                                              importado):
    """PostgreSQL no admite 0x00 en una columna de texto.

    Se QUITA en vez de rechazar el lote: el hilo se reenvia entero cada hora,
    asi que rechazarlo por un byte de transporte dejaria ese ticket sin
    sincronizar para siempre, reintentando igual cada vez. Un NUL en el medio
    de un mensaje no es algo que alguien escribio.

    Antes esto salia como 409 LOTE_NO_ESCRITO por un DataError de la base, que
    es justo lo que la auditoria pidio que no pasara: un rechazo tiene que ser
    determinista y del lado de la aplicacion.
    """
    texto = "antes" + NULO + "despues"
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo=texto)]},
        format="json")
    assert r.status_code == 200, r.content
    guardado = RespuestaExterna.objects.get().cuerpo
    assert NULO not in guardado
    assert guardado == "antesdespues", f"quedo {guardado!r}"


def test_los_otros_caracteres_de_control_se_guardan_tal_cual(admin_client,
                                                             importado):
    """Un salto de linea o una tabulacion son cosas que una persona escribio."""
    texto = ("linea uno" + chr(10) + "linea dos" + chr(9)
             + "con tabulacion" + CAMPANA)
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo=texto)]},
        format="json")
    assert r.status_code == 200, r.content
    assert RespuestaExterna.objects.get().cuerpo == texto
