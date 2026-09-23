# -*- coding: utf-8 -*-
"""
================================================================================
 CONTEXTO DE UNA PROPUESTA  --  lo que ya existe en otro modelo, resuelto
================================================================================

QUE PROBLEMA RESUELVE
---------------------
'PropuestaSupervisor' apunta a su origen con 'origen_tipo' + 'origen_id' y no
resuelve nada mas. La tabla del tablero necesita mostrar la zona, el tecnico
asignado y el numero de ticket del proveedor -- los tres EXISTEN, en
'ProgramacionOrden', 'campo.AsignacionTrabajo' y 'cases.Case'. Ninguno hace
falta crearlo; hacia falta alcanzarlo.

POR QUE EN BLOQUE Y NO EN EL SERIALIZER
---------------------------------------
Porque la lista devuelve hasta 200 propuestas y resolver una por una serian 600
consultas. Este modulo toma el lote entero y lo resuelve en cuatro, con un dict
al final. El serializer solo lee de ese dict.

LO QUE NO HACE, Y ES A PROPOSITO
--------------------------------
1. NO devuelve 'responsable_sugerido' como tecnico. Ese campo es a quien la IA
   PROPONE; el tecnico es quien tiene la orden asignada. Confundirlos afirmaria
   que alguien ya la tiene cuando puede no tenerla. Si no hay asignacion real,
   este modulo devuelve cadena vacia y la pantalla dice "Sin asignar".

2. NO devuelve coordenadas. 'campo.OrdenTrabajo' tiene gps_lat/gps_lng y
   'programacion-noc.js::leerOrden' las quita en el servidor a proposito, junto
   con el telefono: son PII. Mientras esa decision no se tome, no salen de aca.
   No estan "olvidadas" -- estan excluidas, y este comentario es el registro.

3. NO inventa un numero de caso. 'cases.Case' no tiene consecutivo legible. Lo
   que si tiene es 'external_ticket_id' cuando el caso vino de un proveedor, y
   eso es lo que viaja. Un caso sin ticket externo devuelve cadena vacia, no un
   numero fabricado a partir del UUID.
================================================================================
"""

from __future__ import annotations

from collections import defaultdict

# El unico origen que hoy alcanza una orden de trabajo. 'case' y 'actividad'
# existen como origen de una propuesta y no cuelgan de una orden: para esos, el
# contexto sale vacio, que es la respuesta correcta y no un fallo.
ORIGEN_ORDEN = "orden_trabajo"
ORIGEN_CASO = "case"

VACIO = {
    "zona": "",
    "tecnico": "",
    "ticket_externo": "",
    "proveedor_externo": "",
    "orden_numero": None,
    # El plazo operativo. 'sla_estado' es el de 'operaciones/sla.py' tal cual
    # -- VENCIDA, VENCE_PRONTO, A_TIEMPO, SIN_PLAZO, NO_APLICA,
    # DATOS_INSUFICIENTES-- y cadena vacia cuando la propuesta no cuelga de una
    # orden, que es donde vive el plazo. Los seis estados NO se colapsan: "no
    # hay plazo declarado" y "no se pudo calcular" son cosas distintas y la
    # pantalla las dice distinto.
    "sla_estado": "",
    "sla_minutos": None,
}


def _uuids(valores):
    """
    Los 'origen_id' que de verdad son un UUID.

    'origen_id' es un CharField: guarda el id de un caso, de una actividad o de
    una orden, y nada obliga a que sea un UUID valido. Filtrar aca evita que un
    valor raro tumbe la consulta entera con un DataError.
    """
    import uuid

    salida = []
    for v in valores:
        try:
            salida.append(uuid.UUID(str(v)))
        except (ValueError, AttributeError, TypeError):
            continue
    return salida


