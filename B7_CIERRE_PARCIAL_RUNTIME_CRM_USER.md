# B-7 — CIERRE PARCIAL DEL RUNTIME

Fecha: 2026-09-19

# B-7 = **PARCIAL**

No cerrado. El bloque exige decirlo expresamente y así se dice, arriba de todo.

**Resultado del bloque: NO PASS** — por un solo criterio, y no por falta de
evidencia: **el cambio de `DBUSER` no se pudo ejecutar**, porque vive en Dokploy
y no tengo acceso. Todo lo demás está hecho y medido.

Sin commit, sin `git stash`, sin tocar Autonomía 2, sin levantar el kill switch,
sin ejecutar `crear_tag_crm`, sin tocar `app.settings.jwt_secret`.

---

# A — `REVOKE CREATE`: **PASS**

## Ensayo antes de producción

Como con los cuatro `REVOKE` anteriores: primero en `pg-b7`. Se concedió
`CREATE` y se revocó con la sentencia exacta. Quitó lo que dice y **nada más** —
DML 135/135, secuencias 51/51/0, `crm_migrator` intacto, `TEMPORARY` intacto.

## Verificación previa del grant

```
crm_user CREATE en public : True
ACL de public: … | crm_user=UC/pg_database_owner | crm_owner=UC/pg_database_owner
                            ^^ C = CREATE
dueño de la base 'postgres' : postgres
¿soy miembro de pg_database_owner? : True   -> puedo revocarlo
```

## La sentencia — una sola, sin `REVOKE ALL`

```sql
REVOKE CREATE ON SCHEMA public FROM crm_user;
```

Ejecutada como `postgres`, confirmada.

## Antes / después, leído por una conexión **independiente** de la que escribió

| | ANTES | DESPUÉS |
|---|---|---|
| `crm_user` CREATE en public | **True** | **False** |
| `crm_user` USAGE en public | True | True |
| tablas SELECT/INSERT/UPDATE/DELETE | 135/135/135/135 | 135/135/135/135 |
| tablas TRUNCATE | 0 | 0 |
| secuencias USAGE/SELECT/UPDATE | 51/51/0 | 51/51/0 |
| EXECUTE en funciones de public | 149/149 | 149/149 |
| `crm_migrator` CREATE / USAGE | True / True | True / True |
| `crm_user` bypassrls / superuser | False / False | False / False |
| `crm_user` TEMPORARY | True | True |

```
CREATE quitado           : True
todo lo demas IDENTICO   : True   (comparados los 18 campos, uno por uno)
```

No se revocó ningún privilegio adicional. No se tocó `crm_migrator`. No se tocó
`BYPASSRLS`.

---

# B — CAMBIO DE RUNTIME: **BLOQUEADO**

## `DBUSER` sigue siendo `postgres`

```
DBUSER efectivo del runtime: postgres
```

## Por qué no se pudo

`docker-compose.prod.yml` toma el valor del entorno del despliegue, en los tres
servicios del CRM:

```
línea 112  DBUSER: ${DBUSER:?}     (backend)
línea 177  DBUSER: ${DBUSER:?}     (celery-worker)
línea 222  DBUSER: ${DBUSER:?}     (celery-beat)
```

Ese entorno vive en **Dokploy**, y ahí no llego — verificado de nuevo, no
asumido:

```
variables DOKPLOY_* en .env : 0
CLI dokploy                 : NO instalado
~/.dokploy                  : no existe
```

El `.env` del repositorio **no sirve**: es el de desarrollo local. Cambiarlo no
movería producción, solo daría la apariencia de haberlo hecho.

## `[BLOQUEANTE]` Y falta un dato que tampoco tengo

Para poner `DBUSER=crm_user` hace falta también su `DBPASSWORD`. En el equipo
solo existe `b8_crm_migrator_clave.txt` — la de **`crm_migrator`**. **No hay
ninguna de `crm_user`.**

Si esa contraseña no está guardada en otro lado, hay que fijarla con
`ALTER ROLE crm_user PASSWORD …`, que es una escritura en producción **no
autorizada en este bloque**. Lo reporto en vez de hacerlo.

