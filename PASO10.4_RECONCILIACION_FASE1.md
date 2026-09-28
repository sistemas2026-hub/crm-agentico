# Paso 10.4 — Reconciliación de las 2 migraciones de Fase 1

**Fecha:** 17/09/2026
**Alcance:** diseño + prueba en réplica. **Producción no se modificó**, el
ledger no se tocó, las 2 migraciones no se aplicaron, no se concedió ningún
permiso. **El repositorio tampoco se modificó**: la reconciliación se ensayó
sobre una copia en el scratchpad.

> **Hallazgo que decide el diseño:** corregir `ext.` → `extensions.` en los dos
> archivos produce **los 10 cuerpos de función idénticos, byte a byte, a los de
> producción**. La corrección no es una conjetura: es verificable contra el
> catálogo.

---

## 1. Estado actual

| | |
|---|---|
| Ledger | 45 filas · 36 `baseline` · 7 `baseline_humano` · **2 `aplicada`** |
| Tablas en `asistente` / `public` | 35 / 135 |
| md5 de los 10 cuerpos `job*` | `614d3a167d73bac0ca16cf6fc002a19c` |
| Tablas de las 2 migraciones de Fase 1 | **0** — no se aplicaron |
| `--aplicar` y `--adoptar` | **bloqueados** |

## 2. Inventario de las 2 migraciones

| | `202609141200_scheduler_persistente.sql` | `202609141300_scheduler_funciones.sql` |
|---|---|---|
| Checksum histórico | `897cb5d3da222e85913f288aace4b6fe02fb34eb2b9254d47212a6be47d8fc0e` | `f325bd442baad0f70168deedd92175f5ffb15cecc79055f9cbfdd4c2165e77f1` |
| Aplicada | 2026-09-15 **19:32:03.648710+00** | 2026-09-15 **19:40:13.622699+00** |
| Duración | 338 ms | 289 ms |
| Origen / usuario | `aplicada` / `postgres` | `aplicada` / `postgres` |
| Declara | 5 tablas, 9 índices con nombre, 5 políticas, 7 `ALTER TABLE` | 10 funciones, 2 políticas, 11 `GRANT`, 5 `ALTER TABLE … OWNER TO`, 1 `COMMENT` |

**Ambos archivos son idempotentes por construcción** — es el dato que abre las
opciones: `create table if not exists` ×5, `create index if not exists` ×9,
`create or replace function` ×10, `drop policy if exists` antes de cada
política, y ningún `create table` desnudo.

**Dependencias:** `pgcrypto` (vía `digest` y `gen_random_bytes`),
`asistente.tenant_config` y `tenant_config_historial` (el archivo de funciones
crea políticas sobre ellas), `public.organization` (claves foráneas), y los
roles `asistente_owner`, `scheduler_coordinator`, `job_executor`, `monitor_ro`.

## 3. Comparación histórica vs producción

**44 objetos declarados, clasificados contra el catálogo:**

| Estado | Nº | Cuáles |
|---|---|---|
| **EXISTE Y ES EQUIVALENTE** | **34** | 5 tablas, 9 índices, 7 políticas, 6 funciones, 7 `GRANT` |
| **EXISTE PERO DEPENDE DE CONFIG HISTÓRICA** | **5** | `job_claim`, `job_contexto`, `job_intento_vigente`, `job_intento_vigente_por_capability`, y el `USAGE` sobre `extensions` |
| **EXISTE Y NO DEBE TOCARSE** | **4** | `pgcrypto` en `extensions`, la resolución de `digest`/`gen_random_bytes`, el `search_path=pg_catalog` de las 10 funciones, el ledger |
| **NO EXISTE** | **1** | `grant usage on schema ext` — porque el esquema `ext` no existe |

Las 5 divergencias tienen **una sola causa**, en tres sitios: 8 referencias en
4 cuerpos de función, 1 `grant usage on schema ext`, y la guarda de pre-vuelo.

**Lo que ya está materializado en producción:** todo. Las 5 tablas (de
`asistente_owner`, con RLS y sin FORCE), los 21 índices, las 48 restricciones,
las 5 políticas y las 10 funciones `SECURITY DEFINER`. El scheduler funciona.

