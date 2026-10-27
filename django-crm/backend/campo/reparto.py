# -*- coding: utf-8 -*-
"""
================================================================================
 EL REPARTO DE LA MADRUGADA  --  propone una jornada, nunca la publica
================================================================================

QUE HACE
--------
Mira las ordenes que todavia no tienen a quien, las ordena con un criterio
declarado, y las reparte entre las cuadrillas que trabajan ese dia respetando
sus zonas. Devuelve la propuesta: NO escribe asignaciones y NO publica nada.

POR QUE NO PUBLICA
------------------
El Supervisor NOC esta en shadow mode por decision explicita: "lo que el
Supervisor NOC IA RECOMIENDA, nunca lo que hace", y `ejecutada` no es un estado
posible en `PropuestaSupervisor`. Repartir el trabajo del dia siguiente sin que
nadie mire seria cruzar esa linea, y la decision fue mantenerla: la jornada
queda armada y una persona la publica.

Eso no es ceremonia. Si nadie publica, nadie trabaja a ciegas -- y el dia que
el criterio se equivoque, el error se ve antes de que alguien maneje treinta
kilometros.

EL ORDEN, Y POR QUE ESE
-----------------------
    1. vencidas   lo que ya paso su plazo va primero, siempre; entre ellas,
                  la de mas atraso.
    2. prioridad  entre las que no vencieron, la alta, despues la media y la
                  baja (decision del usuario, 23/10/2026: hasta ahi la
                  prioridad solo ordenaba la lista del tecnico).
    3. plazo      dentro de cada prioridad, la que vence antes; sin plazo, al
                  final de su grupo.
    4. numero     para que dos corridas con los mismos datos den lo mismo.

El ultimo no es un criterio de negocio: es lo que hace el reparto
REPRODUCIBLE. Sin un desempate estable, dos corridas seguidas pueden entregar
ordenes distintas a la misma cuadrilla y nadie podria explicar por que.

EL PRECIO DEL PLAN, Y POR QUE VA DESPUES DEL SLA
------------------------------------------------
Un cliente de plan alto pesa, pero NO por encima de un plazo que vence: lo
primero compromete la relacion comercial, lo segundo ya se incumplio. Por eso
entra como desempate entre dos ordenes con el mismo riesgo, antes de la
antiguedad.

El precio no se consulta aca: se lee de `precios_por_plan`, que alguien
sincroniza aparte (ver nucleo/herramientas/planes_precio.py). Preguntarselo al
proveedor durante el reparto serian 50 llamadas, y este proyecto ya pago ese
error una vez -- sacar `contar_clientes` del camino caliente de 'ventas' costo
un incidente el 20/08/2026 por 1-2s de latencia por mensaje.

SIN PRECIO NO SE SUPONE CERO. Un plan sin precio conocido no es el mas barato:
queda neutro, entre los que tienen precio y los que no se pueden ordenar. Un
cero lo mandaria al fondo como si fuera gratis.

Corporativo y antiguedad del cliente siguen sin entrar: esos datos no estan en
el CRM --la tabla `accounts` esta vacia, 237 de 237 casos medidos el
25/09/2026-- y un criterio que no se puede calcular no es un criterio.

LA LABOR TAMBIEN FILTRA, Y TAMBIEN ES DURA
------------------------------------------
Una cuadrilla se pone cada dia en una labor --instalacion, correctivo,
trabajos-- y solo recibe ordenes de tipos de trabajo clasificados en ESA
labor. Hasta el 08/10/2026 el reparto ignoraba ese campo por completo: la
palabra `labor` no aparecia ni una vez en este archivo, asi que una cuadrilla
puesta en correctivo podia recibir instalaciones y nadie lo veia hasta que el
tecnico abria la orden.

Un tipo de trabajo SIN clasificar no se reparte: queda en `sin_clasificar`.
Ningun codigo ('ftth', 'soporte', 'retiro') dice a que labor corresponde
--cada empresa nombra los suyos-- asi que mandarlo a cualquier cuadrilla seria
adivinar. Se clasifica una vez, en el catalogo, no orden por orden.

LA ZONA ES DURA
---------------
Una cuadrilla solo recibe ordenes de las zonas que cubre ese dia. Una orden
cuya localidad no esta mapeada a ninguna zona NO se reparte: queda en
`sin_zona`, que es una respuesta y no un silencio. Repartirla igual la mandaria
a cualquier lado; esconderla la dejaria sin hacer sin que nadie lo note.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from campo.cuadrillas import (JornadaDeCuadrilla, destinatarios,
                              por_que_nadie_recibe)
from campo.models import AsignacionTrabajo, EventoTrabajo, OrdenTrabajo

#: El evento que se suponia que decia que alguien YA fue al sitio.
#:
#: NINGUN codigo de produccion lo escribe (medido el 21/10/2026: solo las
#: pruebas lo fabricaban). El reparto y publicar ya no lo miran: miran la
#: vuelta real, `vueltas_empezadas`. Queda porque `pendientes_de_ayer` todavia
#: lo lee, y ahi tampoco encuentra nada.
EVENTO_INICIO = "trabajo_iniciado"
from campo.zonas import normalizar_localidad

#: Estados en los que una orden todavia espera que alguien la haga.
#:
#: `correccion_requerida` entra: el supervisor la devolvio y vuelve a necesitar
#: a alguien. `bloqueada` NO: esta detenida por algo que no se resuelve
#: repartiendola de nuevo, y asignarla otra vez la haria rebotar cada madrugada.
ESTADOS_QUE_ESPERAN = (
    OrdenTrabajo.ASIGNADA,
    OrdenTrabajo.CORRECCION_REQUERIDA,
)

#: Cuantas ordenes se le proponen a una cuadrilla en un dia.
#:
#: NO es una capacidad calculada --eso depende de la duracion de cada tipo de
#: trabajo, de la disponibilidad y de los bloqueos, y `operaciones/capacidad.py`
#: ya lo deriva cuando se pregunta-- sino un TOPE para que el reparto no le
#: vuelque treinta ordenes a la primera cuadrilla. El supervisor lo ajusta al
#: revisar; lo que no puede es que el reparto decida solo que alguien hace
#: veinte visitas.
TOPE_POR_CUADRILLA = 8

#: Como pesa la prioridad que se eligio al despachar, entre las que no
#: vencieron. Un valor que no esta aca pesa como media: un dato raro no manda
#: una orden ni arriba ni al fondo.
_RANGO_DE_PRIORIDAD = {
    OrdenTrabajo.PRIORIDAD_ALTA: 0,
    OrdenTrabajo.PRIORIDAD_MEDIA: 1,
    OrdenTrabajo.PRIORIDAD_BAJA: 2,
}


def _localidad_de(orden) -> str:
    """De donde es el trabajo, normalizado como los alias de zona.

    Se mira `zona` primero --es lo que la oficina escribio al despachar-- y
    despues la localidad del contexto congelado. Son dos fuentes y la primera
    gana: si alguien la escribio a mano, sabia algo que el proveedor no dice.
    """
    texto = normalizar_localidad(getattr(orden, "zona", "") or "")
    if texto:
        return texto
    contexto = getattr(orden, "contexto", None) or {}
    if isinstance(contexto, dict):
        cliente = contexto.get("cliente") or {}
        if isinstance(cliente, dict):
            return normalizar_localidad(cliente.get("localidad") or "")
    return ""


def _labor_de(orden) -> str:
    """A que labor pertenece este trabajo, o "" si nadie lo clasifico.

    Sale del `WorkType`, no de la orden: el tipo de trabajo es el catalogo de
    la empresa y es ahi donde se declara una vez, en vez de repetirlo en cada
    orden.
    """
    version = getattr(orden, "tipo_trabajo_version", None)
    tipo = getattr(version, "work_type", None)
    return (getattr(tipo, "labor", "") or "").strip()


def _precio_de(orden, precios: dict):
    """Cuanto paga ese cliente, o `None` si no se sabe.

    Se cruza por el ID del plan y no por su nombre: renombrar 'PLAN ELITE' a
    'PLAN ELITE 700' rompe un cruce por texto en silencio, y esas ordenes
    dejarian de pesar sin error ni alerta.
    """
    contexto = getattr(orden, "contexto", None) or {}
    if not isinstance(contexto, dict):
        return None
    cliente = contexto.get("cliente") or {}
    if not isinstance(cliente, dict):
        return None
    plan_id = cliente.get("plan_id")
    if plan_id is None:
        return None
    fila = precios.get(str(plan_id)) or {}
    crudo = fila.get("precio")
    if crudo is None:
        return None
    try:
        return Decimal(str(crudo))
    except (InvalidOperation, ValueError):
        return None


def _riesgo_de(orden, plazo: dict) -> tuple:
    """La clave de orden: menos es mas urgente.

    Una orden sin plazo calculable NO se pone primera ni ultima por accidente:
    va despues de las que si tienen plazo, porque de esas se sabe que urgen y
    de esta no se sabe nada. Sin este desempate quedaria mezclada segun el
    orden en que la base la devolvio.
    """
    restantes = plazo.get("minutos_restantes")
    atraso = plazo.get("minutos_atraso")
    if atraso:
        # Ya vencio: cuanto mas atraso, mas arriba.
        return (0, -atraso)
    if restantes is not None:
        return (1, restantes)
    return (2, 0)


def _urgencia(orden, plazo: dict) -> tuple:
    """La clave de orden con la prioridad adentro: menos es mas urgente.

    LO VENCIDO VA PRIMERO, SIEMPRE, y entre lo vencido manda el atraso: ya se
    incumplio, y la prioridad no lo vuelve menos incumplido. Entre lo que no
    vencio manda la prioridad que se eligio al despachar, y dentro de cada
    prioridad, la que vence antes (sin plazo, al final de su grupo).
    """
    clase, valor = _riesgo_de(orden, plazo)
    if clase == 0:
        return (0, 0, clase, valor)
    rango = _RANGO_DE_PRIORIDAD.get(getattr(orden, "prioridad", ""), 1)
    return (1, rango, clase, valor)


def _como_fecha(fecha):
    """La fecha del reparto como `date`: la pantalla la manda como texto."""
    import datetime as _dt

    if isinstance(fecha, _dt.datetime):
        return fecha.date()
    if isinstance(fecha, _dt.date):
        return fecha
    return _dt.date.fromisoformat(str(fecha))


def _zona_de(org):
    """La zona horaria de ESA empresa (`Org.timezone`), no la del servidor.

    El servidor corre en UTC (`settings.TIME_ZONE`), asi que
    `timezone.localtime` daria el dia de Greenwich: en Bogota, todo lo
    programado despues de las siete de la noche caeria en el dia siguiente.
    Mismo criterio y misma caida a UTC que `campo.tasks._ahora_local`.
    """
    import zoneinfo

    nombre = (getattr(org, "timezone", "") or "UTC").strip() or "UTC"
    try:
        return zoneinfo.ZoneInfo(nombre)
    except Exception:                                            # noqa: BLE001
        return zoneinfo.ZoneInfo("UTC")


def _para_otro_dia(orden, dia, zona) -> bool:
    """Si la orden esta programada para un dia POSTERIOR al del reparto.

    Hasta el 23/10/2026 el reparto no miraba `programada_para`: una orden para
    mañana se repartia hoy, y el tecnico llegaba a una cita que el cliente
    habia pedido para otro dia. Lo programado para hoy o para un dia que ya
    paso si entra: si nadie la hizo, sigue esperando a alguien.

    El dia en el reloj de la empresa (`_zona_de`).
    """
    cuando = getattr(orden, "programada_para", None)
    if cuando is None:
        return False
    return cuando.astimezone(zona).date() > dia


def vueltas_empezadas(org, ids) -> set:
    """De esas ordenes, las que tienen la VUELTA ACTUAL empezada.

    Es la regla de `operaciones.programacion.clasificar_ruta` (la ruta de
    contingencia), en tres consultas para todas en vez de dos por orden:

        sin devoluciones   ->  `iniciada_en` escrito
        con devoluciones   ->  un inicio (en camino, en sitio) despues de la
                               ultima reapertura

    POR QUE NO `trabajo_iniciado` (23/10/2026). Hasta aca la linea era ese
    evento, y NINGUN codigo de produccion lo escribe: solo las pruebas lo
    fabricaban. En los hechos nada contaba como empezado, y publicar le
    quitaba la orden al tecnico que ya la habia marcado en camino.

    POR QUE NO `iniciada_en` A SECAS: se escribe una sola vez, asi que una
    orden devuelta a correccion contaria como empezada para siempre y no
    volveria a repartirse nunca -- justo la que mas lo necesita. Ver
    «LA FRONTERA NO ES 'iniciada_en'» en `operaciones/programacion.py`.
    """
    from django.db.models import Max

    from operaciones.programacion import ESTADOS_DE_INICIO, EVENTO_REAPERTURA

    iniciadas = dict(OrdenTrabajo.objects
                     .filter(org=org, id__in=list(ids))
                     .values_list("id", "iniciada_en"))
    if not iniciadas:
        return set()
    reabiertas = dict(
        EventoTrabajo.objects
        .filter(orden_id__in=list(iniciadas), tipo=EVENTO_REAPERTURA)
        .order_by()
        .values("orden_id")
        .annotate(ultima=Max("created_at"))
        .values_list("orden_id", "ultima"))
    inicios: dict = {}
    for orden_id, cuando in (EventoTrabajo.objects
                             .filter(orden_id__in=list(reabiertas),
                                     datos__nuevo_estado__in=ESTADOS_DE_INICIO)
                             .values_list("orden_id", "created_at")):
        inicios.setdefault(orden_id, []).append(cuando)

    empezadas = set()
    for orden_id, iniciada_en in iniciadas.items():
        ultima = reabiertas.get(orden_id)
        if ultima is None:
            if iniciada_en is not None:
                empezadas.add(orden_id)
        elif any(c > ultima for c in inicios.get(orden_id, ())):
            empezadas.add(orden_id)
    return empezadas


#: Los eventos que dicen QUIEN decidio el ultimo cambio de manos de una orden.
EVENTOS_MANUALES = ("asignacion", "reasignacion")
EVENTOS_QUE_LIBERAN = ("reasignada_por_reparto", "cuadrilla_desasignada")


def _asignadas_a_mano(org, ids=None) -> set:
    """Ordenes cuya ULTIMA decision de asignacion la tomo una persona.

    Con `ids`, solo esas: publicar lo pregunta por una orden, bajo bloqueo.
    """
    eventos = EventoTrabajo.objects.filter(
        org=org, tipo__in=EVENTOS_MANUALES + EVENTOS_QUE_LIBERAN)
    if ids is not None:
        eventos = eventos.filter(orden_id__in=list(ids))
    ultimo: dict = {}
    for orden_id, tipo in (
        eventos
        .order_by("created_at")
        .values_list("orden_id", "tipo")
    ):
        ultimo[orden_id] = tipo
    candidatas = {o for o, t in ultimo.items() if t in EVENTOS_MANUALES}
    #  Y que hoy tenga a alguien: una manual que despues quedo sin nadie
    #  (desasignada por otro camino) no tiene a quien respetar.
    con_alguien = set(AsignacionTrabajo.objects
                      .filter(orden_id__in=candidatas)
                      .values_list("orden_id", flat=True))
    return candidatas & con_alguien


def proponer(org, fecha, *, ahora=None, plazo_de=None, tope=None,
             precios_por_plan=None):
    """La jornada propuesta de un dia. No escribe nada.

    `plazo_de` se inyecta para que las pruebas no dependan del calendario de
    la empresa ni del reloj: el reparto tiene que ser reproducible, y dos
    corridas con los mismos datos tienen que dar lo mismo.

    Devuelve:
        {
          "asignaciones": [{"cuadrilla": c, "ordenes": [...]}],
          "sin_zona":      [ordenes cuya localidad no esta mapeada],
          "sin_cuadrilla": [ordenes de zonas que nadie cubre hoy CON SU LABOR],
          "sobrantes":     [ordenes que no entraron por el tope],
          "sin_clasificar":[ordenes cuyo tipo no declara a que labor va],
          "otro_dia":      [ordenes programadas para un dia posterior],
          "empezadas":     [ya empezadas que siguen con quien las tiene],
        }
    """
    #  El tope de la empresa cuando no se pide uno. Se resuelve aca y no en el
    #  default del parametro: un default se evalua al IMPORTAR el modulo, asi
    #  que leeria la configuracion una sola vez en la vida del proceso y no se
    #  enteraria de un cambio hecho desde la pantalla.
    if tope is None:
        from campo.cuadrillas import configuracion_de_reparto
        tope = configuracion_de_reparto(org).tope_por_cuadrilla

    jornadas = list(
        JornadaDeCuadrilla.objects
        .filter(org=org, fecha=fecha)
        .select_related("cuadrilla")
        .prefetch_related("zonas")
    )

    # Que zonas cubre cada cuadrilla hoy. Una cuadrilla SIN zonas no entra:
    # vacio es "sin zona asignada", nunca "cubre todas".
    zonas_de = {j.id: [str(z.id) for z in j.zonas.all()] for j in jornadas}

    espera = lo_que_espera(org)
    ordenadas = sorted(espera["pendientes"],
                       key=clave_de_reparto(precios_por_plan, plazo_de, ahora))

    #  EL TOPE ES POR CUADRILLA, no uno solo para todas.
    #
    #  Una cuadrilla de dos personas no rinde lo mismo que una de cuatro, y un
    #  numero unico obliga a elegir entre sobrecargar a la chica o
    #  desaprovechar a la grande. `Cuadrilla.tope_diario` manda; si no lo
    #  declara, vale el de la empresa, y si la empresa no tiene fila, el de
    #  fabrica. Ninguno de los tres es capacidad calculada: es un freno.
    topes = {
        j.id: (j.cuadrilla.tope_diario or tope)
        for j in jornadas
    }

    r = repartir(ordenadas, jornadas, zonas_de=zonas_de, topes=topes,
                 zona_de_barrio=zona_de_barrio(org), dia=_como_fecha(fecha),
                 zona_horaria=_zona_de(org))

    return {
        "asignaciones": [
            {"jornada": j, "cuadrilla": j.cuadrilla,
             "ordenes": r["asignadas"][j.id]}
            for j in jornadas
        ],
        "sin_zona": r["sin_zona"],
        #  Las que una persona asigno a mano: no se tocan, y se nombran para
        #  que nadie las busque entre las «perdidas».
        "a_mano": espera["a_mano"],
        "sin_cuadrilla": r["sin_cuadrilla"],
        "sobrantes": r["sobrantes"],
        # Las que ni siquiera se pudieron evaluar: su tipo de trabajo no dice
        # a que labor pertenece. Se arregla clasificando el tipo UNA vez, no
        # orden por orden.
        "sin_clasificar": r["sin_clasificar"],
        #  Programadas para un dia posterior: salen en el reparto de ese dia.
        "otro_dia": r["otro_dia"],
        #  Ya empezadas y todavia esperando: siguen con quien las tiene.
        "empezadas": espera["empezadas"],
    }


# ---------------------------------------------------------------------------
#  LAS PIEZAS DE PROPONER  --  24/10/2026
# ---------------------------------------------------------------------------
#
#  Separadas sin cambiar nada para que «Simular el dia»
#  (`operaciones/simulacion_del_dia.py`) reparta con la MISMA regla las
#  ordenes que ya existen y las que el Supervisor crearia, entre las jornadas
#  que armaria. Una segunda copia del reparto se desincronizaria el primer
#  dia que alguien toque una de las dos.

def zona_de_barrio(org) -> dict:
    """{barrio normalizado: id de su zona activa}. Se arma una vez: preguntarlo
    por orden seria una consulta por fila."""
    from campo.zonas import AliasDeZona, MapaDeBarrios

    #  CON O SIN TILDE (25/10/2026): ver `MapaDeBarrios`.
    return MapaDeBarrios({
        a.localidad: str(a.zona_id)
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
    })


def lo_que_espera(org) -> dict:
    """Las ordenes que el reparto puede mover, y las que no se tocan.

        {"pendientes": [las que esperan a alguien y nadie empezo ni asigno a
                        mano], "a_mano": [...], "empezadas": [...]}
    """
    #  QUIEN EMPEZO UN TRABAJO LO TERMINA, y lo que nadie toco vuelve a
    #  repartirse.
    #
    #  Antes se excluia TODA orden con asignacion, asi que una de ayer que
    #  nadie visito se quedaba pegada a su cuadrilla aunque esa cuadrilla hoy
    #  no cubriera su zona. El SLA no podia moverla y nadie veia por que.
    #
    #  La linea esta donde de verdad esta: la vuelta actual empezo
    #  (`vueltas_empezadas`). Si alguien ya salio para alla, sabe algo que el
    #  reparto no; si no salio nadie, la orden es tan libre como una nueva.
    ya_empezadas = vueltas_empezadas(org, OrdenTrabajo.objects.filter(
        org=org, estado_operativo__in=ESTADOS_QUE_ESPERAN
    ).values_list("id", flat=True))
    #  LO QUE UNA PERSONA ASIGNO A MANO NO SE REPARTE (13/10/2026). Desde que
    #  se puede elegir el tecnico al despachar, el reparto -- que reasigna lo
    #  que nadie empezo -- movia esa decision a otra cuadrilla en la siguiente
    #  publicacion, sin que nadie lo decidiera. La ultima palabra sobre quien
    #  tiene la orden esta en la bitacora: si fue una asignacion manual, se
    #  respeta; si despues el reparto la movio o se desasigno, vuelve a ser
    #  libre.
    a_mano_ids = _asignadas_a_mano(org)
    pendientes = list(
        OrdenTrabajo.objects
        .filter(org=org, estado_operativo__in=ESTADOS_QUE_ESPERAN)
        .exclude(id__in=ya_empezadas)
        .exclude(id__in=a_mano_ids)
        .select_related("tipo_trabajo_version__work_type")
    )
    a_mano = list(OrdenTrabajo.objects
                  .filter(org=org, id__in=a_mano_ids,
                          estado_operativo__in=ESTADOS_QUE_ESPERAN)
                  .exclude(id__in=ya_empezadas))
    #  LAS EMPEZADAS QUE SIGUEN ESPERANDO (23/10/2026): por ejemplo, una que
    #  volvio de un bloqueo a «asignada». Siguen con quien las tiene, y se
    #  NOMBRAN: sin esta lista no aparecian en ninguna (lo encontro la
    #  auditoria de la Fase 2.2).
    empezadas = list(OrdenTrabajo.objects
                     .filter(org=org, id__in=ya_empezadas,
                             estado_operativo__in=ESTADOS_QUE_ESPERAN)
                     .order_by("numero"))
    return {"pendientes": pendientes, "a_mano": a_mano, "empezadas": empezadas}


def clave_de_reparto(precios_por_plan=None, plazo_de=None, ahora=None):
    """La clave con que se ordena lo que se reparte, con su desempate estable
    por numero (ver «EL ORDEN, Y POR QUE ESE» arriba)."""
    if plazo_de is None:                      # import tardio: evita el ciclo
        from operaciones.sla import plazo_de as _plazo
        plazo_de = _plazo
    precios = precios_por_plan or {}

    def clave(o):
        p = _precio_de(o, precios)
        # Mas caro primero -> precio NEGADO. Sin precio queda en el medio: ni
        # arriba como si fuera el mas caro, ni al fondo como si fuera gratis.
        peso = (0, -p) if p is not None else (1, Decimal(0))
        return _urgencia(o, plazo_de(o, ahora=ahora)) + peso + (o.numero or 0,)

    return clave


def repartir(ordenadas, jornadas, *, zonas_de: dict, topes: dict,
             zona_de_barrio: dict, dia, zona_horaria,
             carga_inicial: dict | None = None) -> dict:
    """Reparte `ordenadas` (ya en su orden) entre `jornadas`. No consulta la
    base ni escribe nada.

    Cada jornada necesita `id`, `labor` y `cuadrilla.nombre`; `zonas_de` y
    `topes` van por `id`. Por eso sirve igual para las jornadas de la base y
    para las que el Supervisor armaria.

    `carga_inicial` (27/10/2026, fase 3.1): lo que cada jornada ya tiene hoy.
    Sin ella cada vuelta arranca en cero, y una cuadrilla con tope 8 terminaba
    con 11 si entraban ordenes despues de publicar (auditorias de frontera e
    independiente). El boton no la pasa: reparte el dia entero de una vez.

        {"asignadas": {jornada.id: [ordenes]}, "sin_zona", "sin_cuadrilla",
         "sobrantes", "sin_clasificar", "otro_dia"}
    """
    # Que zonas cubre cada cuadrilla hoy, Y CON QUE LABOR.
    #
    # La clave lleva la labor porque una cuadrilla puesta en correctivo no
    # puede recibir instalaciones -- hasta el 08/10/2026 el reparto ignoraba
    # ese campo y se las daba igual.
    por_zona: dict = {}
    for j in jornadas:
        for z in zonas_de.get(j.id, ()):
            por_zona.setdefault((str(z), j.labor), []).append(j)

    carga = {j.id: (carga_inicial or {}).get(j.id, 0) for j in jornadas}
    asignadas: dict = {j.id: [] for j in jornadas}
    sin_zona, sin_cuadrilla, sobrantes, sin_clasificar = [], [], [], []
    otro_dia = []

    for orden in ordenadas:
        #  LO QUE ES PARA OTRO DIA, ESE DIA. Va primero: no importa si tiene
        #  zona o cuadrilla, hoy no le toca.
        if _para_otro_dia(orden, dia, zona_horaria):
            otro_dia.append(orden)
            continue

        # LA LABOR PRIMERO. Una orden sin clasificar no se reparte: ningun
        # codigo de tipo de trabajo dice a que labor pertenece --cada empresa
        # nombra los suyos-- y mandarla a cualquier cuadrilla seria adivinar.
        # Mismo criterio que la zona, y se nombra igual.
        labor = _labor_de(orden)
        if not labor:
            sin_clasificar.append(orden)
            continue

        barrio = _localidad_de(orden)
        zona_id = zona_de_barrio.get(barrio) if barrio else None
        if not zona_id:
            sin_zona.append(orden)
            continue

        candidatas = por_zona.get((zona_id, labor)) or []
        if not candidatas:
            # Nadie cubre esa zona HOY con esa labor. Puede ser que nadie la
            # cubra, o que quien la cubre hoy este haciendo otra cosa: las dos
            # se arreglan igual --poniendo una cuadrilla-- y por eso van
            # juntas.
            sin_cuadrilla.append(orden)
            continue

        # La menos cargada de las que cubren esa zona, con desempate estable
        # por nombre: sin el, dos corridas pueden repartir distinto.
        con_lugar = [j for j in candidatas if carga[j.id] < topes[j.id]]
        if not con_lugar:
            sobrantes.append(orden)
            continue
        elegida = min(con_lugar, key=lambda j: (carga[j.id], j.cuadrilla.nombre))
        asignadas[elegida.id].append(orden)
        carga[elegida.id] += 1

    return {"asignadas": asignadas, "sin_zona": sin_zona,
            "sin_cuadrilla": sin_cuadrilla, "sobrantes": sobrantes,
            "sin_clasificar": sin_clasificar, "otro_dia": otro_dia}


# ---------------------------------------------------------------------------
#  PUBLICAR  --  lo que el boton hace, y lo que va a hacer el Supervisor
# ---------------------------------------------------------------------------
#
#  Hasta el 23/10/2026 vivia dentro de `RepartoView.post`. Sale aca para que
#  el Supervisor (Fase 3.1 de SPEC/objetivos/supervisor-arma-la-jornada.md)
#  publique con la MISMA funcion que el boton, y no con una copia que se
#  desincronice el primer dia que alguien toque una de las dos.

def publicar(org, asignaciones, *, mover: bool = True,
             por_el_supervisor: dict | None = None,
             trabajan_hoy: frozenset | None = None) -> dict:
    """Escribe las asignaciones que se vieron. No recalcula.

    `asignaciones` = [{"jornada": id, "ordenes": [id, ...]}], lo que la
    pantalla mostro. Si recalculara, entre mirar y publicar podrian aparecer
    ordenes nuevas y se publicaria algo que nadie reviso.

    Pero lo que se vio puede haber cambiado, y eso SI se relee: cada orden se
    toma bajo bloqueo y se vuelve a preguntar si todavia espera a alguien, si
    nadie la empezo y si nadie la asigno a mano mientras tanto. Lo que se
    decide es la fila bloqueada, nunca lo que la pantalla creia.

    LO QUE AGREGO LA FASE 3.1 (27/10/2026)
    --------------------------------------
    `mover=False`: lo que ya tiene gente NO se mueve, solo se asigna lo que no
    tenia a nadie. Es la regla del Supervisor (decision del usuario del 21/10:
    lo publicado queda quieto y lo nuevo se suma; ver
    `operaciones/publicacion_del_reparto.py`). El boton humano sigue moviendo,
    como siempre.

    `trabajan_hoy` (con `mover=False`): las cuentas que hoy trabajan. Una
    orden cuya gente NO esta en ese conjunto --no salio hoy, o declaro
    ausencia-- si se mueve: si no, quedaria en el telefono de quien no sale. Se
    decide sobre la fila bloqueada, con la gente que tiene en ese momento.

    `por_el_supervisor`: los datos del evento `asignada_por_el_supervisor`
    que se deja en cada orden que asigna el Supervisor, sin persona (el patron
    de `creada_por_el_supervisor`). Es OTRO tipo que el `asignacion` de una
    persona, a proposito: ese es el que congela una orden para el reparto
    (`_asignadas_a_mano`), y lo que asigno el Supervisor se puede volver a
    acomodar antes de que arranque el dia.

    Y avisa al telefono, una vez por persona, con lo que ESTA publicacion le
    dio (`avisos.avisar_jornada_publicada`).
    """
    from django.db import transaction

    publicadas = 0
    ya_tenian, ya_no_esperan, a_mano, sin_cambio = [], [], [], []
    sin_cuenta, reasignadas, otro_dia, quietas = [], [], [], []
    #  {fecha: {Profile: [OrdenTrabajo]}}: lo que cada persona recibe por
    #  primera vez en esta publicacion, para avisarle una sola vez.
    nuevas: dict = {}
    #  Se acumula FUERA del ciclo: una variable por cuadrilla solo
    #  guardaria la ultima, y con dos cuadrillas el numero mentiria.
    auxiliares = 0
    zona = _zona_de(org)
    with transaction.atomic():
        #  TODAS SE BLOQUEAN DE UNA VEZ, EN ORDEN DE id. Una por una y en el
        #  orden en que llegan, dos publicaciones con las mismas ordenes
        #  cruzadas se esperarian entre si y Postgres abortaria una entera.
        ids = [oid for cruda in asignaciones
               for oid in ((cruda or {}).get("ordenes") or [])]
        bloqueadas = {
            str(o.id): o
            for o in (OrdenTrabajo.objects.select_for_update()
                      .filter(org=org, id__in=ids).order_by("id"))
        }
        for cruda in asignaciones:
            jornada = JornadaDeCuadrilla.objects.filter(
                org=org, id=(cruda or {}).get("jornada")
            ).prefetch_related("integrantes__persona").first()
            if jornada is None:
                continue

            # QUIEN RECIBE LA ORDEN: el lider del dia siempre, aunque no
            # este anotado entre los integrantes, y quien mas tenga cuenta.
            # El auxiliar sin celular integra la cuadrilla --y por eso
            # queda en la jornada, que es donde se lee quien estuvo-- pero
            # no es a quien se le manda el trabajo. La regla vive en
            # `cuadrillas.destinatarios`, la misma del despacho a mano y
            # del recuadro de la zona (15/10/2026: hasta ahi cada camino
            # tenia su copia, y las tres ignoraban al lider).
            quienes = destinatarios(jornada)
            if not quienes["reciben"]:
                # Nadie que la vea en un telefono: la orden quedaria sin
                # una sola asignacion. Se SALTEA y se dice -- publicar cero
                # asignaciones e informar exito seria peor que no publicar.
                sin_cuenta.append(jornada.cuadrilla.nombre)
                continue

            auxiliares += len(quienes["van_sin_cuenta"])
            nuevos = {(r["profile"].id, r["es_principal"])
                      for r in quienes["reciben"]}
            for oid in (cruda or {}).get("ordenes") or []:
                orden = bloqueadas.get(str(oid))
                if orden is None:
                    continue

                #  LO QUE YA SE EMPEZO NO SE PISA; LO QUE NADIE TOCO, SI.
                #
                #  Con el ESTADO de la fila bloqueada y la vuelta real
                #  (`vueltas_empezadas`), no con `trabajo_iniciado`, que
                #  nadie escribe: hasta el 23/10/2026 una orden marcada en
                #  camino entre mirar y publicar cambiaba de manos igual.
                if orden.estado_operativo in (OrdenTrabajo.EN_CAMINO,
                                              OrdenTrabajo.EN_SITIO):
                    ya_tenian.append(orden.numero)
                    continue
                if orden.estado_operativo not in ESTADOS_QUE_ESPERAN:
                    #  Se cerro, se cancelo o se bloqueo mientras tanto.
                    ya_no_esperan.append(orden.numero)
                    continue
                if vueltas_empezadas(org, [orden.id]):
                    ya_tenian.append(orden.numero)
                    continue
                #  Una persona la asigno a mano despues de que se miro: esa
                #  decision gana, igual que en `proponer` (13/10/2026).
                if _asignadas_a_mano(org, [orden.id]):
                    a_mano.append(orden.numero)
                    continue
                #  La programaron para otro dia despues de que se miro.
                if _para_otro_dia(orden, jornada.fecha, zona):
                    otro_dia.append(orden.numero)
                    continue

                viejas = list(orden.asignaciones.all())
                #  YA ESTA CON ESA GENTE: no se toca. Borrarla y volverla a
                #  crear dejaba en la bitacora una «reasignacion» de la
                #  cuadrilla a si misma, y el telefono la recibia como
                #  cambiada sin que nada cambiara.
                if viejas and {(a.profile_id, a.es_principal)
                               for a in viejas} == nuevos:
                    sin_cambio.append(orden.numero)
                    continue
                if viejas and not mover and not (
                        trabajan_hoy is not None
                        and {a.profile_id for a in viejas}.isdisjoint(
                            trabajan_hoy)):
                    #  LO PUBLICADO QUEDA QUIETO (decision del 21/10/2026):
                    #  un tecnico sin señal que ya va en camino la perderia al
                    #  sincronizar. Salvo que quien la tiene hoy no trabaja.
                    quietas.append(orden.numero)
                    continue
                if viejas:
                    #  Se REEMPLAZA, y queda escrito quien la tenia. Borrar
                    #  sin registro seria perder el unico dato que explica
                    #  por que un trabajo cambio de manos.
                    EventoTrabajo.objects.create(
                        org=org, orden=orden, tipo="reasignada_por_reparto",
                        datos={
                            "de": [str(a.profile_id) for a in viejas],
                            "a_cuadrilla": jornada.cuadrilla.nombre,
                            "motivo": ("nadie la habia empezado y el "
                                       "reparto del dia la movio"),
                        },
                    )
                    orden.asignaciones.all().delete()
                    reasignadas.append(orden.numero)
                antes = {a.profile_id for a in viejas}
                for r in quienes["reciben"]:
                    AsignacionTrabajo.objects.create(
                        orden=orden,
                        profile=r["profile"],
                        rol=r["rol"],
                        es_principal=r["es_principal"],
                    )
                    if r["profile"].id not in antes:
                        (nuevas.setdefault(jornada.fecha, {})
                         .setdefault(r["profile"], []).append(orden))
                #  SUBE LA REVISION: la orden cambio en el servidor, y
                #  `revision` cuenta escrituras (viaja como `revision_base`
                #  cuando el telefono guarda datos). Quien la tenia deja de
                #  verla porque ya no le viene en el listado: el telefono
                #  suelta lo que el servidor no le lista (27/10/2026,
                #  `LocalDatabase.soltarOrdenesQueYaNoSonMias`).
                orden.revision += 1
                orden.save(update_fields=["revision", "updated_at"])
                if por_el_supervisor is not None:
                    EventoTrabajo.objects.create(
                        org=org, orden=orden,
                        tipo="asignada_por_el_supervisor", profile=None,
                        datos={**por_el_supervisor,
                               "cuadrilla": jornada.cuadrilla.nombre,
                               "jornada": str(jornada.id)})
                publicadas += 1

        #  EL AVISO AL TELEFONO (3.1): dentro de la transaccion se escribe la
        #  notificacion --es parte del hecho--, y el envio sale despues del
        #  commit. Si la publicacion se deshace, no sale nada.
        if nuevas:
            from campo.services.avisos import avisar_jornada_publicada
            for fecha, por_perfil in nuevas.items():
                avisar_jornada_publicada(org, por_perfil, fecha)

    return {
        "publicadas": publicadas,
        # Se nombran: si no, la cuenta no cuadra con lo que se vio y nadie
        # sabe cuales quedaron afuera.
        "ya_tenian": ya_tenian,
        "ya_no_esperan": ya_no_esperan,
        "a_mano": a_mano,
        "sin_cambio": sin_cambio,
        "otro_dia": otro_dia,
        # Las cuadrillas que no se pudieron publicar porque NADIE en ellas
        # entra al sistema. Un silencio aca haria creer que se repartio
        # todo.
        "sin_nadie_con_cuenta": sin_cuenta,
        # Cuantos auxiliares integran las cuadrillas publicadas sin recibir
        # asignacion: es lo esperado, no un error, pero se dice para que
        # nadie lo lea como gente perdida.
        "auxiliares_sin_asignacion": auxiliares,
        #  Las que cambiaron de cuadrilla: nadie las habia empezado, asi
        #  que el reparto del dia las movio. Se nombran porque alguien
        #  puede estar esperandolas donde estaban.
        "reasignadas": reasignadas,
        #  Con `mover=False`: ya tenian gente y el dia ya arranco.
        "quietas": quietas,
    }


# ---------------------------------------------------------------------------
#  COBERTURA  --  lo que el supervisor tiene que ver AL DESPACHAR (13/10/2026)
# ---------------------------------------------------------------------------
#
#  Al despachar se veia el barrio pero no a que ZONA pertenece ni que CUADRILLA
#  la cubre ese dia -- justo lo que decide a quien le llega el trabajo. Se
#  enteraba despues, en el reparto, si quedo «sin zona» o «nadie cubre».
#
#  Es la MISMA regla que `proponer()`: barrio -> alias -> zona -> las jornadas
#  del dia que cubren esa zona, y de esas, las que estan en esa labor. Una
#  segunda version de la regla, en la pantalla, se desincronizaria el primer
#  dia que alguien la toque aca.

def cobertura(org, barrio: str, fecha, labor: str = "") -> dict:
    """Para un barrio y un dia: la zona, y que cuadrillas la cubren. No escribe.

    `motivo` resume lo que la persona tiene que saber:
        "cubierta"          hay al menos una jornada de esa zona y esa labor
        "otra_labor"        la zona la cubre alguien, pero hoy con otra labor
        "sin_jornada"       nadie cubre esa zona ese dia (o no se armo el dia)
        "sin_zona"          el barrio no esta en ninguna zona
        "sin_barrio"        no hay barrio
    """
    from campo.zonas import AliasDeZona, parecidas

    texto = normalizar_localidad(barrio)
    if not texto:
        return {"barrio": "", "zona": None, "jornadas": [], "habituales": [],
                "motivo": "sin_barrio"}
    alias = (AliasDeZona.objects
             .filter(org=org, localidad=texto, zona__activa=True)
             .select_related("zona").first())
    if alias is None:
        return {"barrio": texto, "zona": None, "jornadas": [], "habituales": [],
                "parecidas": parecidas(org, texto), "motivo": "sin_zona"}
    zona = alias.zona

    jornadas = []
    for j in (JornadaDeCuadrilla.objects
              .filter(org=org, fecha=fecha, zonas=zona)
              .select_related("cuadrilla__lider__user", "lider__user")
              .order_by("cuadrilla__nombre")):
        quienes = destinatarios(j)
        jornadas.append({
            "jornada": str(j.id),
            "cuadrilla": j.cuadrilla.nombre,
            "labor": j.labor,
            "coincide_labor": (not labor) or j.labor == labor,
            #  QUIEN LA RECIBE en un telefono: el lider del dia primero, aunque
            #  no este anotado entre los integrantes (`cuadrillas.destinatarios`,
            #  la misma regla del despacho y del reparto). Los demas van con
            #  la cuadrilla pero no son destinatarios.
            "con_cuenta": [
                {"profile": str(r["profile"].id), "nombre": r["nombre"],
                 "lider": r["es_principal"]}
                for r in quienes["reciben"]
            ],
            "sin_cuenta": len(quienes["van_sin_cuenta"]),
            "van_con_el": quienes["van_sin_cuenta"],
            #  Por que nadie la recibiria, para que la pantalla lo diga.
            "aviso": (None if quienes["reciben"]
                      else por_que_nadie_recibe(j, quienes)),
        })

    #  Si ese dia nadie la cubre, quien la trabaja HABITUALMENTE: es la pista de
    #  a quien hay que armarle la jornada.
    habituales = [
        {"cuadrilla": c.nombre, "labor": c.labor_habitual}
        for c in zona.cuadrillas_habituales.filter(activa=True).order_by("nombre")
    ]

    if any(j["coincide_labor"] for j in jornadas):
        motivo = "cubierta"
    elif jornadas:
        motivo = "otra_labor"
    else:
        motivo = "sin_jornada"
    return {"barrio": texto, "zona": {"id": str(zona.id), "nombre": zona.nombre},
            "jornadas": jornadas, "habituales": habituales, "motivo": motivo}
