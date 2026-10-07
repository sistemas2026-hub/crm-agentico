# -*- coding: utf-8 -*-
"""
===============================================================================
 EL DIAGNOSTICO OPTICO DE UN CASO DESINCRONIZADO  --  escrito, no ejecutado
===============================================================================

QUE HACE
--------
Toma las señales de casos cerrados en el proveedor y abiertos en el CRM, le
pregunta a SmartOLT por el equipo de cada cliente, y deja el resultado ESCRITO
en la señal: como evidencia que una persona lee, y como datos que el codigo de
mas adelante puede usar.

NO CIERRA NADA. El cierre es otra fase, otro techo de autonomia y otra puerta.
Lo que esta fase produce es la razon por la cual un cierre seria seguro --o no
lo seria-- y la deja por escrito antes de que nadie decida.

LA REGLA, Y DE QUIEN ES
-----------------------
La definio el usuario el 07/10/2026, y se implementa en CODIGO porque es una
decision, no una redaccion:

    equipo caido por falta de energia  -> el cierre es seguro
    equipo en linea con señal buena    -> el cierre es seguro
    señal debil, o caida por fibra     -> NO: esto lo mira una persona
    cualquier otra cosa                -> NO: no se afirma nada

'sin_energia' es la casa del cliente; 'fibra' es un corte en la NAP, y eso es
nuestro. Son opuestas, y tratarlas igual seria cerrarle el caso a gente que
sigue sin servicio. Esa distincion es la unica razon por la que este modulo
existe: sin ella, "el ticket esta cerrado alla" alcanzaba para cerrar aca.

POR QUE NO VA DENTRO DEL DETECTOR
---------------------------------
'supervisor.detectar' corre DIECIOCHO detectores y promete no tener efectos.
Meter una llamada a un proveedor ahi adentro le habria costado, con los 19
casos medidos en produccion, unos 190 segundos --'get_onu_full_status_info'
tarda ~10 s, medido 9,9 s en la skill-- a una funcion que hoy tarda
milisegundos y que se dispara desde un boton con una persona esperando.

Esa es la misma forma del incidente del 06/10/2026, cuando encender el cerebro
dejo el ciclo colgado: llamadas sin tope dentro de una peticion sincrona.

EL PRESUPUESTO ES DOBLE, Y POR ESO MISMO
----------------------------------------
Un tope de CANTIDAD solo no alcanza: tres llamadas que tardan 30 s cada una
cuelgan el ciclo igual que treinta. Un tope de RELOJ solo tampoco: se gasta
entero en una llamada que no vuelve. Se reusa 'supervisor.presupuesto', que ya
tiene las dos cosas y ya esta probado, en vez de escribir un mecanismo nuevo
con la misma forma.

Lo que NO se diagnostico por falta de presupuesto queda dicho: "no se
diagnostico" con su motivo. Nunca se parece a "esta sano" -- es la misma regla
que el resto del Supervisor aplica con DESCONOCIDO, y la razon por la que el
ejecutor del motor devuelve 'desconocido' con 'motivo' en vez de levantar.
"""
from __future__ import annotations

from django.utils import timezone

from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

#  Cuantos equipos se diagnostican por corrida, y cuanto reloj se les presta.
#
#  TRES Y SESENTA, y los dos numeros salen de una medicion, no de un gusto: son
#  19 los casos desincronizados en produccion (07/10/2026) y cada diagnostico
#  paga ~10 s de 'get_onu_full_status_info' MAS la llamada que resuelve el
#  equipo. Tres por ciclo son ~60 s en el peor caso, que es lo que tolera un
#  boton; los 19 se cubren en siete ciclos, y un caso cerrado afuera no se
#  vuelve urgente por esperar un ciclo mas.
#
#  Subirlos es una decision de operacion con una medicion detras, no un ajuste:
#  el costo no es la cuota de SmartOLT --1.000/hora, holgadisimo-- sino el
#  tiempo que una persona espera mirando la pantalla.
TOPE_DIAGNOSTICOS_POR_CICLO = 3
SEGUNDOS_MAXIMOS_DE_DIAGNOSTICO = 60

#  Los veredictos de ESTA fase. No son el cierre: son la razon por la que un
#  cierre seria seguro, que es lo que se escribe.
CIERRE_SEGURO = "cierre_seguro"
REVISAR_PERSONA = "revisar_persona"
SIN_DIAGNOSTICO = "sin_diagnostico"