**Lo que sería peligroso volver a ejecutar:** **nada, si el archivo está
corregido.** Con el archivo **tal como está hoy en el repo**, en cambio, la
ejecución **aborta** en su propia guarda de pre-vuelo (`ext.digest` no existe) —
la guarda protege, pero confirma que el archivo actual no es aplicable.

### Corroboración independiente

`--adoptar` se niega con un mensaje que cierra la historia del paso 10.1:

```
PostgreSQL mayor: manifiesto 16, servidor 17
extension pgcrypto: schema manifiesto ext, servidor extensions
```

**El propio manifiesto de adopción registra `pgcrypto` en `ext`.** Se generó
contra una referencia PostgreSQL 16 donde pgcrypto vivía ahí. El repositorio y
el manifiesto comparten la convención `ext`; producción nunca la tuvo.

## 4. Alternativas

### La restricción que las condiciona a todas

Medido en réplica: **la divergencia bloquea los dos modos del CLI**, no sólo
`--aplicar`. `_preparar()` de la adopción se niega con *«hay archivos no
canónicos o aplicados que cambiaron; resolver antes de adoptar»*. Y
`--aceptar` sólo opera sobre archivos **pendientes**, nunca sobre uno que ya
tiene fila (la clave primaria es `archivo` y la tabla es de solo-agregar).

Las únicas formas de vaciar `discrepancias` son: (i) que los archivos vuelvan a
hashear a lo anotado —imposible, el contenido no es recuperable—; (ii) que esos
nombres **dejen de existir en disco**, con lo que pasan a «anotadas sin
archivo»; (iii) tocar el ledger —prohibido—; (iv) cambiar el CLI.

### A · Reconciliación conservadora (renombrar + reconocer)

Corregir el contenido (`ext.` → `extensions.`), **renombrar** los dos archivos
con sellos nuevos, y reconocer el estado existente sin re-ejecutar efectos. Las
filas históricas quedan intactas; los nombres viejos pasan a «anotadas sin
archivo» — un estado que el ledger **ya tiene** para otros 3 archivos.

- **Cambios:** 2 archivos corregidos y renombrados. Ledger: 2 filas nuevas.
- **Riesgos:** el nombre nuevo debe ordenar **después** de `max(anotadas)` =
  `202609141300_scheduler_funciones.sql`, o el CLI lo trata como hueco.
  Se propone `202609151700_` y `202609151705_`, que además conservan el orden
  relativo original (antes de las dos de Fase 1).
- **Rollback:** deshacer el renombrado en el repositorio. El ledger no se toca.
- **Scheduler:** intacto — no se ejecuta nada.
- **Ledger:** gana 2 filas; las históricas se conservan. Trazabilidad completa.
- **Respaldo/restauración:** sin impacto.
- **Futuras migraciones:** desbloqueadas.
- **Variante A1 (adoptar):** requiere **regenerar el manifiesto** contra una
  referencia PostgreSQL 17 con pgcrypto en `extensions` — el actual es de PG16
  y no incluye estos dos archivos. Es la vía más pura: no ejecuta nada.
- **Variante A2 (aplicar):** los archivos renombrados quedan pendientes y
  `--aplicar` los ejecuta. **Probado:** al ser idempotentes y coincidir con
  producción, la ejecución es un no-op verificable.

### B · Migración correctiva (un archivo nuevo, los viejos intactos)

Dejar los dos archivos como están y añadir una migración que aplique la
diferencia (`create or replace` de las 4 funciones + el `grant`).

- **No funciona sola.** La divergencia sigue bloqueando el CLI, así que la
  migración nueva **no se puede aplicar**. Requiere A de todos modos.
- Y deja un problema peor: en una construcción desde cero, el archivo histórico
  se ejecutaría primero y **abortaría** en su guarda de pre-vuelo. La
  reproducibilidad no se recupera.
- **Rollback:** borrar el archivo nuevo.
- **Veredicto:** estrictamente inferior a A. Se documenta por completitud.

### C · Divergencia declarada en el ledger (requiere código)

Añadir un paso 4 al esquema del ledger con una tabla de divergencias —«la fila
X quedó anotada con el checksum A; el archivo vigente es B; aquí está la
evidencia de catálogo de que el efecto coincide; autorizado por Y»— y enseñar
al CLI a consultarla al calcular `discrepancias`.

