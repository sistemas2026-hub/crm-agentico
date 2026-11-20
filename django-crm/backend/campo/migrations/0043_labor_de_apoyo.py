from django.db import migrations, models


def _la_obra_de_red_no(apps, schema_editor):
    """La obra de red pide equipo que una cuadrilla de soporte no lleva."""
    Labor = apps.get_model("campo", "Labor")
    Labor.objects.filter(codigo="trabajos").update(se_toma_de_apoyo=False)


class Migration(migrations.Migration):
    """La labor de apoyo de una jornada (30/10/2026). Columna con valor por
    omision vacio: las jornadas que ya existen quedan sin apoyo, como estaban.
    Y en cada labor, si se toma de apoyo: todas si, menos la obra de red."""

    dependencies = [
        ("campo", "0042_orden_del_dia"),
    ]

    operations = [
        migrations.AddField(
            model_name="jornadadecuadrilla",
            name="labor_de_apoyo",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="labor",
            name="se_toma_de_apoyo",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(_la_obra_de_red_no, migrations.RunPython.noop),
    ]
