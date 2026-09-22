# PASO B-7B — Identidad real de credenciales y usuarios DB en producción

**Fecha:** 2026-09-17
**Naturaleza:** **identificación con evidencia directa**. No se cambió `DBUSER`,
no se modificaron permisos, no se tocó código, no se crearon migraciones, no se
activó autonomía, no se movió el kill switch, no se ejecutó ninguna herramienta
externa. **Ninguna contraseña fue leída, mostrada ni guardada.**

**Etiquetas:** **[MEDIDO]** · **[NO DEMOSTRADO]** · **[DEPENDENCIA]** ·
**[RIESGO]** · **[PENDIENTE]**

---

## A. Evidencia de Dokploy

### A.1 — No existe ninguna vía de acceso desde este entorno

**[MEDIDO]** Se agotaron sistemáticamente todas las posibilidades:

| Vía | Resultado |
|---|---|
| CLI `dokploy` | **no instalada** |
| Contexto Docker remoto | **ninguno** — `default` y `desktop-linux`, ambos locales (`npipe://`) |
| `DOCKER_HOST` apuntando al VPS | **no definido** |
| Clave SSH privada | **no existe** — `~/.ssh` contiene solo `known_hosts` (94 bytes) |
| `ssh-agent` | **no hay agente** (`Could not open a connection to your authentication agent`) |
| Token o config de Dokploy | **ninguno** en entorno ni en el repositorio |
| Panel de Dokploy | **responde** (`http://86.48.18.185:3000` → HTTP 200) |

**[MEDIDO]** El VPS `86.48.18.185` está en `known_hosts` — alguien se conectó
alguna vez desde esta máquina — pero **la clave privada no está**.

> **No intenté autenticarme contra el panel de Dokploy.** No tengo credenciales,
> y probar credenciales contra un panel de administración de producción no es una
> lectura: es un intento de acceso. Queda como lo que es: **[NO DEMOSTRADO]**.

### A.2 — Docker Terminal: el procedimiento, listo para ejecutar

**[PENDIENTE]** Debe ejecutarlo una persona con acceso al panel.
**Dokploy → servicio → Docker Terminal.** Ninguno de estos comandos muestra
contraseñas ni modifica nada.

**Paso 1 — la variable declarada** (en `backend`, `celery-worker`, `celery-beat`,
`motor`, `motor-reloj`):

```bash
python -c "
import os
for v in ('DBUSER','MIGRATOR_DBUSER','MOTOR_DBUSER'):
    x = os.environ.get(v)
    print(f'{v:18} = ' + (x.split('.')[0] if x else '<no definida>'))
print('DBHOST           =', os.environ.get('DBHOST','<no definida>'))
print('DBNAME           =', os.environ.get('DBNAME','<no definida>'))
"
```

**Paso 2 — la verificación que no admite discusión: preguntarle a la base quién
es.** Es lo que pide el §3 del encargo:

```bash
python -c "
import os, psycopg
d = (f\"postgresql://{os.environ['DBUSER']}:{os.environ['DBPASSWORD']}\"
     f\"@{os.environ['DBHOST']}:{os.environ['DBPORT']}/{os.environ['DBNAME']}?sslmode=disable\")
with psycopg.connect(d) as c:
    r = c.execute('''select current_user, session_user,
                            coalesce(current_setting('role', true),'none'),
                            coalesce(inet_server_addr()::text,'-'),
                            coalesce(inet_server_port()::text,'-')''').fetchone()
    print('current_user =', r[0]); print('session_user =', r[1])
    print(\"current_setting('role') =\", r[2])
    print('inet_server_addr =', r[3]); print('inet_server_port =', r[4])
"
```

**[MEDIDO]** La contraseña se toma del entorno y **nunca se imprime**. La salida
esperada, según el formato de referencia medido desde este entorno:

```
current_user            = <rol>
session_user            = <rol>
current_setting('role') = none
inet_server_addr        = 172.20.0.4/32
inet_server_port        = 5432
```

