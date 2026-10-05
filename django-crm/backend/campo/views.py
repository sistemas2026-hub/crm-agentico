# -*- coding: utf-8 -*-
"""Vistas API REST del módulo campo."""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.avisos import DispositivoDeTecnico
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
from campo.services.materiales_de_orden import materiales_de_orden
from campo.services import bloqueos
from campo.services import historial_del_servicio
from campo.services import salud_seguimiento
from campo.services import seguimiento_campo as seguimiento
from campo.services import telemetria
from campo.services.telemetria import (
    TANDAS,
    SinServicioParaPing,
    probar_conexion,
)
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


#: Cuantas ordenes se entregan por pagina si el cliente no pide otra cosa.
LIMITE_POR_DEFECTO = 100

#: Techo duro. Una cuadrilla con mil ordenes no puede pedirlas todas de una:
#: la respuesta no entra en memoria del telefono y el tiempo de espera hace
#: que la sincronizacion se reintente encima de si misma.
LIMITE_MAXIMO = 200


def _limite_pedido(request) -> int:
    """Cuantas filas pidio el cliente, acotado."""
    crudo = request.query_params.get("limite")
    if not crudo:
        return LIMITE_POR_DEFECTO
    try:
        pedido = int(crudo)
    except (TypeError, ValueError):
        return LIMITE_POR_DEFECTO
    return max(1, min(pedido, LIMITE_MAXIMO))


def _escribir_cursor(orden) -> str:
    """
    Donde quedo la pagina: fecha de creacion e identificador.

    Van los dos porque el orden es por fecha y la fecha se repite. Con solo la
    fecha, dos ordenes del mismo milisegundo se pisan entre paginas.
    """
    crudo = f"{orden.created_at.isoformat()}|{orden.id}"
    return base64.urlsafe_b64encode(crudo.encode("utf-8")).decode("ascii")


