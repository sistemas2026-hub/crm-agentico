"""
================================================================================
 INFORME DE CRUCES  --  27/10/2026
================================================================================
Cuenta, sin escribir nada, cuántos días dos o más cuadrillas tuvieron órdenes
en el mismo barrio, y qué porcentaje de las órdenes trae las coordenadas del
cliente.

POR QUÉ EXISTE
--------------
Antes de decidir si el reparto tiene que ordenar por cercanía (o dejar de
mandar dos cuadrillas al mismo barrio el mismo día) hace falta saber dos
números: cuánto pasa, y si hay con qué medir la distancia. CLAUDE.md §10:
medir antes de decidir.

DE QUÉ DÍA ES UNA ORDEN, Y DE QUÉ CUADRILLA
-------------------------------------------
La orden no guarda su cuadrilla (ver `campo/cuadrillas.py`): guarda a quién se
le asignó. La cuadrilla se deduce con la misma regla que reparte el trabajo,
`cuadrillas.destinatarios`: quién recibe por cada jornada de ese día.

El día es el de `iniciada_en` (cuándo se fue de verdad); si no se empezó, el
de `programada_para`; si tampoco, el de su asignación. Siempre en el reloj de
la empresa (`reparto._zona_de`), no en UTC. Las canceladas no cuentan: no fue
nadie.

El barrio es el que usa el reparto (`reparto._localidad_de`): el que escribió
la oficina, o el del contexto del cliente.

LÍMITES CONOCIDOS (auditor independiente, 27/10/2026). La cuadrilla sale de
la asignación de HOY y de `destinatarios` con los datos de hoy: un técnico
dado de baja o un cambio de líder mueve órdenes viejas a «sin cuadrilla» (que
se imprime, no es silencioso). Una persona en dos jornadas el mismo día cuenta
para una sola. Y `OrdenTrabajo.zona` es el barrio en las órdenes del
Supervisor, pero en un despacho a mano puede ser el nombre de una zona: ahí
«mismo barrio» es «misma zona» y los cruces salen de más.

SIN DATOS DEL CLIENTE. Solo barrio, fecha y conteos: ni nombre, ni teléfono,
ni dirección, ni las coordenadas mismas (se cuenta si están, no dónde caen).
Tampoco el nombre de las cuadrillas: el pedido fue barrio, fecha y conteos.

Uso, dentro del contenedor del backend (desde /app):
  python manage.py informe_de_cruces --org <uuid> [--dias 30]
================================================================================
"""
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from common.models import Org
from common.tasks import set_rls_context

#: El mismo tope que 'informe_de_jornadas': tres meses cubren el trimestre.
MAX_DIAS = 92
DIAS_POR_DEFECTO = 30


def _tiene_coordenadas(orden) -> bool:
    """Las dos, y no el (0, 0): ese punto está en el mar, es un valor vacío."""
    lat, lng = orden.gps_lat, orden.gps_lng
    return lat is not None and lng is not None and not (lat == 0 and lng == 0)


def _dia_de(orden, zona):
    """El día de la orden en el reloj de la empresa, o None si no hay cómo saberlo.

    PRIMERO EL DÍA EN QUE SE EMPEZÓ, y después el programado: el reparto toma
    lo atrasado sin mover `programada_para` (`reparto._para_otro_dia`), así que
    una orden del 20 hecha el 22 se contaría el 20, con la cuadrilla de otro
    día (auditor independiente, 27/10/2026).
    """
    for cuando in (orden.iniciada_en, orden.programada_para):
        if cuando is not None:
            return cuando.astimezone(zona).date()
    asignaciones = sorted(orden.asignaciones.all(),
                          key=lambda a: (not a.es_principal, a.asignado_en))
    if asignaciones:
        return asignaciones[0].asignado_en.astimezone(zona).date()
    return None


