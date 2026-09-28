# M09-J — Asistentes especializados y habilidades del Supervisor NOC IA

# ESTADO: DISEÑO / NO IMPLEMENTADO

**Fecha:** 2026-09-17
**Naturaleza:** **auditoría + diseño**. No se modificó código, no se crearon
migraciones, no se tocó la base ni producción, no se crearon tablas ni endpoints,
no se modificaron permisos, no se cambió la autonomía, no se implementó ninguna
habilidad. Contra producción, **solo lecturas**.

**Etiquetas:** **[MEDIDO]** · **[DISEÑO]** · **[DEPENDENCIA]** · **[RIESGO]** ·
**[PENDIENTE]**

---

## 0. El hallazgo que reordena todo el encargo

El encargo pide diseñar asistentes especializados, habilidades, conocimiento y
aprendizaje. La auditoría encontró que **ese sistema ya existe, completo y con
datos reales** — solo que en **otro dominio**.

**[MEDIDO]** Hay **dos sistemas paralelos**, cada uno con su supervisor:

```
SISTEMA A — CONVERSACIONAL  (motor, nucleo/)          ← YA EXISTE Y OPERA
  8 asistentes (roles de IA)  ·  5 habilidades  ·  63 usos
  corpus RAG 21 docs / 427 fragmentos
  supervisor de calidad: asistente.revisiones_supervisor (16)
  aprendizaje: nucleo/habilidades/analista.py
  evaluación: 84 casos dorados

SISTEMA B — OPERACIONAL  (CRM, django-crm/operaciones/)  ← M09, Shadow Mode
  1 supervisor  ·  10 detectores  ·  0 asistentes  ·  0 habilidades formales
  conocimiento: campo 'conocimiento_version' VACÍO
  aprendizaje: decisiones humanas registradas, sin circuito
  evaluación: 83 pruebas (M09-F) + validación M09-E
```

> **La conclusión que debe gobernar el diseño:** no hay que construir el sistema
> de asistentes y habilidades. Hay que **decidir qué del Sistema A se reutiliza
> en el Sistema B, y qué NO debe duplicarse.** Construirlo de nuevo sería el
> error que el propio encargo advierte.

**[RIESGO]** El riesgo principal de este paso no es quedarse corto: es **crear un
segundo sistema de habilidades** que compita con el que ya funciona.

---

# FASE 1 — Auditoría de lo existente

**[MEDIDO]** Todo lo de esta sección se comprobó contra el repositorio y contra
producción.

| Estructura | Ubicación | Propósito real | Quién la usa | Datos reales | Estado | Veredicto |
|---|---|---|---|---|---|---|
| **Habilidades** | `nucleo/habilidades/catalogo.py` | procedimientos que un agente carga cuando hacen falta | motor, vía `cargar_habilidad` | **5 habilidades, 63 usos** | **operativo** | **REUTILIZAR** |
| **Analista de habilidades** | `nucleo/habilidades/analista.py` | detecta qué procedimiento le falta a un agente | operación real | genera `origen='analisis'` | **operativo** | **REUTILIZAR** |
| **Roles de IA (asistentes)** | `asistente.tenant_config.roles` | 8 asistentes especializados | motor | **8 roles, v146** | **operativo** | **REUTILIZAR** |
| **Herramientas** | `tenant_config.herramientas` | catálogo por tenant | motor | **69, 27 de escritura** | **operativo** | **REUTILIZAR** |
| **Corpus / RAG** | `nucleo/recuperacion/`, `corpus/` | referencia semántica | motor | **21 docs, 427 fragmentos** | **operativo** | **REUTILIZAR** |
| **Supervisor de calidad** | `asistente.revisiones_supervisor` | marca buenos/malos ejemplos de conversación | analista | **16 revisiones** | **operativo** | **REUTILIZAR** |
| **Señal de vacíos** | `asistente.unanswered_queries` | preguntas sin respuesta en el corpus | analista | **2.519 filas** | **operativo** | **REUTILIZAR** |
| **Evaluación (casos dorados)** | `evaluacion/rapilink.casos.yaml` | prueba contra el motor real | `cli/evaluar.py` | **84 casos, 9 de humo** | **operativo** | **REUTILIZAR** |
| **Evaluación en base** | `asistente.evaluation_sets/_runs` | corridas persistidas | — | **0 / 0** | **vacío** | evaluar antes de usar |
| **Ejemplos validados** | `asistente.ejemplos_validados` | ejemplos de referencia | — | **0** | **vacío** | **[PENDIENTE]** |
| **Supervisor operativo** | `django-crm/backend/operaciones/` | M09 Shadow Mode | CRM | **0 propuestas en prod** | **operativo, sin datos** | **EVOLUCIONAR** |
| **Detectores M09** | `operaciones/supervisor.py` | 10 señales operativas | M09 | 37 propuestas en réplica | **operativo** | **EVOLUCIONAR a habilidades** |
| **Directivas** | `directivas/` | 1 doc: módulo campo | humanos | 1 archivo | documental | fuera de alcance |
| **PROMPTS / SPEC** | `PROMPTS/`, `SPEC/` | especificación del proyecto | humanos | 1 + 5 archivos | documental | fuera de alcance |
| **Conectores** | `conectores/` | `wisphub.yaml`, `smartolt.yaml` | sondeo | 2 | operativo | reutilizar |
| **App técnicos** | `apps/tecnicos-mobile/` | app móvil de campo | técnicos | 148 archivos | operativo | fuera de alcance |
| **Herramientas propuestas** | `asistente.herramientas_propuestas` | borradores de herramienta | `proponer_herramienta` | **2** | operativo | reutilizar |
| **Verificación de acción** | `asistente.verificaciones_accion` | ¿el efecto ocurrió? | motor | **3** | operativo | **REUTILIZAR** |

### 1.1 — Qué es una habilidad en este proyecto, ya definido

**[MEDIDO]** `nucleo/habilidades/catalogo.py` ya resuelve —y documenta— la
distinción que el encargo pide en la FASE 6:

> *"Una habilidad no ejecuta nada: es texto que entra al prompt. Las garantías
> siguen intactas y donde estaban — listas blancas de campos, precondiciones en
> código, aprobación humana de escrituras. Lo que crece es el ALCANCE (cuánto
> sabe hacer bien), nunca la confianza en lo que el modelo decide por su cuenta."*

