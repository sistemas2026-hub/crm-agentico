-- =============================================================================
--  ESQUEMA DEL LEDGER  --  version 1
-- =============================================================================
--
--  Lo ejecuta 'cli/migrar_asistente.py' DENTRO de la seccion serializada, una
--  sola vez por base: al terminar queda anotado en
--  'asistente.migraciones_ledger_esquema' y no se vuelve a correr. Un comando
--  normal no hace DROP ni ADD de nada.
--
--  Vive en 'supabase/ledger/esquema/', fuera de 'supabase/*.sql': no es una de
--  las migraciones que el ledger registra, es el registro mismo.
--
--  Una version futura del esquema del ledger va en 0002_*.sql, nunca editando
--  este archivo.
-- =============================================================================

create schema if not exists asistente;

create table if not exists asistente.migraciones_ledger_esquema (
  version      integer     primary key check (version >= 1),
  archivo      text        not null,
  sha256       text        not null check (sha256 ~ '^[0-9a-f]{64}$'),
  aplicada_en  timestamptz not null default now(),
  por_usuario  text        not null default session_user
);

create table if not exists asistente.migraciones_aplicadas (
  -- El nombre del archivo, sin ruta. Es la identidad.
  archivo       text        primary key,
  -- SHA-256 del contenido CANONICO (contrato en cli/migrar_asistente.py).
  sha256        text        not null,
  -- Que contrato de hash produjo 'sha256'.
  algoritmo     text        not null default 'sha256-utf8-lf-v1',
  aplicada_en   timestamptz not null default now(),
  duro_ms       integer     not null,
  --   'aplicada'         el migrador la ejecuto
  --   'baseline'         adopcion: TODAS las comprobaciones de su manifiesto pasaron
  --   'baseline_humano'  adopcion por aceptacion humana individual, con motivo
  origen        text        not null default 'aplicada',
  por_usuario   text        not null default current_user,
  nota          text,

  constraint ma_sha_hex    check (sha256 ~ '^[0-9a-f]{64}$'),
  constraint ma_algoritmo  check (algoritmo in ('sha256-utf8-lf-v1')),
  constraint ma_duro       check (duro_ms >= 0),
  constraint ma_origen     check (origen in ('aplicada', 'baseline', 'baseline_humano')),
  constraint ma_nota_base  check (origen = 'aplicada' or nota is not null)
);

comment on table asistente.migraciones_aplicadas is
  'Que archivos de supabase/ ya corrieron en ESTA base, con el hash del '
  'contenido con que corrieron. La fuente de verdad del migrador.';

create index if not exists ma_por_fecha
  on asistente.migraciones_aplicadas (aplicada_en);

-- -----------------------------------------------------------------------------
--  Convergencia de un ledger creado por las versiones SIN esquema versionado
--  (commits 3cf1efd..1a49b23 de infra/ledger-migraciones-asistente; solo
--  existieron en bases efimeras de prueba). Corre una vez, con este paso.
-- -----------------------------------------------------------------------------
alter table asistente.migraciones_aplicadas
  add column if not exists algoritmo text not null default 'sha256-utf8-lf-v1';

do $$
declare
  t constant regclass := 'asistente.migraciones_aplicadas'::regclass;
begin
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'ma_origen'
                 and pg_get_constraintdef(oid) like '%baseline_humano%') then
    alter table asistente.migraciones_aplicadas drop constraint if exists ma_origen;
    alter table asistente.migraciones_aplicadas add constraint ma_origen
      check (origen in ('aplicada', 'baseline', 'baseline_humano'));
  end if;
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'ma_nota_base'
                 and pg_get_constraintdef(oid) like '%''aplicada''%') then
    alter table asistente.migraciones_aplicadas drop constraint if exists ma_nota_base;
    alter table asistente.migraciones_aplicadas add constraint ma_nota_base
      check (origen = 'aplicada' or nota is not null);
  end if;
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'ma_algoritmo') then
    alter table asistente.migraciones_aplicadas add constraint ma_algoritmo
      check (algoritmo in ('sha256-utf8-lf-v1'));
  end if;
end $$;
