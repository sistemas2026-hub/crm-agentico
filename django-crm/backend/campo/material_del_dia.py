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
- Que kit: el que una persona eligio para la labor (`Labor.plantilla_de_kit`);
  si nadie eligio, lo elige el Supervisor (`kit_que_elige`, por el nombre).
- De donde: la bodega que una persona eligio para la cuadrilla
  (`Cuadrilla.bodega`); si nadie eligio, la elige el Supervisor
  (`bodega_que_elige`: la unica, la que nombra su zona, o la de la que ya le
  despacharon a su lider).
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

    kits = list(PlantillaDeKit.objects.filter(org=org, activa=True).order_by("nombre"))
    bodegas = list(UbicacionInventario.objects.filter(
        org=org, tipo=UbicacionInventario.BODEGA).order_by("nombre"))

    def labor(lab):
        #  Lo que elegiria el Supervisor si nadie eligiera: para que el panel
        #  muestre contra que se corrige.
        kit, motivo = kit_que_elige(lab.nombre, kits)
        return {"codigo": lab.codigo, "nombre": lab.nombre,
                "kit": str(lab.plantilla_de_kit_id) if lab.plantilla_de_kit_id else None,
                "elige_el_supervisor": kit.nombre if kit else "", "motivo": motivo}

    def cuadrilla(c):
        bodega, motivo = bodega_que_elige(
            org, [z.nombre for z in c.zonas_habituales.all()],
            c.lider if c.lider_id and c.lider.is_active else None, bodegas)
        return {"id": str(c.id), "nombre": c.nombre,
                "bodega": str(c.bodega_id) if c.bodega_id else None,
                "elige_el_supervisor": bodega.nombre if bodega else "", "motivo": motivo}

    return {
        "labores": [labor(lab) for lab in
                    Labor.objects.filter(org=org, activa=True).order_by("nombre")],
        "cuadrillas": [cuadrilla(c) for c in
                       Cuadrilla.objects.filter(org=org, activa=True)
                       .select_related("lider").prefetch_related("zonas_habituales")
                       .order_by("nombre")],
        "kits": [{"id": str(p.id), "nombre": p.nombre} for p in kits],
        "bodegas": [{"id": str(u.id), "nombre": u.nombre} for u in bodegas],
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
# Lo que elige el Supervisor cuando nadie lo eligio (28/10/2026)
# ---------------------------------------------------------------------------
#
#  Pedido del usuario al ver el panel de configuracion: «la idea era que lo
#  hiciera el Supervisor». El kit de cada labor y la bodega de cada cuadrilla
#  los DEDUCE el codigo, con una regla que se puede leer y un motivo que se
#  muestra; cuando no puede deducirlo, lo dice y no adivina. Lo que una persona
#  eligio en el panel manda siempre: el panel es para corregir al Supervisor.

#: Una palabra «se parece» a otra si comparten estas primeras letras:
#: «instalac(ion)» e «instalac(iones)», «soport(e)» y «soport(e)».
RAIZ = 6
#: Las palabras mas cortas no cuentan: «de», «en», «kit».
LARGO_MINIMO = 5
#: En el nombre de una bodega, las palabras de menos letras son codigos
#: («BOG», «BOF», «SAB»), no lugares.
LARGO_DE_LUGAR = 4

POR_UNA_PERSONA = "lo eligió una persona"


def _palabras(texto: str) -> list[str]:
    """Sin tildes, en minuscula, solo letras y numeros."""
    import unicodedata

    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return "".join(ch if ch.isalnum() else " " for ch in s).split()


def _raices(texto: str) -> set:
    return {p[:RAIZ] for p in _palabras(texto) if len(p) >= LARGO_MINIMO}


def kit_que_elige(nombre_de_labor: str, kits) -> tuple:
    """(kit, motivo) o (None, motivo): el kit cuyo nombre comparte mas raices
    con el de la labor. Empate: no elige. Ninguno: esa labor no carga."""
    raices = _raices(nombre_de_labor)
    puntos = [(len(raices & _raices(k.nombre)), k) for k in kits]
    mejor = max((n for n, _ in puntos), default=0)
    mejores = [k for n, k in puntos if n == mejor and n > 0]
    if len(mejores) == 1:
        return mejores[0], f"se parece por el nombre a «{nombre_de_labor}»"
    if mejores:
        return None, (f"«{nombre_de_labor}» se parece a más de un kit "
                      f"({', '.join(k.nombre for k in mejores)}): no elijo")
    return None, f"ningún kit se parece a «{nombre_de_labor}»: no carga material"


def bodega_que_elige(org, zonas, lider, bodegas) -> tuple:
    """(bodega, motivo) o (None, motivo). En este orden: la unica bodega; la
    que nombra su zona («Soledad zona 1» -> «BOG-SOLEDAD»); la de la que ya le
    despacharon a su lider. Mas de una que cumple: no elige."""
    from django.db.models import Count

    from campo.models import MovimientoDeMaterial

    if len(bodegas) == 1:
        return bodegas[0], "es la única bodega"
    if not bodegas:
        return None, "la empresa no tiene bodegas"
    textos = ["".join(_palabras(z)) for z in zonas]
    nombran = [b for b in bodegas
               if any(p in t for p in _palabras(b.nombre) if len(p) >= LARGO_DE_LUGAR
                      for t in textos)]
    if len(nombran) == 1:
        return nombran[0], "su zona la nombra"
    if len(nombran) > 1:
        return None, "su zona nombra a más de una bodega: no elijo"
    if lider is not None:
        filas = list(MovimientoDeMaterial.objects
                     .filter(org=org, tipo=MovimientoDeMaterial.DESPACHO, profile=lider,
                             ubicacion_origen__in=bodegas)
                     .values("ubicacion_origen").annotate(n=Count("id")).order_by("-n")[:2])
        if filas and (len(filas) == 1 or filas[0]["n"] > filas[1]["n"]):
            elegida = next(b for b in bodegas if b.id == filas[0]["ubicacion_origen"])
            return elegida, "de ahí le despacharon antes a su líder"
    return None, ("no sé de qué bodega carga: su zona no nombra ninguna y a su líder "
                  "no le despacharon antes")


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
# El acta del dia: la que deja la carga del Supervisor (fase 3)
# ---------------------------------------------------------------------------

#: Las actas que carga el Supervisor empiezan asi. Las lee el reporte de
#: entregas para decir «la cargo el Supervisor».
PREFIJO_DE_ACTA = "MAT-"


def acta_de(fecha, jornada_id) -> str:
    """La clave del material de UNA jornada UN dia. Fija: `despachar` es
    idempotente por acta, y eso es lo que impide cargar dos veces."""
    return f"{PREFIJO_DE_ACTA}{fecha:%Y%m%d}-{str(jornada_id)[:8]}"


def cargadas(org, actas) -> dict:
    """{acta: cuando se cargo} de las que ya se cargaron: por su acta de
    entrega, o por la reserva de sus equipos con serie."""
    from campo.inventario_operacion import ReservaDeMaterial
    from campo.models import EntregaDeKit

    actas = [a for a in actas if a]
    salida = dict(EntregaDeKit.objects.filter(org=org, acta__in=actas)
                  .values_list("acta", "entregado_en"))
    for motivo, en in (ReservaDeMaterial.objects
                       .filter(org=org, motivo__startswith=PREFIJO_DE_ACTA)
                       .values_list("motivo", "created_at")):
        acta = motivo.split(" ", 1)[0]
        if acta in actas:
            salida.setdefault(acta, en)
    return salida


def _zona_de_la_empresa(org):
    from campo.reparto import _zona_de
    return _zona_de(org)


# ---------------------------------------------------------------------------
# La propuesta del dia
# ---------------------------------------------------------------------------

def propuesta(org, fecha) -> dict:
    """Lo que se cargaria `fecha`, lista para la pantalla. NO ESCRIBE.

    Lo de `calcular`, sin los objetos internos (las claves con «_»).
    """
    return _serializable(calcular(org, fecha))


def calcular(org, fecha) -> dict:
    """Lo que se cargaria `fecha`. NO ESCRIBE. Ver el encabezado. Cada fila
    lleva tambien los objetos que necesita la carga (fase 3):
    `_lider`, `_bodega` y, en cada linea, `_material`.

        {"fecha", "cuadrillas": [{jornada, cuadrilla, labor, lider, kit,
                                  bodega, peso, lineas: [linea], avisos: [str]}],
         "bodegas": [{bodega, material, unidad, disponible, pedido, repartido,
                      falta}],
         "cuentas": {cuadrillas, completas, con_faltantes, sin_carga}}
    """
    from campo import dia_publicado
    from campo.cuadrillas import JornadaDeCuadrilla, destinatarios
    from campo.inventario import UbicacionInventario
    from campo.inventario_operacion import PlantillaDeKit
    from campo.labores import Labor, nombres_de_labor
    from campo.services import inventario as inv
    from campo.services.inventario_operacion import libre

    jornadas = list(
        JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)
        .select_related("cuadrilla", "cuadrilla__bodega", "cuadrilla__lider", "lider")
        .prefetch_related("zonas", "cuadrilla__zonas_habituales")
        .order_by("cuadrilla__nombre"))
    kit_de = {lab.codigo: lab.plantilla_de_kit for lab in
              Labor.objects.filter(org=org).select_related("plantilla_de_kit")}
    kits = list(PlantillaDeKit.objects.filter(org=org, activa=True).order_by("nombre"))
    bodegas = list(UbicacionInventario.objects.filter(
        org=org, tipo=UbicacionInventario.BODEGA).order_by("nombre"))
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
        nombre_de_labor = nombres.get(j.labor, j.labor)
        #  LO QUE ELIGIO UNA PERSONA MANDA; si no, elige el Supervisor.
        kit = kit_de.get(j.labor)
        if kit is not None:
            kit_por = POR_UNA_PERSONA
        else:
            kit, kit_por = kit_que_elige(nombre_de_labor, kits)
        bodega = j.cuadrilla.bodega
        if bodega is not None:
            bodega_por = POR_UNA_PERSONA
        else:
            #  LAS ZONAS DEL DIA MANDAN; las habituales solo si ese dia no
            #  tiene. Sumadas, una cuadrilla que hoy sale a Sabanagrande pero
            #  tiene Soledad entre sus habituales nombraba a las dos bodegas y
            #  quedaba sin elegir (captura del usuario, 28/10/2026).
            zonas = ([z.nombre for z in j.zonas.all()]
                     or [z.nombre for z in j.cuadrilla.zonas_habituales.all()])
            bodega, bodega_por = bodega_que_elige(org, zonas, lider, bodegas)
        fila = {"jornada": str(j.id), "cuadrilla": j.cuadrilla.nombre,
                "labor": nombre_de_labor,
                "lider": inv.nombre_de(lider) if lider is not None else "",
                "kit": kit.nombre if kit is not None else "", "kit_por": kit_por,
                "bodega": bodega.nombre if bodega is not None else "",
                "bodega_por": bodega_por,
                "peso": peso.get(str(j.id), 0), "lineas": [], "avisos": [],
                "_lider": lider, "_bodega": bodega,
                "acta": acta_de(fecha, j.id), "cargado_en": None}
        filas.append(fila)
        if kit is None:
            fila["avisos"].append(kit_por[:1].upper() + kit_por[1:] + ".")
            continue
        if bodega is None:
            fila["avisos"].append(bodega_por[:1].upper() + bodega_por[1:] + ".")
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
                    "asignado": CERO, "falta": CERO, "_material": m}
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
            #  Solo lo grave va como aviso propio: salir sin un equipo con
            #  serie. Lo que falta de cada material va en su linea.
            if item["falta"] > 0 and item["serializado"] and item["asignado"] == 0:
                fila["avisos"].append(
                    f"Sale sin {material.nombre}: no puede hacer el trabajo que lo necesita.")
        resumen.append({"bodega": bodega.nombre, "material": material.nombre,
                        "unidad": material.unidad, "disponible": disponible,
                        "pedido": pedido, "repartido": repartido,
                        "falta": pedido - repartido})

    #  UN SOLO MENSAJE POR CUADRILLA cuando el kit no se completa, y primero:
    #  una linea «Faltan …» por material llenaba la tarjeta (captura del
    #  usuario, 28/10/2026: «que deje un mensaje que le falta material para
    #  completar el kit pero puede salir con lo que hay en bodega»).
    for fila in filas:
        incompletos = sum(1 for i in fila["lineas"] if i["falta"] > 0)
        if incompletos:
            fila["avisos"].insert(0, (
                f"Le falta material para completar el kit ({incompletos} de "
                f"{len(fila['lineas'])} materiales): sale con lo que hay en bodega."))

    #  SI YA SE CARGO HOY (fase 3): el acta del dia de esa jornada, o la
    #  reserva de sus equipos con serie cuando no habia nada mas que cargar.
    cuando = cargadas(org, [f["acta"] for f in filas])
    zona = _zona_de_la_empresa(org)
    for fila in filas:
        en = cuando.get(fila["acta"])
        fila["cargado_en"] = en.astimezone(zona).isoformat() if en else None

    def completa(f):
        return f["lineas"] and all(i["falta"] == 0 for i in f["lineas"])

    return {
        "fecha": fecha.isoformat(),
        "cuadrillas": filas,
        "bodegas": resumen,
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
        return {k: _serializable(v) for k, v in d.items() if not str(k).startswith("_")}
    if isinstance(d, list):
        return [_serializable(v) for v in d]
    if isinstance(d, Decimal):
        return _texto(d)
    return d
