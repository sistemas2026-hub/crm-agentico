# D-4 — Definición de capacidad operativa

**Estado:** especificación de negocio. **No se implementó nada.**
**Fecha:** 2026-09-17

**Etiquetas:** **[MEDIDO]** · **[DOCUMENTADO]** · **[DISEÑO]** ·
**[DEPENDENCIA]** · **[RIESGO]** · **[PENDIENTE]**

---

## 0. El hallazgo que reordena el paso

D-4 se abrió para definir capacidad operativa porque K-02 la declaró faltante y
H-05 quedó bloqueada por eso. **La auditoría del código encontró que esas dos
cosas no están tan unidas como parecía.**

**[MEDIDO]** Lo que el detector de H-05 hace hoy, textual de su docstring:

> *"Órdenes programadas cuyo técnico principal está declarado ausente ese día.*
>
> *Es el único cruce entre M03 y M09, y es el que justifica que exista
> DisponibilidadTecnico: sin esa tabla, esta señal no se puede emitir sin
> inventar la ausencia."*

**[MEDIDO]** `_ordenes_en_riesgo` **no calcula capacidad**. No suma horas, no
mide carga, no compara oferta con demanda. Detecta **un conflicto directo**:
hay una orden programada para un día y el técnico principal asignado está
declarado ausente ese día.

| Lo que necesita el detector | ¿Existe? |
|---|---|
| `OrdenTrabajo.programada_para` | **[MEDIDO]** campo existe |
| `OrdenTrabajo.tecnico_principal` | **[MEDIDO]** existe, sale de `AsignacionTrabajo.es_principal` |
| `DisponibilidadTecnico` con `disponible=False` | **[MEDIDO]** estructura existe, **0 filas** |
| Una unidad de capacidad | **no lo usa** |
| Rendimiento por unidad | **no lo usa** |
| Complejidad por tipo de trabajo | **no lo usa** |
| Umbral de ocupación | **no lo usa** |

> **[GAP DE HABILIDAD]** La ficha H-05 se llama *"Estimar riesgo operacional de
> una orden por capacidad"* y su conocimiento requerido dice
> *"PENDIENTE — D-4: definición de capacidad operativa"*.
>
> **El código no estima capacidad.** Detecta un conflicto de ausencia. El nombre
> de la ficha promete más de lo que la función hace.
>
> Por §30 (regla de detención) **no se modificó la ficha**. La discrepancia queda
> registrada aquí y en el informe.

**Consecuencia para este paso:** hay **dos preguntas**, no una.

| | Pregunta | Qué necesita |
|---|---|---|
| **A** | ¿Puede H-05 emitir lo que su código emite? | **una sola cosa: que alguien registre ausencias** |
| **B** | ¿Qué es capacidad operativa para Rapilink? | **las seis decisiones de negocio de K-02** |

D-4 responde A con evidencia y deja B como lo que es: **[PENDIENTE — DECISIÓN
DE NEGOCIO]**, sin inventar ningún valor.

---

## 1. Los seis datos de K-02

**[MEDIDO]** Recuperados textualmente de
[`directivas/K-02`](directivas/K-02_definicion_capacidad_operativa.md). No se
reemplazaron por otra lista.

### 1.1 — Qué es una unidad de capacidad

| | |
|---|---|
| **Definición** | la magnitud en la que se mide la oferta de trabajo |
| **Por qué es necesario** | sin unidad no hay medida: no se puede decir "alcanza" ni "no alcanza" |
| **Fuente actual** | **ninguna** |
| **Valor actual** | — |
| **¿En base de datos?** | **no** |
| **¿En código?** | **no** |
| **¿En configuración?** | **no** |
| **¿En procedimiento?** | **no** |
| **¿En operación real?** | **[PENDIENTE]** no se pudo observar: 3 órdenes, 1 tipo de trabajo |
| **Quién debería definirlo** | Jefe de Operaciones |
| **Impacto si no se define** | no se puede construir ningún indicador de ocupación |

**[DOCUMENTADO]** El modelo ya rechazó *guardar* capacidad, y dice por qué:

> *"LA CAPACIDAD NO SE GUARDA ACA, NI EN NINGUN LADO. Un numero de 'capacidad'
> depende de la disponibilidad, de la carga ya asignada, de la duracion estimada
> del tipo de trabajo, de la zona y de los bloqueos. Guardarlo es garantizar que
> quede viejo la proxima vez que cualquiera de esos cinco cambie."*

