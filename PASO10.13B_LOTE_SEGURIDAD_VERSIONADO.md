# Paso 10.13B — Segregación empaquetada y lote de cinco revalidado

**Fecha:** 17/09/2026 · **Producción: NO se ejecutó nada.**
Ledger 45 filas idénticas al respaldo (`63c7c41844593669a03ca2867a8e4218`),
0 tablas nuevas, 0 rol `autonomia_operador`, 0 función de parada.

**Veredicto: GO técnico** para el lote de **cinco** migraciones, condicionado a
una autorización nueva y explícita.

---

## 1. La migración nueva

| | |
|---|---|
| **Archivo** | `supabase/202609151720_segregacion_operador_autonomia.sql` |
| **Checksum** (`sha256-utf8-lf-v1`) | **`5699ffcbffb8f7420ff7681038f41bcf2cecadcb302518a1f4515efbc26bbb0b`** |
| Tamaño | 15.674 bytes · UTF-8 sin BOM · sólo LF |
| Canónico según el CLI | **sí** — `no canonicos: 0` |

### Qué hace, en orden

| § | Sentencia | Por qué |
|---|---|---|
| 0 | Dos `raise` de precondición | Se niega a correr si falta la tabla de 1710 o si no tiene RLS+FORCE |
| 1 | `create role autonomia_operador nologin` (guardado por `if not exists`) | No es una credencial nueva: se alcanza con `SET ROLE` |
| 1 | `alter role … nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls` | Vuelve a la forma mínima aunque el rol ya existiera |
| 1 | `grant autonomia_operador to postgres with inherit false, set true` | `SET` es lo que habilita `SET ROLE`; `inherit false` evita cargar privilegios sin pedirlos |
| 2 | `revoke insert on asistente.interruptor_autonomia from app_backend` | **Cierra el fail-open.** Conserva `SELECT`: el motor debe poder leer |
| 3 | `grant usage on schema asistente to autonomia_operador` | ACL mínima adicional |
| 3 | `grant select, insert … to autonomia_operador` | Append-only: sin `UPDATE` ni `DELETE` |
| 3 | `create policy tenant_aislado_operador` | Con FORCE RLS, un rol sin política no ve ni escribe nada |
| 4 | `create or replace function asistente.autonomia_detener(uuid,text,text)` | Parada de emergencia, `SECURITY DEFINER`, `search_path = pg_catalog` |
| 4 | `revoke all … from public` + `grant execute … to app_backend, autonomia_operador` | Nadie más la ejecuta |
| 5 | **Bloque de 11 verificaciones** | La migración se niega a quedar a medias |

### Lo que NO hace — no duplica nada de 1710/1715

No crea la tabla, ni sus índices, ni sus constraints, ni la política
`tenant_aislado`, ni la fila semilla. **Medido tras aplicar el lote:**

| | Medido |
|---|---|
| Políticas sobre `interruptor_autonomia` | **2** — `tenant_aislado→{app_backend}`, `tenant_aislado_operador→{autonomia_operador}` |
| Índices | **2** — `…_pkey`, `…_vigente_idx` |
| Funciones `autonomia*` | **1** — `autonomia_detener(uuid, text, text)`, sin sobrecargas |
| Constraints duplicadas por definición | **0** |

Es idempotente: `if not exists`, `or replace`, `drop policy if exists`, y
`revoke` de un privilegio inexistente es un no-op.

## 2. El orden, demostrado

```
1700 reconciliación 1  →  1705 reconciliación 2  →  1710 interruptor
                       →  1715 idempotencia      →  1720 segregación
```

El orden sale del nombre del archivo, no de una selección manual. Y la
dependencia **no se declara: se demuestra**, ejecutando el bloque de
precondición contra estados incompletos:

```
A) sin la tabla (como si 1710 no se hubiera aplicado)
   ERROR: falta asistente.interruptor_autonomia: hay que aplicar antes
          202609151710_interruptor_autonomia.sql

B) con la tabla pero sin FORCE RLS
   ERROR: interruptor_autonomia no tiene RLS + FORCE: segregar sobre una
          tabla abierta daria una falsa sensacion de control
```

1720 **no puede** aplicarse fuera de orden.

## 3. Ejecución del lote en réplica limpia

Réplica restaurada desde **`20260917_141238`** (`restaurar.sh` código 0,
`verificar_restauracion.py` **0 fallas**, scheduler `succeeded`).
Precondiciones exactas: ledger 45 · 35 tablas · 35 políticas · funciones `job*`
md5 `614d3a167d73bac0ca16cf6fc002a19c` · 0 tablas nuevas · 0 rol.

