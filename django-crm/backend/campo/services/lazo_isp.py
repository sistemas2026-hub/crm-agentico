# -*- coding: utf-8 -*-
"""
El serial del equipo instalado vuelve al sistema del ISP.

QUE PROBLEMA CIERRA, con su medicion
------------------------------------
`sn_onu` esta VACIO en 1.299 de los 4.163 clientes activos de Rapilink (medido el
14/08/2026, paginacion verificada: 4.163 filas, 4.163 ids distintos). Y es la
llave contra SmartOLT: **uno de cada tres clientes no se puede diagnosticar por
ahi**. El unico que sabe que aparato quedo en esa casa es el tecnico que lo
instalo, y hasta ahora ese dato moria en el inventario de Dexter sin llegar nunca
al ISP.

LA FRONTERA: QUIEN ES DUEÑO DE QUE
----------------------------------
    Dexter   material -> custodia -> tecnico -> salida de custodia
    WispHub  cliente  -> servicio -> equipo instalado CONFIRMADO

Dexter no lleva un segundo registro de lo instalado. Lo que hace es **avisarle al
dueño**: el serial sale de la custodia y el ISP se entera. Por eso este modulo no
guarda ningun estado de "instalado en el cliente X": eso lo sabe WispHub.

`ACCION_CONFIRMADA` NO ES `EFECTO EN EL CLIENTE`
-----------------------------------------------
El proyecto ya tiene el patron y el nombre: *el equipo hizo lo pedido != el
cliente tiene internet*. Aplicado aca:

    la serie salio de la custodia del tecnico  !=  el ISP la tiene registrada

Son dos hechos, y el segundo puede fallar sin que el primero deje de ser cierto.
Por eso un fallo al avisarle al ISP **nunca** revierte el movimiento de
inventario: el consumo ocurrio en la calle y el registro tiene que quedar.

EL CRM NO HABLA CON WISPHUB
---------------------------
No tiene la credencial y no debe tenerla. Le pide al motor por
`POST /interno/herramienta/actualizar_sn_onu`, que es el mismo camino que ya usa
`solicitudes/entrega.py` para crear el ticket de una contratacion. Tres capas del
lado del motor, y ninguna sobra: token de servicio, `invocable_por_servicio`
declarado herramienta por herramienta, y sin sesion.

POR QUE ES REINTENTABLE, a diferencia de los otros efectos externos
------------------------------------------------------------------
Escribir un campo no crea nada: dos veces el mismo serial deja el mismo estado
que una. `crear_ticket` no se reintenta porque crearia un segundo ticket (gate
Q2, cerrado en rojo) y `crear_caso` lo logra artificialmente metiendo el
conversation_id en el nombre. Esta es idempotente **por naturaleza**, asi que no
necesita la cola del reconciliador -- que ademas no la admitiria: su
`conversation_id` es NOT NULL con FK a conversaciones, y una instalacion de campo
no tiene conversacion.

Se manda igual una `Idempotency-Key` estable derivada del movimiento, para que un
reenvio se reconozca como tal en `asistente.operaciones_externas`.

EL RIESGO DEL PUT: MEDIDO EL 28/09/2026, Y NO SE MATERIALIZO
-----------------------------------------------------------
Este modulo nacio apagado por una sola pregunta: un `PUT` normalmente espera el
recurso COMPLETO, asi que mandar solo `sn_onu` podria vaciar los demas campos del
cliente. Se midio con un PUT real contra el cliente de prueba 6555:

    PUT {"sn_onu": "CANARIO-SN-1"}    -> 200, y al leer QUEDO ESCRITO
    PUT {"comentarios": "canario-2"}  -> 200, y sn_onu SOBREVIVIO intacto

**El PUT de este endpoint es PARCIAL.** Escribe lo que se manda y no toca el
resto. Mandar solo `sn_onu` es seguro.

DOS TRAMPAS QUE APARECIERON AL MEDIRLO
--------------------------------------
Las dos estan en la skill wisphub-api con su evidencia, y una afecta a este
modulo:

  1. UN 200 DE ESTA API NO PRUEBA QUE SE ESCRIBIO. Un PUT con campos que la API
     no acepta devuelve 200 y no aplica nada -- se vio con `nombre`, `direccion` y
     `telefono` a la vez. Por eso `intentar_avisar()` devuelve AVISADO cuando el
     motor responde 2xx, y eso significa "el pedido salio", no "el ISP lo
     aplico". Son dos hechos, como siempre en este proyecto. Comprobar el
     segundo exigiria leer el cliente despues, y eso es otra pieza: hoy no se
     hace y queda dicho.

  2. `sn_onu` NO SE PUEDE VACIAR: `""` y `" "` devuelven 200 sin efecto, y `null`
     da 400. Solo se puede SOBRESCRIBIR con otro valor. Este modulo no lo
     necesita --solo escribe al instalar-- pero una funcion futura de
     "desinstalar" que espere limpiar el campo va a fallar en silencio.

QUE FALTA PARA ENCENDERLO
-------------------------
Solo poner `CAMPO_AVISAR_SN_ONU_AL_ISP=1` en el entorno del despliegue. La
variable no vive en el repo: es una decision de operacion, igual que
`RECONCILIADOR_HABILITADO`. Mientras no este, `intentar_avisar()` devuelve
`APAGADO` con su motivo y no sale a la red.
"""

