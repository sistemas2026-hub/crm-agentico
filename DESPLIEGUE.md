# Despliegue

> Agosto 2026. Complementa [ARQUITECTURA.md](ARQUITECTURA.md), que explica **cómo se organiza** el código; esto es **cómo se pone a andar** y qué falla por el camino.

## Dónde vive cada cosa

Un solo VPS (`86.48.18.185`) gestionado con **Dokploy**, con varios proyectos que no se conocen entre sí:

| Stack | Qué es | Lo usa |
|---|---|---|
| `supabase-515b-*` | Supabase viejo, Postgres 15 | El proyecto **isp-reports**. No es nuestro; no se toca |
| `automatizacion-rp-supabase-dgimpk-*` | Supabase nuevo, Postgres 17 | **Este** proyecto: CRM y asistente |
| `crm-agentico-*` | La plataforma (este repo) | — |

De Supabase esta plataforma usa **solo Postgres**. Ni Kong, ni GoTrue, ni Storage, ni Realtime: el CRM tiene su propia autenticación en Django y el motor habla a la base con psycopg. Si algún día pesa la complejidad operativa, esa es la pregunta a hacerse.

## Procedimiento

### 1. Antes de nada: swap

El servidor tiene 11 GB y **cero swap**. Sin swap el kernel no degrada, mata — y elige por su heurística, no por importancia. Compilar el frontend con Node es justo el momento de mayor consumo.

```
fallocate -l 4G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' >> /etc/sysctl.conf
```

`swappiness=10` hace que solo se use bajo presión real: es red de seguridad, no memoria de trabajo.

### 2. El servicio en Dokploy

**Create Service → Compose** (no *Application*: eso es para un solo contenedor).

| Campo | Valor |
|---|---|
| Repository | `sistemas2026-hub/crm-agentico` |
| Branch | `fix/integracion-wisphub` |
| Compose Path | `./docker-compose.prod.yml` |
| Trigger Type | Manual mientras esto se estabiliza — ver abajo |

⚠️ **El Compose Path importa.** `docker-compose.yml` es el de desarrollo: trae un Postgres local y publica el 5432, que en el VPS ya ocupa el pooler del Supabase viejo. Desplegar ese da `address already in use`.

⚠️ **Sobre "On Push".** Esa rama la comparten dos personas. Con el disparador automático, un commit de cualquiera redespliega producción sin que nadie lo decida, compilando en un servidor con poca memoria. Con despliegue manual eso lo decide quien mira.

### 3. Variables

Van en la sección **Environment** del servicio. Quince son obligatorias; el despliegue se detiene nombrando la que falte, antes de construir nada. Péguelas todas de una vez — Compose se para en la primera.

```
DBHOST=crm.rapilinksas.co
DBPORT=5433
DBNAME=postgres
DBUSER=postgres.<tenant-id-del-pooler>
DBPASSWORD=

SECRET_KEY=

ALLOWED_HOSTS=agent-api.rapilinksas.co
DOMAIN_NAME=https://agent-api.rapilinksas.co
PUBLIC_DJANGO_API_URL=https://agent-api.rapilinksas.co
CORS_ALLOWED_ORIGINS=https://agent.rapilinksas.co
CSRF_TRUSTED_ORIGINS=https://agent.rapilinksas.co,https://agent-api.rapilinksas.co
FRONTEND_URL=https://agent.rapilinksas.co

ADMIN_EMAIL=
ADMIN_PASSWORD=

WISPHUB_API_KEY=
WISPHUB_BASE_URL=https://api.wisphub.io
WISPHUB_MODO_REAL=true
DEEPSEEK_API_KEY=

DEFAULT_FROM_EMAIL=noreply@rapilinksas.co
```

Los valores vacíos salen del `.env` local, salvo `SECRET_KEY`, que se genera nuevo y **nunca** se reutiliza el de desarrollo:

```
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

El patrón que más confunde: todas miran al **backend** excepto `CORS_ALLOWED_ORIGINS`, que mira al **frontend** — es la lista de quién tiene permiso de llamarlo. Y `ALLOWED_HOSTS` va sin `https://`; las demás con él.

### 4. Dominios

| Dominio | Servicio | Puerto |
|---|---|---|
| `agent.rapilinksas.co` | `frontend` | **3000** |
| `agent-api.rapilinksas.co` | `backend` | 8000 |

`motor`, `ollama` y `redis` **no llevan dominio**. El frontend alcanza al motor por la red interna (`http://motor:5000`); exponerlo sería abrir el asistente a internet sin autenticación.

El puerto del frontend es 3000, no 5173: con el build de producción manda adapter-node. El 5173 es del servidor de Vite, que quedó solo en desarrollo.

Ambos dominios necesitan DNS apuntando al servidor **antes** de desplegar, o Traefik no puede emitir certificado:

```
dig +short agent.rapilinksas.co agent-api.rapilinksas.co
```

### 5. Después del primer despliegue

```
docker ps | grep ollama
docker exec -it <contenedor-ollama> ollama pull bge-m3
```

Una sola vez: queda en el volumen `ollama_models` y sobrevive a los redespliegues.

Y **recargar el corpus contra ese Ollama** — ver la primera entrada de pendientes, porque no es opcional.

## Pendientes

Cosas sabidas que faltan. Cada una dice por qué importa, que es lo que no se deduce del código.

