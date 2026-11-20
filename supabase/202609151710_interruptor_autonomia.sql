-- =============================================================================
--  INTERRUPTOR DE AUTONOMIA  --  detener las acciones autonomas de una empresa
-- =============================================================================
--
--  QUE ES
--  ------
--  Un control de seguridad por empresa: cuando esta en 'detenido', el motor no
--  ejecuta NINGUNA accion autonoma de ese tenant -- ninguna escritura contra un
--  sistema externo decidida por el modelo, ningun trabajo del scheduler. Las
--  consultas de lectura y lo que un humano aprueba explicitamente siguen
--  andando: detener la autonomia no es apagar el asistente.
--
--  POR QUE UNA TABLA NUEVA Y NO 'asistente.tenant_config'
--  ------------------------------------------------------
--  Es la pregunta obligada -- la configuracion por empresa ya existe, es
--  versionada y se edita desde la pantalla. No sirve para esto, y el motivo no
--  es de gusto: FALLA ABIERTO en los dos caminos que importan.
--
--    1. nucleo/canales/api.py::_config_de sirve una copia en MEMORIA y solo
--       recomprueba la version cada tantos segundos. Y cuando esa comprobacion
--       falla, sigue sirviendo la copia vieja a proposito (esta comentado ahi:
--       "una config de hace un minuto es mucho mejor que un turno fallido").
--       Un interruptor que tarda en llegar, o que no llega si la base se cayo,
--       no es un interruptor.
--    2. nucleo/config/fuente.py::cargar cae al YAML de la imagen cuando no
--       puede leer la base -- y el YAML diria siempre 'activo', porque es la
--       semilla. O sea: cortar la base REACTIVARIA la autonomia.
--
--  Ademas cada tirón del interruptor crearia una version nueva de la config
--  (hoy v146) y 'editor._editar' reserializa el documento entero: una edicion
--  de una clave produjo 68 hojas distintas el 10/09/2026 (ver DESPLIEGUE.md).
--  Un control de seguridad no puede compartir el camino de escritura con la
--  configuracion de producto.
--
--  Y NO es 'limites.max_costo_usd_mes': ese es un tope de gasto y sigue vivo,
--  aparte. Que una empresa gaste poco no dice nada sobre si es seguro que el
--  agente actue solo.
--
--  POR QUE NO 'campo.MutacionIdempotente' NI NINGUNA TABLA DEL CRM
--  ---------------------------------------------------------------
--  Viven en el esquema 'public'. El motor se conecta y BAJA el rol a
--  'app_backend' (nucleo/persistencia/db.py), que tiene privilegios sobre
--  'asistente' y NINGUNO sobre 'public' -- medido el 15/09/2026 contra la base
--  real: 'InsufficientPrivilege: permission denied for schema public'. El motor
--  no puede leer ni escribir ahi sin romper el aislamiento que separa los dos
--  sistemas a proposito.
--
--  POR QUE SOLO AGREGA
--  -------------------
--  La tabla es el historial y el estado a la vez: cada fila es una transicion
--  (quien, cuando, de que estado a cual, por que) y el estado vigente es la
--  fila mas reciente de esa organizacion. Asi el requisito de auditoria
--  --quien lo activo, quien lo desactivo, estado anterior, estado nuevo,
--  motivo-- se cumple sin una segunda tabla y sin poder borrar que alguien lo
--  tiro.
--
--  La regla de solo-agregar se hace con GRANTs, no con un trigger: a
--  'app_backend' se le dan 'select, insert' y nada mas. Sin UPDATE ni DELETE no
--  hace falta una funcion nueva -- y una funcion nueva en 'asistente' volveria
--  no equivalente a cualquier base adoptada por el ledger (ver el comentario de
--  supabase/ledger/esquema/0003_solo_agregar.sql). El owner sigue pudiendo
--  corregir la tabla: eso es un acto deliberado, fuera del runtime.
-- =============================================================================

create table if not exists asistente.interruptor_autonomia (
  id              uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- 'activo'   = la autonomia esta permitida para esta empresa.
  -- 'detenido' = el kill switch esta tirado.
  estado          text not null check (estado in ('activo', 'detenido')),
  -- En que estado estaba antes de esta fila. NULL solo en la primera.
  estado_anterior text check (estado_anterior in ('activo', 'detenido')),
  -- Quien lo movio. Texto libre a proposito: puede ser un profile_id del CRM,
  -- el nombre de un operador, o 'migracion' para la fila semilla de abajo.
  actor           text not null,
  -- Por que. Lo pide el requisito y es lo unico que explica la fila meses
  -- despues.
  motivo          text,
  creado_en       timestamptz not null default now()
);

