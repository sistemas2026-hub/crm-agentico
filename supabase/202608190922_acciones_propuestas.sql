-- =============================================================================
--  20) ACCIONES PROPUESTAS -- confirmacion humana real para escrituras
-- =============================================================================
--  Herramienta.requiere_confirmacion existe desde el principio (se valida en
--  schema.py) pero nunca se aplicaba en tiempo de ejecucion -- documentado
--  como decision explicita en tenants/rapilink.config.yaml: "no reactivar el
--  gate sin discutirlo, afecta a todo el catalogo de escritura". Se retoma
--  ahora con un caso concreto (crear/responder/actualizar tickets de WispHub),
--  no en abstracto.
--
--  Mismo espiritu que asistente.herramientas_propuestas (configuracion
--  guiada): el asistente arma la propuesta, nunca decide solo. La diferencia
--  es el alcance -- esta tabla es GENERICA, para cualquier herramienta de
--  escritura que declare requiere_confirmacion, no solo una feature puntual.
--
--  'argumentos' guarda los valores REALES que se van a mandar a la API si se
--  aprueba -- a proposito, a diferencia de asistente.tool_calls (que
--  enmascara todo). Esta tabla no es un log de auditoria, es la carga util
--  pendiente de una escritura real: sin los valores completos no se podria
--  ejecutar al aprobar. El aislamiento sigue siendo RLS por organizacion,
--  igual que el resto del esquema.

create table if not exists asistente.acciones_propuestas (
  id                  uuid primary key default gen_random_uuid(),
  organization_id     uuid not null references public.organization(id) on delete cascade,
  herramienta         text not null,
  argumentos          jsonb not null default '{}'::jsonb,
  -- Resumen legible para quien aprueba -- que se va a hacer, en una linea,
  -- sin que tenga que leer el JSON crudo de 'argumentos'.
  resumen             text not null,
  rol_solicitante     text,
  propuesto_por       text not null,
  estado              text not null default 'pendiente',  -- pendiente|aprobada|rechazada
  motivo_rechazo      text,
  revisado_por        text,
  -- Lo que devolvio la API real al ejecutarse -- solo se llena tras aprobar.
  -- Nunca se pisa 'argumentos': son dos cosas distintas, lo que se pidio vs.
  -- lo que paso al intentarlo.
  resultado_ejecucion jsonb,
  codigo_error        text,
  creado_en           timestamptz not null default now(),
  revisado_en         timestamptz
);

create index if not exists acciones_propuestas_org_idx
  on asistente.acciones_propuestas (organization_id, estado, creado_en desc);

alter table asistente.acciones_propuestas enable row level security;
alter table asistente.acciones_propuestas force row level security;
grant select, insert, update, delete on asistente.acciones_propuestas to app_backend;
create policy tenant_aislado on asistente.acciones_propuestas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
