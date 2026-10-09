# -*- coding: utf-8 -*-
"""
================================================================================
 DE QUE TIPO ES ESTE TRABAJO  --  lo dice la prueba, no el texto del ticket
================================================================================

QUE DECIDE Y QUE NO
-------------------
Decide una LABOR --instalacion, correctivo o trabajos-- y por que. No elige la
plantilla: eso depende del catalogo de cada empresa (`WorkType.labor`), y entre
dos plantillas de la misma labor la diferencia la sabe quien despacha, no esto.

Y NO EJECUTA. Devuelve una propuesta con su evidencia escrita; una persona la
acepta o la cambia al despachar. Es el mismo corte que el resto del Supervisor
NOC: observa, analiza, propone.

EL ORDEN DE LAS FUENTES, Y POR QUE ESE
--------------------------------------
    1. ¿es una instalacion?        lo dice el proveedor, no se prueba nada
    2. ¿hay una falla AGRUPADA?    varios del mismo PON: es un trabajo de red
    3. ¿que dice la prueba?        el estado real del equipo
    4. ¿que dice el texto?         solo si lo anterior no concluyo, y MARCADO

LA PRUEBA MANDA SOBRE EL TEXTO, pero sobre una pregunta acotada: si esto es o
no una falla de red. Un equipo sano NO significa "no hay trabajo" -- el cliente
puede estar pidiendo una reubicacion o un cambio de equipo. Significa que no es
un correctivo de red, y ahi el texto es la unica fuente que queda.

Tratar "equipo sano" como "no hay nada que hacer" cerraria trabajos reales.

POR QUE LA INSTALACION NO SE PRUEBA
-----------------------------------
Una instalacion nueva no tiene ONT todavia, asi que no hay nada que medir en
SmartOLT. Y el atajo obvio --"si SmartOLT no lo conoce, es instalacion"-- NO
sirve, con numero: 1.299 de 4.163 clientes ACTIVOS de Rapilink no tienen
`sn_onu` cargado (medido, ver la skill `wisphub-api`). Un tercio. La ausencia
no distingue una instalacion de un cliente viejo sin serial.

Por eso la instalacion se pregunta primero y por otro lado. El dato que SI la
distingue --medido el 08/10/2026-- es que el ticket cuelgue del cliente
ficticio "INSTALACIONES NUEVAS" del proveedor: 220 de 220, contra 23 de 220
del asunto. Y mientras ese dato no venga, esto NO afirma nada.

SIN ENERGIA NO ES UN TRABAJO
----------------------------
Si el equipo esta caido por falta de energia (dying-gasp), el problema es un
corte de luz en la casa del cliente. Mandar una cuadrilla ahi es mandarla a
mirar como alguien espera que vuelva la luz. Se dice, y no se propone visita.

La asimetria importa y ya esta escrita en `diagnostico_optico`: el dying-gasp
es de MEJOR ESFUERZO --la ONU lo manda si llega a hacerlo-- asi que su AUSENCIA
no prueba nada. Por eso solo el dying-gasp presente descarta la visita; un LOS
sin mas no.
"""

from __future__ import annotations

from operaciones import diagnostico_optico as optico

#: Las labores. Son las mismas de `campo.models.WorkType.LABORES` y de
#: `JornadaDeCuadrilla.LABORES`: un cuarto catalogo con los mismos valores se
#: separaria en silencio del dia que alguien agregue una.
INSTALACION = "instalacion"
CORRECTIVO = "correctivo"
TRABAJOS = "trabajos"

#: Cuando no se puede concluir. NO es una labor: es la ausencia de una, y se
#: nombra distinto para que nadie la trate como una cuarta opcion.
SIN_CONCLUIR = ""

#: Cuando la prueba dice que no hace falta ir.
NO_REQUIERE_VISITA = "no_requiere_visita"

#: De donde salio la conclusion. Viaja con la propuesta porque "correctivo"
#: sin su fuente no se puede discutir: quien despacha necesita saber si eso lo
#: dijo una medicion o el asunto de un ticket.
POR_PRUEBA = "prueba"
POR_FALLA_AGRUPADA = "falla_agrupada"
POR_TEXTO = "texto"
POR_PROVEEDOR = "proveedor"


def _veredicto(labor, porque, fuente, *, verificada):
    """La forma unica de salida.

    `verificada` dice si esto se APOYA EN UNA MEDICION o en un texto. No es
    cosmetico: una orden clasificada por texto puede encontrarse otra cosa en
    el sitio, y el tecnico tiene que poder saberlo antes de cargar el kit.
    """
    return {
        "labor": labor,
        "porque": porque,
        "fuente": fuente,
        "verificada": verificada,
    }


