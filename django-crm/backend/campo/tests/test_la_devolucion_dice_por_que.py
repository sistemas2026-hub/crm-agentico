# -*- coding: utf-8 -*-
"""
================================================================================
 UNA DEVOLUCION QUE NO DICE POR QUE DEJA AL TECNICO ADIVINANDO  --  09/11/2026
================================================================================
EL CASO, MEDIDO EN LA BITACORA DE LA OT #217 (09/11, 21:18 Bogota)
-------------------------------------------------------------------
    21:18:27  correccion_requerida  requisitos_a_corregir=['medicion_al_llegar']
    21:18:29  devuelta_por_el_supervisor  requisitos=['medicion_al_llegar']
    21:19:06  accion_marcar_llegada
    21:19:45  datos_actualizados        <- corrigio el NUMERO
    21:19:46  cierre_campo
    21:20:35  datos_actualizados        <- otra vez
    21:20:37  cierre_campo
    21:26:33  cierre_campo              <- y otra vez
    (nunca mas un `trabajo_completado_campo`)

El tecnico mando el reporte tres veces y la orden se quedo en `en_sitio`:
`verificar_checklist_completo` exige evidencia DE ESTA VUELTA del requisito
devuelto (CORRECCION_PENDIENTE), y nunca subio la foto nueva.

POR QUE CORRIGIO LO QUE NO ERA
-------------------------------
Porque lo que le llego fue «Rehacer: medicion_al_llegar» y nada mas. La
observacion salia VACIA, y no por un olvido: `lo_que_falto` toma solo los
puntos `ok is False`, y los dos puntos que hoy devuelven una orden sola --la
foto que muestra otra cosa, y el numero que no salio de esa pantalla-- valen
`None` a proposito desde el 31/10.

Esas dos reglas son correctas cada una por su lado. Juntas dejaban toda
devolucion automatica sin motivo escrito.

LO QUE ESTAS GUARDAS AFIRMAN
-----------------------------
El EFECTO sobre lo que queda escrito en la bitacora y en el ticket, no que
exista una funcion nueva. La de verdad es `test_LA_OBSERVACION_LLEGA_CON_LOS_
DOS_NUMEROS`: devuelve una orden entera y lee el evento.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  1) EL CRITERIO
# ---------------------------------------------------------------------------

def test_un_punto_que_dice_NO_sigue_entrando():
    from campo.services.nota_al_isp import por_que_se_devuelve

    r = {"puntos": [{"clave": "servicio", "ok": False,
                     "texto": "El técnico dice que el servicio NO quedó funcionando."}]}

    assert por_que_se_devuelve(r) == [
        "El técnico dice que el servicio NO quedó funcionando."]


def test_EL_PUNTO_QUE_DEVUELVE_LA_ORDEN_ENTRA_AUNQUE_VALGA_NONE():
    """El caso del usuario. Antes este texto no llegaba a ninguna parte."""
    from campo.services.nota_al_isp import lo_que_falto, por_que_se_devuelve

    r = {"puntos": [{"clave": "potencia", "ok": None,
                     "texto": "La foto y el reporte no dicen lo mismo: al llegar, "
                              "la foto marca -50.0 dBm y el reporte dice -21.0."}]}

    assert por_que_se_devuelve(r) != []
    assert "-50.0" in por_que_se_devuelve(r)[0]
    #  Y la diferencia con lo de antes, en la misma guarda: sin esto, la
    #  prueba pasaria igual el dia que alguien unifique las dos funciones.
    assert lo_que_falto(r) == []


def test_la_foto_que_muestra_OTRA_COSA_tambien_entra():
    from campo.services.nota_al_isp import por_que_se_devuelve

    r = {"puntos": [{"clave": "fotos", "ok": None,
                     "texto": "1 de 4 fotos no muestra lo que se pidió."}]}

    assert por_que_se_devuelve(r) == ["1 de 4 fotos no muestra lo que se pidió."]


def test_LO_QUE_ESTA_BIEN_no_se_escribe():
    from campo.services.nota_al_isp import por_que_se_devuelve

    r = {"puntos": [{"clave": "checklist", "ok": True,
                     "texto": "El checklist está completo: datos y fotos."},
                    {"clave": "potencia", "ok": None, "texto": "No coinciden."}]}

    assert por_que_se_devuelve(r) == ["No coinciden."]


def test_LA_ESPERA_DE_LA_MEDICION_NO_ENTRA():
    """«Se mira a las 48 h» no es algo que el tecnico pueda rehacer hoy.
    Escrito en una devolucion, tapa el motivo de verdad."""
    from campo.services.nota_al_isp import por_que_se_devuelve

    r = {"puntos": [{"clave": "medicion", "ok": None,
                     "texto": "Todavía falta medir la señal después del arreglo."},
                    {"clave": "potencia", "ok": None, "texto": "No coinciden."}]}

    assert por_que_se_devuelve(r) == ["No coinciden."]


def test_pero_una_medicion_que_dice_QUE_NO_si_entra():
    """La exclusion es de la ESPERA (`None`), no del punto. Una señal que
    quedo fuera de rango es un hecho medido y el tecnico tiene que saberlo."""
    from campo.services.nota_al_isp import por_que_se_devuelve

    r = {"puntos": [{"clave": "medicion", "ok": False,
                     "texto": "La señal NO quedó en rango después del arreglo."}]}

    assert por_que_se_devuelve(r) != []


def test_una_revision_rota_no_levanta():
    from campo.services.nota_al_isp import por_que_se_devuelve

    assert por_que_se_devuelve(None) == []
    assert por_que_se_devuelve({"puntos": ["basura", None, 7]}) == []


# ---------------------------------------------------------------------------
#  2) EL EFECTO: QUE QUEDA ESCRITO CUANDO LA ORDEN VUELVE DE VERDAD
# ---------------------------------------------------------------------------

def _orden_con_la_potencia_que_no_cuadra(org, numero):
    """La OT #217 reducida: la foto marca -50 y el tecnico escribio -21."""
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)
    from campo.analisis_de_evidencia import AnalisisDeEvidencia

    wt = WorkType.objects.create(org=org, codigo=f"dpq{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                             "titulo": "Medición al llegar",
                             "reglas": {"min": -60, "max": -8}}],
                 "evidencias": [{"id": "medicion_al_llegar", "tipo": "foto",
                                 "titulo": "Foto del medidor al llegar",
                                 "obligatorio": True}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98008"},
        datos={"potencia_al_llegar": "-21.0"}, vuelta=1)
    evidencia = EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="medicion_al_llegar", vuelta=1,
        sha256=f"med{numero}".ljust(64, "x")[:64],
        storage_key=f"k/med{numero}", nombre_original="medidor.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=org, evidencia=evidencia, vuelta=1,
        origen=AnalisisDeEvidencia.IA,
        texto="Medidor óptico Rouhan con pantalla legible: 1550nm, -50.00 dBm, "
              "0.000 µW, 2kHz. MUESTRA: si ATENCION: no")
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1,
               "respuestas": {"potencia_al_llegar": "-21.0",
                              "solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


def test_LA_OBSERVACION_LLEGA_CON_LOS_DOS_NUMEROS(org_a):
    """EL EFECTO, leido donde el tecnico lo lee: el evento
    `correccion_requerida`. Esta es la guarda que mata el bug de la OT #217 --
    las de arriba solo prueban el criterio."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import EventoTrabajo

    orden = _orden_con_la_potencia_que_no_cuadra(org_a, 9901)
    revision = RC.revisar(orden, pendientes=set())
    assert revision["sugeridas"] == ["medicion_al_llegar"], revision["sugeridas"]

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        assert atender_la_que_no_cierra(orden, revision) == "devuelta"

    ev = EventoTrabajo.objects.filter(org=org_a, orden=orden,
                                      tipo="correccion_requerida").first()
    assert ev is not None
    observacion = (ev.datos or {}).get("observacion") or ""
    assert observacion.strip(), "la devolucion volvio a salir sin motivo"
    assert "-50" in observacion, observacion
    assert "-21" in observacion, observacion


def test_y_el_TICKET_DEL_ISP_tambien_lo_recibe(org_a):
    """La misma observacion viaja a `anotar_devolucion`. Sin esto, quien mira
    el ticket ve «vuelve a campo» sin saber que estaba mal."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra

    orden = _orden_con_la_potencia_que_no_cuadra(org_a, 9902)
    revision = RC.revisar(orden, pendientes=set())

    #  Se intercepta `_pedir` y no `requests.post`: sin una empresa mapeada,
    #  `_pedir` se va por `sin_empresa` ANTES de llamar a nadie, y una guarda
    #  sobre el post pasaria en verde sin haber mirado el texto.
    with mock.patch("campo.services.nota_al_isp._pedir") as pedir:
        pedir.return_value = {"anotada": True, "codigo": "anotada"}
        atender_la_que_no_cierra(orden, revision)
        cuerpos = [c.args[1] if len(c.args) > 1 else c.kwargs.get("cuerpo")
                   for c in pedir.call_args_list]

    textos = [str((c or {}).get("texto") or "") for c in cuerpos]
    assert any("-50" in t and "-21" in t for t in textos), textos