#  Los valores que devuelve el ejecutor del motor
#  ('nucleo/herramientas/diagnostico_servicio.py'). Se nombran aca para que un
#  cambio alla rompa una prueba en vez de volver silenciosamente todo
#  'sin_diagnostico' -- que es el modo de falla peligroso: parece prudencia.
EN_LINEA = "en_linea"
CAIDO = "caido"
SENAL_BUENA = "buena"
SENAL_DEBIL = "debil"
CAUSA_SIN_ENERGIA = "sin_energia"
CAUSA_FIBRA = "fibra"


def presupuesto(ahora=None) -> dict:
    """El presupuesto de esta fase. Mismo mecanismo que el del cerebro."""
    return sup.presupuesto(tope=TOPE_DIAGNOSTICOS_POR_CICLO,
                           segundos=SEGUNDOS_MAXIMOS_DE_DIAGNOSTICO,
                           ahora=ahora)


def clasificar(diagnostico: dict) -> tuple[str, str]:
    """
    (veredicto, porque) a partir de un diagnostico. EL CODIGO DECIDE, no el
    modelo.

    Devuelve siempre un porque redactado para que lo lea una persona: quien
    acepta la propuesta cambia el estado de un caso, y tiene que poder ver
    contra que. El texto no es decorativo -- es lo que queda escrito cuando
    alguien pregunte, semanas despues, por que se cerro.

    FAIL-CLOSED EN LA FORMA QUE IMPORTA: cualquier cosa que no sea una de las
    dos condiciones seguras cae en 'revisar_persona' o 'sin_diagnostico'.
    Nunca al reves. Un diagnostico que no se entiende no es un diagnostico
    bueno.
    """
    if not isinstance(diagnostico, dict) or diagnostico.get("error"):
        motivo = ""
        if isinstance(diagnostico, dict):
            motivo = str(diagnostico.get("detalle") or
                         diagnostico.get("error") or "")
        return SIN_DIAGNOSTICO, (
            "no se pudo diagnosticar el equipo"
            + (f": {motivo}" if motivo else "")
            + ". Eso no dice que este sano ni caido: dice que no hay dato.")

    estado = str(diagnostico.get("estado") or "")
    senal = str(diagnostico.get("senal") or "")
    causa = str(diagnostico.get("causa_caida") or "")
    dbm = diagnostico.get("senal_dbm")

    if estado not in (EN_LINEA, CAIDO):
        return SIN_DIAGNOSTICO, (
            f"el estado del equipo volvio como '{estado or 'vacio'}'"
            + (f" ({diagnostico.get('motivo')})" if diagnostico.get("motivo")
               else "")
            + ". Sin estado no se afirma nada.")

    #  CAIDO POR FALTA DE ENERGIA  --  la casa del cliente, no la red.
    if estado == CAIDO and causa == CAUSA_SIN_ENERGIA:
        return CIERRE_SEGURO, (
            "el equipo esta caido y el proveedor reporto falta de energia "
            "(dying-gasp): es un corte de luz en el domicilio, no una falla "
            "de la red. El ticket ya esta cerrado en el proveedor, asi que "
            "cerrarlo aca alinea el estado, no resuelve nada por nadie.")

    #  CAIDO POR FIBRA  --  esto es nuestro, y no se cierra.
    if estado == CAIDO and causa == CAUSA_FIBRA:
        return REVISAR_PERSONA, (
            "el equipo esta caido por perdida de señal optica (LOS/LOF): esa "
            "falla es de la red, no del cliente. No se propone cerrar aunque "
            "el proveedor ya lo haya cerrado.")

    if estado == CAIDO:
        return REVISAR_PERSONA, (
            f"el equipo esta caido y la causa que reporto el proveedor "
            f"({causa or 'ninguna'}) no es una de las dos que este codigo sabe "
            f"distinguir. No se decide por descarte.")

    #  EN LINEA  --  solo la señal buena habilita el cierre.
    #
    #  El dBm se nombra cuando esta, y se omite cuando no: "señal buena" sin el
    #  numero sigue siendo cierto, pero con el numero quien lee puede
    #  comprobarlo por su cuenta en vez de creerle a esta clasificacion. Es la
    #  misma razon por la que la evidencia de un caso nombra su fuente.
    nivel = f" ({dbm} dBm)" if dbm is not None else ""

    if senal == SENAL_BUENA:
        return CIERRE_SEGURO, (
            f"el equipo esta en linea y la señal de bajada es buena{nivel}, "
            f"dentro del rango que la guia considera sano. El ticket ya esta "
            f"cerrado en el proveedor y el equipo responde bien, asi que "
            f"cerrarlo aca alinea el estado.")

    if senal == SENAL_DEBIL:
        return REVISAR_PERSONA, (
            f"el equipo esta en linea pero la señal de bajada es debil"
            f"{nivel}. Puede volver a fallar, asi que lo mira una persona.")

    return SIN_DIAGNOSTICO, (
        "el equipo esta en linea pero no hubo lectura de señal, asi que no se "
        "puede decir si va a aguantar. No se propone cerrar sin ese dato.")


