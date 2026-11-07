-- =============================================================================
--  MENSAJES AUTOMATICOS  -  cada aviso por plantilla, una sola vez por motivo
-- =============================================================================
--
--  Por que existe (28/10/2026)
--  ---------------------------
--  Dexter reemplaza al CRM que mandaba los avisos por WhatsApp (ticket creado,
--  pago confirmado, recordatorio, suspension...). Cada aviso sale por un
--  MOTIVO concreto -- este ticket, esta factura, este pago -- y ese motivo no
--  puede dispararlo dos veces: un reintento del disparador, una tarea diaria
--  que corre de nuevo o dos procesos a la vez le mandarian al cliente el mismo
--  mensaje dos veces, y los bloqueos que eso provoca le bajan la calidad al
--  numero de toda la empresa.
--
--  Se excluye por CLAVE (evento, clave del motivo), nunca por un select previo:
--  la fila se inserta ANTES de mandar ("guardar primero, entregar despues").
--
--  SIN DATOS DEL CLIENTE: ni el numero ni el texto. La clave es el id del
--  motivo (el caso, la factura), no la persona.
-- =============================================================================

create table if not exists asistente.mensajes_automaticos (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  evento          text not null,
  -- El motivo: 'caso:<id>', 'factura:<id>:<fecha_corte>', ... Lo arma quien dispara.
  clave           text not null,
  plantilla       text not null,
  estado          text not null default 'reservado'
                  check (estado in ('reservado', 'enviado', 'fallido')),
  wamid           text,
  creado_en       timestamptz not null default now(),
  enviado_en      timestamptz,
  unique (organization_id, evento, clave)
);

create index if not exists mensajes_automaticos_fecha_idx
  on asistente.mensajes_automaticos (organization_id, creado_en desc);

comment on table asistente.mensajes_automaticos is
  'Cada aviso por plantilla que salio (o se intento), una vez por (evento, motivo). '
  'Sin numero ni texto del cliente.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.mensajes_automaticos enable row level security;
alter table asistente.mensajes_automaticos force row level security;
grant select, insert, update on asistente.mensajes_automaticos to app_backend;

drop policy if exists tenant_aislado on asistente.mensajes_automaticos;
create policy tenant_aislado on asistente.mensajes_automaticos
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
