"""
================================================================================
 INFORME DE JORNADAS  --  17/10/2026
================================================================================
Lista, sin escribir nada, como se armaron las jornadas de cuadrilla en un rango
de dias y que se repite: con quien va cada persona, que zonas y que labor toma
cada cuadrilla, que dias trabaja, y cuanto se parece un dia al anterior.

POR QUE EXISTE
--------------
El usuario quiere que el Supervisor arme la jornada solo, segun el trabajo que
hay en Despacho, y antes de escribir la regla pidio ver como la arma hoy una
persona: "analiza bien esa ventana de cuadrilla y dime que se repite". El dato
esta en la pantalla de Cuadrillas ("Quien estuvo con quien"), una fila por
persona y por dia, pero sin contar.

QUE SACA, Y QUE NO
------------------
Nombres de la gente de campo, de las cuadrillas y de las zonas: es lo que hay
que ver para saber quien va con quien. Nada del cliente, y tampoco las notas
de la jornada, que son texto libre.

Uso, dentro del contenedor del backend (desde /app):
  python manage.py informe_de_jornadas --org <uuid> [--dias 60]
================================================================================
"""
from collections import Counter, defaultdict
from datetime import timedelta
from itertools import combinations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from campo.cuadrillas import JornadaDeCuadrilla, _nombre_de_cuenta
from campo.zonas import ZonaOperativa
from common.models import Org
from common.tasks import set_rls_context

#: El mismo tope que la pantalla ('cuadrillas_views.MAX_DIAS_DE_HISTORIAL'):
#: tres meses cubren el trimestre, que es como se mira una cuadrilla.
MAX_DIAS = 92
DIAS_POR_DEFECTO = 60
SEMANA = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")
#: Ancho maximo de una columna: lo que pasa se corta, para que la tabla se lea.
ANCHO = 70


def _top(contador, n=3) -> str:
    return ", ".join(f"{k} ({v})" for k, v in contador.most_common(n)) or "-"


def _gente(jornada) -> set:
    """Quienes fueron ese dia: los integrantes y el lider del dia, una vez cada uno."""
    integrantes = list(jornada.integrantes.all())
    nombres = {i.persona.nombre.strip() for i in integrantes
               if (i.persona.nombre or "").strip()}
    lider_id = jornada.lider_id
    if lider_id and not any(i.persona.profile_id == lider_id for i in integrantes):
        nombre = _nombre_de_cuenta(jornada.lider)
        if nombre:
            nombres.add(nombre)
    return nombres


def _zonas(jornada) -> set:
    return {z.nombre for z in jornada.zonas.all()}