def _de_la_prueba(equipo: dict) -> dict | None:
    """Lo que el estado real del equipo permite afirmar, o None si no alcanza.

    Se apoya en el vocabulario de `diagnostico_optico` --mismos estados, misma
    causa-- en vez de redefinirlo: dos tablas con los mismos valores se separan
    el dia que una cambie.
    """
    if not isinstance(equipo, dict) or not equipo:
        return None

    estado = str(equipo.get("estado") or "")
    senal = str(equipo.get("senal") or "")
    causa = str(equipo.get("causa_caida") or "")
    dbm = equipo.get("senal_dbm")
    nivel = f" ({dbm} dBm)" if dbm is not None else ""

    if estado not in (optico.EN_LINEA, optico.CAIDO):
        return None

    #  SIN ENERGIA: la casa del cliente, no la red. No se manda a nadie.
    if estado == optico.CAIDO and causa == optico.CAUSA_SIN_ENERGIA:
        return _veredicto(
            NO_REQUIERE_VISITA,
            "el equipo esta caido y el proveedor reporto falta de energia "
            "(dying-gasp): es un corte de luz en el domicilio. Una visita no "
            "resuelve eso.",
            POR_PRUEBA, verificada=True)

    #  FIBRA: LOS/LOF. Es de la red, y es nuestro.
    if estado == optico.CAIDO and causa == optico.CAUSA_FIBRA:
        return _veredicto(
            CORRECTIVO,
            "el equipo esta caido por perdida de señal optica (LOS/LOF): la "
            "falla es de la red.",
            POR_PRUEBA, verificada=True)

    if estado == optico.CAIDO:
        #  Caido por algo que este codigo no sabe distinguir. Que este caido ya
        #  es suficiente para mandar un correctivo --hay un cliente sin
        #  servicio-- pero la causa NO se afirma.
        return _veredicto(
            CORRECTIVO,
            f"el equipo esta caido. La causa que reporto el proveedor "
            f"({causa or 'ninguna'}) no es una de las que se saben distinguir, "
            f"asi que no se afirma por que.",
            POR_PRUEBA, verificada=True)

    if senal == optico.SENAL_DEBIL:
        return _veredicto(
            CORRECTIVO,
            f"el equipo esta en linea pero la señal de bajada es debil{nivel}: "
            f"va a volver a fallar.",
            POR_PRUEBA, verificada=True)

    #  EN LINEA Y SANO. Esto NO cierra el caso: el cliente puede estar pidiendo
    #  otra cosa. Lo unico que queda probado es que NO es una falla de red.
    if senal == optico.SENAL_BUENA:
        return None

    #  En linea sin lectura de señal: no alcanza para afirmar nada.
    return None


def _de_la_falla_agrupada(situacion: dict | None) -> dict | None:
    """Varios clientes del mismo puerto: un trabajo de red, no N correctivos.

    GANA SOBRE EL CORRECTIVO INDIVIDUAL. Si cinco clientes de la misma NAP
    estan caidos, cinco ordenes mandan cinco cuadrillas al mismo poste -- y la
    quinta llega cuando ya esta arreglado.

    `correlacion.py` es quien agrupa, y afirma que COINCIDEN (mismo PON, misma
    ventana), nunca que una cosa causa la otra. Esto respeta esa distincion: no
    dice "la NAP esta rota", dice "hay N afectados del mismo puerto".
    """
    if not isinstance(situacion, dict) or not situacion:
        return None
    afectados = situacion.get("afectados")
    if not isinstance(afectados, int) or afectados < 2:
        return None

    donde = situacion.get("etiqueta") or situacion.get("pon") or "el mismo puerto"
    return _veredicto(
        TRABAJOS,
        f"hay {afectados} clientes afectados en {donde}, en la misma ventana. "
        f"Es un trabajo de red: una sola cuadrilla, no una visita por cliente.",
        POR_FALLA_AGRUPADA, verificada=True)


def _del_proveedor(contexto: dict, marcadores: dict | None) -> dict | None:
    """Si el proveedor dice que esto es una instalacion.

    LA HIPOTESIS OBVIA ERA FALSA, y se midio el 08/10/2026 contra la API real:
    `estado_instalacion` **no existe** en `/api/clientes/` --ni en la lista (54
    campos) ni en el detalle (34)-- y como filtro se IGNORA en silencio:
    devuelve los 7.451 clientes igual que un parametro inventado. La propia
    skill lo documentaba al reves, porque `?instalacion` habilita esos campos
    para ESCRIBIR, no para leer.

    LO QUE SI FUNCIONA, y con mejor numero: los tickets de instalacion cuelgan
    de un CLIENTE FICTICIO del proveedor ("INSTALACIONES NUEVAS"), cuyo id vive
    en la config del tenant (`WISPHUB_ID_SERVICIO_INSTALACIONES`), nunca fijo
    aca. Medido sobre 3.418 tickets reales:

        por `id_servicio`   220 de 220   100%
        por el ASUNTO        23 de 220    10%

    Los otros 202 usan el NOMBRE Y EL BARRIO del prospecto como asunto, asi
    que el texto --que parecia el camino obvio-- es el peor discriminador
    disponible justo para este tipo.

    Hay una segunda via, tambien medida: una instalacion no existe en
    `/api/clientes/` (`?id_servicio=` da count 0 y el detalle da 404) y si en
    `/api/instalaciones/`. Es una prueba POSITIVA --aparece en un lado y no en
    el otro-- a diferencia de "no aparece en SmartOLT", que no prueba nada.
    """
    if not isinstance(marcadores, dict) or not marcadores:
        return None

    #  1 · El cliente ficticio del proveedor. Es el discriminador fuerte.
    ficticio = str(marcadores.get("id_servicio_instalaciones") or "").strip()
    servicio = str((contexto or {}).get("servicio") or "").strip()
    if ficticio and servicio and servicio == ficticio:
        return _veredicto(
            INSTALACION,
            "el ticket cuelga del cliente de instalaciones nuevas del "
            "proveedor: es una instalacion, y todavia no hay equipo que medir.",
            POR_PROVEEDOR, verificada=True)

    #  2 · Esta en el padron de instalaciones y no en el de clientes.
    #
    #  Se exige que la respuesta VENGA. Un `None` no es "no es instalacion":
    #  es "no se pudo preguntar", y son cosas distintas -- la misma razon por
    #  la que la ausencia en SmartOLT no prueba nada.
    en_instalaciones = marcadores.get("en_padron_de_instalaciones")
    if en_instalaciones is True:
        estado = marcadores.get("estado_instalacion")
        detalle = f" (estado {estado})" if estado not in (None, "", 0) else ""
        return _veredicto(
            INSTALACION,
            f"el proveedor lo tiene en su padron de instalaciones{detalle} y "
            f"no entre sus clientes: el servicio todavia no esta activo.",
            POR_PROVEEDOR, verificada=True)
    return None


