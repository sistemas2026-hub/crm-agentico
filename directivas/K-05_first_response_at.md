# K-05 — `first_response_at`: qué es, y por qué no se usa

## Identificación

| | |
|---|---|
| **ID** | K-05 |
| **Nombre** | `first_response_at`: qué es, y por qué no se usa |
| **Versión** | v1 |
| **Estado** | **VIGENTE** |
| **Fecha efectiva** | 2026-09-17 |
| **Habilidades relacionadas** | H-01 (lo excluye explícitamente); **todas** por la prohibición |
| **Señal relacionada** | ninguna — **este documento existe para que no se cree una** |

---

## Propósito

Impedir que un campo que *parece* medir la atención se use para afirmar que
alguien no atendió.

Es el único de los cinco documentos cuyo objetivo es **prohibir**, no habilitar.

---

## Alcance

El campo `case.first_response_at` y los campos de SLA de primera respuesta.

## Fuera de alcance

- No cubre el SLA de resolución — eso es **K-01**.
- No prohíbe mostrar el dato: prohíbe **concluir** con él.

---

## Fuentes

| # | Fuente | Qué aporta | Clasificación |
|---|---|---|---|
| F-1 | `cases/models.py` | el campo existe en el modelo | **[DOCUMENTADO]** |
| F-2 | Producción, 2026-09-17 | **4 de 197** poblado | **[MEDIDO]** |
| F-3 | `operaciones/supervisor.py` (docstring de módulo) | la prohibición, ya escrita en código | **[DOCUMENTADO]** |
| F-4 | M09-C | la decisión original | **[DOCUMENTADO]** |
| F-5 | `PRD.md:592` | *"SLA de primera respuesta / siguiente respuesta — Falta"* | **[DOCUMENTADO]** |
| F-6 | `cases/workflow.py:14-19` | `DEFAULT_FIRST_RESPONSE_SLA` por prioridad | **[DOCUMENTADO]** |

---

## Definiciones

| Término | Definición | Fuente |
|---|---|---|
| `first_response_at` | momento de la primera respuesta registrada | F-1 |
| `sla_first_response_hours` | horas de SLA declaradas en el caso | F-6 |

---

## Reglas

### R-1 · El campo existe y está casi vacío — HECHO

**[MEDIDO]** (F-2):

```
casos totales                        197
first_response_at poblado              4      (2,0 %)
sla_first_response_hours poblado     197      (todos = 8 h)
priority                             197      (todos = 'Normal')
```

El **contenedor** está poblado en el 100%; el **contenido** en el 2%.

### R-2 · Su ausencia no prueba nada — REGLA

**[DOCUMENTADO]** (F-3), textual del código de M09:

> *"No hay ninguna [señal] sobre incumplimiento de primera respuesta.
> 'first_response_at' está poblado en 4 de 165 casos (medido el 15/09/2026), así
> que su ausencia no prueba nada: un caso sin ese dato puede haber sido atendido
> en diez minutos. Afirmar un incumplimiento sobre eso sería acusar a alguien de
> algo que el dato no sostiene."*

> **Nota sobre las cifras:** el código dice *4 de 165* (15/09/2026); la medición
> de hoy es *4 de 197*. **El numerador no se movió**: entraron 32 casos nuevos y
> ninguno registró primera respuesta. La conclusión se refuerza.

### R-3 · No se usa para determinar incumplimiento — REGLA

**[DOCUMENTADO]** (F-4). Decisión de M09-C, vigente:
`first_response_at` **no se utiliza** para determinar incumplimientos de SLA.

### R-4 · Si alguna vez hace falta usarlo, se reporta como medición ausente — REGLA

**[DOCUMENTADO]** (F-3):

> *"Si alguna vez hace falta usarlo, se reporta como 'dato insuficiente /
> medición no disponible', nunca como incumplimiento."*

### R-5 · Los valores de SLA son defaults, no una política por caso — HECHO

**[MEDIDO]** (F-6 + F-2). `DEFAULT_FIRST_RESPONSE_SLA`:

```
Low: 24 h   ·   Normal: 8 h   ·   High: 4 h   ·   Urgent: 1 h
```

