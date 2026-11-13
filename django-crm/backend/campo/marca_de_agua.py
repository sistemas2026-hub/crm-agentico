# -*- coding: utf-8 -*-
"""
================================================================================
 QUE DICE LA MARCA DE AGUA DE CADA EMPRESA  --  12/11/2026
================================================================================

La configuracion. El dibujo vive aparte, en `campo/services/marca_de_agua.py`,
y la separacion es a proposito: ese modulo es una FUNCION PURA --recibe bytes y
diccionarios, devuelve bytes-- y se prueba sin base de datos ni Django. Meterle
el modelo adentro lo ataria a los dos.

POR QUE UN MODELO PROPIO Y NO CAMPOS EN `Org`
---------------------------------------------
`Org` lo comparten el CRM, las facturas y las solicitudes. Siete campos de
presentacion de una foto de campo adentro de ese modelo mezclan dominios. El
patron de `campo/` para esto ya esta escrito tres veces --
`ConfiguracionDeSeguimiento` (`campo/seguimiento.py`), `ConfiguracionDeReparto`
(`campo/cuadrillas.py`), `ConfiguracionDeAvisos` (`campo/avisos.py`)-- y
siempre igual: `OneToOneField(Org)` en el app que manda.

EL LOGO Y EL NOMBRE NO SE DUPLICAN AQUI
---------------------------------------
Salen de `Org.logo` y `Org.name`, que ya existen y ya tienen pantalla donde
cargarlos (`/settings/organization`). Un `logo_marca_de_agua` propio crearia
dos logos que divergen el dia que la empresa cambie de imagen, y nadie sabria
cual manda.

LOS VALORES POR OMISION ESTAN DEL LADO QUE NO SORPRENDE
-------------------------------------------------------
`activa` arranca APAGADA: ninguna empresa empieza a recibir fotos marcadas por
una migracion. Y `mostrar_coordenadas` arranca APAGADA aunque las demas vengan
encendidas, porque estampar el GPS es grabar el domicilio de una persona
dentro de un archivo que despues viaja al ticket del ISP y se puede reenviar
por WhatsApp. Eso se prende a proposito, no se hereda.
================================================================================
"""
from django.db import models

from common.models import BaseModel, Org

#: Donde va la banda. El valor viaja tal cual al renderizador.
ABAJO_IZQUIERDA = "abajo_izquierda"
ABAJO_DERECHA = "abajo_derecha"
ARRIBA_IZQUIERDA = "arriba_izquierda"
ARRIBA_DERECHA = "arriba_derecha"
POSICIONES = (
    (ABAJO_IZQUIERDA, "Abajo a la izquierda"),
    (ABAJO_DERECHA, "Abajo a la derecha"),
    (ARRIBA_IZQUIERDA, "Arriba a la izquierda"),
    (ARRIBA_DERECHA, "Arriba a la derecha"),
)

#: Las cinco casillas que el usuario pidio, mas las dos de presentacion. El
#: orden es el que la pantalla muestra.
CAMPOS_SI_NO = (
    "activa",
    "mostrar_logo",
    "mostrar_empresa",
    "mostrar_tecnico",
    "mostrar_fecha",
    "mostrar_coordenadas",
    "estampar_capturas",
)


