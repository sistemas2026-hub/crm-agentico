# -*- coding: utf-8 -*-
"""Lo que sale por la API. La evidencia viaja entera: es el punto."""

from __future__ import annotations

from rest_framework import serializers

from operaciones import asistentes, indicadores
from operaciones.models import (APROBADO, REQUIERE_CORRECCION,
                                REQUIERE_REVISION, ActividadOperativa,
                                DisponibilidadTecnico, ProgramacionOrden,
                                PropuestaSupervisor)


class PropuestaListaSerializer(serializers.ModelSerializer):
    tipo_senal_display = serializers.CharField(
        source="get_tipo_senal_display", read_only=True)
    dentro_del_alcance = serializers.BooleanField(read_only=True)

    class Meta:
        model = PropuestaSupervisor
        fields = [
            "id", "tipo_senal", "tipo_senal_display", "origen_tipo", "origen_id",
            "accion_propuesta", "prioridad", "estado",
            "nivel_autonomia_requerido", "dentro_del_alcance",
            "created_at", "expira_en",
        ]


class PropuestaDetalleSerializer(serializers.ModelSerializer):
    tipo_senal_display = serializers.CharField(
        source="get_tipo_senal_display", read_only=True)
    dentro_del_alcance = serializers.BooleanField(read_only=True)
    revisado_por_email = serializers.SerializerMethodField()
    responsable_sugerido_email = serializers.SerializerMethodField()

    class Meta:
        model = PropuestaSupervisor
        fields = [
            "id", "tipo_senal", "tipo_senal_display", "origen_tipo", "origen_id",
            "accion_propuesta", "motivo", "evidencia", "prioridad", "impacto",
            "nivel_autonomia_requerido", "dentro_del_alcance", "estado",
            "conocimiento_version", "expira_en",
            "revisado_por", "revisado_por_email", "revisado_en", "resultado",
            # Paso M09-F. 'propuesta_original' viaja entero y a proposito: es
            # el termino de comparacion entre lo que la IA recomendo y lo que
            # el humano decidio, que es lo que el Shadow Mode existe para medir.
            "responsable_sugerido", "responsable_sugerido_email",
            "observaciones", "propuesta_original",
            "accion_propuesta_ref", "created_at", "updated_at",
        ]

    def get_revisado_por_email(self, obj):
        if obj.revisado_por and obj.revisado_por.user:
            return obj.revisado_por.user.email
        return None

    def get_responsable_sugerido_email(self, obj):
        if obj.responsable_sugerido and obj.responsable_sugerido.user:
            return obj.responsable_sugerido.user.email
        return None


class RevisionSerializer(serializers.Serializer):
    """Lo que manda el Jefe de Operaciones."""

    decision = serializers.ChoiceField(
        choices=PropuestaSupervisor.ESTADOS_REVISADOS)
    comentario = serializers.CharField(
        required=False, allow_blank=True, max_length=2000)
    #  LO QUE EL REVISOR EDITA  --  paso M09-F
    #  Diccionario libre a proposito: la lista blanca la hace cumplir
    #  supervisor.CAMPOS_MODIFICABLES, en un solo lugar. Declararla tambien aca
    #  seria una segunda lista que tarde o temprano diverge de la primera --
    #  el mismo motivo por el que operaciones/permissions.py IMPORTA
    #  ROLES_GESTION en vez de copiarlo.
    cambios = serializers.DictField(required=False)

    def validate(self, datos):
        # Rechazar o modificar sin decir por que deja una auditoria que no
        # explica nada seis meses despues.
        if (datos["decision"] in (PropuestaSupervisor.RECHAZADA,
                                  PropuestaSupervisor.MODIFICADA)
                and not (datos.get("comentario") or "").strip()):
            raise serializers.ValidationError({
                "comentario": "Rechazar o modificar exige decir por qué."
            })
        if (datos["decision"] == PropuestaSupervisor.MODIFICADA
                and not datos.get("cambios")):
            raise serializers.ValidationError({
                "cambios": ("Modificar sin cambiar nada no es modificar: es "
                            "aceptar. Manda 'cambios', o decide 'aceptada'.")
            })
        return datos


class CancelacionSerializer(serializers.Serializer):
    """Cancelar exige decir qué hecho del mundo dejó la propuesta sin sentido."""

    motivo = serializers.CharField(max_length=2000)

    def validate_motivo(self, valor):
        if not valor.strip():
            raise serializers.ValidationError(
                "Una cancelación sin motivo es indistinguible de una fila perdida.")
        return valor


