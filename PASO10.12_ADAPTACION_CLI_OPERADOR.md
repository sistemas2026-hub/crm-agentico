# Paso 10.12 — Adaptación del CLI al rol operador

**Fecha:** 17/09/2026
**Producción:** intacta. Ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`,
**0** tablas de las migraciones 3 y 4, **0** roles nuevos, **0** funciones
`autonomia_detener`. No se aplicaron migraciones, no se cambió `DBUSER`, no se
desplegó `interruptor.py` ni `idempotencia.py`, no se implementó autonomía 0–4,
y M02, M03, M09 y M10 no se tocaron.

> **Un solo archivo modificado**, y el CLI no fue uno de ellos.

---

## Estado anterior

```
cli/autonomia.py → interruptor.detener()/reactivar()
                 → db.registrar_transicion_autonomia()
                   → db.sesion(tenant)      ← "set local role app_backend"
                     → INSERT en asistente.interruptor_autonomia
```

`db.sesion()` bajaba **siempre** a `app_backend`. El rol del runtime del motor y
el rol del flujo administrativo eran el mismo, así que el proceso del motor
podía insertar `'activo'` y reactivarse solo (medido en el paso 10.10).

## Estado nuevo

```
cli/autonomia.py → interruptor.detener()/reactivar()
                 → db.registrar_transicion_autonomia()
                   → db.sesion(tenant, rol=ROL_OPERADOR_AUTONOMIA)
                     → "set local role autonomia_operador"
                       → INSERT

motor / api / reloj / coordinador
                 → db.sesion(tenant)        ← sigue en app_backend
