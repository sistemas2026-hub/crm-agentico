# Vuelve a sellar las politicas de aislamiento comparando UUID contra UUID.
#
# QUE ARREGLA  --  medido el 09/10/2026
# -------------------------------------
# La politica decia `org_id::text = (select ...)`. Castear la COLUMNA deja
# inutilizable cualquier indice sobre org_id: Postgres tiene que leer la tabla
# entera y convertir fila por fila. Y como la politica se aplica a TODAS las
# consultas de las 65 tablas con aislamiento, convertia cada una en un
# recorrido secuencial.
#
# Medido sobre 200.000 filas:
#
#     org_id::text = text  ->  Parallel Seq Scan   70,4 ms
#     org_id = uuid        ->  Index Only Scan      6,7 ms
#
# El sintoma era una carga de 22 SEGUNDOS de la pantalla del Supervisor NOC,
# que dispara decenas de consultas sobre `case` y `activity`. En la misma
# sesion, TODAS las demas peticiones tardaban menos de 500 ms -- lo que
# descarto la red, el frontend y el sondeo del panel, que eran las sospechas
# iniciales.
#
# EL CAST SE MUEVE AL VALOR, donde se evalua UNA VEZ: el `(select ...)` que ya
# estaba lo convierte en un InitPlan.
#
# LO QUE CAMBIA DE CONDUCTA, y mejora: un valor de contexto no vacio pero mal
# formado comparaba falso y devolvia cero filas EN SILENCIO. Ahora levanta.
# Cero filas sin error es indistinguible de "no hay datos", que es la forma de
# fallar que este repositorio ya pago varias veces. Un valor VACIO sigue
# devolviendo cero filas: NULLIF lo vuelve NULL y `org_id = NULL` no coincide
# con nada -- el fail-closed de siempre.
#
# NO CAMBIA QUE DATOS VE NADIE. `org_id::text = '<uuid>'` y `org_id =
# '<uuid>'::uuid` seleccionan exactamente las mismas filas; lo unico distinto
# es como Postgres llega a ellas.
#
# IDEMPOTENTE: el SQL generado empieza con DROP POLICY IF EXISTS.
#
# atomic = False, igual que las otras migraciones de RLS: cada DROP/CREATE
# POLICY toma un ACCESS EXCLUSIVE, y confirmar por sentencia mantiene cada
# bloqueo corto en vez de uno largo sobre 65 tablas.

from django.db import migrations

from common.rls import (ORG_SCOPED_TABLES, get_check_table_exists_sql,
                        get_enable_policy_sql)


def resellar(apps, schema_editor):
    """Vuelve a crear las politicas de todas las tablas con aislamiento."""
    if schema_editor.connection.vendor != "postgresql":
        print("RLS solo existe en PostgreSQL. Se omite.")
        return

    resellada = 0
    ausente = 0
    with schema_editor.connection.cursor() as cursor:
        for tabla in ORG_SCOPED_TABLES:
            cursor.execute(get_check_table_exists_sql(), [tabla])
            if not cursor.fetchone()[0]:
                #  Una tabla declarada que todavia no existe no es un error:
                #  pasa en una base construida solo con migraciones, donde la
                #  app que la crea puede correr despues. Se cuenta y se dice.
                ausente += 1
                continue
            cursor.execute(get_enable_policy_sql(tabla))
            resellada += 1

    print(f"  Politicas reselladas: {resellada} tabla(s); "
          f"{ausente} declarada(s) y todavia sin crear")


def sin_vuelta(apps, schema_editor):
    """
    No-op.

    Volver atras significaria restaurar el cast que hace lenta cada consulta.
    La politica nueva selecciona exactamente las mismas filas, asi que dejarla
    puesta no rompe nada en una revision anterior del codigo.
    """


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("common", "0042_p6_coordinacion"),
    ]

    operations = [
        migrations.RunPython(resellar, sin_vuelta),
    ]
