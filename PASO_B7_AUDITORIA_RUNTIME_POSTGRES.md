# PASO B-7 — Auditoría y plan de migración del runtime fuera de `postgres`

**Fecha:** 2026-09-17
**Naturaleza:** **auditoría y plan**. No se modificó producción, no se cambió
`DBUSER`, no se tocó código, no se crearon migraciones, no se modificó ningún
permiso, no se activó nada. Contra producción, **solo lecturas**.

**Etiquetas:** **[MEDIDO]** · **[DISEÑO]** · **[DEPENDENCIA]** · **[RIESGO]** ·
**[PENDIENTE]**

---

## 0. Tres correcciones a M09-I, antes de nada

La auditoría profunda cambió tres cosas que M09-I afirmó. Van primero porque
**reducen el alcance de B-7** y conviene saberlo antes de leer el plan.

### 0.1 — El motor **ya** corre fuera de `postgres`

**[MEDIDO]** `.env`:

```
DBUSER        = postgres.<ref>        ← CRM (backend, celery-worker, celery-beat)
MOTOR_DBUSER  = motor_user.<ref>      ← motor y motor-reloj
```

**[MEDIDO]** `docker-compose.prod.yml` ya separa los servicios: `motor` y
`motor-reloj` usan `${MOTOR_DBUSER:?}` — con un incidente documentado el
18/08/2026 que explica por qué dejaron de compartir credencial con el CRM.

> **La migración pendiente es solo del lado CRM/Django, no del motor.**
> M09-I dijo "la aplicación se conecta como `postgres`" — cierto para el CRM,
> **no** para el motor.

### 0.2 — `motor_user` **sí** tiene privilegios en `asistente`, por herencia

**[MEDIDO]** M09-I midió grants **directos** y reportó "ninguno". La medición
correcta incluye la membresía:

```
motor_user  ES MIEMBRO DE  app_backend   (inherit = true, otorgado por supabase_admin)
```

**[MEDIDO]** Efectivo (`has_table_privilege`, que sí cuenta herencia):
`motor_user` == `app_backend` en todo lo medido. La afirmación "sin grants" era
un artefacto de mirar `role_table_grants` en vez de la herencia.

### 0.3 — El INSERT de `autonomia_operador` es **por diseño**, no un exceso

**[MEDIDO]** `db.py::registrar_transicion_autonomia` abre la sesión con
`rol=ROL_OPERADOR_AUTONOMIA`, es decir **hace `SET ROLE autonomia_operador`** y
recién entonces inserta. El INSERT existe porque esa es la vía administrativa
(`cli/autonomia.py`), documentada en los pasos 10.11 y 10.12.

**[MEDIDO]** Y el reparto es exactamente el que se quería:

| Quién | Qué puede hacer con el interruptor |
|---|---|
| Runtime (`app_backend` / `motor_user`) | **LEER**, y `autonomia_detener()` — cuyo cuerpo tiene `'detenido'` **escrito literal** |
| Administración (`autonomia_operador`, vía SET ROLE) | insertar cualquier transición, con actor y motivo |

**[MEDIDO]** La pregunta decisiva, medida:

```
¿quién puede SET ROLE autonomia_operador?
  postgres               SI   ← el único
  app_backend            no
  motor_user             no
  crm_user               no
  crm_migrator           no
  job_executor           no
  scheduler_coordinator  no
```

> **[RIESGO] reformulado, y es más preciso que el de M09-I:** el problema no es
> que `autonomia_operador` pueda activar —para eso existe—. El problema es que
> **mientras el runtime sea `postgres`, el runtime puede hacer `SET ROLE
> autonomia_operador` y activar la autonomía por su cuenta.**
>
> Ese riesgo **desaparece solo** con B-7: ningún rol restringido puede llegar ahí.

**La segregación diseñada en 10.11/10.12 está completa y es correcta. Lo único
que le falta es estar en vigor del lado CRM.**

---

## A. Estado actual

### A.1 — Sesión y base

**[MEDIDO]** Con las credenciales del repositorio:

```
PostgreSQL 17.6 · db = postgres · puerto 5433 (Supavisor, modo sesión)
current_user = postgres      session_user = postgres
```

### A.2 — Qué rol usa cada proceso

