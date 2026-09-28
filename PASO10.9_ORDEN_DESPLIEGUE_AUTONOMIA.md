# Paso 10.9 — Orden seguro entre migraciones 3/4 y código

**Fecha:** 17/09/2026
**Alcance:** auditoría + prueba en réplica. **Producción no se modificó** (ledger
45 filas, md5 `58ff01f220787396657af7832f6c48c8`; las tablas 3 y 4 no existen).
No se desplegó código, no se activó autonomía, ningún sistema externo se tocó.

> ## La Fase 2 ordena detenerse si existe cualquier fail-open. **Existen dos.**
>
> Los dos están condicionados a la misma causa —«la tabla no existe»— y los dos
> son **deliberados y documentados** en el propio código. Este informe los
> reporta y **no prescribe un orden de despliegue como aprobado**: esa decisión
> depende de qué se haga con ellos.

---

## 1. Auditoría de fail-open / fail-closed

### Los dos fail-open

**`nucleo/seguridad/interruptor.py:120`**

```python
if tabla_ausente(e):
    print("... La autonomia queda PERMITIDA porque nadie pudo detenerla todavia.")
    return Veredicto(True, SIN_REGISTRO, "el interruptor todavia no esta instalado")
```

**`nucleo/seguridad/idempotencia.py:195`**

```python
if tabla_ausente(e):
    print("... se ejecuta SIN control de repeticion.")
    return Resultado(ejecutada=True, decision="sin_control", clave=clave,
                     respuesta=hacer(), ...)
```

El segundo es más grave que el primero: `respuesta=hacer()` **invoca la llamada
externa de verdad**. No es un permiso teórico — es una mutación contra un
tercero sin ninguna protección contra repetición.

Ambos se disparan sólo con `tabla_ausente(e)`, que clasifica por **SQLSTATE
`42P01`** y por el nombre de clase `UndefinedTable`, nunca por el texto del
mensaje. La clasificación es correcta y estrecha: no se confunde con otros
errores.

**El razonamiento declarado en el código** (cabecera de `interruptor.py`):

> «la tabla NO EXISTE → PERMITE, y lo grita por consola. No es una excepción de
> conveniencia: es el único caso en que se sabe con certeza que NADIE pudo tirar
> el interruptor todavía. Sin esto, desplegar el código antes que la migración
> apagaría la operación entera de golpe — y en este proyecto el código va antes
> que la config, siempre.»

Es un argumento serio, y su premisa es «el código va antes que la migración».
**Choca de frente con el principio obligatorio de esta etapa**, que lista
«tabla inexistente» entre los casos que deben bloquear.

### Todo lo demás cierra correctamente

Barrido AST de los `except` de ambos módulos: 4 `return` dentro de un `except`,
dos cierran y dos son los de arriba. No hay `pass` silencioso, ni defaults
positivos, ni caché, ni bypass.

| Situación | Respuesta | Correcto |
|---|---|---|
| Fila dice `detenido` | **BLOQUEA** | sí |
| Fila dice `activo` | permite | sí |
| **No hay fila** para esa organización | **BLOQUEA** (`sin_registro`) | sí |
| No se pudo **leer** (error de base) | **BLOQUEA** (`desconocido`) | sí |
| **Timeout** de conexión | **BLOQUEA** | sí |
| **Permiso denegado** | **BLOQUEA** | sí |
| Estado fuera del catálogo | lo rechaza el `CHECK` de la base | sí |
| **La tabla no existe** | **PERMITE** | **NO** |

Y dos decisiones de diseño que refuerzan el cierre:

- **No se cachea nunca.** Cada evaluación va a la base. Es la razón explícita
  por la que esto no vive en `tenant_config`, cuya ruta se sirve cacheada y cae
  al YAML de la imagen cuando la base no responde — o sea que cortar la base
  reactivaría la autonomía.
- **`db.estado_autonomia()` no atrapa excepciones a propósito**, al revés que
  casi todo ese módulo: deja que el fallo suba para que el llamador lo convierta
  en bloqueo.

## 2. Comparación A / B / C