Y por qué no es corpus:

1. **Un procedimiento partido deja de ser un procedimiento.** El RAG trae top-k;
   si el paso 4 de 6 no entra, el agente hace 1,2,3,5,6 y nadie se entera.
2. **Se activa por SITUACIÓN, no por parecido.** *"Se me cayó el internet"* no
   comparte una palabra con *"antes de agendar una visita, descartá que la caída
   sea compartida con vecinos del mismo puerto"*. El disparador lo escribe una
   persona (`cuando_usarla`), **no lo calcula un coseno**.

**[MEDIDO]** Esquema real de `asistente.habilidades`:

```
codigo · nombre · cuando_usarla · pasos · roles_permitidos · estado · version
origen · evidencia · motivo_rechazo · aprobada_por · creada_en · aprobada_en
```

**Ya trae lo que el encargo pide inventar:** propietario (`roles_permitidos`),
disparador, procedimiento, evidencia, versión, y un **flujo de aprobación
humana** (`estado`: propuesta → vigente → obsoleta).

---

# FASE 2 — Inventario de asistentes existentes

**[MEDIDO]** **SÍ existen asistentes especializados formalmente.** Son los 8
roles de IA de `tenant_config`, v146.

| Asistente | Área | Orientado a | Tools | Escalada | Campos | Verifica identidad |
|---|---|---|---:|---:|---:|:--:|
| `soporte` | Atención al Cliente | colaborador | **28** | 0 | 25 | ✔ |
| `soporte_tecnico_cliente` | Soporte Técnico | cliente final | **21** | 0 | 15 | ✔ |
| `ventas` | Ventas | cliente final | 15 | 4 | 7 | ✘ |
| `facturacion` | Facturación | colaborador | 11 | 0 | 9 | ✔ |
| `administracion` | Administración | colaborador | 9 | 0 | 7 | ✔ |
| `facturacion_cliente` | Facturación | cliente final | 7 | 4 | 2 | ✔ |
| `configuracion_guiada` | Administración | colaborador | 2 | 0 | 2 | ✔ |
| `cliente_final` | Atención al Cliente | cliente final | 1 | 0 | 0 | ✘ |

**[MEDIDO]** Cada rol declara: `area`, `atiende`, `cargo`, `descripcion`,
`orientado_a`, `puede_consultar` (herramientas), `campos_permitidos` (lista
blanca por entidad), `exige_verificacion`, `deriva_verificacion`,
`motivos_escalada`, `nunca_revelar`.

**[MEDIDO]** Modelo: ninguno declara uno propio — usan el default del tenant.
**[MEDIDO]** Autonomía: ninguno tiene autonomía ejecutiva; las 27 escrituras
pasan por la frontera y el kill switch está DETENIDO.
**[MEDIDO]** Pruebas: **84 casos dorados**, repartidos —
`cliente_final` 38 · `soporte_tecnico_cliente` 13 · `ventas` 11 · `soporte` 10 ·
`facturacion_cliente` 5 · `administracion` 4 · `facturacion` 2 ·
`configuracion_guiada` 1.

### 2.1 — El Supervisor NOC IA **no tiene** asistentes

**[MEDIDO]** M09 tiene un supervisor y **10 detectores**, sin ninguna capa de
asistentes entre medio:

```
_casos_abiertos_antiguos · _actividades_vencidas · _actividades_sin_responsable
_actividades_bloqueadas  · _compromisos_por_vencer · _dependencias_pendientes
_ordenes_sin_programar   · _ordenes_desincronizadas · _programaciones_sin_publicar
_ordenes_en_riesgo
```

**Lo digo explícitamente, como pide el encargo: bajo el Supervisor NOC IA **no
existe** ningún asistente especializado. Los 8 que existen son del sistema
conversacional y **no le reportan**.

---

# FASE 3 — Propuesta de asistentes

### 3.1 — El criterio, antes de los nombres

El encargo exige: *"Los asistentes deben existir porque tengan una
responsabilidad operativa diferenciada y medible."* Aplicado literalmente contra
los datos:

**[MEDIDO]** Cobertura real de datos por dominio (M09-E):

| Dominio | Detectores | Datos reales en producción |
|---|:--:|---|
| **M01 Casos** | 1 | **197 casos · 37 señales validadas** |
| M02 Actividades | 4 | **0 filas** |
| M03 Programación | 3 | **3 OT · 0 disponibilidad** |
| M05 Novedades | 1 | **0 filas** |
| M10 Calidad de dato | 1 | transversal |

> **[DISEÑO] Solo un dominio tiene hoy responsabilidad operativa medible.**
> Crear cuatro o cinco asistentes para dominios con cero filas sería construir
> organigrama para trabajo que todavía no existe — exactamente lo que el encargo
> prohíbe.

### 3.2 — Asistentes que NO deben crearse, y por qué

| Candidato del encargo | Veredicto | Motivo |
|---|---|---|
| Asistente Técnico/NOC | **NO** | **Ya existe**: `soporte_tecnico_cliente`, 21 herramientas, 13 casos dorados. Duplicarlo es el error del §0 |
| Asistente de Atención | **NO** | Ya existe: `soporte` + `cliente_final` |
| Asistente de Cartera | **NO** | Ya existe: `facturacion` + `facturacion_cliente` |
| Asistente de Fidelización | **NO** | **No hay ninguna señal operativa medible** que lo sostenga. Sería un departamento, no una responsabilidad |
| Asistente de Calidad | **NO** | **Ya existe** como `revisiones_supervisor` + `analista.py` en el sistema conversacional |
| Asistente de Reportes/Analítica | **NO** | Las herramientas `agregado` ya calculan; **el código calcula, el modelo compone** (PRD §12.5). Un asistente aquí no agrega responsabilidad |
| Asistente de Instalaciones | **NO todavía** | M03 tiene 3 OT y 0 disponibilidad |

### 3.3 — Lo que sí se propone

**[DISEÑO]** **Un solo asistente nuevo, y solo cuando haya datos. Hoy, ninguno.**

La recomendación honesta tiene dos niveles:

#### Nivel 1 — Implementable ahora: **ningún asistente nuevo**

