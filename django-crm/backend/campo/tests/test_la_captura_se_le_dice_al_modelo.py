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


def _de_galeria(evidencia, valor=True):
    """La app marca asi la imagen que no salio de la camara (09/11/2026)."""
    evidencia.metadatos_captura = {"de_galeria": valor}
    evidencia.save(update_fields=["metadatos_captura"])
    return evidencia


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

# ---------------------------------------------------------------------------
#  LA CAPTURA QUE NADIE DECLARO: LA IMAGEN ELEGIDA DE LA GALERIA
#  --  20/11/2026, OT #281
# ---------------------------------------------------------------------------
#  El usuario adjunto una captura en vez de una foto y la orden volvio
#  devuelta, con la regla general ya desplegada. La app marca `de_galeria`, y
#  una captura solo puede entrar por ahi: a ESA imagen se le dice, junto a la
#  foto, que ser captura no la frena.

def test_a_la_imagen_de_GALERIA_se_le_dice_que_una_captura_vale(org_a):
    texto = _texto(_de_galeria(_evidencia(org_a, es_captura=False, numero=710)))

    assert "puede ser una captura de pantalla" in texto, texto
    assert "NO es motivo de atencion ni de 'MUESTRA: no'" in texto, texto
    assert "si en ella se ve lo que se pedia, es 'MUESTRA: si'" in texto, texto
    #  En el MISMO envoltorio: las reglas 7 y 12 disparan por el prefijo.
    assert texto.startswith("Esta foto tenia que mostrar: Test de velocidad. "
                            + INSTRUCCION), texto


def test_la_de_galeria_que_muestra_OTRA_COSA_se_sigue_marcando(org_a):
    """El caso del 06/11 --el sistema de tickets donde iba el test-- tiene
    que seguir volviendo: se afloja el formato, no el contenido."""
    texto = _texto(_de_galeria(_evidencia(org_a, es_captura=False, numero=711)))

    assert "Marca solo si lo que muestra es otra cosa o no se distingue" in texto, texto


def test_la_de_galeria_SIN_instrucciones_tambien_lo_recibe(org_a):
    """La plantilla base de «Daño encontrado» no trae instrucciones."""
    texto = _texto(_de_galeria(_evidencia(org_a, es_captura=False, numero=712,
                                          instrucciones="")))

    assert texto.startswith("Esta foto tenia que mostrar: Test de velocidad."), texto
    assert "puede ser una captura de pantalla" in texto, texto


def test_a_la_foto_de_CAMARA_no_se_le_dice_nada(org_a):
    """De la camara no sale una captura. Y solo vale el `True` de la app."""
    for numero, valor in ((713, False), (714, "true"), (715, 1), (716, None)):
        texto = _texto(_de_galeria(
            _evidencia(org_a, es_captura=False, numero=numero), valor))

        assert "captura" not in texto.lower(), (valor, texto)
        assert texto.endswith(INSTRUCCION), (valor, texto)


def test_la_DECLARADA_captura_conserva_su_propio_texto(org_a):
    """El test de velocidad acepta ademas la foto a otra pantalla (08/11):
    que venga de la galeria no puede cambiarle ese pie por el mas angosto."""
    texto = _texto(_de_galeria(_evidencia(org_a, es_captura=True, numero=717)))

    assert "foto tomada de otra pantalla" in texto, texto
    assert "se eligio de la galeria" not in texto, texto
