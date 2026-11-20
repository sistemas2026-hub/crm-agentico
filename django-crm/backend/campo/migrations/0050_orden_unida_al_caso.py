# -*- coding: utf-8 -*-
"""
La orden de campo queda UNIDA a su ticket (12/11/2026).

Agrega `OrdenTrabajo.caso` (FK nullable a `cases.Case`, SET_NULL) y rellena las
ordenes existentes que nacieron de un ticket: `origen_tipo="case"` con un
`origen_ref` que es el id de un caso DE LA MISMA EMPRESA. Lo que no cumple las
tres cosas queda en NULL --nunca se une a ciegas-- y se cuenta.

EL RELLENO Y LA SEGURIDAD POR FILA (RLS)
----------------------------------------
`case` tiene RLS forzado: con un rol que NO la saltea y sin `app.current_org`,
la consulta de casos devuelve cero filas y el relleno uniria cero ordenes SIN
ERROR. Por eso se fija el contexto de cada empresa antes de buscar sus casos
--el mismo patron que `common/0031`-- y se limpia al final. Las ordenes
(`campo_orden_trabajo`) no tienen RLS: se leen todas de una vez.

La vuelta atras quita la columna; el relleno no tiene nada que deshacer.
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


def _contexto(connection, valor):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_org', %s, false)", [valor])


def rellenar(apps, schema_editor):
    """Une cada orden nacida de un ticket con su caso, empresa por empresa."""
    connection = schema_editor.connection
    OrdenTrabajo = apps.get_model("campo", "OrdenTrabajo")
    Case = apps.get_model("cases", "Case")

    por_org = {}
    for o in (OrdenTrabajo.objects.filter(origen_tipo="case", caso__isnull=True)
              .exclude(origen_ref="").only("id", "org_id", "origen_ref").iterator()):
        try:
            pk = uuid.UUID(str(o.origen_ref).strip())
        except (ValueError, AttributeError):
            continue
        por_org.setdefault(o.org_id, []).append((o.id, pk))

    try:
        for org_id, filas in por_org.items():
            _contexto(connection, str(org_id))
            existentes = set(Case.objects.filter(
                org_id=org_id, pk__in={pk for _, pk in filas}
            ).values_list("pk", flat=True))
            for orden_id, pk in filas:
                if pk in existentes:
                    OrdenTrabajo.objects.filter(pk=orden_id).update(caso_id=pk)
    finally:
        _contexto(connection, "")


class Migration(migrations.Migration):

    dependencies = [
        #  0050 y no 0049 (13/11/2026): la 0049 de produccion es el cotejo del
        #  reporte, y dos hojas en la misma app frenan el 'migrate' del
        #  despliegue ("Conflicting migrations detected").
        ("campo", "0049_cotejo_del_reporte"),
        ("cases", "0034_primera_respuesta_desde_el_hilo_externo"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordentrabajo",
            name="caso",
            field=models.ForeignKey(
                blank=True,
                help_text="El ticket del que nacio esta visita, si nacio de uno.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ordenes_de_campo",
                to="cases.case",
            ),
        ),
        migrations.RunPython(rellenar, migrations.RunPython.noop),
    ]
