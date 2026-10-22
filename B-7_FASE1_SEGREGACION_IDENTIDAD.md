# B-7 — SEGREGACIÓN DE IDENTIDAD DE BASE DE DATOS

## INFORME DE FASE 1 — AUDITORÍA + ENTORNO AISLADO

Fecha: 2026-09-19
Alcance: **FASE 1 únicamente.** No se ejecutó Fase 2. No se cambió `DBUSER`
productivo. No se creó ningún rol en producción. No se activó autonomía. No se
tocó el kill switch. No se hizo commit.

Convenciones: `[MEDIDO]` = lo comprobé ejecutando algo y leyendo el resultado.
`[DISEÑO]` = propuesta, todavía no ejecutada. `[RIESGO]`, `[PENDIENTE]`,
`[DECISIÓN]` = requieren su autorización.

---

# 0. INCIDENTE — DEBO REPORTARLO ANTES QUE NADA

**Creé una tabla en producción por error. Sigue ahí.**

```
public.b7_no_deberia_existir   dueño=postgres   0 filas   0 columnas
tablas en public: 135 (antes)  ->  136 (ahora)
```

### Qué pasó

El script de verificación contra producción abría la conexión así:

```python
conn = psycopg.connect(..., autocommit=True)
conn.read_only = True
```

y terminaba con una comprobación que pretendía *demostrar* que la conexión era
de solo lectura, intentando un `CREATE TABLE` y esperando que el servidor lo
rechazara. **El servidor lo aceptó.**

La causa: en psycopg 3, `conn.read_only` se aplica a las transacciones que la
propia librería abre. Con `autocommit=True` psycopg **no abre transacción
explícita**, así que `default_transaction_read_only` nunca llega al servidor y
el atributo queda decorativo. `autocommit` y `read_only` no componen.

Lo verifiqué: la misma conexión **sin** `autocommit` sí rechaza la escritura
(`cannot execute CREATE TABLE in a read-only transaction`).

### Lo que esto significa sobre los pasos anteriores

Es una lección que corrige una afirmación que vengo repitiendo en informes
previos: **decir «conexión abierta con `read_only=True`» no era prueba de nada**
si esa conexión también llevaba `autocommit=True`. La barrera real en aquellos
pasos fue que las consultas eran `SELECT` — no el atributo. La barrera que yo
creía tener no existía.

No encontré ninguna otra escritura: los scripts anteriores solo ejecutaban
`SELECT`, y los contadores de producción (roles 41, `django_migrations` 192,
`organization` 2, `case` 213, las tablas de `operaciones` en 0) siguen en su
valor conocido. La única diferencia es esta tabla.

### Qué necesito de usted

Intenté revertirlo — un `DROP TABLE public.b7_no_deberia_existir` sin `CASCADE`,
previa comprobación de que está vacía, sin columnas y sin nada que la
referencie. **La operación fue bloqueada por la política de permisos de esta
sesión** (modificación de recurso compartido), y no la eludí.

`[DECISIÓN]` **Producción no está en su estado previo por culpa mía.** Hace falta
que autorice el `DROP` (o que lo ejecute usted). Mientras la tabla siga ahí,
`tablas en public = 136`, y cualquier comparación futura contra el baseline de
135 va a marcar una diferencia que soy yo.

El script de reversión ya está escrito y comprueba antes de actuar:
`scratchpad/revertir_artefacto.py`.

---

# 1. GO / NO-GO DE FASE 1

## **GO** — con una condición previa bloqueante para Fase 2.

Los diez criterios del bloque P, uno por uno:

| # | Criterio (§P) | Estado | Evidencia |
|---|---|---|---|
| 1 | identidad actual medida | **CUMPLE** | §3 |
| 2 | `crm_user` medido | **CUMPLE** | §4 |
| 3 | `crm_migrator` medido | **CUMPLE** | §5 |
| 4 | permisos reales identificados | **CUMPLE** | §8 |
| 5 | runtime requerido identificado | **CUMPLE** | §10 |
| 6 | pooler entendido | **CUMPLE** | §7 — medido, no inferido |
| 7 | RLS probado | **CUMPLE** | §9 — incluye prueba de desarme |
| 8 | smoke test definido | **CUMPLE** | §12 — 13/13 |
| 9 | entorno aislado pasa | **CUMPLE** | §13 |
| 10 | rollback diseñado | **CUMPLE** | §15 |

**Condición bloqueante para iniciar Fase 2:** revertir la tabla de §0. No es un
criterio del bloque P; es que producción no debe entrar a un cambio controlado
arrastrando una modificación no autorizada.

---

# 2. GO / NO-GO DE FASE 2

## **NO-GO todavía** — y no por falta de evidencia técnica.

El bloque Q pide seis cosas. Cuatro ya están demostradas; dos son decisiones
suyas que no puedo tomar:

| Criterio (§Q) | Estado |
|---|---|
| `crm_user` funciona | **DEMOSTRADO** — 13/13 en entorno aislado (§12) |
| runtime no necesita privilegios de `postgres` | **DEMOSTRADO** — §10, §11 |
| migraciones separadas | **DEMOSTRADO** — §11; el mecanismo ya existe en el repo |
| smoke test pasa | **DEMOSTRADO** — §12 |
| rollback probado/documentado | **DOCUMENTADO** (§15). **Probado, no**: probarlo exige un cambio productivo, que es Fase 2 |
| ventana de cambio definida | `[PENDIENTE]` — **decisión suya** |
| evidencia de permisos completa | **CUMPLE** (§8), con dos ajustes propuestos (§8.3) |

`[DECISIÓN]` Fase 2 necesita de usted: (a) la reversión de §0; (b) una ventana
de cambio; (c) autorización explícita para crear/ajustar permisos en producción.

---

