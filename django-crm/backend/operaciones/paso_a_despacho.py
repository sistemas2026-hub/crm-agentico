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
    "confianza_del_grupo": {
        "valores": ("alta", "media", "baja"),
        "ayuda": (
            "que tan seguro estas DEL GRUPO que elegiste arriba. OJO: no es "
            "lo mismo que 'confianza', que habla de tu hipotesis sobre la "
            "CAUSA. Aca la pregunta es mas simple: ¿el reclamo dice con "
            "claridad que es lo que se pide? Un texto que dice 'solicita "
            "cambio de domicilio' es 'alta' aunque no tengas ninguna "
            "hipotesis de que le pasa al equipo; un texto confuso o que "
            "mezcla dos pedidos es 'baja'"),
    },
}

#:  POR QUE HAY DOS CONFIANZAS, Y NO ES REDUNDANCIA  --  14/10/2026
#:
#:  La primera version de este modulo uso 'cerebro.Confianza', la de la
#:  hipotesis, como puerta de los grupos que pasan sin medicion. MEDIDO sobre
#:  las 142 lecturas que existian ese dia, el umbral resulto inalcanzable:
#:
#:      media           84   59.2%
#:      baja            29   20.4%
#:      sin_hipotesis   24   16.9%
#:      alta             5    3.5%   <- lo que la regla exigia
#:
#:  De los 40 tickets de 'trabajo_pedido' y 'obra_de_red' habrian pasado uno o
#:  dos. Fue poner un umbral sin medir si el modelo lo alcanza.
#:
#:  Y el numero ademas señala el error conceptual: esa confianza acompaña a una
#:  HIPOTESIS SOBRE LA CAUSA, y en un trabajo pedido no hay causa que
#:  hipotetizar -- el cliente pide algo. Exigirle seguridad sobre una hipotesis
#:  que no existe es pedir lo imposible, y el 16.9% de 'sin_hipotesis' es
#:  exactamente eso ocurriendo.
#:
#:  Asi que se le pregunta lo que si corresponde: que tan claro esta el PEDIDO.
CONFIANZA_DEL_GRUPO = "confianza_del_grupo"


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


#:  La fuente con la que 'diagnostico_de_ticket' marca sus observaciones. Se
#:  repite aca a proposito en vez de importarla: ese modulo arrastra el ciclo
#:  entero, y lo unico que hace falta es la cadena. La guarda que verifica que
#:  siguen siendo la misma vive en las pruebas.
FUENTE_DE_LA_LECTURA = "diagnostico_del_ticket"

#:  Que puerta freno el paso. Viaja en lo que devuelve 'pasar_si_corresponde'
#:  para que quien anota el motivo sepa si es el de las REGLAS --propio de
#:  este caso, y lo que una persona necesita leer-- o el de una puerta de la
#:  empresa, que es igual para todos y puede traer texto que escribio alguien.
PUERTA_REGLAS = "reglas"
PUERTA_TAREA = "tarea"
PUERTA_EMPRESA = "empresa"
PUERTA_REGISTRO = "registro"

#:  La fuente con la que el paso deja escrito, en la propuesta, por que una
#:  lectura se queda con una persona.
#:
#:  NO PUEDE CONTENER "diagnostico_del_ticket": '_tickets_abiertos_con_tecnico'
#:  busca esa cadena con 'evidencia__icontains' sobre TODO el JSON para saber
#:  que tickets ya se leyeron, y una propuesta sin lectura que solo tuviera
#:  esta pieza dejaria de leerse. Una prueba lo fija.
FUENTE_REVISION = "revision_del_paso_a_despacho"


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
        #  LA CONFIANZA DEL GRUPO, no la de la hipotesis -- ver la nota de
        #  CONFIANZA_DEL_GRUPO arriba, con la medicion que lo motivo.
        confianza=str(datos.get(CONFIANZA_DEL_GRUPO) or ""))


