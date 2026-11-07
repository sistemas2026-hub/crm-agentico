-- =============================================================================
--  SECRETOS POR TENANT  -  para que cada empresa traiga sus propias credenciales
-- =============================================================================
--
--  Por que existe
--  --------------
--  Hasta aca, 'auth_ref' (tenant_config.config) guardaba el NOMBRE de una
--  credencial y nucleo/herramientas/http.py la resolvia contra os.environ. Eso
--  alcanza mientras haya un tenant: el proceso tiene una sola tanda de
--  variables de entorno.
--
--  Deja de alcanzar en cuanto entran dos ISPs. Cada uno tiene su propia cuenta
--  de WhatsApp Business (su token, su app secret) y su propia clave de WispHub.
--  Con una sola tanda por proceso habria que levantar un motor por empresa, que
--  es justo lo que la arquitectura multi-tenant existe para evitar.
--
--  Y es el requisito de fondo de que el cliente cargue sus datos desde la
--  plataforma: una pantalla de ajustes no puede escribir en el .env del
--  servidor.
--
--  EL VALOR VA CIFRADO, NO EN CLARO
--  --------------------------------
--  A diferencia del contenido de las conversaciones (que SI va en claro por
--  decision explicita del PRD RNF-01, con la autorizacion de tratamiento como
--  base legal), un token de Meta no es un dato personal: es una llave. Quien lo
--  lee puede escribirle a los clientes de la empresa haciendose pasar por ella.
--
--  El cifrado es simetrico (Fernet) con una clave maestra que vive en el
--  entorno del servidor -- ver nucleo/seguridad/secretos.py. No protege contra
--  quien tenga a la vez la base Y el entorno del motor; si protege contra un
--  volcado de la base, una copia de seguridad filtrada, o alguien con el rol
--  'postgres' (que tiene BYPASSRLS -- ver ARQUITECTURA.md) mirando tablas.
--
--  Esa clave maestra queda como la UNICA credencial que sigue en el .env.
--  Perderla obliga a recargar todos los secretos a mano: no hay forma de
--  recuperar los valores sin ella, y esa es exactamente la propiedad buscada.
-- =============================================================================

create table if not exists asistente.tenant_secrets (
  organization_id uuid not null references public.organization(id) on delete cascade,
  -- El mismo nombre que la configuracion referencia en 'auth_ref',
  -- 'token_ref', 'app_secret_ref'... (ej. 'WHATSAPP_TOKEN'). Se valida con la
  -- forma de una variable de entorno para que el dia que un secreto vuelva al
  -- .env no haya que traducir nada: el nombre es el mismo en los dos lados.
  nombre          text not null
                  check (nombre ~ '^[A-Z][A-Z0-9_]*$'),
  -- Fernet: 'gAAAAA...'. NUNCA el valor en claro. Ver el encabezado.
  valor_cifrado   text not null,
  -- Para saber que es sin exponerlo: 'Token permanente de la app de Meta'.
  descripcion     text,
  -- Los ultimos 4 caracteres del valor en claro. Sirve para que la pantalla de
  -- ajustes pueda mostrar "...a3f9" y el operador confirme que cargo el token
  -- correcto sin que la interfaz tenga que descifrar ni mostrar el secreto.
  pista           text,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now(),
  primary key (organization_id, nombre)
);

comment on table asistente.tenant_secrets is
  'Credenciales por empresa, cifradas con la clave maestra del entorno del '
  'motor. Es el "Vault" que menciona el comentario de tenant_config.config: '
  'la configuracion guarda el NOMBRE, el valor vive aqui.';


-- -----------------------------------------------------------------------------
--  RLS  -  misma politica unica que el resto del esquema
-- -----------------------------------------------------------------------------
--  Sin esto, un motor que se olvide de fijar app.current_tenant leeria los
--  tokens de todas las empresas. Con esto, no lee ninguno: falla cerrado.

alter table asistente.tenant_secrets enable row level security;
alter table asistente.tenant_secrets force row level security;
grant select, insert, update, delete on asistente.tenant_secrets to app_backend;

drop policy if exists tenant_aislado on asistente.tenant_secrets;
create policy tenant_aislado on asistente.tenant_secrets
  for all to app_backend
  using (organization_id = asistente.org_actual())
  with check (organization_id = asistente.org_actual());