class ConfiguracionDeMarcaDeAgua(BaseModel):
    """Que se estampa en las fotos de campo de esta empresa."""

    org = models.OneToOneField(
        Org, on_delete=models.CASCADE,
        related_name="configuracion_marca_de_agua")

    #: APAGADA de fabrica. Una empresa no empieza a recibir fotos marcadas
    #: porque alguien corrio una migracion.
    activa = models.BooleanField(
        default=False,
        help_text="Si las fotos de campo salen con marca de agua.")

    mostrar_logo = models.BooleanField(
        default=True,
        help_text="El logo que la empresa cargó en su perfil.")
    mostrar_empresa = models.BooleanField(
        default=True, help_text="El nombre de la empresa.")
    mostrar_tecnico = models.BooleanField(
        default=True, help_text="Quién tomó la foto.")
    mostrar_fecha = models.BooleanField(
        default=True,
        help_text="Cuándo se tomó, en hora de Colombia. Es el instante del "
                  "obturador, no el de subida.")

    #: APAGADA aunque el usuario la haya pedido: ver el encabezado. La prende
    #: quien decide que el domicilio viaje dentro de la imagen.
    mostrar_coordenadas = models.BooleanField(
        default=False,
        help_text="Dónde se tomó. Ojo: queda grabado dentro de la imagen, que "
                  "después viaja al ticket del ISP y se puede reenviar.")

    #: Una captura de pantalla NO es una foto, y la marca puede tapar lo que
    #: prueba. El requisito ya se declara como captura en la plantilla.
    estampar_capturas = models.BooleanField(
        default=False,
        help_text="Si también se marcan las capturas de pantalla (por "
                  "ejemplo un test de velocidad). Apagado, porque la marca "
                  "puede tapar justo los números que la captura prueba.")

    posicion = models.CharField(
        max_length=20, choices=POSICIONES, default=ABAJO_IZQUIERDA)

    opacidad = models.PositiveSmallIntegerField(
        default=55,
        help_text="De 10 a 100. Cuanto más alta, más tapa la foto.")

    texto_extra = models.CharField(
        max_length=80, blank=True, default="",
        help_text="Una línea más, si la empresa la necesita.")

    class Meta:
        db_table = "campo_configuracion_marca_de_agua"
        verbose_name = "Configuración de marca de agua"
        verbose_name_plural = "Configuraciones de marca de agua"

    def __str__(self) -> str:                                # pragma: no cover
        return f"Marca de agua de {self.org_id}"

    def como_dict(self) -> dict:
        """Lo que el renderizador necesita, y nada más.

        Se pasa un diccionario y no el modelo para que
        `campo/services/marca_de_agua.py` siga sin saber que existe Django.
        """
        return {
            "activa": self.activa,
            "mostrar_logo": self.mostrar_logo,
            "mostrar_empresa": self.mostrar_empresa,
            "mostrar_tecnico": self.mostrar_tecnico,
            "mostrar_fecha": self.mostrar_fecha,
            "mostrar_coordenadas": self.mostrar_coordenadas,
            "estampar_capturas": self.estampar_capturas,
            "posicion": self.posicion,
            "opacidad": self.opacidad,
            "texto_extra": self.texto_extra,
        }


#: Lo que rige cuando la empresa nunca configuró nada. APAGADA: sin fila, no
#: se estampa. Devolver un diccionario y no `None` deja que quien llama no
#: tenga que preguntar dos cosas distintas.
APAGADA = {
    "activa": False, "mostrar_logo": False, "mostrar_empresa": False,
    "mostrar_tecnico": False, "mostrar_fecha": False,
    "mostrar_coordenadas": False, "estampar_capturas": False,
    "posicion": ABAJO_IZQUIERDA, "opacidad": 55, "texto_extra": "",
}


def configuracion_de(org) -> dict:
    """La configuración de esta empresa, o la apagada.

    NO CREA LA FILA. Esto corre en el camino de subida de cada evidencia: un
    `get_or_create` ahí escribiría en la base en cada foto, y una escritura
    por foto en el camino caliente es justo lo que no hace falta para
    contestar «está apagada».
    """
    if org is None:
        return dict(APAGADA)
    fila = (ConfiguracionDeMarcaDeAgua.objects
            .filter(org=org).first())
    return fila.como_dict() if fila else dict(APAGADA)


# =============================================================================
#  EL PUENTE: de una EvidenciaTrabajo a los datos que el renderizador necesita
# =============================================================================
#  Vive aca y no en `campo/services/marca_de_agua.py` para que ese modulo siga
#  sin saber que existe Django: es una funcion pura y por eso se puede probar
#  sin base, sin migraciones y en milisegundos.
def _logo_de(org) -> bytes | None:
    """Los bytes del logo de la empresa, o None.

    LEE DEL CAMPO, NO DE UNA URL  --  y la diferencia es de seguridad. El
    cargador de WeasyPrint (`invoices/pdf.py:54`) tiene que resolver una URL
    arbitraria y por eso levanta tres muros contra traversal y contra leer el
    logo de otra empresa. Aca no hay URL: `org.logo` es un `FileField` de
    Django, el nombre lo puso el `upload_to="org_logos/"` y el storage ya
    resuelve la ruta. No hay nada que un tercero pueda apuntar.

    Nunca levanta: el logo no puede costar la marca, y la marca no puede
    costar la evidencia.
    """
    campo = getattr(org, "logo", None)
    if not campo:
        return None
    try:
        with campo.open("rb") as f:
            return f.read()
    except Exception:                                            # noqa: BLE001
        #  Sin `str(e)`: el mensaje puede traer la ruta del archivo.
        import logging
        logging.getLogger(__name__).warning(
            "marca de agua: el logo de la empresa no se pudo leer")
        return None


