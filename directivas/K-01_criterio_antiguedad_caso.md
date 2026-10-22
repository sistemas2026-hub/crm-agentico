# K-01 — Criterio de antigüedad de un caso

## Identificación

| | |
|---|---|
| **ID** | K-01 |
| **Nombre** | Criterio de antigüedad de un caso |
| **Versión** | v1 |
| **Estado** | **PARCIAL — la regla operativa no está definida** |
| **Fecha efectiva** | 2026-09-17 |
| **Habilidades relacionadas** | H-01 (`caso_abierto_antiguo`) |
| **Señal relacionada** | `caso_abierto_antiguo` |

> **Este documento NO define un umbral.** Documenta lo que existe, mide lo que
> hay, y deja explícito que **la regla operativa no está decidida**.

---

## Propósito

Que quien lea una propuesta de tipo `caso_abierto_antiguo` sepa **con qué
criterio se emitió**, y sepa también que ese criterio **no es una política
aprobada** sino una constante de código.

---

## Alcance

Casos del CRM (`public.case`) con `resolved_at` nulo.

## Fuera de alcance

- No define el SLA de la empresa.
- No define incumplimiento.
- No cubre primera respuesta — eso es **K-05**.
- No cubre actividades ni órdenes de trabajo.

---

## Fuentes

| # | Fuente | Qué aporta | Clasificación |
|---|---|---|---|
| F-1 | `operaciones/supervisor.py:95` → `DIAS_CASO_ANTIGUO = 7` | el umbral que usa hoy el detector | **[MEDIDO]** |
| F-2 | `cases/workflow.py:21-26` → `DEFAULT_RESOLUTION_SLA` | tabla de horas de resolución por prioridad | **[DOCUMENTADO]** |
| F-3 | `cases/models.py:434-442` | esa tabla se aplica en `save()` al crear | **[MEDIDO]** |
| F-4 | `PRD.md:592` | *"SLA de primera respuesta / siguiente respuesta — Falta — problema de escala"* | **[DOCUMENTADO]** |
| F-5 | Producción, 2026-09-17, lectura | distribución real de antigüedad | **[MEDIDO]** |

---

## Definiciones

| Término | Definición | Fuente |
|---|---|---|
| **Caso abierto** | `case.resolved_at IS NULL` | F-1 |
| **Antigüedad** | `now() - case.created_at` | F-1 |
| **SLA de resolución** | horas declaradas en `case.sla_resolution_hours` | F-2, F-3 |
| **Caso antiguo** | **no definido operativamente** — ver Reglas | — |

---

## Reglas

### R-1 · El detector usa 7 días — **HECHO, no regla aprobada**

**[MEDIDO]** `DIAS_CASO_ANTIGUO = 7` (F-1). El detector marca un caso cuando
`created_at` es anterior a `now() - 7 días` y `resolved_at` es nulo.

> **[PENDIENTE — REGLA NO DEFINIDA]** No existe ningún documento, configuración
> ni decisión registrada que establezca que **7 días** es el criterio de
> antigüedad de la empresa. Se buscó en `PRD.md`, `SPEC/`, `ARQUITECTURA.md`,
> `CLAUDE.md`, `directivas/`, la configuración del tenant y el código: el número
> aparece **una sola vez**, como constante, sin justificación.
>
> **Es un valor de implementación, no una política.**

### R-2 · El CRM carga un SLA de resolución de 48 h — **HECHO**

**[MEDIDO]** `DEFAULT_RESOLUTION_SLA` (F-2):

```
Low: 72 h   ·   Normal: 48 h   ·   High: 24 h   ·   Urgent: 4 h
```

**[MEDIDO]** En producción, **los 197 casos** tienen `priority = 'Normal'` y por
lo tanto `sla_resolution_hours = 48`, aplicado automáticamente al crear (F-3).

### R-3 · Los dos números **no coinciden** — HECHO

> **[RIESGO — CONTRADICCIÓN ABIERTA]**
>
> | Criterio | Valor | Origen |
> |---|---|---|
> | Detector de M09 | **168 h** (7 días) | constante de código |
> | SLA del propio CRM | **48 h** (2 días) | tabla por prioridad |
>
> **Difieren por 3,5×.** Un caso que el CRM considera fuera de SLA a las 48 h no
> produce ninguna señal de M09 hasta las 168 h.
>
> **Nadie decidió cuál gobierna.** Este documento **no lo decide**.

### R-4 · Un patrón observado no es una política — REGLA

**[DOCUMENTADO]** Ninguna estadística de este documento debe convertirse en
umbral. Que existan casos de cierta antigüedad describe el estado de la
operación; **no dice cuál debería ser el límite**.

