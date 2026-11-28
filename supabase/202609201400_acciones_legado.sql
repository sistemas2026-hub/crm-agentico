-- =============================================================================
-- G3: EL LEGADO DE ACCIONES PROPUESTAS  (contrato del relevo §11.4, X24, I6, I12)
-- =============================================================================
-- Hay 36 acciones en 'pendiente' que nadie propuso desde una conversacion viva
-- (A5): quedaron de antes de que existiera el vinculo. Ejecutarlas hoy seria
-- crear 34 tickets reales por problemas de hace mas de una semana, con los
-- argumentos congelados de entonces y sin la revalidacion de §3.7 -- que es
-- justo lo que X24 prohibe.
--
-- El contrato decide que hacer con ellas: las obsoletas se CANCELAN, con
-- evento y motivo; las que sigan haciendo falta se vuelven a proponer desde el
-- contexto actual. Lo que faltaba no era la decision, sino que el sistema
-- permitiera ejecutarla.
--
-- QUE SE AGREGA
-- -------------
--   1. 'cancelada' como estado declarado. Hasta ahora 'estado' era texto libre
--      --se podia escribir cualquier cosa-- y lo mas cercano era 'rechazada'.
--      No son lo mismo: rechazada es "alguien la evaluo y dijo que no";
--      cancelada es "quedo obsoleta". En un registro que existe para auditar,
--      la diferencia es el registro entero.
--
--   2. asistente.acciones_eventos, el expediente de cada accion.
--      I12 pide que toda transicion inserte su evento en la MISMA transaccion
--      que el cambio de estado. relevo_eventos no sirve para esto: su
--      conversation_id es NOT NULL con FK a conversations, y estas 36 no
--      tienen conversacion. Por eso una tabla propia, con el mismo vocabulario
--      de tipos y conversation_id NULLABLE -- cuando B5 traiga la columna, el
--      evento la lleva tambien y las dos vistas se cruzan.
--
-- QUE NO CAMBIA
-- -------------
-- Ninguna fila existente. No hay UPDATE masivo (§11.5): las 36 siguen
-- 'pendiente' hasta que una persona las cancele una por una desde la pantalla.
-- No se agrega conversation_id a acciones_propuestas: eso es B5.

-- El check va NOT VALID a proposito: no escanea la tabla --sin lock largo
-- sobre datos de produccion-- y aun asi valida todo INSERT y UPDATE nuevo, que
-- es donde puede entrar un estado inventado. Las filas viejas se validan
-- aparte, con VALIDATE CONSTRAINT, cuando produccion lo decida.
alter table asistente.acciones_propuestas
  drop constraint if exists acciones_propuestas_estado_declarado;
alter table asistente.acciones_propuestas
  add constraint acciones_propuestas_estado_declarado
  check (estado in ('pendiente', 'aprobada', 'rechazada', 'cancelada'))
  not valid;

-- Una cancelacion sin motivo es una fila que no explica nada, y estas existen
-- para explicar por que 36 acciones no se ejecutaron nunca.
alter table asistente.acciones_propuestas
  drop constraint if exists acciones_propuestas_cancelada_con_motivo;
alter table asistente.acciones_propuestas
  add constraint acciones_propuestas_cancelada_con_motivo
  check (estado <> 'cancelada' or motivo_rechazo is not null)
  not valid;

create table if not exists asistente.acciones_eventos (
  id                 uuid primary key default gen_random_uuid(),
  organization_id    uuid not null references public.organization(id) on delete cascade,
  accion_id          uuid not null references asistente.acciones_propuestas(id) on delete cascade,
  -- NULLABLE, al reves que en relevo_eventos: una accion de legado no tiene
  -- conversacion, y esa ausencia es justamente lo que la hace de legado.
  conversation_id    uuid references asistente.conversations(id) on delete set null,
  tipo               text not null
    constraint acciones_eventos_tipo_check check (tipo in (
      'accion_aprobada', 'accion_rechazada', 'accion_cancelada',
      'accion_vencida', 'accion_desconocida',
      -- Un intento de aprobar que la guarda de X24 rechazo. Se registra
      -- porque un intento repetido contra el legado es algo que alguien
      -- deberia poder ver, no solo una respuesta 409 que se pierde.
      'accion_aprobacion_rechazada')),
  motivo             text,
  actor_tipo         text not null
    constraint acciones_eventos_actor_tipo_check
    check (actor_tipo in ('operador', 'sistema')),
  actor_nombre       text,
  datos              jsonb not null default '{}'::jsonb
    constraint acciones_eventos_datos_objeto check (jsonb_typeof(datos) = 'object'),
  creado_en          timestamptz not null default now(),
  -- Quien cancela da la cara: una cancelacion administrativa sin nombre no se
  -- puede auditar. El sistema no cancela nada por su cuenta (X24).
  constraint acciones_eventos_operador_identificado
    check (actor_tipo <> 'operador' or actor_nombre is not null),
  constraint acciones_eventos_cancelada_con_motivo
    check (tipo <> 'accion_cancelada' or motivo is not null)
);

create index if not exists acciones_eventos_accion_idx
  on asistente.acciones_eventos (organization_id, accion_id, creado_en);

alter table asistente.acciones_eventos enable row level security;
alter table asistente.acciones_eventos force row level security;

-- Solo SELECT e INSERT, igual que relevo_eventos: un expediente que se puede
-- corregir no es un expediente. Ninguna ruta del motor puede editar ni borrar
-- un evento ya escrito.
grant select, insert on asistente.acciones_eventos to app_backend;

create policy tenant_aislado on asistente.acciones_eventos
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
