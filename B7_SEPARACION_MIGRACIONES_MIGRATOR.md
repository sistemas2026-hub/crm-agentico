# B-7 — SEPARACIÓN RUNTIME / MIGRACIONES

Fecha: 2026-09-19

```
MECANISMO                    PASS   (probado de punta a punta en el aislado)
CAMBIO DE CODIGO NECESARIO   NINGUNO
SEPARACION EN PRODUCCION     SIN EFECTO  <- no esta desplegada
```

**No se hizo ningún despliegue. No se ejecutó ninguna migración de producción. No
se cambió `DBUSER`, ni `MOTOR_DBUSER`, ni RLS, ni propiedad, ni un solo
privilegio. No se hizo commit.**

---

## El diagnóstico en una línea

El mecanismo está escrito y funciona. **No está en git**, así que Dokploy nunca lo
ha desplegado — y las variables `MIGRATOR_*` que el colaborador cargó en el
Environment **ni siquiera llegan al contenedor**, porque el
`docker-compose.prod.yml` desplegado no las declara.

No es un fallo de lógica. Es el repositorio declarando algo que producción no
tiene — la misma clase de problema que CLAUDE.md documenta en «Lo que se verifica
no es lo que está desplegado».

---

## 1. Por qué `migrate` corrió como `crm_user`

`git show HEAD:django-crm/docker/backend/entrypoint.sh` — lo que de verdad se
ejecutó a las 22:21:

```sh
echo "Running migrations..."
python manage.py migrate --noinput
```

Sin rama `if`. Sin override de `DBUSER`. Sin `verificar_credenciales`. `migrate`
usó la única credencial que el contenedor tiene, que es la de tráfico:
`DBUSER=crm_user`.

Medido, no supuesto:

| Dónde | `MIGRATOR` en `entrypoint.sh` | `MIGRATOR` en `docker-compose.prod.yml` |
|---|---|---|
| `origin/fix/integracion-wisphub` (lo que Dokploy clona, `601d8be`) | **0 apariciones** | **0 apariciones** |
| `HEAD` local | **0 apariciones** | **0 apariciones** |
| disco (sin commitear) | 5 | 2 |

Esto explica además las dos anomalías que quedaron abiertas en el informe
anterior:

- **`select current_user, session_user` no tiene ninguna entrada nueva de hoy en
  `pg_stat_statements`.** Es la consulta que ejecuta `verificar_credenciales
  --con-base`, y ese comando **no existe en el entrypoint desplegado**. No se
  degradó: nunca se ejecutó.
- **El contenedor completó el arranque** (`create_default_admin` 22:22:15, beat
  22:25:01) pese a `set -e`. Porque no había ninguna comprobación que pudiera
  fallar.

### Y las variables de Dokploy tampoco llegaban

Aunque el entrypoint hubiera estado desplegado, el compose de `HEAD` no tiene las
dos líneas que inyectan las variables al servicio. Una variable en el Environment
de Dokploy que el compose no declara **no entra al contenedor**. Hacían falta las
dos cosas, y no estaba ninguna.

---

## 2. Archivos y líneas

### Dónde se decide el usuario de conexión de `migrate`

