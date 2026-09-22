# Paso M09-C — Diseño funcional del Supervisor NOC IA (Shadow Mode)

**Fecha:** 17/09/2026 · **Sin código, sin migraciones, sin despliegue.**
Producción intacta: ledger 50 · kill switch **DETENIDO** · 0 filas `activo` ·
`DBUSER` sin cambios · cero llamadas externas.

> Todo lo que este documento afirma sobre el repositorio y sobre los datos está
> **medido**, no supuesto. Donde no hay datos, lo dice.

---

## 0. Punto de partida: qué existe ya

`PropuestaSupervisor` **ya está en el repositorio** (`operaciones/models.py`,
tabla `operaciones_propuesta_supervisor`), con 8 señales, 6 estados, 5 niveles
de autonomía y una restricción que exige evidencia. Este paso **no la
rediseña**: la valida, cierra lo que quedaba ambiguo y marca los huecos.

### Los datos de producción, hoy

| Tabla | Filas | Qué implica |
|---|---|---|
| `case` | **197** (116 New · 69 Closed · 12 Assigned) | hay materia para señales de caso |
| `activity` | **586** | historial poblado |
| `campo_orden_trabajo` | **3** | 2 `en_sitio`, 1 `completada_campo` |
| `campo_asignacion_trabajo` / `evento` / `evidencia` | 3 / 12 / 5 | el flujo de campo se usó |
| `solicitudes_solicitudservicio` | 5 | |
| `campo_work_type_version` | 1 | |
| **`operaciones_actividad`** (M02) | **0** | esquema sí, datos no |
| **`operaciones_disponibilidad`** (M03) | **0** | ídem |
| **`operaciones_programacion_semanal`** | **0** | ídem |
| **`operaciones_programacion_orden`** | **0** | ídem |
| **`operaciones_novedad`** (M05) | **0** | ídem |
| **`operaciones_propuesta_supervisor`** (M09) | **0** | nunca se escribió |

Hay que distinguir tres cosas que no son lo mismo:

- **sin esquema** — no se puede calcular de ninguna manera;
- **con esquema y sin datos** — se calcula perfectamente y da cero;
- **con datos** — se calcula y dispararía.

**Ninguna señal está en el primer grupo.** Cinco de ocho están en el segundo.

### El campo que queda fuera por decisión, y por medición

`case.first_response_at`: **4 de 197 poblados (2 %)**. Su ausencia no prueba
nada, así que **no se usa para determinar incumplimiento de SLA**. Coincide con
lo que el propio modelo ya documenta y con la regla de este paso.
`sla_paused_at`: **0 de 197**.

---

## 1. Inventario de señales

`⚠️` = calculable pero **sin datos de origen hoy**.
Ninguna señal infiere causa, culpa ni responsable.

### A · Caso

**S-A1 · `caso_abierto_antiguo`**
- Origen · modelo: `cases.Case` (`public.case`)
- Condición objetiva: `status` ∉ (Closed, Rejected, Duplicate) **y**
  `created_at < now() − N días`, con N de configuración
- Evidencia mínima: `case.id`, `status`, `created_at`, `now()`, días transcurridos
- Antigüedad: es el eje de la señal
- Propuesta: revisar el caso · **M01** · nivel **1** · revisa humano
- **No puede inferir:** por qué sigue abierto, de quién es la demora, si está
  bloqueado. «Antiguo» es una medición; «atrasado» sería un juicio.

**S-A2 · `caso_en_riesgo_sla`** — *ver §10*
- Origen: **propiedad calculada** `Case.is_sla_resolution_breached` /
  `resolution_sla_deadline` (`cases/models.py:485-503`), que usa horas hábiles
- Condición: la propiedad de M04 dice que sí. **M09 la lee; no la recalcula.**
- Datos: `sla_resolution_hours` **197/197 poblados**; `resolved_at` 69/197
- Propuesta: priorizar · **M04** · nivel **1**
- **No puede inferir:** de quién es la responsabilidad del retraso.

### B · Actividad

**S-B1 · `actividad_vencida` ⚠️**
- `operaciones.ActividadOperativa`: `vence_en < now()` **y**
  `estado_operativo` ∉ (`completada`, `cancelada`)
