# D-3 — Conocimiento operativo del Supervisor NOC IA

**Índice maestro.** Los documentos viven en [`directivas/`](directivas/), la
carpeta documental que ya existía. No se creó ninguna estructura nueva.

---

## 1. Los cinco documentos

| ID | Documento | Versión | Estado | Habilidades | Fuente principal |
|---|---|:--:|---|---|---|
| **K-01** | [Criterio de antigüedad de un caso](directivas/K-01_criterio_antiguedad_caso.md) | v1 | **PARCIAL** | H-01 | `supervisor.py:95`, `cases/workflow.py` |
| **K-02** | [Definición de capacidad operativa](directivas/K-02_definicion_capacidad_operativa.md) | — | **NO ESCRITO** | H-05 | — |
| **K-03** | [Estados operativos que implican trabajo iniciado](directivas/K-03_estados_operativos_trabajo_iniciado.md) | v1 | **VIGENTE** | H-02, H-03 | `campo/models.py`, `transiciones.py` |
| **K-04** | [Guía de redacción sin atribución de culpa](directivas/K-04_redaccion_sin_atribucion_de_culpa.md) | v1 | **VIGENTE** | las 14 (vía H-C4) | `NovedadOperativa.TIPOS`, M09-C |
| **K-05** | [`first_response_at`: qué es y por qué no se usa](directivas/K-05_first_response_at.md) | v1 | **VIGENTE** | H-01, todas | `supervisor.py`, PRD.md:592 |

**Son exactamente los cinco identificados en M09-J FASE 7.** No se reemplazó
ninguno.

---

## 2. Matriz maestra — conocimiento

| ID | Documento | Versión | Estado | Habilidades | Fuente principal | Gap |
|---|---|:--:|---|---|---|---|
| K-01 | Criterio de antigüedad | v1 | PARCIAL | H-01 | constante de código + tabla SLA del CRM | **el umbral no es una política aprobada; y contradice el SLA del CRM** |
| K-02 | Capacidad operativa | — | **NO ESCRITO** | H-05 | — | **6 datos faltantes: no se puede escribir. D-4** |
| K-03 | Estados operativos | v1 | VIGENTE | H-02, H-03 | modelo + máquina de estados | ninguna OT real en `asignada`: validado por el lado negativo |
| K-04 | Redacción sin culpa | v1 | VIGENTE | las 14 | catálogo cerrado de causas | el filtro no cubre la paráfrasis |
| K-05 | `first_response_at` | v1 | VIGENTE | H-01, todas | prohibición ya en código | ninguna: el documento **prohíbe**, no habilita |

## 3. Matriz maestra — habilidades

| Habilidad | Conocimiento | Versión habilidad | Versión conocimiento | Estado |
|---|---|:--:|:--:|---|
| H-01 caso abierto antiguo | **K-01, K-05** | @1 | @1, @1 | con conocimiento |
| H-02 completitud de datos | **K-03** | @1 | @1 | con conocimiento |
| H-03 programación vigente | **K-03** | @1 | @1 | con conocimiento |
| H-04 plan sin publicar | — | @1 | — | **[PENDIENTE]** |
| H-05 riesgo por capacidad | — (K-02 no escrito) | @1 | — | **BLOQUEADA — D-4** |
| H-06 actividad vencida | — | @1 | — | **[PENDIENTE]** |
| H-07 sin responsable | — | @1 | — | **[PENDIENTE]** |
| H-08 bloqueada | — | @1 | — | **[PENDIENTE]** |
| H-09 compromiso por vencer | — | @1 | — | **[PENDIENTE]** |
| H-10 dependencia pendiente | — | @1 | — | **[PENDIENTE]** |
| H-C1 prioridad | — | @1 | — | **[PENDIENTE]** |
| H-C2 evidencia trazable | — | @1 | — | **[PENDIENTE]** |
| H-C3 huella | — | @1 | — | **[PENDIENTE]** |
| H-C4 redacción sin culpa | **K-04** | @1 | @1 | con conocimiento |

**4 de 14 con conocimiento. 10 sin él, declarado como tal — no inventado.**

---

## 4. Trazabilidad: cómo se representa

**[MEDIDO]** El formato de `PropuestaSupervisor.conocimiento_version` se extendió
**sin migración**: el campo ya era `CharField(128)`.

```
habilidad:H-01@1 conocimiento:K-01@1,K-05@1
└ versión de la habilidad  └ documentos que gobiernan su DETECCIÓN
```

Donde no hay documento, **la palabra `conocimiento` no aparece**:

```
habilidad:H-06@1          ← H-06 no tiene documento. El silencio es el dato.
```

**Estabilidad hacia atrás:** una propuesta emitida antes de D-3 guarda
`habilidad:H-01@1`; una de después guarda la forma extendida. **La primera mitad
no cambió**, así que las dos siguen significando lo mismo sobre la habilidad.

### Por qué K-04 no aparece en ninguna propuesta

K-04 gobierna el **texto** de las 14, pero se referencia desde **H-C4**, que no
emite señales. Es deliberado: repetirlo en las diez señales sería relleno, y la
referencia responde *"qué conocimiento gobernó la detección"*, no la redacción.

### Por qué el mapa está fuera de la ficha

**[MEDIDO]** Agregar la referencia dentro de `Habilidad` habría cambiado el
contenido literal de las 14 fichas y por lo tanto **sus huellas**, que M09-K ya
registró. El §17 del encargo es explícito: si el conocimiento obliga a tocar una
habilidad, se registra el gap y no se toca.

