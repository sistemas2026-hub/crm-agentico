# AUTONOMÍA 2 — TRAZABILIDAD · PRECIERRE DE B-7

Fecha: 2026-09-19 · **PASS**

Nada se activó. Producción intacta, sin commit, sin `git stash`, sin tocar
trabajo ajeno.

---

# BLOQUE A — `invocable_por_servicio`, CORREGIDO

## Qué estaba mal

El propio docstring de `motor.ejecutar_para_servicio()` lo decía:

> *«…y `invocable_por_servicio` en schema.py — **ESE es el permiso; acá ya se da
> por concedido**.»*

Era literal. La comprobación vivía solo en la ruta, y llamar a la función
directamente con una herramienta no invocable **ejecutaba** — 1 llamada externa
contada.

## La corrección, mínima

Cuatro líneas al principio de la función, **antes** de resolver argumentos y
antes de cualquier compuerta:

```python
if not getattr(herramienta, "invocable_por_servicio", False):
    raise ValueError(
        f"'{herramienta.nombre}' no esta declarada 'invocable_por_servicio' "
        f"y no se ejecuta desde un servicio. …")
```

- **No se crea un segundo sistema de autorización**: usa la propiedad que ya
  existe en el catálogo.
- **No se duplica lógica**: la comprobación de la ruta **no se quita** — sigue
  contestando un 400 con un mensaje útil antes de llegar hasta aquí. Lo que
  cambia es **quién la hace cumplir**: un mensaje en el borde, una guarda en el
  efecto. Es el patrón que este módulo ya usa para todo lo demás.
- **No cambia el contrato de herramientas** ni ninguna herramienta existente.
- Misma forma de error que el `ValueError` que esa función ya levanta al final:
  no se agrega una excepción nueva al contrato.

Y el docstring quedó corregido: dice qué pasaba, qué se midió y por qué ahora
se comprueba aquí.

## Las cuatro pruebas pedidas

| # | Caso | Medido |
|---|---|---|
| 1 | no invocable → 0 llamadas | **0**, y el error nombra `invocable_por_servicio` |
| 2 | invocable + sin autorización → 0 | **0** |
| 3 | invocable + autorización válida | **este control no la frena** (ver nota) |
| 4 | no se salta la frontera llamando al servicio | **0** sin autorización; **0** con una R3 y techo 4 |

> Nota sobre el caso 3: se afirma que **este** control no la frena, no que llegue
> a la red. La única escritura invocable por servicio del catálogo
> (`cerrar_ticket_operativo`) necesita argumentos que esta prueba no tiene;
> afirmar «sale 1» mediría la resolución de argumentos, no el permiso. Se dice
> en vez de forzar un verde que no significaría eso.

**Ninguna guarda existente se relajó.**

---

# BLOQUE B — TRAZABILIDAD

## Inspección primero: el puente ya existía

| Tabla | Identificador |
|---|---|
| `asistente.operaciones_externas` | **clave primaria `(organization_id, clave)`** |
| `asistente.ejecucion_autonoma` | ya tenía `organization_id` **y** `clave_idempotencia` |
| `campo_mutacion_idempotente` | del **CRM** (Django, `campo/`). El motor no lo usa — **otro perímetro** |

**Cero tablas nuevas. Cero columnas nuevas.** La columna existía y nadie la
llenaba: lo único que faltaba era escribirla.

## Cómo se cierra: dos renglones por intento, sin columna nueva

```
resultado IS NULL      AUTORIZACION   creado_en = momento de autorizacion
resultado IS NOT NULL  DESENLACE      creado_en = momento de ejecucion,
                                      y trae clave_idempotencia
```

Se distinguen por una columna que ya estaba. La bitácora sigue siendo
**append-only**: no se actualiza ninguna fila.

