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

from django.db.models import Count, Q
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


def _quien_tiene(org, case_id: str) -> str | None:
    """A quien esta asignada la orden viva de ese caso, o None si a nadie.

    El estado con que nace una orden se llama «Asignada» aunque no tenga a
    nadie (13/10/2026) -- y eso hacia creer que ya le habia llegado a alguien.
    Esto dice la verdad: el nombre del principal, o None = SIN ASIGNAR.
    """
    orden = (OrdenTrabajo.objects
             .filter(org=org, origen_sistema="crm", origen_ref=str(case_id))
             .exclude(estado_operativo__in=[OrdenTrabajo.CERRADA,
                                            OrdenTrabajo.CANCELADA])
             .first())
    if orden is None:
        return None
    a = (orden.asignaciones.select_related("profile__user")
         .order_by("-es_principal").first())
    if a is None:
        return None
    from campo.services.inventario import nombre_de

    return nombre_de(a.profile)


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
    #:
    #: DESDE EL 18/10/2026 ES EL TAMAÑO DE LA PAGINA, no un corte. Hasta ese
    #: dia el caso numero 26 no aparecia en ningun lado y la pantalla no decia
    #: que faltaban: el tope de la ficha estaba bien puesto, pero como corte
    #: escondia trabajo aprobado. Ahora la ficha sigue costando 25 llamadas como
    #: mucho --las de la pagina que se mira-- y el resto se alcanza paginando.
    TOPE = 25

    #: Lo mas largo que se acepta para buscar. Un asunto, un nombre o un numero
    #: de ticket entran de sobra; mas que esto no es una busqueda.
    LARGO_BUSQUEDA = 100

    def get(self, request):

        org = request.profile.org
        con_ficha = request.query_params.get("ficha") == "1"
        q = (request.query_params.get("q") or "").strip()[:self.LARGO_BUSQUEDA]
        asunto = (request.query_params.get("asunto") or "").strip()
        try:
            pedida = int(request.query_params.get("pagina") or 1)
        except (TypeError, ValueError):
            pedida = 1

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

        #  DOS CAMINOS LLEGAN A CAMPO, y los dos exigen que alguien acepte:
        #
        #    CASO_REQUIERE_VISITA     lo sostiene una MEDICION del equipo. El
        #                             Supervisor lo detecta solo.
        #    TICKET_SIN_DIAGNOSTICO   sale de LEER el reclamo (13/10/2026). El
        #                             Supervisor dice que le pasa al cliente y
        #                             a que labor corresponde, y una persona lo
        #                             autoriza.
        #
        #  El segundo NO entra por tener labor: entra por estar ACEPTADO. Un
        #  diagnostico leido que nadie miro no manda a nadie a manejar hasta
        #  una casa -- es la regla que este modulo ya tenia y que no cambia.
        #  LA REGLA VIVE EN 'paso_a_despacho' desde el 17/10/2026: el
        #  Supervisor la usa para no pedir que alguien mire un caso que ya
        #  esta aca, y dos copias de una regla se desincronizan.
        from operaciones import paso_a_despacho as pad

        aprobados = pad.aprobados_para_despacho(org)
        if not aprobados:
            #  Vacio NO es un error, y se distingue: "todavia nadie aprobo
            #  ninguno" y "no se pudo leer" se dibujan distinto.
            return Response({"casos": [], "tope": self.TOPE,
                             "sin_aprobados": True, "total": 0,
                             "total_sin_filtro": 0, "pagina": 1,
                             "paginas": 1, "asuntos": []})

        en_cola = pad.casos_en_despacho(org, aprobados)

        #  LOS ASUNTOS SE CUENTAN SOBRE TODA LA COLA, no sobre lo filtrado:
        #  son las opciones del filtro, y si se recortaran con el filtro puesto
        #  la unica opcion seria la elegida y no habria como cambiarla.
        asuntos = [
            {"asunto": a["name"], "n": a["n"]}
            for a in (en_cola.values("name").annotate(n=Count("id"))
                      .order_by("name"))
        ]
        total_sin_filtro = sum(a["n"] for a in asuntos)

        filtrados = en_cola
        if asunto:
            filtrados = filtrados.filter(name=asunto)
        if q:
            #  Lo que se ve en la fila, y nada mas: buscar en la descripcion
            #  haria salir casos por un texto que no esta a la vista.
            #
            #  El ticket y el servicio van por 'iexact', como en la cola de
            #  casos (cases/views.py): buscar '553' no tiene por que traer el
            #  ticket 94553. El '#' se quita porque asi se ve el numero en la
            #  pantalla, y quien lo copia de ahi lo trae puesto.
            numero = q.lstrip("#").strip()
            filtrados = filtrados.filter(
                Q(name__icontains=q)
                | Q(external_client_name__icontains=q)
                | Q(account__name__icontains=q)
                | Q(external_ticket_id__iexact=numero)
                | Q(external_service_id__iexact=numero)
            )

        total = filtrados.count()
        paginas = max(1, -(-total // self.TOPE))
        #  La pagina se recorta a lo que existe: al filtrar, la 3 puede dejar
        #  de haber, y quedarse ahi mostraria una tabla vacia sin decir por que.
        pagina = min(max(1, pedida), paginas)
        desde = (pagina - 1) * self.TOPE

        #  'id' desempata: dos casos importados en el mismo lote comparten
        #  'created_at', y sin un orden total la misma fila puede salir en dos
        #  paginas y otra en ninguna.
        qs = (filtrados.select_related("account")
              .order_by("-created_at", "id")[desde:desde + self.TOPE])

        casos = []
        for caso in qs:
            fila = {
                "id": str(caso.id),
                "nombre": caso.name,
                #  DE QUIEN ES. Sin esto la lista son siete "Instalacion Tdt"
                #  iguales. La cuenta del CRM manda cuando existe; si no, el
                #  nombre que trajo el proveedor (ver 'Case.external_client_name':
                #  en este despliegue la tabla de cuentas esta vacia).
                "cliente": ((caso.account.name if caso.account_id else "")
                            or caso.external_client_name or "").strip(),
                "estado": caso.status,
                "prioridad": caso.priority,
                "creado": caso.created_at.isoformat() if caso.created_at else None,
                "servicio": (caso.external_service_id or "").strip(),
                "ticket": (caso.external_ticket_id or "").strip(),
                #  Para que se vea ANTES de despachar, no despues de crear la
                #  segunda orden del mismo caso.
                "orden_activa": _orden_activa_de(org, caso.id),
                #  None = la orden existe pero NADIE la tiene todavia.
                "orden_activa_tecnico": _quien_tiene(org, caso.id),
                "sugerencia": None,
                #  DE DONDE ES EL TRABAJO. Sin esto la orden nace sin zona, y
                #  el reparto la deja en `sin_zona` para siempre: nunca llega
                #  a una cuadrilla, y el sintoma --«no se asigno»-- no señala
                #  aca. Solo se sabe con la ficha; sin ella viaja vacia y la
                #  carga quien despacha.
                "localidad": "",
            }

            #  LA FICHA SE PIDE, NO VIENE SIEMPRE. Es una llamada al motor por
            #  caso --que a su vez habla con WispHub y SmartOLT-- y abrir la
            #  lista no puede costar veinticinco viajes de red. Quien quiere la
            #  sugerencia la pide para el caso que esta mirando.
            if con_ficha:
                fila["localidad"] = self._localidad_de(caso)
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
                         "sin_aprobados": False,
                         #  'total' es lo que coincide con el filtro;
                         #  'total_sin_filtro', toda la cola. Son dos numeros
                         #  distintos y la pantalla dice los dos: «3 de 41».
                         "total": total, "total_sin_filtro": total_sin_filtro,
                         "pagina": pagina, "paginas": paginas,
                         "asuntos": asuntos})

    def _localidad_de(self, caso) -> str:
        """El barrio del cliente, que es lo que el reparto mapea a una zona.

        Sale del contexto que el motor ya trajo. Se lee aparte de la
        sugerencia porque son dos preguntas distintas: una puede fallar sin la
        otra, y la orden sin localidad no se reparte aunque el diagnostico
        haya salido perfecto.
        """
        from campo.services.despacho import contexto_del_caso

        try:
            contexto = contexto_del_caso(str(caso.id))
            cliente = (contexto or {}).get("cliente") or {}
            return str(cliente.get("localidad") or "").strip()
        except Exception:                                    # noqa: BLE001
            return ""

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


