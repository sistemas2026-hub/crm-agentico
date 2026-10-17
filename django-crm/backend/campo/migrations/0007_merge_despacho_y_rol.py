# -*- coding: utf-8 -*-
"""
Une las dos ramas del grafo de migraciones de `campo`.

POR QUE EXISTE
--------------
Dos ramas divergieron y cada una escribio su propia `0003` sobre el mismo padre
`0002`:

    0003_alter_asignaciontrabajo_rol   (la rama de despliegue)
    0003_campos_de_despacho            (la rama de Campo, y de ella cuelgan
                                        0004/0005/0006, las de materiales)

Django ve dos hojas en el grafo de una misma app y se niega a migrar hasta que
alguien las una. Se resolvio con un MERGE y no renumerando: conserva la historia
de las dos ramas, y renumerar reescribiria migraciones que ya se aplicaron en
produccion.

POR QUE EL MERGE ES SEGURO, medido antes de escribirlo
-----------------------------------------------------
La pregunta que decide un merge es si las dos hojas tocan lo mismo:

    0003_alter_asignaciontrabajo_rol   AlterField  asignaciontrabajo.rol
    0003_campos_de_despacho            AddField    ordentrabajo x 9 campos

Modelos distintos, cero colision. Y ninguna de las de materiales
(0004/0005/0006) toca `asignaciontrabajo`, asi que el orden de aplicacion entre
las dos ramas no cambia el resultado.

No lleva operaciones: un merge solo une el grafo.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("campo", "0003_alter_asignaciontrabajo_rol"),
        ("campo", "0006_actadedevolucion_incidenciadematerial_and_more"),
    ]

    operations = []