**[DISEÑO]** Lo que M09 necesita hoy no es una capa de asistentes: es que sus
**10 detectores se formalicen como habilidades operativas** con el mismo contrato
que ya tienen las conversacionales (`cuando_usarla`, `pasos`, `evidencia`,
`estado`, `version`, aprobación humana).

Motivo medido: **un asistente se justifica cuando un dominio tiene varias
habilidades que comparten conocimiento y reglas de escalada.** Hoy el único
dominio con datos (M01) tiene **una** habilidad. Una capa de coordinación sobre
una sola habilidad es coordinación de nada.

#### Nivel 2 — Diseñados, activables cuando haya datos

**[DISEÑO]** Dos asistentes, y ninguno se crea en este paso:

---

### **A-1 · Asistente de Programación Operativa** *(activar cuando M03 tenga datos)*

| | |
|---|---|
| **1. Nombre** | Asistente de Programación Operativa |
| **2. Propósito** | Determinar si el trabajo comprometido tiene cómo ejecutarse |
| **3. Problemas que resuelve** | órdenes sin plan, planes sin publicar, riesgo de incumplimiento por falta de capacidad |
| **4. Qué NO hace** | **no programa, no asigna, no reprograma.** M03 es el dueño del efecto (M09-G §14) |
| **5. Casos de uso** | semana empezada sin plan publicado; OT sin programación vigente; carga > capacidad |
| **6. Entradas** | `OrdenTrabajo`, `ProgramacionSemanal`, `ProgramacionOrden`, `DisponibilidadTecnico` |
| **7. Salidas** | señales con evidencia + prioridad explicada |
| **8. Habilidades** | H-03, H-04, H-05 (FASE 4) |
| **9. Conocimiento** | criterio de publicación semanal; definición de capacidad **[PENDIENTE]** |
| **10. Procedimientos** | qué mirar antes de afirmar que una OT no está programada |
| **11. Herramientas/datos** | **solo lectura** del CRM propio. Ninguna externa |
| **12. Evidencias** | estado del plan, `publicada_en`, estado operativo de la OT, fecha de observación |
| **13. Escala al Supervisor** | siempre: no emite propuestas por su cuenta |
| **14. Escala a humano** | cuando la condición implique reprogramar trabajo comprometido |
| **15. Nivel inicial** | **1 · recomendar** |
| **16. Métricas** | falsos positivos sobre OT ya en campo (la corrección de M09-D suprimió 3 de 3) |

### **A-2 · Asistente de Seguimiento de Compromisos** *(activar cuando M02 tenga datos)*

| | |
|---|---|
| **1. Nombre** | Asistente de Seguimiento de Compromisos |
| **2. Propósito** | Detectar que algo comprometido está por vencer o ya venció |
| **3. Problemas que resuelve** | actividades vencidas, sin responsable, bloqueadas; compromisos por vencer; dependencias |
| **4. Qué NO hace** | **no asigna responsables, no cierra actividades, no atribuye incumplimiento a personas** |
| **5. Casos de uso** | compromiso a < 24 h; actividad vencida sin cierre; cadena de dependencias detenida |
| **6. Entradas** | `ActividadOperativa`, `NovedadOperativa` |
| **7. Salidas** | señales con evidencia |
| **8. Habilidades** | H-06 … H-09 |
| **9. Conocimiento** | qué es un compromiso; catálogo cerrado de causas (`NovedadOperativa.TIPOS`) |
| **10. Procedimientos** | cómo describir una demora **sin** nombrar un culpable |
| **11. Herramientas/datos** | solo lectura del CRM |
| **12. Evidencias** | fecha comprometida real, motivo de bloqueo registrado, actividad previa concreta |
| **13. Escala al Supervisor** | siempre |
| **14. Escala a humano** | cuando el bloqueo lleve más de un ciclo sin novedad |
| **15. Nivel inicial** | **1 · recomendar** |
| **16. Métricas** | % de propuestas cuyo texto pasa el filtro de 13 patrones de atribución de culpa (hoy 100%) |

**[DEPENDENCIA]** Los dos dependen de que M02/M03 tengan datos reales. **[MEDIDO]**
Hoy no los tienen.

---

# FASE 4 — Catálogo de habilidades

**[DISEÑO]** Diez habilidades operativas, derivadas de los 10 detectores que ya
existen y funcionan. **Ninguna se implementa aquí.**

Nivel = **0 o 1**, como exige la FASE 9. Ninguna tiene herramienta de escritura.

| ID | Habilidad | Propietario | Compartida | Nivel |
|---|---|---|:--:|:--:|
| **H-01** | Detectar caso abierto sin resolución registrada | Supervisor (M01) | no | **1** |
| **H-02** | Evaluar completitud de datos de una orden | transversal | **sí** | **0** |
| **H-03** | Determinar si una OT tiene programación vigente | A-1 | no | **1** |
| **H-04** | Detectar plan semanal sin publicar con semana en curso | A-1 | no | **1** |
| **H-05** | Estimar riesgo operacional de una OT por capacidad | A-1 | no | **1** |
| **H-06** | Detectar actividad vencida sin cierre | A-2 | no | **1** |
| **H-07** | Detectar actividad sin responsable asignado | A-2 | no | **1** |
| **H-08** | Detectar actividad bloqueada y citar su causa registrada | A-2 | no | **1** |
| **H-09** | Detectar compromiso próximo a vencer | A-2 | no | **1** |
| **H-10** | Detectar dependencia pendiente que detiene una cadena | A-2 | no | **1** |
| **H-C1** | Calcular y explicar prioridad | transversal | **sí** | **0** |
| **H-C2** | Construir evidencia trazable | transversal | **sí** | **0** |
| **H-C3** | Calcular huella de condición (deduplicación) | transversal | **sí** | **0** |
| **H-C4** | Redactar sin atribuir culpa | transversal | **sí** | **0** |

### Ficha completa — ejemplo: **H-03**

**[DISEÑO]**

