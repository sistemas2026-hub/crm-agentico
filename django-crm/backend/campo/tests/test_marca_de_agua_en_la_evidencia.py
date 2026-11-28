# -*- coding: utf-8 -*-
"""La marca de agua, desde la evidencia real y desde la pantalla.

`test_marca_de_agua.py` prueba el DIBUJO, que es una funcion pura. Este prueba
las dos puntas que lo rodean:

  A  EL PUENTE -- de una `EvidenciaTrabajo` a los datos del dibujo: que lea
     lo que tiene que leer, que no estampe la firma ni las capturas, y que
     NUNCA pueda costar una evidencia
  B  LA PANTALLA -- que la empresa pueda prenderla y configurarla, y que un
     valor malo se rechace con un 400 en vez de reventar en la base

Lo que NO se prueba aca y se dice: que la foto quede linda. Eso no es una
afirmacion que un test pueda sostener.
"""
import io

import pytest

from campo.marca_de_agua import ConfiguracionDeMarcaDeAgua
from campo.models import EvidenciaTrabajo

pytestmark = pytest.mark.django_db

URL = "/api/campo/marca-de-agua/configuracion/"


def _jpeg(ancho=800, alto=600) -> bytes:
    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), (30, 80, 140)).save(salida, format="JPEG")
    return salida.getvalue()


class _EvidenciaFalsa:
    """Una evidencia con lo justo que el puente lee.

    NO ES UN DOBLE DEL DIBUJO --ese corre de verdad-- sino de la fila: armar
    una orden, su version de plantilla y su cuadrilla para cada caso costaria
    minutos por prueba y no mediria nada mas.
    """

    def __init__(self, org, *, requisito_id="onu_instalada",
                 mime_type="image/jpeg", metadatos=None, esquema=None):
        from datetime import datetime, timezone

        self.org = org
        self.requisito_id = requisito_id
        self.mime_type = mime_type
        self.capturada_en_cliente = datetime(2026, 11, 12, 20, 30,
                                             tzinfo=timezone.utc)
        self.metadatos_captura = metadatos or {"lat": 10.9108, "lng": -74.8186,
                                               "precision_m": 8}

        class _Version:
            pass

        class _Orden:
            tecnico_principal = None

        self.orden_trabajo = _Orden()
        v = _Version()
        v.esquema = esquema or {"evidencias": [{"id": "onu_instalada"}]}
        self.orden_trabajo.tipo_trabajo_version = v


def _prender(org, **extra):
    fila, _ = ConfiguracionDeMarcaDeAgua.objects.get_or_create(org=org)
    fila.activa = True
    fila.mostrar_empresa = True
    fila.mostrar_logo = False
    for k, v in extra.items():
        setattr(fila, k, v)
    fila.save()
    return fila


# =========================================================================== #
#  A. EL PUENTE
# =========================================================================== #
def test_a1_sin_configuracion_NO_se_estampa(org_a):
    #  Ninguna empresa empieza a recibir fotos marcadas por una migración.
    from campo.marca_de_agua import estampar_evidencia

    original = _jpeg()
    assert estampar_evidencia(_EvidenciaFalsa(org_a), original) is original


def test_a2_prendida_SI_se_estampa(org_a):
    from campo.marca_de_agua import estampar_evidencia

    _prender(org_a)
    original = _jpeg()
    salida = estampar_evidencia(_EvidenciaFalsa(org_a), original)

    assert salida is not original
    from PIL import Image
    with Image.open(io.BytesIO(salida)) as img:
        assert img.size == (800, 600), "la marca no recorta la evidencia"


def test_a3_LA_FIRMA_DEL_CLIENTE_no_se_estampa(org_a):
    #  El logo encima de la firma tapa la firma. La app la sube como una
    #  evidencia más, con este `requisito_id`, y NO está declarada en ninguna
    #  plantilla -- por eso no se puede preguntar al esquema.
    from campo.marca_de_agua import estampar_evidencia

    _prender(org_a)
    original = _jpeg()
    ev = _EvidenciaFalsa(org_a, requisito_id="firma_receptor")
    assert estampar_evidencia(ev, original) is original


