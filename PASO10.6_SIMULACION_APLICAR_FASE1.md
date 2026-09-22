# Paso 10.6 — Simulación completa de `--aplicar` sobre el estado reconciliado

**Fecha:** 17/09/2026
**Alcance:** simulación en réplica. **Producción no se modificó** — ninguna
escritura, ninguna migración, el ledger intacto en 45 filas y md5
`58ff01f220787396657af7832f6c48c8`.
**Clasificación:** **A — seguro para producción, con una condición operativa.**

> No basta con «terminó con código 0». Se instrumentó la réplica con
> `log_statement = 'all'` y dos *event triggers* (`ddl_command_end` y
> `sql_drop`) para registrar **cada DDL realmente ejecutado**, con su comando y
> su identidad. Lo que sigue son 113 operaciones observadas, no inferidas.

---

## 1. Estado antes

Réplica virgen construida desde el respaldo validado **`20260917_104932`** con
`restaurar.sh` (código 0). Reproduce producción: **25 de 25** comprobaciones
estructurales idénticas, scheduler funcional con 0 fallas, y el **ledger con el
md5 exacto de producción**: `58ff01f220787396657af7832f6c48c8`, 45 filas.

| | |
|---|---|
| Ledger | 45 filas · 2 con `origen='aplicada'` |
| Funciones `job*` | 10 · md5 conjunto `614d3a167d73bac0ca16cf6fc002a19c` |
| Tablas / índices / constraints / políticas en `asistente` | 35 / 98 / 142 / 35 |
| `public` | 135 tablas · 132 políticas · todas de `crm_owner` |
| pgcrypto | `extensions` |

Archivos pendientes y su checksum:

```
202609151700_scheduler_persistente_reconciliado.sql  e7a70f0556d29022…
202609151705_scheduler_funciones_reconciliado.sql    ca0bf08137214414…
202609151710_interruptor_autonomia.sql               e0d6b8dcb7d29f0b…
202609151715_operaciones_externas.sql                9c2f242d9319664a…
```

Las dos filas históricas, literales: `897cb5d3da22…` (19:32:03, 338 ms) y
`f325bd442baa…` (19:40:13, 289 ms), ambas `origen=aplicada`, `por=postgres`,
`nota=NULL`, `evidencia=NULL`.

## 2-3. Comando ejecutado y salida

```
$ py -3.13 cli/migrar_asistente.py --aplicar
[migrar] 4 pendiente(s):
  [ok] 202609151700_scheduler_persistente_reconciliado.sql  (18 ms)
  [ok] 202609151705_scheduler_funciones_reconciliado.sql    (59 ms)
  [ok] 202609151710_interruptor_autonomia.sql               (11 ms)
  [ok] 202609151715_operaciones_externas.sql                (10 ms)
[migrar] 4 aplicada(s).

stderr: (vacío)      código de salida: 0
```

## 4. SQL/DDL realmente ejecutado

113 operaciones registradas por los *event triggers*. Repartidas:

| Comando | Nº | Sobre qué |
|---|---|---|
| `REVOKE` (función) | 20 | las 10 funciones, dos veces (antes y después de los `GRANT`) |
| `ALTER TABLE` (tabla) | 18 | `owner to`, `enable row level security` |
| `CREATE FUNCTION` | 10 | las 10 `job*` — es como el catálogo registra `create or replace` |
| `ALTER FUNCTION` | 10 | `owner to asistente_owner` |
| `CREATE POLICY` | 9 | 7 recreadas + 2 nuevas (Fase 1) |
| `DROP POLICY` | 7 | 5 de `job_*` + `scheduler_congela` en `tenant_config` y `tenant_config_historial` |
| `GRANT` (función/tabla/esquema) | 13 | |
| `REVOKE` (tabla) | 5 | `revoke all … from public` sobre las 5 `job_*` |
| `ALTER TABLE` (trigger) | 4 | triggers de integridad referencial de la FK recreada |
| `CREATE INDEX` | 4 | **las 4 son de las tablas nuevas de Fase 1** |
| `CREATE TABLE` | 2 | **las 2 son de Fase 1** |
| `ALTER TABLE` (constraint) | 1 | `js_run_coherente` |
| `COMMENT` | 6 | |

**Cero `CREATE TABLE` y cero `CREATE INDEX` sobre los objetos históricos.** El
`if not exists` hizo su trabajo: las 5 tablas y los 21 índices no se tocaron.

La operación física más notable sobre lo histórico:

```sql
alter table asistente.job_schedule_state drop constraint if exists js_run_coherente;
alter table asistente.job_schedule_state add constraint js_run_coherente
  foreign key (current_run_id, job_code, organization_id, current_slot)
  references asistente.job_run (id, job_code, organization_id, scheduled_slot);
```

Es idempotente por diseño, pero **no es un no-op**: elimina y recrea la clave
foránea, revalidándola y creando cuatro triggers de integridad nuevos.

## 5. Ledger, antes y después

| | Antes | Después |
|---|---|---|
| Filas | 45 | **49** |
| Filas preexistentes modificadas | — | **0** |
| Las 2 históricas | — | **INTACTAS**, campo por campo |

Cuatro filas nuevas, todas `origen='aplicada'`, con los checksums de los
archivos reconciliados. El CLI **no tocó** ninguna fila anterior: no hubo
`UPDATE`, ni `DELETE`, ni reescritura de checksums.

## 6. Objetos, antes y después

| | Antes | Después | Comunes con definición distinta |
|---|---|---|---|
| Tablas en `asistente` | 35 | 37 (+2 de Fase 1) | — |
| Índices | 98 | 102 (+4 de Fase 1) | **0 de 98** |
| Constraints | 142 | 149 (+7 de Fase 1) | **0 de 142** |
| Políticas | 35 | 37 (+2 de Fase 1) | **0 de 35** |
| Funciones `job*` | 10 | 10 | md5 conjunto **idéntico** |

Las políticas se **eliminan y se recrean con definición idéntica**; los índices
y constraints preexistentes no se tocan; los cuerpos de las 10 funciones se
reescriben byte a byte iguales.

### El ACL: lo que parecía un cambio y no lo es

La comparación mostró que las 5 tablas `job_*` pasaban de `(nulo)` a
`{asistente_owner=arwdDxtm/asistente_owner}`, por el `revoke all … from public`.
Dos mediciones lo aclaran:

1. **No hay cambio de permisos.** 315 combinaciones rol × privilegio × tabla y
   90 combinaciones función × rol comparadas contra producción: **0 diferencias
   efectivas**. El ACL de las funciones es además **literalmente idéntico**.
2. **En producción el ACL ya está en la forma explícita.** Las 5 tablas ya
   tienen `{asistente_owner=arwdDxtm/asistente_owner}`. El `(nulo)` que mostraba
   la réplica es un artefacto de `pg_dump`, que **omite los ACL iguales al valor
   por defecto** — verificado: el volcado emite `REVOKE`/`GRANT` de funciones
   pero ninguno de tabla para `job_*`.

O sea: **aplicar en producción no cambiaría esos ACL en absoluto.**

## 7. Scheduler, después de `--aplicar`

```
job_claim()      intento #1
                 capability 64 hex   -> extensions.gen_random_bytes resolvio
                 config_hash 64 hex  -> extensions.digest resolvio
job_contexto()   turno completo; config_hash coincide con el del claim
job_heartbeat()  lease renovado
job_finalize()   desenlace = succeeded
job_run          'succeeded'    job_attempt  'succeeded' con completed_at
job_run_event    3 eventos
0 falla(s)
```

## 8. Datos

| | Producción | Réplica tras `--aplicar` |
|---|---|---|
| `asistente.messages` / `conversations` / `tool_calls` | 2.594 / 302 / 1.190 | **iguales** |
| `asistente.tenant_config` | 1 | **1** |
| `public.case` / `public.activity` | 188 / 568 | **iguales** |

Ningún dato histórico alterado, ningún objeto duplicado, ninguna fila
inesperada.

## 9-10. Respaldo y restauración posteriores

Respaldo B.6/B.7 de la réplica ya aplicada (3 artefactos, 8.908.328 bytes) y
restauración desde cero en otra réplica virgen: `restaurar.sh` **código 0**,
scheduler **0 fallas** con `succeeded`.

El ledger llega completo al otro lado: **49 filas, 6 con `origen='aplicada'`** —
las 2 históricas con sus checksums originales y las 4 nuevas con los suyos. La
trazabilidad sobrevive al ciclo.

## 11. Riesgos

1. **No es un no-op: toma bloqueos `ACCESS EXCLUSIVE` sobre 7 tablas.** Las 5
   de `job_*` más **`asistente.tenant_config` y `tenant_config_historial`**,
   cuya política `scheduler_congela` se elimina y se recrea. Esas dos **las lee
   el motor**. Todo ocurre dentro de la transacción del archivo, así que nadie
   ve un estado sin política: lo que pasa es que **esperan**. Las dos
   migraciones reconciliadas tardaron **77 ms** en total (18 + 59).