# =============================================================================
#  DISPONIBILIDAD  --  paso A-3.3
# =============================================================================
#  La organizacion NO es un campo de entrada, y esa ausencia es el control.
#  A-3.1 midio que la fuente confiable es el JWT firmado revalidado contra
#  Profile, no el cuerpo de la peticion: "This prevents org spoofing attacks"
#  (common/middleware/get_company.py). Declarar 'org' aca lo convertiria en algo
#  que el cliente puede proponer. La vista la toma de request.org.
#
#  Mismo criterio que RevisionSerializer: lo que el cliente no debe elegir, no
#  se declara.

class DisponibilidadSerializer(serializers.ModelSerializer):
    """Lo que sale. 'profile' se expande lo justo para poder leer la franja."""

    profile_email = serializers.SerializerMethodField()
    es_ausencia = serializers.SerializerMethodField()

    class Meta:
        model = DisponibilidadTecnico
        fields = [
            "id", "profile", "profile_email", "fecha",
            "hora_inicio", "hora_fin", "disponible", "es_ausencia",
            "motivo", "zona", "created_at", "created_by",
        ]

    def get_profile_email(self, obj):
        if obj.profile and obj.profile.user:
            return obj.profile.user.email
        return None

    def get_es_ausencia(self, obj) -> bool:
        """El mismo hecho que 'disponible', dicho como lo dice la operación."""
        return not obj.disponible


class LineaJornadaSerializer(serializers.ModelSerializer):
    """
    Una linea del plan, legible  --  paso M03-E2.

    QUE SE EXPONE, Y POR QUE
    ------------------------
    Se exponen los tres campos de planificacion --'secuencia', 'zona' y
    'prioridad'-- porque el objeto de E2 es justamente hacerlos observables:
    hasta ahora se podian escribir y no leer.

    'prioridad' se incluye aunque NINGUN consumidor la aplique hoy (medido en
    M03-E1: no aparece en ningun 'order_by'). Se expone para que eso se vea,
    no para sugerir que ordena: el orden lo da 'secuencia', y el desempate no
    significa nada -- ver ORDEN_JORNADA.

    De la orden se expande lo justo para poder leer la linea sin una segunda
    consulta: numero, cliente y estado. NO se expande el cliente completo:
    telefono, direccion y GPS no hacen falta para mirar un plan.
    """

    #  Las dos FK se declaran como UUIDField sobre el '_id'  --  M03-E4.
    #  Un ModelSerializer las mapea a PrimaryKeyRelatedField, que devuelve el
    #  objeto UUID en '.data'. Al renderizar una respuesta da igual --el
    #  JSONRenderer lo convierte-- pero si alguien GUARDA ese '.data' en un
    #  JSONField revienta con "Object of type UUID is not JSON serializable".
    #  Se descubrio asi: la idempotencia de M03-E4 almacena la respuesta.
    orden = serializers.UUIDField(source="orden_id", read_only=True)
    programacion = serializers.UUIDField(source="programacion_id", read_only=True)

    numero = serializers.IntegerField(source="orden.numero", read_only=True)
    cliente = serializers.CharField(source="orden.cliente_nombre", read_only=True)
    estado_orden = serializers.CharField(
        source="orden.estado_operativo", read_only=True)
    programada_para = serializers.DateTimeField(
        source="orden.programada_para", read_only=True)
    plan_semana = serializers.DateField(
        source="programacion.semana_inicio", read_only=True)
    plan_estado = serializers.CharField(
        source="programacion.estado", read_only=True)

    class Meta:
        model = ProgramacionOrden
        fields = [
            "id", "orden", "numero", "cliente", "estado_orden",
            "programada_para",
            "programacion", "plan_semana", "plan_estado",
            "dia", "hora_inicio", "hora_fin",
            "secuencia", "zona", "prioridad", "estado",
        ]


class SecuenciaSerializer(serializers.Serializer):
    """
    Lo que entra al cambiar el orden propuesto  --  paso M03-E4.

    SOLO 'secuencia'. No se declaran 'dia', 'plan', 'zona', 'prioridad' ni
    'programada_para': cambiar el orden no es reprogramar, y lo que esta
    operacion no debe tocar, no se declara. Lo que el cliente no puede proponer
    no llega a existir -- mismo criterio que A-3.3 con 'org'.

    'min_value=0' repite el CHECK que ya tiene la base. Es la misma regla dicha
    a tiempo: la base contesta IntegrityError, que el cliente no puede leer.

    'causa' pertenece al catalogo cerrado de NovedadOperativa y se valida en el
    servicio, no aca: duplicar la lista seria dos catalogos que divergen.
    """

    secuencia = serializers.IntegerField(min_value=0, max_value=32767)
    causa = serializers.CharField(required=False, allow_blank=True, default="")
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   default="", max_length=255)
    contexto = serializers.DictField(required=False, default=dict)


