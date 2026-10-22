# B.6 — Plan de cambio controlado

**Fecha:** 16/09/2026 · **Rama:** `fix/integracion-wisphub`
**Alcance:** preparación. **No se ejecutó ningún cambio en producción.**

Prepara la separación `crm_user` (tráfico) / `crm_migrator` (migraciones) /
`crm_owner` (propiedad, NOLOGIN) / `motor_user` (motor).

> **Tres de las cuatro condiciones de B.5 están cerradas con medición**, y de la
> cuarta sólo queda una comprobación de 30 segundos que exige crear el rol. Por
> el camino aparecieron ocho defectos: seis en el procedimiento de respaldo y
> restauración que yo mismo había documentado y dos en mis propios scripts.
> Todos están corregidos y probados.
>
> **Actualizado el 16/09/2026 tras B.7:** la sección B se reescribió entera. La
> versión anterior mandaba generar un respaldo **irrestaurable** — le faltaba un
> esquema, no llevaba las extensiones y no incluía los roles.
>
> **Actualizado el 17/09/2026 tras el simulacro del paso 9:** dos defectos más,
> esta vez en la **restauración** — el filtro del índice perdía los permisos del
> esquema, y el `SET role` de `crm_migrator` no viaja en ningún volcado
> (hallazgos 5 y 6). Ahora el procedimiento está validado de punta a punta con
> los datos reales de producción.
>
> **Actualizado el 17/09/2026 tras la etapa 9.1:** el paso 9 deja una dependencia
> permanente —`postgres` miembro de `crm_owner`— que este plan no documentaba.
> Medida en réplica: no sostiene el tráfico del CRM (eso lo cubre `service_role`)
> pero sí toda capacidad de reparación. Ver §D, «La dependencia que crea el paso
> 9», y la fila nueva de §I.
>
> **Actualizado el 17/09/2026 tras las etapas 10.2 y 10.3:** el procedimiento de
> restauración de §B instalaba `pgcrypto` en el esquema `ext` y dejaba **un
> scheduler roto** — `pg_restore` en 0 y `job_claim()` fallando. Reescrito
> entero: tres artefactos en vez de dos, tres scripts ejecutables en
> `despliegue/respaldo/`, y una verificación **funcional** obligatoria. Probado
> dos veces desde cero: 25/25 estructurales contra producción y el flujo del
> scheduler hasta `succeeded`. El protocolo completo está en
> `B7_PROTOCOLO_RESPALDO.md`.

---

## A. Objetivo

Que las migraciones dejen de correr con la credencial que sirve peticiones, sin
que el usuario de tráfico llegue nunca a ser dueño de una tabla.

El mecanismo ya está en el repositorio desde B.4. Lo que falta es el
procedimiento para ejecutarlo: los roles, la propiedad y el orden.

---

## B. Estado de las condiciones de B.5

| # | Condición | Estado |
|---|---|---|
| A | **`DBUSER` real** | ✅ **CERRADA** — `DBUSER = postgres` |
| B | **Respaldo restaurado y validado** | ✅ **CERRADA con datos reales** — con seis hallazgos |
| C | **`crm_migrator` por el pooler** | ⚠️ **3 de 4 partes** — la cuarta exige crear el rol |
| D | **Recreación de contenedores** | ✅ **CERRADA con medición** |

### A — `DBUSER` real: CERRADA, `DBUSER = postgres`

No hay claves SSH en esta máquina, así que la vía original —`docker compose exec`
en el VPS— no estaba disponible. Se cerró por otra: **`pg_stat_statements`
guarda el rol de cada consulta**, acumulado desde el 07/08/2026. No es un
muestreo puntual, así que no depende de pillar viva una conexión de Django, que
dura lo que una petición (`CONN_MAX_AGE = 0`).

```
INSERT INTO "activity"   postgres=542     crm_user=0
INSERT INTO "case"       postgres=186     crm_user=0
UPDATE "case"            postgres=8.852   crm_user=0
SELECT  FROM "case"      postgres=56.178  crm_user=5
```

**`crm_user` no ha escrito nunca en este CRM.** Sus 230 llamadas totales en 40
días encajan con lo que `DESPLIEGUE.md` describe del 18/08: el corte que se
activó y revirtió el mismo día, más la verificación manual de entonces.

Coincide con las dos evidencias indirectas anteriores (las 129 tablas creadas
por migraciones pertenecen a `postgres`; la reversión documentada del 18/08).
Se reconfirma igualmente en el paso 1 del procedimiento:

```bash
docker compose exec backend sh -c 'echo $DBUSER'
docker compose exec backend python manage.py shell -c \
  "from django.db import connection; c=connection.cursor(); \
   c.execute('select current_user'); print(c.fetchone()[0])"
```

Los dos, no uno: el primero dice qué se configuró; el segundo, con qué rol llega
la conexión al otro lado del pooler.

### B — Respaldo: CERRADA con datos reales (actualizado tras B.7)

> **Esta sección se reescribió el 16/09/2026.** La versión anterior documentaba
> un comando de respaldo que produce un archivo **irrestaurable**. El defecto no
> se veía en el archivo: sólo aparecía al intentar restaurarlo, y la versión
> anterior sólo había validado el esquema. Lo que sigue es el procedimiento
> **ejecutado entero con los datos de producción**.

**Lo que se hizo en B.7:** respaldo completo de producción (operación de solo
lectura; `pg_dump` toma `ACCESS SHARE` y no bloquea), restauración en un
contenedor desechable, comparación fila a fila, y eliminación de los datos al
terminar.