| Archivo | Líneas | Qué decide |
|---|---|---|
| [django-crm/backend/crm/settings.py](django-crm/backend/crm/settings.py#L161-L162) | 161–162 | `"USER": os.environ.get("DBUSER", ...)`. **Única** fuente del usuario: Django lee la variable de entorno del proceso |
| [django-crm/docker/backend/entrypoint.sh](django-crm/docker/backend/entrypoint.sh#L53-L72) | 53–72 | La rama que decide con qué credencial arranca `migrate` |
| [django-crm/docker/backend/entrypoint.sh](django-crm/docker/backend/entrypoint.sh#L58-L61) | 58, 60 | El override, como prefijo por proceso: `DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" python manage.py …` |
| [docker-compose.prod.yml](docker-compose.prod.yml#L123-L124) | 123–124 | `MIGRATOR_DBUSER` / `MIGRATOR_DBPASSWORD` — sólo en `backend`, opcionales (`:-`) |
| [docker-compose.prod.yml](docker-compose.prod.yml#L143-L145) | 143, 145 | `command: /bin/bash /entrypoint.sh` y el **montaje** del script |

### Hipótesis descartadas por medición

| Hipótesis | Cómo se descartó |
|---|---|
| `load_dotenv()` en `settings.py:12` pisa las variables | `.dockerignore` líneas 32–35 excluyen `.env*`; `backend/.env` no existe; y `load_dotenv()` sin `override=True` **no** pisa variables ya presentes |
| `MIGRATOR_DBPASSWORD` vacía | Prueba D: sale por `[ERROR A]` con exit 1. Con `set -e` el contenedor no arranca |
| La rama `else` corrió y se degradó a aviso | Prueba C: sale con `[ERROR A]` y exit 1. Con `set -e` el contenedor no arranca |

Ninguna de las tres sobrevive a `set -e`
([entrypoint.sh:2](django-crm/docker/backend/entrypoint.sh#L2)), y el contenedor
**sí** completó el arranque. Sólo queda una causa posible, y es la medida.

---

## 3. El cambio mínimo: **cero líneas de código**

El código ya está escrito y probado. Lo que falta es llevarlo a git. Son cuatro
archivos, ninguno más:

| Archivo | Estado | Por qué es imprescindible |
|---|---|---|
| `django-crm/docker/backend/entrypoint.sh` | `M` | La rama que hace el override |
| `docker-compose.prod.yml` | `M` | Sin las 2 líneas, las variables de Dokploy no entran al contenedor |
| `django-crm/backend/common/management/commands/verificar_credenciales.py` | `??` (66 líneas) | El entrypoint lo invoca. **Sin él, `set -e` + «Unknown command» = el backend no arranca** |
| `django-crm/backend/common/credenciales.py` | `??` (333 líneas) | Lo importa el comando anterior |

Dependencias comprobadas: `credenciales.py` importa sólo `dataclasses`;
`verificar_credenciales.py` importa `os`, Django y `common.credenciales`. Los dos
`__init__.py` de `management/commands/` ya están en git. **No arrastra nada más.**

### Y un quinto, recomendado: la guarda

`tests/test_entrypoint_credenciales.py` también está sin seguimiento, y corre en
verde hoy (`0 fallas`). No hace falta para que el mecanismo funcione, pero es lo
que impide que alguien deshaga la separación sin darse cuenta. Afirma sobre el
**efecto**, no sobre el texto del script — su propio comentario (línea 257) anota
que la primera versión escaneaba el texto y que eso no probaba nada:

```
[ok]  la credencial de trafico NUNCA aparece en un 'migrate'
[ok]  y el proceso que queda sirviendo es el de trafico
       -> arranque='gunicorn: crm_user.05b5a4b4'
```

Commitearlo con los otros cuatro no cambia nada en producción: es un archivo de
pruebas, no entra en ninguna ruta de ejecución.

> **`entrypoint.sh` se monta como volumen**
> ([compose:145](docker-compose.prod.yml#L145)), no va en la imagen. Pero los dos
> `.py` sí entran por `COPY backend/ .`
> ([Dockerfile:31](django-crm/Dockerfile#L31)). El despliegue tiene que ser
> **Rebuild**, no un restart.

### Lo que NO debe entrar

`git status` muestra 8 migraciones y la app `operaciones/` sin seguimiento. **No
pueden ir en el mismo commit**: cambiarían el esquema de producción, que no es lo
que este bloque autoriza.

---

## 4. Pruebas realizadas

Entorno aislado: `pg-b7` (PostgreSQL 16) + imagen construida desde **`HEAD` + los
4 archivos**, nada más — no desde el árbol de trabajo. Red `net-b7`.

### A. El mecanismo, con credenciales correctas

```
1. sin override         : session_user=crm_user      current_user=crm_user
2. con el override      : session_user=crm_migrator  current_user=crm_owner
3. despues del override : session_user=crm_user      current_user=crm_user
4. rama elegida         : IF  ("Running migrations as crm_migrator")
5. verificar_credenciales --con-base : sin problemas, exit 0
6. migrate                           : exit 0
```

El punto 3 es el que importa: el override es **por proceso**. La variable del
contenedor no cambia, así que el servidor web sigue levantando con la de tráfico.
Es la diferencia entre *separar* credenciales y *cambiarlas*.

### B, C, D. Desarmes — una prueba que sólo ve el camino feliz no prueba nada

| Desarme | Resultado | Qué prueba |
|---|---|---|
| **B.** `MIGRATOR_DBPASSWORD` incorrecta | `migrate` exit **1**: `password authentication failed for user "crm_migrator"` | El override **se usa de verdad**. Si `migrate` hubiera pasado, estaría conectando con otra credencial |
| **C.** `MIGRATOR_DBUSER` vacía | rama ELSE, exit **1**: `[ERROR A] El rol efectivo 'crm_user' no puede actuar como dueno de 135 tabla(s)` | La rama sin credencial propia falla en el arranque, no a mitad de una migración |
| **D.** usuario presente, clave vacía | exit **1**: `[ERROR A] MIGRATOR_DBUSER esta definida pero MIGRATOR_DBPASSWORD no` | El caso medio roto se detecta como tal, y no como un fallo que apunte a otra causa |

Los tres son fail-closed y los tres matan el contenedor con `set -e`.

### E. Arranque completo, medido desde el lado de la base

Instrumento: `log_statement='all'` + `log_line_prefix='ROL[%u] '` en `pg-b7`, que
atribuye **cada sentencia a su rol**.

> **El instrumento se probó antes de confiar en sus cifras.** El primer intento
> devolvió cero — no porque no hubiera actividad, sino porque el `ALTER SYSTEM`
> había fallado (`postgres` no existe en `pg-b7`; el superusuario es `admin`, y
> psql envuelve varios `-c` en una transacción, donde `ALTER SYSTEM` no corre).
> Un canario con los tres roles confirmó que dispara antes de dar por buena
> ninguna lectura.

Log del arranque real:

```
Checking traffic credentials...
credenciales (trafico): sin problemas.
Running migrations as crm_migrator (separate credential)...   <- la linea decisiva
credenciales (migraciones): sin problemas.
Running migrations:
  No migrations to apply.
Creating default admin user (if needed)...
```

Y lo que vio PostgreSQL en ese mismo arranque:

| Rol | Sentencias | Qué ejecutó |
|---|---|---|
| `crm_migrator` | **84** | `verificar_credenciales --con-base` + todo `migrate` |
| `crm_user` | **4** | `create_default_admin` (SELECT + INSERT en `users`) y el arranque del servidor web |

Un solo contenedor, dos identidades, cada una en su sitio.

### F. El flujo completo

| Componente | Credencial | Verificado |
|---|---|---|
| backend (servidor web) | `DBUSER` → **`crm_user`** | Log de `pg-b7`: 4 sentencias como `crm_user` |
| celery-worker / celery-beat | `DBUSER` → **`crm_user`** | Compose 177–178, 222–223; `command: celery …` — **no corren `entrypoint.sh`, no migran** |
| migraciones | `MIGRATOR_DBUSER` → **`crm_migrator` → `crm_owner`** | `session_user=crm_migrator current_user=crm_owner`; puede ejercer el rol dueño de **135/135** tablas |
| motor / motor-reloj | `MOTOR_DBUSER` → **`motor_user`** | Compose 307–308, 406–407. Sin `MIGRATOR_*`, sin `entrypoint.sh` |

### G. Secretos

```
literales de credencial en los 4 archivos      : 0
claves de b8_*.txt en archivos del repositorio : 0
claves de b8_*.txt en el historial de git      : 0
clave en el log del backend                    : 0 apariciones
clave en el log de PostgreSQL                  : 0 apariciones
```

Lo único que el entrypoint imprime del usuario de migración es
`${MIGRATOR_DBUSER%%.*}` — recortado en el punto. Comprobado con un valor con
sufijo de pooler: `crm_migrator.abcdef…6789` se imprime como `crm_migrator`. **El
sufijo de Supavisor no sale por consola.**

---

## 5. Producción, leída en solo lectura

```
solo lectura verificada en el servidor : on
tablas en public                       : 135      ok
roles                                  : 41       ok
FORCE RLS                              : 66       ok
migraciones aplicadas                  : 192
```

**Migraciones que `migrate` aplicaría al desplegar el cambio mínimo: 0.** El
despliegue no ejecutaría ningún DDL — el riesgo es el de un rebuild, no el de una
migración.

### `[HALLAZGO]` Producción va por delante del repositorio

Cuatro migraciones **del proyecto** están aplicadas en producción y no existen en
git:

```
campo.0003_alter_asignaciontrabajo_rol
common.0039_alter_activity_entity_type
operaciones.0001_initial
operaciones.0002_rls_operaciones
```

(Las otras 32 diferencias son de `auth`, `contenttypes`, `sessions`,
`token_blacklist` y `django_ses`, que viven en las librerías y no en el árbol del
proyecto — ruido esperado del método de conteo, no un hallazgo.)

No lo introduje yo y no lo toqué. Queda reportado: la base tiene estructura que el
código desplegado no declara.

### `[HALLAZGO]` El arranque de producción está a una migración de romperse

Hoy `migrate` corre como `crm_user` y no falla **sólo porque no hay nada
pendiente**. La primera migración que alguien commitee sin este cambio intentará
un `ALTER TABLE` sobre una tabla de `crm_owner`, dará `must be owner of table`, y
con `set -e` el backend **no arrancará**. Es exactamente lo que predice el
comentario del propio entrypoint, escrito antes de que `DBUSER` fuera `crm_user`.

---

## CRITERIO DE SALIDA

| # | Criterio | Resultado |
|---|---|---|
| 1 | Identificar dónde se decide el usuario de `migrate` | **PASS** — 5 puntos, con archivo y línea |
| 2 | Determinar por qué corre como `crm_user` | **PASS** — no está en git; medido en HEAD y en el remoto |
| 3 | Cambio mínimo propuesto | **PASS** — 0 líneas de código; 4 archivos a git |
| 4 | Probado primero en entorno aislado | **PASS** — imagen desde HEAD + los 4 archivos |
| 5 | runtime → `crm_user` | **PASS** — 4 sentencias como `crm_user` en el log del servidor |
| 6 | migraciones → `crm_migrator` → `crm_owner` | **PASS** — 84 sentencias; 135/135 tablas |
| 7 | motor → `motor_user` | **PASS** — compose 307–308, 406–407, sin cambios |
| 8 | Sin secretos en código, git, logs ni consola | **PASS** — 0 en las cinco comprobaciones |
| 9 | Sin cambios de permisos, RLS ni `BYPASSRLS` | **PASS** — no se ejecutó ninguno |
| 10 | Sin despliegue de producción | **PASS** — ninguno |

### **PASS** del mecanismo

Y, dicho expresamente: **la separación runtime/migraciones NO está en efecto en
producción y no lo estará hasta que se despliegue.** Hoy las migraciones siguen
corriendo como `crm_user`. **B-7 sigue siendo PARCIAL**, sin cambios respecto de
`B7_DECISION_NO_ROTAR.md` en el camino indirecto de `service_role`.

---

## Lo que queda pendiente de tu autorización

1. Commit de los 4 archivos, **y sólo esos 4** (excluyendo las 8 migraciones y
   `operaciones/` sin seguimiento).
2. `git push` a `fix/integracion-wisphub`.
3. En Dokploy: **Rebuild** (no Restart — los dos `.py` van dentro de la imagen).
4. Verificar en el log del arranque la línea `Running migrations as crm_migrator
   (separate credential)...` y, desde PostgreSQL, que el rol que ejecutó `migrate`
   fue `crm_migrator`.

No he hecho nada de esto.
