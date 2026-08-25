-- =============================================================================
--  19. Identidad del colaborador en asistente.tool_calls
-- =============================================================================
--  tool_calls ya guardaba 'rol_solicitante' (el area/rol, fusionado si el
--  colaborador tiene varios agentes asignados), pero no de QUIEN. Para
--  flujos disparados desde la app web (/asistente, /configuracion-guiada)
--  la identidad real del colaborador SI existe -- viaja como
--  'identificador_sesion' y ya queda en conversations.usuario_externo -- pero
--  saber que colaborador ejecuto una herramienta puntual exigia cruzar
--  tool_calls.conversation_id contra esa columna. Esta migracion lo deja como
--  columna propia, sin depender del cruce.
--
--  Nullable a proposito: los canales que atienden clientes finales (WhatsApp)
--  no tienen profile_id -- ahi la identidad relevante es el cliente
--  (usuario_externo), no un colaborador del CRM.
-- =============================================================================

alter table asistente.tool_calls
  add column if not exists profile_id uuid;

comment on column asistente.tool_calls.profile_id is
  'Perfil del CRM (public.profile) del colaborador que disparo la llamada, '
  'cuando el turno vino de POST /chat con profile_id (app web). Null en '
  'turnos de canales orientados a cliente final (WhatsApp), donde no hay un '
  'colaborador identificado -- ahi la identidad es la conversacion misma '
  '(usuario_externo).';

create index if not exists tool_calls_profile_idx
  on asistente.tool_calls (organization_id, profile_id, creado_en desc)
  where profile_id is not null;
