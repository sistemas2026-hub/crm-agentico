# -*- coding: utf-8 -*-
"""
================================================================================
 LA POTENCIA SE LEE DE DONDE PRODUCCION LA TIENE  --  07/11/2026
================================================================================
El usuario cerro la OT #185 con -35.0 dBm al salir, que esta fuera del rango
que Rapilink declaro bueno (-27 a -8). El Supervisor no dijo nada del rango.

MEDIDO EN PRODUCCION ese mismo dia:

    OT 185 | estado completada_campo | vuelta 1
    plantilla v9
    campo al salir: {'max': -8.0, 'min': -60.0, 'required': True}
    bueno         : {'max': -8.0, 'min': -27.0}
    cierre        : SI
    respuestas pot: {}          <- ACA
    punto rango   : None
    punto potencia: None

La plantilla estaba bien, el rango cargado, el cierre existia. Lo que fallaba
es DONDE se leia: los campos del formulario viven en `OrdenTrabajo.datos`
--es lo que `cierre_en_isp.resumen_de` imprime en el ticket del ISP, y por
eso la nota SI mostraba el -35.0-- y la revision leia
`cierre.datos["respuestas"]`, que solo trae lo que se manda en el momento
del cierre.

POR QUE LAS 37 GUARDAS DE ESE BLOQUE ESTABAN EN VERDE
------------------------------------------------------
Porque el andamiaje ponia la potencia en `cierre.datos["respuestas"]`. Cada
una afirmaba sobre el efecto y cada mutacion moria -- contra una forma del
dato que produccion no usa. Una prueba no puede descubrir que su propio
andamiaje miente; lo unico que lo descubre es mirar una fila real.

Por eso ESTA guarda arma la orden al reves de como la armaban aquellas: el
evento de cierre SIN una sola clave de potencia, y `orden.datos` CON ella.
Si la lectura vuelve al lugar equivocado, estas se ponen rojas y aquellas no.
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

PISO, TECHO = -27.0, -8.0


def _como_en_produccion(org, numero, *, al_salir="-35.0", al_llegar=None,
                        bueno=(PISO, TECHO)):
    """Una orden con la forma EXACTA de la OT #185.

    `orden.datos` trae la potencia; el evento de cierre trae `solucion` y
    `servicio_validado` y NINGUNA clave de potencia.
    """
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    campos = []
    for ident, titulo in (("potencia_al_llegar", "Potencia al llegar"),
                          ("potencia_al_salir", "Potencia al salir")):
        campo = {"id": ident, "tipo": "decimal", "titulo": titulo,
                 "unidad": "dBm"}
        if ident == "potencia_al_salir" and bueno is not None:
            campo["bueno"] = {"min": bueno[0], "max": bueno[1]}
        campos.append(campo)

    wt = WorkType.objects.create(org=org, codigo=f"p{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=9, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [], "campos": campos})

    datos = {"potencia_al_salir": al_salir,
             "que_encontro": "Problema dentro de la casa"}
    if al_llegar is not None:
        datos["potencia_al_llegar"] = al_llegar

    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, datos=datos)

    #  EL EVENTO, TAL COMO LLEGA: sin una sola clave de potencia.
    cierre = EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"}})
    return orden, cierre


# ---------------------------------------------------------------------------
#  EL CASO QUE FALLO EN PRODUCCION
# ---------------------------------------------------------------------------

def test_el_evento_de_cierre_NO_trae_la_potencia(org_a):
    """La premisa. Si fallara, el caso no reproduce lo que paso."""
    _orden, cierre = _como_en_produccion(org_a, 501)

    respuestas = (cierre.datos or {}).get("respuestas") or {}

    assert not [k for k in respuestas if "potencia" in k], respuestas


def test_la_OT_185_AHORA_SI_queda_fuera_de_rango(org_a):
    from campo.revision_del_cierre import _en_rango

    orden, cierre = _como_en_produccion(org_a, 502, al_salir="-35.0")

    p = _en_rango(orden, cierre)

    assert p is not None, "el punto no aparecio, que es lo que paso el 07/11"
    assert p["ok"] is False, p
    assert "-35" in p["texto"], p["texto"]


def test_una_medida_BUENA_sigue_diciendo_que_si(org_a):
    from campo.revision_del_cierre import _en_rango

    orden, cierre = _como_en_produccion(org_a, 503, al_salir="-18.0")

    assert _en_rango(orden, cierre)["ok"] is True


def test_el_punto_entra_en_la_REVISION_entera(org_a):
    """Que `_en_rango` acierte no prueba que la revision lo muestre."""
    from campo.revision_del_cierre import revisar

    orden, _cierre = _como_en_produccion(org_a, 504, al_salir="-35.0")

    revision = revisar(orden)

    rango = [p for p in revision["puntos"] if p.get("clave") == "rango"]
    assert rango, revision["puntos"]
    assert rango[0]["ok"] is False, rango[0]


def test_fuera_de_rango_NO_DEJA_CERRAR(org_a):
    """El efecto que el usuario pidio, no el texto del punto."""
    from campo.revision_del_cierre import revisar

    orden, _cierre = _como_en_produccion(org_a, 505, al_salir="-35.0")

    assert revisar(orden)["veredicto"] != "APROBABLE"


# ---------------------------------------------------------------------------
#  LA COMPARACION CON LA FOTO, POR EL MISMO CAMINO
# ---------------------------------------------------------------------------

def test_la_potencia_de_la_foto_tambien_lee_la_orden(org_a):
    """La lectura del modelo vive en `AnalisisDeEvidencia`, colgada de la
    evidencia -- no en un evento. La primera version de esta guarda la puso
    en un `EventoTrabajo` y fallo: el mismo error de andamiaje que escondio
    el defecto que esta prueba existe para cazar, encontrado esta vez porque
    se leyo `_texto_de_la_foto` antes de creerle a la prueba."""
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo
    from campo.revision_del_cierre import _potencia

    orden, cierre = _como_en_produccion(org_a, 506, al_salir="-21.0")
    evidencia = EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=orden, requisito_id="medicion_al_salir",
        vuelta=orden.vuelta, sha256="s506".ljust(64, "x")[:64],
        storage_key="k/506", nombre_original="f.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=org_a, evidencia=evidencia, vuelta=orden.vuelta,
        texto="la pantalla se lee: 1310 nm y -70.00 dBm")

    p = _potencia(orden, cierre)

    assert p is not None, "sin leer la orden, este punto no aparece"
    assert "-70" in p["texto"] and "-21" in p["texto"], p["texto"]


# ---------------------------------------------------------------------------
#  QUE NO SE PIERDA LO QUE SOLO VIVE EN EL EVENTO
# ---------------------------------------------------------------------------

def test_lo_que_solo_esta_en_el_EVENTO_sigue_llegando(org_a):
    """`orden.datos` gana, pero no tapa lo que el evento trae solo."""
    from campo.revision_del_cierre import _lo_que_escribio_el_tecnico

    orden, cierre = _como_en_produccion(org_a, 507)

    todo = _lo_que_escribio_el_tecnico(orden, cierre)

    assert todo["solucion"] == "se cambia conector APC"
    assert todo["servicio_validado"] == "Hecho"
    assert todo["potencia_al_salir"] == "-35.0"


def test_la_orden_GANA_sobre_el_evento(org_a):
    """Si los dos traen el campo, manda el formulario de registro."""
    from campo.revision_del_cierre import _lo_que_escribio_el_tecnico

    orden, cierre = _como_en_produccion(org_a, 508, al_salir="-35.0")
    cierre.datos["respuestas"]["potencia_al_salir"] = "-18.0"
    cierre.save(update_fields=["datos"])

    todo = _lo_que_escribio_el_tecnico(orden, cierre)

    assert todo["potencia_al_salir"] == "-35.0", todo


def test_un_vacio_en_la_orden_no_borra_lo_del_evento(org_a):
    from campo.revision_del_cierre import _lo_que_escribio_el_tecnico

    orden, cierre = _como_en_produccion(org_a, 509)
    orden.datos["solucion"] = ""
    orden.save(update_fields=["datos"])

    todo = _lo_que_escribio_el_tecnico(orden, cierre)

    assert todo["solucion"] == "se cambia conector APC"


def test_sin_cierre_igual_se_lee_la_orden(org_a):
    from campo.revision_del_cierre import _lo_que_escribio_el_tecnico

    orden, _cierre = _como_en_produccion(org_a, 510)

    assert _lo_que_escribio_el_tecnico(orden, None)["potencia_al_salir"] == "-35.0"
