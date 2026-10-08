# -*- coding: utf-8 -*-
"""
================================================================================
 GOBIERNO  --  la decision, su desenlace, y lo que se aprendio
================================================================================

QUE HUECO CIERRA
----------------
'DecisionSupervisor' existia desde P4 con sus tres restricciones de base, y
NUNCA se escribia: la unica aparicion de 'DecisionSupervisor(' fuera de las
pruebas era la definicion de la clase. Medido el 05/10/2026.

Consecuencia directa: 'indicadores.indicadores_situaciones' ya calculaba
'tasa_aceptacion', 'recomendaciones_que_funcionaron', 'decisiones_corregidas' y
los cinco 'decisiones_<tipo>' leyendo una tabla que nunca se llenaba. Las
metricas estaban escritas y devolvian 0 / NO_APLICA para siempre.

Este modulo es el camino de escritura que faltaba. No reemplaza nada:
'PropuestaSupervisor' sigue siendo la propuesta y su revision,
'SituacionOperativa' sigue siendo la situacion, y 'supervisor.revisar' sigue
siendo el flujo por donde una persona decide.

LA DISTINCION QUE SOSTIENE TODO EL BLOQUE
-----------------------------------------
    DECISION  !=  RESULTADO

Una persona acepta una recomendacion y el arreglo falla. Otra la rechaza y el
problema se confirma igual. Las dos cosas pasan, y si se midieran juntas la
metrica diria "obediencia" donde dice "acierto".

Por eso son dos escrituras separadas y en dos momentos:

    registrar_decision()   cuando la persona decide. Resultado = PENDIENTE.
    registrar_resultado()  despues, cuando se sabe que paso. Con evidencia.

Y por eso 'aceptada' NO entra como 'funciono' en ninguna parte de este archivo.

EL VOCABULARIO: LO QUE YA EXISTIA Y NO SE RENOMBRO
--------------------------------------------------
El bloque pide cinco resultados --EXITOSO, PARCIAL, FALLIDO, NO_SE_PUEDE_SABER,
PENDIENTE-- y los cinco YA EXISTEN en 'ResultadoDecision', con dos nombres
distintos:

    EXITOSO  ->  ResultadoDecision.FUNCIONO
    FALLIDO  ->  ResultadoDecision.NO_FUNCIONO

No se renombraron. Son los mismos valores con la misma semantica, ya estan en
la base, ya los lee 'indicadores.py' y renombrarlos seria una migracion de datos
para no ganar nada. Igual con las decisiones: ACEPTADA/RECHAZADA/MODIFICADA son
'ACEPTO'/'RECHAZO'/'MODIFICO'. Lo unico que falto fue 'NO_APLICABLE', y se
agrego.

QUIEN PUEDE CONCLUIR, Y QUIEN NO
--------------------------------
El Supervisor NO puede escribir su propio resultado. 'OrigenAprendizaje' tiene
tres valores --persona, verificacion, evidencia_operativa-- y ninguno es
'supervisor'. Una tabla donde el evaluado se pone la nota no mide nada.
================================================================================
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from operaciones import auditoria
from operaciones.gobierno_modelos import (AprendizajeSupervisor,
                                          OrigenAprendizaje, ResultadoDecision,
                                          TipoAprendizaje, TipoDecision)
from operaciones.models import DecisionSupervisor, PropuestaSupervisor
from operaciones.situaciones_modelos import (SituacionOperativa, TipoEvento,
                                             TipoRelacion)

P = PropuestaSupervisor
D = DecisionSupervisor
S = SituacionOperativa

#  El puente entre el estado de la propuesta y el tipo de decision. Explicito y
#  en un solo lugar: dos tablas con vocabularios parecidos se desincronizan
#  calladas, y este dict es lo que lo impide.
ESTADO_A_DECISION = {
    P.ACEPTADA: TipoDecision.ACEPTO,
    P.RECHAZADA: TipoDecision.RECHAZO,
    P.MODIFICADA: TipoDecision.MODIFICO,
    P.EXPIRADA: TipoDecision.EXPIRO,
    P.CANCELADA: TipoDecision.NO_APLICABLE,
}

#  Los resultados que CIERRAN el desenlace. Reutiliza la tupla que ya existia:
#  'no_se_puede_sabe' NO cierra, porque no es un veredicto -- es la ausencia de
#  uno, y mezclarlos dejaria una metrica que cuenta ignorancia como fracaso.
CERRADOS = ResultadoDecision.CERRADOS


class ErrorGobierno(Exception):
    """No se puede registrar lo que se pide."""


class DesenlaceIncompatible(ErrorGobierno):
    """Ya hay un desenlace cerrado y el nuevo dice otra cosa."""


# =============================================================================
#  §3  --  LA CAPTURA DE LA DECISION
# =============================================================================

def _situacion_de(propuesta):
    """
    La situacion que origino la propuesta, si la hubo.

    No se inventa: se lee de 'origen_tipo'/'origen_id', que es el par que P6 ya
    usa para atar una coordinacion a su situacion. Una propuesta nacida de un
    detector de M02/M03 no tiene situacion, y eso es un estado valido -- el
    campo es nullable a proposito.
    """
    from operaciones import coordinacion

    if propuesta.origen_tipo != coordinacion.ORIGEN_SITUACION:
        return None
    return S.objects.filter(org=propuesta.org,
                            id=propuesta.origen_id).first()


def registrar_decision(propuesta, *, actor, ahora=None,
                       automatico: bool = False) -> DecisionSupervisor:
    """
    Deja la decision que una persona acaba de tomar sobre una propuesta.

    La llama 'supervisor.revisar' DENTRO de su transaccion, asi que si esto
    falla la revision entera se deshace. Es deliberado: una propuesta revisada
    sin su fila de decision es justo el estado que dejaba las metricas en cero.

    'recomendacion' se COPIA, no se referencia. Si mas adelante alguien edita la
    propuesta, lo que se decidio aquel dia sigue siendo legible -- y eso es el
    punto de una bitacora.

    El resultado nace PENDIENTE siempre. Nunca se deriva de la decision.
    """
    ahora = ahora or timezone.now()
    tipo = ESTADO_A_DECISION.get(propuesta.estado)
    #  Una aceptacion del SISTEMA no es una aceptacion humana, y el tipo lo
    #  dice. Se decide aqui y no en el llamador para que no haya dos formas de
    #  escribir la misma fila.
    if automatico and tipo == TipoDecision.ACEPTO:
        tipo = TipoDecision.CERRO_SOLO
    if tipo is None:
        raise ErrorGobierno(
            f"el estado '{propuesta.estado}' no es una decision: no se "
            f"registra un desenlace para algo que nadie decidio")
    #  'expiro' es lo unico que puede no tener actor (lo hace el reloj). Lo
    #  exige la restriccion 'decision_humana_con_actor' de la base.
    if tipo not in (TipoDecision.EXPIRO, TipoDecision.CERRO_SOLO) and actor is None:
        raise ErrorGobierno(
            "una decision humana necesita actor: sin nombre no se puede "
            "repreguntar por que se decidio eso")

    decision = D.objects.create(
        org=propuesta.org,
        situacion=_situacion_de(propuesta),
        propuesta=propuesta,
        recomendacion=propuesta.accion_propuesta[:255],
        tipo=tipo,
        actor=actor,
        decidida_en=ahora,
        motivo=(propuesta.resultado or "")[:2000],
        #  PENDIENTE, y no se discute: el resultado se sabe despues.
        resultado=ResultadoDecision.PENDIENTE,
    )

    #  La correccion humana se guarda como aprendizaje APARTE, con su propio
    #  tipo, para que "cuantas veces el humano corrigio al Supervisor" sea una
    #  consulta y no una interpretacion de un JSON.
    if tipo == TipoDecision.MODIFICO:
        registrar_aprendizaje(
            propuesta.org, tipo=TipoAprendizaje.CORRECCION_HUMANA,
            origen=OrigenAprendizaje.PERSONA,
            conclusion=f"Una persona modificó la recomendación: "
                       f"{propuesta.accion_propuesta[:140]}",
            evidencia=(propuesta.resultado
                       or "la propuesta quedó en estado 'modificada'"),
            propuesta=propuesta, decision=decision, actor=actor,
            situacion=decision.situacion, ahora=ahora,
            #  El original NO se pierde: 'propuesta_original' lo guarda intacto
            #  y aqui queda la referencia de donde mirarlo.
            datos={"original_en": "PropuestaSupervisor.propuesta_original"})

    if decision.situacion is not None:
        from operaciones import situaciones as svc

        svc.anotar(decision.situacion, TipoEvento.RECOMENDACION,
                   f"Decisión humana: {tipo} sobre "
                   f"{propuesta.accion_propuesta[:140]}",
                   datos={"decision_id": str(decision.id),
                          "propuesta_id": str(propuesta.id),
                          "tipo": tipo, "resultado": "pendiente"},
                   actor=actor, ocurrido_en=ahora)
    return decision


# =============================================================================
#  §4/§5/§19  --  EL RESULTADO POSTERIOR
# =============================================================================

@transaction.atomic
def registrar_resultado(decision, *, actor, resultado: str, evidencia: str,
                        correccion: str = "", ahora=None) -> DecisionSupervisor:
    """
    Dice QUE PASO despues. Con evidencia, y una sola vez.

    POR QUE EXIGE EVIDENCIA
    -----------------------
    Porque sin ella "funciono" es una opinion, y la restriccion
    'decision_resultado_con_evidencia' de la base ya lo exigia -- esto solo deja
    de intentar saltearla. Se comprueba aqui ADEMAS de en la base: las dos,
    porque una sola se puede saltear llamando por el otro camino.

    POR QUE NO SE PUEDE CAMBIAR UN DESENLACE CERRADO  (§19)
    -------------------------------------------------------
    Un desenlace es un hecho fechado, no un campo editable. Registrar
    'funciono' y despues 'no_funciono' sobre la misma decision no es corregir:
    es borrar lo que se afirmo. Si el mismo valor se repite, la llamada es
    idempotente y devuelve la fila como esta; si dice otra cosa, levanta.

    La fila se relee con 'select_for_update': sin el candado, dos personas
    cerrando a la vez pasarian las dos el chequeo antes de que ninguna escriba.
    """
    ahora = ahora or timezone.now()
    resultado = (resultado or "").strip()
    evidencia = (evidencia or "").strip()

    if resultado not in ResultadoDecision.TODOS:
        raise ErrorGobierno(f"resultado desconocido: {resultado!r}")
    if resultado == ResultadoDecision.PENDIENTE:
        raise ErrorGobierno(
            "'pendiente' no es un desenlace: es el estado en el que nace")
    if resultado in CERRADOS and not evidencia:
        raise ErrorGobierno(
            "un resultado cerrado exige evidencia: sin ella 'funcionó' es una "
            "opinión, y la base tampoco lo acepta")
    if actor is None:
        raise ErrorGobierno(
            "el resultado lo registra una persona: el Supervisor no puede "
            "escribir su propio desenlace para declararse correcto")

    fresca = D.objects.select_for_update().get(pk=decision.pk)
    if fresca.resultado in CERRADOS:
        if fresca.resultado == resultado:
            #  Idempotente: el mismo desenlace dos veces es el mismo hecho.
            return fresca
        raise DesenlaceIncompatible(
            f"esta decisión ya tiene desenlace '{fresca.resultado}' desde "
            f"{fresca.resultado_en}: registrar '{resultado}' encima borraría "
            f"lo que se afirmó. Si la conclusión cambió, va como aprendizaje.")

    anterior = fresca.resultado
    fresca.resultado = resultado
    fresca.resultado_en = ahora
    fresca.resultado_evidencia = evidencia
    if correccion:
        fresca.correccion = correccion
    fresca.save(update_fields=["resultado", "resultado_en",
                               "resultado_evidencia", "correccion",
                               "updated_at", "updated_by"])

    auditoria.registrar(
        org=fresca.org, actor=actor, accion="STATUS_CHANGED",
        entidad=auditoria.ENTIDAD_PROPUESTA,
        entidad_id=(fresca.propuesta_id or fresca.id),
        nombre=fresca.recomendacion,
        descripcion=f"Desenlace de la decisión: {resultado}",
        estado_anterior=anterior, estado_nuevo=resultado,
        motivo=evidencia[:500],
        extra={"decision_id": str(fresca.id), "tipo_decision": fresca.tipo,
               "hubo_correccion": bool(correccion)})

    #  Y la leccion, cuando el desenlace la deja ver. SOLO en los dos casos que
    #  son un veredicto sobre el criterio del Supervisor, y nunca al reves:
    #  'acepto + funciono' dice que acerto; 'rechazo + funciono' NO dice nada
    #  sobre el Supervisor, porque lo que funciono fue no hacerle caso.
    leccion = _leccion_de(fresca)
    if leccion:
        registrar_aprendizaje(
            fresca.org, tipo=leccion, origen=OrigenAprendizaje.PERSONA,
            conclusion=f"{fresca.recomendacion[:140]} — desenlace: {resultado}",
            evidencia=evidencia, propuesta=fresca.propuesta,
            decision=fresca, situacion=fresca.situacion, actor=actor,
            ahora=ahora, datos={"tipo_decision": fresca.tipo,
                                "resultado": resultado})

    if fresca.situacion is not None:
        from operaciones import situaciones as svc

        svc.anotar(fresca.situacion, TipoEvento.VERIFICACION,
                   f"Desenlace de la decisión: {resultado}",
                   datos={"decision_id": str(fresca.id),
                          "resultado": resultado,
                          "evidencia": evidencia[:200]},
                   actor=actor, ocurrido_en=ahora)
    return fresca


def _leccion_de(decision) -> str | None:
    """
    Que leccion deja este desenlace, si deja alguna.

    Dos y nada mas, y el resto es None a proposito:

      acepto  + funciono     -> la recomendacion servia. A favor.
      rechazo + no_funciono  -> se rechazo y el problema siguio. Es el
                                'RECHAZO_ERRADO': el Supervisor tenia razon y no
                                se le creyo.

    Lo que NO se concluye, y es el error que el bloque nombra:
      acepto  + no_funciono  -> NO es un falso positivo. La deteccion pudo ser
                                correcta y el arreglo malo. Para decir que no
                                habia problema hace falta que alguien lo afirme
                                con evidencia, y eso es otra llamada.
      rechazo + funciono     -> NO dice nada del Supervisor: lo que funciono fue
                                no hacerle caso, y eso ya esta en la decision.
    """
    if decision.tipo == TipoDecision.ACEPTO \
            and decision.resultado == ResultadoDecision.FUNCIONO:
        return TipoAprendizaje.RECOMENDACION_CONFIRMADA
    if decision.tipo == TipoDecision.RECHAZO \
            and decision.resultado == ResultadoDecision.NO_FUNCIONO:
        return TipoAprendizaje.RECHAZO_ERRADO
    return None


# =============================================================================
#  §9/§10/§11/§12  --  EL APRENDIZAJE
# =============================================================================

def registrar_aprendizaje(org, *, tipo: str, origen: str, conclusion: str,
                          evidencia: str, situacion=None, propuesta=None,
                          decision=None, actor=None, confianza: str = "media",
                          datos: dict | None = None,
                          ahora=None) -> AprendizajeSupervisor:
    """
    Una leccion, con su evidencia y su autor. Append-only.

    Es la puerta UNICA de 'AprendizajeSupervisor', y valida lo mismo que la base
    por los dos lados. 'origen' no admite 'supervisor': ese valor no existe en
    'OrigenAprendizaje', asi que el agente no puede concluir sobre si mismo ni
    pasando por aqui ni por el ORM.
    """
    ahora = ahora or timezone.now()
    if tipo not in TipoAprendizaje.TODOS:
        raise ErrorGobierno(f"tipo de aprendizaje desconocido: {tipo!r}")
    if origen not in OrigenAprendizaje.TODOS:
        raise ErrorGobierno(
            f"origen desconocido: {origen!r}. El Supervisor no es un origen "
            f"válido: no puede concluir sobre su propio acierto.")
    if not (conclusion or "").strip():
        raise ErrorGobierno("falta la conclusión")
    if not (evidencia or "").strip():
        raise ErrorGobierno(
            "falta la evidencia: una conclusión sin respaldo es una opinión")
    if origen == OrigenAprendizaje.PERSONA and actor is None:
        raise ErrorGobierno(
            "una lección de una persona lleva su nombre: sin autor no se puede "
            "repreguntar")
    #  Una OMISION se exime, y no es una excepcion de conveniencia: un falso
    #  negativo existe porque NO habia situacion. Exigirle una haria que el caso
    #  principal de §11 fuera imposible de registrar. Lo cazó 'test_I3'.
    if (situacion is None and propuesta is None and decision is None
            and tipo != TipoAprendizaje.OMISION):
        raise ErrorGobierno(
            "la lección tiene que apuntar a algo: una huérfana no la vuelve a "
            "encontrar nadie. La única excepción es una omisión, que existe "
            "precisamente porque no había situación.")

    return AprendizajeSupervisor.objects.create(
        org=org, tipo=tipo, origen=origen, situacion=situacion,
        propuesta=propuesta, decision=decision,
        conclusion=conclusion.strip(), evidencia=evidencia.strip(),
        confianza=confianza, actor=actor, registrado_en=ahora,
        datos=datos or {})


def registrar_falso_positivo(situacion, *, actor, motivo: str,
                             ahora=None) -> AprendizajeSupervisor:
    """
    El Supervisor vio una situacion y no habia problema. Lo dice una persona.

    NO cambia el estado de la situacion: descartarla es de 'situaciones.
    cambiar_estado', y son dos cosas. Una situacion puede descartarse por otros
    motivos --se duplicó, se absorbio en otra-- y no todos son un falso
    positivo del Supervisor.
    """
    return registrar_aprendizaje(
        situacion.org, tipo=TipoAprendizaje.FALSO_POSITIVO,
        origen=OrigenAprendizaje.PERSONA,
        conclusion=f"No había problema en {situacion.codigo}: "
                   f"{situacion.titulo[:120]}",
        evidencia=motivo, situacion=situacion, actor=actor, ahora=ahora,
        datos={"estado_al_descartar": situacion.estado})


def registrar_omision(org, *, actor, conclusion: str, evidencia: str,
                      situacion=None, datos=None,
                      ahora=None) -> AprendizajeSupervisor:
    """
    Habia un problema real y el Supervisor NO lo habia visto. El falso negativo.

    'situacion' es opcional y suele venir vacia: el caso tipico es justamente
    que NO existia ninguna. Cuando alguien la crea despues, se pasa -- y queda
    la relacion para que P8.3 pueda contar cuantas omisiones hubo y de donde
    salieron.

    Lo que este bloque NO hace es detectarlas solo: eso exigiria comparar cada
    ticket contra las situaciones de ese momento, y esa es otra decision.
    """
    return registrar_aprendizaje(
        org, tipo=TipoAprendizaje.OMISION, origen=OrigenAprendizaje.PERSONA,
        conclusion=conclusion, evidencia=evidencia, situacion=situacion,
        actor=actor, ahora=ahora, datos=datos or {})


def registrar_calidad_de_correlacion(situacion, *, actor, propuestos: int,
                                     confirmados: int, evidencia: str,
                                     ahora=None) -> AprendizajeSupervisor:
    """
    Cuantos afectados dijo el Supervisor y cuantos eran. Con los dos numeros.

    El tipo sale de comparar: iguales o confirmados mayores -> correlacion
    correcta (no se le escapo nada); confirmados menores -> incorrecta, agrupo
    de mas. Los dos numeros viajan en 'datos' para que P8.3 pueda calcular la
    magnitud del error y no solo su signo.
    """
    propuestos, confirmados = int(propuestos), int(confirmados)
    tipo = (TipoAprendizaje.CORRELACION_CORRECTA if confirmados >= propuestos
            else TipoAprendizaje.CORRELACION_INCORRECTA)
    return registrar_aprendizaje(
        situacion.org, tipo=tipo, origen=OrigenAprendizaje.EVIDENCIA_OPERATIVA,
        conclusion=f"{situacion.codigo}: propuso {propuestos} afectados, "
                   f"se confirmaron {confirmados}",
        evidencia=evidencia, situacion=situacion, actor=actor, ahora=ahora,
        datos={"afectados_propuestos": propuestos,
               "afectados_confirmados": confirmados,
               "diferencia": confirmados - propuestos})


# =============================================================================
#  §8  --  REINCIDENCIA: se PROPONE, no se afirma
# =============================================================================

def candidatas_de_reincidencia(situacion, *, dias: int = 30,
                               ahora=None) -> list[dict]:
    """
    Situaciones anteriores que PODRIAN ser la misma cosa repitiendose.

    Es LECTURA. No crea relaciones, no escribe nada y no afirma reincidencia:
    devuelve candidatas con el afectado que comparten y cuantos dias pasaron,
    para que una persona decida. 'TipoRelacion.REINCIDENCIA' esta fuera de
    'AUTOMATICOS' justamente por esto.

    POR QUE NO SE AFIRMA SOLA
    -------------------------
    Que dos situaciones compartan PON no prueba que una sea reincidencia de la
    otra: un PON con una caida por semana puede estar sufriendo tres causas
    distintas, y declararlas reincidencia escondería dos problemas detrás de
    uno. La coincidencia es el dato; el diagnostico es de quien sabe.
    """
    from operaciones.situaciones_modelos import SituacionAfectado, TipoAfectado

    ahora = ahora or timezone.now()
    desde = ahora - timezone.timedelta(days=int(dias))

    #  Los afectados de topologia de ESTA situacion. Un caso o un ticket no
    #  sirven para esto: el mismo cliente puede reclamar por dos cosas.
    mios = set(
        SituacionAfectado.objects
        .filter(situacion=situacion,
                tipo__in=(TipoAfectado.PON, TipoAfectado.OLT,
                          TipoAfectado.ZONA))
        .values_list("tipo", "identificador"))
    if not mios:
        return []

    candidatas: dict = {}
    for tipo, ident in mios:
        for otra in (SituacionAfectado.objects
                     .filter(org=situacion.org, tipo=tipo,
                             identificador=ident,
                             situacion__detectada_en__gte=desde,
                             situacion__detectada_en__lt=situacion.detectada_en)
                     .exclude(situacion=situacion)
                     .select_related("situacion")[:25]):
            s = otra.situacion
            fila = candidatas.setdefault(str(s.id), {
                "situacion_id": str(s.id), "codigo": s.codigo,
                "titulo": s.titulo, "estado": s.estado,
                "detectada_en": s.detectada_en.isoformat(),
                "dias_antes": (situacion.detectada_en - s.detectada_en).days,
                "comparten": [],
            })
            fila["comparten"].append({"tipo": tipo, "identificador": ident})

    return sorted(candidatas.values(), key=lambda f: f["dias_antes"])


def marcar_reincidencia(situacion, anterior, *, actor, motivo: str,
                        ahora=None):
    """
    Una PERSONA afirma que esto ya habia pasado. Reutiliza 'relacionar'.

    No hay version automatica de esta funcion, y no es un olvido: 'relacionar'
    exige actor para los tipos que no estan en 'AUTOMATICOS', y REINCIDENCIA no
    esta. Si el dia que haga falta se quiere automatizar, el cambio es declarar
    el tipo como automatico -- y eso obliga a venir aqui a justificarlo.
    """
    from operaciones import situaciones as svc

    if actor is None:
        raise ErrorGobierno(
            "la reincidencia la afirma una persona: compartir un PON no prueba "
            "que sea la misma causa repitiéndose")
    ahora = ahora or timezone.now()
    relacion = svc.relacionar(situacion, anterior,
                              tipo=TipoRelacion.REINCIDENCIA,
                              motivo=motivo, actor=actor, ahora=ahora)
    registrar_aprendizaje(
        situacion.org, tipo=TipoAprendizaje.REINCIDENCIA,
        origen=OrigenAprendizaje.PERSONA,
        conclusion=f"{situacion.codigo} es reincidencia de {anterior.codigo}",
        evidencia=motivo, situacion=situacion, actor=actor, ahora=ahora,
        datos={"situacion_anterior": str(anterior.id),
               "codigo_anterior": anterior.codigo,
               "dias_entre": (situacion.detectada_en
                              - anterior.detectada_en).days})
    return relacion


# =============================================================================
#  §17  --  LO QUE P8.3 VA A PODER CONTAR
# =============================================================================

def resumen_de_aprendizaje(org, *, desde=None, hasta=None) -> dict:
    """
    Los conteos crudos que P8.3 necesita. Conteos, no indicadores.

    Devuelve numeros por tipo de leccion y los dos tiempos que ya se pueden
    medir. NO calcula precision ni tasas: eso es P8.3, y hacerlo aqui dejaria
    la formula en dos lugares.

    Lo que se puede medir HOY, y se dice: 'deteccion -> decision' sale de
    'situacion.detectada_en' contra 'decision.decidida_en'; 'decision ->
    resultado' sale de 'decidida_en' contra 'resultado_en'. Los dos solo para
    las decisiones que tienen situacion y desenlace; las demas se cuentan aparte
    en vez de promediarse como cero.
    """
    from django.db.models import Count

    qs = AprendizajeSupervisor.objects.filter(org=org)
    dec = D.objects.filter(org=org)
    if desde:
        qs = qs.filter(registrado_en__gte=desde)
        dec = dec.filter(decidida_en__gte=desde)
    if hasta:
        qs = qs.filter(registrado_en__lte=hasta)
        dec = dec.filter(decidida_en__lte=hasta)

    por_tipo = {t: 0 for t in TipoAprendizaje.TODOS}
    for fila in qs.values("tipo").annotate(n=Count("id")):
        por_tipo[fila["tipo"]] = fila["n"]

    con_situacion = dec.filter(situacion__isnull=False)
    tiempos_a_decision = [
        (d.decidida_en - d.situacion.detectada_en).total_seconds() / 60.0
        for d in con_situacion.select_related("situacion")
        if d.situacion.detectada_en and d.decidida_en]
    cerradas = dec.filter(resultado__in=CERRADOS, resultado_en__isnull=False)
    tiempos_a_resultado = [
        (d.resultado_en - d.decidida_en).total_seconds() / 60.0
        for d in cerradas if d.decidida_en]

    return {
        "aprendizajes": qs.count(),
        "por_tipo": por_tipo,
        "a_favor": sum(por_tipo[t] for t in TipoAprendizaje.A_FAVOR),
        "en_contra": sum(por_tipo[t] for t in TipoAprendizaje.EN_CONTRA),
        "decisiones": dec.count(),
        "decisiones_con_desenlace": cerradas.count(),
        #  Se publica al lado a proposito: una tasa calculada sin saber cuantas
        #  quedaron sin desenlace no se puede interpretar.
        "decisiones_sin_desenlace": dec.filter(
            resultado=ResultadoDecision.PENDIENTE).count(),
        "minutos_deteccion_a_decision": sorted(tiempos_a_decision),
        "minutos_decision_a_resultado": sorted(tiempos_a_resultado),
        #  Lo que NO se puede medir todavia, dicho en el dato y no en un
        #  comentario: cuantas decisiones no tienen situacion de la que medir el
        #  tiempo de deteccion.
        "decisiones_sin_situacion": dec.filter(situacion__isnull=True).count(),
    }