# 3. DBUSER ACTUAL `[MEDIDO]`

```
DBHOST declarado    : crm.rapilinksas.co
DBPORT declarado    : 5433          (5433 = session mode; 6544 = transaction)
DBNAME              : postgres
DBUSER              : postgres.<sufijo de pooler, 36 caracteres>
MOTOR_DBUSER        : motor_user.<mismo sufijo>
PostgreSQL          : 17.6
puerto real detrás del pooler : 5432
```

Conectando con `DBUSER` tal como está en `.env`:

```
session_user = postgres
current_user = postgres
rolsuper     = False        <-- postgres NO es superusuario en este Supabase
rolbypassrls = True
rolcreatedb  = True
rolcreaterole= True
```

**El CRM/Django corre hoy como `postgres`.** `postgres` no es superusuario en
esta instalación (lo es `supabase_admin`), pero sí tiene `BYPASSRLS`,
`CREATEDB` y `CREATEROLE`, y es miembro de 24 roles, entre ellos `crm_owner`,
`crm_user`, `crm_migrator`, `app_backend` y `autonomia_operador`.

`[RIESGO]` **`BYPASSRLS` es lo grave, no `SUPERUSER`.** Con `BYPASSRLS` el
aislamiento por organización descrito en `common/rls/` **no se aplica en
absoluto** al runtime del CRM: las 66 políticas existen y no filtran nada. Hoy
la separación entre tenants la sostiene solo el código de aplicación. Ese es
exactamente el agujero que B-7 cierra.

### El valor por defecto es una trampa

`crm/settings.py`:

```python
"USER": os.environ.get("DBUSER", "postgres"),
```

Si `DBUSER` no llega al contenedor, Django **no falla: se conecta como
`postgres`**. `docker-compose.prod.yml` lo exige (`${DBUSER:?}`), así que en ese
camino no puede faltar — pero el default sigue siendo el rol más privilegiado
disponible, que es al revés de lo que conviene.

---

# 4. `crm_user` `[MEDIDO]`

**Existe.** Atributos en producción:

```
rolsuper=False  rolbypassrls=False  rolcreatedb=False  rolcreaterole=False
rolcanlogin=True  rolinherit=True
no es miembro de ningún otro rol
ALTER ROLE: idle_in_transaction_session_timeout=60s
```

Cumple el bloque N: sin SUPERUSER, sin BYPASSRLS, sin CREATEDB, sin CREATEROLE.

Privilegios sobre `public` (136 tablas — 135 reales + la de §0):

```
SELECT     136/136
INSERT     135/135  (de las tablas reales)
UPDATE     135/135
DELETE     135/135
TRUNCATE   130/136   <-- de más
REFERENCES 130/136   <-- de más
TRIGGER    130/136   <-- de más
secuencias USAGE 51/51, SELECT 51/51, UPDATE 51/51   <-- UPDATE de más
dueño de   0/135 tablas          (las 135 son de crm_owner)
CREATE en el esquema public: False
USAGE en public: True | en extensions: False | en asistente: False
```

`USAGE=False` en `asistente` es **correcto y deliberado**: el esquema del motor
no le corresponde al runtime del CRM. Es lo que explica el incidente del 18/08.

Además ya existen `ALTER DEFAULT PRIVILEGES` a favor de `crm_user` en `public`,
tanto de `crm_owner` como de `postgres`, para tablas, secuencias y funciones:
las tablas que cree una migración futura quedan utilizables por `crm_user` sin
un `GRANT` manual.

---

# 5. `crm_migrator` `[MEDIDO]`

**Existe** — al contrario de lo que asumía el antecedente. No hubo que crearlo.

```
rolsuper=False  rolbypassrls=False  rolcreatedb=False  rolcreaterole=False
rolcanlogin=True  rolinherit=True
miembro de: crm_owner
ALTER ROLE crm_migrator IN DATABASE postgres SET role = crm_owner
0 grants directos: todo lo ejerce heredando de crm_owner
TRUNCATE/REFERENCES/TRIGGER 135/136, SELECT 135/136
```

`crm_owner` **no tiene LOGIN** (`rolcanlogin=False`): la única puerta de entrada
al rol dueño es `crm_migrator`, y esa puerta está sujeta a su propia contraseña.
Es la forma correcta.

La contraseña vive fuera del repo, en `C:\Users\Usuario\b8_crm_migrator_clave.txt`.
No la imprimí en ningún momento.

---

# 6. `motor_user` `[MEDIDO]`

```
rolsuper=False  rolbypassrls=TRUE  rolcreatedb=False  rolcreaterole=False
miembro de: app_backend
USAGE: public=True, asistente=True, extensions=False
SELECT sobre public: 1 de 136 tablas   (vive en el esquema 'asistente')
TRUNCATE/REFERENCES/TRIGGER: 0/136
```

`[RIESGO]` **`motor_user` tiene `BYPASSRLS`.** No lo toqué — el bloque N dice
«No modificar `motor_user` salvo que una evidencia específica lo requiera», y no
la hay dentro de B-7. Pero queda anotado: el motor ve todas las filas de todas
las organizaciones en las tablas que alcance. Hoy alcanza 1 tabla de `public`,
así que el impacto real es chico; el atributo es lo que no lo es.

**Explícitamente NO copié `BYPASSRLS` a `crm_user`.**

### Hallazgo heredado que sigue abierto

El defecto del kill switch reportado en M10-A sigue igual:
`pg_has_role('motor_user','autonomia_operador','SET') = False`. La salida de
emergencia `asistente.autonomia_detener()` existe como SECURITY DEFINER de
`postgres` y `app_backend` tiene `EXECUTE`, pero la ruta
`POST /autonomia/detener` no la llama: pasa por `sesion(..., rol=ROL_OPERADOR_AUTONOMIA)`,
que necesita el `SET ROLE` que `motor_user` no tiene. **B-7 no lo arregla ni lo
empeora.** Queda reportado, sin parchear.

