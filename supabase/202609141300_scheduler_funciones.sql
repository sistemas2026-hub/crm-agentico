-- =============================================================================
--  SCHEDULER PERSISTENTE  --  ROLES, PROPIEDAD Y LAS SEIS FUNCIONES
-- =============================================================================
--
--  La migracion anterior creo las tablas. Esta define QUIEN puede tocarlas y
--  COMO. La regla es una sola: ningun proceso de runtime escribe 'job_*' con
--  SQL propio. Todo pasa por seis funciones SECURITY DEFINER, y los roles de
--  runtime no tienen ni un GRANT sobre las tablas.
--
--  Por que asi y no con permisos de tabla: las invariantes del scheduler
--  --un solo intento activo, el lease se renueva solo si el fencing sigue
--  siendo el tuyo, la config se congela en el primer claim-- no se pueden
--  expresar con GRANT. Con permisos de tabla, un worker con un bug puede
--  escribir un estado que ninguna constraint prohibe y que el coordinador no
--  sabe interpretar. Con funciones, el estado invalido no es alcanzable.
--
--  Lo que estas funciones NO son: una barrera de aislamiento entre empresas.
--  'job_executor' es un proceso CONFIABLE y opera como 'app_backend' eligiendo
--  el tenant. La capability protege la COORDINACION --que un worker zombi no
--  siga escribiendo sobre un turno que ya no es suyo-- no el movimiento
--  lateral. Escribirlo aca para que nadie lo lea al reves mas adelante.
-- =============================================================================

-- -----------------------------------------------------------------------------
--  0. pgcrypto, otra vez
-- -----------------------------------------------------------------------------
-- La migracion anterior ya lo exige, pero esta lo USA en el cuerpo de las
-- funciones. Si alguien aplica esta sola, que falle aca y no en la primera
-- ejecucion a las 3 de la mañana.
do $$
begin
  if to_regprocedure('ext.digest(text,text)') is null
     or to_regprocedure('ext.gen_random_bytes(integer)') is null then
    raise exception 'falta pgcrypto en el esquema ext'
      using hint = 'CREATE EXTENSION pgcrypto WITH SCHEMA ext;';
  end if;
end $$;

-- -----------------------------------------------------------------------------
--  1. ROLES
-- -----------------------------------------------------------------------------
--  asistente_owner        dueño de las tablas job_*. NOLOGIN. Es el rol bajo el
--                         que corren las funciones SECURITY DEFINER, y por eso
--                         es el unico que ve todas las organizaciones.
--  scheduler_coordinator  el proceso que decide QUE turnos tocan. NOLOGIN.
--  job_executor           el proceso que EJECUTA un turno. NOLOGIN.
--  monitor_ro             metricas agregadas. NOLOGIN. Cero DML, cero filas.
--
--  Ninguno es miembro de otro. En particular NO existe
--  'grant app_backend to job_executor': el ejecutor asume app_backend por su
--  propia membresia desde el proceso, no heredandola del rol de scheduler.
--  Mezclarlos anularia la separacion entera.
do $$
declare
  r text;
begin
  foreach r in array array['asistente_owner', 'scheduler_coordinator',
                           'job_executor', 'monitor_ro']
  loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin', r);
    end if;
  end loop;

  -- Membresia para quien corre las migraciones. Es requisito estructural, no
  -- comodidad: para hacer 'alter table ... owner to asistente_owner' hay que
  -- ser miembro del rol destino. Quien crea la cadena de propiedad la tiene.
  execute format('grant asistente_owner to %I', current_user);
end $$;

-- Las tablas pasan a ser del dueño. A partir de aca, ningun rol de runtime
-- tiene permiso sobre ellas: se revoca todo y no se otorga nada.
alter table asistente.job_catalogo       owner to asistente_owner;
alter table asistente.job_schedule_state owner to asistente_owner;
alter table asistente.job_run            owner to asistente_owner;
alter table asistente.job_attempt        owner to asistente_owner;
alter table asistente.job_run_event      owner to asistente_owner;

