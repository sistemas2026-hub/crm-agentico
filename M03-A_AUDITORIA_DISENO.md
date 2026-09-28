# M03-A — Auditoría y diseño de Programación, Asignación y Cuadrillas

**Fecha:** 2026-09-18
**Alcance:** auditoría + diseño. **0 líneas de código, 0 migraciones, producción solo lectura.**
**Método:** lectura de modelos y servicios + `SELECT` contra producción con `read_only = True`.

---

## RESUMEN EJECUTIVO

El hallazgo central de M03-A cabe en una frase:

> **M03 no está a medio construir: está construido por la mitad de arriba y vacío
> por la mitad de abajo.** Las tres estructuras que definen la programación
> —`ProgramacionSemanal`, `ProgramacionOrden`, `NovedadOperativa`— existen como
> tabla, con RLS, con constraints y registradas en el admin, y **no tienen un solo
> escritor en todo el código**. Ni servicio, ni endpoint, ni serializador.

Lo que sí existe y funciona es el **ciclo de ejecución**: crear una orden,
asignarle un técnico, moverla por sus estados, recoger evidencias, validarla. Eso
tiene servicio, endpoints, máquina de estados, bitácora y pruebas.

Lo que no existe es **el día anterior**: decidir qué se hace mañana, con quién, en
qué orden, y qué pasa cuando eso cambia.

### Los tres huecos que ordenan todo lo demás

| # | Hueco | Consecuencia |
|---|---|---|
| **1** | **No hay operación de programar.** `programada_para` se escribe **solo al crear la orden** y **ningún código lo modifica después** | No existe "reprogramar". H-05 no puede dispararse |
| **2** | **No hay cuadrilla.** La palabra aparece 13 veces; el modelo, cero | No se puede asignar trabajo a un grupo, solo a personas una por una |
| **3** | **No hay ningún dato para calcular capacidad.** Ni duración, ni complejidad, ni jornada por persona, ni desplazamiento | Toda decisión de "cuánto cabe en un día" sería inventada |

### Y un hallazgo de seguridad que no esperaba encontrar aquí

**Las tablas `campo_*` no tienen RLS. Ninguna.** `campo_orden_trabajo`,
`campo_asignacion_trabajo`, `campo_evento_trabajo`, `campo_work_type`,
`campo_work_type_version`, `campo_evidencia_trabajo` y
`campo_mutacion_idempotente`: **7 tablas, `relrowsecurity = false`, 0 políticas**.

La causa es precisa y está en una línea: `ORG_SCOPED_TABLES`
(`common/rls/__init__.py:34`) lista las cinco tablas `operaciones_*` y **ninguna
`campo_*`**.

> **Esto cambia lo que B-7 resuelve.** A-3.4 dejó dicho que el aislamiento de
> `operaciones_disponibilidad` pasa a dos capas cuando el runtime deje de conectar
> como `postgres`. Para `campo_orden_trabajo` eso **no ocurrirá**: no hay política
> que activar. B-7 no la protege. **La tabla central de M03 tiene una sola capa.**

*(Reportado, no corregido: §33 prohíbe modificar RLS.)*

---

## 1. Estado actual

### Lo que se midió en producción (solo lectura)

```
OrdenTrabajo ................  3      DisponibilidadTecnico ......  0
AsignacionTrabajo ..........  3      ProgramacionSemanal ........  0
EventoTrabajo .............. 12      ProgramacionOrden ..........  0
EvidenciaTrabajo ...........  5      NovedadOperativa ...........  0
WorkType ...................  1      ActividadOperativa .........  0
WorkTypeVersion ............  1      PropuestaSupervisor ........  0
BusinessCalendar ...........  1      Teams ......................  0
BusinessHoliday ............  0      RoutingRule ................  0
Profile ....................  5      Case ...................... 197
```

Las 3 órdenes, en detalle:

| # | estado operativo | validación | `programada_para` | `iniciada_en` | GPS | origen |
|---|---|---|:--:|:--:|:--:|---|
| 1842 | `en_sitio` | `sin_evaluar` | **NULL** | sí | sí | wisphub / ticket / WH-91288 |
| 1843 | `en_sitio` | `sin_evaluar` | **NULL** | sí | sí | wisphub / ticket / WH-91300 |
| 1844 | `completada_campo` | `sin_evaluar` | **NULL** | sí | sí | wisphub / ticket / WH-91311 |

### La regla del §3, aplicada

**Una tabla vacía no significa que la funcionalidad no exista.** Separando las seis
dimensiones, el cuadro cambia de forma:

| Componente | Estructura | Código | Datos | Uso real | Pruebas | Producción |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `OrdenTrabajo` | sí | **sí** | 3 | **sí** | sí | **sí** |
| `AsignacionTrabajo` | sí | **sí** | 3 | **sí** | sí | **sí** |
| `EventoTrabajo` | sí | **sí** | 12 | **sí** | sí | **sí** |
| `DisponibilidadTecnico` | sí | **sí** (A-3.3) | 0 | **no** | sí (27) | **desplegado, sin uso** |
| `ProgramacionSemanal` | sí | **NO** | 0 | no | lectura | **estructura sola** |
| `ProgramacionOrden` | sí | **NO** | 0 | no | lectura | **estructura sola** |
| `NovedadOperativa` | sí | **NO** | 0 | no | lectura | **estructura sola** |

> Las tres últimas son el caso que el §3 describe: **existen de verdad, con RLS y
> constraints, y nadie las escribe.** No están rotas ni son inexistentes: están
> **esperando a M03**.

---

## 2. Inventario de estructuras

| Modelo | Tabla | Escritor real | Endpoint | RLS |
|---|---|---|:--:|:--:|
| `campo.OrdenTrabajo` | `campo_orden_trabajo` | `despacho.crear_orden`, `transiciones.*` | sí | **NO** |
| `campo.AsignacionTrabajo` | `campo_asignacion_trabajo` | `despacho.asignar` | sí | **NO** |
| `campo.EventoTrabajo` | `campo_evento_trabajo` | despacho, transiciones, views | — | **NO** |
| `campo.EvidenciaTrabajo` | `campo_evidencia_trabajo` | `campo/views.py` | sí | **NO** |
| `campo.WorkType` | `campo_work_type` | **solo admin** | no | **NO** |
| `campo.WorkTypeVersion` | `campo_work_type_version` | **solo admin** | no | **NO** |
| `operaciones.DisponibilidadTecnico` | `operaciones_disponibilidad` | `DisponibilidadView` | sí | sí (2) |
| `operaciones.ProgramacionSemanal` | `operaciones_programacion_semanal` | **ninguno** | **no** | sí (2) |
| `operaciones.ProgramacionOrden` | `operaciones_programacion_orden` | **ninguno** | **no** | sí (2) |
| `operaciones.NovedadOperativa` | `operaciones_novedad` | **ninguno** | **no** | sí (2) |
| `business_hours.BusinessCalendar` | `business_calendar` | views propias | sí | sí (2) |
| `common.Teams` | `teams` | CRM genérico | sí | sí (2) |
| `cases.RoutingRule` | `routing_rule` | `cases.routing` | sí | sí |
| materiales / inventario | **no existe** | — | — | — |

