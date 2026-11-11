# -*- coding: utf-8 -*-
"""Habilitar «Otro» publica una versión nueva y no toca las viejas.

POR QUE ESTE ARCHIVO EXISTE  --  11/11/2026. El comando se escribió, se
verificó que parseaba, que importaba y que Django lo registraba, y se mandó a
producción. **Falló las dos primeras corridas**: una por leer las opciones de
una sola de las dos claves posibles, otra por llamar `opciones` a dos cosas
distintas en la misma función. Ninguno de los dos errores sobrevive a
ejecutarlo una vez; los dos sobrevivieron a «parsea e importa».

Es `PARSEA != IMPORTA != FUNCIONA` con los tres escalones medidos de a uno, y
el tercero cobrándoselo a quien estaba del otro lado de la terminal.
"""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


def _tipo(org, *, campo: dict, codigo: str = "prueba_otro"):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre="Prueba",
                                   activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [campo], "evidencias": []})
    return tipo


def _correr(org, tipo, campo, aplicar=False):
    salida = io.StringIO()
    call_command("permitir_otro", org=str(org.id), tipo=tipo.codigo,
                 campo=campo, aplicar=aplicar, stdout=salida)
    return salida.getvalue()


SELECCION_CON_REGLAS = {
    "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
    #  LA FORMA QUE ROMPIO LA PRIMERA CORRIDA: las opciones viven en
    #  `reglas.options`, no en `opciones`. Las dos existen en producción según
    #  cómo se creó la plantilla, y `plantillas.py` contempla las dos.
    "reglas": {"options": ["Conector sucio", "Fibra partida", "Roseta"]},
}


# --------------------------------------------------------------------------- #
# A. Lo que hace
# --------------------------------------------------------------------------- #
def test_a1_el_simulacro_no_publica_nada(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    salida = _correr(org_a, tipo, "que_encontro")

    assert "SIMULACRO" in salida
    assert "3 opciones" in salida, f"lee las opciones de `reglas`: {salida}"
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_a2_al_aplicar_publica_una_version_nueva(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    versiones = list(WorkTypeVersion.objects.filter(work_type=tipo)
                     .order_by("version"))
    assert [v.version for v in versiones] == [1, 2]
    nuevo = [c for c in versiones[-1].esquema["campos"]
             if c["id"] == "que_encontro"][0]
    assert nuevo.get("permite_otro") is True


def test_a3_LA_VIEJA_NO_SE_TOCA(org_a):
    #  Una orden congela su versión al nacer. Si la v1 cambiara, le estaríamos
    #  cambiando el formulario a órdenes que ya tienen respuestas escritas
    #  --incluso cerradas--. Es la razón entera de publicar en vez de editar.
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    v1 = WorkTypeVersion.objects.get(work_type=tipo, version=1)
    viejo = [c for c in v1.esquema["campos"] if c["id"] == "que_encontro"][0]
    assert not viejo.get("permite_otro"), "la v1 quedó como estaba"


def test_a4_correrlo_dos_veces_no_publica_una_tercera(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)
    salida = _correr(org_a, tipo, "que_encontro", aplicar=True)

    #  «v3» igual a «v2» solo ensuciaría la historia y haría creer que algo
    #  cambió.
    assert "YA lo tiene" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2


# --------------------------------------------------------------------------- #
# B. Lo que se niega a hacer
# --------------------------------------------------------------------------- #
def test_b1_un_campo_sin_opciones_no_se_marca(org_a):
    #  «Otro» en un campo de texto no significa nada, y el validador lo
    #  rechazaría después — con una versión de más ya publicada.
    tipo = _tipo(org_a, campo={"id": "nota", "titulo": "Nota", "tipo": "texto"})

    with pytest.raises(CommandError, match="no tiene opciones"):
        _correr(org_a, tipo, "nota", aplicar=True)

    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_b2_un_campo_que_no_existe_lo_dice_y_lista_los_que_hay(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    with pytest.raises(CommandError) as e:
        _correr(org_a, tipo, "campo_inventado")

    #  Decir «no existe» y no cuál hay obliga a salir a buscar el esquema a
    #  mano, que es lo que el mensaje debería evitar.
    assert "que_encontro" in str(e.value)


def test_b3_una_plantilla_que_no_existe_no_revienta(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))
    tipo.codigo = "no_existe_este_codigo"

    with pytest.raises(CommandError, match="no existe"):
        _correr(org_a, tipo, "que_encontro")


# --------------------------------------------------------------------------- #
# C. La otra forma del dato
# --------------------------------------------------------------------------- #
def test_c1_tambien_lee_las_opciones_de_la_clave_vieja(org_a):
    #  La otra mitad de lo que rompió la primera corrida: hay plantillas con
    #  las opciones en `opciones` y otras en `reglas.options`.
    tipo = _tipo(org_a, campo={
        "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
        "opciones": ["Uno", "Dos"],
    })

    salida = _correr(org_a, tipo, "que_encontro")

    assert "2 opciones" in salida, salida
