# M03-D — Auditoría y diseño de reprogramación operativa

**Fecha:** 2026-09-18
**Alcance:** auditoría + diseño. **0 código, 0 migraciones, producción solo `SELECT`.**

---

## RESUMEN EJECUTIVO

Reprogramar no es "programar otra vez". Es la primera operación de M03 que tiene
que **conservar lo que deja de ser cierto**, y la auditoría encontró que el
sistema está preparado para eso a medias — con una asimetría estructural que
nadie había nombrado:

> **La constraint `unique(programacion, orden)` hace que reprogramar dentro de la
> misma semana y reprogramar a otra semana sean dos operaciones técnicamente
> distintas.** Dentro de un plan, una orden puede tener **una sola línea**: no se
> puede conservar la anterior creando una nueva. Entre planes distintos, sí.
>
> O sea: **el historial por fila nueva es posible al cambiar de semana e
> imposible al cambiar de día.**

### Los cuatro hallazgos que ordenan el diseño

| # | Hallazgo | Consecuencia |
|---|---|---|
| **1** | `unique(programacion, orden)` | mismo-plan y otro-plan necesitan **mecanismos distintos** de historial |
| **2** | `ProgramacionOrden.REPROGRAMADA` **existe y nadie la escribe** | el modelo ya anticipó esta operación; M03-D sería su primer escritor |
| **3** | `EventoTrabajo.tipo` es **texto libre**, y `datos` es JSONB | es la **única** superficie de auditoría que admite antes/después **sin migración** |
| **4** | `NovedadOperativa` guarda la **fecha** anterior/nueva pero **no el plan** | no hay FK a `ProgramacionSemanal` ni a `ProgramacionOrden` → **GAP** |

### Y una medición que desactiva un miedo

**[MEDIDO]** `Case._sla_deadline` (`cases/models.py:454`) camina horas hábiles
**desde `Case.created_at`**, más el tiempo en pausa. **Nunca lee
`programada_para`.** Y `OrdenTrabajo` ni siquiera tiene FK a `Case`.

> **Reprogramar una OT NO extiende el SLA, ni lo toca.** Lo que el §16 pedía no
> asumir, está medido: la fecha programada es **informativa** para el SLA.
>
> El riesgo real es el contrario y conviene decirlo: como reprogramar no mueve el
> reloj, **reprogramar repetidamente consume presupuesto de SLA sin que nada
> avise**.

---

## 1. Estado actual

**[MEDIDO]** Producción, solo `SELECT`:

```
ProgramacionSemanal ....  0      ordenes ..............  3
ProgramacionOrden ......  0      ordenes programadas ..  0
NovedadOperativa .......  0      ordenes asignadas ....  3
EventoTrabajo .......... 12      Activity ............. 592  (564 Case, 28 Lead)

estados de OT:  en_sitio 2 · completada_campo 1
tipos de evento: datos_actualizados 3 · accion_marcar_en_camino 3 ·
                 accion_marcar_llegada 3 · evidencia_confirmada 2 ·
                 trabajo_completado_campo 1
```

**Cero planes, cero líneas, cero novedades.** M03-B y M03-C están desplegados en
código y **sin usar**: nadie ha programado ni publicado todavía.

> **Consecuencia metodológica:** no hay un solo caso real de reprogramación que
> auditar. Todo lo que sigue sale de **leer el modelo y el código**, no de
> observar datos. Donde no hay evidencia, se dice.

---

## 2. Infraestructura encontrada

Releída directamente (§3), no tomada de M03-A/B/C.

### `ProgramacionSemanal`

```
org (FK) · semana_inicio (Date, "Lunes de la semana que planifica")
estado {borrador | publicada | cerrada}  default borrador
publicada_en (DateTime, null) · publicada_por (FK Profile, SET_NULL, null)
notas (Text) · + created_at/by, updated_at/by de BaseModel
unique(org, semana_inicio) · ordering ["-semana_inicio"]
```

**Sin máquina de transiciones** (lo estableció M03-C). **Sin campo de
concurrencia optimista.** La única transición restringida hoy es
`borrador → publicada`, implementada en M03-C.

### `ProgramacionOrden`

```
org (FK) · programacion (FK ProgramacionSemanal, CASCADE)
orden (FK campo.OrdenTrabajo, CASCADE)
dia (Date) · hora_inicio · hora_fin (null) · zona (text) · prioridad · secuencia
estado {planificada | confirmada | reprogramada | cancelada}  default planificada
unique(programacion, orden)  ← LA CONSTRAINT QUE DECIDE TODO
ordering ["dia", "secuencia"] · index (org, dia)
```

**[MEDIDO]** De los cuatro estados, **el código solo escribe `planificada`**
(`programacion.py:222`). `confirmada`, `reprogramada` y `cancelada` están
**declarados y sin escritor** — el mismo patrón que `estado_validacion =
aprobable` en `OrdenTrabajo`, que su propio código documenta como deliberadamente
sin uso.

> `reprogramada` no es un estado que haya que inventar: **ya está esperando**.

### `OrdenTrabajo` — lo relevante aquí

```
programada_para (DateTime, null)  ·  iniciada_en · completada_campo_en · cerrada_en
estado_operativo {asignada | en_camino | en_sitio | completada_campo |
                  correccion_requerida | cerrada | cancelada}
revision (PositiveInteger)  ← control optimista de la cola offline
SIN prioridad · SIN campos SLA · SIN zona · SIN FK a Case
```

### `AsignacionTrabajo`

