-- El ticket que la conversacion abrio en el sistema operativo del ISP.
--
-- Hasta ahora ese numero solo existia como TEXTO adentro de la descripcion del
-- caso del CRM ("Ticket operativo #91288"), que sirve para que una persona lo
-- lea y para nada mas: no se puede consultar, y sobre todo no se puede
-- responder ni cerrar desde el codigo sin volver a parsear un parrafo.
--
-- Se guarda como texto y no como entero a proposito: es el identificador de un
-- sistema externo, y el proximo ISP puede numerar con letras. Lo mismo que ya
-- se hace con caso_id.
alter table asistente.conversations
  add column if not exists ticket_operativo text;

comment on column asistente.conversations.ticket_operativo is
  'Identificador del ticket en el sistema operativo del ISP (WispHub en el
   primer despliegue), abierto al escalar. Permite responderlo y cerrarlo
   desde el codigo -- ver nucleo/seguimiento/operativo.py.';
