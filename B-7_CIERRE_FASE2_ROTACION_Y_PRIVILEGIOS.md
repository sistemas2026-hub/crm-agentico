# B-7 — CIERRE DE FASE 2

## ROTACIÓN DE SECRETO · REDUCCIÓN DE PRIVILEGIOS · CAMBIO DE RUNTIME

Fecha: 2026-09-19

# ROTACIÓN BLOQUEADA POR FALTA DE ACCESO A DOKPLOY.

No la simulé. Como la rotación es la primera compuerta y de ella dependen el
retiro del GUC (§C) y el cambio de `DBUSER` (§F), esos dos pasos **no se
ejecutaron**.

La decisión 2 —los cuatro `REVOKE`— no depende de la rotación y estaba
autorizada sin condición previa: **está aplicada y verificada**.

Sin commit. Sin autonomía. Sin tocar M09, M11 ni el kill switch. Ninguna
modificación de producción fuera de las autorizadas.

---

# 1. ROTACIÓN: **BLOCKED**

## Verificación del acceso, no suposición

| Comprobación | Resultado |
|---|---|
| variables `DOKPLOY_*` en `.env` | **0** |
| credenciales/token de Dokploy en el repo | **ninguna** — solo menciones en prosa de `DESPLIEGUE.md` |
| CLI `dokploy` instalado | **NO** |
| `~/.dokploy` (config de sesión) | **no existe** |

Dokploy es una interfaz **web** en el VPS `86.48.18.185`. `DESPLIEGUE.md` la
describe como un flujo de navegador (formularios, sesión que caduca con
`UNAUTHORIZED`, «Docker Terminal»). No hay API ni token con el que operar.

No inventé una API. No modifiqué el secreto desde SQL. No escribí ningún secreto
nuevo en código. No imprimí ni copié ningún valor.

## Instrucciones exactas para quien sí tenga acceso

Contexto medido que hace falta para no romper nada:

- El secreto es el GUC `app.settings.jwt_secret` de la base `postgres`, y
  **verifica la firma HS256 de `SUPABASE_SERVICE_ROLE_KEY`** (demostrado en el
  informe de Fase 2, §5.2).
- El stack de Supabase vive en el proyecto de Dokploy
  **`automatizacion-rp-supabase-dgimpk`** — no en `crm-agentico-*`.
- Servicios de ese stack conectados a la base ahora mismo (medido):
  **PostgREST 14.12** (`authenticator`), **Realtime** (`supabase_admin`, 9
  conexiones), **Storage** (`supabase_storage_admin`), **Supavisor**
  (`pgbouncer`).

### Pasos

1. **Generar** un secreto nuevo de al menos 40 caracteres con el gestor de
   secretos. No a mano, no en un archivo del repo.
2. En Dokploy, proyecto `automatizacion-rp-supabase-dgimpk`, poner
   **`JWT_SECRET`** con el valor nuevo en **todos** los servicios que lo llevan:
   `kong`, `auth` (GoTrue), `rest` (PostgREST), `realtime`, `storage` y `studio`
   si lo tiene.
3. **Regenerar `ANON_KEY` y `SERVICE_ROLE_KEY`**: son JWT firmados con
   `JWT_SECRET`. Con el secreto nuevo, los actuales dejan de validar. Firmar los
   nuevos con las mismas *claims* (`role: anon` / `role: service_role`,
   `iss: supabase`, y el `exp` que se decida).
4. **Redesplegar** los servicios. `DESPLIEGUE.md` lo advierte dos veces: Dokploy
   aplica los cambios al recrear los contenedores, **no al guardar el
   formulario**.
5. Actualizar `SUPABASE_SERVICE_ROLE_KEY` donde esté guardada (el `.env` del
   despliegue y el `.env` local de cada colaborador). **Nunca en código, nunca en
   SQL.**
6. Avisarme para ejecutar §C (retiro del GUC), §D (prueba de escalamiento) y §F
   (cambio de `DBUSER`).

