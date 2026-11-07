# -*- coding: utf-8 -*-
"""
================================================================================
 LA CACHE TIENE QUE SER COMPARTIDA, O NO ES UNA CACHE
================================================================================

DE DONDE SALE
-------------
"Sin ejecutar ciclo recargo la pagina y los datos no salen dentro de un tiempo".
Esa frase, del 14/10/2026, descarto la explicacion que se venia dando --que los
indicadores competian con el ciclo-- y dejo ver la de verdad.

Los indicadores del Supervisor corren 'detectar()' entero para pintarse: 771
tickets, 18 tipos de hallazgo. Medido el 13/10/2026: 22 segundos. Se le habia
puesto una ventana de cinco minutos... sobre 'LocMemCache', que es la memoria
LOCAL de cada proceso, porque el proyecto no declaraba 'CACHES'.

El backend corre con varios procesos y el worker con otro. Cada uno guardaba su
copia, asi que la pantalla salia rapida o tardaba 22 segundos SEGUN A QUIEN LE
TOCARA ATENDER. No era intermitencia: era loteria de proceso.

LO QUE AFIRMA, Y POR QUE ASI
----------------------------
Que la cache configurada NO es la de memoria local, y que el ciclo deja sus
señales donde la pantalla las busca. Afirma sobre el EFECTO --lo guardado se
lee-- y no sobre que tal clase este en el settings: un backend cambiado a otra
cosa que tampoco comparta pasaria una prueba escrita sobre el nombre.
================================================================================
"""

import pytest
from django.core.cache import cache
from django.utils import timezone

from operaciones import indicadores

pytestmark = pytest.mark.django_db


def test_PRODUCCION_no_usa_la_cache_de_un_solo_proceso():
    """
    'LocMemCache' no se comparte entre procesos. Con gunicorn en varios y el
    worker aparte, cada uno guarda la suya -- y lo que para uno esta caliente,
    para el siguiente no existe.

    SE MIRA 'crm/settings.py' Y NO 'settings' A SECAS: las pruebas corren con
    'crm.test_settings', que usa la cache en memoria a proposito --no hay Redis
    en el entorno de pruebas y no deberia hacer falta--. Preguntarle a la
    configuracion ACTIVA daria siempre "local" y la guarda seria un adorno que
    nunca puede fallar.
    """
    from pathlib import Path

    crudo = (Path(__file__).resolve().parents[2] / "crm" / "settings.py").read_text(
        encoding="utf-8")
    #  SIN LOS COMENTARIOS. La primera version de esta guarda fallo contra su
    #  propio texto: el comentario que explica POR QUE no se usa 'LocMemCache'
    #  nombra 'LocMemCache', y la busqueda no distinguia codigo de prosa.
    texto = " ".join(ln for ln in crudo.splitlines()
                     if not ln.lstrip().startswith("#"))

    assert "CACHES" in texto, (
        "produccion no declara CACHES: Django cae a la cache LOCAL de cada "
        "proceso, y la pantalla sale rapida o tarda 22 segundos segun a quien "
        "le toque atender")
    assert "locmem" not in texto.lower(), (
        "produccion quedo con la cache local al proceso")
    assert "RedisCache" in texto, (
        "la cache de produccion dejo de ser compartida")


def test_lo_que_guarda_el_ciclo_es_lo_que_lee_la_pantalla(org_a):
    """
    LA MISMA CLAVE EN LOS DOS LADOS, medido por el efecto.

    Si el ciclo guardara en una clave y la pantalla leyera de otra, las dos
    mitades estarian "bien" por separado y la pantalla recalcularia igual --
    que es exactamente la clase de error que este archivo vino a cerrar.
    """
    cache.delete(f"senales_vigentes:{org_a.id}")
    indicadores.refrescar_senales(org_a, ["una-senal-de-prueba"],
                                  timezone.now())

    leido = indicadores._senales_con_ventana(org_a, timezone.now())
    assert leido == ["una-senal-de-prueba"], (
        "lo que dejo el ciclo no es lo que encuentra la pantalla: va a "
        "recalcular los 22 segundos igual")


def test_la_ventana_cubre_el_hueco_entre_dos_ciclos(org_a):
    """
    El ciclo corre cada 60 minutos. Si la ventana durara menos, vencería entre
    corrida y corrida y el recalculo le tocaria a quien abra la pantalla --
    que es lo que pasaba con los cinco minutos originales.
    """
    assert indicadores.SEGUNDOS_DE_VENTANA_DE_DETECCION > 60 * 60, (
        "la ventana no cubre la hora entre ciclos: va a vencer en el medio y "
        "el recalculo lo paga la persona que esta mirando")


def test_si_la_cache_falla_se_calcula_y_no_se_miente(org_a, monkeypatch):
    """
    Un indicador que desaparece porque la cache no esta seria PEOR que uno
    lento: el tablero diria "cero hallazgos", que es una afirmacion, no un
    hueco. Se conserva ese contrato.
    """
    def _revienta(*a, **k):
        raise RuntimeError("redis caido")

    monkeypatch.setattr("django.core.cache.cache.get", _revienta)
    llamadas = {"n": 0}

    def _detectar(org, ahora):
        llamadas["n"] += 1
        return ["calculado-a-mano"]

    monkeypatch.setattr(indicadores.m09, "detectar", _detectar)

    r = indicadores._senales_con_ventana(org_a, timezone.now())
    assert r == ["calculado-a-mano"] and llamadas["n"] == 1
