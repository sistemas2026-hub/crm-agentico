# B.5 — Auditoría técnica de preproducción

**Fecha:** 16/09/2026 · **Rama:** `fix/integracion-wisphub`
**Alcance:** auditoría y solo lectura. **No se modificó producción.**

Cierra la preparación para separar `crm_user` (tráfico) / `crm_migrator`
(migraciones) / `crm_owner` (propiedad) / `motor_user` (motor), diseñada en B.3
e implementada en B.4.

> **Decisión final: LISTO CON CONDICIONES.** Las cuatro condiciones están en la
> sección J. Ninguna es un rediseño; son comprobaciones del entorno real que no
> se pueden hacer desde aquí.

---

## A. Estado actual

### A.1 Base de datos

| Hecho | Valor medido |
|---|---|
| Servidor | PostgreSQL **17.6** (Supabase, tras el pooler Supavisor) |
| Tablas en `public` | **129**, propietario `postgres` las 129 |
| Secuencias / índices | 51 / 783, todos de `postgres` |
| Funciones en `public` | 145 + 4 agregados, de **`supabase_admin`** — no son del CRM |
| Vistas · vistas materializadas · triggers de usuario · tipos propios | **0 · 0 · 0 · 0** |
| Tablas en publicaciones de replicación | **0** |
| Tablas con RLS + FORCE | 60 · sin RLS: 69 (de ellas, **11** con columna de organización) |
| `crm_owner` / `crm_migrator` existen | **NO** — 0 filas en `pg_roles` |

### A.2 Roles

| Rol | LOGIN | SUPERUSER | BYPASSRLS | `public` | `asistente` |
|---|---|---|---|---|---|
| `postgres` | sí | **no** (`rolsuper=false`) | **sí** | todo + dueño de las 129 | todo |
| `crm_user` | sí | no | **no** | USAGE + CREATE + DML | **ninguno** |
| `motor_user` | sí | no | sí *(a propósito)* | solo `organization` | vía `app_backend` |
| `app_backend` | **no** | no | no | ninguno | USAGE + DML por tabla |

`postgres` es miembro de `crm_user` **con `ADMIN OPTION`**; `crm_user` **no** es
miembro de `postgres`. Ese asimetría es la que hace que mover la propiedad hacia
abajo nunca deje a `postgres` fuera.

### A.3 Servicios y credenciales

| Servicio | Variable → valor | Para qué | ¿Corre `entrypoint.sh`? |
|---|---|---|---|
| `backend` | `DBUSER` → `${DBUSER:?}` | HTTP **y migraciones** | **Sí — el único** |
| `celery-worker` | `DBUSER` → `${DBUSER:?}` | tareas (DML) | No — `celery -A crm worker` |
| `celery-beat` | `DBUSER` → `${DBUSER:?}` | agenda (DML) | No — `celery -A crm beat` |
| `motor` | `DBUSER` → **`${MOTOR_DBUSER:?}`** | esquema `asistente` | No |
| `motor-reloj` | `DBUSER` → **`${MOTOR_DBUSER:?}`** | esquema `asistente` | No |

El motor lee una variable **llamada** `DBUSER` dentro del contenedor (es lo que
espera `nucleo/persistencia/conexion.py`) pero su **valor** viene de
`${MOTOR_DBUSER}`. Confundir el nombre con el valor es un error fácil: la
primera versión de mi propia comprobación lo cometió.

### A.4 Migraciones pendientes: 6

Ninguna aplicada. Última aplicada en producción: `cases/0031_respuestaexterna`,
11/09/2026.

---

## B. Verificaciones realizadas

### B.1 Supavisor — cerrado el NO VERIFICABLE de B.4

**Pregunta 1: ¿el pooler cambia el nombre efectivo del usuario?** **Sí.**

```
se envía   DBUSER = postgres.05b5a4b4-3b9a-4901-86f2-f3ed8f8ac0a1
la base ve current_user = postgres
           session_user = postgres
```

El sufijo del tenant es **enrutamiento del pooler**, no parte del nombre del
rol. Consecuencia directa: `rol_base()` de B.4 hace exactamente la misma
transformación que Supavisor, así que la guarda compara contra el mismo nombre
que la base va a ver. Y la comprobación `--con-base`, que pregunta
`current_user`, ya recibe el nombre limpio.

