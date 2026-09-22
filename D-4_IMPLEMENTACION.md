# D-4 — Informe

```
ESTADO: PARCIAL

Seis parámetros identificados:   6 / 6
Parámetros definidos:            0 / 6
Parámetros pendientes:           6 / 6

Valores inventados:              0
Cambios de código:               0
Migraciones:                     0
Producción:                      SIN CAMBIOS
Efectos externos:                0

H-05:   DESBLOQUEABLE según su código · BLOQUEADA según su ficha  (ver §3)
K-02:   PENDIENTE
K-01:   PARCIAL — NO TOCADO
B-7:    PENDIENTE — NO TOCADO
```

---

## 1. Por qué PARCIAL

D-4 tenía que responder *"¿qué significa capacidad operativa para Rapilink?"*.
**No se pudo responder, y no debía inventarse.** Las once decisiones que faltan
son de negocio: ninguna se resuelve midiendo.

**Ningún valor fue inventado.** No se propuso ninguna unidad, ningún
rendimiento, ninguna duración, ningún nivel de complejidad, ningún umbral de
ocupación, ninguna definición de sobrecarga.

Lo que sí se logró: **saber exactamente qué falta, quién debe definirlo, y qué
pasa mientras tanto.**

---

## 2. Los seis parámetros

**[MEDIDO]** Recuperados textualmente de K-02, sin sustituir ninguno.

| # | Parámetro | Estado | ¿Estructura? | ¿Datos? |
|:--:|---|---|:--:|:--:|
| 1 | Unidad de capacidad | **PENDIENTE** | no | no |
| 2 | Rendimiento por unidad | **PENDIENTE** | no | no |
| 3 | Registro de disponibilidad | **PENDIENTE** (operativo) | **sí** | **0 filas** |
| 4 | Catálogo de ausencias | **PENDIENTE** | texto libre | — |
| 5 | Variación por tipo de trabajo | **PENDIENTE** | no | 1 tipo |
| 6 | Margen de riesgo | **PENDIENTE** | no | no |

**0 de 6 definidos.** El 3 es el único que no necesita decisión de negocio: la
estructura existe y está probada; falta que alguien la use.

---

## 3. El hallazgo principal

**[MEDIDO]** `_ordenes_en_riesgo` —el detector de H-05— **no calcula capacidad**.
Su docstring lo dice:

> *"Órdenes programadas cuyo técnico principal está declarado ausente ese día."*

Es detección de **conflicto directo**, no estimación. De los seis parámetros,
**usa uno**: que exista una fila de ausencia.

Por eso H-05 tiene dos respuestas distintas:

| | Estado | Qué falta |
|---|---|---|
| **Según su código** | **DESBLOQUEABLE** | que se carguen ausencias — **acto operativo** |
| **Según su ficha** | **BLOQUEADA** | las seis definiciones — **decisiones de negocio** |

> **[GAP DE HABILIDAD]** La ficha se llama *"Estimar riesgo operacional de una
> orden por capacidad"*. El código detecta un conflicto de ausencia. **El nombre
> promete más de lo que la función hace.**
>
> Por §30 **no se modificó la ficha**: hacerlo cambiaría su huella, registrada en
> M09-K, y exige una decisión de versionado que D-4 no tiene mandato para tomar.

---

## 4. Lo que la auditoría midió y no se sabía

| Hallazgo | Medición | Dónde impacta |
|---|---|---|
| **El calendario de la empresa no está configurado** | `business_calendar`: 1 fila, `name="Default"`, `timezone="UTC"` (Colombia es UTC−5), `business_holiday` **0 filas** | §4 de D-4 — cualquier cálculo de jornada estaría corrido 5 h y contaría festivos como hábiles |
| **No hay duración ni complejidad en ningún lado** | `WorkType` / `WorkTypeVersion` sin campo alguno | parámetros 2 y 5 |
| **Un solo tipo de trabajo** | `ftth_instalacion` | el parámetro 5 no se puede ni observar |
| **Roles de cuadrilla: catálogo cerrado** | `tecnico`, `tecnico_lider`, `ayudante`, `chofer`, `supervisor` | ya definido |
| **Técnico principal: único por orden** | `es_principal` con constraint | ya definido |
| **Motivo de ausencia: texto libre** | `CharField(255)`; el `help_text` sugiere ejemplos | parámetro 4 |
| **La composición de la capacidad ya estaba documentada** | docstring de `DisponibilidadTecnico`: *"no se guarda… depende de cinco cosas"* | reduce el problema a unidad + valores |
| **Las 3 asignaciones reales** | todas `tecnico_lider`, `es_principal=True` | H-05 podría operar sobre ellas |

---

## 5. Archivos

### Creados

| Archivo | Qué es |
|---|---|
| `D-4_DEFINICION_CAPACIDAD.md` | la especificación: 18 secciones, matriz de decisiones (23 parámetros) y matriz de responsabilidad (11 decisiones) |
| `D-4_IMPLEMENTACION.md` | este informe |

### Modificados

| Archivo | Cambio |
|---|---|
| `directivas/K-02_definicion_capacidad_operativa.md` | sección *"Actualización tras D-4"* — **sigue PENDIENTE** |

