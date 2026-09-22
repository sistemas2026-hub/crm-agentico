# B-7 — VERIFICACIÓN DEL RUNTIME TRAS EL REDEPLOY

Fecha: 2026-09-19 · Medido entre 22:21 y 22:30 UTC

# EL CAMBIO `postgres` → `crm_user` QUEDÓ **EFECTIVO**

Confirmado explícitamente. Con dos salvedades que hay que leer: el **motor no
pudo verificarse** (§2) y la **separación de migraciones no está en efecto**
(§3).

Solo lectura. Sin migraciones, sin cambios, sin commit.

---

# 1. BACKEND, WORKER Y BEAT → `crm_user`: **PASS**

## Por qué la primera foto no servía

`pg_stat_activity` mostraba **cero** conexiones de la plataforma. No es un
fallo: Django corre con `CONN_MAX_AGE=0` y cierra la conexión al terminar cada
petición. Sin tráfico, no hay nada conectado. **La ausencia no prueba nada**, así
que busqué evidencia histórica en `pg_stat_statements`, que en PostgreSQL 17
trae `stats_since` — cuándo apareció cada sentencia.

## La secuencia de arranque, con hora y usuario

Todo esto está registrado **bajo `crm_user`**:

```
22:21:55   SELECT c.relname, CASE WHEN c.relispartition ...    introspeccion de migrate
22:21:55   SELECT "django_migrations"."id", "app", ...          migrate leyendo lo aplicado
22:21:56   SELECT "django_content_type"."model" ... (38 llamadas)
22:21:57   SELECT "django_content_type"... / "auth_permission"...  sincronizacion post-migrate
22:22:15   SELECT $1 AS "a" FROM "users" WHERE "users"."is_superuser"   create_default_admin
22:25:01   SELECT DISTINCT "escalation_policy"."org_id" ...      scan_for_breached_cases
```

Las tres primeras son `migrate`. La de las 22:22:15 es **`create_default_admin`**,
que `entrypoint.sh` ejecuta justo después. La de las 22:25:01 es
**`scan_for_breached_cases`**, la tarea que `celery-beat` programa **cada 5
minutos** y que ejecuta el **worker**.

O sea: el contenedor arrancó, corrió su secuencia completa y **celery-beat y
celery-worker también están operando como `crm_user`**. Beat no consulta la base
por su cuenta —usa el `beat_schedule` estático de `crm/celery.py`, no
`django_celery_beat`—, así que su prueba es indirecta pero firme: si beat no
estuviera vivo, esa tarea no se habría disparado.

## Conexiones vivas, capturadas

Muestreo de 7 minutos, cada 4 segundos:

```
[22:22:32] crm_user      pid=444422   app=Supavisor   edad=35s
[22:25:03] crm_user      pid=444651   app=Supavisor   edad=1s
```

## Y la otra mitad: `postgres` ya no es el runtime

**Ninguna sentencia nueva del ORM bajo `postgres` después del redeploy.** Las
únicas entradas nuevas de `postgres` son las de mis propias consultas de
verificación — esta máquina se conecta con esa identidad.

Antes del cambio, las consultas del ORM estaban **todas** bajo `postgres` (211
sentencias, 50.319 llamadas). Después, las nuevas están bajo `crm_user`.

## Y el estado del rol

```
crm_user  bypassrls = False
crm_user  CREATE en public = False
```

---

# 2. MOTOR Y MOTOR-RELOJ: **NO VERIFICADO**

**No es FAIL. Es que no puedo probarlo, y prefiero decirlo.**

Lo medido:

```
motor_user: ultima sentencia registrada       02:16 de hoy
motor_user: sentencias nuevas tras el redeploy  NINGUNA
muestreo de 7 minutos: conexiones de motor_user  NINGUNA
asistente.conversations  ultima escritura  01:53
asistente.messages       ultima escritura  02:15
asistente.tool_calls     ultima escritura  01:58
```

**Por qué eso no alcanza para concluir nada.** El motor escribe **cuando atiende
una conversación**. Si no entró un mensaje de WhatsApp desde las 02:15, un motor
perfectamente sano no deja ninguna huella. Y las tablas del scheduler
persistente (`asistente.job_run`, `job_attempt`, `job_schedule_state`) están
**todas en 0**, que es su estado conocido — ese mecanismo está inerte, así que
tampoco sirve de señal.