**[MEDIDO]** Nota sobre esos dos últimos: conectando al **puerto 5433**
(Supavisor), `inet_server_port()` devuelve **5432** y la dirección es la interna
del contenedor de Postgres. **`inet_server_*` describe el servidor final, no el
pooler** — no sirve para distinguir por dónde entró la conexión, y por eso el
dato que importa es `session_user`.

---

## B. Identidad DB de cada servicio

### B.1 — El mapa real

| Servicio | Usuario real | Evidencia | ¿postgres? | Rol esperado | Estado |
|---|---|---|:--:|---|---|
| **Django/Web** (`backend`) | **desconocido** | solo `.env` del repo: `postgres.<ref>` | **?** | `crm_user` | **[NO DEMOSTRADO]** |
| **Workers** (`celery-worker`) | **desconocido** | `.env`: comparte `${DBUSER}` | **?** | `crm_user` | **[NO DEMOSTRADO]** |
| **Scheduler** (`celery-beat`) | **desconocido** | `.env`: comparte `${DBUSER}` | **?** | `crm_user` | **[NO DEMOSTRADO]** |
| **Migraciones** (`entrypoint`) | **desconocido** | `.env`: `MIGRATOR_DBUSER` **ausente** → usaría `${DBUSER}` | **?** | `crm_migrator` | **[NO DEMOSTRADO]** |
| **Motor** | **desconocido** | `.env`: `MOTOR_DBUSER = motor_user.<ref>` | **?** | `motor_user` | **[NO DEMOSTRADO]** |
| **Motor-reloj** | **desconocido** | `.env`: comparte `${MOTOR_DBUSER}` | **?** | `motor_user` | **[NO DEMOSTRADO]** |
| `frontend` | — no conecta a la base | compose | — | — | **[MEDIDO]** n/a |
| `redis` | — | compose | — | — | **[MEDIDO]** n/a |

| Campo | Valor |
|---|---|
| Fecha/hora de medición | **2026-09-17, 01:05–01:20** |
| Fuente única disponible | `.env` del repositorio |
| Autoridad de esa fuente | **ninguna** sobre el despliegue |

### B.2 — Por qué no se puede deducir

**[MEDIDO]** El `.env` del repositorio es el archivo de desarrollo local. Las
variables de producción viven en Dokploy y **no se leen desde aquí** (A.1).

**[RIESGO]** Y hay una señal concreta de que podrían diferir: `.env` declara
`MOTOR_DBUSER = motor_user`, pero en **255 muestreos** de `pg_stat_activity` con
tráfico real **nunca apareció una conexión de `motor_user`** — y el motor
mantiene conexiones de trabajo. Eso no prueba que el motor no use `motor_user`
(ver C), pero tampoco lo confirma.

---

## C. Pooler vs conexión real — qué se puede y qué no

Esta sección existe porque en B-7A yo mismo saqué una conclusión equivocada de
`pg_stat_activity`, y conviene que quede medido por qué no sirve.

### C.1 — El error de B-7A, y su corrección

**[MEDIDO]** En B-7A muestreé 255 veces con tráfico real y reporté *"roles de
aplicación capturados: `['postgres']`"*. Al pedir los detalles, las tres
conexiones tenían `backend_start` a las **01:05:00 y 01:06:49** — el momento
exacto en que arrancó el muestreo. **Eran mías, no del CRM.** La conclusión era
falsa y queda descartada.

### C.2 — El experimento controlado

**[MEDIDO]** Abrí conexiones cliente adicionales y conté las filas:

```
A) solo el observador (1 cliente)       -> filas con usename=postgres = 1
B) +3 conexiones cliente abiertas       -> filas con usename=postgres = 1   ← no cambió
C) las 3 cerradas hace 2s               -> filas = 1
D) las 3 cerradas hace 10s              -> filas = 1
```

> **Cuatro conexiones cliente produjeron UNA sola fila.** Supavisor **multiplexa**:
> las filas de `pg_stat_activity` son conexiones de **su pool contra Postgres**,
> no sesiones de cliente.

