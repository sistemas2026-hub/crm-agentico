# -*- coding: utf-8 -*-
"""
================================================================================
 Politica de promesa de pago con reactivacion  --  codigo, no criterio
================================================================================

Un cliente suspendido pide que le devuelvan el internet prometiendo pagar. El
proveedor lo concede a veces, y la decision tiene reglas: hace cuanto que
debe, cuanto debe, para cuando promete, si ya prometio antes.

ESTE MODULO NO DECIDE NADA POR SU CUENTA Y NO HABLA CON NADIE. Recibe HECHOS
--ya leidos-- y una POLITICA --del tenant-- y dice si la accion es elegible.
Separarlo asi es lo que permite probar las reglas sin red y sin base, y lo que
impide que la decision dependa de como se sintio el modelo ese dia.

    el modelo entiende el pedido   ->  este modulo evalua  ->  una persona aprueba

LOS TRES DESENLACES, Y POR QUE NO SON DOS
------------------------------------------
    ELEGIBLE          se comprobo todo y se cumple     -> se puede proponer
    NO_ELEGIBLE       se comprobo y NO se cumple       -> a revision humana
    NO_SE_PUDO        falta un dato para decidir       -> NO se propone

La tercera es la que se olvida. Si no se pudo leer el estado del cliente, la
respuesta honesta no es "entonces no" ni "entonces si": es que no se sabe. Con
un booleano habria que elegir un lado, y los dos estan mal -- la misma regla
que X17 en la revalidacion y que 'desconocida' en B4.

EL PUNTO CIEGO, QUE NO SE CIERRA CON CODIGO
-------------------------------------------
WispHub NO permite consultar promesas vigentes: '/api/promesa-pago/' declara
solo POST, el detalle de factura no las trae y el cliente tampoco (medido el
21/09/2026). Asi que 'ya tiene una promesa' SOLO se puede comprobar contra lo
que registro Dexter.

Una promesa que un agente cargo a mano en el panel es INVISIBLE para esto, y
ninguna guarda la va a ver nunca. Por eso esta politica no autoriza a ejecutar
sola: reduce el riesgo, no lo elimina, y la aprobacion humana sigue siendo la
que cubre ese hueco. Ver SPEC/auditorias/B4-Q2-WISPHUB.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

ELEGIBLE = "elegible"
NO_ELEGIBLE = "no_elegible"
NO_SE_PUDO = "no_se_pudo_comprobar"

#: DEUDA CONOCIDA, anotada y no tapada: las dos etiquetas de abajo son el
#: vocabulario del proveedor de facturacion, no de la plataforma. Un ISP con
#: otro sistema las tendria distintas, asi que por la regla multi-tenant
#: deberian ser configurables. Se dejan en codigo por ahora --con el mismo
#: criterio que 'ESTADOS_CERRADOS' en seguimiento/escalamiento.py, que ya vive
#: asi-- y porque moverlas a config sin un segundo tenant que lo exija es
#: adivinar la forma. El dia que entre un proveedor distinto, esto es lo
#: primero que hay que mover.
#:
#: Lo que el proveedor llama a un cliente cuyo servicio esta cortado.
SUSPENDIDO = "Suspendido"
#: Lo que llama a una factura sin pagar. Se compara por PREFIJO: la etiqueta
#: real es 'Pendiente de Pago' y atarse a la frase entera la rompe con
#: cualquier cambio de redaccion.
PREFIJO_PENDIENTE = "pendiente"


@dataclass
class Veredicto:
    resultado: str
    motivo: str = ""                      # codigo estable, para el registro
    detalle: str = ""                     # texto para quien lo lea
    datos: dict = field(default_factory=dict)

    @property
    def elegible(self) -> bool:
        return self.resultado == ELEGIBLE


def _a_fecha(valor) -> date | None:
    """Fecha desde lo que devuelva la API, o None si no se entiende.

    WispHub devuelve fechas en mas de un formato segun el recurso: las de
    factura vienen 'YYYY-MM-DD' y las de cliente 'DD/MM/YYYY' (medido). No se
    adivina: si no coincide con ninguno conocido, se devuelve None y quien
    llama lo trata como dato ausente -- que termina en NO_SE_PUDO, no en un
    'no' silencioso.
    """
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    texto = texto.split("T")[0].split(" ")[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _es_pendiente(factura: dict) -> bool:
    return str(factura.get("estado") or "").strip().lower().startswith(PREFIJO_PENDIENTE)


def evaluar(hechos: dict, politica, *, hoy: date | None = None) -> Veredicto:
    """
    ¿Se puede proponer 'registrar promesa y reactivar' para este cliente?

    'hechos' es lo que ya se leyo, y cada clave ausente o None significa "no se
    pudo leer", nunca "no aplica":

        cliente          dict con 'estado' (y lo demas que traiga)
        facturas         lista de facturas del cliente
        fecha_limite     la que pide el cliente
        promesa_previa   fecha de la ultima promesa que registro DEXTER para
                         este cliente, o None si no hay
                         (None = no hay; ausente = no se pudo consultar)

    El orden de las comprobaciones importa para el MOTIVO que sale, no para el
    resultado: se informa la primera razon por la que no procede, y es la que
    va a leer una persona. Por eso lo que no se pudo leer se mira antes que lo
    que no se cumple: "no pude ver el estado" es mas util que "no es elegible".
    """
    hoy = hoy or date.today()
    datos: dict = {}

    # ---- 1. ¿tenemos con que decidir? ---------------------------------------
    cliente = hechos.get("cliente")
    if not isinstance(cliente, dict) or not cliente:
        return Veredicto(NO_SE_PUDO, "sin_cliente",
                         "No se pudo leer el estado del cliente.")
    estado = str(cliente.get("estado") or "").strip()
    if not estado:
        return Veredicto(NO_SE_PUDO, "sin_estado",
                         "El cliente no trae estado.")
    datos["estado"] = estado

    facturas = hechos.get("facturas")
    if facturas is None:
        return Veredicto(NO_SE_PUDO, "sin_facturas",
                         "No se pudieron leer las facturas del cliente.")

    if "promesa_previa" not in hechos:
        # Ausente NO es lo mismo que None. None dice "consulte y no hay";
        # ausente dice "no pude consultar", y sin eso no se puede aplicar la
        # regla de espaciado.
        return Veredicto(NO_SE_PUDO, "sin_historial",
                         "No se pudo consultar el historial de promesas.")

    fecha_limite = _a_fecha(hechos.get("fecha_limite"))
    if fecha_limite is None:
        return Veredicto(NO_SE_PUDO, "sin_fecha_limite",
                         "No hay una fecha limite valida para la promesa.")
    datos["fecha_limite"] = fecha_limite.isoformat()

    # ---- 2. el servicio tiene que estar cortado -----------------------------
    # Reactivar a quien ya tiene servicio no significa nada, y ademas oculta el
    # caso real: alguien que pide una promesa ANTES de que lo corten quiere
    # registrar la promesa, no reactivar.
    if estado != SUSPENDIDO:
        return Veredicto(NO_ELEGIBLE, "no_esta_suspendido",
                         f"El servicio esta '{estado}': no hay nada que reactivar. "
                         f"Si lo que quiere es dejar la promesa registrada, esa "
                         f"es la otra accion.", datos)

    # ---- 3. exactamente UNA factura pendiente -------------------------------
    pendientes = [f for f in facturas if _es_pendiente(f)]
    datos["pendientes"] = len(pendientes)
    if not pendientes:
        return Veredicto(NO_ELEGIBLE, "sin_factura_pendiente",
                         "No tiene facturas pendientes: no hay que prometer nada.",
                         datos)
    if len(pendientes) > 1:
        # Dos o mas ya no es un descuido de un mes: es deuda acumulada, y esa
        # es una conversacion de cobranza, no un tramite.
        return Veredicto(NO_ELEGIBLE, "varias_pendientes",
                         f"Tiene {len(pendientes)} facturas pendientes. La deuda "
                         f"acumulada la decide una persona.", datos)

    factura = pendientes[0]
    datos["id_factura"] = factura.get("id_factura")

    # ---- 4. la factura tiene que estar vencida ------------------------------
    vence = _a_fecha(factura.get("fecha_vencimiento"))
    if vence is None:
        return Veredicto(NO_SE_PUDO, "sin_vencimiento",
                         "La factura no trae fecha de vencimiento legible.", datos)
    datos["fecha_vencimiento"] = vence.isoformat()
    if vence >= hoy:
        return Veredicto(NO_ELEGIBLE, "factura_no_vencida",
                         f"La factura vence el {vence.isoformat()} y todavia no "
                         f"llego. Reactivar ahora no corresponde.", datos)

    # ---- 5. el plazo que pide, contra el tope del tenant --------------------
    dias = (fecha_limite - hoy).days
    datos["dias_de_plazo"] = dias
    if dias < 0:
        return Veredicto(NO_ELEGIBLE, "fecha_limite_pasada",
                         "La fecha que pide ya paso.", datos)
    if dias > politica.dias_maximos_promesa:
        return Veredicto(NO_ELEGIBLE, "plazo_excedido",
                         f"Pide {dias} dias y el maximo es "
                         f"{politica.dias_maximos_promesa}.", datos)

    # ---- 6. el monto, contra el tope del tenant -----------------------------
    # 0 significa SIN TOPE, no "tope cero": un tope de cero dejaria la accion
    # muerta sin que nadie entienda por que.
    if politica.monto_maximo_promesa:
        try:
            monto = float(factura.get("total"))
        except (TypeError, ValueError):
            return Veredicto(NO_SE_PUDO, "sin_monto",
                             "La factura no trae un total legible.", datos)
        datos["monto"] = monto
        if monto > politica.monto_maximo_promesa:
            return Veredicto(NO_ELEGIBLE, "monto_excedido",
                             f"El monto {monto} supera el maximo "
                             f"{politica.monto_maximo_promesa}.", datos)

    # ---- 7. que no venga prometiendo seguido --------------------------------
    previa = _a_fecha(hechos.get("promesa_previa"))
    if previa is not None:
        desde = (hoy - previa).days
        datos["dias_desde_promesa_previa"] = desde
        if desde < politica.dias_entre_promesas:
            return Veredicto(NO_ELEGIBLE, "promesa_reciente",
                             f"Dexter ya le registro una promesa hace {desde} "
                             f"dias y el minimo entre promesas es "
                             f"{politica.dias_entre_promesas}.", datos)

    return Veredicto(ELEGIBLE, "", "", datos)


def resumen_de_aprobacion(datos: dict) -> str:
    """
    Lo que va a leer quien aprueba. Nombra los DOS efectos.

    No es cosmetico: el panel de aprobacion muestra unicamente el resumen, y
    fue exactamente asi como una reactivacion de servicio se aprobaba sin que
    nada la nombrara (B5, 21/09/2026).
    """
    factura = datos.get("id_factura", "?")
    hasta = datos.get("fecha_limite", "?")
    # Sin nombrar al proveedor: nucleo/ no conoce a ninguno, y ademas la
    # reversion automatica al vencer es conducta de ESE sistema de facturacion,
    # no de la plataforma. Se dice en voz pasiva --lo que le pasa al servicio--
    # y no como promesa sobre quien lo hace.
    return (f"Registrar promesa de pago de la factura {factura} hasta el {hasta} "
            f"Y REACTIVAR el servicio (hoy suspendido). Si no paga, el servicio "
            f"vuelve a suspenderse al vencer la promesa.")
