# Paso 10.13 — Ejecución en producción del lote de cinco migraciones

**Fecha:** 17/09/2026
**Inicio:** 15:25:41.206 · **Fin:** 15:25:47.195 · **Duración:** **5,99 s**
(preflight completo: 15:19 – 15:25)

## Resultado: **4 de 5 aplicadas. La quinta falló y se deshizo entera.**

```
[migrar] 5 pendiente(s):
  [ok]    202609151700_scheduler_persistente_reconciliado.sql  (1127 ms)
  [ok]    202609151705_scheduler_funciones_reconciliado.sql     (560 ms)
  [ok]    202609151710_interruptor_autonomia.sql                (576 ms)
  [ok]    202609151715_operaciones_externas.sql                 (479 ms)
  [FALLA] 202609151720_segregacion_operador_autonomia.sql:
          InsufficientPrivilege: permission denied to alter role
  La migracion se deshizo entera y NO quedo anotada. Las anteriores si.

codigo de salida: 1
```

**Me detuve ahí**, como exige la condición 8. No se intentó corregir en
producción, no se ejecutó SQL manual, no se tocó ningún permiso a mano.

> ## ⚠️ El interruptor quedó instalado en su configuración INSEGURA
>
> Las migraciones 3 y 4 crearon el kill switch, pero la 5 —la que retira el
> `INSERT` de `app_backend`— se deshizo. Ahora mismo:
>
> ```
> app_backend   INSERT,SELECT   sobre asistente.interruptor_autonomia
> ```
>
> Es decir: **el runtime podría insertar una fila `'activo'` y activarse la
> autonomía a sí mismo.** Es exactamente el fail-open que la migración 5 cierra.
>
> **Hoy es inerte**: ningún código desplegado lee esa tabla (`interruptor.py` no
> está desplegado), la autonomía no está operativa y hay **0 filas `activo`**.
> Pero el estado no es el que se buscaba y no debería quedarse así.

---

## 1. La causa, medida — no deducida

El fallo lo provoca **una sola palabra**, y no está en el SQL de 10.11: está en
una línea defensiva que yo añadí al empaquetar la migración en el paso 10.13B.

```sql
alter role autonomia_operador
  nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
```

Probando **cada atributo por separado** en producción, dentro de una
transacción deshecha:

| Atributo | En producción |
|---|---|
| `nologin` | **permitido** |
| **`nosuperuser`** | **`permission denied to alter role`** |
| `nocreatedb` | permitido |
| `nocreaterole` | permitido |
| `noreplication` | permitido |
| `nobypassrls` | permitido |
| la línea completa | **rechazada** |
| `nologin nocreatedb nocreaterole` | permitido |

**Por qué.** Producción corre como `postgres` con
`super=False, createrole=True, bypassrls=True, replication=True, createdb=True`.
Un rol que no es superusuario **no puede tocar el atributo SUPERUSER de nadie —
ni siquiera para quitarlo**. En la réplica pasó porque allí `postgres` es el
superusuario de arranque.

**Y la ironía:** `nosuperuser` era redundante. Medido sobre un rol recién creado
en producción, sin ningún `ALTER`:

```
login=False super=False createdb=False createrole=False replication=False bypassrls=False
```

Un rol nuevo ya nace con todo en falso. La única palabra que no puede ejecutarse
en producción es también la única que no aportaba nada.

**Esto es un fallo mío**, y del tipo que este proyecto ya tiene documentado: la
réplica no reproduce el modelo de privilegios de producción. Lo señalé como
riesgo nº 6 en el informe 10.13B —«la réplica corre con `postgres` superusuario
y no se puede degradar»— y cubrí con experimentos aislados los dos mecanismos
que creí expuestos (BYPASSRLS y la membresía SET). **No cubrí el `ALTER ROLE`**,
que era el tercero.

## 2. Condiciones previas — todas cumplidas antes de ejecutar

### Condición 1 · Respaldo `20260917_141238`

| Dimensión | Resultado |
|---|---|
| Existencia | 3 artefactos |
| SHA-256 | **3 de 3 coinciden** con el Paso 10.13 (`0ab7ebf5…`, `94e9b396…`, `97d31850…`) |
| Restaurabilidad | `restaurar.sh` **código 0**; `verificar_restauracion.py` **0 fallas**; scheduler `succeeded` |
| Correspondencia con producción | ledger del respaldo restaurado **idéntico** al de producción (`diff` vacío, `63c7c418…` ambos lados) |