**[MEDIDO]** de `docker-compose.prod.yml`, `.env`, `settings.py` y
`nucleo/persistencia/conexion.py`:

| Proceso | Archivo / configuración | Variable | Usuario DB real | Operación | Rol esperado tras B-7 |
|---|---|---|---|---|---|
| `backend` (Django) | compose:109-124 · `settings.py:161` | `${DBUSER}` | **`postgres`** | DML CRM | `crm_user` |
| `celery-worker` | compose:174-177 | `${DBUSER}` | **`postgres`** | DML CRM | `crm_user` |
| `celery-beat` | compose:219-222 | `${DBUSER}` | **`postgres`** | DML CRM | `crm_user` |
| `migrate` (entrypoint) | `entrypoint.sh:53-71` | `${MIGRATOR_DBUSER}` o `${DBUSER}` | **`postgres`** (no hay MIGRATOR) | **DDL** | `crm_migrator` |
| `motor` | compose:304-307 | `${MOTOR_DBUSER}` | **`motor_user`** ✔ | DML `asistente` | `motor_user` (ya) |
| `motor-reloj` | compose:403-406 | `${MOTOR_DBUSER}` | **`motor_user`** ✔ | scheduler | `motor_user` (ya) |
| CLI / scripts | `conexion.py::dsn()` | `DBUSER` o `DATABASE_URL` | según `.env` | variable | según tarea |
| Tests | `conftest` / env de prueba | local | n/a | n/a | n/a |

**[PENDIENTE]** **No se pudo verificar qué credencial usan los servicios
desplegados.** Su entorno vive en Dokploy y desde aquí no se lee. `.env` del
repositorio **no es necesariamente** el entorno de despliegue.
**[MEDIDO]** `pg_stat_activity` no lo resuelve: las únicas conexiones vivas eran
de Supabase y del pooler; el tráfico de la aplicación pasa por Supavisor. **Este
punto debe confirmarse en Dokploy antes de ejecutar B-7.**

---

## B. Dependencias de `postgres` — qué funciona solo por entrar como él

**[MEDIDO]** Clasificadas:

| # | Dependencia | Evidencia | Clase |
|---|---|---|:--:|
| B-a | **DDL de migraciones Django** | `crm_user`/`crm_migrator` tienen CREATE en `public`; `migrate` corre hoy con `postgres` porque no hay `MIGRATOR_DBUSER` | **B** (solo migraciones) |
| B-b | **`SET ROLE autonomia_operador`** | solo `postgres` puede | **C** (administrativa) |
| B-c | **Escritura de `asistente.migraciones_aplicadas`** | solo `postgres` tiene privilegios | **B** |
| B-d | **Escritura de `asistente.job_schedule_state`** | solo `postgres`; el scheduler usa funciones `SECURITY DEFINER` | **D** (accidental: el camino correcto ya existe) |
| B-e | **Propiedad de 32 tablas de `asistente`** | `owner=postgres` | **C** |
| B-f | **Propiedad del esquema `asistente`** | `owner=postgres` | **C** |
| B-g | **BYPASSRLS** | `rolbypassrls=true` | **D** — ver B.1 |
| B-h | CREATEROLE / CREATEDB / REPLICATION | atributos del rol | **C** |
| B-i | Ejecución de `cli/autonomia.py` | necesita SET ROLE (B-b) | **C** |

**Ninguna dependencia clasificada como A (necesaria para runtime).**
Es el resultado que hace viable B-7: **el runtime no necesita ser `postgres`.**

### B.1 — La consecuencia que hay que decir en voz alta

> **[RIESGO]** Hoy la RLS de `asistente.*` **no restringe al runtime del CRM**,
> porque `postgres` tiene `BYPASSRLS` y además es **dueño** de 32 de esas tablas.
> Está medido en el paso 10.13 que **BYPASSRLS atraviesa FORCE RLS**.
>
> Es la misma categoría de hallazgo que las tablas `campo_*` sin RLS: el
> aislamiento efectivo hoy es **de aplicación**, no de base.
>
> **B-7 es lo que convierte la RLS de `asistente.*` en un control real.** No es
> solo higiene de permisos: es la diferencia entre una política escrita y una
> política que se aplica.

---

## C. Matriz de roles

