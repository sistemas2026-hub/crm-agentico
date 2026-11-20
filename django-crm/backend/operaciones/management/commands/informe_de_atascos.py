"""
Lo que el Supervisor no pudo decidir en los últimos días, por clase y por tipo.
No escribe nada.

    python manage.py informe_de_atascos --org <id> [--dias 14]

POR QUÉ EXISTE
--------------
Pregunta del usuario el 29/10/2026, antes de decidir si un agente de IA
resuelve lo que las reglas no saben: «¿eso mejora al Supervisor en qué rango
de fallar?». No había un número. Esto lo da: cuántos días se trabó cada cosa,
cuántas cosas distintas, y de qué clase (la regla no sabe decidir, no alcanza
lo que hay, la IA no contestó, una puerta de la empresa…). Las cuentas las
hace el código (`operaciones/atascos.informe`), no quien lee.

«Cosas» son sujetos distintos: una orden, una cuadrilla, una labor, una
propuesta. «Vueltas» son cuántas corridas del ciclo lo vieron.

SIN DATOS DEL CLIENTE: lo anotado son ids y textos fijos del código. Se puede
pegar en una conversación.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context


class Command(BaseCommand):
    help = "Lo que el Supervisor no pudo decidir, por clase y por tipo. No escribe."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--dias", type=int, default=14,
                            help="cuántos días hacia atrás, contando hoy (14)")

    def handle(self, *args, **options):
        from campo.reparto import _zona_de
        from operaciones import atascos

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        if options["dias"] < 1:
            raise CommandError("--dias tiene que ser 1 o más.")
        set_rls_context(org.id)

        hasta = timezone.now().astimezone(_zona_de(org)).date()
        desde = hasta - dt.timedelta(days=options["dias"] - 1)
        r = atascos.informe(org, desde, hasta)

        self.stdout.write(f"Atascos del Supervisor · {desde:%d/%m/%Y} a {hasta:%d/%m/%Y} · "
                          f"{r['dias_con_atascos']} de {options['dias']} días con atascos")
        if not r["por_tipo"]:
            self.stdout.write("Nada anotado en esos días.")
            return

        self.stdout.write("")
        self.stdout.write(f"{'POR CLASE':<44}{'días':>6}{'cosas':>7}{'vueltas':>9}")
        for c in r["por_clase"]:
            self.stdout.write(f"{c['que_es']:<44}{c['dias']:>6}{c['sujetos']:>7}"
                              f"{c['veces']:>9}")

        self.stdout.write("")
        self.stdout.write("POR TIPO")
        for t in r["por_tipo"]:
            self.stdout.write(f"[{t['clase']}] {t['fase']} · {t['tipo']} · {t['motivo'] or t['que_es']}")
            self.stdout.write(f"    días {t['dias']} · cosas {t['sujetos']} · vueltas {t['veces']}")