### Verificación posterior exigida por §A — quién puede hacer cada punto

| # | Verificación | Quién |
|---|---|---|
| 1 | el servicio que consume `SERVICE_ROLE_KEY` inicia | quien tenga Dokploy |
| 2 | operaciones legítimas funcionan | quien tenga Dokploy |
| 3 | el secreto **nuevo** funciona | quien tenga Dokploy |
| 4 | **el secreto anterior deja de funcionar** | **yo puedo demostrarlo** — §5 |
| 5 | no hay secretos impresos | ✅ ya verificado: `grep` sobre los tres informes = **0** coincidencias |

### Impacto, documentado ANTES de ejecutar

| Se invalida | Alcance |
|---|---|
| `SERVICE_ROLE_KEY` y `ANON_KEY` actuales | quien los tenga guardados; el Studio de Supabase |
| Sesiones emitidas por GoTrue | si hubiera usuarios autenticados por Supabase Auth |
| Conexiones de Realtime autenticadas por JWT | se reconectan con el token nuevo |
| **Sesiones y tokens del CRM (Django)** | **NO se ven afectadas** — usan `SECRET_KEY`, otro secreto |
| **Motor ↔ base (`motor_user`)** | **NO se ve afectado** — psycopg directo, sin JWT |
| **CRM ↔ base** | **NO se ve afectado** — psycopg directo, sin JWT |

`[MEDIDO]` `DESPLIEGUE.md` §«Dónde vive cada cosa» dice que **esta plataforma usa
de Supabase solo Postgres: ni Kong, ni GoTrue, ni Storage, ni Realtime**. Y el
`grep` lo confirma: **ningún archivo de código de este repo lee
`SUPABASE_SERVICE_ROLE_KEY`**. El riesgo de la rotación para *esta* plataforma es
por tanto bajo; el impacto real es sobre el Studio de Supabase y cualquier
consumidor externo que no esté en este repo.

Eso **no reduce la urgencia**: los servicios están corriendo y conectados a la
base, así que el token forjado seguiría siendo válido contra ellos aunque
nosotros no los usemos.

---

# 2. SECRETO ANTERIOR INVALIDADO: **BLOCKED**

Depende de §1. El secreto actual sigue vigente y sigue siendo legible por
`crm_user`.

---

# 3. GUC: **NO EJECUTADO** (correctamente bloqueado)

Su decisión 3 lo autoriza «**SOLO DESPUÉS DE LA ROTACIÓN Y VERIFICACIÓN**». La
rotación no ocurrió, así que **no toqué el GUC**.

Lo que ya está demostrado y queda listo para cuando se autorice:

- **Ninguna función SQL de la base lo lee** — medido sobre `pg_get_functiondef`
  de todas las funciones no-C: cero coincidencias con `app.settings.jwt`.
- `pgjwt` **no está instalada** (las únicas `sign` son `pg_catalog.sign`, la
  función matemática).
- No hay GUC `pgrst.*` de configuración en base.

`[LÍMITE HONESTO]` Puedo demostrar que ninguna función **de la base** lo usa. **No
puedo demostrar que ningún servicio externo lo lea por SQL.** Comprobarlo exige
ver la configuración del stack en Dokploy — el punto 3 de su §C («verificar que
PostgREST/servicios siguen funcionando mediante su mecanismo oficial») solo lo
puede cerrar quien tenga ese acceso.

Comando previsto, para cuando corresponda:

```sql
ALTER DATABASE postgres RESET app.settings.jwt_secret;
ALTER DATABASE postgres RESET app.settings.jwt_exp;
```

---

# 4. CUATRO REVOKE: **PASS**

## 4.1 Ensayo antes de tocar producción

No apliqué a producción un comando que no hubiera visto funcionar. Dos ensayos en
`pg-b7`:

**Ensayo 1 — ¿el comando quita lo que dice?**

