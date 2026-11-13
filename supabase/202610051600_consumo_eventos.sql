-- =============================================================================
--  CONSUMO_EVENTOS  -  cada llamada de IA, con de donde vino y cuanto costo
-- =============================================================================
--
--  POR QUE EXISTE (05/10/2026, auditoria de consumo y costos)
--  ----------------------------------------------------------
--  'asistente.usage_daily' agrega por (organization_id, dia) y nada mas. No
--  sabe de que proveedor fue el gasto, ni de que modelo, ni de que servicio,
--  ni de que conversacion. Con esa fila no se puede responder "cuanto costo
--  Vision" ni "cuanto costo esta conversacion", y son las dos preguntas que
--  mas se hacen cuando la factura sube.
--
--  Lo que lo volvio urgente, medido ese dia sobre 23 dias de Rapilink:
--
--      lo que calculaba el sistema      $2.37
--      lo que bajo el saldo del proveedor  $6.78     (sin recargas)
--      razon                               2.86x
--
--  Tres causas, y ninguna era un error de calculo:
--    1. Vision llama a DeepSeek y NO se contabilizaba (dos fallos a la vez:
--       no llamaba a anotar(), y corria fuera del ContextVar del turno).
--    2. La transcripcion recibe 'usage' de OpenAI y lo descartaba.
--    3. Las evaluaciones y las pruebas gastan saldo REAL y, por diseño, no se
--       contaban en ningun lado -- ni siquiera para saber cuanto fueron.
--
--  La tarifa, en cambio, no era la causa: comparada ese dia contra la oficial,
--  SOBREestimaba ~45%. O sea que la brecha real de llamadas sin contar es
--  todavia mayor que 2.86x.
--
--  'origin' ES LA COLUMNA QUE DESTRABA EL PROBLEMA
--  ------------------------------------------------
--  Hasta ahora habia que elegir entre contar las pruebas --y entonces el tope
--  del tenant saltaba por trabajo que nadie facturo-- o no contarlas, y
--  entonces no saber cuanto se gasto en ellas. Con 'origin' se puede hacer lo
--  correcto: registrar TODO, y que el tope mire solo 'production'.
--
--  SOLO SE AGREGA
--  --------------
--  Ninguna fila se actualiza ni se borra desde el motor. 'usage_daily' sigue
--  existiendo y sigue siendo lo que lee el frontend de hoy: esta tabla es la
--  fuente detallada, no su reemplazo.
--
--  SIN PII
--  -------
--  Ni texto del cliente, ni nombres, ni telefonos. 'conversation_id' y
--  'message_id' son identificadores internos y sirven para cruzar; lo que se
--  guarda del contenido es, como mucho, cuantos tokens tenia.
-- =============================================================================

create table if not exists asistente.consumo_eventos (
  id                  uuid primary key default gen_random_uuid(),
  organization_id     uuid not null references public.organization(id) on delete cascade,
  creado_en           timestamptz not null default now(),

  --  QUE se gasto. 'embeddings' y 'tts' estan declarados aunque todavia no
  --  escriban: el dia que lo hagan no hace falta otra migracion, y mientras
  --  tanto la lista documenta el alcance previsto.
  servicio            text not null
                      check (servicio in ('conversation', 'vision',
                                          'transcription', 'embeddings',
                                          'tts')),
  proveedor           text not null,
  modelo              text not null,

  --  DE DONDE vino. Lo que decide si entra o no en el tope del tenant.
  origen              text not null default 'production'
                      check (origen in ('production', 'evaluation', 'test')),

  conversation_id     uuid,
  message_id          uuid,

  --  Tokens. 'cached_input_tokens' es un SUBCONJUNTO de 'input_tokens', no se
  --  suma aparte: asi los reporta DeepSeek y asi los cobra.
  input_tokens        bigint not null default 0,
  cached_input_tokens bigint not null default 0,
  output_tokens       bigint not null default 0,
  --  Los que el proveedor cobra como salida aunque no se vean (DeepSeek y
  --  Anthropic los exponen aparte). Se guardan para poder explicar una
  --  factura que no cuadra con el texto que se vio.
  reasoning_tokens    bigint not null default 0,
  --  Para lo que NO se cobra por tokens: TTS cobra por caracteres.
  caracteres          bigint not null default 0,

  costo_usd           numeric(14,8) not null default 0,
  --  FALSE significa "hubo gasto y no sabemos cuanto", que no es lo mismo que
  --  "no hubo gasto". Sin esta columna las dos cosas se ven como un 0 y nadie
  --  puede distinguirlas -- que es exactamente el agujero que esta tabla
  --  viene a tapar.
  hay_tarifa          boolean not null default false,

  --  Detalle tecnico minimo (duracion, si fue reintento, codigo de error).
  --  Nunca contenido.
  metadatos           jsonb not null default '{}'::jsonb,

  check (input_tokens >= 0 and output_tokens >= 0 and caracteres >= 0),
  check (cached_input_tokens <= input_tokens),
  --  Un costo sin tarifa solo puede ser 0. Si alguna vez llega otra cosa, es
  --  un estimado y esta tabla no guarda estimados.
  check (hay_tarifa or costo_usd = 0)
);

