# -*- coding: utf-8 -*-
"""
================================================================================
 LA AUTONOMIA SE GANA CON EVIDENCIA  --  31/10/2026 (PRD §2, §8.17 Ola 3)
================================================================================

Una accion pasa de "una persona aprueba" a "la IA ejecuta" SOLO si cumple las
cuatro condiciones del PRD §2. Este modulo calcula las tres primeras, por
empresa y por accion, y lo dice con sus numeros. NO ejecuta nada ni cambia
ningun permiso: subir lo decide una persona viendo esto; bajar, el codigo.

  1. EFECTO VERIFICABLE EN CODIGO: la herramienta declara 'verificacion' con
     comprobaciones (reiniciar_ont mide 'last_status_change'). Sin eso, nunca:
     'registrar_pago' no tiene como medirse y queda afuera POR CONSTRUCCION,
     no por estar en una lista con su nombre (el nucleo no conoce nombres).
  2. PRECONDICIONES EN CODIGO: declara 'exige_previas', sobre datos medidos.
  3. EVIDENCIA EN ESTA EMPRESA, en la ventana: un minimo de propuestas que
     una persona reviso, una tasa de aprobacion por encima del umbral, CERO
     verificaciones no confirmadas y CERO ejecuciones fallidas.

  4. (DEGRADACION SOLA) vive donde se ejecuta: Fases C y D.

FASE B (31/10/2026): una persona promueve, con la evidencia medida en ese
momento; una persona retira; el estado vigente se lee sin cache y falla
cerrado. La tabla es de solo agregar (supabase/202610310200_autonomia_ganada.sql).

EL PISO
-------
Cada empresa elige sus umbrales ('autonomia_ganada' en su config), pero nunca
por debajo del piso del nucleo: ninguna empresa puede ganar autonomia con
cinco casos revisados o con una de cada cinco rechazada. Cero no confirmadas
y cero fallidas no se configuran: un solo reinicio que no reinicio es razon
suficiente para que una persona siga mirando.

El modelo no cuenta nada (PRD §12.5): los numeros salen de SQL y la regla de
aca.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

#: El piso del nucleo: lo menos que puede pedir una empresa.
#: Las confirmaciones (31/10/2026, auditor de frontera): aprobar no prueba que
#: el efecto ocurra. Se exige ademas un minimo de verificaciones CONFIRMADAS y
#: una tasa de confirmacion sobre las que se pudieron medir -- una
#: NO_VERIFICABLE cuenta en contra: sin verificacion posible, una persona.
PISO = {"minimo_revisadas": 20, "ventana_dias": 14, "tasa_minima_aprobacion": 0.90,
        "minimo_confirmadas": 10, "tasa_minima_confirmacion": 0.90}
#: Lo que se pide si la empresa no dijo nada: mas que el piso.
POR_DEFECTO = {"minimo_revisadas": 30, "ventana_dias": 30, "tasa_minima_aprobacion": 0.95,
               "minimo_confirmadas": 20, "tasa_minima_confirmacion": 0.95}
#: De los efectos ejecutados en la ventana, que parte se pudo MEDIR (confirmada,
#: no confirmada o no verificable) frente a los que siguen pendientes. Con
#: menos, la tasa de confirmacion se calcula sobre una minoria y no dice nada.
PROPORCION_MINIMA_MEDIDA = 0.80
#: Cuantas verificaciones sin resolver (con mas de HORAS_SIN_RESOLVER) frenan
#: la autonomia y la degradan: una verificacion se resuelve cuando el cliente
#: vuelve a escribir, y un reinicio que nadie mide no es evidencia de nada.
MAXIMO_SIN_RESOLVER = 3
HORAS_SIN_RESOLVER = 1
#: El tope de volumen, en la base: cuantas ejecuciones autonomas por hora en
#: una empresa, y cuantas de la MISMA accion (mismo equipo) en un dia.
TOPE_POR_HORA = 10
TOPE_MISMA_ACCION_POR_DIA = 1


def por_que_no_es_candidata(herramienta) -> list[str]:
    """Las condiciones 1 y 2 que la herramienta no cumple, por su config.
    Vacio = es candidata."""
    faltan = []
    verificacion = getattr(herramienta, "verificacion", None)
    if verificacion is None or not getattr(verificacion, "comprobaciones", None):
        faltan.append("efecto_no_verificable")
    if not getattr(herramienta, "exige_previas", None):
        faltan.append("sin_previas_en_codigo")
    return faltan


def umbrales(config, accion: str) -> dict:
    """Los de la empresa para esa accion, o los por defecto. Nunca bajo el piso
    (el schema ya lo valida; esto lo repite por si llega una config vieja)."""
    propios = {}
    ag = getattr(config, "autonomia_ganada", None)
    if ag is not None and accion in (ag.acciones or {}):
        u = ag.acciones[accion]
        propios = {k: getattr(u, k) for k in POR_DEFECTO if getattr(u, k, None) is not None}
    u = {**POR_DEFECTO, **propios}
    return {k: max(u[k], PISO[k]) for k in PISO}


def veredicto(medicion: dict, u: dict) -> dict:
    """
    {'elegible', 'tasa_aprobacion', 'faltan': [{condicion, tiene, necesita}]}.
    'tasa_aprobacion' es None sin revisadas: 0 de 0 no es 0%.
    """
    revisadas = medicion["revisadas"]
    tasa = (revisadas - medicion["rechazadas"]) / revisadas if revisadas else None
    faltan = []
    if revisadas < u["minimo_revisadas"]:
        faltan.append({"condicion": "minimo_revisadas", "tiene": revisadas,
                       "necesita": u["minimo_revisadas"]})
    if tasa is None or tasa < u["tasa_minima_aprobacion"]:
        faltan.append({"condicion": "tasa_minima_aprobacion",
                       "tiene": None if tasa is None else round(tasa, 4),
                       "necesita": u["tasa_minima_aprobacion"]})
    if medicion["no_confirmadas"] > 0:
        faltan.append({"condicion": "cero_no_confirmadas", "tiene": medicion["no_confirmadas"],
                       "necesita": 0})
    if medicion["fallidas"] > 0:
        faltan.append({"condicion": "cero_fallidas", "tiene": medicion["fallidas"], "necesita": 0})
    medidas = medicion["confirmadas"] + medicion["no_confirmadas"] + medicion["no_verificables"]
    confirmacion = medicion["confirmadas"] / medidas if medidas else None
    if medicion["confirmadas"] < u["minimo_confirmadas"]:
        faltan.append({"condicion": "minimo_confirmadas", "tiene": medicion["confirmadas"],
                       "necesita": u["minimo_confirmadas"]})
    if confirmacion is None or confirmacion < u["tasa_minima_confirmacion"]:
        faltan.append({"condicion": "tasa_minima_confirmacion",
                       "tiene": None if confirmacion is None else round(confirmacion, 4),
                       "necesita": u["tasa_minima_confirmacion"]})
    con_pendientes = medidas + medicion.get("pendientes", 0)
    medida = medidas / con_pendientes if con_pendientes else None
    if medida is None or medida < PROPORCION_MINIMA_MEDIDA:
        faltan.append({"condicion": "proporcion_medida",
                       "tiene": None if medida is None else round(medida, 4),
                       "necesita": PROPORCION_MINIMA_MEDIDA})
    if medicion.get("degradaciones", 0) > 0:
        faltan.append({"condicion": "cero_degradaciones", "tiene": medicion["degradaciones"],
                       "necesita": 0})
    return {"elegible": not faltan, "tasa_aprobacion": None if tasa is None else round(tasa, 4),
            "tasa_confirmacion": None if confirmacion is None else round(confirmacion, 4),
            "faltan": faltan}


def evaluar(config, tenant: str, ahora, *, medir, leer_vigente=None) -> list[dict]:
    """
    Cada herramienta que hoy pide aprobacion humana, con si es candidata, su
    evidencia en la ventana de la empresa, si es elegible y -- con
    leer_vigente -- si ya es autonoma. medir(tenant, herramienta, desde,
    hasta) -> conteos (nucleo/persistencia/autonomia_ganada).
    """
    salida = []
    for h in config.herramientas:
        if not getattr(h, "aprobacion_humana", False):
            continue
        no_candidata = por_que_no_es_candidata(h)
        fila = {"accion": h.nombre, "candidata": not no_candidata, "no_candidata": no_candidata}
        if not no_candidata:
            u = umbrales(config, h.nombre)
            desde = ahora - timedelta(days=u["ventana_dias"])
            m = medir(tenant, h.nombre, desde, ahora)
            fila.update({"umbrales": u, "evidencia": m, "desde": desde.isoformat(),
                         **veredicto(m, u)})
            if leer_vigente is not None:
                fila["autonomia"] = vigente(tenant, h.nombre, leer=leer_vigente)
        else:
            fila["elegible"] = False
        salida.append(fila)
    return salida


# =============================================================================
#  FASE B  --  promover (una persona), retirar (una persona), y el estado vigente
# =============================================================================

class NoPromovible(Exception):
    """Por que no se puede promover, con un codigo fijo y lo que falta."""

    def __init__(self, codigo: str, faltan=None):
        super().__init__(codigo)
        self.codigo = codigo
        self.faltan = faltan or []


def vigente(tenant: str, herramienta: str, *, leer) -> dict:
    """
    Si la herramienta es autonoma AHORA en esta empresa. FALLA CERRADO, como
    el interruptor: sin fila, con la base caida o con la tabla sin instalar,
    NO es autonoma. Sin cache: cada consulta va a la base -- una degradacion
    tiene que valer desde la proxima accion, no dentro de N segundos.

    leer(tenant, herramienta) -> la ultima fila | None (puede lanzar).
    {'autonoma', 'estado', 'promocion_id'}.
    """
    try:
        fila = leer(tenant, herramienta)
    except (Exception, SystemExit):                             # noqa: BLE001
        #  SystemExit tambien: sin credenciales la capa de conexion lo lanza
        #  (CLAUDE.md §13, D11), y no hereda de Exception. Una lectura de
        #  seguridad falla CERRADO; nunca tumba el proceso.
        return {"autonoma": False, "estado": "desconocido", "promocion_id": None}
    if not fila:
        return {"autonoma": False, "estado": "sin_registro", "promocion_id": None}
    if fila.get("estado") != "activa":
        return {"autonoma": False, "estado": str(fila.get("estado")), "promocion_id": None}
    return {"autonoma": True, "estado": "activa", "promocion_id": str(fila.get("id")),
            "desde": fila.get("creado_en")}


def promover(config, tenant: str, accion: str, actor: str, ahora, *, medir, escribir,
             leer_vigente=None) -> dict:
    """
    Una PERSONA le da autonomia a una accion. Se vuelve a medir la evidencia
    en este momento -- no la de la pantalla que la persona miro --, y si no
    alcanza, no se promueve. Lo que se escribe lleva la evidencia que lo
    justifico, para que la auditoria no tenga que reconstruirla.

    escribir(tenant, accion, actor, motivo, evidencia) -> la fila.
    """
    if not (actor or "").strip():
        raise NoPromovible("FALTA_QUIEN_PROMUEVE")
    h = next((x for x in config.herramientas
              if x.nombre == accion and getattr(x, "aprobacion_humana", False)), None)
    if h is None:
        raise NoPromovible("NO_ES_UNA_ACCION_CON_APROBACION")
    no_candidata = por_que_no_es_candidata(h)
    if not getattr(h, "irreversible", False):
        #  Solo las irreversibles pasan por frontera.critica, que es donde se
        #  vuelve a exigir la promocion al ejecutar: una reversible quedaria
        #  "autonoma" en el reporte sin ejecutarse nunca sola.
        no_candidata = [*no_candidata, "no_pasa_por_la_puerta_critica"]
    if no_candidata:
        raise NoPromovible("NO_CANDIDATA", no_candidata)
    if leer_vigente is not None and vigente(tenant, accion, leer=leer_vigente)["autonoma"]:
        #  Dos clics seguidos dejaban dos filas 'activa'; la segunda tapaba a
        #  la primera y una degradacion bajaba la que no correspondia.
        raise NoPromovible("YA_ES_AUTONOMA")
    u = umbrales(config, accion)
    desde = ahora - timedelta(days=u["ventana_dias"])
    m = medir(tenant, accion, desde, ahora)
    v = veredicto(m, u)
    if not v["elegible"]:
        raise NoPromovible("SIN_EVIDENCIA", v["faltan"])
    return escribir(tenant, accion, actor.strip(), "promovida con la evidencia de la ventana",
                    {"evidencia": m, "umbrales": u, "desde": desde.isoformat(),
                     "tasa_aprobacion": v["tasa_aprobacion"]})
