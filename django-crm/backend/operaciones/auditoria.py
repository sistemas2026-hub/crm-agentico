# -*- coding: utf-8 -*-
"""
================================================================================
 AUDITORIA  --  se escribe en la que ya existe, no se inventa otra
================================================================================

POR QUE common.Activity Y NO UNA TABLA PROPIA
---------------------------------------------
Porque ya es el registro de auditoria del CRM y esta vivo: 516 filas, 241 de
ellas en los ultimos 7 dias (medido el 15/09/2026). Tiene lo que hace falta --
'user' (quien), 'action' (que), 'created_at' (cuando), 'org' (organizacion),
'metadata' (estado anterior, estado nuevo, motivo) y 'description'-- y su
registro de verbos ya incluye APPROVED, REJECTED y STATUS_CHANGED, que es
exactamente el flujo de revision.

Crear una tabla de auditoria para este modulo seria el tercer sistema: ya estan
'common.Activity' (el CRM) y 'asistente.audit_log' (el motor, que Fase 1
estreno). Cada uno cubre su dominio; un tercero solo agregaria un lugar mas
donde buscar.

LO QUE ESTO NO ES
-----------------
No convierte Activity en una agenda. Se ESCRIBE en ella un hecho en pasado --
"el Jefe de Operaciones acepto la propuesta X"-- que es exactamente para lo que
esta hecha. Lo que falta hacer vive en ActividadOperativa, que es otra tabla.

QUE PASA SI FALLA
-----------------
Nada se traga. Si no se puede anotar una transicion, la transicion no ocurre:
esto corre dentro de la misma transaccion que el cambio. Es lo contrario del
criterio del motor (donde perder una fila de auditoria no puede tumbar la
atencion a un cliente) y la diferencia es deliberada -- aca no hay ningun
cliente esperando, y una decision humana sin rastro no sirve para nada.
================================================================================
"""

from __future__ import annotations

from django.db.models import Q

from common.models import Activity

# Los dos tipos de entidad que este modulo audita. Se declaran en
# common.models.Activity.ENTITY_TYPE_CHOICES: un valor no declarado se guarda
# igual (Django valida 'choices' en formularios, no al guardar) pero queda
# divergiendo en silencio -- que es como 'AsignacionTrabajo.rol' termino con un
# 'tecnico_lider' que su propio modelo no documenta.
ENTIDAD_ACTIVIDAD = "ActividadOperativa"
ENTIDAD_PROPUESTA = "PropuestaSupervisor"
ENTIDAD_NOVEDAD = "NovedadOperativa"
#  P6: para auditar una coordinacion rechazada, que por definicion no tiene
#  actividad contra la que registrarse.
ENTIDAD_SITUACION = "SituacionOperativa"

#  EL CASO, Y POR QUE FALTABA  --  15/10/2026
#
#  Cuando el Supervisor CIERRA un caso desincronizado, esa auditoria se escribe
#  sobre el CASO: 'cierre_de_caso.py' hace entity_type="Case",
#  action="STATUS_CHANGED'. Como 'Case' no estaba en esta lista, el feed no lo
#  mostraba -- y esa es la accion con mas efecto que el Supervisor hace hoy:
#  veintiocho casos cerrados solo el 14/10/2026 en produccion, ninguno visible
#  en su propio panel de actividad.
#
#  Medido el 15/10 sobre el local, con la auditoria entera a la vista:
#      PropuestaSupervisor CREATE    100   llegaba
#      PropuestaSupervisor APPROVED   20   llegaba
#      Case                CREATE     69   NO llegaba
#      Case                ASSIGN     69   NO llegaba
#
#  'Case' SI esta declarado en 'Activity.ENTITY_TYPE_CHOICES', asi que esto no
#  agrega un valor que el modelo no conozca.
ENTIDAD_CASO = "Case"

