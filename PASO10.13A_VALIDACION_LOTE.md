# Paso 10.13A — Validación final del lote de cuatro migraciones

**Fecha:** 17/09/2026
**Veredicto: GO técnico.** Las cuatro migraciones pasan juntas sobre una réplica
restaurada del respaldo `20260917_141238`, sin huecos, con el ledger coherente y
con un rollback demostrado.
**Producción intacta**: ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`,
0 tablas de las migraciones 3 y 4, rol `autonomia_operador` inexistente.
**No se ejecutó nada en producción.**

---

## 1. Restore y precondiciones

Réplica limpia desde **`20260917_141238`**, `restaurar.sh` código 0.

| Precondición | Medido | Esperado |
|---|---|---|
| Ledger: filas | **45** | 45 |
| Ledger: md5 | **`58ff01f220787396657af7832f6c48c8`** | idem |
| `asistente.interruptor_autonomia` | **0** | ausente |
| `asistente.operaciones_externas` | **0** | ausente |
| Rol `autonomia_operador` | **0** | ausente |
| Funciones `job*` / md5 | **10 / `614d3a167d73bac0ca16cf6fc002a19c`** | idem |
| Tablas en `asistente` | **35** | 35 |
| Scheduler | **`succeeded`, 0 fallas** | operativo |

## 2. Ejecución con el mecanismo canónico

```bash
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar
```

Sin SQL manual alternativo. Resultado:

```
[migrar] 4 pendiente(s):
  [ok] 202609151700_scheduler_persistente_reconciliado.sql  (15 ms)
  [ok] 202609151705_scheduler_funciones_reconciliado.sql    (63 ms)
  [ok] 202609151710_interruptor_autonomia.sql               (12 ms)
  [ok] 202609151715_operaciones_externas.sql                ( 9 ms)
[migrar] 4 aplicada(s).

