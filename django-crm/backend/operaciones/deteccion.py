# -*- coding: utf-8 -*-
"""
================================================================================
 DETECCION  --  del dato crudo a una señal que no confunde creer con saber
================================================================================

QUE HACE
--------
Toma la ultima captura de una fuente y produce señales ESTRUCTURADAS. Cada señal
mantiene separadas seis cosas que normalmente se dicen juntas:

    HECHO           12 ONT presentan caida
    RELACION        las 12 pertenecen al mismo PON 3/1/4
    INTERPRETACION  hay concentracion topologica y temporal
    RIESGO          posible afectacion comun
    HIPOTESIS       posible falla del PON
    RECOMENDACION   verificar el PON y su evolucion

POR QUE ESTA SEPARACION ES EL PUNTO DEL MODULO
----------------------------------------------
Porque "12 ONT caidas en el mismo PON" es un HECHO y "el PON esta fallado" es una
HIPOTESIS, y si las dos llegan en la misma frase nadie distingue cual se midio.
El proyecto ya tiene la cicatriz: una respuesta que afirma con el mismo tono lo
que verifico y lo que supuso es exactamente como un diagnostico confiado termina
equivocado.

Asi que la hipotesis viaja en su propio campo, con su CONFIANZA al lado, y una
señal puede perfectamente no tener hipotesis -- que es el caso honesto mas comun
al principio.

LO QUE ESTE MODULO NO HACE
--------------------------
No escribe. No crea situaciones, no las actualiza y no toca la base: devuelve
objetos en memoria. Quien decide que hacer con ellos es 'correlacion.py'.
Separarlo permite probar la lectura del dato sin tener que crear situaciones, y
--mas importante-- permite ver si un error esta en lo que se leyo o en lo que se
concluyo.

Tampoco inventa. Si la captura no alcanza para saber que esta afectado, la señal
lo dice con 'datos_insuficientes' en vez de dejar la lista vacia: una lista vacia
se lee como "nada afectado".
================================================================================
"""

from __future__ import annotations

from operaciones.fuentes_modelos import EstadoLectura, Fuente, Frescura
from operaciones.situaciones_modelos import (Confianza, Riesgo, SituacionOperativa,
                                             TipoAfectado)

#  Desde cuantos afectados en un mismo PON se considera que hay concentracion.
#  DOS, y no un numero mas alto: un solo abonado caido es un problema de ese
#  abonado; dos del mismo puerto ya es una coincidencia que vale mirar. Subirlo
#  haria perder justamente las afectaciones chicas, que son las que nadie nota.
MINIMO_PARA_CONCENTRACION = 2

#  A partir de que porcentaje del PON afectado el riesgo sube. Son umbrales de
#  PRESENTACION --cuanto preocupa-- y no de deteccion: la señal se emite igual.
PORCENTAJE_RIESGO_ALTO = 50.0
PORCENTAJE_RIESGO_MEDIO = 20.0


class Senal:
    """
    Una señal estructurada. Seis campos que no se mezclan, y su dimension.

    'dimension' y 'clave_dimension' son lo que la correlacion usa para agrupar:
    ('pon', '3/1/4'). Viajan aqui porque quien lee el dato sabe de que topologia
    esta hablando; hacer que la correlacion lo deduzca de un texto seria pedirle
    que parsee lo que este modulo ya sabe.
    """

    __slots__ = ("fuente", "tipo_situacion", "dimension", "clave_dimension",
                 "hecho", "relacion", "interpretacion", "riesgo", "hipotesis",
                 "confianza", "recomendacion", "afectados", "evidencia",
                 "observada_en", "concluyente", "datos")

    def __init__(self, *, fuente, tipo_situacion, dimension, clave_dimension,
                 hecho, relacion="", interpretacion="", riesgo=Riesgo.INFORMATIVO,
                 hipotesis="", confianza=Confianza.SIN_HIPOTESIS,
                 recomendacion="", afectados=None, evidencia=None,
                 observada_en=None, concluyente=True, datos=None):
        if riesgo not in Riesgo.TODOS:
            raise ValueError(f"riesgo desconocido: {riesgo!r}")
        if confianza not in Confianza.TODAS:
            raise ValueError(f"confianza desconocida: {confianza!r}")
        #  La regla que no se puede romper: una hipotesis SIEMPRE viaja con su
        #  confianza, y una confianza declarada SIEMPRE con su hipotesis. Las dos
        #  formas de violarlo son las dos formas de presentar una sospecha como
        #  un hecho.
        if bool(hipotesis) != (confianza != Confianza.SIN_HIPOTESIS):
            raise ValueError(
                "una hipotesis necesita su confianza, y una confianza declarada "
                "necesita su hipotesis: sin las dos, una sospecha se lee como un "
                "hecho")
        self.fuente = fuente
        self.tipo_situacion = tipo_situacion
        self.dimension = dimension
        self.clave_dimension = clave_dimension
        self.hecho = hecho
        self.relacion = relacion
        self.interpretacion = interpretacion
        self.riesgo = riesgo
        self.hipotesis = hipotesis
        self.confianza = confianza
        self.recomendacion = recomendacion
        self.afectados = afectados or []
        self.evidencia = evidencia or []
        self.observada_en = observada_en
        #  Si de esta señal se puede concluir algo. Una señal de una fuente
        #  INCONCLUSA viaja igual --para que quede registrada-- pero marcada.
        self.concluyente = concluyente
        self.datos = datos or {}

    @property
    def huella(self) -> str:
        """
        La clave DETERMINISTICA de la situacion que esta señal describe.

        Dos ciclos que ven la misma anomalia producen la misma huella, y eso es
        lo que permite que la base --con su indice unico parcial-- impida la
        situacion gemela. Incluye el tipo: una caida de PON y una de OLT sobre la
        misma topologia no son la misma situacion.
        """
        return f"{self.tipo_situacion}|{self.dimension}:{self.clave_dimension}"

    def __repr__(self):
        return f"<Senal {self.huella} afectados={len(self.afectados)}>"


