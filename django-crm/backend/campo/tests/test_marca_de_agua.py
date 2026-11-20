# -*- coding: utf-8 -*-
"""La marca de agua dice lo que se midio, y se niega a estampar lo que no.

NO SE AFIRMA QUE DIBUJE BONITO: se afirma que diga la verdad y que no pueda
costar una evidencia. Son dos familias de prueba y las dos importan igual:

  A  QUE DICE  -- las lineas se arman de lo que el sistema sabe, y las tres
     mentiras medidas no entran (galeria, sin GPS, ubicacion simulada)
  B  CUANDO NO  -- apagada, firma, captura, PDF: se devuelve EL ORIGINAL
  C  QUE NO ROMPE -- la imagen sigue siendo una imagen, y un fallo cualquiera
     devuelve los bytes de entrada en vez de perderlos

La C es la que mas vale. Una marca de agua que rompe una foto destruye la
prueba de un trabajo que ya se hizo y no se puede repetir: el tecnico se fue.
"""
import io

import pytest

from campo.services import marca_de_agua as M

pytestmark = []  # no pide base: es una funcion pura


# --------------------------------------------------------------------------- #
#  Imagenes de verdad, hechas acá: nada de archivos binarios en el repo
# --------------------------------------------------------------------------- #
def _imagen(ancho=1920, alto=1080, color=(40, 90, 160), formato="JPEG") -> bytes:
    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(salida, format=formato)
    return salida.getvalue()


def _png_con_transparencia() -> bytes:
    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGBA", (400, 300), (255, 0, 0, 128)).save(salida, format="PNG")
    return salida.getvalue()


def _abre(datos: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(datos))


TODO = {"activa": True, "mostrar_empresa": True, "mostrar_tecnico": True,
        "mostrar_coordenadas": True, "mostrar_fecha": True,
        "mostrar_logo": False, "opacidad": 55, "posicion": "abajo_izquierda"}


def _datos(**extra):
    from datetime import datetime, timezone

    base = {
        "empresa": "Rapilink SAS",
        "tecnico": "Carlos Pérez",
        "fecha": datetime(2026, 11, 12, 20, 30, tzinfo=timezone.utc),
        "mime_type": "image/jpeg",
        "metadatos_captura": {"lat": 10.9108, "lng": -74.8186,
                              "precision_m": 8},
    }
    base.update(extra)
    return base


# =========================================================================== #
#  A. QUE DICE
# =========================================================================== #
def test_a1_las_cuatro_lineas_salen_de_lo_que_el_sistema_sabe():
    lineas = M.lineas_de(TODO, _datos())
    texto = " | ".join(lineas)

    assert "Rapilink SAS" in texto
    assert "Carlos Pérez" in texto
    assert "10.910800" in texto and "-74.818600" in texto
    #  LA FECHA EN BOGOTA, NO EN UTC: 20:30 UTC son las 15:30 acá
    #  (CLAUDE.md §8: la base es UTC y se reporta en America/Bogotá).
    assert "12/11/2026 15:30" in texto, texto


def test_a2_lo_que_la_empresa_apaga_NO_aparece():
    config = dict(TODO, mostrar_tecnico=False, mostrar_coordenadas=False)
    texto = " | ".join(M.lineas_de(config, _datos()))

    assert "Rapilink SAS" in texto
    assert "Carlos" not in texto
    assert "10.9" not in texto


def test_a3_UNA_FOTO_DE_GALERIA_no_lleva_coordenadas():
    #  LA MENTIRA 1. El tecnico pudo elegir una imagen de otro dia y otra
    #  casa; estamparle «se tomó acá» la deja con cara de prueba.
    datos = _datos(metadatos_captura={"lat": 10.9108, "lng": -74.8186,
                                      "de_galeria": True})
    texto = " | ".join(M.lineas_de(TODO, datos))

    assert "10.9" not in texto, "no puede afirmar dónde se tomó"
    assert "galeria" in texto.lower(), (
        "y tampoco puede callarlo: sin esto, una foto de galería se ve igual "
        "que una donde el GPS no fijó")


def test_a4_SIN_GPS_dice_por_que_y_nunca_cero_cero():
    #  LA MENTIRA 2. `0,0` es una coordenada válida, en el golfo de Guinea.
    datos = _datos(metadatos_captura={"ubicacion_motivo": "permiso_denegado"})
    texto = " | ".join(M.lineas_de(TODO, datos))

    assert "Sin ubicacion" in texto
    #  EL MOTIVO, TRADUCIDO Y NO CRUDO (12/11/2026): ver `d1`. El valor de la
    #  app sale de un catálogo cerrado porque `metadatos_captura` no se
    #  valida y lo escribe quien sube.
    assert "sin permiso de ubicacion" in texto, "el motivo manda a revisar algo"
    assert "0, 0" not in texto and "0.000000" not in texto


