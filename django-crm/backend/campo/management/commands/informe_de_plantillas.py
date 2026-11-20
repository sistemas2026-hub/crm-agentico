# -*- coding: utf-8 -*-
"""
================================================================================
 INFORME DE PLANTILLAS  --  solo lectura  --  12/11/2026
================================================================================

    python manage.py informe_de_plantillas
    python manage.py informe_de_plantillas --org <id>

POR QUE EXISTE
--------------
Dos preguntas que hoy no se podian contestar sin entrar a la base, y de las que
dependen dos trabajos distintos:

  1. «¿La empresa adopto `instalacion_fibra`?» Si no la adopto, la instalacion
     no tiene formulario y el Supervisor no puede elegir plantilla. Es un clic
     en /supervisor-noc/plantillas, pero antes hay que saber si falta.

  2. «¿Cual es el ID del campo?» `campo_escaneable`, `permitir_otro` y
     `fijar_rango_bueno` lo piden, y el id NO es el titulo: se genera a partir
     de el. Adivinarlo cuesta una corrida fallida cada vez.

Y UNA TERCERA QUE MUERDE SOLA: cuantas plantillas tiene cada labor. Si una
labor tiene DOS y ninguna declara el asunto del caso, `plantilla_del_caso`
devuelve `VARIAS_SIN_ASUNTO` y NINGUNA plantilla -- el Supervisor deja de crear
ordenes de esa labor. Adoptar una segunda plantilla sin cargarle asuntos es
exactamente como se llega ahi, asi que la cuenta se imprime al lado.

NO ESCRIBE NADA, y no imprime ni un dato de cliente: nombres de plantilla, de
labor, de campo y de asunto, mas conteos. Los asuntos son del catalogo del ISP,
no de una persona.

LA SALIDA SE PEGA EN UNA CONVERSACION, y por eso es corta a proposito: una
linea por plantilla y una por campo. La terminal web del servidor trunca los
comandos largos --ya paso dos veces-- asi que este se corre con una linea
corta y lo que es largo es la respuesta, no el pedido.
================================================================================
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Lista las plantillas de cada empresa, con sus campos y sus "
            "asuntos. Solo lectura.")

    def add_arguments(self, parser):
        parser.add_argument("--org", default="", help="id (UUID) de una empresa")

    def handle(self, *args, **opciones):
        from campo.models import WorkType, WorkTypeVersion
        from common.models import Org

        orgs = Org.objects.all().order_by("name")
        if opciones["org"]:
            orgs = orgs.filter(pk=opciones["org"])

        for org in orgs:
            tipos = list(WorkType.objects.filter(org=org).order_by("labor", "codigo"))
            if not tipos:
                continue
            self.stdout.write(f"\n== {org.name or '(sin nombre)'}  [{org.id}]")

            #  CUANTAS POR LABOR, ANTES DE LA LISTA: es el dato que decide si
            #  el Supervisor puede elegir plantilla, y si va al final nadie lo
            #  lee.
            por_labor: dict[str, int] = {}
            for t in tipos:
                if t.activo:
                    por_labor[t.labor or "(sin labor)"] = \
                        por_labor.get(t.labor or "(sin labor)", 0) + 1
            for labor, cuantas in sorted(por_labor.items()):
                aviso = ""
                if cuantas > 1:
                    aviso = ("  <- con mas de una, CADA UNA necesita declarar "
                             "sus asuntos o no se elige ninguna")
                self.stdout.write(f"   labor {labor:<14} {cuantas} activa(s){aviso}")

            for t in tipos:
                v = (WorkTypeVersion.objects
                     .filter(work_type=t, estado=WorkTypeVersion.PUBLICADA)
                     .order_by("-version").first())
                estado = "activa" if t.activo else "INACTIVA"
                version = f"v{v.version}" if v else "SIN VERSION PUBLICADA"
                self.stdout.write(
                    f"\n   {t.codigo}  «{t.nombre}»  labor={t.labor or '-'}  "
                    f"{estado}  {version}")

                #  `WorkType.asuntos` ES UNA LISTA, NO UNA RELACION
                #  (`models.py:66`, JSONField), y es lo que lee el codigo real
                #  al elegir plantilla: `plantilla_para_asunto` itera
                #  `v.work_type.asuntos`.
                #
                #  LA PRIMERA VERSION DE ESTE COMANDO HIZO `t.asuntos.all()`,
                #  envuelto en un `except Exception` que imprimia «(sin la
                #  tabla de asuntos)». O sea: preguntaba al objeto equivocado y
                #  el except convertia el error en un mensaje CREIBLE, que
                #  encima culpaba a la base. Se vio en la primera corrida
                #  contra produccion, el 12/11/2026 -- las ocho pruebas de este
                #  comando pasaban porque ninguna afirmaba sobre esta linea.
                #
                #  Es el anti-patron que CLAUDE.md marca: un except amplio que
                #  no deja fallar nada y por eso no deja ver nada. Ahora no hay
                #  except: si `asuntos` dejara de existir, esto revienta y se
                #  arregla, en vez de informar una mentira tranquilizadora.
                #
                #  Los asuntos de la LABOR son otra cosa (`labores.py:111`,
                #  related_name en `Labor`) y los lista `informe_de_labores`.
                asuntos = [str(a) for a in (t.asuntos or []) if str(a).strip()]
                self.stdout.write(
                    f"      asuntos: {', '.join(asuntos) if asuntos else 'NINGUNO'}")

                if v is None:
                    continue
                campos = (v.esquema or {}).get("campos") or []
                if not campos:
                    self.stdout.write("      campos: ninguno")
                for c in campos:
                    marcas = []
                    if c.get("escaneable"):
                        marcas.append("camara")
                    if c.get("permite_otro"):
                        marcas.append("Otro")
                    if c.get("bueno"):
                        marcas.append("rango bueno")
                    if (c.get("reglas") or {}).get("required"):
                        marcas.append("obligatorio")
                    self.stdout.write(
                        f"      campo {str(c.get('id')):<28} "
                        f"{str(c.get('tipo')):<10} "
                        f"«{c.get('titulo')}»"
                        f"{'  [' + ', '.join(marcas) + ']' if marcas else ''}")

        self.stdout.write("")
        self.stdout.write("  El 'campo <id>' de arriba es lo que piden "
                          "campo_escaneable, permitir_otro y fijar_rango_bueno.")
