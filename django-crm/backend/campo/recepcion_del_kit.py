"""
================================================================================
 LA RECEPCION DEL KIT  --  28/10/2026
================================================================================
Fase 2 de SPEC/objetivos/material-del-dia.md: lo que el tecnico hace en la app
al recibir su material en la bodega. Decisiones del usuario:
  28/10  El tecnico verifica en la mañana que lo que recibio coincide con lo
         que dice la app, y confirma.
  28/10  Las ONT se atan a su serie cuando el tecnico las escanea al recibirlas
         (el Supervisor no elige series: las deja reservadas a su nombre).
  28/10  Las confirmaciones fisicas son de una persona: el sistema no cuenta
         objetos, deja todo precargado y marca la diferencia.

TRES COSAS:
  pendiente_de  lo que tiene por confirmar (actas de los ultimos dias sin
                confirmar) y por escanear (equipos reservados a su nombre).
  confirmar     «recibi todo», o lo que recibio de cada material con un motivo:
                lo que no llego queda como incidencia explicada, y asi el cierre
                de la jornada cuadra. `EntregaDeKit.confirmado_en`, que existia
                desde siempre y nadie escribia.
  escanear      la serie de un equipo: si esta en la bodega donde tiene una
                reserva a su nombre de ese material, se le despacha (bodega ->
                su custodia, con su serie) y el despacho cierra SU reserva
                (`consumir_reservas(para=...)`). Escanear es recibir: esa acta
                nace confirmada.

Solo lo suyo: cada funcion recibe la persona de la sesion y nunca toca lo de
otro. Lo que no se puede hacer se rechaza con una frase que se lee en la app.
================================================================================
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

#: Cuantos dias atras se ofrece confirmar una entrega. Las de antes de que
#: existiera la confirmacion no tienen por que aparecer como pendientes.
DIAS_PARA_CONFIRMAR = 2


class RecepcionInvalida(Exception):
    """Lo que se rechaza, con una frase para el tecnico."""


def _numero(valor) -> str:
    d = Decimal(valor)
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d:f}"


def pendiente_de(profile, org, ahora=None) -> dict:
    """{"por_confirmar": [acta], "por_escanear": [equipo]}. No escribe."""
    from django.utils import timezone

    from campo.inventario_operacion import ReservaDeMaterial
    from campo.material_del_dia import PREFIJO_DE_ACTA
    from campo.models import EntregaDeKit, MovimientoDeMaterial
    from campo.reparto import _zona_de

    zona = _zona_de(org)
    hoy = (ahora or timezone.now()).astimezone(zona).date()
    desde = dt.datetime.combine(hoy - dt.timedelta(days=DIAS_PARA_CONFIRMAR - 1),
                                dt.time.min, tzinfo=zona)
    entregas = list(EntregaDeKit.objects
                    .filter(org=org, profile=profile, confirmado_en__isnull=True,
                            entregado_en__gte=desde)
                    .prefetch_related("items__material").order_by("entregado_en"))
    bodega_de = dict(MovimientoDeMaterial.objects
                     .filter(org=org, tipo=MovimientoDeMaterial.DESPACHO,
                             datos__entrega__in=[str(e.id) for e in entregas])
                     .values_list("datos__entrega", "ubicacion_origen__nombre"))
    por_confirmar = [{
        "id": str(e.id), "acta": e.acta,
        "entregado_en": e.entregado_en.astimezone(zona).isoformat(),
        "bodega": bodega_de.get(str(e.id)) or "",
        "lineas": [{"codigo": i.material.codigo, "nombre": i.material.nombre,
                    "unidad": i.material.unidad, "cantidad": _numero(i.cantidad),
                    "serie": i.serie}
                   for i in sorted(e.items.all(), key=lambda i: (i.material.nombre, i.serie))],
    } for e in entregas]

    agrupadas = {}
    for r in (ReservaDeMaterial.objects
              .filter(org=org, reservada_por=profile, resuelta_en__isnull=True,
                      motivo__startswith=PREFIJO_DE_ACTA)
              .select_related("material", "ubicacion").order_by("created_at")):
        clave = (r.ubicacion_id, r.material_id)
        if clave not in agrupadas:
            agrupadas[clave] = {"codigo": r.material.codigo, "nombre": r.material.nombre,
                                "bodega": r.ubicacion.nombre, "cantidad": Decimal("0")}
        agrupadas[clave]["cantidad"] += r.cantidad
    por_escanear = [{**v, "cantidad": _numero(v["cantidad"])} for v in agrupadas.values()]
    return {"por_confirmar": por_confirmar, "por_escanear": por_escanear}


def confirmar(profile, org, entrega_id, *, conforme: bool, diferencias=None) -> dict:
    """Confirma UNA entrega suya. `diferencias` = [{codigo, recibido, motivo}]
    cuando no es conforme. Idempotente: confirmar dos veces no repite nada."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.utils import timezone

    from campo.models import EntregaDeKit, IncidenciaDeMaterial
    from campo.services.cierre_jornada import registrar_incidencia

    try:
        entrega = (EntregaDeKit.objects.filter(org=org, profile=profile)
                   .prefetch_related("items__material").get(pk=entrega_id))
    except (EntregaDeKit.DoesNotExist, ValidationError, ValueError):
        raise RecepcionInvalida("Esa entrega no es tuya o no existe.")
    if entrega.confirmado_en is not None:
        return {"id": str(entrega.id), "confirmado_en": entrega.confirmado_en.isoformat(),
                "ya_estaba": True}

    por_codigo = {}
    for i in entrega.items.all():
        por_codigo.setdefault(i.material.codigo, [i.material, Decimal("0")])[1] += i.cantidad
    faltantes = []
    if not conforme:
        if not diferencias:
            raise RecepcionInvalida("Decí qué no coincide: lo que recibiste de cada material.")
        for d in diferencias:
            codigo = str((d or {}).get("codigo") or "")
            if codigo not in por_codigo:
                raise RecepcionInvalida(f"El material {codigo or '(vacío)'} no está en esta entrega.")
            material, en_el_acta = por_codigo[codigo]
            try:
                recibido = Decimal(str(d.get("recibido")))
            except (InvalidOperation, TypeError, ValueError):
                raise RecepcionInvalida(f"Lo recibido de {material.nombre} no es un número.")
            if recibido < 0 or recibido > en_el_acta:
                raise RecepcionInvalida(
                    f"Lo recibido de {material.nombre} va de 0 a {_numero(en_el_acta)}.")
            motivo = " ".join(str(d.get("motivo") or "").split())
            if recibido < en_el_acta and not motivo:
                raise RecepcionInvalida(f"Falta decir por qué no llegó todo {material.nombre}.")
            if recibido < en_el_acta:
                faltantes.append((material, en_el_acta - recibido, motivo))
        if not faltantes:
            raise RecepcionInvalida("Lo que escribiste coincide con la entrega: tocá «Recibí todo».")

    with transaction.atomic():
        for material, falta, motivo in faltantes:
            registrar_incidencia(
                org=org, profile=profile, material=material,
                tipo=IncidenciaDeMaterial.OTRO, cantidad=falta,
                motivo=f"No llegó en la entrega {entrega.acta or entrega.id}: {motivo}",
                idempotency_key=f"recepcion|{entrega.id}|{material.id}")
        entrega.confirmado_en = timezone.now()
        nota = ("Al recibir: conforme." if not faltantes else
                "Al recibir faltó: " + "; ".join(
                    f"{_numero(f)} {m.unidad} de {m.nombre} ({mot})" for m, f, mot in faltantes)
                + ".")
        entrega.notas = (f"{entrega.notas}\n{nota}" if entrega.notas else nota)
        entrega.save(update_fields=["confirmado_en", "notas", "updated_at"])
    return {"id": str(entrega.id), "confirmado_en": entrega.confirmado_en.isoformat(),
            "faltantes": len(faltantes)}


