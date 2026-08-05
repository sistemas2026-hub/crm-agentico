-- =============================================================================
--  ASISTENTE OPERATIVO PARA ISP  -  esquema multi-tenant
--  Entregable 1 de 9. Agosto 2026. (v2: convive con la aplicacion existente)
-- =============================================================================
--
--  DONDE VIVE ESTO
--  ---------------
--  Todo va en el esquema 'asistente', NO en 'public'. La base ya tiene 50
--  tablas de una aplicacion en produccion (CRM, inventario, mantenimiento,
--  workflows, voz) y este sistema debe convivir sin estorbar:
--
--    - cero riesgo de choque de nombres, ahora y en el futuro
--    - se puede revisar de un vistazo que es de quien
--    - si algo sale mal:  drop schema asistente cascade;  y no queda rastro
--
--  NO SE MODIFICA NINGUNA TABLA EXISTENTE. La identidad de empresa se toma de
--  public.organizations, que ya existe; la configuracion del asistente se
--  guarda aparte, en asistente.tenant_config, para no alterar esa tabla.
--
--  TERMINOLOGIA
--  ------------
--  Lo que la configuracion llama "tenant" es una fila de public.organizations.
--  En SQL se usa 'organization_id' porque es lo que referencia; en los YAML se
--  sigue diciendo tenant. Es la misma entidad.
--
--  PRINCIPIO RECTOR
--  ----------------
--  Dar de alta un ISP = fila en organizations + tenant.config.yaml + cargar sus
--  documentos. Cero cambios de codigo. Por eso NADA aqui conoce a un cliente
--  concreto: lo especifico vive en tenant_config.config (JSONB).
--
--  RESIDENCIA DE DATOS (RNF-01)
--  ----------------------------
--  Supabase es AUTO-HOSPEDADO en infraestructura propia, no un SaaS de
--  terceros. Aun asi se mantiene una regla:
--
--    tool_calls guarda un RESUMEN de cada llamada, nunca el payload.
--
--  Una conversacion la escribe el cliente y esta cubierta por su autorizacion
--  de tratamiento. El registro de WispHub no: son 54 campos con cedula,
--  direccion, coordenadas GPS y CUATRO contrasenas, que nadie autorizo
--  replicar y que el sistema no necesita persistir para funcionar.
--
-- =============================================================================

create extension if not exists vector;
create extension if not exists pg_trgm;

create schema if not exists asistente;


-- =============================================================================
--  0) ROL DE APLICACION  -  por que NO se usa service_role
-- =============================================================================
--  En Supabase, 'service_role' tiene el atributo BYPASSRLS: las politicas NO se
--  evaluan para ese rol, y ni 'force row level security' lo detiene, porque el
--  bypass es del rol y no de la tabla.
--
--  Con service_role, un bug que olvide el 'where organization_id = ...' expone
--  los datos de TODOS los tenants sin que nada lo impida: la defensa en
--  profundidad seria imaginaria. Comprobado — como superusuario se ven todas
--  las filas; como app_backend, solo las del tenant activo.
--
--  El backend se conecta y hace 'set role app_backend'. BYPASSRLS es atributo
--  del rol ACTUAL, asi que al cambiar de rol se pierde y RLS empieza a aplicar.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_backend') then
    create role app_backend nologin;
  end if;
  -- Membresia para quien conecta. Sin esto, 'set role app_backend' falla con
  -- "permission denied to set role": en Supabase auto-hospedado el usuario
  -- 'postgres' NO es superusuario y solo puede asumir roles de los que es
  -- miembro. Es requisito del diseno, no un permiso de conveniencia: el backend
  -- se conecta y cambia de rol en cada peticion para que RLS aplique.
  execute format('grant app_backend to %I', current_user);
end $$;

grant usage on schema asistente to app_backend;
-- Solo lectura de la identidad de empresa. El asistente nunca escribe ahi.
grant select on public.organizations to app_backend;

-- El tenant activo viaja en una variable de sesion que el backend fija al
-- inicio de cada peticion:
--     set role app_backend;
--     set local app.current_tenant = '<uuid>';
-- 'set local' muere con la transaccion, asi que una peticion no puede heredar
-- el tenant de otra por reutilizacion de conexion del pool.
create or replace function asistente.org_actual()
returns uuid
language sql stable
as $$
  select nullif(current_setting('app.current_tenant', true), '')::uuid;
$$;


-- =============================================================================
--  1) CONFIGURACION DEL TENANT
-- =============================================================================
--  public.organizations ya existe y aporta id/name/slug. Aqui se le cuelga lo
--  que necesita el asistente, SIN alterar esa tabla: una fila por empresa que
--  tenga el asistente activo. Una organizacion sin fila aqui simplemente no lo
--  tiene habilitado.

