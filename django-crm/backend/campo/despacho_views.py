# -*- coding: utf-8 -*-
"""
================================================================================
 LAS TRES PUERTAS QUE FALTABAN  --  crear, asignar, validar
================================================================================

El modulo campo tenia el ciclo del tecnico entero y ninguna forma de que el
trabajo entrara, se despachara o se aprobara. Lo unico que habia era el panel
de Django, que exige 'is_staff' -- la bandera de superusuario -- y que ademas
no filtra por empresa.

Estas tres usan la sesion del usuario, su rol y el mismo aislamiento por
organizacion que el resto de la API. Nadie necesita 'is_staff' para despachar
una cuadrilla.
================================================================================
"""

from __future__ import annotations

from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import Profile

from campo.models import OrdenTrabajo, WorkTypeVersion
from campo.permissions import IsCampoAuthenticated, ROLES_GESTION
from campo.serializers import (
    AgregarIntegranteSerializer,
    AsignarSerializer,
    CambiarPrincipalSerializer,
    ContingenciaSerializer,
    CrearOrdenSerializer,
    DesasignarSerializer,
    OrdenTrabajoDetailSerializer,
    ProgramarSerializer,
    ReprogramarSerializer,
    RetirarIntegranteSerializer,
    ValidarSerializer,
)
from campo.services.despacho import (
    ConflictoDeCuadrilla, ErrorDespacho, RequiereSucesor, agregar_integrante,
    asignar, cambiar_principal, contexto_del_caso, crear_orden, desasignar,
    retirar_integrante,
)
from campo.services.idempotencia import manejar_idempotencia
from campo.services.transiciones import (
    TransicionInvalidaError, aprobar, requerir_correccion,
)
from operaciones.models import ProgramacionSemanal
from operaciones.programacion import (
    ErrorProgramacion, NoEstaProgramada, PlanNoPublicable, RequiereContingencia,
    YaEnEsaFecha, YaProgramada, clasificar_ruta, programar_orden,
    registrar_contingencia, reprogramar_orden,
)


