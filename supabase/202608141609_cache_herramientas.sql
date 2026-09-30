-- =============================================================================
--  CACHE DE HERRAMIENTAS  -  respuestas de herramientas 'http' con cache=true
-- =============================================================================
--
--  Por que existe
--  --------------
--  Algunas herramientas consultan un catalogo que casi no cambia (un plan de
--  internet, una zona) pero exigen una llamada por registro para resolver un
--  dato puntual (ej. si un plan incluye TV -- ver consultar_plan_tv en
--  tenants/rapilink.config.yaml). Sin cache, cada conversacion que toca ese
--  dato le pega a la API de nuevo por algo que no cambio desde la ultima vez.
--
--  Generico a proposito (ver nucleo/config/schema.py:Herramienta.cache y
--  nucleo/modelo/motor.py:_ejecutar_tool): cualquier herramienta tipo 'http'
--  puede activarlo, no es exclusivo de un proveedor ni de un caso.
--
--  NUNCA datos por cliente (saldo, estado del servicio): el validador de
--  Herramienta (nucleo/config/schema.py) rechaza 'cache=true' en cualquier
--  herramienta que tenga 'inyectar_sesion' -- esa marca es justamente "la
--  respuesta depende de que cliente pregunta". Sin esa combinacion, lo que
--  cae aca es catalogo (un plan, una zona), nunca el dato crudo de un
--  cliente -- ver el docstring de nucleo/persistencia/db.py.
-- =============================================================================

create table if not exists asistente.herramientas_cache (
  organization_id uuid not null references public.organization(id) on delete cascade,
  herramienta     text not null,
  -- Los argumentos ya resueltos (filtros_verificados + inyectar_sesion),
  -- ordenados y unidos en un string -- ver nucleo/modelo/motor.py.
  clave           text not null,
  respuesta       jsonb not null,
  actualizado_en  timestamptz not null default now(),
  primary key (organization_id, herramienta, clave)
);

comment on table asistente.herramientas_cache is
  'Respuestas cacheadas de herramientas tipo http con cache=true (ver '
  'nucleo/config/schema.py:Herramienta). Pensado para catalogos que '
  'cambian poco (un plan, una zona) pero exigen una llamada por registro '
  'para resolver un dato. El validador de Herramienta rechaza cache=true '
  'combinado con inyectar_sesion, asi que aca nunca entra el dato crudo '
  'de un cliente puntual (saldo, estado del servicio).';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------

alter table asistente.herramientas_cache enable row level security;
alter table asistente.herramientas_cache force row level security;
grant select, insert, update, delete on asistente.herramientas_cache to app_backend;

drop policy if exists tenant_aislado on asistente.herramientas_cache;
create policy tenant_aislado on asistente.herramientas_cache
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
