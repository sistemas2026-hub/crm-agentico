# Como se llama cada labor en cada empresa (20/10/2026): se cambia el nombre
# que se ve, no el valor interno que usan el reparto y el Supervisor.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0034_plantilla_asuntos_y_plazo'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuraciondereparto',
            name='nombres_de_labor',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
