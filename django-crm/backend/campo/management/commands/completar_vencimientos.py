"""
Le pone su vencimiento a las órdenes vivas que el Supervisor creó antes del
29/10/2026 y no lo tienen. Sin `--aplicar`, solo dice qué haría.

    python manage.py completar_vencimientos --org <id>            # simulacro
    python manage.py completar_vencimientos --org <id> --aplicar

POR QUÉ EXISTE
--------------
Las órdenes que crea el Supervisor nunca guardaban `sla_vence_en`: la app no
podía ordenar por «lo que vence antes» y Programación no tenía fecha que
mostrar. Desde el 29/10/2026 se guarda al crear la orden
(`operaciones.ordenes_de_despacho.vencimiento_del_caso`: el día del ticket más
el plazo del nivel de su asunto). Esto lo hace con LA MISMA función para las
que ya estaban.

SOLO las vivas (asignadas, en camino, en sitio, a corregir, detenidas), solo
las que nacieron de un caso y solo las que no tienen vencimiento: una fecha que
alguien escribió no se pisa. Sin plazo (ni del nivel ni de la plantilla) se
deja vacía y se dice.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common.models import Org
from common.tasks import set_rls_context


class Command(BaseCommand):
    help = "Completa el vencimiento de las órdenes vivas del Supervisor que no lo tienen."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--aplicar", action="store_true",
                            help="escribir (sin esto, solo dice qué haría)")

    def handle(self, *args, **options):
        from campo import niveles as N
        from campo.dia_publicado import _activas
        from campo.models import OrdenTrabajo
        from campo.reparto import _zona_de
        from cases.models import Case
        from operaciones.ordenes_de_despacho import vencimiento_del_caso

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        set_rls_context(org.id)
        zona = _zona_de(org)
        nivel_de = N.lector_de_niveles(org)

        ordenes = list(OrdenTrabajo.objects
                       .filter(org=org, estado_operativo__in=_activas(),
                               sla_vence_en__isnull=True, origen_tipo="case")
                       .select_related("tipo_trabajo_version__work_type")
                       .order_by("numero"))
        casos = {str(c.id): c for c in Case.objects.filter(
            org=org, id__in=[o.origen_ref for o in ordenes if o.origen_ref])}

        cambian, sin = [], []
        for o in ordenes:
            caso = casos.get(str(o.origen_ref))
            tipo = getattr(o.tipo_trabajo_version, "work_type", None)
            vence = vencimiento_del_caso(
                getattr(caso, "created_at", None),
                nivel=nivel_de(caso.name or "") if caso else None,
                plazo_de_la_plantilla=getattr(tipo, "plazo_dias", None), zona=zona)
            if vence is None:
                sin.append(o.numero)
                continue
            o.sla_vence_en = vence
            cambian.append(o)
            self.stdout.write(f"  OT-{o.numero}: vence {vence:%d/%m/%Y}")

        if options["aplicar"] and cambian:
            with transaction.atomic():
                OrdenTrabajo.objects.bulk_update(cambian, ["sla_vence_en"])
        verbo = "Se completaron" if options["aplicar"] else "Se completarían"
        self.stdout.write(f"{verbo} {len(cambian)} de {len(ordenes)} órdenes sin vencimiento.")
        if sin:
            self.stdout.write("Sin plazo que contar (quedan vacías): "
                              + ", ".join(f"OT-{n}" for n in sin))
        if not options["aplicar"] and cambian:
            self.stdout.write("Es un simulacro: para escribir, repetí con --aplicar.")
