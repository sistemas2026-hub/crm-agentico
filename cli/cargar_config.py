# -*- coding: utf-8 -*-
"""
================================================================================
 CARGAR tenant.config.yaml A LA BASE
================================================================================

El YAML es la fuente que se versiona en git; la base es de donde LEE el sistema
en ejecucion. Este comando lleva uno al otro.

Se guarda en la base, y no se lee del disco en caliente, por dos razones:
cambiar la configuracion no debe exigir redeploy, y varios procesos (API, worker
de ingesta, cron de informes) tienen que ver exactamente la MISMA version.

Nunca se carga sin validar: un YAML con un rol mal escrito o un filtro que la
API ignora se rechaza aqui, no en produccion con un cliente adelante.

'config_version' sube en cada carga efectiva. Queda en evaluation_runs para
poder decir "esta corrida se hizo con la config v3", y no adivinarlo despues.

Uso
---
    py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml
    py -3.13 cli/cargar_config.py --todos
    py -3.13 cli/cargar_config.py --ver rapilink
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config          # noqa: E402
from nucleo.persistencia.conexion import dsn     # noqa: E402

load_dotenv(RAIZ / ".env", override=True)


def _conectar():
    return psycopg.connect(dsn(), connect_timeout=40)


def _organizacion(cur, slug: str, org_id: str | None = None) -> str:
    """
    Resuelve slug -> organization_id.

    El slug no existe en public.organization: esa tabla es del CRM y solo tiene
    'name'. El vinculo vive en asistente.tenant_config.slug, y esta funcion es
    la que lo establece la primera vez.

    Tres caminos, en orden. El ultimo falla ruidosamente a proposito: vincular
    la configuracion a la empresa equivocada mezcla los datos de dos ISP, y es
    un error que nadie nota hasta que es tarde.
    """
    cur.execute("select organization_id from asistente.tenant_config where slug = %s",
                (slug,))
    fila = cur.fetchone()
    if fila:
        return fila[0]                            # ya vinculado

    if org_id:
        cur.execute("select id from public.organization where id = %s", (org_id,))
        if not cur.fetchone():
            raise SystemExit(f"No existe public.organization con id '{org_id}'.")
        return org_id

    cur.execute("select id, name from public.organization order by created_at")
    orgs = cur.fetchall()
    if len(orgs) == 1:
        org, nombre = orgs[0]
        print(f"    vinculando '{slug}' a la unica organizacion del CRM: {nombre}")
        return org
    if not orgs:
        raise SystemExit(
            f"El CRM no tiene ninguna organizacion todavia.\n"
            f"Crearla primero desde el CRM: el asistente no inventa "
            f"organizaciones, esa tabla la mantiene django-crm.")
    listado = "\n".join(f"      {i}  {n}" for i, n in orgs)
    raise SystemExit(
        f"Hay {len(orgs)} organizaciones en el CRM y '{slug}' no esta vinculado "
        f"a ninguna. Indicar cual:\n\n"
        f"      py -3.13 cli/cargar_config.py tenants/{slug}.config.yaml --org-id <id>\n\n"
        f"{listado}")


def cargar(ruta: Path, org_id: str | None = None) -> None:
    cfg = cargar_config(ruta)                     # valida o revienta
    slug = cfg.identidad.slug
    datos = cfg.model_dump(mode="json")

    with _conectar() as con, con.cursor() as cur:
        org = _organizacion(cur, slug, org_id)

        # Si el contenido no cambio, no se sube la version: asi 'config_version'
        # cuenta cambios reales y no ejecuciones del comando.
        cur.execute("""select config, config_version from asistente.tenant_config
                       where organization_id = %s""", (org,))
        actual = cur.fetchone()

        if actual and actual[0] == datos:
            print(f"[=] {slug}: sin cambios (v{actual[1]})")
            return

        if actual:
            cur.execute("""update asistente.tenant_config
                           set config = %s,
                               config_version = config_version + 1,
                               actualizado_en = now()
                           where organization_id = %s
                           returning config_version""",
                        (json.dumps(datos), org))
            version = cur.fetchone()[0]
            print(f"[^] {slug}: actualizada a v{version}")
        else:
            cur.execute("""insert into asistente.tenant_config
                             (organization_id, slug, config, config_version)
                           values (%s, %s, %s, 1)""",
                        (org, slug, json.dumps(datos)))
            print(f"[+] {slug}: cargada v1")
        con.commit()

    print(f"    roles: {', '.join(cfg.roles)}")
    print(f"    herramientas: {len(cfg.herramientas)}   modelo: "
          f"{cfg.llm.modelo_por_defecto}")


def ver(slug: str) -> None:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""select tc.config_version, tc.plan, tc.activo,
                              tc.actualizado_en, tc.config
                       from asistente.tenant_config tc
                       where tc.slug = %s""", (slug,))
        fila = cur.fetchone()
    if not fila:
        raise SystemExit(f"'{slug}' no tiene configuracion cargada.")
    v, plan, activo, cuando, cfg = fila
    print(f"{slug}  v{v}  plan={plan}  activo={activo}")
    print(f"  actualizada: {cuando:%Y-%m-%d %H:%M}")
    print(f"  asistente  : {cfg['persona']['nombre_asistente']}")
    print(f"  roles      : {', '.join(cfg['roles'])}")
    print(f"  modelo     : {cfg['llm']['modelo_por_defecto']}")
    print(f"  embeddings : {cfg['rag']['modelo_embeddings']} "
          f"({cfg['rag']['dimensiones']} dim)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__.split("Uso\n---")[1].strip())

    # --org-id <uuid>: vincula un slug nuevo a una organizacion concreta del CRM.
    # Solo hace falta la primera vez, y solo si hay mas de una.
    org_id = None
    if "--org-id" in args:
        i = args.index("--org-id")
        org_id = args[i + 1]
        del args[i:i + 2]

    if args[0] == "--ver":
        ver(args[1])
    elif args[0] == "--todos":
        for y in sorted((RAIZ / "tenants").glob("*.config.yaml")):
            if y.name.startswith("tenant.config.example"):
                continue                          # la plantilla no es un tenant
            try:
                cargar(y)
            except SystemExit as e:
                print(f"[!] {y.name}: {e}")
    else:
        cargar(Path(args[0]), org_id)
