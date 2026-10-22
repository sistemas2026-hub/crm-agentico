# ESTADO: IMPLEMENTADO

**D-3 — Documentos de conocimiento operativo · Informe de implementación**
Fecha: 2026-09-17

---

## Resultado

```
Documentos creados:            5 / 5
Documentos completos:          3 / 5     (K-03, K-04, K-05)
Documentos parciales:          1 / 5     (K-01 — la regla no está definida)
Documentos pendientes:         1 / 5     (K-02 — información insuficiente)

Habilidades con conocimiento:  4 / 14

Versionamiento:                OK
Trazabilidad:                  OK
Incertidumbre:                 OK

Pruebas:                       384 PASSED / 0 FAILED
Producción:                    SIN CAMBIOS
Efectos externos:              0
Autonomía:                     SIN CAMBIOS

H-05:                          BLOQUEADA — D-4
B-7:                           PENDIENTE — NO TOCADO
```

---

## Los cinco documentos

**Verificados contra M09-J FASE 7**, en su orden original. Ninguno fue
reemplazado.

| # de M09-J | ID | Documento | Estado |
|:--:|---|---|---|
| 1 | K-01 | Criterio de antigüedad de un caso | **PARCIAL** |
| 2 | K-02 | Definición de capacidad operativa | **NO ESCRITO** |
| 3 | K-03 | Estados operativos que implican trabajo iniciado | **VIGENTE** |
| 4 | K-04 | Guía de redacción sin atribución de culpa | **VIGENTE** |
| 5 | K-05 | Nota sobre `first_response_at` | **VIGENTE** |

Ubicación: [`directivas/`](directivas/) — la carpeta documental que ya existía.
**No se creó ninguna estructura nueva.**

### Por qué K-01 es PARCIAL

**[MEDIDO]** El umbral de 7 días **no tiene justificación en ninguna parte**:
aparece una sola vez, como constante en `supervisor.py:95`. Se buscó en `PRD.md`,
`SPEC/`, `ARQUITECTURA.md`, `CLAUDE.md`, `directivas/`, la configuración del
tenant y el código.

**[MEDIDO]** Y el propio CRM carga otro número: `DEFAULT_RESOLUTION_SLA['Normal']
= 48 h`, aplicado a **los 197 casos**. Los dos criterios **difieren por 3,5×**.

El documento **no eligió** cuál gobierna. Registra la contradicción y la escala a
decisión humana. Convertir el 7 en política habría sido inventarla.

### Por qué K-02 no se escribió

**[MEDIDO]** `operaciones_disponibilidad` = **0 filas**. 3 órdenes de trabajo, 0
con `programada_para`. Faltan seis definiciones de negocio —qué es una unidad de
capacidad, cuánto rinde, qué cuenta como ausencia, qué margen es riesgo— y
**ninguna se resuelve midiendo**.

El archivo existe y declara, en un encabezado:

```
# ESTE DOCUMENTO NO SE PUDO ESCRIBIR
Y no debe rellenarse con conocimiento genérico.
```

**No se propuso ningún umbral.** Con 3 órdenes no habría ni patrón que observar.

---

## Archivos creados

| Archivo | Qué es |
|---|---|
| `directivas/K-01_criterio_antiguedad_caso.md` | documento de conocimiento |
| `directivas/K-02_definicion_capacidad_operativa.md` | constancia de que no se pudo escribir |
| `directivas/K-03_estados_operativos_trabajo_iniciado.md` | documento de conocimiento |
| `directivas/K-04_redaccion_sin_atribucion_de_culpa.md` | documento de conocimiento |
| `directivas/K-05_first_response_at.md` | documento de conocimiento (prohibición) |
| `D-3_CONOCIMIENTO_OPERATIVO.md` | índice maestro |
| `D-3_IMPLEMENTACION.md` | este informe |
| `operaciones/tests/test_d3_conocimiento.py` | 60 pruebas de consistencia |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `operaciones/habilidades.py` | **mapa `CONOCIMIENTO` nuevo** + `conocimiento_de()` + `referencia_de()` extendida |
| `operaciones/tests/test_m09k_habilidades.py` | 2 pruebas actualizadas al formato extendido |

