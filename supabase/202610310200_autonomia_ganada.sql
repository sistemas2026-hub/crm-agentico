-- =============================================================================
--  AUTONOMIA GANADA  -  que accion hace sola cada empresa, quien lo decidio
-- =============================================================================
--
--  Por que existe (31/10/2026, PRD §2 y §8.17 Ola 3)
--  -------------------------------------------------
--  Una accion que hoy aprueba una persona puede pasar a hacerse sola en UNA
--  empresa, solo si cumple las cuatro condiciones del PRD §2. Subir lo decide
--  una persona viendo la evidencia; bajar lo hace el codigo. Esta tabla es ese
--  registro: cada promocion, cada retiro y cada degradacion, con quien, por
--  que y con que evidencia.
--
--  POR QUE NO 'asistente.tenant_config'
--  ------------------------------------
--  El mismo motivo que el interruptor (202609151710): esa ruta se sirve
--  cacheada y cae al YAML de la imagen si la base no contesta. Una autonomia
--  que sigue activa unos segundos despues de degradarse, o que el YAML
--  "devuelve" cuando la base se cae, no es una autonomia ganada.
--
--  SOLO AGREGAR, COMO EL INTERRUPTOR
--  ---------------------------------
--  El estado vigente de (empresa, herramienta) es la ULTIMA fila. Nada se
--  borra ni se edita: la historia de quien dio y quien quito autonomia es lo
--  que se audita. Lo impone el GRANT (sin UPDATE ni DELETE para nadie).
--
--  QUIEN ESCRIBE QUE
--  -----------------
--    autonomia_operador   promover ('activa') y retirar ('retirada'): es
--                         administracion, no runtime (mismo criterio que el
--                         interruptor, paso 10.12).
--    app_backend          LEER, y degradar por 'autonomia_ganada_degradar()',
--                         cuyo cuerpo tiene el estado escrito: no se le puede
--                         pedir 'activa' por ninguna via. Bajar es seguro;
--                         subir no.
--
--  FALLA CERRADO: sin fila, sin tabla o sin base, NINGUNA accion es autonoma
--  (nucleo/seguridad/autonomia_ganada.vigente). Esta tabla no autoriza nada
--  sola: la frontera sigue exigiendo interruptor, techo y previas.
--
--  SIN DATOS DEL CLIENTE: 'evidencia' son conteos (revisadas, rechazadas...).
-- =============================================================================

create table if not exists asistente.autonomia_ganada (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  herramienta     text not null,
  estado          text not null check (estado in ('activa', 'retirada', 'degradada')),
  -- Quien: una persona (por id) al promover o retirar; 'codigo' al degradar.
  actor           text not null check (btrim(actor) <> ''),
  motivo          text,
  -- Los conteos que justificaron la promocion, o la falla que la degrado.
  evidencia       jsonb not null default '{}'::jsonb,
  creado_en       timestamptz not null default now()
);

create index if not exists autonomia_ganada_vigente_idx
  on asistente.autonomia_ganada (organization_id, herramienta, creado_en desc, id desc);

comment on table asistente.autonomia_ganada is
  'Promociones, retiros y degradaciones de autonomia por empresa y herramienta. '
  'Solo agregar: el estado vigente es la ultima fila. Ver nucleo/seguridad/autonomia_ganada.py.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema, y una para el operador
-- -----------------------------------------------------------------------------

alter table asistente.autonomia_ganada enable row level security;
alter table asistente.autonomia_ganada force row level security;

grant usage on schema asistente to app_backend;
grant select on asistente.autonomia_ganada to app_backend;
grant usage on schema asistente to autonomia_operador;
grant select, insert on asistente.autonomia_ganada to autonomia_operador;

drop policy if exists tenant_aislado on asistente.autonomia_ganada;
create policy tenant_aislado on asistente.autonomia_ganada
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

drop policy if exists tenant_aislado_operador on asistente.autonomia_ganada;
create policy tenant_aislado_operador on asistente.autonomia_ganada
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());


-- -----------------------------------------------------------------------------
--  LA DEGRADACION DEL RUNTIME  (condicion 4 del PRD §2)
-- -----------------------------------------------------------------------------
--  El codigo baja la autonomia solo, sin esperar a nadie, cuando una
--  ejecucion falla o una verificacion no confirma. El estado NO es parametro:
--  esta escrito en el cuerpo. Solo degrada lo que esta 'activa' (si ya no lo
--  esta, no agrega nada y devuelve null): una degradacion no puede crear una
--  fila 'activa' ni repetir ruido en la historia.
--
--  SECURITY DEFINER porque app_backend no tiene INSERT; el dueño es quien
--  corre la migracion, que atraviesa FORCE RLS (mismo requisito que
--  'autonomia_detener').

create or replace function asistente.autonomia_ganada_degradar(
        p_org uuid, p_herramienta text, p_motivo text, p_evidencia jsonb)
returns asistente.autonomia_ganada
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_vigente text;
  v_fila asistente.autonomia_ganada;
begin
  if coalesce(btrim(p_motivo), '') = '' then
    raise exception 'hay que decir POR QUE se degrada la autonomia';
  end if;
  --  SECURITY DEFINER atraviesa RLS: sin esto, una sesion fijada en una
  --  empresa podria degradar la de otra. Bajar es seguro, pero no ajeno.
  if p_org is distinct from asistente.org_actual() then
    raise exception 'solo se degrada la autonomia de la empresa de esta sesion';
  end if;
  select a.estado into v_vigente
    from asistente.autonomia_ganada a
   where a.organization_id = p_org and a.herramienta = p_herramienta
   order by a.creado_en desc, a.id desc
   limit 1;
  if v_vigente is distinct from 'activa' then
    return null;
  end if;
  insert into asistente.autonomia_ganada
         (organization_id, herramienta, estado, actor, motivo, evidencia)
  values (p_org, p_herramienta, 'degradada', 'codigo', btrim(p_motivo),
          coalesce(p_evidencia, '{}'::jsonb))
  returning * into v_fila;
  return v_fila;
end $$;

revoke all on function asistente.autonomia_ganada_degradar(uuid, text, text, jsonb) from public;
grant execute on function asistente.autonomia_ganada_degradar(uuid, text, text, jsonb)
  to app_backend, autonomia_operador;

comment on function asistente.autonomia_ganada_degradar(uuid, text, text, jsonb) is
  'Degradacion automatica (PRD §2, condicion 4). El estado esta FIJO en el cuerpo '
  '(''degradada''): no se puede pedir ''activa'' por esta via.';