```
ANTES : TRUNCATE=135/135 REFERENCES=135/135 TRIGGER=135/135  secuencias UPDATE=51/51
DESPUÉS: TRUNCATE=0/135   REFERENCES=0/135   TRIGGER=0/135    secuencias UPDATE=0/51
         SELECT/INSERT/UPDATE/DELETE intactos 135/135/135/135, secuencias USAGE/SELECT 51/51
```

**Ensayo 2 — ¿funciona en la condición real de producción?** En producción el
otorgante es `crm_owner` y yo ejecuto como `postgres`, **que no es
superusuario**. Un `REVOKE` que no es del otorgante puede no hacer nada y no
avisar. Reproduje la condición exacta: creé en `pg-b7` un rol
`imita_postgres` (no superusuario, miembro de `crm_owner`), hice que `crm_owner`
concediera y que ese rol revocara.

```
otorgante(s) de TRUNCATE: crm_owner
revocando como imita_postgres (nosuperuser, solo miembro de crm_owner):
  activity TRUNCATE=false  REFERENCES=false  TRIGGER=false
  activity SELECT (no debe cambiar)=true
  secuencia UPDATE=false   USAGE (no debe cambiar)=true
```

Funciona. El rol de ensayo se eliminó del entorno aislado.

## 4.2 Inventario real

```
otorgante de TRUNCATE/REFERENCES/TRIGGER a crm_user: crm_owner (387 concesiones)
ninguno llega vía PUBLIC
6 tablas NO los tenían: las operaciones_* (creadas bajo el default correcto de crm_owner)
secuencias con UPDATE: 51, otorgadas por crm_owner
```

## 4.3 Comandos exactos — generados del inventario, nunca `REVOKE ALL`

**180 sentencias**: 129 de tabla + 51 de secuencia. Forma exacta:

```sql
REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public."account_email" FROM crm_user;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public."accounts"      FROM crm_user;
...
REVOKE UPDATE ON SEQUENCE public."users_groups_id_seq"               FROM crm_user;
```

El script aborta si alguna sentencia generada contiene `REVOKE ALL`. Ninguna lo
contiene.

## 4.4 Aplicación y verificación

```
ejecutando como current_user=postgres session_user=postgres
180 sentencias ejecutadas y confirmadas

VERIFICACIÓN (conexión independiente, solo lectura, transaction_read_only=on):
  tablas    SELECT=135/135 INSERT=135/135 UPDATE=135/135 DELETE=135/135
  tablas    TRUNCATE=0/135 REFERENCES=0/135 TRIGGER=0/135
  secuencias USAGE=51/51 SELECT=51/51 UPDATE=0/51

  los CUATRO privilegios quedaron en 0 : True
  SELECT/INSERT/UPDATE/DELETE intactos : True
```

Lo que **no** se tocó, verificado después: `EXECUTE` sobre funciones de `public`
**149/149**, `USAGE` en `public` = True, y los cuatro privilegios de DML.

Ningún proceso estaba conectado como `crm_user` (**0 conexiones vivas**): el
runtime sigue siendo `postgres`, así que el `REVOKE` no interrumpió nada.

## 4.5 `[HALLAZGO]` Un quinto privilegio innecesario — y un error mío

**`crm_user` tiene `CREATE` sobre el esquema `public` en producción.**

```
ACL de public: pg_database_owner=UC/... | =U/... | postgres=U/... |
               service_role=U/... | crm_user=UC/... | crm_owner=UC/...
                                              ^^ C = CREATE, concesión explícita
crm_user CREATE=True   crm_migrator CREATE=True   motor_user CREATE=False
```

**En mi informe de Fase 1 escribí «CREATE en el esquema public: False» dentro del
bloque de producción. Era el valor del entorno aislado, atribuido a producción
sin medirlo.** Es el mismo error que cometí con «0 columnas» de la tabla
accidental: afirmar un número que no había comprobado.

