# -*- coding: utf-8 -*-
"""
================================================================================
 UNA IMAGEN DE CATALOGO NO ES EVIDENCIA DE NADA  --  09/11/2026
================================================================================
EL CASO, MEDIDO EN VIVO
------------------------
El usuario subio como evidencia la foto de catalogo de un medidor Rouhan --el
equipo recortado sobre fondo blanco, de la pagina de una tienda-- en las DOS
mediciones de una orden. El modelo lo vio y lo escribio las dos veces:

    "Se ve medidor de potencia optico Rouhan con pantalla legible: 1550 nm,
     -21.0 dBm, 0.682 uW, 2kHz. Equipo sobre fondo blanco, sin entorno de
     instalacion; imagen de catalogo.
     MUESTRA: si
     ATENCION: si"

Y la orden paso igual:

  - `MUESTRA` decia `si`, con razon: se pedia la pantalla del medidor y la
    pantalla SE VE. La marca contesta si la imagen muestra lo pedido, no de
    donde salio.
  - `ATENCION: si` por si solo no devuelve nada desde el 06/11, y ese motivo
    sigue en pie: «4 de 4 fotos piden una mirada» sobre fotos oscuras de un
    trabajo bien hecho.

POR QUE ESTA SI DEVUELVE Y «ATENCION» NO
-----------------------------------------
Son afirmaciones de distinto peso. «Pide una mirada» es un juicio difuso
sobre la calidad de una foto. «Es material de producto» es un hecho sobre su
ORIGEN: esa imagen no se tomo en la casa del cliente, asi que no es evidencia,
por nitida que sea. Es el mismo criterio con el que `MUESTRA: no` ya devuelve:
lo verificable mirando.

Decision del usuario del 09/11/2026, con las dos opciones a la vista.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

#: El analisis real, copiado de la prueba en vivo.
DE_CATALOGO = (
    "Se ve medidor de potencia óptico Rouhan con pantalla legible: 1550 nm, "
    "-21.0 dBm, 0.682 µW, 2kHz. Equipo sobre fondo blanco, sin entorno de "
    "instalación; imagen de catálogo.\n"
    "CATALOGO: si\nMUESTRA: si\nATENCION: si")

DEL_TRABAJO = (
    "Se ve la pantalla de un medidor Rouhan sostenido junto a la roseta: "
    "1550 nm, -21.0 dBm. Lectura legible.\n"
    "CATALOGO: no\nMUESTRA: si\nATENCION: no")

#: Un analisis de ANTES de la regla 13: sin la marca.
SIN_LA_MARCA = ("Se ve la pantalla de un medidor Rouhan: 1550 nm, -21.0 dBm.\n"
                "MUESTRA: si\nATENCION: no")


# ---------------------------------------------------------------------------
#  1) LEER LA MARCA
# ---------------------------------------------------------------------------

def test_la_marca_se_lee():
    from campo.tasks import es_de_catalogo

    assert es_de_catalogo(DE_CATALOGO) is True
    assert es_de_catalogo(DEL_TRABAJO) is False


def test_SIN_MARCA_NO_ES_QUE_SI(org_a):
    """Un analisis viejo no la trae. Tratar la ausencia como «es de catalogo»
    devolveria ordenes por fotos que nadie miro con este criterio."""
    from campo.tasks import es_de_catalogo

    assert es_de_catalogo(SIN_LA_MARCA) is None
    assert es_de_catalogo("") is None
    assert es_de_catalogo(None) is None


def test_LA_PALABRA_EN_LA_PROSA_NO_CUENTA():
    """LA GUARDA QUE JUSTIFICA LEER POR LINEA y no con `rfind` sobre todo el
    texto, como hace `muestra_lo_pedido`. El analisis real dice «imagen de
    catalogo.» en el parrafo: si se buscara en cualquier posicion, el veredicto
    dependeria de como redacto el modelo esa frase."""
    from campo.tasks import es_de_catalogo

    texto = ("Se ve un medidor junto a la roseta. No parece imagen de "
             "catalogo: hay cableado alrededor.\n"
             "CATALOGO: no\nATENCION: no")

    assert es_de_catalogo(texto) is False


def test_la_marca_con_tilde_tambien():
    from campo.tasks import es_de_catalogo

    assert es_de_catalogo("Algo.\nCATÁLOGO: si\nATENCION: si") is True


# ---------------------------------------------------------------------------
#  2) EL EFECTO: LA ORDEN VUELVE
# ---------------------------------------------------------------------------

def _orden(org, numero, *, textos):
    """`textos`: {requisito: texto del analisis}. None = sin analisis."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"cat{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [],
                 "evidencias": [{"id": r, "tipo": "foto", "titulo": r,
                                 "obligatorio": True} for r in textos]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98008"}, vuelta=1)
    for requisito, texto in textos.items():
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="f.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        if texto is not None:
            AnalisisDeEvidencia.objects.create(
                org=org, evidencia=ev, vuelta=1,
                origen=AnalisisDeEvidencia.IA, texto=texto,
                pide_atencion="ATENCION: si" in texto)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "sin_material_confirmado": True,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"}})
    return orden


def test_LA_FOTO_DE_CATALOGO_SE_PIDE_REHACER(org_a):
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9601, textos={"medicion_al_salir": DE_CATALOGO,
                                        "dano_encontrado": DEL_TRABAJO})

    r = RC.revisar(orden, pendientes=set())

    assert r["sugeridas"] == ["medicion_al_salir"], r["sugeridas"]


