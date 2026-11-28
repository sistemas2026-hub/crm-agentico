# -*- coding: utf-8 -*-
"""El motivo del bloqueo, en botones y no en un campo vacío.

    python manage.py motivos_del_bloqueo --org <id> --tipo correctivo_fibra
    python manage.py motivos_del_bloqueo --org <id> --tipo correctivo_fibra --aplicar

POR QUÉ EXISTE
--------------
Mejora 7 del encargo de la app (`SPEC/APP_CAMPO_DIEZ_MEJORAS.md`): «motivo
primero y como botones (falta material / sin acceso / daño en red / otro) y el
texto libre debajo. Hoy arranca en un campo vacío, parado en la calle».

Y NO HACE FALTA TOCAR LA APP, porque el formulario de cada momento sale del
esquema de la plantilla: `seguimiento_campo.formulario_de` --«la app y la
pantalla dibujan ESTO; ninguna de las dos sabe qué campos existen hasta
preguntar»--. Hoy ninguna plantilla declara su bloqueo, así que se usa el
mínimo genérico de `seguimiento_campo.MINIMO`: dos campos de TEXTO, los dos
obligatorios. Ese es el campo vacío del pedido.

LA COLUMNA YA EXISTÍA Y NADIE LA LLENABA
----------------------------------------
`BloqueoDeTrabajo.categoria` está en el modelo desde el principio, con su
comentario: «lo que el tenant eligió en su formulario, copiado como texto para
poder agrupar. No es una lista cerrada de plataforma: cada empresa tiene las
suyas». Y `bloqueos.py:139` la lee de `respuestas["categoria"]`.

Nadie declaró nunca un campo con ese id, así que **la columna está vacía en
todos los bloqueos** y no se puede agrupar por nada. Es el patrón que CLAUDE.md
§6 llama «código construido no es código que corre», visto desde el otro lado:
el lector estaba escrito y esperando un dato que nadie mandaba.

QUÉ QUEDA DESPUÉS
-----------------
    categoria        selección, OBLIGATORIA, con «Otro» y texto libre
    motivo           texto, OPCIONAL -- el detalle que la lista no cubre
    necesita_de_noc  texto, OBLIGATORIO -- igual que el mínimo de hoy

Lo obligatorio pasa de «escribir dos textos» a «tocar un botón y escribir un
texto». Eso es el pedido.

`necesita_de_noc` SIGUE OBLIGATORIO a propósito, y no es un descuido: el
mínimo lo exige con su motivo escrito --«sin eso un bloqueo no es accionable y
vuelve a ser un mensaje de chat»--. Es una decisión cerrada, y con CERO
bloqueos reportados en producción no hay medición nueva para reabrirla
(CLAUDE.md §10).

`motivo` BAJA DE OBLIGATORIO A OPCIONAL, y eso sí se cambia: lo que el
`required` protegía --que el bloqueo diga algo-- ahora lo garantiza la
categoría, que no se puede dejar sin elegir. Y si la lista no alcanza, «Otro»
exige el texto (`faltan_textos_de_otro`).

QUÉ NO HACE
-----------
No sobreescribe un bloqueo que la empresa ya declaró: si `seguimiento.bloqueo`
trae campos, el comando lo dice y se va. Esa lista es una decisión de alguien,
no un hueco que haya que rellenar.

No toca el resto del esquema, y lo verifica: se comparan los dos esquemas sin
la rama del bloqueo y tienen que ser idénticos.
"""
import copy
import json

from django.core.management.base import BaseCommand, CommandError

#: La opción que deja escribir lo que la lista no tiene. El nombre exacto
#: importa: la app (`CampoDelFormulario.otro`) y el servidor (`validador.OTRO`)
#: la reconocen por él.
OTRO = "Otro"

#: Las tres del encargo. SON UN DEFAULT, NO UNA LISTA DE PLATAFORMA: cada
#: empresa bloquea por lo suyo, y `--opciones` las cambia sin tocar código.
#: Mismo criterio que el comentario de `BloqueoDeTrabajo.categoria`.
POR_OMISION = ["Falta material", "Sin acceso al sitio", "Daño en la red"]