---

# 7. POOLER `[MEDIDO]` — medido, no inferido

El bloque I pedía explícitamente no asumir que la cadena determina el usuario
efectivo. Lo medí abriendo **una** conexión de solo lectura como `crm_migrator`
con el sufijo del pooler y preguntándole a la base quién era:

```
usuario ENVIADO en la cadena : crm_migrator.<sufijo de 36 caracteres>
session_user (quién entró)   : crm_migrator      <-- el pooler QUITA el sufijo
current_user (quién actúa)   : crm_owner         <-- por el ALTER ROLE ... SET role
role (SET ROLE vigente)      : crm_owner
puerto del servidor real     : 5432   (la cadena pide 5433)
session_user es superusuario : False
session_user tiene BYPASSRLS : False
search_path                  : "$user", public
```

Cuatro cosas quedan demostradas y no supuestas:

1. **Supavisor entrega el rol base, no el sufijo.** `crm_user.<sufijo>` llegará a
   PostgreSQL como `crm_user`. El sufijo lo exige el pooler para enrutar; no es
   parte de la identidad dentro de la base.
2. **El `SET ROLE` de `ALTER ROLE ... IN DATABASE` sobrevive al pooler.** Es lo
   que permite que `crm_migrator` actúe como `crm_owner` sin ser dueño.
3. **Session mode, no transaction mode** (5433). Importa mucho: `app.current_org`
   se fija con `set_config(..., is_local=false)`, o sea **alcance de sesión**.
   En transaction mode (6544) una conexión multiplexada llevaría el `org_id` del
   tenant anterior al siguiente. El puerto actual es el correcto y **no debe
   cambiarse** al hacer Fase 2.
4. `pg_stat_activity` muestra la infraestructura (`supabase_admin` ×9,
   `authenticator`, `pgbouncer`/Supavisor, `supabase_storage_admin`). Las
   conexiones del CRM y del motor aparecen y desaparecen según el pool; en
   mediciones anteriores se identificaron como `postgres` (ejecutando una
   consulta del ORM de Django) y `motor_user`.

### `search_path`: la diferencia que sí investigué

`postgres` tiene `search_path = "$user", public, extensions`. `crm_user` **no
tiene `search_path` configurado**, así que usaría `"$user", public` — sin
`extensions`. Y `crm_user` ni siquiera tiene `USAGE` sobre ese esquema.

¿Rompe algo? **No.** Lo medí en vez de suponerlo:

| Función | Dónde vive | ¿La usa el CRM? |
|---|---|---|
| `gen_random_uuid` | `extensions` **y `pg_catalog`** | sí, y resuelve por `pg_catalog` (nativa desde PG13) |
| `uuid_generate_v4` | solo `extensions` | **no la usa nadie** |
| `digest`, `crypt` | solo `extensions` | **no**: las coincidencias del grep eran `hexdigest(` y `encrypt(`/`decrypt(` de Python |
| `pg_trgm`, `vector` | `public` | accesibles |

Además: **cero columnas de `public` tienen un `DEFAULT` que llame a una función
sin calificar** de `extensions`. Django genera los UUID en Python.

Confirmado en la práctica: en el entorno aislado, `crm_user` ejecutó
`insert ... values (gen_random_uuid(), ...)` correctamente.

---

# 8. PERMISOS

## 8.1 Lo que el runtime **necesita** `[MEDIDO]`

En el entorno aislado concedí a `crm_user` **solo esto** y los 13 ítems del
smoke test pasaron:

```sql
GRANT USAGE ON SCHEMA public TO crm_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO crm_user;
```

Comprobación del resultado en el aislado:

```
tablas  SELECT/INSERT/UPDATE/DELETE : 135/135/135/135 de 135
tablas TRUNCATE/REFERENCES/TRIGGER  : 0/0/0 de 135
secuencias USAGE/SELECT/UPDATE      : 51/51/0 de 51
esquema public USAGE=true  CREATE=false
tablas de las que puede ejercer el rol dueño: 0
```

**Con TRUNCATE=0, REFERENCES=0, TRIGGER=0 y secuencias sin UPDATE, el smoke test
pasó 13/13.** Eso no es una opinión sobre qué «debería» bastar: es la medición de
qué basta.

## 8.2 Lo que **no** puede hacer `[MEDIDO]`

Siete operaciones administrativas, todas rechazadas por el servidor:

| Operación | Resultado |
|---|---|
| `CREATE TABLE` | BLOQUEADA |
| `CREATE ROLE` | BLOQUEADA |
| `ALTER TABLE ... OWNER TO` | BLOQUEADA |
| `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` | BLOQUEADA |
| `DROP TABLE` | BLOQUEADA |
| `TRUNCATE` | BLOQUEADA |
| `ALTER ROLE ... SUPERUSER` | BLOQUEADA |

> **Corrección de una medición anterior.** En una corrida previa tres de estas
> aparecieron como «PERMITIDO». Era falso: usé el nombre de tabla `org`, que no
> existe, y el error era `relation "org" does not exist`, no una autorización.
> Repetido con `activity`, las siete quedan bloqueadas. Un fallo por el motivo
> equivocado se lee igual que un éxito si uno no mira el mensaje.

## 8.3 Dos ajustes propuestos para producción `[DISEÑO]`

En producción `crm_user` tiene **más** de lo que necesita:

| Privilegio | Producción | Necesario (medido) | Propuesta |
|---|---|---|---|
| `TRUNCATE` | 130/136 tablas | 0 | `REVOKE TRUNCATE` |
| `REFERENCES` | 130/136 | 0 | `REVOKE REFERENCES` |
| `TRIGGER` | 130/136 | 0 | `REVOKE TRIGGER` |
| secuencias `UPDATE` | 51/51 | 0 (basta `USAGE`) | `REVOKE UPDATE ON SEQUENCES` |

`TRUNCATE` es el que más pesa: vacía una tabla entera sin pasar por las
políticas RLS de fila y sin dejar filas que auditar.

`[DECISIÓN]` **No ejecuté ningún `REVOKE`.** Quitar privilegios en producción es
un cambio productivo y pertenece a Fase 2, con su autorización.

## 8.4 Un hallazgo de seguridad que B-7 **no** resuelve `[RIESGO]`

`crm_user` **puede leer `pg_catalog.pg_db_role_setting`** (`SELECT=True`), y ahí
hay **una entrada con un secreto de aplicación a nivel de base de datos**
(un `jwt_secret`). `motor_user` también puede leerla. No pueden leer `pg_authid`
ni `pg_shadow` (hashes de contraseña), eso sí está protegido.

Consecuencia honesta: **cambiar el runtime a `crm_user` no oculta ese secreto.**
Cualquier rol que pueda iniciar sesión lo lee. No es un problema que B-7 cause
ni que B-7 arregle, pero sería deshonesto presentar la segregación como si lo
cubriera.

`[AVISO]` Ese valor apareció impreso en la salida de una de mis consultas
durante esta sesión (al volcar `pg_db_role_setting` completo). No lo reproduzco
aquí. **Si la transcripción de esta sesión no se considera un lugar seguro para
ese secreto, hay que rotarlo.** Es su decisión; la reporto porque ocultarla
sería peor.

---

# 9. RLS `[MEDIDO]`

## 9.1 Estado en producción

```
tablas con RLS      : 66 de 135
tablas con FORCE RLS: 66 de 66      <-- todas
tablas con RLS sin FORCE: ninguna
políticas por tabla : 2 (org_isolation FOR ALL + org_insert_check FOR INSERT)
```

Ambas comparan contra
`org_id::text = (select NULLIF(current_setting('app.current_org', true), ''))`,
o sea **fallan cerrado**: contexto vacío ⇒ cero filas.

## 9.2 Comportamiento real como `crm_user`, no como superusuario

En el entorno aislado, con dos organizaciones y filas de cada una:

| Prueba | Resultado |
|---|---|
| `SELECT` **sin** contexto | 0 filas |
| `SELECT` con contexto A | solo la fila de A |
| `SELECT` con contexto B | solo la fila de B |
| `UPDATE` con contexto A sobre fila de B | `UPDATE 0` |
| `DELETE` con contexto A sobre fila de B | `DELETE 0` |
| `INSERT` con contexto A y `org_id` de B | **RECHAZADO** — `new row violates row-level security policy` |
| `INSERT` con contexto A y `org_id` de A | `INSERT 0 1` |

## 9.3 La prueba de desarme — porque un cero no prueba nada solo

`UPDATE 0` puede significar «RLS lo impidió» o «el `WHERE` no encontró nada».
Para distinguirlo, desarmé la guarda **en el entorno aislado**:

```
crm_user CON BYPASSRLS  ->  UPDATE 1   y la fila de B queda con desc='INTRUSION'
crm_user SIN BYPASSRLS  ->  UPDATE 0   y la fila de B queda intacta
```

El instrumento dispara. Los ceros de §9.2 son RLS, no un `WHERE` mal escrito.
`crm_user` quedó con `rolbypassrls = f` al terminar.

## 9.4 FORCE RLS alcanza al dueño — y eso tiene una consecuencia

Conectado como `crm_migrator` (que actúa como `crm_owner`, **dueño de las 135
tablas**):

```
SELECT sin contexto                        -> 0 filas
UPDATE con contexto A sobre la fila de B   -> UPDATE 0
```

`FORCE ROW LEVEL SECURITY` funciona: ni el dueño se salta sus propias políticas.

`[RIESGO]` **Esto rompe silenciosamente las migraciones de datos.** Medido:

```
filas reales en 'activity' (vistas por superusuario) : 3
UPDATE como crm_migrator, sin contexto de tenant     : UPDATE 0     <-- sin error
el mismo UPDATE sobre 'organization' (SIN RLS)       : UPDATE 2
```

O sea: `crm_migrator` **sí** puede escribir; lo que no puede es *ver* las filas
protegidas por RLS. Un `RunPython` de backfill correría, no lanzaría excepción,
reportaría éxito y **no cambiaría ni una fila**.

El repo tiene 39 migraciones con `RunPython`; al menos nueve escriben filas, y
sus tablas destino sí tienen RLS: `lead`, `opportunity`, `accounts`, `invoice`,
`estimate`, `csat_survey`, `business_calendar` (`organization`, `profile` y
`portal_access_token` no lo tienen).

Matices que importan:

- **Las migraciones ya aplicadas no están en riesgo**: corrieron como `postgres`,
  que tiene `BYPASSRLS`. El riesgo es para **migraciones de datos futuras**.
- El éxito del entorno aislado **no prueba lo contrario**: ahí las migraciones
  corrieron contra tablas **vacías**, y con tablas vacías «0 filas afectadas» es
  el resultado correcto. No se puede distinguir de «0 porque RLS». Por eso lo
  medí aparte, con filas reales.

`[DECISIÓN]` Es un problema real y **no lo parcheé**. Tres salidas posibles, todas
suyas: (a) que cada migración de datos fije `app.current_org` por organización;
(b) conceder `BYPASSRLS` a `crm_migrator` **solo durante la migración** — repone
justo el privilegio que B-7 quita, aunque en una identidad que no sirve
peticiones; (c) exigir que las migraciones de datos se ejecuten con una
identidad administrativa declarada caso por caso. No elijo por usted.