create table if not exists asistente.tenant_config (
  organization_id uuid primary key
                  references public.organizations(id) on delete cascade,
  -- El tenant.config.yaml validado y serializado. Se guarda en la base, y no
  -- en un archivo del servidor, para que cambiar la configuracion no exija
  -- redeploy.
  config          jsonb not null default '{}'::jsonb,
  config_version  integer not null default 1,
  plan            text not null default 'piloto',
  activo          boolean not null default true,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

comment on column asistente.tenant_config.config is
  'tenant.config.yaml validado. NUNCA contiene secretos: solo referencias '
  '(auth_ref, phone_number_id_ref) que se resuelven contra el entorno o Vault.';


-- =============================================================================
--  2) USUARIOS DEL ASISTENTE
-- =============================================================================
--  Distinta de public.profiles: aqui viven las identidades de CANAL (numero de
--  WhatsApp) y el rol frente al asistente, que no tienen por que coincidir con
--  los usuarios de la aplicacion existente.

create table if not exists asistente.tenant_users (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  profile_id      uuid,                            -- enlace opcional a public.profiles
  rol             text not null,                   -- admin|coordinador|tecnico|cliente_final
  nombre          text,
  -- Identificador del canal EN CLARO. Se hasheaba en el primer borrador, pero
  -- al decidirse que el contenido de las conversaciones va en claro, el hash
  -- dejo de proteger nada — la propia conversacion dice "soy Juan Perez,
  -- cedula ..." — y solo complicaba el panel y el cambio de numero.
  canal_identidad text,
  canal           text,                            -- whatsapp|web
  activo          boolean not null default true,
  creado_en       timestamptz not null default now(),
  unique (organization_id, canal, canal_identidad)
);

create index if not exists tenant_users_org_rol_idx
  on asistente.tenant_users (organization_id, rol) where activo;
create index if not exists tenant_users_canal_idx
  on asistente.tenant_users (canal, canal_identidad) where activo;

comment on column asistente.tenant_users.canal_identidad is
  'Para WhatsApp, el numero. Medido en la base del ISP (600 clientes): 98.7% '
  'tienen al menos un movil registrado, 50% tienen dos, y solo el 0.4% de los '
  'numeros apunta a mas de un cliente. Por eso sirve como factor de POSESION. '
  'La cedula NO sirve: identifica pero no autentica, porque es publica (esta '
  'en la factura, el contrato y el documento).';


-- =============================================================================
--  3) DOCUMENTOS Y FRAGMENTOS  (el corpus RAG)
-- =============================================================================

create table if not exists asistente.documents (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  codigo          text not null,                   -- 'G-GO-06'
  titulo          text not null,
  version         text not null,                   -- '01'
  fecha_vigencia  date,
  tipo            text not null,
  estado          text not null default 'vigente', -- vigente|obsoleto
  storage_path    text,
  hash            text,                            -- detecta recargas identicas
  -- Defectos hallados durante la ingesta: numeraciones duplicadas, referencias
  -- cruzadas rotas, secciones vacias. Degradan las respuestas y hay que poder
  -- mostrarselos al cliente.
  defectos        jsonb not null default '[]'::jsonb,
  creado_en       timestamptz not null default now(),
  unique (organization_id, codigo, version)
);

create index if not exists documents_org_idx
  on asistente.documents (organization_id, estado, tipo);

create table if not exists asistente.document_chunks (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_id     uuid not null references asistente.documents(id) on delete cascade,
  orden           integer not null,
  -- Dos versiones del texto, a proposito:
  --   contenido                 -> el original, es lo que se MUESTRA
  --   contenido_contextualizado -> con encabezado de procedencia, es lo que se
  --                                VECTORIZA. Un fragmento suelto que dice "se
  --                                configura en 192.168.1.1" no se recupera
  --                                bien; con "Del documento G-GO-06, seccion
  --                                1.4 Configuracion WAN:" delante, si.
  contenido                 text not null,
  contenido_contextualizado text not null,
  -- 1024 = bge-m3 (local, multilingue, buen espanol).
  -- OJO: la dimension NO se puede cambiar sin re-vectorizar TODO el corpus.
  embedding       vector(1024),
  -- Mitad lexica de la busqueda hibrida.
  busqueda        tsvector generated always as
                    (to_tsvector('spanish', contenido_contextualizado)) stored,
  metadata        jsonb not null default '{}'::jsonb,
  tokens          integer,
  -- Versionado: al recargar un documento los fragmentos viejos se marcan
  -- obsoletos y NO se borran. Sin esto es imposible reconstruir con que version
  -- se respondio algo hace tres meses.
  vigente         boolean not null default true,
  creado_en       timestamptz not null default now()
);

