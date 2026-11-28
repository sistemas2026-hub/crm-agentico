-- =============================================================================
--  ETIQUETAS DEL EQUIPO  -  las que pone una persona a un chat, varias y con color
-- =============================================================================
--
--  Por que existe (11/11/2026)
--  ---------------------------
--  El equipo marca los chats como en WhatsApp Business: «Cliente VIP»,
--  «Moroso», «Pide visita». No es la 'etiqueta' de la conversacion: esa la
--  elige el MODELO al escalar, de una taxonomia cerrada
--  (TenantConfig.conversaciones.etiquetas), y alimenta metricas y derivacion.
--  Estas las pone una persona, son varias por chat, y no deciden nada en el
--  motor: ordenan el trabajo del equipo y se filtran en la cola.
--
--  EL CATALOGO VIVE EN LA CONFIGURACION; LA ASIGNACION, ACA
--  -------------------------------------------------------
--  Que etiquetas existen, su nombre y su color, es de cada empresa y se edita
--  desde /settings/bandeja (Conversaciones.etiquetas_del_equipo, nucleo/config/
--  schema.py). Esta tabla guarda solo QUE CLAVES tiene cada chat. El motor
--  rechaza una clave que no este en el catalogo (fail-closed, 400) antes de
--  escribir, asi que lo que entra aca siempre existio.
--
--  Una clave que despues se BORRA del catalogo no se borra de aca: la lectura
--  la filtra y no se muestra. Borrarla de todas las filas seria una escritura
--  masiva disparada por un formulario de ajustes, y volver a crear la etiqueta
--  con la misma clave la devuelve a los chats que la tenian.
--
--  POR CHAT, NO POR CONVERSACION
--  -----------------------------
--  La clave es (empresa, canal, usuario_externo): el mismo chat que agrupa la
--  Bandeja (nucleo/relevo/proyeccion.py::agrupar_por_numero). Una conversacion
--  cerrada no se reabre, y lo siguiente que escribe ese numero abre otra; si
--  la etiqueta fuera de la conversacion, «Cliente VIP» se perderia cada vez
--  que el cliente vuelve, que es justo cuando hace falta verla.
--
--  UNA FILA POR CHAT, CON EL ARREGLO DE CLAVES
--  -------------------------------------------
--  La cola se pide cada 8 s y su costo esta medido por subconsulta (ver
--  db.ultima_actividad). Con una fila por chat, la cola la trae con un JOIN
--  por clave primaria, sin subconsulta ni agregacion por conversacion.
--  'cambiada_por_*' y 'cambiada_en' dicen quien y cuando la toco por ultima
--  vez, que es lo que se pidio; el historial completo de cada cambio no.
--
--  COMO SE REVIERTE
--  ----------------
--      drop table if exists asistente.etiquetas_de_chat;
--
--  Igual que 202611111200: la cola la lee (db.ultima_actividad), asi que
--  revertir exige revertir antes el codigo.
-- =============================================================================

set local lock_timeout = '3s';
set local statement_timeout = '60s';

create table if not exists asistente.etiquetas_de_chat (
    organization_id         uuid not null,
    canal                   text not null,
    -- El numero (o el identificador del canal). Vacio no es un chat: la
    -- Bandeja no agrupa nada con un usuario_externo vacio, y aca tampoco.
    usuario_externo         text not null check (usuario_externo <> ''),

    -- Las claves del catalogo de la empresa. Vacio = sin etiquetas: se guarda
    -- la fila igual, para no perder quien las saco y cuando. El tope es una
    -- red: el esquema de la config ya acota el catalogo.
    claves                  text[] not null default '{}'
                            check (cardinality(claves) <= 50),

    -- Quien y cuando las cambio por ultima vez. El id sale de la sesion
    -- autenticada del CRM (el mismo 'autor_usuario_id' de los mensajes de
    -- persona), nunca del navegador.
    cambiada_por_usuario_id uuid,
    cambiada_por_nombre     text,
    cambiada_en             timestamptz not null default now(),

    primary key (organization_id, canal, usuario_externo)
);

-- EL AISLAMIENTO, con el patron de 202611101201_ejecuciones.sql.
--
-- 'force' no es decorativo: sin el, el DUEÑO de la tabla se saltea la politica.
-- 'postgres' y 'motor_user' tienen BYPASSRLS, asi que lo que de verdad aisla es
-- 'set local role app_backend' + 'set local app.current_tenant'. La politica es
-- la red que convierte un olvido en CERO filas en vez de en TODAS.
alter table asistente.etiquetas_de_chat enable row level security;
alter table asistente.etiquetas_de_chat force row level security;

grant select, insert, update, delete on asistente.etiquetas_de_chat to app_backend;

drop policy if exists tenant_aislado on asistente.etiquetas_de_chat;
create policy tenant_aislado on asistente.etiquetas_de_chat
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