Consecuencia: `crm_user` puede crear tablas en `public` (no alterar ni borrar las
existentes — no es dueño). Es un quinto privilegio por encima del mínimo, **y no
está entre los cuatro autorizados**, así que **no lo revoqué**. Su §J es
explícito: ninguna modificación distinta de las aprobadas.

`[DECISIÓN]` Si quiere cerrarlo:
`REVOKE CREATE ON SCHEMA public FROM crm_user;` — el entorno aislado corre con
`CREATE=False` y pasa 18/18, así que está demostrado que sobra.

## 4.6 `[HALLAZGO]` El REVOKE es reversible por accidente

```
ALTER DEFAULT PRIVILEGES vigentes:
  quien=crm_owner  tipo=r  acl=crm_user=arwd/crm_owner          <-- correcto
  quien=crm_owner  tipo=S  acl=crm_user=rU/crm_owner            <-- correcto
  quien=postgres   tipo=r  acl=crm_user=arwdDxtm/postgres       <-- D,x,t vuelven
  quien=postgres   tipo=S  acl=crm_user=rwU/postgres            <-- w (UPDATE) vuelve
```

**Una tabla nueva creada por `postgres` volvería a conceder a `crm_user` los tres
privilegios de tabla; una secuencia nueva, el `UPDATE`.** Hoy las migraciones
corren como `postgres` (`DBUSER` sin cambiar), así que **la próxima migración
desharía parte de este `REVOKE`**.

El default de `crm_owner` ya es el correcto (`arwd` / `rU`). O sea: el `REVOKE`
se vuelve **durable en cuanto las migraciones corran como `crm_migrator` →
`crm_owner`**, que es justamente lo que hace `MIGRATOR_DBUSER`.

`[DECISIÓN]` Dos caminos, ninguno tomado por mí: (a) poblar
`MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD` —lo resuelve solo—; o (b) además,
`ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE TRUNCATE,
REFERENCES, TRIGGER ON TABLES FROM crm_user;` y el equivalente para secuencias.

---

# 5. PRUEBA DE ESCALAMIENTO: **BLOCKED**

Su §D pide demostrar que `crm_user` ya **no** puede obtener el secreto anterior,
firmar un `service_role` válido, recuperar `BYPASSRLS` por esa vía ni alcanzar
datos de otro tenant. **Esa prueba solo tiene sentido después de la rotación y
del retiro del GUC.** Ninguno de los dos ocurrió, así que no la ejecuté.

Lo que sí puedo declarar, medido: **la vía sigue abierta.**

```
app.settings.jwt_secret legible por: crm_user, crm_migrator, motor_user,
                                     authenticator, anon, authenticated, app_backend
ACL de pg_db_role_setting: ... | =r/supabase_admin      <-- PUBLIC lee
service_role: bypassrls=TRUE, DML sobre 129/135 tablas de public
authenticator -> SET ROLE service_role : True
PostgREST 14.12 corriendo y conectado a la base
```

Los cuatro `REVOKE` **no cierran esta vía** y nunca pretendieron hacerlo: quitan
privilegios SQL directos, no la capacidad de leer un secreto y firmar un token.
Decirlo al revés sería vender el `REVOKE` como algo que no es.

`[LÍMITE HONESTO]` La vía exige además alcanzar PostgREST o Kong. **No probé si
están expuestos a internet** — habría sido una petición a producción que nadie
autorizó. Lo que está probado es el lado de la base: el secreto es legible y el
rol destino tiene `BYPASSRLS`.

## Prueba que ejecutaré cuando se autorice, ya diseñada

Sin crear ni modificar datos de negocio:

1. Como `crm_user`, leer `pg_db_role_setting` → debe devolver **0 filas** con
   `jwt` (GUC retirado) o el valor **nuevo** (si se conserva).
