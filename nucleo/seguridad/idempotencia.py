# -*- coding: utf-8 -*-
"""
================================================================================
 IDEMPOTENCIA DE OPERACIONES EXTERNAS  --  que una mutacion salga UNA vez
================================================================================

EL PROBLEMA
-----------
El motor escribe en sistemas de terceros: reinicia una ONT en SmartOLT, activa
CATV, cambia el tipo de ONU, crea un ticket o registra un pago en WispHub.
Ninguna de esas llamadas es idempotente del lado del proveedor: mandarla dos
veces reinicia dos veces, cobra dos veces, crea dos tickets.

Y hay mas de una forma de mandarla dos veces sin quererlo -- un reintento, un
timeout, una conexion cortada, dos procesos, el scheduler, un reenvio de la
misma peticion. Hasta ahora nada lo impedia y, peor, nada dejaba rastro de que
hubiera pasado.

COMO SE RESUELVE
----------------
Una fila por operacion logica en 'asistente.operaciones_externas', con la clave
primaria (organizacion, clave) haciendo de exclusion: el que consigue insertar
la fila es el que ejecuta, y es uno solo. No hay lock en memoria -- eso no
sobrevive a dos procesos ni a un reinicio, que son justo los casos.

    reclamar  ->  (transaccion corta, COMMIT)
    ejecutar  ->  (la llamada externa, fuera de toda transaccion)
    anotar    ->  (transaccion corta con el resultado)

Las tres fases estan separadas a proposito. Sostener la transaccion durante una
llamada HTTP de hasta 15 s dejaria a cualquier otro proceso esperando en el
indice unico todo ese rato.

DE DONDE SALE LA CLAVE  --  lo mas delicado de todo esto
--------------------------------------------------------
La clave tiene que valer lo mismo para dos ENTREGAS de la misma solicitud, y
distinto para dos solicitudes distintas. Si se equivoca para un lado, no
protege nada; si se equivoca para el otro, bloquea un pedido legitimo.

Por eso NO se deriva solo de (herramienta + argumentos): un cliente puede pedir
legitimamente dos reinicios en la misma conversacion con una hora de por medio,
y colapsarlos en una sola clave cambiaria el comportamiento de una accion de
red -- que es exactamente lo que esta fase no debe hacer.

La clave lleva un tercer componente, 'origen', que lo aporta quien llama y que
identifica la SOLICITUD, no la herramienta:

    conversacion   el identificador del evento entrante (el wamid de WhatsApp,
                   por ejemplo). Es estable si Meta reentrega el mismo mensaje,
                   y distinto en el mensaje siguiente.
    scheduler      el 'run_id' del intento del trabajo.
    otro servicio  la cabecera 'Idempotency-Key' que mande, si manda una.

Y de ahi sale el limite honesto de todo el mecanismo: LA GARANTIA VALE LO QUE
VALGA EL ORIGEN. Cuando quien llama no tiene un identificador estable, pasa uno
propio de ese turno y entonces esto protege contra un reintento dentro del
turno, no contra una reentrega del turno completo. Donde eso pasa esta dicho en
el sitio, no escondido aca.

LO QUE ESTO NO PUEDE PROMETER
-----------------------------
Si la llamada sale y la respuesta se pierde, nadie sabe si el tercero la
aplico. Lo que se garantiza es que el reintento es UNO, con dueño, contado y
anotado, en vez de N sin registro. Decir mas seria mentir.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from nucleo.persistencia import db as persistencia
from nucleo.seguridad.interruptor import tabla_ausente

# Cuanto puede estar una operacion en 'ejecutando' antes de que otra pasada
# tenga derecho a rescatarla.
#
# El numero no es arbitrario: el ejecutor HTTP corta a los 15 s
# (nucleo/herramientas/http.py::TIMEOUT_SEGUNDOS) y el asincrono sondea la
# tarea del proveedor, asi que una operacion viva no deberia pasar de un par de
# minutos. Se eligio holgado a proposito -- rescatar temprano es repetir una
# mutacion que quizas seguia en curso, y ese es el error caro.
SEGUNDOS_VENCIDA = 300

# Codigos que ve el modelo cuando la operacion NO se ejecuta. Son bloqueos del
# codigo, no fallos de un tercero: van a motor.CODIGOS_DE_BLOQUEO.
EN_CURSO = "OPERACION_EN_CURSO"
CLAVE_REUTILIZADA = "CLAVE_REUTILIZADA"
FALLIDA_PREVIA = "OPERACION_FALLIDA_PREVIA"
SIN_REGISTRO = "OPERACION_SIN_REGISTRO"
# La tabla del registro no existe: falta la migracion. Bloquea, igual que
# SIN_REGISTRO -- se separa porque se arregla distinto (aplicar la migracion,
# no investigar la base). Ver el bloque de abajo sobre el paso 10.10.
CONTROL_AUSENTE = "REGISTRO_NO_INSTALADO"
# El registro contesto algo que este modulo no sabe interpretar. Bloquea, por
# el mismo motivo que los de arriba: una respuesta que no se entiende no es una
# autorizacion. Ver la nota en 'ejecutar()' sobre por que hasta el 19/09/2026
# este caso EJECUTABA.
DECISION_DESCONOCIDA = "DECISION_DE_RECLAMO_DESCONOCIDA"


@dataclass
class Resultado:
    """Que paso con la operacion."""
    # True = la llamada externa SALIO en esta pasada.
    ejecutada: bool
    # ejecutar | repetida | en_curso | rechazada | fallida | sin_control
    # | desconocida  (19/09/2026: el registro contesto algo no interpretable)
    decision: str
    clave: str
    respuesta: Any = None
    motivo: str = ""
    # El codigo de bloqueo, cuando la operacion no se hizo ni se pudo repetir.
    codigo: str | None = None
    detalles: dict = field(default_factory=dict)

    @property
    def hubo_respuesta(self) -> bool:
        """Si hay algo que devolverle a quien pidio la operacion."""
        return self.ejecutada or self.decision == "repetida"


def hash_de(argumentos: Any) -> str:
    """
    SHA-256 del JSON canonico de los argumentos: claves ordenadas, sin
    espacios.

    Es el MISMO algoritmo que ya usa campo/services/idempotencia.py
    ('calcular_hash_canonico'). Se repite en vez de importarse porque aquel
    vive en Django y este en el motor, y el motor no importa Django -- pero el
    algoritmo es deliberadamente identico para que dos partes del sistema no
    discrepen sobre si dos pedidos son "el mismo".
    """
    if argumentos is None or argumentos == "" or argumentos == {}:
        canonico = "{}"
    elif isinstance(argumentos, (dict, list)):
        canonico = json.dumps(argumentos, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, default=str)
    else:
        canonico = str(argumentos)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def clave_de(origen: str, herramienta: str, argumentos: Any) -> str:
    """
    La identidad de la operacion logica. Ver el encabezado sobre 'origen'.

    Lleva los argumentos ademas del origen porque un mismo turno puede pedir
    dos acciones distintas -- reiniciar el equipo de un cliente y crear su
    ticket-- y esas son dos operaciones, no una.
    """
    if not (origen or "").strip():
        raise ValueError("una operacion externa sin origen no se puede "
                         "identificar: ver el encabezado de este modulo")
    return f"{origen.strip()}|{herramienta}|{hash_de(argumentos)[:16]}"


def ejecutar(tenant: str, herramienta: str, argumentos: Any, origen: str,
             hacer: Callable[[], Any], *, clave: str | None = None,
             reintentar_fallida: bool = False,
             segundos_vencida: int = SEGUNDOS_VENCIDA) -> Resultado:
    """
    Ejecuta 'hacer' a lo sumo una vez para esta operacion logica.

    'hacer' es la llamada externa ya armada -- este modulo no sabe ni tiene por
    que saber a que API le pega.

    Si la operacion ya se ejecuto con exito, NO se vuelve a llamar: se devuelve
    lo que contesto el tercero la primera vez. Si esta en curso, si la clave se
    reuso con otros argumentos, o si fallo antes sin autorizacion de reintento,
    tampoco se llama, y el Resultado trae el codigo de bloqueo.

    QUE PASA SI FALLA LA LLAMADA EXTERNA
    ------------------------------------
    La operacion queda 'fallida' con su error, y la excepcion SE VUELVE A
    LEVANTAR tal cual. Es deliberado: quien llama ya sabe manejarla (en el
    motor termina en 'codigo_error' y el modelo avisa que hubo un problema), y
    convertirla aca en un valor de retorno cambiaria el comportamiento de todas
    las herramientas de escritura, que es justo lo que esta fase no debe hacer.

    QUE PASA SI NO SE PUEDE RECLAMAR
    --------------------------------
    Si la base no responde, NO se ejecuta: sin registro no hay garantia de una
    sola vez, y ejecutar igual seria tener el mecanismo apagado justo el dia
    que hace falta. **Sin excepciones**, y eso incluye que la tabla todavia no
    exista: hasta el 17/09/2026 ese caso se ejecutaba "sin control", y era la
    misma inversion que corrigio el interruptor -- "el control no esta
    instalado" no puede significar "adelante". Si falta la migracion, la
    operacion se rechaza con 'REGISTRO_NO_INSTALADO' y se aplica la migracion.
    """
    #  LA AUTORIZACION VA PRIMERO  --  paso 10.14A
    #  ------------------------------------------
    #  Este modulo garantiza "una sola vez", no "esta permitido". Son cosas
    #  distintas y hasta el 17/09/2026 se podian usar por separado: cualquier
    #  modulo podia llamar a ejecutar() y la mutacion salia sin que nadie
    #  hubiera consultado el interruptor. Que sus tres llamadores estuvieran
    #  todos en motor.py era una propiedad del codigo de hoy, no una garantia.
    #
    #  Ahora exige que haya un permiso vigente en el contexto. No hay un
    #  parametro 'autorizado=True': el permiso lo construye unicamente
    #  nucleo/seguridad/frontera.py, al entrar por autonoma() o por humana().
    from nucleo.seguridad import frontera

    permiso = frontera.permiso_vigente()
    if permiso is None:
        registrar("idempotencia", "llego sin permiso de la frontera: NO se ejecuta",
                  tenant=tenant, herramienta=herramienta)
        return Resultado(ejecutada=False, decision="sin_autorizar", clave="",
                         codigo=frontera.SIN_AUTORIZAR,
                         motivo="la operacion no paso por la frontera de "
                                "acciones externas")

    clave = clave or clave_de(origen, herramienta, argumentos)
    huella = hash_de(argumentos)

    try:
        reclamo = persistencia.reclamar_operacion_externa(
            tenant, clave, herramienta, huella, origen, segundos_vencida,
            reintentar_fallida=reintentar_fallida)
    except BaseException as e:                                   # noqa: BLE001
        if tabla_ausente(e):
            # NO se llama a hacer(). Corregido el 17/09/2026 (paso 10.10): antes
            # se ejecutaba "sin control de repeticion", que es tener el mecanismo
            # apagado justo cuando no se puede saber si la operacion ya salio.
            # Medido: con la tabla ausente llegaba a hacer 1 llamada externa real.
            # Falta supabase/202609151715_operaciones_externas.sql: sin
            # registro no hay garantia de una sola vez.
            registrar("idempotencia", "registro no instalado: NO se ejecuta",
                      tenant=tenant, herramienta=herramienta)
            return Resultado(ejecutada=False, decision="control_ausente",
                             clave=clave, codigo=CONTROL_AUSENTE,
                             motivo="el registro de operaciones no esta instalado")
        registrar("idempotencia", "no se pudo reclamar la operacion: NO se ejecuta",
                  tenant=tenant, herramienta=herramienta, error=e)
        return Resultado(ejecutada=False, decision="sin_registro", clave=clave,
                         codigo=SIN_REGISTRO,
                         motivo=f"no se pudo registrar la operacion: {type(e).__name__}")

    decision = reclamo["decision"]
    fila = reclamo.get("fila") or {}

    if decision == "repetida":
        #  Las compuertas pasaron pero el EFECTO NO OCURRIO. Se anota igual,
        #  con la misma clave: asi la bitacora no miente por omision y el
        #  segundo intento queda visible sin parecer una segunda ejecucion.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.NO_EJECUTADA,
                                  codigo="repetida", motivo="ya se habia ejecutado con exito: no se repite el efecto")
        return Resultado(ejecutada=False, decision="repetida", clave=clave,
                         respuesta=fila.get("respuesta"),
                         motivo="esta operacion ya se habia ejecutado con exito",
                         detalles={"intentos": fila.get("intentos")})

    if decision == "en_curso":
        #  Las compuertas pasaron pero el EFECTO NO OCURRIO. Se anota igual,
        #  con la misma clave: asi la bitacora no miente por omision y el
        #  segundo intento queda visible sin parecer una segunda ejecucion.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.NO_EJECUTADA,
                                  codigo="en_curso", motivo="otro proceso la tiene reclamada")
        return Resultado(ejecutada=False, decision="en_curso", clave=clave,
                         codigo=EN_CURSO,
                         motivo="otro proceso esta ejecutando esta misma operacion")

    if decision == "rechazada":
        #  Las compuertas pasaron pero el EFECTO NO OCURRIO. Se anota igual,
        #  con la misma clave: asi la bitacora no miente por omision y el
        #  segundo intento queda visible sin parecer una segunda ejecucion.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.NO_EJECUTADA,
                                  codigo="rechazada", motivo="la misma clave con otros argumentos")
        return Resultado(ejecutada=False, decision="rechazada", clave=clave,
                         codigo=CLAVE_REUTILIZADA,
                         motivo=reclamo.get("motivo") or
                                "la misma clave ya se uso con otros argumentos")

    if decision == "fallida":
        #  Las compuertas pasaron pero el EFECTO NO OCURRIO. Se anota igual,
        #  con la misma clave: asi la bitacora no miente por omision y el
        #  segundo intento queda visible sin parecer una segunda ejecucion.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.NO_EJECUTADA,
                                  codigo="fallida_previa", motivo="fallo antes y el reintento no esta autorizado")
        return Resultado(ejecutada=False, decision="fallida", clave=clave,
                         codigo=FALLIDA_PREVIA,
                         motivo=(fila.get("error") or "fallo en un intento anterior"),
                         detalles={"intentos": fila.get("intentos")})

    #  DECISION DESCONOCIDA: NO SE EJECUTA  --  corregido el 19/09/2026
    #  -------------------------------------------------------------
    #  Hasta hoy este punto se alcanzaba con un comentario que DECIA
    #  'decision == "ejecutar"' y un codigo que no lo comprobaba: cualquier
    #  valor que no fuera uno de los cuatro de arriba caia aca y la mutacion
    #  SALIA. No era alcanzable --el unico productor, db.py::
    #  reclamar_operacion_externa, devuelve exactamente cinco valores-- pero la
    #  garantia la daba el productor, no este modulo.
    #
    #  Se vio de verdad: una prueba escrita con nombres de decision inventados
    #  quedo en VERDE ejecutando la llamada externa igual. O sea que el dia que
    #  se agregue una decision nueva y se olvide su rama, el sintoma seria una
    #  escritura que sale sin que nadie la haya autorizado, y ninguna prueba
    #  existente lo veria.
    #
    #  Ahora se exige el valor. Es la misma inversion que ya se aplico al
    #  interruptor y a la tabla ausente: "no se entiende la respuesta" no puede
    #  significar "adelante".
    #
    #  NO se toca el registro. El reclamo pudo haber dejado la fila en
    #  'ejecutando' o no haberla tocado -- no se sabe, porque no se entiende su
    #  respuesta. Marcarla 'fallida' seria afirmar que la operacion se intento,
    #  y no se intento. Si quedo reclamada, vence sola por SEGUNDOS_VENCIDA y
    #  otro proceso la rescata; eso es un estado controlado, inventar una
    #  transicion no lo seria.
    if decision != "ejecutar":
        # Una respuesta que no se entiende no es una autorizacion.
        registrar("idempotencia", "decision desconocida del registro: NO se ejecuta",
                  tenant=tenant, herramienta=herramienta, decision=str(decision)[:40])
        #  Las compuertas pasaron pero el EFECTO NO OCURRIO. Se anota igual,
        #  con la misma clave: asi la bitacora no miente por omision y el
        #  segundo intento queda visible sin parecer una segunda ejecucion.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.NO_EJECUTADA,
                                  codigo="desconocida", motivo="el registro contesto algo no interpretable")
        return Resultado(ejecutada=False, decision="desconocida", clave=clave,
                         codigo=DECISION_DESCONOCIDA,
                         motivo=f"el registro de operaciones contesto "
                                f"'{decision}', que no es una decision conocida",
                         detalles={"decision_recibida": decision})

    # decision == "ejecutar": la operacion es nuestra.
    try:
        respuesta = hacer()
    except BaseException as e:                                   # noqa: BLE001
        persistencia.finalizar_operacion_externa(
            tenant, clave, "fallida", error=f"{type(e).__name__}: {e}")
        #  EL EFECTO SE INTENTO Y VOLVIO CON ERROR: eso SI es fallida, y es la
        #  unica diferencia que separa "no salio" de "salio y salio mal". El
        #  error no se copia -- ya quedo en operaciones_externas, y la clave
        #  alcanza para llegar hasta el.
        frontera.anotar_desenlace(tenant, herramienta, clave,
                                  frontera.FALLIDA, codigo="fallida",
                                  motivo=type(e).__name__)
        raise
    persistencia.finalizar_operacion_externa(tenant, clave, "exitosa",
                                             respuesta=respuesta)
    frontera.anotar_desenlace(tenant, herramienta, clave, frontera.EXITOSA,
                              codigo="exitosa")
    return Resultado(ejecutada=True, decision="ejecutar", clave=clave,
                     respuesta=respuesta,
                     detalles={"intentos": fila.get("intentos"),
                               "rescatada": bool(reclamo.get("rescatada")),
                               "reintento": bool(reclamo.get("reintento"))})