def contexto_de(org, propuestas) -> dict:
    """
    Resuelve el contexto de un lote de propuestas.

    Devuelve {id_de_propuesta (str): {zona, tecnico, ticket_externo,
    proveedor_externo, orden_numero}}. Toda propuesta del lote tiene entrada:
    las que no alcanzan nada traen el diccionario vacio, para que quien lo lea
    no tenga que distinguir "no estaba" de "no tiene".
    """
    from campo.models import AsignacionTrabajo, OrdenTrabajo
    from cases.models import Case

    from operaciones.models import ProgramacionOrden

    propuestas = list(propuestas)
    salida = {str(p.id): dict(VACIO) for p in propuestas}
    if not propuestas:
        return salida

    ids_orden = _uuids(
        p.origen_id for p in propuestas if p.origen_tipo == ORIGEN_ORDEN
    )
    ids_caso = _uuids(
        p.origen_id for p in propuestas if p.origen_tipo == ORIGEN_CASO
    )

    # --- Las ordenes: numero legible ---------------------------------------
    # El filtro por org va SIEMPRE, aqui tambien: la propuesta ya esta acotada
    # a la organizacion, pero 'origen_id' es texto libre y podria apuntar a una
    # orden de otra. Dos capas, como en el resto del CRM.
    ordenes = {}
    if ids_orden:
        # Sin '.only': 'sla.plazo_de' necesita created_at, estado_operativo y
        # el tipo de trabajo vigente. Recortar campos aqui costaria una
        # consulta extra por orden al tocarlos.
        ordenes = {
            str(o.id): o
            for o in OrdenTrabajo.objects.filter(org=org, id__in=ids_orden)
            .select_related("tipo_trabajo_version")
        }

    # --- El tecnico: la asignacion PRINCIPAL, no la sugerencia -------------
    # 'es_principal' marca al responsable. Si una orden tiene cuadrilla pero
    # nadie marcado, se queda vacia: "hay tres personas" no responde "quien
    # responde por esto".
    tecnicos = {}
    if ordenes:
        for a in (
            AsignacionTrabajo.objects.filter(
                orden_id__in=list(ordenes.keys()), es_principal=True
            )
            .select_related("profile", "profile__user")
        ):
            perfil = a.profile
            usuario = getattr(perfil, "user", None)
            nombre = ""
            if usuario is not None:
                nombre = (usuario.name or usuario.email or "").strip()
            tecnicos[str(a.orden_id)] = nombre

    # --- La zona: de la linea de programacion mas reciente ------------------
    # Una orden puede tener varias lineas (se reprograma). La zona que vale es
    # la del dia mas reciente: la de la semana pasada describe donde estuvo,
    # no donde esta.
    zonas = {}
    if ordenes:
        por_orden = defaultdict(list)
        for linea in (
            ProgramacionOrden.objects.filter(
                org=org, orden_id__in=list(ordenes.keys())
            )
            .only("orden_id", "zona", "dia")
            .order_by("orden_id", "-dia")
        ):
            por_orden[str(linea.orden_id)].append(linea)
        for orden_id, lineas in por_orden.items():
            for linea in lineas:
                if linea.zona:
                    zonas[orden_id] = linea.zona
                    break

    # --- Los casos: el ticket del proveedor --------------------------------
    casos = {}
    if ids_caso:
        casos = {
            str(c.id): c
            for c in Case.objects.filter(org=org, id__in=ids_caso)
            .only("id", "provider", "external_ticket_id")
        }

    # --- El plazo operativo ------------------------------------------------
    # El calendario se busca UNA vez para el lote: 'get_default_calendar' no
    # cachea, y sin esto serian 200 consultas identicas.
    plazos = {}
    if ordenes:
        from business_hours.calendar import get_default_calendar

        from operaciones import sla

        calendario = get_default_calendar(org.id)
        for orden_id, orden in ordenes.items():
            p = sla.plazo_de(orden, calendario=calendario)
            plazos[orden_id] = {
                "sla_estado": p["estado"] or "",
                # Lo que falta cuando vence, lo que sobra cuando no. La
                # pantalla ya sabe cual es por el estado.
                "sla_minutos": (p["minutos_atraso"] if p["estado"] == sla.VENCIDA
                                else p["minutos_restantes"]),
            }

    for p in propuestas:
        clave = str(p.id)
        origen = str(p.origen_id)
        if p.origen_tipo == ORIGEN_ORDEN and origen in ordenes:
            salida[clave].update({
                "orden_numero": ordenes[origen].numero,
                "tecnico": tecnicos.get(origen, ""),
                "zona": zonas.get(origen, ""),
                **plazos.get(origen, {}),
            })
        elif p.origen_tipo == ORIGEN_CASO and origen in casos:
            caso = casos[origen]
            salida[clave].update({
                "ticket_externo": caso.external_ticket_id or "",
                "proveedor_externo": caso.provider or "",
            })

    return salida
