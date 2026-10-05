# -*- coding: utf-8 -*-
"""
================================================================================
 P4  --  SEGUIMIENTO, MEMORIA DE DECISIONES Y GOBIERNO DE AUTONOMIA
================================================================================

LAS CUATRO PROPIEDADES QUE JUSTIFICAN ESTE BLOQUE
-------------------------------------------------
  1. Una situacion NO termina porque termino un ciclo. El seguimiento la evalua
     entre ciclos y puede concluir sin ninguna señal nueva -- que es el caso que
     importa: una situacion de la que hace rato no se sabe nada.
  2. El Supervisor puede decir "no tengo suficiente informacion". 'SIN_EVIDENCIA'
     es una salida de primera clase, no un error.
  3. Una decision humana se guarda CON SU RESULTADO. Medir aceptaciones sin
     desenlace mide obediencia, no acierto.
  4. El Supervisor NO puede subirse el nivel de autonomia. Lo exige el codigo y
     lo vuelve a exigir la base.

COMO ESTA ORDENADO
------------------
    §1  el veredicto del seguimiento, caso por caso
    §2  lo que el seguimiento escribe, y lo que NO cambia
    §3  propuestas desde una situacion, sin duplicar
    §4  memoria de decisiones
    §5  gobierno de autonomia 0-4
    §6  el nivel efectivo y el interruptor del motor
    §7  metricas
    §8  multi-tenant
    §9  lo que NO hace
================================================================================
"""

import json
from unittest import mock

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone

from campo.models import OrdenTrabajo
from cases.models import Case
from operaciones import (autonomia, correlacion, fuentes, indicadores,
                         situaciones as svc, situaciones_propuestas,
                         situaciones_seguimiento as seg)
from operaciones.fuentes_modelos import EstadoLectura, Fuente, FuenteEstado
from operaciones.gobierno_modelos import (DecisionSupervisor, NivelAutonomia,
                                          ResultadoDecision, TipoDecision)
from operaciones.models import PropuestaSupervisor
from operaciones.situaciones_modelos import (Confianza, Riesgo,
                                             SituacionAfectado,
                                             SituacionOperativa, TipoAfectado,
                                             TipoEvento)
from operaciones.situaciones_seguimiento import Veredicto

S = SituacionOperativa
P = PropuestaSupervisor


# =============================================================================
#  utilidades
# =============================================================================

def _captura(org, *, pons, ahora=None, estado=EstadoLectura.CON_DATOS):
    ahora = ahora or timezone.now()
    f, _ = FuenteEstado.objects.update_or_create(
        org=org, fuente=Fuente.SMARTOLT,
        defaults={"activa": True, "frecuencia_segundos": 300,
                  "ventana_inconclusa_segundos": 0})
    return fuentes.registrar(
        f, fuentes.Lectura(estado, datos=pons, registros=len(pons),
                           dato_en=ahora if pons else None,
                           esquema="smartolt_pon_v1",
                           error_tecnico="x" if estado == EstadoLectura.ERROR
                           else ""),
        inicio=ahora, ahora=ahora)


def _pon(afectados, *, abonados=103, tipo="partial_los", porcentaje=None):
    fila = {"afectados": afectados, "abonados": abonados, "tipo": tipo,
            "caja": "CTO 56"}
    if porcentaje is not None:
        fila["porcentaje_afectado"] = porcentaje
    return fila


def _situacion(org, *, afectados=12, riesgo=Riesgo.ALTO, **extra):
    """Una situacion con su afectado de PON, como la dejaria el ciclo."""
    ahora = extra.pop("ahora", None) or timezone.now()
    datos = dict(org=org, codigo="S-900", tipo=S.AFECTACION_PON,
                 titulo="Posible afectación del PON 3/1/4",
                 descripcion="concentracion", estado=S.DETECTADA, riesgo=riesgo,
                 huella="afectacion_pon|pon:3/1/4", detectada_en=ahora,
                 actualizada_en=ahora, senal_vista_en=ahora,
                 fuente_origen=Fuente.SMARTOLT,
                 evidencia=[{"fuente": "smartolt", "dato": f"{afectados} ONT",
                             "observado_en": ahora.isoformat()}])
    datos.update(extra)
    s = S.objects.create(**datos)
    if afectados is not None:
        svc.agregar_afectados(
            s, [{"tipo": TipoAfectado.PON, "identificador": "3/1/4",
                 "datos": {"afectados": afectados}}], ahora=ahora)
    return s