from __future__ import annotations

import hashlib
import logging
import os

from campo.models import MovimientoDeMaterial

logger = logging.getLogger(__name__)

#: Vale `"1"` o no se avisa. Interruptor propio y no el de otra cosa: encender
#: esto no enciende ningun otro efecto externo.
BANDERA = "CAMPO_AVISAR_SN_ONU_AL_ISP"

#: La herramienta del catalogo del tenant. El nombre es configuracion: otro ISP
#: puede llamarla distinto, y el dia que haya dos no se toca este archivo.
VARIABLE_HERRAMIENTA = "CAMPO_HERRAMIENTA_SN_ONU"
HERRAMIENTA_POR_DEFECTO = "actualizar_sn_onu"


class ResultadoAviso:
    """Que paso al intentar avisarle al ISP.

    Es una clase y no un booleano porque hay TRES desenlaces y el proyecto
    distingue los tres: se aviso, no se pudo medir, y no correspondia. Un
    booleano los aplastaria en dos y perderia justo el que importa -- "no se
    pudo" no es "no hacia falta".
    """

    AVISADO = "avisado"
    APAGADO = "apagado"
    NO_CORRESPONDE = "no_corresponde"
    FALLO = "fallo"

    def __init__(self, estado: str, detalle: str = ""):
        self.estado = estado
        self.detalle = detalle

    def __repr__(self) -> str:
        return f"ResultadoAviso({self.estado}: {self.detalle})"

    @property
    def salio(self) -> bool:
        return self.estado == self.AVISADO


def _habilitado() -> bool:
    return os.environ.get(BANDERA, "0").strip() == "1"


def clave_idempotente(movimiento) -> str:
    """Derivada del MOVIMIENTO, que es durable.

    Un uuid nuevo por intento es un identificador unico, no una clave
    idempotente -- invariante congelado del proyecto. Con esta, un reenvio del
    mismo consumo se reconoce en `asistente.operaciones_externas` en vez de
    volver a salir a la red.
    """
    crudo = f"sn_onu:{movimiento.org_id}:{movimiento.id}"
    return "campo-sn-onu-" + hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:40]


def _id_servicio_de(orden) -> str:
    """El id del cliente en el ISP, tal como lo congelo el despacho.

    Sale del snapshot de la orden y NO se va a buscar en vivo: la orden guarda a
    que cliente del ISP corresponde, y preguntarselo de nuevo al motor abriria la
    posibilidad de escribirle a otro cliente si algo cambio en el medio.
    """
    if orden is None:
        return ""
    directo = (getattr(orden, "cliente_id_abonado", "") or "").strip()
    if directo:
        return directo
    contexto = getattr(orden, "contexto", None) or {}
    return str(contexto.get("servicio") or "").strip()


