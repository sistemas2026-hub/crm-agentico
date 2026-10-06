# -*- coding: utf-8 -*-
"""
================================================================================
 INDICADORES Y REPORTES OPERATIVOS  --  paso M11
================================================================================

Una capa de LECTURA y CALCULO. No hay tabla de hechos, no hay data warehouse,
no hay entidad KPI y no hay segunda fuente de verdad: cada numero se deriva de
la fila que lo sostiene, en el momento en que se pregunta.

LO QUE NO SE RECALCULA
----------------------
'cases/analytics.py' ya computa FRT, MTTR, backlog, agentes y SLA de casos, y
alimenta un dashboard. M11 NO lo reescribe: lo LLAMA y le agrega el sobre de
cobertura que le falta. Duplicar ese calculo crearia dos verdades sobre el
mismo numero.

Lo mismo con el resto: la capacidad la calcula 'operaciones.capacidad' (M03-G),
el vencimiento lo clasifica 'operaciones.actividades' (M02) y las senales las
produce 'operaciones.supervisor' (M09). Aqui se agrega, no se reimplementa.

TRES ESTADOS, Y EL TERCERO NO ES DECORACION
-------------------------------------------
    VALIDO               el numero representa lo que dice representar
    DATOS_INSUFICIENTES  hay un valor, pero NO sobre toda la poblacion
    NO_APLICA            no hay poblacion sobre la cual calcular

POR QUE NO HAY UMBRAL DE COBERTURA
----------------------------------
Seria un numero inventado, y esta prohibido inventarlo. La regla no necesita
uno:

    un CONTEO sobre un campo obligatorio siempre es VALIDO -- no hay nada que
    pueda faltar;

    una DERIVADA (promedio, porcentaje) sobre un campo opcional es
    DATOS_INSUFICIENTES en cuanto la cobertura baja del 100%, porque cada
    valor ausente desplaza el promedio en una direccion que nadie puede saber.

El valor igual se devuelve, pero etiquetado: 'valor' con su 'cobertura' al
lado dice mas que un promedio limpio que no representa a nadie. Lo que no se
hace nunca es imputar, rellenar ni suponer.

Y 0 poblacion no es 0%: es NO_APLICA. Un "0% de incumplimiento" sobre cero
casos parece un logro y no significa nada.

LO QUE ESTE MODULO NO HACE
--------------------------
No escribe una sola fila. No crea actividad de negocio, no toca
PropuestaSupervisor, no ejecuta nada y no llama a ningun sistema externo.
Generar un reporte no deja rastro operativo -- y por eso el contador de
common.Activity no sirve para probar que M11 no toco nada: lo que sirve es que
no importa un solo servicio de escritura.
================================================================================
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from campo.models import AsignacionTrabajo, OrdenTrabajo
from cases.models import Case
from operaciones import actividades as m02
from operaciones import capacidad as m03g
from operaciones import supervisor as m09
from operaciones.models import (ActividadOperativa, NovedadOperativa,
                                ProgramacionOrden, ProgramacionSemanal,
                                PropuestaSupervisor, VALIDACION_PENDIENTE)

A = ActividadOperativa
P = PropuestaSupervisor

VALIDO = "VALIDO"
DATOS_INSUFICIENTES = "DATOS_INSUFICIENTES"
NO_APLICA = "NO_APLICA"

#  Ventana por defecto de un reporte. NO es un umbral de negocio: es cuanto
#  mira hacia atras un "resumen diario" si nadie pide otra cosa.
DIAS_VENTANA = 7


# ==============================================================================
#  EL SOBRE
# ==============================================================================

def conteo(valor: int, fuente: str, periodo=None) -> dict:
    """
    Un CONTEO sobre un campo obligatorio. Siempre VALIDO: no hay nada que
    pueda faltar, asi que no hay cobertura que declarar mas alla del 100%.
    """
    return {"estado": VALIDO, "valor": valor, "unidad": "conteo",
            "denominador": valor, "con_dato": valor, "cobertura": 1.0,
            "periodo": periodo, "fuente": fuente, "motivo": ""}


def derivada(valor, *, con_dato: int, denominador: int, unidad: str,
             fuente: str, periodo=None) -> dict:
    """
    Una DERIVADA sobre un campo opcional. El estado lo decide la cobertura, no
    un umbral: si falta un solo valor, el numero ya no representa al conjunto.
    """
    if denominador == 0:
        return {"estado": NO_APLICA, "valor": None, "unidad": unidad,
                "denominador": 0, "con_dato": 0, "cobertura": None,
                "periodo": periodo, "fuente": fuente,
                "motivo": "No hay poblacion en el periodo: 0 no es un "
                          "resultado, es la ausencia de uno."}
    cobertura = con_dato / denominador
    if con_dato < denominador:
        return {
            "estado": DATOS_INSUFICIENTES, "valor": valor, "unidad": unidad,
            "denominador": denominador, "con_dato": con_dato,
            "cobertura": round(cobertura, 4), "periodo": periodo,
            "fuente": fuente,
            "motivo": (f"El valor se calculo sobre {con_dato} de "
                       f"{denominador}. Los que faltan pueden desplazarlo en "
                       f"cualquier direccion; no se imputa ninguno."),
        }
    return {"estado": VALIDO, "valor": valor, "unidad": unidad,
            "denominador": denominador, "con_dato": con_dato,
            "cobertura": 1.0, "periodo": periodo, "fuente": fuente,
            "motivo": ""}


def _periodo(desde, hasta) -> dict:
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat()}


def _ventana(desde=None, hasta=None, ahora=None):
    ahora = ahora or timezone.now()
    hasta = hasta or ahora
    desde = desde or (hasta - timedelta(days=DIAS_VENTANA))
    return desde, hasta, ahora


# ==============================================================================
#  B.2  --  ACTIVIDADES  (M02)
# ==============================================================================

def indicadores_actividades(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    Todo conteo, todo sobre campos obligatorios: no hay cobertura parcial que
    declarar. Una actividad siempre tiene estado.
    """
    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    per = _periodo(desde, hasta)
    fuente = "operaciones.ActividadOperativa"

    qs = A.objects.filter(org=org)
    por_estado = dict(qs.values_list("estado_operativo")
                      .annotate(n=Count("id")).values_list("estado_operativo", "n"))
    abiertas = qs.exclude(estado_operativo__in=A.ESTADOS_FINALES)

    #  'vencida' usa la MISMA definicion que M02 y que el detector de M09: la
    #  fecha paso y no esta cerrada. No se redefine aca.
    vencidas = abiertas.filter(vence_en__lt=ahora).count()

    con_dependencia = 0
    for a in abiertas.select_related("depende_de").only(
            "id", "depende_de", "estado_operativo"):
        if a.bloqueada_por_dependencia:
            con_dependencia += 1

    salida = {
        "total": conteo(qs.count(), fuente, per),
        "abiertas": conteo(abiertas.count(), fuente, per),
        "vencidas": conteo(vencidas, fuente, per),
        "sin_responsable": conteo(
            abiertas.filter(responsable__isnull=True).count(), fuente, per),
        "con_dependencia_pendiente": conteo(con_dependencia, fuente, per),
        "validacion_pendiente": conteo(
            qs.filter(estado_validacion=VALIDACION_PENDIENTE).count(),
            fuente, per),
    }
    for estado, _etiqueta in A.ESTADOS_OPERATIVOS:
        salida[f"estado_{estado}"] = conteo(por_estado.get(estado, 0), fuente, per)

    #  Por tipo: el catalogo entero, incluidos los tipos en cero. Un tipo que
    #  no aparece se lee como "no existe", y no es lo mismo que "hay cero".
    por_tipo = dict(qs.values_list("tipo").annotate(n=Count("id"))
                    .values_list("tipo", "n"))
    salida["por_tipo"] = {t: conteo(por_tipo.get(t, 0), fuente, per)
                          for t, _e in A.TIPOS}
    return salida


