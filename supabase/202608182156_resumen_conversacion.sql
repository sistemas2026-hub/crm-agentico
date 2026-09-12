-- =============================================================================
--  RESUMEN DE CONVERSACION  -  el contexto que sobrevive al cierre
-- =============================================================================
--  Nace de un caso real (18/08/2026): una conversacion acumulo 67 mensajes a lo
--  largo de 180 HORAS -- internet lento, un caso escalado y despues television,
--  todo en el mismo hilo, porque una conversacion solo se cerraba si el
--  evaluador la marcaba resuelta o si la cerraba una persona.
--
--  Con ese contexto el modelo se pierde de dos formas distintas, y las dos se
--  vieron: volvio a preguntar algo que el cliente ya le habia contestado dos
--  turnos antes, y afirmo "ya mire el estado de tu servicio: la fibra llega
--  bien" reciclando mediciones de CUATRO HORAS antes, sin ejecutar ninguna
--  herramienta en ese tramo. Lo segundo es peor: es decirle a alguien que su
--  equipo esta sano sin haberlo mirado.
--
--  La conversacion ahora se cierra sola por inactividad, pero cerrar sin mas
--  perderia lo que ya se sabe del cliente. Por eso al cerrar se guarda un
--  resumen corto, y cuando la persona vuelve a escribir se le entrega al
--  modelo ANTES del primer turno: sabe con quien habla y que quedo pendiente,
--  sin arrastrar 67 mensajes.
-- =============================================================================

alter table asistente.conversations
    add column if not exists resumen text;

comment on column asistente.conversations.resumen is
  'Que paso en esta conversacion, en pocas frases. Se escribe al cerrarla y se
   le entrega al modelo cuando el mismo usuario_externo vuelve a escribir (ver
   nucleo/seguimiento/resumen.py). No reemplaza al historial: es lo que queda
   cuando el historial ya no se manda.';