```

## Archivos modificados

**Uno: `nucleo/persistencia/db.py`.**

| Cambio | Qué hace |
|---|---|
| Constantes `ROL_RUNTIME`, `ROL_OPERADOR_AUTONOMIA`, `ROLES_PERMITIDOS` | la lista blanca de roles a los que el módulo puede bajar |
| `sesion(tenant, connect_timeout, rol=ROL_RUNTIME)` | parámetro nuevo, con el runtime por omisión |
| Guarda dentro de `sesion()` | `if rol not in ROLES_PERMITIDOS: raise ValueError` **antes** de interpolar |
| `registrar_transicion_autonomia()` | única llamada con `rol=ROL_OPERADOR_AUTONOMIA` |
| Docstrings | el encabezado del módulo, `sesion()` y la función, explicando la excepción y por qué |

La lista blanca no es ceremonia: **`SET ROLE` es una sentencia de utilidad y no
acepta parámetros** — el mismo motivo por el que `statement_timeout` se fija con
`set_config()` unas líneas más arriba. El nombre del rol se interpola en el SQL,
así que interpolar algo fuera de la tupla sería una inyección.

**`cli/autonomia.py`: sin cambios.** No los necesita — llama a
`interruptor.detener()`/`reactivar()`, que bajan a
`db.registrar_transicion_autonomia()`. El cambio de rol es transparente para él.

**`interruptor.sembrar()`: sin cambios.** Verificado: `cli/cargar_config.py` usa
su propia conexión (`_conectar()`) **sin degradar el rol**, así que el alta de un
tenant corre como la credencial de conexión y no como `app_backend`. Revocar el
`INSERT` a `app_backend` **no rompe el alta**.

## SQL

El del paso 10.11, sin cambios (§E de ese informe): el rol
`autonomia_operador` `NOLOGIN`, el `REVOKE INSERT` a `app_backend`, el `GRANT`
al operador con su política, y la función `asistente.autonomia_detener`.

**Añadido en esta etapa — lo que necesita el contexto administrativo:**

```sql
-- el contexto desde el que se corre cli/autonomia.py necesita las DOS
-- membresias, y las dos con inherit=false para que haya que pedirlas:
grant app_backend        to <contexto_admin> with inherit false, set true;
grant autonomia_operador to <contexto_admin> with inherit false, set true;
```

**Por qué las dos.** Las transiciones bajan al operador, pero **leer** el estado
y anotar en `audit_log` siguen usando `sesion()` con el runtime
(`estado_autonomia`, `historial_autonomia`, `registrar_auditoria`). Sin la
membresía a `app_backend`, el CLI escribe la transición pero **no puede leerla
ni auditarla** — medido: `permission denied to set role "app_backend"`, con
`estado_anterior` quedando en `NULL`.

En producción ese contexto es `postgres`, que ya es miembro de `app_backend` con
`SET`. Sólo falta el `GRANT` del operador.

**Y una condición del propio `db.sesion()`:** la credencial de conexión necesita
poder leer `asistente.tenant_config` **antes** de bajar de rol, para resolver el
slug — el comentario del código lo dice: hacerlo después sería circular, porque
la política de esa tabla exige el tenant ya fijado. En la práctica eso significa
`BYPASSRLS` en la credencial de conexión, que es lo que tienen `postgres` y
`motor_user`. **No afecta a la segregación**: `BYPASSRLS` salta políticas, no
`GRANT`s — la credencial sigue sin `INSERT` propio sobre el interruptor.

## Matriz de roles

| Rol | SELECT | INSERT | UPDATE | DELETE | `EXECUTE` parada | `SET ROLE` operador |
|---|---|---|---|---|---|---|
| `app_backend` (runtime) | **sí** | no | no | no | **sí** | **no** |
| `autonomia_operador` | sí | **sí** | no | no | sí | — |
| contexto administrativo (`postgres`) | por `SET ROLE` | por `SET ROLE` | no | no | sí | **sí** |
| `motor_user` | no | no | no | no | no | **no** |
| `crm_user`, `job_executor`, `scheduler_coordinator`, `monitor_ro`, `asistente_owner`, `service_role` | no | no | no | no | no | **no** |

Nadie tiene `UPDATE` ni `DELETE`: el interruptor es de solo agregar.

## Funciones SECURITY DEFINER

Auditadas las **10** de `asistente`:

| | |
|---|---|
| Con `search_path` fijado | **10 de 10**, todas a `pg_catalog` |
| Dueño | `autonomia_detener` → `postgres`; las 9 del scheduler → `asistente_owner` |
| `EXECUTE` de `autonomia_detener` | `postgres`, `app_backend`, `autonomia_operador`. **`PUBLIC` revocado** |
| Que escriben en el interruptor | **una sola: `autonomia_detener`** (INSERTA) |
| Que mencionan `'activo'` | **ninguna** |
| Que permitan activar indirectamente | **ninguna** |

Las 9 del scheduler no mencionan el interruptor y tienen `EXECUTE` acotado a
`scheduler_coordinator`, `job_executor` o `monitor_ro` según corresponda.

## Pruebas con `session_user` real

Réplica desde cero (B.6/B.7 + las 2 migraciones + la segregación del 10.11), con
**dos logins de prueba**, ninguno `postgres`:

- **`sim_admin`** — el contexto administrativo futuro: `LOGIN`, `BYPASSRLS`,
  miembro de `app_backend` **y** de `autonomia_operador`, ambos con
  `inherit false, set true`.
- **`sim_runtime`** — el motor: `LOGIN`, `BYPASSRLS`, miembro de `app_backend`
  con `SET`. Igual que `motor_user` en producción.

| # | Prueba | Esperado | Resultado |
|---|---|---|---|
| **A** | `sim_admin` → `SET ROLE autonomia_operador` | OK | **`session_user=sim_admin, current_user=autonomia_operador`** |
| **B** | `sim_runtime` → `SET ROLE autonomia_operador` | DENEGADO | **`permission denied to set role "autonomia_operador"`** |
| **C** | operador → `INSERT` `DETENIDO` | OK | la semilla y el alta escriben `detenido` |
| **D** | operador → activar | OK | **`rapilink: detenido -> activo`**, actor `mayra` |
| **E** | operador → detener | OK | **`rapilink: activo -> detenido`** |
| **F** | `app_backend` → `INSERT ACTIVO` | DENEGADO | **`permission denied for table interruptor_autonomia`** |
| **G** | `app_backend` → `UPDATE` | DENEGADO | **`permission denied for table`** |
| **H** | `app_backend` → `DELETE` | DENEGADO | **`permission denied for table`** |
| **I** | `app_backend` → función de parada | OK | **`detenido`** |
| **J** | `app_backend` → parada pidiendo `activo` | DENEGADO | **`function … does not exist`** — ese parámetro no existe |
| **K** | operador → historial | append-only | 5 transiciones, ninguna borrada, `estado_anterior` calculado |
| **L** | restore → permisos y comportamiento | idénticos | ver abajo |

**D y E se ejecutaron con el CLI real**, `cli/autonomia.py`, con
`DBUSER=sim_admin`. No con SQL a mano: es el código nuevo funcionando de punta a
punta.

Y la prueba negativa a nivel de aplicación: el **mismo CLI** con
`DBUSER=sim_runtime` →

```
[autonomia] no se pudo mover el interruptor:
InsufficientPrivilege: permission denied to set role "autonomia_operador"
```

### Auditoría de lo que quedó escrito

```
estado_anterior | estado   | actor      | motivo
activo          | detenido | mayra      | paso 10.12: detencion por el flujo administrativo
detenido        | activo   | mayra      | paso 10.12: activacion por el flujo administrativo
(ninguno)       | detenido | migracion  | Estado inicial al crear el interruptor
```

Y en `asistente.audit_log`: `autonomia_detenida` y `autonomia_reactivada`, con
`actor=mayra`, `recurso=autonomia:rapilink`, `resultado=permitido`.

## Ciclo completo y ausencia de privilegio persistente

```
1. login          : session_user=sim_admin  current_user=sim_admin
2. begin; set local role autonomia_operador  → current_user=autonomia_operador
3. transicion     : INSERT 0 1
4. commit         → current_user=sim_admin   (el 'set local' murió con la transacción)
5. reset role     → current_user=sim_admin
6. INSERT sin SET ROLE → ERROR: permission denied for table interruptor_autonomia
```

El `inherit false` es lo que hace esto cierto: `sim_admin` **no carga** los
privilegios del operador por ser miembro — tiene que pedirlos con `SET ROLE`, y
al cerrar la transacción no queda nada elevado. El paso 6 lo comprueba
directamente.

## Restore

Respaldo B.6/B.7 de la réplica con todo puesto → restauración desde cero:

| | Tras el restore |
|---|---|
| `app_backend` | `select=true insert=false` |
| `autonomia_operador` | `select=true insert=true` |
| Políticas | `tenant_aislado→{app_backend}` · `tenant_aislado_operador→{autonomia_operador}` |
| `autonomia_detener` | presente, `security definer` |
| **Comportamiento**: CLI como `sim_admin` | **escribió la transición** |
| **Comportamiento**: `sim_runtime` → `SET ROLE` | **`permission denied`** |

**Los permisos y el comportamiento son idénticos.**

### Una corrección de mi propio sondeo

El chequeo tras el restore imprimió `sim_admin puede SET ROLE operador: false`
**mientras el CLI escribía la transición**. Uno de los dos estaba mal, y era el
sondeo: usé `pg_has_role(rol, 'USAGE')`, que mide **herencia**, y la herencia
está deshabilitada a propósito (`inherit false`). Verificado en un contenedor
limpio:

```
grant op to adm with inherit false, set true;
  pg_has_role(adm, op, 'USAGE')  = false      ← lo que yo medía
  pg_has_role(adm, op, 'MEMBER') = true
  pg_has_role(adm, op, 'SET')    = true       ← lo correcto
  y en la practica: SET ROLE op  → current_user=op