```
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar

[migrar] 5 pendiente(s):
  [ok] 202609151700_scheduler_persistente_reconciliado.sql   (13 ms)
  [ok] 202609151705_scheduler_funciones_reconciliado.sql     (59 ms)
  [ok] 202609151710_interruptor_autonomia.sql                (14 ms)
  [ok] 202609151715_operaciones_externas.sql                 (12 ms)
  [ok] 202609151720_segregacion_operador_autonomia.sql       (16 ms)
[migrar] 5 aplicada(s).

codigo 0    SQL: 114 ms    proceso completo: 0,71 s
```

Sin SQL manual. Todo por el mecanismo versionado.

## 4. Ledger — 45 → 50

| | |
|---|---|
| Filas | **50** |
| Filas históricas | **45**, `diff` vacío contra el respaldo |
| md5 reproducible de las 45 | **`63c7c41844593669a03ca2867a8e4218`** — sin moverse |
| `huecos()` | **vacío** · pendientes 0 · discrepancias 0 · no canónicos 0 |
| Máxima anotada | `202609151720_segregacion_operador_autonomia.sql` |

Las cinco filas nuevas, contra el archivo en disco:

| Archivo | Checksum | ¿= disco? | origen | ms |
|---|---|---|---|---|
| `…1700_scheduler_persistente_reconciliado` | `e7a70f0556d29022…` | **sí** | aplicada | 9 |
| `…1705_scheduler_funciones_reconciliado` | `ca0bf08137214414…` | **sí** | aplicada | 54 |
| `…1710_interruptor_autonomia` | `9c8df21b002826e1…` | **sí** | aplicada | 10 |
| `…1715_operaciones_externas` | `9c2f242d9319664a…` | **sí** | aplicada | 8 |
| `…1720_segregacion_operador_autonomia` | `5699ffcbffb8f742…` | **sí** | aplicada | 12 |

> **Sobre el checksum del ledger.** Se usa el valor reproducible verificado
> entre producción y respaldo — `63c7c418…` sobre
> `archivo|sha256|origen|duro_ms` ordenado. **`58ff01f2…` queda retirado**: no
> es reproducible con ninguna de las 15.330 combinaciones probadas en el paso
> 10.13.

## 5. Objetos y permisos

| Tabla | RLS | FORCE | Dueño | Índices | Constraints | Políticas |
|---|---|---|---|---|---|---|
| `interruptor_autonomia` | **sí** | **sí** | `postgres` | 2 | 4 | 2 |
| `operaciones_externas` | **sí** | **sí** | `postgres` | 2 | 3 | 1 |

### Matriz sobre el interruptor

| Rol | Privilegios |
|---|---|
| **`app_backend`** | **`SELECT`** — y nada más |
| **`autonomia_operador`** | **`INSERT, SELECT`** — append-only |
| `postgres` (dueño) | completo |

### Quién puede `SET ROLE autonomia_operador`

| Rol | hereda USAGE | es MIEMBRO | **puede SET ROLE** |
|---|---|---|---|
| `postgres` | sí | sí | **sí** |
| `app_backend` | no | no | **no** |
| `motor_user`, `crm_migrator`, `asistente_owner`, `service_role` | no | no | **no** |

`autonomia_operador`: **NOLOGIN**, sin super, sin bypassrls, sin createrole.

## 6. Auditoría `SECURITY DEFINER`

| | |
|---|---|
| Función | `asistente.autonomia_detener(uuid, text, text)` — **una sola, sin sobrecargas** |
| Dueño | `postgres` |
| `SECURITY DEFINER` | **sí** |
| `search_path` | **`pg_catalog`** (fijado) |
| ACL | `{postgres=X, app_backend=X, autonomia_operador=X}` — **sin PUBLIC** |
| Funciones que tocan el interruptor | **1** — sólo ésta |
| ¿Acepta el estado por parámetro? | **no** · ¿menciona `'activo'`? **no** |

### El hallazgo que obligó a diseñar la guarda 5.10

La tabla tiene **FORCE RLS**, y con FORCE el dueño **también** queda sujeto a
las políticas. Las políticas son `to app_backend` y `to autonomia_operador`;
ninguna es para el dueño. Entonces la parada sólo funciona si el dueño puede
atravesar RLS.

**Producción `postgres`: `rolsuper = false`, pero `rolbypassrls = true`.**
En la réplica es superusuario — misma conducta, causa distinta. Para no
probarlo por el motivo equivocado, se midió el mecanismo aislado, con control:

```
rol NOSUPERUSER + BYPASSRLS, definer sobre tabla con FORCE RLS y sin politica
  -> la insercion FUNCIONA

el MISMO rol con 'nobypassrls'
  -> ERROR: new row violates row-level security policy for table "t"
```

Por eso la migración exige `rolsuper or rolbypassrls` en el dueño: si no, la
parada de emergencia fallaría **recién al llamarla**.

Y el segundo mecanismo, también bajo el modelo de producción
(`NOSUPERUSER + CREATEROLE`, `session_user` real):

```
session_user=sim_admin
  USAGE (herencia) = false        <- 'inherit false' respetado
  SET   (set role)  = true        <- la concesion tomo efecto
  set role sim_operador -> current_user=sim_operador  session_user=sim_admin
```

## 7. Pruebas de conducta — con `session_user` real, no `postgres`

Rol principal de prueba: **`sim_runtime`**, login sin superusuario y **sin
bypassrls**, con `SET ROLE app_backend`. Es **más estricto** que producción,
donde `session_user` es `postgres` (que sí tiene BYPASSRLS).

```
session_user=sim_runtime (super=False bypassrls=False)   current_user=app_backend
```

| Prueba | Resultado |
|---|---|
| app_backend **puede leer** el estado | `detenido`, actor `migracion` |
| app_backend **no** puede `INSERT 'activo'` | `permission denied for table` |
| app_backend **no** puede `INSERT` (ni `'detenido'`) | `permission denied for table` |
| app_backend **no** puede `UPDATE` | `permission denied for table` |
| app_backend **no** puede `DELETE` | `permission denied for table` |
| app_backend **no** puede `SET ROLE autonomia_operador` | `permission denied to set role` |
| **la parada autorizada SÍ funciona** | `autonomia_detener(...)` → `detenido`, actor `sim_runtime` |
| no hay sobrecarga que acepte el estado | `function … (unknown,unknown,unknown,unknown) does not exist` |
| la parada exige actor y motivo | `hay que decir QUIEN detiene la autonomia` |
| **el operador puede activar** | → `activo` |
| **el operador puede detener** | → `detenido` |
| el operador **tampoco** puede `UPDATE` / `DELETE` | `permission denied` (append-only para todos) |
| el operador **no** puede escribir para otra organización | `new row violates row-level security policy` |

## 8. Estado por tenant — sin configuración artificial

```
Rapilink                       config=1  ->  detenido
Rapilink Telecomunicaciones    config=0  ->  sin_registro (no hay fila)
```

`tenant_config` sigue teniendo **1 fila**: no se creó nada. La organización sin
configuración queda `sin_registro`, que el interruptor trata como **bloqueo**.

## 9. Idempotencia — sin una sola llamada externa

La acción es una función **local** que sólo anota que la llamaron.

| Caso | Resultado | Llamadas |
|---|---|---|
| 1 · primera vez | `ejecutar` | 1 |
| 2 · misma clave + mismos argumentos | `repetida` | **0** |
| 3 · misma clave con otro hash de argumentos | **`rechazada`** | **0** |
| 4 · otro origen | `ejecutar` | 1 |
| 5 · dos hilos, misma clave | una sola ejecutada (`en_curso` / `ejecutar`) | 1 |

**3 llamadas simuladas, todas locales. Cero a WispHub, SmartOLT o cualquier
servicio externo.** Además, `tests/test_idempotencia_externa.py` pasa completo.

> **Corrección de método.** El caso 3 estaba mal planteado por mí: la clave es
> `origen|herramienta|hash(argumentos)`, así que cambiar los argumentos produce
> **otra** clave — y eso es correcto, no un agujero. La colisión sólo existe al
> nivel de la primitiva `reclamar_operacion_externa`, que es donde vive la
> defensa y donde ahora se prueba.

## 10. Scheduler

`job_claim → job_contexto → job_heartbeat → job_finalize` = **`succeeded`**,
con `capability` de 64 hex, `config_hash` coincidente y 3 eventos. Sobre la
réplica migrada **y** sobre la restaurada.

> `verificar_restauracion.py` reporta 2 «fallas»: «tablas en asistente» y
> «políticas en asistente». **Son las diferencias esperadas** — 35→**37**
> tablas (+2) y 35→**38** políticas (+3) — porque compara contra la línea base
> de producción *previa* a estas migraciones. No es un defecto.

## 11. Locks

`ACCESS EXCLUSIVE` retenido sobre `asistente.tenant_config`, `lock_timeout=10s`:

