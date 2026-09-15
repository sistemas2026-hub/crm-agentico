-- =============================================================================
--  18. La conversacion guarda de QUE es, no solo si escalo
-- =============================================================================
--  Ya se clasificaba: 'escalamiento.evaluar()' (nucleo/seguimiento/
--  escalamiento.py) le pide al modelo, EN CADA TURNO, a cual de los casos
--  del tenant ('manual.casos': internet_lento, sin_senal_tv, consulta_saldo,
--  ...) corresponde la conversacion. Es un enum cerrado, no texto libre: el
--  modelo no puede inventar una categoria fuera de la lista.
--
--  Pero ese valor se usaba para UNA sola cosa -- decidir si el caso tiene
--  agendamiento automatico habilitado -- y despues se tiraba. La bandeja de
--  conversaciones no tenia con que decir "esta es de TV y esta de facturacion"
--  sin que alguien la abriera y la leyera entera.
--
--  Ojo con la columna que ya existia: 'etiqueta' es la taxonomia GRUESA
--  ('conversaciones.etiquetas': soporte_tecnico, facturacion, comercial,
--  queja) y ademas solo se escribe al escalar, asi que una conversacion que
--  el asistente resolvio solo se quedaba sin nada. Esta es la fina, y se
--  escribe siempre. Son dos cosas distintas y por eso son dos columnas:
--  "soporte_tecnico" no distingue una falla de television de un internet
--  lento, que es justo lo que hay que separar para medir.
--
--  Sin valor por defecto ni NOT NULL: una conversacion recien abierta
--  todavia no tiene de que ser -- el cliente dijo "hola" y nada mas. NULL
--  significa "todavia sin clasificar", que es un estado real y no un dato
--  faltante.
-- =============================================================================

alter table asistente.conversations
    add column if not exists caso_manual text;

comment on column asistente.conversations.caso_manual is
  'A cual de los casos declarados en la config del tenant (manual.casos)
   corresponde esta conversacion. Lo elige el modelo en cada turno, acotado
   por enum -- ver nucleo/seguimiento/escalamiento.py. NULL = todavia sin
   clasificar. Distinta de ''etiqueta'', que es la taxonomia gruesa y solo
   se escribe al escalar.';

-- Filtrar la bandeja por tipo de caso es la consulta que justifica esta
-- columna; sin indice, cada filtro recorre toda la tabla de la organizacion.
-- Parcial: las conversaciones sin clasificar no se buscan por este campo.
create index if not exists conversations_caso_manual_idx
    on asistente.conversations (organization_id, caso_manual)
    where caso_manual is not null;
