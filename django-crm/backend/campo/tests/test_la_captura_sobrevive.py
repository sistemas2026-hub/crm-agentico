# -*- coding: utf-8 -*-
"""
================================================================================
 LA MARCA DE «CAPTURA DE PANTALLA» SOBREVIVE AL GUARDADO  --  07/11/2026
================================================================================
El usuario, en el editor de plantillas:

    «en plantilla cuando marco captura de pantalla despues de guardar se pone
    en blanco otra vez»

Y era literal. `es_captura` dice que esa evidencia NO se toma con la camara
sino que se elige de la galeria -- el test de velocidad ES una captura, y sin
la marca la app abre la camara y el tecnico tiene que fotografiar la pantalla
de otro telefono.

LAS DOS PUNTAS ESTABAN ROTAS. `componer` no leia `es_captura` de lo que
manda el editor, asi que el guardado la tiraba; y `leer_definicion` no la
devolvia, asi que la casilla abria destildada aunque la plantilla la tuviera.
El flag solo sobrevivia en las plantillas que nacen en codigo.

ES EL AGUJERO DE D7, otra vez: lo que esas dos funciones no nombran, se borra
en silencio al republicar. El mismo que el rango bueno esquivo esa mañana.

QUE AFIRMA ESTA GUARDA
----------------------
  · que la marca sobreviva a UNA VUELTA COMPLETA leer -> publicar -> leer,
    que es lo que hace el boton «Guardar en la plantilla». Probar solo una de
    las dos funciones deja pasar el defecto entero
  · que sobreviva a DOS vueltas: un borrado puede tardar un guardado mas
  · que la foto que NO es captura siga sin serlo -- marcarlas todas seria el
    otro defecto
  · y que la marca llegue al esquema, que es lo que la app lee
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def _tipo(org, codigo="corr_cap"):
    from campo.models import WorkType

    return WorkType.objects.create(org=org, codigo=codigo, nombre="Soporte",
                                   labor="correctivo")


DEFINICION = {
    "campos": [],
    "evidencias": [
        {"titulo": "Test de velocidad", "obligatorio": True,
         "instrucciones": "Descarga, subida y ping legibles.",
         "es_captura": True},
        {"titulo": "Daño encontrado", "obligatorio": True,
         "instrucciones": "El conector o la roseta afectada.",
         "es_captura": False},
    ],
}


def _captura_de(evidencias, titulo):
    fila = next(e for e in evidencias if e.get("titulo") == titulo)
    return fila.get("es_captura")


# ---------------------------------------------------------------------------
#  LA VUELTA COMPLETA
# ---------------------------------------------------------------------------

def test_la_marca_SOBREVIVE_a_guardar_y_volver_a_abrir(org_a):
    """Leer -> publicar -> leer: lo que hace «Guardar en la plantilla»."""
    from campo import plantillas as P

    tipo = _tipo(org_a)
    version, _ = P.publicar(tipo, DEFINICION)

    definicion, motivos = P.leer_definicion(version.esquema)

    assert not motivos, motivos
    assert _captura_de(definicion["evidencias"], "Test de velocidad") is True
    assert _captura_de(definicion["evidencias"], "Daño encontrado") is False


def test_la_marca_SOBREVIVE_A_DOS_guardados(org_a):
    """Un borrado silencioso puede tardar una vuelta mas en aparecer."""
    from campo import plantillas as P

    tipo = _tipo(org_a, "corr_cap2")
    v1, _ = P.publicar(tipo, DEFINICION)
    leida, _ = P.leer_definicion(v1.esquema)
    v2, _ = P.publicar(tipo, leida)
    otra_vez, _ = P.leer_definicion(v2.esquema)
    v3, _ = P.publicar(tipo, otra_vez)

    final, motivos = P.leer_definicion(v3.esquema)

    assert not motivos, motivos
    assert _captura_de(final["evidencias"], "Test de velocidad") is True


def test_la_marca_LLEGA_AL_ESQUEMA_que_lee_la_app(org_a):
    """La app no lee la definicion del editor: lee el esquema publicado."""
    from campo import plantillas as P

    tipo = _tipo(org_a, "corr_cap3")
    version, _ = P.publicar(tipo, DEFINICION)

    evidencias = version.esquema["evidencias"]

    assert _captura_de(evidencias, "Test de velocidad") is True
    #  La que no es captura no escribe la clave: un esquema que marca todas
    #  manda a la galeria una foto que hay que tomar en el momento.
    danio = next(e for e in evidencias if e["titulo"] == "Daño encontrado")
    assert not danio.get("es_captura"), danio


def test_destildarla_TAMBIEN_se_guarda(org_a):
    """Que se guarde el si no prueba que se guarde el no."""
    from campo import plantillas as P

    tipo = _tipo(org_a, "corr_cap4")
    v1, _ = P.publicar(tipo, DEFINICION)
    leida, _ = P.leer_definicion(v1.esquema)
    for e in leida["evidencias"]:
        e["es_captura"] = False
    v2, _ = P.publicar(tipo, leida)

    final, _ = P.leer_definicion(v2.esquema)

    assert _captura_de(final["evidencias"], "Test de velocidad") is False


def test_una_plantilla_SIN_la_clave_no_rompe(org_a):
    """Las que ya estan publicadas no la traen."""
    from campo import plantillas as P

    tipo = _tipo(org_a, "corr_cap5")
    sin_clave = {"campos": [], "evidencias": [
        {"titulo": "Daño encontrado", "obligatorio": True}]}
    version, _ = P.publicar(tipo, sin_clave)

    definicion, motivos = P.leer_definicion(version.esquema)

    assert not motivos, motivos
    assert _captura_de(definicion["evidencias"], "Daño encontrado") is False
