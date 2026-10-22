-- =============================================================================
--  B.6  --  PASO 3: TRANSFERIR LA PROPIEDAD DE LAS TABLAS DEL CRM
-- =============================================================================
--
--    *** NO EJECUTAR EN PRODUCCION SIN AUTORIZACION EXPLICITA ***
--
--  Uso:
--    psql "$DSN" -v ON_ERROR_STOP=1 -v esperadas=129 -f 03_transferir_propiedad.sql
--
--  'esperadas' es una guarda, no un adorno: si el numero de tablas que este
--  script esta a punto de mover no coincide con el que se inventario en el
--  precheck, ALGO CAMBIO entre una cosa y la otra y hay que mirar antes de
--  seguir. Sin ese numero, el script se niega a correr.
--
--  ALCANCE  --  que se mueve y que NO
--  ---------------------------------
--  Se mueve:  tablas ordinarias (relkind='r') del esquema 'public' cuyo dueno
--             sea 'postgres'. En produccion son las 129 del CRM (verificado en
--             B.3 contra el registro de modelos de Django).
--
--  NO se mueve, y no por suerte sino porque el filtro no las alcanza:
--    * las 145 funciones + 4 agregados de 'public'  -> son de supabase_admin
--    * PostgREST / Realtime / Storage / GraphQL     -> viven en sus esquemas
--                                                      (auth, storage, realtime,
--                                                      graphql), no en 'public'
--    * cualquier tabla que Supabase anada a 'public' -> seria de supabase_admin
--    * el esquema 'asistente' del motor              -> otro esquema, y 5 de sus
--                                                      tablas ya son de
--                                                      asistente_owner
--    * vistas, vistas materializadas, triggers, tipos -> en produccion hay CERO
--                                                        de cada uno (B.3)
--
--  LO QUE SE ARRASTRA SOLO  (medido en B.3, no supuesto)
--  -----------------------------------------------------
--    * los indices                    -> siguen a su tabla
--    * las secuencias 'owned by'      -> siguen a su tabla, tanto las de
--                                        columnas IDENTITY como las de SERIAL
--    * las politicas RLS y el FORCE   -> pertenecen a la TABLA, no a su dueno
--    * los GRANT existentes           -> estan sobre el objeto, no sobre el dueno
--
--  LO QUE *NO* SE ARRASTRA
--    * una secuencia SUELTA (creada aparte, usada como default, sin OWNED BY).
--      Produccion no tiene ninguna -- las 51 estan todas atadas -- pero el
--      precheck lo vuelve a comprobar antes de cada ejecucion.
--
--  TRANSACCIONAL
--  -------------
--  Todo va en un begin/commit. Si falla a mitad, Postgres revierte el lote
--  entero: no existe el estado "mitad transferido". Eso importa porque una
--  tabla rezagada rompe la primera migracion que la toque, meses despues, con
--  'must be owner of table' (medido en B.3, escenario 6).
-- =============================================================================

\set ON_ERROR_STOP on

begin;

-- -----------------------------------------------------------------------------
--  GUARDA 1: que exista el destino y que quien ejecuta pueda ejercerlo
-- -----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'crm_owner') then
    raise exception 'crm_owner no existe. Correr antes 01_crear_roles.sql';
  end if;
  if not pg_has_role(current_user, 'crm_owner', 'USAGE') then
    raise exception 'el rol actual (%) no puede actuar como crm_owner; '
                    'falta "grant crm_owner to %"', current_user, current_user;
  end if;
end $$;

-- -----------------------------------------------------------------------------
--  GUARDA 2: el recuento tiene que coincidir con el del precheck
-- -----------------------------------------------------------------------------
-- El valor entra por set_config y no directo en el bloque: psql NO interpola
-- sus variables dentro de 'do $$ ... $$' -- el texto entre comillas de dolar le
-- resulta opaco, y ':esperadas' llegaria literal al servidor. Aqui la
-- sustitucion ocurre fuera, donde psql si la ve, y el bloque lo lee de vuelta.
-- El 'true' lo deja local a esta transaccion, asi que no queda nada puesto.
select set_config('b6.esperadas', :'esperadas', true);

