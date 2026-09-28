# B-7 — INVESTIGACIÓN: CÓMO CAMBIAR EL RUNTIME EN DOKPLOY

Fecha: 2026-09-19 · **Solo investigación. No se cambió nada.**

Sin commit, sin `git stash`, sin redeploy, sin tocar `DBUSER`, sin `export`, sin
`docker exec` modificando archivos. Ningún valor secreto impreso.

---

# LA RESPUESTA CORTA A TU PREGUNTA

**No existe un comando en la terminal de Dokploy que haga el cambio
persistente.** La terminal de Dokploy es un **Docker Terminal**: te mete
*dentro* de un contenedor. Un contenedor se **reemplaza** en el redeploy, así
que todo lo que cambies ahí desaparece por construcción — no es una limitación
de Dokploy, es lo que significa recrear un contenedor.

El cambio persistente se hace en **Dokploy → servicio → Environment**, que es
donde Dokploy guarda las variables que interpola en el compose.

La terminal sí sirve, y mucho, para **otra cosa**: verificar antes y después. Eso
te lo dejo abajo.

---

# 1. EL CONTENEDOR DEL RUNTIME

`[NO VERIFICABLE DESDE AQUÍ]` No tengo acceso al VPS — sin llaves en `~/.ssh`
(solo `known_hosts`), y los contextos de Docker de esta máquina son locales
(`npipe:////./pipe/docker_engine`, `desktop-linux`). No puedo listar los
contenedores reales.

`[MEDIDO]` Lo que sí sé del repositorio: **`docker-compose.prod.yml` no declara
`container_name` en ningún servicio** (0 ocurrencias). Por lo tanto los nombres
los genera Docker Compose a partir del nombre del proyecto que le pone Dokploy,
con la forma `<proyecto>-<servicio>-<n>`.

El comando para identificarlo está en §6.

# 2. EL SERVICIO DEL COMPOSE

`[MEDIDO]` El runtime del CRM son **tres** servicios, no uno:

| Servicio | Qué es | Comando |
|---|---|---|
| **`backend`** | Django + gunicorn. **Es el que sirve las peticiones** | `/bin/bash /entrypoint.sh` |
| **`celery-worker`** | tareas asíncronas | — |
| **`celery-beat`** | tareas periódicas | — |

Los tres se construyen desde `./django-crm/Dockerfile` y **los tres leen las
mismas variables de base**.

`[MEDIDO]` En Dokploy el servicio está creado como **Compose**, no Application
(`DESPLIEGUE.md` §2): repositorio `sistemas2026-hub/crm-agentico`, rama
`fix/integracion-wisphub`, Compose Path `./docker-compose.prod.yml`, Autodeploy
**On Push**.

⚠️ Eso último importa para tu ventana: **un `git push` a esa rama sale a
producción solo**, y la rama la comparten dos personas.

# 3. CÓMO RECIBEN LAS VARIABLES

`[MEDIDO]` **Todas por `environment:`.** El compose **no usa `env_file` ni
`secrets:`** en ningún servicio (0 ocurrencias). El valor se interpola desde el
entorno del despliegue, o sea desde la sección **Environment** de Dokploy.

## Asignaciones reales (comentarios excluidos)

