# -*- coding: utf-8 -*-
"""Los dos umbrales del seguimiento, y la señal de que el telefono hablo.

POR QUE SON DOS UMBRALES Y NO UN NUMERO
---------------------------------------
    minutos_para_reportar        cada cuanto hay que actualizar un trabajo abierto
    minutos_contacto_reciente    desde cuando se considera que el telefono aparecio

El primero sale del PROCEDIMIENTO de la empresa: el comunicado de Rapilink dice
30 minutos. El segundo sale de COMO FUNCIONA LA APP, que es otra cosa: si
sincronizara cada dos minutos, diez alcanzarian; si solo sincroniza cuando alguien
abre una pantalla, no hay numero que sirva.

Compartir un mismo 30 para las dos preguntas seria un numero magico atado a dos
cosas que cambian por motivos distintos.

POR QUE `minutos_contacto_reciente` VIENE EN NULO, Y QUE SIGNIFICA ESO
---------------------------------------------------------------------
Medido el 30/09/2026 sobre `apps/tecnicos-mobile`: la cola offline se drena por
EVENTOS DE LA INTERFAZ --`procesarCola()` se llama al entrar a la jornada, al
abrir una orden, al apretar el sello de sincronizacion y al iniciar sesion-- y
**no hay `Timer.periodic` ni escucha de conectividad**. No hay latido.

Consecuencia: el servidor solo se entera del telefono cuando la persona USA la
aplicacion. Un tecnico que trabaja media hora con el telefono en el bolsillo no
produce ningun contacto, y eso NO significa que no tenga señal.

Entonces, mientras este en nulo, el sistema NO dice "sin sincronizacion
reciente": no lo puede probar, y afirmarlo seria acusar a alguien de algo que
nadie midio. El ultimo contacto se muestra como dato, sin veredicto.

Se enciende --poniendo los minutos-- el dia que la aplicacion tenga un latido
regular. La logica que lo usa ya esta construida y probada; lo que falta es que su
ausencia signifique algo.

Y ESTO ES CONFIGURACION POR EMPRESA, no una constante
-----------------------------------------------------
Otro ISP puede exigir 45 minutos, o 20. Un valor fijo en el codigo obligaria a un
commit para dar de alta la segunda empresa, que es justo lo que la regla del
proyecto prohibe.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile


#: Lo que dice el comunicado de operaciones. Es el DEFECTO de fabrica, no una ley:
#: cada empresa lo cambia en su fila.
MINUTOS_PARA_REPORTAR = 30


class ConfiguracionDeSeguimiento(BaseModel):
    """Cada cuanto tiene que reportar un trabajo abierto, por empresa."""

    org = models.OneToOneField(
        Org, on_delete=models.CASCADE, related_name="configuracion_seguimiento"
    )

    minutos_para_reportar = models.PositiveSmallIntegerField(
        default=MINUTOS_PARA_REPORTAR,
        help_text=(
            "Cada cuántos minutos hay que actualizar un trabajo abierto. "
            "Sale del procedimiento de la empresa."
        ),
    )

    #: NULO = no se evalua. Ver el encabezado: sin latido en la aplicacion, la
    #: ausencia de contacto no distingue "sin señal" de "app cerrada", y el
    #: sistema no afirma lo que no puede medir.
    minutos_contacto_reciente = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Desde cuándo se considera que el teléfono apareció. En nulo, el "
            "sistema NO dice «sin sincronización reciente»: no lo puede probar "
            "mientras la app no tenga un latido regular."
        ),
    )

    class Meta:
        db_table = "campo_configuracion_seguimiento"

    def __str__(self) -> str:
        return f"Seguimiento de {self.org_id}: cada {self.minutos_para_reportar} min"


class ContactoDeDispositivo(BaseModel):
    """La ultima vez que el telefono de alguien le hablo al servidor.

    QUE ES UNA EVIDENCIA DE CONTACTO
    --------------------------------
    Cualquier peticion autenticada que llega desde la aplicacion de campo. No hace
    falta que traiga un reporte: que el telefono haya podido hablar ya es el dato.

    QUE NO ES
    ---------
    Una prueba de que AHORA tiene señal. Es lo ultimo que se supo, y por eso su
    ausencia no alcanza para afirmar nada mientras la app no lata sola.

    POR QUE SE ESCRIBE CON FRENO
    ----------------------------
    Una persona abriendo pantallas produce decenas de peticiones por minuto.
    Escribir en cada una convertiria esta fila en el cuello de botella de todo el
    modulo, y para la pregunta que contesta --"¿aparecio en los ultimos N
    minutos?"-- da exactamente lo mismo.
    """

    #: Cada cuanto, como maximo, se toca la fila. Ver el docstring.
    SEGUNDOS_DE_FRENO = 60

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="contactos_de_dispositivo"
    )
    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE, related_name="contacto_de_dispositivo"
    )
    visto_en = models.DateTimeField(default=timezone.now)
    #: Para saber por donde apareció, cuando haga falta depurar.
    ultima_ruta = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "campo_contacto_dispositivo"
        indexes = [models.Index(fields=["org", "visto_en"], name="idx_contacto_org")]

    def __str__(self) -> str:
        return f"{self.profile_id} visto {self.visto_en}"

    @property
    def minutos_desde_el_ultimo_contacto(self) -> int:
        return int((timezone.now() - self.visto_en).total_seconds() // 60)