def campos_del_bloqueo(opciones: list[str]) -> list[dict]:
    """Los tres campos, en el orden en que se llenan parado en la calle."""
    lista = [o for o in opciones if o != OTRO] + [OTRO]
    return [
        {
            "id": "categoria",
            "titulo": "Por qué no se puede seguir",
            "tipo": "seleccion",
            "permite_otro": True,
            #  LAS DOS CLAVES CON LO MISMO: la app lee `reglas.options` y
            #  `componer` lee `opciones`. Dejar una sola es lo que hizo que
            #  «Otro» no se viera el 11/11/2026.
            "opciones": list(lista),
            "reglas": {"required": True, "options": list(lista)},
        },
        {
            "id": "motivo",
            "titulo": "Contá qué pasó",
            "tipo": "texto",
            "ayuda": "Opcional. El detalle que la lista de arriba no cubre.",
            "reglas": {"max": 500},
        },
        {
            "id": "necesita_de_noc",
            "titulo": "Qué se necesita del NOC",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
    ]


def _sin_el_bloqueo(esquema: dict) -> str:
    """El esquema serializado SIN la rama del bloqueo, para compararlos."""
    copia = copy.deepcopy(esquema or {})
    seg = copia.get("seguimiento")
    if isinstance(seg, dict):
        seg.pop("bloqueo", None)
        if not seg:
            copia.pop("seguimiento", None)
    return json.dumps(copia, sort_keys=True)


class Command(BaseCommand):
    help = "Declara el formulario de bloqueo con el motivo en botones."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--tipo", required=True, help="código de la plantilla")
        parser.add_argument(
            "--opciones", default="",
            help="las categorías, separadas por «;». Sin esto, las tres del "
                 "encargo. «Otro» se agrega siempre al final.")
        parser.add_argument("--aplicar", action="store_true",
                            help="publicar (sin esto, solo dice qué haría)")

    def handle(self, *args, **opciones):
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

        elegidas = [o.strip() for o in (opciones["opciones"] or "").split(";")
                    if o.strip()] or list(POR_OMISION)
        if len(elegidas) < 1:
            raise CommandError("hace falta al menos una categoría")

        esquema = copy.deepcopy(vigente.esquema or {})
        seguimiento = esquema.get("seguimiento")
        if not isinstance(seguimiento, dict):
            seguimiento = {}
        declarado = seguimiento.get("bloqueo")
        if isinstance(declarado, dict) and declarado.get("campos"):
            ids = [c.get("id") for c in declarado["campos"] if isinstance(c, dict)]
            self.stdout.write(f"  {tipo.codigo}: el bloqueo YA está declarado "
                              f"por la empresa: {ids}")
            self.stdout.write("  No se toca: esa lista la decidió alguien.")
            return

        self.stdout.write(f"  {tipo.codigo}: vigente es la v{vigente.version}")
        self.stdout.write("  hoy usa el mínimo genérico: 'motivo' (texto, "
                          "obligatorio) + 'necesita_de_noc' (texto, obligatorio)")

        campos = campos_del_bloqueo(elegidas)
        bloqueo = dict(declarado) if isinstance(declarado, dict) else {}
        bloqueo["campos"] = campos
        seguimiento["bloqueo"] = bloqueo
        esquema["seguimiento"] = seguimiento

        self.stdout.write("")
        self.stdout.write(f"  Los botones quedan: {campos[0]['reglas']['options']}")
        self.stdout.write("  Y el formulario: categoría (obligatoria) · "
                          "motivo (opcional) · qué se necesita del NOC "
                          "(obligatorio)")

        if not opciones["aplicar"]:
            self.stdout.write("")
            self.stdout.write(f"  SIMULACRO: se publicaría la v{vigente.version + 1}.")
            self.stdout.write("  Nada más del esquema cambia. Agregá --aplicar.")
            return

        #  NADA MÁS CAMBIÓ, Y SE MIDE  --  misma guarda que `permitir_otro`,
        #  por el mismo motivo: `componer` rechaza plantillas que el editor no
        #  sabe crear, así que no se puede recomponer para validar. Lo que sí
        #  se puede afirmar es que fuera de la rama del bloqueo el esquema es
        #  byte por byte el mismo.
        if _sin_el_bloqueo(esquema) != _sin_el_bloqueo(vigente.esquema or {}):
            raise CommandError(
                "el esquema nuevo difiere del vigente en algo más que el "
                "bloqueo: no se publica nada")

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
                          f"{org.id} --tipo {tipo.codigo} --aplicar")
        self.stdout.write("  Eso mueve solo las que nadie empezó.")