> **Eso ya es media respuesta, y conviene reconocerlo:** la *composición* de la
> capacidad está documentada (cinco insumos). Lo que falta son **los valores y
> la unidad**, no la estructura.

### 1.2 — Cuánto rinde una unidad

| | |
|---|---|
| **Definición** | cuánto trabajo absorbe una unidad de capacidad en un período |
| **Por qué es necesario** | sin rendimiento, la unidad no se traduce en trabajo |
| **Fuente actual** | **ninguna** |
| **¿En código?** | **no** — no hay campo de duración ni de estimación en `campo/models.py` |
| **¿En operación real?** | **[MEDIDO]** 3 órdenes en total: **no hay población suficiente para observar un rendimiento** |
| **Quién debería definirlo** | Jefe de Operaciones, con datos de campo |
| **Impacto si no se define** | cualquier cálculo de ocupación sería arbitrario |

> **[RIESGO]** Es el punto donde más fácil sería inventar: mirar órdenes
> históricas y llamar a eso "rendimiento". **Con 3 órdenes no hay patrón**, y
> aunque lo hubiera, K-02 y §16 lo prohíben: productividad observada **no es**
> capacidad normativa.

### 1.3 — Cómo se registra la disponibilidad

| | |
|---|---|
| **Definición** | el mecanismo por el que se declara quién puede trabajar y cuándo |
| **Por qué es necesario** | es el único insumo que H-05 usa hoy |
| **Fuente actual** | **[MEDIDO]** `DisponibilidadTecnico` — **la estructura EXISTE** |
| **Campos** | `profile`, `fecha`, `hora_inicio`, `hora_fin`, `disponible`, `motivo`, `zona` |
| **¿En base de datos?** | **sí, y con 0 filas** |
| **¿En procedimiento?** | **[PENDIENTE]** no hay procedimiento que diga quién carga esto ni cuándo |
| **Quién debería definirlo** | Jefe de Operaciones (el procedimiento), despacho (la carga) |
| **Impacto si no se define** | **H-05 nunca emite**, y su silencio se confunde con "no hay riesgo" |

> **Este es el único de los seis que NO es una decisión de negocio.** La
> estructura está diseñada y probada. Lo que falta es **que alguien la use**.

### 1.4 — Qué cuenta como ausencia

| | |
|---|---|
| **Definición** | el catálogo de motivos por los que alguien no está disponible |
| **Por qué es necesario** | para poder contar, agrupar y distinguir ausencia planificada de imprevista |
| **Fuente actual** | **[MEDIDO]** `DisponibilidadTecnico.motivo` es **texto libre**, `CharField(255)` |
| **Valor actual** | el `help_text` sugiere *"vacaciones, permiso, incapacidad"* — **es una ayuda de formulario, no un catálogo** |
| **¿Catálogo cerrado?** | **no** |
| **Quién debería definirlo** | Jefe de Operaciones / Recursos Humanos |
| **Impacto si no se define** | se puede operar igual —H-05 cita el motivo textual— pero **no se puede agrupar ni medir** |

> **[MEDIDO]** H-05 **no necesita** el catálogo: cita `ausencia.motivo` tal cual,
> que es exactamente lo que K-04 exige para una causa registrada. El catálogo
> hace falta para **medir**, no para detectar.

### 1.5 — Si la capacidad varía por tipo de trabajo

| | |
|---|---|
| **Definición** | si una instalación y un correctivo consumen capacidad distinta |
| **Por qué es necesario** | sin esto, contar órdenes trata todo como equivalente |
| **Fuente actual** | **ninguna** |
| **¿En código?** | **[MEDIDO] no.** `WorkType` y `WorkTypeVersion` **no tienen** ningún campo de duración, complejidad ni peso |
| **¿En operación real?** | **[MEDIDO]** existe **1 solo WorkType**: `ftth_instalacion`. La pregunta no se puede observar |
| **Quién debería definirlo** | Jefe de Operaciones |
| **Impacto si no se define** | cualquier conteo de órdenes es una aproximación sin respaldo |

### 1.6 — Qué margen se considera riesgo