| Comprobación | Producción | Restaurado |
|---|---|---|
| Tablas | 164 | **164** |
| Filas | 10.023 | **10.023** |
| Contenido (hash por tabla, 54 con datos) | 54 | **54 idénticas** |
| Secuencias y su `last_value` | 51 | **51** |
| Índices · restricciones · políticas | 881 · 823 · 155 | **iguales** |
| Tablas con RLS · con FORCE | 93 · 88 | **iguales** |
| Propietarios | postgres 159, asistente_owner 5 | **iguales** |
| `GRANT` a crm_user · app_backend · motor_user | 903 · 111 · 1 | **iguales** |

**0 fallos de integridad.** Archivo: 8,8 MB. Restauración: **código de salida 0,
13 segundos**, con `--exit-on-error`.

#### 🔴 Hallazgo 1 (B.2/B.5) — `--no-owner` deja el respaldo sin privilegios

En B.2 y B.5 se escribió `pg_dump --no-owner --format=custom`. Medido:

| Volcado | `GRANT` | `OWNER TO` | Al restaurar |
|---|---|---|---|
| `--no-owner --no-privileges` | **0** | **0** | **0 GRANT a `crm_user`** |
| **sin esas banderas** | 414 | 180 | **903 GRANT**, dueños preservados |

Producción tiene **903 `GRANT` a `crm_user`**. Con `--no-owner`, un respaldo
restaurado dejaría a `crm_user` sin permiso sobre nada: el CRM quedaría roto
justo en el momento en que se recurre al respaldo.

#### 🔴 Hallazgo 2 (B.7) — faltaba un esquema: `asistente_ledger`

El alcance `--schema=public --schema=asistente` produce un archivo que **aborta
a mitad de la restauración**:

```
pg_restore: error: ERROR:  schema "asistente_ledger" does not exist
Command was: CREATE TRIGGER ma_sin_truncate
  BEFORE TRUNCATE ON asistente.migraciones_aplicadas
  EXECUTE FUNCTION asistente_ledger.solo_agregar();
```

Dos tablas del ledger —`migraciones_aplicadas` y `migraciones_ledger_esquema`—
tienen *triggers* que llaman a una función en un **tercer esquema**. Se
comprobó si había más dependencias cruzadas: **es la única**, y ningún *default*
de columna nombra otro esquema.

#### 🔴 Hallazgo 3 (B.7) — el volcado no lleva las extensiones

```
pg_restore --list … | grep EXTENSION   ->  0 entradas
```

Un volcado por esquemas **no incluye `CREATE EXTENSION`**. Y dos de las
extensiones que el proyecto usa viven en `public`:

| Extensión | Esquema en producción | Quién la necesita |
|---|---|---|
| `pg_trgm` | **`public`** | búsquedas del CRM |
| `vector` | **`public`** | `asistente.document_chunks.embedding` |
| `pgcrypto` | `ext` | funciones del motor |

Si el destino no las tiene instaladas **antes**, cualquier tabla que use el tipo
`vector` falla. Hay que instalarlas en **el mismo esquema** en el que están en
producción.

#### 🔴 Hallazgo 4 (B.7) — `pg_dump` nunca incluye los roles

```
entradas de ROLE en el volcado:  0
pg_dumpall --roles-only       ->  23 CREATE ROLE + 29 GRANT
```

Los roles son objetos del **clúster**, no de la base. Un respaldo que sólo tenga
el `pg_dump` restaura tablas cuyos dueños y concesionarios **no existen**. Es un
**segundo artefacto, obligatorio**.

#### 🔴 Hallazgo 5 (17/09) — el filtro del índice perdía los permisos del esquema

Los hallazgos 5 y 6 salieron del **simulacro final del paso 9**, ejecutado sobre
una réplica exacta del estado de producción. Ninguno afecta a la transferencia:
los dos afectan a qué pasa **si algún día hay que restaurar**.

La versión anterior de este procedimiento filtraba tres entradas del índice para
evitar el choque de `CREATE SCHEMA public`. Una de ellas no debía filtrarse:

```
ACL de 'public' en PRODUCCION
  {pg_database_owner=UC/…, =U/…, postgres=U/…, service_role=U/…,
   crm_user=UC/…, crm_owner=UC/…}

ACL de 'public' tras restaurar con el filtro antiguo
  {pg_database_owner=UC/…, =U/…}          <- crm_user y crm_owner, perdidos
```

La `ACL` del esquema lleva `USAGE` y `CREATE` para `crm_user` y `crm_owner`. Al
filtrarla, la restauración deja el esquema sin esos permisos y **`crm_migrator`
no puede crear tablas**: `permission denied for schema public`. Es decir, las
migraciones dejarían de funcionar justo después de recuperar de un desastre.

El filtro correcto quita **sólo** la entrada que crea el esquema. Va anclado al
principio de línea y con un espacio final, para no cazar también `COMMENT - SCHEMA
public` ni `ACL - SCHEMA public`:

```bash
grep -vE '^[0-9]+; [0-9]+ [0-9]+ SCHEMA - public '
```

#### 🔴 Hallazgo 6 (17/09) — el `SET role` no viaja en ningún volcado

```
ALTER ROLE crm_migrator IN DATABASE postgres SET role = crm_owner

  en pg_dump de la base          -> NO
  en pg_dumpall --roles-only     -> NO
```

Los ajustes por rol **y base** viven en `pg_db_role_setting`, y sólo los emite un
`pg_dumpall` completo — no el volcado de la base ni el de roles. Una restauración
a partir de los dos artefactos de este procedimiento **pierde exactamente la
pieza que impide que la propiedad derive**: sin ese `SET role`, cada tabla que
cree una migración posterior queda de `crm_migrator`, un rol con LOGIN.

Es una sola sentencia, y está ahora como **paso 2 explícito** de la restauración.

---

### El procedimiento de respaldo — corregido y ejecutable

> **Reescrito el 17/09/2026 (paso 10.3).** La versión anterior de esta sección
> instalaba `pgcrypto` en el esquema `ext` y producía **un scheduler roto**: el
> `pg_restore` terminaba en 0 y `job_claim()` fallaba con
> `schema "extensions" does not exist`. El procedimiento ya no se escribe a
> mano: vive en tres archivos y está probado dos veces desde cero.
> Ver `B7_PROTOCOLO_RESPALDO.md` y `PASO10.2` / `PASO10.3`.

