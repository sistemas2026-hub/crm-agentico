# -*- coding: utf-8 -*-
"""
================================================================================
 PROBAR UNA INSTRUCCION SIN ENSUCIAR NADA  --  06/11/2026
================================================================================
Guarda de `campo/probar_instruccion_de_foto.py`.

LO QUE DE VERDAD PUEDE SALIR MAL
---------------------------------
Un ensayo que deja rastro. Si probar escribiera un `AnalisisDeEvidencia`, el
veredicto de prueba entraria en la revision del Supervisor --que lee la fila
MAS RECIENTE (`revision_del_cierre.py`)-- y en lo que la app le muestra al
tecnico (`analisis_para_el_tecnico.py`). Alguien afinando una redaccion
cerraria o devolveria ordenes sin saberlo.

Por eso el caso central de este archivo no es que la ruta conteste: es que
DESPUES DE PROBAR no haya una fila mas.

Y el segundo: que el pie que viaja lleve el prefijo de produccion. Sin el, el
ensayo mide un prompt que no corre -- el defecto que tuvo el comando de
consola el mismo dia.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

from campo.analisis_de_evidencia import AnalisisDeEvidencia
from campo.models import (AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db

#: Lo que contesta el motor cuando se le pregunta si la empresa lo tiene
#: habilitado, y cuando se le manda la foto.
HABILITADA = {"habilitada": True}
ANALISIS = {"estado": "procesado", "texto": "Se ve el test de velocidad con "
                                            "100 Mbps.\n\nMUESTRA: si\n"
                                            "ATENCION: no",
            "modelo": "m", "segundos": 1.0, "tokens": 10, "motivo": ""}


class _Resp:
    def __init__(self, datos, codigo=200):
        self._datos, self.status_code, self.content = datos, codigo, b"x"

    def json(self):
        return self._datos


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
        org=org_a, numero=9200, tipo_trabajo_version=version,
        cliente_nombre="Cliente Prueba",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO)
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=orden, requisito_id="test_de_velocidad",
        vuelta=orden.vuelta, sha256="s", storage_key="k/f",
        nombre_original="f.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)


def _url(evidencia) -> str:
    return f"/api/campo/evidencias/{evidencia.id}/probar-instruccion/"


def _con_el_motor_contestando(fn):
    """Todo el camino mockeado: el interruptor, los bytes y el analisis."""
    #  `tenant_de` TAMBIEN. Sin el mapeo org -> tenant, `analizar` corta
    #  antes de llamar al motor y devuelve un resultado sin texto. La
    #  prueba daba 200 y fallaba el veredicto: el andamio media otra cosa
    #  que el modulo. Lo encontro el caso que afirma los tres valores.
    with mock.patch("requests.get", return_value=_Resp(HABILITADA)), \
         mock.patch("operaciones.areas_del_tenant.tenant_de",
                    return_value="rapilink"), \
         mock.patch("requests.post", return_value=_Resp(ANALISIS)) as post, \
         mock.patch("campo.inspeccion_visual._bytes_de",
                    return_value=b"\xff\xd8\xff" + b"0" * 2000), \
         mock.patch("campo.inspeccion_visual.se_puede_mirar", return_value=""):
        return fn(post)


def test_probar_NO_escribe_un_analisis(admin_client, evidencia):
    """EL CASO CENTRAL. Un ensayo no puede entrar en la revision.

    La revision del Supervisor y la app del tecnico leen la fila MAS RECIENTE.
    Si probar dejara una, alguien afinando una redaccion estaria cambiando el
    veredicto de una orden real sin saberlo.
    """
    antes = AnalisisDeEvidencia.objects.count()

    def pedir(_post):
        return admin_client.post(
            _url(evidencia), {"instrucciones": "Los tres numeros del test."},
            content_type="application/json")

    r = _con_el_motor_contestando(pedir)
    assert r.status_code == 200, r.content
    assert AnalisisDeEvidencia.objects.count() == antes, "el ensayo dejo rastro"


def test_el_pie_lleva_el_prefijo_de_produccion(admin_client, evidencia):
    """Sin el prefijo se mide un prompt que no corre.

    Produccion envuelve en "Esta foto tenia que mostrar: <titulo>. <texto>", y
    ese prefijo dispara las reglas 7 y 12 de la instruccion -- la de MUESTRA
    entre ellas. El comando de consola tuvo este defecto el mismo dia: aprobaba
    un texto y al guardarlo el veredicto podia cambiar.
    """
    def pedir(_post):
        return admin_client.post(
            _url(evidencia), {"instrucciones": "Los tres numeros del test."},
            content_type="application/json")

    cuerpo = _con_el_motor_contestando(pedir).json()
    assert cuerpo["se_le_pidio"].startswith(
        "Esta foto tenia que mostrar: Test de velocidad."), cuerpo["se_le_pidio"]
    assert "Los tres numeros del test." in cuerpo["se_le_pidio"]
    #  Y NO el texto viejo de la plantilla: se probo el candidato, no el guardado.
    assert "Velocidad contratada" not in cuerpo["se_le_pidio"]


def test_devuelve_los_tres_valores_del_veredicto(admin_client, evidencia):
    def pedir(_post):
        return admin_client.post(
            _url(evidencia), {"instrucciones": "Los tres numeros del test."},
            content_type="application/json")

    cuerpo = _con_el_motor_contestando(pedir).json()
    assert cuerpo["corresponde"] is True
    assert "100 Mbps" in cuerpo["texto"]


def test_un_tecnico_no_puede_probar(user_client, evidencia):
    """Mismo gate que guardar la plantilla.

    Probar y guardar detras de puertas distintas dejaria a alguien afinando un
    texto que despues no puede aplicar -- y cada prueba cuesta una llamada al
    modelo, que se cobra.
    """
    r = user_client.post(_url(evidencia),
                         {"instrucciones": "Lo que sea."},
                         content_type="application/json")
    assert r.status_code == 403, r.content


def test_sin_texto_no_se_gasta_una_llamada(admin_client, evidencia):
    with mock.patch("requests.post") as post:
        r = admin_client.post(_url(evidencia), {"instrucciones": "   "},
                              content_type="application/json")
    assert r.status_code == 400
    post.assert_not_called()


def test_un_texto_mas_largo_del_que_se_puede_guardar_se_rechaza(
        admin_client, evidencia):
    """Aprobar un texto que la plantilla no admite seria aprobar nada.

    El campo tiene tope 400 (`plantillas.MAX_TEXTO_LARGO`). Si el ensayo
    aceptara mas, alguien probaria un texto de 600, le gustaria, y al guardarlo
    se encontraria con que no entra.
    """
    with mock.patch("requests.post") as post:
        r = admin_client.post(_url(evidencia), {"instrucciones": "x" * 401},
                              content_type="application/json")
    assert r.status_code == 400
    assert r.json()["error"] == "INSTRUCCION_LARGA"
    post.assert_not_called()