-- HNSW, coseno: bge-m3 entrega vectores normalizados. El indice parcial evita
-- recorrer fragmentos obsoletos.
create index if not exists document_chunks_embedding_idx
  on asistente.document_chunks using hnsw (embedding vector_cosine_ops)
  where vigente;
create index if not exists document_chunks_busqueda_idx
  on asistente.document_chunks using gin (busqueda) where vigente;
create index if not exists document_chunks_doc_idx
  on asistente.document_chunks (organization_id, document_id, orden);
create index if not exists document_chunks_meta_idx
  on asistente.document_chunks using gin (metadata jsonb_path_ops);


-- =============================================================================
--  4) CONVERSACIONES
-- =============================================================================

create table if not exists asistente.conversations (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  canal           text not null,
  usuario_externo text,                            -- en claro, ver tenant_users
  tenant_user_id  uuid references asistente.tenant_users(id),
  rol_efectivo    text,                            -- con que permisos se atendio
  estado          text not null default 'abierta',
  escalada_a_humano boolean not null default false,
  motivo_escalamiento text,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create index if not exists conversations_org_idx
  on asistente.conversations (organization_id, estado, actualizado_en desc);
create index if not exists conversations_usuario_idx
  on asistente.conversations (organization_id, canal, usuario_externo);

create table if not exists asistente.messages (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid not null references asistente.conversations(id) on delete cascade,
  rol             text not null,                   -- user|assistant|tool|system
  contenido       text,
  -- DECIDIDO: se guarda EN CLARO. La anonimizacion por patrones es fiable con
  -- cedulas y telefonos pero imperfecta con nombres y direcciones: no garantiza
  -- cumplimiento y si degrada el historial de depuracion. Lo peor de los dos
  -- mundos. La base legal es la autorizacion de tratamiento que el cliente
  -- firma al contratar.
  -- La bandera se conserva para dejar registrado que fue una DECISION y no un
  -- descuido, y para poder anonimizar selectivamente sin migrar.
  contenido_anonimizado boolean not null default false,
  tokens_entrada  integer,
  tokens_salida   integer,
  costo_usd       numeric(10,6),
  latencia_ms     integer,
  modelo          text,
  -- Solo IDs y puntajes, no el texto: permite reconstruir la respuesta y
  -- auditar el RAG sin duplicar el corpus.
  chunks_recuperados jsonb not null default '[]'::jsonb,
  creado_en       timestamptz not null default now()
);

create index if not exists messages_conv_idx
  on asistente.messages (organization_id, conversation_id, creado_en);
create index if not exists messages_org_fecha_idx
  on asistente.messages (organization_id, creado_en desc);


-- =============================================================================
--  5) LLAMADAS A HERRAMIENTAS  -  metadatos, NUNCA el payload
-- =============================================================================
--  Aqui RNF-01 se hace cumplir en el ESQUEMA, no en una convencion que alguien
--  puede olvidar. No existe una columna 'resultado jsonb' a proposito: si
--  existiera, alguien la llenaria con la respuesta de la API del ISP y esta
--  base se convertiria en una copia de su base de clientes.
--
--  Lo registrado responde "quien consulto que y cuando", que es el proposito de
--  auditoria, sin replicar el dato consultado.

create table if not exists asistente.tool_calls (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  message_id      uuid references asistente.messages(id) on delete set null,
  conversation_id uuid references asistente.conversations(id) on delete cascade,
  herramienta     text not null,
  -- Con los identificadores largos ENMASCARADOS por el backend. Se conservan
  -- porque sin ellos la auditoria no sirve: hay que poder saber QUE se
  -- consulto, no solo que se consulto algo.
  parametros      jsonb not null default '{}'::jsonb,
  rol_solicitante text,
  -- Resumen del resultado. NO el resultado.
  exito           boolean not null,
  n_registros     integer,
  codigo_error    text,
  duracion_ms     integer,
  es_escritura    boolean not null default false,
  confirmado_por  text,
  creado_en       timestamptz not null default now()
);

create index if not exists tool_calls_org_idx
  on asistente.tool_calls (organization_id, creado_en desc);
create index if not exists tool_calls_herr_idx
  on asistente.tool_calls (organization_id, herramienta, creado_en desc);
create index if not exists tool_calls_escritura_idx
  on asistente.tool_calls (organization_id, creado_en desc) where es_escritura;


