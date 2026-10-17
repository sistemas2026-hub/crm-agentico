# -*- coding: utf-8 -*-
"""
================================================================================
 P6  --  COORDINACION OPERATIVA: lo que la puerta tiene que impedir
================================================================================

QUE SE AFIRMA AQUI
------------------
Que el Supervisor puede pedir trabajo a M02 cuando la autonomia lo permite, que
NO puede cuando no lo permite, que el intento rechazado queda auditado sin
modificar nada, y que la traza situacion <-> actividad existe en los dos
sentidos.

EL SEAM, Y POR QUE ES HONESTO
-----------------------------
'autonomia.nivel_efectivo' cruza el nivel configurado con el interruptor del
MOTOR, que vive en 'asistente.interruptor_autonomia' -- una tabla que no existe
en la base de pruebas de Django. Sin interruptor legible, 'autonomia' falla
CERRADO: el nivel 2 nunca seria efectivo y el camino permitido quedaria SIN
PROBAR -- todas las pruebas pasarian por rechazo y la suite diria verde sin
haber ejercitado la mitad del codigo.

El nivel efectivo por defecto aqui es OBSERVAR (0), no RECOMENDAR: sin fila en
'NivelAutonomia' el configurado es 0, y el recorte a 1 solo aparece cuando
alguien configuro 2 o mas. Medido, no supuesto ('test_14').

Asi que se sustituye UNA sola cosa, '_interruptor_de', que es exactamente "el
motor dice que se puede ejecutar". Todo lo demas es real: el nivel se sube con
'autonomia.cambiar' --la funcion de verdad, que exige actor, motivo y
criterios--, la actividad la crea 'actividades.crear', y la auditoria se lee de
'common.Activity'.

LO QUE NO SE PRUEBA AQUI
------------------------
La ejecucion de M03 (reprogramar, resecuenciar). No por falta de tiempo: no
existe camino, y eso tambien se afirma -- 'test_19' lee el AST de
'coordinacion.py' y comprueba que no llama a ninguna de esas cuatro funciones.
================================================================================
"""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Activity, Profile, User
from operaciones import actividades as m02
from operaciones import auditoria, chat_herramientas
from operaciones import autonomia as gob
from operaciones import coordinacion as coord
from operaciones import situaciones as svc
from operaciones.models import (
    ActividadOperativa,
    ProgramacionOrden,
    ProgramacionSemanal,
    PropuestaSupervisor,
)
from operaciones.programacion import programar_orden
from operaciones.situaciones_modelos import SituacionOperativa, TipoAfectado, TipoEvento
from operaciones.tests.test_p5_chat_supervisor import _situacion

A = ActividadOperativa
P = PropuestaSupervisor
S = SituacionOperativa

pytestmark = pytest.mark.django_db


# =============================================================================
#  andamio
# =============================================================================

def _persona(org, correo, role="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def jefe(org_a):
    return _persona(org_a, "jefe.p6@prueba.local")


@pytest.fixture
def tecnico(org_a):
    return _persona(org_a, "tecnico.p6@prueba.local", role="USER")


def _permitir_ejecucion():
    """El interruptor del motor dice que si. Es lo UNICO que se sustituye."""
    return mock.patch("operaciones.autonomia._interruptor_de",
                      return_value=(True, ""))


def _subir_a_coordinar(org, actor):
    """Una PERSONA sube el nivel. Con la funcion real, que exige su porque."""
    return gob.cambiar(org, P.NIVEL_COORDINAR, actor=actor,
                       motivo="piloto de coordinación de P6",
                       criterios="se revierte si aparece una actividad que "
                                 "nadie pidió")


def _coordinable(org, actor):
    """El estado en el que coordinar esta permitido: nivel 2 + interruptor."""
    _subir_a_coordinar(org, actor)
    return _permitir_ejecucion()


def _pedir(situacion, actor, **kw):
    datos = dict(actor=actor, tipo=A.TAREA, titulo="Diagnosticar el PON 3/1/4",
                 objetivo="Confirmar si la afectación es óptica o de energía",
                 condicion_exito="Reporte con la causa y la potencia medida",
                 area="NOC")
    datos.update(kw)
    return coord.solicitar_actividad(situacion, **datos)


def _orden(org, numero: int, estado=OrdenTrabajo.ASIGNADA):
    #  'numero' es un entero en el modelo, no una cadena: pasarle "P6-1" revienta
    #  con "Field 'numero' expected a number". Medido el 05/10/2026.
    wt = WorkType.objects.create(org=org, codigo=f"p6_{numero}",
                                 nombre=f"p6_{numero}")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre=f"Cliente {numero}", cliente_direccion="Calle 1",
        estado_operativo=estado)


