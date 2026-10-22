# Paso 10.7 — Runbook para ejecutar `--aplicar` en producción

**Fecha:** 17/09/2026
**Estado:** runbook preparado. **`--aplicar` NO se ejecutó.** Producción
intacta: ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`, 35 tablas en
`asistente`.

> Todo lo que este runbook afirma sobre bloqueos, transacciones y
> comportamiento ante un timeout está **medido en réplica**, no supuesto.

---

## 1. Objetivo

Aplicar en producción las **4 migraciones pendientes** dejando el ledger
coherente con el estado físico, sin tocar las 45 filas históricas.

## 2. Alcance

| # | Archivo | Qué hace de verdad |
|---|---|---|
| 1 | `202609151700_scheduler_persistente_reconciliado.sql` | Reconciliación. No crea nada: recrea 5 políticas y la FK `js_run_coherente` |
| 2 | `202609151705_scheduler_funciones_reconciliado.sql` | Reconciliación. Reemplaza 10 funciones con cuerpos idénticos; recrea 2 políticas sobre tablas del motor |
| 3 | `202609151710_interruptor_autonomia.sql` | **Despliegue real**: crea `asistente.interruptor_autonomia` |
| 4 | `202609151715_operaciones_externas.sql` | **Despliegue real**: crea `asistente.operaciones_externas` |

> **Los archivos 3 y 4 no son reconciliación.** `--aplicar` los ejecuta en la
> misma pasada porque están pendientes. Si sólo se quiere reconciliar, hay que
> sacarlos del directorio antes y volver a ponerlos después — decisión previa,
> no improvisada durante la ventana.

**Fuera de alcance:** `DBUSER`, ownership de `public`, RLS del CRM, Celery,
motor, autonomía, integraciones externas.

## 3. Precondiciones

- Paso 10.5 aplicado: `con checksum distinto: 0`, 4 pendientes.
- Credencial: **`postgres`** — es dueño del esquema `asistente`.
  `crm_migrator` **no** tiene permisos ahí y no se le van a conceder.
- Respaldo fresco y verificado (§4).
- Ventana con el motor y el CRM en reposo (§6).

### Las 7 tablas que reciben `ACCESS EXCLUSIVE`

| Tabla | Filas | Tamaño | Quién la lee | Riesgo de bloquearla |
|---|---|---|---|---|
| `asistente.job_catalogo` | 0 | 32 kB | sólo `asistente_owner`, `postgres`, roles admin | **nulo** |
| `asistente.job_schedule_state` | 0 | 72 kB | ídem | **nulo** |
| `asistente.job_run` | 0 | 128 kB | ídem | **nulo** |
| `asistente.job_attempt` | 0 | 96 kB | ídem | **nulo** |
| `asistente.job_run_event` | 0 | 80 kB | ídem | **nulo** |
| `asistente.tenant_config` | 1 | 2.848 kB | **`app_backend`, `motor_user`** | **el motor espera** |
| `asistente.tenant_config_historial` | 27 | 2.632 kB | **`app_backend`, `motor_user`** | **el motor espera** |

**Y una octava tabla, fuera de `asistente`:** los archivos 3 y 4 crean claves
foráneas hacia `public.organization`. Medido en réplica:

```
public.organization    ShareRowExclusiveLock    <- TABLA DEL CRM
```

`ShareRowExclusiveLock` **bloquea las escrituras** sobre `organization` (permite
lecturas). O sea: el radio de impacto **entra en el esquema del CRM**, no se
queda en `asistente`.

### Qué queda esperando

- Cualquier `SELECT` del motor sobre `tenant_config` / `tenant_config_historial`
  durante los ~60 ms del archivo 2.
- Cualquier `INSERT`/`UPDATE`/`DELETE` sobre `public.organization` durante los
  archivos 3 y 4.
- Nada sobre las 5 tablas `job_*`: están vacías y ningún proceso de runtime las
  lee (el scheduler no tiene trabajos registrados — `job_catalogo` = 0 filas).

### Qué ocurre si se alcanza `lock_timeout` — **medido**

Réplica con `ACCESS EXCLUSIVE` retenido sobre `tenant_config` y
`PGOPTIONS="-c lock_timeout=2s"`:

```
[migrar] 4 pendiente(s):
  [ok]    202609151700_…persistente  (17 ms)
  [FALLA] 202609151705_…funciones: LockNotAvailable: canceling statement due to lock timeout
  La migracion se deshizo entera y NO quedo anotada. Las anteriores si.
