from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campo", "0044_novedad_de_cuadrilla"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuraciondeseguimiento",
            name="recordar_al_tecnico",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Si el Supervisor le manda un recordatorio al teléfono del "
                    "técnico cuando su orden pasa la ventana sin reporte. Uno "
                    "por atraso: un reporte nuevo empieza otro."
                ),
            ),
        ),
    ]
