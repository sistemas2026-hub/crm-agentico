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

**Embeddings del corpus: API de OpenAI, no Ollama** (agosto 2026 -- ver `nucleo/recuperacion/embeddings.py`). El VPS no tenia recursos de sobra para correr un modelo local ademas de todo lo demas (el CRM, el motor, dos Supabase, Traefik), y el unico consumidor de ese contenedor era la vectorizacion del corpus: los cinco roles de chat ya estaban redirigidos a DeepSeek/Anthropic, asi que no hacia falta para nada mas. Se saco el servicio `ollama` de los dos compose (dev y prod) en vez de dejarlo corriendo sin uso.

Requiere `OPENAI_API_KEY` en el `.env` (dev) o en las variables de Dokploy del servicio `motor` (prod) -- ver la tabla de variables mas abajo. `cli/banco_pruebas.py` y `cli/prueba_velocidad.py` (PRD.md 7.1.1, comparar modelos de chat) siguen hablando contra el Ollama nativo de tu maquina si lo tenes instalado; eso no cambio, es un uso aparte del RAG.

**Recargar el corpus de produccion ya no necesita tunel SSH.** Antes habia que vectorizar desde una maquina de desarrollo apuntando al Ollama del servidor por un tunel, porque Ollama no publica puerto al host. Con OpenAI de por medio no hay ningun servicio de red al que hacerle tunel -- el script corre igual desde donde esten los `.docx` (`corpus/<slug>/*.docx`, que estan en `.gitignore` y nunca llegan a la imagen del motor), apuntando el `.env` local a la base real:

```
py -3.13 cli/cargar_corpus.py rapilink --forzar
```

Hecho en vivo el 13/08/2026: 106 fragmentos recargados con el `bge-m3` del servidor en 49 segundos -- pero ese fue el ultimo tunel: mas tarde ese mismo dia se paso a embeddings de OpenAI, asi que esos 106 quedaron obsoletos otra vez y hay que recargarlos una vez mas (ya sin tunel) antes de que el RAG vuelva a servir contexto real.

**No hay recarga en caliente del frontend dentro de Docker.** El código entra por un bind mount desde Windows y los eventos de archivo del host no cruzan al contenedor Linux, así que Vite nunca se entera de un cambio: sigue sirviendo el módulo compilado viejo. No falla ni avisa — se edita, se recarga el navegador y no pasa nada; o peor, SSR y cliente quedan en versiones distintas y sale `hydration_mismatch` en consola. Después de editar cualquier archivo del frontend:

```
docker compose restart frontend
```

El sondeo de archivos (`usePolling`), que es el arreglo habitual, **se probó acá y empeora las cosas**: deja el proceso a ~25% de CPU constante y le come el turno al servidor hasta que deja de responder (medido: `/login` cuatro minutos sin devolver un byte; apagándolo, 200 y CPU a 0%). Está detrás de `VITE_USE_POLLING`, apagada.

Y paciencia con el arranque en frío: la primera petición a cada ruta compila a través del bind mount y puede tardar un minuto. Después queda cacheada y responde en milisegundos.

⚠️ **No correr `pnpm build` ni `pnpm check` en Windows con el contenedor levantado.** Los dos ejecutan `svelte-kit sync`, que reescribe `.svelte-kit/generated/` — una carpeta que vive en el bind mount, o sea compartida con el contenedor. pnpm trunca los nombres de directorio largos en Windows, así que las rutas quedan escritas cortas y el contenedor (Linux, rutas completas) deja de resolverlas: la aplicación entera pasa a devolver **500** con `Failed to resolve import ... Does the file exist?`. El síntoma no apunta para nada a la causa. Si ya pasó:

```
docker exec <contenedor-frontend> sh -c "cd /app && pnpm exec svelte-kit sync"
docker compose restart frontend
```

Para verificar tipos o compilar sin romper el entorno, hacerlo **dentro** del contenedor: `docker exec <contenedor-frontend> pnpm check`.

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
| Trigger Type | **On Push** (`Autodeploy` encendido) — ver abajo |