```
[ok]    202609151700_…persistente   (14 ms)
[FALLA] 202609151705_…funciones: LockNotAvailable: canceling statement due to lock timeout
La migracion se deshizo entera y NO quedo anotada. Las anteriores si.
codigo 1     duracion: ~11 s
```

| Tras el fallo | |
|---|---|
| Ledger | 45 → **46** (sólo la que aplicó) |
| La que falló, ¿anotada? | **no** |
| `interruptor_autonomia` / `operaciones_externas` | **no existen** |
| Rol `autonomia_operador` / función de parada | **no existen** |
| Migraciones 3, 4 y 5 | **nunca corrieron** |

**Liberado el bloqueo, el reintento recupera:** 4 aplicadas, código 0, ledger
50, en 0,73 s. Falla limpia y atómica; nada a medias.

## 12. Respaldo y restauración del resultado

Respaldo de la réplica migrada (3 artefactos, sello `20260917_150833`,
8.913.437 + 7.481 + 3.751 bytes, código 0) → restaurado en un contenedor
virgen → **27 de 27 comprobaciones idénticas**:

ledger 50 y su md5 · última anotada · rol operador y sus 4 atributos ·
`postgres` puede `SET ROLE` · grants de `app_backend` (**`SELECT`**) y del
operador (`INSERT,SELECT`) · grants sobre `operaciones_externas` · RLS+FORCE de
ambas tablas · las 2 políticas del interruptor · 38 políticas · md5 de las 10
funciones `job*` · **cuerpo y firma de `autonomia_detener`** · `SECURITY
DEFINER` + `search_path` + dueño · ACL de `EXECUTE` · semilla `detenido` ·
**0 filas `activo`** · actor `migracion` · clave primaria de idempotencia ·
37 tablas · ownership · `public` 135/`crm_owner`.

Y sobre la restaurada se repitieron **todas** las pruebas de conducta del §7:
**0 en rojo**. La segregación sobrevive al ciclo completo.

## 13. El bloque de verificación funciona — probado desarmándolo

No basta con que exista. Dos evidencias de que **actúa**:

1. **Fallo real durante el desarrollo.** La primera corrida abortó en la
   comprobación de firma y **deshizo el archivo entero sin anotarlo**:
   ```
   [FALLA] 202609151720_…: RaiseException: asistente.autonomia_detener no tiene la firma (uuid, text, text)
   La migracion se deshizo entera y NO quedo anotada. Las anteriores si.
   ```
   Causa: `pg_get_function_identity_arguments` **sí incluye los nombres** de los
   parámetros (`p_org uuid, …`), al contrario de lo que yo había supuesto.
   Corregido comparando los **tipos**, que es el invariante que importa.

2. **Desarme deliberado.** Devolviendo `INSERT` a `app_backend` y reejecutando
   el bloque:
   ```
   ERROR: app_backend quedo con INSERT,SELECT sobre interruptor_autonomia; debe ser solo SELECT
   ```

## 14. Diferencias respecto al Paso 10.13A

| | 10.13A | 10.13B |
|---|---|---|
| Migraciones | 4 | **5** |
| Segregación del operador | **SQL manual de 10.11**, fuera del ledger | **migración versionada** `202609151720`, en el ledger |
| Ledger | 45 → 49 | 45 → **50** |
| ¿El estado validado correspondía a lo autorizado? | **no** — incluía SQL no versionado | **sí** — todo por el mecanismo canónico |
| Checksum del ledger | `58ff01f2…` (no reproducible) | **`63c7c418…`** (reproducible, verificado contra el respaldo) |
| Privilegios del dueño de la función | no analizado | **medido con control**: `NOSUPERUSER + BYPASSRLS` y guarda 5.10 |
| Verificación dentro de la migración | ninguna | **11 comprobaciones, fail-closed** |
| SQL manual en producción | requerido | **ninguno** |

## 15. Riesgos

1. **`public.organization` se bloquea para escrituras** (`ShareRowExclusive`)
   durante 1710 y 1715. Es tabla del CRM.
2. **`tenant_config(_historial)` en `ACCESS EXCLUSIVE`** durante 1705 (~60 ms).
   Las lee el motor.
3. **`Rapilink Telecomunicaciones` quedará `sin_registro`** → bloquea. Correcto
   y deliberado; no se crea configuración artificial.
4. **`grant … with inherit false, set true` bajo supautils.** En producción,
   supautils auto-concede cada rol nuevo a `postgres` con `SET FALSE`; la
   concesión explícita debe prevalecer. **Esto no se puede reproducir en la
   réplica** (la imagen no tiene supautils). Mitigado: la comprobación 5.2
   aborta la migración entera si `pg_has_role('postgres','autonomia_operador','SET')`
   no queda en `true`. El riesgo es que la migración **falle**, no que deje un
   estado inseguro.
