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

from django.db import transaction
from django.db.models import Case as CuandoSQL
from django.db.models import IntegerField, When
from django.db.utils import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import Profile
from common.permissions import HasOrgContext
from django.http import Http404
from django.utils import timezone

from operaciones import (actividades, asistentes, auditoria, chat,
                         contexto_propuesta, correlacion,
                         fuentes, indicadores,
                         supervisor)
from operaciones.capacidad import capacidad_de_jornada
from campo.services.idempotencia import manejar_idempotencia
from operaciones.chat_modelos import ConversacionSupervisor, RolMensaje
from operaciones.models import (ActividadOperativa, DisponibilidadTecnico, ProgramacionOrden,
                                ProgramacionSemanal, PropuestaSupervisor)
from operaciones.situaciones_modelos import SituacionOperativa
from operaciones.programacion import (ErrorProgramacion, PlanIncoherente,
                                      PlanNoCerrable, PlanNoPublicable,
                                      cerrar_programacion, _lineas_vigentes,
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
    CrearProgramacionSerializer,
    ProgramacionSemanalSerializer,
    PropuestaDetalleSerializer,
    PropuestaListaSerializer,
    RevisionSerializer,
)
from operaciones.programacion import ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS


#: Cuantas propuestas viajan en una respuesta. El tope existe para no mandar
#: miles de filas a una pantalla; lo que NO puede hacer es esconder trabajo
#: sin revisar, y por eso el orden pone primero lo que espera decision.
LOTE_MAXIMO = 200


class PropuestasView(APIView):
    """
    Las propuestas de esta organización: primero las que esperan una
    decisión, y dentro de cada grupo las más urgentes.
    """

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
        #  LO QUE ESPERA UNA DECISION VIAJA PRIMERO  --  06/10/2026
        #  --------------------------------------------------------
        #  El orden del modelo es ("prioridad", "-created_at") y el tope es de
        #  200. Las dos cosas estaban bien por separado y juntas escondian
        #  trabajo: medido en produccion ese dia, de 260 propuestas las 10 que
        #  esperaban revision caian en las posiciones 211 a 225 --prioridad 32
        #  a 40-- y NO llegaban al navegador. La pantalla decia "Pendientes
        #  (0)" con diez casos abiertos esperando, y "Todas (200)" era el
        #  unico rastro del corte.
        #
        #  Urgencia y pendiente son cosas distintas: una propuesta ya aceptada
        #  puede tener prioridad 1 y una pendiente prioridad 40. Ordenar por
        #  urgencia y despues cortar deja que lo ya decidido desplace a lo que
        #  falta decidir.
        #
        #  Esto NO cambia que es pendiente ni esconde nada: dentro de cada
        #  grupo sigue mandando la misma urgencia de siempre. Lo unico que
        #  garantiza es que el tope solo pueda recortar lo YA revisado.
        qs = qs.annotate(
            _espera_decision=CuandoSQL(
                When(estado=PropuestaSupervisor.PROPUESTA, then=0),
                default=1, output_field=IntegerField(),
            )
        ).order_by("_espera_decision", "prioridad", "-created_at")

        # El lote se materializa UNA vez: el contexto se resuelve sobre las
        # mismas filas que se serializan, no sobre una segunda consulta que
        # podria devolver otras si algo se inserto en el medio.
        total = qs.count()
        lote = list(qs[:LOTE_MAXIMO])
        contexto = contexto_propuesta.contexto_de(request.org, lote)
        return Response({
            "count": total,
            #  Que el corte se SEPA. Una lista recortada en silencio es lo que
            #  produjo este defecto: quien la lee no puede distinguir "no hay
            #  mas" de "no te las mande".
            "truncado": total > len(lote),
            "resultados": PropuestaListaSerializer(
                lote, many=True, context={"contexto": contexto}
            ).data,
        })