⚠️ **El Compose Path importa.** `docker-compose.yml` es el de desarrollo: trae un Postgres local y publica el 5432, que en el VPS ya ocupa el pooler del Supabase viejo. Desplegar ese da `address already in use`.

⚠️ **Un `git push` a esa rama SALE A PRODUCCIÓN.** `Autodeploy` está encendido a propósito (confirmado el 15/08/2026). No hay paso intermedio ni nadie que apruebe: se empuja y se despliega.

Y esa rama la comparten dos personas, así que el commit de cualquiera redespliega el servicio del otro. La consecuencia práctica: **las guardas se corren ANTES de empujar, no después** — `tests/`, y `cli/evaluar.py` si se tocó un prompt, un catálogo o un modelo. Un push con algo roto no espera a que alguien lo revise.

Esta advertencia decía lo contrario hasta hoy (afirmaba que el disparador era manual). Estuvo desactualizada un tiempo indeterminado, y sirvió para razonar mal sobre por qué producción se comportaba distinto al motor local: se dio por hecho que allá había código viejo cuando ya estaba desplegado. **Si el disparador se cambia, hay que cambiar esta línea en el mismo momento.**

⚠️ **Un cambio de CONFIGURACIÓN no es un despliegue, y a veces necesita un reinicio.** `nucleo/canales/api.py` cachea la config por proceso (`_configs`) y la lee una sola vez. Los endpoints del editor llaman a `olvidar_config()` al guardar, así que **lo que se edita desde la interfaz se ve al instante**. Lo que se escribe desde un script o desde otra máquina (`cli/cargar_config.py`, `editor._editar`) NO invalida el caché del motor que está corriendo: sigue sirviendo la versión vieja hasta que se reinicie. El síntoma es desconcertante — la base dice v36, el agente contesta como en v35 — y cuesta un rato si no se sabe.

### 3. Variables

Van en la sección **Environment** del servicio. **Veinte** son obligatorias; el despliegue se detiene nombrando la que falte, antes de construir nada. Péguelas todas de una vez — **Compose se para en la primera**, así que ir agregándolas de a una es un redespliegue por variable.

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
OPENAI_API_KEY=
BOTTLECRM_API_TOKEN=

SECRETOS_CLAVE_MAESTRA=

ASISTENTE_TENANT=rapilink

DEFAULT_FROM_EMAIL=noreply@rapilinksas.co
```

`ASISTENTE_TENANT` es el slug del `tenants/<slug>.config.yaml`, y es de quién habla el frontend cuando alguien abre `/agentes` o `/settings/asistente`. Se declara acá y no en el código porque es lo único que ata esa interfaz a una empresa concreta. La URL del motor no está en esta lista: la fija el compose (`http://motor:5000`), que es quien conoce el nombre del servicio.

`SECRETOS_CLAVE_MAESTRA` descifra las credenciales por empresa (`asistente.tenant_secrets`). Tiene que ser **la misma** que la del `.env` de desarrollo, o lo que se cargue desde una máquina no se descifra en la otra. Se genera una vez con:

```
py -3.13 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Si se pierde, no hay forma de recuperar los valores**: hay que volver a cargar todas las credenciales a mano. Es la propiedad buscada, no un descuido — guardala donde guardes las demás.

`OPENAI_API_KEY` vectoriza el corpus (`nucleo/recuperacion/embeddings.py`, `text-embedding-3-large`). Reemplaza a Ollama local desde agosto 2026 — sin ella el motor arranca igual, pero cada pregunta se responde sin contexto documental y queda `[rag] no se pudo recuperar contexto` en el log.

`BOTTLECRM_API_TOKEN` lo usa el motor para abrir el ticket al escalar una conversación y para comprobar si ese caso sigue abierto. Sin él, el bot escala y el ticket nunca se crea.

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

`motor` y `redis` **no llevan dominio**. El frontend alcanza al motor por la red interna (`http://motor:5000`); exponerlo sería abrir el asistente a internet sin autenticación.

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