def test_a5_UNA_UBICACION_SIMULADA_se_dice():
    #  LA MENTIRA 3, y la peor: estampar un GPS falseado como real es
    #  exactamente el daño que esta marca existe para evitar.
    datos = _datos(metadatos_captura={"lat": 10.9108, "lng": -74.8186,
                                      "ubicacion_simulada": True})
    texto = " | ".join(M.lineas_de(TODO, datos))

    #  SE DICE, PERO NO ACUSA (12/11/2026): ver `d5`. El flag tiene falsos
    #  positivos conocidos y esto queda horneado en un archivo que sale de la
    #  empresa.
    assert "no verificada" in texto


@pytest.mark.parametrize("precision,esperado,no_esperado", [
    (8, "10.910800", None),          # buena: seis decimales, ~11 cm
    (120, "10.9108", "10.910800"),   # media: cuatro, ~11 m
    (2000, "10.911", "10.9108"),     # triangulada: tres, ~110 m
])
def test_a6_los_decimales_siguen_a_la_precision_declarada(precision, esperado,
                                                          no_esperado):
    #  Seis decimales sobre una posición de ±2000 m aparentan 11 cm de
    #  precisión que no existe. No es estética: alguien va a ir a ese punto.
    datos = _datos(metadatos_captura={"lat": 10.9108, "lng": -74.8186,
                                      "precision_m": precision})
    texto = " | ".join(M.lineas_de(TODO, datos))

    assert esperado in texto
    if no_esperado:
        assert no_esperado not in texto
    assert f"±{precision} m" in texto


# =========================================================================== #
#  B. CUANDO NO SE ESTAMPA  --  y siempre vuelve EL ORIGINAL, byte a byte
# =========================================================================== #
#: CADA CASO TRAE SU PROPIO CONTENIDO  --  12/11/2026. La versión anterior
#: pasaba un JPEG y lo DECLARABA «application/pdf» o «image/heic», y pasaba
#: porque el código le creía a la declaración. Eso era justo el agujero H3:
#: la garantía la podía apagar quien subía, declarando otra cosa. Ahora
#: deciden los bytes, así que un caso que miente sobre su contenido ya no
#: prueba lo que decía probar -- tiene que traer el archivo de verdad.
_PDF = b"%PDF-1.4" + bytes(40)


@pytest.mark.parametrize("config,datos,contenido,porque", [
    ({**TODO, "activa": False}, {}, None, "la empresa la tiene apagada"),
    (TODO, {"mime_type": "application/pdf"}, _PDF, "un PDF no se dibuja"),
    (TODO, {"mime_type": "image/jpeg", "es_firma": True}, None,
     "el logo encima de la firma del cliente tapa la firma"),
    (TODO, {"mime_type": "image/jpeg", "es_captura": True}, None,
     "la marca encima de un test de velocidad tapa los números"),
])
def test_b1_devuelve_EL_ORIGINAL_byte_a_byte(config, datos, contenido, porque):
    original = contenido if contenido is not None else _imagen()
    completo = {**_datos(), **datos}
    assert M.estampar(original, config, completo) is original, porque


def test_b2_una_captura_SI_se_estampa_si_la_empresa_lo_pide():
    #  El control de la anterior: que se pueda, si alguien decide que sí.
    original = _imagen()
    config = dict(TODO, estampar_capturas=True)
    salida = M.estampar(original, config, _datos(es_captura=True))

    assert salida is not original
    assert len(salida) > 0


def test_b3_sin_nada_que_decir_no_reencodea():
    #  Reencodear para no agregar nada degrada la imagen y la agranda.
    config = {"activa": True, "mostrar_empresa": False, "mostrar_tecnico": False,
              "mostrar_coordenadas": False, "mostrar_fecha": False,
              "mostrar_logo": False}
    original = _imagen()
    assert M.estampar(original, config, _datos()) is original


# =========================================================================== #
#  C. QUE NO ROMPE  --  la familia que de verdad protege la evidencia
# =========================================================================== #
def test_c1_la_salida_SIGUE_SIENDO_UNA_IMAGEN_del_mismo_tamano():
    original = _imagen(1920, 1080)
    salida = M.estampar(original, TODO, _datos())

    assert salida is not original, "esta sí tenía que estamparse"
    with _abre(salida) as img:
        assert img.size == (1920, 1080), "la marca no recorta la evidencia"
        assert img.format == "JPEG"


