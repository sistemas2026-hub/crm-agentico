-- =============================================================================
--  CERRAR B-7  -  el secreto de firma de JWT deja de estar guardado en la base
-- =============================================================================
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
    if v.setrole = 0 then
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