def _medicion(situacion, n, *, cuando=None):
    """Un evento de medicion, que es de donde el seguimiento saca el delta."""
    svc.anotar(situacion, TipoEvento.ACTUALIZADA,
               f"{n} ONT afectadas en el PON 3/1/4",
               ocurrido_en=cuando or timezone.now())


# =============================================================================
#  §1  EL VEREDICTO
# =============================================================================

def test_1_sin_cambio_es_estable(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=12, ahora=ahora)
    _medicion(s, 12, cuando=ahora - timezone.timedelta(minutes=10))
    _medicion(s, 12, cuando=ahora)

    r = seg.evaluar(s, ahora=ahora)

    assert r["veredicto"] == Veredicto.ESTABLE
    assert r["abonados_afectados"] == 12
    assert r["concluyente"] is True


def test_2_mas_afectados_es_empeora(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=15, ahora=ahora)
    _medicion(s, 12, cuando=ahora - timezone.timedelta(minutes=5))
    _medicion(s, 15, cuando=ahora)

    r = seg.evaluar(s, ahora=ahora)

    assert r["veredicto"] == Veredicto.EMPEORA
    assert r["delta"] == 3
    assert "12" in r["porque"] and "15" in r["porque"]


def test_3_menos_afectados_es_mejora(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=4, ahora=ahora)
    _medicion(s, 12, cuando=ahora - timezone.timedelta(minutes=5))
    _medicion(s, 4, cuando=ahora)

    r = seg.evaluar(s, ahora=ahora)

    assert r["veredicto"] == Veredicto.MEJORA
    assert r["delta"] == -8


def test_4_sin_afectados_PUEDE_RESOLVERSE_pero_no_se_resolvio(org_a):
    #  La distincion que sostiene el bloque anterior: no quedan afectados NO es
    #  "se resolvio". Son las condiciones para ir a comprobar.
    ahora = timezone.now()
    s = _situacion(org_a, afectados=0, ahora=ahora)

    r = seg.evaluar(s, ahora=ahora)

    assert r["veredicto"] == Veredicto.PUEDE_RESOLVERSE
    assert "comprobar" in r["porque"]
    assert Veredicto.PUEDE_RESOLVERSE not in (S.RESUELTA, S.CERRADA)


def test_5_un_riesgo_critico_pide_una_persona_aunque_este_estable(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO, ahora=ahora)
    _medicion(s, 60, cuando=ahora - timezone.timedelta(minutes=5))
    _medicion(s, 60, cuando=ahora)

    r = seg.evaluar(s, ahora=ahora)

    #  Un critico "estable" sigue siendo un critico. El orden de las preguntas
    #  es lo que lo garantiza.
    assert r["veredicto"] == Veredicto.REQUIERE_HUMANO
    assert "critico" in r["porque"]


def test_6_un_ciclo_sin_informacion_es_SIN_EVIDENCIA(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=12, ahora=ahora)
    svc.anotar(s, TipoEvento.INCONCLUSA, "la fuente no concluyo",
               ocurrido_en=ahora)

    r = seg.evaluar(s, ahora=ahora)

    #  No se concluye nada. No es un error, y tampoco es "estable".
    assert r["veredicto"] == Veredicto.SIN_EVIDENCIA
    assert r["concluyente"] is False


def test_7_dos_ciclos_sin_informacion_piden_una_persona(org_a):
    #  Un ciclo sin dato puede ser un hueco de lectura. Dos seguidos es un
    #  patron, y el Supervisor tiene que poder decir que no sabe.
    ahora = timezone.now()
    s = _situacion(org_a, afectados=12, ahora=ahora)
    for i in range(seg.CICLOS_SIN_EVIDENCIA_PARA_ESCALAR):
        svc.anotar(s, TipoEvento.INCONCLUSA, "sin informacion",
                   ocurrido_en=ahora + timezone.timedelta(seconds=i))

    r = seg.evaluar(s, ahora=ahora)

    assert r["veredicto"] == Veredicto.REQUIERE_HUMANO
    assert "sin informacion concluyente" in r["porque"]


def test_8_el_veredicto_es_reproducible(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, afectados=12, ahora=ahora)
    _medicion(s, 10, cuando=ahora - timezone.timedelta(minutes=5))
    _medicion(s, 12, cuando=ahora)

    #  Misma situacion y mismo 'ahora' -> mismo veredicto. Sin esto no se puede
    #  depurar por que una situacion quedo clasificada como quedo.
    a = seg.evaluar(s, ahora=ahora)
    b = seg.evaluar(s, ahora=ahora)
    assert a == b


