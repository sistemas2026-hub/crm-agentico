"""
================================================================================
 EL SUPERVISOR PUBLICA EL REPARTO DEL DIA  --  27/10/2026
================================================================================
Fase 3.1 de SPEC/objetivos/supervisor-arma-la-jornada.md. Las decisiones del
usuario que la gobiernan:

  17/10  El Supervisor publica el reparto SOLO, sin que una persona lo mire;
         detras de una tarea delegada propia, y primero en sombra.
  21/10  Publica solo: al tecnico le llega la visita.
  21/10  Antes de que arranque el dia puede mover lo que nadie empezo; desde
         la apertura lo publicado queda quieto y lo nuevo se suma.
  21/10  Cupo lleno: entran hoy las mas urgentes y el resto queda para mañana.
  21/10  Aviso al telefono cada vez que le asignan una visita
         (`campo.services.avisos.avisar_jornada_publicada`).

LO QUE HACE: SUMA, Y LIBERA LO TRABADO. NO REACOMODA.
-----------------------------------------------------
En cada vuelta, solo dos clases de orden cambian de manos:

  - la que NO TIENE A NADIE (nueva, o que quedo sin cuadrilla), y
  - la que tiene a alguien que HOY NO TRABAJA: no esta en ninguna jornada
    del dia, o declaro ausencia. Si no, quedaria en el telefono de quien no
    sale, y encima le ocuparia el cupo a la cuadrilla que si sale.

Lo que ya tiene a alguien que hoy trabaja NO SE MUEVE NUNCA, ni antes de la
apertura. La decision del 21/10 permitia mover antes de la apertura; se elige
no usarlo (27/10/2026, por la regla del usuario: la opcion recomendada, con lo
que midieron las auditorias de frontera e independiente de ese dia):
  - las jornadas del Supervisor se arman EN la apertura
    (`armado_de_jornadas`), asi que antes no habia nada suyo que reacomodar;
  - reacomodar cada hora mandaba avisos que se contradicen («2 visitas» y una
    hora despues «otras 2», sin decir que las primeras se fueron);
  - deshacia lo que una persona decidio en la pantalla de Cuadrillas.

EL TOPE ES LA CARGA DEL DIA, NO LA DE ESTA VUELTA: cada cuadrilla arranca con
lo que sus tecnicos ya tienen hoy (asignado, en camino, en sitio). Sin eso, una
cuadrilla con tope 8 terminaba con 11 si entraban urgentes despues de publicar.

UNA CUADRILLA SIN NADIE QUE RECIBA, o con alguien que declaro ausencia, no
entra al reparto: sus ordenes quedarian sin nadie mientras otra cuadrilla de
la zona tiene lugar.

La regla de reparto es la del boton (`reparto.repartir`, `clave_de_reparto`,
`publicar`): una segunda copia se desincronizaria el primer dia que alguien
toque una de las dos.

CUANDO
------
  - Solo en un dia que las cuadrillas trabajan, segun SU horario (sin el, no
    corre: decision del 21/10), y con las mismas comprobaciones de zona que el
    armado: una zona que no se puede leer, o un calendario que ya esta en
    otro dia, y no corre.
  - Desde HORAS_ANTES_DE_ABRIR antes de la apertura hasta el cierre: el aviso
    al telefono no sale de madrugada.
  - La hora es la del momento de publicar, no la de cuando arranco la vuelta:
    las fases de antes pueden tardar minutos.

LAS PUERTAS, todas fail-closed (no poder comprobarlas es no tenerlas)
---------------------------------------------------------------------
  la tarea `publicar_el_reparto_del_dia`, delegada por una persona
  el nivel 3 de la empresa (`autonomia.puede`, con su interruptor)

Sin alguna, LA SOMBRA: cuenta cuantas asignaria y cuantas liberaria, sin
escribir nada. Nunca levanta: lo que no se pudo, se dice.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

PUBLICO = "publico"
SOMBRA = "sombra"
NO_CORRIO = "no_corrio"

#: Desde cuantas horas antes de la apertura publica. Ver «CUANDO» arriba.
#: Candidato a «Ajustes del Supervisor» (ficha, «Anotado para otro momento»).
HORAS_ANTES_DE_ABRIR = 2

#: Lo que ocupa el cupo del dia de una cuadrilla.
def _estados_que_cargan():
    from campo.models import OrdenTrabajo
    return (OrdenTrabajo.ASIGNADA, OrdenTrabajo.CORRECCION_REQUERIDA,
            OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO)


def _tarea():
    from operaciones import tareas_delegadas as td
    return td.PUBLICAR_EL_REPARTO


def _puertas(org) -> str:
    """Por que NO puede publicar, o "" si puede. Texto fijo: va a un log."""
    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    try:
        if not td.esta_delegada(org, _tarea()):
            return ("nadie le delegó al Supervisor que publique el reparto: se "
                    "le pide desde su chat")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar la tarea ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(
            org, td.CATALOGO[_tarea()]["exige_nivel"]) or {}
    except Exception as e:                                       # noqa: BLE001
        veredicto = {"puede": False, "motivo": type(e).__name__}
    if not veredicto.get("puede"):
        #  TEXTO FIJO: el motivo del interruptor arrastra lo que una persona
        #  escribio al moverlo, y esto va a un log.
        return "la empresa no tiene autorizado que el Supervisor publique"
    return ""


def cuando(org, ahora) -> tuple:
    """(hoy, porque, aviso): el dia de la empresa; si no corresponde publicar
    ahora, por que; y si las zonas horarias piden revision, el aviso. Las
    mismas comprobaciones que `armado_de_jornadas`."""
    import zoneinfo

    from campo.reparto import _zona_de
    from operaciones import capacidad

    de_la_empresa = _zona_de(org)
    hoy = ahora.astimezone(de_la_empresa).date()
    jornada = capacidad.jornada_de(org, hoy, solo_de_cuadrillas=True)
    if not jornada.abierta:
        return hoy, ("las cuadrillas no trabajan hoy ("
                     f"{jornada.motivo or 'cerrado'})"), ""
    del_calendario = jornada.zona_horaria or "UTC"
    try:
        zona = zoneinfo.ZoneInfo(del_calendario)
    except Exception:                                            # noqa: BLE001
        return hoy, ("el horario de las cuadrillas tiene una zona horaria que "
                     "no se puede leer"), ""
    empresa = getattr(de_la_empresa, "key", "")
    if empresa and empresa != del_calendario:
        aviso = (f"el horario de las cuadrillas esta en {del_calendario} y la "
                 f"empresa en {empresa}: revisar la zona del horario")
    elif del_calendario == "UTC":
        aviso = ("la empresa y el horario de las cuadrillas estan en UTC: "
                 "revisar si es la zona de la operacion")
    else:
        aviso = ""
    local = ahora.astimezone(zona)
    if local.date() != hoy:
        return hoy, "para el horario de las cuadrillas ya es otro día", aviso
    apertura = dt.datetime.combine(hoy, jornada.apertura, tzinfo=zona)
    cierre = dt.datetime.combine(hoy, jornada.cierre, tzinfo=zona)
    if local < apertura - dt.timedelta(hours=HORAS_ANTES_DE_ABRIR):
        return hoy, ("todavía es temprano: publica desde dos horas antes de "
                     "que abran las cuadrillas"), aviso
    if local >= cierre:
        return hoy, "las cuadrillas ya cerraron: lo que queda sale mañana", aviso
    return hoy, "", aviso


def propuesta(org, hoy, ahora) -> dict:
    """Lo que el Supervisor asignaria ahora. No escribe nada.

        {"asignaciones": [{"jornada": id, "ordenes": [id]}],
         "trabajan_hoy": frozenset(profile_id),
         "publicaria": n, "libera": n, "sobrantes": n, "sin_cuadrilla": n,
         "sin_zona": n, "sin_nadie_con_cuenta": n, "con_ausentes": n}
    """
    from campo import reparto as R
    from campo.cuadrillas import (
        JornadaDeCuadrilla,
        configuracion_de_reparto,
        destinatarios,
    )
    from campo.jornada_automatica import ausentes_del_dia
    from campo.models import OrdenTrabajo

    ausentes = ausentes_del_dia(org, hoy)
    jornadas, receptores = [], {}
    sin_nadie = con_ausentes = 0
    for j in (JornadaDeCuadrilla.objects.filter(org=org, fecha=hoy)
              .select_related("cuadrilla", "cuadrilla__lider", "lider")
              .prefetch_related("zonas")):
        ids = {r["profile"].id for r in destinatarios(j)["reciben"]}
        if not ids:
            sin_nadie += 1
        elif ids & ausentes:
            #  Alguien que la recibiria declaro ausencia despues de armarla:
            #  que la mire una persona, no se le manda trabajo.
            con_ausentes += 1
        else:
            jornadas.append(j)
            receptores[j.id] = ids
    trabajan_hoy = frozenset().union(*receptores.values())

    espera = R.lo_que_espera(org)
    pendientes = list(
        OrdenTrabajo.objects
        .filter(org=org, id__in=[o.id for o in espera["pendientes"]])
        .select_related("tipo_trabajo_version__work_type")
        .prefetch_related("asignaciones"))
    candidatas, liberables = [], set()
    for o in pendientes:
        quienes = {a.profile_id for a in o.asignaciones.all()}
        if not quienes:
            candidatas.append(o)
        elif quienes.isdisjoint(trabajan_hoy):
            candidatas.append(o)
            liberables.add(o.id)

    #  LA CARGA DEL DIA de cada cuadrilla: lo que sus tecnicos ya tienen hoy.
    zona = R._zona_de(org)
    carga = {j.id: 0 for j in jornadas}
    for o in (OrdenTrabajo.objects
              .filter(org=org, estado_operativo__in=_estados_que_cargan(),
                      asignaciones__profile_id__in=trabajan_hoy)
              .distinct().prefetch_related("asignaciones")):
        if R._para_otro_dia(o, hoy, zona):
            continue
        quienes = {a.profile_id for a in o.asignaciones.all()}
        for j in jornadas:
            if quienes & receptores[j.id]:
                carga[j.id] += 1
                break

    tope = configuracion_de_reparto(org).tope_por_cuadrilla
    r = R.repartir(
        sorted(candidatas, key=R.clave_de_reparto(None, None, ahora)), jornadas,
        zonas_de={j.id: [str(z.id) for z in j.zonas.all()] for j in jornadas},
        topes={j.id: (j.cuadrilla.tope_diario or tope) for j in jornadas},
        zona_de_barrio=R.zona_de_barrio(org), dia=hoy, zona_horaria=zona,
        carga_inicial=carga)
    asignaciones = [
        {"jornada": str(j.id), "ordenes": [str(o.id) for o in r["asignadas"][j.id]]}
        for j in jornadas if r["asignadas"][j.id]]
    elegidas = [o for j in jornadas for o in r["asignadas"][j.id]]
    return {
        "asignaciones": asignaciones,
        "trabajan_hoy": trabajan_hoy,
        "publicaria": len(elegidas),
        "libera": sum(1 for o in elegidas if o.id in liberables),
        #  Cupo lleno: quedan para mañana (21/10/2026). Solo lo que no tiene a
        #  nadie que trabaje hoy: lo que ya tiene gente no es un sobrante.
        "sobrantes": len(r["sobrantes"]),
        "sin_cuadrilla": len(r["sin_cuadrilla"]),
        "sin_zona": len(r["sin_zona"]),
        "sin_nadie_con_cuenta": sin_nadie,
        "con_ausentes": con_ausentes,
    }


def publicar_el_reparto(org, ahora=None) -> dict:
    """La fase del ciclo. Nunca levanta: lo que no se pudo, se dice.

    `ahora` None = la hora real AL PUBLICAR (ver «CUANDO»)."""
    from campo import reparto

    ahora = ahora or timezone.now()
    salida = {"modo": NO_CORRIO, "porque": "", "aviso": "",
              "publicaria": 0, "libera": 0, "publicadas": 0, "liberadas": 0,
              "quietas": 0, "sobrantes": 0, "sin_cuadrilla": 0, "sin_zona": 0,
              "sin_nadie_con_cuenta": 0, "con_ausentes": 0}
    try:
        hoy, porque, aviso = cuando(org, ahora)
        salida["aviso"] = aviso
        if porque:
            salida["porque"] = porque
            return {"reparto_del_dia": salida}
        p = propuesta(org, hoy, ahora)
    except Exception as e:                                       # noqa: BLE001
        salida["porque"] = f"no se pudo armar la propuesta ({type(e).__name__})"
        logger.warning("Supervisor: reparto del dia · %s", salida["porque"])
        return {"reparto_del_dia": salida}
    for clave in ("publicaria", "libera", "sobrantes", "sin_cuadrilla",
                  "sin_zona", "sin_nadie_con_cuenta", "con_ausentes"):
        salida[clave] = p[clave]
    if aviso:
        logger.warning("Supervisor: reparto del dia · %s", aviso)

    porque = _puertas(org)
    if porque:
        salida["modo"], salida["porque"] = SOMBRA, porque
        logger.info("Supervisor: reparto del dia · sombra (%s) · asignaria=%s "
                    "· liberaria=%s · sobrantes=%s · sin cuadrilla=%s · "
                    "sin zona=%s · cuadrillas sin nadie=%s · con ausentes=%s",
                    porque, p["publicaria"], p["libera"], p["sobrantes"],
                    p["sin_cuadrilla"], p["sin_zona"],
                    p["sin_nadie_con_cuenta"], p["con_ausentes"])
        return {"reparto_del_dia": salida}

    salida["modo"] = PUBLICO
    if p["asignaciones"]:
        r = reparto.publicar(
            org, p["asignaciones"], mover=False, trabajan_hoy=p["trabajan_hoy"],
            por_el_supervisor={"tarea": _tarea(), "fecha": hoy.isoformat()})
        salida.update(publicadas=r["publicadas"], liberadas=len(r["reasignadas"]),
                      quietas=len(r["quietas"]))
    logger.info("Supervisor: reparto del dia · asigno=%s · libero=%s · "
                "quietas=%s · sobrantes=%s · sin cuadrilla=%s · sin zona=%s · "
                "cuadrillas sin nadie=%s · con ausentes=%s",
                salida["publicadas"], salida["liberadas"], salida["quietas"],
                salida["sobrantes"], salida["sin_cuadrilla"], salida["sin_zona"],
                salida["sin_nadie_con_cuenta"], salida["con_ausentes"])
    return {"reparto_del_dia": salida}
