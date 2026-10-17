# Cancelacion de una solicitud de instalacion por pedido del cliente.
#
# COMPATIBILIDAD HACIA ATRAS: los tres cambios son aditivos. 'estado' solo
# suma una opcion a 'choices' -- que Django valida en Python, no en la base,
# asi que ninguna fila existente queda invalida-- y los dos campos nuevos
# aceptan vacio con default. Una version anterior del codigo leyendo esta
# tabla sigue funcionando: ve dos columnas que no conoce y las ignora.
#
# ROLLBACK: revertir esta migracion borra las dos columnas. Si ya hubiera
# solicitudes canceladas, su 'estado' quedaria en 'cancelada' -- un valor que
# el codigo viejo no tiene en choices y mostraria crudo, sin romper. El motivo
# si se perderia, y por eso conviene exportarlo antes de revertir en vez de
# confiar en que no habia ninguna.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0003_solicitudservicio_ip_autorizaciones'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudservicio',
            name='motivo_cancelacion',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='solicitudservicio',
            name='cancelada_en',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='solicitudservicio',
            name='estado',
            field=models.CharField(
                choices=[('nueva', 'Nueva'), ('enviada', 'Enviada'),
                         ('aprobada', 'Aprobada'),
                         ('sin_factibilidad', 'Sin factibilidad'),
                         ('cancelada', 'Cancelada')],
                default='nueva', max_length=20),
        ),
    ]
