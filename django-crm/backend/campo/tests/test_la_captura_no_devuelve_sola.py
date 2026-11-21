# -*- coding: utf-8 -*-
"""
================================================================================
 LA IMAGEN DE GALERIA NO DEVUELVE LA ORDEN SOLA  --  21/11/2026
================================================================================
EL USUARIO, TRES VECES
----------------------
    «el supervisor no puede detener una orden solo por ser captura»
    «adjunte una captura en vez de foto y aun asi me la devolvio»
    «aun sigue devolviendo las ordenes que mandaron las evidencias por captura
     y no por foto»

LO QUE SE HIZO MAL DOS VECES
----------------------------
Dos arreglos fueron texto para el modelo --una regla general y una frase junto
a la imagen-- desplegados sin poder medir si el modelo obedecia. El prompt es
guia; la garantia va en codigo (CLAUDE.md §4).

LA GARANTIA QUE ESTO MIDE
-------------------------
Una captura solo puede entrar por la galeria, y la app lo marca
(`metadatos_captura.de_galeria`). Sobre esa imagen, lo que el modelo OPINE ya
no devuelve la orden sola:

    «MUESTRA: no»                       -> no se pide rehacer
    el medidor sin ningun numero leido  -> se dice, y no se pide rehacer

CADA PRUEBA TIENE SU CONTROL: la misma imagen tomada con la camara SI
devuelve. Sin el control, estas pruebas pasarian tambien con la regla apagada
para todo el mundo.

LO QUE SIGUE DEVOLVIENDO, y tambien se mide: el numero leido que no coincide
con el que escribio el tecnico. Eso no es una opinion sobre la imagen.
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

OTRA_COSA = ("Captura de pantalla de una conversación de mensajería. No se ve "
             "lo que se pedía.\nCATALOGO: no\nMUESTRA: no\nATENCION: si")

BIEN = ("Cable de fibra partido junto a la roseta.\n"
        "CATALOGO: no\nMUESTRA: si\nATENCION: no")

NO_SE_LEE = ("Captura de pantalla de una aplicación con varios paneles. No se "
             "distingue ningún valor de potencia.\n"
             "CATALOGO: no\nMUESTRA: no se sabe\nATENCION: si")

SE_LEE = ("Medidor óptico, pantalla legible: 1550 nm, -21.0 dBm.\n"
          "CATALOGO: no\nMUESTRA: si\nATENCION: no")

OTRO_VALOR = ("Medidor óptico, pantalla legible: 1550 nm, -40.0 dBm.\n"
              "CATALOGO: no\nMUESTRA: si\nATENCION: no")

REQUISITOS = ("dano_encontrado", "medicion_al_llegar", "medicion_al_salir")


def _foto(org, orden, requisito, texto, *, galeria, vuelta=1):
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=vuelta,
        sha256=f"{requisito}{orden.numero}{vuelta}".ljust(64, "x")[:64],
        storage_key=f"k/{requisito}{orden.numero}{vuelta}",
        nombre_original="m.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO,
        metadatos_captura={"de_galeria": True} if galeria else {})
    AnalisisDeEvidencia.objects.create(
        org=org, evidencia=ev, vuelta=vuelta, origen=AnalisisDeEvidencia.IA,
        texto=texto, pide_atencion="ATENCION: si" in texto)
    return ev


def _orden(org, numero, *, vuelta=1):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    reglas = {"min": -60, "max": -8}
    wt = WorkType.objects.create(org=org, codigo=f"gal{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                             "titulo": "Medición al llegar", "reglas": reglas},
                            {"id": "potencia_al_salir", "tipo": "decimal",
                             "titulo": "Medición al salir", "reglas": reglas}],
                 "evidencias": [{"id": r, "tipo": "foto", "titulo": r,
                                 "obligatorio": True} for r in REQUISITOS]})
    respuestas = {"solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho",
                  "potencia_al_llegar": "-21.0", "potencia_al_salir": "-21.0"}
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98008"},
        datos={"potencia_al_llegar": "-21.0", "potencia_al_salir": "-21.0"},
        vuelta=vuelta)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": vuelta, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


def _revision(orden):
    from campo import revision_del_cierre as RC

    return RC.revisar(orden, pendientes=set())


def _potencia(r):
    return next((p for p in r["puntos"] if p["clave"] == "potencia"), None)


# ---------------------------------------------------------------------------
#  1) «MUESTRA: no»
# ---------------------------------------------------------------------------

def test_CONTROL_la_de_CAMARA_que_muestra_otra_cosa_se_pide_rehacer(org_a):
    orden = _orden(org_a, 9601)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=False)

    assert "dano_encontrado" in _revision(orden)["sugeridas"]


def test_la_de_GALERIA_que_el_modelo_dice_que_muestra_otra_cosa_NO(org_a):
    orden = _orden(org_a, 9602)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=True)

    r = _revision(orden)

    assert "dano_encontrado" not in r["sugeridas"], r["sugeridas"]


def test_pero_NO_CIERRA_SOLA_queda_para_que_la_mire_una_persona(org_a):
    """No devolver no puede convertirse en aprobar: lo que el modelo dudo
    sigue dejando el veredicto en «hay dudas»."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9603)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=True)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False)
    _foto(org_a, orden, "medicion_al_salir", SE_LEE, galeria=False)

    assert _revision(orden)["veredicto"] != RC.CERRAR


