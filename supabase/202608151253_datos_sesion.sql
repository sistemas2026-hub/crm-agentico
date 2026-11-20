-- =============================================================================
--  17. Los datos capturados al verificar sobreviven a un reinicio del motor
-- =============================================================================
--  'id_cliente' y 'nombre_cliente' ya se persistian (ver 14), pero la
--  verificacion captura MAS cosas de la ficha del cliente: hoy el serial de
--  su equipo de fibra y la interfaz de red. Esas vivian solo en memoria del
--  proceso.
--
--  Consecuencia, vista en produccion el 15/08/2026: despues de cualquier
--  reinicio del motor, una conversacion abierta se rehidrataba VERIFICADA
--  pero sin esos datos, y todas las herramientas que dependen de ellos
--  fallaban con "endpoint sin resolver". El cliente recibia un diagnostico a
--  ciegas -- se le pedia reiniciar el router a mano porque el agente nunca
--  llego a ver el estado ni la señal de su equipo. No habia error visible:
--  la guarda fallaba cerrado y el modelo seguia con el camino alternativo.
--
--  Se guarda como JSONB y no como columnas: QUE se captura al verificar es
--  decision del tenant (su catalogo de herramientas), no del motor. Una
--  columna 'sn_onu' meteria en el esquema el vocabulario de un ISP de fibra
--  -- el proximo tenant puede capturar otra cosa. Ver
--  Sesion.CAMPOS_PERSISTIBLES en nucleo/seguridad/verificacion.py.
-- =============================================================================

alter table asistente.conversations
  add column if not exists datos_sesion jsonb not null default '{}'::jsonb;

comment on column asistente.conversations.datos_sesion is
  'Datos capturados al verificar la identidad, mas alla de id_cliente/nombre '
  '(ej. el serial de la ONU). Se restauran al rehidratar la conversacion tras '
  'un reinicio del motor. Nunca credenciales: lo que entra aca es lo que '
  'declara Sesion.CAMPOS_PERSISTIBLES.';
