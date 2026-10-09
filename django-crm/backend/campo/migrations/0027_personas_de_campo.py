# -*- coding: utf-8 -*-
"""
Un auxiliar sin celular tambien integra la cuadrilla.

`IntegranteDeJornada` apuntaba a `Profile`, que exige un `User` con correo y
credenciales: o sea que para anotar a un auxiliar habia que inventarle una
cuenta que nadie iba a usar. El catalogo de roles ya ofrecia 'ayudante' y
'chofer' para gente que el modelo no permitia registrar.

Esta migracion separa las dos preguntas --quien ENTRA al sistema y quien
TRABAJO-- en dos tablas, y mueve los integrantes que ya existan sin perder
ninguno: cada `Profile` que estuviera en una jornada recibe su
`PersonaDeCampo` con la cuenta enlazada, asi que su historial sigue siendo
uno.

El paso de datos corre en los dos sentidos. La vuelta atras solo puede
conservar a los integrantes que TIENEN cuenta --un auxiliar sin `Profile` no
cabe en el modelo viejo-- y por eso los cuenta y lo dice en vez de borrarlos
en silencio.
"""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def poblar_personas(apps, schema_editor):
    """Una `PersonaDeCampo` por cada cuenta que ya integraba una jornada."""
    IntegranteDeJornada = apps.get_model("campo", "IntegranteDeJornada")
    PersonaDeCampo = apps.get_model("campo", "PersonaDeCampo")

    por_cuenta = {}
    for integrante in IntegranteDeJornada.objects.select_related(
        "profile__user", "org"
    ).all():
        clave = (integrante.org_id, integrante.profile_id)
        persona = por_cuenta.get(clave)
        if persona is None:
            user = getattr(integrante.profile, "user", None)
            # El nombre vive en `User.name`, no en `Profile` -- la misma
            # leccion que ya dejo escrita `cuadrillas_views._nombre_de`: sin
            # esto la pantalla diria "Custodia de 47905efd-...".
            nombre = (
                getattr(user, "name", "") or getattr(user, "email", "") or ""
            ).strip() or "Sin nombre"
            persona, _ = PersonaDeCampo.objects.get_or_create(
                org_id=integrante.org_id,
                profile_id=integrante.profile_id,
                defaults={"nombre": nombre, "rol_habitual": integrante.rol},
            )
            por_cuenta[clave] = persona
        integrante.persona = persona
        integrante.save(update_fields=["persona"])


def devolver_cuentas(apps, schema_editor):
    """La vuelta atras: solo cabe quien tiene cuenta, y se dice cuantos no."""
    IntegranteDeJornada = apps.get_model("campo", "IntegranteDeJornada")

    sin_cuenta = 0
    for integrante in IntegranteDeJornada.objects.select_related("persona").all():
        cuenta = getattr(integrante.persona, "profile_id", None)
        if cuenta is None:
            sin_cuenta += 1
            continue
        integrante.profile_id = cuenta
        integrante.save(update_fields=["profile"])

    if sin_cuenta:
        # No se borra nada aca: las filas quedan y la que sigue
        # (RemoveField de 'persona') las dejaria sin persona ni cuenta. Que la
        # vuelta atras avise es lo unico honesto que puede hacer.
        print(
            f"\n  [aviso] {sin_cuenta} integrante(s) sin cuenta de usuario no "
            f"caben en el modelo anterior: revisarlos antes de seguir."
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("common", "0001_initial"),
        ("campo", "0026_zonas_operativas"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonaDeCampo",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Last Modified At")),
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                (
                    "rol_habitual",
                    models.CharField(
                        choices=[
                            ("tecnico", "Técnico"),
                            ("tecnico_lider", "Técnico líder"),
                            ("ayudante", "Ayudante"),
                            ("chofer", "Chofer"),
                            ("supervisor", "Supervisor"),
                        ],
                        default="ayudante",
                        max_length=64,
                    ),
                ),
                ("activa", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated_by",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Last Modified By",
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personas_de_campo",
                        to="common.org",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="persona_de_campo",
                        to="common.profile",
                    ),
                ),
            ],
            options={
                "db_table": "campo_persona_de_campo",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="personadecampo",
            constraint=models.UniqueConstraint(
                condition=models.Q(("profile__isnull", False)),
                fields=("org", "profile"),
                name="unique_persona_de_campo_por_cuenta",
            ),
        ),
        # El constraint viejo nombra 'profile', asi que se quita ANTES de que
        # el campo deje de existir.
        migrations.RemoveConstraint(
            model_name="integrantedejornada",
            name="unique_persona_por_jornada",
        ),
        migrations.AddField(
            model_name="integrantedejornada",
            name="persona",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="jornadas_de_cuadrilla",
                to="campo.personadecampo",
            ),
        ),
        migrations.RunPython(poblar_personas, devolver_cuentas),
        migrations.AlterField(
            model_name="integrantedejornada",
            name="persona",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="jornadas_de_cuadrilla",
                to="campo.personadecampo",
            ),
        ),
        #  LA COLUMNA VIEJA SE VA, Y SU VUELTA ATRAS TIENE QUE SER NULLABLE.
        #
        #  Medido el 08/10/2026: con la definicion original (NOT NULL),
        #  revertir esta migracion muere con «column "profile_id" of relation
        #  "campo_integrante_jornada" contains null values» -- Django re-crea
        #  la columna antes de que el RunPython inverso la pueble. O sea que
        #  la salida de emergencia del deploy no existia, y nada lo decia.
        #
        #  El estado pasa a declararla nullable sin tocar la base (la columna
        #  se borra en la operacion siguiente), asi que al revertir se
        #  re-crea nullable. Y nullable es lo correcto, no un atajo: un
        #  auxiliar sin cuenta no cabe en el modelo viejo, y un nulo lo DICE
        #  en vez de inventarle una cuenta.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="integrantedejornada",
                    name="profile",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        # Distinto del que ahora usa `persona`: con el mismo,
                        # el estado intermedio tendria dos campos peleando por
                        # el mismo accesor inverso. Nadie lo usa (verificado
                        # el 08/10/2026 con un barrido del repo).
                        related_name="jornadas_de_cuadrilla_legacy",
                        to="common.profile",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RemoveField(
            model_name="integrantedejornada",
            name="profile",
        ),
        migrations.AlterModelOptions(
            name="integrantedejornada",
            options={"ordering": ["rol", "persona__nombre"]},
        ),
        migrations.AddConstraint(
            model_name="integrantedejornada",
            constraint=models.UniqueConstraint(
                fields=("jornada", "persona"),
                name="unique_persona_por_jornada",
            ),
        ),
    ]
