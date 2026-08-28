"""Solicitud de servicio: el formulario de contratacion, dentro de la plataforma.

Por que existe esta app y no vive en `leads/`
---------------------------------------------
`leads/`, `cases/` y el resto vienen de BottleCRM (Django-CRM upstream). Esto
es codigo nuestro y de nadie mas, asi que va aparte: una app propia no entra en
conflicto cuando se traiga algo de arriba, y no cruza con quien este trabajando
en `cases/` al mismo tiempo.

Que reemplaza
-------------
Habia un formulario en el sitio web (rapilinksas.co/solicitud) que al enviarse
mandaba un correo con un PDF y creaba un ticket "Instalacion Nueva" en WispHub.
Funcionaba, pero era una caja negra: nadie sabia quien lo habia abierto y no lo
habia terminado, ni de que conversacion de WhatsApp venia cada solicitud.

Trayendolo aca el link puede llevar un token atado al Lead que Dexter ya creo
durante la conversacion, y entonces se sabe exactamente quien llego, quien
completo y quien quedo a mitad. El correo y el ticket de WispHub se siguen
mandando igual: lo que funciona no se toca, se le suma el registro.

Sobre los datos que guarda
--------------------------
Esto guarda cedula, direccion, coordenadas GPS y un PDF que contiene fotos del
documento de identidad, de un recibo de servicios y del solicitante. Es la
informacion mas sensible de todo el sistema, y es una decision deliberada
(27/08/2026): hoy ese mismo PDF vive en una bandeja de Gmail, que protege
bastante menos que una tabla con RLS y acceso por rol.

Las tres imagenes NO se guardan sueltas: van dentro del PDF y nada mas. Un solo
objeto que proteger en vez de cuatro.
"""

from __future__ import annotations

import uuid

from django.db import models

from common.base import BaseModel
from common.models import Org


