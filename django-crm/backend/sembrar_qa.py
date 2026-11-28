"""Siembra una organizacion y un usuario de PRUEBA para el QA visual.

    python3 sembrar_qa.py

SOLO para entornos desechables. Se niega a correr si la base parece de
produccion: crear un usuario con contrasena conocida en produccion seria
exactamente el agujero que este QA existe para no abrir.

Todo lo que crea lleva 'QA' en el nombre y un correo @qa.local, para que sea
imposible confundirlo con datos reales.
"""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from common.models import Org, Profile  # noqa: E402

BASE = os.environ.get("DBNAME", "")
PROHIBIDAS = ("prod", "produccion", "postgres", "wisphub", "rapilink")
if any(p in BASE.lower() for p in PROHIBIDAS) or not BASE.startswith("qa_"):
    print(f"[ABORTADO] la base '{BASE}' no parece desechable. "
          f"Se exige un nombre que empiece con 'qa_'.")
    sys.exit(1)

CORREO = "ana.qa@qa.local"
CLAVE = os.environ.get("QA_PASSWORD")
if not CLAVE:
    print("[ABORTADO] falta QA_PASSWORD en el entorno.")
    sys.exit(1)

User = get_user_model()

org, creada = Org.objects.get_or_create(
    name="QA BANDEJA (datos de prueba)",
    defaults={"is_active": True},
)
print(f"org {'creada' if creada else 'ya existia'}: {org.id}")

usuario, creado = User.objects.get_or_create(
    email=CORREO,
    defaults={"is_active": True},
)
usuario.set_password(CLAVE)
usuario.is_active = True
usuario.save()
print(f"usuario {'creado' if creado else 'actualizado'}: {usuario.id} {usuario.email}")

perfil, _ = Profile.objects.get_or_create(
    user=usuario, org=org,
    defaults={"role": "ADMIN", "is_active": True},
)
perfil.role = "ADMIN"
perfil.is_active = True
perfil.save()
print(f"perfil: {perfil.id} role={perfil.role}")

print(f"\nORG_ID={org.id}")
print(f"USER_ID={usuario.id}")
