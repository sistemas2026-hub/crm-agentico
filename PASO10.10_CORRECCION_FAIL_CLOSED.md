# Paso 10.10 — Corrección de fail-open y gobierno del kill switch

**Fecha:** 17/09/2026
**Producción:** intacta. Ledger 45 filas, md5 `58ff01f220787396657af7832f6c48c8`,
**0 tablas** de las migraciones 3 y 4. No se desplegó código, no se aplicó
ninguna migración, no se activó autonomía, no se tocaron Motor, Celery ni las
integraciones. Ningún sistema externo recibió una llamada.

> **Los dos fail-open están cerrados y demostrado en réplica.**
> Barrido AST final sobre los dos módulos: los 4 `return` dentro de un `except`
> bloquean, y no queda ninguna llamada a `hacer()` dentro de un `except`.

---

## 1. Problemas encontrados

| # | Problema | Estado |
|---|---|---|
| 1 | `interruptor.py` permitía si la tabla no existe | **corregido** |
| 2 | `idempotencia.py` ejecutaba `hacer()` si la tabla no existe | **corregido** |
| 3 | Medido: 1 llamada externa real con las tablas ausentes | **0 llamadas ahora** |
| 4 | La migración sembraba `activo` en vez de `detenido` | **corregido** |
| 5 | `app_backend` tiene INSERT sobre el interruptor | **analizado, no revocado** |
| 6 | Los niveles de autonomía 0–4 no existen en código | **documentado, no implementado** |

## 2. Cambios realizados en código

### `nucleo/seguridad/interruptor.py`

- **El caso «tabla ausente» bloquea.** `Veredicto(True, SIN_REGISTRO, …)` →
  `Veredicto(False, SIN_INSTALAR, …)`.
- **Estado propio para el control no disponible:** `SIN_INSTALAR = "sin_instalar"`,
  que distingue «falta la migración» de `desconocido` (no se pudo leer) y de
  `sin_registro` (la tabla existe, esta empresa no tiene fila).
- **`ESTADOS_SIN_CONTROL = (SIN_REGISTRO, DESCONOCIDO, SIN_INSTALAR)`** — los
  tres bloquean; se separan porque se leen y se arreglan distinto.
- Cabecera reescrita: la sección FAIL-CLOSED ahora enumera cinco casos y dice
  explícitamente que no hay excepciones, con el argumento antiguo y por qué se
  descartó.

Los tres resultados quedan distinguibles, como pedía la Fase 1:
`activo` (permite) · `detenido` (bloquea, decisión tomada) ·
`sin_instalar`/`sin_registro`/`desconocido` (bloquean, control no disponible).

### `nucleo/seguridad/idempotencia.py`

- **No se llama a `hacer()`.** El `return Resultado(ejecutada=True,
  decision="sin_control", respuesta=hacer(), …)` pasó a
  `Resultado(ejecutada=False, decision="control_ausente",
  codigo=CONTROL_AUSENTE, …)`.
- **`CONTROL_AUSENTE = "REGISTRO_NO_INSTALADO"`**, código nuevo.
- Docstring corregido: decía «la única excepción es que la tabla todavía no
  exista… ahí se ejecuta sin control».

### `nucleo/modelo/motor.py`

- **`CODIGOS_DE_BLOQUEO` incluye `idempotencia.CONTROL_AUSENTE`.** Sin este
  renglón el modelo habría leído el rechazo nuevo como un error de un tercero
  en vez de como una guarda del código. Pasa de 12 a 13 códigos.

### Pruebas ajustadas

Tres afirmaciones existentes exigían el comportamiento antiguo y habrían dado
verde con el fail-open puesto. Las tres se invirtieron, con el motivo escrito:

| Archivo | Afirmaba | Ahora |
|---|---|---|
| `tests/test_interruptor_autonomia.py` | «si la TABLA no existe, se permite» | bloquea, con `SIN_INSTALAR` y 0 llamadas |
| `tests/test_idempotencia_externa.py` | tabla ausente → `debe_ejecutar=True` | no ejecuta; ambos caminos con 0 llamadas |
| `tests/test_timeout_interruptor.py` | «la única excepción sigue siendo 'la tabla no existe'» | no hay excepciones al fail-closed |

**5 suites en verde:** `test_interruptor_autonomia`, `test_idempotencia_externa`,
`test_alta_tenant_autonomia`, `test_timeout_interruptor`,
`test_nucleo_sin_tenants`.

> `tests/test_reloj.py` falla con 2 comprobaciones, **y era así antes de esta
> etapa**: ese archivo ya venía modificado al empezar la sesión y las
> afirmaciones fallidas son de contadores de reconciliación y de las
> herramientas internas de Fase 2 — no mencionan el interruptor. La traza del
> propio test muestra la consulta de autonomía funcionando.

## 3. Cambios propuestos en migraciones

### Hecho: `supabase/202609151710_interruptor_autonomia.sql`

La fila semilla pasa de `'activo'` a `'detenido'`, con el razonamiento escrito
en el archivo. **El checksum cambia**: `e0d6b8dc…` → `9c8df21b…`. La migración
está pendiente y sin aplicar, así que no crea ninguna divergencia con el ledger.

El argumento que sostenía `'activo'` era: «hay trabajos que ya corren
(`cerrar_vencidas`) y nacer en `detenido` los apagaría». **La premisa es falsa,
y se midió:** en el commit desplegado hay **cero** referencias al interruptor —
ni en `nucleo/reloj.py`, ni en `nucleo/modelo/motor.py`, ni en
`nucleo/canales/api.py`, ni en `nucleo/programador/coordinador.py`. Toda la
integración es código sin desplegar. Sembrar `detenido` **no apaga nada**: hoy
nadie consulta esa tabla.

Con eso, queda **una sola regla**: empresa nueva o recién instrumentada =
DETENIDA. Igual que `sembrar()`, que ya nacía detenida.

### Propuesto y NO aplicado: la política restrictiva

```sql
create policy autonomia_no_activar
  on asistente.interruptor_autonomia
  as restrictive for insert to app_backend
  with check (estado = 'detenido');
```

**No se creó como archivo de migración**, para no alterar el conjunto de
pendientes que el paso 10.8 dejó cuidadosamente en cuatro. Queda pendiente de
autorización.

## 4. Análisis de `app_backend`

**Por qué tiene INSERT: porque lo necesita la única vía legítima de escritura.**

```
cli/autonomia.py --detener/--reactivar
  → interruptor.detener()/reactivar()
    → db.registrar_transicion_autonomia()
      → db.sesion(tenant)   ← "Conexion con el tenant fijado y el rol
                               degradado a app_backend"
```

Y también lo necesita el alta: `interruptor.sembrar(cur, …)` se llama desde
`cli/cargar_config.py` con el cursor de `sesion()`, que es igualmente
`app_backend`.

| Pregunta de la Fase 4 | Respuesta |
|---|---|
| Qué código usa INSERT | `registrar_transicion_autonomia` (transiciones) y `sembrar` (alta) |
| Cuándo | al mover el interruptor por CLI, y al dar de alta un tenant |
| Forma parte del alta | **sí**, y comparte transacción con `tenant_config` |
| Puede reemplazarse por una función controlada | Sí en forma, no en efecto: una `SECURITY DEFINER` seguiría siendo invocable por `app_backend`. Y con `FORCE RLS` el dueño también queda sujeto a las políticas |
| Otra vía para cambiar el estado | No: sin `UPDATE` ni `DELETE`, el estado sólo se mueve agregando filas |
| Qué rol debería poder modificarlo | Uno **distinto** del runtime. Hoy no existe: operador y motor son el mismo `app_backend` |
| Permite activar sin pasar por `cli/autonomia.py` | **Sí.** Medido: `app_backend` puede insertar `'activo'` directamente |