def intentar_avisar(movimiento) -> ResultadoAviso:
    """Le dice al ISP que esta serie quedo instalada. NO revierte nada si falla.

    Devuelve un `ResultadoAviso` y nunca lanza: el consumo ya ocurrio en la
    calle, y un fallo al avisar no puede tumbar la transaccion que lo registro.
    Eso convertiria un problema de red en material perdido del inventario.
    """
    if not _habilitado():
        return ResultadoAviso(
            ResultadoAviso.APAGADO,
            f"{BANDERA} != '1'. El riesgo del PUT ya se midio y es seguro "
            f"(28/09/2026): solo falta poner la variable en el entorno del "
            f"despliegue. Ver el docstring de este modulo.")

    if movimiento.tipo != MovimientoDeMaterial.CONSUMO:
        return ResultadoAviso(
            ResultadoAviso.NO_CORRESPONDE,
            "solo un CONSUMO instala algo en una casa: una devolucion o un "
            "traslado no cambian que equipo tiene el cliente.")
    if movimiento.estado != MovimientoDeMaterial.ACEPTADO:
        # Un descuadre o un conflicto no se avisan: el primero esta sin explicar
        # y el segundo, por definicion, no ocurrio.
        return ResultadoAviso(
            ResultadoAviso.NO_CORRESPONDE,
            f"el movimiento esta en '{movimiento.estado}' y no en 'aceptado'.")

    serie = (movimiento.serie or "").strip()
    if not serie:
        return ResultadoAviso(ResultadoAviso.NO_CORRESPONDE,
                              "el consumo no lleva serie: no hay aparato que avisar.")

    id_servicio = _id_servicio_de(movimiento.orden)
    if not id_servicio:
        # Se NOMBRA en vez de adivinar. Sin el id del cliente en el ISP no hay a
        # quien escribirle, y elegir uno "parecido" seria escribirle al cliente
        # equivocado.
        return ResultadoAviso(
            ResultadoAviso.NO_CORRESPONDE,
            "la orden no dice a que cliente del ISP corresponde "
            "(cliente_id_abonado y contexto.servicio vacios).")

    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")

    # NINGUNA EMPRESA CONCRETA VIVE EN EL CODIGO.
    #
    # Esta linea decia `or "rapilink"`. Es un hardcode de cliente, y lo peligroso
    # no es el estilo: este parametro decide A QUE EMPRESA se le escribe en el
    # ISP. Si un dia se despliega una segunda instalacion y alguien olvida la
    # variable, el aviso de un tecnico de otra empresa sale con el tenant de
    # Rapilink y escribe sobre los clientes de Rapilink. Fail-closed: sin el dato
    # no se avisa, y se dice que falta.
    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        return ResultadoAviso(
            ResultadoAviso.NO_CORRESPONDE,
            "falta MOTOR_TENANT: sin saber de que empresa es este movimiento no "
            "se le puede escribir al ISP, y suponerlo escribiria sobre los "
            "clientes de otra.")
    herramienta = (os.environ.get(VARIABLE_HERRAMIENTA, "")
                   or HERRAMIENTA_POR_DEFECTO)

    cabeceras = {
        "Content-Type": "application/json",
        "Idempotency-Key": clave_idempotente(movimiento),
    }
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        r = requests.post(
            f"{base}/interno/herramienta/{herramienta}",
            params={"tenant": tenant},
            json={"id_servicio": id_servicio, "sn_onu": serie},
            headers=cabeceras, timeout=45)
    except Exception as e:  # noqa: BLE001
        # Tipo y no texto: el texto de una excepcion de red trae la URL, y la URL
        # trae el id del cliente. Misma regla que nucleo/observabilidad.
        logger.warning("sn_onu: no se pudo avisar al ISP (%s)", type(e).__name__)
        return ResultadoAviso(ResultadoAviso.FALLO, type(e).__name__)

    if r.status_code == 409:
        # El motor dice que la autonomia esta detenida. NO es un fallo: es una
        # decision del sistema, y quien lea esto tiene que poder distinguirla.
        logger.info("sn_onu: el motor no ejecuto (autonomia detenida)")
        return ResultadoAviso(ResultadoAviso.NO_CORRESPONDE,
                              "el motor tiene las acciones automaticas detenidas.")
    if r.status_code >= 400:
        logger.warning("sn_onu: el motor respondio %s", r.status_code)
        return ResultadoAviso(ResultadoAviso.FALLO, f"HTTP {r.status_code}")

    return ResultadoAviso(ResultadoAviso.AVISADO, f"HTTP {r.status_code}")
