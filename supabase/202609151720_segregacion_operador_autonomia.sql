-- =============================================================================
--  SEGREGACION OPERADOR / RUNTIME DEL INTERRUPTOR DE AUTONOMIA
-- =============================================================================
--  Version versionada del SQL disenado en el paso 10.11, empaquetada como
--  migracion en el paso 10.13B para que entre por el flujo canonico y no como
--  SQL manual contra produccion.
--
--  EL PROBLEMA QUE CIERRA
--  ----------------------
--  202609151710 crea el interruptor y le da a 'app_backend' select + insert.
--  Pero 'app_backend' es a la vez el runtime del motor Y el rol con el que
--  corre cli/autonomia.py, porque db.sesion() degrada a app_backend. Con INSERT,
--  el runtime puede agregar una fila 'activo' -- es decir, ACTIVARSE LA
--  AUTONOMIA A SI MISMO. Eso es fail-open, y es justo lo que el interruptor
--  existe para impedir.
--
--  DEPENDE DE 202609151710
--  -----------------------
--  La tabla, su RLS y su politica 'tenant_aislado' tienen que existir antes.
--  Por eso ordena despues (1720 > 1715 > 1710) y por eso el bloque 0 se niega a
--  correr sobre un lote incompleto en vez de fallar a medias.
--
--  LO QUE NO HACE -- no duplica nada de 1710 ni de 1715
--  ----------------------------------------------------
--  No crea la tabla, ni sus indices, ni sus constraints, ni la politica
--  'tenant_aislado', ni la fila semilla. Solo agrega: el rol operador, su
--  politica propia ('tenant_aislado_operador', nombre distinto), la funcion de
--  parada y los permisos. Todo con 'if not exists' / 'or replace' / 'drop
--  policy if exists', asi que reaplicarla no duplica objetos.
-- =============================================================================


-- -----------------------------------------------------------------------------
--  0)  PRECONDICIONES  -  no se segrega sobre un lote incompleto
-- -----------------------------------------------------------------------------

do $$
begin
  if to_regclass('asistente.interruptor_autonomia') is null then
    raise exception
      'falta asistente.interruptor_autonomia: hay que aplicar antes '
      '202609151710_interruptor_autonomia.sql';
  end if;

  if not exists (select 1
                   from pg_class c
                   join pg_namespace n on n.oid = c.relnamespace
                  where n.nspname = 'asistente'
                    and c.relname = 'interruptor_autonomia'
                    and c.relrowsecurity
                    and c.relforcerowsecurity) then
    raise exception
      'interruptor_autonomia no tiene RLS + FORCE: segregar sobre una tabla '
      'abierta daria una falsa sensacion de control';
  end if;
end $$;


-- -----------------------------------------------------------------------------
--  1)  EL ROL DE OPERADOR
-- -----------------------------------------------------------------------------
--  NOLOGIN a proposito: no es una credencial nueva que guardar en Dokploy ni
--  que rotar. Se alcanza con SET ROLE desde la credencial que ya existe, que es
--  justo lo que hace db.sesion() hoy con app_backend.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'autonomia_operador') then
    create role autonomia_operador nologin;
  end if;
end $$;

--  Explicito y reaplicable: si el rol ya existia con otros atributos, aqui
--  vuelve a la forma minima. Un operador no necesita nada de esto.
--
--  SUPERUSER NO SE IMPONE: SE COMPRUEBA  --  corregido el 17/09/2026 (10.13C)
--  ------------------------------------------------------------------------
--  La version anterior incluia 'nosuperuser' en esta linea y PRODUCCION la
--  rechazo entera con 'permission denied to alter role'. Alli 'postgres' corre
--  con SUPERUSER=false, y un rol que no es superusuario no puede tocar el
--  atributo SUPERUSER de nadie -- ni siquiera para quitarlo. En la replica
--  pasaba porque alli 'postgres' es el superusuario de arranque.
--
--  Y era redundante: medido en produccion, un rol recien creado ya nace con
--  login, superuser, createdb, createrole, replication y bypassrls en falso.
--  Asi que el atributo se COMPRUEBA abajo en vez de imponerse. Las otras cinco
--  propiedades si se imponen: estan probadas una por una contra produccion.
alter role autonomia_operador
  nologin nocreatedb nocreaterole noreplication nobypassrls;