**[MEDIDO]** Roles reales (se excluyen los `pg_*` del sistema). **No se creó
ninguno.**

| Rol | LOGIN | SUPER | INHERIT | CREATEROLE | CREATEDB | REPL | BYPASSRLS | Miembro de |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| `postgres` | ✔ | ✘ | ✔ | ✔ | ✔ | ✔ | **✔** | anon, app_backend, asistente_owner, authenticated, authenticator, autonomia_operador, crm_migrator, crm_owner, crm_user, job_executor, monitor_ro, scheduler_coordinator, service_role… |
| `crm_user` | ✔ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `crm_migrator` | ✔ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | **`crm_owner`** (inherit+set) |
| `crm_owner` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `motor_user` | ✔ | ✘ | ✔ | ✘ | ✘ | ✘ | **✔** | **`app_backend`** (inherit+set) |
| `app_backend` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `asistente_owner` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `autonomia_operador` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `job_executor` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `scheduler_coordinator` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |
| `monitor_ro` | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | — |

**[RIESGO]** `motor_user` tiene **`BYPASSRLS = true`**. Es el único rol de runtime
que lo tiene, y **no es obvio que lo necesite**: la RLS de `asistente` filtra por
`org_actual()`, que el motor fija por sesión. **[PENDIENTE]** revisar si puede
quitarse; si se puede, el aislamiento del motor pasa a ser de base.

**[MEDIDO]** SET ROLE, medido con `pg_has_role(..., 'SET')`:

```
crm_migrator  -> crm_owner            SI     (DDL de migraciones: correcto)
postgres      -> autonomia_operador   SI     (único)
postgres      -> app_backend, crm_owner, asistente_owner   SI
ningún otro rol de runtime puede escalar a nada
```

---

## D. Matriz de privilegios

**[MEDIDO]** `has_table_privilege` — **incluye herencia**.
`S`=select `I`=insert `U`=update `D`=delete `T`=truncate

| Objeto | postgres | app_backend | motor_user | crm_user | crm_migrator | autonomia_op | job_exec | sched_coord |
|---|---|---|---|---|---|---|---|---|
| `asistente.tenant_config` | SIUDT | **SIUD** | **SIUD** | — | — | — | — | — |
| `asistente.interruptor_autonomia` | SIUDT | **S** | **S** | — | — | **SI** | — | — |
| `asistente.operaciones_externas` | SIUDT | SIU | SIU | — | — | — | — | — |
| `asistente.audit_log` | SIUDT | SIUD | SIUD | — | — | — | — | — |
| `asistente.acciones_propuestas` | SIUDT | SIUD | SIUD | — | — | — | — | — |
| `asistente.migraciones_aplicadas` | SIUDT | — | — | — | — | — | — | — |
| `asistente.job_schedule_state` | SIUDT | — | — | — | — | — | — | — |
| `public.operaciones_propuesta_supervisor` | SIUDT | — | — | SIUD | SIUDT | — | — | — |
| `public.campo_orden_trabajo` | SIUDT | — | — | SIUDT | SIUDT | — | — | — |
| `public.case` | SIUDT | — | — | SIUDT | SIUDT | — | — | — |
| `public.profile` | SIUDT | — | — | SIUDT | SIUDT | — | — | — |

**[MEDIDO]** EXECUTE sobre funciones de `asistente`:

| Función | SECDEF | Owner | Quién puede ejecutarla |
|---|:--:|---|---|
| `autonomia_detener` | **DEFINER** | postgres | postgres, app_backend, **motor_user**, autonomia_operador |
| `job_claim`, `jobs_vencidos` | DEFINER | asistente_owner | postgres, **scheduler_coordinator** |
| `job_contexto`, `job_finalize`, `job_heartbeat` | DEFINER | asistente_owner | postgres, **job_executor** |
| `job_cerrar_turno`, `job_salud`, `job_slot`, `job_intento_*` | DEFINER/inv | asistente_owner | **solo postgres** |
| `org_actual`, `match_chunks*`, `gasto_del_mes` | invoker | postgres | todos |

**[MEDIDO]** Esquemas:

| Rol | public.USAGE | public.CREATE | asistente.USAGE | asistente.CREATE |
|---|:--:|:--:|:--:|:--:|
| `postgres` | ✔ | ✔ | ✔ | ✔ |
| `app_backend` / `motor_user` | ✔ | **✘** | ✔ | **✘** |
| `crm_user` / `crm_migrator` | ✔ | **✔** | **✘** | ✘ |

