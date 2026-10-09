# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA PANTALLA DE DESPACHO NECESITA PARA EXISTIR
================================================================================

POR QUE HACIA FALTA
-------------------
`POST /campo/trabajos/crear/` existia desde siempre y **nadie lo llamaba**:
verificado el 09/10/2026 en los cuatro lugares posibles --frontend, app movil,
motor y scripts-- sin una sola referencia. Las ordenes de trabajo solo se
podian crear por API directa.

Eso dejaba el circuito cortado justo al principio: el ciclo de la madrugada
reparte ordenes, la clasificacion propone su tipo, y nada de eso se ejercita si
no hay por donde decir «este caso va a campo».

Dos lecturas, y ninguna escribe:

    GET /campo/plantillas-de-trabajo/   con que se puede despachar
    GET /campo/casos-despachables/      que casos esperan, y que dice la
                                        evidencia de cada uno

El despacho en si sigue siendo `trabajos/crear/`, que ya existia y ya tiene su
idempotencia. Aca no se duplica nada de eso.

LA SUGERENCIA NO ELIGE
----------------------
`casos-despachables` devuelve la labor que la evidencia sostiene y POR QUE,
pero no decide: quien despacha ve el porque escrito y acepta o cambia. Es el
mismo corte que el resto del Supervisor NOC -- observa, analiza, propone.

Y la sugerencia es una LABOR, no una plantilla. Entre dos plantillas de la
misma labor la diferencia la sabe quien despacha, no esto.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.permissions import IsCampoAuthenticated