## 9.5 Las 69 tablas sin RLS

Un runtime sin `BYPASSRLS` las ve completas. Incluyen las 7 de campo ya
reportadas en pasos anteriores (`campo_orden_trabajo`, `campo_asignacion_trabajo`,
`campo_evento_trabajo`, `campo_evidencia_trabajo`, `campo_mutacion_idempotente`,
`campo_work_type`, `campo_work_type_version`), las tablas puente `*_assigned_to`
/ `*_tags` / `*_teams`, `profile`, `users`, `organization`, `personal_access_token`,
`portal_access_token`, `magic_link_token`, `security_audit_log`,
`solicitudes_solicitudservicio` y las de Django.

`[RIESGO]` Sigue abierto y **B-7 no lo cambia**: hoy tampoco están protegidas,
porque el runtime tiene `BYPASSRLS` y las 66 con RLS tampoco filtran. Después de
B-7, 66 quedan realmente protegidas y estas 69 siguen dependiendo del código.
**B-7 mejora la situación; no la completa.**

---

# 10. RUNTIME REAL `[MEDIDO]`

Qué ejecuta de verdad el CRM contra la base, comprobado ejecutándolo:

| Operación | ¿La necesita? | Evidencia |
|---|---|---|
| `SELECT` | sí | ítems 3, 8, 9 del smoke |
| `INSERT` | sí | ítems 4, 5, 6, 7 |
| `UPDATE` | sí | ítem 4 (PUT de un caso), ítem 5 |
| `DELETE` | sí (el ORM lo usa en cascadas y limpiezas) | concedido; no ejercido por el smoke |
| secuencias (`nextval`) | sí | basta `USAGE`; con `UPDATE=0` todo pasó |
| `set_config('app.current_org', ...)` | **sí, crítico** | middleware `SetOrgContext` y `reset_rls_context` del pool |
| transacciones + `SELECT ... FOR UPDATE` | sí | los servicios de M03/M09 bloquean OT, plan y org |
| `CREATE/ALTER/DROP TABLE` | **no** | solo migraciones |
| `CREATE EXTENSION` | **no** | ninguna migración pendiente la pide |
| esquema `asistente` | **no** | es del motor |
| `TRUNCATE`, `REFERENCES`, `TRIGGER` | **no** | 13/13 sin ellos |

Procesos que deben usar `crm_user`: gunicorn (peticiones), Celery worker y
Celery beat. Procesos que necesitan identidad administrativa: **solo `migrate`**
(y `verificar_credenciales --proposito migraciones`).

---

# 11. MIGRACIONES `[MEDIDO]`

## 11.1 El mecanismo ya existe en el repo, sin desplegar

`django-crm/docker/backend/entrypoint.sh` ya separa las dos identidades:

```sh
if [ -n "${MIGRATOR_DBUSER:-}" ]; then
    DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" \
        python manage.py migrate --noinput
else
    python manage.py migrate --noinput
fi
```

El override vale **solo para `migrate`**; gunicorn arranca después con la
variable de tráfico sin tocar. `docker-compose.prod.yml` ya pasa
`MIGRATOR_DBUSER: ${MIGRATOR_DBUSER:-}` y `.env.example` documenta el sufijo de
Supavisor y el `ALTER ROLE ... SET role = crm_owner`.

`[MEDIDO]` En el `.env` de producción, `MIGRATOR_DBUSER` y `MIGRATOR_DBPASSWORD`
están **vacíos**. El mecanismo está escrito y no está en uso.

> Aplico aquí la advertencia del propio CLAUDE.md —«lo que se verifica no es lo
> que está desplegado»— y la suya: **que exista la estructura técnica no
> significa que sea una política aprobada.** Lo reporto como disponible, no como
> decidido.

## 11.2 La guarda `verificar_credenciales` funciona `[MEDIDO]`

Ya existe `python manage.py verificar_credenciales --proposito {trafico|migraciones} [--con-base]`.
La ejecuté en las cuatro combinaciones contra el entorno aislado:

| Identidad | Propósito | Salida | Veredicto |
|---|---|---|---|
| `crm_user` | `trafico` | exit 0 | sin problemas |
| `crm_user` | `migraciones` | **exit 1** | `[ERROR A]` no puede ejercer el rol dueño de 135 tablas |
| `crm_migrator` | `trafico` | **exit 1** | `[ERROR B]` es la credencial de migraciones |
| `crm_migrator` | `migraciones` | exit 0 | sin problemas |

Acierta en la diagonal correcta y **falla al arrancar**, con el motivo escrito,
en vez de reventar a mitad de una migración.

`[HALLAZGO]` El texto de `[ERROR B]` justifica el rechazo diciendo que «un dueño
se saltea su propia política RLS salvo que esté FORCE». Medí que **FORCE sí está
activo** en las 66 tablas, así que ese motivo concreto ya no aplica. El veredicto
sigue siendo correcto por otras razones (las 69 tablas sin RLS, y el principio de
no servir peticiones con el rol dueño), pero **la justificación escrita está
desactualizada**. No la modifiqué.

## 11.3 Migraciones ejecutadas como `crm_migrator` `[MEDIDO]`

En el entorno aislado, `manage.py migrate` completo como `crm_migrator`:

```
135 tablas creadas, TODAS con dueño crm_owner
"Re-stamped RLS policies on 45 table(s)"
"Stamped RLS policies on 6 pipeline table(s)"
"Políticas RLS estampadas en 6 tabla(s) de operaciones"
```

Esto **responde la pregunta que `DESPLIEGUE.md` dejaba abierta**: sí, un migrador
que no es dueño puede ejecutar `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`,
porque `ALTER ROLE crm_migrator SET role = crm_owner` lo hace actuar *como* el
dueño. No hace falta `SUPERUSER`.