revoke all on asistente.job_catalogo       from public;
revoke all on asistente.job_schedule_state from public;
revoke all on asistente.job_run            from public;
revoke all on asistente.job_attempt        from public;
revoke all on asistente.job_run_event      from public;

-- El dueño tambien lo necesita, y no es una formalidad: las comprobaciones
-- internas de las FK corren como el dueño de la tabla, asi que sin este grant
-- una simple insercion en job_schedule_state muere con 'permission denied for
-- schema asistente' al verificar la referencia al catalogo. Medido.
grant usage on schema asistente to asistente_owner;
-- Y sobre 'ext', donde vive pgcrypto: 'job_claim' calcula ahi el sha256 de la
-- config y genera los 32 bytes de la capability. Solo el dueño lo necesita --
-- ningun rol de runtime llama a pgcrypto.
grant usage on schema ext to asistente_owner;
grant usage on schema asistente to scheduler_coordinator, job_executor, monitor_ro;

-- -----------------------------------------------------------------------------
--  1b. LO UNICO QUE EL SCHEDULER LEE FUERA DE job_*
-- -----------------------------------------------------------------------------
-- 'job_claim' congela la version de configuracion del tenant, y para eso tiene
-- que leerla. Es el unico punto en que este subsistema cruza el limite de una
-- organizacion, asi que se abre lo minimo y se deja escrito que es:
--
--   * SELECT de TRES columnas. No 'grant select' a la tabla: sin 'config' no se
--     puede calcular el hash, pero lo demas no hace falta y no se otorga.
--   * Las dos tablas tienen RLS con FORCE y su unica politica nombra a
--     'app_backend'. Para asistente_owner no hay politica, y sin politica RLS
--     devuelve CERO filas -- el grant solo no alcanza. Por eso la politica
--     explicita de abajo.
--   * Se resuelve con una politica nominal y NO dandole BYPASSRLS al dueño.
--     BYPASSRLS es un atributo de rol que aplica a TODAS las tablas de la base
--     y no se puede acotar; una politica dice exactamente sobre que tabla, para
--     que rol y para que comando. Sacar BYPASSRLS de donde todavia esta es una
--     tarea abierta aparte: este subsistema no lo agrega.
--   * Solo SELECT. El scheduler no escribe configuracion de nadie.
grant select (organization_id, config_version, config)
  on asistente.tenant_config to asistente_owner;
grant select (organization_id, config_version)
  on asistente.tenant_config_historial to asistente_owner;

drop policy if exists scheduler_congela on asistente.tenant_config;
create policy scheduler_congela on asistente.tenant_config
  for select to asistente_owner using (true);
drop policy if exists scheduler_congela on asistente.tenant_config_historial;
create policy scheduler_congela on asistente.tenant_config_historial
  for select to asistente_owner using (true);

-- -----------------------------------------------------------------------------
--  2. EL SLOT ALINEADO
-- -----------------------------------------------------------------------------
-- El turno de un job no es "una hora despues del anterior": es un punto fijo de
-- una grilla que arranca en 'anchor'. Esa es la diferencia entre un reloj y un
-- temporizador, y es exactamente el defecto que se midio en el scheduler viejo
-- --dormir el intervalo DESPUES de terminar acumulaba +33,7 s por ciclo, 13,5
-- minutos por dia. Con la grilla, el atraso de un ciclo no se hereda.
create or replace function asistente.job_slot(
  p_anchor    timestamptz,
  p_intervalo interval,
  p_momento   timestamptz)
returns timestamptz
language sql
-- stable, no immutable: 'date_trunc' sobre timestamptz depende de TimeZone y
-- es stable. Declararla immutable seria mentirle al planificador.
stable
set search_path = pg_catalog
as $$
  select date_trunc('second',
           p_anchor + floor(extract(epoch from (p_momento - p_anchor))
                          / extract(epoch from p_intervalo)) * p_intervalo);
$$;

comment on function asistente.job_slot(timestamptz, interval, timestamptz) is
  'El slot de la grilla vigente en ese momento. Si p_momento es anterior al '
  'anchor devuelve un slot anterior al anchor: el job simplemente no vence '
  'todavia, y eso lo decide next_run_at, no esta funcion.';