| Variable en Dokploy | Servicio | Línea | Clave dentro del contenedor | ¿Obligatoria? | Mecanismo |
|---|---|---|---|---|---|
| `DBUSER` | `backend` | 112 | `DBUSER` | **sí** (`:?`) | `environment` |
| `DBUSER` | `celery-worker` | 177 | `DBUSER` | **sí** | `environment` |
| `DBUSER` | `celery-beat` | 222 | `DBUSER` | **sí** | `environment` |
| `DBPASSWORD` | `backend` | 113 | `DBPASSWORD` | **sí** | `environment` |
| `DBPASSWORD` | `celery-worker` | 178 | `DBPASSWORD` | **sí** | `environment` |
| `DBPASSWORD` | `celery-beat` | 223 | `DBPASSWORD` | **sí** | `environment` |
| `DBHOST` | `backend`, `celery-worker`, `celery-beat`, `motor`, `motor-reloj` | 109/174/219/304/403 | `DBHOST` | **sí** | `environment` |
| `DBNAME` | los mismos cinco | 111/176/221/306/405 | `DBNAME` | **sí** | `environment` |
| `DBPORT` | los mismos cinco | 110/175/220/305/404 | `DBPORT` | **sí** | `environment` |
| `MOTOR_DBUSER` | `motor`, `motor-reloj` | 307/406 | `DBUSER` | **sí** | `environment` |
| `MOTOR_DBPASSWORD` | `motor`, `motor-reloj` | 308/407 | `DBPASSWORD` | **sí** | `environment` |
| `MIGRATOR_DBUSER` | `backend` | 123 | `MIGRATOR_DBUSER` | no (`:-`) | `environment` |
| `MIGRATOR_DBPASSWORD` | `backend` | 124 | `MIGRATOR_DBPASSWORD` | no (`:-`) | `environment` |

Todas **PRESENTES** en el compose. Ningún valor mostrado.

`:?` significa que el despliegue **se detiene** si falta, nombrando la variable,
antes de construir nada. `:-` significa opcional.

## Lo que importa: a quién afecta cambiar `DBUSER`

```
cambiar ${DBUSER}/${DBPASSWORD} afecta EXACTAMENTE a: backend, celery-beat, celery-worker
NO afecta a: motor, motor-reloj   (leen MOTOR_DBUSER/MOTOR_DBPASSWORD)
```

**Es una sola edición, no tres.** `DBUSER` es una variable compartida del stack;
Dokploy la reparte a los tres servicios.

Ojo con el detalle inverso: `motor` y `motor-reloj` **sí** comparten `DBHOST`,
`DBNAME` y `DBPORT` con el CRM. Tocar cualquiera de esas tres **sí** los
alcanzaría. Por eso no se tocan.

---

# 4. `[CRÍTICO]` ESTE CAMBIO YA SE HIZO UNA VEZ Y SALIÓ MAL

Está documentado en `DESPLIEGUE.md`, y merece leerse antes de repetirlo.

**18/08/2026.** Se puso `crm_user` en Dokploy. La verificación fue incompleta:
se probó que `agent.rapilinksas.co/login` y `/admin/` cargaran, y eso se tomó
por «anda». Pero en ese momento **el motor leía la misma `${DBUSER}`**, y
`crm_user` no tiene ningún privilegio sobre el esquema `asistente`.

Consecuencia medida: las conversaciones de WhatsApp **siguieron respondiendo
normal** —el historial vive en memoria del proceso— pero todo lo que debía
guardarse en `asistente.*` (mensajes, `tool_calls`, conversaciones nuevas)
**falló en silencio**: esas funciones atrapan la excepción y solo la logean, a
propósito, para no tumbarle la respuesta a un cliente por un problema de
auditoría.

> **Un hueco de datos, no un corte de servicio. No se puede recuperar lo que no
> se guardó.**

Se detectó recién cuando un script local dio
`psycopg.errors.InsufficientPrivilege: permission denied for schema asistente`.

**Hoy ese camino está cerrado**: `motor` y `motor-reloj` leen
`MOTOR_DBUSER`/`MOTOR_DBPASSWORD`, verificado arriba en las líneas 307, 308, 406
y 407. El incidente **no puede repetirse por esa vía**.

La lección que dejó escrita, y que apliqué en esta investigación:

> *«verificar CADA servicio que lea la variable que se está cambiando, no el
> primero que responda bien.»*

## Y el otro tropiezo del mismo día

El primer intento **rompió el build**:

```
error while interpolating services.backend.environment.DBPASSWORD:
required variable DBPASSWORD is missing a value
```

Causa: se escribió `DBUSER:` con **dos puntos**. **La sección Environment de
Dokploy es formato `.env` (`CLAVE=valor`), no YAML.**

---

# 5. ¿HAY UNA FORMA SEGURA DESDE LA TERMINAL? — **NO**

