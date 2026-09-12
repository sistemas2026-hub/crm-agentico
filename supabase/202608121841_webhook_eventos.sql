-- =============================================================================
--  EVENTOS DE WEBHOOK  -  para no contestar dos veces el mismo mensaje
-- =============================================================================
--
--  Por que existe
--  --------------
--  Meta reintenta la entrega de un webhook si no recibe 200 rapido, y tambien
--  puede reenviar por su cuenta. Sin memoria de lo ya visto, el mismo mensaje
--  del cliente se procesa dos veces: dos turnos del modelo (dos cobros), dos
--  respuestas al cliente, y dos filas en la conversacion.
--
--  El identificador lo pone Meta ('wamid.HBg...'), es unico y estable entre
--  reintentos: alcanza con recordar cuales ya se atendieron.
--
--  POR QUE UNA TABLA Y NO UN SET EN MEMORIA
--  ----------------------------------------
--  El motor corre bajo gunicorn con varios workers (ver docker-compose.prod.yml).
--  Un set en memoria vive en UN proceso, y el reintento de Meta puede caer en
--  otro worker -- justo el caso que hay que cubrir. La memoria compartida es la
--  base.
--
--  Es distinto de '_sesiones' en nucleo/canales/api.py, que si vive en memoria
--  a proposito: ahi perder el estado degrada (se re-verifica), aca perderlo
--  duplica un cobro y un mensaje al cliente.
--
--  RETENCION
--  ---------
--  Estas filas no tienen valor pasadas unas horas: los reintentos de Meta
--  ocurren en minutos. Se limpian con la misma politica de retencion que el
--  resto (limites.retencion_conversaciones_dias), o antes -- no hay razon para
--  guardar un ano de identificadores.
-- =============================================================================

create table if not exists asistente.webhook_eventos (
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- El id que pone Meta. Es la clave: si ya esta, el evento se descarta.
  wamid           text not null,
  canal           text not null default 'whatsapp',
  visto_en        timestamptz not null default now(),
  primary key (organization_id, wamid)
);

-- Para el barrido de limpieza por antiguedad.
create index if not exists webhook_eventos_visto_idx
  on asistente.webhook_eventos (organization_id, visto_en);

comment on table asistente.webhook_eventos is
  'Identificadores de webhooks ya procesados. Evita que un reintento de la '
  'plataforma del canal genere un segundo turno del modelo y un segundo '
  'mensaje al cliente.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.webhook_eventos enable row level security;
alter table asistente.webhook_eventos force row level security;
grant select, insert, update, delete on asistente.webhook_eventos to app_backend;

drop policy if exists tenant_aislado on asistente.webhook_eventos;
create policy tenant_aislado on asistente.webhook_eventos
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
