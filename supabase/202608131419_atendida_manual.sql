-- =============================================================================
--  ATENDIDA MANUAL  -  marcar "ya lo tome" sin tener que escribirle al cliente
-- =============================================================================
--
--  Por que existe
--  ---------------
--  'atendida' (nucleo/persistencia/db.py::ultima_actividad) hoy es 100%
--  CALCULADA: exists(mensaje con rol='humano'). Una conversacion escalada
--  solo deja de pedir atencion cuando alguien le responde DESDE el chat.
--
--  Eso no cubre el caso real de un colaborador que resuelve el caso por
--  telefono, en persona, o desde otro canal, y solo quiere sacarla de "Sin
--  atender" sin mandarle un mensaje falso al cliente por el chat. Sin esta
--  columna, la unica forma de lograrlo era escribir igual (aunque no hiciera
--  falta) solo para que el calculo la contara como atendida.
--
--  Como conviven las dos fuentes
--  ------------------------------
--  ultima_actividad() pasa a calcular:
--      atendida = existe mensaje humano OR atendida_manual
--  Ninguna reemplaza a la otra: responder de verdad sigue marcando atendida
--  igual que siempre (sin tocar esta columna), y esto agrega el camino
--  manual para cuando no hace falta (o no corresponde) responder por ahi.
--
--  POR QUE UNA COLUMNA Y NO UNA TABLA
--  Mismo motivo que 'conservar' (ver 10_conservar_conversacion.sql): es un
--  atributo de la conversacion, uno por fila, sin historia propia.
-- =============================================================================

alter table asistente.conversations
  add column if not exists atendida_manual boolean not null default false;

-- Quien la marco. Sin esto, "por que esta atendida si nadie le respondio" no
-- tiene respuesta dentro de un mes.
alter table asistente.conversations
  add column if not exists atendida_por text;

comment on column asistente.conversations.atendida_manual is
  'Un colaborador marco el caso como resuelto sin responder por el chat '
  '(telefono, en persona, otro canal). Se combina con OR junto al calculo '
  'existente (exists mensaje rol=humano) -- ver ultima_actividad().';
