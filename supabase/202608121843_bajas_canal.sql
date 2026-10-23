-- =============================================================================
--  BAJAS DEL CANAL  -  quien pidio que no le escribamos mas
-- =============================================================================
--
--  Por que existe
--  --------------
--  El dia que el sistema puede escribir PRIMERO (avisos de mora, de corte, de
--  mantenimiento) aparece la obligacion de dejar de hacerlo cuando alguien lo
--  pide. En Colombia no es cortesia: la Ley 1581 le da al titular el derecho a
--  revocar la autorizacion y a oponerse al tratamiento, y WhatsApp por su lado
--  penaliza a los numeros que acumulan bloqueos -- una cuenta con mala
--  reputacion pierde limite de envio y puede quedar inhabilitada.
--
--  Es una tabla y no una bandera en tenant_users porque la baja pertenece al
--  NUMERO y al canal, no al usuario: alguien puede pedir baja de los avisos de
--  WhatsApp y seguir siendo cliente, y un numero puede escribir sin tener
--  todavia una fila de usuario.
--
--  LA BAJA NO CIERRA LA CONVERSACION
--  ---------------------------------
--  Se bloquea lo PROACTIVO, no lo reactivo. Si despues el cliente escribe, se
--  le contesta: dejar sin respuesta a alguien que pregunta seria un peor
--  servicio y no es lo que pidio. Lo que pidio es que no lo interrumpamos.
-- =============================================================================

create table if not exists asistente.canal_bajas (
  organization_id uuid not null references public.organization(id) on delete cascade,
  canal           text not null default 'whatsapp',
  -- El identificador tal cual lo usa el canal (el telefono, sin '+').
  usuario_externo text not null,
  -- La palabra con que lo pidio, para poder auditar por que se dio de baja.
  motivo          text,
  creado_en       timestamptz not null default now(),
  primary key (organization_id, canal, usuario_externo)
);

comment on table asistente.canal_bajas is
  'Numeros que pidieron no recibir mensajes proactivos. Bloquea plantillas y '
  'avisos, NUNCA la respuesta a un mensaje que el cliente inicia.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.canal_bajas enable row level security;
alter table asistente.canal_bajas force row level security;
grant select, insert, update, delete on asistente.canal_bajas to app_backend;

drop policy if exists tenant_aislado on asistente.canal_bajas;
create policy tenant_aislado on asistente.canal_bajas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
