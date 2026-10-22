# K-03 — Estados operativos que implican trabajo ya iniciado

## Identificación

| | |
|---|---|
| **ID** | K-03 |
| **Nombre** | Estados operativos que implican trabajo ya iniciado |
| **Versión** | v1 |
| **Estado** | **VIGENTE** |
| **Fecha efectiva** | 2026-09-17 |
| **Habilidades relacionadas** | H-03 (`orden_sin_programar`), H-02 (`dato_incompleto`) |
| **Señal relacionada** | `orden_sin_programar` |

---

## Propósito

Que quede escrito **cuáles de los siete estados operativos de una orden de
trabajo significan que el trabajo ya arrancó**, y por qué esa distinción evita
un falso positivo concreto y medido.

Es el único de los cinco documentos cuyas reglas están **completamente
respaldadas** por el modelo y la máquina de estados: aquí no hay ningún umbral
que decidir.

---

## Alcance

`campo_orden_trabajo.estado_operativo` y su relación con
`operaciones.ProgramacionOrden`.

## Fuera de alcance

- No cubre el eje de **validación** (`estado_validacion`), que es otro eje.
- No define cuándo debe programarse una orden.
- No define capacidad — eso es **K-02**, pendiente.

---

## Fuentes

| # | Fuente | Qué aporta | Clasificación |
|---|---|---|---|
| F-1 | `campo/models.py` → `OrdenTrabajo.ESTADOS_OPERATIVOS` | los 7 estados y sus etiquetas | **[DOCUMENTADO]** |
| F-2 | `campo/services/transiciones.py` | la máquina de estados | **[DOCUMENTADO]** |
| F-3 | `operaciones/supervisor.py::_ordenes_sin_programar` (docstring) | el razonamiento completo | **[DOCUMENTADO]** |
| F-4 | Producción, 2026-09-17 | las 3 OT reales y sus estados | **[MEDIDO]** |
| F-5 | M09-E §G.2 | la medición de los 3 falsos positivos suprimidos | **[MEDIDO]** |

---

## Definiciones

| Término | Definición | Fuente |
|---|---|---|
| **Estado operativo** | dónde está el trabajo en el terreno | F-1 |
| **Trabajo iniciado** | el técnico ya salió del estado `asignada` | F-2 |
| **Programación vigente** | `ProgramacionOrden` en `planificada` o `confirmada` | F-3 |

---

## Reglas

### R-1 · Los siete estados — HECHO

**[DOCUMENTADO]** (F-1):

| Estado | ¿Trabajo iniciado? |
|---|:--:|
| `asignada` | **NO** |
| `en_camino` | **SÍ** |
| `en_sitio` | **SÍ** |
| `completada_campo` | **SÍ** (y terminado) |
| `correccion_requerida` | **SÍ** (volvió del supervisor) |
| `cerrada` | **SÍ** (y cerrado) |
| `cancelada` | no aplica: no se va a hacer |

### R-2 · `asignada` es el único estado que implica "no arrancó" — REGLA

**[DOCUMENTADO]** (F-3), textual del código:

> *"'estado_operativo = asignada' YA implica que no arrancó: ninguna transición
> vuelve a ese estado (campo/services/transiciones.py) y 'iniciada_en' sólo se
> escribe al salir de él. Por eso no se comprueba aparte — agregarlo sugeriría
> una protección que la máquina de estados ya da."*

**Consecuencia:** el detector filtra `estado_operativo = asignada` y **no**
comprueba `iniciada_en` por separado. No es un olvido: es que sería redundante.

### R-3 · `programada_para IS NULL` **no** significa "sin programar" — REGLA

**[DOCUMENTADO]** (F-3):

> *"ProgramacionOrden y OrdenTrabajo.programada_para son dos cosas distintas y
> NADA las sincroniza — lo dice el propio modelo: la primera es lo que se
> planificó el viernes anterior, la segunda lo que rige ahora mismo. Una orden
> puede estar en el plan semanal con 'programada_para' todavía en NULL."*

### R-4 · La regla se validó contra las órdenes reales — HECHO

**[MEDIDO]** (F-4, F-5). Las 3 órdenes de producción:

```
OT 1842  estado=en_sitio          programada_para=NULL  iniciada_en=SI
OT 1843  estado=en_sitio          programada_para=NULL  iniciada_en=SI
OT 1844  estado=completada_campo  programada_para=NULL  iniciada_en=SI

condición vieja (programada_para IS NULL)  →  3 falsos positivos
condición corregida (R-2 + R-3)            →  0 señales
```

**Las tres órdenes reales del sistema tienen `programada_para` nulo y todas ya
estaban en campo o terminadas.** Sin R-3, el Supervisor habría recomendado
programar trabajo que un técnico ya estaba haciendo.

---

## Procedimiento

**[MEDIDO]** El que ejecuta H-03 hoy:

```
1. Leer el estado operativo de la orden.
2. Si NO es 'asignada' → NO hay señal. (R-1, R-2)
3. Buscar una ProgramacionOrden en 'planificada' o 'confirmada'.
4. Si existe → NO hay señal. (R-3)
5. Si no existe → emitir señal citando el estado y la ausencia del plan.
```

La huella es `estado:<estado_operativo>`: si el estado cambia, es otra condición.

---

## Evidencia requerida

| Para afirmar | Hace falta | Tipo |
|---|---|---|
| que el trabajo no arrancó | `estado_operativo = 'asignada'` | **observado** |
| que no hay plan vigente | ausencia de `ProgramacionOrden` planificada/confirmada | **faltante**, declarado como ausencia |
| cuándo se miró | `observado_en` | **observado** |

**No se puede afirmar**: que alguien omitió programarla, ni que la orden está
retrasada.

---

## Limitaciones e incertidumbre

| # | Limitación |
|---|---|
| L-1 | **Una orden puede estar planificada fuera del sistema** — acordada verbalmente — y no constar |
| L-2 | La ausencia de `ProgramacionOrden` **no distingue** "nadie la planificó" de "se planificó y no se registró" |
| L-3 | **[MEDIDO] Solo hay 3 órdenes reales, las 3 iniciadas.** No hay ninguna orden real en `asignada`: la regla está validada por el lado negativo (no produce falsos positivos), **no** por el positivo |
| L-4 | `en_camino` no aparece en producción: su clasificación viene del modelo (F-1), no de un caso observado |
| L-5 | `correccion_requerida` cuenta como iniciado porque el trabajo se hizo y volvió — **[DISEÑO PROPUESTO]** si el negocio quisiera que vuelva a programarse, sería otra regla y exigiría decisión |

### Cuándo abstenerse

- No emitir señal sobre una orden que no esté en `asignada`.
- No afirmar que falta programación si existe `ProgramacionOrden` vigente, aunque `programada_para` esté vacío.

---

## Excepciones

**[MEDIDO]** `cancelada` queda fuera por R-1: no se va a hacer, no tiene sentido
programarla.

**[PENDIENTE — REGLA NO DEFINIDA]** No hay decisión sobre si una orden en
`correccion_requerida` debe volver al circuito de programación (L-5).

---

## Escalamiento

| Situación | A quién |
|---|---|
| Toda señal `orden_sin_programar` | al Supervisor, siempre |
| **Orden ya en campo sin ningún plan registrado** | **a humano**: el trabajo se está haciendo sin respaldo de planificación |

---

## Prohibiciones

La IA **NO** debe concluir:

- que una orden sin `programada_para` no está programada (R-3);
- que alguien omitió programarla;
- que una orden iniciada está fuera de plan;
- proponer una fecha o un técnico — **M03 es el dueño de ese efecto**.

---

## Ejemplos

**[MEDIDO]** De la validación M09-E, 10 escenarios:

| Escenario | Estado | Plan | Resultado |
|---|---|---|---|
| A | asignada | ninguno | **señal** ✔ |
| B | asignada | borrador | sin señal ✔ |
| C | asignada | publicado | sin señal ✔ |
| D | asignada | programada | sin señal ✔ |
| E | **en_sitio** | — | **sin señal** ✔ |
| F | **completada_campo** | — | **sin señal** ✔ |
| G | cancelada | — | sin señal ✔ |
| H | **correccion_requerida** | — | **sin señal** ✔ |
| I | asignada | línea reprogramada | **señal** ✔ |
| J | asignada | línea cancelada | **señal** ✔ |

---

## Versionado

**v1** — versión inicial. Documenta la regla vigente desde M09-D.

**Qué haría falta para una v2:** una decisión sobre L-5
(`correccion_requerida`), o un cambio en la máquina de estados de `campo`.