**Pregunta 2: ¿hay que registrar un rol nuevo en el pooler?** **No.**

Un intento con un rol inexistente devuelve
`FATAL: (EAUTHQUERY) user not found in the database`. Mi primera lectura fue que
el pooler tenía lista blanca — **y era incorrecta**. La función que Supavisor
usa para autenticar está en la propia base:

```sql
CREATE OR REPLACE FUNCTION pgbouncer.get_auth(p_usename text)
 RETURNS TABLE(username text, password text) ...
    select rolname::text, ... rolpassword::text
    from pg_authid
    where rolname = $1 and rolcanlogin;
```

Consulta `pg_authid` **en vivo**. Un rol creado con `LOGIN PASSWORD '…'` queda
disponible sin registrar nada en Supavisor. Dos evidencias adicionales:
`motor_user` se creó en agosto y funciona por el mismo pooler, y
`DESPLIEGUE.md` no menciona ningún paso de registro.

**Corolario que conviene tener presente:** `crm_owner` es `NOLOGIN`, así que
`get_auth` nunca lo devolverá. **Es imposible conectarse como `crm_owner` por el
pooler**, que es exactamente lo que se busca.

### B.2 Revisión del código de B.4 — 22 comprobaciones, 0 fallos

Todas sobre el AST o sobre el YAML parseado, nunca sobre el texto.

| Comprobación | Resultado |
|---|---|
| El generador de políticas RLS se invoca desde 25 archivos, **todos migraciones** | ✅ |
| Ningún `execute()` de un camino de petición contiene DDL | ✅ |
| Los 10 módulos de `operaciones` **no leen variables de entorno** | ✅ |
| …ni nombran ninguna credencial ni ningún rol en su código | ✅ |
| …ni importan `common.credenciales` por ninguna vía | ✅ |
| El entrypoint **no exporta** `DBUSER`/`DBPASSWORD` a nivel de shell | ✅ |
| Las 2 asignaciones de `DBUSER` son prefijo de comando (alcance de un proceso) | ✅ |
| `gunicorn` arranca fuera y después del bloque de migraciones | ✅ |
| `celery-worker`, `celery-beat`, `motor`, `motor-reloj` **no** reciben `MIGRATOR_DBUSER` | ✅ |
| `backend` —el único que migra— **sí** la recibe | ✅ |
| `motor` y `motor-reloj` toman su `DBUSER` de `${MOTOR_DBUSER:?}` | ✅ |
| `MIGRATOR_*` usan `:-` (opcional), no `:?` | ✅ |
| La comprobación de la credencial de tráfico corre **antes** de migrar | ✅ |

**Dos comprobaciones mías fallaron por estar mal escritas, no por el código:**
una buscaba cadenas de DDL y marcaba el *generador* de políticas
(`common/rls/__init__.py` contiene ese texto porque lo produce) y dos
*docstrings* de `rls_context.py`; otra buscaba `${DBUSER}` en el bloque del
motor y lo encontraba **en el comentario que explica que el motor no lo usa**.
Es el cuarto sitio de este proyecto donde un escaneo de texto se encuentra a sí
mismo en su propia explicación. Las dos se reescribieron para mirar lo que se
*ejecuta* y lo que el YAML *vale*.

### B.3 Camino del Supervisor NOC IA hacia las credenciales

| Puede el Supervisor… | Resultado |
|---|---|
| leer `DBUSER`/`MIGRATOR_DBUSER` | **No** — sus 10 módulos no llaman `os.environ` ni `getenv` |
| nombrar un rol o una credencial | **No** — ni en código ni en constantes |
| importar `common.credenciales` | **No** |
| crear un rol | **No** — `permission denied to create role` con la credencial de tráfico |
| darse `BYPASSRLS` | **No** — `permission denied to alter role` |
| hacerse miembro de `crm_owner` | **No** — `permission denied to grant role` |
| hacer `ALTER TABLE` | **No** — `must be owner of table` |
| cambiar ownership o RLS | **No** — se deriva de lo anterior |
| tocar el interruptor de autonomía | **No** — vive en `asistente`, al que `crm_user` no llega |

