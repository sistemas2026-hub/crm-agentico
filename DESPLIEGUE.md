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

## Desarrollo local contra la base real

Para probar un cambio sin pasar por Dokploy: `docker compose up` (el compose de **desarrollo**, no el de producción) ya puede apuntar el CRM y el motor al Supabase real del VPS en vez de al Postgres local del propio compose. No hace falta tocar código ni el compose — la traducción ya está armada, ver el comentario en el servicio `backend` de `docker-compose.yml`. Lo único que decide a cuál base se conecta es **el `.env` de la raíz**.

```
DBHOST=crm.rapilinksas.co
DBPORT=5433
DBNAME=postgres
DBUSER=postgres.<tenant-id-del-pooler>
DBPASSWORD=
```

Con esas cinco variables presentes en `.env`, `backend`, `celery-worker`, `celery-beat` y `motor` se conectan al Supabase real — Compose interpola `${DBHOST:-db}` desde ese archivo antes de levantar los contenedores. El servicio `db` del compose se sigue levantando (nadie lo quitó del `depends_on`) pero queda sin usar; es ruido, no un problema. Para volver a la base local, basta con comentar o borrar esas cinco líneas del `.env` — sin `DBHOST` en el entorno, el default `db` de cada servicio vuelve a mandar.

**Esto no es una copia. Es la base de producción**, la misma que atiende `agent-api.rapilinksas.co`. Antes de usarlo:

- **Las migraciones corren solas al arrancar** (`entrypoint.sh`, `python manage.py migrate --noinput`). Un cambio de esquema que no esté listo para producción no se prueba así — se aplica ahí mismo, en caliente, contra la base real. Tanto el motor como el backend imprimen un aviso cuando `DBHOST` no es local, para que esto no pase desapercibido.
- **`WISPHUB_MODO_REAL=true` en el `.env` de la raíz** significa que el motor llama a la API real de WispHub, no a datos simulados. Una herramienta de lectura no hace daño; `registrar_pago` sigue exigiendo confirmación humana, pero esa confirmación pasa a ser sobre un pago de verdad.
- **Dos personas trabajando así a la vez chocan.** Dos entornos locales corriendo migraciones o escribiendo conversaciones contra la misma base al mismo tiempo compiten por las mismas filas — ver la nota sobre colaboración en la rama compartida. Avisar antes de usarlo, no asumir que nadie más está.
- El backend se conecta como `postgres`, que tiene `BYPASSRLS` (ver ARQUITECTURA.md). Local o en el VPS, la separación por tenant no lo protege: ve todo.

**Si ya tenés Ollama nativo en la máquina** (el uso habitual del equipo de desarrollo, ver PRD.md 7.1.1 — `banco_pruebas.py` habla contra ese, no contra Docker), el servicio `ollama` del compose es un contenedor aparte con un volumen vacío: no ve los modelos que ya tenés instalados, y `docker compose up` los vuelve a bajar (~4-5 GB, imagen + `bge-m3`). Se evita apuntando `OLLAMA_HOST` al Ollama del host desde tu `.env`:

```
OLLAMA_HOST=http://host.docker.internal:11434
```

Y arrancando `motor` con `--no-deps`, para que no arrastre al contenedor `ollama` por el `depends_on`:

```
docker compose up -d --build backend celery-worker celery-beat frontend
docker compose up -d --build --no-deps motor
```

Verificar que tiene `bge-m3` antes: `curl localhost:11434/api/tags`. Sin override, el default sigue siendo el contenedor — a nadie más le cambia nada.

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

Van en la sección **Environment** del servicio. Dieciséis son obligatorias; el despliegue se detiene nombrando la que falte, antes de construir nada. Péguelas todas de una vez — Compose se para en la primera.

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

ASISTENTE_TENANT=rapilink

DEFAULT_FROM_EMAIL=noreply@rapilinksas.co
```

`ASISTENTE_TENANT` es el slug del `tenants/<slug>.config.yaml`, y es de quién habla el frontend cuando alguien abre `/agentes` o `/settings/asistente`. Se declara acá y no en el código porque es lo único que ata esa interfaz a una empresa concreta. La URL del motor no está en esta lista: la fija el compose (`http://motor:5000`), que es quien conoce el nombre del servicio.

Los valores vacíos salen del `.env` local, salvo `SECRET_KEY`, que se genera nuevo y **nunca** se reutiliza el de desarrollo:

```
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

El patrón que más confunde: todas miran al **backend** excepto `CORS_ALLOWED_ORIGINS`, que mira al **frontend** — es la lista de quién tiene permiso de llamarlo. Y `ALLOWED_HOSTS` va sin `https://`; las demás con él.

### 4. Dominios

**Uno por servicio.** Traefik enruta por nombre de host, así que dos servicios no pueden compartir dominio.

| Dominio | Servicio | Puerto |
|---|---|---|
| `agent.rapilinksas.co` | `frontend` | **3000** |
| `agent-api.rapilinksas.co` | `backend` | 8000 |

⚠️ **Después de crear o editar un dominio hay que redesplegar.** Dokploy escribe las etiquetas de Traefik al recrear los contenedores, no al guardar el formulario. Guardar y quedarse esperando es media hora perdida — y el síntoma es un 404 de Traefik que parece un problema de DNS.

⚠️ **Si sale `UNAUTHORIZED` en rojo al guardar**, es la sesión de Dokploy caducada, no la configuración. Recargar la página, volver a entrar, repetir.

**Cómo leer los errores de Traefik**, que es lo que más tiempo ahorra:

| Respuesta | Significa |
|---|---|
| `404 page not found` en texto plano, sin cabecera `Server` | Traefik no tiene ruta para ese host: falta el dominio, o falta redesplegar |
| `502 Bad Gateway` | Sí hay ruta, pero el destino no responde: contenedor caído, puerto equivocado, o el contenedor no comparte red con Traefik |
| Respuesta con `server: gunicorn` | Ya llegó a la aplicación; el problema, si lo hay, es de la aplicación |

Para saber qué contenedor reclama un dominio y en qué redes está:

```
docker ps --format '{{.Names}}' | while read c; do
  if docker inspect "$c" --format '{{json .Config.Labels}}' 2>/dev/null | grep -q 'TU-DOMINIO'; then
    echo "=== $c ==="
    docker inspect "$c" --format '{{json .Config.Labels}}' | tr ',' '\n' \
      | grep -iE 'rule|loadbalancer.server.port|docker.network'
    echo "  redes: $(docker inspect "$c" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
  fi
done
```

### 4.b El Studio de Supabase

Va aparte, en el proyecto del Supabase (`automatizacion-rp-supabase-dgimpk`), no en el nuestro:

| Dominio | Servicio | Puerto |
|---|---|---|
| `crm.rapilinksas.co` | **`kong`** | 8000 |

El servicio es `kong`, la pasarela de API — **no `db`**. Apuntarlo a `db` da 502 permanente: Postgres escucha en 5432 y no tiene nada en el 8000. Ya pasó una vez.

Al entrar pide usuario y contraseña: son `DASHBOARD_USERNAME` y `DASHBOARD_PASSWORD` de las variables de ese proyecto.

`motor`, `ollama` y `redis` **no llevan dominio**. El frontend alcanza al motor por la red interna (`http://motor:5000`); exponerlo sería abrir el asistente a internet sin autenticación.

### 4.c El webhook de WhatsApp — la única excepción

Meta necesita una URL pública HTTPS para entregar los mensajes, así que el motor **sí** necesita un dominio. Pero solo para esa ruta:

| Dominio | Servicio | Puerto | Regla de Traefik |
|---|---|---|---|
| `motor.rapilinksas.co` | `motor` | 5000 | `Host(...) && PathPrefix(/canales/whatsapp)` |

⚠️ **No sirve reusar `agent.rapilinksas.co`.** Ese dominio apunta al **frontend** (puerto 3000), que no tiene esa ruta: la petición de Meta cae en el guardia de sesión de SvelteKit y sale un **307 a `/login`**. Meta espera el `hub.challenge` en texto plano, recibe una redirección, y muestra *«No se pudo validar la URL de devolución de llamada o el token de verificación»* — un mensaje que hace pensar en el verify token cuando el problema es que la URL nunca llegó al motor. Ya pasó una vez.

**Pasos, en este orden** (saltarse el primero hace fallar el tercero):

1. **DNS**: registro A de `motor.rapilinksas.co` → `86.48.18.185`. Comprobar con `dig +short motor.rapilinksas.co` antes de seguir; sin esto Traefik no puede emitir certificado.
2. **Variables** en Dokploy, servicio `motor`: `SECRETOS_CLAVE_MAESTRA` (obligatoria — sin ella no se descifra ninguna credencial) y `BOTTLECRM_API_TOKEN`. En `backend`, `celery-worker` y `celery-beat`: `ASISTENTE_URL` y `ASISTENTE_TENANT`.
3. **Dominio** en Dokploy sobre el servicio `motor`. La regla de arriba no se escribe a mano: Dokploy la arma con los campos del formulario.

