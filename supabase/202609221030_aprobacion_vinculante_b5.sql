-- ============================================================================
--  APROBACION VINCULANTE SOBRE EL CICLO B5  (M06-A + M06-C, integrados en M06-F)
--  22/09/2026. Va DESPUES de 202609201800_acciones_b5.sql (origin).
-- ============================================================================
--
--  QUE HACE
--  --------
--  Ata la aprobacion humana de una accion IRREVERSIBLE (R3/R4 y las
--  excepciones de M06-E) a la operacion exacta, SIN crear una segunda maquina
--  de aprobacion. El ciclo sigue siendo el de B5 (acciones_b5.sql):
--
--      pendiente --reservar--> ejecutando --resolver--> ejecutada_ok
--                                                       ejecutada_fallo
--                                                       desconocida
--      pendiente --> vencida | cancelada | rechazada
--      ejecutando --liberar--> pendiente        (no se pudo revalidar)
--      ejecutando --> vencida                   (revalidacion o guarda: NO)
--
--  Lo que se AGREGA son cuatro columnas y un trigger:
--
--    hash_argumentos   huella de los argumentos RESUELTOS, calculada al
--                      proponer (idempotencia.hash_de). Su presencia es lo que
--                      marca una fila como VINCULANTE; las demas siguen
--                      exactamente como en B5.
--    origen            la solicitud que pidio la accion (wamid, run_id,
--                      'bandeja:<conversacion>:<uuid>'...).
--    contexto          lo minimo para volver a medir las precondiciones al
--                      aprobar: identificadores tecnicos y argumentos de las
--                      previas. Sin ficha del cliente, sin respuestas crudas.
--    sello_aprobacion  hash de tenant + organizacion + herramienta + origen +
--                      huella + aprobador (nucleo/seguridad/aprobacion.py::
--                      sello_de). Lo escribe db.reservar_accion en la MISMA
--                      escritura que pasa la fila a 'ejecutando': reservar ES
--                      aprobar en B5. Se recalcula al ejecutar.
--
--  conversation_id NO se agrega: B5 ya la trae. La version anterior de esta
--  migracion (202609211800, nunca aplicada) la agregaba, y habrian quedado dos
--  columnas para lo mismo.
--
--  EL TRIGGER
--  ----------
--  Una sola funcion para INSERT y UPDATE. Reemplaza a las dos versiones de
--  'acciones_propuestas_inmutable' de 202609211800 y 202609212000 (ninguna
--  aplicada en ningun entorno):
--
--    a TODA fila   la identidad de una propuesta no se edita (organizacion,
--                  herramienta, argumentos, huella, origen, contexto, quien la
--                  propuso, cuando). La conversacion se fija una sola vez;
--                  soltarla (NULL, lo que hace ON DELETE SET NULL al borrar la
--                  conversacion) se permite, porque la vuelve legado y el
--                  legado no se aprueba.
--    a la fila     nace 'pendiente' y sin sello; el sello solo se escribe al
--    VINCULANTE    reservar, y con aprobador y momento; liberar lo borra;
--                  despues nada lo reescribe, ni al aprobador; un desenlace no
--                  se reescribe; y las transiciones son solo las de B5.
--
--  Una fila comun (sin huella) no gana ninguna regla nueva salvo la identidad,
--  que B5 ya respeta: ningun UPDATE del codigo de origin toca esos campos.
--
--  NO SE APLICA EN ESTE BLOQUE.
-- ============================================================================

alter table asistente.acciones_propuestas
  add column if not exists hash_argumentos  text,
  add column if not exists origen           text,
  add column if not exists contexto         jsonb,
  add column if not exists sello_aprobacion text;

-- Las columnas nacen NULL en todas las filas existentes, asi que las dos
-- condiciones se cumplen ya y pueden validarse.
alter table asistente.acciones_propuestas
  drop constraint if exists acciones_propuestas_sello_solo_vinculante;
alter table asistente.acciones_propuestas
  add constraint acciones_propuestas_sello_solo_vinculante
  check (sello_aprobacion is null or hash_argumentos is not null);

alter table asistente.acciones_propuestas
  drop constraint if exists acciones_propuestas_vinculante_con_origen;
alter table asistente.acciones_propuestas
  add constraint acciones_propuestas_vinculante_con_origen
  check (hash_argumentos is null or btrim(coalesce(origen, '')) <> '');