Lo que **sí** está verificado, y es lo que importa para el riesgo del 18/08:

```
motor       linea 307  DBUSER: ${MOTOR_DBUSER:?}
motor       linea 308  DBPASSWORD: ${MOTOR_DBPASSWORD:?}
motor-reloj linea 406  DBUSER: ${MOTOR_DBUSER:?}
motor-reloj linea 407  DBPASSWORD: ${MOTOR_DBPASSWORD:?}
```

**El motor no lee `${DBUSER}`.** Estructuralmente no puede haber heredado el
cambio. El incidente del 18/08 —cuando compartían variable y el motor quedó sin
privilegios sobre el esquema `asistente`— **no puede repetirse por esa vía**.

## `[OBSERVACIÓN]` Algo que conviene mirar, y que es ANTERIOR al redeploy

El importador de tickets de WispHub creó casos a las **14:02, 15:05 y 17:13** de
hoy. Después, nada — cinco horas sin un solo caso nuevo, y el redeploy fue a las
22:21.

Dos lecturas posibles y no puedo elegir entre ellas desde la base: **no entraron
tickets nuevos** (plausible), o **el reloj del motor no está corriendo**. Lo
anoto porque es anterior al cambio y no debería atribuirse a él.

## Cómo verificarlo de verdad

Desde el contenedor del motor, en la terminal de Dokploy:

```sh
python cli/reporte_huecos_documentacion.py
```

Es exactamente la prueba que faltó el 18/08 y que destapó aquel incidente. Si
corre limpio, el motor tiene su identidad y sus permisos. Si da
`permission denied for schema asistente`, hay que revertir.

**No alcanza con que el CRM cargue.** Es la lección literal que dejó escrita ese
incidente.

---

# 3. `crm_migrator`: **PASS** — pero la separación **NO está en efecto**

## El rol funciona

```
entra como = crm_migrator
actua como = crm_owner          (por ALTER ROLE ... SET role)
puede ejercer el rol dueno de 135/135 tablas
bypassrls = False   superuser = False
```

Es exactamente lo que necesita para `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`.

## `[HALLAZGO]` Pero las migraciones corrieron como `crm_user`

La consulta `SELECT "django_migrations"...` de las 22:21:55, junto con la
introspección `SELECT c.relname ... relispartition` —que es la que hace `migrate`
para ver qué tablas existen— están registradas **bajo `crm_user`**, no bajo
`crm_owner`.

Si `MIGRATOR_DBUSER` estuviera puesta, `entrypoint.sh` habría corrido `migrate`
con `crm_migrator`, que actúa como `crm_owner`, y esas consultas se habrían
atribuido a `crm_owner`.

Señal concordante: la consulta exacta que hace `verificar_credenciales
--con-base` (`select current_user, session_user`) **no tiene ninguna entrada de
hoy** bajo `crm_user` ni `crm_owner` — solo una de `autonomia_operador` del
18/09.

`[INCERTIDUMBRE, dicha]` La consulta a `django_migrations` **podría** venir de
otro comando de gestión y no de `migrate`. La introspección de `relispartition`
apunta claramente a `migrate`, pero no puedo separarlas del todo desde aquí. Lo
que sí es firme: **no hay ninguna traza de que las migraciones hayan corrido con
`crm_migrator`.**

## Por qué no rompió nada hoy

```
django_migrations : 192   (sin cambios)
ultima aplicada   : 2026-09-17 15:11
```

**No había ninguna migración pendiente.** `migrate` leyó la tabla, no encontró
nada que aplicar y siguió. El riesgo es futuro: la próxima migración que cree
una tabla y active RLS va a fallar con `must be owner of table` **a mitad de
camino**, porque `crm_user` no es dueño de ninguna.

## Qué falta

Agregar en el Environment de Dokploy, y redesplegar:

```
MIGRATOR_DBUSER=crm_migrator.<el mismo sufijo>
MIGRATOR_DBPASSWORD=<la de b8_crm_migrator_clave.txt>
```