# ==============================================================================
#  B.4  --  COMPROMISOS  (M02, subconjunto)
# ==============================================================================

def indicadores_compromisos(org, ahora=None, ventana_horas=None) -> dict:
    """
    Los compromisos, clasificados con la MISMA funcion que usa M02
    ('clasificar_vencimiento'). La ventana de "vence pronto" es explicita y por
    defecto la que ya usa el detector de M09 -- no un valor nuevo.
    """
    ahora = ahora or timezone.now()
    fuente = "operaciones.ActividadOperativa (tipo=compromiso)"
    qs = list(A.objects.filter(org=org, tipo=A.COMPROMISO)
              .select_related("depende_de"))

    por_vencimiento = {}
    for c in qs:
        k = m02.clasificar_vencimiento(c, ahora, ventana_horas)
        por_vencimiento[k] = por_vencimiento.get(k, 0) + 1

    abiertos = [c for c in qs if c.estado_operativo not in A.ESTADOS_FINALES]
    return {
        "total": conteo(len(qs), fuente),
        "abiertos": conteo(len(abiertos), fuente),
        "vencidos": conteo(por_vencimiento.get(m02.VENCIDA, 0), fuente),
        "por_vencer": conteo(por_vencimiento.get(m02.VENCE_PRONTO, 0), fuente),
        "a_tiempo": conteo(por_vencimiento.get(m02.A_TIEMPO, 0), fuente),
        #  SIN fecha comprometida no es lo mismo que "a tiempo": es que nadie
        #  declaro una, y un compromiso sin fecha es legitimo (M02).
        "sin_fecha": conteo(por_vencimiento.get(m02.SIN_VENCIMIENTO, 0), fuente),
        "bloqueados": conteo(
            sum(1 for c in abiertos if c.estado_operativo == A.BLOQUEADA),
            fuente),
        "en_espera": conteo(
            sum(1 for c in abiertos if c.estado_operativo == A.EN_ESPERA),
            fuente),
        "validacion_pendiente": conteo(
            sum(1 for c in qs if c.estado_validacion == VALIDACION_PENDIENTE),
            fuente),
        "ventana_por_vencer_horas": (
            ventana_horas if ventana_horas is not None
            else m02._ventana_por_defecto()),
    }


# ==============================================================================
#  B.3  --  PROGRAMACION Y CAPACIDAD  (M03 + M03-G)
# ==============================================================================

