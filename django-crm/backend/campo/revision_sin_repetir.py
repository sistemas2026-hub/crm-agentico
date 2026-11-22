# -*- coding: utf-8 -*-
"""
================================================================================
 LA REVISION NO SE RECALCULA SI NADA CAMBIO  --  21/11/2026
================================================================================
El usuario: «la pestaña de Supervisor cuando se recarga demora en salir».

LO QUE SE MIDIO
---------------
Programacion pide lo publicado cada 15 segundos por cada pestaña a la vista, y
cada pedido recalculaba la revision del cierre de TODAS las ordenes terminadas
sin validar --las del dia y las de cualquier dia anterior--. Medido contra
PostgreSQL con ordenes sin fotos (el piso; una orden real lee mas):

    10 de dias anteriores + 5 del dia  ->  339 consultas por pedido
    de esas, dentro de `revisar()`     ->  275

Y las del dia se calculaban DOS veces por pedido: una para las cuentas y otra
para la tarjeta de su cuadrilla (20 llamadas para 15 ordenes).

QUE HACE
--------
Antes de calcular, saca una HUELLA de cada orden: cuantas filas tiene y cuando
se toco la ultima en cada tabla que la revision lee. Son seis consultas para
todas las ordenes juntas, no una docena por orden. Si la huella es la misma
que la de la ultima vez, devuelve la revision de entonces.

NO CONTRADICE «SE CALCULA, NO SE GUARDA»
----------------------------------------
`revision_del_cierre.py` no guarda el veredicto porque la medicion llega hasta
una hora despues del cierre, y uno guardado diria «revisar» cuando ya se sabe.
Ese motivo sigue en pie y por eso la medicion ENTRA EN LA HUELLA: cuando llega,
la huella cambia y se recalcula en el pedido siguiente. Esto no guarda una
decision; evita repetir una cuenta cuyo resultado no pudo cambiar.

SOLO PARA MOSTRAR. Quien CIERRA --una persona al aprobar, o el Supervisor por
`cierre_por_el_supervisor.py`-- llama a `revisar()` directo y no pasa por aca.

DOS LIMITES, A PROPOSITO
------------------------
  · LA VIDA ES CORTA (un minuto, `vida()`) y es la red de atras: la huella no
    ve una fila escrita con `.update()` o `bulk_update` (que no mueven
    `updated_at`), ni dos escritores que confirman cruzados. Nada de eso queda
    viejo mas de un minuto. Lo que SI ve aunque no sea de la orden: la
    plantilla y su nombre, la zona horaria de la empresa, y el codigo mismo
    --un despliegue que cambie como se revisa no devuelve lo de antes--.
  · LA HUELLA SE SACA ANTES DE CALCULAR, nunca despues: asi lo guardado es
    igual o mas nuevo que su huella, y cualquier cambio posterior la mueve. Al
    reves, una revision vieja podria quedar bajo una huella nueva.

SI ALGO FALLA, SE CALCULA. La cache caida, una huella que no se pudo sacar o
una revision que revento: todo cae al camino de siempre. Y una revision que
fallo NO se guarda -- se reintenta en el pedido siguiente.
================================================================================
"""
from __future__ import annotations

import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

#: Cuantos segundos vale una revision sin recalcular, aunque su huella no se
#: haya movido. Es la red de atras; ver el encabezado.
VIDA_POR_DEFECTO = 60

#: El tope: por mas que se pida, lo que la huella no ve no queda viejo mas de
#: diez minutos.
VIDA_MAXIMA = 600

#: LA PERILLA DE OPERACION, UNA SOLA: cuantos segundos vale lo guardado. `0`
#: vuelve a calcular siempre. No es configuracion de una empresa --es si este
#: atajo esta puesto y cuanto se le confia--, y por eso es una variable del
#: servicio y no un campo del tenant. ESTA DECLARADA en el compose de
#: produccion: una variable que el contenedor no recibe no apaga nada.
VARIABLE = "CAMPO_REVISION_VIDA_SEGUNDOS"


