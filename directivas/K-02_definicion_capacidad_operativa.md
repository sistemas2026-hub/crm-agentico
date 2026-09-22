# K-02 — Definición de capacidad operativa

## Identificación

| | |
|---|---|
| **ID** | K-02 |
| **Nombre** | Definición de capacidad operativa |
| **Versión** | — (no hay versión: el documento no se pudo construir) |
| **Estado** | **[PENDIENTE — INFORMACIÓN OPERATIVA INSUFICIENTE]** |
| **Fecha efectiva** | — |
| **Habilidades relacionadas** | H-05 (`orden_con_riesgo_operacional`) — **BLOQUEADA** |
| **Señal relacionada** | `orden_con_riesgo_operacional` |

---

# ESTE DOCUMENTO NO SE PUDO ESCRIBIR

Y no debe rellenarse con conocimiento genérico.

---

## Por qué

**[MEDIDO]** Los datos que harían falta para definir capacidad operativa **no
existen**:

```
asistente / operaciones_disponibilidad (DisponibilidadTecnico)   0 filas
campo_orden_trabajo                                              3 filas
  de esas, con programada_para                                   0
```

**[DOCUMENTADO]** M09-E clasificó H-05 como **NO VALIDABLE POR FALTA DE DATOS**,
y esa clasificación fue aprobada.

**[DOCUMENTADO]** M09-J la dejó bloqueada y M09-K la registró con
`estado = "bloqueada"`, con dos pruebas que verifican que siga así.

**[DOCUMENTADO]** El encargo de D-3, §18, es explícito: *"No definir capacidad
operativa en D-3."*

---

## Qué información falta

Para escribir K-02 con evidencia haría falta, como mínimo:

| # | Falta | Por qué sin eso no se puede |
|---|---|---|
| 1 | **Qué es una unidad de capacidad** | ¿un técnico-día? ¿una hora de cuadrilla? ¿una orden? Sin unidad no hay medida |
| 2 | **Cuánto rinde una unidad** | ¿cuántas órdenes hace una cuadrilla por día? No hay ninguna medición |
| 3 | **Cómo se registra la disponibilidad** | `DisponibilidadTecnico` existe y tiene **0 filas**: el mecanismo está, el dato no |
| 4 | **Qué cuenta como ausencia** | vacaciones, licencia, media jornada: sin catálogo no hay resta |
| 5 | **Si la capacidad varía por tipo de trabajo** | una instalación y un correctivo no cuestan lo mismo, y no hay dato que lo diga |
| 6 | **Qué margen se considera riesgo** | ¿90% de ocupación es riesgo? ¿110%? **Es una decisión de negocio, no un cálculo** |

---

## Lo que NO se va a hacer

> **[RIESGO]** La tentación evidente es derivar un umbral de los datos: mirar
> cuántas órdenes se hicieron por día y llamar a eso "capacidad".
>
> **Eso sería convertir un patrón observado en política**, que es exactamente lo
> que la regla de no invención prohíbe. Y con **3 órdenes** en total, ni siquiera
> habría patrón que observar.

No se define capacidad. No se propone un umbral. No se escribe un procedimiento
que dependa de una definición inexistente.

---

## Estado de la habilidad H-05

**[MEDIDO]** El detector `_ordenes_en_riesgo` **existe y corre**. Lo que falta no
es código: es el conocimiento para poder confiar en su resultado.

**[MEDIDO]** La ficha H-05 lo declara así, y su incertidumbre lo dice:

> *Sin definición de capacidad, cualquier umbral sería arbitrario y la señal no
> sería defendible ante quien la reciba.*
>
> *Con 0 filas de disponibilidad, la ausencia de señal no significa ausencia de
> riesgo.*

---

## Escalamiento

**A decisión humana.** Los seis puntos de "Qué información falta" son decisiones
de negocio: ninguno se resuelve midiendo.

---

## Prohibiciones

La IA **NO** debe:

- inferir capacidad a partir de órdenes históricas;
- proponer un umbral de ocupación;
- tratar `DisponibilidadTecnico` vacío como "hay capacidad";
- tratar la ausencia de señal de H-05 como ausencia de riesgo.