comment on table asistente.interruptor_autonomia is
  'Kill switch de autonomia por empresa. Solo se AGREGA: cada fila es una '
  'transicion y el estado vigente es la fila mas reciente por organizacion. '
  'Lo lee nucleo/seguridad/interruptor.py antes de cualquier accion autonoma '
  '(escritura externa decidida por el modelo, o trabajo del scheduler). No '
  'vive en tenant_config porque esa ruta falla ABIERTA: se sirve cacheada y '
  'cae al YAML de la imagen cuando la base no responde.';

comment on column asistente.interruptor_autonomia.estado is
  'activo | detenido. Detenido NO apaga el asistente: las consultas de '
  'lectura y las acciones que un humano aprueba siguen funcionando.';

-- La consulta del runtime es siempre la misma: la fila mas reciente de una
-- organizacion. Este indice la resuelve sin leer el historial entero.
create index if not exists interruptor_autonomia_vigente_idx
  on asistente.interruptor_autonomia (organization_id, creado_en desc);


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------
--  'select, insert' y NADA MAS: es lo que vuelve la tabla de solo agregar para
--  el rol con el que corre el motor.

alter table asistente.interruptor_autonomia enable row level security;
alter table asistente.interruptor_autonomia force row level security;
grant select, insert on asistente.interruptor_autonomia to app_backend;

drop policy if exists tenant_aislado on asistente.interruptor_autonomia;
create policy tenant_aislado on asistente.interruptor_autonomia
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());


-- -----------------------------------------------------------------------------
--  FILA SEMILLA  -  por que existe, y por que dice 'detenido'
-- -----------------------------------------------------------------------------
--  Sin fila, "no hay registro" y "esta detenido" se confunden. Con la semilla,
--  la ausencia de fila pasa a significar una sola cosa -- algo anda mal, o el
--  tenant no esta dado de alta -- y el codigo puede tratarla como bloqueo sin
--  ambiguedad (nucleo/seguridad/interruptor.py: fail-closed).
--
--  DICE 'detenido'  --  corregido el 17/09/2026 (paso 10.10)
--  ---------------------------------------------------------
--  La version anterior sembraba 'activo', con este argumento: hay trabajos que
--  ya corren ('cerrar_vencidas' en nucleo/reloj.py) y nacer en 'detenido' los
--  apagaria sin que nadie lo pidiera.
--
--  La premisa resulto falsa, y se midio: en el commit desplegado NO hay una
--  sola referencia al interruptor -- ni en nucleo/reloj.py, ni en
--  nucleo/modelo/motor.py, ni en nucleo/canales/api.py, ni en
--  nucleo/programador/coordinador.py. Toda la integracion del interruptor es
--  codigo que todavia no esta desplegado. Sembrar 'detenido' no apaga nada:
--  hoy nadie consulta esta tabla.
--
--  Y con el orden correcto --migraciones primero, codigo despues-- sembrar
--  'activo' seria autorizar la autonomia de cada empresa sin que nadie lo
--  hubiera decidido, en el mismo momento de instalar el control. Un mecanismo
--  de seguridad no se instala encendido.
--
--  Queda alineado con el alta de un tenant nuevo, que ya nacia detenida
--  (nucleo/seguridad/interruptor.py::sembrar). Una sola regla, sin excepciones:
--  EMPRESA NUEVA O RECIEN INSTRUMENTADA = DETENIDA.
--
--  Levantarlo es un acto explicito y queda registrado:
--      py -3.13 cli/autonomia.py <slug> --reactivar --actor "..." --motivo "..."
--
--  Solo siembra organizaciones que ya tienen configuracion de asistente
--  cargada: las demas no son tenants de este motor.

insert into asistente.interruptor_autonomia
       (organization_id, estado, estado_anterior, actor, motivo)
select distinct tc.organization_id, 'detenido', null, 'migracion',
       'Estado inicial al crear el interruptor (202609151710). Nace DETENIDO: '
       'instalar el control no equivale a autorizar la autonomia. Se levanta '
       'con cli/autonomia.py --reactivar, que deja actor y motivo.'
  from asistente.tenant_config tc
 where not exists (
       select 1 from asistente.interruptor_autonomia i
        where i.organization_id = tc.organization_id);