def test_Y_LA_ORDEN_VUELVE_DE_VERDAD(org_a):
    """EL EFECTO. Que `sugeridas` la nombre no prueba que la orden vuelva."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 9602, textos={"medicion_al_salir": DE_CATALOGO})
    revision = RC.revisar(orden, pendientes=set())

    with mock.patch("campo.services.nota_al_isp._pedir") as pedir:
        pedir.return_value = {"anotada": True, "codigo": "anotada"}
        assert atender_la_que_no_cierra(orden, revision) == "devuelta"

    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert fresca.vuelta == 2


def test_el_punto_LO_NOMBRA_en_vez_de_decir_pide_una_mirada(org_a):
    """El supervisor leia «1 de 2 fotos piden una mirada» y no tenia como
    saber que la diferencia con una foto oscura era esa."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9603, textos={"medicion_al_salir": DE_CATALOGO,
                                        "dano_encontrado": DEL_TRABAJO})

    r = RC.revisar(orden, pendientes=set())
    p = next(x for x in r["puntos"] if x["clave"] == "fotos")

    assert "imagen de producto" in p["texto"], p["texto"]
    assert p["ok"] is None, "sigue sin poder decir que NO (31/10)"


def test_una_foto_del_trabajo_NO_DEVUELVE_NADA(org_a):
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9604, textos={"medicion_al_salir": DEL_TRABAJO})

    r = RC.revisar(orden, pendientes=set())

    assert r["sugeridas"] == [], r["sugeridas"]
    assert r["veredicto"] == RC.CERRAR, r["veredicto"]


def test_un_analisis_VIEJO_sin_la_marca_no_devuelve(org_a):
    """La regla 13 es del 09/11. Las ordenes analizadas antes no la traen y no
    pueden empezar a volver al tecnico por eso."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9605, textos={"medicion_al_salir": SIN_LA_MARCA})

    r = RC.revisar(orden, pendientes=set())

    assert r["sugeridas"] == [], r["sugeridas"]


def test_no_se_pide_una_que_la_PLANTILLA_NO_DECLARA(org_a):
    """Mismo criterio que el rango y la medicion: pedir rehacer algo que el
    formulario no tiene deja al tecnico sin poder cumplirlo."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9606, textos={"medicion_al_salir": DE_CATALOGO})
    version = orden.tipo_trabajo_version
    #  La version se publica inmutable: se crea otra sin esa evidencia.
    from campo.models import WorkTypeVersion
    otra = WorkTypeVersion.objects.create(
        work_type=version.work_type, version=2, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden.tipo_trabajo_version = otra
    orden.save(update_fields=["tipo_trabajo_version"])

    r = RC.revisar(orden, pendientes=set())

    assert r["sugeridas"] == [], r["sugeridas"]


# ---------------------------------------------------------------------------
#  3) LO QUE EL TECNICO VE
# ---------------------------------------------------------------------------

def test_la_marca_NO_se_le_muestra_al_tecnico():
    """`CATALOGO:` es plomeria. En la pantalla del telefono estorba."""
    from campo.analisis_para_el_tecnico import _resumen

    salida = _resumen(DE_CATALOGO)

    assert "CATALOGO" not in salida.upper()
    assert "imagen de catálogo" in salida
