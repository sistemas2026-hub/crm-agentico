# Material del dia (28/10/2026, SPEC/objetivos/material-del-dia.md): que kit
# lleva cada labor y de que bodega carga cada cuadrilla. Dos columnas que
# admiten vacio: nada cambia hasta que la empresa las configure.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0039_niveles_de_respuesta'),
    ]

    operations = [
        migrations.AddField(
            model_name='labor',
            name='plantilla_de_kit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='labores', to='campo.plantilladekit'),
        ),
        migrations.AddField(
            model_name='cuadrilla',
            name='bodega',
            field=models.ForeignKey(blank=True, help_text='Ubicacion de inventario de tipo bodega.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cuadrillas_que_cargan', to='campo.ubicacioninventario'),
        ),
    ]
