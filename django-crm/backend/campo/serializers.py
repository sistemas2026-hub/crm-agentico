# -*- coding: utf-8 -*-
"""Serializadores para la API REST del módulo campo."""

from __future__ import annotations

from rest_framework import serializers

from campo.models import AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


class WorkTypeVersionEsquemaSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(source="work_type.codigo", read_only=True)
    nombre = serializers.CharField(source="work_type.nombre", read_only=True)

    class Meta:
        model = WorkTypeVersion
        fields = [
            "codigo",
            "nombre",
            "version",
            "schema_version",
            "estado",
            "esquema",
            "schema_hash",
            "publicada_en",
        ]


class EvidenciaTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenciaTrabajo
        fields = [
            "id",
            "requisito_id",
            "storage_key",
            "nombre_original",
            "mime_type",
            "bytes",
            "sha256",
            "estado_archivo",
            "capturada_en_cliente",
            "recibida_en_servidor",
            "metadatos_captura",
        ]


class AsignacionSerializer(serializers.ModelSerializer):
    """
    Un integrante de la cuadrilla. Es la SALIDA que faltaba: hasta M03-F-B
    ningun serializer devolvia las asignaciones, asi que una cuadrilla se podia
    construir y no se podia mirar.

    No hay campo de estado que exponer: la pertenencia es la existencia de la
    fila. Las fechas que existen son 'asignado_en' y las de BaseModel.
    """

    profile_id = serializers.UUIDField(source="profile.id", read_only=True)
    nombre = serializers.SerializerMethodField()
    rol_display = serializers.CharField(source="get_rol_display", read_only=True)

    class Meta:
        model = AsignacionTrabajo
        fields = ["id", "profile_id", "nombre", "rol", "rol_display",
                  "es_principal", "asignado_en"]

    def get_nombre(self, obj: AsignacionTrabajo) -> str:
        u = obj.profile.user
        return u.name or u.email


class OrdenTrabajoListSerializer(serializers.ModelSerializer):
    tipo = serializers.SerializerMethodField()
    cliente = serializers.SerializerMethodField()
    tecnico_principal = serializers.SerializerMethodField()

    class Meta:
        model = OrdenTrabajo
        fields = [
            "id",
            "numero",
            "revision",
            "tipo",
            "cliente",
            "tecnico_principal",
            "estado_operativo",
            "estado_validacion",
            "programada_para",
            "iniciada_en",
            "created_at",
        ]

    def get_tipo(self, obj: OrdenTrabajo) -> dict:
        v = obj.tipo_trabajo_version
        return {
            "codigo": v.work_type.codigo,
            "nombre": v.work_type.nombre,
            "version": v.version,
        }

    def get_cliente(self, obj: OrdenTrabajo) -> dict:
        return {
            "nombre": obj.cliente_nombre,
            "telefono": obj.cliente_telefono,
            "direccion": obj.cliente_direccion,
            "lat": obj.gps_lat,
            "lng": obj.gps_lng,
        }

    def get_tecnico_principal(self, obj: OrdenTrabajo) -> dict | None:
        tec = obj.tecnico_principal
        if not tec:
            return None
        #  'str' y no el UUID crudo. Sobre HTTP no cambia nada -- el renderer
        #  de DRF ya lo serializaba a texto -- pero el cuerpo se GUARDA tal
        #  cual en 'MutacionIdempotente', y ahi un UUID no es JSON. Hasta
        #  M03-F-B, cualquier POST a /asignar/ con cabecera 'Idempotency-Key'
        #  reventaba por esto; no se veia porque ninguna prueba la enviaba a
        #  este endpoint.
        return {
            "id": str(tec.id),
            "nombre": tec.user.name or tec.user.email,
        }


