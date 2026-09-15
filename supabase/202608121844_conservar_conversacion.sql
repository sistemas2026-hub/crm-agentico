-- =============================================================================
--  CONSERVAR  -  sacar una conversacion de la purga, a mano y a proposito
-- =============================================================================
--
--  Por que existe, si ya habia una forma
--  -------------------------------------
--  La purga por retencion (nucleo/persistencia/db.py::purgar_conversaciones)
--  ya exceptuaba las conversaciones con alguna respuesta marcada como ejemplo
--  valido. Eso alcanzaba para no destruir el manual, pero se presto a usarse
--  como "guardar esto": marcar el ejemplo era la unica manera de salvar una
--  conversacion de la purga.
--
--  Son dos intenciones distintas y montarlas en el mismo boton rompe las dos:
--
--    marcar como ejemplo  =  "esta respuesta del asistente fue BUENA para el
--                             caso X". Obliga a elegir un caso, y la
--                             conversacion pasa a alimentar /manual como
--                             material del que se redactan procedimientos.
--
--    conservar            =  "no borres esto todavia". Un reclamo, un
--                             incidente, algo que puede terminar en disputa.
--                             Justo lo que NO hay que copiar como ejemplo.
--
--  Sin esta separacion, conservar un reclamo lo publicaba en el manual como
--  respuesta a imitar, y quien despues escribiera los procedimientos se
--  encontraba con casos que nadie eligio por buenos.
--
--  POR QUE UNA COLUMNA Y NO UNA TABLA
--  ----------------------------------
--  Es un atributo de la conversacion, uno por fila, sin historia propia: no
--  hay nada que una tabla aparte agregue mas que un join en la consulta de la
--  bandeja. Agregar una columna nullable en Postgres 11+ no reescribe la
--  tabla, asi que tampoco cuesta nada aplicarla con datos ya cargados.
-- =============================================================================

alter table asistente.conversations
  add column if not exists conservar boolean not null default false;

-- Por que se conserva. Sin esto, dentro de seis meses nadie sabe si la marca
-- sigue teniendo sentido y no hay forma de decidir si se puede soltar.
alter table asistente.conversations
  add column if not exists conservar_motivo text;

alter table asistente.conversations
  add column if not exists conservar_por text;

comment on column asistente.conversations.conservar is
  'Excluye la conversacion de la purga por retencion. Distinto de tener un '
  'ejemplo marcado: eso dice "fue una buena respuesta", esto dice "no la '
  'borres todavia".';

-- Parcial, no total: solo interesa localizar las conservadas, que son pocas.
-- Un indice sobre toda la columna seria casi todo 'false' y no ahorraria nada.
create index if not exists conversations_conservadas_idx
  on asistente.conversations (organization_id)
  where conservar;
