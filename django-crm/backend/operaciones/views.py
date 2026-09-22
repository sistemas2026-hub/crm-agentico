# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CINCO RUTAS DEL SHADOW MODE
================================================================================

    GET  /api/operaciones/propuestas/            listar, filtrable por estado
    GET  /api/operaciones/propuestas/<id>/       el detalle, con su evidencia
                                                 y su historial de auditoria
    POST /api/operaciones/propuestas/<id>/revisar/    aceptar/modificar/rechazar
    POST /api/operaciones/propuestas/<id>/cancelar/   la condicion desaparecio
    POST /api/operaciones/supervisor/ciclo/      correr una pasada de deteccion

NINGUNA EJECUTA NADA CONTRA UN SISTEMA EXTERNO. La de 'ciclo' escribe filas de
propuesta y de auditoria, y nada mas; la de 'revisar' cambia el estado de una
propuesta y lo audita. No hay ruta de ejecucion porque no hay ejecucion.

LOS CODIGOS DE RESPUESTA, Y POR QUE ESOS  --  paso M09-F
--------------------------------------------------------
    400  la peticion esta mal (campo no editable, prioridad fuera de rango)
    403  no tiene rol de gestion
    404  la propuesta es de otra organizacion  -- nunca 403: un 403 confirma
         que el id existe
    409  alguien decidio primero (o fue un doble clic). NO es un 400: la
         peticion era valida, lo que cambio fue el mundo mientras el revisor
         miraba la pantalla.

