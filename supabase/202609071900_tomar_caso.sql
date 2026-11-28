-- =============================================================================
--  TOMAR UN CASO NO ES HABERLO RESUELTO
-- =============================================================================
--  El 07/09/2026 se agrego la pestaña "En atencion" a la bandeja y se calculo
--  reusando 'atendida_manual'. Estaba mal, y no por el nombre.
--
--  'atendida_manual' significa una cosa concreta y esta escrita en el
--  comentario de su propia columna: "un colaborador marco el caso como
--  RESUELTO sin responder por el chat (telefono, en persona, otro canal)".
--
--  Dos reglas del motor dependen de eso, y las dos hacen daño si la marca
--  significa "estoy trabajando en esto":
--
--    nucleo/persistencia/db.py:625   un "ok, gracias" del cliente CIERRA el
--                                    caso, pero solo si alguien ya lo
--                                    atendio. Ese chequeo existe por un
--                                    incidente real: se cerro una
--                                    conversacion con el cambio de clave sin
--                                    hacer, porque un "ok" a nadie no
--                                    confirma nada.
--
--    nucleo/persistencia/db.py:799   el barrido por plazo vencido cierra
--                                    SOLO lo que alguien ya atendio. Una que
--                                    nadie toco no esta esperando al
--                                    cliente: esta esperando al equipo, y
--                                    cerrarla enterraria trabajo sin hacer
--                                    con cara de trabajo terminado.
--
--  Con "Atender" escribiendo 'atendida_manual', pulsarlo para decir "me hago
--  cargo" dejaba el caso cerrable por un "gracias" del cliente y por el
--  barrido automatico. Y 'marcar_atendida' NO tiene desmarcar -- esta escrito
--  a proposito, porque desmarcar algo resuelto no tiene sentido.
--
--  TOMAR ES OTRA COSA, Y ES REVERSIBLE
--  -----------------------------------
--  Quien toma un caso se lo adjudica: sale de la cola de nadie y pasa a ser
--  de alguien. Eso SI se puede soltar -- se toma por error, o se va el turno,
--  o resulta que era de otra area. Por eso son columnas propias y no un bit
--  mas sobre la de resolucion.
--
--  Es la capa minima de la "asignacion activa" que quedo para una segunda
--  etapa: quien lo tiene y desde cuando. No incluye reasignar ni cola por
--  persona; incluye lo suficiente para que el boton no mienta.

alter table asistente.conversations
  add column if not exists tomada_por  text,
  add column if not exists tomada_en   timestamptz;

comment on column asistente.conversations.tomada_por is
  'Quien se hizo cargo de este caso. NO significa resuelto -- para eso esta '
  'atendida_manual, que ademas habilita el cierre por "gracias" del cliente y '
  'el barrido por plazo. Tomar es reversible: se suelta poniendo esto en NULL.';

comment on column asistente.conversations.tomada_en is
  'Cuando lo tomo. Sirve para ver un caso adjudicado hace horas sin que nadie '
  'escriba, que es distinto de uno que nadie miro.';

create index if not exists conversations_tomada_idx
  on asistente.conversations (organization_id) where tomada_por is not null;

-- Las que se marcaron con el boton "Atender" HOY: se les pone 'tomada_por' y
-- se les QUITA 'atendida_manual', que es lo que no correspondia. Solo las de
-- hoy: 'atendida_manual' existe desde el 13/08 y todo lo anterior si
-- significa resuelto, que es su sentido original.
update asistente.conversations
   set tomada_por = atendida_por,
       tomada_en = actualizado_en,
       atendida_manual = false
 where atendida_manual
   and atendida_por is not null
   and estado <> 'cerrada'
   and actualizado_en::date = date '2026-09-07';