```

**Para comprobar la capacidad de `SET ROLE` hay que usar `'SET'`, no
`'USAGE'`.** La conclusión del paso 10.11 —que `motor_user` no puede alcanzar al
operador— sigue siendo correcta, porque allí la sostuvo la prueba de
comportamiento con `sim_motor`, no el sondeo.

*(Y explica por qué `postgres` daba `USAGE=true` en el 10.11: tiene `CREATEROLE`
y creó el rol, así que obtiene admin implícito sobre él.)*

## Regresiones

Suite existente completa, **7 de 7 con código 0**:

```
test_interruptor_autonomia.py      test_idempotencia_externa.py
test_alta_tenant_autonomia.py      test_timeout_interruptor.py
test_nucleo_sin_tenants.py         test_editor_config.py
test_timeouts_modelo.py
```

`tests/test_reloj.py` sigue con 2 comprobaciones fallidas **anteriores a esta
etapa** (contadores de reconciliación y herramientas internas de Fase 2), ajenas
al interruptor.

**El runtime no cambió de comportamiento:** `sesion()` sin argumento sigue
bajando a `app_backend`, y el scheduler completó `job_claim → job_finalize` con
`succeeded` en la réplica.

## Riesgos

1. **El cambio de código y el SQL van juntos.** `db.py` ya pide
   `autonomia_operador`; si se despliega sin crear el rol,
   `cli/autonomia.py` falla con `permission denied to set role`. Y aplicar el
   `REVOKE` sin el código deja al CLI sin `INSERT`. **Ninguno de los dos sirve
   solo.**
2. **El contexto administrativo necesita las dos membresías.** Con sólo la del
   operador, el CLI escribe pero no lee ni audita, y `estado_anterior` queda
   `NULL` — el historial pierde justo el dato que importa.
3. **La credencial de conexión necesita `BYPASSRLS`** para resolver el slug antes
   de degradar. No debilita la segregación (no otorga `GRANT`s), pero es una
   condición del diseño de `db.sesion()` que conviene tener escrita.
4. **`postgres` sigue fuera del modelo** (`BYPASSRLS` + `CREATEROLE`): puede
   otorgarse el operador. Se cierra con el paso 15 (`DBUSER → crm_user`).
5. **La lista blanca hay que mantenerla.** Si algún día otra función necesita un
   tercer rol, hay que agregarlo a `ROLES_PERMITIDOS` — y ese es el punto: el
   cambio tiene que ser deliberado y visible.
6. **`autonomia_detener` es `SECURITY DEFINER` y su dueño es `postgres`**, con
   `BYPASSRLS`. Su alcance está contenido por el `search_path` fijo y por tener
   el estado escrito en el cuerpo, pero cualquier edición de esa función es un
   cambio de seguridad.

## Cambios que quedan pendientes

1. **El SQL del 10.11 como migración**, más el `GRANT autonomia_operador TO
   postgres with inherit false, set true`.
2. **Aplicar las migraciones 3 y 4** — no hecho.
3. **Decidir el dueño** de esas dos tablas (`postgres` frente a
   `asistente_owner`).
4. **Desplegar** `interruptor.py`, `idempotencia.py` y los cambios de `db.py`,
   `motor.py`, `reloj.py`, `api.py` y `coordinador.py` — **después** de las
   migraciones y del rol.
5. **El paso 15 (`DBUSER → crm_user`)**, que cierra el riesgo 4.
6. **Reactivar la autonomía** de Rapilink, que nacerá `detenida` — acto
   explícito y auditado, el último de la secuencia.

## Autonomía 0–4: NO implementada

El control sigue siendo **binario**: `activo` / `detenido`, más
`sin_registro`, `desconocido` y `sin_instalar`, que bloquean. Lo único que lo
modula es `es_accion_autonoma(herramienta, aprobada_por_humano)`. **Esta etapa
no introdujo niveles ni amplió el alcance.**

---

## Regla de cierre

| No pasar si… | Estado |
|---|---|
| `app_backend` puede activar | **no puede** — F, G, H y J denegados |
| `app_backend` puede alcanzar `autonomia_operador` | **no puede** — B, con `session_user` real |
| El operador no puede activar | **puede** — D, con el CLI real |
| Se necesita una credencial nueva | **no** — `autonomia_operador` es `NOLOGIN`; los logins de prueba son dobles, no producción |
| Una función `SECURITY DEFINER` permite saltarse el control | **ninguna** — 10 auditadas, una sola escribe, ninguna menciona `'activo'` |
| El restore cambia los permisos | **no los cambia** — L |
| Existe un camino alternativo para activar | **ninguno** — INSERT, UPDATE, DELETE, `SET ROLE`, función forjada, función propia y escritura sin `SET ROLE`, todos denegados |

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, **0**
tablas de las migraciones 3 y 4, **0** roles nuevos, **0** funciones nuevas.
Réplicas eliminadas. Un archivo modificado: `nucleo/persistencia/db.py`.
