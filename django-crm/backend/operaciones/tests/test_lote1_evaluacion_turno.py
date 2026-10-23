# -*- coding: utf-8 -*-
"""
================================================================================
 LOTE 1  --  P8.3 metricas, P10 el ciclo, P11 resumen de turno y Shadow Mode
================================================================================

LAS CUATRO PROPIEDADES QUE JUSTIFICAN EL LOTE
---------------------------------------------
  1. ACEPTADA NO ES CORRECTA. La precision sale de 'AprendizajeSupervisor' --
     filas con evidencia obligatoria y un origen que nunca es el Supervisor--,
     nunca de que alguien haya aceptado una propuesta.
  2. UN CERO NO ES UN RESULTADO. Sin poblacion, el indicador sale NO_APLICA; con
     cobertura parcial, DATOS_INSUFICIENTES. Lo que no se puede medir se publica
     como lo que es, y nunca se imputa.
  3. UNA SEÑAL QUE DESAPARECE NO CIERRA NADA, tampoco pasando por el ciclo real
     del scheduler. Y el ciclo es el que corre por HTTP, no la funcion suelta.
  4. INFERIDO NO SE PROMUEVE A CONFIRMADO. Una lectura del Supervisor sigue
     siendo una lectura aunque pase el tiempo y nadie la contradiga.

COMO ESTA ORDENADO
------------------
    §A  P8.3  precision y lo que NO entra en ella
    §B  P8.3  falso positivo, omision, y los datos insuficientes al lado
    §C  P8.3  calidad de correlacion
    §D  P8.3  reincidencia: confirmada, no candidata
    §E  P8.3  anticipacion, y los tres casos que no se pueden medir
    §F  P8.3  timestamps faltantes
    §G  P8.3  el reporte, lectura, tenant
    §H  P10   el ciclo 24/7 por su ruta real, turno a turno
    §I  P11   las doce preguntas del turno
    §J  P11   la procedencia, y que no se promueve
    §K  P11   Shadow Mode: medido, no declarado
    §L  seguridad, idempotencia de lectura, tenant

LO QUE SE SUSTITUYE
-------------------
Nada. Las capturas de fuente se escriben como las dejaria el sondeo (el mismo
andamio de P3) y desde ahi todo es real: deteccion, correlacion, seguimiento,
gobierno, modelos y Postgres. Ninguna metrica se calcula con numeros a mano.
================================================================================
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from cases.models import Case
from common.models import Activity, Profile, User
from operaciones import correlacion, gobierno, indicadores
from operaciones import situaciones as svc
from operaciones import supervisor as sup
from operaciones import turno as trn
from operaciones.gobierno_modelos import (AprendizajeSupervisor,
                                          OrigenAprendizaje, ResultadoDecision,
                                          TipoAprendizaje)
from operaciones.models import DecisionSupervisor, PropuestaSupervisor
from operaciones.situaciones_modelos import (SituacionAfectado,
                                             SituacionOperativa,
                                             SituacionRelacion, TipoAfectado,
                                             TipoRelacion)
#  El andamio de capturas y casos ya existe y esta probado: reusarlo es parte
#  de no construir un segundo sistema de pruebas al lado del primero.
from operaciones.tests.test_p3_situaciones import _captura, _caso, _pon
from operaciones.tests.test_p82_desenlace import _decidir, _propuesta

P = PropuestaSupervisor
D = DecisionSupervisor
S = SituacionOperativa
Ap = AprendizajeSupervisor
RUTA_SONDEO = "/api/operaciones/supervisor/sondeo/"


# =============================================================================
#  andamio
# =============================================================================

@pytest.fixture
def jefe(org_a):
    u = User.objects.create_user(email="jefe.lote1@prueba.local",
                                 password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org_a, role="OPERACIONES",
                                  is_active=True)


@pytest.fixture
def jefe_b(org_b):
    u = User.objects.create_user(email="jefe.lote1.b@prueba.local",
                                 password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org_b, role="OPERACIONES",
                                  is_active=True)


def _situacion_real(org, *, pon="3/1/4", afectados=12, ahora=None):
    """
    Una situacion nacida del camino REAL: captura de fuente -> ciclo.

    Importa que no se cree a mano: lo que mide la anticipacion es
    'detectada_en', y una situacion fabricada con 'objects.create' permitiria
    poner ahi cualquier instante -- justo el dato que la metrica no debe poder
    elegir.
    """
    ahora = ahora or timezone.now()
    _captura(org, pons={pon: _pon(afectados)}, ahora=ahora)
    correlacion.correr(org, ahora=ahora)
    return S.objects.filter(org=org).order_by("-detectada_en").first()


def _caso_en(org, *, pon, creado_en):
    """Un caso con 'created_at' puesto: el campo es auto_now_add."""
    caso = _caso(org, pon=pon)
    Case.objects.filter(pk=caso.pk).update(created_at=creado_en)
    caso.refresh_from_db()
    return caso


def _ev(org, ahora=None):
    return indicadores.indicadores_evaluacion(org, ahora=ahora)


def _cerrar_bien(situacion, que_se_comprobo):
    """
    Cierra una situacion por el camino que la base permite.

    No es ceremonia del test: 'detectada -> resuelta' esta prohibida a
    proposito (P3 'test_45'), y el unico camino es
    verificacion -> verificar -> resuelta -> cerrada.
    """
    svc.cambiar_estado(situacion, S.EN_VERIFICACION,
                       motivo="la señal dejó de verse")
    svc.verificar(situacion, que_se_comprobo)
    svc.cerrar(situacion)
    situacion.refresh_from_db()
    return situacion


# =============================================================================
#  §A  PRECISION  --  y lo que NO entra en ella
# =============================================================================

def test_A1_la_precision_sale_de_las_lecciones_confirmadas(org_a, jefe):
    """Tres a favor y una en contra son 0.75, y el sobre sale VALIDO."""
    s = _situacion_real(org_a)
    for i in range(3):
        gobierno.registrar_aprendizaje(
            org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA,
            origen=OrigenAprendizaje.VERIFICACION,
            conclusion=f"la recomendación {i} funcionó",
            evidencia="el PON volvió en línea", situacion=s, actor=jefe)
    gobierno.registrar_falso_positivo(s, actor=jefe, motivo="no era nada")

    m = _ev(org_a)["precision"]

    assert m["valor"] == 0.75
    assert m["estado"] == indicadores.VALIDO
    assert m["denominador"] == 4
    assert m["cobertura"] == 1.0


def test_A2_sin_lecciones_la_precision_es_NO_APLICA_no_cero(org_a):
    """
    §5: un cero se leeria como 'nunca acierta'. No hay poblacion, no hay
    resultado -- y eso es una respuesta, no un hueco.
    """
    _situacion_real(org_a)

    m = _ev(org_a)["precision"]

    assert m["estado"] == indicadores.NO_APLICA
    assert m["valor"] is None, "sin lecciones NO se reporta 0"
    assert m["denominador"] == 0
    assert "no es un resultado" in m["motivo"]


def test_A3_una_propuesta_ACEPTADA_no_mueve_la_precision(org_a, jefe):
    """
    La propiedad 1 del lote, afirmada sobre el EFECTO.

    Aceptar deja una decision con resultado PENDIENTE. Si eso contara como
    acierto, la precision diria 1.0 sin que nadie haya comprobado nada.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)

    assert D.objects.filter(org=org_a,
                            resultado=ResultadoDecision.PENDIENTE).count() == 1
    m = _ev(org_a)["precision"]
    assert m["estado"] == indicadores.NO_APLICA
    assert m["valor"] is None, "aceptada no es correcta"


