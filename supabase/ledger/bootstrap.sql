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

  -- SHA-256 del contenido, en hex. Lo que convierte al ledger en algo mas que
  -- una lista: si el archivo cambia despues de aplicado, el migrador lo ve y
  -- se detiene. Sin esto, editar una migracion ya corrida no da ningun aviso
  -- y las bases quedan divergiendo en silencio.
  sha256        text        not null,

  aplicada_en   timestamptz not null default now(),
  duro_ms       integer     not null,

  -- Como llego a estar aca:
  --   'aplicada'  el migrador la ejecuto
  --   'baseline'  se adopto una base que ya la tenia, con verificacion de
  --               objetos y autorizacion humana explicita
  origen        text        not null default 'aplicada',

  -- Quien la anoto. No es auditoria fuerte --es 'current_user'-- pero al
  -- adoptar una base existente importa saber si la fila la puso el migrador
  -- corriendo o una persona decidiendo.
  por_usuario   text        not null default current_user,

  -- Solo para baseline: que se comprobo antes de darla por aplicada.
  nota          text,

  constraint ma_sha_hex    check (sha256 ~ '^[0-9a-f]{64}$'),
  constraint ma_origen     check (origen in ('aplicada', 'baseline')),
  constraint ma_duro       check (duro_ms >= 0),
  constraint ma_nota_base  check (origen <> 'baseline' or nota is not null)
);

comment on table asistente.migraciones_aplicadas is
  'Que archivos de supabase/ ya corrieron en ESTA base, con el hash del '
  'contenido con que corrieron. La fuente de verdad del migrador.';

create index if not exists ma_por_fecha
  on asistente.migraciones_aplicadas (aplicada_en);
