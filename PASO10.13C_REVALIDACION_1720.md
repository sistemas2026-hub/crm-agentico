# Paso 10.13C — Corrección de la migración 1720 y revalidación

**Fecha:** 17/09/2026 · **Producción: NO se ejecutó nada.**
Sigue en ledger **49**, sin rol `autonomia_operador`, sin función de parada,
sin política del operador, y con `app_backend` conservando `INSERT,SELECT`.

**Veredicto: GO técnico** para aplicar la 1720 corregida, condicionado a una
autorización nueva y explícita.

---

## 1. El cambio

### Checksums

| | |
|---|---|
| **Anterior** | `5699ffcbffb8f7420ff7681038f41bcf2cecadcb302518a1f4515efbc26bbb0b` |
| **Nuevo** | **`3ab03f9e8046e1accf60fc69833de62acd5b2bc3b4aa54bf27db8b597e3879f9`** |
| Tamaño | 15.674 → **16.935 bytes** · UTF-8 sin BOM · sólo LF |
| Canónico según el CLI | **sí** — `no canonicos: 0` |

### Diff exacto

**Una sola línea funcional cambia.** El resto son comentario y la comprobación
sustitutiva.

```diff
@@ -72,8 +72,33 @@
 --  Explicito y reaplicable: si el rol ya existia con otros atributos, aqui
 --  vuelve a la forma minima. Un operador no necesita nada de esto.
+--
+--  SUPERUSER NO SE IMPONE: SE COMPRUEBA  --  corregido el 17/09/2026 (10.13C)
+--  ------------------------------------------------------------------------
+--  La version anterior incluia 'nosuperuser' en esta linea y PRODUCCION la
+--  rechazo entera con 'permission denied to alter role'. Alli 'postgres' corre
+--  con SUPERUSER=false, y un rol que no es superusuario no puede tocar el
+--  atributo SUPERUSER de nadie -- ni siquiera para quitarlo. En la replica
+--  pasaba porque alli 'postgres' es el superusuario de arranque.
+--
+--  Y era redundante: medido en produccion, un rol recien creado ya nace con
+--  login, superuser, createdb, createrole, replication y bypassrls en falso.
+--  Asi que el atributo se COMPRUEBA abajo en vez de imponerse. Las otras cinco
+--  propiedades si se imponen: estan probadas una por una contra produccion.
 alter role autonomia_operador
-  nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
+  nologin nocreatedb nocreaterole noreplication nobypassrls;
+
+do $$
+begin
+  if exists (select 1 from pg_roles
+              where rolname = 'autonomia_operador' and rolsuper) then
+    raise exception
+      'autonomia_operador es SUPERUSER. Esta migracion no lo degrada a '
+      'proposito: produccion rechaza ALTER ROLE ... NOSUPERUSER porque su '
+      'postgres no es superusuario. Corregirlo con una credencial de '
+      'superusuario antes de volver a aplicar.';
+  end if;
+end $$;
 
 --  'set true' es lo que habilita el SET ROLE; 'inherit false' evita que
 --  postgres cargue estos privilegios sin pedirlos.
```

**1 línea quitada, 26 añadidas.** Ninguna otra línea del archivo se tocó.

### Motivo

`ALTER ROLE ... NOSUPERUSER` es **imposible** en producción: `postgres` corre con
`SUPERUSER=false`, y un rol que no es superusuario no puede tocar el atributo
SUPERUSER de nadie, ni para quitarlo. Y era **redundante**, porque el rol ya
nace `NOSUPERUSER`. Se sustituye por una comprobación que *verifica* el
atributo en vez de imponerlo.

### Punto 1 — cada propiedad conservada, probada explícitamente EN PRODUCCIÓN

Sonda dentro de una transacción deshecha. No se asumió nada.

```
postgres: super=False createrole=True createdb=True replication=True bypassrls=True

atributos POR DEFECTO de un rol recien creado (sin ningun ALTER):
  rolcanlogin False · rolsuper False · rolcreatedb False
  rolcreaterole False · rolreplication False · rolbypassrls False · rolinherit True

cada propiedad, por separado:
  [ok] nologin        -> permitido        [ok] nobypassrls   -> permitido
  [ok] nocreatedb     -> permitido        [ok] noinherit     -> permitido
  [ok] nocreaterole   -> permitido        [ok] inherit       -> permitido
  [ok] noreplication  -> permitido
  [NO] nosuperuser    -> InsufficientPrivilege: permission denied to alter role

la linea VIEJA (con nosuperuser) -> RECHAZADA
la linea NUEVA (sin nosuperuser) -> PERMITIDA
```