**Búsqueda exhaustiva de tablas por nombre** (`%material%`, `%inventar%`,
`%stock%`, `%ruta%`, `%route%`, `%vehic%`, `%cuadrilla%`, `%crew%`, `%capacid%`,
`%jornada%`, `%zona%`, `%zone%`) sobre **todo** el catálogo de producción:

```
[]   -- ninguna coincidencia en ningun esquema
```

---

## 3. Orden de trabajo

### Campos reales (27 columnas, leídas de `information_schema`)

```
created_at, updated_at, id, numero, origen_sistema, origen_tipo, origen_ref,
cliente_nombre, cliente_telefono, cliente_direccion, gps_lat, gps_lng,
diagnostico_previo, datos, revision, estado_operativo, estado_validacion,
programada_para, iniciada_en, completada_campo_en, cerrada_en,
created_by_id, org_id, updated_by_id, tipo_trabajo_version_id, contexto, vuelta
```

**Lo que NO tiene, y el §5 preguntaba:**

| Campo esperado | Estado |
|---|---|
| `prioridad` | **NO EXISTE** en la orden. Existe en `ProgramacionOrden.prioridad` y en `Case.priority` |
| SLA | **NO EXISTE** en la orden. Vive en `Case` (§12) |
| zona | **NO EXISTE** en la orden. Existe en `ProgramacionOrden.zona` y `DisponibilidadTecnico.zona` |
| duración estimada | **NO EXISTE** en ningún lado |
| FK a `Case` | **NO EXISTE**. El vínculo es por texto: `origen_sistema` + `origen_tipo` + `origen_ref` |

### Dos máquinas de estados, no una

**[EXISTENTE EN CÓDIGO]** `campo/services/transiciones.py:19` y `:48`.

```
OPERATIVA  (dónde está el trabajo)

  asignada ──> en_camino ──> en_sitio ──> completada_campo ──> cerrada
     │             │            │                │
     │             │            │                └──> correccion_requerida
     └─────────────┴────────────┴──> cancelada         │
                                                        └──> en_camino / en_sitio

VALIDACIÓN  (si alguien lo dio por bueno)

  sin_evaluar ──> pendiente ──> aprobado
                      ├──> requiere_correccion ──> pendiente
                      └──> requiere_revision ──> aprobado / requiere_correccion

  aprobable: declarado y SIN USO deliberado (el propio código lo dice)
```

### Respuestas del §5

| Pregunta | Respuesta medida |
|---|---|
| ¿Qué estados permiten **programación**? | **Ninguno lo restringe.** `programada_para` no tiene validación de estado — se fija al crear y nadie lo vuelve a tocar |
| ¿Qué estados permiten **asignación**? | Todos salvo `cerrada` y `cancelada` (`despacho.py:162`) |
| ¿Qué estados indican que **ya inició**? | Salir de `asignada`. El propio detector lo razona: *"`estado_operativo = asignada` YA implica que no arrancó: ninguna transición vuelve a ese estado y `iniciada_en` sólo se escribe al salir de él"* (`supervisor.py:340`) |
| ¿Qué estados indican **finalización**? | `cerrada` y `cancelada` — los dos son terminales (`set()` en la tabla) |

### Un detalle semántico que importa para M03

**[MEDIDA]** `estado_operativo` tiene `default = ASIGNADA`, y `crear_orden` **no
recibe estado ni crea ninguna `AsignacionTrabajo`**.

> **Una orden nace "asignada" sin que haya nadie asignado.** No existe un estado
> que signifique *"creada y todavía sin dueño"*. M03 tendrá que decidir si eso se
> corrige o se convive con ello — **es una decisión de negocio, no un bug obvio**:
> cambiarlo mueve la frontera de dos detectores de M09.

---

## 4. Programación semanal

**[MEDIDA]** Estructura completa: `semana_inicio` (lunes), `estado`
(`borrador` → `publicada` → `cerrada`), `publicada_en`, `publicada_por` (FK a
`Profile`), `notas`, `org`. Unique `(org, semana_inicio)`.

**¿Existe realmente una programación semanal, o solo una estructura preparada?**

> **Solo la estructura.** 0 filas, 0 escritores, 0 endpoints. El único acceso es
> `admin.site.register(ProgramacionSemanal)` (`operaciones/admin.py:38`) — y el
> admin es justamente la vía que A-3 descartó: está en `EXEMPT_PATHS`, no fija
> `app.current_org`, y exige `is_staff` (1 de 5 usuarios).

El ciclo `borrador → publicada → cerrada` está **declarado y no implementado**:
no hay función `publicar()` ni `cerrar()`. `publicada_en` y `publicada_por` son
campos que nadie escribe.

M09 **sí la lee**: `_programaciones_sin_publicar` (`supervisor.py:425`) emite señal
cuando un plan lleva demasiado en borrador. Ese detector nunca ha tenido nada que
detectar.

---

## 5. Programación de orden

**[MEDIDA]** Campos: `programacion` (FK), `orden` (FK a `campo.OrdenTrabajo`),
`dia`, `hora_inicio`, `hora_fin`, `zona`, **`prioridad`** (0 = más urgente),
**`secuencia`**, `estado` (`planificada` / `confirmada` / `reprogramada` /
`cancelada`), `org`. Unique `(programacion, orden)`.

> **Buena noticia para el §18: la secuencia ya es representable.** `secuencia` y
> `prioridad` existen, y el help_text es explícito: *"NO es una ruta optimizada:
> es el orden propuesto."*

**Lo que NO tiene:** ninguna FK a técnico ni a cuadrilla. **Quién hace la orden
sale de `AsignacionTrabajo`, no del plan.** Eso significa que el plan semanal
planifica *qué y cuándo*, pero **no *quién***.

### §7 — ¿Están sincronizados `ProgramacionOrden` y `programada_para`?

**No, y no por accidente: por diseño.** El modelo lo dice literalmente
(`operaciones/models.py:400`):

> *"ProgramacionOrden = lo que se PLANIFICÓ el viernes anterior.
> OT.programada_para = lo que RIGE ahora mismo."*

**[MEDIDA] Lo que nada garantiza es que la relación entre ambos sea coherente**,
porque no hay código que las escriba juntas:

```sql
lineas_plan .............................. 0
ot_con_fecha ............................. 0
plan_sin_fecha_en_ot ..................... 0
plan_y_ot_discrepan ...................... 0
```

**Los cuatro ceros no son una confirmación de coherencia: son la ausencia de
datos.** Con 0 líneas de plan, la discrepancia no puede manifestarse todavía.

