# -*- coding: utf-8 -*-
"""Siembra datos de prueba para la app movil de campo.

EL INCIDENTE QUE ORDENA ESTE ARCHIVO
------------------------------------
El 08/09/2026 este comando sembro en la base de PRODUCCION una organizacion
completa, un tecnico con contrasena publicada en el repositorio y la orden
1842. Nadie se salto ningun control: **el comando no tenia ninguno**. Y las
tres ordenes decian `origen_sistema = "wisphub"`, asi que parecian tickets
reales y por eso costo rastrearlas.

Las cuatro cosas que lo hacian posible, y como quedan cerradas:

1. **Corria en cualquier entorno.** Ahora lo primero que hace es comprobar
   `settings.DEBUG`, antes de mirar un solo argumento: no hay combinacion de
   parametros que lo pase.
2. **Se inventaba la empresa** con `get_or_create(name=...)`. Ahora `--org` es
   obligatorio, tiene que ser un UUID y tiene que existir. **Este comando NO
   crea organizaciones**, ni en desarrollo.
3. **Pisaba la contrasena** del tecnico en cada corrida con una clave que
   estaba en el repositorio. Ahora a un usuario que ya existe **no se le toca
   la clave** --sembrar datos no es una operacion de seguridad-- y el usuario
   nuevo nace con una clave aleatoria, salvo que se pida otra con
   `--password`.
4. **Los numeros eran fijos** (1842, 1843, 1844) y el origen decia `wisphub`.
   Ahora el numero sale del consecutivo de la empresa --el mismo
   `siguiente_numero` que usa el despacho real-- y el origen dice `demo`, con
   un resumen que lo anuncia en el primer renglon.

POR QUE UNA SOLA ORDEN POR DEFECTO
-----------------------------------
Sembraba tres de una, y eso hacia imposible afirmar cuantas habia sembrado una
corrida: dos corridas dejaban seis ordenes y ninguna prueba podia distinguir
"sembro de mas" de "sembro dos veces". Por defecto siembra **una**; los tres
casos de la aplicacion --la que esta en sitio y la devuelta por el supervisor--
siguen disponibles con `--completo`.

QUE NO COMPRUEBA, Y HAY QUE SABERLO
------------------------------------
`settings.DEBUG` dice en que entorno se CREE que corre, no contra que base
apunta. Un entorno de desarrollo mal configurado, con `DEBUG=True` y la URL de
produccion, pasa esta guarda. Lo que la hace valer es que el servidor corre con
`DEBUG=False`: ahi el comando no arranca.

Para esa otra mitad --contra QUE BASE se escribe-- el comando hermano
`seed_campo_carga` tiene la guarda mas fuerte del modulo: `--si-la-base-es`
exige que quien corre escriba el nombre de la base, y sin eso solo informa. Si
hace falta sembrar contra una base remota de desarrollo, ese es el camino.
Aca no se copia porque no se puede ejercitar: las pruebas corren contra el
Postgres del laboratorio, que no es local, asi que una guarda de host las
dejaria a todas en rojo -- y un mecanismo que ninguna prueba puede tocar es
justo lo que §6 llama «una prueba que dice que algo existe no prueba que
funcione».
"""

import secrets
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from campo.models import (
    AsignacionTrabajo, EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion,
)
from campo.services.despacho import siguiente_numero
from common.models import Org, Profile, User

#: El tecnico de ejemplo. `demo.local` y no un dominio que exista: un correo de
#: prueba en un dominio real puede recibir de verdad el dia que alguien conecte
#: el envio.
EMAIL_POR_DEFECTO = "carlos.tecnico@demo.local"