### C.3 — Qué se puede y qué no demostrar desde `pg_stat_activity`

| Se **puede** | Se **NO puede** |
|---|---|
| Ver qué roles tienen **alguna** conexión de pool viva | Contar cuántos clientes hay |
| Ver que un rol **apareció** en algún momento | Atribuir una fila a un servicio concreto |
| Distinguir roles de plataforma (`supabase_admin`, `authenticator`, `pgbouncer`) de roles de aplicación | Concluir que un rol **no se usa** porque no aparece |
| Leer `backend_start` para descartar conexiones propias | Saber qué rol usa un servicio que está inactivo |

**[MEDIDO]** Dos razones acumuladas por las que la ausencia no prueba nada:

1. **`CONN_MAX_AGE = 0`** en `settings.py` — Django abre y cierra una conexión
   por petición; entre peticiones no hay ninguna.
2. **Supavisor multiplexa** — demostrado en C.2.

**[MEDIDO]** Lo que sí se observó, consistentemente: los únicos roles presentes
fueron `supabase_admin`, `authenticator` (PostgREST), `pgbouncer`,
`supabase_storage_admin` — **todos de la plataforma Supabase**, ninguno de la
aplicación salvo el mío.

> **Conclusión metodológica:** `pg_stat_activity` **no puede** responder la
> pregunta de este paso, ni a favor ni en contra. La única evidencia válida es
> ejecutar `select session_user` **desde el contexto de cada servicio** (A.2).

---

## D. Estado de G-2

**[MEDIDO]** Todo lo de esta sección se comprobó **empíricamente**, con la sesión
en `read_only` y la transacción revertida. **No se insertó nada. El interruptor
quedó intacto: 1 fila, `detenido`, del 2026-09-17 20:25 — anterior a las pruebas.**

### D.1 — Las tres comprobaciones que pedía el §6

| # | Prueba | Resultado |
|:--:|---|---|
| 1 | `motor_user` → `EXECUTE autonomia_detener()` | **True** ✔ |
| 2 | `motor_user` → `SET ROLE autonomia_operador` | **False** ✔ (debe seguir fallando, y falla) |
| 3 | `postgres` → `SET ROLE autonomia_operador` | **permitido** ✔ (confirmado en vivo) |

### D.2 — La prueba en vivo

**[MEDIDO]** `postgres` cambiando de rol, dentro de una transacción revertida:

```
[1] postgres -> SET LOCAL ROLE autonomia_operador : OK
    current_user=autonomia_operador   session_user=postgres
    como autonomia_operador: INSERT en interruptor = True   EXECUTE detener = True
    (no se insertó nada: sesión read_only y transacción revertida)
    tras revertir: current_user=postgres

[2] postgres -> SET LOCAL ROLE motor_user : DENEGADO
    InsufficientPrivilege: permission denied to set role "motor_user"
```

**[MEDIDO]** Y lo que el propio Postgres afirma de los roles de runtime:

| | `SET ROLE autonomia_operador` | `EXECUTE autonomia_detener` | `INSERT` interruptor | `SELECT` interruptor |
|---|:--:|:--:|:--:|:--:|
| `motor_user` | **False** | **True** | **False** | **True** |
| `crm_user` | **False** | **False** | — | — (sin USAGE en `asistente`) |
| `postgres` | **True** | True | True | True |

### D.3 — El dilema de B-7A queda **confirmado**, no resuelto

**[MEDIDO]** Las rutas `/autonomia/detener` y `/autonomia/reactivar` del motor
terminan en `db.registrar_transicion_autonomia`, que hace
`SET LOCAL ROLE autonomia_operador`. Y `motor_user` **no puede hacerlo** —
comprobado.