---

## Procedimiento

**[MEDIDO]** Lo que el detector hace hoy (F-1):

```
1. Tomar los casos con resolved_at nulo y created_at < (ahora − 7 días).
2. Calcular los días transcurridos.
3. Emitir una señal por caso, citando la fecha de apertura y el estado reales.
4. La huella es 'abierto_sin_resolucion': la magnitud NO entra.
```

**Mientras R-1 siga pendiente**, quien lea una propuesta debe interpretarla como:
*"este caso lleva más de 7 días abierto según el criterio de implementación
vigente"*, y **no** como *"este caso incumplió un plazo"*.

---

## Evidencia requerida

| Para afirmar | Hace falta | Tipo |
|---|---|---|
| que el caso sigue abierto | `resolved_at IS NULL` | **observado** |
| desde cuándo | `created_at` | **observado** |
| cuánto lleva | `now() − created_at` | **calculado** |
| en qué estado está | `case.status` | **observado** |
| por qué esa prioridad | componentes del cálculo | **calculado** |

**No se puede afirmar** con los datos disponibles: que nadie lo atendió, quién
debía atenderlo, ni que se incumplió un plazo.

---

## Limitaciones e incertidumbre

**[MEDIDO]** Estado real al 2026-09-17:

```
casos totales        197
abiertos             128
  < 1 día             12
  1–3 días            29
  3–7 días            50
  7–14 días           37     ← los que el detector marcaría
  > 14 días            0
resolved_at poblado   69 de 197
```

| # | Limitación |
|---|---|
| L-1 | **La ausencia de cierre no prueba ausencia de atención.** Un caso puede haberse atendido por WhatsApp o por teléfono sin que quede registro de resolución |
| L-2 | `first_response_at` está poblado en **4 de 197** — no sirve para medir atención. Ver **K-05** |
| L-3 | **Todos los casos son prioridad `Normal`**: no hay variedad para saber si el criterio debería depender de la prioridad |
| L-4 | **Ningún caso supera los 14 días.** No hay evidencia sobre el comportamiento con casos muy viejos |
| L-5 | La antigüedad no distingue un caso complejo de uno olvidado |
| L-6 | **[DOCUMENTADO]** El volumen es bajo: PRD.md mide *5 días con tráfico, ~5 conversaciones por día*. Un criterio calibrado con este volumen puede no servir con otro |

### Cuándo abstenerse

- **No afirmar incumplimiento.** Ninguna propuesta puede decir que se incumplió un plazo mientras R-1 y R-3 sigan abiertas.
- **No nombrar responsables.** Ver **K-04**.
- **No inferir desatención** de la ausencia de cierre.

---

## Excepciones

**[PENDIENTE — REGLA NO DEFINIDA]** No hay excepciones documentadas. Casos que
plausiblemente las merecerían y sobre los que **no existe decisión**: casos en
espera del cliente, casos pausados, casos dependientes de un tercero.

---

## Escalamiento

| Situación | A quién |
|---|---|
| Toda señal de `caso_abierto_antiguo` | al Supervisor, siempre |
| Toda propuesta | a revisión humana (M09-F) — único camino |
| **La contradicción R-3** | **a decisión humana: es una política, no un cálculo** |

---

## Prohibiciones

La IA **NO** debe concluir:

- que 7 días es el SLA de la empresa;
- que un caso de 7 días incumplió algo;
- que nadie atendió el caso;
- quién debía atenderlo;
- que 48 h es el criterio operativo de M09 (no lo es hoy);
- que un caso cerrado se atendió bien, ni que uno abierto se atendió mal.

---

## Ejemplos

**[MEDIDO]** Texto real emitido en la validación M09-E, que cumple este documento:

```
MOTIVO    Lleva 8 días abierto sin resolución registrada. No se afirma
          que nadie lo haya atendido: solo que el sistema no tiene
          registro de cierre.
EVIDENCIA abierto desde 2026-09-09 (8 dias)   [observado]
          estado actual: New                  [observado]
          base 50 · antiguedad -8             [calculado]
```

Declara el hecho, cita la fuente y **dice explícitamente qué no afirma**.

No se incluyen ejemplos de textos incorrectos: no se produjo ninguno — las 52
propuestas revisadas en M09-E pasaron el criterio.

---

## Versionado

**v1** — versión inicial. No reemplaza a ninguna anterior.

**Qué haría falta para una v2:** una decisión humana sobre R-3 (cuál criterio
gobierna) o sobre R-1 (aprobar un umbral). Ese cambio **sí** sería un cambio de
regla operativa y exigiría versión nueva.
