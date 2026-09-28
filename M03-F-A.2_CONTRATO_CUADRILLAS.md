# M03-F-A.2 — Contrato funcional y técnico de cuadrillas

**Fecha:** 2026-09-18
**Alcance:** auditoría + diseño. **Sin implementar.**
**Veredicto F-B:** **NO-GO** — 13 de 13 criterios cumplen; **1 decisión empresarial sigue abierta** (§10, retiro del principal)

---

## Resumen

```
Codigo modificado:   0    Modelos: 0   Migraciones: 0   Endpoints: 0   M09: sin tocar
makemigrations --check:    "No changes detected"
Produccion:          SIN CAMBIOS -- 15 claves, DIFERENCIAS: NINGUNA (solo SELECT, read_only)
Commit:              no

Mediciones nuevas:   7 (N1..N7), contenedor aislado, 0 credenciales de produccion
Decisiones cerradas: F-1, F-2, F-3, F-4  (las cuatro, con evidencia)
Decision abierta:    1 -- que ocurre al retirar al principal
```

### Las cuatro propuestas, contrastadas contra la evidencia

> El encargo pide asumirlas como **propuesta de trabajo** y **no** marcarlas
> aprobadas hasta confirmar que son coherentes y que no hay evidencia
> contradictoria.

| | Propuesta | Veredicto | Evidencia contradictoria |
|:--:|---|:--:|---|
| **F-1** | Cuadrilla ad-hoc por OT | **COHERENTE** | **ninguna** |
| **F-2** | 0 / 1 / 2+, líder solo para cuadrilla | **COHERENTE** | **ninguna** — y se cierra además la sub-pregunta de §7 con evidencia medida |
| **F-3** | `es_principal` es la fuente de verdad | **COHERENTE** | **ninguna** — 6 consumidores contra 0 |
| **F-4** | Catálogo cerrado en la API | **COHERENTE, y más barato de lo previsto** | **ninguna** — y **no requiere migración** tal como está redactada |

**[MEDIDO]** Ninguna de las cuatro tropieza con evidencia en contra. Lo que
queda abierto no es ninguna de ellas: es una consecuencia de F-2 que el encargo
aísla en su §10.

---

## Método

**[MEDIDO]** Siete mediciones (N1–N7) sobre PostgreSQL 16 aislado (`pg-fa2`) con
runner desde `crm-agentico-backend:latest`. Credenciales de producción visibles
en el runner: **0** (medido con `env | grep -ci`). Entorno **eliminado**;
archivo de medición **borrado** (verificado con `git status`).

Producción: **solo `SELECT`**, `read_only = True`.

**[MEDIDO]** El `CHECK` de N4 se aplicó y se retiró **en la base aislada**.
Confirmado después contra producción: `CHECK constraints sobre
campo_asignacion_trabajo = 0`.

---

## A. F-1 — Cuadrilla ad-hoc por OT

### A.1 Compatibilidad con cada superficie

**[MEDIDO]**

| Superficie | Compatible | Evidencia |
|---|:--:|---|
| `AsignacionTrabajo` | **sí** | `orden_id` NOT NULL agrupa; N2 formó cuadrillas y personas repetidas sin error |
| `OrdenTrabajo` | **sí** | `tecnico_principal` es @property derivada; no hay campo que duplicar |
| **Programación** | **sí, sin acoplamiento** | `operaciones/programacion.py` **no lee `asignaciones` en ninguna línea** |
| `ProgramacionOrden` | **sí** | N3: dos `asignar()` dejaron `secuencia`, `dia`, `zona`, `prioridad` y `updated_at` de la línea **idénticos** |
| **Disponibilidad** | **parcial** | El dato es por persona y ya existe; **el consumidor solo mira al principal** (§J) |
| **Ejecución** | **sí** | `PuedeAccederOrden` concede por **pertenencia**, no por principalía (M5 de F-A.1) |

### A.2 Qué datos existentes la representan

**[MEDIDO]** `cuadrilla(OT) := OT.asignaciones.all()`. Cada fila es un
integrante: `profile` (quién), `rol` (qué hace), `es_principal` (quién
responde), `asignado_en` (desde cuándo).

### A.3 ¿Falta información? ¿Hace falta un identificador de cuadrilla?

**[DISEÑO] No, y `orden_id` es suficiente.** F-1 define la cuadrilla como
**ad-hoc por OT**: no sobrevive a la OT, luego no necesita identidad propia. Un
`cuadrilla_id` solo tendría sentido para una cuadrilla que persiste entre OTs —
que es exactamente lo que F-1 **descarta**.

**[MEDIDO]** Consistente con `operaciones/models.py:19`, que ya lo declaraba:
*"campo.AsignacionTrabajo — la cuadrilla. Ya soporta N personas con rol."*

### A.4 ¿Qué ocurre cuando una persona pertenece a dos OTs?

**[MEDIDO] N2 — está permitido, y no hay ningún control de solape:**

```
misma persona en 2 OTs distintas ......... 2 asignaciones, sin error
ambas programadas 2026-10-05 09:00 ....... nada lo impidio
misma persona DOS VECES en la misma OT ... RECHAZADO (unique_profile_per_orden)
```

