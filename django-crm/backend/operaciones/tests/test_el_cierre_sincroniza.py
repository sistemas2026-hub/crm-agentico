# -*- coding: utf-8 -*-
"""
================================================================================
 CERRAR UN DESINCRONIZADO ES SINCRONIZAR, NO DECIDIR POR EL CLIENTE
================================================================================

LA DECISION, Y QUIEN LA TOMO
----------------------------
El 14/10/2026 el cliente la pidio con estas palabras: "si estan cerrados en
wisphub automaticamente se cierren en dexter sin validar y ya se acaba eso".

Hasta ese dia, un diagnostico del equipo que no dijera CIERRE_SEGURO frenaba el
cierre. La consecuencia, medida ese mismo dia sobre 25 casos acumulados:

    11  de clientes SIN ONU REGISTRADA en WispHub
     3  con el equipo caido y sin causa confirmada
     1  con problema de señal
    10  todavia sin diagnosticar

Los 11 primeros NUNCA iban a poder diagnosticarse --no hay equipo que medir--
asi que se acumulaban para siempre.

POR QUE LA DECISION SE SOSTIENE
-------------------------------
Cerrar en Dexter un caso que el proveedor YA cerro no es afirmar que el
problema del cliente se resolvio: es dejar de contradecir a quien ya decidio.
El estado del ticket lo manda WispHub; Dexter mostrandolo abierto solo ensucia
la cola de alguien.

LO QUE SIGUE SIENDO CODIGO ANTES DEL EFECTO
-------------------------------------------
    · que el proveedor lo reporte cerrado (dato externo, verificado)
    · que esa lectura tenga menos de 72 horas
    · que alguien haya delegado la tarea
    · el techo de autonomia
Y el cierre es SOLO en Dexter: no toca WispHub ni al cliente.

LO QUE NO SE PIERDE
-------------------
El diagnostico, cuando se pudo hacer, queda ESCRITO en el caso que se cierra.
Si el equipo estaba caido, eso se lee despues. Lo que cambia es que ya no
impide sincronizar.
================================================================================
"""

import pytest
from django.utils import timezone

from operaciones import diagnostico_optico as dx
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


class _Senal:
    """Una señal de desincronizado, con el veredicto que se quiera."""

    def __init__(self, caso_id, veredicto=None):
        self.tipo = PropuestaSupervisor.CASO_DESINCRONIZADO
        self.origen_tipo = "case"
        self.origen_id = str(caso_id)
        self.evidencia = []
        self.datos = {} if veredicto is None else {
            "diagnostico_veredicto": veredicto}


def _caso_cerrado_en_el_proveedor(org):
    import uuid

    from cases.models import Case

    ahora = timezone.now()
    return Case.objects.create(
        org=org, name="Sin internet", status="New", priority="Normal",
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Cerrado",
        external_status_at=ahora, external_fetched_at=ahora,
        description="Reclamo.")


def _evaluar(org, senal):
    return dx.evaluar_cierre_automatico(org, [senal], ahora=timezone.now())


# =============================================================================
#  §1  EL DIAGNOSTICO YA NO BLOQUEA
# =============================================================================

def test_sin_ONU_registrada_igual_se_sincroniza(org_a):
    """
    Los once que se acumulaban. No tienen equipo que medir, asi que ningun
    diagnostico los iba a habilitar nunca.
    """
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id, "sin_equipo_registrado")

    informe = _evaluar(org_a, s)

    assert informe["cerraria"] == 1, (
        f"sigue sin cerrarse por el diagnostico: {s.datos.get('cierre_automatico_porque')}")
    assert s.datos["cierre_automatico"] == "cerraria"


def test_con_el_equipo_caido_tambien(org_a):
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id, "equipo_caido")

    assert _evaluar(org_a, s)["cerraria"] == 1


def test_y_sin_ningun_diagnostico_tambien(org_a):
    #  Los diez que estaban sin mirar: el proveedor ya cerro, eso alcanza.
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id)

    assert _evaluar(org_a, s)["cerraria"] == 1


# =============================================================================
#  §2  PERO QUEDA ESCRITO QUE EL EQUIPO NO LO RESPALDABA
# =============================================================================

def test_un_cierre_sin_respaldo_lo_dice(org_a):
    """
    Sincronizar un estado no es afirmar que el cliente esta bien, y esa
    diferencia tiene que poder leerse despues -- sobre todo en el caso donde
    el equipo estaba caido.
    """
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id, "equipo_caido")

    informe = _evaluar(org_a, s)

    porque = s.datos["cierre_automatico_porque"]
    assert "OJO" in porque and "equipo_caido" in porque, (
        f"se cerro sin dejar constancia de que el equipo no lo respaldaba: "
        f"{porque}")
    assert informe.get("cerrados_sin_respaldo") == 1


def test_un_cierre_sin_medicion_tambien_lo_dice(org_a):
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id)

    informe = _evaluar(org_a, s)

    assert "no se pudo medir" in s.datos["cierre_automatico_porque"]
    assert informe.get("cerrados_sin_medir") == 1


def test_cuando_el_equipo_SI_respalda_no_se_pone_la_advertencia(org_a):
    caso = _caso_cerrado_en_el_proveedor(org_a)
    s = _Senal(caso.id, dx.CIERRE_SEGURO)

    informe = _evaluar(org_a, s)

    assert "OJO" not in s.datos["cierre_automatico_porque"]
    assert "lo respalda" in s.datos["cierre_automatico_porque"]
    assert not informe.get("cerrados_sin_respaldo")


# =============================================================================
#  §3  LO QUE SIGUE FRENANDO
# =============================================================================

def test_un_caso_que_ya_no_existe_no_se_cierra(org_a):
    import uuid

    s = _Senal(uuid.uuid4())
    informe = _evaluar(org_a, s)

    assert informe["cerraria"] == 0
    assert "ya no existe" in s.datos["cierre_automatico_porque"]


def test_las_condiciones_del_caso_siguen_mandando(org_a):
    """
    El proveedor NO lo cerro: entonces no hay nada que sincronizar, y el cierre
    no sale aunque el diagnostico fuera perfecto.
    """
    caso = _caso_cerrado_en_el_proveedor(org_a)
    caso.external_status = "En Progreso"
    caso.save(update_fields=["external_status"])
    s = _Senal(caso.id, dx.CIERRE_SEGURO)

    informe = _evaluar(org_a, s)

    assert informe["cerraria"] == 0, (
        "se cerro un caso que el proveedor NO tiene cerrado: eso ya no es "
        "sincronizar, es decidir")