**La discrepancia no es hipotética — M09 ya construyó el detector.**
`_ordenes_desincronizadas` (`supervisor.py:375`) existe exactamente para *"la orden
SÍ está en un plan publicado, pero `programada_para` está vacío"*. Y
`_ordenes_sin_programar` documenta por qué (`supervisor.py:327`):

> *"Con la condición anterior esa orden disparaba la señal y el Supervisor
> recomendaba programar algo que ya estaba programado. No era hipotético:
> `programada_para` está en 0 de 3 órdenes de producción, así que **el primer plan
> que M03 cargue produce el falso positivo**."*

> **Conclusión del §7:** existe el detector de la discrepancia y no existe la
> operación que la evita. **M03 tiene que escribir las dos cosas en la misma
> transacción, o nacer produciendo el falso positivo que M09 ya previó.**

---

## 6. Asignación

**[MEDIDA]** `AsignacionTrabajo`: `orden`, `profile`, `rol`, `es_principal`,
`asignado_en`. Dos constraints: unique `(orden, profile)` y **unique `(orden)`
where `es_principal = true`** — un solo principal por orden, impuesto por la base.

**¿Una OT puede tener varios técnicos?** **Sí, estructuralmente.** N filas por
orden, cada una con su rol. **En producción, no:**

```
personas por orden:  1  ->  3 ordenes     (ninguna con 2 o mas)
roles:               tecnico_lider, es_principal=true  ->  3
```

### La divergencia de roles que el §8 pedía investigar

**[MEDIDA + EXISTENTE EN CÓDIGO]** Está documentada en el propio modelo
(`campo/models.py:326`):

> *"CATÁLOGO CERRADO (15/09/2026). Antes era texto libre con la lista solo en el
> help_text, y ya había divergido: las 3 asignaciones de producción dicen
> `tecnico_lider`, que no estaba entre los cuatro documentados.*
>
> *`tecnico_lider` se INCLUYE en el catálogo en vez de corregirse: las filas
> existentes son datos de producción y renombrarlas sería reescribir histórico por
> una razón cosmética."*

**Estado hoy:** resuelta. El catálogo es cerrado y tiene 5 valores
(`tecnico`, `tecnico_lider`, `ayudante`, `chofer`, `supervisor`). Las 3 filas de
producción son válidas. **No hay nada que arreglar aquí.**

### Reasignación: existe, y conserva historial

**[MEDIDA]** `despacho.asignar()` (`campo/services/despacho.py:145`) baja el
principal anterior y sube el nuevo **en una transacción**, y escribe un
`EventoTrabajo`:

```python
tipo = "asignacion" if anterior is None else "reasignacion"
datos = {"anterior": ..., "nuevo": ..., "rol": ..., "motivo": ...}
```

Expuesto en `POST /trabajos/<pk>/asignar/`, restringido a `ROLES_GESTION`.

### Una observación medida que no sé explicar del todo

**[MEDIDA]** Los 12 eventos de producción son:

```
datos_actualizados 3 · accion_marcar_en_camino 3 · accion_marcar_llegada 3
evidencia_confirmada 2 · trabajo_completado_campo 1
```

**No hay ni un solo `orden_creada` ni `asignacion`**, y hay 3 órdenes y 3
asignaciones. `crear_orden` y `asignar` **siempre** escriben su evento.

**[HIPÓTESIS — no verificada]** Las órdenes y asignaciones se crearon por una vía
que no pasa por el servicio. Dos candidatas conocidas: el admin de Django, y
`campo/management/commands/seed_campo_demo.py`, que **crea `OrdenTrabajo` y
`AsignacionTrabajo` directo por ORM y no escribe ningún evento** (verificado: el
comando no menciona `EventoTrabajo`). No tengo evidencia para elegir entre las dos
y **no la invento**.

> **Lo que sí se puede afirmar:** la bitácora tiene un hueco en el nacimiento de
> las 3 órdenes vivas, y el resto de su ciclo sí quedó registrado.

---

## 7. Cuadrillas

# GAP

**[MEDIDA]** Búsqueda exhaustiva de `cuadrilla|crew|Cuadrilla|Crew` en todo el
código: **13 coincidencias, ninguna es un modelo.** Son docstrings, un
`verbose_name`, y `ROLES_CUADRILLA` (que es un catálogo de roles, no una entidad).

Búsqueda de tablas `%cuadrilla%` / `%crew%` en producción: **ninguna.**

### `Teams` no es una cuadrilla, y conviene decirlo antes de que alguien lo asuma

**[MEDIDA]** `common.Teams` (`common/models.py:774`) tiene exactamente cuatro
campos: `name`, `description`, `users` (M2M a `Profile`), `org`.

| ¿Tiene…? | |
|---|---|
| técnico líder | **no** |
| vehículo | **no** |
| zona | **no** |
| disponibilidad | **no** |
| ¿se usa? | **no — 0 filas en producción** |

Es el equipo genérico del CRM, pensado para repartir *casos*, no para mandar gente
a la calle.

> **Hoy "cuadrilla" = el conjunto de filas de `AsignacionTrabajo` que comparten
> `orden`.** Es una cuadrilla *por orden*, efímera, que no existe antes de la
> orden ni sobrevive a ella. No se puede decir "la cuadrilla 3 trabaja el martes"
> porque la cuadrilla 3 no existe hasta que hay una orden que la nombre.

**NO se crea en M03-A** (§9, §33). Queda como decisión de negocio: ¿la cuadrilla
es estable (una entidad con miembros, vehículo y zona) o sigue siendo ad-hoc por
orden?

---

## 8. Disponibilidad

**[MEDIDA]** `DisponibilidadTecnico`, implementado en A-3.3 y validado en A-3.4
(31 PASS / 0 FAIL). Aporta: `profile`, `fecha`, `hora_inicio`, `hora_fin`,
`disponible`, `motivo`, `zona`.

**0 filas en producción.** Y no hay ningún perfil `SUPERVISOR` para cargarlas
(`{ADMIN: 1, USER: 4}`).

### Disponibilidad ≠ capacidad — y el propio modelo lo dice

**[EXISTENTE EN CÓDIGO]** `operaciones/models.py:286`:

> *"Un número de 'capacidad' depende de la disponibilidad, de la carga ya
> asignada, de la duración estimada del tipo de trabajo, de la zona y de los
> bloqueos. Guardarlo es garantizar que quede viejo la próxima vez que cualquiera
> de esos cinco cambie."*

Una franja `08:00–17:00 disponible` dice **que la persona puede trabajar**. No dice
cuántas órdenes caben en ella — para eso hacen falta los otros cuatro factores, y
**ninguno existe** (§9).

---

## 9. Capacidad

# GAP DE NEGOCIO — no hay con qué calcularla

