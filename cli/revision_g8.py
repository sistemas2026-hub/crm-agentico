# -*- coding: utf-8 -*-
"""
================================================================================
 REVISIÓN G8  --  las conversaciones de legado que quedarían esperando a alguien
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \\
      py -3.13 cli/revision_g8.py
    ... py -3.13 cli/revision_g8.py --incluir-pruebas   (tambien los 30 hilos)

SOLO LECTURA. No escribe, no adopta, no cierra, no ejecuta nada.

QUE ES G8, Y QUE NO ES
----------------------
El backfill de §11.2 dejaria en 'control = humano' toda conversacion abierta
con las dos banderas de legado puestas. Medido en produccion (A7): 16 de
WhatsApp real quedarian asi **sin 'atendida_manual'** -- o sea, clientes que
segun el modelo esperan a una persona y que nadie atendio.

G8 NO es una clasificacion automatica. El contrato es explicito: "una persona
las revisa UNA POR UNA y decide para cada una: seguir en humano, cerrar (con
desenlace), resolver el estado externo o volver a la IA. No se ocultan ni se
resuelven automaticamente."

Asi que esta herramienta NO decide. Junta lo que hace falta para que alguien
decida, y lo deja reproducible. La sugerencia que calcula es eso: una
sugerencia, para ordenar el trabajo -- nunca una decision aplicada.

QUE NO SACA, Y POR QUE
----------------------
NO saca el contenido de los mensajes. Quien revisa necesita saber de que va
cada hilo, y para eso esta la bandeja, donde el acceso queda auditado y la
conversacion se lee entera y en contexto. Volcar 16 conversaciones de clientes
a un archivo de trabajo es exactamente lo que este proyecto no hace con los
datos de nadie.

Tampoco saca 'autor_nombre'. Sale el conteo, las fechas y los estados: lo que
permite ordenar y priorizar sin leer a nadie.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

#: Los canales que NO son clientes reales. Los 30 hilos de prueba de A6 siguen
#: el mismo modelo pero no entran a la cola operativa, y su politica es otra
#: decision (§11.2). Se separan, no se mezclan.
CANALES_DE_PRUEBA = ["whatsapp-simulado", "api", "web"]

#: La regla del backfill de §11.2, tal cual: es la misma que hoy decide la
#: pausa al reconstruir (api.py). Si esta consulta y esa regla se separan, G8
#: estaria revisando un conjunto distinto del que el corte va a producir.
CANDIDATAS = """
    estado = 'abierta'
    and escalada_a_humano
    and necesita_atencion_humana
    and coalesce(relevo_version, 0) = 0
