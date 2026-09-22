# Paso 10.13D — Segregación del operador, aplicada en producción

**Fecha:** 17/09/2026
**Inicio:** 16:34:17.779 · **Fin:** 16:34:21.134 · **Duración:** **3,36 s**
(617 ms de SQL · preflight 16:28 – 16:34 · validación posterior 16:34 – 16:38)

## Resultado: **APLICADA. Ledger 49 → 50. `huecos()` vacío.**

```
[migrar] 1 pendiente(s):
  [ok] 202609151720_segregacion_operador_autonomia.sql  (617 ms)
[migrar] 1 aplicada(s).

codigo de salida: 0
```

**El fail-open quedó cerrado.** `app_backend` pasó de `INSERT,SELECT` a
**`SELECT`** sobre `asistente.interruptor_autonomia`: el runtime ya no puede
activarse la autonomía a sí mismo.

**Autonomía: DETENIDA.** El interruptor sigue con **1 sola fila** —la semilla—,
estado **`detenido`**, y **0 filas `activo`**.

---

## 1. Condiciones previas — todas cumplidas

### Condición 1 · Estado de producción

| Comprobación | Medido | Exigido |
|---|---|---|
| `session_user` / `current_user` | `postgres` / `postgres` | ok |
| Servidor | PostgreSQL **17.6** | ok |
| Ledger | **49** | 49 |
| `interruptor_autonomia` / `operaciones_externas` | **existen** | existen |
| Rol `autonomia_operador` | **0** | ausente |
| Función `autonomia_detener` | **0** | ausente |
| Política `tenant_aislado_operador` | **0** | ausente |
| `app_backend` sobre el interruptor | **`INSERT,SELECT`** | el fail-open sin cerrar |
| Bloqueos pesados | **0** | 0 |
| Transacciones abiertas | **0** | 0 |
| Sesiones de cliente activas | **0** | 0 |
| `--estado` | **1 pendiente**, `checksum distinto: 0`, `no canonicos: 0` | ok |

md5 reproducible del ledger de 49 filas: **`d0d44a4f48c0895b6343f82c4c9b8629`**

### Condición 2 · Respaldo vigente `20260917_152749`

| Artefacto | Tamaño | SHA-256 |
|---|---|---|
| `…_datos.dump` | 8.911.699 B | `0d6b6b908ddfa3777af873d95a7493a4d6364b1eba413081…` |
| `…_roles.sql` | 9.936 B | `4434984ae14c0c1e29446caba692fc70c76ca6636bb80f45…` |
| `…_entorno.sql` | 4.525 B | `d0007d874b80d0f09390df643223439e3c299800cc2920f7…` |

**Restaurado, no sólo comprobado:** `restaurar.sh` código **0**,
`verificar_restauracion.py` **0 fallas**, scheduler `succeeded`, ledger 49.
El respaldo anterior `20260917_141238` **no** se usó como punto de retorno.

### Condición 3 · Precondición supautils, medida otra vez en producción

Sonda dentro de una transacción deshecha; no modificó ningún permiso.

```
A. postgres: super=False  bypassrls=True  createrole=True  login=True

B. supautils AUTOMATICAMENTE al crear un rol:
     supabase_admin -> postgres   admin=True inherit=False  set=False
     SET antes de la concesion explicita: False

C. tras la concesion de la migracion:
     postgres       -> postgres   admin=False inherit=False set=True
     supabase_admin -> postgres   admin=True  inherit=False set=False
     USAGE=False   MEMBER=True   SET=True          <- precondicion 5.2 [ok]

D. SET ROLE funciona de verdad                                      [ok]
E. funcion SECURITY DEFINER de postgres ATRAVIESA force rls         [ok]
F. app_backend sin la funcion: permission denied                    [ok]
G. la sonda no dejo rastro: 0 roles, 0 esquemas                     [ok]
```

### Condición 4 · La migración no impone `NOSUPERUSER`

```
toda sentencia 'alter role'  ->  linea 88:  alter role autonomia_operador
                                 linea 89:    nologin nocreatedb nocreaterole
                                              noreplication nobypassrls;
'nosuperuser' en el archivo  ->  linea 78, dentro de un COMENTARIO. Nada mas.
'rolsuper' se COMPRUEBA en   ->  lineas 94, 232 y 335
```

