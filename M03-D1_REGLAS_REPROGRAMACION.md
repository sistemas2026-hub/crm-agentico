# M03-D1 — Reglas de negocio para la reprogramación

**Fecha:** 2026-09-18
**Alcance:** análisis, decisión y especificación funcional. **0 código, 0 migraciones, 0 cambios en producción.**

---

## 0. Lo que este paso cierra, y lo que no

Dos decisiones llegaron aprobadas (P-4 y Caso G). Este informe las convierte en
reglas verificables, y encuentra que **una de las dos deja un borde que la
decisión aprobada no cubre** y **la otra choca con un caso real que conviene
mirar antes de implementar**. Los dos quedan marcados `[PENDIENTE]`, no
resueltos por mi cuenta.

El hallazgo que más cambia el diseño es una sola línea de código:

> **[MEDIDO]** `campo/services/transiciones.py:293`
> ```python
> if nuevo_estado in (OrdenTrabajo.EN_SITIO, OrdenTrabajo.EN_CAMINO) and not orden.iniciada_en:
>     orden.iniciada_en = ahora
> ```
>
> **`en_camino` YA escribe `iniciada_en`.** El sistema considera que la ejecución
> empezó cuando el técnico **sale**, no cuando llega. Así que el Caso G se
> clasifica por medición y no por criterio: **`en_camino` es una OT iniciada.**

---

## 1. Estado actual medido

**[MEDIDO]** Producción, solo `SELECT` (`read_only = True`):

```
ProgramacionSemanal ....  0        ordenes ..............  3
ProgramacionOrden ......  0        ordenes programadas ..  0
NovedadOperativa .......  0        ordenes asignadas ....  3
EventoTrabajo .......... 12        Activity ............. 592  (564 Case, 28 Lead)

estados de OT:   en_sitio 2 · completada_campo 1
tipos de evento: datos_actualizados 3 · accion_marcar_en_camino 3 ·
                 accion_marcar_llegada 3 · evidencia_confirmada 2 ·
                 trabajo_completado_campo 1
```

**[MEDIDO]** M03-B y M03-C están desplegados y **sin usar**: cero planes, cero
líneas. No existe una sola reprogramación real que auditar.

**[MEDIDO]** Las 3 órdenes de producción están **las tres iniciadas**
(`en_sitio`, `completada_campo`): con las reglas de este informe, **ninguna
entraría hoy por la ruta normal de reprogramación.**

**[RIESGO]** Eso significa que la ruta normal se implementará sin ningún caso
real que la ejercite, y la ruta de contingencia es la que aplicaría a todo lo que
hoy existe. Conviene tenerlo presente al decidir el alcance de M03-D2.

---

## 2. Decisiones aprobadas

### P-4 — plan publicado

**[DECISIÓN APROBADA]**

> Un `ProgramacionSemanal` publicado **NO queda congelado de forma absoluta**,
> pero **no se permite modificarlo silenciosamente**. Toda modificación posterior
> a la publicación es una **REPROGRAMACIÓN FORMAL** con trazabilidad de: qué
> estaba programado, qué cambió, fecha/hora anterior, fecha/hora nueva, motivo,
> quién, cuándo, y referencia al contexto operativo que lo originó.
>
> **No eliminar ni sobrescribir silenciosamente la programación anterior.**

Corresponde a la alternativa **P4-C** de M03-D.

### Caso G — orden ya iniciada

**[DECISIÓN APROBADA]**

> Una OT que **ya inició su ejecución NO entra por la ruta normal** de
> reprogramación. Debe existir un tratamiento diferenciado mediante
> `NovedadOperativa` / contingencia y decisión del responsable.
>
> **No inventar automáticamente una nueva programación ni alterar
> `programada_para` de una OT ya iniciada.**

---

## 3. Reglas de negocio definitivas

### Ruta y frontera

**R-1 [DECISIÓN APROBADA]** Existen **dos rutas**, no una:

```
RUTA NORMAL          la OT no ha iniciado    → cambia la programación
RUTA DE CONTINGENCIA la OT ya inició         → registra la novedad, NO cambia la programación
```

**R-2 [MEDIDO + DISEÑO]** La frontera entre las dos **no la decide un criterio
nuevo: la decide `iniciada_en`.** Una OT ha iniciado si y solo si
`iniciada_en IS NOT NULL`. *Evidencia: `transiciones.py:293`.*