def test_a4_UNA_CAPTURA_no_se_estampa_salvo_que_la_empresa_lo_pida(org_a):
    #  La marca encima de un test de velocidad tapa los números que el test
    #  prueba. La plantilla ya declara cuál requisito es una captura.
    from campo.marca_de_agua import estampar_evidencia

    esquema = {"evidencias": [{"id": "test_de_velocidad", "es_captura": True}]}
    ev = _EvidenciaFalsa(org_a, requisito_id="test_de_velocidad",
                         esquema=esquema)
    original = _jpeg()

    _prender(org_a)
    assert estampar_evidencia(ev, original) is original

    _prender(org_a, estampar_capturas=True)
    assert estampar_evidencia(ev, original) is not original


def test_a5_UN_PDF_no_se_toca(org_a):
    from campo.marca_de_agua import estampar_evidencia

    _prender(org_a)
    original = b"%PDF-1.4 esto es un pdf"
    ev = _EvidenciaFalsa(org_a, mime_type="application/pdf")
    assert estampar_evidencia(ev, original) is original


def test_a6_UNA_EVIDENCIA_ROTA_no_pierde_los_bytes(org_a):
    #  LA AFIRMACIÓN QUE MÁS VALE. Si el puente levanta, la evidencia de un
    #  trabajo que ya se hizo se pierde, y no se puede repetir: el técnico se
    #  fue de la casa.
    from campo.marca_de_agua import estampar_evidencia

    _prender(org_a)

    class _Rota:
        org = org_a
        #  Sin `requisito_id`, sin `mime_type`, sin orden: todo lo que el
        #  puente lee, ausente.

    original = _jpeg()
    assert estampar_evidencia(_Rota(), original) is original


def test_a7_la_empresa_y_la_fecha_salen_en_la_imagen(org_a):
    #  No se puede leer el texto de un JPEG, así que se afirma sobre lo que
    #  SÍ se puede: que las líneas que el dibujo va a escribir son las que
    #  corresponden a esta evidencia. El dibujo en sí tiene su archivo.
    from campo.marca_de_agua import configuracion_de
    from campo.services.marca_de_agua import lineas_de

    _prender(org_a, mostrar_fecha=True, mostrar_coordenadas=True)
    ev = _EvidenciaFalsa(org_a)
    lineas = lineas_de(configuracion_de(org_a), {
        "empresa": org_a.name, "tecnico": "",
        "fecha": ev.capturada_en_cliente,
        "metadatos_captura": ev.metadatos_captura})

    texto = " | ".join(lineas)
    assert org_a.name in texto
    assert "12/11/2026 15:30" in texto, "en hora de Colombia, no UTC"
    assert "10.910800" in texto


# =========================================================================== #
#  B. LA PANTALLA
# =========================================================================== #
def test_b1_arranca_apagada_y_sin_coordenadas(admin_client):
    datos = admin_client.get(URL).json()

    assert datos["activa"] is False, (
        "ninguna empresa empieza a recibir fotos marcadas por una migración")
    assert datos["mostrar_coordenadas"] is False, (
        "estampar el GPS graba el domicilio dentro de la imagen: se prende a "
        "propósito")
    assert datos["mostrar_empresa"] is True


def test_b2_se_prende_y_queda(admin_client):
    r = admin_client.put(URL, {"activa": True, "mostrar_coordenadas": True},
                         format="json")
    assert r.status_code == 200, r.content
    assert r.json()["activa"] is True
    assert admin_client.get(URL).json()["mostrar_coordenadas"] is True


def test_b3_la_pantalla_sabe_si_falta_el_logo(admin_client):
    #  Si la empresa prende «el logo» y no cargó ninguno, la marca sale sin
    #  logo y nadie entiende por qué. El formulario lo puede decir antes.
    datos = admin_client.get(URL).json()
    assert "logo_cargado" in datos
    assert datos["logo_cargado"] is False


