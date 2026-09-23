# -*- coding: utf-8 -*-
"""
================================================================================
 DATOS DE PRUEBA DE CAMPO  --  solo desarrollo, y solo sobre una org que existe
================================================================================

POR QUE ESTE COMANDO TIENE CANDADOS
-----------------------------------
Corrió contra producción. El 08/09/2026 sembró en la base real una
organización entera ("Rapilink Telecomunicaciones"), un usuario técnico con
una contraseña que estaba escrita en este archivo, una plantilla FTTH y la
orden 1842 -- y ese tenant de juguete sigue ahí, con la única operación de
campo que existe, mientras los 237 casos reales viven en otra organización.
Nadie lo hizo con mala intención: el comando no tenía forma de negarse.

Los tres candados salen de las tres cosas que lo hicieron posible:

  1. 'get_or_create(name=...)' CREABA UN TENANT. Ejecutarlo en un entorno donde
     ese nombre no existía daba de alta una empresa nueva, en silencio. Ahora
     la organización se recibe por '--org <uuid>' y tiene que existir: este
     comando ya no puede crear ninguna.

  2. NO SABÍA DÓNDE ESTABA CORRIENDO. Ahora se niega si 'DEBUG' está apagado,
     que es la definición de "esto no es mi máquina".

  3. LA CONTRASEÑA ESTABA EN EL REPOSITORIO. Cualquiera que leyera el código
     podía entrar a la app móvil. Ahora se genera al azar y se imprime una sola
     vez, o se pasa por '--password' para una corrida reproducible.

Y una cuarta, que no es candado sino cortesía: a un usuario que YA existe no se
le toca la contraseña. Antes se la reescribía en cada corrida.

USO EN DESARROLLO
-----------------
    python manage.py seed_campo_demo --org 8a0a07ac-...        # clave al azar
    python manage.py seed_campo_demo --org 8a0a07ac-... --password local12345

'--org' sale de la organización de desarrollo que ya tengas sembrada
('seed_data' crea una). Si no existe, el comando lo dice y no crea nada.
================================================================================
"""

import secrets
import uuid as uuid_lib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Org, Profile, User

EMAIL_TECNICO_POR_DEFECTO = "carlos.tecnico@demo.local"


