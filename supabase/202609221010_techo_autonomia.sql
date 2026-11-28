-- ============================================================================
--  TECHO DE AUTONOMIA POR NIVELES  --  M06-B, 21/09/2026
-- ============================================================================
--  RENUMERADA el 22/09/2026 (M06-F): antes 202609211900. No se aplico en ningun
--  entorno, y con su nombre viejo ordenaba ANTES de migraciones de origin que
--  produccion quiza ya tiene anotadas: el runner la habria tratado como hueco.
--  El contenido no cambio.
--
--  Sobre asistente.nivel_autonomia (202609221000_autonomia2_autorizacion.sql),
--  que ya era el techo por empresa. Esta migracion NO fija ningun nivel y NO
--  habilita nada: solo endurece la tabla y agrega la auditoria de intentos.
--
--  1. AISLAMIENTO. La tabla no tenia RLS: el runtime podia leer el techo de
--     cualquier empresa y solo el WHERE del codigo lo evitaba. Ahora tiene la
--     misma politica que el interruptor, para los dos roles que la tocan.
--
--  2. TOPE DE POLITICA. El techo nuevo no puede pasar de 3 ("ejecutar
--     autorizado"). El 4 de la escala de M09-J es "critico, siempre humano" y
--     eso lo gobierna el gate de las irreversibles, no un numero. Va como
--     NOT VALID: una fila vieja con 4 no rompe la migracion -- y el codigo la
--     lee como techo INVALIDO, o sea que bloquea.
--
--  3. ORIGEN. Cada cambio dice de que canal vino ('cli:...').
--
--  4. INTENTOS. asistente.techo_autonomia_intentos guarda TODOS los intentos
--     de mover el techo: aplicados, repetidos, en conflicto y rechazados, con
--     empresa, nivel anterior, nivel pedido, quien, cuando, motivo, origen y
--     resultado. El runtime solo puede escribir filas 'rechazado' (constancia
--     de que alguien lo intento); un 'aplicado' solo lo escribe el operador,
--     en la misma transaccion que el techo.
--
--  El runtime (app_backend) sigue sin INSERT sobre el techo: no puede subirse
--  el nivel. Lo mueve 'autonomia_operador', la identidad del paso 10.12.
-- ============================================================================

alter table asistente.nivel_autonomia
  add column if not exists origen text;

do $$
begin
  if not exists (select 1 from pg_constraint
                  where conname = 'techo_dentro_de_politica'
                    and conrelid = 'asistente.nivel_autonomia'::regclass) then
    alter table asistente.nivel_autonomia
      add constraint techo_dentro_de_politica check (nivel between 0 and 3)
      not valid;
  end if;
end $$;

comment on table asistente.nivel_autonomia is
  'Techo de autonomia por empresa (M06-B). Solo se AGREGA: el vigente es la '
  'fila mas reciente. Acota, nunca autoriza. Sin fila, con un valor fuera de '
  '0..3 o de otra empresa, el codigo NO ejecuta (falla cerrado; ya no se lee '
  'como nivel 0). Lo escribe solo autonomia_operador.';

alter table asistente.nivel_autonomia enable row level security;
alter table asistente.nivel_autonomia force row level security;

drop policy if exists tenant_aislado on asistente.nivel_autonomia;
create policy tenant_aislado on asistente.nivel_autonomia
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists tenant_aislado_operador on asistente.nivel_autonomia;
create policy tenant_aislado_operador on asistente.nivel_autonomia
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());


-- ----------------------------------------------------------------------------
--  LOS INTENTOS
-- ----------------------------------------------------------------------------
create table if not exists asistente.techo_autonomia_intentos (
  id               uuid primary key default gen_random_uuid(),
  organization_id  uuid not null references public.organization(id) on delete cascade,
  nivel_anterior   smallint,
  nivel_solicitado smallint,
  actor            text not null,
  motivo           text,
  origen           text not null,
  resultado        text not null
                   check (resultado in ('aplicado', 'repetido', 'conflicto', 'rechazado')),
  codigo           text,
  creado_en        timestamptz not null default now()
);

comment on table asistente.techo_autonomia_intentos is
  'Todo intento de mover el techo de autonomia, aplicado o no (M06-B). Solo se '
  'AGREGA. El runtime solo puede anotar rechazos; los aplicados los escribe '
  'autonomia_operador junto con el techo.';

create index if not exists techo_autonomia_intentos_idx
  on asistente.techo_autonomia_intentos (organization_id, creado_en desc);

alter table asistente.techo_autonomia_intentos enable row level security;
alter table asistente.techo_autonomia_intentos force row level security;

drop policy if exists intentos_lee on asistente.techo_autonomia_intentos;
create policy intentos_lee on asistente.techo_autonomia_intentos
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists intentos_runtime_rechazo on asistente.techo_autonomia_intentos;
create policy intentos_runtime_rechazo on asistente.techo_autonomia_intentos
  for insert to app_backend
  with check (organization_id = asistente.org_actual()
              and resultado = 'rechazado');

drop policy if exists intentos_operador on asistente.techo_autonomia_intentos;
create policy intentos_operador on asistente.techo_autonomia_intentos
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_backend') then
    grant select, insert on asistente.techo_autonomia_intentos to app_backend;
  end if;
  if exists (select 1 from pg_roles where rolname = 'autonomia_operador') then
    grant select, insert on asistente.techo_autonomia_intentos to autonomia_operador;
  end if;
end $$;


-- ----------------------------------------------------------------------------
--  COMPROBACION: el runtime no puede escribir el techo
-- ----------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from information_schema.role_table_grants
              where grantee = 'app_backend' and table_schema = 'asistente'
                and table_name = 'nivel_autonomia'
                and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')) then
    raise exception 'app_backend tiene escritura sobre asistente.nivel_autonomia: '
                    'el runtime podria subirse el techo';
  end if;
end $$;
