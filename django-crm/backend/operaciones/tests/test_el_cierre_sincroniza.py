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


# =============================================================================
#  §4  EL EFECTO, QUE ES LO UNICO QUE CUENTA
# =============================================================================
#
#  POR QUE ESTA SECCION EXISTE  --  14/10/2026, el mismo dia
#  ---------------------------------------------------------
#  Las tres secciones de arriba se escribieron primero, pasaron las ocho, se
#  desplegaron... y el sintoma siguio vivo: de 27 propuestas pendientes se
#  cerraron 3. Las otras 24 no se movieron.
#
#  La razon es que §1 a §3 afirman sobre 'informe["cerraria"]' y sobre
#  'senal.datos' -- el MECANISMO. El cierre de verdad lo decide otra cosa: el
#  NIVEL que la propuesta pide, que hasta ese momento subia unicamente con un
#  veredicto 'cierre_seguro'. Quitar la reja de 'evaluar_cierre_automatico' sin
#  tocar el nivel dejo las tres rejas que de verdad frenaban:
#
#      1. 'completar_propuesta_existente' subia el nivel solo con CIERRE_SEGURO
#      2. 'cerrar_si_corresponde' puerta 1 rechaza por nivel insuficiente
#      3. el ciclo no metia en ninguna cola a las ya diagnosticadas
#
#  Es textualmente la leccion de CLAUDE.md §6: "afirmar sobre el EFECTO, nunca
#  sobre la presencia del mecanismo". Ocho pruebas en verde con el sintoma
#  vivo, por tercera vez en este repositorio.
#
#  LO QUE ESTA SECCION MIRA: la columna 'status' del caso, releida de la base.

def _propuesta_ya_diagnosticada(org, caso, veredicto=dx.REVISAR_PERSONA):
    """
    Una propuesta como las 24 que se acumularon: diagnostico escrito, veredicto
    que NO habilita, y el nivel que nacio con ella.

    Las tres cosas juntas son lo que la dejaba fuera de las tres colas del
    ciclo: no le falta diagnostico, no hay nada que reintentar, y el nivel no
    alcanza para 'por_cerrar'.
    """
    from operaciones import supervisor

    senales = [s for s in supervisor.detectar(org)
               if s.origen_id == str(caso.id)
               and s.tipo == PropuestaSupervisor.CASO_DESINCRONIZADO]
    assert senales, "el detector no vio el caso: el andamio esta mal armado"
    p = supervisor.registrar_propuesta(org, senales[0],
                                       supervisor.analizar(senales[0]))
    p.evidencia = list(p.evidencia or []) + [{
        "fuente": "diagnostico", "origen_id": str(caso.id),
        "texto": "diagnostico del equipo: el equipo esta caido",
        "veredicto": veredicto, "en": timezone.now().isoformat()}]
    p.nivel_autonomia_requerido = PropuestaSupervisor.NIVEL_RECOMENDAR
    p.save(update_fields=["evidencia", "nivel_autonomia_requerido"])
    assert not dx.le_falta_diagnostico(p)
    assert not dx.hay_que_reintentar_diagnostico(p)
    return p


def _las_puertas_abiertas(org, monkeypatch, llamadas=None):
    """
    Delegacion y techo de autonomia, que NO son lo que estas pruebas miden --
    tienen sus propias guardas en §3 y en 'test_tareas_delegadas.py'.

    'llamadas' recoge lo que se le pidio al motor, que es LA UNICA salida al
    mundo de este camino.
    """
    from operaciones import autonomia, cierre_de_caso, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: True)
    #  LA CLAVE ES 'puede', NO 'autorizado'. La primera version de este
    #  andamio devolvia {"autorizado": True} y el cierre se rechazaba por
    #  "la empresa no lo autoriza" -- un falso negativo de la PRUEBA, que
    #  habria hecho buscar el error en el codigo.
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})

    def _falso_motor(propuesta_id, id_caso):
        if llamadas is not None:
            llamadas.append((propuesta_id, id_caso))
        return {"cerrado": True, "codigo": "CERRADO", "motivo": "",
                "referencia": f"propuesta:{propuesta_id}"}

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", _falso_motor)


