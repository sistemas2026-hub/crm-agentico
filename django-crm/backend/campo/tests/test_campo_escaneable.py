# -*- coding: utf-8 -*-
"""Marcar un campo como leíble con la cámara publica una versión, y nada más.

POR QUE ESTE ARCHIVO EXISTE  --  12/11/2026
-------------------------------------------
El comando hermano (`permitir_otro`) se escribió, se verificó que parseaba, que
importaba y que Django lo registraba, y falló **las dos primeras corridas
contra producción**. Ninguno de esos dos errores sobrevive a ejecutarlo una
vez; los dos sobrevivieron a «parsea e importa».

Así que este se ejecuta acá antes de ir a ninguna parte.

LO QUE SE AFIRMA ES EL EFECTO: que la bandera quede en el esquema publicado y
que NO quede en ningún otro lado. El defecto simétrico es igual de malo: una
cámara en cada campo de texto ensucia los formularios de todas las empresas, y
una bandera publicada en un campo donde la app la ignora gasta una versión y
deja a quien la pidió creyendo que la tiene.
"""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

TEXTO = {"id": "serial_de_la_onu", "titulo": "Serial de la ONU",
         "tipo": "texto", "reglas": {"required": True},
         "ayuda": "El de la etiqueta del equipo instalado."}

NUMERO = {"id": "potencia_en_la_roseta", "titulo": "Potencia en la roseta",
          "tipo": "decimal", "unidad": "dBm",
          "reglas": {"required": True, "min": -28.0, "max": -8.0}}

SELECCION = {"id": "que_encontro", "titulo": "Qué encontró",
             "tipo": "seleccion",
             "reglas": {"options": ["Conector sucio", "Fibra partida"]}}


def _tipo(org, *, campos, codigo: str = "prueba_escaneable"):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre="Prueba",
                                   activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": list(campos), "evidencias": []})
    return tipo


def _correr(org, tipo, campo, aplicar=False):
    salida = io.StringIO()
    call_command("campo_escaneable", org=str(org.id), tipo=tipo.codigo,
                 campo=campo, aplicar=aplicar, stdout=salida)
    return salida.getvalue()


def _vigente(tipo):
    return (WorkTypeVersion.objects
            .filter(work_type=tipo, estado=WorkTypeVersion.PUBLICADA)
            .order_by("-version").first())


# --------------------------------------------------------------------------- #
# A. Lo que hace
# --------------------------------------------------------------------------- #
def test_a1_el_simulacro_no_publica_nada(org_a):
    tipo = _tipo(org_a, campos=[TEXTO])
    salida = _correr(org_a, tipo, "serial_de_la_onu")

    assert "SIMULACRO" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1
    assert "escaneable" not in _vigente(tipo).esquema["campos"][0]


def test_a2_al_aplicar_publica_una_version_nueva_con_la_bandera(org_a):
    tipo = _tipo(org_a, campos=[TEXTO])
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)

    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2
    v = _vigente(tipo)
    assert v.version == 2
    assert v.esquema["campos"][0]["escaneable"] is True


def test_a3_LA_VIEJA_NO_SE_TOCA(org_a):
    #  Una orden que nació con la v1 sigue leyendo la v1: las versiones son
    #  inmutables y de eso depende que publicar no cambie lo que ya salió.
    tipo = _tipo(org_a, campos=[TEXTO])
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)

    v1 = WorkTypeVersion.objects.get(work_type=tipo, version=1)
    assert "escaneable" not in v1.esquema["campos"][0]


def test_a4_correrlo_dos_veces_no_publica_una_tercera(org_a):
    tipo = _tipo(org_a, campos=[TEXTO])
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)
    salida = _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)

    assert "YA lo tiene" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2


def test_a5_NO_TOCA_NADA_MAS_DEL_ESQUEMA(org_a):
    #  LA AFIRMACION CENTRAL. Un comando que habilita una cámara no puede
    #  reescribir el formulario de paso: ni los otros campos, ni las reglas
    #  del que marca, ni las evidencias.
    tipo = _tipo(org_a, campos=[TEXTO, NUMERO, SELECCION])
    antes = _vigente(tipo).esquema
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)
    despues = _vigente(tipo).esquema

    assert despues["campos"][0].pop("escaneable") is True
    assert despues == antes, "la única diferencia tenía que ser la bandera"


# --------------------------------------------------------------------------- #
# B. Lo que se niega a hacer
# --------------------------------------------------------------------------- #
def test_b1_un_NUMERO_se_niega_y_no_publica(org_a):
    #  La app no dibuja el botón en un número --no hay etiqueta de código de
    #  barras con una medida de potencia, y la caja ya tiene el `dBm` a la
    #  derecha--. Publicarlo gastaría una versión sin cambiar nada.
    tipo = _tipo(org_a, campos=[NUMERO])
    with pytest.raises(CommandError) as e:
        _correr(org_a, tipo, "potencia_en_la_roseta", aplicar=True)

    assert "texto" in str(e.value)
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_b2_una_SELECCION_tambien_se_niega(org_a):
    tipo = _tipo(org_a, campos=[SELECCION])
    with pytest.raises(CommandError):
        _correr(org_a, tipo, "que_encontro", aplicar=True)

    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_b3_un_campo_que_no_existe_lo_dice_y_lista_los_que_hay(org_a):
    tipo = _tipo(org_a, campos=[TEXTO, NUMERO])
    with pytest.raises(CommandError) as e:
        _correr(org_a, tipo, "no_existe", aplicar=True)

    #  Que LISTE los que hay no es cortesía: el id de un campo no se adivina,
    #  y sin la lista hay que entrar a la base para encontrarlo.
    assert "serial_de_la_onu" in str(e.value)
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_b4_una_plantilla_que_no_existe_no_revienta(org_a):
    tipo = _tipo(org_a, campos=[TEXTO])
    with pytest.raises(CommandError) as e:
        call_command("campo_escaneable", org=str(org_a.id), tipo="no_existe",
                     campo="serial_de_la_onu", aplicar=True,
                     stdout=io.StringIO())
    assert "no existe" in str(e.value)
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


# --------------------------------------------------------------------------- #
# C. La forma que la app lee
# --------------------------------------------------------------------------- #
def test_c1_la_bandera_queda_DONDE_LA_APP_LA_LEE(org_a):
    #  La app hace `campo['escaneable'] == true` sobre cada campo del esquema
    #  (`campo_del_formulario.dart`). No en `reglas`, no en la raíz del
    #  esquema: en el campo. Una bandera en el lugar equivocado sería
    #  invisible, y la versión publicada diría que está.
    tipo = _tipo(org_a, campos=[TEXTO])
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)
    campo = _vigente(tipo).esquema["campos"][0]

    assert campo.get("escaneable") is True
    assert "escaneable" not in (campo.get("reglas") or {})
    assert "escaneable" not in _vigente(tipo).esquema


def test_c2_solo_el_campo_pedido_queda_escaneable(org_a):
    tipo = _tipo(org_a, campos=[TEXTO, dict(TEXTO, id="otro_texto",
                                            titulo="Comentarios")])
    _correr(org_a, tipo, "serial_de_la_onu", aplicar=True)
    campos = _vigente(tipo).esquema["campos"]

    assert campos[0].get("escaneable") is True
    assert "escaneable" not in campos[1], (
        "marcar uno no puede marcar todos los de texto: «Comentarios» no se "
        "lee de ninguna etiqueta")