def test_c2_UN_ARCHIVO_ROTO_no_pierde_los_bytes():
    #  Lo que entra vuelve. Perder la prueba de un trabajo que ya se hizo
    #  --y que no se puede repetir, porque el técnico se fue-- por una marca
    #  de agua sería un intercambio absurdo.
    basura = b"esto no es una imagen" * 50
    assert M.estampar(basura, TODO, _datos()) is basura


def test_c3_un_PNG_con_transparencia_no_revienta():
    #  Guardar un RGBA como JPEG sin convertir levanta. Con la conversión,
    #  sale.
    original = _png_con_transparencia()
    salida = M.estampar(original, TODO, _datos(mime_type="image/png"))

    assert salida is not original
    with _abre(salida) as img:
        assert img.size == (400, 300)


def test_c4_UN_LOGO_ILEGIBLE_no_se_lleva_la_marca_entera():
    #  El logo es lo más frágil de la cadena: lo sube una persona desde la
    #  pantalla de la empresa y puede ser cualquier cosa.
    config = dict(TODO, mostrar_logo=True)
    salida = M.estampar(_imagen(), config, _datos(logo_bytes=b"no soy un logo"))

    with _abre(salida) as img:
        assert img.size == (1920, 1080)
    assert len(salida) > 0


def test_c5_UNA_FOTO_CHICA_tampoco_revienta():
    #  Una banda de píxeles fijos sería más alta que la foto.
    salida = M.estampar(_imagen(320, 240), TODO, _datos())
    with _abre(salida) as img:
        assert img.size == (320, 240)


def test_c6_NO_CRECE_hasta_el_tope_que_WispHub_descarta():
    #  WispHub descarta en silencio relativo toda foto de más de 5 MB
    #  (`nucleo/seguimiento/nota_en_el_ticket.py`): no da error, la foto
    #  simplemente no viaja al ISP y el motivo queda en el rastro. Un
    #  reencode con calidad alta puede agrandar un JPEG que ya venía
    #  comprimido, así que esto se mide en vez de suponerse.
    from PIL import Image

    #  Una foto con ruido, no un color plano: un color plano comprime a nada
    #  y la prueba no mediría el caso real.
    import random
    random.seed(7)
    img = Image.new("RGB", (1920, 1080))
    img.putdata([(random.randint(0, 255), random.randint(0, 255),
                  random.randint(0, 255)) for _ in range(1920 * 1080)])
    crudo = io.BytesIO()
    img.save(crudo, format="JPEG", quality=85)
    original = crudo.getvalue()

    salida = M.estampar(original, TODO, _datos())
    assert len(salida) < 5 * 1024 * 1024, (
        f"la marca dejó la foto en {len(salida) / 1048576:.1f} MB y el tope "
        f"hacia WispHub son 5 MB")


# =========================================================================== #
#  D. LO QUE LA REVISION DE PII ENCONTRO  --  12/11/2026
# =========================================================================== #
#  Las tres primeras familias las escribi yo antes de que nadie mirara. Estas
#  salen de una pasada independiente, y por eso valen distinto: son los
#  agujeros que quien construyo no vio.
def test_d1_H2_el_motivo_de_ubicacion_NO_se_imprime_crudo():
    #  MEDIDO POR LA REVISION: `metadatos_captura` es un dict SIN VALIDAR que
    #  escribe quien sube. Un motivo de 190 caracteres con una cedula y un
    #  telefono adentro salia entero en la banda, horneado en el pixel, y de
    #  ahi al ticket del ISP y al proveedor de vision. La redaccion no puede
    #  ayudar: mira el texto que vuelve, no la imagen que va.
    veneno = ("X" * 160) + " cedula 1012345678 tel 3150000000"
    datos = _datos(metadatos_captura={"ubicacion_motivo": veneno})
    texto = " | ".join(M.lineas_de(TODO, datos))

    assert "1012345678" not in texto
    assert "3150000000" not in texto
    assert "XXX" not in texto
    assert "Sin ubicacion" in texto


@pytest.mark.parametrize("motivo,esperado", [
    ("servicio_apagado", "GPS apagado"),
    ("permiso_denegado", "sin permiso"),
    ("sin_senal_gps", "señal GPS"),
    ("error_TimeoutException", "error del sistema"),
])
def test_d2_los_CUATRO_motivos_de_la_app_siguen_diciendo_algo(motivo, esperado):
    #  El control de la anterior: acotar no puede volver inutil el dato. Los
    #  cuatro son los que la app emite y los cuatro mandan a revisar cosas
    #  distintas -- «sin permiso» y «sin señal» no se arreglan igual.
    datos = _datos(metadatos_captura={"ubicacion_motivo": motivo})
    assert esperado in " | ".join(M.lineas_de(TODO, datos))


