-- =============================================================================
--  04) LIMPIEZA DE LA AUDIENCIA DUPLICADA + MODELO DE EMBEDDINGS
-- =============================================================================
--
-- Contexto (11/08/2026)
-- ---------------------
-- Dos personas resolvieron en paralelo el mismo problema -- que documento puede
-- recuperar cada audiencia -- con disenos distintos, y ambos llegaron a la base:
--
--   documents.visible_cliente_final  booleano, colaborador vs cliente_final
--   documents.roles_permitidos       text[], N roles por documento
--
-- Se conserva 'roles_permitidos': es estrictamente mas expresivo (permite
-- "tecnica ve este documento y facturacion no", que el booleano no puede
-- representar) y su valor viaja DENTRO del .docx, en la tabla de metadatos, en
-- vez de depender de una lista de patrones de nombre de archivo en el YAML.
--
-- Con los dos disenos aplicados quedaron ademas DOS sobrecargas de
-- match_chunks() conviviendo, una terminada en 'p_solo_publico boolean' y otra
-- en 'p_rol text'. Una llamada posicional podria caer en cualquiera de las dos.
-- Aqui se elimina la que sobra.
--
-- Lo unico que se rescata del diseno descartado es la columna de abajo, que es
-- ortogonal a la audiencia y resuelve otro problema.
-- =============================================================================

-- --- se va la version binaria de la audiencia ------------------------------
drop function if exists asistente.match_chunks(uuid, vector, integer, real, jsonb, boolean);

alter table asistente.documents
  drop column if exists visible_cliente_final;

-- --- se queda: con que modelo se vectorizo cada fragmento -------------------
-- Dos vectores solo son comparables si los genero el mismo modelo. Un corpus
-- vectorizado a medias con dos modelos distintos NO da error: simplemente
-- devuelve fragmentos peores, y nadie lo nota hasta que alguien dice que "el
-- asistente ya no responde bien". Esta columna no lo previene, lo hace visible:
--
--   select distinct modelo_embeddings from asistente.document_chunks;
--
-- Una sola fila = un solo espacio vectorial. Nullable a proposito: lo cargado
-- antes de que esto existiera no tiene forma honesta de deducirse.
alter table asistente.document_chunks
  add column if not exists modelo_embeddings text;

comment on column asistente.document_chunks.modelo_embeddings is
  'Modelo que genero el embedding (ej. bge-m3). NULL = cargado antes de que se '
  'registrara. Sirve para detectar un corpus vectorizado con mas de un modelo, '
  'que degrada la busqueda sin dar ningun error.';

grant execute on all functions in schema asistente to app_backend;