class ActividadSupervisorView(APIView):
    """
    Los últimos hechos del módulo, para el feed del tablero.

    SOLO LEE. No corre el ciclo, no crea propuestas y no cambia ningún estado:
    abrir un tablero no debe producir trabajo, la misma regla que ya sigue
    IndicadoresView.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        try:
            limite = int(request.query_params.get("limite", 20))
        except (TypeError, ValueError):
            limite = 20
        limite = max(1, min(limite, 100))

        filas = auditoria.recientes(request.org, limite)
        return Response({
            "count": len(filas),
            "resultados": [
                {
                    "id": str(f.id),
                    "accion": f.action,
                    "entidad": f.entity_type,
                    "entidad_id": str(f.entity_id) if f.entity_id else "",
                    "nombre": f.entity_name or "",
                    # 'user=None' significa que el autor fue la IA, y se
                    # reconoce por eso -- no por un usuario de sistema
                    # inventado que despues se confunda con una persona.
                    "quien": (f.user.user.email
                              if f.user and f.user.user else "Supervisor NOC IA"),
                    "es_ia": f.user is None,
                    "cuando": f.created_at.isoformat(),
                    "descripcion": f.description or "",
                }
                for f in filas
            ],
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

    ACEPTAR REGISTRA LA DECISIÓN; PARA UN TIPO, ADEMÁS INTENTA EL CIERRE
    -------------------------------------------------------------------
    Hasta el cierre controlado, aceptar no ejecutaba nada y este docstring lo
    decía así. Hoy es cierto para todos los tipos MENOS uno: con
    'caso_desincronizado', una vez persistida la revisión se intenta cerrar el
    caso en Dexter -- se revalidan las doce condiciones y, si siguen dándose, el
    caso se cierra. Nunca se toca el sistema del proveedor.

    Y sigue valiendo lo que importa: ACEPTADA no es CERRADA. El intento ocurre
    FUERA de la transacción de la revisión, así que un fallo no revierte la
    decisión humana. La respuesta lo dice con 'ejecutada', 'motivo' y 'aviso',
    para que nadie que use esta API confunda las dos cosas.
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

        #  EL CIERRE VA DESPUES, Y FUERA DE LA TRANSACCION DE 'revisar'
        #  ------------------------------------------------------------
        #  'supervisor.revisar' ya cerro su transaccion aca arriba, asi que la
        #  decision humana esta PERSISTIDA antes de que se intente nada. El
        #  orden importa por dos motivos: una llamada de red dentro de esa
        #  transaccion mantendria la fila bloqueada todo su tiempo, y un fallo
        #  haria rollback de una decision que SI se tomo.
        #
        #  Consecuencia que la pantalla tiene que poder contar: "aceptada" y
        #  "cerrada" son dos hechos distintos, y el segundo puede no ocurrir.
        cierre = None
        if (propuesta.estado == PropuestaSupervisor.ACEPTADA
                and propuesta.tipo_senal == PropuestaSupervisor.CASO_DESINCRONIZADO):
            from operaciones import cierre_de_caso
            cierre = cierre_de_caso.cerrar(propuesta, actor=request.profile)
            propuesta.refresh_from_db()

        cuerpo = {
            "propuesta": PropuestaDetalleSerializer(propuesta).data,
            #  'ejecutada' ya lo consume el frontend y conserva su significado:
            #  si una accion salio de verdad. Para todo lo que no es un cierre
            #  de caso sigue siendo False, que es la verdad -- el Supervisor
            #  observa y recomienda, y esta es la unica accion que ejecuta.
            "ejecutada": bool(cierre and cierre.get("cerrado")),
            "motivo": (cierre or {}).get("motivo", ""),
            "detalle": (cierre or {}).get("detalle", ""),
        }
        if cierre is None:
            cuerpo["aviso"] = ("La decisión quedó registrada y auditada. "
                               "Ninguna acción se ejecutó.")
        elif cierre.get("cerrado"):
            cuerpo["aviso"] = "El caso quedó cerrado en Dexter."
        else:
            #  El motivo viaja aparte y en clave: la pantalla decide como
            #  decirlo, y no tiene que interpretar prosa para distinguir "el
            #  sistema esta detenido" de "el caso cambio".
            cuerpo["aviso"] = ("La decisión quedó registrada, pero el caso NO "
                               "se cerró.")
        return Response(cuerpo)

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


class ProgramacionesView(APIView):
    """
    ================================================================================
     LOS PLANES SEMANALES DE LA ORGANIZACION
    ================================================================================

        GET  /api/operaciones/programacion/     los planes que existen
        POST /api/operaciones/programacion/     crear el de una semana

    QUE BRECHA CIERRA
    -----------------
    'POST /api/campo/trabajos/<pk>/programar/' exige 'programacion_semanal_id',
    y hasta hoy no habia forma de AVERIGUAR ese id por la API: la pantalla solo
    podia pedirle al usuario que escribiera un UUID a mano. Esto lo lista.

    NO PROGRAMA NADA
    ----------------
    Es un GET y solo un GET. No crea planes, no los publica, no los cierra, no
    agrega lineas y no toca ninguna orden. La unica escritura del dominio sigue
    viviendo en 'programar_orden' y en 'publicar_programacion'.

    LAS DOS REGLAS SE LEEN DE DONDE VIVEN, NO SE COPIAN
    ---------------------------------------------------
    Un plan 'cerrado' no admite ordenes nuevas -- eso ya lo decide
    'ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS' en operaciones/programacion.py, y es
    la MISMA constante que usa el servicio al programar. Aca solo se expone
    ('admite_lineas' del serializer) y se ofrece como filtro opcional. No hay
    un segundo criterio que pueda quedar desincronizado con el primero.

    LA ORGANIZACION NO SE ELIGE
    ---------------------------
    Sale de 'request.org', que el middleware saca del JWT firmado. No se lee
    ningun 'organization_id' ni 'org' de la querystring: un parametro que no se
    consulta no se puede usar para cruzar empresas. Mismo criterio que
    DisponibilidadView y que ProgramarSerializer, que directamente no declara
    el campo.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        #  El filtro por organizacion va SIEMPRE y no depende de la RLS: hoy el
        #  runtime conecta con un rol que la atraviesa (ver B-7), asi que esta
        #  linea es la que de verdad aisla.
        qs = ProgramacionSemanal.objects.filter(org=request.org)

        #  Filtros OPCIONALES. Un 'estado' que no existe en el catalogo no se
        #  traduce ni se corrige: devuelve vacio, que es la respuesta honesta a
        #  "planes en un estado que ninguno tiene".
        estado = request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        if request.query_params.get("admite_lineas") in ("1", "true", "si"):
            qs = qs.filter(estado__in=ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS)

        #  El mismo orden que ya declara el modelo ('ordering = [-semana_inicio]'),
        #  con 'id' de desempate para que dos lecturas iguales devuelvan la misma
        #  lista. La restriccion unique(org, semana_inicio) hace que dentro de una
        #  organizacion no pueda haber empate real: el segundo criterio es una
        #  garantia, no una conducta que se vea todos los dias.
        qs = qs.order_by("-semana_inicio", "id")

        return Response({
            "count": qs.count(),
            "resultados": ProgramacionSemanalSerializer(qs[:500], many=True).data,
        })

    @manejar_idempotencia
    def post(self, request):
        """
        Crea el plan de una semana. Nace en BORRADOR, siempre.

        POR QUE ESTA RUTA EXISTE
        ------------------------
        Hasta hoy un plan semanal solo se podia crear desde el admin de Django.
        El efecto medible: CERO planes en produccion, y con eso todo M03
        bloqueado -- 'programar_orden' exige un 'programacion_semanal_id' que no
        existia, asi que ninguna orden podia programarse desde la aplicacion.

        EL ESTADO NO SE ELIGE
        ---------------------
        Nace borrador y punto. Publicar es una decision posterior, con su
        propia ruta, su actor y su sello ('publicada_por', 'publicada_en'), y
        con la comprobacion de coherencia delante. Aceptar 'estado' en el
        cuerpo permitiria crear un plan ya publicado sin que nadie lo revisara.

        SI YA EXISTE, SE DICE CUAL  --  y no se crea otro
        -------------------------------------------------
        La base lo impide con unique(org, semana_inicio), pero un 500 de
        IntegrityError no le sirve a nadie: se contesta 409 CON EL PLAN QUE YA
        ESTA, para que quien llamo pueda usarlo en vez de reintentar a ciegas.
        Es el mismo criterio que 'YaProgramada' en campo.

        LA CARRERA, CERRADA DONDE DE VERDAD OCURRE
        ------------------------------------------
        Entre comprobar "no existe" y crear cabe otra peticion identica. No se
        resuelve con un 'select' previo --ahi es justo donde vive la carrera--
        sino dejando que la restriccion de la base decida: se intenta crear y,
        si la base lo rechaza, se lee el que gano. Mismo patron que
        'asistente.operaciones_externas' en el motor.
        """
        entrada = CrearProgramacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        try:
            with transaction.atomic():
                plan = ProgramacionSemanal.objects.create(
                    org=request.org,
                    semana_inicio=datos["semana_inicio"],
                    #  El estado NO viene del cuerpo: es el default del modelo.
                    estado=ProgramacionSemanal.BORRADOR,
                    notas=datos.get("notas", ""),
                )
        except IntegrityError:
            existente = ProgramacionSemanal.objects.filter(
                org=request.org, semana_inicio=datos["semana_inicio"]).first()
            return Response(
                {"error": "YA_EXISTE",
                 "detalle": (f"Ya hay un plan para la semana del "
                             f"{datos['semana_inicio']}."),
                 "programacion": (ProgramacionSemanalSerializer(existente).data
                                  if existente else None)},
                status=status.HTTP_409_CONFLICT)

        return Response(
            {"programacion": ProgramacionSemanalSerializer(plan).data,
             "aviso": ("Creado en borrador. No programa ninguna orden y no "
                       "compromete a nadie hasta que se publique."),
             "server_time": timezone.now().isoformat()},
            status=status.HTTP_201_CREATED)



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