```bash
# RESPALDO -- produce TRES artefactos. Los tres son obligatorios.
py -3.13 despliegue/respaldo/respaldar.py --destino "$CARPETA" \
        [--imagen pgvector/pgvector:pg17]   # si la maquina no tiene pg_dump

# RESTAURACION -- un solo comando, sin pasos manuales fuera de el
sh despliegue/respaldo/restaurar.sh "$CARPETA" "$SELLO" "$BASE" -U "$USUARIO"

# VERIFICACION -- estructura Y funcion. Obligatoria.
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto "$PUERTO"
```

**Por qué tres artefactos y no dos.** Medido, no supuesto:

| Artefacto | Lo que transporta | Lo que NO |
|---|---|---|
| `*_datos.dump`<br>`pg_dump --format=custom` de los 3 esquemas | 328 TABLE, 616 INDEX, 265 CONSTRAINT, 155 POLICY, **231 ACL**, 3 SCHEMA | **0 EXTENSION**; nada fuera de los 3 esquemas |
| `*_roles.sql`<br>`pg_dumpall --roles-only` | 25 `CREATE ROLE`, 43 `ALTER ROLE`, **33 `GRANT` de membresía** | **0** `IN DATABASE … SET`; **0** `GRANT` sobre esquemas; 0 `CREATE EXTENSION` |
| `*_entorno.sql`<br>**nuevo**, generado del catálogo | Extensiones y su esquema; ACL de esquemas ajenos a los 3; `pg_db_role_setting` de nuestros roles | Nada de ámbito «toda la base»: ahí vive el secreto JWT |

**Lo que el respaldo NO transporta y por eso vive en el artefacto 3** — cuatro
cosas, no dos:

1. `create extension pgcrypto with schema **extensions**` (no `ext`).
2. `grant usage on schema extensions to asistente_owner` — sin esto `job_claim`
   falla con `permission denied for schema extensions` en la **primera
   llamada**, no al restaurar.
3. `alter role crm_migrator in database … set role = crm_owner`.
4. `alter role crm_user|motor_user set idle_in_transaction_session_timeout`.

> **`--schema=extensions` NO es la solución.** Se probó: trae los event triggers
> internos de Supabase (`grant_pg_cron_access`, `pgrst_ddl_watch`,
> `grant_pg_net_access`), que son de `supabase_admin` y referencian extensiones
> que el destino puede no tener — y **ni siquiera trae la extensión**, porque
> `pg_dump` no vuelca extensiones cuando se le pasa `--schema`.

> El archivo de roles contiene los **hashes de las contraseñas**. Guardarlo con
> el mismo cuidado que una credencial.

**El orden de la restauración, y por qué es ese** (lo implementa `restaurar.sh`):

1. **roles** — cada `OWNER TO` y cada `GRANT` del volcado necesita que el rol
   exista.
2. **entorno** — después de los roles, porque concede a `asistente_owner`; y
   antes del volcado, porque los índices del volcado usan `pg_trgm` y `vector`.
3. **datos** — con el índice filtrado: se quita **sólo** la entrada que *crea*
   el esquema `public`. Su `ACL` no se filtra (lleva `crm_user=UC`,
   `crm_owner=UC`), y el anclaje con espacio final evita cazar
   `COMMENT - SCHEMA public` y `ACL - SCHEMA public`.

**Verificación obligatoria después de restaurar.** `pg_restore` en 0 no
demuestra nada: con `pgcrypto` en el esquema equivocado también da 0.
`verificar_restauracion.py` compara 25 puntos contra producción **y** ejecuta
`job_claim → job_contexto → job_heartbeat → job_finalize` exigiendo
`succeeded`.

**Un límite que conviene saber antes de necesitarlo.** El volcado de la **base
completa** (sin `--schema`) sí lleva las 7 extensiones y los 12 esquemas, pero
**no se restaura en un PostgreSQL normal**:

```
ERROR:  extension "pg_net" is not available
```

`pg_net`, `supabase_vault` y compañía son de Supabase. El volcado completo sólo
es restaurable **sobre otra instancia de Supabase**. El de tres esquemas es el
que recupera el CRM y el motor en cualquier PostgreSQL 17 con pgvector, y es el
que se validó.

**Cómo se comprueba que un respaldo sirve** (no basta con que el archivo exista):

1. Restaurarlo en un contenedor desechable con el procedimiento de arriba.
2. Comparar el recuento de filas de cada tabla contra producción. Tomar **dos
   referencias**, antes y después del volcado: producción sigue viva, y contra
   una sola referencia el restaurado puede tener *más* filas — que es imposible
   en un restore y sólo significa que el volcado se tomó después.
3. Comparar el **contenido**, no sólo el recuento. Ordenar por el `md5` de cada
   fila, nunca por su texto: ordenar texto depende de la **colación**, y la de
   Supabase no es la de una imagen de Debian — mismo contenido, distinto hash.
4. Probar un `INSERT` real en una tabla con secuencia: el id asignado tiene que
   ser el siguiente al `last_value`, no uno ya ocupado. Si el restore perdiera
   la posición de la secuencia, el fallo no se ve hasta que ocurre.
5. Probar el aislamiento por organización sobre los datos restaurados.
6. **Borrar el contenedor y el archivo.**

### C — `crm_migrator` por el pooler: 3 de 4 partes cerradas

La condición exige que `crm_migrator` **exista**, y crearlo es modificar
producción. Se partió en piezas y se midieron las que no exigen crear nada:

| Parte | Pregunta | Estado |
|---|---|---|
| **C.1** | ¿El pooler admite un rol que no sea `postgres`? | ✅ **sí** |
| **C.2** | ¿Hay que registrar el rol nuevo en el pooler? | ✅ **no** |
| **C.3** | ¿Un `ALTER ROLE … SET` sobrevive al pooler? | ✅ **sí** |
| **C.4** | ¿Un rol `NOLOGIN` queda fuera de su alcance? | ✅ **sí** |
| **C.5** | ¿Autentica **`crm_migrator`** concretamente? | ⚠️ imposible sin crearlo |

**C.1** — `motor_user` (creado el 18/08/2026, *después* de que el pooler
existiera, sin privilegios especiales) autentica con el sufijo del tenant.

**C.2** — `pgbouncer.get_auth` consulta `pg_authid` **en vivo** filtrando por
`rolcanlogin`: **no hay lista blanca que registrar**. Un rol creado con `LOGIN
PASSWORD` queda disponible sin más.

**C.4** — se sigue de C.2: `crm_owner` es `NOLOGIN`, así que `get_auth` nunca lo
devuelve. **Es inalcanzable por el pooler** — justo lo que se busca.

**C.3** — es la pieza de la que depende que la propiedad no derive. Si el pooler
descartara los ajustes por rol, el `SET role = crm_owner` no llegaría y cada
tabla que creara una migración quedaría de `crm_migrator` *sin que nadie lo
notase*. Medido con `motor_user`, que ya tiene un ajuste propio en el catálogo:

```
conectado POR EL POOLER como motor_user
  idle_in_transaction_session_timeout
    valor por defecto de PostgreSQL : 0       (desactivado)
    valor en esta sesión            : 60000   (60 s)
```

Ese `60000` sólo puede venir del `ALTER ROLE motor_user SET …`. **Los ajustes
por rol atraviesan el pooler** — los aplica PostgreSQL al abrir la sesión, no el
pooler, y el puerto 5433 es modo *session*. `SET role = crm_owner` es un ajuste
de la misma clase (`pg_db_role_setting`).

**C.5** se comprueba en 30 segundos tras crear el rol — es el paso 7 del
procedimiento.

### D — Recreación de contenedores: CERRADA con medición

```
1) arranque sin la variable          -> MIGRATOR_DBUSER=[]
2) se define + docker compose restart -> MIGRATOR_DBUSER=[]          ← NO la toma
3) se define + up -d --force-recreate -> MIGRATOR_DBUSER=[crm_migrator]  ← sí
```

`restart` reinicia el contenedor **con el entorno que ya tenía**. Si se carga
`MIGRATOR_DBUSER` y sólo se reinicia, el entrypoint sigue migrando con la
credencial vieja y **todo parece correcto**.

---

## C. Precheck

**`despliegue/separacion_credenciales/precheck.py`** — solo lectura, conexión
marcada `read_only`, **sale con 1** ante cualquier condición crítica.

```bash
py -3.13 despliegue/separacion_credenciales/precheck.py
py -3.13 despliegue/separacion_credenciales/precheck.py --respaldo b6_previo.dump
```

Comprueba, en siete bloques: identidad de la conexión (y si el pooler recortó el
sufijo), los seis roles y sus atributos, el `SET role` de `crm_migrator` si ya
existe, propiedad de las tablas, **secuencias sueltas**, vistas/triggers
inesperados, RLS y FORCE, la frontera con `asistente`, las 6 migraciones y el
respaldo.

**Tres niveles.** `CRITICO` detiene; `AVISO` no detiene; `DATO` es un número que
hay que anotar. Dos de esos datos son **guardas de los pasos siguientes**: el
recuento de tablas a transferir (que el paso 3 exige que coincida) y el número
de políticas (que tiene que ser el mismo después).

**Probado contra el esquema real de producción restaurado.** Devolvió
exactamente los números de producción — 129 tablas, 60 con RLS+FORCE, 120
políticas, 51 secuencias todas atadas — y **NO-GO con salida 1** porque no se
había declarado un respaldo.

> No se ejecutó contra producción durante B.6.

---

## D. SQL preparado

Cuatro archivos en **`despliegue/separacion_credenciales/`**. Están ahí y **no
en `supabase/`** a propósito: `cli/migrar_asistente.py` recorre `supabase/*.sql`
y aplica lo que falte en su ledger. Un archivo operativo de una sola vez no
tiene por qué entrar en ese registro, y meterlo ahí haría que se reaplicara solo.

| Archivo | Qué hace |
|---|---|
| `01_crear_roles.sql` | `crm_owner` (NOLOGIN) y `crm_migrator` (LOGIN), con el `SET role` |
| `02_default_privileges.sql` | Los defaults de `crm_owner` → `crm_user` |
| `03_transferir_propiedad.sql` | La transferencia, transaccional y con tres guardas |
| `99_revertir_propiedad.sql` | El rollback de la propiedad |

Todos llevan el aviso **`NO EJECUTAR EN PRODUCCIÓN SIN AUTORIZACIÓN EXPLÍCITA`**
en la cabecera. Todos se probaron contra el esquema real restaurado.

### Dos defectos encontrados al probarlos

**psql no interpola sus variables dentro de un bloque `DO $$ … $$`.** El texto
entre comillas de dólar le resulta opaco, así que `:'clave_migrator'` y
`:esperadas` llegaban literales al servidor y daban
`syntax error at or near ":"`. Corregido de dos formas distintas, según el caso:

- para la contraseña, `\gexec` sobre un `format(...)` construido fuera del
  bloque — y con un `where not exists` que lo vuelve re-ejecutable sin pisar la
  clave de un rol ya creado;
- para el recuento, `set_config('b6.esperadas', :'esperadas', true)` antes del
  bloque, que lo lee con `current_setting`.

**Son exactamente el tipo de error que sólo aparece ejecutando.** Leyendo el SQL
los dos parecen correctos.

### Alcance de la transferencia