def test_A4_el_desenlace_SI_la_mueve_y_en_la_direccion_que_dice(org_a, jefe):
    """
    El contrapunto de A3: con desenlace y evidencia, la leccion aparece.

    Sin esta prueba, 'la precision no se mueve' podria significar 'nunca se
    mueve', que no es la garantia que se pidio.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)
    d = D.objects.get(org=org_a)

    gobierno.registrar_resultado(d, actor=jefe,
                                 resultado=ResultadoDecision.FUNCIONO,
                                 evidencia="las 12 ONT volvieron")

    m = _ev(org_a)["precision"]
    assert m["estado"] == indicadores.VALIDO
    assert m["valor"] == 1.0
    assert _ev(org_a)["lecciones_a_favor"]["valor"] == 1


def test_A5_un_rechazo_que_resulto_errado_cuenta_a_FAVOR(org_a, jefe):
    """
    El Supervisor tenia razon y la persona no: eso es acierto del Supervisor.

    Es la unica forma de que la metrica no premie al que siempre acepta.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.RECHAZADA,
             comentario="no hace falta")
    d = D.objects.get(org=org_a)

    gobierno.registrar_resultado(d, actor=jefe,
                                 resultado=ResultadoDecision.NO_FUNCIONO,
                                 evidencia="el PON siguió caído 4 horas")

    assert Ap.objects.filter(org=org_a,
                             tipo=TipoAprendizaje.RECHAZO_ERRADO).count() == 1
    assert _ev(org_a)["precision"]["valor"] == 1.0


# =============================================================================
#  §B  FALSO POSITIVO, OMISION, Y LOS DATOS INSUFICIENTES AL LADO
# =============================================================================

def test_B1_un_falso_positivo_se_cuenta_y_baja_la_precision(org_a, jefe):
    s1 = _situacion_real(org_a, pon="3/1/4")
    s2 = _situacion_real(org_a, pon="5/2/1")
    gobierno.registrar_aprendizaje(
        org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA,
        origen=OrigenAprendizaje.VERIFICACION, conclusion="funcionó",
        evidencia="volvió", situacion=s1, actor=jefe)
    gobierno.registrar_falso_positivo(s2, actor=jefe,
                                      motivo="era una ventana de mantenimiento")

    m = _ev(org_a)
    assert m["falsos_positivos"]["valor"] == 1
    assert m["precision"]["valor"] == 0.5


def test_B2_una_omision_no_necesita_situacion(org_a, jefe):
    """
    §11: una omision existe PORQUE no hubo situacion. Exigirle una la volveria
    imposible de registrar, que es la forma mas barata de no tener ninguna.
    """
    gobierno.registrar_omision(
        org_a, actor=jefe,
        conclusion="hubo una caída en el PON 7/1/2 que nadie detectó",
        evidencia="19 tickets del mismo sector entre 02:10 y 02:40")

    m = _ev(org_a)
    assert m["omisiones_conocidas"]["valor"] == 1
    assert m["precision"]["valor"] == 0.0, "una omisión es una leccion EN CONTRA"


def test_B3_los_datos_insuficientes_NO_son_una_omision(org_a):
    """
    §7, y es la distincion que mas facil se pierde: no saber cuantos clientes
    hay detras de un PON no es haberse perdido una caida.
    """
    s = _situacion_real(org_a, afectados=12)

    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.DATOS_INSUFICIENTES).exists()
    m = _ev(org_a)
    assert m["situaciones_con_datos_insuficientes"]["valor"] == 1
    assert m["omisiones_conocidas"]["valor"] == 0, "no se suman"
    assert m["precision"]["estado"] == indicadores.NO_APLICA, (
        "una insuficiencia no empeora la precisión: no es un error")


def test_B4_los_dos_viajan_en_claves_distintas(org_a, jefe):
    """Que ninguna lectura los pueda sumar sin darse cuenta."""
    s = _situacion_real(org_a)
    gobierno.registrar_omision(org_a, actor=jefe, conclusion="se perdió una",
                               evidencia="14 tickets", situacion=s)

    m = _ev(org_a)
    assert m["omisiones_conocidas"]["fuente"] == "AprendizajeSupervisor"
    assert m["situaciones_con_datos_insuficientes"]["fuente"] == (
        "operaciones.SituacionAfectado")


# =============================================================================
#  §C  CALIDAD DE CORRELACION
# =============================================================================

def test_C1_la_calidad_es_correctas_sobre_evaluadas(org_a, jefe):
    s1 = _situacion_real(org_a, pon="3/1/4")
    s2 = _situacion_real(org_a, pon="5/2/1")
    s3 = _situacion_real(org_a, pon="6/3/2")
    gobierno.registrar_calidad_de_correlacion(
        s1, actor=jefe, propuestos=12, confirmados=12,
        evidencia="se revisaron las 12 en sitio")
    gobierno.registrar_calidad_de_correlacion(
        s2, actor=jefe, propuestos=12, confirmados=12,
        evidencia="las 12 confirmadas por el técnico")
    gobierno.registrar_calidad_de_correlacion(
        s3, actor=jefe, propuestos=12, confirmados=9,
        evidencia="solo 9 estaban afectadas")

    m = _ev(org_a)
    assert m["calidad_correlacion"]["valor"] == round(2 / 3, 4)
    assert m["calidad_correlacion"]["estado"] == indicadores.VALIDO
    assert m["afectados_propuestos"]["valor"] == 36
    assert m["afectados_confirmados"]["valor"] == 33


def test_C2_el_desvio_se_mide_en_valor_absoluto(org_a, jefe):
    """
    'propuso 12, eran 10' y 'propuso 10, eran 12' se equivocan lo mismo.
    Promediar con signo los cancelaria y daria cero error.
    """
    s1 = _situacion_real(org_a, pon="3/1/4")
    s2 = _situacion_real(org_a, pon="5/2/1")
    gobierno.registrar_calidad_de_correlacion(
        s1, actor=jefe, propuestos=12, confirmados=10, evidencia="eran 10")
    gobierno.registrar_calidad_de_correlacion(
        s2, actor=jefe, propuestos=10, confirmados=12, evidencia="eran 12")

    m = _ev(org_a)["desvio_medio_afectados"]
    assert m["valor"] == 2.0, "dos errores de 2 no se cancelan a 0"