class Command(BaseCommand):
    help = ("Como se armaron las jornadas de cuadrilla en un rango de dias, y que "
            "se repite. No escribe nada.")

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

        hasta = _ahora_local(org).date()
        desde = hasta - timedelta(days=dias - 1)
        jornadas = list(
            JornadaDeCuadrilla.objects
            .filter(org=org, fecha__range=(desde, hasta))
            .select_related("cuadrilla", "lider__user")
            .prefetch_related("zonas", "integrantes__persona")
            .order_by("fecha", "cuadrilla__nombre"))
        self.stdout.write(
            f"jornadas del {desde} al {hasta} ({dias} dias): {len(jornadas)} "
            f"jornadas en {len({j.fecha for j in jornadas})} dias")
        if not jornadas:
            self.stdout.write("no hay ninguna jornada armada en ese rango")
            return

        por_cuadrilla = defaultdict(list)
        for j in jornadas:
            por_cuadrilla[j.cuadrilla.nombre].append(j)

        self._cada_cuadrilla(por_cuadrilla)
        self._parejas(jornadas)
        self._repeticion(por_cuadrilla)
        self._semana(por_cuadrilla)
        self._zonas(org, jornadas)

    # -------------------------------------------------------------------------

    def _cada_cuadrilla(self, por_cuadrilla):
        self.stdout.write("\n1. CADA CUADRILLA: lo que mas toma (dias)")
        filas = []
        for nombre, js in sorted(por_cuadrilla.items()):
            filas.append((
                nombre, str(len(js)),
                _top(Counter(j.labor for j in js)),
                _top(Counter(z for j in js for z in _zonas(j))),
                _top(Counter(_nombre_de_cuenta(j.lider) or "-" for j in js), 2),
                _top(Counter(p for j in js for p in _gente(j)), 4),
                str(sum(1 for j in js if not _zonas(j))),
            ))
        self._tabla(("cuadrilla", "dias", "labor", "zonas", "lider del dia",
                     "gente", "sin zona"), filas)

    def _parejas(self, jornadas):
        self.stdout.write("\n2. QUIEN VA CON QUIEN: las parejas que mas se repiten (dias)")
        parejas = Counter()
        donde = defaultdict(Counter)
        for j in jornadas:
            for a, b in combinations(sorted(_gente(j)), 2):
                parejas[(a, b)] += 1
                donde[(a, b)][j.cuadrilla.nombre] += 1
        filas = [(f"{a} + {b}", str(n), _top(donde[(a, b)], 2))
                 for (a, b), n in parejas.most_common(20)]
        if not filas:
            self.stdout.write("ninguna jornada tuvo mas de una persona")
            return
        self._tabla(("pareja", "dias", "en que cuadrilla"), filas)

    def _repeticion(self, por_cuadrilla):
        self.stdout.write(
            "\n3. CUANTO SE REPITE EL DIA: cada dia trabajado contra el anterior")
        filas = []
        for nombre, js in sorted(por_cuadrilla.items()):
            js = sorted(js, key=lambda j: j.fecha)
            pares = list(zip(js, js[1:]))
            n = len(pares)
            if not n:
                filas.append((nombre, str(len(js)), "-", "-", "-"))
                continue
            filas.append((
                nombre, str(len(js)),
                f"{sum(_gente(a) == _gente(b) for a, b in pares)} de {n}",
                f"{sum(_zonas(a) == _zonas(b) for a, b in pares)} de {n}",
                f"{sum(a.labor == b.labor for a, b in pares)} de {n}",
            ))
        self._tabla(("cuadrilla", "dias", "misma gente", "mismas zonas",
                     "misma labor"), filas)

    def _semana(self, por_cuadrilla):
        self.stdout.write("\n4. QUE DIAS TRABAJA CADA CUADRILLA (jornadas)")
        filas = []
        for nombre, js in sorted(por_cuadrilla.items()):
            c = Counter(j.fecha.weekday() for j in js)
            filas.append((nombre, *(str(c.get(d, 0)) for d in range(7))))
        self._tabla(("cuadrilla", *SEMANA), filas)

    def _zonas(self, org, jornadas):
        self.stdout.write("\n5. CADA ZONA: cuantos dias la cubrio alguien, y quien")
        cubiertas = Counter()
        quienes = defaultdict(Counter)
        for j in jornadas:
            for z in _zonas(j):
                cubiertas[z] += 1
                quienes[z][j.cuadrilla.nombre] += 1
        filas = []
        for z in (ZonaOperativa.objects.filter(org=org, activa=True)
                  .prefetch_related("cuadrillas_habituales").order_by("nombre")):
            habituales = ", ".join(sorted(
                c.nombre for c in z.cuadrillas_habituales.all() if c.activa))
            filas.append((z.nombre, str(cubiertas.get(z.nombre, 0)),
                          _top(quienes[z.nombre], 3), habituales or "ninguna"))
        if not filas:
            self.stdout.write("no hay zonas activas")
            return
        self._tabla(("zona", "dias cubierta", "por quien",
                     "cuadrillas que la tienen habitual"), filas)

    def _tabla(self, cabecera, filas):
        anchos = [min(ANCHO, max(len(str(x)) for x in col))
                  for col in zip(cabecera, *filas)]

        def linea(fila):
            return "  ".join(str(x)[:a].ljust(a)
                             for x, a in zip(fila, anchos)).rstrip()

        self.stdout.write(linea(cabecera))
        self.stdout.write("-" * len(linea(cabecera)))
        for fila in filas:
            self.stdout.write(linea(fila))
