# B-7 — FASE 2: SEGREGACIÓN PRODUCTIVA DE IDENTIDAD

## INFORME — BLOQUEADORES RESUELTOS Y PREPARACIÓN COMPLETA

Fecha: 2026-09-19

**El cambio de `DBUSER` productivo NO se ejecutó.** Dos de los tres bloqueadores
están resueltos con evidencia; el tercero (rotación del secreto JWT) requiere una
autorización y un acceso que no tengo, y por eso me detengo aquí, como pide el
cierre de su instrucción.

Sin commit. Sin autonomía. Sin tocar M09, M11 ni el kill switch. Sin limpieza
adicional de producción.

---

# 1. ESTADO DE LA TABLA ACCIDENTAL

**Eliminada.** Producción volvió a 135 tablas.

Procedimiento ejecutado, en el orden exigido:

| Paso | Exigido | Hecho |
|---|---|---|
| 1 | verificar que está vacía | `select count(*)` → **0 filas** |
| 2 | verificar dependencias | `pg_depend` (excl. índices/auto) → **0**; claves foráneas que la referencian → **0** |
| 3 | `DROP TABLE` **SIN CASCADE** | `drop table public."b7_no_deberia_existir"` — sin `CASCADE` |
| 4 | no cambiar permisos | ningún `GRANT`/`REVOKE`/`ALTER ROLE` |
| 5 | no usar `SET ROLE` | ninguno: la tabla era de `postgres` y se conectó como `postgres` |
| 6 | identidad administrativa ya autorizada | la del `.env` (`postgres.<sufijo>`), la misma que la creó |
| 7 | verificar que desapareció | `to_regclass(...)` → **None** |
| 8 | verificar 135 tablas | **135** por `pg_tables` **y** por `pg_class` |
| 9 | registrar evidencia | §3 |

No se eliminó ninguna otra tabla. No se hizo limpieza adicional.

> **Corrección a mi informe de Fase 1.** Ahí escribí que la tabla tenía «0 filas,
> 0 columnas». Las filas sí las había medido; **las columnas no**. Al medirlas
> antes del `DROP`: **1 columna** (`id int`, la del `create table
> b7_no_deberia_existir(id int)`). Afirmé un número que no había comprobado.

---

# 2. EVIDENCIA DE ELIMINACIÓN

Verificado con una conexión **nueva**, distinta de la que ejecutó el `DROP`, y
con solo lectura **efectiva** (§4):

```
transaction_read_only del servidor          : on
to_regclass('public.b7_no_deberia_existir') : None
tablas 'b7_*' en public                     : 0
tablas (pg_class, relkind='r') en public    : 135   (baseline 135)
tablas (pg_tables) en public                : 135   (baseline 135)
```

---

# 3. ESTADO FINAL DE TABLAS — BASELINE COMPLETO

```
tablas en public                 135    ok
tablas b7_*                      0      ok
roles                            41     ok
django_migrations                192    ok
tablas con RLS                   66     ok
tablas con FORCE RLS             66     ok
organization                     2      ok
case                             213    ok
activity (entity_type de operaciones)  0    ok
operaciones_actividad            0      ok
operaciones_propuesta_supervisor 0      ok
campo_orden_trabajo              3      ok
campo_mutacion_idempotente       14     ok

DIFERENCIAS CONTRA EL BASELINE: NINGUNA
```

Atributos de rol, sin cambios:

```
crm_migrator   super=False bypassrls=False createdb=False createrole=False login=True
crm_owner      super=False bypassrls=False createdb=False createrole=False login=False
crm_user       super=False bypassrls=False createdb=False createrole=False login=True
motor_user     super=False bypassrls=True  createdb=False createrole=False login=True
postgres       super=False bypassrls=True  createdb=True  createrole=True  login=True
```

`session_user` del runtime: **`postgres`** — sin cambiar, como corresponde.

---

# 4. PROCEDIMIENTO READ-ONLY CORREGIDO

## 4.1 El defecto, demostrado

No basta con decir que la combinación era incorrecta. Se le pregunta al
**servidor**:

| `conn.read_only` | `autocommit` | atributo local | `SHOW transaction_read_only` |
|---|---|---|---|
| `True` | `True` | dice `True` | **`off`** ← el atributo nunca llegó |
| `True` | `False` | dice `True` | **`on`** |
| `False` | `False` | dice `False` | `off` |

Causa: psycopg aplica `default_transaction_read_only` a las transacciones que
**él** abre. Con `autocommit=True` no abre transacción explícita, así que el
ajuste nunca se envía. El atributo local queda decorativo.