def de_la_propuesta(propuesta) -> Decision:
    """
    La decision usando la lectura que YA esta guardada, sin volver a leer.

    POR QUE EXISTE  --  14/10/2026
    ------------------------------
    El paso a Despacho se decide con lo que 'diagnosticar' deja en
    'senal.datos', y la señal se muere con el ciclo. Sin esta funcion, un
    ticket que no pudo pasar hoy --porque una puerta estaba cerrada ese dia--
    necesita que el modelo lo LEA OTRA VEZ para reintentar, y el tope son diez
    lecturas por vuelta.

    Es la misma forma del bug que tenia atascados a los desincronizados: una
    propuesta diagnosticada el lunes no volvia a entrar nunca, por mas que el
    martes se autorizara todo. Ahi el disparador era el nivel de autonomia;
    aca, un dato que solo vivia durante la corrida que lo produjo.

    SE LEEN CLAVES, NO TEXTO. La observacion de la lectura trae 'grupo',
    'labor', 'labor_verificada' y 'confianza' como claves propias --mismo
    patron que 'pieza["veredicto"]' en el modulo optico-- asi que esto no
    interpreta ninguna frase.

    LA MAS RECIENTE GANA: la evidencia de un ticket se ACUMULA a proposito (es
    el historial del reclamo, no un diagnostico que se corrige), asi que la
    ultima lectura es la que describe la situacion de hoy.
    """
    ultima = _ultima_lectura_con_grupo(propuesta)
    if ultima is None:
        return Decision(False, "la lectura guardada no trae el grupo: hay que "
                               "volver a leer el reclamo antes de poder "
                               "decidir")
    return decidir(
        str(ultima.get("grupo") or ""),
        {"labor": ultima.get("labor") or "",
         "porque": ultima.get("labor_porque") or "",
         "verificada": bool(ultima.get("labor_verificada"))},
        confianza=str(ultima.get(CONFIANZA_DEL_GRUPO) or ""))


def _ultima_lectura_con_grupo(propuesta) -> dict | None:
    """
    La ultima pieza de lectura que trae la clave 'grupo', o None.

    Es el recorrido que 'de_la_propuesta' hacia en linea, sacado para que la
    anotacion del motivo lea EXACTAMENTE la misma lectura que decidio: si cada
    una tuviera su propio recorrido, el dia que uno cambie el motivo escrito
    hablaria de otra lectura que la que fallo.
    """
    ultima = None
    for pieza in (getattr(propuesta, "evidencia", None) or []):
        if not isinstance(pieza, dict):
            continue
        if pieza.get("fuente") != FUENTE_DE_LA_LECTURA:
            continue
        if "grupo" not in pieza:
            #  Una lectura anterior al 14/10/2026: tiene la frase pero no las
            #  claves. No sirve para decidir, y tratarla como "sin grupo" es
            #  justo lo correcto -- va a una persona hasta que se relea.
            continue
        ultima = pieza
    return ultima


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

    #  LA SEÑAL PRIMERO, LA PROPUESTA DESPUES. Si este ciclo acaba de leer el
    #  ticket, la señal trae el juicio mas nuevo; si no lo leyo --el tope son
    #  diez por vuelta-- se usa la lectura que ya estaba guardada, en vez de
    #  dejar el ticket esperando una relectura que cuesta una llamada al
    #  modelo.
    d = de_la_senal(senal)
    if not d.grupo:
        d = de_la_propuesta(propuesta)

    #  PUERTA 1 · LAS REGLAS.
    if not d.pasa:
        return {"paso": False, "porque": d.porque, "grupo": d.grupo,
                "puerta": PUERTA_REGLAS}

    #  PUERTA 2 · QUE ALGUIEN LO HAYA PEDIDO.
    try:
        delegada = tareas_delegadas.esta_delegada(org, TAREA)
    except Exception as e:                                       # noqa: BLE001
        #  No poder COMPROBAR el permiso es lo mismo que no tenerlo.
        return {"paso": False, "grupo": d.grupo, "puerta": PUERTA_TAREA,
                "porque": f"no se pudo comprobar si la tarea esta delegada "
                          f"({type(e).__name__}): sin eso no se pasa"}
    if not delegada:
        return {"paso": False, "grupo": d.grupo, "puerta": PUERTA_TAREA,
                "porque": "nadie le delego al Supervisor que pase casos a "
                          "Despacho: se le pide desde su chat"}

    #  PUERTA 3 · EL TECHO DE LA EMPRESA.
    veredicto = autorizacion if autorizacion is not None else autonomia.puede(
        org, NIVEL_PARA_PASAR)
    if not (veredicto or {}).get("puede"):
        return {"paso": False, "grupo": d.grupo, "puerta": PUERTA_EMPRESA,
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
            #  LA TAREA QUEDA EN LA AUDITORIA, y sin esto el panel no puede
            #  separar un pase a Despacho de la aceptacion de un cierre: las
            #  dos escriben 'PropuestaSupervisor APPROVED'.
            tarea=TAREA,
            ahora=ahora)
    except Exception as e:                                       # noqa: BLE001
        #  El tipo y no el texto: el mensaje podria traer de vuelta la
        #  descripcion del ticket, que lleva datos del cliente.
        logger.info("Supervisor: no se pudo pasar a Despacho (%s)",
                    type(e).__name__)
        return {"paso": False, "grupo": d.grupo, "puerta": PUERTA_REGISTRO,
                "porque": f"no se pudo registrar la aceptacion "
                          f"({type(e).__name__})"}

    return {"paso": True, "porque": d.porque, "grupo": d.grupo,
            "labor": d.labor}