Se suma lo verificado en B.1: **23 módulos recorridos, cero caminos** a un
cliente HTTP, a WispHub/SmartOLT, a las herramientas de red o al motor. Y el
Supervisor **no tiene disparador**: sin señales, sin `ready()`, sin Celery; se
invoca desde una única vista HTTP que exige Jefe de Operaciones.

### B.4 Estado de producción — intacto

| Qué | Valor |
|---|---|
| `crm_owner` / `crm_migrator` en `pg_roles` | **0** |
| Tablas de `public` que no son de `postgres` | **0** |
| Tablas `operaciones_*` | **0** |
| `interruptor_autonomia` / `operaciones_externas` | **0** / **0** |
| Las 4 migraciones de Django en `django_migrations` | **0** |
| Escrituras en `tool_calls` (24 h) | **0** |
| `acciones_propuestas` aprobadas (24 h) | **0** · pendientes: **36**, intactas |
| `tenant_config` | v146, sin cambios |

Todas las consultas de esta auditoría corrieron sobre una conexión marcada
`read_only`: el servidor rechaza cualquier escritura.

---

## C. Datos NO VERIFICABLES

| # | Dato | Por qué | Cómo se cierra |
|---|---|---|---|
| 1 | **Valor actual de `DBUSER`** | Vive en Dokploy | `docker compose exec backend sh -c 'echo $DBUSER'` |
| 2 | **Cómo carga Dokploy las variables** | Panel propietario, sin acceso | Mirarlo al hacer el cambio |
| 3 | **Que un `crm_migrator` nuevo autentique por el pooler** | No puedo crear el rol | Crearlo y conectar *antes* de depender de él |
| 4 | **Que el respaldo restaure** | No he restaurado ninguno | Restaurar en un contenedor desechable y contar filas |
| 5 | **Efecto sobre PostgREST / Realtime / Storage** | Mi banco no los levanta | Comprobar tras el cambio de propiedad |
| 6 | **Comportamiento bajo carga real** | Banco de una sola conexión | Observar tras el corte |
| 7 | **PostgreSQL 17.6 exacto** | La imagen con pgvector para PG 17 es **17.11** | Mismo *major*; las *minor* no cambian semántica de RLS ni de propiedad |

Sobre el **#1**: no está confirmado hoy, pero **sí fechado**. Todas las tablas
creadas por migraciones hasta el 11/09/2026 pertenecen a `postgres`, y
`entrypoint.sh` corre `migrate` con `DBUSER`; luego `DBUSER` era `postgres` ese
día. `DESPLIEGUE.md` registra además que el corte a `crm_user` del 18/08 se
revirtió el mismo día. Dos evidencias independientes coinciden.

---

## D. Riesgos

### Críticos

**D.1 — `docker compose restart` no recoge variables nuevas.**
Es un error ya pagado en este proyecto: `restart` reinicia el contenedor con el
entorno que ya tenía. Hace falta `up -d --force-recreate <servicio>`. Si se
carga `MIGRATOR_DBUSER` y solo se hace `restart`, **el entrypoint seguirá
migrando con la credencial vieja y todo parecerá correcto.**
*Contención:* el paso 11 del procedimiento lo dice explícitamente, y la
verificación posterior no es "el backend arrancó" sino leer el rol efectivo.

**D.2 — Transferencia parcial de propiedad.**
Una tabla rezagada rompe la primera migración que la toque, meses después
(`must be owner of table`). Medido en B.3, escenario 6.
*Contención:* un solo bloque `DO`, una transacción; verificación de que queden
**0** tablas de `postgres`.

**D.3 — Repetir el incidente del 18/08.**
Cambiar `${DBUSER}` y verificar solo el CRM. El motor falla en silencio porque
atrapa la excepción y solo la registra.
*Contención:* las variables ya están separadas en el compose (verificado), y el
paso 15 verifica el motor específicamente, no por inferencia.

### Altos

**D.4 — Cargar `MIGRATOR_DBUSER` antes de crear el rol.** El backend no
arrancaría. *Contención:* el orden del procedimiento, y que las variables son
opcionales.

