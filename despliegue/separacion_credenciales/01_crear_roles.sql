-- =============================================================================
--  B.6  --  PASO 1: CREAR LOS ROLES  (crm_owner, crm_migrator)
-- =============================================================================
--
--    *** NO EJECUTAR EN PRODUCCION SIN AUTORIZACION EXPLICITA ***
--
--  Esta carpeta NO es 'supabase/'. Ahi vive el ledger de migraciones del motor
--  (cli/migrar_asistente.py recorre 'supabase/*.sql' y aplica lo que falte);
--  un archivo operativo de una sola vez no tiene por que entrar en ese
--  registro, y meterlo ahi haria que se reaplicara solo.
--
--  Se ejecuta a mano, una vez, como un rol que pueda crear roles.
--
--  Uso:
--    psql "$DSN" -v ON_ERROR_STOP=1 \
--         -v clave_migrator="'...'" -v base="postgres" \
--         -f 01_crear_roles.sql
--
--  La clave NO va en este archivo ni en el repositorio. Se pasa por -v.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

-- -----------------------------------------------------------------------------
--  crm_owner  --  el rol DUENO. No es una credencial.
-- -----------------------------------------------------------------------------
--  nologin      nadie puede conectarse como el. Y no es solo higiene: la
--               funcion que Supavisor usa para autenticar
--               (pgbouncer.get_auth) filtra por 'rolcanlogin', asi que un rol
--               NOLOGIN es literalmente inalcanzable por el pooler. Medido en
--               la Etapa B.5.
--  nobypassrls  si algun dia poseyera datos y alguien le diera login, FORCE
--               sigue haciendo falta. No se le regala el atajo.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'crm_owner') then
    create role crm_owner nologin nosuperuser nobypassrls nocreatedb nocreaterole;
    raise notice 'crm_owner creado';
  else
    raise notice 'crm_owner ya existia -- no se toca';
  end if;
end $$;

-- Quien corre esto tiene que ser MIEMBRO del rol destino, o el
-- 'alter table ... owner to crm_owner' del paso 3 falla. Es requisito
-- estructural, no comodidad.
--
-- LA FORMA IMPORTA, y costo un intento fallido contra produccion (17/09/2026).
-- Escrito como 'grant crm_owner to current_user' -- la palabra clave, en un
-- GRANT plano -- el servidor CERRO LA CONEXION en esa linea:
--
--     psql:01_crear_roles.sql:51: server closed the connection unexpectedly
--
-- La transaccion revirtio entera y produccion quedo intacta, pero el rol no se
-- creo. La forma de abajo es la que SI funciona contra esta misma base: es
-- textualmente la de supabase/202609141300_scheduler_funciones.sql:132, que
-- hizo exactamente esto con asistente_owner y esta aplicada en produccion
-- desde el 14/09. Resuelve 'current_user' a un identificador literal ANTES de
-- ejecutar el GRANT.
--
-- El comentario anterior ya citaba esa migracion como precedente y el codigo
-- usaba otra forma. Eso fue el error.
do $$
begin
  execute format('grant crm_owner to %I', current_user);
end $$;

-- postgres conserva la llave de emergencia. No es un privilegio nuevo: ya es
-- miembro de crm_user CON ADMIN OPTION (medido en B.2), asi que mover la
-- propiedad hacia abajo nunca lo deja fuera.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'postgres') then
    execute 'grant crm_owner to postgres';
  end if;
end $$;

-- EL CREATE VA AQUI, NO EN crm_migrator.
-- Con 'set role', Postgres evalua los permisos como el rol ACTIVO. Medido en
-- B.4: con el CREATE solo en crm_migrator, la migracion falla con
-- 'permission denied for schema public' aunque crm_migrator si lo tenga.
grant usage, create on schema public to crm_owner;

