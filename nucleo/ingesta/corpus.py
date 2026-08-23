# -*- coding: utf-8 -*-
"""
================================================================================
 INGESTA AL CORPUS  -  del documento fragmentado a las filas de la base
================================================================================

Por que existe
--------------
Esta logica vivia solo dentro de 'cli/cargar_corpus.py', mezclada con recorrer
un directorio e imprimir en consola. Mientras cargar documentos fuera tarea de
un desarrollador con el repo clonado, alcanzaba. Deja de alcanzar cuando la
empresa sube un documento desde la interfaz del CRM: ahi el mismo trabajo lo
hace un endpoint HTTP, y duplicarlo garantizaria que los dos caminos se
separen con el tiempo.

Aqui queda solo lo que ambos comparten: dado un documento YA fragmentado,
escribirlo con su versionado. Recorrer carpetas, validar la tabla de roles del
.docx y decidir que archivos mirar sigue siendo del CLI.

RECIBE EL CURSOR, NO LO ABRE  (no es un detalle)
------------------------------------------------
La conexion es una decision de seguridad y no le corresponde a este modulo:

  - El CLI se conecta como el usuario del .env ('postgres', con BYPASSRLS)
    porque es una herramienta de operacion, como una migracion.
  - Un endpoint que sirve peticiones debe usar nucleo/persistencia/db.py::
    sesion(), que baja a 'app_backend' y deja que las politicas de aislamiento
    por tenant se evaluen de verdad.

Si este modulo abriera su propia conexion impondria una de las dos a los dos
llamadores, y la que sobra es justo la peligrosa.

VERSIONADO: NUNCA SE BORRA
--------------------------
Si un documento cambio (se detecta por hash del archivo), sus fragmentos
viejos se marcan 'vigente=false' y se insertan los nuevos. Sin eso seria
imposible reconstruir con que version del documento se respondio algo hace
tres meses.
================================================================================
"""

from __future__ import annotations

import json


class ErrorIngesta(Exception):
    """El documento no se pudo escribir en el corpus."""


def perfil_desde_config(config):
    """
    Traduce el perfil documental declarado por el tenant al que usa el
    fragmentador. Devuelve (PerfilDocumento, tokens_objetivo).

    Vivia solo en cli/ingerir.py::perfil_de(), que recibe un slug y relee el
    YAML del disco. El motor ya tiene la configuracion cargada (y en
    produccion la fuente de verdad es la base, no el archivo), asi que aqui
    se recibe la config y no se vuelve a leer nada.
    """
    from nucleo.ingesta.docx import PerfilDocumento

    p = config.corpus.perfil_documento
    tokens = (config.corpus.tipos_documento[0].tamano_objetivo_tokens
              if config.corpus.tipos_documento else 500)
    return PerfilDocumento(
        marcas_callout=tuple(p.marcas_callout),
        encabezados_pie=tuple(p.encabezados_pie),
        campos_metadatos=tuple(p.campos_metadatos),
        titulo_un_nivel_en_tabla=p.titulo_un_nivel_en_tabla,
        exigir_multinivel_sin_estilo=p.exigir_multinivel_sin_estilo,
        max_largo_titulo=p.max_largo_titulo,
        defectos_a_reportar=tuple(p.defectos_a_reportar),
        anotar_imagenes=p.anotar_imagenes,
    ), tokens


def roles_validos(config, roles_texto: str | None) -> list[str] | None:
    """
    'soporte, facturacion' -> ['soporte', 'facturacion'], validado contra los
    roles reales del tenant. Un typo no puede pasar en silencio y dejar el
    documento invisible para todo el mundo sin que nadie se entere.

    None si no se declara ninguno: fail-closed (ver
    supabase/03_documentos_roles.sql) -- sin roles asignados, match_chunks no
    lo recupera para nadie hasta que alguien lo asigne a proposito.

    Levanta ValueError con los nombres desconocidos; quien llama decide si eso
    es un SystemExit (CLI) o un 400 (endpoint).
    """
    if not roles_texto:
        return None
    nombres = [r.strip() for r in str(roles_texto).split(",") if r.strip()]
    desconocidos = [r for r in nombres if r not in config.roles]
    if desconocidos:
        raise ValueError(
            f"rol(es) inexistente(s): {', '.join(desconocidos)}. "
            f"Roles del tenant: {', '.join(sorted(config.roles))}")
    return nombres or None