| Campo | Contenido |
|---|---|
| **ID** | H-03 |
| **Nombre** | Determinar si una OT tiene programación vigente |
| **Descripción** | Decide si una orden de trabajo está efectivamente planificada, mirando el plan **y** el estado operativo real |
| **Asistente propietario** | A-1 · Programación Operativa |
| **Reutilizable por** | Supervisor directamente, mientras A-1 no exista |
| **Entradas** | `orden_trabajo_id`, `ahora` |
| **Datos requeridos** | `campo_orden_trabajo.estado_operativo`, `programada_para`, `iniciada_en`; `ProgramacionOrden.estado`; `ProgramacionSemanal.estado` |
| **Conocimiento** | qué estados operativos implican que el trabajo ya empezó |
| **Procedimiento** | 1) leer estado operativo; 2) si ya está en campo o terminado → **no hay señal**; 3) buscar `ProgramacionOrden` en `planificada`/`confirmada`; 4) si existe → no hay señal; 5) si no → señal |
| **Herramientas de consulta** | ninguna externa: ORM del CRM propio |
| **Herramientas de escritura** | **ninguna** |
| **Resultado esperado** | señal o ausencia de señal, con motivo |
| **Evidencia obligatoria** | estado operativo citado, existencia/ausencia de `ProgramacionOrden` con su estado, fecha de observación |
| **Reglas** | `programada_para IS NULL` **no** implica sin programar |
| **Restricciones** | no propone fecha; no asigna técnico |
| **Escalamiento** | al Supervisor siempre; a humano si la OT ya está en campo sin plan |
| **Nivel inicial** | **1** |
| **Métrica** | falsos positivos sobre OT ya iniciadas. **[MEDIDO]** la condición corregida suprimió **3 de 3** |

> **[MEDIDO]** H-03 no es hipotética: es exactamente la corrección validada en
> M09-E §G.2. La condición vieja (`programada_para IS NULL`) habría acusado de no
> programadas a las 3 únicas OT reales, que ya estaban en campo.

---

# FASE 5 — Habilidades compartidas

**[DISEÑO]** Cuatro, y el criterio para que lo sean es estricto: **una habilidad
es compartida cuando duplicarla produciría dos verdades distintas sobre el mismo
hecho.**

| ID | Habilidad | Por qué NO puede duplicarse |
|---|---|---|
| **H-C1** | Calcular y explicar prioridad | Dos fórmulas = dos colas distintas. Ya es una sola función: `_prioridad(base, componentes)`, y cada componente queda escrito en la evidencia |
| **H-C2** | Construir evidencia trazable | Ya es `_observacion(fuente, id, dato, observado_en)`. Dos formatos = auditoría ilegible |
| **H-C3** | Calcular huella de condición | **Crítica.** Dos criterios de huella rompen la deduplicación: una propuesta rechazada volvería al día siguiente con otra huella — el defecto que M09-D cerró |
| **H-C4** | Redactar sin atribuir culpa | Es una regla de M09-C, no un estilo. Duplicarla garantiza que una copia se relaje |

**[MEDIDO]** Las cuatro **ya existen como funciones únicas** en `supervisor.py`.
Formalizarlas como habilidades compartidas es documentar lo que ya es cierto, no
refactorizar.

**[DISEÑO]** No se propone como compartida el **análisis de SLA**: `first_response_at`
está poblado en **4 de 165 casos**, y M09-C ya decidió que no se use para
determinar incumplimientos. Una habilidad compartida sobre un dato que no
sostiene la afirmación multiplicaría el error.

---

# FASE 6 — Habilidad ≠ herramienta

**[MEDIDO]** Esta separación **ya está construida y documentada**:

```
HABILIDAD  =  texto (procedimiento) que entra al prompt.  NO ejecuta nada.
HERRAMIENTA=  capacidad de consultar o escribir.          Autorizada aparte.
```

**[MEDIDO]** Las garantías que impiden que una habilidad se convierta en permiso:

| Garantía | Dónde |
|---|---|
| `roles_permitidos` en la habilidad | `asistente.habilidades` |
| `puede_consultar` en el rol | `tenant_config.roles` |
| `campos_permitidos` (lista blanca) | ídem |
| Frontera de efectos externos | `http.py::ejecutar` |
| Kill switch | `asistente.interruptor_autonomia` |
| Idempotencia | `asistente.operaciones_externas` |

> **Una habilidad nueva no concede ninguna herramienta.** Las dos listas son
> independientes y se cruzan en tiempo de ejecución.

**[DISEÑO]** Clasificación de las herramientas que las 14 habilidades propuestas
necesitan:

| Herramienta | Tipo | Efecto externo | Crítica | Aprobación | Autónoma posible |
|---|---|:--:|:--:|:--:|:--:|
| ORM del CRM (lecturas de `case`, `campo_*`, `operaciones_*`) | **lectura** | no | no | no | n/a |
| **Ninguna de escritura** | — | — | — | — | — |

**[MEDIDO]** Las 14 habilidades propuestas necesitan **cero** herramientas de
escritura y **cero** efectos externos. Es coherente con el nivel 0/1 y con el
resultado de M09-E: 52 propuestas, **0 llamadas externas**.

---

# FASE 7 — Conocimiento y procedimientos

**[DISEÑO]** Qué necesita cada grupo de habilidades, y qué falta.

| Habilidades | Conocimiento necesario | ¿Existe? | Estado |
|---|---|---|---|
| H-01 | umbral de "caso antiguo" (7 días) y su justificación | en código, **no documentado** | **incompleto** |
| H-02 | qué campos son obligatorios por tipo de trabajo | `WorkTypeVersion.esquema` | **[MEDIDO]** existe |
| H-03, H-04 | criterio de publicación semanal; estados que implican trabajo iniciado | en código | **incompleto** |
| H-05 | **definición de capacidad de una cuadrilla** | **no existe** | **falta** |
| H-06…H-10 | catálogo cerrado de causas | `NovedadOperativa.TIPOS` | **[MEDIDO]** existe |
| H-C4 | qué es atribuir culpa | M09-C + 13 patrones en la prueba | **incompleto** |

**[MEDIDO]** El campo `PropuestaSupervisor.conocimiento_version` existe y **está
vacío en las 52 propuestas** de M09-E. Es el enganche para esto y no se usa.

**[RIESGO]** **Información contradictoria detectada:** `first_response_at` existe
como campo de SLA y el CRM lo expone, pero M09-C prohíbe usarlo para
incumplimientos porque está poblado en 4 de 165 casos. Un procedimiento futuro
que lo use sin saberlo produciría acusaciones sobre un dato que no las sostiene.
**Debe quedar escrito en el conocimiento, no solo en un informe.**

**[PENDIENTE]** Documentos que habría que escribir — **no se escriben aquí**:

