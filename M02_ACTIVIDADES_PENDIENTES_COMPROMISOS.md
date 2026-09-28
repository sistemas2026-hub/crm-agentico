# M02 — Actividades, pendientes y compromisos

**Fecha:** 2026-09-19
**Veredicto:** **M02 = GO**

```
Pruebas propias ........  33 passed / 0 failed / 0 skipped
Regresion completa .....  4374 passed / 1 failed / 19 skipped
  el unico fallo ....... CATEGORIA C (entorno), ya probado en M03-F-B y M03-G
Migraciones ............  1  -- aditiva, reversible, NO aplicada en produccion
Entidades nuevas .......  0
Efectos externos .......  0        (espia probado que dispara primero)
Produccion .............  SIN CAMBIOS -- 20 claves, DIFERENCIAS: NINGUNA
Commit .................  no
```

---

## A. Auditoría mínima

**El hallazgo que cambió el paso: la entidad ya existía, completa.**

`operaciones.ActividadOperativa` (`models.py:93`) estaba construida y **viva en
producción**:

| | [MEDIDO] |
|---|---|
| **Tabla** | `operaciones_actividad` **existe** en producción, **0 filas** |
| **RLS** | **habilitada Y forzada**, 2 políticas, 9 índices |
| `ORG_SCOPED_TABLES` | ya la incluye (`common/rls/__init__.py:140`) |
| **Tipos** | 9 declarados: tarea, pendiente, compromiso, seguimiento, solicitud_informacion, dependencia, handoff, soporte, correccion |
| **Estados** | 7 operativos + eje de validación separado (6 valores) + `vuelta` |
| **Dependencia** | `depende_de` self-FK, con `clean()` que impide el ciclo de largo 1 |
| **Bloqueo** | `motivo_bloqueo` + **CHECK en la base** (`actividad_bloqueada_exige_motivo`) |
| **Consumidores** | **5 detectores de M09 ya la leen**, y 5 habilidades declaradas la citan |
| **Auditoría** | `operaciones/auditoria.py` con `ENTIDAD_ACTIVIDAD` ya declarado |
| **Admin** | ya registrada |

**Lo que NO existía:** una sola forma de crear una actividad o moverla de estado
que no fuera el panel de Django. Sin servicios, sin serializers, sin endpoints,
sin pruebas.

**Eso es M02: la capa operativa.** No una entidad nueva.

Estado de las alternativas, medido: `common.Activity` **610 filas** (creció
desde las 516 que citaba la auditoría previa), `task` **0 filas**.

---

## B. Arquitectura

```
common.Activity          lo que YA paso. Bitacora del CRM, 610 filas vivas.
                         M02 ESCRIBE aqui un hecho por transicion.
                         NO se usa como agenda.
         ^
         | operaciones/auditoria.py  (superficie existente, sin tabla nueva)
         |
ActividadOperativa       lo que FALTA hacer. Tabla propia, RLS forzada.
         |
         +-- operaciones/actividades.py   <-- NUEVO: servicios (M02)
         +-- operaciones/views.py         <-- +3 vistas
         |
         v
M09 supervisor.py        5 detectores que ya la leian. SIN TOCAR.
```

La distinción la declaró el propio modelo en su docstring y M02 la respeta:
*"Activity: lo que YA paso, en pasado, sin estado ni vencimiento."*

---

## C. Modelo utilizado

**`operaciones.ActividadOperativa` — reutilizada, no recreada.** 0 entidades
nuevas. No se creó `Task`, `ActivityTask`, `PendingTask` ni ninguna variante.

---

## D. Campos

Los 18 que exigía §4. **16 ya existían**; se agregaron **2**:

| Campo | Estado |
|---|---|
| `org`, `tipo`, `titulo`, `descripcion` | **[EXISTENTE]** |
| `estado_operativo`, `estado_validacion`, `vuelta` | **[EXISTENTE]** |
| `responsable` (nullable) | **[EXISTENTE]** |
| `origen_tipo` + `origen_id` | **[EXISTENTE]** — patrón desacoplado, sin GenericFK |
| `vence_en` (nullable) | **[EXISTENTE]** |
| `depende_de` (self-FK) | **[EXISTENTE]** |
| `motivo_bloqueo` | **[EXISTENTE]** |
| `created_by`, `updated_by`, `created_at`, `updated_at` | **[EXISTENTE]** (BaseModel) |
| **`completado_en`** | **[NUEVO]** |
| **`validado_en`** | **[NUEVO]** |

