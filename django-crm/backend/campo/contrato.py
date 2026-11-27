# -*- coding: utf-8 -*-
"""
================================================================================
 EL CONTRATO DEL CLIENTE, CREADO DESDE LA APP  --  13/11/2026
================================================================================

Decision del usuario: *«ahora el tecnico crearia el contrato desde la app de
dexter»*. Hasta hoy el tecnico, parado en la casa del cliente, entraba a WispHub
y llenaba A MANO nombre, apellido, cedula, plan, direccion, coordenadas, el
tecnico y la fecha. Todo eso ya esta en la plataforma antes de que llegue: lo
lleno el cliente en la solicitud (`solicitudes.SolicitudServicio`).

QUE HACE ESTE ARCHIVO, Y QUE TODAVIA NO
---------------------------------------
* Arma el BORRADOR del contrato de una orden: los datos del cliente salen de su
  solicitud --encontrada por el ticket del ISP que la solicitud creo--, y si no
  hay solicitud, de lo que la orden ya sabe del cliente.
* Guarda el contrato FIRMADO: los datos tal como quedaron, el servidor elegido,
  la firma del cliente y una huella. La firma vive SOLO dentro del PDF, igual
  que las fotos del expediente de la solicitud: un objeto que proteger, no dos.
* NO da de alta el cliente en el ISP: eso es otro hecho, y vive en
  `campo/services/alta_en_el_isp.py` (25/11/2026). Firmar guarda el contrato
  y contesta; si la empresa lo tiene encendido, el alta se pide ahi y corre
  despues, en una tarea. Este archivo guarda como va (`alta_*`) y decide
  cuando un contrato se puede anular.

LA FIRMA NO VA A WISPHUB POR API PORQUE WISPHUB NO TIENE DONDE
--------------------------------------------------------------
Medido el 13/11/2026 sobre su especificacion: no hay recurso de contratos,
firmas ni documentos del cliente. Lo que si acepta es `archivo` en la respuesta
de un ticket, y ese camino ya lleva las fotos de campo
(`nucleo/seguimiento/nota_en_el_ticket.py`, que admite PDF). El contrato
firmado viajara por ahi cuando exista el alta.

LO QUE SE AGREGO EL 25/11/2026, PLANEANDO EL FORMATO DE INSTALACION
-------------------------------------------------------------------
El pedido: *«que sea lo mas facil para el tecnico»*. El tecnico no teclea,
confirma. Detalle y decisiones en la ficha
(SPEC/objetivos/agente-de-campo-para-instalaciones.md, «El formato de
instalacion»).

* LOS DATOS LLEGAN ESCRITOS COMO LOS ESCRIBE LA EMPRESA, en el borrador y al
  firmar: `campo/contrato_formato.py`. Lo que es costumbre de una empresa
  (mayusculas, barrio pegado, digitos del telefono) es configuracion.
* EL PLAN SE RECONOCE contra los que la empresa vende, y el servidor se elige
  entre los de ese plan: `campo/contrato_plan.py`.
* LAS COORDENADAS: mandan las del ticket; donde se firmo se guarda aparte.
* UN CONTRATO SE ANULA y la orden firma otro (`anular`). Uno que ya esta en el
  ISP no: deshacerlo es borrar un cliente del otro lado.

EL CONTRATO A NOMBRE DE OTRA PERSONA  --  26/11/2026
---------------------------------------------------
El usuario: *«cuando el tecnico llegue y el contrato se hace a nombre de otra
persona, pero los otros datos siguen igual: solo cambiarian el nombre, el
apellido y la cedula»*. El telefono ya podia cambiarlos (lo que manda gana
sobre el borrador). Lo que estaba mal es lo que el contrato AFIRMABA: las
autorizaciones de habeas data y centrales de riesgo salian de la solicitud,
asi que el PDF habria dicho que la persona nueva las acepto en una solicitud
que nunca lleno. Las acepto la otra.

Por eso «otra persona» es una marca explicita (`titular: "otro"`), no algo que
se deduce de un nombre distinto: con ella el nombre, el apellido y el
documento salen SOLO del telefono, y las autorizaciones tambien, aceptadas por
esa persona al firmar (habeas data obligatoria, como en la solicitud). Lo
demas --telefono, correo, direccion, plan, corte, coordenadas-- sigue igual.
Una cedula que cambia SIN la marca (una app vieja, o un numero mal escrito en
la solicitud) se firma como antes y queda `documento_cambiado`: la oficina lo
ve en Instalaciones.

POR QUE LAS CONDICIONES NO ESTAN ESCRITAS ACA
---------------------------------------------
Son el contrato de cada empresa (permanencia, comodato, mora...). Se cargan como
texto desde la plataforma (`ConfiguracionDeContrato.texto_condiciones`) y van
tal cual al PDF. Un texto legal escrito en codigo seria el de una empresa
imponiendose a todas (CLAUDE.md §3.3).
================================================================================
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from io import BytesIO

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from common.base import BaseModel
from common.models import Org

logger = logging.getLogger(__name__)

#: Lo minimo para que un contrato identifique a alguien y a un lugar.
CAMPOS_OBLIGATORIOS = ("nombre", "numero_documento", "direccion")

#: Los tipos de documento: los mismos que ofrece la solicitud
#: (`solicitud/[token]/+page.svelte`). Solo se eligen cuando el contrato va a
#: nombre de otra persona; si no, manda el de la solicitud.
TIPOS_DE_DOCUMENTO = ("Cédula de ciudadanía", "Cédula de extranjería", "Pasaporte", "NIT")

#: Los datos del cliente que el contrato lleva, en el orden de la pantalla.
CAMPOS_DEL_CLIENTE = ("nombre", "apellido", "tipo_documento", "numero_documento",
                      "telefono", "correo", "direccion", "barrio")

#: Tope del texto de cada campo: es un contrato, no un ensayo, y una cadena de
#: 10.000 caracteres en «nombre» rompe el PDF antes que cualquier otra cosa.
LARGO_MAXIMO = 160

#: La firma llega como PNG. Mas de esto no es una firma.
FIRMA_MAXIMA = 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"


class ConfiguracionDeContrato(BaseModel):
    """Lo que cada empresa pone en su contrato. Editable desde Programacion."""

    org = models.OneToOneField(Org, on_delete=models.CASCADE,
                               related_name="configuracion_contrato")
    nit = models.CharField(max_length=80, blank=True, default="")

    #: LOS SERVIDORES ENTRE LOS QUE ELIGE EL TECNICO. El usuario, 13/11/2026:
    #: «zona es el servidor, asi que debe mostrar los dos y ahi se elige». Cada
    #: uno es `{"id_zona": int, "nombre": str}`: el id es el de `/api/zonas/`
    #: de WispHub, NO el de `/api/router/` -- son catalogos con ids distintos
    #: aunque se llamen igual (skill de WispHub, «CRITICO»).
    servidores = models.JSONField(default=list, blank=True)

    texto_condiciones = models.TextField(blank=True, default="")

    #  COMO ESCRIBE ESTA EMPRESA LOS DATOS DEL CLIENTE  --  25/11/2026
    #  Tres costumbres, no tres reglas del producto: otra empresa escribe con
    #  minusculas, o lleva el barrio aparte, o esta en un pais con otro largo
    #  de telefono. Apagadas por defecto. Ver `campo/contrato_formato.py`.
    datos_en_mayusculas = models.BooleanField(default=False)
    barrio_en_la_direccion = models.BooleanField(default=False)
    #: Cuantos digitos lleva un telefono en el pais de la empresa (10 en
    #: Colombia). Lo que sobre adelante es el indicativo y se quita. 0 = no
    #: recortar.
    digitos_del_telefono = models.PositiveSmallIntegerField(default=0)
    #: COMO SE ESCRIBE CADA PALABRA DE LA DIRECCION (25/11/2026). El usuario:
    #: «si esta escrita cll debe ser calle y si esta kra es cra». Cada regla es
    #: `{"como_lo_escriben": ["CLL", "CL"], "como_queda": "CALLE"}`. Vacio = la
    #: direccion queda como la escribio el cliente. Ver `contrato_formato.abreviar`.
    abreviaturas_de_direccion = models.JSONField(default=list, blank=True)

    #  SI AL FIRMAR SE CREA EL CLIENTE EN EL ISP  --  25/11/2026
    #  APAGADO DE FABRICA, y no es timidez: crear un cliente en el sistema del
    #  proveedor es un efecto que no se deshace solo, y una empresa que ya
    #  firma contratos desde la app no puede empezar a crear clientes porque
    #  alguien desplego una version. Lo enciende quien gestiona, cuando ya
    #  cargo sus servidores y sus rangos de IP. Ver
    #  `campo/services/alta_en_el_isp.py`.
    crear_en_el_isp = models.BooleanField(default=False)
    #  ACTIVAR LA ONU DESDE LA APP (26/11/2026). Apagado de fabrica, como el
    #  alta: escribe en el sistema del proveedor. La VLAN de cada servidor va
    #  en `servidores` (`vlan`). Ver `campo/activacion_onu.py`.
    activar_onu = models.BooleanField(default=False)
    #  LA INSTALACION LA VALIDA UNA PERSONA ANTES DE ACTIVARLA (26/11/2026).
    #  Encendido: el alta se pide al «Finalizar trabajo» y COMO INSTALACION, y
    #  una persona la aprueba en Dexter, que la activa. Ver campo/instalacion.py.
    validar_antes_de_activar = models.BooleanField(default=False)
    #  EL CLIENTE FIRMA EL CONTRATO DEL PROVEEDOR, NO UNO DE DEXTER (26/11/2026).
    #  Encendido: el tecnico confirma los datos sin firma, la instalacion se
    #  crea en ese momento y Dexter guarda el contrato del proveedor con la
    #  cedula y el recibo; el cliente firma ahi. Exige `crear_en_el_isp` y
    #  `validar_antes_de_activar`. Ver campo/contrato_del_proveedor.py.
    firma_en_el_proveedor = models.BooleanField(default=False)
    #  EL ANCHO DE BANDA DE CADA PLAN EN LA RED (27/11/2026). El usuario: «en
    #  SmartOLT tambien hay que ponerle el ancho de banda de descarga y carga».
    #  Cada fila es `{"plan": "PLAN FAMILIA", "bajada": "PLAN_200MB_SV",
    #  "subida": "PLAN_100MB"}`, con los nombres de los perfiles del proveedor
    #  de la red. Vacio = la ONU se autoriza sin perfil, como hasta hoy. Con
    #  filas, un plan sin la suya NO se activa: saldria con el perfil por
    #  defecto. Ver `activacion_onu.perfiles_del_plan`.
    perfiles_de_velocidad = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "campo_configuracion_contrato"
        verbose_name = "Configuración del contrato"

    def como_dict(self) -> dict:
        return {"nit": self.nit, "servidores": list(self.servidores or []),
                "texto_condiciones": self.texto_condiciones,
                "datos_en_mayusculas": self.datos_en_mayusculas,
                "barrio_en_la_direccion": self.barrio_en_la_direccion,
                "digitos_del_telefono": self.digitos_del_telefono,
                "abreviaturas_de_direccion": list(self.abreviaturas_de_direccion or []),
                "crear_en_el_isp": self.crear_en_el_isp,
                "activar_onu": self.activar_onu,
                "validar_antes_de_activar": self.validar_antes_de_activar,
                "firma_en_el_proveedor": self.firma_en_el_proveedor,
                "perfiles_de_velocidad": list(self.perfiles_de_velocidad or [])}


VACIA = {"nit": "", "servidores": [], "texto_condiciones": "",
         "datos_en_mayusculas": False, "barrio_en_la_direccion": False,
         "digitos_del_telefono": 0, "abreviaturas_de_direccion": [],
         "crear_en_el_isp": False, "activar_onu": False,
         "validar_antes_de_activar": False, "firma_en_el_proveedor": False,
         "perfiles_de_velocidad": []}

#: Tope de `digitos_del_telefono`: ningun pais pasa de 15 (E.164).
MAXIMO_DIGITOS_DE_TELEFONO = 15


def configuracion_de(org) -> dict:
    fila = ConfiguracionDeContrato.objects.filter(org=org).first()
    return fila.como_dict() if fila else dict(VACIA)


class ContratoDeServicio(BaseModel):
    """Un contrato firmado en la casa del cliente. No se edita: se firma una
    vez. Si esta mal se ANULA y se firma otro (25/11/2026)."""

    FIRMADO = "firmado"            # existe y tiene firma; el alta en el ISP falta
    EN_EL_ISP = "en_el_isp"        # el cliente quedo creado en WispHub
    ANULADO = "anulado"            # se dejo sin efecto; la orden puede firmar otro
    #  26/11/2026: creada en el proveedor como INSTALACION; falta que una
    #  persona la valide y la active (campo/instalacion.py).
    INSTALACION = "instalacion"
    ESTADOS = ((FIRMADO, "Firmado"), (INSTALACION, "Instalación creada en el ISP"),
               (EN_EL_ISP, "Creado en el ISP"), (ANULADO, "Anulado"))

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="contratos_de_servicio")
    #: PROTECT y no CASCADE: borrar una orden no puede borrar un contrato que
    #: un cliente firmo.
    orden = models.ForeignKey("campo.OrdenTrabajo", on_delete=models.PROTECT,
                              related_name="contratos")
    solicitud = models.ForeignKey("solicitudes.SolicitudServicio",
                                  on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="contratos")
    numero = models.CharField(max_length=40)
    #: Los datos TAL COMO SE FIRMARON. Si despues se corrige la solicitud, el
    #: contrato no cambia: es lo que el cliente acepto ese dia.
    datos = models.JSONField(default=dict)
    #: LA IP DEL CONTRATO, EN SU PROPIA COLUMNA  --  27/11/2026. Es la misma de
    #: `datos["ip_elegida"]`; existe para que LA BASE no acepte dos contratos
    #: vigentes de la empresa con la misma direccion (`una_ip_por_contrato_
    #: vigente`). La comprobacion previa de `firmar` no alcanzaba: dos tecnicos
    #: que confirman en los mismos segundos leen los dos «libre» antes de que
    #: cualquiera guarde. Vacia = el contrato no tiene IP, y no cuenta.
    ip = models.CharField(max_length=15, blank=True, default="")
    pdf = models.FileField(upload_to="contratos/%Y/%m/", null=True, blank=True)
    huella = models.CharField(max_length=64)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=FIRMADO)
    servicio_isp = models.CharField(max_length=64, blank=True, default="")
    firmado_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name="contratos_firmados")
    firmado_en = models.DateTimeField()

    #  LA ANULACION: quien, cuando y por que. El contrato anulado NO se borra
    #  ni pierde su PDF: lo firmo un cliente, y que despues se haya dejado sin
    #  efecto es parte de su historia, no un motivo para que desaparezca.
    anulado_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name="contratos_anulados")
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=300, blank=True, default="")

    #  COMO VA EL ALTA EN EL ISP  --  25/11/2026
    #  Mientras el contrato esta `firmado`, esto dice que paso con crear al
    #  cliente del otro lado. Cuando queda creado, el contrato pasa a
    #  `en_el_isp` y `servicio_isp` lleva su numero.
    #
    #    ""           nadie lo pidio (la empresa no lo tiene encendido)
    #    pedida       esta en la cola, o saliendo
    #    en_curso     se pidio y el cliente todavia no aparece: se sigue mirando
    #    por_revisar  NADIE SABE si quedo creado. No se anula ni se reintenta:
    #                 lo resuelve una persona de gestion mirando en el proveedor
    #    fallida      NO HAY CLIENTE: el proveedor dijo que no, o nunca se le
    #                 pidio. `alta_codigo` y `alta_detalle` dicen por que, y
    #                 una persona decide: reintentar o anular
    #
    #  «NO SE» NO ES «FALLO» (auditoria de frontera, el mismo dia). Al
    #  principio lo incierto tambien quedaba `fallida`, que se puede anular, y
    #  anular para firmar otro con el primer cliente quiza ya creado es crear
    #  dos. Por eso `por_revisar` existe y es un estado aparte.
    #
    #  NO ES UNA SEGUNDA MAQUINA DE ESTADOS DEL CONTRATO: el contrato sigue
    #  teniendo tres (firmado, en el ISP, anulado). Esto es el detalle de UNO.
    ALTA_PEDIDA = "pedida"
    ALTA_EN_CURSO = "en_curso"
    ALTA_POR_REVISAR = "por_revisar"
    ALTA_FALLIDA = "fallida"
    #: La tarea esta trabajando: va a seguir sola.
    ALTA_EN_VUELO = (ALTA_PEDIDA, ALTA_EN_CURSO)
    #: Los que significan «todavia no se sabe si el cliente quedo creado». Con
    #: cualquiera de estos el contrato no se anula ni se vuelve a pedir.
    ALTA_SIN_RESOLVER = (ALTA_PEDIDA, ALTA_EN_CURSO, ALTA_POR_REVISAR)

    alta_estado = models.CharField(max_length=20, blank=True, default="")
    #: El resultado tal como lo nombro el motor (`ip_ocupada`, `fallo`...).
    alta_codigo = models.CharField(max_length=40, blank=True, default="")
    #: Por que, en palabras. SIN datos del cliente: viene del motor, que no
    #: los pone en sus motivos.
    alta_detalle = models.CharField(max_length=300, blank=True, default="")
    #: El trabajo en segundo plano del proveedor, para volver a preguntar.
    alta_tarea = models.CharField(max_length=80, blank=True, default="")
    #: El numero de pedido. Sube solo cuando una persona insiste despues de
    #: que el proveedor dio el anterior por hecho sin dejar cliente: ese si
    #: es otro pedido. Un reintento de red repite el numero y no sale dos
    #: veces (la clave idempotente del motor lo lleva adentro).
    alta_intento = models.PositiveSmallIntegerField(default=0)
    alta_avisos = models.JSONField(default=list, blank=True)
    alta_actualizada_en = models.DateTimeField(null=True, blank=True)
    #: ALGUN PEDIDO DE ESTE CONTRATO PUDO HABER SALIDO hacia el proveedor. No
    #: vuelve a False. Sirve para una sola cosa, y es la que evita el cliente
    #: duplicado: con esto en True, una IP «ocupada» puede estar ocupada por
    #: ESTE cliente, y no se le dice a nadie que elija otra.
    alta_emitida = models.BooleanField(default=False)

    #  EL ALTA COMO INSTALACION Y SU ACTIVACION (26/11/2026). Ver
    #  campo/instalacion.py.
    alta_como_instalacion = models.BooleanField(default=False)
    ACTIVACION_PEDIDA = "pedida"
    ACTIVACION_EN_CURSO = "en_curso"
    ACTIVACION_POR_REVISAR = "por_revisar"
    ACTIVACION_FALLIDA = "fallida"
    #  Lo que esta en vuelo: no se pide otra encima. «Por revisar» NO: una
    #  persona vuelve a aprobar y el motor empieza mirando si ya es cliente.
    ACTIVACION_SIN_RESOLVER = (ACTIVACION_PEDIDA, ACTIVACION_EN_CURSO)
    activacion_estado = models.CharField(max_length=20, blank=True, default="")
    activacion_detalle = models.CharField(max_length=300, blank=True, default="")
    activacion_intento = models.PositiveSmallIntegerField(default=0)
    activacion_actualizada_en = models.DateTimeField(null=True, blank=True)
    activado_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="instalaciones_activadas")
    activado_en = models.DateTimeField(null=True, blank=True)
    #: Quien pidio el ultimo pedido, cuando lo pidio una persona. Vacio = salio
    #: de la firma, y entonces es quien firmo.
    alta_pedida_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="altas_pedidas")
    #: Quien dijo, despues de mirar en el proveedor, si el cliente quedo
    #: creado. Es la unica salida de `por_revisar`.
    alta_resuelta_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                          null=True, blank=True,
                                          related_name="altas_resueltas")
    alta_resuelta_en = models.DateTimeField(null=True, blank=True)

    #  EL CONTRATO DEL PROVEEDOR (26/11/2026): el cliente firma el contrato
    #  del proveedor. `firma_en_el_proveedor` queda fijo al confirmar (lo que
    #  la empresa tenia en ese momento). Ver campo/contrato_del_proveedor.py.
    firma_en_el_proveedor = models.BooleanField(default=False)
    FIRMA_PROVEEDOR_PEDIDA = "pedida"          # se esta preparando
    FIRMA_PROVEEDOR_LISTA = "lista"            # guardado: el cliente puede firmar
    FIRMA_PROVEEDOR_FIRMADA = "firmada"        # el proveedor ya tiene la firma
    FIRMA_PROVEEDOR_FALLIDA = "fallida"        # no quedo: se sabe que no
    FIRMA_PROVEEDOR_POR_REVISAR = "por_revisar"  # salio y nadie sabe si quedo
    firma_proveedor_estado = models.CharField(max_length=20, blank=True, default="")
    firma_proveedor_detalle = models.CharField(max_length=300, blank=True, default="")
    firma_proveedor_avisos = models.JSONField(default=list, blank=True)
    firma_proveedor_intento = models.PositiveSmallIntegerField(default=0)
    firma_proveedor_actualizada_en = models.DateTimeField(null=True, blank=True)
    firma_proveedor_pedida_por = models.ForeignKey(
        "common.Profile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contratos_del_proveedor_pedidos")
    #: El numero del contrato en el proveedor y el usuario del cliente alli
    #: (el que pide el enlace de firma). El ENLACE no se guarda: entra al
    #: portal del cliente sin clave, y se pide cada vez.
    contrato_proveedor = models.CharField(max_length=64, blank=True, default="")
    usuario_proveedor = models.CharField(max_length=200, blank=True, default="")
    firmado_en_el_proveedor_en = models.DateTimeField(null=True, blank=True)

    #  EL COSTO Y EL SERIAL, AL ACTIVAR (26/11/2026): se escriben en el cliente
    #  cuando la oficina aprueba y la instalacion pasa a cliente. Ver
    #  campo/instalacion.py → completar.
    COMPLETAR_PEDIDO = "pedido"
    COMPLETAR_HECHO = "hecho"
    COMPLETAR_NADA = "nada"            # no habia costo ni serial que escribir
    COMPLETAR_FALLIDO = "fallido"
    COMPLETAR_POR_REVISAR = "por_revisar"
    completar_estado = models.CharField(max_length=20, blank=True, default="")
    completar_detalle = models.CharField(max_length=300, blank=True, default="")
    completar_intento = models.PositiveSmallIntegerField(default=0)

    #  LAS FOTOS DEL TRABAJO A LOS ARCHIVOS DEL CLIENTE, AL FINALIZAR
    #  (26/11/2026). Ver campo/contrato_del_proveedor.py → subir_fotos.
    FOTOS_PEDIDAS = "pedidas"
    FOTOS_SUBIDAS = "subidas"
    FOTOS_FALLIDAS = "fallidas"
    FOTOS_POR_REVISAR = "por_revisar"
    fotos_proveedor_estado = models.CharField(max_length=20, blank=True, default="")
    fotos_proveedor_detalle = models.CharField(max_length=300, blank=True, default="")
    fotos_proveedor_intento = models.PositiveSmallIntegerField(default=0)
    fotos_proveedor_pedida_por = models.ForeignKey(
        "common.Profile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fotos_al_proveedor_pedidas")

    class Meta:
        db_table = "campo_contrato_de_servicio"
        verbose_name = "Contrato de servicio"
        constraints = [
            #  UNO VIGENTE POR ORDEN. Un segundo envio del mismo telefono (sin
            #  señal, reintento) devuelve el que ya existe en vez de crear otro.
            #  Los anulados no cuentan: por eso se puede firmar uno nuevo. Hasta
            #  el 25/11/2026 era «uno por orden», y un contrato mal hecho no
            #  tenia arreglo.
            models.UniqueConstraint(fields=["orden"],
                                    condition=~models.Q(estado="anulado"),
                                    name="un_contrato_vigente_por_orden"),
            #  UNA IP, UN CONTRATO VIGENTE, POR EMPRESA (27/11/2026). Excluye
            #  por CLAVE y no por una consulta previa: ahi vive la carrera de
            #  dos confirmaciones simultaneas (CLAUDE.md 12). `firmar` atrapa
            #  el choque y toma la siguiente libre.
            models.UniqueConstraint(fields=["org", "ip"],
                                    condition=~models.Q(estado="anulado") & ~models.Q(ip=""),
                                    name="una_ip_por_contrato_vigente"),
        ]

    def como_dict(self) -> dict:
        return {
            "id": str(self.id),
            "numero": self.numero,
            "estado": self.estado,
            "estado_etiqueta": self.get_estado_display(),
            "servicio_isp": self.servicio_isp or None,
            "firmado_en": self.firmado_en.isoformat(),
            "cliente": (self.datos or {}).get("cliente", {}),
            "servidor": (self.datos or {}).get("servidor", {}),
            "plan": (self.datos or {}).get("plan", ""),
            "ip_elegida": (self.datos or {}).get("ip_elegida", ""),
            "gps": (self.datos or {}).get("gps"),
            #  A nombre de otra persona que la de la solicitud (26/11/2026), y
            #  si la cedula cambio sin decirlo.
            "otro_titular": bool((self.datos or {}).get("otro_titular")),
            "documento_cambiado": bool((self.datos or {}).get("documento_cambiado")),
            "huella": self.huella,
            "tiene_pdf": bool(self.pdf),
            #  Solo uno FIRMADO se puede anular desde aca: el que ya creo al
            #  cliente en el ISP no (ver `anular`). La pantalla lee esto en vez
            #  de decidirlo ella.
            "se_puede_anular": (self.estado == self.FIRMADO
                                and self.alta_estado not in self.ALTA_SIN_RESOLVER),
            #  COMO VA EL ALTA (25/11/2026). `se_puede_pedir`: firmado y sin un
            #  pedido en vuelo. Lo decide el servidor y la pantalla lo lee.
            "alta": {
                "estado": self.alta_estado or None,
                "codigo": self.alta_codigo or None,
                "detalle": self.alta_detalle or None,
                "avisos": list(self.alta_avisos or []),
                "actualizada_en": (self.alta_actualizada_en.isoformat()
                                   if self.alta_actualizada_en else None),
                "se_puede_pedir": (self.estado == self.FIRMADO
                                   and self.alta_estado not in self.ALTA_SIN_RESOLVER),
                #  NADIE SABE si quedo creado: lo dice una persona de gestion.
                "por_revisar": (self.estado == self.FIRMADO
                                and self.alta_estado == self.ALTA_POR_REVISAR),
            },
            #  LA INSTALACION Y SU ACTIVACION (26/11/2026).
            "instalacion": {
                "es_instalacion": bool(self.alta_como_instalacion),
                "activacion": self.activacion_estado or None,
                "detalle": self.activacion_detalle or None,
                "actualizada_en": (self.activacion_actualizada_en.isoformat()
                                   if self.activacion_actualizada_en else None),
                "activada_en": self.activado_en.isoformat() if self.activado_en else None,
                "se_puede_activar": (self.estado == self.INSTALACION
                                     and self.activacion_estado not in self.ACTIVACION_SIN_RESOLVER),
                #  El costo y el serial, escritos en el cliente al activar.
                "costo_y_serial": self.completar_estado or None,
                "costo_y_serial_detalle": self.completar_detalle or None,
            },
            #  EL CONTRATO DEL PROVEEDOR (26/11/2026). Ni el usuario del cliente
            #  ni el enlace viajan aca: el enlace se pide aparte, cada vez.
            "firma_proveedor": {
                "activa": bool(self.firma_en_el_proveedor),
                "estado": self.firma_proveedor_estado or None,
                "detalle": self.firma_proveedor_detalle or None,
                "avisos": list(self.firma_proveedor_avisos or []),
                "contrato": self.contrato_proveedor or None,
                "puede_firmar": self.firma_proveedor_estado == self.FIRMA_PROVEEDOR_LISTA,
                "firmado": self.firma_proveedor_estado == self.FIRMA_PROVEEDOR_FIRMADA,
                "firmado_en": (self.firmado_en_el_proveedor_en.isoformat()
                               if self.firmado_en_el_proveedor_en else None),
                #  Las fotos del trabajo, en los archivos del cliente.
                "fotos": self.fotos_proveedor_estado or None,
                "fotos_detalle": self.fotos_proveedor_detalle or None,
                "se_puede_pedir": (self.firma_en_el_proveedor
                                   and self.estado in (self.INSTALACION, self.EN_EL_ISP)
                                   and self.firma_proveedor_estado in (
                                       "", self.FIRMA_PROVEEDOR_FALLIDA,
                                       self.FIRMA_PROVEEDOR_POR_REVISAR)),
            },
            "anulado_en": self.anulado_en.isoformat() if self.anulado_en else None,
            "motivo_anulacion": self.motivo_anulacion or None,
        }


def vigente_de(orden):
    """El contrato que hoy vale para esa orden (ninguno anulado), o None."""
    return (ContratoDeServicio.objects.filter(orden=orden)
            .exclude(estado=ContratoDeServicio.ANULADO).first())


# =============================================================================
#  DE DONDE SALEN LOS DATOS
# =============================================================================
def _tickets_de(orden) -> set[str]:
    """Los ids de ticket del ISP con los que esta orden se puede reconocer."""
    ids = set()
    ref = str(getattr(orden, "origen_ref", "") or "").strip().lstrip("#")
    if ref and getattr(orden, "origen_tipo", "") in ("ticket", "case", ""):
        ids.add(ref)
    caso = getattr(orden, "caso", None)
    externo = str(getattr(caso, "external_ticket_id", "") or "").strip().lstrip("#")
    if externo:
        ids.add(externo)
    return ids


def solicitud_de_la_orden(orden):
    """La solicitud del cliente de esta orden, o None.

    Se reconoce por el ticket del ISP: la solicitud CREO ese ticket
    (`SolicitudServicio.ticket_wisphub`) y la orden nacio de el. Filtra por la
    empresa de la orden: un id de ticket repetido entre empresas no une a ciegas.
    Una solicitud cancelada o sin factibilidad no sirve para un contrato.
    """
    from solicitudes.models import SolicitudServicio

    ids = _tickets_de(orden)
    if not ids:
        return None
    return (SolicitudServicio.objects
            .filter(org=orden.org, ticket_wisphub__in=ids)
            .exclude(estado__in=[SolicitudServicio.CANCELADA,
                                 SolicitudServicio.SIN_FACTIBILIDAD])
            .order_by("-created_at").first())


def borrador(orden, config: dict | None = None, catalogo=...) -> dict:
    """Lo que la pantalla del contrato muestra antes de firmar.

    LLEGA ESCRITO COMO LO ESCRIBE LA EMPRESA (25/11/2026): el tecnico no
    teclea, confirma. El formato sale de `contrato_formato`, el plan y sus
    servidores de `contrato_plan`.

    `config` y `catalogo` los pasa `firmar`, que ya los leyo; la pantalla no
    los pasa y se leen aca. `...` y no None, porque None es una respuesta
    valida del catalogo: «no se pudo saber».
    """
    from campo import contrato_formato, contrato_plan

    if config is None:
        config = configuracion_de(orden.org)
    if catalogo is ...:
        catalogo = contrato_plan.catalogo_de(orden.org)

    s = solicitud_de_la_orden(orden)
    if s is not None:
        origen, solicitud_id = "solicitud", str(s.id)
        cliente = {
            "nombre": s.nombre, "apellido": s.apellido,
            "tipo_documento": s.tipo_documento or "CC",
            "numero_documento": s.numero_documento, "telefono": s.telefono,
            "correo": s.correo, "direccion": s.direccion, "barrio": s.barrio,
        }
        gps = ({"lat": s.gps_lat, "lng": s.gps_lng,
                "precision_m": s.gps_precision_m} if s.gps_lat and s.gps_lng else None)
        autorizaciones = {
            "habeas_data": bool(s.autoriza_habeas_data),
            "centrales_de_riesgo": bool(s.autoriza_centrales_riesgo),
            "aceptadas_en": s.enviada_en.isoformat() if s.enviada_en else None,
        }
        plan_del_ticket, corte = s.plan_interesado, s.fecha_corte
    elif (del_ticket := contrato_plan.cliente_del_ticket(orden)) is not None:
        #  EL CLIENTE NUEVO ESCRITO EN EL TICKET (27/11/2026). En el ISP la
        #  instalacion se abre sobre un cliente DE PASO y los datos del cliente
        #  de verdad van en la descripcion (`contrato_plan.cliente_del_ticket`).
        #  Ni el nombre, ni el telefono, ni la direccion, ni las coordenadas de
        #  la orden sirven: son las del cliente de paso. Sin autorizaciones,
        #  como sin solicitud.
        origen, solicitud_id = "ticket", None
        cliente = {c: del_ticket.get(c, "") for c in CAMPOS_DEL_CLIENTE}
        gps = del_ticket.get("gps")
        autorizaciones = None
        plan_del_ticket = contrato_plan.dato_del_ticket(orden, "Plan")
        corte = contrato_plan.dato_del_ticket(orden, "Corte")
    else:
        #  SIN SOLICITUD: lo que la orden ya sabe. El nombre viene entero en
        #  un solo campo; el tecnico lo separa si hace falta. Sin
        #  autorizaciones: no hay donde las haya aceptado, y el contrato lo
        #  dira. El plan y el corte, de lo que el ticket traiga escrito.
        origen, solicitud_id = "orden", None
        cliente = {"nombre": orden.cliente_nombre, "apellido": "",
                   "tipo_documento": "CC", "numero_documento": "",
                   "telefono": orden.cliente_telefono, "correo": "",
                   "direccion": orden.cliente_direccion, "barrio": ""}
        gps = ({"lat": orden.gps_lat, "lng": orden.gps_lng}
               if orden.gps_lat is not None and orden.gps_lng is not None else None)
        autorizaciones = None
        plan_del_ticket = contrato_plan.dato_del_ticket(orden, "Plan")
        corte = contrato_plan.dato_del_ticket(orden, "Corte")

    reconocido = contrato_plan.reconocer(plan_del_ticket, catalogo)
    servidores = contrato_plan.servidores_del_plan(reconocido, config["servidores"])
    return {
        "origen": origen, "solicitud_id": solicitud_id,
        "cliente": contrato_formato.cliente_con_formato(cliente, config),
        #  El nombre DEL CATALOGO si se reconocio; si no, lo que decia el
        #  ticket, para que el tecnico vea que pidio el cliente y elija.
        "plan": reconocido["nombre"] if reconocido else _texto(plan_del_ticket),
        "plan_del_ticket": _texto(plan_del_ticket),
        "plan_reconocido": reconocido is not None,
        "corte": _texto(corte),
        #  Lo que el ticket dice del corte, vuelto servidor. Es para dejar una
        #  opcion marcada: el corte se le pregunta al cliente.
        "servidor_sugerido": contrato_plan.servidor_del_corte(corte, servidores),
        "gps": gps, "autorizaciones": autorizaciones,
    }


def para_la_pantalla(orden) -> dict:
    """Todo lo que la pantalla del contrato necesita de una orden SIN firmar.

    * `borrador`: los datos, ya con formato.
    * `servidores`: SOLO los del plan del borrador, con el sugerido primero.
      La app de hoy los dibuja en el orden en que llegan y marca sola el unico
      cuando hay uno: asi el filtro funciona sin esperar un APK nuevo.
    * `planes`: cada plan que la empresa vende con SUS servidores, para que la
      pantalla pueda cambiar de plan sin volver a preguntar.
    * `falta_cargar_servidores`: el plan se reconocio y ninguno de sus
      servidores esta cargado en el contrato de la empresa.

    LO QUE PIDIO EL USUARIO AL PROBARLA EN EL TELEFONO  --  25/11/2026
    -----------------------------------------------------------------
    Tres cosas, resueltas desde aca para que se vean con la app que ya esta
    instalada:

    * «Al escoger el corte, mejor si automatico se lo asigna sin que tenga que
      escoger el tecnico.» El servidor del corte del ticket va PRIMERO y es
      `servidor_sugerido`: la app lo deja marcado. Los demas del plan van
      tambien. El 25/11 se mandaba SOLO ese, y al probarlo el usuario dijo
      «en la parte de corte no deja escoger» (26/11/2026): el ticket puede
      traer el corte equivocado y el tecnico, en la casa, lo corrige.
    * «En la cedula sale CC y los numeros.» La app dibuja el tipo de documento
      delante del numero. Se le manda vacio en `cliente.tipo_documento`, y el
      verdadero viaja aparte (`borrador.tipo_documento`). Al firmar, si el
      telefono lo devuelve vacio, se toma el de la solicitud: el contrato
      firmado SI lleva el tipo de documento.
    * «Habeas data y centrales de riesgo ya no es necesario.» No se le mandan
      a la pantalla. SIGUEN EN EL CONTRATO: son la prueba de que el cliente
      autorizo, y las toma `firmar` de la solicitud, no del telefono.
    """
    from campo import contrato_plan

    config = configuracion_de(orden.org)
    catalogo = contrato_plan.catalogo_de(orden.org)
    b = borrador(orden, config, catalogo)
    reconocido = contrato_plan.reconocer(b["plan"], catalogo) if b["plan_reconocido"] else None
    servidores = contrato_plan.servidores_del_plan(reconocido, config["servidores"])
    sugerido = b["servidor_sugerido"]
    servidores = sorted(servidores, key=lambda s: s.get("id_zona") != sugerido)
    b = {**b, "autorizaciones": None,
         "tipo_documento": b["cliente"].get("tipo_documento", ""),
         "cliente": {**b["cliente"], "tipo_documento": ""}}
    return {
        "borrador": b,
        "servidores": servidores,
        #  Cada plan con SU servidor del corte (26/11/2026): la app muestra el
        #  plan como menu, y si el tecnico cambia de plan tiene que quedar
        #  marcado solo el del corte de ESE plan. Lo decide el servidor, con la
        #  misma regla que `servidor_sugerido`; la pantalla solo lo representa.
        "planes": [{"nombre": p["nombre"], "servidores": sp,
                    "servidor_sugerido": contrato_plan.servidor_del_corte(b["corte"], sp)}
                   for p in (catalogo or [])
                   for sp in [contrato_plan.servidores_del_plan(p, config["servidores"])]],
        "falta_cargar_servidores": bool(reconocido and config["servidores"] and not servidores),
        #  A NOMBRE DE OTRA PERSONA (26/11/2026): que puede elegir la pantalla
        #  y que tiene que aceptar esa persona. Lo dice el servidor para que
        #  el texto sea uno solo, con el nombre de la empresa.
        "otro_titular": para_otro_titular(orden.org),
    }


def para_otro_titular(org) -> dict:
    """Los tipos de documento y las dos autorizaciones que acepta la persona a
    cuyo nombre va el contrato cuando no es la de la solicitud. Las mismas dos
    que pide la solicitud, con la misma regla: habeas data obligatoria,
    centrales de riesgo no. Los textos son los rotulos del PDF; las
    condiciones completas son las de la empresa (`texto_condiciones`)."""
    empresa = (getattr(org, "name", "") or "").strip() or "la empresa"
    return {
        "tipos_de_documento": list(TIPOS_DE_DOCUMENTO),
        "autorizaciones": [
            {"id": "habeas_data", "obligatoria": True,
             "texto": f"Autoriza a {empresa} el tratamiento de sus datos personales "
                      "(habeas data, Ley 1581 de 2012)."},
            {"id": "centrales_de_riesgo", "obligatoria": False,
             "texto": f"Autoriza a {empresa} a consultar y reportar su información "
                      "en centrales de riesgo (Ley 1266 de 2008)."},
        ],
    }


def _mismo_documento(a, b) -> bool:
    """Dos numeros de documento son el mismo si coinciden sus letras y digitos:
    una cedula con puntos o espacios es la misma cedula."""
    import re
    limpio = lambda x: re.sub(r"[^0-9A-Za-z]", "", str(x or "")).upper()  # noqa: E731
    return limpio(a) == limpio(b)


# =============================================================================
#  FIRMAR
# =============================================================================
class ContratoInvalido(ValueError):
    """Lo que el telefono mando no alcanza para un contrato. El texto se le
    muestra al tecnico tal cual."""


def _texto(valor) -> str:
    return str(valor or "").strip()[:LARGO_MAXIMO]


def _firma_de(cuerpo: dict) -> bytes:
    crudo = str(cuerpo.get("firma_png_base64") or "")
    if "," in crudo and crudo.startswith("data:"):
        crudo = crudo.split(",", 1)[1]
    try:
        firma = base64.b64decode(crudo, validate=True)
    except (ValueError, TypeError):
        raise ContratoInvalido("La firma no llegó bien. Pídele al cliente que firme otra vez.")
    if not firma.startswith(_PNG) or len(firma) > FIRMA_MAXIMA:
        raise ContratoInvalido("La firma no llegó bien. Pídele al cliente que firme otra vez.")
    return firma


def _gps_de(cuerpo: dict) -> dict | None:
    g = cuerpo.get("gps")
    if not isinstance(g, dict):
        return None
    try:
        lat, lng = float(g["lat"]), float(g["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None   # 0,0 es el golfo de Guinea, no una casa
    out = {"lat": round(lat, 6), "lng": round(lng, 6)}
    try:
        out["precision_m"] = int(float(g.get("precision_m") or 0))
    except (TypeError, ValueError):
        pass
    return out


def _ip_de(cuerpo: dict) -> str:
    """La IP que el tecnico eligio, validada en FORMA. "" si no mando ninguna.

    QUE SE COMPRUEBA ACA Y QUE NO  --  14/11/2026
    ---------------------------------------------
    Aca: que sea una IPv4 de verdad y que su ultimo octeto no sea `.0` (la
    red), `.255` (el broadcast) ni `.1` (la puerta de enlace, medida el 14/11:
    libre en 83 de 86 pools, uno con 240 de 254 ocupadas).

    **Aca NO se comprueba que este libre**, y es a proposito. Comprobarlo exige
    preguntarle al motor, que puede no contestar -- y entonces el tecnico, con
    el cliente delante y la firma hecha, no podria firmar por un problema de
    red que no es suyo. Firmar no crea el cliente en el ISP: no hay ningun
    efecto externo que proteger todavia.

    La comprobacion de verdad va donde esta el efecto irreversible: el alta.
    Ahi, contra la ocupacion viva y en el ultimo metro, que es donde la
    frontera la pone (CLAUDE.md 5). Esta IP es «la que eligio el tecnico», no
    «la que el sistema garantiza libre», y el nombre del campo lo dice.

    VACIO ES VALIDO. Una empresa sin pools declarados no tiene nada que
    ofrecer, y eso no puede impedir que se firme un contrato.
    """
    import ipaddress

    crudo = str(cuerpo.get("ip") or "").strip()
    if not crudo:
        return ""
    try:
        direccion = ipaddress.ip_address(crudo)
    except ValueError:
        raise ContratoInvalido("Esa no es una dirección IP válida.")
    if direccion.version != 4:
        raise ContratoInvalido("La dirección tiene que ser IPv4.")
    ultimo = int(str(direccion).rsplit(".", 1)[1])
    if ultimo in (0, 255):
        raise ContratoInvalido(
            "Esa dirección es la red o el broadcast del rango: no es de un cliente.")
    if ultimo == 1:
        raise ContratoInvalido(
            "El .1 es la puerta de enlace del rango: elegí otra.")
    return str(direccion)


#: Cuantas candidatas se le preguntan al proveedor al firmar. Cada una es una
#: lectura (~1 s); el telefono espera 40 s la firma entera.
COMPROBACIONES_DE_IP = 5


def _ip_automatica(org, id_zona, ademas=()) -> str:
    """La IP que el sistema le asigna al contrato: la primera libre del
    servidor que no tenga otro contrato vigente.

    Pregunta al motor por las libres (`services.ips_libres`, el mismo camino
    que alimentaba la lista de la app) y descarta las que ya eligio otro
    contrato que no este anulado: el motor no sabe de contratos, solo de lo
    que el proveedor ya tiene.

    VACIO SI NO SE PUEDE SABER. Si el motor no contesta o no hay ninguna
    libre, el contrato se firma sin IP, igual que antes (ver `_ip_de`): el
    tecnico tiene al cliente delante y la firma hecha, y una falla de red que
    no es suya no puede impedirle firmar. La IP se comprueba de verdad en el
    alta, contra la ocupacion viva.

    Y SE PREGUNTA EN VIVO ANTES DE PONERLA  --  26/11/2026. La lista sale de
    una foto que envejece: en la primera prueba real del alta, la primera
    libre de la foto se la habian dado a un cliente esa misma tarde, y el
    contrato quedo firmado con una IP ajena. Ahora cada candidata se le
    pregunta al proveedor (hasta `COMPROBACIONES_DE_IP`): la tomada se salta.
    Si no se puede preguntar, se usa la candidata como antes: el alta la
    vuelve a mirar antes de crear, y una lectura caida no impide firmar.

    `ademas`: las que ya chocaron con la regla de la base en un intento
    anterior de esta misma firma (27/11/2026): otro contrato las tomo en esos
    segundos y esta consulta todavia podria no verlo.
    """
    from campo.services import ips_libres

    try:
        libres = ips_libres.para_la_zona(org, id_zona, ips_libres.CUANTAS_MAXIMO).get("libres") or []
    except Exception:   # noqa: BLE001 - no poder preguntar no impide firmar
        logger.warning("contrato.ip_automatica_sin_respuesta")
        return ""
    vigentes = (ContratoDeServicio.objects.filter(org=org)
                .exclude(estado=ContratoDeServicio.ANULADO))
    tomadas = (set(vigentes.values_list("datos__ip_elegida", flat=True))
               | set(vigentes.values_list("ip", flat=True)) | set(ademas))
    preguntadas = 0
    for crudo in libres:
        try:
            ip = _ip_de({"ip": crudo})
        except ContratoInvalido:
            continue
        if not ip or ip in tomadas:
            continue
        if preguntadas >= COMPROBACIONES_DE_IP:
            logger.warning("contrato.ip_automatica_todas_tomadas_en_vivo")
            return ""
        preguntadas += 1
        libre = ips_libres.libre_en_el_proveedor(org, ip)
        if libre is False:
            continue
        if libre is None:
            logger.warning("contrato.ip_automatica_sin_comprobar_en_vivo")
        return ip
    return ""


def firmar(orden, profile, cuerpo: dict) -> tuple["ContratoDeServicio", bool]:
    """Crea el contrato firmado de la orden. Devuelve (contrato, creado).

    Idempotente por orden: si ya hay uno VIGENTE, se devuelve ese y
    `creado=False`. Uno anulado no cuenta: la orden puede firmar otro.
    """
    from campo import contrato_formato, contrato_plan
    from campo.marca_de_agua import nombre_para_la_marca

    existente = vigente_de(orden)
    if existente is not None:
        return existente, False

    config = configuracion_de(orden.org)
    catalogo = contrato_plan.catalogo_de(orden.org)
    base = borrador(orden, config, catalogo)
    llegado = cuerpo.get("cliente") if isinstance(cuerpo.get("cliente"), dict) else {}
    #  LO QUE MANDA EL TELEFONO GANA SOBRE EL BORRADOR: el tecnico tiene el
    #  documento delante y pudo corregir un dato mal escrito en la solicitud.
    cliente = {c: _texto(llegado.get(c, base["cliente"].get(c, ""))) for c in CAMPOS_DEL_CLIENTE}
    #  A NOMBRE DE OTRA PERSONA (26/11/2026, ver el encabezado): el nombre, el
    #  apellido y el documento salen SOLO del telefono, sin caer a los de la
    #  solicitud, que son de otra persona.
    otro_titular = cuerpo.get("titular") == "otro"
    if otro_titular:
        for c in ("nombre", "apellido", "tipo_documento", "numero_documento"):
            cliente[c] = _texto(llegado.get(c))
        if cliente["tipo_documento"] not in TIPOS_DE_DOCUMENTO:
            raise ContratoInvalido("Elige el tipo de documento de la persona a cuyo nombre va el contrato.")
        if (base["origen"] == "solicitud" and cliente["numero_documento"]
                and _mismo_documento(cliente["numero_documento"],
                                     base["cliente"].get("numero_documento"))):
            raise ContratoInvalido(
                "Ese documento es el de la solicitud: no es otra persona. "
                "Vuelve a los datos de la solicitud.")
    #  EL TIPO DE DOCUMENTO VACIO NO SE FIRMA ASI: la pantalla lo recibe vacio
    #  para no dibujarlo delante del numero (ver `para_la_pantalla`) y lo
    #  devuelve igual. El contrato lleva el de la solicitud.
    if not cliente["tipo_documento"]:
        cliente["tipo_documento"] = _texto(base["cliente"].get("tipo_documento")) or "CC"
    #  Y LO QUE CORRIGIO QUEDA ESCRITO COMO TODO LO DEMAS: una cedula tecleada
    #  con puntos o un nombre en minusculas no entran asi al contrato. El
    #  barrio del borrador viaja para que, si el tecnico lo cambio, la
    #  direccion no se quede con el viejo pegado.
    cliente = contrato_formato.cliente_con_formato(
        cliente, config, barrio_anterior=base["cliente"].get("barrio", ""))
    faltan = [c for c in CAMPOS_OBLIGATORIOS if not cliente[c]]
    if faltan:
        nombres = {"nombre": "el nombre", "numero_documento": "el documento",
                   "direccion": "la dirección"}
        raise ContratoInvalido("Falta " + ", ".join(nombres[c] for c in faltan) + ".")

    #  LAS AUTORIZACIONES DE OTRA PERSONA las acepta ESA persona, al firmar.
    #  Las de la solicitud no le sirven: las acepto quien la lleno.
    autorizaciones_nuevas = None
    if otro_titular:
        aut = cuerpo.get("autorizaciones") if isinstance(cuerpo.get("autorizaciones"), dict) else {}
        if aut.get("habeas_data") is not True:
            raise ContratoInvalido(
                "Falta que la persona a cuyo nombre va el contrato autorice el "
                "tratamiento de sus datos (habeas data).")
        autorizaciones_nuevas = {"habeas_data": True,
                                 "centrales_de_riesgo": aut.get("centrales_de_riesgo") is True}
    #  UNA CEDULA QUE CAMBIO SIN DECIR «OTRA PERSONA»: una app vieja, o un
    #  numero mal escrito en la solicitud. Se firma como antes, y queda dicho.
    documento_cambiado = (not otro_titular and base["origen"] == "solicitud"
                          and not _mismo_documento(cliente["numero_documento"],
                                                   base["cliente"].get("numero_documento")))

    plan = _texto(cuerpo.get("plan") or base.get("plan"))
    if not plan:
        raise ContratoInvalido("Falta el plan.")
    #  EL PLAN TIENE QUE SER UNO DE LOS QUE LA EMPRESA VENDE, cuando se puede
    #  saber cuales son. Con el catalogo a la vista, un plan que no esta ahi
    #  es un contrato que el alta no va a poder crear: mejor decirlo ahora,
    #  con el cliente delante, que cuando ya firmo. Sin catalogo (el motor no
    #  contesto, o la empresa no cargo planes) se firma con lo escrito: no
    #  poder preguntar no puede dejar al tecnico sin firmar.
    reconocido = contrato_plan.reconocer(plan, catalogo)
    if catalogo and reconocido is None:
        raise ContratoInvalido(
            "Ese plan no es uno de los que vende tu empresa. Escribe uno de estos: "
            + ", ".join(p["nombre"] for p in catalogo) + ".")
    if reconocido is not None:
        plan = reconocido["nombre"]

    #  EL SERVIDOR, ENTRE LOS DE ESE PLAN. Elegir el corte es elegir entre
    #  ellos (`contrato_plan`). Con uno solo no hay nada que elegir.
    permitidos = contrato_plan.servidores_del_plan(reconocido, config["servidores"])
    try:
        id_zona = int(cuerpo.get("id_zona"))
    except (TypeError, ValueError):
        id_zona = permitidos[0].get("id_zona") if len(permitidos) == 1 else None
    servidor = next((s for s in permitidos if s.get("id_zona") == id_zona), None)
    if servidor is None:
        if not config["servidores"]:
            raise ContratoInvalido("Tu empresa todavía no cargó sus servidores.")
        if not permitidos:
            raise ContratoInvalido(
                f"Tu empresa no cargó en su contrato el servidor del plan {plan} "
                "(Programación → El contrato de instalación).")
        if any(isinstance(s, dict) and s.get("id_zona") == id_zona
               for s in config["servidores"]):
            raise ContratoInvalido(
                f"Ese servidor no es del plan {plan}. Elige: "
                + " o ".join(str(s.get("nombre", "")) for s in permitidos) + ".")
        raise ContratoInvalido("Elige el servidor.")

    #  LA IP QUE ELIGIO EL TECNICO. Va en los datos firmados porque es parte
    #  de lo que se decidio en la casa, y de aqui la lee el alta cuando se
    #  construya. Se llama asi --«la que eligio»-- y no «asignada»: hasta que
    #  el alta la aplique, nadie la tiene.
    ip_elegida = _ip_de(cuerpo)
    #  UNA IP, UN CONTRATO (auditoria de frontera, 25/11/2026). Dos contratos
    #  vigentes con la misma IP pasarian los dos la comprobacion del alta --la
    #  IP esta libre hasta que el primero termine de crearse-- y saldrian dos
    #  pedidos por la misma direccion. Aca no hace falta preguntarle a nadie:
    #  es una consulta a la propia base. Los anulados no cuentan.
    if ip_elegida and ip_de_otro_contrato(orden.org, ip_elegida):
        raise ContratoInvalido(
            "Esa dirección IP ya la eligió otro contrato. Elige otra.")

    #  EL CLIENTE FIRMA EN EL PROVEEDOR (26/11/2026): aca no hay firma, y la
    #  cedula y el recibo TIENEN que estar subidos (decision del usuario:
    #  «exigirlas antes de confirmar»): se guardan con el contrato del
    #  proveedor apenas se crea la instalacion, antes de que el cliente firme.
    sin_firma = bool(config.get("firma_en_el_proveedor"))
    if sin_firma:
        from campo.contrato_del_proveedor import falta_el_costo, faltan_documentos

        faltan = faltan_documentos(orden)
        if faltan is None:
            raise ContratoInvalido("No se pudo saber qué documentos pide la plantilla. "
                                   "Avisa a la oficina.")
        #  EL VALOR DE LA INSTALACION TAMBIEN (26/11/2026): viaja al crear la
        #  instalacion, que es ahora; despues el proveedor ya no lo toma.
        costo = falta_el_costo(orden)
        if costo:
            faltan = [*faltan, f"«{costo}» anotado"]
        if faltan:
            raise ContratoInvalido(
                "Antes de confirmar falta: " + ", ".join(faltan)
                + ". Si ya lo hiciste, espera a que suba (necesitas señal) y vuelve a "
                  "tocar «Confirmar contrato».")
        firma = b""
    else:
        firma = _firma_de(cuerpo)
    #  LA IP LA ASIGNA EL SISTEMA (el usuario, 26/11/2026: «seria mejor si el
    #  sistema le indica la IP al contrato sin que tenga que elegir el
    #  tecnico»). Si el telefono no manda una, se toma la primera libre del
    #  servidor que no haya elegido otro contrato vigente. Va despues de
    #  validar todo lo demas: un pedido que no se va a firmar no le pregunta
    #  nada al motor. Una app vieja que todavia manda la suya, la sigue usando.
    ip_origen = "tecnico" if ip_elegida else ""
    if not ip_elegida:
        ip_elegida = _ip_automatica(orden.org, servidor["id_zona"])
        ip_origen = "sistema" if ip_elegida else ""
    ahora = timezone.now()
    #  LAS COORDENADAS: MANDAN LAS DEL TICKET (el usuario, 25/11/2026: «las
    #  coordenadas que tienen el ticket»). Hasta ese dia mandaba el GPS del
    #  telefono y las del ticket eran el respaldo; ahora es al reves. Las del
    #  telefono se guardan igual, aparte: dicen DONDE SE FIRMO, que es otro
    #  dato y no se pierde por haber cambiado cual manda.
    del_telefono = _gps_de(cuerpo)
    #  LAS QUE CORRIGIO EL TECNICO GANAN (el usuario, 26/11/2026: «en la parte
    #  de coordenadas que permita editar, y si sale un mapa para que
    #  seleccione la ubicacion correcta»). Llegan aparte (`coordenadas`) del
    #  GPS del telefono (`gps`), porque son dos datos distintos: donde queda
    #  la casa y donde se firmo. Unas invalidas --fuera de rango, 0,0-- no
    #  cuentan y vale lo de siempre.
    del_tecnico = _gps_de({"gps": cuerpo.get("coordenadas")})
    if del_tecnico:
        del_tecnico.pop("precision_m", None)
    gps = del_tecnico or base.get("gps") or del_telefono
    gps_origen = ("tecnico" if del_tecnico else "ticket" if base.get("gps")
                  else "telefono" if del_telefono else "")
    datos = {
        "cliente": cliente,
        "plan": plan,
        #  Si el plan salio del catalogo de la empresa o es texto que nadie
        #  pudo comprobar (no habia catalogo). El alta lo lee para no confiar
        #  en un nombre sin comprobar.
        "plan_del_catalogo": reconocido is not None,
        "ip_elegida": ip_elegida,
        #  Quien la puso: «sistema» (la primera libre al firmar) o «tecnico»
        #  (una app vieja que todavia la ofrece). Vacio: no habia ninguna.
        "ip_origen": ip_origen,
        "servidor": {"id_zona": servidor["id_zona"], "nombre": servidor.get("nombre", "")},
        "gps": gps,
        #  De donde salieron: «tecnico» (las corrigio en el mapa), «ticket» o
        #  «telefono» (el ticket no traia).
        "gps_origen": gps_origen,
        "gps_del_telefono": del_telefono,
        #  Las de la solicitud, o las que la otra persona acepto al firmar.
        "autorizaciones": (base.get("autorizaciones") if autorizaciones_nuevas is None
                           else {**autorizaciones_nuevas, "aceptadas_en": ahora.isoformat(),
                                 "donde": "al_firmar"}),
        "otro_titular": otro_titular,
        "documento_cambiado": documento_cambiado,
        "tecnico": nombre_para_la_marca(profile),
        "orden_numero": orden.numero,
        "origen": base["origen"],
    }
    #  EL NUMERO NO SE REPITE: el segundo contrato de una orden (el primero se
    #  anulo) lleva «-2». Dos papeles firmados con el mismo numero no se
    #  pueden distinguir cuando alguien pregunte por uno.
    anteriores = ContratoDeServicio.objects.filter(orden=orden).count()
    numero = f"C-{ahora:%Y}-{orden.numero:06d}" + (f"-{anteriores + 1}" if anteriores else "")

    def _armar(ip: str, origen: str) -> "ContratoDeServicio":
        """El contrato con ESA IP: sus datos firmados, su huella y su PDF. Se
        vuelve a armar entero si la IP choca, porque la IP va en los tres."""
        firmados = {**datos, "ip_elegida": ip, "ip_origen": origen}
        canonico = json.dumps(firmados, sort_keys=True, ensure_ascii=False).encode("utf-8")
        nuevo = ContratoDeServicio(
            org=orden.org, orden=orden,
            solicitud_id=base.get("solicitud_id"),
            numero=numero, datos=firmados,
            huella=hashlib.sha256(canonico + hashlib.sha256(firma).digest()).hexdigest(),
            ip=ip, firmado_por=profile, firmado_en=ahora,
            firma_en_el_proveedor=sin_firma,
        )
        nuevo.pdf.save(f"{numero}.pdf", armar_pdf(nuevo, firma, config), save=False)
        return nuevo

    contrato = _armar(ip_elegida, ip_origen)
    chocadas: list[str] = []
    while True:
        try:
            #  En su propia transaccion: si una restriccion frena este guardado,
            #  la de quien llama sigue sana y se puede leer quien gano.
            with transaction.atomic():
                contrato.save()
            return contrato, True
        except IntegrityError:
            #  Otro envio del MISMO contrato gano la carrera: la restriccion
            #  `un_contrato_vigente_por_orden` lo freno. Se devuelve el que quedo.
            ganador = vigente_de(orden)
            if ganador is not None:
                _sin_pdf(contrato)
                return ganador, False
            #  OTRO CONTRATO TOMO ESTA IP EN ESTOS MISMOS SEGUNDOS (27/11/2026):
            #  lo freno `una_ip_por_contrato_vigente`. La que puso el sistema
            #  se cambia por la siguiente libre; la que eligio el tecnico (una
            #  app vieja) se le devuelve, como la comprobacion de arriba.
            if not (contrato.ip and ip_de_otro_contrato(orden.org, contrato.ip)):
                raise
            _sin_pdf(contrato)
            if ip_origen != "sistema":
                raise ContratoInvalido(
                    "Esa dirección IP ya la eligió otro contrato. Elige otra.") from None
            chocadas.append(contrato.ip)
            if len(chocadas) > INTENTOS_DE_IP:
                raise ContratoInvalido(
                    "Otros contratos tomaron las IP libres en este mismo momento. "
                    "Toca «Confirmar contrato» de nuevo.") from None
            logger.warning("contrato.ip_tomada_por_otro_se_toma_la_siguiente")
            nueva = _ip_automatica(orden.org, servidor["id_zona"], ademas=chocadas)
            contrato = _armar(nueva, "sistema" if nueva else "")


#: Cuantas veces se cambia la IP de una firma que choco con otra. Cada choque
#: es otro contrato confirmado en los mismos segundos: tres seguidos ya no es
#: una carrera sino algo que una persona tiene que mirar.
INTENTOS_DE_IP = 3


def ip_de_otro_contrato(org, ip: str) -> bool:
    """Si otro contrato VIGENTE de la empresa ya tiene esa IP (la columna o los
    datos firmados de uno anterior a la columna)."""
    vigentes = ContratoDeServicio.objects.filter(org=org).exclude(estado=ContratoDeServicio.ANULADO)
    return (vigentes.filter(ip=ip).exists()
            or vigentes.filter(datos__ip_elegida=ip).exists())


def _sin_pdf(contrato) -> None:
    """Borra el PDF de un contrato que no se llego a guardar: quedaria suelto
    en el almacenamiento, firmado y con una IP que no es la suya."""
    try:
        if contrato.pdf:
            contrato.pdf.delete(save=False)
    except Exception:                                            # noqa: BLE001
        logger.warning("contrato.pdf_suelto_no_se_pudo_borrar")


# =============================================================================
#  ANULAR  --  25/11/2026
# =============================================================================
class ContratoNoAnulable(ValueError):
    """Ese contrato no se puede anular desde aca. El texto se muestra tal cual."""


#: Lo minimo para que el motivo diga algo.
MOTIVO_MINIMO = 5
MOTIVO_MAXIMO = 300


def _por_que_no_se_anula(contrato) -> str:
    """Lo que se le dice a quien quiere anular con el alta sin resolver."""
    if contrato.alta_estado == ContratoDeServicio.ALTA_POR_REVISAR:
        return ("No se sabe si el cliente quedó creado en el sistema del "
                "proveedor. Antes de anular, alguien de gestión tiene que "
                "revisarlo allá y decir si quedó o no (Instalaciones).")
    return ("El cliente se está creando en el sistema del proveedor y todavía "
            "no se sabe si quedó. Espera a que termine para anular.")


def anular(contrato: "ContratoDeServicio", profile, motivo) -> "ContratoDeServicio":
    """Deja un contrato sin efecto, para que la orden pueda firmar otro.

    Pedido del usuario: *«si se crea un contrato se puede borrar y crear
    otro»*. Se ANULA, no se borra: queda con quien lo anulo, cuando y por que,
    y con su PDF.

    UNO QUE YA ESTA EN EL ISP NO SE ANULA DESDE ACA. Ese contrato ya creo un
    cliente del otro lado; anularlo solo en la plataforma dejaria al cliente
    creado alla y la orden lista para crearlo OTRA VEZ. Deshacerlo es borrar
    un cliente en el sistema del proveedor, que es una accion critica (PRD 2)
    y va por la frontera del motor cuando esa baja exista. Hasta entonces se
    rechaza, y se dice por que.

    Idempotente: anular uno ya anulado lo devuelve igual, sin tocarlo.
    """
    if contrato.estado == ContratoDeServicio.ANULADO:
        return contrato
    if contrato.estado != ContratoDeServicio.FIRMADO:
        raise ContratoNoAnulable(
            "Este contrato ya creó al cliente en el sistema del proveedor. "
            "Anularlo desde aquí lo dejaría creado allá: pídeselo a la oficina.")
    #  CON EL ALTA EN VUELO NO SE ANULA (25/11/2026). Nadie sabe todavia si
    #  el cliente quedo creado del otro lado: anular ahora dejaria la orden
    #  lista para firmar otro contrato y crear OTRO cliente, con el primero
    #  quiza ya hecho. Cuando el alta termine --creado o fallido-- se sabe.
    if contrato.alta_estado in ContratoDeServicio.ALTA_SIN_RESOLVER:
        raise ContratoNoAnulable(_por_que_no_se_anula(contrato))
    motivo = " ".join(str(motivo or "").split())[:MOTIVO_MAXIMO]
    if len(motivo) < MOTIVO_MINIMO:
        raise ContratoInvalido("Escribe por qué se anula el contrato.")

    #  CON CONDICION EN LA MISMA SENTENCIA, no «leer y despues guardar»: si el
    #  alta lo pasa a `en_el_isp` entre la lectura de arriba y este cambio,
    #  esta sentencia no toca ninguna fila y el contrato no se anula.
    ahora = timezone.now()
    tocadas = (ContratoDeServicio.objects
               .filter(pk=contrato.pk, estado=ContratoDeServicio.FIRMADO)
               .exclude(alta_estado__in=ContratoDeServicio.ALTA_SIN_RESOLVER)
               .update(estado=ContratoDeServicio.ANULADO, anulado_por=profile,
                       anulado_en=ahora, motivo_anulacion=motivo, updated_at=ahora))
    contrato.refresh_from_db()
    if not tocadas and contrato.estado != ContratoDeServicio.ANULADO:
        if contrato.alta_estado in ContratoDeServicio.ALTA_SIN_RESOLVER:
            raise ContratoNoAnulable(_por_que_no_se_anula(contrato))
        raise ContratoNoAnulable(
            "Este contrato ya creó al cliente en el sistema del proveedor. "
            "Anularlo desde aquí lo dejaría creado allá: pídeselo a la oficina.")
    return contrato


# =============================================================================
#  EL PDF
# =============================================================================
def _fecha_bogota(cuando) -> tuple[str, str]:
    from zoneinfo import ZoneInfo

    local = cuando.astimezone(ZoneInfo("America/Bogota"))
    return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")


def armar_pdf(contrato: "ContratoDeServicio", firma: bytes, config: dict):
    """El contrato en PDF, con el mismo motor que el expediente de la solicitud."""
    from django.core.files.base import ContentFile
    from django.template.loader import render_to_string
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    from campo.contrato_formato import direccion_ya_trae_el_barrio
    from solicitudes.pdf import _data_uri, _logo_de

    d = contrato.datos
    #  Si la empresa pega el barrio a la direccion, la direccion YA lo trae:
    #  imprimirlo otra vez al lado dejaria «... VILLA DEL SOL, VILLA DEL SOL».
    cliente = d["cliente"]
    direccion = cliente.get("direccion", "")
    if cliente.get("barrio") and not direccion_ya_trae_el_barrio(direccion, cliente["barrio"]):
        direccion = f"{direccion}, {cliente['barrio']}"
    fecha, hora = _fecha_bogota(contrato.firmado_en)
    aut = d.get("autorizaciones") or {}
    aceptadas = ""
    if aut.get("aceptadas_en"):
        from datetime import datetime
        aceptadas = _fecha_bogota(datetime.fromisoformat(aut["aceptadas_en"]))[0]

    #  DOS COORDENADAS, DOS LUGARES DEL PAPEL (25/11/2026). Las de la
    #  INSTALACION (`gps`: las del ticket) van con los datos del suscriptor.
    #  DONDE SE FIRMO (`gps_del_telefono`) va en el pie, que es el que dice
    #  «firmado en…»: poner ahi las del ticket seria afirmar que se firmo en
    #  un punto donde quiza nadie estuvo.
    def _punto(g) -> str:
        g = g or {}
        if g.get("lat") is None or g.get("lng") is None:
            return ""
        return f"{g['lat']}, {g['lng']}" + (f" (±{g['precision_m']} m)"
                                            if g.get("precision_m") else "")

    contexto = {
        "empresa": contrato.org.name, "nit": config.get("nit", ""),
        "logo": _logo_de(contrato.org),
        "numero": contrato.numero, "orden": d.get("orden_numero"),
        "fecha": fecha, "hora": hora,
        "c": cliente, "direccion": direccion,
        "plan": d["plan"], "servidor": d["servidor"],
        "tecnico": d.get("tecnico", ""),
        "autorizaciones": aut, "aceptadas_en": aceptadas,
        "al_firmar": aut.get("donde") == "al_firmar",
        "otro_titular": bool(d.get("otro_titular")),
        "condiciones": config.get("texto_condiciones", ""),
        "coordenadas": _punto(d.get("gps")),
        "gps": _punto(d.get("gps_del_telefono")),
        #  Sin firma (el cliente firma el contrato del proveedor): el papel
        #  lo dice en vez de mostrar un recuadro vacio.
        "firma": _data_uri(firma, "image/png") if firma else "",
        "huella": contrato.huella,
    }
    html = render_to_string("campo/contrato.html", contexto)
    salida = BytesIO()
    HTML(string=html).write_pdf(salida, font_config=FontConfiguration())
    return ContentFile(salida.getvalue())
