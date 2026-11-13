-- =============================================================================
--  LA BANDEJA DECIA 155 Y ERAN 31
-- =============================================================================
--  Medido el 07/09/2026 sobre produccion, de las 155 que la cabecera contaba
--  como "esperan a una persona":
--
--     42  escaladas de verdad
--    113  marcadas 'necesita_atencion_humana' SIN haber escalado nunca
--     28  ya CERRADAS, contadas igual
--    115  de canales de prueba (simulado, prueba-wifi, api, test-...)
--
--  Conversaciones de WhatsApp real, abiertas y esperando: 31. De esas, 17
--  escaladas. El numero estaba inflado cinco veces, y un contador en el que
--  no se puede confiar es peor que ningun contador: quien atiende deja de
--  mirarlo.
--
--  LA CAUSA -- no era el filtro, era el DEFAULT
--  --------------------------------------------
--  'necesita_atencion_humana' se creo con DEFAULT TRUE. Toda conversacion
--  nace marcada como que necesita a una persona, y lo unico que corrige esa
--  marca es marcar_escalada(). Una conversacion que el asistente resuelve
--  solo --que es el caso normal, y el objetivo del producto-- se queda con la
--  marca puesta para siempre.
--
--  El frontend la trata como razon INDEPENDIENTE para estar en la cola, con
--  este razonamiento escrito en el codigo: cubre el caso en que el evaluador
--  de escalamiento se cayo y no se pudo decidir si correspondia escalar
--  (NO_DETERMINADO), y ahi el pedido del cliente se perderia en silencio.
--
--  Ese razonamiento es bueno. El problema es que de las 113, solo 3 son
--  NO_DETERMINADO: las otras 111 tienen 'estado_escalada' en NULL. No son el
--  caso que se queria cubrir -- son el default que nadie apago.
--
--  QUE CAMBIA
--  ----------
--  El default pasa a FALSE: la marca vuelve a significar lo que dice su
--  nombre, y la pone quien tiene algo que decir (marcar_escalada, o el
--  camino de NO_DETERMINADO). Y se apaga en las que la traen puesta sin
--  haber escalado ni haber fallado el evaluador.
--
--  Lo que NO se toca: las 42 escaladas. Ahi la marca la puso el motor a
--  proposito y distingue "escalo pero puede esperar" de "alguien tiene que
--  entrar ya" -- ver supabase/202608131420_necesita_atencion_humana.sql.
--
--  El filtro de conversaciones CERRADAS y el de canales de prueba no van
--  aca: son decision de la pantalla, no del dato. Una conversacion cerrada
--  sigue estando cerrada aunque alguien quiera verla.

alter table asistente.conversations
  alter column necesita_atencion_humana set default false;

comment on column asistente.conversations.necesita_atencion_humana is
  'Alguien del equipo tiene que entrar a esta conversacion. La pone el motor '
  'al escalar (donde distingue "escalo pero puede esperar" de "hace falta '
  'alguien ya") y el camino de NO_DETERMINADO, cuando el evaluador se cayo y '
  'no se pudo decidir si correspondia escalar. Nacio con DEFAULT TRUE por '
  'error y eso inflaba la bandeja cinco veces: desde el 07/09/2026 el default '
  'es false y la marca solo esta puesta cuando alguien la puso.';

-- Las que la traen puesta sin haber escalado y sin que el evaluador haya
-- fallado: es el default viejo, no una decision. Se apaga.
update asistente.conversations
   set necesita_atencion_humana = false
 where necesita_atencion_humana
   and not escalada_a_humano
   and coalesce(estado_escalada, '') <> 'NO_DETERMINADO';