# =============================================================================
#  EL MOTIVO ESCRITO EN LA PROPUESTA
# =============================================================================
#
#  POR QUE EXISTE  --  16/10/2026
#  -----------------------------
#  La definicion de terminado del objetivo lo pedia desde el 14/10 --"los casos
#  que ninguna regla habilita siguen esperando a una persona, con el motivo
#  escrito"-- y el motivo solo salia sumado en el log del worker. En el panel,
#  una propuesta que el Supervisor revisaba cada hora se veia igual que una que
#  nadie habia mirado, y por eso parecia que no revisaba.
#
#  UNA PIEZA QUE SE REEMPLAZA, NO SE APILA. Es el patron del modulo optico
#  ('diagnostico_optico.anotar_el_cierre'): el panel dibuja cada pieza en
#  "Hechos observados" sin su hora, y dos motivos juntos se leerian como dos
#  cosas que pasan a la vez. La lectura del reclamo, en cambio, se apila: es
#  la historia del ticket. Esto es el estado de la ultima revision.
#
#  SOLO CUANDO CAMBIA. Con el mismo motivo no se toca nada: sesenta escrituras
#  por hora diciendo lo mismo no informan. Por eso 'observado_en' dice DESDE
#  CUANDO vale ese motivo, no cuando fue la ultima vuelta.

#:  Lo que se escribe cuando las reglas dejan pasar el caso y lo frena una
#:  puerta de la empresa. TEXTO FIJO a proposito: el motivo de la puerta 3
#:  arrastra lo que una persona escribio al mover el interruptor del motor, y
#:  copiarlo a cada propuesta seria repartir texto libre por toda la cola.
_POR_QUE_LAS_PUERTAS = {
    PUERTA_TAREA: (
        "Las reglas lo dejan pasar, pero el paso automatico a Despacho no esta "
        "delegado al Supervisor, o no se pudo comprobar. Lo mira una persona"),
    PUERTA_EMPRESA: (
        "Las reglas lo dejan pasar, pero la empresa no tiene autorizado ahora "
        "que el Supervisor lo pase solo. Lo mira una persona"),
}


#:  Una falla sin confirmar cuya lectura dijo "el equipo esta en linea y sano".
#:  Medido el 16/10/2026: esa frase hoy no sale de una medicion (ver
#:  'clasificacion_de_trabajo.EQUIPO_SANO'), y el 'porque' de las reglas
#:  --"puede estar sano, o no se pudo medir"-- tampoco es cierto: SmartOLT
#:  contesto. Con una fibra cortada, ese texto empujaba a llamar al cliente en
#:  vez de mandar a alguien (auditor independiente, 16/10). Lleva "Falta" a
#:  proposito: el panel lo pone en "Informacion que falta", que es lo que es.
_FALLA_SIN_INTERPRETAR = (
    "falla de servicio sin confirmar: SmartOLT contesto, pero la lectura "
    "todavia no interpreta el estado del equipo, asi que no se sabe si esta "
    "sano o caido. Falta mirarlo en SmartOLT antes de llamar al cliente; lo "
    "mira una persona")

#:  Una propuesta que todavia no tiene lectura del reclamo. El 'porque' de
#:  'de_la_propuesta' dice "la lectura guardada no trae el grupo", y en una
#:  que nunca se leyo eso afirma una lectura que no existe.
_SIN_LECTURA = (
    "falta la lectura del reclamo: las reglas todavia no tienen con que "
    "decidir. Se decide en la vuelta en que el Supervisor lo lea")