def indicadores_programacion(org, ahora=None, dias=None) -> dict:
    """
    La programacion y lo que se sabe de la capacidad.

    La capacidad NO se recalcula: la da 'operaciones.capacidad' (M03-G), con su
    regla de INDETERMINADO intacta. Y la sobrecarga solo se cuenta donde es
    matematicamente defendible -- la carga conocida ya no cabe.
    """
    ahora = ahora or timezone.now()
    hoy = timezone.localtime(ahora).date()
    dias = dias if dias is not None else DIAS_VENTANA
    fin = hoy + timedelta(days=dias)
    fuente = "campo.OrdenTrabajo + operaciones.Programacion*"

    ordenes = OrdenTrabajo.objects.filter(org=org)
    abiertas = ordenes.exclude(estado_operativo__in=(
        OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA))

    lineas = ProgramacionOrden.objects.filter(
        org=org, estado__in=(ProgramacionOrden.PLANIFICADA,
                             ProgramacionOrden.CONFIRMADA))
    planes = ProgramacionSemanal.objects.filter(org=org)

    #  Sin principal: se lee la MISMA propiedad que usa todo el modulo.
    sin_principal = sum(
        1 for o in abiertas.prefetch_related("asignaciones")
        if o.asignaciones.exists() and o.tecnico_principal is None)
    sin_cuadrilla = sum(
        1 for o in abiertas.prefetch_related("asignaciones")
        if not o.asignaciones.exists())

    #  Capacidad: se pregunta a M03-G dia por dia, sobre los dias que TIENEN
    #  trabajo. Un dia sin trabajo no tiene capacidad "libre": no se evalua.
    dias_con_trabajo = sorted(set(
        lineas.filter(dia__gte=hoy, dia__lte=fin)
        .values_list("dia", flat=True)))
    sobrecargadas, no_determinables, evaluadas = [], [], 0
    for dia in dias_con_trabajo:
        jornada = m03g.capacidad_de_jornada(org, dia)
        for fila in jornada["resultados"]:
            evaluadas += 1
            if fila["riesgo"] == m03g.SOBRECARGA:
                sobrecargadas.append({
                    "dia": str(dia), "persona": fila["profile"]["nombre"],
                    "capacidad_minutos": fila["capacidad_minutos"],
                    "carga_minutos": fila["carga"]["minutos_conocidos"],
                    "exceso_minutos": fila["exceso_minutos"],
                    "es_cota_inferior": fila["carga"]["es_cota_inferior"]})
            elif fila["resultado"] == m03g.NO_DETERMINABLE:
                no_determinables.append({
                    "dia": str(dia), "persona": fila["profile"]["nombre"],
                    "motivo": fila["jornada"]["motivo"]})

    return {
        "ordenes_total": conteo(ordenes.count(), fuente),
        "ordenes_abiertas": conteo(abiertas.count(), fuente),
        "ordenes_programadas": conteo(
            abiertas.filter(programada_para__isnull=False).count(), fuente),
        "ordenes_sin_programar": conteo(
            abiertas.filter(programada_para__isnull=True).count(), fuente),
        "lineas_vigentes": conteo(lineas.count(), fuente),
        "planes_publicados": conteo(
            planes.filter(estado=ProgramacionSemanal.PUBLICADA).count(), fuente),
        "planes_borrador": conteo(
            planes.filter(estado=ProgramacionSemanal.BORRADOR).count(), fuente),
        "asignaciones": conteo(
            AsignacionTrabajo.objects.filter(orden__org=org).count(), fuente),
        "ordenes_sin_cuadrilla": conteo(sin_cuadrilla, fuente),
        "ordenes_con_gente_sin_principal": conteo(sin_principal, fuente),
        "novedades": conteo(
            NovedadOperativa.objects.filter(org=org).count(),
            "operaciones.NovedadOperativa"),
        "capacidad": {
            "horizonte_dias": dias,
            "jornadas_evaluadas": evaluadas,
            "jornadas_sobrecargadas": sobrecargadas,
            "jornadas_no_determinables": no_determinables,
            "fuente": "operaciones.capacidad (M03-G)",
            "nota": ("La sobrecarga solo se cuenta donde la carga CONOCIDA ya "
                     "no cabe. Donde faltan duraciones no se afirma que quepa: "
                     "INDETERMINADO no es cero."),
        },
    }


# ==============================================================================
#  B.5  --  SUPERVISOR IA  (M09)
# ==============================================================================