class LineaSecuenciaSerializer(serializers.Serializer):
    """
    Una linea dentro de la peticion de jornada  --  paso M03-E5-B.

    'secuencia_leida' es lo que el cliente VIO; 'secuencia' es lo que quiere
    dejar. Lo primero no es adorno: sin ese dato no se puede cumplir "no
    sobrescribir silenciosamente cambios concurrentes", porque
    'ProgramacionOrden' no tiene campo de concurrencia optimista -- ni
    'revision' ni version, a diferencia de OrdenTrabajo. Lo unico disponible
    como token de version es lo que el cliente afirma haber leido.

    Es opcional para no romper un cliente que no lo mande; cuando falta, la
    comprobacion de concurrencia de esa linea simplemente no se puede hacer, y
    eso queda dicho en el informe en vez de disimularse.
    """

    linea = serializers.UUIDField()
    secuencia = serializers.IntegerField(min_value=0, max_value=32767)
    secuencia_leida = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        min_value=0, max_value=32767)


class SecuenciarJornadaSerializer(serializers.Serializer):
    """
    La jornada entera  --  paso M03-E5-B.

    G-2 aprobada: la peticion trae TODAS las lineas del dia. Representa el
    estado completo que el usuario deja para esa jornada, no un parche.

    NO declara 'org': sale de la sesion ya validada. Y no declara 'dia' por
    linea: el dia es de la jornada, no de cada fila -- si una linea estuviera
    fechada en otro dia, el servicio lo rechaza en vez de aceptarlo.
    """

    plan = serializers.UUIDField()
    dia = serializers.DateField()
    lineas = LineaSecuenciaSerializer(many=True)
    causa = serializers.CharField(required=False, allow_blank=True, default="")
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   default="", max_length=255)
    contexto = serializers.DictField(required=False, default=dict)


class DisponibilidadCrearSerializer(serializers.Serializer):
    """
    Lo que entra al registrar una franja o una ausencia.

    NO declara 'org': ver el comentario del bloque. Tampoco declara
    'created_by' -- BaseModel.save() lo escribe desde crum con el usuario de la
    peticion, asi que aceptarlo seria dejar que alguien firme como otro.
    """

    profile = serializers.UUIDField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()
    hora_fin = serializers.TimeField()
    disponible = serializers.BooleanField()
    motivo = serializers.CharField(required=False, allow_blank=True,
                                   max_length=255)
    zona = serializers.CharField(required=False, allow_blank=True,
                                 max_length=128)

    def validate(self, datos):
        #  Las dos reglas ya viven en la base como CheckConstraint
        #  ('disponibilidad_franja_valida' y 'ausencia_exige_motivo'). Se
        #  repiten aca por una sola razon: la base contesta con un IntegrityError
        #  que el cliente no puede leer, y esto contesta con un 400 que dice cual
        #  de las dos fallo. No son reglas nuevas -- son las mismas, dichas a
        #  tiempo. Si divergieran, manda la base.
        if datos["hora_fin"] <= datos["hora_inicio"]:
            raise serializers.ValidationError({
                "hora_fin": "La franja tiene que terminar después de empezar."
            })
        if not datos["disponible"] and not (datos.get("motivo") or "").strip():
            raise serializers.ValidationError({
                "motivo": ("Una ausencia sin motivo no se registra: sin él, "
                           "nadie puede saber después por qué se movió el "
                           "trabajo de ese día.")
            })
        return datos


# =============================================================================
#  M02  --  ACTIVIDADES OPERATIVAS
# =============================================================================

class ActividadOperativaSerializer(serializers.ModelSerializer):
    """
    Lo que se devuelve de una actividad. Todo en texto: el cuerpo se GUARDA tal
    cual en 'MutacionIdempotente' cuando la petición trae 'Idempotency-Key', y
    ahí un UUID crudo no es JSON (defecto real encontrado en M03-F-B).
    """

    responsable = serializers.SerializerMethodField()
    depende_de = serializers.SerializerMethodField()
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_display = serializers.CharField(
        source="get_estado_operativo_display", read_only=True)
    vencimiento = serializers.SerializerMethodField()
    esta_vencida = serializers.BooleanField(read_only=True)
    bloqueada_por_dependencia = serializers.BooleanField(read_only=True)

    class Meta:
        model = ActividadOperativa
        fields = [
            "id", "tipo", "tipo_display", "titulo", "descripcion",
            "estado_operativo", "estado_display", "estado_validacion", "vuelta",
            "responsable", "origen_tipo", "origen_id",
            "vence_en", "vencimiento", "esta_vencida",
            "depende_de", "bloqueada_por_dependencia", "motivo_bloqueo",
            "completado_en", "validado_en", "created_at", "updated_at",
        ]

    def get_responsable(self, obj) -> dict | None:
        p = obj.responsable
        if not p:
            return None
        return {"id": str(p.id),
                "nombre": (p.user.name or p.user.email) if p.user else str(p.id)}

    def get_depende_de(self, obj) -> dict | None:
        d = obj.depende_de
        if not d:
            return None
        return {"id": str(d.id), "titulo": d.titulo,
                "estado_operativo": d.estado_operativo}

    def get_vencimiento(self, obj) -> str:
        from operaciones.actividades import clasificar_vencimiento
        return clasificar_vencimiento(obj)


