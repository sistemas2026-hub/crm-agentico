# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULAR EL DIA  --  24/10/2026
================================================================================

Pedido del usuario: ver «cómo dejaría distribuidos los tickets a los técnicos,
para analizar la carga con que los deja y si los asigna bien según la labor».
Es el ENSAYO del dia entero, sin escribir nada:

    1. arma las cuadrillas como las armaria el Supervisor
       (`jornada_automatica.planear_el_dia`, el mismo de la fase horaria);
    2. crea, en memoria, las ordenes de los casos de Despacho
       (`ordenes_de_despacho.decidir`, la misma regla de «Ver qué crearía»);
    3. reparte esas y las que ya esperan entre esas cuadrillas
       (`reparto.repartir`, el MISMO reparto del boton Publicar).

Ninguna de las tres escribe ni le pregunta al motor. Las ordenes nuevas son
`OrdenTrabajo` SIN GUARDAR: asi el reparto las ordena y las filtra con la
misma regla que a las de verdad, sin una copia que se desincronice.

Lo que no puede saber: el barrio de un caso que todavia no se leyo (la fase
de cada hora lo pide al motor; mirar una pantalla no). Esos casos aparecen en
«no se crearían», con su motivo.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from django.utils import timezone


def _gente(p):
    """El lider y la gente de un plan: la de la jornada si ya esta armada, la
    que se copiaria si no. Mismo criterio que `armado_de_jornadas.vista_previa`."""
    if p.jornada is not None:
        lider = getattr(p.jornada.lider, "user", None)
        gente = [(i.persona, i.rol) for i in
                 p.jornada.integrantes.select_related("persona")]
    else:
        lider = getattr(p.lider, "user", None)
        gente = p.integrantes
    nombre = ((getattr(lider, "name", "") or getattr(lider, "email", ""))
              if lider else "")
    return nombre, [{"nombre": persona.nombre, "rol": rol}
                    for persona, rol in gente]


