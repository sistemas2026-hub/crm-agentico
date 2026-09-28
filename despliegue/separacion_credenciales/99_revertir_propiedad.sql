-- =============================================================================
--  B.6  --  ROLLBACK DEL PASO 3: DEVOLVER LA PROPIEDAD A postgres
-- =============================================================================
--
--    *** NO EJECUTAR EN PRODUCCION SIN AUTORIZACION EXPLICITA ***
--
--  Uso:
--    psql "$DSN" -v ON_ERROR_STOP=1 -f 99_revertir_propiedad.sql
--
--  Cuando hace falta
--  -----------------
--  Casi nunca. Antes de correr esto, considerar que:
--
--    * devolver la propiedad NO es necesario para restablecer el servicio. Si
--      el problema es que el backend no arranca o que las consultas fallan, el
--      arreglo rapido es volver DBUSER a su valor anterior y recrear los
--      contenedores -- la propiedad puede quedarse en crm_owner sin molestar,
--      porque postgres sigue siendo miembro y puede con todo.
--
--    * este script es para el caso en que se decida DESHACER la transicion
--      entera, no para apagar un incendio.
--
--  Que NO hace
--  -----------
--  No borra los roles. Un crm_owner sin tablas y un crm_migrator sin uso son
--  inertes: el primero no tiene login (y por eso el pooler no puede siquiera
--  intentarlo) y el segundo no esta en ninguna variable mientras MIGRATOR_DBUSER
--  siga vacia. Borrarlos es una decision aparte y exige que nada dependa de
--  ellos.
--
--  Que no se pierde
--  ----------------
--  Nada. 'ALTER TABLE ... OWNER TO' es una operacion de catalogo: no reescribe
--  ni mueve una sola fila. Medido en B.3 -- 135 tablas de ida y vuelta, mismo
--  recuento de filas antes y despues, 132 politicas intactas.
-- =============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  t record;
  n int := 0;
begin
  if not exists (select 1 from pg_roles where rolname = 'crm_owner') then
    raise notice 'crm_owner no existe: no hay nada que revertir';
    return;
  end if;

  for t in
    select c.relname
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relkind = 'r'
       and pg_get_userbyid(c.relowner) = 'crm_owner'
     order by c.relname
  loop
    execute format('alter table public.%I owner to postgres', t.relname);
    n := n + 1;
  end loop;
  raise notice 'devueltas % tabla(s) a postgres', n;
end $$;

-- -----------------------------------------------------------------------------
--  COMPROBACION
-- -----------------------------------------------------------------------------
do $$
declare quedan int;
begin
  select count(*) into quedan
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r'
     and pg_get_userbyid(c.relowner) = 'crm_owner';
  if quedan > 0 then
    raise exception 'quedaron % tabla(s) bajo crm_owner', quedan;
  end if;
  raise notice 'OK: ninguna tabla de public quedo bajo crm_owner';
end $$;

commit;

-- =============================================================================
--  SI ADEMAS SE QUIERE DESHACER EL RESTO (en este orden):
--
--    -- 1) quitar los default privileges declarados en el paso 2
--    alter default privileges for role crm_owner in schema public
--      revoke select, insert, update, delete on tables from crm_user;
--    alter default privileges for role crm_owner in schema public
--      revoke usage, select on sequences from crm_user;
--    alter default privileges for role crm_owner in schema public
--      revoke execute on functions from crm_user;
--
--    -- 2) devolverle a crm_user el CREATE, si se le habia revocado
--    grant create on schema public to crm_user;
--
--    -- 3) y solo si nada depende ya de ellos, los roles
--    alter role crm_migrator in database <base> reset role;
--    drop owned by crm_migrator;   -- no borra tablas: quita privilegios
--    drop role crm_migrator;
--    drop owned by crm_owner;
--    drop role crm_owner;
--
--  ANTES del punto 3, vaciar MIGRATOR_DBUSER en Dokploy y recrear el backend
--  con 'up -d --force-recreate'. Si se borra el rol con la variable todavia
--  puesta, el backend no arranca.
-- =============================================================================