| | **A · migraciones → código** | **B · código → migraciones** | **C · híbrida con protección previa** |
|---|---|---|---|
| Ventana de riesgo | **ninguna** para el fail-open: la tabla existe antes de que el código pueda consultarla | **toda la ventana entre los dos despliegues** el fail-open está activo | ninguna, y además el fail-open queda inalcanzable por código |
| Comportamiento del CRM | sin efecto (las tablas son de `asistente`) — salvo el `ShareRowExclusiveLock` sobre `public.organization` al crear las FK | ídem | ídem |
| Comportamiento del código nuevo | lee una tabla que ya existe → camino fail-closed | lee una tabla ausente → **fail-open** | fail-closed siempre |
| Fail-open alcanzable | **no** | **sí** | **no** |
| Rollback | `drop table` de las 2 tablas; el código no está desplegado | revertir el despliegue de código; las tablas se aplican después | ambos |
| Qué exige | decidir dueño y ventana | nada extra — y por eso es la peligrosa | **cambiar el código**: que `tabla_ausente` bloquee |

**A neutraliza el fail-open operativamente**: si la tabla existe antes de que
exista el código que la consulta, ese `if` nunca se evalúa. Pero el camino sigue
en el código, disponible para cualquier despliegue futuro que invierta el orden
—o para una base restaurada a la que le falte la migración—.

**C lo elimina**: sustituir el `Veredicto(True, SIN_REGISTRO, …)` por un
bloqueo, y el `respuesta=hacer()` por una negativa. Con A ya aplicado, el
cambio no rompe nada: la tabla existe, así que ese camino no se recorre.

## 3. Resultados de los escenarios

Módulos reales contra réplicas restauradas del respaldo validado
`20260917_104932`. La «acción externa» es una función local que sólo anota si la
llamaron.

| # | Escenario | Exigido | Obtenido |
|---|---|---|---|
| 1 | Código nuevo + **tablas ausentes** (el estado de producción hoy) | BLOQUEA | **`interruptor` → PERMITE** · **`idempotencia` → ejecutó la acción externa (1 llamada)** |
| 2 | Tablas + interruptor **DETENIDO** | BLOQUEA | **BLOQUEA** (`estado=detenido`) |
| 3 | Tablas + interruptor **ACTIVO** | permite | **permite** |
| 4 | **Base inaccesible** (puerto muerto) | BLOQUEA | **BLOQUEA** (`estado=desconocido`, `ConnectionTimeout`) |
| 5 | **Permiso denegado** sobre la tabla | BLOQUEA | **BLOQUEA** (`InsufficientPrivilege`) |
| 6 | **Organización sin fila** de interruptor | BLOQUEA | **BLOQUEA** (`sin_registro`) |
| 7 | **Configuración inválida** (estado fuera del catálogo) | rechazar | **`CheckViolation`** en la base |

**5 de 7 correctos. Los dos que fallan son el mismo escenario 1**, que es
exactamente el estado de producción en este momento: las tablas no existen.

## 4. Estado inicial de una organización nueva

Hay **dos sembradores distintos, con estados distintos**, y la diferencia está
documentada como decisión deliberada:

| Vía | Estado inicial | Dónde |
|---|---|---|
| La **migración** `202609151710` | **`activo`** | `select distinct tc.organization_id, 'activo', null, 'migracion', …` |
| El **alta de un tenant nuevo** (`sembrar()`, llamado desde `cli/cargar_config.py`) | **`detenido`** | `(organization_id, DETENIDO, actor, motivo, organization_id)` |

Verificado en réplica: al aplicar la migración, la fila que queda dice
**`activo`**.

El código justifica la asimetría: la semilla de la migración describe empresas
**que ya estaban operando**, y nacer en `detenido` las habría apagado sin que
nadie lo pidiera; `sembrar()` en cambio crea un tenant donde nada opera
todavía.

> **Esto choca con el requisito de esta etapa:** «el kill switch debe quedar
> DETENIDO antes de que exista cualquier posibilidad de ejecución autónoma».
> Con la migración tal como está, la única organización de producción quedaría
> **`activo`** desde el instante en que se aplique. **Decisión pendiente.**

**Atomicidad del alta: correcta.** `sembrar(cur, …)` recibe un cursor y **no
abre sesión**: se ejecuta dentro de la misma transacción que crea la fila de
`tenant_config`, así que no puede existir un tenant sin registro de autonomía.
No atrapa excepciones a propósito. Y el `where not exists` impide duplicar si
alguien corre el alta dos veces.

