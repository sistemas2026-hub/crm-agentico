"""
================================================================================
 EL MATERIAL DEL DIA  --  28/10/2026
================================================================================
Que kit lleva cada cuadrilla que sale un dia, de que bodega, a quien se le
carga, y que pasa si la bodega no alcanza. Ficha y decisiones:
SPEC/objetivos/material-del-dia.md.

Pedido del usuario: «el supervisor debe indicar que plantilla de material sale
… hay veces que no esta la cantidad necesaria y el supervisor debe ver como
esta programado el dia para distribuir los materiales y sus cantidades bien
entre las cuadrillas».

FASE 1: SOLO PROPONE. `propuesta` no mueve material, no reserva y no despacha:
dice lo que se cargaria. La carga la hara el Supervisor en la fase 3, con
`inventario.despachar` --el mismo camino que la bodega-- y en sombra primero.

LAS REGLAS (las decisiones del 28/10/2026)
------------------------------------------
- Que kit: el de la labor de la jornada (`Labor.plantilla_de_kit`).
- De donde: la bodega de la cuadrilla (`Cuadrilla.bodega`).
- A quien: al LIDER de la jornada (`destinatarios`), a su custodia.
- Cuanto: el kit menos lo que el lider ya tiene en custodia, nunca negativo.
- Si no alcanza: lo LIBRE de la bodega (existencia menos reservado) se reparte
  en proporcion al trabajo publicado del dia de cada cuadrilla, pesando la
  prioridad (alta 3, media 2, baja 1), sin pasarse de lo que cada una
  necesita. El reparto es por unidades, con la regla de D'Hondt: cada unidad
  va a la que tiene mas peso por unidad ya asignada.
- Lo que falta se dice por cuadrilla; una que sale sin un equipo con serie de
  su kit es una alerta: no puede hacer el trabajo que lo necesita.
================================================================================
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

#: Cuanto pesa una orden del dia al repartir lo que no alcanza.
PESO_POR_PRIORIDAD = {"alta": 3, "media": 2, "baja": 1}
PESO_SIN_PRIORIDAD = 1

CERO = Decimal("0")
UNO = Decimal("1")


class ConfiguracionInvalida(Exception):
    """Lo que se rechaza al guardar la configuracion, con una frase que se lee."""


# ---------------------------------------------------------------------------
# La configuracion: que kit lleva cada labor, de que bodega carga cada cuadrilla
# ---------------------------------------------------------------------------

def configuracion(org) -> dict:
    from campo.cuadrillas import Cuadrilla
    from campo.inventario import UbicacionInventario
    from campo.inventario_operacion import PlantillaDeKit
    from campo.labores import Labor

    return {
        "labores": [{"codigo": lab.codigo, "nombre": lab.nombre,
                     "kit": str(lab.plantilla_de_kit_id) if lab.plantilla_de_kit_id else None}
                    for lab in Labor.objects.filter(org=org, activa=True).order_by("nombre")],
        "cuadrillas": [{"id": str(c.id), "nombre": c.nombre,
                        "bodega": str(c.bodega_id) if c.bodega_id else None}
                       for c in Cuadrilla.objects.filter(org=org, activa=True).order_by("nombre")],
        "kits": [{"id": str(p.id), "nombre": p.nombre}
                 for p in PlantillaDeKit.objects.filter(org=org, activa=True).order_by("nombre")],
        "bodegas": [{"id": str(u.id), "nombre": u.nombre}
                    for u in UbicacionInventario.objects.filter(
                        org=org, tipo=UbicacionInventario.BODEGA).order_by("nombre")],
    }


def guardar_configuracion(org, datos: dict) -> dict:
    """Cambia SOLO lo que viene: `kits` = {codigo de labor: id de kit | None},
    `bodegas` = {id de cuadrilla: id de bodega | None}. Todo o nada."""
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from campo.cuadrillas import Cuadrilla
    from campo.inventario import UbicacionInventario
    from campo.inventario_operacion import PlantillaDeKit
    from campo.labores import Labor

    kits = datos.get("kits") or {}
    bodegas = datos.get("bodegas") or {}
    if not isinstance(kits, dict) or not isinstance(bodegas, dict):
        raise ConfiguracionInvalida("Formato inválido.")

    def una(modelo, ident, **filtro):
        """None si viene vacio; False si no existe en ESTA empresa."""
        if ident in (None, ""):
            return None
        try:
            return modelo.objects.filter(org=org, **filtro).get(pk=ident)
        except (modelo.DoesNotExist, ValidationError, ValueError):
            return False

    cambios_labor, cambios_cuadrilla = [], []
    for codigo, kit_id in kits.items():
        labor = Labor.objects.filter(org=org, codigo=codigo, activa=True).first()
        if labor is None:
            raise ConfiguracionInvalida(f"La labor «{codigo}» no existe.")
        kit = una(PlantillaDeKit, kit_id, activa=True)
        if kit is False:
            raise ConfiguracionInvalida("Uno de los kits no existe o está dado de baja.")
        cambios_labor.append((labor, kit))
    for cuadrilla_id, bodega_id in bodegas.items():
        cuadrilla = una(Cuadrilla, cuadrilla_id)
        if not cuadrilla:
            raise ConfiguracionInvalida("Una de las cuadrillas no existe.")
        bodega = una(UbicacionInventario, bodega_id, tipo=UbicacionInventario.BODEGA)
        if bodega is False:
            raise ConfiguracionInvalida("Una de las bodegas no existe.")
        cambios_cuadrilla.append((cuadrilla, bodega))

    with transaction.atomic():
        for labor, kit in cambios_labor:
            labor.plantilla_de_kit = kit
            labor.save(update_fields=["plantilla_de_kit", "updated_at"])
        for cuadrilla, bodega in cambios_cuadrilla:
            cuadrilla.bodega = bodega
            cuadrilla.save(update_fields=["bodega", "updated_at"])
    return configuracion(org)


# ---------------------------------------------------------------------------
# El reparto de lo que no alcanza
# ---------------------------------------------------------------------------

def repartir_lo_que_hay(pedidos: list[tuple], disponible: Decimal) -> dict:
    """`pedidos` = [(clave, necesita, peso)] en un orden estable. Devuelve
    {clave: asignado}. Si alcanza, cada una recibe lo que necesita; si no, por
    unidades con D'Hondt: la siguiente unidad va a la de mayor peso / (lo ya
    asignado + 1), entre las que todavia necesitan. Pura: no consulta nada."""
    necesita = {k: max(CERO, Decimal(n)) for k, n, _ in pedidos}
    if sum(necesita.values(), CERO) <= disponible:
        return dict(necesita)
    asignado = {k: CERO for k, _, _ in pedidos}
    peso = {k: Decimal(p) for k, _, p in pedidos}
    orden = {k: i for i, (k, _, _) in enumerate(pedidos)}
    restante = max(CERO, Decimal(disponible))
    while restante > 0:
        candidatas = [k for k in asignado if asignado[k] < necesita[k]]
        if not candidatas:
            break
        k = max(candidatas, key=lambda c: (peso[c] / (asignado[c] + 1), -orden[c]))
        paso = min(UNO, restante, necesita[k] - asignado[k])
        asignado[k] += paso
        restante -= paso
    return asignado


# ---------------------------------------------------------------------------
# La propuesta del dia
# ---------------------------------------------------------------------------

def propuesta(org, fecha) -> dict:
    """Lo que se cargaria `fecha`. NO ESCRIBE. Ver el encabezado.

        {"fecha", "cuadrillas": [{jornada, cuadrilla, labor, lider, kit,
                                  bodega, peso, lineas: [linea], avisos: [str]}],
         "bodegas": [{bodega, material, unidad, disponible, pedido, repartido,
                      falta}],
         "cuentas": {cuadrillas, completas, con_faltantes, sin_carga}}
    """
    from campo import dia_publicado
    from campo.cuadrillas import JornadaDeCuadrilla, destinatarios
    from campo.labores import Labor, nombres_de_labor
    from campo.services import inventario as inv
    from campo.services.inventario_operacion import libre

    jornadas = list(
        JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)
        .select_related("cuadrilla", "cuadrilla__bodega", "cuadrilla__lider", "lider")
        .order_by("cuadrilla__nombre"))
    kit_de = {lab.codigo: lab.plantilla_de_kit for lab in
              Labor.objects.filter(org=org).select_related("plantilla_de_kit")}
    nombres = nombres_de_labor(org)

    #  EL PESO DE CADA CUADRILLA: su trabajo publicado del dia, con la misma
    #  cuenta que muestra Programacion. Lo terminado no pide material.
    peso = defaultdict(int)
    for c in dia_publicado.del_dia(org, fecha)["cuadrillas"]:
        for o in c["ordenes"]:
            if o["estado"] in ("completada_campo", "cerrada"):
                continue
            peso[c["jornada"]] += PESO_POR_PRIORIDAD.get(o["prioridad"], PESO_SIN_PRIORIDAD)

    filas, pedidos = [], defaultdict(list)
    for j in jornadas:
        lider = destinatarios(j)["lider"]
        kit = kit_de.get(j.labor)
        bodega = j.cuadrilla.bodega
        fila = {"jornada": str(j.id), "cuadrilla": j.cuadrilla.nombre,
                "labor": nombres.get(j.labor, j.labor),
                "lider": inv.nombre_de(lider) if lider is not None else "",
                "kit": kit.nombre if kit is not None else "",
                "bodega": bodega.nombre if bodega is not None else "",
                "peso": peso.get(str(j.id), 0), "lineas": [], "avisos": []}
        filas.append(fila)
        if kit is None:
            fila["avisos"].append("Su labor no tiene kit: no carga material.")
            continue
        if bodega is None:
            fila["avisos"].append("La cuadrilla no tiene bodega: no se sabe de dónde carga.")
            continue
        if lider is None or not lider.is_active:
            fila["avisos"].append("No tiene líder con cuenta activa: no hay a quién cargarle.")
            continue
        custodia = inv.ubicacion_de_tecnico(lider, org, crear=False)
        for linea in kit.lineas.select_related("material").order_by("material__nombre"):
            m = linea.material
            en_mano = inv.existencia(custodia, m) if custodia is not None else CERO
            necesita = max(CERO, linea.cantidad - max(CERO, en_mano))
            item = {"material": m.nombre, "unidad": m.unidad,
                    "serializado": m.es_serializado, "kit": linea.cantidad,
                    "en_mano": en_mano, "necesita": necesita,
                    "asignado": CERO, "falta": CERO}
            fila["lineas"].append(item)
            pedidos[(bodega, m)].append((item, fila))

    resumen = []
    for (bodega, material), lista in sorted(pedidos.items(),
                                            key=lambda x: (x[0][0].nombre, x[0][1].nombre)):
        disponible = libre(bodega, material)
        reparto = repartir_lo_que_hay(
            [(id(item), item["necesita"], fila["peso"]) for item, fila in lista],
            disponible)
        pedido = sum((item["necesita"] for item, _ in lista), CERO)
        repartido = CERO
        for item, fila in lista:
            item["asignado"] = reparto[id(item)]
            item["falta"] = item["necesita"] - item["asignado"]
            repartido += item["asignado"]
            if item["falta"] > 0 and item["serializado"] and item["asignado"] == 0:
                fila["avisos"].append(
                    f"Sale sin {material.nombre}: no puede hacer el trabajo que lo necesita.")
            elif item["falta"] > 0:
                fila["avisos"].append(
                    f"Faltan {_texto(item['falta'])} {material.unidad} de {material.nombre}.")
        resumen.append({"bodega": bodega.nombre, "material": material.nombre,
                        "unidad": material.unidad, "disponible": disponible,
                        "pedido": pedido, "repartido": repartido,
                        "falta": pedido - repartido})

    def completa(f):
        return f["lineas"] and all(i["falta"] == 0 for i in f["lineas"])

    return {
        "fecha": fecha.isoformat(),
        "cuadrillas": [_serializable(f) for f in filas],
        "bodegas": [_serializable(b) for b in resumen],
        "cuentas": {
            "cuadrillas": len(filas),
            "completas": sum(1 for f in filas if completa(f)),
            "con_faltantes": sum(1 for f in filas if any(i["falta"] > 0 for i in f["lineas"])),
            "sin_carga": sum(1 for f in filas if not f["lineas"]),
        },
    }


def _texto(cantidad: Decimal) -> str:
    """«10» y no «10.000»."""
    return f"{cantidad.normalize():f}" if cantidad == cantidad.to_integral() else f"{cantidad:f}"


def _serializable(d):
    """Los Decimal viajan como texto sin ceros de mas: el JSON los perderia."""
    if isinstance(d, dict):
        return {k: _serializable(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_serializable(v) for v in d]
    if isinstance(d, Decimal):
        return _texto(d)
    return d