| | |
|---|---|
| **Definición** | a partir de qué nivel de ocupación se debe avisar |
| **Por qué es necesario** | es el umbral que convierte una medición en una señal |
| **Fuente actual** | **ninguna** |
| **Quién debería definirlo** | **Jefe de Operaciones. Es una decisión de tolerancia al riesgo, no un cálculo** |
| **Impacto si no se define** | no se puede emitir ninguna señal basada en ocupación |

**[MEDIDO]** H-05 **no usa umbral**: su condición es binaria (hay ausencia
declarada para ese día, o no).

### 1.7 — Resumen

| # | Dato | ¿Definido? | ¿Lo necesita H-05 hoy? |
|:--:|---|:--:|:--:|
| 1 | Unidad de capacidad | **no** | **no** |
| 2 | Rendimiento por unidad | **no** | **no** |
| 3 | Registro de disponibilidad | **estructura sí, datos no** | **SÍ — es el único** |
| 4 | Catálogo de ausencias | **no** | no (solo para medir) |
| 5 | Variación por tipo de trabajo | **no** | **no** |
| 6 | Margen de riesgo | **no** | **no** |

---

## 2. Capacidad no es solo cantidad de órdenes

**[DISEÑO]** Marco de análisis, **no fórmula**. La fórmula queda
**[PENDIENTE — DECISIÓN DE NEGOCIO]**.

| Factor | ¿Hay dato hoy? | Dónde |
|---|---|---|
| Disponibilidad | **estructura sí, 0 filas** | `DisponibilidadTecnico` |
| Jornada | **[MEDIDO]** 1 calendario, **sin configurar** — ver §4 | `business_calendar` |
| Tiempo operativo | **no** | — |
| Complejidad | **no** | `WorkType` sin campo |
| Desplazamiento | **no** — ver §6 | — |
| Ubicación | **parcial**: `DisponibilidadTecnico.zona`, texto libre | — |
| Tipo de trabajo | **[MEDIDO]** 1 tipo (`ftth_instalacion`) | `WorkType` |
| Bloqueos | **estructura sí, 0 filas** | `NovedadOperativa` |
| Materiales | **no** — ver §7 | — |
| SLA | **[MEDIDO]** existe y opera | `cases/` |
| Programación existente | **estructura sí, 0 filas** | `ProgramacionSemanal/Orden` |

> **[RIESGO]** Convertir esta tabla en una suma ponderada sería inventar once
> valores de golpe. **No se hace.**

---

## 3. Disponibilidad — y con qué no confundirla

**[DISEÑO]** Cuatro conceptos que hoy se nombran parecido:

| Concepto | Qué responde | Dónde vive |
|---|---|---|
| **Disponibilidad** | ¿esta persona puede trabajar el jueves a las 10? | `DisponibilidadTecnico` |
| **Capacidad** | ¿cuánto trabajo cabe? | **no existe, y no se guarda** (§1.1) |
| **Asignación** | ¿quién es responsable de esta orden? | `AsignacionTrabajo` |
| **Programación** | ¿qué se planificó para esta semana? | `ProgramacionSemanal/Orden` |
| **Ruta** | ¿en qué orden se visitan? | **no existe** |

**[MEDIDO]** Lo que la estructura actual ya representa:

| Situación | ¿Se puede representar? |
|---|---|
| vacaciones | **sí** — `disponible=False` + `motivo` |
| incapacidad | **sí** — ídem |
| permiso | **sí** — ídem |
| ausencia imprevista | **sí** — ídem |
| capacitación | **sí** — ídem |
| jornada parcial | **sí** — `hora_inicio`/`hora_fin` |
| descansos | **[PENDIENTE]** representable como franja no disponible; **no hay procedimiento** |
| restricción de zona | **sí** — `zona` (texto libre) |
| **cuadrillas** | **parcial** — la disponibilidad es **por persona**; la cuadrilla se arma en `AsignacionTrabajo` |
| técnico líder / ayudante / chofer | **sí** — `AsignacionTrabajo.ROLES_CUADRILLA`, catálogo cerrado |

**[MEDIDO]** Roles de cuadrilla existentes: `tecnico`, `tecnico_lider`,
`ayudante`, `chofer`, `supervisor`. En producción, las 3 asignaciones son
`tecnico_lider` con `es_principal=True`.

> **[PENDIENTE — DECISIÓN DE NEGOCIO]** Si la ausencia de un **ayudante** afecta
> la capacidad igual que la del **técnico líder**. Hoy H-05 solo mira al
> principal.