# =============================================================================
#  §2  LO QUE ESCRIBE, Y LO QUE NO CAMBIA
# =============================================================================

def test_9_el_seguimiento_anota_el_veredicto_en_el_timeline(org_a):
    s = _situacion(org_a, afectados=12)

    seg.seguir(org_a)

    evento = s.eventos.filter(tipo=TipoEvento.EVIDENCIA).last()
    assert evento is not None
    assert "seguimiento:" in evento.resumen
    assert evento.datos["veredicto"] in Veredicto.TODOS


def test_10_fija_cuando_volver_a_mirarla(org_a):
    s = _situacion(org_a, afectados=12)
    assert s.proxima_revision_en is None

    seg.seguir(org_a)

    s.refresh_from_db()
    assert s.proxima_revision_en is not None
    assert s.proxima_revision_en > s.actualizada_en


def test_11_una_que_empeora_se_revisa_antes_que_una_estable(org_a):
    #  El intervalo depende del veredicto, y la diferencia tiene motivo: una
    #  estable no gana nada con que se la mire cada cinco minutos.
    assert (seg.PROXIMA_REVISION[Veredicto.EMPEORA]
            < seg.PROXIMA_REVISION[Veredicto.ESTABLE])


def test_12_sin_afectados_pasa_a_VERIFICACION_no_a_cerrada(org_a):
    s = _situacion(org_a, afectados=0)

    seg.seguir(org_a)

    s.refresh_from_db()
    assert s.estado == S.EN_VERIFICACION
    assert s.estado != S.CERRADA
    assert s.cerrada_en is None


def test_13_requiere_humano_NO_cambia_el_estado(org_a):
    #  Marcarla 'en_atencion' afirmaria que alguien la esta atendiendo, y lo que
    #  pasa es lo contrario: hace falta que alguien lo haga.
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)

    seg.seguir(org_a)

    s.refresh_from_db()
    assert s.estado == S.DETECTADA
    assert s.estado != S.EN_ATENCION


def test_14_el_seguimiento_no_cierra_NUNCA(org_a):
    for afectados, riesgo in ((0, Riesgo.BAJO), (12, Riesgo.CRITICO),
                              (12, Riesgo.MEDIO)):
        S.objects.filter(org=org_a).delete()
        s = _situacion(org_a, afectados=afectados, riesgo=riesgo)
        seg.seguir(org_a)
        s.refresh_from_db()
        assert s.estado not in S.TERMINALES, (afectados, riesgo, s.estado)


def test_15_una_situacion_que_revienta_no_se_lleva_a_las_demas(org_a):
    _situacion(org_a, afectados=12, codigo="S-901",
               huella="afectacion_pon|pon:3/1/4")
    _situacion(org_a, afectados=8, codigo="S-902",
               huella="afectacion_pon|pon:3/2/7")

    llamadas = {"n": 0}
    real = seg.evaluar

    def una_revienta(situacion, **kw):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("explotó")
        return real(situacion, **kw)

    with mock.patch.object(seg, "evaluar", una_revienta):
        informe = seg.seguir(org_a)

    assert informe["errores"] == 1
    assert informe["evaluadas"] == 1, "la otra se evaluo igual"


# =============================================================================
#  §3  PROPUESTAS DESDE UNA SITUACION
# =============================================================================

def test_16_un_veredicto_que_pide_humano_deja_una_propuesta(org_a):
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)
    salida = seg.evaluar(s)

    propuesta = situaciones_propuestas.proponer(s, salida)

    assert propuesta is not None
    assert propuesta.origen_tipo == "situacion_operativa"
    assert propuesta.origen_id == str(s.id)
    #  SIEMPRE nivel 1: es una recomendacion, no hay camino de ejecucion detras.
    assert propuesta.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR
    assert propuesta.estado == P.PROPUESTA
    assert propuesta.evidencia, "la base exige evidencia"


def test_17_una_situacion_estable_no_propone_nada(org_a):
    #  Generar una recomendacion por ciclo convertiria la bandeja en ruido, que
    #  es la forma mas segura de que nadie la mire.
    ahora = timezone.now()
    s = _situacion(org_a, afectados=12, ahora=ahora)
    _medicion(s, 12, cuando=ahora - timezone.timedelta(minutes=5))
    _medicion(s, 12, cuando=ahora)

    assert situaciones_propuestas.proponer(s, seg.evaluar(s, ahora=ahora)) is None
    assert P.objects.filter(org=org_a).count() == 0


