# K-04 — Guía de redacción sin atribución de culpa

## Identificación

| | |
|---|---|
| **ID** | K-04 |
| **Nombre** | Guía de redacción sin atribución de culpa |
| **Versión** | v1 |
| **Estado** | **VIGENTE** |
| **Fecha efectiva** | 2026-09-17 |
| **Habilidades relacionadas** | **las 14** — H-C4 la aplica; el resto la obedece |
| **Señal relacionada** | todas |

---

## Propósito

Que una demora no se convierta en una acusación.

El sistema mide fechas y estados. **No mide intenciones ni esfuerzo.** Escribir
como si los midiera convierte un dato incompleto en un juicio sobre una persona
real — y el costo de equivocarse **lo paga esa persona**.

---

## Alcance

El texto de toda propuesta: `accion_propuesta`, `motivo`, `impacto`, y la
descripción de cualquier evidencia.

## Fuera de alcance

- No suaviza un hecho cierto. Esto no es una guía para no incomodar.
- No omite un problema real.
- No cubre la comunicación con clientes finales — eso es del motor conversacional.

---

## Fuentes

| # | Fuente | Qué aporta | Clasificación |
|---|---|---|---|
| F-1 | `operaciones/models.py` → `NovedadOperativa.TIPOS` + docstring | el catálogo **cerrado** de causas | **[DOCUMENTADO]** |
| F-2 | `operaciones/supervisor.py` (docstring de módulo) | la regla de no nombrar personas | **[DOCUMENTADO]** |
| F-3 | M09-C | prohibición de `incumplimiento_de_persona` | **[DOCUMENTADO]** |
| F-4 | Validación M09-E, filtro de patrones | la lista de patrones prohibidos | **[MEDIDO]** |
| F-5 | Producción/réplica 2026-09-17 | 52 propuestas revisadas, 0 con atribución | **[MEDIDO]** |

---

## Definiciones — los siete tipos de afirmación

Esta tabla es el núcleo del documento. **No mezclarlos es toda la guía.**

| Tipo | Qué es | Cómo se escribe | Ejemplo |
|---|---|---|---|
| **Hecho observado** | un dato leído tal cual | afirmación directa, citando fuente | *"estado actual: New"* |
| **Dato calculado** | derivado, determinista | afirmación directa, mostrando el cálculo | *"lleva 8 días abierto"* |
| **Causa registrada** | alguien escribió el motivo | **citarlo textual**, atribuyéndolo al registro | *"motivo de bloqueo registrado: falta_material"* |
| **Causa no registrada** | no hay motivo cargado | **declarar la ausencia**, no rellenarla | *"no hay causa registrada"* |
| **Bloqueo** | estado declarado | describir el estado + su causa registrada | *"la actividad está bloqueada; motivo: dependencia"* |
| **Dependencia** | espera por otra cosa | **nombrar la cosa concreta** | *"espera la actividad X, que no terminó"* |
| **Dato faltante** | el campo está vacío | **declarar la ausencia como ausencia** | *"no hay registro de cierre"* |
| **Inferencia** | conclusión que puede ser falsa | **marcarla como tal y declarar la incertidumbre** | *"podría estar detenida; el dato no lo confirma"* |

---

## Reglas

### R-1 · La lista de causas es cerrada — REGLA

**[DOCUMENTADO]** (F-1). Las ocho causas que el sistema reconoce:

```
ausencia · bloqueo · falta_material · dependencia
reprogramacion · cambio_de_prioridad · dato_incompleto
demora_sin_causa_registrada
```

**[DOCUMENTADO]** Textual del modelo, sobre por qué falta una novena:

> *"No existe 'incumplimiento_de_persona', y su ausencia es deliberada. Una
> demora puede ser un bloqueo, un material que no llegó, una dependencia, una
> ausencia, un cambio de prioridad o un dato mal cargado. Con los datos de hoy
> no hay forma de distinguir ninguna de esas de un incumplimiento — y el costo
> de equivocarse lo paga una persona real."*

### R-2 · Cuando solo hay fechas, el nombre de la causa lo dice — REGLA

**[DOCUMENTADO]** (F-1):

> *"'demora_sin_causa_registrada' es lo que se usa cuando solo hay fechas. Su
> nombre dice exactamente lo que se sabe y nada más."*

### R-3 · Una ausencia de dato **nunca** es una causa — REGLA

| ❌ No escribir | ✔ Escribir |
|---|---|
| *"nadie lo atendió"* | *"no hay registro de cierre"* |
| *"el técnico no cargó la evidencia"* | *"la evidencia no está cargada"* |
| *"no se asignó responsable"* | *"no hay responsable asignado"* |
| *"se olvidaron de publicar el plan"* | *"el plan sigue en borrador; `publicada_en` está vacío"* |

La diferencia no es de tono: la izquierda **afirma un sujeto y una acción que el
dato no sostiene**.

### R-4 · Declarar explícitamente lo que NO se afirma — REGLA

**[MEDIDO]** Donde el hecho pueda leerse como acusación, el texto debe decir qué
no está diciendo. Ejemplo real emitido (F-5):

> *"Lleva 8 días abierto sin resolución registrada. **No se afirma que nadie lo
> haya atendido**: solo que el sistema no tiene registro de cierre."*