**Sólo `nosuperuser` es rechazado.** Las cinco propiedades que la migración
conserva son ejecutables en producción, una por una y en conjunto.

## 2. Respaldo utilizado y estado inicial

**`20260917_152749`** — la producción **de hoy**, con las cuatro primeras ya
aplicadas. Restaurado con `restaurar.sh`, código **0**.

| Estado inicial | Medido | Exigido |
|---|---|---|
| Ledger | **49** | 49 |
| `interruptor_autonomia` / `operaciones_externas` | **existen** | existen |
| Rol `autonomia_operador` | **0** | ausente |
| Función `autonomia_detener` | **0** | ausente |
| Política `tenant_aislado_operador` | **0** | ausente |
| `app_backend` sobre el interruptor | **`INSERT,SELECT`** | el fail-open sin cerrar |
| Tablas / políticas en `asistente` | **37 / 37** | 37 / 37 |
| Scheduler | **`succeeded`, 0 fallas** | operativo |

### Punto 5 — precondiciones antes de aplicar

```
anotados en el ledger : 49
pendientes            : 1
con checksum distinto : 0        <- las cuatro ya aplicadas siguen coincidiendo
no canonicos          : 0
  pendiente: 202609151720_segregacion_operador_autonomia.sql
checksum del pendiente: 3ab03f9e8046e1accf60fc69833de62acd5b2bc3b4aa54bf27db8b597e3879f9
huecos()              : []  vacio
```

## 3. Ejecución — sólo corrió la 1720

```
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar

[migrar] 1 pendiente(s):
  [ok] 202609151720_segregacion_operador_autonomia.sql  (25 ms)
[migrar] 1 aplicada(s).

codigo 0     proceso completo: 0,60 s
```

**No reaplicó las cuatro anteriores.** El mecanismo canónico, sin SQL manual.

## 4. Punto 17 — Ledger 49 → 50

| | |
|---|---|
| Filas | **50** |
| Las 49 previas | **idénticas** — `diff` vacío contra el ledger extraído del respaldo |
| Fila nueva | `202609151720…` · `3ab03f9e8046e1ac…` · `origen=aplicada` · 15 ms |
| Checksum del ledger = archivo en disco | **sí** |
| `huecos()` | **vacío** · pendientes 0 · discrepancias 0 · no canónicos 0 |

## 5. Puntos 6 y 16 — propiedades del rol, **verificadas**

| Atributo | Medido | |
|---|---|---|
| `rolcanlogin` | **False** | NOLOGIN |
| **`rolsuper`** | **False** | **NOSUPERUSER — verificado, no impuesto** |
| `rolcreatedb` | **False** | NOCREATEDB |
| `rolcreaterole` | **False** | NOCREATEROLE |
| `rolreplication` | **False** | NOREPLICATION |
| `rolbypassrls` | **False** | NOBYPASSRLS |
| `rolinherit` | True | atributo propio del rol; **no afecta**: el rol no es miembro de nada, y la membresía administrativa es `inherit false` |

**La migración ya no ejecuta `ALTER ROLE … NOSUPERUSER`.** El atributo se
comprueba y, si alguna vez fuera `true`, la migración aborta con un mensaje que
dice exactamente qué hacer.

### Membresías y SET

```
otorgante=postgres  miembro=postgres   admin=false inherit=false set=true
otorgante=postgres  miembro=sim_admin  admin=false inherit=false set=true   (fixture)
```

| Rol | ¿puede `SET ROLE autonomia_operador`? |
|---|---|
| `postgres` | **sí** |
| `sim_admin` (fixture) | **sí** |
| `sim_runtime` | **no** |
| `app_backend` | **no** |

## 6. Punto 7 — `session_user` real, ninguno es `postgres`

| Rol de prueba | Atributos | Papel |
|---|---|---|
| **`sim_admin`** | `NOSUPERUSER`, `CREATEROLE`, `BYPASSRLS`, `LOGIN` | imita al `postgres` de producción (medido: idénticos) |
| **`sim_runtime`** | sin atributos, `LOGIN`, miembro de `app_backend` | imita al motor |

```
admin  : session_user=sim_admin super=False bypassrls=True
         SET ROLE autonomia_operador -> current_user=autonomia_operador   [ok]

runtime: session_user=sim_runtime
         SET ROLE autonomia_operador -> permission denied to set role     [ok]
```

