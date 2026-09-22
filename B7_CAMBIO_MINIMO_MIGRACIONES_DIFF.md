# B-7 — CAMBIO MÍNIMO DE SEPARACIÓN DE MIGRACIONES

Fecha: 2026-09-19 · **Preparado, sin commit**

```
DIFF REVISADO          SI
CONFIRMACIONES         9 de 9   PASS
PRUEBAS                40 pasan, 0 fallan
COMMIT / PUSH / DEPLOY NO EJECUTADOS
```

**No se hizo commit. No se hizo push. No se hizo despliegue. No se ejecutó
ninguna migración. No se tocó producción.**

---

## 1. Archivos afectados

| # | Archivo | Estado | Líneas del cambio |
|---|---|---|---|
| 1 | [django-crm/docker/backend/entrypoint.sh](django-crm/docker/backend/entrypoint.sh) | `M` | +37 −2 |
| 2 | [docker-compose.prod.yml](docker-compose.prod.yml) | `M` | +11 −0 |
| 3 | [django-crm/backend/common/management/commands/verificar_credenciales.py](django-crm/backend/common/management/commands/verificar_credenciales.py) | nuevo | 66 |
| 4 | [django-crm/backend/common/credenciales.py](django-crm/backend/common/credenciales.py) | nuevo | 333 |

Total: **+447 −2**, de las cuales 399 son los dos archivos nuevos.

Los cuatro están presentes en disco y **ninguno está ignorado por
`.gitignore`** — comprobado con `git check-ignore`, porque un archivo ignorado no
hace fallar a `git add`: simplemente no se añade, y el commit saldría incompleto
sin avisar.

---

## 2. El diff

### 2.1 `django-crm/docker/backend/entrypoint.sh`

```diff
@@ -33,8 +33,43 @@
     echo ""
 fi
 
-echo "Running migrations..."
-python manage.py migrate --noinput
+# =============================================================================
+#  CREDENCIALES  --  quien sirve y quien migra no son el mismo
+# =============================================================================
+# Hasta la Etapa B.4, 'migrate' corria con las MISMAS credenciales con las que
+# gunicorn sirve las peticiones. Mientras esas credenciales fueron las de
+# 'postgres' no se noto: es dueno de las 129 tablas y puede con todo. El dia que
+# el CRM se corte a 'crm_user' -que no es dueno de ninguna- la primera migracion
+# que necesite 'ALTER TABLE ... ENABLE ROW LEVEL SECURITY' falla con 'must be
+# owner of table'. Medido contra PostgreSQL 17 en la Etapa B.3.
+#
+# MIGRATOR_DBUSER/MIGRATOR_DBPASSWORD son OPCIONALES a proposito: sin ellas esto
+# se comporta exactamente como antes. Asi el archivo se puede desplegar sin
+# haber creado todavia ningun rol nuevo.
+
+echo "Checking traffic credentials..."
+python manage.py verificar_credenciales --proposito trafico
+
+if [ -n "${MIGRATOR_DBUSER:-}" ]; then
+    echo "Running migrations as ${MIGRATOR_DBUSER%%.*} (separate credential)..."
+    # El override vale SOLO para estos dos procesos. La variable del contenedor
+    # no cambia, asi que gunicorn -mas abajo- sigue levantando con la de
+    # trafico. Es la diferencia entre separar las credenciales y cambiarlas.
+    DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" \
+        python manage.py verificar_credenciales --proposito migraciones --con-base
+    DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" \
+        python manage.py migrate --noinput
+else
+    echo "Running migrations with DBUSER (no separate migration credential)..."
+    # Sin credencial propia, se migra con la de siempre -- pero se comprueba
+    # igual, y CONTRA LA BASE: lo que decide si esta credencial sirve para
+    # migrar no es como se llama, sino de cuantas tablas puede ejercer el rol
+    # dueno. En desarrollo crm_user las posee todas y esto pasa; en produccion
+    # no posee ninguna y esto falla aca, con el motivo escrito, en vez de a
+    # mitad de una migracion con 'must be owner of table'.
+    python manage.py verificar_credenciales --proposito migraciones --con-base
+    python manage.py migrate --noinput
+fi
 
 echo "Creating default admin user (if needed)..."
 python manage.py create_default_admin
```

### 2.2 `docker-compose.prod.yml`