#:  Las entidades que este modulo mira. NO es toda 'common.Activity' y no debe
#:  serlo: sin este filtro el feed se llenaria de contactos editados y correos
#:  enviados, que es cierto pero no es lo que esta pantalla pregunta.
ENTIDADES_DEL_SUPERVISOR = (ENTIDAD_PROPUESTA, ENTIDAD_ACTIVIDAD,
                            ENTIDAD_NOVEDAD, ENTIDAD_SITUACION, ENTIDAD_CASO)

#:  LOS GRUPOS DEL FILTRO, por lo que una persona quiere preguntar.
#:
#:  Se agrupa por ACCION CRUDA y no por el texto que se muestra: atar el filtro
#:  al idioma hace que una redaccion nueva lo deje sin encontrar nada, y la
#:  pantalla se ve igual, solo vacia. Es la clase de falla que no da error.
#:
#:  'pasa_a_despacho' es APPROVED porque una propuesta aceptada ES un caso que
#:  entro a la cola: 'campo/casos-despachables' lista los casos cuya propuesta
#:  esta en ACEPTADA o MODIFICADA.
#:  CADA GRUPO ES (entidad, accion), NO solo la accion.
#:
#:  La primera version agrupaba por accion sola, y el conteo la delato: dijo
#:  "propone: 169" cuando el Supervisor habia generado 100 propuestas. Los otros
#:  69 eran 'Case CREATE' --casos creados por otra via-- contados como si el
#:  Supervisor los hubiera propuesto. Un panel de auditoria que le atribuye a
#:  alguien lo que no hizo es peor que uno incompleto.
#:  La tarea que marca un pase a Despacho. Se declara aca --y no se importa de
#:  'paso_a_despacho'-- para no crear un ciclo de imports; una prueba la fija
#:  contra la del catalogo para que no diverjan en silencio.
TAREA_PASO_A_DESPACHO = "pasar_a_despacho_segun_las_reglas"

#  UNA ENTRADA PUEDE EXIGIR ADEMAS UNA TAREA  --  16/10/2026
#  ----------------------------------------------------------
#  Aceptar una propuesta de CIERRE y pasar un ticket a DESPACHO escribian la
#  misma fila: 'PropuestaSupervisor APPROVED'. Medido en produccion: el filtro
#  "Pasados a Despacho" marcaba 597 y el detalle de esas filas decia "Cerrar el
#  caso en Dexter". El numero contaba las dos cosas.
#
#  Desde hoy 'revisar' escribe 'metadata["tarea"]' cuando quien acepta declara
#  cual fue. Las filas anteriores NO la tienen y caen en "acepta", que es lo
#  honesto: inventarles una tarea seria afirmar algo que nadie registro.
GRUPOS = {
    "pasa_a_despacho": ((ENTIDAD_PROPUESTA, "APPROVED",
                         TAREA_PASO_A_DESPACHO),),
    "acepta": ((ENTIDAD_PROPUESTA, "APPROVED", None),),
    "cierra_caso": ((ENTIDAD_CASO, "STATUS_CHANGED"),),
    "propone": ((ENTIDAD_PROPUESTA, "CREATE"),
                (ENTIDAD_PROPUESTA, "CREATED")),
    "descarta": ((ENTIDAD_PROPUESTA, "REJECTED"),
                 (ENTIDAD_PROPUESTA, "DELETE"),
                 (ENTIDAD_PROPUESTA, "DELETED")),
    "otros": (),          # lo que no cae en ninguno de los anteriores
}