## 5. Pruebas de idempotencia

Réplica con las tablas aplicadas. **4 llamadas externas en total**, todas
justificadas.

| Caso | Resultado | Llamadas externas |
|---|---|---|
| Misma clave + mismos argumentos, 1ª vez | `ejecutada=True`, `decision=ejecutar` | 1 |
| Misma clave + mismos argumentos, 2ª vez | `ejecutada=False`, `decision=repetida`, **devuelve la respuesta de la primera** | **0** |
| Misma clave + **argumentos distintos** | `ejecutada=False`, `decision=rechazada`, `codigo=CLAVE_REUTILIZADA` | **0** |
| **Concurrencia** (2 hilos, misma clave) | hilo 1 `ejecutar`, hilo 2 **`en_curso`** | **1** |
| La acción externa **falla** | la excepción **se relanza tal cual** | 1 |
| Reintento de la fallida **sin autorización** | `ejecutada=False`, `codigo=OPERACION_FALLIDA_PREVIA` | **0** |
| Reintento **con `reintentar_fallida=True`** | `ejecutada=True`, `decision=ejecutar` | 1 |

El mecanismo funciona: una operación lógica se ejecuta una vez, el reuso de
clave con otros argumentos se rechaza (no se devuelve el resultado del primero),
la carrera la gana uno solo, y un reintento tras un fallo exige autorización
explícita.

## 6. RLS y permisos

**Privilegios sobre `asistente.interruptor_autonomia`:**

| Rol | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| `app_backend` | **sí** | **sí** | no | no |
| `crm_user`, `crm_migrator`, `crm_owner` | no | no | no | no |
| `motor_user`, `job_executor`, `scheduler_coordinator`, `asistente_owner` | no | no | no | no |

**Sobre `asistente.operaciones_externas`:** `app_backend` tiene
`select, insert, update` y **no `delete`**; el resto, nada.

Ambas tablas: **RLS activa y `FORCE`**, con una política `tenant_aislado` que
compara `organization_id = asistente.org_actual()`. Ni el dueño se salta el
aislamiento. **Una organización no puede ver la del otro.**

Sin `UPDATE` ni `DELETE`, la tabla del interruptor es **de solo agregar** para
el runtime: el estado vigente es la fila más reciente y el historial no se puede
reescribir.

**Lo que el agente IA no puede hacer:** `crm_user` —la credencial del tráfico
del CRM— no tiene ningún privilegio sobre ninguna de las dos. Y las credenciales
del CRM (`crm_user`, `crm_migrator`, `crm_owner`) no tienen `USAGE` sobre el
esquema `asistente`.

> **Riesgo residual a nombrar:** `app_backend` —el rol efectivo con el que corre
> el motor— **tiene INSERT** sobre el interruptor. Como el estado vigente es la
> fila más reciente, un `INSERT` de `'activo'` **reactivaría la autonomía**. La
> protección de que eso no ocurra es **de código, no de permisos**:
> `detener()`/`reactivar()` sólo se invocan desde `cli/autonomia.py`, y ninguna
> herramienta del catálogo los expone. Cerrarlo a nivel de base exigiría un rol
> aparte para las transiciones, o una política que restrinja el `INSERT`.

## 7. Orden recomendado

**No lo prescribo todavía**, porque la Fase 2 ordena detenerse ante un
fail-open y hay dos. Lo que la evidencia sostiene:

- **La opción B queda descartada.** Desplegar el código antes de las migraciones
  abre una ventana en la que el interruptor permite y la idempotencia ejecuta
  mutaciones externas sin control. No es una hipótesis: está medido.
- **A es correcta y suficiente para el fail-open**, pero lo neutraliza por
  orden, no por diseño. El camino sigue existiendo para cualquier despliegue
  futuro y para una base restaurada sin la migración.
- **C = A + cerrar el código** es lo único que cumple el principio obligatorio
  al pie de la letra. El cambio es pequeño y localizado: dos `return`.

**Y hay una decisión previa a las tres:** el estado de la semilla. Con la
migración tal como está, aplicarla deja la única organización de producción en
**`activo`**, que es lo contrario de lo que pide esta etapa.

## 8. Rollback