**El problema real, medido:** la base **no puede distinguir** al operador que
corre el CLI del motor en caliente — los dos son `app_backend`. La única
protección hoy es de código: ninguna herramienta del catálogo expone
`detener`/`reactivar`.

**El diseño propuesto, probado:** la política restrictiva de §3 produce la
asimetría que importa:

```
sin la politica:  app_backend PUEDE insertar 'activo'   <== el problema
con la politica:  'activo'   -> InsufficientPrivilege
                  'detenido' -> permitido
```

**El backend puede DETENER pero no ACTIVAR.** Parar es seguro y debe ser
posible desde cualquier parte; arrancar exige autoridad. Y no rompe el alta,
porque `sembrar()` inserta `'detenido'`.

La reactivación pasaría entonces por un rol que no sea `app_backend` — la
política es `to app_backend`, así que no alcanza a los demás. Eso exige una
credencial nueva para el CLI: **cambio pendiente, no hecho.**

## 5. Diseño final de permisos

| Rol | `interruptor_autonomia` | `operaciones_externas` |
|---|---|---|
| `app_backend` | SELECT + INSERT, **restringido a `detenido`** (propuesto) | SELECT, INSERT, UPDATE · sin DELETE |
| rol de operador (**a crear**) | INSERT de `activo` | — |
| `crm_user`, `crm_migrator`, `crm_owner` | nada | nada |
| `motor_user`, `job_executor`, `scheduler_coordinator`, `asistente_owner` | nada | nada |

Ambas tablas: **RLS activa + FORCE**, política `tenant_aislado` sobre
`organization_id = asistente.org_actual()`. Ni el dueño se salta el
aislamiento. Sin `UPDATE` ni `DELETE`, el interruptor es de solo agregar: el
estado vigente es la fila más reciente y el historial no se reescribe.

## 6. Pruebas fail-closed

Módulos reales contra réplicas construidas con B.6/B.7 desde el respaldo
`20260917_104932`. La acción externa es una función local que anota si la
llamaron.

| # | Escenario | Resultado |
|---|---|---|
| 1 | **Tabla inexistente** | **BLOQUEA** · `estado=sin_instalar` |
| 2 | **Tabla inexistente en idempotencia** | **NO llama `hacer()`** · 0 llamadas · `ejecutada=False` · `REGISTRO_NO_INSTALADO` |
| 3 | Base caída | **BLOQUEA** · `desconocido` |
| 4 | Timeout | **BLOQUEA** · `desconocido` |
| 5 | Permiso denegado | **BLOQUEA** · `desconocido` |
| 6 | Organización sin fila | **BLOQUEA** · `sin_registro` |
| 7 | Estado fuera del catálogo | lo rechaza el `CHECK` · `CheckViolation` |
| 8 | `detenido` explícito | **BLOQUEA** |
| 9 | `activo` explícito | permite |
| 10 | Acción no autónoma con `activo` | lectura → no la gobierna; escritura aprobada por humano → tampoco |
| 11 | **Organización nueva** | **`detenido`**, `actor=migracion`, y el veredicto bloquea |
| 12 | **Backend intenta insertar `activo`** | sin política: **lo consigue**. Con la política restrictiva: **`InsufficientPrivilege`**, y sigue pudiendo `detenido` |

**12 de 12. 0 fallas.** En la fase de tablas ausentes: **0 llamadas externas en
toda la corrida**.

## 7. Pruebas de idempotencia