class SolicitudServicio(BaseModel):
    """Una solicitud de contratacion, tal como la completa el interesado.

    Los nombres de campo siguen el formulario que ya existia, no un modelo
    ideal: quien compare uno contra el otro tiene que poder hacerlo sin
    traducir. Casi todo es texto libre a proposito -- lo escribe una persona
    desde el celular, y rechazarle una solicitud por el formato de un campo
    es peor negocio que guardarlo como vino y que alguien lo mire despues.
    """

    # --- de donde vino -----------------------------------------------------
    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="solicitudes_servicio")
    # El Lead que Dexter creo durante la conversacion. Es el vinculo que hace
    # que todo esto valga la pena: sin el, una solicitud enviada no se puede
    # atar a la conversacion que la origino. Puede ser nulo -- alguien puede
    # llegar al formulario por fuera del chat.
    lead = models.ForeignKey("leads.Lead", on_delete=models.SET_NULL,
                             null=True, blank=True,
                             related_name="solicitudes_servicio")
    # SHA-256 del token firmado que viaja en la URL, nunca el token. Mismo
    # criterio que CsatSurvey: una filtracion de la base no expone links
    # validos. Ver solicitudes/tokens.py.
    token_hash = models.CharField(max_length=64, unique=True)
    expira_en = models.DateTimeField()

    # --- 1. datos personales ----------------------------------------------
    nombre = models.CharField(max_length=120, blank=True, default="")
    apellido = models.CharField(max_length=120, blank=True, default="")
    # Texto y no entero: el formulario pide "minimo 18 anos" y quien escribe
    # "35 anos" no deberia perder la solicitud por eso. La validacion de que
    # sea mayor de edad vive en el formulario, donde se le puede explicar.
    edad = models.CharField(max_length=16, blank=True, default="")
    correo = models.EmailField(blank=True, default="")
    telefono = models.CharField(max_length=64, blank=True, default="")
    tipo_documento = models.CharField(max_length=32, blank=True, default="")
    numero_documento = models.CharField(max_length=64, blank=True, default="")

    # --- 2. informacion del servicio --------------------------------------
    tipo_solicitud = models.CharField(max_length=64, blank=True, default="")
    plan_interesado = models.CharField(max_length=160, blank=True, default="")
    fecha_corte = models.CharField(max_length=32, blank=True, default="")
    como_se_entero = models.CharField(max_length=120, blank=True, default="")

    # --- 3. ubicacion ------------------------------------------------------
    direccion = models.CharField(max_length=255, blank=True, default="")
    barrio = models.CharField(max_length=160, blank=True, default="")
    # Las coordenadas son lo que decide la factibilidad tecnica -- el
    # formulario lo dice con todas las letras: sin ellas no se puede
    # confirmar si el servicio llega a esa direccion. Se guardan como vinieron
    # del navegador, sin redondear: redondear coordenadas es perder metros, y
    # aca los metros son si hay poste cerca o no.
    gps_lat = models.CharField(max_length=32, blank=True, default="")
    gps_lng = models.CharField(max_length=32, blank=True, default="")
    gps_precision_m = models.CharField(max_length=32, blank=True, default="")

    # --- 4, 5. el expediente ----------------------------------------------
    # El PDF con la plantilla, las tres fotos y la firma adentro. Es EL
    # entregable: es lo que Operaciones abre para instalar, y lo que hoy
    # llega por correo. Las imagenes sueltas no se guardan -- ver el docstring
    # del modulo.
    pdf = models.FileField(upload_to="solicitudes/%Y/%m/", null=True, blank=True)

    # --- 6. autorizaciones -------------------------------------------------
    # No alcanza con un booleano. Una autorizacion de tratamiento de datos que
    # no dice QUE texto acepto la persona ni CUANDO no prueba nada el dia que
    # alguien la reclame: el texto de la politica cambia, y "acepto" a secas
    # no dice a que. Por eso se guarda la version del texto y el momento.
    autoriza_centrales_riesgo = models.BooleanField(default=False)
    autoriza_habeas_data = models.BooleanField(default=False)
    texto_autorizaciones = models.TextField(blank=True, default="")
    autorizaciones_en = models.DateTimeField(null=True, blank=True)

    # --- estado ------------------------------------------------------------
    # El recorrido real de una solicitud, y por que tiene cuatro estados y no
    # dos: entre que llega y que alguien la instala hay una DECISION -- si el
    # servicio puede llegar a esa direccion. Antes esa decision existia pero
    # no quedaba escrita en ningun lado: se sabia mirando a nombre de quien
    # estaba el ticket en WispHub, y no quien la habia tomado ni cuando.
    NUEVA = "nueva"              # el link se genero, todavia no la enviaron
    ENVIADA = "enviada"          # llego completa, falta validar factibilidad
    APROBADA = "aprobada"        # hay viabilidad: pasa al equipo que instala
    SIN_FACTIBILIDAD = "sin_factibilidad"
    ESTADOS = ((NUEVA, "Nueva"), (ENVIADA, "Enviada"),
               (APROBADA, "Aprobada"), (SIN_FACTIBILIDAD, "Sin factibilidad"))
    estado = models.CharField(max_length=20, choices=ESTADOS, default=NUEVA)

    # Quien decidio y cuando. No es burocracia: es lo unico que permite
    # preguntar despues por que una instalacion se aprobo, o por que una
    # direccion quedo afuera. En WispHub esa decision no deja rastro -- solo
    # se ve el resultado.
    revisada_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="solicitudes_revisadas")
    revisada_en = models.DateTimeField(null=True, blank=True)
    # Por que no hay factibilidad, o cualquier nota de quien reviso. Se le
    # puede leer al cliente tal cual, asi que se escribe pensando en el.
    nota_revision = models.TextField(blank=True, default="")

    # Cuando se abrio el link por primera vez y cuando se envio. La distancia
    # entre los dos ES la metrica: cuantos abren y no terminan, que es lo que
    # con el formulario del sitio web no se podia saber.
    abierta_en = models.DateTimeField(null=True, blank=True)
    enviada_en = models.DateTimeField(null=True, blank=True)

    # Resultado de los dos efectos que el formulario viejo ya producia. Se
    # guardan por separado y ninguno frena al otro: si WispHub no responde,
    # la solicitud NO se pierde -- queda enviada, con el fallo anotado, y se
    # puede reintentar. Perder una solicitud por un timeout de un tercero
    # seria el peor final posible para esto.
    ticket_wisphub = models.CharField(max_length=64, blank=True, default="")
    correo_enviado_en = models.DateTimeField(null=True, blank=True)
    fallo_integracion = models.TextField(blank=True, default="")

    class Meta:
        db_table = "solicitudes_solicitudservicio"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["org", "estado"]),
            models.Index(fields=["org", "-created_at"]),
        ]

    def __str__(self) -> str:
        quien = f"{self.nombre} {self.apellido}".strip() or self.telefono or "sin nombre"
        return f"Solicitud de {quien} ({self.get_estado_display()})"

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()

    @property
    def tiene_gps(self) -> bool:
        return bool(self.gps_lat and self.gps_lng)