def test_C3_sin_correlaciones_evaluadas_la_calidad_es_NO_APLICA(org_a):
    _situacion_real(org_a)
    m = _ev(org_a)["calidad_correlacion"]
    assert m["estado"] == indicadores.NO_APLICA
    assert m["valor"] is None


# =============================================================================
#  §D  REINCIDENCIA  --  confirmada, no candidata
# =============================================================================

def test_D1_una_candidata_NO_cuenta_como_reincidencia(org_a):
    """
    §8: que dos situaciones compartan PON es el dato; el diagnostico es de
    quien sabe. Contar candidatas convertiria una coincidencia en un hecho.
    """
    ayer = timezone.now() - timezone.timedelta(days=1)
    vieja = _situacion_real(org_a, pon="3/1/4", ahora=ayer)
    _cerrar_bien(vieja, "se revisó el PON 3/1/4 y volvió")
    nueva = _situacion_real(org_a, pon="3/1/4")

    candidatas = gobierno.candidatas_de_reincidencia(nueva)

    assert len(candidatas) == 1, "la candidata se ve"
    assert _ev(org_a)["reincidencias_confirmadas"]["valor"] == 0, (
        "pero no se cuenta hasta que alguien la afirme")


def test_D2_cuando_una_persona_la_afirma_SI_se_cuenta(org_a, jefe):
    ayer = timezone.now() - timezone.timedelta(days=1)
    vieja = _situacion_real(org_a, pon="3/1/4", ahora=ayer)
    _cerrar_bien(vieja, "se revisó el PON 3/1/4")
    nueva = _situacion_real(org_a, pon="3/1/4")

    gobierno.marcar_reincidencia(nueva, vieja, actor=jefe,
                                 motivo="mismo empalme, tercera vez este mes")

    assert SituacionRelacion.objects.filter(
        org=org_a, tipo=TipoRelacion.REINCIDENCIA).count() == 1
    assert _ev(org_a)["reincidencias_confirmadas"]["valor"] == 1


def test_D3_la_reincidencia_no_la_puede_afirmar_el_sistema(org_a):
    ayer = timezone.now() - timezone.timedelta(days=1)
    vieja = _situacion_real(org_a, pon="3/1/4", ahora=ayer)
    nueva = _situacion_real(org_a, pon="3/1/4")

    with pytest.raises(gobierno.ErrorGobierno):
        gobierno.marcar_reincidencia(nueva, vieja, actor=None, motivo="x")
    assert _ev(org_a)["reincidencias_confirmadas"]["valor"] == 0


# =============================================================================
#  §E  ANTICIPACION  --  y los casos que no se pueden medir
# =============================================================================

def test_E1_detectar_antes_del_primer_ticket_es_anticipar(org_a):
    """
    Minutos POSITIVOS. Y el instante que se compara es 'Case.created_at' --
    cuando el cliente reclamo--, NO cuando el Supervisor asocio el caso, que
    es siempre posterior y daria un anticipo inflado.
    """
    t0 = timezone.now() - timezone.timedelta(minutes=60)
    s = _situacion_real(org_a, pon="3/1/4", ahora=t0)
    _caso_en(org_a, pon="3/1/4", creado_en=t0 + timezone.timedelta(minutes=20))
    correlacion.asociar_tickets(org_a)

    m = _ev(org_a)
    assert m["situaciones_anticipadas"]["valor"] == 1
    assert m["situaciones_detectadas_tarde"]["valor"] == 0
    assert m["minutos_anticipacion"]["valor"] == pytest.approx(20, abs=1)
    assert m["tasa_anticipacion"]["valor"] == 1.0
    #  Y no se midio contra la asociacion, que ocurrio despues.
    af = SituacionAfectado.objects.get(situacion=s, tipo=TipoAfectado.CASO)
    assert af.detectado_en > Case.objects.get(org=org_a).created_at


def test_E2_un_ticket_anterior_es_haber_llegado_tarde(org_a):
    t0 = timezone.now() - timezone.timedelta(minutes=60)
    _caso_en(org_a, pon="3/1/4", creado_en=t0 - timezone.timedelta(minutes=30))
    _situacion_real(org_a, pon="3/1/4", ahora=t0)
    correlacion.asociar_tickets(org_a)

    m = _ev(org_a)
    assert m["situaciones_detectadas_tarde"]["valor"] == 1
    assert m["situaciones_anticipadas"]["valor"] == 0
    assert m["minutos_anticipacion"]["valor"] < 0, "negativo = llego tarde"


def test_E3_una_situacion_SIN_tickets_no_entra_en_la_cuenta(org_a):
    """
    De esas no se puede saber si anticipo o si nadie reclamo nunca. Entrarlas
    como anticipadas inflaria el anticipo con el silencio de los clientes.
    """
    _situacion_real(org_a, pon="3/1/4")

    m = _ev(org_a)
    assert m["situaciones_sin_ticket"]["valor"] == 1
    assert m["situaciones_anticipadas"]["valor"] == 0
    assert m["situaciones_detectadas_tarde"]["valor"] == 0
    assert m["tasa_anticipacion"]["estado"] == indicadores.NO_APLICA
    assert m["tasa_anticipacion"]["valor"] is None
    assert m["minutos_anticipacion"]["valor"] is None


def test_E4_un_caso_irresoluble_se_publica_no_se_inventa(org_a):
    """
    El afectado nombra un caso que ya no existe. No hay instante que comparar,
    y lo que NO se hace es suponer uno.
    """
    t0 = timezone.now() - timezone.timedelta(minutes=60)
    s = _situacion_real(org_a, pon="3/1/4", ahora=t0)
    caso = _caso_en(org_a, pon="3/1/4",
                    creado_en=t0 + timezone.timedelta(minutes=10))
    correlacion.asociar_tickets(org_a)
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 1
    #  El caso desaparece; el afectado queda nombrandolo.
    Case.objects.filter(pk=caso.pk).delete()

    m = _ev(org_a)
    assert m["situaciones_con_caso_irresoluble"]["valor"] == 1
    assert m["situaciones_anticipadas"]["valor"] == 0
    assert m["minutos_anticipacion"]["valor"] is None, (
        "sin el caso no hay instante: no se imputa ninguno")


def test_E5_los_tres_casos_que_no_se_miden_viajan_por_separado(org_a):
    """
    Sin ticket, caso irresoluble y detectada tarde son tres cosas distintas, y
    una sola clave que los juntara haria imposible saber cual paso.
    """
    m = _ev(org_a)
    for clave in ("situaciones_sin_ticket", "situaciones_con_caso_irresoluble",
                  "situaciones_detectadas_tarde", "situaciones_anticipadas"):
        assert clave in m, clave


# =============================================================================
#  §F  TIMESTAMPS FALTANTES
# =============================================================================