> Dos concesiones son **fixture de prueba**, no parte de la migración: crear
> `sim_admin`/`sim_runtime` y darle a `sim_admin` la misma membresía que la
> migración le da a `postgres`. Ambos roles se retiran al terminar.

## 7. Punto 8 — segregación

Con `session_user=sim_runtime`, `current_user=app_backend`:

| Operación | Resultado |
|---|---|
| `SELECT` | **permitido** — `detenido`, actor `migracion` |
| `INSERT 'activo'` | **`permission denied for table`** |
| `INSERT` arbitrario | **`permission denied for table`** |
| `UPDATE` | **`permission denied for table`** |
| `DELETE` | **`permission denied for table`** |
| `SET ROLE autonomia_operador` | **`permission denied to set role`** |

Con `session_user=sim_admin`, `current_user=autonomia_operador`:

| Operación | Resultado |
|---|---|
| activar | **permitido** → `activo` |
| detener | **permitido** → `detenido` |
| `UPDATE` | **denegado** (append-only también para el operador) |
| `DELETE` | **denegado** |

## 8. Punto 9 — la parada

| | |
|---|---|
| `app_backend` detiene por la función | **sí** → `detenido`, actor `sim_runtime` |
| Pasar `'activo'` como destino | **imposible** — `function asistente.autonomia_detener(unknown,unknown,unknown,unknown) does not exist` |
| Exige actor y motivo | **sí** — `hay que decir QUIEN detiene la autonomia` |

El estado está fijo en el cuerpo de la función; no es un parámetro. Y la
verificación de la migración prohíbe que exista una segunda `autonomia_detener`
sobrecargada.

## 9. Punto 10 — RLS con FORCE

| | |
|---|---|
| Operador escribiendo para otra organización | **`new row violates row-level security policy`** |
| Operador leyendo otra organización | **0 filas** |
| Runtime con el tenant B | **0 filas** (no ve las de A) |
| Runtime con el tenant A | 4 filas (las suyas) |

| Organización | `tenant_config` | Estado |
|---|---|---|
| Rapilink | 1 | **`detenido`** |
| Rapilink Telecomunicaciones | **0** | **`sin_registro`** → bloquea |

**No se creó `tenant_config` artificial** — sigue habiendo 1.

## 10. Punto 11 — idempotencia, sin llamadas externas

| Caso | Resultado | Llamadas |
|---|---|---|
| Primera vez | `ejecutar` | 1 |
| Repetida (misma clave, mismos argumentos) | `repetida` | **0** |
| Colisión en la primitiva (misma clave, otro hash) | **`rechazada`** | **0** |
| Otro origen | `ejecutar` | 1 |
| Concurrencia (2 hilos) | una sola ejecutada (`en_curso` / `ejecutar`) | 1 |

Y el reintento, con clave limpia:

```
1) primera, el tercero falla : excepcion propagada; llamadas=1
2) reintento IMPLICITO       : ejecutada=False decision=fallida
                               codigo=OPERACION_FALLIDA_PREVIA  llamadas nuevas=0
3) reintento EXPLICITO       : ejecutada=True decision=ejecutar  llamadas nuevas=1
```

**El reintento es sólo explícito.** Todas las acciones son funciones locales:
**cero llamadas a WispHub, SmartOLT o cualquier servicio externo.**

## 11. Punto 12 — scheduler

`job_claim → job_contexto → job_heartbeat → job_finalize` = **`succeeded`**, con
`capability` de 64 hex, `config_hash` coincidente y **3 eventos**. En la réplica
migrada y en la restaurada.

> `verificar_restauracion.py` reporta **1 falla: «politicas en asistente»** —
> 38 en la réplica contra 37 en producción. Es **exactamente la política que la
> migración añade** (`tenant_aislado_operador`). Las tablas coinciden (37 = 37).
> No es un defecto.

## 12. Punto 13 — locks

`ACCESS EXCLUSIVE` retenido sobre `asistente.interruptor_autonomia` (la tabla
que esta migración necesita), `lock_timeout=10s`:

```
[FALLA] 202609151720_…: LockNotAvailable: canceling statement due to lock timeout
La migracion se deshizo entera y NO quedo anotada.
codigo 1     duracion: ~11 s
```

| Tras el fallo | |
|---|---|
| Ledger | **49** — nada anotado |
| Rol / función / política del operador | **0 / 0 / 0** |
| `app_backend` | **`INSERT,SELECT`** — el `revoke` no se aplicó |

**Liberado el bloqueo, el reintento aplica y sale con código 0** (1138 ms).
Falla limpia, atómica y recuperable.