## 4.2 El procedimiento nuevo, obligatorio

```python
conn = psycopg.connect(...)            # SIN autocommit
conn.read_only = True
with conn.cursor() as c:
    c.execute("show transaction_read_only")
    assert c.fetchone()[0] == "on"     # ANTES de confiar en nada
```

Está aplicado en **todos** los scripts de esta fase: cada uno aborta si el
servidor no responde `on`.

## 4.3 Escritura de control — en objeto aislado, no en producción

Un rechazo, solo, no prueba nada: podría fallar por cualquier otra causa. Se
valida con la mitad complementaria, la misma prueba de desarme que se usó con RLS.
Ejecutado **en `pg-b7`**, sobre una tabla creada y borrada para eso:

```
1) crear objeto de prueba        transaction_read_only = off   -> creado
2) INSERT con read-only EFECTIVO transaction_read_only = on    -> [ok] rechazada:
                                    cannot execute INSERT in a read-only transaction
3) DESARME: el MISMO INSERT      transaction_read_only = off   -> [ok] aceptada
4) verificación independiente    transaction_read_only = on    -> 1 fila (solo la del paso 3)
5) limpieza                      to_regclass = None
```

El paso 3 es el que da valor al paso 2: la sentencia es válida, lo que la
bloqueaba era el read-only.

**No se creó ningún objeto de prueba en producción.**

---

# 5. SECRETO JWT — IDENTIFICADO, NO ROTADO

**El valor no aparece en este informe, ni en ningún log, ni se copió a ningún
lado.**

## 5.1 Identificación

| Dato | Valor |
|---|---|
| Tipo | secreto de firma **HS256** |
| Nombre | GUC `app.settings.jwt_secret` (junto a `app.settings.jwt_exp=3600`) |
| Mecanismo | `ALTER DATABASE postgres SET ...` → `pg_db_role_setting` |
| Alcance | **todos los roles**, base `postgres` |
| Forma | 32 caracteres, alfanumérico minúscula (el valor no se publica) |

## 5.2 ¿Es el secreto de firma de JWT de producción? **Sí, demostrado**

Sin mirarlo: se verificó la firma HS256 del `SUPABASE_SERVICE_ROLE_KEY` del
despliegue usando el secreto leído de la base.

```
SUPABASE_SERVICE_ROLE_KEY
   alg=HS256  role=service_role  iss=supabase  exp=1893456000  (2030-01-01)
   firma verificada con el secreto de la base: SÍ
```

Es el secreto de firma del plano de datos de Supabase.

## 5.3 Quién lo consume

Servicios medidos conectados a la base: **PostgREST 14.12** (rol `authenticator`),
**Realtime** (`supabase_admin`, 9 conexiones), **Storage**
(`supabase_storage_admin`) y **Supavisor**. Los esquemas `auth`, `storage`,
`realtime`, `graphql` y `supabase_functions` están presentes: es un Supabase
autohospedado completo.

**El CRM (Django) NO lo usa**: firma sus propios JWT con `SECRET_KEY`
(`OrgAwareRefreshToken`). Es un plano distinto.

**Ningún servicio de este repo lo lee**: `SUPABASE_SERVICE_ROLE_KEY` está en
`.env` y **no aparece en ningún archivo de código**. El stack de Supabase tampoco
está definido en `docker-compose.prod.yml` — es un despliegue aparte.

## 5.4 Quién puede leerlo

```
ACL de pg_catalog.pg_db_role_setting: supabase_admin=arwdDxtm/supabase_admin | =r/supabase_admin
                                                                               ^^^^ PUBLIC lee
crm_user=True  crm_migrator=True  motor_user=True  authenticator=True
anon=True  authenticated=True  app_backend=True
```

Un `SELECT` simple, con cualquier credencial de login sobre esta base.

## 5.5 Impacto potencial — y por qué afecta directamente a B-7

```
service_role   super=False  bypassrls=TRUE   login=False
   SELECT/INSERT/UPDATE/DELETE sobre 129 de 135 tablas de public
authenticator -> SET ROLE service_role : True
```

Quien lea el secreto puede firmar un JWT con `role: service_role` y, a través de
PostgREST, leer y escribir 129 tablas de negocio **saltándose RLS por completo**.

`[RIESGO CRÍTICO PARA EL OBJETIVO DE B-7]` El propósito de B-7 es que el runtime
deje de tener `BYPASSRLS`. Pero `crm_user` **puede leer este secreto**: un
`SELECT` y un HMAC devuelven exactamente el privilegio que B-7 quita.

