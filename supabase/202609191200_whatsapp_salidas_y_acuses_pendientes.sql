-- =============================================================================
-- WHATSAPP: COMPUERTA DURABLE DE SALIDA Y ACUSES QUE LLEGAN ANTES DEL MENSAJE
-- =============================================================================
-- Una salida se adquiere en una transaccion corta y se confirma en otra, nunca
-- durante el POST a Meta. La PK tenant-scoped hace que dos requests con la
-- misma clave obtengan un solo derecho a enviar. El resultado "incierto" es
-- terminal: pudo haber salido y por eso no se vuelve a adquirir automaticamente.

-- Las FK compuestas impiden que una salida del tenant A apunte por accidente a
-- un mensaje o conversacion del tenant B, aun bajo un rol con BYPASSRLS.
create unique index if not exists messages_org_id_uq
  on asistente.messages (organization_id, id);
create unique index if not exists conversations_org_id_uq
  on asistente.conversations (organization_id, id);

create table if not exists asistente.whatsapp_salidas (
  organization_id    uuid not null references public.organization(id) on delete cascade,
  clave_idempotencia text not null,
  mensaje_id          uuid,
  conversation_id     uuid,
  proposito           text not null,
  estado              text not null default 'adquirido'
    constraint whatsapp_salidas_estado_check
    check (estado in ('adquirido', 'aceptado', 'rechazado', 'incierto', 'sin_id')),
  wamid               text,
  error               text,
  estado_entrega      text,
  error_entrega       text,
  adquirido_en        timestamptz not null default clock_timestamp(),
  resuelto_en         timestamptz,
  primary key (organization_id, clave_idempotencia),
  constraint whatsapp_salidas_mensaje_fk
    foreign key (organization_id, mensaje_id)
    references asistente.messages(organization_id, id) on delete cascade,
  constraint whatsapp_salidas_conversacion_fk
    foreign key (organization_id, conversation_id)
    references asistente.conversations(organization_id, id) on delete cascade,
  constraint whatsapp_salidas_aceptada_coherente
    check ((estado = 'aceptado') = (wamid is not null))
);

create unique index if not exists whatsapp_salidas_wamid_uq
  on asistente.whatsapp_salidas (organization_id, wamid)
  where wamid is not null;
create index if not exists whatsapp_salidas_mensaje_idx
  on asistente.whatsapp_salidas (organization_id, mensaje_id)
  where mensaje_id is not null;
create index if not exists whatsapp_salidas_conversacion_idx
  on asistente.whatsapp_salidas (organization_id, conversation_id, adquirido_en desc)
  where conversation_id is not null;

alter table asistente.whatsapp_salidas enable row level security;
alter table asistente.whatsapp_salidas force row level security;
grant select, insert, update on asistente.whatsapp_salidas to app_backend;
drop policy if exists tenant_aislado on asistente.whatsapp_salidas;
create policy tenant_aislado on asistente.whatsapp_salidas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

comment on table asistente.whatsapp_salidas is
  'Derecho durable e idempotente a hacer un POST a Meta. adquirido/rechazado/'
  'incierto/sin_id son terminales para la misma clave; solo aceptado lleva wamid.';

-- Meta puede entregar el webhook antes de que la respuesta al POST haya sido
-- persistida. Se conserva el mejor acuse y marcar_envio lo aplica y elimina en
-- la misma transaccion que guarda el wamid.
create table if not exists asistente.whatsapp_acuses_pendientes (
  organization_id uuid not null references public.organization(id) on delete cascade,
  wamid            text not null,
  estado           text not null
    constraint whatsapp_acuses_pendientes_estado_check
    check (estado in ('enviado', 'entregado', 'leido', 'fallido')),
  precedencia      smallint not null
    constraint whatsapp_acuses_pendientes_precedencia_check
    check (precedencia between 1 and 4),
  error            text,
  recibido_en      timestamptz not null default clock_timestamp(),
  actualizado_en   timestamptz not null default clock_timestamp(),
  primary key (organization_id, wamid)
);

create index if not exists whatsapp_acuses_pendientes_retencion_idx
  on asistente.whatsapp_acuses_pendientes (organization_id, actualizado_en);

alter table asistente.whatsapp_acuses_pendientes enable row level security;
alter table asistente.whatsapp_acuses_pendientes force row level security;
grant select, insert, update, delete on asistente.whatsapp_acuses_pendientes to app_backend;
drop policy if exists tenant_aislado on asistente.whatsapp_acuses_pendientes;
create policy tenant_aislado on asistente.whatsapp_acuses_pendientes
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

comment on table asistente.whatsapp_acuses_pendientes is
  'Acuses sin salida correlacionable todavia. Retencion: 30 dias. Limpieza: '
  'DELETE con organization_id obligatorio y actualizado_en < now()-interval ''30 days''; '
  'ejecutarla por tenant desde el reconciliador, nunca como borrado global.';

-- Reemplaza el indice historico no tenant-scoped. Toda busqueda por wamid en
-- runtime incluye organization_id y el indice refleja ese contrato.
drop index if exists asistente.messages_wamid_idx;
create index if not exists messages_org_wamid_idx
  on asistente.messages (organization_id, wamid)
  where wamid is not null;
