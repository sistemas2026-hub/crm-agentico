# -*- coding: utf-8 -*-
"""
Respaldo completo y RESTAURABLE de la base del CRM + asistente.

    py -3.13 despliegue/respaldo/respaldar.py [--destino CARPETA]

Produce TRES artefactos. Los tres hacen falta: con dos, la restauracion
termina en 0 y deja el scheduler roto (medido en el paso 10.2).

  1. <sello>_datos.dump    pg_dump --format=custom de los 3 esquemas, CON
                           dueños y privilegios.
  2. <sello>_roles.sql     pg_dumpall --roles-only. Crea los roles y sus
                           membresias. Medido: 25 CREATE ROLE, 43 ALTER ROLE,
                           33 GRANT de membresia.
  3. <sello>_entorno.sql   Lo que NINGUNO de los dos anteriores transporta, y
                           que hay que generar leyendo el catalogo:
                             - las extensiones y EN QUE ESQUEMA viven;
                             - el ACL de esquemas ajenos a los 3 volcados
                               (p.ej. 'grant usage on schema extensions to
                               asistente_owner', sin el cual job_claim falla);
                             - los ajustes de pg_db_role_setting de NUESTROS
                               roles (p.ej. el 'set role = crm_owner' de
                               crm_migrator).

POR QUE NO SE USA --schema=extensions PARA EL PUNTO 3
-----------------------------------------------------
Se probo (paso 10.3): trae 'CREATE SCHEMA extensions' y, con el, los event
triggers internos de Supabase --grant_pg_cron_access, pgrst_ddl_watch,
grant_pg_net_access-- que son de supabase_admin y referencian extensiones que
el destino puede no tener. Y NO trae la extension: pg_dump no vuelca
extensiones cuando se le pasa --schema. Por eso el artefacto 3 se genera
leyendo el catalogo, no ampliando el volcado.

SECRETOS
--------
pg_db_role_setting tiene ajustes a NIVEL DE BASE que incluyen el secreto JWT
del proyecto. El artefacto 3 los EXCLUYE por diseño: solo se emiten ajustes de
los roles de la lista ROLES_PROPIOS, nunca los de ambito 'toda la base' ni los
de los roles de plataforma de Supabase.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from dotenv import load_dotenv
load_dotenv(str(RAIZ / ".env"), override=False)

import psycopg
from psycopg.rows import dict_row

ESQUEMAS = ("public", "asistente", "asistente_ledger")

# Los roles que crea y usa este proyecto. Todo lo demas es plataforma de
# Supabase y no se transporta: en un destino Supabase ya existe, y en un
# PostgreSQL desnudo no tiene sentido.
ROLES_PROPIOS = ("crm_user", "crm_owner", "crm_migrator", "motor_user",
                 "app_backend", "asistente_owner", "job_executor",
                 "scheduler_coordinator", "monitor_ro")


def dsn_partes():
    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        raise SystemExit(f"faltan variables de entorno: {', '.join(faltan)}")
    return {v: os.environ[v] for v in
            ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")}


class Herramientas:
    """
    Ejecuta pg_dump / pg_dumpall, aqui o dentro de un contenedor.

    Si la maquina no tiene las herramientas cliente instaladas --el caso de
    cualquier estacion Windows sin PostgreSQL local-- se usan las de una imagen
    de contenedor. La VERSION MAYOR tiene que coincidir con la del servidor
    (produccion es 17.6), o pg_dump se niega a volcar.
    """

    def __init__(self, imagen: str | None, destino: Path, clave: str):
        self.imagen = imagen
        self.destino = destino.resolve()
        self.clave = clave

    def ruta(self, archivo: Path) -> str:
        """Como se llama ese archivo desde donde corre la herramienta."""
        return f"/salida/{archivo.name}" if self.imagen else str(archivo)

    def correr(self, args, salida: Path | None = None) -> int:
        if self.imagen:
            cmd = ["docker", "run", "--rm",
                   "-v", f"{self.destino}:/salida",
                   "-e", f"PGPASSWORD={self.clave}", self.imagen, *args]
            entorno = dict(os.environ)
        else:
            cmd = list(args)
            entorno = {**os.environ, "PGPASSWORD": self.clave}
        if salida is not None:
            with salida.open("w", encoding="utf-8", newline="\n") as fh:
                return subprocess.run(cmd, env=entorno, stdout=fh).returncode
        return subprocess.run(cmd, env=entorno).returncode


def generar_entorno(con, destino: Path, sello: str) -> Path:
    """El artefacto 3, leido del catalogo."""
    cur = con.cursor()
    lineas = [
        "-- =========================================================================",
        f"--  ENTORNO  --  generado por respaldar.py el {datetime.now():%Y-%m-%d %H:%M:%S}",
        "-- =========================================================================",
        "--  Lo que ni pg_dump (3 esquemas) ni pg_dumpall --roles-only transportan.",
        "--  Se aplica DESPUES de los roles y ANTES de pg_restore.",
        "--",
        "--  Requiere la variable de psql 'base_destino':",
        "--      psql -v base_destino=postgres -f <este archivo>",
        "-- =========================================================================",
        "",
    ]

    # --- extensiones ------------------------------------------------------
    cur.execute("""select e.extname as ext, ns.nspname as esquema
                     from pg_extension e
                     join pg_namespace ns on ns.oid = e.extnamespace
                    where e.extname <> 'plpgsql'
                    order by 1""")
    exts = cur.fetchall()
    lineas += ["-- --- extensiones -------------------------------------------------------",
               "--  Con guarda de disponibilidad: si el servidor destino no tiene el",
               "--  binario, avisa por NOTICE en vez de abortar la restauracion entera.",
               ""]
    for r in exts:
        lineas += [
            "do $$",
            "begin",
            f"  if exists (select 1 from pg_available_extensions where name = '{r['ext']}') then",
            f"    execute 'create schema if not exists {r['esquema']}';",
            f"    execute 'create extension if not exists \"{r['ext']}\" with schema {r['esquema']}';",
            "  else",
            f"    raise notice 'extension {r['ext']} NO disponible en este servidor; "
            f"los objetos que dependan de ella fallaran al usarse';",
            "  end if;",
            "end $$;",
            "",
        ]

    # --- ACL de esquemas ajenos a los 3 volcados --------------------------
    #  Solo para NUESTROS roles: el resto es plataforma.
    cur.execute("""
        select ns.nspname as esquema,
               ae.grantee::regrole::text as rol,
               string_agg(distinct ae.privilege_type, ', '
                          order by ae.privilege_type) as privs
          from pg_namespace ns,
               lateral aclexplode(ns.nspacl) ae
         where ns.nspacl is not null
           and ns.nspname <> all(%s)
           and ns.nspname not in ('pg_catalog','information_schema','pg_toast')
           and ae.grantee::regrole::text = any(%s)
         group by 1, 2 order by 1, 2""",
                (list(ESQUEMAS), list(ROLES_PROPIOS)))
    acls = cur.fetchall()
    lineas += ["-- --- ACL de esquemas FUERA de los 3 volcados ---------------------------",
               "--  El caso que rompia la restauracion: las 10 funciones del scheduler son",
               "--  SECURITY DEFINER de asistente_owner, llaman a extensions.digest y",
               "--  corren con search_path=pg_catalog. Sin este USAGE, job_claim falla con",
               "--  'permission denied for schema extensions' en la PRIMERA llamada -- no",
               "--  al restaurar.",
               ""]
    if not acls:
        lineas.append("--  (ninguno)")
    for r in acls:
        lineas.append(f"grant {r['privs'].lower()} on schema {r['esquema']} to {r['rol']};")
    lineas.append("")

    # --- ajustes por rol ---------------------------------------------------
    cur.execute("""select r.rolname as rol, s.setdatabase as base, s.setconfig as cfg
                     from pg_db_role_setting s
                     join pg_roles r on r.oid = s.setrole
                    where r.rolname = any(%s)
                    order by 1""", (list(ROLES_PROPIOS),))
    ajustes = cur.fetchall()
    lineas += ["-- --- ajustes de pg_db_role_setting de NUESTROS roles -------------------",
               "--  Sin el 'role=crm_owner' de crm_migrator, cada tabla que cree una",
               "--  migracion posterior nace de crm_migrator -un rol CON login- y la",
               "--  separacion de credenciales se deshace en silencio.",
               "--  Los ajustes de ambito 'toda la base' NO se emiten: incluyen el",
               "--  secreto JWT del proyecto.",
               ""]
    if not ajustes:
        lineas.append("--  (ninguno)")
    for r in ajustes:
        alcance = " in database :\"base_destino\"" if r["base"] else ""
        for kv in r["cfg"]:
            clave, _, valor = kv.partition("=")
            lineas.append(
                f"alter role {r['rol']}{alcance} set {clave} = '{valor}';")
    lineas.append("")

    ruta = destino / f"{sello}_entorno.sql"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=str(Path.home() / "respaldo_crm"))
    ap.add_argument("--imagen", default=None,
                    help="imagen de contenedor con las herramientas cliente, "
                         "para maquinas sin PostgreSQL instalado "
                         "(ej. pgvector/pgvector:pg17). La version MAYOR debe "
                         "coincidir con la del servidor.")
    # El artefacto 3 se genera desde ESTA maquina, no desde el contenedor. Con
    # --imagen apuntando a una base local, el nombre que ve el contenedor
    # (host.docker.internal) no resuelve aqui. Medido en el paso 10.4.
    ap.add_argument("--host-catalogo", default=None,
                    help="host para la consulta de catalogo del artefacto 3, "
                         "si difiere del que ve el contenedor (por ejemplo "
                         "'localhost' cuando --imagen usa host.docker.internal)")
    args = ap.parse_args()

    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = dsn_partes()
    h = Herramientas(args.imagen, destino, p["DBPASSWORD"])
    base = ["-h", p["DBHOST"], "-p", p["DBPORT"], "-U", p["DBUSER"]]

    print(f"  sello: {sello}   destino: {destino}")
    print(f"  herramientas: {args.imagen or 'locales (PATH)'}")

    # 1) datos -- CON dueños y privilegios. Nunca --no-owner ni --no-privileges.
    f1 = destino / f"{sello}_datos.dump"
    cmd = ["pg_dump", *base, "-d", p["DBNAME"], "--format=custom"]
    for e in ESQUEMAS:
        cmd += [f"--schema={e}"]
    cmd += ["-f", h.ruta(f1)]
    cod = h.correr(cmd)
    print(f"  1/3 datos   : {f1.name}  "
          f"({f1.stat().st_size if f1.exists() else 0} bytes)  codigo={cod}")
    if cod:
        raise SystemExit(1)

    # 2) roles
    f2 = destino / f"{sello}_roles.sql"
    cod = h.correr(["pg_dumpall", *base, "--roles-only"], salida=f2)
    print(f"  2/3 roles   : {f2.name}  ({f2.stat().st_size} bytes)  codigo={cod}")
    if cod:
        raise SystemExit(1)

    # 3) entorno
    con = psycopg.connect(
        host=args.host_catalogo or p["DBHOST"], port=p["DBPORT"],
        dbname=p["DBNAME"], user=p["DBUSER"], password=p["DBPASSWORD"],
        sslmode="disable", connect_timeout=30, row_factory=dict_row)
    con.read_only = True
    try:
        f3 = generar_entorno(con, destino, sello)
    finally:
        con.close()
    print(f"  3/3 entorno : {f3.name}  ({f3.stat().st_size} bytes)")

    (destino / ".sello").write_text(sello, encoding="utf-8")
    print(f"\n  Los TRES artefactos son obligatorios. Ver B7_PROTOCOLO_RESPALDO.md")


if __name__ == "__main__":
    main()
