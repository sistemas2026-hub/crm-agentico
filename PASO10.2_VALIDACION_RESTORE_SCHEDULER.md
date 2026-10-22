# Paso 10.2 — Validación funcional del respaldo/restauración y pgcrypto

**Fecha:** 17/09/2026
**Alcance:** diagnóstico y prueba funcional en réplicas desechables.
**Producción:** sólo lectura. No se modificó nada, no se tocó el ledger, no se
aplicó ninguna migración, no se concedió ningún permiso.
**Veredicto:** el procedimiento de B.6 **produce un scheduler roto**,
demostrado funcionalmente. La corrección está probada y reproduce producción.

> El fallo no es de una pieza sino de **tres**, y sólo la primera se sospechaba:
> el esquema equivocado (`ext` en vez de `extensions`), la ausencia de una
> concesión (`asistente_owner` necesita `USAGE` sobre ese esquema), y el hecho
> de que **ningún artefacto de respaldo transporta ninguna de las dos**.

---

## 1. Estado real de pgcrypto en producción

| Extensión | Esquema | Versión | Reubicable |
|---|---|---|---|
| `pgcrypto` | **`extensions`** | 1.3 | sí |
| `uuid-ossp` | `extensions` | 1.1 | sí |
| `pg_net` | `extensions` | 0.20.3 | no |
| `pg_stat_statements` | `extensions` | 1.11 | sí |
| `pg_trgm` | `public` | 1.6 | sí |
| `vector` | `public` | 0.8.2 | sí |
| `supabase_vault` | `vault` | 0.3.1 | no |
| `plpgsql` | `pg_catalog` | 1.0 | no |

El esquema `ext` **no existe en producción**.

ACL del esquema `extensions`:

```
postgres=UC/postgres, anon=U, authenticated=U, service_role=U,
dashboard_user=UC, asistente_owner=U/postgres
```

`asistente_owner=U` es la pieza que importa: es una concesión **añadida
deliberadamente** para este subsistema, no parte de la plantilla de Supabase.

---

## 2. Estado de `digest` y `gen_random_bytes`

| Función | Existe | Procede de |
|---|---|---|
| `extensions.digest(text, text)` | **sí** | `pgcrypto` |
| `extensions.digest(bytea, text)` | sí | `pgcrypto` |
| `extensions.gen_random_bytes(integer)` | **sí** | `pgcrypto` |
| `extensions.gen_random_uuid()` | sí | `pgcrypto` |
| `pg_catalog.gen_random_uuid()` | sí | **nativa de PostgreSQL 13+** |
| `ext.digest(text, text)` | **NO EXISTE** | — |
| `ext.gen_random_bytes(integer)` | **NO EXISTE** | — |

Las funciones de pgcrypto tienen `=X/supabase_admin` en su ACL: **`PUBLIC` puede
ejecutarlas**. El permiso que falta nunca es el de la función — es el `USAGE`
del esquema.

Las **10 funciones del scheduler llevan `search_path = pg_catalog`**. Es un
endurecimiento deliberado, y su consecuencia es que **no hay resolución por
búsqueda**: el nombre tiene que estar calificado y el esquema tiene que
llamarse exactamente así. `extensions.digest` sólo resuelve si existe un
esquema llamado `extensions`.

---

## 3. Dependencias del scheduler

Referencias a `extensions.` en los tres esquemas volcados — **8 en total, todas
en funciones**:

| Función | Referencias |
|---|---|
| `asistente.job_claim` | 4 |
| `asistente.job_contexto` | 2 |
| `asistente.job_intento_vigente` | 1 |
| `asistente.job_intento_vigente_por_capability` | 1 |

**Ninguna** en valores por defecto, restricciones, índices ni vistas. El
escaneo del texto completo del volcado confirma el mismo recuento: 7 `digest` +
1 `gen_random_bytes`. `gen_random_uuid` aparece 23 veces **sin calificar** y lo
resuelve `pg_catalog` de forma nativa, así que no necesita pgcrypto.

