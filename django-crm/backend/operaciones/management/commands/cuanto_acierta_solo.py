# -*- coding: utf-8 -*-
"""
Cuánto acertaría el Supervisor si decidiera solo: la comparación en sombra.

    python manage.py cuanto_acierta_solo --org <id>
    python manage.py cuanto_acierta_solo --org <id> --dias 60

POR QUÉ EXISTE
--------------
El objetivo abierto es reemplazar a un supervisor humano por un agente
(`SPEC/objetivos/el-agente-sabe-cuando-no-sabe.md`), y la forma de medirlo la
eligió el usuario con estas palabras: *«en sombras: decide en paralelo al
humano y comparamos»*.

Eso ya está pasando y nadie lo está contando. El Supervisor propone, una
persona acepta / modifica / rechaza, y ese veredicto humano es exactamente la
etiqueta que hace falta:

    aceptada     el humano no le cambió nada  -> habría acertado solo
    modificada   tuvo que corregirlo          -> a medias
    rechazada    se equivocó

**Esa proporción es el número que decide cuándo soltarle autonomía**, y no una
sensación. Sin esto, «¿ya está listo?» no tiene respuesta.

LO QUE NO MIDE, Y HAY QUE DECIRLO
---------------------------------
Mide si el humano coincidió, no si el humano tenía razón. Un revisor que
acepta todo sin leer produce un 100% que no significa nada. Por eso además se
reporta **cuánto tarda la revisión**: un veredicto en menos de diez segundos
sobre una propuesta con evidencia es una señal de que nadie la leyó.

Y no mide lo que el Supervisor NO propuso. Un agente que calla sobre la mitad
de la operación puede tener 100% en lo que dice. Ese otro lado se mide con
`informe_de_pendientes`.

SIN DATOS DE CLIENTE. Solo conteos y tipos de señal: nunca el asunto, la
descripción, el nombre ni el teléfono. Es una salida pensada para pegarse en
una conversación.

EL CONTEXTO RLS SE FIJA ACÁ, como en los otros dos comandos de este
directorio: un comando no pasa por el middleware, y sin él las tablas
devuelven 0 filas **sin error** -- que es el peor resultado posible para algo
cuyo trabajo es contar.
"""

from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg, Count, F
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context
from operaciones.models import PropuestaSupervisor

#:  Por debajo de esto, un veredicto humano es sospechoso de no haber leído.
#:  No es un juicio sobre la persona: es que un número de aceptación alto
#:  construido con revisiones de cinco segundos no sirve para decidir nada.
SEGUNDOS_SOSPECHOSOS = 10