- **Cambios:** migración del esquema del ledger + cambios en
  `migrar_asistente.py` y `manifiesto_adopcion.py`.
- **Riesgos:** toca el mecanismo que protege el ledger; hay que probarlo con el
  mismo rigor que todo lo demás.
- **Ventaja real:** es la única que conserva **el nombre original** y deja la
  divergencia explícita y auditable en vez de convertirla en un archivo
  renombrado que alguien tendrá que interpretar en seis meses.
- **Rollback:** revertir el paso del esquema (el ledger versiona su esquema:
  hoy 3 de 3).
- **Futuras migraciones:** desbloqueadas, y el mecanismo queda para la próxima
  vez que pase lo mismo.

## 5. Riesgos

1. **El renombrado pierde el vínculo nombre↔historia.** Quien lea el ledger
   verá `202609141200_…` anotada sin archivo y `202609151700_…_reconciliado`
   aplicada, sin que nada diga que son la misma migración salvo el nombre y lo
   que digan los comentarios del archivo.
2. **La adopción (A1) exige regenerar el manifiesto** contra una referencia
   PostgreSQL 17 con pgcrypto en `extensions`. El actual es PG16/`ext` y no
   incluye estos archivos.
3. **A2 ejecuta DDL en producción**, aunque sea un no-op medido: reescribe 10
   cuerpos de función y recrea 7 políticas (`drop`+`create` dentro de la
   transacción del archivo).
4. **Las 2 migraciones de Fase 1 crean sus tablas bajo `postgres`**, no bajo
   `asistente_owner` — a diferencia de las `job_*`, que llevan `ALTER TABLE …
   OWNER TO asistente_owner` explícito. Coincide con las otras 30 tablas de
   `asistente`, pero es una inconsistencia que conviene decidir antes de
   aplicarlas.
5. **Nada de esto resuelve quién aplicará las 2 de Fase 1.** Siguen siendo del
   dominio del motor, y `crm_migrator` sigue sin permisos sobre `asistente`.

## 6. Pruebas en réplica

Réplica desde cero con el procedimiento B.6/B.7 corregido (`restaurar.sh`,
código 0).

| # | Prueba | Resultado |
|---|---|---|
| 1 | Restore | código 0 |
| 2 | Estado de las 2 migraciones | `con checksum distinto: 2`; **`--aplicar` y `--adoptar` se niegan** |
| — | Tras aplicar la estrategia A al árbol de pruebas | `checksum distinto: **0**`; `anotadas sin archivo: 3 → **5**`; 4 pendientes |
| — | `--aplicar` | **4 aplicadas** (20 ms, 61 ms, 10 ms, 9 ms), código 0 |
| 3-7 | `job_claim → job_contexto → job_heartbeat → job_finalize` | **`succeeded`**, capability 64 hex, `config_hash` coincidente, 3 eventos |
| 8 | RLS | 5 tablas `job_*` con RLS — idéntico a producción |
| 9 | ACL | `job_claim`: `asistente_owner=X, scheduler_coordinator=X` — idéntico |
| 10 | Ownership | `job_*` de `asistente_owner`; `public` de `crm_owner` — idéntico |
| 11 | Respaldo posterior | 3 artefactos, 8.907.945 bytes |
| 12 | Restauración posterior | código 0, scheduler **0 fallas** |

**No se duplicó ningún objeto.** Tras re-aplicar: 5 tablas `job_*`, 21 índices,
48 restricciones, 5 políticas, 10 funciones — **los mismos números que
producción**, y el **md5 de los 10 cuerpos idéntico**
(`614d3a167d73bac0ca16cf6fc002a19c`). La única diferencia con producción son
las 2 tablas que añaden las migraciones de Fase 1 (37 vs 35).

**Las dos filas históricas sobrevivieron intactas** al ciclo completo, con sus
checksums originales, junto a las nuevas.

### Un defecto encontrado por la prueba

`respaldar.py` usaba el mismo host para las herramientas en contenedor y para
la consulta de catálogo. Contra una base local eso rompe:
`failed to resolve host 'host.docker.internal'`. Corregido con
`--host-catalogo`, y verificado en el ciclo 11-12.