def ultima_revision(propuesta) -> dict | None:
    """La pieza que el paso dejo escrita en la propuesta, o None."""
    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE_REVISION:
            return pieza
    return None


def motivo_para_anotar(propuesta, resultado: dict) -> str | None:
    """
    El texto que se escribe en la propuesta, o None si no hay que escribir.

    'propuesta' es LA COPIA CON LA QUE SE DECIDIO, no la que se vuelve a leer
    bloqueada para escribir. Si entre una y otra llego una lectura nueva, el
    motivo explica la decision que se tomo, sin mezclar su 'porque' con la
    explicacion de otra lectura. La vuelta que viene decide con la nueva y, si
    el motivo cambia, lo reemplaza.

    LAS REGLAS: su 'porque'. Y para una falla de servicio que la medicion no
    confirmo, ademas por que no se pudo medir --"no se pudo leer el equipo
    (onu_no_vinculada)"--, que es lo que una persona necesita para saber que
    hacer. Es texto fijo de 'clasificacion_de_trabajo', sin datos del cliente.

    LO QUE NO SE COPIA: "el equipo esta en linea y sano". Medido el 16/10/2026,
    esa frase hoy no sale de una medicion (ver 'clasificacion_de_trabajo.
    EQUIPO_SANO'): el clasificador la dice con cualquier dato del equipo, aun
    con la fibra cortada. Copiarla aca convertiria un defecto de la lectura en
    una afirmacion escrita en la propuesta, que es donde una persona decide si
    manda a alguien. Tampoco sirve el 'porque' de las reglas solo: "puede estar
    sano, o no se pudo medir" es falso las dos veces cuando SmartOLT contesto.
    Va '_FALLA_SIN_INTERPRETAR'. El dia que el clasificador lea las claves del
    motor y separe "sano" de "no lo entendi", esta excepcion se quita: la
    prueba 'test_k' avisa ese dia.

    SIN LECTURA TODAVIA: '_SIN_LECTURA', no el texto de 'de_la_propuesta', que
    supone una lectura guardada.

    UNA PUERTA DE LA EMPRESA: texto fijo, ver '_POR_QUE_LAS_PUERTAS'.

    NO PODER REGISTRAR LA ACEPTACION: nada. Es transitorio y la vuelta que
    viene lo reintenta; escribir "se queda para una persona" seria falso.
    """
    from operaciones import clasificacion_de_trabajo as clf

    puerta = resultado.get("puerta") or PUERTA_REGLAS
    if puerta in _POR_QUE_LAS_PUERTAS:
        return _POR_QUE_LAS_PUERTAS[puerta]
    if puerta != PUERTA_REGLAS:
        return None
    from operaciones import diagnostico_de_ticket as dxt

    if dxt.le_falta_lectura(propuesta):
        return _SIN_LECTURA
    porque = str(resultado.get("porque") or "sin motivo")
    lectura = _ultima_lectura_con_grupo(propuesta) or {}
    explicacion = str(lectura.get("labor_porque") or "")
    sin_confirmar = (resultado.get("grupo") == FALLA_DE_SERVICIO
                     and not lectura.get("labor_verificada"))
    if sin_confirmar and explicacion.startswith(clf.EQUIPO_SANO):
        return _FALLA_SIN_INTERPRETAR
    if sin_confirmar and explicacion:
        porque = f"{porque}. Lo que dijo la medicion: {explicacion}"
    return porque


def motivo_para_el_registro(resultado: dict) -> str:
    """
    La clave con que el motivo se suma en la linea de log de la fase.

    Es el 'porque' tal cual, MENOS el de la puerta de la empresa: ese arrastra
    lo que una persona escribio al mover el interruptor, y ni el log ni el
    resultado de la tarea que guarda Celery tienen control de acceso. Va el
    mismo texto fijo que se escribe en la propuesta; el motivo libre se lee en
    /autonomia, que es donde se escribio. Las demas puertas llevan texto fijo
    y, a lo sumo, el tipo de una excepcion.
    """
    if (resultado.get("puerta") or PUERTA_REGLAS) == PUERTA_EMPRESA:
        return _POR_QUE_LAS_PUERTAS[PUERTA_EMPRESA]
    return str(resultado.get("porque") or "sin motivo")