**Ninguna ficha de habilidad fue modificada.** El mapa vive **fuera** del
dataclass, y hay una prueba que verifica que **las huellas de M09-K siguen
idénticas**.

## Archivos NO modificados — verificado por marca de tiempo

| Archivo / área | Estado |
|---|---|
| `operaciones/supervisor.py` | **sin cambios en D-3** (mtime 21:14 = M09-K; D-3 empezó 21:29) |
| Los 10 detectores | sin cambios |
| `operaciones/models.py` · `PropuestaSupervisor` | **sin cambios, ningún campo nuevo** |
| Las 14 fichas de habilidad | **sin cambios**, huellas intactas |
| `nucleo/` **completo** | **sin cambios** — `find nucleo/ -newermt` → vacío |
| `asistente.habilidades` (tabla) | **sin tocar**: 5 filas |
| `asistente.habilidad_usos` | **sin tocar**: 63 filas |
| Migraciones | **ninguna creada** |

---

## Trazabilidad: la extensión, sin migración

**[MEDIDO]** El campo ya era `CharField(128)`. **No hizo falta migración.**

```
antes de D-3   habilidad:H-01@1
después        habilidad:H-01@1 conocimiento:K-01@1,K-05@1

sin documento  habilidad:H-06@1        ← la palabra 'conocimiento' no aparece
```

**Estabilidad hacia atrás:** la primera mitad no cambió. Una propuesta vieja y
una nueva siguen diciendo lo mismo sobre la habilidad.

**4 de 14 habilidades** tienen conocimiento. Las otras 10 devuelven la referencia
sin la segunda mitad: **el silencio es el dato**, no un error.

---

## Pruebas

| Momento | Suite | Resultado |
|---|---|---|
| Antes de D-3 (cierre de M09-K) | `operaciones/tests/` | **324 passed** |
| Nuevas, aisladas | `test_d3_conocimiento.py` | **60 passed** |
| **Después** | `operaciones/tests/` | **384 passed** |

```
384 = 324 + 60      regresiones: 0
```

Las 14 comprobaciones del §20 quedan cubiertas: los cinco documentos existen,
tienen ID, versión, estado y fuentes; las habilidades citadas existen; el mapa
no apunta al vacío; las versiones coinciden con los documentos; las fichas siguen
intactas; H-05 sigue bloqueada; cero acciones externas.

### Un fallo durante el desarrollo, y su causa real

La primera corrida dio **37 failed**. Causa: `Path(__file__).parents[4]` resolvía
a `/` dentro del contenedor, porque `django-crm` se monta directo en `/proyecto`
y la raíz del repositorio queda fuera del árbol.

Se corrigió **la prueba**, buscando `directivas/` hacia arriba en vez de contar
niveles fijos, y se agregó un `skipif` para que las pruebas que leen archivos se
**salten** si el repositorio no está montado, en vez de fallar. *Una prueba que
falla por cómo se montó un volumen entrena a ignorar fallos reales.*

---

## Producción

# NO — Producción no modificada

```
ledger                   50      (sin cambios)
kill switch              detenido (sin cambios)
filas ACTIVO             0
PropuestaSupervisor      0
django_migrations        192     (sin cambios)
tenant_config            v146    (sin cambios)
asistente.habilidades    5       (intactas)
asistente.habilidad_usos 63      (intactos)
```

Las únicas operaciones contra producción fueron **lecturas** (`read_only=True`)
para medir: distribución de antigüedad de casos, valores de SLA, prioridades,
cobertura de `first_response_at`.

## Efectos externos

# 0

No se llamó a WispHub, SmartOLT, WhatsApp ni al CRM externo.

## Autonomía

# SIN CAMBIOS

Kill switch **DETENIDO**. Ninguna habilidad cambió de nivel. Ninguna ganó
herramienta de escritura. `ejecutar_propuesta` sigue levantando.