**D.5 — Crear `crm_migrator` sin `SET role = crm_owner`.** Todo funcionaría y
la propiedad derivaría de vuelta a un rol con LOGIN, migración a migración.
*Contención:* la guarda lo detecta con `--con-base` comparando rol efectivo
contra rol de sesión.

**D.6 — Las 11 tablas sin RLS.** Deuda preexistente, no introducida aquí. Las
dos más expuestas son `personal_access_token` y `portal_access_token`.

### Medios

**D.7 — Encender `CRM_CREDENCIALES_ESTRICTO` antes de tiempo.** Impide arrancar
mientras `DBUSER` siga siendo `postgres`.

**D.8 — `organization`, `users` y 2 tablas `campo_*` sin columna de
organización.** Necesitan una política que `get_enable_policy_sql` no sabe
generar. Decisión de diseño pendiente, fuera de alcance.

**D.9 — PostgreSQL 17.11 vs 17.6.** Mismo *major*.

### Bajos

**D.10 — Una comprobación `--con-base` que no pueda conectar.** Avisa y sigue;
el propio `migrate` prueba la conexión un segundo después.

**D.11 — El Supervisor no corre solo.** Es el diseño. En producción significa
que sin alguien que lo invoque no genera ninguna propuesta.

---

## E. Orden recomendado para producción

> **No ejecutado.** Cada paso supone que el anterior se verificó.

| # | Paso | Criterio de parada |
|---|---|---|
| 1 | **Leer y anotar `DBUSER` y `MOTOR_DBUSER`** | Si `DBUSER` no es `postgres`, **parar**: este plan supone las 129 tablas de `postgres` |
| 2 | **Re-inventariar** tablas, secuencias sueltas, vistas, triggers | Si apareció una secuencia suelta, hay que transferirla aparte |
| 3 | **Respaldo + restauración verificada** en contenedor desechable | Si no restaura, **parar** |
| 4 | **Aplicar las 2 de Fase 1** — `cli/migrar_asistente.py --estado`, luego `--aplicar` | El ledger debe quedar en 2 y el interruptor en `detenido` |
| 5 | **Aplicar las 4 de Django** como `postgres` | 6 tablas `operaciones_*`, 12 políticas |
| 6 | **Crear `crm_owner`** (NOLOGIN) + `GRANT crm_owner TO postgres` + `GRANT USAGE, CREATE ON SCHEMA public TO crm_owner` | — |
| 7 | **Crear `crm_migrator`** (LOGIN) + `GRANT crm_owner TO crm_migrator` + **`ALTER ROLE crm_migrator IN DATABASE <base> SET role = crm_owner`** | — |
| 8 | **Probar que `crm_migrator` conecta por el pooler** y que `current_user` devuelve `crm_owner` | Si no conecta, **parar**: es el NO VERIFICABLE #3 |
| 9 | **`ALTER DEFAULT PRIVILEGES FOR ROLE crm_owner`** sobre tablas **y secuencias** | Antes de transferir, no después |
| 10 | **Transferir propiedad** — el bloque `DO` completo, de una vez | — |
| 11 | **Verificar propiedad**: 0 de `postgres`, 0 de `crm_user`, 129 de `crm_owner`; mismo número de `pg_policies` que antes | Si no cuadra, rollback (H.3) |
| 12 | **`REVOKE CREATE ON SCHEMA public FROM crm_user`** | — |
| 13 | **Cargar `MIGRATOR_*` en Dokploy y `up -d --force-recreate backend`** | **Nunca `restart`** (D.1) |
| 14 | **Verificar el rol efectivo de las migraciones** en el log de arranque | Debe decir `Running migrations as crm_migrator` |
| 15 | **Cambiar `DBUSER` a `crm_user`** y `--force-recreate` de `backend`, `celery-worker`, `celery-beat` | — |
| 16 | **Verificar los 5 servicios uno por uno** (checklist G) | — |
| 17 | **Verificar RLS**: petición sin contexto → 0 filas, en una ruta real | — |
| 18 | *Más adelante:* `CRM_CREDENCIALES_ESTRICTO=1` | Solo cuando 15 y 17 estén confirmados |

