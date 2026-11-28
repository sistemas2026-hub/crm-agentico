# -*- coding: utf-8 -*-
"""
================================================================================
 DE DONDE SALIO UNA IMAGEN DE GALERIA, Y DE CUANDO ES  --  21/11/2026
================================================================================
EL USUARIO
----------
    «cuando el verifica una imagen mira la hora y el origen?»
    «se puede poner que revise eso de la fecha en que es el capture y si es de
     internet o capture del telefono»

LO QUE SE MIDE
--------------
1. La clasificacion, sin base y sin modelo: es una funcion de lo que la app
   declara. Cada regla con su contrario al lado.
2. Que el punto entra a la revision del cierre, DEJA EN DUDA y NO DEVUELVE.
3. Que cada imagen lleva su origen a la tarjeta.

LAS DOS COSAS QUE NO PUEDEN PASAR, y por eso tienen prueba propia:
  - que lo que NO SE PUDO LEER se trate como sospechoso (marcaria todas las
    capturas de una marca de telefono que nombra distinto);
  - que un valor de otro tipo --un "1080", un `True`-- cuente como dato: el
    diccionario llega del telefono sin validar.
================================================================================
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from campo import origen_de_la_imagen as OI

BOGOTA = ZoneInfo("America/Bogota")

#: Adjuntada el 21/11/2026 a las 09:30 de Bogota.
ADJUNTADA = dt.datetime(2026, 11, 21, 14, 30, tzinfo=dt.timezone.utc)


def _ev(**metadatos):
    return SimpleNamespace(metadatos_captura=metadatos,
                           capturada_en_cliente=ADJUNTADA,
                           recibida_en_servidor=None)


def _captura(**extra):
    """Una captura de este telefono, de hoy: lo que la app manda."""
    base = {"de_galeria": True, "origen_version": 1,
            "imagen_ancho": 1080, "imagen_alto": 2400,
            "pantalla_ancho": 1080, "pantalla_alto": 2400,
            "nombre_dice_captura": True,
            "fecha_segun_nombre": "2026-11-21T09:23:01",
            "exif_camara": False}
    base.update(extra)
    return _ev(**{k: v for k, v in base.items() if v is not None})


# ---------------------------------------------------------------------------
#  1) CUANDO NO HAY NADA QUE DECIR
# ---------------------------------------------------------------------------

def test_la_foto_de_CAMARA_no_tiene_origen_que_revisar():
    assert OI.leer(_ev(), BOGOTA) is None
    assert OI.leer(_ev(de_galeria=False, origen_version=1), BOGOTA) is None


def test_solo_vale_el_TRUE_de_la_app():
    assert OI.leer(_ev(de_galeria="true", origen_version=1), BOGOTA) is None
    assert OI.leer(_ev(de_galeria=1, origen_version=1), BOGOTA) is None


def test_los_metadatos_que_no_son_un_diccionario_no_rompen():
    sin = SimpleNamespace(metadatos_captura=None, capturada_en_cliente=None,
                          recibida_en_servidor=None)
    assert OI.leer(sin, BOGOTA) is None
    assert OI.leer(SimpleNamespace(metadatos_captura=["x"]), BOGOTA) is None


def test_una_APP_VIEJA_no_levanta_dudas():
    """Manda `de_galeria` y nada mas. Ahi nadie miro: no es «desconocido»."""
    leido = OI.leer(_ev(de_galeria=True), BOGOTA)

    assert leido["tipo"] == OI.SIN_DATOS
    assert leido["duda"] is False
    assert leido["texto"] == "Elegida de la galería"


# ---------------------------------------------------------------------------
#  2) QUE CLASE DE IMAGEN ES
# ---------------------------------------------------------------------------

def test_la_que_mide_lo_que_la_pantalla_es_una_captura_de_ESTE_telefono():
    leido = OI.leer(_captura(nombre_dice_captura=False), BOGOTA)

    assert leido["tipo"] == OI.CAPTURA_DE_ESTE_TELEFONO
    assert leido["texto"].startswith("Captura de pantalla de este teléfono")


def test_con_el_telefono_GIRADO_tambien():
    leido = OI.leer(_captura(imagen_ancho=2400, imagen_alto=1080,
                             nombre_dice_captura=False), BOGOTA)

    assert leido["tipo"] == OI.CAPTURA_DE_ESTE_TELEFONO


def test_un_pixel_de_diferencia_YA_NO_es_la_pantalla():
    leido = OI.leer(_captura(imagen_alto=2399, nombre_dice_captura=False),
                    BOGOTA)

    assert leido["tipo"] == OI.DESCONOCIDO


def test_si_no_mide_la_pantalla_pero_el_nombre_dice_captura_es_CAPTURA():
    """Una captura recortada, o una hecha en otro telefono. No se afirma que
    sea de ESTE."""
    leido = OI.leer(_captura(imagen_ancho=1080, imagen_alto=900), BOGOTA)

    assert leido["tipo"] == OI.CAPTURA
    assert "de este teléfono" not in leido["texto"]
    assert leido["duda"] is False


def test_la_que_trae_la_marca_de_una_camara_es_una_FOTO_GUARDADA():
    leido = OI.leer(_captura(imagen_ancho=1920, imagen_alto=1440,
                             nombre_dice_captura=False, exif_camara=True,
                             fecha_segun_nombre=None,
                             exif_fecha="2026-11-21T08:10:00"), BOGOTA)

    assert leido["tipo"] == OI.FOTO_GUARDADA
    assert leido["duda"] is False
    assert "del 21/11 08:10" in leido["texto"]


def test_la_que_no_es_ninguna_de_las_tres_es_de_ORIGEN_DESCONOCIDO():
    """La imagen bajada de una tienda: cuadrada, sin nombre de captura y sin
    camara. No se dice «es de internet»: se dice lo que no es."""
    leido = OI.leer(_captura(imagen_ancho=800, imagen_alto=800,
                             nombre_dice_captura=False,
                             fecha_segun_nombre=None), BOGOTA)

    assert leido["tipo"] == OI.DESCONOCIDO
    assert leido["duda"] is True
    assert "internet" not in leido["texto"].lower()
    #  Las dos medidas a la vista: es lo unico que deja ver, desde la
    #  oficina, si la comparacion falla en un telefono que mide distinto.
    assert "800×800" in leido["texto"] and "1080×2400" in leido["texto"]


# ---------------------------------------------------------------------------
#  3) DE CUANDO ES
# ---------------------------------------------------------------------------

def test_la_del_MISMO_DIA_no_levanta_dudas_y_lo_dice():
    leido = OI.leer(_captura(), BOGOTA)

    assert leido["del_dia"] is True
    assert leido["duda"] is False
    assert "del 21/11 09:23, el mismo día en que se adjuntó" in leido["texto"]


def test_la_de_OTRO_DIA_levanta_la_duda_con_las_dos_fechas():
    leido = OI.leer(_captura(fecha_segun_nombre="2026-11-14T16:05:09"), BOGOTA)

    assert leido["del_dia"] is False
    assert leido["duda"] is True
    assert "es del 14/11 16:05 y se adjuntó el 21/11" in leido["texto"]


def test_la_foto_guardada_de_otro_dia_tambien():
    leido = OI.leer(_captura(imagen_ancho=1920, imagen_alto=1440,
                             nombre_dice_captura=False, exif_camara=True,
                             fecha_segun_nombre=None,
                             exif_fecha="2026-11-14T16:05:09"), BOGOTA)

    assert leido["tipo"] == OI.FOTO_GUARDADA
    assert leido["duda"] is True


def test_SIN_FECHA_no_es_una_duda():
    """La que no puede pasar: tratar lo ilegible como sospechoso marcaria
    todas las capturas de una marca que nombra distinto sus archivos."""
    leido = OI.leer(_captura(fecha_segun_nombre=None), BOGOTA)

    assert leido["del_dia"] is None
    assert leido["duda"] is False
    assert "no dice de cuándo es" in leido["texto"]


def test_una_fecha_MAL_ESCRITA_es_sin_fecha_no_otro_dia():
    for mala in ("ayer", "21/11/2026", "2026-13-40T00:00:00", 20261121, True,
                 "1999-11-21T09:23:01"):
        leido = OI.leer(_captura(fecha_segun_nombre=mala), BOGOTA)

        assert leido["del_dia"] is None, mala
        assert leido["duda"] is False, mala


def test_solo_el_dia_sin_hora_tambien_se_compara():
    leido = OI.leer(_captura(fecha_segun_nombre="2026-11-21"), BOGOTA)

    assert leido["del_dia"] is True
    assert "del 21/11, el mismo día" in leido["texto"]


def test_el_dia_se_cuenta_EN_LA_HORA_DE_LA_EMPRESA():
    """Adjuntada el 21/11 a las 02:00 UTC: en Bogota todavia es el 20 a las
    21:00. Una captura del 20 a las 20:59 es del mismo dia; leido en UTC
    pareceria de la vispera."""
    ev = _captura(fecha_segun_nombre="2026-11-20T20:59:00")
    ev.capturada_en_cliente = dt.datetime(2026, 11, 21, 2, 0,
                                          tzinfo=dt.timezone.utc)

    assert OI.leer(ev, BOGOTA)["del_dia"] is True


def test_sin_la_hora_del_telefono_se_usa_la_del_servidor():
    ev = _captura()
    ev.capturada_en_cliente = None
    ev.recibida_en_servidor = ADJUNTADA

    assert OI.leer(ev, BOGOTA)["del_dia"] is True


def test_sin_NINGUNA_de_las_dos_no_se_compara():
    ev = _captura()
    ev.capturada_en_cliente = None

    leido = OI.leer(ev, BOGOTA)

    assert leido["del_dia"] is None
    assert leido["duda"] is False


# ---------------------------------------------------------------------------
#  4) EL DICCIONARIO LLEGA DEL TELEFONO SIN VALIDAR
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("falso", ["1080", 1080.0, True, None, 0, -5, [1080]])
def test_un_ancho_que_no_es_un_entero_NO_es_un_ancho(falso):
    """Con un ancho falso no hay comparacion contra la pantalla: lo decide el
    nombre. Y `True` es un `int` en Python: se excluye a mano."""
    leido = OI.leer(_captura(imagen_ancho=falso, pantalla_ancho=falso,
                             nombre_dice_captura=False,
                             fecha_segun_nombre=None), BOGOTA)

    assert leido["tipo"] == OI.DESCONOCIDO
    #  Sin medidas validas no se escriben medidas inventadas.
    assert "×" not in leido["texto"]


@pytest.mark.parametrize("falso", ["true", 1, "si", None])
def test_un_booleano_que_no_es_TRUE_no_cuenta(falso):
    leido = OI.leer(_captura(imagen_ancho=800, imagen_alto=800,
                             nombre_dice_captura=falso, exif_camara=falso,
                             fecha_segun_nombre=None), BOGOTA)

    assert leido["tipo"] == OI.DESCONOCIDO


@pytest.mark.parametrize("falsa", ["1", True, None, 0, 1.0])
def test_una_VERSION_que_no_es_un_entero_es_una_app_vieja(falsa):
    ev = _ev(de_galeria=True, origen_version=falsa, imagen_ancho=800,
             imagen_alto=800, pantalla_ancho=1080, pantalla_alto=2400)

    assert OI.leer(ev, BOGOTA)["tipo"] == OI.SIN_DATOS


# ---------------------------------------------------------------------------
#  5) EN LA REVISION DEL CIERRE: DEJA EN DUDA, NO DEVUELVE
# ---------------------------------------------------------------------------

DESCONOCIDA = {"de_galeria": True, "origen_version": 1,
               "imagen_ancho": 800, "imagen_alto": 800,
               "pantalla_ancho": 1080, "pantalla_alto": 2400,
               "nombre_dice_captura": False, "exif_camara": False}


def _de_hoy():
    """Una captura de este telefono hecha HOY, en la hora de Bogota."""
    from django.utils import timezone

    hoy = timezone.now().astimezone(BOGOTA)
    return {"de_galeria": True, "origen_version": 1,
            "imagen_ancho": 1080, "imagen_alto": 2400,
            "pantalla_ancho": 1080, "pantalla_alto": 2400,
            "nombre_dice_captura": True, "exif_camara": False,
            "fecha_segun_nombre": hoy.strftime("%Y-%m-%dT%H:%M:%S")}


def _orden(org, numero, *, vuelta=1):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"ori{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [],
                 "evidencias": [
                     {"id": "dano_encontrado", "tipo": "foto",
                      "titulo": "Daño encontrado", "obligatorio": True},
                     {"id": "trabajo_terminado", "tipo": "foto",
                      "titulo": "Trabajo terminado", "obligatorio": True}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98008"}, vuelta=vuelta)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": vuelta,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


def _foto(org, orden, requisito, metadatos, *, vuelta=1):
    from django.utils import timezone

    from campo.models import EvidenciaTrabajo

    return EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=vuelta,
        sha256=f"{requisito}{orden.numero}{vuelta}".ljust(64, "x")[:64],
        storage_key=f"k/{requisito}{orden.numero}{vuelta}",
        nombre_original="m.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO,
        capturada_en_cliente=timezone.now(), metadatos_captura=metadatos)


def _revision(orden):
    from campo import revision_del_cierre as RC

    return RC.revisar(orden, pendientes=set())


def _punto(r):
    return next((p for p in r["puntos"] if p["clave"] == "origen"), None)


pytestmark_db = pytest.mark.django_db


@pytestmark_db
def test_sin_imagenes_de_galeria_el_punto_NO_APARECE(org_a):
    orden = _orden(org_a, 9701)
    _foto(org_a, orden, "dano_encontrado", {})
    _foto(org_a, orden, "trabajo_terminado", {})

    assert _punto(_revision(orden)) is None


@pytestmark_db
def test_con_una_app_vieja_el_punto_NO_APARECE(org_a):
    orden = _orden(org_a, 9702)
    _foto(org_a, orden, "dano_encontrado", {"de_galeria": True})
    _foto(org_a, orden, "trabajo_terminado", {})

    assert _punto(_revision(orden)) is None


@pytestmark_db
def test_la_captura_de_hoy_deja_el_punto_EN_ORDEN(org_a):
    orden = _orden(org_a, 9703)
    _foto(org_a, orden, "dano_encontrado", _de_hoy())
    _foto(org_a, orden, "trabajo_terminado", {})

    p = _punto(_revision(orden))

    assert p is not None and p["ok"] is True
    assert "no levanta dudas" in p["texto"]


@pytestmark_db
def test_la_de_origen_desconocido_DEJA_EN_DUDA_y_dice_cual(org_a):
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9704)
    _foto(org_a, orden, "dano_encontrado", DESCONOCIDA)
    _foto(org_a, orden, "trabajo_terminado", {})

    r = _revision(orden)
    p = _punto(r)

    assert p["ok"] is None
    assert "Daño encontrado" in p["texto"]
    assert "no se sabe de dónde salió" in p["texto"]
    assert r["veredicto"] != RC.CERRAR


@pytestmark_db
def test_NUNCA_vale_False_ni_nombra_nada_que_rehacer(org_a):
    """Lo declara el telefono: deja en duda, no niega ni devuelve."""
    orden = _orden(org_a, 9705)
    _foto(org_a, orden, "dano_encontrado", DESCONOCIDA)
    _foto(org_a, orden, "trabajo_terminado", DESCONOCIDA)

    r = _revision(orden)

    assert _punto(r)["ok"] is None
    assert r["sugeridas"] == []


@pytestmark_db
def test_el_Supervisor_NO_devuelve_la_orden_por_esto(org_a):
    from campo import cierre_por_el_supervisor as CS
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 9706)
    _foto(org_a, orden, "dano_encontrado", DESCONOCIDA)
    _foto(org_a, orden, "trabajo_terminado", {})

    assert CS.atender_la_que_no_cierra(orden, _revision(orden)) == "nada"
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert orden.vuelta == 1


@pytestmark_db
def test_la_que_se_REEMPLAZO_por_una_foto_de_camara_se_lleva_la_duda(org_a):
    orden = _orden(org_a, 9707, vuelta=2)
    _foto(org_a, orden, "dano_encontrado", DESCONOCIDA, vuelta=1)
    _foto(org_a, orden, "dano_encontrado", {}, vuelta=2)
    _foto(org_a, orden, "trabajo_terminado", {}, vuelta=2)

    assert _punto(_revision(orden)) is None


@pytestmark_db
def test_cada_imagen_lleva_su_origen_a_la_tarjeta(org_a):
    orden = _orden(org_a, 9708)
    _foto(org_a, orden, "dano_encontrado", DESCONOCIDA)
    _foto(org_a, orden, "trabajo_terminado", {})

    evidencias = {e["id"]: e for e in _revision(orden)["evidencias"]}

    assert evidencias["dano_encontrado"]["origen"]["duda"] is True
    assert "no se sabe de dónde salió" in (
        evidencias["dano_encontrado"]["origen"]["texto"])
    #  La de camara: nada que decir.
    assert evidencias["trabajo_terminado"]["origen"] is None


@pytestmark_db
def test_la_que_NO_LLEGO_tampoco_rompe(org_a):
    orden = _orden(org_a, 9709)
    _foto(org_a, orden, "dano_encontrado", _de_hoy())

    evidencias = {e["id"]: e for e in _revision(orden)["evidencias"]}

    assert evidencias["trabajo_terminado"]["origen"] is None
    assert evidencias["dano_encontrado"]["origen"]["duda"] is False