def test_el_Supervisor_NO_la_devuelve(org_a):
    """El efecto entero: la funcion que devuelve sola no hace nada."""
    from campo import cierre_por_el_supervisor as CS
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 9604)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=True)
    _foto(org_a, orden, "medicion_al_llegar", NO_SE_LEE, galeria=True)
    _foto(org_a, orden, "medicion_al_salir", SE_LEE, galeria=True)

    assert CS.atender_la_que_no_cierra(orden, _revision(orden)) == "nada"
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert orden.vuelta == 1


def test_la_que_REHIZO_con_la_camara_ya_no_tiene_perdon(org_a):
    """Vale la foto de la ultima vuelta: si la captura se reemplazo por una
    foto de camara que muestra otra cosa, esa SI devuelve."""
    orden = _orden(org_a, 9605, vuelta=2)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=True, vuelta=1)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=False, vuelta=2)

    assert "dano_encontrado" in _revision(orden)["sugeridas"]


def test_y_al_reves_la_captura_que_REEMPLAZO_a_la_de_camara_no_devuelve(org_a):
    orden = _orden(org_a, 9606, vuelta=2)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=False, vuelta=1)
    _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=True, vuelta=2)

    assert "dano_encontrado" not in _revision(orden)["sugeridas"]


def test_solo_vale_el_TRUE_de_la_app(org_a):
    """Un valor cualquiera en ese campo no apaga la regla."""
    from campo.models import EvidenciaTrabajo

    orden = _orden(org_a, 9607)
    ev = _foto(org_a, orden, "dano_encontrado", OTRA_COSA, galeria=False)
    EvidenciaTrabajo.objects.filter(pk=ev.pk).update(
        metadatos_captura={"de_galeria": "true"})

    assert "dano_encontrado" in _revision(orden)["sugeridas"]


# ---------------------------------------------------------------------------
#  2) EL MEDIDOR EN EL QUE NO SE LEE NINGUN NUMERO
# ---------------------------------------------------------------------------

def test_CONTROL_el_medidor_de_CAMARA_que_no_se_lee_se_pide_rehacer(org_a):
    orden = _orden(org_a, 9611)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=False)

    assert "medicion_al_salir" in _revision(orden)["sugeridas"]


def test_el_medidor_de_GALERIA_que_no_se_lee_NO_se_pide_rehacer(org_a):
    orden = _orden(org_a, 9612)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=True)

    r = _revision(orden)

    assert "medicion_al_salir" not in r["sugeridas"], r["sugeridas"]


def test_pero_SE_DICE_y_el_punto_queda_en_duda(org_a):
    """Lo que no se pudo leer no se calla: la persona que mira tiene que
    saber que esa medicion nadie la verifico."""
    orden = _orden(org_a, 9613)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=True)

    p = _potencia(_revision(orden))

    assert p is not None and p["ok"] is None
    assert "no deja leer ningún número" in p["texto"]


def test_el_medidor_REHECHO_con_la_camara_que_no_se_lee_SI_devuelve(org_a):
    """Vale la foto de la ultima vuelta, la misma que se lee. Mirando la
    vieja se perdonaria una foto de camara por la captura que reemplazo
    (medido mutando el orden de la consulta, 21/11/2026)."""
    orden = _orden(org_a, 9614, vuelta=2)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False, vuelta=2)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=True, vuelta=1)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=False, vuelta=2)

    assert "medicion_al_salir" in _revision(orden)["sugeridas"]


def test_y_la_captura_que_reemplazo_al_medidor_de_camara_NO(org_a):
    orden = _orden(org_a, 9615, vuelta=2)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=False, vuelta=2)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=False, vuelta=1)
    _foto(org_a, orden, "medicion_al_salir", NO_SE_LEE, galeria=True, vuelta=2)

    assert "medicion_al_salir" not in _revision(orden)["sugeridas"]


# ---------------------------------------------------------------------------
#  3) LO QUE SIGUE DEVOLVIENDO, DE GALERIA O NO
# ---------------------------------------------------------------------------

def test_el_numero_que_NO_COINCIDE_se_sigue_devolviendo_aunque_sea_captura(org_a):
    """No es una opinion sobre la imagen: se leyo -40.0 y el tecnico escribio
    -21.0. Que la imagen sea una captura no cambia que no cuadran."""
    orden = _orden(org_a, 9621)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=True)
    _foto(org_a, orden, "medicion_al_salir", OTRO_VALOR, galeria=True)

    assert "medicion_al_salir" in _revision(orden)["sugeridas"]


def test_la_captura_que_esta_BIEN_no_pide_nada(org_a):
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9622)
    _foto(org_a, orden, "dano_encontrado", BIEN, galeria=True)
    _foto(org_a, orden, "medicion_al_llegar", SE_LEE, galeria=True)
    _foto(org_a, orden, "medicion_al_salir", SE_LEE, galeria=True)

    r = _revision(orden)

    assert r["sugeridas"] == []
    assert _potencia(r)["ok"] is True
    assert r["veredicto"] != RC.NO_CERRAR