def enriquecer(org, senales, *, ahora=None, presupuesto_=None,
               diagnosticar=None) -> dict:
    """
    Le agrega el diagnostico optico a las señales de casos desincronizados.

    Muta las señales --'Senal' es mutable y su 'evidencia' y 'datos' son del
    llamador-- y devuelve CONTEOS para el informe del ciclo.

    'diagnosticar' SE INYECTA, igual que 'proponer' e 'interpretar' en el
    seguimiento: este modulo decide QUE significa un diagnostico, y no tiene
    por que saber que del otro lado hay un motor por HTTP. Tambien es lo que
    permite probar la clasificacion sin red.
    """
    ahora = ahora or timezone.now()
    p = presupuesto_ if presupuesto_ is not None else presupuesto(ahora=ahora)

    if diagnosticar is None:
        from operaciones import chat_herramientas

        def diagnosticar(org_, id_servicio):
            return chat_herramientas.diagnosticar_servicio(
                org_, id_servicio=id_servicio)

    informe = {"diagnosticados": 0, "cierre_seguro": 0, "revisar_persona": 0,
               "sin_diagnostico": 0, "sin_llave": 0, "sin_presupuesto": 0,
               "errores": 0}

    for senal in senales:
        if senal.tipo != PropuestaSupervisor.CASO_DESINCRONIZADO:
            continue

        id_servicio = str(senal.datos.get("id_servicio") or "").strip()
        if not id_servicio:
            informe["sin_llave"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    "el caso no tiene el id de servicio del proveedor, asi que "
                    "no se puede preguntar por el equipo. No se diagnostico.",
                    None, ahora)
            continue

        if not sup._hay_presupuesto(p):
            informe["sin_presupuesto"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    "no se diagnostico en esta corrida: se agoto el "
                    "presupuesto de diagnosticos del ciclo. Se intenta en el "
                    "siguiente; esto NO dice nada del estado del equipo.",
                    None, ahora)
            continue

        sup._gastar(p)
        try:
            diagnostico = diagnosticar(org, id_servicio)
        except Exception as e:                                   # noqa: BLE001
            #  El tipo y no el texto: el texto de una excepcion de red trae la
            #  URL, y la URL de SmartOLT lleva el identificador del equipo de
            #  un cliente. Misma regla que 'fuentes_adaptadores._pedirle_al_motor'.
            informe["errores"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    f"no se pudo preguntar por el equipo "
                    f"({type(e).__name__}). No se diagnostico.", None, ahora)
            continue

        informe["diagnosticados"] += 1
        veredicto, porque = clasificar(diagnostico)
        informe[veredicto] = informe.get(veredicto, 0) + 1
        _anotar(senal, veredicto, porque, diagnostico, ahora)

    return informe


def _anotar(senal, veredicto: str, porque: str, diagnostico, ahora) -> None:
    """
    Deja el veredicto en la señal: en la evidencia Y en los datos.

    EN LOS DOS LADOS A PROPOSITO, porque sirven a lectores distintos. La
    evidencia es lo que ve la persona que decide, en el mismo formato que las
    otras siete observaciones del caso. Los datos son lo que lee el codigo de
    la fase siguiente -- y leer un veredicto parseando el texto de una
    evidencia seria exactamente el error que este proyecto llama "el modelo
    compone, el codigo calcula".

    LO QUE NO SE ESCRIBE: el serial del equipo (el ejecutor del motor no lo
    devuelve) ni el nombre del cliente. Esto termina en una propuesta que
    queda guardada, y una propuesta no es lugar para datos de un abonado.
    """
    senal.evidencia.append(sup._observacion(
        "diagnostico", senal.origen_id, f"diagnostico del equipo: {porque}",
        ahora))

    senal.datos["diagnostico_veredicto"] = veredicto
    senal.datos["diagnostico_porque"] = porque
    if isinstance(diagnostico, dict):
        #  Las cinco claves que sostienen el veredicto, y solo esas. Guardar el
        #  diagnostico entero metería campos que nadie decidio guardar el dia
        #  que el ejecutor devuelva uno nuevo.
        senal.datos["diagnostico"] = {
            k: diagnostico.get(k) for k in
            ("estado", "causa_caida", "senal", "senal_dbm", "estado_config")
            if k in diagnostico
        }