> **Por qué se ancla ahí y no en una lista de estados:** una lista se desincroniza
> cuando alguien agrega un estado; `iniciada_en` lo escribe la propia máquina de
> transiciones. Si mañana aparece un estado nuevo que marca inicio, la frontera lo
> incluye sola.

**R-3 [MEDIDO]** `estado_operativo = asignada` es el único estado sin
`iniciada_en`: *"ninguna transición vuelve a ese estado y `iniciada_en` sólo se
escribe al salir de él"* (`supervisor.py:341`). **La ruta normal opera sobre
`asignada` y nada más.**

### Atomicidad y coherencia

**R-4 [DISEÑO]** Una reprogramación escribe **la línea de plan y
`programada_para` en la misma transacción**, con `select_for_update()` sobre la
OT. *Mismo mecanismo que M03-B, verificado desarmándolo.*

**R-5 [DISEÑO]** **`dia = timezone.localtime(programada_para).date()`**, la misma
conversión que usan M03-B y H-05. No se introduce otra. *Evidencia:
`supervisor.py:480`, `programacion.py::_dia_y_hora`.*

**R-6 [DISEÑO]** **Una OT no puede tener más de una línea vigente**
(`planificada` o `confirmada`) en ningún momento visible desde fuera de la
transacción.

> **[RIESGO] Por qué es una regla y no higiene:** `_programacion_vigente` hace
> `.first()` y el `Meta.ordering` de `ProgramacionOrden` es `["dia","secuencia"]`,
> así que con dos líneas vigentes **devuelve la del día más temprano — la
> obsoleta**. M09 razonaría sobre un plan que ya no rige, sin que nada fallara.

**R-7 [DISEÑO]** La línea anterior se marca **`reprogramada`** dentro de la misma
transacción. *Evidencia: el estado existe en el modelo y **ningún código lo
escribe** — M03-D sería su primer escritor.*

### Historial

**R-8 [DECISIÓN APROBADA + DISEÑO]** **El historial se escribe ANTES de mover la
fecha.**

> Programar solo tenía que dejar un estado correcto. Reprogramar tiene que dejar
> constancia de **lo que dejó de ser cierto**, y si eso se escribe al final y algo
> falla, lo que se pierde es justo la parte que no se puede reconstruir.

**R-9 [DECISIÓN APROBADA]** **No se borra ni se sobrescribe la programación
anterior.** La línea anterior se marca, no se elimina.

### Publicación

**R-10 [DECISIÓN APROBADA]** Modificar la programación de una OT que ya está en
un plan **publicado** exige la ruta formal completa, con los siete datos de
trazabilidad del §7.

**R-11 [DISEÑO]** En un plan **borrador** la reprogramación sigue siendo formal y
deja historial, pero **no exige** referencia al contexto operativo: un borrador
*"no compromete a nadie: las cuadrillas no lo ven"* (`supervisor.py:630`), así que
no hay compromiso que explicar.

### Contingencia

**R-12 [DECISIÓN APROBADA]** Para una OT iniciada, la ruta de contingencia
registra una `NovedadOperativa` y **NO toca `programada_para`, ni la línea de
plan, ni el estado operativo**.

> **[DISEÑO] Y eso es coherente, no una limitación:** `programada_para` dice lo
> que se **planificó**; `iniciada_en` / `completada_campo_en` dicen lo que
> **pasó**. Un trabajo que empezó tarde no necesita que se le reescriba el plan:
> necesita que quede registrado por qué. Reescribir el plan borraría justamente la
> diferencia entre lo previsto y lo ocurrido.

---

## 4. Matriz de estados de OrdenTrabajo

**Clasificación por `iniciada_en`, no por criterio.**

| `estado_operativo` | ¿escribe `iniciada_en`? | Reprogramación normal | Contingencia | Evidencia |
|---|:--:|:--:|:--:|---|
| **`asignada`** | **no** | **SÍ** | — | `transiciones.py:293` (no está en la tupla) |
| **`en_camino`** | **SÍ** | **NO** | **SÍ** | `transiciones.py:293` — **está en la tupla** |
| **`en_sitio`** | **SÍ** | **NO** | **SÍ** | `transiciones.py:293` |
| **`completada_campo`** | ya lo tiene | **NO** | **SÍ** | viene de `en_sitio` |
| **`correccion_requerida`** | ya lo tiene | **PENDIENTE** | **PENDIENTE** | ver §4.1 |
| **`cerrada`** | — | **NO APLICA** | no | terminal: `TRANSICIONES_PERMITIDAS[cerrada] = set()` |
| **`cancelada`** | — | **NO APLICA** | no | terminal |

