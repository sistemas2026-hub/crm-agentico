-- ============================================================================
--  M06-C  --  AISLAMIENTO DE LA AUTORIZACION Y SELLO DE LA APROBACION R4
--  21/09/2026. Va DESPUES de 202609191430, 202609211800 y 202609211900.
-- ============================================================================
--
--  1. RLS EN asistente.autorizacion_herramienta Y asistente.ejecucion_autonoma
--     ---------------------------------------------------------------------
--     Las dos se crearon (202609191430) con GRANTs pero SIN RLS: el runtime
--     podia leer las autorizaciones y la bitacora de cualquier empresa, y solo
--     el WHERE del codigo lo evitaba. Mismo hueco que tenia el techo (M06-B).
--
--     Quien las usa, medido en el codigo (M06-C):
--       autorizacion_herramienta  LEE: el gate (persistencia.autorizacion_
--                                 herramienta), como app_backend. ESCRIBE:
--                                 nadie en codigo; solo autonomia_operador
--                                 tiene INSERT (la via administrativa).
--       ejecucion_autonoma        ESCRIBE: la bitacora de la frontera
--                                 (persistencia.registrar_ejecucion_autonoma),
--                                 como app_backend. LEE: nadie en codigo;
--                                 app_backend y el operador tienen SELECT.
--     Django no toca ninguna. No hay ningun acceso legitimo entre empresas.
--
--     Se aplica el MISMO patron que interruptor_autonomia y nivel_autonomia:
--     ENABLE + FORCE, una politica por rol y por comando, siempre contra
--     asistente.org_actual(). No se agrega ningun permiso: las politicas
--     ACOTAN lo que los GRANTs ya daban.
--
--     BYPASSRLS, dicho: el usuario con el que CONECTA el motor lo tiene (asi
--     resuelve el tenant antes de bajar de rol, ver persistencia/db.py::
--     _organizacion), y 'service_role' tambien (el vector de B-7). Ninguno de
--     los dos es el rol con el que se lee o se escribe: el motor hace SET ROLE
--     app_backend, que NO lo tiene, y ahi la RLS aplica. Que exista BYPASSRLS
--     en otra identidad no es motivo para dejar estas tablas sin politica --
--     es exactamente el motivo para tenerla.
--
--  2. SELLO DE LA APROBACION  (asistente.acciones_propuestas.sello_aprobacion)
--     -----------------------------------------------------------------------
--     Hash de tenant + organizacion + herramienta + origen + huella de los
--     argumentos + aprobador, escrito al aprobar (persistencia.
--     aprobar_accion_propuesta) y recalculado al ejecutar
--     (nucleo/seguridad/aprobacion.py). Hasta aca el origen y el tenant solo
--     se exigian "no vacios". El trigger de 202609211800 se extiende: una vez
--     aprobada, el sello tampoco se reescribe.
--
--  NO SE APLICA EN ESTE BLOQUE.
-- ============================================================================


-- ----------------------------------------------------------------------------
--  1a. autorizacion_herramienta
-- ----------------------------------------------------------------------------
alter table asistente.autorizacion_herramienta enable row level security;
alter table asistente.autorizacion_herramienta force row level security;

drop policy if exists autorizacion_runtime_lee on asistente.autorizacion_herramienta;
create policy autorizacion_runtime_lee on asistente.autorizacion_herramienta
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists autorizacion_operador on asistente.autorizacion_herramienta;
create policy autorizacion_operador on asistente.autorizacion_herramienta
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());


-- ----------------------------------------------------------------------------
--  1b. ejecucion_autonoma
-- ----------------------------------------------------------------------------
alter table asistente.ejecucion_autonoma enable row level security;
alter table asistente.ejecucion_autonoma force row level security;

drop policy if exists bitacora_runtime_lee on asistente.ejecucion_autonoma;
create policy bitacora_runtime_lee on asistente.ejecucion_autonoma
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists bitacora_runtime_escribe on asistente.ejecucion_autonoma;
create policy bitacora_runtime_escribe on asistente.ejecucion_autonoma
  for insert to app_backend
  with check (organization_id = asistente.org_actual());

drop policy if exists bitacora_operador_lee on asistente.ejecucion_autonoma;
create policy bitacora_operador_lee on asistente.ejecucion_autonoma
  for select to autonomia_operador
  using (organization_id = asistente.org_actual());


-- ----------------------------------------------------------------------------
--  2. El sello de la aprobacion
-- ----------------------------------------------------------------------------
alter table asistente.acciones_propuestas
  add column if not exists sello_aprobacion text;

create or replace function asistente.acciones_propuestas_inmutable()
returns trigger
language plpgsql
as $$
begin
  if new.organization_id is distinct from old.organization_id
     or new.herramienta   is distinct from old.herramienta
     or new.argumentos    is distinct from old.argumentos
     or new.hash_argumentos is distinct from old.hash_argumentos
     or new.origen        is distinct from old.origen
     or new.contexto      is distinct from old.contexto
     or new.propuesto_por is distinct from old.propuesto_por
     or new.creado_en     is distinct from old.creado_en then
    raise exception 'acciones_propuestas: la identidad de una propuesta no se edita (id %)', old.id
      using errcode = 'check_violation';
  end if;

  if old.conversation_id is not null
     and new.conversation_id is distinct from old.conversation_id then
    raise exception 'acciones_propuestas: la propuesta % ya tiene conversacion', old.id
      using errcode = 'check_violation';
  end if;

  --  Irreversibles: la aprobacion, una vez escrita, no se reescribe -- ni el
  --  estado, ni quien, ni cuando, ni su sello (M06-C).
  if old.hash_argumentos is not null and old.estado <> 'pendiente' then
    if new.estado       is distinct from old.estado
       or new.revisado_por is distinct from old.revisado_por
       or new.revisado_en  is distinct from old.revisado_en
       or new.sello_aprobacion is distinct from old.sello_aprobacion then
      raise exception 'acciones_propuestas: la aprobacion de % ya esta % y no se reescribe',
        old.id, old.estado using errcode = 'check_violation';
    end if;
  end if;

  --  Un sello solo se escribe al APROBAR: una propuesta pendiente no puede
  --  traer uno puesto de antemano.
  if new.sello_aprobacion is not null and new.estado = 'pendiente' then
    raise exception 'acciones_propuestas: una propuesta pendiente no lleva sello (id %)', old.id
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;


-- ----------------------------------------------------------------------------
--  COMPROBACIONES
-- ----------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['autorizacion_herramienta', 'ejecucion_autonoma'] loop
    if not exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'asistente' and c.relname = t
                      and c.relrowsecurity and c.relforcerowsecurity) then
      raise exception 'asistente.% quedo sin RLS forzada', t;
    end if;
  end loop;
  if exists (select 1 from information_schema.role_table_grants
              where grantee = 'app_backend' and table_schema = 'asistente'
                and table_name = 'autorizacion_herramienta'
                and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')) then
    raise exception 'app_backend tiene escritura sobre autorizacion_herramienta: '
                    'el runtime podria autorizarse a si mismo';
  end if;
  if exists (select 1 from information_schema.role_table_grants
              where grantee = 'app_backend' and table_schema = 'asistente'
                and table_name = 'ejecucion_autonoma'
                and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE')) then
    raise exception 'app_backend puede reescribir la bitacora ejecucion_autonoma';
  end if;
end $$;
