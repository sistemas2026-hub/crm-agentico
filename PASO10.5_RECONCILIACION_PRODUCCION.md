# Paso 10.5 — Reconciliación controlada de las 2 migraciones de Fase 1

**Fecha:** 17/09/2026
**Resultado:** reconciliación aplicada. **`con checksum distinto: 2 → 0`**, con
el ledger **bit a bit intacto** y sin recrear un solo objeto.
**La base de datos de producción no se modificó**: el cambio es del
repositorio. La única escritura que tocó producción fue la prueba funcional del
scheduler, dentro de una transacción revertida que no dejó ni una fila.

---

## 1. Estado antes

| | |
|---|---|
| Ledger | **45 filas**, md5 `58ff01f220787396657af7832f6c48c8` |
| `--estado` | 44 archivos · 2 pendientes · **2 con checksum distinto** · 3 anotadas sin archivo |
| `--aplicar` y `--adoptar` | bloqueados |
| Objetos del scheduler | 5 tablas · 21 índices · 48 constraints · 5 políticas · 10 funciones |
| md5 de los 10 cuerpos | `614d3a167d73bac0ca16cf6fc002a19c` |
| `git` | los dos archivos versionados y limpios en `HEAD 108935f` |

## 2. Respaldo utilizado

Tomado con el procedimiento B.6/B.7 corregido **antes** de tocar ningún archivo.

```
sello: 20260917_104932
  20260917_104932_datos.dump      8.897.369 bytes
  20260917_104932_roles.sql           9.936 bytes
  20260917_104932_entorno.sql         4.525 bytes
```

**Verificado como utilizable**, no sólo generado: restaurado en una réplica
desechable (`restaurar.sh` código 0), **25 de 25** comprobaciones estructurales
idénticas a producción, y el scheduler funcional con **0 fallas**.

Además, copia de los dos archivos originales fuera del repositorio en
`C:\Users\Usuario\respaldo_p105_archivos\`.

## 3. Archivos modificados

| Antes | Después |
|---|---|
| `supabase/202609141200_scheduler_persistente.sql` | `supabase/202609151700_scheduler_persistente_reconciliado.sql` |
| `supabase/202609141300_scheduler_funciones.sql` | `supabase/202609151705_scheduler_funciones_reconciliado.sql` |

Los sellos nuevos ordenan **después** de `max(anotadas)`
(`202609141300_scheduler_funciones.sql`) — para que el CLI no los trate como
huecos — y **antes** de las dos migraciones de Fase 1 pendientes, conservando
el orden relativo original.

## 4. Cambios exactos

**Sólo `ext.` → `extensions.`. Nada más.** El pre-flight lo verificó línea por
línea antes de tocar nada: de las 338 + 987 líneas, cambian **18**, y cada una
vuelve exactamente al original aplicando la sustitución inversa.

`202609141200` — **4 líneas**: la guarda de pre-vuelo (`ext.digest`,
`ext.gen_random_bytes`) y dos textos de mensaje/hint.

`202609141300` — **14 líneas**: la guarda de pre-vuelo y su hint, 2 líneas de
comentario del contrato de la capability, `grant usage on schema ext to
asistente_owner`, y **8 referencias en 4 cuerpos de función** (`job_claim` ×4,
`job_contexto` ×2, `job_intento_vigente` ×1,
`job_intento_vigente_por_capability` ×1).

No se añadió ninguna nota de cabecera a los archivos: la Fase 3 prohíbe
explícitamente cualquier otra modificación. Queda como pendiente documental.

## 5. Checksums

| Archivo | Histórico (ledger) | Repositorio antes | Repositorio después |
|---|---|---|---|
| `…_scheduler_persistente…` | `897cb5d3da222e85…` | `d77a31b201ab6111…` | **`e7a70f0556d29022…`** |
| `…_scheduler_funciones…` | `f325bd442baad0f7…` | `63bc3f14ffa5f384…` | **`ca0bf08137214414…`** |

Los checksums históricos **no se tocaron**: siguen en sus filas, sin cambio.

## 6. Resultado del CLI

```
archivos en supabase/ : 44
anotados en el ledger : 45
pendientes            : 4
con checksum distinto : 0          <-- era 2
no canonicos          : 0
  pendiente: 202609151700_scheduler_persistente_reconciliado.sql
  pendiente: 202609151705_scheduler_funciones_reconciliado.sql
  pendiente: 202609151710_interruptor_autonomia.sql
  pendiente: 202609151715_operaciones_externas.sql
