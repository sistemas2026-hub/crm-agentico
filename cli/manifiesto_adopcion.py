# -*- coding: utf-8 -*-
"""
================================================================================
 EL MANIFIESTO DE ADOPCION  --  que prueba que una migracion ya esta aplicada
================================================================================

    # 1. generar, contra una base de REFERENCIA construida desde cero por el
    #    ledger (nunca contra la base que se quiere adoptar):
    py -3.13 cli/manifiesto_adopcion.py --generar

    # 2. adoptar una base existente (solo lectura; no escribe):
    py -3.13 cli/migrar_asistente.py --adoptar

    # 3. escribir las filas que pasaron TODAS sus verificaciones:
    py -3.13 cli/migrar_asistente.py --adoptar --escribir-baseline

    # 4. aceptacion humana individual de UNA migracion, con motivo:
    py -3.13 cli/migrar_asistente.py --adoptar --escribir-baseline \\
        --aceptar <archivo.sql> --motivo "..." --autorizado-por "<persona o acta>"

Por que existe
--------------
La primera version de la adopcion miraba si EXISTIAN las tablas, funciones,
columnas e indices que un archivo declaraba. Eso no prueba que el archivo este
aplicado. Con ese criterio se habian dado por demostrados 39 de 40 archivos.

Que verifica, y contra que
--------------------------
Cada sentencia del archivo se clasifica y se traduce a una comprobacion de
CATALOGO sobre el objeto que toca: columnas (tipo, not null, default,
identity) y TODAS las constraints; flags de RLS; pg_get_indexdef con predicado;
politicas con roles, comando, USING y WITH CHECK; ACL exactas; md5 de
pg_get_functiondef, dueño, SECURITY DEFINER, SET y comentario; triggers;
comentarios; schema y extension.

Desde el 15/09/2026 tambien la ACL de las SECUENCIAS de un schema
('acl_secuencias', por 'grant ... on all sequences in schema') y los DEFAULT
PRIVILEGES de un rol en un schema ('default_acl', por 'alter default privileges
for role R in schema S ...', con todos sus tipos en una sola foto). Antes esas
sentencias caian como desconocidas y mandaban a revision humana un archivo que
se podia verificar. Solo se reconoce la forma con un rol y un schema
explicitos; ver tests/test_manifiesto_acl_secuencias_default.py.

El ESPERADO es el estado final de una referencia construida desde cero con
exactamente esos archivos.

UPDATE/INSERT/DELETE -> migracion_de_datos_no_repetible. DO -> requiere revision
humana. Sentencia no reconocida -> requiere revision humana. Nunca automaticas.

La huella del servidor, como compuerta
--------------------------------------
Las definiciones que devuelve pg_get_*def pueden cambiar entre versiones
mayores de PostgreSQL, y una extension en otra version u otro schema cambia
tipos, operadores y firmas. Comparar catalogos entre servidores distintos no
dice nada confiable. Por eso el manifiesto guarda la huella de la referencia
--version mayor y, por extension, version y schema-- y la adopcion la compara
ANTES de verificar nada y ANTES de crear el ledger. Si no coincide: exit 7, sin
una sola fila y sin una sola comprobacion. Una extension de mas en la base
adoptada no bloquea; una que falta o difiere, si.

Cuando escribe
--------------
Toda escritura (baseline o aceptacion humana) ocurre dentro de la seccion
serializada del migrador: lock -> huella -> esquema del ledger -> plan ->
verificacion -> INSERT, en ese orden y sin salir del lock. La verificacion que
cuenta es la que se hace DENTRO: un dry-run previo no autoriza nada.

La evidencia de cada fila
-------------------------
Toda fila 'baseline' o 'baseline_humano' se escribe con 'evidencia' (jsonb,
paso 0002 del esquema del ledger): sha256 y git blob del manifiesto usado, su
referencia, la version exacta del servidor y sus extensiones medidas dentro del
lock, cuantas comprobaciones pasaron, los efectos que quedaron sin comprobar, el
rol de la sesion y, si se dio, --autorizado-por. Esa identidad la DECLARA quien
corre el comando: la herramienta no la autentica. Con --aceptar es obligatoria.
Formato: supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md.
================================================================================
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import psycopg                                                    # noqa: E402

from cli import migrar_asistente as mig                           # noqa: E402

MANIFIESTO = RAIZ / "supabase" / "ledger" / "manifiesto_adopcion.json"
VERSION = 1
FORMATO_EVIDENCIA = 1

AUTOMATICA = "verificable_automaticamente"
HUMANA = "requiere_revision_humana"
DATOS = "migracion_de_datos_no_repetible"


# =============================================================================
#  partir el SQL en sentencias
# =============================================================================

_DOLAR = re.compile(r"\$[A-Za-z_]*\$")


def dividir(texto: str) -> list[str]:
    """
    Sentencias de nivel superior, sin comentarios.

    Respeta cadenas '...' (con '' escapado), identificadores "...", cuerpos
    $tag$...$tag$ y comentarios -- y /* */. Un ';' dentro de cualquiera de ellos
    no parte la sentencia.
    """
    sentencias: list[str] = []
    buf: list[str] = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if texto.startswith("--", i):
            j = texto.find("\n", i)
            i = n if j == -1 else j
            continue
        if texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if texto[j] == "'":
                    if j + 1 < n and texto[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            buf.append(texto[i:j + 1])
            i = j + 1
            continue
        if c == '"':
            j = texto.find('"', i + 1)
            j = n - 1 if j == -1 else j
            buf.append(texto[i:j + 1])
            i = j + 1
            continue
        if c == "$":
            m = _DOLAR.match(texto, i)
            if m:
                tag = m.group(0)
                j = texto.find(tag, i + len(tag))
                j = n if j == -1 else j + len(tag)
                buf.append(texto[i:j])
                i = j
                continue
        if c == ";":
            s = "".join(buf).strip()
            if s:
                sentencias.append(s)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    s = "".join(buf).strip()
    if s:
        sentencias.append(s)
    return sentencias


# =============================================================================
#  clasificar cada sentencia
# =============================================================================

_ID = r'(?:"[^"]+"|[a-z_][a-z0-9_$]*)'
_QID = rf"(?:{_ID}\.)?{_ID}"


def _partes(q: str, defecto: str = "public") -> tuple[str, str]:
    trozos = [t.strip().strip('"') for t in re.split(r'\.(?=(?:[^"]*"[^"]*")*[^"]*$)', q)]
    if len(trozos) == 1:
        return defecto, trozos[0]
    return trozos[-2], trozos[-1]


def _plano(sentencia: str) -> str:
    return " ".join(sentencia.split()).lower()


def clasificar(sentencia: str) -> list[tuple]:
    """
    Devuelve las CLAVES de comprobacion que esa sentencia exige. Una clave es
    una tupla ('tipo', ...). Los tipos 'datos', 'dinamico' y 'desconocido' no
    tienen comprobacion de catalogo: marcan la migracion como no automatica.
    """
    s = _plano(sentencia)

    m = re.match(rf"create (?:unlogged )?table (?:if not exists )?({_QID})", s)
    if m:
        return [("tabla",) + _partes(m.group(1))]

    m = re.match(rf"alter table (?:if exists )?(?:only )?({_QID}) (.*)$", s)
    if m:
        t, resto = _partes(m.group(1)), m.group(2)
        if re.search(r"\brename to\b", resto):
            return [("desconocido", s[:80])]
        if re.search(r"\b(enable|disable|force|no force) row level security\b", resto):
            return [("rls",) + t]
        return [("tabla",) + t]

    m = re.match(rf"create (?:unique )?index (?:concurrently )?(?:if not exists )?"
                 rf"({_ID}) on (?:only )?({_QID})", s)
    if m:
        esquema, _ = _partes(m.group(2))
        return [("indice", esquema, m.group(1).strip('"'))]

    m = re.match(rf"drop index (?:concurrently )?(?:if exists )?({_QID})", s)
    if m:
        return [("indice",) + _partes(m.group(1))]

    m = re.match(rf"(?:create|alter|drop) policy (?:if exists )?({_ID}) on ({_QID})", s)
    if m:
        return [("politicas",) + _partes(m.group(2))]

    m = re.match(rf"(?:create|drop) (?:constraint )?trigger (?:if exists )?({_ID}) "
                 rf"(?:.*? )?on ({_QID})", s)
    if m:
        return [("triggers",) + _partes(m.group(2))]

    m = re.match(rf"create (?:or replace )?function ({_QID})\s*\(", s)
    if m:
        return [("funcion",) + _partes(m.group(1))]
    m = re.match(rf"(?:drop|alter) function (?:if exists )?({_QID})", s)
    if m:
        return [("funcion",) + _partes(m.group(1))]

    m = re.match(rf"create (?:or replace )?view ({_QID})", s)
    if m:
        return [("vista",) + _partes(m.group(1))]

    m = re.match(rf"create schema (?:if not exists )?({_ID})", s)
    if m:
        return [("schema", m.group(1).strip('"'))]

    m = re.match(rf"create extension (?:if not exists )?({_ID})", s)
    if m:
        return [("extension", m.group(1).strip('"'))]

    m = re.match(r"comment on (table|column|function|schema|view|index) (.+?) is ", s)
    if m:
        clase, obj = m.group(1), m.group(2)
        if clase in ("table", "view"):
            return [("comentario_tabla",) + _partes(obj)]
        if clase == "column":
            *tabla, col = [p.strip('"') for p in obj.split(".")]
            esquema, t = (tabla[0], tabla[1]) if len(tabla) == 2 else ("public", tabla[0])
            return [("comentario_columna", esquema, t, col)]
        if clase == "function":
            return [("funcion",) + _partes(obj.split("(")[0])]
        if clase == "schema":
            return [("schema", obj.strip('"'))]
        if clase == "index":
            return [("indice",) + _partes(obj)]

    # Default privileges: solo la forma con UN rol y UN schema explicitos, sobre
    # tablas, secuencias o funciones. Cualquier otra (sin FOR ROLE, sin IN SCHEMA,
    # listas, TYPES, SCHEMAS) sigue siendo 'desconocido'. Una sola clave por par
    # rol+schema: la foto trae todos los tipos juntos.
    m = re.match(rf"alter default privileges for (?:role|user) ({_ID}) in schema ({_ID}) "
                 rf"(?:grant|revoke) .*? on (?:tables|sequences|functions) (?:to|from) ", s)
    if m:
        return [("default_acl", m.group(1).strip('"'), m.group(2).strip('"'))]

    m = re.match(r"(?:grant|revoke) .*? on (.+?) (?:to|from) ", s)
    if m:
        obj = m.group(1)
        mm = re.match(rf"all functions in schema ({_ID})$", obj)
        if mm:
            return [("acl_funciones", mm.group(1).strip('"'))]
        mm = re.match(rf"all sequences in schema ({_ID})$", obj)
        if mm:
            return [("acl_secuencias", mm.group(1).strip('"'))]
        mm = re.match(rf"all tables in schema ({_ID})$", obj)
        if mm:
            return [("acl_tablas", mm.group(1).strip('"'))]
        mm = re.match(rf"schema ({_ID})$", obj)
        if mm:
            return [("schema", mm.group(1).strip('"'))]
        mm = re.match(rf"function ({_QID})\s*\(", obj)
        if mm:
            return [("funcion",) + _partes(mm.group(1))]
        mm = re.match(rf"(?:table )?({_QID}(?:\s*,\s*{_QID})*)$", obj)
        if mm:
            return [("acl_tabla",) + _partes(t.strip())
                    for t in mm.group(1).split(",")]
        return [("desconocido", s[:80])]

    m = re.match(rf"(update|insert into|delete from) (?:only )?({_QID})", s)
    if m:
        return [("datos",) + _partes(m.group(2))]

    if re.match(r"do\b", s):
        return [("dinamico",)]

    return [("desconocido", s[:80])]


def estado_de(claves: list[tuple]) -> tuple[str, str]:
    tipos = {c[0] for c in claves}
    if "datos" in tipos:
        objetos = sorted({".".join(c[1:]) for c in claves if c[0] == "datos"})
        return DATOS, (f"transforma datos en {objetos}: el catalogo no registra "
                       f"que transformacion se hizo; hace falta una invariante "
                       f"escrita por una persona")
    if "dinamico" in tipos:
        return HUMANA, "contiene un bloque DO: SQL dinamico que no se puede leer sin ejecutarlo"
    if "desconocido" in tipos:
        raras = [c[1] for c in claves if c[0] == "desconocido"]
        return HUMANA, f"sentencias que el clasificador no cubre: {raras}"
    return AUTOMATICA, "todas sus sentencias tienen comprobacion de catalogo"


# =============================================================================
#  fotos de catalogo
# =============================================================================

def _md5(v):
    return None if v is None else hashlib.md5(v.encode("utf-8")).hexdigest()


def _acl(con, consulta, params):
    fila = con.execute(consulta, params).fetchone()
    return None if fila is None or fila[0] is None else sorted(fila[0])


def foto(con, clave: tuple):
    tipo = clave[0]

    if tipo in ("tabla", "rls", "acl_tabla", "comentario_tabla"):
        _, esquema, nombre = clave
        oid = con.execute("select to_regclass(format('%%I.%%I', %s::text, %s::text))::oid",
                          (esquema, nombre)).fetchone()[0]
        if oid is None:
            return {"existe": False}
        if tipo == "rls":
            f = con.execute("select relrowsecurity, relforcerowsecurity from pg_class "
                            "where oid=%s", (oid,)).fetchone()
            return {"existe": True, "rls": f[0], "force": f[1]}
        if tipo == "acl_tabla":
            return {"existe": True,
                    "dueño": con.execute("select pg_get_userbyid(relowner) from pg_class "
                                         "where oid=%s", (oid,)).fetchone()[0],
                    "acl": _acl(con, "select relacl::text[] from pg_class where oid=%s",
                                (oid,))}
        if tipo == "comentario_tabla":
            return {"existe": True, "comentario": _md5(con.execute(
                "select obj_description(%s, 'pg_class')", (oid,)).fetchone()[0])}
        columnas = {
            f[0]: [f[1], f[2], f[3], f[4], f[5]]
            for f in con.execute(
                "select a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
                "       pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated "
                "  from pg_attribute a left join pg_attrdef d "
                "    on d.adrelid = a.attrelid and d.adnum = a.attnum "
                " where a.attrelid = %s and a.attnum > 0 and not a.attisdropped",
                (oid,)).fetchall()}
        constraints = {
            f[0]: f[1] for f in con.execute(
                "select conname, pg_get_constraintdef(oid, true) from pg_constraint "
                "where conrelid = %s", (oid,)).fetchall()}
        dueño = con.execute("select pg_get_userbyid(relowner) from pg_class where oid=%s",
                            (oid,)).fetchone()[0]
        return {"existe": True, "dueño": dueño, "columnas": columnas,
                "constraints": constraints}

    if tipo == "comentario_columna":
        _, esquema, tabla, col = clave
        f = con.execute(
            "select col_description(c.oid, a.attnum) from pg_class c "
            "join pg_namespace n on n.oid=c.relnamespace "
            "join pg_attribute a on a.attrelid=c.oid "
            "where n.nspname=%s and c.relname=%s and a.attname=%s and not a.attisdropped",
            (esquema, tabla, col)).fetchone()
        return {"existe": f is not None, "comentario": _md5(f[0]) if f else None}

    if tipo == "indice":
        _, esquema, nombre = clave
        f = con.execute("select pg_get_indexdef(to_regclass(format('%%I.%%I', %s::text, %s::text)))",
                        (esquema, nombre)).fetchone()
        return {"definicion": f[0] if f else None}

    if tipo == "politicas":
        _, esquema, tabla = clave
        return {f[0]: [f[1], sorted(f[2] or []), f[3], f[4], f[5]]
                for f in con.execute(
                    "select policyname, permissive, roles::text[], cmd, qual, with_check "
                    "from pg_policies where schemaname=%s and tablename=%s",
                    (esquema, tabla)).fetchall()}

    if tipo == "triggers":
        _, esquema, tabla = clave
        return {f[0]: f[1] for f in con.execute(
            "select t.tgname, pg_get_triggerdef(t.oid, true) from pg_trigger t "
            "join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname=%s and c.relname=%s and not t.tgisinternal",
            (esquema, tabla)).fetchall()}

    if tipo == "funcion":
        _, esquema, nombre = clave
        return {f[0]: {"definicion": _md5(f[1]), "dueño": f[2], "secdef": f[3],
                       "config": sorted(f[4] or []),
                       "acl": sorted(f[5]) if f[5] is not None else None,
                       "comentario": _md5(f[6])}
                for f in con.execute(
                    "select p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')', "
                    "       pg_get_functiondef(p.oid), pg_get_userbyid(p.proowner), "
                    "       p.prosecdef, p.proconfig, p.proacl::text[], "
                    "       obj_description(p.oid, 'pg_proc') "
                    "  from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
                    " where n.nspname=%s and p.proname=%s and p.prokind='f'",
                    (esquema, nombre)).fetchall()}

    if tipo == "acl_funciones":
        _, esquema = clave
        return {f[0]: (sorted(f[1]) if f[1] is not None else None)
                for f in con.execute(
                    "select p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')', "
                    "       p.proacl::text[] from pg_proc p join pg_namespace n "
                    "on n.oid=p.pronamespace where n.nspname=%s", (esquema,)).fetchall()}

    if tipo == "acl_tablas":
        _, esquema = clave
        return {f[0]: (sorted(f[1]) if f[1] is not None else None)
                for f in con.execute(
                    "select c.relname, c.relacl::text[] from pg_class c "
                    "join pg_namespace n on n.oid=c.relnamespace "
                    "where n.nspname=%s and c.relkind in ('r','p','v')",
                    (esquema,)).fetchall()}

    if tipo == "acl_secuencias":
        # Solo relkind='S'. Lista ordenada por nombre en Python (no depende de
        # collation); ACL ordenada; None = sin grants explicitos; [] = no hay
        # secuencias en el schema (o el schema no existe).
        _, esquema = clave
        filas = con.execute(
            "select c.relname, pg_get_userbyid(c.relowner), c.relacl::text[] from pg_class c "
            "join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname=%s and c.relkind='S'", (esquema,)).fetchall()
        return sorted(({"schema": esquema, "nombre": f[0], "dueño": f[1],
                        "acl": sorted(f[2]) if f[2] is not None else None} for f in filas),
                      key=lambda x: x["nombre"])

    if tipo == "default_acl":
        # pg_default_acl de ESE rol en ESE schema, todos los tipos juntos
        # (r tablas, S secuencias, f funciones, T tipos, n schemas). [] = sin filas,
        # tambien si el rol no existe.
        _, rol, esquema = clave
        filas = con.execute(
            "select d.defaclobjtype::text, d.defaclacl::text[] from pg_default_acl d "
            "join pg_namespace n on n.oid=d.defaclnamespace join pg_roles r on r.oid=d.defaclrole "
            "where r.rolname=%s and n.nspname=%s", (rol, esquema)).fetchall()
        return sorted(({"rol": rol, "schema": esquema, "tipo": f[0], "acl": sorted(f[1] or [])} for f in filas),
                      key=lambda x: x["tipo"])

    if tipo == "vista":
        _, esquema, nombre = clave
        f = con.execute("select pg_get_viewdef(to_regclass(format('%%I.%%I', %s::text, %s::text)))",
                        (esquema, nombre)).fetchone()
        return {"definicion": _md5(f[0]) if f else None}

    if tipo == "schema":
        _, nombre = clave
        f = con.execute("select pg_get_userbyid(nspowner), nspacl::text[] from pg_namespace "
                        "where nspname=%s", (nombre,)).fetchone()
        return {"existe": f is not None, "dueño": f[0] if f else None,
                "acl": (sorted(f[1]) if f and f[1] is not None else None)}

    if tipo == "extension":
        _, nombre = clave
        f = con.execute("select n.nspname from pg_extension e join pg_namespace n "
                        "on n.oid=e.extnamespace where e.extname=%s", (nombre,)).fetchone()
        return {"existe": f is not None, "schema": f[0] if f else None}

    raise ValueError(f"tipo de comprobacion sin foto: {tipo}")


def _normal(v):
    """Lo que devuelve la base, llevado a la forma que queda en el JSON."""
    return json.loads(json.dumps(v, sort_keys=True, default=str))


def diferencias(esperado, actual, ruta="") -> list[str]:
    if isinstance(esperado, dict) and isinstance(actual, dict):
        salida = []
        for k in sorted(set(esperado) | set(actual)):
            if k not in actual:
                salida.append(f"{ruta}{k}: falta")
            elif k not in esperado:
                salida.append(f"{ruta}{k}: sobra")
            else:
                salida.extend(diferencias(esperado[k], actual[k], f"{ruta}{k}."))
        return salida
    if esperado != actual:
        return [f"{ruta.rstrip('.')}: esperado {str(esperado)[:80]} / hay {str(actual)[:80]}"]
    return []


# =============================================================================
#  generar
# =============================================================================

def generar(con, carpeta: Path | None = None, descripcion: str = "") -> dict:
    """
    El manifiesto, sacado de una base de REFERENCIA construida desde cero por el
    ledger con EXACTAMENTE los archivos de la carpeta. Solo lectura.
    """
    if not mig.ledger_existe(con):
        raise SystemExit("[manifiesto] la base de referencia no tiene ledger: no fue "
                         "construida por cli/migrar_asistente.py.")
    pendientes, discrepancias, invalidos, anotadas = mig.plan(con, carpeta)
    malas = [a for a, f in anotadas.items() if f["origen"] != "aplicada"]
    en_carpeta = {r.name for r in mig.archivos(carpeta)}
    sobrantes = sorted(set(anotadas) - en_carpeta)
    if pendientes or discrepancias or invalidos or malas or sobrantes or not anotadas:
        raise SystemExit(
            "[manifiesto] la base de referencia tiene que estar construida "
            "desde cero por el ledger con EXACTAMENTE los archivos de la "
            "carpeta: todo aplicado, nada adoptado, ningun hash distinto, nada "
            f"de mas. pendientes={len(pendientes)} "
            f"discrepancias={len(discrepancias)} invalidos={len(invalidos)} "
            f"no_aplicadas={malas} anotadas_sin_archivo={sobrantes}")

    version_pg = con.execute("show server_version").fetchone()[0]
    migraciones = {}
    for ruta in mig.archivos(carpeta):
        texto, sha = mig.leer_migracion(ruta)
        claves: list[tuple] = []
        tipos = collections.Counter()
        for sentencia in dividir(texto):
            for c in clasificar(sentencia):
                tipos[c[0]] += 1
                if c not in claves:
                    claves.append(c)
        estado, motivo = estado_de(claves)
        verificables = [c for c in claves
                        if c[0] not in ("datos", "dinamico", "desconocido")]
        migraciones[ruta.name] = {
            "sha256": sha,
            "estado": estado,
            "motivo": motivo,
            "sentencias": dict(sorted(tipos.items())),
            "efectos_sin_comprobacion": [list(c) for c in claves
                                         if c[0] in ("datos", "dinamico", "desconocido")],
            "verificaciones": [{"clave": list(c), "esperado": _normal(foto(con, c))}
                               for c in verificables],
        }
    return {
        "version": VERSION,
        "algoritmo_checksum": mig.ALGORITMO,
        "referencia": {"postgres": version_pg, "descripcion": descripcion,
                       "huella": mig.huella_servidor(con)},
        "migraciones": migraciones,
    }


def _serializar(manifiesto: dict) -> bytes:
    return (json.dumps(manifiesto, sort_keys=True, indent=1, ensure_ascii=False)
            + "\n").encode("utf-8")


def guardar(manifiesto: dict, ruta: Path = MANIFIESTO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(_serializar(manifiesto))


def identidad(canon: bytes, calculado_sobre: str) -> dict:
    """
    Con que manifiesto se decidio una adopcion. 'sha256' sobre los bytes
    canonicos (mismo contrato que las migraciones); 'git_blob' es el id que git
    le da a esos bytes, para encontrar el commit con
    'git log --all --find-object=<git_blob>'.
    """
    return {"sha256": hashlib.sha256(canon).hexdigest(),
            "git_blob": hashlib.sha1(b"blob %d\0" % len(canon) + canon).hexdigest(),
            "calculado_sobre": calculado_sobre}


def leer(ruta: Path = MANIFIESTO) -> tuple[dict, dict]:
    """(manifiesto, identidad) de UNA lectura: lo que se usa es lo que se identifica."""
    canon = mig.bytes_canonicos(ruta.read_bytes(), ruta.name)
    m = json.loads(canon.decode("utf-8"))
    if m.get("version") != VERSION:
        raise SystemExit(f"[manifiesto] version {m.get('version')} no soportada "
                         f"(esta herramienta entiende la {VERSION}).")
    if m.get("algoritmo_checksum") != mig.ALGORITMO:
        raise SystemExit(f"[manifiesto] generado con otro contrato de hash: "
                         f"{m.get('algoritmo_checksum')}")
    return m, identidad(canon, "archivo")


def cargar(ruta: Path = MANIFIESTO) -> dict:
    return leer(ruta)[0]


# =============================================================================
#  verificar y adoptar
# =============================================================================

def verificar_migracion(con, entrada: dict) -> list[str]:
    fallas: list[str] = []
    for v in entrada["verificaciones"]:
        clave = tuple(v["clave"])
        actual = _normal(foto(con, clave))
        for d in diferencias(v["esperado"], actual):
            fallas.append(f"{'/'.join(clave)} :: {d}")
    return fallas


def _huella_compatible(con, m) -> bool:
    """La compuerta: antes de cualquier verificacion y antes de crear el ledger."""
    esperada = m.get("referencia", {}).get("huella")
    if not esperada:
        malas = ["el manifiesto no trae huella de servidor: fue generado por una "
                 "version anterior de esta herramienta y hay que regenerarlo"]
    else:
        malas = mig.comparar_huella(esperada, mig.huella_servidor(con))
    if malas:
        print("[adoptar] LA HUELLA DEL SERVIDOR NO ES LA DEL MANIFIESTO. No se "
              "verifica ni se escribe nada:")
        for linea in malas:
            print(f"    {linea}")
        print("  Comparar definiciones de catalogo entre versiones mayores o con "
              "extensiones distintas no es confiable. Hay que generar el manifiesto "
              "contra una referencia con la misma huella que esta base.")
        return False
    return True


def _preparar(con, m, carpeta):
    """Plan filtrado al conjunto del manifiesto. (codigo_de_salida | None, pendientes)"""
    pendientes, discrepancias, invalidos, _anotadas = mig.plan(con, carpeta)
    if invalidos or discrepancias:
        print("[adoptar] hay archivos no canonicos o aplicados que cambiaron; "
              "resolver antes de adoptar.")
        return mig.SALIDA_CHECKSUM, None
    # El manifiesto esta atado a un CONJUNTO de migraciones.
    del_manifiesto = set(m["migraciones"])
    actuales = {r.name for r in mig.archivos(carpeta)}
    faltan = sorted(del_manifiesto - actuales)
    if faltan:
        print(f"[adoptar] el manifiesto referencia archivos que no estan en el "
              f"repo: {faltan}. No se adopta.")
        return mig.SALIDA_FALLO, None
    ultima = max(del_manifiesto)
    extras = sorted(actuales - del_manifiesto)
    intercaladas = [e for e in extras if e < ultima]
    if intercaladas:
        print(f"[adoptar] hay archivos fuera del manifiesto que ordenan antes de "
              f"su ultimo archivo ({ultima}): {intercaladas}. No hay referencia "
              f"para ese orden. No se adopta.")
        return mig.SALIDA_FALLO, None
    if extras:
        print(f"[adoptar] {len(extras)} archivo(s) posteriores al manifiesto quedan "
              f"FUERA de la adopcion y pendientes para --aplicar: {extras}")
    return None, [p for p in pendientes if p[0].name in del_manifiesto]


def _clasificar(con, m, pendientes):
    pasan, fallan, no_auto = [], [], []
    print(f"[adoptar] {len(pendientes)} migracion(es) sin anotar. Manifiesto "
          f"v{m['version']}, referencia PostgreSQL {m['referencia']['postgres']}.\n")
    for ruta, _texto, sha in pendientes:
        e = m["migraciones"].get(ruta.name)
        if e["sha256"] != sha:
            no_auto.append((ruta, "manifiesto_desactualizado",
                            "el archivo cambio desde que se genero el manifiesto"))
            print(f"  [MANIFIESTO VIEJO]   {ruta.name}")
            continue
        if e["estado"] != AUTOMATICA:
            no_auto.append((ruta, e["estado"], e["motivo"]))
            print(f"  [{e['estado'].upper()}] {ruta.name}")
            print(f"      {e['motivo']}")
            continue
        fallas = verificar_migracion(con, e)
        if fallas:
            fallan.append((ruta, fallas))
            print(f"  [NO EQUIVALENTE]     {ruta.name}  ({len(fallas)} diferencia(s))")
            for f in fallas[:6]:
                print(f"      {f}")
        else:
            pasan.append((ruta, sha, len(e["verificaciones"])))
            print(f"  [VERIFICADA]         {ruta.name}  ({len(e['verificaciones'])} comprobaciones)")
    print(f"\n  verificadas automaticamente : {len(pasan)}")
    print(f"  no equivalentes             : {len(fallan)}")
    print(f"  sin decision automatica     : {len(no_auto)}")
    return pasan, fallan, no_auto


def _constructor_de_evidencia(con, m, ident, autorizado_por):
    """
    Mide servidor y sesion UNA vez, dentro del lock y despues de la compuerta de
    huella, y devuelve la funcion que arma la evidencia de cada fila.
    """
    h = mig.huella_servidor(con)
    entorno = {"server_version": con.execute("show server_version").fetchone()[0],
               "server_version_num": h["server_version_num"],
               "extensiones": h["extensiones"]}
    # Sin application_name: lleva el hostname, que puede ser el nombre de una
    # persona y no hace falta para reconstruir la decision.
    rol = con.execute("select session_user::text").fetchone()[0]
    pid = os.getpid()
    autorizacion = None if autorizado_por is None else {
        "declarada_por": autorizado_por.strip(),
        "naturaleza": "declarada por quien corrio el comando; la herramienta no la autentica"}

    def evidencia(entrada: dict) -> str:
        n = len(entrada["verificaciones"])
        return json.dumps({
            "formato": FORMATO_EVIDENCIA,
            "manifiesto": {**ident, "formato": m["version"], "referencia": m["referencia"]},
            "entorno": entorno,
            "verificacion": {
                "estado_en_manifiesto": entrada["estado"],
                "comprobaciones_totales": n,
                # Solo se escribe una fila cuando TODAS coinciden: la adopcion
                # automatica y la aceptacion humana se niegan con una sola falla.
                "comprobaciones_coincidentes": n,
                "efectos_sin_comprobacion": entrada["efectos_sin_comprobacion"]},
            "autorizacion": autorizacion,
            "operacion": {"rol_sesion": rol, "pid": pid},
        }, sort_keys=True, ensure_ascii=False)

    return evidencia


def _aceptar(con, m, pendientes, archivo, motivo, escribir, evidencia) -> int:
    fila = next(((r, t, s) for r, t, s in pendientes if r.name == archivo), None)
    if fila is None:
        print(f"[adoptar] '{archivo}' no esta pendiente.")
        return mig.SALIDA_FALLO
    _ruta, _texto, sha = fila
    e = m["migraciones"].get(archivo)
    if e is None or e["sha256"] != sha:
        print(f"[adoptar] '{archivo}' no esta en el manifiesto o cambio desde que se "
              f"genero: no se acepta a ciegas.")
        return mig.SALIDA_FALLO
    # Las partes estaticas SI tienen que coincidir. La aceptacion humana cubre
    # lo que el catalogo no puede ver, no lo que si ve y esta mal.
    fallas = verificar_migracion(con, e)
    if fallas:
        print(f"[adoptar] '{archivo}': sus partes verificables NO coinciden con la "
              f"referencia. No se acepta:")
        for f in fallas[:6]:
            print(f"    {f}")
        return mig.SALIDA_FALLO
    quien = con.execute("select session_user").fetchone()[0]
    print(f"[adoptar] '{archivo}' [{e['estado']}]")
    print(f"    efectos sin comprobacion: {e['efectos_sin_comprobacion']}")
    print(f"    partes verificables: {len(e['verificaciones'])} coinciden")
    if not escribir:
        print("[adoptar] solo lectura: no se escribio nada.")
        return mig.SALIDA_OK
    with con.transaction():
        con.execute(
            "insert into asistente.migraciones_aplicadas "
            "(archivo, sha256, algoritmo, duro_ms, origen, nota, evidencia) "
            "values (%s,%s,%s,0,'baseline_humano',%s,%s::jsonb)",
            (archivo, sha, mig.ALGORITMO,
             f"ACEPTACION HUMANA por {quien} [{e['estado']}]: {motivo.strip()}",
             evidencia(e)))
    print(f"[adoptar] '{archivo}' anotada como baseline_humano por {quien}; "
          f"autorizacion declarada: {json.loads(evidencia(e))['autorizacion']['declarada_por']}.")
    return mig.SALIDA_OK


def _cuerpo(con, m, escribir, aceptar, motivo, carpeta, ident=None,
            autorizado_por=None) -> int:
    """Lo mismo en solo lectura que dentro de la seccion; solo cambia el final."""
    if not _huella_compatible(con, m):
        return mig.SALIDA_HUELLA
    evidencia = None
    if escribir:
        mig.asegurar_ledger(con)
        evidencia = _constructor_de_evidencia(con, m, ident, autorizado_por)
    codigo, pendientes = _preparar(con, m, carpeta)
    if codigo is not None:
        return codigo
    if not pendientes:
        print("[adoptar] no hay nada que adoptar: el ledger ya esta completo.")
        return mig.SALIDA_OK
    if aceptar is not None:
        return _aceptar(con, m, pendientes, aceptar, motivo, escribir, evidencia)

    pasan, fallan, no_auto = _clasificar(con, m, pendientes)
    if fallan:
        print("\n[adoptar] la base NO es equivalente a una construida desde cero en "
              "las migraciones marcadas. No se escribe nada hasta resolverlo.")
        return mig.SALIDA_FALLO
    if not escribir:
        print("\n[adoptar] SOLO LECTURA: no se escribio nada. Lo que vale es la "
              "verificacion que se repite dentro del lock al escribir.")
        if no_auto:
            print(f"[adoptar] ADOPCION INCOMPLETA: {len(no_auto)} migracion(es) "
                  f"necesitan decision humana antes de que el ledger quede completo.")
        return mig.SALIDA_OK
    with con.transaction():
        for ruta, sha, n in pasan:
            con.execute(
                "insert into asistente.migraciones_aplicadas "
                "(archivo, sha256, algoritmo, duro_ms, origen, nota, evidencia) "
                "values (%s,%s,%s,0,'baseline',%s,%s::jsonb)",
                (ruta.name, sha, mig.ALGORITMO,
                 f"adoptada: {n} comprobaciones de catalogo contra manifiesto "
                 f"v{m['version']} (referencia PostgreSQL {m['referencia']['postgres']})",
                 evidencia(m["migraciones"][ruta.name])))
    print(f"\n[adoptar] {len(pasan)} migracion(es) anotadas como baseline.")
    if no_auto:
        print(f"[adoptar] ADOPCION INCOMPLETA: quedan {len(no_auto)} sin anotar:")
        for ruta, est, _mot in no_auto:
            print(f"    {ruta.name}  [{est}]")
        print("  '--aplicar' se va a NEGAR a correr mientras existan: son "
              "migraciones anteriores a otras ya anotadas.")
    return mig.SALIDA_OK


def autorizacion_valida(texto: str | None) -> bool:
    if texto is None:
        return False
    t = texto.strip()
    return 3 <= len(t) <= 200 and all(ord(c) >= 32 and ord(c) != 127 for c in t)


def adoptar(con, escribir: bool, espera: float, aceptar: str | None = None,
            motivo: str | None = None, carpeta: Path | None = None,
            manifiesto: dict | None = None, autorizado_por: str | None = None) -> int:
    if aceptar is not None and (not motivo or len(motivo.strip()) < 20):
        print("[adoptar] --aceptar exige --motivo de al menos 20 caracteres: queda "
              "escrito en el ledger como la razon de dar por aplicada una migracion "
              "que no se pudo verificar sola.")
        return mig.SALIDA_CHECKSUM
    if aceptar is not None and autorizado_por is None:
        print("[adoptar] --aceptar exige --autorizado-por: la persona, o la referencia "
              "del acta o ticket, que autorizo dar por aplicada una migracion sin poder "
              "verificarla entera. Queda en la evidencia como identidad DECLARADA por "
              "quien corre el comando: la herramienta no la autentica.")
        return mig.SALIDA_CHECKSUM
    if autorizado_por is not None and not autorizacion_valida(autorizado_por):
        print("[adoptar] --autorizado-por tiene que tener entre 3 y 200 caracteres, "
              "sin saltos de linea ni caracteres de control.")
        return mig.SALIDA_CHECKSUM
    if manifiesto is None:
        m, ident = leer()
    else:
        m, ident = manifiesto, identidad(_serializar(manifiesto), "serializacion")
    if not escribir:
        return _cuerpo(con, m, False, aceptar, motivo, carpeta)
    try:
        with mig.seccion_serializada(con, espera):
            return _cuerpo(con, m, True, aceptar, motivo, carpeta, ident, autorizado_por)
    except mig.LockNoObtenido as e:
        return mig.informar_lock(e, "No se verifico ni se escribio nada.")
    except mig.LedgerNoActualizable as e:
        return mig.informar_ledger(e, "No se verifico nada ni se escribio ninguna fila de adopcion.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--generar", action="store_true", required=True)
    p.add_argument("--salida", default=str(MANIFIESTO))
    p.add_argument("--descripcion", default="")
    a = p.parse_args(argv)
    con = mig.conectar()
    try:
        man = generar(con, descripcion=a.descripcion)
    finally:
        con.close()
    guardar(man, Path(a.salida))
    cuenta = collections.Counter(e["estado"] for e in man["migraciones"].values())
    print(f"[manifiesto] {len(man['migraciones'])} migraciones -> {a.salida}")
    for est, n in sorted(cuenta.items()):
        print(f"    {est}: {n}")
    print(f"    huella: PostgreSQL {man['referencia']['huella']['major']}, "
          f"extensiones {sorted(man['referencia']['huella']['extensiones'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