class OrdenTrabajoDetailSerializer(serializers.ModelSerializer):
    tipo = serializers.SerializerMethodField()
    cliente = serializers.SerializerMethodField()
    schema = serializers.SerializerMethodField()
    evidencias = EvidenciaTrabajoSerializer(many=True, read_only=True)
    tecnico_principal = serializers.SerializerMethodField()
    #  M03-F-B: la cuadrilla completa. 'tecnico_principal' se conserva -- es lo
    #  que consumen la bandeja y H-05, y quitarlo seria una ruptura gratuita.
    #  Aqui no se duplica: es el mismo dato visto por extenso.
    cuadrilla = AsignacionSerializer(source="asignaciones", many=True,
                                     read_only=True)

    class Meta:
        model = OrdenTrabajo
        fields = [
            "id",
            "numero",
            "revision",
            "tipo",
            "cliente",
            "tecnico_principal",
            "cuadrilla",
            "diagnostico_previo",
            "schema",
            "datos",
            "evidencias",
            "estado_operativo",
            "estado_validacion",
            "programada_para",
            "iniciada_en",
            "completada_campo_en",
            "created_at",
            "updated_at",
        ]

    def get_tipo(self, obj: OrdenTrabajo) -> dict:
        v = obj.tipo_trabajo_version
        return {
            "codigo": v.work_type.codigo,
            "nombre": v.work_type.nombre,
            "version": v.version,
            "schema_version": v.schema_version,
            "schema_hash": v.schema_hash,
        }

    def get_cliente(self, obj: OrdenTrabajo) -> dict:
        return {
            "nombre": obj.cliente_nombre,
            "telefono": obj.cliente_telefono,
            "direccion": obj.cliente_direccion,
            "lat": obj.gps_lat,
            "lng": obj.gps_lng,
        }

    def get_schema(self, obj: OrdenTrabajo) -> dict:
        return obj.tipo_trabajo_version.esquema

    def get_tecnico_principal(self, obj: OrdenTrabajo) -> dict | None:
        tec = obj.tecnico_principal
        if not tec:
            return None
        #  'str' y no el UUID crudo. Sobre HTTP no cambia nada -- el renderer
        #  de DRF ya lo serializaba a texto -- pero el cuerpo se GUARDA tal
        #  cual en 'MutacionIdempotente', y ahi un UUID no es JSON. Hasta
        #  M03-F-B, cualquier POST a /asignar/ con cabecera 'Idempotency-Key'
        #  reventaba por esto; no se veia porque ninguna prueba la enviaba a
        #  este endpoint.
        return {
            "id": str(tec.id),
            "nombre": tec.user.name or tec.user.email,
        }


class AccionOperativaSerializer(serializers.Serializer):
    accion = serializers.CharField(max_length=64)
    client_mutation_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    client_time = serializers.DateTimeField(required=False)
    metadatos = serializers.DictField(required=False, default=dict)


class GuardarDatosSerializer(serializers.Serializer):
    revision_base = serializers.IntegerField(min_value=1)
    valores = serializers.DictField()
    client_mutation_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class RegistroEvidenciaSerializer(serializers.Serializer):
    requisito_id = serializers.CharField(max_length=64)
    nombre = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=128)
    bytes = serializers.IntegerField(min_value=0)
    sha256 = serializers.CharField(max_length=64)
    capturada_en_cliente = serializers.DateTimeField(required=False, allow_null=True)
    metadatos_captura = serializers.DictField(required=False, default=dict)
    client_mutation_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


# =============================================================================
#  DESPACHO  --  lo que la oficina manda para crear, asignar y validar
# =============================================================================
#
# Ninguno acepta 'org' ni 'profile'. Los dos salen de la sesion: son
# exactamente los campos con los que se cruza un tenant si se leen del cuerpo.


class CrearOrdenSerializer(serializers.Serializer):
    """Alta de una orden, con o sin caso detras."""

    work_type_version_id = serializers.UUIDField()
    # Vacio = orden manual (preventivo, inspeccion, obra). Con valor = nace de
    # un caso del CRM y hereda su ficha tecnica congelada.
    case_id = serializers.CharField(required=False, allow_blank=True, default="")
    cliente_nombre = serializers.CharField(required=False, allow_blank=True, default="")
    cliente_telefono = serializers.CharField(required=False, allow_blank=True, default="")
    cliente_direccion = serializers.CharField(required=False, allow_blank=True, default="")
    gps_lat = serializers.FloatField(required=False, allow_null=True)
    gps_lng = serializers.FloatField(required=False, allow_null=True)
    programada_para = serializers.DateTimeField(required=False, allow_null=True)
    # A quien se le asigna de entrada. Opcional: una orden puede quedar sin
    # asignar esperando que alguien la tome, y esa es una columna util en la
    # bandeja del supervisor.
    tecnico_profile_id = serializers.UUIDField(required=False, allow_null=True)


