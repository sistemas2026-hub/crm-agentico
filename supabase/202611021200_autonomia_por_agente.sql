-- =============================================================================
--  AUTONOMIA POR AGENTE  -  la misma accion puede salir sola en un agente y no en otro
-- =============================================================================
--
--  Por que existe (02/11/2026, PRD §2 y §8.18)
--  -------------------------------------------
--  El usuario, viendo /capacidad: "eso no deberia ir en cada agente... con un
--  agente si pueda reiniciar y otro no". Hasta hoy la autonomia de una accion
--  valia para toda la empresa. Ahora cada fila puede nombrar el agente (el rol
--  del tenant que pidio la accion: 'cliente_final', 'soporte'...).
--
--  LA REGLA, ENTERA
--  ----------------
--    rol nulo        = todos los agentes que usan esa herramienta.
--    rol nombrado    = solo ese agente, y MANDA sobre la general: si un agente
--                      tiene una fila propia, decide esa (activa o no); si no
--                      tiene, decide la general.
--    degradar        = baja TODO lo activo de esa herramienta en la empresa,
--                      general y por agente. Una verificacion que no confirma
--                      dice que la ACCION no anda, no que un agente la uso mal;
--                      y quien degrada (verificacion, ejecucion fallida,
--                      huerfana) no siempre sabe que agente la pidio.
--
--  POR QUE NO EN LA CONFIG DEL AGENTE (tenant_config)
--  --------------------------------------------------
--  Se controla desde /agentes, pero el dato sigue aca: tenant_config se sirve
--  cacheado y cae al YAML de la imagen si la base no contesta (falla ABIERTO,
--  CLAUDE.md §8). Una autonomia retirada que siguiera viva unos minutos no es
--  un permiso. Esta tabla falla CERRADO: sin fila o sin base, nada sale solo.
--
--  COMPATIBLE CON LO DESPLEGADO
--  ----------------------------
--  Las tres funciones de 202610310200 siguen existiendo y ahora miran solo las
--  filas generales (rol nulo): el codigo de antes del despliegue sigue
--  funcionando igual mientras la migracion y el push no coinciden. Las nuevas
--  (*_agente) reciben el rol, y la degradacion pasa a bajar todos los alcances.

alter table asistente.autonomia_ganada
  add column if not exists rol text check (rol is null or btrim(rol) <> '');

comment on column asistente.autonomia_ganada.rol is
  'El agente (rol del tenant) al que vale la fila; nulo = todos. La fila propia de un agente '
  'manda sobre la general. Ver supabase/202611021200_autonomia_por_agente.sql.';

create index if not exists autonomia_ganada_por_agente_idx
  on asistente.autonomia_ganada (organization_id, herramienta, rol, creado_en desc, id desc);


-- -----------------------------------------------------------------------------
--  DEGRADAR: todos los alcances activos de la herramienta
-- -----------------------------------------------------------------------------
create or replace function asistente.autonomia_ganada_degradar(
        p_org uuid, p_herramienta text, p_motivo text, p_evidencia jsonb)
returns asistente.autonomia_ganada
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_alcance record;
  v_fila asistente.autonomia_ganada;
begin
  if coalesce(btrim(p_motivo), '') = '' then
    raise exception 'hay que decir POR QUE se degrada la autonomia';
  end if;
  if p_org is distinct from asistente.org_actual() then
    raise exception 'solo se degrada la autonomia de la empresa de esta sesion';
  end if;
  --  Cada alcance (general y cada agente) cuya ULTIMA fila esta activa.
  for v_alcance in
    select distinct on (a.rol) a.rol, a.estado
      from asistente.autonomia_ganada a
     where a.organization_id = p_org and a.herramienta = p_herramienta
     order by a.rol, a.creado_en desc, a.id desc
  loop
    if v_alcance.estado = 'activa' then
      insert into asistente.autonomia_ganada
             (organization_id, herramienta, rol, estado, actor, motivo, evidencia)
      values (p_org, p_herramienta, v_alcance.rol, 'degradada', 'codigo', btrim(p_motivo),
              coalesce(p_evidencia, '{}'::jsonb))
      returning * into v_fila;
    end if;
  end loop;
  --  null si no habia nada activo: una degradacion no repite ruido.
  return v_fila;
end $$;


-- -----------------------------------------------------------------------------
--  PROMOVER Y RETIRAR, CON AGENTE
-- -----------------------------------------------------------------------------
create or replace function asistente.autonomia_ganada_promover_agente(
        p_org uuid, p_herramienta text, p_rol text, p_actor text, p_motivo text,
        p_evidencia jsonb)
returns asistente.autonomia_ganada
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_vigente text;
  v_fila asistente.autonomia_ganada;
  v_rol text := nullif(btrim(coalesce(p_rol, '')), '');