### Cambios respecto del orden que pediste

Tres, y los tres por un motivo medido:

1. **Añadí el paso 8** (probar la conexión de `crm_migrator` por el pooler antes
   de depender de ella). Aunque `pgbouncer.get_auth` demuestra que no hace falta
   registro, un rol recién creado por el pooler es el NO VERIFICABLE #3 y no
   quiero descubrirlo durante un despliegue.
2. **Los DEFAULT PRIVILEGES (9) van ANTES de transferir (10)**, no después: así
   cualquier tabla creada entre medias ya nace con los permisos correctos.
3. **Separé el corte en dos pasos (13 y 15)**: primero la credencial de
   migraciones, después la de tráfico. Cambiar las dos a la vez hace imposible
   saber cuál causó un fallo.

### Sobre `crm_migrator` y el `CREATE`

El `CREATE ON SCHEMA public` va en **`crm_owner`**, no en `crm_migrator`. Con
`SET role`, los permisos se evalúan como el rol activo: medido en B.4, con el
`CREATE` solo en `crm_migrator` la migración falla con `permission denied for
schema public`. Es contraintuitivo y no se deduce leyendo el diseño.

---

## F. Checklist previo al cambio

- [ ] `DBUSER` real leído y anotado; `MOTOR_DBUSER` también
- [ ] Confirmado que `DBUSER` es `postgres` (si no, revisar el plan entero)
- [ ] `pg_dump` hecho **y restaurado** en un contenedor desechable
- [ ] Recuento de filas en 3 tablas conocidas, antes y después de restaurar
- [ ] Inventario repetido: 129 tablas, 51 secuencias, 0 sueltas, 0 vistas, 0 triggers
- [ ] `pg_policies` contadas (número de referencia para el paso 11)
- [ ] Contraseña de `crm_migrator` generada y guardada donde va (nunca en el repo)
- [ ] Ventana acordada: el paso 5 aplica migraciones sobre datos reales
- [ ] Confirmado que se usará `up -d --force-recreate`, no `restart`
- [ ] Alguien disponible para verificar el **motor**, no solo el CRM

## G. Checklist posterior al cambio

- [ ] **`backend`** — `select current_user` devuelve `crm_user`; una petición autenticada devuelve datos, no lista vacía
- [ ] **`celery-worker`** — `manage.py check --database default` pasa; una tarea sobre tablas con RLS devuelve filas
- [ ] **`celery-beat`** — arranca y programa (es el que falla más tarde y más callado)
- [ ] **`motor`** — `py -3.13 cli/diferencias_config.py rapilink` corre limpio
- [ ] **`motor-reloj`** — el segundo servicio que lee `MOTOR_DBUSER`; no basta verificar `motor`
- [ ] **Propiedad** — 0 tablas de `postgres`, 0 de `crm_user`, 129 de `crm_owner`
- [ ] **Ninguna tabla de `crm_migrator`** (si la hay, falta el `SET role`)
- [ ] **Políticas** — mismo número que en el paso F
- [ ] **Fail-closed** — consulta sin contexto de organización → 0 filas, en ruta real
- [ ] **`crm_user` sin DDL** — su `ALTER TABLE` falla con `must be owner`
- [ ] **`crm_user` sin CREATE** — su `CREATE TABLE` falla
- [ ] **El interruptor** — `py -3.13 cli/autonomia.py rapilink` dice `detenido`
- [ ] **Humo del motor** — `py -3.13 cli/evaluar.py rapilink --humo --base`

---

## H. Plan de rollback

