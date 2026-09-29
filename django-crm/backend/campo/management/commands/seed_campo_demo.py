# -*- coding: utf-8 -*-
"""Comando para sembrar datos de prueba de Campo para la aplicación móvil Flutter."""

from django.core.management.base import BaseCommand
from common.models import Org, Profile, User
from campo.models import (
    AsignacionTrabajo, EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion,
)


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
                "contexto": {
                    "contexto_disponible": True,
                    "capturado_en": "2026-09-22T07:00:00Z",
                    "fuente": "motor",
                    "cliente": {
                        "nombre": "María Fernández",
                        "estado": "activo",
                        "plan": "Fibra 500 Mbps Simétrica",
                        "ip": "10.42.18.77",
                    },
                    "sn_onu": "ZTEG-48A9B0C1",
                },
                "estado_operativo": OrdenTrabajo.ASIGNADA,
                "revision": 1,
            },
        )

        # 7. Asignar como técnico principal de la cuadrilla
        AsignacionTrabajo.objects.get_or_create(
            orden=orden,
            profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )

        # 8. Un correctivo, con su propia plantilla y sus propios pasos. Sirve
        #    para ver que el protocolo de atención cambia con el tipo de
        #    trabajo, porque sale de la plantilla y no de la aplicación.
        work_type_correctivo, _ = WorkType.objects.get_or_create(
            org=org,
            codigo="ftth_correctivo",
            defaults={"nombre": "Reparación de Señal (FTTH)", "activo": True},
        )
        version_correctivo, _ = WorkTypeVersion.objects.get_or_create(
            work_type=work_type_correctivo,
            version=1,
            defaults={
                "schema_version": 1,
                "estado": WorkTypeVersion.PUBLICADA,
                "esquema": {
                    "pasos": [
                        {"id": "p1", "titulo": "Notificación de llegada al inmueble"},
                        {"id": "p2", "titulo": "Inspección de acometida y roseta"},
                        {"id": "p3", "titulo": "Medición óptica con power meter"},
                        {"id": "p4", "titulo": "Reconectorización o fusión"},
                        {"id": "p5", "titulo": "Prueba de servicio y cierre"},
                    ],
                    "campos": [
                        {
                            "id": "estado_luces",
                            "titulo": "Estado de luces físicas en la ONT",
                            "tipo": "seleccion",
                            "reglas": {
                                "required": True,
                                "options": ["Online", "Offline", "Intermitente"],
                            },
                        },
                        {
                            "id": "requiere_cambio",
                            "titulo": "¿Requiere cambio de conector o equipo?",
                            "tipo": "booleano",
                            "ayuda": "Sustitución física en sitio",
                        },
                        {
                            "id": "potencia_rx",
                            "titulo": "Nueva medición en campo",
                            "tipo": "decimal",
                            "reglas": {"required": True, "min": -30.0, "max": -5.0},
                            "ayuda": "Umbral de aceptación: -15 a -25 dBm",
                        },
                    ],
                    "evidencias": [
                        {
                            "id": "foto_cto",
                            "titulo": "Fotografía de la caja CTO",
                            "tipo": "foto",
                            "obligatorio": True,
                            "instrucciones": "Que se vea el puerto y la etiqueta.",
                        },
                        {
                            "id": "foto_potencia",
                            "titulo": "Fotografía de la medición",
                            "tipo": "foto",
                            "obligatorio": True,
                            "instrucciones": "Pantalla del medidor con la lectura legible.",
                        },
                    ],
                },
            },
        )

        correctivo, correctivo_nuevo = OrdenTrabajo.objects.get_or_create(
            org=org,
            numero=1843,
            defaults={
                "tipo_trabajo_version": version_correctivo,
                "origen_sistema": "wisphub",
                "origen_tipo": "ticket",
                "origen_ref": "WH-91301",
                "cliente_nombre": "Carlos Gómez",
                "cliente_telefono": "+57 312 455 8901",
                "cliente_direccion": "Cl. 45 #12-88, Barrio San José",
                "gps_lat": 6.2451,
                "gps_lng": -75.5812,
                "contexto": {
                    "contexto_disponible": True,
                    "capturado_en": "2026-09-22T08:10:00Z",
                    "fuente": "motor",
                    "cliente": {
                        "nombre": "Carlos Gómez",
                        "estado": "activo",
                        "plan": "Fibra 300 Mbps",
                    },
                    "sn_onu": "48575443-A9B0C1",
                },
                "diagnostico_previo": {
                    "resumen": "Luz LOS parpadeando en rojo, pérdida intermitente desde anoche.",
                },
                "estado_operativo": OrdenTrabajo.EN_SITIO,
                "revision": 1,
            },
        )
        AsignacionTrabajo.objects.get_or_create(
            orden=correctivo,
            profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )

        # 9. Una orden devuelta por el supervisor. Es el caso que la aplicación
        #    no podía mostrar hasta el 22/09/2026: el técnico la recibía sin
        #    saber qué rehacer.
        devuelta, devuelta_nueva = OrdenTrabajo.objects.get_or_create(
            org=org,
            numero=1844,
            defaults={
                "tipo_trabajo_version": version_correctivo,
                "origen_sistema": "crm",
                "origen_tipo": "case",
                "origen_ref": "CASE-5521",
                "cliente_nombre": "Talleres Unidos S.A.S",
                "cliente_telefono": "+57 604 444 1122",
                "cliente_direccion": "Zona Industrial Cra 50 #18-04",
                "estado_operativo": OrdenTrabajo.CORRECCION_REQUERIDA,
                "estado_validacion": OrdenTrabajo.REQUIERE_CORRECCION,
                "vuelta": 2,
                "revision": 3,
            },
        )
        AsignacionTrabajo.objects.get_or_create(
            orden=devuelta,
            profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )
        if devuelta_nueva:
            # La devolución vive en la bitácora, que es de donde la lee el
            # serializador. Sembrarla en una columna no probaría nada.
            EventoTrabajo.objects.create(
                org=org,
                orden=devuelta,
                tipo="correccion_requerida",
                profile=profile,
                datos={
                    "vuelta_anterior": 1,
                    "vuelta_nueva": 2,
                    "requisitos_a_corregir": ["foto_potencia"],
                    "observacion": "La medición no coincide con la lectura de la OLT.",
                },
            )

        self.stdout.write(self.style.SUCCESS("[OK] Datos de prueba sembrados exitosamente:"))
        self.stdout.write(f"  Organizacion: {org.name} (ID: {org.id})")
        self.stdout.write(f"  Usuario Tecnico: {user.email} (Password: campo12345)")
        self.stdout.write(f"  Perfil: {profile.id}")
        self.stdout.write(f"  Orden de Trabajo: #{orden.numero} ({orden.id})")
        self.stdout.write(f"  Tipo: {work_type.nombre} (Schema v{version.schema_version})")
        self.stdout.write(f"  Orden en sitio: #{correctivo.numero} ({correctivo.id})")
        self.stdout.write(
            f"  Orden devuelta: #{devuelta.numero} — el tecnico ve que rehacer"
        )