def vida() -> int:
    """Los segundos que vale lo guardado; 0 es apagado. Se lee en cada pedido."""
    crudo = (os.environ.get(VARIABLE) or "").strip().lower()
    if not crudo:
        return VIDA_POR_DEFECTO
    if crudo in ("no", "false", "off"):
        return 0
    try:
        pedido = int(crudo)
    except ValueError:
        #  Un valor que no se entiende no apaga el atajo en silencio ni lo
        #  deja sin tope: queda como si no estuviera.
        return VIDA_POR_DEFECTO
    return max(0, min(pedido, VIDA_MAXIMA))


def encendido() -> bool:
    return vida() > 0


_VERSION = []


def version_del_codigo() -> str:
    """Una huella de `campo/*.py`, sacada una vez por proceso.

    Lo guardado sobrevive a un despliegue (vive en Redis, no en el proceso). Si
    el despliegue cambio como se revisa, devolver lo de antes seria mostrar el
    criterio viejo con el codigo nuevo ya corriendo -- y quien acaba de
    desplegar un arreglo mira la tarjeta en ese mismo minuto.
    """
    if not _VERSION:
        h = hashlib.sha256()
        try:
            carpeta = os.path.dirname(os.path.abspath(__file__))
            for raiz, carpetas, archivos in os.walk(carpeta):
                carpetas[:] = sorted(c for c in carpetas
                                     if c not in ("tests", "migrations",
                                                  "__pycache__"))
                for nombre in sorted(archivos):
                    if nombre.endswith(".py"):
                        with open(os.path.join(raiz, nombre), "rb") as f:
                            h.update(f.read())
            _VERSION.append(h.hexdigest()[:16])
        except OSError:
            #  Sin poder leerse no hay version comun: cada proceso usa una
            #  propia y lo guardado por otro no le sirve. De mas, no de menos.
            _VERSION.append(f"sin-leer-{os.getpid()}")
    return _VERSION[0]


def _clave(org_id, orden_id) -> str:
    return f"campo:revision:{org_id}:{orden_id}"


def _sello(valor) -> str:
    return valor.isoformat() if valor is not None else ""


def _por_orden(consulta, campo: str) -> dict:
    """{orden_id: (cuantas, ultima)} de una tabla, en UNA consulta."""
    from django.db.models import Count, Max

    return {str(f[campo]): (f["n"], _sello(f["u"]))
            for f in (consulta.order_by().values(campo)
                      .annotate(n=Count("id"), u=Max("updated_at")))}


def _de_la_orden(o) -> list:
    """Lo que la revision lee de la orden misma, que ya esta cargada."""
    version = getattr(o, "tipo_trabajo_version", None)
    #  EL NOMBRE DEL TIPO va por su valor: es el «asunto» que la tarjeta
    #  compara con lo que hizo el tecnico, y renombrar una plantilla no mueve
    #  el `updated_at` de su version.
    tipo = getattr(getattr(version, "work_type", None), "nombre", "")
    suelto = json.dumps(
        [getattr(o, "datos", None), getattr(o, "resumen", None),
         getattr(o, "diagnostico_previo", None), getattr(o, "contexto", None),
         getattr(o, "origen_sistema", None), getattr(o, "origen_tipo", None),
         getattr(o, "origen_ref", None)],
        sort_keys=True, default=str)
    return [o.vuelta, o.estado_operativo, o.estado_validacion,
            _sello(getattr(o, "updated_at", None)),
            #  La plantilla entra por CUAL es, no por su fecha: el esquema de
            #  una version publicada no se puede editar (`WorkTypeVersion.
            #  clean`), cambiarlo es pasar la orden a otra version.
            str(getattr(version, "id", "")),
            str(tipo or ""),
            hashlib.sha256(suelto.encode("utf-8")).hexdigest()]