#:  Los pares que YA tienen grupo. Sirve para resolver "otros" sin enumerarlo:
#:  lo que no esta aqui, es otro -- y asi un hecho NUEVO aparece en 'otros' en
#:  vez de desaparecer del panel sin que nadie lo note.
def _condicion(entrada) -> Q:
    """
    La condicion de UNA entrada del catalogo.

    Dos formas, y la tercera posicion es la que decide:

        (entidad, accion)                 cualquier fila de ese par
        (entidad, accion, "la_tarea")     solo las que declararon esa tarea
        (entidad, accion, None)           solo las que NO declararon ninguna

    El tercer caso es el que recoge lo historico: 'metadata__tarea' ausente.
    """
    entidad, accion = entrada[0], entrada[1]
    base = Q(entity_type=entidad, action=accion)
    if len(entrada) < 3:
        return base
    tarea = entrada[2]
    if tarea is None:
        #  LA TRAMPA DEL NULL, medida el 16/10/2026 con la prueba del contador.
        #  '~Q(metadata__tarea=X)' se traduce a NOT (metadata->>'tarea' = X).
        #  Para una fila SIN esa clave el lado izquierdo es NULL, la
        #  comparacion da NULL y NOT NULL sigue siendo NULL: la fila queda
        #  AFUERA. O sea que lo historico --que es justo lo que esta rama
        #  existe para recoger-- desaparecia.
        #
        #  El sintoma no era un error: el filtro devolvia cero y el contador,
        #  que cuenta en Python y no sufre el NULL, devolvia tres. La guarda
        #  que compara los dos numeros es la que lo encontro.
        return base & (Q(metadata__tarea__isnull=True)
                       | ~Q(metadata__tarea=TAREA_PASO_A_DESPACHO))
    return base & Q(metadata__tarea=tarea)


#  PARA 'otros' SE MIRA EL PAR Y NUNCA LA TAREA: una fila de un par ya
#  declarado tiene grupo aunque su tarea no coincida con ninguno -- si no,
#  caeria en "otros" Y en "acepta" a la vez, y los conteos no sumarian.
_CON_GRUPO = tuple((p[0], p[1]) for pares in GRUPOS.values() for p in pares)


def registrar(*, org, actor, accion: str, entidad: str, entidad_id,
              nombre: str = "", descripcion: str = "",
              estado_anterior: str = "", estado_nuevo: str = "",
              motivo: str = "", extra: dict | None = None) -> Activity:
    """
    Una fila de auditoría. Devuelve la fila escrita.

    'actor' es el Profile que decidió, o None cuando el autor es el Supervisor
    -- y esa distinción importa: una propuesta creada por la IA tiene
    'user=None' y se reconoce por eso, no por un usuario de sistema inventado
    que despues se confunda con una persona.
    """
    metadata = {k: v for k, v in {
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado_nuevo,
        "motivo": motivo,
    }.items() if v}
    if extra:
        metadata.update(extra)

    return Activity.objects.create(
        org=org,
        user=actor,
        action=accion,
        entity_type=entidad,
        entity_id=entidad_id,
        entity_name=(nombre or "")[:255],
        description=descripcion or "",
        metadata=metadata,
    )


def historial(org, entidad: str, entidad_id):
    """Todo lo que le pasó a una entidad, lo más reciente primero."""
    return Activity.objects.filter(
        org=org, entity_type=entidad, entity_id=entidad_id
    ).order_by("-created_at")


