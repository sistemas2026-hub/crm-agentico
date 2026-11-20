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
import copy

from django.core.management.base import BaseCommand, CommandError

#: El nombre exacto que la app y el servidor reconocen. No es una etiqueta
#: cualquiera: `CampoDelFormulario.otro` y `validador.OTRO` comparan contra
#: esta palabra, asi que «otro» o «OTRO» no sirven.
OTRO = "Otro"


def _con_otro(lista) -> list:
    """La lista con «Otro» al final y una sola vez. Lo que hace `componer`."""
    return [o for o in lista if o != OTRO] + [OTRO]


def _marcar(campo: dict) -> None:
    """Habilita «Otro» en un campo de seleccion, sobre el campo recibido.

    LAS TRES COSAS JUNTAS, y la tercera es la que faltaba  --  11/11/2026.
    Las dos primeras se publicaron a produccion y «Otro» NO APARECIA:

      1. la bandera `permite_otro`, que es lo que la app mira para dibujar el
         campo de texto que acompaña a la opcion;
      2. las opciones en `opciones`, porque `componer` las lee de ahi;
      3. **la opcion «Otro» DENTRO de la lista**, que es de donde el tecnico
         elige. Sin esto la app no la dibuja --lee `reglas.options` con
         prioridad (`campo_del_formulario.dart:244`)-- y el servidor la
         rechazaria con «Opcion invalida» (`validador._validar_reglas`).

    Quien agrega «Otro» a la lista en el camino normal es `componer`
    (`plantillas.py:519`). Este comando NO recompone a proposito --la v16 de
    `correctivo_fibra` tiene campos que el editor no sabe crear-- asi que la
    parte de `componer` que si corresponde la hace aca, y nada mas.

    SE USA EN LOS DOS LADOS: el esquema que se publica y el control con el que
    se compara. Antes eran dos bucles escritos aparte, y el segundo se escribio
    copiando el primero con su defecto adentro: la guarda bendijo el error en
    vez de atraparlo. Una sola funcion no puede divergir de si misma.
    """
    campo["permite_otro"] = True

    reglas = campo.get("reglas") or {}
    if reglas.get("options"):
        reglas["options"] = _con_otro(reglas["options"])
        campo["reglas"] = reglas
    #  `componer` lee de `opciones`; la app lee de `reglas.options`. Las dos
    #  quedan con lo mismo para que no importe quien lea despues.
    if campo.get("opciones"):
        campo["opciones"] = _con_otro(campo["opciones"])
    elif reglas.get("options"):
        campo["opciones"] = list(reglas["options"])


