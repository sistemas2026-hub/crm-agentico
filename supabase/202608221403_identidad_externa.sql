-- =============================================================================
--  IDENTIDAD EXTERNA DE UN COLABORADOR  -  quien es esta persona en el sistema
--                                          operativo del ISP
-- =============================================================================
--
--  Por que existe
--  ---------------
--  El asistente sabe QUE agentes puede usar cada colaborador
--  (asistente.tenant_users, ver 15_agentes_por_colaborador.sql), pero no sabia
--  quien es esa misma persona del otro lado -- en el sistema donde de verdad
--  se trabaja la orden.
--
--  Sin ese dato, un ticket creado al escalar solo podia asignarse a un usuario
--  FIJO escrito en la config del tenant. Y quedo escrito uno solo: todos los
--  tickets de todos los casos caian sobre la misma persona, incluidas las
--  consultas de factura, que no son suyas.
--
--  Generica a proposito
--  --------------------
--  'sistema' es texto libre y no una columna llamada como un proveedor: el
--  nucleo no conoce a ninguno (ver ARQUITECTURA.md y la guarda
--  tests/test_nucleo_sin_tenants.py). El proximo ISP va a tener otro sistema
--  operativo y esta tabla no deberia enterarse.
--
--  'nombre_visible' se guarda junto al identificador aunque sea redundante:
--  el identificador solo no le dice nada a quien mira la pantalla, y volver a
--  consultar la API externa para poder MOSTRAR un nombre es una llamada por
--  fila. Es una copia, no la fuente de verdad -- si alguien renombra a esa
--  persona alla, aca queda el nombre viejo hasta la proxima vez que se elija.
-- =============================================================================

create table if not exists asistente.identidades_externas (
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- El perfil del CRM. Mismo TIPO que asistente.tenant_users.profile_id: si
  -- una tabla lo guarda como texto y la otra como uuid, cualquier cruce entre
  -- las dos empieza a necesitar casts y tarde o temprano alguien escribe algo
  -- que no es un uuid y nadie se entera hasta el insert.
  profile_id      uuid not null,
  -- Que sistema externo. Permite que una misma persona tenga identidad en mas
  -- de uno el dia que haga falta, sin migrar nada.
  sistema         text not null,
  -- El id tal cual lo espera ese sistema al asignar. Texto, no entero: no
  -- todos los proveedores usan numeros.
  identificador   text not null,
  nombre_visible  text not null default '',
  actualizado_en  timestamptz not null default now(),
  primary key (organization_id, profile_id, sistema)
);

comment on table asistente.identidades_externas is
  'Quien es un colaborador del CRM dentro de un sistema externo del tenant '
  '(el operativo del ISP, por ejemplo), para poder asignarle trabajo real '
  'ahi. Una fila por persona y por sistema.';

alter table asistente.identidades_externas enable row level security;
alter table asistente.identidades_externas force row level security;

grant select, insert, update, delete on asistente.identidades_externas to app_backend;

drop policy if exists tenant_aislado on asistente.identidades_externas;
create policy tenant_aislado on asistente.identidades_externas
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
