-- ============================================================================
--  APROBACION VINCULANTE  --  M06-A, 21/09/2026
-- ============================================================================
--
--  QUE AGREGA
--  ----------
--  Cuatro columnas a asistente.acciones_propuestas, para atar la aprobacion
--  de una herramienta IRREVERSIBLE (Herramienta.irreversible: R3 equipo del
--  cliente, R4 dinero) a la accion EXACTA:
--
--    hash_argumentos  SHA-256 canonico de 'argumentos' al PROPONER. La
--                     frontera lo compara contra la fila (¿la tocaron?) y
--                     contra lo que va a salir (¿se manda otra cosa?).
--    origen           la solicitud de la que salio (el turno, el wamid).
--    contexto         lo minimo para volver a medir las precondiciones al
--                     aprobar: identificadores tecnicos (sn_onu, id_cliente)
--                     y con que argumentos se consulto cada previa. NO la
--                     ficha del cliente ni las respuestas de la API.
--    conversation_id  donde anotar la verificacion posterior de la accion.
--
--  Quien aprobo y cuando ya existian: 'revisado_por', 'revisado_en'. Lo que
--  cambia es CUANDO se escriben para una irreversible: antes del efecto, no
--  despues (ver nucleo/canales/api.py::_aprobar_irreversible).
--
--  INMUTABILIDAD  --  defensa en profundidad, no la unica
--  ------------------------------------------------------
--  El codigo ya bloquea una aprobacion cuyos argumentos cambiaron
--  (nucleo/seguridad/aprobacion.py compara la huella). Este trigger impide
--  ademas que alguien cambie los argumentos Y la huella a la vez con un
--  UPDATE: la identidad de una propuesta no se edita, se propone otra.
--
--  Para las irreversibles (hash_argumentos no nulo) tambien fija la maquina
--  de estados: pendiente -> aprobada | rechazada, y de ahi no se mueve. Una
--  aprobacion ya ejecutada no puede pasar a 'rechazada' despues y reescribir
--  quien aprobo. Las propuestas comunes (R2) no cambian de comportamiento.
--
--  NO SE APLICA EN ESTE BLOQUE. El codigo tolera que falte: una propuesta
--  comun sigue funcionando, y una irreversible falla CERRADA (el insert con
--  las columnas nuevas no pasa, o la aprobacion llega sin huella y la
--  frontera la bloquea).
-- ============================================================================

alter table asistente.acciones_propuestas
  add column if not exists hash_argumentos text,
  add column if not exists origen          text,
  add column if not exists contexto        jsonb,
  add column if not exists conversation_id uuid
    references asistente.conversations(id) on delete set null;

create or replace function asistente.acciones_propuestas_inmutable()
returns trigger
language plpgsql
as $$
begin
  if new.organization_id is distinct from old.organization_id
     or new.herramienta   is distinct from old.herramienta
     or new.argumentos    is distinct from old.argumentos
     or new.hash_argumentos is distinct from old.hash_argumentos
     or new.origen        is distinct from old.origen
     or new.contexto      is distinct from old.contexto
     or new.propuesto_por is distinct from old.propuesto_por
     or new.creado_en     is distinct from old.creado_en then
    raise exception 'acciones_propuestas: la identidad de una propuesta no se edita (id %)', old.id
      using errcode = 'check_violation';
  end if;

  --  El vinculo a la conversacion se llena UNA vez y no se muda.
  if old.conversation_id is not null
     and new.conversation_id is distinct from old.conversation_id then
    raise exception 'acciones_propuestas: la propuesta % ya tiene conversacion', old.id
      using errcode = 'check_violation';
  end if;

  --  Irreversibles: la aprobacion, una vez escrita, no se reescribe.
  if old.hash_argumentos is not null and old.estado <> 'pendiente' then
    if new.estado       is distinct from old.estado
       or new.revisado_por is distinct from old.revisado_por
       or new.revisado_en  is distinct from old.revisado_en then
      raise exception 'acciones_propuestas: la aprobacion de % ya esta % y no se reescribe',
        old.id, old.estado using errcode = 'check_violation';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists acciones_propuestas_inmutable on asistente.acciones_propuestas;
create trigger acciones_propuestas_inmutable
  before update on asistente.acciones_propuestas
  for each row execute function asistente.acciones_propuestas_inmutable();
