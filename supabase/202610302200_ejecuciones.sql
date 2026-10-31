-- =============================================================================
--  EJECUCIONES  -  saber que un agente esta trabajando AHORA, no hace un rato
-- =============================================================================
--
--  Por que existe (30/10/2026)
--  ---------------------------
--  'asistente.tool_calls' se escribe cuando la llamada TERMINA, con su duracion.
--  No existe la fila "en vuelo", y por eso el motor se niega --con razon-- a
--  emitir el estado 'waiting_tool': una herramienta lenta y una recien
--  terminada se ven exactamente igual.
--
--  La consecuencia en la oficina virtual es que el personaje solo puede
--  representar COSAS QUE YA PASARON, con una animacion breve y acotada. Esta
--  tabla es lo que falta para que pueda representar lo que esta pasando.
--
--  UNA LLAMADA NO ES UNA EJECUCION
--  -------------------------------
--  Un turno del agente puede llamar a cinco herramientas. La ejecucion es EL
--  TURNO, no cada llamada. Una fila por llamada daria cinco "esta trabajando"
--  solapados para un solo trabajo, y ademas multiplicaria por cinco el costo
--  que la seccion siguiente explica.
--
--  POR QUE ES UNA TABLA NUEVA Y NO COLUMNAS EN 'tool_calls'
--  --------------------------------------------------------
--  'tool_calls' es auditoria: se escribe una vez y no se toca mas. Una fila de
--  ejecucion MUTA --nace iniciada y termina terminada-- y mezclar las dos cosas
--  convierte un registro inmutable en uno editable. Ademas el grano es
--  distinto: una ejecucion agrupa N llamadas.
--
--  EL COSTO, MEDIDO ANTES DE DECIDIR
--  ---------------------------------
--  Un viaje a la base de produccion cuesta 1.054 ms de mediana (medido el
--  07/09/2026, y es la razon por la que la traza del turno se mueve a un hilo
--  aparte: ver nucleo/canales/api.py).
--
--  O sea que escribir la fila 'iniciada' en el camino critico le agregaria UN
--  SEGUNDO a cada respuesta del cliente -- para que una pantalla que quiza
--  nadie este mirando pueda animar un personaje. Eso es cobrarle al cliente el
--  costo de nuestro registro, que es justo lo que ya se decidio no hacer.
--
--  Por eso el motor la escribe EN UN HILO, fuera del camino critico, con la
--  misma regla que la traza: si el proceso muere en ese segundo se pierde la
--  observabilidad de un turno, no el turno. Y el cierre se pliega dentro del
--  viaje que la traza ya hace, asi que el costo total es UN viaje mas por
--  turno, no dos.
--
--  'desconocida' NO SE GUARDA, SE DERIVA
--  -------------------------------------
--  El diseño original listaba 'desconocida' como un quinto estado guardado, que
--  un barrido escribiria pasado un umbral. No se hace asi, y el motivo ya esta
--  decidido en este repositorio: la salud del seguimiento de campo se CALCULA y
--  no se guarda, porque un veredicto guardado diria "al dia" mientras el reloj
--  corre (ver SPEC/objetivos/seguimiento-campo-por-ticket.md).
--
--  Aca pasa lo mismo y peor: el barrido es un proceso que TIENE que estar
--  corriendo, y este repositorio ya se quemo con eso --el reloj de tareas
--  colgaba de un bloque __main__ que gunicorn nunca ejecuta--. Si el barrido no
--  corre, las filas se quedan en 'iniciada' para siempre y la pantalla afirma
--  que alguien trabaja desde hace tres dias.
--
--  Derivado en la lectura no puede fallar asi: una ejecucion 'iniciada' mas
--  vieja que el umbral ES desconocida, la calcule quien la calcule, sin que
--  nadie tenga que haber corrido nada.
--
--  EL MISMO CURSOR QUE E1
--  ----------------------
--  'tx xid8 default pg_current_xact_id()' y el indice por (organization_id, tx,
--  id). Es la misma garantia de entrega del flujo incremental: ordenar por
--  identificador de transaccion y no entregar nada que todavia pueda tener
--  transacciones por delante. Ver 202610291700_tool_calls_cursor.sql.
--
--  COMO SE REVIERTE
--  ----------------
--      drop table if exists asistente.ejecuciones;
--
--  Es una tabla nueva y nada la lee todavia salvo el endpoint nuevo: tirarla no
--  toca ninguna fila existente.
-- =============================================================================

