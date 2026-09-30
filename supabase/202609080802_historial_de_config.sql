-- =============================================================================
--  QUE CONFIGURACION ESTABA SIRVIENDO CUANDO PASO ESO
-- =============================================================================
--  'asistente.tenant_config' guarda UNA fila por empresa y el editor la
--  actualiza EN EL LUGAR (nucleo/config/editor.py, 'update ... set config').
--  'config_version' sube en cada cambio real, asi que hay un contador de
--  cambios -- pero no queda ningun rastro de lo que decia la version anterior.
--
--  El 07/09/2026 se desactivo el razonamiento del modelo y quedo pendiente
--  mirar varios dias de trafico para saber si sirvio. A la hora de comparar
--  "antes" contra "despues" no habia forma de responder cual config sirvio
--  cada turno: v119 ya no existia en ningun lado. Reconstruirlo a mano --por
--  el commit, por la memoria-- es exactamente lo que no hay que tener que
--  hacer dos semanas despues.
--
--  Esto no reemplaza a 'tenant_config': esa sigue siendo la vigente, la que
--  el motor lee. Esta guarda una copia por version, para poder mirar atras.
--
--  LO QUE NO SE PUEDE RECUPERAR
--  ---------------------------
--  Las 119 versiones anteriores se perdieron cuando se sobreescribieron, y
--  no hay de donde sacarlas. La semilla de abajo inserta SOLO la vigente. El
--  informe (cli/medir_turnos.py) marca con '?' los turnos anteriores a la
--  primera version registrada en vez de atribuirlos a algo: un turno de ayer
--  no corrio con la config de hoy, y decir que si seria peor que no saberlo.

create table if not exists asistente.tenant_config_historial (
  organization_id uuid    not null references public.organization(id) on delete cascade,
  config_version  integer not null,
  -- La config COMPLETA, no solo lo que cambio. Un diff obliga a reconstruir
  -- el estado sumando pasos, y basta que falte uno para que lo reconstruido
  -- sea plausible y falso -- que es el peor resultado posible para algo que
  -- existe para responder "que estaba sirviendo".
  config          jsonb   not null,
  -- Cuando empezo a servir. El motor cachea la config y comprueba la version
  -- cada 15 segundos (SEGUNDOS_ENTRE_COMPROBACIONES en nucleo/canales/api.py),
  -- asi que un turno de los 15 segundos siguientes pudo correr con la
  -- anterior todavia. Para comparar dias de trafico es irrelevante; para
  -- explicar UN turno justo en el borde, no.
  creado_en       timestamptz not null default now(),
  primary key (organization_id, config_version)
);

comment on table asistente.tenant_config_historial is
  'Copia de cada version de la config de un tenant, para poder saber cual '
  'estaba sirviendo en una fecha. La vigente vive en asistente.tenant_config; '
  'esta es el historial. Empieza en la version que estuviera vigente el '
  '08/09/2026 -- lo anterior se sobreescribio y no se puede recuperar.';

alter table asistente.tenant_config_historial enable row level security;
alter table asistente.tenant_config_historial force row level security;
grant select, insert on asistente.tenant_config_historial to app_backend;
-- Sin update ni delete a proposito: un historial que se puede reescribir no
-- es un historial. Si una version se guardo mal, lo que corresponde es
-- guardar la siguiente, no cambiar la que ya sirvio.
create policy tenant_aislado on asistente.tenant_config_historial
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());

-- Semilla: la version vigente, con la fecha en que se guardo de verdad
-- ('actualizado_en'), no la de esta migracion.
insert into asistente.tenant_config_historial
       (organization_id, config_version, config, creado_en)
select tc.organization_id, tc.config_version, tc.config,
       coalesce(tc.actualizado_en, tc.creado_en, now())
  from asistente.tenant_config tc
 where tc.config is not null
    on conflict (organization_id, config_version) do nothing;