```diff
@@ -111,6 +111,17 @@ services:
       DBNAME: ${DBNAME:?}
       DBUSER: ${DBUSER:?}
       DBPASSWORD: ${DBPASSWORD:?}
+      # --- Migraciones: credencial APARTE de la de trafico ---
+      # Este es el UNICO servicio que corre 'entrypoint.sh' (los dos celery
+      # arrancan 'celery' directo), asi que es el unico que migra y el unico que
+      # necesita esto. Ponerlo en celery-* no haria nada salvo repartir una
+      # credencial con permiso de DDL por donde no hace falta.
+      #
+      # OPCIONALES a proposito ('-' y no ':?'): sin ellas el entrypoint migra
+      # como siempre, con ${DBUSER}. Asi este archivo se puede desplegar antes
+      # de que exista el rol. Ver DESPLIEGUE.md, "Credencial de migraciones".
+      MIGRATOR_DBUSER: ${MIGRATOR_DBUSER:-}
+      MIGRATOR_DBPASSWORD: ${MIGRATOR_DBPASSWORD:-}
       # --- Celery ---
       CELERY_BROKER_URL: redis://redis:6379/0
       CELERY_RESULT_BACKEND: redis://redis:6379/0
```

**Un solo hunk, de 11 líneas, todas dentro del servicio `backend`.**

### 2.3 y 2.4 — los dos archivos nuevos

Se mostraron íntegros en la conversación (66 y 333 líneas). Resumen de lo que
contienen:

- **`verificar_credenciales.py`** (66 líneas) — envoltura de Django. Lee
  `os.environ`, delega en `common.credenciales`, y sale con **código 1** si hay
  un problema de gravedad `ERROR`. Eso es lo que, con `set -e`, impide que el
  arranque siga. **No ejecuta ningún SQL propio.**
- **`credenciales.py`** (333 líneas) — la lógica. No importa Django ni abre
  conexiones: las comprobaciones de entorno son aritmética de cadenas sobre un
  dict, y las que necesitan la base reciben un cursor ya abierto. Ejecuta
  **6 consultas, todas de lectura** (§3.4).

---

## 3. Las nueve confirmaciones

### 3.1 `DBUSER=crm_user` sigue siendo el runtime — **CONFIRMADO**

El diff **no añade ni quita ninguna línea que defina `DBUSER`**. Después del
cambio:

```
112:      DBUSER: ${DBUSER:?}          backend
177:      DBUSER: ${DBUSER:?}          celery-worker
222:      DBUSER: ${DBUSER:?}          celery-beat
307:      DBUSER: ${MOTOR_DBUSER:?}    motor
406:      DBUSER: ${MOTOR_DBUSER:?}    motor-reloj
```

La palabra `DBUSER` aparece dos veces en el diff del entrypoint, y en ninguna de
las dos define nada: una es el texto de un `echo`, la otra un comentario.

### 3.2 Alcance de `MIGRATOR_*` — **CONFIRMADO, con una precisión**

No es exacto decir «sólo para `migrate`». El override llega a **dos procesos**, y
los dos son el paso de migración:

| Línea | Proceso | Credencial |
|---|---|---|
| L51 | `verificar_credenciales --proposito trafico` | `DBUSER` del contenedor |
| **L58** | `verificar_credenciales --proposito migraciones --con-base` | **`MIGRATOR_DBUSER`** |
| **L60** | `migrate --noinput` | **`MIGRATOR_DBUSER`** |
| L70–71 | rama `else` (sin credencial separada) | `DBUSER` del contenedor |
| L75 | `create_default_admin` | `DBUSER` del contenedor |
| L78 | `collectstatic --noinput` | `DBUSER` del contenedor |
| L87 | **`exec gunicorn`** | `DBUSER` del contenedor |
| L95 | `exec runserver` | `DBUSER` del contenedor |

L58 es la comprobación **de esa misma credencial de migración**, justo antes de
usarla: sin ella, un `MIGRATOR_DBUSER` mal puesto fallaría a mitad de una
migración en vez de al arrancar. Ningún otro proceso lo recibe, y **gunicorn —el
que queda sirviendo— no lo recibe**.

`MIGRATOR_` aparece en 4 líneas del entrypoint entero: 53, 54, 58 y 60.

### 3.3 Motor y Motor-Reloj no cambian — **CONFIRMADO**

Mapeando cada línea modificada del diff al servicio que la contiene:

```
backend        lineas   44- 149   cambiadas: 114..124
celery-worker  lineas  150- 194   cambiadas: NINGUNA
celery-beat    lineas  195- 239   cambiadas: NINGUNA
frontend       lineas  240- 277   cambiadas: NINGUNA
motor          lineas  278- 383   cambiadas: NINGUNA
motor-reloj    lineas  384- 429   cambiadas: NINGUNA
redis          lineas   35-  43   cambiadas: NINGUNA
```