- Evidencia: `id`, `titulo`, `vence_en`, `estado_operativo`, `now()`
- Propuesta: retomar o reprogramar · **M02** · nivel **1**
- **No puede inferir:** la causa del vencimiento — salvo que exista una
  `NovedadOperativa` asociada, y entonces la causa **se lee**, no se deduce.

**S-B2 · `actividad_sin_responsable` ⚠️**
- `responsable IS NULL` **y** `estado_operativo` ∉ (`completada`, `cancelada`)
- Propuesta: asignar responsable · **M02/M03** · nivel **1**
- **No puede inferir:** a quién asignársela.

**S-B3 · `actividad_bloqueada` ⚠️**
- `estado_operativo = 'bloqueada'`; `motivo_bloqueo` es **dato declarado**
- Propuesta: escalar el bloqueo · **M05** · nivel **1**
- **No puede inferir:** si el bloqueo sigue vigente ni si es atribuible.

**S-B4 · `compromiso_por_vencer` ⚠️**
- `tipo = 'compromiso'` **y** `vence_en` dentro de la ventana **y** no completada
- Propuesta: avisar antes del vencimiento · **M02** · nivel **1**

### C · Compromiso
Cubierto por **S-B4**: `ActividadOperativa` es una sola tabla con nueve tipos, y
`compromiso` es uno de ellos. **No se crea una entidad nueva.**

### D · Dependencia

**S-D1 · `dependencia_pendiente` ⚠️**
- `depende_de` apunta a una actividad que **no** está `completada`, y la
  dependiente no está `completada`/`cancelada`
- Evidencia: las dos actividades, sus estados, la arista
- Propuesta: resolver primero la dependencia · **M02** · nivel **1**

### E · Orden de trabajo

**S-E1 · `orden_sin_programar`** — **la señal del ejemplo, y hay que corregirla**

> La condición que propone el enunciado —«OT existente + `programada_para`
> NULL»— **produciría hoy 3 propuestas falsas de 3**. Medido:
>
> ```
> OT-1842  en_sitio          programada_para=None  iniciada_en=sí
> OT-1843  en_sitio          programada_para=None  iniciada_en=sí
> OT-1844  completada_campo  programada_para=None  iniciada_en=sí  completada=sí
> ```
>
> **`programada_para` está vacío en el 100 % de las OT, y las tres ya
> arrancaron.** El campo no está en uso; su NULL no significa «falta
> programarla», significa «nadie usa ese campo todavía». Recomendar «programar»
> una OT ya completada es exactamente la propuesta inventada que las reglas
> prohíben.

- Condición corregida: `estado_operativo = 'asignada'` **y** `iniciada_en IS
  NULL` **y** `programada_para IS NULL` **y** no existe `ProgramacionOrden` para
  esa OT
- Evidencia: `numero`, `estado_operativo`, `programada_para`, `iniciada_en`,
  ausencia de fila en `operaciones_programacion_orden`
- Propuesta: programar · **M03** · nivel **1**
- **Resultado hoy: 0 señales.** Es el resultado correcto.
- **No puede inferir:** que esté atrasada. Sin fecha comprometida no hay atraso
  que demostrar.

**S-E2 · `orden_con_riesgo_operacional`**
- Condición: OT en `en_sitio` **y** `iniciada_en < now() − N horas` **y**
  `completada_campo_en IS NULL`
- Evidencia: `numero`, estado, `iniciada_en`, horas transcurridas
- Propuesta: verificar el estado en sitio · **M03/M05** · nivel **1**
- **No puede inferir:** que el técnico esté incumpliendo. Una visita larga puede
  ser un trabajo difícil.

### F · Programación
**S-F1 · `programacion_sin_publicar` ⚠️** — `ProgramacionSemanal.estado` ≠
publicada y la semana ya empezó · **M03** · nivel **1**.

### G · Incidencia / bloqueo
Se **leen** de `NovedadOperativa`, cuyos 8 tipos coinciden exactamente con las
causas cerradas autorizadas: `ausencia`, `bloqueo`, `falta_material`,
`dependencia`, `reprogramacion`, `cambio_de_prioridad`, `dato_incompleto`,
`demora_sin_causa_registrada`. **M09 no inventa causas: las cita.**