---

## 4. Jornada — el calendario existe y **no está configurado**

**[MEDIDO]** `business_calendar` tiene **1 fila**:

```
name        = "Default"
timezone    = "UTC"                     ← Colombia es UTC-5
lunes a viernes  09:00 – 17:00
sábado y domingo cerrado
business_holiday = 0 filas              ← ningún festivo colombiano cargado
```

> **[RIESGO]** `name="Default"`, `timezone="UTC"` y cero festivos son la firma de
> **un valor semilla que nadie configuró**. Un cálculo de jornada sobre este
> calendario estaría corrido **5 horas** y contaría como hábil cualquier festivo.

**[DOCUMENTADO]** No hay que duplicarlo: el modelo lo dice explícitamente —
*"business_hours.BusinessCalendar define el horario de la EMPRESA, y el SLA ya
lo respeta. No dice nada de una persona concreta"*. Los dos niveles ya están
separados y son complementarios.

**[PENDIENTE — DECISIÓN DE NEGOCIO]**

| # | Falta |
|---|---|
| J-1 | La jornada real de Rapilink (¿09–17? ¿sábados?) |
| J-2 | La zona horaria correcta |
| J-3 | El calendario de festivos de Colombia |
| J-4 | Si existen ventanas operativas distintas de la jornada comercial |
| J-5 | Qué debe hacer el Supervisor ante una jornada especial |

---

## 5. Complejidad

**[MEDIDO]** Rapilink **no clasifica las órdenes por complejidad**. No hay campo
de duración, complejidad ni peso en `campo/models.py`.

**[MEDIDO]** Existe **1 solo tipo de trabajo**: `ftth_instalacion` —
*Instalación Fibra Óptica (FTTH)*. Los tipos que K-02 mencionaba —soporte,
reconexión, retiro, mantenimiento— **no existen como `WorkType`**.

> **[DISEÑO PROPUESTO — REQUIERE APROBACIÓN]** Si alguna vez hiciera falta,
> `WorkTypeVersion` sería el lugar natural: ya es versionada e inmutable, así que
> una duración estimada quedaría atada a la versión del tipo de trabajo y no
> cambiaría el significado de una orden vieja.
>
> **No se propone ningún nivel `baja/media/alta` ni ninguna duración.**

---

## 6. Desplazamiento

**[MEDIDO]** Información disponible hoy:

| Dato | ¿Existe? |
|---|---|
| Zona del técnico | **sí**, `DisponibilidadTecnico.zona` — **texto libre** |
| Dirección de la orden | **[PENDIENTE]** no se auditó campo por campo; no hay uso en M09 |
| Coordenadas GPS | **[DOCUMENTADO]** existen en WispHub/SmartOLT, y son **PII con criterio RNF-01**: no se persisten |
| Ruta | **no existe** ninguna estructura |
| Distancia / tiempo de viaje | **no existe** |

> **[DEPENDENCIA]** No hay información suficiente para calcular ni estimar
> desplazamiento. Y la que existiría —GPS— está bajo una restricción de
> privacidad que este paso no puede levantar.
>
> **No se implementa cálculo geográfico.**

---

## 7. Materiales

**[MEDIDO]** No existe ninguna estructura de inventario en el CRM.
**[DOCUMENTADO]** `NovedadOperativa.TIPOS` incluye `falta_material` como
**causa registrable**, pero eso registra un hecho, no un stock.

**[DISEÑO]** Distinción conceptual, **sin regla**:

| Estado | ¿Representable hoy? |
|---|---|
| material disponible | **no** |
| material reservado | **no** |
| material faltante | **como causa**: `falta_material` en una novedad |
| pendiente de preparación | **no** |
| material crítico | **no** |

> **No se inventan reglas de inventario. No se modifica el consumo de
> materiales.** **[PENDIENTE — DECISIÓN DE NEGOCIO]** si el material debe
> afectar la capacidad, y cómo.

---

## 8. Bloqueos — una orden bloqueada no es falta de capacidad

**[DOCUMENTADO]** Regla ya establecida en K-04 y en `NovedadOperativa.TIPOS`:

```
ausencia · bloqueo · falta_material · dependencia
reprogramacion · cambio_de_prioridad · dato_incompleto
demora_sin_causa_registrada
```