**Recargar el corpus con el Ollama del servidor.** Los 106 fragmentos actuales se vectorizaron con el `bge-m3` de una máquina de desarrollo. Si la versión del modelo que baja el contenedor no es idéntica, los vectores dejan de ser comparables con los de las consultas — y esto **no da error**: simplemente empieza a devolver fragmentos peores. Es la clase de degradación que nadie nota hasta que alguien dice que "el asistente ya no responde bien". `py -3.13 cli/cargar_corpus.py rapilink --forzar` con `OLLAMA_HOST` apuntando al servidor.

**Limpiar el esquema `asistente` de la base de isp-reports.** Una corrida temprana lo creó ahí con 106 fragmentos, cuando todavía se creía que el asistente viviría dentro de esa base. Está aislado en su propio esquema y no estorba, pero es contaminación de un proyecto en otro. `drop schema asistente cascade` contra `supabase-515b-db` no deja rastro — el esquema se diseñó para eso.

**Cerrar los puertos de Postgres expuestos.** Hoy `5432`, `6543`, `5433` y `6544` escuchan en la IP pública, protegidos solo por contraseña. Una vez que el CRM y el motor corran dentro del servidor, nadie externo los necesita. Para acceso administrativo desde fuera, túnel SSH en vez de puerto abierto:

```
ssh -L 5434:<ip-del-contenedor-db>:5432 root@86.48.18.185
```

**Un rol `crm_user` para Django.** Hoy el CRM se conecta como `postgres`, que tiene `BYPASSRLS` — las políticas de aislamiento no se evalúan. Con una sola organización no hay consecuencia visible, y por eso es fácil de olvidar. El motor ya baja a `app_backend` (ver `nucleo/persistencia/db.py`); el CRM todavía no.

**El webhook de WhatsApp.** `nucleo/canales/api.py` expone `/chat`, `/agentes` y `/salud`. No hay ruta de entrada para WhatsApp, y cuando la haya necesita dominio público por Traefik.

**El 502 de `crm.rapilinksas.co`.** Ese dominio tiene ruta en Traefik apuntando a algo que no responde. No afecta a la base —el pooler escucha en TCP directo, sin pasar por Traefik— pero quien espere llegar al Studio de Supabase por ahí, hoy no puede.

**Variables muertas en `.env`.** `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` no las usa nadie en este repositorio. Probablemente son residuo del proyecto de reportes. Confunden más de lo que ayudan.

## Diagnóstico

Errores que ya costaron tiempo una vez.

**`FATAL: Tenant or user not found`** — No es la contraseña ni el tenant. Casi seguro estás hablando con el pooler **equivocado**: hay dos Supabase en el servidor y durante mucho tiempo solo el viejo publicaba puertos al host. Verifica a cuál llegas antes de tocar credenciales:

```
docker ps --format "{{.Ports}}\t{{.Names}}" | grep supavisor
```

Si el contenedor nuevo muestra `5432/tcp` sin `0.0.0.0:`, no es alcanzable desde fuera y todo lo que llegue a ese puerto lo atiende el viejo.

**`(ECIRCUITBREAKER) failed to retrieve database credentials`** — El cortacircuitos de Supavisor. Tras varios fallos bloquea conexiones nuevas por un rato, **y cada reintento lo mantiene activado**. Deja de reintentar y espera, o reinicia el contenedor del pooler. Es fácil confundirlo con un problema de credenciales y salir a borrar el registro del tenant, que estaba bien.

**`(ENOIDENTIFIER) no tenant identifier provided`** — Falta el sufijo en el usuario. Supavisor exige `postgres.<tenant_id>`, no `postgres` a secas.

**`strconv.ParseUint: parsing "5433:5432": invalid syntax`** — Un mapeo `host:contenedor` puesto bajo `expose:` en vez de `ports:`. `expose:` solo acepta números sueltos y no publica nada; es `ports:` el que publica.

**`external volume "..." not found`** — El compose de desarrollo declara un volumen externo que no existe en esa máquina. `docker volume create <nombre>`.

**La interfaz carga pero ninguna llamada funciona** — CORS. El valor por defecto de `CORS_ALLOWED_ORIGINS` es `http://localhost:5173`, así que sin definirlo el despliegue arranca bien y falla en cada clic. El error en la consola del navegador habla de CORS y no menciona la variable.

**"Correo o contraseña incorrectos" con credenciales correctas** — Ese texto es el **valor por defecto** del frontend (`login/+page.server.js`), no una respuesta del backend: aparece ante cualquier fallo de la petición. La causa real suele estar en los logs del backend. Ya pasó una vez con `DisallowedHost`: el frontend llama a Django por la red interna (`http://backend:8000`), así que las peticiones llegan con `Host: backend:8000` y `ALLOWED_HOSTS` tiene que incluir `backend` además del dominio público. Ante este mensaje, mirar siempre:

```
docker logs <contenedor-backend> --tail 20
```

**El backend no arranca y habla del `SECRET_KEY`** — Con `ENV_TYPE=prod`, Django rechaza cualquier clave que empiece por `django-insecure` y exige mínimo 32 bytes, porque esa clave firma todos los JWT. Es deliberado: falla el despliegue en vez de firmar tokens débiles.

**`Permission denied ... 403` al hacer push** — Credenciales de GitHub, no del repositorio. Suele aparecer después de tocar la instalación de la GitHub App de Dokploy.
