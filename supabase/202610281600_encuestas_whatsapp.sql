-- =============================================================================
--  ENCUESTAS POR WHATSAPP  -  como califico el cliente la atencion de su caso
-- =============================================================================
--
--  Por que existe (28/10/2026)
--  ---------------------------
--  El CRM tiene encuestas de satisfaccion, pero salen por CORREO y solo si el
--  caso tiene un contacto con correo: en Rapilink no tiene ninguno, asi que
--  no sale ninguna. El canal real del cliente es WhatsApp.
--
--  Al cerrar un caso con chat detras, el motor le manda una plantilla con
--  botones ("Excelente", "Buena"...). La respuesta es el boton que toca.
--
--  POR QUE EN EL MOTOR Y NO EN EL CRM
--  ----------------------------------
--  La respuesta la recibe el webhook, que es del motor. Escribirla en el CRM
--  seria una escritura hacia afuera SIN una persona detras -- la frontera la
--  manda por la puerta autonoma, y en produccion esa puerta no escribe
--  (AUTONOMIA_2_NO_ACTIVA). La nota se perderia sin que nadie lo note.
--  Guardarla aca es como guardar un mensaje que llega: no es un efecto.
--
--  UNA POR CASO, Y SE RESERVA ANTES DE ENVIAR
--  ------------------------------------------
--  La fila se inserta ANTES de mandar la plantilla ("guardar primero, entregar
--  despues"), y la unicidad (organization_id, caso_id) es la que impide la
--  segunda: un caso reabierto y vuelto a cerrar no recibe otra encuesta. Se
--  excluye por clave, nunca por un select previo -- ahi vive la carrera.
--
--  SIN DATOS DEL CLIENTE
--  ---------------------
--  Ni telefono ni nombre: para responderle se usa la conversacion, y para
--  medir alcanza el caso. 'responsable' es la persona del equipo que tenia el
--  caso al cerrarse (lo manda el CRM), para ver la calidad por persona.
-- =============================================================================

create table if not exists asistente.encuestas_whatsapp (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- El caso del CRM (su id, como texto: el caso vive en otro esquema).
  caso_id         text not null,
  conversation_id uuid references asistente.conversations(id) on delete set null,
  plantilla       text not null,
  -- reservada -> enviada | fallida; enviada -> respondida.
  estado          text not null default 'reservada'
                  check (estado in ('reservada', 'enviada', 'fallida', 'respondida')),
  -- El id del mensaje de la plantilla en Meta. La respuesta llega con
  -- 'context.id' = este valor: es como se sabe a que encuesta responde.
  wamid           text,
  responsable_id     text,
  responsable_nombre text,
  area            text,
  enviada_en      timestamptz,
  vence_en        timestamptz not null,
  -- El texto del boton que toco, y el puntaje que la config le asigna.
  opcion          text,
  puntaje         smallint check (puntaje between 1 and 5),
  respondida_en   timestamptz,
  creado_en       timestamptz not null default now(),
  unique (organization_id, caso_id)
);

create unique index if not exists encuestas_whatsapp_wamid_idx
  on asistente.encuestas_whatsapp (organization_id, wamid) where wamid is not null;
create index if not exists encuestas_whatsapp_fecha_idx
  on asistente.encuestas_whatsapp (organization_id, enviada_en desc);

comment on table asistente.encuestas_whatsapp is
  'Una encuesta de satisfaccion por caso cerrado con chat, y el boton que toco el '
  'cliente. Sin telefono ni nombre del cliente.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.encuestas_whatsapp enable row level security;
alter table asistente.encuestas_whatsapp force row level security;
grant select, insert, update on asistente.encuestas_whatsapp to app_backend;

drop policy if exists tenant_aislado on asistente.encuestas_whatsapp;
create policy tenant_aislado on asistente.encuestas_whatsapp
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