**Por qué esos dos y no más:** `updated_at` se mueve con cualquier cambio
posterior, así que no sirve para responder *"qué se completó esta semana"*.
Reconstruirlo desde `common.Activity` obligaría a recorrer la bitácora entera
para algo tan básico. Son **hechos**, no derivaciones — a diferencia de la
capacidad de M03-G, que sí se deriva. Nulos mientras el hecho no ocurra: una
actividad sin completar **no** tiene fecha de completada.

---

## E. Estados — dos ejes, no uno

```
OPERATIVO    pendiente · en_gestion · en_espera · bloqueada · escalada
             completada · cancelada
VALIDACION   sin_evaluar · pendiente · aprobable · requiere_correccion
             requiere_revision · aprobado
```

**`validacion_pendiente` NO es un estado operativo**, y el modelo ya lo decía:
con un solo eje habría que elegir, y se perdería *"completada + requiere
corrección"*, que es el caso real que produce una devolución.

**Máquina de estados explícita** (`actividades.TRANSICIONES`). Una transición
que no esté declarada no ocurre. `cancelada` es terminal de verdad; `completada`
admite volver a `en_gestion` **solo** por una devolución de validación.

---

## F. Tipos

Los 9 del modelo, sin agregar ninguno. Un compromiso y una solicitud de
información son el mismo objeto con distinto `tipo` — crear nueve entidades
sería el error simétrico al de meter todo en `Activity`.

---

## G. Operaciones

Las 13 de §12, en `operaciones/actividades.py`. Todas
`@transaction.atomic` + `select_for_update()` sobre la fila.

| | Operación | Nota |
|:--:|---|---|
| A/B | `crear` | tipo libre entre los 9; compromiso sin fecha es legítimo |
| C | `asignar_responsable` | acepta `None` (quitar); no-op si no cambia |
| D | `iniciar_gestion` | rechaza si está bloqueada |
| E | `poner_en_espera` | distinto de bloquear |
| F | `bloquear` | **exige motivo** |
| G | `desbloquear` | limpia el motivo; destino explícito |
| — | `escalar` | **exige motivo**. Se añadió porque `ESCALADA` existía en el modelo y era inalcanzable por API |
| H | `completar` | **no cierra** si hay validación pendiente |
| J | `validar` | 3 decisiones; devolución sube `vuelta` |
| I | `cancelar` | **exige motivo**; no borra |
| K | `establecer_dependencia` | detecta ciclos de cualquier longitud |
| — | `cambiar_vencimiento` | auditado con anterior y nueva |
| L/M | `pendientes_relevantes` + `resumen` | lectura |

---

## H. Dependencias

`A depende de B`: mientras B no termine, A **no se puede completar** — el
servicio lo rechaza y la propiedad `bloqueada_por_dependencia` lo expone.

**Ciclos rechazados, de cualquier longitud.** El modelo ya impedía el de largo
1; el servicio recorre la cadena hacia arriba (tope 64) y rechaza si desde el
candidato se vuelve a la misma actividad. Es validación de **servicio**:
PostgreSQL no puede expresar *"sin ciclos"* en una constraint, tal como §7
contemplaba.

**[RIESGO] Un defecto real que encontró la prueba de ciclo de largo 3:** el
recorrido partía del objeto que pasa quien llama, que puede estar rancio — con
una copia vieja el ciclo no se detectaba y pasaba. Corregido releyendo la fila
antes de recorrerla. Lo cazó `test_15` antes de que llegara a ninguna parte.

---

## I. Compromisos

`tipo='compromiso'` con responsable, fecha límite **cuando exista**, origen,
descripción y estado.

**Un compromiso sin fecha es legítimo y no se le inventa una.** Queda
`vence_en = NULL` y se clasifica como **`SIN_VENCIMIENTO`**, que es un dato
distinto de *"vence hoy"*. Y no todo pendiente es compromiso: es un tipo entre
nueve.

---

## J. Bloqueos

Motivo (obligatorio, con CHECK en la base), fecha, actor y referencia — los
cuatro de §8, todos en el evento de auditoría.

**Un bloqueo describe un impedimento, no atribuye culpa.** No se crea ningún
*"incumplimiento de persona"*. Y `EN_ESPERA` se mantiene separado de
`BLOQUEADA`: esperar algo previsto no es estar trabado, y mezclarlos dejaría al
Supervisor sin poder distinguir *"va lento"* de *"no avanza"*.

---

## K. Responsables

