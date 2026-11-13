# -*- coding: utf-8 -*-
"""
================================================================================
 UN TIMEOUT DEJABA LA ORDEN TRABADA PARA SIEMPRE  --  10/11/2026, OT #200
================================================================================
MEDIDO EN PRODUCCION
---------------------
    v1  medicion_al_salir  [recibido]  1 analisis
          ia 10/11 15:17:31 v1  motivo=no se pudo hablar con el motor (ReadTimeout)

Texto vacio: el motor no contesto esa vez. A las 16:33 --una hora y cuarto
despues-- la orden seguia en «esperando que una persona la revise», y nada
iba a destrabarla.

LA CADENA, Y CADA ESLABON PARECIA CORRECTO POR SEPARADO
--------------------------------------------------------
1. `analizar_evidencia` NO reintenta: devuelve el motivo y termina.
2. `_mirar_y_anotar` escribe la fila igual, con el texto vacio -- a
   proposito, «un fallo hay que poder verlo».
3. `mirar_las_que_faltan` elegia «las que no tienen analisis», y esa fila
   vacia contaba como analisis. La foto no volvia a mirarse nunca.
4. Su docstring decia que la red de atras eran «la tarea por foto y el ciclo
   horario». La tarea no reintenta, y el ciclo horario NO llamaba a esta
   funcion. La red no existia -- prometida por escrito, que es lo que la
   vuelve dificil de ver.

Ninguno de los cuatro da error ni log de alarma. Es exactamente lo que
CLAUDE.md §6 llama codigo construido que no corre.

QUE AFIRMAN ESTAS GUARDAS
--------------------------
El EFECTO: que la foto se vuelva a mirar, que deje de mirarse cuando el
fallo ya no es transitorio, y que el camino que mira sea el del ciclo y no
el del diagnostico.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [],
    "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                "titulo": "Medición al llegar",
                "reglas": {"min": -60, "max": -8}}],
    "evidencias": [{"id": "medicion_al_llegar", "tipo": "foto",
                    "titulo": "Foto del medidor al llegar",
                    "obligatorio": True}],
}


def _orden_con_foto(org, numero, *, intentos_fallidos=0, texto_bueno=None):
    """Una orden con su foto subida. `intentos_fallidos` escribe esa cantidad
    de filas sin texto, como las que deja un ReadTimeout."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EvidenciaTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"to{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA)
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "97997"},
        datos={"potencia_al_llegar": "-50.0"}, vuelta=1)
    ev = EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="medicion_al_llegar",
        vuelta=1, sha256=f"to{numero}".ljust(64, "x")[:64],
        storage_key=f"k/to{numero}", nombre_original="m.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    for _ in range(intentos_fallidos):
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto="",
            motivo="no se pudo hablar con el motor (ReadTimeout)")
    if texto_bueno:
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=texto_bueno)
    return orden, ev


# ---------------------------------------------------------------------------
#  1) LA GUARDA DEL BUG
# ---------------------------------------------------------------------------

def test_UNA_FILA_SIN_TEXTO_NO_CUENTA_COMO_MIRADA(org_a):
    """El caso de la OT #200. Antes de esto la foto quedaba marcada como
    mirada por una fila que solo dice que el motor no contesto."""
    from campo.tasks import mirar_las_que_faltan

    orden, _ = _orden_con_foto(org_a, 9931, intentos_fallidos=1)

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        mirar.return_value = {"estado": "ok", "motivo": ""}
        r = mirar_las_que_faltan(orden)

    assert r["faltaban"] == 1, r
    assert mirar.call_count == 1, "la foto no se volvio a mirar"


def test_UNA_FILA_CON_TEXTO_SI_CUENTA(org_a):
    """La otra mitad, y no es menor: sin esta, cada pasada del ciclo volveria
    a pagarle al modelo por una foto que ya se leyo bien."""
    from campo.tasks import mirar_las_que_faltan

    orden, _ = _orden_con_foto(
        org_a, 9932,
        texto_bueno="Medidor Rouhan, pantalla legible: -50.00 dBm. "
                    "CATALOGO: no MUESTRA: si ATENCION: no")

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        r = mirar_las_que_faltan(orden)

    assert r["faltaban"] == 0, r
    assert mirar.call_count == 0, "se volvio a mirar una foto ya leida"