class CerrarProgramacionView(APIView):
    """
    ================================================================================
     CERRAR UN PLAN SEMANAL  --  el ultimo paso del ciclo
    ================================================================================

        POST /api/operaciones/programacion/<uuid:programacion_id>/cerrar/

    POR QUE EXISTE
    --------------
    'cerrada' estaba declarada en ESTADOS desde M03 y ninguna funcion la
    asignaba nunca. Un estado inalcanzable es una promesa que el modelo no
    cumple: la semana pasada seguia figurando como 'publicada' para siempre.
    Es el mismo hueco que tenia el cierre de una ORDEN, y se cierra igual --
    con una transicion explicita sobre el servicio, no con un UPDATE suelto.

    NO EJECUTA NADA
    ---------------
    No toca las lineas del plan, ni 'programada_para', ni el estado de ninguna
    orden. Igual que publicar: lo unico que cambia es que el plan deja de estar
    vigente. Una orden a medias sigue a medias, y su cierre es otra operacion.

    DOS CIERRES NO PRODUCEN DOS EFECTOS
    -----------------------------------
    El segundo contesta 409 y no vuelve a escribir: el propio estado es el
    registro de que la operacion ya ocurrio (misma idempotencia semantica que
    publicar). Y sobre el reintento de red actua ademas 'manejar_idempotencia'.
    ================================================================================
    """

    permission_classes = [EsJefeDeOperaciones]

    @manejar_idempotencia
    def post(self, request, programacion_id):
        #  Acotado a request.org: un id de otra organizacion no da 403 --eso
        #  confirmaria que existe-- sino que no aparece.
        plan = ProgramacionSemanal.objects.filter(
            id=programacion_id, org=request.org).first()
        if plan is None:
            return Response(
                {"error": "NO_EXISTE",
                 "detalle": "No existe ese plan semanal en esta organización."},
                status=status.HTTP_404_NOT_FOUND)

        try:
            cerrado = cerrar_programacion(
                org=request.org, programacion=plan, actor=request.profile)
        except PlanNoCerrable as e:
            #  409 y no 400: la peticion es correcta, el conflicto es con el
            #  estado actual del plan.
            return Response({"error": "NO_SE_PUEDE_CERRAR", "detalle": str(e),
                             "estado_actual": plan.estado},
                            status=status.HTTP_409_CONFLICT)
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_CERRAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "programacion": ProgramacionSemanalSerializer(cerrado).data,
            "lineas": _lineas_vigentes(cerrado).count(),
            "aviso": ("Cerrado. Las órdenes que quedaron a medias siguen como "
                      "estaban: cerrar el plan no cierra ningún trabajo."),
            "server_time": timezone.now().isoformat(),
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
                #  Los dos son obligatorios y no se completan solos: sin
                #  destinatario el escalamiento no llega a nadie, y no hay
                #  politica que permita elegirlo por el usuario.
                if not d.get("escalado_a_id"):
                    return Response(
                        {"error": "FALTA_DESTINATARIO",
                         "detalle": "Escalar exige 'escalado_a_id'."},
                        status=status.HTTP_400_BAD_REQUEST)
                if not d.get("nivel_escalamiento"):
                    return Response(
                        {"error": "FALTA_NIVEL",
                         "detalle": "Escalar exige 'nivel_escalamiento'."},
                        status=status.HTTP_400_BAD_REQUEST)
                #  '_perfil_o_404' ya filtra por request.org: es la misma
                #  convencion de tenancy del resto del modulo, y deja el
                #  rechazo de otra empresa como segunda barrera en el servicio.
                destino_esc = _perfil_o_404(request, d["escalado_a_id"],
                                            que="persona destinataria")
                a = actividades.escalar(
                    a, actor=actor, motivo=motivo,
                    escalado_a=destino_esc, nivel=d["nivel_escalamiento"])
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