def test_18_la_misma_situacion_en_el_mismo_estado_no_propone_dos_veces(org_a):
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)
    salida = seg.evaluar(s)

    primera = situaciones_propuestas.proponer(s, salida)
    segunda = situaciones_propuestas.proponer(s, salida)

    assert primera is not None
    assert segunda is None, "la deduplicacion que ya existia tiene que aplicar"
    assert P.objects.filter(org=org_a).count() == 1


def test_19_un_veredicto_distinto_SI_es_una_recomendacion_nueva(org_a):
    #  La huella lleva el veredicto: si la situacion pasa de 'empeora' a
    #  'requiere_humano', la pregunta es otra y debe poder entrar.
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)

    situaciones_propuestas.proponer(s, {"veredicto": Veredicto.EMPEORA,
                                       "porque": "crece",
                                       "abonados_afectados": 60, "delta": 5})
    situaciones_propuestas.proponer(s, {"veredicto": Veredicto.REQUIERE_HUMANO,
                                       "porque": "critico",
                                       "abonados_afectados": 60, "delta": 0})

    assert P.objects.filter(org=org_a).count() == 2


def test_20_la_prioridad_la_calcula_el_codigo_y_explica_por_que(org_a):
    critica = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)
    p = situaciones_propuestas.proponer(critica, seg.evaluar(critica))

    assert p.prioridad >= 80
    #  Los componentes viajan como evidencia: la propuesta explica su numero en
    #  vez de mostrarlo.
    plano = json.dumps(p.evidencia)
    assert "riesgo critico" in plano


def test_21_verificar_es_importante_y_no_urgente(org_a):
    #  'puede_resolverse' baja la prioridad a proposito: si se deja un rato,
    #  nadie se queda sin servicio por eso.
    s = _situacion(org_a, afectados=0, riesgo=Riesgo.ALTO)
    p = situaciones_propuestas.proponer(s, seg.evaluar(s))

    assert p is not None
    assert p.prioridad < 70


def test_22_la_propuesta_queda_anotada_en_el_timeline(org_a):
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)

    p = situaciones_propuestas.proponer(s, seg.evaluar(s))

    evento = s.eventos.filter(tipo=TipoEvento.RECOMENDACION).last()
    assert evento is not None
    assert evento.datos["propuesta_id"] == str(p.id)


def test_23_la_propuesta_NO_reemplaza_a_la_situacion(org_a):
    s = _situacion(org_a, afectados=60, riesgo=Riesgo.CRITICO)

    situaciones_propuestas.proponer(s, seg.evaluar(s))

    s.refresh_from_db()
    #  Las dos siguen existiendo, y la situacion sigue viva.
    assert s.viva is True
    assert S.objects.filter(org=org_a).count() == 1
    assert P.objects.filter(org=org_a).count() == 1


def test_24_el_ciclo_completo_propone_cuando_corresponde(org_a):
    #  Integrado: el turno hace sondeo -> correlacion -> seguimiento -> propuesta.
    ahora = timezone.now()
    _captura(org_a, pons={"3/1/4": _pon(60, abonados=100, porcentaje=60.0)},
             ahora=ahora)

    informe = correlacion.correr(org_a, ahora=ahora)

    assert informe["creadas"] == 1
    #  El riesgo sale CRITICO por el porcentaje, asi que pide una persona.
    assert informe["seguimiento"]["piden_humano"] == 1
    assert informe["seguimiento"].get("propuestas") == 1
    assert P.objects.filter(org=org_a).count() == 1


# =============================================================================
#  §4  MEMORIA DE DECISIONES
# =============================================================================

def test_25_una_decision_guarda_quien_que_y_por_que(org_a, admin_profile):
    s = _situacion(org_a, afectados=12)
    ahora = timezone.now()

    d = DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="Verificar el PON",
        tipo=TipoDecision.ACEPTO, actor=admin_profile, decidida_en=ahora,
        motivo="coincide con lo que reporto el tecnico")

    assert d.resultado == ResultadoDecision.PENDIENTE
    assert d.actor_id == admin_profile.id