def _leer_cursor(cursor: str):
    """El corte que representa el cursor, o None si viene roto."""
    try:
        crudo = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        fecha_texto, ident = crudo.split("|", 1)
        fecha = datetime.fromisoformat(fecha_texto)
        return fecha, uuid.UUID(ident)
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        return None


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

        # Orden estable: sin un desempate, dos ordenes creadas en el mismo
        # milisegundo pueden intercambiarse entre paginas y una se pierde.
        qs = qs.distinct().order_by("-created_at", "-id")

        limite = _limite_pedido(request)
        cursor = request.query_params.get("cursor")
        if cursor:
            corte = _leer_cursor(cursor)
            if corte is None:
                return Response(
                    {"detail": "El cursor no es valido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            creada_en, ident = corte
            qs = qs.filter(
                Q(created_at__lt=creada_en)
                | Q(created_at=creada_en, id__lt=ident)
            )

        # Se pide una fila de mas: es como se sabe si hay pagina siguiente sin
        # contar la tabla entera.
        filas = list(qs[: limite + 1])
        hay_mas = len(filas) > limite
        filas = filas[:limite]

        serializer = OrdenTrabajoListSerializer(filas, many=True)
        return Response(
            {
                "results": serializer.data,
                "next_cursor": _escribir_cursor(filas[-1]) if hay_mas and filas else None,
            }
        )


class TrabajoDetailView(APIView):
    """Detalle completo descargable de una orden para ejecución offline."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        serializer = OrdenTrabajoDetailSerializer(orden)
        return Response(serializer.data)


class DispositivoDeCampoView(APIView):
    """El telefono dice «este soy yo», para poder recibir una notificacion.

    POR QUE ES UN POST Y NO ALGO QUE SE DEDUCE
    ------------------------------------------
    El token lo emite el servicio de notificaciones en el telefono y cambia solo:
    al reinstalar, al limpiar datos, cada tanto por su cuenta. No hay forma de
    que el servidor lo sepa si el telefono no lo dice. Por eso la app lo manda al
    entrar y cada vez que cambia.

    ES IDEMPOTENTE, Y NO POR PROLIJIDAD
    -----------------------------------
    La app lo va a mandar muchas veces --cada arranque--. Si cada envio creara
    una fila, el mismo telefono recibiria el aviso cinco veces, que es
    exactamente lo que hace que la gente apague las notificaciones. La unicidad
    la garantiza la base: `(org, token)`.

    DELETE da de baja el telefono de ESTE perfil. Se usa al cerrar sesion: un
    telefono de cuadrilla pasa de mano en mano, y el que entra no tiene por que
    recibir los avisos del que salio.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            return Response(
                {"detail": "Falta el token del dispositivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plataforma = (request.data.get("plataforma") or "android").strip().lower()
        if plataforma not in dict(DispositivoDeTecnico.PLATAFORMAS):
            return Response(
                {"detail": f"Plataforma '{plataforma}' desconocida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dispositivo, creado = DispositivoDeTecnico.objects.update_or_create(
            org=request.org,
            token=token,
            defaults={
                # El perfil se REESCRIBE a proposito: si el telefono cambio de
                # dueño, los avisos tienen que seguir a quien lo tiene ahora.
                "profile": request.profile,
                "plataforma": plataforma,
                "activo": True,
            },
        )
        return Response(
            {"id": str(dispositivo.id), "nuevo": creado},
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK,
        )

    def delete(self, request):
        token = (request.data.get("token") or "").strip()
        qs = DispositivoDeTecnico.objects.filter(
            org=request.org, profile=request.profile
        )
        if token:
            qs = qs.filter(token=token)
        # Se desactiva, no se borra: un token que dejo de servir y CUANDO dejo de
        # servir es lo que permite contestar por que un aviso no llego.
        bajas = qs.update(activo=False)
        return Response({"dados_de_baja": bajas})


class SeguimientoDeOrdenView(APIView):
    """La bitacora de la intervencion: leerla entera, o agregarle un reporte.

    GET  devuelve la linea de tiempo --los cuatro momentos mezclados con los nueve
         eventos que ya se escribian-- mas los formularios vigentes, para que la
         app y la pantalla dibujen lo que ESTE tipo de trabajo pide sin saberlo de
         antemano.
    POST agrega un reporte: `momento` (inicio, avance, bloqueo, cierre) y
         `respuestas`.

    NO MUEVE EL ESTADO OPERATIVO, y no es un olvido: la maquina de estados vive en
    `services/transiciones.py` y NIEGA los saltos invalidos. Que `bloqueada` sea
    un estado --con sus transiciones y su estado de retorno-- es la fase siguiente.
    Ver SPEC/objetivos/seguimiento-campo-por-ticket.md, decision 1.

    El aislamiento lo da `_obtener_orden_o_404`: otra empresa recibe 404 --nunca
    403-- y un tecnico que no esta asignado tampoco la ve.

    La idempotencia sale de la cabecera `Idempotency-Key`, que es la que manda la
    cola offline del telefono. Sin ella, un reintento de red dejaria dos AVANCE
    identicos y la bitacora contaria dos hechos donde hubo uno.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        datos = seguimiento.linea_de_tiempo(orden)
        datos["formularios"] = {
            m: seguimiento.formulario_de(orden, m) for m in seguimiento.MOMENTOS
        }
        # El bloqueo vivo, si hay. La ficha lo necesita para poder decir dos cosas
        # distintas: "detenida desde tal hora, vuelve a tal estado" y "reportado,
        # pero el estado operativo NO cambió".
        abierto = bloqueos.bloqueo_abierto_de(orden)
        datos["bloqueo_abierto"] = bloqueos.serializar(abierto) if abierto else None
        datos["estado_operativo"] = orden.estado_operativo
        # La salud del seguimiento viaja con la bitacora: es la misma pregunta
        # --"¿este trabajo esta reportando?"-- y separarla en otra llamada haria
        # que la pantalla mostrara la linea de tiempo y el veredicto en dos
        # momentos distintos.
        #
        # El BACKEND decide y la pantalla dibuja. Reconstruir la regla en el
        # frontend seria repetir el defecto que encontro la fase C: la regla
        # viviria en dos lados y uno se quedaria viejo.
        datos["salud"] = salud_seguimiento.calcular(orden)
        return Response(datos)

    @manejar_idempotencia
    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        momento = str(request.data.get("momento") or "").strip().lower()
        respuestas = request.data.get("respuestas") or {}
        if not isinstance(respuestas, dict):
            return Response(
                {"error": "RESPUESTAS_INVALIDAS",
                 "detalle": "'respuestas' tiene que ser un objeto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if momento == seguimiento.BLOQUEO:
                # UN SOLO CAMINO para un bloqueo. Si esta ruta escribiera solo el
                # evento, habria dos formas de reportar lo mismo y una de ellas no
                # dejaria la fila que la bandeja del NOC necesita.
                #
                # `requiere_noc` viaja aparte de las respuestas a proposito: el
                # campo del formulario lo nombra cada empresa como quiere, y un
                # filtro que depende de ese nombre deja de funcionar con la
                # segunda. Ver campo/bloqueos.py.
                _bloqueo, evento, _detuvo = bloqueos.bloquear(
                    orden,
                    profile=getattr(request, "profile", None),
                    respuestas=respuestas,
                    requiere_noc=bool(request.data.get("requiere_noc")),
                    detener=request.data.get("detener", True) is not False,
                    capturado_en_dispositivo=request.data.get("capturado_en_dispositivo"),
                )
            else:
                evento = seguimiento.registrar(
                    orden,
                    profile=getattr(request, "profile", None),
                    momento=momento,
                    respuestas=respuestas,
                    capturado_en_dispositivo=request.data.get("capturado_en_dispositivo"),
                )
        except bloqueos.BloqueoInvalido as e:
            return Response(
                {"error": "BLOQUEO_INVALIDO", "detalle": e.mensaje, "campos": e.errores},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except seguimiento.SeguimientoInvalido as e:
            # 422 y no 400: el cuerpo esta bien formado y la ruta es la correcta;
            # lo que no se puede es aceptar ESTE contenido. Con un 400 para las dos
            # cosas, la pantalla no sabe si reintentar o pedirle algo a la persona.
            return Response(
                {"error": "SEGUIMIENTO_INVALIDO", "detalle": e.mensaje,
                 "campos": e.errores},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(
            {
                "id": str(evento.id),
                "tipo": evento.tipo,
                "etiqueta": seguimiento.ETIQUETAS.get(evento.tipo, evento.tipo),
                "recibido_en": evento.created_at.isoformat() if evento.created_at else None,
            },
            status=status.HTTP_201_CREATED,
        )


class ResolverBloqueoView(APIView):
    """Destraba un trabajo detenido.

    El estado al que vuelve NO se adivina: lo guardo la fila del bloqueo cuando se
    abrio, y la maquina de transiciones valida que ese retorno sea legal. Se puede
    pedir otro destino --el mundo cambio mientras estaba trabado-- y se valida
    igual.

    Idempotente por `Idempotency-Key`: destrabar dos veces por un reintento de red
    dejaria dos eventos y una historia que cuenta dos resoluciones donde hubo una.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        bloqueo = bloqueos.bloqueo_abierto_de(orden)
        if bloqueo is None:
            return Response(
                {"error": "SIN_BLOQUEO_ABIERTO",
                 "detalle": "Esta orden no tiene ningún bloqueo abierto."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            bloqueo, evento, volvio_a = bloqueos.resolver(
                bloqueo,
                profile=getattr(request, "profile", None),
                que_se_hizo=request.data.get("que_se_hizo", ""),
                resuelto_por_rol=request.data.get("resuelto_por_rol", ""),
                volver_a=request.data.get("volver_a") or None,
            )
        except bloqueos.BloqueoInvalido as e:
            return Response(
                {"error": "BLOQUEO_INVALIDO", "detalle": e.mensaje, "campos": e.errores},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        # El estado sale de la instancia que la transicion MOVIO --la que cuelga
        # del bloqueo--, no de la que cargo esta vista: son dos objetos distintos
        # en memoria apuntando a la misma fila, y el de aca quedo viejo. La
        # pantalla pinta el estado con esto, asi que devolverlo sin refrescar
        # mostraria "bloqueada" justo despues de destrabar.
        return Response(
            {
                "bloqueo": bloqueos.serializar(bloqueo),
                "evento_id": str(evento.id),
                "volvio_a": volvio_a,
                "estado_operativo": bloqueo.orden.estado_operativo,
            }
        )


class BloqueosAbiertosView(APIView):
    """Los bloqueos vivos de la empresa, para los filtros de la bandeja.

    `?requiere_noc=1` devuelve SOLO los que le tocan al NOC. Son dos filtros
    distintos y los dos dicen la verdad: un trabajo detenido esperando al cliente
    esta bloqueado y NO requiere NOC, y mezclarlos llenaria esa bandeja de cosas
    que nadie de esa mesa puede resolver.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = getattr(request, "org", None)
        if org is None:
            raise Http404
        solo_noc = str(request.query_params.get("requiere_noc", "")).lower() in (
            "1", "true", "si", "sí",
        )
        filas = bloqueos.abiertos_de(org, solo_noc=solo_noc)
        return Response({"bloqueos": filas, "total": len(filas)})


class SaludDelSeguimientoView(APIView):
    """La salud del seguimiento de todas las ordenes en ejecucion.

    Una llamada para toda la bandeja, en vez de una por fila: con veinte lineas
    serian veinte viajes y el calculo es el mismo.

    NO DEVUELVE UN ESTADO GUARDADO. Se calcula al preguntar, a proposito: un
    veredicto guardado diria "al dia" mientras el reloj sigue corriendo, y haria
    falta un proceso que lo refresque. Ver campo/services/salud_seguimiento.py.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = getattr(request, "org", None)
        if org is None:
            raise Http404
        return Response(salud_seguimiento.resumen_de_org(org))


class MaterialesDeOrdenView(APIView):
    """Que material toco esta orden: comprometido, consumido, devuelto y otros.

    Solo lectura, y a proposito: la ficha de una orden no es lugar para mover
    inventario. Despachar, devolver y trasladar siguen entrando por sus propias
    rutas, que son las que tienen la frontera puesta.

    El aislamiento lo da `_obtener_orden_o_404`: una orden de otra empresa
    responde 404 --nunca 403-- y un tecnico que no esta asignado tampoco la ve.
    No se repite el chequeo aca para que exista UN solo lugar donde se decide
    quien puede leer una orden.

    `?custodia=1` agrega el kit vigente del tecnico como CONTEXTO. Viene apagado
    por defecto porque no es material de esta orden, y la respuesta lo dice en el
    propio dato (`es_de_esta_orden: false`).
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        incluir = str(request.query_params.get("custodia", "")).lower() in (
            "1", "true", "si", "sí",
        )
        return Response(
            materiales_de_orden(orden, incluir_custodia=incluir)
        )


class MedirSenalView(APIView):
    """Volver a medir la señal optica del equipo, desde el terreno.

    LA QUE TRAE LA FICHA ES DE CUANDO SE ARMO LA ORDEN. Si eso fue a las 08:10 y
    el tecnico llego a las 14:00, esa lectura tiene seis horas -- y justo despues
    de limpiar un conector o cambiar una roseta, lo unico que contesta «¿quedo
    bien?» es volver a medir.

    NO PISA LA LECTURA CONGELADA. `orden.contexto` es el registro de como estaba
    el servicio ANTES de la visita, que es lo que permite decir despues si la
    visita sirvio. Esta ruta devuelve una lectura nueva con SU hora; quien la
    muestra la pone al lado de la vieja.

    TRES RESPUESTAS, igual que el ping:
      200 ok=true    se midio -- con los niveles y la hora
      200 ok=false   no se pudo medir, con el motivo
      409            la orden no tiene serial: no hay a que equipo preguntarle

    «No se pudo medir» y «se midio y esta mal» son cosas distintas, y esa
    diferencia es el punto entero: la primera se reintenta, la segunda es un dato
    sobre el equipo del cliente.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        try:
            return Response(telemetria.medir_senal(orden))
        except telemetria.SinEquipoParaMedir as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)


class HistorialDelServicioView(APIView):
    """Las ultimas visitas al MISMO servicio, para quien esta en la puerta.

    POR QUE EXISTE
    --------------
    El cliente dice «ya llame tres veces» y el tecnico no tiene con que
    contestar: la ficha le da el numero de ticket y nada mas. Es la llamada al
    NOC mas frecuente de la lista que armo el tecnico, y el dato ya estaba en la
    base -- son ordenes del mismo abonado, y nadie se las mostraba.

    SE AGRUPA POR EL IDENTIFICADOR DEL ABONADO, NUNCA POR NOMBRE
    -----------------------------------------------------------
    Agrupar por nombre o direccion devolveria visitas de otra persona, y el
    tecnico decidiria sobre eso: le diria al cliente «ya le cambiamos la ONT dos
    veces» cuando fue al vecino. Sin identificador se devuelve lista vacia y se
    dice por que, en vez de adivinar.

    EL AISLAMIENTO LO DA `_obtener_orden_o_404`, igual que el resto: una orden de
    otra empresa responde 404 y un tecnico no asignado tampoco la ve. Y las
    hermanas se filtran por `org` ademas del servicio -- dos empresas pueden usar
    el mismo identificador de abonado, porque cada una lo toma de SU WispHub.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)
        servicio = historial_del_servicio.id_de_servicio(orden)
        return Response(
            {
                # `hay_servicio: false` es distinto de `visitas: []`. El primero
                # dice «no se puede saber»; el segundo, «es la primera vez». La
                # app los dibuja distinto porque el tecnico actua distinto.
                "hay_servicio": bool(servicio),
                "visitas": historial_del_servicio.visitas_anteriores(orden),
            }
        )


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
        evento_id = serializer.validated_data.get("evento_id")

        # ---------------------------------------------------------------
        # DE QUE ES ESTA FOTO, Y CONTRA QUE SE VALIDA
        # ---------------------------------------------------------------
        # Sin `evento_id` es lo de siempre: una evidencia del CHECKLIST, y el
        # requisito tiene que estar en la version inmutable de la orden.
        #
        # Con `evento_id` es una foto de un REPORTE de la bitacora, y entonces el
        # conjunto valido NO sale del esquema vigente sino del snapshot que ese
        # reporte guardo cuando se escribio. Es la misma razon por la que el
        # reporte guarda sus campos: una version nueva del tipo de trabajo no
        # puede volver invalida la foto que el tecnico saco siguiendo lo que la
        # app le mostro ese dia, ni aceptar una que entonces nadie le pidio.
        evento = None
        if evento_id:
            evento = EventoTrabajo.objects.filter(
                id=evento_id, org=orden.org, orden=orden
            ).first()
            # Se comprueba que sea DE ESTA ORDEN: con solo el id, una foto podria
            # colgarse del reporte de otra empresa.
            if evento is None:
                return Response(
                    {
                        "error": "EVENTO_INVALIDO",
                        "detalle": "Ese reporte no pertenece a esta orden.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            declaradas = (evento.datos or {}).get("evidencias") or []
            requisitos_validos = {
                e.get("id") for e in declaradas if isinstance(e, dict)
            }
            donde = "el reporte"
        else:
            esquema = orden.tipo_trabajo_version.esquema
            requisitos_validos = {e["id"] for e in esquema.get("evidencias", [])}
            donde = "la versión de esta orden"

        if requisito_id not in requisitos_validos:
            return Response(
                {
                    "error": "REQUISITO_INVALIDO",
                    "detalle": f"El requisito '{requisito_id}' no pertenece a {donde}. Válidos: {sorted(requisitos_validos)}",
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
            # El reintento se busca EN SU AMBITO. Buscar siempre por orden
            # haria que la foto de un bloqueo encontrara la de otro reporte con
            # el mismo requisito y el mismo sha, y devolviera esa -- la segunda
            # nunca se guardaria y el segundo bloqueo quedaria sin su foto.
            ambito = (
                {"evento": evento}
                if evento is not None
                else {"orden_trabajo": orden, "evento__isnull": True}
            )
            evidencia = (
                EvidenciaTrabajo.objects.select_for_update()
                .filter(requisito_id=requisito_id, sha256=sha256, **ambito)
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
                            # La orden se guarda IGUAL cuando la foto es de un
                            # reporte: es la misma orden, y sin ella una consulta
                            # por trabajo dejaria estas fotos afuera.
                            evento=evento,
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
                        requisito_id=requisito_id, sha256=sha256, **ambito
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


class ProbarConexionView(APIView):
    """
    Un ping en vivo al equipo del cliente, pedido desde el terreno.

    ES DEL TECNICO, a diferencia del refresco de ficha: el que la pide es el
    que esta parado en la casa despues de mover un conector, y la respuesta
    solo le sirve en ese momento.

    SIN SEÑAL SE RECHAZA, NUNCA SE ENCOLA. Es el mismo criterio que
    RefrescarFichaView dejo escrito para lo suyo, y aca aprieta mas: un ping
    encolado se ejecutaria cuando el tecnico ya se fue, midiendo un momento
    que a nadie le importa y con cara de respuesta a lo que pregunto. La
    aplicacion no lo mete en la cola; si no hay conexion, lo dice.

    TRES RESPUESTAS, NO DOS
    -----------------------
      200 medido=true      se pregunto y contesto -- con el conteo crudo
      200 medido=false     no se pudo preguntar, con el motivo
      409                  la orden no tiene servicio identificado: no hay a
                           que equipo pingear

    'no se pudo medir' y 'se midio y no respondio' son cosas distintas y la
    diferencia es el punto entero de este endpoint. La primera se reintenta;
    la segunda es un dato sobre el equipo del cliente.

    Y lo que devuelve NO es un veredicto. Esta medido dos veces en este
    proyecto que el mismo equipo sano da '1 de 3', '2 de 3' y '3 de 3' en
    corridas seguidas: el conteo viaja crudo, y quien decide que significa es
    la persona que esta ahi.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        orden = _obtener_orden_o_404(request, pk)

        # Cuantos paquetes pide ESTA llamada. La app manda tandas para ir
        # mostrandolas; el minimo que WispHub acepta es 3, medido (1 y 2 dan
        # 400), asi que se acota en vez de confiar en lo que llegue.
        try:
            pedidos = int(request.data.get("paquetes") or max(TANDAS))
        except (TypeError, ValueError):
            pedidos = max(TANDAS)
        pedidos = max(3, min(pedidos, 10))

        try:
            resultado = probar_conexion(orden, paquetes=pedidos)
        except SinServicioParaPing as e:
            return Response(
                {"error": "SIN_SERVICIO", "detalle": str(e)},
                status=status.HTTP_409_CONFLICT,
            )

        if not resultado["ok"]:
            # 200 y no 5xx: la peticion al CRM se proceso bien, y "no se pudo
            # medir" es un dato sobre el intento, no un error del servidor.
            # Mandarlo como 5xx haria que la app dijera "algo salio mal" en
            # vez del motivo, que es justo la distincion que cuida el modulo.
            return Response({
                "medido": False,
                "motivo": resultado["motivo"],
                "server_time": timezone.now().isoformat(),
            })

        return Response({
            "medido": True,
            "respondieron": resultado["respondieron"],
            # Uno por uno, no un promedio: la pantalla los lista y quien mira
            # ve DONDE se cayo, no solo cuantos volvieron.
            "paquetes": resultado["paquetes"],
            "server_time": timezone.now().isoformat(),
        })
