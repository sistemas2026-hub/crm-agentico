# Despacho llena el formulario solo (19/10/2026): la plantilla por el asunto
# del ticket, y «para cuando» por la creacion del ticket mas el plazo.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0033_corte_de_red_por_empresa'),
    ]

    operations = [
        migrations.AddField(
            model_name='worktype',
            name='asuntos',
            field=models.JSONField(
                blank=True, default=list,
                help_text='Asuntos de tickets del proveedor que se despachan con '
                          'esta plantilla. Dos plantillas de la empresa no '
                          'comparten asunto.'),
        ),
        migrations.AddField(
            model_name='worktype',
            name='plazo_dias',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                help_text='Dias desde la creacion del ticket para hacer el trabajo.'),
        ),
    ]