### H · Capacidad / disponibilidad
**NO DISPONIBLE ACTUALMENTE.** `operaciones_disponibilidad` tiene **0 filas**.
Sin disponibilidad declarada no hay sobrecarga que medir, y deducirla del
número de asignaciones sería inventar una capacidad que nadie declaró.

### I · Riesgo operativo
Derivado de S-A2, S-E2 y S-D1. **No hay un «score de riesgo» propio**: sería un
número sin respaldo.

### J · Integración / dato inconsistente
**S-J1 · `dato_incompleto`** — señal **informativa (nivel 0)**, no propuesta:
una OT sin `tipo_trabajo_version`, un caso sin organización, una actividad con
`origen_id` que no resuelve. No recomienda nada; deja constancia.

---

## 2. Matriz señal → propuesta

| Señal | Evidencia | Interpretación permitida | Propuesta | Módulo | Prioridad | Impacto | Autonomía | Revisor | Resultado |
|---|---|---|---|---|---|---|---|---|---|
| `caso_abierto_antiguo` | id, status, created_at, días | «lleva N días abierto» | revisar el caso | M01 | por antigüedad | cola que crece | 1 | Jefe de Op. | propuesta pendiente |
| `caso_en_riesgo_sla` | propiedad de M04 + horas | «M04 lo marca en riesgo» | priorizar | M04 | por deadline | compromiso con el cliente | 1 | Jefe de Op. | propuesta pendiente |
| `actividad_vencida` ⚠️ | id, vence_en, estado | «venció y sigue abierta» | retomar o reprogramar | M02 | por atraso | compromiso incumplido | 1 | Jefe de Op. | propuesta pendiente |
| `actividad_sin_responsable` ⚠️ | id, responsable NULL | «nadie la tiene» | asignar | M02/M03 | media | nadie la mira | 1 | Jefe de Op. | propuesta pendiente |
| `actividad_bloqueada` ⚠️ | id, motivo_bloqueo | «está declarada bloqueada» | escalar | M05 | alta | detenida | 1 | Jefe de Op. | propuesta pendiente |
| `compromiso_por_vencer` ⚠️ | id, vence_en, ventana | «vence pronto» | avisar | M02 | por ventana | incumplir | 1 | Jefe de Op. | propuesta pendiente |
| `dependencia_pendiente` ⚠️ | ambas actividades | «depende de una abierta» | resolver la previa | M02 | por la bloqueante | cadena parada | 1 | Jefe de Op. | propuesta pendiente |
| `orden_sin_programar` | estado, prog NULL, sin fila M03 | «asignada y sin programar» | programar | **M03** | por antigüedad | sin fecha | 1 | Jefe de Op. | propuesta pendiente |
| `orden_con_riesgo_operacional` | numero, iniciada_en, horas | «lleva N h en sitio» | verificar estado | M03/M05 | por horas | visita larga | 1 | Jefe de Op. | propuesta pendiente |
| `dato_incompleto` | el campo que falta | «falta este dato» | — (informativa) | M10 | baja | no calculable | **0** | — | señal, no propuesta |

**Ninguna fila afirma que algo esté atrasado sin una fecha comprometida que lo
demuestre.**

---

## 3. Niveles de autonomía

| Nivel | Qué es | Puede la IA | NO puede | Evidencia | Quién autoriza |
|---|---|---|---|---|---|
| **0 · Observar** | informar | emitir señal, contar, mostrar | recomendar nada | el dato y su fuente | nadie: no cambia nada |
| **1 · Recomendar** | proponer | crear `PropuestaSupervisor` | ejecutar, notificar a terceros, cambiar estados | evidencia completa (§4) | Jefe de Operaciones al revisar |
| **2 · Coordinar** | *FUTURO — NO IMPLEMENTADO* | — | — | — | — |
| **3 · Ejecutar reversible** | *FUTURO — NO IMPLEMENTADO* | — | — | — | — |
| **4 · Acción crítica** | *FUTURO — NO IMPLEMENTADO* | — | — | — | — |