`orden`, `profile`, `rol` (catálogo cerrado de 5), `es_principal`, `asignado_en`.
`unique(orden, profile)` y `unique(orden) where es_principal`.
**No participa en una reprogramación** — ver §3.

### `EventoTrabajo` — la pieza clave

```
org · orden (FK) · tipo (CharField 64, SIN choices)  ← TEXTO LIBRE
profile (FK, SET_NULL) · datos (JSONField) · created_at
ordering ["created_at"]   append-only por convención
```

**[MEDIDO]** `tipo` **no tiene catálogo**. Es exactamente por eso que M03-B pudo
escribir `tipo="programacion"` sin migración. Y `datos` es JSONB: admite plan
anterior, plan nuevo, fecha anterior, fecha nueva y motivo **sin tocar el
esquema**.

### `NovedadOperativa`

```
org · tipo (8 valores, CATÁLOGO CERRADO) · descripcion (Text libre)
orden (FK, null) · actividad (FK, null) · profile (FK, null, "a quién afecta")
programada_anterior (DateTime, null) · programada_nueva (DateTime, null)
registrada_por (FK Profile, SET_NULL, null)
index (org, tipo, created_at) · index (org, orden)
```

**Lo que sí puede representar:** fecha anterior, fecha nueva, actor
(`registrada_por`), timestamp (`created_at`), organización, orden, motivo (`tipo`
+ `descripcion`).

**Lo que NO puede:** **plan anterior y plan nuevo.** No hay FK a
`ProgramacionSemanal` ni a `ProgramacionOrden`. → **GAP G-2.**

### `Activity` — la auditoría transversal del CRM

```
user (FK Profile) · action (35 verbos) · entity_type (12 valores, CATÁLOGO)
entity_id (UUID) · entity_name · description · metadata (JSONField) · org
```

**[MEDIDO]** `operaciones/auditoria.py::registrar` **ya acepta**
`estado_anterior`, `estado_nuevo`, `motivo` y `extra`, y los guarda en `metadata`.
**La infraestructura de antes/después está completa y funcionando** — M09-F la usa.

**El único bloqueo es `ENTITY_TYPE_CHOICES`**, que tiene `ActividadOperativa` y
`PropuestaSupervisor` y **ninguna entidad de M03**. Declarar una es una migración
→ §32 prohíbe. → **GAP G-3.**

**[MEDIDO]** En producción `Activity` tiene 592 filas, todas `Case` (564) y `Lead`
(28): **ninguna entidad de operaciones ha escrito nunca ahí.**

### Servicios y endpoints existentes

| Operación | Servicio | Endpoint | Locking | Auditoría |
|---|---|---|---|---|
| crear orden | `despacho.crear_orden` | `POST campo/trabajos/crear/` | — | `EventoTrabajo` `orden_creada` |
| asignar / reasignar | `despacho.asignar` | `POST campo/trabajos/<pk>/asignar/` | transacción | `EventoTrabajo` `asignacion`/`reasignacion` |
| **programar** | `programacion.programar_orden` | `POST campo/trabajos/<pk>/programar/` | `select_for_update` OT | `EventoTrabajo` `programacion` |
| **publicar plan** | `programacion.publicar_programacion` | `POST operaciones/programacion/<id>/publicar/` | `select_for_update` plan | `publicada_por` + `updated_by` |
| **reprogramar** | **NO EXISTE** | **NO EXISTE** | — | — |

---

## 3. Definición — seis operaciones que no son sinónimos (§4)

| Operación | Qué cambia | Existe hoy |
|---|---|---|
| **PROGRAMAR** | **cuándo** se hace, por primera vez | **SÍ** — M03-B |
| **REPROGRAMAR** | **cuándo** se hace, cuando ya había un cuándo | **NO** |
| **ASIGNAR** | **quién** lo hace, por primera vez | **SÍ** — `despacho.asignar` |
| **REASIGNAR** | **quién** lo hace, cambiando al anterior | **SÍ** — mismo servicio, evento distinto |
| **REDISTRIBUIR** | **quién**, sobre varias órdenes, para equilibrar carga | **NO** — necesita capacidad, que no existe |
| **CANCELAR** | la orden deja de hacerse | **SÍ** — transición a `cancelada` |

> **REPROGRAMAR no implica cambiar técnico.** Son ejes independientes: el *cuándo*
> vive en `programada_para` + `ProgramacionOrden`; el *quién*, en
> `AsignacionTrabajo`. Una reprogramación que además cambie de persona son **dos
> operaciones**, y mezclarlas haría imposible saber cuál de las dos causó qué.

---

## 4. Casos de uso (§5)

**Ninguno se decide aquí.** Se clasifica lo que el código ya permite o impide.

| Caso | Situación | Qué dice el código hoy | Veredicto |
|:--:|---|---|---|
| **A** | misma semana, otra fecha | `unique(programacion, orden)` **impide** una segunda línea en el mismo plan | **[TÉCNICO]** solo cabe actualizar la línea o marcarla y mover la orden a otro plan |
| **B** | otra semana | una línea nueva en otro plan **sí cabe**; la anterior quedaría vigente salvo que se marque | **[TÉCNICO]** posible; exige marcar la vieja |
| **C** | plan en borrador | M03-B acepta `borrador`; nada lo impide | **[MEDIDO]** permitido |
| **D** | plan publicado | M03-B acepta `publicada`; nada lo impide | **[MEDIDO]** permitido hoy → **P-4** |
| **E** | OT programada, sin asignar | M03-B programa sin exigir técnico (prueba B9) | **[MEDIDO]** permitido |
| **F** | OT asignada, no iniciada | `estado_operativo = asignada` es el único programable | **[MEDIDO]** es el caso natural |
| **G** | OT ya iniciada | M03-B rechaza los 6 estados restantes con 400 | **[MEDIDO]** hoy imposible programar; reprogramar **no tiene regla** → decisión |
| **H** | OT finalizada | `cerrada` es terminal; `despacho.asignar` ya rechaza "trabajo terminado" | **[EXISTENTE]** precedente claro: no |
| **I** | OT cancelada | terminal, mismo precedente | **[EXISTENTE]** precedente claro: no |