def escanear(profile, org, serie: str) -> dict:
    """Recibe UN equipo con serie: de su bodega a su custodia, cerrando su
    reserva. Ver el encabezado."""
    from django.db import transaction
    from django.utils import timezone

    from campo.inventario import (
        ActivoSerializado,
        UbicacionDeActivo,
        UbicacionInventario,
    )
    from campo.inventario_operacion import ReservaDeMaterial
    from campo.material_del_dia import PREFIJO_DE_ACTA
    from campo.services import inventario as inv

    serie = " ".join(str(serie or "").split())
    if not serie:
        raise RecepcionInvalida("No se leyó ninguna serie.")
    activos = list(ActivoSerializado.objects.filter(org=org, serie__iexact=serie)
                   .select_related("material"))
    if not activos:
        raise RecepcionInvalida(f"La serie {serie} no está registrada en ninguna bodega.")

    reservas = (ReservaDeMaterial.objects
                .filter(org=org, reservada_por=profile, resuelta_en__isnull=True,
                        motivo__startswith=PREFIJO_DE_ACTA)
                .select_related("ubicacion", "material").order_by("created_at"))
    for activo in activos:
        pos = UbicacionDeActivo.objects.filter(activo=activo).select_related("ubicacion").first()
        reserva = next((r for r in reservas if r.material_id == activo.material_id), None)
        if reserva is None:
            continue
        if pos is None or pos.ubicacion is None or pos.ubicacion.tipo != UbicacionInventario.BODEGA:
            raise RecepcionInvalida(f"La serie {serie} no figura en una bodega.")
        if pos.ubicacion_id != reserva.ubicacion_id:
            raise RecepcionInvalida(
                f"La serie {serie} figura en {pos.ubicacion.nombre}, y tus "
                f"{activo.material.nombre} se apartaron en {reserva.ubicacion.nombre}.")
        acta = f"{reserva.motivo.split(' ', 1)[0]}:{activo.serie}"
        try:
            with transaction.atomic():
                entrega, _ = inv.despachar(
                    org=org, ubicacion_origen=pos.ubicacion, profile_destino=profile,
                    lineas=[{"material": activo.material, "serie": activo.serie}],
                    acta=acta, notas="Equipo escaneado por el técnico al recibirlo.")
                if entrega.confirmado_en is None:
                    entrega.confirmado_en = timezone.now()
                    entrega.save(update_fields=["confirmado_en", "updated_at"])
        except inv.DespachoInvalido as e:
            raise RecepcionInvalida(str(e))
        return {"material": activo.material.nombre, "serie": activo.serie,
                "acta": entrega.acta, "bodega": pos.ubicacion.nombre}
    nombres = ", ".join(sorted({a.material.nombre for a in activos}))
    raise RecepcionInvalida(f"No tenés {nombres} por escanear: no hay ninguno apartado a tu nombre.")
