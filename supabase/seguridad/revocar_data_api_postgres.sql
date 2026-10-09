-- ============================================================================
-- Revocar a anon y authenticated lo que la plantilla de Supabase les da sobre
-- el schema public. PARTE 1 de 2: lo que es de 'postgres'.
-- ============================================================================
--
-- POR QUE. Dexter no usa la Data API de Supabase (PostgREST / GraphQL /
-- Realtime): el CRM entra por Django y el motor por psycopg. Pero los default
-- privileges de la imagen le dan a anon y authenticated CRUD sobre todo lo que
-- 'postgres' crea en public, y el 15/09/2026 eso estaba publicado por HTTP.
-- La ruta se cerro en Kong (DESPLIEGUE.md 4.b.1); esto cierra el permiso, para
-- que una ruta reabierta no vuelva a dar acceso.
--
-- QUE HACE, como postgres:
--   1. REVOKE ALL a anon/authenticated sobre tablas, vistas y secuencias de public.
--   2. REVOKE EXECUTE directo sobre funciones de public que son de postgres y
--      NO pertenecen a una extension (las de extension las ve la parte 2).
--   3. REVOKE del USAGE directo de anon/authenticated sobre el schema public.
--   4. ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public: que lo que
--      postgres cree despues no vuelva a concederles nada.
--
-- QUE NO TOCA, a proposito: service_role, crm_user, motor_user, app_backend,
-- PUBLIC (ni sobre funciones ni sobre el schema), los demas schemas (storage,
-- graphql, auth...) y los default privileges de otros roles.
--
-- LIMITE QUE HAY QUE SABER: PUBLIC tiene USAGE sobre public
-- (=U/pg_database_owner). Quitar el USAGE directo no le quita a anon el USAGE
-- efectivo. Lo que lo deja sin acceso es el paso 1: sin privilegios sobre las
-- relaciones, el USAGE solo sirve para resolver nombres. Las postcondiciones
-- miden el efecto (has_table_privilege), no la presencia del grant.
--
-- Atomico: una transaccion. Si una postcondicion falla, no queda nada aplicado.
-- Idempotente: correrlo dos veces deja lo mismo.
-- ============================================================================

begin;

do $$
begin
    if session_user <> 'postgres' or current_user <> 'postgres' then
        raise exception 'revocar_data_api_postgres.sql debe correr como postgres (session_user=%, current_user=%)',
            session_user, current_user;
    end if;
end
$$;

-- Foto de TODO lo que no es anon/authenticated, para exigir al final que no cambio.
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

-- 1. Relaciones existentes.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- 2. Funciones de postgres que no son de una extension.
do $$
declare
    f regprocedure;
begin
    for f in
        select p.oid::regprocedure
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proowner = 'postgres'::regrole
          and not exists (select 1 from pg_depend d
                          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e')
    loop
        execute format('revoke all on function %s from anon, authenticated', f);
    end loop;
end
$$;

-- 3. USAGE directo sobre el schema.
revoke usage on schema public from anon, authenticated;

-- 4. Lo que postgres cree despues.
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;

-- POSTCONDICIONES. Sin EXCEPTION: si algo no quedo, aborta la transaccion entera.
do $$
declare
    malas text;
begin
    -- a) Efecto: ningun privilegio efectivo sobre relaciones de public.
    select string_agg(format('%s:%s', r.rol, c.oid::regclass), ', ') into malas
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    cross join (values ('anon'), ('authenticated')) r(rol)
    where n.nspname = 'public'
      and ((c.relkind in ('r', 'v', 'm', 'p', 'f')
            and has_table_privilege(r.rol, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN'))
        or (c.relkind = 'S' and has_sequence_privilege(r.rol, c.oid, 'USAGE,SELECT,UPDATE')));
    if malas is not null then
        raise exception 'revocar_data_api: anon/authenticated conservan privilegios efectivos sobre: %', left(malas, 1500)
            using hint = 'Una relacion que no es de postgres no se puede revocar desde aca: correr la parte 2 o revisar el owner.';
    end if;

    -- b) Ninguna entrada directa en funciones de postgres que no son de extension.
    select string_agg(p.oid::regprocedure::text, ', ') into malas
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    cross join lateral aclexplode(p.proacl) a
    where n.nspname = 'public' and p.proowner = 'postgres'::regrole
      and not exists (select 1 from pg_depend d
                      where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e')
      and a.grantee in ('anon'::regrole, 'authenticated'::regrole);
    if malas is not null then
        raise exception 'revocar_data_api: EXECUTE directo de anon/authenticated sigue en: %', left(malas, 1500);
    end if;

    -- c) Sin USAGE directo sobre el schema.
    if exists (select 1 from pg_namespace n cross join lateral aclexplode(n.nspacl) a
               where n.nspname = 'public' and a.grantee in ('anon'::regrole, 'authenticated'::regrole)) then
        raise exception 'revocar_data_api: anon/authenticated conservan USAGE directo sobre public'
            using hint = 'El grantor es pg_database_owner: postgres tiene que ser dueno de la base, o esto va en la parte 2.';
    end if;

    -- d) Los default privileges de postgres en public ya no los nombran.
    if exists (select 1 from pg_default_acl d cross join lateral aclexplode(d.defaclacl) a
               where d.defaclrole = 'postgres'::regrole and d.defaclnamespace = 'public'::regnamespace
                 and a.grantee in ('anon'::regrole, 'authenticated'::regrole)) then
        raise exception 'revocar_data_api: los default privileges de postgres en public siguen concediendo a anon/authenticated';
    end if;

    -- e) Nada mas cambio.
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
