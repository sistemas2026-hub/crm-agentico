# El rol BODEGA se puede asignar (13/10/2026). Ver common/utils.py::ROLES.
#
# Solo cambia las opciones del campo: no toca filas ni la columna, que ya es
# varchar(50). Es reversible.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0043_rls_sin_cast_a_texto"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="role",
            field=models.CharField(
                choices=[("ADMIN", "ADMIN"), ("SUPERVISOR", "SUPERVISOR"),
                         ("OPERACIONES", "OPERACIONES"), ("USER", "USER"),
                         ("BODEGA", "BODEGA")],
                default="USER", max_length=50),
        ),
    ]
