# -*- coding: utf-8 -*-
"""
Los numeros de un turno, por dia y por canal -- separados a proposito.

    py -3.13 cli/medir_turnos.py rapilink
    py -3.13 cli/medir_turnos.py rapilink --dias 14

POR QUE EXISTE
--------------
El 07/09/2026 se desactivo el razonamiento del modelo ('thinking'), que en
banco de pruebas daba 4.26s contra 1.77s por llamada, y que en los 51 casos
dorados no costo calidad (50/51, y el unico fallo era un timeout externo que
ya fallaba antes).

Un banco de pruebas y 51 casos NO son produccion. Lo que decide si el cambio
sirve son varios dias de trafico real, mirando cuatro cosas a la vez:

    cuanto tarda el MODELO       (no el turno entero: ver abajo)
    cuanto cuesta el turno
    con que frecuencia se escala
    con que frecuencia falla una herramienta

Los ultimos dos pueden SUBIR mientras los primeros bajan, y eso significa que
se compro velocidad a costa de resolver. Un solo numero promedio lo taparia.

POR QUE SE SEPARA EL TIEMPO DEL MODELO DEL TOTAL
------------------------------------------------
Un mal dia de la API del ISP convierte un buen dia del modelo en un p95 feo.
Sin separarlos, un cambio en el modelo parece no haber servido cuando lo que
empeoro fue un tercero. 'modelo' es el total menos lo que el turno paso
esperando a un sistema externo: es una resta y no una medida directa, pero es
la unica forma de ver el efecto de un cambio del modelo por separado.

NO INVENTA DATOS
----------------
'latencia_ms', 'llamadas_modelo' y los tokens por mensaje existen desde la
noche del 07/09/2026. Antes de eso las columnas estan vacias, y salen con
guion -- un 0 se leeria como "salio gratis", que es un dato falso.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv                                   # noqa: E402
load_dotenv(RAIZ / ".env", override=False)

from nucleo.persistencia.db import sesion                        # noqa: E402

# La zona de la EMPRESA, no UTC. La base guarda UTC y esta bien que lo haga,
# pero un informe operativo que corta el dia a la medianoche de Londres agrupa
# la tarde de un ISP colombiano con la mañana del dia siguiente. Y dentro de un
# mes nadie recuerda con que frontera se agrupo: por eso va en el titulo.
ZONA = "America/Bogota"

# Y se convierte con UN SOLO 'at time zone', nunca con dos. 'creado_en' ya
# es timestamptz: escribir "at time zone 'UTC' at time zone 'America/Bogota'"
# primero le quita la zona y despues lee ese valor sin zona COMO SI fuera
# hora de Bogota -- o sea SUMA cinco horas en vez de restarlas. Se escribio
# asi al agregar esta agrupacion, y el informe puso en el 08/09 turnos de
# las 6 de la tarde del 07/09. No da error: solo mueve un dia entero de
# trabajo al dia siguiente, que es justo lo que este agrupamiento existe
# para evitar.

# Con pocos turnos el p95 es, literalmente, el turno mas lento. Se muestra
# igual --esconderlo seria peor-- pero marcado, para que nadie saque una
# conclusion de una muestra que no la sostiene.
MINIMO_PARA_P95 = 20


def _velocidad(cur, org, dias):
    """Un renglon por dia y canal: cuanto tardo, en que, cuanto costo y con
    que configuracion."""
    cur.execute(
        """with turnos as (
             select m.id, m.conversation_id cid, m.creado_en, cv.canal,
                    m.latencia_ms, m.llamadas_modelo, m.costo_usd,
                    m.tokens_entrada,
                    lag(m.creado_en) over (partition by m.conversation_id
                                           order by m.creado_en) previo
               from asistente.messages m
               join asistente.conversations cv on cv.id = m.conversation_id
              where m.organization_id = %s and m.rol = 'assistant'
                and m.latencia_ms is not null
                and m.creado_en > now() - make_interval(days => %s))
           select (t.creado_en at time zone %s)::date d,
                  t.canal, count(*) n,
                  percentile_cont(0.5) within group (order by t.latencia_ms) p50,
                  percentile_cont(0.95) within group (order by t.latencia_ms) p95,
                  avg(t.llamadas_modelo) llamadas,
                  sum(t.costo_usd) costo,
                  avg(t.tokens_entrada) entrada,
                  avg(coalesce(h.ms, 0)) tools_ms,
                  array_agg(distinct c.config_version) versiones
             from turnos t
             -- Las herramientas se atribuyen al turno por VENTANA DE TIEMPO,
             -- entre esta respuesta y la anterior de la misma conversacion:
             -- tool_calls cuelga de la conversacion, no del mensaje.
             left join lateral (
                  select sum(tc.duracion_ms) ms from asistente.tool_calls tc
                   where tc.conversation_id = t.cid
                     and tc.creado_en > coalesce(
                           t.previo, t.creado_en - interval '5 minutes')
                     and tc.creado_en <= t.creado_en + interval '30 seconds'
             ) h on true
             -- La config tambien por ventana: la vigente en un turno es la
             -- ultima anotada antes de el. NULL = anterior al historial.
             --
             -- PENDIENTE, y sabido: 't.creado_en' es cuando el turno TERMINO
             -- (el mensaje del cliente guarda el inicio, el del asistente no
             -- -- ver creado_en=llego_en en nucleo/canales/api.py). Un turno
             -- que empieza a las 20:37:59 con v119, con un guardado de config
             -- a las 20:38:10, y termina 20:38:25, sale etiquetado v120 y no
             -- corrio con v120.
             --
             -- No hace falta guardar nada nuevo para arreglarlo: esta misma
             -- fila tiene 'latencia_ms', asi que el inicio del turno es
             -- 'creado_en - latencia_ms'. Es cambiar el 'hc.creado_en <=' de
             -- abajo por esa resta -- sin migracion y sin tocar el camino
             -- caliente.
             --
             -- Se deja asi a proposito mientras se acumula trafico para
             -- comparar razonamiento ON contra OFF: solo se equivoca en un
             -- turno que este corriendo JUSTO cuando alguien guarda config, y
             -- cambiar el instrumento en mitad de la medicion cuesta mas que
             -- ese caso. Si durante la ventana no se guarda ninguna config,
             -- el error no puede ocurrir.
             left join lateral (
                  select hc.config_version
                    from asistente.tenant_config_historial hc
                   where hc.organization_id = %s
                     and hc.creado_en <= t.creado_en
                   order by hc.creado_en desc limit 1
             ) c on true
            group by 1, 2 order by 1 desc, 3 desc""",
        (org, dias, ZONA, org))
    return cur.fetchall()


def _calidad(cur, org, dias):
    """Por dia: cuanto se escalo y cuantas herramientas fallaron."""
    cur.execute(
        """select (cv.creado_en at time zone %s)::date d,
                  count(*) conv,
                  count(*) filter (where cv.escalada_a_humano) escaladas
             from asistente.conversations cv
            where cv.organization_id = %s
              and cv.creado_en > now() - make_interval(days => %s)
            group by 1""", (ZONA, org, dias))
    conv = {f["d"]: f for f in cur.fetchall()}

    cur.execute(
        """select (t.creado_en at time zone %s)::date d,
                  count(*) n,
                  -- 'es_bloqueo' NO cuenta como error: es el codigo frenando
                  -- una accion, o sea la proteccion funcionando.
                  count(*) filter (where not t.exito and not t.es_bloqueo) fallidas
             from asistente.tool_calls t
            where t.organization_id = %s
              and t.creado_en > now() - make_interval(days => %s)
            group by 1""", (ZONA, org, dias))
    return conv, {f["d"]: f for f in cur.fetchall()}


def _historial(cur, org, dias):
    """Que configuracion empezo a servir, y cuando.

    Incluye la ultima ANTERIOR a la ventana: es la que estaba vigente cuando
    la ventana empezo, y sin ella los primeros dias no tendrian con que
    explicarse.
    """
    cur.execute(
        """(select config_version v, creado_en at time zone %s b,
                   config->'llm'->>'razonamiento' razona, true dentro
              from asistente.tenant_config_historial
             where organization_id = %s
               and creado_en > now() - make_interval(days => %s))
           union all
           (select config_version, creado_en at time zone %s,
                   config->'llm'->>'razonamiento', false
              from asistente.tenant_config_historial
             where organization_id = %s
               and creado_en <= now() - make_interval(days => %s)
             order by creado_en desc limit 1)
           order by 1""", (ZONA, org, dias, ZONA, org, dias))
    return cur.fetchall()


def _proporcion(parte, total, ancho):
    """'1/5 ( 20.0%)'. El denominador va SIEMPRE, no solo cuando es chico.

    Con 5 conversaciones, '20.0%' se lee como una tendencia y es UNA
    conversacion. El porcentaje solo, sin cuantos casos lo sostienen, invita
    a una conclusion que la muestra no aguanta -- y cuando la muestra si
    aguanta, ver el denominador no le molesta a nadie.
    """
    if not total:
        return "-".rjust(ancho)
    return f"{parte}/{total} ({100.0 * parte / total:5.1f}%)".rjust(ancho)


def _versiones(fila) -> str:
    """'v120', o '? v120' si parte de esos turnos son anteriores al historial.

    El '?' no se rellena con la version conocida mas vieja: un turno anterior
    al historial NO corrio con esa config -- corrio con una que se
    sobreescribio. Adivinarla daria una comparacion limpia y falsa, que es
    justo lo que este informe existe para no producir.
    """
    crudas = fila["versiones"] or []
    vs = sorted({v for v in crudas if v is not None})
    marca = "? " if any(v is None for v in crudas) else ""
    return (marca + ",".join(f"v{v}" for v in vs)).strip() or "?"


def informe(tenant: str, dias: int = 7) -> None:
    with sesion(tenant) as (cur, org):
        filas = _velocidad(cur, org, dias)
        if not filas:
            print("Todavia no hay turnos medidos. Las columnas se llenan desde\n"
                  "la noche del 07/09/2026 -- hace falta trafico posterior.")
            return

        cab = ("dia", "canal", "n", "total", "p95", "modelo", "tools", "llam",
               "entrada", "costo", "config")
        print(f"  {cab[0]:7s} {cab[1]:18s} {cab[2]:>4s} {cab[3]:>7s} "
              f"{cab[4]:>8s} {cab[5]:>8s} {cab[6]:>7s} {cab[7]:>5s} "
              f"{cab[8]:>8s} {cab[9]:>9s}  {cab[10]:<9s}")
        for f in filas:
            guion5, guion8 = "-".rjust(5), "-".rjust(8)
            llam = f"{f['llamadas']:5.1f}" if f["llamadas"] is not None else guion5
            ent = f"{f['entrada']:8,.0f}" if f["entrada"] is not None else guion8
            tools = float(f["tools_ms"] or 0) / 1000
            modelo = max(0.0, f["p50"] / 1000 - tools)
            p95 = (f"{f['p95']/1000:7.1f}s" if f["n"] >= MINIMO_PARA_P95
                   else f"{f['p95']/1000:6.1f}s*")
            print(f"  {f['d']:%d/%m}   {f['canal']:18s} {f['n']:4d} "
                  f"{f['p50']/1000:6.1f}s {p95} {modelo:7.1f}s {tools:6.1f}s "
                  f"{llam} {ent} ${float(f['costo'] or 0):8.4f}  "
                  f"{_versiones(f):<9s}")
        if any(f["n"] < MINIMO_PARA_P95 for f in filas):
            print(f"\n  (*) menos de {MINIMO_PARA_P95} turnos: ese p95 es casi "
                  f"'el turno mas lento', no una tendencia.")

        conv, herram = _calidad(cur, org, dias)
        c2, c3 = "escalado", "herramientas con error"
        print(f"\n  {cab[0]:7s} {c2:>16s} {c3:>26s}")
        for d in sorted(set(conv) | set(herram), reverse=True):
            c, h = conv.get(d), herram.get(d)
            esc = _proporcion(c["escaladas"], c["conv"], 16) if c else "-".rjust(16)
            err = _proporcion(h["fallidas"], h["n"], 26) if h else "-".rjust(26)
            print(f"  {d:%d/%m}   {esc} {err}")

        historia = _historial(cur, org, dias)
        if historia:
            print("\n  Que configuracion estuvo sirviendo:")
            for x in historia:
                razona = ("razonamiento OFF" if x["razona"] == "disabled"
                          else "razonamiento por defecto (ON)")
                ya = "" if x["dentro"] else "   (ya vigente al empezar la ventana)"
                print(f"    {x['b']:%d/%m %H:%M}  v{x['v']:<4d} {razona}{ya}")
            print("    El motor comprueba la version cada 15s: un turno de los "
                  "15 segundos\n    siguientes a un cambio pudo correr todavia "
                  "con la anterior.")

        if any("?" in _versiones(f) for f in filas):
            print("\n  Los turnos marcados '?' son anteriores al historial de "
                  "config, que se\n  empezo a guardar el 08/09/2026. Lo de antes "
                  "se sobreescribio: no se\n  puede saber con que configuracion "
                  "corrieron, y no se adivina.")

        print("\n  Si el escalado o los errores SUBEN mientras 'modelo' y el\n"
              "  costo bajan, la rapidez se esta pagando con calidad.")


if __name__ == "__main__":
    tenant = sys.argv[1] if len(sys.argv) > 1 else "rapilink"
    dias = 7
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])
    print(f"\nTurnos medidos de '{tenant}', ultimos {dias} dia(s). "
          f"Dias en {ZONA}.\n")
    informe(tenant, dias)
