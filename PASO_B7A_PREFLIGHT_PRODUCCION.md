# PASO B-7A — Preflight para migrar el CRM fuera de `postgres`

**Fecha:** 2026-09-17
**Naturaleza:** **preparación y verificación**. No se cambió `DBUSER`, no se
modificó producción, no se tocó ningún permiso, no se modificó código, no se
crearon migraciones, no se activó nada. Contra producción, **solo lecturas** y
dos peticiones HTTP a páginas públicas.

**Etiquetas:** **[MEDIDO]** · **[DISEÑO]** · **[DEPENDENCIA]** · **[RIESGO]** ·
**[PENDIENTE]**

---

## 0. Lo que este preflight encontró, y por qué cambia el plan

Tres cosas aparecieron al preparar el terreno. La tercera es la que obliga a
reordenar B-7.

**① El corte a `crm_user` ya se hizo una vez, y salió mal.**
**[MEDIDO]** `DESPLIEGUE.md` lo documenta: se activó el 18/08/2026, y como
`DBUSER`/`DBPASSWORD` eran **una sola variable compartida por todo el stack**, el
motor quedó sin acceso al esquema `asistente`. El CRM seguía respondiendo —
`/login` y `/admin/` cargaban— y por eso se dio por bueno. Lo que se perdió, en
silencio, fue todo lo que se intentó persistir en esa ventana: mensajes,
`tool_calls`, conversaciones. **No se puede recuperar lo que no se guardó.**

**② No se pudo verificar qué credencial usa el despliegue.** Ver §1.

**③ Las rutas del motor que mueven el interruptor no pueden funcionar con
`motor_user`.** Ver §3 — es el hallazgo central de este paso.

---

## 1. Credenciales reales de Dokploy

### 1.1 — La matriz

| Servicio | Usuario DB | Fuente de verificación | Estado |
|---|---|---|---|
| `backend` (Django/gunicorn) | `${DBUSER}` → `postgres.<ref>` | **`.env` del repositorio** | **[PENDIENTE]** |
| `celery-worker` | `${DBUSER}` | `.env` del repositorio | **[PENDIENTE]** |
| `celery-beat` | `${DBUSER}` | `.env` del repositorio | **[PENDIENTE]** |
| `migrate` (entrypoint) | `${MIGRATOR_DBUSER}` o `${DBUSER}` | `.env`: **`MIGRATOR_DBUSER` no está** | **[PENDIENTE]** |
| `motor` | `${MOTOR_DBUSER}` → `motor_user.<ref>` | `.env` del repositorio | **[PENDIENTE]** |
| `motor-reloj` | `${MOTOR_DBUSER}` | `.env` del repositorio | **[PENDIENTE]** |
| `frontend` | — (no conecta a la base) | compose | **[MEDIDO]** n/a |
| `redis` | — | compose | **[MEDIDO]** n/a |

**Ningún valor de contraseña fue leído ni se muestra.**

### 1.2 — Por qué todo está en [PENDIENTE]

**[MEDIDO]** El `.env` del repositorio **no es** el entorno de despliegue. Las
variables de producción viven en Dokploy, y desde aquí no se leen:

```
dokploy CLI : no disponible
clave SSH   : no existe (~/.ssh tiene solo known_hosts, 94 bytes)
VPS         : 86.48.18.185 en known_hosts, sin credencial para entrar
```

### 1.3 — Se intentó deducirlo desde la base, y no sirve

**[MEDIDO]** Se muestreó `pg_stat_activity` **255 veces** mientras se generaba
tráfico real contra `agent-api.rapilinksas.co/admin/login/`. Apareció
`postgres`/`Supavisor`, y **esa lectura resultó ser falsa**: al pedir los
detalles, esas tres conexiones tenían `backend_start` a las **01:05:00 y
01:06:49** — el momento exacto en que empezó el muestreo. **Era el pool que
Supavisor abrió para mi propia sesión**, no el CRM.

**[MEDIDO]** Motivo de fondo: `settings.py` fija `CONN_MAX_AGE = 0`, así que
Django abre y cierra una conexión por petición; y Supavisor multiplexa. En
**ningún** muestreo apareció `crm_user`, `motor_user` ni `app_backend`.

> **[RIESGO]** Que `motor_user` **nunca** apareciera, teniendo el motor
> conexiones de trabajo, es en sí una señal de que el `.env` del repositorio
> puede no describir el despliegue. No prueba nada en ninguna dirección: lo
> prueba solo leer Dokploy.

