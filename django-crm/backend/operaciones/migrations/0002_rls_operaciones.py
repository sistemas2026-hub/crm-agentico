# Estampa las políticas de Row-Level Security sobre las seis tablas del módulo
# de operaciones (M02, M03 y M09).
#
# POR QUE VA AQUI Y NO SOLO EN ORG_SCOPED_TABLES
# ----------------------------------------------
# Registrar la tabla en common/rls la hace visible para el tooling central
# (manage_rls --status, las auditorías), pero NO crea ninguna política: eso lo
# hace una migración. Es exactamente el hueco que common/0034 tuvo que venir a
# tapar para los seis pipelines de Kanban -- estaban vivos, sin registrar y sin
# política, y en las bases desplegadas no se notaba porque alguien las había
# estampado a mano fuera de banda. Una base construida solo con migraciones
# --CI, o un despliegue nuevo-- se quedaba sin nada debajo de los filtros del
# ORM.
#
# Las seis tablas llevan org_id directo, así que la política estándar aplica
# tal cual.
#
# Idempotente: el SQL generado abre con DROP POLICY IF EXISTS, así que volver a
# correrla es seguro.
#
# atomic = False, igual que common/0028 y common/0034: cada DROP/CREATE POLICY
# toma un ACCESS EXCLUSIVE, y confirmar por sentencia mantiene cada bloqueo
# corto.

from django.db import migrations

from common.rls import get_check_table_exists_sql, get_enable_policy_sql

TABLAS_OPERACIONES = [
    "operaciones_actividad",
    "operaciones_disponibilidad",
    "operaciones_programacion_semanal",
    "operaciones_programacion_orden",
    "operaciones_novedad",
    "operaciones_propuesta_supervisor",
]


def estampar_rls(apps, schema_editor):
    """Crea las políticas de aislamiento e inserción sobre las seis tablas."""
    if schema_editor.connection.vendor != "postgresql":
        print("RLS solo existe en PostgreSQL. Se omite.")
        return

    estampadas = 0
    with schema_editor.connection.cursor() as cursor:
        for tabla in TABLAS_OPERACIONES:
            cursor.execute(get_check_table_exists_sql(), [tabla])
            if not cursor.fetchone()[0]:
                print(f"  Se omite {tabla} (la tabla no existe)")
                continue
            cursor.execute(get_enable_policy_sql(tabla))
            estampadas += 1

    print(f"  Políticas RLS estampadas en {estampadas} tabla(s) de operaciones")


def sin_reversa(apps, schema_editor):
    """
    No hace nada.

    Revertir significaría quitar el aislamiento entre organizaciones, que nunca
    es la dirección segura. Las políticas no cambian el resultado de una
    consulta correctamente acotada, así que dejarlas puestas no rompe nada en
    una revisión anterior del código.
    """


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("operaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(estampar_rls, sin_reversa),
    ]