`motor` y `motor-reloj` conservan `DBUSER: ${MOTOR_DBUSER:?}` sin tocar, no
reciben `MIGRATOR_*`, y no ejecutan `entrypoint.sh`.

### 3.4 No se modifica RLS, ownership ni privilegios — **CONFIRMADO**

Extraído **por AST** desde las llamadas a `cursor.execute` — no por búsqueda de
texto, que es el error en el que este proyecto ya cayó tres veces:

```
credenciales.py -> 6 sentencias, TODAS de lectura:
  L232  select current_user, session_user
  L244  select count(*) from pg_class ... not pg_has_role(current_user, c.relowner, 'USAGE')
  L281  select has_schema_privilege(%s, 'asistente', 'usage')
  L294  select count(*) from pg_class ... pg_get_userbyid(c.relowner) = %s
  L312  select 1 from pg_roles where rolname = %s
  L317  select 1 from pg_namespace where nspname = %s

verificar_credenciales.py -> 0 sentencias
```

**Cero DDL. Cero escrituras.** El módulo sólo consulta catálogos de PostgreSQL.

> Las cadenas `REVOKE USAGE ON SCHEMA asistente FROM crm_user` y
> `ALTER ROLE crm_migrator ... SET role = crm_owner` que aparecen en el archivo
> son **texto de los mensajes de remedio** — lo que el operador lee para saber
> qué hacer. Nunca se ejecutan: no están en ninguna de las 6 sentencias de
> arriba.

### 3.5 No se ejecuta ninguna migración nueva — **CONFIRMADO**

```
EN HEAD PERO NO APLICADAS EN PRODUCCION: 0
   (ninguna -- 'migrate' no ejecutaria ningun DDL)
```

Comparadas una a una las 156 migraciones de `HEAD` contra las 192 filas de
`django_migrations` en producción, leyendo con `transaction_read_only = on`
verificado en el servidor.

Y ninguno de los 4 archivos del commit está en un directorio `migrations/`.

### 3.6 No hay secretos — **CONFIRMADO**

Cuatro detectores sobre los 4 archivos:

```
clave/secreto asignado a literal : 0
cadena tipo JWT                  : 0
verificador SCRAM-SHA-256        : 0
URI con credencial embebida      : 0
                         TOTAL   : 0
```

**Los cuatro se probaron contra un cebo antes de dar por bueno el cero.** El
primer cebo no contenía un verificador SCRAM, así que ese detector quedaba sin
probar; se repitió con `SCRAM-SHA-256$4096:...` y disparó. Los cuatro disparan.

Y en git:

```
claves de b8_*.txt en archivos del repositorio : 0
claves de b8_*.txt en el historial de git      : 0
.env                                           : ignorado (.gitignore:2)
```

En consola, lo único que el entrypoint imprime del usuario de migración es
`${MIGRATOR_DBUSER%%.*}` — recortado en el punto, así que el sufijo de Supavisor
no sale. Comprobado: `crm_migrator.abcdef…6789` se imprime como `crm_migrator`.
Las contraseñas no se imprimen nunca: 0 apariciones en el log del backend y 0 en
el de PostgreSQL durante el arranque completo.

### 3.7 Requiere **Rebuild**, no Restart — **CONFIRMADO**