> **[RIESGO] Por lo tanto, hoy exactamente una de estas dos es cierta:**
>
> **(a)** el motor corre como **`postgres`** → `SET ROLE` funciona → **el runtime
> puede reactivar la autonomía por su cuenta**; o
>
> **(b)** el motor corre como **`motor_user`** → `SET ROLE` falla con
> `InsufficientPrivilege` → **`POST /autonomia/detener` y `/autonomia/reactivar`
> están rotos en producción**, y la parada de emergencia por HTTP no existe.
>
> **B-7B no pudo determinar cuál**, porque depende de B (la identidad real), que
> quedó **[NO DEMOSTRADO]**.

**[MEDIDO]** Lo que sí queda demostrado es que **la solución propuesta en B-7A
funciona**: `motor_user` **sí** tiene `EXECUTE` sobre `autonomia_detener()`. Si
`interruptor.detener()` llamara a esa función en vez de hacer `SET ROLE`, detener
funcionaría bajo `motor_user` y reactivar seguiría siendo imposible para el
runtime — que es la asimetría buscada.

**[DEPENDENCIA]** Ese cambio es de código y no se hizo aquí. **`interruptor.py`
no se modificó.**

---

## E. Credenciales

**Ningún valor secreto fue leído ni se guarda en este documento.**

| Pregunta | Respuesta | Estado |
|---|---|---|
| ¿`crm_user` existe y sirve para Django? | El **rol** existe, sin SUPERUSER ni BYPASSRLS, con DML sobre `public` y **sin USAGE sobre `asistente`** | **[MEDIDO]** el rol · **[NO DEMOSTRADO]** la credencial |
| ¿`crm_migrator` existe y sirve para migraciones? | El **rol** existe y puede `SET ROLE crm_owner` (necesario para el DDL de RLS) | **[MEDIDO]** el rol · **[NO DEMOSTRADO]** la credencial |
| ¿Dónde se administran? | **Variables de entorno de Dokploy**, por servicio | **[MEDIDO]** por diseño del compose |
| ¿Existen como secret/env/config? | Como **env** en Dokploy. **No** en `asistente.tenant_secrets` | **[MEDIDO]** |
| ¿Quién necesitaría modificarlas? | Quien administre Dokploy. No el CRM, no el motor, no la IA | **[MEDIDO]** |

**[MEDIDO]** `asistente.tenant_secrets` contiene **9 secretos, todos de APIs
externas** (WispHub, SmartOLT, WhatsApp, BottleCRM, importación). **Ninguna
credencial de base de datos**, y es correcto: para leer esa tabla hay que estar
ya conectado a la base que abre.

**[NO DEMOSTRADO]** Que las contraseñas de `crm_user` y `crm_migrator` existan,
sean correctas y estén accesibles. **Un rol que existe no es una credencial
utilizable**, y la única forma de comprobarlo es intentar conectar con ella —
algo que exige tener la contraseña.

**[PENDIENTE]** Comprobación sugerida, sin exponer nada, desde el Docker Terminal
o desde una máquina con la credencial:

```bash
python -c "
import os, psycopg
d=(f\"postgresql://{os.environ['PRUEBA_USER']}:{os.environ['PRUEBA_PASS']}\"
   f\"@{os.environ['DBHOST']}:{os.environ['DBPORT']}/{os.environ['DBNAME']}?sslmode=disable\")
with psycopg.connect(d) as c:
    print('conecta OK como', c.execute('select session_user').fetchone()[0])
"
```

---

## F. GO / NO-GO para B-7C

### Criterios del §7

| # | Condición | Estado |
|:--:|---|---|
| 1 | Usuario real de **Django** | **[NO DEMOSTRADO]** |
| 2 | Usuario real del **motor** | **[NO DEMOSTRADO]** |
| 3 | Usuario real del **motor-reloj** | **[NO DEMOSTRADO]** |
| 4 | Usuario real del **scheduler** (`celery-beat`) | **[NO DEMOSTRADO]** |
| 5 | Usuario real de **workers** (`celery-worker`) | **[NO DEMOSTRADO]** |
| 6 | Disponibilidad de **`crm_user`** | rol **[MEDIDO]** · credencial **[NO DEMOSTRADO]** |
| 7 | Disponibilidad de **`crm_migrator`** | rol **[MEDIDO]** · credencial **[NO DEMOSTRADO]** |