| Campo del formulario | Valor |
|---|---|
| Service Name | `motor` |
| Host | `motor.rapilinksas.co` |
| **Path** | **`/canales/whatsapp`** ← acá va el `PathPrefix`, no en un campo de regla |
| Internal Path | `/` (el valor por defecto) |
| **Strip Path** | **apagado** |
| Container Port | `5000` |

⚠️ **Strip Path tiene que quedar apagado.** Encendido, Traefik le quita `/canales/whatsapp` a la petición antes de pasarla y al motor le llega `/rapilink`, que no existe: da **404 con todo lo demás bien configurado**, y el síntoma no señala la causa. El motor espera la ruta completa, que es justo lo que `Internal Path: /` significa.

**Redesplegar después de guardar** — Dokploy escribe las etiquetas de Traefik al recrear el contenedor, no al guardar el formulario. Lo avisa él mismo en el formulario, y es el paso que más veces se olvida.

⚠️ **El `PathPrefix` no es opcional.** Sin él, el mismo dominio publica `/chat`, `/agentes` y `/agentes/catalogo`, que no piden autenticación de ninguna clase: cualquiera podría conversar con el asistente a costa de la empresa y leer cómo está configurado cada agente. La regla tiene que restringirse a `/canales/whatsapp` y nada más.

⚠️ **Y por eso el envío proactivo vive FUERA de ese prefijo.** `POST /avisos/whatsapp/<tenant>` (mandar una plantilla) y `GET /plantillas/whatsapp/<tenant>` están deliberadamente en otra ruta: la firma de Meta no los protege —quien llama no es Meta, es una tarea interna del CRM por la red del compose— así que si cayeran bajo `/canales/whatsapp` quedarían expuestos a internet **sin autenticación de ninguna clase**, y cualquiera podría mandarle mensajes a los clientes de la empresa desde su número. Si algún día hay que exponerlos, necesitan autenticación propia primero.

La autenticación de esa ruta no es un token de sesión sino **la firma del cuerpo**: Meta firma cada entrega con el App Secret (`X-Hub-Signature-256`) y el motor rechaza con 401 lo que no valide. Falla cerrado — si no puede resolver el secreto (base caída incluida), tampoco procesa.

En Meta, la URL de callback se registra como `https://motor.rapilinksas.co/canales/whatsapp/rapilink` (el último segmento es el slug del tenant, así que un segundo ISP entra por la misma infraestructura sin tocar nada).

**Cómo saber en qué paso se quedó**, sin adivinar. Medido el 12/08/2026 con el dominio creado a medias:

```
curl -sk -o /dev/null -w "%{http_code} %{remote_ip}\n" https://motor.rapilinksas.co/salud
```

| Lo que sale | Dónde está el problema |
|---|---|
| `curl: (6)` no resuelve | Falta el DNS (paso 1) |
| IP correcta, pero **`404` y falla el certificado** | DNS ok, Traefik **sin ruta para ese host**: falta crear el dominio, o falta **redesplegar**. El certificado no existe porque Traefik solo lo pide cuando el router existe — el fallo de TLS es consecuencia, no causa |
| `404` con certificado válido | Hay ruta y `PathPrefix` está bien: `/salud` **debe** dar 404. Probar el handshake de abajo |
| `502` | Hay ruta pero el contenedor no responde: puerto equivocado (tiene que ser 5000) o el motor está caído |

El `404` de Traefik se reconoce por el cuerpo `404 page not found` en texto plano, `Content-Length: 19` y **sin cabecera `Server`**. Si viniera del motor sería un JSON.

Comprobar el alta antes de darla en Meta — tiene que devolver `12345` en texto plano:

```
curl "https://motor.rapilinksas.co/canales/whatsapp/rapilink?hub.mode=subscribe&hub.verify_token=<el-verify-token>&hub.challenge=12345"
```

Y que lo demás **no** esté publicado (404 de Traefik, no una respuesta del motor):

```
curl -s -o /dev/null -w "%{http_code}\n" https://motor.rapilinksas.co/salud   # 404 esperado
```

### Credenciales de WhatsApp

