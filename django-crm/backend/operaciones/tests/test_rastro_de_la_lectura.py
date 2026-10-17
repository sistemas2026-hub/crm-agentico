# -*- coding: utf-8 -*-
"""
================================================================================
 ¿EL SUPERVISOR MIDE EL EQUIPO, O SOLO LEE EL TEXTO DEL TICKET?
================================================================================

DE DONDE SALE, Y POR QUE ES UNA GUARDA Y NO UNA ANOTACION
---------------------------------------------------------
El 13/10/2026 nadie podia contestar esa pregunta, y es la pregunta central de
todo este bloque: una hipotesis que dice "-26.19 dBm" puede haberlo MEDIDO o
haberlo COPIADO de la descripcion --WispHub embebe un panel con la señal en el
cuerpo del reclamo-- y las dos frases se leen igual.

Se intento contestar con 'asistente.tool_calls' y dio "cero llamadas, nunca".
Era falso: ese registro no ve este camino. Se comprobo el mismo dia pidiendole
al Supervisor que midiera un equipo desde su chat --contesto con un valor
fresco, -26.02 dBm-- y la tabla siguio en cero.

O sea: se afirmo una conclusion fuerte con un instrumento que no recorria el
camino que pretendia medir. Esta guarda existe para que la proxima vez la
respuesta se mire en vez de deducirse.

LO QUE AFIRMA, Y LO QUE NO
--------------------------
Afirma que la lectura DEJA RASTRO de lo que pidio, y que ese rastro distingue
medir de citar. NO afirma que el modelo mida -- eso lo decide el modelo en cada
corrida, y es justamente lo que el rastro permite vigilar.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import diagnostico_de_ticket as dxt
from operaciones.models import PropuestaSupervisor
from operaciones.razonamiento_modelos import (FuenteRazonamiento,
                                              RazonamientoSupervisor)
from operaciones.supervisor import Senal

pytestmark = pytest.mark.django_db


# =============================================================================
#  §1  MEDIR NO ES CITAR
# =============================================================================

def test_una_lectura_que_consulto_el_equipo_cuenta_como_medicion():
    assert dxt.midio_el_equipo(["consultar_ticket", "diagnosticar_servicio"])


def test_una_lectura_que_solo_miro_papeles_NO_cuenta_como_medicion():
    #  Son las herramientas que el ciclo pide de verdad, copiadas de la corrida
    #  del 13/10/2026: ocho, y ninguna toca el equipo.
    assert not dxt.midio_el_equipo([
        "estado_fuentes", "listar_situaciones", "detalle_situacion",
        "tareas_disponibles", "mis_limites", "propuestas_pendientes",
        "tareas_activas", "decisiones_recientes"])


def test_sin_herramientas_no_es_una_medicion():
    assert not dxt.midio_el_equipo([])
    assert not dxt.midio_el_equipo(None)


def test_la_lista_de_lo_que_mide_es_BLANCA():
    """
    Una herramienta nueva NO cuenta como medicion hasta que alguien lo decida.

    Al reves --lista negra-- cualquier herramienta agregada despues inflaria el
    numero sin que nadie lo note, y el numero es justo lo que se va a mirar
    para decidir si esto puede seguir camino solo.
    """
    assert not dxt.midio_el_equipo(["una_herramienta_que_no_existia_ayer"])


# =============================================================================
#  §2  EL RASTRO QUEDA, Y DICE LO QUE PASO
# =============================================================================

class _Razonamiento:
    def __init__(self, herramientas):
        self.herramientas_usadas = list(herramientas)
        self.vueltas = 2
        self.agotado = False
        self.modelo = "un-modelo"
        self.proveedor = "un-proveedor"
        self.duracion_ms = 1234


class _Veredicto:
    """Lo minimo que 'razonamiento.registrar' mira de un veredicto."""

    def __init__(self, herramientas, hipotesis="Degradacion optica"):
        self.concluyente = True
        self.hechos = []
        self.inferencias = []
        self.riesgos = []
        self.riesgo = "informativo"
        self.hipotesis = hipotesis
        self.confianza = "media"
        self.recomendacion = ""
        self.falta = []
        self.descartes = []
        self.razonamiento = _Razonamiento(herramientas)


def _caso(org):
    from cases.models import Case

    return Case.objects.create(
        org=org, name="Internet intermitente", status="Assigned",
        priority="Normal", provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614",
        description="Reporta intermitencia del servicio, niveles altos.")


def _propuesta(org, caso):
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        accion_propuesta="Decidir que se hace", motivo="Sigue abierto.",
        evidencia=[{"fuente": "cases.Case", "id": str(caso.id),
                    "dato": "abierto",
                    "observado_en": timezone.now().isoformat()}],
        prioridad=40, impacto="Tiempo sin decision",
        huella_condicion="h-" + uuid.uuid4().hex[:8],
        expira_en=timezone.now() + timezone.timedelta(days=7))


def _senal(caso):
    return Senal(
        tipo=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id), evidencia=[],
        datos={"id_servicio": "3614", "ticket": "94721", "dias_abierto": 7,
               "sin_movimiento": True})


def _correr(org, caso, herramientas):
    """Diagnostica con un modelo falso que declara que herramientas uso."""
    p = _propuesta(org, caso)
    s = _senal(caso)
    informe = dxt.diagnosticar(
        org, [s], ahora=timezone.now(),
        concluir=lambda o, entrada: _Veredicto(herramientas),
        propuestas={str(caso.id): p})
    return informe, p


def test_queda_la_fila_y_dice_que_herramientas_se_pidieron(org_a):
    caso = _caso(org_a)
    informe, p = _correr(org_a, caso,
                         ["consultar_ticket", "diagnosticar_servicio"])

    filas = list(RazonamientoSupervisor.objects.filter(propuesta=p))
    assert len(filas) == 1, (
        "la lectura no dejo rastro: sin esta fila, 'mide o solo lee' hay que "
        "deducirlo, y el 13/10/2026 se dedujo mal")
    r = filas[0]
    assert r.fuente == FuenteRazonamiento.LECTURA_TICKET, (
        f"la lectura se mezcla con otra poblacion: fuente={r.fuente!r}")
    assert "diagnosticar_servicio" in r.herramientas


def test_el_informe_del_ciclo_dice_cuantas_midieron(org_a):
    informe, _ = _correr(org_a, _caso(org_a), ["diagnosticar_servicio"])
    assert informe["midieron"] == 1 and informe["sin_medir"] == 0


def test_una_lectura_sin_medicion_se_cuenta_aparte(org_a):
    #  El caso que importa: el modelo leyo, concluyo con una hipotesis que
    #  suena segura, y NO fue a buscar nada. Tiene que poder distinguirse.
    informe, p = _correr(org_a, _caso(org_a), ["consultar_ticket"])

    assert informe["sin_medir"] == 1 and informe["midieron"] == 0
    r = RazonamientoSupervisor.objects.filter(propuesta=p).first()
    assert r is not None, "una lectura sin medicion tambien deja rastro"
    assert not dxt.midio_el_equipo(r.herramientas)


def test_el_valor_de_la_fuente_entra_en_la_columna(org_a):
    """
    El campo es CharField(16). 'lectura_de_ticket' --el nombre natural-- entra
    en 17 y se habria truncado o rechazado lejos de aqui.
    """
    assert len(FuenteRazonamiento.LECTURA_TICKET) <= 16
    caso = _caso(org_a)
    _, p = _correr(org_a, caso, ["diagnosticar_servicio"])
    r = RazonamientoSupervisor.objects.filter(propuesta=p).first()
    assert r.fuente == "lectura_ticket"


def test_si_la_bitacora_falla_el_diagnostico_igual_queda(org_a):
    """
    Una bitacora que rompe el trabajo que registraba es peor que no tenerla.

    Se mide el EFECTO: la señal sale con su evidencia aunque no haya propuesta
    a la cual colgar la fila.
    """
    caso = _caso(org_a)
    s = _senal(caso)
    informe = dxt.diagnosticar(
        org_a, [s], ahora=timezone.now(),
        concluir=lambda o, entrada: _Veredicto(["diagnosticar_servicio"]),
        propuestas=None)          # <- sin propuestas: no hay donde registrar

    assert informe["leidos"] == 1
    assert informe["midieron"] == 1, "el contador vale aunque no haya fila"
    assert any(p.get("fuente") == dxt.FUENTE for p in s.evidencia), (
        "se perdio el diagnostico por no poder escribir la bitacora")