exit code: 0     SQL: 99 ms     proceso completo: 0,78 s
```

**El orden es el canónico** y sale del nombre del archivo, no de una selección
manual.

### DDL realmente ejecutado — 119 operaciones, registradas por *event triggers*

| Comando | Nº |
|---|---|
| `REVOKE` (función) | 21 |
| `ALTER TABLE` (tabla) | 18 |
| `CREATE FUNCTION` | 11 |
| `ALTER FUNCTION` | 10 |
| `CREATE POLICY` | 10 |
| `DROP POLICY` | 7 |
| `GRANT` (función / tabla / esquema) | 18 |
| `REVOKE` (tabla) | 6 |
| `ALTER TABLE` (trigger de FK) | 4 |
| **`CREATE INDEX`** | **4** |
| `COMMENT` | 7 |
| **`CREATE TABLE`** | **2** |
| `ALTER TABLE` (constraint) | 1 |

**Los 2 `CREATE TABLE` y los 4 `CREATE INDEX` son exclusivamente de las tablas
nuevas:**

```
CREATE TABLE  asistente.interruptor_autonomia
CREATE INDEX  asistente.interruptor_autonomia_pkey
CREATE INDEX  asistente.interruptor_autonomia_vigente_idx
CREATE TABLE  asistente.operaciones_externas
CREATE INDEX  asistente.operaciones_externas_pkey
CREATE INDEX  asistente.operaciones_externas_ejecutando_idx
```

Cero sobre los objetos históricos del scheduler.

### Bloqueos observados

El muestreo en paralelo (cada 20 ms) atrapó
**`public.organization · ShareRowExclusiveLock`** — el de las FK de las
migraciones 3 y 4. Los de `asistente` duran decenas de milisegundos y se
midieron con precisión reteniendo transacciones en los pasos 10.8 y 10.11:

| Migración | Bloqueos |
|---|---|
| 1 · persistente | `AccessExclusive` sobre las 5 `job_*`; `ShareRowExclusive` sobre `job_run` y `job_schedule_state` (la FK que se recrea) |
| 2 · funciones | `AccessExclusive` sobre las 5 `job_*` **+ `tenant_config` y `tenant_config_historial`** |
| 3 y 4 | **`ShareRowExclusive` sobre `public.organization`** (bloquea escrituras del CRM) |

## 3. No existen huecos

`mig.huecos()` invocado directamente sobre la réplica ya migrada:

```
pendientes         : 0   []
discrepancias      : 0
no canonicos       : 0
anotadas en ledger : 49
max(anotadas)      : 202609151715_operaciones_externas.sql
huecos()           : 0   []      -> resultado vacio: True
```

| | |
|---|---|
| Ledger | **45 → 49** |
| md5 de las 45 anteriores a `202609151700` | **`58ff01f220787396657af7832f6c48c8`** — idéntico |
| Filas nuevas | **4**, todas `origen='aplicada'` |

Y cada fila nueva contra el checksum del archivo en disco:

| Archivo | Ledger = disco | ms |
|---|---|---|
| `202609151700_…persistente_reconciliado` | `e7a70f0556d29022…` **sí** | 11 |
| `202609151705_…funciones_reconciliado` | `ca0bf08137214414…` **sí** | 59 |
| `202609151710_interruptor_autonomia` | `9c8df21b002826e1…` **sí** | 9 |
| `202609151715_operaciones_externas` | `9c2f242d9319664a…` **sí** | 5 |

## 4. Reconciliaciones 1 y 2 — **12 de 12 idénticos a producción**

| Comprobación | Valor (igual en réplica y producción) |
|---|---|
| **md5 conjunto de los 10 cuerpos `job*`** | `614d3a167d73bac0ca16cf6fc002a19c` |
| Tablas `job_*` / índices / constraints / policies | 5 / 21 / 48 / 5 |
| Triggers de usuario | 0 |
| Funciones `SECURITY DEFINER` en `asistente` | 9, **todas con `search_path` fijado** |
| Dueño de funciones y tablas `job_*` | `asistente_owner` |
| ACL de `job_claim` | `asistente_owner=X, scheduler_coordinator=X` |
| `asistente_owner` con `USAGE` en `extensions` | `true` |

**Función por función: 10 de 10 con el cuerpo byte a byte idéntico.**

## 5. Interruptor

| | |
|---|---|
| Tabla creada · RLS / FORCE | 1 · **`true` / `true`** |
| Políticas | `tenant_aislado→{app_backend}` · `tenant_aislado_operador→{autonomia_operador}` |
| Índices / constraints | 2 / 4 |
| ACL | `postgres=arwdDxtm`, **`app_backend=r`**, `autonomia_operador=ar` |
| **Estado sembrado** | **`detenido`**, actor `migracion` |
| Filas `activo` | **0** |
| `autonomia_operador` | **NOLOGIN**, sin super, sin createrole, sin bypassrls |
| Operador: sel/ins/upd/del | `true/true/false/false` |
| `app_backend`: sel/ins/upd/del | **`true/false/false/false`** |

### Comportamiento, con `session_user` real (`sim_runtime`)

```
LEE: detenido                                       ← runtime puede leer
INSERT 'activo'   → permission denied for table
UPDATE            → permission denied for table
DELETE            → permission denied for table
SET ROLE autonomia_operador → permission denied
autonomia_detener(...)      → detenido               ← la parada SÍ funciona
autonomia_detener(...,'activo') → function does not exist
```

**Tenant nuevo:** la segunda organización, sin fila, se dio de alta por la vía
del operador y quedó **`detenido`**.

> **Nota operativa:** la semilla de la migración sólo alcanza a organizaciones
> con `tenant_config`. En producción hay **2 organizaciones y 1 tenant**, así que
> `Rapilink Telecomunicaciones` quedará **sin fila** → estado `sin_registro` →
> **BLOQUEA**. Es el comportamiento fail-closed correcto, pero conviene saberlo
> antes y no descubrirlo después.

## 6. Idempotencia

Tabla con 3 constraints, RLS + FORCE, 1 política.

| Caso | Resultado | Llamadas externas |
|---|---|---|
| Misma clave + mismos argumentos | `ejecutar` / `repetida` | **1** |
| Misma clave + argumentos distintos | `CLAVE_REUTILIZADA` | **0** |
| Concurrencia (2 hilos) | una sola ejecutada | **1** |
| Fallo → retry implícito | `OPERACION_FALLIDA_PREVIA` | **0** |
| Retry explícito | se ejecuta | 1 |

**4 llamadas simuladas en total, todas justificadas. Ninguna a WispHub, SmartOLT
ni ningún servicio externo real** — la acción es una función local que sólo
anota que la llamaron.

## 7. Scheduler

`job_claim → job_contexto → job_heartbeat → job_finalize` = **`succeeded`**,
**0 fallas**, después de aplicar las cuatro. No se modificó nada del scheduler.

## 8. Locks

Escenario de 10.6/10.7 reproducido: `ACCESS EXCLUSIVE` retenido sobre
`asistente.tenant_config`, `lock_timeout=10s`.

```
[migrar] 4 pendiente(s):
  [ok]    202609151700_…persistente  (20 ms)
  [FALLA] 202609151705_…funciones: LockNotAvailable: canceling statement due to lock timeout
  La migracion se deshizo entera y NO quedo anotada. Las anteriores si.
