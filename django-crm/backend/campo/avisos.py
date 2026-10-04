# -*- coding: utf-8 -*-
"""Avisarle al tecnico algo que pasa mientras el no esta mirando la app.

POR QUE ESTO EXISTE
-------------------
Medido el 04/10/2026: la aplicacion de campo **no tiene forma de decirle nada al
tecnico**. No hay push ni en la app ni en el backend, y la cola de sincronizacion
solo corre cuando alguien toca la pantalla. Es cien por ciento *pull*: se entera
de las cosas cuando abre la orden.

Consecuencia real, contada por el usuario: cuando el supervisor devuelve un
trabajo, **se lo avisan por Google Chat**. Eso no es una maña -- es el unico canal
que alcanza al tecnico. Y es peor que lo que la app ya sabe: la devolucion esta
en la ficha, completa, con que evidencia hay que volver a tomar; el mensaje de
chat dice que te devolvieron algo y nada mas.

El costo es de los caros. Si el tecnico sigue en la casa, volver a sacar una foto
no cuesta nada; si ya se fue, es un viaje. Es la metrica que la industria llama
*first-time fix rate*.

LAS DOS REGLAS QUE MANDAN SOBRE ESTE ARCHIVO
--------------------------------------------
1. **Nada de datos del cliente en un aviso.** Un mensaje de chat sale del sistema
   y queda en una conversacion que nadie audita. Lleva el numero de la OT, que
   hay que rehacer y un enlace: ni nombre, ni direccion, ni telefono. Quien abre
   el enlace se autentica y ahi si ve la ficha.

2. **El webhook es dato de la empresa, no una constante.** Cada ISP tiene su
   espacio de chat. Va en una fila que se edita, nunca en el codigo -- la regla
   multi-tenant del proyecto, que ya costo una correccion.
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class CanalDeAvisos(BaseModel):
    """Por donde se le avisa al tecnico, en esta empresa.

    Una fila por empresa. Vacia = no se avisa por ese canal, y eso es un estado
    legitimo: una empresa puede no usar chat.
    """

    org = models.OneToOneField(
        Org, on_delete=models.CASCADE, related_name="canal_de_avisos"
    )

    #: El webhook de un espacio de Google Chat. Lo crea la empresa en su espacio
    #: y lo pega aca. Vacio = no se publica nada.
    chat_webhook = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "URL del webhook del espacio de Google Chat donde se avisa a la "
            "cuadrilla. Vacío: no se publica."
        ),
    )

    #: De donde cuelgan los enlaces que se mandan. Tiene que ser un dominio de la
    #: empresa para que el App Link de Android lo pueda verificar contra su
    #: `/.well-known/assetlinks.json`; si no, el enlace abre el navegador -- que
    #: tambien sirve, y es la degradacion correcta.
    url_base_app = models.URLField(
        max_length=300,
        blank=True,
        default="",
        help_text=(
            "Dominio desde el que se arman los enlaces a una orden "
            "(https://campo.empresa.co). Sin esto el aviso va sin enlace."
        ),
    )

    activo = models.BooleanField(
        default=True,
        help_text=(
            "Apagar los avisos sin perder la configuración. Se apaga acá y no "
            "borrando el webhook, para que volver a encenderlos no obligue a "
            "pedirle la URL otra vez a alguien."
        ),
    )

    class Meta:
        db_table = "campo_canal_de_avisos"

    def __str__(self) -> str:
        return f"Avisos de {self.org_id}"

    def enlace_a(self, orden_id) -> str:
        """El enlace a una orden, o vacio si la empresa no configuro dominio.

        Vacio no es un error: el aviso sale igual, sin enlace. Un aviso sin
        enlace sigue sirviendo -- dice que pasó algo y en que OT.
        """
        if not self.url_base_app:
            return ""
        return f"{self.url_base_app.rstrip('/')}/ot/{orden_id}"


class DispositivoDeTecnico(BaseModel):
    """El telefono de alguien, para poder mandarle una notificacion.

    POR QUE EL TOKEN VIVE ACA Y NO EN EL PERFIL
    -------------------------------------------
    Una persona puede tener dos telefonos --el de la empresa y el de repuesto de
    la cuadrilla-- y el mismo telefono puede pasar de un tecnico a otro. Un campo
    en `Profile` obligaria a elegir uno y perder el otro.

    Y porque un token se **revoca**: cuando el proveedor dice que ya no sirve, la
    fila se desactiva y queda, con su fecha. Borrarla haria imposible contestar
    por que un aviso no llego el martes.
    """

    ANDROID = "android"
    IOS = "ios"
    PLATAFORMAS = ((ANDROID, "Android"), (IOS, "iOS"))

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="dispositivos_campo"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="dispositivos_campo"
    )

    token = models.CharField(
        max_length=500,
        help_text="El identificador que da el servicio de notificaciones.",
    )
    plataforma = models.CharField(
        max_length=16, choices=PLATAFORMAS, default=ANDROID
    )

    activo = models.BooleanField(default=True)

    #: La ultima vez que el telefono dijo "sigo siendo yo". Sirve para limpiar:
    #: un token que no se renueva en meses es de un telefono que ya no esta.
    visto_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campo_dispositivo_tecnico"
        constraints = [
            # El token identifica al telefono. Que el mismo token aparezca dos
            # veces en la misma empresa significa que alguien se registro dos
            # veces, y mandarle el aviso duplicado es exactamente lo que hace
            # que la gente apague las notificaciones.
            models.UniqueConstraint(
                fields=["org", "token"], name="unique_token_por_org"
            )
        ]

    def __str__(self) -> str:
        return f"{self.plataforma} de {self.profile_id}"


class AvisoEnviado(BaseModel):
    """Que avisos ya salieron. Para no mandar dos veces el mismo.

    POR QUE HACE FALTA UN LEDGER Y NO ALCANZA CON "FIJARSE ANTES"
    ------------------------------------------------------------
    Es la misma leccion que el proyecto ya tiene escrita para las mutaciones
    externas: se excluye por CLAVE PRIMARIA con `on conflict do nothing`, nunca
    con un `select` previo -- ahi vive la carrera.

    Un reintento de la devolucion, o dos supervisores apretando a la vez, no
    pueden producir dos mensajes. Un tecnico que recibe el mismo aviso dos veces
    deja de leerlos.

    La clave la arma quien avisa y describe EL HECHO, no el intento: para una
    devolucion es la orden y su vuelta, porque devolver la vuelta 2 es un hecho
    que ocurre una sola vez.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="avisos_enviados"
    )
    clave = models.CharField(
        max_length=200,
        help_text="Identifica el HECHO que se avisa, no el intento.",
    )

    #: Que canales lo recibieron de verdad. Un aviso que se intento y fallo en
    #: los dos canales queda con la lista vacia, y eso es informacion.
    canales = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "campo_aviso_enviado"
        constraints = [
            models.UniqueConstraint(
                fields=["org", "clave"], name="unique_aviso_por_clave"
            )
        ]

    def __str__(self) -> str:
        return self.clave