> **Los casos G, H e I tienen precedente pero no regla.** `despacho.asignar` dice
> *"No se reasigna un trabajo terminado"* para `cerrada`/`cancelada`, y M03-B
> restringe la programación a `asignada`. Eso **sugiere** el criterio, no lo
> establece para reprogramar. El caso G —una orden que el técnico ya empezó y hay
> que mover a otro día— es el que más falta hace decidir y el que menos evidencia
> tiene.

---

## 5. P-4 — el plan publicado (§6, obligatorio)

### La evidencia que existe

**[EXISTENTE EN CÓDIGO]** `supervisor.py:630`, en la recomendación de la señal
`programacion_sin_publicar`:

> *"Un plan en borrador no compromete a nadie: **las cuadrillas no lo ven**."*

Por contraposición, esa frase dice qué significa publicar en este sistema:
**publicar es el momento en que el plan pasa a ser un compromiso visible para el
campo.** Es la única definición operativa de "publicado" que existe escrita.

**[MEDIDO]** Y el comportamiento actual: `M03-B` acepta planes en `borrador`
**y** en `publicada` (`ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS`), así que **hoy un plan
publicado admite líneas nuevas**.

### El precedente adyacente, que NO decide

`WorkTypeVersion` es el único caso del repositorio donde "publicado" **sí**
significa congelado: `clean()` rechaza `PUBLICADA → BORRADOR`, bloquea los campos
de definición y dice *"Cree una nueva versión vN+1"*.

> **Pero no es el mismo problema, y tomarlo por tal sería el error que A-3.2 ya
> evitó una vez.** Una plantilla congelada protege la auditabilidad de una
> evidencia pasada: hay que poder decir contra qué regla se aprobó un trabajo. Un
> plan semanal describe **trabajo futuro**, que por definición cambia cuando la
> semana ocurre. Congelar lo primero y congelar lo segundo significan cosas
> distintas.

### Veredicto

| | |
|---|---|
| ¿Hay evidencia de qué **significa** publicar? | **SÍ** — compromete, y las cuadrillas lo ven |
| ¿Hay evidencia de si publicar **congela**? | **NO** |

# P-4 = DECISIÓN DE NEGOCIO PENDIENTE

Las tres alternativas, con lo que cada una implica:

| | Alternativa | Qué exigiría |
|---|---|---|
| **P4-A** | publicado = **congelado** | restringir M03-B a `borrador`; toda modificación posterior pasa por reprogramación formal; el plan publicado se vuelve un documento |
| **P4-B** | publicado = **modificable** | nada nuevo; pero entonces "publicado" no distingue nada y la señal de M09 pierde sentido |
| **P4-C** | publicado = **modificable solo por reprogramación formal** | M03-B sigue aceptando borrador; agregar a un publicado exige la operación con historial |

> **P4-C es la que el modelo parece anticipar** —`REPROGRAMADA` existe sin
> escritor, `NovedadOperativa` existe para "lo que obligó a cambiar el plan"— pero
> **anticipar no es decidir**, y M03-A ya dejó escrito que *"no asumir que una
> estructura técnica existente representa una política empresarial aprobada"*.
> **No se elige aquí.**

**No se implementó ninguna restricción** (§6, §32).

---

## 6. Historial (§7)

Qué puede conservar cada infraestructura existente, sin crear nada:

| Dato | `EventoTrabajo` | `NovedadOperativa` | `Activity` | `ProgramacionOrden` |
|---|:--:|:--:|:--:|:--:|
| fecha anterior | **sí** (`datos`) | **sí** (`programada_anterior`) | sí (`metadata`) | no |
| fecha nueva | **sí** (`datos`) | **sí** (`programada_nueva`) | sí (`metadata`) | sí (`dia`) |
| **plan anterior** | **sí** (`datos`) | **NO** | sí (`metadata`) | implícito por FK |
| **plan nuevo** | **sí** (`datos`) | **NO** | sí (`metadata`) | implícito por FK |
| actor | **sí** (`profile`) | **sí** (`registrada_por`) | sí (`user`) | `updated_by` |
| timestamp | **sí** (`created_at`) | **sí** (`created_at`) | sí | `updated_at` |
| motivo | **sí** (`datos`) | **sí** (`tipo`+`descripcion`) | sí (`motivo`) | no |
| **¿exige migración?** | **NO** | **NO** | **SÍ** (`entity_type`) | **NO** |

### La conclusión