**[MEDIDO]** El hallazgo que resuelve la ambigüedad del enunciado: la decisión
aprobada nombra *"en_sitio, ejecutándose, completada, cerrada"* y no menciona
`en_camino`. **El código lo resuelve:** `en_camino` escribe `iniciada_en`, luego
**ya inició**. No hizo falta interpretarlo.

### 4.1 `correccion_requerida` — el borde que la decisión no cubre

**[PENDIENTE]**

**[MEDIDO]** Los hechos:

| | |
|---|---|
| `iniciada_en` | **ya está escrito** (viene de `completada_campo`) |
| `vuelta` | **se incrementó**: es una presentación nueva a validación |
| transiciones de salida | `en_camino`, `en_sitio`, `cancelada` — **el trabajo se rehace** |
| marcador de "esta vuelta empezó" | **NO EXISTE.** `iniciada_en` se escribe **una sola vez** (`and not orden.iniciada_en`) |

> **La tensión, dicha entera:** por el criterio medido (R-2) la OT **ya inició**, y
> le toca contingencia. Pero operativamente es **el caso que más necesita una
> fecha nueva**: el supervisor devolvió el trabajo y hay que volver a mandar a
> alguien. Aplicarle contingencia significa que **un trabajo devuelto nunca puede
> recibir una fecha nueva**, y aplicarle la ruta normal contradice R-2.
>
> El modelo **no puede distinguir** "la vuelta 2 no ha empezado" con los campos
> que tiene: `iniciada_en` es de la primera vuelta y no se reescribe.

**No se decide aquí.** Las tres salidas, sin elegir:

| | Salida | Coste |
|---|---|---|
| **G1** | contingencia, como cualquier iniciada | un trabajo devuelto se queda sin fecha nueva |
| **G2** | ruta normal, excepción explícita a R-2 | rompe el ancla en `iniciada_en`, que es lo que hacía la regla robusta |
| **G3** | ruta normal **solo si `vuelta > 1` y no ha vuelto a salir** | necesita un campo nuevo → migración → fuera de M03-D1 |

---

## 5. Matriz de escenarios

| # | Escenario | Ruta | Línea anterior | Línea nueva | Novedad | Traza |
|:--:|---|---|---|---|---|---|
| **1** | plan **borrador**, **misma semana** | normal | actualizar `dia` in situ | — (la constraint impide 2ª) | opcional | `EventoTrabajo` |
| **2** | plan **borrador**, **otra semana** | normal | marcar `reprogramada` | en el plan destino | opcional | `EventoTrabajo` |
| **3** | plan **publicado**, **misma semana** | **formal** | actualizar `dia` in situ | — | **PENDIENTE** (§9) | `EventoTrabajo` + 7 datos |
| **4** | plan **publicado**, **otra semana** | **formal** | marcar `reprogramada` | en el plan destino | **PENDIENTE** | `EventoTrabajo` + 7 datos |
| **5** | ya existe línea en el **plan destino** | **rechazar** | — | — | — | — |
| **6** | **OT iniciada** (cualquier plan) | **contingencia** | **no se toca** | **no se crea** | **obligatoria** | `NovedadOperativa` + `EventoTrabajo` |
| **7** | OT `cerrada` / `cancelada` | **rechazar** | — | — | — | — |

### El detalle estructural del escenario 1 y 3 (§6 del encargo)

**[MEDIDO]** `unique(programacion, orden)`: **dentro de un plan, una orden tiene
una sola línea.** Mover una OT a otro día de la **misma** semana **no puede**
conservar la línea anterior como fila: hay que actualizarla.

> **Consecuencia que R-8 y R-9 salvan:** el historial de un cambio intra-semana
> **no puede vivir en `ProgramacionOrden`**. Vive en `EventoTrabajo`, que guarda el
> `dia` anterior y el nuevo. **La regla "no se sobrescribe silenciosamente" se
> cumple igual — lo que no se sobrescribe es el registro, no la fila.**

### El escenario 5 (§7 del encargo)

**[MEDIDO]** Si la OT ya tiene línea en el plan destino, `unique(programacion,
orden)` la rechaza en la base.
**[DISEÑO]** El servicio debe detectarlo antes y responder un conflicto legible,
no un `IntegrityError` — mismo criterio que M03-B con sus dos constraints.

### 5.1 El borde que la decisión aprobada NO cubre

**[PENDIENTE — P-4b]**

La lista de trazabilidad aprobada exige *"fecha/hora **anterior**"*. Eso presupone
que **ya había** una programación.

