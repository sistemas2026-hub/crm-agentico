# -*- coding: utf-8 -*-
"""
Cuenta, o retira, las propuestas pendientes del Supervisor NOC sobre tickets
de otras áreas.

    python manage.py propuestas_fuera_de_area --org <id> --contar   # mide
    python manage.py propuestas_fuera_de_area --org <id>            # retira

POR QUÉ EXISTE, si el ciclo ya lo hace
--------------------------------------
'correr_ciclo' retira estas propuestas a las :07 y con el botón "Correr
ciclo", pero una corrida entera cuesta varios minutos y llamadas al modelo.
Esto hace solo el retiro, y sobre todo CUENTA sin escribir: es la evidencia
que se pega antes y después de un deploy ("fuera de área: 0"), con ids y
números, nunca con el asunto ni la descripción del ticket.

EL CONTEXTO RLS SE FIJA ACÁ
---------------------------
Un comando no pasa por el middleware: sin 'app.current_org', 'Case' y
'PropuestaSupervisor' devuelven 0 filas sin ningún error, y un cero así
diría "no hay ajenos" cuando lo que pasa es que no se miró nada. No se
limpia al salir: el proceso termina con el comando.

FAIL-CLOSED: sin el mapa de áreas del motor no se cuenta ni se retira nada,
y el comando sale con error para que no se confunda con un cero.
"""

from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context
from operaciones import areas_del_tenant as areas
from operaciones import supervisor
from operaciones.models import PropuestaSupervisor


class Command(BaseCommand):
    help = (
        "Cuenta o retira las propuestas pendientes del Supervisor NOC sobre "
        "tickets de otras áreas"
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument(
            "--contar",
            action="store_true",
            help="solo contar: no escribe nada",
        )

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")

        set_rls_context(org.id)

        criterio = areas.criterio_de_area()
        if not criterio.se_sabe:
            raise CommandError(
                "No se pudo leer el mapa de áreas del motor: no se cuenta ni "
                "se retira nada."
            )

        pendientes = list(
            supervisor.propuestas_retirables_por_area(org).only(
                "id", "origen_id", "tipo_senal"
            )
        )
        ajenos = supervisor.areas_de_los_ajenos(
            org, {p.origen_id for p in pendientes}, criterio
        )
        fuera = [p for p in pendientes if p.origen_id in ajenos]
        propios = supervisor.propios_entre(
            org, {p.origen_id for p in pendientes}, criterio
        )
        no_se_sabe = [
            p
            for p in pendientes
            if p.origen_id not in ajenos and p.origen_id not in propios
        ]

        self.stdout.write(f"org: {org.id}")
        self.stdout.write(f"pendientes sobre tickets: {len(pendientes)}")
        self.stdout.write(f"fuera de área: {len(fuera)}")
        for area, n in sorted(Counter(ajenos[p.origen_id] for p in fuera).items()):
            self.stdout.write(f"  {area}: {n}")
        for p in fuera:
            self.stdout.write(
                f"  propuesta {p.id} · caso {p.origen_id} · {p.tipo_senal} · "
                f"{ajenos[p.origen_id]}"
            )
        #  Lo que NO se sabe tampoco se retira, y hay que decirlo: un caso sin
        #  area escrita, sin nadie o con alguien que el motor no conoce, sigue
        #  en Pendientes aunque "fuera de area" diga 0.
        self.stdout.write(
            f"pendientes sobre casos cuya área no se sabe: {len(no_se_sabe)} "
            "(no se retiran: sin dato no se adivina)"
        )

        #  LO QUE NO SE RETIRA, DICHO: las propuestas de cierre sobre tickets
        #  de otras areas siguen en Pendientes por decision del 16/10/2026.
        #  Sin esta linea, "fuera de area: 0" se leeria como "Pendientes solo
        #  tiene soporte y operativo", y no es eso.
        cierres = list(
            PropuestaSupervisor.objects.filter(
                org=org,
                estado=PropuestaSupervisor.PROPUESTA,
                origen_tipo="case",
                tipo_senal=PropuestaSupervisor.CASO_DESINCRONIZADO,
            ).only("id", "origen_id")
        )
        cierres_ajenos = supervisor.areas_de_los_ajenos(
            org, {p.origen_id for p in cierres}, criterio
        )
        self.stdout.write(
            "pendientes de cierre sobre otras áreas: "
            f"{sum(1 for p in cierres if p.origen_id in cierres_ajenos)} "
            "(no se retiran: decisión del 16/10/2026)"
        )

        if options["contar"]:
            return

        retiradas = supervisor.retirar_propuestas_fuera_de_area(org, timezone.now())
        self.stdout.write(f"retiradas: {retiradas}")