| Parámetro | Existe | Datos | Fuente | Utilizable M03 | GAP |
|---|---|---|---|:--:|---|
| **disponibilidad** | **SÍ** | 0 filas | `DisponibilidadTecnico` | **sí** | faltan datos, no estructura |
| **jornada (empresa)** | **SÍ** | 1 calendario | `BusinessCalendar` | **sí** | tz UTC, 0 festivos (§11) |
| jornada (por persona) | PARCIAL | 0 filas | `DisponibilidadTecnico.hora_*` | sí | ninguna franja cargada |
| **duración de trabajo** | **NO EXISTE** | — | — | **no** | **decisión de negocio** |
| **complejidad** | **NO EXISTE** | — | — | **no** | **decisión de negocio** |
| **productividad** | **NO EXISTE** | — | — | **no** | **decisión de negocio** |
| **órdenes por técnico/día** | **NO EXISTE** | — | — | **no** | **decisión de negocio** |
| **desplazamiento** | **NO EXISTE** | — | — | **no** | **decisión de negocio** |
| ubicación | **SÍ** | 3/3 con GPS | `OrdenTrabajo.gps_lat/lng` | **sí** | — |
| dirección | **SÍ** | 3/3 | `cliente_direccion` | sí | texto libre, sin normalizar |
| zona | PARCIAL | 0 | `ProgramacionOrden.zona`, `DisponibilidadTecnico.zona` | sí | **texto libre, sin catálogo** |
| **SLA** | **SÍ** | 197/197 | `Case.sla_*` | **sí** | vive en Case, no en la orden |
| **prioridad** | PARCIAL | 197 todos `Normal` | `Case.priority`, `ProgramacionOrden.prioridad` | limitado | **sin varianza: no discrimina** |
| **materiales** | **NO EXISTE** | — | — | **no** | **estructura completa ausente** |
| bloqueos | ESTRUCTURA | 0 filas | `NovedadOperativa` (`bloqueo`) | sí | sin escritor |
| dependencia | ESTRUCTURA | 0 filas | `NovedadOperativa` (`dependencia`) | sí | sin escritor |
| **técnico** | **SÍ** | 3 | `AsignacionTrabajo` | **sí** | 1 por orden en la práctica |
| **cuadrilla** | **NO EXISTE** | — | — | **no** | §7 |

**No se inventó ningún valor** (§11, §32): ni duración estándar, ni productividad,
ni puntos de complejidad, ni órdenes por técnico.

---

## 10. WorkType / WorkTypeVersion

**[MEDIDA]** Columnas reales de `campo_work_type_version`:

```
id, work_type_id, version, schema_version, estado, esquema, schema_hash,
publicada_en, created_at, updated_at, created_by_id, updated_by_id
```

Y el contenido del único esquema en producción (`ftth_instalacion` v1, publicada)
tiene exactamente **tres claves**:

```
pasos        2 pasos  ("Parámetros de Fibra y ONT", "Inspección Visual y Evidencias")
campos       2 campos (serial_ont: texto; potencia_rx: decimal, rango -28.0 a -8.0)
evidencias   2 fotos  (ONT instalada obligatoria; fachada opcional)
```

| Lo que M03 necesitaría | ¿Está? |
|---|:--:|
| duración | **NO** |
| complejidad | **NO** |
| recursos | **NO** |
| **requisitos** | **SÍ** — `campos` + `evidencias`, pero son *qué hay que entregar*, no *qué hace falta para ir* |
| prioridad | **NO** |
| SLA | **NO** |
| materiales | **NO** |
| habilidades | **NO** |

> **`WorkTypeVersion` es el sitio natural para la duración estimada** — es por tipo
> de trabajo, está versionado e inmutable, y ya se congela en cada orden. Pero
> **agregar el campo es una migración y el valor es una decisión de negocio**: las
> dos cosas están fuera de M03-A.

---

## 11. Jornada y calendario

**[MEDIDA]** Un solo `BusinessCalendar`, `is_default = true`:

```
timezone .......... UTC
lunes a viernes ... 09:00 - 17:00
sábado ............ null / null      (cerrado)
domingo ........... null / null      (cerrado)
festivos .......... 0
```

| Pregunta del §13 | Respuesta |
|---|---|
| ¿Cómo se interpreta la jornada hoy? | Solo la usa el **motor de SLA** de `cases`. Nada de campo la consulta |
| ¿Jornada empresarial configurable? | **Sí**, por organización, con endpoints propios |
| ¿Horario por técnico? | **Solo vía `DisponibilidadTecnico`** (A-3.3), y hay 0 franjas |
| ¿Horario por organización? | **Sí** |
| ¿Excepciones? | `BusinessHoliday` existe; **0 filas** |

> **No se convierte UTC a Colombia** (§13). Se registra el hecho: el calendario
> dice UTC y 09:00–17:00 UTC son **04:00–12:00 en Colombia**. Si M03 programara
> contra ese calendario tal como está, programaría de madrugada. **Es una decisión
> de negocio pendiente**, no un error que M03-A deba arreglar.

---

## 12. SLA

**[MEDIDA]** El motor existe, está poblado y **no se duplica**:

```
Case ............................ 197 filas
sla_first_response_hours ........ 197/197   (todas: 8 h)
sla_resolution_hours ............ 197/197   (todas: 48 h)
first_response_at ............... 4/197
resolved_at ..................... 69/197
priority ........................ 197 = "Normal"   (sin varianza)
estados ......................... New 116 · Closed 69 · Assigned 12
```

Motor: `cases/models.py:446-501` — `_sla_calendar`, `_sla_deadline`,
`is_sla_first_response_breached`, `resolution_sla_deadline`. Usa `BusinessCalendar`.

### El problema para M03: la orden no sabe de qué caso viene

**[MEDIDA]** `OrdenTrabajo` **no tiene FK a `Case`**. El vínculo es textual
(`origen_sistema` + `origen_tipo` + `origen_ref`), y en las 3 órdenes reales vale
`wisphub` / `ticket` / `WH-91288` — **no apunta a un `Case` en absoluto**.

> **Para que M03 pueda priorizar por SLA hace falta que la orden sepa a qué caso
> pertenece.** Hoy no lo sabe. Esto **no se resuelve en M03-A**: es un cambio de
> modelo (§33).
>
> **Y la regla del §14 se respeta:** M03 **consume** `Case.sla_*`, no crea un
> segundo motor. Lo que falta es el puente, no el cálculo.

**[MEDIDA]** Además, `priority` no discrimina hoy: los 197 casos valen `Normal`.
Priorizar por ese campo daría un empate universal.

---

## 13. Novedades

**[MEDIDA]** `NovedadOperativa` tiene los 8 tipos que el §15 enumera, y además los
dos campos que hacen auditable una reprogramación:

```python
programada_anterior = DateTimeField(null=True)
programada_nueva    = DateTimeField(null=True)
```

Y `registrada_por` (FK a `Profile`), `orden`, `actividad`, `profile`, `descripcion`.