**En M09-C solo se permiten 0 y 1.** El modelo ya lo declara:
`NIVEL_MAXIMO_ETAPA = NIVEL_RECOMENDAR`.

### La IA no puede elevar su propio nivel

`nivel_autonomia_requerido` describe **qué nivel habría hecho falta** para
ejecutarla sola. Es una etiqueta descriptiva, no un permiso. Aunque una
propuesta se marque nivel 3, **no hay camino de ejecución**: el paso 10.14A puso
la frontera en el ejecutor y M09 **no abre permiso de ninguna de las dos
puertas**. El límite no es una promesa del diseño: es que el código para
ejecutar no existe, y si existiera, la frontera lo frenaría con el kill switch
detenido.

### Controles obligatorios antes de cualquier nivel ≥ 2 (futuro)

Autorización explícita por tipo de acción · kill switch consultado en cada
ejecución (ya existe) · idempotencia con origen estable (ya existe) · límite de
acciones por ventana · reversión definida y probada · auditoría con actor ·
revisión humana obligatoria en nivel 4.

---

## 4. Estándar de evidencia

Cada propuesta responde **siete preguntas**, y las cuatro capas **no se mezclan**:

| Capa | Qué es | Campo |
|---|---|---|
| **HECHO** | lo que ocurrió, sin adjetivos | dentro de `evidencia[]` |
| **EVIDENCIA** | el dato que lo demuestra, con su fuente | `evidencia[]` |
| **INTERPRETACIÓN** | qué significa, acotado a lo permitido | `motivo` |
| **PROPUESTA** | qué se recomienda hacer | `accion_propuesta` |

Forma de cada observación en `evidencia` (lista JSON; el modelo ya **prohíbe la
lista vacía** por restricción de base):

```json
{
  "fuente": "campo_orden_trabajo",      // ¿de qué tabla/modelo?
  "registro": "OT-1842",                 // ¿dónde?
  "campo": "iniciada_en",                // ¿qué dato?
  "valor": "2026-09-17T13:02:00Z",       // ¿qué dice?
  "observado_en": "2026-09-17T22:40:00Z",// ¿cuándo se leyó?
  "regla": "en_sitio > 6 h"              // ¿contra qué se comparó?
}
```

### Si falta evidencia

| Situación | Qué se hace |
|---|---|
| Falta un dato para **evaluar** la condición | **no se genera propuesta**; se emite señal `dato_incompleto` de **nivel 0** |
| La condición se cumple pero falta un dato **accesorio** | se genera la propuesta, y el faltante se anota como observación |
| El dato es **contradictorio** entre dos fuentes | **no se genera nada**; señal informativa (§11) |

**Nunca se rellena un hueco para completar la matriz.**

---

## 5. Duplicados

**Clave de deduplicación conceptual:**

```
(org_id, tipo_senal, origen_tipo, origen_id, ventana)
```

`ventana` es el período en que la misma situación se considera **la misma**; su
tamaño lo fija el tipo de señal (una OT sin programar: la semana; un caso
antiguo: el día).

| Situación | Decisión |
|---|---|
| Misma clave y hay una propuesta en `propuesta` | **reutilizar**: se actualiza la evidencia, no se crea otra |
| Misma clave, la anterior fue `rechazada` dentro de la ventana | **no crear**: rechazar es una decisión, repetir la pregunta es ruido |
| Misma clave, la anterior `expiró` | **crear nueva**, citando la anterior |
| Misma clave, la anterior fue `aceptada` y la condición **sigue** | **reabrir** con nueva evidencia: aceptar no ejecutó nada, y si el hecho persiste hay que decirlo |
| Cambia la ventana | **nueva propuesta** |
| Desaparece la condición | la pendiente pasa a `expirada` |

`expira_en` ya existe en el modelo. Una propuesta se considera **expirada**
cuando pasa esa fecha sin revisión, o cuando el origen se cierra.

---

## 6. Conflictos entre propuestas

Tres prioridades **distintas**, que no se mezclan:

| | Qué mide | Dónde vive |
|---|---|---|
| **Prioridad de la señal** | qué tan grave es lo detectado | regla de M09 |
| **Prioridad de la propuesta** | en qué orden conviene revisarla | `PropuestaSupervisor.prioridad` |
| **Prioridad del Case/OT** | la del negocio | M01 / M03 — **M09 no la toca** |

### Precedencia cuando varias señales caen sobre el mismo origen

Basada en evidencia operacional, no en juicio:

1. **`bloqueo declarado`** — hay una causa registrada por una persona. Gana:
   proponer programar algo bloqueado sería contradecir un dato declarado.
2. **`dependencia_pendiente`** — hay una arista explícita; actuar sobre la
   dependiente antes que sobre la bloqueante es inútil.
3. **`cambio_de_prioridad`** — decisión humana reciente; la respeta.
4. **`orden_sin_programar`** — hecho verificable y accionable.
5. **`actividad_vencida`** — hecho verificable, pero sin causa demostrada.

**Regla de silencio:** si (1) o (2) están presentes, las de abajo **no se
emiten** para ese origen — se citan como contexto dentro de la que sí se emite.
Emitir cinco propuestas sobre la misma OT convierte la bandeja en ruido y obliga
al revisor a deducir la precedencia que el sistema ya conocía.

---

## 7. Estados de `PropuestaSupervisor`

| Estado | Significa | Quién | Cuándo | Qué queda |
|---|---|---|---|---|
| `propuesta` | recién creada, sin revisar | M09 | al detectar | evidencia + motivo |
| `aceptada` | el Jefe está de acuerdo | Jefe de Op. | al revisar | `revisado_por`, `revisado_en`, `resultado` |
| `modificada` | de acuerdo con cambios | Jefe de Op. | al revisar | ídem + qué cambió |
| `rechazada` | no procede | Jefe de Op. | al revisar | ídem + por qué |
| `expirada` | perdió vigencia | M09 (automático) | pasó `expira_en` o el origen se cerró | marca de tiempo |
| `cancelada` | el origen desapareció o se creó por error | M09 o Jefe | cuando corresponda | motivo |

### Lo que más importa

> **ACEPTADA ≠ EJECUTADA. MODIFICADA ≠ EJECUTADA.**

Aceptar significa «estoy de acuerdo», no «se hizo». **En Shadow Mode no existe
ejecución automática**, y eso no es una promesa: el estado `ejecutada` **no
existe** en el modelo, y `accion_propuesta_ref` queda **siempre vacío**. La
ausencia es lo que lo vuelve comprobable.

**Después de aceptar / modificar:** la acción la realiza una persona en **M02 o
M03**, por sus caminos normales. M09 no la ejecuta ni la reclama.
**Después de rechazar:** no se vuelve a proponer lo mismo dentro de la ventana.

Transiciones válidas: `propuesta → {aceptada, modificada, rechazada, expirada,
cancelada}`. Un estado revisado **no vuelve** a `propuesta`; si la condición
reaparece se crea una nueva citando la anterior.

---

## 8. Human in the loop

```
M09 detecta (condición objetiva sobre datos existentes)
  ↓
arma evidencia (fuente, registro, campo, valor, hora, regla)
  ↓
¿evidencia suficiente?  --NO-->  señal 'dato_incompleto' (nivel 0). FIN.
  ↓ sí
¿duplicada en la ventana?  --SÍ-->  actualiza la existente. FIN.
  ↓ no
crea PropuestaSupervisor (estado 'propuesta')
  ↓
Jefe de Operaciones revisa
  ↓
acepta / modifica / rechaza  →  queda registrado quién, cuándo y por qué
  ↓
la acción, si procede, la hace una persona en M02/M03
  ↓
M09 NO ejecuta. Nunca.
```

### Qué tiene que ver el Jefe de Operaciones para decidir

1. **El hecho**, en una línea, sin adjetivos.
2. **La evidencia**, con la tabla y el campo de donde salió y la hora de lectura.
3. **Qué NO se sabe** — explícito. Sin esto, el silencio se lee como certeza.
4. La **propuesta** y el módulo que la ejecutaría.
5. El **origen**, con enlace al Case/OT/Actividad.
6. Si hay **causa declarada** (`NovedadOperativa`), citada tal cual.
7. Propuestas **relacionadas** sobre el mismo origen.
8. Qué pasa **si no se hace nada** — sólo si es calculable.