anotadas sin archivo  : 5          <-- eran 3
  … + 202609141200_scheduler_persistente.sql
  … + 202609141300_scheduler_funciones.sql
```

No apareció ninguna divergencia nueva. Los dos nombres históricos pasan a
«anotada sin archivo», el mismo estado que el ledger ya tenía para otros tres.

## 7. Estado del ledger, antes y después

| | Antes | Después |
|---|---|---|
| Filas | 45 | **45** |
| md5 del contenido completo | `58ff01f220787396657af7832f6c48c8` | **`58ff01f220787396657af7832f6c48c8`** |

**Bit a bit el mismo.** Las dos filas históricas, literales:

```
202609141200_scheduler_persistente.sql
  sha256 = 897cb5d3da222e85913f288aace4b6fe02fb34eb2b9254d47212a6be47d8fc0e
  origen = aplicada   por = postgres   2026-09-15 19:32:03.648710+00   338 ms
  nota = NULL   evidencia = NULL

202609141300_scheduler_funciones.sql
  sha256 = f325bd442baad0f70168deedd92175f5ffb15cecc79055f9cbfdd4c2165e77f1
  origen = aplicada   por = postgres   2026-09-15 19:40:13.622699+00   289 ms
  nota = NULL   evidencia = NULL
```

No se ejecutó ningún `UPDATE`, `DELETE` ni `INSERT` sobre el ledger. La
reconciliación **no escribe en la base**: cambia archivos del repositorio. El
md5 idéntico lo demuestra por medición, no por declaración.

## 8. Estado de los objetos

En producción, sin recrear nada:

| | Esperado (10.2/10.4) | Medido |
|---|---|---|
| Tablas `job_*` | 5 | **5** |
| Índices | 21 | **21** |
| Constraints | 48 | **48** |
| Políticas | 5 | **5** |
| Funciones | 10 | **10** |
| md5 de los 10 cuerpos | `614d3a167d73bac0ca16cf6fc002a19c` | **idéntico** |
| Esquema de `pgcrypto` | `extensions` | **`extensions`** |
| `extensions.digest` / `gen_random_bytes` | resuelven | **true / true** |
| `asistente_owner` con `USAGE` en `extensions` | sí | **true** |

Y fuera del scheduler: `asistente` 35 tablas, `public` 135, 132 políticas, 192
filas en `django_migrations` — todo igual que al cerrar el paso 10.3.

## 9. Fase 6 — qué haría el CLI, medido

El CLI **no tiene modo de ensayo** para `--aplicar`, así que la forma de saber
qué haría es hacerlo sobre una réplica exacta. Se usó la restaurada del
respaldo de §2, tomada minutos antes.

```
ANTES    5 | 21 | 48 | 5 | 10 | 614d3a167d73bac0ca16cf6fc002a19c
  [ok] 202609151700_scheduler_persistente_reconciliado.sql  (15 ms)
  [ok] 202609151705_scheduler_funciones_reconciliado.sql    (55 ms)
  [ok] 202609151710_interruptor_autonomia.sql               (12 ms)
  [ok] 202609151715_operaciones_externas.sql                (10 ms)
DESPUES  5 | 21 | 48 | 5 | 10 | 614d3a167d73bac0ca16cf6fc002a19c
```

**No recrea tablas, no duplica índices, no duplica políticas, y la sustitución
de funciones es una reescritura byte a byte** — el md5 no se mueve. Nada
destructivo ni duplicativo. Aun así, **no se ejecutó en producción**: la Fase 6
ordena detenerse ahí, y ahí se detuvo.

## 10. Scheduler

Ejecutado **en producción**, dentro de una transacción revertida. Las 5 tablas
del scheduler están vacías, así que la prueba sembró catálogo y agenda, recorrió
el flujo y deshizo todo.

```
job_claim()      intento #1, fencing=1
                 capability 64 hex   -> extensions.gen_random_bytes resolvio
                 config_hash 64 hex  -> extensions.digest resolvio
                 adf6952df87766c2b0094ce1d72e9eaa...
