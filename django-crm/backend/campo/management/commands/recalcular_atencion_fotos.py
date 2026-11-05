"""
Vuelve a decidir, con el criterio de hoy, qué análisis de foto piden que una
persona los mire. Sin `--aplicar`, solo dice qué cambiaría.

    python manage.py recalcular_atencion_fotos --org <id>            # simulacro
    python manage.py recalcular_atencion_fotos --org <id> --aplicar

POR QUÉ EXISTE
--------------
Entre que se encendió el análisis de evidencias (03/11/2026) y el arreglo del
05/11, el detector buscaba palabras que la propia instrucción le PIDE al
modelo escribir --«borroso», «no se ve», «no se puede», «tapado», «fuera de
cuadro»--. Resultado medido en la OT 100: **4 de 4 fotos pedían una mirada**,
y así en todas las órdenes.

Esas filas quedaron escritas. La revisión del cierre las lee tal cual, así
que esas órdenes siguen en «Revisalo antes de cerrar» --y el cierre autónomo
exige «Se puede cerrar»-- aunque el defecto ya esté arreglado. Esto las pone
al día.

NO BORRA NI REESCRIBE EL TEXTO
-------------------------------
Lo único que toca es `pide_atencion`, y lo RECALCULA con `_pide_atencion`
sobre el texto que ya está guardado: no lo pone en `False` a lo bruto. Una
foto cuyo análisis sí nombra un defecto --«el equipo está sin fijar»-- sigue
marcada. Poner todo en `False` habría tapado las de verdad junto con el ruido.

Los análisis viejos no traen la marca `ATENCION:` --es posterior-- así que
caen al respaldo por palabras, que es justamente el que quedó limpio. Es la
misma función que corre al analizar una foto nueva: no hay un segundo
criterio que se pueda quedar viejo.

APPEND-ONLY, CON UNA EXCEPCIÓN DICHA
-------------------------------------
`AnalisisDeEvidencia` es append-only por diseño: la corrección de una persona
es una fila nueva, nunca un UPDATE, porque sin el par (lo que dijo la IA, lo
que dijo la persona) no hay con qué medir si acierta.

Esto SÍ hace UPDATE, y la diferencia importa: no está corrigiendo el juicio
del modelo --el `texto` no se toca-- sino un campo que escribió el CÓDIGO y
que el código calculaba mal. El par que el dataset necesita queda intacto.
"""

from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from common.tasks import clear_rls_context, set_rls_context


class Command(BaseCommand):
    help = "Recalcula qué análisis de foto piden una mirada, con el criterio de hoy."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--aplicar", action="store_true",
                            help="escribir (sin esto, solo dice qué haría)")

    def handle(self, *args, **options):
        from campo.models import AnalisisDeEvidencia
        from campo.tasks import _pide_atencion

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, TypeError):
            raise CommandError(f"No existe la organización {options['org']!r}.")

        aplicar = options["aplicar"]
        try:
            #  El contexto antes de leer: estas tablas tienen RLS, y sin esto
            #  la consulta devuelve cero filas y el comando diría «no hay
            #  nada» cuando lo que pasa es que no pudo verlas.
            set_rls_context(org.id)

            #  Solo lo que escribió la IA. Una corrección de una persona no
            #  se recalcula: su `pide_atencion` es un juicio humano.
            filas = list(AnalisisDeEvidencia.objects.filter(
                org=org, origen=AnalisisDeEvidencia.IA).only(
                    "id", "texto", "pide_atencion"))

            cambian = []
            for f in filas:
                ahora = _pide_atencion(f.texto)
                if ahora != f.pide_atencion:
                    cambian.append((f, ahora))

            self.stdout.write(f"  análisis de la IA        : {len(filas)}")
            self.stdout.write(f"  marcados hoy             : "
                              f"{sum(1 for f in filas if f.pide_atencion)}")
            self.stdout.write(f"  cambian                  : {len(cambian)}")
            self.stdout.write(f"    de «pide mirada» a «no»: "
                              f"{sum(1 for _, a in cambian if not a)}")
            self.stdout.write(f"    de «no» a «pide mirada»: "
                              f"{sum(1 for _, a in cambian if a)}")

            if not cambian:
                self.stdout.write(self.style.SUCCESS(
                    "\n  Nada que cambiar: el criterio de hoy coincide con lo guardado."))
                return
            if not aplicar:
                self.stdout.write(
                    "\n  SIMULACRO: no se escribió nada. Con --aplicar se escribe.")
                return

            for f, ahora in cambian:
                f.pide_atencion = ahora
            AnalisisDeEvidencia.objects.bulk_update(
                [f for f, _ in cambian], ["pide_atencion"])

            #  SE AFIRMA SOBRE LO QUE QUEDÓ, releído de la base.
            quedan = AnalisisDeEvidencia.objects.filter(
                org=org, origen=AnalisisDeEvidencia.IA, pide_atencion=True).count()
            self.stdout.write(self.style.SUCCESS(
                f"\n  [OK] {len(cambian)} actualizados. "
                f"Siguen pidiendo una mirada: {quedan}."))
        finally:
            #  De SESIÓN, y la conexión vuelve al pool.
            clear_rls_context()