def huellas(org, ordenes, pendientes, zona=None) -> dict:
    """{orden.id: huella} de cada orden. Seis consultas para todas juntas."""
    from django.db.models import Count, Max

    from campo import revision_del_cierre as RC
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.cotejo_del_reporte import CotejoDelReporte
    from campo.models import (EventoTrabajo, EvidenciaTrabajo,
                              MovimientoDeMaterial)
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    ids = [o.id for o in ordenes]
    eventos = _por_orden(
        EventoTrabajo.objects.filter(org=org, orden_id__in=ids), "orden_id")
    evidencias = _por_orden(
        EvidenciaTrabajo.objects.filter(org=org, orden_trabajo_id__in=ids),
        "orden_trabajo_id")
    analisis = _por_orden(
        AnalisisDeEvidencia.objects.filter(org=org,
                                           evidencia__orden_trabajo_id__in=ids),
        "evidencia__orden_trabajo_id")
    materiales = _por_orden(
        MovimientoDeMaterial.objects.filter(org=org, orden_id__in=ids),
        "orden_id")
    cotejos = _por_orden(
        CotejoDelReporte.objects.filter(org=org, orden_id__in=ids), "orden_id")
    #  LA MEDICION DESPUES DEL ARREGLO vive dentro de las propuestas del
    #  Supervisor, como una pieza de su evidencia. No se puede agrupar por
    #  orden sin abrir el JSON de cada una, asi que entra UN sello para todas:
    #  cuando se mide cualquier orden, se recalculan las de la pantalla. Es de
    #  mas, nunca de menos.
    medidas = (PropuestaSupervisor.objects
               .filter(org=org, evidencia__contains=[{"fuente": FUENTE}])
               .aggregate(n=Count("id"), u=Max("updated_at")))
    sello_medidas = (medidas["n"], _sello(medidas["u"]))
    #  Lo que es igual para todas: el codigo que revisa, y la zona en la que
    #  se escribe la hora de la tarjeta.
    comun = [version_del_codigo(), str(zona or "")]

    salida = {}
    for o in ordenes:
        k = str(o.id)
        espera = ("no_se_sabe" if pendientes == RC.NO_SE_SABE
                  else k in (pendientes or ()))
        todo = json.dumps(
            [_de_la_orden(o), eventos.get(k), evidencias.get(k),
             analisis.get(k), materiales.get(k), cotejos.get(k),
             sello_medidas, espera, comun],
            sort_keys=True, default=str)
        salida[o.id] = hashlib.sha256(todo.encode("utf-8")).hexdigest()
    return salida


def tarjeta_de_error(tipo: str) -> dict:
    """Lo que se muestra cuando una revision no se pudo hacer. Que se VEA: una
    revision que falla en silencio deja la tarjeta sin botones y nadie sabe
    por que. El tipo del error, nunca su texto."""
    return {"veredicto": "revisar", "texto": "No se pudo revisar el cierre",
            "puntos": [{"clave": "error", "ok": None,
                        "texto": f"La revisión falló ({tipo}): "
                                 "miralo antes de cerrar."}],
            "evidencias": [], "sugeridas": [], "solucion": "",
            "supervisor_no_pudo": None}


def de_error(ordenes, tipo: str) -> dict:
    """{orden.id: tarjeta de error | None}: para cuando falla TODO y no una."""
    from campo import revision_del_cierre as RC

    return {o.id: (tarjeta_de_error(tipo) if RC.aplica(o) else None)
            for o in ordenes}


