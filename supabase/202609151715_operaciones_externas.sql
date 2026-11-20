-- =============================================================================
--  OPERACIONES EXTERNAS  --  que una mutacion contra un tercero corra UNA vez
-- =============================================================================
--
--  QUE PROBLEMA RESUELVE
--  ---------------------
--  El motor escribe en sistemas de terceros: reinicia una ONT en SmartOLT,
--  activa CATV, cambia el tipo de ONU, crea un ticket o registra un pago en
--  WispHub. Ninguna de esas llamadas es idempotente del lado del proveedor, y
--  hoy nada impide que la MISMA operacion logica salga dos veces por un
--  reintento, un timeout, una caida de conexion, dos procesos a la vez o un
--  reenvio de la peticion.
--
--  Esta tabla es el registro de esas operaciones: quien la pidio, con que
--  argumentos, en que estado quedo y que contesto el tercero. La clave
--  primaria (organizacion + clave) es lo que hace la exclusion: el que logra
--  insertar la fila es el que ejecuta, y solo ese.
--
--  POR QUE NO SE REUSA 'campo.MutacionIdempotente'
--  -----------------------------------------------
--  Existe, resuelve bien lo suyo, y NO sirve aca. Tres razones, la primera es
--  la que cierra la discusion:
--
--    1. Vive en el esquema 'public'. El motor baja el rol a 'app_backend'
--       (nucleo/persistencia/db.py), que tiene privilegios sobre 'asistente' y
--       ninguno sobre 'public' -- medido el 15/09/2026 contra la base real:
--       'InsufficientPrivilege: permission denied for schema public'. No es
--       una preferencia de diseño: el motor literalmente no la puede leer.
--    2. Su unidad es una PETICION HTTP entrante al CRM (http_method, endpoint,
--       status_code, respuesta de DRF). La unidad de aca es una LLAMADA
--       SALIENTE a un tercero, identificada por herramienta y argumentos. Son
--       ejes distintos, no dos nombres de lo mismo.
--    3. Su manejo del fallo es BORRAR la fila (ver campo/services/idempotencia.py:
--       'MutacionIdempotente.objects.filter(pk=...).delete()'). No hay estado
--       fallida, ni contador de intentos, ni origen -- y los tres hacen falta
--       para decidir si un reintento esta autorizado en vez de repetirlo a
--       ciegas.
--
--  El PATRON si se reusa, que es lo que importa: hash canonico de los
--  argumentos, misma clave con argumentos distintos = conflicto, adquisicion
--  atomica por restriccion unica. Ver nucleo/seguridad/idempotencia.py.
--
--  LO QUE ESTA TABLA NO PUEDE PROMETER
--  -----------------------------------
--  Si la llamada sale y la respuesta se pierde (timeout de red), NADIE sabe si
--  el tercero la aplico -- ni esta tabla ni nadie. Lo que se garantiza es que
--  el reintento es UNO, con dueño, contado y anotado, en vez de N sin registro.
--  Eso es lo que hay; decir mas seria mentir.
-- =============================================================================

create table if not exists asistente.operaciones_externas (
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- La identidad de la operacion logica. La arma quien llama, no el modelo:
  -- ver nucleo/seguridad/idempotencia.py::clave_de.
  clave           text not null,
  herramienta     text not null,
  -- SHA-256 del JSON canonico de los argumentos ya resueltos. Es lo que
  -- distingue "el mismo pedido otra vez" de "otro pedido con la misma clave"
  -- -- el segundo se RECHAZA, nunca se ejecuta ni devuelve el resultado del
  -- primero.
  argumentos_hash text not null,
  estado          text not null
                  check (estado in ('pendiente', 'ejecutando', 'exitosa',
                                    'fallida', 'rechazada')),
  -- Quien la pidio: el turno de una conversacion, un trabajo del scheduler, o
  -- otro servicio del despliegue. Sin esto no se puede responder "por que
  -- corrio esto" cuando no hubo ninguna persona de por medio.
  origen          text not null,
  intentos        integer not null default 1,
  -- La respuesta del tercero, para poder devolverla sin volver a llamar. Es un
  -- resultado de herramienta, no el registro crudo de un cliente: lo que cae
  -- aca ya paso por el ejecutor (ver nucleo/herramientas/http.py) y para las
  -- tres acciones de red es una confirmacion corta, no una ficha de cliente.
  respuesta       jsonb,
  error           text,
  creado_en       timestamptz not null default now(),
  ejecutado_en    timestamptz,
  actualizado_en  timestamptz not null default now(),
  primary key (organization_id, clave)
);

comment on table asistente.operaciones_externas is
  'Una fila por operacion logica del motor contra un sistema de terceros. La '
  'clave primaria (organizacion, clave) es el mecanismo de exclusion: quien '
  'inserta ejecuta. Ver nucleo/seguridad/idempotencia.py. No reemplaza a '
  'campo.MutacionIdempotente (esquema public, inalcanzable para app_backend, '
  'y su unidad es una peticion HTTP entrante, no una llamada saliente).';

comment on column asistente.operaciones_externas.estado is
  'pendiente | ejecutando | exitosa | fallida | rechazada. HOY ningun camino '
  'escribe "pendiente": el motor reclama y ejecuta en el acto. Queda declarada '
  'para una cola futura que separe reclamar de ejecutar.';

comment on column asistente.operaciones_externas.argumentos_hash is
  'SHA-256 del JSON canonico (claves ordenadas, sin espacios) de los '
  'argumentos ya resueltos. Misma clave + hash distinto = rechazada.';

-- Para rescatar las que quedaron en 'ejecutando' porque el proceso murio entre
-- la llamada y el registro del resultado.
create index if not exists operaciones_externas_ejecutando_idx
  on asistente.operaciones_externas (organization_id, estado, creado_en);


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------
--  Sin DELETE: una operacion externa que ya salio no se borra. Purgarla es un
--  acto deliberado del owner, no algo que el runtime pueda hacer.

alter table asistente.operaciones_externas enable row level security;
alter table asistente.operaciones_externas force row level security;
grant select, insert, update on asistente.operaciones_externas to app_backend;

drop policy if exists tenant_aislado on asistente.operaciones_externas;
create policy tenant_aislado on asistente.operaciones_externas
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