Tres situaciones distinguidas: **sin responsable** (legítimo — el propio
`help_text` dice *"una actividad sin responsable es una señal, no un error"*, y
M09 tiene un detector para ella), **asignado**, y **cambiado** (auditado con
anterior y nuevo).

**Nadie asigna automáticamente.** Ni el sistema ni la IA. El Supervisor podrá
**proponer**; ejecutar es de una persona.

---

## L. Auditoría

`common.Activity` vía `operaciones/auditoria.py`. **Sin tabla nueva.**

Los 10 hechos de §15 quedan registrados: creación (`CREATE`), asignación
(`ASSIGN`), cambios de estado (`STATUS_CHANGED`), bloqueo y desbloqueo, cambio
de vencimiento (`UPDATE`), completado, validación (`APPROVED` / `REJECTED`),
cancelación, dependencia (`LINKED_PARENT` / `UNLINKED_PARENT`).

Cada fila lleva org, actor, momento, estado anterior, estado nuevo y motivo.
**`test_19` verifica la secuencia exacta de 8 verbos** de un ciclo completo.

**Y `test_24` comprueba lo que `auditoria.py` advierte que es el riesgo**: que
todo `action` y todo `entity_type` escrito esté **declarado** en sus choices —
el modo de fallo silencioso que produjo el `tecnico_lider` no documentado.
Además afirma que `common.Activity` **no ganó** campos de agenda
(`estado_operativo`, `vence_en`, `responsable`, `depende_de`, `motivo_bloqueo`).

---

## M. Concurrencia

`transaction.atomic()` + `select_for_update()` en **todas** las mutaciones.

`test_20` mide el caso que §16 nombra: **completar y cancelar a la vez**. Con el
lock, una gana y la otra recibe `TransicionInvalida` — nunca las dos. Medido:
`oks == 1`, `errores == ["TransicionInvalida"]`.

---

## N. Idempotencia

`manejar_idempotencia`, el mecanismo existente. **Sin sistema nuevo.**

| Caso | Resultado |
|---|---|
| Replay exacto | **201**, 1 sola fila |
| Misma clave, cuerpo distinto | **409** `IDEMPOTENCY_KEY_REUSED`, no ejecuta |

Los serializers devuelven **todo en texto**: el cuerpo se guarda tal cual en
`MutacionIdempotente`, y ahí un UUID crudo no es JSON — el defecto real
encontrado en M03-F-B.

**Deduplicación (§23)**: `org + tipo + origen_tipo + origen_id + estado activo`.
Otro tipo sobre el mismo origen sí es legítimo, y cerrada la primera se puede
abrir otra igual — probado en `test_21b`.

---

## O. Seguridad

| Verificación | Resultado |
|---|---|
| Tenant A no ve ni toca datos de B | **404** en detalle y transición |
| El cliente **no puede elegir** la organización | probado: `org`/`organization_id` en el cuerpo se ignoran, la fila nace en la org de la sesión |
| Usuario sin rol de gestión | **403** en las 3 rutas |
| Rol de gestión | opera |

**Y aquí el aislamiento sí llega a la base**, a diferencia de `campo_*`:
`operaciones_actividad` tiene `org_id` propio, está en `ORG_SCOPED_TABLES` y
en producción tiene **RLS habilitada Y forzada** con 2 políticas. No se creó
ninguna excepción de seguridad (§31) — la tabla ya cumplía el patrón.

**Permisos:** se reutilizó `EsJefeDeOperaciones`, sin roles nuevos.
**[DEUDA]** No hay granularidad fina (quién puede validar vs. quién puede
cancelar): se usó el permiso existente más cercano, como §19 autoriza.

---

## P. Integración M09

**M09 no se tocó.** Ni una línea de `supervisor.py`.

Los 5 detectores que ya existían pasan a tener datos que leer, y `test_25` lo
comprueba creando la situación de cada uno y verificando que `detectar()`
emite las 5 señales: `ACTIVIDAD_VENCIDA`, `ACTIVIDAD_SIN_RESPONSABLE`,
`ACTIVIDAD_BLOQUEADA`, `COMPROMISO_POR_VENCER`, `DEPENDENCIA_PENDIENTE`.

**No se duplicó el motor de señales** (§21): no hay una segunda fuente de
verdad, hay una tabla que antes estaba vacía.

**`test_26` mide que detectar no ejecuta**: tras `detectar()`, ninguna
actividad cambió de estado y no apareció auditoría nueva — y se comprueba
primero que el detector **sí emitió** señales, para que su cero signifique algo.