def _exigir_gestion(request):
    """
    Despachar es de quien coordina, no de quien ejecuta.

    Se devuelve 403 y no 404: el usuario TIENE acceso a este modulo, lo que no
    tiene es este permiso. El 404 estricto se reserva para cruzar empresas, que
    es donde revelar la existencia del recurso ya seria demasiado.

    Un tecnico no puede crear, asignar ni aprobar -- en particular, no puede
    aprobarse a si mismo el trabajo que acaba de hacer.
    """
    rol = (getattr(request.profile, "role", "") or "").upper()
    if rol in ROLES_GESTION or request.user.is_superuser:
        return None
    return Response(
        {"error": "PERMISO_INSUFICIENTE",
         "detalle": f"Esta accion es de {sorted(ROLES_GESTION)}."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _orden_o_404(request, pk) -> OrdenTrabajo:
    org = getattr(request, "org", None)
    if not org:
        raise Http404
    orden = OrdenTrabajo.objects.select_related(
        "tipo_trabajo_version__work_type", "org").filter(pk=pk, org=org).first()
    if not orden:
        raise Http404("No existe esa orden.")
    return orden


class CrearOrdenView(APIView):
    """Alta de orden de trabajo, desde un caso del CRM o a mano."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        s = CrearOrdenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        org = request.org

        version = WorkTypeVersion.objects.select_related("work_type").filter(
            pk=d["work_type_version_id"], work_type__org=org).first()
        if version is None:
            # 404 y no 400: una plantilla de otra empresa no debe distinguirse
            # de una que no existe.
            raise Http404("No existe esa version de plantilla.")

        case_id = (d.get("case_id") or "").strip()
        contexto = {}
        activas = []
        if case_id:
            # La ficha tecnica del caso, congelada. Nunca rompe la creacion:
            # si el motor no responde, la orden nace sin snapshot y con la
            # razon anotada adentro.
            contexto = contexto_del_caso(case_id)
            # Que la UI pueda avisar "este caso ya tiene una orden activa". No
            # se bloquea: una segunda visita al mismo caso es legitima, y lo
            # que evita el duplicado accidental es la Idempotency-Key.
            activas = list(
                OrdenTrabajo.objects.filter(
                    org=org, origen_sistema="crm", origen_ref=case_id)
                .exclude(estado_operativo__in=[OrdenTrabajo.CERRADA,
                                               OrdenTrabajo.CANCELADA])
                .values_list("numero", flat=True))

        cliente = {
            "nombre": d.get("cliente_nombre") or (contexto.get("cliente") or {}).get("nombre") or "",
            "telefono": d.get("cliente_telefono") or "",
            "direccion": d.get("cliente_direccion") or "",
            "gps_lat": d.get("gps_lat"),
            "gps_lng": d.get("gps_lng"),
        }

        try:
            orden = crear_orden(
                org=org,
                profile=request.profile,
                version=version,
                cliente=cliente,
                origen_sistema="crm" if case_id else "manual",
                origen_tipo="case" if case_id else "",
                origen_ref=case_id,
                programada_para=d.get("programada_para"),
                contexto=contexto,
            )
        except ErrorDespacho as e:
            return Response({"error": "NO_SE_PUDO_CREAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        if d.get("tecnico_profile_id"):
            tecnico = Profile.objects.filter(
                pk=d["tecnico_profile_id"], org=org).first()
            if tecnico is None:
                raise Http404("No existe esa persona.")
            try:
                asignar(orden, tecnico, request.profile)
            except ErrorDespacho as e:
                return Response({"error": "NO_SE_PUDO_ASIGNAR", "detalle": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)
            orden.refresh_from_db()

        return Response(
            {"orden": OrdenTrabajoDetailSerializer(orden).data,
             "ordenes_activas_del_caso": activas,
             "server_time": timezone.now().isoformat()},
            status=status.HTTP_201_CREATED,
        )


class AsignarTrabajoView(APIView):
    """Pone o cambia al responsable principal. Siempre deja evento."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = AsignarSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        tecnico = Profile.objects.filter(
            pk=s.validated_data["profile_id"], org=request.org).first()
        if tecnico is None:
            raise Http404("No existe esa persona.")

        try:
            asignar(orden, tecnico, request.profile,
                    rol=s.validated_data["rol"] or "tecnico",
                    motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return Response({"error": "NO_SE_PUDO_ASIGNAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                         "server_time": timezone.now().isoformat()})


class ProgramarTrabajoView(APIView):
    """
    Le pone fecha a una orden  --  paso M03-B.

    Vive aqui, junto a crear/asignar/validar, y no en una API propia: es el
    mismo recurso ('trabajos/<pk>/'), el mismo verbo operativo que 'asignar', y
    reusa las tres piezas que ya resuelven lo dificil -- el 404 estricto entre
    empresas, el permiso de gestion y la idempotencia por cabecera. Una ruta
    nueva bajo otro prefijo habria sido una segunda arquitectura para el mismo
    problema.

    El servicio vive en 'operaciones/programacion.py' por la direccion de las
    dependencias: 'operaciones' ya importa 'campo' (sus modelos tienen FK a
    OrdenTrabajo), y 'campo' no importaba 'operaciones'. Poner el servicio del
    otro lado habria cerrado el ciclo.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = ProgramarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        #  El plan se busca ACOTADO a request.org, igual que el perfil en
        #  A-3.3: un id de otra empresa no da 403 --eso confirmaria que
        #  existe-- sino que simplemente no aparece dentro de la propia.
        plan = ProgramacionSemanal.objects.filter(
            pk=d["programacion_semanal_id"], org=request.org).first()
        if plan is None:
            raise Http404("No existe ese plan semanal.")

        try:
            linea = programar_orden(
                org=request.org,
                orden=orden,
                programacion=plan,
                programada_para=d["programada_para"],
                actor=request.profile,
                zona=d.get("zona") or "",
                prioridad=d.get("prioridad"),
                secuencia=d.get("secuencia"),
                #  M03-D3: sobre un plan PUBLICADO el servicio las exige; sobre
                #  un borrador quedan vacias y no cambia nada.
                causa=d.get("causa") or "",
                motivo=d.get("motivo") or "",
            )
        except YaProgramada as e:
            #  409 y no 400: la peticion es valida, el conflicto es con el
            #  estado actual del recurso. Reprogramar es otra operacion.
            return Response(
                {"error": "YA_PROGRAMADA", "detalle": str(e),
                 "pendiente": "REPROGRAMACION"},
                status=status.HTTP_409_CONFLICT)
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_PROGRAMAR", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response(
            {"orden": OrdenTrabajoDetailSerializer(orden).data,
             "programacion": {
                 "linea": str(linea.id),
                 "programacion_semanal": str(plan.id),
                 "dia": str(linea.dia),
                 "hora_inicio": str(linea.hora_inicio),
                 "estado": linea.estado,
             },
             "aviso": ("Programado. Esto NO asigna tecnico ni calcula "
                       "capacidad: solo fija cuando se hace el trabajo."),
             "server_time": timezone.now().isoformat()},
            status=status.HTTP_201_CREATED)


class ValidarTrabajoView(APIView):
    """Aprobar el trabajo, o devolverlo diciendo que hay que rehacer."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = ValidarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            if d["decision"] == "aprobar":
                orden = aprobar(orden, profile=request.profile,
                                observacion=d["observacion"])
            else:
                orden = requerir_correccion(
                    orden, requisitos=d["requisitos_a_corregir"],
                    profile=request.profile, observacion=d["observacion"])
        except TransicionInvalidaError as e:
            return Response({"error": "VALIDACION_INVALIDA", "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                         "server_time": timezone.now().isoformat()})


class ReprogramarTrabajoView(APIView):
    """
    Cambia el CUANDO de una orden que ya tenia un cuando  --  paso M03-D3.

        POST /api/campo/trabajos/<pk>/reprogramar/

    Cubre las rutas NORMAL y CORRECCION. Si la vuelta actual ya arranco NO
    registra una contingencia por su cuenta: devuelve 409 y dice que hay que
    usar la otra ruta. Hacer algo distinto de lo que pidieron y contestar 2xx
    seria peor que rechazar.

    Vive junto a crear/asignar/validar/programar porque es el mismo recurso y
    el mismo verbo operativo, y reusa el 404 estricto entre empresas, el
    permiso de gestion y la idempotencia por cabecera.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = ReprogramarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        plan = ProgramacionSemanal.objects.filter(
            pk=d["programacion_semanal_id"], org=request.org).first()
        if plan is None:
            raise Http404("No existe ese plan semanal.")

        try:
            linea, evento, novedad = reprogramar_orden(
                org=request.org,
                orden=orden,
                programada_para=d["programada_para"],
                programacion_destino=plan,
                actor=request.profile,
                causa=d.get("causa") or "",
                motivo=d.get("motivo") or "",
                contexto=d.get("contexto") or {},
            )
        except RequiereContingencia as e:
            return Response(
                {"error": "REQUIERE_CONTINGENCIA", "detalle": str(e),
                 "ruta": clasificar_ruta(orden),
                 "siguiente": f"/api/campo/trabajos/{orden.id}/contingencia/"},
                status=status.HTTP_409_CONFLICT)
        except YaEnEsaFecha as e:
            #  [BLOQUEADO] M03-D2 dejo este caso PENDIENTE de decision
            #  empresarial. Se rechaza porque es lo REVERSIBLE: aceptarlo
            #  escribiria en una bitacora append-only un cambio que no ocurrio.
            return Response(
                {"error": "YA_EN_ESA_FECHA", "detalle": str(e),
                 "pendiente": "DECISION_EMPRESARIAL_YaEnEsaFecha"},
                status=status.HTTP_409_CONFLICT)
        except NoEstaProgramada as e:
            return Response(
                {"error": "NO_ESTA_PROGRAMADA", "detalle": str(e),
                 "siguiente": f"/api/campo/trabajos/{orden.id}/programar/"},
                status=status.HTTP_409_CONFLICT)
        except PlanNoPublicable as e:
            return Response({"error": "PLAN_NO_ADMITE_LINEAS",
                             "detalle": str(e)},
                            status=status.HTTP_409_CONFLICT)
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_REPROGRAMAR",
                             "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        orden.refresh_from_db()
        return Response({
            "orden": OrdenTrabajoDetailSerializer(orden).data,
            "programacion": {
                "linea": str(linea.id),
                "programacion_semanal": str(plan.id),
                "dia": str(linea.dia),
                "hora_inicio": str(linea.hora_inicio),
                "estado": linea.estado,
            },
            "traza": {"evento": str(evento.id), "ruta": evento.datos["ruta"],
                      "novedad": (str(novedad.id) if novedad else None)},
            "aviso": ("Reprogramado. Esto NO cambia el tecnico asignado ni el "
                      "estado del trabajo: solo cuando se hace."),
            "server_time": timezone.now().isoformat(),
        })


class ContingenciaTrabajoView(APIView):
    """
    Un trabajo EN CURSO se complico  --  paso M03-D3.

        POST /api/campo/trabajos/<pk>/contingencia/

    Registra la novedad y NO toca la programacion. 'programada_para' dice lo
    que se PLANIFICO; 'iniciada_en' y 'completada_campo_en' dicen lo que PASO.
    Reescribir el plan borraria justo la diferencia entre lo previsto y lo
    ocurrido.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = ContingenciaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        try:
            novedad, evento = registrar_contingencia(
                org=request.org, orden=orden, actor=request.profile,
                causa=d["causa"], motivo=d.get("motivo") or "",
                contexto=d.get("contexto") or {})
        except ErrorProgramacion as e:
            return Response({"error": "NO_SE_PUDO_REGISTRAR",
                             "detalle": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "contingencia": {
                "novedad": str(novedad.id),
                "evento": str(evento.id),
                "causa": novedad.tipo,
            },
            "aviso": ("Registrado. La programacion NO se modifico: un trabajo "
                      "en curso conserva la fecha que se planifico."),
            "server_time": timezone.now().isoformat(),
        }, status=status.HTTP_201_CREATED)


# ==============================================================================
#  LAS CUATRO PUERTAS DE LA CUADRILLA  --  M03-F-B
# ==============================================================================
#
#  'asignar' ya existia y significa "pon (o cambia) al responsable". Lo que
#  faltaba era poder tener una cuadrilla sin que cada persona nueva le robara
#  la principalia a la anterior -- que es lo que M03-F-A.1 midio que pasaba.
#
#  Las cuatro comparten forma con el resto del despacho: rol de gestion, 404
#  estricto al cruzar empresas, idempotencia por cabecera y la composicion
#  completa en la respuesta, para que quien opera vea como quedo la cuadrilla
#  sin tener que volver a preguntar.


def _profile_o_404(request, pid, que="persona"):
    """
    Dentro de la empresa de la sesion, o no existe. Nunca 403: confirmar que un
    UUID de otra empresa existe ya seria demasiado.
    """
    p = Profile.objects.filter(pk=pid, org=request.org).first()
    if p is None:
        raise Http404(f"No existe esa {que}.")
    return p


def _respuesta_cuadrilla(orden, **extra):
    orden.refresh_from_db()
    cuerpo = {"orden": OrdenTrabajoDetailSerializer(orden).data,
              "server_time": timezone.now().isoformat()}
    cuerpo.update(extra)
    return Response(cuerpo)


def _error_de_cuadrilla(e):
    """
    El mapeo de errores, en un solo lugar para que las cuatro puertas
    respondan igual. El orden importa: las dos primeras son subclases de
    ErrorDespacho y un 'except' generico se las tragaria.
    """
    if isinstance(e, RequiereSucesor):
        return Response({"error": "REQUIERE_SUCESOR", "detalle": str(e)},
                        status=status.HTTP_409_CONFLICT)
    if isinstance(e, ConflictoDeCuadrilla):
        return Response({"error": "CUADRILLA_CAMBIO", "detalle": str(e)},
                        status=status.HTTP_409_CONFLICT)
    return Response({"error": "NO_SE_PUDO_CAMBIAR_CUADRILLA", "detalle": str(e)},
                    status=status.HTTP_400_BAD_REQUEST)


class AgregarIntegranteView(APIView):
    """Suma a alguien a la cuadrilla. NO mueve al principal."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = AgregarIntegranteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        persona = _profile_o_404(request, s.validated_data["profile_id"])

        try:
            agregar_integrante(
                orden, persona, request.profile,
                rol=s.validated_data["rol"] or "tecnico",
                motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return _error_de_cuadrilla(e)

        return _respuesta_cuadrilla(orden, resultado="integrante_agregado")


class CambiarPrincipalView(APIView):
    """Traslada la responsabilidad entre dos integrantes. Atomico."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = CambiarPrincipalSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        persona = _profile_o_404(request, s.validated_data["profile_id"])

        try:
            _, cambio = cambiar_principal(orden, persona, request.profile,
                                          motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return _error_de_cuadrilla(e)

        if not cambio:
            #  Ya era el principal. 200 'sin_cambios', mismo contrato que
            #  M03-B1 fijo para la secuenciacion: un no-op no es un conflicto.
            return _respuesta_cuadrilla(
                orden, resultado="sin_cambios",
                aviso="Esa persona ya era la principal. No se modifico nada y "
                      "no se registro ningun evento.")
        return _respuesta_cuadrilla(orden, resultado="principal_cambiado")


class RetirarIntegranteView(APIView):
    """
    Saca a alguien. Si es la persona principal y quedan otros integrantes, el
    sucesor viaja en esta misma llamada -- nunca en dos pasos.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = RetirarIntegranteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        persona = _profile_o_404(request, s.validated_data["profile_id"])

        sucesor = None
        sucesor_id = s.validated_data.get("nuevo_principal_id")
        if sucesor_id:
            sucesor = _profile_o_404(request, sucesor_id, que="persona sucesora")

        try:
            r = retirar_integrante(orden, persona, request.profile,
                                   nuevo_principal=sucesor,
                                   motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return _error_de_cuadrilla(e)

        return _respuesta_cuadrilla(
            orden,
            resultado=("principal_retirado" if r["cambio_principal"]
                       else "integrante_retirado"))


class DesasignarTrabajoView(APIView):
    """Deja la orden sin nadie. 0 integrantes es un estado valido."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        negado = _exigir_gestion(request)
        if negado:
            return negado

        orden = _orden_o_404(request, pk)
        s = DesasignarSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            cuantos = desasignar(orden, request.profile,
                                 motivo=s.validated_data["motivo"])
        except ErrorDespacho as e:
            return _error_de_cuadrilla(e)

        if cuantos == 0:
            return _respuesta_cuadrilla(
                orden, resultado="sin_cambios",
                aviso="La orden ya estaba sin asignar.")
        return _respuesta_cuadrilla(orden, resultado="desasignada",
                                    integrantes_retirados=cuantos)