### 1.4 — Procedimiento exacto para cerrar §1 **[DISEÑO]**

En **Dokploy → servicio → Docker Terminal**, uno por servicio. No expone
contraseñas:

```bash
# En backend, celery-worker, celery-beat:
python -c "import os;print('DBUSER =', os.environ.get('DBUSER','<no definida>').split('.')[0]); \
           print('MIGRATOR_DBUSER =', os.environ.get('MIGRATOR_DBUSER','<no definida>').split('.')[0])"

# En motor y motor-reloj:
python -c "import os;print('DBUSER =', os.environ.get('DBUSER','<no definida>').split('.')[0])"
```

Y la comprobación que no admite discusión — **preguntarle a la base quién es**:

```bash
python -c "
import os, psycopg
d=f\"postgresql://{os.environ['DBUSER']}:{os.environ['DBPASSWORD']}@{os.environ['DBHOST']}:{os.environ['DBPORT']}/{os.environ['DBNAME']}?sslmode=disable\"
with psycopg.connect(d) as c: print('session_user =', c.execute('select session_user').fetchone()[0])"
```

**[DEPENDENCIA]** Hasta que esto se ejecute, B-7 no puede empezar: todo el plan
asume un punto de partida que no está demostrado.

---

## 2. `crm_user` y `crm_migrator`

### 2.1 — Existencia y propiedades **[MEDIDO]**

| Rol | LOGIN | SUPER | BYPASSRLS | CREATEROLE | CREATEDB | Miembro de | Veredicto |
|---|:--:|:--:|:--:|:--:|:--:|---|:--:|
| `crm_user` | ✔ | ✘ | **✘** | ✘ | ✘ | — | **correcto** |
| `crm_migrator` | ✔ | ✘ | **✘** | ✘ | ✘ | **`crm_owner`** (inherit+set) | **correcto** |

**[MEDIDO]** Privilegios ya verificados:

- `crm_user`: DML sobre `public` (`case`, `profile`, `campo_*`, `operaciones_*`);
  **sin USAGE sobre `asistente`** — no puede tocar el esquema del motor.
