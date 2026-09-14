-- =============================================================================
--  SCHEDULER PERSISTENTE  --  el reloj deja de vivir en un sleep
-- =============================================================================
--
-- POR QUE
-- -------
-- El reloj actual duerme 3600 s DESPUES de terminar y no persiste nada. Dos
-- consecuencias medidas en produccion el 12-14/09/2026:
--
--   hambre    nueve despliegues en 2 h 43 min reiniciaron el contenedor antes
--             de que el sleep venciera: CERO barridos en cuatro horas. El
--             reloj no avisa que no barrio; simplemente no barre.
--
--   deriva    +33,7 s por ciclo, +10,1 min en 18 ciclos, ~13,5 min/dia.
--             Un barrido de las 09:14 cae a las 22:00 en un mes.
--
-- Ninguna de las dos se arregla con un sleep mas listo: hace falta estado que
-- sobreviva al reinicio.
--
-- LO QUE ESTE ARCHIVO NO RESUELVE
-- -------------------------------
-- 'job_executor' es un proceso CONFIABLE. Opera como 'app_backend', y
-- 'app.current_tenant' es un GUC personalizado de contexto PGC_USERSET:
-- cualquier rol puede fijarlo a cualquier valor, y 'REVOKE SET ON PARAMETER'
-- no lo impide -- medido en PostgreSQL 16.14. La capability de abajo protege
-- la COORDINACION (quien reclama que turno), no el movimiento lateral de un
-- ejecutor comprometido. Dicho asi, en voz alta, para que nadie lea de esto
-- una garantia que no da.
--
-- DEPENDENCIA DE DESPLIEGUE
-- -------------------------
-- 'pgcrypto' en el schema 'ext'. Crearla exige superusuario, asi que es un
-- paso previo del despliegue y no algo que este archivo pueda hacer solo en
-- cualquier entorno. Se comprueba abajo y se falla con un mensaje que dice
-- exactamente que falta.
-- =============================================================================

-- --- la dependencia, comprobada antes de nada -------------------------------
do $$
begin
  if to_regprocedure('ext.digest(text,text)') is null then
    raise exception using
      message = 'Falta ext.digest(text,text): la extension pgcrypto no esta en el schema ext.',
      hint    = 'Ejecutar como superusuario: CREATE SCHEMA IF NOT EXISTS ext; '
                'CREATE EXTENSION pgcrypto WITH SCHEMA ext;';
  end if;
end $$;

-- =============================================================================
--  CATALOGO  --  la fuente canonica de los parametros del job
-- =============================================================================
-- Existian repartidos entre Python (INTERVALO_BARRIDO_SEGUNDOS), el YAML del
-- tenant (cada_horas) y constantes sueltas. Tres lugares para el mismo numero
-- es como se llega a que digan cosas distintas.

create table if not exists asistente.job_catalogo (
  code               text primary key,
  descripcion        text        not null,
  anchor             timestamptz not null,
  intervalo          interval    not null,
  lease_duracion     interval    not null default interval '5 minutes',
  max_intentos       int         not null default 4,
  backoffs           interval[]  not null default
                       array[interval '60 s', interval '300 s', interval '900 s'],
  max_claims_por_tick int        not null default 500,
  presupuesto_tick   interval    not null default interval '45 s',
  habilitado         boolean     not null default true,
  constraint jc_intervalo_positivo check (intervalo > interval '0'),
  constraint jc_lease_positivo     check (lease_duracion > interval '0'),
  constraint jc_intentos           check (max_intentos between 1 and 10),
  -- los backoffs son los que van ENTRE intentos: uno menos que el maximo
  constraint jc_backoffs           check (array_length(backoffs, 1) = max_intentos - 1),
  -- el anchor tiene que estar alineado a si mismo: UTC, sin microsegundos
  constraint jc_anchor_limpio      check (date_trunc('second', anchor) = anchor)
);

-- =============================================================================
--  ESTADO ACTUAL  --  una fila por (job, organizacion)
-- =============================================================================

create table if not exists asistente.job_schedule_state (
  job_code           text        not null references asistente.job_catalogo(code),
  organization_id    uuid        not null references public.organization(id),
  next_run_at        timestamptz not null,
  current_slot       timestamptz,
  current_run_id     uuid,
  retry_due_at       timestamptz,
  lease_token        uuid,
  lease_until        timestamptz,
  fencing_version    bigint      not null default 0,
  attempt_count      int         not null default 0,
  last_started_at    timestamptz,
  last_completed_at  timestamptz,
  last_successful_at timestamptz,
  version            bigint      not null default 0,
  primary key (job_code, organization_id),

  -- turno en curso y run apuntado van juntos o no van
  constraint js_slot_run    check ((current_run_id is null) = (current_slot is null)),
  -- un backoff sin turno en curso no significa nada
  constraint js_retry       check (retry_due_at is null or current_run_id is not null),
  -- el lease es un par
  constraint js_lease_par   check ((lease_token is null) = (lease_until is null)),
  -- y solo existe sobre un turno en curso
  constraint js_lease_run   check (lease_token is null or current_run_id is not null),
  constraint js_intentos    check (attempt_count between 0 and 10),
  constraint js_fencing     check (fencing_version >= 0),
  constraint js_next_limpio check (date_trunc('second', next_run_at) = next_run_at)
);