| Caso | Resultado | Llamadas externas |
|---|---|---|
| Misma clave + mismos argumentos | 1ª `ejecutar`, 2ª `repetida` y devuelve la respuesta original | **1** |
| Misma clave + argumentos distintos | `CLAVE_REUTILIZADA` | **0** |
| Carrera (2 hilos) | gana uno, el otro `en_curso` | **1** |
| Fallo del tercero | la excepción se relanza tal cual | 1 |
| Reintento sin autorizar | `OPERACION_FALLIDA_PREVIA` | **0** |
| Reintento con `reintentar_fallida=True` | se ejecuta | 1 |
| **Tabla ausente** *(nuevo)* | `REGISTRO_NO_INSTALADO` | **0** |
| **Base caída** *(nuevo)* | `OPERACION_SIN_REGISTRO` | **0** |
| **Permiso denegado** *(nuevo)* | `OPERACION_SIN_REGISTRO` | **0** |

**Ningún escenario de control inoperativo ejecuta una llamada externa.**

## 8. Pruebas de organización nueva

**Todas las rutas de creación, auditadas:**

| Ruta | Estado inicial |
|---|---|
| Migración `202609151710` (seed) | **`detenido`** (era `activo`) |
| `interruptor.sembrar()` ← `cli/cargar_config.py` | **`detenido`** |
| `db.registrar_transicion_autonomia()` ← `cli/autonomia.py` | transición explícita, con actor y motivo obligatorios |
| Restauración desde respaldo | **conserva el estado respaldado** (verificado en §9) |

**No hay ninguna otra ruta** que escriba en esa tabla: el barrido del
repositorio devuelve exactamente esas tres, más las pruebas.

**Atomicidad:** `sembrar(cur, …)` recibe un cursor y no abre sesión — se
ejecuta en la misma transacción que crea `tenant_config`, así que no puede
existir un tenant sin registro de autonomía. No atrapa excepciones. El
`where not exists` impide duplicar.

## 9. Pruebas end-to-end

Réplica desde cero con B.6/B.7 → aplicar las 2 migraciones corregidas → respaldo
→ restauración desde cero en otra réplica virgen:

```
restaurar.sh codigo: 0
estado sembrado      : detenido | migracion
tras el restore      : detenido | migracion | "Estado inicial al crear el interruptor…"
veredicto            : permitido=False  estado=detenido
```

**RESTORE → DETENIDO → código nuevo → tabla disponible → acción autónoma
bloqueada.** El estado detenido sobrevive al ciclo de respaldo y restauración.

### Un matiz que la prueba dejó claro, y que conviene tener escrito

En esa misma corrida, `idempotencia.ejecutar()` **sí ejecutó** con el
interruptor en `detenido`. No es un fallo: **`idempotencia` no consulta el
interruptor** — son dos compuertas independientes, y quien las compone es el
motor:

```python
# nucleo/modelo/motor.py
autonoma = interruptor.es_accion_autonoma(herramienta, aprobada_por_humano)
if autonoma and tenant:
    veredicto = interruptor.veredicto(tenant)
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(...)
        raise AutonomiaDetenida(herramienta.nombre, veredicto)
# ... y sólo DESPUES se envuelve en idempotencia
```

Llamar a `idempotencia.ejecutar()` directamente saltea la compuerta de arriba.
En el camino real el interruptor corta antes.

*(Mi primer intento de esta prueba respaldó una réplica que las pruebas habían
dejado en `activo`, así que demostró que la restauración es fiel pero no que
`detenido` sobrevive. Se repitió sin pruebas de por medio.)*

## 10. Backup / restore

El procedimiento B.6/B.7 corregido se usó en todas las réplicas de esta etapa:
`restaurar.sh` código 0 en todas, y el ciclo completo
respaldo → restauración → verificación con los tres artefactos
(~8,9 MB + ~7 kB + ~3,7 kB). El estado del interruptor viaja en el volcado de
datos como cualquier otra fila.

## 11. Riesgos residuales

1. **`app_backend` sigue pudiendo insertar `'activo'`.** La política restrictiva
   está probada pero **no aplicada** y no existe como migración. Hasta entonces,
   la protección es de código.
