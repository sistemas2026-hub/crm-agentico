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

El modelo no juzga si -27 dBm es debil: eso lo calcula el motor
('diagnosticar_servicio') contra el rango de la guia, desde la Fase 3. Y el
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
import math
import re

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

    __slots__ = ("pasa", "porque", "grupo", "labor", "puerta")

    def __init__(self, pasa: bool, porque: str, grupo: str = "",
                 labor: str = "", puerta: str = ""):
        self.pasa = pasa
        self.porque = porque
        self.grupo = grupo
        self.labor = labor
        #  Que la freno. Las reglas, salvo que diga otra cosa: desde la Fase 3
        #  tambien puede ser el caso, que ya no esta abierto (PUERTA_CASO).
        self.puerta = puerta or PUERTA_REGLAS

    def __repr__(self) -> str:                              # pragma: no cover
        return f"<Decision pasa={self.pasa} grupo={self.grupo!r}>"


def decidir(grupo: str, labor_veredicto: dict | None,
            confianza: str = "", medicion: dict | None = None) -> Decision:
    """
    Si este ticket puede entrar a la cola de Despacho sin que alguien lo acepte.

    'labor_veredicto' es lo que devuelve 'clasificacion_de_trabajo.clasificar':
    trae 'labor', 'porque' y 'verificada'. Desde la Fase 3 (16/10/2026) una
    falla de servicio NO se decide con 'verificada' sino con 'medicion', la
    pieza que guarda 'medicion_de_fallas' con lo que midio el motor.

    FAIL-CLOSED EN TODAS LAS SALIDAS: sin grupo, con un grupo que no esta en la
    lista, sin veredicto de labor, o con un dato que no se entiende, la
    respuesta es NO pasa. Que el default sea "lo mira una persona" es lo que
    hace que un camino no previsto degrade hacia lo seguro.
    """
    lv = labor_veredicto if isinstance(labor_veredicto, dict) else {}
    labor = str(lv.get("labor") or "")

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

    #  FALLA DE SERVICIO: LA MEDICION DEL EQUIPO MANDA  --  16/10/2026, Fase 3
    #  ----------------------------------------------------------------------
    #  Hasta la Fase 3 decidia la labor de la lectura ('verificada'). Medido el
    #  16/10: esa labor no salia verificada nunca, porque el clasificador
    #  recibia el equipo del endpoint liviano --Online u Offline, sin causa--
    #  con claves que no lee. Ahora decide la MEDICION: la pieza que deja
    #  'medicion_de_fallas' con lo que devolvio 'diagnosticar_servicio' del
    #  motor. Trae el estado, la causa de la caida y la señal YA CLASIFICADA
    #  contra el rango de la guia: este modulo no copia el rango, lee 'senal'.
    #
    #  UNA SOLA SALIDA PASA: el equipo en linea con la señal fuera de rango.
    #  Decidido por el usuario el 16/10/2026, y cambia la regla 1 del 14/10:
    #  una caida por LOS o LOF va a una persona, porque desde la OLT no se
    #  distingue una fibra cortada de un equipo desenchufado (la skill
    #  smartolt-api registra que la operacion lo vio seguido). Un equipo EN
    #  LINEA con la señal fuera de rango no puede ser un desenchufe.
    from operaciones import diagnostico_optico as optico

    m = medicion if isinstance(medicion, dict) else {}
    if m.get("medido_con") != MEDIDO_CON:
        return Decision(False, _FALTA_MEDIR, grupo=grupo, labor=labor)

    estado = str(m.get("estado") or "")
    senal = str(m.get("senal") or "")
    causa = str(m.get("causa_caida") or "")
    if estado == optico.EN_LINEA:
        #  EL UNICO 'True' DE LA REGLA 1 EXIGE EL NUMERO. El motor clasifica
        #  como 'debil' cualquier cosa fuera del rango, un NaN incluido; sin un
        #  nivel medido no hay contra que haberlo decidido (auditor de
        #  frontera, 16/10).
        if senal == optico.SENAL_DEBIL and _hay_nivel(m):
            return Decision(
                True,
                f"falla de servicio CONFIRMADA por la medicion del equipo: "
                f"esta en linea con la señal fuera del rango de la guia"
                f"{_nivel(m)}",
                grupo=grupo, labor=labor)
        if senal == optico.SENAL_BUENA:
            return Decision(False, _EN_RANGO.format(nivel=_nivel(m)),
                            grupo=grupo, labor=labor)
        return Decision(False, _EN_LINEA_SIN_SENAL, grupo=grupo, labor=labor)
    if estado == optico.CAIDO:
        if causa == optico.CAUSA_SIN_ENERGIA:
            return Decision(False, _SIN_ENERGIA, grupo=grupo, labor=labor)
        if causa == optico.CAUSA_FIBRA:
            return Decision(False, _SIN_SENAL_OPTICA, grupo=grupo, labor=labor)
        if causa:
            return Decision(False, _CAIDO_SIN_CAUSA, grupo=grupo, labor=labor)
        return Decision(False, _CAIDO_SIN_DATOS, grupo=grupo, labor=labor)
    motivo = str(m.get("motivo") or "").strip()
    return Decision(
        False,
        "no se pudo medir el equipo con el proveedor optico"
        + (f" ({motivo[:120]})" if motivo else "")
        + ". Lo mira una persona",
        grupo=grupo, labor=labor)