def indicadores_supervisor(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    Lo que el Supervisor detecto y propuso. Es LECTURA: no corre el ciclo ni
    crea propuestas -- preguntar por un indicador no debe producir trabajo.
    """
    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    per = _periodo(desde, hasta)
    fuente = "operaciones.PropuestaSupervisor"

    qs = P.objects.filter(org=org)
    en_ventana = qs.filter(created_at__gte=desde, created_at__lt=hasta)
    por_estado = dict(qs.values_list("estado").annotate(n=Count("id"))
                      .values_list("estado", "n"))
    por_senal = dict(en_ventana.values_list("tipo_senal").annotate(n=Count("id"))
                     .values_list("tipo_senal", "n"))

    #  Las senales VIGENTES se detectan sin escribir nada.
    senales = m09.detectar(org, ahora)
    vivas = {}
    for s in senales:
        vivas[s.tipo] = vivas.get(s.tipo, 0) + 1

    salida = {
        "senales_vigentes": conteo(len(senales), "operaciones.supervisor.detectar"),
        "senales_por_tipo": {t: conteo(n, "operaciones.supervisor.detectar")
                             for t, n in sorted(vivas.items())},
        "propuestas_total": conteo(qs.count(), fuente),
        "propuestas_en_periodo": conteo(en_ventana.count(), fuente, per),
        "propuestas_por_tipo_senal": {
            t: conteo(por_senal.get(t, 0), fuente, per) for t, _e in P.TIPOS_SENAL},
    }
    for estado, _etiqueta in P.ESTADOS:
        salida[f"propuestas_{estado}"] = conteo(por_estado.get(estado, 0), fuente)

    #  Tasa de revision: DERIVADA. Si no hubo propuestas en el periodo es
    #  NO_APLICA, no "0% revisado".
    total = en_ventana.count()
    revisadas = en_ventana.filter(
        estado__in=P.ESTADOS_REVISADOS).count() if total else 0
    salida["tasa_revision"] = derivada(
        round(revisadas / total, 4) if total else None,
        con_dato=total, denominador=total, unidad="proporcion",
        fuente=fuente, periodo=per)
    if total:
        salida["tasa_revision"]["valor"] = round(revisadas / total, 4)
        salida["tasa_revision"]["revisadas"] = revisadas
    return salida


# ==============================================================================
#  B.0b  --  SITUACIONES OPERATIVAS Y DECISIONES  (paso P4)
# ==============================================================================

def indicadores_situaciones(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    Como va el Supervisor con las situaciones, y si sus recomendaciones sirvieron.

    POR QUE AQUI Y NO EN UN MODULO DE METRICAS NUEVO
    ------------------------------------------------
    Porque este archivo ya tiene las piezas: 'conteo' para un numero con su
    fuente, 'derivada' para una proporcion que sabe decir NO_APLICA en vez de
    inventar un 0%, y la ventana con su periodo. Un modulo paralelo habria
    duplicado las cuatro, y despues dos tableros mostrarian numeros distintos.

    LA METRICA QUE DE VERDAD IMPORTA ES LA ULTIMA
    ---------------------------------------------
    'recomendaciones_que_funcionaron' se calcula SOLO sobre las decisiones que ya
    tienen desenlace registrado. Medir "aceptadas" sin el resultado mide
    obediencia, no acierto -- y una tasa de aceptacion alta con resultados
    desconocidos es exactamente la cifra que haria confiar en algo sin motivo.

    Y ES LECTURA: no corre el ciclo, no evalua seguimiento y no crea nada.
    Preguntar por un indicador no debe producir trabajo.
    """
    from operaciones.gobierno_modelos import (DecisionSupervisor,
                                              ResultadoDecision, TipoDecision)
    from operaciones.situaciones_modelos import SituacionOperativa

    S = SituacionOperativa
    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    per = _periodo(desde, hasta)
    f_sit = "operaciones.SituacionOperativa"
    f_dec = "operaciones.DecisionSupervisor"

    sit = S.objects.filter(org=org)
    en_ventana = sit.filter(detectada_en__gte=desde, detectada_en__lt=hasta)
    por_estado = dict(sit.values_list("estado").annotate(n=Count("id"))
                      .values_list("estado", "n"))
    por_riesgo = dict(sit.filter(estado__in=S.VIVAS).values_list("riesgo")
                      .annotate(n=Count("id")).values_list("riesgo", "n"))

    salida = {
        "situaciones_vivas": conteo(sit.filter(estado__in=S.VIVAS).count(),
                                    f_sit),
        "situaciones_detectadas_en_periodo": conteo(en_ventana.count(), f_sit,
                                                    per),
        "situaciones_por_riesgo_vivas": {
            r: conteo(n, f_sit) for r, n in sorted(por_riesgo.items())},
        #  Las que NADIE habia reportado todavia: situaciones vivas sin un solo
        #  caso asociado. Es el numero que mide si el Supervisor esta viendo antes
        #  que el cliente, que es su razon de ser.
        "situaciones_vivas_sin_ticket": conteo(
            sit.filter(estado__in=S.VIVAS)
            .exclude(afectados__tipo="caso").distinct().count(), f_sit),
    }
    for estado, _e in S.ESTADOS:
        salida[f"situaciones_{estado}"] = conteo(por_estado.get(estado, 0), f_sit)

    #  --- decisiones humanas y su desenlace -------------------------------
    dec = DecisionSupervisor.objects.filter(org=org)
    dec_ventana = dec.filter(decidida_en__gte=desde, decidida_en__lt=hasta)
    por_tipo = dict(dec_ventana.values_list("tipo").annotate(n=Count("id"))
                    .values_list("tipo", "n"))
    for tipo in TipoDecision.TODOS:
        salida[f"decisiones_{tipo}"] = conteo(por_tipo.get(tipo, 0), f_dec, per)

    #  La tasa de aceptacion se calcula solo sobre decisiones HUMANAS: una
    #  propuesta que expiro no la rechazo nadie, y contarla como rechazo diria que
    #  alguien dijo no.
    humanas = dec_ventana.filter(tipo__in=TipoDecision.HUMANOS).count()
    aceptadas = dec_ventana.filter(tipo=TipoDecision.ACEPTO).count()
    salida["tasa_aceptacion"] = derivada(
        round(aceptadas / humanas, 4) if humanas else None,
        con_dato=humanas, denominador=humanas, unidad="proporcion",
        fuente=f_dec, periodo=per)

    #  EL ACIERTO. Solo sobre las que tienen desenlace: sin resultado no se puede
    #  decir si la recomendacion servia.
    con_desenlace = dec_ventana.filter(
        resultado__in=ResultadoDecision.CERRADOS).count()
    funcionaron = dec_ventana.filter(
        resultado=ResultadoDecision.FUNCIONO).count()
    salida["recomendaciones_que_funcionaron"] = derivada(
        round(funcionaron / con_desenlace, 4) if con_desenlace else None,
        con_dato=con_desenlace, denominador=con_desenlace, unidad="proporcion",
        fuente=f_dec, periodo=per)
    #  Y cuantas quedaron sin desenlace, que es la cifra que explica por que la de
    #  arriba puede ser NO_APLICA.
    salida["decisiones_sin_desenlace"] = conteo(
        dec_ventana.filter(resultado=ResultadoDecision.PENDIENTE).count(),
        f_dec, per)
    salida["decisiones_corregidas"] = conteo(
        dec_ventana.exclude(correccion="").count(), f_dec, per)

    return salida


# ==============================================================================
#  B.1  --  CASOS  (se ENVUELVE cases/analytics, no se reescribe)
# ==============================================================================

def indicadores_casos(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    Los conteos de casos, mas el sobre de cobertura sobre lo que
    'cases/analytics.py' ya calcula.

    POR QUE UN SOBRE Y NO UN CALCULO PROPIO
    ---------------------------------------
    'compute_frt' promedia sobre los casos que TIENEN 'first_response_at' y
    devuelve cuantos son ('count') y cuantos habia ('case_ids'). El numero esta
    bien calculado; lo que falta es decir sobre cuantos se calculo. Eso se
    agrega aca sin tocar ese modulo: reescribir el promedio crearia una segunda
    verdad sobre el mismo indicador.
    """
    from cases import analytics

    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    per = _periodo(desde, hasta)
    fuente = "cases.Case"

    qs = Case.objects.filter(org=org)
    en_ventana = qs.filter(created_at__gte=desde, created_at__lt=hasta)
    por_estado = dict(qs.values_list("status").annotate(n=Count("id"))
                      .values_list("status", "n"))
    por_prioridad = dict(qs.values_list("priority").annotate(n=Count("id"))
                         .values_list("priority", "n"))
    por_tipo = dict(qs.values_list("case_type").annotate(n=Count("id"))
                    .values_list("case_type", "n"))
    por_origen = dict(qs.values_list("provider").annotate(n=Count("id"))
                      .values_list("provider", "n"))

    salida = {
        "total": conteo(qs.count(), fuente),
        "en_periodo": conteo(en_ventana.count(), fuente, per),
        "cerrados": conteo(qs.filter(resolved_at__isnull=False).count(), fuente),
        "abiertos": conteo(qs.filter(resolved_at__isnull=True).count(), fuente),
        "por_estado": {k: conteo(v, fuente) for k, v in sorted(por_estado.items())},
        # De donde viene cada caso. 'cases.Case.provider' ya lo distingue: trae
        # 'wisphub' cuando el caso espeja un ticket del proveedor, y queda
        # vacio cuando nacio en el CRM. No hace falta un campo nuevo -- hacia
        # falta agruparlo. La clave vacia se rotula 'dexter' para que el
        # frontend no tenga que interpretar una cadena en blanco.
        "por_origen": {(k or "dexter"): conteo(v, fuente)
                       for k, v in sorted(por_origen.items(),
                                          key=lambda kv: (kv[0] or ""))},
        "por_prioridad": {k: conteo(v, fuente)
                          for k, v in sorted(por_prioridad.items())},
        "por_tipo": {str(k): conteo(v, fuente) for k, v in sorted(
            por_tipo.items(), key=lambda x: str(x[0]))},
    }

    #  --- FRT, envuelto ---
    frt = analytics.compute_frt(qs, desde, hasta)
    salida["primera_respuesta_horas"] = derivada(
        frt.get("median_hours"),
        con_dato=frt.get("count", 0),
        denominador=len(frt.get("case_ids", [])),
        unidad="horas (mediana)", fuente="cases.analytics.compute_frt",
        periodo=per)

    #  --- MTTR, envuelto ---
    mttr = analytics.compute_mttr(qs, desde, hasta)
    salida["resolucion_horas"] = derivada(
        mttr.get("median_hours"),
        con_dato=mttr.get("count", 0),
        denominador=len(mttr.get("case_ids", [])),
        unidad="horas (mediana)", fuente="cases.analytics.compute_mttr",
        periodo=per)
    return salida


# ==============================================================================
#  SLA  --  con las definiciones que YA existen, sin inventar ninguna
# ==============================================================================

def indicadores_sla(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    El SLA se lee de los campos que el propio 'Case' ya define
    ('sla_first_response_hours', 'sla_resolution_hours') y de sus propiedades
    calculadas, que respetan el calendario laboral y las pausas.

    NO se inventan tiempos objetivo, prioridades, calendarios, pausas ni reglas
    de cumplimiento. Y un caso cuyo SLA no se puede decidir se cuenta aparte,
    en vez de asumirlo cumplido.
    """
    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    per = _periodo(desde, hasta)
    fuente = "cases.Case (sla_* y sus propiedades)"

    casos = list(Case.objects.filter(org=org, created_at__gte=desde,
                                     created_at__lt=hasta))
    dentro = vencidos = pausados = no_calculable = 0
    for c in casos:
        if not c.sla_first_response_hours and not c.sla_resolution_hours:
            #  Sin objetivo declarado no hay cumplimiento que medir.
            no_calculable += 1
            continue
        if c.sla_paused_at is not None:
            pausados += 1
            continue
        try:
            incumple = bool(c.is_sla_first_response_breached
                            or c.is_sla_resolution_breached)
        except Exception:
            no_calculable += 1
            continue
        if incumple:
            vencidos += 1
        else:
            dentro += 1

    decidibles = dentro + vencidos
    salida = {
        "casos_en_periodo": conteo(len(casos), fuente, per),
        "dentro_de_sla": conteo(dentro, fuente, per),
        "vencidos": conteo(vencidos, fuente, per),
        "pausados": conteo(pausados, fuente, per),
        "no_calculable": conteo(no_calculable, fuente, per),
    }
    salida["cumplimiento"] = derivada(
        round(dentro / decidibles, 4) if decidibles else None,
        con_dato=decidibles, denominador=len(casos),
        unidad="proporcion", fuente=fuente, periodo=per)
    return salida


# ==============================================================================
#  TODO JUNTO
# ==============================================================================

def indicadores(org, desde=None, hasta=None, ahora=None, dias=None) -> dict:
    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    return {
        "organizacion": {"id": str(org.id), "nombre": org.name},
        "generado_en": (ahora or timezone.now()).isoformat(),
        "periodo": _periodo(desde, hasta),
        "casos": indicadores_casos(org, desde, hasta, ahora),
        "sla": indicadores_sla(org, desde, hasta, ahora),
        "actividades": indicadores_actividades(org, desde, hasta, ahora),
        "compromisos": indicadores_compromisos(org, ahora),
        "programacion": indicadores_programacion(org, ahora, dias),
        "supervisor": indicadores_supervisor(org, desde, hasta, ahora),
        "situaciones": indicadores_situaciones(org, desde, hasta, ahora),
        "evaluacion": indicadores_evaluacion(org, desde, hasta, ahora),
    }




# ==============================================================================
#  B.8  --  EVALUACION DEL SUPERVISOR  (P8.3)
# ==============================================================================
#
#  QUE MIDE ESTE BLOQUE Y QUE NO
#  -----------------------------
#  Mide si el Supervisor ACERTO, y eso solo se puede medir con resultados que
#  alguien confirmo. Por eso la fuente de casi todo aqui es
#  'AprendizajeSupervisor', donde cada fila lleva evidencia obligatoria por
#  restriccion de base y un origen que NUNCA es el propio Supervisor.
#
#  Lo que NO se hace, y es la mitad del diseño:
#
#    * una propuesta ACEPTADA no cuenta como correcta;
#    * una propuesta RECHAZADA no cuenta como incorrecta;
#    * un denominador en cero NO devuelve 0, devuelve NO_APLICA;
#    * una decision sin situacion NO tiene tiempo de deteccion, y se cuenta
#      aparte en vez de entrar como cero.
#
#  UNA SOLA FORMULA POR METRICA, Y VIVE AQUI
#  -----------------------------------------
#  'gobierno.resumen_de_aprendizaje' devuelve CONTEOS crudos a proposito: no
#  calcula tasas. Las formulas estan en este archivo y en ninguno mas, para que
#  no haya dos definiciones de "precision" que se desincronicen calladas.

#: Las lecciones que cuentan a favor y en contra. Se importan de donde se
#: declaran: duplicar las listas aqui seria la primera divergencia.
def _aprendizajes(org, desde, hasta):
    from operaciones.gobierno_modelos import AprendizajeSupervisor

    return AprendizajeSupervisor.objects.filter(
        org=org, registrado_en__gte=desde, registrado_en__lte=hasta)


def _mediana(valores):
    """La mediana, o None si no hay con que. Nunca 0 por ausencia."""
    if not valores:
        return None
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else round((v[n // 2 - 1] + v[n // 2]) / 2.0, 2)


def indicadores_evaluacion(org, desde=None, hasta=None, ahora=None) -> dict:
    """
    Si el Supervisor acierta, con que cobertura, y que no se puede saber.

    PRECISION  (§5)
    ---------------
        numerador    lecciones a favor   (recomendacion confirmada,
                                          rechazo errado, correlacion correcta)
        denominador  a favor + en contra (falso positivo, omision,
                                          correlacion incorrecta)
        filtro       'AprendizajeSupervisor' del periodo, de esta organizacion
        cero         NO_APLICA -- sin lecciones confirmadas no hay precision
                     que reportar, y 0 se leeria como "nunca acierta"

    Las lecciones son la unica fuente de verdad disponible: cada una exige
    evidencia y la escribe una persona, una verificacion o un hecho operativo.
    Una decision por si sola no entra en esta cuenta.
    """
    from operaciones.gobierno_modelos import (ResultadoDecision,
                                              TipoAprendizaje)
    from operaciones.models import DecisionSupervisor
    from operaciones.situaciones_modelos import (SituacionAfectado,
                                                 SituacionOperativa,
                                                 SituacionRelacion,
                                                 TipoAfectado, TipoRelacion)

    desde, hasta, ahora = _ventana(desde, hasta, ahora)
    p = _periodo(desde, hasta)
    ap = _aprendizajes(org, desde, hasta)

    #  --- A. PRECISION ------------------------------------------------------
    por_tipo = {t: 0 for t in TipoAprendizaje.TODOS}
    for fila in ap.values("tipo").annotate(n=Count("id")):
        por_tipo[fila["tipo"]] = fila["n"]
    a_favor = sum(por_tipo[t] for t in TipoAprendizaje.A_FAVOR)
    en_contra = sum(por_tipo[t] for t in TipoAprendizaje.EN_CONTRA)
    conocidas = a_favor + en_contra

    salida = {
        "precision": derivada(
            round(a_favor / conocidas, 4) if conocidas else None,
            con_dato=conocidas, denominador=conocidas, unidad="proporcion",
            fuente="operaciones.AprendizajeSupervisor", periodo=p),
        "lecciones_a_favor": conteo(a_favor, "AprendizajeSupervisor", p),
        "lecciones_en_contra": conteo(en_contra, "AprendizajeSupervisor", p),

        #  --- B / C.  Falsos positivos y omisiones -------------------------
        #  Van como CONTEOS y no como tasas: una tasa de falsos positivos
        #  necesitaria saber cuantas detecciones hubo en total CONFIRMADAS, y
        #  de las que nadie reviso no se sabe nada. El conteo es honesto; la
        #  tasa seria una invencion.
        "falsos_positivos": conteo(
            por_tipo[TipoAprendizaje.FALSO_POSITIVO],
            "AprendizajeSupervisor", p),
        "omisiones_conocidas": conteo(
            por_tipo[TipoAprendizaje.OMISION], "AprendizajeSupervisor", p),
        #  §7: los datos insuficientes NO son una omision. Se publican al lado
        #  para que nadie los sume.
        "situaciones_con_datos_insuficientes": conteo(
            SituacionAfectado.objects.filter(
                org=org, tipo=TipoAfectado.DATOS_INSUFICIENTES,
                situacion__detectada_en__gte=desde,
                situacion__detectada_en__lte=hasta)
            .values("situacion").distinct().count(),
            "operaciones.SituacionAfectado", p),

        #  --- H. Correcciones humanas --------------------------------------
        #  Se reutiliza el mismo criterio que 'indicadores_situaciones' ya
        #  publicaba: la correccion vive en 'DecisionSupervisor.correccion'.
        "correcciones_humanas": conteo(
            DecisionSupervisor.objects
            .filter(org=org, decidida_en__gte=desde, decidida_en__lte=hasta)
            .exclude(correccion="").count(),
            "operaciones.DecisionSupervisor", p),
    }

    #  --- D. CALIDAD DE CORRELACION ----------------------------------------
    correctas = por_tipo[TipoAprendizaje.CORRELACION_CORRECTA]
    incorrectas = por_tipo[TipoAprendizaje.CORRELACION_INCORRECTA]
    evaluadas = correctas + incorrectas
    propuestos = confirmados = 0
    desvios = []
    for fila in ap.filter(tipo__in=(TipoAprendizaje.CORRELACION_CORRECTA,
                                    TipoAprendizaje.CORRELACION_INCORRECTA)):
        d = fila.datos or {}
        if "afectados_propuestos" in d and "afectados_confirmados" in d:
            propuestos += int(d["afectados_propuestos"])
            confirmados += int(d["afectados_confirmados"])
            desvios.append(abs(int(d.get("diferencia", 0))))
    salida["calidad_correlacion"] = derivada(
        round(correctas / evaluadas, 4) if evaluadas else None,
        con_dato=evaluadas, denominador=evaluadas, unidad="proporcion",
        fuente="AprendizajeSupervisor.correlacion", periodo=p)
    salida["afectados_propuestos"] = conteo(propuestos, "aprendizaje.datos", p)
    salida["afectados_confirmados"] = conteo(confirmados, "aprendizaje.datos",
                                             p)
    #  El desvio medio en valor absoluto: 'propuso 12, eran 10' y 'propuso
    #  10, eran 12' se equivocan lo mismo, y promediar con signo los
    #  cancelaria.
    salida["desvio_medio_afectados"] = derivada(
        _mediana(desvios), con_dato=len(desvios), denominador=evaluadas,
        unidad="afectados", fuente="aprendizaje.datos", periodo=p)

    #  --- E. REINCIDENCIA ---------------------------------------------------
    #  Solo las CONFIRMADAS. 'candidatas_de_reincidencia' propone y no escribe:
    #  contar candidatas aqui convertiria una coincidencia en un diagnostico.
    salida["reincidencias_confirmadas"] = conteo(
        SituacionRelacion.objects.filter(
            org=org, tipo=TipoRelacion.REINCIDENCIA,
            creada_en__gte=desde, creada_en__lte=hasta).count(),
        "operaciones.SituacionRelacion", p)

    #  --- F / G.  RESULTADO POR TIPO DE SEÑAL Y POR HABILIDAD --------------
    #  Conteos por categoria y no una tasa: con tres funciono y un fallo en una
    #  señal, y cero en otra, una tasa unica las volveria incomparables.
    decisiones = (DecisionSupervisor.objects
                  .filter(org=org, decidida_en__gte=desde,
                          decidida_en__lte=hasta)
                  .select_related("propuesta"))
    vacio = {r: 0 for r in ResultadoDecision.TODOS}
    por_senal: dict = {}
    por_habilidad: dict = {}
    sin_propuesta = 0
    for d in decisiones:
        if d.propuesta_id is None:
            sin_propuesta += 1
            continue
        senal = d.propuesta.tipo_senal
        hab = d.propuesta.conocimiento_version or "(sin ficha)"
        por_senal.setdefault(senal, dict(vacio))[d.resultado] += 1
        por_habilidad.setdefault(hab, dict(vacio))[d.resultado] += 1
    salida["resultado_por_tipo_senal"] = por_senal
    salida["resultado_por_habilidad"] = por_habilidad
    #  Las decisiones cuya propuesta ya no esta no se pueden clasificar por
    #  señal. Se cuentan aparte en vez de caer en una categoria inventada.
    salida["decisiones_sin_propuesta"] = conteo(
        sin_propuesta, "operaciones.DecisionSupervisor", p)

    #  --- I / J.  LOS DOS TIEMPOS -------------------------------------------
    #  §4: una decision SIN situacion no tiene tiempo de deteccion. No se
    #  imputa cero: se excluye del numerador y se publica cuantas fueron.
    a_decision, sin_situacion = [], 0
    for d in decisiones.select_related("situacion"):
        if d.situacion_id is None or d.situacion.detectada_en is None:
            sin_situacion += 1
            continue
        a_decision.append(
            (d.decidida_en - d.situacion.detectada_en).total_seconds() / 60.0)
    cerradas = [d for d in decisiones
                if d.resultado in ResultadoDecision.CERRADOS
                and d.resultado_en and d.decidida_en]
    a_resultado = [(d.resultado_en - d.decidida_en).total_seconds() / 60.0
                   for d in cerradas]
    total_dec = decisiones.count()
    salida["minutos_deteccion_a_decision"] = derivada(
        _mediana(a_decision), con_dato=len(a_decision),
        denominador=total_dec, unidad="minutos",
        fuente="situacion.detectada_en -> decision.decidida_en", periodo=p)
    salida["decisiones_sin_situacion"] = conteo(
        sin_situacion, "operaciones.DecisionSupervisor", p)
    salida["minutos_decision_a_resultado"] = derivada(
        _mediana(a_resultado), con_dato=len(a_resultado),
        denominador=total_dec, unidad="minutos",
        fuente="decision.decidida_en -> decision.resultado_en", periodo=p)

    #  --- K / L / M.  ANTICIPACION -----------------------------------------
    #  La pregunta: ¿el Supervisor vio la situacion ANTES del primer ticket?
    #
    #  El dato sale de cruzar 'situacion.detectada_en' contra el 'created_at'
    #  del primer caso asociado -- NO contra cuando el Supervisor lo asocio,
    #  que es otra cosa y siempre es posterior.
    #
    #  Minutos POSITIVOS = anticipo. Negativos = llego tarde. Las situaciones
    #  sin ningun caso NO entran en la cuenta: de esas no se puede saber si
    #  anticipo o si nadie reclamo nunca, y mezclarlas inflaria el anticipo.
    sits = list(SituacionOperativa.objects.filter(
        org=org, detectada_en__gte=desde, detectada_en__lte=hasta))
    anticipos, anticipadas, tardias = [], 0, 0
    sin_caso = casos_irresolubles = 0
    for s in sits:
        ids = list(SituacionAfectado.objects
                   .filter(situacion=s, tipo=TipoAfectado.CASO)
                   .values_list("identificador", flat=True))
        if not ids:
            sin_caso += 1
            continue
        primero = (Case.objects.filter(org=org, id__in=ids)
                   .order_by("created_at")
                   .values_list("created_at", flat=True).first())
        if primero is None:
            #  El afectado nombra un caso que ya no existe o no se puede
            #  resolver. No se inventa un instante.
            casos_irresolubles += 1
            continue
        minutos = (primero - s.detectada_en).total_seconds() / 60.0
        anticipos.append(minutos)
        if minutos > 0:
            anticipadas += 1
        else:
            tardias += 1

    con_ticket = len(anticipos)
    salida["situaciones_en_periodo"] = conteo(
        len(sits), "operaciones.SituacionOperativa", p)
    salida["situaciones_anticipadas"] = conteo(anticipadas, "anticipacion", p)
    salida["situaciones_detectadas_tarde"] = conteo(tardias, "anticipacion", p)
    salida["tasa_anticipacion"] = derivada(
        round(anticipadas / con_ticket, 4) if con_ticket else None,
        con_dato=con_ticket, denominador=con_ticket, unidad="proporcion",
        fuente="situacion.detectada_en vs Case.created_at", periodo=p)
    salida["minutos_anticipacion"] = derivada(
        _mediana(anticipos), con_dato=con_ticket, denominador=con_ticket,
        unidad="minutos",
        fuente="situacion.detectada_en vs Case.created_at", periodo=p)
    #  Los dos que NO se pueden medir, publicados y no escondidos.
    salida["situaciones_sin_ticket"] = conteo(sin_caso, "anticipacion", p)
    salida["situaciones_con_caso_irresoluble"] = conteo(
        casos_irresolubles, "anticipacion", p)
    return salida

# ==============================================================================
#  REPORTES
# ==============================================================================

DIARIO = "diario"
PENDIENTES = "pendientes"
PROGRAMACION = "programacion"
COMPROMISOS = "compromisos"
SUPERVISOR = "supervisor"
EVALUACION = "evaluacion"
REPORTES = (DIARIO, PENDIENTES, PROGRAMACION, COMPROMISOS,
            SUPERVISOR, EVALUACION)


def _sobre(nombre, org, desde, hasta, ahora, fuentes, metricas,
           observaciones=None) -> dict:
    """La cabecera comun. Un reporte sin periodo ni fuente no se puede revisar."""
    faltantes = _insuficientes(metricas)
    return {
        "reporte": nombre,
        "organizacion": {"id": str(org.id), "nombre": org.name},
        "generado_en": ahora.isoformat(),
        "periodo": _periodo(desde, hasta),
        "filtros": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "fuentes": fuentes,
        "metricas": metricas,
        "datos_insuficientes": faltantes,
        "cobertura_completa": not faltantes,
        "observaciones": observaciones or [],
    }


def _insuficientes(nodo, ruta="") -> list[dict]:
    """
    Recorre el arbol de metricas y junta las que NO son VALIDO. Asi el lector
    ve de una vez que parte del reporte no se puede usar, sin tener que
    inspeccionar indicador por indicador.
    """
    salida = []
    if isinstance(nodo, dict):
        if "estado" in nodo and nodo["estado"] in (DATOS_INSUFICIENTES, NO_APLICA):
            salida.append({"indicador": ruta, "estado": nodo["estado"],
                           "cobertura": nodo.get("cobertura"),
                           "motivo": nodo.get("motivo", "")})
            return salida
        for k, v in nodo.items():
            salida.extend(_insuficientes(v, f"{ruta}.{k}" if ruta else k))
    return salida


def reporte(org, nombre: str, desde=None, hasta=None, ahora=None,
            dias=None) -> dict:
    """
    Un reporte. Es LECTURA: no escribe una fila, no crea actividad de negocio y
    no corre el ciclo del Supervisor.
    """
    if nombre not in REPORTES:
        raise ValueError(f"'{nombre}' no es un reporte. Hay {len(REPORTES)}: "
                         f"{', '.join(REPORTES)}.")
    desde, hasta, ahora = _ventana(desde, hasta, ahora)

    if nombre == EVALUACION:
        #  El reporte que contesta "¿acierta?". Lleva los dos bloques juntos a
        #  proposito: 'situaciones' trae el QUE paso y 'evaluacion' el SI
        #  SIRVIO, y leer el segundo sin el primero invita a interpretar una
        #  precision sin saber sobre cuantas situaciones se calculo.
        m = {"situaciones": indicadores_situaciones(org, desde, hasta, ahora),
             "evaluacion": indicadores_evaluacion(org, desde, hasta, ahora)}
        return _sobre(
            nombre, org, desde, hasta, ahora,
            ["operaciones.AprendizajeSupervisor",
             "operaciones.DecisionSupervisor",
             "operaciones.SituacionOperativa",
             "operaciones.SituacionRelacion", "cases.Case"], m,
            ["La precision se calcula SOLO sobre lecciones confirmadas: cada "
             "una exige evidencia y la escribe una persona, una verificacion o "
             "un hecho operativo. Una propuesta aceptada NO cuenta como "
             "correcta, y una rechazada NO cuenta como incorrecta.",
             "Un denominador en cero devuelve NO_APLICA, no 0: la ausencia de "
             "resultados conocidos no es un rendimiento de cero.",
             "La anticipacion se mide contra el 'created_at' del primer caso "
             "asociado, no contra cuando el Supervisor lo asocio. Las "
             "situaciones sin ningun caso quedan FUERA del calculo y se "
             "cuentan aparte: de esas no se puede saber si anticipo o si nadie "
             "reclamo nunca.",
             "Los datos insuficientes NO se cuentan como omision."])

    if nombre == DIARIO:
        m = {"casos": indicadores_casos(org, desde, hasta, ahora),
             "sla": indicadores_sla(org, desde, hasta, ahora),
             "actividades": indicadores_actividades(org, desde, hasta, ahora),
             "programacion": indicadores_programacion(org, ahora, dias),
             "supervisor": indicadores_supervisor(org, desde, hasta, ahora)}
        return _sobre(nombre, org, desde, hasta, ahora,
                      ["cases.Case", "operaciones.ActividadOperativa",
                       "campo.OrdenTrabajo", "operaciones.PropuestaSupervisor",
                       "operaciones.capacidad"], m,
                      ["Las cifras son del momento de generacion: este reporte "
                       "no se guarda y no queda historizado."])

    if nombre == PENDIENTES:
        act = indicadores_actividades(org, desde, hasta, ahora)
        m = {"actividades": act,
             "compromisos": indicadores_compromisos(org, ahora)}
        return _sobre(nombre, org, desde, hasta, ahora,
                      ["operaciones.ActividadOperativa"], m,
                      ["'vencida' significa que la fecha objetivo paso y la "
                       "actividad no esta cerrada. NO significa que alguien "
                       "haya incumplido: la causa no esta registrada."])

    if nombre == PROGRAMACION:
        m = {"programacion": indicadores_programacion(org, ahora, dias)}
        return _sobre(nombre, org, desde, hasta, ahora,
                      ["campo.OrdenTrabajo", "operaciones.ProgramacionOrden",
                       "operaciones.capacidad (M03-G)"], m,
                      ["La capacidad se deriva; no hay ningun porcentaje "
                       "guardado. Donde faltan duraciones el resultado es "
                       "INDETERMINADO, que no es cero."])

    if nombre == COMPROMISOS:
        m = {"compromisos": indicadores_compromisos(org, ahora)}
        return _sobre(nombre, org, desde, hasta, ahora,
                      ["operaciones.ActividadOperativa (tipo=compromiso)"], m,
                      ["Un compromiso sin fecha es legitimo y se cuenta aparte: "
                       "no se le supone una."])

    m = {"supervisor": indicadores_supervisor(org, desde, hasta, ahora)}
    return _sobre(nombre, org, desde, hasta, ahora,
                  ["operaciones.supervisor", "operaciones.PropuestaSupervisor"],
                  m,
                  ["Las senales se detectan sin escribir: consultar este "
                   "reporte NO corre el ciclo ni crea propuestas.",
                   "'acciones_propuestas' (historico del motor) NO se mezcla "
                   "aca: es otra semantica y otra tabla."])
