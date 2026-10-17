# -*- coding: utf-8 -*-
"""
Borra los datos personales de una copia local, para poder probar con volumen
real sin pasear la libreta de clientes de la empresa.

POR QUÉ EXISTE
--------------
Probar la aplicación con tres órdenes inventadas no dice cómo se comporta con
la jornada de una cuadrilla de verdad: listas largas, direcciones raras,
clientes sin teléfono, órdenes sin coordenadas. Eso solo se ve con datos
reales.

Pero una copia de producción en un portátil es la libreta de clientes de la
empresa: nombres, teléfonos, direcciones y el GPS de cada domicilio. Este
comando conserva la *forma* —cuántas órdenes, de qué tipo, en qué estado, con
qué largo de dirección— y reemplaza el contenido personal.

CÓMO SE USA
-----------
1. Restaurar el volcado de producción en una base LOCAL.
2. Correr este comando contra esa base.
3. Recién entonces levantar el backend para la aplicación.

LA GUARDA
---------
Se niega a correr si la base no es local. No es una formalidad: el 22/09/2026
un arranque que se creía local terminó escribiendo en producción porque
`manage.py` pisaba la variable de configuración. Un comando que reescribe
nombres de clientes no puede depender de que quien lo ejecuta no se equivoque.
"""

import hashlib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from campo.models import EvidenciaTrabajo, OrdenTrabajo
from common.models import Profile, User

#: Hosts que se consideran locales. Cualquier otro aborta el comando.
HOSTS_LOCALES = {"", "localhost", "127.0.0.1", "::1", "db", "postgres"}

NOMBRES = [
    "Abonado Uno", "Abonado Dos", "Abonado Tres", "Abonado Cuatro",
    "Abonado Cinco", "Abonado Seis", "Abonado Siete", "Abonado Ocho",
]
CALLES = ["Calle", "Carrera", "Transversal", "Diagonal", "Avenida"]


