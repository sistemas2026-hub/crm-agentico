-- =============================================================================
--  CERRAR B-7  -  el secreto de firma de JWT deja de estar guardado en la base
-- =============================================================================
--
--  NO ES UNA MIGRACION DEL LEDGER, Y POR ESO VIVE EN supabase/operador/
--  -------------------------------------------------------------------
--  Borrar un ajuste de la base pide ser su dueño o superusuario, y el rol del
--  ledger probablemente no lo es: fallaria, y migrar_asistente.py se detiene en
--  la primera que falla, asi que TODAS las migraciones siguientes quedarian
--  trabadas (auditoria de frontera, 02/11/2026, B3). Es configuracion del
--  servidor, no esquema: la aplica quien administra el Postgres de Supabase,
--  con psql, como superusuario, y deja constancia en el estado del proyecto.
--
--  BORRAR NO ALCANZA: HAY QUE ROTAR PRIMERO (auditoria, A1)
--  -------------------------------------------------------
--  Esto apaga la compuerta B7_REQUERIDO (nucleo/seguridad/autonomia2.py), pero
--  el secreto que estuvo legible sigue siendo el mismo: quien lo haya leido
--  puede seguir firmando un token 'service_role'. El orden es:
--    1. rotar JWT_SECRET de Supabase y regenerar ANON_KEY y SERVICE_ROLE_KEY;
--    2. aplicar este archivo;
--    3. reiniciar el pooler (Supavisor) y el CRM, para que ninguna sesion
--       abierta conserve el valor viejo.
--  Hasta el paso 3, B-7 no esta cerrado aunque la compuerta diga que si.
--
--  DECIDIDO EL 02/11/2026: se aplica SIN rotar todavia (pasos 2 y 3). Leer el
--  secreto exigia credenciales de la base, que ya dan acceso total sin el;
--  PostgREST esta cerrado en Kong; y el riesgo mayor son las contraseñas de la
--  base filtradas en transcripciones. La rotacion va junto con la de esas
--  contraseñas (DESPLIEGUE.md §3).
--
--  Por que existe (02/11/2026, PRD §8.18)
--  --------------------------------------
--  Supabase autoalojado deja el secreto con que se firman los JWT en un GUC de
--  la base ('app.settings.jwt_secret', puesto con ALTER DATABASE al crearla).
--  Cualquier sesion lo lee con current_setting(), y con el se firma un token
--  'service_role', que tiene BYPASSRLS: el aislamiento entre empresas se
--  recupera por otra via. Ese es el vector B-7.
--
--  Mientras siga ahi, nucleo/seguridad/autonomia2.py frena TODA escritura
--  autonoma y toda irreversible, tambien las que aprueba una persona
--  (frontera.critica): responde B7_REQUERIDO. Es una de las tres llaves por las
--  que "en produccion hoy no cierra nada" (SPEC/objetivos/revision-del-cierre.md,
--  31/10). El objetivo del producto (PRD §1) no se puede cumplir con ella puesta.
--
--  POR QUE SE PUEDE BORRAR
--  -----------------------
--  Los servicios de Supabase reciben el secreto por su entorno (GoTrue,
--  PostgREST, Realtime, Storage), no por este GUC; y Dexter no lo usa: solo
--  mira si ESTA (db.secreto_jwt_en_base, que devuelve la presencia y nunca el
--  valor). INFERIDO de la configuracion de Supabase autoalojado, no medido en
--  este servidor: despues de aplicar, comprobar que el login del CRM y el
--  motor siguen respondiendo. Para volver atras hace falta el valor, que esta
--  en el JWT_SECRET del entorno de Supabase: ALTER DATABASE <base> SET
--  "app.settings.jwt_secret" TO '<valor>'.
--
--  QUE HACE
--  --------
--  Borra el GUC en cada lugar donde este guardado (la base, un rol, o un rol
--  en una base) y despues comprueba que no quede en ninguno. No imprime ni
--  guarda el valor en ningun momento. Las sesiones ya abiertas lo conservan
--  hasta reconectar; las nuevas ya no lo ven.
--
--  PERMISOS
--  --------
--  Borrar un ajuste de una base pide ser su dueño o superusuario. Si el rol del
--  ledger no lo es, falla con "permiso denegado" sin cambiar nada (todo va en
--  un solo bloque): entonces la aplica quien administre el Postgres de
--  Supabase, con este mismo archivo.

do $$
declare
  v record;
begin
  for v in
    select s.setdatabase, s.setrole, d.datname, r.rolname
      from pg_db_role_setting s
      left join pg_database d on d.oid = s.setdatabase
      left join pg_roles r on r.oid = s.setrole
     where exists (select 1 from unnest(s.setconfig) c
                    where c like 'app.settings.jwt_secret=%')
  loop
    if v.setrole = 0 and v.setdatabase = 0 then
      --  ALTER ROLE ALL SET: para todos los roles, en todas las bases.
      execute 'alter role all reset "app.settings.jwt_secret"';
    elsif v.setrole = 0 then
      execute format('alter database %I reset "app.settings.jwt_secret"', v.datname);
    elsif v.setdatabase = 0 then
      execute format('alter role %I reset "app.settings.jwt_secret"', v.rolname);
    else
      execute format('alter role %I in database %I reset "app.settings.jwt_secret"',
                     v.rolname, v.datname);
    end if;
  end loop;

  if exists (select 1 from pg_db_role_setting s
              where exists (select 1 from unnest(s.setconfig) c
                             where c like 'app.settings.jwt_secret=%')) then
    raise exception 'B-7: el secreto de firma de JWT sigue guardado en la base';
  end if;
end $$;
