# M03-E3 — Reglas empresariales de secuenciación

**Fecha:** 2026-09-18
**Alcance:** definición empresarial. **0 código, 0 migraciones, 0 modelos, 0 endpoints, producción solo `SELECT`.**

---

## RESUMEN EJECUTIVO

De las seis decisiones, la evidencia del repositorio **cierra una, descarta
opciones en tres, y deja dos enteramente abiertas**. Ninguna se toma por cuenta
propia.

| | Decisión | Resultado |
|---|---|---|
| **E-2** | significado de `secuencia = 0` | **PENDIENTE** — y **A y C son indistinguibles en el modelo actual** |
| **E-1** | empates | **PENDIENTE** — ninguna alternativa descartable con evidencia |
| **E-4** | publicación | **PARCIALMENTE CERRADA por P-4** — no congela; el resto pendiente |
| **E-5** | `revisar_coherencia` | **ERROR descartado por evidencia** — el resto pendiente |
| **E-6** | prioridad | **A descartada por evidencia** — B no probada |
| **E-7** | zona | **PENDIENTE** — pero con una asimetría medida entre las dos `zona` |

### Los dos hallazgos que más pesan

**[MEDIDO] 1 — El modelo no puede distinguir "sin secuenciar" de "posición
primera".** El serializador acepta `secuencia` opcional y **el servicio traduce
`null` a "no la mandes"**, de modo que *"no la envié"* y *"la envié en 0"*
producen la misma fila. Cualquier decisión que necesite separar A de B **exige un
cambio de modelo**, no solo una firma.

**[MEDIDO] 2 — La convención "menor es más urgente" SÍ está viva en este
repositorio, en otro modelo.** `PropuestaSupervisor.prioridad` tiene el mismo
tipo, el mismo default (50) y la misma frase, **y su `Meta.ordering` la aplica**:
`["prioridad", "-created_at"]`, con índice `(org, estado, prioridad)` y una vista
cuyo docstring dice *"las más urgentes primero"*.

> Eso **descarta** que la frase de `ProgramacionOrden.prioridad` sea documentación
> histórica muerta. **No prueba** que sea una política de empresa aprobada.

---

## 1. Estado actual medido

**[MEDIDO]** Producción, solo `SELECT` (`read_only = True`), idéntica a la foto
de M03-E2 — **DIFERENCIAS: NINGUNA**:

```
ProgramacionSemanal ......... 0        ProgramacionOrden ........... 0
secuencia = 0 ............... 0        secuencia > 0 ............... 0
empates mismo día/mismo plan  0        empates mismo día/cualquier plan  0
órdenes con línea ........... 0        líneas por día .............. vacío
django_migrations 192 · PropuestaSupervisor 0 · kill switch detenido
```

> **[RIESGO] No hay evidencia empírica y E3 no puede fabricarla.** Todo lo que
> sigue sale de leer el modelo, los servicios y el código — nunca de observar
> cómo el negocio trata empates reales, porque **no ha habido ninguno**.

**[MEDIDO]** M09 sigue sin usar `secuencia`: **0 coincidencias** en
`supervisor.py`. Confirmado de nuevo en este paso.

---

## 2. E-2 — Significado de `secuencia = 0`

### La evidencia, superficie por superficie

| Superficie | Qué dice sobre el **0** |
|---|---|
| **modelo** | `PositiveSmallIntegerField(default=0)` — **el default es 0**, y **nada dice qué significa** |
| **help_text** | *"Orden dentro de la jornada. NO es una ruta optimizada: es el orden propuesto."* — define **el campo**, no el valor |
| **serializer** | `required=False, min_value=0, allow_null=True, default=None` |
| **servicio** | `**({"secuencia": secuencia} if secuencia is not None else {})` — **`null` ≡ "no la mandes" ≡ `0`** |
| **frontend** | **0 coincidencias** |
| **API** | hasta M03-E2 no era legible; ahora se lee y **el resumen deliberadamente no la interpreta** |
| **documentación** | **0 coincidencias** en PRD, ARQUITECTURA, directivas, docs |
| **consumidores** | los cuatro son *ordenar*. **Ninguno trata el 0 de forma especial** |