El mapa `CONOCIMIENTO` es aditivo. Hay una prueba que verifica que **las cuatro
huellas de M09-K siguen siendo idénticas**.

---

## 5. Los hallazgos que más importan

### 5.1 — El umbral de 7 días no es una política, y contradice al CRM

**[MEDIDO]** `DIAS_CASO_ANTIGUO = 7` aparece **una sola vez** en todo el
repositorio, como constante, sin justificación. Se buscó en `PRD.md`, `SPEC/`,
`ARQUITECTURA.md`, `CLAUDE.md`, `directivas/`, la configuración del tenant y el
código.

**[MEDIDO]** Y el propio CRM carga otro número:

| Criterio | Valor | Origen |
|---|---|---|
| Detector de M09 | **168 h** (7 días) | constante de código |
| SLA de resolución del CRM | **48 h** (2 días) | `DEFAULT_RESOLUTION_SLA['Normal']`, en los 197 casos |

**Difieren por 3,5×.** Nadie decidió cuál gobierna. **K-01 no lo decide**: lo
deja como contradicción abierta, porque es una decisión de negocio.

### 5.2 — `first_response_at` sigue sin poder usarse, y el dato empeoró

**[MEDIDO]** El código decía *4 de 165* (15/09/2026). Hoy: **4 de 197**.
**El numerador no se movió**: entraron 32 casos nuevos y ninguno registró primera
respuesta. La prohibición se refuerza.

### 5.3 — K-02 no se pudo escribir, y no se rellenó

**[MEDIDO]** `operaciones_disponibilidad` = **0 filas**; 3 órdenes de trabajo, 0
con `programada_para`. Faltan seis definiciones de negocio, ninguna resoluble
midiendo. **No se propuso ningún umbral.**

---

## 6. Dependencias

| Dependencia | ¿Bloquea D-3? | ¿Qué bloquea? |
|---|:--:|---|
| **D-4** (capacidad operativa) | no | **K-02 y H-05** |
| **B-7** (runtime fuera de `postgres`) | **no** | solo autonomía ejecutiva. **No tocado** |
| **M10** (RLS `campo_*`) | no | autonomía sobre órdenes |
| Decisión sobre K-01 R-3 | no | que K-01 pase de PARCIAL a VIGENTE |

---

## 7. Vacíos

| # | Vacío | Dónde |
|---|---|---|
| V-1 | **10 de 14 habilidades sin documento** | matriz §3 |
| V-2 | **K-02 sin escribir** | D-4 |
| V-3 | **El umbral de 7 días no está aprobado** | K-01 R-1 |
| V-4 | **Contradicción 7 días vs 48 h sin resolver** | K-01 R-3 |
| V-5 | No hay excepciones documentadas para casos en espera del cliente | K-01 |
| V-6 | Sin decisión sobre si `correccion_requerida` vuelve al circuito de programación | K-03 L-5 |
| V-7 | El texto que escribe un humano al modificar una propuesta **no pasa** por K-04 | K-04 L-5 |

---

## 8. Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-1 | Que alguien lea el umbral de 7 días como política | K-01 lo declara **[PENDIENTE — REGLA NO DEFINIDA]** en la primera línea de R-1 |
| R-2 | Que un patrón observado se convierta en regla | K-01 R-4 lo prohíbe explícitamente; K-02 lo rechaza por escrito |
| R-3 | Que el filtro de 12 patrones se tome por garantía | K-04 R-6 lo dice: *"se puede atribuir culpa sin usar ninguna de esas palabras"* |
| R-4 | Que un documento y el código diverjan | 60 pruebas verifican IDs, versiones, secciones y que nada apunte al vacío |
| R-5 | Que mover la referencia dentro de la ficha invalide las huellas de M09-K | prueba explícita sobre 4 huellas |
| R-6 | Que K-02 se dé por escrito porque el archivo existe | el archivo declara **NO SE PUDO ESCRIBIR** en un encabezado, y hay prueba |

---

## 9. Pendientes

| # | Qué | Dónde |
|---|---|---|
| **P-1** | Decidir el criterio de antigüedad (K-01 R-1/R-3) | **decisión humana** |
| **P-2** | Definir capacidad operativa → K-02, H-05 | **D-4** |
| **P-3** | Conocimiento para las 10 habilidades sin documento | etapa posterior |
| **P-4** | **[GAP DE HABILIDAD]** H-C4 dice *"13 patrones"*; son **12** | ver §10 |
| **P-5** | Motor: los 63 usos con `conversation_id` NULL | fuera de alcance, sin tocar |
| **P-6** | B-7 | **no tocado** |

---

## 10. GAP DE HABILIDAD registrado

**[GAP DE HABILIDAD]** Al escribir K-04 se contó la lista real de patrones de
atribución de culpa: **son 12**.

La ficha H-C4 de `operaciones/habilidades.py` dice *"13 patrones"*, y los
informes M09-E, M09-J y M09-K repiten esa cifra. **Es un error de conteo mío,
arrastrado desde M09-E.**

**Por §17 del encargo, la ficha NO se modificó.** La corrección queda aquí y en
K-04 R-5, que es la fuente correcta de la lista. Corregir la ficha cambiaría su
huella —registrada en M09-K— y eso exige una decisión sobre versionado que este
paso no tiene mandato para tomar.

**Impacto:** ninguno operativo. El filtro de validación usa la tupla real, no la
cifra; el número solo aparece en texto descriptivo.