1. Criterio de antigüedad de un caso y por qué 7 días.
2. **Definición de capacidad operativa** (bloquea H-05).
3. Estados operativos que implican trabajo ya iniciado.
4. Guía de redacción sin atribución de culpa.
5. Nota explícita sobre `first_response_at`.

---

# FASE 8 — El Supervisor como orquestador

**[DISEÑO]** Cómo debería funcionar. **No implementado.**

```
  CASO / SEÑAL
       ↓
  SUPERVISOR: normaliza y determina dominio
       ↓
  selecciona ASISTENTE  (o ejecuta la habilidad directamente si no hay asistente)
       ↓
  selecciona HABILIDAD  (por 'cuando_usarla', no por parecido)
       ↓
  ASISTENTE analiza con CONOCIMIENTO + PROCEDIMIENTO + DATOS
       ↓
  produce EVIDENCIA trazable  (H-C2)
       ↓
  devuelve RESULTADO al Supervisor
       ↓
  SUPERVISOR integra, calcula prioridad (H-C1), huella (H-C3), redacta (H-C4)
       ↓
  PROPUESTA  →  REVISIÓN HUMANA  →  [la cadena se corta aquí, a propósito]
```

### Reparto de decisiones

| Decisión | Quién | Por qué |
|---|---|---|
| Qué dominio es | **Supervisor** | es el único con la vista completa |
| Qué habilidad aplica | **Supervisor** | evita que dos asistentes tomen el mismo caso |
| Si la condición se cumple | **Asistente** | es su dominio |
| Qué evidencia se cita | **Asistente** | tiene los datos delante |
| Prioridad | **Supervisor** (H-C1) | una sola fórmula para toda la cola |
| Deduplicación | **Supervisor** (H-C3) | una sola huella |
| Si se emite propuesta | **Supervisor** | el asistente **nunca** emite |
| Aceptar / modificar / rechazar | **Humano** | M09-F |
| Ejecutar | **nadie hoy** | `ejecutar_propuesta` levanta |

### Las tres patologías, y cómo se evitan

**[DISEÑO]**

| Patología | Mecanismo |
|---|---|
| **Dos asistentes resuelven lo mismo** | un dominio → un asistente, y la asignación la hace el Supervisor, no el asistente. La **huella** (H-C3) lo caza aunque falle: dos análisis del mismo hecho producen la misma huella y el segundo se deduplica |
| **Ciclos entre asistentes** | **un asistente no puede invocar a otro.** Solo el Supervisor invoca. El grafo es un árbol de profundidad 1, y un árbol no tiene ciclos |
| **Conflicto entre recomendaciones** | dos señales sobre el mismo objeto **no se fusionan ni se descartan**: se emiten como propuestas separadas con su evidencia, y **decide el humano**. Resolver el conflicto en código exigiría una regla de precedencia que hoy nadie puede justificar |

---

# FASE 9 — Autonomía

**[DISEÑO]** **No se implementa nada.**

| Nivel | Definición | Habilidades propuestas |
|:--:|---|---|
| **0** · observar | detecta y registra, no propone acción | H-02, H-C1, H-C2, H-C3, H-C4 |
| **1** · recomendar | propone con evidencia, **no ejecuta** | H-01, H-03…H-10 |
| 2 · coordinar | — | **ninguna** |
| 3 · ejecutar reversible | — | **ninguna** |
| 4 · crítica | — | **ninguna** |

**[DISEÑO]** Reglas que no admiten excepción:

- **Ningún asistente puede elevar su propio nivel.**
- **Una habilidad tampoco puede elevar el nivel.** Una habilidad es texto; el
  nivel es una propiedad de la organización y la herramienta (M09-I).
- **El nivel es un techo, no una llave** (M09-I): nivel suficiente **no** implica
  herramienta autorizada.
- **[MEDIDO]** Hoy el interruptor es binario y los niveles no existen como
  mecanismo. Ninguna habilidad puede pedir nivel ≥ 2 **porque no hay dónde
  concederlo**.

---

# FASE 10 — Evidencia

**[MEDIDO]** El contrato ya existe y está validado: `CheckConstraint
propuesta_exige_evidencia` + `_observacion(fuente, id, dato, observado_en)`, y
M09-E comprobó las 52 propuestas contra la base: **0 problemas**.

**[DISEÑO]** Taxonomía que falta declarar explícitamente:

| Tipo | Definición | Ejemplo | Cómo debe marcarse |
|---|---|---|---|
| **Dato observado** | leído tal cual | `status = 'New'` | `fuente=<tabla>` |
| **Dato calculado** | derivado de observados, determinista | `8 días abierto` | `fuente=calculo` |
| **Dato inferido** | conclusión que **puede ser falsa** | "parece sin atender" | **`fuente=inferencia`, y debe declarar su incertidumbre** |
| **Dato faltante** | no existe | `publicada_en` vacío | `fuente=ausencia` — **nunca como causa** |
| **Evidencia externa** | de otro sistema | señal de la ONU | `fuente=<sistema>` + hora |
| **Evidencia humana** | la aportó una persona | motivo de bloqueo | `fuente=novedad` + autor |

**[RIESGO]** La distinción que más importa es **dato faltante vs. causa**. *"No
hay registro de cierre"* es un dato faltante; *"nadie lo atendió"* es una causa
inventada a partir de una ausencia. **[MEDIDO]** Las propuestas actuales ya lo
dicen bien: *"No se afirma que nadie lo haya atendido: solo que el sistema no
tiene registro de cierre."*

**[DISEÑO]** Toda recomendación debe poder responder seis preguntas — cinco ya se
responden, **la sexta no**:

| Pregunta | ¿Se responde hoy? |
|---|:--:|
| qué detectó | **[MEDIDO]** sí |
| con qué datos | **[MEDIDO]** sí |
| cuándo | **[MEDIDO]** sí (`observado_en`) |
| qué regla aplicó | **no** — `conocimiento_version` vacío |
| qué recomienda | **[MEDIDO]** sí |
| **qué incertidumbre existe** | **no** — **falta** |

---

# FASE 11 — Evaluación de habilidades

**[DISEÑO]** Plantilla por habilidad. **No se implementan pruebas.**