---

## 9. Relación con M02 y M03

| | Dueño de | M09 hace |
|---|---|---|
| **M02** | actividades, tareas, pendientes, compromisos, dependencias | **detecta** y recomienda; no crea ni cierra actividades |
| **M03** | programación, asignación, redistribución, reprogramación | **detecta** y recomienda; no programa ni asigna |
| **M09** | detección, análisis, recomendación | eso, y nada más |

**M09 no se vuelve dueño de procesos ajenos.** Detecta «OT sin programación»,
propone «programar OT», y **M03 es quien programa**. La lógica de programación
no se duplica en M09: M09 sólo comprueba **ausencia** de programación.

`common.Activity` sigue siendo **historial/ciclo de vida**, no agenda.
`tasks.Task` y `Board` quedan fuera. `asistente.acciones_propuestas` conserva su
histórico y **no** se reutiliza como cola del Supervisor.

---

## 10. Relación con M04 y M05

> **No se crea un segundo motor de SLA.**

La lógica de SLA **ya vive** en `cases/models.py:475-503`, como propiedades
calculadas (`is_sla_resolution_breached`, `resolution_sla_deadline`) que usan
horas hábiles. **M09 las lee.** Si el umbral cambia, cambia en un solo sitio.

| Lógica | Vive en | M09 |
|---|---|---|
| Cálculo de deadline y de incumplimiento | **M04** (`Case`, `business_hours`) | lee |
| Causas de bloqueo y su catálogo | **M05** (`NovedadOperativa`, 8 tipos) | cita |
| Escalamiento | **M05** | recomienda escalar |
| Prioridad del negocio | M01/M03 | no la toca |
| Detección + recomendación | **M09** | única responsabilidad |

Si M09 necesitara un umbral que M04 no expone, **lo correcto es agregarlo a
M04**, no calcularlo aparte.

---

## 11. Casos prohibidos — M09 **no** genera recomendación

1. **Evidencia insuficiente** para evaluar la condición.
2. **Causa no demostrada** — nunca deducir por qué algo se demoró.
3. **Responsable no verificable** — nunca nombrar a quién «le falló».
4. **Información contradictoria** entre fuentes.
5. **Tenant inexistente o no resuelto.**
6. **Estado inconsistente** (p. ej. OT `cerrada` con `cerrada_en` NULL).
7. **Datos incompletos** en el origen.
8. **Cualquier acción externa** — M09 no las propone como ejecutables ni abre
   permiso en la frontera.
9. **Inferir culpa.** `incumplimiento_de_persona` **permanece prohibido**, y no
   existe como tipo.
10. **Fuente no confiable** — nada que venga de texto libre del modelo.
11. **Duplicidad sin resolver** (§5).
12. **Demora sin causa registrada** → se nombra
    `demora_sin_causa_registrada`, que es un **hecho**; jamás
    «incumplimiento».

> **Demora ≠ incumplimiento de una persona.** Una demora es una medición de
> tiempo; un incumplimiento es un juicio sobre alguien. M09 mide.

---

## 12. Indicadores futuros (definición, sin dashboards)

| Indicador | Fórmula conceptual |
|---|---|
| Señales detectadas | `count(señales)` por tipo y período |
| Propuestas generadas | `count(PropuestaSupervisor)` por tipo |
| **Tasa de aceptación** | `aceptadas / (aceptadas+modificadas+rechazadas)` |
| Tasa de modificación | `modificadas / revisadas` — mide qué tan afinada está la recomendación |
| **Tasa de rechazo** | `rechazadas / revisadas` — **el indicador de calidad**: rechazo alto = ruido |
| Tasa de expiración | `expiradas / generadas` — mide si alguien las mira |
| Tiempo hasta revisión | `avg(revisado_en − created_at)` |
| Tiempo hasta resolución | `avg(cierre del origen − created_at)` — **sólo correlación, no causa** |
| Cobertura por módulo | propuestas por módulo destino |
| Precisión por señal | aceptación desagregada por `tipo_senal` |