codigo de salida: 1
```

Estado resultante: ledger **45 → 46**; el archivo 2 **sin rastro** (no anotado,
sin efecto); archivos 3 y 4 **nunca corrieron** (sus tablas no existen).

**Recuperación, medida:** liberado el bloqueo, un simple reintento aplica las 3
restantes y sale con código 0 (ledger 49, 6 `aplicada`). **Un timeout no deja
nada a medias — deja la corrida a medias, que es recuperable reintentando.**

## 4. Respaldo

```bash
py -3.13 despliegue/respaldo/respaldar.py \
        --destino "C:/Users/Usuario/respaldo_p107" \
        --imagen pgvector/pgvector:pg17
```

**Artefactos** (los tres obligatorios): `<sello>_datos.dump` (~8,9 MB),
`<sello>_roles.sql` (~10 kB), `<sello>_entorno.sql` (~4,5 kB).
**Identificación:** el sello `AAAAMMDD_HHMMSS`, anotado en el informe de la
ejecución y en `<destino>/.sello`.

**Verificación de integridad — obligatoria, no opcional:**

```bash
# restaurar en una replica desechable
docker run -d --name pg-verif -p 15470:5432 -e POSTGRES_PASSWORD=test \
  -v "<destino>:/r" -v "<repo>/despliegue/respaldo:/procedimiento" \
  pgvector/pgvector:pg17
docker exec pg-verif sh /procedimiento/restaurar.sh /r <sello> postgres -U postgres
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto 15470
```

**El respaldo sólo está validado si el verificador sale con 0 fallas** — 25
comprobaciones estructurales contra producción **y** el flujo
`job_claim → job_finalize` terminando en `succeeded`. Un `pg_restore` en 0 no
es evidencia: está medido que también da 0 con el scheduler roto.

**Conservación:** no borrar la réplica de verificación ni los artefactos hasta
cerrar la operación y dar por buena la validación de servicios (§8).

## 5. Pre-flight — todo debe estar en verde

| # | Comprobación | Valor exigido |
|---|---|---|
| 1 | Conexión a producción | responde |
| 2 | `session_user` / `current_user` | `postgres` / `postgres` |
| 3 | Credencial | `postgres` (dueño de `asistente`); **no** `crm_migrator` |
| 4 | `--estado` | `con checksum distinto: 0`, **4 pendientes**, 5 anotadas sin archivo |
| 5 | Ledger | **45 filas**, md5 `58ff01f220787396657af7832f6c48c8` |
| 6 | Bloqueos sobre `asistente` y `public.organization` | **0** |
| 7 | Transacciones abiertas (`idle in transaction`) | **0** |
| 8 | Actividad del scheduler | `job_catalogo` = 0 filas (no hay trabajos) |
| 9 | Actividad del motor | sin sesiones `motor_user` activas; sin escrituras recientes |
| 10 | Tablas en `asistente` | **35** (5 `job_*`) |
| 11 | Políticas en `asistente` | **35** |
| 12 | Funciones `job*` | **10**, md5 conjunto `614d3a167d73bac0ca16cf6fc002a19c` |
| 13 | RLS | 5 `job_*` con RLS activa; `tenant_config(_historial)` con RLS **y FORCE** |
| 14 | Ownership | `job_*` de `asistente_owner`; `public` de `crm_owner` (135 tablas) |
| 15 | Respaldo | sello anotado **y** verificado con 0 fallas |

### Condición exacta de ABORTAR

Abortar **antes de ejecutar** si cualquiera de estas es cierta:

- `con checksum distinto` ≠ 0, o pendientes ≠ 4.
- Ledger ≠ 45 filas o md5 ≠ `58ff01f2…`.
- Hay algún bloqueo sobre `asistente` o sobre `public.organization`.
- Hay transacciones abiertas.
- `job_catalogo` ≠ 0 filas (el scheduler tendría trabajos y el bloqueo dejaría
  de ser inocuo).
- El verificador del respaldo no salió con 0 fallas.
- La credencial no es `postgres`.

## 6. Ventana recomendada

Fuera del horario de atención, con el motor sin tráfico de WhatsApp — la misma
clase de ventana que se usó en el paso 9 (entonces: 0 transacciones abiertas,
0 bloqueos, 0 actividad en 15 minutos).

**Duración esperada, medida:** 17 + 23 + 13 + 8 ≈ **60 ms** de ejecución. La
ventana no es por duración, es por garantizar que nadie tenga tomada una de las
8 tablas.

## 7. Ejecución

```bash
cd <repo>
set -a; source <(grep -E "^DB(HOST|PORT|NAME|USER|PASSWORD)=" .env); set +a