**[MEDIDO]** La única aparición de `secuencia == 0` en todo el código no-test es
el **contador** del resumen de E2, que cuenta sin clasificar.

### El hallazgo que condiciona la decisión

**[MEDIDO]** El sistema **no puede distinguir hoy**:

```
el usuario no envió secuencia          →  fila con secuencia = 0
el usuario envió secuencia = null      →  fila con secuencia = 0
el usuario envió secuencia = 0 aposta  →  fila con secuencia = 0
```

> **Las tres intenciones producen el mismo dato.** Eso no es una limitación de la
> decisión: es una limitación del **modelo**.

**[DISEÑO]** Si el negocio elige **A** (*"sin secuenciar"*) o **B**
(*"primera posición"*), la diferencia entre ambas **no es representable** sin
uno de estos cambios, **todos con migración**:

| Opción técnica | Coste |
|---|---|
| hacer `secuencia` nullable | migración; `NULL` = "sin secuenciar", `0` = una posición real |
| centinela (ej. default `32767`) | migración de dato; reinterpreta filas existentes |
| campo booleano aparte | migración; dos campos que pueden divergir |

### La asimetría con `prioridad`, que es evidencia

**[MEDIDO]** Dos campos adyacentes en la misma clase, del mismo autor:

```python
prioridad = PositiveSmallIntegerField(
    default=50, help_text="Menor corre antes. 0 = lo más urgente.")
secuencia = PositiveSmallIntegerField(
    default=0,  help_text="Orden dentro de la jornada. ... es el orden propuesto.")
```

> En `prioridad` **declaró qué significa el 0 y puso el default lejos de él** (50).
> En `secuencia` **hizo del 0 el default y no dijo nada**.
>
> **[DISEÑO]** Esa asimetría **debilita la lectura B** (*"0 = primera posición"*):
> si el autor hubiera querido que el 0 fuera la posición más fuerte, tenía el
> patrón delante y no lo siguió. **No la descarta** —es un indicio de intención,
> no una política— pero no es neutral.

### Veredicto

# E-2 = PENDIENTE DE DECISIÓN EMPRESARIAL

| | Alternativa | Estado |
|---|---|---|
| **A** | *"sin secuenciar"* | **posible**, pero **indistinguible de C con el modelo actual** |
| **B** | *"primera posición"* | **posible**, **debilitada** por la asimetría con `prioridad` |
| **C** | *"valor por defecto sin significado"* | **describe exactamente lo que el código hace hoy** — nada trata el 0 especialmente |
| **D** | otra | — |

**[PENDIENTE]** Y una pregunta que el encargo no listaba y que la decisión
arrastra: **¿debe `secuencia` seguir siendo opcional?** Mientras lo sea, la mitad
de las líneas nacerá con el mismo número.

---

## 3. E-1 — Tratamiento de empates

**[MEDIDO] Punto de partida:** no hay constraint que los impida, el default los
produce, y **hoy no tienen ninguna consecuencia observable** — porque hasta
M03-E2 nadie podía leer la jornada.

### Las cinco alternativas, con sus ocho impactos

#### A — Permitir el empate

| | |
|---|---|
| **efecto operativo** | dos órdenes del día sin orden relativo declarado. El lector ve un orden estable (desempate por `id`) y el resumen le dice `orden_arbitrario` |
| **riesgos** | quien mire la jornada puede **creer** que el orden mostrado es una decisión. Se mitiga con la marca del resumen, ya implementada |
| **programación** | ninguno — es la conducta actual |
| **reprogramación** | ninguno |
| **publicación** | ninguno |
| **lectura** | ya resuelta en E2 |
| **M09** | **ninguno** — no lee `secuencia` |
| **rutas/cuadrillas/capacidad** | ninguno hoy; una futura ruta tendría que aportar su propio criterio |
| **coste** | **cero código** |