Se mueve: tablas ordinarias (`relkind='r'`) de `public` cuyo dueño sea
`postgres`.

**No se mueve, y no por suerte sino porque el filtro no las alcanza:** las 145
funciones + 4 agregados de `public` (son de `supabase_admin`); PostgREST,
Realtime, Storage y GraphQL (viven en sus propios esquemas); cualquier tabla que
Supabase añada a `public` (sería de `supabase_admin`); el esquema `asistente`
del motor.

### Las tres guardas del paso 3

1. `crm_owner` existe y quien ejecuta puede ejercerlo.
2. **El recuento coincide con el del precheck.** Probado: con `-v esperadas=999`
   aborta — *«se iban a mover 0 tabla(s) y el precheck contó 999»*.
3. **No hay secuencias sueltas** que se quedarían atrás.

Y al cerrar, dentro de la transacción: 0 tablas bajo `postgres` y **0 bajo una
credencial con login** — porque acabar en manos de `crm_user` sería cambiar un
problema por otro peor.

### La dependencia que crea el paso 9: `postgres` → `crm_owner`

`01_crear_roles.sql` ejecuta `grant crm_owner to current_user` para que el
`ALTER TABLE … OWNER TO crm_owner` del paso 9 esté permitido — PostgreSQL exige
que quien transfiere sea miembro del rol que va a recibir. Esa línea
**sobrevive al paso 9 y queda como dependencia permanente**. Medido en
producción y en réplica el 17/09/2026 (etapa 9.1).

En producción `postgres` tiene **dos** filas de membresía a `crm_owner`, y la
diferencia entre ellas es lo que decide si un rollback es posible:

| Otorgante | hereda | SET | admin | Qué aporta |
|---|---|---|---|---|
| `postgres` — la de `01_crear_roles.sql` | **sí** | sí | no | Los privilegios: DDL sobre las 129 tablas y `CREATE` en `public` |
| `supabase_admin` — la crea supautils con cada rol nuevo | no | no | **sí** | Ningún privilegio, pero permite **volver a otorgarse** la anterior |

**Lo que NO depende de esta membresía**, medido revocándola en réplica: el CRM
sigue leyendo y escribiendo. `service_role` está en la ACL de las 129 tablas
(`arwdDxtm`) y de las 51 secuencias, y `postgres` lo hereda; `pg_read_all_data`
añade SELECT. Los respaldos tampoco se ven afectados — `pg_dump --schema=public`
dio **952.246 bytes, 190 entradas ACL y 129 `TABLE DATA` idénticos** con y sin
la membresía.

**Lo que sí depende:** `ALTER TABLE`, `CREATE INDEX`, `DROP TABLE` y
`CREATE TABLE` en `public`. Sobre el esquema, `postgres` tiene `U` directo
(`postgres=U/pg_database_owner`) pero el `C` lo aporta `crm_owner`.

> **No revocarla mientras `DBUSER = postgres`.** No por el tráfico —que
> sobrevive— sino porque deja a la credencial de emergencia sin capacidad de
> reparar nada. Si se decide revocarla, hacerlo **después del paso 14** y
> **nunca tocar la fila de `supabase_admin`**: es la que permite deshacerlo.

**El camino administrativo no depende de ella.** `crm_migrator` conecta por el
pooler y actúa como `crm_owner` vía `ALTER ROLE … SET role`; en la réplica siguió
haciendo DDL con `postgres` completamente desvinculado de `crm_owner`. El
mantenimiento rutinario (`VACUUM`, `ANALYZE`, `REINDEX`, `LOCK TABLE`) tampoco:
lo cubre el privilegio `MAINTAIN` (`m`) que `service_role` ya tiene sobre las 129.

---

## E. Orden de ejecución

| # | Paso | Con qué |
|---|---|---|
| 1 | Leer y anotar `DBUSER` y `MOTOR_DBUSER` | contenedor |
| 2 | **Respaldo de DOS archivos** (base + roles) y restaurarlo verificando filas, contenido y secuencias | ver §B |
| 3 | **Precheck** — anotar el recuento de tablas y de políticas | `precheck.py --respaldo …` |
| 4 | Aplicar las 2 de Fase 1 | `cli/migrar_asistente.py --estado`, luego `--aplicar` |
| 5 | Aplicar las 4 de Django **como `postgres`** | `manage.py migrate` |
| 6 | Crear los roles | `01_crear_roles.sql` |
| 7 | **Probar `crm_migrator` POR EL POOLER** | `psql -h … -p 5433 -U crm_migrator.<tenant>` |
| 8 | Default privileges | `02_default_privileges.sql` |
| 9 | Transferir propiedad | `03_transferir_propiedad.sql -v esperadas=N` |
| 10 | Verificar propiedad y políticas | precheck otra vez |
| 11 | `REVOKE CREATE ON SCHEMA public FROM crm_user` | — |
| 12 | **FASE A:** cargar `MIGRATOR_*` y `up -d --force-recreate backend` | Dokploy |
| 13 | Verificar en el log: `Running migrations as crm_migrator` | — |
| 14 | **FASE B:** cambiar `DBUSER` a `crm_user` y `--force-recreate` de los tres | Dokploy |
| 15 | Verificar los 5 servicios, uno por uno | checklist H |
| 16 | Monitorizar 24 h | — |
| 17 | *Más adelante:* `CRM_CREDENCIALES_ESTRICTO=1` | — |

**Las migraciones (4 y 5) van ANTES de crear los roles**, con `postgres`, que es
dueño de todo. Así las 6 tablas nuevas nacen bajo el esquema conocido y entran en
la transferencia del paso 9 como cualquier otra.

**El paso 7 va antes del 8**: si `crm_migrator` no autentica por el pooler, mejor
saberlo antes de haber tocado permisos.

---

## F. Las 6 migraciones

