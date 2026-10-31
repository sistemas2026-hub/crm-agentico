-- =============================================================================
--  Ejemplos validados: respuestas del agente marcadas como buenas
-- =============================================================================
--
--  Base del manual de procedimientos que se arma DESDE conversaciones reales
--  (y de prueba) en vez de escribirse a ciegas: un colaborador marca, desde
--  el Simulador de WhatsApp o desde /conversaciones, que una respuesta del
--  agente fue buena y a que caso/proceso corresponde (nucleo/canales/api.py,
--  endpoints /conversaciones/<id>/mensajes/<mensaje_id>/marcar). La pantalla
--  /manual agrupa lo marcado por caso para que despues se redacte el
--  procedimiento final -- publicarlo al corpus es una entrega aparte.
--
--  Solo se marcan respuestas BUENAS (decision del usuario, agosto 2026): no
--  hay una contraparte "invalida" ni flujo de correccion en el momento. Una
--  fila = una burbuja marcada; unique(mensaje_id) porque una burbuja se marca
--  una sola vez -- volver a marcarla actualiza el caso, no duplica fila.

create table if not exists asistente.ejemplos_validados (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  conversation_id uuid not null references asistente.conversations(id) on delete cascade,
  mensaje_id      uuid not null references asistente.messages(id) on delete cascade,
  -- De tenant_config.manual.casos -- nunca fuera de esa lista (lo valida
  -- nucleo/canales/api.py antes de llamar a marcar_ejemplo).
  caso            text not null,
  -- Email de quien marco (locals.user.email en el frontend). Nunca un valor
  -- que mande el cliente sin pasar por su sesion logueada.
  marcado_por     text,
  creado_en       timestamptz not null default now(),
  unique (mensaje_id)
);

create index if not exists ejemplos_validados_caso_idx
  on asistente.ejemplos_validados (organization_id, caso, creado_en desc);

alter table asistente.ejemplos_validados enable row level security;
alter table asistente.ejemplos_validados force row level security;
grant select, insert, update, delete on asistente.ejemplos_validados to app_backend;

drop policy if exists tenant_aislado on asistente.ejemplos_validados;
create policy tenant_aislado on asistente.ejemplos_validados
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