@pytest.mark.parametrize("cuerpo", [
    {"activa": "si"},                     # texto donde va un booleano
    {"opacidad": 0},                      # por debajo del mínimo
    {"opacidad": 101},                    # por encima del máximo
    {"opacidad": True},                   # un bool ES int en Python
    {"opacidad": "media"},
    {"posicion": "en el medio"},
    {"texto_extra": "x" * 81},            # el campo es de 80
])
def test_b4_un_valor_malo_se_rechaza_con_400(admin_client, cuerpo):
    #  CON 400 Y NO CON 500: `opacidad` es un `PositiveSmallIntegerField` y
    #  un 70000 revienta en la base. Lo mismo que ya aprendió la
    #  configuración de seguimiento.
    r = admin_client.put(URL, cuerpo, format="json")
    assert r.status_code == 400, (cuerpo, r.content)


def test_b5_quien_no_gestiona_no_la_toca(user_client):
    assert user_client.put(URL, {"activa": True},
                           format="json").status_code in (403, 404)


def test_b6_un_campo_que_no_existe_se_ignora(admin_client):
    #  No revienta y no lo guarda: la pantalla puede mandar de más sin
    #  tumbar la configuración.
    r = admin_client.put(URL, {"activa": True, "color_del_logo": "rojo"},
                         format="json")
    assert r.status_code == 200
    assert "color_del_logo" not in r.json()


# =========================================================================== #
#  C. LO QUE LA REVISION DE PII PIDIO MEDIR  --  12/11/2026
# =========================================================================== #
def test_c1_EL_LOGO_DE_OTRA_EMPRESA_no_se_puede_dibujar(org_a, org_b):
    """El aislamiento, afirmado por EFECTO y no por argumento.

    La revision de PII no pudo romper `_logo_de` --la evidencia ya viene
    acotada por `filter(org=request.org)` y `Org.logo` es un FileField que
    solo escribe el serializer de Org-- pero senalo que el argumento no
    estaba respaldado por ninguna prueba: no habia NI UN caso con `org_b`.

    Un argumento correcto hoy no impide que manana alguien cambie el
    storage. Esto si.
    """
    from django.core.files.base import ContentFile

    from campo.marca_de_agua import _logo_de

    #  Un PNG de un pixel, rojo, para la empresa B.
    rojo = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
            b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
            b"\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00"
            b"\x00\x00IEND\xaeB`\x82")
    org_b.logo.save("logo_b.png", ContentFile(rojo), save=True)

    assert _logo_de(org_b) == rojo, "el control: el de su dueña sí se lee"
    assert _logo_de(org_a) is None, (
        "la empresa A no tiene logo, y el de B no es alcanzable desde ella")


def test_c2_H4_la_fila_dice_lo_que_el_archivo_ES(admin_client, org_a, django_user_model):
    """Entra PNG, sale JPEG, y `mime_type` tiene que seguir al archivo.

    MEDIDO POR LA REVISION: tres consumidores usan el mime DECLARADO --el
    ticket de WispHub, el adjunto del caso del CRM y la pantalla de revision,
    que ademas sirve `nosniff`, la cabecera que le prohibe al navegador
    corregir la mentira--.

    Esta guarda afirma sobre la FUNCION que decide, no sobre la vista
    completa: montar la subida entera pide orden, cuadrilla y version de
    plantilla, y lo que puede romperse es la decision.
    """
    from campo.services.marca_de_agua import estampar

    _prender(org_a)
    png = _png()
    salida = estampar(png, {"activa": True, "mostrar_empresa": True,
                            "opacidad": 55},
                      {"empresa": "X", "metadatos_captura": {}})

    assert salida is not png
    assert salida[:3] == b"\xff\xd8\xff", (
        "la salida es JPEG, así que la fila que diga 'image/png' miente")


def _png() -> bytes:
    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (300, 200), (10, 120, 60)).save(salida, format="PNG")
    return salida.getvalue()


# =========================================================================== #
#  D. EL NOMBRE DEL TECNICO, Y LO QUE LEE EL TELEFONO  --  13/11/2026
# =========================================================================== #
class _Usuario:
    def __init__(self, name, email="tecnico@empresa.co"):
        self.name = name
        self.email = email

    def __str__(self):
        #  Igual que `common.models.User.__str__`: el correo.
        return self.email


