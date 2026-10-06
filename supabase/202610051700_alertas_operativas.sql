-- =============================================================================
--  ALERTAS OPERATIVAS  --  que alguien se entere antes de que se corte
-- =============================================================================
--
--  POR QUE EXISTE (05/10/2026, auditoria de alertas de saldo y conciliacion)
--  -------------------------------------------------------------------------
--  Las dos senales ya existian y nadie las miraba.
--
--    'usage_daily.saldo_proveedor_usd' guarda la foto diaria del saldo desde
--    hace semanas. El 05/10/2026 valia 0.72 USD -- unos tres dias de consumo
--    al ritmo medido -- y lo supo una auditoria a mano, no el sistema.
--
--    'consumo.veredicto_conciliacion' calcula desde hace tiempo que el
--    proveedor cobro 2.86 veces lo que el sistema contaba. Tambien lo supo
--    una persona que fue a mirar.
--
--  Un dato que solo se ve cuando alguien lo busca no es monitoreo. Esta tabla
--  es donde el reloj deja escrito lo que encontro, para que la proxima vez el
--  aviso llegue sin que nadie vaya a buscarlo.
--
--  POR QUE UNA TABLA Y NO SOLO UN LOG
--  -----------------------------------
--  Porque hace falta ESTADO. Sin el, cada barrido --uno por hora-- volveria a
--  gritar lo mismo, y una alerta que aparece 24 veces por dia se deja de leer
--  en dos dias. La regla es "una activa por (empresa, tipo, proveedor)", y
--  tiene que sobrevivir a un reinicio de 'motor-reloj': un dict en memoria se
--  vacia con el proceso y el primer barrido posterior duplicaria todo.
--
--  LA EXCLUSION ES ESTRUCTURAL, NO UN 'SELECT' PREVIO
--  ---------------------------------------------------
--  El indice unico parcial de mas abajo es el que impide el duplicado, con
--  'insert ... on conflict do nothing'. Mismo criterio que
--  'asistente.operaciones_externas' (CLAUDE.md 12): un 'select' que mira si
--  ya existe y despues inserta tiene una carrera adentro, y aca ademas hay un
--  proceso que puede estar arrancando mientras otro termina de apagarse.
--
--  NO BLOQUEA NADA
--  ---------------
--  Escribir una fila aca no detiene a Dexter, no frena el tope, no recarga
--  nada y no cambia ninguna tarifa. Es una senal para una persona. Dejar sin
--  atender a los clientes de un ISP por una discrepancia contable seria
--  cambiar un problema de plata por uno de servicio.
--
--  SIN PII
--  -------
--  Ni texto, ni nombres, ni telefonos, ni conversaciones. Lo que se guarda es
--  una cifra, un umbral y de que se trata.
-- =============================================================================

create table if not exists asistente.alertas_operativas (
  id               uuid primary key default gen_random_uuid(),
  organization_id  uuid not null references public.organization(id) on delete cascade,
  creado_en        timestamptz not null default now(),

  tipo             text not null
                   check (tipo in ('saldo_bajo', 'divergencia_consumo')),
  gravedad         text not null
                   check (gravedad in ('warning', 'critical')),

  --  Obligatorio aunque hoy haya un solo proveedor con endpoint de saldo. Es
  --  parte de la clave de unicidad: el dia que se agregue otro, sus alertas
  --  conviven con estas en vez de pisarlas, y no hace falta otra migracion.
  proveedor        text not null,

  --  QUE se midio. Sin esto 'valor 7.2 / umbral 5' es ambiguo: puede ser una
  --  razon o pueden ser dolares. Una alerta que no se entiende sola obliga a
  --  leer el codigo que la escribio.
  metrica          text not null
                   check (metrica in ('saldo_usd', 'ratio', 'diferencia_usd')),
  valor            numeric(14,4) not null,
  umbral           numeric(14,4) not null,

  --  NULL = sigue vigente. Es la columna sobre la que trabaja el indice
  --  unico parcial: cerrar una alerta libera el lugar para la siguiente.
  resuelta_en      timestamptz,

  --  Contexto tecnico para poder explicar la cifra despues (dias comparables,
  --  ventana, que regla disparo, edad de la foto del saldo). Nunca contenido.
  metadatos        jsonb not null default '{}'::jsonb,

  check (resuelta_en is null or resuelta_en >= creado_en)
);

comment on table asistente.alertas_operativas is
  'Alertas de operacion que detecta motor-reloj (05/10/2026): saldo bajo del '
  'proveedor y divergencia entre el consumo calculado y la bajada real del '
  'saldo. Una activa por (empresa, tipo, proveedor), garantizado por indice '
  'unico parcial. No bloquea nada: es una senal para una persona. Sin PII.';

comment on column asistente.alertas_operativas.resuelta_en is
  'NULL mientras la condicion sigue cumpliendose. Al dejar de cumplirse se '
  'sella, y eso habilita que una recaida posterior genere una alerta NUEVA '
  'en vez de reabrir la vieja -- asi queda el historico de cuantas veces paso.';

comment on column asistente.alertas_operativas.metrica is
  'La unidad de valor/umbral. saldo_usd y diferencia_usd son dolares; ratio '
  'es la razon entre lo que cobro el proveedor y lo que calculamos.';

-- =============================================================================
--  LA REGLA DE ANTIRREPETICION, EN LA BASE
-- =============================================================================
--  Con esto, 'insert ... on conflict (organization_id, tipo, proveedor)
--  where resuelta_en is null do nothing' no puede crear una segunda alerta
--  activa del mismo asunto, venga del barrido que venga y reinicie el proceso
--  las veces que reinicie.

create unique index if not exists alertas_operativas_activa_idx
  on asistente.alertas_operativas (organization_id, tipo, proveedor)
  where resuelta_en is null;

--  El historico: "cuantas veces se quedo sin saldo este mes".
create index if not exists alertas_operativas_historico_idx
  on asistente.alertas_operativas (organization_id, creado_en desc);

-- =============================================================================
--  AISLAMIENTO  -  mismo patron que identidad_eventos y consumo_eventos
-- =============================================================================
--  Con una diferencia: aquellas son de solo agregar. Esta necesita UPDATE,
--  porque resolver una alerta es sellarla, no borrarla. El DELETE sigue sin
--  concederse: el historico es el dato.

alter table asistente.alertas_operativas enable row level security;
alter table asistente.alertas_operativas force row level security;

drop policy if exists alertas_operativas_lee on asistente.alertas_operativas;
create policy alertas_operativas_lee on asistente.alertas_operativas
  for select to app_backend
  using (organization_id = asistente.org_actual());

drop policy if exists alertas_operativas_anota on asistente.alertas_operativas;
create policy alertas_operativas_anota on asistente.alertas_operativas
  for insert to app_backend
  with check (organization_id = asistente.org_actual());

--  'using' Y 'with check': el primero acota que filas se pueden tocar, el
--  segundo que no se las pueda mover a otra empresa al tocarlas.
drop policy if exists alertas_operativas_resuelve on asistente.alertas_operativas;
create policy alertas_operativas_resuelve on asistente.alertas_operativas
  for update to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_backend') then
    grant select, insert, update on asistente.alertas_operativas to app_backend;
  end if;
end $$;