class CrearActividadSerializer(serializers.Serializer):
    """
    Lo que entra al crear. NO declara 'org' ni 'estado_operativo': lo que el
    cliente no debe elegir, no se declara -- misma decisión que
    ProgramarSerializer en M03-B. La organización sale de la sesión.
    """

    tipo = serializers.ChoiceField(choices=ActividadOperativa.TIPOS,
                                   required=False,
                                   default=ActividadOperativa.TAREA)
    titulo = serializers.CharField(max_length=255)
    descripcion = serializers.CharField(required=False, allow_blank=True,
                                        default="")
    responsable_id = serializers.UUIDField(required=False, allow_null=True)
    origen_tipo = serializers.CharField(required=False, allow_blank=True,
                                        default="", max_length=64)
    origen_id = serializers.CharField(required=False, allow_blank=True,
                                      default="", max_length=128)
    #  Opcional a propósito: un compromiso sin fecha es legítimo y no se le
    #  inventa una. Queda como SIN_VENCIMIENTO, que es un dato distinto.
    vence_en = serializers.DateTimeField(required=False, allow_null=True)
    depende_de_id = serializers.UUIDField(required=False, allow_null=True)
    evitar_duplicado = serializers.BooleanField(required=False, default=True)


class TransicionActividadSerializer(serializers.Serializer):
    """
    Una sola puerta para todas las transiciones, y cada una explícita por su
    nombre. Es lo contrario de un PATCH sobre 'estado_operativo': ahí cualquier
    salto sería representable y la máquina de estados no significaría nada.
    """

    ACCIONES = ("asignar", "iniciar", "esperar", "bloquear", "desbloquear",
                "escalar", "completar", "validar", "cancelar", "dependencia",
                "vencimiento")

    accion = serializers.ChoiceField(choices=[(a, a) for a in ACCIONES])
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    #  Sólo los usa la acción que corresponde; el servicio valida lo demás.
    responsable_id = serializers.UUIDField(required=False, allow_null=True)
    depende_de_id = serializers.UUIDField(required=False, allow_null=True)
    #  M05-B. Escalar los exige; la vista devuelve 400 si faltan. No hay valor
    #  por defecto: no existe politica que permita elegir destinatario.
    escalado_a_id = serializers.UUIDField(required=False, allow_null=True)
    nivel_escalamiento = serializers.ChoiceField(
        choices=ActividadOperativa.NIVELES_ESCALAMIENTO, required=False)
    vence_en = serializers.DateTimeField(required=False, allow_null=True)
    destino = serializers.ChoiceField(
        choices=[(x, x) for x in ("pendiente", "en_gestion", "en_espera")],
        required=False, default="en_gestion")
    requiere_validacion = serializers.BooleanField(required=False, default=False)
    decision = serializers.ChoiceField(
        choices=[(x, x) for x in (APROBADO, REQUIERE_CORRECCION,
                                  REQUIERE_REVISION)],
        required=False)


class AsistenteSerializer(serializers.Serializer):
    """
    Cuál de los dos asistentes corre.

    Va en el CUERPO y no en la ruta a propósito: un `<str:>` en el path habría
    necesitado una excepción en el guarda de rutas malformadas
    (common/tests/test_malformed_id_routes.py), que existe para que ningún
    parámetro de ruta llegue crudo al ORM. Aquí el valor lo valida DRF contra
    un catálogo cerrado y un dominio inventado responde 400, no 500.
    """

    dominio = serializers.ChoiceField(
        choices=[(d, d) for d in sorted(asistentes.SENALES)])


class ReporteSerializer(serializers.Serializer):
    """
    Qué reporte y con qué ventana. El nombre va como parámetro de consulta y no
    en la ruta: un `<str:>` en el path habría necesitado una excepción en el
    guarda de rutas malformadas.
    """

    reporte = serializers.ChoiceField(
        choices=[(r, r) for r in indicadores.REPORTES], required=False,
        default=indicadores.DIARIO)
    desde = serializers.DateTimeField(required=False, allow_null=True)
    hasta = serializers.DateTimeField(required=False, allow_null=True)
    dias = serializers.IntegerField(required=False, allow_null=True,
                                    min_value=0, max_value=90)