| Caso | Qué se exige |
|---|---|
| **Exitoso** | la condición se cumple → señal, con evidencia completa |
| **Negativo** | la condición no se cumple → **sin señal** |
| **Ambiguo** | datos parciales → señal **con incertidumbre declarada**, o ninguna |
| **Datos faltantes** | **no inventar**. Puede emitir `dato_incompleto` (nivel 0) |
| **Datos contradictorios** | **no ejecutar ni proponer**; escalar |
| **Evidencia insuficiente** | **no se crea la propuesta** — lo impide la restricción de la base |
| **Debe escalar** | condición con efecto sobre personas |
| **NO debe actuar** | condición ya resuelta, o ya propuesta (huella) |

| Métrica | Definición | Línea base medida |
|---|---|---|
| Precisión | señales correctas ÷ emitidas | **[MEDIDO]** 52/52 sin problemas (M09-E) |
| Evidencia | % con evidencia completa | **[MEDIDO]** 100% |
| Escalamiento | % que escala cuando debía | **[PENDIENTE]** |
| Falsos positivos | señales sobre condición inexistente | **[MEDIDO]** 0 en 14 escenarios |
| Falsos negativos | condiciones no detectadas | **[MEDIDO]** 0 (cruce SQL 37=37) |

**[DISEÑO]** Cómo escribirlas — tres exigencias que vienen de errores ya
cometidos:

1. **Afirmar sobre el EFECTO, nunca sobre la presencia del mecanismo.**
2. **Cada prueba debe fallar si se desarma su guarda.**
3. **"0 señales" no es "correcto"** — puede ser "no había nada que detectar".

---

# FASE 12 — Aprendizaje

**[MEDIDO]** El circuito **ya existe en el sistema conversacional**:

```
conversaciones (302) · mensajes (2.594) · escaladas
        ↓
revisiones_supervisor (16)   buen/mal ejemplo + justificación + aporte_sugerido
unanswered_queries (2.519)   preguntas que el corpus no cubrió
        ↓
nucleo/habilidades/analista.py
   3 señales: escaladas repetidas por el mismo motivo · el agente dijo que no
   tiene el procedimiento · habilidad cargada y escaló igual
        ↓
habilidad en estado 'propuesta'  →  APROBACIÓN HUMANA  →  'vigente'
        ↓
habilidad_usos (63)
```

**[DISEÑO]** El equivalente operativo para M09 — **datos a conservar, sin
aprendizaje automático**:

| Decisión humana | Qué significa | Qué conservar |
|---|---|---|
| **Aceptada** | la recomendación era válida | huella, tipo de señal, evidencia, tiempo hasta revisión |
| **Modificada** | válida pero mal formulada | **`propuesta_original` vs. lo editado** — es la señal más rica |
| **Rechazada** | no era válida, o el revisor sabía algo que el sistema no | **el motivo, obligatorio** |
| **Expirada** | nadie la miró | mide la cola, **no la calidad** |
| **Cancelada** | la condición desapareció sola | **mide si la señal llegó tarde** |

**[MEDIDO]** M09-F ya dejó los datos: `propuesta_original` (copia literal de lo
que la IA propuso), `resultado`, `revisado_en`, y auditoría con antes/después por
campo. **El circuito no existe; los datos para construirlo, sí.**

**[DISEÑO]** La pregunta que debería poder responderse: *"¿qué tan buenas fueron
las recomendaciones?"* — como **tasa por tipo de señal**, no como score de una
persona. Una tasa de rechazo alta puede significar que la IA recomienda mal, que
el revisor tiene contexto que el sistema no, o que la ventana está mal calibrada.
**Un ranking elegiría en silencio la interpretación que más daño hace.**

---

# FASE 13 — Matrices

### Matriz consolidada

| Asistente | Habilidad | Conocimiento | Procedimiento | Datos | Herramientas | Evidencia | Escala | Nivel |
|---|---|---|---|---|---|---|---|:--:|
| Supervisor | H-01 caso antiguo | umbral 7 días **(falta)** | leer estado y resolución | `case` | ORM lectura | fecha, estado, días | Supervisor | 1 |
| transversal | H-02 completitud | `WorkTypeVersion.esquema` | comparar contra esquema | `campo_*` | ORM lectura | campo faltante nombrado | Supervisor | 0 |
| A-1 | H-03 programación vigente | estados iniciados **(falta)** | 5 pasos (ficha) | `campo_*`, `operaciones_*` | ORM lectura | estado + plan | Supervisor | 1 |
| A-1 | H-04 plan sin publicar | criterio semanal **(falta)** | estado + `publicada_en` | `ProgramacionSemanal` | ORM lectura | estado, fecha vacía | Supervisor | 1 |
| A-1 | H-05 riesgo por capacidad | **definición de capacidad (NO EXISTE)** | — | `DisponibilidadTecnico` **(0 filas)** | ORM lectura | — | Supervisor | 1 |
| A-2 | H-06 actividad vencida | — | `vence_en` vs. ahora | `ActividadOperativa` | ORM lectura | fecha real | Supervisor | 1 |
| A-2 | H-07 sin responsable | — | campo vacío | ídem | ORM lectura | ausencia declarada | Supervisor | 1 |
| A-2 | H-08 bloqueada | `NovedadOperativa.TIPOS` | citar causa registrada | ídem | ORM lectura | motivo textual | Supervisor | 1 |
| A-2 | H-09 compromiso | — | ventana 24 h | ídem | ORM lectura | fecha comprometida | Supervisor | 1 |
| A-2 | H-10 dependencia | — | actividad previa | ídem | ORM lectura | previa concreta | Supervisor | 1 |
| transversal | H-C1 prioridad | — | suma de componentes | — | — | cálculo explícito | — | 0 |
| transversal | H-C2 evidencia | — | 4 claves | — | — | la evidencia misma | — | 0 |
| transversal | H-C3 huella | — | identidad ≠ magnitud | — | — | huella | — | 0 |
| transversal | H-C4 redacción | guía **(falta)** | 13 patrones prohibidos | — | — | texto | — | 0 |

### Matriz de asistentes

