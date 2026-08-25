-- =============================================================================
--  06) REVISIONES DEL SUPERVISOR
-- =============================================================================
--  Un agente supervisor revisa cada conversacion que termina resuelta (ver
--  nucleo/seguimiento/supervisor.py) y propone si fue un buen ejemplo, de
--  que caso, y un aporte para el manual. Nada de esto se vuelve confiable
--  solo: 'estado' arranca en 'pendiente' y solo una persona lo mueve a
--  'aprobado' o 'descartado' desde /manual -- el supervisor no tiene forma
--  de verificar si un dato es correcto de verdad (ver el mismo criterio ya
--  aplicado en asistente.ejemplos_validados).

create table if not exists asistente.revisiones_supervisor (
  id                uuid primary key default gen_random_uuid(),
  organization_id   uuid not null references public.organization(id) on delete cascade,
  conversation_id   uuid not null references asistente.conversations(id) on delete cascade,
  es_buen_ejemplo   boolean not null,
  -- Solo tiene sentido cuando es_buen_ejemplo=true; NULL en las descartadas.
  caso              text,
  -- Por que el supervisor decidio esto -- util tanto para aprobar un buen
  -- ejemplo como para entender que salio mal en uno malo (sirve de QA
  -- aunque nunca alimente el manual).
  justificacion     text not null,
  aporte_sugerido   text,
  estado            text not null default 'pendiente',  -- pendiente|aprobado|descartado
  revisado_por      text,
  creado_en         timestamptz not null default now(),
  revisado_en       timestamptz,
  -- Una revision por conversacion: el disparador (conversacion marcada
  -- 'resuelta') solo pasa una vez por conversacion real.
  unique (conversation_id)
);

create index if not exists revisiones_supervisor_org_idx
  on asistente.revisiones_supervisor (organization_id, estado, creado_en desc);
create index if not exists revisiones_supervisor_caso_idx
  on asistente.revisiones_supervisor (organization_id, caso) where estado = 'pendiente';

alter table asistente.revisiones_supervisor enable row level security;
alter table asistente.revisiones_supervisor force row level security;
grant select, insert, update, delete on asistente.revisiones_supervisor to app_backend;
create policy tenant_aislado on asistente.revisiones_supervisor
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
