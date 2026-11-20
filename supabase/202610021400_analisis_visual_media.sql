-- =============================================================================
--  ANALISIS VISUAL  -  que se ve en la foto, junto a la foto
-- =============================================================================
--
--  POR QUE COLUMNAS PROPIAS Y NO LAS DE TRANSCRIPCION
--  --------------------------------------------------
--  'transcripcion', 'estado_transcripcion' y 'error_transcripcion' ya existen
--  y son de AUDIO. Reusarlas para imagen ahorraria tres columnas y costaria
--  lo unico que importa: poder saber que produjo ese texto. Una fila con
--  'transcripcion' llena no diria si alguien hablo o si una camara miro, y
--  las dos cosas tienen reglas distintas de privacidad y de reintento.
--
--  POR QUE EL ESTADO VA APARTE DEL TEXTO
--  -------------------------------------
--  Mismo motivo que en transcripcion: 'sin analisis' tiene causas que no se
--  parecen en nada.
--
--    pendiente   todavia no se intento (foto vieja, anterior a esto).
--    procesando  se esta intentando ahora.
--    procesado   se intento y salio. El analisis puede estar VACIO y ser
--                correcto: la foto de un gato no tiene ningun elemento del
--                catalogo, y eso no es un error.
--    error       se intento y fallo. El motivo esta en error_analisis.
--
--  Sin el estado, un analisis vacio seria indistinguible de un fallo, y quien
--  mire la bandeja no sabria si reintentar o si no habia nada que ver.
--
--  QUE GUARDA 'analisis_visual', Y QUE NO
--  --------------------------------------
--  La DESCRIPCION que escribio el modelo mirando la foto, en texto. No el
--  bloque ya rotulado que lee el agente: el rotulo y el pie del cliente se
--  vuelven a armar cada vez que se reusa, y guardarlos dejaria el pie
--  escrito dos veces el dia que alguien mande la misma foto con otro
--  comentario.
--
--  NO guarda la imagen ni nada parecido a base64: los bytes ya viven en
--  'contenido', y duplicarlos en texto multiplicaria por 1.3 el tamano de la
--  fila sin agregar un solo dato.
--
--  LO QUE ESTA COLUMNA NO PUEDE PROMETER, y conviene que este escrito donde
--  se guarda: el texto lo escribe un modelo sin catalogo cerrado, asi que
--  puede contener cualquier cosa que el modelo haya decidido decir. Pasa por
--  nucleo/seguridad/redaccion.py antes de llegar aca --que tapa cedulas,
--  telefonos, correos y coordenadas-- pero eso es un filtro por patron, no
--  una lista blanca. Importa porque esta fila se borra con la foto a los 30
--  dias (limites.retencion_multimedia_dias) mientras que el MISMO texto, ya
--  dentro del hilo de la conversacion, vive 365.
--
--  POR QUE NO SE GUARDA EL MODELO NI EL COSTO
--  ------------------------------------------
--  Igual que en transcripcion: el modelo es una constante de plataforma
--  (nucleo/canales/vision.py) y guardarlo por fila seria copiar el mismo
--  valor en todas. El costo va al registro de observabilidad, con los tokens
--  que devuelve la API -- esta tabla no es un libro de cuentas.
--
--  IDEMPOTENTE
--  -----------
--  'if not exists' en las tres: aplicarla dos veces no hace nada la segunda.
--  Las filas que ya existen quedan con NULL, que es lo correcto -- esas fotos
--  nunca se intentaron analizar, y 'pendiente' diria que estan en cola.
-- =============================================================================

alter table asistente.media
  add column if not exists analisis_visual text;

alter table asistente.media
  add column if not exists estado_analisis text;

alter table asistente.media
  add column if not exists error_analisis text;

comment on column asistente.media.analisis_visual is
  'Lo que se ve en la foto, segun el modelo de vision. Texto, no JSON. Pasa por redaccion.py antes de guardarse. NUNCA base64 ni la imagen.';

comment on column asistente.media.estado_analisis is
  'pendiente | procesando | procesado | error. NULL = nunca se intento.';

comment on column asistente.media.error_analisis is
  'Por que no se pudo. Sin el texto del proveedor: ver nucleo/canales/vision.py.';

--  Para encontrar las fotos que quedaron en error sin recorrer la tabla
--  entera. Parcial a proposito: las filas con analisis bueno son la mayoria
--  y no hacen falta en este indice. Mismo criterio y misma forma que
--  idx_media_transcripcion_error.
create index if not exists idx_media_analisis_error
  on asistente.media (organization_id, creado_en)
  where estado_analisis = 'error';