def simular(org, fecha=None, ahora=None) -> dict:
    """El dia entero como lo dejaria el Supervisor. No escribe nada."""
    from django.db.models import Max

    from campo import jornada_automatica as ja
    from campo import reparto as R
    from campo.cuadrillas import JornadaDeCuadrilla, configuracion_de_reparto
    from campo.labores import nombres_de_labor
    from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkTypeVersion
    from campo.zonas import ZonaOperativa
    from cases.models import Case
    from operaciones import armado_de_jornadas as adj
    from operaciones import capacidad
    from operaciones import ordenes_de_despacho as O

    ahora = ahora or timezone.now()
    zona_horaria = R._zona_de(org)
    fecha = fecha or ahora.astimezone(zona_horaria).date()
    nombres = nombres_de_labor(org)
    salida = {"fecha": fecha.isoformat(), "trabaja": False, "porque": "",
              "hora_de_corte": "", "sin_crear_porque": "",
              "cuadrillas": [], "no_salen": [],
              "fuera": {"sin_zona": [], "sin_cuadrilla": [], "sobrantes": [],
                        "sin_clasificar": [], "otro_dia": []},
              "cuentas": {}}

    #  UN DIA QUE NO SE TRABAJA NO CORTA LA SIMULACION (auditoria del
    #  24/10/2026): el Supervisor no arma ese dia, pero una jornada que una
    #  persona armo a mano igual recibe trabajo al publicar. Se muestra eso.
    jornada = capacidad.jornada_de(org, fecha, solo_de_cuadrillas=True)
    if jornada.motivo == capacidad.SIN_HORARIO_DE_CUADRILLAS:
        salida["porque"] = ("Falta el horario de las cuadrillas: sin él, el "
                            "Supervisor no arma.")
    elif not jornada.abierta:
        salida["porque"] = {
            capacidad.FERIADO: "Ese día es feriado y no tiene horario.",
            capacidad.CERRADA: "Ese día las cuadrillas no trabajan.",
        }.get(jornada.motivo, "Ese día no se trabaja.")
    else:
        salida["trabaja"] = True

    # 1 · LAS CUADRILLAS QUE SALDRIAN -----------------------------------------
    propuestas = adj.propuestas_en_despacho(org)
    tope = configuracion_de_reparto(org).tope_por_cuadrilla
    jornadas, zonas_de, topes, ficha, gente_de = [], {}, {}, {}, {}
    planes = []
    if salida["trabaja"]:
        demanda = adj.demanda_de_despacho(org, propuestas)
        planes = ja.planear_el_dia(org, fecha, demanda=demanda["por_zona"])
    for p in planes:
        que_haria = adj._QUE_HARIA.get((p.accion, p.motivo),
                                       f"{p.accion} ({p.motivo})")
        if p.accion == "no_se_arma":
            salida["no_salen"].append({"cuadrilla": p.cuadrilla.nombre,
                                       "porque": que_haria})
            continue
        jid = p.jornada.id if p.jornada is not None else f"nueva-{p.cuadrilla.id}"
        labor = p.labor or getattr(p.jornada, "labor", "") or ""
        jornadas.append(SimpleNamespace(id=jid, labor=labor, cuadrilla=p.cuadrilla))
        zonas_de[jid] = [str(z.id) for z in p.zonas]
        topes[jid] = p.cuadrilla.tope_diario or tope
        lider, gente = _gente(p)
        gente_de[jid] = _perfiles(p.jornada if p.jornada is not None else p)
        ficha[jid] = {"cuadrilla": p.cuadrilla.nombre, "que_haria": que_haria,
                      "labor": nombres.get(labor, labor),
                      "zonas": [z.nombre for z in p.zonas],
                      "lider": lider, "gente": gente, "tope": topes[jid]}

    #  LAS QUE YA ESTAN ARMADAS Y EL PLAN NO MIRA: las de una cuadrilla
    #  inactiva, o las de un dia que no se trabaja. Publicar les da trabajo
    #  igual (`reparto.proponer` reparte entre TODAS las jornadas del dia), asi
    #  que la simulacion tambien (auditoria del 24/10/2026).
    del_plan = {p.cuadrilla.id for p in planes}
    for j in (JornadaDeCuadrilla.objects
              .filter(org=org, fecha=fecha)
              .exclude(cuadrilla_id__in=del_plan)
              .select_related("cuadrilla", "lider__user")
              .prefetch_related("zonas", "integrantes__persona")):
        jornadas.append(SimpleNamespace(id=j.id, labor=j.labor, cuadrilla=j.cuadrilla))
        zonas_de[j.id] = [str(z.id) for z in j.zonas.all()]
        topes[j.id] = j.cuadrilla.tope_diario or tope
        lider = getattr(j.lider, "user", None)
        gente_de[j.id] = _perfiles(j)
        ficha[j.id] = {
            "cuadrilla": j.cuadrilla.nombre,
            "que_haria": ("Ya está armada para un día que no se trabaja"
                          if not salida["trabaja"] else
                          "Ya está armada (la cuadrilla está inactiva)"),
            "labor": nombres.get(j.labor, j.labor),
            "zonas": [z.nombre for z in j.zonas.all()],
            "lider": ((getattr(lider, "name", "") or getattr(lider, "email", ""))
                      if lider else ""),
            "gente": [{"nombre": i.persona.nombre, "rol": i.rol}
                      for i in j.integrantes.all()],
            "tope": topes[j.id]}

    # 2 · LAS ORDENES: las que ya esperan, y las que crearia ------------------
    espera = R.lo_que_espera(org)
    decision = O.decidir(org, ahora)
    salida["hora_de_corte"] = decision["hora_de_corte"]
    salida["sin_crear_porque"] = decision["porque"]
    versiones = {str(v.id): v for v in WorkTypeVersion.objects
                 .filter(id__in=[f["version"] for f in decision["crear"]])
                 .select_related("work_type")}
    #  EL NUMERO QUE TENDRIAN (auditoria del 24/10/2026): el reparto desempata
    #  por numero, y sin el una orden simulada le ganaba el lugar a una vieja
    #  que creada de verdad le gana a ella. Se crearian en este orden, con el
    #  consecutivo siguiente al mayor de la empresa.
    siguiente = (OrdenTrabajo.objects.filter(org=org)
                 .aggregate(n=Max("numero"))["n"] or 0) + 1
    nuevas = []
    para_otro_dia = 0
    for f in decision["crear"]:
        if not f["para"]:
            continue                    # sin hora de corte no crea nada
        #  SOLO LAS DE ESE DIA: las que salen hoy no se cuentan otra vez al
        #  simular mañana, y las de mañana no salen hoy.
        if dt.date.fromisoformat(f["para"]) != fecha:
            para_otro_dia += 1
            continue
        v = OrdenTrabajo(org=org, tipo_trabajo_version=versiones.get(f["version"]),
                         prioridad=f["prioridad"], zona=f["barrio"],
                         estado_operativo=OrdenTrabajo.ASIGNADA, contexto={},
                         numero=siguiente + len(nuevas))
        #  Se crearia AHORA: el plazo operativo de la orden corre desde aca.
        v.created_at = ahora
        v.simulada = f
        nuevas.append(v)

    # 3 · EL REPARTO -----------------------------------------------------------
    barrios = R.zona_de_barrio(org)
    ordenadas = sorted([*espera["pendientes"], *nuevas],
                       key=R.clave_de_reparto(ahora=ahora))
    r = R.repartir(ordenadas, jornadas, zonas_de=zonas_de, topes=topes,
                   zona_de_barrio=barrios, dia=fecha,
                   zona_horaria=zona_horaria)

    #  LO QUE CADA CUADRILLA YA TIENE Y EL REPARTO NO MUEVE: lo asignado a mano
    #  y lo empezado. No cuenta para su tope --el reparto no lo cuenta-- pero
    #  es carga de verdad, y se dice (auditoria del 24/10/2026).
    quietas = [o.id for o in (*espera["a_mano"], *espera["empezadas"])]
    de_quien: dict = {}
    for orden_id, profile_id in (AsignacionTrabajo.objects
                                 .filter(orden_id__in=quietas)
                                 .values_list("orden_id", "profile_id")):
        de_quien.setdefault(orden_id, set()).add(profile_id)

    # LO QUE SE MUESTRA ---------------------------------------------------------
    #  El ticket y el asunto de las ordenes que ya existen, en una consulta.
    refs = [o.origen_ref for o in espera["pendientes"]
            if o.origen_sistema == "crm" and o.origen_ref]
    casos = {str(c.id): c for c in Case.objects.filter(
        org=org, id__in=[x for x in refs if _es_uuid(x)])}
    nombre_zona = {str(i): n for i, n in ZonaOperativa.objects.filter(org=org)
                   .values_list("id", "nombre")}

    def fila(o):
        f = getattr(o, "simulada", None)
        tipo = getattr(getattr(o, "tipo_trabajo_version", None), "work_type", None)
        if f is not None:
            return {"nueva": True, "orden": None, "ticket": f["ticket"],
                    "asunto": f["asunto"], "plantilla": f["plantilla"],
                    "prioridad": o.prioridad, "barrio": f["barrio"],
                    "llamar_al_cliente": f["llamar_al_cliente"]}
        caso = casos.get(str(o.origen_ref or ""))
        return {"nueva": False, "orden": o.numero,
                "ticket": (getattr(caso, "external_ticket_id", "") or "").strip(),
                "asunto": getattr(caso, "name", "") or "",
                "plantilla": getattr(tipo, "nombre", "") or "",
                "prioridad": o.prioridad, "barrio": o.zona or "",
                "llamar_al_cliente": False}

    repartidas_nuevas = 0
    for j in sorted(jornadas, key=lambda x: x.cuadrilla.nombre):
        ordenes = r["asignadas"][j.id]
        repartidas_nuevas += sum(1 for o in ordenes if hasattr(o, "simulada"))
        perfiles = gente_de.get(j.id, set())
        salida["cuadrillas"].append({
            **ficha[j.id], "carga": len(ordenes),
            "ya_tiene": sum(1 for q in de_quien.values() if q & perfiles),
            "ordenes": [fila(o) for o in ordenes]})
    for clave in salida["fuera"]:
        for o in r[clave]:
            x = fila(o)
            if clave == "sin_cuadrilla":
                labor = R._labor_de(o)
                x["labor"] = nombres.get(labor, labor)
                zona = barrios.get(R._localidad_de(o))
                x["zona"] = nombre_zona.get(str(zona), "")
            salida["fuera"][clave].append(x)

    repartidas = sum(len(v) for v in r["asignadas"].values())
    salida["cuentas"] = {
        "nuevas": len(nuevas),
        "ya_esperaban": len(espera["pendientes"]),
        "repartidas": repartidas,
        "repartidas_nuevas": repartidas_nuevas,
        "repartidas_existentes": repartidas - repartidas_nuevas,
        "afuera": sum(len(v) for v in salida["fuera"].values()),
        "nuevas_para_otro_dia": para_otro_dia,
        "no_se_crearian": len(decision["no_se_crea"]),
        "atadas": len(decision["atadas"]),
        "a_mano": len(espera["a_mano"]),
        "empezadas": len(espera["empezadas"]),
    }
    return salida


def _perfiles(jornada_o_plan) -> set:
    """Las cuentas de la gente de una jornada (o de un plan): el lider y quien
    de los integrantes tenga cuenta. Para ver que ya tiene asignado."""
    lider = getattr(jornada_o_plan, "lider", None)
    perfiles = {lider.id} if lider is not None else set()
    integrantes = getattr(jornada_o_plan, "integrantes", None)
    if hasattr(integrantes, "all"):
        personas = [i.persona for i in integrantes.all()]
    else:
        personas = [persona for persona, _rol in (integrantes or [])]
    perfiles |= {p.profile_id for p in personas if getattr(p, "profile_id", None)}
    return perfiles


def _es_uuid(texto) -> bool:
    import uuid

    try:
        uuid.UUID(str(texto))
    except (ValueError, TypeError):
        return False
    return True