2. Verificar la firma HS256 del `SERVICE_ROLE_KEY` **anterior** con el secreto que
   `crm_user` pueda leer → **debe fallar**. (Verificación criptográfica local, no
   se presenta ningún token a ningún servicio.)
3. Confirmar `crm_user`: `rolbypassrls=False`, `rolsuper=False`.
4. Como `crm_user`, con contexto de un tenant, contar filas de **otro** tenant →
   **0**. Solo `SELECT`.

---

# 6. `crm_user`: **PASS**

Smoke completo **después** de los `REVOKE`, con el entorno aislado espejando
exactamente el juego reducido de producción:

```
tablas SELECT/INSERT/UPDATE/DELETE = 135/135/135/135
tablas TRUNCATE/REFERENCES/TRIGGER = 0/0/0
secuencias USAGE/SELECT/UPDATE     = 51/51/0

current_user=crm_user  session_user=crm_user  rolsuper=False  rolbypassrls=False
=== SMOKE TEST B-7: 18/18 items OK ===
```

Ninguna prueba falló, así que no hubo que conceder ningún privilegio. Los dos
ítems que tocan el borde exacto de los `REVOKE`:

- **Ítem 15**: `nextval` funciona con solo `USAGE`; **`setval` queda bloqueado**
  (necesita el `UPDATE` que acabamos de quitar). El borde está donde debe.
- **Ítem 12**: las 7 operaciones administrativas siguen bloqueadas.

---

# 7. `DBUSER` EFECTIVO

```
session_user medido contra la base: postgres
```

**Sin cambiar**, como corresponde: su §F lo condiciona a `[PASS] rotación`,
`[PASS] secreto anterior invalidado` y `[PASS] GUC retirado`, y los tres están en
BLOCKED. No cambié `DBUSER` antes de tiempo.

---

# 8. POOLER

Sin cambios. Lo medido sigue vigente: Supavisor **quita el sufijo de tenant** (se
entra como el rol base), el `SET ROLE` de `ALTER ROLE ... IN DATABASE` sobrevive
al pooler, y `DBPORT=5433` es **session mode** — crítico, porque
`app.current_org` es de alcance de sesión. **No tocar el puerto.**

---

# 9. RLS: **PASS**

```
tablas con RLS      : 66 de 135
tablas con FORCE RLS: 66 de 66
```

Intacto. No se desactivó RLS en ninguna tabla, no se quitó `FORCE`, no se
concedió `BYPASSRLS` a `crm_user` (`rolbypassrls=False`, medido después de los
`REVOKE`).

Ítem 13 del smoke: sin `BYPASSRLS`; 0 filas sin contexto; sin fuga cruzada;
`UPDATE` cruzado = 0; `INSERT` cruzado rechazado; `FORCE` en todas.

---

# 10. TENANT ISOLATION: **PASS**

Ítem 9: ORG-B tiene 1 caso; con contexto de MicroPyramid el ORM ve **0** de
ellos; fuga por HTTP **0**.

---

# 11. SCHEDULER: **PASS**

Ítem 17: `check_overdue_invoices()` —tarea real de Celery beat— corre como
`crm_user`, y lo que importa para RLS: **no deja contexto residual** en la
conexión. `set_rls_context` fija y `clear_rls_context` limpia.

---

# 12. SMOKE TEST: **18/18**