**[EXISTENTE EN CÓDIGO]** La ausencia de `incumplimiento_de_persona` es deliberada
y está explicada en el modelo: *"con los datos de hoy no hay forma de distinguir
ninguna de esas de un incumplimiento — y el costo de equivocarse lo paga una
persona real."*

**Cómo afectaría cada tipo a la programación** — clasificado, sin inventar reglas:

| Tipo | Efecto esperable | Estado |
|---|---|---|
| `ausencia` | libera la carga del día de esa persona | **[DECISIÓN DE NEGOCIO]** ¿reasigna o reprograma? |
| `bloqueo` | la orden no avanza | **[DECISIÓN]** ¿sale del día o se queda? |
| `falta_material` | la orden no puede ejecutarse | **[GAP]** no hay materiales (§17) |
| `dependencia` | espera otra orden | **[GAP]** no hay FK orden→orden |
| `reprogramacion` | cambia la fecha | **[GAP]** no hay operación (§14) |
| `cambio_de_prioridad` | reordena la secuencia | **[DECISIÓN]** |
| `dato_incompleto` | no se puede despachar | **[DECISIÓN]** |
| `demora_sin_causa_registrada` | se registra el hecho | listo |

**Escritor: ninguno.** Solo `admin.site.register(NovedadOperativa)`.

---

## 14. Reprogramación

# La estructura existe. La operación NO.

**[MEDIDA]** Búsqueda de todos los sitios que escriben `programada_para`:

| Sitio | Qué hace |
|---|---|
| `campo/services/despacho.py:108` | lo fija **al crear** la orden |
| `campo/despacho_views.py:135` | lo pasa desde el cuerpo del POST de creación |
| `campo/serializers.py:63,117,200` | lo **lee** / lo declara como entrada de creación |
| `campo/admin.py:139` | lo muestra en el panel |

**Ninguno lo modifica después de crear la orden.**

| Operación del §16 | ¿Existe? |
|---|:--:|
| cambiar fecha | **NO** |
| cambiar horario | **NO** |
| cambiar técnico | **SÍ** — `despacho.asignar` |
| cambiar cuadrilla | **NO** (no hay cuadrilla) |
| devolver a programación | **NO** |
| preservar histórico | **estructura sí** (`NovedadOperativa`), **escritor no** |

> **M03 tiene todo lo que necesita para preservar una reprogramación y ninguna
> forma de producirla.** Los campos `programada_anterior` / `programada_nueva`,
> `registrada_por` y `descripcion` son exactamente los cinco datos que el §16 pide
> (valor anterior, valor nuevo, fecha/hora vía `created_at`, actor, motivo).
>
> **No es un GAP de estructura: es un GAP de operación.**

---

## 15. Redistribución

**[MEDIDA]** Separando los dos conceptos, como pide el §17:

| | ¿Existe? | Evidencia |
|---|:--:|---|
| **Reasignación** (quitar a A, poner a B) | **SÍ** | `despacho.asignar()`, transaccional, con `EventoTrabajo` tipo `reasignacion` y `{anterior, nuevo, rol, motivo}` |
| **Redistribución de carga** (mover N órdenes para equilibrar) | **NO** | no hay noción de carga; requiere capacidad (§9), que no existe |

La reasignación conserva historial de verdad: el evento es append-only y guarda el
perfil anterior y el nuevo.

> La redistribución **no es una reasignación repetida**: necesita saber *cuánta*
> carga tiene cada persona, y eso depende de duración y capacidad. **Bloqueada por
> el §9.**

---

## 16. Rutas y secuencia

### `RoutingRule` no tiene que ver con rutas

**[MEDIDA]** `cases/models.py:1023` — es **asignación automática de casos**:
estrategias `round_robin`, `least_busy`, `direct`, `by_team`, con condiciones sobre
`priority`, `case_type`, `account`, `tags`. **0 filas.**

> "Routing" aquí significa *encaminar un caso a un agente*, no *trazar un
> recorrido*. **No sirve para M03.**

### Lo que sí hay para secuencia

| Pregunta del §18 | Respuesta |
|---|---|
| **¿Podemos representar una secuencia?** | **SÍ** — `ProgramacionOrden.secuencia` + `prioridad` |
| **¿Podemos ordenar las OTs de una jornada?** | **SÍ** — `Meta.ordering = ["dia", "secuencia"]` |
| ¿Existe origen/destino? | **NO** — no hay punto de partida ni base/bodega |
| **¿Ubicación confiable?** | **SÍ** — `gps_lat`/`gps_lng` poblados en **3 de 3**, más dirección |
| ¿Zona? | **PARCIAL** — campo existe en `ProgramacionOrden` y `DisponibilidadTecnico`, **texto libre, sin catálogo, 0 datos** |
| ¿Tiempo de desplazamiento? | **NO** — ninguna estructura, ninguna integración |

> **La primera versión de M03 puede hacer SECUENCIA sin nada nuevo.** La
> optimización de ruta necesita tiempo de desplazamiento, que no existe.
> **No se decide aquí** (§18, §32).

---

## 17. Materiales

# GAP TOTAL

**[MEDIDA]** Ningún modelo, ninguna tabla, ningún campo:

- búsqueda de `class .*Material|Inventario|Stock` en el código: **0**
- búsqueda de tablas `%material%`, `%inventar%`, `%stock%` en producción: **0**

Lo único que existe es el **tipo de novedad** `falta_material` — un hueco con
nombre, que hoy no se puede llenar ni verificar.

El modelo operativo definido (caja preparada a las 08:00 → ejecución → conteo
físico a las 17:00 → esperado vs. físico) **no tiene ni una sola de sus piezas**:
no hay catálogo de materiales, ni entrega, ni consumo, ni devolución, ni conteo.

---

## 18. Conflictos

| Conflicto | ¿Datos? | ¿Regla? | ¿Detector? | ¿Historial? |
|---|:--:|:--:|:--:|:--:|
| técnico ausente + OT asignada | **no** (0 franjas, 0 programadas) | sí | **SÍ — H-05** `_ordenes_en_riesgo` | `PropuestaSupervisor` |
| OT sin técnico | sí | sí | **parcial** — `_actividades_sin_responsable` cubre actividades, **no órdenes** | — |
| técnico con varias OTs a la vez | **no** | **no** | **NO** | — |
| OT fuera de jornada | parcial (calendario UTC) | **no** | **NO** | — |
| OT que amenaza SLA | sí (en `Case`) | sí (en `Case`) | **NO para órdenes** — falta el puente (§12) | — |
| **OT sin programación** | sí | sí | **SÍ** — `_ordenes_sin_programar` | `PropuestaSupervisor` |
| **plan semanal sin publicar** | **no** (0 planes) | sí | **SÍ** — `_programaciones_sin_publicar` | `PropuestaSupervisor` |
| **plan y `programada_para` discrepan** | **no** | sí | **SÍ** — `_ordenes_desincronizadas` | `PropuestaSupervisor` |
| asignación incompatible | **no** | **no** | **NO** | — |
| dependencia pendiente | estructura | sí | **SÍ** — `_dependencias_pendientes` (actividades) | `PropuestaSupervisor` |
| material faltante | **NO** | **no** | **NO** | — |