PGOPTIONS="-c lock_timeout=10s" \
  py -3.13 cli/migrar_asistente.py --aplicar \
  > /tmp/p107_out.txt 2> /tmp/p107_err.txt
echo "codigo: $?"
```

**`lock_timeout` por sesión, nunca permanente.** `PGOPTIONS` lo fija sólo para
las conexiones de ese proceso; termina el proceso y desaparece. **No** usar
`ALTER SYSTEM` ni `ALTER DATABASE … SET lock_timeout`, que lo dejarían puesto
para todo el mundo.

**La transacción que usa el CLI — medida en el código y en réplica:** una
transacción **por archivo**, no una para los cuatro. Dentro de cada una van el
SQL del archivo **y** su fila del ledger, así que son atómicos juntos: o se
aplica y queda anotado, o no pasa ninguna de las dos cosas. Todo bajo un
*advisory lock* de sesión que impide que dos migradores corran a la vez.

**Qué capturar:** `stdout`, `stderr`, código de salida, y la hora de inicio y
fin. Guardar los dos archivos junto al informe.

**Éxito:** código de salida **0** y la línea `[migrar] 4 aplicada(s).`

### Si salta el timeout

Código **1** y una línea `[FALLA] <archivo>: LockNotAvailable`. No es una
emergencia: el archivo que falló no dejó rastro y los anteriores quedaron bien.

1. Identificar quién tenía el bloqueo (`pg_locks` + `pg_stat_activity`).
2. Esperar a que termine. **No** matar sesiones del motor ni del CRM.
3. Reintentar el mismo comando: el CLI aplica sólo lo que falta.
4. Si vuelve a fallar dos veces, **abortar la ventana** y reprogramar. Dejar
   anotado en qué archivo se quedó.

### Si aparece un DDL inesperado

Se ejecuta con la traza puesta (§11). Si el DDL registrado **no coincide** con
el inventario del paso 10.6 —113 operaciones: 0 `CREATE TABLE` y 0
`CREATE INDEX` sobre objetos históricos, 10 funciones reemplazadas, 7 políticas
recreadas, 1 FK recreada— **abortar y no reintentar**. Recoger la traza y
analizarla antes de volver a intentarlo.

## 8. Validación

### A. Ledger

- **49 filas** (45 + 4).
- Las **45 históricas idénticas**: comparar el md5 de esas 45 contra
  `58ff01f220787396657af7832f6c48c8`, calculado sobre el mismo conjunto.
- 4 filas nuevas con `origen='aplicada'` y los checksums
  `e7a70f05…`, `ca0bf081…`, `e0d6b8dc…`, `9c2f242d…`.

### B. Objetos

| | Esperado |
|---|---|
| Tablas `job_*` / índices / constraints / políticas | 5 / 21 / 48 / 5 |
| Funciones `job*` y md5 conjunto | 10 · `614d3a167d73bac0ca16cf6fc002a19c` |
| FK `js_run_coherente` | presente, con sus 4 triggers de integridad |
| ACL de las 5 `job_*` | `{asistente_owner=arwdDxtm/asistente_owner}` (ya es el actual) |
| Ownership | `job_*` de `asistente_owner` |
| RLS | 5 `job_*` activa; `tenant_config(_historial)` activa **y FORCE** |
| Tablas nuevas | `interruptor_autonomia` y `operaciones_externas`, con su RLS y su política |
| `public` | 135 tablas, 132 políticas, todas de `crm_owner` — **sin cambios** |

### C. Scheduler

```bash
py -3.13 despliegue/respaldo/verificar_restauracion.py --puerto <replica>
```
o, contra producción, el flujo dentro de una transacción revertida (como en el
paso 10.5): `job_claim → job_contexto → job_heartbeat → job_finalize` →
**`succeeded`**, con `capability` de 64 hex, `config_hash` coincidente y 3
eventos. Comprobar después que las 5 tablas vuelven a 0 filas.

### D. Datos

`asistente.messages` / `conversations` / `tool_calls` / `tenant_config` y
`public.case` / `activity` con los mismos conteos que antes de la ventana.

## 9. Validación de servicios — a definir ahora, ejecutar después

| Servicio | Prueba | Verde si |
|---|---|---|
| CRM backend | `GET https://crm.rapilinksas.co/` y el admin de Django | 401 y 302, como antes |
| Frontend | `GET https://agent.rapilinksas.co/login` | 200 |
| Scheduler | flujo completo revertido (§8.C) | `succeeded` |
| Motor | `app_backend` conserva `select/insert` en sus 4 tablas de `asistente`; y de las tablas nuevas puede leer las que su política permita | permisos sin cambio |
| Celery | no se toca en este paso; comprobar que no aparecen errores nuevos de permisos o conexión | sin errores nuevos |