**[MEDIDO]** Pero hoy M03-B permite **agregar una línea nueva** a un plan ya
publicado (`ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS` incluye `PUBLICADA`). Ese caso:

- **es** una modificación posterior a la publicación — el plan que vieron las
  cuadrillas cambió;
- **no tiene** "fecha anterior", así que la trazabilidad aprobada no le encaja.

| | Alternativa | Implicación |
|---|---|---|
| **P4b-1** | agregar a un publicado **también** es reprogramación formal | M03-B debe restringirse a `borrador` → cambia M03-B |
| **P4b-2** | agregar es **programar**, no reprogramar; basta el `EventoTrabajo` que M03-B ya escribe | el plan publicado cambia con menos ceremonia que una reprogramación |

**No se elige.** Se deja medido que **hoy rige P4b-2 de hecho**, sin que nadie lo
haya decidido.

---

## 6. Flujo funcional propuesto

```
                        ¿iniciada_en IS NULL?
                          /              \
                        SÍ                NO
                        │                  │
              ┌─────────┴────────┐    ┌────┴─────────────────┐
              │  RUTA NORMAL     │    │  RUTA DE CONTINGENCIA│
              └─────────┬────────┘    └────┬─────────────────┘
                        │                  │
   1 validar org (request.org, nunca del cliente)
   2 lock select_for_update sobre la OT
   3 releer estado y programada_para     │
   4 ¿estado terminal? → rechazar        │
   5 ¿hay programación previa?           │   registrar NovedadOperativa
       no → esto es PROGRAMAR (M03-B)    │     tipo = la causa
   6 ¿plan destino admite líneas?        │     descripcion = motivo
   7 ¿fecha dentro de la semana destino? │     registrada_por = actor
   8 ¿ya hay línea en el destino? →      │     orden = la OT
       rechazar (escenario 5)            │
                        │                │   EventoTrabajo tipo="contingencia"
   9 ESCRIBIR HISTORIAL  ← R-8           │
  10 marcar línea anterior 'reprogramada'│   NO tocar programada_para
  11 crear/actualizar línea destino      │   NO tocar la línea
  12 programada_para = nueva; revision+=1│   NO tocar estado_operativo
  13 EventoTrabajo tipo="reprogramacion" │
  14 NovedadOperativa si hay causa       │
                        │                │
                   una sola transacción  │  una sola transacción
```

**[DISEÑO]** El paso 5 marca la frontera con M03-B: **si no había programación,
esto no es reprogramar.** Reprogramar exige que existiera un *cuándo*.

---

## 7. Trazabilidad requerida

Los siete datos que P-4 exige, y dónde cabe cada uno **sin migración**:

| # | Dato exigido | Superficie | ¿Cabe hoy? |
|:--:|---|---|:--:|
| 1 | qué estaba programado originalmente | `EventoTrabajo.datos` | **sí** |
| 2 | qué cambió | `EventoTrabajo.datos` | **sí** |
| 3 | fecha/hora anterior | `EventoTrabajo.datos` **+** `NovedadOperativa.programada_anterior` | **sí** |
| 4 | fecha/hora nueva | `EventoTrabajo.datos` **+** `NovedadOperativa.programada_nueva` | **sí** |
| 5 | motivo | `NovedadOperativa.tipo` + `descripcion`; copia en `datos` | **sí** |
| 6 | quién | `EventoTrabajo.profile` **+** `NovedadOperativa.registrada_por` | **sí** |
| 7 | cuándo | `created_at` de ambas | **sí** |
| 8 | **referencia al contexto operativo** | `EventoTrabajo.datos` (id de la novedad y/o de la `PropuestaSupervisor`) | **sí, sin integridad referencial** |

### La superficie correcta, y por qué

**[MEDIDO]** `EventoTrabajo.tipo` es `CharField(max_length=64)` **sin `choices`**
— por eso M03-B pudo escribir `tipo="programacion"` sin migración. Y `datos` es
`JSONField`.

> **`EventoTrabajo` es la única superficie que admite una reprogramación completa
> —incluido el cambio de plan— sin tocar el esquema.** Es además donde ya vive
> `reasignacion`, con exactamente la misma forma (`{anterior, nuevo, motivo}`).