> **Cuatro de los diez detectores de M09 apuntan a M03 y nunca han tenido nada que
> detectar.** No están rotos: están esperando datos que nadie produce.

**No se crearon detectores** (§19).

---

## 19. Preparación de jornada

Qué pieza del flujo existe hoy:

```
08:00  programación ......... ESTRUCTURA SIN ESCRITOR    ProgramacionSemanal/Orden
       ruta/secuencia ....... ESTRUCTURA LISTA           ProgramacionOrden.secuencia
       órdenes .............. EXISTE Y FUNCIONA          OrdenTrabajo + endpoints
       materiales ........... NO EXISTE                  -
       cuadrilla sale ....... NO EXISTE (hay personas)   AsignacionTrabajo

durante el día
       novedades ............ ESTRUCTURA SIN ESCRITOR    NovedadOperativa
       bloqueos ............. ESTRUCTURA SIN ESCRITOR    NovedadOperativa.bloqueo
       reprogramaciones ..... NO EXISTE LA OPERACIÓN     §14
       redistribuciones ..... NO EXISTE                  §15

cierre
       ejecución ............ EXISTE Y FUNCIONA          transiciones + evidencias
       validación ........... EXISTE Y FUNCIONA          2ª máquina de estados
       conteo de material ... NO EXISTE                  §17
```

**El técnico ya tiene su app**: `BootstrapView` le entrega usuario, organización,
capacidades y hora del servidor; `TrabajosListView` sus trabajos. **Lo que no
recibe es un plan del día**, porque no hay plan.

---

## 20. Mapa de datos

```
   Case (197)                          [ NO HAY FK ]
     │  origen_sistema/origen_tipo/origen_ref   ← solo texto, y hoy apunta a WispHub
     ▼
   OrdenTrabajo (3)  ──1:N──> AsignacionTrabajo (3)  ──N:1──> Profile (5)
     │  FK: org, tipo_trabajo_version                unique(orden) where es_principal
     │
     ├──1:N──> EventoTrabajo (12)        bitácora append-only
     ├──1:N──> EvidenciaTrabajo (5)
     ├──1:N──> ProgramacionOrden (0) ──N:1──> ProgramacionSemanal (0)
     │            unique(programacion, orden)              unique(org, semana_inicio)
     └──1:N──> NovedadOperativa (0)
                  programada_anterior / programada_nueva

   DisponibilidadTecnico (0) ──N:1──> Profile        index(org, fecha, profile)
   BusinessCalendar (1) ──1:N──> BusinessHoliday (0)
   Teams (0) ──M2M──> Profile        (CRM genérico, no cuadrilla)
   RoutingRule (0)                   (asignación de casos, no rutas)
```

| Relación | Modelo | FK | Cardinalidad | Estado |
|---|---|---|---|---|
| Case → Orden | — | **ninguna** | — | **GAP: vínculo textual** |
| Orden → Asignación | `AsignacionTrabajo.orden` | sí | 1:N (1 principal) | **funciona** |
| Orden → Programación | `ProgramacionOrden.orden` | sí | 1:N | **sin datos ni escritor** |
| Programación → Semanal | `ProgramacionOrden.programacion` | sí | N:1 | **sin datos ni escritor** |
| Orden → Novedad | `NovedadOperativa.orden` | sí (nullable) | 1:N | **sin datos ni escritor** |
| Orden → Evento | `EventoTrabajo.orden` | sí | 1:N | **funciona** |
| Disponibilidad → Profile | `DisponibilidadTecnico.profile` | sí | N:1 | **listo, sin datos** |
| Programación → técnico | — | **ninguna** | — | **GAP: el plan no dice quién** |

---

## 21. Dependencias de H-05

**[MEDIDA]** `_ordenes_en_riesgo` (`supervisor.py:463`) exige **cuatro** cosas:

```python
OrdenTrabajo.objects.filter(
    org=org,
    programada_para__isnull=False,          # (1)
    estado_operativo=OrdenTrabajo.ASIGNADA, # (2)
).prefetch_related("asignaciones")
  → o.tecnico_principal is not None         # (3)
  → DisponibilidadTecnico.filter(
        profile=principal,
        fecha=programada_para.date(),
        disponible=False).first()           # (4)
```

| # | Requisito | Producción hoy | Quién lo debe producir |
|:--:|---|:--:|---|
| 1 | `programada_para` no nulo | **0 de 3** | **M03** |
| 2 | `estado_operativo = asignada` | **0 de 3** | **M03** (ver abajo) |
| 3 | técnico principal | **3 de 3** ✔ | ya está |
| 4 | ausencia declarada ese día | **0 filas** | **A-3.3** ✔ + un `SUPERVISOR` que la cargue |

### El matiz del requisito 2, que no es un defecto

Las 3 órdenes están en `en_sitio` (2) y `completada_campo` (1): **ya pasaron de
`asignada`**. Eso es correcto — *una orden que el técnico ya empezó no está "en
riesgo por una ausencia"*: la persona apareció.

> **H-05 solo puede dispararse en la ventana entre asignar y arrancar.** Para
> validarla end-to-end hace falta **una orden programada a futuro, todavía sin
> iniciar, cuyo técnico esté declarado ausente ese día**. Ninguna de esas tres
> condiciones la puede producir A-3: las tres son M03.

### Lo mínimo que M03 debe entregar para desbloquear H-05

1. Escribir `programada_para` **con una fecha futura** (una operación de programar).
2. Que la orden **permanezca en `asignada`** hasta esa fecha — ya ocurre solo.
3. Escribir la línea de plan **en la misma transacción**, o `_ordenes_sin_programar`
   y `_ordenes_desincronizadas` empiezan a emitir falsos positivos que M09 ya
   documentó.

**No se modificó H-05** (§25, §33).

---

## 22. Seguridad

### El hallazgo: `campo_*` no tiene RLS

**[MEDIDA]** Estado real en producción:

| Tabla | RLS enabled | forced | políticas |
|---|:--:|:--:|:--:|
| `campo_orden_trabajo` | **false** | **false** | **0** |
| `campo_asignacion_trabajo` | **false** | **false** | **0** |
| `campo_evento_trabajo` | **false** | **false** | **0** |
| `campo_evidencia_trabajo` | **false** | **false** | **0** |
| `campo_work_type` | **false** | **false** | **0** |
| `campo_work_type_version` | **false** | **false** | **0** |
| `campo_mutacion_idempotente` | **false** | **false** | **0** |
| `operaciones_disponibilidad` | true | true | 2 |
| `operaciones_programacion_semanal` | true | true | 2 |
| `operaciones_programacion_orden` | true | true | 2 |
| `operaciones_novedad` | true | true | 2 |
| `business_calendar` | true | true | 2 |
| `teams` | true | true | 2 |