class Command(BaseCommand):
    help = (
        "Siembra datos de prueba para la app movil de campo. SOLO en desarrollo "
        "(DEBUG=True) y sobre una organizacion que ya exista (--org)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--org", required=True,
            help="UUID de una organizacion EXISTENTE. El comando no crea ninguna.")
        parser.add_argument(
            "--email", default=EMAIL_TECNICO_POR_DEFECTO,
            help=f"Correo del tecnico de prueba (por defecto {EMAIL_TECNICO_POR_DEFECTO}).")
        parser.add_argument(
            "--password", default=None,
            help=("Contrasena para el tecnico NUEVO. Sin este argumento se "
                  "genera al azar y se imprime una sola vez. A un usuario que "
                  "ya existe no se le cambia nunca."))

    def handle(self, *args, **options):
        #  CANDADO 1: el entorno.
        #  Va primero y antes de mirar nada: si esto es produccion, la respuesta
        #  es no, sin importar que argumentos vengan.
        if not settings.DEBUG:
            raise CommandError(
                "seed_campo_demo NO corre con DEBUG=False. Este comando siembra "
                "datos de demostracion y ya ensucio una base real una vez "
                "(08/09/2026). Si de verdad hacen falta datos en este entorno, "
                "se crean por la API, con su bitacora."
            )

        #  CANDADO 2: la organizacion existe, o no hay nada que hacer.
        #  Se busca por ID y nunca por nombre: 'get_or_create(name=...)' es
        #  exactamente lo que dio de alta un tenant sin que nadie lo pidiera.
        try:
            org_id = uuid_lib.UUID(str(options["org"]))
        except (ValueError, AttributeError, TypeError):
            raise CommandError(f"--org debe ser un UUID. Recibi: {options['org']!r}")

        org = Org.objects.filter(id=org_id).first()
        if org is None:
            raise CommandError(
                f"No existe ninguna organizacion con id {org_id}. Este comando "
                f"NO crea organizaciones: pasa el id de una que ya exista "
                f"(las de desarrollo las siembra 'seed_data')."
            )

        self.stdout.write(f"Sembrando datos de campo en '{org.name}' ({org.id})...")

        email_tecnico = options["email"]
        user = User.objects.filter(email=email_tecnico).first()
        clave_nueva = None
        if user is None:
            #  CANDADO 3: ninguna contrasena vive en este archivo.
            clave_nueva = options["password"] or secrets.token_urlsafe(16)
            user = User.objects.create_user(email=email_tecnico, password=clave_nueva)
            user.name = "Carlos Gomez (demo)"
            user.is_active = True
            user.save()
        elif options["password"]:
            #  Cambiar la clave de una cuenta que ya existe es una decision de
            #  seguridad, no un efecto de sembrar datos. Se avisa y no se hace.
            self.stdout.write(self.style.WARNING(
                f"  '{email_tecnico}' ya existe: NO se le cambio la contrasena."))

        profile, _ = Profile.objects.get_or_create(
            user=user, org=org,
            defaults={"role": "USER", "is_active": True},
        )

        work_type, _ = WorkType.objects.get_or_create(
            org=org, codigo="ftth_instalacion",
            defaults={"nombre": "Instalacion Fibra Optica (FTTH)", "activo": True},
        )

        esquema_ftth = {
            "pasos": [
                {"id": "paso_1", "titulo": "Parametros de Fibra y ONT"},
                {"id": "paso_2", "titulo": "Inspeccion Visual y Evidencias"},
            ],
            "campos": [
                {
                    "id": "serial_ont",
                    "titulo": "Numero de Serie ONT",
                    "tipo": "texto",
                    "reglas": {"required": True, "min": 5},
                    "ayuda": "Ejemplo: ZTEG12345678 o ALCL87654321",
                },
                {
                    "id": "potencia_rx",
                    "titulo": "Potencia Optica RX (dBm)",
                    "tipo": "decimal",
                    "reglas": {"required": True, "min": -28.0, "max": -8.0},
                    "ayuda": "Rango optimo: entre -28.0 y -8.0 dBm",
                },
            ],
            "evidencias": [
                {
                    "id": "foto_ont",
                    "titulo": "Fotografia ONT Instalada",
                    "tipo": "foto",
                    "obligatorio": True,
                    "instrucciones": "Foto nitida de la fijacion, roseta y latiguillo.",
                },
                {
                    "id": "foto_fachada",
                    "titulo": "Fotografia Fachada del Domicilio",
                    "tipo": "foto",
                    "obligatorio": False,
                    "instrucciones": "Foto exterior con la nomenclatura visible.",
                },
            ],
        }

        version, _ = WorkTypeVersion.objects.get_or_create(
            work_type=work_type, version=1,
            defaults={
                "schema_version": 1,
                "estado": WorkTypeVersion.PUBLICADA,
                "esquema": esquema_ftth,
            },
        )

        #  El numero es el consecutivo de la organizacion, no una constante: en
        #  una base de desarrollo con ordenes ya sembradas, un 1842 fijo choca
        #  contra unique(org, numero).
        ultimo = (OrdenTrabajo.objects.filter(org=org)
                  .order_by("-numero").values_list("numero", flat=True).first())
        orden = OrdenTrabajo.objects.create(
            org=org,
            numero=(ultimo or 0) + 1,
            tipo_trabajo_version=version,
            #  'demo' y no 'wisphub': el origen dice de donde salio el dato, y
            #  estas ordenes no salieron de ningun ticket. Las tres que quedaron
            #  en produccion dicen 'wisphub' y por eso costo rastrearlas.
            origen_sistema="demo",
            origen_tipo="seed",
            origen_ref=f"DEMO-{secrets.token_hex(4)}",
            cliente_nombre="Cliente de prueba",
            cliente_telefono="+57 300 000 0000",
            cliente_direccion="Calle falsa 123",
            gps_lat=6.2087,
            gps_lng=-75.5678,
            diagnostico_previo={
                "resumen": "Datos de DEMOSTRACION. No corresponden a ningun cliente real.",
                "nap_sugerida": "NAP-0000",
            },
            estado_operativo=OrdenTrabajo.ASIGNADA,
            revision=1,
        )

        AsignacionTrabajo.objects.get_or_create(
            orden=orden, profile=profile,
            defaults={"rol": "tecnico_lider", "es_principal": True},
        )

        self.stdout.write(self.style.SUCCESS("[OK] Datos de prueba sembrados:"))
        self.stdout.write(f"  Organizacion : {org.name} ({org.id})")
        self.stdout.write(f"  Tecnico      : {user.email}")
        self.stdout.write(f"  Orden        : #{orden.numero} ({orden.id})")
        self.stdout.write(f"  Plantilla    : {work_type.nombre} (schema v{version.schema_version})")
        if clave_nueva:
            #  Unica vez que se ve. No queda en el repositorio ni en la base en
            #  claro -- si se pierde, se restablece como cualquier otra cuenta.
            self.stdout.write(self.style.WARNING(
                f"  Contrasena (se muestra UNA vez): {clave_nueva}"))
