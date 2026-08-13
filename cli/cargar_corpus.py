# -*- coding: utf-8 -*-
"""
================================================================================
 CARGA DEL CORPUS  -  vectoriza y sube los documentos de un tenant a Supabase
================================================================================

Cierra el entregable 4. nucleo/ingesta/docx.py fragmenta (ya probado: 126
fragmentos, 36 tablas intactas, 6 defectos reales detectados); este script
vectoriza cada fragmento con bge-m3 y lo escribe en asistente.document_chunks.

Que se carga y que no
----------------------
  vigente   -> se fragmenta, se vectoriza, se carga completo. Es lo unico
               que match_chunks() puede recuperar.
  obsoleto  -> se inserta solo la FILA de asistente.documents (codigo, version,
               hash, estado). NO se fragmenta ni se vectoriza: match_chunks()
               filtra por d.estado='vigente', asi que esos fragmentos nunca
               se recuperarian — vectorizarlos seria trabajo tirado. La fila
               sola ya cumple el proposito de auditoria: queda constancia de
               que esa version existio y fue superada.
  excluido  -> NI SIQUIERA se lee. Mismo criterio que cli/ingerir.py.

Versionado, nunca sobreescritura
---------------------------------
Si un documento VIGENTE cambio (detectado por hash del archivo), sus
fragmentos viejos se marcan vigente=false -nunca se borran- y se insertan los
nuevos. Sin esto, seria imposible reconstruir con que version del documento se
respondio algo hace tres meses.

Si el hash no cambio, el documento se salta. Re-vectorizar lo mismo no aporta
nada y cada fragmento es una llamada real al modelo de embeddings.

Conexion
--------
Mismo patron que cli/cargar_config.py: conexion directa con el usuario del
.env (ver nucleo/persistencia/conexion.py), sin cambiar a app_backend. Es una
herramienta de operacion (como una migracion), no el backend que sirve
peticiones — ese si debe usar app_backend siempre.

Uso
---
    py -3.13 cli/cargar_corpus.py rapilink
    py -3.13 cli/cargar_corpus.py rapilink --forzar   # ignora el hash, recarga todo
================================================================================
"""

from __future__ import annotations

import hashlib
from fnmatch import fnmatch
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "cli"))

import psycopg                                                 # noqa: E402
from dotenv import load_dotenv                                 # noqa: E402

from nucleo.config import cargar_config                        # noqa: E402
from nucleo.ingesta.docx import procesar                       # noqa: E402
from nucleo.persistencia.conexion import dsn                   # noqa: E402
from nucleo.recuperacion.embeddings import (                   # noqa: E402
    MODELO as MODELO_EMBEDDINGS, vectorizar as _vectorizar_openai)
from ingerir import clasificar, perfil_de                      # noqa: E402  (reutiliza lo ya construido)

load_dotenv(RAIZ / ".env", override=True)


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _roles_de_respaldo(cfg, ruta: Path) -> list[str] | None:
    """
    Los roles que el YAML declara para este archivo, cuando el documento no
    los trae adentro. Primer patron que coincide, en el orden del YAML.

    Es un respaldo, no la fuente: lo que manda siempre es la tabla de
    metadatos del .docx -- ver Corpus.roles_por_defecto en
    nucleo/config/schema.py para por que hace falta igual.
    """
    for patron, roles in (cfg.corpus.roles_por_defecto or {}).items():
        if fnmatch(ruta.name, patron):
            return list(roles) or None
    return None


def _roles_validos(cfg, roles_texto: str, ruta: Path) -> list[str] | None:
    """
    'soporte, facturacion' -> ['soporte', 'facturacion'], validado contra los
    roles reales del tenant -- un typo en la tabla de metadatos del documento
    no debe pasar en silencio y dejar el proceso invisible para todo el mundo
    sin que nadie se entere.

    None (columna NULL) si el documento no declara 'roles': fail-closed, ver
    supabase/03_documentos_roles.sql -- sin roles asignados, match_chunks no
    lo recupera para ningun rol hasta que alguien lo asigne a proposito.
    """
    if not roles_texto:
        return None
    nombres = [r.strip() for r in roles_texto.split(",") if r.strip()]
    desconocidos = [r for r in nombres if r not in cfg.roles]
    if desconocidos:
        raise SystemExit(
            f"{ruta.name}: declara rol(es) inexistente(s) en 'roles': "
            f"{', '.join(desconocidos)}. Roles del tenant: {', '.join(sorted(cfg.roles))}")
    return nombres or None


def _conectar():
    return psycopg.connect(dsn(), connect_timeout=40)


def _organizacion(cur, slug: str) -> str:
    """
    El slug se resuelve contra asistente.tenant_config, no contra el CRM: la
    tabla public.organization solo tiene 'name'. Quien establece ese vinculo es
    cli/cargar_config.py, asi que si falta aqui es que falta el paso anterior.
    """
    cur.execute("select organization_id from asistente.tenant_config where slug = %s",
                (slug,))
    fila = cur.fetchone()
    if not fila:
        raise SystemExit(
            f"'{slug}' no tiene configuracion cargada, asi que no se sabe a que "
            f"organizacion del CRM pertenece.\n"
            f"Cargarla primero:  py -3.13 cli/cargar_config.py tenants/{slug}.config.yaml")
    return fila[0]