### Condición 5 · Checksum y `lock_timeout`

```
sha256     : 3ab03f9e8046e1accf60fc69833de62acd5b2bc3b4aa54bf27db8b597e3879f9
autorizado : 3ab03f9e8046e1accf60fc69833de62acd5b2bc3b4aa54bf27db8b597e3879f9
COINCIDE   : True
```

`PGOPTIONS="-c lock_timeout=10s"` — **sólo para la sesión de migración**. Sin
`ALTER SYSTEM`, sin `ALTER DATABASE`.

## 2. Comando ejecutado

```bash
cd C:/Users/Usuario/crm-agentico
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar
```

Sin `--adoptar`, sin SQL manual, sin renombrar, sin tocar el archivo ni su
checksum. **Sólo corrió la 1720**: las 1700/1705/1710/1715 no se reaplicaron.

## 3. Puntos 9, 10 y 11 — ledger

| | |
|---|---|
| Ledger | **50** |
| Las 49 previas | **idénticas** — md5 `d0d44a4f48c0895b6343f82c4c9b8629` |
| Fila nueva | `202609151720…` · **`3ab03f9e8046e1ac…`** · `origen=aplicada` · **383 ms** |
| `huecos()` | **vacío** |
| pendientes / discrepancias / no canónicos | **0 / 0 / 0** |

## 4. Punto 12 — el rol `autonomia_operador`

| Atributo | Medido |
|---|---|
| existe | **sí** |
| `rolcanlogin` | **False** — NOLOGIN |
| **`rolsuper`** | **False** — NOSUPERUSER, *verificado, no impuesto* |
| `rolcreatedb` | **False** |
| `rolcreaterole` | **False** |
| `rolreplication` | **False** |
| `rolbypassrls` | **False** |
| `rolinherit` | True — atributo propio; el rol no es miembro de nada |

### Membresías reales en producción

```
postgres        -> postgres   admin=False inherit=False  set=True    <- la migracion
supabase_admin  -> postgres   admin=True  inherit=False  set=False   <- supautils
```

| ¿Quién puede `SET ROLE autonomia_operador`? | |
|---|---|
| `postgres` | **sí** |
| `motor_user` | **no** |
| `crm_migrator` | **no** |
| `app_backend` | **no** |

## 5. Puntos 13, 14 y 15 — segregación con `session_user` real

> **Sin crear ningún rol.** El sujeto de prueba es **`motor_user`**, rol de
> login que ya existía en producción. No hubo DDL fuera de la migración.
>
> **Ninguna prueba dejó escritura**: todo lo que escribe corrió dentro de una
> transacción que termina en `ROLLBACK`. El permiso y la RLS se evalúan al
> ejecutar la sentencia, no al confirmarla.

```
session_user=motor_user   current_user=app_backend   (super=False bypassrls=False)
```

| Prueba | Resultado |
|---|---|
| `SELECT` | **permitido** — `detenido`, actor `migracion` |
| `INSERT 'activo'` | **`permission denied for table interruptor_autonomia`** |
| `INSERT` arbitrario | **`permission denied for table`** |
| `UPDATE` | **`permission denied for table`** |
| `DELETE` | **`permission denied for table`** |
| `SET ROLE autonomia_operador` | **`permission denied to set role`** |

### Punto 15 · la parada

| | |
|---|---|
| `app_backend` detiene por `autonomia_detener(...)` | **funciona** → `detenido` |
| Pedir `'activo'` por esa función | **imposible** — `function asistente.autonomia_detener(unknown,unknown,unknown,unknown) does not exist` |

### El operador

`session_user=postgres` + `SET ROLE autonomia_operador` — **es la vía de diseño**:
`postgres` es el único con la membresía, y es lo que hace `db.sesion()`.

| Prueba | Resultado |
|---|---|
| ACTIVAR | **permitido** → `activo` *(revertido)* |
| DETENER | **permitido** → `detenido` *(revertido)* |
| `UPDATE` | **denegado** — append-only también para el operador |
| `DELETE` | **denegado** |

## 6. Puntos 16 y 17 — RLS y aislamiento

