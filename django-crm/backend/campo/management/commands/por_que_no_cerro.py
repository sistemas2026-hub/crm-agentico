"""
================================================================================
 POR QUE NO CERRO  --  09/11/2026
================================================================================
Dice, para una orden que la pantalla muestra como «Se puede cerrar» y que sin
embargo sigue abierta, EN QUE PASO se cae. No escribe nada: ni un evento, ni
una transicion, ni una llamada al ISP.

POR QUE EXISTE
--------------
Entre que la pantalla calcula «Se puede cerrar» y que la orden quede cerrada
hay seis filtros, y ninguno deja rastro en la tarjeta:

  1. `puertas(org)`          -- delegacion y nivel de autonomia
  2. `RC.aplica(orden)`      -- completada en campo y sin validar
  3. la medicion pendiente   -- una falla de servicio sin medir espera
  4. el filtro de la vuelta  -- H4 y su refinamiento del 09/11
  5. `_reclamar`             -- un intento de hace menos de 60 minutos
  6. el ticket del ISP       -- lo que contesto el motor

El 08 y el 09/11 el mismo sintoma --«los siete puntos en verde y no cierra»--
salio dos veces por dos filtros distintos, y las dos veces se diagnostico
leyendo codigo en vez de la bitacora. Esto lee la bitacora.

SIN DATOS DEL CLIENTE. Numero de orden, estados, vuelta, tipos de evento y
fechas. De los `datos` de cada evento salen solo claves conocidas y cortas
(estado, codigo, ticket, vuelta, requisitos, veredicto); el resto se nombra
por su clave, sin su contenido, porque ahi vive el texto libre.

Uso, dentro del contenedor del backend (desde /app):
  python manage.py por_que_no_cerro --org <uuid>
  python manage.py por_que_no_cerro --org <uuid> --ot 212
================================================================================
"""
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context

BOGOTA = ZoneInfo("America/Bogota")

#: De los `datos` de un evento solo salen estas claves. Todo lo demas se
#: nombra sin su valor: ahi van `observacion` y los textos del tecnico.
CLAVES_SEGURAS = (
    "estado", "codigo", "ticket", "ticket_isp", "vuelta", "vuelta_nueva",
    "vuelta_anterior", "requisitos", "requisitos_a_corregir", "veredicto",
    "puntos", "estado_validacion_anterior", "estado_validacion_nuevo",
    "referencia", "detalle",
)

ORDEN_POR_DEFECTO = 3


def _hora(dt) -> str:
    return timezone.localtime(dt, BOGOTA).strftime("%d/%m %H:%M:%S")


def _datos(d: dict) -> str:
    if not isinstance(d, dict) or not d:
        return ""
    partes = []
    for k, v in d.items():
        if k in CLAVES_SEGURAS:
            partes.append(f"{k}={str(v)[:120]}")
        else:
            partes.append(f"{k}=<...>")
    return "  " + " ".join(partes)


