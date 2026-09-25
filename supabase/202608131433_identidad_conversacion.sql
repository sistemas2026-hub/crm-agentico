-- =============================================================================
--  IDENTIDAD DE LA CONVERSACION  -  quien es, no solo con que numero escribio
-- =============================================================================
--
--  Por que existe
--  ---------------
--  'usuario_externo' guarda el identificador crudo del canal (telefono, o el
--  BSUID que manda WhatsApp cuando el numero viene oculto). Nunca fue el
--  cliente resuelto, y no habia forma de saberlo: nucleo.seguridad.
--  verificacion.Sesion vive SOLO en memoria del proceso del motor (a
--  proposito, ver su docstring) y se pierde en cada reinicio.
--
--  Con un BSUID de por medio esto dejo de ser cosmetico: no hay ningun
--  telefono contra el cual cruzar automaticamente, asi que la UNICA forma de
--  saber quien escribe es que el propio cliente lo diga (cedula) y el motor
--  lo verifique -- y sin persistir el resultado, /conversaciones muestra el
--  BSUID en crudo para siempre, aunque la verificacion haya ocurrido.
--
--  Que se guarda y que no
--  ------------------------
--  Solo el ID de servicio de WispHub y el nombre que el cliente confirmo --
--  NO el registro completo (54 campos, cedula, GPS, contrasenas: ver PRD
--  RNF-01). Es la misma clase de dato que 'usuario_externo' (un numero de
--  telefono ya se guarda en claro desde agosto 2026) y bastante menos
--  sensible que el contenido de la conversacion, que ya se persiste entero.
-- =============================================================================

alter table asistente.conversations
  add column if not exists id_cliente text,
  add column if not exists nombre_cliente text;

comment on column asistente.conversations.id_cliente is
  'id_servicio de WispHub, solo despues de que el cliente confirmo el '
  'nombre en el segundo paso de _ejecutar_confirmacion (motor.py). NULL '
  'mientras la sesion no este verificada -- no es lo mismo que '
  'usuario_externo, que es el identificador crudo del canal.';
comment on column asistente.conversations.nombre_cliente is
  'El nombre que figura en WispHub para id_cliente, capturado en el mismo '
  'momento. Para que /conversaciones muestre "Juan Perez" en vez de un '
  'BSUID opaco sin tener que consultar WispHub en cada carga de pantalla.';
