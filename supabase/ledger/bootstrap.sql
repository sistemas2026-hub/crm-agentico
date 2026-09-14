-- =============================================================================
--  EL LEDGER DE MIGRACIONES  --  se crea antes que todo lo demas
-- =============================================================================
--
--  Vive en 'supabase/ledger/', NO en 'supabase/', a proposito: el migrador
--  recorre 'supabase/*.sql' y este archivo no puede ser una de las migraciones
--  que recorre. Es la tabla donde va a anotar que recorrio.
--
--  Por que hacia falta
--  -------------------
--  Hasta ahora 'aplicar las migraciones' era ejecutar los 40 archivos, todos,
--  siempre. Con eso:
--
--    * la segunda corrida falla -- cinco archivos hacen 'create policy' sin
--      guarda y chocan con DuplicateObject (42710);
--    * un 'grant execute on all functions in schema asistente to app_backend'
--      escrito en agosto se vuelve a ejecutar hoy y alcanza funciones que no
--      existian cuando se escribio;
--    * nadie puede decir que quedo aplicado en una base concreta, salvo
--      mirando el esquema y adivinando;
--    * editar un archivo ya aplicado no produce ningun sintoma.
--
--  Los cuatro son el mismo problema: no hay registro. Esta tabla es el
--  registro, y el migrador que la usa vive en 'cli/migrar_asistente.py'.
--
--  Lo que NO se hace: tocar los archivos historicos. Ninguno de los 40 cambia.
--  Dejan de re-ejecutarse porque el migrador los saltea, no porque se los haya
--  vuelto idempotentes uno por uno -- eso seria arreglar el sintoma cuarenta
--  veces y dejar el problema intacto para el archivo cuarenta y uno.
-- =============================================================================

create schema if not exists asistente;

create table if not exists asistente.migraciones_aplicadas (
  -- El nombre del archivo, sin ruta. Es la identidad: dos archivos con el
  -- mismo nombre en distintas carpetas serian la misma migracion, y eso no
  -- puede pasar porque el migrador mira una sola carpeta.
  archivo       text        primary key,

  -- SHA-256 del contenido CANONICO, en hex. Lo que convierte al ledger en
  -- algo mas que una lista: si el archivo cambia despues de aplicado, el
  -- migrador lo ve y se detiene. El contrato exacto del contenido canonico
  -- esta en cli/migrar_asistente.py y se nombra en 'algoritmo'.
  sha256        text        not null,

  -- Que contrato de hash produjo 'sha256'. Hoy hay uno solo. Existe para que
  -- un cambio futuro de contrato no convierta cuarenta filas validas en
  -- cuarenta "archivos que cambiaron".
  algoritmo     text        not null default 'sha256-utf8-lf-v1',

  aplicada_en   timestamptz not null default now(),
  duro_ms       integer     not null,

  -- Como llego a estar aca:
  --   'aplicada'         el migrador la ejecuto
  --   'baseline'         se adopto una base existente y TODAS las
  --                      comprobaciones de catalogo de su manifiesto pasaron
  --   'baseline_humano'  se adopto por aceptacion humana individual, con motivo;
  --                      es la unica via para migraciones con efectos que el
  --                      catalogo no puede ver (datos, SQL dinamico)
  origen        text        not null default 'aplicada',

  -- Quien la anoto. No es auditoria fuerte --es 'current_user'-- pero al
  -- adoptar una base existente importa saber si la fila la puso el migrador
  -- corriendo o una persona decidiendo.
  por_usuario   text        not null default current_user,

  -- Solo para baseline: que se comprobo antes de darla por aplicada.
  nota          text,

  constraint ma_sha_hex    check (sha256 ~ '^[0-9a-f]{64}$'),
  constraint ma_algoritmo  check (algoritmo in ('sha256-utf8-lf-v1')),
  constraint ma_duro       check (duro_ms >= 0)
);

comment on table asistente.migraciones_aplicadas is
  'Que archivos de supabase/ ya corrieron en ESTA base, con el hash del '
  'contenido con que corrieron. La fuente de verdad del migrador.';

create index if not exists ma_por_fecha
  on asistente.migraciones_aplicadas (aplicada_en);

-- Ledgers creados antes de que existiera 'algoritmo': la columna se agrega con
-- el valor por defecto, que es el unico contrato que existio. Correcto porque
-- el contrato explicito da el mismo hash que la lectura en modo texto para
-- todo archivo sin BOM ni CR suelto -- y los 40 historicos no tienen ninguno.
alter table asistente.migraciones_aplicadas
  add column if not exists algoritmo text not null default 'sha256-utf8-lf-v1';

-- Las dos reglas sobre 'origen' van fuera del CREATE para que CONVERJAN en un
-- ledger creado por una version anterior de este archivo: 'create table if not
-- exists' no actualiza un CHECK que ya existe.
alter table asistente.migraciones_aplicadas drop constraint if exists ma_origen;
alter table asistente.migraciones_aplicadas add constraint ma_origen
  check (origen in ('aplicada', 'baseline', 'baseline_humano'));
alter table asistente.migraciones_aplicadas drop constraint if exists ma_nota_base;
alter table asistente.migraciones_aplicadas add constraint ma_nota_base
  check (origen = 'aplicada' or nota is not null);