| Asistente | Propósito | Habilidades | Herramientas | Escala al Supervisor | Humano |
|---|---|---|---|---|---|
| **Supervisor NOC IA** | orquestar, integrar, proponer | H-01 + las 4 transversales | ORM lectura | — | siempre (M09-F) |
| **A-1** *(no crear hoy)* | ¿el trabajo tiene cómo ejecutarse? | H-03, H-04, H-05 | ORM lectura | siempre | si implica reprogramar |
| **A-2** *(no crear hoy)* | ¿lo comprometido va a cumplirse? | H-06…H-10 | ORM lectura | siempre | bloqueo > 1 ciclo |
| **Los 8 conversacionales** | atención por canal | 5 habilidades existentes | 69 del catálogo | **no le reportan** | `motivos_escalada` |

### Matriz de habilidades

| ID | Habilidad | Asistente | Compartida | Evidencia | Nivel |
|---|---|---|:--:|---|:--:|
| H-01 | caso abierto antiguo | Supervisor | no | fecha, estado, días | 1 |
| H-02 | completitud de datos | transversal | **sí** | campo faltante | 0 |
| H-03 | programación vigente | A-1 | no | estado + plan | 1 |
| H-04 | plan sin publicar | A-1 | no | estado + `publicada_en` | 1 |
| H-05 | riesgo por capacidad | A-1 | no | **[PENDIENTE]** | 1 |
| H-06 | actividad vencida | A-2 | no | fecha real | 1 |
| H-07 | sin responsable | A-2 | no | ausencia declarada | 1 |
| H-08 | bloqueada | A-2 | no | causa registrada | 1 |
| H-09 | compromiso por vencer | A-2 | no | fecha comprometida | 1 |
| H-10 | dependencia pendiente | A-2 | no | actividad previa | 1 |
| H-C1 | prioridad | — | **sí** | cálculo | 0 |
| H-C2 | evidencia trazable | — | **sí** | — | 0 |
| H-C3 | huella | — | **sí** | huella | 0 |
| H-C4 | redacción sin culpa | — | **sí** | texto | 0 |

### Matriz de herramientas

| Herramienta | L/E | Asistentes | Habilidades | Efecto externo | Crítica |
|---|---|---|---|:--:|:--:|
| ORM lectura `case` | **L** | Supervisor | H-01 | no | no |
| ORM lectura `campo_*` | **L** | A-1, transversal | H-02, H-03 | no | no |
| ORM lectura `operaciones_*` | **L** | A-1, A-2 | H-03…H-10 | no | no |
| **Ninguna de escritura** | — | — | — | — | — |
| *(las 27 de escritura del catálogo)* | E | **ninguno** | **ninguna** | sí | 12 críticas |

> **Ningún asistente ni habilidad propuesta toca una herramienta de escritura.**

### Matriz de riesgos

| Riesgo | Evidencia | Impacto | Mitigación | ¿Bloquea? |
|---|---|---|---|:--:|
| **Duplicar el sistema de habilidades** | ya existe con 5 habilidades y 63 usos | dos verdades sobre el mismo procedimiento | reutilizar `asistente.habilidades` | **sí** |
| **Crear asistentes sin datos** | M02/M03 con 0 filas | organigrama sin trabajo | A-1/A-2 solo cuando haya datos | **sí** |
| **Duplicar los 8 roles conversacionales** | 8 roles, 84 casos dorados | competencia entre asistentes | prohibido crear NOC/Atención/Cartera | **sí** |
| `conocimiento_version` vacío | 52 propuestas sin regla citada | no se puede auditar qué regla se aplicó | poblarlo al formalizar habilidades | no |
| **Capacidad operativa sin definir** | `DisponibilidadTecnico` 0 filas | H-05 no es implementable | documentar primero | **sí, para H-05** |
| `first_response_at` contradictorio | 4 de 165 poblados | acusaciones sin sustento | dejarlo escrito en el conocimiento | no |
| Incertidumbre no declarada | 6ª pregunta sin responder | un dato inferido se lee como observado | taxonomía de FASE 10 | no |
| **M10 abierto** | 7 `campo_*` sin RLS | sin aislamiento de base sobre OT | M10 | **para autonomía** |
| **B-7 abierto** | CRM como `postgres` | GRANT/RLS inefectivos | B-7 | **para autonomía ejecutiva** |

---

# FASE 14 — Arquitectura final propuesta

**[DISEÑO]**

```
                         SUPERVISOR NOC IA
                                │
      ┌─────────────────────────┼──────────────────────────┐
      │                         │                          │
 HABILIDADES                ASISTENTE A-1            ASISTENTE A-2
 TRANSVERSALES            Programación Operativa   Seguimiento de
      │                    [NO CREAR HOY]           Compromisos
      ├── H-C1 prioridad          │                 [NO CREAR HOY]
      ├── H-C2 evidencia          ├── H-03 progr. vigente   │
      ├── H-C3 huella             ├── H-04 plan sin publicar├── H-06 vencida
      ├── H-C4 sin culpa          └── H-05 riesgo capacidad ├── H-07 sin respons.
      └── H-02 completitud            [bloqueada]           ├── H-08 bloqueada
                                                            ├── H-09 compromiso
 HABILIDAD DIRECTA DEL SUPERVISOR                           └── H-10 dependencia
      └── H-01 caso abierto antiguo   ← la única con datos reales hoy


 ─────────────────  SISTEMA CONVERSACIONAL, YA EXISTENTE  ─────────────────
 8 asistentes (roles) · 5 habilidades · corpus 21/427 · analista · 84 casos
 NO le reporta al Supervisor NOC IA. NO se toca. NO se duplica.
```

Flujo completo:

```
  CASO ──► SEÑAL ──► SUPERVISOR ──► ASISTENTE ──► HABILIDAD
                                                      │
                                                 CONOCIMIENTO
                                                      │
                                              DATOS / HERRAMIENTAS (solo lectura)
                                                      │
                                                  EVIDENCIA
                                                      │
                                                  RESULTADO
                                                      │
                                                  PROPUESTA
                                                      │
                                    SUPERVISOR integra ──► HUMANO decide
                                                              │
                                                     [la cadena termina aquí]
```

---

# FASE 15 — Decisiones necesarias

### 1. Implementable inmediatamente después

| # | Qué | Por qué es seguro |
|---|---|---|
| 1 | **Formalizar las 4 habilidades transversales** (H-C1…H-C4) como documentación de funciones que ya existen | no cambia comportamiento |
| 2 | **Poblar `conocimiento_version`** al emitir una propuesta | campo existente, hoy vacío |
| 3 | **Declarar la taxonomía de evidencia** (FASE 10) y el campo de incertidumbre | aditivo |
| 4 | **Formalizar H-01** como habilidad con ficha completa | es el único detector con datos reales |

