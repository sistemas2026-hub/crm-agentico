-- =============================================================================
--  HABILIDADES -- procedimientos que un agente carga cuando le hacen falta
-- =============================================================================
--  Que es una habilidad y en que se diferencia de un documento del corpus
--  ---------------------------------------------------------------------
--  El corpus (asistente.documents) es REFERENCIA: se fragmenta, se vectoriza,
--  y se recupera por parecido con la pregunta. Contesta "que dice la guia
--  sobre esto". Funciona bien cuando la pregunta se parece al texto.
--
--  Una habilidad es PROCEDIMIENTO: "cuando pase X, hace estos pasos". No se
--  fragmenta ni se busca por parecido, porque un procedimiento partido en
--  pedazos deja de ser un procedimiento -- si el paso 4 no entra en el top-k,
--  el agente hace 1, 2, 3, 5 y nadie se entera. Se carga ENTERA o no se carga.
--
--  Y se activa distinto. El corpus se recupera por similitud con lo que la
--  persona escribio; una habilidad hace falta en situaciones que el mensaje
--  no nombra. "Se me cayo el internet" no se parece en nada al texto de
--  "antes de agendar una visita, descarta una caida compartida" -- y es
--  justamente ahi donde hace falta. Por eso el disparador es 'cuando_usarla',
--  escrito por una persona, y no un vector.
--
--  Como se activa
--  --------------
--  El prompt lleva SIEMPRE el indice: codigo + cuando_usarla, una linea por
--  habilidad. Es barato. El cuerpo (los pasos) solo llega si el agente pide
--  esa habilidad por su codigo, con la herramienta interna cargar_habilidad.
--  Es divulgacion progresiva: el indice ocupa poco y el cuerpo se paga solo
--  cuando de verdad se usa.
--
--  Esto NO agranda la autonomia del modelo (PRD seccion 2): una habilidad no
--  ejecuta nada, es texto que entra al prompt. Toda garantia sigue viviendo
--  donde vivia -- listas blancas, precondiciones, aprobacion humana. Crece el
--  ALCANCE (cuanto sabe hacer bien), no la confianza.
--
--  Por que tabla propia y no un campo de tenant_config
--  --------------------------------------------------
--  Porque tiene ciclo de vida: se propone, se aprueba, se retira, se versiona.
--  Igual que un documento, y por el mismo motivo. Meterlo en la config seria
--  un blob que se pisa entero en cada edicion, sin historia de quien aprobo
--  que procedimiento -- y un procedimiento mal aprobado es exactamente lo que
--  despues hay que poder rastrear.
--
--  El estado inicial es 'propuesta', NUNCA 'vigente'. Vale para la que
--  escribe una persona y para la que propone el analista automatico: nada
--  entra al prompt de un agente sin que un humano lo apruebe. Mismo criterio
--  que asistente.herramientas_propuestas y asistente.acciones_propuestas.

create table if not exists asistente.habilidades (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- Estable y legible: es lo que el agente escribe para pedirla, y lo que
  -- aparece en la traza de la conversacion cuando la cargo.
  codigo          text not null,
  nombre          text not null,
  -- El disparador. Es lo UNICO que el agente ve sin cargar la habilidad, asi
  -- que decide si la carga o no. Se escribe como condicion observable ("el
  -- cliente pide instalacion en una direccion nueva"), no como tema.
  cuando_usarla   text not null,
  -- El procedimiento. Llega entero o no llega.
  pasos           text not null,
  -- Lista BLANCA, mismo criterio que documents.roles_permitidos y que las
  -- herramientas: vacio o null = ningun rol la ve. Falla cerrado.
  roles_permitidos text[],
  estado          text not null default 'propuesta',  -- propuesta|vigente|obsoleta
  version         integer not null default 1,
  -- 'manual' (la escribio una persona) u 'analisis' (la propuso el analista
  -- mirando conversaciones reales). Sirve para saber que revisar con mas
  -- cuidado, y para medir si el analista propone cosas utiles.
  origen          text not null default 'manual',
  -- De donde salio la propuesta: conversaciones, motivos de escalada, conteos.
  -- Sin esto, "el sistema sugiere una habilidad" es un oraculo -- con esto,
  -- quien aprueba puede ir a leer los casos que la motivaron.
  evidencia       jsonb not null default '{}'::jsonb,
  motivo_rechazo  text,
  aprobada_por    text,
  creada_en       timestamptz not null default now(),
  aprobada_en     timestamptz,
  unique (organization_id, codigo, version)
);

create index if not exists habilidades_org_idx
  on asistente.habilidades (organization_id, estado);

-- =============================================================================
--  USOS -- se cargo, y despues que paso
-- =============================================================================
--  Una habilidad aprobada y nunca cargada es ruido en el indice de todos los
--  turnos. Una que se carga siempre y la conversacion igual termina en un
--  humano esta mal escrita. Ninguna de las dos cosas se puede saber sin
--  registrarlo, y es el insumo del analista para proponer la version 2.
--
--  No guarda nada del contenido de la conversacion: solo que habilidad, en
--  que conversacion y cuando. Mismo criterio que asistente.tool_calls.

create table if not exists asistente.habilidad_usos (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  habilidad_id    uuid not null references asistente.habilidades(id) on delete cascade,
  conversation_id uuid,
  rol             text,
  creado_en       timestamptz not null default now()
);

create index if not exists habilidad_usos_idx
  on asistente.habilidad_usos (organization_id, habilidad_id, creado_en desc);

alter table asistente.habilidades enable row level security;
alter table asistente.habilidades force row level security;
grant select, insert, update, delete on asistente.habilidades to app_backend;
create policy tenant_aislado on asistente.habilidades
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

alter table asistente.habilidad_usos enable row level security;
alter table asistente.habilidad_usos force row level security;
grant select, insert, update, delete on asistente.habilidad_usos to app_backend;
create policy tenant_aislado on asistente.habilidad_usos
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
