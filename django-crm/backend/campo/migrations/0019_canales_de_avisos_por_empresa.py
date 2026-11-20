# -*- coding: utf-8 -*-
#
# LOS AVISOS DEJAN DE NOMBRAR UN PROVEEDOR
# ========================================
# La 0018 creo `CanalDeAvisos` con un campo llamado `chat_webhook` y una sola
# fila por empresa. Eso escribe el nombre de un proveedor --Google Chat-- en la
# estructura, que es justo lo que la regla multi-tenant del proyecto prohibe: la
# empresa siguiente usa Teams, o Slack, o quiere un correo.
#
# Ahora son N filas con un `tipo`, y lo que era `url_base_app` --que es de la
# empresa y no de un canal-- se muda a su propia tabla.
#
# POR QUE SE PUEDE BORRAR LA TABLA EN VEZ DE MIGRAR SUS FILAS
# -----------------------------------------------------------
# La 0018 es del MISMO dia y nunca se desplegó: la rama no esta publicada y la
# unica base donde corrio es el laboratorio. No hay una sola fila configurada en
# ningun lado, asi que no hay nada que migrar.
#
# Si esto se descubriera tarde --con webhooks ya cargados-- la migracion seria
# otra: copiar `chat_webhook` a una fila con `tipo='google_chat'`. Queda escrito
# por si alguien llega aca con datos y se pregunta por que no se hizo asi.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("campo", "0018_avisos_al_tecnico"),
        ("common", "0041_m05a_lifecycle_incidencia"),
    ]

    operations = [
        migrations.DeleteModel(name="CanalDeAvisos"),
        migrations.CreateModel(
            name="ConfiguracionDeAvisos",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=__import__("uuid").uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "url_base_app",
                    models.URLField(
                        blank=True,
                        default="",
                        help_text=(
                            "Dominio desde el que se arman los enlaces a una "
                            "orden (https://campo.empresa.co). Sin esto el "
                            "aviso va sin enlace."
                        ),
                        max_length=300,
                    ),
                ),
                (
                    "org",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configuracion_de_avisos",
                        to="common.org",
                    ),
                ),
            ],
            options={"db_table": "campo_configuracion_de_avisos"},
        ),
        migrations.CreateModel(
            name="CanalDeAvisos",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=__import__("uuid").uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("google_chat", "Google Chat"),
                            ("slack", "Slack"),
                            ("teams", "Microsoft Teams"),
                            ("discord", "Discord"),
                            ("webhook", "Webhook genérico"),
                            ("correo", "Correo"),
                        ],
                        default="google_chat",
                        max_length=24,
                    ),
                ),
                (
                    "nombre",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Cómo lo llama la empresa. Solo para reconocerlo "
                            "en la lista."
                        ),
                        max_length=80,
                    ),
                ),
                (
                    "destino",
                    models.CharField(
                        help_text=(
                            "URL del webhook, o dirección de correo según el "
                            "tipo."
                        ),
                        max_length=500,
                    ),
                ),
                (
                    "activo",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Apagar un canal sin perder la configuración. Se "
                            "apaga acá y no borrándolo, para que volver a "
                            "encenderlo no obligue a pedirle la URL otra vez a "
                            "alguien."
                        ),
                    ),
                ),
                ("probado_en", models.DateTimeField(blank=True, null=True)),
                ("ultimo_error", models.CharField(blank=True, default="", max_length=300)),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="canales_de_avisos",
                        to="common.org",
                    ),
                ),
            ],
            options={
                "db_table": "campo_canal_de_avisos",
                "ordering": ["tipo", "nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="canaldeavisos",
            # El mismo destino dos veces en la misma empresa manda el aviso
            # duplicado, que es como se logra que la gente deje de leerlos.
            constraint=models.UniqueConstraint(
                fields=("org", "destino"), name="unique_destino_por_org"
            ),
        ),
    ]