### Condición 2 y 3 · Preflight del runbook — **0 en rojo**

| Comprobación | Medido |
|---|---|
| `session_user` / `current_user` | `postgres` / `postgres` |
| Servidor | PostgreSQL **17.6** |
| Ledger | **45 filas** · md5 reproducible **`63c7c41844593669a03ca2867a8e4218`** |
| Bloqueos pesados sobre `asistente` y `public.organization` | **0** |
| Transacciones abiertas | **0** |
| `job_catalogo` | **0** |
| Sesiones de cliente **activas** | **0** |
| Tablas / políticas en `asistente` | **35 / 35** |
| Funciones `job*` · md5 | **10** · `614d3a167d73bac0ca16cf6fc002a19c` |
| `public` | **135** tablas, **135** de `crm_owner`, 132 políticas |
| `interruptor_autonomia` / `operaciones_externas` | **0 / 0** |
| Rol `autonomia_operador` / función de parada | **0 / 0** |

> El criterio `58ff01f2…` queda **retirado**, como usted indicó. Se usa
> únicamente el reproducible `63c7c418…`, verificado entre producción y respaldo.

### Condición 4 · SUPAUTILS — **demostrada en producción antes de aplicar**

Sonda dentro de una transacción deshecha. No se modificó ningún permiso para
hacerla pasar.

```
A. postgres: super=False bypassrls=True createrole=True inherit=True login=True

B. que hace supautils AUTOMATICAMENTE al crear un rol:
     otorgante=supabase_admin  miembro=postgres  admin=True inherit=False set=False
     SET antes de la concesion explicita: False        <- el riesgo era real

C. tras la concesion exacta de la migracion:
     otorgante=postgres        admin=False inherit=False set=True
     otorgante=supabase_admin  admin=True  inherit=False set=False
     USAGE=False  MEMBER=True  SET=True
  [ok] PRECONDICION 5.2: pg_has_role(postgres, rol, 'SET') = true

D. SET ROLE de verdad: current_user=probe...  session_user=postgres   [ok]

E. FORCE RLS contra una funcion SECURITY DEFINER de postgres:
     llamada como current_user=app_backend -> filas escritas=1        [ok]

F. el mismo rol sin la funcion: permission denied for table t         [ok]

G. tras el rollback: rol de sonda 0, esquema de sonda 0, autonomia_operador 0
```

**La condición supautils se cumplía.** `pg_has_role(...,'SET')` daba `true` en
producción. Lo que falló fue otra línea, cinco sentencias antes.

### Condición 5 · Checksum de la migración 5

```
archivo : 202609151720_segregacion_operador_autonomia.sql
bytes   : 15674
sha256  : 5699ffcbffb8f7420ff7681038f41bcf2cecadcb302518a1f4515efbc26bbb0b
validado: 5699ffcbffb8f7420ff7681038f41bcf2cecadcb302518a1f4515efbc26bbb0b
COINCIDE: True
```

Y `--estado` mostró **5 pendientes, exactamente los cinco autorizados**,
`con checksum distinto: 0`, `no canonicos: 0`.

## 3. Comandos ejecutados

```bash
cd C:/Users/Usuario/crm-agentico
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar
```

`lock_timeout` **sólo para la sesión de migración**, vía `PGOPTIONS`. No se usó
`ALTER SYSTEM` ni `ALTER DATABASE`. No se usó `--adoptar`, no se renombró nada,
no se modificó ningún checksum, no se ejecutó SQL manual ninguno.

## 4. Rollback transaccional — confirmado

La migración 5 **no dejó nada**:

| | |
|---|---|
| Rol `autonomia_operador` | **0** — deshecho |
| Función `asistente.autonomia_detener` | **0** — deshecha |
| Política `tenant_aislado_operador` | **0** — deshecha |
| ¿Quedó anotada en el ledger? | **no** |

## 5. Ledger — 45 → **49**