class FichaDespachableView(CasosDespachablesView):
    """``GET`` lo que hace falta para despachar UN caso, ya cargado.

    POR QUE EXISTE (13/10/2026)
    ---------------------------
    Al despachar habia que escribir a mano el barrio, como se entra y que hay
    que hacer -- con el barrio en la ficha del ISP y la lectura del Supervisor
    ya hecha. La ficha venia solo con «Traer el diagnostico de cada uno», que
    consulta TODOS los casos; esto la trae para el que se esta mirando: una
    consulta, no veinticinco.

    QUE TRAE, Y DE DONDE
      localidad      la ficha del cliente en el ISP. Es lo que el reparto mapea
                     a una zona: sin ella la orden no llega a ninguna cuadrilla.
      sugerencia     la misma de la lista.
      lectura        lo que el Supervisor leyo del reclamo y recomienda, de la
                     propuesta que una persona ACEPTO. Es una lectura, no un
                     dato: la pantalla la ofrece para confirmar o corregir.
      descripcion    el texto del ticket, TAPADO (celular, documento, correo).
                     Como se entra al inmueble suele estar escrito ahi a mano;
                     no se extrae solo -- seria que un modelo adivine en un campo
                     que el tecnico lee como dato -- se muestra para copiarlo.

    Solo para un caso APROBADO de la empresa: los demas dan 404, igual que si
    no existieran.
    """

    def get(self, request, pk):
        from cases.models import Case

        org = request.profile.org
        from operaciones import paso_a_despacho as pad

        #  La misma regla que la lista: 'paso_a_despacho'.
        propuesta = (
            pad.propuestas_que_llevan_a_despacho(org)
            .filter(origen_id=str(pk))
            .order_by("-revisado_en", "-created_at").first())
        caso = (Case.objects.filter(org=org, id=pk, is_active=True).first()
                if propuesta else None)
        if caso is None:
            return Response({"detail": "No existe."}, status=404)

        try:
            sugerencia = self._sugerencia_de(caso)
        except Exception:                                    # noqa: BLE001
            sugerencia = None
        return Response({
            "id": str(caso.id),
            "localidad": self._localidad_de(caso),
            "sugerencia": sugerencia,
            "lectura": _lectura_de(propuesta),
            "descripcion": _descripcion_tapada(caso),
        })