exit code: 1     duracion: 10,6 s
```

| | |
|---|---|
| Ledger | 45 → **46** (sólo la que sí aplicó) |
| La que falló, ¿anotada? | **no** |
| ¿Dejó objetos a medias? | **no** — `interruptor_autonomia` y `operaciones_externas` no existen |
| Migraciones 3 y 4 | **nunca corrieron** |

**Falla limpiamente y es atómica.** Y liberado el bloqueo, el reintento
recupera: 3 aplicadas, exit 0, ledger 49, en 0,59 s.

## 9. Backup / restore del estado resultante

Respaldo de la réplica ya migrada (3 artefactos, 8.915.163 B) → restauración
desde cero → **12 de 12 idénticos**:

ledger 49 / mismo md5 · 37 tablas en `asistente` · md5 de las 10 funciones ·
38 políticas · `autonomia_operador` NOLOGIN · `app_backend` `true/false` ·
operador `true/true` · RLS+FORCE · función `secdef` · **semilla `detenido`** ·
**0 filas `activo`** · filas de `operaciones_externas`.

Scheduler sobre la restaurada: **`succeeded`, 0 fallas.**

## 10. Rollback — el hallazgo que importa

### Durante la migración (antes del COMMIT de un archivo)

**Automático y medido** (§8): la transacción de ese archivo se deshace entera y
**no queda anotado**. Los anteriores de la misma corrida sí quedan aplicados. Se
corrige la causa y se reintenta.

### Después de una migración ya anotada

Demostrado en réplica. Se hizo `drop table` de las dos tablas nuevas:

```
tablas nuevas tras el drop : 0
ledger                     : 49 filas
las filas de 3 y 4 SIGUEN anotadas: 2

$ cli/migrar_asistente.py --estado   → pendientes: 0
$ cli/migrar_asistente.py --aplicar  → [migrar] 0 migraciones pendientes.
```

> **Un `drop` manual no es un rollback: es una divergencia.** El ledger es de
> solo agregar, así que la fila se queda diciendo «aplicada» mientras los
> objetos ya no están — y el CLI **no las reaplica**, porque para él no hay nada
> pendiente. La base queda en un estado que sólo se arregla restaurando.

### El rollback que sí cierra

Restaurar el respaldo **`20260917_141238`**:

```
restaurar.sh → codigo 0
ledger 45 filas, md5 58ff01f220787396657af7832f6c48c8 · tablas nuevas: 0
```

Vuelve **exacto** al punto de partida.

### Lo que NO debe hacerse a mano

- `delete`/`update` sobre `asistente.migraciones_aplicadas` — es de solo
  agregar y tiene disparadores que lo impiden; intentarlo deja el ledger
  sospechoso sin arreglar nada.
- `drop` de objetos sin restaurar después, por lo de arriba.
- Reaplicar con SQL manual: el ledger quedaría diciendo una duración y un
  checksum que no corresponden a lo ejecutado.
- Forzar el lock matando sesiones del motor o del CRM.

---

# GO / NO-GO técnico para producción

## **GO**, con las condiciones de abajo.

### Resultado en réplica

| Criterio | Resultado |
|---|---|
| Las cuatro pasan juntas | **sí** — exit 0, 99 ms de SQL |
| `huecos()` vacío | **sí** |
| Ledger 45 → 49, las 45 originales idénticas | **sí** |
| Checksums del ledger = archivos en disco | **4 de 4** |
| Reconciliaciones idénticas a producción | **12/12**, y 10/10 cuerpos byte a byte |
| Interruptor sembrado `detenido`, 0 `activo` | **sí** |
| `app_backend` no puede activar | **sí** — 4 vías cerradas |
| Operador puede activar y detener | **sí** |
| Tenant nuevo nace `detenido` | **sí** |
| Idempotencia: los 5 casos | **sí**, 0 llamadas externas reales |
| Scheduler | **`succeeded`** |
| Backup/restore del resultado | **12/12** |
| Rollback demostrado | **sí** |

### Duración medida

**99 ms de SQL** (15 + 63 + 12 + 9), **0,78 s** de proceso completo.
Con un bloqueo de por medio: hasta **10,6 s** antes de abortar.

### Objetos bloqueados

| Tabla | Modo | Quién la usa |
|---|---|---|
| `asistente.job_catalogo`, `job_schedule_state`, `job_run`, `job_attempt`, `job_run_event` | `ACCESS EXCLUSIVE` | vacías; sólo roles administrativos |
| **`asistente.tenant_config`**, **`tenant_config_historial`** | `ACCESS EXCLUSIVE` | **el motor** |
| **`public.organization`** | `SHARE ROW EXCLUSIVE` | **el CRM** (bloquea escrituras) |

### Ventana recomendada

Fuera del horario de atención, con el motor sin tráfico de WhatsApp. Lo que hay
que garantizar no es duración —son décimas de segundo— sino que **nadie tenga
tomada ninguna de esas 8 tablas**.

### Comandos exactos

```bash
# 1) respaldo fresco y verificado
py -3.13 despliegue/respaldo/respaldar.py --destino "$CARPETA" \
        --imagen pgvector/pgvector:pg17