| Nivel | Situación | Acción | Pérdida |
|---|---|---|---|
| 1 | Falla la migración 3 o 4 antes del COMMIT | automático: esa migración se deshace entera y no queda anotada (medido en 10.7) | ninguna |
| 2 | Hubo COMMIT y algo falla después | `drop table asistente.interruptor_autonomia` / `operaciones_externas`. No tienen dependientes; la única pérdida son las filas semilla | las filas semilla |
| 3 | Despliegue de código con problemas | revertir el despliegue. Con las tablas ya aplicadas, el código viejo simplemente no las usa | ninguna |
| 4 | Pérdida o alteración de datos | restaurar el respaldo con el procedimiento B.6/B.7 | lo posterior al respaldo |

El ledger no se toca en ningún nivel: una reversión física se documenta, no se
borra su fila.

## 9. Checklist de despliegue

Para cuando se autorice, en este orden:

1. **Decidir el estado de la semilla**: `activo` (como está) o `detenido` (como
   pide el principio). Si es `detenido`, hay que editar la migración — y eso
   cambia su checksum, así que se decide **antes** de aplicarla.
2. **Decidir el dueño** de las dos tablas nuevas: `postgres` (por omisión, como
   las otras 30 de `asistente`) o `asistente_owner` (como las 5 `job_*`).
3. **Decidir si se cierra el fail-open** en el código antes o después.
4. Respaldo B.6/B.7 fresco y **verificado restaurándolo**.
5. Pre-flight del runbook 10.7, con la adición de que las FK bloquean
   escrituras sobre `public.organization`.
6. Aplicar las migraciones 3 y 4 con `lock_timeout=10s` por sesión y credencial
   `postgres`.
7. Verificar: 2 tablas, RLS + FORCE, 1 política cada una, permisos de
   `app_backend`, y el estado de la fila semilla.
8. **Recién entonces** desplegar `interruptor.py` e `idempotencia.py`.
9. Verificar los escenarios 2 a 7 contra producción (los que no requieren
   romper nada: `detenido`, `activo`, sin fila).
10. **No activar autonomía.** Eso es una decisión aparte, posterior a todo esto.

## 10. Riesgos residuales

1. **Los dos fail-open siguen en el código** salvo que se decida cerrarlos. El
   orden A los vuelve inalcanzables hoy, no mañana.
2. **`app_backend` puede insertar en el interruptor** y así reactivar la
   autonomía. Hoy lo impide el código, no la base.
3. **La semilla de la migración dice `activo`.** Aplicarla sin decidir esto deja
   la autonomía permitida para Rapilink desde ese instante.
4. **Las dos tablas nacerían bajo `postgres`**, no bajo `asistente_owner`.
   Inconsistencia con las `job_*`, sin consecuencia funcional conocida.
5. **Las FK entran en `public.organization`**, con `ShareRowExclusiveLock` que
   bloquea escrituras del CRM durante su creación.
6. **`idempotencia` no protege contra la respuesta perdida.** Está dicho en su
   propia cabecera: si la llamada sale y la respuesta se pierde, nadie sabe si
   el tercero la aplicó. Lo que garantiza es que el reintento sea uno, con dueño
   y contado.
7. **La interacción con «niveles de autonomía 0–4» no se pudo auditar**: no
   existe tal escala en el código. El interruptor es binario
   (`activo`/`detenido`) y lo único que lo modula es
   `es_accion_autonoma(herramienta, aprobada_por_humano)`, que exige que la
   herramienta escriba **y** que ningún humano la haya aprobado. Si esos niveles
   son un requisito, hoy no están implementados.

---

## Estado al cerrar

Producción: ledger **45 filas**, md5 `58ff01f220787396657af7832f6c48c8`, **0
tablas de las migraciones 3 y 4**. No se aplicó ninguna migración, no se
desplegó código, no se activó autonomía, no se tocó el ledger, no se tocaron
Motor, Celery, WispHub ni SmartOLT. Réplicas `pg-109` y `pg-109b` eliminadas.

**El criterio de éxito —«no debe existir ninguna ruta por la cual kill switch
desconocido/error → ejecuto autonomía»— se cumple para todos los casos de error
salvo uno: la tabla ausente. Ahí hay dos rutas, están medidas, y la decisión de
qué hacer con ellas es suya.**