Quién escribe el desenlace: `nucleo/seguridad/frontera.py::anotar_desenlace()`,
llamado desde `idempotencia.ejecutar()` cuando la operación termina — **ahí es
donde se conoce la clave y el desenlace, y no antes**. Escribirlo en el motor
habría sido el mismo error que la frontera existe para corregir.

Dos decisiones dentro:

- **Solo anota ejecuciones autónomas.** Una acción aprobada por una persona
  entra por `humana()`, tiene su propio rastro (actor + evidencia + la fila que
  aprobó) y no es «el sistema actuando solo»: meterla ahí ensuciaría la única
  tabla que contesta esa pregunta.
- **No se copia el resultado ni el error.** Ya están en `operaciones_externas`;
  se guarda la **clave**, que es la referencia. Medido: el texto del error
  (`500`) **no** aparece en el renglón.

## Lo que queda relacionable

| Exigido | Dónde |
|---|---|
| herramienta | `ejecucion_autonoma.herramienta` |
| tenant / organización | `organization_id` |
| clave de idempotencia | `clave_idempotencia` → PK de `operaciones_externas` |
| momento de autorización | `creado_en` de la fila con `resultado IS NULL` |
| momento de ejecución | `creado_en` de la fila con `resultado IS NOT NULL` |
| estado final | `resultado` |
| resultado o error | por referencia, en `operaciones_externas` |
| identificador de `operaciones_externas` | `(organization_id, clave_idempotencia)` |
| origen / autonomía | `evidencia` (el origen), `actor`, `nivel_efectivo`, `decision` |

---

# BLOQUE C — ESTADOS

| Estado | Qué significa | Dónde vive |
|---|---|---|
| **AUTORIZADA** | las compuertas pasaron; el efecto está por intentarse | `decision='permitida'`, `resultado IS NULL` |
| **BLOQUEADA** | una compuerta frenó **antes** del efecto | `decision='bloqueada'`, `resultado='no_ejecutada'` |
| **EJECUTANDO** | la operación está reclamada | **`operaciones_externas.estado`** — no se duplica aquí |
| **EXITOSA** | el efecto ocurrió y el tercero contestó bien | `resultado='exitosa'` |
| **FALLIDA** | el efecto **se intentó** y volvió con error | `resultado='fallida'` |
| **EXPIRADA** | la reclamación venció sin ejecutar | **`idempotencia.py`** — no se toca |

Las dos reglas que importan, medidas:

- **Una operación bloqueada antes del efecto NO se marca FALLIDA.** Queda
  `no_ejecutada`, con el código de la compuerta. Llamarla fallida haría creer
  que un tercero respondió mal cuando lo que pasó es que el sistema no salió.
- **Solo un intento real que volvió con error queda FALLIDA.** Es la única
  diferencia que separa *«no salió»* de *«salió y salió mal»*.

`EJECUTANDO` y `EXPIRADA` **no se replican** en la bitácora: son de quien reclama
la operación, y duplicarlos sería el segundo mecanismo que este bloque prohíbe.
Comprobado por AST: `frontera.py` no define `EJECUTANDO`, `EXPIRADA` ni
`SEGUNDOS_VENCIDA`. **El vencimiento de 300 s y su rescate no se tocaron**
(`idempotencia.SEGUNDOS_VENCIDA == 300`, verificado).

---

# BLOQUE D — PRUEBAS DE TRAZABILIDAD

`tests/test_autonomia2_trazabilidad.py` — **todo en verde**.

## CASO 1 — autorización bloqueada
```
efecto externo              : 0
filas: 1 bloqueada, 0 desenlaces
resultado                   : 'no_ejecutada'   (NO 'fallida')
operaciones_externas        : vacio  -> no aparece como operacion ejecutada
clave                       : ausente -> nunca hubo operacion que reclamar
```

