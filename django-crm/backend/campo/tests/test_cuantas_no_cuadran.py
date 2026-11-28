# -*- coding: utf-8 -*-
"""
================================================================================
 EL COMANDO QUE MIDE CUANTAS NO CUADRAN  --  12/11/2026
================================================================================
`cuantas_no_cuadran` pone el ticket y el reporte del tecnico uno al lado del
otro para que una PERSONA cuente cuantos no cuadran. Ese numero decide si se
enciende el cotejo automatico (PRD §8.23), que cuesta una llamada al modelo
por cada cierre.

QUE AFIRMAN ESTAS GUARDAS, Y POR QUE ESAS
------------------------------------------
  1. **No escribe nada.** Es un comando de medicion: si escribiera, la
     medicion cambiaria lo que mide.
  2. **No llama a ningun proveedor.** Usar el modelo para decidir si vale la
     pena usar el modelo seria pagar justo lo que se quiere evaluar.
  3. **No imprime datos del cliente.** La salida se corre en el contenedor de
     PRODUCCION y se pega en un chat -- el mismo modo de falla que dejo 14
     secretos en transcripciones.
  4. **Pone los dos lados.** Sin uno de los dos no hay nada que contar, y el
     comando dejaria de servir para lo que existe.

  pytest campo/tests/test_cuantas_no_cuadran.py --reuse-db --no-cov
================================================================================
"""
from __future__ import annotations

from io import StringIO

import pytest

pytestmark = pytest.mark.django_db

CASO = ("Verificar el puerto 3/4/4 de la OLT: hay tres clientes en LOS "
        "a la vez.")
REPORTE = "fibra partida antes del conector"


def _orden(org, numero, *, con_reporte=True):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"cq{numero}",
                                 nombre="Soporte Técnico", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        resumen=CASO,
        #  LOS DATOS QUE NO PUEDEN SALIR.
        cliente_nombre="Beatriz Pinzón", cliente_telefono="3001234567",
        cliente_direccion="Calle 50 # 10-20")
    if con_reporte:
        EventoTrabajo.objects.create(
            org=org, orden=o, tipo="cierre_campo",
            datos={"respuestas": {"que_encontro": REPORTE,
                                  "solucion": "se preparó el conector"}})
    return o


def _correr(org, **kw) -> str:
    from django.core.management import call_command

    salida = StringIO()
    call_command("cuantas_no_cuadran", org=str(org.id), stdout=salida, **kw)
    return salida.getvalue()


def test_PONE_LOS_DOS_LADOS(org_a):
    """Lo que el comando existe para hacer. Sin los dos lados no hay nada
    que contar."""
    _orden(org_a, 9960)

    t = _correr(org_a)

    assert "SE PIDIÓ" in t and "QUÉ HIZO" in t
    assert "puerto 3/4/4" in t, t
    assert "fibra partida" in t, t


def test_NO_IMPRIME_DATOS_DEL_CLIENTE(org_a):
    """La salida se corre en producción y se pega en un chat."""
    _orden(org_a, 9961)

    t = _correr(org_a)

    assert "Beatriz" not in t, t
    assert "3001234567" not in t, t
    assert "Calle 50" not in t, t


def test_NO_ESCRIBE_NI_UNA_FILA(org_a):
    """Una medición que cambia lo que mide no sirve. Se cuenta TODO lo que
    la orden podría ganar: eventos, análisis y cotejos."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.cotejo_del_reporte import CotejoDelReporte
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9962)
    antes = (EventoTrabajo.objects.filter(orden=orden).count(),
             AnalisisDeEvidencia.objects.filter(org=org_a).count(),
             CotejoDelReporte.objects.filter(orden=orden).count(),
             orden.estado_operativo, orden.estado_validacion)

    _correr(org_a)

    orden.refresh_from_db()
    assert (EventoTrabajo.objects.filter(orden=orden).count(),
            AnalisisDeEvidencia.objects.filter(org=org_a).count(),
            CotejoDelReporte.objects.filter(orden=orden).count(),
            orden.estado_operativo, orden.estado_validacion) == antes


def test_NO_LE_PREGUNTA_A_NINGUN_PROVEEDOR(org_a):
    """Usar el modelo para decidir si vale la pena usar el modelo sería
    pagar justo lo que se quiere evaluar."""
    from unittest import mock

    _orden(org_a, 9963)

    with mock.patch("requests.post") as post, mock.patch("requests.get") as get:
        _correr(org_a)

    assert not post.called and not get.called


def test_SEPARA_LAS_QUE_NO_TIENEN_LOS_DOS_LADOS(org_a):
    """Una orden sin reporte no puede contarse como «cuadra» ni como «no
    cuadra»: el cotejo automático la deja en `no_se_sabe` sin llamar a nadie,
    así que tampoco entra en el número que decide si encenderlo."""
    _orden(org_a, 9964)
    _orden(org_a, 9965, con_reporte=False)

    t = _correr(org_a)

    assert "Comparables (tienen los dos lados): 1" in t, t
    assert "Sin uno de los dos lados:           1" in t, t