Se comprueba igual que hoy: tras el próximo arranque, las consultas a
`django_migrations` deben aparecer bajo **`crm_owner`**, no bajo `crm_user`.

---

# 4. ERRORES DE AUTENTICACIÓN, PERMISOS O ARRANQUE: **NINGUNO OBSERVABLE**

Para el CRM, la evidencia es fuerte y es de efecto, no de ausencia: **la
secuencia de arranque se completó entera**. Un fallo de autenticación habría
dejado al contenedor en bucle de reinicio sin llegar nunca a `create_default_admin`
ni a las tareas de beat. Un fallo de permisos habría roto `migrate` o la
sincronización de `django_content_type` / `auth_permission`, que sí corrieron (38
llamadas).

`[LÍMITE]` **Un bucle de reinicio por credencial equivocada sería invisible
desde la base**: una autenticación fallida no crea backend y no aparece en
`pg_stat_activity`. Para el CRM eso queda descartado por lo de arriba. **Para el
motor, no**: ver §2.

---

# 5. CAMBIOS DE DATOS: **NINGUNO INESPERADO**

| | Valor | |
|---|---|---|
| tablas en `public` | **135** | ok |
| roles | **41** | ok |
| `django_migrations` | **192** | ok — ninguna migración aplicada |
| tablas con FORCE RLS | **66** | ok |
| `organization` | **2** | ok |
| `activity` con `entity_type` de operaciones | **0** | ok |
| kill switch | **detenido** | ok |
| tablas de Autonomía 2 | ausentes | ok |
| `crm_user` CREATE en public | **False** | ok |
| `crm_user` bypassrls | **False** | ok |

**Tablas vivas** (no son baseline fijo — crecen con el uso real):

```
case      215     ultimo alta 17:13  (importador de WispHub, provider='wisphub')
activity  622     ultima fila 17:13  (CREATE + ASSIGN del mismo caso)
```

Las dos últimas escrituras de negocio son **anteriores** al redeploy de las
22:21. Nada se creó ni se modificó durante el cambio.

---

# VEREDICTO

| Comprobación pedida | Resultado |
|---|---|
| `backend` conecta como `crm_user` | **PASS** — arranque completo registrado a las 22:21:55 |
| `celery-worker` como `crm_user` | **PASS** — `scan_for_breached_cases` a las 22:25:01 |
| `celery-beat` como `crm_user` | **PASS (indirecto)** — disparó esa tarea; no consulta la base por sí mismo |
| `motor` y `motor-reloj` con `motor_user` | **NO VERIFICADO** — sin actividad desde las 02:16. Estructuralmente separados (§2) |
| `crm_migrator` autentica y actúa como `crm_owner` | **PASS** — dueño de 135/135 |
| Sin errores de autenticación / permisos / arranque | **PASS para el CRM**; no observable para el motor |
| Sin cambios de datos inesperados | **PASS** |
| **¿`postgres` → `crm_user` quedó efectivo?** | **SÍ** |

## Lo que queda abierto

1. **`[PENDIENTE, VERIFICABLE YA]`** Correr
   `python cli/reporte_huecos_documentacion.py` en el contenedor del motor. Es la
   prueba que faltó el 18/08. Hasta hacerla, el motor está sin verificar.
2. **`[PENDIENTE]`** `MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD`: las migraciones
   corren hoy como `crm_user`. No rompe nada mientras no haya migraciones
   pendientes; rompe la primera que active RLS.
3. **`[OBSERVACIÓN]`** Cinco horas sin importar tickets, desde antes del
   redeploy. Puede ser normal.

## Y lo que sigue sin cerrarse, por decisión

**B-7 sigue siendo PARCIAL.** `app.settings.jwt_secret` continúa presente y
legible por `crm_user`; `service_role` conserva `BYPASSRLS`. El runtime ya no es
`postgres` —que es una mejora real y medida— pero **`crm_user` puede recuperar
`BYPASSRLS` con un `SELECT` y un HMAC**. No se puede afirmar que el aislamiento
por organización esté garantizado por la base.

---

**No se ejecutaron migraciones. No se hicieron cambios. No se hizo commit. No se
usó `git stash`. Todo se consultó con `transaction_read_only = on` verificado en
el servidor.**