Se cargan **por empresa y cifradas** en `asistente.tenant_secrets` (ver `nucleo/seguridad/secretos.py`), no en el `.env`. El YAML solo guarda los nombres:

| Nombre | De dónde sale en Meta |
|---|---|
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp → API Setup. Es el ID del emisor, **no el teléfono** |
| `WHATSAPP_TOKEN` | System User → token **permanente**. El de la consola dura 24 h |
| `WHATSAPP_WABA_ID` | WhatsApp Business Account ID. Solo hace falta para plantillas |
| `WHATSAPP_APP_SECRET` | App → Settings → Basic. Firma los webhooks |
| `WHATSAPP_VERIFY_TOKEN` | **Lo inventa la empresa.** Solo se usa en el handshake de alta |

La única que sigue en el `.env` (y en las variables de Dokploy) es `SECRETOS_CLAVE_MAESTRA`, que es la que descifra las demás. **Si se pierde hay que volver a cargar todos los secretos a mano** — no hay forma de recuperarlos, y esa es la propiedad buscada. Generarla con:

```
py -3.13 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Permisos que el System User necesita: `whatsapp_business_messaging` y `whatsapp_business_management`.

### Plantillas y avisos proactivos

Fuera de las 24 h desde el último mensaje del cliente, WhatsApp solo acepta **plantillas aprobadas por Meta**. La configuración mapea una clave interna al nombre registrado (`plantillas: {aviso_mora: recordatorio_pago_v3}`) para que el código diga `aviso_mora` y cada empresa lo resuelva a lo suyo.

Antes de confiar en una plantilla, comprobar que Meta la aprobó de verdad — devuelve `declaradas_sin_aprobar`, que es lo único que hay que mirar:

```
curl "http://motor:5000/plantillas/whatsapp/rapilink"   # desde dentro de la red del compose
```

Una plantilla declarada en el YAML que Meta nunca aprobó falla recién al mandar el primer aviso, y a esa altura ya hay un cliente que no se enteró de su corte.

**Baja de avisos.** Un cliente que escribe `baja` (o `stop`, configurable) deja de recibir mensajes proactivos; `alta` lo revierte. No es cortesía: la Ley 1581 le da al titular el derecho a revocar la autorización, y por el lado de WhatsApp, un número que quiere dejar de recibir y no puede **bloquea** — y los bloqueos le bajan la reputación al número de la empresa, y con ella el límite de envío. La baja **no** corta la atención: si después escribe, se le contesta. Sin la **verificación del negocio** en Business Manager el número queda limitado a 250 conversaciones/día y no se aprueban plantillas. Y el número **no puede estar en uso en la app normal de WhatsApp**: hay que borrarlo de ahí o migrarlo, no se puede tener en los dos lados.

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

### 6. Comprobar que quedó bien

En este orden, porque cada paso descarta el anterior:

```
# 1. Los siete contenedores arriba, ninguno en Restarting
docker ps --filter "name=crm-agentico" --format "table {{.Names}}\t{{.Status}}"

# 2. Desde fuera: la interfaz, la API y el Studio
curl -s -o /dev/null -w "%{http_code}\n" https://agent.rapilinksas.co/login      # 200
curl -s -o /dev/null -w "%{http_code}\n" https://agent-api.rapilinksas.co/admin/ # 302
curl -s -o /dev/null -w "%{http_code}\n" https://crm.rapilinksas.co/             # 401

# 3. El circuito completo del asistente: embeddings, base, modelo y persistencia
docker exec <contenedor-motor> python -c "
import json, urllib.request, time
cuerpo = json.dumps({'tenant':'rapilink','rol':'tecnica',
                     'identificador_sesion':'prueba','mensaje':'hola'}).encode()
req = urllib.request.Request('http://127.0.0.1:5000/chat', data=cuerpo,
                             headers={'Content-Type':'application/json'})