La limitación está en §9.4 (migraciones de **datos**), no en las de estructura.

---

# 12. SMOKE TESTS `[MEDIDO]` — 13 de 13

Los 13 ítems del bloque K, ejecutados **enteros como `crm_user`** contra el
entorno aislado. Ningún efecto externo: no se llamó WispHub ni SmartOLT; el
ciclo del Supervisor corre en Shadow Mode.

```
current_user=crm_user  session_user=crm_user  rolsuper=False  rolbypassrls=False
```

| # | Ítem | Método | Resultado |
|---|---|---|---|
| 1 | login | HTTP `POST /api/auth/login/` | HTTP 200, token emitido |
| 2 | health | HTTP `GET /healthz/` | anónimo 403 · autenticado 200 |
| 3 | listar casos | HTTP `GET /api/cases/` | HTTP 200, `cases_count=5` |
| 4 | crear/editar | HTTP `POST` + `PUT /api/cases/` | INSERT y UPDATE **persistidos**, verificado con conexión independiente |
| 5 | actividades | servicio `operaciones.actividades` | creada + asignada + iniciada; estado `en_gestion` persistido |
| 6 | programación | servicio `operaciones.programacion` | orden programada/reprogramada, línea persistida, jornada con 1 línea |
| 7 | propuestas Supervisor | `supervisor.correr_ciclo` (Shadow Mode) | ciclo completo, propuestas escritas y leídas por conexión independiente |
| 8 | reportes | `operaciones.indicadores` | 5 reportes: diario, pendientes, programación, compromisos, supervisor |
| 9 | tenant isolation | ORM + HTTP | ORG-B tiene 1 caso; con contexto MicroPyramid el ORM ve **0**; fuga por HTTP **0** |
| 10 | transacción | `atomic` + conexión independiente | tras commit, 1 fila (esperado 1) |
| 11 | rollback | `atomic` que revienta | tras rollback, 0 filas (esperado 0) |
| 12 | permisos | 7 operaciones administrativas | 7 de 7 bloqueadas |
| 13 | RLS | políticas como `crm_user` | sin BYPASSRLS; 0 filas sin contexto; sin fuga cruzada; UPDATE cruzado 0; INSERT cruzado rechazado; FORCE en todas |

**La persistencia se verifica siempre con una conexión `psycopg` independiente
del ORM**, no leyendo de vuelta por el mismo camino que escribió. Un ORM puede
devolver lo que tiene en memoria.

El script es reproducible: si la orden ya quedó programada por una corrida
anterior, el ítem 6 toma la ruta `reprogramar_orden`, que es el camino real, en
vez de fallar.

Ubicación: `scratchpad/smoke_b7.py`. **No lo agregué al repo ni hice commit.**

### Hallazgo del ítem 2, independiente de B-7 `[HALLAZGO]`

`GET /healthz/` devuelve **403 sin autenticación**: la ruta no está en
`EXEMPT_PATHS` de `RequireOrgContext`, así que exige contexto de organización.

Lo medí **también como superusuario**: 403 igual. **No lo causa la identidad de
base**, así que no es un fallo de B-7. Anotado aparte: `docker-compose.prod.yml`
no declara `healthcheck` para el backend (el único que hay es el de redis), así
que hoy nada depende de esa ruta — pero un health check que exige login no sirve
como health check.

---

# 13. ENTORNO AISLADO `[MEDIDO]`

```
pg-b7     postgres:16-alpine          base de pruebas
runner-b7 crm-agentico-backend:latest el backend real, mismo código
redis-b7  redis:7-alpine              broker para Celery
net-b7    red docker propia
```

Montajes: `django-crm/backend` → `/app` (rw), `django-crm/docs` → `/docs` (ro),
el repo → `/repo` (ro).

**Credenciales productivas en el entorno: 0.** Medido con
`env | grep -ciE "supabase|dokploy|rapilink|b8_|DBPASSWORD|API_KEY"` → **0**.

> Una medición anterior dio `2`. Investigado: eran `SECRET_KEY` y
> `DJANGO_SECRET_KEY`, que coincidían con el patrón por contener la subcadena
> `prod` en un valor que yo mismo había inventado — ni de la imagen (que no trae
> ninguna) ni de ningún archivo del repo (comparado por hash). Aun así recreé el
> contenedor con un valor explícitamente desechable
> (`b7-entorno-aislado-descartable-...`) para que el conteo sea 0 sin discusión.

Roles creados en el aislado replicando la forma de producción: `crm_owner` (sin
LOGIN), `crm_migrator` (miembro de `crm_owner`, con `SET role = crm_owner`),
`crm_user` (sin super/bypass/createdb/createrole). Contraseñas desechables,
usadas solo ahí.

Datos: `seed_data` (MicroPyramid: 5 casos, 20 leads, 10 oportunidades, 50
facturas…) y `seed_campo_demo` (Rapilink Telecomunicaciones: 1 OT, 1 técnico,
1 tipo de trabajo publicado), más ORG-A y ORG-B para las pruebas de aislamiento.
**La siembra se hizo como superusuario a propósito**: representa los datos que ya
existen en producción, y así un fallo de siembra no se confunde con un fallo de
permisos del runtime.

---

# 14. PRODUCCIÓN

## 14.1 Qué se hizo contra producción

**Solo lectura, salvo el incidente de §0.** Ninguna migración, ningún `GRANT`,
ningún `REVOKE`, ningún rol creado, ningún dato modificado, `DBUSER` sin tocar.

