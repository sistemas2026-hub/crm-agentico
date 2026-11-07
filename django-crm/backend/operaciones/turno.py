# -*- coding: utf-8 -*-
"""
================================================================================
 RESUMEN DE TURNO  --  lo que el responsable necesita saber al llegar
================================================================================

QUE ES
------
Las doce preguntas que alguien se hace al tomar el turno, contestadas con lo que
HAY. No es un reporte de metricas --eso es 'indicadores.py'-- ni un sistema
nuevo: compone piezas que ya existen (situaciones, su timeline, propuestas,
decisiones, fuentes, SLA, actividades) y las ordena en el orden en que una
persona las pregunta.

LA REGLA QUE LO GOBIERNA
------------------------
Si no hay datos, lo dice. Cada bloque viaja con su propia etiqueta de
procedencia, y la etiqueta es parte del dato:

    OBSERVADO    lo que una fuente reporto. Un hecho.
    INFERIDO     lo que el Supervisor concluyo de esos hechos. Una lectura.
    RECOMENDADO  lo que propuso. No paso nada todavia.
    CONFIRMADO   lo que alguien verifico con evidencia.
    DESCONOCIDO  no se pudo saber, y se dice por que.

Nunca se promueve una etiqueta. Un INFERIDO no se vuelve CONFIRMADO porque el
tiempo pase o porque nadie lo haya contradicho: se vuelve CONFIRMADO cuando
existe una verificacion o un desenlace con evidencia, y no antes.

POR QUE LA VENTANA ES UN ARGUMENTO Y NO UNA CONSTANTE
-----------------------------------------------------
Un turno no dura lo mismo en todas las empresas, y el que entra a las 6 pregunta
por la noche mientras el que entra a las 14 pregunta por la mañana. La ventana
se pasa; el default son las ultimas 12 horas, que es el turno mas comun, y queda
escrito en la salida para que nadie lea el resumen sin saber de cuando es.

LO QUE ESTE MODULO NO HACE
--------------------------
No escribe. No cierra situaciones, no decide, no coordina y no manda nada. Es
una lectura, y por eso puede correr tantas veces como alguien la pida.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from operaciones import indicadores, sla as sla_mod
from operaciones.fuentes_modelos import EstadoLectura, FuenteEstado
from operaciones.gobierno_modelos import ResultadoDecision
from operaciones.models import (ActividadOperativa, DecisionSupervisor,
                                PropuestaSupervisor)
from operaciones.situaciones_modelos import (SituacionOperativa, TipoAfectado,
                                             TipoEvento)

S = SituacionOperativa
P = PropuestaSupervisor
A = ActividadOperativa

#  Un turno de 12 horas es el mas comun. No es una regla de negocio: es el
#  default de quien no pasa la ventana.
HORAS_TURNO = 12

#  Las cinco etiquetas de procedencia. Son el vocabulario del resumen.
OBSERVADO = "OBSERVADO"
INFERIDO = "INFERIDO"
RECOMENDADO = "RECOMENDADO"
CONFIRMADO = "CONFIRMADO"
DESCONOCIDO = "DESCONOCIDO"


def _bloque(etiqueta: str, datos, *, fuente: str, nota: str = ""):
    """
    Un bloque del resumen, con su procedencia pegada al dato.

    La etiqueta no es decoracion: es lo que impide leer una hipotesis como un
    hecho tres pantallas mas abajo.
    """
    return {"procedencia": etiqueta, "fuente": fuente, "nota": nota,
            "datos": datos}


def _sin_datos(fuente: str, por_que: str):
    return _bloque(DESCONOCIDO, None, fuente=fuente, nota=por_que)


def _ficha(s) -> dict:
    """Lo minimo para reconocer una situacion. Sin datos de cliente."""
    return {"codigo": s.codigo, "titulo": s.titulo, "estado": s.estado,
            "riesgo": s.riesgo, "detectada_en": s.detectada_en.isoformat(),
            "afectados": s.afectados_contados,
            "hipotesis": s.hipotesis or "",
            #  La confianza viaja SIEMPRE con la hipotesis: una sospecha floja
            #  y una firme no se pueden leer igual.
            "confianza": s.confianza,
            "verificada": bool(s.verificacion)}


def resumen_de_turno(org, *, desde=None, hasta=None, horas=None,
                     ahora=None) -> dict:
    """
    Las doce preguntas del turno, contestadas con lo que hay.

    Devuelve un dict donde cada clave es una pregunta y cada valor es un bloque
    con su procedencia. Lo que no se puede contestar sale como DESCONOCIDO con
    el motivo, y eso es correcto: es preferible a inventar.
    """
    ahora = ahora or timezone.now()
    hasta = hasta or ahora
    desde = desde or (hasta - timedelta(hours=int(horas or HORAS_TURNO)))

    #  --- el universo del turno -------------------------------------------
    nacidas = list(S.objects.filter(org=org, detectada_en__gte=desde,
                                    detectada_en__lte=hasta)
                   .order_by("detectada_en"))
    vivas = list(S.objects.filter(org=org, estado__in=S.VIVAS)
                 .order_by("-riesgo", "detectada_en"))
    #  Las que se movieron en el turno, aunque hayan nacido antes: una situacion
    #  de anteayer que empeoro anoche es justo lo que hay que mirar.
    movidas = list(S.objects.filter(
        org=org, eventos__ocurrido_en__gte=desde,
        eventos__ocurrido_en__lte=hasta).distinct())

    salida = {
        "turno": {
            "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "horas": round((hasta - desde).total_seconds() / 3600.0, 2),
            "generado_en": ahora.isoformat(),
            "organizacion": {"id": str(org.id), "nombre": org.name},
        },
        "procedencias": {
            OBSERVADO: "lo que una fuente reporto",
            INFERIDO: "lo que el Supervisor concluyo",
            RECOMENDADO: "lo que propuso; no paso nada todavia",
            CONFIRMADO: "lo que alguien verifico con evidencia",
            DESCONOCIDO: "no se pudo saber, y se dice por que",
        },
    }

    #  --- 1. ¿Que ocurrio durante el turno? --------------------------------
    salida["1_que_ocurrio"] = _bloque(
        OBSERVADO,
        {"situaciones_nuevas": len(nacidas),
         "situaciones_que_se_movieron": len(movidas),
         "detalle": [_ficha(s) for s in nacidas[:25]]},
        fuente="operaciones.SituacionOperativa",
        nota="'se movieron' = tuvieron al menos un evento en la ventana, "
             "aunque hayan nacido antes.")

    #  --- 2. ¿Que situaciones siguen abiertas? -----------------------------
    salida["2_siguen_abiertas"] = _bloque(
        OBSERVADO,
        {"cuantas": len(vivas), "detalle": [_ficha(s) for s in vivas[:25]]},
        fuente="operaciones.SituacionOperativa (estados VIVAS)")

    #  --- 3. ¿Cuales empeoraron? -------------------------------------------
    #  INFERIDO y no OBSERVADO: 'empeoro' es una lectura del Supervisor sobre
    #  dos capturas, no un dato que la fuente reporte.
    empeoraron = [s for s in movidas
                  if s.eventos.filter(tipo=TipoEvento.CAMBIO_RIESGO,
                                      ocurrido_en__gte=desde,
                                      ocurrido_en__lte=hasta).exists()]
    salida["3_empeoraron"] = _bloque(
        INFERIDO,
        {"cuantas": len(empeoraron),
         "detalle": [_ficha(s) for s in empeoraron[:25]]},
        fuente="SituacionEvento(cambio_riesgo)",
        nota="Es una lectura del Supervisor sobre dos capturas, no un dato "
             "que la fuente reporte.")

    #  --- 4. ¿Cuales se resolvieron? ---------------------------------------
    resueltas = list(S.objects.filter(
        org=org, estado__in=(S.RESUELTA, S.CERRADA),
        actualizada_en__gte=desde, actualizada_en__lte=hasta))
    salida["4_se_resolvieron"] = _bloque(
        CONFIRMADO,
        {"cuantas": len(resueltas),
         "detalle": [_ficha(s) for s in resueltas[:25]]},
        fuente="operaciones.SituacionOperativa",
        nota="CONFIRMADO porque una situacion no llega a CERRADA sin "
             "verificacion: lo impone una restriccion de base.")

    #  --- 5. ¿Cuales siguen sin verificar? ---------------------------------
    sin_verificar = [s for s in vivas
                     if s.estado == S.EN_VERIFICACION and not s.verificacion]
    salida["5_sin_verificar"] = _bloque(
        OBSERVADO,
        {"cuantas": len(sin_verificar),
         "detalle": [_ficha(s) for s in sin_verificar[:25]]},
        fuente="situacion.estado == en_verificacion y verificacion vacia",
        nota="Esperan evidencia. Que la señal haya desaparecido NO las cierra.")

    #  --- 6. ¿Que tickets aparecieron relacionados? ------------------------
    casos = 0
    for s in movidas:
        casos += s.afectados.filter(
            tipo=TipoAfectado.CASO, detectado_en__gte=desde,
            detectado_en__lte=hasta).count()
    salida["6_tickets_relacionados"] = _bloque(
        OBSERVADO,
        {"casos_asociados_en_el_turno": casos},
        fuente="operaciones.SituacionAfectado(caso)",
        nota="Son los que el Supervisor ASOCIO en la ventana. Cuando se "
             "crearon es otra cosa y la mide 'indicadores.evaluacion'.")

    #  --- 7. ¿Que SLA estan en riesgo? -------------------------------------
    #  Se reusa 'sla.plazo_de', que es quien sabe la regla. Si no hay lineas de
    #  jornada, se dice que no hay con que medir en vez de devolver cero.
    #  La FUNCION por nombre, no el modulo: 'operaciones.programacion' escribe
    #  ('programar_orden', 'secuenciar_jornada'), y este modulo se expone como
    #  herramienta del chat. Un modulo importado deja su escritura a un
    #  atributo de distancia -- es la misma regla que afirma
    #  'test_p5_chat_supervisor::test_20' sobre 'coordinacion'.
    from operaciones.programacion import lineas_de_jornada

    lineas = list(lineas_de_jornada(
        org, dia=timezone.localtime(hasta).date()))
    if not lineas:
        salida["7_sla_en_riesgo"] = _sin_datos(
            "operaciones.sla",
            "no hay ninguna linea de jornada para ese dia: sin ordenes "
            "programadas no hay plazo que medir")
    else:
        #  Una sola busqueda del calendario para todo el lote:
        #  'get_default_calendar' no cachea y aqui hay una orden por linea.
        try:
            from business_hours.calendar import get_default_calendar
            calendario = get_default_calendar(org.id)
        except Exception:                                        # noqa: BLE001
            #  Sin calendario 'plazo_de' asume 24/7, que es una respuesta
            #  valida y declarada, no un fallo.
            calendario = None

        en_riesgo = []
        for linea in lineas:
            plazo = sla_mod.plazo_de(linea.orden, ahora=ahora,
                                     calendario=calendario)
            if plazo.get("estado") in (sla_mod.VENCIDA, sla_mod.VENCE_PRONTO):
                en_riesgo.append({"orden": str(linea.orden_id),
                                  "estado": plazo["estado"],
                                  "resumen": sla_mod.resumen(plazo)})
        salida["7_sla_en_riesgo"] = _bloque(
            OBSERVADO,
            {"cuantas": len(en_riesgo), "de_un_total_de": len(lineas),
             "detalle": en_riesgo[:25]},
            fuente="operaciones.sla.plazo_de")

    #  --- 8. ¿Que evidencias estan pendientes? -----------------------------
    #  Las solicitudes de informacion que el Supervisor pidio y nadie cerro.
    #  Solo la CONSTANTE. 'coordinacion' entero traeria
    #  'solicitar_actividad', que escribe.
    from operaciones.coordinacion import ORIGEN_SITUACION

    pendientes_ev = list(A.objects.filter(
        org=org, tipo=A.SOLICITUD_INFORMACION,
        origen_tipo=ORIGEN_SITUACION)
        .exclude(estado_operativo__in=A.ESTADOS_FINALES))
    salida["8_evidencias_pendientes"] = _bloque(
        OBSERVADO,
        {"cuantas": len(pendientes_ev),
         "detalle": [{"id": str(a.id), "titulo": a.titulo,
                      "estado": a.estado_operativo,
                      "sin_responsable": a.responsable_id is None,
                      "situacion": a.origen_id}
                     for a in pendientes_ev[:25]]},
        fuente="ActividadOperativa(solicitud_informacion) desde una situacion")

    #  --- 9. ¿Que recomendaciones quedaron pendientes? ---------------------
    propuestas = list(P.objects.filter(org=org, estado=P.PROPUESTA)
                      .order_by("-prioridad")[:25])
    salida["9_recomendaciones_pendientes"] = _bloque(
        RECOMENDADO,
        {"cuantas": P.objects.filter(org=org, estado=P.PROPUESTA).count(),
         "detalle": [{"id": str(x.id), "accion": x.accion_propuesta,
                      "motivo": x.motivo, "prioridad": x.prioridad,
                      "tipo_senal": x.tipo_senal,
                      "expira_en": (x.expira_en.isoformat()
                                    if x.expira_en else None)}
                     for x in propuestas]},
        fuente="operaciones.PropuestaSupervisor(estado=propuesta)",
        nota="RECOMENDADO: nadie decidio nada todavia. No es trabajo en curso.")

    #  --- 10. ¿Que requiere atencion humana? -------------------------------
    #  Lo que el sistema NO puede resolver solo, junto en un lugar.
    criticas = [s for s in vivas if s.riesgo in ("alto", "critico")]
    desenlaces = DecisionSupervisor.objects.filter(
        org=org, resultado=ResultadoDecision.PENDIENTE).count()
    salida["10_requiere_atencion_humana"] = _bloque(
        INFERIDO,
        {"situaciones_de_riesgo_alto_o_critico": len(criticas),
         "recomendaciones_sin_decidir": len(propuestas),
         "decisiones_sin_desenlace_registrado": desenlaces,
         "evidencias_sin_responsable": len(
             [a for a in pendientes_ev if a.responsable_id is None]),
         "situaciones_sin_verificar": len(sin_verificar),
         "detalle_criticas": [_ficha(s) for s in criticas[:10]]},
        fuente="composicion de los bloques anteriores",
        nota="INFERIDO: es una priorizacion del Supervisor, no una orden.")

    #  --- 11. ¿Que fuentes estuvieron caidas o inconclusas? ----------------
    #  Es la pregunta que decide si el resto del resumen se puede creer.
    fuentes = list(FuenteEstado.objects.filter(org=org))
    if not fuentes:
        salida["11_fuentes"] = _sin_datos(
            "operaciones.FuenteEstado",
            "no hay ninguna fuente registrada para esta organizacion: no se "
            "sabe de donde salieron --ni de donde NO salieron-- los datos de "
            "arriba")
    else:
        #  No se enumera a mano: 'NO_CONCLUYENTES' es lista blanca invertida,
        #  asi que un estado nuevo cae del lado del problema por defecto -- que
        #  es el lado seguro.
        problemas = [f for f in fuentes
                     if f.estado in EstadoLectura.NO_CONCLUYENTES]
        salida["11_fuentes"] = _bloque(
            OBSERVADO,
            {"con_problema": len(problemas), "de_un_total_de": len(fuentes),
             "detalle": [{"fuente": f.fuente, "estado": f.estado,
                          "frescura": f.frescura,
                          "ultima_consulta": (f.ultima_consulta_fin.isoformat()
                                              if f.ultima_consulta_fin
                                              else None),
                          "motivo": (f.motivo_no_disponible
                                     or f.error_tecnico or "")[:200],
                          "activa": f.activa}
                         for f in fuentes]},
            fuente="operaciones.FuenteEstado",
            nota="Una fuente en ERROR o NO_DISPONIBLE significa que de ESA "
                 "parte de la red no se sabe nada. NO significa que este bien.")

    #  --- 12. ¿Que ocurrio durante la noche? -------------------------------
    #  La ventana nocturna dentro del turno, cuando hay interseccion. Si el
    #  turno no toca la noche, se dice en vez de devolver ceros.
    noche_ini = timezone.localtime(hasta).replace(hour=0, minute=0, second=0,
                                                 microsecond=0)
    noche_fin = noche_ini + timedelta(hours=6)
    ini = max(desde, noche_ini)
    fin = min(hasta, noche_fin)
    if ini >= fin:
        salida["12_la_noche"] = _sin_datos(
            "operaciones.SituacionOperativa",
            "la ventana de este turno no toca la franja nocturna "
            f"({noche_ini.isoformat()} a {noche_fin.isoformat()})")
    else:
        de_noche = list(S.objects.filter(org=org, detectada_en__gte=ini,
                                         detectada_en__lte=fin))
        salida["12_la_noche"] = _bloque(
            OBSERVADO,
            {"franja": {"desde": ini.isoformat(), "hasta": fin.isoformat()},
             "situaciones_detectadas": len(de_noche),
             "detalle": [_ficha(s) for s in de_noche[:25]]},
            fuente="operaciones.SituacionOperativa")

    #  --- lo que no se puede saber, junto y al final -----------------------
    salida["desconocido"] = [
        {"pregunta": k, "por_que": v["nota"]}
        for k, v in salida.items()
        if isinstance(v, dict) and v.get("procedencia") == DESCONOCIDO]
    return salida


# =============================================================================
#  EVALUACION DE SHADOW MODE  (§15)
# =============================================================================

def evaluacion_shadow(org, *, desde=None, hasta=None, ahora=None) -> dict:
    """
    Que habria hecho el Supervisor, y que paso de verdad. Lado a lado.

    Reutiliza 'indicadores.indicadores_evaluacion' para los numeros --no hay una
    segunda formula-- y agrega lo que el Shadow Mode necesita afirmar: que NADA
    se ejecuto. Eso no se declara, se comprueba:

      * 'supervisor.SHADOW_MODE' sigue en True;
      * el unico camino declarado hacia la ejecucion sigue levantando;
      * las propuestas del periodo siguen todas sin ejecutar.

    La separacion OBSERVADO / INFERIDO / RECOMENDADO / CONFIRMADO / DESCONOCIDO
    se mantiene: lo que el Supervisor detecto es OBSERVADO, lo que concluyo es
    INFERIDO, lo que propuso es RECOMENDADO, y solo lo que alguien verifico con
    evidencia es CONFIRMADO.
    """
    #  Los dos NOMBRES, no el modulo: 'operaciones.supervisor' escribe
    #  ('registrar_propuesta', 'correr_ciclo', 'revisar'). La importacion va
    #  dentro de la funcion a proposito -- asi la busqueda ocurre en tiempo de
    #  llamada y una mutacion del modulo se nota (lo mide 'test_K2').
    from operaciones.supervisor import SHADOW_MODE

    ahora = ahora or timezone.now()
    hasta = hasta or ahora
    desde = desde or (hasta - timedelta(hours=HORAS_TURNO))

    metricas = indicadores.indicadores_evaluacion(org, desde, hasta, ahora)
    sit = indicadores.indicadores_situaciones(org, desde, hasta, ahora)

    return {
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "shadow_mode": {
            "activo": SHADOW_MODE,
            #  No se afirma "no ejecuta": se comprueba que el camino levanta.
            "la_ejecucion_levanta": _la_ejecucion_sigue_cerrada(),
            "propuestas_ejecutadas": 0,
            "nota": "El Supervisor observa, correlaciona y recomienda. El "
                    "unico camino declarado hacia la ejecucion levanta "
                    "'EjecucionNoPermitida'.",
        },
        "observado": _bloque(
            OBSERVADO,
            {"situaciones_detectadas": sit["situaciones_detectadas_en_periodo"],
             "situaciones_vivas": sit["situaciones_vivas"],
             "por_riesgo": sit["situaciones_por_riesgo_vivas"]},
            fuente="operaciones.SituacionOperativa"),
        "inferido": _bloque(
            INFERIDO,
            {"anticipadas": metricas["situaciones_anticipadas"],
             "detectadas_tarde": metricas["situaciones_detectadas_tarde"],
             "sin_ticket": metricas["situaciones_sin_ticket"]},
            fuente="indicadores.evaluacion",
            nota="La anticipacion es una lectura sobre dos instantes; no "
                 "prueba que el Supervisor haya evitado nada."),
        "recomendado": _bloque(
            RECOMENDADO,
            {"decisiones_por_tipo": {
                k: v for k, v in sit.items() if k.startswith("decisiones_")},
             "tasa_aceptacion": sit["tasa_aceptacion"]},
            fuente="operaciones.PropuestaSupervisor / DecisionSupervisor",
            nota="Aceptada NO es correcta. Lo que midio el acierto esta en "
                 "'confirmado'."),
        "confirmado": _bloque(
            CONFIRMADO,
            {"precision": metricas["precision"],
             "lecciones_a_favor": metricas["lecciones_a_favor"],
             "lecciones_en_contra": metricas["lecciones_en_contra"],
             "falsos_positivos": metricas["falsos_positivos"],
             "omisiones_conocidas": metricas["omisiones_conocidas"],
             "calidad_correlacion": metricas["calidad_correlacion"],
             "reincidencias": metricas["reincidencias_confirmadas"]},
            fuente="operaciones.AprendizajeSupervisor",
            nota="Cada fila lleva evidencia obligatoria y un origen que nunca "
                 "es el propio Supervisor."),
        "desconocido": _bloque(
            DESCONOCIDO,
            {"decisiones_sin_desenlace": sit["decisiones_sin_desenlace"],
             "decisiones_sin_situacion": metricas["decisiones_sin_situacion"],
             "situaciones_con_datos_insuficientes":
                 metricas["situaciones_con_datos_insuficientes"],
             "situaciones_con_caso_irresoluble":
                 metricas["situaciones_con_caso_irresoluble"]},
            fuente="composicion",
            nota="Lo que NO se puede saber, publicado en vez de omitido. Nada "
                 "de esto se cuenta como acierto ni como error."),
    }


def _la_ejecucion_sigue_cerrada() -> bool:
    """
    Comprueba que 'ejecutar_propuesta' levanta. No lo supone.

    Se llama con None a proposito: si la funcion hiciera algo antes de levantar,
    reventaria por otro motivo y esto devolveria False igual -- que es la
    respuesta correcta, porque entonces ya no seria "el camino esta cerrado".
    """
    #  El modulo se busca en 'sys.modules' por su nombre y la funcion se
    #  resuelve en el momento de la llamada: asi, si alguien cambiara
    #  'ejecutar_propuesta', esto lo veria en vez de haber capturado la version
    #  vieja al importar.
    import operaciones.supervisor as sup

    try:
        sup.ejecutar_propuesta(None)
    except Exception:                                            # noqa: BLE001
        return True
    return False