-- =============================================================================
--  6) PREGUNTAS SIN RESPUESTA  -  requisito de negocio, no tecnico
-- =============================================================================
--  Cuando ningun fragmento supera el umbral NO se llama al modelo: se responde
--  con el mensaje configurado y se registra aqui. Cada fila es un hueco en la
--  documentacion del cliente, y esa lista es un entregable comercial.

create table if not exists asistente.unanswered_queries (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  conversation_id uuid references asistente.conversations(id) on delete set null,
  pregunta        text not null,
  mejor_similitud real,
  rol_solicitante text,
  revisada        boolean not null default false,
  accion_tomada   text,
  creado_en       timestamptz not null default now()
);

create index if not exists unanswered_org_idx
  on asistente.unanswered_queries (organization_id, revisada, creado_en desc);


-- =============================================================================
--  7) EVALUACION  -  el set dorado por tenant
-- =============================================================================

create table if not exists asistente.evaluation_sets (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  nombre          text not null,
  casos           jsonb not null default '[]'::jsonb,
  activo          boolean not null default true,
  creado_en       timestamptz not null default now(),
  unique (organization_id, nombre)
);

create table if not exists asistente.evaluation_runs (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  evaluation_set_id uuid not null
                    references asistente.evaluation_sets(id) on delete cascade,
  modelo          text not null,
  config_version  integer,
  n_casos         integer not null,
  n_aciertos      integer not null,
  -- SEPARADA del acierto, a proposito. Medido: un modelo "respondia bien" pero
  -- ignoraba el dato de la herramienta e inventaba cliente, plan y factura. Un
  -- sistema con 92% de acierto que inventa el 3% restante es peligroso; uno con
  -- 88% que dice "no se" el 12% es utilizable. El promedio no distingue.
  -- CRITERIO DE ACEPTACION: n_invenciones = 0. No "bajo". Cero.
  n_invenciones   integer not null default 0,
  detalle         jsonb not null default '{}'::jsonb,
  latencia_media_ms integer,
  costo_usd       numeric(10,6),
  creado_en       timestamptz not null default now()
);

create index if not exists evaluation_runs_idx
  on asistente.evaluation_runs (organization_id, evaluation_set_id, creado_en desc);


-- =============================================================================
--  8) CONSUMO DIARIO
-- =============================================================================

create table if not exists asistente.usage_daily (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  dia             date not null,
  n_conversaciones integer not null default 0,
  n_mensajes      integer not null default 0,
  n_tool_calls    integer not null default 0,
  tokens_entrada  bigint not null default 0,
  tokens_salida   bigint not null default 0,
  costo_usd       numeric(12,6) not null default 0,
  primary key (organization_id, dia)
);

-- El limite vive en la config del tenant, no aqui: es comportamiento
-- parametrizable, no estructura.
create or replace function asistente.gasto_del_mes(
  p_org uuid, p_fecha date default current_date)
returns numeric
language sql stable
as $$
  select coalesce(sum(costo_usd), 0)
  from asistente.usage_daily
  where organization_id = p_org
    and dia >= date_trunc('month', p_fecha)::date
    and dia <= p_fecha;
$$;


-- =============================================================================
--  9) BITACORA DE ACCESO A DATOS SENSIBLES
-- =============================================================================
--  Distinta de tool_calls: aquella registra toda invocacion; esta, solo los
--  accesos a datos sensibles y por que se permitieron. Es la que responde
--  "quien vio la cedula de este cliente" ante un requerimiento de habeas data.

create table if not exists asistente.audit_log (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  actor           text not null,
  accion          text not null,                   -- consulta|escritura|export
  recurso         text,                            -- 'cliente:4821'
  campos_sensibles text[],
  base_legal      text,
  resultado       text not null,                   -- permitido|denegado
  motivo_denegacion text,
  creado_en       timestamptz not null default now()
);

create index if not exists audit_log_org_idx
  on asistente.audit_log (organization_id, creado_en desc);
create index if not exists audit_log_resultado_idx
  on asistente.audit_log (organization_id, resultado, creado_en desc);


-- =============================================================================
--  10) ROW LEVEL SECURITY
-- =============================================================================
--  Politica unica y repetida: solo se ve lo del tenant activo en la sesion.
--  'force' hace que aplique tambien al dueno de la tabla. No protege de
--  service_role (ver seccion 0) — por eso el backend usa app_backend.