| # | Ítem | Resultado |
|---|---|---|
| 1 | login | HTTP 200, token emitido |
| 2 | health | anónimo 403 (idéntico como superusuario) · autenticado 200 |
| 3 | listar casos | `cases_count=5` |
| 4 | crear/editar | INSERT y UPDATE persistidos, conexión independiente |
| 5 | actividades | creada + asignada + iniciada, `en_gestion` persistido |
| 6 | programación | vía `reprogramar_orden`, línea persistida |
| 7 | propuestas Supervisor | ciclo Shadow Mode completo |
| 8 | reportes | 5 reportes |
| 9 | tenant isolation | 0 filas de otro tenant, fuga HTTP 0 |
| 10 | transacción | 1 fila tras commit |
| 11 | rollback | 0 filas tras rollback |
| 12 | permisos | 7/7 operaciones administrativas bloqueadas |
| 13 | RLS | sin BYPASSRLS, FORCE en todas |
| 14 | locks | `FOR UPDATE NOWAIT` rebota desde otra conexión; advisory lock se toma **y se libera** |
| 15 | secuencias | `nextval` con solo `USAGE`; **`setval` bloqueado** |
| 16 | funciones | `set_config`, `gen_random_uuid`, `hashtext`, `pg_advisory_xact_lock` ejecutan |
| 17 | scheduler | tarea real de beat, sin contexto residual |
| 18 | backfill verificable | con contexto 3/3/3 ÉXITO; sin contexto 0/0/0 **DETECTADO COMO FALLO** |

---

# 13. ROLLBACK

Sin cambios respecto a lo documentado. **No hizo falta**: no hubo cambio de
`DBUSER` que revertir.

Para los cuatro `REVOKE` aplicados, la vuelta atrás —si alguna vez hiciera falta—
es el `GRANT` simétrico generado del mismo inventario. **No es un `DROP`, no
toca datos y no requiere reinicio.** No se necesitó: el runtime no usa `crm_user`
todavía, así que el `REVOKE` no pudo romper nada en marcha (0 conexiones vivas
como `crm_user`, medido).

---

# 14. PRODUCCIÓN

Modificaciones en este paso: **una sola clase, la autorizada.**

| Operación | Autorización | Verificada |
|---|---|---|
| 180 `REVOKE` (TRUNCATE, REFERENCES, TRIGGER, UPDATE de secuencias) sobre `crm_user` | decisión 2, §B | §4.4 |

**No** se hizo: crear tablas · crear roles · cambiar RLS · desactivar FORCE RLS ·
conceder `BYPASSRLS` a `crm_user` · tocar el kill switch · activar autonomía ·
modificar M09 · modificar M11 · rotar el secreto desde SQL · retirar el GUC ·
cambiar `DBUSER` · reiniciar ningún proceso.

Todo lo demás contra producción fue lectura, con `transaction_read_only = on`
verificado en el servidor antes de consultar.

Baseline al cerrar:

```
tablas en public         135    ok
roles                    41     ok
django_migrations        192    ok
tablas con RLS           66     ok
tablas con FORCE RLS     66     ok
case                     213    ok
organization             2      ok
operaciones_actividad    0      ok
```

---

# 15. AUTONOMÍA

**Detenida.** Sin cambios en el nivel de autonomía, el kill switch,
`PropuestaSupervisor`, M09, M11 ni ninguna tool.

---

# 16. GO / NO-GO

## **NO-GO.**

Su §K lo dice sin margen: «Si la rotación no puede realizarse por falta de acceso
a Dokploy: NO-GO. No simularla.»

| | Criterio | Estado |
|---|---|---|
| ❌ | secreto rotado | **BLOCKED** — sin acceso a Dokploy (§1) |
| ❌ | secreto anterior invalidado | **BLOCKED** — depende del anterior |
| ✅ | valor nunca expuesto en informe/log | `grep` sobre los tres informes: **0** coincidencias |
| ❌ | GUC innecesario retirado | **NO EJECUTADO** — su decisión 3 lo condiciona a la rotación |
| ❌ | `crm_user` ya no puede leer el secreto | sigue pudiendo (§5) |
| ✅ | cuatro privilegios innecesarios revocados | **PASS** (§4) |
| ✅ | 18/18 runtime smoke test | **PASS**, después del `REVOKE` (§6) |
| ✅ | RLS PASS | 66/66 con FORCE (§9) |
| ✅ | tenant isolation PASS | (§10) |
| ✅ | scheduler PASS | (§11) |
| ✅ | backfill verificable | (§12, ítem 18) |
| ❌ | `DBUSER` efectivo = `crm_user` | **`postgres`** — no se cambió, correctamente (§7) |
| ✅ | motor sigue como `motor_user` | sin tocar |
| ✅ | migraciones separadas | mecanismo listo; `MIGRATOR_DBUSER` aún vacío |
| ✅ | rollback definido | (§13) |
| ✅ | aplicación estable | ningún proceso reiniciado, ninguna conexión afectada |

