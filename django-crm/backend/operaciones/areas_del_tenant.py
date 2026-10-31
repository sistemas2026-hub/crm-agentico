# -*- coding: utf-8 -*-
"""
================================================================================
 QUIEN ES DE QUE AREA, SEGUN LA CONFIGURACION DE LA EMPRESA
================================================================================

PARA QUE EXISTE
---------------
El Supervisor NOC lee tickets de SOPORTE TECNICO. Hasta el 14/10/2026 leia
todos, y el cliente lo vio enseguida: "revise la lista de soporte tecnico en
los ticket y no salen los ticket de descuentos programados, esos son de
cartera".

Tenia razon, y el numero lo confirmo: de los tickets abiertos, una sola persona
concentraba 563 --509 de ellos de cartera-- mientras la de soporte tenia 76,
exactamente los 76 que la pantalla de Tickets muestra para esa area.

EL AREA YA SE GUARDA EN EL CASO desde cdaa9b27 (16/10/2026, 'Case.area'):
cuando se escribio esto no existia, y el primer camino fue no agregarla para
no dejar sin area a los ~1.300 casos ya importados. Hoy el area escrita manda
y este mapa decide solo para los casos que todavia no la tienen -- ver
'criterio_de_area' abajo, que es donde vive la regla.

LA PIEZA YA EXISTIA, y la encontro el cliente preguntando lo obvio: "los
tickets en Dexter si estan divididos bien... ¿no puede el supervisor extraer de
esa area los ticket sin tanto rodeo?". La pantalla de Tickets le pregunta al
motor que personas son de cada area y filtra por 'assigned_to'. Esto hace lo
mismo para el Supervisor.

EL MAPA PERSONA -> AREA es como la empresa lo configura: se edita desde la
interfaz, y el dia que entre alguien nuevo a soporte el Supervisor lo respeta
sin tocar codigo. Desde el 16/10/2026 decide solo lo que el caso no trae
escrito.
================================================================================
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import requests
from django.db.models import Q

logger = logging.getLogger(__name__)

#:  LAS AREAS que le tocan al Supervisor NOC, que son DOS y no una.
#:
#:  Se escribio con una sola --'soporte_tecnico'-- razonando que
#:  'importacion_tickets.destinos' manda el departamento "Operativo" a esa
#:  area. Eso es cierto para a donde va el TICKET, y no tiene nada que ver con
#:  a que area pertenece una PERSONA, que es lo que se consulta aqui.
#:
#:  MEDIDO el 14/10/2026 contra 'asistente.area_colaborador': 'operativo' es un
#:  area propia con cuatro personas. Con un solo nombre, los tickets de esas
#:  cuatro quedaban afuera -- y el cliente pidio expresamente "soporte tecnico
#:  y operativo".
AREAS_DEL_SUPERVISOR = ("soporte_tecnico", "operativo")

#:  Se conserva el nombre viejo apuntando a la primera, por si algo quedo
#:  leyendolo. No se usa en este modulo.
AREA_DEL_SUPERVISOR = AREAS_DEL_SUPERVISOR[0]

#:  Cuanto vale la lectura antes de volver a preguntar. Las areas cambian
#:  cuando entra o sale alguien del equipo -- no en minutos.
SEGUNDOS_DE_CACHE = 15 * 60

#:  Mas que suficiente para una lectura local del motor, y corto para que un
#:  motor trabado no deje al ciclo esperando: el ciclo ya tarda seis minutos.
ESPERA_MAXIMA = 5

#:  Cuanto se recuerda que el motor NO contesto, para no volver a preguntar en
#:  cada lectura de la misma vuelta. Ver '_sin_respuesta' en area_por_persona.
SEGUNDOS_SIN_RESPUESTA = 60
_SIN_RESPUESTA = "__sin_respuesta__"


def _solo_texto(mapa) -> dict:
    """
    El mapa con la forma que este modulo promete: {str: str}. Cualquier otra
    cosa que mande el motor --una lista, claves raras, valores nulos-- se
    descarta en vez de levantar: una excepcion aca ocurre dentro de la
    transaccion del ciclo y deshace expiraciones, retiros y propuestas de
    toda la vuelta (medido por la auditoria de frontera, 16/10/2026).
    """
    if not isinstance(mapa, dict):
        return {}
    return {str(k): v for k, v in mapa.items()
            if isinstance(k, str) and isinstance(v, str)}


def _motor():
    """Donde vive el motor y con que se le habla. Igual que telemetria.py."""
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or ""
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, tenant, cabeceras


def area_por_persona() -> dict:
    """
    {profile_id: area} tal como lo declara la configuracion de la empresa.

    Devuelve {} cuando no se puede saber, y quien llama tiene que distinguir
    ESO de "nadie es de esa area": son cosas distintas y la diferencia decide
    si se lee un ticket ajeno.
    """
    _, tenant, _ = _motor()
    if not tenant:
        #  FAIL-CLOSED CON EL TENANT, igual que en el resto del proyecto: sin
        #  saber de que empresa es, preguntar por sus areas devolveria las de
        #  otra.
        logger.info("Supervisor: falta MOTOR_TENANT, no se consultan areas")
        return {}
    return _mapa_del_motor(tenant, "areas_por_persona")


def area_por_persona_de_org(org_id) -> dict:
    """
    {profile_id: area} de la empresa de ESA organizacion.

    Lo mismo que 'area_por_persona', con la empresa sacada de la organizacion
    de quien pregunta y no de 'MOTOR_TENANT' (24/10/2026). Existe porque de
    este mapa pasa a depender un PERMISO -- un colaborador toma un ticket sin
    asignar de su area (cases/access.py) -- y un permiso no puede leer las
    areas de la empresa que diga una variable de entorno: con dos empresas en
    la misma instalacion, la segunda leeria las de la primera.

    {} si no se sabe de que empresa es o el motor no contesta: el permiso cae
    al de antes, ver solo lo propio.
    """
    tenant = tenant_de_organizacion(org_id)
    if not tenant:
        return {}
    return _mapa_del_motor(tenant, f"areas_por_persona:{tenant}")


def tenant_de_organizacion(org_id) -> str:
    """
    El tenant del motor para una organizacion del CRM, o '' si no se sabe.

    Lo resuelve el motor ('/tenant-de-organizacion/<id>'), igual que el
    frontend en 'tenantDeLaSesion': Django no lee el esquema 'asistente'. SIN
    DEFAULT: ni 'MOTOR_TENANT' ni "el de siempre" -- no saber es '' y quien
    llama no le da a nadie nada que dependa de la empresa.
    """
    from django.core.cache import cache

    if not org_id:
        return ""
    clave = f"tenant_de_org:{org_id}"
    try:
        guardado = cache.get(clave)
        if guardado == _SIN_RESPUESTA:
            return ""
        if guardado is not None:
            return guardado
    except Exception:                                        # noqa: BLE001
        pass

    base, _, cabeceras = _motor()
    tenant = ""
    try:
        r = requests.get(f"{base}/tenant-de-organizacion/{org_id}",
                         headers=cabeceras, timeout=ESPERA_MAXIMA)
        if r.ok:
            tenant = str((r.json() or {}).get("tenant") or "").strip()
        else:
            logger.info("Areas: el motor respondio %s al tenant", r.status_code)
    except Exception as e:                                   # noqa: BLE001
        logger.info("Areas: no se pudo resolver el tenant (%s)",
                    type(e).__name__)
    try:
        if tenant:
            cache.set(clave, tenant, SEGUNDOS_DE_CACHE)
        else:
            cache.set(clave, _SIN_RESPUESTA, SEGUNDOS_SIN_RESPUESTA)
    except Exception:                                        # noqa: BLE001
        pass
    return tenant


def _mapa_del_motor(tenant: str, clave: str) -> dict:
    """El mapa persona -> area de 'tenant' segun el motor, con su cache."""
    from django.core.cache import cache

    try:
        guardado = cache.get(clave)
        if guardado == _SIN_RESPUESTA:
            return {}
        if guardado is not None:
            return guardado
    except Exception:                                        # noqa: BLE001
        pass

    def _sin_respuesta():
        #  UN MINUTO SIN VOLVER A PREGUNTAR  --  16/10/2026. Un ciclo del
        #  Supervisor lee el mapa diez veces (tres señales, el retiro, y
        #  'detectar' corre tres veces por ciclo). Con el motor sin contestar
        #  y nada cacheado, eran diez esperas de hasta cinco segundos, cuatro
        #  de ellas con la fila de la organizacion bloqueada. Y peor: una
        #  lectura podia fallar y la siguiente no, con lo que el retiro y las
        #  señales veian mapas distintos en la MISMA vuelta. Lo midio la
        #  auditoria de frontera. Un minuto es menos que un ciclo y mas que
        #  una corrida: todas las lecturas de la vuelta dicen lo mismo.
        try:
            cache.set(clave, _SIN_RESPUESTA, SEGUNDOS_SIN_RESPUESTA)
        except Exception:                                    # noqa: BLE001
            pass
        return {}

    base, _, cabeceras = _motor()

    #  Se prueba el liviano y se cae al viejo, igual que la pantalla de
    #  Tickets: '/agentes/asignaciones' devuelve lo mismo y ademas sale a
    #  consultar al sistema externo, que aqui no hace falta.
    for ruta in ("/agentes/areas", "/agentes/asignaciones"):
        try:
            r = requests.get(f"{base}{ruta}", params={"tenant": tenant},
                             headers=cabeceras, timeout=ESPERA_MAXIMA)
        except Exception as e:                               # noqa: BLE001
            logger.info("Supervisor: no se pudieron leer las areas (%s)",
                        type(e).__name__)
            return _sin_respuesta()
        if r.status_code == 404:
            continue
        if not r.ok:
            logger.info("Supervisor: el motor respondio %s a las areas",
                        r.status_code)
            return _sin_respuesta()
        try:
            mapa = _solo_texto((r.json() or {}).get("areas_por_persona"))
        except Exception:                                    # noqa: BLE001
            return _sin_respuesta()
        try:
            cache.set(clave, mapa, SEGUNDOS_DE_CACHE)
        except Exception:                                    # noqa: BLE001
            pass
        return mapa
    return {}


def responsables_de(areas, mapa: dict | None = None) -> list:
    """
    Los perfiles que pertenecen a esas areas. Acepta un nombre o varios.

    Lista vacia significa "no hay nadie de esas areas" O "no se pudo
    preguntar". Quien llama no puede tratar las dos igual: filtrar por una
    lista vacia no filtra nada y traeria la cola entera -- que es exactamente
    lo que este modulo vino a evitar.
    """
    m = area_por_persona() if mapa is None else mapa
    nombres = [areas] if isinstance(areas, str) else list(areas or [])
    objetivo = {str(a or "").strip().lower() for a in nombres}
    return [pid for pid, suya in (m or {}).items()
            if str(suya or "").strip().lower() in objetivo]


# =============================================================================
#  EL CRITERIO DE AREA, EN UN SOLO LUGAR  --  16/10/2026
# =============================================================================
#  Hasta hoy la pregunta "¿este caso es del Supervisor?" vivia inline en
#  '_tickets_abiertos_con_tecnico', y las otras señales que leen tickets no la
#  hacian: 'CASO_ANTIGUO' y 'CASO_REQUIERE_VISITA' proponian tickets de cartera
#  y de ventas, y las propuestas ya hechas sobre tickets ajenos no las retiraba
#  nadie hasta que expiraran a los 7 dias. Tres lugares con la misma pregunta
#  son tres respuestas que divergen; por eso se contesta aca, una vez.
#
#  TRES RESPUESTAS, NO DOS. Un caso es PROPIO (area escrita del Supervisor, o
#  sin area escrita y con alguien del area encima), AJENO (area escrita de
#  otra, o sin area escrita y con gente cuya area el motor conoce y es otra) o
#  NO SE SABE (sin area escrita y sin nadie, o con alguien que el motor no
#  conoce). "No se sabe" NO es ajeno: por eso no se cancela nada, y no se le
#  inventa un area. Ver SPEC/objetivos/supervisor-retira-propuestas-ajenas.md.
#
#  SIN EL MAPA (el motor no contesto) solo se puede decidir por el area
#  escrita: 'se_sabe' queda en False y cada llamador decide. La lectura con
#  diagnostico no lee nada (cuesta una llamada al modelo por ticket), el retiro
#  no retira nada (escribe un estado), y las señales de ruido proponen solo lo
#  que NO depende de la persona: area escrita propia, o sin area y sin nadie.
#  Lo que tiene gente encima espera al mapa: proponerlo sin saber era
#  proponer hoy lo que la vuelta siguiente cancela, y con el motor caido una
#  vuelta eso oscilaba caso por caso -- hasta los ~500 tickets de cartera
#  importados antes del campo (medido por la auditoria de frontera,
#  16/10/2026).


@dataclass(frozen=True)
class CriterioDeArea:
    propio: Q
    ajeno: Q
    #  Lo que solo el mapa puede decidir: sin area escrita y con alguien
    #  encima. Con el mapa, cae en 'propio' o 'ajeno' (o en "no se sabe" si
    #  esa persona no figura); sin el mapa, no se propone.
    indecidible_sin_mapa: Q
    se_sabe: bool
    mapa: dict


def _normal(area) -> str:
    return str(area or "").strip().lower()


def criterio_de_area(mapa: dict | None = None) -> CriterioDeArea:
    """
    Los dos filtros --propio y ajeno-- para 'Case', y si se pudo saber.

    'mapa' es persona -> area tal como lo sirve el motor; si no viene se lee
    (con su cache de 15 minutos). Con el mapa vacio solo decide el area
    escrita en el caso.
    """
    m = _solo_texto(area_por_persona() if mapa is None else mapa)
    objetivo = {_normal(a) for a in AREAS_DEL_SUPERVISOR}
    #  LO ESCRITO SE COMPARA SIN MAYUSCULAS NI ESPACIOS ALREDEDOR. 'Case.area'
    #  lo escribe la importacion tal cual viene de 'destinos', y el nucleo
    #  valida ese nombre normalizado; una grafia distinta no es otra area, y
    #  tratarla como ajena cancelaba cada hora lo propio (auditoria
    #  independiente, 16/10/2026). Acentos y guiones no se tocan: eso es
    #  normalizar al escribir, y le toca a la importacion.
    patron = (r"^\s*(" + "|".join(re.escape(a) for a in AREAS_DEL_SUPERVISOR)
              + r")\s*$")
    vacia = Q(area__regex=r"^\s*$")
    escrita_propia = Q(area__iregex=patron)
    escrita_ajena = ~vacia & ~escrita_propia
    con_alguien_y_sin_area = vacia & Q(assigned_to__isnull=False)
    if not m:
        return CriterioDeArea(propio=escrita_propia, ajeno=escrita_ajena,
                              indecidible_sin_mapa=con_alguien_y_sin_area,
                              se_sabe=False, mapa={})
    de_soporte = [pid for pid, a in m.items() if _normal(a) in objetivo]
    de_otras = [pid for pid, a in m.items()
                if _normal(a) and _normal(a) not in objetivo]
    propio = escrita_propia | (vacia & Q(assigned_to__in=de_soporte))
    ajeno = escrita_ajena | (vacia & Q(assigned_to__in=de_otras))
    return CriterioDeArea(propio=propio, ajeno=ajeno,
                          indecidible_sin_mapa=con_alguien_y_sin_area,
                          se_sabe=True, mapa=dict(m))


def ajenos_entre(casos, criterio: CriterioDeArea):
    """
    Los casos de 'casos' que SE SABE que son de otra area.

    Un caso sin area escrita con alguien del Supervisor encima no es ajeno
    aunque tenga tambien a alguien de cartera: lo propio gana, y por eso se
    resta. Todo por subconsulta: un join al M2M dentro de un OR duplicaba
    filas (medido el 16/10/2026 en la cola de tickets).
    """
    propios = casos.filter(criterio.propio).values("pk")
    return casos.filter(criterio.ajeno).exclude(pk__in=propios).distinct()


def sin_ajenos(casos, criterio: CriterioDeArea):
    """
    'casos' sin los que se sabe ajenos. Lo que no se sabe por falta de mapa
    tampoco entra si depende de la persona (sin area escrita y con alguien
    encima): espera a la vuelta en que el motor conteste. Lo que no depende
    de nadie --sin area y sin nadie-- se queda, con o sin mapa.
    """
    filtrados = casos.exclude(pk__in=ajenos_entre(casos, criterio).values("pk"))
    if criterio.se_sabe:
        return filtrados
    return filtrados.exclude(
        pk__in=casos.filter(criterio.indecidible_sin_mapa).values("pk"))