def _afectado(tipo, identificador, *, etiqueta="", datos=None) -> dict:
    return {"tipo": tipo, "identificador": str(identificador),
            "etiqueta": etiqueta, "datos": datos or {}}


def _observacion(fuente, dato, momento) -> dict:
    """Un HECHO con su procedencia. Sin fuente, una evidencia no es evidencia."""
    return {"fuente": fuente, "dato": dato,
            "observado_en": momento.isoformat() if momento else None}


# =============================================================================
#  SMARTOLT  --  la unica fuente que ve antes de que haya tickets
# =============================================================================

def desde_smartolt(snapshot, ahora) -> list[Senal]:
    """
    Una señal por PON con afectados. Es el caso del ejemplo del bloque.

    POR QUE NO SE EMITE NADA CUANDO LA LECTURA NO CONCLUYE, SALVO LA MARCA
    ---------------------------------------------------------------------
    Si la captura es ERROR o NO_DISPONIBLE no hay nada que interpretar, y emitir
    una señal "sin afectados" seria afirmar que la red esta sana justo cuando no
    se la pudo mirar. Se devuelve vacio y el estado de la fuente ya lo dice.

    INCONCLUSA es distinto: ahi SI hubo respuesta, solo que dentro de la ventana
    de 2 a 5 minutos en la que el proveedor todavia no agrupo. Esa se propaga como
    una señal marcada 'concluyente=False', para que una situacion viva pueda
    anotar "la fuente no concluye" en su timeline en vez de interpretar el vacio
    como recuperacion.
    """
    if snapshot is None:
        return []
    if snapshot.estado in (EstadoLectura.ERROR, EstadoLectura.NO_DISPONIBLE,
                           EstadoLectura.NO_CONSULTADA):
        return []

    if snapshot.estado == EstadoLectura.INCONCLUSA:
        #  Una sola señal, sin dimension topologica: no describe un PON, describe
        #  el estado de la fuente. 'correlacion' la usa para NO cerrar nada.
        return [Senal(
            fuente=Fuente.SMARTOLT,
            tipo_situacion=SituacionOperativa.OTRA,
            dimension="fuente", clave_dimension=Fuente.SMARTOLT,
            hecho=("SmartOLT contesto sin agrupaciones activas, dentro de la "
                   "ventana en la que su agrupacion todavia no refleja una "
                   "caida reciente"),
            interpretacion=("un vacio en esta ventana no prueba que la red este "
                            "sana: el proveedor agrupa con 2 a 5 minutos de "
                            "retraso"),
            riesgo=Riesgo.INFORMATIVO,
            recomendacion="volver a consultar en el proximo ciclo",
            evidencia=[_observacion(Fuente.SMARTOLT, "respuesta inconclusa",
                                    snapshot.capturado_en)],
            observada_en=snapshot.dato_en or snapshot.capturado_en,
            concluyente=False)]

    datos = snapshot.datos if isinstance(snapshot.datos, dict) else {}
    senales: list[Senal] = []

    for clave, fila in sorted(datos.items()):
        #  Las claves que empiezan con '_' son metadatos del resumen, no PONs.
        if clave.startswith("_") or not isinstance(fila, dict):
            continue
        afectados_n = fila.get("afectados")
        if not isinstance(afectados_n, int) or afectados_n <= 0:
            continue

        abonados = fila.get("abonados")
        porcentaje = fila.get("porcentaje_afectado")
        tipo_alerta = str(fila.get("tipo") or "sin_tipo")
        caja = str(fila.get("caja") or "")

        #  --- HECHO: lo que la fuente dice, sin adjetivos ------------------
        hecho = f"{afectados_n} ONT afectadas en el PON {clave}"
        if isinstance(abonados, int) and abonados > 0:
            hecho += f", de {abonados} abonados del puerto"

        #  --- RELACION: por que estas estan juntas -------------------------
        relacion = f"las {afectados_n} pertenecen al mismo puerto PON {clave}"
        if caja:
            relacion += f" (caja {caja})"

        #  --- INTERPRETACION y RIESGO --------------------------------------
        concentracion = afectados_n >= MINIMO_PARA_CONCENTRACION
        if concentracion:
            interpretacion = ("hay concentracion topologica: los afectados "
                              "comparten puerto, no estan dispersos")
            riesgo = _riesgo_de(afectados_n, porcentaje)
        else:
            interpretacion = ("un solo afectado en el puerto: no hay "
                              "concentracion que sugiera una causa comun")
            riesgo = Riesgo.BAJO

        #  --- HIPOTESIS: solo si la concentracion la sostiene --------------
        #  Con un unico afectado NO se emite hipotesis. Decir "posible falla del
        #  PON" por una ONT caida seria exactamente convertir una sospecha
        #  debil en una afirmacion.
        if concentracion:
            hipotesis = _hipotesis_de(tipo_alerta, clave)
            confianza = _confianza_de(afectados_n, porcentaje)
        else:
            hipotesis, confianza = "", Confianza.SIN_HIPOTESIS

        afectados = [_afectado(TipoAfectado.PON, clave, etiqueta=caja,
                               datos={"afectados": afectados_n,
                                      "abonados": abonados,
                                      "tipo_alerta": tipo_alerta})]
        #  La OLT tambien queda registrada como afectada: es el primer segmento
        #  de la clave 'olt/board/port', y permite correlacionar por OLT sin
        #  volver a parsear nada.
        olt = clave.split("/")[0] if "/" in clave else ""
        if olt and olt != "?":
            afectados.append(_afectado(TipoAfectado.OLT, olt))

        #  LAS ONT INDIVIDUALES NO SE INVENTAN. 'get_outage_pons' agrupa y NO
        #  devuelve los seriales; saber cuales son exige otra llamada. Se
        #  registra que hay N afectadas sin identificar, en vez de dejar la
        #  insuficiencia fuera del registro.
        afectados.append(_afectado(
            TipoAfectado.DATOS_INSUFICIENTES, "datos_insuficientes",
            etiqueta=f"{afectados_n} ONT sin identificar",
            datos={"cuantas": afectados_n,
                   "porque": "get_outage_pons agrupa por PON y no devuelve los "
                             "seriales de cada ONT"}))

        senales.append(Senal(
            fuente=Fuente.SMARTOLT,
            tipo_situacion=SituacionOperativa.AFECTACION_PON,
            dimension="pon", clave_dimension=clave,
            hecho=hecho, relacion=relacion, interpretacion=interpretacion,
            riesgo=riesgo, hipotesis=hipotesis, confianza=confianza,
            recomendacion=("verificar el PON y como evoluciona en los proximos "
                           "ciclos" if concentracion else
                           "seguir el caso del abonado afectado"),
            afectados=afectados,
            evidencia=[_observacion(Fuente.SMARTOLT, hecho,
                                    snapshot.dato_en or snapshot.capturado_en)],
            observada_en=snapshot.dato_en or snapshot.capturado_en,
            #  Una captura con dato VIEJO describe el pasado. La señal viaja para
            #  que quede registrada, marcada como no concluyente.
            concluyente=(snapshot.frescura != Frescura.VIEJA),
            datos={"afectados": afectados_n, "abonados": abonados,
                   "porcentaje": porcentaje, "tipo_alerta": tipo_alerta}))

    return senales