#    restaurar en desechable y:
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto "$PUERTO"

# 2) preflight (§ validaciones pre)

# 3) la migracion -- lock_timeout POR SESION, nunca global
cd <repo>
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar \
  > /tmp/p1013.out 2> /tmp/p1013.err
echo "codigo: $?"

# 4) el rol y los permisos del operador (SQL del paso 10.11 §E)
#    + grant autonomia_operador to postgres with inherit false, set true;
```

### Validaciones previas (abortar si alguna falla)

`checksum distinto: 0` y **4 pendientes** · ledger **45 filas / `58ff01f2…`** ·
0 bloqueos sobre `asistente` y `public.organization` · 0 transacciones abiertas ·
`job_catalogo` = 0 filas · sin sesiones activas de `motor_user` · 35 tablas en
`asistente` · md5 de funciones `614d3a16…` · `public` 135 tablas de `crm_owner` ·
**respaldo verificado con 0 fallas** · credencial `postgres` · las tres tablas y
el rol **ausentes**.

### Validaciones posteriores

`huecos()` vacío · ledger **49**, las 45 originales con md5 `58ff01f2…` · los 4
checksums = archivos en disco · md5 de las 10 funciones `614d3a16…` sin moverse ·
5/21/48/5 en `job_*` · interruptor con RLS+FORCE, 2 políticas, semilla
**`detenido`**, **0 filas `activo`** · `app_backend` `true/false/false/false` ·
operador NOLOGIN con `true/true/false/false` · las 4 vías de activación cerradas ·
idempotencia en sus 5 casos · scheduler `succeeded` · datos de negocio sin
cambios.

### Criterio de abortar

- Cualquier validación previa en rojo.
- `LockNotAvailable`: **no forzar, no matar sesiones**. Detenerse, anotar qué
  objeto bloqueó, conservar la evidencia y reprogramar. **No continuar
  parcialmente.**
- DDL distinto de las 119 operaciones inventariadas en §2.
- Cualquier fallo posterior: **no corregir a mano en producción** — restaurar
  desde el respaldo.

### Riesgos

1. **`public.organization` se bloquea para escrituras** durante las migraciones
   3 y 4. Es del CRM, no del motor.
2. **`tenant_config(_historial)` se bloquean** durante la migración 2 (~60 ms).
   Las lee el motor.
3. **La segunda organización quedará `sin_registro`** — bloquea, que es lo
   correcto, pero conviene decidir si se le siembra fila.
4. **El SQL del operador (10.11 §E) y el código de `db.py` (10.12) van juntos.**
   Aplicar el `REVOKE` sin desplegar el código deja a `cli/autonomia.py` sin
   poder mover el interruptor; desplegar el código sin crear el rol, también.
   **Ninguno de los dos sirve solo** — y este paso **no despliega código**.
5. **Un `drop` manual posterior no revierte nada** (§10): deja el ledger
   divergente y el CLI ciego.
6. **`postgres` sigue fuera del modelo administrativo**; se cierra con el paso 15.

### Lo que sigue sin hacerse

Autonomía **DETENIDA / NO OPERATIVA**. No se despliega `interruptor.py` ni
`idempotencia.py`, no se cambia `DBUSER`, no se implementan niveles 0–4, y no se
tocan M02, M03, M09, WispHub, SmartOLT ni el scheduler.

---

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, **0**
tablas de las migraciones 3 y 4, **0** rol `autonomia_operador`. Réplicas
eliminadas. Respaldo **`20260917_141238`** conservado en
`C:\Users\Usuario\respaldo_p1013\`.

**Las cuatro migraciones pasaron juntas en réplica. Me detengo y espero
autorización explícita para ejecutar en producción.**