> El host público del motor devuelve `404` del router desde antes del paso 9;
> **no sirve como señal de salud** y no debe tomarse como fallo.

## 10. Rollback

### NIVEL 1 — falla antes del COMMIT de un archivo

**Automático y ya medido.** La transacción de ese archivo se deshace entera y
**no queda anotado**. Los archivos anteriores de la misma corrida **sí quedan
aplicados y anotados**. No hay nada que hacer a mano: se corrige la causa y se
reintenta.

### NIVEL 2 — hubo COMMIT y una verificación posterior falla

No todo se arregla restaurando el respaldo. Por partes:

| Qué falló | Reversible por migración | Requiere restauración |
|---|---|---|
| Archivos 1 y 2 (reconciliación) | **No hay nada que revertir**: dejan definiciones idénticas a las que ya había. Medido: índices, constraints, políticas y cuerpos de función quedan iguales | — |
| Archivos 3 y 4 (tablas nuevas) | **Sí**: `drop table asistente.interruptor_autonomia` / `operaciones_externas`. Son tablas nuevas, sin datos de negocio y sin dependientes | — |
| Pérdida o alteración de datos | — | **Sí**, restaurar el respaldo de §4 |
| RLS o permisos alterados en `tenant_config(_historial)` | Reaplicar la política correcta | Sólo si no se puede reconstruir |

**El ledger no se toca en ningún nivel.** Es de solo-agregar: una fila anotada
se queda. Si se revierte físicamente una migración, eso se documenta — no se
borra su fila.

## 11. Evidencias a recoger

1. `--estado` antes y después.
2. Ledger: filas y md5, antes y después; y las 45 históricas comparadas.
3. `stdout`, `stderr` y código de salida del `--aplicar`, con horas.
4. **La traza de DDL**, para poder compararla con las 113 operaciones del 10.6.
   Si se quiere el mismo detalle que en réplica, instalar antes los *event
   triggers* de auditoría — **decisión previa**: son DDL en producción, así que
   o se autorizan explícitamente o se acepta tener sólo el log del servidor.
5. Inventario de objetos antes/después (§8.B).
6. Resultado del flujo del scheduler.
7. Conteos de datos antes/después.
8. Sello del respaldo y salida de su verificación.

## 12. Checklist GO / NO-GO

| Check | GO | NO-GO | Evidencia |
|---|---|---|---|
| **Respaldo** | 3 artefactos + verificador con **0 fallas** | falta un artefacto, o el verificador falla | sello + salida de `verificar_restauracion.py` |
| **Bloqueos** | 0 sobre `asistente` y `public.organization` | cualquiera presente | `pg_locks` |
| **Transacciones abiertas** | 0 | ≥ 1 | `pg_stat_activity` |
| **Scheduler** | `job_catalogo` = 0 filas | hay trabajos registrados | conteo |
| **Motor** | sin sesiones activas ni escrituras recientes | tráfico en curso | `pg_stat_activity` + `max(creado_en)` |
| **Migraciones** | `checksum distinto: 0`, 4 pendientes | cualquier otro número | `--estado` |
| **Ledger** | 45 filas, md5 `58ff01f2…` | distinto | consulta |
| **Ownership** | `job_*` de `asistente_owner`, `public` de `crm_owner` | distinto | catálogo |
| **RLS** | 5 `job_*` activa; `tenant_config(_historial)` activa+FORCE | distinto | catálogo |
| **DDL esperado** | coincide con las 113 operaciones del 10.6 | aparece algo distinto | traza |
| **`lock_timeout`** | fijado por `PGOPTIONS`, por sesión | permanente o sin fijar | comando |
| **Rollback** | niveles 1 y 2 definidos y respaldo conservado | respaldo borrado o sin plan | este documento |
| **Credencial** | `postgres` | `crm_migrator` o cualquier otra | `session_user` |
| **Alcance decidido** | está decidido si los archivos 3 y 4 entran o no | sin decidir | autorización |

**GO exige las catorce.** Cualquier NO-GO detiene la ventana.

---

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, 35
tablas en `asistente`, 5 `job_*`. **`--aplicar` no se ejecutó.** Réplica de
pruebas `pg-107` eliminada. `DBUSER`, ownership, RLS, Celery, motor, autonomía
e integraciones: sin tocar.

**Pendiente de decisión antes de autorizar la ejecución:** si los archivos 3 y 4
—que no son reconciliación, son despliegue— entran en la misma ventana o se
separan.
