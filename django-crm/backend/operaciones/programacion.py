# -*- coding: utf-8 -*-
"""
================================================================================
 PROGRAMAR UNA ORDEN  --  paso M03-B
================================================================================

La primera operación real de programación. Hasta este paso el sistema tenía las
tres tablas del plan -- ProgramacionSemanal, ProgramacionOrden, NovedadOperativa
-- con RLS, constraints y registro en el admin, y NINGÚN escritor: 0 filas, 0
servicios, 0 endpoints (medido en M03-A). Existían esperando a M03.

POR QUÉ UNA SOLA TRANSACCIÓN, Y NO DOS ESCRITURAS
-------------------------------------------------
'ProgramacionOrden' y 'OrdenTrabajo.programada_para' son dos cosas distintas a
propósito -- el plan dice lo que se pensó el viernes, el campo dice lo que rige
ahora (ver operaciones/models.py::ProgramacionOrden). Pero que sean distintas no
las autoriza a contradecirse.

M09 ya había previsto la contradicción antes de que existiera esta función:
'_ordenes_desincronizadas' (supervisor.py) detecta exactamente "la orden está en
un plan publicado y 'programada_para' está vacío", y '_ordenes_sin_programar'
deja escrito por qué importa:

    "Con la condición anterior esa orden disparaba la señal y el Supervisor
     recomendaba programar algo que ya estaba programado. No era hipotético:
     'programada_para' está en 0 de 3 órdenes de producción, así que el primer
     plan que M03 cargue produce el falso positivo."

Este módulo es ese primer plan. Si escribiera la línea sin el campo, nacería
produciendo el falso positivo que M09 documentó. Por eso las dos escrituras van
en la misma transacción y bajo el mismo lock: o quedan las dos, o no queda
ninguna.

QUÉ NO HACE  --  y ninguna de estas ausencias es un descuido
------------------------------------------------------------
No calcula capacidad, duración, complejidad ni desplazamiento: M03-A midió que
NO EXISTE un solo dato para hacerlo. No asigna técnico -- una orden puede quedar
programada y sin dueño, y eso es deliberado. No reprograma: mover una fecha ya
puesta exige registrar el antes y el después, y esa operación es de otra fase.
No cambia 'estado_operativo'. No llama a ningún sistema externo.
================================================================================
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from campo.models import EventoTrabajo, OrdenTrabajo
from operaciones.models import (NovedadOperativa, ProgramacionOrden,
                                ProgramacionSemanal)


class ErrorProgramacion(ValueError):
    """No se pudo programar. El mensaje dice por qué, en castellano."""


class YaProgramada(ErrorProgramacion):
    """
    La orden ya tiene programación. NO se sobrescribe.

    Es una clase aparte y no un mensaje más porque quien llama necesita poder
    distinguir "no se puede programar" de "ya está programada": lo segundo no
    es un error del que pide, es una operación distinta -- reprogramar -- que
    todavía no existe.
    """


#  LOS ESTADOS QUE ADMITEN PROGRAMACIÓN, Y DE DÓNDE SALE LA LISTA
#  --------------------------------------------------------------
#  M03-A midió el GAP: NINGÚN estado de OrdenTrabajo restringe hoy la escritura
#  de 'programada_para' -- el campo se fija al crear la orden y nada lo valida.
#  Así que la lista no se deduce de una regla que no existe: se toma el único
#  estado cuya semántica YA está establecida en código.
#
#  'asignada' es ese estado, y lo dice el propio detector de M09
#  (supervisor.py::_ordenes_sin_programar):
#
#      "'estado_operativo = asignada' YA implica que no arrancó: ninguna
#       transición vuelve a ese estado y 'iniciada_en' sólo se escribe al salir
#       de él."
#
#  Programar un trabajo que el técnico ya empezó, o uno cerrado, no es una
#  decisión que este paso deba habilitar. Los demás estados quedan fuera de
#  forma explícita, no por olvido -- y 'correccion_requerida' en particular es
#  una DECISIÓN DE NEGOCIO pendiente: un trabajo devuelto probablemente deba
#  poder reprogramarse, pero eso es la fase que este paso no implementa.
ESTADOS_PROGRAMABLES = frozenset({OrdenTrabajo.ASIGNADA})

#  Un plan cerrado es historia. Mismo criterio que despacho.asignar aplica a las
#  órdenes terminadas ("No se reasigna un trabajo terminado"): el ciclo declarado
#  es borrador -> publicada -> cerrada, y 'cerrada' no tiene salida.
ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS = frozenset({
    ProgramacionSemanal.BORRADOR,
    ProgramacionSemanal.PUBLICADA,
})


def _dia_y_hora(programada_para):
    """
    El día y la hora locales de un instante, con la MISMA conversión que H-05.

    No es un detalle de formato. '_ordenes_en_riesgo' compara la ausencia de un
    técnico contra 'timezone.localtime(o.programada_para).date()'. Si aquí se
    usara otra conversión --UTC crudo, o la fecha del servidor-- la línea del
    plan y la fecha que H-05 mira podrían caer en días distintos, y el detector
    buscaría la ausencia en el día equivocado sin que nada fallara.
    """
    local = timezone.localtime(programada_para)
    return local.date(), local.time()


def _programacion_vigente_de(org, orden):
    """
    La linea que RIGE para esta orden, si existe.

    Misma definicion de "vigente" que 'supervisor._programacion_vigente' y que
    '_lineas_vigentes': 'planificada' y 'confirmada' cuentan, 'reprogramada' y
    'cancelada' no. Tener tres definiciones distintas de lo mismo seria la
    forma mas rapida de que M09 y M03 discrepen sin que nadie lo note.
    """
    return (ProgramacionOrden.objects
            .filter(org=org, orden=orden,
                    estado__in=(ProgramacionOrden.PLANIFICADA,
                                ProgramacionOrden.CONFIRMADA))
            .select_related("programacion")
            .first())


def _programacion_existente(org, orden):
    """Cualquier línea de plan de esta orden, vigente o no."""
    return (ProgramacionOrden.objects
            .filter(org=org, orden=orden)
            .select_related("programacion")
            .first())


@transaction.atomic
def programar_orden(*, org, orden, programacion, programada_para, actor,
                    zona: str = "", prioridad: int | None = None,
                    secuencia: int | None = None,
                    causa: str = "", motivo: str = "") -> ProgramacionOrden:
    """
    Pone fecha a una orden: crea su línea de plan y fija 'programada_para'.

    Las dos escrituras y todas las comprobaciones van dentro de la misma
    transacción, y la orden se bloquea antes de leer su estado: sin el lock,
    dos peticiones simultáneas pueden comprobar "no está programada" a la vez y
    programarla dos veces con fechas distintas.

    'actor' no tiene default a propósito. Una programación sin persona detrás no
    debería ser representable: es una decisión operativa, no un cálculo.
    """
    if actor is None:
        raise ErrorProgramacion(
            "Una programación sin actor no se registra: es una decisión de "
            "una persona, y tiene que quedar quién la tomó.")

    if programada_para is None:
        raise ErrorProgramacion("Falta la fecha y hora de programación.")
    if timezone.is_naive(programada_para):
        #  Una fecha sin zona se interpretaría con la del servidor, y el día
        #  que le tocaría a la línea dependería de dónde corre el proceso.
        raise ErrorProgramacion(
            "La fecha de programación tiene que traer zona horaria.")

    #  LAS DOS PERTENENCIAS, ANTES DE TOCAR NADA
    #  -----------------------------------------
    #  'org' sale de la sesión, nunca del cuerpo de la petición. Y se comprueban
    #  las DOS puntas: una orden de A metida en un plan de B cruzaría las
    #  empresas por la vía del plan aunque la orden fuera legítima.
    if orden.org_id != org.id:
        raise ErrorProgramacion("Esa orden es de otra empresa.")
    if programacion.org_id != org.id:
        raise ErrorProgramacion("Ese plan semanal es de otra empresa.")

    if programacion.estado not in ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS:
        raise ErrorProgramacion(
            f"El plan de la semana del {programacion.semana_inicio} está "
            f"'{programacion.get_estado_display()}'. No se agregan órdenes a "
            f"un plan cerrado.")

    #  AGREGAR A UN PLAN PUBLICADO ES UNA ADICIÓN FORMAL  --  paso M03-D3
    #  ------------------------------------------------------------------
    #  Un plan publicado ya lo vieron las cuadrillas: meterle trabajo nuevo
    #  cambia un compromiso que alguien está mirando. Sigue permitido --no se
    #  congela-- pero deja de ser silencioso: exige causa, y el evento se llama
    #  distinto para que la bitácora lo distinga de una programación normal.
    #
    #  Sobre un BORRADOR no se exige nada nuevo: no compromete a nadie, y esa
    #  conducta es la que M03-B dejó validada.
    es_adicion_formal = (programacion.estado == ProgramacionSemanal.PUBLICADA)
    causa, motivo = _validar_causa(
        causa, motivo, exigida=es_adicion_formal,
        donde="Agregar una orden a un plan ya publicado")

    #  LA REGLA DERIVADA, Y SE DICE QUE LO ES
    #  --------------------------------------
    #  'semana_inicio' se define en el modelo como "Lunes de la semana que
    #  planifica". Una línea fechada fuera de esa semana deja al plan diciendo
    #  algo que no es. No hay constraint en la base que lo impida ni política de
    #  empresa que lo declare: es coherencia derivada del propio campo, y queda
    #  marcada como tal en el informe por si el negocio decide otra cosa.
    dia, hora = _dia_y_hora(programada_para)
    fin_de_semana = programacion.semana_inicio + timedelta(days=6)
    if not (programacion.semana_inicio <= dia <= fin_de_semana):
        raise ErrorProgramacion(
            f"El {dia} cae fuera del plan de la semana del "
            f"{programacion.semana_inicio} (hasta el {fin_de_semana}).")

    #  EL LOCK, Y POR QUÉ SE RELEE LA ORDEN
    #  ------------------------------------
    #  El objeto que llegó por parámetro pudo leerse hace rato. Lo que decide es
    #  la fila bloqueada: se comprueban el estado y 'programada_para' sobre ella,
    #  no sobre la copia en memoria.
    fresca = (OrdenTrabajo.objects
              .select_for_update()
              .get(pk=orden.pk, org=org))

    if fresca.estado_operativo not in ESTADOS_PROGRAMABLES:
        raise ErrorProgramacion(
            f"La orden #{fresca.numero} está "
            f"'{fresca.get_estado_operativo_display()}'. Solo se programa un "
            f"trabajo que todavía no arrancó.")

    #  NO SE SOBRESCRIBE EN SILENCIO  (M03-B §8)
    #  -----------------------------------------
    #  Se mira por las dos vías, porque las dos pueden estar pobladas por
    #  separado -- que es justamente la incoherencia que este módulo existe para
    #  no producir.
    linea_previa = _programacion_existente(org, fresca)
    if fresca.programada_para is not None or linea_previa is not None:
        cuando = (fresca.programada_para or
                  (linea_previa.dia if linea_previa else None))
        raise YaProgramada(
            f"La orden #{fresca.numero} ya está programada para {cuando}. "
            f"Cambiar una fecha ya puesta es reprogramar, y eso exige registrar "
            f"el motivo y el valor anterior: todavía no está implementado.")

    try:
        linea = ProgramacionOrden.objects.create(
            org=org,
            programacion=programacion,
            orden=fresca,
            dia=dia,
            hora_inicio=hora,
            zona=(zona or "").strip(),
            #  prioridad y secuencia conservan el default del modelo cuando no
            #  se envían. No se calculan: ordenar una jornada necesita duración
            #  y desplazamiento, y M03-A midió que no existe ninguno de los dos.
            **({"prioridad": prioridad} if prioridad is not None else {}),
            **({"secuencia": secuencia} if secuencia is not None else {}),
            estado=ProgramacionOrden.PLANIFICADA,
        )
    except IntegrityError as e:
        #  La base manda. Si llega aquí es que hay un camino que las
        #  comprobaciones de arriba no cubren, y entonces lo correcto es que
        #  gane la constraint y no quede nada escrito.
        raise ErrorProgramacion(
            f"La base rechazó la línea de plan: {str(e).strip().splitlines()[0]}"
        ) from e

    fresca.programada_para = programada_para
    #  'revision' es el control optimista que usa la cola offline del técnico.
    #  Subirlo es lo que hace 'despacho.asignar' cuando cambia algo que la app
    #  ya se llevó; programar cambia el día del trabajo, así que cuenta igual.
    fresca.revision += 1
    #  'updated_by' va en la lista  --  corregido en M03-D3.2
    #  BaseModel.save() lo asigna desde crum con el usuario de la peticion,
    #  pero sin nombrarlo aqui el UPDATE no lo escribe: quedaba asignado en
    #  memoria y perdido al guardar. M03-C lo aprendio al implementar
    #  'publicar_programacion' y M03-D3 lo copio; esta funcion es anterior a
    #  esa leccion.
    #
    #  Fuera de una peticion HTTP no cambia nada: crum devuelve None, 'save' ni
    #  siquiera entra en la rama que asigna, y el UPDATE escribe el valor que
    #  el campo ya tenia.
    fresca.save(update_fields=["programada_para", "revision",
                               "updated_by", "updated_at"])

    #  AUDITORÍA POR EL MECANISMO QUE YA EXISTE  (M03-B §14)
    #  -----------------------------------------------------
    #  EventoTrabajo es la bitácora append-only de campo, y es donde
    #  'despacho.asignar' deja la reasignación. No hace falta tabla nueva: aquí
    #  quedan actor, organización, orden, operación y timestamp.
    EventoTrabajo.objects.create(
        org=org,
        orden=fresca,
        tipo=("adicion_a_plan_publicado" if es_adicion_formal
              else "programacion"),
        profile=actor,
        datos={
            #  Las seis claves originales se conservan tal cual: la suite de
            #  M03-B afirma sobre ellas, y una traza no se renombra porque
            #  aparezca un caso nuevo.
            "numero": fresca.numero,
            "programada_para": programada_para.isoformat(),
            "dia": str(dia),
            "programacion_semanal": str(programacion.id),
            "semana_inicio": str(programacion.semana_inicio),
            "estado_del_plan": programacion.estado,
            "linea": str(linea.id),
            #  Añadidas en M03-D3. 'anterior' es None a propósito y se declara:
            #  agregar no tiene fecha previa, y omitir la clave se leería como
            #  "nadie lo pensó".
            "ruta": "adicion" if es_adicion_formal else "programacion",
            "anterior": None,
            "causa": causa,
            "motivo": motivo,
            "sla": _bloque_sla(fresca),
        },
    )
    if causa:
        _novedad_de(org, fresca, actor, causa, motivo, None, programada_para)
    return linea


# =============================================================================
#  PUBLICAR UN PLAN SEMANAL  --  paso M03-C
# =============================================================================
#  LO QUE LA AUDITORIA DEL MODELO ENCONTRO, Y QUE CAMBIA EL DISEÑO
#  ---------------------------------------------------------------
#  'ProgramacionSemanal' declara tres estados y NO tiene maquina de
#  transiciones. No es como 'OrdenTrabajo', que tiene TRANSICIONES_PERMITIDAS,
#  ni como 'WorkTypeVersion', que defiende su inmutabilidad en clean()/save().
#  Aqui el ciclo borrador -> publicada -> cerrada existe en el orden de la tupla
#  ESTADOS y en los docstrings, y en ningun sitio mas: hoy cualquier escritura
#  puede poner cualquier estado.
#
#  Por eso este modulo NO "respeta" una maquina existente: es el primer sitio
#  donde una transicion de plan queda restringida, y solo restringe la unica
#  que necesita. No se declara una maquina completa porque eso decidiria de
#  paso cerrar y reabrir, que son operaciones de otras fases.
#
#  Tampoco hay campo de concurrencia optimista --ni 'revision' ni version-- asi
#  que la carrera se resuelve con el lock de la fila, no con un contador.


class PlanNoPublicable(ErrorProgramacion):
    """
    El plan no esta en un estado desde el que se pueda publicar.

    Clase aparte porque quien llama necesita distinguirlo de "el plan tiene
    datos incoherentes": lo primero es un conflicto con el estado actual del
    recurso --la peticion no tiene nada de malo-- y lo segundo es un problema
    de los datos que hay que arreglar antes.
    """


class PlanIncoherente(ErrorProgramacion):
    """
    El plan contiene lineas que se contradicen con las ordenes que referencian.

    Trae 'problemas': la lista de lo que no cuadra, sin corregir ninguno.
    """

    def __init__(self, mensaje, problemas):
        super().__init__(mensaje)
        self.problemas = problemas


def _lineas_vigentes(programacion):
    """
    Las lineas del plan que comprometen algo.

    'planificada' y 'confirmada' cuentan; 'reprogramada' y 'cancelada' no --
    misma definicion que 'supervisor._programacion_vigente', y por la misma
    razon: una linea reprogramada ya fue reemplazada y una cancelada no
    compromete nada, asi que exigirles coherencia con la fecha vigente de la
    orden seria exigirsela justo a las dos que por definicion no la tienen.
    """
    return (ProgramacionOrden.objects
            .filter(programacion=programacion,
                    estado__in=(ProgramacionOrden.PLANIFICADA,
                                ProgramacionOrden.CONFIRMADA))
            .select_related("orden")
            #  Tercera clave: sin ella dos lineas empatadas salen en orden
            #  arbitrario. Ver ORDEN_JORNADA -- 'id' se elige por no significar
            #  nada, no por significar algo.
            .order_by("dia", "secuencia", "id"))


def revisar_coherencia(programacion) -> list[str]:
    """
    Todo lo que impide publicar este plan. Lista vacia = coherente.

    Se devuelven TODOS los problemas y no el primero: quien tiene que
    arreglarlos prefiere verlos juntos a descubrirlos de a uno.

    NO CORRIGE NADA, a proposito. Una linea que no cuadra con su orden es un
    desacuerdo entre dos decisiones humanas, y elegir cual gana no es algo que
    esta funcion pueda saber.
    """
    problemas = []
    fin = programacion.semana_inicio + timedelta(days=6)

    for linea in _lineas_vigentes(programacion):
        orden = linea.orden
        etiqueta = f"linea {linea.id} (OT #{orden.numero})"

        if linea.org_id != programacion.org_id:
            problemas.append(
                f"{etiqueta}: la linea es de otra organizacion que el plan.")
        if orden.org_id != programacion.org_id:
            problemas.append(
                f"{etiqueta}: la orden es de otra organizacion que el plan.")

        if not (programacion.semana_inicio <= linea.dia <= fin):
            problemas.append(
                f"{etiqueta}: esta fechada el {linea.dia}, fuera de la semana "
                f"del {programacion.semana_inicio} al {fin}.")

        #  La coherencia que M03-B garantiza al escribir, comprobada aqui sobre
        #  lo que hay. Importa porque M03-B no es el unico escritor posible: el
        #  panel de Django tambien puede crear lineas, y no pasa por el servicio.
        if orden.programada_para is None:
            problemas.append(
                f"{etiqueta}: la orden no tiene 'programada_para'; el plan "
                f"dice {linea.dia} y la orden no dice nada.")
        else:
            dia_de_la_orden = timezone.localtime(orden.programada_para).date()
            if dia_de_la_orden != linea.dia:
                problemas.append(
                    f"{etiqueta}: el plan dice {linea.dia} y la orden dice "
                    f"{dia_de_la_orden}.")

    problemas.extend(_ordenes_con_dos_lineas_vigentes(programacion))
    return problemas


def _ordenes_con_dos_lineas_vigentes(programacion) -> list[str]:
    """
    I-1: una orden no puede tener mas de una linea vigente  --  paso M03-D3.2.

    POR QUE NO LA VEIA LA COMPROBACION DE ARRIBA
    ---------------------------------------------
    El bucle de 'revisar_coherencia' mira DE LA LINEA HACIA LA ORDEN y solo
    dentro de este plan. I-1 es la direccion contraria --de la orden hacia
    TODAS sus lineas-- y CRUZA PLANES: el caso tipico es una linea vigente aqui
    y otra vigente en el plan de la semana siguiente, que ninguna
    reprogramacion bien hecha produce pero el panel de Django si puede crear.

    POR QUE ES UN ERROR Y NO UN AVISO
    ----------------------------------
    'supervisor._programacion_vigente' hace '.first()' heredando el
    'Meta.ordering' de ProgramacionOrden, que es ["dia", "secuencia"]. Con dos
    lineas vigentes devuelve LA DEL DIA MAS TEMPRANO -- la obsoleta-- y M09
    razona sobre un plan que ya no rige SIN QUE NADA FALLE. Un aviso que se
    puede ignorar no protege de un error que no se ve.

    NO RESUELVE NADA
    ----------------
    No elige que linea gana, no borra ninguna y no toca la programacion.
    Elegir es una decision operativa: la funcion nombra la orden, las lineas y
    los planes, y se detiene ahi.
    """
    from django.db.models import Count

    #  Las ordenes que este plan toca. Si el plan esta vacio no hay nada que
    #  comprobar y la consulta agregada ni se dispara.
    ordenes = list(_lineas_vigentes(programacion)
                   .values_list("orden_id", flat=True))
    if not ordenes:
        return []

    #  "Vigente" es la definicion del modelo, la misma de '_lineas_vigentes' y
    #  de 'supervisor._programacion_vigente': planificada o confirmada.
    #  'reprogramada' y 'cancelada' son historia y no cuentan.
    vigentes = ProgramacionOrden.objects.filter(
        org=programacion.org_id,
        orden_id__in=ordenes,
        estado__in=(ProgramacionOrden.PLANIFICADA,
                    ProgramacionOrden.CONFIRMADA))

    duplicadas = (vigentes.values("orden_id")
                  .annotate(n=Count("id"))
                  .filter(n__gt=1)
                  .values_list("orden_id", flat=True))

    problemas = []
    for orden_id in duplicadas:
        lineas = (vigentes.filter(orden_id=orden_id)
                  .select_related("orden", "programacion")
                  .order_by("dia", "secuencia", "id"))
        numero = lineas[0].orden.numero
        detalle = "; ".join(
            f"linea {l.id} el {l.dia} en el plan de la semana del "
            f"{l.programacion.semana_inicio} (estado '{l.estado}')"
            for l in lineas)
        problemas.append(
            f"OT #{numero}: tiene {len(lineas)} lineas vigentes a la vez y "
            f"solo puede tener una -> {detalle}. Hay que decidir cual rige: "
            f"esta funcion no lo elige.")
    return problemas


@transaction.atomic
def publicar_programacion(*, org, programacion, actor, ahora=None):
    """
    Pasa un plan de 'borrador' a 'publicada'. Nada mas.

    Publicar NO ejecuta la programacion: no toca 'programada_para', ni el
    estado de ninguna orden, ni crea asignaciones. Hace explicito que el plan
    dejo de ser un borrador -- y eso es exactamente lo que la señal
    'programacion_sin_publicar' de M09 lleva midiendo desde que existe, sin
    que nadie pudiera apagarla.

    'actor' es obligatorio: publicar es una decision de una persona, y
    'publicada_por' existe justamente para que quede cual.
    """
    if actor is None:
        raise ErrorProgramacion(
            "Publicar es una decision de una persona: tiene que quedar quien "
            "la tomo.")
    if programacion.org_id != org.id:
        raise ErrorProgramacion("Ese plan semanal es de otra empresa.")

    #  El lock antes de leer el estado. Sin el, dos peticiones simultaneas leen
    #  'borrador' a la vez y las dos publican: la segunda pisaria 'publicada_en'
    #  y 'publicada_por' de la primera, y el plan terminaria diciendo que lo
    #  publico alguien que llego despues.
    fresco = (ProgramacionSemanal.objects
              .select_for_update()
              .get(pk=programacion.pk, org=org))

    if fresco.estado == ProgramacionSemanal.PUBLICADA:
        #  IDEMPOTENCIA SEMANTICA (M03-C §12): la segunda llamada NO repite la
        #  transicion. No hace falta mecanismo nuevo -- el estado ya es el
        #  registro de que la operacion ocurrio. Es una idempotencia distinta
        #  de la de 'manejar_idempotencia', que protege mutaciones EXTERNAS de
        #  un reintento; aqui no hay tercero, hay una maquina de estados.
        cuando = (f" el {fresco.publicada_en:%Y-%m-%d %H:%M}"
                  if fresco.publicada_en else "")
        raise PlanNoPublicable(
            f"El plan de la semana del {fresco.semana_inicio} ya estaba "
            f"publicado{cuando}.")
    if fresco.estado != ProgramacionSemanal.BORRADOR:
        raise PlanNoPublicable(
            f"El plan de la semana del {fresco.semana_inicio} esta "
            f"'{fresco.get_estado_display()}'. Solo se publica un borrador.")

    problemas = revisar_coherencia(fresco)
    if problemas:
        #  No se publica Y no se arregla nada. Publicar un plan que se
        #  contradice con las ordenes seria darle caracter de compromiso a algo
        #  que ya no describe la realidad.
        raise PlanIncoherente(
            f"El plan tiene {len(problemas)} inconsistencia(s) con las ordenes "
            f"que referencia. No se publica.", problemas)

    fresco.estado = ProgramacionSemanal.PUBLICADA
    fresco.publicada_en = ahora or timezone.now()
    fresco.publicada_por = actor
    #  'updated_by' va en la lista a proposito: BaseModel.save() lo escribe
    #  desde crum con el usuario de la peticion, y sin nombrarlo aqui el
    #  update_fields lo dejaria fuera del UPDATE. Es un segundo registro del
    #  actor, independiente de 'publicada_por' y que nadie puede pasar por
    #  payload.
    fresco.save(update_fields=["estado", "publicada_en", "publicada_por",
                               "updated_by", "updated_at"])
    return fresco


class PlanNoCerrable(ErrorProgramacion):
    """El plan no esta en un estado desde el que se pueda cerrar."""


def cerrar_programacion(*, org, programacion, actor, ahora=None):
    """
    Pasa un plan de 'publicada' a 'cerrada'. El ultimo paso del ciclo.

    POR QUE ESTA FUNCION NO EXISTIA
    -------------------------------
    'cerrada' estaba declarada en ESTADOS desde M03 y ninguna funcion la
    asignaba nunca. Un estado que no puede ocurrir es una promesa que el modelo
    no cumple: la semana pasada seguia figurando como 'publicada' para siempre,
    y la señal 'programacion_sin_publicar' no podia distinguir un plan vivo de
    uno que ya paso.

    SOLO DESDE 'publicada', Y NO DESDE 'borrador'
    ---------------------------------------------
    Cerrar un borrador seria archivar un plan que nadie llego a ver: si no
    sirvio, lo que corresponde es dejarlo como esta o no haberlo creado, no
    darle el sello de "esta semana termino". El ciclo declarado es
    borrador -> publicada -> cerrada, y esta funcion respeta las dos flechas.

    CERRAR NO TOCA NINGUNA ORDEN
    ----------------------------
    Ni las lineas del plan, ni 'programada_para', ni el estado operativo de
    nada. Igual que publicar: lo unico que cambia es que el plan deja de estar
    vigente. Una orden que quedo a medias sigue a medias y su propio cierre es
    otra operacion (campo/trabajos/<pk>/cerrar/).

    IDEMPOTENCIA SEMANTICA, LA MISMA QUE PUBLICAR
    ---------------------------------------------
    La segunda llamada no repite la transicion ni pisa 'cerrada_en': levanta
    'PlanNoCerrable' diciendo cuando se cerro. No hace falta un mecanismo
    nuevo -- el estado ES el registro de que la operacion ya ocurrio.
    """
    if actor is None:
        raise ErrorProgramacion(
            "Cerrar es una decision de una persona: tiene que quedar quien "
            "la tomo.")
    if programacion.org_id != org.id:
        raise ErrorProgramacion("Ese plan semanal es de otra empresa.")

    #  El lock antes de leer el estado, por el mismo motivo que en publicar:
    #  sin el, dos peticiones simultaneas leen 'publicada' a la vez y las dos
    #  cierran.
    fresco = (ProgramacionSemanal.objects
              .select_for_update()
              .get(pk=programacion.pk, org=org))

    if fresco.estado == ProgramacionSemanal.CERRADA:
        raise PlanNoCerrable(
            f"El plan de la semana del {fresco.semana_inicio} ya estaba "
            f"cerrado.")
    if fresco.estado != ProgramacionSemanal.PUBLICADA:
        raise PlanNoCerrable(
            f"El plan de la semana del {fresco.semana_inicio} esta "
            f"'{fresco.get_estado_display()}'. Solo se cierra un plan "
            f"publicado: cerrar un borrador archivaria algo que nadie vio.")

    fresco.estado = ProgramacionSemanal.CERRADA
    #  'updated_by' va nombrado a proposito, igual que en publicar: BaseModel
    #  lo escribe desde crum y sin listarlo el update_fields lo dejaria fuera.
    fresco.save(update_fields=["estado", "updated_by", "updated_at"])
    return fresco


# =============================================================================
#  REPROGRAMAR  --  paso M03-D3
# =============================================================================
#  Reprogramar no es "programar otra vez": es la primera operacion de M03 que
#  tiene que CONSERVAR LO QUE DEJA DE SER CIERTO.
#
#  LA FRONTERA NO ES 'iniciada_en', Y ESO SE MIDIO
#  -----------------------------------------------
#  'iniciada_en' se escribe UNA SOLA VEZ (transiciones.py: "and not
#  orden.iniciada_en"), asi que con esa regla un trabajo devuelto por
#  correccion no podria recibir fecha nueva NUNCA MAS -- justo el caso que mas
#  la necesita.
#
#  La distincion si es determinable con los datos que ya existen:
#
#      requerir_correccion()  ->  EventoTrabajo tipo="reapertura_correccion"
#      cualquier inicio       ->  EventoTrabajo datos["nuevo_estado"] en
#                                 {"en_camino", "en_sitio"}
#
#  'EventoTrabajo' es append-only y ordenado por fecha, de modo que LA VUELTA
#  ACTUAL EMPEZO si y solo si hay un inicio posterior a la ultima reapertura.
#  Sin reaperturas, eso equivale exactamente a 'iniciada_en IS NOT NULL'.
#
#  SE ANCLA EN 'nuevo_estado' Y NO EN EL NOMBRE DEL EVENTO
#  -------------------------------------------------------
#  '_aplicar_transicion' escribe {"estado_anterior", "nuevo_estado", ...} en
#  TODOS los eventos de transicion. Mirar 'nuevo_estado' sobrevive a que manana
#  alguien agregue una accion operativa nueva; una lista de nombres de evento
#  habria que mantenerla a mano.
# =============================================================================

RUTA_NORMAL = "normal"
RUTA_CORRECCION = "correccion"
RUTA_CONTINGENCIA = "contingencia"

#  Los estados a los que se entra cuando el trabajo arranca. Salen de
#  transiciones.py:293, que es donde el sistema decide escribir 'iniciada_en'.
ESTADOS_DE_INICIO = ("en_camino", "en_sitio")

EVENTO_REAPERTURA = "reapertura_correccion"

#  La causa de una reprogramacion es una causa, nunca el efecto. El catalogo es
#  el que ya existe y es cerrado; 'reprogramacion' queda fuera a proposito --
#  usarla como causa perderia POR QUE se movio el trabajo, que es el unico dato
#  que la bitacora no puede reconstruir sola.
CAUSAS_VALIDAS = frozenset(
    t for t, _ in NovedadOperativa.TIPOS if t != NovedadOperativa.REPROGRAMACION
)


class NoEstaProgramada(ErrorProgramacion):
    """No habia programacion previa: esto es programar, no reprogramar."""


class RequiereContingencia(ErrorProgramacion):
    """
    La vuelta actual ya arranco.

    Es una excepcion y NO una rama silenciosa a proposito: si 'reprogramar'
    registrara una contingencia por su cuenta, haria algo distinto de lo que le
    pidieron y contestaria 2xx. La contingencia tiene que ser un acto
    deliberado.
    """


class YaEnEsaFecha(ErrorProgramacion):
    """
    El destino coincide con la programacion vigente: se RECHAZA.

    DECISION EMPRESARIAL APROBADA (M03-D3.2). No es provisional.

    Si la orden ya tiene exactamente esa fecha en ese mismo plan, no hay cambio
    que registrar: no se crea linea, no se escribe evento de reprogramacion, no
    se toca 'programada_para' y no sube 'revision'. La bitacora solo contiene
    cambios que ocurrieron -- y como es append-only, un evento con
    anterior == nuevo no se podria quitar despues.
    """


def clasificar_ruta(orden) -> str:
    """
    Que ruta le corresponde a esta orden. Lectura pura, sin efectos.

    Se expone para que una pantalla pueda saber que formulario mostrar ANTES de
    enviar nada, en vez de descubrirlo con un 409.
    """
    ultima_reapertura = (EventoTrabajo.objects
                         .filter(orden=orden, tipo=EVENTO_REAPERTURA)
                         .order_by("-created_at")
                         .first())

    if ultima_reapertura is None:
        #  El fallback aprobado: sin devoluciones, 'iniciada_en' contesta
        #  exactamente lo mismo.
        return RUTA_CONTINGENCIA if orden.iniciada_en else RUTA_NORMAL

    inicio_posterior = (EventoTrabajo.objects
                        .filter(orden=orden,
                                datos__nuevo_estado__in=ESTADOS_DE_INICIO,
                                created_at__gt=ultima_reapertura.created_at)
                        .exists())
    return RUTA_CONTINGENCIA if inicio_posterior else RUTA_CORRECCION


def _validar_causa(causa: str, motivo: str, *, exigida: bool, donde: str):
    """La causa pertenece al catalogo cerrado, y no puede ser el efecto."""
    causa = (causa or "").strip()
    if not causa:
        if exigida:
            raise ErrorProgramacion(
                f"{donde} exige decir por que. Sin causa, nadie puede saber "
                f"despues por que se movio el trabajo.")
        return "", (motivo or "").strip()
    if causa == NovedadOperativa.REPROGRAMACION:
        raise ErrorProgramacion(
            "'reprogramacion' es el efecto, no la causa. La causa es lo que "
            "obligo a mover el trabajo: una ausencia, un bloqueo, una "
            "dependencia.")
    if causa not in CAUSAS_VALIDAS:
        raise ErrorProgramacion(
            f"'{causa}' no esta en el catalogo de causas. Validas: "
            f"{sorted(CAUSAS_VALIDAS)}.")
    return causa, (motivo or "").strip()


def _bloque_sla(orden) -> dict:
    """
    Lo que se sabe del SLA, que hoy es que no se puede saber.

    Reprogramar no extiende, no reinicia y no modifica el SLA -- y no hay nada
    que impedir: 'Case._sla_deadline' camina horas habiles desde
    'Case.created_at' y no lee 'programada_para'. Lo que no se puede es
    EVALUAR si la fecha nueva cae despues del vencimiento, porque OrdenTrabajo
    no tiene FK a Case y crearla esta expresamente prohibido.
    """
    if orden.origen_tipo == "case" and (orden.origen_ref or "").strip():
        return {"evaluado": False,
                "razon": ("la orden referencia un caso por texto "
                          "('origen_ref'), pero no existe vinculo que permita "
                          "evaluarlo")}
    return {"evaluado": False, "razon": "la orden no tiene caso vinculado"}


def _foto(orden, linea):
    """Los valores ANTES de tocarlos. Se leen de la fila bloqueada."""
    return {
        "programada_para": (orden.programada_para.isoformat()
                            if orden.programada_para else None),
        "dia": str(linea.dia) if linea else None,
        "hora_inicio": str(linea.hora_inicio) if linea and linea.hora_inicio else None,
        "plan": str(linea.programacion_id) if linea else None,
        "plan_estado": linea.programacion.estado if linea else None,
        "linea": str(linea.id) if linea else None,
    }


def _novedad_de(org, orden, actor, causa, motivo, anterior_dt, nueva_dt):
    """La CAUSA va aca; el efecto va a la bitacora. Nunca al reves."""
    if not causa:
        return None
    return NovedadOperativa.objects.create(
        org=org,
        tipo=causa,
        descripcion=motivo,
        orden=orden,
        registrada_por=actor,
        programada_anterior=anterior_dt,
        programada_nueva=nueva_dt,
    )


@transaction.atomic
def reprogramar_orden(*, org, orden, programada_para, programacion_destino,
                      actor, causa: str = "", motivo: str = "",
                      contexto: dict | None = None):
    """
    Cambia el cuando de una orden que YA tenia un cuando.

    Cubre las rutas NORMAL y CORRECCION. Si la vuelta actual ya arranco levanta
    'RequiereContingencia': no decide por su cuenta registrar una contingencia.

    Devuelve (linea_vigente, evento, novedad).
    """
    if actor is None:
        raise ErrorProgramacion(
            "Reprogramar es una decision de una persona: tiene que quedar "
            "quien la tomo.")
    if programada_para is None:
        raise ErrorProgramacion("Falta la fecha y hora nuevas.")
    if timezone.is_naive(programada_para):
        raise ErrorProgramacion(
            "La fecha de programacion tiene que traer zona horaria.")
    if orden.org_id != org.id:
        raise ErrorProgramacion("Esa orden es de otra empresa.")
    if programacion_destino.org_id != org.id:
        raise ErrorProgramacion("Ese plan semanal es de otra empresa.")

    #  LOS LOCKS, EN ORDEN FIJO: ORDEN PRIMERO, PLAN DESPUES.
    #  ------------------------------------------------------
    #  No es arbitrario. M03-B bloquea solo la orden y M03-C solo el plan, asi
    #  que con este orden ninguna de las tres espera por otra y no hay ciclo.
    #  Invertirlo si podria producir un interbloqueo el dia que alguien escriba
    #  una operacion que tome el plan primero.
    fresca = (OrdenTrabajo.objects
              .select_for_update()
              .get(pk=orden.pk, org=org))
    destino = (ProgramacionSemanal.objects
               .select_for_update()
               .get(pk=programacion_destino.pk, org=org))

    ruta = clasificar_ruta(fresca)
    if ruta == RUTA_CONTINGENCIA:
        raise RequiereContingencia(
            f"La orden #{fresca.numero} ya arranco la vuelta {fresca.vuelta}. "
            f"Mover la fecha de un trabajo en curso no es reprogramar: hay que "
            f"registrar una contingencia.")

    if fresca.estado_operativo in (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA):
        raise ErrorProgramacion(
            f"La orden #{fresca.numero} esta "
            f"'{fresca.get_estado_operativo_display()}'. No se reprograma un "
            f"trabajo terminado.")

    linea_vigente = _programacion_vigente_de(org, fresca)
    if fresca.programada_para is None and linea_vigente is None:
        raise NoEstaProgramada(
            f"La orden #{fresca.numero} no esta programada. Ponerle fecha por "
            f"primera vez es programar, no reprogramar.")

    if destino.estado not in ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS:
        raise PlanNoPublicable(
            f"El plan de la semana del {destino.semana_inicio} esta "
            f"'{destino.get_estado_display()}'. No se agregan ordenes a un "
            f"plan cerrado.")

    dia, hora = _dia_y_hora(programada_para)
    fin = destino.semana_inicio + timedelta(days=6)
    if not (destino.semana_inicio <= dia <= fin):
        raise ErrorProgramacion(
            f"El {dia} cae fuera del plan de la semana del "
            f"{destino.semana_inicio} (hasta el {fin}).")

    mismo_plan = (linea_vigente is not None
                  and linea_vigente.programacion_id == destino.id)

    #  [BLOQUEADO] Ver la docstring de YaEnEsaFecha.
    if mismo_plan and fresca.programada_para == programada_para:
        raise YaEnEsaFecha(
            f"La orden #{fresca.numero} ya esta programada para esa misma "
            f"fecha en ese mismo plan. No hay nada que mover.")

    #  El motivo es obligatorio cuando hay compromiso: un plan publicado ya lo
    #  vieron las cuadrillas, y una correccion ya consumio trabajo. Un borrador
    #  no compromete a nadie, asi que no se exige.
    plan_origen_publicado = (
        linea_vigente is not None
        and linea_vigente.programacion.estado == ProgramacionSemanal.PUBLICADA)
    exige_causa = (ruta == RUTA_CORRECCION
                   or destino.estado == ProgramacionSemanal.PUBLICADA
                   or plan_origen_publicado)
    causa, motivo = _validar_causa(
        causa, motivo, exigida=exige_causa,
        donde=("Una reprogramacion por correccion" if ruta == RUTA_CORRECCION
               else "Reprogramar sobre un plan publicado"))

    #  R-8': LOS VALORES ANTERIORES SE CAPTURAN ANTES DE MUTAR.
    #  --------------------------------------------------------
    #  El orden de las escrituras dentro de la transaccion da igual --si algo
    #  falla se deshace todo--; lo que no da igual es LEER ANTES DE
    #  SOBRESCRIBIR. Lo que habia que proteger no era el orden de los INSERT:
    #  era no perder 'programada_para', 'dia' y el plan al pisarlos.
    anterior = _foto(fresca, linea_vigente)
    programada_anterior = fresca.programada_para

    if mismo_plan:
        #  LA CONSTRAINT MANDA: unique(programacion, orden) impide una segunda
        #  linea en el mismo plan, asi que dentro de una semana la linea se
        #  ACTUALIZA. El historial no se pierde -- vive en el evento, que es
        #  append-only. Lo que no se sobrescribe es el registro, no la fila.
        linea_vigente.dia = dia
        linea_vigente.hora_inicio = hora
        linea_vigente.save(update_fields=["dia", "hora_inicio",
                                          "updated_by", "updated_at"])
        linea_final = linea_vigente
    else:
        #  Una linea NUNCA cambia de plan: se marca y se crea otra. Asi el plan
        #  viejo sigue diciendo lo que decia.
        ya_en_destino = ProgramacionOrden.objects.filter(
            org=org, programacion=destino, orden=fresca).first()
        if ya_en_destino is not None:
            raise ErrorProgramacion(
                f"La orden #{fresca.numero} ya tiene una linea en el plan de "
                f"la semana del {destino.semana_inicio} (estado "
                f"'{ya_en_destino.estado}'). La restriccion de la base admite "
                f"una sola por plan.")
        if linea_vigente is not None:
            linea_vigente.estado = ProgramacionOrden.REPROGRAMADA
            linea_vigente.save(update_fields=["estado", "updated_by",
                                              "updated_at"])
        try:
            #  LOS TRES ATRIBUTOS DE PLANIFICACION VIAJAN JUNTOS  --  M03-D3.2
            #  ---------------------------------------------------------------
            #  'zona', 'prioridad' y 'secuencia' describen COMO se penso la
            #  linea, y hasta D3 se arrastraban dos y se perdia la tercera: la
            #  nueva nacia con 'secuencia' en el default.
            #
            #  El efecto medido en D3.1 era que la MISMA operacion se comportaba
            #  distinto segun el caso -- dentro del mismo plan la linea se
            #  actualiza y conserva su secuencia; al cambiar de plan se recreaba
            #  y la perdia. Nadie decidio esa diferencia.
            #
            #  Arrastrar los tres iguala los dos casos SIN agregar conducta:
            #  no se compacta nada, no se reordena ninguna otra orden y
            #  'secuencia' sigue siendo lo que el modelo dice que es, el ORDEN
            #  PROPUESTO.
            linea_final = ProgramacionOrden.objects.create(
                org=org, programacion=destino, orden=fresca,
                dia=dia, hora_inicio=hora,
                #  Sin linea previa no hay nada que arrastrar: valen los
                #  defaults del modelo, que es lo mismo que hacia antes.
                **({"zona": linea_vigente.zona,
                    "prioridad": linea_vigente.prioridad,
                    "secuencia": linea_vigente.secuencia}
                   if linea_vigente else {}),
                estado=ProgramacionOrden.PLANIFICADA)
        except IntegrityError as e:
            raise ErrorProgramacion(
                f"La base rechazo la linea de plan: "
                f"{str(e).strip().splitlines()[0]}") from e

    fresca.programada_para = programada_para
    #  Igual que M03-B y 'despacho.asignar': cambia el dia del trabajo, asi que
    #  la cola offline del tecnico tiene que enterarse.
    fresca.revision += 1
    fresca.save(update_fields=["programada_para", "revision",
                               "updated_by", "updated_at"])
    #  'iniciada_en' NO se toca: el codigo lo trata como el primer inicio
    #  historico, y reescribirlo borraria cuando empezo el trabajo de verdad.
    #  'estado_operativo' tampoco: reprogramar no es una transicion.

    novedad = _novedad_de(org, fresca, actor, causa, motivo,
                          programada_anterior, programada_para)

    evento = EventoTrabajo.objects.create(
        org=org, orden=fresca,
        tipo=("reprogramacion_por_correccion" if ruta == RUTA_CORRECCION
              else "reprogramacion"),
        profile=actor,
        datos={
            "ruta": ruta,
            "vuelta": fresca.vuelta,
            "anterior": anterior,
            "nuevo": _foto(fresca, linea_final),
            "causa": causa,
            "motivo": motivo,
            "novedad": str(novedad.id) if novedad else None,
            "contexto": contexto or {},
            "sla": _bloque_sla(fresca),
        })
    return linea_final, evento, novedad


@transaction.atomic
def registrar_contingencia(*, org, orden, actor, causa: str, motivo: str = "",
                           contexto: dict | None = None):
    """
    Una orden en curso se complico. Se registra; NO se reprograma.

    'programada_para' dice lo que se PLANIFICO; 'iniciada_en' y
    'completada_campo_en' dicen lo que PASO. Un trabajo que se complico no
    necesita que le reescriban el plan: necesita que quede por que. Reescribirlo
    borraria justo la diferencia entre lo previsto y lo ocurrido.

    Devuelve (novedad, evento).
    """
    if actor is None:
        raise ErrorProgramacion(
            "Una contingencia sin actor no se registra.")
    if orden.org_id != org.id:
        raise ErrorProgramacion("Esa orden es de otra empresa.")

    fresca = (OrdenTrabajo.objects
              .select_for_update()
              .get(pk=orden.pk, org=org))

    causa, motivo = _validar_causa(causa, motivo, exigida=True,
                                   donde="Una contingencia")

    linea_vigente = _programacion_vigente_de(org, fresca)
    #  'programada_nueva' queda en None: una contingencia no propone fecha.
    novedad = NovedadOperativa.objects.create(
        org=org, tipo=causa, descripcion=motivo, orden=fresca,
        registrada_por=actor,
        programada_anterior=fresca.programada_para,
        programada_nueva=None)

    evento = EventoTrabajo.objects.create(
        org=org, orden=fresca, tipo="contingencia", profile=actor,
        datos={
            "ruta": RUTA_CONTINGENCIA,
            "vuelta": fresca.vuelta,
            "anterior": _foto(fresca, linea_vigente),
            "nuevo": None,
            "causa": causa,
            "motivo": motivo,
            "novedad": str(novedad.id),
            "contexto": contexto or {},
            "sla": _bloque_sla(fresca),
            "estado_operativo": fresca.estado_operativo,
        })
    #  NO se toca: programada_para, la linea, estado_operativo ni revision.
    return novedad, evento


# =============================================================================
#  LA JORNADA: LEERLA, Y LEERLA SIEMPRE IGUAL  --  paso M03-E2
# =============================================================================
#  M03-E1 midio dos cosas que este bloque atiende, y ninguna mas:
#
#    1. 'secuencia' era de SOLO ESCRITURA. Se podia enviar por la API y no
#       habia forma de volver a verla: ni respuesta, ni endpoint de lectura,
#       ni pantalla. Una regla de ordenamiento sobre un campo que nadie puede
#       observar no se puede comprobar.
#
#    2. El orden era ARBITRARIO en los empates. 'ordering' tiene dos claves
#       --dia y secuencia-- y ninguna tercera, asi que dos lineas empatadas
#       salen en el orden que produzca el plan de ejecucion, que puede cambiar
#       entre dos consultas identicas.
#
#  Y el empate NO es un borde: 'secuencia' es opcional con default 0, de modo
#  que un plan que nadie secuencio tiene TODAS sus lineas empatadas.
#
#  LO QUE ESTE BLOQUE NO HACE
#  --------------------------
#  No recompacta, no reasigna, no valida, no convierte 'secuencia' en prioridad
#  ni en compromiso, y no decide que significa el 0. E1 dejo esas decisiones
#  abiertas (E-1, E-2, E-4, E-5) y aqui solo se mide.
# =============================================================================

#  EL DESEMPATE, Y POR QUE ES 'id' Y NO OTRA COSA
#  ----------------------------------------------
#  Hacia falta una tercera clave para que la lectura sea REPRODUCIBLE. Las
#  candidatas existentes eran tres, y dos se descartaron por decir demasiado:
#
#    hora_inicio  es nullable y tiene lectura operativa ("el que empieza antes
#                 va primero"). Elegirla seria decidir una regla de orden.
#    created_at   tiene lectura de politica ("el que se registro primero va
#                 primero"). Mismo problema.
#    id           UUID4: unico, NOT NULL, y SIN NINGUN significado. No se puede
#                 malinterpretar como prioridad, ni como decision operativa,
#                 ni como ruta.
#
#  Se elige 'id' precisamente porque no dice nada. Dos lineas empatadas ESTAN
#  empatadas: el sistema no tiene con que ordenarlas, y fingir un criterio
#  seria peor que mostrar un orden estable y declarar el empate -- que es lo
#  que hace 'resumen_de_jornada'.
ORDEN_JORNADA = ("dia", "secuencia", "id")


def lineas_de_jornada(org, *, programacion=None, dia=None):
    """
    Las lineas VIGENTES que rigen, en orden reproducible.

    'vigente' es la definicion del modelo, la misma de '_lineas_vigentes' y de
    'supervisor._programacion_vigente': planificada o confirmada. Una linea
    'reprogramada' o 'cancelada' es historia y no aparece.
    """
    qs = (ProgramacionOrden.objects
          .filter(org=org,
                  estado__in=(ProgramacionOrden.PLANIFICADA,
                              ProgramacionOrden.CONFIRMADA))
          .select_related("orden", "programacion"))
    if programacion is not None:
        qs = qs.filter(programacion=programacion)
    if dia is not None:
        qs = qs.filter(dia=dia)
    return qs.order_by(*ORDEN_JORNADA)


def resumen_de_jornada(lineas) -> dict:
    """
    Lo que se puede MEDIR de un conjunto de lineas, sin interpretarlo.

    Deliberadamente NO llama al 0 "sin ordenar" ni "primera": M03-E1 dejo esa
    lectura abierta (E-2) y el repositorio no la sustenta. Aqui hay conteos, y
    quien decida vera numeros en vez de una etiqueta que ya decide por el.

    Tampoco marca el empate como error ni como aviso: lo cuenta. Que un empate
    sea un problema es la decision E-5, que sigue pendiente.
    """
    lineas = list(lineas)
    por_dia = {}
    for linea in lineas:
        por_dia.setdefault(linea.dia, []).append(linea)

    dias = []
    lineas_empatadas = 0
    for dia in sorted(por_dia):
        del_dia = por_dia[dia]
        conteo = {}
        for linea in del_dia:
            conteo[linea.secuencia] = conteo.get(linea.secuencia, 0) + 1
        #  EL 0 NO EMPATA  --  corregido en M03-E5-B
        #  ------------------------------------------
        #  'secuencia = 0' significa SIN SECUENCIAR (decision E-2, aprobada
        #  despues de que se escribiera este resumen). Varias lineas sin
        #  secuenciar no compiten por ninguna posicion, asi que contarlas como
        #  empate era afirmar un conflicto que la regla dice que no existe --
        #  y ademas contradecia a '_empate_de', que ya lo trataba bien.
        grupos = {s: n for s, n in conteo.items() if n > 1 and s > 0}
        afectadas = sum(grupos.values())
        lineas_empatadas += afectadas
        sin_secuenciar = sum(1 for x in del_dia if x.secuencia == 0)
        dias.append({
            "dia": str(dia),
            "lineas": len(del_dia),
            "secuencia_cero": sum(1 for x in del_dia if x.secuencia == 0),
            "secuencia_mayor_que_cero": sum(1 for x in del_dia if x.secuencia > 0),
            "secuencias_empatadas": sorted(grupos),
            "lineas_en_empate": afectadas,
            #  Si todas las lineas del dia comparten numero, el orden que
            #  devuelve la consulta es estable pero no significa nada. Decirlo
            #  es mas util que dejar que parezca una decision.
            #  "lo que ves no significa nada": o el dia entero esta sin
            #  secuenciar, o todas sus lineas empatan. En los dos casos el
            #  orden que devuelve la consulta es estable y arbitrario, y
            #  decirlo es mas util que dejar que parezca una decision.
            "orden_arbitrario": len(del_dia) > 1 and (
                sin_secuenciar == len(del_dia) or afectadas == len(del_dia)),
        })

    return {
        "lineas": len(lineas),
        "secuencia_cero": sum(1 for x in lineas if x.secuencia == 0),
        "secuencia_mayor_que_cero": sum(1 for x in lineas if x.secuencia > 0),
        "lineas_en_empate": lineas_empatadas,
        "dias": dias,
        "desempate": " -> ".join(ORDEN_JORNADA),
        "nota": ("'secuencia' es el orden propuesto; 0 significa SIN "
                 "SECUENCIAR y no empata con nada. Los empates se cuentan, "
                 "no se resuelven: el desempate por 'id' solo hace la lectura "
                 "reproducible y no expresa ninguna prioridad."),
    }


# =============================================================================
#  CAMBIAR LA POSICION PROPUESTA DE UNA LINEA  --  paso M03-E4
# =============================================================================
#  CAMBIAR LA SECUENCIA NO ES REPROGRAMAR, Y ESA ES LA RAZON DE SER
#  ----------------------------------------------------------------
#  Hasta M03-E4 la unica forma de tocar la 'secuencia' de una linea ya escrita
#  era reprogramar la orden -- o sea, mover el TRABAJO para corregir el ORDEN
#  en que se propone hacerlo. Son dos cosas distintas: el 'cuando' no cambia,
#  cambia la posicion dentro de ese mismo dia.
#
#  Por eso esta operacion NO toca: 'programada_para', el dia, el plan, la
#  orden, la zona, la prioridad, el estado operativo ni el de validacion.
#
#  QUE SIGNIFICA EL 0  --  DECISION EMPRESARIAL APROBADA (M03-E4)
#  --------------------------------------------------------------
#  'secuencia = 0' significa SIN SECUENCIAR. NO es la primera posicion.
#  De ahi se sigue, y se implementa asi:
#
#    * varias lineas en 0 NO son un empate -- estan todas sin secuenciar;
#    * poner 0 es una operacion legitima: es DESsecuenciar;
#    * el 0 no expresa prioridad.
#
#  LOS DUPLICADOS > 0 SE PERMITEN  --  DECISION EMPRESARIAL APROBADA
#  -----------------------------------------------------------------
#  No se recompacta, no se reasigna y no se toca ninguna otra linea. El empate
#  queda observable por la lectura de jornada de M03-E2, y se ANOTA en el
#  evento; no se corrige.
# =============================================================================


def _empate_de(linea, secuencia) -> dict:
    """
    Con que otras lineas del mismo dia quedaria empatada. NO valida: describe.

    El 0 no cuenta como empate: significa SIN SECUENCIAR, y varias lineas sin
    secuenciar no compiten por ninguna posicion.
    """
    if secuencia == 0:
        return {"hay_empate": False,
                "razon": "secuencia 0 significa sin secuenciar: no hay empate"}
    otras = list(ProgramacionOrden.objects
                 .filter(org=linea.org_id,
                         programacion=linea.programacion_id,
                         dia=linea.dia,
                         secuencia=secuencia,
                         estado__in=(ProgramacionOrden.PLANIFICADA,
                                     ProgramacionOrden.CONFIRMADA))
                 .exclude(pk=linea.pk)
                 .select_related("orden")
                 .order_by(*ORDEN_JORNADA))
    return {
        "hay_empate": bool(otras),
        "con": [{"linea": str(o.id), "orden": o.orden.numero} for o in otras],
    }


@transaction.atomic
def actualizar_secuencia(*, org, linea, secuencia, actor, causa: str = "",
                         motivo: str = "", contexto: dict | None = None):
    """
    Cambia la posicion propuesta de una linea. Nada mas.

    Devuelve (linea, evento, novedad|None).
    """
    if actor is None:
        raise ErrorProgramacion(
            "Cambiar el orden propuesto es una decision de una persona: tiene "
            "que quedar quien la tomo.")
    if secuencia is None:
        raise ErrorProgramacion("Falta la secuencia.")
    if secuencia < 0:
        #  La base tambien lo impide (CHECK secuencia >= 0) y el serializador
        #  tambien (min_value=0). Se comprueba aqui igual para que quien llame
        #  al servicio directo reciba un error legible en vez de IntegrityError.
        raise ErrorProgramacion("La secuencia no puede ser negativa.")
    if linea.org_id != org.id:
        raise ErrorProgramacion("Esa linea de plan es de otra empresa.")

    #  LOS DOS LOCKS, EN ORDEN FIJO: LINEA PRIMERO, PLAN DESPUES.
    #  ----------------------------------------------------------
    #  Mismo criterio que M03-D3: el plan se bloquea SIEMPRE el ultimo, asi
    #  ninguna operacion del modulo espera por otra y no hay ciclo. Se piden por
    #  separado y sin 'select_related' a proposito: un FOR UPDATE sobre un JOIN
    #  bloquearia filas de las tablas unidas, que es justo lo que no hace falta.
    fresca = (ProgramacionOrden.objects
              .select_for_update()
              .get(pk=linea.pk, org=org))
    plan = (ProgramacionSemanal.objects
            .select_for_update()
            .get(pk=fresca.programacion_id, org=org))

    anterior = fresca.secuencia
    if anterior == secuencia:
        #  NO-OP  --  DECISION B-1 (M03-B1), unifica E4 con E5
        #  --------------------------------------------------
        #  Pedir el estado que ya rige no es un error: es una peticion valida
        #  cuyo efecto ya esta aplicado. Hasta M03-B1 esta via devolvia 409
        #  mientras la de jornada (E5) devolvia 200 al mismo hecho, y un
        #  cliente que usara las dos veia dos respuestas distintas para lo
        #  mismo.
        #
        #  Lo que NO cambia es lo que se escribe: NADA. No hay evento, porque
        #  la bitacora solo contiene cambios que ocurrieron; no hay novedad; no
        #  se toca la fila. Ni siquiera se valida la causa -- una peticion que
        #  no cambia nada no tiene nada que justificar, igual que en E5.
        #
        #  El 409 queda para lo que de verdad es un conflicto: que alguien haya
        #  cambiado la linea mientras tanto.
        return fresca, None, None

    #  UN PLAN PUBLICADO YA LO VIERON LAS CUADRILLAS
    #  ----------------------------------------------
    #  P-4 (M03-D1.1) dejo aprobado que publicar NO congela, pero que toda
    #  modificacion posterior es FORMAL y trazable; y D1.1-D, que el motivo es
    #  obligatorio cuando hay compromiso operativo. Un plan publicado lo es.
    #  Sobre un borrador no se exige nada: "un borrador no compromete a nadie".
    es_formal = (plan.estado == ProgramacionSemanal.PUBLICADA)
    causa, motivo = _validar_causa(
        causa, motivo, exigida=es_formal,
        donde="Cambiar el orden de un plan ya publicado")

    #  El empate se calcula ANTES de escribir, con el valor nuevo: es un dato
    #  del evento, no una validacion. Ningun empate impide el cambio.
    empate = _empate_de(fresca, secuencia)

    fresca.secuencia = secuencia
    #  Solo la secuencia y las columnas de auditoria. 'dia', 'hora_inicio',
    #  'zona', 'prioridad', 'estado', 'orden' y 'programacion' quedan fuera de
    #  la lista a proposito: esta operacion no los toca.
    fresca.save(update_fields=["secuencia", "updated_by", "updated_at"])

    novedad = _novedad_de(org, fresca.orden, actor, causa, motivo,
                          None, None) if causa else None

    evento = EventoTrabajo.objects.create(
        org=org, orden_id=fresca.orden_id,
        tipo=("secuencia_en_plan_publicado" if es_formal else "secuencia"),
        profile=actor,
        datos={
            "linea": str(fresca.id),
            "anterior": anterior,
            "nuevo": secuencia,
            #  El 0 se declara, no se deduce: quien lea el evento no tiene por
            #  que recordar que significa.
            "anterior_sin_secuenciar": anterior == 0,
            "nuevo_sin_secuenciar": secuencia == 0,
            "plan": str(plan.id),
            "plan_semana": str(plan.semana_inicio),
            "plan_estado": plan.estado,
            "dia": str(fresca.dia),
            "empate": empate,
            "causa": causa,
            "motivo": motivo,
            "novedad": str(novedad.id) if novedad else None,
            "contexto": contexto or {},
        })
    return fresca, evento, novedad


# =============================================================================
#  SECUENCIAR UNA JORNADA ENTERA  --  paso M03-E5-B
# =============================================================================
#  POR QUE UNA OPERACION DE CONJUNTO
#  ---------------------------------
#  Con M03-E4, poner tres ordenes en 1-2-3 eran TRES peticiones, TRES
#  transacciones y TRES eventos. Entre la primera y la tercera el plan pasaba
#  por estados intermedios que un lector de la jornada podia ver: 1-2-2, o
#  1-1-3. Aqui la jornada queda como el usuario la dejo, o no queda de ninguna
#  forma.
#
#  LA UNIDAD ES (organizacion, dia)  --  E5-A
#  ------------------------------------------
#  No el plan --una semana son seis jornadas y secuenciar el lunes no deberia
#  bloquear el jueves-- ni un conjunto suelto de lineas, que permitiria mezclar
#  dias sin que nada lo notase. El plan se pide ademas del dia porque es la
#  autoridad sobre "publicado o borrador", y porque exigirlo convierte en
#  comprobacion el hecho de que una linea pueda estar fechada fuera de la
#  semana de su plan (lo permite el panel de Django; lo detecta
#  'revisar_coherencia' al publicar).
#
#  EL CLIENTE DECLARA LO QUE LEYO, Y ESO NO ES UN ADORNO
#  -----------------------------------------------------
#  Cada linea del cuerpo trae 'secuencia_leida' ademas de 'secuencia'. Sin ese
#  dato la regla aprobada --"no sobrescribir silenciosamente cambios
#  concurrentes"-- seria INAPLICABLE: 'ProgramacionOrden' no tiene campo de
#  concurrencia optimista (ni 'revision' ni version, a diferencia de
#  OrdenTrabajo), asi que el unico token de version disponible es lo que el
#  cliente afirma haber visto.
# =============================================================================


class JornadaCambio(ErrorProgramacion):
    """
    Alguien toco la jornada entre que el cliente la leyo y la envio.

    Trae 'conflictos': que linea, que leyo el cliente y que hay de verdad. No
    se aplica NADA -- ni las lineas que si coincidian. Aplicar a medias seria
    exactamente lo que esta operacion existe para evitar.
    """

    def __init__(self, mensaje, conflictos):
        super().__init__(mensaje)
        self.conflictos = conflictos


class JornadaIncompleta(ErrorProgramacion):
    """
    El conjunto enviado no es el conjunto real de la jornada.

    Trae 'faltantes' y 'sobrantes'. G-2 decidio que la peticion representa el
    ESTADO COMPLETO que el usuario deja para ese dia, asi que una linea que no
    viene no significa "dejala como esta": significa que el cliente no vio la
    jornada que hay.
    """

    def __init__(self, mensaje, faltantes=None, sobrantes=None,
                 desconocidas=None, ajenas=None):
        super().__init__(mensaje)
        self.faltantes = faltantes or []
        self.sobrantes = sobrantes or []
        self.desconocidas = desconocidas or []
        self.ajenas = ajenas or []


def _semana_de(plan, dia) -> bool:
    return plan.semana_inicio <= dia <= plan.semana_inicio + timedelta(days=6)


@transaction.atomic
def secuenciar_jornada(*, org, plan, dia, lineas, actor, causa: str = "",
                       motivo: str = "", contexto: dict | None = None) -> dict:
    """
    Aplica de una sola vez el orden propuesto de una jornada.

    'lineas' es una lista de dicts {linea, secuencia_leida, secuencia}.

    Devuelve un resumen: jornada, recibidas, modificadas, sin_cambio, lote y
    resultado. Todo o nada.
    """
    if actor is None:
        raise ErrorProgramacion(
            "Secuenciar una jornada es una decision de una persona: tiene que "
            "quedar quien la tomo.")
    if plan.org_id != org.id:
        raise ErrorProgramacion("Ese plan semanal es de otra empresa.")
    if not _semana_de(plan, dia):
        raise ErrorProgramacion(
            f"El {dia} no cae en la semana del plan ({plan.semana_inicio} a "
            f"{plan.semana_inicio + timedelta(days=6)}).")

    pedidas = {}
    for item in lineas:
        clave = str(item["linea"])
        if clave in pedidas:
            raise ErrorProgramacion(
                f"La linea {clave} viene repetida en la peticion.")
        pedidas[clave] = item

    #  LOS LOCKS  --  lineas por id ascendente, y el plan DESPUES.
    #  -----------------------------------------------------------
    #  El orden no es una preferencia: M03-E4 bloquea linea -> plan, y si esta
    #  operacion bloqueara el plan primero se cerraria un ciclo (E4 sostiene la
    #  linea y pide el plan; E5 sostiene el plan y pide la linea). Y entre dos
    #  E5 concurrentes, ordenar por 'id' evita el ciclo simetrico.
    #
    #  Se bloquea la UNION de lo enviado y lo real: si el cliente omitio una
    #  linea, esa linea tambien tiene que estar quieta mientras se comprueba
    #  que falta.
    vigentes = (ProgramacionOrden.PLANIFICADA, ProgramacionOrden.CONFIRMADA)
    bloqueadas = list(ProgramacionOrden.objects
                      .select_for_update()
                      .filter(Q(org=org) &
                              (Q(id__in=list(pedidas)) |
                               Q(programacion=plan, dia=dia,
                                 estado__in=vigentes)))
                      .order_by("id"))
    plan = (ProgramacionSemanal.objects
            .select_for_update()
            .get(pk=plan.pk, org=org))

    #  RELECTURA: lo que decide es la fila bloqueada, no lo que llego.
    reales = {str(l.id): l for l in bloqueadas
              if l.programacion_id == plan.id and l.dia == dia
              and l.estado in vigentes}

    faltantes = sorted(set(reales) - set(pedidas))
    sobrantes = []
    desconocidas = []
    ajenas = []
    conocidas = {str(l.id): l for l in bloqueadas}
    for clave in pedidas:
        if clave in reales:
            continue
        if clave not in conocidas:
            desconocidas.append(clave)
        else:
            otra = conocidas[clave]
            if otra.org_id != org.id:
                ajenas.append(clave)
            else:
                sobrantes.append(
                    {"linea": clave, "dia": str(otra.dia),
                     "plan": str(otra.programacion_id),
                     "estado": otra.estado})
    if faltantes or sobrantes or desconocidas or ajenas:
        raise JornadaIncompleta(
            "El conjunto enviado no es la jornada que hay: "
            f"{len(faltantes)} sin enviar, {len(sobrantes)} de otra jornada, "
            f"{len(desconocidas)} inexistente(s).",
            faltantes=faltantes, sobrantes=sobrantes,
            desconocidas=desconocidas, ajenas=ajenas)

    #  ¿ALGUIEN TOCO LA JORNADA MIENTRAS EL USUARIO LA ORDENABA?
    #  ---------------------------------------------------------
    #  Se compara lo que el cliente dice haber leido contra la fila bloqueada.
    #  Si discrepan, se rechaza ENTERA: aplicar solo las que coincidian dejaria
    #  media jornada del usuario y media de quien llego antes.
    conflictos = []
    for clave, linea in reales.items():
        leida = pedidas[clave].get("secuencia_leida")
        if leida is not None and leida != linea.secuencia:
            conflictos.append({"linea": clave, "orden": linea.orden_id and
                               linea.orden.numero if hasattr(linea, "orden")
                               else None,
                               "leida": leida, "actual": linea.secuencia})
    if conflictos:
        raise JornadaCambio(
            f"La jornada cambio mientras la ordenabas: {len(conflictos)} "
            f"linea(s) ya no tienen el valor que leiste.", conflictos)

    cambios = [(reales[c], pedidas[c]["secuencia"]) for c in reales
               if reales[c].secuencia != pedidas[c]["secuencia"]]

    jornada = {"plan": str(plan.id), "dia": str(dia),
               "plan_estado": plan.estado,
               "plan_semana": str(plan.semana_inicio)}

    if not cambios:
        #  G-1: un lote sin cambios responde 200. No se escribe nada -- ni
        #  eventos, ni filas -- porque no hay ningun cambio que registrar.
        return {"jornada": jornada, "recibidas": len(reales),
                "modificadas": 0, "sin_cambio": len(reales),
                "lote": None, "resultado": "sin_cambios",
                "lineas": list(reales.values())}

    #  El motivo se exige solo si hay algo que justificar. Un plan publicado ya
    #  lo vieron las cuadrillas (D1.1-D), pero una peticion que no cambia nada
    #  no tiene nada que explicar -- y exigirselo haria imposible el caso G-1.
    es_formal = (plan.estado == ProgramacionSemanal.PUBLICADA)
    causa, motivo = _validar_causa(
        causa, motivo, exigida=es_formal,
        donde="Secuenciar una jornada de un plan ya publicado")

    lote = str(uuid.uuid4())
    novedad = None
    if causa:
        #  UNA novedad por lote, no una por linea: la jornada se reordeno por
        #  un motivo, no por N motivos. Se cuelga de la primera orden afectada
        #  porque 'NovedadOperativa.orden' es opcional pero identificar algo es
        #  mejor que nada; el lote del evento es lo que agrupa de verdad.
        novedad = _novedad_de(org, cambios[0][0].orden, actor, causa, motivo,
                              None, None)

    resultado = []
    for posicion, (linea, nueva) in enumerate(cambios, start=1):
        anterior = linea.secuencia
        linea.secuencia = nueva
        linea.save(update_fields=["secuencia", "updated_by", "updated_at"])

        EventoTrabajo.objects.create(
            org=org, orden_id=linea.orden_id,
            tipo=("secuencia_jornada_en_plan_publicado" if es_formal
                  else "secuencia_jornada"),
            profile=actor,
            datos={
                "lote": lote,
                "linea": str(linea.id),
                "anterior": anterior,
                "nuevo": nueva,
                #  El 0 se declara, no se deduce: significa SIN SECUENCIAR.
                "anterior_sin_secuenciar": anterior == 0,
                "nuevo_sin_secuenciar": nueva == 0,
                "jornada": jornada,
                "lote_tamano": len(reales),
                "lote_cambiadas": len(cambios),
                "lote_sin_cambio": len(reales) - len(cambios),
                "posicion_en_lote": posicion,
                "empate": _empate_de(linea, nueva),
                "causa": causa,
                "motivo": motivo,
                "novedad": str(novedad.id) if novedad else None,
                "contexto": contexto or {},
            })
        resultado.append(linea)

    #  Las que no cambiaron NO generan evento (regla 23), pero siguen en la
    #  respuesta: el usuario pidio una jornada entera.
    for clave, linea in reales.items():
        if linea not in resultado:
            resultado.append(linea)

    return {"jornada": jornada, "recibidas": len(reales),
            "modificadas": len(cambios),
            "sin_cambio": len(reales) - len(cambios),
            "lote": lote, "resultado": "aplicado",
            "novedad": str(novedad.id) if novedad else None,
            "lineas": sorted(resultado, key=lambda l: (l.dia, l.secuencia,
                                                       str(l.id)))}
