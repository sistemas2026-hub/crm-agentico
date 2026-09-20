# -*- coding: utf-8 -*-
"""
================================================================================
 T20 -- el reconciliador de efectos externos  (B4, contrato del relevo §3.6)
================================================================================

Escalar produce dos cosas afuera: un caso en el CRM y, cuando corresponde, un
ticket en el sistema del ISP. Antes de B4, si alguna fallaba, el `except` la
mandaba al log y la intencion se perdia: la conversacion quedaba escalada,
visible en la bandeja, y sin caso -- y nadie se enteraba hasta que alguien lo
buscaba a mano.

Ahora la intencion queda encolada en `sincronizaciones_externas` en la misma
transaccion que la transicion, y esto la retoma.

LAS DOS VELOCIDADES
-------------------
No es una cola homogenea, y esa es la decision que la gobierna entera:

  crear_caso    se reintenta. El nombre del caso lleva el conversation_id y es
                unico por organizacion -- un repetido da 400, se busca y se
                adopta el que ya existe. La idempotencia esta del lado de
                afuera, asi que reintentar es seguro.

  crear_ticket  NO se reintenta cuando el resultado quedo incierto. Medido en
                el gate Q2 (SPEC/auditorias/B4-Q2-WISPHUB.md): la API de
                WispHub no acepta clave de idempotencia, no hay filtro para
                buscar el ticket despues, reescribe el asunto y recorta el
                historico sin rango de fecha. No hay forma de preguntar "¿esto
                ya se hizo?". Un incierto queda 'desconocida' y espera a una
                persona.

                Es preferible un ticket pendiente de revision a dos visitas
                tecnicas al mismo cliente.

POR QUE CADENCIA PROPIA
-----------------------
El reloj general del motor corre cada ~60 minutos, y los plazos de §14.1 Q4
son de 10 y 15. Bajar el reloj general para esto moveria TODAS las tareas
periodicas del motor: T20 corre aparte, cada 5 minutos, y solo mira trabajos
cuyo `proximo_intento_en` ya paso. Un ciclo sin trabajo elegible es una
consulta a un indice parcial y nada mas.

La activacion de esa cadencia en produccion es el gate G7 y no se toca desde
aca.
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar
from nucleo.persistencia import db

#: Cada cuanto corre. La activacion real en produccion es G7.
CADENCIA_SEGUNDOS = 300

#: Lo que NO se reintenta cuando el resultado quedo incierto. La razon no es el
#: tipo de efecto sino la API: sin forma de preguntar si ya se hizo, reintentar
#: es apostar. Ver el gate Q2.
SIN_REINTENTO_SI_INCIERTO = frozenset({"crear_ticket", "cerrar_ticket"})


class ResultadoEfecto:
    """
    Lo que un ejecutor le contesta al reconciliador.

    `clase` es lo unico que decide el siguiente paso, y las tres no se mezclan:

      exito        quedo hecho, con su referencia externa si la hay
      transitorio  no se llego a hacer y se puede volver a intentar
      permanente   no se va a poder: el pedido estaba mal y reintentarlo
                   igual daria el mismo error
      incierto     el pedido PUDO haber llegado. No se sabe.
    """

    def __init__(self, clase: str, *, referencia: str | None = None,
                 codigo: str | None = None):
        self.clase = clase
        self.referencia = referencia
        self.codigo = codigo


def _desenlace(tipo: str, resultado: ResultadoEfecto, intentos: int) -> tuple[str, str | None]:
    """
    Del resultado de un intento al estado durable. Devuelve (estado, clase).

    Aca vive la regla de Q2 y es el unico lugar donde se decide reintentar.
    """
    if resultado.clase == "exito":
        return "hecha", None
    if resultado.clase == "permanente":
        # No se va a arreglar solo. Que lo vea alguien.
        return "fallida_definitiva", "permanente"
    if resultado.clase == "incierto":
        # El pedido pudo haber llegado. Para lo que no se puede preguntar
        # "¿ya se hizo?", esto es terminal: queda para revision humana.
        if tipo in SIN_REINTENTO_SI_INCIERTO:
            return "desconocida", "incierto"
        # Para lo que SI es idempotente hacia afuera, un incierto se resuelve
        # preguntando: el proximo intento adopta lo que ya exista.
        return ("pendiente", "incierto") if intentos < db.MAX_INTENTOS_SINCRONIZACION \
            else ("desconocida", "incierto")
    # transitorio
    if intentos >= db.MAX_INTENTOS_SINCRONIZACION:
        return "fallida_definitiva", "transitorio"
    return "pendiente", "transitorio"


def procesar_una(tenant: str, trabajo: dict, ejecutar) -> str:
    """
    Un trabajo, de punta a punta. Devuelve el estado con el que quedo.

    `ejecutar(tipo, datos, referencia)` es lo que habla con el sistema externo
    y devuelve un ResultadoEfecto. Se inyecta para que esta funcion no conozca
    ni al CRM ni a WispHub: lo que decide aca es que hacer con el desenlace, no
    como se produce.
    """
    sid = str(trabajo["id"])
    tipo = trabajo["tipo"]

    # El candado: si otro reconciliador lo tomo primero, este no sale a la red.
    # Sin esto, dos procesos podrian crear dos casos para la misma conversacion.
    if not db.tomar_sincronizacion(tenant, sid):
        return "tomada_por_otro"

    try:
        resultado = ejecutar(tipo, trabajo.get("datos_intencion") or {},
                             trabajo.get("referencia_externa"))
    except Exception as e:
        # Una excepcion aca NO es "no salio": el pedido pudo haber viajado. Se
        # trata como incierto, que para crear_ticket significa terminal.
        registrar("reconciliador", "fallo al ejecutar un efecto externo",
                  tipo=tipo, error=e)
        resultado = ResultadoEfecto("incierto", codigo="excepcion_local")

    estado, clase = _desenlace(tipo, resultado, int(trabajo.get("intentos") or 0) + 1)
    db.resolver_sincronizacion(
        tenant, sid, estado=estado, referencia=resultado.referencia,
        error_clase=clase, error_codigo=resultado.codigo)

    if estado == "desconocida":
        # Se dice con todas las letras: no es un fallo, es algo que nadie puede
        # confirmar y que ya no se va a reintentar solo.
        registrar("reconciliador", "efecto externo con resultado desconocido: "
                                   "queda para revision humana",
                  tipo=tipo, codigo=resultado.codigo)
    return estado


#: Cuanto puede estar una accion en 'ejecutando' antes de darla por colgada
#: (§14.1 Q4). Es un default de PLATAFORMA, no configuracion por tenant: el
#: plazo no describe al ISP sino cuanto tarda en ser evidente que un proceso
#: murio a mitad de camino.
MINUTOS_EJECUTANDO_HUERFANA = 10


def barrer_acciones(tenant: str, limite: int = 50) -> dict:
    """
    T20 (c) y (d): lo que quedo a medias en las acciones aprobables (B5).

        ejecutando vieja   -> desconocida    el proceso murio entre la reserva
                                             y el desenlace. NO se reejecuta.
        pendiente vencida  -> vencida        paso su plazo y nadie la aprobo.

    NO TOCA NINGUN SISTEMA EXTERNO. Este barrido solo cierra estados que
    quedaron abiertos; el efecto de una 'desconocida' pudo haber ocurrido y
    nadie puede demostrar lo contrario, asi que reintentarlo es apostar (X21).
    Por eso la funcion no recibe 'ejecutar': no hay nada que ejecutar.
    """
    conteo: dict[str, int] = {}
    try:
        huerfanas = db.barrer_acciones_ejecutando(
            tenant, MINUTOS_EJECUTANDO_HUERFANA, limite)
        if huerfanas:
            # Sin ids ni conversaciones en el log: solo cuantas. Lo que hace
            # falta para saber que esta pasando, sin que el log sea un indice
            # de conversaciones.
            registrar("reconciliador", "acciones colgadas pasadas a desconocida",
                      tenant=tenant, cuantas=len(huerfanas))
            conteo["acciones_desconocidas"] = len(huerfanas)
    except Exception as e:
        registrar("reconciliador", "no se pudieron barrer las acciones colgadas",
                  tenant=tenant, error=e)

    try:
        vencidas = db.barrer_acciones_vencidas(tenant, limite)
        if vencidas:
            registrar("reconciliador", "acciones vencidas por plazo",
                      tenant=tenant, cuantas=len(vencidas))
            conteo["acciones_vencidas"] = len(vencidas)
    except Exception as e:
        registrar("reconciliador", "no se pudieron vencer las acciones del plazo",
                  tenant=tenant, error=e)
    return conteo


def correr(tenant: str, ejecutar, limite: int = 50) -> dict:
    """
    Un ciclo de la cola de efectos externos. Devuelve el conteo por desenlace.

    NO barre acciones: eso es barrer_acciones(), y el worker llama a las dos
    por separado. Estan separadas porque una necesita hablar con sistemas
    externos y la otra tiene prohibido hacerlo -- juntarlas obligaria a que el
    barrido dependiera de tener un ejecutor que no usa.

    No lanza: un tenant que falla no puede dejar sin reconciliar a los demas.
    """
    conteo: dict[str, int] = {}
    try:
        trabajos = db.sincronizaciones_elegibles(tenant, limite)
    except Exception as e:
        registrar("reconciliador", "no se pudo leer la cola de efectos externos", error=e)
        return conteo

    for trabajo in trabajos:
        try:
            estado = procesar_una(tenant, trabajo, ejecutar)
        except Exception as e:
            registrar("reconciliador", "fallo al procesar un efecto externo", error=e)
            estado = "error_local"
        conteo[estado] = conteo.get(estado, 0) + 1
    return conteo
