# Paso 10 — Aplicación controlada de las migraciones pendientes

**Fecha:** 17/09/2026
**Resultado:** **4 de 6 aplicadas.** Las 4 de Django, en producción, con
`crm_migrator`, 0 fallos en 32 verificaciones. **Las 2 de Fase 1 NO se
aplicaron**: están bloqueadas por dos impedimentos independientes, ninguno
resoluble dentro del alcance autorizado de este paso. Sin rollback.

> **El criterio de éxito exige 6/6, así que este paso NO está aprobado.** El
> §10 explica los dos bloqueos y el §13 las opciones.

---

## 1. Estado inicial

Medido en producción inmediatamente antes de ejecutar.

| Elemento | Antes |
|---|---|
| Tablas en `public` | 129, todas de `crm_owner` |
| Secuencias / índices | 51 / 783 |
| RLS / FORCE / políticas | 60 / 60 / 120 |
| `GRANT` a `crm_user` | 903 |
| Filas en `django_migrations` | 188 |
| Las 6 tablas de `operaciones` | ninguna existía |
| `postgres → crm_owner` | 2 filas (una hereda, otra con `ADMIN OPTION`) |

**Datos:** `case` 185 · `activity` 562 · `organization` 2 · `users` 5 ·
`contacts` 0 · `lead` 5 · `task` 0 · `comment` 4 ·
`asistente.messages` 2.594 · `conversations` 302 · `tool_calls` 1.190.

**Estabilidad:** 0 transacciones abiertas, 0 bloqueos `ACCESS EXCLUSIVE`,
0 deadlocks, 13 sesiones ociosas.

**Respaldo:** `paso10_20260917_100237_datos.dump` (8.843.854 bytes) +
`paso10_20260917_100237_roles.sql` (25 roles). **Verificado restaurándolo** en
un desechable con el procedimiento de B.6 §B: `pg_restore` exit 0 →
129 · 51 · 783 · 120 · 903 · 129 de `crm_owner` · 35 tablas en `asistente`.

---

## 2. Migraciones ejecutadas

| # | Migración | Efecto real |
|---|---|---|
| 1 | `campo.0003_alter_asignaciontrabajo_rol` | **`-- (no-op)`** — sólo cambian `choices` y `help_text`, que no viven en la base. Comprobado con `sqlmigrate` antes de aplicar |
| 2 | `common.0039_alter_activity_entity_type` | **`-- (no-op)`** — ídem |
| 3 | `operaciones.0001_initial` | Crea las 6 tablas del módulo, con 46 índices |
| 4 | `operaciones.0002_rls_operaciones` | Estampa 12 políticas RLS (2 por tabla). `atomic = False`: confirma por sentencia para que cada `ACCESS EXCLUSIVE` sea corto |

```
Applying campo.0003_alter_asignaciontrabajo_rol... OK
Applying common.0039_alter_activity_entity_type... OK
Applying operaciones.0001_initial... OK
Applying operaciones.0002_rls_operaciones...  Políticas RLS estampadas en 6 tabla(s)
 OK
>>> CODIGO DE SALIDA: 0    duracion: 42 s
```

Se fijó `PGOPTIONS=-c lock_timeout=10s`: si algo hubiera estado bloqueado, la
migración abortaba en 10 s en vez de encolar el tráfico del CRM.

**NO ejecutadas:** `202609151710_interruptor_autonomia.sql` y
`202609151715_operaciones_externas.sql` (ver §10).

---

## 3. Identidad efectiva utilizada para migrar

Comprobada contra producción **por el pooler**, con la misma conexión que usó
Django:

```
session_user       = crm_migrator
current_user       = crm_owner
role de la sesion  = crm_owner
SET ROLE configurado = ['role=crm_owner']
servidor           = PostgreSQL 17.6
tablas de public cuyo dueno puede asumir: 129 de 129
crm_migrator: login=True bypassrls=False super=False createdb=False createrole=False
```

Los cinco puntos de la condición 3, cumplidos. **`crm_user` no intervino en
ningún momento.**

---

## 4. Propiedad, antes y después

| | Antes | Después |
|---|---|---|
| Tablas de `public` | 129 | **135** |
| De `crm_owner` | 129 | **135** |
| De `crm_user` | 0 | **0** |
| De `postgres` | 0 | **0** |