def anotar_por_que_se_queda(propuesta, resultado: dict, ahora) -> bool:
    """
    Deja escrito en la propuesta por que se queda con una persona, y desde
    cuando. Devuelve si escribio.

    LA FILA SE BLOQUEA Y SE VUELVE A MIRAR. Entre que el ciclo listo las
    pendientes y llega aca, una persona pudo aceptarla o rechazarla, y otra
    vuelta pudo anotarle algo. Sin el bloqueo, una propuesta ya decidida
    ganaria una pieza que dice que se queda; sin releer la evidencia, se
    pisaria lo que otra escritura acaba de dejar. Es el patron de 'revisar' y
    'cancelar'.

    EL MOTIVO SALE DE LA COPIA QUE DECIDIO ('propuesta'), y la evidencia que
    se reescribe es la de la fila bloqueada ('fresca'): asi no se pierde una
    lectura que llego en el medio, y el motivo no mezcla dos lecturas.

    LO QUE NO CUBRE, dicho: 'diagnostico_de_ticket.guardar_en_propuesta'
    escribe la lectura sin bloqueo y sin mirar el estado, desde una copia
    cargada antes de leer. Si dos ciclos se solapan --basta apretar el boton
    durante la fase de lectura, que tarda unos 19 minutos--, esa escritura
    puede borrar la pieza de aca o DEVOLVER la anterior. Si la propuesta sigue
    pendiente, se repara sola en la vuelta siguiente, pero el "desde cuando"
    empieza de nuevo. Si ya paso, la pieza devuelta se queda: ninguna vuelta
    vuelve a mirar una aceptada. Es anterior a este cambio: ver
    SPEC/auditorias/PASO-A-DESPACHO.md (A-10 y A-11).
    """
    from django.db import transaction

    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor

    with transaction.atomic():
        fresca = (PropuestaSupervisor.objects
                  .select_for_update()
                  .filter(pk=propuesta.pk,
                          estado=PropuestaSupervisor.PROPUESTA)
                  .first())
        if fresca is None:
            return False
        porque = motivo_para_anotar(propuesta, resultado)
        if porque is None:
            return False
        porque = " ".join(porque.split())[:600]
        ultima = ultima_revision(fresca)
        if ultima is not None and ultima.get("porque") == porque:
            return False
        pieza = sup._observacion(
            FUENTE_REVISION, fresca.origen_id,
            f"Revisada por el Supervisor NOC IA: se queda para una persona. "
            f"{porque}",
            ahora)
        pieza["porque"] = porque
        pieza["grupo"] = str(resultado.get("grupo") or "")
        resto = [x for x in (fresca.evidencia or [])
                 if not (isinstance(x, dict)
                         and x.get("fuente") == FUENTE_REVISION)]
        fresca.evidencia = [*resto, pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    return True


def quitar_por_que_se_quedaba(propuesta) -> bool:
    """
    Cuando la propuesta PASA, la pieza que decia "se queda para una persona"
    deja de ser cierta, y se quita. Devuelve si quito algo.

    El caso tipico: el interruptor estuvo apagado, se escribio "la empresa no
    tiene autorizado ahora...", y en la vuelta siguiente paso. Sin esto queda
    una propuesta ACEPTADA cuya evidencia dice que se quedo con una persona, y
    el panel la dibuja sin hora. El pase ya queda dicho donde corresponde: en
    'resultado' y en la auditoria.

    Mismo cuidado que al escribir: la fila bloqueada, y solo si ya no esta
    pendiente.

    NADIE LO REINTENTA: la vuelta siguiente solo mira pendientes. Si esto
    falla, la aceptada conserva el motivo viejo (A-11 en
    SPEC/auditorias/PASO-A-DESPACHO.md).
    """
    from django.db import transaction

    from operaciones.models import PropuestaSupervisor

    with transaction.atomic():
        fresca = (PropuestaSupervisor.objects
                  .select_for_update()
                  .filter(pk=propuesta.pk)
                  .exclude(estado=PropuestaSupervisor.PROPUESTA)
                  .first())
        if fresca is None or ultima_revision(fresca) is None:
            return False
        fresca.evidencia = [x for x in (fresca.evidencia or [])
                            if not (isinstance(x, dict)
                                    and x.get("fuente") == FUENTE_REVISION)]
        fresca.save(update_fields=["evidencia", "updated_at"])
    return True