do $$
declare t text;
begin
  foreach t in array array[
    'tenant_config','tenant_users','documents','document_chunks','conversations',
    'messages','tool_calls','unanswered_queries','evaluation_sets',
    'evaluation_runs','usage_daily','audit_log'
  ] loop
    execute format('alter table asistente.%I enable row level security', t);
    execute format('alter table asistente.%I force row level security', t);
    execute format('grant select, insert, update, delete on asistente.%I to app_backend', t);
    execute format('drop policy if exists tenant_aislado on asistente.%I', t);
  end loop;
end $$;

-- tenant_config se filtra por su propia clave; el resto por organization_id.
create policy tenant_aislado on asistente.tenant_config
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

do $$
declare t text;
begin
  foreach t in array array[
    'tenant_users','documents','document_chunks','conversations','messages',
    'tool_calls','unanswered_queries','evaluation_sets','evaluation_runs',
    'usage_daily','audit_log'
  ] loop
    execute format($f$
      create policy tenant_aislado on asistente.%I
        for all to app_backend
        using (organization_id = asistente.org_actual())
        with check (organization_id = asistente.org_actual())
    $f$, t);
  end loop;
end $$;


-- =============================================================================
--  11) BUSQUEDA
-- =============================================================================

-- Vectorial pura. El tenant es PARAMETRO OBLIGATORIO y ademas se filtra: si
-- alguna vez se llama desde un rol que evade RLS, el filtro explicito sigue.
create or replace function asistente.match_chunks(
  p_org             uuid,
  p_query_embedding vector(1024),
  p_match_count     integer default 8,
  p_umbral          real    default 0.0,
  p_filtros         jsonb   default '{}'::jsonb
)
returns table (
  chunk_id     uuid,
  document_id  uuid,
  codigo       text,
  titulo       text,
  version      text,
  contenido    text,
  metadata     jsonb,
  similitud    real
)
language sql stable
as $$
  select c.id, c.document_id, d.codigo, d.titulo, d.version,
         c.contenido, c.metadata,
         (1 - (c.embedding <=> p_query_embedding))::real as similitud
  from asistente.document_chunks c
  join asistente.documents d on d.id = c.document_id
  where c.organization_id = p_org
    and c.vigente
    and d.estado = 'vigente'
    and (p_filtros = '{}'::jsonb or c.metadata @> p_filtros)
    and (1 - (c.embedding <=> p_query_embedding)) >= p_umbral
  order by c.embedding <=> p_query_embedding
  limit p_match_count;
$$;

-- Hibrida con Reciprocal Rank Fusion. RRF combina dos rankings sin normalizar
-- puntajes que viven en escalas distintas: la similitud coseno y el ts_rank de
-- PostgreSQL no son comparables entre si, pero sus POSICIONES si. k=60 es el
-- valor habitual de la literatura.
create or replace function asistente.match_chunks_hibrido(
  p_org             uuid,
  p_query_embedding vector(1024),
  p_query_texto     text,
  p_match_count     integer default 8,
  p_filtros         jsonb   default '{}'::jsonb,
  p_k               integer default 60
)
returns table (
  chunk_id    uuid,
  document_id uuid,
  codigo      text,
  titulo      text,
  version     text,
  contenido   text,
  metadata    jsonb,
  puntaje_rrf real
)
language sql stable
as $$
  with candidatos as (
    select c.id, c.document_id, c.contenido, c.metadata, c.embedding, c.busqueda
    from asistente.document_chunks c
    join asistente.documents d on d.id = c.document_id
    where c.organization_id = p_org
      and c.vigente and d.estado = 'vigente'
      and (p_filtros = '{}'::jsonb or c.metadata @> p_filtros)
  ),
  vectorial as (
    select id, row_number() over (order by embedding <=> p_query_embedding) as pos
    from candidatos
    order by embedding <=> p_query_embedding
    limit p_match_count * 5
  ),
  lexica as (
    select id, row_number() over (
             order by ts_rank(busqueda, plainto_tsquery('spanish', p_query_texto)) desc
           ) as pos
    from candidatos
    where busqueda @@ plainto_tsquery('spanish', p_query_texto)
    limit p_match_count * 5
  ),
  fusion as (
    select coalesce(v.id, l.id) as id,
           (coalesce(1.0 / (p_k + v.pos), 0)
            + coalesce(1.0 / (p_k + l.pos), 0))::real as rrf
    from vectorial v
    full outer join lexica l on l.id = v.id
  )
  select c.id, c.document_id, d.codigo, d.titulo, d.version,
         c.contenido, c.metadata, f.rrf
  from fusion f
  join asistente.document_chunks c on c.id = f.id
  join asistente.documents d on d.id = c.document_id
  order by f.rrf desc
  limit p_match_count;
$$;

grant execute on all functions in schema asistente to app_backend;