| # | Migración | Con qué credencial | Por qué |
|---|---|---|---|
| 1 | `202609151710_interruptor_autonomia.sql` | **`postgres`** | Crea la tabla, así que es su dueño. Va por `cli/migrar_asistente.py`, que lee `DBUSER` del shell |
| 2 | `202609151715_operaciones_externas.sql` | **`postgres`** | Igual |
| 3 | `operaciones/0001_initial` | **`postgres`** | Crea 6 tablas; es su dueño |
| 4 | `operaciones/0002_rls_operaciones` | **`postgres`** | `ALTER TABLE … ENABLE RLS` sobre las 6 que acaba de crear `postgres`. **Bajo `crm_user` fallaría** con `must be owner of table` |
| 5 | `common/0039_alter_activity_entity_type` | **`postgres`** | `-- (no-op)`: sólo `choices` |
| 6 | `campo/0003_alter_asignaciontrabajo_rol` | **`postgres`** | `-- (no-op)` |

**Ninguna necesita `crm_migrator`, y es a propósito.** Se aplican antes de crear
los roles, con la credencial que hoy es dueña de todo. `crm_migrator` existe para
las migraciones **futuras**, que llegarán cuando la propiedad ya esté en
`crm_owner` — empezando por la de las 11 tablas sin RLS.

**Ninguna de las 6 pierde datos.** Las cuatro primeras sólo crean; las dos
últimas no emiten una sola sentencia SQL.

### Verificación posterior

```sql
select count(*) from asistente.migraciones_aplicadas
 where archivo like '2026091517%';                                  -- 2
select estado from asistente.interruptor_autonomia
 order by creado_en desc limit 1;                                   -- 'detenido'
select count(*) from information_schema.tables
 where table_schema='public' and table_name like 'operaciones\_%';  -- 6
select count(*) from pg_policies
 where schemaname='public' and tablename like 'operaciones\_%';     -- 12
select app, name from django_migrations
 where (app='common' and name like '0039%')
    or (app='campo'  and name like '0003%');                        -- 2 filas
```

---

## G. Cambio de credenciales y recreación de servicios

**Las dos fases van separadas. Nunca a la vez** — si algo falla, hay que poder
decir cuál de las dos lo causó.

### FASE A — la credencial de migraciones

```bash
# en Dokploy: MIGRATOR_DBUSER=crm_migrator.<tenant-id>
#             MIGRATOR_DBPASSWORD=<la generada en el paso 6>
docker compose up -d --force-recreate backend
docker compose logs backend | grep "Running migrations"
# tiene que decir:  Running migrations as crm_migrator (separate credential)
```

Sólo `backend`: es el único que corre `entrypoint.sh`. `celery-worker` y
`celery-beat` arrancan `celery` directo y **no migran nunca** — verificado en los
dos composes.

### FASE B — la credencial de tráfico

```bash
# en Dokploy: DBUSER=crm_user.<tenant-id>  (y su DBPASSWORD)
docker compose up -d --force-recreate backend celery-worker celery-beat
```

**`MOTOR_DBUSER` no se toca en ningún paso.** `motor` y `motor-reloj` no se
recrean.

### Por qué `--force-recreate` y no `restart`

Medido en D: `restart` reinicia el contenedor con el entorno que ya tenía. La
variable nueva **no se aplica**, y el arranque parece normal. Con
`--force-recreate` el contenedor se crea de nuevo y sí la toma.

### Lo que garantiza el reparto (verificado en B.4 y B.5)

| Proceso | Credencial |
|---|---|
| `gunicorn` | tráfico |
| `celery-worker` / `celery-beat` | tráfico |
| `create_default_admin`, `collectstatic` | tráfico |
| **`migrate`** | **migraciones** |
| `motor`, `motor-reloj` | `MOTOR_DBUSER` |

El *override* es **por proceso** (`DBUSER=… comando`), no un `export`. Un
`export` habría dejado a gunicorn sirviendo como `crm_migrator`, que actúa como
dueño de las tablas y se saltea su política salvo `FORCE`.

---

## H. Verificaciones

### CRM

- [ ] Login por contraseña y por *magic link*
- [ ] Listado de casos devuelve filas (no vacío)
- [ ] Crear un caso · editarlo · comentar
- [ ] Actividades: la bitácora registra la creación
- [ ] Usuarios y perfiles: listado y edición
- [ ] Organizaciones: la propia se ve, y sólo la propia
- [ ] Endpoints principales: `/api/cases/`, `/api/accounts/`, `/api/contacts/`, `/api/tasks/`

### Celery

- [ ] `worker` — `manage.py check --database default` pasa
- [ ] `worker` — una tarea sobre tablas con RLS devuelve filas, **no cero en silencio**
- [ ] `beat` — arranca y programa (es el que falla más tarde y más callado)
- [ ] Ninguna tarea en la cola muerta

### Motor

- [ ] Conexión — `py -3.13 cli/diferencias_config.py rapilink` corre limpio
- [ ] Consultas — `py -3.13 cli/evaluar.py rapilink --humo --base`
- [ ] Scheduler / reloj — `motor-reloj` arriba y programando
- [ ] Acceso a `asistente` — se escribe una conversación de prueba y **queda**
- [ ] Aislamiento — `crm_user` sigue sin alcanzar `asistente`

### Seguridad

- [ ] `crm_user` **no** puede DDL → `must be owner of table`
- [ ] `crm_user` **no** puede crear roles → `permission denied to create role`
- [ ] `crm_user` **no** puede cambiar ownership
- [ ] `crm_user` **no** puede modificar RLS
- [ ] `crm_user` **no** puede crear tablas (tras el paso 11)
- [ ] `crm_migrator` **sí** puede migrar, y sus tablas quedan de `crm_owner`
- [ ] `crm_owner` es NOLOGIN → **el pooler no puede ni intentarlo**
- [ ] `motor_user` sigue separado: no administra `public`
- [ ] El interruptor dice `detenido`

