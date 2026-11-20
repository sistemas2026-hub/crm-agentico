# -*- coding: utf-8 -*-
"""
================================================================================
 CARGAR EL RANGO QUE LA EMPRESA CONSIDERA BUENO  --  07/11/2026
================================================================================
El rango vive en la plantilla (CLAUDE.md §3.3: lo que varia por empresa es
configuracion), y hoy no hay pantalla donde escribirlo. Sin una forma de
cargarlo, el diagnostico que el usuario pidio no se enciende nunca: codigo
construido que no corre.

Esto NO es la solucion definitiva -- lo es un campo en el editor de
plantillas-- y se escribe sabiendolo. Es lo que destraba hoy, en un comando
que simula por defecto y se lee entero antes de aplicar.

    python manage.py fijar_rango_bueno --org rapilink --min -27 --max -8
    python manage.py fijar_rango_bueno --org rapilink --min -27 --max -8 --aplicar

PUBLICA UNA VERSION NUEVA, no toca la publicada: una plantilla congelada que
cambia debajo de una orden es justo lo que la inmutabilidad impide. Las
ordenes vivas siguen con la suya; las nuevas toman esta.
================================================================================
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fija el rango de potencia que se considera bueno, por tipo de trabajo."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="Nombre o id de la empresa.")
        parser.add_argument("--min", type=float, required=True,
                            help="El extremo mas negativo, en dBm (ej: -27).")
        parser.add_argument("--max", type=float, required=True,
                            help="El extremo menos negativo, en dBm (ej: -8).")
        parser.add_argument("--campo", default="potencia_al_salir",
                            help="El campo al que se le fija el rango.")
        parser.add_argument("--tipo", default="",
                            help="Codigo del tipo de trabajo. Vacio: todos los "
                                 "que tengan ese campo.")
        parser.add_argument("--aplicar", action="store_true",
                            help="Sin esto solo simula y no escribe nada.")

    def handle(self, *args, **o):
        from campo import plantillas as P
        from campo.models import WorkType, WorkTypeVersion
        from common.models import Org

        org = (Org.objects.filter(name__iexact=o["org"]).first()
               or Org.objects.filter(id=o["org"]).first())
        if org is None:
            raise CommandError(f"No existe la empresa '{o['org']}'.")

        piso, techo = min(o["min"], o["max"]), max(o["min"], o["max"])
        tipos = WorkType.objects.filter(org=org, activo=True)
        if o["tipo"]:
            tipos = tipos.filter(codigo=o["tipo"])

        tocados, saltados = 0, []
        for tipo in tipos:
            vigente = P.ultima_publicada(tipo)
            if vigente is None:
                saltados.append(f"{tipo.codigo}: sin version publicada")
                continue
            definicion, motivos = P.leer_definicion(vigente.esquema)
            if motivos:
                #  NO SE PUBLICA LO QUE NO SE PUDO LEER ENTERO: republicar
                #  desde una lectura parcial borraria lo que el editor no
                #  entiende. Misma razon que en `probar_instruccion_de_foto`.
                saltados.append(f"{tipo.codigo}: {motivos[0]}")
                continue
            campo = next((c for c in definicion.get("campos") or []
                          if c.get("id") == o["campo"]), None)
            if campo is None:
                saltados.append(f"{tipo.codigo}: no pide '{o['campo']}'")
                continue
            if (campo.get("bueno_min") == piso
                    and campo.get("bueno_max") == techo):
                saltados.append(f"{tipo.codigo}: ya tiene ese rango")
                continue

            antes = (campo.get("bueno_min"), campo.get("bueno_max"))
            campo["bueno_min"], campo["bueno_max"] = piso, techo
            self.stdout.write(
                f"  {tipo.codigo} ({tipo.nombre}): v{vigente.version} "
                f"{antes} -> ({piso}, {techo})")
            if o["aplicar"]:
                nueva, cambio = P.publicar(tipo, definicion)
                self.stdout.write(self.style.SUCCESS(
                    f"    publicada v{nueva.version}"
                    + ("" if cambio else " (sin cambios: mismo esquema)")))
            tocados += 1

        for s in saltados:
            self.stdout.write(self.style.WARNING(f"  (saltado) {s}"))

        if not tocados:
            self.stdout.write("Nada que cambiar.")
        elif not o["aplicar"]:
            self.stdout.write(self.style.WARNING(
                f"\nSIMULACRO: {tocados} plantilla(s) cambiarian. "
                "Volvé a correrlo con --aplicar."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nListo: {tocados} plantilla(s). Las ordenes YA creadas "
                "conservan su version; las nuevas toman esta."))