**Sincronizar la configuración del tenant. Redesplegar NO la actualiza.** El motor lee la configuración de `asistente.tenant_config`, no del YAML del repo: el contenedor puede tener código nuevo y seguir corriendo con roles, herramientas y modelos viejos. Nada avisa — el asistente contesta igual, solo que con menos herramientas de las que el repo cree que tiene.

```
py -3.13 cli/cargar_config.py --ver rapilink        # que hay hoy en la base
py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml
```

⚠️ **Esto ya causó un bug que costó medio día.** En agosto 2026 la base estaba en v14 y le faltaba `confirmar_identidad` en el rol `cliente_final`. El síntoma: un cliente confirmaba su identidad por WhatsApp y el bot respondía *"no tengo la herramienta para cerrar ese paso"* y escalaba a un humano. Se persiguió como un problema de prompt —el modelo **decía la verdad**, no alucinaba: esa herramienta no existía en la configuración que él veía—. Comparar el YAML contra la base habría dado la respuesta en un minuto.

La carga **se niega** a pisar roles que solo existan en la base y nombra cuál (los roles también se editan desde `/agentes`, y esas ediciones viven ahí). Si aparece esa negativa, hay dos caminos, y hay que elegir a conciencia:

```
py -3.13 cli/cargar_config.py --exportar rapilink            # la base gana: baja al YAML
py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml --forzar   # el YAML gana
```

Antes de `--forzar`, guardá la configuración vigente — es el único respaldo que vas a tener:

```
py -3.13 cli/cargar_config.py --ver rapilink > respaldo_config.txt
```

**Cargar el corpus.** A diferencia de Ollama, la API de OpenAI no necesita bajar ningún modelo — con `OPENAI_API_KEY` puesta (ver Variables) alcanza con correr, desde cualquier máquina con el `.env` apuntando a la base real:

```
py -3.13 cli/cargar_corpus.py rapilink --forzar
```

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

**`umbral_similitud` — cerrado, no era el número (20/08/2026).** La cifra de 0.35 (y el ejemplo del ajiaco arrastrando 0.350) se midió con el corpus vectorizado en `bge-m3` y las consultas ya vectorizadas con OpenAI — dos espacios vectoriales distintos, comparación sin sentido, no un umbral mal puesto. Re-medido con ambos lados en el mismo modelo (`text-embedding-3-large` recortado a 1024, ver embeddings.py) contra preguntas reales de `asistente.unanswered_queries` más un control deliberadamente ajeno: la ajena cae a 0.174 (margen amplio) y las preguntas de venta reales caen entre 0.40 y 0.48. **0.35 queda como está.**

De paso salió un hallazgo más grande que el umbral: los 18 documentos del corpus tenían `roles_permitidos: [soporte, facturacion, administracion]` — ninguno alcanzable por `cliente_final`, `ventas`, `soporte_tecnico_cliente` ni los otros roles de cara al cliente. Por eso las ~103 preguntas distintas registradas en `unanswered_queries` para esos roles tenían `mejor_similitud` **NULL siempre**, sin excepción: `match_chunks` filtra por rol antes de calcular ninguna similitud, así que devolvía cero filas pase lo que pase con el umbral. Ajustar el número no iba a cambiar nada de lo que recibía un cliente. Primer documento asignado a un rol de cliente: `MANUAL-VENTAS-01` (técnica de ventas, sin precios ni planes — esos siguen calculados por `consultar_planes_venta`), asignado a `ventas`.

**Limpiar el esquema `asistente` de la base de isp-reports.** Una corrida temprana lo creó ahí con 106 fragmentos, cuando todavía se creía que el asistente viviría dentro de esa base. Está aislado en su propio esquema y no estorba, pero es contaminación de un proyecto en otro. `drop schema asistente cascade` contra `supabase-515b-db` no deja rastro — el esquema se diseñó para eso.