## CASO 2 — ejecución exitosa
```
efecto                      : 1
fila de autorizacion        : 1
fila de operaciones_externas: 1
fila de desenlace           : 1
vinculadas por la clave     : wamid-c2|crear_tag_crm|44136fa355b3678a
estado final                : 'exitosa'  (y coincide con operaciones_externas)
la clave conserva origen y herramienta -> la idempotencia sigue asociada
el renglon dice herramienta, organizacion, actor y evidencia
```

## CASO 3 — error real
```
el efecto SI se intento     : 1 llamada
operaciones_externas        : 1 fila
desenlace vinculado         : si
estado final                : 'fallida'
el error esta en operaciones_externas: "RuntimeError: el CRM contesto 500"
y NO se copia al renglon    : el texto '500' no aparece en el
```

## CASO 4 — repetición con la misma clave
```
segundo efecto              : no (1 llamada en total)
desenlaces 'exitosa'        : 1   -> no se inventa una segunda ejecucion
segundo intento             : anotado 'no_ejecutada' con codigo 'repetida'
referencia                  : los dos renglones apuntan a la MISMA clave
operaciones_externas        : 1 sola fila
```

## CASO 5 — concurrencia
```
8 hilos                     -> 1 solo efecto
operaciones_externas        -> 1 sola fila
desenlaces 'exitosa'        -> 1
todos los desenlaces apuntan a una fila real, y a la MISMA
los demas intentos quedan 'no_ejecutada': ninguno fingido
```

## Y no hay arquitectura paralela
```
la frontera no crea tablas
siguen siendo TRES tablas: no se agrego una cuarta
el puente usa la columna que ya existia
```

---

# BLOQUE E — PRECIERRE DEL PRIVILEGIO `CREATE`

## SQL preparado — **PENDIENTE DE EJECUCIÓN EN PRODUCCIÓN**

```sql
-- PENDIENTE DE EJECUCION EN PRODUCCION  --  no ejecutado en este bloque
REVOKE CREATE ON SCHEMA public FROM crm_user;
```

## Las cuatro confirmaciones, medidas hoy

| Qué | Resultado |
|---|---|
| runtime 18/18 sin `CREATE` | **18/18 OK**, con `crm_user CREATE en public = false` durante la corrida |
| ¿se necesita `CREATE` sobre `public`? | **No.** 0 objetos de `public` cuyo dueño sea `crm_user`; 0 DDL en código de runtime |
| `pg_temp` sigue disponible | **Sí**, demostrado: como `crm_user` y con `CREATE=false`, se creó una tabla temporal, se escribió, se leyó (`filas: 1`) y se borró |
| `crm_migrator` conserva lo suyo | **Sí**: `CREATE en public = True`. Lo necesita: es quien migra |

Estado en producción al cerrar, **sin tocar**:

```
crm_user CREATE en public     : True    (NO revocado, como indica el bloque)
crm_migrator CREATE en public : True    (lo necesita)
crm_user TEMPORARY            : True    (intacto)
```

---

# BLOQUE F — SECUENCIA DE CIERRE DE B-7

**Ninguna fase se ejecutó.**

## FASE 1 — Rotación en Dokploy · proyecto `automatizacion-rp-supabase-dgimpk`

| # | Paso |
|---|---|
| 1.1 | Generar `JWT_SECRET` nuevo (≥40 caracteres) con el gestor de secretos. Nunca a mano en un archivo |
| 1.2 | Regenerar **`ANON_KEY`** — JWT firmado con el secreto nuevo, `role: anon`, `iss: supabase` |
| 1.3 | Regenerar **`SERVICE_ROLE_KEY`** — ídem con `role: service_role` |
| 1.4 | Aplicar los tres en los servicios que los llevan: `kong`, `auth` (GoTrue), `rest` (PostgREST), `realtime`, `storage`, y `studio` si existe |
| 1.5 | **Recreate / redeploy.** Dokploy aplica variables **al recrear el contenedor, no al guardar el formulario** — `DESPLIEGUE.md` lo advierte dos veces |
| 1.6 | Verificar que el **secreto anterior ya no valida**. Avisarme: lo compruebo por firma HS256, sin presentar ningún token a ningún servicio y sin imprimir valores |
| 1.7 | Verificar que los cuatro servicios siguen operativos (reconectan a la base; `pg_stat_activity` vuelve a mostrarlos) |