### 2. Requiere conocimiento adicional

Los 5 documentos de la FASE 7. **H-05 está bloqueada** hasta que exista una
definición de capacidad operativa.

### 3. Requiere datos reales

**A-1, A-2 y 9 de las 10 habilidades de dominio.** **[MEDIDO]** M02 = 0 filas,
`DisponibilidadTecnico` = 0 filas.

### 4. Requiere infraestructura

Un registro de habilidades **operativas**. **[DISEÑO]** Y la decisión clave:
**reutilizar `asistente.habilidades` o crear su equivalente en el CRM.**
**[PENDIENTE]** — las habilidades conversacionales viven en el motor y las
operativas en Django, que no comparten base lógica.

### 5. Requiere resolver M10

Cualquier autonomía sobre órdenes de trabajo. **No bloquea el diseño ni Shadow
Mode.**

### 6. Requiere resolver B-7

**Solo la autonomía ejecutiva.** **No bloquea nada de este documento**, tal como
el encargo indica.

### 7. Lo que NO debemos implementar todavía

| # | Qué | Por qué |
|---|---|---|
| 1 | **Un segundo sistema de habilidades** | ya existe uno con 63 usos |
| 2 | **Asistentes de NOC, Atención, Cartera, Calidad, Reportes, Fidelización** | los 4 primeros ya existen; los 2 últimos no tienen señal medible |
| 3 | **A-1 y A-2** | sin datos que los justifiquen |
| 4 | **H-05** | sin definición de capacidad |
| 5 | **Aprendizaje automático** | conservar datos, no cerrar el lazo |
| 6 | **Cualquier nivel ≥ 2** | no hay dónde concederlo |
| 7 | **Herramientas de escritura para asistentes** | ninguna la necesita |

---

# RESUMEN EJECUTIVO

**[MEDIDO]** El sistema de asistentes + habilidades + conocimiento + aprendizaje
que este paso pedía diseñar **ya existe y opera** — en el dominio conversacional:
8 asistentes, 5 habilidades con flujo de aprobación, 63 usos, corpus de 21
documentos y 427 fragmentos, un supervisor de calidad con 16 revisiones, un
analista que detecta procedimientos faltantes a partir de la operación real, y 84
casos dorados.

**[MEDIDO]** El Supervisor NOC IA **no tiene asistentes** y sus 10 detectores no
están formalizados como habilidades.

**[DISEÑO]** La respuesta honesta a *"¿cuántos asistentes necesitamos?"* es
**ninguno hoy**. Nueve de los diez detectores operan sobre dominios con **cero
filas**. Una capa de asistentes sobre el único dominio con datos —que tiene una
sola habilidad— sería coordinación de nada.

Lo que sí corresponde ahora: **formalizar las habilidades que ya funcionan**,
con el mismo contrato que las conversacionales, y dejar A-1 y A-2 diseñados para
cuando M02/M03 tengan datos.

# DECISIONES PROPUESTAS

1. **Reutilizar** el sistema de habilidades existente; **no crear un segundo**.
2. **No crear ningún asistente** en esta etapa.
3. **Formalizar los 10 detectores** como habilidades, nivel 0/1.
4. **Cuatro habilidades transversales**, nunca duplicadas.
5. **Ninguna habilidad con herramienta de escritura.**
6. **Un asistente no invoca a otro** — el grafo es un árbol de profundidad 1.
7. **Los conflictos los resuelve el humano**, no una regla de precedencia.

# DECISIONES QUE REQUIEREN AUTORIZACIÓN

| # | Decisión |
|---|---|
| **D-1** | ¿Las habilidades operativas reutilizan `asistente.habilidades` (motor) o necesitan su equivalente en el CRM? |
| **D-2** | ¿Quién aprueba una habilidad operativa? En el motor hoy es `aprobada_por` |
| **D-3** | Escribir los 5 documentos de conocimiento de la FASE 7 |
| **D-4** | **Definición de capacidad operativa** — bloquea H-05 |
| **D-5** | ¿Se agrega un campo de incertidumbre a la evidencia? |
| **D-6** | Confirmar que A-1 y A-2 esperan a que M02/M03 tengan datos |

# SIGUIENTE PASO RECOMENDADO

**[DISEÑO]** **M09-K — Formalización de las habilidades operativas existentes.**

Alcance acotado: tomar los 10 detectores y las 4 funciones transversales y
escribir su ficha completa (`cuando_usarla`, `pasos`, `conocimiento`,
`evidencia`, `métrica`), **sin crear asistentes, sin tablas nuevas, sin cambiar
comportamiento**. Y poblar `conocimiento_version`, que existe y está vacío.

Requiere **D-1** resuelto antes de empezar.

**No lo ejecuto. Espero autorización.**

---

### Anexo — qué se midió

| Medición | Resultado |
|---|---|
| `asistente.habilidades` | **5** (1 vigente, 2 propuesta, 2 obsoleta) |
| `asistente.habilidad_usos` | **63**, todos de `HAB-CAMBIO-NOMBRE-CLAVE-WIFI` |
| Roles de IA en `tenant_config` | **8**, v146 |
| Herramientas por rol | soporte 28 · soporte_tecnico_cliente 21 · ventas 15 · facturacion 11 · administracion 9 · facturacion_cliente 7 · configuracion_guiada 2 · cliente_final 1 |
| Corpus | `documents` **21** · `document_chunks` **427** |
| Conversaciones / mensajes / tool_calls | **302** / **2.594** / **1.190** |
| `revisiones_supervisor` | **16** (buen/mal ejemplo + justificación) |
| `unanswered_queries` | **2.519** |
| Casos dorados | **84** (9 de humo) |
| Detectores M09 | **10** |
| `evaluation_sets` / `evaluation_runs` / `ejemplos_validados` | **0 / 0 / 0** |
| `herramientas_propuestas` / `verificaciones_accion` | **2** / **3** |
| Tablas en `asistente` | **37** |

Producción al cerrar el paso, sin cambios:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · operaciones_externas 0 · 192 django_migrations
tenant_config v146 · 25 roles de base · habilidades 5 · usos 63
```