**Cerrar los puertos de Postgres expuestos.** Hoy `5432`, `6543`, `5433` y `6544` escuchan en la IP pública, protegidos solo por contraseña. Una vez que el CRM y el motor corran dentro del servidor, nadie externo los necesita. Para acceso administrativo desde fuera, túnel SSH en vez de puerto abierto:

```
ssh -L 5434:<ip-del-contenedor-db>:5432 root@86.48.18.185
```

**Un rol `crm_user` para Django — creado y verificado (18/08/2026), falta el corte en Dokploy.**

Hoy el CRM se conecta como `postgres`, que tiene `BYPASSRLS` — las políticas de aislamiento no se evalúan. Con una sola organización no hay fuga posible entre clientes, y por eso es fácil de olvidar; el riesgo real es otro, y hay que decirlo primero: **el propio diagnóstico de BottleCRM (`manage_rls --status`) miente en este entorno.** Solo mira `usesuper` en `pg_user` (`common/management/commands/manage_rls.py:60`), y en Supabase `postgres` tiene `rolsuper=false` pero `rolbypassrls=true` — dos atributos distintos que el comando no distingue. Reporta *"Database user postgres is not a superuser — RLS will be enforced"*, y es falso: verificado por SQL directo (`select rolsuper, rolbypassrls from pg_roles`), las 60 tablas de `ORG_SCOPED_TABLES` tienen su política `ENABLED (forced)` — las migraciones de BottleCRM ya las activaron — pero no protegen nada mientras el CRM se conecte como `postgres`. Es exactamente el error que la propia documentación de BottleCRM (`postgresql-and-rls.md`) advierte que puede pasar desapercibido "sin error, sin log", solo que aquí pasa incluso con su propia herramienta de verificación.

**Lo que ya se hizo, sin tocar producción:**

1. `crm_user` creado en la base real (`CREATE ROLE ... LOGIN`, sin `BYPASSRLS`, sin `SUPERUSER`) con `GRANT ALL` sobre el esquema `public` (tablas, secuencias y funciones existentes, más `ALTER DEFAULT PRIVILEGES` para las que cree `postgres` a futuro). El esquema `asistente` del motor **no** se tocó — mismo criterio de aislamiento que ya separa `app_backend`.
2. Verificado con el backend local apuntando a la base real (ver "Desarrollo local contra la base real"), sin pasar por Dokploy: `manage_rls --verify-user` confirma `Is superuser: False` bajo `crm_user` — a diferencia de `--status`, este SÍ pregunta lo correcto. `--test` no corre (pide 2 organizaciones y hoy hay 1), así que se probó a mano: con `app.current_org` puesto al id real, `crm_user` ve exactamente las mismas filas que ve `postgres` sin ninguna restricción (11 `cases`, verificado); sin contexto, 0 filas — el fail-safe funciona.
3. Revisadas las 11 tareas de Celery en `common/tasks.py`: las que tocan tablas con RLS (`remove_users`, `update_team_users`, `purge_read_notifications`, `ingerir_documento_en_asistente`, `retirar_documento_del_asistente`) ya llaman `set_rls_context()`. Las que no lo llaman (`send_welcome_email` y las otras tres de email, `flush_expired_refresh_tokens`) operan sobre `profile`/`user`/tokens, que **no** están en `ORG_SCOPED_TABLES` — no necesitan contexto. No hay ninguna tarea activa en este despliegue que vaya a devolver "cero filas" en silencio tras el corte.

**Lo que falta, y por qué no se hizo solo:**