def _del_texto(texto: str, mapa: dict | None) -> dict | None:
    """La ultima fuente, y la unica que NO queda verificada.

    El mapa lo declara la empresa --mismo patron que `importacion_tickets`
    traduce asunto a area-- porque ningun texto dice por si solo a que labor
    corresponde: 'soporte' en una empresa puede ser lo que en otra es
    'mantenimiento'.

    Se busca por SUBCADENA y en minusculas, y la clave mas larga gana: con
    'instalacion' y 'instalacion de camara' mapeadas a labores distintas, la
    especifica tiene que ganarle a la generica, y el orden de un dict no puede
    decidir eso.
    """
    if not texto or not isinstance(mapa, dict) or not mapa:
        return None

    plano = " ".join(str(texto).lower().split())
    mejor, clave = None, ""
    for patron, labor in mapa.items():
        p = str(patron or "").lower().strip()
        if p and p in plano and len(p) > len(clave):
            mejor, clave = labor, p
    if not mejor:
        return None

    return _veredicto(
        mejor,
        f"ninguna medicion concluyo, y el texto del caso contiene '{clave}', "
        f"que esta declarado como '{mejor}'. NO esta verificado contra el "
        f"equipo: puede encontrarse otra cosa en el sitio.",
        POR_TEXTO, verificada=False)


def clasificar(contexto: dict, *, texto: str = "", mapa_de_texto=None,
               situacion=None, marcadores=None) -> dict:
    """De que tipo es este trabajo, y por que.

    `contexto` es el snapshot que `campo.services.despacho.contexto_del_caso`
    ya arma: trae `equipo` (de SmartOLT), `cliente` y `ticket`. Se reusa en vez
    de salir a preguntar de nuevo -- y ademas Django NO habla con WispHub ni
    SmartOLT a proposito, eso es del motor.

    Devuelve SIEMPRE la misma forma, incluso cuando no concluye: quien lo use
    no tiene que distinguir entre "no hay respuesta" y "hay respuesta vacia".
    """
    contexto = contexto if isinstance(contexto, dict) else {}

    #  1 · EL PROVEEDOR PRIMERO. Una instalacion no tiene equipo que medir, y
    #     preguntarle a SmartOLT por ella devolveria "no existe" -- que no
    #     prueba nada (ver el encabezado: 1.299 de 4.163 activos tampoco).
    por_proveedor = _del_proveedor(contexto, marcadores)
    if por_proveedor:
        return por_proveedor

    #  2 · LA FALLA AGRUPADA LE GANA AL CORRECTIVO INDIVIDUAL.
    agrupada = _de_la_falla_agrupada(situacion)
    if agrupada:
        return agrupada

    #  3 · LA PRUEBA.
    prueba = _de_la_prueba(contexto.get("equipo") or {})
    if prueba:
        return prueba

    #  4 · EL TEXTO, y queda marcado como no verificado.
    por_texto = _del_texto(texto, mapa_de_texto)
    if por_texto:
        return por_texto

    #  NO SE CONCLUYE, y se dice por que no se pudo -- no es lo mismo "el
    #  equipo esta sano" que "no se pudo medir".
    sin_equipo = contexto.get("equipo_no_disponible")
    if not contexto.get("contexto_disponible"):
        motivo = ("no se pudo traer la ficha tecnica del caso, asi que no hubo "
                  "nada que medir")
    elif sin_equipo:
        motivo = f"no se pudo leer el equipo ({sin_equipo})"
    elif contexto.get("equipo"):
        motivo = ("el equipo esta en linea y sano, asi que esto NO es una "
                  "falla de red. Que tipo de trabajo es lo decide quien "
                  "despacha")
    else:
        motivo = "no hay datos del equipo ni texto declarado para este caso"

    return _veredicto(SIN_CONCLUIR, motivo, "", verificada=False)