-- -----------------------------------------------------------------------------
--  3. QUE VENCE  --  solo lectura
-- -----------------------------------------------------------------------------
-- Tres puertas de entrada, y son EXCLUYENTES entre si, no alternativas:
--
--   nuevo          no hay turno en curso  y  next_run_at ya paso
--   reintento      HAY turno en curso     y  el backoff ya vencio
--   lease_vencido  HAY turno en curso, sin backoff, y el lease se murio
--
-- La exclusividad la da 'current_run_id is null / is not null'. Importa: una
-- version anterior de esto usaba 'next_run_at <= ahora OR retry_due_at <=
-- ahora', y eso deja reclamar como NUEVO un turno que esta esperando su
-- backoff. El backoff dejaba de existir.
create or replace function asistente.jobs_vencidos(
  p_ahora  timestamptz default now(),
  p_limite int         default 100)
returns table (
  job_code        text,
  organization_id uuid,
  slot            timestamptz,
  motivo          text,
  vencido_desde   timestamptz)
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select s.job_code,
         s.organization_id,
         case when s.current_run_id is null then s.next_run_at
              else s.current_slot end                        as slot,
         case when s.current_run_id is null    then 'nuevo'
              when s.retry_due_at is not null  then 'reintento'
              else 'lease_vencido' end                       as motivo,
         case when s.current_run_id is null    then s.next_run_at
              when s.retry_due_at is not null  then s.retry_due_at
              else s.lease_until end                         as vencido_desde
    from asistente.job_schedule_state s
    join asistente.job_catalogo c on c.code = s.job_code
   where c.habilitado
     and (s.lease_until is null or s.lease_until <= p_ahora)
     and (
           (s.current_run_id is null
            and s.next_run_at <= p_ahora)
        or (s.current_run_id is not null
            and s.retry_due_at is not null
            and s.retry_due_at <= p_ahora)
        or (s.current_run_id is not null
            and s.retry_due_at is null
            and s.lease_until is not null
            and s.lease_until <= p_ahora)
         )
   order by 5, 1, 2
   limit greatest(p_limite, 0);
$$;

-- -----------------------------------------------------------------------------
--  4. RECLAMAR
-- -----------------------------------------------------------------------------
-- Devuelve CERO filas cuando no se pudo reclamar. Nunca lanza excepcion por una
-- carrera perdida: que otro coordinador se haya quedado con el turno es
-- funcionamiento normal, no un error.
--
-- Lanza excepcion, en cambio, cuando falta la config historica de la
-- organizacion. Eso no es una carrera: es que el turno no puede congelar contra
-- que version se ejecuta, y ejecutarlo "con la que haya" es justamente lo que
-- este diseño existe para impedir.
create or replace function asistente.job_claim(
  p_job_code        text,
  p_organization_id uuid,
  p_slot            timestamptz,
  p_worker_id       text,
  p_inputs          jsonb default '{}'::jsonb)
returns table (
  run_id          uuid,
  attempt_id      uuid,
  attempt_number  int,
  fencing_version bigint,
  capability      text,
  config_version  int,
  config_hash     text,
  inputs          jsonb,
  lease_until     timestamptz,
  slot            timestamptz)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_ahora      timestamptz := now();
  v_cat        asistente.job_catalogo%rowtype;
  v_est        asistente.job_schedule_state%rowtype;
  v_run        asistente.job_run%rowtype;
  v_slot       timestamptz;
  v_cfg_ver    int;
  v_cfg        jsonb;
  v_cfg_hash   text;
  v_inputs     jsonb := coalesce(p_inputs, '{}'::jsonb);
  v_in_hash    text;
  v_idem       text;
  v_intento    int;
  v_fencing    bigint;
  v_lease_tok  uuid;
  v_lease_hasta timestamptz;
  v_cap        text;
  v_att        uuid;
