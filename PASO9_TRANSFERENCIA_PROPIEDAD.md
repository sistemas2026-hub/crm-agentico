# Paso 9 — Transferencia de propiedad de las 129 tablas

**Fecha:** 17/09/2026
**Alcance autorizado:** exclusivamente la transferencia de propiedad de las 129
tablas de `public`, de `postgres` a `crm_owner`.
**Resultado:** ejecutado, verificado, **sin rollback**. 10/10 comprobaciones.

---

## 1. Lo que se ejecutó

```
psql ... -c "set lock_timeout = '10s'" \
         -v ON_ERROR_STOP=1 -v esperadas=129 \
         -f despliegue/separacion_credenciales/03_transferir_propiedad.sql
```

El `lock_timeout` se fijó **en la sesión, con un `-c` aparte**, sin tocar el
script ya validado en desechable: si alguna tabla hubiera estado bloqueada, la
transacción abortaba en 10 s en vez de encolar el tráfico del CRM detrás de un
`ACCESS EXCLUSIVE`.

Salida:

```
a mover: 129 tabla(s) de public
transferidas 129 tabla(s) a crm_owner
OK: 0 tablas bajo postgres, 0 bajo una credencial con login
CODIGO DE SALIDA: 0    duracion: 3 s
```

### Precondiciones, todas cumplidas antes de ejecutar

| Precondición | Evidencia |
|---|---|
| Respaldo fresco | `paso9_20260917_094215_datos.dump` (8.841.942 bytes) + `paso9_20260917_094215_roles.sql` (25 roles) |
| Respaldo **restaurado y verificado** | Desechable `pg-p9`: `pg_restore` exit 0 → 129 tablas, 51 secuencias, 783 índices, 120 políticas, 903 GRANT. Coincidencia exacta. Contenedor eliminado |
| Precheck | `0 critico(s), 1 aviso(s), 23 dato(s)`, exit 0 |
| 129 tablas objetivo | `{'postgres': 129}`, "A TRANSFERIR (dueno=postgres): 129" |
| Ventana limpia | 0 transacciones abiertas, 0 bloqueos sobre `public`, 0 actividad del CRM en 15 min |

---

## 2. Las diez verificaciones

| # | Punto | Resultado |
|---|---|---|
| 1 | 129 tablas propiedad de `crm_owner` | **129/129** — `{'crm_owner': 129}` |
| 2 | 0 tablas objetivo bajo `postgres` | **0**. Ninguna credencial con LOGIN es dueña de nada |
| 3 | 51 secuencias correctas | **51/51** de `crm_owner`; 0 sueltas; `crm_user` conserva USAGE en las 51 |
| 4 | 783 índices intactos | **783/783** de `crm_owner`; 0 inválidos; 409 claves foráneas siguen declaradas |
| 5 | 120 políticas RLS intactas | **120**; 60 tablas con RLS activa; **60 con FORCE** |
| 6 | 903 GRANT a `crm_user` intactos | **903**; SELECT/INSERT/UPDATE/DELETE concedidos en **129/129** |
| 7 | El CRM puede SELECT/INSERT/UPDATE | **Sí** — 185 casos leídos, INSERT+UPDATE aplicados y revertidos |
| 8 | `crm_user` no puede ALTER TABLE | **No puede** — no es superusuario, no es dueño, y no puede asumir el rol dueño de ninguna de las 129 |
| 9 | `crm_migrator` mantiene `current_user = crm_owner` | **Sí** por el pooler: `current_user=crm_owner`, `session_user=crm_migrator`; ALTER TABLE permitido (revertido) |
| 10 | Nada fuera del alcance | 0 migraciones aplicadas; `asistente`/`asistente_ledger` sin cambios; 0 vistas; 3 default privileges; 5 roles con atributos idénticos |

