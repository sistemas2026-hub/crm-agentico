-- =============================================================================
--  CUANDO ESCALO -- para poder ordenar la cola por quien lleva mas esperando
-- =============================================================================
--  Hoy la bandeja se ordena por 'actualizado_en', que es lo ultimo que paso en
--  la conversacion. Con 164 casos esperando eso ordena al reves de lo que hace
--  falta:
--
--    quien escalo hace tres dias y no volvio a escribir  -> se hunde al fondo
--    quien escalo hace diez minutos y sigue escribiendo  -> sube al tope
--
--  El primero es el que lleva tres dias esperando. El segundo acaba de llegar.
--  'actualizado_en' no distingue "esto es urgente" de "esto es reciente", y no
--  puede: mide otra cosa.
--
--  QUE HABILITA, ADEMAS DE ORDENAR
--  --------------------------------
--  "Volvio a escribir": los mensajes del cliente POSTERIORES a la escalada.
--  Sin esta marca no habia forma de contarlos. Se intento deducirlo de otra
--  manera --mensajes del cliente sin respuesta despues-- y medido contra
--  produccion dio CERO en las 51 conversaciones escaladas, porque el asistente
--  le acusa recibo a cada mensaje mientras espera a la persona. La señal
--  existia; la forma de leerla, no.
--
--  POR QUE UNA COLUMNA Y NO EL PRIMER MENSAJE DE ESCALADA
--  ------------------------------------------------------
--  Se podria buscar en 'messages' el turno donde el asistente anuncio la
--  escalada, pero eso obliga a reconocerlo por su texto -- y ese texto lo
--  redacta el modelo y cambia con el prompt. Una marca explicita no se rompe
--  cuando alguien mejora la redaccion.
--
--  RELLENO
--  -------
--  Para las que ya estan escaladas no se sabe el momento exacto. Se usa
--  'actualizado_en' como aproximacion -- es la mejor cota disponible y deja la
--  cola ordenada de forma razonable desde el primer dia, en vez de con 51
--  nulos que habria que tratar como caso especial en la pantalla para
--  siempre. Las nuevas si llevan el momento real.
--
--  CONSECUENCIA DEL RELLENO, dicha aca para que nadie la descubra midiendo:
--  como el relleno usa 'actualizado_en' --que es, por definicion, el ultimo
--  movimiento-- ningun mensaje puede ser POSTERIOR a el. El contador de
--  "volvio a escribir" da 0 para las 42 que ya estaban esperando, y eso no
--  significa que ninguna insistiera: significa que no se sabe. La pantalla
--  solo dibuja el aviso cuando el contador es mayor que cero, asi que una
--  vieja que insistio se muestra de menos, nunca de mas. De las nuevas en
--  adelante el numero es real.

alter table asistente.conversations
  add column if not exists escalada_en timestamptz;

comment on column asistente.conversations.escalada_en is
  'Momento en que la conversacion paso a una persona. Ordena la cola por '
  'quien lleva mas esperando (actualizado_en mide otra cosa: lo ultimo que '
  'paso) y permite contar los mensajes que el cliente mando DESPUES de '
  'escalar. En las anteriores al 06/09/2026 es una aproximacion: se relleno '
  'con actualizado_en porque el momento real no quedo registrado.';

update asistente.conversations
   set escalada_en = actualizado_en
 where escalada_a_humano and escalada_en is null;

-- -----------------------------------------------------------------------------
--  QUE FALTA Y QUE NO SE PUDO -- lo que el modelo ya escribe y se tiraba
-- -----------------------------------------------------------------------------
--  Al evaluar una escalada, el modelo produce tres textos: un resumen del
--  caso, que NO se pudo comprobar, y cual seria el siguiente paso. Los tres
--  se pegan en la descripcion del ticket del CRM y ahi termina su vida.
--
--  Quien toma el caso desde la bandeja no ve ninguno: tiene que leer el hilo
--  entero para reconstruir a mano lo que el modelo ya habia escrito. Guardarlos
--  no cuesta una llamada mas al modelo -- ya estan calculados.
--
--  Se guardan como columnas y no como un JSON: son tres campos fijos, de
--  significado distinto, y la pantalla los muestra por separado. Un JSON
--  serviria para no volver a migrar, al precio de que nadie pueda consultarlos.

alter table asistente.conversations
  add column if not exists escalada_no_comprobado text,
  add column if not exists escalada_siguiente_paso text;

comment on column asistente.conversations.escalada_no_comprobado is
  'Lo que el asistente NO pudo verificar antes de pasar el caso. Lo redacta '
  'el modelo al evaluar la escalada; hasta el 06/09/2026 solo iba a la '
  'descripcion del ticket. Vacio en las anteriores a esa fecha.';

comment on column asistente.conversations.escalada_siguiente_paso is
  'Que habria que hacer a continuacion, segun el asistente. Misma procedencia '
  'y misma limitacion que escalada_no_comprobado.';

-- La bandeja pide siempre lo mismo: las de una empresa que esperan a alguien,
-- ordenadas por antiguedad de la espera.
create index if not exists conversations_espera_idx
  on asistente.conversations (organization_id, escalada_en)
  where escalada_a_humano;
