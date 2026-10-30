# -*- coding: utf-8 -*-
"""
================================================================================
 LA JORNADA DEL DIA, ARMADA SOLA
================================================================================

POR QUE HACE FALTA
------------------
`reparto.proponer()` reparte entre las cuadrillas que YA tienen jornada armada
ese dia:

    JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)

La composicion es del dia a proposito --es lo que permite decir quien estuvo el
miercoles pasado-- pero eso tiene un costo: a primera hora, la jornada de hoy
todavia no existe. Sin este modulo el reparto automatico devolveria vacio, y el
sintoma seria "no se asigno nada", que no señala a la causa.

LA REGLA  --  17/10/2026, objetivo `supervisor-arma-la-jornada`
---------------------------------------------------------------
Decidida por el usuario con 60 dias de produccion a la vista
(`informe_de_jornadas`): lo que se repite es la PAREJA de cada cuadrilla; las
zonas y la labor no se repiten.

    QUIEN VA      la gente de su ultima jornada: la pareja de siempre. Sin los
                  dados de baja y sin los ausentes (`DisponibilidadTecnico`).
    ADONDE        sus ZONAS HABITUALES, marcadas en Cuadrillas. No las del
                  ultimo dia: eso era justo lo que no se repetia.
    QUE LABOR     la de la mayoria de los casos de Despacho de sus zonas ese
                  dia; sin casos, su labor habitual. Si dos cuadrillas
                  comparten zona y hay casos de dos labores, cada una toma una
                  (`_elegir_labores`).
    QUIEN LIDERA  el lider de la cuadrilla.

Hasta esa fecha se copiaba la ultima jornada entera, zonas y labor incluidas.

LO QUE NO SE ARMA, Y SE DICE POR QUE
------------------------------------
    sin_zona        no tiene zonas habituales. Vacio NO es "cubre todas": con
                    zona dura no recibiria trabajo, y armarla seria una fila
                    que parece trabajo hecho.
    lider_ausente   su lider declaro ausencia ese dia. Sin lider no hay a quien
                    entregarle la orden (`destinatarios`): la arma una persona.
    sin_gente       nadie de su ultima jornada puede salir.
    sin_base        nunca trabajo y no tiene lider: no hay de donde armarla.

UNA SOLA REGLA PARA LOS DOS QUE ARMAN
------------------------------------
El Supervisor en cada vuelta (`operaciones.armado_de_jornadas`) y el ciclo de
la madrugada (`campo.tasks.correr_para`) usan `planear_el_dia` y `aplicar`.
Dos constructores serian dos reglas, y el dia que difieran nadie sabria cual
armo la jornada que esta mirando.

LO QUE NO PISA
--------------
Una jornada armada por una PERSONA no se toca nunca: la tomo alguien mirando
el caso. Una armada SOLA (`armada_por = AUTOMATICA`) se reajusta de labor
mientras no tenga ordenes: lo que entra a Despacho a la tarde con otra labor
sale ese mismo dia (decidido por el usuario). Con ordenes ya no: cambiarle la
labor a una cuadrilla que ya salio con trabajo seria repartirle otro.

Eso hace la operacion IDEMPOTENTE: correrla dos veces deja lo mismo que
correrla una, que es la condicion para poder reintentarla sin pensar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from campo.cuadrillas import (
    Cuadrilla,
    IntegranteDeJornada,
    JornadaDeCuadrilla,
    destinatarios,
)

#: Que se hace con cada cuadrilla.
ARMAR = "armar"
REAJUSTAR = "reajustar"
DEJAR = "dejar"
NO_SE_ARMA = "no_se_arma"

#: Por que. Son CLAVES y no frases: van al resumen y al log.
COPIADA = "copiada"
ESTRENADA = "estrenada"
ARMADA_POR_UNA_PERSONA = "armada_por_una_persona"
YA_TIENE_ORDENES = "ya_tiene_ordenes"
MISMA_LABOR = "misma_labor"
OTRA_LABOR = "otra_labor"
SIN_ZONA = "sin_zona"
LIDER_AUSENTE = "lider_ausente"
SIN_GENTE = "sin_gente"
SIN_BASE = "sin_base"

#: El desempate entre dos labores con los mismos casos, despues de la que ya
#: tiene y de la habitual: primero quien se quedo sin servicio.
_DESEMPATE = (JornadaDeCuadrilla.CORRECTIVO, JornadaDeCuadrilla.INSTALACION,
              JornadaDeCuadrilla.TRABAJOS)


@dataclass
class Plan:
    """Lo que se haria con UNA cuadrilla. No escribe nada."""

    cuadrilla: Cuadrilla
    accion: str
    motivo: str
    labor: str = ""
    labor_antes: str = ""
    #: La de apoyo (30/10/2026, SPEC/objetivos/labor-de-apoyo.md): con el cupo
    #: que su labor deja libre, en sus mismas zonas. Vacia = sin apoyo.
    labor_de_apoyo: str = ""
    apoyo_antes: str = ""
    zonas: list = field(default_factory=list)
    lider: object = None
    #: [(PersonaDeCampo, rol)]
    integrantes: list = field(default_factory=list)
    #: La que ya existe ese dia, si hay.
    jornada: object = None
    #: De que dia sale la gente.
    desde: object = None
    de_baja: int = 0
    ausentes: int = 0
    #: Los que una persona ya puso en otra cuadrilla ese dia: esa decision
    #: gana, y esta cuadrilla sale sin ellos.
    en_otra_cuadrilla: int = 0


# ---------------------------------------------------------------------------
#  Lo que se lee
# ---------------------------------------------------------------------------

def _ultima_jornada(cuadrilla, antes_de):
    """La jornada mas reciente de esa cuadrilla ANTERIOR a la fecha pedida.

    `antes_de` y no `<=`: si ya hay una del mismo dia, no hay nada que armar
    -- de eso se encarga quien llama, y copiarse a si misma seria un no-op
    disfrazado de trabajo.
    """
    return (
        JornadaDeCuadrilla.objects
        .filter(cuadrilla=cuadrilla, fecha__lt=antes_de)
        .prefetch_related("zonas", "integrantes__persona")
        .order_by("-fecha")
        .first()
    )


def ausentes_del_dia(org, fecha) -> set:
    """Las cuentas que ese dia no trabajan.

    Una ausencia que deja a la persona sin un minuto de la jornada de la
    empresa (`capacidad.disponibilidad_de` == AUSENTE). Una de media mañana no
    la saca: sale tarde, pero sale. Si la empresa no tiene la jornada de ese
    dia abierta --sin calendario, un feriado-- no hay contra que medir, y una
    ausencia declarada cuenta entera: ante la duda no se arma con alguien que
    dijo que no viene.

    Un auxiliar sin cuenta no puede declarar ausencia --la tabla es por
    cuenta--, asi que de el no se sabe nada: va.
    """
    from operaciones import capacidad
    from operaciones.models import DisponibilidadTecnico

    perfiles = set(
        DisponibilidadTecnico.objects
        .filter(org=org, fecha=fecha, disponible=False)
        .values_list("profile_id", flat=True)
    )
    if not perfiles:
        return set()
    jornada = capacidad.jornada_de(org, fecha)
    if not jornada.abierta:
        return perfiles
    return {
        p for p in perfiles
        if capacidad.disponibilidad_de(org, p, fecha, jornada)["estado"]
        == capacidad.AUSENTE
    }


def tiene_ordenes(jornada) -> bool:
    """Si alguien que recibe por esta jornada tiene una orden ABIERTA asignada.

    No hay una columna que ate una orden a una jornada: la asignacion es a una
    CUENTA (`AsignacionTrabajo`), la del lider del dia o la de un integrante
    con cuenta (`destinatarios`).

    ABIERTA, Y NO "ASIGNADA HOY"  --  auditor de frontera, 17/10/2026. La
    primera version miraba solo lo asignado desde las 00:00, y una orden para
    hoy asignada anoche no congelaba la labor. Ahora cuenta toda orden que no
    este terminada --completada en campo, cerrada o cancelada--, se haya
    asignado cuando sea: una cuadrilla que todavia carga trabajo no cambia de
    labor. Conservador a proposito: ante la duda, la jornada no se toca.
    """
    from campo.models import AsignacionTrabajo, OrdenTrabajo

    perfiles = [r["profile"].id for r in destinatarios(jornada)["reciben"]]
    if not perfiles:
        return False
    return (AsignacionTrabajo.objects
            .filter(orden__org_id=jornada.org_id, profile_id__in=perfiles)
            .exclude(orden__estado_operativo__in=(
                OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA,
                OrdenTrabajo.CANCELADA))
            .exists())


# ---------------------------------------------------------------------------
#  El plan
# ---------------------------------------------------------------------------

def planear_el_dia(org, fecha, *, demanda=None, ausentes=None) -> list:
    """Que se haria con cada cuadrilla activa ese dia. NO ESCRIBE.

    `demanda` es {zona_id: {labor: casos}}: los casos de Despacho de cada
    zona, por labor. Vacio = no hay casos, y cada cuadrilla sale con su labor
    habitual. `ausentes` son ids de cuenta; si no viene se lee
    (`ausentes_del_dia`).

    Es la mitad que la sombra muestra: lo que se armaria, sin armarlo.
    """
    demanda = demanda or {}
    if ausentes is None:
        ausentes = ausentes_del_dia(org, fecha)

    cuadrillas = list(
        Cuadrilla.objects.filter(org=org, activa=True)
        .select_related("lider")
        .prefetch_related("zonas_habituales")
        .order_by("nombre")
    )
    existentes = {
        j.cuadrilla_id: j
        for j in (JornadaDeCuadrilla.objects
                  .filter(org=org, fecha=fecha)
                  .select_related("cuadrilla__lider", "lider")
                  .prefetch_related("zonas"))
    }

    planes = []
    for c in cuadrillas:
        zonas = [z for z in c.zonas_habituales.all() if z.activa]
        ya = existentes.get(c.id)

        if ya is not None:
            if ya.armada_por != JornadaDeCuadrilla.AUTOMATICA:
                planes.append(Plan(c, DEJAR, ARMADA_POR_UNA_PERSONA,
                                   labor=ya.labor,
                                   labor_de_apoyo=ya.labor_de_apoyo,
                                   jornada=ya, zonas=list(ya.zonas.all())))
            elif tiene_ordenes(ya):
                #  Con ordenes no se toca, tampoco el apoyo: el material del
                #  dia ya se cargo con el que tenia.
                planes.append(Plan(c, DEJAR, YA_TIENE_ORDENES,
                                   labor=ya.labor,
                                   labor_de_apoyo=ya.labor_de_apoyo,
                                   jornada=ya, zonas=list(ya.zonas.all())))
            else:
                #  Candidata a reajustar: la labor y el apoyo se eligen
                #  abajo, con las demas. Si salen los mismos, queda en DEJAR.
                planes.append(Plan(c, REAJUSTAR, OTRA_LABOR,
                                   labor_antes=ya.labor,
                                   apoyo_antes=ya.labor_de_apoyo,
                                   jornada=ya, zonas=list(ya.zonas.all())))
            continue

        if not zonas:
            planes.append(Plan(c, NO_SE_ARMA, SIN_ZONA))
            continue

        anterior = _ultima_jornada(c, fecha)
        lider = c.lider or (anterior.lider if anterior is not None else None)
        if lider is not None and lider.id in ausentes:
            planes.append(Plan(c, NO_SE_ARMA, LIDER_AUSENTE, zonas=zonas))
            continue

        if anterior is None:
            if lider is None:
                planes.append(Plan(c, NO_SE_ARMA, SIN_BASE, zonas=zonas))
                continue
            #  EL ARRANQUE EN FRIO: nunca trabajo. Sale con el lider solo; la
            #  gente la agrega una persona. Lo que esto evita es que no
            #  exista NADA que corregir.
            planes.append(Plan(c, ARMAR, ESTRENADA, zonas=zonas, lider=lider))
            continue

        gente, de_baja, fuera = [], 0, 0
        for viejo in anterior.integrantes.all():
            persona = viejo.persona
            if not persona.activa:
                de_baja += 1
                continue
            if persona.profile_id is not None and persona.profile_id in ausentes:
                fuera += 1
                continue
            gente.append((persona, viejo.rol))
        if not gente and lider is None:
            planes.append(Plan(c, NO_SE_ARMA, SIN_GENTE, zonas=zonas,
                               de_baja=de_baja, ausentes=fuera))
            continue
        planes.append(Plan(c, ARMAR, COPIADA, zonas=zonas, lider=lider,
                           integrantes=gente, desde=anterior.fecha,
                           de_baja=de_baja, ausentes=fuera))

    _elegir_labores(planes, demanda)
    return planes


def _la_de_mas_casos(cuenta: dict, orden: list) -> str:
    """La labor con mas casos; en empate, la que aparece antes en `orden`."""
    return max(cuenta, key=lambda lab: (
        cuenta[lab], -orden.index(lab) if lab in orden else -len(orden)))


def _elegir_labores(planes, demanda) -> None:
    """La labor de cada jornada que se arma o se reajusta. Escribe en el plan.

    SEGUN LA CANTIDAD  --  21/10/2026, decision del usuario. Reemplaza la regla
    del 17/10 («si la zona tiene casos de dos labores, la segunda toma la
    otra»): la vista previa mostro en Soledad 27 casos de correctivo y 1 de
    trabajos, y esa regla mandaba una cuadrilla ENTERA a trabajos por un caso.

    COMO: cada cuadrilla «se lleva» tantos casos como su tope (el suyo, o el
    de la empresa). Primero descuentan las jornadas que no se tocan. Despues,
    de a una, se asigna el par (cuadrilla, labor) con MAS casos sin cubrir en
    las zonas de esa cuadrilla; en empate gana la que ya tiene esa labor, o la
    tiene de habitual, y despues el orden de nombre. Asi:

        - una labor con pocos casos no se lleva una cuadrilla mientras otra
          tenga mas sin cubrir: esos casos esperan, o los despacha una persona;
        - una cuadrilla no cambia de labor si la suya todavia tiene trabajo
          (la #1 de instalacion y la #2 de correctivo no salen cruzadas por el
          orden alfabetico);
        - si todo lo de sus zonas ya esta cubierto, ayuda con la mayoria; sin
          casos, sale con la que tiene o su habitual.
    """
    from campo.cuadrillas import configuracion_de_reparto

    if not planes:
        return
    tope_de_la_empresa = configuracion_de_reparto(
        planes[0].cuadrilla.org).tope_por_cuadrilla

    def _tope(p) -> int:
        return p.cuadrilla.tope_diario or tope_de_la_empresa

    resto = {str(z): {lab: n for lab, n in (labs or {}).items() if n and n > 0}
             for z, labs in demanda.items()}

    def _cubrir(zonas, labor, cuanto) -> int:
        """Descuenta lo que cubre; devuelve el cupo que le queda."""
        for z in sorted(zonas, key=lambda z: -resto.get(z, {}).get(labor, 0)):
            if cuanto <= 0:
                break
            hay = resto.get(z, {}).get(labor, 0)
            if hay > 0:
                toma = min(hay, cuanto)
                resto[z][labor] = hay - toma
                cuanto -= toma
        return cuanto

    def _cerrar(p) -> None:
        if (p.accion == REAJUSTAR and p.labor == p.labor_antes
                and p.labor_de_apoyo == p.apoyo_antes):
            p.accion, p.motivo = DEJAR, MISMA_LABOR

    #  El cupo que le queda a cada una despues de su labor principal: es el
    #  unico que puede usar el apoyo.
    libre = {}
    for p in planes:
        if p.accion == DEJAR:
            zonas = [str(z.id) for z in p.zonas]
            libre[id(p)] = _cubrir(zonas, p.labor, _tope(p))
            #  Un apoyo ya puesto --por una persona, o por el Supervisor en una
            #  jornada que ya salio-- tambien se lleva lo suyo.
            if p.labor_de_apoyo and p.labor_de_apoyo != p.labor:
                _cubrir(zonas, p.labor_de_apoyo, libre[id(p)])

    pendientes = [p for p in planes if p.accion in (ARMAR, REAJUSTAR)]
    while pendientes:
        mejor = None
        for i, p in enumerate(pendientes):
            preferidas = [x for x in (p.labor_antes,
                                      p.cuadrilla.labor_habitual) if x]
            sin_cubrir = {}
            for z in (str(z.id) for z in p.zonas):
                for lab, n in resto.get(z, {}).items():
                    if n > 0:
                        sin_cubrir[lab] = sin_cubrir.get(lab, 0) + n
            for lab, n in sin_cubrir.items():
                clave = (n,
                         len(preferidas) - preferidas.index(lab)
                         if lab in preferidas else 0,
                         -i,
                         -(_DESEMPATE.index(lab) if lab in _DESEMPATE
                           else len(_DESEMPATE)))
                if mejor is None or clave > mejor[0]:
                    mejor = (clave, p, lab)
        if mejor is None:
            #  Nadie tiene casos sin cubrir en sus zonas.
            for p in pendientes:
                total = {}
                for z in (str(z.id) for z in p.zonas):
                    for lab, n in (demanda.get(z) or {}).items():
                        if n and n > 0:
                            total[lab] = total.get(lab, 0) + n
                orden = [x for x in (p.labor_antes, p.cuadrilla.labor_habitual,
                                     *_DESEMPATE) if x]
                p.labor = (_la_de_mas_casos(total, orden) if total
                           else p.labor_antes or p.cuadrilla.labor_habitual)
                libre[id(p)] = _tope(p)
            break
        _, p, lab = mejor
        p.labor = lab
        libre[id(p)] = _cubrir([str(z.id) for z in p.zonas], lab, _tope(p))
        pendientes.remove(p)

    from campo.labores import labores_de_apoyo

    _elegir_apoyos(planes, resto, libre, _cubrir,
                   permitidas=labores_de_apoyo(planes[0].cuadrilla.org))
    for p in planes:
        _cerrar(p)


def _elegir_apoyos(planes, resto, libre, cubrir, *, permitidas) -> None:
    """LA LABOR DE APOYO de cada jornada que se arma o se reajusta sola
    (30/10/2026, SPEC/objetivos/labor-de-apoyo.md). Escribe en el plan.

    Va DESPUES de todas las principales: el apoyo nunca le gana a la labor
    principal de otra cuadrilla. De a una, el par (cuadrilla, labor) con mas
    casos SIN CUBRIR en las zonas de esa cuadrilla, entre las que tienen cupo
    libre; lo que toma se descuenta, y dos cuadrillas no se llevan el mismo
    caso. Sin casos sin cubrir de otra labor, sin apoyo. Solo las labores
    que la empresa dice que se toman de apoyo (`Labor.se_toma_de_apoyo`): una
    obra de red no se le da a la de soporte.
    """
    candidatas = [p for p in planes
                  if p.accion in (ARMAR, REAJUSTAR) and libre.get(id(p), 0) > 0]
    for p in planes:
        if p.accion in (ARMAR, REAJUSTAR):
            p.labor_de_apoyo = ""
    while candidatas:
        mejor = None
        for i, p in enumerate(candidatas):
            sin_cubrir = {}
            for z in (str(z.id) for z in p.zonas):
                for lab, n in resto.get(z, {}).items():
                    if n > 0 and lab != p.labor and lab in permitidas:
                        sin_cubrir[lab] = sin_cubrir.get(lab, 0) + n
            for lab, n in sin_cubrir.items():
                clave = (min(n, libre[id(p)]), -i,
                         -(_DESEMPATE.index(lab) if lab in _DESEMPATE
                           else len(_DESEMPATE)))
                if mejor is None or clave > mejor[0]:
                    mejor = (clave, p, lab)
        if mejor is None:
            return
        _, p, lab = mejor
        p.labor_de_apoyo = lab
        cubrir([str(z.id) for z in p.zonas], lab, libre[id(p)])
        candidatas.remove(p)


# ---------------------------------------------------------------------------
#  Lo que se escribe
# ---------------------------------------------------------------------------

def resumen(planes) -> dict:
    """Que paso --o que pasaria-- con cada cuadrilla, nombrandolas.

    Un conteo sin nombres obliga a salir a buscar cual fue. Son las claves de
    siempre del ciclo de la madrugada, mas las de la regla del 17/10.
    """
    salida = {"copiadas": [], "estrenadas": [], "reajustadas": [],
              "ya_estaban": [], "sin_base": [], "sin_zona": [],
              "lider_ausente": [], "sin_gente": [], "labores": {}}
    for p in planes:
        nombre = p.cuadrilla.nombre
        if p.accion == ARMAR and p.motivo == COPIADA:
            salida["copiadas"].append({
                "cuadrilla": nombre,
                "desde": p.desde.isoformat() if p.desde else None,
                "sin_gente": p.de_baja,
                "ausentes": p.ausentes,
                "en_otra_cuadrilla": p.en_otra_cuadrilla,
                "labor": p.labor,
            })
        elif p.accion == ARMAR:
            salida["estrenadas"].append(nombre)
        elif p.accion == REAJUSTAR:
            salida["reajustadas"].append(
                {"cuadrilla": nombre, "de": p.labor_antes, "a": p.labor})
        elif p.accion == DEJAR:
            salida["ya_estaban"].append(nombre)
        elif p.motivo in salida:
            salida[p.motivo].append(nombre)
        if p.accion in (ARMAR, REAJUSTAR):
            salida["labores"][nombre] = p.labor
            if p.labor_de_apoyo:
                salida.setdefault("apoyos", {})[nombre] = p.labor_de_apoyo
    return salida


def aplicar(org, fecha, planes, *, origen: str = "") -> dict:
    """Escribe el plan. Devuelve `resumen` de lo que de verdad quedo.

    Cada cuadrilla en su propia transaccion: que una falle --una persona armo
    la misma jornada en ese instante-- no deshace las demas. Cada escritura
    lleva su fila de auditoria EN LA MISMA transaccion: una jornada armada sin
    registro no se arma. `origen` dice quien la armo (la tarea del Supervisor,
    o el ciclo de la madrugada).
    """
    for p in planes:
        if p.accion == ARMAR:
            if not _armar(org, fecha, p, origen):
                p.accion, p.motivo = DEJAR, ARMADA_POR_UNA_PERSONA
        elif p.accion == REAJUSTAR:
            #  SE VUELVE A MIRAR AL ESCRIBIR (auditor de frontera, 17/10): entre
            #  el plan y esto hay una llamada de red, y alguien pudo publicar el
            #  reparto en el medio.
            if tiene_ordenes(p.jornada):
                p.accion, p.motivo = DEJAR, YA_TIENE_ORDENES
                continue
            with transaction.atomic():
                #  CONDICIONAL: si una persona la corrigio entre el plan y esto,
                #  ya es suya (`armada_por = PERSONA`) y no se toca.
                n = (JornadaDeCuadrilla.objects
                     .filter(id=p.jornada.id,
                             armada_por=JornadaDeCuadrilla.AUTOMATICA,
                             labor=p.labor_antes,
                             labor_de_apoyo=p.apoyo_antes)
                     .update(labor=p.labor, labor_de_apoyo=p.labor_de_apoyo,
                             updated_at=timezone.now()))
                if n:
                    _auditar(org, fecha, p, p.jornada.id, origen)
            if not n:
                p.accion, p.motivo = DEJAR, ARMADA_POR_UNA_PERSONA
    return resumen(planes)


def _armar(org, fecha, p, origen) -> bool:
    """Crea la jornada de un plan. False si ya existia: la armo alguien."""
    try:
        with transaction.atomic():
            jornada = JornadaDeCuadrilla.objects.create(
                org=org, cuadrilla=p.cuadrilla, fecha=fecha, labor=p.labor,
                labor_de_apoyo=p.labor_de_apoyo,
                lider=p.lider, armada_por=JornadaDeCuadrilla.AUTOMATICA,
            )
            jornada.zonas.set(p.zonas)
            for persona, rol in p.integrantes:
                integrante = IntegranteDeJornada(
                    org=org, jornada=jornada, persona=persona, rol=rol)
                try:
                    #  `full_clean` y no `save` a secas: ahi vive la guarda de
                    #  "esta persona ya esta en otra cuadrilla hoy". Si una
                    #  persona la puso en otra, esa decision gana.
                    integrante.full_clean()
                except ValidationError:
                    p.en_otra_cuadrilla += 1
                    continue
                integrante.save()
            _auditar(org, fecha, p, jornada.id, origen)
    except IntegrityError:
        return False
    return True


def _auditar(org, fecha, p, jornada_id, origen) -> None:
    """La fila de auditoria de una jornada armada o reajustada sola.

    EL NIVEL 3 ES EJECUTAR ALGO REVERSIBLE, y revertir se apoya en poder ver
    que se hizo. La jornada dice `armada_por`, pero de un reajuste no quedaba
    ni la labor anterior (auditor de frontera, 17/10/2026). Actor None: la
    escribio el sistema, y asi se reconoce -- no por un usuario inventado.
    """
    from operaciones import auditoria

    armada = p.accion == ARMAR
    zonas = ", ".join(z.nombre for z in p.zonas) or "sin zona"
    apoyo = f" (apoyo: {p.labor_de_apoyo})" if p.labor_de_apoyo else ""
    apoyo_antes = f" (apoyo: {p.apoyo_antes})" if p.apoyo_antes else ""
    auditoria.registrar(
        org=org, actor=None,
        accion="CREATE" if armada else "UPDATE",
        entidad=auditoria.ENTIDAD_JORNADA, entidad_id=jornada_id,
        nombre=f"{p.cuadrilla.nombre} · {fecha.isoformat()}",
        descripcion=(f"Jornada armada sola: {p.labor}{apoyo} en {zonas}."
                     if armada
                     else f"Labor reajustada sola: de {p.labor_antes}"
                          f"{apoyo_antes} a {p.labor}{apoyo}."),
        estado_anterior="" if armada else p.labor_antes,
        estado_nuevo=p.labor,
        motivo=p.motivo,
        extra={"automatico": True, "origen": origen or "sin_origen",
               "labor_de_apoyo": p.labor_de_apoyo,
               "apoyo_antes": "" if armada else p.apoyo_antes},
    )


def asegurar_jornadas(org, fecha, *, demanda=None,
                      origen: str = "ciclo_de_la_madrugada") -> dict:
    """Deja armada la jornada de cada cuadrilla activa para esa fecha.

    La entrada del ciclo de la madrugada. Es `planear_el_dia` + `aplicar`, la
    misma regla que usa el Supervisor en cada vuelta.
    """
    return aplicar(org, fecha, planear_el_dia(org, fecha, demanda=demanda),
                   origen=origen)
