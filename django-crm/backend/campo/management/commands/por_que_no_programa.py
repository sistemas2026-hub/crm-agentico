"""
================================================================================
 POR QUE EL SUPERVISOR NO PROGRAMA UNA LABOR  --  13/11/2026
================================================================================
Recorre, en orden, TODAS las puertas que hay entre «el ISP tiene tickets de
instalacion» y «una cuadrilla sale a instalar», y dice en cual se corta.

    python manage.py por_que_no_programa --org <uuid> [--labor instalacion]

POR QUE EXISTE
--------------
El usuario reporto que el Supervisor no programa instalaciones. Hay SEIS
puertas en ese camino y ninguna avisa cuando se cierra: el ciclo apagado, un
dia que no se trabaja, la labor sin fila en la tabla de la empresa, ninguna
cuadrilla con esa labor habitual, los casos sin barrio o sin zona, y el tope
diario. Mirar la pantalla no distingue una de otra, y cada una se arregla de
una manera distinta.

El numero que mas costo encontrar, y por eso sale aparte: una instalacion
nueva NO TRAE BARRIO --su ficha es la del cliente ficticio-- asi que se le
cuenta a las zonas de las cuadrillas activas cuya labor habitual es la de
instalacion. Si ninguna la tiene, esos casos no entran en NINGUNA zona, la
demanda sale sin instalaciones, y el Supervisor arma el dia sin ellas sin que
nada quede en rojo. Ver `armado_de_jornadas.demanda_de_despacho`.

QUE SACA, Y QUE NO
------------------
Numeros, nombres de cuadrilla, de zona y de labor. Del cliente, NADA: ni
asunto, ni descripcion, ni nombre, ni telefono, ni direccion. Los tickets
salen por su numero. Es una salida pensada para pegarse en una conversacion.

NO ESCRIBE NADA. Ni una fila, ni una jornada, ni una orden: `planear_el_dia`
devuelve el plan en memoria y `aplicar` no se llama.

EL CONTEXTO RLS SE FIJA ACA, como en 'informe_de_despacho': un comando no pasa
por el middleware, y sin el las tablas devuelven 0 filas sin error --que se lee
igual que «no hay trabajo».
================================================================================
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from common.tasks import set_rls_context

#: Lo que se diagnostica por defecto, que es lo que el usuario reporto.
LABOR_POR_DEFECTO = "instalacion"


def _si_no(v) -> str:
    return "SI" if v else "NO"


class Command(BaseCommand):
    help = "Dice en que puerta se corta la programacion de una labor."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organizacion")
        parser.add_argument("--labor", default=LABOR_POR_DEFECTO,
                            help=f"la labor a diagnosticar (def. {LABOR_POR_DEFECTO})")
        parser.add_argument("--fecha", default="",
                            help="AAAA-MM-DD; por defecto, hoy en la empresa")

    def handle(self, *args, **options):
        from datetime import date

        from django.utils import timezone

        from campo import jornada_automatica as ja
        from campo import tasks as T
        from campo.cuadrillas import (
            INSTALACION_NUEVA,
            ConfiguracionDeReparto,
            Cuadrilla,
            configuracion_de_reparto,
            labor_de_cada_grupo,
        )
        from campo.labores import labor_valida
        from campo.reparto import _zona_de
        from campo.zonas import ZonaOperativa
        from operaciones import armado_de_jornadas as adj

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organizacion con ese id.")
        set_rls_context(org.id)

        labor_pedida = options["labor"]
        if options["fecha"]:
            try:
                fecha = date.fromisoformat(options["fecha"])
            except ValueError:
                raise CommandError("La fecha va como AAAA-MM-DD.")
        else:
            fecha = timezone.now().astimezone(_zona_de(org)).date()

        w = self.stdout.write
        w("=" * 78)
        w(f" POR QUE NO SE PROGRAMA '{labor_pedida}'   --   {fecha}")
        w("=" * 78)

        cortes = []     # las puertas cerradas, en orden

        # -- PUERTA 1: el ciclo de la empresa -----------------------------
        config = configuracion_de_reparto(org)
        hay_fila = ConfiguracionDeReparto.objects.filter(org=org).exists()
        w("")
        w("1 · EL CICLO DE LA MADRUGADA")
        w(f"    fila de configuracion propia ..... {_si_no(hay_fila)}"
          + ("" if hay_fila else "   (corre con los valores de fabrica)"))
        w(f"    activo ........................... {_si_no(config.activo)}")
        w(f"    copia_la_jornada ................. {_si_no(config.copia_la_jornada)}")
        w(f"    hora local ....................... {config.hora_local}")
        w(f"    ultima corrida ................... {config.ultima_corrida or '— nunca'}")
        w(f"    tope por cuadrilla ............... {config.tope_por_cuadrilla}")
        if not config.activo:
            cortes.append("el ciclo de la madrugada esta APAGADO (`activo`): "
                          "nadie arma la jornada sola")
        if not config.copia_la_jornada:
            cortes.append("`copia_la_jornada` esta en NO: el ciclo corre pero "
                          "no arma jornadas")
        if config.ultima_corrida != fecha:
            cortes.append(f"la ultima corrida del ciclo es "
                          f"{config.ultima_corrida or 'ninguna'}, no {fecha}: "
                          f"revisar celery-beat (corre a las :07)")

        # -- PUERTA 2: el dia ---------------------------------------------
        no_trabajan = T._las_cuadrillas_no_trabajan(org, fecha)
        w("")
        w("2 · EL DIA")
        w(f"    las cuadrillas trabajan .......... "
          f"{'NO  -- ' + no_trabajan if no_trabajan else 'SI'}")
        if no_trabajan:
            cortes.append(f"ese dia las cuadrillas no trabajan ({no_trabajan}): "
                          f"el Supervisor no arma, a proposito")

        # -- PUERTA 3: la labor existe y esta en la tabla -------------------
        labores = labor_de_cada_grupo(org)
        labor_nueva = labores.get(INSTALACION_NUEVA)
        w("")
        w("3 · LA LABOR EN LA TABLA DE LA EMPRESA")
        w(f"    '{labor_pedida}' es una labor valida ... "
          f"{_si_no(labor_valida(org, labor_pedida))}")
        w(f"    grupo '{INSTALACION_NUEVA}' -> ........ {labor_nueva or '— SIN FILA'}")
        for grupo, lab in sorted(labores.items()):
            w(f"      {grupo:<22} -> {lab}")
        sin_fila = [g for g in ConfiguracionDeReparto.LABOR_POR_GRUPO_DE_FABRICA
                    if g not in labores]
        if sin_fila:
            w(f"    grupos SIN labor ................. {', '.join(sin_fila)}")
        if not labor_valida(org, labor_pedida):
            cortes.append(f"'{labor_pedida}' no es una labor valida de esta "
                          f"empresa: se dio de baja, o esta mal escrita")
        if not labor_nueva:
            cortes.append(f"el grupo '{INSTALACION_NUEVA}' no tiene labor en la "
                          f"tabla: los casos de un cliente nuevo quedan en "
                          f"'sin_labor' y no piden cuadrilla")

        # -- PUERTA 4: cuadrillas con esa labor habitual --------------------
        con_la_labor = list(Cuadrilla.objects
                            .filter(org=org, activa=True,
                                    labor_habitual=labor_pedida)
                            .prefetch_related("zonas_habituales"))
        w("")
        w("4 · LAS CUADRILLAS")
        w(f"    activas en total ................. "
          f"{Cuadrilla.objects.filter(org=org, activa=True).count()}")
        w(f"    con labor habitual '{labor_pedida}' .. {len(con_la_labor)}")
        zonas_de_la_labor = set()
        for c in con_la_labor:
            zs = [z for z in c.zonas_habituales.all() if z.activa]
            zonas_de_la_labor.update(str(z.id) for z in zs)
            w(f"      {c.nombre:<24} zonas: "
              f"{', '.join(z.nombre for z in zs) or '— SIN ZONA'}")
        if not con_la_labor:
            cortes.append(f"ninguna cuadrilla activa tiene '{labor_pedida}' como "
                          f"labor habitual: las instalaciones sin barrio no se "
                          f"le cuentan a NINGUNA zona, y la demanda sale sin "
                          f"ellas")
        elif not zonas_de_la_labor:
            cortes.append(f"las cuadrillas de '{labor_pedida}' no tienen zona "
                          f"habitual activa: sin zona no reciben trabajo")

        # -- PUERTA 5: la demanda ------------------------------------------
        propuestas = adj.propuestas_en_despacho(org)
        demanda = adj.demanda_de_despacho(org, propuestas)
        w("")
        w("5 · LA DEMANDA DE DESPACHO")
        for clave in ("casos", "contados", "ya_despachados", "sin_barrio",
                      "instalaciones_sin_barrio", "sin_zona", "sin_labor",
                      "mismo_corte_de_red", "obras_sin_barrio",
                      "zonas_con_instalaciones_sin_barrio"):
            w(f"    {clave:<34} {demanda.get(clave, 0)}")
        nombres_zona = {str(z.id): z.nombre for z in ZonaOperativa.objects
                        .filter(org=org)}
        total_de_la_labor = 0
        w("    por zona:")
        for zona, labs in sorted(demanda["por_zona"].items(),
                                 key=lambda kv: nombres_zona.get(kv[0], kv[0])):
            total_de_la_labor += labs.get(labor_pedida, 0)
            detalle = ", ".join(f"{k}={v}" for k, v in sorted(labs.items()) if v)
            w(f"      {nombres_zona.get(zona, zona)[:28]:<28} {detalle or '—'}")
        w(f"    casos de '{labor_pedida}' en la demanda . {total_de_la_labor}")
        if not total_de_la_labor:
            cortes.append(f"la demanda no tiene NI UN caso de '{labor_pedida}': "
                          f"el Supervisor no tiene por que programarla. Mirar "
                          f"los contadores de arriba para saber donde se "
                          f"quedaron los casos")

        # -- PUERTA 6: lo que el plan asignaria -----------------------------
        w("")
        w("6 · LO QUE EL SUPERVISOR ASIGNARIA HOY  (en memoria, no escribe)")
        planes = ja.planear_el_dia(org, fecha, demanda=demanda["por_zona"])
        con_la_labor_hoy = 0
        for p in planes:
            marca = ""
            if p.labor == labor_pedida or p.labor_de_apoyo == labor_pedida:
                con_la_labor_hoy += 1
                marca = "  <<<"
            w(f"      {p.cuadrilla.nombre:<24} {p.accion}/{p.motivo:<22} "
              f"labor={p.labor or '—'} apoyo={p.labor_de_apoyo or '—'}{marca}")
        if not planes:
            cortes.append("`planear_el_dia` no devolvio ningun plan: no hay "
                          "cuadrillas que armar")
        elif not con_la_labor_hoy:
            cortes.append(f"ninguna cuadrilla saldria con '{labor_pedida}' hoy, "
                          f"ni como labor ni como apoyo")

        # -- EL VEREDICTO ---------------------------------------------------
        w("")
        w("=" * 78)
        if cortes:
            w(f" SE CORTA EN {len(cortes)} PUERTA(S):")
            for i, c in enumerate(cortes, 1):
                w(f"   {i}. {c}")
        else:
            w(f" NINGUNA PUERTA CERRADA: hoy saldrian {con_la_labor_hoy} "
              f"cuadrilla(s) con '{labor_pedida}'.")
            w(" Si en la pantalla no se ve, el problema esta DESPUES: en el")
            w(" reparto de las ordenes o en la publicacion del dia.")
        w("=" * 78)