def test_26_una_decision_humana_SIN_actor_se_rechaza(org_a):
    #  Sin esto, cualquier camino podria registrar decisiones sin dueño y las
    #  metricas de aceptacion dejarian de significar algo.
    s = _situacion(org_a, afectados=12)

    with pytest.raises(IntegrityError):
        DecisionSupervisor.objects.create(
            org=org_a, situacion=s, recomendacion="x",
            tipo=TipoDecision.ACEPTO, actor=None,
            decidida_en=timezone.now())


def test_27_una_expiracion_SI_puede_no_tener_actor(org_a):
    #  Expirar no es una decision de nadie, y por eso se distingue: contarla como
    #  rechazo diria que alguien dijo no.
    s = _situacion(org_a, afectados=12)

    d = DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="x", tipo=TipoDecision.EXPIRO,
        actor=None, decidida_en=timezone.now())

    assert d.actor_id is None


def test_28_una_decision_sin_objeto_se_rechaza(org_a, admin_profile):
    with pytest.raises(IntegrityError):
        DecisionSupervisor.objects.create(
            org=org_a, situacion=None, propuesta=None, recomendacion="x",
            tipo=TipoDecision.ACEPTO, actor=admin_profile,
            decidida_en=timezone.now())


def test_29_un_resultado_cerrado_exige_decir_COMO_se_supo(org_a, admin_profile):
    s = _situacion(org_a, afectados=12)
    d = DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="x", tipo=TipoDecision.ACEPTO,
        actor=admin_profile, decidida_en=timezone.now())

    #  'funciono' sin evidencia es una opinion.
    with pytest.raises(IntegrityError):
        DecisionSupervisor.objects.filter(pk=d.pk).update(
            resultado=ResultadoDecision.FUNCIONO, resultado_evidencia="")


def test_30_una_decision_puede_quedar_en_NO_SE_PUEDE_SABER(org_a,
                                                           admin_profile):
    #  El caso en que ningun endpoint puede confirmar el efecto. Marcarlo asi
    #  evita contar como exito algo que nadie comprobo.
    s = _situacion(org_a, afectados=12)
    d = DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="x", tipo=TipoDecision.ACEPTO,
        actor=admin_profile, decidida_en=timezone.now(),
        resultado=ResultadoDecision.NO_SE_PUEDE_SABER)

    assert d.resultado not in ResultadoDecision.CERRADOS


def test_31_nada_convierte_una_decision_en_una_regla(org_a):
    #  La regla que esta tabla existe para hacer posible SIN romperla. Se afirma
    #  sobre el AST: ningun modulo del Supervisor lee 'DecisionSupervisor' para
    #  cambiar un umbral.
    import ast
    import inspect

    for modulo in (seg, situaciones_propuestas, correlacion):
        arbol = ast.parse(inspect.getsource(modulo))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol)
                    if isinstance(n, ast.Attribute)}
        assert "DecisionSupervisor" not in nombres, modulo.__name__


# =============================================================================
#  §5  GOBIERNO DE AUTONOMIA
# =============================================================================

def test_32_sin_fila_el_nivel_es_CERO(org_a):
    #  Fail-closed: el alcance se concede, no se hereda de un default.
    assert autonomia.nivel_configurado(org_a) == P.NIVEL_OBSERVAR


def test_33_cambiar_el_nivel_exige_persona_motivo_y_criterios(org_a,
                                                              admin_profile):
    for kw in ({"actor": None}, {"motivo": "  "}, {"criterios": "  "}):
        datos = {"actor": admin_profile, "motivo": "piloto",
                 "criterios": "30 dias en shadow sin falsos positivos"}
        datos.update(kw)
        with pytest.raises(autonomia.ErrorAutonomia):
            autonomia.cambiar(org_a, P.NIVEL_COORDINAR, **datos)

    assert NivelAutonomia.objects.filter(org=org_a).count() == 0


def test_34_el_Supervisor_no_puede_subirse_el_nivel(org_a):
    #  Sin actor no hay cambio. Es la barrera que impide que la IA se amplie el
    #  alcance, y esta en dos lugares.
    with pytest.raises(autonomia.ErrorAutonomia) as e:
        autonomia.cambiar(org_a, P.NIVEL_EJECUTAR_REVERSIBLE, actor=None,
                          motivo="x", criterios="y")
    assert "no puede ampliarse su propio alcance" in str(e.value)