class LatidoSupervisorView(APIView):
    """
        GET /api/operaciones/supervisor/latido/

    El SCHEDULER despierta al Supervisor y le pregunta qué ve. No escribe nada.

    POR QUE ESTA RUTA EXISTE, SI YA HAY UNA DE CICLO
    -----------------------------------------------
    `POST supervisor/ciclo/` ESCRIBE: registra propuestas, y su permiso es
    `EsJefeDeOperaciones` porque detrás hay una persona. El scheduler no es una
    persona y no debe entrar por la puerta de una: el proyecto ya tiene esa
    distinción escrita en `nucleo/seguridad/frontera.py::puerta` -- con actor se
    entra por la puerta humana, sin actor por la autónoma -- y reusar el permiso
    del Jefe para un proceso la borraría.

    Así que esta ruta hace UNA cosa, de solo lectura, con el mismo patrón de
    servicio que ya usan los endpoints de importación que llama el motor:
    `IsAuthenticated + HasOrgContext`, con la credencial acotada por scope
    (`operaciones:read`) en `common.middleware.get_company`.

    Y POR QUE NO SE REUSA `indicadores/`, QUE YA CALCULA ESTO MISMO
    --------------------------------------------------------------
    Porque `indicadores.py:346` tambien llama a `detectar()` y hasta publica
    `senales_vigentes` y `senales_por_tipo` con esta misma cadena de fuente: lo
    que devuelve este latido es un SUBCONJUNTO estricto de eso. La duplicacion
    es real y esta aqui a proposito, por dos razones que no se arreglan
    reusando:

      * `IndicadoresView` esta detras de `EsJefeDeOperaciones`. Darle esa
        credencial al scheduler seria darle a un proceso el rol de una persona,
        que es justo lo que este bloque evita.
      * devuelve el juego COMPLETO de indicadores operativos. Un turno que corre
        cada hora no necesita --ni debe arrastrar al log del motor-- mas que
        conteos.

    Lo que NO se duplico es el calculo: las tres puertas (`ciclo`,
    `indicadores`, este latido) llaman a la MISMA `supervisor.detectar()`, asi
    que no hay una segunda definicion de "senal vigente" que se desincronice.

    POR QUE `detectar()` Y NO `correr_ciclo()`
    -----------------------------------------
    `detectar()` es LECTURA pura -- lo dice su módulo y lo reusa
    `indicadores.indicadores_supervisor`: «las señales VIGENTES se detectan sin
    escribir nada». `correr_ciclo()` además registra propuestas, y este bloque
    tiene que demostrar el circuito sin producir ningún efecto.

    LO QUE DEVUELVE, Y LO QUE NO
    ----------------------------
    Conteos por tipo de señal y nada más. NO devuelve `origen_id`, ni evidencia,
    ni datos: un latido que arrastre la identidad de un caso convierte la traza
    de un turno --el informe del tick y la línea de log del motor-- en un
    registro con datos de cliente, y ninguno de los dos es lugar para eso.

    EL TENANT SE COMPRUEBA, NO SE SUPONE
    ------------------------------------
    La organización sale de la credencial (`request.org`). Si quien llama manda
    `organization_id`, tiene que COINCIDIR: así un turno del scheduler que
    apunte a otra empresa falla en vez de leer la de al lado con el token
    equivocado. Es la misma regla que `frontera.exigir` aplica al permiso.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request):
        pedida = str(request.query_params.get("organization_id") or "").strip()
        if pedida and pedida != str(request.org.id):
            #  409 y no 403: la credencial es válida, lo que no coincide es a qué
            #  empresa apunta el turno. Un 403 mandaría a revisar el token.
            return Response(
                {"error": "ORGANIZACION_DISTINTA",
                 "detalle": "el turno apunta a una organización que no es la de "
                            "esta credencial: no se lee nada"},
                status=status.HTTP_409_CONFLICT)

        leido_en = timezone.now()
        senales = supervisor.detectar(request.org)

        por_tipo: dict = {}
        for s in senales:
            por_tipo[s.tipo] = por_tipo.get(s.tipo, 0) + 1

        return Response({
            "organizacion": str(request.org.id),
            "leido_en": leido_en.isoformat(),
            "senales_vigentes": len(senales),
            "senales_por_tipo": por_tipo,
            #  Que el latido declare que no escribió viaja con la respuesta
            #  para que quien lea el informe del tick --o la línea de log del
            #  motor-- no tenga que ir al código a comprobarlo. No queda en una
            #  tabla: 'job_run' no tiene columna de salida (medido el
            #  02/10/2026, tests/test_latido_extremo_a_extremo.py).
            "escrituras": 0,
            "fuente": "operaciones.supervisor.detectar",
        })


class TurnoSupervisorView(APIView):
    """
        GET /api/operaciones/supervisor/turno/

    El RELEVO DE TURNO: las doce preguntas que alguien se hace al llegar.

    POR QUE EXISTE ESTA RUTA
    ------------------------
    Porque sin ella 'operaciones/turno.py' seria otro modulo probado y sin
    llamador -- la falla que este repositorio ya pago dos veces (el reloj de
    tareas colgado de un '__main__' que gunicorn no ejecuta, y la
    reconciliacion sin quien la llamara). Es la misma razon por la que existe
    'supervisor/coordinar/': codigo construido no es codigo que corre.

    POR QUE 'EsJefeDeOperaciones' Y NO EL PATRON DEL SCHEDULER
    ---------------------------------------------------------
    Detras de esta puerta hay una PERSONA tomando el turno, no un proceso. El
    'latido' y el 'sondeo' los llama el scheduler y por eso entran con
    'IsAuthenticated + HasOrgContext'; esta devuelve el panorama operativo
    completo --topologia, hipotesis, que falta verificar-- y va detras del
    mismo permiso que el chat y los indicadores.

    GET Y SOLO GET
    --------------
    No escribe nada, y por eso se puede pedir tantas veces como alguien quiera.
    Lo afirma la suite contando filas antes y despues
    ('test_lote1_evaluacion_turno.py::test_L3'), no este comentario.

    LA PROCEDENCIA VIAJA CON EL DATO
    --------------------------------
    Cada bloque dice si lo que trae es OBSERVADO, INFERIDO, RECOMENDADO,
    CONFIRMADO o DESCONOCIDO. No es decoracion: un INFERIDO leido como un hecho
    tres pantallas mas abajo es la forma mas barata de que un relevo de turno
    mienta. Y un DESCONOCIDO trae SIEMPRE su motivo -- 'no se sabe' no se
    reporta como cero.

    'shadow' ES OPCIONAL Y NO VIENE POR DEFECTO
    -------------------------------------------
    La evaluacion del Shadow Mode recorre decisiones y aprendizajes del
    periodo; es mas caro que el resumen y no hace falta para tomar el turno.
    Se pide con '?shadow=1'.
    """

    permission_classes = (IsAuthenticated, HasOrgContext, EsJefeDeOperaciones)

    def get(self, request):
        from operaciones import turno as turno_mod

        horas = request.query_params.get("horas")
        try:
            horas = max(1, min(int(horas), 72)) if horas else None
        except (TypeError, ValueError):
            #  Un 'horas' ilegible no es un error del turno: se contesta la
            #  ventana por defecto y se dice que se ignoro, en vez de un 400
            #  que deja a quien llega sin su relevo.
            horas = None

        cuerpo = turno_mod.resumen_de_turno(request.org, horas=horas)
        cuerpo["fuente"] = "operaciones.turno.resumen_de_turno"
        #  Que la lectura no escribio viaja con la respuesta, igual que en el
        #  latido, para que no haya que ir al codigo a comprobarlo.
        cuerpo["escrituras"] = 0

        if str(request.query_params.get("shadow") or "").strip() in ("1",
                                                                     "true"):
            cuerpo["shadow"] = turno_mod.evaluacion_shadow(request.org)

        return Response(cuerpo)


class SondeoFuentesView(APIView):
    """
        POST /api/operaciones/supervisor/sondeo/

    El SCHEDULER despierta al Supervisor y este consulta las fuentes que ya
    vencieron. Devuelve conteos y estados; no decide nada.

    POR QUE ES POST SI EL BLOQUE ES "SOLO LECTURA"
    ---------------------------------------------
    Porque "solo lectura" es respecto de los sistemas EXTERNOS: a los de afuera
    se les consulta con herramientas `solo_lectura: true` por el camino del
    motor, y a las fuentes internas con consultas al ORM. Ninguna de las seis
    escribe afuera.

    CUALES son esas fuentes, y como se consulta cada una, vive en
    `operaciones/fuentes_adaptadores.py` y no aqui: esta vista no habla con
    ningun proveedor -- le pide el sondeo a la capa de fuentes. Por eso la guarda
    de M03-E5 puede seguir exigiendo que este modulo no nombre un sistema
    externo, y sigue siendo cierto.

    Lo que SI escribe esta ruta son dos tablas PROPIAS -- el estado de cada
    fuente y su captura-- y eso es el entregable del bloque, no un efecto
    secundario: sin escribirlo no hay con que comparar el ciclo siguiente ni
    forma de distinguir "no hay nada" de "no se pudo preguntar". Un GET que
    escribe es peor que un POST honesto.

    LO QUE NO HACE, Y SE AFIRMA EN LA SUITE CONTANDO FILAS
    -----------------------------------------------------
    No crea Situaciones Operativas (no existen todavia), no crea propuestas, no
    corre `supervisor.correr_ciclo`, no toca un caso, no escala, no crea
    tickets, no llama a nada que produzca un efecto afuera y no modifica el
    interruptor de autonomia.

    CORRERLA DOS VECES SEGUIDAS NO DUPLICA NADA
    -------------------------------------------
    No por una clave de idempotencia, sino por como esta armado: al registrar
    una lectura se corre `proxima_consulta_en` hacia adelante, asi que el
    segundo sondeo no encuentra ninguna fuente vencida y no consulta nada. Es
    una propiedad del dato, no una promesa del codigo, y la suite la afirma
    contando snapshots.

    EL TENANT SE COMPRUEBA, NO SE SUPONE
    ------------------------------------
    Igual que el latido: la organizacion sale de la credencial, y si quien llama
    manda `organization_id` tiene que COINCIDIR. Un turno del scheduler apuntando
    a otra empresa falla con 409 en vez de sondear las fuentes de al lado.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        pedida = str(request.query_params.get("organization_id") or "").strip()
        if pedida and pedida != str(request.org.id):
            return Response(
                {"error": "ORGANIZACION_DISTINTA",
                 "detalle": "el turno apunta a una organización que no es la de "
                            "esta credencial: no se sondea nada"},
                status=status.HTTP_409_CONFLICT)

        #  Las filas de las seis fuentes se crean si faltan, y nacen APAGADAS.
        #  Que el sondeo las cree no las enciende: sin 'activa=True' ninguna se
        #  consulta, y encenderla es una decision de operacion.
        creadas = fuentes.asegurar_fuentes(request.org)

        ahora = timezone.now()
        informe = fuentes.sondear(request.org, ahora=ahora)
        informe["fuentes_creadas"] = len(creadas)
        informe["fuente"] = "operaciones.fuentes.sondear"

        #  Y en el MISMO turno, la deteccion y la correlacion sobre lo que acaba
        #  de capturarse. Van juntas a proposito: si corrieran en turnos
        #  distintos, una situacion se construiria sobre la foto anterior y el
        #  conteo de afectados llegaria siempre un ciclo tarde.
        #
        #  Sigue siendo UN solo scheduler y UN solo turno: esto no agenda nada.
        informe["situaciones"] = correlacion.correr(request.org, ahora=ahora)
        return Response(informe)


