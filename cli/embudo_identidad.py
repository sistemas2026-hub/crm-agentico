# -*- coding: utf-8 -*-
"""
================================================================================
 EMBUDO DE IDENTIDAD  --  bloqueo -> verificacion -> confirmacion, por tenant
================================================================================
    py -3.13 cli/embudo_identidad.py rapilink                 # ultimos 45 dias
    py -3.13 cli/embudo_identidad.py rapilink --dias 7
    py -3.13 cli/embudo_identidad.py rapilink --simulados     # incluye canales de prueba
    py -3.13 cli/embudo_identidad.py rapilink --guardar-linea-base linea_base.json
    py -3.13 cli/embudo_identidad.py rapilink --comparar linea_base.json   # sale 1 si empeora

Por que existe (Fase 1 de "completar el ciclo de identidad", 23/09/2026)
-------------------------------------------------------------------------
El motor frena en codigo toda herramienta que necesita saber quien es el
cliente y le pide al modelo que consiga el dato. Lo que pasa DESPUES lo decide
el modelo: si llama a verificar, y si llama a confirmar. Antes de mover esas
dos decisiones al codigo (Fase 2) hay que poder medir cuantas conversaciones
se pierden entre el bloqueo y la confirmacion -- y volver a medirlo despues.

La primera medicion se hizo a mano el 23/09/2026: 79 bloqueos en 49
conversaciones, 45 verificaron, 33 confirmaron, 16 perdidas. Este comando la
vuelve repetible.

Dos fuentes, a proposito
------------------------
  asistente.tool_calls        historia completa: sirve desde hoy hacia atras.
                              No distingue "encontrado" de "no encontrado" en
                              la verificacion (exito=true en ambos).
  asistente.identidad_eventos desde que se aplique su migracion: cada paso con
                              su resultado y lo que el motor esperaba despues.
                              Si la tabla no existe todavia, se dice y se sigue.

SIN PII. Solo cuentas, roles, herramientas y codigos. Ningun id de conversacion
sale por pantalla: para eso esta "Ver proceso".
================================================================================
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.canales import canal as canales                              # noqa: E402
from nucleo.config import fuente                                         # noqa: E402
from nucleo.persistencia.db import sesion                                # noqa: E402

CODIGOS_BLOQUEO = ["IDENTIDAD_NO_VERIFICADA", "IDENTIDAD_NO_RESUELTA",
                   "DATO_DEL_EQUIPO_NO_CARGADO"]


def _herramientas_de_identidad(tenant: str) -> tuple[list[str], list[str]]:
    """(verifican, confirman) segun la config vigente en la base."""
    cargada = fuente.desde_base(tenant)
    if not cargada:
        sys.exit(f"'{tenant}' no tiene configuracion cargada en la base.")
    config, _version = cargada
    verifican = [h.nombre for h in config.herramientas if getattr(h, "verifica_identidad", False)]
    confirman = [h.nombre for h in config.herramientas if getattr(h, "confirma_identidad", False)]
    return verifican, confirman


def medir(tenant: str, dias: int, incluir_simulados: bool) -> dict:
    verifican, confirman = _herramientas_de_identidad(tenant)
    filtro_canal = "" if incluir_simulados else "and c.canal = any(%(canales)s)"
    params = {"dias": dias, "codigos": CODIGOS_BLOQUEO,
              "verif": verifican or ["__ninguna__"],
              "conf": confirman or ["__ninguna__"],
              "canales": sorted(canales.REALES)}

    with sesion(tenant) as (cur, org):
        params["org"] = org
        cur.execute(f"""
          with b as (
            select t.conversation_id, min(t.creado_en) t0
            from asistente.tool_calls t
            join asistente.conversations c on c.id = t.conversation_id
            where t.organization_id = %(org)s
              and t.codigo_error = any(%(codigos)s)
              and t.creado_en > now() - make_interval(days => %(dias)s)
              {filtro_canal}
            group by t.conversation_id),
          v as (select t.conversation_id, min(t.creado_en) t1
                from asistente.tool_calls t join b using (conversation_id)
                where t.herramienta = any(%(verif)s) and t.creado_en > b.t0
                group by t.conversation_id),
          k as (select t.conversation_id
                from asistente.tool_calls t join b using (conversation_id)
                where t.herramienta = any(%(conf)s) and t.creado_en > b.t0
                group by t.conversation_id),
          e as (select r.conversation_id
                from asistente.relevo_eventos r join b using (conversation_id)
                where r.tipo = 'escalada' and r.creado_en > b.t0
                  and r.datos ->> 'motivo' = 'duda_de_identidad'
                group by r.conversation_id)
          select count(*) bloqueadas,
                 count(v.t1) verificaron,
                 count(k.conversation_id) confirmaron,
                 count(e.conversation_id) escaladas_por_identidad,
                 percentile_cont(0.5) within group
                   (order by extract(epoch from (v.t1 - b.t0)) / 60) mediana_min,
                 count(*) filter (where v.t1 is null and c.estado = 'abierta')
                   abiertas_sin_verificar,
                 count(*) filter (where v.t1 is not null and k.conversation_id is null
                                    and c.estado = 'cerrada') cerradas_sin_confirmar
          from b left join v using (conversation_id) left join k using (conversation_id)
                 left join e using (conversation_id)
          join asistente.conversations c on c.id = b.conversation_id""", params)
        embudo = dict(cur.fetchone())

        cur.execute(f"""
          select t.rol_solicitante rol, t.herramienta, t.codigo_error, count(*) n,
                 count(distinct t.conversation_id) convs
          from asistente.tool_calls t
          join asistente.conversations c on c.id = t.conversation_id
          where t.organization_id = %(org)s and t.codigo_error = any(%(codigos)s)
            and t.creado_en > now() - make_interval(days => %(dias)s) {filtro_canal}
          group by 1, 2, 3 order by n desc""", params)
        por_rol = [dict(r) for r in cur.fetchall()]

        cur.execute(f"""
          select date_trunc('day', t.creado_en)::date dia, count(*) n
          from asistente.tool_calls t
          join asistente.conversations c on c.id = t.conversation_id
          where t.organization_id = %(org)s and t.codigo_error = any(%(codigos)s)
            and t.creado_en > now() - make_interval(days => %(dias)s) {filtro_canal}
          group by 1 order by 1""", params)
        por_dia = [(str(r["dia"]), r["n"]) for r in cur.fetchall()]

        # DE QUE CANAL VIENE CADA BLOQUEO. Medido el 23/09/2026: los 79 bloqueos
        # de 45 dias eran de 'api' (43 conversaciones) y 'whatsapp-simulado'
        # (6). CERO en WhatsApp real -- y se habian reportado como "trafico
        # real". Un embudo sin procedencia mide el trafico de prueba y lo
        # llama operacion. Se imprime siempre, con o sin --simulados.
        cur.execute("""
          select coalesce(c.canal, '(sin canal)') canal,
                 count(distinct t.conversation_id) convs, count(*) n
          from asistente.tool_calls t
          join asistente.conversations c on c.id = t.conversation_id
          where t.organization_id = %(org)s and t.codigo_error = any(%(codigos)s)
            and t.creado_en > now() - make_interval(days => %(dias)s)
          group by 1 order by convs desc""", params)
        por_canal = [dict(r) for r in cur.fetchall()]

        # EL CANAL REAL, SIN EXIGIR BLOQUEO. En WhatsApp de verdad el numero
        # cuenta como factor de posesion y el modelo verifica por su propio
        # prompt antes de tocar una herramienta, asi que la compuerta no se
        # dispara: el embudo de arriba da cero y no significa que no haya
        # identidad que medir. Esto es lo que si pasa ahi.
        cur.execute("""
          with c as (select id from asistente.conversations
                     where organization_id = %(org)s and canal = any(%(canales)s)
                       and creado_en > now() - make_interval(days => %(dias)s)),
          v as (select distinct conversation_id from asistente.tool_calls
                where herramienta = any(%(verif)s)),
          k as (select distinct conversation_id from asistente.tool_calls
                where herramienta = any(%(conf)s)),
          t as (select distinct conversation_id from asistente.tool_calls)
          select count(*) conversaciones,
                 count(k.conversation_id) confirmaron,
                 count(*) filter (where v.conversation_id is not null
                                    and k.conversation_id is null) verificaron_sin_confirmar,
                 count(*) filter (where v.conversation_id is null
                                    and t.conversation_id is not null) herramientas_sin_verificar,
                 count(*) filter (where t.conversation_id is null) sin_herramientas
          from c left join v on v.conversation_id = c.id
                 left join k on k.conversation_id = c.id
                 left join t on t.conversation_id = c.id""", params)
        canal_real = dict(cur.fetchone())

        # La fuente nueva: existe solo desde que se aplique su migracion.
        eventos = None
        cur.execute("""select 1 from information_schema.tables
                       where table_schema = 'asistente' and table_name = 'identidad_eventos'""")
        if cur.fetchone():
            cur.execute("""
              select etapa, coalesce(motivo, '') motivo, coalesce(siguiente_paso, '') paso,
                     rol, count(*) n, count(distinct conversation_id) convs
              from asistente.identidad_eventos
              where organization_id = %(org)s
                and creado_en > now() - make_interval(days => %(dias)s)
              group by 1, 2, 3, 4 order by etapa, n desc""", params)
            eventos = [dict(r) for r in cur.fetchall()]

    bloq = embudo["bloqueadas"] or 0
    perdidas = bloq - (embudo["confirmaron"] or 0)
    embudo["perdidas"] = perdidas
    embudo["pct_perdidas"] = round(100.0 * perdidas / bloq, 1) if bloq else 0.0
    if embudo.get("mediana_min") is not None:
        embudo["mediana_min"] = round(float(embudo["mediana_min"]), 1)
    return {"tenant": tenant, "dias": dias, "simulados": incluir_simulados,
            "herramientas": {"verifican": verifican, "confirman": confirman},
            "embudo": embudo, "por_rol": por_rol, "por_dia": por_dia,
            "por_canal": por_canal, "canal_real": canal_real, "eventos": eventos}


def imprimir(m: dict) -> None:
    e = m["embudo"]
    print("=" * 72)
    print(f"  EMBUDO DE IDENTIDAD -- {m['tenant']}, ultimos {m['dias']} dias"
          + ("  (con canales simulados)" if m["simulados"] else "  (solo canales reales)"))
    print("=" * 72)
    print(f"  conversaciones bloqueadas por identidad : {e['bloqueadas']}")
    mediana = (f"   (mediana {e['mediana_min']} min)"
               if e.get("mediana_min") is not None else "")
    print(f"  verificaron despues del bloqueo         : {e['verificaron']}{mediana}")
    print(f"  confirmaron identidad                   : {e['confirmaron']}")
    print(f"  escaladas por duda de identidad         : {e['escaladas_por_identidad']}")
    print(f"  PERDIDAS (bloqueadas - confirmadas)     : {e['perdidas']}  ({e['pct_perdidas']}%)")
    print(f"     abiertas sin verificar               : {e['abiertas_sin_verificar']}")
    print(f"     cerradas sin confirmar               : {e['cerradas_sin_confirmar']}")

    print("\n  DE QUE CANAL VIENEN LOS BLOQUEOS (siempre, todos los canales):")
    if not m["por_canal"]:
        print("    ninguno en el periodo")
    for r in m["por_canal"]:
        real = "REAL" if r["canal"] in canales.REALES else "prueba"
        print(f"    {r['canal']:<20} {real:<7} convs={r['convs']:<4} bloqueos={r['n']}")

    cr = m["canal_real"]
    print("\n  CANAL REAL, SIN EXIGIR BLOQUEO (la identidad por el camino del prompt):")
    print(f"    conversaciones                 : {cr['conversaciones']}")
    print(f"    confirmaron identidad          : {cr['confirmaron']}")
    print(f"    verificaron sin confirmar      : {cr['verificaron_sin_confirmar']}")
    print(f"    usaron herramientas sin verif. : {cr['herramientas_sin_verificar']}")
    print(f"    sin ninguna herramienta        : {cr['sin_herramientas']}")

    if m["por_rol"]:
        print("\n  bloqueos por rol y herramienta:")
        for r in m["por_rol"]:
            print(f"    {r['rol'] or '-':<26} {r['herramienta']:<34} {r['codigo_error']:<28}"
                  f" n={r['n']:<4} convs={r['convs']}")
    if m["por_dia"]:
        print("\n  bloqueos por dia:")
        for dia, n in m["por_dia"]:
            print(f"    {dia}  {n}")

    print("\n  asistente.identidad_eventos (la fuente con resultado de cada paso):")
    if m["eventos"] is None:
        print("    la tabla no existe en esta base: la migracion "
              "202609231445_identidad_eventos.sql no esta aplicada todavia.")
    elif not m["eventos"]:
        print("    sin eventos en el periodo (la tabla existe; el motor desplegado "
              "todavia no los escribe, o no hubo bloqueos).")
    else:
        for r in m["eventos"]:
            print(f"    {r['etapa']:<22} {r['motivo']:<30} {r['paso']:<14} "
                  f"{r['rol'] or '-':<26} n={r['n']:<4} convs={r['convs']}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Embudo de identidad por tenant")
    ap.add_argument("tenant")
    ap.add_argument("--dias", type=int, default=45)
    ap.add_argument("--simulados", action="store_true",
                    help="incluye conversaciones de canales que no son reales")
    ap.add_argument("--guardar-linea-base", metavar="RUTA")
    ap.add_argument("--comparar", metavar="RUTA",
                    help="sale 1 si el porcentaje de perdidas subio mas de 5 puntos")
    args = ap.parse_args()

    m = medir(args.tenant, args.dias, args.simulados)
    imprimir(m)

    resumen = {k: m["embudo"][k] for k in
               ("bloqueadas", "verificaron", "confirmaron", "perdidas", "pct_perdidas")}
    if args.guardar_linea_base:
        Path(args.guardar_linea_base).write_text(
            json.dumps({"tenant": m["tenant"], "dias": m["dias"], **resumen},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"linea base guardada en {args.guardar_linea_base}")
    if args.comparar:
        base = json.loads(Path(args.comparar).read_text(encoding="utf-8"))
        delta = resumen["pct_perdidas"] - float(base.get("pct_perdidas", 0))
        print(f"perdidas: {base.get('pct_perdidas')}% (linea base) -> {resumen['pct_perdidas']}%"
              f"  delta {delta:+.1f} puntos")
        if delta > 5:
            print("[FALLA] el embudo de identidad empeoro respecto a la linea base")
            sys.exit(1)
        print("[OK] el embudo no empeoro")


if __name__ == "__main__":
    main()
