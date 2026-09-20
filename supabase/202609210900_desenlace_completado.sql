-- =============================================================================
--  B6: COMPLETAR EL DESENLACE DESPUES DEL CIERRE  (contrato §3.5)
-- =============================================================================
--  §3.5 dice que los cierres por el cliente (T15a, T15b) y por inactividad
--  (T18) dejan el desenlace en NULL "y se completan despues si una persona
--  revisa". Esa completada existe ahora como transicion propia
--  (transiciones.completar_desenlace) y necesita su tipo de evento.
--
--  POR QUE UN TIPO PROPIO Y NO UN SEGUNDO 'cerrada'
--  ------------------------------------------------
--  Porque no vuelve a cerrar nada. La conversacion ya estaba cerrada, sigue
--  cerrada, y 'cerrada_por_tipo' no cambia: la cerro el cliente o el reloj, y
--  que alguien le ponga el codigo despues no lo convierte en el que cerro.
--  Dos eventos 'cerrada' en el mismo expediente se leerian como dos cierres, y
--  cualquier conteo de "cuantas cerro el cliente solo" pasaria a mentir.
--
--  LO QUE ESTE EVENTO NO ES
--  ------------------------
--  No es una correccion. El desenlace se escribe UNA vez, solo sobre NULL: la
--  transicion lo condiciona en el propio UPDATE. Si alguna vez hiciera falta
--  corregir uno ya escrito, eso es otra decision, con su propio tipo de evento
--  y su propia discusion sobre quien puede hacerlo -- no este.
--
--  QUE NO CAMBIA
--  -------------
--  Ninguna fila existente, ninguna columna. Solo se amplia la lista de tipos
--  que el CHECK acepta.

alter table asistente.relevo_eventos
  drop constraint if exists relevo_eventos_tipo_check;
alter table asistente.relevo_eventos
  add constraint relevo_eventos_tipo_check check (tipo in (
    'escalada', 'intervencion', 'devolucion_solicitada', 'devuelta_a_ia',
    'devolucion_fallida', 'caso_externo_cerrado',
    'tomada', 'soltada', 'reasignada',
    'pendiente_interno_abierto', 'pendiente_interno_cerrado',
    'evaluacion_revisada',
    'accion_propuesta_duplicada', 'accion_aprobada', 'accion_rechazada',
    'accion_vencida', 'accion_cancelada', 'accion_desconocida',
    'cerrada', 'desenlace_completado'));