def test_35_la_BASE_tambien_rechaza_un_cambio_sin_actor(org_a):
    #  La segunda barrera: sobrevive a un camino nuevo que se olvide de la
    #  primera.
    with pytest.raises(IntegrityError):
        NivelAutonomia.objects.create(
            org=org_a, nivel=3, actor=None, cambiado_en=timezone.now(),
            motivo="x", criterios="y")


def test_36_un_cambio_valido_queda_con_su_historia(org_a, admin_profile):
    fila = autonomia.cambiar(
        org_a, P.NIVEL_COORDINAR, actor=admin_profile,
        motivo="arranca el piloto de coordinacion",
        criterios="30 dias en shadow, 0 falsos positivos medidos")

    assert fila.nivel == P.NIVEL_COORDINAR
    assert fila.nivel_anterior == P.NIVEL_OBSERVAR
    assert autonomia.nivel_configurado(org_a) == P.NIVEL_COORDINAR
    h = autonomia.historial(org_a)
    assert len(h) == 1 and h[0]["motivo"].startswith("arranca")
    #  El historial NO lleva el nombre de la persona: puede terminar en un log.
    assert "actor_id" in h[0]
    assert all("nombre" not in k for k in h[0])


def test_37_el_historial_es_append_only_en_la_practica(org_a, admin_profile):
    autonomia.cambiar(org_a, 1, actor=admin_profile, motivo="a", criterios="a")
    autonomia.cambiar(org_a, 2, actor=admin_profile, motivo="b", criterios="b")
    autonomia.cambiar(org_a, 1, actor=admin_profile, motivo="c", criterios="c")

    #  Tres filas, y el vigente es el ultimo. No hay columna 'vigente' que
    #  obligue a dos escrituras por cambio.
    assert NivelAutonomia.objects.filter(org=org_a).count() == 3
    assert autonomia.nivel_configurado(org_a) == 1


def test_38_un_nivel_fuera_de_rango_se_rechaza(org_a, admin_profile):
    for nivel in (-1, 5, 99):
        with pytest.raises(autonomia.ErrorAutonomia):
            autonomia.cambiar(org_a, nivel, actor=admin_profile, motivo="x",
                              criterios="y")


def test_39_la_base_tambien_rechaza_un_nivel_fuera_de_rango(org_a,
                                                            admin_profile):
    with pytest.raises(IntegrityError):
        NivelAutonomia.objects.create(
            org=org_a, nivel=9, actor=admin_profile,
            cambiado_en=timezone.now(), motivo="x", criterios="y")


def test_40_una_persona_de_otra_empresa_no_gobierna_esta(org_a, org_b,
                                                         profile_b):
    with pytest.raises(autonomia.ErrorAutonomia) as e:
        autonomia.cambiar(org_a, 1, actor=profile_b, motivo="x", criterios="y")
    assert "pertenecer a esa empresa" in str(e.value)


# =============================================================================
#  §6  EL NIVEL EFECTIVO
# =============================================================================

def test_41_sin_interruptor_legible_observar_y_recomendar_siguen(org_a,
                                                                 admin_profile):
    #  En la base de pruebas NO existe 'asistente.interruptor_autonomia' -- la
    #  construye el ledger del motor, no Django. Asi que el interruptor es
    #  ILEGIBLE, y eso es exactamente el caso que importa medir.
    autonomia.cambiar(org_a, P.NIVEL_RECOMENDAR, actor=admin_profile,
                      motivo="x", criterios="y")

    estado = autonomia.nivel_efectivo(org_a)

    #  No se recorta: observar y recomendar NO son ejecutar, y dejar a la empresa
    #  sin diagnostico porque no se pudo leer un interruptor de EJECUCION seria
    #  quitarle justo lo que mas necesita.
    assert estado["efectivo"] == P.NIVEL_RECOMENDAR
    assert estado["interruptor_permite"] is False
    assert "no se pudo leer" in estado["motivo"]