## 13. Punto 14 — respaldo y restauración del estado 50

Respaldo de la réplica en estado 50 prístino (sello `20260917_153708`;
8.914.671 + 7.481 + 3.751 bytes; código 0) → restaurado desde cero →
**27 de 27 comprobaciones idénticas**:

ledger 50 y su md5 · última anotada · rol operador y sus atributos ·
`SET ROLE` · grants de `app_backend` (**`SELECT`**) y del operador
(`INSERT,SELECT`) · grants sobre `operaciones_externas` · RLS+FORCE de ambas
tablas · las 2 políticas · 38 políticas · md5 de las 10 funciones `job*` ·
**cuerpo y firma de `autonomia_detener`** · `SECURITY DEFINER` + `search_path` +
dueño · ACL de `EXECUTE` · semilla `detenido` · **0 filas `activo`** · clave
primaria de idempotencia · 37 tablas · ownership · `public` 135/`crm_owner`.

**Membresías, comparadas aparte** (el respaldo de roles debe transportarlas):

```
origen     : postgres -> postgres  admin=false inherit=false set=true
restaurada : postgres -> postgres  admin=false inherit=false set=true
pg_has_role(postgres, operador, 'SET') = true   en ambos
```

Scheduler sobre la restaurada: **`succeeded`**. Y **todas** las pruebas de
conducta (§6–§9) repetidas sobre la restaurada: **0 en rojo**.

## 14. Punto 15 — supautils: qué se probó dónde

**No declaro equivalencia entre réplica y producción.** El reparto exacto:

### Probado EN PRODUCCIÓN (transacción deshecha, sin dejar rastro)

| Comportamiento | Resultado |
|---|---|
| `postgres`: `super=False`, `bypassrls=True`, `createrole=True` | medido |
| **supautils auto-concede** cada rol nuevo a `postgres` | `supabase_admin → postgres`, `admin=True inherit=False` **`set=False`** |
| `SET` **antes** de la concesión explícita | **`False`** — el riesgo era real |
| La concesión de la migración | crea una **segunda** membresía `otorgante=postgres`, **`set=true`** |
| Resultado: `USAGE` / `MEMBER` / `SET` | `False` / `True` / **`True`** |
| `SET ROLE` de verdad | funciona |
| Función `SECURITY DEFINER` de `postgres` atraviesa `FORCE RLS` | **sí** — 1 fila escrita llamada como `app_backend` |
| `app_backend` sin la función | `permission denied` |
| Cada atributo de `ALTER ROLE` por separado | sólo `nosuperuser` rechazado |
| La línea nueva completa | **permitida** |

### Probado SÓLO EN RÉPLICA

Aplicación real de la migración y su anotación en el ledger; conducta del
operador y del runtime con `session_user` real; aislamiento RLS entre
organizaciones; idempotencia; scheduler; locks; respaldo/restauración.

### Lo que depende de supautils y no se puede reproducir en réplica

La **auto-concesión con `SET FALSE`**. La imagen `pgvector/pgvector:pg17` no
tiene supautils, así que allí sólo existe la membresía que crea la migración.
En producción coexisten **dos** membresías y `SET` acaba en `true` porque
`pg_has_role` resuelve por cualquiera de ellas. **Esto está medido en
producción**, no inferido — y la comprobación 5.2 de la migración aborta si
alguna vez dejara de cumplirse.

### Otra divergencia conocida

La réplica corre con `postgres` **SUPERUSER** (es el superusuario de arranque y
**no se puede degradar**: `the bootstrap superuser must have the SUPERUSER
attribute`). Por eso el fallo del Paso 10.13 no apareció en réplica. Mitigación
aplicada aquí: **cada propiedad del `ALTER ROLE` se probó contra producción**, y
las pruebas de conducta usan `sim_admin`/`sim_runtime`, que no son superusuarios.

## 15. Riesgos

1. **`asistente.interruptor_autonomia` recibe `ACCESS EXCLUSIVE`** durante la
   migración (el `revoke` y la política). Es tabla nueva y nadie la lee todavía:
   riesgo bajo. Duración medida: **25 ms**.
2. **Producción sigue hoy con el fail-open abierto**: `app_backend` tiene
   `INSERT` sobre el interruptor. Inerte porque ningún código desplegado lee esa
   tabla — pero **no debe desplegarse `interruptor.py` antes de cerrar esto**.
3. **La auto-concesión de supautils no es reproducible en réplica.** Medida en
   producción y protegida por la comprobación 5.2, que aborta la migración
   entera si `SET` no queda en `true`.