"""


def conectar():
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"[g8] faltan variables de conexion: {faltan}")
        raise SystemExit(2)
    return psycopg.connect(
        host=os.environ["DBHOST"], port=os.environ["DBPORT"],
        dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
        password=os.environ["DBPASSWORD"],
        autocommit=True, row_factory=dict_row)


def sugerir(c: dict) -> tuple[str, str]:
    """
    (clase, por que). SUGERENCIA, no decision.

        A  segura para adoptar tal cual: el modelo y el legado dicen lo mismo
        B  hace falta que alguien mire: hay algo que el dato no resuelve
        C  no adoptar sin resolver antes otra cosa

    El criterio no mira el contenido de la conversacion. Mira si adoptarla
    afirmaria algo que no se puede demostrar -- que es el unico motivo por el
    que una adopcion automatica hace daño.
    """
    # Sin caso ni ticket, pero escalada: el efecto externo se perdio en su
    # momento (§11.2 lo lista y NO lo reintenta solo). Adoptarla dejaria una
    # conversacion "en manos de una persona" sin nada del otro lado.
    if not c["caso_id"] and not c["tiene_ticket"]:
        return "C", ("escalada sin caso ni ticket: el efecto externo se perdio "
                     "y adoptarla no lo recupera")

    # Un nombre en 'tomada_por' que no se puede resolver a un usuario: el
    # backfill copiaria el nombre con 'asignada_a_usuario_id = NULL'. Eso es lo
    # que §11.2 permite, pero deja una asignacion que no identifica a nadie.
    if c["tomada_por"]:
        return "B", (f"la tiene '{c['tomada_por']}' como nombre, sin id de "
                     f"usuario: hay que confirmar quien es antes de adoptarla")

    # Nadie la tomo nunca y lleva mucho esperando. No es un defecto del dato:
    # es la situacion que G8 existe para mirar.
    if c["dias_esperando"] is not None and c["dias_esperando"] >= 7:
        return "B", (f"nadie la tomo y el cliente espera hace "
                     f"{c['dias_esperando']} dias: decidir si se cierra o se "
                     f"retoma")

    if c["mensajes_del_cliente_sin_respuesta"]:
        return "B", (f"{c['mensajes_del_cliente_sin_respuesta']} mensaje(s) del "
                     f"cliente despues de la ultima respuesta")

    return "A", "escalada con caso, sin dueño ambiguo y sin cliente esperando"


def revisar(cn, incluir_pruebas: bool) -> list[dict]:
    # '<> all(...)' y no 'not in (...)': psycopg manda la lista como UN
    # parametro, y 'not in' espera una lista de parametros separados.
    filtro_canal = "" if incluir_pruebas else " and c.canal <> all(%(pruebas)s)"
    filas = cn.execute(f"""
        select c.id, c.canal, c.estado, c.control, c.control_motivo,
               c.tomada_por, c.tomada_en, c.caso_id, c.atendida_manual,
               c.creado_en, c.actualizado_en, c.relevo_version,
               (select count(*) from asistente.messages m
                 where m.conversation_id = c.id) as mensajes,
               (select count(*) from asistente.messages m
                 where m.conversation_id = c.id and m.origen is null) as sin_origen,
               (select max(m.creado_en) from asistente.messages m
                 where m.conversation_id = c.id and m.rol = 'user') as ultimo_del_cliente,
               (select max(m.creado_en) from asistente.messages m
                 where m.conversation_id = c.id and m.rol <> 'user') as ultima_respuesta,
               (select count(*) from asistente.messages m
                 where m.conversation_id = c.id and m.rol = 'user'
                   and m.creado_en > coalesce(
                       (select max(m2.creado_en) from asistente.messages m2
                         where m2.conversation_id = c.id and m2.rol <> 'user'),
                       '-infinity'::timestamptz)) as mensajes_del_cliente_sin_respuesta,
               (c.ticket_operativo is not null) as tiene_ticket,
               extract(day from (now() - coalesce(
                   (select max(m.creado_en) from asistente.messages m
                     where m.conversation_id = c.id and m.rol = 'user'),
                   c.actualizado_en)))::int as dias_esperando
        from asistente.conversations c
        where {CANDIDATAS} {filtro_canal}
        order by dias_esperando desc nulls last, c.creado_en
        """, {"pruebas": CANALES_DE_PRUEBA}).fetchall()

    for c in filas:
        c["clase"], c["por_que"] = sugerir(c)
    return [dict(c) for c in filas]


def informe(filas: list[dict], incluir_pruebas: bool) -> None:
    print(f"\n{'=' * 78}\n  REVISION G8  ({os.environ['DBNAME']})\n{'=' * 78}")
    if not filas:
        print("\n  No hay conversaciones candidatas en esta base.")
        print("  Contra produccion, A7 midio 16 de WhatsApp real.")
        return

    reales = [c for c in filas if c["canal"] not in CANALES_DE_PRUEBA]
    pruebas = [c for c in filas if c["canal"] in CANALES_DE_PRUEBA]
    print(f"\n  candidatas: {len(filas)}   reales: {len(reales)}"
          f"   de prueba: {len(pruebas)}")

    sin_atendida = [c for c in reales if not c["atendida_manual"]]
    print(f"  de las reales, SIN atendida_manual: {len(sin_atendida)}"
          f"   <- estas son las de G8")

    por_clase = {}
    for c in sin_atendida:
        por_clase.setdefault(c["clase"], []).append(c)
    print("\n  sugerencia (NO es la decision):")
    for clase, texto in (("A", "podria adoptarse tal cual"),
                         ("B", "hace falta que alguien mire"),
                         ("C", "no adoptar sin resolver antes otra cosa")):
        print(f"     {clase}  {len(por_clase.get(clase, [])):>3}   {texto}")

    print(f"\n{'-' * 78}")
    for i, c in enumerate(sin_atendida, 1):
        print(f"\n  [{i:>2}/{len(sin_atendida)}]  {c['clase']}  conversacion {c['id']}")
        print(f"        canal {c['canal']}   creada {c['creado_en']:%Y-%m-%d}"
              f"   espera {c['dias_esperando']} dias")
        print(f"        control={c['control']}/{c['control_motivo'] or '-'}"
              f"   tomada_por={c['tomada_por'] or '(nadie)'}"
              f"   caso={c['caso_id'] or '(ninguno)'}"
              f"   ticket={'si' if c['tiene_ticket'] else 'no'}")
        print(f"        mensajes={c['mensajes']} (sin origen: {c['sin_origen']})"
              f"   del cliente sin responder: "
              f"{c['mensajes_del_cliente_sin_respuesta']}")
        print(f"        -> {c['por_que']}")

    print(f"\n{'-' * 78}")
    print("  Las cuatro decisiones posibles, por conversacion (§11.2):")
    print("     seguir en humano  ·  cerrar con desenlace  ·  resolver el")
    print("     estado externo (caso/ticket)  ·  volver a la IA")
    print("  Cada una queda como evento del relevo con datos.g8 = <decision>.")
    print("\n  ESTA HERRAMIENTA NO DECIDE NINGUNA. Solo junta el dato.")


def main():
    p = argparse.ArgumentParser(description="Revision G8 (solo lectura)")
    p.add_argument("--incluir-pruebas", action="store_true",
                   help="tambien los hilos de canales de prueba (A6)")
    p.add_argument("--json", metavar="ARCHIVO",
                   help="ademas, escribe el detalle para adjuntar a la revision")
    args = p.parse_args()

    cn = conectar()
    try:
        filas = revisar(cn, args.incluir_pruebas)
        informe(filas, args.incluir_pruebas)
        if args.json:
            Path(args.json).write_text(
                json.dumps(filas, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
            print(f"\n  detalle en {args.json}")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
