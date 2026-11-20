alter table asistente.conversations
  add column if not exists necesita_atencion_humana boolean not null default true;

comment on column asistente.conversations.necesita_atencion_humana is
  'Si esta escalada, si ademas hace falta que alguien del equipo la '
  'atienda ahora (vs. un caso que se paso a registro/otro flujo sin '
  'necesitar atencion inmediata). Independiente de escalada_a_humano: '
  'una conversacion puede escalar sin necesitar atencion humana urgente. '
  'Default true preserva el comportamiento actual para filas existentes.';
