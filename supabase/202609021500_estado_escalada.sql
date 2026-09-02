-- =============================================================================
--  ESTADO DEL TRASPASO A UNA PERSONA
-- =============================================================================
--  El 02/09/2026 el evaluador se cayo por timeout, nadie decidio escalar, y el
--  modelo le dijo al cliente que su caso ya estaba con un colaborador humano.
--  No habia caso, no habia ticket, y no quedaba rastro de nada: 'evaluar()'
--  devolvia None igual que cuando decide que NO corresponde escalar.
--
--  Estas dos columnas guardan lo que antes solo existia en un print: en que
--  termino el traspaso y por que. Ver nucleo/seguimiento/estado_escalada.py.
-- =============================================================================

alter table asistente.conversations
  add column if not exists estado_escalada text,
  add column if not exists escalada_detalle text;

comment on column asistente.conversations.estado_escalada is
  'ESCALAMIENTO_CONFIRMADO | ESCALAMIENTO_NO_CONFIRMADO | NO_DETERMINADO -- lo
   calcula el codigo. NO_DETERMINADO significa que el evaluador fallo, nunca
   que se haya escalado.';

comment on column asistente.conversations.escalada_detalle is
  'Por que quedo en ese estado: si el evaluador fallo, si el caso o el ticket
   se crearon, y con que motivo se intento.';