---

## I. Rollback

| Situación | Acción | Pérdida |
|---|---|---|
| **Migración falla** | Django: `migrate <app> <anterior>`. Fase 1 no tiene reversa automática y no la necesita — **pero deshacerla reactiva la autonomía**, porque el motor vuelve a su excepción de «tabla ausente» | Ninguna |
| **Error de permisos** | `GRANT` puntual como `postgres`, que sigue siendo miembro de `crm_owner`. Si es sistemático, volver `DBUSER` | Ninguna |
| **El backend no inicia** | Volver `DBUSER` al valor del paso 1 + `up -d --force-recreate`. Es lo que se hizo el 18/08 y funcionó | Ninguna |
| **Celery falla** | Mismo `--force-recreate` con la variable anterior. `beat` puede necesitar purgar su agenda | Ninguna |
| **El motor falla** | `MOTOR_DBUSER` no se toca en ningún paso. Si aun así falla, comprobar que no se compartió con `${DBUSER}` — es el 18/08 | Lo que no se guardó en la ventana no se recupera |
| **Supavisor falla** (el rol nuevo no autentica) | Vaciar `MIGRATOR_*` + `--force-recreate`: el entrypoint vuelve a migrar con `DBUSER` | Ninguna |
| **RLS se comporta raro** | Volver `DBUSER` a `postgres`: con `BYPASSRLS` las políticas dejan de evaluarse y el servicio se restablece mientras se investiga | Ninguna |
| **Deshacer la transición entera** | `99_revertir_propiedad.sql` | Ninguna |
| **Se revocó `crm_owner` de `postgres` y hace falta DDL de emergencia** | `grant crm_owner to postgres;` ejecutado por el propio `postgres` — funciona gracias a la fila con `ADMIN OPTION` de `supabase_admin`. Si también se revocó ésa, sólo `supabase_admin` o el panel de Supabase pueden rehacerla. Medido en réplica (9.1) | Ninguna |

**Prioridad: restablecer servicio antes que deshacer.** Devolver la propiedad
**no** hace falta para que el CRM vuelva a funcionar: si el problema es el
arranque o las consultas, basta con volver `DBUSER`. La propiedad puede quedarse
en `crm_owner` sin molestar, porque `postgres` sigue siendo miembro.

**Rollback de propiedad, medido:** 129 tablas de vuelta, 963 objetos
(tablas + 51 secuencias + 783 índices) todos a `postgres`, **120 políticas y 903
`GRANT` intactos**. `ALTER TABLE … OWNER TO` es catálogo: no reescribe una fila.

---

## J. Criterios GO / NO-GO

### GO exige las cinco

1. `precheck.py` sale con **0**
2. El respaldo **restaurado** —los dos archivos— con filas, contenido y
   secuencias verificados (procedimiento completo en §B)
3. `DBUSER` confirmado como `postgres`
4. `crm_migrator` **autentica por el pooler** y devuelve `current_user=crm_owner`
5. Ventana acordada y alguien disponible para verificar **el motor**

Los cinco son comprobaciones **del momento del cambio**, no de ahora. Lo que ya
está establecido de antemano: el **3** se conoce (`DBUSER = postgres`, medido
sobre `pg_stat_statements`) pero se reconfirma en el paso 1; el **2** tiene un
procedimiento validado con datos reales (§B) y hay que volver a ejecutarlo sobre
el respaldo de ese día; el **4** tiene el mecanismo probado y sólo falta el rol.
Sin hacer **1, 2 y 5** en el momento, no hay GO por mucho que el diseño esté
validado.

### NO-GO inmediato

- El precheck sale con 1
- El respaldo no restaura, o restaura con menos `GRANT`/filas de los esperados
- `DBUSER` no es lo esperado
- Aparecen secuencias sueltas, vistas o triggers que el plan no contemplaba
- El recuento de tablas no coincide con el del precheck
- Hay tablas con RLS **sin** FORCE (tras mover la propiedad, el dueño se
  saltearía su política en ésas)

### Puntos de no retorno

**Ninguno hasta el paso 9.** Los pasos 1–8 no borran datos, no reescriben filas y
son reversibles. El 9 también lo es (`99_revertir_propiedad.sql`). Lo único
verdaderamente difícil de deshacer son las migraciones de Fase 1, y sólo porque
revertirlas **reactiva la autonomía**.

---

## K. Riesgos

| Riesgo | Nivel | Contención |
|---|---|---|
| **Respaldo mal tomado** — con `--no-owner` pierde los 903 `GRANT`; sin `asistente_ledger` no restaura; sin `pg_dumpall --roles-only` los dueños no existen | **CRÍTICO** | Corregido en §B, validado con datos reales en B.7 |
| **Restauración mal hecha** — el filtro del índice pierde los permisos del esquema, y el `SET role` de `crm_migrator` no viaja en ningún volcado | **CRÍTICO** | Hallazgos 5 y 6 de §B. Los dos salieron del simulacro del paso 9, no de leer el procedimiento |
| **Verificación que sólo comprueba existencia** — PostgreSQL no registra dependencia alguna del cuerpo de una función plpgsql, así que una referencia de esquema rota no se ve al restaurar: falla en la primera llamada. Es lo que dejó pasar `pgcrypto` en el esquema equivocado durante B.7, el simulacro del paso 9 y el paso 10 | **CRÍTICO** | `verificar_restauracion.py`: ejercita `job_claim → job_finalize`. Y `job_salud`/`jobs_vencidos` NO valen como prueba: responden con el scheduler roto |
| **`restart` en vez de `--force-recreate`** — la variable no se aplica y todo parece bien | **CRÍTICO** | Medido en D. La verificación es leer el log, no «arrancó» |
| **Transferencia parcial** — una tabla rezagada rompe una migración meses después | **CRÍTICO** | Un solo `DO`, una transacción, y la guarda del recuento |
| **Repetir el 18/08** — cambiar `${DBUSER}` y verificar sólo el CRM | **CRÍTICO** | Variables ya separadas; el checklist H verifica el motor aparte |
| **Revocar `crm_owner` de `postgres` como «limpieza»** — la credencial de emergencia queda sin poder reparar nada, y si además se revoca la fila de `supabase_admin` no puede ni recuperarse sola | ALTO | Documentado en §D y §I. Medido en réplica (9.1): el tráfico sobrevive, el DDL no |
| **Cargar `MIGRATOR_*` antes de crear el rol** | ALTO | El orden, y que las variables son opcionales |
| **`crm_migrator` sin `SET role`** — la propiedad derivaría de vuelta | ALTO | El paso 7 lo comprueba; el precheck también |
| **Las 11 tablas sin RLS** | ALTO | Deuda preexistente; fuera de alcance |
| **`CRM_CREDENCIALES_ESTRICTO` antes de tiempo** | MEDIO | Impide arrancar mientras `DBUSER` sea `postgres` |
| **`organization`, `users`, 2 `campo_*` sin columna de organización** | MEDIO | Decisión de diseño pendiente |
| **PostgreSQL 17.11 en el banco vs 17.6 real** | BAJO | Mismo *major* |