-- -----------------------------------------------------------------------------
--  crm_migrator  --  la credencial de MIGRACIONES
-- -----------------------------------------------------------------------------
-- OJO con la forma de esto: psql NO interpola sus variables dentro de un
-- bloque 'do $$ ... $$'. El texto entre comillas de dolar le resulta opaco, asi
-- que ':clave_migrator' llegaria literal al servidor y daria
-- 'syntax error at or near ":"'. Paso por ahi al probarlo.
--
-- '\gexec' ejecuta el resultado de la consulta anterior. La variable se
-- sustituye ANTES, donde psql si la ve, y el 'where not exists' hace que no
-- genere nada -- y por lo tanto no ejecute nada-- si el rol ya existia. Eso lo
-- vuelve re-ejecutable sin pisar la clave de un rol ya creado.
select format(
  'create role crm_migrator login password %L '
  'nosuperuser nobypassrls nocreatedb nocreaterole',
  :'clave_migrator')
 where not exists (select 1 from pg_roles where rolname = 'crm_migrator')
\gexec

grant crm_owner to crm_migrator;

-- ### LA PIEZA QUE IMPIDE QUE ESTO SE DESHAGA SOLO ###
--
-- Sin esto, cada tabla que cree una migracion queda de 'crm_migrator' -- un rol
-- CON login -- y a los seis meses media base vuelve a estar en manos de una
-- credencial. Medido en B.3: con el 'set role', lo que crea queda de
-- crm_owner; sin el, de crm_migrator.
--
-- Se fija en el ROL, no en cada migracion, para que no dependa de que alguien
-- se acuerde de escribir 'SET ROLE' en el sitio correcto.
alter role crm_migrator in database :"base" set role = crm_owner;

-- Lo que crm_migrator NO tiene, a proposito:
--   BYPASSRLS   migrar no es ver los datos de todas las organizaciones
--   SUPERUSER   nunca
--   CREATEROLE  no puede fabricarse un rol con mas permisos que el
--   acceso a 'asistente'  el motor es de otro

-- -----------------------------------------------------------------------------
--  COMPROBACION  --  falla ruidosamente si algo no quedo como se pidio
-- -----------------------------------------------------------------------------
do $$
declare r record;
begin
  select rolcanlogin, rolsuper, rolbypassrls into r
    from pg_roles where rolname = 'crm_owner';
  if r.rolcanlogin or r.rolsuper or r.rolbypassrls then
    raise exception 'crm_owner quedo mal: login=% super=% bypassrls=%',
      r.rolcanlogin, r.rolsuper, r.rolbypassrls;
  end if;

  select rolcanlogin, rolsuper, rolbypassrls into r
    from pg_roles where rolname = 'crm_migrator';
  if not r.rolcanlogin or r.rolsuper or r.rolbypassrls then
    raise exception 'crm_migrator quedo mal: login=% super=% bypassrls=%',
      r.rolcanlogin, r.rolsuper, r.rolbypassrls;
  end if;

  if not pg_has_role('crm_migrator', 'crm_owner', 'USAGE') then
    raise exception 'crm_migrator no puede actuar como crm_owner';
  end if;

  if not exists (select 1 from pg_db_role_setting s
                   join pg_roles ro on ro.oid = s.setrole
                  where ro.rolname = 'crm_migrator'
                    and s.setconfig::text like '%role=crm_owner%') then
    raise exception 'falta el SET role = crm_owner en crm_migrator';
  end if;

  raise notice 'OK: los dos roles quedaron como se pidio';
end $$;

commit;

-- =============================================================================
--  DESPUES DE ESTO, ANTES DE SEGUIR AL PASO 2:
--
--    Comprobar que crm_migrator autentica POR EL POOLER, no solo contra
--    Postgres directo. Es la condicion C de la Etapa B.5 y el unico punto que
--    no se pudo verificar de antemano:
--
--      PGPASSWORD=... psql -h <host> -p 5433 \
--        -U crm_migrator.<tenant-id> -d <base> \
--        -c "select current_user, session_user"
--
--    Tiene que devolver:  current_user = crm_owner  |  session_user = crm_migrator
--
--    Si devuelve crm_migrator en las dos, falta el 'set role' de arriba.
--    Si no conecta, PARAR: revisar antes de tocar nada mas.
-- =============================================================================
