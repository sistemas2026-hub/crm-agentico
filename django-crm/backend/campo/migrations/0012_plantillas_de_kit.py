# -*- coding: utf-8 -*-
"""
Las plantillas de kit: la lista de materiales que se repite todas las mañanas.

Escrita a mano y no con `makemigrations` porque el motor de Docker de esta
maquina no levantaba en ese momento (el servicio de Windows estaba detenido y
arrancarlo pide permisos de administrador). Se copio la forma exacta de
`Proveedor` en 0010, que es un modelo equivalente --`BaseModel` + org + unique
por organizacion-- para no inventar los campos heredados.

VERIFICAR ANTES DE DARLA POR BUENA:

    python manage.py makemigrations campo --check --dry-run

Si Django no propone ninguna migracion nueva, este archivo describe los modelos
tal como estan. Si propone una, manda la que propone Django.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        # `common` no se declara: llega por la cadena --0011 depende de 0010, y
        # esa ya exige `common.0041`--. Fijar aca una version de common seria
        # atar el grafo a un numero que no tiene por que ser este.
        ("campo", "0011_direccion_de_los_movimientos_historicos"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlantillaDeKit",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.CharField(blank=True, default="", help_text="Para que sirve este kit, en palabras de quien lo arma.", max_length=300)),
                ("activa", models.BooleanField(default=True, help_text="Una plantilla que se deja de usar se desactiva en vez de borrarse: sigue explicando por que un despacho viejo llevaba lo que llevaba.")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL, verbose_name="Created By")),
                ("org", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plantillas_kit", to="common.org")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL, verbose_name="Last Modified By")),
            ],
            options={
                "db_table": "campo_plantilla_kit",
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="LineaDePlantilla",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("cantidad", models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created_by", to=settings.AUTH_USER_MODEL, verbose_name="Created By")),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="en_plantillas", to="campo.materialcatalogo")),
                ("plantilla", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lineas", to="campo.plantilladekit")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated_by", to=settings.AUTH_USER_MODEL, verbose_name="Last Modified By")),
            ],
            options={
                "db_table": "campo_linea_plantilla",
                "ordering": ["material__categoria", "material__nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="plantilladekit",
            constraint=models.UniqueConstraint(
                fields=("org", "nombre"), name="unique_plantilla_por_org"
            ),
        ),
        migrations.AddConstraint(
            model_name="lineadeplantilla",
            constraint=models.UniqueConstraint(
                fields=("plantilla", "material"), name="unique_material_por_plantilla"
            ),
        ),
    ]