Las 6 tablas nuevas quedaron de `crm_owner` **sin que ninguna migración lo
pidiera**: lo hace el `SET role` de `crm_migrator`. Las 129 ya transferidas no
cambiaron de dueño.

---

## 5. RLS, antes y después

| | Antes | Después |
|---|---|---|
| Tablas con RLS | 60 | **66** |
| Con `FORCE` | 60 | **66** |
| Políticas en `public` | 120 | **132** |

Las 6 nuevas: `ENABLE` + `FORCE` + 2 políticas cada una.

```
org_isolation     cmd=ALL     using: org_id = current_setting('app.current_org')
org_insert_check  cmd=INSERT  check: org_id = current_setting('app.current_org')
```

---

## 6. Pruebas de aislamiento

Hechas **asumiendo `crm_user` de verdad** sobre la réplica exacta, porque en
producción `set role crm_user` es imposible (`GRANT crm_user TO postgres …
SET FALSE` de `supabase_admin`, medido en el paso 9). La réplica se construyó
con el respaldo de hoy y se le aplicaron las mismas 4 migraciones.

| Prueba | Resultado |
|---|---|
| `crm_user` inserta como org1 y consulta como org2 | org2 ve **0 filas** |
| org2 intenta insertar una fila con `org_id` de org1 | **rechazado** — `new row violates row-level security policy` |
| Consulta **sin** contexto de organización | no falla y devuelve **0 filas** (fail-closed) |

---

## 7. Pruebas DML / DDL

**DML de `crm_user`** — en producción, `SELECT`, `INSERT`, `UPDATE` y `DELETE`
concedidos en **las 6/6 tablas nuevas**, y `USAGE` donde corresponde. Ninguna
migración escribió esos `GRANT`: salen de los **DEFAULT PRIVILEGES de
`crm_owner`** aplicados en B.8 paso 2. Es la primera confirmación en vivo de
que ese mecanismo funciona sobre objetos nuevos.

En la réplica, además, ejercidos de verdad: `SELECT` e `INSERT` sobre
`operaciones_actividad`, ambos revertidos.

**DDL:**

| Rol | Operación | Resultado |
|---|---|---|
| `crm_user` | `ALTER TABLE operaciones_actividad ADD COLUMN` | **rechazado** — `must be owner of table` |
| `crm_user` | `CREATE TABLE` en `public` | **permitido** — conserva `CREATE`; revocarlo es el paso 11, no autorizado |
| `crm_migrator` | `ALTER TABLE` | **permitido** (revertido) |

Todo sobre objetos desechables o revertido; ninguna estructura productiva se
alteró fuera de las migraciones.

---

## 8. Estado de los servicios

| Servicio | Resultado |
|---|---|
| CRM (`crm.rapilinksas.co`) | **HTTP 401** en 0,41 s — arriba, pide credenciales |
| Admin de Django (`agent-api…/admin/`) | **HTTP 302** — arriba, redirige a login |
| Frontend (`agent.rapilinksas.co/login`) | **HTTP 200** | 
| Base | 0 deadlocks, 0 conflictos, 0 errores de permisos nuevos |
| `motor_user`, `app_backend`, `asistente_owner` | atributos sin cambios |

**Lo que NO puedo afirmar:** que el motor esté arriba. Su host público devuelve
`404 page not found` en texto plano —respuesta del router, no de Flask— en
`/salud`, `/agentes` y `/configuracion`, y **ya devolvía 404 en el paso 9**,
antes de estas migraciones. No hay sesiones de `motor_user` ahora mismo y su
última escritura fue a las 14:20 UTC; con el tráfico de WhatsApp parado, Supavisor
recicla las conexiones ociosas, así que eso no es evidencia de fallo — pero
tampoco es prueba de salud. Lo que sí está medido es que **nada en la base
cambió para él**: `app_backend` conserva `select`/`insert` en sus 4 tablas de
`asistente`, y de las 6 tablas nuevas puede leer **0**.

---

## 9. Comparación de datos

