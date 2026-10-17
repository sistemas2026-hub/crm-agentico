-- =============================================================================
--  Conversaciones: enlace al caso/ticket real y etiqueta automatica
-- =============================================================================
--
--  Referencia BLANDA a proposito: 'asistente' nunca declara un FK real hacia
--  una tabla que Django migra (la unica excepcion ya aceptada es
--  organization_id -> public.organization, y esa es de solo lectura). El caso
--  vive en django-crm (Case, tabla 'case'), creado via su API REST con un
--  Personal Access Token -- no una escritura directa de este esquema en esa
--  tabla. Guardar el uuid que la API devolvio alcanza para poder ir a
--  buscarlo despues; una FK ahi ataria una migracion de Django a este schema.
--
--  'etiqueta' es la categoria que el modelo eligio, de
--  tenant_config.conversaciones.etiquetas -- nunca fuera de esa lista (el
--  modulo que la asigna la fuerza por function-calling con un enum).

alter table asistente.conversations
  add column if not exists caso_id uuid,
  add column if not exists etiqueta text;