## Qué queda, en orden

1. **`[BLOQUEANTE]` Rotar el secreto** siguiendo §1. Es lo único que impide
   avanzar.
2. Avisarme. Entonces: retirar el GUC (§3), correr la prueba de escalamiento
   (§5), y cambiar `DBUSER` con las verificaciones de su §G.
3. `[DECISIÓN]` El quinto privilegio: `REVOKE CREATE ON SCHEMA public FROM
   crm_user` (§4.5). Demostrado innecesario, fuera de lo autorizado.
4. `[DECISIÓN]` Hacer durable el `REVOKE` (§4.6): poblar `MIGRATOR_DBUSER`, o
   corregir también los `ALTER DEFAULT PRIVILEGES` de `postgres`.
5. `[DECISIÓN]` La ventana de 30–60 minutos. No invento la hora.

Cuando eso esté, el cambio productivo es: `DBUSER`/`DBPASSWORD` de `crm_user`,
`MIGRATOR_DBUSER`/`MIGRATOR_DBPASSWORD` poblados, reiniciar backend, Celery
worker y Celery beat, y correr el smoke. Sin roles que crear, sin migraciones que
aplicar, sin tocar el puerto del pooler.

---

## RESUMEN EJECUTIVO

**La rotación está bloqueada y no la simulé.** Lo verifiqué en concreto —sin
variables `DOKPLOY_*`, sin CLI, sin `~/.dokploy`, sin token— y entregué las
instrucciones exactas de qué cambiar en el proyecto
`automatizacion-rp-supabase-dgimpk`, con el impacto documentado de antemano. Como
la rotación es la primera compuerta, el GUC y el `DBUSER` se quedaron donde
estaban.

**Los cuatro `REVOKE` están aplicados.** 180 sentencias generadas del inventario
real, ninguna `REVOKE ALL`. Antes de tocar producción ensayé dos veces: que el
comando quita lo que dice, y —lo que de verdad podía fallar en silencio— que un
rol **no superusuario miembro de `crm_owner`** puede revocar lo que `crm_owner`
concedió. Resultado: los cuatro privilegios en **0**, lo requerido intacto, y el
smoke en **18/18** con el juego ya reducido; el ítem 15 marca el borde exacto —
`nextval` funciona, `setval` queda bloqueado.

**Dos hallazgos que corrigen el alcance.** `crm_user` tiene además **`CREATE`
sobre el esquema `public`** en producción — un quinto privilegio innecesario que
**yo había declarado como `False` en el informe de Fase 1 copiándolo del entorno
aislado sin medirlo en producción**. Y los `ALTER DEFAULT PRIVILEGES` de
`postgres` harían que **la próxima migración devolviera** tres de los cuatro
privilegios recién quitados; se vuelve durable en cuanto las migraciones corran
como `crm_migrator`. Ninguno de los dos lo toqué: están fuera de lo autorizado.

**Y lo que el `REVOKE` no arregla, dicho claro:** la vía indirecta sigue abierta.
`crm_user` puede leer el secreto y firmar un `service_role` con `BYPASSRLS` sobre
129 de 135 tablas. Quitar privilegios SQL no cierra eso; solo lo cierra la
rotación más el retiro del GUC.

**`DBUSER` sigue en `postgres`.** Producción sin diferencias contra el baseline.

---

**No se hizo commit. No se activó autonomía. No se tocó M09 ni M11. No se tocó el
kill switch. Ninguna modificación de producción fuera de los 180 `REVOKE`
autorizados.**
