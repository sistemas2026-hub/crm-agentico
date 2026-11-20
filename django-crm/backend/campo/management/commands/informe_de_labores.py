# -*- coding: utf-8 -*-
"""
================================================================================
 INFORME DE LABORES  --  solo lectura  --  20/10/2026
================================================================================

    python manage.py informe_de_labores            # todas las empresas
    python manage.py informe_de_labores --org <id>

Para la Fase 1 de SPEC/objetivos/labores-propias-por-empresa.md (criterio
1.7). Se corre en produccion ANTES del deploy y despues:

  ANTES   dice lo que la migracion 0036 va a encontrar: asuntos que chocan
          entre plantillas de una misma empresa (la siembra se queda con el
          primero y saltea el resto), plantillas SIN labor que tienen asuntos
          (no aportan a ninguna labor, D7) y los nombres que la empresa ya les
          puso a las labores (la siembra los copia).
  DESPUES ademas lista las labores sembradas, con cuantos asuntos tiene cada
          una.

NO ESCRIBE NADA. Funciona con o sin las tablas nuevas: antes del deploy no
existen. No imprime nada de clientes: nombres de plantillas y labores y los
asuntos que las PLANTILLAS declaran (los escribio una persona de la empresa,
no vienen de un ticket).
================================================================================
"""

from django.core.management.base import BaseCommand
from django.db import connection

from campo.cuadrillas import ConfiguracionDeReparto
from campo.models import WorkType
from campo.plantillas import normalizar_asunto
from common.models import Org


class Command(BaseCommand):
    help = "Solo lectura: lo que la siembra de labores encuentra (y sembro)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="", help="id de una sola empresa")

    def handle(self, *args, **opciones):
        orgs = Org.objects.all().order_by("name")
        if opciones["org"]:
            orgs = orgs.filter(id=opciones["org"])
        hay_tablas = "campo_labor" in connection.introspection.table_names()
        self.stdout.write(f"tablas de labores: {'SI' if hay_tablas else 'NO (antes del deploy)'}")

        total_choques = total_sin_labor = 0
        for org in orgs:
            self.stdout.write(f"\n== {org.name or '(sin nombre)'}  [{org.id}]")

            nombres = (ConfiguracionDeReparto.objects.filter(org=org)
                       .values_list("nombres_de_labor", flat=True).first()) or {}
            self.stdout.write(f"   nombres puestos el 20/10: {nombres or 'ninguno'}")

            primero = {}
            choques, sin_labor = [], []
            for tipo in WorkType.objects.filter(org=org).order_by("codigo"):
                asuntos = [a for a in (tipo.asuntos or []) if str(a).strip()]
                if not asuntos:
                    continue
                if not tipo.labor:
                    sin_labor.append(f"{tipo.nombre} ({len(asuntos)} asuntos)")
                    continue
                for a in asuntos:
                    clave = normalizar_asunto(a)
                    if clave in primero and primero[clave] != tipo.nombre:
                        choques.append(f"«{a}»: {primero[clave]} y {tipo.nombre}")
                    primero.setdefault(clave, tipo.nombre)
            total_choques += len(choques)
            total_sin_labor += len(sin_labor)
            self.stdout.write(f"   asuntos que chocan entre plantillas: {len(choques)}")
            for c in choques:
                self.stdout.write(f"      {c}")
            self.stdout.write(f"   plantillas SIN labor con asuntos: {len(sin_labor)}")
            for s in sin_labor:
                self.stdout.write(f"      {s}")

            if hay_tablas:
                from campo.labores import Labor
                labores = (Labor.objects.filter(org=org)
                           .order_by("-de_fabrica", "codigo"))
                if not labores.exists():
                    self.stdout.write("   labores sembradas: NINGUNA "
                                      "(se usan las de fabrica sin escribir)")
                for l in labores:
                    estado = "activa" if l.activa else "DADA DE BAJA"
                    self.stdout.write(
                        f"   labor {l.codigo:<12} «{l.nombre}» {estado}"
                        f"{' · de fabrica' if l.de_fabrica else ''} · "
                        f"{l.asuntos.count()} asuntos")

        self.stdout.write(f"\nTOTAL choques: {total_choques} · "
                          f"plantillas sin labor con asuntos: {total_sin_labor}")