Y en vivo, después del cambio: `crm.rapilinksas.co` HTTP 401, el admin de Django
302, el frontend 200, y `motor_user` —una credencial que estos scripts nunca
usan— ejecutando consultas 102 s después de la transferencia. `deadlocks=0`,
`conflictos=0`.

---

## 3. Los cuatro fallos que reportó la primera pasada, y por qué no eran del cambio

La primera corrida del verificador marcó **4 fallas**. Ninguna resultó ser de la
transferencia; las cuatro eran de mi propio método. Se diagnosticaron en solo
lectura **antes** de decidir un rollback, porque revertir una transferencia
correcta por una carencia del arnés habría sido, en sí mismo, otro cambio no
autorizado en producción.

### 3.1 Tres fallas: `permission denied to set role "crm_user"`

El verificador probaba el DML y el DDL de `crm_user` con `set local role
crm_user` desde la conexión de `postgres` — que es exactamente como funcionó en
el simulacro. En producción no funciona, y la causa está **en el respaldo tomado
antes de la transferencia**:

```
GRANT crm_user TO postgres WITH ADMIN OPTION, INHERIT FALSE, SET FALSE GRANTED BY supabase_admin;
```

`SET FALSE`. PostgreSQL 16+ separa la membresía (`MEMBER`, que hereda
privilegios) de la capacidad de hacer `SET ROLE`, y `supabase_admin` otorga cada
rol nuevo a `postgres` sin ninguna de las dos. En el desechable no se vio porque
allí `postgres` **sí** es superusuario; en Supabase, `rolsuper = false`.

Consecuencias que importan:

- **La falla es anterior al paso 9.** La transferencia no toca `pg_auth_members`
  ni `rolsuper`.
- **El punto 8 "pasó" por el motivo equivocado** en la primera pasada: el ALTER
  falló, sí, pero por el `set role` denegado, no por falta de propiedad. Un
  `[ok]` espurio, del tipo contra el que advierte CLAUDE.md — una prueba que
  afirma sobre el mecanismo equivocado sobrevive intacta a que el mecanismo real
  esté roto. Se rehizo.
- Se sustituyó por la comprobación que sí decide: `ALTER TABLE` exige ser el
  dueño, ser miembro del rol dueño, o ser superusuario. `crm_user` no cumple
  **ninguna de las tres** — 0 de 129 tablas cuyo dueño puede asumir. Es una
  prueba completa, no un sustituto.
- El punto 7 se rehizo contra **la credencial que el CRM usa hoy de verdad**
  (`postgres`), que es lo que responde si producción sigue en pie.

### 3.2 Una falla: "tablas de `asistente` fuera de postgres: 5"

Afirmé `0` sin haberlo medido nunca. Son `job_attempt`, `job_catalogo`,
`job_run`, `job_run_event` y `job_schedule_state`, propiedad de
**`asistente_owner`** — y `pg_restore -l` sobre el respaldo **previo** a la
transferencia las muestra con ese mismo dueño. Estado preexistente; el paso 9
sólo filtró por `nspname = 'public'`.

De paso confirma algo útil: el scheduler del asistente ya usaba exactamente este
patrón (rol dueño sin login, separado de la credencial de tráfico) desde antes.

### 3.3 Un error más, en el diagnóstico

La consulta de secuencias puso `has_sequence_privilege(...)` y el filtro
`relkind='S'` en el mismo `WHERE`. PostgreSQL no garantiza el orden de
evaluación entre predicados, así que la función se evaluó contra un índice
(`comment_org_id_231a23a0`) y reventó. Rehecha con un CTE `as materialized`.

---

## 4. Hallazgo operativo: la dependencia `postgres` → `crm_owner`

> **Corregido el 17/09/2026 por la etapa 9.1.** La primera versión de esta
> sección afirmaba que el acceso del CRM dependía **por completo** de esta
> membresía. Es falso, y se midió: `service_role` está en la ACL de las 129
> tablas y `postgres` lo hereda, así que el tráfico sobrevive a la revocación.
> Lo que no sobrevive es el DDL. El detalle completo está en
> [9.1_DEPENDENCIA_POSTGRES_CRM_OWNER.md](9.1_DEPENDENCIA_POSTGRES_CRM_OWNER.md).