class ChatSupervisorView(APIView):
    """
        POST /api/operaciones/supervisor/chat/

    La conversación entre un responsable humano y el Supervisor NOC IA.

    POR QUE ES UNA RUTA DEL SUPERVISOR Y NO UN CHAT GENERICO
    -------------------------------------------------------
    Lo que la hace del Supervisor no es el nombre: es que el contexto, las
    herramientas y los límites salen de los datos del Supervisor. El modelo no
    puede consultar nada que no sea una situación, una fuente, una propuesta o
    una decisión de ESTA organización -- y el tenant lo pone el despachador de
    herramientas, no el modelo.

    POR QUE NO VA POR EL '/chat' DEL MOTOR
    --------------------------------------
    `/chat` atiende un turno de un agente del PRODUCTO (router, soporte,
    facturación, ventas): resuelve rol o perfil, arma el catálogo del tenant y
    escribe en las conversaciones de WhatsApp. CLAUDE.md §11.1 separa esa capa de
    la operativa, y el Supervisor es operativo. El motor presta el modelo por
    `/interno/supervisor/chat` y nada más.

    LO QUE NO PUEDE HACER, Y HAY UNA PRUEBA POR CADA UNO
    ---------------------------------------------------
    No cambia el estado de una situación, no toca `Case.status`, no cierra ni
    crea ni reasigna tickets, no escribe en M02 ni en M03, no activa fuentes, no
    llama a SmartOLT ni a WispHub, y no puede subir su nivel de autonomía.
    Ninguna de esas cosas tiene herramienta: no es que el prompt lo prohíba, es
    que no hay por dónde.

    PERMISO: el mismo que el resto del Supervisor. Ver el panorama operativo de
    una empresa --qué está caído, qué técnicos tienen compromisos-- no es
    información para cualquiera con una sesión.
    """

    permission_classes = (IsAuthenticated, HasOrgContext, EsJefeDeOperaciones)

    #  Cuantos mensajes se devuelven al abrir la burbuja. El mismo numero que
    #  manda la ruta del frontend; aca esta el TOPE, porque un limite que solo
    #  vive del lado del navegador no es un limite.
    TOPE_HISTORIAL = 200

    def get(self, request):
        """
        El hilo persistido de esta persona, para que la burbuja no lo pierda.

        POR QUE EXISTE ESTE GET
        -----------------------
        La conversacion ya se guardaba --'ConversacionSupervisor' y
        'MensajeSupervisor' existen desde P5-- y no habia forma de leerla: al
        recargar la pantalla el hilo desaparecia de la vista aunque siguiera en
        la base. La rama que traia la burbuja SI recuperaba el historial, pero
        contra el hilo del motor. Al adoptar el Supervisor dedicado habia que
        conservar esa propiedad, y por eso se agrega aca.

        LOS ROLES SE TRADUCEN AQUI, NO EN EL FRONTEND
        ---------------------------------------------
        'aBurbujas' (lib/supervisor/chat-sesion.js) espera 'user'/'assistant', y
        esta tabla guarda 'humano'/'supervisor'/'herramienta'/'error'. La
        traduccion vive de este lado para no tocar ese archivo ni sus pruebas:
        el contrato del componente queda intacto.

        QUE NO DEVUELVE, Y SE DICE EN VEZ DE ESCONDERLO
        ----------------------------------------------
        Los turnos de rol 'herramienta' y 'error' NO salen. Los de herramienta
        son el detalle interno del bucle --el modelo los necesita, una persona
        no-- y los de error no tienen traduccion honesta: mandarlos como
        'assistant' los haria leer como una respuesta del Supervisor, que es
        justo lo contrario de lo que son. Quedan GUARDADOS y visibles en la
        auditoria; lo que no hacen es volver a la burbuja. Es una perdida
        declarada, no un olvido.

        ES LECTURA. No abre conversacion si no hay: devuelve la lista vacia.
        Crear un hilo porque alguien abrio una pantalla dejaria conversaciones
        sin un solo mensaje.
        """
        from operaciones.chat_modelos import (ConversacionSupervisor,
                                              MensajeSupervisor, RolMensaje)

        try:
            limite = int(request.query_params.get("limite") or 60)
        except (TypeError, ValueError):
            limite = 60
        limite = max(1, min(limite, self.TOPE_HISTORIAL))

        #  El hilo de ESTA persona en ESTA empresa. Los dos filtros, siempre:
        #  sin 'actor' se leeria la conversacion de un companero.
        conversacion = (ConversacionSupervisor.objects
                        .filter(org=request.org, actor=request.profile)
                        .order_by("-ultimo_mensaje_en")
                        .first())
        if conversacion is None:
            return Response({"conversacion_id": None, "mensajes": []})

        #  Se piden los ULTIMOS 'limite' y se devuelven en orden cronologico:
        #  un hilo que llega al reves no se puede pintar.
        traduccion = {RolMensaje.HUMANO: "user",
                      RolMensaje.SUPERVISOR: "assistant"}
        filas = list(MensajeSupervisor.objects
                     .filter(org=request.org, conversacion=conversacion,
                             rol__in=tuple(traduccion))
                     .order_by("-escrito_en", "-created_at")[:limite])
        filas.reverse()

        return Response({
            "conversacion_id": str(conversacion.id),
            "mensajes": [{"id": str(m.id),
                          "rol": traduccion[m.rol],
                          "contenido": m.contenido,
                          "creado_en": m.escrito_en.isoformat()}
                         for m in filas],
            "fuente": "operaciones.chat_modelos.MensajeSupervisor",
        })

    def post(self, request):
        datos = request.data if isinstance(request.data, dict) else {}
        texto = str(datos.get("mensaje") or "").strip()
        if not texto:
            return Response({"error": "FALTA_MENSAJE"},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(texto) > 4000:
            return Response({"error": "MENSAJE_DEMASIADO_LARGO"},
                            status=status.HTTP_400_BAD_REQUEST)

        #  La conversación se resuelve SIEMPRE dentro de la organización y del
        #  actor. Un id de conversación de otra empresa --o de otra persona-- no
        #  da 403: da 404, porque un 403 confirmaría que ese hilo existe.
        conversacion = None
        if datos.get("conversacion_id"):
            conversacion = ConversacionSupervisor.objects.filter(
                id=datos["conversacion_id"], org=request.org,
                actor=request.profile).first()
            if conversacion is None:
                return Response({"error": "CONVERSACION_NO_ENCONTRADA"},
                                status=status.HTTP_404_NOT_FOUND)

        #  El contexto inicial, cuando el chat se abre desde una situación.
        situacion = None
        if datos.get("situacion"):
            situacion = SituacionOperativa.objects.filter(
                org=request.org, codigo=str(datos["situacion"]).strip()).first()
            if situacion is None:
                return Response({"error": "SITUACION_NO_ENCONTRADA"},
                                status=status.HTTP_404_NOT_FOUND)

        if conversacion is None:
            conversacion = chat.abrir(
                request.org, request.profile, situacion=situacion,
                caso_id=str(datos.get("caso") or "")[:64])
        elif situacion is not None and conversacion.situacion_id != situacion.id:
            #  Cambiar de tema en un hilo que ya existe queda ESCRITO en el hilo:
            #  sin eso, dos respuestas sobre situaciones distintas quedarían
            #  seguidas sin nada que explique el salto.
            chat.cambiar_contexto(conversacion, situacion=situacion)

        try:
            respuesta = chat.responder(conversacion, texto)
        except chat.ErrorChat as e:
            return Response({"error": "TURNO_NO_COMPLETADO",
                             "detalle": str(e)},
                            status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            "conversacion_id": str(conversacion.id),
            "contexto": {
                "situacion": (conversacion.situacion.codigo
                              if conversacion.situacion_id else None),
                "caso": conversacion.caso_id or None,
            },
            "respuesta": respuesta.contenido,
            "es_error": respuesta.rol == RolMensaje.ERROR,
            #  Qué consultó para contestar. Va al cliente a propósito: una
            #  respuesta del Supervisor sin poder ver de dónde salió es una
            #  afirmación sin respaldo.
            "herramientas": [h.get("nombre") for h in (respuesta.herramientas or [])],
            "duracion_ms": respuesta.duracion_ms,
        })