| | |
|---|---|
| `interruptor_autonomia` | RLS **sí** · FORCE **sí** · dueño `postgres` |
| `operaciones_externas` | RLS **sí** · FORCE **sí** · dueño `postgres` |
| Políticas del interruptor | **2** — `tenant_aislado→{app_backend}` · `tenant_aislado_operador→{autonomia_operador}` |
| `EXECUTE` sobre la parada | `{postgres=X, app_backend=X, autonomia_operador=X}` — **sin PUBLIC** |
| `SECURITY DEFINER` + `search_path` | **sí** · `{search_path=pg_catalog}` · dueño `postgres` |
| Operador escribiendo para otra organización | **`new row violates row-level security policy`** |
| Operador leyendo otra organización | **0 filas** |

## 7. Punto 18 — idempotencia

Ejecutada **sobre la copia restaurada del respaldo posterior** —un duplicado
exacto de producción— para no dejar filas de prueba en la tabla real.
`asistente.operaciones_externas` de producción sigue en **0 filas**.

| Caso | Resultado | Llamadas |
|---|---|---|
| Primera vez | `ejecutar` | 1 |
| Repetida | `repetida` | **0** |
| Colisión de clave en la primitiva | **`rechazada`** | **0** |
| Otro origen | `ejecutar` | 1 |
| Concurrencia (2 hilos) | una sola ejecutada | 1 |

**3 llamadas simuladas, todas locales. Cero a WispHub, SmartOLT o cualquier
servicio externo.**

## 8. Punto 19 — scheduler

**En producción**, con el flujo completo dentro de una transacción revertida:

| | |
|---|---|
| `job_claim()` | **reclama turno** — `run_id=64cfbb7a…`, intento #1 |
| `capability` | **64 hex** (`gen_random_bytes` resolvió) |
| `config_hash` | **64 hex** (`digest` sha256 resolvió), coincide con el contexto |
| `job_contexto()` / `job_heartbeat()` / `job_finalize()` | **ok** |
| Estado final de `job_run` | **`succeeded`** |
| `job_run_event` | **3 eventos** |

Todo revertido: las tablas `job_*` de producción quedan como estaban.
Repetido sobre la copia restaurada: **`succeeded`, 0 fallas**.

## 9. Punto 20 — estado operativo

| | |
|---|---|
| Bloqueos pesados | **0** |
| Transacciones abiertas | **0** |
| `https://crm.rapilinksas.co/` | **HTTP 401** (igual que antes) |
| `https://agent.rapilinksas.co/login` | **HTTP 200** |
| `asistente.messages` | 2594 — sin cambios |
| `asistente.conversations` | 302 — sin cambios |
| `asistente.tool_calls` | 1190 — sin cambios |
| `asistente.tenant_config` | **1** — sin alteraciones |
| `public.organization` | **2** — sin alteraciones |
| `interruptor_autonomia` | **1 fila** (la semilla) · **0 `activo`** |
| `operaciones_externas` | **0 filas** |

> `public.case` pasó de 191 a 193 durante la ventana. Es actividad normal del
> CRM, que está en producción y atendiendo; ninguna migración toca esa tabla.

### Segundo tenant

```
Rapilink                      tenant_config=1  ->  detenido
Rapilink Telecomunicaciones   tenant_config=0  ->  sin_registro
```

**No se creó `tenant_config` artificial.** La segunda organización queda
`sin_registro`, que el interruptor trata como **bloqueo** — fail-closed.

## 10. Punto 21 — respaldo posterior del estado 50

| | |
|---|---|
| Sello | **`20260917_163739`** |
| Ubicación | `C:\Users\Usuario\respaldo_p1013d\` |

| Artefacto | Tamaño | SHA-256 |
|---|---|---|
| `…_datos.dump` | 8.915.608 B | `b467177976498dac209f6a39dfbfd32b4d5b45a549ac86cc…` |
| `…_roles.sql` | **10.267 B** | `3d81ac25adb6c639ecf6712ec10d3c4737eaf20218553fe1…` |
| `…_entorno.sql` | 4.525 B | `96eb3929e791a92e04644ce1f77157220985478628c43dc1…` |

`roles.sql` creció de 9.936 a 10.267 B: el rol nuevo y su membresía.

**Restaurabilidad validada** — restaurado en contenedor virgen, código 0:

```
ledger: 50
rol autonomia_operador: 1
atributos: login=false super=false createdb=false createrole=false
           repl=false bypassrls=false