2. **No existe un rol de operador.** Con la política puesta, `cli/autonomia.py`
   —que corre como `app_backend`— **no podría reactivar**. Hace falta una
   credencial nueva antes de aplicarla, o el CLI queda a medias.
3. **El checksum de la migración 3 cambió** (`e0d6b8dc…` → `9c8df21b…`). Está
   pendiente, así que no hay divergencia; pero si alguien la hubiera aplicado
   entre el 10.8 y hoy, habría una.
4. **Las dos tablas nacerían bajo `postgres`**, no bajo `asistente_owner`.
   Sigue sin decidirse.
5. **`idempotencia` no protege contra la respuesta perdida.** Si la llamada sale
   y la respuesta se pierde, nadie sabe si el tercero la aplicó. Garantiza que
   el reintento sea uno, con dueño y contado.
6. **Las compuertas se componen en el llamador.** Cualquier código nuevo que
   llame a `idempotencia.ejecutar()` sin consultar antes el interruptor se salta
   el kill switch. No hay nada que lo impida estructuralmente.
7. **`tests/test_reloj.py` sigue fallando** por dos comprobaciones anteriores a
   esta etapa, ajenas al interruptor.

## 12. Cambios que quedarían pendientes

1. **La política restrictiva** `autonomia_no_activar`, como migración nueva.
2. **El rol de operador** para las transiciones, y que `cli/autonomia.py` lo use
   en lugar de bajar a `app_backend`.
3. **El dueño** de las dos tablas nuevas.
4. **Aplicar las migraciones 3 y 4** en producción — no hecho.
5. **Desplegar** `interruptor.py`, `idempotencia.py` y los cambios de `motor.py`,
   `reloj.py`, `api.py` y `coordinador.py` — no hecho, y **después** de las
   migraciones.
6. **Reactivar la autonomía** para Rapilink, que con la semilla corregida
   quedará `detenida` — acto explícito, posterior a todo lo anterior.

## 13. Autonomía 0–4: NO implementada

**Confirmado: los niveles 0–4 no existen en el código, y esta etapa no los
implementó ni amplió su alcance.**

Lo que hay hoy:

- **El kill switch es binario:** `activo` / `detenido`, más tres estados de
  control no disponible que bloquean (`sin_registro`, `desconocido`,
  `sin_instalar`).
- **`es_accion_autonoma(herramienta, aprobada_por_humano)`** es lo único que
  modula: exige que la herramienta **escriba** (`solo_lectura=False`) **y** que
  ningún humano la haya aprobado. Una consulta nunca se gobierna por el
  interruptor; una escritura aprobada por una persona tampoco.
- **La aprobación humana existe** como mecanismo aparte
  (`Herramienta.aprobacion_humana`): proponer una acción no la ejecuta.
- **Los niveles 0–4 son arquitectura objetivo, no funcionalidad.** Si son un
  requisito, hoy no están implementados y su diseño no es parte de este paso.

---

## Criterio de éxito

| Exigido | Demostrado |
|---|---|
| Tabla ausente → BLOQUEA | **sí** · `estado=sin_instalar` |
| Tabla ausente en idempotencia → 0 llamadas externas | **sí** · `ejecutada=False`, `REGISTRO_NO_INSTALADO` |
| Base caída → BLOQUEA | **sí** |
| Permiso denegado → BLOQUEA | **sí** |
| Configuración inválida → BLOQUEA | **sí** · `CheckViolation` |
| Nuevo tenant → DETENIDO | **sí** · las tres rutas, y sobrevive al restore |
| El backend no puede activar arbitrariamente | **probado con la política restrictiva; no aplicada** |

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, **0
tablas** de las migraciones 3 y 4. Réplicas eliminadas. No se aplicaron
migraciones, no se desplegó código, no se activó autonomía, no se cambió
`DBUSER`, no se tocaron ownership, RLS productivo, Motor, Celery ni
integraciones.