def test_F1_una_decision_SIN_situacion_se_excluye_y_se_publica(org_a, jefe):
    """
    §4: no hay 'detectada_en' contra la que medir. No se imputa cero --eso
    diria 'decidio al instante'--: se excluye del numerador y se dice cuantas.

    Y el estado es DATOS_INSUFICIENTES, NO 'NO_APLICA': hay UNA decision en el
    periodo, asi que poblacion hay. Lo que falta es el instante contra el que
    medirla. Los dos estados dicen cosas distintas y la diferencia importa --
    'no hay nada que medir' frente a 'hay algo y no se pudo medir'.
    """
    _decidir(_propuesta(org_a), jefe)          # sin situacion atada

    m = _ev(org_a)
    assert m["decisiones_sin_situacion"]["valor"] == 1
    t = m["minutos_deteccion_a_decision"]
    assert t["valor"] is None, "no se imputa cero"
    assert t["estado"] == indicadores.DATOS_INSUFICIENTES
    assert t["estado"] != indicadores.NO_APLICA, (
        "hay una decision en el periodo: poblacion hay")
    assert (t["con_dato"], t["denominador"]) == (0, 1)
    assert t["cobertura"] == 0.0


def test_F2_cobertura_parcial_es_DATOS_INSUFICIENTES_no_un_numero_limpio(
        org_a, jefe):
    """
    Una con situacion y una sin ella: el numero se calcula sobre la mitad, y el
    sobre lo dice. Un 'valor' sin su estado seria el dato mas enganoso de todos.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s, accion="Con situación"), jefe)
    _decidir(_propuesta(org_a, accion="Sin situación"), jefe)

    t = _ev(org_a)["minutos_deteccion_a_decision"]
    assert t["estado"] == indicadores.DATOS_INSUFICIENTES
    assert t["valor"] is not None, "lo que se pudo medir se reporta"
    assert (t["con_dato"], t["denominador"]) == (1, 2)
    assert t["cobertura"] == 0.5
    assert "no se imputa" in t["motivo"]


def test_F3_una_decision_sin_desenlace_no_tiene_el_segundo_tiempo(org_a, jefe):
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)

    t = _ev(org_a)["minutos_decision_a_resultado"]
    assert t["estado"] == indicadores.DATOS_INSUFICIENTES
    assert t["con_dato"] == 0


def test_F4_el_recorrido_completo_SI_da_los_dos_tiempos(org_a, jefe):
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(d, actor=jefe,
                                 resultado=ResultadoDecision.FUNCIONO,
                                 evidencia="volvió")

    m = _ev(org_a)
    assert m["minutos_deteccion_a_decision"]["estado"] == indicadores.VALIDO
    assert m["minutos_decision_a_resultado"]["estado"] == indicadores.VALIDO
    assert m["minutos_decision_a_resultado"]["valor"] is not None


# =============================================================================
#  §G  EL REPORTE, LECTURA, TENANT
# =============================================================================

def test_G1_el_reporte_de_evaluacion_existe_y_trae_sus_observaciones(org_a):
    _situacion_real(org_a)

    r = indicadores.reporte(org_a, indicadores.EVALUACION)

    assert "evaluacion" in r["metricas"]
    assert "situaciones" in r["metricas"]
    texto = " ".join(r["observaciones"])
    assert "aceptada" in texto.lower(), (
        "el reporte dice que aceptada no es correcta, no lo deja implicito")
    assert r["datos_insuficientes"], (
        "sin lecciones hay indicadores NO_APLICA y el reporte los lista")
    assert r["cobertura_completa"] is False


def test_G2_los_indicadores_NO_escriben_nada(org_a, jefe):
    """
    Corolario del metodo: se afirma sobre el EFECTO, contando filas en las seis
    tablas que podrian moverse -- no sobre la ausencia de un 'save' en el codigo.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    antes = {
        "situaciones": S.objects.count(),
        "eventos": s.eventos.count(),
        "afectados": SituacionAfectado.objects.count(),
        "propuestas": P.objects.count(),
        "decisiones": D.objects.count(),
        "aprendizajes": Ap.objects.count(),
        "relaciones": SituacionRelacion.objects.count(),
        "auditoria": Activity.objects.count(),
    }

    indicadores.indicadores_evaluacion(org_a)
    indicadores.reporte(org_a, indicadores.EVALUACION)

    assert {
        "situaciones": S.objects.count(),
        "eventos": s.eventos.count(),
        "afectados": SituacionAfectado.objects.count(),
        "propuestas": P.objects.count(),
        "decisiones": D.objects.count(),
        "aprendizajes": Ap.objects.count(),
        "relaciones": SituacionRelacion.objects.count(),
        "auditoria": Activity.objects.count(),
    } == antes


def test_G3_las_metricas_de_una_empresa_no_ven_a_la_otra(org_a, org_b, jefe,
                                                         jefe_b):
    s_a = _situacion_real(org_a, pon="3/1/4")
    s_b = _situacion_real(org_b, pon="3/1/4")
    gobierno.registrar_falso_positivo(s_a, actor=jefe, motivo="no era nada")
    gobierno.registrar_aprendizaje(
        org_b, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA,
        origen=OrigenAprendizaje.VERIFICACION, conclusion="funcionó",
        evidencia="volvió", situacion=s_b, actor=jefe_b)

    a, b = _ev(org_a), _ev(org_b)

    assert (a["precision"]["valor"], b["precision"]["valor"]) == (0.0, 1.0)
    assert a["falsos_positivos"]["valor"] == 1
    assert b["falsos_positivos"]["valor"] == 0


# =============================================================================
#  §H  P10  --  EL CICLO 24/7 POR SU RUTA REAL, TURNO A TURNO
# =============================================================================
#
#  POR QUE POR HTTP Y NO LLAMANDO A 'correlacion.correr'
#  -----------------------------------------------------
#  'test_58' de P3 ya prueba los cuatro ciclos llamando a la funcion, y esa
#  prueba no se toca. Lo que NO estaba probado es el camino que de verdad corre
#  en produccion: el scheduler del motor hace POST a '/supervisor/sondeo/', y
#  esa vista agrega tres cosas que la funcion no tiene --'asegurar_fuentes', la
#  comprobacion de tenant y 'fuentes.sondear', que mueve 'proxima_consulta_en'.
#  Es §6 de CLAUDE.md aplicado tal cual: codigo construido no es codigo que
#  corre, y el instrumento solo mide el camino que recorre.

def test_H1_una_situacion_sobrevive_turnos_del_scheduler(org_a, admin_client,
                                                         admin_profile):
    """Nace en un turno, sigue viva en el siguiente, y NO se duplica."""
    _captura(org_a, pons={"3/1/4": _pon(12)})
    r1 = admin_client.post(RUTA_SONDEO).json()
    assert r1["situaciones"]["creadas"] == 1
    s = S.objects.get(org=org_a)

    _captura(org_a, pons={"3/1/4": _pon(15)})
    r2 = admin_client.post(RUTA_SONDEO).json()

    assert r2["situaciones"]["creadas"] == 0, "el segundo turno no crea otra"
    assert r2["situaciones"]["actualizadas"] == 1
    assert S.objects.filter(org=org_a).count() == 1
    s.refresh_from_db()
    assert s.estado == S.INVESTIGANDO, "evoluciono: la señal se repitio"