4. **La réplica no puede degradar a `postgres`.** Compensado probando cada
   propiedad contra producción; pero es una asimetría estructural que seguirá
   existiendo para futuras migraciones que toquen roles.
5. **`rolinherit = True`** en `autonomia_operador`. No tiene efecto: el rol no es
   miembro de ningún otro y la membresía administrativa es `inherit false`. Se
   documenta para que no sorprenda en una auditoría.
6. **El código de `db.py` (10.12) sigue sin desplegar.** Hasta que salga,
   `cli/autonomia.py` no podrá mover el interruptor por la vía del operador.

## 16. Rollback

- **Durante la corrida:** automático y medido (§12) — se deshace entera y no
  queda anotada.
- **Tras el COMMIT:** restaurar **`20260917_152749`**, que es exactamente el
  estado actual de producción (verificado hoy: restaura, scheduler `succeeded`).
- **Lo que NO es rollback:** un `drop` manual. Deja el ledger diciendo
  «aplicada» con 0 objetos y el CLI reportando 0 pendientes.

---

# GO / NO-GO para producción

## **GO**, condicionado a autorización nueva y explícita.

| Criterio | Resultado |
|---|---|
| Diff mínimo: sólo se quita `nosuperuser` | **sí** — 1 línea funcional |
| Cada propiedad conservada, probada en producción | **6 de 6** |
| `nosuperuser` confirmado como la única rechazada | **sí** |
| La línea nueva es ejecutable en producción | **sí** |
| Aplica sólo la 1720, no reaplica las cuatro | **sí** — 25 ms, código 0 |
| Ledger 49 → 50, las 49 previas idénticas | **sí** |
| Checksum del ledger = archivo | **sí** |
| `huecos()` vacío | **sí** |
| Rol: NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS | **6 de 6, verificados** |
| `NOSUPERUSER` verificado y no impuesto | **sí** |
| `SET ROLE` con `session_user` real: admin sí, runtime no | **sí** |
| Segregación de `app_backend` (5 vías) | **5 de 5 cerradas** |
| Operador: activar, detener, sin UPDATE/DELETE | **sí** |
| Parada sólo por la función; `'activo'` imposible | **sí** |
| RLS: aislamiento del operador y del runtime | **sí** |
| Idempotencia, retry sólo explícito | **sí**, 0 llamadas externas |
| Scheduler | **`succeeded`** |
| Locks | falla limpia ~11 s, nada parcial, retry recupera |
| Backup/restore del estado 50 | **27/27** + membresías + conducta 0 en rojo |
| Producción | **intacta, ledger 49** |

**Duración medida:** **25 ms** de SQL, 0,60 s de proceso.
Con bloqueo de por medio: ~11 s antes de abortar.

**Comando exacto:**

```bash
cd <repo>
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a
PGOPTIONS="-c lock_timeout=10s" py -3.13 cli/migrar_asistente.py --aplicar
```

**Preflight mínimo:** ledger **49** · **1 pendiente** (`…1720`) ·
`con checksum distinto: 0` · checksum del pendiente
**`3ab03f9e8046e1ac…`** · rol, función y política del operador **ausentes** ·
`app_backend` con `INSERT,SELECT` · 0 bloqueos sobre
`asistente.interruptor_autonomia` · 0 transacciones abiertas.

**Post:** ledger **50** · 49 previas idénticas · `huecos()` vacío · los 6
atributos del rol · `SET` sólo para `postgres` · `app_backend` con **`SELECT`**
· las 5 vías cerradas · operador opera · parada funciona · RLS aislado ·
scheduler `succeeded`.

**Criterio de abortar:** cualquier preflight en rojo · `LockNotAvailable` (no
forzar, no matar sesiones) · cualquier `raise` del bloque de verificación ·
cualquier fallo posterior → restaurar `20260917_152749`, no corregir a mano.

---

## Estado al cerrar

Producción: ledger **49**, rol `autonomia_operador` **no existe**, función de
parada **no existe**, política del operador **no existe**, `app_backend`
conserva `INSERT,SELECT`. `DBUSER` sin cambios. **AUTONOMÍA = DETENIDA / NO
OPERATIVA.** Ningún código de autonomía desplegado. M02, M03, M09, WispHub,
SmartOLT, Celery, motor y scheduler: **sin tocar**. Réplicas eliminadas.
Respaldos `20260917_141238` y `20260917_152749` conservados.

**Me detengo. La ejecución productiva requiere una autorización nueva y
explícita.**