Se abrieron dos conexiones de escritura potencial:
- una como `postgres` (la del `.env`), que por el fallo de §0 **creó una tabla**;
- una como `crm_migrator` con la contraseña del archivo externo, **de solo
  lectura efectiva** (sin `autocommit`, `read_only` sí aplicó), usada para una
  única consulta de identidad (§7). La contraseña no se imprimió.

## 14.2 Baseline al cierre

| Clave | Valor | ¿Coincide con lo conocido? |
|---|---|---|
| `organization` | 2 | sí |
| `case` | 213 | sí |
| `activity` (total) | 618 | tabla **viva**: crece con el uso real del CRM |
| `activity` con `entity_type IN ('ActividadOperativa','PropuestaSupervisor')` | **0** | **sí — nada de M02/M09 tocó producción** |
| `operaciones_actividad` | 0 | sí |
| `operaciones_propuesta_supervisor` | 0 | sí |
| `operaciones_programacion_orden` | 0 | sí |
| `operaciones_novedad` | 0 | sí |
| `campo_orden_trabajo` | 3 | sí |
| `campo_asignacion_trabajo` | 3 | sí |
| `campo_mutacion_idempotente` | 14 | sí (filas del 8–9 de septiembre) |
| `django_migrations` | 192 | sí — **ninguna migración nueva aplicada** |
| roles | 41 | sí |
| **tablas en `public`** | **136** | **NO — eran 135. La diferencia es §0.** |

El contador crudo de `activity` **no** sirve como prueba de que producción está
intacta: es una tabla viva. El indicador válido es el filtro por `entity_type`,
que está en **0**.

---

# 15. ROLLBACK `[DISEÑO]`

Bloque M: `crm_user → postgres`, **únicamente como contingencia controlada**.

## 15.1 Condición de rollback

Se ejecuta si, tras el cambio, aparece **cualquiera** de estas:

1. El backend no arranca: `verificar_credenciales --proposito trafico` sale con
   código distinto de 0, o gunicorn no llega a servir.
2. `permission denied` o `must be owner of` en los logs del backend, para una
   operación que el smoke test no cubrió.
3. Un endpoint del smoke test que pasaba devuelve 5xx.
4. Aislamiento roto **en cualquier dirección**: un tenant ve filas de otro, o un
   tenant deja de ver las suyas (cero filas donde antes había).
5. El scheduler / Celery beat deja de ejecutar trabajos.

**No** es condición de rollback: un error puntual en una ruta no crítica cuyo
permiso concreto esté identificado. Ahí corresponde conceder **ese** permiso, no
volver atrás — es literalmente lo que pide el bloque G («determinar exactamente
qué permiso falta»).

## 15.2 Qué se revierte, y qué no

El rollback es **solo de configuración**:

```
DBUSER: crm_user.<sufijo>  ->  postgres.<sufijo>
DBPASSWORD: la de crm_user ->  la de postgres
```

y reiniciar backend, Celery worker y Celery beat.

**No se revierte con `DROP`.** No hay nada que borrar: no se crean roles, no se
crean tablas, no se eliminan políticas. Los `GRANT`/`REVOKE` de §8.3, si se
aplican, son independientes del `DBUSER` y **no hace falta deshacerlos para
volver atrás** — `postgres` tiene `BYPASSRLS` y no depende de los grants de
`crm_user`. Esto respeta su regla: *no hacer DROP manual como mecanismo de
rollback*.

`MIGRATOR_DBUSER` puede quedarse puesto: el entrypoint lo usa solo para
`migrate`, y migrar como `crm_migrator` es correcto con cualquier `DBUSER` de
tráfico.

## 15.3 Quién lo ejecuta

Quien tenga acceso a Dokploy y a las variables de entorno del servicio. **No yo**:
no tengo acceso a Dokploy, y por eso el `DBUSER` efectivo hubo que medirlo desde
la base (§3) en vez de leerlo de la configuración del despliegue.

## 15.4 Cómo verificar que el rollback funcionó

1. `verificar_credenciales --proposito trafico --con-base` → exit 0.
2. Desde la base: `select usename from pg_stat_activity where datname=current_database()`
   → aparece `postgres` para el backend.
3. Los 13 ítems del smoke test, adaptados a producción **sin los que escriben**
   (1, 2, 3, 8, 9, 12, 13 son de solo lectura o de permisos).
4. Contadores de §14.2 sin cambios.

## 15.5 Qué evidencia recoger

Antes: `DBUSER` anterior, salida de `verificar_credenciales`, contadores,
`pg_stat_activity`. Durante: hora del cambio, hora del reinicio, primer error
con su texto completo. Después: los cuatro puntos de §15.4, y **el permiso exacto
que faltó** si el motivo fue un `permission denied` — sin eso, la próxima Fase 2
repite el mismo tropiezo.

## 15.6 Límite honesto de este diseño

`[RIESGO]` **El rollback está diseñado, no probado.** Probarlo exige hacer el
cambio productivo, que es Fase 2. Lo que sí está demostrado es que el camino de
ida funciona (13/13) y que la vuelta es un cambio de dos variables de entorno
más un reinicio — la operación más simple posible, sin estado que deshacer.

---

# 16. RIESGOS