**Impacto, para elegir la ventana:** se invalidan `SERVICE_ROLE_KEY`/`ANON_KEY`
actuales, las sesiones de GoTrue y las conexiones de Realtime con JWT. **NO** se
afectan las sesiones del CRM (usan `SECRET_KEY`, otro secreto) ni las conexiones
del motor y del CRM a la base (psycopg directo, sin JWT). Ningún archivo de este
repositorio lee `SUPABASE_SERVICE_ROLE_KEY`.

## FASE 2 — Retirar el GUC (**solo después de verificar la Fase 1**)

```sql
ALTER DATABASE postgres RESET app.settings.jwt_secret;
ALTER DATABASE postgres RESET app.settings.jwt_exp;
```

Verificar después:
1. el GUC ya no existe (`pg_db_role_setting` sin entradas `jwt`);
2. `crm_user` no puede leer ningún secreto ahí;
3. **el camino indirecto desapareció**: el `SERVICE_ROLE_KEY` anterior ya no
   verifica contra nada que `crm_user` pueda leer.

> Medido: **ninguna función SQL de esta base lee ese GUC**, y `pgjwt` no está
> instalada. **Límite honesto:** eso prueba que ninguna función *de la base* lo
> usa; **no** prueba que ningún servicio externo lo lea por SQL. Solo el paso 1.4
> —revisar la configuración del stack— puede cerrar esa duda.

## FASE 3 — Endurecer `crm_user`

```sql
REVOKE CREATE ON SCHEMA public FROM crm_user;
```
Verificar: `has_schema_privilege('crm_user','public','CREATE') = false`;
`TEMPORARY` intacto; DML 135/135 intacto; y correr el smoke de runtime.

## FASE 4 — Cambio de runtime

1. `DBUSER` de `postgres` → `crm_user` (y su `DBPASSWORD`). **`DBHOST` y `DBNAME`
   no se tocan; el puerto tampoco** — 5433 es *session mode*, y `app.current_org`
   es de alcance de sesión.
2. Poblar `MIGRATOR_DBUSER` / `MIGRATOR_DBPASSWORD`.
3. Reiniciar **solo** backend, Celery worker y Celery beat.
4. **Medir el usuario efectivo desde la base**, no confiar en la variable:
   `select session_user` debe decir `crm_user`.
5. Smoke completo: locks (`select_for_update` y advisory), secuencias
   (`nextval` sí, `setval` no), RLS y FORCE RLS, tenant isolation, scheduler/beat,
   endpoints críticos, transacción y rollback.
6. Revisar errores de aplicación y conexiones nuevas.

**Rollback:** `DBUSER` vuelve a `postgres` y se reinician los tres procesos. Sin
`DROP`, sin datos que deshacer. No se usa para tapar un permiso faltante: si
falta uno concreto, se concede **ese**.

## FASE 5 — Migraciones futuras

- Las migraciones se ejecutan con **`crm_migrator`** (`MIGRATOR_DBUSER`), que
  actúa como `crm_owner`. El `entrypoint.sh` ya lo hace cuando la variable está.
- **No** conceder `BYPASSRLS` a `crm_user`. (Y medido: dárselo a `crm_migrator`
  tampoco serviría — `BYPASSRLS` se evalúa sobre `current_user`, que ahí es
  `crm_owner`.)
- **No** restaurar privilegios excesivos al runtime. Los cuatro `REVOKE` se
  vuelven durables en cuanto las migraciones corran como `crm_migrator`: el
  *default privilege* de `crm_owner` ya es el correcto (`arwd`).
