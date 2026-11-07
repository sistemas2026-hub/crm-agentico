-- =============================================================================
--  VERIFICACION POSTERIOR A UNA ACCION
-- =============================================================================
--  Una herramienta de escritura confirma que el COMANDO SE MANDO, no que hizo
--  efecto: 'reiniciar_ont' responde "Device reboot command sent" en medio
--  segundo y el equipo tarda minutos en volver. Hasta ahora lo unico que
--  separaba una cosa de la otra era que el modelo leyera bien esa palabra.
--
--  Aca queda la constancia: que se ejecuto, cuanto habia que esperar, con que
--  se midio, que se midio ANTES y DESPUES, y en que estado termino. Es tabla
--  propia y no una columna mas en 'tool_calls' porque una verificacion no es
--  una llamada: nace de una, ocurre despues, puede reintentarse y tiene un
--  estado que cambia con el tiempo.
--
--  'tool_calls' queda igual que siempre -- esto no toca esa traza.
-- =============================================================================

create table if not exists asistente.verificaciones_accion (
  id                 uuid primary key default gen_random_uuid(),
  organization_id    uuid not null references public.organization(id) on delete cascade,
  conversation_id    uuid not null references asistente.conversations(id) on delete cascade,
  -- La accion que hay que comprobar.
  herramienta        text not null,
  ejecutada_en       timestamptz not null default now(),
  -- Cuanto habia que esperar antes de que medir signifique algo, y cuantas
  -- veces se podia volver a medir. Se guardan con la fila y no se leen de la
  -- config al resolver: si alguien cambia el plazo mañana, esta verificacion
  -- tiene que seguir contando con el que estaba vigente cuando se ejecuto.
  espera_segundos    integer not null,
  max_intentos       integer not null,
  intentos           integer not null default 0,
  -- Las dos mediciones, crudas. Sirven para poder rehacer la conclusion a
  -- mano si alguna vez el estado no se entiende.
  medicion_previa    jsonb,
  medicion_posterior jsonb,
  -- VERIFICACION_PENDIENTE | ACCION_CONFIRMADA | ACCION_NO_CONFIRMADA |
  -- NO_VERIFICABLE -- ver nucleo/seguimiento/verificacion_accion.py.
  estado             text not null default 'VERIFICACION_PENDIENTE',
  por_que            text,
  verificada_en      timestamptz
);

-- La consulta que corre en cada turno: "¿esta conversacion tiene algo sin
-- comprobar?". Es tambien la que sostiene el candado de cierre.
create index if not exists verificaciones_accion_pendientes_idx
  on asistente.verificaciones_accion (organization_id, conversation_id, estado);

alter table asistente.verificaciones_accion enable row level security;
alter table asistente.verificaciones_accion force row level security;
grant select, insert, update, delete on asistente.verificaciones_accion to app_backend;

drop policy if exists tenant_aislado on asistente.verificaciones_accion;
create policy tenant_aislado on asistente.verificaciones_accion
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

comment on table asistente.verificaciones_accion is
  'Comprobacion posterior de que una accion produjo su efecto tecnico. El
   estado lo calcula el codigo comparando la medicion previa con una
   posterior y fresca -- nunca el modelo. Ver Herramienta.verificacion en
   nucleo/config/schema.py.';