## Lo que hay que hacer, exacto

En Dokploy, proyecto **`crm-agentico-*`** (el de la plataforma, **no** el de
Supabase), en las variables del servicio Compose:

```
DBUSER      = crm_user.<mismo sufijo de pooler que ya usa>
DBPASSWORD  = <la de crm_user>
```

**Sin tocar** `DBHOST`, `DBNAME`, `DBPORT` (5433 = session mode; cambiarlo
filtraría `app.current_org` entre empresas), ni `MOTOR_DBUSER`/`MOTOR_DBPASSWORD`
— el motor tiene identidad propia a propósito, desde el incidente del 18/08.

Después: **Redeploy / Recreate**, no *Save*. Recrea `backend`, `celery-worker` y
`celery-beat`.

---

# C — VERIFICACIÓN DE IDENTIDAD: **NO VERIFICABLE TODAVÍA**

Depende de B. Hoy:

```
runtime del CRM : postgres     <- lo que B debe cambiar
motor           : motor_user   <- identidad propia, correcta, sin tocar
migraciones     : crm_migrator <- separada, ver E
```

## Cómo se comprueba cuando B ocurra

Desde la base, no desde la variable de entorno — que es justo lo que el bloque
pide no dar por supuesto:

```sql
select usename, application_name, backend_start
  from pg_stat_activity
 where datname = current_database();
```

Debe aparecer **`crm_user`** en las conexiones del backend. Dos señales
adicionales de que el redeploy fue real: las conexiones son nuevas (minutos, no
horas) y el `application_name` corresponde al ORM de Django.

**No se acepta** `postgres`, `crm_migrator` ni `service_role` como identidad del
runtime normal.

---

# D — SMOKE TESTS: **18/18**

Ejecutados en el entorno aislado, que **espeja el estado nuevo de producción**:

```
CREATE en public : false      <- igual que produccion tras el REVOKE de hoy
TEMPORARY        : true
bypassrls        : false
current_user=crm_user  session_user=crm_user  rolsuper=False  rolbypassrls=False
```

| # | Ítem del bloque D | Resultado |
|---|---|---|
| 1 | SELECT normal | ítem 3: `cases_count=5` |
| 2 | INSERT | ítem 4: persistido, verificado con conexión independiente |
| 3 | UPDATE | ítem 4: `status='Assigned'` persistido |
| 4 | DELETE controlado | concedido y medido (135/135); el smoke no borra datos a propósito |
| 5 | transacciones | ítems 10 y 11: commit deja 1, rollback deja 0 |
| 6 | locks / `select_for_update` | ítem 14: otra conexión **rebota con NOWAIT**; advisory lock tomado **y liberado** |
| 7 | secuencias | ítem 15: `nextval` 11→12 **permitido**; **`setval` BLOQUEADO** |
| 8 | RLS bajo `crm_user` | ítem 13: 0 filas sin contexto, UPDATE cruzado 0, INSERT cruzado rechazado, FORCE en todas |
| 9 | aislamiento por organización | ítem 9: ORG-B tiene 1 caso, el ORM ve **0**, fuga por HTTP **0** |
| 10 | scheduler/beat sin fuga de contexto | ítem 17: tarea real de beat, **contexto residual vacío** |
| 11 | endpoints críticos | ítems 1–4: login, health, listar, crear/editar |
| 12 | persistencia por conexión independiente | en los ítems 4, 5, 6, 7, 10, 11 |
| 13 | lectura/escritura normales | ítems 5, 6, 7, 8 |
| 14 | **no puede crear objetos en public** | ítem 12: 7 de 7 operaciones administrativas bloqueadas |
| 15 | **`pg_temp` funciona** | medido aparte: como `crm_user` y con `CREATE=false`, tabla temporal creada, escrita, leída (1 fila) y borrada |
| 16 | **`crm_user` sin BYPASSRLS** | `rolbypassrls=False`, medido en producción y en el aislado |