class PlantillasDeTrabajoView(APIView):
    """``GET`` con que se puede despachar hoy.

    Solo las PUBLICADAS: una borrador puede cambiar debajo del tecnico, y
    `despachar()` ya las rechaza -- ofrecerlas en la pantalla seria dejar que
    alguien eligiera algo que va a fallar al enviar.

    Cada una viaja con la LABOR de su tipo de trabajo, que es lo que permite
    marcar cual coincide con la sugerencia sin que la pantalla reconstruya esa
    relacion por su cuenta.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        qs = (
            WorkTypeVersion.objects
            .filter(work_type__org=org, work_type__activo=True,
                    estado=WorkTypeVersion.PUBLICADA)
            .select_related("work_type")
            .order_by("work_type__codigo", "-version")
        )

        #  UNA POR TIPO: la version publicada mas alta. Ofrecer todas las
        #  versiones publicadas de un mismo tipo obligaria a quien despacha a
        #  elegir entre dos cosas que para el son la misma, y la vieja solo
        #  sirve para auditar lo ya despachado.
        vistas, plantillas = set(), []
        for v in qs:
            if v.work_type_id in vistas:
                continue
            vistas.add(v.work_type_id)
            plantillas.append({
                "id": str(v.id),
                "version": v.version,
                "codigo": v.work_type.codigo,
                "nombre": v.work_type.nombre,
                "labor": v.work_type.labor,
                #  Cuantos requisitos trae: quien despacha puede anticipar que
                #  le va a pedir al tecnico sin abrir la plantilla.
                "requisitos": len((v.esquema or {}).get("campos") or []),
            })

        return Response({
            "plantillas": plantillas,
            "labores": [{"id": v, "texto": n} for v, n in WorkType.LABORES],
            #  Las que no tienen labor NO las puede repartir el ciclo de la
            #  madrugada. Se dice aca para que el aviso aparezca donde se
            #  despacha, no solo en la pantalla de configuracion.
            "sin_clasificar": sum(1 for p in plantillas if not p["labor"]),
        })


def _orden_activa_de(org, case_id: str):
    """La orden viva de ese caso, si ya tiene una.

    NO bloquea el despacho: una segunda visita al mismo caso es legitima --el
    tecnico fue y falto un material, o el cliente no estaba-- y lo que evita el
    duplicado accidental es la `Idempotency-Key`. Pero quien despacha tiene que
    VERLO antes, que es distinto de que el sistema decida por el.
    """
    return (
        OrdenTrabajo.objects
        .filter(org=org, origen_sistema="crm", origen_ref=str(case_id))
        .exclude(estado_operativo__in=[OrdenTrabajo.CERRADA,
                                       OrdenTrabajo.CANCELADA])
        .values_list("numero", flat=True)
        .first()
    )


class CasosDespachablesView(APIView):
    """``GET`` los casos abiertos que podrian ir a campo, con su evidencia.

    SOLO LOS QUE UNA PERSONA YA APROBO. El Supervisor detecta que un caso
    necesita visita --`CASO_REQUIERE_VISITA`, y solo cuando la MEDICION lo
    sostiene-- alguien acepta esa propuesta en «Pendientes por revision», y
    recien ahi el caso llega aca.

    Hasta el 09/10/2026 se listaban todos los casos abiertos, y eso dejaba al
    Supervisor de decorado: proponia, pero cualquier caso se podia despachar
    igual. Ahora nada sale a campo sin el visto de alguien.

    Y SIGUE SIN DECIDIR cual se despacha: que un caso aprobado se mande hoy o
    mañana, con que plantilla y con que prioridad, lo elige quien mira. Lo que
    hace esto es juntar lo que hay que ver para decidirlo, en vez de obligar a
    abrir tres pantallas por caso.
    """

    permission_classes = [IsCampoAuthenticated]

    #: Cuantos casos se traen de una. No es una preferencia: cada uno pide la
    #: ficha tecnica al motor, y eso es una llamada de red por caso. Treinta
    #: pantallas de scroll no las mira nadie, y treinta llamadas si las paga
    #: quien espera.
    TOPE = 25

    def get(self, request):
        from cases.models import Case

        org = request.profile.org
        con_ficha = request.query_params.get("ficha") == "1"

        #  SOLO LO QUE UNA PERSONA YA APROBO.
        #
        #  Hasta el 09/10/2026 esta pantalla listaba TODOS los casos abiertos, y
        #  eso convertia al Supervisor en decorado: proponia, pero cualquier
        #  caso se podia despachar igual. Ahora el flujo es uno solo --el
        #  Supervisor detecta que un caso necesita visita, una persona lo
        #  acepta, y recien ahi llega aca-- asi que nada sale a campo sin pasar
        #  por el visto de alguien.
        #
        #  ACEPTADA y MODIFICADA, no RECHAZADA: modificar es aceptar cambiando
        #  algo, rechazar es decir que no. Tratar las tres como "revisadas"
        #  --que es como `ESTADOS_REVISADOS` las agrupa para OTRA pregunta--
        #  traeria justo las que alguien decidio que no van.
        from operaciones.models import PropuestaSupervisor

        aprobados = set(
            PropuestaSupervisor.objects
            .filter(org=org,
                    tipo_senal=PropuestaSupervisor.CASO_REQUIERE_VISITA,
                    estado__in=(PropuestaSupervisor.ACEPTADA,
                                PropuestaSupervisor.MODIFICADA),
                    origen_tipo="case")
            .values_list("origen_id", flat=True)
        )
        if not aprobados:
            #  Vacio NO es un error, y se distingue: "todavia nadie aprobo
            #  ninguno" y "no se pudo leer" se dibujan distinto.
            return Response({"casos": [], "tope": self.TOPE,
                             "sin_aprobados": True})

        qs = (
            Case.objects
            .filter(org=org, is_active=True, is_sample=False,
                    merged_into__isnull=True, id__in=aprobados)
            .exclude(status="Closed")
            .order_by("-created_at")[:self.TOPE]
        )

        casos = []
        for caso in qs:
            fila = {
                "id": str(caso.id),
                "nombre": caso.name,
                "estado": caso.status,
                "prioridad": caso.priority,
                "creado": caso.created_at.isoformat() if caso.created_at else None,
                "servicio": (caso.external_service_id or "").strip(),
                "ticket": (caso.external_ticket_id or "").strip(),
                #  Para que se vea ANTES de despachar, no despues de crear la
                #  segunda orden del mismo caso.
                "orden_activa": _orden_activa_de(org, caso.id),
                "sugerencia": None,
            }

            #  LA FICHA SE PIDE, NO VIENE SIEMPRE. Es una llamada al motor por
            #  caso --que a su vez habla con WispHub y SmartOLT-- y abrir la
            #  lista no puede costar veinticinco viajes de red. Quien quiere la
            #  sugerencia la pide para el caso que esta mirando.
            if con_ficha:
                #  El try tambien ACA, no solo dentro de `_sugerencia_de`.
                #  Una excepcion que escape de ahi --un import roto, un
                #  cambio de firma-- tiraria la lista entera, y quien mira se
                #  quedaria sin los otros veinticuatro casos por culpa de uno.
                try:
                    fila["sugerencia"] = self._sugerencia_de(caso)
                except Exception:                            # noqa: BLE001
                    fila["sugerencia"] = None
            casos.append(fila)

        return Response({"casos": casos, "tope": self.TOPE,
                         "sin_aprobados": False})

    def _sugerencia_de(self, caso) -> dict | None:
        """Que dice la evidencia de este caso. Nunca rompe la lista."""
        from campo.services.despacho import contexto_del_caso
        from operaciones import clasificacion_de_trabajo as clf

        try:
            contexto = contexto_del_caso(str(caso.id))
            if not (isinstance(contexto, dict)
                    and contexto.get("contexto_disponible")):
                #  Se DICE que no se pudo, y por que. Un `None` se leeria como
                #  "no hay nada que sugerir", que es otra cosa.
                return {
                    "labor": "", "verificada": False, "fuente": "",
                    "porque": (contexto or {}).get("motivo")
                              and f"no se pudo traer la ficha: "
                                  f"{contexto['motivo']}"
                              or "no se pudo traer la ficha del caso.",
                }
            return clf.clasificar(
                contexto,
                texto=f"{caso.name or ''} {caso.description or ''}",
                marcadores={
                    "id_servicio_instalaciones":
                        contexto.get("id_servicio_instalaciones"),
                },
            )
        except Exception:                                    # noqa: BLE001
            #  Un caso que no se pudo evaluar no puede dejar sin lista a los
            #  otros veinticuatro.
            return None
