-- =============================================================================
--  ORIGEN Y AUTOR DE CADA MENSAJE -- el rol dice como hablarle al modelo, no quien escribio
-- =============================================================================
--  'rol' mezclaba dos preguntas. 'assistant' lo escriben tanto la IA como una
--  persona del equipo que responde desde la bandeja o el ticket -- a
--  proposito: la ventana de 24 h de WhatsApp y el protocolo del modelo
--  necesitan que las dos esten del mismo lado. Pero entonces nada guardado
--  decia QUIEN habia escrito cada cosa.
--
--  La consecuencia medida (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D8): mientras el
--  proceso vive, la respuesta de una persona entra al historial del modelo con
--  su nombre adelante; al reiniciar -- el autodeploy lo hace varias veces por
--  dia -- el historial se reconstruye desde esta tabla, sin nombre, y la IA
--  toma como propio lo que prometio una persona.
--
--  QUE SE AGREGA
--  -------------
--    origen              cliente | ia | humano | sistema. NULL = legado: todo
--                        lo anterior a este corte. Se midio que no hay
--                        evidencia para asignarle procedencia a ninguna fila
--                        historica (gate G4, 0 filas), asi que NO hay backfill:
--                        no se inventa procedencia. La aplicacion exige origen
--                        en toda fila nueva; la base lo admite nulo SOLO por
--                        el legado, y por eso no es NOT NULL.
--    autor_usuario_id    id del usuario del CRM que escribio (uuid: es el
--                        User.id de Django, el mismo que llega en el JWT como
--                        user_id). Sin FK: el motor no depende de las tablas
--                        del CRM. NULL salvo en mensajes de personas.
--    autor_nombre        el nombre TAL COMO ERA al escribir. Si la persona
--                        cambia de nombre, lo dicho sigue firmado como se firmo.
--    clave_idempotencia  la genera quien compone el mensaje. Reintentar un
--                        envio con la misma clave NO crea otra fila (D15): antes
--                        cada "Reintentar" insertaba una copia.
--
--  QUE NO CAMBIA
--  -------------
--  Ni 'rol' ni ninguna fila existente. Tampoco la unica fila historica con
--  rol = 'humano': se lee como legado, no se edita.
--
--  Aditiva y sin efecto de conducta por si sola: el codigo que escribe y lee
--  estas columnas se despliega DESPUES, en un paso aparte.

alter table asistente.messages
  add column if not exists origen text
    constraint messages_origen_check
    check (origen in ('cliente', 'ia', 'humano', 'sistema')),
  add column if not exists autor_usuario_id uuid,
  add column if not exists autor_nombre text,
  add column if not exists clave_idempotencia text;

comment on column asistente.messages.origen is
  'Quien produjo el mensaje: cliente | ia | humano | sistema. NULL = legado '
  'anterior al 16/09/2026, sin procedencia registrada. Independiente de rol, '
  'que sigue siendo el protocolo del modelo y del canal.';

comment on column asistente.messages.autor_nombre is
  'Nombre de la persona del equipo al momento de escribir (instantanea). Solo '
  'con origen = humano.';

comment on column asistente.messages.clave_idempotencia is
  'La genera quien compone el mensaje. La misma clave en la misma conversacion '
  'no crea una segunda fila: reintentar reintenta la entrega de la existente.';

-- Una clave repetida solo choca dentro de la MISMA conversacion y organizacion.
-- Con organization_id aunque conversation_id ya sea unico: el aislamiento entre
-- empresas no depende de esa casualidad.
create unique index if not exists messages_clave_idempotencia_uq
  on asistente.messages (organization_id, conversation_id, clave_idempotencia)
  where clave_idempotencia is not null;
