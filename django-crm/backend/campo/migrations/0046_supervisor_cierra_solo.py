from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campo", "0045_recordar_al_tecnico"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuraciondeseguimiento",
            name="supervisor_cierra_solo",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Si el Supervisor aprueba y cierra solo, ticket del ISP "
                    "incluido, lo que su revisión marca «Se puede cerrar». "
                    "Pasa por la puerta autónoma del motor: sin Autonomía 2 "
                    "y la autorización de la herramienta, no cierra nada."
                ),
            ),
        ),
    ]