#  POR QUE NO SE AFIRMA SOBRE 'caso.status'  --  y no es una concesion
#  ------------------------------------------------------------------
#  La primera version de esta seccion afirmaba 'caso.status == "Closed"' y
#  fallaba. No por el arreglo: 'cierre_de_caso.cerrar' NO escribe esa columna
#  --lo comprueba un grep: no hay un solo 'status =' en ese modulo-- porque el
#  cierre en Dexter lo ejecuta el MOTOR, por HTTP, y el motor es justo lo que
#  un test tiene que sustituir.
#
#  Con el motor falso, 'status' no puede cambiar nunca: afirmar sobre esa
#  columna mediria el andamio, no el sistema. El efecto real de este lado del
#  limite es QUE SE LE PIDIO AL MOTOR CERRAR ESE CASO -- una llamada saliente,
#  con el id del caso adentro-- y eso si distingue el arreglo de su ausencia:
#  antes del 14/10/2026 esa llamada no ocurria.
#
#  Lo que pasa del otro lado del limite tiene sus propias guardas, del lado
#  del motor. Esto no las reemplaza y no finge hacerlo.


def test_se_le_PIDE_al_motor_cerrar_aunque_el_equipo_no_lo_respalde(
        org_a, monkeypatch):
    """
    LA PRUEBA QUE FALTABA. Mira la llamada saliente, no un contador.
    """
    from operaciones import supervisor

    llamadas = []
    caso = _caso_cerrado_en_el_proveedor(org_a)
    p = _propuesta_ya_diagnosticada(org_a, caso)
    _las_puertas_abiertas(org_a, monkeypatch, llamadas)

    supervisor._atender_desincronizados(org_a, timezone.now(),
                                        desatendido=True)

    assert llamadas == [(str(p.id), str(caso.id))], (
        "no se le pidio al motor cerrar este caso. Es el sintoma de las 24 "
        f"propuestas que no se movian: {llamadas}")
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA, (
        f"la propuesta no quedo aceptada: {p.estado}")


def test_un_ticket_ELIMINADO_alla_tambien_se_cierra_solo(org_a, monkeypatch):
    """
    20/10/2026: el motor marca 'Eliminado' un ticket que el proveedor contesta
    con 404 dos veces, separadas por una hora. Ya no existe alla: el detector
    lo ve como cerrado alla y se le pide al motor cerrarlo, por el mismo
    camino y con las mismas compuertas que un 'Cerrado'. Hasta ese dia habia
    que cerrarlos a mano (95549 y 95778).
    """
    from operaciones import supervisor

    llamadas = []
    caso = _caso_cerrado_en_el_proveedor(org_a)
    caso.external_status = "Eliminado"
    caso.save(update_fields=["external_status"])
    p = _propuesta_ya_diagnosticada(org_a, caso)
    _las_puertas_abiertas(org_a, monkeypatch, llamadas)

    supervisor._atender_desincronizados(org_a, timezone.now(),
                                        desatendido=True)

    assert llamadas == [(str(p.id), str(caso.id))], llamadas


def test_y_el_ciclo_lo_CUENTA_entre_los_cerrados(org_a, monkeypatch):
    """
    Que el caso quede cerrado y el informe diga 'cerrados: 0' seria un cierre
    invisible: nadie podria medir si esto funciona.
    """
    from operaciones import supervisor

    caso = _caso_cerrado_en_el_proveedor(org_a)
    _propuesta_ya_diagnosticada(org_a, caso)
    _las_puertas_abiertas(org_a, monkeypatch)

    informe = supervisor._atender_desincronizados(org_a, timezone.now(),
                                                  desatendido=True)

    assert informe["cierre_automatico"]["cerrados"] == 1, informe
    assert informe["cierre_automatico"]["destrabadas_por_el_proveedor"] == 1


def test_si_el_proveedor_NO_lo_cerro_el_nivel_no_se_toca(org_a, monkeypatch):
    """
    El contrafactico, y es el que impide que esto sea "cerrar todo".

    Una propuesta ya diagnosticada cuyo ticket el proveedor tiene ABIERTO no
    sube de nivel y no se cierra -- aunque las dos puertas humanas esten
    abiertas. Lo que habilita el cierre es el estado del proveedor, no el paso
    del tiempo.
    """
    from operaciones import supervisor

    llamadas = []
    caso = _caso_cerrado_en_el_proveedor(org_a)
    p = _propuesta_ya_diagnosticada(org_a, caso)
    _las_puertas_abiertas(org_a, monkeypatch, llamadas)
    #  Se reabre DESPUES de que la propuesta existe: es el caso real de un
    #  ticket que el proveedor vuelve a abrir entre un ciclo y el siguiente.
    caso.external_status = "En Progreso"
    caso.save(update_fields=["external_status"])

    supervisor._atender_desincronizados(org_a, timezone.now(),
                                        desatendido=True)

    p.refresh_from_db()
    assert llamadas == [], (
        f"se le pidio al motor cerrar un caso que el proveedor reabrio: {llamadas}")
    assert p.nivel_autonomia_requerido == PropuestaSupervisor.NIVEL_RECOMENDAR, (
        "se le subio el nivel a una propuesta que el proveedor no respalda")
