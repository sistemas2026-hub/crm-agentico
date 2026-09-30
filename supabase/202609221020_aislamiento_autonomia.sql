-- ============================================================================
--  AISLAMIENTO DE LA AUTORIZACION Y DE LA BITACORA AUTONOMA  (M06-C, M06-F)
--  Va DESPUES de 202609221000_autonomia2_autorizacion.sql, que crea las dos
--  tablas. Reconstruida el 22/09/2026 (M06-F) sobre origin/fix/integracion-
--  wisphub: es la mitad de RLS de la antigua 202609212000_m06c_aislamiento_y_
--  sello.sql, que no se aplico en ningun entorno. La otra mitad -- el sello --
--  vive ahora en 202609221030_aprobacion_vinculante_b5.sql, junto al resto de
--  la aprobacion vinculante, para que haya UN solo trigger sobre
--  acciones_propuestas y no dos versiones de la misma funcion.
-- ============================================================================
--
--  RLS EN asistente.autorizacion_herramienta Y asistente.ejecucion_autonoma
--  ---------------------------------------------------------------------
--  Las dos se crean (202609221000) con GRANTs pero SIN RLS: sin esto el
--  runtime podria leer las autorizaciones y la bitacora de cualquier empresa,
--  y solo el WHERE del codigo lo evitaria. Mismo hueco que tenia el techo.
--
--  Quien las usa, medido en el codigo:
--    autorizacion_herramienta  LEE: el gate (persistencia.autorizacion_
--                              herramienta), como app_backend. ESCRIBE:
--                              nadie en codigo; solo autonomia_operador
--                              tiene INSERT (la via administrativa).
--    ejecucion_autonoma        ESCRIBE: la bitacora de la frontera
--                              (persistencia.registrar_ejecucion_autonoma),
--                              como app_backend. LEE: nadie en codigo;
--                              app_backend y el operador tienen SELECT.
--  Django no toca ninguna. No hay ningun acceso legitimo entre empresas.
--
--  Mismo patron que interruptor_autonomia y nivel_autonomia: ENABLE + FORCE,
--  una politica por rol y por comando, siempre contra asistente.org_actual().
--  No se agrega ningun permiso: las politicas ACOTAN lo que los GRANTs daban.
--
--  BYPASSRLS, dicho: el usuario con el que CONECTA el motor lo tiene (asi
--  resuelve el tenant antes de bajar de rol, ver persistencia/db.py::
--  _organizacion), y 'service_role' tambien (el vector de B-7). Ninguno de
--  los dos es el rol con el que se lee o se escribe: el motor hace SET ROLE
--  app_backend, que NO lo tiene, y ahi la RLS aplica. Por eso ademas de la
--  politica, las comprobaciones del final exigen que app_backend no tenga
--  escritura sobre la autorizacion ni pueda reescribir la bitacora.
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
