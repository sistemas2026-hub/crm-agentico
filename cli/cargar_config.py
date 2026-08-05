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
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config          # noqa: E402

load_dotenv(RAIZ / ".env", override=True)
URL = os.environ.get("DATABASE_URL")
if not URL:
    raise SystemExit("Falta DATABASE_URL en el .env")


def _conectar():
    return psycopg.connect(URL, connect_timeout=40)


def cargar(ruta: Path) -> None:
    cfg = cargar_config(ruta)                     # valida o revienta
    slug = cfg.identidad.slug
    datos = cfg.model_dump(mode="json")

    with _conectar() as con, con.cursor() as cur:
        cur.execute("select id from public.organizations where slug = %s", (slug,))
        fila = cur.fetchone()
        if not fila:
            raise SystemExit(
                f"No existe public.organizations con slug '{slug}'.\n"
                f"Crearla primero: el asistente no inventa organizaciones, "
                f"porque esa tabla es de la aplicacion y no suya.")
        org = fila[0]

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
                             (organization_id, config, config_version)
                           values (%s, %s, 1)""", (org, json.dumps(datos)))
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
                       join public.organizations o on o.id = tc.organization_id
                       where o.slug = %s""", (slug,))
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
        cargar(Path(args[0]))