## Por qué no, en tres niveles

**a) `[CIERTO POR CONSTRUCCIÓN]` Dentro del contenedor, nada persiste.** El
Docker Terminal de Dokploy hace `exec` sobre un contenedor en marcha. El
redeploy **lo destruye y crea otro** desde la imagen. Un `export`, un `.env`
editado o un archivo tocado ahí dentro no sobrevive — y mientras tanto te deja
un proceso corriendo con una configuración que no está en ningún lado, que es
peor que no hacer nada.

**b) `[CIERTO POR CONSTRUCCIÓN]` Editar el compose del repositorio tampoco
sirve**, y además es peligroso: `docker-compose.prod.yml` declara
`DBUSER: ${DBUSER:?}`, o sea que **no contiene el valor**. Cambiarlo ahí
significaría *hardcodear una credencial en un archivo versionado*, y con
Autodeploy On Push saldría a producción con el `git push`.

**c) `[CONOCIMIENTO GENERAL, no medido — verificalo con §6]` El `.env` que
Dokploy materializa junto al compose lo regenera él desde su propia base en cada
despliegue.** Editarlo desde una shell del host se perdería en el siguiente
deploy desde la interfaz. No pude comprobarlo: no tengo acceso al VPS. Lo marco
como lo que es en vez de afirmarlo.

## Entonces, el único camino persistente

**Dokploy → servicio → pestaña Environment → editar → Redeploy/Recreate.**

Es la misma vía que usó el corte del 18/08 (`DESPLIEGUE.md` lo describe así) y la
que usan el resto de los procedimientos del proyecto.

---

# 6. LO QUE SÍ TE SIRVE LA TERMINAL: VERIFICAR

Todos estos comandos son **de solo lectura**. Ninguno cambia nada.

## Antes de tocar nada — identificar el contenedor y el servicio

Si la terminal de Dokploy te da shell en el **host**:

```sh
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -Ei 'backend|celery|motor'
```

Si te da shell **dentro del contenedor del backend**, confirmá que es el correcto
sin imprimir secretos:

```sh
# quien es este contenedor
hostname
# que proceso corre
ps -eo pid,comm,args --no-headers | head -5
# que variables de base EXISTEN, sin mostrar valores
for v in DBHOST DBPORT DBNAME DBUSER DBPASSWORD MIGRATOR_DBUSER MIGRATOR_DBPASSWORD; do
  if [ -n "$(printenv $v)" ]; then echo "$v = PRESENTE"; else echo "$v = AUSENTE"; fi
done
```

⚠️ **No uses `echo $DBUSER`.** `DESPLIEGUE.md` lo sugiere, pero imprime el
usuario **con el sufijo del pooler** en pantalla. Esta versión dice
PRESENTE/AUSENTE y nada más.

## El rol EFECTIVO — que es otra cosa que la variable

```sh
python manage.py verificar_credenciales --proposito trafico --con-base
```

Esta guarda ya existe (`common/credenciales.py`) y **no compara por el nombre**:
cuenta de cuántas tablas de `public` el rol efectivo no puede ejercer el dueño.
Hoy, con `postgres`, debería avisar que el tráfico corre con un rol que tiene
`BYPASSRLS`.

## Después del redeploy — las tres comprobaciones que el 18/08 no se hicieron

```sh
# 1. el backend corre como crm_user
python manage.py verificar_credenciales --proposito trafico --con-base

# 2. el MOTOR sigue con su propia identidad (lo que faltó aquella vez)
#    en el contenedor de 'motor':
python -c "from nucleo.persistencia import db; \
           print(db.sesion.__module__)" >/dev/null 2>&1; \
python cli/reporte_huecos_documentacion.py 2>&1 | tail -3

# 3. la identidad medida desde la base, no desde la variable
```

La tercera la hago yo desde aquí en cuanto me avises: consulto
`pg_stat_activity` y te digo qué `usename` tiene cada conexión y de cuándo son.
**Es la única que no se puede falsear**: si el redeploy no ocurrió, las
conexiones siguen viejas.

