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
        return {
            "id": tec.id,
            "nombre": tec.user.name or tec.user.email,
        }


class OrdenTrabajoDetailSerializer(serializers.ModelSerializer):
    tipo = serializers.SerializerMethodField()
    cliente = serializers.SerializerMethodField()
    schema = serializers.SerializerMethodField()
    evidencias = EvidenciaTrabajoSerializer(many=True, read_only=True)
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
        return {
            "id": tec.id,
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
    profile_id = serializers.UUIDField()
    rol = serializers.CharField(required=False, allow_blank=True, default="tecnico")
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


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