## Comparación con los smoke anteriores

**Idéntico: 18/18 antes y después del `REVOKE`.** Era lo esperado —
`CREATE` ya estaba en `false` en el aislado cuando se probó— y confirma lo que
el bloque D pedía comparar: quitar `CREATE` no cambió el resultado de ninguna
prueba.

`[LÍMITE]` Este smoke corre contra el entorno aislado, no contra producción.
Correrlo como `crm_user` **contra producción** exige su contraseña y el cambio
de `DBUSER` — o sea, el bloque B. Lo digo en vez de presentar el verde del
aislado como si fuera el de producción.

---

# E — MIGRACIONES: **PASS**

Medido contra **producción**, en solo lectura, con la credencial de
`crm_migrator` del archivo externo (nunca impresa):

```
entra como            : crm_migrator
actua como            : crm_owner        (por ALTER ROLE ... SET role)
bypassrls / superuser : False / False
puede ejercer el rol DUENO de 135 de 135 tablas
CREATE en public      : True
```

Poder ejercer el rol dueño de las 135 es exactamente lo que exige
`ALTER TABLE … ENABLE ROW LEVEL SECURITY`, que es donde fallaría una migración
mal identificada.

La otra mitad, que importa igual:

```
crm_user: tablas de las que puede ejercer el rol dueno : 0
crm_user: CREATE en public                             : False
crm_user: bypassrls                                    : False
```

```
runtime     -> crm_user       (no puede migrar)
migraciones -> crm_migrator   (puede, y solo eso)
```

**No se concedió `BYPASSRLS` a `crm_user`. No se le concedió ningún privilegio
adicional.** No se ejecutó ninguna migración productiva.

`[PENDIENTE]` `MIGRATOR_DBUSER` / `MIGRATOR_DBPASSWORD` en el despliegue: **no
verificable desde aquí**, viven en Dokploy. El mecanismo existe en
`docker/backend/entrypoint.sh` y la última vez que se midió el `.env` estaban
vacías. Hay que poblarlas en la misma ventana que el cambio de `DBUSER`.

---

# F — AUTONOMÍA 2: **SIGUE BLOQUEADA**

No se activó. Se verificó ejecutando **el código real contra la base de
producción**:

```
con la etapa APAGADA   -> AUTONOMIA_2_NO_ACTIVA
con la etapa ENCENDIDA -> B7_REQUERIDO
veredicto_b7() directo -> permitido=False  codigo=B7_REQUERIDO
```

Es el punto que importa: **encender `AUTONOMIA_2_ACTIVA` no alcanza**. El
prerequisito se mide contra la base, y mientras el GUC exista la respuesta es
`B7_REQUERIDO`. La variable se encendió **solo dentro de ese proceso**; el
`.env` quedó sin ella (verificado: 0 ocurrencias).

Estado confirmado:

```
app.settings.jwt_secret  : presente (SIN TOCAR)
kill switch              : detenido
AUTONOMIA_2_ACTIVA       : ausente del .env = apagada
asistente.nivel_autonomia            : no existe
asistente.autorizacion_herramienta   : no existe
asistente.ejecucion_autonoma         : no existe
tags creados hoy por este trabajo    : 0
actividades de operaciones (M02/M09) : 0
crear_tag_crm ejecutado              : NO
```

---

# G — LÍMITES DE LO QUE SE PUEDE AFIRMAR

## Lo que sí se puede decir

- El runtime **ya no necesita** `postgres`: probado 18/18 como `crm_user`.
- El `CREATE` innecesario **fue revocado** en producción.
- Los privilegios del runtime **están reducidos**: sin TRUNCATE, REFERENCES,
  TRIGGER, sin UPDATE de secuencias, sin CREATE, sin BYPASSRLS, dueño de 0
  tablas.
- Las migraciones **quedan separadas**: `crm_migrator` puede, `crm_user` no.

## Lo que NO se puede decir, y no se dice