def modelo_real() -> str:
    """
    El modelo con el que de verdad se vectoriza, leido de la unica fuente que
    lo decide (nucleo/recuperacion/embeddings.py).

    Existe porque 'rag.modelo_embeddings' de la config NO manda: embeddings.py
    fija un solo proveedor de plataforma. Estampar en
    document_chunks.modelo_embeddings lo que dice la config -- que es lo que
    se hacia hasta el 21/08/2026 -- registra una mentira cuando las dos cosas
    no coinciden, y es peor que no registrar nada: un corpus consistente
    queda etiquetado como mezclado, o al reves.

    Verificado ese dia: la config de rapilink declaraba 'bge-m3' mientras
    embeddings.py usaba 'text-embedding-3-large'. Los vectores eran todos de
    OpenAI (comprobado midiendo similitudes reales), asi que la etiqueta era
    lo unico incorrecto.
    """
    from nucleo.recuperacion.embeddings import MODELO
    return MODELO


def vectorizar(texto: str, modelo: str | None = None) -> list[float]:
    """Un fragmento -> un vector.

    'modelo' se acepta por compatibilidad con los llamadores viejos pero se
    IGNORA: con que se vectoriza lo decide embeddings.py, no quien llama. Ver
    modelo_real() arriba.
    """
    from nucleo.recuperacion.embeddings import vectorizar as _vectorizar_openai
    return _vectorizar_openai(texto)


def _fila(cur, org_id: str, codigo: str, version: str):
    """(id, hash) del documento, o (None, None). Tolera tuplas y dict_row: el
    CLI usa el cursor por defecto y el motor uno de diccionarios."""
    cur.execute(
        """select id, hash from asistente.documents
           where organization_id = %s and codigo = %s and version = %s""",
        (org_id, codigo, version))
    f = cur.fetchone()
    if f is None:
        return None, None
    return (f["id"], f["hash"]) if isinstance(f, dict) else (f[0], f[1])