def test_AGOTADO_EL_TOPE_se_deja_para_una_persona(org_a):
    """Si el motor esta caido de verdad, reintentar sin limite le pega en
    cada pasada y por cada foto. Agotado el tope, la foto queda sin texto y
    la orden espera a una persona."""
    from campo.tasks import INTENTOS_POR_FOTO, mirar_las_que_faltan

    orden, _ = _orden_con_foto(org_a, 9933,
                               intentos_fallidos=INTENTOS_POR_FOTO)

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        r = mirar_las_que_faltan(orden)

    assert r["faltaban"] == 0, r
    assert mirar.call_count == 0

    #  Y UNO MENOS TODAVIA SE INTENTA: sin esto, un tope mal puesto en 0 o 1
    #  pasaria esta guarda igual.
    orden2, _ = _orden_con_foto(org_a, 9934,
                                intentos_fallidos=INTENTOS_POR_FOTO - 1)
    with mock.patch("campo.tasks._mirar_y_anotar") as mirar2:
        mirar2.return_value = {"estado": "ok", "motivo": ""}
        assert mirar_las_que_faltan(orden2)["faltaban"] == 1
    assert mirar2.call_count == 1


# ---------------------------------------------------------------------------
#  2) LA RED DE ATRAS: QUIEN MIRA Y QUIEN NO
# ---------------------------------------------------------------------------

def test_EL_CICLO_HORARIO_MIRA_LAS_QUE_FALTAN(org_a):
    """La red de atras que el docstring prometia y no existia. Sin esto, una
    foto que fallo en el camino inmediato no se mira NUNCA mas."""
    from campo.cierre_por_el_supervisor import cerrar_lo_revisado

    orden, _ = _orden_con_foto(org_a, 9935, intentos_fallidos=1)

    with mock.patch("campo.tasks.mirar_las_que_faltan") as mirar:
        mirar.return_value = {"miradas": 1, "faltaban": 1}
        cerrar_lo_revisado(org_a)

    assert mirar.called, "el ciclo horario sigue sin mirar ninguna foto"
    assert orden.pk in [c.args[0].pk for c in mirar.call_args_list]


def test_EL_DIAGNOSTICO_NO_MIRA_NI_ESCRIBE(org_a):
    """`por_que_no_cerro` llama a `revisadas`. Una herramienta de diagnostico
    que le habla al modelo y escribe filas deja de servir para diagnosticar:
    cambia lo que fue a mirar."""
    from campo.cierre_por_el_supervisor import revisadas
    from django.utils import timezone

    _orden_con_foto(org_a, 9936, intentos_fallidos=1)

    with mock.patch("campo.tasks.mirar_las_que_faltan") as mirar:
        revisadas(org_a, timezone.now())

    assert not mirar.called, "el diagnostico escribio analisis"


def test_UN_FALLO_AL_MIRAR_NO_FRENA_LA_REVISION(org_a):
    """Si el modelo no contesta en medio del ciclo, la orden igual se revisa
    -- con la foto sin texto, que deja el veredicto en revisar. Lo que no
    puede pasar es que el ciclo entero se caiga."""
    from campo.cierre_por_el_supervisor import revisadas
    from django.utils import timezone

    orden, _ = _orden_con_foto(org_a, 9937, intentos_fallidos=1)

    with mock.patch("campo.tasks.mirar_las_que_faltan") as mirar:
        mirar.side_effect = RuntimeError("el motor no contesta")
        salida = revisadas(org_a, timezone.now(), mirar=True)

    assert salida is not None
    assert orden.pk in [o.pk for o, _ in salida], \
        "la orden desaparecio de la revision por un fallo al mirar"