**Sería falso presentar B-7 como «el runtime ya no puede saltarse RLS» mientras
este secreto siga siendo legible por el rol del runtime.** B-7 sigue valiendo la
pena (cierra la vía directa y es defensa en profundidad), pero no cierra esta.

## 5.6 Un hallazgo que simplifica la solución

**Ninguna función SQL de esta base lee el GUC.** Medido sobre `pg_get_functiondef`
de todas las funciones no-C: cero coincidencias con `app.settings.jwt`. `pgjwt` no
está instalada (las únicas `sign` son `pg_catalog.sign`, la función matemática).
Tampoco hay GUC `pgrst.*` de configuración en base.

Es decir: **dentro de la base, el GUC es una copia del secreto que nadie usa y
todos pueden leer.**

`[LÍMITE HONESTO]` Puedo demostrar que ninguna función **de la base** lo lee. **No
puedo demostrar que ningún servicio externo lo lea por SQL** — Realtime lo hacía
en versiones antiguas. Comprobarlo exige ver la configuración del stack de
Supabase en Dokploy.

## 5.7 Procedimiento oficial de rotación

Supabase autohospedado: el secreto vive en la variable `JWT_SECRET` del
despliegue, no en la base.

1. Generar un secreto nuevo (≥40 caracteres) **con el gestor de secretos**, no a
   mano en un archivo.
2. Poner `JWT_SECRET` en el despliegue de Supabase (Dokploy): `kong`, `auth`
   (GoTrue), `rest` (PostgREST), `realtime`, `storage`.
3. **Regenerar `ANON_KEY` y `SERVICE_ROLE_KEY`**: son JWT firmados con ese
   secreto; con el secreto nuevo, los viejos dejan de validar.
4. Actualizar `SUPABASE_SERVICE_ROLE_KEY` donde esté guardado (`.env` del
   despliegue) — **nunca en código, nunca en SQL**.
5. Reiniciar los servicios de Supabase.
6. Aparte y por separado: decidir si el GUC `app.settings.jwt_secret` debe seguir
   existiendo (§5.6). Si se conserva, hay que actualizarlo también; si se retira,
   `ALTER DATABASE postgres RESET app.settings.jwt_secret`.

## 5.8 Impacto de la rotación — documentado ANTES de ejecutar, como exige la instrucción

| Se invalida | Alcance |
|---|---|
| `SERVICE_ROLE_KEY` y `ANON_KEY` actuales | todo consumidor que los tenga guardados |
| Sesiones emitidas por GoTrue (`auth`) | si hay usuarios autenticados por Supabase Auth, se les cae la sesión |
| Conexiones de Realtime autenticadas por JWT | se reconectan con el token nuevo |
| **Sesiones y tokens del CRM (Django)** | **NO se ven afectadas** — usan `SECRET_KEY`, otro secreto |
| Motor ↔ base (`motor_user`) | **NO se ve afectado** — es conexión PostgreSQL directa, no JWT |

El único consumidor identificable del lado de este repo es
`SUPABASE_SERVICE_ROLE_KEY` en `.env`, **que ningún código lee**. El riesgo real
está del lado del stack de Supabase, que no puedo inspeccionar.

## 5.9 Estado: **NO ROTADO — me detengo aquí**

`[DETENCIÓN REPORTADA]` No ejecuté la rotación, por dos motivos concretos:

1. **No tengo acceso a Dokploy.** Quedó establecido en Fase 1: por eso el
   `DBUSER` efectivo hubo que medirlo desde la base en vez de leerlo del
   despliegue. El mecanismo oficial de rotación vive ahí.
2. **Una rotación parcial sería una caída, no una rotación.** Cambiar solo el GUC
   en la base, o solo `JWT_SECRET` en un servicio, deja el stack firmando con un
   secreto y verificando con otro. Eso es una interrupción de servicio.

Su instrucción dice: *«No hacer una rotación ciega de un secreto cuya función no
haya sido identificada»* — la función **está** identificada — y *«Si una operación
productiva requiere una autorización adicional no contemplada aquí, detenerse y
reportarla»*. Es este caso: la operación está fuera de la base de datos, en un
despliegue al que no llego.

`[DECISIÓN]` Necesito de usted: acceso a Dokploy o que ejecute usted §5.7, y una
decisión sobre §5.6 (retirar el GUC).

---

# 6. FORCE RLS

**Intacto. No se tocó.**

```
tablas con RLS      : 66 de 135
tablas con FORCE RLS: 66 de 66
```

No se desactivó RLS en ninguna tabla. No se quitó `FORCE` de ninguna. No se
concedió `BYPASSRLS` a `crm_user` — y la medición de §3 lo confirma:
`crm_user bypassrls=False`.

