-- =============================================================================
--  MARCAS DE TV QUE NADIE CARGO TODAVIA
-- =============================================================================
--
--  Por que existe
--  --------------
--  Desde el 10/09/2026 las instrucciones de sintonizacion viven en un catalogo
--  administrable (TenantConfig.guias_tv). Cuando un cliente nombra una marca
--  que no tiene guia propia, el agente NO se queda sin nada que decir: usa la
--  guia general y sigue atendiendo. Que falte la guia especifica no es motivo
--  de escalamiento -- la general resuelve la mayoria.
--
--  Pero esa marca es informacion que la empresa no tenia. Sin anotarla, cada
--  cliente con un televisor de marca nueva recibe la guia general una y otra
--  vez, y nadie se entera nunca de que valdria la pena cargar la suya. Esta
--  tabla es la cola de trabajo para que una persona la escriba desde
--  /settings/guias-tv.
--
--  LA MARCA SE GUARDA TAL CUAL LA ESCRIBIO EL CLIENTE
--  --------------------------------------------------
--  'Sansung', 'LG smart', 'kalley'. Sin normalizar, sin corregir la ortografia
--  y sin sustituir el valor original por una version limpia: quien despues
--  cree la guia necesita ver COMO la nombra la gente, no como deberia
--  llamarse. Si diez clientes escriben 'Sansung', eso es un dato sobre el
--  mundo, no un error que haya que tapar.
--
--  Para agrupar sin perder el original va 'marca_normalizada' APARTE -- misma
--  idea que 'contenido' y 'contenido_anonimizado' en asistente.messages: dos
--  columnas, no una pisando a la otra.
--
--  POR QUE NO ES CONFIGURACION DEL TENANT
--  --------------------------------------
--  guias_tv es lo que alguien DECIDIO. Esto es lo que el mundo trajo, y crece
--  solo con cada conversacion. Mezclarlos haria que la config del tenant
--  cambie de version cada vez que un cliente menciona un televisor.
-- =============================================================================

create table if not exists asistente.marcas_tv_desconocidas (
  id               uuid primary key default gen_random_uuid(),
  organization_id  uuid not null references public.organization(id) on delete cascade,
  -- EXACTAMENTE como la escribio el cliente. No se toca.
  marca            text not null,
  -- Solo para agrupar y deduplicar (sin tildes, en minusculas). El original
  -- vive arriba y es el que se le muestra a quien va a crear la guia.
  marca_normalizada text not null,
  -- De donde salio. Sin esto la marca es un nombre suelto: quien la revise no
  -- puede leer que televisor tenia el cliente ni si la guia general le sirvio.
  conversation_id  uuid references asistente.conversations(id) on delete set null,
  -- 'pendiente' hasta que alguien cargue la guia o decida que no hace falta.
  estado           text not null default 'pendiente'
                   check (estado in ('pendiente', 'atendida')),
  creado_en        timestamptz not null default now(),
  -- Cuantas veces volvio a aparecer. Una marca que sale treinta veces merece
  -- su guia antes que una que salio una vez, y esa prioridad se pierde si
  -- cada mencion es una fila mas en una lista larga.
  veces            integer not null default 1,
  visto_por_ultima_vez timestamptz not null default now()
);

-- UNA FILA POR MARCA Y CONVERSACION, no una por mencion.
--
-- Dentro de una misma conversacion el cliente puede repetir la marca varias
-- veces -- porque el agente vuelve a preguntar, porque reintenta la
-- sintonizacion, porque el turno se rehace. Sin esta restriccion, una sola
-- conversacion llena la cola de trabajo con la misma marca y la vuelve
-- ilegible justo para lo que sirve.
--
-- La unicidad es por conversacion y NO por marca a secas a proposito: que dos
-- clientes distintos nombren 'Kalley' son dos hechos, y perder el segundo
-- borraria la señal de que esa marca aparece seguido.
create unique index if not exists marcas_tv_una_por_conversacion
  on asistente.marcas_tv_desconocidas (organization_id, marca_normalizada, conversation_id)
  where conversation_id is not null;

comment on table asistente.marcas_tv_desconocidas is
  'Marcas de televisor que un cliente nombro y no tienen guia de sintonizacion '
  'cargada. Cola de trabajo para crearlas desde /settings/guias-tv. La marca se '
  'conserva tal cual la escribio el cliente.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.marcas_tv_desconocidas enable row level security;
alter table asistente.marcas_tv_desconocidas force row level security;
grant select, insert, update, delete on asistente.marcas_tv_desconocidas to app_backend;

drop policy if exists tenant_aislado on asistente.marcas_tv_desconocidas;
create policy tenant_aislado on asistente.marcas_tv_desconocidas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
