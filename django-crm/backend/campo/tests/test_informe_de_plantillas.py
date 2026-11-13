# -*- coding: utf-8 -*-
"""El informe de plantillas CORRE, y dice las tres cosas por las que existe.

POR QUE SE PRUEBA UN COMANDO DE SOLO LECTURA  --  12/11/2026
------------------------------------------------------------
Porque `permitir_otro` se escribio, se verifico que parseaba, que importaba y
que Django lo registraba, y fallo las dos primeras corridas contra produccion.
Un comando que nadie ejecuto no esta probado, y este se corre en la terminal
del servidor donde un error no cuesta un rojo: cuesta el tiempo de quien esta
del otro lado.

Y NO IMPRIME DATOS DE CLIENTE: la ultima prueba lo afirma, porque un informe
que se pega en una conversacion es exactamente el camino por el que un
domicilio termina en un historial de chat.
"""
import io

import pytest
from django.core.management import call_command

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


def _tipo(org, *, codigo, labor, campos, activo=True):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor=labor, activo=activo)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": list(campos), "evidencias": []})
    return tipo


SERIAL = {"id": "serial_de_la_onu", "titulo": "Serial de la ONU",
          "tipo": "texto", "reglas": {"required": True}}
POTENCIA = {"id": "potencia_en_la_roseta", "titulo": "Potencia en la roseta",
            "tipo": "decimal", "unidad": "dBm",
            "bueno": {"min": -28.0, "max": -8.0}}


def _correr(org=None):
    salida = io.StringIO()
    call_command("informe_de_plantillas",
                 **({"org": str(org.id)} if org else {}), stdout=salida)
    return salida.getvalue()


def test_a1_dice_el_id_de_cada_campo(org_a):
    #  LA RAZON PRINCIPAL: el id no es el titulo, y los tres comandos que
    #  editan una plantilla lo piden.
    _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
          campos=[SERIAL, POTENCIA])
    salida = _correr(org_a)

    assert "serial_de_la_onu" in salida
    assert "potencia_en_la_roseta" in salida
    assert "Serial de la ONU" in salida


def test_a2_dice_si_una_plantilla_esta_o_no(org_a):
    _tipo(org_a, codigo="traslado_servicio", labor="instalacion", campos=[SERIAL])
    salida = _correr(org_a)

    assert "traslado_servicio" in salida
    assert "instalacion_fibra" not in salida, (
        "lo que NO esta tiene que poder verse por su ausencia: es la pregunta "
        "«la adoptamos o no»")


def test_a3_AVISA_cuando_una_labor_tiene_mas_de_una_plantilla(org_a):
    #  EL CASO QUE MUERDE SOLO. Con dos plantillas en la misma labor y ninguna
    #  declarando asuntos, `plantilla_del_caso` no elige NINGUNA y el
    #  Supervisor deja de crear ordenes de esa labor.
    _tipo(org_a, codigo="instalacion_fibra", labor="instalacion", campos=[SERIAL])
    _tipo(org_a, codigo="traslado_servicio", labor="instalacion", campos=[SERIAL])
    salida = _correr(org_a)

    assert "2 activa(s)" in salida
    assert "sus asuntos" in salida, "el aviso tiene que explicar el riesgo"


def test_a4_con_UNA_sola_no_avisa_nada(org_a):
    #  El control: un aviso que sale siempre es ruido y se deja de leer.
    _tipo(org_a, codigo="instalacion_fibra", labor="instalacion", campos=[SERIAL])
    salida = _correr(org_a)

    assert "1 activa(s)" in salida
    assert "sus asuntos" not in salida


def test_a5_marca_lo_que_ya_esta_configurado(org_a):
    tipo = _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
                 campos=[dict(SERIAL, escaneable=True), POTENCIA])
    salida = _correr(org_a)

    assert "camara" in salida, "si un campo ya se lee con la camara, se ve"
    assert "rango bueno" in salida
    assert tipo.codigo in salida