`docker/backend/entrypoint.sh` corre `migrate --noinput` con las mismas credenciales (`DBUSER`/`DBPASSWORD`) con las que gunicorn sirve las peticiones — no hay un usuario de migración separado. Si `crm_user` se pone en Dokploy, las migraciones **futuras** de BottleCRM correrían como `crm_user`, que no es dueño de las tablas: una migración nueva que llame `get_enable_policy_sql()` sobre una tabla recién creada (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) fallaría, porque esa operación exige ser el dueño. No es un problema hoy — no hay ninguna migración pendiente que lo necesite — pero es una decisión de despliegue (¿migrar siempre con una credencial de owner aparte? ¿aceptar el riesgo y arreglarlo si aparece?) que no me correspondía tomar sola.

**Activado en producción (18/08/2026), con un incidente real de por medio — ver abajo.** `DBUSER`/`DBPASSWORD` son una sola variable compartida por todo el stack (Docker Compose, no un panel por servicio como se pensaba al principio), así que el corte fue un solo cambio, no tres. Primer intento falló el build (`error while interpolating services.backend.environment.DBPASSWORD: required variable DBPASSWORD is missing a value`) por escribir `DBUSER:...` con dos puntos en vez de `DBUSER=...` — un `.env` no es YAML. Corregido, redesplegado.

**La verificación que se hizo en ese momento fue incompleta — solo probó el CRM, no el motor.** `https://agent.rapilinksas.co/login` y `https://agent-api.rapilinksas.co/admin/` cargaban normal, sin 500/502, y eso se tomó como "andá". Pero esas dos URLs son Django, que sí funciona con `crm_user`. El **motor** (`nucleo/`, servicio aparte) también leía `${DBUSER}`/`${DBPASSWORD}` — la misma variable — y `crm_user` no tiene ningún privilegio sobre el esquema `asistente`. Nadie lo notó hasta que un script de este mismo día (`cli/reporte_huecos_documentacion.py`, corriendo local contra la base real) dio `psycopg.errors.InsufficientPrivilege: permission denied for schema asistente`.

**Impacto real, mientras esa configuración estuvo activa:** las conversaciones de WhatsApp siguieron respondiendo normal (el historial de una charla vive en memoria del proceso, no en la base, turno a turno — ver el comentario sobre `--workers 1` más abajo), pero cualquier intento de guardar algo en `asistente.*` —mensajes, `tool_calls`, conversaciones nuevas— falló en silencio: varias de esas funciones atrapan la excepción y solo la logean, a propósito, para no tumbarle la respuesta a un cliente por un problema de auditoría. Consecuencia: un hueco de datos en esa ventana, no un corte de servicio. No se puede recuperar lo que no se guardó.

**Mitigación inmediata:** revertir `DBUSER`/`DBPASSWORD` a los valores de `postgres` en Dokploy, redesplegar. Confirmado que la conexión volvió (`cli/reporte_huecos_documentacion.py` corrió limpio contra datos reales).

**Arreglo de fondo: el motor necesita una credencial propia, nunca la misma que Django.** Se creó `motor_user` — mismo patrón que ya usaba `postgres` para el motor (`LOGIN`, `BYPASSRLS` porque `nucleo/persistencia/db.py::_organizacion()` resuelve el tenant *antes* de bajar a `app_backend`, a propósito, y esa consulta puntual necesita bypass — está comentado así en el propio código), con `GRANT app_backend TO motor_user`. `docker-compose.prod.yml` deja de compartir variable: `motor` ahora lee `${MOTOR_DBUSER}`/`${MOTOR_DBPASSWORD}`, distintas de `${DBUSER}`/`${DBPASSWORD}` que siguen siendo de `crm_user` para `backend`/`celery-*`.

**Para terminar de activarlo en producción**, además de lo ya cargado:

| Servicio | `DBUSER` | `DBPASSWORD` |
|---|---|---|
| `backend`, `celery-worker`, `celery-beat` | `crm_user.05b5a4b4-3b9a-4901-86f2-f3ed8f8ac0a1` | (la de `crm_user`, ya cargada) |
| `motor` | `${MOTOR_DBUSER}` → agregar en Dokploy: `motor_user.05b5a4b4-3b9a-4901-86f2-f3ed8f8ac0a1` | `${MOTOR_DBPASSWORD}` → agregar (entregada aparte, nunca commiteada) |

