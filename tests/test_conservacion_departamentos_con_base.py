# -*- coding: utf-8 -*-
"""
================================================================================
 CONSERVACION DE DEPARTAMENTOS  --  contra PostgreSQL de verdad
================================================================================

Por que esta prueba existe aparte de 'test_guarda_cargar_config.py'
-------------------------------------------------------------------
Aquella afirma sobre '_lo_que_pisaria', que es la funcion que DECIDE. Esta
afirma sobre 'cargar()', que es la que ESCRIBE -- y entre una y otra hay una
conexion, una transaccion y un 'update' que la primera no atraviesa.

Es la distincion que CLAUDE.md §6 cobra dos veces: una prueba del backend en
verde mientras el salto siguiente pierde el dato. Aca el salto es
decidir -> escribir, y lo unico que lo cubre es una base real.

Lo que fija
-----------
1. Un YAML sin 'areas' NO borra los departamentos de la base: corta antes.
2. El corte NOMBRA lo que se perderia, para que quien lo lea sepa que pasa.
3. La config de la base queda INTACTA despues del intento.
4. Con --forzar si se pisan: la salida deliberada sigue existiendo.

Como se corre
-------------
Necesita un PostgreSQL de laboratorio, NUNCA produccion. Se salta solo si no
hay uno, con exit 0 y diciendolo -- igual que las otras pruebas con base de
este repositorio.

    docker run -d --rm --name pg-conservacion -e POSTGRES_PASSWORD=prueba \\
        -e POSTGRES_DB=laboratorio -p 15432:5432 postgres:16

    set DBHOST=localhost & set DBPORT=15432 & set DBUSER=postgres
    set DBPASSWORD=prueba & set DBNAME=laboratorio
    py -3.13 tests/test_conservacion_departamentos_con_base.py

La prueba crea su propio esquema minimo y sus propios datos inventados. No
lee ni escribe nada de produccion.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
#  SE SALTA SIN BASE, Y LO DICE. Un exit 0 silencioso seria peor que no tener
#  la prueba: el CI la contaria como verde sin haber comprobado nada.
# ---------------------------------------------------------------------------
if not os.environ.get("DBHOST"):
    print("[saltada] No hay DBHOST: esta prueba necesita un PostgreSQL de")
    print("          laboratorio. Ver la cabecera del archivo. NO se comprobo")
    print("          la conservacion de departamentos.")
    raise SystemExit(0)

#  Guarda contra el peor error posible: correrla contra produccion.
_HOST = os.environ.get("DBHOST", "")
if _HOST not in ("localhost", "127.0.0.1", "::1", "host.docker.internal"):
    print(f"[ABORTA] DBHOST='{_HOST}' no es local. Esta prueba ESCRIBE y "
          f"BORRA: solo corre contra un laboratorio.")
    raise SystemExit(1)

import psycopg                                           # noqa: E402
import yaml                                              # noqa: E402

import json                                              # noqa: E402

from cli import cargar_config                            # noqa: E402
from nucleo.config import editor                         # noqa: E402
from nucleo.config.schema import TenantConfig            # noqa: E402
from nucleo.persistencia.conexion import dsn             # noqa: E402

# ---------------------------------------------------------------------------
#  SE AISLA EL SUJETO DE PRUEBA, y vale explicar por que no es hacer trampa.
#
#  'cargar()' tiene DOS guardas en serie: primero la de alineacion con git
#  --que esta copia no pasa, porque tiene commits propios sin publicar-- y
#  despues la de conservacion, que es la que esta prueba existe para medir.
#  La primera corta antes y nunca se llega a la segunda.
#
#  Saltearla con 'forzar=True' no sirve: ese mismo interruptor apaga TAMBIEN
#  la de conservacion, asi que la prueba pasaria sin haber comprobado nada.
#  Se neutraliza solo la de git, que ya tiene su propia prueba
#  ('test_guarda_alineacion_git.py') y no es el sujeto de esta.
#
#  ESTO SE DESCUBRIO porque la prueba afirmaba sobre el TEXTO del corte y no
#  solo sobre que cortara: con "corto o no corto" daba verde, y lo hacia por
#  la razon equivocada. Es exactamente el falso verde que CLAUDE.md §6
#  describe -- una prueba verde con el sintoma vivo.
# ---------------------------------------------------------------------------
editor.problemas_de_alineacion_git = lambda *a, **k: []

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


AREAS = [
    {"nombre": "cartera", "etiqueta": "Cartera", "agentes": ["facturacion"],
     "icono": "factura", "color": "#7c5cd6"},
    {"nombre": "soporte_tecnico", "etiqueta": "Soporte Tecnico",
     "agentes": ["soporte"], "icono": "llave", "color": "#2f6fed"},
]


def _preparar(cur) -> str:
    """Esquema minimo y una empresa de laboratorio. Datos inventados."""
    cur.execute("create schema if not exists asistente")
    cur.execute("""create table if not exists public.organization (
                     id uuid primary key default gen_random_uuid(),
                     name text not null,
                     created_at timestamptz not null default now())""")
    cur.execute("""create table if not exists asistente.tenant_config (
                     organization_id uuid primary key
                       references public.organization(id),
                     slug text unique not null,
                     config jsonb not null,
                     config_version integer not null default 1,
                     actualizado_en timestamptz not null default now())""")
    #  'cargar()' anota cada version en el historial: sin esta tabla, la
    #  escritura revienta DESPUES de haber pisado la config, que es el peor
    #  momento posible para fallar.
    cur.execute("""create table if not exists asistente.tenant_config_historial (
                     organization_id uuid not null,
                     config_version integer not null,
                     config jsonb not null,
                     creado_en timestamptz not null default now(),
                     primary key (organization_id, config_version))""")
    cur.execute("delete from asistente.tenant_config_historial")
    cur.execute("delete from asistente.tenant_config")
    cur.execute("delete from public.organization")
    cur.execute("insert into public.organization (name) values "
                "('ISP de laboratorio') returning id")
    return cur.fetchone()[0]


print("=" * 70)
print(" CONSERVACION DE DEPARTAMENTOS CONTRA POSTGRES")
print("=" * 70)

#  El YAML real del tenant sirve de molde: asi la config que se guarda valida
#  contra el esquema de verdad y no contra un minimo inventado que pasaria
#  por casualidad.
crudo = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
crudo["areas"] = AREAS
#  Se normaliza con el esquema REAL antes de guardar: es exactamente lo que
#  escribe 'cargar()', y ademas resuelve los tipos que el YAML trae sueltos
#  (una fecha de YAML no es JSON serializable).
molde = TenantConfig(**crudo).model_dump(mode="json")

with psycopg.connect(dsn(), connect_timeout=20) as con, con.cursor() as cur:
    org = _preparar(cur)
    cur.execute("""insert into asistente.tenant_config
                     (organization_id, slug, config, config_version)
                   values (%s, %s, %s, 1)""",
                (org, molde["identidad"]["slug"], json.dumps(molde)))
    con.commit()
    print(f"\n[base] empresa de laboratorio con {len(AREAS)} departamentos")

#  El archivo que se intenta cargar: el mismo, pero SIN departamentos. Es
#  exactamente lo que paso el 19/10/2026.
sin_areas = dict(crudo)
sin_areas.pop("areas", None)
archivo = RAIZ / "tenants" / "_laboratorio_conservacion.config.yaml"
archivo.write_text(yaml.safe_dump(sin_areas, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")

print("\n[1] Un archivo sin departamentos NO puede borrarlos")
try:
    cargar_config.cargar(archivo)
    comprobar(False, "cargar() DEBIO cortar y no corto -- los departamentos se "
                     "habrian perdido")
    aviso = ""
except SystemExit as e:
    aviso = str(e)
    comprobar(True, "cargar() corta antes de escribir")
    comprobar("areas" in aviso,
              "el corte NOMBRA la seccion que se perderia")
    comprobar("BORRARIA" in aviso,
              "y dice BORRARIA: quien lo lee entiende que es una perdida")

print("\n[2] La base quedo INTACTA despues del intento")
with psycopg.connect(dsn(), connect_timeout=20) as con, con.cursor() as cur:
    cur.execute("select config, config_version from asistente.tenant_config "
                "where organization_id = %s", (org,))
    guardado, version = cur.fetchone()
    comprobar([a["nombre"] for a in (guardado.get("areas") or [])]
              == [a["nombre"] for a in AREAS],
              "los dos departamentos siguen en la base, con sus nombres")
    comprobar(version == 1,
              "y la version NO subio: un intento frenado no es un cambio")

print("\n[3] --forzar sigue siendo la salida deliberada")
#  La guarda protege del descuido, no de la decision. Si deja de haber forma
#  de pisar a proposito, alguien edita la base a mano y entonces no hay
#  registro de nada.
try:
    cargar_config.cargar(archivo, forzar=True)
    forzo = True
except SystemExit:
    forzo = False
comprobar(forzo, "con --forzar la carga se completa")

with psycopg.connect(dsn(), connect_timeout=20) as con, con.cursor() as cur:
    cur.execute("select config from asistente.tenant_config "
                "where organization_id = %s", (org,))
    guardado = cur.fetchone()[0]
    comprobar(not (guardado.get("areas") or []),
              "y ahi si se pisaron -- la salida existe y hace lo que dice")

archivo.unlink(missing_ok=True)

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Los departamentos de una empresa sobreviven a una carga de config.")
print("=" * 70)
