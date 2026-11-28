# -*- coding: utf-8 -*-
"""Une las dos historias de migraciones de `campo`. No cambia nada.

POR QUE EXISTIA EL CONFLICTO
----------------------------
Dos ramas colgaron de `0011_direccion_de_los_movimientos_historicos` al mismo
tiempo:

    0011 ─┬─ 0012_restaurar_catalogo_de_rol   (produccion: `choices` de rol)
          └─ 0012_plantillas_de_kit ─ 0013 ─ 0014 ─ 0015   (el inventario)

Dos nodos hoja, y Django se niega a arrancar con «Conflicting migrations
detected». **Eso no rompe solo las pruebas: el entrypoint del backend corre
`migrate`, asi que habria roto el despliegue.** Es el mismo problema que la propia
`0012_restaurar_catalogo_de_rol` cuenta en su docstring, una vuelta mas tarde.

POR QUE UN MERGE Y NO UNA RENUMERACION
--------------------------------------
Aquella vez se renumero porque era un numero repetido sobre una sola historia.
Esta vez si hay dos historias: cuatro migraciones del inventario ya aplicadas en
bases reales de un lado, y el arreglo del catalogo de rol del otro. Renumerar
exigiria reescribir migraciones que ya corrieron.

POR QUE ES SEGURA
-----------------
Las dos ramas tocan cosas distintas y no se pisan:

    0012_restaurar_catalogo_de_rol   `choices` de `AsignacionTrabajo.rol`, que
                                     Django valida en serializers -- no hay CHECK
                                     ni enum en la base, asi que no cambia datos
    0012..0015 del inventario        tablas NUEVAS (plantillas, bloqueos,
                                     configuracion de seguimiento, contacto) mas
                                     `imagen_key` y el estado `bloqueada`

`operations` esta vacio a proposito: una migracion de merge solo declara que estas
dos historias siguen juntas desde aca.

VERIFICADO EL 30/09/2026: las 17 de `campo` aplican desde una base VACIA en este
orden, y `makemigrations --check` no detecta cambios pendientes despues.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("campo", "0012_restaurar_catalogo_de_rol"),
        ("campo", "0015_seguimiento_y_contacto"),
    ]

    operations = []