La arquitectura aprobada queda como usted la fijó:

```
RUNTIME      Django -> crm_user     -> RLS / FORCE RLS
MIGRACIONES  proceso -> crm_migrator -> operación administrativa controlada
```

---

# 7. `crm_user`

Sin cambios en producción: `super=False bypassrls=False createdb=False
createrole=False login=True`, dueño de 0 tablas, `CREATE` en `public` = False,
`USAGE` en `asistente` = False.

`EXECUTE` sobre funciones de `public`: **149 de 149** (vía los `ALTER DEFAULT
PRIVILEGES` ya existentes).

Privilegios de más, ya reportados en Fase 1 y **todavía sin corregir** porque
corregirlos es un cambio productivo:

| Privilegio | Producción | Necesario (medido) |
|---|---|---|
| `TRUNCATE` | 130/135 | **0** |
| `REFERENCES` | 130/135 | **0** |
| `TRIGGER` | 130/135 | **0** |
| secuencias `UPDATE` | 51/51 | **0** — basta `USAGE` |

La prueba de que sobran no es un argumento: el entorno aislado corre con
`TRUNCATE=0`, `REFERENCES=0`, `TRIGGER=0` y secuencias sin `UPDATE`, y **pasa los
18 ítems**. Además el ítem 15 demuestra el borde exacto: `nextval` funciona con
solo `USAGE`, y `setval` —que sí necesita `UPDATE`— queda **bloqueado**.

---

# 8. `crm_migrator`

**No se creó. Ya existe.** No se recreó ningún rol.

```
super=False  bypassrls=False  createdb=False  createrole=False  login=True
miembro de crm_owner
ALTER ROLE crm_migrator IN DATABASE postgres SET role = crm_owner
```

## 8.1 ¿Necesita `BYPASSRLS`? **No. Y dárselo no serviría.**

Su bloque 6 pide demostrar que no existe alternativa más restrictiva antes de
conceder nada. La demostración, en el entorno aislado, con 9 filas repartidas en
4 organizaciones:

| Camino | `BYPASSRLS` | expected | matched | updated | verified | Veredicto |
|---|---|---|---|---|---|---|
| **A.** backfill ingenuo, sin contexto | no | 9 | 0 | 0 | 0 | **el conteo lo detecta como fallo** |
| **B.** backfill por organización | **no** | 9 | **9** | **9** | **9** | alcanza todas las filas |
| **C.** desarme: con `BYPASSRLS` en `crm_migrator` | sí | 9 | **0** | **0** | **0** | **no cambió nada** |

El resultado de C no era el esperado, así que lo investigué en vez de anotarlo:

```
¿Sobre QUÉ rol se evalúa BYPASSRLS?
  estado inicial                     current_user=crm_owner (bypassrls=False) -> ve 0 filas
  BYPASSRLS en crm_migrator          current_user=crm_owner (bypassrls=False) -> ve 0 filas
  BYPASSRLS en crm_owner             current_user=crm_owner (bypassrls=TRUE ) -> ve 4 filas
```

**`BYPASSRLS` se evalúa sobre `current_user`, no sobre `session_user`.** Con
`SET role = crm_owner` activo, `current_user` es `crm_owner`. Por eso:

`[HALLAZGO]` **Conceder `BYPASSRLS` a `crm_migrator` no tiene ningún efecto.**
Para que funcionara habría que dárselo a `crm_owner`, el dueño de las 135 tablas
— un privilegio mucho más amplio y permanente.

Esto **corrige la opción (b) que yo mismo propuse en el informe de Fase 1**
(«conceder `BYPASSRLS` a `crm_migrator` solo durante la migración»). No es
indeseable: es **inoperante**.

Respuesta a los cinco puntos de su bloque 6:

1. **Existe alternativa más restrictiva**: fijar `app.current_org` por
   organización. Demostrada, 9/9/9.
2. **Ninguna operación lo exige**: las migraciones de estructura ya funcionan sin
   él (135 tablas creadas, RLS estampado); las de datos funcionan con contexto.
3. **Ni permanente ni temporal**: no corresponde concederlo.
4. N/A.
5. **No se copió al runtime**: `crm_user bypassrls=False`, medido.

Los roles del entorno aislado quedaron revertidos a `bypassrls=False`.

---

# 9. PERMISOS

Ningún `GRANT` ni `REVOKE` en producción durante esta fase. Los cuatro `REVOKE`
propuestos (§7) siguen **propuestos, no aplicados**.

Juego mínimo demostrado suficiente (entorno aislado, 18/18):

