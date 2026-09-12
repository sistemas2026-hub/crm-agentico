-- =============================================================================
--  AREA DE TRABAJO DE UN COLABORADOR
-- =============================================================================
--
--  Por que es una columna propia y no se deduce de los agentes
--  -----------------------------------------------------------
--  Tentador: si Cartera precarga 'facturacion', bastaria con mirar que agentes
--  tiene alguien para saber su area. No sirve, por dos motivos.
--
--  El primero es que dos areas pueden compartir un agente. En cuanto eso pasa
--  -- y va a pasar-- la deduccion es una adivinanza, y la columna "Area" de la
--  pantalla mostraria cualquiera de las dos.
--
--  El segundo es que los agentes se EDITAN despues del alta, a proposito:
--  alguien de soporte que ademas atiende facturas termina con los dos. Si el
--  area sale de ahi, esa persona cambia de area sola por haber recibido una
--  capacidad extra, que no es lo que nadie quiso decir.
--
--  El area es un dato que alguien decidio. Los agentes son consecuencia de esa
--  decision mas los ajustes que se le hagan. No son la misma cosa.
-- =============================================================================

create table if not exists asistente.area_colaborador (
  organization_id uuid not null references public.organization(id) on delete cascade,
  profile_id      uuid not null,
  -- El 'nombre' interno de un area declarada en la config del tenant. No se
  -- valida contra ella con una FK: la config vive en otra tabla y versionada,
  -- y un area retirada no deberia romper el alta de nadie. Si aparece un area
  -- que ya no existe, la pantalla la muestra tal cual y se puede corregir.
  area            text not null,
  actualizado_en  timestamptz not null default now(),
  primary key (organization_id, profile_id)
);

comment on table asistente.area_colaborador is
  'Donde trabaja cada colaborador. Una fila por persona: alguien pertenece a '
  'un area, no a varias -- si necesita capacidades de otra, eso son agentes, '
  'no un segundo lugar de trabajo.';

alter table asistente.area_colaborador enable row level security;
alter table asistente.area_colaborador force row level security;

grant select, insert, update, delete on asistente.area_colaborador to app_backend;

drop policy if exists tenant_aislado on asistente.area_colaborador;
create policy tenant_aislado on asistente.area_colaborador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