-- =============================================================================
--  TURNO  --  una fila por scheduled_slot. La config congelada vive aca.
-- =============================================================================

create table if not exists asistente.job_run (
  id               uuid primary key default gen_random_uuid(),
  job_code         text        not null references asistente.job_catalogo(code),
  organization_id  uuid        not null references public.organization(id),
  scheduled_slot   timestamptz not null,
  idempotency_key  text        not null,
  -- la configuracion se congela en el PRIMER claim y todos los intentos usan
  -- esta version. Un cambio en la config vigente NO afecta un turno reclamado.
  config_version   int         not null,
  config_hash      text        not null,
  -- las entradas del turno, canonicas y acotadas. No es solo un hash: sin
  -- esto, un reintento no podria reconstruir que habia que hacer.
  inputs           jsonb       not null default '{}'::jsonb,
  inputs_hash      text        not null,
  estado           text        not null default 'pending',
  started_at       timestamptz,
  completed_at     timestamptz,
  creado_en        timestamptz not null default now(),

  constraint jr_estado check (estado in
    ('pending','running','retry_wait','succeeded','failed_terminal')),
  -- terminal si y solo si tiene completed_at
  constraint jr_terminal_completo check
    ((estado in ('succeeded','failed_terminal')) = (completed_at is not null)),
  constraint jr_slot_limpio check (date_trunc('second', scheduled_slot) = scheduled_slot),
  constraint jr_inputs_acotados check (pg_column_size(inputs) <= 8192),

  unique (job_code, organization_id, scheduled_slot),
  unique (idempotency_key),

  -- la FK a la configuracion historica, por organizacion. ON DELETE RESTRICT:
  -- una version referenciada por un turno no puede desaparecer.
  constraint jr_config_historica
    foreign key (organization_id, config_version)
    references asistente.tenant_config_historial (organization_id, config_version)
    on delete restrict,

  -- superclaves, destino de las FK compuestas de abajo. Redundantes como
  -- claves (id ya es PK) y necesarias para que las FK puedan exigir que la
  -- organizacion coincida en toda la cadena.
  constraint jr_superclave_slot unique (id, job_code, organization_id, scheduled_slot),
  constraint jr_superclave_org  unique (id, organization_id)
);

-- un solo turno vivo por (job, organizacion)
create unique index if not exists jr_uno_activo
  on asistente.job_run (job_code, organization_id)
  where estado in ('pending','running','retry_wait');

-- el estado apunta a un run del MISMO job, organizacion y slot
alter table asistente.job_schedule_state
  drop constraint if exists js_run_coherente;
alter table asistente.job_schedule_state
  add constraint js_run_coherente
  foreign key (current_run_id, job_code, organization_id, current_slot)
  references asistente.job_run (id, job_code, organization_id, scheduled_slot);

-- =============================================================================
--  INTENTO  --  una fila por intento del turno
-- =============================================================================

create table if not exists asistente.job_attempt (
  id                  uuid primary key default gen_random_uuid(),
  run_id              uuid not null,
  organization_id     uuid not null references public.organization(id),
  attempt_number      int  not null,
  lease_token         uuid not null,
  fencing_version     bigint not null,
  -- SOLO el hash. El valor original vive en memoria del coordinador y se
  -- entrega una vez al ejecutor.
  capability_hash     bytea not null,
  capability_revocada boolean not null default false,
  worker_id           text not null,
  started_at          timestamptz not null default now(),
  completed_at        timestamptz,
  outcome             text,
  error_code          text,

  constraint ja_numero  check (attempt_number between 1 and 10),
  constraint ja_outcome check (outcome is null or outcome in
    ('succeeded','failed_retryable','failed_terminal','lease_lost')),
  -- terminado si y solo si tiene completed_at
  constraint ja_completo check ((outcome is null) = (completed_at is null)),
  -- Un error_code solo tiene sentido en un fallo. El 'coalesce' no es
  -- cosmetico: con 'outcome in (...)' a secas, un outcome NULL hace que la
  -- expresion entera valga NULL, y un CHECK que da NULL SE ACEPTA. Medido: la
  -- version sin coalesce dejaba entrar un intento en curso con error_code.
  constraint ja_error check (error_code is null or coalesce(outcome,'') in
    ('failed_retryable','failed_terminal','lease_lost')),
  constraint ja_cap_len check (octet_length(capability_hash) = 32),

  unique (run_id, attempt_number),

  -- el intento pertenece a un run de LA MISMA organizacion
  constraint ja_run_misma_org
    foreign key (run_id, organization_id)
    references asistente.job_run (id, organization_id),

  -- superclave para la FK del evento
  constraint ja_superclave unique (id, run_id, organization_id)
);