class Command(BaseCommand):
    help = "Habilita «Otro» en un campo de selección, publicando una versión."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="id (UUID) de la organización")
        parser.add_argument("--tipo", required=True, help="código de la plantilla")
        parser.add_argument("--campo", required=True, help="id del campo de selección")
        parser.add_argument("--aplicar", action="store_true",
                            help="publicar (sin esto, solo dice qué haría)")

    def handle(self, *args, **opciones):
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

        #  COPIA PROFUNDA, y no es precaucion de mas: `dict(c)` es
        #  superficial, asi que `c["reglas"]` seguia siendo EL MISMO dict que
        #  el de la version vigente. Agregarle «Otro» ahi mutaba el esquema
        #  publicado en memoria, y el control --que se arma despues-- se
        #  habria comparado contra lo ya mutado: siempre igual, siempre verde.
        esquema = copy.deepcopy(vigente.esquema or {})
        campos = esquema.get("campos") or []
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

        #  «YA LO TIENE» SE MIDE POR LA LISTA, NO POR LA BANDERA, y esto es
        #  lo que permite reparar lo que quedo a medio hacer.
        #
        #  El 11/11/2026 este comando publico cuatro versiones con
        #  `permite_otro: true` y SIN «Otro» en la lista. Con la pregunta
        #  anterior --solo la bandera-- esas cuatro plantillas quedaban
        #  inarreglables por este camino: el comando contestaba «ya lo tiene»
        #  y se iba, mientras el tecnico seguia sin ver la opcion.
        #
        #  Completo es: la bandera puesta Y la opcion en la lista de la que se
        #  elige. Cualquier otra combinacion es un trabajo a medias que hay
        #  que terminar.
        lista_actual = ((objetivo.get("reglas") or {}).get("options")
                        or objetivo.get("opciones") or [])
        if objetivo.get("permite_otro") and OTRO in lista_actual:
            self.stdout.write("  YA lo tiene: no hay nada que publicar.")
            return
        if objetivo.get("permite_otro"):
            self.stdout.write(
                "  A MEDIO HACER: la bandera está y la opción «Otro» NO está "
                "en la lista.")
            self.stdout.write(
                "  El técnico no la ve. Esto lo repara publicando una versión "
                "con la opción adentro.")

        #  SOLO EL CAMPO NOMBRADO, y esto se corrigio despues de verlo en
        #  produccion (11/11/2026): el bucle recorria TODOS y le agrego la
        #  clave a `servicio_probado_con_el_cliente`, que nadie pidio tocar.
        #  Era inocuo --el lector mira las dos claves-- pero el comando promete
        #  que nada mas cambia, y cambiaba.
        _marcar(objetivo)
        esquema["campos"] = campos

        if not opciones["aplicar"]:
            self.stdout.write("")
            self.stdout.write("  SIMULACRO: se publicaría la "
                              f"v{vigente.version + 1} con «Otro» habilitado "
                              f"en '{opciones['campo']}'.")
            #  LA LISTA, IMPRESA  --  lo que el técnico va a ver. El simulacro
            #  decía «Otro habilitado» y la opción no llegaba a la lista: una
            #  salida que describe la intención y no el resultado no sirve para
            #  revisar nada.
            lista = ((objetivo.get("reglas") or {}).get("options")
                     or objetivo.get("opciones") or [])
            self.stdout.write(f"  La lista queda: {lista}")
            self.stdout.write("  Nada más cambia. Agregá --aplicar.")
            return

        #  SE COPIA EL ESQUEMA VIGENTE, NO SE RECOMPONE  --  11/11/2026.
        #
        #  El primer intento llamaba a `plantillas.publicar`, que pasa la
        #  definicion por `componer`. Contra produccion eso corto con
        #  «'decimal' no esta disponible»: la v16 de `correctivo_fibra` tiene
        #  campos que el EDITOR no sabe crear, porque esa plantilla no se hizo
        #  con el editor. `componer` es el validador de lo que entra POR AHI,
        #  y un esquema que lleva meses en produccion no entra por ahi.
        #
        #  Recomponerlo tenia dos finales y los dos malos: o rechaza la
        #  plantilla entera --lo que paso-- o la «arregla» cambiandole tipos a
        #  campos que hoy funcionan. Un comando que habilita una opcion no
        #  puede reescribir el formulario de paso.
        #
        #  LA GUARDA QUE REEMPLAZA A `componer` ES MAS ESTRECHA Y MAS FUERTE
        #  para este caso: se compara el esquema nuevo contra el vigente y se
        #  exige que la UNICA diferencia sea la bandera. `componer` valida que
        #  el esquema sea construible; esto valida que no se toco nada mas,
        #  que es exactamente lo que este comando promete.
        import json

        control = copy.deepcopy(vigente.esquema or {})
        for c in (control.get("campos") or []):
            if c.get("id") == opciones["campo"]:
                _marcar(c)
        if json.dumps(esquema, sort_keys=True) != json.dumps(control,
                                                             sort_keys=True):
            raise CommandError(
                "el esquema nuevo difiere del vigente en algo mas que la "
                "bandera: no se publica nada")

        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=vigente.version + 1,
            schema_version=vigente.schema_version,
            estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
        self.stdout.write("")
        self.stdout.write(f"  PUBLICADA la v{version.version}.")
        self.stdout.write("")
        self.stdout.write("  FALTA UN PASO: las órdenes ya abiertas siguen con "
                          "la versión con que nacieron.")
        self.stdout.write(f"    python manage.py repuntar_plantilla --org "
                          f"{org.id} --tipo {tipo.codigo}")
        self.stdout.write("  Eso mueve solo las que nadie empezó. Las que ya "
                          "tienen respuestas no se tocan.")