> **Dependencias registradas hacia `pg_extension`: 0.**
> PostgreSQL no analiza el cuerpo de una función plpgsql al crearla. La
> referencia a `extensions.digest` **no deja rastro en el catálogo**, así que
> nada avisa al restaurar. El fallo aparece en la primera llamada, no antes.

Esa es la razón de fondo por la que este defecto sobrevivió a B.7, al simulacro
del paso 9 y al paso 10: **todas las verificaciones eran estructurales.**

---

## 4. Reproducción del fallo de B.6

Instrucción actual de B.6 §B, paso 3:

```bash
psql -d "$DESTINO" -c "create schema if not exists ext;
  create extension if not exists pgcrypto with schema ext;
  create extension if not exists pg_trgm  with schema public;
  create extension if not exists vector   with schema public;"
```

Réplica `pg-102a`, restaurada siguiendo eso al pie de la letra desde
`paso10_20260917_100237_datos.dump` + `_roles.sql`:

```
pg_restore codigo de salida: 0
tablas public = 129 | tablas asistente = 35 | funciones job* = 10
```

**Todo lo estructural pasa.** Y sin embargo:

```
job_claim()  ->  InvalidSchemaName: schema "extensions" does not exist
```

Para descartar que fuera un problema de permisos, se repitió concediendo a `ext`
exactamente el mismo `USAGE` que después se le dio al escenario B:

```
ACL de ext: {postgres=UC/postgres,asistente_owner=U/postgres}
job_claim()  ->  InvalidSchemaName: schema "extensions" does not exist
```

**Mismo error.** El fallo es el nombre del esquema, aislado.

---

## 5. Resultado del restore funcional

Escenario B, réplica `pg-102b`: `extensions` + pgcrypto ahí + `grant usage on
schema extensions to asistente_owner`. Flujo real de
`nucleo/programador/puerta.py`, con datos de prueba creados **sólo en la
réplica**:

```
job_claim()      run_id=3eb6a057…  attempt #1  fencing=1
                 capability = 64 hex   <- gen_random_bytes(32) funciono
                 config_hash = 64 hex  <- digest sha256 funciono
job_contexto()   job_code=p102_prueba, inputs={'prueba': True},
                 config_hash coincide con el del claim
job_heartbeat()  lease renovado hasta 15:32:11
job_finalize()   desenlace registrado: succeeded
job_run          estado 'succeeded'
job_attempt      outcome 'succeeded' con completed_at
job_run_event    3 eventos registrados
job_salud()      1 fila    jobs_vencidos()  0 filas

>>> 0 falla(s)
```

El turno se reclamó, se procesó, se actualizó y se cerró **sin un solo error de
resolución de funciones**.

---

## 6. Comparación A vs B

| | **A** — B.6 literal | **A.2** — B.6 + `usage` sobre `ext` | **B** — corrección |
|---|---|---|---|
| Esquema de pgcrypto | `ext` | `ext` | **`extensions`** |
| `grant usage … asistente_owner` | no | sí (sobre `ext`) | sí (sobre `extensions`) |
| `pg_restore` | **0** | **0** | **0** |
| 129 tablas / 35 en `asistente` / 10 funciones | **sí** | **sí** | **sí** |
| `extensions.digest` resuelve | no | no | **sí** |
| `job_salud()`, `jobs_vencidos()` | responden | responden | responden |
| **`job_claim()`** | **`InvalidSchemaName`** | **`InvalidSchemaName`** | **OK** |
| Flujo completo hasta `succeeded` | — | — | **OK** |

Dos lecciones concretas:

- **`pg_restore` en 0 no dice nada** sobre este defecto. Los tres escenarios
  restauran igual de bien.
- **`job_salud()` y `jobs_vencidos()` tampoco**: responden en los tres, porque
  no llaman a `digest`. Una prueba de humo sobre el scheduler que use esas dos
  funciones daría verde con el scheduler roto.