t=time.time()
with urllib.request.urlopen(req, timeout=180) as r: d=json.load(r)
print(f'{time.time()-t:.1f}s'); print(d.get('respuesta','')[:300])
"
```

El paso 3 es el que vale: un 500 ahí no lo detecta ningún healthcheck, porque varios imports del motor son perezosos y solo fallan en la primera consulta real.

Y un cuarto, la primera vez que se despliega el editor de agentes — que crea y borra un rol de verdad contra la base, porque es el único camino que las pruebas locales no cubren (`tests/test_editor_config.py` valida las mutaciones sin Postgres):

```
docker exec <contenedor-motor> python -c "
import json, urllib.request, urllib.error
def pedir(metodo, ruta, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo else None
    req = urllib.request.Request(f'http://127.0.0.1:5000{ruta}', data=datos,
                                 headers={'Content-Type':'application/json'}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, r.read()[:200]
    except urllib.error.HTTPError as e: return e.code, e.read()[:300]
print(pedir('POST', '/agentes', {'tenant':'rapilink','nombre':'prueba_editor',
      'descripcion':'Borrar despues.','orientado_a':'colaborador','herramientas':[]}))
print(pedir('DELETE', '/agentes/prueba_editor?tenant=rapilink'))
"
```

Se espera `201` y después `204`. Un `500` que mencione `psycopg` o `app_backend` es la base; un `400` es la configuración, y el texto dice cuál. Después, `py -3.13 cli/cargar_config.py --ver rapilink` debe mostrar la versión subida en dos.

### 7. Cambiar la configuración después

La configuración vive en `asistente.tenant_config` y se edita en dos lugares, así que la sincronización va en **dos sentidos**:

| Qué cambia | Dónde se hace | Cómo llega al otro lado |
|---|---|---|
| Roles y agentes | La interfaz (`/agentes`) | Ya está en la base. Bajarlo al repo con `--exportar` |
| Nombre, tono y largo del asistente | La interfaz (`/settings/asistente`) | Ídem |
| Herramientas, prompts, RAG, filtros | El YAML, en git | `cli/cargar_config.py tenants/<slug>.config.yaml` |

Lo que se edita desde la interfaz necesita `PRIVATE_ASISTENTE_URL=http://motor:5000` y `PRIVATE_ASISTENTE_TENANT=<slug>` en el servicio `frontend`. Sin esas dos, las pantallas cargan pero no encuentran al asistente — y el hub de configuración las lista igual, sin valor, en vez de caerse.

```
py -3.13 cli/cargar_config.py --exportar rapilink   # base  -> archivo
py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml   # archivo -> base
```

**La carga se niega a pisar roles que solo existen en la base.** Es la protección que importa: un agente creado desde la interfaz no está en git y no se recupera. Cuando pasa, el comando dice exactamente qué se perdería y sale sin tocar nada; `--exportar` primero, revisar el `git diff`, y recién ahí cargar. Si de verdad hay que descartar lo de la base, `--forzar`.

La exportación conserva los comentarios del YAML — son notas de verificación en vivo, no adorno — y es idempotente: exportar dos veces seguidas no cambia el archivo, así que lo que salga en el diff es cambio real.

## Pendientes

Cosas sabidas que faltan. Cada una dice por qué importa, que es lo que no se deduce del código.

**Conectar el RAG.** El asistente no lee el corpus. `motor.responder()` solo usa `construir_system()` de `nucleo/recuperacion/`: no vectoriza la pregunta ni llama a `match_chunks`. Todo lo demás ya está en pie —106 fragmentos vectorizados, la función en la base, `bge-m3` corriendo, el aislamiento verificado— así que falta únicamente el paso que los une. Hoy, preguntarle a un técnico cómo diagnosticar una falla devuelve una respuesta razonable del prompt, no el procedimiento de `G-GO-04` que está cargado.

**Calibrar `umbral_similitud`.** Está en 0.35 y una pregunta deliberadamente ajena ("la receta del ajiaco santafereño") todavía arrastra un fragmento con 0.350. `bge-m3` da similitudes altas de base; 0.45 parece más sano, pero subirlo puede dejar fuera preguntas legítimas mal formuladas. Decidirlo midiendo con preguntas reales de los técnicos.

**Recargar el corpus con el Ollama del servidor.** Los 106 fragmentos actuales se vectorizaron con el `bge-m3` de una máquina de desarrollo. Si la versión del modelo que baja el contenedor no es idéntica, los vectores dejan de ser comparables con los de las consultas — y esto **no da error**: simplemente empieza a devolver fragmentos peores. Es la clase de degradación que nadie nota hasta que alguien dice que "el asistente ya no responde bien". `py -3.13 cli/cargar_corpus.py rapilink --forzar` con `OLLAMA_HOST` apuntando al servidor.

**Limpiar el esquema `asistente` de la base de isp-reports.** Una corrida temprana lo creó ahí con 106 fragmentos, cuando todavía se creía que el asistente viviría dentro de esa base. Está aislado en su propio esquema y no estorba, pero es contaminación de un proyecto en otro. `drop schema asistente cascade` contra `supabase-515b-db` no deja rastro — el esquema se diseñó para eso.

**Cerrar los puertos de Postgres expuestos.** Hoy `5432`, `6543`, `5433` y `6544` escuchan en la IP pública, protegidos solo por contraseña. Una vez que el CRM y el motor corran dentro del servidor, nadie externo los necesita. Para acceso administrativo desde fuera, túnel SSH en vez de puerto abierto:

```
ssh -L 5434:<ip-del-contenedor-db>:5432 root@86.48.18.185
```

**Un rol `crm_user` para Django.** Hoy el CRM se conecta como `postgres`, que tiene `BYPASSRLS` — las políticas de aislamiento no se evalúan. Con una sola organización no hay consecuencia visible, y por eso es fácil de olvidar. El motor ya baja a `app_backend` (ver `nucleo/persistencia/db.py`); el CRM todavía no.

**El webhook de WhatsApp — falta el dominio, no el código.** Las rutas ya existen (`GET`/`POST /canales/whatsapp/<tenant>`, ver §4.c) y sus guardas pasan (`py -3.13 tests/test_canal_whatsapp.py`). Lo que falta para el piloto: el DNS de `motor.rapilinksas.co`, crear el dominio en Dokploy con el `PathPrefix`, cargar las variables del §4.c, y cargar los secretos de Meta desde **Ajustes → WhatsApp**. Lo único de producto que sigue dependiendo de terceros son las plantillas para avisos proactivos, que las aprueba Meta.

**Autenticar `/chat` y `/agentes` en el motor.** Hoy no piden nada: lo que impide que se usen desde fuera es que el motor no sea alcanzable, y desde que exista el dominio del webhook (§4.c) lo único que los separa de internet es el `PathPrefix` de una regla de Traefik. Funciona, pero es **una sola capa**, y el resto del proyecto usa dos por principio (PRD §7.4: las reglas duras se aplican en código, no solo en la configuración de alrededor). Una regla mal escrita al agregar un dominio, y cualquiera puede conversar con el asistente a costa de la empresa y leer cómo está configurado cada agente.

La forma es un token de servicio compartido entre el frontend y el motor: una variable más en los dos lados y una comprobación en `nucleo/canales/api.py` que rechace sin ella. No es urgente mientras la regla esté bien —por eso está acá y no bloqueando el piloto— pero conviene hacerlo antes de sumar un segundo ISP, cuando haya más manos tocando dominios. El webhook seguiría exento: su credencial es la firma de Meta, no un token nuestro.

**Dar de alta un segundo ISP: el motor está listo, el pegamento no.** El motor ya es multi-empresa de verdad —la URL del webhook lleva el tenant (`/canales/whatsapp/<slug>`), las credenciales van cifradas por empresa en `asistente.tenant_secrets`, y el aislamiento está medido: `app_backend` sin fijar empresa ve **0 filas**, no todas—. BottleCRM, por su lado, ya es multi-organización.

Lo que no acompaña es lo que los une: **`PRIVATE_ASISTENTE_TENANT` es una variable de entorno usada en 23 lugares del frontend, y nunca se deriva de la organización del usuario logueado**. Con una sola empresa no se nota; con dos, hay que elegir:

| Camino | Qué implica | Costo |
|---|---|---|
| Un despliegue por ISP | Cada uno con su CRM y su frontend | Cero código, más contenedores que mantener |
| Una plataforma, N ISPs | Que esos 23 lugares saquen el tenant de `locals.org` | Trabajo acotado y mecánico, toca todas las pantallas del asistente |

Es una decisión de producto —¿se vende una instalación por ISP, o una plataforma donde entran varios?— y conviene tomarla **antes** de escribir el código, no después.

Dos cosas que se deciden junto con eso:

- **El nombre del dominio del webhook.** `motor.rapilinksas.co` está bajo la marca del primer cliente; el segundo ISP estaría pegando el dominio de otra empresa en su configuración de Meta. Si el camino es "una plataforma", conviene un dominio neutro desde el principio: cambiarlo después obliga a que **cada** cliente reconfigure su webhook en Meta a mano.
- **El motor corre con `--workers 1`** (ver el comentario en `docker-compose.prod.yml`). No es por memoria: `_sesiones` guarda el historial caliente en RAM del proceso. Aguanta bien con hilos, pero es un techo real con varios ISPs, y se levanta el día que ese historial viva en `asistente.conversations` en vez de en memoria.

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