do $$
declare
  n_mover int;
  n_esperadas int := current_setting('b6.esperadas')::int;
begin
  select count(*) into n_mover
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r'
     and pg_get_userbyid(c.relowner) = 'postgres';

  if n_mover <> n_esperadas then
    raise exception
      'se iban a mover % tabla(s) y el precheck conto %. Algo cambio entre '
      'una cosa y la otra: revisar ANTES de seguir.', n_mover, n_esperadas;
  end if;
  raise notice 'a mover: % tabla(s) de public', n_mover;
end $$;

-- -----------------------------------------------------------------------------
--  GUARDA 3: ninguna secuencia suelta que se quedaria atras
-- -----------------------------------------------------------------------------
do $$
declare sueltas text;
begin
  select string_agg(s.relname, ', ') into sueltas
    from pg_class s
    join pg_namespace n on n.oid = s.relnamespace
   where n.nspname = 'public' and s.relkind = 'S'
     and pg_get_userbyid(s.relowner) = 'postgres'
     and not exists (
       select 1 from pg_depend d
        where d.objid = s.oid
          and d.refclassid = 'pg_class'::regclass
          and d.deptype in ('a', 'i'));   -- 'a' = serial, 'i' = identity

  if sueltas is not null then
    raise exception
      'hay secuencia(s) SUELTA(S) que no seguirian a su tabla: %. '
      'Transferirlas aparte o revisar por que existen.', sueltas;
  end if;
end $$;

-- -----------------------------------------------------------------------------
--  LA TRANSFERENCIA
-- -----------------------------------------------------------------------------
do $$
declare
  t record;
  n int := 0;
begin
  for t in
    select c.relname
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relkind = 'r'
       and pg_get_userbyid(c.relowner) = 'postgres'
     order by c.relname
  loop
    execute format('alter table public.%I owner to crm_owner', t.relname);
    n := n + 1;
  end loop;
  raise notice 'transferidas % tabla(s) a crm_owner', n;
end $$;

-- -----------------------------------------------------------------------------
--  COMPROBACION FINAL  --  dentro de la transaccion, para que un fallo revierta
-- -----------------------------------------------------------------------------
do $$
declare
  rezagadas int;
  de_trafico int;
  nombres text;
begin
  -- Ninguna tabla del CRM puede quedar bajo postgres.
  select count(*), string_agg(c.relname, ', ') into rezagadas, nombres
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r'
     and pg_get_userbyid(c.relowner) = 'postgres';
  if rezagadas > 0 then
    raise exception 'quedaron % tabla(s) bajo postgres: %', rezagadas, nombres;
  end if;

  -- Y ninguna puede haber acabado en manos del usuario de TRAFICO: un dueno se
  -- saltea su propia politica RLS salvo que este FORCE, asi que eso seria
  -- cambiar un problema por otro peor.
  select count(*) into de_trafico
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind = 'r'
     and pg_get_userbyid(c.relowner) in ('crm_user', 'crm_migrator');
  if de_trafico > 0 then
    raise exception 'quedaron % tabla(s) en manos de una credencial CON login', de_trafico;
  end if;

  raise notice 'OK: 0 tablas bajo postgres, 0 bajo una credencial con login';
end $$;

commit;

-- =============================================================================
--  VERIFICACION POSTERIOR (fuera de la transaccion)
--
--    select pg_get_userbyid(relowner) as dueno, relkind, count(*)
--      from pg_class c join pg_namespace n on n.oid = c.relnamespace
--     where n.nspname = 'public' and relkind in ('r','S','i')
--     group by 1, 2 order by 1, 2;
--
--    -- esperado: crm_owner en las tres clases; supabase_admin puede aparecer
--    --           en funciones, que no son relkind
--
--    select count(*) from pg_policies where schemaname = 'public';
--    -- esperado: el MISMO numero que antes de empezar (anotarlo en el precheck)
-- =============================================================================