comment on table asistente.consumo_eventos is
  'Una fila por llamada de IA (05/10/2026). Distingue servicio, proveedor, '
  'modelo y ORIGEN: production cuenta para max_costo_usd_mes, evaluation y '
  'test se registran pero no. Solo se AGREGA. Sin PII. usage_daily sigue '
  'siendo el agregado diario que lee el frontend.';

comment on column asistente.consumo_eventos.origen is
  'production entra en el tope del tenant; evaluation y test se cuentan para '
  'saber cuanto costaron, pero no bloquean a nadie.';

comment on column asistente.consumo_eventos.hay_tarifa is
  'false = hubo consumo y NO se sabe cuanto costo. Distinto de costo cero.';

comment on column asistente.consumo_eventos.cached_input_tokens is
  'Subconjunto de input_tokens, no se suma aparte. Asi lo reporta y lo cobra el proveedor.';

--  El indice que sostiene el tope: gasto de produccion del mes, por empresa.
--  Parcial a proposito -- las filas de prueba son las que mas van a crecer y
--  no hacen falta para esta pregunta.
create index if not exists consumo_eventos_tope_idx
  on asistente.consumo_eventos (organization_id, creado_en)
  where origen = 'production';

--  Para el desglose del panel: por servicio y por dia.
create index if not exists consumo_eventos_panel_idx
  on asistente.consumo_eventos (organization_id, creado_en desc, servicio);

--  "Cuanto costo esta conversacion".
create index if not exists consumo_eventos_conv_idx
  on asistente.consumo_eventos (conversation_id)
  where conversation_id is not null;

--  Para encontrar rapido lo que se gasto sin saber cuanto.
create index if not exists consumo_eventos_sin_tarifa_idx
  on asistente.consumo_eventos (organization_id, modelo)
  where hay_tarifa = false;

-- =============================================================================
--  AISLAMIENTO  -  mismo patron que identidad_eventos
-- =============================================================================

alter table asistente.consumo_eventos enable row level security;
alter table asistente.consumo_eventos force row level security;

drop policy if exists consumo_eventos_lee on asistente.consumo_eventos;
create policy consumo_eventos_lee on asistente.consumo_eventos
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists consumo_eventos_anota on asistente.consumo_eventos;
create policy consumo_eventos_anota on asistente.consumo_eventos
  for insert to app_backend
  with check (organization_id = asistente.org_actual());

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_backend') then
    grant select, insert on asistente.consumo_eventos to app_backend;
  end if;
end $$;

-- =============================================================================
--  EL GASTO QUE CUENTA PARA EL TOPE
-- =============================================================================
--  Reemplaza a asistente.gasto_del_mes, que sumaba usage_daily entero. La
--  diferencia esta en el 'where origen': un tope que sube porque alguien
--  corrio los casos dorados no protege de nada y ademas miente.
--
--  Cae a usage_daily mientras no haya eventos del mes. Sin eso, el dia que
--  esta migracion se aplica el gasto del mes volveria a cero de golpe y el
--  tope quedaria sin memoria justo en el cambio.

create or replace function asistente.gasto_produccion_del_mes(
  p_org uuid, p_fecha date default current_date)
returns numeric
language sql stable
as $$
  select greatest(
    coalesce((select sum(costo_usd)
                from asistente.consumo_eventos
               where organization_id = p_org
                 and origen = 'production'
                 and creado_en >= date_trunc('month', p_fecha)
                 and creado_en <  date_trunc('month', p_fecha) + interval '1 month'), 0),
    coalesce((select sum(costo_usd)
                from asistente.usage_daily
               where organization_id = p_org
                 and dia >= date_trunc('month', p_fecha)::date
                 and dia <  (date_trunc('month', p_fecha) + interval '1 month')::date), 0)
  );
$$;

comment on function asistente.gasto_produccion_del_mes(uuid, date) is
  'Gasto facturable del mes: solo origen=production. Toma el mayor entre los '
  'eventos y usage_daily para que el corte de la migracion no borre el gasto '
  'ya acumulado del mes en curso.';