| | |
|---|---|
| Filas | **49** (no 50: la quinta no entró) |
| 45 históricas | **idénticas**, md5 `63c7c41844593669a03ca2867a8e4218` |
| `huecos()` | **vacío** |
| pendientes / discrepancias / no canónicos | **1 / 0 / 0** |
| Máxima anotada | `202609151715_operaciones_externas.sql` |

| Archivo | Checksum | = disco | origen | ms |
|---|---|---|---|---|
| `…1700_scheduler_persistente_reconciliado` | `e7a70f0556d29022…` | **sí** | aplicada | 896 |
| `…1705_scheduler_funciones_reconciliado` | `ca0bf08137214414…` | **sí** | aplicada | 375 |
| `…1710_interruptor_autonomia` | `9c8df21b002826e1…` | **sí** | aplicada | 351 |
| `…1715_operaciones_externas` | `9c2f242d9319664a…` | **sí** | aplicada | 286 |

> **El ledger quedó recuperable.** `202609151720` sigue pendiente y ordena
> **después** de la máxima anotada (1715), así que **no crea hueco**: una
> versión corregida se aplica con `--aplicar` normal, sin `--adoptar`.

## 6. Objetos creados por las migraciones 1–4

| Tabla | RLS | FORCE | Dueño | Índices | Políticas |
|---|---|---|---|---|---|
| `asistente.interruptor_autonomia` | **sí** | **sí** | `postgres` | 2 | 1 |
| `asistente.operaciones_externas` | **sí** | **sí** | `postgres` | 2 | 1 |

`asistente`: 35 → **37** tablas, 35 → **37** políticas.
Funciones `job*`: **10**, md5 `614d3a167d73bac0ca16cf6fc002a19c` — **sin moverse**.
`public`: **135** tablas, sin cambios.

### Kill switch

| | |
|---|---|
| Tabla / RLS / FORCE | existe · **sí** · **sí** |
| Políticas | **1** (`tenant_aislado → {app_backend}`) — falta la del operador |
| `Rapilink` (con `tenant_config`) | **`detenido`**, actor `migracion` |
| `Rapilink Telecomunicaciones` (sin `tenant_config`) | **`sin_registro`** → bloquea |
| Filas `'activo'` | **0** |

### Segregación — **NO instalada**

| | Estado |
|---|---|
| `app_backend` sobre el interruptor | **`INSERT, SELECT`** ← debía quedar sólo `SELECT` |
| Rol `autonomia_operador` | **no existe** |
| Función de parada | **no existe** |
| Política del operador | **no existe** |

## 7. Validaciones que NO se pudieron ejecutar

Las condiciones 16 a 20 dependen de objetos que la migración 5 no llegó a
crear. **No se ejecutaron, y no se simularon:**

- app_backend no puede INSERT ACTIVO / UPDATE / DELETE / SET ROLE operador
- operador NOLOGIN, activar, detener, aislamiento por organización
- parada runtime por la función autorizada
- que la parada no permita DETENIDO → ACTIVO

Las pruebas de idempotencia (condición 20) tampoco se ejecutaron contra
producción: se decidió no escribir filas de prueba en `operaciones_externas` de
producción estando el lote incompleto. Su validación en réplica está en el paso
10.13B (5/5, 3 llamadas locales, **0 externas**).

## 8. Condiciones 21 a 24 — verificadas

| | Resultado |
|---|---|
| **Scheduler** (`job_claim → … → job_finalize`) | **`succeeded`**, 0 fallas |
| `public.organization` disponible | **sí** — 0 bloqueos |
| `tenant_config` disponible | **sí** — 0 bloqueos, 1 fila |
| Locks remanentes | **0** |
| Transacciones abiertas | **0** |
| CRM `https://crm.rapilinksas.co/` | **HTTP 401** (igual que antes) |
| Frontend `https://agent.rapilinksas.co/login` | **HTTP 200** |
| Datos | `messages` 2594 · `conversations` 302 · `tool_calls` 1190 · `public.case` 191 — **sin cambios** |
| **Segundo tenant** | **`sin_registro` → bloqueado. NO se creó `tenant_config` artificial.** |

## 9. Condición 25 · Respaldo posterior — creado y verificado

El respaldo anterior ya **no** corresponde a producción (cambió de 45 a 49
filas), así que se tomó uno nuevo:

| | |
|---|---|
| Sello | **`20260917_152749`** |
| Ubicación | `C:\Users\Usuario\respaldo_p1013_post\` |
| Artefactos | `datos.dump` 8.911.699 B · `roles.sql` 9.936 B · `entorno.sql` 4.525 B · **código 0** |

**Validación de restore, dentro de la ventana:** restaurado en contenedor
virgen, código 0 → ledger **49** · 37 tablas · 37 políticas · interruptor
**`detenido`** · **0 filas `activo`** · rol operador ausente · `app_backend`
`INSERT,SELECT` · **scheduler `succeeded`, 0 fallas**.

**No se hizo ningún `DROP` manual.**

## 10. Evidencia conservada

| Archivo | Qué es |
|---|---|
| `scratchpad/p1013_prod_out.txt` / `_err.txt` | stdout y stderr del `--aplicar` |
| `scratchpad/p1013_prod_tiempos.txt` | inicio, fin y código de salida |
| `scratchpad/p1013_preflight_final.out` | preflight completo |
| `scratchpad/p1013_supautils.py` | la sonda de la condición 4 |
| `scratchpad/p1013_diag_alterrole.py` | el diagnóstico atributo por atributo |
| `C:\Users\Usuario\respaldo_p1013\` | respaldo **previo** `20260917_141238` |
| `C:\Users\Usuario\respaldo_p1013_post\` | respaldo **posterior** `20260917_152749` |

## 11. Estado final

| | |
|---|---|
| Migraciones aplicadas | **4 de 5** |
| Ledger | **49 filas**, coherente, `huecos()` **vacío** |
| Kill switch | **instalado**, `detenido`, 0 `activo` |
| **Segregación** | **NO instalada** — `app_backend` conserva `INSERT` |
| Rol `autonomia_operador` | **no existe** |
| **AUTONOMÍA** | **DETENIDA / NO OPERATIVA** |
| Código de autonomía desplegado | **ninguno** |
| `DBUSER` | **sin cambios** |
| M02 / M03 / M09 / M10 | **intactos** |
| WispHub / SmartOLT / Celery / motor / scheduler | **intactos** |
| Llamadas a servicios externos | **ninguna** |

## 12. Rollback disponible

- **Durante la ejecución:** ya ocurrió y está confirmado — la migración 5 se
  deshizo entera y no quedó anotada.
- **Para volver al estado previo al lote:** restaurar **`20260917_141238`**
  (verificado hoy: código 0, 0 fallas, ledger idéntico a producción de entonces).
- **Para volver al estado actual:** restaurar **`20260917_152749`** (verificado).
- **NO se hará `DROP` manual** — deja el ledger diciendo «aplicada» con 0 objetos
  y el CLI reportando 0 pendientes.

---

## Lo que hace falta decidir

La corrección es **quitar una palabra**: `nosuperuser` de la línea `alter role`
de `202609151720`. Es redundante —un rol nuevo ya nace `NOSUPERUSER`— y es la
única que producción rechaza.

Eso **cambia el checksum** del archivo, que usted autorizó explícitamente y
ordenó no modificar. Por eso **no lo he tocado**: el archivo sigue en disco con
`5699ffcbffb8f742…` intacto.

Lo que propongo para un paso 10.13C, si lo autoriza:

1. Quitar `nosuperuser` (y dejar el resto de la línea, que sí es ejecutable).
2. Añadir a la verificación una comprobación explícita de que el rol quedó
   `NOSUPERUSER`, en vez de intentar forzarlo — comprobar en lugar de imponer.
3. Revalidar en réplica restaurada del respaldo **`20260917_152749`**, que es el
   estado real de producción hoy: con las cuatro ya aplicadas, la quinta se
   aplica sola.
4. Nuevo checksum y nueva autorización explícita.

**Mientras tanto, el riesgo vivo** es que `app_backend` tiene `INSERT` sobre el
interruptor. Es inerte hoy porque ningún código desplegado lo lee — y refuerza
que **no debe desplegarse `interruptor.py` hasta cerrar la segregación**.

**Me detengo aquí.** No continúo automáticamente. La autorización del Paso 10.13
queda consumida.