**Ninguna de las 129 tablas nombra a `postgres` en su ACL** (0 de 129). No hacía
falta: era el dueño. Ahora el dueño es `crm_owner`, y lo que `postgres` conserva
sobre esas tablas viene de dos sitios distintos:

| Vía | Qué aporta |
|---|---|
| `service_role` (heredado, `arwdDxtm` en las 129 + USAGE en las 51 secuencias) | Todo el DML: SELECT, INSERT, UPDATE, DELETE, y el mantenimiento (`MAINTAIN`) |
| `crm_owner` (heredado, por `GRANT crm_owner TO postgres ... INHERIT TRUE`) | El DDL: `ALTER`, `CREATE INDEX`, `DROP`, y el `CREATE` sobre el esquema `public` |

La segunda la creó `01_crear_roles.sql` (`grant crm_owner to current_user`)
**para otra cosa**: para que `ALTER TABLE ... OWNER TO crm_owner` estuviera
permitido. Sobrevive al paso 9 como dependencia permanente.

> **No revocarla mientras `DBUSER = postgres`.** No rompería el CRM, pero dejaría
> a la credencial de emergencia sin capacidad de reparar nada. Si se revoca,
> después del paso 14 y **nunca** la fila con `ADMIN OPTION` de `supabase_admin`,
> que es la que permite deshacerlo.

Queda documentado en `B6_PLAN_CAMBIO_CONTROLADO.md` §D, §I y §K, junto con la
nota de que `set role crm_user` no es una técnica de verificación disponible en
producción.

Dato relacionado, ya conocido pero que el cambio vuelve más visible: `postgres`
tiene `BYPASSRLS = true`. Mientras el CRM circule con esa credencial, se salta
las 120 políticas. `crm_user` no tiene BYPASSRLS — es precisamente lo que el
paso 15 viene a cerrar.

---

## 5. Estado de producción al cerrar el paso 9

| Elemento | Estado |
|---|---|
| Dueño de las 129 tablas | `crm_owner` (NOLOGIN, inalcanzable por el pooler) |
| Secuencias / índices | 51 / 783, todos de `crm_owner` |
| RLS | 120 políticas, 60 tablas, 60 con FORCE |
| `crm_user` | 903 GRANT intactos; sin BYPASSRLS; dueño de nada; **conserva CREATE en `public`** (paso 11, no autorizado) |
| `crm_migrator` | LOGIN por pooler, actúa como `crm_owner`, 3 default privileges activos |
| `motor_user`, `app_backend` | Sin cambios |
| DBUSER del CRM | **Sin cambios** (`postgres`) |
| Migraciones | **0 aplicadas** — las 6 pendientes siguen pendientes |
| Celery, motor, autonomía, RLS | **Sin tocar** |

Nada de lo prohibido para este paso se ejecutó.

---

## 6. Pendiente, no autorizado

Paso 11 (`REVOKE CREATE ON SCHEMA public FROM crm_user`) · paso 13 (cargar
`MIGRATOR_*` en Dokploy) · paso 15 (DBUSER → `crm_user`) ·
`CRM_CREDENCIALES_ESTRICTO=1` · las 6 migraciones pendientes · las 11 tablas sin
RLS · el problema de diseño de políticas en `organization`/`users`/2 `campo_*` ·
`Idempotency-Key` en `solicitudes` · `manage_rls --status`.

**Archivos sensibles a mover fuera de esta máquina:**
`C:\Users\Usuario\b8_crm_migrator_clave.txt` (a Dokploy) y
`C:\Users\Usuario\respaldo_b8\` — el `.sql` de roles contiene 9 hashes SCRAM.