- **NO** «RLS completamente protegido».
- **NO** «`service_role` ya no puede saltarse RLS».
- **NO** «B-7 cerrado».
- **NO** «Autonomía 2 lista para producción».

## Por qué

`app.settings.jwt_secret` sigue presente y legible por `crm_user`;
`service_role` conserva `BYPASSRLS` y DML sobre 129 de 135 tablas;
`authenticator` puede `SET ROLE service_role`. El camino indirecto **no está
cerrado**, por la decisión documentada en `B7_DECISION_NO_ROTAR.md`.

Y hay una consecuencia que conviene tener presente cuando B se ejecute:
**mientras ese camino siga abierto, `crm_user` puede recuperar `BYPASSRLS`** con
un `SELECT` y un HMAC. El cambio de `DBUSER` sigue valiendo la pena —cierra la
vía directa y es defensa en profundidad— pero no produce el aislamiento que su
nombre sugiere.

---

# CRITERIO DE SALIDA

| # | Criterio | Resultado |
|---|---|---|
| 1 | `REVOKE CREATE` ejecutado correctamente | **PASS** |
| 2 | `DBUSER` efectivo del runtime = `crm_user` | **NO** — bloqueado en Dokploy |
| 3 | runtime funciona | **PASS** (18/18 en aislado; en producción depende de 2) |
| 4 | smoke tests pasan | **PASS** — 18/18 |
| 5 | RLS y aislamiento bajo `crm_user` | **PASS** |
| 6 | `setval` bloqueado | **PASS** |
| 7 | `nextval` funciona | **PASS** |
| 8 | `pg_temp` funciona | **PASS** |
| 9 | `crm_user` sin BYPASSRLS | **PASS** |
| 10 | `crm_migrator` conserva capacidad de migración | **PASS** — dueño de 135/135 |
| 11 | Autonomía 2 bloqueada | **PASS** — `B7_REQUERIDO` |
| 12 | kill switch detenido | **PASS** |
| 13 | `crear_tag_crm` no ejecutado | **PASS** |
| 14 | `app.settings.jwt_secret` sin modificar | **PASS** |
| 15 | el informe declara **B-7 = PARCIAL** | **PASS** |

## **VEREDICTO: NO PASS** — falla el criterio 2, y solo ese

Catorce de quince cumplidos. El que falta no depende de más evidencia ni de más
pruebas: depende de un acceso que no tengo.

---

# ESTADO DE PRODUCCIÓN AL CERRAR

```
crm_user CREATE en public     : False    <- CAMBIO DE HOY, autorizado
crm_user TRUNCATE/REFS/TRIGGER: 0        (revocados antes)
crm_user secuencias UPDATE    : 0        (revocado antes)
crm_user bypassrls            : False
crm_migrator                  : sin tocar (dueño de 135/135, CREATE True)
app.settings.jwt_secret       : presente, sin tocar
kill switch                   : detenido
AUTONOMIA_2_ACTIVA            : apagada
DBUSER efectivo               : postgres
tablas en public              : 135
tablas de Autonomia 2         : ausentes
```

La única escritura en producción de este bloque fue el `REVOKE` autorizado.
Todo lo demás se consultó con `transaction_read_only = on` verificado en el
servidor.

---

# LO QUE FALTA, Y DE QUIÉN ES

1. **`[BLOQUEANTE, HUMANO]`** Conseguir o fijar la contraseña de `crm_user`.
2. **`[BLOQUEANTE, HUMANO]`** En Dokploy, proyecto de la plataforma: poner
   `DBUSER`/`DBPASSWORD` de `crm_user`, poblar `MIGRATOR_DBUSER`/
   `MIGRATOR_DBPASSWORD`, y **Redeploy/Recreate**.
3. Avisarme: mido el `session_user` efectivo desde la base y corro las
   verificaciones del bloque C contra producción.

---

**No se hizo commit. No se usó `git stash`. No se tocó Autonomía 2. No se
levantó el kill switch. No se ejecutó `crear_tag_crm`. No se modificó
`app.settings.jwt_secret`. B-7 sigue siendo PARCIAL.**
