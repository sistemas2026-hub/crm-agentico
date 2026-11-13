# -*- coding: utf-8 -*-
"""
================================================================================
 LA MIRADA LE VUELVE AL TECNICO, EN EL SITIO  --  06/11/2026
================================================================================
Guarda de `campo/analisis_para_el_tecnico.py`.

POR QUE EXISTE ESA RUTA, MEDIDO ESE DIA
----------------------------------------
Una orden cerro con las cuatro fotos marcadas "no es lo que se pidio". La
sospecha fue que el analisis se equivocaba; se comparo la misma foto con y
sin degradar (`comparar_calidad_vision`) y las dos dijeron lo mismo:

    "la imagen es la pantalla de un sistema de gestion de tickets con un
     mapa, sin equipos ni instalacion de telecomunicaciones"

El analisis acertaba. El tecnico habia subido una captura de pantalla en el
lugar del test de velocidad. El problema no era la mirada: era CUANDO llega.
Para cuando alguien la lee, el tecnico ya se fue de la casa del cliente.

QUE AFIRMA ESTA GUARDA
----------------------
Tres cosas que, si se rompen, mandan a un tecnico a rehacer una foto que
estaba bien -- o lo dejan irse con una que estaba mal:

  · "no se sabe" NO es "no corresponde". El campo lleva tres valores.
  · la foto de otro no se ve, aunque se tenga el id.
  · lo que dijo una PERSONA le gana a lo que dijo el modelo.
================================================================================
"""
from __future__ import annotations

import pytest

from campo.analisis_de_evidencia import AnalisisDeEvidencia
from campo.models import (AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db


def _url(evidencia) -> str:
    return f"/api/campo/evidencias/{evidencia.id}/analisis/"


@pytest.fixture
def evidencia(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="corr", nombre="Correctivo",
                                 labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [
            {"id": "test_de_velocidad", "titulo": "Test de velocidad",
             "tipo": "foto", "obligatorio": True,
             "instrucciones": "Velocidad contratada"}]})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=9100, tipo_trabajo_version=version,
        cliente_nombre="Cliente Prueba",
        estado_operativo=OrdenTrabajo.EN_SITIO)
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=orden, requisito_id="test_de_velocidad",
        vuelta=orden.vuelta, sha256="s", storage_key="k/f",
        nombre_original="f.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)


def _analisis(evidencia, texto, **kw):
    return AnalisisDeEvidencia.objects.create(
        org=evidencia.org, evidencia=evidencia, vuelta=evidencia.vuelta,
        texto=texto, **kw)


def test_sin_analisis_todavia_no_bloquea_nada(user_client, evidencia):
    """Contesta 200 con `listo: false`, nunca un error.

    Si esto fuera un 404 o un 500, la app no podria distinguir "todavia no se
    miro" de "se cayo la red", y le mostraria un error al tecnico por algo que
    no lo es.
    """
    r = user_client.get(_url(evidencia))
    assert r.status_code == 200, r.content
    cuerpo = r.json()
    assert cuerpo["listo"] is False
    #  Y le dice que se esperaba de la foto, que es util aunque no haya
    #  analisis: el tecnico puede compararlo con lo que saco.
    assert "Velocidad contratada" in cuerpo["que_se_pidio"]


def test_una_foto_que_no_corresponde_se_dice_con_su_motivo(user_client, evidencia):
    """El caso real del 06/11/2026, con el texto que devolvio el modelo."""
    _analisis(evidencia,
              "No se ve lo que se pedía: la imagen es la pantalla de un "
              "sistema de gestión de tickets con un mapa, sin equipos ni "
              "instalación de telecomunicaciones.\n\nMUESTRA: no\nATENCION: si",
              pide_atencion=True)

    cuerpo = user_client.get(_url(evidencia)).json()
    assert cuerpo["listo"] is True
    assert cuerpo["corresponde"] is False
    assert "sistema de gestión de tickets" in cuerpo["resumen"]
    #  LAS MARCAS DEL PROTOCOLO NO SE MUESTRAN. Son como el codigo habla
    #  consigo mismo; en la pantalla del tecnico son ruido.
    assert "MUESTRA" not in cuerpo["resumen"]
    assert "ATENCION" not in cuerpo["resumen"]


def test_no_se_sabe_NO_es_no_corresponde(user_client, evidencia):
    """La diferencia que evita mandar a rehacer una foto que esta bien.

    `muestra_lo_pedido` devuelve tres valores y esta ruta los pasa tal cual.
    Un parser binario leeria "no se sabe" como "no" --paso el 06/11/2026 en
    `comparar_calidad_vision`-- y el tecnico volveria a sacar una foto que
    nadie dijo que estuviera mal.
    """
    _analisis(evidencia, "La imagen es un primer plano y el borde queda fuera "
                         "de cuadro.\n\nMUESTRA: no se sabe\nATENCION: si",
              pide_atencion=True)

    cuerpo = user_client.get(_url(evidencia)).json()
    assert cuerpo["corresponde"] is None, cuerpo
    assert cuerpo["corresponde"] is not False


def test_lo_que_dijo_una_persona_le_gana_al_modelo(user_client, evidencia):
    """La correccion es una fila NUEVA, y la mas reciente manda."""
    _analisis(evidencia, "No se ve.\n\nMUESTRA: no\nATENCION: si",
              pide_atencion=True, origen=AnalisisDeEvidencia.IA)
    _analisis(evidencia, "Si se ve el medidor.\n\nMUESTRA: si\nATENCION: no",
              pide_atencion=False, origen=AnalisisDeEvidencia.PERSONA)

    cuerpo = user_client.get(_url(evidencia)).json()
    assert cuerpo["corresponde"] is True, cuerpo
    assert cuerpo["lo_dijo"] == AnalisisDeEvidencia.PERSONA
    assert cuerpo["pide_atencion"] is False


def test_la_foto_de_otro_no_se_ve_aunque_se_tenga_el_id(
        user_client, org_a, evidencia):
    """El aislamiento es el mismo del resto, no uno nuevo.

    Se le quita la asignacion: el tecnico deja de tener que ver con esa orden
    y la ruta tiene que dejar de mostrarsela, aunque conozca el id.

    404 y no 403: quien no tiene por que verla tampoco tiene por que saber
    que existe.
    """
    _analisis(evidencia, "Lo que sea.\n\nMUESTRA: si\nATENCION: no")
    AsignacionTrabajo.objects.filter(orden=evidencia.orden_trabajo).delete()

    r = user_client.get(_url(evidencia))
    assert r.status_code == 404, r.content


def test_el_resumen_no_se_corta_a_la_mitad_de_una_palabra(user_client, evidencia):
    """Se lee en un telefono, al sol, con guantes: no puede quedar cortado feo."""
    largo = ("Se ve un medidor de potencia optica con la pantalla encendida. "
             * 12)
    _analisis(evidencia, largo + "\n\nMUESTRA: si\nATENCION: no")

    resumen = user_client.get(_url(evidencia)).json()["resumen"]
    assert len(resumen) <= 230, len(resumen)
    assert resumen.endswith((".", "…")), repr(resumen[-30:])
