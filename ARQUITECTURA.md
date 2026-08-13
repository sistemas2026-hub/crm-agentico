# Estructura del proyecto

> Entregable 3 de 9. Agosto 2026.

## La única regla

El proyecto se parte en dos zonas, y toda la arquitectura depende de que no se mezclen:

| Zona | Qué es | Puede conocer un cliente |
|---|---|---|
| `nucleo/` | El motor | **Nunca** |
| `tenants/` | Configuración por empresa | Es su razón de existir |

Dar de alta un ISP nuevo es: fila en `tenants` (tabla), archivo en `tenants/` (carpeta), cargar sus documentos. **Cero cambios en `nucleo/`.**

Si al escribir código en el núcleo aparece la necesidad de distinguir un cliente, no se resuelve con un `if`: significa que **falta un campo en la configuración**.

### Y no depende de que alguien se acuerde

```
py -3.13 tests/test_nucleo_sin_tenants.py
```

Lee los slugs de `tenants/*.yaml` y falla si alguno aparece bajo `nucleo/`. También caza las formas de colar lógica por cliente sin nombrarlo: ramas por tenant, comparaciones contra slug literal, URLs de servicios concretos embebidas.

Ignora comentarios y docstrings —documentar por qué existe una regla no es violarla— pero **no** las cadenas dentro del código, que es justamente donde se escondería un slug.

Cuando falla, no se agrega una excepción. Se mueve el comportamiento a la configuración.

## Mapa

```
nucleo/                    EL MOTOR — genérico, sin clientes
  config/                  carga y validación de tenant.config.yaml
  seguridad/               listas blancas, permisos por rol, autenticación
  herramientas/            tipos genéricos: http · agregado · sql · batch
  ingesta/                 fragmentación, contextualización, versionado
  recuperacion/            búsqueda híbrida, ensamblado del prompt
  modelo/                  cliente LLM, selección por canal/rol
  canales/                 whatsapp, web
  persistencia/            repositorios sobre Supabase
  observabilidad/          auditoría, consumo, Langfuse

tenants/                   DATOS por empresa — sin código
  tenant.config.example.yaml    plantilla de alta
  rapilink.config.yaml          primer despliegue

supabase/                  migraciones SQL
cli/                       utilidades operativas
evaluacion/                sets dorados por tenant
tests/                     incluye la guarda del núcleo

django-crm/                LA PLATAFORMA — CRM (BottleCRM/Django-CRM)
  backend/                 Django + DRF
  frontend/                SvelteKit — incluye /agentes, /asistente,
                            /simulador-whatsapp (hablan con nucleo/canales/api.py)
```

**`tenants/` no contiene código a propósito.** El validador vive en `nucleo/config/schema.py`: la configuración es dato, y lo que la interpreta es motor.

### `django-crm/`