def recientes(org, limite: int = 20, *, grupo: str = "", antes_de=None):
    """
    Los últimos hechos registrados por este módulo, lo más reciente primero.

    Es el feed del tablero, y es lo único de esa pantalla que no existía en
    ninguna forma: 'historial' responde "qué le pasó a ESTA propuesta", y no
    hay manera de preguntar "qué pasó, en general, en la última hora".

    Se acota a las entidades de este módulo a propósito. 'common.Activity' es
    la auditoría del CRM entero -- sin el filtro, el feed del Supervisor se
    llenaría de contactos editados y correos enviados, que es cierto pero no es
    lo que esta pantalla pregunta.

    P6 sumó la CUARTA: sin ella, una coordinación rechazada por la autonomía se
    auditaba y no aparecía en el feed -- justo el hecho que hay que ver.

    'grupo' FILTRA POR LO QUE EL SUPERVISOR HIZO  --  15/10/2026
    -----------------------------------------------------------
    Vacío trae todo. Con un grupo de 'GRUPOS' trae solo esas acciones, y
    'otros' trae lo que no cae en ningún grupo -- que es distinto de "nada": un
    hecho nuevo aparece ahí en vez de desaparecer del panel sin que nadie lo
    note.

    Un grupo que no existe devuelve VACÍO y no "todo": tratar lo que no se
    entiende como "sin filtro" mostraría más de lo que se pidió, y en un panel
    de auditoría eso es la peor dirección del error.

    'antes_de' ES LA PAGINACIÓN, y va por fecha y no por 'offset'
    ------------------------------------------------------------
    Con 'offset' y filas entrando arriba todo el tiempo --el ciclo audita cada
    hora-- la página 2 repetiría lo que la 1 ya mostró y saltearía otras. Un
    corte por 'created_at' no se mueve: lo que ya pasó no cambia de lugar.
    """
    qs = Activity.objects.filter(
        org=org, entity_type__in=list(ENTIDADES_DEL_SUPERVISOR))

    pedido = (grupo or "").strip()
    if pedido:
        if pedido not in GRUPOS:
            return Activity.objects.none()
        pares = GRUPOS[pedido]
        if pares:
            cond = Q()
            for entrada in pares:
                cond |= _condicion(entrada)
            qs = qs.filter(cond)
        else:
            #  'otros': todo lo que no cae en ningun grupo declarado.
            fuera = Q()
            for entidad, accion in _CON_GRUPO:
                fuera |= Q(entity_type=entidad, action=accion)
            qs = qs.exclude(fuera)

    if antes_de is not None:
        qs = qs.filter(created_at__lt=antes_de)

    return (qs.select_related("user", "user__user")
              .order_by("-created_at", "-id")[:limite])


def cuantos_por_grupo(org) -> dict:
    """
    Cuántos hechos hay de cada grupo. Para que el filtro diga lo que deja fuera.

    Un selector que no dice cuántos hay obliga a probarlo para saber si sirve, y
    con un panel que se refresca solo eso significa apretarlo y no saber si lo
    que se ve es "no hay" o "todavía no llegó".

    Cuenta sobre TODO el historial, no sobre la página: el número de al lado de
    "Cierres de caso" tiene que decir cuántos cierres hubo, no cuántos entraron
    en los últimos veinte hechos.
    """
    from django.db.models import Count

    #  SE AGREGA TAMBIEN POR TAREA  --  16/10/2026
    #  --------------------------------------------
    #  Agrupar solo por (entidad, accion) devolvia un numero para
    #  'PropuestaSupervisor APPROVED' que mezclaba los pases a Despacho con las
    #  aceptaciones de cierres. 'metadata__tarea' entra en el 'values_list' para
    #  que el conteo se parta igual que el filtro -- si uno mira la tarea y el
    #  otro no, el boton dice un numero y la lista muestra otro.
    crudo = (Activity.objects
             .filter(org=org, entity_type__in=list(ENTIDADES_DEL_SUPERVISOR))
             .values_list("entity_type", "action", "metadata__tarea")
             .annotate(n=Count("id")))
    #  Las filas historicas no tienen la clave: vienen con 'None', que es
    #  exactamente lo que la entrada '(…, None)' recoge.
    por_terna = {}
    for e, a, t, n in crudo:
        por_terna[(e, a, t)] = por_terna.get((e, a, t), 0) + n

    def _cuantos(entrada) -> int:
        entidad, accion = entrada[0], entrada[1]
        if len(entrada) < 3:
            return sum(n for (e, a, _t), n in por_terna.items()
                       if (e, a) == (entidad, accion))
        tarea = entrada[2]
        if tarea is None:
            return sum(n for (e, a, t), n in por_terna.items()
                       if (e, a) == (entidad, accion)
                       and t != TAREA_PASO_A_DESPACHO)
        return por_terna.get((entidad, accion, tarea), 0)

    salida, con_grupo = {}, 0
    for nombre, pares in GRUPOS.items():
        if not pares:
            continue
        n = sum(_cuantos(entrada) for entrada in pares)
        salida[nombre] = n
        con_grupo += n
    total = sum(por_terna.values())
    salida["otros"] = total - con_grupo
    salida["todo"] = total
    return salida