**[MEDIDO]** `NovedadOperativa` es la que el modelo **declara** para esto (*"Lo
que obligó a cambiar el plan. Es lo que hace auditable una reprogramación"*) y le
falta el plan: **no tiene FK a `ProgramacionSemanal` ni a `ProgramacionOrden`.**

**[GAP]** `common.Activity` **no se puede usar**: sus `ENTITY_TYPE_CHOICES` tienen
`ActividadOperativa` y `PropuestaSupervisor` y **ninguna entidad de M03**.
Declarar una es una migración. *Medido además en producción: las 592 filas de
`Activity` son `Case` (564) y `Lead` (28) — ninguna de operaciones.*

**[GAP]** El dato 8 se puede guardar como UUID dentro de `datos`, pero **sin FK**:
`PropuestaSupervisor` referencia su origen con `origen_tipo` (texto) + `origen_id`
(CharField 128), y nada referencia a una propuesta. La traza existe; la integridad
referencial, no.

---

## 8. Actor y responsable

### Lo que existe

**[MEDIDO]** Precedente **unánime** en las cuatro operaciones comparables:

| Operación | Permiso | Evidencia |
|---|---|---|
| crear / asignar / validar | `ROLES_GESTION` | `campo/permissions.py:9`, `despacho_views.py::_exigir_gestion` |
| **programar** (M03-B) | el mismo | `despacho_views.py::ProgramarTrabajoView` |
| **publicar** (M03-C) | el mismo, vía `EsJefeDeOperaciones` | `operaciones/permissions.py` |
| registrar disponibilidad (A-3.3) | el mismo | `operaciones/views.py::DisponibilidadView` |

```
ROLES_GESTION = {"ADMIN", "SUPERVISOR", "OPERACIONES"}
```

**[DISEÑO]** **Reprogramar con el mismo conjunto es lo coherente**, y es lo que se
recomienda. **0 roles nuevos.**

### Solicitar / ejecutar / autorizar (§11 del encargo)

**[MEDIDO]** El sistema **no tiene hoy ninguna separación** entre pedir y aprobar
para estas operaciones. La única máquina de aprobación que existe es
`supervisor.revisar` de M09 — y opera sobre **propuestas de la IA**, no sobre
acciones humanas.

**[PENDIENTE]** Si el negocio quiere que una reprogramación sobre un plan
**publicado** requiera autorización de un rol distinto al que la solicita, eso es
maquinaria nueva (estado "solicitada", segundo actor, transición de aprobación).
**No existe y no se diseña aquí.**

**[DISEÑO]** Mientras tanto, hay **un solo acto** —ejecutar— y **un solo actor**,
que queda registrado dos veces: `EventoTrabajo.profile` y
`NovedadOperativa.registrada_por`.

### La decisión que esto arrastra

**[PENDIENTE — D-6]** Adoptar `ROLES_GESTION` **resuelve por defecto** la pregunta
*"¿quién programa?"* abierta desde M03-A. Es una decisión, no una deducción — se
señala en vez de darse por hecha.

---

## 9. Motivos de reprogramación

Clasificados como pide el encargo: **A** existentes, **B** derivados, **C** por
decidir.

### A — Existen y están documentados

**[MEDIDO]** `NovedadOperativa.TIPOS`, catálogo **cerrado** de 8 valores:

| Valor | Naturaleza |
|---|---|
| `ausencia` | **causa** |
| `bloqueo` | **causa** |
| `falta_material` | **causa** |
| `dependencia` | **causa** |
| `cambio_de_prioridad` | **causa** |
| `dato_incompleto` | **causa** |
| `demora_sin_causa_registrada` | **ausencia de causa conocida** |
| `reprogramacion` | **EFECTO** |

**[MEDIDO]** Y su propio modelo documenta por qué falta una:

> *"No existe `incumplimiento_de_persona`, y su ausencia es deliberada. […] el
> costo de equivocarse lo paga una persona real."*

### B — Derivados razonablemente del modelo

**[DISEÑO]** Las **seis causas** sirven directamente como motivo de una
reprogramación: son exactamente los hechos que obligan a mover trabajo. No hace
falta inventar ninguno.

### C — Requieren decisión empresarial

**[PENDIENTE]**

1. **El catálogo mezcla causa y efecto.** Una sola fila **no puede decir "se
   reprogramó porque el técnico estaba ausente"**: `tipo` es un campo único y el
   catálogo es cerrado. Tres salidas, sin elegir:

   | | Salida | Coste |
   |---|---|---|
   | **N1** | dos filas: causa + `reprogramacion` | duplica; **nada las relaciona** (no hay FK entre novedades) |
   | **N2** | una fila con la **causa**, y el antes/después en `programada_anterior/nueva` | `reprogramacion` queda para siempre sin uso |
   | **N3** | una fila `reprogramacion` con la causa en `descripcion` | la causa deja de ser agrupable |

2. **¿Falta algún motivo?** Casos plausibles que el catálogo no cubre —el cliente
   pide otro día, clima, acceso denegado— **no se agregan**: el catálogo es cerrado
   y ampliarlo es una migración **y** una decisión.

3. **¿El motivo es obligatorio?** *(ver §11, GAP-4.)*

**No se inventó ningún motivo** para completar el diseño.

---

## 10. Relación con las estructuras existentes (§12, §13)

| Estructura | Papel en una reprogramación |
|---|---|
| `ProgramacionSemanal` | contenedor. **[MEDIDO]** sin máquina de transiciones; solo M03-C restringe `borrador → publicada` |
| `ProgramacionOrden` | la línea. Se actualiza (misma semana) o se marca `reprogramada` + nueva (otra semana) |
| `OrdenTrabajo.programada_para` | el *cuándo* vigente. **Solo la ruta normal lo toca** |
| `NovedadOperativa` | la **causa**. Guarda fecha antes/después, actor, timestamp. **No el plan** |
| `EventoTrabajo` | el **hecho técnico**, completo, sin migración |
| `Activity` | **no utilizable** — `ENTITY_TYPE_CHOICES` sin entidades M03 |

### §13 — ¿OT ↔ Case?

**[MEDIDO]** **No existe FK.** `campo/models.py` no importa ni referencia `Case`.

**[MEDIDO]** Existe un **vínculo blando por texto**, que el código sí sabe
escribir (`despacho_views.py:137-139`):

```python
origen_sistema = "crm" if case_id else "manual"
origen_tipo    = "case" if case_id else ""
origen_ref     = case_id
```

**[MEDIDO]** Pero en producción **ninguna** de las 3 órdenes lo usa: las tres son
`wisphub` / `ticket` / `WH-…`.

> **Son estructuras independientes con un puente de texto opcional, hoy sin usar.**

---

## 11. Impacto sobre el SLA (§14)

**[MEDIDO]** El motor, `cases/models.py:454`:

```python
deadline = add_business_hours(self.created_at, hours, self._sla_calendar())
deadline = deadline + timedelta(seconds=paused)
```

| Pregunta | Respuesta medida |
|---|---|
| ¿Qué fecha ancla el SLA? | **`Case.created_at`**, caminada en horas hábiles, más el tiempo en `Pending` |
| ¿Lee `programada_para`? | **No.** No aparece en el motor |
| ¿La OT sabe a qué Case pertenece? | **No** — sin FK (§10) |

**[DECISIÓN APROBADA — declarada expresamente]**

> **Una reprogramación NO extiende, NO reinicia y NO altera el SLA.**
> No se crea ningún motor nuevo; se usa el existente, que simplemente **no
> depende** de la fecha programada.

**[PENDIENTE]** No existe ninguna regla documentada que diga lo contrario, y **no
se inventa**.

**[RIESGO]** El riesgo real es el inverso y conviene dejarlo escrito: **como el
reloj no se mueve, reprogramar repetidamente consume presupuesto de SLA sin que
nada avise.** Hoy nadie lo vería, porque la orden ni siquiera sabe a qué caso
pertenece. Si el negocio quiere una alerta, es una regla nueva → **decisión.**

---

## 12. Reglas adicionales contra los cinco riesgos (§15)

| Riesgo | Regla | Mecanismo existente |
|---|---|---|
| **dos programaciones vigentes** | R-6 + R-7: marcar la anterior en la misma transacción | `select_for_update` + estado `reprogramada` |
| **pérdida de historial** | R-8: historial **antes** de mover la fecha | `transaction.atomic` |
| **inconsistencia línea ↔ `programada_para`** | R-4 + R-5: una transacción, una conversión | el patrón de M03-B, y `revisar_coherencia` de M03-C ya sabe detectarlo |
| **reprogramación silenciosa** | R-9 + R-10: sin `EventoTrabajo` no hay reprogramación | `EventoTrabajo` obligatorio |
| **reprogramar una OT iniciada** | R-1 + R-2 + R-12: la frontera es `iniciada_en` | `transiciones.py:293` |

**[DISEÑO]** Una regla más, que sale de M03-C: **`revisar_coherencia` podría
extenderse con la invariante "una sola línea vigente por orden"**, de modo que
publicar un plan comprobara además que ninguna reprogramación dejó dos.

---

## 13. Dependencias

| Con | Qué |
|---|---|
| **M09** | **[DEPENDENCIA]** H-05 reemite por huella al cambiar la fecha — *"otra fecha comprometida → la huella cambia y la propuesta nueva SÍ se crea"* (`_ya_propuesta`). **Es la conducta declarada, no un defecto.** `orden_sin_programar` y `dato_incompleto` dan falsos positivos si la operación no es atómica → R-4 los evita |
| **M03-E** (secuencia) | **[DEPENDENCIA]** reprogramar cambia el día: la `secuencia` del día origen y la del destino quedan con huecos. M03-E tendrá que decidir si se recompacta |
| **M03-F** (cuadrillas) | **[DEPENDENCIA]** ninguna hoy: reprogramar no toca `AsignacionTrabajo` (R-1 separa *cuándo* de *quién*) |
| **M03-G** (capacidad) | **[DEPENDENCIA]** mover una OT a otro día cambia la carga de los dos días. **Sin capacidad no hay nada que recalcular** — y M03-A midió que no existe un solo dato para hacerlo |
| **B-7** | **[RIESGO]** una reprogramación escribe en `campo_orden_trabajo` y `campo_evento_trabajo` (**sin RLS**, 0 políticas) y en `operaciones_*` (con RLS). **B-7 no cierra ese hueco**: la causa es `ORG_SCOPED_TABLES`, que no lista ninguna `campo_*` |

---

## 14. GAPs que requieren decisión empresarial

| # | GAP | Tipo |
|:--:|---|---|
| **GAP-1** | **`correccion_requerida`**: por el criterio medido ya inició, pero es el caso que más necesita fecha nueva. El modelo no distingue "esta vuelta no ha empezado" | **decisión** (§4.1) |
| **GAP-2** | **P-4b**: agregar una línea **nueva** a un plan publicado — es modificación posterior, pero no tiene "fecha anterior" | **decisión** (§5.1) |
| **GAP-3** | El catálogo de `NovedadOperativa` **mezcla causa y efecto**: N1 / N2 / N3 | **decisión** (§9) |
| **GAP-4** | **¿El motivo es obligatorio** en una reprogramación de plan publicado? P-4 lo exige en la lista, pero no dice si el sistema debe rechazar sin él | **decisión** |
| **GAP-5** | **¿Solicitar y autorizar son actos distintos** para un plan publicado? Hoy no existe la separación | **decisión** |
| **GAP-6** | **SLA consumido en silencio** por reprogramaciones repetidas: ¿debe avisar? | **decisión** |
| **GAP-7** | `NovedadOperativa` **sin FK a plan** → la novedad no puede decir a qué plan se movió | **técnico (migración)** |
| **GAP-8** | `Activity.ENTITY_TYPE_CHOICES` **sin entidades M03** | **técnico (migración)** |
| **GAP-9** | La **referencia al contexto operativo** (dato 8) se guarda como UUID suelto, sin integridad referencial | **técnico** |
| **GAP-10** | **`campo_*` sin RLS** — B-7 no lo resuelve | **seguridad** |

---

## 15. Alcance recomendado para M03-D2

**[DISEÑO]** M03-D2 puede cerrarse **solo** sobre lo que quedó DEFINIDO:

### Dentro de alcance

1. **Ruta normal**, exclusivamente sobre `estado_operativo = asignada`.
2. **Escenarios 1 y 2** (plan borrador, misma semana y otra semana).
3. **Escenarios 3 y 4** (plan publicado) **con los 7 datos de trazabilidad**.
4. **Escenario 5**: rechazo legible si ya hay línea en el destino.
5. **Escenario 7**: rechazo para `cerrada` / `cancelada`.
6. Historial en **`EventoTrabajo`** `tipo="reprogramacion"`, escrito **antes** de
   mover la fecha.
7. `select_for_update` + una transacción + `localtime()`.
8. Permiso: **`ROLES_GESTION`**, 0 roles nuevos.

### Fuera de alcance hasta que se decida

| | Bloqueado por |
|---|---|
| `correccion_requerida` | GAP-1 |
| agregar líneas a un plan publicado | GAP-2 |
| forma exacta de la `NovedadOperativa` | GAP-3, GAP-4 |
| autorización separada | GAP-5 |
| **ruta de contingencia completa** | GAP-3 — necesita saber qué novedad escribir |

> **[DISEÑO] Recomendación de orden:** implementar **primero la ruta normal**
> (escenarios 1–5 y 7), que no depende de ningún GAP abierto, y dejar la
> contingencia para cuando GAP-1 y GAP-3 estén resueltos.
>
> **[RIESGO] Con una advertencia honesta:** las 3 órdenes de producción están las
> tres iniciadas, así que **la ruta normal no tendría hoy ni un caso real que
> ejercitar** y la contingencia sería la que aplicaría a todo lo existente.
> Implementar primero lo que no bloquea sigue siendo lo correcto, pero **el valor
> operativo inmediato está del otro lado.**

---

## 16. Evidencia del repositorio utilizada

| Decisión | Evidencia | Tipo |
|---|---|---|
| frontera de "ya inició" | `campo/services/transiciones.py:293` | **[MEDIDO]** |
| `asignada` = no inició | `operaciones/supervisor.py:341` | **[MEDIDO]** |
| estados terminales | `transiciones.py:19` (`TRANSICIONES_PERMITIDAS`) | **[MEDIDO]** |
| una línea por plan | `unique(programacion, orden)`, `operaciones/models.py:459` | **[MEDIDO]** |
| `reprogramada` sin escritor | grep: solo `PLANIFICADA` se escribe (`programacion.py:222`) | **[MEDIDO]** |
| dos vigentes → M09 lee la obsoleta | `supervisor._programacion_vigente` + `Meta.ordering` | **[MEDIDO]** |
| `EventoTrabajo.tipo` sin catálogo | `campo/models.py:387` | **[MEDIDO]** |
| `Activity` no utilizable | `common/models.py:672` (`ENTITY_TYPE_CHOICES`) | **[MEDIDO]** |
| `Novedad` sin FK a plan | `operaciones/models.py:469-540` | **[MEDIDO]** |
| catálogo de 8 motivos | `NovedadOperativa.TIPOS` | **[MEDIDO]** |
| SLA ancla en `created_at` | `cases/models.py:454` | **[MEDIDO]** |
| sin FK OT ↔ Case | `campo/models.py` (no importa `Case`) | **[MEDIDO]** |
| vínculo blando por texto | `campo/despacho_views.py:137-139` | **[MEDIDO]** |
| permiso por precedente | `campo/permissions.py:9` + las 4 operaciones | **[MEDIDO]** |
| borrador no compromete | `supervisor.py:630` | **[MEDIDO]** |
| H-05 reemite por huella | `supervisor._ya_propuesta` | **[MEDIDO]** |
| `campo_*` sin RLS | `pg_class` en producción + `common/rls/__init__.py:34` | **[MEDIDO]** |
| datos de producción | `SELECT` con `read_only = True` | **[MEDIDO]** |

---

## CIERRE

### DEFINIDO

- **R-1 … R-12**: las doce reglas del §3.
- **La frontera de "ya inició"**, anclada en `iniciada_en` y no en una lista.
- **`en_camino` es una OT iniciada** — resuelto por medición.
- **La matriz de estados** completa salvo `correccion_requerida`.
- **Los escenarios 1, 2, 3, 4, 5, 6 y 7** de la matriz.
- **La superficie de trazabilidad**: `EventoTrabajo` como canónica, `NovedadOperativa` para la causa, `Activity` descartada con evidencia.
- **El actor**: `ROLES_GESTION`, 0 roles nuevos.
- **El SLA**: reprogramar **no** lo toca. Declarado expresamente.
- **OT ↔ Case**: independientes, con puente de texto opcional hoy sin usar.

### PENDIENTE

**Decisión empresarial:** GAP-1 (`correccion_requerida`) · GAP-2 (P-4b) ·
GAP-3 (causa vs. efecto) · GAP-4 (motivo obligatorio) · GAP-5 (autorización
separada) · GAP-6 (SLA silencioso) · D-6 (quién programa).

**Técnico, requiere migración:** GAP-7 (FK a plan en `Novedad`) · GAP-8
(`Activity`) · GAP-9 (integridad del contexto) · GAP-10 (RLS de `campo_*`).

### IMPLEMENTABLE EN M03-D2

La **ruta normal** completa: escenarios 1–5 y 7, sobre `asignada`, con
`EventoTrabajo` como historial, una transacción, `select_for_update` y
`ROLES_GESTION`. **No depende de ningún GAP abierto.**

### REQUIERE DECISIÓN ANTES DE IMPLEMENTAR

La **ruta de contingencia** (GAP-1, GAP-3), la modificación de planes publicados
por adición (GAP-2), y la obligatoriedad del motivo (GAP-4).

---

```
código ......... 0     migraciones ... 0     modelos ....... 0
endpoints ...... 0     permisos ...... 0     tablas ........ 0
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