do $$
begin
  if exists (select 1 from pg_roles
              where rolname = 'autonomia_operador' and rolsuper) then
    raise exception
      'autonomia_operador es SUPERUSER. Esta migracion no lo degrada a '
      'proposito: produccion rechaza ALTER ROLE ... NOSUPERUSER porque su '
      'postgres no es superusuario. Corregirlo con una credencial de '
      'superusuario antes de volver a aplicar.';
  end if;
end $$;

--  'set true' es lo que habilita el SET ROLE; 'inherit false' evita que
--  postgres cargue estos privilegios sin pedirlos.
--
--  OJO -- 'USAGE' y 'SET' son privilegios DISTINTOS desde PostgreSQL 16:
--  pg_has_role(...,'USAGE') mide herencia, no la capacidad de SET ROLE. El
--  bloque de verificacion del final comprueba 'SET', que es el que importa.
--
--  En Supabase, supautils auto-concede cada rol nuevo a 'postgres' con
--  'INHERIT FALSE, SET FALSE'. Esta concesion explicita es la que deja SET en
--  true; si no llegara a tomar efecto, la verificacion final aborta la
--  migracion entera en vez de dejar un operador inalcanzable.
grant autonomia_operador to postgres with inherit false, set true;


-- -----------------------------------------------------------------------------
--  2)  EL RUNTIME PIERDE LA ESCRITURA DIRECTA
-- -----------------------------------------------------------------------------
--  Conserva SELECT: el motor tiene que poder LEER el estado antes de cada
--  accion autonoma. Lo que pierde es la capacidad de escribirlo.

revoke insert on asistente.interruptor_autonomia from app_backend;


-- -----------------------------------------------------------------------------
--  3)  EL OPERADOR ES EL UNICO CON ESCRITURA DIRECTA
-- -----------------------------------------------------------------------------

grant usage on schema asistente to autonomia_operador;
grant select, insert on asistente.interruptor_autonomia to autonomia_operador;

--  Con FORCE ROW LEVEL SECURITY un rol sin politica no ve ni escribe NADA. La
--  politica de 1710 es 'to app_backend', asi que el operador necesita la suya.
--  Mismo predicado: el aislamiento por organizacion no se relaja.
drop policy if exists tenant_aislado_operador on asistente.interruptor_autonomia;
create policy tenant_aislado_operador on asistente.interruptor_autonomia
  for all to autonomia_operador
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());


-- -----------------------------------------------------------------------------
--  4)  LA PARADA DE EMERGENCIA DEL RUNTIME
-- -----------------------------------------------------------------------------
--  POR QUE app_backend PUEDE DETENER
--  --------------------------------
--  Parar es seguro y arrancar no. Un motor que detecta algo raro tiene que
--  poder frenar sin esperar a nadie; el costo de una parada indebida es que el
--  agente deja de actuar solo, y eso se revierte con una reactivacion auditada.
--  El costo de una activacion indebida es una escritura contra un tercero que
--  nadie autorizo.
--
--  QUE IMPIDE USARLA PARA ACTIVAR
--  ------------------------------
--  El estado NO es un parametro: esta escrito en el cuerpo. No hay forma de
--  pedirle 'activo' a esta funcion. Es la diferencia entre "el runtime puede
--  detener" y "el runtime puede escribir el estado que quiera". La verificacion
--  final ademas prohibe que exista una segunda 'autonomia_detener' sobrecargada
--  que si acepte el estado.
--
--  POR QUE SECURITY DEFINER
--  ------------------------
--  La tabla tiene FORCE RLS y las politicas son 'to app_backend' y 'to
--  autonomia_operador'. app_backend ya no tiene INSERT, asi que sin definer la
--  parada seria imposible. El dueno de la funcion es quien corre la migracion;
--  la verificacion final exige que ese rol pueda atravesar FORCE RLS
--  (superusuario o BYPASSRLS), porque si no la parada fallaria recien al
--  llamarla -- y una parada de emergencia que falla cuando se necesita no
--  sirve de nada.

create or replace function asistente.autonomia_detener(
        p_org uuid, p_actor text, p_motivo text)
returns asistente.interruptor_autonomia
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_anterior text;
  v_fila asistente.interruptor_autonomia;