Redesplegar, y esta vez **verificar el motor específicamente** (no alcanza con que el CRM cargue) — `cli/reporte_huecos_documentacion.py` o cualquier script de `cli/` corriendo contra la base real sirve de prueba.

Sigue en pie el pendiente de fondo del lado de Django: el día que una migración de BottleCRM necesite activar RLS en una tabla nueva, va a fallar bajo `crm_user` porque no es dueño de las tablas (`postgres` sí). No es una tarea de hoy — se resuelve separando la credencial de migración de la de tráfico normal cuando haga falta.

**Lección de esto, para cualquier corte de credencial futuro: verificar CADA servicio que lea la variable que se está cambiando, no el primero que responda bien.** Un `grep` de la variable en el compose antes de cortar hubiera mostrado los cuatro servicios que la usaban, no solo los tres que se pensaban cambiar.

**El webhook de WhatsApp — falta el dominio, no el código.** Las rutas ya existen (`GET`/`POST /canales/whatsapp/<tenant>`, ver §4.c) y sus guardas pasan (`py -3.13 tests/test_canal_whatsapp.py`). Lo que falta para el piloto: el DNS de `motor.rapilinksas.co`, crear el dominio en Dokploy con el `PathPrefix`, cargar las variables del §4.c, y cargar los secretos de Meta desde **Ajustes → WhatsApp**. Lo único de producto que sigue dependiendo de terceros son las plantillas para avisos proactivos, que las aprueba Meta.

**Contestarle a un BSUID va por `recipient`, no por `to`.** Está resuelto, pero queda escrito porque el error costó días y no da ninguna señal de que se está cometiendo.

Desde abril de 2026 Meta entrega `contacts[0].user_id` y `messages[0].from_user_id` con la forma `CO.1360399936298471` —un **BSUID** (Business-Scoped User ID)— en vez de `wa_id`/`from`, cuando la persona escondió su número detrás de un nombre de usuario. Los envíos a BSUID se habilitaron en julio de 2026.

El campo del destinatario **no es el mismo para los dos**: `to` es para un teléfono, `recipient` para un BSUID (con `recipient_type: individual` en ambos). Lo resuelve `_destinatario()` en `nucleo/canales/whatsapp.py`.

**Por qué no se ve el error.** Un BSUID mandado por `to` no da 400. Meta acepta con **200**, le extrae los dígitos, los trata como teléfono, y el fallo llega minutos después y por otro lado: un **131026** (*"el número no es un número de WhatsApp"*) en el webhook de `statuses`. El log dice que el mensaje salió. Nada apunta al campo.

Eso mandó la búsqueda a todos lados menos al lugar correcto: se revisó y descartó la URL del callback, `active: true`, la suscripción al campo `messages`, el App Secret, el verify token, el número (`CONNECTED`, `CLOUD_API`, `VERIFIED`), la suscripción de la WABA y la app publicada. Se probaron cinco formas del destinatario en `v23.0` y `v26.0` —**todas usando `to`**, que era el error—. Y se llegó a escribir acá que no había forma de responder, que era falso.

**Dos detalles que hacen fallar la petición:** el `CO.` es parte del identificador, no un prefijo de país — quitarle el punto o los caracteres alfanuméricos la rompe. Y los BSUID están acotados al *business portfolio*: solo un número del mismo portfolio puede escribirle a un BSUID dado.

**Lo que sigue sin poder hacerse** es reconocer al cliente: un BSUID no es un teléfono, así que no cruza contra WispHub. Esa persona tiene que identificarse con la cédula, como cualquier número desconocido. Por eso `mensajes_entrantes()` guarda `telefono` y `bsuid` en campos separados en vez de colapsarlos.