```sql
select count(*) from pg_policy p join pg_class c on c.oid = p.polrelid
where c.relname like 'campo_%';
→ 0
```

**La causa, en una línea:** `ORG_SCOPED_TABLES` (`common/rls/__init__.py:34-151`)
enumera las cinco tablas `operaciones_*` y **ninguna `campo_*`**. La migración
`0028_restamp_rls_policies` recorre esa lista; lo que no está en la lista, no se
estampa. No es un fallo de la migración: es una omisión del registro.

### Qué significa, exactamente

**[MEDIDA]** El aislamiento de `campo_*` lo da **solo la aplicación**, y esa capa
sí existe y está probada: `campo/views.py` filtra por `org=request.org` en cada
consulta, `misma_organizacion` devuelve 404 y no 403, y hay una suite dedicada
(`campo/tests/test_aislamiento_tenant_404.py`).

> **Pero A-3.4 dejó dicho que B-7 convierte el aislamiento de disponibilidad en dos
> capas. Para `campo_orden_trabajo` eso no va a pasar: no hay política que
> activar.** Después de B-7, la tabla central de M03 seguirá teniendo una sola
> capa.
>
> **Esto no bloquea M03**, pero cambia qué hay que decir sobre su seguridad: la
> orden de trabajo no está protegida por la base, ni lo estará por B-7.

**Reportado, no corregido** (§26, §33): no se modificó RLS, ni roles, ni permisos,
ni `ORG_SCOPED_TABLES`.

### Actor y auditoría

| | Estado |
|---|---|
| `organization_id` | presente en todas las tablas de M03 |
| permisos de despacho | `ROLES_GESTION` = `{ADMIN, SUPERVISOR, OPERACIONES}` |
| actor en asignación | `EventoTrabajo.profile` + `datos.anterior/nuevo/motivo` |
| actor en programación | **no existe la operación** |
| `created_by` / `updated_by` | automáticos vía `BaseModel` + `crum` |
| runtime | conecta como `postgres`, `rolbypassrls = true` — **B-7 pendiente** |

---

## 23. GAPs

### Críticos — bloquean M03

| # | GAP | Tipo |
|:--:|---|---|
| **G-1** | **No existe operación de programar ni reprogramar.** `programada_para` solo se escribe al crear | **operación** |
| **G-2** | **`ProgramacionSemanal` / `ProgramacionOrden` / `NovedadOperativa` no tienen escritor** — solo el admin, que A-3 ya descartó | **operación** |
| **G-3** | **No hay ningún dato para calcular capacidad**: sin duración, complejidad, productividad ni desplazamiento | **decisión de negocio** |
| **G-4** | **No existe la cuadrilla como entidad.** `Teams` no lo es (0 filas, sin líder, vehículo ni zona) | **modelo + negocio** |

### Importantes — limitan el alcance

| # | GAP | Tipo |
|:--:|---|---|
| G-5 | **La orden no tiene FK a `Case`**: no puede heredar SLA ni prioridad | modelo |
| G-6 | **Materiales: nada en absoluto** — 0 tablas, 0 campos | modelo + negocio |
| G-7 | **Calendario en UTC**, 09:00–17:00 = 04:00–12:00 Colombia; 0 festivos | **decisión de negocio** |
| G-8 | **`priority` sin varianza**: los 197 casos son `Normal` | datos |
| G-9 | **Zona es texto libre sin catálogo**, en dos tablas distintas | modelo + negocio |
| G-10 | **Sin tiempo de desplazamiento**: la secuencia es posible, la optimización no | negocio |
| G-11 | **El plan no dice quién**: `ProgramacionOrden` no tiene FK a técnico | modelo |
| G-12 | **`campo_*` sin RLS** (7 tablas); B-7 no lo resuelve | **seguridad** |

### Observados

| # | Observación |
|:--:|---|
| G-13 | Una orden nace en `asignada` **sin nadie asignado** |
| G-14 | `estado_validacion = aprobable` declarado y sin uso, a propósito |
| G-15 | 3 órdenes y 3 asignaciones **sin sus eventos de nacimiento** — *[HIPÓTESIS]* creadas fuera del servicio |
| G-16 | No existe perfil `SUPERVISOR` en producción (`{ADMIN: 1, USER: 4}`) |

---

## 24. Decisiones de negocio requeridas

**Ninguna se toma aquí** (§32).

| # | Decisión | Bloquea |
|:--:|---|---|
| **D-1** | **¿La cuadrilla es una entidad estable** (miembros, líder, vehículo, zona) **o sigue siendo ad-hoc por orden?** | G-4, asignación, capacidad |
| **D-2** | **¿Cuánto dura cada tipo de trabajo?** Sin esto no hay capacidad | G-3, todo cálculo de carga |
| **D-3** | **¿Cuál es la jornada real?** El calendario dice UTC 09:00–17:00 | G-7, toda programación |
| **D-4** | **¿Cuántas órdenes caben en un día por técnico?** ¿O se deriva de D-2? | G-3 |
| **D-5** | **¿Qué es una zona?** ¿Catálogo, o el `router` de WispHub? | G-9, rutas |
| **D-6** | **¿Quién programa?** ¿El mismo Supervisor de Operaciones de A-3.2? | permisos de M03 |
| **D-7** | **¿Qué hace el sistema cuando una ausencia choca con una orden programada?** ¿Reasigna, reprograma, o solo avisa? | H-05, novedades |
| **D-8** | **¿La programación es obligatoria?** ¿Puede existir una orden sin plan? | G-1, detectores M09 |
| **D-9** | **¿Se gestionan materiales en este sistema** o en otro? | G-6 |
| **D-10** | **¿Secuencia basta, o hace falta ruta optimizada?** | G-10 |
| **D-11** | **¿Debe la orden heredar SLA del caso?** Si sí, hace falta el vínculo | G-5 |

---

## 25. Propuesta de implementación futura

**Diseño, no compromiso.** El orden sale de las dependencias medidas, no de una
preferencia.

### El principio que ordena todo

> **Lo que no se puede medir, no se programa todavía.** M03 puede entregar valor
> real **sin resolver capacidad**, que es el GAP más caro y el único que depende
> por completo de decisiones que nadie ha tomado.

### Orden propuesto

**M03-B — Programar, y nada más** *(no necesita ninguna decisión de negocio nueva)*

Una operación que, **en una sola transacción**, escribe `ProgramacionOrden` **y**
`OrdenTrabajo.programada_para`. Eso solo:

- desbloquea H-05 (los requisitos 1 y 2 del §21);
- apaga el falso positivo que M09 previó;
- da su primer dato real a tres detectores que nunca lo tuvieron;
- reutiliza `ProgramacionSemanal` y `ProgramacionOrden` **tal como están** — sin
  modelo nuevo, sin migración.