> **`EventoTrabajo` es la única superficie que puede registrar una reprogramación
> completa —incluido el cambio de plan— sin tocar el esquema.** Su `tipo` es texto
> libre y su `datos` es JSONB.
>
> **`NovedadOperativa` es la que el modelo declara para esto** (*"Lo que obligó a
> cambiar el plan. Es lo que hace auditable una reprogramación"*) y le **falta
> precisamente el plan**.
>
> Las dos son complementarias, no alternativas: una registra el **hecho técnico**,
> la otra la **causa operativa**.

---

## 7. `ProgramacionOrden` — cómo evoluciona una línea (§9)

**La constraint decide, y decide distinto según el caso.**

```
unique(programacion, orden)     una orden, una línea POR PLAN
```

### Caso A — misma semana (mismo plan)

```
Plan A (semana del 05/10)
  └── OT 100 · dia 07/10 · planificada

  reprogramar al 09/10 →  NO CABE una segunda línea en Plan A
```

**Opciones que el modelo permite:**

| Opción | Historial en la línea | Coste |
|---|---|---|
| **A1** actualizar `dia` in situ | **se pierde** | ninguno; el historial queda solo en `EventoTrabajo`/`NovedadOperativa` |
| **A2** marcar `reprogramada` y **no** crear otra | se conserva | la orden queda **sin línea vigente** → dispara `orden_sin_programar` |
| **A3** marcar `reprogramada` y crear la nueva **en otro plan** | se conserva | convierte un cambio de día en un cambio de plan: artificial |

### Caso B — otra semana (otro plan)

```
Plan A ── OT 100 · 07/10 · planificada  →  marcar 'reprogramada'
Plan B ── OT 100 · 20/10 · planificada  ←  línea nueva, la constraint la permite
```

**Aquí el historial por fila nueva sí funciona**, y es exactamente para lo que
`REPROGRAMADA` parece existir.

### El peligro que hay que nombrar

**[MEDIDO]** `supervisor._programacion_vigente` hace
`.filter(estado__in=(planificada, confirmada)).first()`, y `Meta.ordering` de
`ProgramacionOrden` es `["dia", "secuencia"]`.

> **`.first()` devuelve la línea del día MÁS TEMPRANO.** Si una reprogramación
> deja la línea vieja en `planificada` y crea una nueva más adelante, el detector
> de M09 **leerá la vieja** — la que ya no rige. No fallaría nada: contestaría la
> pregunta equivocada con aire de dato.
>
> **Marcar la línea anterior no es higiene: es la condición para que M09 siga
> diciendo la verdad.**

**No se elige opción** (§9). La asimetría A/B es lo que M03-D aporta.

---

## 8. `programada_para` (§10)

### Quién la escribe

**[MEDIDO]** Exactamente dos sitios:

| Sitio | Cuándo |
|---|---|
| `despacho.crear_orden` (`despacho.py:108`) | al **crear** la orden |
| `programacion.programar_orden` (M03-B) | al **programar**, con la línea, en una transacción |

**Ningún tercero la modifica.** Reprogramar sería el tercero.

### Quién la lee

| Lector | Condición | Qué pasa si cambia |
|---|---|---|
| `_ordenes_sin_programar` | `isnull=True` + `asignada` + sin línea vigente | una reprogramación que la dejara en NULL dispararía la señal |
| `_ordenes_desincronizadas` | `isnull=True` + `asignada` + línea vigente en plan **publicado** | **el escenario exacto de una reprogramación a medias** |
| `_ordenes_en_riesgo` (**H-05**) | `isnull=False` + `asignada` + principal + ausencia ese día | cambia el día que se compara contra la ausencia |
| serializers de campo | lectura | la app del técnico ve otra fecha |
| `campo/admin.py` | lectura | — |
| **SLA** | **no la lee** | **nada** |

### Constraints

**Ninguna.** `programada_para` es `DateTimeField(null=True, blank=True)` sin
`CheckConstraint` ni validación de estado. Todo el control es de servicio.

---

## 9. Novedades (§8, §17, §19)

### Qué es `tipo = reprogramacion` hoy

**[MEDIDO]** Un valor del catálogo cerrado de 8, **que nadie escribe** (0 filas en
producción, 0 escritores en el código).

### El hallazgo del §17: el catálogo mezcla causa y efecto

```
CAUSAS          ausencia · bloqueo · falta_material · dependencia ·
                cambio_de_prioridad · dato_incompleto
EFECTO          reprogramacion
NI UNA NI OTRO  demora_sin_causa_registrada   (es "solo tengo fechas")
```

> **Una sola `NovedadOperativa` no puede decir "se reprogramó **porque** el
> técnico estaba ausente".** Si se guarda `tipo=reprogramacion`, se pierde la
> causa; si se guarda `tipo=ausencia`, se pierde el efecto. El campo `tipo` es uno
> solo y el catálogo es cerrado.

Tres salidas, ninguna elegida aquí:

| | Salida | Coste |
|---|---|---|
| **N1** | dos filas: una causa + una `reprogramacion` | duplica; nada las relaciona (no hay FK entre novedades) |
| **N2** | una fila con la causa, y el antes/después en `programada_anterior/nueva` | `reprogramacion` queda para siempre sin uso |
| **N3** | una fila `reprogramacion` con la causa en `descripcion` (texto libre) | la causa deja de ser agrupable |

### ¿Toda reprogramación genera una novedad? (§17)

**No hay regla.** El docstring dice que `NovedadOperativa` es *"lo que obligó a
cambiar el plan"* — lo que sugiere que la novedad es la **causa**, no el registro
del cambio. Pero una reprogramación **sin** causa registrada (alguien cambia de
idea) no tendría novedad, y entonces el antes/después de la fecha **no quedaría en
ningún sitio** salvo `EventoTrabajo`.

**Separando causa y efecto como pide el §17:**

```
señal (H-05, bloqueo, falta de material...)
   ↓
propuesta del Supervisor NOC IA      ← M09, ya existe, no ejecuta
   ↓
DECISIÓN HUMANA                      ← la frontera
   ↓
reprogramación                       ← M03-D, no existe
```

**Ausencia ≠ reprogramación automática.** Una ausencia es un hecho; reprogramar es
una decisión. El §18 y el §19 lo piden explícitamente y el sistema entero ya está
construido así: M09 **propone** y no ejecuta.

---

## 10. SLA (§16)

**[MEDIDO]** El motor, en `cases/models.py:454`:

```python
deadline = add_business_hours(self.created_at, hours, self._sla_calendar())
deadline = deadline + timedelta(seconds=paused)
```

| Pregunta del §16 | Respuesta medida |
|---|---|
| ¿Qué fecha usa el SLA? | **`Case.created_at`**, caminada en horas hábiles, más el tiempo en `Pending` |
| ¿La fecha programada afecta al SLA? | **NO.** `programada_para` no aparece en el motor |
| ¿La fecha programada es informativa? | **Sí**, para el SLA lo es por completo |
| ¿Qué lee M03 del SLA? | **Nada.** La orden no tiene FK a `Case` |

> **Reprogramar NO extiende el SLA.** Lo que el §16 advertía no asumir está
> medido: no hay ningún camino por el que una reprogramación toque el reloj.
>
> **Y el riesgo real es el inverso:** como el reloj no se mueve, reprogramar tres
> veces **gasta presupuesto de SLA en silencio**. Hoy nadie lo vería, porque la
> orden ni siquiera sabe a qué caso pertenece. → **decisión de negocio.**

**No se modificó el motor SLA** (§16, §32).

---

## 11. H-05 (§18)

**No se tocó.**

**[MEDIDO]** `_ordenes_en_riesgo` exige `programada_para IS NOT NULL` +
`estado = asignada` + técnico principal + ausencia ese día, y construye su huella
así:

```python
huella = f"prog:{o.programada_para:%Y-%m-%d}|aus:{ausencia.id}"
```

**La huella incluye la fecha programada.** Y `_ya_propuesta` documenta qué
significa eso:

> *"Si la condición cambia --otro motivo de bloqueo, **otra fecha comprometida**,
> otra dependencia-- la huella cambia y la propuesta nueva SÍ se crea, aunque la
> anterior esté rechazada. Una decisión se toma sobre unos hechos; con hechos
> distintos, la pregunta es otra."*

> **Reprogramar generando una propuesta H-05 nueva no es un defecto: es la
> conducta declarada.** Si se reprograma a un día en que el técnico también está
> ausente, la señal debe volver — y vuelve. Si el día nuevo está libre, no vuelve.
>
> El ciclo correcto es el del §18: **H-05 detecta → el Supervisor revisa → una
> persona decide reprogramar.** H-05 no reprograma, y M03-D no debe hacer que lo
> haga.

---

## 12. M09 (§22)

| Señal | ¿Afectada por reprogramar? | Riesgo |
|---|---|---|
| `orden_sin_programar` | **sí** | si la reprogramación deja `programada_para` en NULL o sin línea vigente → **falso positivo** |
| `dato_incompleto` (`_ordenes_desincronizadas`) | **sí** | es literalmente "hay línea y no hay fecha": una reprogramación a medias **lo produce** |
| `orden_con_riesgo_operacional` (H-05) | **sí** | huella nueva → propuesta nueva. **Correcto por diseño**, no duplicación |
| `programacion_sin_publicar` | **indirecta** | reprogramar a un plan nuevo en borrador crea un borrador más que envejecerá |
| las otras 6 | no | no leen programación |

### Los dos peligros concretos

1. **La línea vieja sin marcar.** `_programacion_vigente().first()` con ordering
   por `dia` devuelve la **más temprana**: la obsoleta. M09 razonaría sobre un plan
   que ya no rige.
2. **La ventana de incoherencia.** Si fecha y línea no se escriben en la misma
   transacción, un ciclo del Supervisor que corra en medio ve exactamente el estado
   que `dato_incompleto` reporta.

> Las dos se evitan con lo mismo: **una transacción y marcar la línea anterior.**
> Es la misma lección que M03-B ya aplicó, extendida a un caso más.

**No se modificó M09.**

---

## 13. Concurrencia (§12)

**[MEDIDO]** Lo que ya existe y sirve:

| Mecanismo | Dónde | Reutilizable |
|---|---|---|
| `select_for_update()` sobre la OT | `programar_orden` | **sí, directamente** |
| `select_for_update()` sobre el plan | `publicar_programacion` | sí, si cambia de plan |
| `transaction.atomic` | ambos | sí |
| `unique(programacion, orden)` | base | **sí** — corta el duplicado dentro de un plan |
| `OrdenTrabajo.revision` | control optimista de la app offline | señala el cambio al técnico |
| `manejar_idempotencia` | `Idempotency-Key` en campo | **sí**, si la ruta cuelga de `trabajos/<pk>/` |

**Las carreras que hay que evitar:**

| Carrera | Resultado sin lock | Lo que ya lo resuelve |
|---|---|---|
| dos reprogramaciones a la vez | dos fechas incompatibles | `select_for_update` sobre la OT |
| dos líneas vigentes | M09 lee la obsoleta | marcar la anterior **dentro** de la misma transacción |
| historial perdido | la segunda pisa el antes/después de la primera | el lock + escribir historial antes de mover la fecha |

**No hace falta mecanismo nuevo.** (§12, §32.)

---

## 14. Idempotencia (§13)

Hay que distinguir **tres** cosas, no dos:

| | Qué es | Infraestructura |
|---|---|---|
| **repetir la misma reprogramación** (doble clic) | la misma fecha, el mismo plan, el mismo motivo | **`manejar_idempotencia`** (`Idempotency-Key`) ya lo cubre si la ruta está en campo |
| **una reprogramación nueva** | otra fecha, u otro motivo | debe ejecutarse: es una decisión distinta |
| **reprogramar a la fecha que ya tiene** | el estado final es idéntico | **sin regla** → decisión |

> El tercer caso no es idempotencia: es una operación cuyo efecto es nulo pero
> cuyo **registro** no lo sería (quedaría un evento y quizá una novedad diciendo
> que se movió algo que no se movió). **Decisión de negocio.**

**No se crea mecanismo nuevo sin necesidad demostrada** (§13).

---

## 15. Permisos y seguridad (§14, §29)

### Actor

**[MEDIDO]** No hay **ninguna** evidencia específica sobre quién reprograma: ni en
PRD, ni en el SOP de campo, ni en código, ni en comentarios.

**El precedente, que sí existe:**

| Operación | Permiso |
|---|---|
| crear / asignar / validar (campo) | `ROLES_GESTION` = `{ADMIN, SUPERVISOR, OPERACIONES}` |
| **programar** (M03-B) | el mismo |
| **publicar** (M03-C) | el mismo, vía `EsJefeDeOperaciones` |
| registrar disponibilidad (A-3.3) | el mismo |

> **Reprogramar con el mismo conjunto sería coherente con las cuatro operaciones
> anteriores.** Pero eso **resuelve por defecto la decisión D-6** (*"¿quién
> programa?"*), que sigue abierta desde M03-A.
>
> **No se elige.** Se deja dicho que el precedente es unánime y que adoptarlo es
> una decisión, no una deducción.

**0 roles nuevos** (§32).

### Seguridad

**[MEDIDO]** Estado real de RLS en las tablas que una reprogramación tocaría:

| Tabla | RLS | forced | políticas |
|---|:--:|:--:|:--:|
| `campo_orden_trabajo` | **false** | **false** | **0** |
| `campo_evento_trabajo` | **false** | **false** | **0** |
| `campo_asignacion_trabajo` | **false** | **false** | **0** |
| `operaciones_programacion_semanal` | true | true | 2 |
| `operaciones_programacion_orden` | true | true | 2 |
| `operaciones_novedad` | true | true | 2 |
| `activity` | true | true | 2 |

> **Una reprogramación escribiría en tablas con RLS y en tablas sin RLS a la vez.**
> El aislamiento de `campo_orden_trabajo` y `campo_evento_trabajo` lo da **solo la
> aplicación**, y **B-7 no lo cambia**: no hay política que activar (la causa es
> `ORG_SCOPED_TABLES`, que no lista ninguna `campo_*`).

`organization_id` debe salir de `request.org`, nunca del cliente — el criterio ya
establecido en A-3.3, M03-B y M03-C. **No se modificó B-7 ni RLS** (§29, §32).

---

## 16. Matriz de decisiones (§25)

| Tema | Evidencia encontrada | Regla actual | Decisión requerida |
|---|---|---|---|
| **P-4 plan publicado** | *"un borrador no compromete a nadie: las cuadrillas no lo ven"* (`supervisor.py:630`). Precedente adyacente: `WorkTypeVersion` congela | M03-B **acepta** borrador y publicada | **SÍ — P4-A / P4-B / P4-C** |
| reprogramar misma semana | `unique(programacion, orden)` impide 2ª línea en el plan | ninguna operación existe | **SÍ — actualizar in situ vs. mover de plan** |
| cambio de semana | la constraint **sí** permite línea en otro plan; `REPROGRAMADA` existe sin escritor | ninguna | **SÍ — marcar la anterior o no** |
| **OT asignada, no iniciada** | M03-B solo programa `asignada` | programar sí; reprogramar no existe | no (caso natural) |
| **OT iniciada** | M03-B la rechaza para programar; **sin regla para reprogramar** | ninguna | **SÍ — el caso G es el más urgente** |
| OT finalizada / cancelada | `despacho.asignar`: *"no se reasigna un trabajo terminado"* | precedente, no regla | **SÍ**, aunque el precedente es claro |
| **actor autorizado** | precedente unánime: `ROLES_GESTION` en las 4 operaciones previas | ninguna específica | **SÍ — D-6 sigue abierta** |
| **motivo** | `NovedadOperativa.tipo` (8, cerrado) mezcla causa y efecto; `descripcion` es libre | ninguna | **SÍ — catálogo de motivos pendiente** |
| **SLA** | `_sla_deadline` ancla en `Case.created_at`; no lee `programada_para` | reprogramar **no** toca el SLA | **SÍ — ¿debe avisarse el consumo silencioso?** |
| **novedad** | el modelo la declara para esto; le falta el plan | ninguna | **SÍ — ¿obligatoria? ¿una fila o dos?** |
| **historial** | `EventoTrabajo` puede todo sin migración; `Novedad` no guarda el plan; `Activity` bloqueada por `entity_type` | ninguna | **SÍ — qué superficie es la canónica** |

---

## 17. Matriz de impacto (§26)

| Cambio | `ProgramacionOrden` | `programada_para` | Novedad | SLA | H-05 | M09 |
|---|---|---|---|:--:|---|---|
| **A · misma semana, otro día** | actualizar `dia` (la constraint impide 2ª línea) | nueva fecha | opcional | **ninguno** | huella nueva → puede reemitir | `dato_incompleto` si no es atómico |
| **B · otra semana** | marcar vieja `reprogramada` + línea nueva en otro plan | nueva fecha | opcional | **ninguno** | huella nueva → puede reemitir | riesgo de **dos vigentes** |
| **C · plan borrador** | igual que A/B | igual | igual | **ninguno** | igual | `programacion_sin_publicar` si envejece |
| **D · plan publicado** | **depende de P-4** | igual | **probablemente obligatoria** | **ninguno** | igual | — |
| **E · sin asignar** | igual | igual | igual | **ninguno** | **no aplica** (H-05 exige principal) | — |
| **F · asignada, no iniciada** | igual | igual | igual | **ninguno** | **aplica** | — |
| **G · ya iniciada** | **sin regla** | **sin regla** | **sin regla** | **ninguno** | no aplica (ya no es `asignada`) | — |
| **H/I · finalizada / cancelada** | no debería | no debería | no | **ninguno** | no aplica | — |
| **sin marcar la línea vieja** | 2 vigentes | — | — | — | — | **M09 lee la obsoleta** |
| **sin transacción única** | línea sin fecha | fecha sin línea | — | — | — | **`dato_incompleto`** |

---

## 18. Diseño propuesto (§27)

**Conceptual. No se escribió una línea de código.**

### Operación

```
reprogramar_orden(*, org, orden, programada_para_nueva, actor,
                  programacion_destino=None, motivo="", tipo_novedad=None)
    → (linea_nueva, novedad|None)
```

### Transacción y locking

Una sola `transaction.atomic`, con `select_for_update()` sobre la OT **antes** de
leer su estado — el mismo patrón que M03-B, verificado desarmándolo. Si cambia de
plan, también sobre el plan destino.

### Orden de las operaciones

```
1. actor presente; fecha con zona horaria
2. la orden y el plan destino pertenecen a request.org
3. lock sobre la OT; releer estado y programada_para
4. la orden ESTÁ programada (si no, esto es programar, no reprogramar)
5. estado permitido                              ← DECISIÓN (casos F/G)
6. el plan destino admite líneas                 ← DECISIÓN (P-4)
7. la fecha cae dentro de la semana del destino  ← regla derivada, heredada
8. ESCRIBIR EL HISTORIAL PRIMERO
9. marcar la línea anterior 'reprogramada'       ← evita las dos vigentes
10. crear/actualizar la línea destino
11. fijar programada_para; revision += 1
12. EventoTrabajo tipo='reprogramacion' con antes/después
13. NovedadOperativa si hay causa               ← DECISIÓN
```

> **El paso 8 es el que distingue esta operación de M03-B.** Programar solo tenía
> que dejar un estado correcto; reprogramar tiene que dejar además **constancia de
> lo que dejó de ser cierto**. Si el historial se escribe al final y algo falla,
> lo que se pierde es justo la parte que no se puede reconstruir.

### Historial: dos superficies, cada una con su trabajo

| Superficie | Registra | Por qué |
|---|---|---|
| **`EventoTrabajo`** `tipo="reprogramacion"` | fecha anterior/nueva, plan anterior/nuevo, línea anterior/nueva, actor, timestamp | **el hecho técnico**. Es la única que lo admite entero sin migración, y ya es donde vive `reasignacion` |
| **`NovedadOperativa`** | la causa (`tipo`), el motivo, `programada_anterior/nueva`, `registrada_por` | **la causa operativa**, cuando la hay |

**No se crea tabla ni entidad** (§7, §32).

### Coherencia

Idéntica a M03-B, con la misma conversión (§20): `dia =
timezone.localtime(programada_para).date()`, la que usa H-05. **No se introduce
otra conversión, no se toca `TIME_ZONE`, no se corrige `BusinessCalendar`.**

Y una invariante nueva que M03-C ya sabe comprobar: **una orden, una sola línea
vigente**. `revisar_coherencia` podría extenderse para afirmarlo.

### Permisos

`ROLES_GESTION`, por precedente — **sujeto a D-6**.

### Comportamiento por estado

| Estado de la OT | Propuesta | Origen |
|---|---|---|
| `asignada` | **permitir** | es el caso natural; M03-B ya lo restringe así |
| `en_camino` / `en_sitio` | **DECISIÓN** (caso G) | sin evidencia |
| `correccion_requerida` | **DECISIÓN** | heredada de M03-B |
| `completada_campo` | **DECISIÓN** | sin evidencia |
| `cerrada` / `cancelada` | **rechazar** | precedente de `despacho.asignar` |

---

## 19. Orden de implementación (§28)

| Fase | Qué | Bloqueada por |
|---|---|---|
| **M03-D1** | **Decisión de negocio**: P-4, casos F/G/H/I, actor, motivo, novedad obligatoria o no | nadie — solo hace falta decidir |
| **M03-D2** | **Diseño técnico cerrado**: elegir A1/A2/A3 y N1/N2/N3 según D1 | D1 |
| **M03-D3** | **Implementar** `reprogramar_orden` + endpoint + suite | D2 |
| **M03-D4** | *(opcional)* extender `revisar_coherencia` con "una sola línea vigente" | D3 |

**Fuera del camino pero en él:**

| | Qué | Por qué |
|---|---|---|
| **G-3** | `Activity.ENTITY_TYPE_CHOICES` sin entidades de M03 | sin eso, la auditoría transversal no ve M03 |
| **G-2** | `NovedadOperativa` sin FK a plan | la novedad no puede decir a qué plan se movió |
| **P-8** | `campo_*` sin RLS | reprogramar escribiría en tablas sin aislamiento de base |

> **Lo mínimo que desbloquea más:** M03-D1. Ninguna línea de código puede
> escribirse con honestidad mientras P-4 y el caso G sigan sin respuesta — y
> ninguna de las dos es una pregunta técnica.

---

## GAPs

### Críticos

| # | GAP | Tipo |
|:--:|---|---|
| **G-1** | **No existe operación de reprogramar.** `programada_para` solo se escribe al crear y al programar | operación |
| **G-2** | **`NovedadOperativa` no guarda plan anterior ni nuevo** — sin FK a `ProgramacionSemanal`/`ProgramacionOrden` | modelo |
| **G-3** | **`Activity.ENTITY_TYPE_CHOICES` sin entidades de M03** → la auditoría transversal no puede registrar antes/después | modelo (migración) |
| **G-4** | **`unique(programacion, orden)` impide conservar la línea anterior dentro del mismo plan** | estructural |

### Importantes

| # | GAP | Tipo |
|:--:|---|---|
| G-5 | El catálogo de `NovedadOperativa` **mezcla causa y efecto**: `reprogramacion` convive con seis causas | modelo + negocio |
| G-6 | **`.first()` por `dia`** devuelve la línea más temprana: dos vigentes hacen que M09 lea la obsoleta | riesgo de diseño |
| G-7 | **La orden no tiene FK a `Case`**: no puede saber qué SLA consume al reprogramarse | modelo |
| G-8 | `ProgramacionOrden` **no dice quién**: no hay FK a técnico | modelo |
| G-9 | `confirmada`, `reprogramada` y `cancelada` **declarados sin escritor** | observación |
| G-10 | **`campo_*` sin RLS** — B-7 no lo resuelve | seguridad |

---

## CRITERIO DE SALIDA (§34) — las 15 respuestas

| # | Pregunta | Respuesta |
|:--:|---|---|
| 1 | **¿Qué es reprogramar?** | Cambiar **cuándo** se ejecuta una OT que ya tenía cuándo. **No implica cambiar técnico** |
| 2 | **¿Qué estados permiten reprogramar?** | `asignada` por precedente. `cerrada`/`cancelada` no, por el precedente de `asignar`. **Los intermedios: sin regla** |
| 3 | **¿Plan publicado?** | Hoy **admite líneas**. Hay evidencia de qué significa publicar, **ninguna** de si congela → **P-4 abierto** |
| 4 | **¿Plan cerrado?** | M03-C ya lo rechaza para publicar; `cerrada` no tiene salida. Para reprogramar, **sin regla explícita** |
| 5 | **¿Se puede cambiar de semana?** | **Estructuralmente sí** — la constraint lo permite entre planes. Es el único caso donde el historial por fila nueva funciona |
| 6 | **¿Cómo se conserva el historial?** | **`EventoTrabajo`** (todo, sin migración) + **`NovedadOperativa`** (la causa; le falta el plan) |
| 7 | **¿Coherencia con `programada_para`?** | Misma transacción, mismo lock, misma conversión `localtime()` que M03-B y H-05 |
| 8 | **¿`NovedadOperativa`?** | Puede guardar fecha antes/después, actor y motivo. **No el plan.** Y su catálogo mezcla causa con efecto |
| 9 | **¿Qué actor?** | Precedente unánime `ROLES_GESTION` en las 4 operaciones previas. **Adoptarlo es decidir D-6** |
| 10 | **¿Qué motivo?** | `tipo` (catálogo de 8) + `descripcion` libre. **No hay catálogo de motivos de reprogramación** → pendiente |
| 11 | **¿Impacto en SLA?** | **Ninguno, medido.** El SLA ancla en `Case.created_at`. Riesgo inverso: consumo silencioso |
| 12 | **¿Impacto en H-05 / M09?** | H-05 reemite por huella — **es la conducta declarada**. `orden_sin_programar` y `dato_incompleto` dan falsos positivos si no es atómico |
| 13 | **¿Carrera concurrente?** | `select_for_update` sobre la OT + `transaction.atomic` + `unique(programacion, orden)`. **Todo existe** |
| 14 | **¿Qué es existente y qué decisión?** | 10 GAPs técnicos vs. **11 decisiones de negocio** (§16) |
| 15 | **¿Implementación mínima futura?** | **M03-D1: decidir.** Nada honesto se puede codificar mientras P-4 y el caso G sigan abiertos |

---

## Conformidad (§30, §31, §32)

```
código ................. 0        modelos .......... 0        tablas ..... 0
migraciones ............ 0        roles ............ 0        RLS ........ sin cambios
M03-B / M03-C .......... sin tocar    H-05 / M09 ... sin tocar
A-3 / B-7 / SLA ........ sin tocar    catálogo de motivos ... no creado
automatización ......... ninguna      IA de reprogramación .. ninguna
producción ............. SOLO SELECT (read_only = True)
commit ................. no
```

No hizo falta entorno aislado (§24): toda la auditoría se resolvió leyendo
modelos, servicios, constraints y datos existentes. **No se creó ningún dato
sintético.**