Es el proyecto [Django-CRM/Django-CRM](https://github.com/Django-CRM/Django-CRM) (BottleCRM), **vendorizado sin su historial de git** — se copió el estado del código, no se clonó ni se agregó como submódulo. Motivo: unificar todo en un solo repo (`sistemas2026-hub/crm-agentico`) para que cloná-y-arrancá alcance con un solo `docker compose up`, sin manejar dos remotos.

Costo de esa decisión: **actualizar del proyecto original a futuro es manual** (no hay `git pull` que traiga cambios de upstream — hay que copiar lo que corresponda a mano). A cambio, no se carga el historial de miles de commits ajenos dentro de este repo.

Sigue siendo, en espíritu, la misma separación núcleo/tenant: `django-crm/` es la plataforma (genérica, de terceros), y lo que le agregamos encima para hablarle al motor (`frontend/src/routes/(app)/agentes/`, `/asistente/`, `/simulador-whatsapp/`, y sus proxies en `frontend/src/routes/api/`) es la integración específica de este producto — no se tocó el resto del CRM.

`docker-compose.yml` (en la raíz) levanta todo junto: `db`, `redis`, `backend`, `celery-worker`, `celery-beat`, `frontend` (de `django-crm/`) y `motor` (`nucleo/`), en la misma red — el frontend le habla al motor por `http://motor:5000`, igual que le habla a Postgres por `db:5432`.

Los embeddings del corpus (`nucleo/recuperacion/embeddings.py`) van a la API de OpenAI (`text-embedding-3-large`), no a un modelo local: hasta agosto 2026 corría un contenedor `ollama` aparte con `bge-m3` (~2-3 GB de RAM) solo para esto, pero el VPS no tenía recursos de sobra para sostenerlo junto con todo lo demás, y era su único consumidor — los cinco roles de chat ya estaban redirigidos a `deepseek-v4-flash`. Tampoco se puede resolver con DeepSeek — su API expone `/models` y `/chat/completions`, pero `/embeddings` devuelve 404 (verificado); un modelo de chat no produce vectores. El motor requiere `OPENAI_API_KEY` en el entorno.

## Dónde aterriza lo que ya existía

El sistema actual se **absorbe**, no se rescribe. Casi todo era ya configuración disfrazada de código:

| Hoy | Destino | Naturaleza |
|---|---|---|
| `AGREGACIONES` (filtros verificados) | `tenants/rapilink.config.yaml` | ✅ ya portado |
| Listas blancas por área | `roles.*.campos_permitidos` | ✅ ya portado |
| `AREAS` (4 roles) | `roles` | ✅ ya portado |
| Motor de agregación | `nucleo/herramientas/agregado.py` | Código genérico |
| `filtrar_campos()` | `nucleo/seguridad/listas_blancas.py` | Código genérico |
| `registrar_auditoria()` | `nucleo/observabilidad/auditoria.py` | Código genérico |
| `construir_system()` | `nucleo/recuperacion/prompt.py` | Código genérico |
| `cli/banco_pruebas.py` | semilla de `evaluacion/` | Casos → tabla |
| `cli/informe_materiales.py` | herramienta tipo `batch` | Ya declarada en config |

`soporte_wisphub.py` sigue funcionando mientras tanto. La migración es incremental: cada pieza que se mueve al núcleo se valida contra el banco de pruebas antes de retirar la anterior.

## Variables de entorno

Ninguna vive en los YAML. La configuración solo guarda **nombres** (`auth_ref: WISPHUB_API_KEY`); el validador rechaza el archivo si detecta un valor con pinta de credencial.

```
WISPHUB_API_KEY            clave del ISP
WISPHUB_BASE_URL
WISPHUB_MODO_REAL

VITE_SUPABASE_URL          proyecto
VITE_SUPABASE_ANON_KEY     pública por diseño — protegida por RLS
SUPABASE_SERVICE_ROLE_KEY  ⚠️  solo migraciones (ver abajo)

DATABASE_URL               conexión al Postgres del Supabase propio
POSTGRES_PASSWORD          la usa DATABASE_URL; separada para poder rearmarla
POOLER_TENANT_ID           lo exige Supavisor en el usuario: postgres.<id>
```

`django-crm/.env.docker.local` (ignorado por git) apunta Django al mismo Postgres, sobreescribiendo el bloque de base de datos de `.env.docker`. El servicio `db` del compose sigue existiendo pero ya no se usa.

### ⚠️ `BYPASSRLS` no es solo de `SUPABASE_SERVICE_ROLE_KEY`

Ese rol tiene `BYPASSRLS`: **las políticas de aislamiento no se evalúan para él**. Comprobado en la prueba del esquema — como superusuario se ven los datos de todos los tenants.

**Y el rol `postgres` de esta instalación también lo tiene.** Verificado contra la base: `select rolbypassrls from pg_roles where rolname='postgres'` devuelve `true`. Como `DATABASE_URL` conecta justamente como `postgres`, cualquier consulta que se quede en ese rol ve los datos de todas las organizaciones sin que nada lo impida.

Por eso `DATABASE_URL` tiene **dos usos que no hay que confundir**:

| Uso | Rol efectivo | Quién |
|---|---|---|
| Operación: migraciones, carga de configuración y corpus | `postgres` | `cli/`, `supabase/01_schema.sql` |
| Servir peticiones | `app_backend` | `nucleo/persistencia/db.py` |

El motor abre transacción, hace `set local role app_backend` y fija `set local app.current_tenant` en cada operación — ver el encabezado de `nucleo/persistencia/db.py`. Ambos `local`, para que una petición no herede el tenant de otra al reutilizarse la conexión.

Medido sobre `asistente.conversations` con una fila cargada:

| Conexión | Filas visibles |
|---|---|
| `postgres` (BYPASSRLS), sin fijar tenant | 1 |
| `app_backend` + tenant correcto | 1 |
| `app_backend` + tenant de otra empresa | 0 |
| `app_backend` **sin** fijar tenant | 0 |

La última fila es la propiedad que importa: olvidar fijar el tenant no devuelve todo, devuelve nada. Falla cerrado.
