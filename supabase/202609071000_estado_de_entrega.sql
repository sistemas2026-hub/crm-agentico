-- =============================================================================
--  ESTADO DE ENTREGA POR MENSAJE -- "lo mande" no es "le llego"
-- =============================================================================
--  Meta manda acuses (sent / delivered / read / failed) por el mismo webhook
--  que los mensajes, y nucleo/canales/whatsapp.py::estados_entrantes() ya los
--  sabe leer desde hace tiempo -- con su codigo de error y todo.
--
--  Se imprimen en el log y se tiran. No habia donde guardarlos: 'messages' no
--  tenia el wamid, que es la unica clave que casa un acuse con el mensaje que
--  lo produjo.
--
--  La consecuencia se ve del lado de quien atiende: escribe, ve su mensaje en
--  el hilo, y da el caso por contestado. Si el envio fallo --lo mas comun no
--  es una caida sino la ventana de 24 h de WhatsApp-- el aviso aparece una
--  sola vez, en la respuesta del POST, y despues no queda rastro. Al recargar
--  la pagina el mensaje se ve exactamente igual que uno entregado.
--
--  QUE SE GUARDA
--  -------------
--    wamid            el id que devuelve Meta al enviar. Es la clave del cruce
--                     y por eso tiene indice propio: el webhook llega con el
--                     wamid y nada mas.
--    estado_entrega   pendiente -> enviado -> entregado -> leido, o fallido.
--                     Se escribe en español porque es lo que se muestra; la
--                     traduccion desde los nombres de Meta vive en un solo
--                     lugar (nucleo/canales/api.py).
--    error_entrega    por que fallo, en palabras. El CODIGO de Meta importa
--                     mas que su texto -- el mensaje es el mismo ('Message
--                     undeliverable') para causas opuestas-- asi que se guarda
--                     ya traducido a algo que explique que hacer.
--
--  POR QUE NO RETROCEDE
--  --------------------
--  Los acuses de Meta NO llegan siempre en orden: un 'delivered' puede
--  entrar despues de un 'read'. Sin cuidado, un mensaje leido volveria a
--  decir "entregado". El orden se fuerza en el UPDATE (ver
--  persistencia.marcar_entrega), no aca -- pero el orden de los valores es
--  parte del contrato de esta columna y por eso queda escrito.
--
--  Los mensajes anteriores a hoy quedan en NULL, que es lo correcto: no se
--  sabe si llegaron. NULL significa "no se sabe" y la pantalla no dibuja
--  nada; 'pendiente' significaria "se esta enviando", que seria falso.

alter table asistente.messages
  add column if not exists wamid text,
  add column if not exists estado_entrega text,
  add column if not exists error_entrega text;

comment on column asistente.messages.wamid is
  'Id que WhatsApp le asigna al mensaje. Unica clave para casar los acuses de '
  'entrega, que llegan por webhook sin ninguna otra referencia. NULL en los '
  'canales que no son WhatsApp y en todo lo anterior al 07/09/2026.';

comment on column asistente.messages.estado_entrega is
  'pendiente | enviado | entregado | leido | fallido. NULL = no se sabe (otro '
  'canal, o anterior al registro). Nunca retrocede: los acuses de Meta pueden '
  'llegar desordenados.';

-- El webhook llega con el wamid y nada mas: sin este indice, cada acuse
-- --y son varios por mensaje-- recorre la tabla entera.
create index if not exists messages_wamid_idx
  on asistente.messages (wamid) where wamid is not null;