---

## Dependencia

**D-4.** Hasta que D-4 defina capacidad operativa, este documento permanece sin
escribir y H-05 permanece bloqueada.

---

# Actualización tras D-4 — 2026-09-17

**Estado: sigue PENDIENTE.** D-4 no pudo definir capacidad operativa, y **no
debía**: las once decisiones que faltan son de negocio, no de medición.

Lo que D-4 **sí** resolvió, y cambia cómo hay que leer este documento:

## 1. H-05 no necesita capacidad

**[MEDIDO]** El detector `_ordenes_en_riesgo` **no calcula capacidad**. Su
docstring lo dice:

> *"Órdenes programadas cuyo técnico principal está declarado ausente ese día."*

Es una **detección de conflicto directo**, no una estimación. De los seis datos
que este documento declaró faltantes, **usa uno**: que exista una fila de
`DisponibilidadTecnico` con `disponible=False`.

| # | Dato faltante | ¿Lo necesita el detector? |
|:--:|---|:--:|
| 1 | Unidad de capacidad | **no** |
| 2 | Rendimiento por unidad | **no** |
| 3 | Registro de disponibilidad | **SÍ — el único** |
| 4 | Catálogo de ausencias | no (solo para medir) |
| 5 | Variación por tipo de trabajo | **no** |
| 6 | Margen de riesgo | **no** |

> **[GAP DE HABILIDAD]** La ficha H-05 se llama *"Estimar riesgo operacional de
> una orden por capacidad"*. **El código no estima capacidad.** El nombre promete
> más de lo que la función hace. Por §30 de D-4, la ficha **no se modificó**.

**Consecuencia:** el punto 3 de la lista de arriba **no es una decisión de
negocio**. La estructura existe y está probada; lo que falta es que alguien
cargue ausencias. Es un acto operativo.

## 2. La composición de la capacidad ya estaba documentada

**[DOCUMENTADO]** `DisponibilidadTecnico` lo dice en su propio docstring:

> *"LA CAPACIDAD NO SE GUARDA ACA, NI EN NINGUN LADO. Un numero de 'capacidad'
> depende de la disponibilidad, de la carga ya asignada, de la duracion estimada
> del tipo de trabajo, de la zona y de los bloqueos. Guardarlo es garantizar que
> quede viejo la proxima vez que cualquiera de esos cinco cambie."*

Lo que falta no es la **estructura** ni la **composición**: son **la unidad y los
valores**.

## 3. Lo que D-4 midió y este documento no sabía

| Hallazgo | Medición |
|---|---|
| **El calendario de la empresa no está configurado** | `business_calendar`: 1 fila, `name="Default"`, `timezone="UTC"` (Colombia es UTC−5), **0 festivos** |
| **No hay duración ni complejidad en ningún lado** | `WorkType` y `WorkTypeVersion` no tienen ningún campo de duración, complejidad ni peso |
| **Hay un solo tipo de trabajo** | `ftth_instalacion`. La pregunta 5 no se puede ni observar |
| **Los roles de cuadrilla sí son un catálogo cerrado** | `tecnico`, `tecnico_lider`, `ayudante`, `chofer`, `supervisor` |
| **El motivo de ausencia es texto libre** | `CharField(255)`; el `help_text` sugiere ejemplos, **no es un catálogo** |

## 4. Qué decisión falta, exactamente

Ver la **matriz de responsabilidad** de
[`D-4_DEFINICION_CAPACIDAD.md`](../D-4_DEFINICION_CAPACIDAD.md) §16: **once
decisiones**, la mayoría del Jefe de Operaciones.

**Este documento pasa a VIGENTE solo cuando estén definidas al menos las cuatro
que sostienen un cálculo**: unidad de capacidad, rendimiento, duración por tipo
de trabajo y margen de riesgo.

## 5. Lo que sigue prohibido

Sin cambios. Y D-4 agrega uno:

- **no tomar la productividad histórica como capacidad normativa.** Si el equipo
  viene trabajando por encima de lo sostenible, tomar eso como capacidad
  convierte la sobrecarga en la norma.