-- un solo intento activo por turno
create unique index if not exists ja_uno_activo
  on asistente.job_attempt (run_id) where outcome is null;

-- =============================================================================
--  HISTORIA  --  append-only frente a roles runtime
-- =============================================================================

create table if not exists asistente.job_run_event (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null,
  attempt_id      uuid,
  organization_id uuid not null references public.organization(id),
  tipo            text not null,
  ocurrido_en     timestamptz not null default now(),
  -- lista blanca por tipo, validada en las funciones. NUNCA: PII, secretos,
  -- cuerpos del proveedor, tracebacks, capabilities ni sus hashes.
  datos           jsonb not null default '{}'::jsonb,

  constraint jre_tipo check (tipo in
    ('CLAIMED','STARTED','SUCCEEDED','FAILED_RETRYABLE',
     'FAILED_TERMINAL','LEASE_LOST','CAPABILITY_REVOCADA')),
  constraint jre_datos_acotados check (pg_column_size(datos) <= 2048),
  -- un evento terminal es de un INTENTO concreto
  constraint jre_terminal_con_intento check (
    tipo not in ('SUCCEEDED','FAILED_RETRYABLE','FAILED_TERMINAL','LEASE_LOST')
    or attempt_id is not null),

  -- el evento pertenece a un run de la misma organizacion
  constraint jre_run_misma_org
    foreign key (run_id, organization_id)
    references asistente.job_run (id, organization_id),

  -- y si nombra un intento, ese intento es del MISMO run y organizacion
  constraint jre_attempt_del_mismo_run
    foreign key (attempt_id, run_id, organization_id)
    references asistente.job_attempt (id, run_id, organization_id)
);

-- un solo evento terminal por intento, sea cual sea el tipo
create unique index if not exists jre_un_terminal_por_intento
  on asistente.job_run_event (attempt_id)
  where tipo in ('SUCCEEDED','FAILED_RETRYABLE','FAILED_TERMINAL','LEASE_LOST');

-- y un solo desenlace del turno
create unique index if not exists jre_un_desenlace_por_run
  on asistente.job_run_event (run_id)
  where tipo in ('SUCCEEDED','FAILED_TERMINAL');

-- =============================================================================
--  INDICES DE BUSQUEDA
-- =============================================================================

create index if not exists js_por_vencer on asistente.job_schedule_state (next_run_at);
create index if not exists js_por_retry  on asistente.job_schedule_state (retry_due_at)
  where retry_due_at is not null;
create index if not exists js_por_lease  on asistente.job_schedule_state (lease_until)
  where lease_until is not null;
create index if not exists jr_por_org    on asistente.job_run (organization_id, creado_en desc);
create index if not exists jre_por_run   on asistente.job_run_event (run_id, ocurrido_en);

-- =============================================================================
--  RLS  --  habilitado, SIN force
-- =============================================================================
-- Sin FORCE a proposito: el dueño (asistente_owner, NOLOGIN) tiene que poder
-- ver todas las filas desde las funciones SECURITY DEFINER. Esa es la unica
-- excepcion, y es alcanzable solo a traves de las seis funciones auditadas --
-- ningun rol con login puede hacer SET ROLE asistente_owner ni leer estas
-- tablas directamente.

alter table asistente.job_catalogo        enable row level security;
alter table asistente.job_schedule_state  enable row level security;
alter table asistente.job_run             enable row level security;
alter table asistente.job_attempt         enable row level security;
alter table asistente.job_run_event       enable row level security;

drop policy if exists tenant_aislado on asistente.job_schedule_state;
create policy tenant_aislado on asistente.job_schedule_state
  using (organization_id = asistente.org_actual());
drop policy if exists tenant_aislado on asistente.job_run;
create policy tenant_aislado on asistente.job_run
  using (organization_id = asistente.org_actual());
drop policy if exists tenant_aislado on asistente.job_attempt;
create policy tenant_aislado on asistente.job_attempt
  using (organization_id = asistente.org_actual());
drop policy if exists tenant_aislado on asistente.job_run_event;
create policy tenant_aislado on asistente.job_run_event
  using (organization_id = asistente.org_actual());
-- el catalogo no es por tenant: lectura para todos, escritura de nadie runtime
drop policy if exists catalogo_legible on asistente.job_catalogo;
create policy catalogo_legible on asistente.job_catalogo using (true);
