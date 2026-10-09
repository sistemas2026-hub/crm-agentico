# -*- coding: utf-8 -*-
"""
Comprueba que la credencial de base de datos es la que corresponde al proposito.

    python manage.py verificar_credenciales --proposito trafico
    python manage.py verificar_credenciales --proposito migraciones
    python manage.py verificar_credenciales --proposito trafico --con-base

Sale con codigo 1 si encuentra un problema de gravedad ERROR. Eso es lo que hace
que 'docker/backend/entrypoint.sh' -que corre con 'set -e'- no siga adelante.

La logica vive en common/credenciales.py, sin Django y sin conexion, para que se
pueda probar sin levantar nada. Aca solo esta la envoltura.
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection

from common import credenciales


class Command(BaseCommand):
    help = ("Verifica que DBUSER/MIGRATOR_DBUSER/MOTOR_DBUSER correspondan al "
            "proposito de este proceso (trafico o migraciones)")

    def add_arguments(self, parser):
        parser.add_argument(
            "--proposito", required=True, choices=list(credenciales.PROPOSITOS),
            help="para que se va a usar esta conexion")
        parser.add_argument(
            "--con-base", action="store_true",
            help="ademas de las variables, comprueba contra la base (rol "
                 "efectivo, frontera con 'asistente', propiedad de tablas)")

    def handle(self, *args, **opciones):
        proposito = opciones["proposito"]

        problemas = credenciales.revisar_entorno(dict(os.environ), proposito)

        if opciones["con_base"]:
            # Si las variables ya estan mal, conectar no aporta nada y puede
            # colgarse. Se comprueba lo barato primero.
            if not credenciales.hay_que_abortar(problemas):
                try:
                    with connection.cursor() as cur:
                        problemas += credenciales.revisar_base(cur, proposito)
                except Exception as e:
                    # No poder comprobar no es lo mismo que estar bien, y
                    # tampoco es motivo para tumbar el arranque: la conexion
                    # real la prueba el propio 'migrate' un segundo despues.
                    self.stderr.write(self.style.WARNING(
                        f"  no se pudo comprobar contra la base: "
                        f"{type(e).__name__}: {str(e)[:120]}"))

        texto = credenciales.formatear(problemas, proposito)

        if credenciales.hay_que_abortar(problemas):
            self.stderr.write(self.style.ERROR(texto))
            raise SystemExit(1)

        if problemas:
            self.stderr.write(self.style.WARNING(texto))
        else:
            self.stdout.write(self.style.SUCCESS(texto))