begin
  if coalesce(btrim(p_actor), '') = '' then
    raise exception 'hay que decir QUIEN detiene la autonomia';
  end if;
  if coalesce(btrim(p_motivo), '') = '' then
    raise exception 'hay que decir POR QUE se detiene la autonomia';
  end if;
  if not exists (select 1 from public.organization o where o.id = p_org) then
    raise exception 'la organizacion % no existe', p_org;
  end if;

  select i.estado into v_anterior
    from asistente.interruptor_autonomia i
   where i.organization_id = p_org
   order by i.creado_en desc, i.id desc
   limit 1;

  insert into asistente.interruptor_autonomia
         (organization_id, estado, estado_anterior, actor, motivo)
  values (p_org, 'detenido', v_anterior, btrim(p_actor), btrim(p_motivo))
  returning * into v_fila;
  return v_fila;
end $$;

revoke all on function asistente.autonomia_detener(uuid, text, text) from public;
grant execute on function asistente.autonomia_detener(uuid, text, text)
  to app_backend, autonomia_operador;

comment on function asistente.autonomia_detener(uuid, text, text) is
  'Parada de emergencia. El estado esta FIJO en el cuerpo (''detenido''): no se '
  'puede pedir ''activo'' por esta via. Es el unico camino de escritura que le '
  'queda a app_backend sobre el interruptor. Ver PASO10.11 y PASO10.13B.';


-- -----------------------------------------------------------------------------
--  5)  VERIFICACION  -  la migracion se niega a quedar a medias
-- -----------------------------------------------------------------------------
--  Todo esto corre dentro de la misma transaccion que el resto del archivo: si
--  algo no quedo como debe, se deshace la migracion entera y NO queda anotada
--  en el ledger. Un control de seguridad que se instala "casi bien" es peor que
--  no instalarlo, porque nadie vuelve a mirarlo.

do $$
declare
  v_privs  text;
  v_dueno  text;
