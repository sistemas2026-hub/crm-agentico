# -*- coding: utf-8 -*-
"""
================================================================================
 EL DINERO QUE RECIBE EL TECNICO  --  26/11/2026
================================================================================
El usuario: *«falta aun registrar el dinero que recibe el tecnico»*. Decidio:

* el tecnico cobra en la casa el valor de la instalacion y los equipos o el
  material extra, SOLO EN EFECTIVO, y ESCRIBE cuanto recibio;
* queda en Dexter y la oficina lo recibe: ve cuanto debe entregar cada tecnico
  y marca «recibido». NO toca WispHub.

DONDE SE ANOTA: EN LA PLANTILLA, NO EN UNA COLA NUEVA
-----------------------------------------------------
Un campo de numero de la plantilla puede llevar la marca `dinero`
(`campo/plantillas.py`). Asi lo que se cobra lo decide cada empresa en su
formato --que conceptos, en que paso, si es obligatorio-- y viaja como
cualquier otro dato de la orden: se anota sin señal y sube solo. Una cola
propia en el telefono habria repetido, para dos numeros, todo lo que los datos
de la orden ya resuelven.

LO QUE SE GUARDA ACA: LAS ENTREGAS, NO LOS COBROS
-------------------------------------------------
El cobro es el dato de la orden. Lo nuevo es cuando la oficina RECIBE ese
dinero del tecnico (`EntregaDeDinero`): una fila por orden y entrega, que no
se borra. Lo pendiente se CALCULA --lo cobrado menos lo entregado-- y no se
guarda: si el tecnico corrige la cifra despues de entregar, la diferencia
aparece sola, en cualquiera de las dos direcciones.

RECIBIR EXIGE LA CIFRA QUE SE VIO
---------------------------------
La pantalla manda, por cada orden, el monto que mostraba. Si en el medio el
tecnico cambio la cifra (o alguien ya la recibio), no se recibe: se dice que
cambio. Recibir «lo que haya» seria firmar por una plata que nadie conto.
================================================================================
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile


class EntregaDeDinero(BaseModel):
    """La oficina recibio del tecnico el dinero de una orden."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="entregas_de_dinero")
    orden = models.ForeignKey("campo.OrdenTrabajo", on_delete=models.CASCADE,
                              related_name="entregas_de_dinero")
    #  De quien se recibio: el tecnico principal de la orden en ese momento.
    tecnico = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="dinero_entregado")
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    recibido_por = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="dinero_recibido")
    recibido_en = models.DateTimeField()

    class Meta:
        db_table = "campo_entrega_de_dinero"
        verbose_name = "Entrega de dinero"
        ordering = ["-recibido_en"]


class DineroInvalido(ValueError):
    """Lo que se pidio recibir no se puede recibir asi. El texto va tal cual."""


class DineroCambio(ValueError):
    """La cifra cambio desde que la pantalla la mostro. El texto va tal cual."""


def campos_de_dinero(esquema) -> list[dict]:
    """Los campos de la plantilla que son dinero, en su orden: [{id, titulo}]."""
    return [{"id": str(c.get("id")), "titulo": str(c.get("titulo") or c.get("id"))}
            for c in ((esquema or {}).get("campos") or [])
            if isinstance(c, dict) and c.get("dinero") and c.get("id")]


def _monto(valor) -> Decimal:
    """Lo anotado, como plata. Lo que no es un numero positivo no cuenta."""
    if isinstance(valor, bool) or valor in (None, ""):
        return Decimal(0)
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return d if d.is_finite() and d > 0 else Decimal(0)


def _numero(d: Decimal):
    """Para el JSON: entero si no tiene centavos."""
    return int(d) if d == d.to_integral_value() else float(d)


def _principal(orden):
    """El tecnico principal de la orden (el que cobro), o el primero."""
    asignaciones = list(orden.asignaciones.all())
    return next((a.profile for a in asignaciones if a.es_principal),
                asignaciones[0].profile if asignaciones else None)


def _versiones_con_dinero(org) -> dict:
    from campo.models import WorkTypeVersion

    salida = {}
    for v in WorkTypeVersion.objects.filter(work_type__org=org).only("id", "esquema"):
        campos = campos_de_dinero(v.esquema)
        if campos:
            salida[v.id] = campos
    return salida


def _cuentas(org, ordenes=None) -> list[dict]:
    """Cada orden con dinero cobrado: sus conceptos, lo cobrado, lo entregado
    y lo pendiente. Si `ordenes` viene, solo esas (ya bloqueadas)."""
    from django.db.models import Sum

    from campo.models import OrdenTrabajo

    versiones = _versiones_con_dinero(org)
    if not versiones:
        return []
    if ordenes is None:
        ordenes = (OrdenTrabajo.objects
                   .filter(org=org, tipo_trabajo_version_id__in=list(versiones))
                   .exclude(estado_operativo=OrdenTrabajo.CANCELADA)
                   .prefetch_related("asignaciones__profile__user"))
    entregado = {f["orden_id"]: f["total"] or Decimal(0) for f in (
        EntregaDeDinero.objects.filter(org=org, orden__in=[o.id for o in ordenes])
        .values("orden_id").annotate(total=Sum("monto")))}
    salida = []
    for o in ordenes:
        campos = versiones.get(o.tipo_trabajo_version_id) or []
        datos = o.datos or {}
        conceptos = [{"titulo": c["titulo"], "valor": _monto(datos.get(c["id"]))} for c in campos]
        conceptos = [c for c in conceptos if c["valor"] > 0]
        cobrado = sum((c["valor"] for c in conceptos), Decimal(0))
        ya = entregado.get(o.id, Decimal(0))
        if cobrado == 0 and ya == 0:
            continue
        salida.append({"orden": o, "conceptos": conceptos, "cobrado": cobrado,
                       "entregado": ya, "pendiente": cobrado - ya, "tecnico": _principal(o)})
    return salida