begin
  if coalesce(btrim(p_actor), '') = '' then
    raise exception 'hay que decir QUIEN promueve';
  end if;
  if coalesce(btrim(p_herramienta), '') = '' then
    raise exception 'hay que decir QUE herramienta';
  end if;
  if p_org is distinct from asistente.org_actual() then
    raise exception 'solo se promueve en la empresa de esta sesion';
  end if;
  --  Serializa dos clics a la vez sobre el mismo alcance.
  perform pg_advisory_xact_lock(hashtextextended(
    p_org::text || ':' || p_herramienta || ':' || coalesce(v_rol, '*'), 0));
  select a.estado into v_vigente
    from asistente.autonomia_ganada a
   where a.organization_id = p_org and a.herramienta = p_herramienta
     and a.rol is not distinct from v_rol
   order by a.creado_en desc, a.id desc
   limit 1;
  if v_vigente = 'activa' then
    raise exception 'ya es autonoma en ese alcance: no se promueve dos veces';
  end if;
  insert into asistente.autonomia_ganada
         (organization_id, herramienta, rol, estado, actor, motivo, evidencia)
  values (p_org, p_herramienta, v_rol, 'activa', btrim(p_actor), btrim(coalesce(p_motivo, '')),
          coalesce(p_evidencia, '{}'::jsonb))
  returning * into v_fila;
  return v_fila;
end $$;

create or replace function asistente.autonomia_ganada_retirar_agente(
        p_org uuid, p_herramienta text, p_rol text, p_actor text, p_motivo text)
returns asistente.autonomia_ganada
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_fila asistente.autonomia_ganada;
begin
  if coalesce(btrim(p_actor), '') = '' then
    raise exception 'hay que decir QUIEN retira';
  end if;
  if coalesce(btrim(p_motivo), '') = '' then
    raise exception 'hay que decir POR QUE se retira';
  end if;
  if p_org is distinct from asistente.org_actual() then
    raise exception 'solo se retira en la empresa de esta sesion';
  end if;
  insert into asistente.autonomia_ganada
         (organization_id, herramienta, rol, estado, actor, motivo)
  values (p_org, p_herramienta, nullif(btrim(coalesce(p_rol, '')), ''), 'retirada',
          btrim(p_actor), btrim(p_motivo))
  returning * into v_fila;
  return v_fila;
end $$;

revoke all on function asistente.autonomia_ganada_promover_agente(uuid, text, text, text, text, jsonb) from public;
revoke all on function asistente.autonomia_ganada_retirar_agente(uuid, text, text, text, text) from public;
grant execute on function asistente.autonomia_ganada_promover_agente(uuid, text, text, text, text, jsonb)
  to app_backend, autonomia_operador;
grant execute on function asistente.autonomia_ganada_retirar_agente(uuid, text, text, text, text)
  to app_backend, autonomia_operador;


-- -----------------------------------------------------------------------------
--  LAS DE ANTES, ACOTADAS A LO GENERAL (rol nulo)
-- -----------------------------------------------------------------------------
--  Despues de las *_agente: una funcion 'language sql' valida su cuerpo al
--  crearla, y estas las llaman.
create or replace function asistente.autonomia_ganada_promover(
        p_org uuid, p_herramienta text, p_actor text, p_motivo text, p_evidencia jsonb)
returns asistente.autonomia_ganada
language sql
security definer
set search_path = pg_catalog
as $$
  select * from asistente.autonomia_ganada_promover_agente(
    p_org, p_herramienta, null, p_actor, p_motivo, p_evidencia)
$$;

create or replace function asistente.autonomia_ganada_retirar(
        p_org uuid, p_herramienta text, p_actor text, p_motivo text)
returns asistente.autonomia_ganada
language sql
security definer
set search_path = pg_catalog
as $$
  select * from asistente.autonomia_ganada_retirar_agente(
    p_org, p_herramienta, null, p_actor, p_motivo)
$$;


-- -----------------------------------------------------------------------------
--  AUTOVERIFICACION
-- -----------------------------------------------------------------------------
do $$
declare
  v_funcion text;
begin
  foreach v_funcion in array array['autonomia_ganada_promover', 'autonomia_ganada_retirar',
                                   'autonomia_ganada_degradar',
                                   'autonomia_ganada_promover_agente',
                                   'autonomia_ganada_retirar_agente'] loop
    if not exists (select 1 from pg_proc p
                     join pg_namespace n on n.oid = p.pronamespace
                     join pg_roles r on r.oid = p.proowner
                    where n.nspname = 'asistente' and p.proname = v_funcion
                      and (r.rolsuper or r.rolbypassrls)) then
      raise exception 'el dueño de % no puede atravesar FORCE RLS', v_funcion;
    end if;
  end loop;
  if not exists (select 1 from information_schema.columns
                  where table_schema = 'asistente' and table_name = 'autonomia_ganada'
                    and column_name = 'rol') then
    raise exception 'autonomia_ganada: falta la columna rol';
  end if;
end $$;