#### B — Resolver automáticamente

| | |
|---|---|
| **efecto operativo** | el sistema asigna números a órdenes que nadie ordenó |
| **riesgos** | **inventa una decisión operativa**. Y con el default en 0, *todo* plan no secuenciado sería reescrito completo en su primera publicación o lectura |
| **programación** | habría que definir **cuándo** dispara y **sobre qué conjunto** (¿el día? ¿el día por zona?) |
| **reprogramación** | **chocaría con M03-D3.2**, que decidió arrastrar la secuencia: resolverla automáticamente la pisaría al llegar |
| **publicación** | si dispara al publicar, **reescribe líneas de un plan que ya vieron las cuadrillas** — colisiona con P-4 |
| **lectura** | el orden pasaría a ser una afirmación del sistema, no un dato del usuario |
| **M09** | ninguno directo |
| **futuro** | fija un criterio hoy que una ruta real querrá reemplazar mañana |
| **coste** | alto, y **no reversible**: reescribe datos |

#### C — Pedir al usuario que defina el orden

| | |
|---|---|
| **efecto operativo** | el empate se convierte en una tarea pendiente para una persona |
| **riesgos** | **no hay dónde pedirlo**: no existe pantalla, y la jornada es API |
| **programación** | exigir `secuencia` al programar la volvería obligatoria — **es la pregunta abierta de E-2** |
| **reprogramación** | habría que pedirla otra vez en cada movimiento |
| **publicación** | podría bloquear la publicación hasta que se resuelva — eso es E-5 |
| **lectura** | ya existe la vía para **mostrar** el empate |
| **M09** | ninguno |
| **futuro** | es la única que produce **dato real de intención humana**, que es lo que hoy no existe |
| **coste** | medio en backend, **alto en producto** (R-3: no hay pantalla) |

#### D — Generar alerta

| | |
|---|---|
| **efecto operativo** | alguien se entera de que hay un empate |
| **riesgos** | **¿alerta a quién y dónde?** Hoy la única vía sería M09, y M09 **no se puede modificar** en esta línea de trabajo |
| **publicación** | si la alerta es un hallazgo de `revisar_coherencia`, **es E-5, no E-1** |
| **M09** | **requeriría un detector nuevo** — fuera de alcance |
| **coste** | depende enteramente de dónde viva la alerta |

#### E — Otra

**[PENDIENTE]** El encargo la deja abierta. Una variante que la medición sugiere
como concebible —**permitir el empate y hacerlo visible**— es en realidad **A más
lo que E2 ya construyó**, no una quinta opción.

### Veredicto

# E-1 = PENDIENTE DE DECISIÓN EMPRESARIAL

**[DISEÑO]** Ninguna alternativa se puede descartar con evidencia. Lo que la
medición sí aporta:

- **B choca con dos decisiones ya aprobadas** (M03-D3.2 y P-4);
- **C y D dependen de una superficie que no existe** (pantalla; o un detector de M09);
- **A es la única de coste cero**, y **es lo que el sistema hace hoy**.

> **Que A sea lo barato no la hace correcta.** Se dice porque es un hecho del
> coste, no un argumento a favor.

---

## 4. E-4 — Publicación

### Lo medido, caso por caso

| # | Caso | Qué pasa **hoy** con la secuencia |
|:--:|---|---|
| 1 | plan **BORRADOR** | nada especial |
| 2 | plan **PUBLICADO** | **nada**: `publicar_programacion` no la lee, no la valida, no la congela |
| 3 | **agregar** una OT después de publicar | permitido como **adición formal** (causa obligatoria, D3). La línea nueva toma lo enviado o `0` |
| 4 | **reprogramar** después de publicar | permitido con causa. Caso A conserva la secuencia; caso B la arrastra |
| 5 | cambiar de **día** (mismo plan) | la línea se actualiza; `secuencia` **no está en `update_fields`** → intacta |
| 6 | cambiar de **plan** | la línea nueva **arrastra** la secuencia (M03-D3.2) |