create or replace function asistente.acciones_propuestas_vinculante()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' then
    if new.sello_aprobacion is not null then
      raise exception 'acciones_propuestas: una propuesta nace sin sello'
        using errcode = 'check_violation';
    end if;
    if new.hash_argumentos is not null and new.estado <> 'pendiente' then
      raise exception 'acciones_propuestas: una propuesta vinculante nace pendiente'
        using errcode = 'check_violation';
    end if;
    return new;
  end if;

  -- La identidad de CUALQUIER propuesta.
  if new.organization_id    is distinct from old.organization_id
     or new.herramienta     is distinct from old.herramienta
     or new.argumentos      is distinct from old.argumentos
     or new.hash_argumentos is distinct from old.hash_argumentos
     or new.origen          is distinct from old.origen
     or new.contexto        is distinct from old.contexto
     or new.propuesto_por   is distinct from old.propuesto_por
     or new.creado_en       is distinct from old.creado_en then
    raise exception 'acciones_propuestas: la identidad de una propuesta no se edita (id %)', old.id
      using errcode = 'check_violation';
  end if;
  if old.conversation_id is not null and new.conversation_id is not null
     and new.conversation_id is distinct from old.conversation_id then
    raise exception 'acciones_propuestas: la propuesta % ya tiene conversacion', old.id
      using errcode = 'check_violation';
  end if;

  -- Las comunes siguen el ciclo B5 sin mas reglas.
  if old.hash_argumentos is null then
    return new;
  end if;

  -- Liberar (B5 §9.3 paso 2): la reserva se deshace, y el sello con ella. Lo
  -- borra el trigger y no el codigo, para que ninguna via de liberar pueda
  -- dejar una fila 'pendiente' con el sello de alguien.
  if old.estado = 'ejecutando' and new.estado = 'pendiente' then
    new.sello_aprobacion := null;
    return new;
  end if;

  -- Reservar = aprobar: con aprobador, momento y sello, o no.
  if old.estado = 'pendiente' and new.estado = 'ejecutando' then
    if new.sello_aprobacion is null
       or btrim(coalesce(new.revisado_por, '')) = ''
       or new.revisado_en is null then
      raise exception 'acciones_propuestas: aprobar % exige aprobador, momento y sello', old.id
        using errcode = 'check_violation';
    end if;
    return new;
  end if;

  if new.sello_aprobacion is distinct from old.sello_aprobacion then
    raise exception 'acciones_propuestas: el sello de % solo se escribe al aprobar', old.id
      using errcode = 'check_violation';
  end if;
  if old.estado <> 'pendiente' and new.revisado_por is distinct from old.revisado_por then
    raise exception 'acciones_propuestas: quien aprobo % no se reescribe', old.id
      using errcode = 'check_violation';
  end if;
  if old.estado not in ('pendiente', 'ejecutando')
     and new.estado is distinct from old.estado then
    raise exception 'acciones_propuestas: % ya esta % y no se reescribe', old.id, old.estado
      using errcode = 'check_violation';
  end if;
  if old.estado = 'ejecutando'
     and new.estado not in ('ejecutando', 'ejecutada_ok', 'ejecutada_fallo',
                            'desconocida', 'vencida') then
    raise exception 'acciones_propuestas: % no puede pasar de ejecutando a %', old.id, new.estado
      using errcode = 'check_violation';
  end if;
  if old.estado = 'pendiente'
     and new.estado not in ('pendiente', 'vencida', 'cancelada', 'rechazada') then
    raise exception 'acciones_propuestas: % no puede pasar de pendiente a %', old.id, new.estado
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

-- El nombre de las versiones anteriores (nunca aplicadas): si alguna base de
-- prueba las tiene, no quedan dos triggers para el mismo control.
drop trigger if exists acciones_propuestas_inmutable on asistente.acciones_propuestas;
drop function if exists asistente.acciones_propuestas_inmutable();

drop trigger if exists acciones_propuestas_vinculante on asistente.acciones_propuestas;
create trigger acciones_propuestas_vinculante
  before insert or update on asistente.acciones_propuestas
  for each row execute function asistente.acciones_propuestas_vinculante();


-- ----------------------------------------------------------------------------
--  COMPROBACIONES
-- ----------------------------------------------------------------------------
do $$
declare
  c text;
begin
  foreach c in array array['hash_argumentos', 'origen', 'contexto', 'sello_aprobacion'] loop
    if not exists (select 1 from information_schema.columns
                    where table_schema = 'asistente' and table_name = 'acciones_propuestas'
                      and column_name = c) then
      raise exception 'falta asistente.acciones_propuestas.%', c;
    end if;
  end loop;
  if (select count(*) from pg_trigger t join pg_class r on r.oid = t.tgrelid
        join pg_namespace n on n.oid = r.relnamespace
       where n.nspname = 'asistente' and r.relname = 'acciones_propuestas'
         and not t.tgisinternal) <> 1 then
    raise exception 'acciones_propuestas tiene que quedar con UN solo trigger propio';
  end if;
  if not exists (select 1 from pg_class r join pg_namespace n on n.oid = r.relnamespace
                  where n.nspname = 'asistente' and r.relname = 'acciones_propuestas'
                    and r.relrowsecurity and r.relforcerowsecurity) then
    raise exception 'acciones_propuestas perdio la RLS forzada de origin';
  end if;
end $$;
