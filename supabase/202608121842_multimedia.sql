-- =============================================================================
--  MULTIMEDIA  -  las fotos y audios que manda el cliente por el canal
-- =============================================================================
--
--  Por que existe
--  --------------
--  Para un ISP, la foto de las luces del router es EL caso de soporte: dice en
--  un segundo lo que al cliente le cuesta tres mensajes explicar. Sin guardarla
--  no llega a la persona que toma el caso.
--
--  El enlace que da Meta no alcanza: es temporal y firmado. Si el agente entra
--  al rato, ya vencio y la foto se perdio -- justo cuando mas hace falta, que
--  es despues de escalar.
--
--  POR QUE EN POSTGRES Y NO EN UN ALMACEN DE OBJETOS
--  -------------------------------------------------
--  Supabase Storage funciona en esta instalacion (verificado), pero escribir
--  ahi obliga al motor a autenticarse con SUPABASE_SERVICE_ROLE_KEY, que
--  ARQUITECTURA.md marca como "solo migraciones" porque tiene BYPASSRLS. Usada
--  en cada peticion, el aislamiento por empresa deja de evaluarse: la foto de
--  un cliente quedaria sin la barrera que si tiene su propia conversacion.
--
--  Aca hereda la MISMA politica que el resto del esquema, entra en la copia de
--  seguridad con todo lo demas, y el borrado por antiguedad es un delete en vez
--  de reconciliar filas contra objetos huerfanos en un bucket.
--
--  El costo es tamano en la base, y esta medido: ~20 fotos por dia comprimidas
--  a ~200 KB, con 30 dias de retencion, son ~120 MB en regimen. Si algun dia el
--  volumen lo cambia, mover esto a un almacen de objetos con una credencial
--  acotada al bucket (no la llave maestra) es la migracion correcta.
--
--  RETENCION MAS CORTA QUE EL TEXTO, A PROPOSITO
--  ---------------------------------------------
--  Las conversaciones se guardan 365 dias (limites.retencion_conversaciones_dias);
--  esto, 30 (limites.retencion_multimedia_dias). No son lo mismo: una
--  conversacion escrita es barata y util para depurar, y una foto pesa y puede
--  mostrar la casa, la cedula o una cara. La foto sirve para resolver el caso,
--  y un caso vive dias.
-- =============================================================================

create table if not exists asistente.media (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  conversation_id uuid not null references asistente.conversations(id) on delete cascade,
  -- El mensaje al que acompana. Puede ser null si el turno no llego a
  -- guardarse: la foto igual se conserva y se ve en el hilo por conversacion.
  mensaje_id      uuid references asistente.messages(id) on delete cascade,
  -- El id de Meta. Unico por organizacion, para que un reintento del webhook
  -- no guarde la misma foto dos veces.
  media_id        text not null,
  tipo            text not null,            -- image | audio | video | document
  mime            text,
  -- Los bytes YA comprimidos (ver nucleo/canales/media.py). Se guarda lo que
  -- se va a mostrar, no el original: nadie necesita los 4 MB que salen de un
  -- telefono moderno para ver que la luz esta en rojo.
  contenido       bytea not null,
  bytes           integer not null,
  -- Lo que el cliente escribio junto a la foto, si escribio algo.
  descripcion     text,
  creado_en       timestamptz not null default now(),
  unique (organization_id, media_id)
);

-- Para el barrido por antiguedad y para listar lo de una conversacion.
create index if not exists media_conversacion_idx
  on asistente.media (organization_id, conversation_id, creado_en);
create index if not exists media_antiguedad_idx
  on asistente.media (organization_id, creado_en);

comment on table asistente.media is
  'Fotos y audios recibidos por el canal, comprimidos. Retencion mas corta que '
  'las conversaciones (limites.retencion_multimedia_dias): la foto sirve para '
  'resolver el caso, y un caso vive dias.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.media enable row level security;
alter table asistente.media force row level security;
grant select, insert, update, delete on asistente.media to app_backend;

drop policy if exists tenant_aislado on asistente.media;
create policy tenant_aislado on asistente.media
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
