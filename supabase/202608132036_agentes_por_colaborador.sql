-- =============================================================================
--  AGENTES POR COLABORADOR  -  que agentes puede usar cada empleado
-- =============================================================================
--
--  Por que existe
--  ---------------
--  asistente.tenant_users ya tenia las columnas necesarias desde 01_schema.sql
--  (profile_id -> el perfil del CRM, rol -> el nombre del agente), pero nunca
--  se poblo ni se leyo: /asistente estaba FIJO en el rol 'soporte'
--  (django-crm/frontend/src/routes/api/asistente/+server.js), asi que
--  'facturacion' y 'administracion' quedaban configurados y sin forma de
--  usarlos. Un colaborador que preguntaba por una factura le hablaba a un
--  agente sin consultar_facturas.
--
--  Ahora un ADMIN asigna agentes por persona desde la plataforma, y el motor
--  arma la union de lo que esa persona tenga permitido.
--
--  POR QUE HACE FALTA ESTE INDICE
--  -------------------------------
--  El unico UNIQUE de la tabla es (organization_id, canal, canal_identidad),
--  pensado para un cliente final de WhatsApp. Un colaborador interno no tiene
--  canal ni identidad de canal: esas dos columnas van en NULL. Y en Postgres
--  dos NULL NO se consideran iguales, asi que ese UNIQUE no impide nada aqui
--  -- se podrian insertar diez filas identicas asignandole 'soporte' a la
--  misma persona.
--
--  El indice es PARCIAL ('where profile_id is not null') a proposito: aplica
--  solo a las asignaciones de colaboradores, sin tocar las filas de clientes
--  finales, que son las que ese otro UNIQUE ya cubre.
-- =============================================================================

create unique index if not exists tenant_users_agente_por_persona_idx
  on asistente.tenant_users (organization_id, profile_id, rol)
  where profile_id is not null;

comment on column asistente.tenant_users.rol is
  'Para un colaborador (profile_id no nulo): el nombre de UN agente que esa '
  'persona puede usar, tal cual figura en tenant_config.roles. Una fila por '
  'agente asignado -- alguien con Soporte y Facturacion tiene dos filas, y el '
  'motor le arma la union de ambos. Sin ninguna fila no accede a nada '
  '(fail-closed). Para un cliente final es el rol con el que se le atiende.';