**[MEDIDO]** Propiedad: `asistente` → `postgres` (32 tablas) + `asistente_owner`
(5). `public` → `pg_database_owner`, 135 tablas de `crm_owner`.

**Ningún privilegio fue concedido, revocado ni modificado en este paso.**

---

## E. Problemas encontrados

| # | Problema | Clase |
|---|---|---|
| **E-1** | El CRM (backend + 2 celery) corre como `postgres` | **[MEDIDO]** |
| **E-2** | `migrate` corre como `postgres`: no hay `MIGRATOR_DBUSER` configurado | **[MEDIDO]** |
| **E-3** | Mientras el runtime sea `postgres`, puede `SET ROLE autonomia_operador` y **activar autonomía** | **[RIESGO]** |
| **E-4** | La RLS de `asistente.*` **no restringe** al runtime CRM: BYPASSRLS + propiedad de 32 tablas | **[RIESGO]** |
| **E-5** | **`registrar_transicion_autonomia` se romperá** tras B-7 si `crm_user` no puede `SET ROLE autonomia_operador` — hoy funciona porque es `postgres` | **[RIESGO]** |
| **E-6** | `crm_user` y `crm_migrator` tienen **CREATE en `public`** (pendiente de pasos anteriores) | **[MEDIDO]** |
| **E-7** | `motor_user` tiene `BYPASSRLS` sin necesidad evidente | **[PENDIENTE]** |
| **E-8** | No se pudo confirmar qué credencial usan los servicios **desplegados** | **[PENDIENTE]** |

**E-5 es el que puede romper producción en silencio** y es el motivo por el que
este paso es una auditoría y no una ejecución. El camino correcto
(`autonomia_detener()`) **existe y `crm_user` no lo tiene concedido**: hoy
`autonomia_detener` es ejecutable por `postgres`, `app_backend`, `motor_user` y
`autonomia_operador` — **`crm_user` no está en la lista**.

---

## F. Diseño objetivo

**[DISEÑO]** Estado final. Nada de esto está aplicado.

```
  backend / celery-worker / celery-beat   →  crm_user
  migrate (entrypoint)                    →  crm_migrator   (SET ROLE crm_owner)
  motor / motor-reloj                     →  motor_user     [MEDIDO] ya está
  cli/autonomia.py (administración)       →  sesión admin → SET ROLE autonomia_operador
  postgres                                →  FUERA del runtime
```

**[DISEÑO]** Con ese reparto:

| Propiedad | Se obtiene |
|---|---|
| El runtime no puede activar autonomía | ningún rol de runtime puede `SET ROLE autonomia_operador` — **[MEDIDO]** ya es así |
| El runtime no puede hacer DDL | `crm_user` conserva CREATE en `public` → **falta E-6** |
| El runtime no puede tocar `asistente` desde el CRM | `crm_user` no tiene USAGE en `asistente` — **[MEDIDO]** ya es así |
| La RLS pasa a ser efectiva | al dejar de ser dueño y de tener BYPASSRLS |
| El motor conserva lo suyo | sin cambios |

**[DISEÑO]** Y queda una base técnica real para lo de M09-I: una tabla de
autorización en `asistente` a la que `crm_user` **no llega** (sin USAGE) y
`motor_user` solo lee — que es exactamente lo que el modelo necesita.

---

## G. Plan de migración — 14 pasos

**[DISEÑO]** **No se ejecuta ninguno en este paso.**