begin
  -- 5.1 el rol no puede iniciar sesion ni tener atributos de mas
  if exists (select 1 from pg_roles
              where rolname = 'autonomia_operador'
                and (rolcanlogin or rolsuper or rolcreaterole
                     or rolcreatedb or rolbypassrls or rolreplication)) then
    raise exception 'autonomia_operador quedo con atributos que no le corresponden';
  end if;

  -- 5.2 la membresia tiene que habilitar SET ROLE (no USAGE: son distintos)
  if not pg_has_role('postgres', 'autonomia_operador', 'SET') then
    raise exception
      'postgres no puede SET ROLE autonomia_operador: la membresia no quedo '
      'con SET TRUE y el operador seria inalcanzable';
  end if;

  -- 5.3 app_backend solo puede LEER
  select string_agg(privilege_type, ',' order by privilege_type) into v_privs
    from information_schema.table_privileges
   where grantee = 'app_backend' and table_schema = 'asistente'
     and table_name = 'interruptor_autonomia';
  if coalesce(v_privs, '(ninguno)') <> 'SELECT' then
    raise exception
      'app_backend quedo con % sobre interruptor_autonomia; debe ser solo SELECT',
      coalesce(v_privs, '(ninguno)');
  end if;

  -- 5.4 el operador puede leer y agregar, y nada mas
  select string_agg(privilege_type, ',' order by privilege_type) into v_privs
    from information_schema.table_privileges
   where grantee = 'autonomia_operador' and table_schema = 'asistente'
     and table_name = 'interruptor_autonomia';
  if coalesce(v_privs, '(ninguno)') <> 'INSERT,SELECT' then
    raise exception
      'autonomia_operador quedo con %; debe ser exactamente INSERT,SELECT',
      coalesce(v_privs, '(ninguno)');
  end if;

  -- 5.5 sigue siendo append-only: nadie mas que el dueno puede UPDATE/DELETE
  select pg_get_userbyid(c.relowner) into v_dueno
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'asistente' and c.relname = 'interruptor_autonomia';
  if exists (select 1 from information_schema.table_privileges
              where table_schema = 'asistente'
                and table_name = 'interruptor_autonomia'
                and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE')
                and grantee <> v_dueno) then
    raise exception
      'alguien quedo con UPDATE/DELETE/TRUNCATE sobre el interruptor: deja de '
      'ser append-only y el historial se vuelve falsificable';
  end if;

  -- 5.6 RLS y FORCE siguen puestas
  if not exists (select 1 from pg_class c
                   join pg_namespace n on n.oid = c.relnamespace
                  where n.nspname = 'asistente'
                    and c.relname = 'interruptor_autonomia'
                    and c.relrowsecurity and c.relforcerowsecurity) then
    raise exception 'la tabla quedo sin RLS o sin FORCE RLS';
  end if;

  -- 5.7 exactamente dos politicas, sin duplicados equivalentes
  if (select count(*) from pg_policies
       where schemaname = 'asistente'
         and tablename = 'interruptor_autonomia') <> 2 then
    raise exception
      'se esperaban exactamente 2 politicas sobre interruptor_autonomia '
      '(tenant_aislado y tenant_aislado_operador)';
  end if;

  -- 5.8 una sola autonomia_detener, con la firma exacta: sin sobrecarga que
  --     acepte el estado por parametro
  if (select count(*) from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
       where n.nspname = 'asistente' and p.proname = 'autonomia_detener') <> 1 then
    raise exception
      'hay mas de una asistente.autonomia_detener: una sobrecarga podria '
      'aceptar el estado por parametro y saltarse la segregacion';
  end if;
  --  Se comparan los TIPOS, no 'pg_get_function_identity_arguments', que
  --  incluye tambien los NOMBRES de los parametros ('p_org uuid, ...'). Lo que
  --  importa aqui es la firma: una sobrecarga que aceptara el estado tendria
  --  otra aridad u otros tipos.
  if not exists (select 1 from pg_proc p
                   join pg_namespace n on n.oid = p.pronamespace
                  where n.nspname = 'asistente' and p.proname = 'autonomia_detener'
                    and array_to_string(p.proargtypes::oid[]::regtype[], ', ')
                        = 'uuid, text, text') then
    raise exception 'asistente.autonomia_detener no tiene la firma (uuid, text, text)';
  end if;

  -- 5.9 SECURITY DEFINER con search_path fijado
  if not exists (select 1 from pg_proc p
                   join pg_namespace n on n.oid = p.pronamespace
                  where n.nspname = 'asistente' and p.proname = 'autonomia_detener'
                    and p.prosecdef
                    and p.proconfig @> array['search_path=pg_catalog']) then
    raise exception
      'autonomia_detener sin SECURITY DEFINER o sin search_path fijado';
  end if;

  -- 5.10 el dueno de la funcion tiene que poder atravesar FORCE RLS, o la
  --      parada de emergencia fallaria recien al llamarla
  if not exists (select 1 from pg_proc p
                   join pg_namespace n on n.oid = p.pronamespace
                   join pg_roles r on r.oid = p.proowner
                  where n.nspname = 'asistente' and p.proname = 'autonomia_detener'
                    and (r.rolsuper or r.rolbypassrls)) then
    raise exception
      'el dueno de autonomia_detener no puede atravesar FORCE RLS: la parada '
      'de emergencia fallaria justo cuando hace falta';
  end if;

  -- 5.11 nadie mas que app_backend y autonomia_operador puede ejecutarla
  if exists (select 1
               from pg_proc p
               join pg_namespace n on n.oid = p.pronamespace,
                    aclexplode(coalesce(p.proacl, '{}'::aclitem[])) a
              where n.nspname = 'asistente' and p.proname = 'autonomia_detener'
                and a.privilege_type = 'EXECUTE'
                and a.grantee <> 0
                and pg_get_userbyid(a.grantee) not in
                    ('app_backend', 'autonomia_operador', pg_get_userbyid(p.proowner))) then
    raise exception 'autonomia_detener quedo ejecutable por un rol no previsto';
  end if;
  if exists (select 1
               from pg_proc p
               join pg_namespace n on n.oid = p.pronamespace,
                    aclexplode(coalesce(p.proacl, '{}'::aclitem[])) a
              where n.nspname = 'asistente' and p.proname = 'autonomia_detener'
                and a.privilege_type = 'EXECUTE' and a.grantee = 0) then
    raise exception 'autonomia_detener quedo ejecutable por PUBLIC';
  end if;
end $$;