| Tabla | Antes | Después |
|---|---|---|
| `case` / `activity` | 185 / 562 | **185 / 562** |
| `organization` / `users` | 2 / 5 | **2 / 5** |
| `contacts` / `lead` / `task` / `comment` | 0 / 5 / 0 / 4 | **0 / 5 / 0 / 4** |
| `asistente.messages` / `conversations` / `tool_calls` | 2.594 / 302 / 1.190 | **2.594 / 302 / 1.190** |
| Las 6 nuevas | — | 0 filas cada una |

**0 pérdida de registros. 0 datos de negocio modificados.** Los 903 `GRANT`
previos siguen intactos (927 − 24 de las 6 nuevas = 903). 0 índices inválidos.
`django_migrations` 188 → **192**, y las 4 más recientes son exactamente las 4
aplicadas; la anterior es del 11/09. **0 migraciones inesperadas.**

---

## 10. Incidencias

### 10.1 · Las 2 de Fase 1 están bloqueadas, por dos motivos independientes

**Bloqueo A — `crm_migrator` no puede tocar el esquema `asistente`.**
Las dos migraciones crean tablas en `asistente`, no en `public`. Medido:

```
crm_owner     en 'asistente':  CREATE=False  USAGE=False
crm_migrator  en 'asistente':  CREATE=False  USAGE=False
postgres      en 'asistente':  CREATE=True   USAGE=True
```

El esquema es de `postgres`, y su ACL nombra a `app_backend`,
`asistente_owner`, `scheduler_coordinator`, `job_executor` y `monitor_ro`. La
separación de credenciales del CRM cubre `public` y sólo `public`; eso fue el
alcance explícito desde B.3. Habilitar a `crm_migrator` exigiría
`GRANT USAGE, CREATE ON SCHEMA asistente TO crm_owner`, que mezcla los dos
dominios de propiedad y entra de lleno en el «no tocar Motor» de este paso.

**Bloqueo B — el ledger se niega a aplicar nada.** Independiente del anterior:

```
[migrar] HAY ARCHIVOS APLICADOS QUE CAMBIARON. No se escribe nada.
    202609141200_scheduler_persistente.sql
    202609141300_scheduler_funciones.sql
```

`cli/migrar_asistente.py --aplicar` es todo-o-nada: mientras dos archivos ya
aplicados no coincidan con su checksum, no aplica **ninguna** migración
pendiente, con cualquier credencial.

Investigado a fondo:

- Mi reproducción del algoritmo (`sha256` sobre el contenido normalizado a LF)
  se **validó primero** contra el ledger entero: 40 coincidencias + 2
  divergencias + 3 anotadas sin archivo = las 45 filas, exactamente el
  veredicto del CLI.
- Esas dos son las **únicas** filas con `origen='aplicada'` de todo el ledger
  (el resto son `baseline` 36 y `baseline_humano` 7). Se aplicaron el
  **15/09 a las 19:32 y 19:40 UTC**, por `postgres`.
- **Ninguna versión del historial de git coincide** con el checksum anotado, en
  ninguno de los dos archivos. Los commits que los tocan son todos del 14/09 —
  anteriores a la aplicación. O sea: se aplicaron desde un árbol de trabajo con
  ediciones sin commitear que nunca se commitearon en esa forma exacta.
- Lo que sí se puede leer del último commit de cada uno: en
  `scheduler_funciones` son **51 líneas de puro comentario**; en
  `scheduler_persistente`, una guarda de pre-vuelo que comprueba dos funciones
  de `pgcrypto` en vez de una. Ninguna de las dos crea ni altera un objeto.

No toqué el ledger: es una tabla de solo-agregar con disparadores que impiden
`UPDATE`, `DELETE` y `TRUNCATE`, y resolver esto es una decisión deliberada, no
un trámite.

### 10.2 · Tres errores de método míos

- **Etiqueta escrita de antemano, otra vez.** Imprimí
  `app_backend en schema public: usage=True (debe seguir siendo False)`. El
  `True` es correcto y **anterior a todo este trabajo**: la ACL del esquema
  incluye `=U/pg_database_owner`, es decir `USAGE` para `PUBLIC`, el valor por
  defecto de PostgreSQL. Lo que de verdad limita al motor son las tablas: puede
  leer **1 de 135** (`organization`) y **0 de las 6 nuevas**. Mi «debe seguir
  siendo False» era una suposición, no una medición — el mismo error que ya
  cometí en el paso 9 con las tablas de `asistente`.