```sql
GRANT USAGE ON SCHEMA public TO crm_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO crm_user;
```

Siete operaciones administrativas, las siete bloqueadas (ítem 12).

---

# 10. RUNTIME

Cubierto por el smoke de 18 ítems (§12), **entero como `crm_user`**:

```
current_user=crm_user  session_user=crm_user  rolsuper=False  rolbypassrls=False
```

Los 17 puntos que exige su bloque 7 están cubiertos: login, health, lectura,
escritura, transacciones, rollback, **locks**, **secuencias**, **funciones**,
actividades, casos, programación, propuestas Supervisor, reportes, **scheduler**,
tenant isolation, RLS.

**No se inspeccionaron grants como sustituto de ejecutar.** Cada ítem ejecuta la
operación real y verifica su efecto.

---

# 11. POOLER

Sin cambios. Lo medido en Fase 1 sigue vigente y no se repitió contra producción
para no abrir conexiones innecesarias:

- Supavisor **quita el sufijo de tenant**: `crm_migrator.<sufijo>` entra como
  `session_user = crm_migrator`.
- El `SET ROLE` de `ALTER ROLE ... IN DATABASE` **sobrevive al pooler**:
  `current_user = crm_owner`.
- `DBPORT=5433` = **session mode**. Crítico: `app.current_org` es de alcance de
  sesión. **El puerto no debe tocarse en el cambio productivo.**

---

# 12. SMOKE TEST — 18 de 18

```
=== SMOKE TEST B-7: 18/18 items OK ===
```

| # | Ítem | Resultado |
|---|---|---|
| 1 | login | HTTP 200, token emitido |
| 2 | health | anónimo 403 (idéntico como superusuario: no depende de la identidad) · autenticado 200 |
| 3 | listar casos | HTTP 200, `cases_count=5` |
| 4 | crear/editar | INSERT y UPDATE persistidos, verificado con conexión independiente |
| 5 | actividades | creada + asignada + iniciada, estado `en_gestion` persistido |
| 6 | programación | vía `reprogramar_orden`, línea persistida, jornada con 1 línea |
| 7 | propuestas Supervisor | ciclo Shadow Mode completo, propuestas leídas por conexión independiente |
| 8 | reportes | 5 reportes generados |
| 9 | tenant isolation | ORG-B tiene 1 caso; con contexto MicroPyramid el ORM ve **0**; fuga por HTTP **0** |
| 10 | transacción (commit) | 1 fila tras commit |
| 11 | rollback | 0 filas tras rollback |
| 12 | permisos | 7 de 7 operaciones administrativas bloqueadas |
| 13 | RLS | sin BYPASSRLS; 0 filas sin contexto; UPDATE cruzado 0; INSERT cruzado rechazado; FORCE en todas |
| **14** | **locks** | `select_for_update`: otra conexión **rebota con NOWAIT**; `pg_advisory_xact_lock`: otra conexión no lo consigue; **se libera** al cerrar la transacción |
| **15** | **secuencias** | `USAGE=True UPDATE=False`; `nextval` 3→4; **`setval` bloqueado** |
| **16** | **funciones** | `set_config`, `gen_random_uuid`, `hashtext`, `pg_advisory_xact_lock`, `current_user` ejecutan; sin `USAGE` en `asistente` |
| **17** | **scheduler** | `check_overdue_invoices()` (tarea real de beat) corre; **no deja contexto residual**; `set_rls_context`/`clear_rls_context` fijan y limpian |
| **18** | **backfill con conteo verificable** | con contexto 3/3/3 → ÉXITO; sin contexto 0/0/0 → **DETECTADO COMO FALLO** |

Notas de honestidad sobre dos ítems:

- **Ítem 14**: el lock no se da por bueno porque la llamada no falle. Se comprueba
  desde **otra conexión** con `FOR UPDATE NOWAIT`, que debe rebotar, y luego que
  el advisory lock **se libere** al cerrar la transacción. Un lock que no suelta
  es tan defectuoso como uno que no toma.
- **Ítem 16**: el entorno aislado **no tiene el esquema `asistente`** (es del
  motor). En vez de inventar un resultado, el ítem lo declara y remite a la
  medición de producción: `crm_user` `USAGE=False` **[medido]**.

---

# 13. MIGRACIONES

Flujo separado, confirmado:

```
APLICACIÓN   -> crm_user
MIGRACIONES  -> crm_migrator (actúa como crm_owner)
APLICACIÓN   -> postgres        NUNCA
```

