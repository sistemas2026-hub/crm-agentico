-- =============================================================================
--  ESTE SCRIPT NO ADOPTA NI MODIFICA NADA.
-- =============================================================================
--  Inspeccion de SOLO LECTURA de la base objetivo, antes de decidir una
--  adopcion. No es una migracion: vive fuera de 'supabase/*.sql', el migrador no
--  lo lee y el aviso de post-merge no lo cuenta.
--
--  Solo SELECT sobre catalogo y conteos agregados. Ningun resultado identifica
--  una conversacion, un cliente ni un ticket, y no lee parametros que puedan
--  guardar secretos.
--
--  Correr con psql, sin psqlrc, con la sesion en solo lectura desde afuera
--  (PGOPTIONS) y desde adentro (SET SESSION CHARACTERISTICS, abajo):
--
--    PGOPTIONS='-c default_transaction_read_only=on' psql -X -h <host> -U <rol> -d <base> -f supabase/ledger/analisis/inspeccion_solo_lectura.sql
--
--  La clave va por PGPASSWORD o .pgpass, nunca en la linea de comandos.
--
--  Para citar esta inspeccion en una decision: el commit y el git blob del
--  archivo (git rev-parse <commit>:supabase/ledger/analisis/inspeccion_solo_lectura.sql)
--  en el --motivo de la aceptacion.
--
--  Cada consulta corre en su propia transaccion: si falta un objeto, falla solo
--  esa consulta y el resto sigue (la falta ES la respuesta).
--
--  Probado por tests/test_inspeccion_solo_lectura.py.
-- =============================================================================

\set ON_ERROR_STOP on
set session characteristics as transaction read only;
set statement_timeout = '30s';
set lock_timeout = '1s';

-- Fail-closed: si la sesion no quedo en solo lectura, no se consulta nada.
select current_setting('default_transaction_read_only') = 'on' as solo_lectura \gset
\if :solo_lectura
\else
  \echo 'LA SESION NO ESTA EN SOLO LECTURA. No se consulta nada.'
  \quit
\endif
\set ON_ERROR_STOP off

\echo '== 0. contexto'
select current_database() as base, session_user as rol_sesion,
       current_setting('transaction_read_only') as transaccion_solo_lectura;
-- La zona horaria por defecto (tomar_caso uso ::date con la de la sesion).
-- Solo TimeZone: pg_db_role_setting puede guardar secretos en otros parametros.
select name, setting, source from pg_settings where name = 'TimeZone';
select coalesce(r.rolname, '<todos los roles>') as rol, c as ajuste
  from pg_db_role_setting s
  left join pg_roles r on r.oid = s.setrole
  cross join lateral unnest(s.setconfig) c
 where s.setdatabase in (0, (select oid from pg_database where datname = current_database()))
   and c ilike 'timezone=%';

\echo '== 1. huella (compuerta del manifiesto)'
select current_setting('server_version_num')::int as server_version_num,
       current_setting('server_version_num')::int / 10000 as major,
       current_setting('server_version') as server_version;
select e.extname, e.extversion, n.nspname as schema
  from pg_extension e join pg_namespace n on n.oid = e.extnamespace
 where e.extname <> 'plpgsql' order by 1;

\echo '== 2. que existe'
select to_regnamespace('asistente') is not null as schema_asistente,
       to_regclass('asistente.migraciones_aplicadas') is not null as ledger,
       to_regclass('asistente.migraciones_ledger_esquema') is not null as ledger_esquema,
       to_regnamespace('ext') is not null as schema_ext_para_p2,
       (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'asistente' and c.relkind in ('r', 'p')) as tablas_en_asistente;

-- Columnas que tocan las siete (su falta vuelve inutil la consulta de datos).
select v.tabla, v.columna, a.attnum is not null as existe,
       pg_get_expr(d.adbin, d.adrelid) as valor_por_defecto
  from (values ('document_chunks', 'modelo_embeddings'),
               ('unanswered_queries', 'chunks_elegibles'),
               ('tool_calls', 'es_bloqueo'),
               ('conversations', 'escalada_en'),
               ('conversations', 'escalada_no_comprobado'),
               ('conversations', 'escalada_siguiente_paso'),
               ('conversations', 'necesita_atencion_humana'),
               ('conversations', 'estado_escalada'),
               ('conversations', 'tomada_por'),
               ('conversations', 'tomada_en')) v(tabla, columna)
  left join pg_attribute a on a.attrelid = to_regclass('asistente.' || v.tabla)
                          and a.attname = v.columna and not a.attisdropped
  left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
 order by 1, 2;

select o as objeto, to_regclass(o) is not null as existe
  from unnest(array['asistente.tool_calls_bloqueo_idx', 'asistente.conversations_espera_idx',
                    'asistente.conversations_tomada_idx', 'asistente.tenant_config_historial']) o;