**[DOCUMENTADO]** Y el motivo de que no exista una novena, textual del modelo:

> *"No existe 'incumplimiento_de_persona', y su ausencia es deliberada. Una
> demora puede ser un bloqueo, un material que no llegó, una dependencia, una
> ausencia, un cambio de prioridad o un dato mal cargado. Con los datos de hoy no
> hay forma de distinguir ninguna de esas de un incumplimiento — y el costo de
> equivocarse lo paga una persona real."*

**[DISEÑO]** Regla para la capacidad: **una orden detenida por cualquiera de esas
ocho causas no consume ni libera capacidad de forma automática.** Restarla sería
afirmar que el técnico quedó libre; sumarla, que sigue ocupado. **Ninguna de las
dos se puede sostener con el dato.**

---

## 9. SLA — no se crea un segundo motor

**[MEDIDO]** El SLA existente vive en `cases/` y opera sobre **casos**:
`sla_first_response_hours`, `sla_resolution_hours`, con tabla por prioridad en
`cases/workflow.py`. **No se modificó.**

**[MEDIDO]** Las órdenes de trabajo **no tienen SLA propio**.

**[DISEÑO]** Cómo debería influir, conceptualmente: el SLA de un caso **ordena**
qué trabajo es más urgente; **no dice cuánto trabajo cabe**. Son ejes distintos y
no deben fundirse.

> **[DEPENDENCIA]** K-01 dejó abierta una contradicción (7 días vs 48 h) que
> afecta a los casos. **D-4 no la resuelve** (§23) y no depende de ella.

---

## 10. Capacidad semanal y diaria

**[DOCUMENTADO]** M03 estableció: la programación **semanal** es la base, y la
**diaria** es una modificación de ella.

**[DISEÑO]** Qué información necesitaría el plan semanal para representar
capacidad — **conceptual, sin tablas**:

| Necesita | ¿Existe? |
|---|---|
| quiénes están disponibles esa semana | estructura sí, 0 filas |
| cuántas horas por persona | derivable de las franjas |
| qué órdenes están comprometidas | `ProgramacionOrden`, 0 filas |
| cuánto consume cada orden | **[PENDIENTE]** §1.2, §1.5 |
| qué margen es aceptable | **[PENDIENTE]** §1.6 |

**[DISEÑO]** Y para la capacidad **diaria**, qué debería alterarla:

| Evento | Efecto conceptual | ¿Definido? |
|---|---|---|
| novedad | según su tipo | **[PENDIENTE]** |
| ausencia imprevista | resta disponibilidad de ese día | **estructura lista** |
| bloqueo | **ni suma ni resta** (§8) | **[DISEÑO]** |
| reprogramación | mueve el consumo a otro día | **[PENDIENTE]** |
| nueva prioridad | reordena, no cambia el total | **[DISEÑO]** |
| trabajo emergente | consume capacidad no planificada | **[PENDIENTE]** |

**No se implementa ningún algoritmo.**

---

## 11. Sobrecarga

**[PENDIENTE — DECISIÓN DE NEGOCIO]** No existe ninguna definición empresarial
de sobrecarga operativa.

> **[RIESGO]** **Más órdenes no es sobrecarga.** Seis instalaciones en la misma
> cuadra y seis repartidas por la ciudad no son el mismo trabajo, y hoy el
> sistema no puede distinguirlas: no tiene duración, ni complejidad, ni
> desplazamiento.

Definir sobrecarga exige, como mínimo, §1.1, §1.2, §1.5 y §1.6.

---

## 12. Capacidad, productividad, cumplimiento, utilización

**[DISEÑO]** Cuatro cosas distintas que conviene no mezclar:

| Concepto | Qué mide | Es normativo? |
|---|---|---|
| **Capacidad** | cuánto trabajo **cabe** | **sí** — lo define el negocio |
| **Productividad** | cuánto trabajo **se hizo** | no — es observación |
| **Cumplimiento** | si se hizo **lo comprometido** | depende de un compromiso previo |
| **Utilización** | qué parte de la capacidad se **usó** | derivado: exige capacidad definida |

> **[RIESGO]** La productividad histórica **no puede convertirse en capacidad
> normativa** sin decisión de negocio. Si el equipo viene trabajando por encima
> de lo sostenible, tomar eso como capacidad convierte la sobrecarga en la norma.

