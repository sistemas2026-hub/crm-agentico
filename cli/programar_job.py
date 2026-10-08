# -*- coding: utf-8 -*-
"""
================================================================================
 ENCENDER Y APAGAR UN TRABAJO DEL RELOJ  --  la pieza que faltaba
================================================================================

    py -3.13 cli/programar_job.py --ver
    py -3.13 cli/programar_job.py supervisor_ciclo --cada 60m \\
        --actor "quien decide" --motivo "por que"
    py -3.13 cli/programar_job.py supervisor_ciclo --apagar \\
        --actor "quien decide" --motivo "por que"

POR QUE EXISTE
--------------
El scheduler estaba completo y no tenia forma de arrancar. Lo que hace correr
un trabajo es una fila en 'asistente.job_catalogo', y esa fila no la siembra
NINGUNA migracion --'tests/test_p2_inerte.py' lo afirma como uno de sus cinco
puntos-- ni la escribia ningun comando. Medido el 08/10/2026: el reloj llevaba
encendido desde el 22/09 girando sin un solo trabajo que hacer.

Eso no era un descuido: "cablear no es encender" es la separacion deliberada
del registro de jobs, y encender es operacion. Lo que faltaba era el gesto de
operacion, no el permiso para saltearse la separacion.

QUE NO HACE, Y ES LA MITAD DEL DISEÑO
-------------------------------------
No concede permisos. Encender 'supervisor_ciclo' significa "despertalo cada
tanto", nunca "puede hacer lo que quiera": del otro lado siguen las tres
puertas --la tarea delegada por una persona, el nivel de autonomia de la
empresa, y el diagnostico caso por caso-- y ninguna se abre por esta fila.

Tampoco construye el trabajo. Solo se pueden encender los que el despliegue YA
sabe hacer ('nucleo/programador/registro.py'); una clave que no este ahi se
rechaza, porque una fila sin handler es un turno que falla cada hora para
siempre.

ACTOR Y MOTIVO SON OBLIGATORIOS, igual que en 'cli/autonomia.py' y por lo
mismo: esto pone a un sistema a actuar sin que nadie mire, y sin saber quien lo
decidio y por que, la decision no se puede discutir despues.

APAGAR ES BARATO Y NO BORRA NADA: 'habilitado' pasa a false y la fila queda. El
reloj deja de reclamarlo en el tick siguiente. Borrarla haria imposible
contestar "¿esto estuvo encendido alguna vez?", que es la pregunta del dia que
algo haya corrido y nadie recuerde haberlo pedido.

EL ROL
------
Se usa 'scheduler_coordinator' con 'puerta.sesion', que es el unico que puede
tocar 'job_catalogo'. Ni el motor ni el reloj pueden leer esa tabla con su
usuario de conexion -- comprobado en produccion, 'permission denied'-- y eso es
la segregacion funcionando, no un obstaculo que esquivar.

CODIGOS DE SALIDA
  0  hecho, o nada que hacer
  1  no se pudo (base, permisos, el job no esta cableado)
  2  uso invalido (falta el job, falta --actor o --motivo, intervalo ilegible)
================================================================================
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.programador import puerta, registro             # noqa: E402

#  El intervalo se escribe como lo diria una persona --'60m', '15m', '6h',
#  '1d'-- y no en segundos: 'cada 3600' se lee mal y se tipea peor.
_UNIDADES = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}

#  PISO DE UN MINUTO, y no es arbitrario: el coordinador mira cada 60 s
#  ('coordinador.TICK_SEGUNDOS'), asi que un intervalo menor no se cumple --
#  prometeria una frecuencia que el reloj no puede dar.
_MINIMO_SEGUNDOS = 60


def _intervalo(texto: str) -> tuple[str, int]:
    """('60 minutes', 3600) a partir de '60m'. Levanta ValueError si no se lee."""
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", str(texto or "").lower())
    if not m:
        raise ValueError(
            f"no entiendo '{texto}'. Se escribe como '60m', '6h' o '1d'")
    cantidad, unidad = int(m.group(1)), m.group(2)
    if cantidad <= 0:
        raise ValueError("el intervalo tiene que ser mayor que cero")
    segundos = cantidad * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unidad]
    if segundos < _MINIMO_SEGUNDOS:
        raise ValueError(
            f"el minimo es 1 minuto: el reloj mira cada 60 s y un intervalo "
            f"menor prometeria una frecuencia que no puede cumplir")
    return f"{cantidad} {_UNIDADES[unidad]}", segundos


def _ver(cur) -> int:
    cur.execute("""
        select c.code, c.descripcion, c.intervalo::text as intervalo,
               c.habilitado,
               (select count(*) from asistente.job_schedule_state s
                 where s.job_code = c.code) as organizaciones
          from asistente.job_catalogo c
         order by c.code
    """)
    filas = cur.fetchall()
    print(f"\n  TRABAJOS EN EL CATALOGO: {len(filas)}")
    if not filas:
        print("    (ninguno: el reloj corre y no tiene nada que hacer)")
    for f in filas:
        print(f"    {f['code']:24s} cada {f['intervalo']:<14s} "
              f"{'ENCENDIDO' if f['habilitado'] else 'apagado':10s} "
              f"empresas={f['organizaciones']}")

    #  Y lo que el DESPLIEGUE sabe hacer, que es otra cosa: un trabajo cableado
    #  y sin fila no corre, y una fila sin handler falla cada tick.
    conocidos = sorted(registro.registrados())
    print(f"\n  LO QUE ESTE DESPLIEGUE SABE HACER: {len(conocidos)}")
    for c in conocidos:
        esta = any(f["code"] == c for f in filas)
        print(f"    {c:24s} {'(con fila)' if esta else '(sin fila: no corre)'}")
    print()
    return 0


def _encender(cur, code: str, intervalo_sql: str, actor: str,
              motivo: str) -> int:
    #  'anchor' truncado al segundo: la tabla lo exige
    #  ('jc_anchor_limpio'), y los slots se alinean contra el.
    cur.execute("""
        insert into asistente.job_catalogo (code, descripcion, anchor,
                                            intervalo, habilitado)
        values (%s, %s, date_trunc('second', now() at time zone 'utc'),
                %s::interval, true)
        on conflict (code) do update
           set intervalo   = excluded.intervalo,
               descripcion = excluded.descripcion,
               habilitado  = true
        returning (xmax = 0) as creado
    """, [code, f"{motivo} -- por {actor}", intervalo_sql])
    creado = cur.fetchone()["creado"]

    #  LA FILA DE ESTADO POR EMPRESA. Sin ella el coordinador no tiene a quien
    #  reclamarle el turno: el catalogo dice QUE y cada cuanto, el estado dice
    #  PARA QUIEN y cuando toca.
    cur.execute("""
        insert into asistente.job_schedule_state (job_code, organization_id,
                                                  next_run_at)
        select %s, o.id, date_trunc('second', now() at time zone 'utc')
          from public.organization o
         where o.is_active
        on conflict (job_code, organization_id) do nothing
    """, [code])
    nuevas = cur.rowcount

    print(f"\n  {'CREADO' if creado else 'ACTUALIZADO'}: {code}")
    print(f"    cada ............ {intervalo_sql}")
    print(f"    empresas nuevas . {nuevas}")
    print(f"    quien ........... {actor}")
    print(f"\n  El reloj lo va a reclamar en el proximo tick (hasta 60 s).")
    print(f"  Encender NO concede permisos: lo que el trabajo pueda hacer")
    print(f"  sigue dependiendo de lo que este delegado del otro lado.\n")
    return 0


def _apagar(cur, code: str, actor: str, motivo: str) -> int:
    cur.execute("""
        update asistente.job_catalogo
           set habilitado = false,
               descripcion = %s
         where code = %s
        returning code
    """, [f"APAGADO: {motivo} -- por {actor}", code])
    if cur.fetchone() is None:
        print(f"\n  '{code}' no esta en el catalogo: no hay nada que apagar.\n")
        return 0
    #  LA FILA QUEDA. Borrarla haria imposible contestar "¿esto estuvo
    #  encendido alguna vez?".
    print(f"\n  APAGADO: {code}")
    print(f"    quien ... {actor}")
    print(f"    La fila queda, con el motivo escrito. El reloj deja de")
    print(f"    reclamarlo desde el proximo tick.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Enciende o apaga un trabajo del reloj.",
        epilog="Encender no concede permisos: solo dice cada cuanto despertar.")
    p.add_argument("job", nargs="?", help="la clave del trabajo")
    p.add_argument("--ver", action="store_true",
                   help="que hay en el catalogo y que sabe hacer el despliegue")
    p.add_argument("--cada", help="intervalo: 60m, 6h, 1d")
    p.add_argument("--apagar", action="store_true")
    p.add_argument("--actor", default="", help="quien lo decide")
    p.add_argument("--motivo", default="", help="por que")
    a = p.parse_args(argv)

    if a.ver or not a.job:
        if not a.ver:
            p.print_help()
            return 2
        try:
            with puerta.sesion(puerta.COORDINADOR) as cur:
                return _ver(cur)
        except Exception as e:                                   # noqa: BLE001
            print(f"\n  no se pudo consultar: {type(e).__name__}\n")
            return 1

    #  ACTOR Y MOTIVO, SIEMPRE, para encender y para apagar. Sin saber quien lo
    #  decidio no se puede discutir despues, y apagar sin motivo deja un
    #  "¿por que estaba apagado?" que nadie va a poder contestar.
    if not a.actor.strip() or not a.motivo.strip():
        print("\n  Hacen falta --actor y --motivo. Esto pone a un sistema a\n"
              "  actuar sin que nadie mire, o lo detiene: las dos cosas hay\n"
              "  que poder discutirlas despues.\n")
        return 2

    #  SOLO LO QUE EL DESPLIEGUE SABE HACER. Una fila sin handler es un turno
    #  que falla cada hora para siempre, y el error no señalaria aqui.
    if not registro.conocido(a.job):
        print(f"\n  '{a.job}' no esta cableado en este despliegue.\n"
              f"  Los que si: {', '.join(sorted(registro.registrados()))}\n")
        return 1

    #  EL INTERVALO SE VALIDA ANTES DE CONECTAR. Hacerlo adentro daba un error
    #  de base --"no hay datos de conexion"-- para un '30s' mal escrito: un
    #  mensaje que manda a revisar el .env cuando el problema esta en la linea
    #  que se acaba de tipear.
    intervalo_sql = ""
    if not a.apagar:
        if not a.cada:
            print("\n  Falta --cada: cada cuanto despertarlo (60m, 6h).\n")
            return 2
        try:
            intervalo_sql, _ = _intervalo(a.cada)
        except ValueError as e:
            print(f"\n  {e}\n")
            return 2

    try:
        with puerta.sesion(puerta.COORDINADOR) as cur:
            if a.apagar:
                return _apagar(cur, a.job, a.actor.strip(), a.motivo.strip())
            return _encender(cur, a.job, intervalo_sql,
                             a.actor.strip(), a.motivo.strip())
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de un error de base trae el SQL.
        print(f"\n  no se pudo: {type(e).__name__}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