#: Lo que se muestra del ticket. Es para copiar una indicacion, no para leer el
#: historial entero.
MAX_DESCRIPCION = 1500


def _descripcion_tapada(caso) -> str:
    from operaciones.lectura_de_ticket import tapar

    texto = " ".join(str(caso.description or "").split())
    texto = tapar(texto)
    return texto if len(texto) <= MAX_DESCRIPCION else texto[:MAX_DESCRIPCION] + "…"


def _lectura_de(propuesta) -> dict:
    """La hipotesis y la recomendacion del Supervisor, de la propuesta ACEPTADA.

    La hipotesis vive en la evidencia, como una observacion con la etiqueta de
    `diagnostico_de_ticket` -- se lee por esa etiqueta y no parseando el motivo.
    La recomendacion es `accion_propuesta` (la primera frase); el texto entero
    esta en `motivo`.
    """
    from operaciones.diagnostico_de_ticket import ETIQUETA_LECTURA

    hipotesis = ""
    for obs in propuesta.evidencia or []:
        dato = str((obs or {}).get("dato") or "") if isinstance(obs, dict) else ""
        if dato.startswith(ETIQUETA_LECTURA):
            hipotesis = dato[len(ETIQUETA_LECTURA):].strip()
    return {"hipotesis": hipotesis,
            "recomendacion": (propuesta.accion_propuesta or "").strip(),
            "motivo": (propuesta.motivo or "").strip(),
            "por_que_paso": _por_que_paso_solo(propuesta)}


def _por_que_paso_solo(propuesta) -> str:
    """
    Si la propuesta la acepto el Supervisor solo, por que: el motivo que dejo
    el paso a Despacho, sin el prefijo. Vacio si la acepto una persona: quien
    despacha ya sabe que alguien la miro.

    POR QUE  --  17/10/2026. Desde la Fase 4 pasan solas fallas que la
    medicion no confirma del todo: una caida por LOS puede ser un equipo
    desenchufado, y "no se pudo medir" no confirma nada. El aviso para quien
    despacha --confirmarlo con el cliente antes de mandar a alguien-- quedaba
    en la propuesta y no llegaba a esta pantalla (auditor independiente de la
    Fase 4, hallazgo 2). Es texto fijo de 'paso_a_despacho.decidir', sin datos
    del cliente.
    """
    from operaciones import paso_a_despacho as pad
    from operaciones.models import PropuestaSupervisor

    if (propuesta.estado != PropuestaSupervisor.ACEPTADA
            or propuesta.revisado_por_id is not None):
        return ""
    texto = (propuesta.resultado or "").strip()
    if not texto.startswith(pad.PREFIJO_DEL_PASE.strip()):
        return ""
    return texto[len(pad.PREFIJO_DEL_PASE.strip()):].strip()


class CoberturaView(APIView):
    """``GET ?barrio=&fecha=&labor=`` a que zona va y que cuadrilla la cubre.

    Lo que el supervisor tiene que ver AL DESPACHAR (13/10/2026): no el barrio
    solo, sino la zona a la que pertenece y que cuadrilla la cubre ese dia con
    esa labor. Misma regla que el reparto: ver `campo.reparto.cobertura`.
    `fecha` vacia = hoy en la hora de la empresa.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        import datetime as dt

        from campo.reparto import cobertura

        org = request.profile.org
        texto = (request.query_params.get("fecha") or "").strip()
        try:
            fecha = dt.date.fromisoformat(texto) if texto else None
        except ValueError:
            return Response({"detail": "La fecha va como AAAA-MM-DD."}, status=400)
        if fecha is None:
            from campo.tasks import _ahora_local

            fecha = _ahora_local(org).date()
        return Response({
            "fecha": fecha.isoformat(),
            **cobertura(org, request.query_params.get("barrio") or "", fecha,
                        (request.query_params.get("labor") or "").strip()),
        })
