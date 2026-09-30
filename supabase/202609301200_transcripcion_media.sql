-- =============================================================================
--  TRANSCRIPCION DE AUDIO  -  lo que el cliente dijo, junto al audio
-- =============================================================================
--
--  POR QUE TRES COLUMNAS Y NO UNA
--  ------------------------------
--  'descripcion' YA existe y es el pie que el cliente ESCRIBIO al mandar el
--  archivo. Meter ahi lo que dijo hablando borraria uno de los dos y nadie
--  podria saber cual fue cual: son dos cosas que dijo la misma persona de dos
--  maneras distintas.
--
--  El estado va aparte del texto porque 'sin transcripcion' tiene tres causas
--  que no se parecen en nada:
--
--    pendiente   todavia no se intento (audio viejo, anterior a esto).
--    procesando  se esta intentando ahora.
--    procesado   se intento y salio. El texto puede estar VACIO y ser
--                correcto: un audio sin voz --un toque sin querer-- transcribe
--                a nada, y eso no es un error.
--    error       se intento y fallo. El motivo esta en error_transcripcion.
--
--  Sin el estado, un texto vacio seria indistinguible de un fallo, y quien
--  mire la bandeja no sabria si reintentar o si no habia nada que oir.
--
--  POR QUE NO SE GUARDA EL MODELO NI EL COSTO
--  ------------------------------------------
--  El modelo es una constante de plataforma (nucleo/canales/transcripcion.py)
--  y guardarlo por fila seria copiar el mismo valor en todas. El costo no se
--  guarda porque esta tabla no es un libro de cuentas: lo que se consumio va
--  al registro de observabilidad, con los tokens que devuelve la API.
--
--  IDEMPOTENTE
--  -----------
--  'if not exists' en las tres: aplicarla dos veces no hace nada la segunda.
--  Las filas que ya existen quedan con NULL, que es lo correcto -- esos audios
--  nunca se intentaron transcribir, y 'pendiente' diria que estan en cola.
-- =============================================================================

alter table asistente.media
  add column if not exists transcripcion text;

alter table asistente.media
  add column if not exists estado_transcripcion text;

alter table asistente.media
  add column if not exists error_transcripcion text;

comment on column asistente.media.transcripcion is
  'Lo que dice el audio, segun gpt-4o-transcribe. NUNCA el caption: ese vive en descripcion.';

comment on column asistente.media.estado_transcripcion is
  'pendiente | procesando | procesado | error. NULL = nunca se intento.';

comment on column asistente.media.error_transcripcion is
  'Por que no se pudo. Sin el texto del proveedor: ver nucleo/canales/transcripcion.py.';

--  Para encontrar los audios que quedaron en error sin recorrer la tabla
--  entera. Parcial a proposito: las filas con transcripcion buena son la
--  mayoria y no hacen falta en este indice.
create index if not exists idx_media_transcripcion_error
  on asistente.media (organization_id, creado_en)
  where estado_transcripcion = 'error';
