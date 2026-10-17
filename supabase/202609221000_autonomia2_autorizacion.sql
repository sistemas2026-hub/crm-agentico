-- ============================================================================
--  AUTONOMIA 2  --  AUTORIZACION GRANULAR POR HERRAMIENTA
-- ============================================================================
--  RENUMERADA el 22/09/2026 (M06-F): antes 202609191430. No se aplico en ningun
--  entorno, y con su nombre viejo ordenaba ANTES de migraciones de origin que
--  produccion quiza ya tiene anotadas: el runner la habria tratado como hueco.
--  El contenido no cambio.
--
--  POR QUE TRES TABLAS Y NO UNA BANDERA
--  ------------------------------------
--  El kill switch (asistente.interruptor_autonomia) contesta UNA pregunta:
--  "¿esta empresa puede actuar sola?". No contesta "¿puede hacer ESTO?".
--  Mientras la respuesta a la segunda se deduzca de la primera, autorizar una
--  herramienta autoriza las veintisiete.
--
--  Por eso:
--
--    nivel_autonomia          el TECHO de la empresa. 0..4.
--    autorizacion_herramienta que puede hacerse de verdad, herramienta por
--                             herramienta, por debajo de ese techo.
--    ejecucion_autonoma       que paso. Bitacora, NO agenda -- ver abajo.
--
--  El techo no autoriza: acota. Una empresa en nivel 3 sin autorizaciones no
--  puede ejecutar nada. Una autorizacion de nivel 3 en una empresa con techo 1
--  tampoco. Se exige que PASEN LAS DOS, y por eso son dos tablas y no una
--  columna: revocar una herramienta no debe obligar a bajarle el techo a la
--  empresa entera, y bajar el techo no debe borrar las autorizaciones que
--  habria que volver a escribir despues.
--
--  ESTO NO ES UNA SEGUNDA COLA  --  requisito 3 del bloque
--  ------------------------------------------------------
--  'ejecucion_autonoma' es append-only y mira HACIA ATRAS: cada fila dice que
--  se decidio y que salio. No tiene 'pendiente', no tiene reclamo, no tiene
--  indice por "proximo a ejecutar", y nadie la consulta para saber que hacer.
--  La cola de trabajo sigue siendo UNA: operaciones.PropuestaSupervisor.
--  Si algun dia alguien le agrega un estado 'pendiente' y una funcion que
--  reclame filas, habra creado la segunda cola que este bloque prohibe --
--  tests/test_autonomia2.py lo comprueba.
--
--  APPEND-ONLY, COMO EL INTERRUPTOR
--  --------------------------------
--  Ninguna de las tres se actualiza: cada fila es una transicion y el estado
--  vigente es la mas reciente. Un UPDATE borraria quien autorizo que y cuando,
--  que es justo lo que hay que poder reconstruir meses despues.
-- ============================================================================

create schema if not exists asistente;


-- ----------------------------------------------------------------------------
--  1. EL TECHO POR EMPRESA
-- ----------------------------------------------------------------------------
create table if not exists asistente.nivel_autonomia (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- 0 observar · 1 recomendar · 2 ejecutar lo autorizado · 3 reversible
  -- autorizado · 4 critico con aprobacion humana. Los define M09-J.
  nivel           smallint not null check (nivel between 0 and 4),
  nivel_anterior  smallint check (nivel_anterior between 0 and 4),
  actor           text not null,
  motivo          text,
  creado_en       timestamptz not null default now()
);

comment on table asistente.nivel_autonomia is
  'Techo de autonomia por empresa. Solo se AGREGA: el nivel vigente es la fila '
  'mas reciente. Acota, nunca autoriza: sin una fila en '
  'asistente.autorizacion_herramienta no se ejecuta nada, tenga el nivel que '
  'tenga. La ausencia de fila se lee como nivel 0.';

create index if not exists nivel_autonomia_vigente_idx
  on asistente.nivel_autonomia (organization_id, creado_en desc);


-- ----------------------------------------------------------------------------
--  2. LA AUTORIZACION GRANULAR
-- ----------------------------------------------------------------------------
create table if not exists asistente.autorizacion_herramienta (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- El nombre tal cual esta en el catalogo del tenant. No hay FK: el catalogo
  -- vive en asistente.tenant_config (jsonb), no en una tabla de herramientas.
  herramienta     text not null,
  estado          text not null check (estado in ('autorizada', 'revocada')),
  estado_anterior text check (estado_anterior in ('autorizada', 'revocada')),
  -- El nivel que esta autorizacion habilita. Se compara contra el techo de
  -- nivel_autonomia: manda el MENOR de los dos.
  nivel_maximo    smallint not null check (nivel_maximo between 0 and 4),
  -- VIGENCIA. 'vigente_hasta' null = sin vencimiento explicito. Una
  -- autorizacion vencida NO se borra: deja de aplicar y queda en la bitacora.
  vigente_desde   timestamptz not null default now(),
  vigente_hasta   timestamptz,
  -- QUIEN. Texto libre a proposito, igual que en el interruptor: puede ser un
  -- profile_id del CRM, el nombre de un operador, o 'migracion'.
  autorizado_por  text not null,
  motivo          text,
  -- LIMITES. Lo que esta autorizacion acota ademas del nivel: cuantas veces
  -- por dia, sobre que subconjunto, con que argumentos maximos. Se guarda como
  -- jsonb porque el limite que importa depende de la herramienta, y meterlos
  -- como columnas obligaria a migrar la tabla cada vez que aparece uno nuevo.
  limites         jsonb not null default '{}'::jsonb,
  creado_en       timestamptz not null default now(),
  constraint vigencia_coherente check (vigente_hasta is null
                                       or vigente_hasta > vigente_desde)
);