def _riesgo_de(afectados: int, porcentaje) -> str:
    """Cuanto preocupa. El porcentaje manda sobre el conteo cuando se conoce."""
    if isinstance(porcentaje, (int, float)) and not isinstance(porcentaje, bool):
        if porcentaje >= PORCENTAJE_RIESGO_ALTO:
            return Riesgo.CRITICO
        if porcentaje >= PORCENTAJE_RIESGO_MEDIO:
            return Riesgo.ALTO
    #  Sin porcentaje se usa el conteo, que es mas grueso: 10 afectados en un
    #  puerto de 15 y en uno de 120 no son lo mismo, y sin el denominador no se
    #  puede distinguir. Se elige el lado prudente.
    if afectados >= 10:
        return Riesgo.ALTO
    if afectados >= MINIMO_PARA_CONCENTRACION:
        return Riesgo.MEDIO
    return Riesgo.BAJO


def _hipotesis_de(tipo_alerta: str, pon: str) -> str:
    """
    La explicacion posible, segun QUE tipo de alerta agrupo SmartOLT.

    Los tipos vienen del proveedor y significan cosas distintas: 'power' es un
    corte de energia --una causa que no esta en la red-- y 'los' es perdida de
    señal optica. Darles la misma hipotesis mandaria a revisar la fibra cuando se
    fue la luz del barrio.
    """
    if tipo_alerta == "power":
        return (f"posible corte de energia en la zona del PON {pon}: la "
                f"agrupacion es por perdida de alimentacion, no por señal "
                f"optica")
    if tipo_alerta in ("los", "partial_los"):
        return (f"posible falla optica en el PON {pon} (fibra, empalme o caja): "
                f"la agrupacion es por perdida de señal")
    if tipo_alerta == "offline":
        return (f"posible afectacion comun en el PON {pon}: los equipos estan "
                f"fuera de linea sin que la causa este clasificada")
    return f"posible afectacion comun en el PON {pon}"