| Archivo | Cómo entra al contenedor | Qué exige |
|---|---|---|
| `entrypoint.sh` | montado como volumen ([compose:145](docker-compose.prod.yml#L145)) | basta el `git pull` de Dokploy |
| `docker-compose.prod.yml` | lo lee el orquestador | basta el `git pull` de Dokploy |
| `credenciales.py` | `COPY backend/ .` ([Dockerfile:31](django-crm/Dockerfile#L31)) | **REBUILD** |
| `verificar_credenciales.py` | `COPY backend/ .` | **REBUILD** |

**Por qué importa:** un Restart reutiliza la imagen actual. El entrypoint nuevo
—que sí se actualiza, por ser un volumen— invocaría `verificar_credenciales`, que
no existiría en esa imagen. Con `set -e`, «Unknown command» y **el backend no
arranca**. Restart no es una versión más suave de este despliegue: es la forma de
romperlo.

### 3.8 El entrypoint no invoca nada inexistente — **CONFIRMADO**

Extraídos del script los 5 comandos que invoca, y resuelto cada uno:

```
collectstatic           integrado en Django
migrate                 integrado en Django
runserver               integrado en Django   (verificado en la imagen:
                        django/core/management/commands/runserver.py)
create_default_admin    propio del proyecto   disco=SI  git=SI
verificar_credenciales  propio del proyecto   disco=SI  git=NO -> va en este commit
```

`runserver` apareció como «no encontrado» en mi primera lista por una omisión
mía, no del script: no estaba en mi conjunto de comandos integrados. Verificado
después dentro de la imagen.

**El único comando que hoy no está en git es `verificar_credenciales`, y es
exactamente el archivo 3 de este commit.** Su import (`common.credenciales`) es
el archivo 4. Las dependencias cierran.

### 3.9 Los 4 archivos presentes — **CONFIRMADO**

```
entrypoint.sh                OK   96 lineas
docker-compose.prod.yml      OK  462 lineas
verificar_credenciales.py    OK   66 lineas
credenciales.py              OK  333 lineas
```

---

## 4. Pruebas realizadas

Todas en el entorno aislado (`pg-b7`, `runner-b7`). **Producción no se tocó.**

| Prueba | Resultado |
|---|---|
| `common/tests/test_credenciales.py` — la lógica, sin base | **28 pasan** |
| `common/tests/test_credenciales_postgres.py` — contra PostgreSQL real | **10 pasan** |
| `tests/test_entrypoint_credenciales.py` — la guarda del efecto | **0 fallas** |
| `tests/test_nucleo_sin_tenants.py` — arquitectura | **OK** |

```
40 pruebas, 0 fallas
```

Las dos primeras fallaban al principio con `django.db.utils.OperationalError`.
No era el código: era pytest-django intentando `CREATE DATABASE "test_crmdb"` con
`crm_user`, que no tiene `CREATEDB`. Corridas con el superusuario del aislado,
pasan. (Antes de eso, un intento con `-c /dev/null` había roto la configuración de
pytest-django y producido 28 errores que tampoco eran del código — anotado para
que nadie lo lea como un fallo real.)

A esto se suma lo ya medido en
[B7_SEPARACION_MIGRACIONES_MIGRATOR.md](B7_SEPARACION_MIGRACIONES_MIGRATOR.md):
arranque completo con la imagen construida desde `HEAD` + estos 4 archivos,
`crm_migrator` con 84 sentencias y `crm_user` con 4 en el mismo arranque, y los
tres desarmes (clave incorrecta, usuario vacío, clave vacía) fallando cerrado.

> **Efecto colateral del aislado, declarado:** para correr las pruebas copié los
> tres archivos al contenedor `runner-b7` con `docker cp`. Es un contenedor
> descartable del entorno de pruebas, no producción y no el repositorio.

---

## 5. Lo que este commit **no** lleva

`git status` tiene 8 migraciones y la app `operaciones/` sin seguimiento. **No
entran**: cambiarían el esquema de producción.

Tampoco entran, y conviene decidirlo aparte:

| Archivo | Qué es |
|---|---|
| `tests/test_entrypoint_credenciales.py` | La guarda que afirma sobre el **efecto** del entrypoint |
| `django-crm/backend/common/tests/test_credenciales.py` | Las 28 pruebas de lógica |
| `django-crm/backend/common/tests/test_credenciales_postgres.py` | Las 10 contra base real |

Son las 40 pruebas que acaban de pasar. Si se commitean sólo los 4 archivos, el
mecanismo queda desplegado **sin ninguna guarda en el repositorio**: nadie se
enteraría si alguien deshace la separación más adelante. No los añadí por mi
cuenta porque el bloque pide cuatro archivos; queda como recomendación.

---

## CONCLUSIÓN

| # | Confirmación pedida | Resultado |
|---|---|---|
| 1 | `DBUSER=crm_user` sigue siendo el runtime | **PASS** |
| 2 | `MIGRATOR_*` sólo para el paso de migración | **PASS** (2 procesos, ambos del paso de migración) |
| 3 | Motor / Motor-Reloj no cambian | **PASS** — 0 líneas tocadas |
| 4 | No se modifica RLS, ownership ni privilegios | **PASS** — 6 SELECT, 0 DDL, por AST |
| 5 | No se ejecuta ninguna migración nueva | **PASS** — 0 pendientes |
| 6 | Sin secretos en git, código, logs ni diff | **PASS** — 0 con 4 detectores probados |
| 7 | Requiere Rebuild y no sólo Restart | **PASS** — confirmado, con el porqué |
| 8 | El entrypoint no invoca archivos inexistentes | **PASS** — 5 comandos, los 5 resuelven |
| 9 | Los 4 archivos presentes | **PASS** |

### **PASS** — el cambio está listo para commit

Sigue sin estar desplegado. **B-7 continúa siendo PARCIAL**, y la separación
runtime/migraciones seguirá sin efecto en producción hasta el Rebuild.

**No se hizo commit, ni push, ni despliegue.** Esperan tu autorización.
