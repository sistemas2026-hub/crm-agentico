-- =============================================================================
--  EVENTOS DE IDENTIDAD -- el embudo bloqueo -> verificacion -> confirmacion
-- =============================================================================
--  Por que existe (23/09/2026, Fase 1 de "completar el ciclo de identidad")
--  -----------------------------------------------------------------------
--  El motor ya frena en codigo toda herramienta que necesita saber QUIEN es el
--  cliente (IDENTIDAD_NO_VERIFICADA, IDENTIDAD_NO_RESUELTA) y le pide al
--  modelo que consiga el dato. Lo que pasa DESPUES lo decide el modelo dos
--  veces: si llama a verificar, y si llama a confirmar. Medido sobre 45 dias
--  de Rapilink: 79 bloqueos en 49 conversaciones; 45 verificaron despues, 33
--  confirmaron. 16 de 49 (un tercio) nunca completaron la identidad.
--
--  Esa medicion se hizo a mano sobre asistente.tool_calls, y tiene un hueco
--  que la tabla no puede cerrar: la fila de 'verificar_identidad_por_cedula'
--  dice exito=true tanto si encontro al cliente como si no (el resultado
--  negativo es un dato, no un error). Tampoco dice que esperaba el sistema
--  despues del bloqueo (la cedula, o el nombre para confirmar).
--
--  Aqui se anota cada paso del embudo con su resultado y con lo que el motor
--  esperaba a continuacion. Solo se AGREGA. La escalada por duda de identidad
--  NO se repite aqui: ya vive en asistente.relevo_eventos (tipo 'escalada',
--  datos.motivo). Los pasos "dato pedido" y "dato recibido" tampoco: exigen un
--  estado pendiente que hoy no existe en codigo (es la Fase 2).
--
--  SIN PII, A PROPOSITO. No hay cedula, ni nombre, ni telefono, ni texto del
--  cliente: solo etapa, motivo de vocabulario fijo, herramienta y rol. Lo que
--  se quiere contar es cuantos llegan al final, no quienes.
-- =============================================================================

create table if not exists asistente.identidad_eventos (
  id               uuid primary key default gen_random_uuid(),
  organization_id  uuid not null references public.organization(id) on delete cascade,
  conversation_id  uuid,
  rol              text,
  herramienta      text,
  etapa            text not null
                   check (etapa in ('bloqueo',
                                    'verificacion_ok', 'verificacion_fallo',
                                    'verificacion_ambigua',
                                    'confirmacion_ok', 'confirmacion_fallo')),
  motivo           text,
  siguiente_paso   text
                   check (siguiente_paso is null
                          or siguiente_paso in ('espera_cedula', 'espera_nombre', 'ninguno')),
  intentos         smallint,
  creado_en        timestamptz not null default now()
);

comment on table asistente.identidad_eventos is
  'Embudo de identidad por conversacion (Fase 1, 23/09/2026): bloqueo por '
  'identidad, verificacion (encontrado / no encontrado / ambiguo) y '
  'confirmacion del nombre, con lo que el motor esperaba despues. Solo se '
  'AGREGA. Sin PII: etapa, motivo fijo, herramienta y rol. La escalada por '
  'duda de identidad se lee de relevo_eventos, no se duplica aqui.';

create index if not exists identidad_eventos_org_idx
  on asistente.identidad_eventos (organization_id, creado_en desc);
create index if not exists identidad_eventos_conv_idx
  on asistente.identidad_eventos (conversation_id, creado_en);

alter table asistente.identidad_eventos enable row level security;
alter table asistente.identidad_eventos force row level security;

drop policy if exists identidad_eventos_lee on asistente.identidad_eventos;
create policy identidad_eventos_lee on asistente.identidad_eventos
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists identidad_eventos_anota on asistente.identidad_eventos;
create policy identidad_eventos_anota on asistente.identidad_eventos
  for insert to app_backend
  with check (organization_id = asistente.org_actual());

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_backend') then
    grant select, insert on asistente.identidad_eventos to app_backend;
  end if;
end $$;