### R-5 · Patrones prohibidos — REGLA

**[MEDIDO]** (F-4) La validación de M09-E rechaza cualquier texto que contenga:

```
 1. incumpl                  7. irresponsab
 2. negligen                 8. abandon
 3. culpa                    9. ignoro
 4. no quiso                10. no hizo
 5. olvid                   11. fallo el tecnico
 6. descuid                 12. responsable de la demora
```

> **Son 12 patrones.**
>
> **[GAP DE HABILIDAD]** La ficha H-C4 de `operaciones/habilidades.py` dice
> *"13 patrones"*, y los informes M09-E, M09-J y M09-K repiten esa cifra. **Es
> un error de conteo: la lista tiene 12.** Por §17 del encargo de D-3, la ficha
> **no se modificó**; la corrección queda registrada aquí y en el informe de
> implementación. **Este documento es la fuente correcta de la lista.**

### R-6 · La lista es una guarda, no una garantía — REGLA

**[MEDIDO]** Se puede atribuir culpa sin usar ninguna de esas 12 palabras.
*"La actividad sigue sin avanzar desde que se le asignó a Juan"* no contiene
ningún patrón y **es una acusación**. El filtro caza lo obvio; la regla la
aplican R-1 a R-4.

---

## Procedimiento

```
1. Describir la condición observada, con su fuente.
2. Si hay causa registrada  → citarla textual, atribuida al registro.
   Si NO la hay             → decir que no hay causa registrada. NO rellenar.
3. Si el hecho puede leerse como acusación → declarar qué NO se afirma (R-4).
4. Revisar que no aparezca ningún patrón de R-5.
5. Revisar que no aparezca ningún nombre propio como causa.
```

---

## Evidencia requerida

| Para afirmar | Hace falta | Si no está |
|---|---|---|
| una causa | motivo registrado por una persona | **declarar la ausencia** |
| una demora | fechas observadas | no se afirma demora |
| un bloqueo | `estado_operativo` + motivo | citar solo lo que haya |
| una dependencia | la actividad previa **concreta** | no se afirma dependencia |

---

## Limitaciones e incertidumbre

| # | Limitación |
|---|---|
| L-1 | **El filtro de 12 patrones no cubre la paráfrasis** (R-6) |
| L-2 | El sistema **no puede distinguir** una demora justificada de una injustificada. Por eso no lo intenta |
| L-3 | Una causa registrada **puede estar desactualizada o ser incorrecta**: citarla no la valida, la atribuye |
| L-4 | **[MEDIDO]** Los datos son escasos: M02 y M03 tienen 0 filas. La guía se validó sobre 52 propuestas, casi todas de un solo tipo de señal |
| L-5 | Esta guía cubre el texto **generado por código**. Cuando un humano modifica una propuesta (M09-F), su texto **no pasa por este filtro** — es su responsabilidad |

### Cuándo abstenerse

- Si no hay causa registrada, **no proponer una**.
- Si la única evidencia son fechas, usar `demora_sin_causa_registrada` (R-2).
- Ante datos contradictorios, **no concluir**: escalar.

---

## Excepciones

**Ninguna.** No hay situación en la que el Supervisor pueda atribuir
incumplimiento a una persona. Si un humano necesita hacerlo, lo hace él, con su
nombre, por la vía de revisión — y queda auditado como decisión suya.

---

## Escalamiento

| Situación | A quién |
|---|---|
| Causa registrada que contradice los datos | al Supervisor, con ambas versiones |
| Bloqueo que persiste más de un ciclo sin novedad | **a humano** |
| Cualquier situación que parezca exigir nombrar a alguien | **a humano, sin nombrarlo** |

---

## Prohibiciones

La IA **NO** debe:

- usar `incumplimiento_de_persona` ni ninguna variante — **no existe** (R-1);
- nombrar a una persona como causa de una demora;
- convertir una ausencia de dato en una causa (R-3);
- inferir intención, esfuerzo o diligencia;
- usar lenguaje sancionatorio;
- afirmar que un plazo se incumplió mientras **K-01 R-3** siga abierta.

---

## Ejemplos

**[MEDIDO]** Reales, de M09-E:

✔ **Correcto** — declara el hecho y su límite:
> *"Lleva 8 días abierto sin resolución registrada. No se afirma que nadie lo
> haya atendido: solo que el sistema no tiene registro de cierre."*

✔ **Correcto** — cita la causa registrada, atribuida:
> *"La actividad está bloqueada. Motivo registrado: falta_material."*

✔ **Correcto** — declara la ausencia como ausencia:
> *"El plan de la semana sigue en borrador y `publicada_en` está vacío."*

**[MEDIDO]** No hay ejemplos incorrectos reales: las **52 propuestas** revisadas
pasaron el criterio, **0 con atribución de culpa** (F-5). Los ejemplos ❌ de R-3
son construidos para la guía, no textos que el sistema haya producido.

---

## Versionado

**v1** — versión inicial. Consolida reglas que ya estaban dispersas en M09-C, el
docstring de `NovedadOperativa` y el filtro de validación de M09-E.

**Qué haría falta para una v2:** ampliar la lista de patrones, o una decisión
sobre L-5 (texto escrito por humanos al modificar).
