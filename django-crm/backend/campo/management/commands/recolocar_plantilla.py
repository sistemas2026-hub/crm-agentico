"""
Mueve órdenes ABIERTAS a otra plantilla, cuando la que se eligió no era.
Sin `--aplicar`, solo dice qué haría.

    python manage.py recolocar_plantilla --org <id> --de <codigo> --a <codigo>
    python manage.py recolocar_plantilla --org <id> --de <codigo> --a <codigo> --texto "problema de tv"
    python manage.py recolocar_plantilla --org <id> --de <codigo> --a <codigo> --aplicar

POR QUÉ EXISTE
--------------
La plantilla decide qué fotos y qué datos se le piden al técnico, y la orden
la **congela** al nacer: cambiar la configuración después no la toca. Así que
una orden despachada con la plantilla equivocada sigue pidiendo lo que esa
plantilla pide -- y si exige una foto que ese trabajo no necesita, **no se
puede cerrar**: el servidor la rechaza con 400 (`views.py:1290`,
`verificar_checklist_completo`), no solo la app.

El caso real (06/11/2026): todos los tickets caían en «Soporte en campo»
--una plantilla de correctivo de fibra-- porque los asuntos de «problema de
TV» y «cambio de contraseña» no estaban cargados en ninguna otra. Esa
plantilla exige la medición de potencia óptica, que en un cambio de
contraseña del wifi no significa nada. El técnico quedaba trabado en la calle.

Cargar los asuntos en las plantillas correctas arregla los tickets NUEVOS.
Esto arregla los que ya salieron.

QUÉ NO ROMPE, Y POR QUÉ IMPORTA
--------------------------------
**El esquema de cada plantilla sigue intacto.** No se edita ninguna versión
publicada --eso está prohibido en código (`models.py:95-117`) y es lo que
hace que «qué se le pidió a esta orden» se conteste leyendo una fila que
nadie pudo tocar--. Lo único que cambia es a CUÁL de esas filas apunta la
orden, y queda escrito en un `EventoTrabajo` con quién, cuándo, de dónde y a
dónde.

SOLO LAS ABIERTAS. Una orden completada o cerrada no se toca: nadie va a
volver a esa casa, y cambiarle la plantilla reescribiría la historia de un
trabajo que ya se revisó.

LAS FOTOS QUE QUEDAN HUÉRFANAS SE DICEN ANTES, NO DESPUÉS. Si el técnico ya
subió la «Medición al llegar» y la plantilla nueva no la pide, esa evidencia
queda sin requisito que la reclame. No se borra --es trabajo que alguien
hizo-- pero el simulacro lo nombra para que la decisión se tome sabiéndolo.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common.models import Org
from common.tasks import set_rls_context


def _como_se_filtro(numeros, texto) -> str:
    """Qué se usó para elegir las órdenes, dicho en la cabecera.

    QUE DIGA «NINGUNO» CUANDO NO HAY FILTRO ES EL PUNTO: sin eso, quien corre
    el comando sin `--numeros` ni `--texto` ve una lista larga y puede creer
    que filtró algo. Son TODAS las abiertas de esa plantilla.
    """
    if numeros:
        return f"números {','.join(numeros)} (exacto)"
    if texto:
        return f"texto {texto!r} — aproximado, revisá la lista"
    return "NINGUNO: todas las abiertas de esa plantilla"


class Command(BaseCommand):
    help = "Mueve órdenes abiertas a otra plantilla, con su registro."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")
        parser.add_argument("--de", required=True,
                            help="código de la plantilla que se eligió mal")
        parser.add_argument("--a", required=True,
                            help="código de la plantilla que corresponde")
        parser.add_argument("--numeros", default="",
                            help="números de orden separados por coma: el "
                                 "filtro EXACTO. Ej: 42,44,116")
        parser.add_argument("--texto", default="",
                            help="solo las órdenes cuyo RESUMEN contenga esto. "
                                 "SIRVE PARA MIRAR, no para aplicar: usá "
                                 "--numeros con lo que el simulacro te muestre")
        parser.add_argument("--aplicar", action="store_true",
                            help="escribir (sin esto, solo dice qué haría)")

    def handle(self, *args, **options):
        from campo.dia_publicado import _activas
        from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                                  WorkType, WorkTypeVersion)

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValidationError, ValueError, TypeError):
            #  ValidationError TAMBIEN: Django la lanza ANTES de consultar
            #  cuando el texto no es un UUID. Sin atraparla el comando escupe
            #  40 lineas de traza en vez de decir que el id esta mal -- ya
            #  paso con `recalcular_atencion_fotos` (05/11/2026), y la prueba
            #  de este lo encontro antes de que le pasara a nadie.
            raise CommandError(
                f"{options['org']!r} no es una organización válida. Para "
                f"verlas:\n  python manage.py shell -c \"from common.models "
                f"import Org; [print(o.id, o.name) for o in Org.objects.all()]\""
            ) from None

        set_rls_context(str(org.id))
        aplicar = options["aplicar"]
        asunto = (options["texto"] or "").strip()

        destino = self._ultima_publicada(org, options["a"], WorkType,
                                         WorkTypeVersion)
        origen_wt = WorkType.objects.filter(org=org, codigo=options["de"]).first()
        if origen_wt is None:
            raise CommandError(f"No existe la plantilla '{options['de']}' en "
                               f"{org.name}.")

        #  `org=org` ES REDUNDANTE Y SE QUEDA, MEDIDO (06/11/2026). Una
        #  mutacion que lo quitaba SOBREVIVIO, y el motivo es bueno:
        #  `tipo_trabajo_version__work_type=origen_wt` ya limita a esta
        #  empresa --ese WorkType es suyo, y una orden ajena apunta a otro--,
        #  y ademas RLS esta puesto arriba. Son tres redes para lo mismo.
        #
        #  Se queda igual porque es la unica de las tres que se lee de un
        #  vistazo: quien venga a cambiar este filtro tiene que ver que esto
        #  es por empresa ANTES de tocarlo, no deducirlo de un join.
        candidatas = (OrdenTrabajo.objects
                      .filter(org=org,
                              estado_operativo__in=_activas(),
                              tipo_trabajo_version__work_type=origen_wt)
                      .select_related("tipo_trabajo_version")
                      .order_by("numero"))
        #  POR NUMERO, QUE ES EXACTO (06/11/2026). El filtro por texto se
        #  midio en produccion el mismo dia que se escribio: buscar "tv" en el
        #  resumen trajo DIEZ ordenes y solo cuatro eran de television. Las
        #  otras: un traslado de abonado, una derivacion a Comercial y tres
        #  instalaciones. Aplicarlo habria movido un traslado a la plantilla
        #  de TV, y nadie lo habria notado hasta que el tecnico llegara.
        #
        #  El texto libre sirve para MIRAR; para escribir hace falta el
        #  numero. Por eso este filtro va primero y, cuando esta, el de texto
        #  ni se mira.
        numeros = [n.strip() for n in (options["numeros"] or "").split(",")
                   if n.strip()]
        if numeros:
            try:
                enteros = [int(n) for n in numeros]
            except ValueError:
                raise CommandError(
                    f"--numeros lleva numeros separados por coma. "
                    f"Recibi: {options['numeros']!r}") from None
            candidatas = candidatas.filter(numero__in=enteros)
        elif asunto:
            #  EL RESUMEN, que es donde vive el texto del ticket en la
            #  orden: `OrdenTrabajo` no tiene `asunto` --lo supuse al
            #  escribir esto y la prueba lo corrigio--. `origen_ref` apunta
            #  al caso, y el asunto vive alla.
            candidatas = candidatas.filter(resumen__icontains=asunto)
        candidatas = list(candidatas)

        pide_destino = {
            e.get("id") for e in (destino.esquema or {}).get("evidencias", [])
            if e.get("id")}

        self.stdout.write(
            f"\n  {org.name}\n"
            f"  de  : {origen_wt.nombre} ({origen_wt.codigo})\n"
            f"  a   : {destino.work_type.nombre} ({destino.work_type.codigo}) "
            f"v{destino.version}\n"
            f"  filtro: {_como_se_filtro(numeros, asunto)}\n"
            f"  órdenes abiertas que se moverían: {len(candidatas)}\n")
        if asunto and not numeros and options["aplicar"]:
            #  SE AVISA Y NO SE BLOQUEA: puede ser legítimo --un texto bien
            #  elegido-- pero el caso medido dice que conviene mirar la lista
            #  primero. Bloquearlo sería decidir por quien conoce sus tickets.
            self.stdout.write(
                "  OJO: estás aplicando con un filtro de TEXTO. Medido el\n"
                "  06/11/2026: buscar «tv» trajo 10 órdenes y 4 eran de TV.\n"
                "  Corré el simulacro, mirá los resúmenes y aplicá con\n"
                "  --numeros sobre las que de verdad correspondan.\n")
        if not aplicar:
            self.stdout.write("  SIMULACRO: no se escribe nada. "
                              "Agregá --aplicar.\n")

        movidas = huerfanas_total = 0

        for orden in candidatas:
            #  LAS QUE QUEDARÍAN HUÉRFANAS, dichas ANTES: una evidencia cuyo
            #  requisito no existe en la plantilla nueva. No se borra --es
            #  trabajo que alguien hizo-- pero nadie la va a reclamar.
            huerfanas = [
                ev.requisito_id for ev in EvidenciaTrabajo.objects.filter(
                    org=org, orden_trabajo=orden, vuelta=orden.vuelta)
                if ev.requisito_id not in pide_destino]

            if aplicar:
                with transaction.atomic():
                    #  Se vuelve a exigir el estado DENTRO de la transacción:
                    #  entre listar y escribir el técnico pudo completarla, y
                    #  una orden terminada no se toca.
                    escritas = (OrdenTrabajo.objects
                                .filter(pk=orden.pk,
                                        estado_operativo__in=_activas())
                                .update(tipo_trabajo_version=destino))
                    if not escritas:
                        self.stdout.write(
                            f"    OT #{orden.numero:<6} se terminó mientras "
                            f"corría: no se toca")
                        continue
                    #  EL REGISTRO, append-only: sin esto, «por qué esta orden
                    #  cambió de plantilla» no tendría respuesta.
                    EventoTrabajo.objects.create(
                        org=org, orden=orden, tipo="plantilla_recolocada",
                        datos={
                            "de": origen_wt.codigo,
                            "de_version": orden.tipo_trabajo_version.version,
                            "a": destino.work_type.codigo,
                            "a_version": destino.version,
                            "motivo": "la plantilla elegida pedía evidencias "
                                      "que este trabajo no necesita",
                            "evidencias_huerfanas": huerfanas,
                            "por": "recolocar_plantilla",
                        })

            movidas += 1
            huerfanas_total += len(huerfanas)
            aviso = (f"   · {len(huerfanas)} foto(s) quedan sin requisito"
                     if huerfanas else "")
            #  EL RESUMEN, EN EL SIMULACRO: sin verlo no se puede decidir si
            #  esa orden de verdad corresponde. Lo pidió el caso medido del
            #  06/11/2026 -- la lista decía «OT #176 se movería» y recién
            #  mirando el texto se veía que era un traslado de abonado, no un
            #  trabajo de televisión.
            texto = (orden.resumen or "").replace("\n", " ").strip()[:70]
            self.stdout.write(
                f"    OT #{orden.numero:<6} "
                f"{'movida' if aplicar else 'se movería'}{aviso}"
                + (f"\n               {texto}" if texto and not aplicar else ""))

        self.stdout.write(
            f"\n  {'MOVIDAS' if aplicar else 'SE MOVERÍAN'}: {movidas}"
            f"   ·  fotos que quedarían sin requisito: {huerfanas_total}\n")
        if huerfanas_total:
            self.stdout.write(
                "  Esas fotos NO se borran: siguen en la orden y en la\n"
                "  auditoría. Lo que cambia es que la plantilla nueva no las\n"
                "  pide, así que no bloquean el cierre ni se muestran como\n"
                "  faltantes.\n")

    def _ultima_publicada(self, org, codigo, WorkType, WorkTypeVersion):
        """La versión publicada más alta de esa plantilla.

        Se exige PUBLICADA: una borrador puede cambiar debajo del técnico, y
        es la misma regla que aplica `crear_orden`.
        """
        wt = WorkType.objects.filter(org=org, codigo=codigo).first()
        if wt is None:
            raise CommandError(
                f"No existe la plantilla '{codigo}' en {org.name}. Para ver "
                f"las que hay:\n  python manage.py informe_de_labores --org "
                f"{org.id}")
        v = (WorkTypeVersion.objects
             .filter(work_type=wt, estado=WorkTypeVersion.PUBLICADA)
             .order_by("-version").first())
        if v is None:
            raise CommandError(
                f"La plantilla '{codigo}' no tiene ninguna versión PUBLICADA. "
                f"Publicala en /supervisor-noc/plantillas antes de mover nada.")
        return v