**Autenticar `/chat` y `/agentes` en el motor — COMPLETO (agosto 2026).** Hoy `/chat`, `/agentes` y el resto de rutas internas no pedían nada: lo único que las separaba de internet era el `PathPrefix` de una regla de Traefik, una sola capa, cuando el resto del proyecto usa dos por principio (PRD §7.4). El lado del **motor**: `nucleo/canales/api.py::_exigir_token_de_servicio()` rechaza con 401 cualquier ruta que no sea `/salud` o el webhook de WhatsApp (esas dos se autentican con otro mecanismo — healthcheck sin credenciales y firma de Meta, respectivamente) si no llega el header `X-Servicio-Token` con el valor de `MOTOR_SERVICE_TOKEN`. Guarda: `tests/test_token_servicio.py`.

**Deliberadamente NO bloquea nada si `MOTOR_SERVICE_TOKEN` no está en el entorno** — así no rompe un arranque local ni el despliegue actual, que todavía no la tiene cargada.

**El lado del frontend ya está wireado.** `django-crm/frontend` le habla al motor desde 30 archivos (~40 llamadas `fetch()`), sin un cliente HTTP compartido — cada ruta arma la suya, así que se agregó `lib/server/v2/motor-headers.js` (`headersMotor()`) y se aplicó a las 30. Sin `PRIVATE_MOTOR_SERVICE_TOKEN` puesto, no manda nada (mismo criterio permisivo del motor). **Verificado con el stack local corriendo (Docker), no solo con `pnpm check`**: se activó `MOTOR_SERVICE_TOKEN` en el `.env` local, se confirmó `401` sin header / `200` con el header correcto contra el motor real, y se repitió exactamente la lógica de `headersMotor()` desde dentro del contenedor del frontend contra el motor real — `200`, datos reales. La llamada frontend→motor es una red interna de Docker (`http://motor:5000`) idéntica en forma en desarrollo y en producción (confirmado comparando ambos `docker-compose*.yml`), así que este mecanismo verificado en local es el mismo que correría en Dokploy.

**Lo que la verificación local NO prueba, y sigue siendo un paso manual:** que la variable quede cargada en Dokploy, con el **mismo valor**, en los dos servicios (`motor` y `frontend`). Es configuración de la interfaz de Dokploy, no código.

### Para activarlo en producción

1. Generar un valor random (ej. `openssl rand -hex 32` o cualquier cadena larga e impredecible — no tiene que ser recordable, es una contraseña entre dos servicios).
2. En Dokploy, panel del servicio **`crm`** → **Environment**: agregar `MOTOR_SERVICE_TOKEN=<el mismo valor>` una sola vez (Compose ya lo reparte a `motor` como `MOTOR_SERVICE_TOKEN` y a `frontend` como `PRIVATE_MOTOR_SERVICE_TOKEN`, ver `docker-compose.prod.yml`).
3. **Reload** (o redeploy) para que los contenedores relean el entorno.
4. Confirmar en los logs de `motor` que dice `MOTOR_SERVICE_TOKEN activo` (no `no esta configurado`).
5. Probar `/agentes` y un par de pantallas más — si algo devuelve "Asistente no configurado" o un error de red, revisar que el valor haya llegado igual a los dos servicios.

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

**Variables muertas en `.env` — retiradas (18/08/2026).** `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` no las usaba nadie en este repositorio (confirmado por grep completo, no solo por sospecha) — residuo de un diseño anterior donde el frontend hablaba directo con Supabase; ARQUITECTURA.md también las listaba y quedó corregido. Solo en el `.env` local, no versionado — cada colaborador con su propia copia debe quitarlas a mano si las tiene.

## Diagnóstico

Errores que ya costaron tiempo una vez.

