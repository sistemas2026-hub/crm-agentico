-- ============================================================================
-- Revocar a anon y authenticated lo que la plantilla de Supabase les da sobre
-- el schema public. PARTE 2 de 2: lo que 'postgres' no puede tocar.
-- ============================================================================
--
-- Correr DESPUES de revocar_data_api_postgres.sql, como supabase_admin (el
-- superusuario de la imagen). Motivo, medido el 15/09/2026 sobre la imagen
-- exacta de produccion (supabase/postgres 17.6.1.136, por digest):
--
--   * supabase_admin tiene default privileges en public que conceden
--     arwdDxtm / rwU / X a anon y authenticated. Lo que ese rol cree en public
--     (una extension nueva, una migracion de la plataforma) vuelve a quedar
--     expuesto. 'postgres' no es miembro de supabase_admin: no puede
--     cambiarlos.
--   * Las funciones de public son todas de extensiones (vector, pg_trgm) y su
--     owner es supabase_admin: el EXECUTE directo a anon/authenticated lo
--     concedio supabase_admin y solo el puede quitarlo.
--
-- QUE HACE: repite, como superusuario, el REVOKE sobre relaciones, funciones y
-- USAGE directo del schema (idempotente; alcanza tambien objetos que no son de
-- postgres) y quita a anon/authenticated de los default privileges de
-- supabase_admin en public.
--
-- LO QUE NO CAMBIA, y hay que decirlo: PUBLIC conserva EXECUTE sobre esas
-- funciones de extension y USAGE sobre el schema. anon las sigue pudiendo
-- ejecutar a traves de PUBLIC. Son funciones de calculo (distancias
-- vectoriales, trigramas) que no leen tablas; quitarle eso a PUBLIC afecta a
-- todos los roles y es otra decision.
--
-- QUE NO TOCA: service_role, crm_user, motor_user, app_backend, PUBLIC, los
-- demas schemas (storage, graphql, graphql_public, auth...) ni los default
-- privileges de supabase_admin FUERA de public.
-- ============================================================================

begin;

do $$
begin
    if session_user <> 'supabase_admin' or current_user <> 'supabase_admin' then
        raise exception 'revocar_data_api_supabase_admin.sql debe correr como supabase_admin (session_user=%, current_user=%)',
            session_user, current_user;
    end if;
end
$$;

create temp table _acl_antes on commit drop as
select 'relacion'::text as tipo, c.oid::regclass::text as objeto, a.grantor, a.grantee, a.privilege_type, a.is_grantable
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 's' else 'r' end)::"char", c.relowner))) a
where n.nspname = 'public' and c.relkind in ('r', 'v', 'm', 'p', 'f', 'S')
  and a.grantee not in ('anon'::regrole, 'authenticated'::regrole)
union all
select 'funcion', p.oid::regprocedure::text, a.grantor, a.grantee, a.privilege_type, a.is_grantable
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
where n.nspname = 'public'
  and a.grantee not in ('anon'::regrole, 'authenticated'::regrole)
union all
select 'schema', n.nspname, a.grantor, a.grantee, a.privilege_type, a.is_grantable
from pg_namespace n
cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
where n.nspname = 'public'
  and a.grantee not in ('anon'::regrole, 'authenticated'::regrole)
union all
select 'default_acl:' || pg_get_userbyid(d.defaclrole) || ':' || d.defaclobjtype::text, coalesce(n.nspname, '(global)'),
       a.grantor, a.grantee, a.privilege_type, a.is_grantable
from pg_default_acl d
left join pg_namespace n on n.oid = d.defaclnamespace
cross join lateral aclexplode(d.defaclacl) a
where a.grantee not in ('anon'::regrole, 'authenticated'::regrole);

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
revoke usage on schema public from anon, authenticated;

alter default privileges for role supabase_admin in schema public revoke all on tables from anon, authenticated;
alter default privileges for role supabase_admin in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role supabase_admin in schema public revoke all on functions from anon, authenticated;