---

## L. Evidencia de pruebas

Todo contra **PostgreSQL 17.11** con el **esquema real de producción
restaurado** — 129 tablas, 60 con RLS+FORCE, 120 políticas, 903 `GRANT`.

| Prueba | Resultado |
|---|---|
| `pg_dump --schema-only` de producción | **0 errores**, 129 + 35 tablas |
| Restauración con dueños y privilegios | **0 errores**, 903 `GRANT` vueltos |
| Restauración con `--no-owner` | **0 `GRANT`** ← el hallazgo |
| **B.7 · respaldo completo con datos** | 8,8 MB, **0 errores**, 13 s |
| **B.7 · integridad del restaurado** | 164 tablas, 10.023 filas, 54 hashes idénticos, 51 secuencias |
| **B.7 · alcance de dos esquemas** | **falla**: `schema "asistente_ledger" does not exist` |
| **B.7 · extensiones en el volcado** | **0 entradas** — hay que instalarlas antes |
| **B.7 · roles en el volcado** | **0 entradas** — `pg_dumpall --roles-only` aparte |
| **B.7 · volcado de base completa** | **no restaurable** fuera de Supabase (`pg_net`) |
| **17/09 · simulacro del paso 9** | réplica exacta: 129 · 51 · 783 · 120 · 903 · 3 |
| **17/09 · transferencia sobre la réplica** | 11 de 11 verificaciones, 0 fallos |
| **17/09 · migración real como `crm_migrator`** | 4 migraciones aplicadas, 6 tablas de `crm_owner` |
| **17/09 · filtro antiguo del índice** | ACL del esquema perdido: `permission denied for schema public` |
| **17/09 · filtro corregido** | ACL idéntico a producción, `pg_restore --exit-on-error` = 0 |
| **B.7 · secuencias tras restaurar** | `INSERT` asigna 87 tras `last_value`=86 |
| **B.7 · RLS sobre datos restaurados** | 178 / 0 / 0 filas según el contexto |
| `restart` vs `up -d --force-recreate` | `[]` vs `[crm_migrator]` |
| `precheck.py` contra el banco | 22 datos, **NO-GO por respaldo**, salida 1 |
| `01_crear_roles.sql` | Los dos roles, con su comprobación en verde |
| `02_default_privileges.sql` | 3 entradas para `crm_user` |
| `03_transferir_propiedad.sql` | 129 tablas + 51 secuencias + 783 índices → `crm_owner` |
| Guarda del recuento (`-v esperadas=999`) | **Aborta**, como debe |
| `crm_migrator` conectando | `current_user=crm_owner`, `session_user=crm_migrator` |
| Tabla nueva creada por `crm_migrator` | Dueño **`crm_owner`** |
| `crm_user` sobre esa tabla | select/insert/update/delete **true**, secuencia **true** |
| `INSERT` real de `crm_user` | **Funciona** (`id=1`) |
| `ALTER TABLE` de `crm_user` | **`must be owner of table`** |
| `99_revertir_propiedad.sql` | 963 objetos a `postgres`, 120 políticas y 903 `GRANT` intactos |

Los volcados de esquema se borraron al terminar: no queda estructura de
producción en disco. Los contenedores desechables (`pg-b6`, `pg-b6b`) se
eliminaron.

### Suites

| Suite | Total | Pasan | Fallan |
|---|---|---|---|
| Regresión Django (B.4) | 3.728 | 3.685 | **0** |
| Suite del motor | 84 | 83 | 1 (`test_reloj.py`, preexistente) |
| Pruebas nuevas de B.4 | 55 | 55 | 0 |

---

## Archivos de esta etapa

**Nuevos:**

```
B6_PLAN_CAMBIO_CONTROLADO.md
despliegue/separacion_credenciales/precheck.py
despliegue/separacion_credenciales/01_crear_roles.sql
despliegue/separacion_credenciales/02_default_privileges.sql
despliegue/separacion_credenciales/03_transferir_propiedad.sql
despliegue/separacion_credenciales/99_revertir_propiedad.sql
```

**Modificados:** ninguno. B.6 no cambió una línea de código existente.

---

*B.6 es preparación. No se crearon roles reales, no se transfirió propiedad
real, no se cambió `DBUSER` real, no se aplicaron migraciones reales, no se
modificó RLS real y no se activó autonomía. Lo único que tocó producción fue un
`pg_dump` —operación de solo lectura, toma `ACCESS SHARE` y no bloquea— y consultas de catálogo
sobre una conexión marcada `read_only`.*