**[DISEÑO]** Que se permita es **correcto y necesario**: F-1 lo exige
explícitamente (*"una misma persona puede participar en diferentes OTs con
diferentes compañeros"*).

**[RIESGO] Lo que no existe es el control de solape horario.** Hoy nada impide
que la misma persona quede programada en dos OTs a la misma hora del mismo día.
No es un defecto **introducido** por F-1 —ya era así con asignación
individual— pero F-1 lo vuelve más alcanzable, y por eso queda documentado.
**No es bloqueante de F-B**: detectar solapes es trabajo del supervisor (M09),
que este paso tiene prohibido tocar.

### A.5 ¿Qué ocurre cuando una OT cambia de composición?

**[MEDIDO] N3 — no se mueve nada más:**

```
campo              antes -> despues
programada_para    IGUAL
secuencia          IGUAL
dia                IGUAL
zona               IGUAL
prioridad          IGUAL
linea_updated      IGUAL
revision           CAMBIO  2 -> 4     (+1 por cada asignar())
lineas del plan:   1                  (sin cambios)
```

**[DISEÑO]** `revision` **debe** seguir incrementándose: es el contador de
sincronización de la cola offline del técnico (`despacho.py:181-182`). Si
cambia la cuadrilla, el dispositivo del técnico tiene que enterarse. **Es la
única escritura sobre la OT que F-B debe conservar deliberadamente.**

### A.6 Veredicto F-1

**[DISEÑO] F-1 es coherente y no encuentra evidencia en contra.** Se representa
con lo que ya existe, sin campo nuevo, sin migración y sin entidad `Cuadrilla`.

---

## B. F-2 — Los tres estados

### B.1 Definición técnica de cada estado

**[DISEÑO]** Cada fila sustentada con lo medido:

| | Estado | ¿Puede existir? | ¿Requiere principal? | ¿Requiere rol? | ¿Requiere líder? | Qué significa `es_principal` |
|:--:|---|:--:|:--:|:--:|:--:|---|
| **A** | **0 asignaciones** | **SÍ** — deliberado | **NO** | **NO** | **NO** | *no aplica*: no hay filas |
| **B** | **1 asignación** | **SÍ** | **SÍ** — `True` | sí (con valor por defecto) | **NO** — no hay cuadrilla que liderar | esa persona responde por la OT |
| **C** | **2+ asignaciones** | **SÍ** | **SÍ** — exactamente uno | sí, uno por integrante | **el principal cumple ese papel** | quién responde por la OT y por la cuadrilla |

### B.2 Estado A — la OT sin asignar es legítima, y está en uso

**[MEDIDO]** Dos evidencias independientes, ambas deliberadas:

`campo/serializers.py:202-204` — el comentario del propio campo:

```python
# A quien se le asigna de entrada. Opcional: una orden puede quedar sin
# asignar esperando que alguien la tome, y esa es una columna util en la
# bandeja del supervisor.
tecnico_profile_id = serializers.UUIDField(required=False, allow_null=True)
```

`operaciones/supervisor.py:477-479` — M09 ya lo consume sin romperse:

```python
principal = o.tecnico_principal
if principal is None:
    continue
```

**[DISEÑO] F-2 lo respeta correctamente**: la exigencia de principal aplica
**desde que existe al menos una asignación**, nunca al estado vacío. Esto
resuelve el conflicto que M03-F-A.1 había dejado abierto como decisión #2.

### B.3 §7 — ¿Una asignación individual debe tener `es_principal=True`?

> El encargo: *"No decidir por preferencia. Buscar evidencia del comportamiento
> actual. Si no existe evidencia suficiente: [PENDIENTE EMPRESARIAL]."*

**[MEDIDO] La evidencia existe, es unánime, y la respuesta es A (`True`).**
Tres fuentes independientes:

| Fuente | Evidencia |
|---|---|
| **Todas las vías de servicio** | `asignar()` **no tiene rama**: siempre `es_principal=True` (`despacho.py:174` y `:178`). `CrearOrdenView:158` pasa por ahí |
| **Los datos de producción** | 3 de 3 asignaciones con `es_principal=True` |
| **La consecuencia funcional** (N1) | *ver abajo* |

**[MEDIDO] N1 — qué pasa si una asignación individual NO es principal:**

```
default del modelo para es_principal .... False
miembros de la OT ....................... 1
OrdenTrabajo.tecnico_principal .......... None
H-05 senales de riesgo .................. 0    (¡con la persona AUSENTE ese dia!)
CONTRASTE con es_principal=True ......... 1 senal
```

**[MEDIDO]** Una OT con técnico asignado y `es_principal=False` queda:
invisible para H-05, con `tecnico_principal: null` en ambos serializers, y
como *"Sin asignar"* en el panel (`admin.py:162`). **Tiene a alguien asignado y
todas las superficies de supervisión dicen que no.**

**[DISEÑO] Respuesta: A — `es_principal=True`.** No es preferencia: la opción B
produce una incoherencia medible entre el dato y lo que ve quien supervisa.

**[RIESGO] El valor por defecto del modelo contradice a todas las vías de
escritura.** `es_principal = models.BooleanField(default=False)`
(`campo/models.py:353`). Ninguna vía de servicio lo usa — pero el **admin**, el
**seed** y cualquier escritura por ORM sí, y son justamente las que producirían
el estado que N1 mide como dañino. **F-B debería alinear el default**; es un
cambio de modelo y por tanto **exige migración** (§O).

### B.4 Veredicto F-2

**[DISEÑO] F-2 es coherente y no encuentra evidencia en contra.** Los tres
estados quedan definidos, y la sub-pregunta de §7 **cerrada con evidencia
medida**, no por preferencia.

---

## C. F-3 — `es_principal` como fuente de verdad

### C.1 Qué significa `es_principal=True` — medido por sus consumidores

**[MEDIDO] Seis consumidores funcionales:**

| Consumidor | Archivo | Qué decide |
|---|---|---|
| `OrdenTrabajo.tecnico_principal` | `campo/models.py:307-315` | La @property de la que cuelga todo |
| **H-05 `_ordenes_en_riesgo`** | `operaciones/supervisor.py:477` | **Si se emite señal de riesgo por ausencia** |
| `OrdenTrabajoSerializer` | `campo/serializers.py:85-92` | Lo que ve la bandeja |
| `OrdenTrabajoDetailSerializer` | `campo/serializers.py:146-153` | El detalle |
| `admin.tecnico_responsable` | `campo/admin.py:162` | La columna "Técnico Principal" |
| `despacho.asignar` | `campo/services/despacho.py:167` | El `anterior` del evento |

Más, estructuralmente: el índice único parcial (`models.py:369`), el
`Meta.ordering` (`models.py:361`) y el `__str__` (`models.py:376`).

**[MEDIDO] Significa: el responsable de la OT — la persona por la que pregunta
el supervisor y cuya ausencia pone la OT en riesgo.** N1 lo demuestra por
contraste: con `es_principal=True` H-05 emite; con `False`, no emite **con la
misma persona igual de ausente**. No es "líder de cuadrilla": es
**responsabilidad**, y se mide en H-05.

### C.2 ¿Cuál debe ser la regla?

**[DISEÑO] "Exactamente un principal cuando existen asignaciones."**

Las tres candidatas del encargo, contrastadas:

| Candidata | Veredicto | Sustento |
|---|:--:|---|
| **"máximo un principal"** | **insuficiente** | Es lo que la base hace **hoy** (índice parcial). N1 y N7 miden que el estado "cero principales con gente asignada" es dañino: la OT desaparece de la supervisión |
| **"exactamente uno cuando existen asignaciones"** | **SUSTENTADA** | Cubre B y C; deja A (0 asignaciones) intacto, que es el estado deliberado de §B.2 |
| **"exactamente uno solo con 2+ personas"** | **rechazada** | Legitimaría exactamente el estado que N1 mide como dañino: 1 persona, 0 principales, invisible a H-05 |

**[DISEÑO]** Formalmente:

```
count(asignaciones) == 0                    ->  count(es_principal) == 0     (valido)
count(asignaciones) >= 1                    ->  count(es_principal) == 1     (exigido)
```

**[DISEÑO] Momento de evaluación: al CIERRE de la transacción, no por fila.**
Durante `asignar()` existe un instante legítimo con cero principales —
`update(es_principal=False)` corre **antes** del `get_or_create`
(`despacho.py:170-176`). Una comprobación inmediata abortaría una operación
correcta.

### C.3 Veredicto F-3

**[DISEÑO] F-3 es coherente y no encuentra evidencia en contra.** `es_principal`
es la fuente operacional de verdad, medida por sus 6 consumidores. **No se
cambia el nombre del campo ni se crea otro.**

---

## D. F-4 — Catálogo cerrado

### D.1 Auditoría del catálogo actual

**[MEDIDO]**

| | |
|---|---|
| **Valores** | `tecnico` · `tecnico_lider` · `ayudante` · `chofer` · `supervisor` (`campo/models.py:335-341`) |
| **Consumidores que deciden algo** | **ninguno** (§E) |
| **Único lector** | `campo/admin.py:20`, que solo lo muestra |
| **Escrituras** | `despacho_views.py:193` · `despacho.py:174`/`:178` · `admin.py:20` (inline editable) · `seed_campo_demo.py:122` |
| **API** | `AsignarSerializer.rol` = **`CharField`** (`serializers.py:209`) |
| **Modelo** | `CharField(choices=ROLES_CUADRILLA, default="tecnico")` |
| **DB** | **0 CHECK**, 0 triggers, `rol` no participa de ningún índice |
| **Valores en producción** | 3 de 3 = `tecnico_lider` — **dentro** del catálogo |

**[MEDIDO] El catálogo no se hace cumplir hoy** (hallazgo ya reportado en
F-A.1 §K.4, no parcheado): la API acepta y persiste cualquier cadena con
HTTP 200, porque el serializer es `CharField`, nadie llama `full_clean()` y no
hay `CHECK`.

### D.2 Las cuatro fronteras, medidas

**[MEDIDO] N5 — la frontera de entrada:**

```
CharField (hoy)  con rol='pirata'  -> valido=True
ChoiceField      con rol='pirata'  -> valido=False   "pirata" is not a valid choice.
ChoiceField      con rol valido    -> valido=True
```

**[MEDIDO] N4 — la frontera de base**, con un `CHECK` real aplicado y retirado
en la base aislada:

```
catalogo declarado: ['tecnico','tecnico_lider','ayudante','chofer','supervisor']
CHECK aplicado SOBRE la fila estilo-produccion .... ACEPTADA
rol invalido tras el CHECK ....................... RECHAZADO
los 5 valores del catalogo ....................... 5 aceptados
```

**[MEDIDO]** El `CHECK` **no rompería producción**: admite el `tecnico_lider`
que hay en las 3 filas y los 5 valores del catálogo, y rechaza lo de fuera.
Probado que **dispara** antes de confiar en él.

### D.3 Qué frontera debe hacer cumplir el catálogo

**[DISEÑO]**

| | Opción | Cubre | Migración | Evaluación |
|:--:|---|---|:--:|---|
| **A** | `ChoiceField` | **la API operacional** | **NO** | **Satisface F-4 tal como está redactada** |
| **B** | Validación de servicio | el servicio | no | **Redundante** si existe A, y no cubre admin/ORM |
| **C** | `CHECK` de DB | **toda** escritura | **sí** | Endurecimiento **más allá** de lo que F-4 pide |
| **D** | Combinación A+C | todo, con buen mensaje | **sí** | Lo completo |

**[DISEÑO] Precisión que cambia el costo:** F-4 dice *"un rol fuera del
catálogo no debe poder ser persistido **a través de la API operacional**"*.
Eso es **exactamente** lo que cubre la opción **A**, y **A no requiere
migración** (N5). El `CHECK` cierra además admin, seeds y ORM — valioso, pero
es una **decisión aparte**, no un requisito de F-4.

**[DISEÑO] Recomendación: A ahora (0 migraciones, cierra F-4), C como
endurecimiento explícito.** B se descarta por redundante.

### D.4 Veredicto F-4

**[DISEÑO] F-4 es coherente, no encuentra evidencia en contra, y — tal como
está redactada — NO requiere migración.**

---

## E. Principal / líder / rol

### E.1 ¿Existe "líder" operacionalmente?

**[MEDIDO] No. `rol=tecnico_lider` no tiene ningún consumidor funcional.**

`rol` aparece **solo en escritura**. **No** aparece en: ninguna respuesta de
API (ni `OrdenTrabajoSerializer` ni `OrdenTrabajoDetailSerializer` lo exponen),
ningún `filter()`, ningún `order_by()`, ningún permiso, ninguna constraint,
ningún índice, ninguna regla de `operaciones/programacion.py`.

**Se dice, como pide el encargo: el concepto "líder" NO está siendo utilizado
operativamente por el sistema.**

### E.2 Qué debería significar cada uno

**[DISEÑO]**

| Término | Significado propuesto | Sustento |
|---|---|---|
| **principal** | **Quien responde por la OT.** Único cuando hay asignaciones. Decide H-05 | **[MEDIDO]** Es lo que ya significa, por sus 6 consumidores (N1 por contraste) |
| **líder** | **No es un concepto del sistema.** Si la empresa lo usa, hoy coincide con el principal | **[MEDIDO]** 0 consumidores |
| **rol** | **Dato descriptivo** del papel de cada integrante. No decide nada | **[MEDIDO]** Nadie lo lee para decidir |

### E.3 Qué debe hacer `rol` — las cuatro opciones del encargo

**[DISEÑO] Opción A: permanecer como dato descriptivo.**

| | Opción | Veredicto | Sustento |
|:--:|---|:--:|---|
| **A** | Dato descriptivo | **ELEGIDA** | Es lo que es hoy. Con F-4 pasa a ser un dato **confiable** sin pasar a ser un dato **con poder** |
| **B** | Alinearse con el principal | **rechazada** | **[RIESGO]** `rol` heredaría la semántica de H-05: cambiar un rol pasaría a mover **qué ausencia dispara una señal de riesgo**. Hoy cambiar `rol` no afecta a nada (0 consumidores) |
| **C** | Eliminarse de ciertas operaciones | **rechazada** | Es dato real, poblado en las 3 filas de producción y visible en el panel. Quitarlo perdería información sin ganar nada |
| **D** | Otra función existente | **no encontrada** | El barrido no halló ninguna |

**[DISEÑO] El mínimo necesario para F-B: que `rol` sea confiable (F-4) y que
siga sin decidir nada.** No se le inventa semántica, que es lo que el encargo
prohíbe.

**[MEDIDO]** Esto **no modifica `rol` en este paso** — el encargo lo prohíbe
expresamente, y no se tocó.

---

## F. Operaciones necesarias

**[DISEÑO]** Sin implementar. `[EXISTENTE]` = ya funciona hoy.

### F.1 Cuáles son necesarias

| | Operación | ¿Necesaria? | Estado |
|:--:|---|:--:|---|
| **A** | Asignar primera persona | **SÍ** | **[EXISTENTE]** — `asignar()` ya lo hace correctamente |
| **B** | Agregar integrante | **SÍ** | **[NUEVO]** — no existe (F-A.1 §A.8) |
| **C** | Retirar integrante | **SÍ** | **[NUEVO]** — **semántica del principal ABIERTA** (§F.4) |
| **D** | Cambiar principal | **SÍ** | **[CAMBIO NECESARIO]** — `asignar()` lo hace, pero **también agrega** si la persona no estaba. Hay que separar los dos actos |
| **E** | Reemplazar integrante | **NO como operación propia** | **[NO NECESARIO]** — es `C` + `B` en una transacción. Se justifica solo si debe ser atómico de cara al usuario |
| **F** | Desasignar OT | **SÍ** | **[NUEVO]** — volver al estado A (0 asignaciones), que §B.2 declara legítimo |
| **G** | Consultar composición | **SÍ** | **[CAMBIO NECESARIO]** — **la cuadrilla no se expone hoy**: ningún serializer devuelve `asignaciones` |

**[MEDIDO] `G` es un hueco real**: los serializers devuelven
`tecnico_principal` (id + nombre) y nada más. Sin `G`, F-B construiría
cuadrillas que **ninguna interfaz puede mostrar**.

### F.2 Contrato de cada operación

**[DISEÑO]** Precondiciones, permitido, prohibido, auditoría, concurrencia,
permisos. Común a todas: **rol de gestión** (`ROLES_GESTION`, igual que
`AsignarTrabajoView` hoy vía `_exigir_gestion`), y **misma org** en las dos
puntas (patrón de `despacho.py:159` y `programar_orden`).

| Operación | Precondiciones | Cambios permitidos | Cambios **prohibidos** |
|---|---|---|---|
| **A. Asignar primera** | OT no `CERRADA`/`CANCELADA`; 0 asignaciones; persona de la misma org | +1 fila con `es_principal=True`; `revision += 1` | fecha · secuencia · plan · estado de la OT |
| **B. Agregar integrante** | ≥1 asignación; persona no está ya en la OT; OT no terminada | +1 fila con **`es_principal=False`** | **mover el principal** (§F.3) · fecha · secuencia · plan |
| **C. Retirar integrante** | La persona está en la OT; **no es la principal** *(mientras §10 siga abierta)* | marcar retirada | dejar la OT con gente y sin principal |
| **D. Cambiar principal** | Ambas personas ya son integrantes; OT no terminada | baja el anterior, sube el nuevo, **en la misma transacción** | agregar a alguien que no estaba · cambiar `rol` |
| **F. Desasignar OT** | OT no iniciada *(a confirmar con §10)* | retirar a todos → estado A | dejar una cuadrilla parcial sin principal |
| **G. Consultar** | Permiso de lectura sobre la OT | ninguno (lectura) | — |

**Auditoría, concurrencia y permisos:** §H, §G y §M respectivamente.

### F.3 §8 — Agregar un segundo integrante sin mover el principal

**[MEDIDO] Hoy la operación NO existe, y la que hay hace justo lo contrario.**
M1 (F-A.1), re-confirmado: `asignar(p1,'tecnico_lider')` seguido de
`asignar(p2,'ayudante')` deja `p1` **sin** principal y `p2` **como** principal.

**[DISEÑO] Cómo se evita que "agregar" mueva el principal accidentalmente:**

```
agregar_integrante(orden, persona, rol):
    bloquear la OT                      #  select_for_update, §G
    verificar que ya hay >= 1 asignacion
    verificar que 'persona' no esta ya
    crear fila con es_principal = False     <-- FIJADO EN CODIGO, no parametro
    revision += 1
    evento 'integrante_agregado'
```

**[DISEÑO] `es_principal` NO es un parámetro de esta operación.** Es la misma
decisión que ya rige en el módulo: *"lo que el cliente no debe elegir, no se
declara"* (`ProgramarSerializer`, M03-B). Mover el principal es la operación
**D**, y tiene su propio nombre, su propio evento y su propio motivo.

**[DISEÑO]** El resultado esperado es el que pide el encargo: **A principal,
B no principal.**

### F.4 §10 — Retirar al principal: la decisión abierta

**[MEDIDO] N7 — lo que pasa hoy con un borrado crudo:**

```
antes: miembros=2  principal=pa
tras borrar al principal:
     miembros ............. 1     (queda pb)
     tecnico_principal .... None
     eventos .............. 1 -> 1   (delta=0)   <-- sin rastro
     H-05 con pb ausente .. 0 senales
=> la OT queda con gente, sin principal e invisible para H-05
```

**[MEDIDO] Retirar a un auxiliar no tiene problema:** `A` sigue siendo
principal, la OT sigue visible. El caso abierto es **solo** el del principal.

**[DISEÑO] La regla de §C.2 excluye técnicamente una de las cuatro opciones:**

| | Opción | Veredicto |
|:--:|---|---|
| **a** | Queda la OT sin principal | **EXCLUIDA técnicamente** — viola "exactamente uno cuando existen asignaciones", y N1/N7 miden el daño |
| **b** | Se exige elegir reemplazo en la misma operación | **viable** |
| **c** | Se rechaza: primero `cambiar_principal`, después retirar | **viable** |
| **d** | Pasa a "pendiente de asignación" | **incoherente** si quedan otros integrantes: la OT no está sin asignar |

**[PENDIENTE EMPRESARIAL] Queda entre (b) y (c), y no la tomo.** Son dos
políticas operativas distintas — una fuerza la decisión en el acto, la otra la
parte en dos pasos explícitos — y **ninguna se deriva de la evidencia**. Es la
única decisión abierta de este paso.

---

## G. Concurrencia

### G.1 El patrón existente en M03

**[MEDIDO]** El invariante del módulo, escrito en
`operaciones/programacion.py:765-770`:

> *"LOS LOCKS, EN ORDEN FIJO: ORDEN PRIMERO, PLAN DESPUES. No es arbitrario.
> […] Invertirlo si podria producir un interbloqueo."*

| Operación | Bloquea |
|---|---|
| `programar_orden` | OT |
| `publicar_programacion` | plan |
| `reprogramar_orden` | OT → plan |
| `actualizar_secuencia` | línea → plan |
| `secuenciar_jornada` | líneas (id asc) → plan |

**El plan es SIEMPRE el último lock.**

### G.2 Qué hace hoy `asignar()`

**[MEDIDO] `asignar()` es `@transaction.atomic` pero NO toma ningún lock.**
`select_for_update` aparece una sola vez en todo `campo/services/despacho.py`,
y es **dentro de un comentario** (línea 46), sobre otro tema.

**[MEDIDO] N6 — dos `asignar()` simultáneos sobre la misma OT:**

```
excepciones ..... 1   IntegrityError: duplicate key ... "unique_tecnico_princip..."
filas resultantes  1   principales=1
eventos ......... 1
```

**[DISEÑO] El estado final es coherente — pero lo salva la base, no el
servicio.** El segundo solicitante recibe un `IntegrityError` sin manejar, que
es un **500**, no un conflicto explicado. Comparado con el resto de M03, donde
un conflicto real da **409 con mensaje**, es una asimetría.

### G.3 Diseño de locks para F-B

**[DISEÑO] Bloquear la OT, y solo la OT.**

```
agregar_integrante  ->  OT
retirar_integrante  ->  OT
cambiar_principal   ->  OT
reemplazar          ->  OT
```

**[DISEÑO] Por qué la OT y no las filas de asignación:** el invariante
—"exactamente un principal"— es **del conjunto**, no de una fila. Bloquear
filas individuales no impide que llegue una fila nueva; bloquear la OT sí
serializa toda la composición. Es además el mismo objeto que bloquea
`programar_orden`, así que **no se introduce un orden de lock nuevo**.

**[DISEÑO] Sin riesgo de interbloqueo:** ninguna operación de cuadrilla toca el
plan, así que nunca se toma un segundo lock. El invariante "plan siempre
último" se respeta **por vacuidad**.

**[DISEÑO]** Con el lock, la carrera de N6 deja de resolverse con un
`IntegrityError` y pasa a resolverse con la regla del servicio y su mensaje.

---

## H. Auditoría

### H.1 La superficie existente sirve

**[MEDIDO]** `EventoTrabajo` (`campo/models.py`) — *"Bitácora append-only de
eventos y auditoría operativa de campo"*:

| Campo | Cubre lo que pide el encargo |
|---|---|
| `orden` (FK, **NOT NULL**) | **OT** |
| `profile` (FK, nullable, `SET_NULL`) | **actor** |
| `created_at` (de `BaseModel`) | **fecha/hora** |
| `datos` (JSONField) | **antes**, **después**, **motivo** |
| `tipo` (CharField) | qué ocurrió |

**[DISEÑO] No hace falta ninguna auditoría paralela.** `EventoTrabajo` ya tiene
las seis piezas.

### H.2 Los cinco registros

**[DISEÑO]**

| Hecho | `tipo` | `datos` mínimos |
|---|---|---|
| Asignación (primera) | `asignacion` | **[EXISTENTE]**, sin cambios |
| Incorporación | `integrante_agregado` | `{profile, rol}` |
| Retiro | `integrante_retirado` | `{profile, rol_que_tenia, motivo}` |
| Cambio de principal | `cambio_principal` | `{anterior, nuevo, motivo}` |
| Reemplazo | `integrante_reemplazado` | `{sale, entra, rol, motivo}` |

**[DISEÑO] Motivo obligatorio cuando hay compromiso operacional** — la misma
regla ya aprobada en M03-D1/E3: si la OT está en un **plan publicado** o ya
arrancó, retirar o cambiar al principal exige motivo. Agregar a alguien a un
borrador, no.

### H.3 Dos riesgos medidos

**[RIESGO] La escritura directa no deja rastro.** M6 (F-A.1) y N7: crear o
borrar la fila por ORM deja **0 eventos** (`delta=0`). Mientras el inline del
admin exponga `es_principal` y `rol` como editables (`campo/admin.py:17-21`),
el historial de cuadrillas tendrá huecos silenciosos — el mismo problema que el
docstring de `asignar()` dice haber resuelto para el panel, y que **solo se
resolvió del lado del servicio**.

**[RIESGO] `EventoTrabajo.tipo` es texto sin catálogo cerrado.**
`operaciones/auditoria.py:44` ya advierte que un tipo sin declarar *"se guarda
igual y queda divergiendo sin que nadie lo vea"* — y cita precisamente a
`AsignacionTrabajo.rol` como el caso que terminó así. Agregar 4 tipos nuevos
sin declararlos repetiría el error que esa nota describe.

---

## I. Programación

### I.1 Qué relación existe

**[MEDIDO] Ninguna. `ProgramacionOrden` y `AsignacionTrabajo` no se cruzan.**

`operaciones/programacion.py` **no lee `asignaciones` en ninguna línea** — sus
únicas referencias a `profile` son `profile=actor`, quien escribe el evento.
`revisar_coherencia` tampoco: comprueba org, límites de semana, coherencia
día↔fecha y líneas duplicadas. **Nada de personas.**

| | Responde |
|---|---|
| `ProgramacionOrden` | **cuándo** y **en qué orden** |
| `AsignacionTrabajo` | **quién** |
| `OrdenTrabajo` | **qué** trabajo, y su estado |

### I.2 ¿Cambiar integrantes debe modificar programación, secuencia o fecha?

**[MEDIDO] No, y hoy efectivamente no lo hace.** N3, con la OT ya programada en
un plan, secuencia 7, zona norte, prioridad 3:

```
programada_para IGUAL · secuencia IGUAL · dia IGUAL · zona IGUAL
prioridad IGUAL · linea.updated_at IGUAL · lineas del plan: 1
```

**[DISEÑO] F-B debe conservar esta independencia**, y es fácil: las operaciones
de cuadrilla ni siquiera abren el plan (§G.3). La única escritura sobre la OT
es `revision += 1`, que es deliberada (§A.5).

### I.3 Un hueco que queda documentado

**[RIESGO]** `ESTADOS_PROGRAMABLES = {ASIGNADA}` filtra por el **campo de
estado** `estado_operativo`, no por la existencia de asignaciones. **Una OT en
estado `ASIGNADA` con cero asignaciones se puede programar.** El estado dice
"asignada" y la tabla puede decir que no hay nadie.

**[PENDIENTE]** Si programar debe exigir cuadrilla es **decisión empresarial** —
podría ser legítimo planificar la semana y asignar personas después. **No
bloquea F-B**: es una regla de `programar_orden`, no de las operaciones de
cuadrilla, y el encargo no autoriza tocar ese camino.

---

## J. Disponibilidad

### J.1 Qué existe y qué se detecta hoy

**[MEDIDO]** `DisponibilidadTecnico` guarda `(org, profile, fecha, hora_inicio,
hora_fin, disponible, motivo, zona)` — **por persona**. El dato crudo para
detectar el conflicto **ya está completo**.

**[MEDIDO]** El consumidor no lo aprovecha: `_ordenes_en_riesgo`
(`supervisor.py:471-490`) consulta **solo al principal**.

### J.2 El caso del encargo: A disponible, B ausente

**[DISEÑO]** Con B ausente y el principal A presente, **H-05 no emite nada
hoy**. Es consecuencia directa de §J.1, y **no es un defecto de H-05**: se
escribió cuando una OT era una persona.

**[MEDIDO]** N1 y N7 miden el mismo punto ciego desde el otro lado: una persona
no-principal ausente produce **0 señales**, y una OT sin principal es invisible
aunque tenga gente.

### J.3 Lo que se puede afirmar — y lo que no

**[DISEÑO]**

| | |
|---|---|
| **Señal detectable** | *"la OT #N está programada el día D y **k** de sus **m** integrantes están declarados no disponibles ese día"* — computable **hoy**, con los datos que ya existen |
| **Responsable** | **quien programa / supervisa**. La señal es sobre la **OT**, no sobre la persona |
| **Propuesta futura** | reasignar, reprogramar o reducir alcance — **ninguna automática** |

**[DISEÑO] No se atribuye incumplimiento personal**, como exige el encargo. Una
ausencia declarada es un dato de disponibilidad, no una falta: la señal dice
que **la OT** está en riesgo, no que alguien haya fallado. El texto de la señal
debe nombrar la OT como sujeto.

**[DEPENDENCIA]** Ampliar H-05 a todos los integrantes **vive en `operaciones/
supervisor.py`, que es M09** — y este paso prohíbe modificarlo. Queda como
**paso posterior**, no como parte de F-B.

**[RIESGO] Consecuencia a declarar:** F-B habilita cuadrillas de N personas
mientras H-05 sigue mirando a una sola. **El punto ciego crece con la
adopción.** Debe quedar dicho antes de habilitar cuadrillas, no después.

---

## K. Vehículo

**[MEDIDO] Confirmado: no existe modelo, no existe tabla, no existe campo.**
Barrido completo de `vehiculo|vehículo|flota|placa` sobre el backend: **1 sola
coincidencia**, y es ajena — `seed_campo_demo.py:81`, el texto de una
instrucción de evidencia sobre la placa de **nomenclatura** de una dirección.

**[DISEÑO] F-B puede implementarse sin vehículo.** Una cuadrilla ad-hoc es un
conjunto de personas asignadas a una OT; el vehículo es un recurso adicional.
Ninguno de los invariantes de F-1, F-2, F-3 o F-4 lo menciona.

**[DEPENDENCIA] Futura, documentada, no bloqueante.** Si algún día se modela,
la pregunta será si se asocia a la OT, a la cuadrilla o a la jornada — la misma
pregunta de agrupación que F-1 ya resolvió con `orden_id`.

---

## L. Zona

**[MEDIDO]** `zona` vive en `ProgramacionOrden`, **no** en `AsignacionTrabajo`
ni en la OT. Es texto libre sin catálogo (gap **E-7**, abierto desde M03-E4).

**[DISEÑO] Una cuadrilla NO necesita zona propia.** La zona describe **dónde se
trabaja** y ya cuelga de la línea de programación; la cuadrilla describe
**quién trabaja**. Duplicarla crearía dos fuentes para el mismo dato — lo
contrario de la regla de *"fuente única de verdad"* que ya rige para
`tecnico_principal`.

**[MEDIDO]** `DisponibilidadTecnico` **sí** tiene su propio campo `zona`. Es
otra cosa: la zona en la que una persona está disponible, no la de una
cuadrilla.

**[PENDIENTE]** *"Esta cuadrilla solo atiende la zona norte"* sería una
**restricción de asignación**, no un atributo de la cuadrilla, y exigiría
cerrar E-7 primero. **No se inventa aquí.**

---

## M. Seguridad

### M.1 Aislamiento real, medido

**[MEDIDO]**

```
TODAS las tablas campo_*     RLS = False   forzada = False   politicas = 0
campo_asignacion_trabajo     SIN columna org_id / organization_id
campo_orden_trabajo          tiene org_id, pero SIN RLS
rol de conexion en runtime   postgres   bypassrls = True   superuser = False
ORG_SCOPED_TABLES            no contiene ninguna entrada 'campo_'
```

### M.2 De qué depende hoy el aislamiento

**[MEDIDO] Enteramente de la capa de aplicación:**

| Capa | Qué hace |
|---|---|
| `PuedeAccederOrden` | **404 estricto** si `obj.org != request.org` (`permissions.py:47-49`) |
| `despacho.asignar` | `if profile_tecnico.org_id != orden.org_id: raise` (`despacho.py:159-160`) |
| `programar_orden` | comprueba **las dos puntas**, orden y plan |

**[MEDIDO]** El permiso concede por **pertenencia**: un integrante no principal
accede a la OT; un ajeno recibe 404 (M5 de F-A.1). **Esta pieza ya está bien
construida para F-1** — no requiere cambios.

### M.3 Lo que hay que decir explícitamente

> El encargo: *"No afirmar que reutilizar `AsignacionTrabajo` resuelve
> automáticamente el aislamiento DB."*

**[RIESGO] No lo resuelve, y conviene decirlo sin matices:** reutilizar
`AsignacionTrabajo` hereda **exactamente** el aislamiento que esa tabla tiene
hoy, que en la capa de base de datos es **ninguno**. Sin RLS y sin `org_id`
propio, **toda** la separación entre empresas vive en el código de aplicación.

**[RIESGO]** Si algún día se activa RLS sobre `campo_*`, esta tabla **no tiene
columna sobre la que filtrar**: la política tendría que navegar el FK a
`campo_orden_trabajo` — viable, pero más cara y más frágil que una columna
directa. **Es un dato que F-B debe conocer antes de diseñar, no después.**

**[MEDIDO]** **B-7 no resuelve ninguno de los dos puntos** (confirmado en pasos
previos; la causa es `ORG_SCOPED_TABLES` en `common/rls/__init__.py`).

**No se corrige en este paso**, como ordena el encargo.

---

## N. Modelo conceptual final

**[DISEÑO]** No implementado. Cada componente etiquetado.

```
OrdenTrabajo                                              [EXISTENTE]
 |   estado A: 0 asignaciones  -- valido y deliberado
 |
 +-- AsignacionTrabajo   (N filas, agrupadas por orden_id)
      |
      +-- orden           FK NOT NULL                     [EXISTENTE]  <- el agrupador
      +-- profile         FK NOT NULL                     [EXISTENTE]
      +-- rol             descriptivo, catalogo cerrado   [CAMBIO NECESARIO]  <- F-4
      +-- es_principal    fuente de verdad, default       [CAMBIO NECESARIO]  <- default False
      +-- asignado_en     auto_now_add                    [EXISTENTE]
      +-- retirado_en     null => vigente                 [NUEVO]
      +-- cuadrilla_ref   agrupador entre OTs             [NO NECESARIO]      <- F-1 lo descarta
      +-- estado          ciclo de vida propio            [NO NECESARIO]
      +-- zona            zona de la cuadrilla            [NO NECESARIO]      <- §L
      +-- org_id          aislamiento propio              [PENDIENTE]         <- §M
```

### N.1 ¿Realmente basta?

**[DISEÑO] Basta para representar la cuadrilla; no basta para operarla.** Lo
que falta no son campos: son **operaciones** (§F) y **una salida en la API**
(§F.1-G). Con un solo campo nuevo —`retirado_en`— el modelo soporta los tres
estados de F-2, la regla de principal de §C.2 y el historial de §H.

| Componente | Etiqueta | Por qué |
|---|---|---|
| `orden_id` como agrupador | **[EXISTENTE]** | F-1 es por OT |
| `retirado_en` | **[NUEVO]** | Sin él, retirar es `DELETE` y el `CASCADE` borra la historia (N7: delta=0 eventos) |
| `rol` → `ChoiceField` en la frontera | **[CAMBIO NECESARIO]** | F-4. Sin migración |
| `es_principal` default → `True`… | **[CAMBIO NECESARIO]** | …o mejor: **quitar el default** y obligar a decidirlo. Hoy `False` contradice todas las vías de escritura (§B.3) |
| Exponer la composición | **[CAMBIO NECESARIO]** | Ningún serializer devuelve `asignaciones` hoy |
| `cuadrilla_ref`, `estado`, `zona` | **[NO NECESARIO]** | §A.3, §N, §L |
| `org_id` propio | **[PENDIENTE]** | §M — excede F-B: afecta a las 7 tablas `campo_*` |

---

## O. Migraciones

### O.1 ¿F-B puede hacerse sin migración?

**[DISEÑO] Depende del alcance, y la frontera es nítida:**

| Alcance | Migración |
|---|:--:|
| **F-4 tal como está redactada** (cerrar la API) | **NO** — `ChoiceField`, medido en N5 |
| **Operaciones B, D, F, G** (agregar, cambiar principal, desasignar, consultar) | **NO** — son servicios, vistas y serializers |
| **Regla de principal** (§C.2) por servicio | **NO** |
| **Operación C** (retirar sin perder historia) | **SÍ** — `retirado_en` |
| **Alinear el default de `es_principal`** | **SÍ** |
| **`CHECK` del catálogo** (endurecimiento) | **SÍ** |
| **"Exactamente un principal" garantizado por DB** | **SÍ** — y con SQL crudo |

### O.2 Qué exigiría exactamente cada una

**[DISEÑO]** Ninguna se crea aquí.

| # | Migración | Por qué | Riesgo sobre producción |
|:--:|---|---|---|
| 1 | `AddField retirado_en (DateTimeField, null=True)` | Único modo de retirar sin que el `CASCADE` borre la historia | **Ninguno** — nullable, sin backfill; las 3 filas quedan vigentes |
| 2 | `AlterField es_principal` (default) | El default contradice todas las vías de escritura (§B.3) | **Ninguno** — el default solo afecta a filas futuras |
| 3 | `AddConstraint CheckConstraint(rol IN ROLES_CUADRILLA)` | Cierra el catálogo donde ninguna vía lo rodea | **Ninguno — medido.** N4: el `CHECK` **acepta** el `tecnico_lider` de las 3 filas y los 5 valores del catálogo |
| 4 | `RunSQL` con trigger `CONSTRAINT ... DEFERRABLE` | "Exactamente un principal" no es expresable como constraint de Django: es un invariante **de conjunto**, y debe evaluarse al **cierre** (§C.2) | **[RIESGO]** SQL crudo, invisible a `makemigrations --check` |

### O.3 Índices y RLS

**[DISEÑO] Índices: ninguno nuevo necesario.** `orden_id` ya tiene índice
propio, y `unique_profile_per_orden` cubre la búsqueda por `(orden, profile)`.
Un índice sobre `retirado_en` solo se justificaría con volumen — producción
tiene **3 filas**.

**[PENDIENTE] RLS: fuera del alcance de F-B** (§M). Activarla exigiría decidir
antes si `campo_asignacion_trabajo` lleva `org_id` propio, y eso afecta a las 7
tablas `campo_*`, no solo a esta.

---

## P. Matriz de decisiones

### F-1 — Cuadrilla ad-hoc por OT

| | |
|---|---|
| **Decisión** | La cuadrilla **es** el conjunto de `AsignacionTrabajo` de una OT, agrupado por `orden_id`. Sin entidad `Cuadrilla`, sin agrupador nuevo |
| **Evidencia** | **[MEDIDO]** `orden_id` NOT NULL agrupa · N2: una persona en 2 OTs sin obstáculo, y rechazo correcto de duplicarla en una · N3: cambiar composición no mueve nada del plan · `programacion.py` y `revisar_coherencia` no leen asignaciones · `teams` con 0 filas y consumidores de otros dominios |
| **Regla técnica** | `cuadrilla(OT) := OT.asignaciones.filter(retirado_en__isnull=True)` · tamaño := `count()` · dos OTs son independientes |
| **Pendientes** | **ninguno para F-1**. Documentado aparte: **[RIESGO]** no hay control de solape horario de una persona entre OTs (§A.4) — corresponde a M09 |

### F-2 — Los tres estados

| | |
|---|---|
| **Decisión** | `0` válido · `1` con principal · `2+` con exactamente un principal. La exigencia de principal empieza **con la primera asignación** |
| **Evidencia** | **[MEDIDO]** Estado A deliberado y consumido (`serializers.py:202-204`, `supervisor.py:478`) · §7 resuelto con N1: con `es_principal=False` la OT es **invisible para H-05** con la persona ausente, y visible con `True` · todas las vías de servicio ponen `True` · producción 3/3 |
| **Regla técnica** | `count(asignaciones) == 0 → count(principal) == 0` · `count(asignaciones) >= 1 → count(principal) == 1`, evaluado **al cierre de la transacción** |
| **Pendientes** | **[RIESGO]** el default del modelo (`False`) contradice la regla; lo usan admin, seed y ORM (§B.3) |

### F-3 — `es_principal` como fuente de verdad

| | |
|---|---|
| **Decisión** | `es_principal` es la fuente operacional de verdad. `rol` **permanece descriptivo** (opción **A**) |
| **Evidencia** | **[MEDIDO]** `es_principal`: **6 consumidores**, decide H-05 (N1 por contraste). `rol`: **0 consumidores**; no aparece en ninguna respuesta de API, filtro, orden, permiso ni constraint. **El concepto "líder" no se usa operativamente** |
| **Regla técnica** | El responsable de una OT se obtiene **siempre** de `es_principal`, nunca de `rol`. `rol` no participa de ninguna decisión |
| **Pendientes** | **ninguno**. Se rechaza la opción B (alinear `rol` con el principal) por **[RIESGO]** medido: `rol` heredaría la semántica de H-05 |

### F-4 — Catálogo cerrado

| | |
|---|---|
| **Decisión** | Un rol fuera del catálogo **no debe poder persistirse por la API operacional**. Frontera: **`ChoiceField`** (opción **A**); `CHECK` de DB como endurecimiento aparte (opción **C**) |
| **Evidencia** | **[MEDIDO]** N5: `CharField` acepta `'pirata'`, `ChoiceField` lo rechaza · N4: un `CHECK` real acepta el valor de producción y los 5 del catálogo, y rechaza lo de fuera · hoy: 0 CHECK, sin `full_clean`, serializer `CharField` |
| **Regla técnica** | `rol ∈ ROLES_CUADRILLA` validado en la frontera de entrada; el catálogo sigue siendo `ROLES_CUADRILLA` como única fuente |
| **Pendientes** | **ninguno para F-4 tal como está redactada**: **no requiere migración**. El `CHECK` es **decisión aparte** |

---

## Q. Pruebas futuras para F-B

**[DISEÑO]** Las 20 que pide el encargo. No se implementan. Para cada una se
anota **cómo se comprueba que no es una prueba falsa** — la disciplina del
proyecto: *una prueba que afirma que un mecanismo existe no prueba que
funcione*.

| # | Prueba | Afirma sobre el **efecto** | Cómo se verifica que no es falsa |
|:--:|---|---|---|
| 1 | OT sin asignar | 0 filas · `tecnico_principal is None` · H-05 **no** revienta | Ya cubierto por `supervisor.py:478`; sirve de no-regresión |
| 2 | Primera asignación | 1 fila, **`es_principal=True`** · 1 evento | **Desarmar** la regla → debe caer en el estado que N1 mide como invisible |
| 3 | Segunda asignación | 2 filas · **el principal NO se mueve** | **Desarmar** → debe reproducir M1 (el ayudante roba la principalía) |
| 4 | Tercera asignación | 3 filas · 1 principal | Confirmar que `unique_profile_per_orden` sigue impidiendo duplicar persona |
| 5 | Principal único | `count(principal) == 1` tras **cada** operación | **Desarmar** la regla → la prueba debe fallar |
| 6 | Múltiples principales | rechazado | Hoy ya lo rechaza la base (M4-E); la prueba debe distinguir **rechazo del servicio** de `IntegrityError` |
| 7 | Ningún principal | rechazado **al cierre**, no por fila | Debe pasar **con** el instante intermedio de cero dentro de `cambiar_principal` |
| 8 | Cambio de principal | 2 filas tocadas · 1 evento · `anterior` encadena con el principal previo | Leer con **conexión independiente del ORM** |
| 9 | Retiro de auxiliar | `retirado_en` poblado · fila **NO borrada** · principal intacto | Afirmar que la fila **sigue existiendo** |
| 10 | Retiro del principal | **según la decisión de §F.4** | **No redactable hasta cerrar §10** |
| 11 | Reemplazo | N salidas + M entradas en **una** transacción · principal coherente | Forzar un fallo a mitad → **nada** debe quedar escrito |
| 12 | Rol válido | aceptado y persistido | Cubre los **5** valores, no solo uno |
| 13 | **Rol inválido** | **rechazado con 400** | **Hoy pasaría con 200** (M2/N5). La prueba debe fallar **antes** del cambio |
| 14 | Concurrencia | dos operaciones simultáneas → estado coherente **y mensaje del servicio** | **Desarmar el lock** → debe reproducir el `IntegrityError` de N6 |
| 15 | Tenant diferente | OT de otra org → **404**, nunca 403 | **Conexión independiente del ORM**: no hay RLS que lo respalde (§M) |
| 16 | Auditoría | cada operación deja **exactamente 1** evento; un no-op deja **0** | Probar que el instrumento **dispara** antes de confiar en el cero |
| 17 | Programación no modificada | plan y línea **idénticos** | Comparar `updated_at` de la línea, no solo los valores (N3) |
| 18 | Secuencia no modificada | `secuencia` idéntica | Con una secuencia **distinta de 0**, o el cero taparía el fallo |
| 19 | Fecha no modificada | `programada_para` idéntica · `revision` **sí** sube | Afirmar **ambas**: que no cambie lo que no debe y que **sí** cambie `revision` |
| 20 | Disponibilidad conflictiva | señal detectable con **k de m** integrantes ausentes | **Fuera de F-B** (§J): H-05 es M09. Queda como prueba del paso posterior |

**[RIESGO]** La prueba **10** no se puede redactar hoy: su resultado esperado
**es** la decisión abierta de §F.4.

---

## R. Archivos que F-B modificaría

**[DISEÑO]** Ninguno tocado en este paso.

| Archivo | Cambio previsto | Migración |
|---|---|:--:|
| `campo/serializers.py` | `rol` → **`ChoiceField`** (F-4) · serializers de entrada de las operaciones nuevas · **exponer la composición** de la cuadrilla | no |
| `campo/services/despacho.py` | `agregar_integrante`, `retirar_integrante`, `cambiar_principal`, `desasignar` · regla de principal · **`select_for_update` sobre la OT** (§G.3) · eventos nuevos | no |
| `campo/despacho_views.py` | 4 endpoints nuevos · **`CrearOrdenView:158` debe pasar `rol` explícito** (hoy deja `tecnico`+principal) | no |
| `campo/urls.py` | 4 rutas | no |
| `campo/models.py` | `retirado_en` · default de `es_principal` · (opcional) `CheckConstraint` | **sí** |
| `campo/admin.py` | **[RIESGO]** `es_principal`/`rol` a `readonly`: el inline rodea toda regla de servicio y no deja evento (M6, N7) | no |
| `campo/permissions.py` | **sin cambios** — ya concede por pertenencia (M5) | no |
| `campo/migrations/00XX_*.py` | 1 migración con los cambios del modelo | **sí** |
| `campo/tests/` · `operaciones/tests/` | las 20 pruebas de §Q | no |

### R.1 Lo que F-B NO toca

**[MEDIDO]**

| | Por qué |
|---|---|
| `operaciones/programacion.py` | **No lee asignaciones en ninguna línea.** N3 confirma que la programación no se mueve |
| `revisar_coherencia` | **Prohibido por el encargo** — y además no lee asignaciones |
| `operaciones/supervisor.py` (**M09**) | **Prohibido por el encargo.** El punto ciego de H-05 queda como **[DEPENDENCIA]** de un paso posterior (§J) |
| `campo/permissions.py` | Ya funciona correctamente para cuadrillas |

---

## S. GO / NO-GO para F-B

### Los 13 criterios

| # | Criterio | | Sustento |
|:--:|---|:--:|---|
| 1 | **F-1 cerrado** | **SÍ** | Ad-hoc por OT; `orden_id` agrupa; sin evidencia en contra (§A) |
| 2 | **F-2 cerrado** | **SÍ** | 0/1/2+ definidos; §7 resuelto **con evidencia medida** (N1), no por preferencia (§B) |
| 3 | **F-3 cerrado** | **SÍ** | `es_principal` es la fuente de verdad: 6 consumidores contra 0 (§C) |
| 4 | **F-4 cerrado** | **SÍ** | `ChoiceField` en la frontera; **sin migración**; medido en N5 y N4 (§D) |
| 5 | **Se sabe qué significa principal** | **SÍ** | *Quien responde por la OT y de quien depende H-05* — medido por contraste en N1 |
| 6 | **Se sabe si existe líder operacional** | **SÍ** | **NO existe.** `rol=tecnico_lider` tiene 0 consumidores (§E.1) |
| 7 | **Se sabe qué hacer con 0/1/2+** | **SÍ** | Tabla de §B.1, con la regla de §C.2 |
| 8 | **Se sabe qué operaciones necesita F-B** | **SÍ** | 7 evaluadas: 5 necesarias, 1 descartada (`reemplazar`), 1 existente (§F) |
| 9 | **No se duplica `AsignacionTrabajo`** | **SÍ** | Se evoluciona, no se copia |
| 10 | **No se crea `Cuadrilla` innecesariamente** | **SÍ** | F-1 la descarta explícitamente; `orden_id` basta |
| 11 | **Impacto de seguridad conocido** | **SÍ** | 0 RLS, 0 políticas, sin `org_id`, `bypassrls=True`. **Dicho sin matices: reutilizar la tabla NO resuelve el aislamiento DB** (§M.3) |
| 12 | **Impacto de migraciones conocido** | **SÍ** | 4 migraciones identificadas, cada una con su riesgo **medido** contra los datos reales (§O) |
| 13 | **Pruebas conocidas** | **SÍ** | 20 diseñadas, cada una con su comprobación anti-falso-positivo (§Q) |

```
CUMPLEN: 13 de 13
```

### Pero la cláusula final decide

> *"Si queda cualquier decisión empresarial crítica: NO-GO."*

# NO-GO

**[PENDIENTE] Queda una — y solo una:**

| | Decisión abierta | Por qué no la puedo cerrar |
|---|---|---|
| **§10** | **¿Qué ocurre al retirar al integrante principal?** | N7 mide que hoy la OT queda **con gente, sin principal e invisible para H-05, sin dejar rastro**. La regla de §C.2 excluye la opción (a) *"queda sin principal"* y la (d) *"pasa a pendiente"* es incoherente si quedan otros integrantes. Queda entre **(b) exigir reemplazo en el acto** y **(c) rechazar y obligar a `cambiar_principal` primero** — dos políticas operativas distintas, **ninguna derivable de la evidencia** |

**[DISEÑO] Es un NO-GO mucho más estrecho que el de F-A.1** — de cuatro
decisiones abiertas se pasó a una, acotada a **un caso de una operación**:

```
F-A.1:  4 decisiones abiertas   ->   F-A.2:  1 decision abierta
```

**Alcance real del bloqueo:** las operaciones **A** (asignar primera), **B**
(agregar integrante), **D** (cambiar principal), **F** (desasignar) y **G**
(consultar composición) **no dependen** de esa respuesta. La única que la
necesita es **C** (retirar integrante), y solo en el caso del principal —
retirar a un auxiliar ya está definido y medido.

**[DISEÑO]** Si se prefiere avanzar con alcance reducido —F-B con 5 de 6
operaciones, dejando `retirar_integrante` para después de la decisión— es
viable técnicamente y no deja el modelo incoherente. **Es una decisión de
alcance, y le corresponde a usted, no a mí**: yo la señalo, no la tomo.

---

## Anexo — Mediciones

**[MEDIDO]** Contenedor aislado, **0** credenciales de producción.

```
N1  default del modelo es_principal ........ False
    1 asignacion con es_principal=False:
      tecnico_principal ...... None
      H-05 (persona AUSENTE) . 0 senales
      CONTRASTE con True ..... 1 senal

N2  misma persona en 2 OTs ................. 2 asignaciones, sin error
    ambas el mismo dia y hora .............. nada lo impide
    misma persona 2 veces en 1 OT .......... RECHAZADO (unique_profile_per_orden)

N3  tras dos asignar() sobre una OT programada:
      programada_para IGUAL · secuencia IGUAL · dia IGUAL
      zona IGUAL · prioridad IGUAL · linea.updated_at IGUAL
      revision CAMBIO 2 -> 4        lineas del plan: 1

N4  CHECK real sobre la fila estilo-produccion .... ACEPTADA
    rol invalido tras el CHECK .................... RECHAZADO
    los 5 valores del catalogo .................... 5 aceptados

N5  CharField  con rol='pirata' -> valido=True
    ChoiceField con rol='pirata' -> valido=False  "pirata" is not a valid choice.

N6  dos asignar() simultaneos (sin lock en el servicio):
      excepciones 1  IntegrityError unique_tecnico_principal_por_orden
      filas 1 · principales 1 · eventos 1

N7  borrar al principal de una cuadrilla de 2:
      miembros 1 · tecnico_principal None · eventos delta=0
      H-05 con el que queda ausente ....... 0 senales
```

### Producción — foto de cierre

**[MEDIDO]** Solo `SELECT`, `read_only = True`. **15 claves → DIFERENCIAS:
NINGUNA.**

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
OrdenTrabajo 3 · AsignacionTrabajo 3 (1 persona) · EventoTrabajo 12
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
PropuestaSupervisor 0 · teams 0 · Profile 5 · Disponibilidad 0
operaciones_externas 0 · kill switch detenido · tenant_config rapilink v146

CHECK sobre campo_asignacion_trabajo: 0   (el de N4 fue en la base AISLADA)
```

---

```
codigo ......... 0 archivos modificados    pruebas ... 0 (el temporal se borro)
migraciones .... 0    modelos .... 0    endpoints .... 0    constraints .... 0
M09 ............ sin tocar    revisar_coherencia ... sin tocar
AsignacionTrabajo  sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no

VEREDICTO F-B .. NO-GO   (13/13 criterios; 1 decision empresarial abierta: §10)
```