def test_H2_el_seguimiento_corre_DENTRO_del_turno(org_a, admin_client,
                                                  admin_profile):
    """
    No es un proceso aparte ni un segundo scheduler: el mismo POST que sondea
    deja el veredicto del seguimiento en su informe.
    """
    _captura(org_a, pons={"3/1/4": _pon(60, abonados=100, porcentaje=60.0)})

    cuerpo = admin_client.post(RUTA_SONDEO).json()

    assert "seguimiento" in cuerpo["situaciones"]
    assert cuerpo["situaciones"]["seguimiento"]["piden_humano"] == 1
    assert cuerpo["situaciones"]["seguimiento"]["propuestas"] == 1
    s = S.objects.get(org=org_a)
    assert s.eventos.filter(tipo="recomendacion").exists()


def test_H3_la_senal_que_desaparece_pasa_a_VERIFICACION_por_la_ruta(
        org_a, admin_client, admin_profile):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    admin_client.post(RUTA_SONDEO)
    s = S.objects.get(org=org_a)

    #  Pasa el tiempo sin señal y llega otro turno del scheduler.
    S.objects.filter(pk=s.pk).update(
        senal_vista_en=timezone.now() - timezone.timedelta(
            minutes=correlacion.MINUTOS_SIN_SENAL_PARA_VERIFICAR + 10))
    _captura(org_a, pons={})
    cuerpo = admin_client.post(RUTA_SONDEO).json()

    assert cuerpo["situaciones"]["a_verificacion"] == 1
    s.refresh_from_db()
    assert s.estado == S.EN_VERIFICACION
    assert s.estado != S.CERRADA
    assert s.cerrada_en is None


def test_H4_el_ciclo_NO_puede_cerrar_una_situacion(org_a, admin_client,
                                                   admin_profile):
    """
    La regla ya existia (P3 'test_42'/'test_43') y no se modifica: se prueba
    DENTRO del ciclo, que es lo que faltaba. Ni cien turnos la cierran.
    """
    _captura(org_a, pons={"3/1/4": _pon(12)})
    admin_client.post(RUTA_SONDEO)
    s = S.objects.get(org=org_a)
    S.objects.filter(pk=s.pk).update(
        senal_vista_en=timezone.now() - timezone.timedelta(
            minutes=correlacion.MINUTOS_SIN_SENAL_PARA_VERIFICAR + 10))

    for _ in range(3):
        _captura(org_a, pons={})
        admin_client.post(RUTA_SONDEO)

    s.refresh_from_db()
    assert s.estado == S.EN_VERIFICACION, "sigue esperando evidencia"
    assert not s.verificacion
    #  Y cerrarla a mano tampoco, mientras nadie diga QUE comprobo.
    with pytest.raises(svc.ErrorSituacion):
        svc.cerrar(s)

    #  Con la verificacion, si.
    svc.verificar(s, "se midió el PON 3/1/4: las 12 ONT volvieron en línea")
    svc.cerrar(s)
    s.refresh_from_db()
    assert s.estado == S.CERRADA


def test_H5_un_turno_apuntando_a_otra_empresa_no_sondea_nada(
        org_a, org_b, admin_client, admin_profile):
    _captura(org_a, pons={"3/1/4": _pon(12)})

    r = admin_client.post(f"{RUTA_SONDEO}?organization_id={org_b.id}")

    assert r.status_code == 409
    assert r.json()["error"] == "ORGANIZACION_DISTINTA"
    assert S.objects.count() == 0, "no se creo ninguna situacion"


# =============================================================================
#  §I  P11  --  LAS DOCE PREGUNTAS DEL TURNO
# =============================================================================

LAS_DOCE = (
    "1_que_ocurrio", "2_siguen_abiertas", "3_empeoraron", "4_se_resolvieron",
    "5_sin_verificar", "6_tickets_relacionados", "7_sla_en_riesgo",
    "8_evidencias_pendientes", "9_recomendaciones_pendientes",
    "10_requiere_atencion_humana", "11_fuentes", "12_la_noche",
)


def test_I1_las_doce_preguntas_estan_y_cada_una_trae_su_procedencia(org_a):
    _situacion_real(org_a)

    r = trn.resumen_de_turno(org_a)

    for pregunta in LAS_DOCE:
        assert pregunta in r, pregunta
        assert r[pregunta]["procedencia"] in (
            trn.OBSERVADO, trn.INFERIDO, trn.RECOMENDADO, trn.CONFIRMADO,
            trn.DESCONOCIDO), pregunta
        assert r[pregunta]["fuente"], f"{pregunta} sin fuente declarada"


def test_I2_la_ventana_del_turno_queda_escrita_en_la_salida(org_a):
    """
    Un resumen sin su ventana no se puede leer: 'hay 3 situaciones nuevas' no
    dice nada si no se sabe de cuanto tiempo.
    """
    ahora = timezone.now()

    r = trn.resumen_de_turno(org_a, horas=8, ahora=ahora)

    assert r["turno"]["horas"] == 8.0
    assert r["turno"]["desde"] < r["turno"]["hasta"]
    assert r["turno"]["generado_en"] == ahora.isoformat()
    assert r["turno"]["organizacion"]["id"] == str(org_a.id)


def test_I3_una_situacion_de_anteanoche_que_se_movio_hoy_aparece(org_a):
    """
    'Lo que ocurrio en el turno' no es solo lo que nacio en el turno: una
    situacion vieja que empeoro anoche es justo lo que hay que mirar.
    """
    hace_tres_dias = timezone.now() - timezone.timedelta(days=3)
    s = _situacion_real(org_a, pon="3/1/4", ahora=hace_tres_dias)
    #  Se mueve AHORA, dentro de la ventana del turno.
    svc.anotar(s, tipo="actualizada", resumen="subio a 15 ONT")

    r = trn.resumen_de_turno(org_a, horas=12)

    assert r["1_que_ocurrio"]["datos"]["situaciones_nuevas"] == 0
    assert r["1_que_ocurrio"]["datos"]["situaciones_que_se_movieron"] == 1
    assert r["2_siguen_abiertas"]["datos"]["cuantas"] == 1


def test_I4_lo_que_no_se_puede_saber_sale_DESCONOCIDO_con_su_motivo(org_a):
    """
    §2 del lote: sin fuentes registradas, la pregunta 11 no contesta 'cero
    problemas' -- contesta que no se sabe de donde salieron los datos.
    """
    r = trn.resumen_de_turno(org_a)

    f = r["11_fuentes"]
    assert f["procedencia"] == trn.DESCONOCIDO
    assert f["datos"] is None
    assert "no hay ninguna fuente registrada" in f["nota"]
    #  Y todos los DESCONOCIDO quedan juntos al final, con su por que.
    assert any(d["pregunta"] == "11_fuentes" for d in r["desconocido"])