class _Perfil:
    def __init__(self, usuario):
        self.user = usuario


def test_d1_EL_CORREO_DEL_TECNICO_nunca_sale_en_la_foto():
    """Medido el 13/11/2026: la marca pedía `perfil.nombre_completo`, que no
    existe, y caía a `str(perfil.user)` -- el correo."""
    from campo.marca_de_agua import nombre_para_la_marca

    assert nombre_para_la_marca(_Perfil(_Usuario("Carlos Pérez"))) == "Carlos Pérez"
    assert nombre_para_la_marca(_Perfil(_Usuario(""))) == "", (
        "sin nombre cargado no se imprime nada: nunca el correo")
    assert nombre_para_la_marca(_Perfil(_Usuario("  "))) == ""
    assert nombre_para_la_marca(None) == ""


def test_d2_el_estampado_usa_ESE_nombre(org_a, monkeypatch):
    from campo import marca_de_agua as puente
    from campo.services import marca_de_agua as dibujo

    vistos = {}

    def _espia(contenido, config, datos):
        vistos.update(datos)
        return contenido

    monkeypatch.setattr(dibujo, "estampar", _espia)
    _prender(org_a, mostrar_tecnico=True)

    ev = _EvidenciaFalsa(org_a)
    ev.orden_trabajo.tecnico_principal = _Perfil(_Usuario("", "x@y.co"))
    puente.estampar_evidencia(ev, _jpeg())
    assert vistos["tecnico"] == "", "un técnico sin nombre no se vuelve su correo"

    ev.orden_trabajo.tecnico_principal = _Perfil(_Usuario("Ana Ruiz", "x@y.co"))
    puente.estampar_evidencia(ev, _jpeg())
    assert vistos["tecnico"] == "Ana Ruiz"


URL_APP = "/api/campo/marca-de-agua/"
URL_LOGO = "/api/campo/marca-de-agua/logo/"


def test_d3_EL_TELEFONO_lee_la_misma_configuracion_que_estampa(user_client, org_a):
    #  No es gestión: cualquier persona de campo la lee, porque no trae nada
    #  que la foto misma no vaya a mostrar.
    _prender(org_a, posicion="arriba_derecha", texto_extra="Garantía 30 días")

    r = user_client.get(URL_APP)
    assert r.status_code == 200, r.content
    datos = r.json()

    from campo.marca_de_agua import configuracion_de
    assert datos["configuracion"] == configuracion_de(org_a), (
        "una sola fuente: el teléfono pinta lo que el servidor va a estampar")
    assert datos["empresa"] == org_a.name
    assert datos["logo_version"] is None
    assert "@" not in (datos["tecnico"] or ""), "nunca el correo"


def test_d4_apagada_el_telefono_lo_sabe(user_client):
    #  Sin fila: la apagada, igual que el estampado. El teléfono no pinta
    #  una banda que la foto no va a llevar.
    datos = user_client.get(URL_APP).json()
    assert datos["configuracion"]["activa"] is False


def test_d5_EL_LOGO_es_el_de_SU_empresa_y_solo_ese(user_client, org_a, org_b):
    from django.core.files.base import ContentFile

    assert user_client.get(URL_LOGO).status_code == 404, "sin logo, 404"

    #  Un logo cargado en OTRA empresa no aparece.
    org_b.logo.save("logo_b.png", ContentFile(_png()), save=True)
    assert user_client.get(URL_LOGO).status_code == 404

    contenido = _png()
    org_a.logo.save("logo_a.png", ContentFile(contenido), save=True)
    r = user_client.get(URL_LOGO)
    assert r.status_code == 200
    assert r.content == contenido
    assert r["Content-Type"] == "image/png"

    version = user_client.get(URL_APP).json()["logo_version"]
    assert version and len(version) == 12, "el teléfono sabe cuándo rebajarlo"


def test_d6_sin_sesion_no_se_lee(unauthenticated_client):
    assert unauthenticated_client.get(URL_APP).status_code in (401, 403)
    assert unauthenticated_client.get(URL_LOGO).status_code in (401, 403)
