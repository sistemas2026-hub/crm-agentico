# -*- coding: utf-8 -*-
"""
Backfill de la identidad externa sobre los casos que ya existen.

QUE HACE
--------
Copia a 'case' la referencia al ticket del ISP que hasta ahora solo se podia
alcanzar dando la vuelta por la conversacion que lo abrio:

    asistente.conversations.ticket_operativo  ->  case.external_ticket_id
    asistente.conversations.id_cliente        ->  case.external_service_id

Nada mas. No toca 'status', ni fechas, ni nada que se vea en una pantalla.

POR QUE SOLO ESTOS
------------------
Medido contra produccion el 08/09/2026, antes de escribir una linea:

    conversaciones con ticket_operativo ....... 16
    tickets WispHub distintos ................. 16
    Cases distintos afectados ................. 16
    un ticket -> varios Case .................. 0
    un Case -> varios tickets ................. 0
    el mismo ticket en dos orgs ............... 0
    valores vacios o no numericos ............. 0

Relacion 1:1 perfecta, asi que el UNIQUE parcial de la migracion anterior no
rompe nada. Ese dry run es la razon por la que este archivo puede escribir sin
preguntar.

LO QUE DELIBERADAMENTE NO SE BACKFILLEA
---------------------------------------
1. Los 13 numeros de ticket que solo viven DENTRO de la descripcion del caso,
   en prosa ("Ticket operativo #91288"). Se pueden parsear -- se probo, los 28
   parsean y no colisionan -- y aun asi no se hace: la columna
   'ticket_operativo' existe justamente para no volver a parsear un parrafo, y
   estrenarla parseando un parrafo seria sembrar de nuevo el problema que vino
   a resolver. Son casos ya cerrados. Quedan como legado, sin referencia
   externa, y eso es un estado valido.

2. Los 2 tickets de 'solicitudes_solicitudservicio.ticket_wisphub'. Son
   tickets que Dexter creo, pero una solicitud no abre un Case, asi que no hay
   ningun Case al que pertenezcan. Inventar uno aca seria fabricar historia.

   ATENCION PARA LA FASE 2 -- esto no es una nota al pie: mientras 'case' no
   sea la referencia canonica, "este ticket lo creo Dexter" se responde
   mirando DOS tablas, no una:

       asistente.conversations.ticket_operativo
       solicitudes_solicitudservicio.ticket_wisphub

   La primera version de la auditoria miro solo la primera y clasifico esos 2
   tickets como externos. El importador que consulte una sola tabla va a
   cometer el mismo error, en silencio y sobre datos nuevos.

'wisphub' va escrito aca a mano y eso esta bien: no es un valor por defecto
para el futuro, es una afirmacion sobre filas que ya existen. Todas ellas se
crearon contra WispHub porque es el unico sistema operativo que este
despliegue tuvo nunca. Un tenant nuevo llega sin filas que backfillear.
"""

from django.db import migrations

PROVEEDOR_HISTORICO = "wisphub"

LEER_CONVERSACIONES = """
    select c.caso_id,
           trim(c.ticket_operativo),
           coalesce(trim(c.id_cliente), ''),
           c.organization_id
      from asistente.conversations c
     where coalesce(trim(c.ticket_operativo), '') <> ''
       and c.caso_id is not null
"""

EXISTE_LA_TABLA = """
    select 1
      from information_schema.tables
     where table_schema = 'asistente' and table_name = 'conversations'
"""


def _conversaciones_con_ticket(conexion) -> list | None:
    """
    Las filas a copiar, o None si aca no hay de donde copiarlas.

    Que el esquema del motor no este NO es un error: las pruebas corren sobre
    SQLite, y un CRM instalado sin el motor al lado tampoco lo tiene. En los
    dos casos no hay nada que backfillear y la migracion tiene que pasar.

    El motor se descarta ANTES de pedir un cursor, no despues: sobre un backend
    que no es Postgres no se abre ninguna conexion ni se ejecuta ninguna
    consulta que este archivo sepa que va a fallar.
    """
    if conexion.vendor != "postgresql":
        return None
    with conexion.cursor() as cursor:
        cursor.execute(EXISTE_LA_TABLA)
        if cursor.fetchone() is None:
            return None
        cursor.execute(LEER_CONVERSACIONES)
        return cursor.fetchall()


def adelante(apps, schema_editor):
    Case = apps.get_model("cases", "Case")

    filas = _conversaciones_con_ticket(schema_editor.connection)
    if filas is None:
        print("  [backfill] sin esquema 'asistente': nada que copiar.")
        return

    copiados = ya_tenian = sin_caso = otra_org = 0
    for caso_id, ticket, id_servicio, org_conversacion in filas:
        caso = Case.objects.filter(pk=caso_id).first()
        if caso is None:
            # La conversacion apunta a un caso que ya no esta. Se cuenta y se
            # sigue: un caso borrado no es motivo para abortar la migracion.
            sin_caso += 1
            continue
        if caso.external_ticket_id:
            ya_tenian += 1
            continue
        if org_conversacion and str(caso.org_id) != str(org_conversacion):
            # Nunca deberia pasar -- se verifico que hay una sola org -- pero
            # escribir la referencia de un ISP sobre el caso de otro es
            # exactamente el fallo que el UNIQUE por org existe para impedir.
            otra_org += 1
            continue

        caso.provider = PROVEEDOR_HISTORICO
        caso.external_ticket_id = ticket
        caso.external_service_id = id_servicio
        # Sabemos que lo creo Dexter porque esta en NUESTRO registro, no
        # porque el proveedor lo diga: 'external_created_by' queda vacio a
        # proposito hasta que alguien lea 'creado_por' del proveedor.
        caso.external_created_by_type = "dexter"
        caso.save(update_fields=["provider", "external_ticket_id",
                                 "external_service_id",
                                 "external_created_by_type"])
        copiados += 1

    print(f"  [backfill] conversaciones con ticket: {len(filas)} | "
          f"copiados: {copiados} | ya tenian: {ya_tenian} | "
          f"sin caso: {sin_caso} | de otra org: {otra_org}")


def atras(apps, schema_editor):
    """
    Deshace SOLO lo que esta migracion escribio.

    El filtro por 'external_fetched_at is null' es lo que distingue una fila
    backfilleada de una que un importador ya leyo del proveedor: revertir esta
    migracion no puede borrar identidad que llego despues por otro camino.
    """
    Case = apps.get_model("cases", "Case")
    n = Case.objects.filter(
        provider=PROVEEDOR_HISTORICO,
        external_created_by_type="dexter",
        external_fetched_at__isnull=True,
    ).update(provider="", external_ticket_id="", external_service_id="",
             external_created_by_type="")
    print(f"  [backfill] revertidos: {n}")


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0029_identidad_ticket_externo"),
    ]

    operations = [
        migrations.RunPython(adelante, atras),
    ]