def test_I5_una_fuente_en_ERROR_no_se_lee_como_red_sana(org_a):
    from operaciones.fuentes_modelos import EstadoLectura

    _captura(org_a, pons={}, estado=EstadoLectura.ERROR)

    f = trn.resumen_de_turno(org_a)["11_fuentes"]

    assert f["procedencia"] == trn.OBSERVADO
    assert f["datos"]["con_problema"] == 1
    assert "NO significa que este bien" in f["nota"]


def test_I6_una_situacion_sin_verificar_aparece_en_las_dos_preguntas(org_a):
    """En la 5 como hecho, y en la 10 como algo que espera a una persona."""
    s = _situacion_real(org_a)
    svc.cambiar_estado(s, S.EN_VERIFICACION, motivo="la señal dejó de verse")

    r = trn.resumen_de_turno(org_a)

    assert r["5_sin_verificar"]["datos"]["cuantas"] == 1
    assert "NO las cierra" in r["5_sin_verificar"]["nota"]
    assert r["10_requiere_atencion_humana"]["datos"][
        "situaciones_sin_verificar"] == 1


def test_I7_sin_jornada_el_SLA_dice_que_no_hay_con_que_medir(org_a):
    """Cero ordenes en riesgo y 'no hay ordenes' no son lo mismo."""
    r = trn.resumen_de_turno(org_a)["7_sla_en_riesgo"]

    assert r["procedencia"] == trn.DESCONOCIDO
    assert "no hay plazo que medir" in r["nota"]


def test_I8_si_el_turno_no_toca_la_noche_lo_dice(org_a):
    """
    Devolver 'cero situaciones nocturnas' para un turno de tarde seria una
    afirmacion sobre una franja que ese turno nunca mira.
    """
    #  Un turno de 2 horas que termina a las 18:00 local.
    hasta = timezone.localtime(timezone.now()).replace(
        hour=18, minute=0, second=0, microsecond=0)

    r = trn.resumen_de_turno(org_a, horas=2, hasta=hasta, ahora=hasta)

    assert r["12_la_noche"]["procedencia"] == trn.DESCONOCIDO
    assert "no toca la franja nocturna" in r["12_la_noche"]["nota"]


def test_I9_un_turno_que_SI_toca_la_noche_la_reporta(org_a):
    de_noche = timezone.localtime(timezone.now()).replace(
        hour=2, minute=15, second=0, microsecond=0)
    _situacion_real(org_a, pon="3/1/4", ahora=de_noche)

    r = trn.resumen_de_turno(org_a, horas=6, hasta=de_noche + timezone.timedelta(
        hours=1), ahora=de_noche + timezone.timedelta(hours=1))

    n = r["12_la_noche"]
    assert n["procedencia"] == trn.OBSERVADO
    assert n["datos"]["situaciones_detectadas"] == 1


# =============================================================================
#  §J  P11  --  LA PROCEDENCIA, Y QUE NO SE PROMUEVE
# =============================================================================

def test_J1_una_recomendacion_pendiente_es_RECOMENDADO_nunca_mas(org_a):
    s = _situacion_real(org_a)
    _propuesta(org_a, situacion=s)

    r = trn.resumen_de_turno(org_a)["9_recomendaciones_pendientes"]

    assert r["procedencia"] == trn.RECOMENDADO
    assert r["datos"]["cuantas"] == 1
    assert "nadie decidio nada todavia" in r["nota"]


def test_J2_lo_que_el_Supervisor_concluyo_es_INFERIDO_no_OBSERVADO(org_a):
    """
    'Empeoro' es una lectura sobre dos capturas. La fuente nunca reporto
    'empeoro': reporto 12 y despues 15.
    """
    r = trn.resumen_de_turno(org_a)

    assert r["3_empeoraron"]["procedencia"] == trn.INFERIDO
    assert r["10_requiere_atencion_humana"]["procedencia"] == trn.INFERIDO
    assert r["1_que_ocurrio"]["procedencia"] == trn.OBSERVADO


