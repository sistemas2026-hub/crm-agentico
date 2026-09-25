-- =============================================================================
--  Corpus por agente: a que rol(es) aplica cada documento
-- =============================================================================
--
--  Hasta ahora el corpus era todo-o-nada por tenant: cualquier documento
--  cargado lo podia recuperar cualquier rol con RAG activo. No habia forma de
--  decir "este proceso es solo para facturacion".
--
--  FAIL-CLOSED a proposito, mismo criterio que el resto del proyecto (ver
--  nucleo/config/schema.py, "una herramienta permitida sin lista blanca de
--  campos no devolveria nada"): un documento sin roles_permitidos asignado no
--  lo recupera NINGUN rol, no todos. Quien carga el documento tiene que
--  asignarlo a proposito -- ver nucleo/ingesta/docx.py, se lee del mismo
--  campo de metadatos del documento que ya declara 'codigo'/'version'/'fecha'.

alter table asistente.documents
  add column if not exists roles_permitidos text[];

comment on column asistente.documents.roles_permitidos is
  'Nombres de rol (los mismos de tenants/<slug>.config.yaml, roles.*) que '
  'pueden recuperar este documento por RAG. NULL o vacio = ningun rol lo ve.';

create or replace function asistente.match_chunks(
  p_org             uuid,
  p_query_embedding vector(1024),
  p_match_count     integer default 8,
  p_umbral          real    default 0.0,
  p_filtros         jsonb   default '{}'::jsonb,
  p_rol             text    default null
)
returns table (
  chunk_id     uuid,
  document_id  uuid,
  codigo       text,
  titulo       text,
  version      text,
  contenido    text,
  metadata     jsonb,
  similitud    real
)
language sql stable
as $$
  select c.id, c.document_id, d.codigo, d.titulo, d.version,
         c.contenido, c.metadata,
         (1 - (c.embedding <=> p_query_embedding))::real as similitud
  from asistente.document_chunks c
  join asistente.documents d on d.id = c.document_id
  where c.organization_id = p_org
    and c.vigente
    and d.estado = 'vigente'
    and (p_filtros = '{}'::jsonb or c.metadata @> p_filtros)
    and (1 - (c.embedding <=> p_query_embedding)) >= p_umbral
    and d.roles_permitidos is not null
    and p_rol = any(d.roles_permitidos)
  order by c.embedding <=> p_query_embedding
  limit p_match_count;
$$;