Los 197 casos son `Normal`, así que **todos** tienen 8 h. Que el valor sea
uniforme en el 100% es la señal de que es **un default aplicado al crear**, no
una decisión tomada caso por caso.

### R-6 · No existe SLA aprobado — HECHO

**[DOCUMENTADO]** (F-5). `PRD.md:592` lista *"SLA de primera respuesta /
siguiente respuesta"* como **"Falta — problema de escala"**, con el razonamiento
de que el volumen real no lo justifica todavía.

> **[PENDIENTE — REGLA NO DEFINIDA]** La tabla de F-6 es un **default de
> implementación**, no una política de servicio aprobada.

---

## Procedimiento

```
1. NO construir ninguna señal a partir de first_response_at.
2. NO usar su ausencia como indicio de nada.
3. Si alguien pide medir primera respuesta:
     a. reportar la cobertura real (hoy 4 de 197);
     b. reportarlo como 'medición no disponible' (R-4);
     c. NO producir un porcentaje de cumplimiento sobre el 2%.
```

---

## Evidencia requerida

| Para afirmar | Hace falta | Estado |
|---|---|---|
| que hubo primera respuesta | `first_response_at` no nulo | disponible en **4 de 197** |
| que NO hubo | **no existe evidencia posible** | — |
| que se incumplió el SLA | una política aprobada **y** cobertura del dato | **ninguna de las dos** |

> **La fila del medio es el documento entero.** No hay ningún dato que permita
> afirmar que un caso no recibió primera respuesta.

---

## Limitaciones e incertidumbre

| # | Limitación |
|---|---|
| L-1 | **Cobertura del 2%.** Cualquier estadística sobre este campo describe 4 casos, no la operación |
| L-2 | **No se sabe por qué está vacío**: puede ser que no se responda, o que la respuesta ocurra por un canal que no lo escribe. Ambas explicaciones encajan con el dato |
| L-3 | Los casos se atienden también por WhatsApp; el CRM puede no registrar esa respuesta como "primera respuesta" |
| L-4 | El SLA de 8 h es un default uniforme (R-5): no refleja una decisión sobre este cliente ni este tipo de caso |
| L-5 | Este documento **no prueba que la atención sea buena ni mala**. Prueba que **el sistema no puede medirla hoy** |

### Cuándo abstenerse

**Siempre, respecto de este campo.** No hay ningún caso en que hoy se pueda
concluir algo sobre primera respuesta.

---

## Excepciones

**Ninguna.** No hay excepción que habilite usar `first_response_at` para afirmar
incumplimiento mientras la cobertura sea del 2% y no exista política aprobada.

---

## Escalamiento

| Situación | A quién |
|---|---|
| Alguien pide una métrica de primera respuesta | **a humano**, con R-1 y L-1 a la vista |
| La cobertura sube de forma sostenida | **a humano**: cambiaría la premisa de este documento |

---

## Prohibiciones

La IA **NO** debe:

- crear una señal de incumplimiento de primera respuesta;
- usar `first_response_at IS NULL` como indicio de desatención;
- calcular tasas de cumplimiento sobre el 2% de cobertura;
- presentar `sla_first_response_hours = 8` como compromiso de servicio;
- concluir nada sobre el desempeño de una persona a partir de este campo.

---

## Ejemplos

✔ **Correcto** — reportar la limitación:
> *"No es posible medir primera respuesta: el dato está disponible en 4 de 197
> casos. Medición no disponible."*

❌ **Incorrecto** — ejemplos construidos, **no producidos por el sistema**:
> *"193 casos incumplieron el SLA de primera respuesta."*
> *"El 98% de los casos no recibió respuesta a tiempo."*

Los dos convierten **un campo vacío** en **un incumplimiento**, que es
exactamente lo que este documento prohíbe. **[MEDIDO]** El sistema nunca los
produjo: no existe ninguna señal que use este campo.

---

## Versionado

**v1** — versión inicial. Consolida una prohibición que ya estaba en el docstring
de `supervisor.py` y en M09-C, y agrega la medición actualizada (4 de 197).

**Qué haría falta para una v2:** que la cobertura suba de forma sostenida **y**
que exista una política de SLA aprobada. **Las dos, no una.**
