# -*- coding: utf-8 -*-
"""Comando para sembrar datos de prueba de Campo para la aplicación móvil Flutter."""

from django.core.management.base import BaseCommand
from common.models import Org, Profile, User
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


class Command(BaseCommand):
    help = "Siembra datos de prueba para la app móvil de campo (Rapilink, técnico Carlos y orden de instalación)."

    def handle(self, *args, **options):
        self.stdout.write("Sembrando datos de prueba para app de campo...")

        # 1. Crear Organización
        org, _ = Org.objects.get_or_create(
            name="Rapilink Telecomunicaciones",
            defaults={"is_active": True},
        )

        # 2. Crear Usuario Técnico
        email_tecnico = "carlos.tecnico@rapilink.com"
        user, created = User.objects.get_or_create(
            email=email_tecnico,
            defaults={"name": "Carlos Gómez", "is_active": True},
        )
        if created or not user.check_password("campo12345"):
            user.set_password("campo12345")
            user.name = "Carlos Gómez"
            user.save()

        # 3. Crear Perfil de Técnico en la Organización
        profile, _ = Profile.objects.get_or_create(
            user=user,
            org=org,
            defaults={"role": "USER", "is_active": True},
        )

        # 4. Crear Tipo de Trabajo (FTTH)
        work_type, _ = WorkType.objects.get_or_create(
            org=org,
            codigo="ftth_instalacion",
            defaults={"nombre": "Instalación Fibra Óptica (FTTH)", "activo": True},
        )

        # 5. Crear Versión Publicada con Schema v1 (2 campos dinámicos y 2 evidencias)
        esquema_ftth = {
            "pasos": [
                {"id": "paso_1", "titulo": "Parámetros de Fibra y ONT"},
                {"id": "paso_2", "titulo": "Inspección Visual y Evidencias"},
            ],
            "campos": [
                {
                    "id": "serial_ont",
                    "titulo": "Número de Serie ONT",
                    "tipo": "texto",
                    "reglas": {"required": True, "min": 5},
                    "ayuda": "Ejemplo: ZTEG12345678 o ALCL87654321",
                },
                {
                    "id": "potencia_rx",
                    "titulo": "Potencia Óptica RX (dBm)",
                    "tipo": "decimal",
                    "reglas": {"required": True, "min": -28.0, "max": -8.0},
                    "ayuda": "Rango óptimo para Rapilink: entre -28.0 y -8.0 dBm",
                },
            ],
            "evidencias": [
                {
                    "id": "foto_ont",
                    "titulo": "Fotografía ONT Instalada",
                    "tipo": "foto",
                    "obligatorio": True,
                    "instrucciones": "Foto nítida donde se aprecie la fijación, roseta y latiguillo de fibra.",
                },
                {
                    "id": "foto_fachada",
                    "titulo": "Fotografía Fachada del Domicilio",
                    "tipo": "foto",
                    "obligatorio": False,
                    "instrucciones": "Foto exterior con placa visible de la nomenclatura.",
                },
            ],
        }

        version, v_created = WorkTypeVersion.objects.get_or_create(
            work_type=work_type,
            version=1,
            defaults={
                "schema_version": 1,
                "estado": WorkTypeVersion.PUBLICADA,
                "esquema": esquema_ftth,
            },
        )

        # 6. Crear Orden de Trabajo Asignada a Carlos
        orden, _ = OrdenTrabajo.objects.get_or_create(
            org=org,
            numero=1842,
            defaults={
                "tipo_trabajo_version": version,
                "origen_sistema": "wisphub",
                "origen_tipo": "ticket",
                "origen_ref": "WH-91288",
                "cliente_nombre": "María Fernández",
                "cliente_telefono": "+57 300 999 8877",
                "cliente_direccion": "Cra. 48 # 12-30, Apto 402",
                "gps_lat": 6.2087,
                "gps_lng": -75.5678,
                "diagnostico_previo": {
                    "resumen": "Cliente nuevo. Fibra desplegada hasta caja NAP-1042 en poste frontal.",
                    "nap_sugerida": "NAP-1042",
                    "puerto_sugerido": 17,
                    "notas": "Hay perro en el patio. Timbre número 402.",
                },
                "estado_operativo": OrdenTrabajo.ASIGNADA,
                "revision": 1,
            },
        )

        # 7. Asignar como técnico principal de la cuadrilla
        AsignacionTrabajo.objects.get_or_create(
            orden=orden,
            profile=profile,
            defaults={"rol": "tecnico_lider", "es_principal": True},
        )

        self.stdout.write(self.style.SUCCESS("[OK] Datos de prueba sembrados exitosamente:"))
        self.stdout.write(f"  Organizacion: {org.name} (ID: {org.id})")
        self.stdout.write(f"  Usuario Tecnico: {user.email} (Password: campo12345)")
        self.stdout.write(f"  Perfil: {profile.id}")
        self.stdout.write(f"  Orden de Trabajo: #{orden.numero} ({orden.id})")
        self.stdout.write(f"  Tipo: {work_type.nombre} (Schema v{version.schema_version})")