### Por qué B reproduce producción

Comparación directa producción ↔ réplica B: **11 de 11 idénticos.**

| Comprobación | Valor (idéntico en ambas) |
|---|---|
| Esquema de pgcrypto | `extensions` |
| `extensions.digest` / `gen_random_bytes` resuelven | `true` / `true` |
| `asistente_owner` con `USAGE` en `extensions` | `true` |
| Funciones `job*` | 10 |
| Con `search_path=pg_catalog` | 10 |
| **md5 de los 10 cuerpos concatenados** | `614d3a167d73bac0ca16cf6fc002a19c` |
| Dueño de las tablas `job*` | `asistente_owner` |
| Tablas / políticas en `asistente` | 35 / 35 |
| ACL de `job_claim` | `asistente_owner=X, scheduler_coordinator=X` |

Lo único que la réplica tiene de más son las filas de la prueba funcional
(1 catálogo, 1 run, 1 attempt, 1 agenda, 3 eventos).

---

## 7. Corrección propuesta

pgcrypto debe instalarse en **`extensions`**, y hace falta además la concesión.
La justificación es doble y ambas medidas están en este informe:

1. **Evidencia de producción:** pgcrypto vive en `extensions`, `ext` no existe,
   y los cuerpos de las funciones —que PostgreSQL guarda literales— llaman a
   `extensions.digest`. Con `search_path = pg_catalog` no hay resolución
   alternativa posible.
2. **Evidencia de restauración funcional:** con `ext` el flujo falla
   (`InvalidSchemaName`) incluso concediendo los mismos permisos; con
   `extensions` + `USAGE` para `asistente_owner` el flujo se completa hasta
   `succeeded`, y la réplica es idéntica a producción en 11 de 11 comprobaciones.

---

## 8. Cambios exactos que deberían hacerse a B.6 / B.7

*(Sin aplicar. B.7 no tiene archivo propio: su procedimiento vive en
`B6_PLAN_CAMBIO_CONTROLADO.md` §B, que es lo que se corrige.)*

**Cambio 1 — §B, paso 3.** Sustituir:

```bash
# ANTES  (produce un scheduler roto)
psql -d "$DESTINO" -c "create schema if not exists ext;
  create extension if not exists pgcrypto with schema ext;
  create extension if not exists pg_trgm  with schema public;
  create extension if not exists vector   with schema public;"
```

por:

```bash
# DESPUES  (reproduce produccion)
psql -d "$DESTINO" -c "create schema if not exists extensions;
  create extension if not exists pgcrypto with schema extensions;
  create extension if not exists pg_trgm  with schema public;
  create extension if not exists vector   with schema public;
  -- Las 10 funciones del scheduler son SECURITY DEFINER de asistente_owner y
  -- llaman a extensions.digest con search_path=pg_catalog. Sin este USAGE
  -- fallan con 'permission denied for schema extensions' en la primera
  -- llamada, no al restaurar. El ACL de un esquema ajeno a los 3 volcados no
  -- viaja en ningun artefacto: hay que concederlo a mano.
  grant usage on schema extensions to asistente_owner;"
```

**Cambio 2 — §B, verificación posterior.** Añadir, después de comprobar el
`nspacl` de `public`, una prueba **funcional**: sembrar `job_catalogo` y
`job_schedule_state` y recorrer
`job_claim → job_contexto → job_heartbeat → job_finalize`, exigiendo
`succeeded`. El guion usado aquí sirve tal cual.

**Cambio 3 — §B, nota sobre lo que el respaldo NO transporta.** Hoy lista dos
cosas (el `SET role` de `crm_migrator`, las extensiones). Son **cuatro**:

| Pieza | ¿Viaja en el respaldo? |
|---|---|
| Roles, incluido `asistente_owner` | **sí**, en `*_roles.sql` (verificado: los 7 roles relevantes) |
| `alter role crm_migrator … set role = crm_owner` | **no** — 0 coincidencias en el volcado de roles |
| `create extension pgcrypto with schema extensions` | **no** — 0 entradas `EXTENSION` en el volcado |
| `grant usage on schema extensions to asistente_owner` | **no** — ACL de un esquema fuera de los 3 volcados |