El mecanismo ya existe en el repo (`docker/backend/entrypoint.sh`): con
`MIGRATOR_DBUSER` definido, el override vale **solo** para `migrate`, y gunicorn
arranca después con la credencial de tráfico. En producción esas dos variables
están **vacías**: el mecanismo está escrito y sin usar.

La guarda `verificar_credenciales` acierta en las cuatro combinaciones
(`crm_user`+tráfico ✓, `crm_user`+migraciones ✗, `crm_migrator`+tráfico ✗,
`crm_migrator`+migraciones ✓) y **aborta al arrancar**, no a mitad de una
migración.

## Qué operaciones de migración requieren de verdad privilegio elevado

| Operación | ¿Necesita elevación? | Evidencia |
|---|---|---|
| `CREATE TABLE` / `ADD COLUMN` / índices | sí, ser dueño | 135 tablas creadas como `crm_migrator` |
| `ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY` | sí, ser dueño | RLS estampado correctamente |
| `CREATE POLICY` / `DROP POLICY` | sí, ser dueño | 66 tablas con 2 políticas |
| **`RunPython` que escribe filas** | **no necesita elevación: necesita CONTEXTO** | §8.1, 9/9/9 sin `BYPASSRLS` |
| `CREATE EXTENSION` | sí (superusuario) | **ninguna migración pendiente lo pide** |
| `SUPERUSER` | **nunca** | ninguna migración lo necesitó |

---

# 14. BACKFILL

Contrato implementado y demostrado, tal como lo define su bloque 5:

```
expected = cuántas filas debería tocar
matched  = cuántas VE la sesión (aquí muerde RLS)
updated  = cuántas afectó el UPDATE (rowcount)
verified = cuántas quedaron efectivamente con el valor nuevo, releídas
```

Regla: si `updated != expected` **o** `verified != expected`, **no es éxito**.

Demostrado en dos formas independientes:

- **Ítem 18 del smoke**: con contexto 3/3/3 → ÉXITO; sin contexto 0/0/0 →
  **detectado como fallo**, no convertido en éxito silencioso.
- **§8.1**, 9 filas en 4 organizaciones: el backfill por organización llega a
  **9/9/9** sin `BYPASSRLS`, y el ingenuo da 0 y queda marcado como fallo.

El `UPDATE 0` no se oculta: se informa y se marca.

---

# 15. CAMBIO PRODUCTIVO

## **NO EJECUTADO.**

Su bloque 9 empieza con «SOLO después de que todos los puntos anteriores estén en
GO». El punto 3 (secreto JWT) **no está en GO**: el secreto está identificado
pero **no rotado**, y rotarlo requiere acceso a Dokploy (§5.9).

Por tanto `DBUSER` sigue en `postgres.<sufijo>`. Medido al cerrar:
`session_user = postgres`.

Los pasos 1 a 6 de su secuencia **sí** están hechos y documentados; los pasos 7 a
17 quedan pendientes de su autorización:

| Paso | Estado |
|---|---|
| 1. snapshot/evidencia previa | **HECHO** (§3) |
| 2. verificar identidad actual | **HECHO** — `postgres`, `bypassrls=True` |
| 3. verificar `crm_user` | **HECHO** — §7, §12 (18/18) |
| 4. verificar migraciones | **HECHO** — §13 |
| 5. verificar secreto JWT | **HECHO** (identificado) — **rotación PENDIENTE** |
| 6. confirmar rollback | **HECHO** (documentado) — §16 |
| 7–17. cambiar `DBUSER` y verificar | **NO EJECUTADO** |

---

# 16. ROLLBACK

Sin cambios respecto al diseño de Fase 1, que sigue vigente:

- **Condición**: la aplicación no inicia; un `permission denied`/`must be owner`
  bloquea una operación real; RLS rompe una operación legítima no detectada; el
  scheduler crítico no funciona; un ítem crítico del smoke falla.
- **No** es condición: un error puntual en una ruta no crítica cuyo permiso
  concreto esté identificado. Ahí se concede **ese** permiso, que es lo que pide
  el bloque G («determinar exactamente qué permiso falta»). Tampoco se hace
  rollback por métricas cosméticas.
- **Qué se revierte**: solo configuración — `DBUSER`/`DBPASSWORD` a
  `postgres.<sufijo>` y reiniciar backend, Celery worker y Celery beat.
- **Sin `DROP`**: no se crean roles ni tablas ni se eliminan políticas. Los
  `REVOKE` de §7, si se aplican, **no hace falta deshacerlos**: `postgres` no
  depende de los grants de `crm_user`.
- **Quién**: quien tenga Dokploy. No yo.
- **Verificación**: `verificar_credenciales --proposito trafico --con-base` → 0;
  `pg_stat_activity` muestra `postgres`; los ítems de solo lectura del smoke;
  contadores de §3 sin cambios.