SET para postgres: true
app_backend sobre interruptor: SELECT
operador sobre interruptor  : INSERT,SELECT
politicas del interruptor   : 2
estado vigente: detenido     filas activo: 0
```

Y sobre esa copia: idempotencia 5/5 y scheduler **`succeeded`, 0 fallas**.

## 11. Evidencia conservada

| Archivo | Qué es |
|---|---|
| `scratchpad/p1013d_out.txt` · `_err.txt` | stdout y stderr del `--aplicar` |
| `scratchpad/p1013d_tiempos.txt` | inicio, fin y código de salida |
| `scratchpad/p1013d_pre.py` | condición 1 |
| `scratchpad/p1013_supautils.py` | condición 3 |
| `scratchpad/p1013d_post.py` | puntos 9 a 20 |
| `C:\Users\Usuario\respaldo_p1013_post\` | respaldo **previo** `20260917_152749` |
| `C:\Users\Usuario\respaldo_p1013d\` | respaldo **posterior** `20260917_163739` |
| `C:\Users\Usuario\respaldo_p1013\` | respaldo `20260917_141238` (previo al lote) |

## 12. Errores e incidentes

**Ninguno en producción.** La migración aplicó a la primera, con código 0.
Cero llamadas a WispHub, SmartOLT o cualquier servicio externo.

Dos incidentes de método, en mis instrumentos de medición:

1. **Conexión del motor con `sslmode=require`** → `server does not support SSL`.
   Supavisor no lo soporta en ese puerto. Corregido a `disable`.
2. **Una prueba dio un falso rojo.** Insertaba las dos transiciones del operador
   en la **misma** transacción, así que `now()` —y por tanto `creado_en`— era
   idéntico en ambas, y el desempate por `id` es un uuid aleatorio: la lectura
   de «la más reciente» devolvía cualquiera de las dos. Corregido leyendo el
   `returning` de cada inserción, que es lo que la prueba debía afirmar.

   > **Observación que queda anotada:** el índice vigente es
   > `(organization_id, creado_en desc)`. Dos transiciones dentro de una misma
   > transacción empatarían, y el desempate no es determinista. En operación
   > real cada transición es su propia transacción, así que no afecta hoy — pero
   > conviene tenerlo presente si alguna vez se escriben dos de golpe.

## 13. Estado final

| Exigido | Medido |
|---|---|
| Ledger = 50 | **50** |
| `huecos()` vacío | **vacío** |
| Segregación instalada | **sí** |
| `app_backend` NO puede activar | **sí** — sólo `SELECT`, 5 vías cerradas |
| Operador puede activar/detener | **sí** |
| Autonomía DETENIDA | **sí** — 1 fila, `detenido`, 0 `activo` |
| Código de autonomía desplegado | **ninguno** |
| `DBUSER` | **sin cambios** |
| M02 / M03 / M09 | **sin cambios** |
| WispHub / SmartOLT | **sin llamadas** |

## 14. Rollback disponible

- **Durante la corrida:** no hizo falta; es automático y está medido.
- **Para volver al estado previo (49):** restaurar **`20260917_152749`**,
  verificado hoy.
- **Para volver al estado actual (50):** restaurar **`20260917_163739`**,
  verificado hoy.
- **Lo que NO es rollback:** un `drop` manual — deja el ledger diciendo
  «aplicada» con 0 objetos y el CLI reportando 0 pendientes.

---

## Lo que sigue pendiente, y no está autorizado

El kill switch está instalado y **fail-closed en la base**, pero **ningún código
lo consulta todavía**: `interruptor.py`, `idempotencia.py`, `db.py`, `motor.py`
y el resto del paso 10.12 siguen sin desplegar. La autonomía no está operativa
por dos motivos independientes, y eso es deliberado.

Fuera de alcance de esta autorización: Paso 10.14, despliegue de
`interruptor.py` / `idempotencia.py`, cambio de `DBUSER`, activación de la
autonomía, niveles 0–4.

**La autorización del Paso 10.13D queda consumida con esta validación. Me
detengo y espero revisión.**