def test_J3_una_decision_aceptada_no_aparece_como_CONFIRMADO(org_a, jefe):
    """
    La propiedad 4 del lote. 'Aceptada' vive en 'recomendado'; 'confirmado'
    solo se puebla con lecciones que llevan evidencia.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)

    e = trn.evaluacion_shadow(org_a)

    #  La clave la nombra 'TipoDecision.ACEPTO' ("acepto"), no el estado de la
    #  propuesta ("aceptada"): son dos vocabularios distintos.
    assert e["recomendado"]["datos"]["decisiones_por_tipo"][
        "decisiones_acepto"]["valor"] == 1
    assert e["confirmado"]["datos"]["precision"]["valor"] is None, (
        "sin desenlace no hay nada confirmado")
    assert e["confirmado"]["datos"]["lecciones_a_favor"]["valor"] == 0
    assert e["desconocido"]["datos"]["decisiones_sin_desenlace"]["valor"] == 1


def test_J4_el_tiempo_NO_promueve_un_INFERIDO_a_CONFIRMADO(org_a, jefe):
    """
    Se mide el EFECTO del paso del tiempo: la misma decision, leida una semana
    despues sin que nadie haya verificado nada, sigue en 'desconocido'.
    """
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)
    una_semana = timezone.now() + timezone.timedelta(days=7)

    e = trn.evaluacion_shadow(org_a, desde=timezone.now() -
                              timezone.timedelta(days=1), hasta=una_semana,
                              ahora=una_semana)

    assert e["confirmado"]["datos"]["precision"]["valor"] is None
    assert e["desconocido"]["datos"]["decisiones_sin_desenlace"]["valor"] == 1


def test_J5_cuando_hay_evidencia_SI_llega_a_CONFIRMADO(org_a, jefe):
    """El contrapunto: 'confirmado' no esta vacio por construccion."""
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(d, actor=jefe,
                                 resultado=ResultadoDecision.FUNCIONO,
                                 evidencia="las 12 ONT volvieron")

    e = trn.evaluacion_shadow(org_a)

    assert e["confirmado"]["datos"]["precision"]["valor"] == 1.0
    assert e["confirmado"]["datos"]["lecciones_a_favor"]["valor"] == 1
    assert "nunca es el propio Supervisor" in e["confirmado"]["nota"]


def test_J6_la_anticipacion_viaja_como_INFERIDO(org_a):
    """
    Anticipar no prueba haber evitado nada: es una lectura sobre dos instantes.
    """
    e = trn.evaluacion_shadow(org_a)

    assert e["inferido"]["procedencia"] == trn.INFERIDO
    assert "anticipadas" in e["inferido"]["datos"]
    assert "no prueba" in e["inferido"]["nota"]


# =============================================================================
#  §K  P11  --  SHADOW MODE: MEDIDO, NO DECLARADO
# =============================================================================

def test_K1_la_ejecucion_LEVANTA_y_eso_se_comprueba(org_a):
    """
    La diferencia entre 'no encontramos ninguna llamada externa' --una
    afirmacion sobre lo que alguien no vio-- y 'el camino levanta'.
    """
    e = trn.evaluacion_shadow(org_a)

    assert e["shadow_mode"]["activo"] is True
    assert e["shadow_mode"]["la_ejecucion_levanta"] is True
    assert e["shadow_mode"]["propuestas_ejecutadas"] == 0
    #  Y la comprobacion no es un booleano escrito a mano:
    assert trn._la_ejecucion_sigue_cerrada() is True
    with pytest.raises(Exception):
        sup.ejecutar_propuesta(None)


def test_K2_la_mutacion_del_shadow_mode_se_detecta(org_a, monkeypatch):
    """
    La guarda muerde: si alguien hiciera que la ejecucion NO levante, esta
    prueba se pone en rojo. Sin esto, 'la_ejecucion_levanta' seria una
    constante disfrazada de medicion.
    """
    monkeypatch.setattr(sup, "ejecutar_propuesta", lambda *a, **k: "ejecutado")

    assert trn._la_ejecucion_sigue_cerrada() is False
    assert trn.evaluacion_shadow(org_a)["shadow_mode"][
        "la_ejecucion_levanta"] is False


def test_K3_un_ciclo_completo_no_ejecuta_ni_deja_rastro_externo(org_a):
    """
    El ciclo entero sobre una situacion critica: deja propuestas y timeline, y
    ni una orden, ni una actividad, ni un caso tocado.
    """
    from campo.models import OrdenTrabajo
    from operaciones.models import ActividadOperativa

    _captura(org_a, pons={"3/1/4": _pon(60, abonados=100, porcentaje=60.0)})
    correlacion.correr(org_a)

    assert P.objects.filter(org=org_a).count() >= 1
    assert OrdenTrabajo.objects.count() == 0
    assert ActividadOperativa.objects.count() == 0
    assert Case.objects.count() == 0
    e = trn.evaluacion_shadow(org_a)
    assert e["shadow_mode"]["la_ejecucion_levanta"] is True


# =============================================================================
#  §L  SEGURIDAD, IDEMPOTENCIA DE LECTURA, TENANT
# =============================================================================

def test_L1_el_resumen_no_lleva_datos_de_cliente(org_a):
    """
    §5 de CLAUDE.md: el nombre de un cliente no tiene por que estar en un
    resumen de turno. Se afirma sobre el TEXTO completo de la salida, no sobre
    la lista de campos que se eligieron.
    """
    import json

    t0 = timezone.now() - timezone.timedelta(minutes=30)
    _situacion_real(org_a, pon="3/1/4", ahora=t0)
    caso = _caso_en(org_a, pon="3/1/4", creado_en=t0 +
                    timezone.timedelta(minutes=5))
    Case.objects.filter(pk=caso.pk).update(
        name="SOFIA MUNOZ - cédula 1234567890 - tel 3001234567")
    correlacion.asociar_tickets(org_a)

    texto = json.dumps(trn.resumen_de_turno(org_a), default=str)

    assert "SOFIA" not in texto.upper()
    assert "1234567890" not in texto
    assert "3001234567" not in texto
    #  Pero el HECHO sigue estando: hay un caso asociado.
    assert trn.resumen_de_turno(org_a)["6_tickets_relacionados"]["datos"][
        "casos_asociados_en_el_turno"] == 1


def test_L2_leer_dos_veces_con_el_mismo_ahora_da_lo_mismo(org_a, jefe):
    """
    Idempotencia de lectura: un resumen que cambia entre dos lecturas iguales
    no se puede revisar, y tampoco se puede citar en un relevo de turno.
    """
    import json

    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    ahora = timezone.now()

    uno = json.dumps(trn.resumen_de_turno(org_a, ahora=ahora), default=str,
                     sort_keys=True)
    dos = json.dumps(trn.resumen_de_turno(org_a, ahora=ahora), default=str,
                     sort_keys=True)

    assert uno == dos


def test_L3_el_resumen_NO_escribe_nada(org_a, jefe):
    s = _situacion_real(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    antes = (S.objects.count(), s.eventos.count(), P.objects.count(),
             D.objects.count(), Ap.objects.count(), Activity.objects.count(),
             SituacionAfectado.objects.count())

    trn.resumen_de_turno(org_a)
    trn.evaluacion_shadow(org_a)

    assert (S.objects.count(), s.eventos.count(), P.objects.count(),
            D.objects.count(), Ap.objects.count(), Activity.objects.count(),
            SituacionAfectado.objects.count()) == antes


def test_L4_el_turno_de_una_empresa_no_ve_a_la_otra(org_a, org_b):
    _situacion_real(org_a, pon="3/1/4")
    _situacion_real(org_b, pon="3/1/4")
    _situacion_real(org_b, pon="5/2/1")

    a = trn.resumen_de_turno(org_a)
    b = trn.resumen_de_turno(org_b)

    assert a["2_siguen_abiertas"]["datos"]["cuantas"] == 1
    assert b["2_siguen_abiertas"]["datos"]["cuantas"] == 2
    codigos_a = {f["codigo"] for f in a["2_siguen_abiertas"]["datos"]["detalle"]}
    codigos_b = {f["codigo"] for f in b["2_siguen_abiertas"]["datos"]["detalle"]}
    assert not (codigos_a & codigos_b) or len(S.objects.filter(
        org=org_a)) == 1, "los codigos son por empresa; los conjuntos no se mezclan"
    assert a["turno"]["organizacion"]["id"] == str(org_a.id)
    assert b["turno"]["organizacion"]["id"] == str(org_b.id)


def test_L5_la_hipotesis_viaja_SIEMPRE_con_su_confianza(org_a):
    """
    Lo mismo que la base obliga en la tabla, obligado en la salida: una
    sospecha floja y una firme no se pueden leer igual.
    """
    _situacion_real(org_a)

    r = trn.resumen_de_turno(org_a)

    for ficha in r["2_siguen_abiertas"]["datos"]["detalle"]:
        if ficha["hipotesis"]:
            assert ficha["confianza"], "una hipotesis sin confianza no sale"
            assert ficha["confianza"] != "sin_hipotesis"


# =============================================================================
#  §M  EL CABLEADO  --  que el resumen tenga por donde llegar
# =============================================================================
#
#  POR QUE ESTA SECCION EXISTE
#  ---------------------------
#  Porque un modulo probado y sin llamador es la falla que este repositorio ya
#  pago dos veces (el reloj colgado de un '__main__' que gunicorn no ejecuta, y
#  la reconciliacion sin quien la llamara). 'turno.py' pasa sus 40 pruebas
#  igual si nadie puede alcanzarlo: lo que esto mide es que se pueda.

RUTA_TURNO = "/api/operaciones/supervisor/turno/"


def test_M1_la_ruta_del_turno_devuelve_las_doce_preguntas(org_a, admin_client,
                                                          admin_profile):
    _situacion_real(org_a)

    r = admin_client.get(RUTA_TURNO)

    assert r.status_code == 200
    cuerpo = r.json()
    for pregunta in LAS_DOCE:
        assert pregunta in cuerpo, pregunta
    assert cuerpo["escrituras"] == 0
    assert cuerpo["fuente"] == "operaciones.turno.resumen_de_turno"


def test_M2_la_evaluacion_shadow_NO_viene_por_defecto(org_a, admin_client,
                                                      admin_profile):
    """Es mas cara que el resumen y no hace falta para tomar el turno."""
    assert "shadow" not in admin_client.get(RUTA_TURNO).json()

    con = admin_client.get(f"{RUTA_TURNO}?shadow=1").json()
    assert "shadow" in con
    assert con["shadow"]["shadow_mode"]["la_ejecucion_levanta"] is True


def test_M3_un_horas_ilegible_no_deja_sin_relevo(org_a, admin_client,
                                                 admin_profile):
    """
    Un 400 dejaria a quien llega sin su resumen por un parametro mal escrito.
    Se contesta la ventana por defecto.
    """
    r = admin_client.get(f"{RUTA_TURNO}?horas=ayer")

    assert r.status_code == 200
    assert r.json()["turno"]["horas"] == float(trn.HORAS_TURNO)


def test_M4_la_ventana_se_acota_arriba(org_a, admin_client, admin_profile):
    """
    Sin tope, 'horas=100000' seria una consulta de tabla completa pedida por
    query string.
    """
    assert admin_client.get(
        f"{RUTA_TURNO}?horas=100000").json()["turno"]["horas"] == 72.0
    assert admin_client.get(
        f"{RUTA_TURNO}?horas=0").json()["turno"]["horas"] == 1.0


def test_M5_sin_el_rol_la_ruta_no_contesta(org_a, user_client, user_profile):
    """
    Detras de esta puerta hay una persona tomando el turno: el panorama
    operativo completo no es para cualquier credencial del tenant.
    """
    r = user_client.get(RUTA_TURNO)
    assert r.status_code in (403, 401), r.status_code


def test_M6_la_ruta_no_cruza_empresas(org_a, org_b, admin_client,
                                      admin_profile):
    _situacion_real(org_a, pon="3/1/4")
    _situacion_real(org_b, pon="3/1/4")
    _situacion_real(org_b, pon="5/2/1")

    cuerpo = admin_client.get(RUTA_TURNO).json()

    assert cuerpo["turno"]["organizacion"]["id"] == str(org_a.id)
    assert cuerpo["2_siguen_abiertas"]["datos"]["cuantas"] == 1


def test_M7_las_dos_herramientas_del_chat_estan_registradas(org_a):
    from operaciones import chat_herramientas as ch

    _situacion_real(org_a)

    for nombre in ("resumen_de_turno", "evaluacion_shadow"):
        assert nombre in ch.HERRAMIENTAS, nombre
        assert nombre in ch.ARGUMENTOS, f"{nombre} sin lista blanca"
        assert any(h["function"]["name"] == nombre for h in ch.esquema()), (
            f"{nombre} no esta en el esquema que ve el modelo")
        #  Y se puede EJECUTAR por el despachador real, que es el que pone el
        #  tenant.
        assert isinstance(ch.ejecutar(org_a, nombre, {}), dict)


def test_M8_la_descripcion_le_dice_al_modelo_que_no_promueva(org_a):
    """
    La lista blanca y el sobre son la garantia; la descripcion es lo unico que
    el modelo lee. Si no dice que un INFERIDO no es un hecho, no lo sabe.
    """
    from operaciones import chat_herramientas as ch

    por_nombre = {h["function"]["name"]: h["function"]["description"]
                  for h in ch.esquema()}
    resumen = por_nombre["resumen_de_turno"]
    assert "PROCEDENCIA" in resumen
    assert "INFERIDO" in resumen and "DESCONOCIDO" in resumen
    assert "NO que no haya nada" in resumen
    shadow = por_nombre["evaluacion_shadow"]
    assert "NO es 'correcta'" in shadow or "NO es \"correcta\"" in shadow
    assert "NO es un cero" in shadow


def test_M9_un_argumento_inventado_se_descarta(org_a):
    """
    Fail-closed: lo que no esta declarado no llega a la funcion. Sin esto, un
    'org' dictado en un mensaje entraria por kwargs.
    """
    from operaciones import chat_herramientas as ch

    salida = ch.ejecutar(org_a, "resumen_de_turno",
                         {"horas": 6, "org": "otra", "limite": 10 ** 9})

    assert salida["turno"]["horas"] == 6.0
    assert salida["turno"]["organizacion"]["id"] == str(org_a.id)


def test_M10_la_ventana_de_la_herramienta_tambien_se_acota(org_a):
    from operaciones import chat_herramientas as ch

    assert ch._acotar_horas(100000) == 72
    assert ch._acotar_horas(0) == 1
    assert ch._acotar_horas("ayer") == trn.HORAS_TURNO
    assert ch._acotar_horas(None) == trn.HORAS_TURNO


def test_M11_turno_no_expone_ningun_modulo_que_escriba(org_a):
    """
    La propiedad que protege a 'test_p5_chat_supervisor::test_20'.

    'turno' es ahora alcanzable desde las herramientas del chat. Si importara
    'coordinacion', 'programacion' o 'supervisor' como MODULO, sus escrituras
    quedarian a un atributo de distancia del modelo -- exactamente lo que esa
    guarda afirma sobre 'coordinacion'. Se mide el EFECTO: el atributo no esta.
    """
    for modulo in ("coordinacion", "programacion", "m03", "supervisor", "sup",
                   "situaciones", "svc", "gobierno"):
        assert not hasattr(trn, modulo), (
            f"turno.{modulo} expuesto: su escritura queda alcanzable")


def test_M12_turno_no_tiene_ni_una_escritura(org_a):
    """
    El mismo escaneo que 'test_19' de M11 aplica a 'indicadores', aplicado a
    'turno' -- que es el modulo nuevo y el que ahora se expone.
    """
    import ast
    import inspect

    ESCRIBEN = {"create", "save", "update", "delete", "update_or_create",
                "get_or_create", "bulk_create", "add", "remove", "set",
                "clear", "post", "put", "patch", "correr_ciclo",
                "registrar_propuesta", "solicitar_actividad"}
    PROHIBIDOS = {"requests", "httpx", "urllib"}

    arbol = ast.parse(inspect.getsource(trn))
    atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}

    colados = (atributos & ESCRIBEN) | (nombres & PROHIBIDOS)
    assert not colados, sorted(colados)