- **Evidencia**: `DBUSER` anterior, hora del cambio y del reinicio, primer error
  con texto completo, y **el permiso exacto que faltó** si esa fue la causa.

`[RIESGO]` **Sigue siendo un rollback documentado, no probado.** Probarlo exige
ejecutar el cambio productivo. Lo que sí está demostrado es que el camino de ida
funciona (18/18) y que la vuelta son dos variables de entorno y un reinicio.

---

# 17. PRODUCCIÓN

Escrituras productivas en esta fase: **una**, la autorizada.

| Operación | Autorización | Reversible | Registrada |
|---|---|---|---|
| `DROP TABLE public.b7_no_deberia_existir` sin `CASCADE` | explícita, bloque 1 | no aplica (restaura el estado previo) | §1, §2 |

Todo lo demás contra producción fue **solo lectura, con `transaction_read_only =
on` verificado en el servidor** antes de cada consulta.

Cumplimiento del bloque 11:

- No se crearon tablas de prueba en producción. ✓
- No se crearon roles de prueba. ✓
- No se ejecutó ningún `UPDATE` de prueba sobre tablas de negocio. ✓
- No se usó producción para demostrar RLS: **todas** las pruebas de RLS, locks,
  backfill y escritura de control corrieron en `pg-b7`. ✓
- No se hizo limpieza adicional. ✓

Se abrió **una** conexión como `crm_migrator` con la clave del archivo externo,
de solo lectura efectiva, para una única consulta de identidad. La clave nunca se
imprimió.

---

# 18. AUTONOMÍA

**Sin tocar.** No se activó autonomía. No se modificó el nivel de autonomía, el
kill switch, `PropuestaSupervisor`, M09, M11 ni ninguna tool.

El defecto heredado del kill switch (`motor_user` no puede
`SET ROLE autonomia_operador`; `asistente.autonomia_detener()` existe, está
concedida a `app_backend` y **no está cableada a la ruta**) sigue abierto,
reportado y **sin parchear**. B-7 no lo toca.

---

# 19. RIESGOS

| # | Riesgo | Evidencia | Impacto | ¿Bloquea? |
|---|---|---|---|---|
| R1 | Tabla accidental en producción | §1, §2 | — | **RESUELTO** |
| R2 | Procedimiento read-only inefectivo | §4 | — | **RESUELTO** |
| R3 | **Secreto JWT legible por `crm_user`; permite firmar `service_role` (BYPASSRLS + DML en 129/135 tablas)** | §5.4, §5.5 | **Crítico: anula el objetivo de B-7** | **SÍ** |
| R4 | Secreto expuesto en la transcripción de la sesión anterior | §5 | Alto | **SÍ** (exige rotación) |
| R5 | Migraciones de datos futuras con `UPDATE 0` silencioso | §14 | Alto | **MITIGADO** por el contrato expected/matched/updated/verified — pero hay que aplicarlo en cada migración |
| R6 | `crm_user` con `TRUNCATE`/`REFERENCES`/`TRIGGER` y `UPDATE` de secuencias de más | §7 | Medio | No, pero corregir en el cambio |
| R7 | 69 tablas sin RLS | Fase 1 §9.5 | Medio | No |
| R8 | `motor_user` con `BYPASSRLS` | §3 | Medio | No (fuera del alcance) |
| R9 | Kill switch sin cablear a la ruta | §18 | Alto **si se activa autonomía** | No (autonomía detenida) |
| R10 | Default `DBUSER="postgres"` en `settings.py` | Fase 1 §3 | Medio | No |
| R11 | Rollback documentado, no probado | §16 | Medio | No |
| R12 | Si alguien cambiara `DBPORT` a 6544 (transaction mode), `app.current_org` se filtraría entre tenants | §11 | Crítico | No — **no tocar el puerto** |
| R13 | `/healthz/` responde 403 sin autenticación | §12 | Bajo | No |

---

# 20. GO / NO-GO

## **NO-GO** para el cambio productivo de `DBUSER`.

Su lista de verificación, punto por punto:

