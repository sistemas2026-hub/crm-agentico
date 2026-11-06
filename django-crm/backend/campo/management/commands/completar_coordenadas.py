"""
Le pone el punto del cliente a las órdenes vivas que nacieron sin él.
Sin `--aplicar`, solo dice qué haría.

    python manage.py completar_coordenadas --org <id>            # simulacro
    python manage.py completar_coordenadas --org <id> --aplicar
    python manage.py completar_coordenadas --org <id> --limite 20

POR QUÉ EXISTE
--------------
Hasta el 05/11/2026 la orden solo guardaba `gps_lat`/`gps_lng` si quien
despachaba los tecleaba en el formulario. Una orden IMPORTADA del sistema del
ISP no pasa por ningún formulario, así que nacía siempre sin punto: el mapa
del Supervisor decía «sin ubicación» y el botón «Ruta GPS» de la app salía
deshabilitado, con el dato cargado del otro lado.

Desde esa fecha las órdenes nuevas lo traen (`campo.services.despacho`). Pero
la orden **congela** la ficha del cliente al crearse: las que ya existían no
se enteran nunca. Esto lo hace con EL MISMO parseo
(`campo.coordenadas_del_cliente.leer`), para que una orden vieja y una nueva
no puedan terminar con criterios distintos.

QUÉ TOCA, Y QUÉ NO
------------------
SOLO las vivas (asignada, en camino, en sitio, a corregir, detenida). Una
orden cerrada o cancelada no se visita: rellenarla no sirve a nadie y cambia
historia que ya quedó firmada.

SOLO las que NO tienen coordenadas. **Nunca pisa un punto existente**, y eso
es deliberado: quien despacha pudo corregir a mano una coordenada mal cargada
mirando el mapa, y este comando no puede distinguir esa corrección de un dato
viejo. Ante la duda, no toca.

SOLO las que tienen `cliente_id_abonado`: sin el identificador del servicio no
hay a quién preguntarle, y adivinar por nombre devuelve otro cliente.

LO QUE NO SE PUEDE ARREGLAR ACÁ, y se dice al final en vez de callarlo: un
cliente que no tiene coordenadas cargadas en el ISP sigue sin ellas. Eso no es
una falla de este comando -- es carga pendiente del otro lado.

PRIVACIDAD
----------
**No imprime ninguna coordenada.** Una coordenada es el domicilio de una
persona y esto se corre en una terminal cuya salida termina pegada en una
conversación. Imprime el número de orden y si quedó o no, nada más. Mismo
criterio que `cli/medir_coordenadas.py`.

El pedido va por el motor, con la herramienta del catálogo del tenant: la
credencial del ISP no pasa por este proceso.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common.models import Org
from common.tasks import set_rls_context


class Command(BaseCommand):
    help = "Completa las coordenadas de las órdenes vivas que no las tienen."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")
        parser.add_argument("--aplicar", action="store_true",
                            help="escribir (sin esto, solo dice qué haría)")
        parser.add_argument("--limite", type=int, default=0,
                            help="cuántas órdenes mirar como máximo (0 = todas)")

    def handle(self, *args, **options):
        from campo.coordenadas_del_cliente import leer
        from campo.dia_publicado import _activas
        from campo.models import OrdenTrabajo
        from operaciones.fuentes_adaptadores import _pedirle_al_motor

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, TypeError) as e:
            raise CommandError(f"No existe esa organización: {e}") from None

        set_rls_context(str(org.id))
        aplicar = options["aplicar"]
        limite = options["limite"] or 0

        candidatas = (OrdenTrabajo.objects
                      .filter(org=org, estado_operativo__in=_activas(),
                              gps_lat__isnull=True, gps_lng__isnull=True)
                      .exclude(cliente_id_abonado="")
                      .order_by("numero"))
        if limite:
            candidatas = candidatas[:limite]
        candidatas = list(candidatas)

        self.stdout.write(
            f"\n  {org.name}: {len(candidatas)} orden(es) viva(s) sin punto "
            f"y con identificador de servicio.")
        if not aplicar:
            self.stdout.write(
                "  SIMULACRO: no se escribe nada. Agregá --aplicar.")
        self.stdout.write("  No se imprime ninguna coordenada: solo el "
                          "resultado por orden.\n")

        puestas = sin_dato = ilegible = fallo = 0

        for orden in candidatas:
            servicio = str(orden.cliente_id_abonado or "").strip()
            try:
                crudo = _pedirle_al_motor(org, "consultar_cliente",
                                          {"id_servicio": servicio})
            except Exception as e:                           # noqa: BLE001
                #  El TIPO y no el texto: el texto de una excepción de red
                #  trae la URL, y la URL lleva el identificador del servicio.
                fallo += 1
                self.stdout.write(
                    f"    OT #{orden.numero:<6} no se pudo preguntar "
                    f"({type(e).__name__})")
                continue

            filas = crudo.get("results") if isinstance(crudo, dict) else None
            fila = (filas or [crudo if isinstance(crudo, dict) else {}])[0] or {}
            valor = fila.get("coordenadas") if isinstance(fila, dict) else None

            if valor is None or (isinstance(valor, str) and not valor.strip()):
                sin_dato += 1
                self.stdout.write(
                    f"    OT #{orden.numero:<6} el cliente no las tiene "
                    f"cargadas en el ISP")
                continue

            lat, lng = leer(valor)
            if lat is None or lng is None:
                #  Una forma que el parseo no reconoce. NO se aproxima: ver el
                #  encabezado de `coordenadas_del_cliente`.
                ilegible += 1
                self.stdout.write(
                    f"    OT #{orden.numero:<6} las tiene, pero con una forma "
                    f"que no se reconoce: queda sin punto")
                continue

            if aplicar:
                with transaction.atomic():
                    #  Se vuelve a exigir que siga vacía DENTRO de la
                    #  transacción: entre el listado y esta línea alguien pudo
                    #  despacharla de nuevo o corregirla a mano, y este
                    #  comando no pisa un punto que puso una persona.
                    escritas = (OrdenTrabajo.objects
                                .filter(pk=orden.pk, gps_lat__isnull=True,
                                        gps_lng__isnull=True)
                                .update(gps_lat=lat, gps_lng=lng))
                if not escritas:
                    self.stdout.write(
                        f"    OT #{orden.numero:<6} ya tenía punto cuando se "
                        f"fue a escribir: no se pisa")
                    continue

            puestas += 1
            self.stdout.write(
                f"    OT #{orden.numero:<6} "
                f"{'punto puesto' if aplicar else 'tendría punto'}")

        self.stdout.write(
            f"\n  {'PUESTAS' if aplicar else 'SE PONDRIAN'}: {puestas}"
            f"   ·  sin dato en el ISP: {sin_dato}"
            f"   ·  forma no reconocida: {ilegible}"
            f"   ·  no se pudo preguntar: {fallo}\n")

        if sin_dato:
            self.stdout.write(
                f"  Las {sin_dato} sin dato NO son una falla de este comando: "
                f"son clientes\n  sin coordenadas cargadas en el ISP. Se "
                f"arreglan cargándolas allá.\n")
        if ilegible:
            self.stdout.write(
                f"  Las {ilegible} con forma no reconocida valen una mirada: "
                f"puede haber un\n  formato que todavía no se midió. Ver "
                f"`campo/coordenadas_del_cliente.py`.\n")
