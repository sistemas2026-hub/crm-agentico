# -*- coding: utf-8 -*-
"""
================================================================================
 EL ENTORNO LOCAL IGUAL A PRODUCCION  --  20/10/2026
================================================================================

    py -3.13 cli/entorno_local.py levantar [--ciclo]
    py -3.13 cli/entorno_local.py bajar
    py -3.13 cli/entorno_local.py verificar
    py -3.13 cli/entorno_local.py copiar --leo-produccion [--ignorar-hora]
    py -3.13 cli/entorno_local.py retapar      (si 'copiar' encontro restos)
    py -3.13 cli/entorno_local.py descartar    (tira la copia en memoria)

POR QUE EXISTE
--------------
El usuario pidio poder probar en local lo mismo que corre en produccion, y
pasar a produccion solo lo que el confirmo. Ese dia lo unico "local" era
codigo local contra la base REAL (DESPLIEGUE.md), o bases vacias que no
reproducian nada: "donde esta cada ticket" no se podia responder sin pegar
scripts en la terminal del servidor, y uno de esos dias el servidor se cayo.

QUE ES IGUAL Y QUE NO
---------------------
Igual: las imagenes y servicios de docker-compose.prod.yml, PostgreSQL 17, el
modelo de roles (crm_owner / crm_migrator / crm_user / motor_user), los datos
y la configuracion del tenant (copiados de la base de produccion), y las
credenciales de LECTURA de WispHub y SmartOLT. Distinto, a proposito, y lo
dice docker-compose.local.yml: nada ESCRIBE afuera (SIN_EFECTOS_EXTERNOS),
WhatsApp no envia, el correo va a la consola, sin push a los telefonos, y el
ciclo y el reloj corren solo cuando se piden.

LA COPIA DE DATOS, Y POR QUE ASI
--------------------------------
1. Se LEE produccion una sola vez (pg_dump) y nunca se escribe. Exige
   '--leo-produccion' para que nadie lo dispare sin decidirlo, y se niega en
   la franja :05-:22 de cada hora, que es cuando corren el ciclo del
   Supervisor y la conciliacion (el 20/10/2026 el servidor se cayo en esa
   franja).
2. Los datos llegan a una base TEMPORAL que vive en memoria (tmpfs): lo que
   tiene nombres y telefonos reales no se escribe en ningun disco.
3. Ahi se TAPAN: nombres, telefonos, correos, documentos y direcciones de
   clientes se reemplazan por valores falsos (iguales en todas las tablas
   dentro de una misma copia, con una sal al azar que no se guarda); el texto
   libre pasa por nucleo/seguridad/redaccion.py, el mismo tapado del motor.
4. Se APAGA lo que podria producir un efecto: credenciales de WhatsApp,
   canales de avisos, dispositivos de push, sesiones, y la autonomia nace
   detenida.
5. Se ESCANEA el resultado buscando telefonos moviles y correos que hayan
   quedado. Si aparece alguno en una columna que no esta explicada, la copia
   NO se entrega: la base local no se toca y la temporal queda viva en
   memoria para ajustar las reglas ('retapar') o tirarla ('descartar').
6. Recien ahi se reemplaza la base local.

LO QUE EL TAPADO NO ALCANZA, dicho
----------------------------------
El texto libre (descripciones de tickets, mensajes) puede traer nombres de
personas escritos a mano: la redaccion por patron saca cedulas, telefonos,
correos, URLs y coordenadas, no nombres. Y si en local se enciende el reloj
(levantar --ciclo), lo que se LEE de WispHub vuelve a traer nombres reales a
la base local: es el precio de leer la API real.

NUNCA IMPRIME UN SECRETO NI UN DATO: las credenciales viajan por el entorno
del proceso (nunca como argumento), y los informes dicen tabla.columna y
cuantas filas.
================================================================================
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

PROYECTO = "dexter-local"
ENV_LOCAL = RAIZ / ".env.local"
IMAGEN_PG = "pgvector/pgvector:pg17"
TEMPORAL = "dexter-copia-tmp"
PUERTO_TEMPORAL = 55441
CONTENEDOR_DB = f"{PROYECTO}-db-1"
SERVICIOS_APP = ("backend", "celery-worker", "celery-beat", "frontend", "motor",
                 "motor-reloj")
FRANJA_PICO = range(5, 23)        # minutos :05-:22
VARIABLES_DB = ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")


# =============================================================================
#  utilidades
# =============================================================================

def _leer_env(ruta: Path) -> dict:
    """KEY=VALOR por linea; quita comillas envolventes. NO imprime nada."""
    out = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def env_local() -> dict:
    if not ENV_LOCAL.exists():
        raise SystemExit(f"Falta {ENV_LOCAL.name}: ver docker-compose.local.yml.")
    return _leer_env(ENV_LOCAL)


def credenciales() -> str:
    """La RUTA del .env con las credenciales de siempre (WispHub, modelo, base)."""
    ruta = env_local().get("ARCHIVO_CREDENCIALES", "").strip()
    if not ruta or not Path(ruta).exists():
        raise SystemExit("Falta ARCHIVO_CREDENCIALES en .env.local (la ruta del .env "
                         "con las credenciales), o el archivo no existe.")
    return ruta


def compose(*args: str, ciclo: bool = False) -> list[str]:
    base = ["docker", "compose", "-p", PROYECTO, "--project-directory", str(RAIZ),
            "-f", str(RAIZ / "docker-compose.prod.yml"),
            "-f", str(RAIZ / "docker-compose.local.yml"),
            "--env-file", credenciales(), "--env-file", str(ENV_LOCAL)]
    if ciclo:
        base += ["--profile", "ciclo"]
    return base + list(args)


_TEL = re.compile(r"(?<!\d)(\+?57)?3\d{9}(?!\d)")
_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")


def _sin_datos(texto: str) -> str:
    """Un mensaje de error puede traer un valor de fila. Se tapa antes de mostrarlo."""
    return _MAIL.sub("<correo>", _TEL.sub("<telefono>", texto or ""))


def correr(cmd: list[str], *, check: bool = True, env: dict | None = None,
           entrada=None) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, stdin=entrada)
    if check and r.returncode != 0:
        raise SystemExit(f"Fallo: {' '.join(cmd[:4])} ...\n"
                         f"{_sin_datos((r.stderr or r.stdout or '')[-1500:])}")
    return r


def paso(n: str, texto: str) -> None:
    print(f"\n[{n}] {texto}", flush=True)


def _sql(contenedor: str, base: str, sql: str, check: bool = True) -> str:
    """psql como postgres por el socket del contenedor. La consulta va por entorno."""
    r = correr(["docker", "exec", "-e", "Q", contenedor, "sh", "-c",
                f'psql -U postgres -d {base} -At -v ON_ERROR_STOP=1 -c "$Q"'],
               env={**os.environ, "Q": sql}, check=check)
    return r.stdout


def _q(*partes: str) -> str:
    return ".".join('"' + p.replace('"', '""') + '"' for p in partes)


# =============================================================================
#  levantar / bajar
# =============================================================================

def levantar(ciclo: bool) -> int:
    paso("1", "levantando el stack local" + (" con el ciclo y el reloj" if ciclo else ""))
    r = correr(compose("up", "-d", ciclo=ciclo), check=False)
    if r.returncode != 0:
        print(_sin_datos(r.stderr[-1500:]))
        return 1
    time.sleep(20)
    print("  frontend: http://dexter.localhost:3300   backend: http://dexter.localhost:8300")
    return verificar()


def bajar() -> int:
    correr(compose("stop", ciclo=True), check=False)
    print("detenido (la base y sus datos quedan)")
    return 0


# =============================================================================
#  el tapado  --  corre contra la base TEMPORAL
# =============================================================================

TEXTO_LIBRE = re.compile(
    r"(descrip|mensaje|message|contenido|content|texto|^text$|body|nota|notes|"
    r"comentario|observacion|resultado|motivo|detalle|respuesta|resumen|summary|"
    r"transcripcion|analisis|subject|error|^name$|asunto)", re.I)

#  Tablas que NO se tocan: configuracion, catalogos y el PERSONAL de la empresa
#  (con sus cuentas se entra al entorno local). No son datos de clientes.
CONSERVAR = {
    "asistente.tenant_config", "asistente.tenant_config_historial",
    "asistente.tenant_secrets", "asistente.migraciones_aplicadas",
    "asistente.migraciones_ledger_esquema", "asistente.habilidades",
    "asistente.herramientas_cache", "asistente.herramientas_propuestas",
    "asistente.evaluation_sets", "asistente.evaluation_runs", "asistente.documents",
    "asistente.document_chunks", "asistente.area_colaborador", "asistente.tenant_users",
    "asistente.identidades_externas", "asistente.nivel_autonomia",
    "asistente.techo_autonomia_intentos", "asistente.interruptor_autonomia",
    "asistente.marcas_tv_desconocidas", "asistente.usage_daily",
    "asistente.job_catalogo", "asistente.job_schedule_state", "asistente.job_run",
    "asistente.job_attempt", "asistente.job_run_event",
    "public.users", "public.profile", "public.organization", "public.teams",
    "public.django_migrations", "public.django_content_type", "public.auth_group",
    "public.auth_permission", "public.custom_field_definition",
    "public.invoice_template", "public.campo_persona_de_campo",
    "public.campo_proveedor", "public.campo_configuracion_de_avisos",
    "public.campo_work_type", "public.campo_work_type_version",
    "public.campo_material_catalogo", "public.campo_plantilla_kit",
    "public.campo_zona_operativa", "public.campo_cuadrilla", "public.tags",
    "public.board", "public.board_column", "public.business_calendar",
    "public.business_holiday", "public.routing_rule", "public.approval_rule",
    "public.escalation_policy", "public.sales_goal", "public.product",
    "public.personal_access_token", "public.security_audit_log",
    "public.case_pipeline", "public.case_stage", "public.lead_pipeline",
    "public.lead_stage", "public.task_pipeline", "public.task_stage",
}

#  Columnas con un dato personal de un tipo conocido. El resto del texto de las
#  tablas que no se conservan pasa por la redaccion por patron.
TAPAR = {
    "public.accounts": {"name": "nombre", "email": "email", "phone": "tel",
                        "address_line": "dir"},
    "public.address": {"address_line": "dir", "street": "dir"},
    "public.contacts": {"first_name": "nombre", "last_name": "nombre",
                        "email": "email", "phone": "tel", "address_line": "dir"},
    "public.lead": {"first_name": "nombre", "last_name": "nombre",
                    "company_name": "nombre", "email": "email", "phone": "tel",
                    "address_line": "dir"},
    "public.case": {"external_client_name": "nombre"},
    "public.campo_orden_trabajo": {
        "cliente_nombre": "nombre", "contacto_alterno_nombre": "nombre",
        "cliente_telefono": "tel", "contacto_alterno_telefono": "tel",
        "cliente_direccion": "dir", "gps_lat": "gps", "gps_lng": "gps"},
    "public.solicitudes_solicitudservicio": {
        "nombre": "nombre", "correo": "email", "telefono": "tel",
        "direccion": "dir", "numero_documento": "doc", "gps_lat": "gps",
        "gps_lng": "gps"},
    "public.estimate": {"accepted_by_email": "email", "accepted_by_name": "nombre",
                        "client_address_line": "dir", "client_email": "email",
                        "client_name": "nombre", "client_phone": "tel"},
    "public.invoice": {"billing_address_line": "dir", "client_address_line": "dir",
                       "client_email": "email", "client_name": "nombre",
                       "client_phone": "tel"},
    "public.invoice_history": {"client_email": "email", "client_name": "nombre"},
    "public.recurring_invoice": {"client_email": "email", "client_name": "nombre"},
    "public.orders": {"billing_address_line": "dir", "shipping_address_line": "dir"},
    "public.email_message": {"from_address": "email", "to_addresses": "email",
                             "cc_addresses": "email"},
    "public.account_email": {"from_email": "email"},
    "public.contact_form_submission": {"name": "nombre", "email": "email",
                                       "ip_address": "ip"},
    "asistente.conversations": {"usuario_externo": "tel", "nombre_cliente": "nombre"},
    "asistente.canal_bajas": {"usuario_externo": "tel"},
}

#  Lo que se APAGA para que la copia no pueda producir un efecto.
APAGAR = (
    "delete from asistente.tenant_secrets where nombre ilike 'whatsapp%'",
    "update public.campo_canal_de_avisos set activo = false",
    "update public.campo_dispositivo_tecnico set activo = false, "
    "token = 'apagado-en-local-' || id",
    "update asistente.interruptor_autonomia set estado_anterior = estado, "
    "estado = 'detenido', actor = 'entorno-local', "
    "motivo = 'Copia local de produccion: la autonomia nace detenida'",
    "truncate public.django_session, public.magic_link_token, "
    "public.portal_access_token, public.token_blacklist_blacklistedtoken, "
    "public.token_blacklist_outstandingtoken",
)

#  Columnas donde un correo o un telefono que quede ESTA explicado, con su
#  motivo. Se llena mirando el escaneo de una copia real, nunca a ciegas.
RESIDUO_EXPLICADO: dict[str, str] = {}


class Tapador:
    """Valores falsos deterministas DENTRO de una copia (la sal no se guarda)."""

    def __init__(self):
        self.sal = secrets.token_hex(16)
        from nucleo.seguridad import redaccion
        self._redactar = redaccion.redactar

    def _h(self, v: str) -> str:
        return hashlib.sha256(f"{self.sal}|{v}".encode()).hexdigest()

    def nombre(self, v):
        return "Cliente " + self._h(v.strip().lower())[:6].upper()

    def tel(self, v):
        d = re.sub(r"\D", "", v)
        if len(d) < 7:
            return v
        #  '5700' no es un prefijo movil colombiano: un falso nunca se confunde
        #  con uno real, ni dispara el escaneo de residuos.
        return "5700" + str(int(self._h(d[-10:])[:14], 16))[-8:]

    def email(self, v):
        return "c" + self._h(v.strip().lower())[:10] + "@ejemplo.invalid"

    def doc(self, v):
        return "9" + str(int(self._h(re.sub(r"\D", "", v) or v)[:14], 16))[-9:]

    def dir(self, v):
        return "Direccion " + self._h(v.strip().lower())[:6].upper()

    #  Lo que 'redaccion.redactar' NO ve, medido al probar esta copia
    #  (20/10/2026): un telefono con separadores ('+57 300 123 4567') y una
    #  cedula con puntos ('1.045.678.901') pasaban enteros.
    _TEL_SEPARADO = re.compile(r"(?<!\d)(\+?57[\s.-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
    _CEDULA_PUNTOS = re.compile(r"(?<!\d)\d{1,3}(\.\d{3}){2,3}(?!\d)")

    def texto(self, v):
        v = self._TEL_SEPARADO.sub("[telefono oculto]", v)
        v = self._CEDULA_PUNTOS.sub("[documento oculto]", v)
        return self._redactar(v)

    def por_clave(self, clave: str, v: str) -> str:
        c = clave.lower()
        if re.search(r"(tel|phone|celular|movil|whatsapp|usuario_externo)", c):
            return self.tel(v)
        if re.search(r"(correo|email|mail)", c):
            return self.email(v)
        if re.search(r"(cedula|documento|identificacion|^nit$|_nit$|dni)", c):
            return self.doc(v)
        if re.search(r"(direccion|address|detalle_acceso)", c):
            return self.dir(v)
        if re.search(r"(nombre|^name$|cliente|contacto|titular)", c):
            return self.nombre(v)
        return self.texto(v)

    def json(self, v, clave: str = ""):
        if isinstance(v, dict):
            return {k: self.json(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [self.json(x, clave) for x in v]
        if isinstance(v, str):
            return self.por_clave(clave, v) if clave else self.texto(v)
        if isinstance(v, float) and re.search(r"(lat|lng|lon|gps)", clave, re.I):
            return round(v, 2)
        return v


def _columnas(con) -> dict[str, list[tuple[str, str]]]:
    filas = con.execute("""
        select c.table_schema || '.' || c.table_name, c.column_name, c.data_type
        from information_schema.columns c
        join information_schema.tables t
          on t.table_schema = c.table_schema and t.table_name = c.table_name
         and t.table_type = 'BASE TABLE'
        where c.table_schema in ('public', 'asistente')
          and c.data_type in ('text', 'character varying', 'json', 'jsonb',
                              'double precision', 'inet')
        order by 1, 2""").fetchall()
    out: dict[str, list[tuple[str, str]]] = {}
    for tabla, col, tipo in filas:
        out.setdefault(tabla, []).append((col, tipo))
    return out


def _que_hacer(tabla: str, col: str, tipo: str) -> str | None:
    if tabla in CONSERVAR:
        return None
    if col in TAPAR.get(tabla, {}):
        return TAPAR[tabla][col]
    if tipo in ("json", "jsonb"):
        return "json"
    if tipo in ("text", "character varying") and TEXTO_LIBRE.search(col):
        return "texto"
    return None


def tapar(con) -> dict:
    """Aplica el tapado y el apagado en la base de 'con'. Devuelve el informe."""
    from psycopg import errors, sql
    from psycopg.types.json import Jsonb

    t = Tapador()
    informe = {"columnas": 0, "filas": 0, "sin_columna": [], "fallidas": []}
    columnas = _columnas(con)
    for tabla, mapa in TAPAR.items():
        existentes = {c for c, _ in columnas.get(tabla, [])}
        informe["sin_columna"] += [f"{tabla}.{c}" for c in mapa if c not in existentes]

    for tabla, cols in columnas.items():
        plan = [(c, tipo, _que_hacer(tabla, c, tipo)) for c, tipo in cols]
        plan = [(c, tipo, q) for c, tipo, q in plan if q]
        if not plan:
            continue
        esquema, nombre = tabla.split(".")
        ident = sql.Identifier(esquema, nombre)
        sel = sql.SQL("select ctid, {} from {}").format(
            sql.SQL(", ").join(sql.Identifier(c) for c, _, _ in plan), ident)
        upd = sql.SQL("update {} set {} where ctid = %s").format(
            ident, sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(c)) for c, _, _ in plan))
        try:
            with con.transaction():
                filas = con.execute(sel).fetchall()
                cambios = []
                for fila in filas:
                    nuevos = []
                    for (c, tipo, q), v in zip(plan, fila[1:]):
                        if v is None or v == "":
                            nuevos.append(v)
                        elif q == "json":
                            nuevos.append(Jsonb(t.json(v)))
                        elif q == "gps":
                            nuevos.append(round(float(v), 2))
                        elif q == "ip":
                            nuevos.append("127.0.0.1")
                        else:
                            nuevos.append(getattr(t, q)(str(v)))
                    if list(fila[1:]) != [getattr(x, "obj", x) for x in nuevos]:
                        cambios.append((*nuevos, fila[0]))
                if cambios:
                    with con.cursor() as cur:
                        cur.executemany(upd, cambios)
        except errors.Error as e:
            informe["fallidas"].append(f"{tabla} ({type(e).__name__})")
            print(f"  {tabla}: FALLO {type(e).__name__}", flush=True)
            continue
        informe["columnas"] += len(plan)
        informe["filas"] += len(cambios)
        if cambios:
            print(f"  {tabla}: {len(plan)} columna(s), {len(cambios)} fila(s)", flush=True)

    for q in APAGAR:
        try:
            with con.transaction():
                con.execute(q)
        except errors.Error as e:
            informe["fallidas"].append(f"apagar: {q[:40]}... ({type(e).__name__})")
    return informe


def residuos(con) -> list[tuple[str, int]]:
    """Telefonos moviles y correos que quedaron, por tabla.columna. Sin valores."""
    hallados = []
    for tabla, cols in _columnas(con).items():
        if tabla in CONSERVAR:
            continue
        esquema, nombre = tabla.split(".")
        for c, tipo in cols:
            if tipo not in ("text", "character varying", "json", "jsonb"):
                continue
            col = _q(c)
            q = (f"select count(*) from {_q(esquema, nombre)} where "
                 f"regexp_replace({col}::text, '[A-Za-z0-9._%+-]+@ejemplo\\.invalid', '', 'g') "
                 f"~ '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\\.[A-Za-z]{{2,}}' "
                 f"or {col}::text ~ '(^|[^0-9])(\\+?57[ .-]?)?3[0-9]{{2}}[ .-]?[0-9]{{3}}[ .-]?[0-9]{{4}}([^0-9]|$)'")
            n = con.execute(q).fetchone()[0]
            if n:
                hallados.append((f"{tabla}.{c}", n))
    return hallados


# =============================================================================
#  copiar / retapar / descartar
# =============================================================================

def _psql_prod(sql: str) -> list[str]:
    """Una consulta de SOLO LECTURA a produccion, desde la base temporal."""
    r = correr(["docker", "exec", "-e", "Q", TEMPORAL, "sh", "-c",
                'PGPASSWORD="$DBPASSWORD" psql -h "$DBHOST" -p "$DBPORT" -U "$DBUSER" '
                '-d "$DBNAME" -At -v ON_ERROR_STOP=1 -c "$Q"'],
               env={**os.environ, "Q": sql})
    return [l for l in r.stdout.splitlines() if l.strip()]


def _roles_del(contenedor: str, base: str, *, de_produccion: bool):
    consulta = _psql_prod if de_produccion else (lambda s: [
        l for l in _sql(contenedor, base, s).splitlines() if l.strip()])
    roles = consulta("select rolname from pg_roles where rolname !~ '^pg_' "
                     "and rolname <> 'postgres' order by 1")
    miembros = consulta(
        "select g.rolname || '|' || m.rolname from pg_auth_members a "
        "join pg_roles g on g.oid = a.roleid join pg_roles m on m.oid = a.member "
        "where g.rolname !~ '^pg_' and m.rolname !~ '^pg_' "
        "and 'postgres' not in (g.rolname, m.rolname)")
    extensiones = consulta(
        "select e.extname || '|' || n.nspname from pg_extension e "
        "join pg_namespace n on n.oid = e.extnamespace "
        "where e.extname in ('vector', 'pgcrypto', 'pg_trgm', 'uuid-ossp', 'citext')")
    return roles, miembros, extensiones


def _replicar_roles(contenedor: str, base: str, roles, miembros, extensiones) -> None:
    for rol in roles:
        _sql(contenedor, base,
             f"do $$ begin if not exists (select 1 from pg_roles where rolname = "
             f"'{rol}') then create role {_q(rol)} nologin; end if; end $$", check=False)
    for m in miembros:
        grupo, miembro = m.split("|")
        _sql(contenedor, base, f"grant {_q(grupo)} to {_q(miembro)}", check=False)
    for e in extensiones:
        nombre, esquema = e.split("|")
        _sql(contenedor, base, f"create schema if not exists {_q(esquema)}", check=False)
        _sql(contenedor, base,
             f"create extension if not exists {_q(nombre)} schema {_q(esquema)}", check=False)


def copiar(leo_produccion: bool, ignorar_hora: bool) -> int:
    if not leo_produccion:
        print("Esto LEE la base de produccion. Repetilo con --leo-produccion.")
        return 2
    minuto = datetime.now().minute
    if minuto in FRANJA_PICO and not ignorar_hora:
        print(f"Son las :{minuto:02d}. Entre :05 y :22 corren el ciclo del Supervisor "
              "y la conciliacion en produccion: probar despues de las :23.")
        return 2

    cred = _leer_env(Path(credenciales()))
    faltan = [v for v in VARIABLES_DB if not cred.get(v)]
    if faltan:
        print(f"El archivo de credenciales no define {faltan}.")
        return 1
    if cred["DBHOST"] in ("db", "localhost", "127.0.0.1", CONTENEDOR_DB):
        print(f"DBHOST={cred['DBHOST']!r} en el archivo de credenciales: eso no es "
              "produccion. Nada que copiar.")
        return 1
    entorno = {**os.environ, **{v: cred[v] for v in VARIABLES_DB},
               "POSTGRES_PASSWORD": secrets.token_urlsafe(18)}

    paso("1", "base temporal en memoria (tmpfs: nada de esto llega a un disco)")
    correr(["docker", "rm", "-f", TEMPORAL], check=False)
    correr(["docker", "run", "-d", "--name", TEMPORAL,
            *[a for v in VARIABLES_DB for a in ("-e", v)],
            "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=copia",
            "--tmpfs", "/var/lib/postgresql/data:rw,size=4g",
            "-p", f"127.0.0.1:{PUERTO_TEMPORAL}:5432", IMAGEN_PG], env=entorno)
    for _ in range(60):
        if correr(["docker", "exec", TEMPORAL, "pg_isready", "-U", "postgres"],
                  check=False).returncode == 0:
            break
        time.sleep(1)
    time.sleep(3)
    print(f"  produccion: {cred['DBHOST']}:{cred['DBPORT']}/{cred['DBNAME']}")

    try:
        paso("2", "roles, membresias y extensiones de produccion (solo lectura)")
        roles, miembros, extensiones = _roles_del(TEMPORAL, "copia", de_produccion=True)
        print(f"  {len(roles)} roles, {len(miembros)} membresias, extensiones: "
              f"{', '.join(extensiones)}")
        _replicar_roles(TEMPORAL, "copia", roles, miembros, extensiones)

        paso("3", "pg_dump de produccion -> base temporal (puede tardar)")
        t0 = time.time()
        r = correr(["docker", "exec", TEMPORAL, "bash", "-c",
                    'PGPASSWORD="$DBPASSWORD" pg_dump -h "$DBHOST" -p "$DBPORT" '
                    '-U "$DBUSER" -d "$DBNAME" -Fc -n public -n asistente '
                    '--exclude-table-data=asistente.media --no-owner 2>/tmp/err_dump '
                    '| pg_restore -U postgres -d copia --no-owner 2>/tmp/err_restore; '
                    'echo "dump=${PIPESTATUS[0]}"; cat /tmp/err_dump; '
                    'grep -ci error /tmp/err_restore; grep -i error /tmp/err_restore | head -12; '
                    'rm -f /tmp/err_dump /tmp/err_restore'], check=False)
        salida = r.stdout.splitlines()
        print(f"  {time.time() - t0:.0f} s")
        for l in salida[:16]:
            print("   ", _sin_datos(l)[:160])
        if not salida or salida[0].strip() != "dump=0":
            print("pg_dump NO termino bien: no se sigue.")
            return 1
    except SystemExit:
        descartar()
        raise
    return retapar()


def _clave_temporal() -> str:
    r = correr(["docker", "exec", TEMPORAL, "printenv", "POSTGRES_PASSWORD"], check=False)
    if r.returncode != 0:
        raise SystemExit("No hay copia temporal viva. Correr 'copiar --leo-produccion'.")
    return r.stdout.strip()


def retapar() -> int:
    """Tapa, escanea y, si queda limpia, reemplaza la base local."""
    import psycopg

    env = env_local()
    paso("4", "tapar datos personales y apagar efectos (en memoria)")
    with psycopg.connect(host="127.0.0.1", port=PUERTO_TEMPORAL, dbname="copia",
                         user="postgres", password=_clave_temporal(),
                         autocommit=True) as con:
        informe = tapar(con)
        print(f"  {informe['filas']} filas tapadas en {informe['columnas']} columnas")
        if informe["sin_columna"]:
            print("  declaradas en TAPAR y ausentes:", ", ".join(informe["sin_columna"]))
        if informe["fallidas"]:
            print("  FALLARON:", ", ".join(informe["fallidas"]))
        paso("5", "escaneo de lo que quedo")
        quedan = residuos(con)
        sin_explicar = [(c, n) for c, n in quedan if c not in RESIDUO_EXPLICADO]
        for c, n in quedan:
            print(f"  {'EXPLICADO   ' if c in RESIDUO_EXPLICADO else 'SIN EXPLICAR'} {c}: {n} fila(s)")
        if sin_explicar or informe["fallidas"]:
            print("\nLA COPIA NO SE ENTREGA. La base local no se toco. La copia sigue en "
                  "memoria: ajustar las reglas y correr 'retapar', o 'descartar'.")
            return 1
        print("  limpio")

    paso("6", "reemplazar la base local")
    roles, miembros, extensiones = _roles_del(TEMPORAL, "copia", de_produccion=False)
    correr(compose("stop", *SERVICIOS_APP, ciclo=True), check=False)
    base = env["DBNAME"]
    _sql(CONTENEDOR_DB, "postgres", f"drop database if exists {_q(base)} with (force)")
    _sql(CONTENEDOR_DB, "postgres", f"create database {_q(base)}")
    _replicar_roles(CONTENEDOR_DB, base, roles, miembros, extensiones)
    volcado = subprocess.Popen(["docker", "exec", TEMPORAL, "pg_dump", "-U", "postgres",
                                "-Fc", "copia"], stdout=subprocess.PIPE)
    r = subprocess.run(["docker", "exec", "-i", CONTENEDOR_DB, "pg_restore", "-U",
                        "postgres", "-d", base, "--no-owner"], stdin=volcado.stdout,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    volcado.stdout.close()
    volcado.wait()
    errores = [l for l in r.stderr.splitlines() if "error" in l.lower()]
    print(f"  avisos de pg_restore: {len(errores)}")
    for l in errores[:8]:
        print("   ", _sin_datos(l)[:160])
    _roles_locales(env, base)
    descartar()
    return levantar(ciclo=False)


def descartar() -> int:
    paso("x", "borrando la copia temporal")
    correr(["docker", "rm", "-f", TEMPORAL], check=False)
    return 0


def _roles_locales(env: dict, base: str) -> None:
    """El modelo de roles de produccion, con las claves de ESTA maquina."""
    import psycopg

    with psycopg.connect(host="127.0.0.1", port=int(env.get("LOCAL_PUERTO_DB", 55440)),
                         dbname=base, user="postgres", password=env["LOCAL_PG_PASSWORD"],
                         autocommit=True) as c:
        def lit(s):
            return "'" + s.replace("'", "''") + "'"
        for rol, clave, extra in (("crm_user", env["DBPASSWORD"], " nobypassrls"),
                                  ("motor_user", env["MOTOR_DBPASSWORD"], " bypassrls"),
                                  ("crm_migrator", env["MIGRATOR_DBPASSWORD"], "")):
            existe = c.execute("select 1 from pg_roles where rolname = %s", (rol,)).fetchone()
            c.execute(f"{'alter' if existe else 'create'} role {rol} login{extra} "
                      f"password {lit(clave)}")
        if not c.execute("select 1 from pg_roles where rolname = 'crm_owner'").fetchone():
            c.execute("create role crm_owner nologin")
        c.execute("grant crm_owner to crm_migrator")
        c.execute(f"alter role crm_migrator in database {_q(base)} set role = crm_owner")
        c.execute("grant usage, create on schema public to crm_owner")
        for kind, nombre in c.execute(
                "select c.relkind, quote_ident(c.relname) from pg_class c "
                "join pg_namespace s on s.oid = c.relnamespace where s.nspname = 'public' "
                "and c.relkind in ('r','p','v','m') and pg_get_userbyid(c.relowner) = 'postgres'"
        ).fetchall():
            tipo = {"v": "view", "m": "materialized view"}.get(kind, "table")
            c.execute(f"alter {tipo} public.{nombre} owner to crm_owner")
        if c.execute("select 1 from pg_roles where rolname = 'app_backend'").fetchone():
            c.execute("grant app_backend to motor_user")
        for q in ("alter default privileges for role crm_owner in schema public grant "
                  "select, insert, update, delete on tables to crm_user",
                  "alter default privileges for role crm_owner in schema public grant "
                  "usage, select, update on sequences to crm_user"):
            c.execute(q)


# =============================================================================
#  verificar
# =============================================================================

def verificar() -> int:
    import psycopg

    malas = []

    def ok(cond, que):
        print(f"  [{'ok' if cond else 'FALLA'}] {que}")
        if not cond:
            malas.append(que)

    paso("v", "comprobaciones del entorno local")
    for svc, esperado in (("motor", {"SIN_EFECTOS_EXTERNOS": "1", "DBHOST": "db"}),
                          ("backend", {"DBHOST": "db", "FCM_CUENTA_DE_SERVICIO": "",
                                       "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"})):
        for var, valor in esperado.items():
            r = correr(["docker", "exec", f"{PROYECTO}-{svc}-1", "printenv", var], check=False)
            ok((r.stdout or "").strip() == valor, f"{svc}: {var}={valor!r}")
    env = env_local()
    with psycopg.connect(host="127.0.0.1", port=int(env.get("LOCAL_PUERTO_DB", 55440)),
                         dbname=env["DBNAME"], user="postgres",
                         password=env["LOCAL_PG_PASSWORD"], autocommit=True) as c:
        def uno(q):
            try:
                with c.transaction():
                    return c.execute(q).fetchone()[0]
            except psycopg.errors.UndefinedTable:
                return None
        ok(uno("select count(*) from asistente.tenant_secrets where nombre ilike 'whatsapp%'") in (0, None),
           "sin credenciales de WhatsApp en la base")
        ok(uno("select count(*) from public.campo_canal_de_avisos where activo") in (0, None),
           "ningun canal de avisos activo")
        ok(uno("select count(*) from public.campo_dispositivo_tecnico where activo") in (0, None),
           "ningun dispositivo de push activo")
        ok(uno("select count(*) from asistente.interruptor_autonomia where estado <> 'detenido'") in (0, None),
           "autonomia detenida")
        quedan = [(col, n) for col, n in residuos(c) if col not in RESIDUO_EXPLICADO]
        ok(not quedan, "sin telefonos ni correos de clientes sin explicar"
           + (f": {', '.join(col for col, _ in quedan)}" if quedan else ""))
    print("\n" + ("[OK] El entorno local no puede producir efectos afuera."
                  if not malas else f"[FALLA] {len(malas)} comprobacion(es)."))
    return 1 if malas else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="El entorno local igual a produccion.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("levantar")
    s.add_argument("--ciclo", action="store_true",
                   help="tambien celery-beat y motor-reloj (leen WispHub)")
    sub.add_parser("bajar")
    sub.add_parser("verificar")
    s = sub.add_parser("copiar")
    s.add_argument("--leo-produccion", action="store_true")
    s.add_argument("--ignorar-hora", action="store_true")
    sub.add_parser("retapar")
    sub.add_parser("descartar")
    a = p.parse_args(argv)
    if a.cmd == "levantar":
        return levantar(a.ciclo)
    if a.cmd == "bajar":
        return bajar()
    if a.cmd == "verificar":
        return verificar()
    if a.cmd == "retapar":
        return retapar()
    if a.cmd == "descartar":
        return descartar()
    return copiar(a.leo_produccion, a.ignorar_hora)


if __name__ == "__main__":
    raise SystemExit(main())
