# -*- coding: utf-8 -*-
"""
Marca un campo de texto como leíble con la cámara, publicando una versión.

    python manage.py campo_escaneable --org <uuid> --tipo instalacion_fibra \
        --campo serial_de_la_onu
    ... --aplicar

POR QUÉ EXISTE  --  12/11/2026
------------------------------
El usuario, sobre las instalaciones: «al momento de digitar los datos hay
muchos errores, mala escritura del nombre, direcciones mal digitalizadas». Y el
serial de la ONU se teclea a mano aunque la aplicación TIENE lector de códigos
desde hace meses: lo usa para materiales y no estaba conectado a ningún campo
del formulario.

El lector de la app ya explica en su propio comentario por qué esto no se
arregla validando: «un dígito mal no da error: queda un equipo registrado con
un serial que no existe, y el problema aparece semanas después cuando alguien
busca ese equipo y no está».

LO DECIDE LA PLANTILLA, NO LA APP
---------------------------------
Un serial de ONU se lee de una etiqueta; «contá qué pasó» no se lee de ninguna
parte. Un botón de cámara en todos los campos de texto llenaría de cámaras los
que no tienen nada que escanear, y elegirlos en el código obligaría a que la
app conozca los campos de cada empresa -- justo lo que el formulario dirigido
por esquema existe para evitar.

SOLO EN CAMPOS DE TEXTO, y se niega en los demás en vez de obedecer. La app
ignora la bandera en un número --un número no está en ninguna etiqueta de
código de barras, y la caja ya tiene la unidad a la derecha-- así que
publicarla ahí sería publicar una versión nueva que no cambia nada y dejar a
quien la pidió creyendo que sí.

QUÉ NO HACE, Y POR QUÉ
----------------------
No recompone el esquema. Mismo motivo que `permitir_otro`, aprendido contra
producción el 11/11/2026: `componer` es el validador de lo que entra POR EL
EDITOR, y una plantilla que lleva meses publicada no entró por ahí -- la v16 de
`correctivo_fibra` tiene campos que el editor no sabe crear. Recomponer tenía
dos finales y los dos malos: rechazar la plantilla entera, o «arreglarle» tipos
a campos que hoy funcionan.

La guarda que reemplaza a `componer` es más estrecha y más fuerte para este
caso: se compara el esquema nuevo contra el vigente y se exige que la ÚNICA
diferencia sea la bandera.

Y NO ES UN SUSTITUTO DE LA CASILLA EN EL EDITOR. La pantalla de plantillas
todavía no la ofrece, así que hoy una empresa no puede marcarlo sola -- y eso
contradice CLAUDE.md §3.3, que pide que lo que varía por empresa se edite desde
la interfaz. Este comando desbloquea; la casilla queda pendiente y está dicho.
"""
import copy

from django.core.management.base import BaseCommand, CommandError


def _marcar(campo: dict) -> None:
    """La bandera, igual que la escribe `componer` (`plantillas.py`)."""
    campo["escaneable"] = True


class Command(BaseCommand):
    help = ("Marca un campo de texto como leíble con la cámara, publicando "
            "una versión.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")
        parser.add_argument("--tipo", required=True,
                            help="código de la plantilla")
        parser.add_argument("--campo", required=True,
                            help="id del campo de texto")
        parser.add_argument("--aplicar", action="store_true",
                            help="publicar (sin esto, solo dice qué haría)")

    def handle(self, *args, **opciones):
        import json

        from campo.models import WorkType, WorkTypeVersion
        from common.models import Org

        org = Org.objects.filter(pk=opciones["org"]).first()
        if org is None:
            raise CommandError("esa organización no existe")
        tipo = WorkType.objects.filter(org=org, codigo=opciones["tipo"]).first()
        if tipo is None:
            raise CommandError(f"la plantilla '{opciones['tipo']}' no existe")

        vigente = (WorkTypeVersion.objects
                   .filter(work_type=tipo, estado=WorkTypeVersion.PUBLICADA)
                   .order_by("-version").first())
        if vigente is None:
            raise CommandError("esa plantilla no tiene ninguna versión publicada")

        #  COPIA PROFUNDA. `dict(c)` es superficial y dejaría `c["reglas"]`
        #  compartido con la versión vigente: el control se compararía contra
        #  lo ya mutado y daría siempre igual, siempre verde. Lo midió
        #  `permitir_otro` el 11/11/2026.
        esquema = copy.deepcopy(vigente.esquema or {})
        campos = esquema.get("campos") or []
        objetivo = next((c for c in campos
                         if c.get("id") == opciones["campo"]), None)
        if objetivo is None:
            ids = [c.get("id") for c in campos]
            raise CommandError(
                f"el campo '{opciones['campo']}' no está en la plantilla. "
                f"Los que hay: {ids}")

        self.stdout.write(f"  {tipo.codigo}: vigente es la v{vigente.version}")
        self.stdout.write(f"  campo '{objetivo.get('id')}' — tipo "
                          f"'{objetivo.get('tipo')}', "
                          f"título «{objetivo.get('titulo')}»")

        #  EL TIPO SE EXIGE ACÁ, no se avisa y se sigue: la app solo dibuja el
        #  botón en texto, así que publicarlo en otro tipo gasta una versión y
        #  no cambia nada.
        if objetivo.get("tipo") != "texto":
            raise CommandError(
                f"ese campo es de tipo '{objetivo.get('tipo')}' y la cámara "
                f"solo se ofrece en campos de texto. No se publica nada.")

        if objetivo.get("escaneable") is True:
            self.stdout.write("  YA lo tiene: no hay nada que publicar.")
            return

        _marcar(objetivo)

        if not opciones["aplicar"]:
            self.stdout.write("")
            self.stdout.write(f"  SIMULACRO: se publicaría la "
                              f"v{vigente.version + 1} con «{objetivo.get('titulo')}» "
                              f"leíble con la cámara.")
            self.stdout.write("  Nada más cambia. Agregá --aplicar.")
            return

        #  LA ÚNICA DIFERENCIA TIENE QUE SER LA BANDERA. `componer` valida que
        #  un esquema sea construible; esto valida que no se tocó nada más,
        #  que es exactamente lo que este comando promete.
        control = copy.deepcopy(vigente.esquema or {})
        for c in (control.get("campos") or []):
            if c.get("id") == opciones["campo"]:
                _marcar(c)
        if json.dumps(esquema, sort_keys=True) != json.dumps(control,
                                                             sort_keys=True):
            raise CommandError(
                "el esquema nuevo difiere del vigente en algo más que la "
                "bandera: no se publica nada")

        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=vigente.version + 1,
            schema_version=vigente.schema_version,
            estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
        self.stdout.write("")
        self.stdout.write(f"  PUBLICADA la v{version.version}.")
        self.stdout.write("")
        self.stdout.write("  FALTA UN PASO: las órdenes ya abiertas siguen con "
                          "la versión con que nacieron.")
        self.stdout.write(f"    python manage.py repuntar_plantilla --org "
                          f"{org.id} --tipo {tipo.codigo}")
        self.stdout.write("  Eso mueve solo las que nadie empezó. Las que ya "
                          "tienen respuestas no se tocan.")
        self.stdout.write("")
        self.stdout.write("  Y EL TELÉFONO NECESITA LA VERSIÓN NUEVA DE LA APP: "
                          "el botón es código, no esquema.")