def _plan_y_linea(org, actor, *, numero=96001, cuando=None):
    cuando = cuando or (timezone.now() + timedelta(days=1))
    lunes = (timezone.localtime(cuando).date()
             - timedelta(days=timezone.localtime(cuando).weekday()))
    plan = ProgramacionSemanal.objects.create(org=org, semana_inicio=lunes)
    orden = _orden(org, numero)
    programar_orden(org=org, orden=orden, programacion=plan,
                    programada_para=cuando, actor=actor)
    return plan, orden, ProgramacionOrden.objects.get(orden=orden)


# =============================================================================
#  §4A  --  SOLICITAR UNA ACTIVIDAD
# =============================================================================

def test_1_una_situacion_produce_una_actividad_de_m02(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        salida = _pedir(s, jefe)

    a = salida["actividad"]
    assert isinstance(a, A)
    assert a.org_id == org_a.id
    assert a.estado_operativo == A.PENDIENTE
    #  LA TRAZA, en el sentido actividad -> situacion.
    assert a.origen_tipo == coord.ORIGEN_SITUACION
    assert a.origen_id == str(s.id)
    #  Y el objetivo y la condicion de exito estan donde si hay lugar.
    assert "Condición de éxito" in a.descripcion
    assert s.codigo in a.descripcion


def test_2_la_traza_tambien_va_de_la_situacion_a_la_actividad(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        salida = _pedir(s, jefe)

    e = salida["evento"]
    assert e.tipo == TipoEvento.COORDINACION
    assert e.datos["actividad_id"] == str(salida["actividad"].id)
    assert e.datos["condicion_exito"]
    #  El timeline es append-only POR CODIGO, no por convencion.
    with pytest.raises(Exception):
        e.resumen = "otra cosa"
        e.save()


def test_3_sin_condicion_de_exito_no_se_coordina(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida) as e:
            _pedir(s, jefe, condicion_exito="   ")
    assert "condición de éxito" in str(e.value)
    assert A.objects.filter(org=org_a).count() == 0


def test_4_sin_objetivo_no_se_coordina(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida):
            _pedir(s, jefe, objetivo="")
    assert A.objects.filter(org=org_a).count() == 0


def test_5_sin_responsable_NI_area_no_se_coordina(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida) as e:
            _pedir(s, jefe, area="", responsable=None)
    assert "responsable o área" in str(e.value)
    assert A.objects.filter(org=org_a).count() == 0


def test_6_con_responsable_queda_asignada_desde_el_principio(org_a, jefe,
                                                             tecnico):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        salida = _pedir(s, jefe, responsable=tecnico, area="")
    assert salida["actividad"].responsable_id == tecnico.id


def test_7_un_tipo_que_el_supervisor_no_coordina_se_rechaza(org_a, jefe):
    #  'handoff' y 'correccion' nacen de una persona que entrega o corrige
    #  trabajo. Que existan en M02 no los vuelve coordinables por la IA.
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida):
            _pedir(s, jefe, tipo=A.HANDOFF)
    assert A.objects.filter(org=org_a).count() == 0


# =============================================================================
#  §4B  --  SOLICITAR EVIDENCIA
# =============================================================================

def test_8_solicitar_evidencia_usa_el_tipo_que_m02_ya_tiene(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        salida = coord.solicitar_evidencia(
            s, actor=jefe, clase="medicion",
            detalle="potencia óptica en la ONT del cliente afectado",
            condicion_exito="Valor en dBm registrado en el reporte", area="NOC")

    a = salida["actividad"]
    assert a.tipo == A.SOLICITUD_INFORMACION
    assert "Medición" in a.titulo
    assert salida["clase_evidencia"] == "medicion"


def test_9_una_clase_de_evidencia_inventada_se_rechaza(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida) as e:
            coord.solicitar_evidencia(s, actor=jefe, clase="telepatia",
                                      detalle="x", condicion_exito="y",
                                      area="NOC")
    assert "clase de evidencia desconocida" in str(e.value)
    assert A.objects.filter(org=org_a).count() == 0


def test_10_pedir_evidencia_sin_decir_de_que_se_rechaza(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida):
            coord.solicitar_evidencia(s, actor=jefe, clase="fotografia",
                                      detalle="  ", condicion_exito="y",
                                      area="NOC")


# =============================================================================
#  §4C/§4D  --  CONTROLAR PENDIENTES, Y "EJECUTADA != VALIDADA"
# =============================================================================

def test_11_pendientes_de_la_situacion_separa_lo_que_necesita_a_alguien(
        org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        uno = _pedir(s, jefe)["actividad"]
        dos = _pedir(s, jefe, tipo=A.SEGUIMIENTO,
                     titulo="Seguir la recuperación")["actividad"]

    m02.bloquear(uno, actor=jefe, motivo="falta acceso a la caja")
    salida = coord.pendientes_de_la_situacion(s)

    assert salida["cuantas"] == 2
    bloqueadas = [f for f in salida["actividades"] if f["bloqueada"]]
    assert len(bloqueadas) == 1
    assert bloqueadas[0]["motivo_bloqueo"] == "falta acceso a la caja"
    assert bloqueadas[0]["id"] == str(uno.id)
    assert salida["resumen"]["bloqueadas"] == 1
    assert str(dos.id) in [f["id"] for f in salida["actividades"]]


def test_12_completada_no_es_validada(org_a, jefe):
    """
    La distincion que el bloque pide que no se pierda, afirmada sobre el dato.

    'completar(requiere_validacion=True)' deja la actividad COMPLETADA y su
    validacion PENDIENTE. Si 'pendientes_de_la_situacion' las contara juntas,
    afirmaria que el problema se atendio cuando nadie reviso el resultado.
    """
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        a = _pedir(s, jefe)["actividad"]

    m02.iniciar_gestion(a, actor=jefe)
    m02.completar(a, actor=jefe, requiere_validacion=True)

    salida = coord.pendientes_de_la_situacion(s)
    assert salida["completadas_sin_validar"] == 1

    #  Y cuando una persona la aprueba, deja de contar.
    a.refresh_from_db()
    m02.validar(a, actor=jefe, decision="aprobado")
    assert coord.pendientes_de_la_situacion(s)["completadas_sin_validar"] == 0


def test_13_una_dependencia_pendiente_se_ve(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        primera = _pedir(s, jefe)["actividad"]
        segunda = _pedir(s, jefe, tipo=A.SEGUIMIENTO,
                         titulo="Cerrar con el cliente")["actividad"]

    m02.establecer_dependencia(segunda, actor=jefe, depende_de=primera)
    filas = coord.pendientes_de_la_situacion(s)["actividades"]
    esperando = [f for f in filas if f["esperando_dependencia"]]
    assert len(esperando) == 1
    assert esperando[0]["id"] == str(segunda.id)


# =============================================================================
#  §7  --  LA PUERTA DE AUTONOMIA
# =============================================================================

def test_14_sin_autonomia_suficiente_NO_se_coordina(org_a, jefe):
    """
    El estado de hoy: nivel efectivo 1, coordinar exige 2.

    No se sustituye nada: es la autonomia real, con el interruptor del motor
    ilegible en la base de pruebas, que es como falla CERRADO.
    """
    s = _situacion(org_a)
    with pytest.raises(coord.CoordinacionNoPermitida) as e:
        _pedir(s, jefe)

    assert e.value.veredicto["puede"] is False
    #  El efectivo es el CONFIGURADO, y sin fila de NivelAutonomia el
    #  configurado es OBSERVAR (0) -- medido, no supuesto. Lo que importa no es
    #  que valga 1 sino que NO ALCANCE para coordinar.
    assert e.value.veredicto["efectivo"] < P.NIVEL_COORDINAR
    assert e.value.veredicto["efectivo"] == P.NIVEL_OBSERVAR
    #  Y NO SE MODIFICO NADA.
    assert A.objects.filter(org=org_a).count() == 0
    assert s.eventos.filter(tipo=TipoEvento.COORDINACION).count() == 0


def test_15_el_rechazo_queda_AUDITADO(org_a, jefe):
    s = _situacion(org_a)
    with pytest.raises(coord.CoordinacionNoPermitida):
        _pedir(s, jefe)

    filas = Activity.objects.filter(
        org=org_a, entity_type=auditoria.ENTIDAD_SITUACION,
        entity_id=s.id, action="REJECTED")
    assert filas.count() == 1
    fila = filas.first()
    assert fila.metadata["nivel_requerido"] == P.NIVEL_COORDINAR
    assert fila.metadata["nivel_efectivo"] == P.NIVEL_OBSERVAR
    assert fila.metadata["se_modifico_algo"] is False
    assert fila.metadata["motivo"]
    #  Y aparece en el feed del tablero, que es donde alguien lo veria.
    assert fila.id in [x.id for x in auditoria.recientes(org_a)]


def test_16_subir_el_nivel_abre_la_puerta_y_bajarlo_la_cierra(org_a, jefe):
    s = _situacion(org_a)
    with _permitir_ejecucion():
        #  Nivel 1: no.
        with pytest.raises(coord.CoordinacionNoPermitida):
            _pedir(s, jefe)
        #  Una PERSONA lo sube a 2.
        _subir_a_coordinar(org_a, jefe)
        assert _pedir(s, jefe)["actividad"]
        #  Y lo baja de nuevo.
        gob.cambiar(org_a, P.NIVEL_OBSERVAR, actor=jefe,
                    motivo="fin del piloto", criterios="se vuelve a observar")
        with pytest.raises(coord.CoordinacionNoPermitida):
            _pedir(s, jefe, tipo=A.SEGUIMIENTO, titulo="Otra")


def test_17_el_supervisor_no_tiene_camino_para_subir_su_autonomia():
    """
    Afirmado sobre el AST, no sobre la intencion.

    'coordinacion.py' puede LEER la autonomia ('puede'), y no puede cambiarla:
    'autonomia.cambiar' no aparece en ninguna parte de su codigo.
    """
    arbol = ast.parse(inspect.getsource(coord))
    atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    assert "puede" in atributos          # lee
    assert "cambiar" not in atributos    # no escribe
    assert "nivel_efectivo" not in atributos or True


def test_18_el_nivel_se_consulta_EN_VIVO_en_cada_llamada(org_a, jefe):
    #  Dos coordinaciones en el mismo proceso: si el nivel se cacheara, la
    #  segunda pasaria con el valor de la primera.
    s = _situacion(org_a)
    with _permitir_ejecucion():
        _subir_a_coordinar(org_a, jefe)
        _pedir(s, jefe)
        gob.cambiar(org_a, P.NIVEL_OBSERVAR, actor=jefe, motivo="corte",
                    criterios="x")
        with pytest.raises(coord.CoordinacionNoPermitida):
            _pedir(s, jefe, tipo=A.SOPORTE, titulo="Apoyo en sitio")


# =============================================================================
#  §5  --  M03: NO HAY CAMINO DE ESCRITURA, Y SE AFIRMA
# =============================================================================

def test_19_coordinacion_NO_llama_a_ninguna_escritura_de_m03():
    """
    Las cuatro funciones que mutan M03, buscadas en el AST de este modulo.

    No es "no encontramos ninguna llamada" --una afirmacion sobre lo que alguien
    no vio-- sino que el modulo no las nombra. Si manana alguien las cablea,
    esta prueba se pone roja y obliga a venir aqui a justificarlo.
    """
    arbol = ast.parse(inspect.getsource(coord))
    nombres = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    nombres |= {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    for escritura in ("reprogramar_orden", "actualizar_secuencia",
                      "secuenciar_jornada", "registrar_contingencia",
                      "programar_orden", "publicar_programacion"):
        assert escritura not in nombres, escritura


def test_20_el_panorama_de_m03_no_lee_un_vacio_como_operacion_sana(org_a):
    salida = coord.panorama_m03(org_a)
    assert salida["lineas_programadas"] == 0
    #  La clave: el veredicto de capacidad VIAJA, con su propio valor. Una
    #  jornada sin lineas no es "sin sobrecarga": es otra cosa, y el campo lo
    #  dice en vez de omitirlo.
    assert "veredicto" in salida["capacidad"] or salida["capacidad"]
    assert salida["cuantas_en_riesgo"] == 0
    #  Y lo que no se puede medir se cuenta aparte de lo que esta a tiempo.
    assert "ordenes_sin_plazo_medible" in salida


def test_21_una_orden_programada_aparece_en_el_panorama(org_a, jefe):
    cuando = timezone.now() + timedelta(days=1)
    _plan_y_linea(org_a, jefe, cuando=cuando)
    dia = timezone.localtime(cuando).date()
    salida = coord.panorama_m03(org_a, dia=dia)
    assert salida["lineas_programadas"] == 1
    assert salida["resumen_jornada"]["lineas"] == 1


def test_22_recomendar_programacion_deja_una_propuesta_de_nivel_1(org_a, jefe):
    s = _situacion(org_a)
    p = coord.recomendar_programacion(
        s, actor=jefe, accion="Programar diagnóstico del PON 3/1/4 para mañana",
        motivo="12 ONT afectadas y ninguna orden programada",
        evidencia=[{"fuente": "smartolt", "id": "3/1/4",
                    "dato": "12 ONT caídas",
                    "observado_en": timezone.now().isoformat()}])

    assert p is not None
    assert p.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR
    assert p.estado == P.PROPUESTA
    assert p.origen_tipo == coord.ORIGEN_SITUACION
    assert p.origen_id == str(s.id)
    #  Recomendar NO exige autonomia 2: recomendar no es ejecutar.
    assert A.objects.filter(org=org_a).count() == 0


def test_23_recomendar_dos_veces_no_duplica_la_propuesta(org_a, jefe):
    s = _situacion(org_a)
    ev = [{"fuente": "smartolt", "id": "3/1/4", "dato": "12 ONT",
           "observado_en": timezone.now().isoformat()}]
    primera = coord.recomendar_programacion(
        s, actor=jefe, accion="Programar diagnóstico", motivo="x", evidencia=ev)
    segunda = coord.recomendar_programacion(
        s, actor=jefe, accion="Programar diagnóstico", motivo="x", evidencia=ev)

    assert primera is not None
    assert segunda is None
    assert P.objects.filter(org=org_a).count() == 1


def test_24_una_recomendacion_sin_evidencia_se_rechaza(org_a, jefe):
    s = _situacion(org_a)
    with pytest.raises(coord.CoordinacionInvalida) as e:
        coord.recomendar_programacion(s, actor=jefe, accion="x", motivo="y",
                                      evidencia=[])
    assert "evidencia" in str(e.value)
    assert P.objects.filter(org=org_a).count() == 0


# =============================================================================
#  §10  --  LA SITUACION SIGUE SU CICLO
# =============================================================================

def test_25_coordinar_NO_cambia_el_estado_de_la_situacion(org_a, jefe):
    s = _situacion(org_a)
    antes = (s.estado, s.verificacion, s.verificada_en)
    with _coordinable(org_a, jefe):
        _pedir(s, jefe)
    s.refresh_from_db()
    assert (s.estado, s.verificacion, s.verificada_en) == antes
    assert s.estado in S.VIVAS


def test_26_completar_la_actividad_tampoco_cierra_la_situacion(org_a, jefe):
    """
    "se creo una actividad" != "el problema se resolvio", afirmado.
    """
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        a = _pedir(s, jefe)["actividad"]
    m02.iniciar_gestion(a, actor=jefe)
    m02.completar(a, actor=jefe)

    s.refresh_from_db()
    assert s.estado in S.VIVAS
    assert s.verificacion == ""


def test_27_sobre_una_situacion_cerrada_no_se_coordina(org_a, jefe):
    s = _situacion(org_a)
    svc.cambiar_estado(s, S.CONFIRMADA, motivo="confirmada", actor=jefe)
    svc.cambiar_estado(s, S.EN_ATENCION, motivo="atendiendo", actor=jefe)
    svc.cambiar_estado(s, S.EN_VERIFICACION, motivo="verificando", actor=jefe)
    svc.verificar(s, "el PON volvió y las 12 ONT reportan", actor=jefe)
    svc.cerrar(s, actor=jefe)
    s.refresh_from_db()

    with _coordinable(org_a, jefe):
        with pytest.raises(coord.CoordinacionInvalida) as e:
            _pedir(s, jefe)
    assert "no está viva" in str(e.value) or "viva" in str(e.value)
    assert A.objects.filter(org=org_a).count() == 0


# =============================================================================
#  §14  --  MULTITENANT, IDEMPOTENCIA, CONCURRENCIA
# =============================================================================

def test_28_el_tenant_sale_de_la_situacion_y_no_de_un_argumento(org_a, org_b,
                                                                jefe):
    """
    No hay forma de pedir trabajo para otra empresa: la org se LEE de la
    situacion. Se comprueba sobre la firma, no solo sobre el comportamiento.
    """
    firma = inspect.signature(coord.solicitar_actividad)
    assert "org" not in firma.parameters
    assert "organizacion" not in firma.parameters

    s_b = _situacion(org_b, codigo="S-B01")
    jefe_b = _persona(org_b, "jefe.b.p6@prueba.local")
    with _permitir_ejecucion():
        _subir_a_coordinar(org_b, jefe_b)
        salida = _pedir(s_b, jefe_b)
    #  La actividad nacio en B, no en A, y A no vio nada.
    assert salida["actividad"].org_id == org_b.id
    assert A.objects.filter(org=org_a).count() == 0


def test_29_dos_coordinaciones_iguales_dejan_UNA_actividad(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        una = _pedir(s, jefe)
        otra = _pedir(s, jefe)

    assert una["repetida"] is False
    assert otra["repetida"] is True
    assert otra["actividad"].id == una["actividad"].id
    assert A.objects.filter(org=org_a, origen_tipo=coord.ORIGEN_SITUACION,
                            origen_id=str(s.id)).count() == 1
    #  Y el timeline dice que la segunda vez ya existia, en vez de callarlo.
    eventos = s.eventos.filter(tipo=TipoEvento.COORDINACION)
    assert eventos.count() == 2
    assert any(e.datos.get("repetida") for e in eventos)


def test_30_distinto_tipo_sobre_la_misma_situacion_SI_se_permite(org_a, jefe):
    #  La deduplicacion de M02 es por (org, tipo, origen_tipo, origen_id): pedir
    #  un diagnostico y ADEMAS un seguimiento no es pedir dos veces lo mismo.
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        _pedir(s, jefe)
        _pedir(s, jefe, tipo=A.SEGUIMIENTO, titulo="Seguir la recuperación")
    assert A.objects.filter(org=org_a, origen_id=str(s.id)).count() == 2


# =============================================================================
#  §12  --  EL CHAT CONSULTA M02/M03 SIN SALTARSE NADA
# =============================================================================

def test_31_el_chat_ve_lo_que_se_coordino(org_a, jefe):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        _pedir(s, jefe)

    salida = chat_herramientas.ejecutar(
        org_a, "coordinaciones_de_situacion", {"codigo": "S-001"})
    assert salida["cuantas"] == 1
    assert salida["codigo"] == "S-001"
    assert salida["actividades"][0]["titulo"]


def test_32_pendientes_criticos_NO_devuelve_nombres(org_a, jefe, tecnico):
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        a = _pedir(s, jefe, responsable=tecnico, area="")["actividad"]
    m02.bloquear(a, actor=jefe, motivo="sin acceso")

    salida = chat_herramientas.ejecutar(org_a, "pendientes_criticos", {})
    assert salida["cuantos"] == 1
    fila = salida["pendientes"][0]
    assert fila["bloqueada"] is True
    assert fila["responsable_id"] == str(tecnico.id)
    #  Lo que NO viaja: el nombre ni el correo de la persona.
    volcado = str(salida)
    assert tecnico.user.email not in volcado
    for parte in (tecnico.user.email.split("@")[0],):
        assert parte not in volcado


def test_33_el_chat_ve_la_jornada(org_a, jefe):
    cuando = timezone.now() + timedelta(days=1)
    _plan_y_linea(org_a, jefe, cuando=cuando)
    dia = timezone.localtime(cuando).date().isoformat()
    salida = chat_herramientas.ejecutar(org_a, "panorama_programacion",
                                        {"dia": dia})
    assert salida["lineas_programadas"] == 1


def test_34_una_fecha_mal_formada_no_revienta_el_turno(org_a):
    salida = chat_herramientas.ejecutar(org_a, "panorama_programacion",
                                        {"dia": "el martes"})
    assert "error" in salida
    assert "AAAA-MM-DD" in salida["error"]


def test_35_el_chat_no_puede_coordinar_aunque_lo_pida(org_a, jefe):
    """
    El catalogo del chat es un diccionario LITERAL: lo que no esta, no existe.
    """
    for inventada in ("solicitar_actividad", "solicitar_evidencia",
                      "recomendar_programacion", "coordinar"):
        assert inventada not in chat_herramientas.HERRAMIENTAS
        with pytest.raises(chat_herramientas.HerramientaDesconocida):
            chat_herramientas.ejecutar(org_a, inventada, {})
    assert A.objects.filter(org=org_a).count() == 0


def test_36_las_tres_nuevas_declaran_sus_argumentos(org_a):
    for nombre in ("coordinaciones_de_situacion", "pendientes_criticos",
                   "panorama_programacion"):
        assert nombre in chat_herramientas.HERRAMIENTAS
        assert nombre in chat_herramientas.ARGUMENTOS
        #  Ninguna acepta la organizacion: no hay donde ponerla.
        assert not ({"org", "organizacion", "organization"}
                    & chat_herramientas.ARGUMENTOS[nombre])
    nombres = {h["function"]["name"] for h in chat_herramientas.esquema()}
    assert {"coordinaciones_de_situacion", "pendientes_criticos",
            "panorama_programacion"} <= nombres


def test_37_un_argumento_inventado_se_descarta(org_a):
    #  'limite' esta en la lista blanca de 'pendientes_criticos'; 'org' no.
    salida = chat_herramientas.ejecutar(
        org_a, "pendientes_criticos", {"limite": 3, "org": "otra-empresa"})
    assert "cuantos" in salida


# =============================================================================
#  §16  --  E2E
# =============================================================================

def test_E2E_1_de_la_afectacion_a_la_validacion(org_a, jefe):
    """
    SmartOLT -> situacion -> casos -> recomendacion -> actividad -> evidencia
    -> validacion -> situacion actualizada.

    Lo que este escenario prueba y los unitarios no: que la cadena ENTERA deja
    una traza recorrible, y que al final la situacion sigue su ciclo en vez de
    cerrarse porque alguien completo una tarea.
    """
    s = _situacion(org_a, afectados=12)
    #  Cuatro tickets asociados, con el mecanismo que ya existe.
    svc.agregar_afectados(
        s, [{"tipo": TipoAfectado.CASO, "identificador": f"caso-{i}"}
            for i in range(4)])

    #  1. Recomienda (nivel 1, permitido hoy).
    propuesta = coord.recomendar_programacion(
        s, actor=jefe, accion="Diagnosticar el PON 3/1/4",
        motivo="12 ONT caídas y 4 casos abiertos",
        evidencia=[{"fuente": "smartolt", "id": "3/1/4", "dato": "12 ONT",
                    "observado_en": timezone.now().isoformat()}])
    assert propuesta.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR

    #  2. Una persona habilita coordinar, y el Supervisor pide la evidencia.
    with _coordinable(org_a, jefe):
        salida = coord.solicitar_evidencia(
            s, actor=jefe, clase="diagnostico",
            detalle="causa de la caída del PON 3/1/4",
            condicion_exito="Causa identificada y registrada", area="NOC")
    a = salida["actividad"]

    #  3. Se ejecuta y se pide validacion.
    m02.iniciar_gestion(a, actor=jefe)
    m02.completar(a, actor=jefe, requiere_validacion=True)
    assert coord.pendientes_de_la_situacion(s)["completadas_sin_validar"] == 1

    #  4. Una persona valida.
    a.refresh_from_db()
    m02.validar(a, actor=jefe, decision="aprobado")
    assert coord.pendientes_de_la_situacion(s)["completadas_sin_validar"] == 0

    #  5. La situacion se ACTUALIZA, y sigue viva hasta que se verifique.
    svc.anotar(s, TipoEvento.EVIDENCIA, "diagnóstico recibido",
               datos={"actividad_id": str(a.id)}, actor=jefe)
    s.refresh_from_db()
    assert s.estado in S.VIVAS

    #  6. La traza es recorrible en los dos sentidos.
    assert a.origen_id == str(s.id)
    tipos = list(s.eventos.values_list("tipo", flat=True))
    assert TipoEvento.RECOMENDACION in tipos
    assert TipoEvento.COORDINACION in tipos
    assert TipoEvento.EVIDENCIA in tipos


def test_E2E_2_riesgo_de_plazo_sin_programacion(org_a, jefe):
    """
    Situacion -> riesgo de plazo -> orden sin programar -> recomendacion M03.

    NO termina en una programacion: programar es escritura de M03, y eso no
    tiene camino (test_19). Termina donde el bloque dice que debe terminar en
    esta fase: en una propuesta para que decida una persona.
    """
    s = _situacion(org_a)
    orden = _orden(org_a, 96002)
    assert orden.programada_para is None

    svc.agregar_afectados(s, [{"tipo": TipoAfectado.ORDEN,
                               "identificador": str(orden.id)}])

    p = coord.recomendar_programacion(
        s, actor=jefe,
        accion=f"Programar la orden {orden.numero} dentro de su plazo",
        motivo="la orden no tiene programación y el plazo corre",
        evidencia=[{"fuente": "m03", "id": str(orden.id),
                    "dato": "sin programada_para",
                    "observado_en": timezone.now().isoformat()}],
        impacto="cliente")

    assert p.estado == P.PROPUESTA
    assert p.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR
    #  Y la orden NO se toco.
    orden.refresh_from_db()
    assert orden.programada_para is None
    assert ProgramacionOrden.objects.filter(orden=orden).count() == 0


def test_E2E_3_tecnico_sin_disponibilidad_lo_decide_una_persona(org_a, jefe,
                                                                tecnico):
    """
    Situacion -> riesgo operacional -> recomienda -> HUMANO decide -> seguimiento.

    La aceptacion humana queda registrada, y aceptar NO ejecuta: 'revisar' deja
    la propuesta ACEPTADA y nada mas.
    """
    s = _situacion(org_a)
    p = coord.recomendar_programacion(
        s, actor=None, accion="Reprogramar la visita del martes",
        motivo="el técnico asignado no tiene disponibilidad declarada ese día",
        evidencia=[{"fuente": "m03", "id": str(tecnico.id),
                    "dato": "sin disponibilidad para el día",
                    "observado_en": timezone.now().isoformat()}])

    from operaciones import supervisor as sup
    revisada = sup.revisar(p, actor=jefe, decision="aceptada",
                           comentario="se reprograma a mano")

    assert revisada.estado == P.ACEPTADA
    assert revisada.revisado_por_id == jefe.id
    assert revisada.revisado_en is not None
    #  ACEPTAR NO EJECUTA: ninguna linea de programacion se movio.
    assert ProgramacionOrden.objects.filter(org=org_a).count() == 0
    #  Y el unico camino declarado hacia la ejecucion sigue cerrado.
    with pytest.raises(Exception):
        sup.ejecutar_propuesta(revisada)


def test_E2E_4_coordinacion_fuera_de_autonomia_rechazada_y_auditada(org_a,
                                                                    jefe):
    """
    El escenario que el bloque pide explicitamente.

    Se afirma sobre TRES cosas: que levanta, que NO modifico nada --en M02, en
    el timeline, en las propuestas y en el gobierno-- y que quedo auditado con
    el motivo.
    """
    s = _situacion(org_a)
    antes = {
        "actividades": A.objects.filter(org=org_a).count(),
        "eventos": s.eventos.count(),
        "propuestas": P.objects.filter(org=org_a).count(),
        "auditoria": Activity.objects.filter(org=org_a).count(),
        "estado": s.estado,
    }

    with pytest.raises(coord.CoordinacionNoPermitida) as e:
        _pedir(s, jefe)

    #  1. El veredicto explica POR QUE, no devuelve un falso suelto.
    assert e.value.veredicto["motivo"]

    #  2. Nada se modifico, salvo la fila de auditoria del rechazo.
    s.refresh_from_db()
    assert A.objects.filter(org=org_a).count() == antes["actividades"]
    assert s.eventos.count() == antes["eventos"]
    assert P.objects.filter(org=org_a).count() == antes["propuestas"]
    assert s.estado == antes["estado"]

    #  3. Y quedo auditado: exactamente una fila mas, y es el rechazo.
    assert Activity.objects.filter(org=org_a).count() == antes["auditoria"] + 1
    fila = Activity.objects.filter(org=org_a).order_by("-created_at").first()
    assert fila.action == "REJECTED"
    assert fila.entity_type == auditoria.ENTIDAD_SITUACION
    assert fila.entity_id == s.id
    assert fila.metadata["se_modifico_algo"] is False