**Sobre `K-02_CAPACIDAD_OPERATIVA.md` (§27):** no se creó. La estructura
documental **ya tiene** `directivas/K-02_definicion_capacidad_operativa.md`, y un
segundo archivo con el mismo contenido sería exactamente la duplicación que D-1
existe para evitar. Se actualizó el que hay.

### NO modificados — verificado

| Área | Estado |
|---|---|
| `operaciones/supervisor.py` | **sin cambios** |
| Los 10 detectores, incluido `_ordenes_en_riesgo` | **sin cambios** |
| `operaciones/habilidades.py` y las 14 fichas | **sin cambios**, huellas intactas |
| `operaciones/models.py` · `PropuestaSupervisor` | **sin cambios** |
| `DisponibilidadTecnico` · `ProgramacionSemanal` · `ProgramacionOrden` | **sin cambios** |
| `AsignacionTrabajo` · `OrdenTrabajo` · `WorkType` | **sin cambios** |
| `business_hours/` · `cases/` | **sin cambios** |
| `nucleo/` completo | **sin cambios** |
| `directivas/K-01`, `K-03`, `K-04`, `K-05` | **sin cambios** |
| Migraciones | **ninguna** |

---

## 6. Comprobación de consistencia (§24)

No se crearon pruebas de comportamiento: no hay código nuevo.

Se corrió la suite existente porque D-3 tiene pruebas que **leen K-02**:

```
384 passed / 0 failed
```

Idéntico al cierre de D-3. Las pruebas que verifican que K-02 declara
`PENDIENTE — INFORMACIÓN OPERATIVA INSUFICIENTE` y que sus habilidades citadas
existen siguen pasando con el texto actualizado.

---

## 7. Producción

# SIN CAMBIOS

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
192 django_migrations · tenant_config v146
DisponibilidadTecnico 0 · OrdenTrabajo 3 · WorkType 1 · business_calendar 1
```

Las únicas operaciones fueron **lecturas** (`read_only=True`) para medir lo del §4.

## 8. Efectos externos

# 0

## 9. Regla de detención (§30)

Se aplicó **cuatro veces**:

| # | Punto que habría exigido inventar | Qué se hizo |
|:--:|---|---|
| 1 | Derivar rendimiento de las órdenes históricas | **no se hizo** — con 3 órdenes no hay patrón, y aunque lo hubiera, productividad ≠ capacidad normativa |
| 2 | Proponer niveles `baja/media/alta` de complejidad | **no se hizo** — se marcó `[DISEÑO PROPUESTO — REQUIERE APROBACIÓN]` solo el *lugar* (`WorkTypeVersion`), sin valores |
| 3 | Corregir la ficha H-05 por el gap del §3 | **no se hizo** — cambiaría su huella; queda registrado |
| 4 | Dar por buena la jornada 09–17 UTC del calendario | **no se hizo** — se reportó como valor semilla sin configurar |

---

## 10. Criterio de éxito (§29)

| Pregunta | ¿Respondida? |
|---|:--:|
| ¿Qué significa capacidad operativa para Rapilink? | **no** — sí su composición (5 insumos) y que no se guarda |
| ¿Qué datos necesita? | **sí** — 11 factores |
| ¿Dónde están esos datos? | **sí** — 6 estructuras identificadas |
| ¿Qué datos faltan? | **sí** — 7 no existen |
| ¿Quién debe definirlos? | **sí** — matriz por cargo |
| ¿Qué reglas están aprobadas? | **sí** — 5 |
| ¿Qué reglas siguen pendientes? | **sí** — 11 |
| ¿Qué NO puede inferir el Supervisor? | **sí** |
| **¿Puede una etapa posterior implementar H-05 sin inventar reglas?** | **SÍ** para lo que el código hace · **NO** para lo que la ficha promete |

Por la primera fila, **D-4 queda PARCIAL**, como el propio §29 exige.

---

## 11. Qué falta, exactamente

| # | Decisión | Responsable | Desbloquea |
|:--:|---|---|---|
| 1 | Unidad de capacidad | Jefe de Operaciones | K-02, sobrecarga |
| 2 | Rendimiento por unidad | Jefe de Operaciones | K-02 |
| 3 | **Procedimiento de carga de disponibilidad** | Jefe de Operaciones | **H-05 según su código** |
| 4 | Catálogo de ausencias | Jefe de Operaciones / RR. HH. | medición |
| 5 | Jornada real y zona horaria | Gerencia | cualquier cálculo de jornada |
| 6 | Calendario de festivos | Administración | ídem |
| 7 | Duración / complejidad por tipo | Jefe de Operaciones | K-02 |
| 8 | Efecto del material | Jefe de Operaciones | K-02 |
| 9 | **Margen de riesgo** | Jefe de Operaciones | cualquier señal de ocupación |
| 10 | Definición de sobrecarga | Jefe de Operaciones | K-02 |
| 11 | Si la ausencia de un ayudante cuenta | Jefe de Operaciones | alcance de H-05 |

**La 3 es la más barata y la que más desbloquea**: no requiere definir nada, solo
decidir quién carga las ausencias y cuándo.

---

## 12. Control de cambios

```
creados:     D-4_DEFINICION_CAPACIDAD.md
             D-4_IMPLEMENTACION.md
modificados: directivas/K-02_definicion_capacidad_operativa.md

código:      0 archivos
migraciones: 0
nucleo/:     sin cambios
producción:  sin cambios
```

**No se hizo commit.** No estaba autorizado.