POR QUE NO HAY PANTALLA TODAVIA
-------------------------------
El encargo dice que no hace falta un tablero complejo y que puede ser
API/servicio/registro interno. Estas cuatro rutas contestan las diez preguntas
que el Shadow Mode tiene que poder contestar -- que detecto, cuando, en que
organizacion, sobre que entidad, con que evidencia, que propuso, por que, que
nivel habria requerido, que hizo el humano y con que resultado.
================================================================================
"""

from __future__ import annotations

from django.db.utils import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import Profile
from django.http import Http404
from django.utils import timezone

from operaciones import (actividades, asistentes, auditoria, indicadores,
                         supervisor)
from operaciones.capacidad import capacidad_de_jornada
from campo.services.idempotencia import manejar_idempotencia
from operaciones.models import (ActividadOperativa, DisponibilidadTecnico, ProgramacionOrden,
                                ProgramacionSemanal, PropuestaSupervisor)
from operaciones.programacion import (ErrorProgramacion, PlanIncoherente,
                                      PlanNoPublicable, _lineas_vigentes,
                                      JornadaCambio, JornadaIncompleta,
                                      actualizar_secuencia,
                                      secuenciar_jornada,
                                      lineas_de_jornada, publicar_programacion,
                                      resumen_de_jornada)
from operaciones.permissions import EsJefeDeOperaciones, misma_organizacion
from operaciones.serializers import (ActividadOperativaSerializer,
                                    AsistenteSerializer,
                                    ReporteSerializer,
                                    CrearActividadSerializer,
                                    TransicionActividadSerializer,

    CancelacionSerializer,
    DisponibilidadCrearSerializer,
    DisponibilidadSerializer,
    LineaJornadaSerializer,
    SecuenciaSerializer,
    SecuenciarJornadaSerializer,
    PropuestaDetalleSerializer,
    PropuestaListaSerializer,
    RevisionSerializer,
)


class PropuestasView(APIView):
    """Las propuestas de esta organización, las más urgentes primero."""

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        # El filtro por organizacion va SIEMPRE, y no depende de la RLS de la
        # base: las dos capas, igual que el resto del CRM.
        qs = PropuestaSupervisor.objects.filter(org=request.org)
        estado = request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        tipo = request.query_params.get("tipo_senal")
        if tipo:
            qs = qs.filter(tipo_senal=tipo)
        return Response({
            "count": qs.count(),
            "resultados": PropuestaListaSerializer(qs[:200], many=True).data,
        })


class PropuestaDetalleView(APIView):
    """Una propuesta con su evidencia completa y su historial de auditoría."""

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request, propuesta_id):
        propuesta = get_object_or_404(PropuestaSupervisor, id=propuesta_id)
        misma_organizacion(propuesta, request)
        historial = auditoria.historial(
            request.org, auditoria.ENTIDAD_PROPUESTA, propuesta.id)
        datos = PropuestaDetalleSerializer(propuesta).data
        datos["historial"] = [
            {
                "accion": h.action,
                "quien": (h.user.user.email if h.user and h.user.user else "Supervisor NOC IA"),
                "cuando": h.created_at.isoformat(),
                "descripcion": h.description,
                "metadata": h.metadata,
            }
            for h in historial
        ]
        return Response(datos)


class RevisarPropuestaView(APIView):
    """
    El Jefe de Operaciones decide: aceptar, modificar o rechazar.

    Aceptar NO ejecuta la propuesta. Es deliberado y está dicho en la respuesta,
    para que nadie que use esta API asuma lo contrario.
    """

    permission_classes = [EsJefeDeOperaciones]

    def post(self, request, propuesta_id):
        propuesta = get_object_or_404(PropuestaSupervisor, id=propuesta_id)
        misma_organizacion(propuesta, request)

        entrada = RevisionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            cambios = self._resolver_cambios(
                entrada.validated_data.get("cambios") or {}, request)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            propuesta = supervisor.revisar(
                propuesta,
                actor=request.profile,
                decision=entrada.validated_data["decision"],
                comentario=entrada.validated_data.get("comentario", ""),
                cambios=cambios,
            )
        except supervisor.YaRevisada as e:
            #  409 y no 400: la petición era válida, lo que cambió fue el mundo
            #  entre que el revisor abrió la pantalla y apretó el botón. Un 400
            #  le diría "te equivocaste" a alguien que no se equivocó, y un
            #  doble clic es el caso más común de los dos.
            return Response(
                {"error": str(e),
                 "estado_actual": PropuestaSupervisor.objects.get(
                     id=propuesta_id).estado,
                 "aviso": "Otra persona (o tu propio doble clic) decidió primero. "
                          "La primera decisión es la que vale."},
                status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "propuesta": PropuestaDetalleSerializer(propuesta).data,
            "ejecutada": False,
            "aviso": ("Shadow Mode: la decisión quedó registrada y auditada. "
                      "Ninguna acción se ejecutó."),
        })

    @staticmethod
    def _resolver_cambios(cambios: dict, request) -> dict:
        """
        Traduce lo que llega por HTTP a lo que entiende el dominio.

        Solo 'responsable_sugerido' necesita traducción: viaja como id y tiene
        que llegar como Profile. Se busca ACOTADO A LA ORGANIZACION de quien
        pide -- un id de otro tenant no da 403 ni 404 desde aquí, simplemente no
        existe dentro de su organización, que es la respuesta correcta.
        """
        if "responsable_sugerido" not in cambios:
            return cambios

        cambios = dict(cambios)
        crudo = cambios["responsable_sugerido"]
        if crudo in (None, ""):
            cambios["responsable_sugerido"] = None
            return cambios
        perfil = Profile.objects.filter(id=crudo, org=request.org).first()
        if perfil is None:
            raise ValueError(
                "El responsable sugerido no existe en esta organización.")
        cambios["responsable_sugerido"] = perfil
        return cambios


class CancelarPropuestaView(APIView):
    """
    La condición desapareció antes de que nadie la revisara.

    Es una ruta aparte de 'revisar' porque no es una decisión sobre el fondo:
    nadie opinó si la recomendación era buena. Por eso no deja revisor, y por
    eso el motivo es obligatorio.
    """

    permission_classes = [EsJefeDeOperaciones]

    def post(self, request, propuesta_id):
        propuesta = get_object_or_404(PropuestaSupervisor, id=propuesta_id)
        misma_organizacion(propuesta, request)

        entrada = CancelacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            propuesta = supervisor.cancelar(
                propuesta, motivo=entrada.validated_data["motivo"])
        except supervisor.YaRevisada as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "propuesta": PropuestaDetalleSerializer(propuesta).data,
            "ejecutada": False,
        })


class CicloSupervisorView(APIView):
    """
    Corre una pasada de detección. Solo lee y propone.

    Se expone como ruta y no como trabajo del scheduler a propósito: engancharlo
    al scheduler sería darle al Supervisor la capacidad de correr solo, y esta
    etapa es explícitamente la que no se la da. Cuando se decida automatizarlo,
    el registro de trabajos del motor ya existe y está vacío.
    """

    permission_classes = [EsJefeDeOperaciones]

    def post(self, request):
        resumen = supervisor.correr_ciclo(request.org)
        return Response({
            "resumen": resumen,
            "shadow_mode": supervisor.SHADOW_MODE,
            "acciones_ejecutadas": 0,
        })


class DisponibilidadView(APIView):
    """
    ================================================================================
     LA VIA OPERATIVA DE DISPONIBILIDAD  --  paso A-3.3
    ================================================================================

        GET  /api/operaciones/disponibilidad/     las franjas de esta organizacion
        POST /api/operaciones/disponibilidad/     registrar una franja o una ausencia

    POR QUE EXISTE, Y QUE REEMPLAZA
    -------------------------------
    Hasta este paso la UNICA forma de registrar que un tecnico no esta disponible
    era el panel de Django. A-3 midio los dos problemas de esa via:

      1. '/admin/' esta en EXEMPT_PATHS de RequireOrgContext, asi que NO fija
         'app.current_org'. La politica RLS compara contra esa variable, de modo
         que el aislamiento por organizacion NO lo daba la base: lo daba el
         BYPASSRLS del rol 'postgres' con el que hoy conecta Django.
      2. Exige 'is_staff' -- 1 de 5 usuarios.

    Es el mismo problema que campo/despacho_views.py ya habia resuelto para
    crear, asignar y validar trabajo, y con las mismas palabras: "Nadie necesita
    'is_staff' para despachar una cuadrilla". Esta vista aplica ese precedente a
    la disponibilidad.

    QUE NO HACE
    -----------
    No calcula capacidad, ni carga, ni ocupacion: eso sigue sin definirse (K-02,
    D-4). No programa ni reprograma -- M03 es el dueño de ese efecto. Y no borra:
    ver 'delete' mas abajo.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        #  El filtro por organizacion va SIEMPRE, igual que en PropuestasView, y
        #  no depende de la RLS: las dos capas. Aca importa el doble porque hoy
        #  el runtime conecta con un rol que atraviesa RLS (ver B-7).
        qs = DisponibilidadTecnico.objects.filter(
            org=request.org).select_related("profile__user")

        fecha = request.query_params.get("fecha")
        if fecha:
            qs = qs.filter(fecha=fecha)
        profile_id = request.query_params.get("profile")
        if profile_id:
            qs = qs.filter(profile_id=profile_id)
        solo_ausencias = request.query_params.get("ausencias")
        if solo_ausencias in ("1", "true", "si"):
            qs = qs.filter(disponible=False)

        return Response({
            "count": qs.count(),
            "resultados": DisponibilidadSerializer(qs[:500], many=True).data,
        })

    def post(self, request):
        entrada = DisponibilidadCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        #  EL CONTROL DE AISLAMIENTO, EN UNA LINEA
        #  ---------------------------------------
        #  El perfil se busca ACOTADO a request.org. Un id de otra organizacion
        #  no da 403 --eso confirmaria que existe-- sino que simplemente no se
        #  encuentra dentro de la propia. Mismo criterio que
        #  RevisarPropuestaView._resolver_cambios y que 'misma_organizacion'.
        profile = Profile.objects.filter(
            id=datos["profile"], org=request.org).first()
        if profile is None:
            return Response(
                {"error": "Ese técnico no existe en esta organización."},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            franja = DisponibilidadTecnico.objects.create(
                #  org NO viene del cliente: sale de la sesion ya validada.
                org=request.org,
                profile=profile,
                fecha=datos["fecha"],
                hora_inicio=datos["hora_inicio"],
                hora_fin=datos["hora_fin"],
                disponible=datos["disponible"],
                motivo=(datos.get("motivo") or "").strip(),
                zona=(datos.get("zona") or "").strip(),
            )
        except IntegrityError as e:
            #  Las dos CheckConstraint de la base. El serializador ya las
            #  comprueba antes, asi que llegar aca significa que alguien
            #  encontro un camino que el serializador no cubre -- y entonces
            #  gana la base, que es lo correcto.
            return Response(
                {"error": "La base rechazó la franja.", "detalle": str(e)[:200]},
                status=status.HTTP_400_BAD_REQUEST)

        #  created_by / updated_by los escribe BaseModel.save() desde crum con
        #  el usuario de la peticion. No se aceptan por payload: firmar como
        #  otro no puede ser un campo de entrada.
        return Response(
            {"disponibilidad": DisponibilidadSerializer(franja).data,
             "aviso": ("Registrado. Esto NO reprograma ni reasigna trabajo: "
                       "solo declara la disponibilidad de la persona.")},
            status=status.HTTP_201_CREATED)

    def delete(self, request):
        """
        No se borra, y no es un descuido.

        Una ausencia declarada pudo haber movido una programación. Borrar la
        fila hace desaparecer la causa de una decisión que sí se tomó, y deja
        una reprogramación sin explicación.

        La política de corrección todavía no está definida (A-3 §7), así que
        esta etapa implementa únicamente registro seguro.
        """
        return Response(
            {"error": "La disponibilidad no se borra.",
             "detalle": ("Una ausencia registrada pudo haber movido trabajo. "
                         "La política de corrección está pendiente de "
                         "definición."),
             "pendiente": "POLITICA DE CORRECCION"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED)


class PublicarProgramacionView(APIView):
    """
    ================================================================================
     PUBLICAR UN PLAN SEMANAL  --  paso M03-C
    ================================================================================

        POST /api/operaciones/programacion/<uuid:programacion_id>/publicar/

    Publicar hace UNA cosa: pasar el plan de 'borrador' a 'publicada'. No
    ejecuta la programacion -- no toca ninguna orden, no crea asignaciones, no
    calcula nada. Lo que cambia es que el plan deja de ser un borrador, y eso
    es exactamente lo que la señal 'programacion_sin_publicar' de M09 lleva
    midiendo desde que existe sin que nadie pudiera apagarla.

    POR QUE ESTA RUTA VIVE AQUI Y LA DE M03-B EN 'campo'
    ----------------------------------------------------
    M03-B programa una ORDEN, y la orden es de campo: su ruta cuelga de
    'trabajos/<pk>/'. Esto publica un PLAN, y el plan es de operaciones. Cada
    operacion vive junto a su recurso en vez de junto a la otra.

    NO ES UNA RUTA DE EJECUCION
    ---------------------------
    No llama a ningun sistema externo, no despacha, no aplica nada a un
    tercero. El inventario de rutas que fija M09-F lo comprueba por nombre y
    por sustring prohibido; esta entra por la puerta de adelante.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    def post(self, request, programacion_id):
        #  El plan se busca ACOTADO a request.org. Un id de otra organizacion
        #  no da 403 --eso confirmaria que existe-- sino que no aparece.
        plan = ProgramacionSemanal.objects.filter(
            id=programacion_id, org=request.org).first()
        if plan is None:
            return Response(
                {"error": "NO_EXISTE",
                 "detalle": "No existe ese plan semanal en esta organización."},
                status=status.HTTP_404_NOT_FOUND)

        try:
            publicado = publicar_programacion(
                org=request.org, programacion=plan, actor=request.profile)
        except PlanNoPublicable as e:
            #  409 y no 400: la peticion es correcta, el conflicto es con el
            #  estado actual del plan. Cubre las dos puertas cerradas -- ya
            #  publicado (idempotencia semantica) y cerrado.
            return Response(
                {"error": "NO_PUBLICABLE", "detalle": str(e),
                 "estado": plan.estado},
                status=status.HTTP_409_CONFLICT)
        except PlanIncoherente as e:
            #  400 con la lista COMPLETA de lo que no cuadra, sin corregir
            #  ninguno: elegir si manda el plan o la orden no es una decision
            #  que el servidor pueda tomar.
            return Response(
                {"error": "PLAN_INCOHERENTE", "detalle": str(e),
                 "problemas": e.problemas},
                status=status.HTTP_400_BAD_REQUEST)
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_PUBLICAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "programacion": {
                "id": str(publicado.id),
                "semana_inicio": str(publicado.semana_inicio),
                "estado": publicado.estado,
                "publicada_en": publicado.publicada_en.isoformat(),
                "publicada_por": str(publicado.publicada_por_id),
            },
            "lineas": _lineas_vigentes(publicado).count(),
            "aviso": ("Publicado. Esto NO asigna técnicos ni modifica ninguna "
                      "orden: solo deja de ser un borrador."),
        })


class JornadaView(APIView):
    """
    ================================================================================
     LA JORNADA, LEIBLE Y EN ORDEN REPRODUCIBLE  --  paso M03-E2
    ================================================================================

        GET /api/operaciones/programacion/jornada/?dia=YYYY-MM-DD
        GET /api/operaciones/programacion/jornada/?plan=<uuid>

    POR QUE EXISTE
    --------------
    M03-E1 midio que 'secuencia' era de SOLO ESCRITURA: se podia enviar al
    programar y no habia forma de volver a verla -- ni en una respuesta, ni en
    un endpoint, ni en pantalla. Una regla de ordenamiento sobre un campo que
    nadie puede observar no se puede comprobar, asi que lo primero es poder
    mirarlo.

    QUE NO HACE
    -----------
    No reordena, no recompacta, no reasigna y no valida. Es una lectura. Los
    empates se CUENTAN y se declaran; resolverlos es la decision E-1, que sigue
    abierta, y decir que significa 'secuencia = 0' es la E-2.

    NO ES UNA RUTA DE EJECUCION
    ---------------------------
    Es un GET. No escribe nada, no llama a ningun sistema externo y no despacha.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        dia = request.query_params.get("dia")
        plan_id = request.query_params.get("plan")
        if not dia and not plan_id:
            return Response(
                {"error": "FALTA_FILTRO",
                 "detalle": "Hay que pedir un día ('dia=YYYY-MM-DD') o un "
                            "plan ('plan=<uuid>'). Sin filtro, 'la jornada' no "
                            "significa nada."},
                status=status.HTTP_400_BAD_REQUEST)

        plan = None
        if plan_id:
            #  Acotado a request.org, igual que el resto del módulo: un id de
            #  otra organización no da 403 --eso confirmaría que existe-- sino
            #  que simplemente no aparece.
            plan = ProgramacionSemanal.objects.filter(
                id=plan_id, org=request.org).first()
            if plan is None:
                return Response(
                    {"error": "NO_EXISTE",
                     "detalle": "No existe ese plan semanal en esta organización."},
                    status=status.HTTP_404_NOT_FOUND)

        if dia:
            serializado = serializers.DateField()
            try:
                dia = serializado.to_internal_value(dia)
            except Exception:
                return Response(
                    {"error": "DIA_INVALIDO",
                     "detalle": "El día tiene que venir como YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST)

        lineas = list(lineas_de_jornada(request.org, programacion=plan, dia=dia))
        return Response({
            "count": len(lineas),
            "resultados": LineaJornadaSerializer(lineas, many=True).data,
            "resumen": resumen_de_jornada(lineas),
            "filtro": {"dia": str(dia) if dia else None,
                       "plan": str(plan.id) if plan else None},
        })


class SecuenciaLineaView(APIView):
    """
    ================================================================================
     CAMBIAR EL ORDEN PROPUESTO DE UNA LINEA  --  paso M03-E4
    ================================================================================

        POST /api/operaciones/programacion/linea/<uuid:linea_id>/secuencia/

    Hasta este paso, corregir el orden de una línea exigía REPROGRAMAR la orden
    -- o sea, mover el trabajo para arreglar la posición. Son dos cosas
    distintas, y ahora se hacen por separado.

    QUE NO TOCA
    -----------
    'programada_para', el día, el plan, la orden, la zona, la prioridad, el
    estado operativo y el de validación. Cambiar la secuencia no es reprogramar.

    NO ES UNA RUTA DE EJECUCION
    ---------------------------
    Escribe una columna de una línea de plan y su evento. No llama a ningún
    sistema externo, no despacha, no reasigna y no mueve trabajo.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    @manejar_idempotencia
    def post(self, request, linea_id):
        entrada = SecuenciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data

        #  Acotada a request.org: una línea de otra organización no da 403
        #  --eso confirmaría que existe-- sino que no aparece. El id por sí solo
        #  nunca alcanza.
        linea = ProgramacionOrden.objects.filter(
            id=linea_id, org=request.org).first()
        if linea is None:
            return Response(
                {"error": "NO_EXISTE",
                 "detalle": "No existe esa línea de plan en esta organización."},
                status=status.HTTP_404_NOT_FOUND)

        try:
            linea, evento, novedad = actualizar_secuencia(
                org=request.org, linea=linea, secuencia=d["secuencia"],
                actor=request.profile, causa=d.get("causa") or "",
                motivo=d.get("motivo") or "",
                contexto=d.get("contexto") or {})
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_CAMBIAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        if evento is None:
            #  NO-OP (decisión B-1): la línea ya tenía esa secuencia. Misma
            #  respuesta que da la vía de jornada al mismo hecho, y con la
            #  misma clave 'resultado' para que las dos hablen igual.
            return Response({
                "linea": LineaJornadaSerializer(linea).data,
                "resultado": "sin_cambios",
                "traza": None,
                "aviso": ("La línea ya tenía ese orden propuesto. No se "
                          "modificó nada y no se registró ningún evento."),
            })

        return Response({
            "linea": LineaJornadaSerializer(linea).data,
            "resultado": "aplicado",
            "traza": {
                "evento": str(evento.id),
                "anterior": evento.datos["anterior"],
                "nuevo": evento.datos["nuevo"],
                "novedad": str(novedad.id) if novedad else None,
            },
            "empate": evento.datos["empate"],
            "aviso": ("Cambiado el orden propuesto. Esto NO reprograma la "
                      "orden ni modifica ninguna otra línea."),
        })


class SecuenciarJornadaView(APIView):
    """
    ================================================================================
     SECUENCIAR UNA JORNADA ENTERA, DE UNA SOLA VEZ  --  paso M03-E5-B
    ================================================================================

        POST /api/operaciones/programacion/jornada/secuenciar/

    Con M03-E4, poner tres órdenes en 1-2-3 eran tres peticiones y tres
    transacciones, y entre la primera y la tercera el plan pasaba por estados
    intermedios que un lector de la jornada podía ver. Aquí la jornada queda
    como el usuario la dejó, o no queda de ninguna forma.

    LA PETICIÓN DECLARA LA JORNADA COMPLETA
    ---------------------------------------
    Se envían TODAS las líneas vigentes del día, cada una con la secuencia que
    el cliente LEYÓ y la que quiere dejar. Lo primero no es adorno: sin ello no
    se puede cumplir "no sobrescribir silenciosamente cambios concurrentes",
    porque 'ProgramacionOrden' no tiene campo de concurrencia optimista.

    NO ES UNA RUTA DE EJECUCION
    ---------------------------
    Escribe una columna de N líneas de plan y sus eventos. No llama a ningún
    sistema externo, no despacha, no reasigna y no mueve trabajo.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    @manejar_idempotencia
    def post(self, request):
        entrada = SecuenciarJornadaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data

        plan = ProgramacionSemanal.objects.filter(
            id=d["plan"], org=request.org).first()
        if plan is None:
            return Response(
                {"error": "NO_EXISTE",
                 "detalle": "No existe ese plan semanal en esta organización."},
                status=status.HTTP_404_NOT_FOUND)

        try:
            r = secuenciar_jornada(
                org=request.org, plan=plan, dia=d["dia"],
                lineas=d["lineas"], actor=request.profile,
                causa=d.get("causa") or "", motivo=d.get("motivo") or "",
                contexto=d.get("contexto") or {})
        except JornadaCambio as e:
            #  409, el mismo código que el resto del módulo usa cuando lo que
            #  cambió fue el mundo y no la petición.
            return Response(
                {"error": "JORNADA_CAMBIO", "detalle": str(e),
                 "conflictos": e.conflictos,
                 "aviso": ("La jornada cambió mientras la ordenabas. "
                           "Recárgala y vuelve a enviarla: no se aplicó nada.")},
                status=status.HTTP_409_CONFLICT)
        except JornadaIncompleta as e:
            return Response(
                {"error": "JORNADA_INCOMPLETA", "detalle": str(e),
                 "faltantes": e.faltantes, "sobrantes": e.sobrantes,
                 "desconocidas": e.desconocidas, "ajenas": e.ajenas,
                 "aviso": ("La petición tiene que traer TODAS las líneas de la "
                           "jornada: representa cómo queda el día entero.")},
                status=status.HTTP_400_BAD_REQUEST)
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_SECUENCIAR",
                             "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        lineas = r.pop("lineas")
        return Response({
            **r,
            "lineas": LineaJornadaSerializer(lineas, many=True).data,
            "resumen": resumen_de_jornada(lineas),
            "aviso": ("Secuenciado. Esto NO reprograma ninguna orden ni "
                      "modifica su asignación: solo el orden propuesto."),
        })


class CapacidadJornadaView(APIView):
    """
    ================================================================================
     CAPACIDAD OPERACIONAL DE UNA JORNADA  --  paso M03-G
    ================================================================================

        GET /api/operaciones/capacidad/jornada/?dia=YYYY-MM-DD
        GET /api/operaciones/capacidad/jornada/?dia=YYYY-MM-DD&profile_id=<uuid>

    QUE DEVUELVE
    ------------
    Por cada persona con trabajo programado ese dia: la jornada de la empresa,
    su disponibilidad, la carga ya comprometida, lo que le queda y si eso se
    pasa.

    ES UN GET, Y ESO NO ES UN DETALLE
    ---------------------------------
    No escribe, no reprograma, no reasigna, no retira a nadie y no llama a
    ningun sistema externo. La capacidad no se guarda en ninguna tabla: se
    deriva cuando se pregunta, porque un numero guardado queda viejo en cuanto
    cambia cualquiera de las cinco cosas de las que depende.

    LO QUE NO PUEDE CONCLUIR, LO DICE
    ---------------------------------
    Si falta la duracion de alguna orden, 'riesgo' responde INDETERMINADO en
    vez de 'sin sobrecarga' -- salvo que lo ya conocido no quepa, en cuyo caso
    la sobrecarga SI se puede afirmar. Un dato que falta no vale cero, y la
    respuesta trae 'faltantes' con el motivo.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        crudo = request.query_params.get("dia")
        if not crudo:
            return Response(
                {"error": "FALTA_DIA",
                 "detalle": "Hay que pedir un día ('dia=YYYY-MM-DD'). Sin día, "
                            "'la capacidad' no significa nada."},
                status=status.HTTP_400_BAD_REQUEST)
        try:
            dia = serializers.DateField().to_internal_value(crudo)
        except Exception:
            return Response(
                {"error": "DIA_INVALIDO",
                 "detalle": "El día tiene que venir como YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST)

        persona = None
        pid = request.query_params.get("profile_id")
        if pid:
            #  Acotado a request.org: un id de otra empresa no da 403 --eso
            #  confirmaria que existe-- sino que no aparece.
            persona = Profile.objects.filter(id=pid, org=request.org).first()
            if persona is None:
                return Response(
                    {"error": "NO_EXISTE",
                     "detalle": "No existe esa persona en esta organización."},
                    status=status.HTTP_404_NOT_FOUND)

        return Response(capacidad_de_jornada(request.org, dia, profile=persona))


# =============================================================================
#  M02  --  ACTIVIDADES OPERATIVAS
# =============================================================================
#
#  Cuatro rutas y nada más: lista, detalle, crear y UNA puerta de transición.
#  La alternativa --un PATCH sobre 'estado_operativo'-- haría representable
#  cualquier salto y la máquina de estados no significaría nada.
#
#  Ninguna ejecuta acciones externas. Producen estado interno y auditoría.


def _actividad_o_404(request, actividad_id):
    a = ActividadOperativa.objects.filter(id=actividad_id, org=request.org).first()
    if a is None:
        #  404 estricto al cruzar empresas: un 403 confirmaría que el id existe.
        raise Http404("No existe esa actividad en esta organización.")
    return a


def _perfil_o_404(request, pid, que="persona"):
    p = Profile.objects.filter(id=pid, org=request.org).first()
    if p is None:
        raise Http404(f"No existe esa {que} en esta organización.")
    return p


def _error_actividad(e):
    if isinstance(e, actividades.ActividadDuplicada):
        return Response({"error": "ACTIVIDAD_DUPLICADA", "detalle": str(e)},
                        status=status.HTTP_409_CONFLICT)
    if isinstance(e, actividades.DependenciaCiclica):
        return Response({"error": "DEPENDENCIA_CICLICA", "detalle": str(e)},
                        status=status.HTTP_409_CONFLICT)
    if isinstance(e, actividades.TransicionInvalida):
        return Response({"error": "TRANSICION_INVALIDA", "detalle": str(e)},
                        status=status.HTTP_409_CONFLICT)
    return Response({"error": "NO_SE_PUDO", "detalle": str(e)},
                    status=status.HTTP_400_BAD_REQUEST)


class ActividadesView(APIView):
    """
        GET  /api/operaciones/actividades/    lista + resumen
        POST /api/operaciones/actividades/    crear

    El GET acota SIEMPRE a la organización de la sesión. Quien consulta no
    elige el tenant.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        responsable = None
        pid = request.query_params.get("responsable_id")
        if pid:
            responsable = _perfil_o_404(request, pid)

        abiertas = request.query_params.get("abiertas", "1") not in ("0", "false")
        qs = actividades.pendientes_relevantes(
            request.org, responsable=responsable,
            tipo=request.query_params.get("tipo") or None,
            estado=request.query_params.get("estado") or None,
            solo_abiertas=abiertas)

        ventana = request.query_params.get("ventana_horas")
        try:
            ventana = int(ventana) if ventana else None
        except ValueError:
            return Response({"error": "VENTANA_INVALIDA",
                             "detalle": "'ventana_horas' tiene que ser un entero."},
                            status=status.HTTP_400_BAD_REQUEST)

        filas = list(qs)
        return Response({
            "count": len(filas),
            "resultados": ActividadOperativaSerializer(filas, many=True).data,
            "resumen": actividades.resumen(filas, ventana_horas=ventana),
        })

    @manejar_idempotencia
    def post(self, request):
        s = CrearActividadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        responsable = (_perfil_o_404(request, d["responsable_id"])
                       if d.get("responsable_id") else None)
        depende_de = (_actividad_o_404(request, d["depende_de_id"])
                      if d.get("depende_de_id") else None)

        try:
            a = actividades.crear(
                org=request.org, actor=request.profile, tipo=d["tipo"],
                titulo=d["titulo"], descripcion=d["descripcion"],
                responsable=responsable, origen_tipo=d["origen_tipo"],
                origen_id=d["origen_id"], vence_en=d.get("vence_en"),
                depende_de=depende_de,
                evitar_duplicado=d["evitar_duplicado"])
        except actividades.ErrorActividad as e:
            return _error_actividad(e)

        return Response({"actividad": ActividadOperativaSerializer(a).data,
                         "server_time": timezone.now().isoformat()},
                        status=status.HTTP_201_CREATED)


class ActividadDetalleView(APIView):
    """
        GET /api/operaciones/actividades/<id>/

    Devuelve la actividad y su historial, que vive en common.Activity: ahí es
    donde este módulo deja cada transición. No hay una tabla de auditoría
    propia y no hace falta.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request, actividad_id):
        a = _actividad_o_404(request, actividad_id)
        historial = auditoria.historial(
            request.org, auditoria.ENTIDAD_ACTIVIDAD, a.id)[:50]
        return Response({
            "actividad": ActividadOperativaSerializer(a).data,
            "historial": [
                {"accion": h.action,
                 "cuando": h.created_at.isoformat(),
                 "actor": str(h.user_id) if h.user_id else None,
                 "descripcion": h.description,
                 "metadata": h.metadata}
                for h in historial
            ],
        })


class TransicionActividadView(APIView):
    """
        POST /api/operaciones/actividades/<id>/transicion/

    Once acciones explícitas. Cada una es la operación de servicio del mismo
    nombre; aquí sólo se resuelven los ids y se traduce el error.
    """

    permission_classes = [EsJefeDeOperaciones]

    @manejar_idempotencia
    def post(self, request, actividad_id):
        a = _actividad_o_404(request, actividad_id)
        s = TransicionActividadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        accion, motivo = d["accion"], d["motivo"]
        actor = request.profile
        resultado = "aplicado"

        try:
            if accion == "asignar":
                nuevo = (_perfil_o_404(request, d["responsable_id"])
                         if d.get("responsable_id") else None)
                a, cambio = actividades.asignar_responsable(
                    a, actor=actor, responsable=nuevo, motivo=motivo)
                resultado = "aplicado" if cambio else "sin_cambios"
            elif accion == "iniciar":
                a = actividades.iniciar_gestion(a, actor=actor, motivo=motivo)
            elif accion == "esperar":
                a = actividades.poner_en_espera(a, actor=actor, motivo=motivo)
            elif accion == "bloquear":
                a = actividades.bloquear(a, actor=actor, motivo=motivo)
            elif accion == "desbloquear":
                a = actividades.desbloquear(a, actor=actor, motivo=motivo,
                                            destino=d["destino"])
            elif accion == "escalar":
                a = actividades.escalar(a, actor=actor, motivo=motivo)
            elif accion == "completar":
                a = actividades.completar(
                    a, actor=actor, motivo=motivo,
                    requiere_validacion=d["requiere_validacion"])
            elif accion == "validar":
                if not d.get("decision"):
                    return Response(
                        {"error": "FALTA_DECISION",
                         "detalle": "Validar exige 'decision'."},
                        status=status.HTTP_400_BAD_REQUEST)
                a = actividades.validar(a, actor=actor,
                                        decision=d["decision"], motivo=motivo)
            elif accion == "cancelar":
                a = actividades.cancelar(a, actor=actor, motivo=motivo)
            elif accion == "dependencia":
                otra = (_actividad_o_404(request, d["depende_de_id"])
                        if d.get("depende_de_id") else None)
                a, cambio = actividades.establecer_dependencia(
                    a, actor=actor, depende_de=otra, motivo=motivo)
                resultado = "aplicado" if cambio else "sin_cambios"
            elif accion == "vencimiento":
                a, cambio = actividades.cambiar_vencimiento(
                    a, actor=actor, vence_en=d.get("vence_en"), motivo=motivo)
                resultado = "aplicado" if cambio else "sin_cambios"
        except actividades.ErrorActividad as e:
            return _error_actividad(e)

        a.refresh_from_db()
        return Response({"actividad": ActividadOperativaSerializer(a).data,
                         "resultado": resultado,
                         "server_time": timezone.now().isoformat()})


class AsistenteView(APIView):
    """
        POST /api/operaciones/asistentes/   {"dominio": "programacion" | "compromiso"}

    Una pasada del asistente: LEE las señales de su dominio, las ANALIZA y
    PROPONE. No ejecuta nada.

    ESCRIBE, Y AUN ASÍ NO EJECUTA
    -----------------------------
    Lo único que escribe son filas de 'PropuestaSupervisor' -- la misma cola
    que ya existía, con el mismo registrador, la misma deduplicación y la misma
    revisión humana. No programa, no asigna, no cierra, no cancela y no llama a
    ningún sistema externo: el módulo no importa un solo servicio de escritura
    operativa, así que no tiene con qué.

    Se serializa por organización, igual que el ciclo de M09-L.
    """

    permission_classes = [EsJefeDeOperaciones]

    @manejar_idempotencia
    def post(self, request):
        s = AsistenteSerializer(data=request.data)
        if not s.is_valid():
            return Response({"error": "ASISTENTE_DESCONOCIDO",
                             "detalle": s.errors.get("dominio", s.errors)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(asistentes.asistir(request.org,
                                           s.validated_data["dominio"]))


class IndicadoresView(APIView):
    """
        GET /api/operaciones/indicadores/?desde=&hasta=&dias=

    Todos los indicadores operativos, derivados en el momento de la consulta.

    ES UN GET, Y NO GUARDA NADA
    ---------------------------
    No hay tabla de KPI, no hay data warehouse y no hay caché persistente: un
    número guardado queda viejo en cuanto cambia la fila que lo sostiene. Y
    consultar un indicador no crea actividad de negocio ni corre el ciclo del
    Supervisor.

    Cada indicador viene con su estado -- VALIDO, DATOS_INSUFICIENTES o
    NO_APLICA -- y con la cobertura sobre la que se calculó. Un promedio sobre
    la mitad de la población no se presenta como si fuera de toda.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        s = ReporteSerializer(data=request.query_params)
        if not s.is_valid():
            return Response({"error": "FILTRO_INVALIDO", "detalle": s.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        d = s.validated_data
        return Response(indicadores.indicadores(
            request.org, desde=d.get("desde"), hasta=d.get("hasta"),
            dias=d.get("dias")))


class ReportesView(APIView):
    """
        GET /api/operaciones/reportes/?reporte=diario&desde=&hasta=&dias=

    Cinco reportes: diario, pendientes, programacion, compromisos, supervisor.

    Cada uno trae periodo, fecha de generación, filtros, fuentes, métricas,
    cobertura, la lista de lo que NO se pudo calcular y sus observaciones. Las
    observaciones dicen lo que los números NO demuestran -- por ejemplo, que
    'vencida' no significa que alguien haya incumplido.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        s = ReporteSerializer(data=request.query_params)
        if not s.is_valid():
            return Response({"error": "FILTRO_INVALIDO", "detalle": s.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        d = s.validated_data
        return Response(indicadores.reporte(
            request.org, d["reporte"], desde=d.get("desde"),
            hasta=d.get("hasta"), dias=d.get("dias")))