def test_42_un_nivel_de_EJECUCION_si_se_recorta(org_a, admin_profile):
    autonomia.cambiar(org_a, P.NIVEL_EJECUTAR_REVERSIBLE, actor=admin_profile,
                      motivo="x", criterios="y")

    estado = autonomia.nivel_efectivo(org_a)

    #  Fail-closed: no poder leer el control es lo mismo que no tenerlo.
    assert estado["configurado"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert estado["efectivo"] == P.NIVEL_RECOMENDAR
    assert estado["recortado"] is True


def test_43_con_el_interruptor_activo_el_nivel_se_respeta(org_a, admin_profile):
    autonomia.cambiar(org_a, P.NIVEL_EJECUTAR_REVERSIBLE, actor=admin_profile,
                      motivo="x", criterios="y")

    with mock.patch.object(autonomia, "_interruptor_de",
                           return_value=(True, "")):
        estado = autonomia.nivel_efectivo(org_a)

    assert estado["efectivo"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert estado["recortado"] is False


def test_44_con_el_interruptor_detenido_se_recorta(org_a, admin_profile):
    autonomia.cambiar(org_a, P.NIVEL_EJECUTAR_REVERSIBLE, actor=admin_profile,
                      motivo="x", criterios="y")

    with mock.patch.object(autonomia, "_interruptor_de",
                           return_value=(False, "esta en 'detenido'")):
        estado = autonomia.nivel_efectivo(org_a)

    assert estado["efectivo"] == P.NIVEL_RECOMENDAR
    assert "detenido" in estado["motivo"]


def test_45_el_nivel_4_NUNCA_alcanza_por_configuracion(org_a, admin_profile):
    #  "Siempre una persona". Subir el nivel a 4 no habilita nada.
    autonomia.cambiar(org_a, P.NIVEL_CRITICO, actor=admin_profile, motivo="x",
                      criterios="y")

    with mock.patch.object(autonomia, "_interruptor_de",
                           return_value=(True, "")):
        r = autonomia.puede(org_a, P.NIVEL_CRITICO)

    assert r["puede"] is False
    assert "siempre la aprueba una persona" in r["motivo"]


def test_46_puede_explica_por_que_no(org_a):
    r = autonomia.puede(org_a, P.NIVEL_COORDINAR)

    assert r["puede"] is False
    #  Un booleano suelto no deja decir POR QUE no.
    assert "requiere nivel 2" in r["motivo"]


def test_47_lo_que_esta_dentro_del_alcance_se_permite(org_a, admin_profile):
    autonomia.cambiar(org_a, P.NIVEL_RECOMENDAR, actor=admin_profile,
                      motivo="x", criterios="y")

    assert autonomia.puede(org_a, P.NIVEL_OBSERVAR)["puede"] is True
    assert autonomia.puede(org_a, P.NIVEL_RECOMENDAR)["puede"] is True
    assert autonomia.puede(org_a, P.NIVEL_COORDINAR)["puede"] is False


# =============================================================================
#  §7  METRICAS
# =============================================================================

def test_48_las_metricas_cuentan_situaciones_y_su_riesgo(org_a):
    _situacion(org_a, afectados=12, codigo="S-801",
               huella="afectacion_pon|pon:3/1/4", riesgo=Riesgo.ALTO)
    _situacion(org_a, afectados=3, codigo="S-802",
               huella="afectacion_pon|pon:3/2/7", riesgo=Riesgo.MEDIO)

    m = indicadores.indicadores_situaciones(org_a)

    assert m["situaciones_vivas"]["valor"] == 2
    assert m["situaciones_por_riesgo_vivas"][Riesgo.ALTO]["valor"] == 1


def test_49_mide_las_situaciones_que_NADIE_habia_reportado(org_a):
    #  Es el numero que dice si el Supervisor ve antes que el cliente, que es su
    #  razon de ser.
    con = _situacion(org_a, afectados=12, codigo="S-801",
                     huella="afectacion_pon|pon:3/1/4")
    _situacion(org_a, afectados=5, codigo="S-802",
               huella="afectacion_pon|pon:3/2/7")
    caso = Case.objects.create(org=org_a, name="Sin internet", status="New",
                               priority="Normal")
    svc.agregar_afectados(con, [{"tipo": TipoAfectado.CASO,
                                 "identificador": str(caso.id)}])

    m = indicadores.indicadores_situaciones(org_a)

    assert m["situaciones_vivas_sin_ticket"]["valor"] == 1


def test_50_el_acierto_se_mide_solo_con_desenlace(org_a, admin_profile):
    #  Medir aceptaciones sin resultado mide obediencia, no acierto. Sin ninguna
    #  decision con desenlace, la tasa es NO_APLICA -- no 0%.
    s = _situacion(org_a, afectados=12)
    DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="x", tipo=TipoDecision.ACEPTO,
        actor=admin_profile, decidida_en=timezone.now())

    m = indicadores.indicadores_situaciones(org_a)

    assert m["tasa_aceptacion"]["valor"] == 1.0
    assert m["recomendaciones_que_funcionaron"]["valor"] is None
    assert m["decisiones_sin_desenlace"]["valor"] == 1


def test_51_una_expiracion_no_cuenta_como_rechazo(org_a, admin_profile):
    s = _situacion(org_a, afectados=12)
    DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="x", tipo=TipoDecision.ACEPTO,
        actor=admin_profile, decidida_en=timezone.now())
    DecisionSupervisor.objects.create(
        org=org_a, situacion=s, recomendacion="y", tipo=TipoDecision.EXPIRO,
        actor=None, decidida_en=timezone.now())

    m = indicadores.indicadores_situaciones(org_a)

    #  Una aceptada de UNA humana: la expirada no entra en el denominador.
    assert m["tasa_aceptacion"]["valor"] == 1.0
    assert m["decisiones_expiro"]["valor"] == 1