- **Una comprobación que sólo vale contra producción.** El verificador exigía
  2 filas de membresía `postgres → crm_owner` y falló en la réplica, que sólo
  tiene 1: el `roles.sql` no puede recrear las líneas `GRANTED BY
  supabase_admin`. Artefacto conocido desde 9.1, no un hallazgo.
- **Comillas escapadas dentro de f-strings** y `docker exec` sin `-i`: dos
  scripts murieron por sintaxis antes de llegar a la base.

---

## 11. Rollback

**Definido antes de ejecutar.** Condición: cualquier tabla nueva que no quedara
de `crm_owner`; cualquier tabla bajo `crm_user` o `postgres`; RLS sin
`ENABLE`+`FORCE`; políticas ≠ 132; cambio de dueño en las 129; pérdida de
filas; `crm_user` ganando propiedad, `BYPASSRLS`, `CREATEDB` o `CREATEROLE`;
cambio en las dos membresías; o errores de permisos nuevos en los servicios.

**Procedimiento, ensayado en la réplica antes de migrar producción:**

```
manage.py migrate operaciones zero    # elimina las 6 tablas y sus politicas
manage.py migrate common 0038
manage.py migrate campo  0002
```

Resultado del ensayo: **129 | 120 | 903 | 0 migraciones de operaciones |
case 185 | activity 562** — vuelta exacta al punto de partida, sin pérdida de
datos. Y re-aplicar después devolvió **135 | 132 | 135**: el rollback también
es reversible. Si fallara, queda la restauración del respaldo verificado de §1.

**No se ejecutó.** Las 32 verificaciones pasaron; ninguna advertencia implicó
desviación real.

---

## 12. Estado final

| Elemento | Estado |
|---|---|
| Tablas de `public` | **135**, todas de `crm_owner` |
| Secuencias / índices | 51 / **829** (0 inválidos) |
| RLS / FORCE / políticas | **66 / 66 / 132** |
| `GRANT` a `crm_user` | **927** (903 previos + 24 nuevos, automáticos) |
| `django_migrations` | **192** (188 + 4) |
| Fase 1 | **2 pendientes**, bloqueadas |
| `crm_user` | sin propiedad, sin `BYPASSRLS`, sin `CREATEDB`/`CREATEROLE`; conserva `CREATE` en `public` (paso 11) |
| `postgres → crm_owner` | **2 filas intactas** |
| DBUSER | **sin cambios** (`postgres`) |
| Celery, motor, WispHub, SmartOLT, autonomía | **sin tocar** |

---

## 13. Riesgos nuevos y decisiones pendientes

1. **El ledger del asistente está bloqueado** y lo seguirá estando para toda
   migración futura de Fase 1 hasta que se decida qué hacer con las dos filas
   divergentes. Opciones, ninguna ejecutada: (a) comprobar contra producción que
   el esquema ya refleja el contenido actual de los dos archivos y anotar la
   divergencia con una fila de adopción; (b) recuperar el contenido exacto que
   se aplicó el 15/09; (c) añadir al CLI una forma explícita y auditada de
   reconocer una divergencia. **Es una decisión suya, no un trámite.**
2. **Las 2 migraciones de Fase 1 pertenecen al dominio del motor**, no al del
   CRM. Si se mantiene el criterio de que toda migración pase por
   `crm_migrator`, hace falta decidir antes si el motor tendrá su propio par
   dueño/migrador en `asistente` —`asistente_owner` ya existe y posee 5
   tablas— o si ese esquema se sigue migrando con `postgres`.
3. **Código desplegado vs esquema.** Las 6 tablas de `operaciones` existen en la
   base pero el módulo **no está desplegado** (`django-crm/backend/operaciones/`
   sigue sin versionar). Es la dirección segura —el esquema va por delante— pero
   conviene no dejar la brecha abierta mucho tiempo.
4. **El host público del motor no enruta.** Pre-existente y ajeno a este paso,
   pero significa que hoy no hay forma de comprobar su salud desde fuera.