| # | Paso | Detalle | Reversible |
|:--:|---|---|:--:|
| 1 | **Respaldo** | `pg_dump` completo + verificación de restauración en réplica. Protocolo B.7 ya existente | — |
| 2 | **Preflight** | confirmar en **Dokploy** qué `DBUSER` usa cada servicio (**E-8**); confirmar que existen las contraseñas de `crm_user` y `crm_migrator` | — |
| 3 | **Credenciales** | **no crear roles**: ya existen. Solo confirmar/rotar contraseñas y guardarlas fuera del repositorio | sí |
| 4 | **GRANTs faltantes** | ver G.1 | sí |
| 5 | **Prueba con sesión real** | conectar **como `crm_user`** y como `crm_migrator` y verificar `session_user`. **No usar `postgres` como prueba principal** | — |
| 6 | **Prueba RLS** | con `crm_user`, comprobar que una consulta sin `org_actual()` devuelve **0 filas**, y que con otra organización no ve lo ajeno | — |
| 7 | **Prueba de scheduler** | `job_claim`/`job_finalize` con `scheduler_coordinator`/`job_executor` | — |
| 8 | **Prueba del motor** | sin cambios (ya es `motor_user`); verificar que sigue leyendo y escribiendo `asistente` | — |
| 9 | **Prueba CRM** | migraciones en réplica como `crm_migrator`; DML como `crm_user` | — |
| 10 | **Prueba de autenticación** | login, magic link y JWT con `crm_user` | — |
| 11 | **Cambio de `DBUSER` en entorno controlado** | **primero réplica, después staging. Producción en una ventana acordada** | sí |
| 12 | **Smoke tests** | `cli/diferencias_config.py rapilink` + `cli/evaluar.py rapilink --humo --base` + CRM 401/frontend 200 + kill switch legible | — |
| 13 | **Rollback** | ver I | — |
| 14 | **Recuperación** | restauración desde el respaldo del paso 1 si el rollback no alcanza | — |

### G.1 — GRANTs que faltan **[DISEÑO]**

| # | Qué | Para qué | Riesgo si se omite |
|---|---|---|---|
| G-1 | `GRANT EXECUTE ON asistente.autonomia_detener TO crm_user` | que el CRM pueda ejecutar la parada de emergencia | **E-5**: el CRM no podría detener la autonomía |
| G-2 | Decidir el camino de `cli/autonomia.py` tras B-7 | hoy depende de `SET ROLE` desde `postgres` | la administración del interruptor deja de funcionar |
| G-3 | `REVOKE CREATE ON SCHEMA public FROM crm_user` | quitar DDL al runtime | **E-6** queda abierto |
| G-4 | Revisar `BYPASSRLS` de `motor_user` | **E-7** | la RLS del motor sigue siendo decorativa |

**[PENDIENTE] G-2 es una decisión, no un GRANT.** Dos opciones, y ninguna se
elige aquí:

- **(a)** `cli/autonomia.py` se ejecuta con una credencial administrativa
  separada que sí pueda `SET ROLE autonomia_operador`. No toca código.
- **(b)** El código pasa a llamar `asistente.autonomia_detener()` para detener, y
  reactivar queda **solo** por vía administrativa. Toca código — **fuera del
  alcance de B-7**.

**[DISEÑO]** La (a) mantiene B-7 como un cambio de configuración. La (b) es más
limpia a largo plazo pero convierte B-7 en un cambio de código, con su propio
ciclo de revisión.

---

## H. Pruebas obligatorias

**[DISEÑO]** Todas con **`session_user` real**, nunca con `postgres`: una prueba
de GRANT ejecutada como superusuario adyacente no prueba nada.

### `app_backend` / `motor_user`
| Prueba | Esperado |
|---|---|
| Leer y escribir `tenant_config`, `audit_log`, `acciones_propuestas` | **permitido** |
| `CREATE TABLE` en `asistente` o `public` | **denegado** (sin CREATE) |
| `SET ROLE postgres` / `crm_owner` / `asistente_owner` | **denegado** |
| `SET ROLE autonomia_operador` | **denegado** |
| `INSERT` directo en `interruptor_autonomia` | **denegado** (solo SELECT) |
| `EXECUTE autonomia_detener()` | **permitido** |
| Insertar `estado='activo'` por cualquier vía | **denegado** |

### `crm_user`
| Prueba | Esperado |
|---|---|
| DML sobre `case`, `profile`, `campo_*`, `operaciones_*` | **permitido** |
| Cualquier acceso a `asistente.*` | **denegado** (sin USAGE) |
| `SET ROLE` a cualquier rol privilegiado | **denegado** |
| `CREATE TABLE` en `public` | **denegado tras G-3** |
| RLS: consulta sin `org_actual()` | **0 filas** |
| RLS: consulta con otra organización | **0 filas ajenas** |