comment on table asistente.autorizacion_herramienta is
  'Autorizacion GRANULAR: que herramienta puede ejecutar el sistema solo, en '
  'que empresa, hasta que nivel, hasta cuando y con que limites. Solo se '
  'AGREGA: revocar es escribir una fila con estado=revocada, nunca borrar la '
  'anterior. Es INDEPENDIENTE de tenant_config.requiere_confirmacion (que es '
  'una preferencia de producto, no una autorizacion) y del kill switch (que '
  'es un corte global, no un permiso).';

create index if not exists autorizacion_herramienta_vigente_idx
  on asistente.autorizacion_herramienta
     (organization_id, herramienta, creado_en desc);


-- ----------------------------------------------------------------------------
--  3. LA BITACORA  (append-only, mira hacia atras -- NO es una cola)
-- ----------------------------------------------------------------------------
create table if not exists asistente.ejecucion_autonoma (
  id                 uuid primary key default gen_random_uuid(),
  organization_id    uuid not null references public.organization(id) on delete cascade,
  -- De que propuesta salio, si salio de una. Sin FK dura: PropuestaSupervisor
  -- vive en el esquema public del CRM y esta tabla en el del motor; una FK
  -- entre los dos ataria el despliegue de uno al del otro.
  propuesta_id       uuid,
  herramienta        text not null,
  -- La clave de asistente.operaciones_externas. Es el puente entre "se
  -- autorizo" y "se ejecuto una sola vez": dos registros distintos, a
  -- proposito, porque responden preguntas distintas.
  clave_idempotencia text,
  -- Que autorizacion se aplico, y que nivel quedo vigente tras cruzar el techo.
  autorizacion_id    uuid references asistente.autorizacion_herramienta(id),
  nivel_efectivo     smallint check (nivel_efectivo between 0 and 4),
  -- 'permitida' o 'bloqueada'. Si es bloqueada, 'codigo' dice por cual de las
  -- nueve compuertas, y ese es el dato que sirve para depurar despues.
  decision           text not null check (decision in ('permitida', 'bloqueada')),
  codigo             text,
  motivo             text,
  actor              text,
  evidencia          text,
  resultado          text check (resultado in ('exitosa', 'fallida', 'no_ejecutada')),
  error              text,
  creado_en          timestamptz not null default now()
);

comment on table asistente.ejecucion_autonoma is
  'Bitacora de decisiones de autonomia. Solo se AGREGA y solo mira hacia '
  'ATRAS: no tiene estado pendiente, no se reclama, no se ordena por "proximo '
  'a ejecutar" y nadie la consulta para saber que hacer. NO es una cola: la '
  'unica cola de trabajo es operaciones.PropuestaSupervisor.';

create index if not exists ejecucion_autonoma_consulta_idx
  on asistente.ejecucion_autonoma (organization_id, creado_en desc);


-- ----------------------------------------------------------------------------
--  4. PERMISOS
-- ----------------------------------------------------------------------------
--  El runtime LEE las dos primeras y ESCRIBE la bitacora. No puede autorizarse
--  a si mismo: el INSERT sobre autorizacion_herramienta y nivel_autonomia no
--  se le concede -- requisito 6 del bloque ("no puede crear permisos, no puede
--  modificar autorizacion"). Quien autoriza lo hace por la via administrativa,
--  con la misma identidad separada que mueve el kill switch.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'app_backend') then
    grant usage on schema asistente to app_backend;
    grant select on asistente.nivel_autonomia          to app_backend;
    grant select on asistente.autorizacion_herramienta to app_backend;
    grant select, insert on asistente.ejecucion_autonoma to app_backend;
  end if;
  if exists (select 1 from pg_roles where rolname = 'autonomia_operador') then
    grant usage on schema asistente to autonomia_operador;
    grant select, insert on asistente.nivel_autonomia          to autonomia_operador;
    grant select, insert on asistente.autorizacion_herramienta to autonomia_operador;
    grant select on asistente.ejecucion_autonoma to autonomia_operador;
  end if;
end $$;