> Ninguno de estos indicadores mide personas. Miden **al Supervisor**.

---

## 13. Seguridad y gobierno

| Control | Estado |
|---|---|
| Tenant isolation | `org` FK obligatorio; RLS del esquema `public` |
| RLS | 132 políticas en `public` (medido) |
| Revisor humano | Jefe de Operaciones — **ver el hueco en §15** |
| Actor | `revisado_por` + `revisado_en` |
| Auditoría | `evidencia[]` + `resultado` + `audit_log` |
| Kill switch | **DETENIDO**; M09 no lo consulta porque **no ejecuta** |
| Frontera externa | M09 **no abre permiso** en ninguna puerta |
| Idempotencia | no aplica: no hay mutación externa |
| No autoelevación | `nivel_autonomia_requerido` es descriptivo, no un permiso |

### «Puede recomendar» ≠ «puede ejecutar»

| | Recomendar | Ejecutar |
|---|---|---|
| Qué hace | escribe una fila en su propia tabla | produce un efecto en WispHub / SmartOLT / CRM |
| Quién decide | la IA propone, **el humano decide** | — |
| Control | evidencia obligatoria | kill switch + frontera + idempotencia |
| **En M09-C** | **sí** | **no, por ausencia de código** |

---

## 14. Matriz final de decisión

| ID | Señal | Evidencia mínima | Propuesta | Módulo | Auton. | Revisor | ¿Shadow Mode? | ¿Autónoma hoy? | Observaciones |
|---|---|---|---|---|---|---|---|---|---|
| S-A1 | `caso_abierto_antiguo` | id, status, created_at, días | revisar | M01 | 1 | Jefe Op. | **sí** | **NO** | 197 casos; 128 abiertos |
| S-A2 | `caso_en_riesgo_sla` | propiedad M04 + horas | priorizar | M04 | 1 | Jefe Op. | **sí** | **NO** | lee M04; **no** usa `first_response_at` |
| S-B1 | `actividad_vencida` | id, vence_en, estado | retomar | M02 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas hoy |
| S-B2 | `actividad_sin_responsable` | id, responsable NULL | asignar | M02/M03 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas |
| S-B3 | `actividad_bloqueada` | id, motivo_bloqueo | escalar | M05 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas; causa **declarada** |
| S-B4 | `compromiso_por_vencer` | id, vence_en, ventana | avisar | M02 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas |
| S-D1 | `dependencia_pendiente` | ambas actividades | resolver previa | M02 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas |
| S-E1 | `orden_sin_programar` | estado, prog NULL, sin fila M03 | programar | **M03** | 1 | Jefe Op. | **sí** | **NO** | **condición corregida**; 0 señales hoy |
| S-E2 | `orden_con_riesgo_operacional` | numero, iniciada_en, horas | verificar | M03/M05 | 1 | Jefe Op. | **sí** | **NO** | 2 OT `en_sitio` |
| S-F1 | `programacion_sin_publicar` | semana, estado | publicar | M03 | 1 | Jefe Op. | **sí** | **NO** | ⚠️ 0 filas; **no está en `TIPOS_SENAL`** |
| S-J1 | `dato_incompleto` | el campo faltante | — | M10 | **0** | — | **sí** | **NO** | informativa; **no está en `TIPOS_SENAL`** |
| — | capacidad / sobrecarga | — | — | M03 | — | — | **NO DISPONIBLE ACTUALMENTE** | **NO** | `operaciones_disponibilidad` = 0 filas |

**«¿Puede ejecutarse autónomamente hoy?» es NO en todas las filas**, y no por
política: por ausencia de camino de ejecución.

---

## 15. Revisión de infraestructura

### Ya existente — reutilizar

| | |
|---|---|
| `PropuestaSupervisor` con 8 señales, 6 estados, 5 niveles | **ya existe** |
| Restricción «sin evidencia no hay propuesta» | **ya existe** en la base |
| `NovedadOperativa` con las 8 causas cerradas | **ya existe** y coincide exactamente |
| Lógica de SLA en `Case` (horas hábiles) | **ya existe**; M09 la lee |
| `ActividadOperativa` con 9 tipos (compromiso, dependencia incluidos) | **ya existe** |
| `ProgramacionOrden` / `ProgramacionSemanal` | **ya existen** |
| RLS, tenant isolation, `audit_log` | **ya existen** |
| Kill switch, frontera, idempotencia | **ya existen** (10.13D / 10.14A) |

