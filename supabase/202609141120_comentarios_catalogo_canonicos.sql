-- ============================================================================
-- Comentarios de catalogo canonicos: formaliza en git el texto que produccion
-- ya tiene en cinco objetos del esquema asistente.
-- ============================================================================
--
-- Fecha real de autoria: 15/09/2026. El timestamp del nombre (202609141120) es
-- ORDEN LOGICO: va despues de 202609141110_roles_operativos_public.sql y antes
-- de P2 (202609141200_scheduler_persistente.sql).
--
-- POR QUE. La comparacion de solo lectura contra produccion del 15/09/2026
-- (10:58 Bogota) encontro que estos cinco comentarios no coinciden con el
-- texto que declaran sus migraciones historicas. El texto de produccion llego
-- fuera de git (borradores que se aplicaron y no se commitearon). Para la
-- adopcion se decidio que el estado canonico es EXACTAMENTE el de produccion:
-- no se escribe produccion para parecerse a git; git declara lo que existe.
--
--   asistente.conversations.ticket_operativo    (202608281530_ticket_operativo.sql)
--   asistente.verificaciones_accion             (202609021130_verificacion_accion.sql)
--   asistente.conversations.estado_escalada     (202609021500_estado_escalada.sql)
--   asistente.conversations.escalada_detalle    (202609021500_estado_escalada.sql)
--   asistente.messages.llamadas_modelo          (202609072000_medicion_por_turno.sql)
--
-- Produccion ya contiene estos textos: al adoptarse, esta migracion se verifica
-- (comentario_tabla / comentario_columna) y no ejecuta nada alli.
--
-- Sin efecto funcional: son documentacion del esquema. Los textos se
-- generaron por programa desde la lectura capturada de produccion y se
-- validaron por md5 contra ella; espacios y saltos de linea son exactos (el de
-- ticket_operativo es un salto real dentro del literal). No editar a mano: una
-- mejora editorial futura va en una migracion nueva y normal.
-- ============================================================================

comment on column asistente.conversations.ticket_operativo is
    'Identificador del ticket en el sistema operativo del ISP (WispHub en el primer
         despliegue), abierto al escalar. Permite responderlo y cerrarlo desde el codigo.';

comment on table asistente.verificaciones_accion is
    'Comprobacion posterior de que una accion produjo su efecto tecnico. El estado lo calcula el codigo comparando la medicion previa con una posterior y fresca -- nunca el modelo.';

comment on column asistente.conversations.estado_escalada is
    'ESCALAMIENTO_CONFIRMADO | ESCALAMIENTO_NO_CONFIRMADO | NO_DETERMINADO -- lo calcula el codigo, ver nucleo/seguimiento/estado_escalada.py. NO_DETERMINADO significa que el evaluador fallo, nunca que se haya escalado.';

comment on column asistente.conversations.escalada_detalle is
    'Por que quedo en ese estado: si el evaluador fallo, si el caso o el ticket se crearon, y con que motivo se intento.';

comment on column asistente.messages.llamadas_modelo is
    'Cuantas veces se hablo con el modelo para producir ESTA respuesta. Junto con tokens_entrada son las dos palancas sobre la latencia: un turno lento lo es por un prompt grande o por muchas idas al modelo, y sin este numero no se distinguen. NULL en todo lo anterior al 08/09/2026.';