def test_52_las_metricas_son_LECTURA(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    antes = (S.objects.count(), P.objects.count(),
             DecisionSupervisor.objects.count())

    indicadores.indicadores_situaciones(org_a)
    indicadores.indicadores_situaciones(org_a)

    assert (S.objects.count(), P.objects.count(),
            DecisionSupervisor.objects.count()) == antes


# =============================================================================
#  §8  MULTI-TENANT
# =============================================================================

def test_53_el_nivel_de_una_empresa_no_afecta_a_la_otra(org_a, org_b,
                                                        admin_profile):
    autonomia.cambiar(org_a, P.NIVEL_COORDINAR, actor=admin_profile,
                      motivo="x", criterios="y")

    assert autonomia.nivel_configurado(org_a) == P.NIVEL_COORDINAR
    assert autonomia.nivel_configurado(org_b) == P.NIVEL_OBSERVAR


def test_54_el_seguimiento_de_una_empresa_no_toca_la_otra(org_a, org_b):
    from conftest import rls_org

    _situacion(org_a, afectados=12)
    with rls_org(org_b):
        sb = _situacion(org_b, afectados=12)
        antes = sb.proxima_revision_en

    seg.seguir(org_a)

    with rls_org(org_b):
        sb.refresh_from_db()
        assert sb.proxima_revision_en == antes


def test_55_las_metricas_no_cruzan_empresas(org_a, org_b):
    from conftest import rls_org

    with rls_org(org_b):
        _situacion(org_b, afectados=12)
        _situacion(org_b, afectados=5, codigo="S-802",
                   huella="afectacion_pon|pon:3/2/7")

    m = indicadores.indicadores_situaciones(org_a)

    assert m["situaciones_vivas"]["valor"] == 0


# =============================================================================
#  §9  LO QUE NO HACE
# =============================================================================

def test_56_el_ciclo_completo_no_toca_casos_ni_ordenes(org_a):
    _captura(org_a, pons={"3/1/4": _pon(60, abonados=100, porcentaje=60.0)})
    caso = Case.objects.create(org=org_a, name="Sin internet", status="New",
                               priority="Normal")
    antes = (caso.status, caso.updated_at, OrdenTrabajo.objects.count())

    correlacion.correr(org_a)
    correlacion.correr(org_a)

    caso.refresh_from_db()
    assert (caso.status, caso.updated_at, OrdenTrabajo.objects.count()) == antes


def test_57_ningun_modulo_nuevo_ejecuta_nada_externo(org_a):
    import ast
    import inspect

    PROHIBIDOS = {"requests", "post", "put", "patch", "delete", "reiniciar_ont",
                  "ejecutar_propuesta", "cerrar_caso"}
    for modulo in (seg, situaciones_propuestas):
        arbol = ast.parse(inspect.getsource(modulo))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol)
                    if isinstance(n, ast.Attribute)}
        colados = nombres & PROHIBIDOS
        assert not colados, (modulo.__name__, sorted(colados))


def test_58_el_shadow_mode_sigue_puesto(org_a):
    from operaciones import supervisor

    #  La bandera de fase que declara que no hay camino de ejecucion. Este bloque
    #  no la toca.
    assert supervisor.SHADOW_MODE is True


def test_59_el_modulo_de_autonomia_no_ejecuta_ni_habilita_nada(org_a):
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(autonomia))
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    #  Contesta "hasta donde" y registra quien lo decidio. No ejecuta.
    for prohibido in ("requests", "ejecutar_propuesta", "reiniciar_ont"):
        assert prohibido not in nombres, prohibido