def _calcular(org, orden, pendientes, zona) -> tuple:
    """`(revision, sirve)`. `sirve` es False cuando la revision fallo: eso se
    muestra --una tarjeta sin botones y sin motivo no le sirve a nadie-- pero
    no se guarda."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import EVENTO_BLOQUEADO
    from campo.models import EventoTrabajo

    try:
        r = RC.revisar(orden, pendientes=pendientes)
        if r is not None:
            #  Si el Supervisor la quiso cerrar solo y el motor no lo dejo:
            #  cuando, y que compuerta (30/10/2026).
            ev = (EventoTrabajo.objects
                  .filter(org=org, orden=orden, tipo=EVENTO_BLOQUEADO)
                  .order_by("-created_at").first())
            r["supervisor_no_pudo"] = ({
                "hora": ev.created_at.astimezone(zona).strftime("%H:%M"),
                "detalle": str((ev.datos or {}).get("detalle") or ""),
            } if ev else None)
        return r, True
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Programacion: no se pudo revisar un cierre (%s)",
                       type(e).__name__)
        return tarjeta_de_error(type(e).__name__), False


def _guardadas(org, huellas_de: dict) -> dict | None:
    """{orden_id: revision} de las que tienen la MISMA huella que hoy.

    None si la cache no contesto: entonces tampoco se intenta guardar. Con
    Redis caido cada intento espera su tope (2 s en produccion), y pagarlo
    dos veces por pedido haria la pantalla MAS lenta justo cuando algo anda
    mal."""
    from django.core.cache import cache

    if not huellas_de:
        return {}
    claves = {_clave(org.id, k): k for k in huellas_de}
    try:
        hallado = cache.get_many(list(claves))
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Programacion: la cache no contesto al leer (%s)",
                       type(e).__name__)
        return None
    salida = {}
    for clave, valor in (hallado or {}).items():
        k = claves.get(clave)
        if (k is not None and isinstance(valor, dict)
                and valor.get("huella") == huellas_de[k]
                and "revision" in valor):
            salida[k] = valor["revision"]
    return salida


def _guardar(org, huellas_de: dict, nuevas: dict, segundos: int) -> None:
    from django.core.cache import cache

    if not nuevas or segundos <= 0:
        return
    try:
        cache.set_many({_clave(org.id, k): {"huella": huellas_de[k],
                                            "revision": r}
                        for k, r in nuevas.items()}, segundos)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Programacion: la cache no contesto al guardar (%s)",
                       type(e).__name__)


def de_las_ordenes(org, ordenes, *, ahora, zona) -> dict:
    """{orden.id: revision | None} de cada orden de la pantalla.

    None para la que no tiene nada que revisar. Cada orden se revisa UNA vez
    aunque aparezca en dos lugares de la pantalla.
    """
    from campo import revision_del_cierre as RC

    salida = {o.id: None for o in ordenes}
    revisables = {o.id: o for o in ordenes if RC.aplica(o)}
    if not revisables:
        return salida

    #  Las que esperan la medicion, UNA vez por pantalla y solo si hay algo
    #  que revisar. Sin poder saberlo, la tarjeta no dice «Se puede cerrar» de
    #  una que quiza espera la medicion.
    medir = RC.pendientes_de_medir(org, ahora)
    pendientes = RC.NO_SE_SABE if medir is None else medir

    segundos = vida()
    huellas_de = {}
    if segundos > 0:
        try:
            #  ANTES de calcular. Ver el encabezado.
            huellas_de = huellas(org, list(revisables.values()), pendientes,
                                 zona)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("Programacion: no se pudo sacar la huella (%s)",
                           type(e).__name__)
            huellas_de = {}
    guardadas = _guardadas(org, huellas_de)
    if guardadas is None:
        #  La cache no contesto: se calcula todo y no se guarda nada.
        guardadas, huellas_de = {}, {}

    nuevas = {}
    for k, o in revisables.items():
        if k in guardadas:
            salida[k] = guardadas[k]
            continue
        revision, sirve = _calcular(org, o, pendientes, zona)
        salida[k] = revision
        if sirve and k in huellas_de:
            nuevas[k] = revision
    _guardar(org, huellas_de, nuevas, segundos)
    return salida
