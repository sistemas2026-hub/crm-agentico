"""
===============================================================================
 EL AVISO DE UNA CAIDA A SUS CLIENTES  --  uno por situacion (30/10/2026)
===============================================================================

PRD §8.17, Ola 2, punto 4. Cuando se cae un PON, una persona aprueba avisar a
sus clientes desde "Fallas de red" y el aviso sale por lotes. Esta fila es esa
aprobacion y su avance: QUIEN aprobo, CUANDO, a cuantos, y por donde va.

UNA POR SITUACION, y lo garantiza la base (OneToOne): aprobar dos veces no
arma dos envios. Igual, cada aviso tiene en el motor su clave (situacion,
servicio): la segunda linea de defensa no depende de esta.

SIN DATOS DEL CLIENTE. 'servicios' y 'pendientes' son numeros de servicio del
ISP -- el mismo dato que ya guarda 'Case.external_service_id' --; ni nombres ni
telefonos: esos los lee el motor en el momento de mandar y no se guardan.

SIN RLS, con el filtro por empresa explicito: el mismo patron que las tablas
de situaciones de las que cuelga.
"""
import uuid

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile
from operaciones.situaciones_modelos import SituacionOperativa


class AvisoDeCaida(BaseModel):
    """La aprobacion de avisar una caida y su avance por lotes."""

    EN_CURSO = "en_curso"
    TERMINADO = "terminado"
    #  La situacion se resolvio o se descarto antes de terminar: no se le
    #  sigue escribiendo a nadie por una falla que ya no existe.
    DETENIDO = "detenido"
    ESTADOS = ((EN_CURSO, "En curso"), (TERMINADO, "Terminado"), (DETENIDO, "Detenido"))

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="avisos_de_caida")
    situacion = models.OneToOneField(SituacionOperativa, on_delete=models.CASCADE,
                                     related_name="aviso_de_caida")
    aprobado_por = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True,
                                     related_name="avisos_de_caida_aprobados")
    aprobado_en = models.DateTimeField()

    #  El puerto, tal como la situacion lo nombra ('olt/placa/puerto').
    olt = models.CharField(max_length=8)
    board = models.CharField(max_length=8)
    port = models.CharField(max_length=8)

    #  Lo que la persona aprobo, y lo que falta mandar.
    servicios = models.JSONField(default=list)
    pendientes = models.JSONField(default=list)
    #  Cuantos por tanda: lo dice el motor (config de la empresa).
    lote = models.PositiveSmallIntegerField(default=25)

    enviados = models.PositiveIntegerField(default=0)
    #  Los que el motor no mando porque ya no estaban en la falla.
    descartados = models.PositiveIntegerField(default=0)
    #  Por que no salio el resto: {'de_baja': 3, 'sin_movil': 5, ...}.
    motivos = models.JSONField(default=dict)

    #  DOS FASES (31/10/2026): primero "se cayo"; cuando la situacion deja de
    #  estar activa, "ya volvio" a los que recibieron el primero y cuyo equipo
    #  volvio. Misma fila, misma ficha de turno, misma retoma.
    CAIDA = "caida"
    RESTABLECIDO = "restablecido"
    FASES = ((CAIDA, "Aviso de la caida"), (RESTABLECIDO, "Aviso de restablecido"))
    fase = models.CharField(max_length=12, choices=FASES, default=CAIDA)
    restablecidos = models.PositiveIntegerField(default=0)

    estado = models.CharField(max_length=12, choices=ESTADOS, default=EN_CURSO)
    vueltas = models.PositiveIntegerField(default=0)
    terminado_en = models.DateTimeField(null=True, blank=True)
    #  Por que se detuvo, con el codigo del motor ('AVISO_APAGADO', ...).
    motivo_detencion = models.CharField(max_length=48, blank=True, default="")

    #  LA FICHA DEL TURNO (auditor de frontera, 31/10/2026). Cada vuelta
    #  agendada lleva la ficha vigente; la que la cola entrega dos veces (Redis
    #  reentrega una tarea con espera larga cada hora) llega con una ficha
    #  vieja y no hace nada. Sin esto, una noche de espera despertaba diez
    #  copias leyendo las mismas fichas del ISP a la vez.
    turno = models.UUIDField(default=uuid.uuid4)
    #  Cuando toca la proxima vuelta. Si la cola la pierde (un reinicio de
    #  Redis), 'retomar' la vuelve a agendar: un envio no queda "en curso"
    #  para siempre con la aprobacion ya gastada.
    proxima_vuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "operaciones_aviso_de_caida"
        ordering = ["-aprobado_en"]
        indexes = [models.Index(fields=["org", "estado"])]
