-- =============================================================================
--  CURSOR DE EVENTOS  -  entregar cada tool_call UNA vez, sin perder ninguna
-- =============================================================================
--
--  Por que existe (29/10/2026)
--  ---------------------------
--  La empresa virtual necesita leer los eventos del motor de forma incremental:
--  pedir "lo que paso desde la ultima vez" en vez de recargar la ventana
--  entera cada 12 segundos.
--
--  EL CURSOR OBVIO NO SIRVE, Y SE MIDIO.  Paginar por (creado_en, id) pierde
--  eventos, reproducido contra PostgreSQL 17.11: de 2 insertados se entrego 1.
--
--  La causa es que 'creado_en default now()' es el instante en que la
--  transaccion EMPEZO, no en el que hizo commit. Una transaccion que arranca a
--  las 10:00:00 y commitea a las 10:00:05 deja una fila sellada 10:00:00; si el
--  lector ya avanzo su cursor a 10:00:03, esa fila queda DETRAS y no se entrega
--  nunca. El 'id' desempata sellos iguales -- no arregla sellos anteriores.
--
--  LA SOLUCION: ordenar por identificador de transaccion, y no entregar nada
--  que todavia pueda tener transacciones por delante.
--
--      where tx < pg_snapshot_xmin(pg_current_snapshot())
--        and (tx, id) > (:cursor_tx, :cursor_id)
--      order by tx, id
--
--  'pg_snapshot_xmin' es la transaccion mas antigua AUN ACTIVA. Entregar solo
--  por debajo de esa frontera garantiza que, cuando se entrego hasta tx = X,
--  ninguna transaccion con tx <= X puede commitear despues. Esa es la garantia,
--  y PostgreSQL la define asi a proposito: distingue xid activos, completados y
--  todavia no visibles.
--
--  'xid8' y no 'xid': 64 bits, NO da la vuelta. Un xid de 32 bits se reinicia
--  y un cursor guardado quedaria del lado equivocado de la comparacion.
--
--  POR QUE NO HACE FALTA 'CREATE INDEX CONCURRENTLY'
--  --------------------------------------------------
--  El ledger (cli/migrar_asistente.py) envuelve cada migracion en una
--  transaccion, y PostgreSQL rechaza CONCURRENTLY ahi dentro. No hace falta,
--  porque los tres pasos de abajo son de METADATA:
--
--    1) ADD COLUMN SIN default   no reescribe la tabla. Con un default VOLATIL
--                                como pg_current_xact_id() la reescribiria
--                                ENTERA y tomaria AccessExclusiveLock largo.
--                                Por eso va en dos pasos y no en uno.
--    2) SET DEFAULT              solo afecta a las filas que entren despues.
--    3) indice PARCIAL           'where tx is not null': al crearse NINGUNA
--                                fila tiene tx, asi que nace vacio.
--
--  Medido sobre 400.000 filas / 46 MB simuladas en PostgreSQL 17.11:
--    indice recien creado   8192 bytes
--    los tres pasos         0,050 s
--
--  LAS FILAS HISTORICAS QUEDAN CON tx NULL, y es deliberado: el indice parcial
--  las excluye y la consulta incremental tampoco las ve. No se pierden -- se
--  leen por la foto de /centro-mando, que no cambia. Rellenarlas seria
--  reescribir la tabla entera para datos que la pantalla ya no necesita.
--
--  REVERSION
--  ---------
--  Es reversible y barata, en el orden inverso. Nada de lo de abajo destruye
--  datos: la columna es nueva y el indice es derivado.
--
--      drop index if exists asistente.tool_calls_cursor_idx;
--      alter table asistente.tool_calls alter column tx drop default;
--      alter table asistente.tool_calls drop column if exists tx;
--
--  Volver atras deja la tabla exactamente como estaba. Lo unico que se pierde
--  es el 'tx' de las filas escritas mientras estuvo puesta, y eso solo apaga
--  el flujo incremental: la foto sigue funcionando.
-- =============================================================================

--  LIMITES DE ESPERA. Los tres pasos son de metadata y tardan milisegundos,
--  pero los tres piden AccessExclusiveLock sobre la tabla: si hay una consulta
--  larga encima, la migracion se queda esperando el lock Y ADEMAS encola a todo
--  el que llegue detras. Con 'lock_timeout' falla rapido en vez de congelar la
--  auditoria del motor; se reintenta cuando la tabla este tranquila.
--
--  Es el mismo criterio con el que se aplico el hardening de la base el
--  15/09/2026 (DESPLIEGUE.md): statement_timeout corto y lock_timeout = 1s.
set local lock_timeout = '3s';
set local statement_timeout = '60s';

--  1) La columna, SIN default: metadata, no reescribe.
alter table asistente.tool_calls
  add column if not exists tx xid8;

--  2) El default, que solo alcanza a las filas nuevas.
alter table asistente.tool_calls
  alter column tx set default pg_current_xact_id();

--  3) El indice del cursor. El orden de las columnas es el de la consulta:
--     primero la empresa (que SIEMPRE filtra, y es el aislamiento), despues el
--     cursor. Parcial, asi que nace vacio y crece solo con lo nuevo.
create index if not exists tool_calls_cursor_idx
  on asistente.tool_calls (organization_id, tx, id)
  where tx is not null;

comment on column asistente.tool_calls.tx is
  'Identificador de transaccion (xid8) para el cursor de eventos. NULL en las '
  'filas anteriores al 29/10/2026: esas se leen por la foto de /centro-mando, '
  'no por el flujo incremental. Ver 202611101200_tool_calls_cursor.sql.';