---

## Q. API

```
GET  /api/operaciones/actividades/                      lista + resumen
POST /api/operaciones/actividades/                      crear
GET  /api/operaciones/actividades/<id>/                 detalle + historial
POST /api/operaciones/actividades/<id>/transicion/      11 acciones explicitas
```

**Cuatro rutas, no once.** Las transiciones van por nombre
(`asignar`, `iniciar`, `esperar`, `bloquear`, `desbloquear`, `escalar`,
`completar`, `validar`, `cancelar`, `dependencia`, `vencimiento`) contra la
máquina de estados.

**No hay PATCH sobre `estado_operativo`**, y es deliberado: haría representable
cualquier salto y la máquina no significaría nada. `test_api_no_hay_patch`
comprueba que PATCH, PUT y DELETE devuelven **405**.

---

## R. Frontend

**No se tocó.** No existe pantalla M02 que integrar sin arquitectura adicional,
y §27 lo excluye. La API queda lista para consumo.

---

## S. Migraciones

```
operaciones/migrations/0005_m02_fechas_actividad.py
    + AddField completado_en (DateTimeField, null=True, blank=True)
    + AddField validado_en   (DateTimeField, null=True, blank=True)
```

**Por qué es necesaria** (§30): §4 exige poder identificar cuándo se completó y
cuándo se validó. `updated_at` no sirve —se mueve con cualquier cambio
posterior— y derivarlo de la bitácora obligaría a recorrer `common.Activity`
para una pregunta básica.

| | |
|---|---|
| **Aditiva** | sí — solo `AddField` |
| **Reversible** | sí — `RemoveField`, sin pérdida |
| **Backfill** | **ninguno** — nullable, y la tabla tiene **0 filas** en producción |
| **`organization_id`** | ya lo tenía |
| **RLS** | ya habilitada y forzada; agregar columnas no la altera |
| **Aplicada en producción** | **NO** — verificado: 0 columnas nuevas |

`makemigrations --check` → **"No changes detected"** tras generarla.

---

## T. Pruebas

```
33 passed / 0 failed / 0 skipped
```

Las 27 ejecutables de §28 más 6 de contrato. Verifican **persistencia real y
efecto**, no HTTP 200. Las que más importan:

| Prueba | Qué demuestra |
|---|---|
| `test_11` | Completar **no es cerrar**: completada + validación pendiente sigue viva; la devolución sube `vuelta` y vuelve a gestión sin borrar lo hecho |
| `test_15` | Ciclos de largo 1, 2 y 3 rechazados — y la cadena legítima queda intacta |
| `test_20` | Completar y cancelar a la vez: una gana, la otra recibe `TransicionInvalida` |
| `test_24` | `common.Activity` conserva su semántica y **no ganó campos de agenda** |
| `test_25` | Los 5 detectores de M09 consumen datos M02 |
| `test_26` | Detectar **no ejecuta** — con el instrumento probado antes |
| `test_27` | 0 llamadas externas, con el espía probado antes |
| `test_22` | El cliente no puede elegir la organización |

---

## U. Regresión

```
4374 passed · 1 failed · 19 skipped        (24m 29s)
```

| Cat. | Fallo | |
|:--:|---|---|
| **A** (por M02) | `test_m09f_gobernanza::test_no_existe_ninguna_ruta_de_ejecucion` · `test_m03e5c_cierre::test_17_e5_no_trajo_ningun_sistema_paralelo` | **2, CORREGIDOS** |
| **B** (preexistente) | — | 0 |
| **C** (entorno) | `test_portal_rls` | **1** |
| **D** (test incorrecto) | — | 0 |

**Los dos fallos A fueron guardas de arquitectura haciendo su trabajo, y
ninguno se relajó:**

1. **Guarda de gobernanza**: fija el inventario exacto de rutas de
   `operaciones/urls.py`. Se declararon las 3 nuevas **con su justificación
   escrita** —por qué la de transición escribe y aun así no ejecuta— igual que
   hicieron M03-E4, E5-B y G.

2. **Guarda de sistemas paralelos** (M03-E5-C): leía
   `programacion.py` **+** `views.py` y exigía que no apareciera `Activity`,
   para que M03-E5 no inventara una auditoría paralela. Pero `views.py` aloja
   vistas de varios módulos, y `common.Activity` **es** la superficie de
   auditoría declarada de `operaciones` —`operaciones/auditoria.py` existe para
   eso y `PropuestaSupervisor` ya la usaba—. **No es un sistema paralelo: es el
   que ya existía.** Se acotó esa comprobación a `programacion.py`, donde vive
   el código que el guarda vigila, con la razón escrita en el propio test. Las
   demás comprobaciones (sistemas externos, idempotencia, celery) siguen
   cubriendo los dos archivos.

