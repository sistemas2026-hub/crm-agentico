-- =============================================================================
--  LOS USUARIOS DE CONEXION DEL SCHEDULER  --  declarativo, sin secretos
-- =============================================================================
--
--  Vive en 'supabase/roles/', FUERA de la cadena 'supabase/*.sql': crea roles
--  de login, que son del cluster y no de la base, y se aplica en el paso de
--  aprovisionamiento de P5, no con cada migracion.
--
--  Los cuatro roles de 'scheduler_funciones' son NOLOGIN: son roles de ACCESO.
--  Aca estan los que se CONECTAN, uno por proceso:
--
--      scheduler_login  -> scheduler_coordinator
--      executor_login   -> job_executor
--      monitor_login    -> monitor_ro
--
--  Reglas, y por que cada una:
--
--    * UNA sola membresia funcional por login. Si el login del coordinador
--      pudiera asumir job_executor, la separacion de roles seria decorativa:
--      el mismo proceso podria reclamar y finalizar.
--    * INHERIT FALSE en la membresia y NOINHERIT en el rol. El login solo, sin
--      'set role', no puede ejecutar nada. Tiene que asumir su rol a
--      proposito, que es lo que ya hace 'puerta.sesion'.
--    * SET TRUE, ADMIN FALSE. Puede asumir su rol; no puede otorgarlo.
--    * NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE, NOREPLICATION.
--      Declarado aunque sea el valor por defecto: este archivo CONVERGE un rol
--      que ya exista con otros atributos, no solo crea uno nuevo.
--    * Cualquier OTRA membresia que tenga el login se revoca. Declarativo
--      quiere decir que el resultado es este, no "agregar esto a lo que haya".
--    * SIN CONTRASEÑA. El secreto no va al repositorio. El aprovisionamiento
--      la fija desde el gestor de secretos del despliegue con
--          alter role scheduler_login password '<desde el gestor>';
--      Un login sin contraseña no puede autenticarse con scram-sha-256, asi
--      que aplicar este archivo solo no abre ninguna puerta.
--
--  NUNCA 'motor'. 'motor' es SUPERUSER + BYPASSRLS en el entorno medido: un
--  proceso conectado como motor puede 'reset role' despues de cualquier
--  'set role' y leer las tablas job_* directamente. Todas las ACL probadas
--  serian irrelevantes. Medido en tests/test_roles_de_conexion.py.
-- =============================================================================

do $$
declare
  par   record;
  otra  record;
begin
  for par in
    select * from (values
      ('scheduler_login', 'scheduler_coordinator'),
      ('executor_login',  'job_executor'),
      ('monitor_login',   'monitor_ro')
    ) as v(login, rol)
  loop
    if not exists (select 1 from pg_roles where rolname = par.rol) then
      raise exception 'falta el rol de acceso %: aplicar antes 202609141300_scheduler_funciones.sql',
                      par.rol;
    end if;

    if not exists (select 1 from pg_roles where rolname = par.login) then
      execute format('create role %I login noinherit nosuperuser nobypassrls '
                     'nocreatedb nocreaterole noreplication connection limit 20',
                     par.login);
    else
      execute format('alter role %I login noinherit nosuperuser nobypassrls '
                     'nocreatedb nocreaterole noreplication connection limit 20',
                     par.login);
    end if;

    -- converger: fuera toda membresia que no sea la suya
    for otra in
      select g.rolname
        from pg_auth_members a
        join pg_roles g on g.oid = a.roleid
        join pg_roles m on m.oid = a.member
       where m.rolname = par.login
         and g.rolname <> par.rol
    loop
      execute format('revoke %I from %I', otra.rolname, par.login);
    end loop;

    execute format('grant %I to %I with admin false, inherit false, set true',
                   par.rol, par.login);
  end loop;
end $$;