### `crm_migrator`
| Prueba | Esperado |
|---|---|
| `python manage.py migrate` en réplica | **permitido** |
| `SET ROLE crm_owner` | **permitido** — **[MEDIDO]** ya lo tiene |
| DML de runtime | **permitido pero no usado**: solo corre en el arranque |
| Acceso a `asistente.*` | **denegado** |

### `postgres`
| Prueba | Esperado |
|---|---|
| No aparece como `session_user` de ningún servicio | **confirmado en Dokploy y en `pg_stat_activity`** |
| Sigue disponible para administración y respaldo | **sí** |

---

## I. Pruebas de falla — todas fail-closed

**[DISEÑO]** El comportamiento correcto ante un fallo de credencial es
**detenerse ruidosamente**, no degradar.

| Escenario | Esperado | **[RIESGO]** a vigilar |
|---|---|---|
| Contraseña incorrecta | el servicio **no arranca**; error visible | que el orquestador reintente en bucle sin alertar |
| Rol inexistente | **no arranca** | — |
| Permiso faltante en runtime | la operación **falla y se registra** | **varias escrituras del motor atrapan el error y solo lo logean** — es el incidente del 18/08/2026, y el síntoma fue silencio |
| RLS bloquea | **0 filas**, nunca filas ajenas | 0 filas puede confundirse con "no hay datos" |
| Tenant incorrecto | **0 filas** | ídem |
| Base caída | el servicio no responde; el kill switch **ilegible ⇒ fail-closed** | — |
| Pool reiniciado | reconexión con la misma credencial; **el contexto RLS debe resetearse** — `settings.py` ya lo hace con `reset_rls_context` | un pool que reutilice contexto es una fuga entre tenants |
| Worker reiniciado | vuelve con su credencial | — |
| Scheduler reiniciado | **[MEDIDO]** 0 trabajos registrados: nada que recuperar | — |

> **[RIESGO] El de mayor probabilidad es "permiso faltante en silencio".** Ya
> ocurrió una vez con esta misma clase de cambio (18/08/2026): al cortar el CRM a
> `crm_user`, el motor quedó sin acceso a `asistente` y **el cliente seguía
> recibiendo respuesta** mientras se perdían mensajes, `tool_calls` y
> conversaciones. **El smoke test del paso 12 debe verificar ESCRITURAS
> persistidas, no solo que la respuesta llegue.**

---

## J. Rollback

**[DISEÑO]**

| Nivel | Acción | Tiempo |
|:--:|---|---|
| **1** | Revertir `DBUSER`/`DBPASSWORD` en Dokploy a los valores anteriores y reiniciar los servicios | minutos |
| **2** | Si el nivel 1 no alcanza: revertir los GRANT de G.1 (todos son `GRANT`/`REVOKE`, ninguno destructivo) | minutos |
| **3** | Restaurar desde el respaldo del paso 1 | según tamaño |

**[DISEÑO]** Propiedades del rollback:

- **B-7 no crea ni borra roles**, no cambia propiedad de objetos y no toca datos.
  Es un cambio de **credencial de conexión** más unos GRANT. Por eso el nivel 1
  alcanza en casi todos los casos.
- **No se hace `DROP` de nada** como mecanismo de reversión.
- El respaldo del paso 1 es el último recurso, no el primero.

**[RIESGO]** Lo que un rollback **no** deshace: las escrituras que no se
persistieron durante la ventana de fallo. Por eso el paso 12 verifica escrituras.

---

## 10. Base técnica para la autonomía — verificación

**[DISEÑO]** No se implementó nada de esto. Se verifica que **después** de B-7
exista la base:

| Pieza del modelo M09-I | ¿La habilita B-7? |
|---|---|
| `nivel_autonomia` por organización | **sí**: tabla en `asistente`, fuera del alcance de `crm_user` |
| `autorizacion_herramienta` | **sí**: el runtime tendría SELECT y nada más; hoy sería DML por ser `postgres` |
| Kill switch | **sí**: pasa a ser el reparto diseñado en 10.11/10.12, en vigor |
| Idempotencia | ya existe; sin cambios |
| Auditoría | ya existe; sin cambios |

> **Sin B-7, la tabla de autorización de M09-I sería un control decorativo**: el
> runtime podría escribirla. Con B-7, no.

---

## 11. Hallazgos M10 — abiertos