\echo '== 3. schema.sql -- DO 2 y DO 3, por tabla (una fila por tabla esperada, exista o no)'
select t.tabla, c.oid is not null as existe, c.relrowsecurity as rls, c.relforcerowsecurity as rls_forzada,
       array(select a.privilege_type from aclexplode(c.relacl) a
               join pg_roles r on r.oid = a.grantee
              where r.rolname = 'app_backend' order by 1) as privilegios_app_backend,
       (select count(*) from pg_policies p where p.schemaname = 'asistente'
           and p.tablename = t.tabla and p.policyname = 'tenant_aislado') as tenant_aislado
  from unnest(array['tenant_config', 'tenant_users', 'documents', 'document_chunks', 'conversations',
                    'messages', 'tool_calls', 'unanswered_queries', 'evaluation_sets',
                    'evaluation_runs', 'usage_daily', 'audit_log']) t(tabla)
  left join pg_class c on c.oid = to_regclass('asistente.' || t.tabla)
 order by 1;

\echo '== 4. app_backend y roles -- USAGE, atributos, membresias en las dos direcciones, EXECUTE'
-- USAGE sobre el schema: sin el, un EXECUTE de PUBLIC no alcanza a nadie.
select case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end as rol,
       a.privilege_type
  from pg_namespace n
  cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
 where n.nspname = 'asistente'
 order by 1, 2;
select rolname, rolcanlogin, rolsuper, rolinherit, rolbypassrls, rolcreaterole
  from pg_roles where rolname = 'app_backend';
select g.rolname as rol, m.rolname as miembro, a.admin_option,
       m.rolcanlogin as miembro_puede_entrar, m.rolsuper as miembro_superusuario,
       pg_get_userbyid(a.grantor) as otorgado_por
  from pg_auth_members a
  join pg_roles g on g.oid = a.roleid
  join pg_roles m on m.oid = a.member
 where 'app_backend' in (g.rolname, m.rolname)
 order by 1, 2;

-- Toda funcion de asistente: quien la ejecuta (PUBLIC incluido) y si es SECURITY DEFINER.
-- Cubre match_chunks (cuantas sobrecargas), match_chunks_hibrido y el comodin.
select p.proname, pg_get_function_identity_arguments(p.oid) as argumentos,
       p.prosecdef as security_definer, pg_get_userbyid(p.proowner) as dueno,
       array(select case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end
               from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
              where a.privilege_type = 'EXECUTE' order by 1) as execute_para
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'asistente'
 order by 1, 2;

-- Privilegios por defecto: si existen, el comodin no fue de una sola vez.
select pg_get_userbyid(d.defaclrole) as rol, d.defaclobjtype as tipo, d.defaclacl::text as acl,
       d.defaclnamespace = 0 as global
  from pg_default_acl d
 where d.defaclnamespace in (0, coalesce(to_regnamespace('asistente')::oid, 0));

\echo '== 5. diagnostico_recuperacion -- STOP si aparece bge-m3'
select coalesce(modelo_embeddings, '<null>') as modelo, count(*) as fragmentos
  from asistente.document_chunks group by 1 order by 2 desc;

\echo '== 6. bloqueos_en_traza'
select count(*) filter (where not es_bloqueo and codigo_error in
         ('IDENTIDAD_NO_VERIFICADA', 'PRECONDICION_NO_CUMPLIDA', 'FALTA_HABLAR_CON_EL_CLIENTE',
          'IDENTIDAD_NO_RESUELTA', 'HERRAMIENTA_DESCONOCIDA', 'LIMITE_DE_CONVERSACION'))
         as bloqueos_sin_marcar,
       count(*) filter (where es_bloqueo) as marcadas
  from asistente.tool_calls;

\echo '== 7. cola_priorizada -- STOP si escaladas_sin_fecha > 0'
select count(*) filter (where escalada_a_humano and escalada_en is null) as escaladas_sin_fecha,
       count(*) filter (where escalada_a_humano) as escaladas
  from asistente.conversations;

\echo '== 8. bandeja_sin_inflar -- esperado: default false y md5 de6e587325b1a623f37a96f98f689911'
select md5(col_description('asistente.conversations'::regclass, a.attnum)) as md5_comentario
  from pg_attribute a
 where a.attrelid = 'asistente.conversations'::regclass
   and a.attname = 'necesita_atencion_humana';
select count(*) filter (where necesita_atencion_humana and not escalada_a_humano
                          and coalesce(estado_escalada, '') <> 'NO_DETERMINADO') as marcadas_fuera_de_regla,
       count(*) filter (where necesita_atencion_humana) as marcadas,
       count(*) as total
  from asistente.conversations;

\echo '== 9. tomar_caso -- mide exposicion y rastro, NO prueba que corrio'
select count(*) filter (where (actualizado_en at time zone 'UTC')::date = date '2026-09-07') as expuestas_si_utc,
       count(*) filter (where (actualizado_en at time zone 'America/Bogota')::date = date '2026-09-07') as expuestas_si_bogota
  from asistente.conversations
 where atendida_manual and atendida_por is not null and estado <> 'cerrada';
select count(*) as tomadas_el_07_09_bogota
  from asistente.conversations
 where tomada_por is not null
   and (tomada_en at time zone 'America/Bogota')::date = date '2026-09-07';

\echo '== 10. historial_de_config'
select count(*) filter (where h.organization_id is null) as vigentes_sin_historial,
       count(*) as tenants
  from asistente.tenant_config tc
  left join asistente.tenant_config_historial h
    on h.organization_id = tc.organization_id and h.config_version = tc.config_version;

\echo '== fin: no se escribio nada'