class Command(BaseCommand):
    help = (
        "Siembra datos de prueba de Campo sobre una organizacion EXISTENTE. "
        "Solo corre con DEBUG=True."
    )

    def add_arguments(self, parser):
        # `required=True` es la PRIMERA de dos redes, no la unica: quitarlo
        # no abre el camino, porque un `--org` vacio tampoco pasa la validacion
        # de UUID de `_organizacion_de`. Medido con dos mutaciones (quitar el
        # required, y quitar la validacion de UUID): las dos dejan las 15 en
        # verde porque el EFECTO --el comando se niega-- lo sostiene la otra.
        # Se dejan las dos a proposito; lo que no hay que concluir es que una
        # sobra.
        parser.add_argument(
            "--org",
            required=True,
            help="UUID de la organizacion EXISTENTE donde sembrar. "
                 "Este comando no crea organizaciones.",
        )
        parser.add_argument(
            "--email",
            default=EMAIL_POR_DEFECTO,
            help=f"Correo del tecnico de prueba (por defecto {EMAIL_POR_DEFECTO}).",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Clave para el usuario NUEVO. Sin esto se genera una al azar. "
                 "A un usuario que ya existe no se le cambia la clave.",
        )
        parser.add_argument(
            "--completo",
            action="store_true",
            help="Siembra tambien la orden en sitio y la devuelta por el "
                 "supervisor, para ejercitar esos dos casos en la aplicacion.",
        )

    def handle(self, *args, **opciones):
        # -------------------------------------------------------------- #
        # §1  EL ENTORNO, ANTES QUE NADA
        # -------------------------------------------------------------- #
        # Va primero a proposito: si la comprobacion viviera despues de validar
        # argumentos, un `--org` mal escrito daria un mensaje sobre el UUID y
        # alguien lo corregiria y volveria a intentar -- contra produccion.
        if not settings.DEBUG:
            raise CommandError(
                "Este comando siembra datos de prueba y corre con DEBUG=False: "
                "se niega. El 08/09/2026 sembro una organizacion, un tecnico y "
                "tres ordenes en la base de produccion. Si hace falta poblar un "
                "entorno real, se hace por el despacho, que deja auditoria."
            )

        org = self._organizacion_de(opciones["org"])
        email = (opciones["email"] or EMAIL_POR_DEFECTO).strip()

        # Todo o nada. Un comando que levanta DESPUES de escribir la mitad
        # seria igual de malo que no levantar: deja la base en un estado que
        # nadie pidio y que no se parece ni al antes ni al despues.
        with transaction.atomic():
            user, clave_nueva = self._tecnico(email, opciones["password"])
            profile, _ = Profile.objects.get_or_create(
                user=user,
                org=org,
                defaults={"role": "USER", "is_active": True},
            )
            version = self._plantilla_ftth(org)
            orden = self._orden_de_instalacion(org, version, profile)
            extras = (
                self._ordenes_extra(org, profile)
                if opciones["completo"]
                else []
            )

        self._contar_lo_hecho(org, user, clave_nueva, orden, extras)

    # ------------------------------------------------------------------ #
    # §2  La organizacion: se recibe, no se inventa
    # ------------------------------------------------------------------ #

    def _organizacion_de(self, crudo: str) -> Org:
        """La empresa donde sembrar. **No la crea.**

        Es el defecto exacto que ensucio produccion: un `get_or_create` por
        nombre daba de alta "Rapilink Telecomunicaciones" en cuanto el nombre
        no coincidia byte a byte con una existente.
        """
        try:
            org_id = uuid.UUID(str(crudo))
        except (ValueError, AttributeError, TypeError):
            raise CommandError(
                f"--org tiene que ser un UUID y llego «{crudo}». "
                "Se identifica por id y no por nombre: dos empresas pueden "
                "llamarse parecido, y buscar por nombre fue lo que creo una "
                "organizacion que nadie pidio."
            )

        org = Org.objects.filter(id=org_id).first()
        if org is None:
            raise CommandError(
                f"No existe la organizacion {org_id}, y este comando NO crea "
                "organizaciones. Dar de alta una empresa es una decision de "
                "negocio, no un efecto de sembrar datos de prueba."
            )
        return org

    # ------------------------------------------------------------------ #
    # §3  La contrasena
    # ------------------------------------------------------------------ #

    def _tecnico(self, email: str, clave_pedida):
        """El usuario de prueba. Devuelve `(user, clave_para_mostrar)`.

        A UN USUARIO QUE YA EXISTE NO SE LE TOCA LA CLAVE, y tampoco con
        `--password`. Sembrar datos no es una operacion de seguridad: antes
        cada corrida reescribia la contrasena del tecnico, asi que correr el
        seed le cerraba la sesion a alguien que estaba trabajando -- y con una
        clave que estaba publicada en el repositorio.
        """
        existente = User.objects.filter(email=email).first()
        if existente is not None:
            return existente, None

        # Al azar y no una fija: una clave en el codigo es una credencial
        # publicada en cuanto el repositorio se comparte, y este archivo ya
        # tuvo una. Se imprime una vez, al final, para poder usarla.
        clave = clave_pedida or secrets.token_urlsafe(12)
        user = User.objects.create_user(email=email, password=clave)
        user.name = "Carlos Gomez (demo)"
        user.is_active = True
        user.save(update_fields=["name", "is_active"])
        return user, clave

    # ------------------------------------------------------------------ #
    # §4  La plantilla y las ordenes
    # ------------------------------------------------------------------ #

    def _plantilla_ftth(self, org) -> WorkTypeVersion:
        work_type, _ = WorkType.objects.get_or_create(
            org=org,
            codigo="ftth_instalacion",
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
                    "instrucciones": "Foto nitida donde se aprecie la fijacion, "
                                     "roseta y latiguillo de fibra.",
                },
                {
                    "id": "foto_fachada",
                    "titulo": "Fotografia Fachada del Domicilio",
                    "tipo": "foto",
                    "obligatorio": False,
                    "instrucciones": "Foto exterior con placa visible de la "
                                     "nomenclatura.",
                },
            ],
        }
        version, _ = WorkTypeVersion.objects.get_or_create(
            work_type=work_type,
            version=1,
            defaults={
                "schema_version": 1,
                "estado": WorkTypeVersion.PUBLICADA,
                "esquema": esquema_ftth,
            },
        )
        return version

    def _orden_de_instalacion(self, org, version, profile) -> OrdenTrabajo:
        """La orden asignada al tecnico.

        EL NUMERO SALE DEL CONSECUTIVO, no de un 1842 fijo. Con el numero fijo,
        la segunda corrida encontraba la fila con `get_or_create` y no sembraba
        nada -- y en produccion ese 1842 se mezclo con la numeracion real.
        """
        numero = siguiente_numero(org)
        orden = OrdenTrabajo.objects.create(
            org=org,
            numero=numero,
            tipo_trabajo_version=version,
            # `demo` y NO `wisphub`: las tres de produccion decian wisphub y por
            # eso parecian tickets reales. Una orden de prueba tiene que decir
            # que lo es, en el dato y no solo en la intencion de quien la creo.
            origen_sistema="demo",
            origen_tipo="orden_manual",
            # Unico por corrida: `demo` no esta en la excepcion de
            # `unique_origen_externo_por_org`, asi que un ref fijo haria que la
            # segunda corrida choque contra la restriccion.
            origen_ref=f"DEMO-{numero}",
            cliente_nombre="Maria Fernandez (demo)",
            cliente_telefono="+57 300 000 0000",
            cliente_direccion="Cra. 48 # 12-30, Apto 402 (direccion de prueba)",
            gps_lat=6.2087,
            gps_lng=-75.5678,
            diagnostico_previo={
                # En el primer renglon y en mayusculas: es lo que ve quien abre
                # la orden sin saber de donde salio.
                "resumen": "DEMOSTRACION — datos de prueba, no es un trabajo "
                           "real. Fibra desplegada hasta la caja NAP-1042.",
                "nap_sugerida": "NAP-1042",
                "puerto_sugerido": 17,
            },
            contexto={
                "contexto_disponible": True,
                "capturado_en": "2026-09-22T07:00:00Z",
                "fuente": "demo",
                "cliente": {
                    "nombre": "Maria Fernandez (demo)",
                    "estado": "activo",
                    "plan": "Fibra 500 Mbps Simetrica",
                },
                "sn_onu": "ZTEG-48A9B0C1",
            },
            estado_operativo=OrdenTrabajo.ASIGNADA,
            revision=1,
        )
        AsignacionTrabajo.objects.get_or_create(
            orden=orden,
            profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )
        return orden

    def _ordenes_extra(self, org, profile) -> list:
        """La que esta en sitio y la devuelta por el supervisor.

        Solo con `--completo`. Son los dos casos que la aplicacion no podia
        mostrar hasta el 22/09/2026 y conviene poder abrirlos; pero sembrarlos
        siempre hacia imposible contar cuantas ordenes dejaba una corrida.
        """
        version = self._plantilla_correctivo(org)
        hechas = []

        numero = siguiente_numero(org)
        en_sitio = OrdenTrabajo.objects.create(
            org=org,
            numero=numero,
            tipo_trabajo_version=version,
            origen_sistema="demo",
            origen_tipo="orden_manual",
            origen_ref=f"DEMO-{numero}",
            cliente_nombre="Carlos Gomez (demo)",
            cliente_telefono="+57 300 000 0001",
            cliente_direccion="Cl. 45 #12-88 (direccion de prueba)",
            gps_lat=6.2451,
            gps_lng=-75.5812,
            diagnostico_previo={
                "resumen": "DEMOSTRACION — datos de prueba. Luz LOS "
                           "parpadeando, perdida intermitente.",
            },
            contexto={
                "contexto_disponible": True,
                "capturado_en": "2026-09-22T08:10:00Z",
                "fuente": "demo",
                # El `cliente` con su `plan` no es relleno: una orden que
                # declara `contexto_disponible` y no lo trae deja la pantalla
                # del cliente mostrando un plan de ejemplo, que es peor que no
                # mostrar nada. Lo exige `test_3_las_ordenes_traen_el_contexto`.
                "cliente": {
                    "nombre": "Carlos Gomez (demo)",
                    "estado": "activo",
                    "plan": "Fibra 300 Mbps",
                },
                "sn_onu": "48575443-A9B0C1",
            },
            estado_operativo=OrdenTrabajo.EN_SITIO,
            revision=1,
        )
        AsignacionTrabajo.objects.get_or_create(
            orden=en_sitio, profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )
        hechas.append(en_sitio)

        numero = siguiente_numero(org)
        devuelta = OrdenTrabajo.objects.create(
            org=org,
            numero=numero,
            tipo_trabajo_version=version,
            origen_sistema="demo",
            origen_tipo="orden_manual",
            origen_ref=f"DEMO-{numero}",
            cliente_nombre="Talleres Unidos (demo)",
            cliente_telefono="+57 300 000 0002",
            cliente_direccion="Zona Industrial Cra 50 #18-04 (prueba)",
            diagnostico_previo={
                "resumen": "DEMOSTRACION — datos de prueba. Devuelta por el "
                           "supervisor para rehacer la medicion.",
            },
            estado_operativo=OrdenTrabajo.CORRECCION_REQUERIDA,
            estado_validacion=OrdenTrabajo.REQUIERE_CORRECCION,
            vuelta=2,
            revision=3,
        )
        AsignacionTrabajo.objects.get_or_create(
            orden=devuelta, profile=profile,
            defaults={"rol": "tecnico", "es_principal": True},
        )
        # La devolucion vive en la bitacora, que es de donde la lee el
        # serializador. Sembrarla en una columna no probaria nada.
        EventoTrabajo.objects.create(
            org=org,
            orden=devuelta,
            tipo="correccion_requerida",
            profile=profile,
            datos={
                "vuelta_anterior": 1,
                "vuelta_nueva": 2,
                "requisitos_a_corregir": ["foto_potencia"],
                "observacion": "La medicion no coincide con la lectura de la OLT.",
            },
        )
        hechas.append(devuelta)
        return hechas

    def _plantilla_correctivo(self, org) -> WorkTypeVersion:
        work_type, _ = WorkType.objects.get_or_create(
            org=org,
            codigo="ftth_correctivo",
            defaults={"nombre": "Reparacion de Senal (FTTH)", "activo": True},
        )
        version, _ = WorkTypeVersion.objects.get_or_create(
            work_type=work_type,
            version=1,
            defaults={
                "schema_version": 1,
                "estado": WorkTypeVersion.PUBLICADA,
                "esquema": {
                    "pasos": [
                        {"id": "paso_1", "titulo": "Diagnostico en sitio"},
                    ],
                    "campos": [
                        {
                            "id": "potencia_rx",
                            "titulo": "Potencia Optica RX (dBm)",
                            "tipo": "decimal",
                            "reglas": {"required": True, "min": -28.0, "max": -8.0},
                        },
                    ],
                    "evidencias": [
                        {
                            "id": "foto_potencia",
                            "titulo": "Fotografia de la medicion",
                            "tipo": "foto",
                            "obligatorio": True,
                            "instrucciones": "Pantalla del medidor con la "
                                             "lectura legible.",
                        },
                    ],
                },
            },
        )
        return version

    # ------------------------------------------------------------------ #
    # §5  Lo que se informa
    # ------------------------------------------------------------------ #

    def _contar_lo_hecho(self, org, user, clave_nueva, orden, extras):
        self.stdout.write(self.style.SUCCESS("[OK] Datos de DEMOSTRACION sembrados:"))
        self.stdout.write(f"  Organizacion: {org.name} ({org.id})")
        self.stdout.write(f"  Tecnico:      {user.email}")
        if clave_nueva:
            self.stdout.write(
                f"  Clave NUEVA:  {clave_nueva}   <- anotala, no se vuelve a mostrar"
            )
        else:
            self.stdout.write(
                "  Clave:        sin cambios (el usuario ya existia y no se toca)"
            )
        self.stdout.write(f"  Orden:        #{orden.numero} ({orden.id})")
        for extra in extras:
            self.stdout.write(
                f"  Orden extra:  #{extra.numero} ({extra.estado_operativo})"
            )
        if not extras:
            # SE DICE, porque con una sola orden la mitad de las pantallas queda
            # sin nada que mostrar y eso no se distingue de «la aplicacion esta
            # rota». Quien siembra para mirar la app tiene que enterarse aca, no
            # despues de abrirla y dudar.
            self.stdout.write(
                "  Con una sola orden no se ven la lista, los filtros ni el "
                "caso de la orden devuelta: agrega --completo."
            )