## 7. Resultado del restore posterior

Réplica nueva desde el respaldo de la réplica reconciliada: `restaurar.sh`
código 0, artefacto de entorno con `grant usage on schema extensions to
asistente_owner` y el `set role = crm_owner`, y el scheduler funcional con
**0 fallas** hasta `succeeded`. El ledger llegó completo: las 2 filas
históricas, las 2 reconciliadas y las 2 de Fase 1.

## 8. Propuesta técnica

No se recomienda una todavía, como pide el encargo. Lo que las pruebas
establecen:

- **A es la única implementable sin tocar código**, y está probada de extremo a
  extremo. A2 (aplicar) está medida como no-op; A1 (adoptar) exige regenerar el
  manifiesto.
- **B no es viable por sí sola** y deja rota la construcción desde cero.
- **C es la mejor desde la trazabilidad** —conserva el nombre original y deja la
  divergencia explícita— y la única que deja mecanismo para la próxima vez. Su
  coste es una migración del esquema del ledger y cambios en dos módulos del
  CLI.

La decisión entre **A** (rápida, probada, con una cicatriz de nombres) y **C**
(más cara, más limpia a largo plazo) es suya.

## 9. Rollback

| Estrategia | Rollback | Pérdida |
|---|---|---|
| A (repositorio) | Deshacer renombrado y corrección; el ledger no se tocó | Ninguna |
| A2 (tras aplicar) | Nada que deshacer: la ejecución es un no-op verificado. Si aun así se quisiera, `99_`-style no aplica; el estado previo es idéntico | Ninguna |
| B | Borrar el archivo nuevo | Ninguna |
| C | Revertir el paso del esquema del ledger (versiona: 3 de 3) | Ninguna |

En los cuatro casos el respaldo verificado del paso 10.3 es la red final.

## 10. Cambios que serían necesarios

**Para A:**
1. Corregir `ext.` → `extensions.` en los dos archivos (5 y 14 sustituciones).
2. Renombrarlos a `202609151700_…` y `202609151705_…`.
3. A1: regenerar `supabase/ledger/manifiesto_adopcion.json` contra una
   referencia PG17 con pgcrypto en `extensions`, y `--adoptar --aceptar` cada
   uno con `--motivo` y `--autorizado-por`.
   A2: `--aplicar` con la credencial que tiene `CREATE` sobre `asistente`.
4. Documentar en ambos archivos, en cabecera, que sustituyen a los históricos y
   por qué.

**Para C:** paso 4 del esquema del ledger, tabla de divergencias con evidencia
y autorización, y que `plan()` la consulte al calcular `discrepancias`.

**En cualquier caso:** decidir el dueño de las tablas que crean las 2
migraciones de Fase 1 (riesgo 5), y con qué credencial se aplicarán.

## 11. Lo que NO debe modificarse

- **El ledger de producción.** Las 45 filas, y en particular las 2 con
  `origen='aplicada'` y sus checksums `897cb5d3…` y `f325bd44…`.
- **`pgcrypto` en el esquema `extensions`**, y el `USAGE` de `asistente_owner`
  sobre él.
- **El `search_path = pg_catalog`** de las 10 funciones del scheduler.
- **Las 5 tablas `job_*`**, su dueño `asistente_owner`, sus 21 índices, 48
  restricciones y 5 políticas.
- **Los 10 cuerpos de función vigentes** (`614d3a167d73bac0ca16cf6fc002a19c`).
- **La separación CRM/Motor**: no conceder `USAGE`/`CREATE` sobre `asistente` a
  `crm_migrator` ni a `crm_owner`.
- **`DBUSER`**, la propiedad de las 135 tablas de `public`, las membresías
  `postgres → crm_owner`, RLS, Celery, motor, autonomía e integraciones.

---

## Estado al cerrar

Producción intacta: ledger 45 filas (2 `aplicada`), 35 tablas en `asistente`,
135 en `public`, md5 de las funciones sin cambios, **0 tablas de las 2
migraciones de Fase 1**. Repositorio sin modificar — la reconciliación se probó
sobre una copia en el scratchpad. Réplicas `pg-104` y `pg-104b` eliminadas.
Todas las consultas contra producción con `read_only = True`.