begin
  if p_worker_id is null or length(p_worker_id) = 0 then
    raise exception 'job_claim sin worker_id';
  end if;

  select * into v_cat from asistente.job_catalogo where code = p_job_code;
  if not found or not v_cat.habilitado then
    return;
  end if;

  -- 'skip locked' sobre UNA fila: si otro coordinador la tiene tomada, este no
  -- espera -- se va sin reclamar y el turno le toca al otro. Bloquear seria
  -- peor: dos coordinadores en serie tardan el doble en barrer.
  select * into v_est
    from asistente.job_schedule_state
   where job_code = p_job_code and organization_id = p_organization_id
     for update skip locked;
  if not found then
    return;
  end if;

  -- El lease se re-verifica DENTRO del candado. Lo que dijo 'jobs_vencidos' se
  -- leyo sin candado y puede tener segundos de antigüedad.
  if v_est.lease_until is not null and v_est.lease_until > v_ahora then
    return;
  end if;

  if v_est.current_run_id is null then
    -- --- turno nuevo -------------------------------------------------------
    if v_est.next_run_at > v_ahora then
      return;
    end if;
    v_slot := v_est.next_run_at;
    if p_slot is distinct from v_slot then
      -- el coordinador trae un slot viejo: su lectura quedo obsoleta
      return;
    end if;

    -- La config se congela AHORA, y la FK a tenant_config_historial exige que
    -- esa version exista. Si no existe, el turno no arranca.
    select t.config_version, t.config into v_cfg_ver, v_cfg
      from asistente.tenant_config t
     where t.organization_id = p_organization_id;
    if not found then
      raise exception 'la organizacion no tiene config vigente'
        using hint = 'no se puede congelar una version que no existe';
    end if;
    if not exists (select 1 from asistente.tenant_config_historial h
                    where h.organization_id = p_organization_id
                      and h.config_version = v_cfg_ver) then
      raise exception 'la config vigente (version %) no esta en el historial',
                      v_cfg_ver
        using hint = 'el turno no puede congelar contra que version corre';
    end if;

    v_cfg_hash := encode(ext.digest(v_cfg::text, 'sha256'), 'hex');
    v_in_hash  := encode(ext.digest(v_inputs::text, 'sha256'), 'hex');
    -- La clave de idempotencia NO lleva el numero de intento. Si lo llevara,
    -- cada reintento seria un turno distinto y la unicidad no protegeria nada.
    v_idem := p_job_code || '|' || p_organization_id::text || '|'
              || to_char(v_slot at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')
              || '|' || v_in_hash;

    insert into asistente.job_run
      (job_code, organization_id, scheduled_slot, idempotency_key,
       config_version, config_hash, inputs, inputs_hash, estado)
    values
      (p_job_code, p_organization_id, v_slot, v_idem,
       v_cfg_ver, v_cfg_hash, v_inputs, v_in_hash, 'pending')
    returning * into v_run;

    v_intento := 1;
  else
    -- --- reintento o recuperacion de lease --------------------------------
    v_slot := v_est.current_slot;
    if p_slot is distinct from v_slot then
      return;
    end if;
    if v_est.retry_due_at is not null and v_est.retry_due_at > v_ahora then
      return;                                  -- todavia esta en backoff
    end if;

    select * into v_run from asistente.job_run where id = v_est.current_run_id;
    if not found then
      raise exception 'estado apunta a un turno que no existe';
    end if;

    -- Un intento abierto con el lease muerto es un worker zombi. Se cierra como
    -- 'lease_lost' ANTES de abrir el siguiente: 'ja_uno_activo' no admite dos.
    update asistente.job_attempt a
       set outcome = 'lease_lost', completed_at = v_ahora
     where a.run_id = v_run.id and a.outcome is null;
    if found then
      insert into asistente.job_run_event (run_id, attempt_id, organization_id,
                                           tipo, datos)
      select v_run.id, a.id, v_run.organization_id, 'LEASE_LOST',
             jsonb_build_object('intento', a.attempt_number,
                                'fencing', a.fencing_version)
        from asistente.job_attempt a
       where a.run_id = v_run.id and a.outcome = 'lease_lost'
         and a.completed_at = v_ahora;
    end if;

    v_intento := v_est.attempt_count + 1;
    if v_intento > v_cat.max_intentos then
      -- se agotaron los intentos mientras nadie miraba: el turno cierra mal y
      -- la grilla sigue. No se reclama.
      perform asistente.job_cerrar_turno(v_run.id, 'failed_terminal', v_ahora);
      return;
    end if;
    v_cfg_ver  := v_run.config_version;
    v_cfg_hash := v_run.config_hash;
    v_inputs   := v_run.inputs;
  end if;

  -- --- el intento -----------------------------------------------------------
  v_fencing     := v_est.fencing_version + 1;
  v_lease_tok   := gen_random_uuid();
  v_lease_hasta := v_ahora + v_cat.lease_duracion;
  -- 256 bits de CSPRNG. El texto plano se devuelve UNA vez y no se guarda:
  -- en la tabla solo queda el sha256. No se afirma comparacion en tiempo
  -- constante en ningun punto -- con 256 bits de entropia el ataque que eso
  -- mitigaria no es el que importa.
  v_cap := encode(ext.gen_random_bytes(32), 'hex');

  insert into asistente.job_attempt
    (run_id, organization_id, attempt_number, lease_token, fencing_version,
     capability_hash, worker_id)
  values
    (v_run.id, v_run.organization_id, v_intento, v_lease_tok, v_fencing,
     ext.digest(v_cap, 'sha256'), p_worker_id)
  returning id into v_att;

  update asistente.job_run
     set estado = 'running', started_at = coalesce(started_at, v_ahora)
   where id = v_run.id;

  update asistente.job_schedule_state
     set current_run_id  = v_run.id,
         current_slot    = v_slot,
         retry_due_at    = null,
         lease_token     = v_lease_tok,
         lease_until     = v_lease_hasta,
         fencing_version = v_fencing,
         attempt_count   = v_intento,
         last_started_at = v_ahora,
         version         = version + 1
   where job_code = p_job_code and organization_id = p_organization_id;

  insert into asistente.job_run_event (run_id, attempt_id, organization_id,
                                       tipo, datos)
  values (v_run.id, v_att, v_run.organization_id, 'CLAIMED',
          jsonb_build_object('intento', v_intento, 'fencing', v_fencing,
                             'worker', p_worker_id)),
         (v_run.id, v_att, v_run.organization_id, 'STARTED',
          jsonb_build_object('intento', v_intento));

  return query
    select v_run.id, v_att, v_intento, v_fencing, v_cap,
           v_cfg_ver, v_cfg_hash, v_inputs, v_lease_hasta, v_slot;
end;
$$;

-- -----------------------------------------------------------------------------
--  5. CERRAR UN TURNO  --  interna, sin GRANT para nadie
-- -----------------------------------------------------------------------------
-- Avanza la grilla al slot vigente, no al siguiente del que fallo. Si el
-- sistema estuvo caido nueve horas, un importador horario NO tiene que correr
-- nueve veces seguidas: tiene que correr el turno de ahora. Los slots perdidos
-- quedan perdidos y contados, que es distinto de quedar pendientes.
create or replace function asistente.job_cerrar_turno(
  p_run_id uuid,
  p_estado text,
  p_ahora  timestamptz)
returns void
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_run  asistente.job_run%rowtype;
  v_cat  asistente.job_catalogo%rowtype;
  v_prox timestamptz;
begin
  select * into v_run from asistente.job_run where id = p_run_id;
  if not found then
    raise exception 'turno inexistente';
  end if;
  select * into v_cat from asistente.job_catalogo where code = v_run.job_code;

  update asistente.job_run
     set estado = p_estado, completed_at = p_ahora
   where id = p_run_id;

  v_prox := asistente.job_slot(v_cat.anchor, v_cat.intervalo,
                               greatest(p_ahora, v_run.scheduled_slot))
            + v_cat.intervalo;

  update asistente.job_schedule_state
     set current_run_id     = null,
         current_slot       = null,
         retry_due_at       = null,
         lease_token        = null,
         lease_until        = null,
         attempt_count      = 0,
         next_run_at        = v_prox,
         last_completed_at  = p_ahora,
         last_successful_at = case when p_estado = 'succeeded' then p_ahora
                                   else last_successful_at end,
         version            = version + 1
   where job_code = v_run.job_code
     and organization_id = v_run.organization_id;
end;
$$;

-- -----------------------------------------------------------------------------
--  6. EL INTENTO VIGENTE  --  interna
-- -----------------------------------------------------------------------------
-- Resuelve un intento a partir de (id, capability) y exige que siga siendo el
-- vigente: mismo lease_token y mismo fencing_version que el estado. Un worker
-- que perdio el lease y volvio de un GC pause encuentra el fencing cambiado y
-- no puede escribir nada. Esa es toda la funcion de la capability.
create or replace function asistente.job_intento_vigente(
  p_attempt_id uuid,
  p_capability text)
returns asistente.job_attempt
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_a asistente.job_attempt%rowtype;
  v_s asistente.job_schedule_state%rowtype;
  v_r asistente.job_run%rowtype;
begin
  if p_capability is null or length(p_capability) = 0 then
    return null;
  end if;
  select * into v_a from asistente.job_attempt
   where id = p_attempt_id
     and capability_hash = ext.digest(p_capability, 'sha256')
     and not capability_revocada
     and outcome is null;
  if not found then
    return null;
  end if;

  select * into v_r from asistente.job_run where id = v_a.run_id;
  select * into v_s from asistente.job_schedule_state
   where job_code = v_r.job_code and organization_id = v_r.organization_id;
  if not found
     or v_s.current_run_id is distinct from v_a.run_id
     or v_s.lease_token   is distinct from v_a.lease_token
     or v_s.fencing_version <> v_a.fencing_version then
    return null;
  end if;
  return v_a;
end;
$$;

-- -----------------------------------------------------------------------------
--  7. HEARTBEAT
-- -----------------------------------------------------------------------------
-- Devuelve el nuevo vencimiento del lease, o NULL si el intento ya no es el
-- vigente. NULL significa "soltá lo que estas haciendo": otro worker tiene el
-- turno.
--
-- Un lease VENCIDO no se renueva aunque la capability sea correcta. Renovarlo
-- seria resucitar a un worker que el coordinador ya dio por muerto y que
-- posiblemente ya tiene un reemplazo corriendo.
create or replace function asistente.job_heartbeat(
  p_attempt_id uuid,
  p_capability text)
returns timestamptz
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_ahora timestamptz := now();
  v_a     asistente.job_attempt%rowtype;
  v_r     asistente.job_run%rowtype;
  v_cat   asistente.job_catalogo%rowtype;
  v_hasta timestamptz;
begin
  v_a := asistente.job_intento_vigente(p_attempt_id, p_capability);
  if v_a.id is null then
    return null;
  end if;
  select * into v_r from asistente.job_run where id = v_a.run_id;
  select * into v_cat from asistente.job_catalogo where code = v_r.job_code;

  update asistente.job_schedule_state
     set lease_until = v_ahora + v_cat.lease_duracion,
         version     = version + 1
   where job_code = v_r.job_code
     and organization_id = v_r.organization_id
     and lease_token = v_a.lease_token
     and lease_until > v_ahora
  returning lease_until into v_hasta;

  return v_hasta;
end;
$$;

-- -----------------------------------------------------------------------------
--  8. FINALIZAR
-- -----------------------------------------------------------------------------
-- Devuelve el desenlace REGISTRADO, que no siempre es el reportado:
--
--   'failed_retryable' en el ultimo intento se registra como 'failed_terminal'.
--
-- No es cosmetica. El ultimo fallo reintentable de un turno ES su fallo
-- definitivo, y registrarlo de las dos formas obligaria a escribir dos eventos
-- terminales para el mismo intento -- que es exactamente lo que
-- 'jre_un_terminal_por_intento' prohibe. Un solo hecho, un solo evento.
--
-- Devuelve NULL si el intento ya no es el vigente: el worker llego tarde.
create or replace function asistente.job_finalize(
  p_attempt_id uuid,
  p_capability text,
  p_outcome    text,
  p_error_code text default null)
returns text
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_ahora   timestamptz := now();
  v_a       asistente.job_attempt%rowtype;
  v_r       asistente.job_run%rowtype;
  v_cat     asistente.job_catalogo%rowtype;
  v_final   text;
  v_espera  interval;
begin
  if p_outcome not in ('succeeded', 'failed_retryable', 'failed_terminal') then
    raise exception 'desenlace invalido: %', p_outcome;
  end if;

  v_a := asistente.job_intento_vigente(p_attempt_id, p_capability);
  if v_a.id is null then
    return null;
  end if;
  select * into v_r from asistente.job_run where id = v_a.run_id;
  select * into v_cat from asistente.job_catalogo where code = v_r.job_code;

  v_final := p_outcome;
  if p_outcome = 'failed_retryable'
     and v_a.attempt_number >= v_cat.max_intentos then
    v_final := 'failed_terminal';
  end if;

  update asistente.job_attempt
     set outcome      = v_final,
         completed_at = v_ahora,
         error_code   = case when v_final = 'succeeded' then null
                             else p_error_code end
   where id = v_a.id;

  insert into asistente.job_run_event (run_id, attempt_id, organization_id,
                                       tipo, datos)
  values (v_r.id, v_a.id, v_r.organization_id, upper(v_final),
          jsonb_build_object('intento', v_a.attempt_number,
                             'error_code', p_error_code));

  if v_final = 'failed_retryable' then
    -- Se conservan current_run_id y current_slot. Limpiarlos --que es lo que
    -- hacia la primera version de esto-- convierte el reintento en un turno
    -- nuevo: se pierde la config congelada, el contador de intentos y el
    -- backoff.
    v_espera := v_cat.backoffs[v_a.attempt_number];
    update asistente.job_run set estado = 'retry_wait' where id = v_r.id;
    update asistente.job_schedule_state
       set lease_token       = null,
           lease_until       = null,
           retry_due_at      = v_ahora + v_espera,
           last_completed_at = v_ahora,
           version           = version + 1
     where job_code = v_r.job_code and organization_id = v_r.organization_id;
  else
    perform asistente.job_cerrar_turno(
              v_r.id,
              case when v_final = 'succeeded' then 'succeeded'
                   else 'failed_terminal' end,
              v_ahora);
  end if;

  return v_final;
end;
$$;

-- -----------------------------------------------------------------------------
--  9. ABRIR CONTEXTO
-- -----------------------------------------------------------------------------
-- Fija 'app.current_tenant' (local a la transaccion) con la organizacion que
-- sale del intento reclamado, y la devuelve.
--
-- Esto NO es un control de contencion y no hay que leerlo como tal.
-- 'app.current_tenant' es un GUC de contexto USERSET: cualquier rol puede
-- fijarlo a cualquier valor, y 'revoke set on parameter' no lo restringe
-- --medido en PostgreSQL 16.14. Lo que aporta esta funcion es que el ejecutor
-- no ELIJA el tenant: lo deriva del claim. Un bug de seleccion en el worker
-- deja de ser posible; un worker malicioso no estaba cubierto por nada aca ni
-- antes, y por eso job_executor es un proceso confiable.
create or replace function asistente.job_abrir_contexto(
  p_attempt_id uuid,
  p_capability text)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_a asistente.job_attempt%rowtype;
begin
  v_a := asistente.job_intento_vigente(p_attempt_id, p_capability);
  if v_a.id is null then
    return null;
  end if;
  perform set_config('app.current_tenant', v_a.organization_id::text, true);
  return v_a.organization_id;
end;
$$;

-- -----------------------------------------------------------------------------
--  10. SALUD  --  agregados, sin organization_id
-- -----------------------------------------------------------------------------
-- Ni una columna que identifique a una empresa. Una metrica etiquetada por
-- organizacion termina en un dashboard compartido y en un sistema de alertas
-- que nadie considero parte del perimetro de datos.
create or replace function asistente.job_salud(
  p_ahora timestamptz default now())
returns table (
  job_code          text,
  organizaciones    bigint,
  corriendo         bigint,
  en_backoff        bigint,
  leases_vencidos   bigint,
  vencidos_sin_tomar bigint,
  atraso_max_seg    numeric,
  sin_exito_max_seg numeric)
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select s.job_code,
         count(*),
         count(*) filter (where s.current_run_id is not null
                            and s.retry_due_at is null),
         count(*) filter (where s.retry_due_at is not null),
         count(*) filter (where s.lease_until is not null
                            and s.lease_until <= p_ahora),
         count(*) filter (where s.current_run_id is null
                            and s.next_run_at <= p_ahora),
         max(extract(epoch from (p_ahora - s.next_run_at)))
           filter (where s.next_run_at <= p_ahora),
         max(extract(epoch from (p_ahora - s.last_successful_at)))
    from asistente.job_schedule_state s
   group by s.job_code;
$$;

-- -----------------------------------------------------------------------------
--  11. PERMISOS
-- -----------------------------------------------------------------------------
-- Primero el dueño. SECURITY DEFINER corre como el DUEÑO de la funcion, no
-- como quien la escribio: sin estos 'alter ... owner', las nueve funciones
-- correrian como el usuario de migraciones y todo el modelo de propiedad de la
-- seccion 1 no estaria haciendo nada.
alter function asistente.job_slot(timestamptz, interval, timestamptz)    owner to asistente_owner;
alter function asistente.jobs_vencidos(timestamptz, int)                 owner to asistente_owner;
alter function asistente.job_claim(text, uuid, timestamptz, text, jsonb) owner to asistente_owner;
alter function asistente.job_cerrar_turno(uuid, text, timestamptz)       owner to asistente_owner;
alter function asistente.job_intento_vigente(uuid, text)                 owner to asistente_owner;
alter function asistente.job_heartbeat(uuid, text)                       owner to asistente_owner;
alter function asistente.job_finalize(uuid, text, text, text)            owner to asistente_owner;
alter function asistente.job_abrir_contexto(uuid, text)                  owner to asistente_owner;
alter function asistente.job_salud(timestamptz)                          owner to asistente_owner;

-- 'revoke from public' en cada funcion: sin esto, SECURITY DEFINER las deja
-- ejecutables por CUALQUIER rol, que es la trampa clasica de este patron.
revoke all on function asistente.job_slot(timestamptz, interval, timestamptz)      from public;
revoke all on function asistente.jobs_vencidos(timestamptz, int)                   from public;
revoke all on function asistente.job_claim(text, uuid, timestamptz, text, jsonb)   from public;
revoke all on function asistente.job_cerrar_turno(uuid, text, timestamptz)         from public;
revoke all on function asistente.job_intento_vigente(uuid, text)                   from public;
revoke all on function asistente.job_heartbeat(uuid, text)                         from public;
revoke all on function asistente.job_finalize(uuid, text, text, text)              from public;
revoke all on function asistente.job_abrir_contexto(uuid, text)                    from public;
revoke all on function asistente.job_salud(timestamptz)                            from public;

-- El coordinador decide y reclama. No finaliza: no es suyo el resultado.
grant execute on function asistente.jobs_vencidos(timestamptz, int)
  to scheduler_coordinator;
grant execute on function asistente.job_claim(text, uuid, timestamptz, text, jsonb)
  to scheduler_coordinator;

-- El ejecutor mantiene vivo su lease, abre su contexto y reporta. No reclama:
-- no elige que le toca.
grant execute on function asistente.job_heartbeat(uuid, text)      to job_executor;
grant execute on function asistente.job_finalize(uuid, text, text, text)
  to job_executor;
grant execute on function asistente.job_abrir_contexto(uuid, text) to job_executor;

-- El monitor ve numeros. Nada mas.
grant execute on function asistente.job_salud(timestamptz) to monitor_ro;

-- 'job_cerrar_turno' y 'job_intento_vigente' no se otorgan a nadie: son piezas
-- internas. Se llaman desde el cuerpo de las otras, que corren como el dueño.
