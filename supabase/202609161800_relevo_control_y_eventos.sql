-- =============================================================================
--  CONTROL, ASIGNACION Y EVENTOS DEL RELEVO -- quien responde deja de vivir en la memoria del proceso
-- =============================================================================
--  B3.1 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md (§3.1, §3.3). Solo esquema.
--
--  Hoy "la IA responde o no" se deduce de dos banderas
--  (escalada_a_humano && necesita_atencion_humana) MAS un diccionario en la
--  memoria del proceso que puede divergir de ellas: una escalada con el CRM
--  caido pausa solo en memoria y se pierde en el siguiente despliegue (D9); un
--  caso cerrado afuera levanta la pausa solo en memoria (D10). Y quien tomo una
--  conversacion se pisa sin rastro (D4).
--
--  QUE SE AGREGA A asistente.conversations
--  ---------------------------------------
--    control              'ia' | 'humano'. Default 'ia': toda fila existente
--                         queda como hoy la ve cualquier camino que no la haya
--                         escalado. NO se backfillea desde las banderas de
--                         legado: el corte de control espera la revision de
--                         las 16 conversaciones reales (gate G8).
--    control_motivo       'escalada' | 'intervencion'. Presente si y solo si
--                         control = 'humano' (CHECK).
--    asignada_a_*         el operador a cargo: id (User.id de Django, uuid),
--                         nombre tal como era, y desde cuando. Solo con control
--                         humano (CHECK). El id puede faltar SOLO en el legado
--                         (tomada_por era texto libre); el nombre no.
--    pendiente_interno_*  "quedo algo por hacer de nuestro lado". Lo marca una
--                         persona; hace que la conversacion siga pidiendo
--                         accion humana aunque el ultimo mensaje sea suyo.
--    aviso_relevo         un aviso que no cambia el control. Hoy su unico
--                         valor: 'caso_externo_cerrado' (el caso se cerro en el
--                         CRM mientras una persona tenia la conversacion).
--    relevo_version       sube con cada transicion. Una accion de operador
--                         hecha sobre una version vieja responde 409.
--
--  QUE SE CREA: asistente.relevo_eventos
--  -------------------------------------
--  El expediente del relevo. SOLO se agrega: app_backend tiene SELECT e INSERT
--  y nada mas, asi que ninguna ruta del motor puede corregir o borrar un
--  evento. 'datos' lleva un esquema por tipo y version validado en codigo
--  (datos_version); aca solo se exige que sea un objeto. Nunca respuestas de
--  APIs externas ni datos del cliente (contrato X19).
--
--  QUE NO CAMBIA
--  -------------
--  Ninguna fila existente, ninguna bandera de legado, ninguna lectura. El
--  codigo que escribe control y eventos va en B3.2, en paralelo con las
--  banderas; el que decide con ellos, despues de G8.

alter table asistente.conversations
  add column if not exists control text not null default 'ia'
    constraint conversations_control_check check (control in ('ia', 'humano')),
  add column if not exists control_motivo text
    constraint conversations_control_motivo_check
    check (control_motivo in ('escalada', 'intervencion')),
  add column if not exists asignada_a_usuario_id uuid,
  add column if not exists asignada_a_nombre text,
  add column if not exists asignada_en timestamptz,
  add column if not exists pendiente_interno_desde timestamptz,
  add column if not exists pendiente_interno_nota text,
  add column if not exists aviso_relevo text
    constraint conversations_aviso_relevo_check
    check (aviso_relevo in ('caso_externo_cerrado')),
  add column if not exists relevo_version integer not null default 0;

-- Control humano <=> motivo. Una fila con control humano y sin motivo, o con
-- motivo y control de la IA, es un estado que no existe en el contrato (I1).
alter table asistente.conversations
  add constraint conversations_control_motivo_coherente
  check ((control = 'humano') = (control_motivo is not null));

-- Asignacion solo con control humano (I2), y nunca un id sin nombre.
alter table asistente.conversations
  add constraint conversations_asignacion_coherente
  check ((asignada_a_usuario_id is null and asignada_a_nombre is null)
         or (control = 'humano' and asignada_a_nombre is not null));

comment on column asistente.conversations.control is
  'Quien responde al cliente: ia | humano. Unica fuente para decidir la pausa '
  'una vez hecho el corte (B3). Default ia; sin backfill desde las banderas de '
  'legado hasta la revision G8.';

comment on column asistente.conversations.relevo_version is
  'Sube con cada transicion del relevo. Concurrencia optimista: una accion de '
  'operador sobre una version vieja responde 409.';

create table if not exists asistente.relevo_eventos (
  id                 uuid primary key default gen_random_uuid(),
  organization_id    uuid not null references public.organization(id) on delete cascade,
  conversation_id    uuid not null references asistente.conversations(id) on delete cascade,
  tipo               text not null
    constraint relevo_eventos_tipo_check check (tipo in (
      'escalada', 'intervencion', 'devolucion_solicitada', 'devuelta_a_ia',
      'devolucion_fallida', 'caso_externo_cerrado',
      'tomada', 'soltada', 'reasignada',
      'pendiente_interno_abierto', 'pendiente_interno_cerrado',
      'evaluacion_revisada',
      'accion_propuesta_duplicada', 'accion_aprobada', 'accion_rechazada',
      'accion_vencida', 'accion_cancelada', 'accion_desconocida',
      'cerrada')),
  datos_version      smallint not null default 1,
  actor_tipo         text not null
    constraint relevo_eventos_actor_tipo_check
    check (actor_tipo in ('ia', 'operador', 'sistema', 'cliente')),
  actor_usuario_id   uuid,
  actor_nombre       text,
  datos              jsonb not null default '{}'::jsonb
    constraint relevo_eventos_datos_objeto check (jsonb_typeof(datos) = 'object'),
  clave_idempotencia text,
  creado_en          timestamptz not null default now(),
  -- Un evento de operador dice quien fue.
  constraint relevo_eventos_operador_identificado
    check (actor_tipo <> 'operador' or actor_nombre is not null)
);

create index if not exists relevo_eventos_conv_idx
  on asistente.relevo_eventos (organization_id, conversation_id, creado_en);

-- La misma transicion reintentada no deja dos eventos.
create unique index if not exists relevo_eventos_clave_uq
  on asistente.relevo_eventos (organization_id, conversation_id, clave_idempotencia)
  where clave_idempotencia is not null;

alter table asistente.relevo_eventos enable row level security;
alter table asistente.relevo_eventos force row level security;

-- SOLO select e insert: el expediente no se corrige ni se borra desde el motor.
grant select, insert on asistente.relevo_eventos to app_backend;

drop policy if exists tenant_aislado on asistente.relevo_eventos;
create policy tenant_aislado on asistente.relevo_eventos
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

comment on table asistente.relevo_eventos is
  'Expediente del relevo IA <-> humano (SPEC/CONTRATO_RELEVO_IA_HUMANO.md §3.3). '
  'Solo se agrega: app_backend tiene SELECT e INSERT. datos: esquema por tipo y '
  'datos_version validado en codigo; nunca payloads externos ni datos del cliente.';
