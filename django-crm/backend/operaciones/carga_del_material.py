"""
================================================================================
 EL SUPERVISOR CARGA EL MATERIAL DEL DIA  --  28/10/2026
================================================================================
Fase 3 de SPEC/objetivos/material-del-dia.md. Las decisiones del usuario que la
gobiernan:
  28/10  El kit va al LIDER de la cuadrilla.
  28/10  «La idea era que lo hiciera el Supervisor»: que kit y de que bodega
         los elige el (`campo.material_del_dia`), y esto los carga.
  28/10  Se carga enseguida despues de publicar el reparto de la mañana, UNA vez
         por dia y cuadrilla; lo que entra despues se pide desde la app.

LO QUE HACE: en cada vuelta, a cada jornada del dia que todavia no se cargo, le
carga lo ASIGNADO por la propuesta (`material_del_dia.calcular`): el kit menos
lo que el lider ya tiene, repartido por el trabajo del dia si la bodega no
alcanza. Con `inventario.despachar`, el mismo camino que la bodega: acta,
movimientos y custodia del lider.

UNA VEZ POR DIA Y CUADRILLA: el acta tiene clave fija (`acta_de`) y `despachar`
es idempotente por acta; antes de cargar se mira si ya esta (`cargadas`). Una
cuadrilla que se arma a la tarde se carga en la vuelta en que aparece.

LOS EQUIPOS CON SERIE NO SE DESPACHAN: `despachar` exige la serie de cada uno y
el Supervisor no la sabe (decision del 28/10: se ata cuando el tecnico la
escanea, fase 2). Lo que le toca a la cuadrilla queda RESERVADO en su bodega
(`reservar`), con el acta al principio del motivo, para que no se lo lleve otro
hasta que lo escanee.

CUANDO: las mismas comprobaciones que la publicacion del reparto
(`publicacion_del_reparto.cuando`): un dia que las cuadrillas trabajan, desde
dos horas antes de que abran hasta el cierre. Y despues de publicar, dentro del
mismo ciclo: el trabajo del dia ya esta repartido.

LAS PUERTAS, fail-closed como las de la publicacion: la tarea delegada propia
`CARGAR_EL_MATERIAL` y el nivel que exige, con su interruptor. Sin ellas, LA
SOMBRA: cuenta cuantas cuadrillas cargaria, sin escribir nada.
================================================================================
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from operaciones import atascos

logger = logging.getLogger(__name__)

PUBLICO = "publico"
SOMBRA = "sombra"
NO_CORRIO = "no_corrio"


def _tarea():
    from operaciones import tareas_delegadas as td
    return td.CARGAR_EL_MATERIAL


def _puertas(org) -> str:
    """Por que NO puede cargar, o "" si puede. Texto fijo: va a un log."""
    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    try:
        if not td.esta_delegada(org, _tarea()):
            return ("nadie le delegó al Supervisor que cargue el material: se "
                    "le pide desde su chat o en Ajustes del Supervisor")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar la tarea ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(
            org, td.CATALOGO[_tarea()]["exige_nivel"]) or {}
    except Exception as e:                                       # noqa: BLE001
        veredicto = {"puede": False, "motivo": type(e).__name__}
    if not veredicto.get("puede"):
        return "la empresa no tiene autorizado que el Supervisor cargue material"
    return ""


def _que_cargar(fila) -> tuple:
    """(lineas sin serie para `despachar`, [(material, cantidad)] con serie)."""
    comunes, con_serie = [], []
    for i in fila["lineas"]:
        if i["asignado"] <= 0:
            continue
        if i["serializado"]:
            con_serie.append((i["_material"], i["asignado"]))
        else:
            comunes.append({"material": i["_material"], "cantidad": i["asignado"]})
    return comunes, con_serie


def _cargar_una(org, hoy, fila, comunes, con_serie) -> int:
    """Carga UNA jornada, todo o nada. Devuelve cuantas reservas dejo."""
    from campo.services import inventario as inv
    from campo.services.inventario_operacion import reservar

    with transaction.atomic():
        if comunes:
            inv.despachar(
                org=org, ubicacion_origen=fila["_bodega"],
                profile_destino=fila["_lider"], lineas=comunes,
                despachado_por=None, acta=fila["acta"],
                notas=(f"Material del día {hoy.isoformat()}: lo cargó el "
                       f"Supervisor ({fila['cuadrilla']})."))
        for material, cantidad in con_serie:
            #  A NOMBRE DEL LIDER: es lo que la recepcion busca cuando escanea
            #  (`campo/recepcion_del_kit.py`), y lo que hace que el despacho de
            #  esa ONT cierre SU reserva y no la de otra cuadrilla.
            reservar(org=org, ubicacion=fila["_bodega"], material=material,
                     cantidad=cantidad, reservada_por=fila["_lider"],
                     motivo=(f"{fila['acta']} · equipos del día para "
                             f"{fila['cuadrilla']}: se entregan al escanearlos"))
    return len(con_serie)


def _anotar_atascos(org, plan, ya, ahora) -> None:
    """Lo que no se puede cargar, en `operaciones/atascos.py`: en la sombra
    tambien, porque lo que se mide es si el Supervisor sabe decidir, no si
    tiene permiso. Las cuadrillas ya cargadas no: su dia ya se decidio."""
    from campo import material_del_dia as M

    def anotar(tipo, sujeto, motivo):
        atascos.anotar(org, atascos.FASE_MATERIAL, tipo, sujeto, motivo, ahora=ahora)

    labores_sin_kit = set()
    for fila in plan["cuadrillas"]:
        if fila["acta"] in ya:
            continue
        cuadrilla = fila["_cuadrilla_id"]
        if fila["_sin"] == "kit":
            #  El atasco es de la LABOR: dos cuadrillas de la misma labor son
            #  un solo kit que no se eligio.
            if fila["_labor"] not in labores_sin_kit:
                labores_sin_kit.add(fila["_labor"])
                anotar("kit_sin_elegir", fila["_labor"], fila["kit_por"])
        elif fila["_sin"] == "bodega":
            anotar("bodega_sin_elegir", cuadrilla, fila["bodega_por"])
        elif fila["_sin"] == "lider":
            anotar("sin_lider", cuadrilla, "no tiene líder con cuenta activa")
        incompletos = [i for i in fila["lineas"] if i["falta"] > 0]
        if incompletos:
            anotar("material_no_alcanza", cuadrilla,
                   f"{len(incompletos)} de {len(fila['lineas'])} materiales")
        for i in incompletos:
            if i["serializado"] and i["asignado"] == M.CERO:
                anotar("sale_sin_equipo", f"{cuadrilla}:{i['_material'].codigo}",
                       i["material"])
    #  QUE FALTA EN CADA BODEGA (29/10/2026): «13 de 14 materiales» por
    #  cuadrilla no dice que comprar ni que cargar en Inventario. Uno por
    #  bodega y material. SIN LA CANTIDAD en el motivo: el informe agrupa por
    #  motivo, y un numero que cambia cada dia partiria la misma falta en
    #  catorce lineas. Cuanto falta hoy lo dice Programacion. Solo de las
    #  cuadrillas que no se cargaron, como todo lo demas.
    faltan = {(f["bodega"], i["material"]) for f in plan["cuadrillas"]
              if f["acta"] not in ya for i in f["lineas"] if i["falta"] > 0}
    for bodega, material in sorted(faltan):
        anotar("falta_en_bodega", f"{bodega}:{material}", f"{bodega} · {material}")


def cargar_el_material(org, ahora=None) -> dict:
    """La fase del ciclo. Nunca levanta: lo que no se pudo, se dice."""
    from campo import material_del_dia as M
    from operaciones import publicacion_del_reparto as pub

    ahora = ahora or timezone.now()
    salida = {"modo": NO_CORRIO, "porque": "", "cargaria": 0, "cargadas": 0,
              "ya_cargadas": 0, "nada_que_cargar": 0, "sin_carga": 0,
              "reservas": 0, "con_faltantes": 0, "no_se_pudo": 0}
    try:
        hoy, porque, _aviso = pub.cuando(org, ahora)
        if porque:
            salida["porque"] = porque
            return {"material_del_dia": salida}
        plan = M.calcular(org, hoy)
    except Exception as e:                                       # noqa: BLE001
        salida["porque"] = f"no se pudo armar la propuesta ({type(e).__name__})"
        logger.warning("Supervisor: material del dia · %s", salida["porque"])
        return {"material_del_dia": salida}

    ya = M.cargadas(org, [f["acta"] for f in plan["cuadrillas"]])
    pendientes = []
    for fila in plan["cuadrillas"]:
        if not fila["lineas"]:
            salida["sin_carga"] += 1
            continue
        if fila["acta"] in ya:
            salida["ya_cargadas"] += 1
            continue
        comunes, con_serie = _que_cargar(fila)
        if not comunes and not con_serie:
            salida["nada_que_cargar"] += 1
            continue
        if any(i["falta"] > 0 for i in fila["lineas"]):
            salida["con_faltantes"] += 1
        pendientes.append((fila, comunes, con_serie))
    salida["cargaria"] = len(pendientes)
    _anotar_atascos(org, plan, ya, ahora)

    porque = _puertas(org)
    if porque:
        salida["modo"], salida["porque"] = SOMBRA, porque
        logger.info("Supervisor: material del dia · sombra (%s) · cargaria=%s · "
                    "ya cargadas=%s · sin carga=%s · con faltantes=%s",
                    porque, salida["cargaria"], salida["ya_cargadas"],
                    salida["sin_carga"], salida["con_faltantes"])
        return {"material_del_dia": salida}

    salida["modo"] = PUBLICO
    for fila, comunes, con_serie in pendientes:
        try:
            salida["reservas"] += _cargar_una(org, hoy, fila, comunes, con_serie)
            salida["cargadas"] += 1
        except Exception as e:                                   # noqa: BLE001
            #  Una cuadrilla que no se pudo cargar no frena a las demas. Por
            #  tipo, nunca el mensaje: puede traer nombres.
            salida["no_se_pudo"] += 1
            logger.warning("Supervisor: material del dia · una cuadrilla no se "
                           "pudo cargar (%s)", type(e).__name__)
            atascos.anotar(org, atascos.FASE_MATERIAL, "carga_fallo",
                           fila["_cuadrilla_id"], type(e).__name__, ahora=ahora)
    logger.info("Supervisor: material del dia · cargadas=%s · reservas=%s · ya "
                "cargadas=%s · sin carga=%s · con faltantes=%s · no se pudo=%s",
                salida["cargadas"], salida["reservas"], salida["ya_cargadas"],
                salida["sin_carga"], salida["con_faltantes"], salida["no_se_pudo"])
    return {"material_del_dia": salida}
