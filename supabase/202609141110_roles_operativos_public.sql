-- ============================================================================
-- Roles operativos sobre public: declara en git los permisos que crm_user y
-- motor_user ya tienen en produccion.
-- ============================================================================
--
-- Fecha real de autoria: 15/09/2026. El timestamp del nombre (202609141110) es
-- ORDEN LOGICO: despues de A1 (202609141100) y antes de P2
-- (202609141200_scheduler_persistente.sql).
--
-- POR QUE. crm_user (Django) y motor_user (el motor) son parte del diseño
-- operativo de Dexter desde el 18/08/2026 (DESPLIEGUE.md, "Un rol crm_user
-- para Django"), pero sus permisos se dieron a mano en produccion y git no los
-- declaraba. La comparacion de solo lectura del 15/09/2026 lo mostro en
-- public.organization. Estos son EXACTAMENTE los permisos medidos en
-- produccion despues del hardening de public (foto de ACL de ese dia), sin
-- ampliar nada:
--
--   crm_user    schema public ............ USAGE, CREATE
--   crm_user    tablas de public ......... todos los privilegios de tabla
--   crm_user    secuencias de public ..... USAGE, SELECT, UPDATE
--   crm_user    default privileges de postgres en public: tablas (todos),
--               secuencias (USAGE, SELECT, UPDATE), funciones (EXECUTE)
--   motor_user  public.organization ...... SELECT
--
-- TRES PRERREQUISITOS DEL ENTORNO, NINGUNO DE ESTA MIGRACION.
--   postgres     rol de plataforma de PostgreSQL/Supabase; en produccion es
--                quien crea las tablas, y por eso se declaran SUS default
--                privileges (no los de quien aplique la migracion).
--   crm_user,    roles operativos de Dexter: los crea el despliegue, con su
--   motor_user   LOGIN, sus contraseñas, el BYPASSRLS de motor_user y su
--                membresia en app_backend.
-- Aca no se crea ningun rol ni se toca ningun atributo. Si falta alguno, la
-- primera sentencia que lo nombra falla (SQLSTATE 42704) y el migrador revierte
-- el archivo entero: no queda ningun grant a medias. En clusters de prueba los
-- prepara cli/base_desde_cero.py::preparar_roles_de_despliegue. Sin bloque DO, a proposito: asi la migracion es verificable
-- automaticamente por el manifiesto (schema, acl_tablas, acl_secuencias,
-- default_acl, acl de organization).
--
-- ALL EN LAS DOS SENTENCIAS DE TABLAS, A PROPOSITO. MAINTAIN existe desde
-- PostgreSQL 17; en 16 nombrarlo es un error de sintaxis. ALL resuelve al
-- conjunto de privilegios de tabla que conoce la version del servidor:
-- arwdDxtm en PostgreSQL 17.6 (produccion y referencia; es exactamente lo
-- medido), arwdDxt en 16 (las suites locales). Asi una sola cadena corre en las
-- dos. CONSECUENCIA: ALL sigue al motor. Si una version mayor futura agrega un
-- privilegio de tabla, ALL lo incluiria; ante cualquier cambio de major de
-- PostgreSQL, este grant hay que volver a auditarlo. La huella del servidor en
-- la adopcion bloquea hoy cualquier version distinta de la de referencia.
-- ============================================================================

grant usage, create on schema public to crm_user;

grant all on all tables in schema public to crm_user;

grant usage, select, update
    on all sequences in schema public to crm_user;

alter default privileges for role postgres in schema public
    grant all on tables to crm_user;

alter default privileges for role postgres in schema public
    grant usage, select, update on sequences to crm_user;

alter default privileges for role postgres in schema public
    grant execute on functions to crm_user;

grant select on public.organization to motor_user;