5. **El código de `db.py` (10.12) sigue sin desplegar.** Tras esta migración,
   `cli/autonomia.py` sólo podrá mover el interruptor cuando ese código salga.
   Este paso **no despliega código**, y la autonomía queda **DETENIDA**.
6. **La réplica corre con `postgres` superusuario** y no se puede degradar (es
   el superusuario de arranque). Cubierto midiendo aparte, con control, los dos
   mecanismos que en producción dependen de `NOSUPERUSER + BYPASSRLS` (§6).

## 16. Rollback

- **Nivel 1 · durante la corrida:** automático y medido (§11). El archivo que
  falla se deshace entero y no queda anotado; los anteriores quedan aplicados.
  Se corrige la causa y se reintenta.
- **Nivel 2 · única salida real tras el COMMIT:** restaurar
  **`20260917_141238`**. Vuelve exacto a 45 filas / `63c7c418…` / 0 tablas
  nuevas.
- **Lo que NO es rollback:** un `drop` manual. Deja el ledger diciendo
  «aplicada» con 0 objetos y el CLI reportando 0 pendientes — divergencia, no
  reversión (medido en 10.13A §10). **No se hará.**

---

# GO / NO-GO para producción

## **GO**, condicionado a autorización nueva y explícita.

| Criterio | Resultado |
|---|---|
| Las cinco pasan juntas por el mecanismo canónico | **sí** — código 0, 114 ms |
| Orden demostrado (no declarado) | **sí** — 1720 se niega sin 1710 |
| Sin duplicar objetos de 1710/1715 | **sí** — 2 políticas, 2 índices, 1 función, 0 constraints duplicadas |
| Ledger 45 → 50 | **sí** |
| 45 históricas byte-identical | **sí** — `diff` vacío, `63c7c418…` |
| 5 checksums = archivos en disco | **5 de 5** |
| `huecos()` vacío | **sí** |
| `autonomia_operador` NOLOGIN | **sí**, sin super/bypassrls/createrole |
| app_backend: no activa, no INSERT, no UPDATE, no DELETE, no SET ROLE | **5 de 5 cerradas** |
| Operador puede activar y detener | **sí** |
| Parada runtime autorizada funciona | **sí** |
| `session_user` real (no `postgres`) | **sí** — `sim_runtime`, sin bypassrls |
| `SECURITY DEFINER` auditado | **sí** — dueño, `search_path`, EXECUTE, sin PUBLIC, sin sobrecargas |
| Imposible saltarse la segregación por función | **sí** — una sola función, estado fijo en el cuerpo |
| Tenant con config → DETENIDO; sin config → `sin_registro` | **sí**, sin configuración artificial |
| Idempotencia | **5/5**, 3 llamadas locales, **0 externas** |
| Scheduler | **`succeeded`** en migrada y restaurada |
| Locks | falla limpia a ~11 s, nada parcial, reintento recupera |
| Backup/restore del resultado | **27/27 idénticos** + conducta 0 en rojo |
| Producción | **intacta** |

**Duración medida:** 114 ms de SQL (13+59+14+12+16), **0,71 s** de proceso.
Con bloqueo de por medio: ~11 s antes de abortar.

**Ventana:** fuera del horario de atención, con el motor sin tráfico, y con las
8 tablas libres (`tenant_config`, `tenant_config_historial`, las 5 `job_*` y
`public.organization`).

**Comando exacto:**

```bash
cd <repo>
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar
```

**Criterio de abortar:** cualquier preflight en rojo; `LockNotAvailable` (no
forzar, no matar sesiones, reprogramar); cualquier `raise` del bloque de
verificación; cualquier fallo posterior → restaurar, no corregir a mano.

---

## Estado al cerrar

Producción: ledger **45 filas** idénticas al respaldo (`63c7c418…`), **0**
tablas nuevas, **0** rol `autonomia_operador`, **0** función de parada.
`DBUSER` sin cambios. **AUTONOMÍA = DETENIDA / NO OPERATIVA.**
`interruptor.py`, `idempotencia.py` y todo el código de autonomía: **sin
desplegar**. M02, M03, M09, M10, WispHub, SmartOLT, Celery, motor y scheduler:
**sin tocar**. Réplicas eliminadas; respaldo `20260917_141238` conservado.

**Me detengo. La autorización anterior no cubre este lote de cinco: hace falta
una nueva, explícita.**