| Situación | Acción | Pérdida de datos |
|---|---|---|
| **H.1 — Falla el backend tras el corte** | Volver `DBUSER` al valor del paso 1 y `up -d --force-recreate`. Es lo que se hizo el 18/08 y funcionó | Ninguna |
| **H.2 — Falla una migración** | Las de Django revierten: `migrate <app> <anterior>`. **Las de Fase 1 no tienen reversa automática** y no la necesitan (tablas nuevas). Si hay que deshacerlas: `drop table` + borrar sus 2 filas del ledger — **pero con las tablas ausentes el motor vuelve a su excepción explícita y la autonomía se reactiva** | Ninguna |
| **H.3 — Falla la transferencia** | El bloque `DO` es una transacción: si falla a mitad, Postgres revierte el lote entero. No existe el estado "mitad transferido" salvo que se ejecute por partes | Ninguna |
| **H.4 — Hay que deshacer la transferencia ya hecha** | El mismo bucle con los roles cambiados. Medido en B.3: 135 tablas ida y vuelta, 0 filas perdidas, 132 políticas intactas | Ninguna — es catálogo, no datos |
| **H.5 — Problema con Supavisor** (el rol nuevo no autentica) | Vaciar `MIGRATOR_*` y `--force-recreate`: el entrypoint vuelve a migrar con `DBUSER` | Ninguna |
| **H.6 — Problema de permisos** (algo no ve una tabla) | `GRANT` puntual como `postgres`, que sigue siendo miembro de `crm_owner`. Si es sistemático, H.1 | Ninguna |
| **H.7 — Problema de RLS** (consultas devuelven vacío) | Volver `DBUSER` a `postgres` (H.1): con `BYPASSRLS` las políticas dejan de evaluarse y el servicio se restablece mientras se investiga | Ninguna |
| **H.8 — Problema de Celery** | Mismo `--force-recreate` con la variable anterior. `celery-beat` puede necesitar purgar su agenda si quedó a medias | Ninguna |
| **H.9 — Problema del motor** | `MOTOR_DBUSER` no se toca en ningún paso. Si aun así falla, comprobar que no se compartió con `${DBUSER}` — es el incidente del 18/08 | Lo que no se guardó en la ventana no se recupera |

**Ningún paso de esta transición ejecuta `INSERT`, `UPDATE`, `DELETE` ni
`DROP` sobre datos.** `CREATE ROLE`, `GRANT`, `ALTER DEFAULT PRIVILEGES` y
`ALTER TABLE … OWNER TO` son operaciones de catálogo. Verificado contando filas
antes y después en B.3.

**Rollback parcial o total:** la transferencia admite ambos (el bucle acepta un
filtro por nombre), pero **se recomienda total**: una transferencia a medias es
el riesgo D.2.

---

## I. Evidencia de pruebas

| Suite | Total | Pasan | Fallan | Saltan |
|---|---|---|---|---|
| `test_credenciales.py` (B.4, sin base) | 28 | **28** | 0 | 0 |
| `test_credenciales_postgres.py` (B.4, PG 17) | 10 | **10** | 0 | 0 |
| `test_entrypoint_credenciales.py` (B.4, shell) | 17 afirmaciones | **17** | 0 | 0 |
| Regresión Django completa | 3.728 | **3.685** | **0** | 43 |
| Suite del motor (`tests/`) | 84 | **83** | 1 | 0 |
| Revisión de código B.5 | 22 | **22** | 0 | 0 |

La cuenta de la regresión cuadra con la línea base de B.1: +38 recolectadas
(las 28 + 10 nuevas), +28 pasan, +10 saltan (las de PostgreSQL sobre SQLite).
**Cero fallos nuevos y cero preexistentes** del lado de Django.
`tests/test_reloj.py`, en el motor, ya fallaba antes de la Etapa B.

**Guardas verificadas desarmándolas** — una prueba en verde no demuestra que
mida algo:

| Desarme | Pruebas en rojo |
|---|---|
| Recorte del sufijo del pooler | **10** |
| Comprobación del motor (D/E) | **3** |
| RLS apagada en la tabla de prueba | ve 2 filas en vez de 0 |

**Probado de punta a punta contra PostgreSQL 17:** el `entrypoint.sh` real, con
Django real, con las 129 tablas en manos de `crm_owner` — las 6 tablas nuevas
quedaron de `crm_owner`, con RLS forzada, y `crm_user` con permiso sin un solo
`GRANT` manual. Y el camino de fallo: `crm_user` sin ser dueño → **salida 1,
cero líneas de migración, servidor sin levantar**.

### Las 6 migraciones — análisis individual