### Lo que P-4 ya decidió

**[DECISIÓN APROBADA — M03-D1.1]**

> *Un `ProgramacionSemanal` publicado **NO queda congelado**. Toda modificación
> posterior debe ser una reprogramación formal o una modificación formal
> equivalente, con trazabilidad.*

**[DISEÑO]** Eso **cierra la forma general de E-4**:

```
A (congela) .......... DESCARTADA por P-4
B (no congela) ....... es la conducta actual, y es coherente con P-4
```

### Lo que P-4 NO decidió

**[MEDIDO]** El enunciado aprobado exige trazabilidad de *"fecha/hora anterior,
fecha/hora nueva, motivo, quién, cuándo"*. **No menciona `secuencia`.**

**[MEDIDO]** Y hoy la pregunta es **inaplicable**: **no existe ninguna operación
que cambie solo la secuencia de una línea.** Ningún endpoint la edita; solo se
fija al programar y se arrastra al reprogramar.

### Veredicto

# E-4 = PARCIALMENTE CERRADA

| | |
|---|---|
| **CERRADO** | publicar **no congela** la secuencia — se sigue de P-4 |
| **[PENDIENTE]** | **¿cambiar *solo* la secuencia de un plan publicado exigirá causa y traza?** La operación no existe todavía, y **la crearía M03-E4** |

---

## 5. E-5 — `revisar_coherencia`

### Por qué la justificación de I-1 NO se traslada

**[MEDIDO]** I-1 es ERROR por una razón concreta:
`supervisor._programacion_vigente` hace `.first()` con `ordering = ["dia",
"secuencia"]`, así que **con dos líneas vigentes de la misma orden devuelve la
obsoleta** y M09 razona sobre un plan que ya no rige, **sin que nada falle**.

**[MEDIDO]** Dos **órdenes distintas** con la misma secuencia **no producen nada
de eso**:

1. `_programacion_vigente` filtra **por una sola orden** — nunca compara líneas de
   órdenes distintas;
2. **M09 no lee `secuencia`** (0 coincidencias, confirmado en este paso).

> **Son dos invariantes distintas y no hay que mezclarlas.** I-1 protege de una
> lectura equivocada; un empate de secuencia **no causa ninguna lectura
> equivocada** en ningún consumidor actual.

### La consecuencia que descarta ERROR

**[MEDIDO]** `secuencia` es opcional con default `0`. **Un plan que nadie
secuenció tiene todas sus líneas empatadas.**

> **Si la duplicidad fuera ERROR, ese plan no se podría publicar nunca.** ERROR
> convertiría la conducta por defecto del sistema en un estado inválido.

**[DISEÑO]** ERROR solo sería viable **junto con** una decisión sobre E-2 que
hiciera que el 0 dejara de ser el estado por defecto — y esa decisión no está
tomada.

### Veredicto

# E-5 = ERROR DESCARTADO POR EVIDENCIA · el resto PENDIENTE

| | Tratamiento | Estado |
|---|---|---|
| **ERROR** | **DESCARTADO** — bloquearía la conducta por defecto, y la razón de I-1 no aplica |
| **WARNING** | **[PENDIENTE]** — exigiría que `revisar_coherencia` tenga dos semánticas: hoy devuelve **una lista de bloqueos**, no de avisos |
| **INFORMACIÓN** | **[PENDIENTE]** — **ya existe**: el resumen de M03-E2 cuenta los empates sin juzgarlos |
| **ningún hallazgo** | **[PENDIENTE]** — es la conducta actual de `revisar_coherencia` |

**[MEDIDO]** Hay prueba que fija la frontera hoy: `test_13b` de M03-E2 comprueba
que dos líneas con la misma secuencia **no** producen ningún hallazgo.

---

## 6. E-6 — Prioridad

### La evidencia que descarta A

**[MEDIDO]** La misma convención existe **dos veces** en el repositorio, y en una
de ellas **está aplicada**:

| | `ProgramacionOrden.prioridad` | `PropuestaSupervisor.prioridad` |
|---|---|---|
| tipo | `PositiveSmallIntegerField` | `PositiveSmallIntegerField` |
| default | **50** | **50** |
| help_text | *"Menor corre antes. 0 = lo más urgente."* | *"Menor es más urgente."* |
| **`Meta.ordering`** | `["dia", "secuencia"]` — **no la incluye** | **`["prioridad", "-created_at"]`** |
| índice | **ninguno** | **`(org, estado, prioridad)`** |
| ¿se calcula? | **no** | **sí** — `supervisor._prioridad(base, componentes)` |
| ¿se aplica? | **NO** | **SÍ** — `PropuestasView` hereda el ordering; su docstring dice *"las más urgentes primero"* |

> **[DISEÑO] Eso descarta la alternativa A** (*"documentación histórica no
> implementada"*). No es una frase muerta heredada de otro sistema: es una
> **convención viva de este repositorio**, aplicada con índice y ordering en un
> modelo hermano, y **replicada campo por campo** en `ProgramacionOrden` sin
> cablear.

### Por qué eso NO prueba B

**[RIESGO]** Lo medido es **la intención del autor del modelo**, no una política
de empresa aprobada. Es exactamente lo que M03-A dejó escrito como trampa a
evitar:

> *"No asumir que una estructura técnica existente representa una política
> empresarial aprobada."*

Y A-3.2 ya evitó esa trampa una vez, con los `cargo` de `tenant_config`.

### Veredicto

# E-6 = A DESCARTADA POR EVIDENCIA · B NO PROBADA · PENDIENTE

**[PENDIENTE]** La pregunta para el negocio, ya acotada: *¿la prioridad de una
línea de plan debe influir en el orden de la jornada — y en qué relación con
`secuencia`: antes, después, o solo como desempate?*

**[DECISIÓN APROBADA]** **No se convirtió `prioridad` en ordenamiento.** Sigue
expuesta por el endpoint de M03-E2 **para que se vea que existe y no ordena**.

---

## 7. E-7 — Zona

**[MEDIDO]** Hay **dos** campos `zona`, y **no significan lo mismo**:

| | `ProgramacionOrden.zona` | `DisponibilidadTecnico.zona` |
|---|---|---|
| tipo | `CharField(128, blank, default="")` | `CharField(128, blank, default="")` |
| help_text | **ninguno** | **`"Zona que cubre en esa franja. Vacío = cualquiera."`** |
| ¿quién la escribe? | `programar_orden` (opcional); se arrastra al reprogramar | `DisponibilidadView` (opcional) |
| ¿quién la **lee** para decidir? | **NADIE** | **NADIE** |
| ¿catálogo? | **no** — texto libre | **no** — texto libre |
| ¿ordena? | **no** | no aplica |

**[DISEÑO] La asimetría es evidencia:** `DisponibilidadTecnico.zona` **tiene una
semántica operativa declarada** (*cobertura*, y el vacío significa *"cualquiera"*).
`ProgramacionOrden.zona` **no tiene ninguna** — ni help_text.

**[MEDIDO]** Y M03-A ya había medido el contexto: **no existe catálogo de zonas**
en ningún sitio, y la agrupación geográfica de facto en el negocio es el `router`
de WispHub, que es otro identificador.

### Veredicto

# E-7 = PENDIENTE DE DECISIÓN EMPRESARIAL

| | Alternativa | Estado |
|---|---|---|
| **A** | dato informativo | **es lo que es hoy**, en las dos tablas |
| **B** | se usará después | plausible — `DisponibilidadTecnico.zona` sugiere cobertura, que es lo que una asignación por zona necesitaría |
| **C** | otra función ya documentada | **la hay, pero solo en disponibilidad**: *"zona que cubre… vacío = cualquiera"*. En la línea de plan, ninguna |

**[PENDIENTE]** Y la pregunta previa que arrastra: **¿debe existir un catálogo de
zonas?** Dos campos de texto libre sin catálogo no se pueden cruzar de forma
fiable — *"Norte"* y *"norte"* son zonas distintas para la base.

**[DECISIÓN APROBADA]** **No se implementó ordenamiento por zona.**

---

## 8. Matriz de escenarios

**[MEDIDO]** Conducta actual, sin proponer cambios:

| Escenario | Secuencia | Empate | Publicación | M09 | Lectura |
|---|---|:--:|---|:--:|---|
| programar sin enviar secuencia | **0** | con cualquier otra en 0 | no la mira | no la mira | visible, marcada `orden_arbitrario` si todas empatan |
| programar enviando secuencia | el valor | si coincide | no la mira | no la mira | visible, ordenada |
| reprogramar mismo plan, otro día | **conserva** | posible en el destino | no la mira | no la mira | visible |
| reprogramar a otro plan | **arrastra** | posible en el destino | no la mira | no la mira | visible; la vieja pasa a `reprogramada` y desaparece de la jornada |
| adición formal a plan publicado | lo enviado o **0** | posible | no la mira | no la mira | visible |
| corrección | igual que normal | posible | no la mira | no la mira | visible |
| contingencia | **no toca ninguna línea** | — | — | — | sin cambio |
| dos órdenes, misma secuencia | permitido | **sí** | **no bloquea** | **ninguno** | contado en `lineas_en_empate` |
| día entero en 0 | permitido | **sí, total** | **no bloquea** | **ninguno** | `orden_arbitrario: true` |
| secuencia NULL | **imposible** — `NOT NULL` | — | — | — | — |
| secuencia negativa | **imposible** — `CHECK >= 0` y `min_value=0` | — | — | — | — |

---

## 9. Impacto sobre M03-E4 / F / G

| Fase | Qué necesita de E3 | ¿Bloqueada? |
|---|---|:--:|
| **M03-E4** | **E-1** (qué hacer con el empate) y **E-2** (qué es el 0). Si además va a permitir editar la secuencia de un plan publicado, necesita la parte pendiente de **E-4** | **SÍ** |
| **M03-F** (cuadrillas) | **E-7** y, antes, la decisión D-1 de M03-A: ¿la cuadrilla es entidad estable o ad-hoc por orden? | **SÍ**, por D-1 |
| **M03-G** (capacidad) | **nada de secuencia**. Depende de duración, complejidad y jornada, que M03-A midió como inexistentes | **SÍ**, por D-2/D-3/D-4 |

**[DEPENDENCIA]** Ninguna de las tres depende de E-5 ni de E-6 para arrancar.

---

## 10. Impacto sobre M09

**[MEDIDO]** **Ninguno.** Confirmado otra vez en este paso: `supervisor.py`
menciona `secuencia` **0 veces**.

**[DISEÑO]** La única exposición sigue siendo indirecta —
`_programacion_vigente().first()` hereda `Meta.ordering`— y está acotada por dos
hechos:

1. la consulta filtra **por una sola orden**;
2. **I-1** impide que una orden tenga dos líneas vigentes.

**[RIESGO]** Anotado desde M03-E2 y sin cambios: **si I-1 se relajara**, ese
`.first()` volvería a ser arbitrario **y nadie lo vería** — porque `Meta.ordering`
no se puede tocar sin generar migración.

**M09 no se modificó.**

---

## 11. Decisiones cerradas

**[DECISIÓN APROBADA — ya vigentes, reafirmadas aquí]**

- `secuencia` = **ORDEN PROPUESTO**. No es ruta, ni distancia, ni tiempo de
  desplazamiento, ni prioridad comercial, ni SLA, ni compromiso de atención.
- **Publicar NO congela** la secuencia *(se sigue de P-4)*.
- **ERROR queda descartado** para la duplicidad de secuencia *(E-5)*.
- **A queda descartada** para `prioridad`: no es documentación muerta *(E-6)*.
- **No se implementó** ordenamiento por `prioridad` ni por `zona`.

---

## 12. Decisiones pendientes

| # | Decisión | Qué la bloquea | Coste de la respuesta |
|:--:|---|---|---|
| **E-2** | ¿qué significa `secuencia = 0`? | falta de evidencia | **A o B exigen MIGRACIÓN**: el modelo no las distingue |
| **E-2b** | ¿`secuencia` debe seguir siendo opcional? | no estaba listada; la arrastra E-2 | serializer, sin migración |
| **E-1** | ¿qué hacer con un empate? A/B/C/D/E | falta de evidencia | A: 0 · B: alto e irreversible · C: alto en producto · D: requiere M09 |
| **E-4b** | ¿cambiar *solo* la secuencia de un plan publicado exige causa? | la operación no existe | la crearía M03-E4 |
| **E-5b** | ¿WARNING, INFORMACIÓN o nada? | falta de evidencia | WARNING exige dar dos semánticas a `revisar_coherencia` |
| **E-6b** | ¿`prioridad` debe ordenar, y en qué relación con `secuencia`? | intención del autor ≠ política | ordering explícito, sin migración |
| **E-7** | ¿`zona` es informativa o se usará? ¿hace falta catálogo? | falta de evidencia | catálogo = modelo nuevo |

---

## 13. Recomendación para M03-E4

**[DISEÑO]** No es una recomendación de **qué decidir**, sino de **en qué orden**
y de **qué se puede hacer mientras tanto**.

### 13.1 El orden de las preguntas es dependencia, no preferencia

```
E-2 (¿qué es el 0?)  →  E-2b (¿sigue siendo opcional?)  →  E-1 (¿qué hacer con el empate?)
                                                            →  E-4b y E-5b
```

> **E-1 no se puede responder bien antes que E-2.** Si el 0 significa *"sin
> secuenciar"*, un día entero en 0 **no es un empate**: es un plan sin ordenar, y
> "resolver el empate" sería la pregunta equivocada. Si el 0 es *"primera
> posición"*, entonces sí hay diez órdenes peleando por el mismo puesto.
>
> **La misma tabla se lee de dos formas incompatibles según E-2.**

### 13.2 Lo que E4 puede hacer sin ninguna firma

**[DISEÑO]**

| | Trabajo | Por qué no necesita decisión |
|---|---|---|
| **1** | **Permitir editar la secuencia de una línea existente** — hoy no hay forma de cambiarla sin reprogramar | es la operación que E-1 y E-4b necesitan para existir. Sin ella, "definir el orden" no es posible ni siquiera a mano |
| **2** | **Exponer `clasificar_ruta` y el resumen en la lectura** *(ya existe)* | — |

**[RIESGO]** El punto 1 tiene un límite: **si la línea está en un plan publicado,
cambiarla es "modificación posterior a la publicación"**, y eso es E-4b. Es
decir: **E4 puede construirlo para borradores sin firma, y necesita E-4b para
publicados.**

### 13.3 Cómo se medirá cada decisión, con lo que E2 ya dejó

**[MEDIDO]** El endpoint de jornada ya devuelve, por día y en total:
`lineas` · `secuencia_cero` · `secuencia_mayor_que_cero` · `lineas_en_empate` ·
`secuencias_empatadas` · `orden_arbitrario`.

> Cualquier regla que E4 implemente se puede medir **antes y después** con la
> misma consulta, sin instrumentación nueva. **Eso era el objeto de E2 y está
> disponible.**

### 13.4 El dato que sigue faltando

**[RIESGO]** **0 planes y 0 líneas en producción**, y las 3 órdenes reales
clasifican como **contingencia**.

> **E-1 y E-2 se van a decidir sin un solo caso observado.** No es un defecto del
> proceso —la decisión hace falta antes de que haya datos— pero conviene que
> quien firme sepa que está definiendo el comportamiento de un fenómeno que
> **nadie ha visto todavía**, y que la vía para observarlo ya existe.

---

```
código ......... 0     modelos ....... 0     migraciones ... 0
endpoints ...... 0     M09 ........... sin tocar
decisiones tomadas por cuenta propia ... 0
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