class CoordinarSupervisorView(APIView):
    """
    El Supervisor PIDE trabajo a M02 a partir de una situación. Con la puerta.

    POR QUE ESTA RUTA EXISTE
    ------------------------
    P6 construyó la coordinación completa y no dejó ninguna forma de alcanzarla:
    `operaciones/coordinacion.py` no tenía endpoint ni trabajo del scheduler, así
    que lo único que la ejercitaba eran sus 42 pruebas. Es exactamente lo que
    CLAUDE.md §6 llama «código construido no es código que corre»: no daba error,
    no daba log, y no servía para nada.

    POR QUE PIDE AUTONOMÍA SI LA APRIETA UNA PERSONA
    ------------------------------------------------
    Esta es la parte que hay que entender para no confundirla con un permiso.
    Quien llama es una persona con rol de gestión; lo que actúa es el SUPERVISOR.
    Una persona que quiere abrir una actividad a mano ya tiene su camino
    (`POST actividades/`), que no consulta autonomía ninguna y es correcto que no
    lo haga. Aquí la actividad la pide el Supervisor a partir de SU lectura de la
    situación, así que la barrera que decide no es el rol de quien aprieta: es la
    autonomía efectiva del agente.

    Por eso un 'no' de autonomía NO es 403 --la persona sí tiene permiso-- sino
    409: el estado del sistema impide la operación. Mismo criterio que
    `TRANSICION_INVALIDA` y `ACTIVIDAD_DUPLICADA`, que ya usan 409 en este módulo.

    LO QUE ESTA RUTA NO HACE
    ------------------------
    No toca M03: no reprograma, no resecuencia, no reasigna. No cierra la
    situación ni le cambia el estado. No ejecuta la actividad que crea --crear no
    es hacer, y hacer no es validar--. Y no eleva autonomía: `coordinacion.py` no
    nombra `autonomia.cambiar` en ninguna parte, y hay una prueba que lo afirma
    sobre el AST.
    """

    permission_classes = (IsAuthenticated, HasOrgContext, EsJefeDeOperaciones)

    @manejar_idempotencia
    def post(self, request):
        from operaciones import coordinacion
        from operaciones.serializers import CoordinarSupervisorSerializer

        s = CoordinarSupervisorSerializer(data=request.data)
        if not s.is_valid():
            return Response({"error": "CUERPO_INVALIDO", "detalle": s.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        d = s.validated_data

        situacion = (SituacionOperativa.objects
                     .filter(org=request.org,
                             codigo=d["situacion"].strip()).first())
        if situacion is None:
            #  404 y no 403, igual que en el chat: decir «existe pero no es tuya»
            #  ya confirmaría que existe.
            return Response({"error": "SITUACION_NO_ENCONTRADA"},
                            status=status.HTTP_404_NOT_FOUND)

        responsable = None
        if d.get("responsable_id"):
            responsable = (Profile.objects
                           .filter(org=request.org,
                                   id=d["responsable_id"]).first())
            if responsable is None:
                return Response({"error": "RESPONSABLE_NO_ENCONTRADO"},
                                status=status.HTTP_404_NOT_FOUND)

        comunes = dict(actor=request.profile, responsable=responsable,
                       area=d.get("area", ""),
                       condicion_exito=d["condicion_exito"],
                       vence_en=d.get("vence_en"))
        try:
            if d["clase"] == CoordinarSupervisorSerializer.EVIDENCIA:
                salida = coordinacion.solicitar_evidencia(
                    situacion, clase=d["clase_evidencia"],
                    detalle=d["detalle"], **comunes)
            else:
                salida = coordinacion.solicitar_actividad(
                    situacion, tipo=(d.get("tipo")
                                     or ActividadOperativa.TAREA),
                    titulo=d["titulo"], objetivo=d["objetivo"], **comunes)
        except coordinacion.CoordinacionNoPermitida as e:
            #  El veredicto viaja COMPLETO: quien recibe el 409 tiene que poder
            #  decir por qué no, y «no se pudo» no explica nada.
            return Response({"error": "AUTONOMIA_INSUFICIENTE",
                             "detalle": str(e),
                             "veredicto": e.veredicto},
                            status=status.HTTP_409_CONFLICT)
        except coordinacion.CoordinacionInvalida as e:
            return Response({"error": "COORDINACION_INVALIDA",
                             "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        except actividades.ErrorActividad as e:
            #  'actividades.ErrorActividad' y NO el nombre suelto: ese nombre no
            #  está importado en este archivo, y el resto lo nombra así (1164,
            #  1282). Escrito suelto, este 'except' daba 'NameError' y la
            #  respuesta un 500. Lo encontró 'ruff' con F821 antes que ninguna
            #  prueba, porque ningún cuerpo válido llega hasta aquí.
            return _error_actividad(e)

        actividad = salida["actividad"]
        return Response({
            "actividad": ActividadOperativaSerializer(actividad).data,
            "situacion": situacion.codigo,
            #  'repetida' viaja a propósito: que M02 ya tuviera una viva para
            #  esta situación y este tipo NO es un error, es la idempotencia de
            #  dominio haciendo su trabajo. Quien llama tiene que poder
            #  distinguir «abrí una» de «ya estaba abierta».
            "repetida": salida["repetida"],
            "evento": str(salida["evento"].id),
            "nivel_efectivo": salida["veredicto"].get("efectivo"),
            "server_time": timezone.now().isoformat(),
        }, status=(status.HTTP_200_OK if salida["repetida"]
                   else status.HTTP_201_CREATED))


class ResultadoDecisionView(APIView):
    """
    Registra QUE PASO con una decision. La entrada es la PROPUESTA.

    POR QUE LA RUTA CUELGA DE LA PROPUESTA Y NO DE LA DECISION
    ----------------------------------------------------------
    Porque la propuesta es el objeto que una persona ve y que el tablero ya
    lista; la decisión es su consecuencia. Montar `decisiones/<id>/` obligaría a
    la pantalla a conocer un id que hoy no muestra en ninguna parte, para no
    ganar nada: cada propuesta revisada tiene exactamente una decisión.

    LO QUE ESTA RUTA NO HACE
    ------------------------
    No cambia el estado de la propuesta --ya fue revisada-- ni el de la
    situación. No convierte «aceptada» en «exitosa»: el resultado lo decide
    quien aporta la evidencia, y sin evidencia no entra. Y no la puede llamar el
    Supervisor: exige una persona autenticada con rol de gestión, porque un
    agente que escribe su propio resultado se declara correcto solo.
    """

    permission_classes = (IsAuthenticated, HasOrgContext, EsJefeDeOperaciones)

    @manejar_idempotencia
    def post(self, request, propuesta_id):
        from operaciones import gobierno
        from operaciones.models import DecisionSupervisor
        from operaciones.serializers import ResultadoDecisionSerializer

        s = ResultadoDecisionSerializer(data=request.data)
        if not s.is_valid():
            return Response({"error": "CUERPO_INVALIDO", "detalle": s.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        d = s.validated_data

        #  La decisión se busca POR ORG además de por propuesta: el filtro de
        #  tenant va en el queryset y no en una comprobación posterior.
        decision = (DecisionSupervisor.objects
                    .filter(org=request.org, propuesta_id=propuesta_id)
                    .order_by("-decidida_en").first())
        if decision is None:
            return Response({"error": "DECISION_NO_ENCONTRADA",
                             "detalle": "esta propuesta no tiene una decisión "
                                        "registrada: primero hay que revisarla"},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            fresca = gobierno.registrar_resultado(
                decision, actor=request.profile, resultado=d["resultado"],
                evidencia=d["evidencia"], correccion=d.get("correccion", ""))
        except gobierno.DesenlaceIncompatible as e:
            #  409: el estado del sistema impide la operación. No es un cuerpo
            #  inválido ni una falta de permiso.
            return Response({"error": "DESENLACE_YA_REGISTRADO",
                             "detalle": str(e)},
                            status=status.HTTP_409_CONFLICT)
        except gobierno.ErrorGobierno as e:
            return Response({"error": "RESULTADO_INVALIDO",
                             "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "decision": str(fresca.id),
            "propuesta": str(propuesta_id),
            "tipo_decision": fresca.tipo,
            "resultado": fresca.resultado,
            "resultado_en": fresca.resultado_en.isoformat(),
            "hubo_correccion": bool(fresca.correccion),
            #  Qué lección dejó, si dejó alguna. Puede ser ninguna, y eso NO es
            #  un error: 'aceptada + falló' no prueba que no hubiera problema.
            "aprendizajes": [
                {"tipo": a.tipo, "conclusion": a.conclusion}
                for a in fresca.aprendizajes.all()],
            "server_time": timezone.now().isoformat(),
        })


class EstiloSupervisorView(APIView):
    """
        GET  /api/operaciones/supervisor/estilo/
        PUT  /api/operaciones/supervisor/estilo/

    EL ESTILO DEL PROMPT, editable por la empresa.

    POR QUE EXISTE
    --------------
    Porque afinar el tono, el largo o que se muestra son cosas que se hacen
    veinte veces hasta que quedan bien, y veinte commits con despliegue para eso
    es desproporcionado. Y porque §3.3 de CLAUDE.md lo pide: lo que varia por
    empresa es configuracion editable y persistida por tenant, nunca un valor
    fijo en codigo.

    QUE SE PUEDE EDITAR POR AQUI, Y QUE NO
    --------------------------------------
    Solo el bloque de ESTILO: como habla, cuanto escribe, que muestra. El
    NUCLEO --la identidad, los limites, el "jamas inventas", el "nunca presentas
    una hipotesis como un hecho"-- sigue en codigo y no se alcanza desde aqui.

    El corte no es estetico: EL CHAT NO PASA POR 'cerebro.validar()'. Usa
    'razonar' y no 'concluir', asi que las cinco garantias no corren en ese
    camino y lo que sostiene el "jamas inventas" es el texto. Dejarlo editable
    seria poner una garantia detras de un formulario.

    'test_estilo' lo afirma sobre el EFECTO: compone el prompt con un estilo que
    intenta contradecir el nucleo, y verifica que el nucleo siga completo.

    MISMO PERMISO QUE EL CHAT Y LOS INDICADORES
    -------------------------------------------
    'EsJefeDeOperaciones'. Detras de esta puerta hay una persona cambiando como
    habla el Supervisor de SU empresa.

    EL PUT EXIGE MOTIVO, Y NO ES BUROCRACIA
    ---------------------------------------
    Un prompt que empeora las respuestas hay que poder discutirlo despues, y
    para eso hace falta saber quien lo cambio y que buscaba. Sin eso la unica
    salida es volver al por defecto a ciegas. Mismo criterio que
    'autonomia.cambiar'.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        """El estilo vigente de cada ambito, el por defecto, y el historial."""
        from operaciones import estilo as svc_estilo
        from operaciones.estilo_modelos import AmbitoEstilo

        return Response({
            "ambitos": [{
                "ambito": a,
                "etiqueta": dict(AmbitoEstilo.ETIQUETAS)[a],
                "vigente": svc_estilo.vigente(request.org, a),
                "por_defecto": svc_estilo.POR_DEFECTO[a],
                "es_el_por_defecto": svc_estilo.es_el_por_defecto(request.org, a),
            } for a in AmbitoEstilo.TODOS],
            "tope_caracteres": svc_estilo.TOPE_TEXTO,
            "historial": svc_estilo.historial(request.org),
            #  Se devuelve el nucleo para MOSTRARLO, no para editarlo: quien
            #  ajusta el estilo necesita ver contra que esta escribiendo. La
            #  pantalla lo presenta como solo lectura.
            "nucleo_solo_lectura": _nucleo_de_ambito(),
        })

    def put(self, request):
        """Cambia el estilo de un ambito. Exige texto y motivo."""
        from operaciones import estilo as svc_estilo

        ambito = str(request.data.get("ambito") or "").strip()
        texto = request.data.get("texto")
        motivo = str(request.data.get("motivo") or "").strip()
        restablecer = bool(request.data.get("restablecer"))

        actor = getattr(request, "profile", None) or getattr(
            request.user, "profile", None)
        if actor is None:
            return Response(
                {"detail": "no se pudo determinar quien hace el cambio"},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            if restablecer:
                fila = svc_estilo.restablecer(
                    request.org, ambito, actor=actor, motivo=motivo)
            else:
                fila = svc_estilo.cambiar(
                    request.org, ambito, texto, actor=actor, motivo=motivo)
        except svc_estilo.ErrorEstilo as e:
            return Response({"detail": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "ambito": fila.ambito,
            "vigente": fila.texto,
            "es_el_por_defecto": svc_estilo.es_el_por_defecto(
                request.org, fila.ambito),
            "cambiado_en": fila.cambiado_en.isoformat(),
        })


class CicloAutomaticoView(APIView):
    """
    El ciclo del Supervisor, disparado por el RELOJ y no por una persona.

    POR QUE UNA RUTA PROPIA Y NO LA DEL BOTON
    -----------------------------------------
    Porque son dos cosas distintas y conviene que se note. La del botón exige
    'EsJefeDeOperaciones' --hay alguien mirando la pantalla-- y esta exige la
    credencial de servicio del reloj, con su organización comprobada. Reusar la
    primera habría hecho que el turno del scheduler entrara con un permiso
    pensado para una persona.

    Y porque esta tiene UNA PUERTA MAS que aquella: corre solo si alguien
    delegó que corra solo. Sin eso contesta que no hizo nada, con el motivo.

    EL TENANT VIAJA Y SE COMPRUEBA, igual que en el latido: 'organization_id'
    sale de la fila del turno, no del coordinador, y se compara contra la
    organización de la credencial. Un turno de una empresa no dispara el ciclo
    de la de al lado ni con el token equivocado.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        from operaciones import tareas_delegadas as td

        pedida = str(request.data.get("organization_id") or "").strip()
        if pedida and pedida != str(request.org.id):
            #  409 y no 403, por el mismo motivo que el latido: la credencial
            #  es válida; lo que no coincide es a qué empresa apunta el turno.
            return Response(
                {"error": "ORGANIZACION_DISTINTA",
                 "detalle": "el turno apunta a una organización que no es la "
                            "de esta credencial: no se corre nada"},
                status=status.HTTP_409_CONFLICT)

        #  LA PUERTA DE ESTA RUTA. Correr el ciclo solo es una tarea que se
        #  delega, igual que cerrar casos: que el reloj SEPA hacerlo no
        #  significa que alguien lo haya pedido.
        if not td.esta_delegada(request.org, td.CICLO_AUTOMATICO):
            return Response({
                "corrio": False,
                "motivo": "NO_DELEGADO",
                "detalle": "nadie delegó que el ciclo corra solo: se pide "
                           "desde el chat del Supervisor",
            })

        resumen = supervisor.correr_ciclo(request.org)
        auto = resumen.get("cierre_automatico") or {}
        #  Se devuelve un RECORTE y no el resumen entero: esto viaja al motor,
        #  termina en su log, y el detalle de cada caso no tiene por qué cruzar
        #  esa frontera. Lo que hace falta del otro lado es saber si corrió,
        #  cuánto hizo y qué lo frenó.
        return Response({
            "corrio": True,
            "senales": resumen.get("senales", 0),
            "propuestas": resumen.get("propuestas", 0),
            "cerrados": auto.get("cerrados", 0),
            #  Los motivos por los que NO cerró. Es lo que permite contestar
            #  "corrió y no hizo nada" distinguiendo de "corrió y no pudo".
            "motivos_de_no_cierre": auto.get("motivos_de_no_cierre", {}),
        })


class AutonomiaSupervisorView(APIView):
    """
    Ver y cambiar cuanto puede hacer solo el Supervisor, desde la interfaz.

    POR QUE EXISTE (08/10/2026)
    ---------------------------
    'autonomia.cambiar' existia desde hacia semanas y NO TENIA NINGUN LLAMADOR:
    ni endpoint, ni boton. El nivel solo se podia tocar desde una consola del
    servidor. Eso se descubrio al ir a encender el cierre automatico de casos,
    cuando hubo que indicarle a una persona "anda a la pantalla de autonomia" y
    esa pantalla no existia.

    Un control que solo se opera por terminal no sirve en el momento en que mas
    se necesita, que es cuando algo esta saliendo mal y hay que pararlo rapido.

    DOS CONTROLES DISTINTOS, Y LA DIFERENCIA IMPORTA
    ------------------------------------------------
      EL NIVEL (0 a 3) vive en el CRM y dice QUE CLASE de cosas puede hacer el
      Supervisor sin pedir permiso. Cambiarlo es una decision de alcance, y por
      eso exige motivo y criterios: que se midio para decidirlo.

      EL INTERRUPTOR vive en el MOTOR, es un si/no, y es el freno de mano: lo
      tira quien ve algo raro, sin tener que explicar nada en ese momento. Vive
      aparte del nivel a proposito -- la config del tenant falla ABIERTA por dos
      caminos medidos, y un freno que se suelta solo cuando falla la base no es
      un freno.

    Tirar el interruptor NO baja el nivel, y volver a levantarlo NO lo sube: son
    dos cosas, y mezclarlas haria que reactivar devolviera silenciosamente un
    alcance que alguien habia decidido recortar.

    SUBIR EL NIVEL NO LO PUEDE HACER EL SUPERVISOR, y eso lo impone
    'autonomia.cambiar', que exige actor y lo vuelve a exigir una restriccion de
    la base. Esta vista pone la cara humana de esa regla, no la reemplaza.
    """

    permission_classes = [EsJefeDeOperaciones]

    def get(self, request):
        """El nivel vigente, el interruptor, los niveles posibles y el historial."""
        from operaciones import autonomia
        from operaciones.models import PropuestaSupervisor as P

        estado = autonomia.nivel_efectivo(request.org)
        return Response({
            "configurado": estado["configurado"],
            "efectivo": estado["efectivo"],
            "recortado": estado["recortado"],
            "motivo": estado["motivo"],
            "interruptor_permite": estado["interruptor_permite"],
            #  El techo del CODIGO, que es distinto del de la empresa: una
            #  pantalla que ofreciera subir a 4 estaria ofreciendo algo que el
            #  sistema niega siempre.
            "techo_de_la_etapa": P.NIVEL_MAXIMO_ETAPA,
            "niveles": [{"nivel": n, "etiqueta": e}
                        for n, e in P.NIVELES
                        if n <= P.NIVEL_MAXIMO_ETAPA],
            "historial": autonomia.historial(request.org, limite=20),
        })

    def put(self, request):
        """Cambia el nivel. Exige motivo y criterios, como el servicio."""
        from operaciones import autonomia

        actor = getattr(request, "profile", None) or getattr(
            request.user, "profile", None)
        if actor is None:
            return Response(
                {"detail": "no se pudo determinar quien hace el cambio"},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            nivel = int(request.data.get("nivel"))
        except (TypeError, ValueError):
            return Response({"detail": "el nivel tiene que ser un numero"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            fila = autonomia.cambiar(
                request.org, nivel, actor=actor,
                motivo=str(request.data.get("motivo") or "").strip(),
                criterios=str(request.data.get("criterios") or "").strip())
        except autonomia.ErrorAutonomia as e:
            #  El mensaje del servicio VIAJA TAL CUAL: ya explica cual de los
            #  tres requisitos falta, y reescribirlo aqui seria mantener dos
            #  textos que se desincronizan.
            return Response({"detail": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        estado = autonomia.nivel_efectivo(request.org)
        return Response({
            "configurado": fila.nivel,
            "efectivo": estado["efectivo"],
            "recortado": estado["recortado"],
            "motivo": estado["motivo"],
            "interruptor_permite": estado["interruptor_permite"],
        })

    def post(self, request):
        """
        Tira o levanta el INTERRUPTOR. El freno de mano.

        Va por el motor, que es el dueño de esa tabla: 'crm_user' no tiene
        acceso a su schema, medido en produccion el 08/10/2026. Misma frontera
        que usa la lectura.

        NO PIDE CRITERIOS, solo un motivo, y la asimetria es deliberada: subir
        el alcance exige demostrar que se midio algo; PARAR no tiene que exigir
        nada, porque quien ve humo no deberia tener que redactar un informe
        antes de apagar el fuego.
        """
        from operaciones import autonomia

        actor = getattr(request, "profile", None) or getattr(
            request.user, "profile", None)
        if actor is None:
            return Response(
                {"detail": "no se pudo determinar quien hace el cambio"},
                status=status.HTTP_400_BAD_REQUEST)

        detener = bool(request.data.get("detener"))
        motivo = str(request.data.get("motivo") or "").strip()

        try:
            resultado = autonomia.mover_interruptor(
                request.org, detener=detener, actor=actor, motivo=motivo)
        except autonomia.ErrorAutonomia as e:
            return Response({"detail": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        estado = autonomia.nivel_efectivo(request.org)
        return Response({
            "estado_interruptor": resultado.get("estado", ""),
            "configurado": estado["configurado"],
            "efectivo": estado["efectivo"],
            "interruptor_permite": estado["interruptor_permite"],
            "motivo": estado["motivo"],
        })


def _nucleo_de_ambito() -> dict:
    """
    Los dos nucleos, para que la pantalla los muestre como solo lectura.

    Se importan tarde a proposito: 'views' no deberia arrastrar 'chat' ni
    'supervisor' al cargarse, y aqui solo hacen falta cuando alguien abre la
    pantalla de estilo.
    """
    from operaciones import supervisor as sup
    from operaciones.chat import NUCLEO

    return {
        "chat": NUCLEO,
        "ciclo": sup._INSTRUCCIONES_DEL_CICLO,
    }
