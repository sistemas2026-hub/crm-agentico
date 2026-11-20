-- =============================================================================
--  LEIDA HASTA  -  los "no leidos" de la Bandeja, como WhatsApp Business
-- =============================================================================
--
--  Por que existe (11/11/2026)
--  ---------------------------
--  La Bandeja no decia que conversaciones tienen mensajes del cliente que
--  nadie del equipo abrio todavia. WhatsApp Business lo dice con un contador
--  verde y el nombre en negrita, y el equipo lo pidio igual: un chat que el
--  cliente escribio mientras todos miraban otra cosa no puede verse igual que
--  uno ya leido.
--
--  UNA MARCA POR CONVERSACION, COMPARTIDA POR EL EQUIPO
--  ----------------------------------------------------
--  Es "alguien del equipo lo leyo", no "lo leyo cada persona". Es lo que hace
--  WhatsApp Business con varios dispositivos en la misma cuenta, y es lo que
--  sirve para repartir el trabajo: si Ana ya abrio el chat, para Luis deja de
--  ser una novedad. Una marca por persona seria una tabla nueva (persona x
--  conversacion) y una cuenta que cambia segun quien mira -- dos colas
--  distintas para el mismo equipo.
--
--  POR QUE UNA HORA Y NO UN CONTADOR
--  ---------------------------------
--  Un contador guardado ("3 sin leer") es un veredicto guardado: hay que
--  sumarle en cada mensaje entrante y restarle al abrir, y cualquier camino
--  que se olvide de una de las dos lo deja mintiendo para siempre. Es la misma
--  regla que la salud del seguimiento de campo (SPEC/objetivos/
--  seguimiento-campo-por-ticket.md): se guarda el HECHO -- hasta cuando se
--  leyo -- y la cuenta se CALCULA en la lectura (db.ultima_actividad):
--
--      no_leidos = mensajes del cliente (rol 'user') con creado_en > leida_hasta
--
--  NULL es "nunca la abrio nadie": cuenta todos los mensajes del cliente. Es
--  el valor de una conversacion nueva, y es el correcto.
--
--  LAS QUE YA EXISTEN NACEN LEIDAS
--  -------------------------------
--  Sin el UPDATE de abajo, cada conversacion abierta hoy amaneceria con todos
--  sus mensajes historicos como "no leidos": la cola entera en negrita el dia
--  del despliegue, y un contador que no distingue nada no le sirve a nadie.
--  Se fija now() en todas: lo que escriba el cliente DESPUES de esta migracion
--  es lo primero que va a contar.
--
--  No toca 'actualizado_en' (la cola ordena por esa columna y el filtro de
--  cerradas la usa) ni 'relevo_version': marcar leida no es una transicion del
--  relevo. No hay triggers sobre esta tabla que lo hagan por su cuenta.
--
--  COMO SE REVIERTE
--  ----------------
--      alter table asistente.conversations drop column if exists leida_hasta;
--
--  Pero OJO con el orden: el codigo que lee esta columna (la cola y el
--  detector de seguimientos, por db.ultima_actividad) falla si la columna no
--  esta. Revertir la migracion exige revertir antes el codigo.
-- =============================================================================

set local lock_timeout = '3s';
set local statement_timeout = '60s';

alter table asistente.conversations
    add column if not exists leida_hasta timestamptz;

comment on column asistente.conversations.leida_hasta is
    'Hasta cuando alguien del equipo leyo la conversacion. Los no leidos se '
    'calculan (mensajes del cliente posteriores); NULL = nunca se abrio.';

update asistente.conversations
   set leida_hasta = now()
 where leida_hasta is null;