---

## 13. Capacidad y responsabilidad

**[DOCUMENTADO]** Regla obligatoria, coherente con K-04 y M09-C:

> **Capacidad insuficiente ≠ incumplimiento personal.**

Una demora puede venir de capacidad, bloqueo, dependencia, material,
desplazamiento, prioridad, cambio de programación o información incompleta.
**El sistema no puede distinguirlas**, y por eso no atribuye ninguna.

**[MEDIDO]** H-05 ya cumple esto: su evidencia cita *"el técnico asignado está
ausente ese día: {motivo}"* — declara un hecho registrado, no un juicio. Y la
ausencia es una **causa legítima del catálogo**, no una falta.

---

## 14. Modelo conceptual

**[DISEÑO]** No es un algoritmo. Marca qué hay y qué falta.

```
  Técnico / Cuadrilla            [MEDIDO] AsignacionTrabajo, roles cerrados
        ↓
  Disponibilidad                 [MEDIDO] estructura lista · 0 filas
        ↓
  Jornada                        [MEDIDO] calendario SIN configurar (§4)
        ↓
  Capacidad disponible           [PENDIENTE] falta unidad y rendimiento
        ↓
  Trabajo requerido              [MEDIDO] ProgramacionOrden · 0 filas
        ↓
  Complejidad                    [PENDIENTE] no existe
        ↓
  Desplazamiento                 [DEPENDENCIA] sin información
        ↓
  Bloqueos / dependencias        [DISEÑO] ni suman ni restan (§8)
        ↓
  SLA / Prioridad                [MEDIDO] existe, sobre casos
        ↓
  Capacidad resultante           [PENDIENTE] falta el margen (§1.6)
        ↓
  Recomendación del Supervisor   [MEDIDO] nivel 1: recomienda, no ejecuta
```

**El único camino completo hoy** es el que usa H-05: *Técnico → Disponibilidad →
(conflicto con una orden programada) → Recomendación.* **No pasa por capacidad.**

---

## 15. Matriz de decisiones

| Parámetro | Existe hoy | Fuente | Valor | Tipo | Falta decisión |
|---|---|---|---|---|---|
| Unidad de capacidad | no | — | — | **PENDIENTE** | **sí** |
| Rendimiento por unidad | no | — | — | **PENDIENTE** | **sí** |
| Estructura de disponibilidad | **sí** | `DisponibilidadTecnico` | 7 campos | **MEDIDO** | no |
| Datos de disponibilidad | **no** | ídem | **0 filas** | **MEDIDO** | no — falta **operación** |
| Procedimiento de carga | no | — | — | **PENDIENTE** | **sí** |
| Catálogo de ausencias | no | `motivo` texto libre | — | **PENDIENTE** | **sí** |
| Roles de cuadrilla | **sí** | `ROLES_CUADRILLA` | 5 valores | **MEDIDO** | no |
| Técnico principal | **sí** | `es_principal` | único por orden | **MEDIDO** | no |
| Jornada | **parcial** | `business_calendar` | L–V 09–17 **UTC, sin festivos** | **MEDIDO** | **sí** |
| Zona horaria | **incorrecta** | ídem | `UTC` | **RIESGO** | **sí** |
| Festivos | no | `business_holiday` | **0 filas** | **MEDIDO** | **sí** |
| Complejidad | no | — | — | **PENDIENTE** | **sí** |
| Duración por tipo | no | `WorkTypeVersion` | sin campo | **PENDIENTE** | **sí** |
| Tipos de trabajo | **sí** | `WorkType` | **1**: `ftth_instalacion` | **MEDIDO** | **sí** |
| Desplazamiento | no | — | — | **DEPENDENCIA** | **sí** |
| Zona del técnico | **parcial** | `zona` texto libre | — | **MEDIDO** | **sí** |
| Materiales | no | — | — | **PENDIENTE** | **sí** |
| Bloqueos (catálogo) | **sí** | `NovedadOperativa.TIPOS` | 8 causas | **DOCUMENTADO** | no |
| Efecto del bloqueo en capacidad | no | — | — | **DISEÑO** | **sí** |
| SLA de casos | **sí** | `cases/workflow.py` | 8h / 48h Normal | **MEDIDO** | no (ver K-01) |
| SLA de órdenes | no | — | — | **PENDIENTE** | **sí** |
| Margen de riesgo | no | — | — | **PENDIENTE** | **sí** |
| Definición de sobrecarga | no | — | — | **PENDIENTE** | **sí** |

