"""
Lista, sin escribir nada, cómo ve el Supervisor cada caso de la cola de
Despacho: qué grupo leyó, qué labor sale de ahí, con qué plantilla iría, si es
una obra de red, de dónde sale su barrio, en qué zona cae, y (26/10/2026) el
nivel de su asunto y la prioridad con la que saldría su orden.

    python manage.py informe_de_despacho --org <id>

POR QUÉ EXISTE (25/10/2026)
---------------------------
El usuario pidió que el Supervisor identifique solo la labor (soporte o
trabajos) y la zona de cada ticket. La auditoría de ese día midió que la
labor que anota el clasificador al leer el ticket sale vacía para casi todo
en producción, y que tres casos («PROYECTO DE AMPLIACION», «INTERVENCION
CTO», «Paginas Bloqueadas») quedaban sin labor porque su grupo no está en la
tabla. Antes de cambiar cómo lee el Supervisor hay que ver, caso por caso, qué
leyó: CLAUDE.md §10, medir antes de decidir.

SIN DATOS DEL CLIENTE. Va el número del ticket y lo que el Supervisor
calculó: nunca el asunto, la descripción, el nombre ni el teléfono. El barrio
sí, porque es justo lo que se mide (es un nombre de barrio, no una dirección).
Es una salida pensada para pegarse en una conversación.

EL CONTEXTO RLS SE FIJA ACÁ, como en 'informe_de_pendientes': un comando no
pasa por el middleware, y sin él las tablas devuelven 0 filas sin error.
"""

from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from common.models import Org
from common.tasks import set_rls_context

_GRUPO = {
    "falla_de_servicio": "falla",
    "trabajo_pedido": "trabajo",
    "obra_de_red": "obra",
    "nada_lo_mide": "nada_mide",
    "ni_cliente_ni_red": "ni_cli_red",
}


class Command(BaseCommand):
    help = ("Lista cómo ve el Supervisor cada caso de Despacho: grupo, labor, "
            "plantilla, obra, barrio y zona. No escribe nada.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")

    def handle(self, *args, **options):
        from django.utils import timezone

        from campo import niveles as N
        from campo import plantillas as P
        from campo.cuadrillas import labor_de_cada_grupo, onus_para_corte_de_red
        from campo.reparto import _zona_de
        from campo.zonas import AliasDeZona, MapaDeBarrios, normalizar_localidad
        from cases.models import Case
        from operaciones import armado_de_jornadas as adj
        from operaciones import ordenes_de_despacho as O
        from operaciones import paso_a_despacho as pad
        from operaciones import ubicacion_del_caso as ub

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        set_rls_context(org.id)

        propuestas = adj.propuestas_en_despacho(org)
        casos = {str(c.id): c for c in Case.objects.filter(
            org=org, id__in=list(propuestas))}
        labores = labor_de_cada_grupo(org)
        ofrecidas = P.plantillas_que_se_ofrecen(org)
        zona_de_barrio = MapaDeBarrios({
            a.localidad: a.zona.nombre
            for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
            .select_related("zona")})
        buscables = ub.preparar(zona_de_barrio)
        umbral = onus_para_corte_de_red(org.id)
        nivel_de = N.lector_de_niveles(org)
        zona_horaria = _zona_de(org)
        hoy = timezone.now().astimezone(zona_horaria).date()

        filas = []
        por_grupo, sin_labor, obras = Counter(), Counter(), Counter()
        por_nivel = Counter()
        for caso_id, p in propuestas.items():
            caso = casos.get(caso_id)
            if caso is None:
                continue
            lectura = pad._ultima_lectura_con_grupo(p) or {}
            grupo = str(lectura.get("grupo") or "")
            corte = pad.es_corte_de_red(pad.ultima_medicion(p), umbral)
            labor = adj.labor_del_caso(p, labores, es_corte=corte) or ""
            elegida = P.plantilla_del_caso(
                org, labor=labor, asunto=caso.name or "",
                labor_medida=bool(adj.labor_de_la_visita(p)), ofrecidas=ofrecidas)
            obra = ub.es_obra_de_red(lectura, es_corte=corte)
            barrio, de_donde = ub.barrio_del_caso(
                normalizar_localidad(
                    (adj.localidad_guardada(p) or {}).get("localidad") or ""),
                f"{caso.name or ''} {caso.description or ''}",
                es_obra=obra, buscables=buscables)
            plantilla = (f"{elegida['version'].work_type.nombre} "
                         f"({elegida['por']})" if elegida["version"]
                         else f"— ({elegida['motivo']})")
            nivel = nivel_de(caso.name or "")
            por_nivel[(nivel or {}).get("nivel") or "sin nivel"] += 1
            prioridad = O.prioridad_del_caso(
                caso.created_at, nivel=nivel,
                plazo_de_la_plantilla=(elegida["version"].work_type.plazo_dias
                                       if elegida["version"] else None),
                caido=O.equipo_medido_caido(p), hoy=hoy, zona=zona_horaria)
            por_grupo[_GRUPO.get(grupo, grupo or "sin grupo")] += 1
            if not labor:
                sin_labor[_GRUPO.get(grupo, grupo or "sin grupo")] += 1
            if obra:
                obras["con barrio" if barrio else "sin barrio"] += 1
            filas.append((
                (caso.external_ticket_id or "").strip() or "—",
                _GRUPO.get(grupo, grupo or "—"),
                labor or "—",
                str(lectura.get("labor") or "—"),
                plantilla,
                "sí" if obra else "",
                f"{barrio or '—'} [{de_donde or '—'}]",
                zona_de_barrio.get(barrio, "—") if barrio else "—",
                (nivel or {}).get("nivel") or "—",
                prioridad,
            ))

        cab = ("ticket", "grupo", "labor", "labor leída", "plantilla",
               "obra", "barrio [de]", "zona", "nivel", "prioridad")
        anchos = [max(len(str(x)) for x in col) for col in zip(cab, *filas)] \
            if filas else [len(c) for c in cab]
        linea = "  ".join(f"{{:<{a}}}" for a in anchos)
        self.stdout.write(linea.format(*cab))
        for f in sorted(filas, key=lambda x: (x[1], x[0])):
            self.stdout.write(linea.format(*f))
        self.stdout.write("")
        self.stdout.write(f"casos en Despacho: {len(filas)}")
        self.stdout.write("por grupo: " + ", ".join(
            f"{g} {n}" for g, n in sorted(por_grupo.items())))
        self.stdout.write("sin labor, por grupo: " + (", ".join(
            f"{g} {n}" for g, n in sorted(sin_labor.items())) or "ninguno"))
        self.stdout.write("obras de red: " + (", ".join(
            f"{k} {n}" for k, n in sorted(obras.items())) or "ninguna"))
        self.stdout.write("por nivel del asunto: " + ", ".join(
            f"{k} {n}" for k, n in sorted(por_nivel.items())))