| | Criterio | Estado |
|---|---|---|
| ✅ | tabla accidental eliminada | §1, §2 |
| ✅ | producción vuelve a 135 tablas | §3 — DIFERENCIAS: NINGUNA |
| ✅ | procedimiento read-only corregido | §4, con prueba de desarme |
| ✅ | secreto JWT evaluado | §5 — identificado de forma decisiva |
| ❌ | **secreto rotado si corresponde** | **Corresponde. NO rotado — requiere Dokploy (§5.9)** |
| ✅ | FORCE RLS permanece | §6 — 66/66 |
| ⚠️ | `crm_user` no tiene privilegios innecesarios | **Tiene 4 de más** (§7). Medido que sobran; `REVOKE` no aplicado |
| ✅ | runtime pasa smoke test | §12 — 18/18 |
| ✅ | migraciones separadas | §13 |
| ✅ | backfill con conteo verificable | §14 |
| ✅ | RLS probado | §12 ítem 13, con desarme |
| ✅ | tenant isolation probado | §12 ítem 9 |
| ✅ | pooler probado | §11 — medido, no inferido |
| ❌ | `DBUSER` efectivo = `crm_user` | **No ejecutado** (depende de lo anterior) |
| ⚠️ | rollback probado/documentado | **Documentado**; probarlo exige el cambio |
| — | producción estable | sin cambios que puedan desestabilizarla |

**Un punto crítico falla: la rotación del secreto.** Y no la compenso ampliando
privilegios ni saltándome el criterio: me detengo.

## Lo que necesito de usted, en orden

1. **`[BLOQUEANTE]` Rotar el secreto JWT** por §5.7 — acceso a Dokploy o que lo
   ejecute usted. El impacto está documentado en §5.8 **antes** de ejecutar, como
   pidió.
2. **`[DECISIÓN]`** Si se retira el GUC `app.settings.jwt_secret` de la base
   (§5.6): ninguna función de la base lo usa, pero no puedo descartar un
   consumidor externo sin ver la configuración del stack de Supabase.
3. **`[DECISIÓN]`** Aplicar o no los cuatro `REVOKE` sobre `crm_user` (§7).
4. **`[DECISIÓN]`** Ventana de cambio, y autorización explícita para los pasos 7
   a 17 del bloque 9.

Con eso hecho, el cambio productivo es: poner `DBUSER`/`DBPASSWORD` de
`crm_user`, poblar `MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD`, reiniciar los tres
procesos y correr el smoke. No hay roles que crear, ni migraciones que aplicar,
ni puerto que tocar.

---

## RESUMEN EJECUTIVO

**Dos bloqueadores resueltos, uno detenido.**

La tabla que creé por error **ya no está**: verificada vacía y sin dependencias,
`DROP` sin `CASCADE`, con la identidad que ya la había creado, sin tocar un solo
permiso. Producción volvió a 135 tablas y el baseline completo da **DIFERENCIAS:
NINGUNA**.

El procedimiento de solo lectura está corregido y **demostrado en las dos
direcciones**: el servidor dice `transaction_read_only=off` con la combinación
vieja y `on` con la nueva, y la escritura de control confirma que lo que bloquea
es el read-only y no otra cosa. Esa prueba corrió en el entorno aislado, no en
producción.

El secreto JWT quedó identificado sin mirarlo: **verifica la firma HS256 del
`SUPABASE_SERVICE_ROLE_KEY` de producción**. Y lo que encontré al medir el impacto
importa más que el secreto en sí: `crm_user` puede leerlo, y con él se firma un
token `service_role` que tiene `BYPASSRLS` y escritura sobre 129 de 135 tablas.
**Eso devuelve, por otra puerta, exactamente el privilegio que B-7 quita.** No
rotarlo no es una formalidad pendiente: es la diferencia entre que B-7 cumpla su
objetivo o solo lo parezca. No pude rotarlo — el mecanismo oficial vive en
Dokploy, al que no tengo acceso — así que me detengo y lo reporto, con el impacto
documentado de antemano.

En el camino, dos hallazgos que corrigen cosas que yo mismo había escrito:
**`BYPASSRLS` se evalúa sobre `current_user`**, así que dárselo a `crm_migrator`
—una de las opciones que propuse en Fase 1— **no habría hecho nada**; y la
alternativa restrictiva sí funciona, medida: un backfill por organización alcanza
**9 de 9** filas en 4 organizaciones sin ningún privilegio extra.

El runtime está listo: **18 de 18** ítems, entero como `crm_user`, incluidos
locks verificados desde otra conexión, `nextval` con solo `USAGE` (y `setval`
bloqueado), una tarea real del scheduler que no deja contexto pegado, y un
backfill que **detecta** el `UPDATE 0` en vez de darlo por bueno.

**`DBUSER` sigue en `postgres`.** El cambio productivo no se ejecutó y no debe
ejecutarse hasta rotar el secreto.

---

**No se hizo commit. No se activó autonomía. No se modificó M09 ni M11. No se
tocó el kill switch. No se hizo limpieza adicional de producción.**
