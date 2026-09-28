# -*- coding: utf-8 -*-
"""
================================================================================
 PRECHECK  --  lo que hay que comprobar ANTES de separar las credenciales
================================================================================

    py -3.13 despliegue/separacion_credenciales/precheck.py
    py -3.13 despliegue/separacion_credenciales/precheck.py --respaldo ruta.dump

Que es
------
Una foto del estado real, con veredicto. Sale con 1 si encuentra una condicion
CRITICA, para que un script de despliegue con 'set -e' no siga adelante.

Es SOLO LECTURA. No crea roles, no transfiere nada, no aplica migraciones. La
conexion se marca read_only, asi que el servidor rechaza cualquier escritura
aunque alguien anada una por error.

Por que existe
--------------
Cada paso de la transicion supone algo del estado anterior: que las 129 tablas
son de postgres, que no hay secuencias sueltas, que crm_user no alcanza el
esquema del motor. Comprobar eso a mano, en orden, la noche del cambio, es
como se olvida uno.

Ademas imprime los numeros que los pasos siguientes necesitan como GUARDA -- el
recuento de tablas a transferir y el de politicas RLS. 03_transferir_propiedad.sql
se niega a correr si el recuento no coincide con el que se le pasa.

Tres niveles
------------
  CRITICO  detiene el cambio. Es algo que rompe el plan o lo invalida.
  AVISO    no detiene. Es algo que conviene saber y que ya se sabia.
  DATO     no es un juicio: es un numero que hay que anotar.
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

try:
    from dotenv import load_dotenv
    load_dotenv(str(RAIZ / ".env"), override=False)
except ImportError:
    pass

import psycopg
from psycopg.rows import dict_row

from nucleo.persistencia.conexion import dsn

# Lo que el plan da por cierto. Si cambia, el plan cambia.
TABLAS_ESPERADAS = 129
ROL_TRAFICO = "crm_user"
ROL_MIGRACIONES = "crm_migrator"
ROL_DUENO = "crm_owner"
ROL_MOTOR = "motor_user"
ROL_EMERGENCIA = "postgres"

CRITICO, AVISO, DATO = "CRITICO", "AVISO", "DATO"
hallazgos: list[tuple[str, str, str]] = []


def anotar(nivel, que, detalle=""):
    hallazgos.append((nivel, que, detalle))
    marca = {CRITICO: "[CRITICO]", AVISO: "[aviso]  ", DATO: "[dato]   "}[nivel]
    print(f"  {marca} {que}" + (f"\n             {detalle}" if detalle else ""))


def seccion(t):
    print("\n" + "-" * 76 + f"\n  {t}\n" + "-" * 76)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--respaldo", metavar="RUTA",
                   help="ruta del respaldo ya restaurado y verificado; sin esto, "
                        "el precheck lo marca como CRITICO")
    p.add_argument("--esperadas", type=int, default=TABLAS_ESPERADAS,
                   help=f"tablas de 'public' que se espera transferir "
                        f"(por defecto {TABLAS_ESPERADAS})")
    args = p.parse_args()

    print("=" * 76)
    print("  PRECHECK  --  separacion de credenciales del CRM")
    print("=" * 76)

    try:
        con = psycopg.connect(dsn(), connect_timeout=15, row_factory=dict_row)
    except Exception as e:
        print(f"\n  [CRITICO] no se pudo conectar: {type(e).__name__}: {e}")
        return 1
    con.read_only = True

    def q(sql, params=None):
        with con.cursor() as cur:
            cur.execute(sql, params)
            f = cur.fetchall()
        con.rollback()
        return f

    def uno(sql, params=None):
        f = q(sql, params)
        return f[0] if f else {}

    # =========================================================================
    seccion("1. IDENTIDAD DE LA CONEXION")

    s = uno("select current_user as efectivo, session_user as sesion, "
            "current_database() as base, version() as v")
    anotar(DATO, f"current_user = {s['efectivo']}  |  session_user = {s['sesion']}")
    anotar(DATO, f"base = {s['base']}  |  {str(s['v']).split(' on ')[0]}")

    enviado = os.environ.get("DBUSER", "")
    if enviado and "." in enviado and enviado.split(".", 1)[0] != s["sesion"]:
        anotar(AVISO,
               f"DBUSER se envio como {enviado!r} y la base ve {s['sesion']!r}",
               "es el pooler recortando el sufijo del tenant: esperado")
    anotar(DATO, f"DBUSER de este proceso = {enviado or '(sin definir)'}")
    anotar(DATO, f"MOTOR_DBUSER = {os.environ.get('MOTOR_DBUSER') or '(sin definir)'}")
    anotar(DATO, f"MIGRATOR_DBUSER = {os.environ.get('MIGRATOR_DBUSER') or '(sin definir)'}")

    # =========================================================================
    seccion("2. ROLES")

    # '= any(%s)' con una lista, no 'in %s' con una tupla: psycopg3 no adapta
    # la tupla a una lista de parametros como hacia psycopg2.
    roles = {r["rolname"]: r for r in q(
        """select rolname, rolcanlogin, rolsuper, rolbypassrls
             from pg_roles
            where rolname = any(%s)""",
        ([ROL_TRAFICO, ROL_MIGRACIONES, ROL_DUENO, ROL_MOTOR,
          ROL_EMERGENCIA, "app_backend"],))}

    for nombre in (ROL_TRAFICO, ROL_MOTOR, "app_backend"):
        if nombre not in roles:
            anotar(CRITICO, f"falta el rol {nombre!r}, que el plan da por existente")
        else:
            r = roles[nombre]
            anotar(DATO, f"{nombre}: login={r['rolcanlogin']} "
                         f"super={r['rolsuper']} bypassrls={r['rolbypassrls']}")

    if ROL_TRAFICO in roles and roles[ROL_TRAFICO]["rolbypassrls"]:
        anotar(CRITICO, f"{ROL_TRAFICO} tiene BYPASSRLS: las politicas no lo alcanzarian")

    # Los dos nuevos: su AUSENCIA es lo normal antes del cambio.
    for nombre in (ROL_DUENO, ROL_MIGRACIONES):
        if nombre in roles:
            r = roles[nombre]
            anotar(DATO, f"{nombre} YA existe: login={r['rolcanlogin']} "
                         f"super={r['rolsuper']} bypassrls={r['rolbypassrls']}")
            if nombre == ROL_DUENO and r["rolcanlogin"]:
                anotar(CRITICO, f"{ROL_DUENO} tiene LOGIN y no debe tenerlo",
                       "con login, el pooler puede autenticarlo y deja de ser "
                       "solo un rol de propiedad")
            if r["rolsuper"] or r["rolbypassrls"]:
                anotar(CRITICO, f"{nombre} tiene SUPERUSER o BYPASSRLS")
        else:
            anotar(DATO, f"{nombre} no existe todavia (esperado antes del paso 1)")

    if ROL_MIGRACIONES in roles:
        tiene_set_role = q(
            """select 1 from pg_db_role_setting s
                 join pg_roles r on r.oid = s.setrole
                where r.rolname = %s and s.setconfig::text like %s""",
            (ROL_MIGRACIONES, "%role=" + ROL_DUENO + "%"))
        if not tiene_set_role:
            anotar(CRITICO,
                   f"{ROL_MIGRACIONES} existe pero le falta 'SET role = {ROL_DUENO}'",
                   "sin eso, cada tabla que cree una migracion queda de "
                   "crm_migrator y la separacion se deshace sola")

    # =========================================================================
    seccion("3. PROPIEDAD DE LAS TABLAS")

    por_dueno = {r["dueno"]: r["n"] for r in q(
        """select pg_get_userbyid(c.relowner) as dueno, count(*) as n
             from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
            group by 1""")}
    anotar(DATO, f"tablas de 'public' por propietario: {por_dueno}")

    total = sum(por_dueno.values())
    a_mover = por_dueno.get(ROL_EMERGENCIA, 0)
    anotar(DATO, f"total de tablas en 'public': {total}")
    anotar(DATO, f"### A TRANSFERIR (dueno={ROL_EMERGENCIA}): {a_mover} ###",
           f"pasarselo al paso 3:  -v esperadas={a_mover}")

    if total != args.esperadas:
        anotar(AVISO,
               f"hay {total} tablas y el plan se escribio con {args.esperadas}",
               "no es necesariamente un problema, pero hay que entender la "
               "diferencia antes de seguir")

    de_trafico = por_dueno.get(ROL_TRAFICO, 0) + por_dueno.get(ROL_MIGRACIONES, 0)
    if de_trafico:
        anotar(CRITICO,
               f"{de_trafico} tabla(s) ya pertenecen a una credencial CON login",
               "un dueno se saltea su propia politica RLS salvo que este FORCE")

    # Secuencias sueltas: lo unico que no seguiria a su tabla.
    sueltas = q("""select s.relname
                     from pg_class s join pg_namespace n on n.oid = s.relnamespace
                    where n.nspname = 'public' and s.relkind = 'S'
                      and not exists (
                        select 1 from pg_depend d
                         where d.objid = s.oid
                           and d.refclassid = 'pg_class'::regclass
                           and d.deptype in ('a', 'i'))""")
    if sueltas:
        anotar(CRITICO,
               f"{len(sueltas)} secuencia(s) SUELTA(S): no seguirian a su tabla",
               ", ".join(r["relname"] for r in sueltas))
    else:
        n_seq = uno("""select count(*) as n from pg_class c
                         join pg_namespace n on n.oid = c.relnamespace
                        where n.nspname='public' and c.relkind='S'""")["n"]
        anotar(DATO, f"{n_seq} secuencias, todas atadas a su tabla: siguen solas")

    # Objetos que el plan da por inexistentes.
    otros = uno("""select
        count(*) filter (where c.relkind = 'v') as vistas,
        count(*) filter (where c.relkind = 'm') as matviews,
        (select count(*) from pg_trigger t
           join pg_class tc on tc.oid = t.tgrelid
           join pg_namespace tn on tn.oid = tc.relnamespace
          where tn.nspname = 'public' and not t.tgisinternal) as triggers
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'""")
    if any(otros.values()):
        anotar(AVISO, f"aparecieron objetos que el plan no contemplaba: {otros}",
               "revisar si hay que transferirlos aparte")
    else:
        anotar(DATO, "0 vistas, 0 vistas materializadas, 0 triggers de usuario")

    # =========================================================================
    seccion("4. RLS")

    rls = uno("""select
        count(*) filter (where c.relrowsecurity) as con_rls,
        count(*) filter (where c.relforcerowsecurity) as forzada
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r'""")
    politicas = uno("select count(*) as n from pg_policies where schemaname='public'")["n"]
    anotar(DATO, f"tablas con RLS: {rls['con_rls']}  |  con FORCE: {rls['forzada']}")
    anotar(DATO, f"### POLITICAS EN 'public': {politicas} ###",
           "anotarlo: tras la transferencia tiene que dar el MISMO numero")

    if rls["con_rls"] != rls["forzada"]:
        anotar(CRITICO,
               f"hay {rls['con_rls'] - rls['forzada']} tabla(s) con RLS pero SIN FORCE",
               "tras mover la propiedad, el dueno se saltearia su politica en esas")

    # =========================================================================
    seccion("5. LA FRONTERA CON EL MOTOR")

    def existe_esquema(n):
        return bool(q("select 1 from pg_namespace where nspname=%s", (n,)))

    if ROL_TRAFICO in roles and existe_esquema("asistente"):
        alcanza = uno("select has_schema_privilege(%s,'asistente','usage') as p",
                      (ROL_TRAFICO,))["p"]
        if alcanza:
            anotar(CRITICO, f"{ROL_TRAFICO} alcanza el esquema 'asistente'",
                   "la frontera es que ninguno llegue al esquema del otro")
        else:
            anotar(DATO, f"{ROL_TRAFICO} no alcanza 'asistente': correcto")

    if ROL_MOTOR in roles:
        del_motor = uno("""select count(*) as n from pg_class c
                             join pg_namespace n on n.oid = c.relnamespace
                            where n.nspname='public' and c.relkind='r'
                              and pg_get_userbyid(c.relowner) = %s""",
                        (ROL_MOTOR,))["n"]
        if del_motor:
            anotar(CRITICO, f"{ROL_MOTOR} es dueno de {del_motor} tabla(s) de 'public'")
        else:
            anotar(DATO, f"{ROL_MOTOR} no administra 'public': correcto")

    vivas = q("""select usename, count(*) as n from pg_stat_activity
                  where datname = current_database() and usename is not null
                    and pid <> pg_backend_pid()
                  group by 1 order by 2 desc limit 6""")
    anotar(DATO, "conexiones vivas: " +
           ", ".join(f"{r['usename']}={r['n']}" for r in vivas))

    # =========================================================================
    seccion("6. LAS 6 MIGRACIONES PENDIENTES")

    fase1 = uno("""select count(*) as n from asistente.migraciones_aplicadas
                    where archivo in ('202609151710_interruptor_autonomia.sql',
                                      '202609151715_operaciones_externas.sql')""")["n"]
    django = uno("""select count(*) as n from django_migrations
                     where app = 'operaciones'
                        or (app = 'common' and name like '0039=_%%' escape '=')
                        or (app = 'campo'  and name like '0003=_%%' escape '=')""")["n"]
    anotar(DATO, f"Fase 1 aplicadas: {fase1} de 2  |  Etapa B aplicadas: {django} de 4")
    if fase1 == 2 and django == 4:
        anotar(DATO, "las 6 ya estan aplicadas: el paso de migraciones se salta")
    elif fase1 or django:
        anotar(AVISO, "hay migraciones aplicadas A MEDIAS",
               "revisar cuales antes de seguir; el orden importa")
    else:
        anotar(DATO, "ninguna de las 6 aplicada: estado esperado antes del cambio")

    # =========================================================================
    seccion("7. RESPALDO")

    if not args.respaldo:
        anotar(CRITICO, "no se declaro ningun respaldo restaurado y verificado",
               "pasar --respaldo RUTA solo DESPUES de restaurarlo en una base "
               "desechable y contar filas. Un pg_dump que nadie restauro no es "
               "un respaldo")
    else:
        ruta = Path(args.respaldo)
        if not ruta.exists():
            anotar(CRITICO, f"el respaldo declarado no existe: {ruta}")
        else:
            mb = ruta.stat().st_size / (1024 * 1024)
            anotar(DATO, f"respaldo declarado: {ruta.name} ({mb:.1f} MB)")
            anotar(AVISO,
                   "que el archivo exista no prueba que restaure",
                   "el precheck no puede comprobarlo; lo confirma quien lo "
                   "restauro y conto filas")

    # =========================================================================
    con.close()
    print("\n" + "=" * 76)
    criticos = [h for h in hallazgos if h[0] == CRITICO]
    avisos = [h for h in hallazgos if h[0] == AVISO]
    print(f"  {len(criticos)} critico(s), {len(avisos)} aviso(s), "
          f"{len(hallazgos) - len(criticos) - len(avisos)} dato(s)")
    if criticos:
        print("\n  NO-GO. Condiciones criticas:")
        for _, que, _ in criticos:
            print(f"    - {que}")
    else:
        print("\n  Sin condiciones criticas.")
        print("  GO depende ademas de lo que este precheck NO puede ver:")
        print("    * que el respaldo restaure de verdad")
        print("    * que crm_migrator autentique POR EL POOLER")
        print("    * que se use 'up -d --force-recreate', nunca 'restart'")
    print("=" * 76)
    return 1 if criticos else 0


if __name__ == "__main__":
    raise SystemExit(main())