def medir(org, *, dias: int, hasta) -> dict:
    """Los cruces y las coordenadas de los últimos `dias` hasta `hasta`. No escribe."""
    from campo.cuadrillas import JornadaDeCuadrilla, destinatarios
    from campo.models import OrdenTrabajo
    from campo.reparto import _localidad_de, _zona_de

    zona = _zona_de(org)
    desde = hasta - timedelta(days=dias - 1)

    #  Quién recibía por cada cuadrilla, cada día: (fecha, cuenta) -> cuadrilla.
    cuadrilla_de = {}
    for j in (JornadaDeCuadrilla.objects
              .filter(org=org, fecha__range=(desde, hasta))
              .select_related("cuadrilla", "lider")):
        for r in destinatarios(j)["reciben"]:
            cuadrilla_de.setdefault((j.fecha, r["profile"].id), j.cuadrilla_id)

    #  Las candidatas por SQL, con un día de margen a cada lado por la zona
    #  horaria; el día exacto se decide en Python, con '_dia_de'.
    inicio = datetime.combine(desde - timedelta(days=1), time.min, tzinfo=zona)
    fin = datetime.combine(hasta + timedelta(days=2), time.min, tzinfo=zona)
    candidatas = (OrdenTrabajo.objects
                  .filter(org=org)
                  .exclude(estado_operativo=OrdenTrabajo.CANCELADA)
                  .filter(Q(iniciada_en__range=(inicio, fin))
                          | Q(iniciada_en__isnull=True,
                              programada_para__range=(inicio, fin))
                          | Q(iniciada_en__isnull=True,
                              programada_para__isnull=True,
                              asignaciones__asignado_en__range=(inicio, fin)))
                  .distinct()
                  .prefetch_related("asignaciones"))

    ordenes = con_coordenadas = sin_barrio = sin_cuadrilla = 0
    por_dia_y_barrio = defaultdict(lambda: {"cuadrillas": set(), "ordenes": 0})
    for orden in candidatas:
        dia = _dia_de(orden, zona)
        if dia is None or not desde <= dia <= hasta:
            continue
        ordenes += 1
        con_coordenadas += _tiene_coordenadas(orden)
        barrio = _localidad_de(orden)
        if not barrio:
            sin_barrio += 1
            continue
        principales = sorted(orden.asignaciones.all(),
                             key=lambda a: not a.es_principal)
        cuadrilla = next((cuadrilla_de[(dia, a.profile_id)] for a in principales
                          if (dia, a.profile_id) in cuadrilla_de), None)
        if cuadrilla is None:
            sin_cuadrilla += 1
            continue
        celda = por_dia_y_barrio[(dia, barrio)]
        celda["cuadrillas"].add(cuadrilla)
        celda["ordenes"] += 1

    cruces = sorted(
        ({"fecha": dia, "barrio": barrio, "cuadrillas": len(c["cuadrillas"]),
          "ordenes": c["ordenes"]}
         for (dia, barrio), c in por_dia_y_barrio.items()
         if len(c["cuadrillas"]) >= 2),
        key=lambda x: (x["fecha"], x["barrio"]))
    return {
        "desde": desde, "hasta": hasta, "dias": dias, "zona": str(zona),
        "ordenes": ordenes, "con_coordenadas": con_coordenadas,
        "sin_barrio": sin_barrio, "sin_cuadrilla": sin_cuadrilla,
        "dias_con_cruce": len({c["fecha"] for c in cruces}),
        "cruces": cruces,
    }


def _porcentaje(parte, total) -> str:
    if not total:
        return "-"
    return f"{100 * parte / total:.1f} %".replace(".", ",")


class Command(BaseCommand):
    help = ("Cuántos días dos o más cuadrillas tuvieron órdenes en el mismo "
            "barrio, y qué porcentaje de órdenes trae coordenadas del cliente. "
            "No escribe nada.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")
        parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO,
                            help=f"cuántos días hacia atrás, de 1 a {MAX_DIAS}")

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        dias = options["dias"]
        if not 1 <= dias <= MAX_DIAS:
            raise CommandError(f"--dias va de 1 a {MAX_DIAS}.")
        set_rls_context(org.id)

        from campo.tasks import _ahora_local

        m = medir(org, dias=dias, hasta=_ahora_local(org).date())
        w = self.stdout.write
        w(f"cruces del {m['desde']} al {m['hasta']} ({m['dias']} días, "
          f"{m['zona']})")
        w("")
        w(f"órdenes con día en el período: {m['ordenes']}")
        w(f"  con coordenadas del cliente: {m['con_coordenadas']} "
          f"({_porcentaje(m['con_coordenadas'], m['ordenes'])})")
        w(f"  sin barrio: {m['sin_barrio']} · sin cuadrilla ese día: "
          f"{m['sin_cuadrilla']} (no entran en los cruces)")
        w("")
        w(f"días con al menos un cruce: {m['dias_con_cruce']} de {m['dias']}")
        w(f"cruces (un día y un barrio con 2 o más cuadrillas): "
          f"{len(m['cruces'])}")
        if not m["cruces"]:
            return
        w("")
        ancho = max(len("barrio"), *(len(c["barrio"]) for c in m["cruces"]))
        w(f"{'fecha':<12}{'barrio':<{ancho + 2}}{'cuadrillas':>10}{'órdenes':>9}")
        for c in m["cruces"]:
            w(f"{c['fecha'].isoformat():<12}{c['barrio']:<{ancho + 2}}"
              f"{c['cuadrillas']:>10}{c['ordenes']:>9}")