set local lock_timeout = '3s';
set local statement_timeout = '60s';

create table if not exists asistente.ejecuciones (
    id               uuid primary key default gen_random_uuid(),
    organization_id  uuid not null,

    -- Quien trabaja. Es el nombre del rol en la configuracion del tenant, el
    -- mismo que viaja en tool_calls.rol_solicitante y el que la oficina usa
    -- para saber que puesto animar.
    agente           text not null,

    -- La conversacion del turno. Nullable a proposito: un turno del
    -- programador o de /interno no tiene una conversacion detras, y forzarlo
    -- obligaria a inventar una.
    conversation_id  uuid,

    -- iniciada | terminada | fallida | cancelada
    --
    -- 'desconocida' NO esta: se deriva en la lectura. Ver arriba.
    estado           text not null default 'iniciada'
                     check (estado in ('iniciada', 'terminada', 'fallida', 'cancelada')),

    -- Cuantas herramientas llamo el turno. Se completa al cerrar; mientras
    -- corre es 0 y eso es cierto: todavia no termino ninguna.
    n_llamadas       integer not null default 0,

    -- Si alguna fallo. Lo que decide si el personaje se pone en alerta.
    hubo_fallo       boolean not null default false,

    iniciada_en      timestamptz not null default now(),
    terminada_en     timestamptz,

    -- UN CIERRE CONTRADICTORIO NO PISA AL PRIMERO, SE ANOTA.
    --
    -- Hoy hay un solo cerrador por turno y siempre escribe 'terminada', asi
    -- que esto no es alcanzable. Pero el esquema admite 'fallida' y
    -- 'cancelada', y el dia que exista un segundo escritor --una cancelacion
    -- externa, un barrido, un corte-- dos terminales distintos podrian llegar
    -- en cualquier orden. Sin guarda, el ultimo en llegar ganaria, que es
    -- justo lo contrario de lo que vale: el primero es el que vio terminar la
    -- ejecucion.
    --
    -- Asi que el primer estado terminal MANDA y el segundo levanta esta
    -- bandera. No se descarta en silencio: una contradiccion es un hecho que
    -- alguien tiene que poder ver.
    cierre_en_conflicto boolean not null default false,

    -- La frontera de entrega del flujo incremental.
    tx               xid8 not null default pg_current_xact_id()
);

-- El indice del cursor: mismo que el de tool_calls. Nace vacio, asi que no
-- hace falta CONCURRENTLY (y el ledger no lo permitiria: envuelve cada
-- migracion en una transaccion).
create index if not exists ejecuciones_cursor_idx
    on asistente.ejecuciones (organization_id, tx, id);

-- El que contesta "quien esta trabajando ahora". Parcial: solo las abiertas,
-- que son unas pocas en cualquier instante, y asi el indice se mantiene chico
-- aunque la tabla crezca.
create index if not exists ejecuciones_abiertas_idx
    on asistente.ejecuciones (organization_id, iniciada_en desc)
    where estado = 'iniciada';

-- EL AISLAMIENTO, con el patron que ya usa el esquema.
--
-- 'force' no es decorativo: sin el, el DUEÑO de la tabla se saltea la politica
-- entera. Y en esta base eso no es teorico -- 'postgres' y 'motor_user' tienen
-- BYPASSRLS, asi que lo unico que de verdad aisla es
-- 'set local role app_backend' + 'set local app.current_tenant', los dos
-- locales. La politica es la red que convierte un olvido en CERO filas en vez
-- de en TODAS.
alter table asistente.ejecuciones enable row level security;
alter table asistente.ejecuciones force row level security;

grant select, insert, update on asistente.ejecuciones to app_backend;

drop policy if exists tenant_aislado on asistente.ejecuciones;
create policy tenant_aislado on asistente.ejecuciones
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
