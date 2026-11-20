-- =============================================================================
--  21. Diagnostico de recuperacion: distinguir "no hay documentos" de
--      "hay documentos y ninguno matcheo"
-- =============================================================================
--  Nace de un fallo real (20-21/08/2026) que costo perseguir la causa
--  equivocada. asistente.unanswered_queries acumulaba 103 preguntas distintas
--  con 'mejor_similitud' en NULL, y eso se leyo como "el umbral esta mal
--  calibrado" o "los embeddings no entienden como habla la gente".
--
--  Ninguna de las dos. La causa era que NINGUN documento del corpus tenia
--  asignados los roles de cara al cliente (cliente_final, ventas,
--  soporte_tecnico_cliente): asistente.match_chunks filtra por rol ANTES de
--  puntuar, asi que devolvia cero filas sin llegar a calcular una sola
--  similitud. Un problema de permisos disfrazado de problema semantico.
--
--  Con 'chunks_elegibles' eso deja de ser ambiguo para siempre:
--
--    chunks_elegibles = 0   ->  a este rol no se le asigno NINGUN documento.
--                              Es configuracion, no recuperacion. Se arregla
--                              en /manual asignando roles, no tocando el
--                              umbral ni el modelo.
--    chunks_elegibles > 0   ->  habia documentos visibles y ninguno supero el
--                              umbral. Recien ACA tiene sentido hablar de
--                              calibracion, vocabulario o busqueda hibrida.
--
--  Se cuenta SOLO cuando la busqueda no devolvio nada (ver
--  nucleo/recuperacion/busqueda.py): en el camino normal no se paga ninguna
--  consulta extra, y ese camino es el de un cliente esperando por WhatsApp.
-- =============================================================================

alter table asistente.unanswered_queries
  add column if not exists chunks_elegibles integer;

comment on column asistente.unanswered_queries.chunks_elegibles is
  'Cuantos fragmentos vigentes podia VER este rol al momento de la consulta, '
  'sin importar su similitud. 0 = no hay documentos asignados a ese rol '
  '(problema de configuracion). >0 = habia documentos y ninguno supero el '
  'umbral (problema de recuperacion). NULL = registrado antes de que esta '
  'columna existiera.';

-- =============================================================================
--  Y el modelo de embeddings de cada fragmento, que hasta ahora quedaba en
--  NULL o -- peor -- con la etiqueta de la config del tenant.
-- =============================================================================
--  document_chunks.modelo_embeddings existia desde el esquema original pero
--  cli/cargar_corpus.py nunca la escribia (todo lo cargado por CLI quedo en
--  NULL), y nucleo/ingesta/corpus.py estampaba 'rag.modelo_embeddings' de la
--  config -- que en rapilink decia 'bge-m3' mientras el codigo vectorizaba de
--  verdad con 'text-embedding-3-large'. Registrar una etiqueta equivocada es
--  peor que no registrar nada: hace parecer mezclado un corpus consistente.
--
--  Los dos caminos ya escriben el modelo REAL (nucleo/recuperacion/
--  embeddings.py:MODELO). Esto rellena lo que quedo atras.
--
--  El valor no se adivina: se comprobo midiendo. Los manuales tecnicos viejos
--  dieron 0.682 de similitud para una pregunta relevante y 0.202 para una
--  pregunta de control ajena al dominio -- el mismo comportamiento que los
--  documentos cargados el 21/08/2026 con OpenAI. Vectores de bge-m3
--  consultados con OpenAI habrian dado ruido, no eso.
-- =============================================================================

update asistente.document_chunks
   set modelo_embeddings = 'text-embedding-3-large'
 where modelo_embeddings is null
    or modelo_embeddings = 'bge-m3';
