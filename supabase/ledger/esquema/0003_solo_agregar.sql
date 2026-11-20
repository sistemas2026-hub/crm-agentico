-- =============================================================================
--  ESQUEMA DEL LEDGER  --  version 3: solo agregar
-- =============================================================================
--
--  Ningun camino del migrador ni de la adopcion hace UPDATE, DELETE ni TRUNCATE
--  sobre filas del ledger: solo INSERT (auditado en
--  supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md). Este paso lo vuelve una
--  regla de la base, para que un error operativo --un UPDATE a mano, un
--  'delete' de limpieza-- no reescriba en silencio lo que paso.
--
--  NO es una proteccion contra el owner ni un superusuario: pueden desactivar
--  el trigger o borrar la tabla. Corregir el ledger queda como un acto
--  deliberado y visible, fuera del migrador.
--
--  La funcion vive en su propio schema y no en 'asistente': el manifiesto de
--  adopcion compara los grants de TODAS las funciones de 'asistente', y una
--  funcion nueva ahi haria no equivalente a cualquier base adoptada.
--
--  Los pasos futuros del esquema son DDL (ALTER TABLE), que no dispara estos
--  triggers.
-- =============================================================================

create schema if not exists asistente_ledger;
revoke all on schema asistente_ledger from public;

create or replace function asistente_ledger.solo_agregar() returns trigger
  language plpgsql
  set search_path = pg_catalog
as $$
begin
  raise exception using
    errcode = 'LG002',
    message = format('%I.%I es de solo agregar: %s no esta permitido',
                     tg_table_schema, tg_table_name, tg_op),
    hint = 'El ledger registra lo que paso. Corregirlo es un acto deliberado del '
           'owner, fuera del migrador: supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md';
end
$$;

revoke all on function asistente_ledger.solo_agregar() from public;

create trigger ma_solo_agregar
  before update or delete on asistente.migraciones_aplicadas
  for each row execute function asistente_ledger.solo_agregar();
create trigger ma_sin_truncate
  before truncate on asistente.migraciones_aplicadas
  for each statement execute function asistente_ledger.solo_agregar();

create trigger mle_solo_agregar
  before update or delete on asistente.migraciones_ledger_esquema
  for each row execute function asistente_ledger.solo_agregar();
create trigger mle_sin_truncate
  before truncate on asistente.migraciones_ledger_esquema
  for each statement execute function asistente_ledger.solo_agregar();
