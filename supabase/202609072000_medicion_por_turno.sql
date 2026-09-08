-- =============================================================================
--  CUANTAS VECES SE LE HABLA AL MODELO PARA PRODUCIR UNA RESPUESTA
-- =============================================================================
--  'messages' ya tenia tokens_entrada, tokens_salida, costo_usd, modelo y
--  latencia_ms. Estaban TODAS vacias: el consumo solo se volcaba al agregado
--  diario (asistente.usage_daily), que dice cuanto cuesta una llamada en
--  promedio pero no CUAL turno salio caro ni por que.
--
--  Medido el 07/09/2026 con mensajes reales de WhatsApp: la espera va de 4.4
--  a 13.6 segundos, y las herramientas explican entre 0 y 1.7 de esos
--  segundos. El resto es el modelo. Las dos palancas sobre eso son el TAMAÑO
--  del prompt (tokens_entrada, que ya tiene columna) y CUANTAS VECES se llama
--  al modelo en un turno -- que no tenia donde guardarse.
--
--  Un turno puede llamar al modelo varias veces: una para elegir herramientas,
--  otra por cada ronda de herramientas, y una final para redactar. Sin este
--  numero, un turno de 11 segundos y uno de 4 se ven igual en la base y no hay
--  forma de saber si la diferencia fue un prompt mas grande o tres llamadas
--  en vez de una.

alter table asistente.messages
  add column if not exists llamadas_modelo smallint;

comment on column asistente.messages.llamadas_modelo is
  'Cuantas veces se hablo con el modelo para producir ESTA respuesta. Junto '
  'con tokens_entrada son las dos palancas sobre la latencia: un turno lento '
  'lo es por un prompt grande o por muchas idas al modelo, y sin este numero '
  'no se distinguen. NULL en todo lo anterior a la noche del 07/09/2026.';