| Migración | Qué hace | ¿Pierde datos? | ¿Exige propiedad? |
|---|---|---|---|
| `202609151710_interruptor_autonomia.sql` | Crea `asistente.interruptor_autonomia`; RLS + FORCE; `GRANT select, insert` (append-only por grant) | **No** — 0 sentencias destructivas | Sí, sobre la tabla que ella misma crea |
| `202609151715_operaciones_externas.sql` | Crea `asistente.operaciones_externas`; RLS + FORCE; `GRANT select, insert, update` | **No** | Sí, sobre la tabla que crea |
| `operaciones/0001_initial` | 6 `CreateModel`, 9 `AddIndex`, 6 `AddConstraint` | **No** | Sí, sobre lo que crea |
| `operaciones/0002_rls_operaciones` | `RunPython(estampar_rls, sin_reversa)` | **No** | **Sí, sobre tablas existentes** — es la que falla bajo `crm_user` |
| `common/0039_alter_activity_entity_type` | `AlterField(activity.entity_type)` — solo `choices` | **No** — `sqlmigrate` emite `-- (no-op)` | No |
| `campo/0003_alter_asignaciontrabajo_rol` | `AlterField(asignaciontrabajo.rol)` — solo `choices` | **No** — `-- (no-op)` | No |

**Orden:** las 2 de Fase 1 primero (esquema `asistente`, independiente), luego
las 4 de Django. Dentro de Django, el grafo de dependencias fija el orden;
`operaciones/0002` va necesariamente después de `0001`.

**Verificación posterior, por migración:**

```sql
-- Fase 1, ledger
select count(*) from asistente.migraciones_aplicadas
 where archivo like '2026091517%';                      -- espera 2
-- Fase 1, efecto: cada tenant nace DETENIDO
select estado from asistente.interruptor_autonomia
 order by creado_en desc limit 1;                       -- espera 'detenido'
-- Etapa B, tablas
select count(*) from information_schema.tables
 where table_schema='public' and table_name like 'operaciones\_%';   -- espera 6
-- Etapa B, políticas
select count(*) from pg_policies
 where schemaname='public' and tablename like 'operaciones\_%';      -- espera 12
-- Las dos no-op
select app, name from django_migrations
 where (app='common' and name like '0039%')
    or (app='campo'  and name like '0003%');            -- espera 2 filas
```

---

## J. Decisión final

### LISTO CON CONDICIONES

**Por qué no "LISTO PARA PRODUCCIÓN":** el mecanismo está probado, pero tres de
los siete NO VERIFICABLES son del entorno real y ninguno se cierra desde aquí.
El más importante no es técnico: **no he restaurado ningún respaldo**. Un
`pg_dump` que nadie restauró no es un respaldo, y este plan mueve la propiedad
de 129 tablas.

**Por qué no "NO LISTO":** nada de lo pendiente es un rediseño. El diseño está
medido contra PostgreSQL 17 de punta a punta, incluido el camino de fallo; el
código de B.4 es compatible hacia atrás y hay una prueba que lo afirma; y el
último NO VERIFICABLE serio de B.4 —qué hace Supavisor con el nombre del
usuario— quedó cerrado hoy, con respuesta favorable en los dos sentidos.

### Las cuatro condiciones

1. **Confirmar `DBUSER`.** Un comando. Si no es `postgres`, el plan cambia.
2. **Restaurar el respaldo y contar filas.** No basta con hacerlo.
3. **Probar que `crm_migrator` conecta por el pooler** (paso 8) antes de
   cargarlo en Dokploy.
4. **Usar `up -d --force-recreate`, nunca `restart`.** Con `restart` la
   variable nueva no se aplica y todo *parece* correcto.

### Lo que esta etapa no autoriza

Ni las 11 tablas sin RLS, ni el problema de diseño de
`organization`/`users`/las 2 `campo_*`, ni M02/M03/M09, ni el scheduler, ni la
autonomía. B.5 termina aquí.

---

*Auditoría en solo lectura. No se crearon roles, no se cambiaron credenciales,
no se aplicaron migraciones, no se transfirió propiedad, no se modificó RLS y no
se activó autonomía. Lo único que tocó producción fueron consultas de catálogo
sobre una conexión marcada `read_only`.*