def ingerir(cur, org_id: str, doc, hash_: str, *,
            modelo_embeddings: str,
            roles_permitidos: list[str] | None = None,
            tipo: str = "guia_tecnica",
            storage_path: str | None = None,
            forzar: bool = False,
            estado: str = "vigente") -> dict:
    """
    Escribe un documento con sus fragmentos vectorizados.

    'doc' es lo que devuelve nucleo/ingesta/docx.py::procesar(). 'hash_' es el
    sha256 del archivo original: es lo que decide si hubo cambios.

    'estado' decide si el asistente puede usarlo YA o si primero lo tiene que
    aprobar una persona (ver supabase/22_aprobacion_documentos.sql):

      'vigente'    el default, y lo que usa cli/cargar_corpus.py. Ese CLI es
                   una herramienta de operacion que exige credenciales de
                   base -- quien lo corre ya decidio.
      'pendiente'  lo que usa la subida desde la interfaz. Se vectoriza igual
                   pero match_chunks no lo recupera hasta que alguien lo
                   apruebe. Es la diferencia entre subir un archivo y
                   publicarlo: una guia escrita para un tecnico en campo,
                   asignada por error a un rol de cliente, produce
                   instrucciones peligrosas sin que salte ningun error.

    No hace commit -- la transaccion la maneja quien abrio el cursor.
    """
    doc_id, hash_guardado = _fila(cur, org_id, doc.codigo, doc.version)

    if doc_id and hash_guardado == hash_ and not forzar:
        return {"accion": "sin_cambios", "document_id": str(doc_id),
                "codigo": doc.codigo, "titulo": doc.titulo, "version": doc.version,
                "fragmentos": 0, "defectos": doc.defectos,
                "roles_permitidos": roles_permitidos}

    defectos = json.dumps(doc.defectos, ensure_ascii=False)

    if doc_id:
        # Reemplazar el contenido de un documento ya aprobado lo devuelve a
        # 'pendiente' si asi lo pide quien sube: aprobar una version no
        # aprueba las siguientes. Se limpia el rastro de la aprobacion
        # anterior, que ya no corresponde a este contenido.
        cur.execute(
            """update asistente.documents
               set titulo=%s, estado=%s, hash=%s, defectos=%s,
                   roles_permitidos=%s, storage_path=coalesce(%s, storage_path),
                   aprobado_por = case when %s = 'pendiente' then null
                                       else aprobado_por end,
                   aprobado_en  = case when %s = 'pendiente' then null
                                       else aprobado_en end
               where id=%s""",
            (doc.titulo, estado, hash_, defectos, roles_permitidos,
             storage_path, estado, estado, doc_id))
        # Los fragmentos viejos quedan obsoletos, NUNCA se borran.
        cur.execute(
            """update asistente.document_chunks
               set vigente=false where document_id=%s and vigente""",
            (doc_id,))
        accion = "actualizado"
    else:
        cur.execute(
            """insert into asistente.documents
                 (organization_id, codigo, titulo, version, tipo, estado, hash,
                  defectos, roles_permitidos, storage_path)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               returning id""",
            (org_id, doc.codigo, doc.titulo, doc.version, tipo, estado, hash_,
             defectos, roles_permitidos, storage_path))
        f = cur.fetchone()
        doc_id = f["id"] if isinstance(f, dict) else f[0]
        accion = "creado"

    # Lo que se REGISTRA es el modelo con el que de verdad se vectoriza, no
    # el que declare la config del tenant -- ver modelo_real() arriba.
    modelo = modelo_real()

    n = 0
    for frag in doc.fragmentos:
        contextualizado = frag.contextualizar(doc)
        vector = vectorizar(contextualizado)
        cur.execute(
            """insert into asistente.document_chunks
                 (organization_id, document_id, orden, contenido,
                  contenido_contextualizado, embedding, metadata, tokens,
                  modelo_embeddings, vigente)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
            (org_id, doc_id, frag.orden, frag.contenido, contextualizado,
             str(vector), json.dumps(frag.metadata, ensure_ascii=False),
             len(contextualizado) // 4, modelo))
        n += 1

    return {"accion": accion, "document_id": str(doc_id),
            "codigo": doc.codigo, "titulo": doc.titulo, "version": doc.version,
            "fragmentos": n, "defectos": doc.defectos,
            "roles_permitidos": roles_permitidos,
            # Para que quien sube sepa si ya quedo en uso o falta aprobarlo:
            # sin esto, la pantalla no puede distinguir "listo" de "cargado
            # pero invisible", que es justo la diferencia que importa.
            "estado": estado}


def actualizar_roles(cur, org_id: str, document_id: str,
                     roles_permitidos: list[str] | None) -> bool:
    """
    Cambia a quien se le puede recuperar un documento YA cargado, sin
    re-vectorizar. Antes de esto, corregir un typo en la tabla de roles del
    .docx o en 'roles_por_defecto' del YAML exigia volver a correr la
    ingesta completa -- esto solo toca la fila de asistente.documents.

    None (sin roles marcados) es el mismo fail-closed que un documento recien
    creado sin tabla de roles: no lo recupera NADIE hasta que alguien lo
    asigne a proposito -- nunca "todos lo ven" por omision.

    Filtra por organization_id ademas del id, como retirar().
    """
    cur.execute(
        """update asistente.documents set roles_permitidos=%s
           where id=%s and organization_id=%s""",
        (roles_permitidos, document_id, org_id))
    return cur.rowcount > 0


def aprobar(cur, org_id: str, document_id: str,
            aprobado_por: str | None = None) -> bool:
    """
    Habilita un documento para que el asistente pueda recuperarlo: pasa de
    'pendiente' a 'vigente' y deja el rastro de quien lo aprobo.

    La garantia de que un documento pendiente NO se use no vive aca sino en
    asistente.match_chunks, que filtra por estado='vigente' en SQL (ver
    supabase/22). Esta funcion solo abre la puerta; no es la puerta.

    Solo actua sobre documentos en 'pendiente': aprobar uno ya vigente no
    tiene sentido, y aprobar uno 'obsoleto' lo resucitaria sin que nadie
    haya pedido eso -- para volver a poner en circulacion algo retirado hay
    que subirlo de nuevo, que es lo que deja constancia de la decision.
    """
    cur.execute(
        """update asistente.documents
              set estado='vigente', aprobado_por=%s, aprobado_en=now()
            where id=%s and organization_id=%s and estado='pendiente'""",
        (aprobado_por, document_id, org_id))
    return cur.rowcount > 0


def retirar(cur, org_id: str, document_id: str) -> bool:
    """
    Saca un documento del corpus sin borrarlo: pasa a 'obsoleto', que es lo
    que match_chunks() excluye. Deshacer tiene que ser posible -- marcar un
    documento por error no puede ser una puerta de una sola direccion, y
    borrar romperia la trazabilidad de con que version se respondio antes.

    Filtra por organization_id ademas del id: dos capas, como el resto del
    proyecto.
    """
    cur.execute(
        """update asistente.documents set estado='obsoleto'
           where id=%s and organization_id=%s""",
        (document_id, org_id))
    return cur.rowcount > 0