Requiere decidir **D-6** (quién programa) y **D-8** (si es obligatoria).

**M03-C — Publicar el plan semanal**
`borrador → publicada → cerrada`, con `publicada_en` y `publicada_por`, que ya
existen. Da sentido a `_programaciones_sin_publicar`.

**M03-D — Reprogramar con historial**
Cambiar la fecha escribiendo `NovedadOperativa` con `programada_anterior` y
`programada_nueva` en la misma transacción. La estructura ya guarda los cinco datos
que el §16 exige. Requiere **D-7**.

**M03-E — Secuencia de jornada**
Ordenar el día con `secuencia` y `prioridad`, que ya existen. **Sin optimización de
ruta** (G-10). Entrega al técnico un plan del día en `BootstrapView`.

**M03-F — Cuadrilla** *(bloqueado por D-1)*
Solo si la decisión es "entidad estable". Si es "ad-hoc por orden", **no se
construye nada** y `AsignacionTrabajo` ya alcanza.

**M03-G — Capacidad** *(bloqueado por D-2, D-3, D-4)*
El último, no el primero. Sin duración no hay carga, y sin carga no hay
redistribución (§15).

### Fuera del camino de M03, pero en su camino

| | Qué | Por qué |
|---|---|---|
| **B-7** | runtime fuera de `postgres` | sin él ninguna RLS es efectiva |
| **G-12** | agregar `campo_*` a `ORG_SCOPED_TABLES` | **B-7 no lo resuelve solo** |
| **G-16** | cargar un perfil `SUPERVISOR` | sin él, A-3.3 no tiene quien la use |
| **G-5** | vínculo orden ↔ caso | sin él M03 no puede priorizar por SLA |

---

## TABLA PRINCIPAL (§31)

| Componente | Existe | Código | Datos | Producción | Reutilizable | Falta |
|---|:--:|:--:|:--:|:--:|:--:|---|
| **OrdenTrabajo** | sí | **sí** | 3 | **en uso** | **sí** | prioridad, SLA, zona, duración, FK a Case |
| **AsignacionTrabajo** | sí | **sí** | 3 | **en uso** | **sí** | nada para asignar; sí para cuadrilla |
| **EventoTrabajo** | sí | **sí** | 12 | **en uso** | **sí** | eventos de programación |
| **DisponibilidadTecnico** | sí | **sí** | **0** | desplegado | **sí** | datos + un `SUPERVISOR` |
| **ProgramacionSemanal** | sí | **NO** | **0** | tabla sola | **sí** | **publicar / cerrar** |
| **ProgramacionOrden** | sí | **NO** | **0** | tabla sola | **sí** | **escritor + FK a técnico** |
| **NovedadOperativa** | sí | **NO** | **0** | tabla sola | **sí** | **escritor** |
| **WorkType** | sí | parcial | 1 | en uso | **sí** | — |
| **WorkTypeVersion** | sí | parcial | 1 | en uso | **sí** | **duración, complejidad, materiales** |
| **BusinessCalendar** | sí | **sí** | 1 | en uso | **sí** | **zona horaria real, festivos** |
| **Teams** | sí | genérico | **0** | sin uso | **NO** | no es una cuadrilla |
| **RoutingRule** | sí | **sí** | **0** | sin uso | **NO** | no es ruta: es asignación de casos |
| **materiales / inventario** | **NO** | **NO** | — | **NO** | — | **todo** |
| **SLA** | sí | **sí** | 197 | **en uso** | **sí** | **puente orden ↔ caso** |

---

## CRITERIO DE SALIDA (§34) — las 14 respuestas

| # | Pregunta | Respuesta con evidencia |
|:--:|---|---|
| 1 | **¿Cómo se representa una OT?** | `campo_orden_trabajo`, 27 columnas, dos máquinas de estados. Sin prioridad, SLA, zona ni duración |
| 2 | **¿Cómo se programa?** | **No se programa.** `programada_para` solo al crear; `ProgramacionSemanal/Orden` sin escritor |
| 3 | **¿Cómo se asigna?** | `despacho.asignar()` → `POST /trabajos/<pk>/asignar/`, `ROLES_GESTION`, un principal por orden, con evento |
| 4 | **¿Existe cuadrilla?** | **NO.** Solo `ROLES_CUADRILLA` dentro de `AsignacionTrabajo`. `Teams` ≠ cuadrilla, 0 filas |
| 5 | **¿Cómo se representa disponibilidad?** | `DisponibilidadTecnico` (A-3.3, validada en A-3.4). 0 filas |
| 6 | **¿Se puede calcular capacidad?** | **NO.** Faltan duración, complejidad, productividad y desplazamiento |
| 7 | **¿`ProgramacionOrden` vs `programada_para`?** | **Distintos por diseño, nada los sincroniza.** M09 ya tiene el detector de la discrepancia; con 0 filas aún no se manifiesta |
| 8 | **¿Cómo se preserva una reprogramación?** | **Estructura sí** (`programada_anterior/nueva`, `registrada_por`), **operación no** |
| 9 | **¿Cómo se preserva una redistribución?** | **Reasignación sí**, con historial en `EventoTrabajo`. **Redistribución de carga no** |
| 10 | **¿Datos para rutas/secuencia?** | **Secuencia: sí** (`secuencia`, `prioridad`, GPS 3/3). **Ruta: no** (sin desplazamiento) |
| 11 | **¿Datos para materiales?** | **Ninguno.** 0 modelos, 0 tablas |
| 12 | **¿Qué necesita H-05?** | Una orden **programada a futuro**, **aún en `asignada`**, con principal y ausencia declarada. Los tres primeros son M03 |
| 13 | **¿Qué es técnico y qué es negocio?** | 12 GAPs técnicos (§23) vs. 11 decisiones de negocio (§24) |
| 14 | **¿Qué primero?** | **M03-B: programar en una transacción.** Desbloquea H-05 sin modelo nuevo ni decisión pendiente |

---

## Conformidad con las prohibiciones (§33)

```
código creado ........... 0        modelos creados .......... 0
migraciones ............. 0        endpoints creados ........ 0
tablas creadas .......... 0        serializers modificados .. 0
H-05 modificado ......... no       supervisor.py ............ no
DisponibilidadTecnico ... no       Programacion* ............ no
AsignacionTrabajo ....... no       WorkTypeVersion .......... no
RLS modificada .......... no       roles .................... no
B-7 ..................... sin cambios
producción .............. SOLO LECTURA (read_only = True)
commit .................. no
```

Producción se consultó únicamente con `SELECT`, sobre una conexión marcada
`read_only = True` a nivel de sesión. **No se creó ningún dato sintético**: no hizo
falta entorno de prueba (§28), porque toda la auditoría se resolvió leyendo código,
constraints y datos existentes.
