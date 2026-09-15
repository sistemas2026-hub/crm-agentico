-- =============================================================================
--  BLOQUEOS EN LA TRAZA -- distinguir "el codigo lo freno" de "el tercero fallo"
-- =============================================================================
--  Son dos cosas opuestas y hasta ahora se veian iguales:
--
--    el sistema externo devolvio 400   -> algo se rompio, hay que reportarlo
--    el codigo freno la accion         -> la proteccion funciono como debia
--
--  Quien atiende tiene que hacer cosas contrarias en cada caso: conseguir lo
--  que falta, o avisar que la API del ISP no responde. Verlos con la misma X
--  lleva justo a la reaccion equivocada.
--
--  El motor produce SEIS codigos que no vienen de ningun sistema externo sino
--  de sus propios gates:
--
--    IDENTIDAD_NO_VERIFICADA      pidio datos de cuenta sin identidad confirmada
--    PRECONDICION_NO_CUMPLIDA     quiso reiniciar un equipo sin haberlo medido
--    FALTA_HABLAR_CON_EL_CLIENTE  accion que corta el servicio, y el cliente
--                                 todavia no dijo que se le cayo
--    IDENTIDAD_NO_RESUELTA · HERRAMIENTA_DESCONOCIDA · LIMITE_DE_CONVERSACION
--
--  POR QUE UNA COLUMNA Y NO DEDUCIRLO DEL TEXTO
--  --------------------------------------------
--  'codigo_error' es texto libre: ahi conviven estos codigos con mensajes de
--  excepcion enteros ("HTTPError: 400 Client Error for url..."). Deducir el
--  tipo comparando contra una lista de seis cadenas obliga a mantener esa
--  lista en la base, en el motor y en la pantalla -- tres lugares que se
--  desincronizan en cuanto alguien agrega un gate.
--
--  LO QUE ESTO CORRIGE, Y POR QUE ERA DEFENDIBLE ANTES
--  ---------------------------------------------------
--  IDENTIDAD_NO_VERIFICADA se excluia del registro a proposito, con este
--  razonamiento escrito en el motor: no es un fallo, es el gate frenando antes
--  de llamar a nada, y mostrarlo como una X en "Ver proceso" parece un error
--  cuando la proteccion funciono.
--
--  Era cierto mientras la traza fuera una lista de exitos y fallos. Deja de
--  serlo cuando la pantalla cuenta los bloqueos: un panel que dice "acciones
--  bloqueadas: 0" en una conversacion donde el sistema bloqueo tres cosas es
--  peor que no mostrar nada. Ahora se registra, pero marcado -- sigue sin
--  contar como fallo, y ademas se puede ver.
--
--  Medido antes de este cambio: de 570 llamadas registradas, 545 exitosas,
--  22 fallos de sistemas externos y CERO bloqueos. No porque no ocurrieran.

alter table asistente.tool_calls
  add column if not exists es_bloqueo boolean not null default false;

comment on column asistente.tool_calls.es_bloqueo is
  'true = la llamada no salio del motor porque un gate del CODIGO la freno '
  '(identidad sin verificar, precondicion no cumplida, accion que interrumpe '
  'el servicio sin confirmar). NO es un fallo: es la proteccion funcionando. '
  'Se separa de codigo_error porque ese campo es texto libre y mezcla estos '
  'codigos con excepciones enteras de HTTP.';

-- Las que ya estaban registradas con un codigo de gate se marcan: sin esto,
-- toda conversacion anterior a hoy mostraria cero bloqueos y una cantidad
-- inflada de errores. Es una sola pasada; de aca en mas lo escribe el motor.
update asistente.tool_calls
   set es_bloqueo = true
 where es_bloqueo = false
   and codigo_error in ('IDENTIDAD_NO_VERIFICADA', 'PRECONDICION_NO_CUMPLIDA',
                        'FALTA_HABLAR_CON_EL_CLIENTE', 'IDENTIDAD_NO_RESUELTA',
                        'HERRAMIENTA_DESCONOCIDA', 'LIMITE_DE_CONVERSACION');

create index if not exists tool_calls_bloqueo_idx
  on asistente.tool_calls (organization_id, conversation_id)
  where es_bloqueo;