def por_tecnico(org) -> dict:
    """Lo que la pantalla de la oficina necesita: cuanto tiene cada tecnico
    por entregar, de que ordenes, y las ultimas entregas."""
    from campo.services.inventario import nombre_de

    grupos: dict = {}
    for c in _cuentas(org):
        if c["pendiente"] == 0:
            continue
        t = c["tecnico"]
        clave = str(t.id) if t else ""
        g = grupos.setdefault(clave, {
            "tecnico": {"id": clave or None, "nombre": (nombre_de(t) if t else "") or "Sin técnico"},
            "pendiente": Decimal(0), "ordenes": []})
        o = c["orden"]
        g["pendiente"] += c["pendiente"]
        g["ordenes"].append({
            "orden_id": str(o.id), "numero": o.numero, "cliente": o.cliente_nombre or "",
            "conceptos": [{"titulo": x["titulo"], "valor": _numero(x["valor"])} for x in c["conceptos"]],
            "cobrado": _numero(c["cobrado"]), "entregado": _numero(c["entregado"]),
            "pendiente": _numero(c["pendiente"]),
            "actualizada_en": o.updated_at.isoformat() if o.updated_at else None,
        })
    tecnicos = sorted(grupos.values(), key=lambda g: (-g["pendiente"], g["tecnico"]["nombre"]))
    for g in tecnicos:
        g["pendiente"] = _numero(g["pendiente"])
        g["ordenes"].sort(key=lambda x: x["numero"] or 0)
    ultimas = [{
        "orden_numero": e.orden.numero, "monto": _numero(e.monto),
        "tecnico": nombre_de(e.tecnico) if e.tecnico else "",
        "recibido_por": nombre_de(e.recibido_por) if e.recibido_por else "",
        "recibido_en": e.recibido_en.isoformat(),
    } for e in (EntregaDeDinero.objects.filter(org=org)
                .select_related("orden", "tecnico__user", "recibido_por__user")[:20])]
    return {"configurado": bool(_versiones_con_dinero(org)), "tecnicos": tecnicos,
            "ultimas": ultimas}


def recibir(org, recibido_por, tecnico_id: str, ordenes: list) -> list[EntregaDeDinero]:
    """La oficina recibe del tecnico el dinero de esas ordenes, con la cifra
    que vio en la pantalla. Todo o nada."""
    from campo.models import OrdenTrabajo

    if not isinstance(ordenes, list) or not ordenes:
        raise DineroInvalido("Elige qué órdenes recibes.")
    pedidas = {}
    for x in ordenes:
        if not isinstance(x, dict) or not x.get("orden_id"):
            raise DineroInvalido("Cada orden va con su id y su monto.")
        m = x.get("monto")
        if isinstance(m, bool) or not isinstance(m, (int, float, str)):
            raise DineroInvalido("Cada orden va con su monto.")
        try:
            pedidas[str(x["orden_id"])] = Decimal(str(m))
        except (InvalidOperation, ValueError):
            raise DineroInvalido("Ese monto no es un número.") from None
    ahora = timezone.now()
    with transaction.atomic():
        bloqueadas = list(OrdenTrabajo.objects.select_for_update()
                          .filter(org=org, id__in=list(pedidas)))
        if len(bloqueadas) != len(pedidas):
            raise DineroInvalido("Alguna de esas órdenes no es de tu empresa.")
        #  Las asignaciones se leen DESPUES del bloqueo, aparte:
        #  `select_for_update` no se lleva con un prefetch de otra tabla.
        cuentas = {str(c["orden"].id): c for c in _cuentas(
            org, [OrdenTrabajo.objects.prefetch_related("asignaciones__profile__user").get(pk=o.pk)
                  for o in bloqueadas])}
        entregas = []
        for oid, monto in pedidas.items():
            c = cuentas.get(oid)
            numero = next(o.numero for o in bloqueadas if str(o.id) == oid)
            if c is None or c["pendiente"] <= 0:
                raise DineroCambio(f"La OT-{numero} ya no tiene dinero por entregar. Recarga la página.")
            t = c["tecnico"]
            if str(getattr(t, "id", "")) != str(tecnico_id or ""):
                raise DineroInvalido(f"La OT-{numero} no es de ese técnico.")
            if monto != c["pendiente"]:
                raise DineroCambio(
                    f"La OT-{numero} cambió: ahora son ${_numero(c['pendiente']):,}".replace(",", ".")
                    + ". Recarga la página y vuelve a contar.")
            entregas.append(EntregaDeDinero(org=org, orden=c["orden"], tecnico=t, monto=monto,
                                            recibido_por=recibido_por, recibido_en=ahora))
        for e in entregas:
            e.save()
    return entregas