class Command(BaseCommand):
    help = "Dice en que paso se cae una orden que deberia cerrar sola. No escribe nada."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="UUID de la empresa")
        parser.add_argument("--ot", type=int, action="append", default=[],
                            help="Numero de orden (repetible). Sin esto, las ultimas sin validar.")
        parser.add_argument("--ultimas", type=int, default=ORDEN_POR_DEFECTO,
                            help=f"Cuantas mirar cuando no se dice --ot (por defecto {ORDEN_POR_DEFECTO})")

    def handle(self, *args, **opciones):
        from datetime import timedelta

        from campo import revision_del_cierre as RC
        from campo import cierre_por_el_supervisor as CS
        from campo.models import EventoTrabajo, OrdenTrabajo
        from campo.services.cierre_en_isp import EVENTO_CERRADO, EVENTO_NO_CERRADO

        try:
            org = Org.objects.get(pk=opciones["org"])
        except (Org.DoesNotExist, ValueError, TypeError) as e:
            raise CommandError(f"No se encontro esa empresa ({type(e).__name__})")
        set_rls_context(org.id)

        ahora = timezone.now()
        base = OrdenTrabajo.objects.filter(org=org)
        if opciones["ot"]:
            ordenes = list(base.filter(numero__in=opciones["ot"]).order_by("-numero"))
            faltan = set(opciones["ot"]) - {o.numero for o in ordenes}
            if faltan:
                self.stdout.write(f"No existen en esta empresa: {sorted(faltan)}")
        else:
            ordenes = list(base.filter(
                estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
                estado_validacion__in=(OrdenTrabajo.PENDIENTE,
                                       OrdenTrabajo.REQUIERE_REVISION),
            ).order_by("-numero")[:max(1, opciones["ultimas"])])
        if not ordenes:
            self.stdout.write("No hay ordenes terminadas en campo esperando validacion.")
            return

        motivo_puertas = CS.puertas(org)
        self.stdout.write("")
        self.stdout.write(f"Hora de la empresa: {_hora(ahora)}  (Bogota)")
        self.stdout.write(
            "1. puertas(org): " + (f"CIERRA -> {motivo_puertas}" if motivo_puertas
                                   else "abierta (delegada y con nivel)"))

        pendientes = RC.pendientes_de_medir(org, ahora)
        if pendientes is None:
            self.stdout.write("   pendientes_de_medir: NO SE PUDO SABER -> no cierra ninguna")

        for orden in ordenes:
            self.stdout.write("")
            self.stdout.write("=" * 72)
            self.stdout.write(
                f"OT #{orden.numero}   operativo={orden.estado_operativo}   "
                f"validacion={orden.estado_validacion}   vuelta={orden.vuelta}")
            self.stdout.write("=" * 72)

            eventos = list(EventoTrabajo.objects.filter(org=org, orden=orden)
                           .order_by("created_at"))
            self.stdout.write(f"BITACORA ({len(eventos)} eventos)")
            for ev in eventos:
                self.stdout.write(f"  {_hora(ev.created_at)}  {ev.tipo}{_datos(ev.datos)}")

            self.stdout.write("")
            self.stdout.write("DONDE SE CAE")

            #  2. aplica
            if not RC.aplica(orden):
                self.stdout.write("  2. RC.aplica: NO -- no esta completada en campo "
                                  "sin validar. La pantalla tampoco la mostraria.")
                continue
            self.stdout.write("  2. RC.aplica: si")

            #  3. la medicion
            if pendientes is None:
                espera = "no se pudo saber"
            elif str(orden.id) in pendientes:
                espera = "SI espera la medicion despues del arreglo"
            else:
                espera = "no espera medicion"
            self.stdout.write(f"  3. medicion: {espera}")

            #  4. el filtro de la vuelta
            devuelta = EventoTrabajo.objects.filter(
                org=org, orden=orden, tipo=CS.EVENTO_DEVUELTA).exists()
            ticket_cerrado = EventoTrabajo.objects.filter(
                org=org, orden=orden, tipo=EVENTO_CERRADO).exists()
            pasa = orden.vuelta <= 1 or (devuelta and not ticket_cerrado)
            self.stdout.write(
                f"  4. filtro de la vuelta: {'pasa' if pasa else 'LA DEJA AFUERA'}"
                f"   (vuelta={orden.vuelta}, devuelta_por_el_supervisor={devuelta}, "
                f"ticket_isp_ya_cerrado={ticket_cerrado})")

            en_revisadas = CS.revisadas(org, ahora, solo=orden.pk)
            if en_revisadas is None:
                self.stdout.write("     revisadas(): None -- no cierra ninguna")
                continue
            if not en_revisadas:
                self.stdout.write("     revisadas(): VACIO -- esta orden no es candidata")
                continue
            _, revision = en_revisadas[0]
            self.stdout.write(f"     revisadas(): entra, veredicto={revision['veredicto']}")
            for p in revision["puntos"]:
                self.stdout.write(f"       [{p.get('ok')}] {p.get('clave')}: "
                                  f"{str(p.get('texto'))[:110]}")
            if revision.get("sugeridas"):
                self.stdout.write(f"     a rehacer: {revision['sugeridas']}")

            if revision["veredicto"] != RC.CERRAR:
                self.stdout.write("  -> No cierra porque la revision no la da por buena. "
                                  "Si hay algo a rehacer, se devuelve.")
                continue

            #  5. el reclamo. SOLO SE CONSULTA: reproducir el `create` de
            #  `_reclamar` aqui dejaria la orden trabada una hora por haber
            #  preguntado.
            desde = ahora - timedelta(minutes=CS.MINUTOS_ENTRE_INTENTOS)
            frenan = list(EventoTrabajo.objects.filter(
                org=org, orden=orden,
                tipo__in=(CS.EVENTO_BLOQUEADO, CS.EVENTO_INTENTO),
                created_at__gte=desde).order_by("created_at"))
            if frenan:
                cuales = ", ".join(f"{e.tipo} a las {_hora(e.created_at)}" for e in frenan)
                self.stdout.write(
                    f"  5. _reclamar: LA FRENA durante {CS.MINUTOS_ENTRE_INTENTOS} min -> {cuales}")
            else:
                self.stdout.write("  5. _reclamar: libre")

            #  6. el ticket, por lo que quedo escrito. No se le vuelve a
            #  preguntar al ISP: esto no habla con nadie.
            ultimos = [e for e in eventos if e.tipo in (
                EVENTO_CERRADO, EVENTO_NO_CERRADO, CS.EVENTO_BLOQUEADO,
                CS.EVENTO_DIVERGENCIA, CS.EVENTO_CERRADA)]
            if ultimos:
                e = ultimos[-1]
                self.stdout.write(f"  6. ticket del ISP, ultimo rastro: {e.tipo} "
                                  f"a las {_hora(e.created_at)}{_datos(e.datos)}")
            else:
                self.stdout.write("  6. ticket del ISP: sin rastro -- nunca se intento cerrar")
        self.stdout.write("")