#  Lo que '_nivel' agrega a un motivo, para sacarlo de la clave del log.
_SIN_NIVEL = re.compile(r" \(-?[0-9.]+ dBm\)")


def _hay_nivel(medicion: dict) -> bool:
    """Si la medicion trae un nivel en dBm de verdad: un numero finito."""
    dbm = (medicion or {}).get("senal_dbm")
    return (isinstance(dbm, (int, float)) and not isinstance(dbm, bool)
            and math.isfinite(dbm))


def _nivel(medicion: dict) -> str:
    """El nivel medido, para que quien lea sepa contra que se decidio."""
    dbm = (medicion or {}).get("senal_dbm")
    return f" ({dbm} dBm)" if isinstance(dbm, (int, float)) else ""


#  LO QUE DICE CADA MEDICION QUE NO PASA. Texto fijo y tecnico, sin datos del
#  cliente: es lo que una persona lee en la propuesta para saber que hacer.
_FALTA_MEDIR = (
    "falla de servicio sin medir todavia: falta la medicion del equipo, que el "
    "Supervisor pide en las proximas vueltas. Hasta entonces la mira una "
    "persona")
_EN_RANGO = (
    "la medicion dice que el equipo esta en linea con la señal dentro del "
    "rango de la guia{nivel}: el reclamo y la medicion se contradicen. Hay que "
    "preguntarle al cliente que le pasa")
_EN_LINEA_SIN_SENAL = (
    "la medicion dice que el equipo esta en linea, pero no trajo el nivel de "
    "señal: no confirma la falla. Se vuelve a medir al dia; mientras tanto lo "
    "mira una persona")
_SIN_ENERGIA = (
    "la medicion dice que el equipo se quedo sin energia (dying-gasp): es la "
    "casa del cliente. Hay que preguntarle si tiene luz; una visita no resuelve "
    "eso")
_SIN_SENAL_OPTICA = (
    "la medicion dice que el equipo perdio la señal optica (LOS/LOF). Puede ser "
    "la fibra o un equipo desenchufado, y desde la OLT no se distingue: falta "
    "preguntarle al cliente si el equipo esta enchufado y tiene luz")
_CAIDO_SIN_CAUSA = (
    "la medicion dice que el equipo esta caido por una causa que no se sabe "
    "distinguir. Lo mira una persona")
#  Un caido sin causa ni señal puede ser un 200 del proveedor sin datos: no se
#  afirma la caida (auditor independiente, 16/10).
_CAIDO_SIN_DATOS = (
    "la medicion volvio como caido, pero sin causa ni señal: puede ser una "
    "respuesta incompleta del proveedor. Se vuelve a medir al dia; mientras "
    "tanto lo mira una persona")


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

#:  LA MEDICION DEL EQUIPO DE UNA FALLA  --  16/10/2026, Fase 3. La escribe
#:  'medicion_de_fallas' y la lee 'decidir'. Su propia fuente, y NO
#:  'diagnostico_del_ticket': esa la buscan con 'icontains' para saber si un
#:  ticket ya se leyo, y una medicion no es una lectura. Tampoco 'diagnostico',
#:  que es la del modulo optico.
FUENTE_MEDICION = "medicion_del_equipo"
#:  De donde salio la medicion. Una pieza sin esta marca no decide nada.
MEDIDO_CON = "diagnosticar_servicio"

#:  Como figura el pase automatico en la auditoria que ve toda la empresa.
#:  TEXTO FIJO a proposito: la 'accion_propuesta' la redacto el modelo leyendo
#:  el ticket, y puede traer el nombre del cliente (revisor de PII, 16/10). La
#:  recomendacion sigue en el detalle de la propuesta, para quien la puede ver.
NOMBRE_DEL_PASE = "Pase automatico a Despacho"

