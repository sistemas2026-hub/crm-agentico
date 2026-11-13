# -*- coding: utf-8 -*-
"""Siembra N ordenes para un tecnico, para medir arranque y scroll con una
jornada cargada (contrato de version candidata, seccion 5).

NO es el sembrador de demostracion. `seed_campo_demo` arma la linea base --
organizacion, tecnico, tipos de trabajo y sus esquemas-- y este NO vuelve a
crear nada de eso: exige que ya exista y falla si no. Un esquema de formulario
declarado en dos lugares es exactamente el defecto que aparecio cinco veces en
esta aplicacion.

La guarda de entorno no es ceremonia. El tecnico se identifica por correo, y
un correo del dominio real de la empresa existe en produccion: sin confirmar
contra que base se escribe, veinte ordenes de prueba terminan en el CRM que
usan los operadores. El repositorio lo prohibe ('no crear mocks productivos').
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from common.models import Profile, User
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkTypeVersion


CALLES = [
    "Cl. 45 #12-88", "Cra. 50 #18-04", "Cl. 9 Sur #33-21", "Cra. 80 #32-15",
    "Cl. 104 #45-12", "Cra. 43A #7-50", "Cl. 30 #65-11", "Cra. 65 #98-33",
    "Cl. 77 #14-09", "Cra. 27 #52-40",
]
BARRIOS = [
    "San Jose", "La Floresta", "Belen", "Robledo", "Laureles",
    "El Poblado", "Aranjuez", "Buenos Aires", "Castilla", "Manrique",
]


class Command(BaseCommand):
    help = (
        "Siembra N ordenes asignadas a un tecnico para medir rendimiento. "
        "Exige confirmar el entorno."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tecnico", required=True,
            help="Correo del usuario tecnico al que se asignan las ordenes.",
        )
        parser.add_argument(
            "--ordenes", type=int, default=20,
            help="Cuantas ordenes crear (por defecto 20).",
        )
        parser.add_argument(
            "--si-la-base-es", default=None,
            help=(
                "Nombre de la base contra la que aceptas escribir. Tiene que "
                "coincidir con la que la conexion resuelve, o no se escribe "
                "nada. Sin este argumento el comando solo informa."
            ),
        )
        parser.add_argument(
            "--borrar", action="store_true",
            help="Borra las ordenes sembradas por este comando y termina.",
        )

    def handle(self, *args, **opciones):
        base = connection.settings_dict.get("NAME")
        host = connection.settings_dict.get("HOST") or "(local)"
        usuario_db = connection.settings_dict.get("USER")

        self.stdout.write("")
        self.stdout.write(f"  base     {base}")
        self.stdout.write(f"  host     {host}")
        self.stdout.write(f"  usuario  {usuario_db}")
        self.stdout.write(f"  DEBUG    {settings.DEBUG}")
        self.stdout.write("")

        confirmada = opciones["si_la_base_es"]
        if not confirmada:
            raise CommandError(
                "No se escribio nada. Mira las tres lineas de arriba y, si es "
                "el entorno correcto, repeti el comando agregando:\n\n"
                f"    --si-la-base-es {base}\n"
            )
        if confirmada != base:
            raise CommandError(
                f"No se escribio nada. Confirmaste '{confirmada}' y la conexion "
                f"resuelve '{base}'. No son la misma base."
            )

        tecnico = opciones["tecnico"]
        try:
            user = User.objects.get(email=tecnico)
        except User.DoesNotExist:
            raise CommandError(
                f"No existe ningun usuario con el correo '{tecnico}' en esta "
                f"base. Es la senal de que estas apuntando al entorno "
                f"equivocado, o de que falta crearlo."
            )

        perfil = Profile.objects.filter(user=user, is_active=True).first()
        if perfil is None:
            raise CommandError(
                f"'{tecnico}' existe pero no tiene perfil activo en ninguna "
                f"organizacion. Sin organizacion no hay donde colgar la orden."
            )
        org = perfil.org

        if opciones["borrar"]:
            borradas, _ = OrdenTrabajo.objects.filter(
                org=org, origen_sistema="manual", origen_ref__startswith="CARGA-",
            ).delete()
            self.stdout.write(self.style.SUCCESS(
                f"Borradas {borradas} filas sembradas por este comando."
            ))
            return

        version = (
            WorkTypeVersion.objects.filter(work_type__org=org)
            .order_by("-id").first()
        )
        if version is None:
            raise CommandError(
                "Esta organizacion no tiene ningun tipo de trabajo publicado. "
                "Corre primero 'seed_campo_demo': el esquema del formulario se "
                "declara en un solo lugar y este comando no lo duplica."
            )

        cuantas = opciones["ordenes"]
        ultimo = (
            OrdenTrabajo.objects.filter(org=org)
            .order_by("-numero").values_list("numero", flat=True).first()
        ) or 0

        creadas = 0
        with transaction.atomic():
            for i in range(cuantas):
                numero = ultimo + 1 + i
                orden, nueva = OrdenTrabajo.objects.get_or_create(
                    org=org,
                    numero=numero,
                    defaults={
                        "tipo_trabajo_version": version,
                        "origen_sistema": "manual",
                        "origen_tipo": "carga",
                        "origen_ref": f"CARGA-{numero}",
                        "cliente_nombre": f"Cliente de carga {i + 1:02d}",
                        "cliente_telefono": f"+57 300 000 {i + 1:04d}",
                        "cliente_direccion": (
                            f"{CALLES[i % len(CALLES)]}, {BARRIOS[i % len(BARRIOS)]}"
                        ),
                        "gps_lat": 6.2442 + (i * 0.0012),
                        "gps_lng": -75.5812 - (i * 0.0009),
                        "estado_operativo": OrdenTrabajo.ASIGNADA,
                        "revision": 1,
                    },
                )
                if nueva:
                    creadas += 1
                AsignacionTrabajo.objects.get_or_create(
                    orden=orden,
                    profile=perfil,
                    defaults={"rol": "tecnico", "es_principal": True},
                )

        self.stdout.write(self.style.SUCCESS(
            f"{creadas} ordenes nuevas (de {cuantas} pedidas) para {tecnico} "
            f"en '{org.name}'. Las que ya existian no se tocaron."
        ))
        self.stdout.write(
            f"Para deshacer:  manage.py seed_campo_carga --tecnico {tecnico} "
            f"--si-la-base-es {base} --borrar"
        )
