# -*- coding: utf-8 -*-
"""
================================================================================
 UNA CAPTURA NO ES LO MISMO QUE UNA FOTO DE OTRA PANTALLA  --  07/11/2026
================================================================================
El usuario, afinando la instruccion de «Daño encontrado» y viendo que el
modelo levantaba ATENCION por «es foto de una pantalla»:

    «que siga distinguiendo entre una foto a otra pantalla y captura»

Y son dos cosas distintas que el modelo no tenia como separar: en las dos ve
pixeles de pantalla. Una CAPTURA es legitima --el test de velocidad ES una
captura, por eso `es_captura` existe en la plantilla-- y una foto tomada DE
otra pantalla es sospechosa: puede ser el trabajo de otro, o una impresion.

La diferencia no la puede inventar el modelo. La sabe la plantilla, que ya
la declara. Lo unico que faltaba era decirsela.

QUE AFIRMA ESTA GUARDA
----------------------
  · que a una evidencia declarada captura se le diga, y en el MISMO envoltorio
    que ya lleva las instrucciones --no en otro lado, porque las reglas 7 y 12
    del prompt disparan sobre ese texto
  · que a las demas NO se les diga nada: la sospecha tiene que quedar intacta
    donde la empresa no declaro nada, que es lo que el usuario pidio conservar
  · que aun siendo captura se siga pidiendo marcar la foto TOMADA de otra
    pantalla -- aflojar una cosa no es aflojar las dos
  · y que el texto de la plantilla siga llegando entero
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

INSTRUCCION = "Descarga, subida y ping legibles."


def _evidencia(org, *, es_captura, numero, instrucciones=INSTRUCCION):
    from campo.models import (EvidenciaTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    foto = {"id": "test_de_velocidad", "tipo": "foto",
            "titulo": "Test de velocidad", "obligatorio": True}
    if instrucciones:
        foto["instrucciones"] = instrucciones
    if es_captura:
        foto["es_captura"] = True

    wt = WorkType.objects.create(org=org, codigo=f"cap{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [foto]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.EN_SITIO, origen_sistema="manual")
    return EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="test_de_velocidad",
        vuelta=orden.vuelta, sha256=f"c{numero}".ljust(64, "x")[:64],
        storage_key=f"k/c{numero}", nombre_original="captura.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)


def _texto(evidencia):
    from campo.inspeccion_visual import que_tenia_que_mostrar

    return que_tenia_que_mostrar(evidencia)


# ---------------------------------------------------------------------------
#  CUANDO LA EMPRESA LO DECLARO
# ---------------------------------------------------------------------------

def test_a_una_CAPTURA_se_le_dice_que_lo_es(org_a):
    texto = _texto(_evidencia(org_a, es_captura=True, numero=701))

    assert "ES una captura" in texto, texto
    assert "no es motivo de atencion" in texto, texto


def test_la_instruccion_de_la_plantilla_SIGUE_LLEGANDO_entera(org_a):
    """La marca se suma; no reemplaza lo que la empresa escribio."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=702))

    assert INSTRUCCION in texto, texto
    assert texto.startswith("Esta foto tenia que mostrar: Test de velocidad."), \
        texto


def test_aun_siendo_captura_SE_SIGUE_PIDIENDO_marcar_la_foto_de_otra_pantalla(org_a):
    """Aflojar una cosa no es aflojar las dos."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=703))

    assert "TOMADA de otra pantalla" in texto, texto
    assert "impresion" in texto, texto


def test_una_captura_SIN_instrucciones_tambien_la_recibe(org_a):
    """El camino del titulo solo. Si se olvidara ahi, el defecto aparece en
    la primera plantilla que no escribio instrucciones."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=704,
                              instrucciones=""))

    assert "ES una captura" in texto, texto
    assert "Test de velocidad" in texto, texto


# ---------------------------------------------------------------------------
#  CUANDO NO
# ---------------------------------------------------------------------------

def test_a_una_foto_COMUN_no_se_le_dice_nada(org_a):
    """La sospecha queda intacta donde la empresa no declaro nada."""
    texto = _texto(_evidencia(org_a, es_captura=False, numero=705))

    assert "captura" not in texto.lower(), texto
    assert texto.endswith(INSTRUCCION), texto


def test_una_foto_comun_SIN_instrucciones_tampoco(org_a):
    texto = _texto(_evidencia(org_a, es_captura=False, numero=706,
                              instrucciones=""))

    assert texto == "Esta foto tenia que mostrar: Test de velocidad.", texto
