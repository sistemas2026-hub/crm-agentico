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
    1. SLA        lo que esta por vencer va primero, siempre.
    2. antiguedad entre dos con el mismo riesgo, la que lleva mas esperando.
    3. numero     para que dos corridas con los mismos datos den lo mismo.

El tercero no es un criterio de negocio: es lo que hace el reparto
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

LA ZONA ES DURA
---------------
Una cuadrilla solo recibe ordenes de las zonas que cubre ese dia. Una orden
cuya localidad no esta mapeada a ninguna zona NO se reparte: queda en
`sin_zona`, que es una respuesta y no un silencio. Repartirla igual la mandaria
a cualquier lado; esconderla la dejaria sin hacer sin que nadie lo note.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from campo.cuadrillas import JornadaDeCuadrilla
from campo.models import AsignacionTrabajo, OrdenTrabajo
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


def proponer(org, fecha, *, ahora=None, plazo_de=None, tope=TOPE_POR_CUADRILLA,
             precios_por_plan=None):
    """La jornada propuesta de un dia. No escribe nada.

    `plazo_de` se inyecta para que las pruebas no dependan del calendario de
    la empresa ni del reloj: el reparto tiene que ser reproducible, y dos
    corridas con los mismos datos tienen que dar lo mismo.

    Devuelve:
        {
          "asignaciones": [{"cuadrilla": c, "ordenes": [...]}],
          "sin_zona":     [ordenes cuya localidad no esta mapeada],
          "sin_cuadrilla":[ordenes de zonas que nadie cubre hoy],
          "sobrantes":    [ordenes que no entraron por el tope],
        }
    """
    if plazo_de is None:                      # import tardio: evita el ciclo
        from operaciones.sla import plazo_de as _plazo
        plazo_de = _plazo

    jornadas = list(
        JornadaDeCuadrilla.objects
        .filter(org=org, fecha=fecha)
        .select_related("cuadrilla")
        .prefetch_related("zonas")
    )

    # Que zonas cubre cada cuadrilla hoy. Una cuadrilla SIN zonas no entra:
    # vacio es "sin zona asignada", nunca "cubre todas".
    por_zona: dict = {}
    for j in jornadas:
        for z in j.zonas.all():
            por_zona.setdefault(str(z.id), []).append(j)

    # De que zona es cada barrio. Se arma una vez: preguntarlo por orden seria
    # una consulta por fila.
    from campo.zonas import AliasDeZona

    zona_de_barrio = {
        a.localidad: str(a.zona_id)
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
    }

    pendientes = (
        OrdenTrabajo.objects
        .filter(org=org, estado_operativo__in=ESTADOS_QUE_ESPERAN)
        .exclude(asignaciones__isnull=False)
        .select_related("tipo_trabajo_version")
    )

    # El orden, con su desempate estable por numero.
    precios = precios_por_plan or {}

    def clave(o):
        p = _precio_de(o, precios)
        # Mas caro primero -> precio NEGADO. Sin precio queda en el medio: ni
        # arriba como si fuera el mas caro, ni al fondo como si fuera gratis.
        peso = (0, -p) if p is not None else (1, Decimal(0))
        return _riesgo_de(o, plazo_de(o, ahora=ahora)) + peso + (o.numero or 0,)

    ordenadas = sorted(pendientes, key=clave)

    carga = {j.id: 0 for j in jornadas}
    asignadas: dict = {j.id: [] for j in jornadas}
    sin_zona, sin_cuadrilla, sobrantes = [], [], []

    for orden in ordenadas:
        barrio = _localidad_de(orden)
        zona_id = zona_de_barrio.get(barrio) if barrio else None
        if not zona_id:
            sin_zona.append(orden)
            continue

        candidatas = por_zona.get(zona_id) or []
        if not candidatas:
            sin_cuadrilla.append(orden)
            continue

        # La menos cargada de las que cubren esa zona, con desempate estable
        # por nombre: sin el, dos corridas pueden repartir distinto.
        con_lugar = [j for j in candidatas if carga[j.id] < tope]
        if not con_lugar:
            sobrantes.append(orden)
            continue
        elegida = min(con_lugar, key=lambda j: (carga[j.id], j.cuadrilla.nombre))
        asignadas[elegida.id].append(orden)
        carga[elegida.id] += 1

    return {
        "asignaciones": [
            {"jornada": j, "cuadrilla": j.cuadrilla, "ordenes": asignadas[j.id]}
            for j in jornadas
        ],
        "sin_zona": sin_zona,
        "sin_cuadrilla": sin_cuadrilla,
        "sobrantes": sobrantes,
    }
