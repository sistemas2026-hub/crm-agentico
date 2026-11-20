-- =============================================================================
--  AUTOR DEL HISTORIAL DE CONFIG  -  quien hizo cada version
-- =============================================================================
--
--  Por que existe (13/11/2026)
--  ---------------------------
--  La pestaña "Cambios" de cada agente (/agentes/[nombre]) lista sus versiones
--  desde asistente.tenant_config_historial, que guarda la config COMPLETA y
--  CUANDO empezo a servir, pero no QUIEN la cambio. La pantalla tenia que
--  decir "quien hizo cada cambio no se registra todavia".
--
--  QUE GUARDA
--  ----------
--  El nombre (o el email, si el perfil no tiene nombre) de la persona que
--  edito, tal como lo arma el proxy del CRM desde la SESION autenticada --
--  nunca desde el navegador (django-crm/frontend/src/lib/server/v2/autor.js).
--  Lo escribe nucleo/config/editor.py::anotar_version, en la misma
--  transaccion que la config.
--
--  NULL es "no se sabe": las versiones anteriores a esta migracion, y las que
--  escribe un CLI o un proceso sin persona detras (cargar_config, la
--  configuracion guiada). Se muestra como "sin registro", no se inventa.
--
--  SE PUEDE APLICAR DESPUES DEL DEPLOY
--  -----------------------------------
--  anotar_version pregunta si la columna existe antes de nombrarla
--  (_hay_columna_autor): con el codigo nuevo y sin esta migracion, el
--  historial se sigue anotando como antes, sin autor. Por eso el orden no
--  importa.
--
--  Sin update ni delete: el historial sigue siendo de solo agregar
--  (202609080802_historial_de_config.sql). La columna nace NULL en todas las
--  filas existentes y no se completa: no hay de donde saberlo.
-- =============================================================================

alter table asistente.tenant_config_historial
  add column if not exists autor text;

comment on column asistente.tenant_config_historial.autor is
  'Quien hizo esta version (nombre o email de la sesion del CRM). NULL = no se '
  'sabe: anterior al 13/11/2026, o escrita por un CLI o un proceso sin persona.';
