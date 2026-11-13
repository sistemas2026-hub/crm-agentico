# -*- coding: utf-8 -*-
"""
================================================================================
 ¿CUANTAS ORDENES TIENEN UN REPORTE QUE NO EXPLICA SU TICKET?  --  12/11/2026
================================================================================
Pone, una al lado de la otra, lo que se PIDIO y lo que el tecnico REPORTO, de
las ultimas N ordenes. Una persona las lee y cuenta cuantas no cuadran.

POR QUE ESTE COMANDO EXISTE, Y POR QUE NO LO HACE EL MODELO
------------------------------------------------------------
El cotejo automatico (PRD §8.23) esta construido y **apagado**. Encenderlo
cuesta una llamada al modelo por cada cierre, y antes de pagar eso hay que
saber cuantas ordenes tienen el problema: si es 1 de 100, se paga por cada
cierre para encontrar una al mes.

CLAUDE.md §10: *medir antes de decidir, y dejar escrita la medicion*. Esta es
la medicion, y la hace una persona leyendo -- usar el modelo para decidir si
vale la pena usar el modelo seria pagar justo lo que se quiere evaluar, y
ademas daria por buena su respuesta sin tener con que compararla.

NO ESCRIBE NADA. Ni un evento, ni una fila, ni una llamada a ningun
proveedor. Solo lee.

SIN DATOS DEL CLIENTE, Y SIN LA PROSA DEL MODELO. Sale el numero de la
orden, el asunto, lo que se pidio y lo que el tecnico escribio. El nombre, el
telefono y la direccion del cliente NO; lo que el modelo escribio de las
fotos tampoco (eso es `por_que_no_cerro --con-texto`, con su advertencia).

OJO CON LO QUE SE LEE: el texto de las dos columnas lo escribieron personas
--un analista y un tecnico-- y puede mencionar a un cliente por su nombre.
La salida se pega en un chat; mirala antes.

Uso, dentro del contenedor del backend (desde /app):
  python manage.py cuantas_no_cuadran --org <uuid>
  python manage.py cuantas_no_cuadran --org <uuid> --ultimas 50
  python manage.py cuantas_no_cuadran --org <uuid> --ancho 100
================================================================================
"""
import textwrap

from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from common.tasks import set_rls_context

#: Cuantas mirar por defecto. Treinta se leen en unos minutos y alcanzan para
#: ver si el problema es de 1 de 100 o de 1 de 5. Mas que eso nadie las lee, y
#: una medicion que no se lee no es una medicion.
POR_DEFECTO = 30


def _envuelto(texto: str, ancho: int, sangria: str) -> str:
    limpio = " ".join(str(texto or "").split())
    if not limpio:
        return sangria + "(vacío)"
    return "\n".join(sangria + l for l in textwrap.wrap(limpio, ancho))


class Command(BaseCommand):
    help = ("Pone el ticket y el reporte del tecnico uno al lado del otro, "
            "para contar a mano cuantos no cuadran.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="UUID de la empresa")
        parser.add_argument("--ultimas", type=int, default=POR_DEFECTO,
                            help=f"Cuantas mirar (por defecto {POR_DEFECTO})")
        parser.add_argument("--ancho", type=int, default=92,
                            help="Ancho de linea para envolver el texto")

    def handle(self, *args, **opciones):
        from campo import revision_del_cierre as RC
        from campo.models import OrdenTrabajo

        try:
            org = Org.objects.get(pk=opciones["org"])
        except (Org.DoesNotExist, ValueError, TypeError):
            raise CommandError(f"No existe la empresa {opciones['org']!r}.")
        set_rls_context(org.id)

        ancho = max(40, int(opciones["ancho"]))
        #  LAS QUE YA TIENEN REPORTE, no las que estan en la calle: sin
        #  reporte no hay nada que cotejar y ocuparian la muestra.
        ordenes = list(
            OrdenTrabajo.objects
            .filter(org=org,
                    estado_operativo__in=[OrdenTrabajo.COMPLETADA_CAMPO,
                                          OrdenTrabajo.CERRADA])
            .select_related("tipo_trabajo_version__work_type")
            .order_by("-numero")[:max(1, int(opciones["ultimas"]))])

        if not ordenes:
            self.stdout.write("No hay órdenes terminadas en campo todavía.")
            return

        con_los_dos = 0
        sin_un_lado = 0

        self.stdout.write("=" * (ancho + 8))
        self.stdout.write(f"  {len(ordenes)} órdenes, de la más nueva a la "
                          f"más vieja. Empresa {org.id}")
        self.stdout.write("  Contá cuántas tienen un REPORTE que no explica "
                          "lo que se PIDIÓ.")
        self.stdout.write("=" * (ancho + 8))

        for o in ordenes:
            t = RC.el_ticket(o)
            cierre = RC._cierre_de_esta_vuelta(o)
            escrito = RC._lo_que_escribio_el_tecnico(o, cierre)
            #  TODO lo que el tecnico dejo escrito, no solo `solucion`: en el
            #  caso del 12/11 la contradiccion estaba en «que encontro».
            reporte = " · ".join(
                f"{k}: {v}" for k, v in sorted(escrito.items())
                if isinstance(v, (str, int, float)) and str(v).strip())

            if t["caso"] and reporte:
                con_los_dos += 1
            else:
                sin_un_lado += 1

            self.stdout.write("")
            self.stdout.write(f"OT #{o.numero}  [{o.estado_operativo}]  "
                              f"vuelta {o.vuelta}  ·  {t['asunto']}")
            self.stdout.write("  SE PIDIÓ")
            self.stdout.write(_envuelto(t["caso"], ancho, "    "))
            if t["diagnostico_previo"]:
                self.stdout.write("  YA SE HABÍA DIAGNOSTICADO")
                self.stdout.write(_envuelto(t["diagnostico_previo"], ancho,
                                            "    "))
            self.stdout.write("  QUÉ HIZO")
            self.stdout.write(_envuelto(reporte, ancho, "    "))
            self.stdout.write("  " + "-" * ancho)

        self.stdout.write("")
        self.stdout.write("=" * (ancho + 8))
        #  EL DENOMINADOR QUE IMPORTA. Una orden sin uno de los dos lados no
        #  puede contarse como «cuadra» ni como «no cuadra»: el cotejo
        #  automatico la deja en `no_se_sabe` sin llamar a nadie, asi que
        #  tampoco entra en la cuenta que decide si encenderlo.
        self.stdout.write(f"  Comparables (tienen los dos lados): {con_los_dos}")
        self.stdout.write(f"  Sin uno de los dos lados:           {sin_un_lado}")
        self.stdout.write("")
        self.stdout.write(f"  De esas {con_los_dos}, ¿cuántas NO cuadran? "
                          f"Ese es el número que decide.")
        self.stdout.write("=" * (ancho + 8))