- `crm_migrator`: DML + `SET ROLE crm_owner`, que es lo que habilita el DDL de
  las migraciones (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` exige ser dueño).

**[MEDIDO]** `DESPLIEGUE.md` documenta que `crm_user` ya fue probado contra la
base real el 18/08/2026: `manage_rls --verify-user` confirmó
`Is superuser: False`, y el fail-safe de RLS funcionó — **0 filas sin contexto**.

### 2.2 — Las credenciales NO están en el mecanismo de secretos

**[MEDIDO]** `asistente.tenant_secrets` contiene **solo credenciales de APIs
externas**:

```
BOTTLECRM_API_TOKEN · IMPORTACION_API_TOKEN · SMARTOLT_API_KEY
WHATSAPP_APP_SECRET · WHATSAPP_PHONE_NUMBER_ID · WHATSAPP_TOKEN
WHATSAPP_VERIFY_TOKEN · WHATSAPP_WABA_ID · WISPHUB_API_KEY
```

**Ninguna credencial de base de datos.** Y está bien que sea así: para leer esa
tabla hay que estar ya conectado a la base. Una credencial de conexión guardada
dentro de la base que abre es un círculo que no cierra.

**[DISEÑO]** Por lo tanto las contraseñas de `crm_user` y `crm_migrator` viven —y
deben vivir— **solo en las variables de Dokploy**, nunca en código ni en el
repositorio.

**[PENDIENTE]** Confirmar que existen y son utilizables. No se puede verificar
desde aquí sin la contraseña, y **este paso no las pide ni las rota**.

---

## 3. G-2 — Detener la autonomía después del corte

### 3.1 — Quién mueve el interruptor, medido

**[MEDIDO]** **Django nunca lo toca.** Las diez referencias en `django-crm/` son
comentarios y pruebas; ninguna función lo escribe. Y hay una prueba que lo
vigila: `test_el_supervisor_no_puede_tocar_permisos_ni_autonomia`.

**[MEDIDO]** Quien lo mueve son dos caminos, los dos del **motor**:

```
cli/autonomia.py:112        → interruptor.detener / interruptor.reactivar
nucleo/canales/api.py:2972  → POST /autonomia/detener
nucleo/canales/api.py:2978  → POST /autonomia/reactivar
```

**[MEDIDO]** Los dos terminan en `db.registrar_transicion_autonomia`, que abre la
sesión con `rol=ROL_OPERADOR_AUTONOMIA`, es decir hace
**`SET LOCAL ROLE autonomia_operador`** y después inserta.

### 3.2 — El problema, con nombre y apellido

**[MEDIDO]**

```
pg_has_role('motor_user','autonomia_operador','SET')  =  FALSE
pg_has_role('app_backend','autonomia_operador','SET') =  FALSE
solo postgres puede hacer ese SET ROLE
```

> **[RIESGO] Por lo tanto, hoy solo puede ser cierta una de estas dos cosas:**
>
> **(a)** el motor está desplegado como `postgres` → **el runtime puede
> reactivar la autonomía por su cuenta** (es E-3 de B-7); **o**
>
> **(b)** el motor está desplegado como `motor_user` → **`POST /autonomia/detener`
> y `/autonomia/reactivar` ya están rotos en producción**, y la parada de
> emergencia por HTTP no funciona.
>
> Las dos son graves y las dos se resuelven mirando Dokploy (§1). **No se puede
> ejecutar B-7 sin saber cuál de las dos es.**

**[MEDIDO]** `cli/autonomia.py` tiene el mismo problema: corre con el `.env`
local, y si ese `DBUSER` deja de ser `postgres`, deja de poder mover el
interruptor.

### 3.3 — Las tres alternativas

| | Alternativa | Detener funciona | Runtime NO puede activar | Toca código |
|---|---|:--:|:--:|:--:|
| **A** | Credencial administrativa separada para la CLI | solo por CLI | ✔ | no |
| **B** | Llamar `asistente.autonomia_detener()` | **✔ por CLI y HTTP** | **✔** | **sí, mínimo** |
| **C** | Reutilizar otro mecanismo existente | — | — | — |

**[MEDIDO]** Sobre **C**: no hay otro mecanismo. Las funciones `job_*` resuelven
la separación del scheduler, no la del interruptor.

### 3.4 — Recomendación **[DISEÑO]**

> **B para detener, A para activar.**

**[MEDIDO]** La función ya existe y ya está concedida a quien hace falta:

```
asistente.autonomia_detener(uuid, text, text) → asistente.interruptor_autonomia
  SECURITY DEFINER, owner = postgres
  cuerpo: el estado 'detenido' está ESCRITO LITERAL — no admite 'activo'
  EXECUTE: postgres ✔  app_backend ✔  motor_user ✔  autonomia_operador ✔
           crm_user ✘   (y no lo necesita: Django no toca el interruptor)
```

**[DISEÑO]** El cambio: que `interruptor.detener()` llame a esa función en vez de
hacer `SET ROLE` + INSERT. `reactivar()` **no** cambia — sigue exigiendo
`SET ROLE autonomia_operador`, que solo una sesión administrativa puede hacer.

Con eso se cumple lo que el §3 exige, punto por punto:

| Requisito | Se cumple porque |
|---|---|
| Detener es posible | `motor_user` ya tiene EXECUTE sobre la función |
| Activar no queda disponible para el runtime | `reactivar` exige `SET ROLE`, que el runtime no puede |
| La IA no puede activar | no hay ninguna herramienta que escriba el interruptor |
| `app_backend` no puede activar | solo SELECT sobre la tabla; sin `SET ROLE` |
| `motor_user` no puede activar | ídem |
| `crm_user` no puede activar directamente | sin USAGE sobre `asistente` |
| `autonomia_operador` conserva lo necesario | sigue siendo la vía administrativa |

**[MEDIDO]** Y no es una idea nueva: `db.py` ya lo dice en su propio docstring —
*"Al runtime le quedan DOS cosas y ninguna más: LEER el estado, y la parada de
emergencia `asistente.autonomia_detener()`, cuyo cuerpo tiene el estado escrito y
no admite 'activo' por ninguna vía."* **El diseño está escrito; el código todavía
no lo sigue.**

**[DEPENDENCIA]** Es un cambio de código. **Fuera del alcance de B-7**, y debe ir
**antes** — un B-7B propio, con su revisión.

---

## 4. Preflight de privilegios — actual vs objetivo

**[MEDIDO]** actual · **[DISEÑO]** objetivo · **Nada se modificó.**

| Rol | Hoy | Objetivo | Diferencia |
|---|---|---|---|
| `crm_user` | DML `public`; **CREATE en public**; sin `asistente`; sin BYPASSRLS | igual **menos CREATE** | **REVOKE CREATE ON SCHEMA public** |
| `crm_migrator` | DML `public` + `SET ROLE crm_owner`; **CREATE en public** | igual — **lo necesita** | ninguna |
| `app_backend` | DML `tenant_config`/`audit_log`/`acciones_propuestas`; SELECT interruptor; SIU `operaciones_externas`; sin CREATE | igual | ninguna |
| `motor_user` | hereda `app_backend`; **BYPASSRLS ✔** | igual **menos BYPASSRLS** | **[PENDIENTE]** revisar si se puede quitar |
| `job_executor` | EXECUTE `job_contexto`/`job_finalize`/`job_heartbeat` | igual | ninguna |
| `scheduler_coordinator` | EXECUTE `job_claim`/`jobs_vencidos` | igual | ninguna |
| `autonomia_operador` | INSERT+SELECT interruptor; EXECUTE `autonomia_detener` | igual | ninguna |
| `postgres` | todo | **fuera del runtime**, solo administración y respaldo | cambiar `DBUSER` |

**[DISEÑO]** Cambios de privilegio en B-7: **uno solo** — `REVOKE CREATE ON
SCHEMA public FROM crm_user`. Todo lo demás ya está en su sitio. Es la medida de
lo bien preparado que está el terreno, y también de lo poco que B-7 explica por
sí solo: **el trabajo está en la verificación, no en los GRANT.**

---

## 5. Riesgo de RLS — qué no es efectivo hoy

**[MEDIDO]** `postgres` tiene `BYPASSRLS` y es **dueño de 32 de las 37 tablas**
de `asistente`. En el paso 10.13 quedó medido que **BYPASSRLS atraviesa FORCE
RLS**.

**[MEDIDO]** `DESPLIEGUE.md` documenta algo peor que el hueco: **la propia
herramienta de diagnóstico miente.** `manage_rls --status` solo mira `usesuper`,
y en Supabase `postgres` tiene `rolsuper=false` con `rolbypassrls=true` — reporta
*"RLS will be enforced"* y es **falso**. Las 60 tablas de `ORG_SCOPED_TABLES`
tienen su política `ENABLED (forced)` y no protegen nada.

**[DISEÑO]** Lo que pasa a ser comprobable **después** de B-7:

| Control | Prueba |
|---|---|
| Aislamiento por organización | sin `app.current_org` → **0 filas** |
| SELECT | con org A no se ve nada de org B |
| INSERT | insertar con org ajena → rechazado por `WITH CHECK` |
| UPDATE | no se puede mover una fila a otra org |
| DELETE | no se puede borrar lo ajeno |
| Funciones `SECURITY DEFINER` | siguen funcionando con el rol degradado |
| Tablas de `asistente` | `crm_user` no llega (sin USAGE) |
| `tenant_config` | `crm_user` no llega; `motor_user` sí, acotado |
| Interruptor | `crm_user` no llega; runtime solo SELECT |
| Idempotencia | `operaciones_externas` acotada por org |
| Auditoría | `audit_log` acotada por org |

> **B-7 no es higiene de permisos: es lo que convierte la RLS de `asistente.*` y
> de las 60 tablas del CRM en un control real en vez de una política escrita.**

---

## 6. Backup

**[MEDIDO]** El procedimiento **ya existe y está probado**:
`B7_PROTOCOLO_RESPALDO.md` (17/09/2026), con la lección cara ya incorporada —
*se restauró cuatro veces con `pg_restore` en 0 y las cuatro dejaron un scheduler
roto, porque todas las verificaciones comprobaban que los objetos existieran.*

**[MEDIDO]** Respaldos previos disponibles: `respaldo_b8`, `respaldo_p103`,
`respaldo_p105`, `respaldo_p105_archivos`, `respaldo_p1013`, `respaldo_p1013_post`,
`respaldo_p1013d`.

**[DISEÑO]** Para B-7:

| Punto | Definición |
|---|---|
| Qué se respalda | esquemas `public`, `asistente` y **`asistente_ledger`** — el tercero no es prescindible: `migraciones_aplicadas` tiene disparadores que llaman a `asistente_ledger.solo_agregar()` y sin él la restauración aborta |
| Qué **no** | la base completa: `pg_net`, `supabase_vault` y compañía son binarios de plataforma y no restauran en un PostgreSQL normal |
| Roles | volcado aparte de roles y grants (contiene **hashes SCRAM**: almacenamiento seguro, fuera del repositorio) |
| Dónde | `C:\Users\Usuario\respaldo_b7\<AAAAMMDD_HHMMSS>\`, fuera del repositorio |
| Cómo se verifica | **restaurándolo en un contenedor limpio** y comprobando **comportamiento**, no existencia: el scheduler reclama un turno, el ledger acepta un append y rechaza un update, el interruptor se lee |
| Cómo se restaura | el procedimiento de B.7 §5 |
| Utilizable antes del cambio | la verificación de arriba corre **antes** de tocar Dokploy |

**[MEDIDO]** Un respaldo es una **lectura**: no modifica producción. Se puede
ejecutar cuando se autorice B-7 sin riesgo añadido. **No se ejecutó aquí.**

---

## 7. Smoke tests — persistencia real, no HTTP 200

**[DISEÑO]** La regla, que viene del incidente del 18/08/2026:

> **HTTP 200, un JSON correcto o una pantalla que carga NO son evidencia.** Ese
> día el CRM respondía perfecto mientras se perdía todo lo que intentaba
> escribirse. Cada prueba tiene que cerrar el círculo:
>
> `petición → escritura → COMMIT → SELECT posterior desde OTRA conexión → la fila está`

| # | Operación | Verificación de persistencia |
|:--:|---|---|
| 1 | Login | `SELECT` de la sesión/refresh token creado |
| 2 | Lectura CRM | conteo de `case` coincide con el `SELECT` directo |
| 3 | **Crear un Case** | `SELECT` por id desde otra conexión → existe |
| 4 | **Actualizar ese Case** | `SELECT` → el campo cambió |
| 5 | **Activity** | `SELECT` → la fila de auditoría existe, con `org` y `user` |
| 6 | Conversación (motor) | `SELECT` en `asistente.mensajes`/`conversaciones` → la fila está |
| 7 | **`tool_calls`** | `SELECT` → quedó el metadato. **Es el que falló en silencio el 18/08** |
| 8 | `tenant_config` lectura | `config_version` = **146** |
| 9 | Auditoría del motor | `SELECT` en `asistente.audit_log` |
| 10 | **Kill switch** | se **lee** y devuelve `detenido`. **No se mueve** |
| 11 | Operación del motor | una herramienta de **solo lectura**; 0 escrituras externas |
| 12 | Scheduler | `job_salud` responde; **[MEDIDO]** 0 trabajos registrados |
| 13 | Workers | una tarea Celery que escriba, y su `SELECT` posterior |

**[DISEÑO]** Datos controlados y reversibles: un Case con marca `B7A-SMOKE-<ts>`,
borrado al terminar. **Nada sobre datos reales de clientes.**

**[RIESGO]** La 7 es la prueba decisiva. Varias escrituras del motor **atrapan la
excepción y solo la logean, a propósito**, para no tumbarle la respuesta a un
cliente por un problema de auditoría. Esa decisión es correcta y es justo la que
vuelve invisible un fallo de permisos.

---

## 8. Pruebas de seguridad

**[DISEÑO]** Todas con **`session_user` real**. Una prueba de GRANT ejecutada
como `postgres` no prueba nada — es la lección del paso 10.13D.

| # | Intento | Esperado | Ya medido |
|:--:|---|---|:--:|
| 1 | `crm_user` → `CREATE TABLE` en `public` | **denegado** | tras REVOKE |
| 2 | `crm_user` → `SET ROLE autonomia_operador` | **denegado** | **✔ `pg_has_role`=false** |
| 3 | `crm_user` → activar autonomía | **denegado** | **✔ sin USAGE en `asistente`** |
| 4 | `app_backend` → activar autonomía | **denegado** | **✔ solo SELECT + sin SET ROLE** |
| 5 | `motor_user` → activar autonomía | **denegado** | **✔ ídem** |
| 6 | `motor_user` → `autonomia_detener()` | **permitido** | **✔ EXECUTE concedido** |
| 7 | runtime → modificar autorización de herramienta | **denegado** | **[DEPENDENCIA]** la tabla no existe |
| 8 | `crm_user` → leer `asistente.tenant_config` | **denegado** | **✔ sin USAGE** |
| 9 | `crm_user` → `SET ROLE postgres`/`crm_owner` | **denegado** | **✔** |
| 10 | `postgres` fuera del runtime | ningún servicio lo usa | **[PENDIENTE]** §1 |

**[MEDIDO]** Siete de las diez ya están demostradas por la matriz de privilegios.
Lo que falta probar con sesión real es que la teoría se cumple en la práctica.

---

## 9. Plan de cambio — 12 pasos

**[DISEÑO]** **No se ejecuta ninguno.**

| # | Paso | Detalle | Detiene el plan si falla |
|:--:|---|---|:--:|
| 0 | **Cerrar §1** | leer Dokploy con el procedimiento de 1.4 | **sí** |
| 0b | **Cerrar G-2** | el cambio de código de §3.4 (B-7B), revisado y desplegado | **sí** |
| 1 | **Backup** | §6, los tres esquemas + roles | **sí** |
| 2 | **Validar backup** | restaurar en contenedor limpio y probar **comportamiento** | **sí** |
| 3 | **Preflight** | matriz de §4 verificada; contraseñas disponibles | **sí** |
| 4 | **Cambio de `DBUSER`** | **primero réplica, luego staging.** Producción en ventana acordada, con `MIGRATOR_DBUSER=crm_migrator` puesto **a la vez** | — |
| 5 | **Reinicio de servicios** | backend, celery-worker, celery-beat. **El motor no se toca** | — |
| 6 | **Prueba de conexión** | `session_user` = `crm_user` en cada uno | **sí** |
| 7 | **Smoke tests** | las 13 de §7 | **sí** |
| 8 | **Pruebas de persistencia** | especialmente la 7 (`tool_calls`) | **sí** |
| 9 | **Pruebas de RLS** | las 11 de §5 | **sí** |
| 10 | **Pruebas de autonomía** | las 10 de §8 | **sí** |
| 11 | **Validación de servicios** | `cli/diferencias_config.py rapilink` + `cli/evaluar.py rapilink --humo --base` + CRM/frontend | **sí** |
| 12 | **GO/NO-GO final** | si algo falló: rollback §10 | — |

**[DISEÑO]** Dos decisiones de secuencia que importan:

- **`MIGRATOR_DBUSER` se pone en el mismo cambio que `DBUSER`.** Si no, el
  siguiente despliegue corre `migrate` como `crm_user`, que no es dueño, y una
  migración que llame `get_enable_policy_sql()` fallaría. **[MEDIDO]** está
  documentado en `DESPLIEGUE.md` como la decisión que quedó pendiente.
- **El motor no se toca en B-7.** Ya usa `MOTOR_DBUSER`. Cambiar dos cosas a la
  vez fue exactamente lo que hizo indetectable el incidente del 18/08.

---

## 10. Rollback

**[DISEÑO]**

| | |
|---|---|
| **Condición que obliga** | cualquier paso marcado "detiene el plan"; o **una sola escritura que no persista** |
| **Cómo restaurar** | revertir `DBUSER`/`DBPASSWORD` (y `MIGRATOR_DBUSER`) en Dokploy a los valores anteriores — **anotados antes de tocarlos** |
| **Qué reiniciar** | `backend`, `celery-worker`, `celery-beat`. El motor no se tocó |
| **Cómo verificar** | repetir §7 completo. **No basta con que la pantalla cargue** |
| **Evidencia a conservar** | valores anteriores, hora exacta del cambio y del rollback, salida de los 13 smoke tests, logs de los servicios en la ventana, y **la lista de escrituras que se perdieron** |

**[DISEÑO]** Propiedades:

- El rollback de primer nivel son **dos variables de entorno y un reinicio**:
  minutos.
- B-7 **no crea ni borra roles**, no cambia propiedad de objetos, no toca datos.
  El único cambio de privilegio es un `REVOKE`, que se revierte con un `GRANT`.
- **No se hace `DROP` de nada** como mecanismo de reversión.
- El respaldo del paso 1 es el **último** recurso.

**[RIESGO]** Lo que el rollback **no** deshace: las escrituras perdidas durante la
ventana de fallo. Es exactamente lo que pasó el 18/08 y no se pudo recuperar. Por
eso el paso 8 es bloqueante y por eso la ventana debe ser corta y vigilada.

---

## 11. Criterios GO / NO-GO

| # | Condición | Estado | Crítica |
|:--:|---|---|:--:|
| 1 | Credenciales verificadas **en Dokploy** | **NO DEMOSTRADA** | **sí** |
| 2 | Servicios identificados con su usuario real | **NO DEMOSTRADA** | **sí** |
| 3 | **G-2 resuelto** | **[DISEÑO] propuesto, código NO cambiado** | **sí** |
| 4 | Backup disponible y verificable | **[MEDIDO]** procedimiento existe y está probado | sí |
| 5 | Rollback documentado | **[DISEÑO]** §10 | sí |
| 6 | Privilegios esperados definidos | **[MEDIDO]** §4; un solo REVOKE | sí |
| 7 | Smoke tests definidos | **[DISEÑO]** §7, 13 pruebas | sí |
| 8 | Persistencia comprobable | **[DISEÑO]** §7 | sí |
| 9 | Sin dependencia de runtime sobre `postgres` | **[MEDIDO]** B-7 §B: ninguna clase A | sí |
| 10 | Contraseñas de `crm_user`/`crm_migrator` disponibles | **NO DEMOSTRADA** | **sí** |

### Veredicto

## NO-GO

**Cuatro condiciones críticas no están demostradas** (1, 2, 3, 10). El criterio
del encargo es explícito: *cualquier condición crítica no demostrada ⇒ NO-GO*.

**Lo que NO significa este NO-GO:** que el plan esté mal o que falte trabajo de
diseño. El terreno está notablemente preparado — los roles existen y están bien
acotados, el compose ya separa los servicios, el protocolo de respaldo está
probado, y el único cambio de privilegio necesario es **un `REVOKE`**.

**Lo que sí significa:** que faltan **dos verificaciones y un cambio de código**,
y ninguno de los tres se puede hacer en este paso:

| # | Para pasar a GO hace falta | Quién |
|:--:|---|---|
| 1 | Leer en Dokploy el `DBUSER` de los 5 servicios (§1.4) | humano con acceso |
| 2 | Confirmar que existen las contraseñas de `crm_user` y `crm_migrator` | humano con acceso |
| 3 | **B-7B**: que `interruptor.detener()` use `asistente.autonomia_detener()` (§3.4) | paso propio, con revisión |

**[RIESGO]** Y una alarma que no debe esperar a B-7: **hoy, o el runtime puede
reactivar la autonomía, o la parada de emergencia por HTTP está rota** (§3.2).
No se sabe cuál, y saberlo solo cuesta leer una variable en Dokploy.

---

## 12. M10 — abiertos

**[MEDIDO]** Ninguno resuelto.

| # | Hallazgo | Estado |
|---|---|---|
| 1 | 7 tablas `campo_*` sin RLS ni políticas | **abierto** |
| 2 | 69 de 135 tablas `public` sin política | **abierto** |
| 3 | Aislamiento de OT dependiente del ORM | **abierto** |
| 4 | Defecto B.4 | **abierto** |
| 5 | Ejecutor del motor sin instrumentar | **abierto** |
| 6 | 20 de 27 escrituras sin compuerta propia | **abierto** |
| 7 | El CRM se conecta como `postgres` | **abierto — objeto de B-7** |
| 8 | RLS de `asistente.*` inefectiva contra el runtime | **abierto** |
| 9 | `motor_user` con `BYPASSRLS` sin necesidad evidente | **abierto** |
| 10 | `manage_rls --status` **diagnostica mal** en Supabase | **abierto — nuevo aquí** |
| 11 | Las rutas `/autonomia/*` del motor: o el runtime puede activar, o están rotas | **abierto — nuevo aquí** |

---

## A. Checklist de preflight

| | Ítem | Estado |
|:--:|---|---|
| ☐ | `DBUSER` real de `backend` leído en Dokploy | **pendiente** |
| ☐ | `DBUSER` real de `celery-worker` y `celery-beat` | **pendiente** |
| ☐ | `MIGRATOR_DBUSER` presente o ausente, confirmado | **pendiente** |
| ☐ | `DBUSER` real de `motor` y `motor-reloj` | **pendiente** |
| ☐ | Contraseñas de `crm_user` y `crm_migrator` disponibles | **pendiente** |
| ☑ | `crm_user` existe, sin BYPASSRLS ni SUPERUSER | **[MEDIDO]** |
| ☑ | `crm_migrator` existe y puede `SET ROLE crm_owner` | **[MEDIDO]** |
| ☑ | `crm_user` sin USAGE sobre `asistente` | **[MEDIDO]** |
| ☑ | Ninguna dependencia de runtime sobre `postgres` | **[MEDIDO]** |
| ☑ | Único cambio de privilegio: `REVOKE CREATE ... FROM crm_user` | **[MEDIDO]** |
| ☑ | Protocolo de respaldo existente y probado | **[MEDIDO]** |
| ☑ | Smoke tests con verificación de persistencia definidos | **[DISEÑO]** |
| ☑ | Rollback definido y rápido | **[DISEÑO]** |
| ☐ | **G-2 implementado (B-7B)** | **pendiente** |

## B. Resolución de G-2

**[DISEÑO]** `interruptor.detener()` pasa a llamar
`asistente.autonomia_detener(org, actor, motivo)` — `SECURITY DEFINER`, con
`'detenido'` escrito literal y `EXECUTE` ya concedido a `motor_user` y
`app_backend`. `reactivar()` **no cambia**: sigue exigiendo
`SET ROLE autonomia_operador`, que ningún rol de runtime puede hacer.

Resultado: **detener funciona desde el runtime; activar no.** Es la asimetría que
el diseño pedía, y el propio `db.py` ya la describe como la intención.

**Es un cambio de código: va en un paso propio (B-7B), antes de B-7.**

## C. Plan exacto de ejecución B-7

§9 — 12 pasos, con dos previos bloqueantes (§1 y G-2) y la regla de no cambiar
el motor en el mismo movimiento.

## D. Plan de rollback

§10 — dos variables de entorno y un reinicio; verificación por persistencia, no
por disponibilidad.

## E. Criterios GO/NO-GO

§11 — **NO-GO**: 4 de 10 condiciones críticas no demostradas.

## F. Riesgos abiertos

| # | Riesgo |
|---|---|
| **R-1** | **Hoy o el runtime puede activar autonomía, o la parada por HTTP está rota** — no se sabe cuál |
| R-2 | El `.env` del repositorio puede no describir el despliegue **en ninguna dirección** |
| R-3 | Un fallo de permisos se manifiesta como **silencio**, no como error: ya pasó el 18/08/2026 |
| R-4 | `manage_rls --status` reporta que la RLS se aplica cuando no |
| R-5 | `MIGRATOR_DBUSER` ausente: el próximo despliegue correría `migrate` como `crm_user` |
| R-6 | `motor_user` con `BYPASSRLS` sin necesidad evidente |
| R-7 | Los nueve hallazgos M10 previos, todos abiertos |

---

### Anexo — qué se midió

| Medición | Resultado |
|---|---|
| Acceso a Dokploy | **ninguno**: sin CLI, sin clave SSH |
| Muestreo de `pg_stat_activity` con tráfico real | 255 muestras; **ningún rol de aplicación identificable** |
| Las 3 conexiones `postgres` capturadas | `backend_start` 01:05–01:06 = **el pool de mi propia sesión**, no el CRM |
| `CONN_MAX_AGE` | **0** — Django no mantiene conexiones entre peticiones |
| `asistente.tenant_secrets` | 9 secretos, **todos de APIs externas**; ninguna credencial de base |
| `crm_user` / `crm_migrator` | existen; sin SUPERUSER ni BYPASSRLS; `crm_migrator` → `SET ROLE crm_owner` ✔ |
| Referencias de Django al interruptor | **ninguna funcional** (comentarios y pruebas) |
| Quién mueve el interruptor | `cli/autonomia.py` y **2 rutas HTTP del motor** |
| `SET ROLE autonomia_operador` | **solo `postgres`** |
| `autonomia_detener(uuid,text,text)` | SECURITY DEFINER, owner postgres, `'detenido'` literal; EXECUTE: postgres, app_backend, **motor_user**, autonomia_operador; **crm_user no** |
| Servicios en línea | CRM `/admin/` → 302 · frontend `/login` → 200 · motor → responde (404 en rutas probadas) |
| Respaldos disponibles | 7 carpetas previas + protocolo B.7 probado |

Producción al cerrar el paso, sin cambios:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · operaciones_externas 0 · 192 django_migrations
tenant_config v146 · 25 roles · {ADMIN: 1, USER: 4}
```