- Toda migración de datos usa el conteo verificable
  `expected / matched / updated / verified`, y `UPDATE 0` **no es éxito**.

---

# REGRESIÓN

## Núcleo: **88 de 90** archivos

Los 2 que fallan son previos y ajenos: `test_p2_inerte` (guarda del scheduler) y
`test_reloj` (barridos sin datos de conexión). Ninguno menciona Autonomía 2 ni
importa los módulos tocados.

## Pruebas que cambiaron de expectativa, y por qué

**Ninguna se relajó.** El contrato cambió y estas lo encodaban:

| Prueba | Antes afirmaba | Ahora |
|---|---|---|
| `test_autonomia2_preactivacion` 9c | *«la función NO comprueba `invocable_por_servicio`»* (el hallazgo) | que **sí** lo comprueba: 0 llamadas, y el error lo nombra |
| `test_autonomia2_preactivacion` 10 | UNA fila `permitida` | **dos**: autorización + desenlace, con la clave |
| `test_autonomia2` §16 | ídem | ídem |
| `test_autonomia2` §9 | `"idempotencia" not in texto` | por AST: que **no defina** clave, hash ni reclamo propios |

Esa última merece decirse: la guarda buscaba texto, y desde hoy `frontera.py`
**nombra** a `idempotencia.py` en un comentario. Leía su propia prosa. Ahora mide
el mecanismo. Es la tercera vez que ese error aparece en este trabajo, y por eso
las guardas nuevas van por AST.

## Dos falsos de prueba incompletos, corregidos

Los encontré porque el sistema hizo lo correcto y mi doble no:

- Al `_Respuesta` de prueba le faltaba `ok`. El efecto **salía** y reventaba al
  post-procesar → desenlace `fallida`. Conducta **correcta** del sistema; falso
  incompleto.
- Y le faltaba la forma que espera `extraer_de: tag`. Mismo síntoma.

Son exactamente los casos que el CASO 3 quiere demostrar — pero con un falso
roto no probaban lo que decían probar.

## CRM (Django)

**4383 pasan · 10 fallan · 64 omitidas** (16 min 03 s).

**Idéntico a la corrida anterior de este mismo bloque de trabajo**: mismo total y
**los mismos 10 tests, uno por uno**. Es la evidencia más fuerte de que estos
cambios no la alcanzaron — y era lo esperado: `django-crm/backend` no importa
nada de `nucleo/` (grep completo: 0 coincidencias), y todo lo tocado aquí es de
`nucleo/` y `tests/`.

Las 10, clasificadas antes y sin cambios:

| Cuántas | Causa |
|---|---|
| 7 | concurrencia real: exigen dos conexiones PostgreSQL; la suite corre sobre **SQLite** |
| 1 | `test_6_el_lock_de_lineas_va_antes_que_el_del_plan` — `select_for_update()` es **no-op en SQLite** |
| 1 | `test_la_rls_de_la_tabla_esta_puesta_y_forzada` — consulta `pg_policies`, que **no existe en SQLite** |
| 1 | `test_no_documented_variable_is_read_nowhere` — deriva de documentación **previa**, reclama `ADMIN_PASSWORD` |

---

# PRODUCCIÓN

```
asistente.nivel_autonomia            existe=False
asistente.autorizacion_herramienta   existe=False
asistente.ejecucion_autonoma         existe=False
kill switch: Rapilink | detenido     (sin cambios)
tablas en public: 135 · roles: 41 · django_migrations: 192
crm_user CREATE en public: True      (NO revocado)
DBUSER efectivo: postgres
```

Todo lo consultado fue con `transaction_read_only = on` verificado en el
servidor. Ninguna escritura.

---

# BLOQUE G — CRITERIO DE SALIDA: **PASS**