def _confianza_de(afectados: int, porcentaje) -> str:
    """
    Que tan sostenida esta la hipotesis. NO es la gravedad.

    Mas afectados del mismo puerto hacen la coincidencia menos casual, y por eso
    suben la confianza. Nunca llega a ALTA desde aqui: una afirmacion de causa
    sobre la red necesita algo mas que una concentracion -- una verificacion en
    campo, o un patron repetido-- y eso no lo tiene este modulo.
    """
    if isinstance(porcentaje, (int, float)) and not isinstance(porcentaje, bool) \
            and porcentaje >= PORCENTAJE_RIESGO_ALTO:
        return Confianza.MEDIA
    if afectados >= 10:
        return Confianza.MEDIA
    return Confianza.BAJA


# =============================================================================
#  LAS DEMAS FUENTES
# =============================================================================

def desde_dexter(snapshot, ahora) -> list[Senal]:
    """
    Los casos abiertos no generan situaciones por si solos, y es deliberado.

    Un caso abierto es un cliente con un problema -- que es el trabajo normal del
    ISP, no una anomalia. Convertir "hay 40 casos abiertos" en una situacion
    produciria una situacion permanente que nadie puede cerrar.

    Lo que SI hace esta fuente es aportar TICKETS para asociar a situaciones que
    ya existen (ver 'correlacion.asociar_tickets'): el ticket llega despues como
    evidencia de una caida que la red ya mostro. Por eso devuelve vacio y no es un
    hueco.
    """
    return []


def desde_sla(snapshot, ahora) -> list[Senal]:
    """
    Igual que Dexter: el riesgo de plazo de una orden es de ESA orden.

    M04 ya emite señales de SLA por orden y las convierte en propuestas; duplicar
    eso aqui crearia dos caminos para la misma afirmacion. Si en algun momento
    varias ordenes vencidas de la misma zona deben verse como UNA situacion, esa
    es una regla de correlacion por zona y se decide con datos -- hoy M03 esta
    vacio en produccion y no hay con que medirla.
    """
    return []


def desde_m02(snapshot, ahora) -> list[Senal]:
    """Sin señales propias: las actividades son trabajo asignado, no anomalias."""
    return []


def desde_m03(snapshot, ahora) -> list[Senal]:
    """Sin señales propias por el mismo motivo que SLA."""
    return []


def desde_wisphub(snapshot, ahora) -> list[Senal]:
    """
    Los tickets de WispHub tampoco crean situaciones, y esto es lo central
    del diseño del bloque: los tickets NO son el origen de una situacion.

    Un pico de tickets podria sugerir una afectacion, pero decidirlo asi
    invertiria el orden que el Supervisor viene a arreglar -- detectar DESPUES del
    reclamo. Los tickets entran como evidencia de situaciones existentes.
    """
    return []


POR_FUENTE = {
    Fuente.SMARTOLT: desde_smartolt,
    Fuente.WISPHUB: desde_wisphub,
    Fuente.DEXTER: desde_dexter,
    Fuente.SLA: desde_sla,
    Fuente.M02: desde_m02,
    Fuente.M03: desde_m03,
}


def detectar(org, *, ahora=None, fuentes_a_mirar=None) -> list[Senal]:
    """
    Las señales que salen de la ULTIMA captura de cada fuente.

    Lee; no escribe. Y una fuente que revienta no se lleva a las demas, por el
    mismo motivo que en el sondeo: cinco fuentes mudas por culpa de una, sin que
    nada lo explique, es peor que una fuente en rojo.
    """
    from django.utils import timezone

    from operaciones import fuentes as capa_fuentes

    ahora = ahora or timezone.now()
    senales: list[Senal] = []
    for nombre in (fuentes_a_mirar or Fuente.TODAS):
        traductor = POR_FUENTE.get(nombre)
        if traductor is None:
            continue
        snap = capa_fuentes.ultimo_snapshot(org, nombre)
        if snap is None:
            continue
        senales.extend(traductor(snap, ahora))
    return senales