**`fetch failed` (o `Bad Gateway`) en mitad de una conversación que venía bien, y la respuesta SÍ está guardada en la base.** No es el motor caído: es el motor tardando de más *después* de haber hecho su trabajo. `atender_turno()` (`nucleo/canales/api.py`) calcula la respuesta, la persiste, y **recién después** — todavía dentro del mismo request, antes de devolver el HTTP — hace hasta tres llamadas más al modelo que no son parte de la respuesta del cliente: evaluar si corresponde escalar, verificar agendamiento, y auditar con el supervisor. Si alguna se demora, el proxy corta la conexión y el cliente ve un error por una respuesta que ya existía.

La señal que lo identifica, y que evita perseguirlo como un problema de red: **buscar la conversación en `asistente.messages` y ver si la respuesta del asistente está ahí.** Si está (y `tool_calls` muestra todo en orden y rápido), el motor funcionó — lo que falló fue la entrega, y la causa está en lo que corre *después* de persistir.

Arreglado el 21/08/2026 acotando cada llamada al modelo: hasta entonces **ninguna** llevaba timeout y se usaba el default del SDK de cada proveedor (minutos, o ninguno). Ahora `nucleo/modelo/cliente.py` define `TIMEOUT_POR_DEFECTO` (90 s, la respuesta que el cliente espera) y `TIMEOUT_SECUNDARIO` (20 s, el trabajo que no espera nadie); los tres llamadores secundarios usan el corto y, si se agota, abandonan esa vuelta y se reintentan en el turno siguiente — que es lo que ya hacían cuando el modelo no contestaba con la función. Guarda: `py -3.13 tests/test_timeouts_modelo.py`.

**El asistente dice que no tiene una herramienta que SÍ está en el YAML.** No es el modelo alucinando: casi seguro está diciendo la verdad sobre la configuración que él ve. El motor lee de `asistente.tenant_config`, no del repo, y redesplegar no la sincroniza. Antes de tocar prompts, comparar:

```
py -3.13 cli/cargar_config.py --ver rapilink
```

Si al rol le faltan herramientas que el YAML sí declara, la cura es `cli/cargar_config.py` (ver §5), no reescribir el prompt. Pasó exactamente así con `confirmar_identidad` en agosto 2026 — ver la advertencia de esa sección.

**Un servicio del compose no resuelve el nombre de otro** (`Temporary failure in name resolution`). Se quedó sin la red `default`, que es por la que los servicios se encuentran por nombre. Pasó con el motor: quedó solo en `dokploy-network` y dejó de ver a `ollama` (el servicio que vectorizaba el corpus antes de pasar a la API de OpenAI, agosto 2026 — ya no existe, pero la lección de red vale igual para cualquier servicio futuro), así que el RAG se apagó. No rompía el turno —`recuperar()` atrapa el error a propósito, porque peor es no atender— así que el asistente siguió contestando, solo que sin la documentación interna, y se notó días después.

Lo que más costó fue el mensaje: la librería de Ollama decía `Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible`, o sea mandaba a instalar algo que llevaba dos días corriendo, sano y con `bge-m3` bajado. La causa no estaba en Ollama sino en la red.

Se ve en una línea — si dos servicios no comparten ninguna red, ahí está:

```
docker inspect -f '{{.Name}} -> {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'   $(docker ps -q --filter name=<servicio-a>) $(docker ps -q --filter name=<servicio-b>)
```

**Por qué se quedó sin `default`, no se sabe.** La explicación obvia —que Dokploy le escribe `networks: [dokploy-network]` al darle dominio, y en Compose declarar una red explícita reemplaza a `default` en vez de sumarse— **no se sostiene**: `backend` también tiene dominio y quedó con las dos. Así que no es una consecuencia automática de tener dominio. Se comprobó el 13/08/2026, después de haberlo escrito acá al revés.

Lo que sí queda resuelto es que no vuelva a depender de eso: los tres servicios con dominio (`backend`, `frontend`, `motor`) declaran **las dos** redes explícitamente en `docker-compose.prod.yml`. Los que no tienen dominio se quedan fuera de `dokploy-network` a propósito: es compartida con los demás proyectos del VPS y ni `redis` ni la base tienen nada que hacer ahí.

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
