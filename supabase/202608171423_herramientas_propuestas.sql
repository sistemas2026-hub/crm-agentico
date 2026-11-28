-- =============================================================================
--  18) HERRAMIENTAS PROPUESTAS -- asistente de configuracion guiada
-- =============================================================================
--  CLAUDE.md: "la proxima empresa que se conecte no deberia necesitar una
--  sesion de codigo para algo que ya se resolvio una vez". Un colaborador
--  ADMIN describe una API nueva; el rol 'configuracion_guiada'
--  (nucleo/herramientas/sondeo.py) la sondea de verdad -- solo lectura,
--  bloqueado contra redes privadas/internas -- y arma un borrador de
--  Herramienta con lo que encontro.
--
--  Nada de esto se activa solo. 'estado' arranca en 'pendiente' y solo una
--  persona lo mueve a 'aprobada' (recien ahi se agrega de verdad al catalogo
--  del tenant, via el mismo editor.py que ya usa /agentes) o 'rechazada' --
--  mismo criterio ya aplicado en asistente.revisiones_supervisor: el
--  asistente propone, nunca decide solo.

create table if not exists asistente.herramientas_propuestas (
  id                  uuid primary key default gen_random_uuid(),
  organization_id     uuid not null references public.organization(id) on delete cascade,
  -- Lo que el colaborador describio, en sus palabras -- para que quien
  -- aprueba entienda la intencion, no solo el YAML resultante.
  descripcion_pedido   text not null,
  -- Evidencia del sondeo real: URL(s) probadas, filtros verificados con el
  -- metodo del valor imposible, muestra de campos. Es lo que separa esto de
  -- "el modelo dice que funciona" -- se puede auditar que se llamo de
  -- verdad y que devolvio.
  sondeo               jsonb not null default '{}'::jsonb,
  -- El borrador de Herramienta (misma forma que nucleo/config/schema.py),
  -- listo para pasarle a editor.py si se aprueba.
  herramienta_propuesta jsonb not null,
  propuesto_por        text not null,
  estado                text not null default 'pendiente',  -- pendiente|aprobada|rechazada
  motivo_rechazo        text,
  revisado_por          text,
  creado_en             timestamptz not null default now(),
  revisado_en            timestamptz
);

create index if not exists herramientas_propuestas_org_idx
  on asistente.herramientas_propuestas (organization_id, estado, creado_en desc);

alter table asistente.herramientas_propuestas enable row level security;
alter table asistente.herramientas_propuestas force row level security;
grant select, insert, update, delete on asistente.herramientas_propuestas to app_backend;
create policy tenant_aislado on asistente.herramientas_propuestas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