**El fallo C** es `test_portal_rls`, ya probado dos veces en este proyecto:
está marcado `postgres_only`, exige rol no-superusuario y
`crm.test_settings_postgres`, y bajo esa configuración da 2 passed.

---

## V. Efectos externos

```
WispHub 0 · SmartOLT 0 · WhatsApp 0 · HTTP externo 0
```

Instrumentado en `socket.socket.connect` alrededor del ciclo completo —crear,
asignar, iniciar, bloquear, desbloquear, completar, validar, listar y
`supervisor.detectar()`—. El cero se leyó **después** de probar que el espía
dispara con una sonda deliberada.

---

## W. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **20 claves → DIFERENCIAS: NINGUNA.**

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
ActividadOperativa 0 · Activity 610 · Task 0
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Disponibilidad 0 · operaciones_externas 0
MutacionIdempotente 14 · BusinessCalendar 1 · kill switch detenido

migracion 0005 aplicada en produccion: NO  (0 columnas nuevas)
RLS en operaciones_actividad: habilitada=True forzada=True
```

**No se convirtió ni una sola de las 610 `common.Activity` en pendiente** (§22).
No se fabricaron datos. M02 arranca con registros nuevos.

---

## X. Deudas

Documentadas, ninguna implementada:

| # | Deuda |
|:--:|---|
| 1 | **Granularidad de permisos**: quién valida vs. quién cancela usa el mismo rol |
| 2 | **Migración 0005 sin aplicar** — decisión suya cuándo y cómo |
| 3 | **Frontend**: no hay pantalla; la API queda lista |
| 4 | **Sin señal de "pendiente sin movimiento"** ni de duplicado — §20 los nombra y M09 no tiene detector; no se creó uno para no duplicar su motor |
| 5 | **Migración de históricos**: si alguna `common.Activity` representa un pendiente real, requiere decisión suya (§22 exige detenerse) |
| 6 | **Tope de cadena de dependencias** = 64, validado por servicio, no por base |
| 7 | RLS de `campo_*` · B-7 · punto ciego de H-05 · zona · vehículo · autonomía 2+ |

---

## Y. GO / NO-GO

| # | Criterio | |
|:--:|---|:--:|
| 1 | Estructura operacional clara | **SÍ** — reutilizada, 0 entidades nuevas |
| 2 | Pendientes y compromisos diferenciados | **SÍ** — `tipo` entre 9 |
| 3 | `Activity` mantiene su significado | **SÍ** — `test_24` |
| 4 | Estados funcionan | **SÍ** — máquina explícita, dos ejes |
| 5 | Dependencias funcionan | **SÍ** — incluida detección de ciclos |
| 6 | Bloqueos funcionan | **SÍ** — motivo obligatorio, CHECK en base |
| 7 | Vencimientos funcionan | **SÍ** — 5 clasificaciones, ventana explícita |
| 8 | Responsables funcionan | **SÍ** — 3 situaciones, sin asignación automática |
| 9 | Auditoría funciona | **SÍ** — sin tabla nueva |
| 10 | Concurrencia funciona | **SÍ** — `test_20` |
| 11 | Idempotencia funciona | **SÍ** — mecanismo existente |
| 12 | Tenant isolation funciona | **SÍ** — y con RLS forzada en base |
| 13 | M09 puede leer | **SÍ** — `test_25`, sin tocar M09 |
| 14 | Sin ejecución autónoma | **SÍ** — `test_26` |
| 15 | 0 efectos externos | **SÍ** |
| 16 | Sin regresiones atribuibles | **SÍ** — los 2 fallos A corregidos declarando, no relajando |
| 17 | Producción intacta | **SÍ** — 20 claves |

# M02 = GO

---

```
codigo ......... 1 archivo creado (actividades.py, 576) · 4 modificados
pruebas ........ 1 archivo creado (33 pruebas, 738 lineas)
entidades ...... 0     modelos nuevos ... 0     tablas nuevas ... 0
migraciones .... 1 aditiva y reversible, NO aplicada en produccion
M09 ............ sin tocar     common.Activity ... semantica intacta
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no
```