def _cargar_obsoleto(cur, org_id: str, ruta: Path, hash_: str, cfg) -> bool:
    """Solo la fila de metadatos. Sin fragmentar, sin vectorizar."""
    doc = procesar(ruta)                      # solo para leer codigo/titulo/version
    roles = _roles_validos(cfg, doc.roles, ruta) or _roles_de_respaldo(cfg, ruta)
    cur.execute("""select id, hash from asistente.documents
                   where organization_id = %s and codigo = %s and version = %s""",
               (org_id, doc.codigo, doc.version))
    fila = cur.fetchone()
    if fila and fila[1] == hash_:
        return False                          # sin cambios
    if fila:
        cur.execute("""update asistente.documents
                       set titulo=%s, estado='obsoleto', hash=%s, roles_permitidos=%s
                       where id=%s""",
                    (doc.titulo, hash_, roles, fila[0]))
    else:
        cur.execute("""insert into asistente.documents
                       (organization_id, codigo, titulo, version, tipo, estado, hash,
                        roles_permitidos)
                       values (%s,%s,%s,%s,'guia_tecnica','obsoleto',%s,%s)""",
                    (org_id, doc.codigo, doc.titulo, doc.version, hash_, roles))
    return True


def cargar_tenant(slug: str, forzar: bool = False) -> None:
    carpeta = RAIZ / "corpus" / slug
    if not carpeta.is_dir():
        raise SystemExit(f"No existe {carpeta}")

    cfg = cargar_config(RAIZ / "tenants" / f"{slug}.config.yaml")
    perfil, tokens = perfil_de(slug)
    archivos = sorted(carpeta.glob("*.docx"))

    print(f"Tenant: {slug}   documentos: {len(archivos)}   modelo: {MODELO_EMBEDDINGS}\n")

    with _conectar() as con, con.cursor() as cur:
        org_id = _organizacion(cur, slug)
        con.commit()

        total_frag = total_saltados = total_obsoletos = 0
        t0 = time.monotonic()

        for ruta in archivos:
            estado = clasificar(ruta, cfg)
            if estado == "excluido":
                print(f"  [excluido] {ruta.name[:55]}")
                continue

            hash_ = _hash(ruta)

            if estado == "obsoleto":
                cambio = _cargar_obsoleto(cur, org_id, ruta, hash_, cfg)
                con.commit()
                total_obsoletos += 1
                print(f"  [obsoleto] {ruta.name[:55]}  "
                     f"{'cargado (solo metadatos)' if cambio else 'sin cambios'}")
                continue

            # --- vigente: fragmentar, vectorizar, cargar ---
            doc = procesar(ruta, perfil=perfil, max_tokens=tokens)
            roles = _roles_validos(cfg, doc.roles, ruta) or _roles_de_respaldo(cfg, ruta)

            cur.execute("""select id, hash from asistente.documents
                           where organization_id = %s and codigo = %s and version = %s""",
                       (org_id, doc.codigo, doc.version))
            fila = cur.fetchone()

            if fila and fila[1] == hash_ and not forzar:
                total_saltados += 1
                print(f"  [sin cambios] {ruta.name[:52]}  ({len(doc.fragmentos)} frag, se salta)")
                continue

            if fila:
                doc_id = fila[0]
                cur.execute("""update asistente.documents
                               set titulo=%s, estado='vigente', hash=%s, defectos=%s,
                                   roles_permitidos=%s
                               where id=%s""",
                            (doc.titulo, hash_, json.dumps(doc.defectos, ensure_ascii=False),
                             roles, doc_id))
                # Los fragmentos viejos quedan obsoletos, NUNCA se borran: es
                # lo que permite reconstruir con que version se respondio algo.
                cur.execute("""update asistente.document_chunks
                               set vigente=false where document_id=%s and vigente""",
                            (doc_id,))
            else:
                cur.execute("""insert into asistente.documents
                               (organization_id, codigo, titulo, version, tipo,
                                estado, hash, defectos, roles_permitidos)
                               values (%s,%s,%s,%s,'guia_tecnica','vigente',%s,%s,%s)
                               returning id""",
                            (org_id, doc.codigo, doc.titulo, doc.version,
                             hash_, json.dumps(doc.defectos, ensure_ascii=False), roles))
                doc_id = cur.fetchone()[0]

            n = 0
            for frag in doc.fragmentos:
                contextualizado = frag.contextualizar(doc)
                vector = _vectorizar_openai(contextualizado)
                cur.execute("""insert into asistente.document_chunks
                               (organization_id, document_id, orden, contenido,
                                contenido_contextualizado, embedding, metadata,
                                tokens, vigente)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,true)""",
                            (org_id, doc_id, frag.orden, frag.contenido,
                             contextualizado, str(vector),
                             json.dumps(frag.metadata, ensure_ascii=False),
                             len(contextualizado) // 4))
                n += 1
            con.commit()
            total_frag += n
            destino = f"roles: {', '.join(roles)}" if roles else "SIN ROL ASIGNADO -- no lo va a recuperar nadie"
            print(f"  [cargado] {ruta.name[:55]}  {n} fragmentos vectorizados  ({destino})")

        elapsed = time.monotonic() - t0

    print(f"\n{'='*66}")
    print(f"  {total_frag} fragmentos nuevos vectorizados y cargados")
    print(f"  {total_saltados} documentos vigentes sin cambios (se saltaron)")
    print(f"  {total_obsoletos} documentos obsoletos con metadatos actualizados")
    print(f"  tiempo: {elapsed:.1f}s")
    print(f"{'='*66}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("Uso: py -3.13 cli/cargar_corpus.py <slug> [--forzar]")
    cargar_tenant(args[0], forzar="--forzar" in sys.argv)