**[MEDIDO]** Ninguno resuelto.

| # | Hallazgo | Estado |
|---|---|---|
| 1 | 7 tablas `campo_*` sin RLS ni políticas | **abierto** |
| 2 | 69 de 135 tablas `public` sin política | **abierto** |
| 3 | Aislamiento de OT dependiente del ORM | **abierto** |
| 4 | Defecto B.4 | **abierto** |
| 5 | Ejecutor del motor sin instrumentar | **abierto** |
| 6 | 20 de 27 escrituras sin compuerta propia | **abierto** |
| 7 | El CRM se conecta como `postgres` | **abierto — es el objeto de B-7** |
| 8 | RLS de `asistente.*` inefectiva contra el runtime | **abierto — nuevo aquí** |
| 9 | `motor_user` con `BYPASSRLS` sin necesidad evidente | **abierto — nuevo aquí** |

---

## J. GO / NO-GO para ejecutar B-7

### GO condicionado

El plan es ejecutable y **el riesgo es bajo comparado con lo que resuelve**:
B-7 no crea roles, no cambia propiedad, no toca datos, y su rollback de primer
nivel es revertir dos variables de entorno.

**Tres condiciones bloqueantes antes de ejecutarlo:**

| # | Condición | Por qué bloquea |
|:--:|---|---|
| **1** | **Confirmar en Dokploy qué credencial usa cada servicio desplegado** (E-8) | Todo el plan asume que el CRM está en `postgres`. Está medido en el `.env` del repositorio, **no** en el despliegue. Ejecutar sobre una suposición es exactamente lo que este proyecto no hace |
| **2** | **Decidir G-2**: cómo opera `cli/autonomia.py` tras B-7 | Sin esto, la administración del interruptor deja de funcionar — y el interruptor es el freno de toda la etapa |
| **3** | **Confirmar que existen las contraseñas de `crm_user` y `crm_migrator`** y dónde están | Los roles existen; las credenciales utilizables no se verificaron |

**Y una condición de método:** el paso 12 debe verificar **escrituras
persistidas**, no que la aplicación responda. El incidente del 18/08/2026 pasó
desapercibido justamente porque la aplicación seguía respondiendo.

### Lo que este GO NO autoriza

Ejecutar B-7, cambiar `DBUSER`, modificar permisos, crear roles, tocar
producción, activar autonomía, ni implementar la autorización por herramienta.

**Significa una sola cosa: el plan está suficientemente auditado para que alguien
decida ejecutarlo.**

---

### Anexo — qué se midió

| Medición | Resultado |
|---|---|
| Versión / sesión | PostgreSQL 17.6 · `session_user=postgres` · db `postgres` · puerto 5433 |
| `DBUSER` en `.env` | `postgres.<ref>` |
| `MOTOR_DBUSER` en `.env` | **`motor_user.<ref>`** — el motor ya está migrado |
| `MIGRATOR_DBUSER` | **no configurado** → `migrate` corre con `DBUSER` |
| Roles no-sistema | **25** |
| `motor_user` es miembro de | **`app_backend`**, con `inherit=true` |
| `crm_migrator` es miembro de | `crm_owner`, con `inherit+set` |
| SET ROLE → `autonomia_operador` | **solo `postgres`** |
| CREATE en esquemas | `app_backend`/`motor_user`: **ninguno**; `crm_user`/`crm_migrator`: `public` |
| USAGE en `asistente` | `crm_user`/`crm_migrator`: **no** |
| Propiedad de tablas | `asistente`: postgres 32 + asistente_owner 5 · `public`: crm_owner 135 |
| `autonomia_detener` | `SECURITY DEFINER`, owner `postgres`, `'detenido'` **literal** en el INSERT |
| EXECUTE de `autonomia_detener` | postgres, app_backend, motor_user, autonomia_operador — **`crm_user` NO** |
| Funciones `job_*` | separación real: `scheduler_coordinator` reclama, `job_executor` ejecuta |
| Conexiones vivas | solo Supabase y el pooler; **no se puede inferir el rol de los servicios** |

Producción al cerrar el paso, sin cambios:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · operaciones_externas 0 · 192 django_migrations
tenant_config v146 · 25 roles · {ADMIN: 1, USER: 4}
```
