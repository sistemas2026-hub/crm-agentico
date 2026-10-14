# -*- coding: utf-8 -*-
"""
================================================================================
 CUAL DE LOS CINCO GRUPOS, Y SI PUEDE SEGUIR SOLO
================================================================================

QUE DECIDE Y QUE NO
-------------------
Decide si un ticket puede entrar a la cola de Despacho SIN que una persona
acepte la propuesta. No crea la orden de trabajo, no elige plantilla y no
asigna tecnico ni fecha: eso lo sigue haciendo quien despacha.

Ese limite es lo que hace reversible todo este modulo. Un caso mal pasado
ensucia una cola y se saca; una cuadrilla mal mandada son dos horas de alguien.

DE DONDE SALEN LAS CINCO REGLAS
-------------------------------
Las decidio el cliente el 14/10/2026, sobre la cola real de ese dia: 71 tickets
abiertos de 'soporte_tecnico' y 'operativo', en 41 asuntos distintos. Los
numeros de cada grupo son de esa medicion, no de una estimacion.

    falla de servicio    24    sin internet 20 · intermitente 3 · lento 1
    trabajo pedido       16    domicilio 5 · TDT 4 · punto TV 2 · retiro 2 ·
                               clave wifi 1 · camara 1 · reconexion 1
    obra de red          24    CTO/caja/splitter 16 · ampliaciones 6 ·
                               proyectos 2
    nada lo mide          2    paginas bloqueadas
    ni cliente ni red     5    cambio de aceite · entrega de guantes · 3 que
                               solo traen un nombre

EL REPARTO, Y ES LO QUE LO HACE AUDITABLE
-----------------------------------------
    el MODELO    dice en que grupo cae, leyendo la DESCRIPCION del reclamo
    el CODIGO    verifica la medicion del equipo y decide el paso

El modelo no juzga si -27 dBm es debil: eso lo calcula
'clasificacion_de_trabajo._de_la_prueba' contra el rango de la guia. Y el
modelo tampoco decide si pasa: devuelve un grupo de una lista cerrada, y la
tabla de abajo --que es codigo-- resuelve el resto. Es PRD §12.5: el modelo
compone, el codigo calcula.

POR QUE NO SE CLASIFICA POR EL TITULO
-------------------------------------
Medido el 14/10/2026: 41 asuntos distintos en 71 tickets, con typos del
catalogo del proveedor ('INSTATALACION NUEVA'), nombres de asesora, y cinco que
traen SOLO un nombre de persona. Y 'external_service_id' no separa nada: los
71 lo tienen, incluidas las obras de red, porque WispHub obliga a colgar el
ticket de algun cliente.

LO QUE ESTA DECISION REVIERTE, A PROPOSITO
------------------------------------------
'models.py', sobre TICKET_SIN_DIAGNOSTICO, dice: "una labor que salio del texto
queda fuera del reparto, porque mandar una cuadrilla a manejar hasta una casa
por lo que decia una frase es pedirle a alguien que confie en lo que nadie
verifico". Los grupos TRABAJO_PEDIDO y OBRA_DE_RED --40 de los 71-- pasan
exactamente asi.

El cliente lo decidio sabiendolo. Lo que lo hace tolerable son dos cosas, y las
dos son codigo: que pasar a la cola NO manda a nadie (el limite de arriba), y
que sin medicion se exige CONFIANZA ALTA del modelo, no cualquier lectura.
================================================================================
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#  LOS IMPORTS DE 'operaciones' VAN DENTRO DE LAS FUNCIONES, a proposito.
#  'clasificacion_de_trabajo' arrastra 'diagnostico_optico', que arrastra
#  'supervisor' -- y 'supervisor' es quien va a importar este modulo desde el
#  ciclo. Al tope, eso es un import circular; adentro, no. Es el patron que ya
#  usa el resto de este paquete por la misma razon.


# =============================================================================
#  LOS CINCO GRUPOS
# =============================================================================

FALLA_DE_SERVICIO = "falla_de_servicio"
TRABAJO_PEDIDO = "trabajo_pedido"
OBRA_DE_RED = "obra_de_red"
NADA_LO_MIDE = "nada_lo_mide"
NI_CLIENTE_NI_RED = "ni_cliente_ni_red"

GRUPOS = (FALLA_DE_SERVICIO, TRABAJO_PEDIDO, OBRA_DE_RED, NADA_LO_MIDE,
          NI_CLIENTE_NI_RED)

#:  Lo que se le pide al modelo, en el formato de 'cerebro.concluir'. La lista
#:  es CERRADA: un valor que no este aca se descarta en 'cerebro' y entonces es
#:  como si el modelo no hubiera dicho nada -- que es exactamente la lectura
#:  correcta de "no supo", y manda el caso a una persona.
CAMPO_PARA_EL_MODELO = {
    "grupo": {
        "valores": GRUPOS,
        "ayuda": (
            "en que grupo cae ESTE ticket, segun lo que PIDE el reclamo: "
            "'falla_de_servicio' si el cliente reporta que algo no funciona "
            "(sin internet, intermitente, lento); "
            "'trabajo_pedido' si pide un trabajo en su casa aunque todo "
            "funcione (cambio de domicilio, punto de TV, TDT, clave del wifi, "
            "retiro de equipos, reconexion); "
            "'obra_de_red' si el trabajo es sobre la planta y no sobre un "
            "abonado (una CTO, una caja, un splitter, una ampliacion de "
            "sector, un proyecto); "
            "'nada_lo_mide' si es un reclamo que ninguna herramienta de red "
            "puede comprobar, como paginas bloqueadas; "
            "'ni_cliente_ni_red' si no es un trabajo de red ni de un abonado "
            "(una tarea administrativa, una entrega interna, o un ticket que "
            "solo trae un nombre sin decir que hacer). "
            "Si el texto no alcanza para elegir, dejalo VACIO: eso lo manda a "
            "una persona, que es mejor que adivinar"),
    },
}


# =============================================================================
#  LA TABLA QUE DECIDE
# =============================================================================

#:  Los grupos que NUNCA pasan solos, por mas que todo lo demas este en orden.
#:  No es una lista de "todavia no": es el resultado de que ninguna medicion
#:  pueda respaldarlos.
#:
#:    NADA_LO_MIDE        ni el ping ni los niveles opticos ven una pagina
#:                        bloqueada. El Supervisor no tiene con que.
#:    NI_CLIENTE_NI_RED   no hay nada que diagnosticar, y si pasaran igual la
#:                        cola de Despacho se llenaria de cosas que no son
#:                        trabajo de campo.
SIEMPRE_UNA_PERSONA = frozenset({NADA_LO_MIDE, NI_CLIENTE_NI_RED})

#:  Los grupos donde el equipo sano es NORMAL, asi que la medicion no es
#:  condicion. Cambiar la clave del wifi igual necesita que alguien vaya, y una
#:  caja no tiene equipo de abonado que medir.
SIN_CONDICION_DE_MEDICION = frozenset({TRABAJO_PEDIDO, OBRA_DE_RED})

#:  La confianza que se exige CUANDO NO HAY MEDICION que respalde. Con
#:  medicion, la medicion manda y la confianza del modelo no decide nada.
#:
#:  Existe porque sin esto los dos grupos de arriba pasarian con una lectura
#:  dudosa, y eso es justo lo que el comentario de 'models.py' advertia. El
#:  valor sale del enum cerrado de 'cerebro.Confianza'.
CONFIANZA_EXIGIDA_SIN_MEDICION = "alta"


class Decision:
    """Lo que sale de evaluar un ticket. Siempre trae el POR QUE."""

    __slots__ = ("pasa", "porque", "grupo", "labor")

    def __init__(self, pasa: bool, porque: str, grupo: str = "",
                 labor: str = ""):
        self.pasa = pasa
        self.porque = porque
        self.grupo = grupo
        self.labor = labor

    def __repr__(self) -> str:                              # pragma: no cover
        return f"<Decision pasa={self.pasa} grupo={self.grupo!r}>"


def decidir(grupo: str, labor_veredicto: dict | None,
            confianza: str = "") -> Decision:
    """
    Si este ticket puede entrar a la cola de Despacho sin que alguien lo acepte.

    'labor_veredicto' es lo que devuelve 'clasificacion_de_trabajo.clasificar':
    trae 'labor', 'porque' y --lo que decide aca-- 'verificada', que distingue
    "lo dice una medicion" de "lo dice el texto".

    FAIL-CLOSED EN TODAS LAS SALIDAS: sin grupo, con un grupo que no esta en la
    lista, sin veredicto de labor, o con un dato que no se entiende, la
    respuesta es NO pasa. Que el default sea "lo mira una persona" es lo que
    hace que un camino no previsto degrade hacia lo seguro.
    """
    from operaciones import clasificacion_de_trabajo as clf

    lv = labor_veredicto if isinstance(labor_veredicto, dict) else {}
    labor = str(lv.get("labor") or "")
    verificada = bool(lv.get("verificada"))

    if not grupo:
        return Decision(False, "el modelo no pudo decir en que grupo cae este "
                               "ticket, asi que lo mira una persona")
    if grupo not in GRUPOS:
        #  No deberia llegar: 'cerebro' ya descarta un valor fuera de la lista.
        #  Se contesta igual, porque una guarda que depende de que OTRA guarda
        #  haya corrido no es una guarda.
        return Decision(False, f"grupo no declarado ({grupo}): lo mira una "
                               f"persona", grupo=grupo)

    if grupo in SIEMPRE_UNA_PERSONA:
        return Decision(False, _POR_QUE_NUNCA[grupo], grupo=grupo, labor=labor)

    if grupo in SIN_CONDICION_DE_MEDICION:
        #  EL EQUIPO SANO ES NORMAL ACA, asi que no se le pide a la medicion
        #  que confirme nada. Lo que SI se pide es que la lectura del reclamo
        #  sea firme: sin medicion que respalde, la confianza del modelo es lo
        #  unico que hay entre esto y mandar un caso por una frase ambigua.
        if confianza == CONFIANZA_EXIGIDA_SIN_MEDICION:
            return Decision(
                True,
                f"{_NOMBRE[grupo]}: el equipo sano es lo normal en este caso, "
                f"asi que la medicion no es condicion. La lectura del reclamo "
                f"es de confianza {confianza}",
                grupo=grupo, labor=labor)
        return Decision(
            False,
            f"{_NOMBRE[grupo]}: sin medicion que lo respalde se exige "
            f"confianza '{CONFIANZA_EXIGIDA_SIN_MEDICION}' en la lectura del "
            f"reclamo, y la que hay es '{confianza or 'ninguna'}'",
            grupo=grupo, labor=labor)

    #  FALLA DE SERVICIO: LA MEDICION MANDA.
    #
    #  'verificada' en True significa que la labor salio de MEDIR el equipo y
    #  no de leer el texto -- y 'clasificacion_de_trabajo._de_la_prueba' solo
    #  la pone en True cuando el equipo esta caido o la señal es debil. Un
    #  equipo en linea y sano NO produce un veredicto verificado: esa funcion
    #  devuelve None, el caso cae al texto, y llega aca con 'verificada' en
    #  False.
    #
    #  Asi que esta sola condicion cubre las cinco salidas que el cliente
    #  definio, sin repetir en dos lugares la tabla de estados del equipo. Si
    #  algun dia hay que distinguirlas por separado, se distinguen ALLA, que es
    #  donde esta el vocabulario.
    if not verificada:
        return Decision(
            False,
            "falla de servicio sin que la medicion la confirme: puede ser que "
            "el equipo este sano --y entonces el reclamo y la medicion se "
            "contradicen, hay que preguntarle al cliente-- o que no se haya "
            "podido medir, que no es lo mismo que estar sano. En los dos casos "
            "lo mira una persona",
            grupo=grupo, labor=labor)

    if labor == clf.NO_REQUIERE_VISITA:
        #  Caido por falta de energia en el domicilio. Esta MEDIDO y es firme,
        #  pero lo que prueba es que una visita NO resuelve nada: hay que
        #  preguntarle al cliente si se le fue la luz.
        return Decision(
            False,
            "la medicion dice que el equipo esta caido por falta de energia en "
            "el domicilio: una visita no resuelve eso. Hay que preguntarle al "
            "cliente",
            grupo=grupo, labor=labor)

    return Decision(
        True,
        f"falla de servicio CONFIRMADA por la medicion del equipo: "
        f"{lv.get('porque') or 'sin detalle'}",
        grupo=grupo, labor=labor)


_NOMBRE = {
    FALLA_DE_SERVICIO: "falla de servicio",
    TRABAJO_PEDIDO: "trabajo pedido por el cliente",
    OBRA_DE_RED: "obra de red",
    NADA_LO_MIDE: "reclamo que ninguna herramienta mide",
    NI_CLIENTE_NI_RED: "ni de un cliente ni de la red",
}

_POR_QUE_NUNCA = {
    NADA_LO_MIDE: (
        "es un reclamo que ninguna herramienta de red puede comprobar: ni el "
        "ping ni los niveles opticos lo ven. Lo mira una persona"),
    NI_CLIENTE_NI_RED: (
        "no es un trabajo de red ni de un abonado, asi que no hay nada que "
        "diagnosticar. Lo mira una persona"),
}


# =============================================================================
#  EL PASO, CON SUS PUERTAS
# =============================================================================

#:  La tarea que una persona tiene que delegar para que esto ocurra. Vive en
#:  'tareas_delegadas.CATALOGO' y es PROPIA: habilitar el cierre de
#:  desincronizados no puede habilitar esto de rebote. Son dos permisos
#:  distintos porque son dos efectos distintos, y el 09/10/2026 ya se dejo
#:  escrito por que el nivel de autonomia no alcanza como unica puerta -- el
#:  nivel dice CUANTO puede hacer, la tarea dice QUE le pidieron que haga.
TAREA = "pasar_a_despacho_segun_las_reglas"

#:  El nivel que la propuesta pide para pasar. Es 3 --ejecutar algo
#:  reversible-- y no 4, porque sacar un caso de la cola de Despacho es
#:  deshacerlo: no se le prometio nada al cliente y no salio nadie a la calle.
#:  El 4 es "siempre lo aprueba una persona" y 'autonomia.puede' lo niega
#:  siempre, por configuracion que tenga la empresa.
#  Se escribe el 3 y NO se importa el enum, por lo mismo que arriba. Que este
#  numero siga siendo 'NIVEL_EJECUTAR_REVERSIBLE' lo afirma una prueba: una
#  constante copiada sin guarda es una que se desincroniza en silencio.
NIVEL_PARA_PASAR = 3


def de_la_senal(senal) -> Decision:
    """La decision para esta señal, leyendo lo que 'diagnosticar' dejo escrito.

    Se lee de 'senal.datos' --que es lo que el codigo de la fase siguiente
    consume-- y NO parseando el texto de una evidencia, que es el error que
    este proyecto nombra en varios archivos.
    """
    datos = getattr(senal, "datos", None) or {}
    return decidir(
        str(datos.get("grupo") or ""),
        {"labor": datos.get("labor") or "",
         "porque": datos.get("labor_porque") or "",
         "verificada": bool(datos.get("labor_verificada"))},
        confianza=str(datos.get("diagnostico_confianza") or ""))


def pasar_si_corresponde(org, senal, propuesta, *, ahora=None,
                         autorizacion=None) -> dict:
    """
    Acepta la propuesta --y con eso el caso entra a la cola de Despacho-- si
    las reglas y las dos puertas lo dejan.

    Devuelve {paso, porque, grupo}. NUNCA levanta: un paso que no ocurre es un
    resultado posible del ciclo, no algo que deba tumbarlo. Quedan otras
    señales por procesar y lo que ya se guardo esta guardado.

    QUE SIGNIFICA "ENTRA A LA COLA"
    -------------------------------
    'campo/casos-despachables/' lista los casos cuya propuesta esta ACEPTADA o
    MODIFICADA. Aceptarla es, literalmente, que el caso aparezca ahi. Lo que
    NO hace: crear la orden de trabajo, elegir plantilla, asignar tecnico o
    fecha. Eso sigue siendo de quien despacha, y ese limite es lo que mantiene
    esto reversible.

    LAS TRES PUERTAS, Y CADA UNA ACOTA SIN AUTORIZAR
    ------------------------------------------------
      1. LAS REGLAS. La tabla de este modulo, que para una falla de servicio
         exige una medicion que la confirme.
      2. ALGUIEN SE LO PIDIO. 'TAREA' delegada por una persona desde el chat.
         Sin esta puerta, subir el nivel para otra cosa encenderia esto en
         silencio.
      3. LA EMPRESA LO AUTORIZO. 'autonomia.puede(org, 3)' lee el nivel de
         ESTA empresa, que solo sube una persona con nombre, motivo y
         criterios medidos.
    """
    from django.utils import timezone

    from operaciones import autonomia, supervisor as sup, tareas_delegadas
    from operaciones.models import PropuestaSupervisor

    ahora = ahora or timezone.now()
    d = de_la_senal(senal)

    #  PUERTA 1 · LAS REGLAS.
    if not d.pasa:
        return {"paso": False, "porque": d.porque, "grupo": d.grupo}

    #  PUERTA 2 · QUE ALGUIEN LO HAYA PEDIDO.
    try:
        delegada = tareas_delegadas.esta_delegada(org, TAREA)
    except Exception as e:                                       # noqa: BLE001
        #  No poder COMPROBAR el permiso es lo mismo que no tenerlo.
        return {"paso": False, "grupo": d.grupo,
                "porque": f"no se pudo comprobar si la tarea esta delegada "
                          f"({type(e).__name__}): sin eso no se pasa"}
    if not delegada:
        return {"paso": False, "grupo": d.grupo,
                "porque": "nadie le delego al Supervisor que pase casos a "
                          "Despacho: se le pide desde su chat"}

    #  PUERTA 3 · EL TECHO DE LA EMPRESA.
    veredicto = autorizacion if autorizacion is not None else autonomia.puede(
        org, NIVEL_PARA_PASAR)
    if not (veredicto or {}).get("puede"):
        return {"paso": False, "grupo": d.grupo,
                "porque": f"la empresa no lo autoriza: "
                          f"{(veredicto or {}).get('motivo') or 'sin motivo'}"}

    #  EL EFECTO. 'revisar' bloquea la fila antes de mirarle el estado, asi que
    #  una persona que acepte o rechace al mismo tiempo no se pisa con esto.
    try:
        sup.revisar(
            propuesta, actor=None, automatico=True,
            decision=PropuestaSupervisor.ACEPTADA,
            comentario=f"Aceptada automaticamente por el Supervisor NOC IA. "
                       f"{d.porque}"[:1000],
            ahora=ahora)
    except Exception as e:                                       # noqa: BLE001
        #  El tipo y no el texto: el mensaje podria traer de vuelta la
        #  descripcion del ticket, que lleva datos del cliente.
        logger.info("Supervisor: no se pudo pasar a Despacho (%s)",
                    type(e).__name__)
        return {"paso": False, "grupo": d.grupo,
                "porque": f"no se pudo registrar la aceptacion "
                          f"({type(e).__name__})"}

    return {"paso": True, "porque": d.porque, "grupo": d.grupo,
            "labor": d.labor}
