# -*- coding: utf-8 -*-
"""Habilita la opción «Otro» con texto libre en un campo de selección.

    python manage.py permitir_otro --org <id> --tipo correctivo_fibra --campo que_encontro
    python manage.py permitir_otro --org <id> --tipo correctivo_fibra --campo que_encontro --aplicar

POR QUÉ EXISTE
--------------
Pedido del usuario: «que las opciones predeterminadas tengan un Otro con texto
libre». La app y el backend YA lo soportan --`campo_del_formulario.dart` lee
`permite_otro`, dibuja la opción, guarda en `{id}_otro` y valida «Elegiste
«Otro»: contá qué fue»--. Lo que faltaba era marcarlo en la plantilla.

PUBLICA UNA VERSIÓN NUEVA, NO EDITA LA VIGENTE, y eso no es ceremonia: una
orden CONGELA su versión al nacer, y editar la publicada le cambiaría el
formulario a órdenes que ya tienen respuestas escritas --incluso cerradas--.
`correctivo_fibra` tiene 16 versiones justamente porque esa regla se respeta.

DESPUÉS DE ESTO FALTA UN PASO, y el comando lo dice al final: las órdenes
abiertas siguen colgando de la versión con que nacieron. `repuntar_plantilla`
mueve a la vigente las que NADIE EMPEZÓ -- las que ya tienen respuestas no se
tocan, y eso también es a propósito.

QUÉ NO HACE
-----------
No toca campos de sí/no. Un «Otro» en «¿probaste el servicio con el cliente?»
le da salida a quien no quiere contestar, que es lo contrario de lo que se
busca. El comando exige nombrar el campo: no hay modo «marcá todos».
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Habilita «Otro» en un campo de selección, publicando una versión."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--tipo", required=True, help="código de la plantilla")
        parser.add_argument("--campo", required=True, help="id del campo de selección")
        parser.add_argument("--aplicar", action="store_true",
                            help="publicar (sin esto, solo dice qué haría)")

    def handle(self, *args, **opciones):
        from campo import plantillas
        from campo.models import WorkType, WorkTypeVersion
        from common.models import Org

        org = Org.objects.filter(pk=opciones["org"]).first()
        if org is None:
            raise CommandError("esa organización no existe")
        tipo = WorkType.objects.filter(org=org, codigo=opciones["tipo"]).first()
        if tipo is None:
            raise CommandError(f"la plantilla '{opciones['tipo']}' no existe")

        vigente = (WorkTypeVersion.objects
                   .filter(work_type=tipo, estado=WorkTypeVersion.PUBLICADA)
                   .order_by("-version").first())
        if vigente is None:
            raise CommandError("esa plantilla no tiene ninguna versión publicada")

        esquema = dict(vigente.esquema or {})
        campos = [dict(c) for c in (esquema.get("campos") or [])]
        objetivo = next((c for c in campos if c.get("id") == opciones["campo"]), None)
        if objetivo is None:
            ids = [c.get("id") for c in campos]
            raise CommandError(
                f"el campo '{opciones['campo']}' no está en la plantilla. "
                f"Los que hay: {ids}")

        self.stdout.write(f"  {tipo.codigo}: vigente es la v{vigente.version}")
        #  LAS OPCIONES VIVEN EN DOS LUGARES, y el codigo real lo sabe:
        #  `reglas.options` o `opciones` (`plantillas.py:687`). Mirar una
        #  sola dio «0 opciones» en un campo que SI las tiene, medido el
        #  11/11/2026 con `que_encontro` de `correctivo_fibra`.
        reglas = objetivo.get("reglas") or {}
        #  NO SE LLAMA `opciones`: ese nombre ya es el de los argumentos del
        #  comando (`opciones["aplicar"]`), y pisarlo rompio la primera
        #  corrida real con un TypeError. Dos cosas distintas con el mismo
        #  nombre en la misma funcion es una que se come a la otra.
        opciones_del_campo = list(
            reglas.get("options") or objetivo.get("opciones") or [])
        self.stdout.write(f"  campo '{objetivo.get('id')}' — tipo "
                          f"'{objetivo.get('tipo')}', "
                          f"{len(opciones_del_campo)} opciones")

        #  NO SE MARCA UN CAMPO QUE NO ES DE SELECCION. Un `permite_otro` en un
        #  campo de texto o numerico no significa nada y el validador lo
        #  rechazaria despues, cuando ya se publico una version de mas.
        if not opciones_del_campo:
            raise CommandError(
                "ese campo no tiene opciones: «Otro» solo tiene sentido donde "
                "hay una lista de la que elegir")

        if objetivo.get("permite_otro"):
            self.stdout.write("  YA lo tiene: no hay nada que publicar.")
            return

        objetivo["permite_otro"] = True

        #  LAS OPCIONES SE NORMALIZAN ANTES DE PUBLICAR, y sin esto el comando
        #  rompe justo al aplicar (11/11/2026, lo encontro la prueba y no la
        #  corrida -- por una vez).
        #
        #  `componer` las lee de `opciones` (`plantillas.py:507`), pero una
        #  plantilla puede tenerlas en `reglas.options`. Republicar un esquema
        #  de esa forma las PIERDE, y `componer` corta con «necesita al menos
        #  dos opciones». El simulacro pasaba igual: la diferencia aparece
        #  recien al publicar.
        for c in campos:
            r = c.get("reglas") or {}
            if r.get("options") and not c.get("opciones"):
                c["opciones"] = list(r["options"])

        esquema["campos"] = campos

        if not opciones["aplicar"]:
            self.stdout.write("")
            self.stdout.write("  SIMULACRO: se publicaría la "
                              f"v{vigente.version + 1} con «Otro» habilitado "
                              f"en '{opciones['campo']}'.")
            self.stdout.write("  Nada más cambia. Agregá --aplicar.")
            return

        #  `publicar` recompone y REVALIDA el esquema entero --«dos guardas que
        #  no confian una en la otra»-- y no crea version si nada cambio.
        version, cambio = plantillas.publicar(tipo, esquema)
        if not cambio:
            self.stdout.write("  el esquema quedó igual: no se publicó nada.")
            return
        self.stdout.write("")
        self.stdout.write(f"  PUBLICADA la v{version.version}.")
        self.stdout.write("")
        self.stdout.write("  FALTA UN PASO: las órdenes ya abiertas siguen con "
                          "la versión con que nacieron.")
        self.stdout.write(f"    python manage.py repuntar_plantilla --org "
                          f"{org.id} --tipo {tipo.codigo}")
        self.stdout.write("  Eso mueve solo las que nadie empezó. Las que ya "
                          "tienen respuestas no se tocan.")