def _es_captura(evidencia) -> bool:
    """Si la plantilla declaro ESTE requisito como captura de pantalla.

    Misma resolucion que usa `inspeccion_visual.que_tenia_que_mostrar`: el
    esquema de la version congelada de la orden, buscando por `requisito_id`.
    No se reimplementa distinto -- dos formas de contestar la misma pregunta
    terminan contestando cosas distintas.
    """
    version = getattr(evidencia.orden_trabajo, "tipo_trabajo_version", None)
    esquema = (getattr(version, "esquema", None) or {}) if version else {}
    for e in esquema.get("evidencias") or []:
        if isinstance(e, dict) and e.get("id") == evidencia.requisito_id:
            return bool(e.get("es_captura"))
    return False


#: Como se reconoce la firma del cliente. La app la sube como una evidencia
#: mas, con este `requisito_id` (`firma_del_cliente.dart`), y NO esta
#: declarada en ninguna plantilla -- por eso no se puede preguntar al esquema.
#: Se compara por prefijo porque la app arma el id con ese campo clave.
_REQUISITOS_DE_FIRMA = ("firma_receptor", "firma")


def _es_firma(evidencia) -> bool:
    rid = str(getattr(evidencia, "requisito_id", "") or "").strip().lower()
    return rid in _REQUISITOS_DE_FIRMA or rid.startswith("firma_")


def nombre_para_la_marca(perfil) -> str:
    """El nombre de quien tomo la foto, o "" -- NUNCA su correo.

    EL CORREO SALIA EN LA FOTO  --  13/11/2026, medido. La version anterior
    pedia `perfil.nombre_completo`, un atributo que `Profile` no tiene, y caia
    a `str(perfil.user)`, que en `common/models.py` es `self.email`. Con la
    marca prendida, cada foto habria salido con el correo del tecnico
    horneado en el pixel, rumbo al ticket del ISP. Las pruebas no lo veian
    porque sus ordenes no tienen tecnico.

    Sin nombre cargado no se imprime nada: un correo es un dato de contacto,
    no una firma, y una vez en la imagen ya no se puede sacar. La app pinta lo
    mismo con este mismo valor (`MarcaDeAguaParaLaAppView`), asi que el
    telefono no puede prometer un nombre que la foto no va a llevar.
    """
    if perfil is None:
        return ""
    usuario = getattr(perfil, "user", None)
    return str(getattr(usuario, "name", "") or "").strip()


def estampar_evidencia(evidencia, contenido: bytes) -> bytes:
    """La foto con la marca de su empresa, o el original.

    SINCRONO, EN EL CAMINO DE SUBIDA, Y ESO ES DELIBERADO. La alternativa era
    una tarea de Celery, y tiene una carrera real: `CompletarTrabajoView`
    manda las fotos al ticket del ISP leyendolas del disco, y nada garantiza
    que la tarea haya corrido antes. La foto llegaria sin marca al ISP de
    forma intermitente -- el peor modo de falla, porque funciona casi siempre.

    Nunca levanta. Si algo sale mal, devuelve lo que entro.
    """
    from campo.services import marca_de_agua as dibujo

    try:
        org = getattr(evidencia, "org", None)
        config = configuracion_de(org)
        if not config.get("activa"):
            #  La salida temprana evita leer el logo y la orden cuando la
            #  empresa no pidio nada. Es el caso de todas, hasta que alguien
            #  la prenda.
            return contenido

        tecnico = ""
        try:
            tecnico = nombre_para_la_marca(
                evidencia.orden_trabajo.tecnico_principal)
        except Exception:                                        # noqa: BLE001
            tecnico = ""

        datos = {
            "empresa": getattr(org, "name", "") or "",
            "tecnico": tecnico,
            "fecha": evidencia.capturada_en_cliente,
            "mime_type": evidencia.mime_type,
            "metadatos_captura": evidencia.metadatos_captura or {},
            "es_captura": _es_captura(evidencia),
            "es_firma": _es_firma(evidencia),
            "logo_bytes": _logo_de(org) if config.get("mostrar_logo") else None,
        }
        return dibujo.estampar(contenido, config, datos)
    except Exception:                                            # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "marca de agua: no se pudo preparar, se guarda el original")
        return contenido
