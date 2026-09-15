# -*- coding: utf-8 -*-
"""Vistas API REST del módulo campo."""

from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.models import EvidenciaTrabajo, EventoTrabajo, OrdenTrabajo
from campo.permissions import IsCampoAuthenticated, PuedeAccederOrden, ROLES_GESTION
from campo.serializers import (
    AccionOperativaSerializer,
    EvidenciaTrabajoSerializer,
    GuardarDatosSerializer,
    OrdenTrabajoDetailSerializer,
    OrdenTrabajoListSerializer,
    RegistroEvidenciaSerializer,
)
from campo.services.idempotencia import manejar_idempotencia
from campo.services.storage import CampoStorage
from campo.services.transiciones import TransicionInvalidaError, completar_campo, ejecutar_accion_operativa
from campo.services.validador import validar_campos_tecnicos, verificar_checklist_completo


def _obtener_orden_o_404(request, pk) -> OrdenTrabajo:
    """Busca la orden garantizando aislamiento estricto (404, nunca 403) ante recursos de otro tenant."""
    org = getattr(request, "org", None)
    if not org:
        raise Http404

    orden = (
        OrdenTrabajo.objects.select_related("tipo_trabajo_version__work_type", "org")
        .prefetch_related("asignaciones__profile__user", "evidencias")
        .filter(pk=pk, org=org)
        .first()
    )
    if not orden:
        raise Http404

    # Permisos intra-tenant
    profile = getattr(request, "profile", None)
    if profile:
        rol = (profile.role or "").upper()
        if rol not in ROLES_GESTION and not request.user.is_superuser:
            esta_asignado = orden.asignaciones.filter(profile=profile).exists()
            if not esta_asignado:
                raise Http404

    return orden


class BootstrapView(APIView):
    """Configuración inicial, usuario, tenant, capacidades y reloj servidor."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        user = request.user
        profile = request.profile
        org = request.org

        return Response({
            "usuario": {
                "id": str(profile.id),
                "nombre": user.name or user.email,
                "email": user.email,
                "rol": profile.role or "tecnico",
            },
            "organizacion": {
                "id": str(org.id),
                "nombre": org.name,
            },
            "capacidades": {
                "trabajos": True,
                "offline": True,
                "validacion_visual": False,
            },
            "server_time": timezone.now().isoformat(),
        })


class TrabajosListView(APIView):
    """Listado de órdenes de trabajo disponibles para el técnico o supervisor."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.org
        profile = request.profile
        qs = (
            OrdenTrabajo.objects.select_related("tipo_trabajo_version__work_type", "org")
            .prefetch_related("asignaciones__profile__user")
            .filter(org=org)
        )

        # Si no es supervisor/admin, fuerza a filtrar solo los asignados
        rol = (profile.role or "").upper()
        solo_mios = request.query_params.get("solo_mios", "").lower() in ("true", "1")
        if rol not in ROLES_GESTION or solo_mios:
            qs = qs.filter(asignaciones__profile=profile)

        # Filtro de estado
        estado = request.query_params.get("estado")
        if estado:
            estados = [e.strip() for e in estado.split(",") if e.strip()]
            qs = qs.filter(estado_operativo__in=estados)

        serializer = OrdenTrabajoListSerializer(qs.distinct()[:100], many=True)
        return Response({"results": serializer.data, "next_cursor": None})


class TrabajoDetailView(APIView):
    """Detalle completo descargable de una orden para ejecución offline."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        serializer = OrdenTrabajoDetailSerializer(orden)
        return Response(serializer.data)


class AccionesTrabajoView(APIView):
    """Transición de estado operativo con soporte de Idempotency-Key."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        serializer = AccionOperativaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        accion = serializer.validated_data["accion"]
        metadatos = serializer.validated_data.get("metadatos", {})

        try:
            orden = ejecutar_accion_operativa(
                orden=orden,
                accion=accion,
                profile=request.profile,
                metadatos=metadatos,
            )
        except TransicionInvalidaError as e:
            return Response(
                {"error": "TRANSICION_INVALIDA", "detalle": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "mutation_id": serializer.validated_data.get("client_mutation_id") or "",
            "aplicada": True,
            "estado_operativo": orden.estado_operativo,
            "revision": orden.revision,
            "server_time": timezone.now().isoformat(),
        })


