-- =============================================================================
--  ESCALAR A UN AREA (T22) Y EL VENCIMIENTO DEL «EN ESPERA» (C22)
-- =============================================================================
--
--  Por que existe (30/10/2026)
--  ---------------------------
--  Contrato del relevo v3.3 (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, C21 y C22).
--
--  T22: un operador que valido y no pudo resolver escala la conversacion a un
--  AREA de la empresa (no a una persona: eso sigue siendo T4, de ADMIN). Queda
--  sin dueño y marcada para esa area, con la nota de lo que se valido. Hasta
--  hoy solo existia Soltar, sin motivo ni destino.
--
--  C22: el pendiente interno («queda en espera», opcion de T5) puede tener
--  una hora; pasada, la fila sube a la banda 1 y vuelve sola al primer lugar.
--
--  QUE NO CAMBIA
--  -------------
--  Ninguna fila existente. Cuatro columnas nullable nuevas y un tipo de evento
--  mas en el CHECK. Las RLS de asistente.conversations y relevo_eventos ya
--  cubren las columnas nuevas.
--
--  SIN DATOS DEL CLIENTE en las columnas nuevas mas alla de lo que escribe el
--  operador en la nota, igual que 'pendiente_interno_nota'.
-- =============================================================================

alter table asistente.conversations
  add column if not exists pendiente_interno_hasta timestamptz,
  add column if not exists area_destino            text,
  add column if not exists area_destino_nota       text,
  add column if not exists area_destino_en         timestamptz;

comment on column asistente.conversations.pendiente_interno_hasta is
  'Hasta cuando se espera (C22). Vencido, la fila sube a la banda 1. Se borra con el pendiente.';
comment on column asistente.conversations.area_destino is
  'Area de TenantConfig.areas a la que se escalo (T22). Se borra al cerrar o con otro T22.';

alter table asistente.relevo_eventos
  drop constraint if exists relevo_eventos_tipo_check;
alter table asistente.relevo_eventos
  add constraint relevo_eventos_tipo_check check (tipo in (
    'escalada', 'intervencion', 'devolucion_solicitada', 'devuelta_a_ia',
    'devolucion_fallida', 'caso_externo_cerrado',
    'tomada', 'soltada', 'reasignada', 'escalada_a_area',
    'pendiente_interno_abierto', 'pendiente_interno_cerrado',
    'evaluacion_revisada',
    'accion_propuesta_duplicada', 'accion_aprobada', 'accion_rechazada',
    'accion_vencida', 'accion_cancelada', 'accion_desconocida',
    'cerrada', 'desenlace_completado'));