| # | Criterio | Resultado |
|---|---|---|
| 1 | `invocable_por_servicio` protegido en la frontera de efecto | **cumple** — la función lo hace cumplir; la ruta conserva su mensaje |
| 2 | no existe bypass nuevo | **cumple** — 0 llamadas por la vía directa, con y sin autorización, y con una R3 |
| 3 | trazabilidad inequívoca entre las dos tablas | **cumple** — por `(organization_id, clave_idempotencia)`, sin tabla ni columna nueva |
| 4 | éxito/error real diferenciados de bloqueo | **cumple** — `exitosa` / `fallida` / `no_ejecutada`, los tres medidos |
| 5 | idempotencia conserva su semántica | **cumple** — misma clave 1 efecto; otros argumentos rechaza; 300 s sin tocar |
| 6 | concurrencia mantiene un único efecto | **cumple** — 8 hilos, 1 efecto, 1 fila, 1 desenlace exitoso |
| 7 | `REVOKE CREATE` preparado | **cumple** — con las cuatro confirmaciones, **no ejecutado** |
| 8 | secuencia completa de B-7 preparada | **cumple** — 5 fases, ninguna ejecutada |
| 9 | producción intacta | **cumple** |
| 10 | no se crea arquitectura paralela | **cumple** — 3 tablas, 0 columnas nuevas, la frontera no reimplementa nada |

## Lo que queda abierto, y de quién es

1. **`[BLOQUEANTE, HUMANO]` Rotar `JWT_SECRET` en Dokploy** (Fase 1). No tengo
   acceso. Mientras el GUC exista, el motor contesta `B7_REQUERIDO` aunque se
   encienda todo lo demás — se mide contra la base, no es una bandera.
2. `[PENDIENTE]` `REVOKE CREATE ON SCHEMA public FROM crm_user` — demostrado
   innecesario, preparado, **no ejecutado**.
3. `[PENDIENTE]` Migración de Autonomía 2 en producción, fila de techo y fila de
   autorización del piloto.
4. `[DECISIÓN]` Ventana de cambio, vigencia de la autorización y quién autoriza.

---

## RESUMEN

**El control que estaba en el lugar equivocado ya está donde ocurre el efecto.**
`ejecutar_para_servicio` comprueba `invocable_por_servicio` en cuatro líneas; la
ruta conserva su 400 con mensaje útil. No es lógica duplicada: es un mensaje en
el borde y una guarda en el efecto.

**La trazabilidad se cerró con lo que ya existía.** `operaciones_externas` tiene
clave primaria `(organization_id, clave)` y `ejecucion_autonoma` ya tenía las dos
columnas: faltaba escribirlas. Cero tablas, cero columnas. Un intento deja dos
renglones —autorización y desenlace— que se distinguen por `resultado IS NULL`,
y de ahí salen los dos momentos que pedía el bloque sin inventar una marca de
tiempo nueva.

**La diferencia que importa quedó medida:** bloqueada es `no_ejecutada`, nunca
`fallida`; `fallida` es solo el intento que salió y volvió con error. Y el error
no se copia: se guarda la referencia, porque ya está del otro lado.

**Los cinco casos pasan**, incluida la concurrencia: 8 hilos, un efecto, una
fila, un desenlace exitoso y los demás anotados como no ejecutados — ninguno
fingido.

Dos cosas que encontré por el camino y que prefiero decir: mis falsos de prueba
estaban incompletos (le faltaba `ok` a la respuesta), y el sistema hacía lo
correcto mientras mi doble mentía; y una guarda mía volvía a leer su propia prosa
—la tercera vez en este trabajo—, así que las nuevas van por AST.

**Nada se activó.** Interruptor apagado, tablas ausentes, kill switch `detenido`,
`DBUSER` en `postgres`, `CREATE` sin revocar, producción sin una sola diferencia.

---

**No se hizo commit. No se tocó producción. No se aplicaron migraciones
productivas. No se activó Autonomía 2. No se levantó el kill switch. No se
cambió `DBUSER`. No se ejecutó `crear_tag_crm`. No se usó `git stash`.**