def test_d3_H3_el_tipo_lo_deciden_LOS_BYTES_no_lo_que_la_fila_declara():
    #  MEDIDO POR LA REVISION: registrar la evidencia como `image/heic`
    #  --que esta en la lista blanca del storage-- y subir un JPEG guardaba
    #  la foto SIN MARCA. No es una fuga: es el reverso, y es peor para lo
    #  que la marca promete, porque la garantia la podia apagar el mismo que
    #  deberia quedar certificado por ella.
    jpeg = _imagen()
    salida = M.estampar(jpeg, TODO, _datos(mime_type="image/heic"))
    assert salida is not jpeg, "lo que importa es que el archivo ES un JPEG"


def test_d4_y_al_reves_un_PDF_que_se_declara_JPEG_no_se_toca():
    #  La otra mitad: mirar los bytes tiene que proteger en los dos sentidos.
    pdf = b"%PDF-1.4" + b"\x00" * 40
    assert M.estampar(pdf, TODO, _datos(mime_type="image/jpeg")) is pdf


def test_d5_una_ubicacion_simulada_NO_acusa_a_la_persona():
    #  Pregunta 6 de la revision: «UBICACION SIMULADA» es una afirmacion
    #  sobre la conducta de un empleado, horneada de forma irreversible en un
    #  archivo que sale de la empresa, y el flag tiene falsos positivos
    #  conocidos. Se sigue diciendo --callarlo dejaria la foto sin ubicacion
    #  por un motivo invisible-- pero sin acusar.
    datos = _datos(metadatos_captura={"lat": 10.9108, "lng": -74.8186,
                                      "ubicacion_simulada": True})
    texto = " | ".join(M.lineas_de(TODO, datos))

    assert "no verificada" in texto
    assert "SIMULADA" not in texto


# =========================================================================== #
#  E. A LA DERECHA  --  13/11/2026
# =========================================================================== #
def _blancos_por_mitad(salida: bytes, arriba: bool) -> tuple[int, int]:
    """Cuantos pixeles casi blancos hay en cada mitad de la banda.

    La foto es de un solo color oscuro, asi que lo unico blanco es el texto.
    """
    with _abre(salida) as img:
        rgb = img.convert("RGB")
        ancho, alto = rgb.size
        banda = int(min(ancho, alto) * 0.055) * 2
        y0, y1 = (0, banda) if arriba else (alto - banda, alto)
        izq = der = 0
        for y in range(y0, y1, 2):
            for x in range(0, ancho, 2):
                r, g, b = rgb.getpixel((x, y))
                if r > 200 and g > 200 and b > 200:
                    if x < ancho // 2:
                        izq += 1
                    else:
                        der += 1
        return izq, der


@pytest.mark.parametrize("posicion,arriba,lado", [
    ("abajo_izquierda", False, "izq"),
    ("abajo_derecha", False, "der"),
    ("arriba_izquierda", True, "izq"),
    ("arriba_derecha", True, "der"),
])
def test_e1_LA_ESQUINA_ELEGIDA_es_la_que_sale(posicion, arriba, lado):
    #  Antes «abajo a la derecha» salía idéntica a «abajo a la izquierda»: la
    #  pantalla ofrecía cuatro esquinas y el dibujo solo miraba arriba/abajo.
    config = dict(TODO, posicion=posicion, mostrar_coordenadas=False,
                  mostrar_fecha=False)
    salida = M.estampar(_imagen(1600, 1200, color=(20, 20, 20)), config,
                        _datos(empresa="Empresa", tecnico="Ana"))

    izq, der = _blancos_por_mitad(salida, arriba)
    assert izq + der > 0, "el texto tiene que estar en la banda elegida"
    if lado == "izq":
        assert izq > der, (posicion, izq, der)
    else:
        assert der > izq, (posicion, izq, der)


def test_e2_a_la_derecha_es_una_sola_regla():
    #  La app la repite en Dart (`marca_de_agua.dart`); que acá sea una
    #  función con nombre es lo que deja escribir la misma prueba allá.
    assert M.a_la_derecha("abajo_derecha") is True
    assert M.a_la_derecha("arriba_derecha") is True
    assert M.a_la_derecha("abajo_izquierda") is False
    assert M.a_la_derecha("") is False