def test_a6_una_plantilla_INACTIVA_se_ve_y_se_distingue(org_a):
    _tipo(org_a, codigo="vieja", labor="trabajos", campos=[SERIAL], activo=False)
    salida = _correr(org_a)

    assert "INACTIVA" in salida
    #  Y NO CUENTA para el aviso de la labor: una plantilla dada de baja no
    #  compite por elegirse.
    assert "activa(s)" not in salida or "trabajos" not in salida.split("campo")[0]


def test_b1_NO_IMPRIME_DATOS_DE_CLIENTE(org_a):
    #  Un informe que se pega en una conversacion es el camino por el que un
    #  domicilio termina en un historial de chat. Este solo habla de
    #  plantillas.
    _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
          campos=[SERIAL, POTENCIA])
    salida = _correr(org_a).lower()

    for prohibido in ("cedula", "telefono", "direccion", "coordenada",
                      "password", "@"):
        assert prohibido not in salida, f"se colo «{prohibido}»"


def test_b2_una_empresa_sin_plantillas_no_ensucia_la_salida(org_a):
    salida = _correr(org_a)
    assert str(org_a.id) not in salida, (
        "sin plantillas no se imprime el encabezado: el informe se lee para "
        "encontrar algo, no para recorrer empresas vacias")


# --------------------------------------------------------------------------- #
# C. La linea de los asuntos  --  agregada el 12/11/2026, DESPUES del defecto
# --------------------------------------------------------------------------- #
#  LAS OCHO PRUEBAS DE ARRIBA PASABAN CON ESTA LINEA ROTA. La primera version
#  del comando hacia `t.asuntos.all()` --preguntandole a un JSONField como si
#  fuera una relacion-- dentro de un `except Exception` que imprimia «(sin la
#  tabla de asuntos)». Contra produccion salio eso en TODAS las plantillas: un
#  mensaje creible, que encima culpaba a la base.
#
#  Ninguna de las ocho afirmaba sobre esta linea. Afirmaban que el comando
#  corre, que lista ids, que avisa de las labores con dos plantillas -- todo
#  cierto, y el dato que decide si el Supervisor puede elegir plantilla salia
#  mal. Por eso estas tres existen.
def test_c1_los_asuntos_SE_IMPRIMEN(org_a):
    tipo = _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
                 campos=[SERIAL])
    tipo.asuntos = ["Instalacion Nueva", "Instatalacion Nueva"]
    tipo.save(update_fields=["asuntos"])

    salida = _correr(org_a)
    assert "Instalacion Nueva" in salida
    #  LAS DOS GRAFIAS: el catalogo de WispHub trae el typo como un valor
    #  DISTINTO, y si una plantilla declara una sola, los tickets de la otra
    #  no la encuentran.
    assert "Instatalacion Nueva" in salida


def test_c2_sin_asuntos_dice_NINGUNO_y_no_una_excusa(org_a):
    _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
          campos=[SERIAL])
    salida = _correr(org_a)

    assert "asuntos: NINGUNO" in salida
    #  EL CONTROL QUE MATA EL DEFECTO: el mensaje que culpaba a la base no
    #  puede volver. Si alguien reintroduce un `except` ahi, esto lo ve.
    assert "sin la tabla" not in salida


def test_c3_los_asuntos_salen_DE_LA_PLANTILLA_no_de_la_labor(org_a):
    #  Son dos cosas distintas y se confunden facil: `WorkType.asuntos` es un
    #  JSONField (`models.py:66`) y es el que lee `plantilla_para_asunto` al
    #  elegir; los asuntos de `Labor` son una relacion (`labores.py:111`) y los
    #  lista `informe_de_labores`. Este informe habla del primero.
    tipo = _tipo(org_a, codigo="instalacion_fibra", labor="instalacion",
                 campos=[SERIAL])
    tipo.asuntos = ["Lo que declara la plantilla"]
    tipo.save(update_fields=["asuntos"])

    salida = _correr(org_a)
    assert "Lo que declara la plantilla" in salida