2. **La clave foránea `js_run_coherente` se elimina y se recrea**, con
   revalidación. Hoy `job_schedule_state` está vacía en producción, así que es
   instantáneo; con datos sería una operación de coste real.
3. **Las 2 migraciones de Fase 1 sí crean objetos nuevos**: 2 tablas, 4
   índices, 7 constraints y 2 políticas. Eso no es reconciliación, es
   despliegue — y sigue sin decidirse con qué credencial se aplican ni bajo qué
   dueño nacen (nacieron bajo `postgres`, no bajo `asistente_owner`).
4. **El CLI no tiene modo de ensayo.** La única forma de saber qué haría es
   hacerlo sobre una réplica exacta, que es lo que se hizo aquí. Conviene que
   quede como requisito del procedimiento, no como iniciativa.
5. **Un error mío en este mismo paso:** imprimí «sigue en nulo» junto a un valor
   medido que decía lo contrario. Era una etiqueta escrita de antemano. La
   corrección está en §6 y cambia la conclusión sobre el ACL a mejor.

## 12. Clasificación

### **A — SEGURO PARA PRODUCCIÓN, con una condición operativa**

Se cumple todo lo que A exige en cuanto al resultado: no recrea, no duplica, no
destruye, no altera datos, deja el estado correcto y el ledger histórico
intacto. Y se descarta C sin ambigüedad.

**Pero la letra de A dice «no realiza cambios físicos innecesarios», y eso no es
literalmente cierto.** Sí los realiza: reemplaza 10 funciones con cuerpos
idénticos, elimina y recrea 7 políticas, y elimina y recrea una clave foránea.
Son inocuos en efecto —medido— pero son operaciones reales, y toman bloqueos
exclusivos sobre siete tablas, dos de ellas del motor.

No es «B — requiere ajuste» porque no hay nada que ajustar en los archivos: son
scripts declarativos completos y correctos, y su idempotencia funciona. Lo que
hace falta no es un cambio, es una **precaución operativa**.

## 13. Recomendación técnica para producción

Si se autoriza `--aplicar` en producción:

1. **Ventana tranquila**, verificada antes: 0 transacciones abiertas, 0 bloqueos
   sobre `asistente`, y el motor sin tráfico — igual que se hizo en el paso 9.
2. **`lock_timeout` en la sesión**, por ejemplo `PGOPTIONS="-c lock_timeout=10s"`.
   Si algo estuviera bloqueado, la migración aborta en vez de encolar al motor
   detrás de un `ACCESS EXCLUSIVE` sobre `tenant_config`.
3. **Respaldo fresco y verificado** justo antes, con el procedimiento B.6/B.7.
4. **Decidir antes qué pasa con las 2 migraciones de Fase 1**: `--aplicar` las
   ejecuta en la misma pasada y no son reconciliación. Si sólo se quiere
   reconciliar, hay que aplicar primero y sacar las otras dos del directorio, o
   asumir que se despliegan a la vez.
5. **Con qué credencial**: `postgres` es dueño de `asistente`; `crm_migrator` no
   tiene permisos ahí y no se le van a conceder.
6. **Verificar después** con `verificar_restauracion.py` y el flujo del
   scheduler, no con «código 0».

---

## Criterio de éxito

| | |
|---|---|
| El ledger histórico no se toca | **sí** — 0 filas preexistentes modificadas |
| No se recrean ni duplican objetos | **sí** — 0 de 98 índices, 0 de 142 constraints, 0 de 35 políticas con definición distinta |
| Los cuerpos de las funciones no cambian | **sí** — md5 conjunto idéntico |
| Los permisos no cambian | **sí** — 315 + 90 comprobaciones, 0 diferencias |
| Los datos no cambian | **sí** |
| Scheduler funcional después | **sí** — `succeeded` |
| Respaldo y restauración posteriores | **sí** — código 0, scheduler 0 fallas |
| Producción sin modificar | **sí** — ledger md5 y objetos idénticos al cierre del 10.5 |

## Estado al cerrar

Producción: ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`, 35 tablas
en `asistente`, 5 `job_*`, `--aplicar` **no ejecutado**. Réplicas `pg-106` y
`pg-106b` eliminadas junto con su respaldo temporal. `DBUSER`, ownership, RLS,
Celery, motor, autonomía e integraciones: sin tocar.