---

## 16. Matriz de responsabilidad

**[DISEÑO]** Por cargo. **No se nombra a ninguna persona.**

| Decisión | Responsable de definir | Responsable de validar | Estado |
|---|---|---|---|
| Unidad de capacidad | Jefe de Operaciones | Gerencia | **PENDIENTE** |
| Rendimiento por unidad | Jefe de Operaciones | Gerencia | **PENDIENTE** |
| **Procedimiento de carga de disponibilidad** | Jefe de Operaciones | Despacho | **PENDIENTE** |
| Catálogo de ausencias | Jefe de Operaciones / RR. HH. | Jefe de Operaciones | **PENDIENTE** |
| Jornada real y zona horaria | Gerencia | Jefe de Operaciones | **PENDIENTE** |
| Calendario de festivos | Administración | Jefe de Operaciones | **PENDIENTE** |
| Complejidad / duración por tipo | Jefe de Operaciones | Técnica | **PENDIENTE** |
| Efecto del material | Jefe de Operaciones | Almacén | **PENDIENTE** |
| Margen de riesgo | **Jefe de Operaciones** | Gerencia | **PENDIENTE** |
| Definición de sobrecarga | Jefe de Operaciones | Gerencia | **PENDIENTE** |
| Si la ausencia de un ayudante cuenta | Jefe de Operaciones | — | **PENDIENTE** |

---

## 17. Las ocho preguntas del criterio de éxito

| Pregunta | Respuesta |
|---|---|
| **¿Qué significa capacidad operativa para Rapilink?** | **No está definido.** Lo que sí está documentado es su *composición* (5 insumos, §1.1) y que **no debe guardarse** |
| **¿Qué datos necesita?** | Los 11 factores del §2, de los cuales 4 tienen estructura y 7 no existen |
| **¿Dónde están esos datos?** | `DisponibilidadTecnico`, `AsignacionTrabajo`, `business_calendar`, `WorkType`, `ProgramacionOrden`, `NovedadOperativa` |
| **¿Qué datos faltan?** | Unidad, rendimiento, complejidad, duración, desplazamiento, materiales, margen |
| **¿Quién debe definirlos?** | §16 — mayoría en el Jefe de Operaciones |
| **¿Qué reglas están aprobadas?** | Catálogo de causas (8), roles de cuadrilla (5), técnico principal único, capacidad no se guarda, capacidad ≠ culpa |
| **¿Qué reglas siguen pendientes?** | Las 11 del §16 |
| **¿Qué NO puede inferir el Supervisor?** | Capacidad, ocupación, sobrecarga, rendimiento, desplazamiento, ni culpa |

### La pregunta decisiva

> **¿Puede una etapa posterior implementar H-05 sin inventar ninguna regla de
> negocio?**

**SÍ — para lo que H-05 hace hoy.** El detector está implementado, probado y
**no necesita ninguna de las seis definiciones**. Su único requisito es que
`DisponibilidadTecnico` deje de tener 0 filas, y eso es **un acto operativo, no
una decisión de negocio**.

**NO — para lo que su ficha promete.** *"Estimar riesgo operacional por
capacidad"* exige las seis, y ninguna está definida.

---

## 18. Conclusión

**[DISEÑO]** D-4 queda **PARCIAL**, y la distinción es la que vale:

| | Estado |
|---|---|
| **Capacidad operativa como concepto** | **[PENDIENTE]** — 11 decisiones de negocio |
| **K-02** | **PENDIENTE** — no se pudo escribir, por lo mismo |
| **H-05 según su código** | **DESBLOQUEABLE** — falta solo que se carguen ausencias |
| **H-05 según su ficha** | **BLOQUEADA** — promete capacidad, y capacidad no existe |

> **La recomendación que se desprende, y no se ejecuta:** antes de definir
> capacidad, conviene decidir si H-05 debe *seguir llamándose* "riesgo por
> capacidad" o si lo que hace —detectar un conflicto de ausencia— merece su
> propio nombre. Eso es una decisión de diseño de habilidades, **no de D-4**, y
> cambiaría una ficha cuya huella está registrada en M09-K.
