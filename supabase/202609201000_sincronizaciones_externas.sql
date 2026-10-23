-- =============================================================================
-- B4: LA COLA DE EFECTOS EXTERNOS  (contrato del relevo §3.6)
-- =============================================================================
-- Escalar tiene que producir dos cosas afuera: un caso en el CRM y --cuando
-- corresponde-- un ticket en el sistema del ISP. Hasta hoy, si alguna fallaba,
-- el except la registraba en el log y la intencion se perdia: la conversacion
-- quedaba escalada, visible en la bandeja, y sin caso donde nadie lo notaba
-- hasta que alguien lo buscaba.
--
-- Esta tabla guarda la INTENCION, no el resultado. Se inserta en la misma
-- transaccion que la transicion que la necesita; el primer intento corre en
-- linea, fuera de esa transaccion. Si falla o el proceso muere, queda
-- 'pendiente' y el reconciliador (T20) la retoma.
--
-- LOS DOS TIPOS NO SE RECONCILIAN IGUAL, y eso gobierna el diseño (gate Q2,
-- cerrado el 20/09/2026, SPEC/auditorias/B4-Q2-WISPHUB.md):
--
--   crear_caso    SI se reintenta. El nombre del caso lleva el conversation_id
--                 y es unico por organizacion: un repetido da 400, se busca y
--                 se adopta el que ya existe.
--   crear_ticket  NO se reintenta cuando el resultado quedo incierto. La API de
--                 WispHub no acepta clave de idempotencia, no hay filtro para
--                 buscar el ticket, reescribe el asunto y recorta el historico.
--                 Un incierto queda 'desconocida' y espera a una persona.
--                 Es preferible un ticket pendiente de revision a dos visitas
--                 tecnicas al mismo cliente.

create table if not exists asistente.sincronizaciones_externas (
  id                 uuid primary key default gen_random_uuid(),
  organization_id    uuid not null references public.organization(id) on delete cascade,
  conversation_id    uuid not null,

  tipo               text not null
    constraint sincronizaciones_tipo_check
    check (tipo in ('crear_caso', 'crear_ticket', 'cerrar_caso', 'cerrar_ticket')),

  -- 'desconocida' NO es 'fallida_definitiva': el pedido pudo llegar al sistema
  -- externo y no se sabe si produjo el efecto. No se reintenta a ciegas.
  estado             text not null default 'pendiente'
    constraint sincronizaciones_estado_check
    check (estado in ('pendiente', 'en_curso', 'hecha',
                      'fallida_definitiva', 'desconocida')),

  -- EXACTAMENTE lo que habia que hacer cuando se decidio. El reconciliador no
  -- reconstruye el efecto con la config actual, que pudo cambiar entre el
  -- intento y el reintento. Solo datos minimos y sanitizados: nunca payloads
  -- crudos, argumentos completos ni datos del cliente (X19).
  datos_version      smallint not null default 1,
  datos_intencion    jsonb not null default '{}'::jsonb
    constraint sincronizaciones_datos_objeto check (jsonb_typeof(datos_intencion) = 'object'),

  intentos           integer not null default 0,
  proximo_intento_en timestamptz,

  ultimo_error_clase text
    constraint sincronizaciones_error_clase_check
    check (ultimo_error_clase is null
           or ultimo_error_clase in ('transitorio', 'permanente', 'incierto')),
  -- Solo el codigo y el estado HTTP. NUNCA el cuerpo de la respuesta.
  ultimo_error_codigo text,

  referencia_externa text,
  clave_idempotencia text not null,

  creado_en          timestamptz not null default now(),
  actualizado_en     timestamptz not null default now(),

  -- La clave se deriva de (conversacion, tipo, evento que la origino), asi que
  -- la misma transicion no puede encolar dos veces el mismo efecto.
  constraint sincronizaciones_clave_uq unique (organization_id, clave_idempotencia),

  -- Tenant-scoped: una sincronizacion de la empresa A no puede apuntar a una
  -- conversacion de B, ni siquiera bajo un rol con BYPASSRLS.
  constraint sincronizaciones_conversacion_fk
    foreign key (organization_id, conversation_id)
    references asistente.conversations(organization_id, id) on delete cascade,

  -- Un trabajo que espera su turno tiene que decir CUANDO. Sin esto, un
  -- 'pendiente' sin hora quedaria invisible para el reconciliador, que
  -- selecciona por proximo_intento_en.
  constraint sincronizaciones_pendiente_con_hora
    check (estado <> 'pendiente' or proximo_intento_en is not null),

  -- Un resultado terminal dice por que. 'hecha' no necesita clase de error;
  -- las otras dos si, o el operador ve un fallo sin causa.
  constraint sincronizaciones_terminal_con_causa
    check (estado not in ('fallida_definitiva', 'desconocida')
           or ultimo_error_clase is not null)
);

-- La consulta del reconciliador, y la unica que corre cada 5 minutos: que hay
-- para hacer AHORA. Indice parcial para que su tamaño no dependa del historico:
-- lo terminado sale del indice solo.
create index if not exists sincronizaciones_elegibles_idx
  on asistente.sincronizaciones_externas (organization_id, proximo_intento_en)
  where estado in ('pendiente', 'en_curso');

-- La del panel: que le falta a ESTA conversacion.
create index if not exists sincronizaciones_conversacion_idx
  on asistente.sincronizaciones_externas (organization_id, conversation_id, creado_en desc);

-- Lo que espera a una persona, en toda la organizacion. Es la consulta de
-- "que quedo sin resolver" y tiene que ser barata aunque la tabla crezca.
create index if not exists sincronizaciones_revision_idx
  on asistente.sincronizaciones_externas (organization_id, actualizado_en desc)
  where estado in ('desconocida', 'fallida_definitiva');

alter table asistente.sincronizaciones_externas enable row level security;
alter table asistente.sincronizaciones_externas force row level security;
grant select, insert, update on asistente.sincronizaciones_externas to app_backend;
drop policy if exists tenant_aislado on asistente.sincronizaciones_externas;
create policy tenant_aislado on asistente.sincronizaciones_externas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

comment on table asistente.sincronizaciones_externas is
  'Cola de efectos externos de una transicion (B4). Guarda la INTENCION, no el '
  'resultado: el reconciliador no reconstruye el efecto con la config actual. '
  'crear_caso se reintenta (nombre unico con conversation_id); crear_ticket con '
  'resultado incierto queda en desconocida y NO se reintenta -- ver gate Q2.';

comment on column asistente.sincronizaciones_externas.estado is
  'desconocida = el pedido pudo llegar al sistema externo y no se sabe si '
  'produjo el efecto. NO es fallida_definitiva y no se reintenta a ciegas: '
  'queda visible en la conversacion, para revision humana.';

comment on column asistente.sincronizaciones_externas.datos_intencion is
  'Exactamente lo que habia que hacer cuando se decidio, con esquema cerrado '
  'por tipo y datos_version. Solo datos minimos y sanitizados: nunca payloads '
  'crudos, argumentos completos ni datos del cliente.';
