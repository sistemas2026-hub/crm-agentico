# Estampa la política de Row-Level Security sobre la tabla del estilo editable
# del Supervisor.
#
# Mismo molde y mismo motivo que operaciones/0002 y operaciones/0017: registrar
# la tabla en common/rls la hace visible para el tooling central, pero NO crea
# ninguna política -- eso lo hace una migración. Es el hueco que common/0034
# tuvo que venir a tapar para los pipelines de Kanban: vivos, sin registrar y
# sin política, y en las bases desplegadas no se notaba porque alguien las había
# estampado a mano fuera de banda.
#
# Y aquí importa especialmente: esta tabla contiene el PROMPT de cada empresa.
# Sin política, una consulta mal acotada podría devolver el prompt de otra.
#
# Idempotente: el SQL generado abre con DROP POLICY IF EXISTS.
#
# atomic = False: cada DROP/CREATE POLICY toma un ACCESS EXCLUSIVE, y confirmar
# por sentencia mantiene cada bloqueo corto.

from django.db import migrations

from common.rls import get_check_table_exists_sql, get_enable_policy_sql

TABLA = "operaciones_estilo_supervisor"


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
    es la dirección segura. Si la tabla se elimina, la política se va con ella.
    """


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("operaciones", "0018_estilosupervisor"),
    ]

    operations = [
        migrations.RunPython(estampar_rls, sin_reversa),
    ]