---

## Criterios de éxito (§27)

| | Criterio | |
|:--:|---|:--:|
| ☑ | Los cinco documentos fueron identificados correctamente | verificados contra M09-J FASE 7 |
| ☑ | Creados, o marcados como imposibles de completar | 4 escritos + K-02 con constancia |
| ☑ | Cada regla tiene fuente | tabla de Fuentes en cada documento |
| ☑ | No se inventaron políticas | K-01 R-1 y R-3 declaradas pendientes |
| ☑ | No se inventaron umbrales | K-02 no propone ninguno |
| ☑ | Existe incertidumbre explícita | sección en los 4 escritos |
| ☑ | Existe evidencia requerida | sección en los 4 escritos |
| ☑ | Existe versionamiento | v1, con regla de cambio |
| ☑ | Existe trazabilidad | `conocimiento_version` extendido |
| ☑ | Las 14 habilidades siguen intactas | huellas verificadas por prueba |
| ☑ | No se modificó `asistente.habilidades` | 5 filas, sin tocar |
| ☑ | No se modificó el Motor | `nucleo/` sin cambios |
| ☑ | No se modificaron detectores | `supervisor.py` sin cambios en D-3 |
| ☑ | No se modificó autonomía | kill switch DETENIDO |
| ☑ | H-05 sigue bloqueada | `estado=bloqueada`, sin conocimiento asociado |
| ☑ | B-7 no fue tocado | — |
| ☑ | Producción no fue modificada | verificado |
| ☑ | No hubo efectos externos | 0 |
| ☑ | Las pruebas existentes continúan pasando | 384, 0 regresiones |

**19 de 19.**

---

## Regla de detención (§29)

No hizo falta detenerse. **Un punto estuvo cerca**, y se resolvió respetando §17:

> **[GAP DE HABILIDAD] registrado, no corregido.**
>
> Al escribir K-04 conté la lista real de patrones de atribución de culpa: **son
> 12**. La ficha H-C4 dice *"13 patrones"*, y los informes M09-E, M09-J y M09-K
> repiten esa cifra. **Es un error de conteo mío, arrastrado desde M09-E.**
>
> Corregir la ficha habría cambiado su huella —registrada en M09-K— así que
> **no se tocó**. La corrección queda en K-04 R-5, que es ahora la fuente
> correcta de la lista, y en el índice §10.
>
> **Impacto operativo: ninguno.** El filtro de validación usa la tupla real, no
> la cifra; el número solo aparecía en texto descriptivo.

Y la decisión de diseño que evitó tocar las fichas: el mapa `CONOCIMIENTO` se
puso **fuera** del dataclass `Habilidad`. Ponerlo dentro habría cambiado el
contenido literal de las 14 y por lo tanto sus huellas.

---

## Control de cambios (§26)

```
archivos tocados por D-3 (marca de tiempo 21:29 en adelante):
  directivas/K-01_criterio_antiguedad_caso.md              [nuevo]
  directivas/K-02_definicion_capacidad_operativa.md        [nuevo]
  directivas/K-03_estados_operativos_trabajo_iniciado.md   [nuevo]
  directivas/K-04_redaccion_sin_atribucion_de_culpa.md     [nuevo]
  directivas/K-05_first_response_at.md                     [nuevo]
  D-3_CONOCIMIENTO_OPERATIVO.md                            [nuevo]
  D-3_IMPLEMENTACION.md                                    [nuevo]
  operaciones/habilidades.py                               [mapa + 2 funciones]
  operaciones/tests/test_d3_conocimiento.py                [nuevo]
  operaciones/tests/test_m09k_habilidades.py               [2 pruebas]

supervisor.py   -> mtime 21:14 (M09-K), NO tocado por D-3
nucleo/         -> sin cambios
migraciones/    -> ninguna
```

`git diff --stat` sigue mostrando 31 archivos de pasos anteriores de esta sesión:
`django-crm/backend/operaciones/` entero está sin versionar (`??`).

**No se hizo commit.** No estaba autorizado.