class AsignarSerializer(serializers.Serializer):
    """
    A quien se le pone la orden. El 'rol' viaja por CATALOGO CERRADO -- F-4.

    Era un CharField, y por eso la API aceptaba y persistia cualquier cadena:
    el modelo declara 'choices', pero Django solo los valida en formularios y
    admin, nunca al guardar, y nadie llamaba a full_clean(). El catalogo se
    habia cerrado en el modelo el 15/09/2026 y la puerta de entrada habia
    quedado abierta -- medido en M03-F-A.1.

    'allow_blank' se conserva: la vista ya traduce "" a 'tecnico', y quitarlo
    romperia a un cliente que hoy manda el campo vacio.
    """

    profile_id = serializers.UUIDField()
    rol = serializers.ChoiceField(
        choices=AsignacionTrabajo.ROLES_CUADRILLA,
        required=False, allow_blank=True, default=AsignacionTrabajo.TECNICO)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class AgregarIntegranteSerializer(serializers.Serializer):
    """Sumar a alguien a la cuadrilla. NO declara 'es_principal' a proposito:
    mover el principal es otra operacion. Lo que el cliente no debe elegir, no
    se declara -- misma decision que 'ProgramarSerializer' en M03-B."""

    profile_id = serializers.UUIDField()
    rol = serializers.ChoiceField(
        choices=AsignacionTrabajo.ROLES_CUADRILLA,
        required=False, allow_blank=True, default=AsignacionTrabajo.TECNICO)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class CambiarPrincipalSerializer(serializers.Serializer):
    """Quien pasa a responder por la orden. Tiene que estar ya en la cuadrilla."""

    profile_id = serializers.UUIDField()
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class RetirarIntegranteSerializer(serializers.Serializer):
    """
    Quien sale, y -- si es la persona principal y quedan otros -- quien queda
    a cargo, EN LA MISMA OPERACION (decision A de M03-F-A.3).

    'nuevo_principal_id' es opcional en el esquema y obligatorio en la regla:
    se exige solo cuando hace falta, igual que '_validar_causa(exigida=...)'
    en M03. Un esquema que lo hiciera siempre obligatorio impediria retirar al
    ultimo integrante, que es un caso legitimo.
    """

    profile_id = serializers.UUIDField()
    nuevo_principal_id = serializers.UUIDField(required=False, allow_null=True)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class DesasignarSerializer(serializers.Serializer):
    """Dejar la orden sin nadie. 0 integrantes es un estado valido (F-2)."""

    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class ProgramarSerializer(serializers.Serializer):
    """
    Lo que entra al programar una orden  --  paso M03-B.

    NO declara 'org' ni 'organization_id'. Es la misma decision que A-3.3:
    lo que el cliente no debe elegir, no se declara. La organizacion sale de
    la sesion ya validada, asi que un 'organization_id' en el cuerpo no tiene
    donde aterrizar -- no se ignora despues, no llega a existir.

    Tampoco declara 'estado': la linea nace 'planificada' y el estado
    operativo de la orden no lo toca esta operacion.
    """

    programacion_semanal_id = serializers.UUIDField()
    programada_para = serializers.DateTimeField()
    #  M03-D3: agregar una orden a un plan YA PUBLICADO es una adicion formal
    #  y exige causa. Sobre un borrador siguen siendo opcionales -- la conducta
    #  que M03-B dejo validada no cambia.
    causa = serializers.CharField(required=False, allow_blank=True, default="")
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   default="", max_length=255)
    zona = serializers.CharField(required=False, allow_blank=True, default="")
    prioridad = serializers.IntegerField(required=False, min_value=0,
                                         max_value=32767, allow_null=True,
                                         default=None)
    secuencia = serializers.IntegerField(required=False, min_value=0,
                                         max_value=32767, allow_null=True,
                                         default=None)


class ReprogramarSerializer(serializers.Serializer):
    """
    Lo que entra al reprogramar  --  paso M03-D3.

    NO declara 'org' ni 'organization_id': la organizacion sale de la sesion ya
    validada, asi que un 'organization_id' en el cuerpo no tiene donde
    aterrizar -- no se ignora despues, no llega a existir.

    'causa' pertenece al catalogo cerrado de NovedadOperativa y se valida en el
    servicio, no aca: la lista vive en el modelo y duplicarla en un serializer
    seria dos catalogos que se desincronizan.
    """

    programacion_semanal_id = serializers.UUIDField()
    programada_para = serializers.DateTimeField()
    causa = serializers.CharField(required=False, allow_blank=True, default="")
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   default="", max_length=255)
    contexto = serializers.DictField(required=False, default=dict)


class ContingenciaSerializer(serializers.Serializer):
    """
    Lo que entra al registrar una contingencia  --  paso M03-D3.

    No lleva fecha: una contingencia NO propone una fecha nueva. Registra que
    un trabajo en curso se complico, y por que.
    """

    causa = serializers.CharField()
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   default="", max_length=255)
    contexto = serializers.DictField(required=False, default=dict)


class ValidarSerializer(serializers.Serializer):
    """Aprobar, o devolver diciendo QUE hay que rehacer."""

    decision = serializers.ChoiceField(choices=["aprobar", "requerir_correccion"])
    observacion = serializers.CharField(required=False, allow_blank=True, default="")
    requisitos_a_corregir = serializers.ListField(
        child=serializers.CharField(), required=False, default=list)

    def validate(self, attrs):
        # Una devolucion sin requisitos deja al tecnico adivinando, y ademas el
        # checklist no exigiria nada nuevo: la orden volveria a completarse sin
        # que nadie corrija nada.
        if attrs["decision"] == "requerir_correccion" and not attrs.get(
                "requisitos_a_corregir"):
            raise serializers.ValidationError({
                "requisitos_a_corregir":
                    "Hay que decir que se devuelve. Una devolucion sin "
                    "requisitos no exige nada nuevo al completar."})
        return attrs