job_contexto()   turno completo; config_hash coincide con el del claim
job_heartbeat()  lease renovado
job_finalize()   desenlace = succeeded
job_run          estado 'succeeded'
job_run_event    3 eventos
>>> ROLLBACK <<<
job_catalogo 0 · job_schedule_state 0 · job_run 0 · job_attempt 0 · job_run_event 0
0 falla(s)
```

Sin errores de permisos y sin errores de resolución de funciones.

## 11. Rollback

Disponible y **verificado sin ejecutarlo**: los dos archivos originales están en
`git HEAD` y en una copia fuera del repositorio, y ambos hashean a lo mismo
(`d77a31b2…` y `63bc3f14…`).

```bash
git checkout -- supabase/202609141200_scheduler_persistente.sql \
                supabase/202609141300_scheduler_funciones.sql
rm supabase/202609151700_scheduler_persistente_reconciliado.sql \
   supabase/202609151705_scheduler_funciones_reconciliado.sql
```

Si alguna vez se detectara una alteración física en la base:

```bash
sh despliegue/respaldo/restaurar.sh <carpeta> 20260917_104932 <base> -U <usuario>
```

**El ledger no se usa como mecanismo de rollback en ningún caso.**

## 12. Diferencias residuales y riesgos

1. **El vínculo nombre↔historia queda implícito.** Quien lea el ledger verá
   `202609141200_…` anotada sin archivo y `202609151700_…_reconciliado`
   pendiente, sin que nada escrito los relacione. La Fase 3 prohibía añadir una
   nota de cabecera; **conviene autorizarla aparte**.
2. **Las dos reconciliadas quedan PENDIENTES**, no aplicadas. El ledger no
   registra todavía que su contenido corresponde al efecto vigente. Cerrar eso
   exige o `--aplicar` (medido como no-op, pero es DDL en producción) o
   `--adoptar`, que necesita **regenerar el manifiesto** contra una referencia
   PostgreSQL 17 con pgcrypto en `extensions` (el actual es PG16 y registra
   `ext`).
3. **Las 2 migraciones de Fase 1 siguen sin aplicar** y siguen siendo del
   dominio del motor: `crm_migrator` no tiene permisos sobre `asistente`, y no
   se le concedieron.
4. **Las tablas que crearían esas 2 migraciones nacerían bajo `postgres`**, no
   bajo `asistente_owner` como las `job_*`. Decisión pendiente.
5. **Los bytes históricos siguen sin ser recuperables.** Nada de este paso lo
   cambia ni lo pretende.

## 13. Declaración explícita

> **Los bytes originales ejecutados el 15/09 no fueron recuperables.
> La reconciliación actual reproduce el efecto histórico verificado y
> mantiene intactos los registros históricos del ledger.**

La verificación de que reproduce el efecto no es una afirmación: corregir
`ext.` → `extensions.` produce **los 10 cuerpos de función idénticos, byte a
byte, a los que PostgreSQL guarda en producción**.

---

## Criterio de éxito

| | |
|---|---|
| checksum actual = 0 divergencias | **sí** (2 → 0) |
| ledger histórico intacto | **sí** — 45 filas, mismo md5, filas literales sin cambio |
| no duplicación de objetos | **sí** — 5/21/48/5/10 y md5 sin moverse, medido en réplica |
| scheduler funcional | **sí** — `succeeded` en producción, revertido |
| respaldo disponible | **sí** — `20260917_104932`, verificado restaurando |
| rollback disponible | **sí** — git + copia externa, ambos comprobados |
| ninguna modificación no autorizada | **sí** — la base no se modificó; el cambio es del repositorio |

## Estado al cerrar

Producción: ledger 45 filas (md5 intacto), `asistente` 35 tablas, `public` 135,
132 políticas, 192 migraciones de Django, las 5 tablas del scheduler vacías.
Repositorio: 2 archivos borrados (versionados, restaurables) y 2 nuevos.
Réplicas eliminadas. `DBUSER`, ownership, RLS, Celery, motor, autonomía e
integraciones: sin tocar.
