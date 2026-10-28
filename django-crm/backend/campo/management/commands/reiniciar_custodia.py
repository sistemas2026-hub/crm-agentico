"""
================================================================================
 REINICIAR LA CUSTODIA DE UNA PERSONA  --  28/10/2026
================================================================================
Borra TODO el historial de material de UNA persona: lo que se le despacho, lo
que consumio, lo que devolvio, sus actas de entrega y de devolucion y sus
incidencias. Para dejar en limpio una cuenta que se uso para probar.

Pedido del usuario el 28/10/2026: la cuenta de un tecnico usada en pruebas
quedo con el cierre de jornada bloqueado --diferencias negativas en nueve
materiales y cinco equipos con serie sin resolver-- y se pidio «limpiar y
empezar otra vez».

VA CONTRA LA REGLA DEL MODULO, Y POR ESO ES UN COMANDO Y NO UN BOTON
--------------------------------------------------------------------
El inventario no borra: cada correccion es un hecho nuevo, y la existencia sale
de sumar movimientos. Esto existe para datos de PRUEBA. No tiene pantalla, pide
la organizacion y el correo de la cuenta, y por defecto NO BORRA: muestra que
borraria y como quedaria cada bodega. Borra solo con `--aplicar`.

POR QUE BORRAR ES CORRECTO, CUANDO LO ES
----------------------------------------
Si todo lo de esta persona salio de una bodega y volvio a una bodega --o se
gasto en una orden--, borrar esos movimientos deja cada bodega como estaba antes
de la prueba. El simulacro lo muestra por bodega y material: ahora -> despues.
Cada equipo con serie vuelve a donde lo deja su libro sin esos movimientos
(`posicion_recalculada`, la misma cuenta que usa el inventario).

NO LO HACE, Y LO DICE (falla cerrado)
------------------------------------
- Material que paso entre esta persona y otra (una transferencia, o un
  movimiento desde o hacia la custodia de otro): borrarlo cambiaria la cuenta
  del otro.
- Material que entro al sistema DIRECTO a su custodia (una entrada o un ajuste
  sin bodega de origen): si despues volvio a una bodega, borrarlo haria
  desaparecer de esa bodega algo que existe.
- Una bodega que quedaria en negativo.

    python manage.py reiniciar_custodia --org <id> --tecnico <correo>
    python manage.py reiniciar_custodia --org <id> --tecnico <correo> --aplicar
================================================================================
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from common.models import Org, Profile
from common.tasks import set_rls_context


def _texto(cantidad: Decimal) -> str:
    """«10» y no «10.000»: el inventario guarda tres decimales."""
    return f"{cantidad.normalize():f}" if cantidad == cantidad.to_integral() else f"{cantidad:f}"


def planear(org, profile) -> dict:
    """Que se borraria y que pasaria. No escribe nada."""
    from campo.inventario import UbicacionDeActivo, UbicacionInventario
    from campo.models import (
        ActaDeDevolucion,
        EntregaDeKit,
        IncidenciaDeMaterial,
        ItemDeKit,
        MovimientoDeMaterial,
        TransferenciaDeMaterial,
    )
    from campo.services import inventario as inv

    custodia = UbicacionInventario.objects.filter(
        org=org, tipo=UbicacionInventario.TECNICO, profile=profile).first()
    de_esta = Q(profile=profile)
    if custodia is not None:
        de_esta |= Q(ubicacion_origen=custodia) | Q(ubicacion_destino=custodia)
    candidatos = list(MovimientoDeMaterial.objects.filter(org=org).filter(de_esta)
                      .select_related("material", "ubicacion_origen",
                                      "ubicacion_destino", "orden"))

    #  SOLO LO DE SU CUSTODIA. `profile` no alcanza: una entrada a bodega guarda
    #  la cuenta de quien la REGISTRO (`inventario_views`), y eso es material
    #  real de la bodega. Se toma lo que entra o sale de su custodia, y sus
    #  consumos y devoluciones --los que el cierre de jornada le cuenta a ella,
    #  esten donde esten--.
    def de_su_custodia(m) -> bool:
        if custodia is not None and custodia.id in (m.ubicacion_origen_id,
                                                    m.ubicacion_destino_id):
            return True
        return m.profile_id == profile.id and m.tipo in (
            MovimientoDeMaterial.CONSUMO, MovimientoDeMaterial.DEVOLUCION)

    movs = [m for m in candidatos if de_su_custodia(m)]
    ajenos = len(candidatos) - len(movs)
    ids = {m.id for m in movs}
    bloqueos = []

    #  ENTRE ESTA PERSONA Y OTRA.
    def de_otro(u):
        return (u is not None and u.tipo == UbicacionInventario.TECNICO
                and u.profile_id != profile.id)

    cruzados = [m for m in movs if de_otro(m.ubicacion_origen) or de_otro(m.ubicacion_destino)]
    if cruzados:
        bloqueos.append(f"{len(cruzados)} movimiento(s) pasan por la custodia de otra persona.")
    transferencias = TransferenciaDeMaterial.objects.filter(org=org).filter(
        Q(entrega=profile) | Q(recibe=profile)).count()
    if transferencias:
        bloqueos.append(f"{transferencias} transferencia(s) con otra persona.")

    #  LO QUE ENTRO DIRECTO A SU CUSTODIA.
    directas = [m for m in movs if custodia is not None
                and m.ubicacion_destino_id == custodia.id and m.ubicacion_origen_id is None
                and m.tipo != MovimientoDeMaterial.DEVOLUCION]
    if directas:
        bloqueos.append(
            f"{len(directas)} movimiento(s) entraron material directo a su custodia, sin "
            "bodega de origen: borrarlos haria desaparecer material que existe.")

    #  CADA BODEGA: ahora -> despues.
    cambio = defaultdict(Decimal)
    for m in movs:
        if m.estado == MovimientoDeMaterial.CONFLICTO:
            continue
        for u, signo in ((m.ubicacion_destino, -1), (m.ubicacion_origen, 1)):
            if u is not None and u.tipo != UbicacionInventario.TECNICO:
                cambio[(u, m.material)] += signo * m.cantidad
    bodegas = []
    for (u, material), delta in sorted(cambio.items(), key=lambda x: (x[0][0].nombre, x[0][1].nombre)):
        if delta == 0:
            continue
        ahora = inv.existencia(u, material)
        bodegas.append({"bodega": u.nombre, "material": material.nombre,
                        "ahora": ahora, "despues": ahora + delta})
        if ahora + delta < 0:
            bloqueos.append(f"{u.nombre} quedaria en negativo de {material.nombre}.")

    #  LOS EQUIPOS CON SERIE: donde quedan sin estos movimientos.
    series = []
    for ua in (UbicacionDeActivo.objects.filter(movimiento_id__in=ids)
               .select_related("activo", "activo__material")):
        a = ua.activo
        anterior = (MovimientoDeMaterial.objects
                    .filter(org=org, material=a.material, serie=a.serie)
                    .exclude(id__in=ids).exclude(estado__in=inv._NO_CUENTAN)
                    .order_by("-ocurrido_en", "-created_at")
                    .select_related("ubicacion_destino").first())
        if anterior is None:
            bloqueos.append(f"El equipo {a.serie} no tiene historia fuera de esta persona: "
                            "borrarla haria desaparecer un equipo que existe.")
            destino = "—"
        elif anterior.ubicacion_destino is None:
            destino = "instalado, consumido o dado de baja (su movimiento anterior)"
        else:
            destino = anterior.ubicacion_destino.nombre
        series.append({"serie": a.serie, "material": a.material.nombre, "vuelve_a": destino,
                       "activo": a})

    entregas = EntregaDeKit.objects.filter(org=org, profile=profile)
    ordenes = sorted({m.orden.numero for m in movs if m.orden_id})
    return {
        "custodia": custodia,
        "movimientos": movs,
        "ids": ids,
        "cuentas": {
            "movimientos": len(movs),
            "actas de entrega": entregas.count(),
            "lineas de acta": ItemDeKit.objects.filter(entrega__in=entregas).count(),
            "actas de devolucion": ActaDeDevolucion.objects.filter(org=org, profile=profile).count(),
            "incidencias": IncidenciaDeMaterial.objects.filter(org=org, profile=profile).count(),
        },
        "ordenes_con_consumo": ordenes,
        "ajenos": ajenos,
        "bodegas": bodegas,
        "series": series,
        "bloqueos": bloqueos,
    }


def aplicar(org, profile, plan) -> None:
    """Borra lo planeado y recoloca los equipos con serie. En una transaccion."""
    from campo.inventario import UbicacionDeActivo
    from campo.models import (
        ActaDeDevolucion,
        EntregaDeKit,
        IncidenciaDeMaterial,
        ItemDeKit,
        MovimientoDeMaterial,
    )
    from campo.services import inventario as inv

    activos = [s["activo"] for s in plan["series"]]
    #  El indice de cada equipo apunta a su ultimo movimiento y no deja
    #  borrarlo: se suelta primero y se rearma desde el libro despues.
    UbicacionDeActivo.objects.filter(activo__in=activos).delete()
    IncidenciaDeMaterial.objects.filter(org=org, profile=profile).delete()
    ActaDeDevolucion.objects.filter(org=org, profile=profile).delete()
    entregas = EntregaDeKit.objects.filter(org=org, profile=profile)
    ItemDeKit.objects.filter(entrega__in=entregas).delete()
    entregas.delete()
    MovimientoDeMaterial.objects.filter(org=org, id__in=plan["ids"]).delete()
    for activo in activos:
        ubicacion, movimiento = inv.posicion_recalculada(activo)
        if movimiento is not None:
            inv._mover_activo(activo, ubicacion, movimiento)


class Command(BaseCommand):
    help = ("Borra el historial de material de UNA cuenta usada para probar. "
            "Por defecto solo muestra que haria; borra con --aplicar.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Id de la organizacion.")
        parser.add_argument("--tecnico", required=True, help="Correo de la cuenta.")
        parser.add_argument("--aplicar", action="store_true",
                            help="Borra. Sin esto, solo muestra que borraria.")

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValidationError, ValueError):
            raise CommandError("No existe una organización con ese id.")
        set_rls_context(org.id)
        correo = (options["tecnico"] or "").strip()
        profile = (Profile.objects.filter(org=org, user__email__iexact=correo)
                   .select_related("user").first())
        if profile is None:
            raise CommandError("No hay una cuenta con ese correo en esa organización.")

        plan = planear(org, profile)
        w = self.stdout.write
        w(f"Cuenta: {correo}")
        for que, n in plan["cuentas"].items():
            w(f"  {que}: {n}")
        if plan["ordenes_con_consumo"]:
            w("  órdenes con material registrado (se borra ese registro): "
              + ", ".join(f"#{n}" for n in plan["ordenes_con_consumo"]))
        if plan["ajenos"]:
            w(f"  {plan['ajenos']} movimiento(s) que registró esta cuenta pero no son "
              "de su custodia (por ejemplo entradas a bodega): NO se tocan.")
        if plan["bodegas"]:
            w("Cada bodega, ahora -> después:")
            for b in plan["bodegas"]:
                w(f"  {b['bodega']} · {b['material']}: {_texto(b['ahora'])} -> {_texto(b['despues'])}")
        if plan["series"]:
            w("Equipos con serie:")
            for s in plan["series"]:
                w(f"  {s['serie']} ({s['material']}): vuelve a {s['vuelve_a']}")
        if plan["bloqueos"]:
            for b in plan["bloqueos"]:
                w(f"NO SE PUEDE: {b}")
            raise CommandError("No se borró nada.")
        if not plan["cuentas"]["movimientos"] and not plan["cuentas"]["actas de entrega"]:
            w("No tiene historial de material: no hay nada que borrar.")
            return
        if not options["aplicar"]:
            w("SIMULACRO: no se borró nada. Si lo de arriba es lo esperado, repetir con --aplicar.")
            return
        #  Se vuelve a planear ADENTRO de la transaccion: lo que se borra es lo
        #  que hay en ese momento, no lo que habia al imprimir el simulacro.
        with transaction.atomic():
            set_rls_context(org.id)
            plan = planear(org, profile)
            if plan["bloqueos"]:
                raise CommandError("Cambió algo mientras tanto: " + " ".join(plan["bloqueos"]))
            aplicar(org, profile, plan)
        w("Listo: su historial de material quedó en cero.")
