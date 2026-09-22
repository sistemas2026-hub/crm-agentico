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

    salida = {
        "total": conteo(qs.count(), fuente),
        "en_periodo": conteo(en_ventana.count(), fuente, per),
        "cerrados": conteo(qs.filter(resolved_at__isnull=False).count(), fuente),
        "abiertos": conteo(qs.filter(resolved_at__isnull=True).count(), fuente),
        "por_estado": {k: conteo(v, fuente) for k, v in sorted(por_estado.items())},
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
    }


# ==============================================================================
#  REPORTES
# ==============================================================================

DIARIO = "diario"
PENDIENTES = "pendientes"
PROGRAMACION = "programacion"
COMPROMISOS = "compromisos"
SUPERVISOR = "supervisor"
REPORTES = (DIARIO, PENDIENTES, PROGRAMACION, COMPROMISOS, SUPERVISOR)


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
