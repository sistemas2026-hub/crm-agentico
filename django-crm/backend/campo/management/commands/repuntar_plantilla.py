# -*- coding: utf-8 -*-
"""
================================================================================
 LAS ORDENES QUE NADIE EMPEZO TOMAN LA PLANTILLA VIGENTE  --  07/11/2026
================================================================================
Una orden congela su version de plantilla al nacer y la conserva hasta cerrar.
Esa regla es correcta y no se toca: quien ya escribio respuestas contra un
formulario tiene derecho a que ese formulario no cambie debajo.

PERO UNA ORDEN QUE NADIE ABRIO NO TIENE RESPUESTAS QUE PROTEGER. Medido el
07/11/2026 en produccion, sobre `correctivo_fibra`:

    v2    asignada       1
    v3    asignada     144      <- publicada el 21/10, antes de TODO lo de hoy
    v3    en_sitio       1
    v7    asignada       6

145 ordenes abiertas colgaban de una plantilla de tres semanas atras: sin las
instrucciones de foto corregidas, sin el rango bueno, con el minimo en -28 que
le impide al tecnico anotar la senal rota que fue a arreglar. Iban a cerrar
todas asi, de a una, durante semanas.

LA CONDICION DE SEGURIDAD, Y POR QUE ES ESA
--------------------------------------------
Se repunta solo lo que nadie empezo:

    estado_operativo == asignada   ·   `datos` vacio   ·   sin evidencias

No alcanza con el estado. Un tecnico puede haber abierto la orden, escrito
media hoja y cerrado la app sin cambiar el estado; esas respuestas ya existen
y son justo las que la inmutabilidad protege. Las tres condiciones juntas
dicen una sola cosa: NO HAY NADA ESCRITO TODAVIA.

La de `en_sitio` no entra. Esa tiene a alguien adentro.

LO QUE NO HACE
--------------
**No toca `revision`.** Es el control de concurrencia de la cola offline: si
sube, la escritura que el tecnico tenga pendiente se rechaza por vieja.
Cambiar el formulario de una orden no es pisar los datos de nadie.

**No publica ni edita plantillas.** Solo mueve el puntero de la orden a la
version que YA esta publicada. Si no hay ninguna, no hace nada.

**No baja de version.** Solo repunta hacia la vigente, y salta la orden que
ya la tiene.

    python manage.py repuntar_plantilla --org rapilink
    python manage.py repuntar_plantilla --org rapilink --aplicar

Sin `--aplicar` simula: lista cuantas ordenes se moverian, desde que version,
y QUE CAMBIA en el formulario entre una y otra. Ese diff es el que hay que
leer antes de aplicar -- la diferencia entre dos versiones no es solo la que
uno fue a buscar.
================================================================================
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


def _por_id(esquema, llave):
    """`{id: definicion}` de `campos` o `evidencias`, tolerando basura."""
    salida = {}
    for item in (esquema or {}).get(llave) or []:
        if isinstance(item, dict) and item.get("id"):
            salida[item["id"]] = item
    return salida


def diferencias(viejo, nuevo) -> list[str]:
    """Que cambia del esquema `viejo` al `nuevo`, en lineas legibles.

    SE COMPARA EL ESQUEMA, NO EL NUMERO DE VERSION. Dos versiones seguidas
    pueden no diferir en nada que le importe al tecnico, y una lejana puede
    cambiar medio formulario: lo que hay que leer antes de mover 145 ordenes
    es el contenido.
    """
    lineas = []
    for llave, nombre in (("campos", "campo"), ("evidencias", "evidencia")):
        a, b = _por_id(viejo, llave), _por_id(nuevo, llave)
        for ident in sorted(set(b) - set(a)):
            lineas.append(f"+ {nombre} nuevo: {ident}")
        for ident in sorted(set(a) - set(b)):
            lineas.append(f"- {nombre} que ya no esta: {ident}")
        for ident in sorted(set(a) & set(b)):
            antes, ahora = a[ident], b[ident]
            for prop in sorted(set(antes) | set(ahora)):
                if antes.get(prop) != ahora.get(prop):
                    lineas.append(f"~ {nombre} {ident}.{prop}: "
                                  f"{antes.get(prop)!r} -> {ahora.get(prop)!r}")
    return lineas


def candidatas(org, tipo):
    """Las ordenes de ese tipo que nadie empezo. Ver el encabezado.

    EL `org=org` DE ABAJO ES REDUNDANTE, Y SE DEJA A SABIENDAS. Un `WorkType`
    pertenece a una sola empresa y `handle` ya filtra los tipos por la suya,
    asi que el tipo solo alcanza para que no se cuele una orden ajena. Medido
    el 07/11/2026: la mutacion que borra este filtro sobrevive a las 21
    guardas, y es correcto que sobreviva -- no hay conducta que cambiar.

    Quitar las DOS defensas a la vez si rompe la guarda de la empresa, que es
    la forma honesta de medir una defensa duplicada. Se conserva porque este
    comando reescribe el formulario de cientos de ordenes y la regla de
    CLAUDE.md §5 es fail-closed: olvidar fijar la empresa devuelve cero filas,
    no todas.
    """
    from campo.models import OrdenTrabajo

    return (OrdenTrabajo.objects
            .filter(org=org,
                    tipo_trabajo_version__work_type=tipo,
                    estado_operativo=OrdenTrabajo.ASIGNADA)
            .select_related("tipo_trabajo_version")
            .order_by("numero"))


def sin_empezar(orden) -> bool:
    """`True` si no hay una sola respuesta ni evidencia escrita.

    LAS TRES CONDICIONES, NO SOLO EL ESTADO. El estado dice lo que el flujo
    cree; `datos` y las evidencias dicen lo que realmente se escribio, que es
    lo unico que la inmutabilidad existe para proteger.
    """
    if orden.estado_operativo != type(orden).ASIGNADA:
        return False
    if orden.datos:
        return False
    return not orden.evidencias.exists()


class Command(BaseCommand):
    help = ("Mueve a la plantilla vigente las ordenes que nadie empezo. "
            "Simula por defecto.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="Nombre o id de la empresa.")
        parser.add_argument("--tipo", default="",
                            help="Codigo del tipo de trabajo. Vacio: todos.")
        parser.add_argument("--aplicar", action="store_true",
                            help="Sin esto solo simula y no escribe nada.")

    def handle(self, *args, **o):
        from django.db import transaction
        from django.utils import timezone

        from campo import plantillas as P
        from campo.models import OrdenTrabajo, WorkType
        from common.models import Org

        org = (Org.objects.filter(name__iexact=o["org"]).first()
               or Org.objects.filter(id=o["org"]).first())
        if org is None:
            raise CommandError(f"No existe la empresa '{o['org']}'.")

        tipos = WorkType.objects.filter(org=org, activo=True)
        if o["tipo"]:
            tipos = tipos.filter(codigo=o["tipo"])

        total = 0
        for tipo in tipos.order_by("codigo"):
            vigente = P.ultima_publicada(tipo)
            if vigente is None:
                continue

            #  SE AGRUPA POR VERSION DE ORIGEN: el diff que hay que leer es
            #  uno por version, no uno por orden. 145 ordenes en v3 son 145
            #  veces el mismo cambio.
            por_version = {}
            for orden in candidatas(org, tipo):
                if orden.tipo_trabajo_version_id == vigente.id:
                    continue
                if not sin_empezar(orden):
                    continue
                por_version.setdefault(orden.tipo_trabajo_version,
                                       []).append(orden)
            if not por_version:
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n{tipo.codigo} ({tipo.nombre}) -> v{vigente.version}"))
            for origen, ordenes in sorted(por_version.items(),
                                          key=lambda kv: kv[0].version):
                numeros = ", ".join(f"#{x.numero}" for x in ordenes[:10])
                if len(ordenes) > 10:
                    numeros += f" y {len(ordenes) - 10} mas"
                self.stdout.write(
                    f"  desde v{origen.version}: {len(ordenes)} orden(es)  "
                    f"[{numeros}]")
                cambios = diferencias(origen.esquema, vigente.esquema)
                if not cambios:
                    self.stdout.write("      (el formulario no cambia)")
                for linea in cambios:
                    self.stdout.write(f"      {linea}")

                if o["aplicar"]:
                    #  SE RELEE BAJO BLOQUEO Y SE VUELVE A PREGUNTAR. Entre
                    #  el listado y esta linea un tecnico pudo abrir la orden
                    #  y escribir: la condicion que autoriza el cambio tiene
                    #  que valer EN EL MOMENTO de escribirlo, no cuando se
                    #  armo la lista.
                    movidas = 0
                    for orden in ordenes:
                        with transaction.atomic():
                            fila = (OrdenTrabajo.objects
                                    .select_for_update().get(pk=orden.pk))
                            if (fila.tipo_trabajo_version_id == vigente.id
                                    or not sin_empezar(fila)):
                                continue
                            #  `update()` y no `save()`: no toca `revision`
                            #  ni dispara los hooks del modelo. `updated_at`
                            #  va explicito porque `update()` saltea
                            #  `auto_now`, y la app lo necesita para saber
                            #  que esta orden cambio.
                            (OrdenTrabajo.objects.filter(pk=fila.pk)
                             .update(tipo_trabajo_version=vigente,
                                     updated_at=timezone.now()))
                            movidas += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"      movidas: {movidas}"))
                    total += movidas
                else:
                    total += len(ordenes)

        if not total:
            self.stdout.write("\nNada que mover.")
        elif not o["aplicar"]:
            self.stdout.write(self.style.WARNING(
                f"\nSIMULACRO: {total} orden(es) se moverian. "
                "Lee el diff de arriba y volve a correrlo con --aplicar."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nListo: {total} orden(es). Las que alguien ya empezo "
                "conservan su version."))
