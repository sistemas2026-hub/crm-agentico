# -*- coding: utf-8 -*-
"""
================================================================================
 «NO PUDE MIRAR» NO ES «NO HABÍA NADA QUE MIRAR»
================================================================================

Por qué existe
--------------
`operaciones/supervisor.py` lleva un comentario encabezado **«LA CUARTA VEZ DEL
MISMO ERROR»**, y el error es siempre el mismo: una lista vacía que significa
dos cosas incompatibles y nadie puede distinguirlas.

Esta es la quinta, encontrada el 20/10/2026. `_tickets_abiertos_con_tecnico`
le pide el mapa de áreas a `criterio_de_area()`, que sale **por HTTP al motor**.
Si el motor no contesta, el mapa vuelve vacío, se trata como «no se pudo»
—correcto, es fail-closed— y el detector devuelve `[]`. `detectar()` hace
`extend()` sobre quince detectores, así que ese `[]` se funde con los demás y
el informe se quedaba callado.

Para quien lee el resumen, **«el motor está caído» y «no hay tickets que leer»
eran el mismo cero**. De madrugada eso significa que el único camino que sale
de LEER —y no de medir— deja de producir en silencio.

Qué afirma
----------
Sobre el EFECTO: con el motor mudo, el informe **lo dice**; con el motor
contestando, **no lo dice**. Las dos mitades, porque afirmar solo la primera no
distingue «lo reporta cuando toca» de «lo reporta siempre».

    pytest operaciones/tests/test_no_pude_mirar_no_es_nada_que_mirar.py
================================================================================
"""

import datetime as dt

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


def _informe(org, monkeypatch, *, mapa):
    """Corre la lectura de tickets con el mapa de áreas que se le diga.

    Se sustituye `area_por_persona`, que es la LECTURA que sale al motor, y no
    `criterio_de_area`, que es la DECISIÓN: así el criterio real corre sobre el
    mapa que se le da, en vez de quedar sustituido él mismo.
    """
    from operaciones import areas_del_tenant, supervisor

    monkeypatch.setattr(areas_del_tenant, "area_por_persona", lambda: mapa)
    return supervisor._leer_tickets_abiertos(org, timezone.now())


def test_a_sin_mapa_el_informe_dice_que_no_pudo_mirar(org_a, monkeypatch):
    """El motor no contesta -> el informe lo NOMBRA."""
    informe = _informe(org_a, monkeypatch, mapa={})

    assert "no_se_pudo_mirar" in informe, (
        "con el mapa de áreas vacío el informe se quedó callado: "
        "«el motor está caído» vuelve a ser indistinguible de «no hay tickets»"
    )
    #  Y DICE QUÉ, no solo que sí. Un booleano manda a buscar; una frase dice
    #  dónde. Es la misma razón por la que `correr_ciclo` devuelve
    #  `no_cerrados_por` y no un contador.
    assert "areas" in informe["no_se_pudo_mirar"], informe["no_se_pudo_mirar"]
    assert "motor" in informe["no_se_pudo_mirar"], informe["no_se_pudo_mirar"]


def test_b_con_mapa_el_informe_NO_lo_dice(org_a, admin_profile, monkeypatch):
    """La otra mitad, y sin ella la prueba no vale.

    Afirmar solo que aparece cuando el mapa falta no distingue «lo reporta
    cuando toca» de «lo reporta siempre». Un aviso que aparece siempre es ruido,
    y en pocas vueltas nadie lo lee -- que es justo cómo este error sobrevivió
    cuatro veces.
    """
    informe = _informe(org_a, monkeypatch,
                       mapa={str(admin_profile.id): "soporte_tecnico"})

    assert "no_se_pudo_mirar" not in informe, (
        "con el mapa presente el informe igual dice que no pudo mirar: "
        f"{informe.get('no_se_pudo_mirar')!r}"
    )


def test_c_la_lista_vacia_sigue_significando_vacia(org_a, admin_profile,
                                                   monkeypatch):
    """Con mapa y sin tickets, el informe sigue siendo un cero legítimo.

    El arreglo NO puede convertir «no hay nada que leer» en una alarma: eso
    sería el mismo error al revés, y el costo es idéntico -- un aviso que
    aparece sin motivo deja de leerse.
    """
    informe = _informe(org_a, monkeypatch,
                       mapa={str(admin_profile.id): "soporte_tecnico"})

    assert informe.get("tickets") == {}, informe
    assert "no_se_pudo_mirar" not in informe