class GuardarDatosTrabajoView(APIView):
    """Guarda valores técnicos de la orden verificando revisión y reglas deterministas."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def patch(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        serializer = GuardarDatosSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        revision_base = serializer.validated_data["revision_base"]
        nuevos_valores = serializer.validated_data["valores"]

        with transaction.atomic():
            orden_fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)

            # Control de concurrencia optimista para evitar pisar cambios offline
            if revision_base < orden_fresca.revision:
                # Comprobar si hay colisión en los mismos campos modificados
                datos_actuales = orden_fresca.datos or {}
                claves_conflicto = [k for k in nuevos_valores if k in datos_actuales and datos_actuales[k] != nuevos_valores[k]]
                if claves_conflicto:
                    return Response(
                        {
                            "error": "STALE_WORK_ORDER",
                            "detalle": f"Conflicto de concurrencia en campos: {claves_conflicto}. La orden fue modificada en el servidor.",
                            "revision_actual": orden_fresca.revision,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            # Validar campos contra la plantilla inmutable
            esquema = orden_fresca.tipo_trabajo_version.esquema
            valores_limpios, errores = validar_campos_tecnicos(esquema, nuevos_valores)
            if errores:
                return Response(
                    {"guardado": False, "errores": errores},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Aplicar delta
            datos_actualizados = dict(orden_fresca.datos or {})
            datos_actualizados.update(valores_limpios)
            orden_fresca.datos = datos_actualizados
            orden_fresca.revision += 1
            orden_fresca.save(update_fields=["datos", "revision", "updated_at"])

            EventoTrabajo.objects.create(
                org=orden_fresca.org,
                orden=orden_fresca,
                tipo="datos_actualizados",
                profile=request.profile,
                datos={"campos_modificados": list(valores_limpios.keys()), "revision": orden_fresca.revision},
            )

        return Response({
            "guardado": True,
            "revision": orden_fresca.revision,
            "validaciones": {k: {"estado": "ok"} for k in valores_limpios},
            "server_time": timezone.now().isoformat(),
        })


class EvidenciasTrabajoView(APIView):
    """Registra la intención de subida de evidencia y emite URL temporal segura."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        serializer = RegistroEvidenciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        requisito_id = serializer.validated_data["requisito_id"]
        nombre = serializer.validated_data["nombre"]
        mime_type = serializer.validated_data["mime_type"]
        tamano_bytes = serializer.validated_data["bytes"]
        sha256 = serializer.validated_data["sha256"]
        capturada_en = serializer.validated_data.get("capturada_en_cliente")
        metadatos = serializer.validated_data.get("metadatos_captura", {})

        # Validación dura: requisito_id DEBE existir en la versión inmutable de esta orden
        esquema = orden.tipo_trabajo_version.esquema
        requisitos_validos = {e["id"] for e in esquema.get("evidencias", [])}
        if requisito_id not in requisitos_validos:
            return Response(
                {
                    "error": "REQUISITO_INVALIDO",
                    "detalle": f"El requisito '{requisito_id}' no pertenece a la versión de esta orden. Válidos: {list(requisitos_validos)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------------------------------
        # Reintento seguro. Antes esto era un update_or_create con
        # 'estado_archivo': SUBIENDO y una storage_key nueva en los defaults,
        # o sea que PISABA el estado sin mirarlo. Un reintento tardio del
        # movil -- el mismo requisito y el mismo sha, que es exactamente lo
        # que manda quien reintenta -- encontraba una evidencia RECIBIDA o
        # VERIFICADA y la devolvia a SUBIENDO, apuntando a una key vacia. La
        # evidencia ya subida quedaba huerfana en el storage y el checklist
        # de la orden retrocedia solo.
        #
        # 'manejar_idempotencia' no lo cubre: solo actua si el cliente manda
        # la cabecera Idempotency-Key, y ante un corte de red un movil puede
        # reintentar sin ella o con una clave nueva (es otra intencion para
        # el, aunque sea la misma para el servidor). La garantia no puede
        # depender de que el cliente colabore.
        #
        # select_for_update: dos subidas en paralelo de la misma foto se
        # serializan aca en vez de competir por el UniqueConstraint.
        # ---------------------------------------------------------------
        with transaction.atomic():
            evidencia = (
                EvidenciaTrabajo.objects.select_for_update()
                .filter(orden_trabajo=orden, requisito_id=requisito_id, sha256=sha256)
                .first()
            )

            # Estados terminales: la evidencia ya esta en el servidor. Se
            # devuelve la MISMA, sin tocar su estado ni su storage_key, y SIN
            # emitir URL de subida: entregarla seria dar la forma de
            # reemplazar una evidencia ya aceptada -- o auditada, si esta
            # verificada -- y el sha256 identifica la fila, no garantiza que
            # lo que se suba despues coincida.
            if evidencia and evidencia.estado_archivo in (
                EvidenciaTrabajo.RECIBIDO,
                EvidenciaTrabajo.VERIFICADO,
            ):
                return Response({
                    "evidencia_id": str(evidencia.id),
                    "estado_archivo": evidencia.estado_archivo,
                    "storage_key": evidencia.storage_key,
                    "upload": None,
                    "mensaje": "La evidencia ya fue recibida; no hay nada que subir.",
                })

            if evidencia:
                # PENDIENTE, SUBIENDO o FALLIDO: es un reintento legitimo y
                # aca es donde se renueva la URL vencida. Se conserva la
                # storage_key -- si se generara otra, lo ya subido quedaria
                # sin dueno y el confirmar posterior no lo encontraria.
                if not evidencia.storage_key:
                    evidencia.storage_key = CampoStorage.generar_storage_key(
                        org_id=str(orden.org.id),
                        orden_id=str(orden.id),
                        requisito_id=requisito_id,
                        nombre_original=nombre,
                    )
                evidencia.nombre_original = nombre
                evidencia.mime_type = mime_type
                evidencia.bytes = tamano_bytes
                evidencia.estado_archivo = EvidenciaTrabajo.SUBIENDO
                evidencia.capturada_en_cliente = capturada_en
                evidencia.metadatos_captura = metadatos
                evidencia.save(update_fields=[
                    "storage_key", "nombre_original", "mime_type", "bytes",
                    "estado_archivo", "capturada_en_cliente",
                    "metadatos_captura", "updated_at",
                ])
            else:
                key_nueva = CampoStorage.generar_storage_key(
                    org_id=str(orden.org.id),
                    orden_id=str(orden.id),
                    requisito_id=requisito_id,
                    nombre_original=nombre,
                )
                try:
                    # atomic() ANIDADO, no decorativo: abre un SAVEPOINT. En
                    # PostgreSQL un INSERT que viola una constraint aborta la
                    # transaccion entera, y toda consulta posterior falla con
                    # InFailedSqlTransaction -- incluida la relectura de aca
                    # abajo. Sin este savepoint, el 'except' atrapaba el
                    # IntegrityError y moria en la linea siguiente.
                    #
                    # No lo detecta la suite: en SQLite la transaccion no queda
                    # abortada y todo pasa en verde. Es un fallo que solo
                    # aparece en produccion, y solo cuando dos subidas de la
                    # misma foto caen a la vez. Ver la guarda marcada
                    # postgres_only en tests/.
                    with transaction.atomic():
                        evidencia = EvidenciaTrabajo.objects.create(
                            org=orden.org,
                            orden_trabajo=orden,
                            requisito_id=requisito_id,
                            # La pone el SERVIDOR desde la orden. Si viniera del
                            # cliente, un movil podria declarar la vuelta que
                            # quisiera y dar por corregido lo que no corrigio.
                            vuelta=orden.vuelta,
                            sha256=sha256,
                            storage_key=key_nueva,
                            nombre_original=nombre,
                            mime_type=mime_type,
                            bytes=tamano_bytes,
                            estado_archivo=EvidenciaTrabajo.SUBIENDO,
                            capturada_en_cliente=capturada_en,
                            metadatos_captura=metadatos,
                        )
                except IntegrityError:
                    # La otra peticion gano la carrera: la fila ya existe. Se
                    # relee y se devuelve la MISMA -- el UniqueConstraint hizo
                    # su trabajo, no hay nada roto que reportar.
                    evidencia = EvidenciaTrabajo.objects.get(
                        orden_trabajo=orden, requisito_id=requisito_id, sha256=sha256
                    )

        # El descriptor se arma recien aca, con el id ya resuelto: la URL de
        # subida se indexa por EVIDENCIA, no por la storage_key, asi el cliente
        # nunca propone una ruta. Ver CampoStorage.descriptor_subida.
        return Response({
            "evidencia_id": str(evidencia.id),
            "estado_archivo": evidencia.estado_archivo,
            "storage_key": evidencia.storage_key,
            "upload": CampoStorage.descriptor_subida(evidencia.id),
        })


class ConfirmarEvidenciaView(APIView):
    """Confirma que la evidencia fue subida con éxito al storage."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        org = getattr(request, "org", None)
        if not org:
            raise Http404

        evidencia = EvidenciaTrabajo.objects.filter(pk=pk, org=org).select_related("orden_trabajo").first()
        if not evidencia:
            raise Http404

        # Si la evidencia ya fue confirmada previamente, retorno idempotente 200 sin duplicar eventos
        if evidencia.estado_archivo in (EvidenciaTrabajo.RECIBIDO, EvidenciaTrabajo.VERIFICADO):
            return Response({
                "estado": "recibida",
                "evidencia_id": str(evidencia.id),
                "mensaje": "Evidencia previamente confirmada",
            })

        # Verificar que el archivo realmente exista en el storage antes de confirmar
        if not CampoStorage.verify_upload(evidencia.storage_key):
            return Response(
                {
                    "error": "ARCHIVO_NO_ENCONTRADO",
                    "detalle": "El archivo de evidencia no se encuentra presente en el almacenamiento.",
                    "storage_key": evidencia.storage_key,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        evidencia.estado_archivo = EvidenciaTrabajo.RECIBIDO
        evidencia.save(update_fields=["estado_archivo", "updated_at"])

        EventoTrabajo.objects.create(
            org=org,
            orden=evidencia.orden_trabajo,
            tipo="evidencia_confirmada",
            profile=request.profile,
            datos={"evidencia_id": str(evidencia.id), "requisito_id": evidencia.requisito_id},
        )

        return Response({"estado": "recibida", "evidencia_id": str(evidencia.id)})


class SubirEvidenciaDirectoView(APIView):
    """Recibe el binario de UNA evidencia. Solo backend local de desarrollo.

    Cierra el circuito que quedaba cortado: 'descriptor_subida' prometia un PUT
    contra esta ruta y la ruta no existia, asi que la app registraba la
    evidencia, recibia una URL y no tenia donde subir el archivo.

    NO es un endpoint generico de escritura. La storage_key NO viaja: se
    resuelve leyendo la evidencia, que ya esta acotada al tenant de quien pide.
    Por eso no hay ruta que sanear -- no hay ruta que el cliente pueda
    proponer, y el path traversal deja de ser un problema a resolver para pasar
    a ser imposible de plantear.

    En produccion con S3/R2 esta vista no participa: 'descriptor_subida' emite
    la URL prefirmada del proveedor y el cliente sube alli. De ahi que solo
    exista en entorno de desarrollo -- con ENV_TYPE de produccion devuelve 404,
    no 403: quien no deberia usarla tampoco tiene por que saber que existe.
    """

    permission_classes = [IsCampoAuthenticated]

    def put(self, request, pk):
        if not getattr(settings, "IS_DEV_ENV", False):
            raise Http404

        org = getattr(request, "org", None)
        if not org:
            raise Http404

        # El 404 tapa las dos cosas a la vez, y es deliberado: una evidencia
        # que no existe y una de otra empresa tienen que ser indistinguibles
        # desde afuera.
        evidencia = EvidenciaTrabajo.objects.filter(pk=pk, org=org).first()
        if not evidencia:
            raise Http404

        # Una evidencia que ya esta en el servidor no se reemplaza. Es el mismo
        # criterio que el registro: el sha256 identifica la fila, no garantiza
        # que lo que se suba despues coincida, y una VERIFICADA ya fue
        # auditada.
        if evidencia.estado_archivo in (EvidenciaTrabajo.RECIBIDO,
                                        EvidenciaTrabajo.VERIFICADO):
            return Response(
                {
                    "error": "EVIDENCIA_NO_MODIFICABLE",
                    "detalle": "La evidencia ya fue recibida; su archivo no se reemplaza.",
                    "estado_archivo": evidencia.estado_archivo,
                },
                status=status.HTTP_409_CONFLICT,
            )

        contenido = request.body or b""
        if not contenido:
            return Response(
                {"error": "CUERPO_VACIO", "detalle": "El PUT no trae bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(contenido) > CampoStorage.MAX_BYTES:
            return Response(
                {
                    "error": "ARCHIVO_DEMASIADO_GRANDE",
                    "detalle": f"Maximo {CampoStorage.MAX_BYTES} bytes.",
                    "bytes": len(contenido),
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Se mira el MIME que la evidencia DECLARO al registrarse, no la
        # cabecera del PUT: la cabecera la elige quien sube, la declaracion ya
        # quedo guardada y es contra eso que se contrasto el resto.
        if evidencia.mime_type not in CampoStorage.MIME_PERMITIDOS:
            return Response(
                {
                    "error": "MIME_NO_PERMITIDO",
                    "detalle": f"'{evidencia.mime_type}' no esta permitido.",
                    "permitidos": list(CampoStorage.MIME_PERMITIDOS),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not evidencia.storage_key or not CampoStorage.guardar(
                evidencia.storage_key, contenido):
            return Response(
                {
                    "error": "STORAGE_KEY_INVALIDA",
                    "detalle": "La evidencia no tiene una ubicacion valida donde guardar.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Reintentar el PUT sobrescribe el MISMO archivo y no toca la fila: no
        # hay forma de que un reintento cree otra EvidenciaTrabajo, porque esta
        # vista no crea ninguna.
        return Response({
            "evidencia_id": str(evidencia.id),
            "estado_archivo": evidencia.estado_archivo,
            "storage_key": evidencia.storage_key,
            "bytes": len(contenido),
        })


class ObtenerUrlEvidenciaView(APIView):
    """Genera URL segura de descarga o visualización de una evidencia."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        org = getattr(request, "org", None)
        if not org:
            raise Http404

        evidencia = EvidenciaTrabajo.objects.filter(pk=pk, org=org).first()
        if not evidencia:
            raise Http404

        url_descarga = CampoStorage.create_download_url(evidencia.storage_key)
        return Response({
            "evidencia_id": str(evidencia.id),
            "storage_key": evidencia.storage_key,
            "download_url": url_descarga,
            "estado_archivo": evidencia.estado_archivo,
        })


class CompletarTrabajoView(APIView):
    """Única puerta de cierre de campo. Valida checklist y transiciona a completada_campo."""

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)

        # 1. Comprobar checklist determinista duro
        errores = verificar_checklist_completo(orden)
        if errores:
            return Response(
                {
                    "ok": False,
                    "error": "CHECKLIST_INCOMPLETO",
                    "mensaje": "Faltan datos técnicos o evidencias requeridas para finalizar el trabajo.",
                    "errores": errores,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Transicionar
        try:
            orden = completar_campo(orden=orden, profile=request.profile)
        except TransicionInvalidaError as e:
            return Response(
                {"error": "TRANSICION_INVALIDA", "detalle": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "ok": True,
            "estado_operativo": orden.estado_operativo,
            "revision": orden.revision,
            "completada_campo_en": orden.completada_campo_en.isoformat(),
            "server_time": timezone.now().isoformat(),
        })