do $$
declare
    malas text;
begin
    select string_agg(format('%s:%s', r.rol, c.oid::regclass), ', ') into malas
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    cross join (values ('anon'), ('authenticated')) r(rol)
    where n.nspname = 'public'
      and ((c.relkind in ('r', 'v', 'm', 'p', 'f')
            and has_table_privilege(r.rol, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN'))
        or (c.relkind = 'S' and has_sequence_privilege(r.rol, c.oid, 'USAGE,SELECT,UPDATE')));
    if malas is not null then
        raise exception 'revocar_data_api: anon/authenticated conservan privilegios efectivos sobre: %', left(malas, 1500);
    end if;

    select string_agg(p.oid::regprocedure::text, ', ') into malas
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    cross join lateral aclexplode(p.proacl) a
    where n.nspname = 'public' and a.grantee in ('anon'::regrole, 'authenticated'::regrole);
    if malas is not null then
        raise exception 'revocar_data_api: EXECUTE directo de anon/authenticated sigue en: %', left(malas, 1500);
    end if;

    if exists (select 1 from pg_namespace n cross join lateral aclexplode(n.nspacl) a
               where n.nspname = 'public' and a.grantee in ('anon'::regrole, 'authenticated'::regrole)) then
        raise exception 'revocar_data_api: anon/authenticated conservan USAGE directo sobre public';
    end if;

    if exists (select 1 from pg_default_acl d cross join lateral aclexplode(d.defaclacl) a
               where d.defaclrole in ('postgres'::regrole, 'supabase_admin'::regrole)
                 and d.defaclnamespace = 'public'::regnamespace
                 and a.grantee in ('anon'::regrole, 'authenticated'::regrole)) then
        raise exception 'revocar_data_api: default privileges de postgres o supabase_admin en public siguen concediendo a anon/authenticated'
            using hint = 'Si es el de postgres, falta correr antes revocar_data_api_postgres.sql.';
    end if;

    select string_agg(format('%s %s %s->%s %s', x.tipo, x.objeto, pg_get_userbyid(x.grantor), pg_get_userbyid(x.grantee),
                             x.privilege_type), '; ') into malas
    from (
        -- Los parentesis importan: EXCEPT y UNION ALL tienen la misma precedencia y
        -- asocian a izquierda. Sin ellos, "A except B union all C" suma C entero.
        select * from _acl_antes
        except
        (select 'relacion'::text, c.oid::regclass::text, a.grantor, a.grantee, a.privilege_type, a.is_grantable
         from pg_class c
         join pg_namespace n on n.oid = c.relnamespace
         cross join lateral aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 's' else 'r' end)::"char", c.relowner))) a
         where n.nspname = 'public' and c.relkind in ('r', 'v', 'm', 'p', 'f', 'S')
         union all
         select 'funcion', p.oid::regprocedure::text, a.grantor, a.grantee, a.privilege_type, a.is_grantable
         from pg_proc p
         join pg_namespace n on n.oid = p.pronamespace
         cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
         where n.nspname = 'public'
         union all
         select 'schema', n.nspname, a.grantor, a.grantee, a.privilege_type, a.is_grantable
         from pg_namespace n
         cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
         where n.nspname = 'public'
         union all
         select 'default_acl:' || pg_get_userbyid(d.defaclrole) || ':' || d.defaclobjtype::text, coalesce(n.nspname, '(global)'),
                a.grantor, a.grantee, a.privilege_type, a.is_grantable
         from pg_default_acl d
         left join pg_namespace n on n.oid = d.defaclnamespace
         cross join lateral aclexplode(d.defaclacl) a)
    ) x;
    if malas is not null then
        raise exception 'revocar_data_api: cambio un privilegio que no era de anon/authenticated: %', left(malas, 1500);
    end if;
end
$$;

commit;
