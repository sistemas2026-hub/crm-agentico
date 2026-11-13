# Estampa la política de Row-Level Security sobre la tabla de constancia del
# razonamiento del cerebro.
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
# ORM. Mismo razonamiento, y mismo molde, que operaciones/0002.
#
# POR QUE ES UNA MIGRACION APARTE DE 0016
# ---------------------------------------
# Porque 'atomic = False' es obligatorio aquí --cada DROP/CREATE POLICY toma un
# ACCESS EXCLUSIVE, y confirmar por sentencia mantiene cada bloqueo corto-- y
# mezclarlo con el CREATE TABLE haría que la creación de la tabla también
# corriera sin transacción, sin ninguna necesidad. operaciones/0002 y
# common/0034 ya separan así; se sigue el precedente en vez de inventar otro.
#
# La tabla lleva org_id directo, así que la política estándar aplica tal cual.
#
# Idempotente: el SQL generado abre con DROP POLICY IF EXISTS, así que volver a
# correrla es seguro.

from django.db import migrations

from common.rls import get_check_table_exists_sql, get_enable_policy_sql

TABLA = "operaciones_razonamiento_supervisor"


def estampar_rls(apps, schema_editor):
    """Crea las políticas de aislamiento e inserción sobre la tabla."""
    if schema_editor.connection.vendor != "postgresql":
        print("RLS solo existe en PostgreSQL. Se omite.")
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(get_check_table_exists_sql(), [TABLA])
        if not cursor.fetchone()[0]:
            print(f"  Se omite {TABLA} (la tabla no existe)")
            return
        cursor.execute(get_enable_policy_sql(TABLA))

    print(f"  Política RLS estampada en {TABLA}")


def sin_reversa(apps, schema_editor):
    """
    No hace nada.

    Revertir significaría quitar el aislamiento entre organizaciones, que nunca
    es la dirección segura. Las políticas no cambian el resultado de una
    consulta correctamente acotada, así que dejarlas puestas no rompe nada en
    una revisión anterior del código. Si la tabla se elimina, la política se va
    con ella.
    """


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("operaciones", "0016_razonamientosupervisor"),
    ]

    operations = [
        migrations.RunPython(estampar_rls, sin_reversa),
    ]