### Veredicto

## NO-GO

**Ninguna de las siete condiciones está demostrada.** El criterio del encargo es
explícito: *si alguno no puede demostrarse, NO-GO*.

**La causa es una sola y no es técnica:** este entorno **no tiene ninguna vía de
acceso al despliegue** — sin CLI, sin clave SSH, sin contexto Docker remoto, sin
token. Se agotaron las seis vías posibles (A.1). No es que falte una medición
más: **falta un acceso que este entorno no tiene y que no me corresponde
conseguir por mi cuenta.**

### Lo que este paso sí dejó cerrado

| # | Resultado |
|---|---|
| 1 | **Se descartó una conclusión falsa de B-7A**: aquellas conexiones `postgres` eran mías, no del CRM |
| 2 | **`pg_stat_activity` queda descartado como fuente**, con demostración: 4 clientes → 1 fila |
| 3 | **G-2 confirmado empíricamente**: `postgres` puede `SET ROLE autonomia_operador` (probado en vivo), `motor_user` no, y `motor_user` sí puede `EXECUTE autonomia_detener` |
| 4 | **La solución de B-7A queda validada**: el privilegio que necesita ya está concedido |
| 5 | **Procedimiento exacto y listo** para cerrar B-7B en un Docker Terminal (A.2) |

### Lo único que falta para pasar a GO

| # | Acción | Quién | Cuánto |
|:--:|---|---|---|
| 1 | Ejecutar los dos comandos de A.2 en los **5 servicios** | persona con acceso a Dokploy | minutos |
| 2 | Confirmar que las contraseñas de `crm_user` y `crm_migrator` existen y conectan (E) | ídem | minutos |

**Con esas dos salidas pegadas en este documento, B-7B pasa a GO sin ningún
trabajo adicional.**

### Alarma que no debería esperar

> **[RIESGO]** Independientemente de B-7: hoy **o el runtime puede reactivar la
> autonomía, o la parada de emergencia por HTTP está rota**. Las dos son graves,
> y distinguirlas cuesta **un solo comando** — el paso 2 de A.2 sobre el servicio
> `motor`.

---

### Anexo — qué se midió y con qué

| Medición | Herramienta | Resultado |
|---|---|---|
| Vías de acceso a Dokploy | `docker context ls`, `ssh-add -l`, `ls ~/.ssh`, `env` | **ninguna disponible** |
| Panel de Dokploy | `curl` (sin autenticar) | HTTP 200 — existe, sin credenciales |
| Identidad de esta sesión | `select current_user, session_user, …` | `postgres` / `postgres` / `role=none` |
| Servidor final | `inet_server_addr/port()` | `172.20.0.4` : **5432** (no 5433: describe el backend, no el pooler) |
| Multiplexación del pooler | 4 conexiones cliente vs filas | **4 → 1 fila** |
| Persistencia de conexiones | cerrar 3 y recontar | sin residuo |
| `postgres` → `SET ROLE autonomia_operador` | en vivo, revertido | **permitido** |
| `postgres` → `SET ROLE motor_user` | en vivo | **`InsufficientPrivilege`** |
| `motor_user` → `autonomia_detener` | `has_function_privilege` | **True** |
| `motor_user` → `SET ROLE autonomia_operador` | `pg_has_role` | **False** |
| `crm_user` → `asistente` | `has_schema_privilege` | **False** (sin USAGE) |
| Secretos de base en `tenant_secrets` | `select distinct nombre` | **ninguno** (9 secretos, todos de APIs) |

Producción al cerrar el paso, sin cambios:

```
interruptor : 1 fila · detenido · 0 ACTIVO · última del 2026-09-17 20:25
ledger 50 · 0 PropuestaSupervisor · 40 acciones_propuestas · 192 django_migrations
tenant_config v146 · 25 roles · 375 grants en asistente
```