class Command(BaseCommand):
    help = "Cuánto coincidió el humano con el Supervisor, por tipo de señal."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")
        parser.add_argument("--dias", type=int, default=30)

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        set_rls_context(org.id)

        dias = options["dias"]
        desde = timezone.now() - timezone.timedelta(days=dias)

        #  SOLO LAS REVISADAS. Una propuesta que sigue en 'propuesta' no dice
        #  nada todavía: no es un acierto ni un error, es una pregunta sin
        #  contestar. Mezclarlas diluiría el número hacia abajo y haría
        #  parecer peor al agente cuanto más rápido propone.
        revisadas = (PropuestaSupervisor.objects
                     .filter(org=org, revisado_en__gte=desde,
                             estado__in=(PropuestaSupervisor.ACEPTADA,
                                         PropuestaSupervisor.MODIFICADA,
                                         PropuestaSupervisor.RECHAZADA)))

        total = revisadas.count()
        self.stdout.write("=" * 72)
        self.stdout.write(f"  CUÁNTO ACERTARÍA SOLO  --  últimos {dias} días")
        self.stdout.write("=" * 72)

        if not total:
            #  SE DICE, no se calla. «0 revisadas» y «el agente nunca acierta»
            #  son cosas distintas, y un cero sin explicación se lee como la
            #  segunda.
            self.stdout.write("")
            self.stdout.write("  Ninguna propuesta revisada en la ventana.")
            self.stdout.write("  Eso NO dice que el agente falle: dice que")
            self.stdout.write("  nadie revisó, o que no propuso nada.")
            self.stdout.write("  Mirá `informe_de_pendientes` para el otro lado.")
            return

        por_estado = Counter(revisadas.values_list("estado", flat=True))
        aceptadas = por_estado.get(PropuestaSupervisor.ACEPTADA, 0)
        modificadas = por_estado.get(PropuestaSupervisor.MODIFICADA, 0)
        rechazadas = por_estado.get(PropuestaSupervisor.RECHAZADA, 0)

        self.stdout.write("")
        self.stdout.write(f"  propuestas revisadas          {total:>6}")
        self.stdout.write(f"    aceptadas sin cambios       {aceptadas:>6}"
                          f"   ({100 * aceptadas / total:.0f}%)"
                          "  <- habría acertado solo")
        self.stdout.write(f"    modificadas                 {modificadas:>6}"
                          f"   ({100 * modificadas / total:.0f}%)")
        self.stdout.write(f"    rechazadas                  {rechazadas:>6}"
                          f"   ({100 * rechazadas / total:.0f}%)")

        #  POR TIPO DE SEÑAL, porque el agregado miente. Un agente que acierta
        #  el 95% en «caso abierto hace mucho» --que es contar días-- y el 40%
        #  en «necesita visita» --que decide si alguien maneja hasta una casa--
        #  da un promedio tranquilizador y una decisión pésima.
        self.stdout.write("")
        self.stdout.write("  POR TIPO DE SEÑAL  (el agregado miente):")
        por_tipo = (revisadas.values("tipo_senal")
                    .annotate(n=Count("id"))
                    .order_by("-n"))
        for fila in por_tipo:
            tipo = fila["tipo_senal"]
            n = fila["n"]
            ok = revisadas.filter(tipo_senal=tipo,
                                  estado=PropuestaSupervisor.ACEPTADA).count()
            self.stdout.write(f"     {tipo:<34} {ok:>4}/{n:<4}"
                              f" {100 * ok / n:>3.0f}% aceptadas")

        #  CUÁNTO TARDÓ LA REVISIÓN. El contrapeso del número de arriba: una
        #  aceptación en cinco segundos sobre una propuesta con evidencia no
        #  es un acuerdo, es un clic.
        con_tiempo = revisadas.exclude(created_at=None).exclude(revisado_en=None)
        medias = con_tiempo.aggregate(
            media=Avg(F("revisado_en") - F("created_at")))["media"]
        rapidas = 0
        for p in con_tiempo.only("created_at", "revisado_en"):
            if (p.revisado_en - p.created_at).total_seconds() < SEGUNDOS_SOSPECHOSOS:
                rapidas += 1

        self.stdout.write("")
        self.stdout.write("  ¿LEYERON, O SOLO CLIQUEARON?")
        if medias is not None:
            self.stdout.write(f"     tiempo medio hasta el veredicto   {medias}")
        self.stdout.write(f"     revisadas en menos de {SEGUNDOS_SOSPECHOSOS}s"
                          f"        {rapidas:>4} de {con_tiempo.count()}")
        if rapidas and con_tiempo.count():
            pct = 100 * rapidas / con_tiempo.count()
            if pct > 30:
                self.stdout.write(
                    f"     AVISO: el {pct:.0f}% se decidió en segundos. El"
                    " porcentaje de aceptación de arriba")
                self.stdout.write(
                    "     mide coincidencia, no criterio -- con revisiones así"
                    " no alcanza para soltar autonomía.")

        self.stdout.write("")
        self.stdout.write("  Lo que esto NO mide: si el humano tenía razón, ni")
        self.stdout.write("  lo que el Supervisor NO propuso (ver"
                          " informe_de_pendientes).")
        self.stdout.write("=" * 72)