---

# 7. EL PROCEDIMIENTO EXACTO — para cuando lo autorices

**No lo ejecutes todavía.** Lo dejo escrito para que lo revises.

### Paso 1 — abrir Environment

Dokploy → proyecto de la plataforma (**`crm-agentico-*`**, *no* el de Supabase)
→ el servicio Compose (en `DESPLIEGUE.md` figura como panel **`crm`**) →
pestaña **Environment**.

### Paso 2 — editar DOS líneas

Formato `.env`: **`CLAVE=valor`, con `=`, nunca `:`**.

```
DBUSER=crm_user.<el mismo sufijo de pooler que ya tiene el valor actual>
DBPASSWORD=<la de C:\Users\Usuario\b8_crm_user_clave.txt>
```

El sufijo es el del tenant de Supavisor, el mismo que hoy acompaña a `postgres.`
— **no lo inventes ni lo escribas de memoria**: copiá el valor actual de `DBUSER`
y reemplazá solo la parte de antes del punto. (Está además escrito en
`DESPLIEGUE.md`, sección de la tabla de activación.)

**No toques** `DBHOST`, `DBNAME`, `DBPORT` — los comparten `motor` y
`motor-reloj`. **No toques** `MOTOR_DBUSER` ni `MOTOR_DBPASSWORD`.

### Paso 3 — decidir las migraciones, en la misma edición

```
MIGRATOR_DBUSER=crm_migrator.<mismo sufijo>
MIGRATOR_DBPASSWORD=<la de b8_crm_migrator_clave.txt>
```

`[RECOMENDADO, y es tu decisión]` Sin esto, `entrypoint.sh` migra con `DBUSER`
— o sea con `crm_user`, que **no es dueño de ninguna tabla**. La próxima
migración que active RLS fallaría con `must be owner of table` **a mitad de
camino**. Está medido y documentado.

Con las variables puestas, el `verificar_credenciales` del arranque lo comprueba
**contra la base** antes de migrar, y aborta con el motivo escrito en vez de
reventar a medias.

### Paso 4 — Redeploy

**Redeploy / Recreate**, no *Save*. Si sale **`UNAUTHORIZED` en rojo**, la
sesión de Dokploy caducó y **no se guardó**: recargar, entrar y repetir.

### Paso 5 — verificar los tres servicios, no el primero que responda

Es la lección del 18/08 escrita con todas las letras. `backend`,
`celery-worker` y `celery-beat`. Y avisame para medir la identidad efectiva
desde la base.

### Rollback

Volver `DBUSER`/`DBPASSWORD` a los valores de `postgres` y redesplegar. Sin
`DROP`, sin datos que deshacer. Guardá los valores actuales **antes** de
sobrescribirlos.

---

# RESUMEN

| Pregunta | Respuesta |
|---|---|
| Contenedor del runtime | `<proyecto>-backend-1` (sin `container_name`; se identifica con `docker ps`) |
| Servicio del compose | **`backend`**, más `celery-worker` y `celery-beat` |
| Mecanismo de las variables | **`environment:`** en los tres. Sin `env_file`, sin `secrets:` |
| `DBUSER`/`DBPASSWORD`/`DBHOST`/`DBNAME`/`DBPORT` | **PRESENTES**, todas obligatorias (`:?`) |
| ¿Cambio persistente desde la terminal? | **NO.** Solo desde Environment + Redeploy |
| ¿Para qué sirve la terminal? | **Verificar** — §6, todo de solo lectura |
| Alcance del cambio | `backend`, `celery-worker`, `celery-beat`. **Una sola edición** |
| Riesgo conocido | El corte del 18/08 dejó un hueco de datos por no verificar el motor. **Hoy el motor tiene identidad propia**: esa vía está cerrada |

---

**No se cambió `DBUSER`. No se hizo redeploy. No se hizo commit. No se usó `git
stash`. No se hicieron `export` temporales ni `docker exec` modificando
archivos. Ningún valor secreto impreso.**