| # | Riesgo | Evidencia | Impacto | ¿Bloquea Fase 2? |
|---|---|---|---|---|
| R1 | **Tabla creada por error en producción** | §0, `tablas en public = 136` | Producción fuera de su baseline | **SÍ** — hay que revertirla antes |
| R2 | **Migraciones de datos futuras afectan 0 filas en silencio** bajo `crm_migrator` | §9.4: `UPDATE 0` con 3 filas reales, sin error | Alto: backfill que reporta éxito y no hace nada | **SÍ** — necesita una decisión suya (§9.4) |
| R3 | `crm_user` tiene `TRUNCATE`/`REFERENCES`/`TRIGGER` y `UPDATE` de secuencias de más | §8.3 | Medio: `TRUNCATE` vacía una tabla sin pasar por RLS de fila | No, pero Fase 2 debería corregirlo |
| R4 | 69 tablas sin RLS siguen sin proteger | §9.5 | Medio: B-7 mejora, no completa | No |
| R5 | `motor_user` conserva `BYPASSRLS` | §6 | Medio; hoy alcanza 1 tabla de `public` | No (fuera del alcance de B-7) |
| R6 | Secreto JWT legible por `crm_user` en `pg_db_role_setting`; además quedó impreso en esta sesión | §8.4 | Alto si la transcripción no es un lugar seguro | No, pero exige decisión sobre rotación |
| R7 | Kill switch: `motor_user` no puede `SET ROLE autonomia_operador`; la salida de emergencia existe y no está cableada a la ruta | §6 | Alto **si se activa autonomía** | No (autonomía está detenida) |
| R8 | El default `DBUSER="postgres"` en `settings.py` convierte una variable ausente en el rol más privilegiado | §3 | Medio | No |
| R9 | `/healthz/` responde 403 sin autenticación | §12 | Bajo hoy (nada depende de él) | No |
| R10 | Rollback diseñado, no probado | §15.6 | Medio | No |
| R11 | Si alguien cambiara `DBPORT` a 6544 (transaction mode), `app.current_org` se filtraría entre tenants | §7 | Crítico | No — pero **el puerto no debe tocarse** |

---

# 17. DECISIONES PENDIENTES

Todas suyas. No tomé ninguna.

1. **`[BLOQUEANTE]` Revertir `public.b7_no_deberia_existir`** (§0). El `DROP` fue
   bloqueado por la política de permisos de la sesión; necesito su autorización o
   que lo ejecute usted.
2. **`[BLOQUEANTE]` Qué hacer con las migraciones de datos bajo RLS** (§9.4):
   contexto por organización, `BYPASSRLS` temporal solo para migrar, o identidad
   administrativa declarada caso por caso.
3. **Rotar o no el secreto JWT** que quedó impreso en esta sesión (§8.4).
4. **Aplicar o no los `REVOKE`** de `TRUNCATE`/`REFERENCES`/`TRIGGER`/secuencias
   sobre `crm_user` (§8.3).
5. **Poblar o no `MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD`** en producción (§11.1).
   El mecanismo existe en el repo y está sin usar; que exista no es una política
   aprobada.
6. **Encender o no `CRM_CREDENCIALES_ESTRICTO=1`**, y cuándo. El propio
   `.env.example` advierte: **después** de la transición, nunca antes — hoy
   impediría arrancar el backend.
7. **Ventana de cambio** para Fase 2.
8. Si conviene poner `search_path` explícito a `crm_user` (§7). Medido: **no hace
   falta**. Es una decisión de higiene, no de funcionamiento.

---

# 18. SIGUIENTE PASO RECOMENDADO

**No ejecutar Fase 2 todavía.** En este orden:

1. **Revertir §0.** Volver a 135 tablas y confirmarlo.
2. **Cerrar la decisión de §9.4** (migraciones de datos bajo RLS). Es la única
   cuestión técnica que puede morder *después* del cambio, cuando ya nadie está
   mirando.
3. **Decidir sobre el secreto de §8.4.**
4. Recién entonces, autorizar Fase 2 con: ventana de cambio, los `REVOKE` de
   §8.3 si los aprueba, `MIGRATOR_DBUSER` poblado, y el rollback de §15 impreso
   y a mano.

## Lo que Fase 2 va a necesitar de producción, para que no haya sorpresas

- **Cambiar** `DBUSER`/`DBPASSWORD` del backend, Celery worker y Celery beat.
- **Poblar** `MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD`.
- **Opcional** (§8.3): cuatro `REVOKE` sobre `crm_user`.
- **No** hace falta crear ningún rol: `crm_user`, `crm_migrator` y `crm_owner`
  ya existen con la forma correcta.
- **No** hace falta tocar `motor_user`, ni el kill switch, ni M09/M11, ni el
  puerto del pooler.

---

## RESUMEN EJECUTIVO

**Fase 1: GO.** Los diez criterios del bloque P están cumplidos y medidos.
`crm_user` y `crm_migrator` ya existen en producción con la forma correcta, así
que B-7 resultó ser **más un cambio de configuración que de infraestructura**: el
entrypoint ya sabe separar las dos identidades, la guarda `verificar_credenciales`
ya acierta en las cuatro combinaciones, y los `ALTER DEFAULT PRIVILEGES` ya están
puestos.

Lo demostrado, no supuesto: el pooler entrega el rol base y conserva el `SET
ROLE`; `crm_user` hace todo lo que el runtime necesita con **solo** cuatro
privilegios de tabla y `USAGE` de secuencia; las siete operaciones
administrativas le están vedadas; RLS aísla de verdad —comprobado desarmándolo—
y `FORCE` alcanza incluso al dueño; los 13 ítems del smoke pasan.

Dos cosas empañan el resultado y las pongo por delante, no al final:

1. **Creé una tabla en producción por error**, por confiar en un `read_only` que
   `autocommit` anulaba. Está reportada, medida y sin revertir porque el `DROP`
   fue bloqueado.
2. **`FORCE RLS` rompe en silencio las migraciones de datos futuras** bajo
   `crm_migrator`: `UPDATE 0` sobre tres filas reales, sin error. No lo parcheé.

**Fase 2: NO-GO todavía**, y no por falta de evidencia técnica —está completa—
sino porque quedan dos decisiones suyas que son bloqueantes y una ventana de
cambio por definir.

---

**No se hizo commit. No se activó autonomía. No se modificó M09/M11. No se tocó
el kill switch. No se creó ningún rol en producción. No se cambió `DBUSER`.**