**Cambio 4 — §K Riesgos.** Añadir: *«Una verificación de restauración que sólo
comprueba que los objetos existen no detecta una dependencia de esquema rota:
PostgreSQL no registra dependencia alguna del cuerpo de una función plpgsql, y
el fallo aparece en la primera llamada.»*

---

## 9. Riesgos residuales

1. **El repositorio sigue diciendo `ext.`** en los dos archivos de Fase 1. La
   corrección de B.6 arregla la restauración, **no** la divergencia del paso
   10.1: si algún día se re-aplican esos archivos tal cual, su guarda de
   pre-vuelo abortará. Son dos problemas distintos con una misma causa.
2. **La corrección se validó contra PostgreSQL desnudo** (`pgvector/pgvector:pg17`).
   En una restauración sobre un proyecto Supabase nuevo, `extensions` ya existirá
   con pgcrypto y las concesiones de plantilla; lo que faltará igualmente es
   `grant usage … to asistente_owner`, porque `asistente_owner` es un rol
   nuestro. El `create schema if not exists` y el `create extension if not
   exists` son inocuos en ese caso.
3. **Sólo se probó el camino feliz del scheduler.** Reclamar, latir, finalizar
   con éxito. No se ejercitaron el rescate de leases vencidos, el backoff, ni
   `job_cerrar_turno`. Ninguno de ellos llama a `digest`, así que no cambian el
   veredicto sobre pgcrypto, pero tampoco están cubiertos.
4. **Quedan otras dependencias fuera de los 3 esquemas sin auditar.** Este
   trabajo buscó `extensions.` exhaustivamente y encontró 8 referencias, todas
   del scheduler. No se auditó qué más podría vivir en `auth`, `storage`,
   `vault` o `supabase_functions` y ser necesario para el CRM.
5. **`job_catalogo` está vacío en producción**: el scheduler no tiene trabajos
   registrados. Cuando se registren, el camino probado aquí pasa a estar en uso
   real, y este defecto habría sido un corte silencioso en cualquier
   restauración.

---

## 10. Criterio de prueba para futuros respaldos

**No aceptar como suficiente:** que `pg_restore` termine en 0; que las tablas,
índices o funciones existan; que `job_salud()` o `jobs_vencidos()` respondan.
Las tres cosas pasan con el scheduler roto.

**Exigir, después de cada restauración:**

1. `extensions.digest(text,text)` y `extensions.gen_random_bytes(integer)`
   resuelven (`to_regprocedure(...) is not null`).
2. `has_schema_privilege('asistente_owner','extensions','usage')` es `true`.
3. Las 10 funciones `job*` existen y conservan `search_path=pg_catalog`.
4. **El flujo completo**: sembrar `job_catalogo` + `job_schedule_state`, y
   recorrer `job_claim → job_contexto → job_heartbeat → job_finalize` hasta
   `succeeded`, comprobando de paso que la `capability` tiene 64 hex y que el
   `config_hash` del contexto coincide con el del claim.
5. `md5` del conjunto de los 10 cuerpos de función igual al de producción —
   hoy `614d3a167d73bac0ca16cf6fc002a19c`. Detecta en una sola comparación
   cualquier deriva entre lo restaurado y lo que corre.

La regla general, que este paso confirma por tercera vez en el proyecto: **una
prueba que afirma que un mecanismo existe no prueba que funcione.**

---

## Estado al cerrar

Producción intacta y verificada: ledger 45 filas, `job_catalogo` 0,
`job_run` 0, 135 tablas en `public`, 192 filas en `django_migrations`, ACL de
`extensions` sin cambios. Réplicas `pg-102a` y `pg-102b` eliminadas. Todas las
consultas contra producción se abrieron con `read_only = True`.
