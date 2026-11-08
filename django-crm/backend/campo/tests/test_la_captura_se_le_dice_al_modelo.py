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

    assert "captura de pantalla" in texto, texto
    assert "NADA de eso es motivo de atencion" in texto, texto


def test_la_instruccion_de_la_plantilla_SIGUE_LLEGANDO_entera(org_a):
    """La marca se suma; no reemplaza lo que la empresa escribio."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=702))

    assert INSTRUCCION in texto, texto
    assert texto.startswith("Esta foto tenia que mostrar: Test de velocidad."), \
        texto


def test_la_foto_de_otra_pantalla_TAMBIEN_vale(org_a):
    """08/11/2026, decision del usuario: «el test de velocidad debe permitir
    foto a otra pantalla o captura, porque a veces se toma la foto para el
    test». Es el uso real -- el speedtest corre en el telefono del cliente.

    No contradice el pedido del dia anterior («que siga distinguiendo»): se
    sigue pidiendo que diga CUAL de las dos es. Lo que cambia es que no
    levanta atencion por eso."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=703))

    assert "foto tomada de otra pantalla" in texto, texto
    assert "las dos" in texto, texto
    #  Y SE SIGUE DISTINGUIENDO: se le pide que diga cual parece.
    assert "Deci cual de las dos" in texto, texto


def test_lo_UNICO_que_marca_es_que_no_se_lean_los_numeros(org_a):
    """Una captura perfecta de la que no se lee la velocidad no sirve; una
    foto torcida de la que se lee todo, si."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=708))

    #  LA CONDICION ENTERA, no su comienzo: la primera version afirmaba
    #  solo «SOLO si los numeros» y la mutacion que invierte el final
    #  --«se leen perfecto»-- sobrevivia, porque el principio seguia ahi.
    esperado = "SOLO si los numeros que se pedian no se pueden leer"
    assert esperado in texto, texto


def test_una_captura_SIN_instrucciones_tambien_la_recibe(org_a):
    """El camino del titulo solo. Si se olvidara ahi, el defecto aparece en
    la primera plantilla que no escribio instrucciones."""
    texto = _texto(_evidencia(org_a, es_captura=True, numero=704,
                              instrucciones=""))

    assert "captura de pantalla" in texto, texto
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