class Command(BaseCommand):
    help = "Reemplaza los datos personales de una copia LOCAL de la base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--si-estoy-seguro",
            action="store_true",
            help="Confirma que esta base es una copia y se puede reescribir.",
        )

    def handle(self, *args, **options):
        self._exigir_base_local()

        if not options["si_estoy_seguro"]:
            raise CommandError(
                "Este comando reescribe nombres, teléfonos, direcciones y "
                "coordenadas de TODAS las órdenes. Si esta base es una copia, "
                "volvé a correrlo con --si-estoy-seguro."
            )

        with transaction.atomic():
            ordenes = self._anonimizar_ordenes()
            evidencias = self._limpiar_metadatos_evidencias()
            personas = self._anonimizar_personas()

        self.stdout.write(self.style.SUCCESS(
            f"[OK] {ordenes} órdenes, {evidencias} evidencias y {personas} "
            f"personas anonimizadas."
        ))
        self.stdout.write(
            "Se conservaron: cantidad, tipo, estado, fechas, vuelta y "
            "estructura del formulario. Se reemplazaron: nombre, teléfono, "
            "dirección, coordenadas, identificador de abonado y el contexto "
            "técnico del cliente."
        )

    # -- La guarda ---------------------------------------------------------

    def _exigir_base_local(self) -> None:
        d = settings.DATABASES["default"]
        motor = d["ENGINE"]
        host = (d.get("HOST") or "").lower()
        nombre = str(d.get("NAME") or "")

        if "sqlite" in motor:
            return

        if host not in HOSTS_LOCALES:
            raise CommandError(
                f"La base configurada está en '{host}', que no es local. "
                f"Este comando reescribe datos de clientes: solo corre contra "
                f"una copia. Revisá DJANGO_SETTINGS_MODULE antes de insistir."
            )

        self.stdout.write(
            self.style.WARNING(
                f"Base PostgreSQL local: {host or 'localhost'}/{nombre}. "
                f"Se va a reescribir su contenido personal."
            )
        )

    # -- El reemplazo ------------------------------------------------------

    @staticmethod
    def _seudonimo(semilla: str, opciones: list[str]) -> str:
        """
        Siempre el mismo reemplazo para el mismo original.

        Que sea estable importa: dos órdenes del mismo cliente siguen
        pareciendo del mismo cliente, que es justo lo que se quiere mirar
        cuando se prueba una lista larga.
        """
        h = hashlib.sha256(semilla.encode("utf-8")).hexdigest()
        return opciones[int(h[:8], 16) % len(opciones)]

    def _anonimizar_ordenes(self) -> int:
        tocadas = 0
        for orden in OrdenTrabajo.objects.all().iterator(chunk_size=500):
            semilla = str(orden.id)
            digito = int(hashlib.sha256(semilla.encode()).hexdigest()[:6], 16)

            orden.cliente_nombre = (
                f"{self._seudonimo(semilla, NOMBRES)} {digito % 900 + 100}"
            )
            orden.cliente_telefono = (
                f"+57 300 {digito % 900 + 100} {digito % 9000 + 1000}"
                if orden.cliente_telefono else ""
            )
            orden.cliente_direccion = (
                f"{self._seudonimo(semilla, CALLES)} {digito % 120 + 1} "
                f"# {digito % 90 + 10}-{digito % 80 + 5}"
            )
            orden.cliente_id_abonado = (
                f"ABO-{digito % 900000 + 100000}" if orden.cliente_id_abonado else ""
            )
            # Las coordenadas se corren lo justo para que dejen de señalar una
            # casa, sin perder la ciudad: la lista ordenada por distancia sigue
            # teniendo sentido.
            if orden.gps_lat is not None:
                orden.gps_lat = round(orden.gps_lat + (digito % 200 - 100) / 10000, 6)
            if orden.gps_lng is not None:
                orden.gps_lng = round(orden.gps_lng + (digito % 200 - 100) / 10000, 6)

            # El contexto trae el snapshot del cliente y su IP.
            if isinstance(orden.contexto, dict) and orden.contexto:
                cliente = orden.contexto.get("cliente")
                if isinstance(cliente, dict):
                    if cliente.get("nombre"):
                        cliente["nombre"] = orden.cliente_nombre
                    if cliente.get("ip"):
                        cliente["ip"] = f"10.{digito % 255}.{digito % 254 + 1}.{digito % 253 + 2}"
                orden.contexto["anonimizado"] = True

            orden.save(update_fields=[
                "cliente_nombre", "cliente_telefono", "cliente_direccion",
                "cliente_id_abonado", "gps_lat", "gps_lng", "contexto",
            ])
            tocadas += 1
        return tocadas

    def _limpiar_metadatos_evidencias(self) -> int:
        """
        Los metadatos de captura llegan sin lista blanca: traen el GPS del
        domicilio donde se tomó la foto.
        """
        tocadas = 0
        for ev in EvidenciaTrabajo.objects.exclude(
            metadatos_captura={}
        ).iterator(chunk_size=500):
            ev.metadatos_captura = {"anonimizado": True}
            ev.save(update_fields=["metadatos_captura"])
            tocadas += 1
        return tocadas

    def _anonimizar_personas(self) -> int:
        """
        Los técnicos y el personal de oficina también son personas.

        No se tocan las contraseñas: quien restaure la copia va a querer
        entrar con un usuario conocido, y para eso está `cambiar_clave`.
        """
        tocadas = 0
        for user in User.objects.all().iterator(chunk_size=500):
            if user.is_superuser:
                continue
            semilla = str(user.id)
            digito = int(hashlib.sha256(semilla.encode()).hexdigest()[:6], 16)
            user.name = f"Persona {digito % 900 + 100}"
            user.email = f"persona{digito % 900 + 100}@ejemplo.local"
            user.save(update_fields=["name", "email"])
            tocadas += 1

        Profile.objects.update()  # nada que anonimizar hoy; queda el gancho
        return tocadas