### Necesario en etapa posterior — **no implementado aquí**

| # | Qué | Por qué |
|---|---|---|
| 1 | **Rol «Jefe de Operaciones»** | **`Profile.ROLES` sólo tiene ADMIN y USER** (medido: 1 ADMIN, 4 USER). Hoy **no existe** el revisor que todo este diseño nombra. Sin él, «quién puede aceptar» no es verificable. **Es el hueco más importante.** |
| 2 | Dos tipos de señal nuevos | `programacion_sin_publicar` y `dato_incompleto` **no están** en `TIPOS_SENAL`. Migración de choices. |
| 3 | Campo de deduplicación | §5 necesita `ventana` o una clave derivada; hoy hay índice por `(org, tipo_senal, origen_id)` pero no unicidad. |
| 4 | Endpoints de revisión | listar propuestas y aceptar/modificar/rechazar. No existen. |
| 5 | Permiso «revisar propuestas» | ligado a (1). |
| 6 | Proceso que evalúe las señales | un job del scheduler — **y el registro de jobs de producción está vacío** a propósito. |
| 7 | Poblar M02/M03 | 5 de 8 señales no dispararán nunca mientras esas tablas tengan 0 filas. **No es un problema de M09.** |

### NO se necesita tocar

**Frontera externa** e **idempotencia**: intactas. M09 no produce efectos
externos, así que no abre permiso ni reclama operaciones. Si algún día lo
hiciera, pasaría por la frontera como cualquier otro módulo — sin excepción.

---

## Lo que este diseño corrige del enunciado

La señal de ejemplo —«OT existente + `programada_para` NULL» → «recomendar
programación»— **habría producido 3 propuestas falsas de 3** en producción hoy:
las tres OT tienen ese campo vacío y **las tres ya están iniciadas**, una de
ellas completada. El campo no está en uso.

La condición corregida exige además `estado_operativo = 'asignada'`,
`iniciada_en IS NULL` y ausencia de fila en `ProgramacionOrden`. **Resultado hoy:
0 señales** — que es la respuesta correcta, y justamente por eso vale.

---

# DECISIÓN

## **GO** para implementar M09 Shadow Mode.

El diseño está cerrado en lo que hace falta para implementar sin ambigüedad:

| | |
|---|---|
| Señales con condición objetiva y evidencia | **11 definidas**, 1 marcada NO DISPONIBLE |
| Cada señal dice qué **no** puede inferir | sí |
| Matriz señal → propuesta → módulo → revisor | completa |
| Niveles 0–1 definidos; 2–4 como FUTURO | sí |
| Estándar de evidencia (7 preguntas, 4 capas) | sí |
| Deduplicación, expiración, reapertura | definidas |
| Precedencia entre señales, sin arbitrariedad | definida |
| Estados y transiciones, con `ACEPTADA ≠ EJECUTADA` | definidos |
| Flujo humano y qué ve el revisor | definido |
| Fronteras con M02/M03/M04/M05 | definidas, sin duplicar lógica |
| Casos prohibidos | 12, explícitos |
| Indicadores | definidos, sin dashboards |

### Condiciones que el GO lleva pegadas

1. **Crear primero el rol «Jefe de Operaciones».** Hoy sólo existen ADMIN y
   USER. Sin revisor identificable, la revisión humana no es auditable.
2. **Aceptar que 5 de 8 señales darán cero** hasta que M02/M03 se pueblen. Es
   correcto; conviene decirlo antes para que nadie lea el silencio como fallo.
3. **Corregir `orden_sin_programar`** antes de implementarla.
4. **Dos tipos de señal nuevos** exigen migración de choices.

**Producción sin tocar. Kill switch DETENIDO. Ninguna llamada externa.**

**Me detengo. No implemento la Etapa D.**