#:  LOS ESTADOS DE DEXTER CON LOS QUE UN CASO PUEDE PASAR SOLO. Lista blanca:
#:  para un efecto que ocurre sin persona, falla cerrado. 'supervisor' trata
#:  'Rejected' y 'Duplicate' como abiertos para decidir si PROPONER cerrar un
#:  caso --'Closed' es lo unico afirmable--; aca la pregunta es otra, si se
#:  DESPACHA solo, y un caso rechazado o duplicado no (auditor de frontera,
#:  16/10). En produccion no habia ninguno el 25/09.
ABIERTOS_EN_DEXTER = ("New", "Assigned", "Pending")

#:  La puerta que frena un caso que ya no esta abierto. Va primera: un caso
#:  cerrado no tiene nada que despachar, digan lo que digan las reglas.
PUERTA_CASO = "caso"


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
        #  SIN MEDICION, a proposito: la medicion vive en la propuesta, no en
        #  la señal. Desde la Fase 3 el paso decide solo con lo guardado
        #  ('evaluar'); una falla que llegue por aca no pasa.


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
        confianza=str(ultima.get(CONFIANZA_DEL_GRUPO) or ""),
        medicion=ultima_medicion(propuesta))


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

    #  SE DECIDE CON LO GUARDADO  --  16/10/2026, Fase 3. Antes se probaba
    #  primero la señal; en produccion la fase le pasa siempre una vacia
    #  ('_SinSenal'), y la medicion que decide la regla 1 vive en la
    #  propuesta. Un segundo camino de decision que solo usaban las pruebas es
    #  una forma de tener verde lo que no corre. 'senal' queda en la firma
    #  porque el llamador la pasa; no se usa.
    d = evaluar(propuesta, ahora)

    #  PUERTA 0 · EL CASO SIGUE ABIERTO, y PUERTA 1 · LAS REGLAS.
    if not d.pasa:
        return {"paso": False, "porque": d.porque, "grupo": d.grupo,
                "puerta": d.puerta}

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
            nombre=NOMBRE_DEL_PASE,
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
    bloqueada para escribir.

    LAS REGLAS: su 'porque', que es texto fijo. Para una falla, desde la Fase 3
    ese 'porque' sale de la MEDICION del equipo y ya dice que hacer: preguntar
    si hay luz, si el equipo esta enchufado, o que el reclamo y la medicion se
    contradicen. Lo que se hacia hasta entonces --sumar la explicacion de la
    lectura, y cambiar "equipo sano" por '_FALLA_SIN_INTERPRETAR'-- se saco: la
    lectura vieja trae 'labor_verificada' en falso y la frase de equipo sano,
    y ese bloque habria tapado con texto viejo cada motivo medido.

    EL CASO NO ESTA ABIERTO: su 'porque', tambien texto fijo.

    SIN LECTURA TODAVIA: '_SIN_LECTURA', no el texto de 'de_la_propuesta', que
    supone una lectura guardada.

    UNA PUERTA DE LA EMPRESA: texto fijo, ver '_POR_QUE_LAS_PUERTAS'.

    NO PODER REGISTRAR LA ACEPTACION: nada. Es transitorio y la vuelta que
    viene lo reintenta; escribir "se queda para una persona" seria falso.
    """
    puerta = resultado.get("puerta") or PUERTA_REGLAS
    if puerta in _POR_QUE_LAS_PUERTAS:
        return _POR_QUE_LAS_PUERTAS[puerta]
    if puerta == PUERTA_CASO:
        return str(resultado.get("porque") or "el caso no esta abierto")
    if puerta != PUERTA_REGLAS:
        return None
    from operaciones import diagnostico_de_ticket as dxt

    if dxt.le_falta_lectura(propuesta):
        return _SIN_LECTURA
    return str(resultado.get("porque") or "sin motivo")


def motivo_para_el_registro(resultado: dict) -> str:
    """
    La clave con que el motivo se suma en la linea de log de la fase.

    Es el 'porque' tal cual, MENOS el de la puerta de la empresa: ese arrastra
    lo que una persona escribio al mover el interruptor, y ni el log ni el
    resultado de la tarea que guarda Celery tienen control de acceso. Va el
    mismo texto fijo que se escribe en la propuesta; el motivo libre se lee en
    /autonomia, que es donde se escribio. Las demas puertas llevan texto fijo
    y, a lo sumo, el tipo de una excepcion. Al de las reglas se le quita el
    nivel medido en dBm, que cambia de caso en caso.
    """
    if (resultado.get("puerta") or PUERTA_REGLAS) == PUERTA_EMPRESA:
        return _POR_QUE_LAS_PUERTAS[PUERTA_EMPRESA]
    #  SIN EL NIVEL MEDIDO  --  16/10/2026, Fase 3: con el dBm adentro, cada
    #  falla en rango abria su propia clave, y la linea dejaria de ser "claves
    #  y conteos". El nivel sigue en la propuesta, que es donde se lee un caso.
    return _SIN_NIVEL.sub("", str(resultado.get("porque") or "sin motivo"))


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


# =============================================================================
#  LA MEDICION Y EL CASO  --  16/10/2026, Fase 3
# =============================================================================

def ultima_medicion(propuesta) -> dict | None:
    """La pieza de medicion del equipo guardada en la propuesta, o None."""
    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE_MEDICION:
            return pieza
    return None


def por_que_el_caso_no_puede_pasar(caso, ahora) -> str | None:
    """
    Por que este caso no puede entrar a la cola de Despacho, o None si puede.

    Medido por el auditor de frontera el 16/10/2026: el paso aceptaba casos
    ya cerrados, en WispHub o en Dexter, y quedaban en la cola. Decidido por el
    usuario ese dia: un caso cerrado no pasa, y su propuesta se queda con el
    motivo escrito.

    MISMO VOCABULARIO QUE EL CIERRE Y LOS DETECTORES, para que el paso y el
    cierre no discrepen sobre el mismo caso: cerrado en Dexter es 'Closed' o
    'resolved_at' puesto ('cierre_de_caso'); en curso en WispHub es la LISTA
    BLANCA 'EN_CURSO_EN_PROVEEDOR', la misma que exige el detector para crear
    la señal; y la copia de WispHub vale mientras no pase 'HORAS_LECTURA_FRESCA'.

    FALLA CERRADO: una copia vieja, sin fecha o con error no dice que el
    ticket siga abierto, y entonces no pasa. Ese 72 mide justo esto, cuan
    fresca es la copia de WispHub. Texto fijo y sin numeros que cambien solos:
    un motivo que cambia cada hora se reescribiria cada vuelta.
    """
    from operaciones import supervisor as sup

    if caso is None:
        return "no se encontro el caso de esta propuesta: no se pasa"
    if not getattr(caso, "is_active", True) or getattr(caso, "merged_into_id", None):
        return "el caso esta inactivo o fusionado con otro: no se pasa"
    if caso.status == sup.CERRADO_EN_DEXTER or caso.resolved_at is not None:
        return "el caso ya esta cerrado en Dexter: no hay nada que despachar"
    if caso.status not in ABIERTOS_EN_DEXTER:
        return ("el caso no esta abierto en Dexter (rechazado o duplicado): "
                "no se pasa")
    if (getattr(caso, "external_fetch_error", "") or "").strip():
        return ("la ultima lectura del ticket en WispHub fallo: no se sabe si "
                "sigue abierto, asi que no se pasa")
    if caso.external_fetched_at is None:
        return ("no consta cuando se leyo el ticket en WispHub: no se sabe si "
                "sigue abierto, asi que no se pasa")
    horas = (ahora - caso.external_fetched_at).total_seconds() / 3600
    if horas > sup.HORAS_LECTURA_FRESCA:
        return (f"la copia del ticket de WispHub tiene mas de "
                f"{sup.HORAS_LECTURA_FRESCA} h sin actualizarse: no se sabe si "
                f"sigue abierto, asi que no se pasa")
    externo = sup._estado_externo(caso)
    if externo in sup.CERRADO_EN_PROVEEDOR:
        return "el ticket ya esta cerrado en WispHub: no hay nada que despachar"
    if externo not in sup.EN_CURSO_EN_PROVEEDOR:
        return ("el ticket no figura en curso en WispHub: no se sabe si sigue "
                "abierto, asi que no se pasa")
    return None


def caso_de(propuesta):
    """El caso de la propuesta, de la misma empresa, o None."""
    from cases.models import Case

    try:
        return (Case.objects
                .filter(pk=propuesta.origen_id, org_id=propuesta.org_id)
                .first())
    except Exception:                                            # noqa: BLE001
        #  Un 'origen_id' que no es un id valido no es un caso.
        return None


def evaluar(propuesta, ahora) -> Decision:
    """
    La decision completa con lo guardado: primero el caso, despues las reglas.

    No llama a nada por red ni escribe: la usan la fase de paso y la rama del
    tope, que solo decide. Un caso cerrado no cuenta como "espera el tope".
    """
    porque = por_que_el_caso_no_puede_pasar(caso_de(propuesta), ahora)
    if porque:
        lectura = _ultima_lectura_con_grupo(propuesta) or {}
        return Decision(False, porque, grupo=str(lectura.get("grupo") or ""),
                        puerta=PUERTA_CASO)
    return de_la_propuesta(propuesta)
