# -*- coding: utf-8 -*-
"""Avisarle al tecnico algo que pasa mientras el no esta mirando la app.

POR QUE ESTO EXISTE
-------------------
Medido el 04/10/2026: la aplicacion de campo **no tiene forma de decirle nada al
tecnico**. No hay push ni en la app ni en el backend, y la cola de sincronizacion
solo corre cuando alguien toca la pantalla. Es cien por ciento *pull*: se entera
de las cosas cuando abre la orden.

Consecuencia real: cuando el supervisor devuelve un trabajo, se lo avisan por
chat, a mano. Eso no es una maña -- es el unico canal que alcanza al tecnico. Y
dice menos que lo que la app ya sabe: que evidencia hay que volver a tomar esta
en la ficha.

El costo es de los caros. Si el tecnico sigue en la casa, volver a sacar una foto
no cuesta nada; si ya se fue, es un viaje.

LAS TRES REGLAS QUE MANDAN SOBRE ESTE ARCHIVO
---------------------------------------------
1. **Nada de datos del cliente en un aviso.** Un mensaje sale del sistema y queda
   en una conversacion que nadie audita. Lleva el numero de la OT, que hay que
   rehacer y un enlace: ni nombre, ni direccion, ni telefono. Quien abre el
   enlace se autentica y ahi si ve la ficha.

2. **Ningun proveedor nombrado en el esquema.** La primera version de este
   archivo tenia un campo `chat_webhook` y mandaba el formato de Google Chat.
   Eso es escribir el nombre de un proveedor en la estructura, que es justo lo
   que la regla multi-tenant prohibe: la empresa siguiente usa Teams, o Slack, o
   quiere un correo.

   LO QUE ESTA REGLA NO PUEDE GARANTIZAR, Y HAY QUE DECIRLO: la `observacion`
   del supervisor es TEXTO LIBRE. El sistema no pone datos del cliente ahi, pero
   una persona puede escribirlos. No se filtra ni se redacta --un aviso recortado
   a mitad de frase es peor que ninguno-- y vale lo mismo para el chat, para el
   correo, para la notificacion de la plataforma y para el push: son el mismo
   texto por cuatro caminos. Si alguna vez hace falta cerrarlo, se cierra en UN
   lugar: aca.

3. **Lo configura la empresa, no un programador.** La regla del proyecto dice
   «configuracion editable desde la interfaz y persistida por tenant: nunca un
   valor fijo en codigo, NI EN UN ARCHIVO QUE SOLO UN DESARROLLADOR SABE
   EDITAR». Una fila que solo se carga por consola es la misma falla con otra
   cara. Por eso hay pantalla, y por eso hay boton de probar.
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org, Profile


class ConfiguracionDeAvisos(BaseModel):
    """Lo que vale para TODOS los canales de esta empresa.

    Una sola fila por empresa, y por eso esta separada de los canales: el dominio
    de los enlaces no es de un canal, es de la empresa. Repetirlo en cada canal
    haria que un dia el enlace del chat y el del correo apunten a lugares
    distintos.
    """

    org = models.OneToOneField(
        Org, on_delete=models.CASCADE, related_name="configuracion_de_avisos"
    )

    #: De donde cuelgan los enlaces. Tiene que ser un dominio de la empresa para
    #: que el App Link de Android lo pueda verificar contra su
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

    # EL NUMERO AL QUE LLAMA EL TECNICO CUANDO ALGO NO CUADRA.
    #
    # Lo pidio el tecnico al recorrer la app: ese numero hoy lo tiene en su
    # AGENDA PERSONAL. Un tecnico nuevo no lo tiene, y el dia que cambia no se
    # entera nadie.
    #
    # Vive en la configuracion de la EMPRESA y no en el codigo, por la regla de
    # CLAUDE.md §3.3: la empresa siguiente tiene otro NOC, y cambiarlo no puede
    # exigir una version nueva de la app. Se edita desde la misma pantalla que
    # los canales de avisos.
    #
    # Vacio por omision: sin numero la aplicacion no dibuja el boton, en vez de
    # ofrecer una llamada que no va a ningun lado.
    telefono_soporte = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=(
            "A quién llama el técnico desde la app cuando algo no cuadra: "
            "el NOC, la mesa de ayuda, el supervisor."
        ),
    )

    class Meta:
        db_table = "campo_configuracion_de_avisos"

    def __str__(self) -> str:
        return f"Avisos de {self.org_id}"

    def enlace_a(self, orden_id) -> str:
        """El enlace a una orden, o vacio si la empresa no configuro dominio.

        Vacio no es un error: el aviso sale igual, sin enlace. Un aviso sin
        enlace sigue sirviendo -- dice que paso algo y en que OT.
        """
        if not self.url_base_app:
            return ""
        return f"{self.url_base_app.rstrip('/')}/ot/{orden_id}"


class CanalDeAvisos(BaseModel):
    """Un lugar donde esta empresa quiere recibir los avisos.

    VARIAS FILAS, NO UNA
    --------------------
    Una empresa puede querer dos: el chat de la cuadrilla y una copia al correo
    del coordinador. Con una sola fila habria que elegir.

    LOS PROVEEDORES NO SON TODOS DISTINTOS
    --------------------------------------
    Google Chat, Slack, Discord, Mattermost y Teams --por Workflows-- son el
    mismo gesto: un POST con un JSON de una clave. Lo unico que cambia es COMO SE
    LLAMA esa clave, y eso cabe en una tabla. Agregar un proveedor nuevo es una
    linea, no una clase.

    El correo es el minimo comun denominador: funciona en toda empresa sin que
    nadie configure nada del otro lado.

    POR QUE WHATSAPP NO ESTA ACA
    ----------------------------
    No es un webhook sino una API con credencial y plantillas aprobadas. Pero el
    motivo de fondo es otro: **Dexter ya habla WhatsApp**, con su entrega
    verificada, su idempotencia por `wamid` y su guardia de salida. Una segunda
    integracion seria un segundo lugar del sistema escribiendole a la gente, con
    dos reglas de entrega que se desincronizan.

    Y hay una diferencia que no es tecnica: un espacio de chat es de la empresa;
    WhatsApp es el numero personal de alguien.
    """

    GOOGLE_CHAT = "google_chat"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    CORREO = "correo"
    TIPOS = (
        (GOOGLE_CHAT, "Google Chat"),
        (SLACK, "Slack"),
        (TEAMS, "Microsoft Teams"),
        (DISCORD, "Discord"),
        (WEBHOOK, "Webhook genérico"),
        (CORREO, "Correo"),
    )

    #: Como se llama, en el cuerpo del POST, el texto del mensaje. Es TODA la
    #: diferencia entre los proveedores de webhook: una tabla, no una clase por
    #: proveedor.
    CLAVE_DEL_TEXTO = {
        GOOGLE_CHAT: "text",
        SLACK: "text",
        TEAMS: "text",
        DISCORD: "content",
        WEBHOOK: "text",
    }

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="canales_de_avisos"
    )

    tipo = models.CharField(max_length=24, choices=TIPOS, default=GOOGLE_CHAT)

    #: Como lo llama la empresa: «Cuadrilla norte», «Coordinacion». Sirve para
    #: que quien mira la pantalla sepa cual apagar.
    nombre = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Cómo lo llama la empresa. Solo para reconocerlo en la lista.",
    )

    #: La URL del webhook, o la direccion de correo. Un campo y no dos: es «a
    #: donde va esto», y que forma tiene lo dice el `tipo`.
    #:
    #: EN UN WEBHOOK, ESTO ES UNA CREDENCIAL: cualquiera con esa URL publica en
    #: el espacio. No vuelve al navegador -- la pantalla muestra `pista`.
    destino = models.CharField(
        max_length=500,
        help_text="URL del webhook, o dirección de correo según el tipo.",
    )

    activo = models.BooleanField(
        default=True,
        help_text=(
            "Apagar un canal sin perder la configuración. Se apaga acá y no "
            "borrándolo, para que volver a encenderlo no obligue a pedirle la "
            "URL otra vez a alguien."
        ),
    )

    #: Cuando se probo por ultima vez y como fue. Pegar una URL y no saber si
    #: sirve es como se pudren estas configuraciones.
    probado_en = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "campo_canal_de_avisos"
        ordering = ["tipo", "nombre"]
        constraints = [
            # El mismo destino dos veces en la misma empresa manda el aviso
            # duplicado, que es como se logra que la gente deje de leerlos.
            models.UniqueConstraint(
                fields=["org", "destino"], name="unique_destino_por_org"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} de {self.org_id}"

    @property
    def pista(self) -> str:
        """Lo justo para reconocerlo sin exponerlo.

        Un webhook es una credencial. La pantalla necesita que alguien distinga
        «este es el del grupo norte» sin que el valor entero pase por el
        navegador cada vez que se abre la configuracion.
        """
        if self.tipo == self.CORREO:
            return self.destino
        return f"…{self.destino[-8:]}" if len(self.destino) > 8 else "…"


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

    #: La ultima vez que el telefono dijo «sigo siendo yo». Sirve para limpiar:
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

    POR QUE HACE FALTA UN LEDGER Y NO ALCANZA CON «FIJARSE ANTES»
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
    #: todos queda con la lista vacia, y eso es informacion.
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
