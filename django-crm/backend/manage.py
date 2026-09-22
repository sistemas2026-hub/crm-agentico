#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    # `setdefault` y no una asignacion: la linea de abajo estuvo hasta el
    # 22/09/2026 pisando la variable del entorno, asi que
    # `DJANGO_SETTINGS_MODULE=... manage.py migrate` corria igual contra la
    # configuracion de produccion mientras quien lo ejecutaba creia estar en
    # local. Es una trampa silenciosa: el comando no falla, escribe donde no
    # se espera.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            pass

        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            ) from exc
        raise
    execute_from_command_line(sys.argv)
