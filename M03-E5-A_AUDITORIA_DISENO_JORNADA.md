# M03-E5-A — Auditoría y diseño de secuenciación de jornada

**Fecha:** 2026-09-18
**Alcance:** auditoría y diseño. **0 código, 0 migraciones, 0 modelos, 0 endpoints, producción solo `SELECT`.**

---

## RESUMEN EJECUTIVO

La operación de conjunto es viable **sin una sola migración**, pero la auditoría
encontró **dos obstáculos estructurales** que condicionan el diseño y que no se
podían anticipar sin mirar el esquema.

### Obstáculo 1 — el evento de conjunto no se puede escribir

**[MEDIDO]** `campo_evento_trabajo.orden_id` es **`NOT NULL`**.

> **Un evento de "jornada" no tiene orden de la cual colgar.** La alternativa B
> del §11 —un evento de conjunto más uno por línea— **exige una migración** para
> hacer `orden` nullable, y eso está fuera de la autorización.
>
> La salida sin migración es la alternativa **C**: un evento por línea, **todos
> con un identificador de lote compartido** en `datos`. El conjunto se
> reconstruye agrupando.

### Obstáculo 2 — bloquear el plan primero produciría un interbloqueo con E4

**[MEDIDO]** El orden de locks de las cinco operaciones del módulo:

| Operación | Bloquea |
|---|---|
| `programar_orden` | `OrdenTrabajo` |
| `publicar_programacion` | `ProgramacionSemanal` |
| `reprogramar_orden` | `OrdenTrabajo` **→** `ProgramacionSemanal` |
| `registrar_contingencia` | `OrdenTrabajo` |
| **`actualizar_secuencia` (E4)** | **`ProgramacionOrden` → `ProgramacionSemanal`** |

> **El plan es SIEMPRE el último lock.** Es una invariante del módulo, medida
> sobre cinco operaciones.
>
> **[RIESGO]** Si E5 bloqueara el plan primero: E4 sostiene la línea y pide el
> plan; E5 sostiene el plan y pide la línea. **Ciclo.** E5 tiene que bloquear
> **líneas → plan**, y las líneas **en orden determinista** para no chocar
> consigo misma.

---

## 1. Unidad de operación

### Lo medido

**[MEDIDO]** FK de `ProgramacionOrden`: `org`, `programacion` (→
`ProgramacionSemanal`), `orden` (→ `campo.OrdenTrabajo`). Campo `dia` (`date`,
`NOT NULL`).

**[MEDIDO]** Constraints e índices relevantes:

```
UNIQUE  unique_orden_por_programacion   (programacion_id, orden_id)
UNIQUE  unique_programacion_semana_por_org  (org_id, semana_inicio)   [en el plan]
INDEX   (org_id, dia)
```

**[MEDIDO]** Cómo se obtiene hoy una jornada — ya existe la superficie:

```python
def lineas_de_jornada(org, *, programacion=None, dia=None)   # M03-E2
```

y el endpoint `GET /api/operaciones/programacion/jornada/?dia=…|?plan=…`, que
**exige uno de los dos filtros**.

### El día mapea a un solo plan, pero por servicio, no por esquema

**[MEDIDO]** Tres hechos encadenados:

1. `unique(org, semana_inicio)` → **un plan por semana y organización**;
2. un `dia` pertenece a **una sola semana**;
3. `programar_orden` y `reprogramar_orden` **exigen** que `linea.dia` caiga
   dentro de `[semana_inicio, +6]`.

> Luego, para un `(org, dia)` dado, **todas las líneas pertenecen al mismo plan**.

**[RIESGO]** Pero el punto 3 **es una regla de servicio, no una constraint**. El
panel de Django puede crear una línea fuera de la semana de su plan. Es
exactamente lo que `revisar_coherencia` detecta al publicar (*"está fechada el X,
fuera de la semana del Y al Z"*), así que el sistema ya lo considera una anomalía
— pero **puede existir entre publicaciones**.

### A · Unidad recomendada

**[DISEÑO]** **La jornada = `(org, dia)`.** No el plan entero, no un conjunto
suelto de líneas.

| Candidata | Por qué no / sí |
|---|---|
| `ProgramacionSemanal` | **demasiado grande**: una semana son cinco o seis jornadas. Secuenciar el lunes no debería bloquear el jueves |
| **`(org, dia)`** | **elegida**: es lo que "jornada" significa, `lineas_de_jornada` ya lo acepta, el endpoint de E2 ya lo trata como filtro de primera clase, y existe el índice `(org_id, dia)` |
| conjunto suelto de `ProgramacionOrden` | **demasiado laxo**: permitiría mezclar días y planes sin que nada lo notase |
| otra | — |

**[DISEÑO]** La entrada debería llevar **`dia` obligatorio y `plan` obligatorio**,
aunque el plan sea deducible. Dos razones:

1. el plan es la **autoridad sobre "publicado o borrador"**, que decide si hace
   falta motivo (§9);
2. pedirlo explícito convierte el `[RIESGO]` de arriba en una **comprobación**:
   si alguna línea del día pertenece a otro plan, la operación **se rechaza en
   vez de abarcar dos planes en silencio**.

---

## 2. Modelo de entrada

### B · Contrato conceptual

```jsonc
POST /api/operaciones/programacion/jornada/secuenciar/
{
  "plan": "<uuid>",
  "dia": "2026-10-07",
  "lineas": [
    {"linea": "<uuid A>", "secuencia": 1},
    {"linea": "<uuid B>", "secuencia": 2},
    {"linea": "<uuid C>", "secuencia": 0}
  ],
  "causa": "cambio_de_prioridad",      // solo si el plan está publicado
  "motivo": "el cliente de la 2 pidió temprano"
}
```

**[MEDIDO]** No hay precedente de escritura por lista en el proyecto: el único
`ListField` es `ValidarSerializer.requisitos_a_corregir`, y es una lista de
cadenas. **E5 sería el primer cuerpo de lista de objetos.**

### ¿Todas las líneas, o solo las modificadas?

**[DISEÑO]** Las dos opciones, con lo que cada una cuesta:

| | Opción | A favor | En contra |
|---|---|---|---|
| **1** | **enviar TODAS** las líneas vigentes de la jornada | el servidor puede comprobar que el cliente **vio la misma jornada**: si el conjunto no coincide exactamente, algo cambió mientras el usuario ordenaba | cuerpo más grande |
| **2** | enviar **solo las modificadas** | cuerpo mínimo | **no se puede distinguir** "la dejé igual" de "no la vi": una línea añadida por otra persona pasaría inadvertida |

**[DISEÑO] Recomendación: opción 1**, y la razón es concreta.

**[MEDIDO]** `ProgramacionOrden` **no tiene campo de concurrencia optimista** —ni
`revision` ni versión—, a diferencia de `OrdenTrabajo`, que sí lo tiene. Con la
opción 1, **el conjunto de ids hace de token de versión** sin agregar ningún
campo: si el servidor recibe exactamente las líneas que hay, el cliente vio el
estado actual.

**[PENDIENTE]** Es una decisión de contrato, no técnica: si el negocio prefiere
ediciones parciales, la opción 2 es válida y pierde esa comprobación.

### Las cuatro validaciones del §2

| Caso | Tratamiento propuesto |
|---|---|
| **línea omitida** | con la opción 1 → **error explícito** que nombra las que faltan. Nunca "se deja como está" en silencio |
| **línea extra / de otra jornada** | error: se comprueba `linea.dia == dia` **y** `linea.programacion_id == plan` |
| **línea de otra organización** | **no llega a existir**: la consulta filtra por `org=request.org`; se reporta como inexistente, no como ajena |
| **línea inexistente** | error que la nombra. **404 si ninguna existe; 400 si el conjunto es incoherente** — se distinguen porque son problemas distintos |

**[DISEÑO]** Todas las validaciones **antes** de escribir nada, y el error
devuelve **todas** las líneas problemáticas, no la primera — mismo criterio que
`revisar_coherencia` de M03-C.

---

## 3. Atomicidad y 4. Concurrencia

### C · Estrategia de locks

**[DISEÑO]**

```
1. las LÍNEAS de la jornada, con select_for_update(), ORDENADAS POR id
2. el PLAN, con select_for_update()
```

| Registro | ¿Se bloquea? | Por qué |
|---|:--:|---|
| **`ProgramacionOrden`** | **SÍ**, todas las de la jornada | son las filas que se escriben |
| **`ProgramacionSemanal`** | **SÍ**, el último | su `estado` decide si hace falta motivo; sin lock, un `publicar` concurrente lo cambiaría a media operación |
| `OrdenTrabajo` | **NO** | la operación no toca ninguna orden. E4 tampoco la bloquea |
| `NovedadOperativa` | **NO** | solo `INSERT` |
| `EventoTrabajo` | **NO** | solo `INSERT`, y es append-only |

**[RIESGO] Por qué el orden importa, y por qué "ordenadas por id":**

- **plan primero** cerraría un ciclo con E4 (línea → plan). Medido en el §RESUMEN.
- **líneas sin orden fijo** cerraría un ciclo entre dos E5 concurrentes: A
  bloquea L1 y pide L2, B bloquea L2 y pide L1. Ordenar por `id` lo elimina.

**[DISEÑO]** ¿Basta bloquear el plan? **No.** El plan protege del `publicar`
concurrente, pero **no impide que E4 cambie una línea** — E4 no lo bloquea hasta
el final. Hay que bloquear las líneas.

### La prueba de concurrencia del §4

**[DISEÑO]** Diseño conceptual, sin implementar:

```
Proceso A                          Proceso B
─────────                          ─────────
GET jornada (3 líneas)
                                   POST E4: línea B de 2 → 7   (commit)
POST E5 secuenciar
  lineas=[A:1, B:2, C:3]
```

| Conducta esperada | Por qué |
|---|---|
| **con la opción 1** (todas las líneas) | A envía exactamente las tres que existen → el conjunto **coincide** → la operación **se aplica** y deja a B en 2. **El cambio de B se pierde**, pero queda en la bitácora: su evento dice `7 → 2`, y el de E4 decía `2 → 7`. **La historia es reconstruible** |
| **si además llega una línea nueva** | el conjunto **no coincide** → **409**, y A tiene que recargar |

> **[PENDIENTE]** Que "el último gana" sea aceptable es una **decisión
> empresarial**. La alternativa —detectar que alguien tocó una línea entre la
> lectura y la escritura— **exige un token de versión que no existe** en
> `ProgramacionOrden` (§2). Sin él, solo el conjunto de ids detecta cambios de
> composición, no de valor.

---

## 5. Transiciones e historial

**[DISEÑO]** Para el caso del encargo:

```
A: 1 → 3      B: 2 → 1      C: 3 → 2
```

**debe poder reconstruirse línea por línea.** Un solo evento que dijera *"se
reordenó la jornada"* sería exactamente el "evento único ambiguo" que el §5
prohíbe.

### E · Estrategia de auditoría

**[MEDIDO]** La alternativa **B** del §11 —un evento de conjunto **más** eventos
por línea— **no se puede implementar sin migración**:

```
campo_evento_trabajo.orden_id  →  NOT NULL
```

Un evento de jornada **no tiene orden de la cual colgar**. Colgarlo de una orden
arbitraria sería mentir sobre a qué pertenece.

**[DISEÑO] Alternativa C — un evento por línea, con lote compartido:**

```jsonc
// un EventoTrabajo por cada línea que cambió
{
  "tipo": "secuencia_jornada",          // o "secuencia_jornada_en_plan_publicado"
  "orden": "<la orden de ESA línea>",
  "profile": "<actor>",
  "datos": {
    "lote": "<uuid compartido por todas las líneas de la operación>",
    "linea": "<uuid>",
    "anterior": 1, "nuevo": 3,
    "anterior_sin_secuenciar": false,
    "nuevo_sin_secuenciar": false,
    "jornada": {"plan": "<uuid>", "dia": "2026-10-07",
                "plan_estado": "publicada"},
    "lote_tamano": 3,            // cuántas líneas tenía la operación
    "lote_cambiadas": 3,         // cuántas cambiaron de verdad
    "lote_sin_cambio": 0,        // cuántas se enviaron iguales
    "posicion_en_lote": 1,
    "causa": "...", "motivo": "...", "novedad": "<uuid|null>",
    "empate": {...}              // igual que E4
  }
}
```

**[DISEÑO]** Con eso se contesta **todo** lo que el §11 exige:

| Exigido | Dónde |
|---|---|
| quién ejecutó | `EventoTrabajo.profile` |
| cuándo | `created_at` |
| jornada afectada | `datos.jornada` |
| líneas afectadas | agrupar por `datos.lote` |
| secuencia anterior / nueva | `datos.anterior` / `datos.nuevo` |
| motivo cuando corresponda | `datos.causa` + `motivo` + `novedad` |
| **si hubo líneas sin cambio** | `datos.lote_sin_cambio` |
| resultado final | la suma de los eventos del lote |

**[PENDIENTE]** Una sub-decisión: **¿se escribe evento para las líneas que NO
cambiaron?** Escribirlos deja constancia de que se revisaron; no escribirlos
mantiene la bitácora con solo cambios reales —el criterio que D3.2 y E4 ya
aplicaron—. **Se recomienda no escribirlos y registrar el conteo en
`lote_sin_cambio`**, pero es una decisión.

---

## 6. Sin cambio

**[MEDIDO]** La convención del proyecto, sobre cinco operaciones:

| Operación | Cuando el estado pedido ya es el actual |
|---|---|
| `programar_orden` | **409** `YaProgramada` |
| `publicar_programacion` | **409** `NO_PUBLICABLE` (ya publicado) |
| `reprogramar_orden` | **409** `YaEnEsaFecha` |
| `actualizar_secuencia` (E4) | **409** `SECUENCIA_SIN_CAMBIO` |
| `manejar_idempotencia` (replay) | **200** con `Idempotent-Replay: true` |

> **[MEDIDO] El proyecto distingue dos cosas:** *"lo que pides ya está hecho"* →
> **409**; *"esta petición exacta ya se procesó"* → **200 con replay**. Son
> mecanismos distintos y conviven.

**[DISEÑO]** Para un conjunto, **el caso "ninguna línea cambió" no es igual** al
caso individual de E4:

- una operación de conjunto donde **9 de 10** cambian y 1 no, **debe aplicarse**:
  rechazarla por una línea sería inutilizable;
- luego la pregunta es **solo** sobre el caso "ninguna de las N cambió".

| | Lectura | A favor |
|---|---|---|
| **409** | coherente con las cuatro operaciones existentes | una jornada idéntica no es un cambio |
| **200 idempotente** | el estado final pedido **es** el estado actual; la operación de conjunto es declarativa | evita que un cliente que reenvía por timeout reciba un error |

**[PENDIENTE — y con dependencia]** No se elige. Y hay que notar que **depende de
B-1**: el caso `SECUENCIA_SIN_CAMBIO` de E4 sigue pendiente de firma, y sería
raro que E4 y E5 contestaran distinto al mismo hecho.

> **Recomendación de proceso, no de contenido: resolver B-1 primero y aplicar la
> misma respuesta a E5.**

---

## 7. Secuencia 0

**[DECISIÓN APROBADA]** `0` = **SIN SECUENCIAR**. No es posición.

**[DISEÑO]** E5 **reutiliza literalmente lo que E4 ya implementó**, sin
reinterpretarlo:

```python
"anterior_sin_secuenciar": anterior == 0,
"nuevo_sin_secuenciar":    nuevo    == 0,
```

y el empate lo calcula `_empate_de`, que **ya devuelve `hay_empate: False` para el
0** con su razón escrita.

**[DISEÑO]** Una consecuencia propia del conjunto: **una jornada puede enviarse
entera en 0** — es *dessecuenciar la jornada*, y es una operación legítima, no un
error.

---

## 8. Duplicados

**[DECISIÓN APROBADA]** Las secuencias > 0 **pueden repetirse**.

**[DISEÑO]** E5 **no** crea `UNIQUE`, **no** convierte el duplicado en error y
**no** compacta. El conjunto puede llegar con `[1, 1, 2]` y se aplica tal cual.

**[DISEÑO]** El empate se **anota** por línea, igual que en E4, y sigue siendo
observable por la lectura de M03-E2.

---

## 9. Plan borrador vs. publicado

**[MEDIDO]** La única diferencia que el código ya establece, heredada de D1.1-D y
aplicada en E4:

| | Borrador | Publicado |
|---|---|---|
| **motivo** | **no se exige** — *"un borrador no compromete a nadie"* | **obligatorio** — hay compromiso operativo |
| `EventoTrabajo.tipo` | `secuencia_jornada` | **`secuencia_jornada_en_plan_publicado`** |
| `NovedadOperativa` | solo si hay causa | **sí**, con causa del catálogo cerrado |

**[DISEÑO]** **No se inventa ninguna regla nueva.** La única pregunta propia del
conjunto:

**[PENDIENTE]** **¿Una causa por lote, o una por línea?** Una por lote es lo
natural —la jornada se reordenó por un motivo— y produce **una** `NovedadOperativa`
referenciada por todos los eventos del lote. Una por línea permitiría motivos
distintos, a costa de N novedades para una sola decisión. **Se recomienda una por
lote**, pero es una decisión.

---

## 10. Idempotencia

### F · Estrategia

**[MEDIDO]** `manejar_idempotencia` (`campo/services/idempotencia.py`):

- clave: cabecera `Idempotency-Key`, ámbito `(org, clave)`;
- compara `http_method`, `endpoint` y `request_hash`;
- `calcular_hash_canonico` hace `json.dumps(..., sort_keys=True)` **para `dict`
  y para `list`** — **un cuerpo de lista se hashea igual de bien**;
- completada → **replay** de la respuesta guardada.

**[DISEÑO]** **Se reutiliza tal cual. No se crea otro sistema.** E4 ya demostró
que el decorador funciona desde una vista de `operaciones/`.

**[RIESGO] Con una precaución medida en E4:** la respuesta se **guarda** en un
`JSONField`, así que **todo el payload debe ser JSON primitivo**. E4 destapó
exactamente ese defecto (`UUID is not JSON serializable`) y lo corrigió en
`LineaJornadaSerializer`. **E5 debe verificarlo en su propia respuesta**, que será
más grande.

**[DISEÑO]** La identificación lógica de la operación es **la cabecera que envía
el cliente**, no algo que el servidor invente — igual que en el resto del
proyecto.

---

## 11-12. Auditoría y rol

**[DISEÑO]** Auditoría: ver §5 (alternativa **C**).

**[MEDIDO]** Permisos — el patrón exacto a reutilizar, ya usado por E2 y E4:

```python
permission_classes = [EsJefeDeOperaciones]     # operaciones/permissions.py
    → ROLES_GESTION = {"ADMIN", "SUPERVISOR", "OPERACIONES"}
```

**0 roles nuevos.** Y la organización sale de `request.org`, **nunca del cuerpo**.

---

## 13. Transacción

### D · Orden exacto

**[DISEÑO]**

```
 1. LECTURA        resolver plan y día acotados a request.org
 2. VALIDACIÓN     cuerpo bien formado; secuencias >= 0; sin ids repetidos
 3. LOCK           líneas de la jornada (select_for_update, ORDENADAS POR id)
 4. LOCK           el plan (select_for_update)          <- siempre el último
 5. RELECTURA      el conjunto real de líneas vigentes, ya bloqueado
 6. VALIDACIÓN     el conjunto enviado coincide exactamente con el real;
                   todas del mismo plan y del mismo día;
                   motivo si el plan está publicado
 7. CÁLCULO        capturar los valores ANTERIORES de las filas bloqueadas;
                   determinar qué líneas cambian de verdad;
                   calcular los empates resultantes
 8. ESCRITURA      UPDATE de cada línea que cambia (solo 'secuencia' +
                   'updated_by' + 'updated_at')
 9. AUDITORÍA      NovedadOperativa si hay causa; un EventoTrabajo por línea
                   cambiada, con el 'lote' compartido
10. COMMIT
```

**[DISEÑO]** Los pasos 2 y 6 están separados a propósito: el 2 valida **la forma**
del cuerpo sin tocar la base; el 6 valida **contra la realidad bloqueada**. Mismo
patrón que M03-D3 y E4, que releen tras el lock en vez de confiar en el objeto
recibido.

**[DISEÑO]** El paso 7 es **R-8'** de M03-D2: *capturar antes de mutar*.

---

## 14. Errores parciales

**[DISEÑO]** Todo dentro de **una `transaction.atomic`**, así que los cuatro
fallos del §14 se comportan igual — **nada queda aplicado**:

| Falla en | Qué queda |
|---|---|
| **validación** (pasos 2 o 6) | nada: aún no se escribió |
| **escritura de una línea** (paso 8) | **nada**, ni las líneas ya actualizadas |
| **escritura de auditoría** (paso 9) | **nada**: ni secuencias sin evento, ni eventos sin cambio |
| **idempotencia** | el decorador envuelve la vista; si la operación falla, la mutación no queda como COMPLETADA |

**[DISEÑO]** Y es comprobable con el método que M03-B, C, D3 y E4 ya usan:
romper el **último** paso e ir a mirar con una **conexión independiente del ORM**
que no quedó nada.

---

## 15. Impacto en E4

**[DISEÑO]** **E5 NO requiere modificar E4.**

| Aspecto | ¿Cambia E4? |
|---|---|
| orden de locks | **no** — E5 se adapta a la invariante "plan al final" que E4 ya respeta |
| `_empate_de`, `_validar_causa`, `_novedad_de` | **no** — se reutilizan |
| `SecuenciaSinCambio` | **no**, aunque su decisión pendiente (B-1) **condiciona** la respuesta de E5 (§6) |
| `actualizar_secuencia` | **no** — E5 es una operación aparte |

**[DISEÑO]** Una duplicación aceptable y una a evitar: la lógica de *"capturar,
comparar, escribir, auditar"* es la misma en E4 y E5. **Conviene extraer un helper
compartido** (`_aplicar_secuencia_a_linea`) en vez de copiarla — pero eso **sí
tocaría E4**, y por tanto obliga a repetir sus 30 pruebas. **[PENDIENTE]** Es una
decisión de alcance para E5-B.

---

## 16. Impacto en M09

**[MEDIDO]** **Ninguno.** `supervisor.py` menciona `secuencia` **0 veces** —
confirmado otra vez.

**[DISEÑO]** La única exposición sigue siendo `_programacion_vigente().first()`,
que hereda `Meta.ordering = ["dia","secuencia"]`. Cambiar secuencias en bloque
**podría** alterar cuál devuelve `.first()` **si una orden tuviera dos líneas
vigentes** — y eso lo impide **I-1** desde M03-D3.2.

**[RIESGO]** Sin cambios respecto de E2/E4: si I-1 se relajara, ese `.first()`
volvería a ser arbitrario y nadie lo vería.

**M09 no se modifica.**

---

## 17. `revisar_coherencia`

**[DISEÑO]** **No se modifica**, y la operación de conjunto **no introduce ninguna
condición nueva que haya que auditar** — con un matiz medido:

**[MEDIDO]** La única anomalía que E5 podría encontrar es *"líneas del mismo día
en planes distintos"*, y **eso ya lo detecta** `revisar_coherencia` por la vía de
la semana (*"está fechada el X, fuera de la semana del Y al Z"*).

**[DISEÑO]** Lo que E5 aporta es **detectarlo antes**: al exigir que todas las
líneas del día pertenezcan al plan indicado, **la operación se niega a operar
sobre datos incoherentes** en vez de esperar a la publicación.

**[PENDIENTE]** Si en el futuro se quisiera que la duplicidad de secuencia fuera
un hallazgo, **eso sigue siendo E-5 de M03-E3**, que está abierta. **E5-A no la
toca.**

---

## 18. G · Matriz de pruebas

| # | Escenario | Resultado esperado | Evidencia que debe persistir |
|:--:|---|---|---|
| 1 | **jornada vacía** | 400 o 200 sin efecto — **[PENDIENTE]**, depende de §6 | 0 eventos |
| 2 | **una línea** | 200 | 1 evento con `lote_tamano: 1` |
| 3 | **varias líneas** | 200 | N eventos, **mismo `lote`** |
| 4 | **secuencias 1-2-3** | 200 | los tres eventos reconstruyen la transición |
| 5 | **secuencias repetidas** `[1,1,2]` | **200 — permitido** | `empate` anotado; ninguna otra línea tocada |
| 6 | **todas en 0** | 200 | `nuevo_sin_secuenciar: true`; **ningún empate** |
| 7 | **mezcla 0 y >0** | 200 | conteos correctos en el resumen de E2 |
| 8 | **todos sin cambio** | **[PENDIENTE]** §6 | 0 escrituras en cualquier caso |
| 9 | **una sin cambio, otras cambiadas** | **200** | eventos **solo** de las cambiadas; `lote_sin_cambio: 1` |
| 10 | **línea de otra jornada** | **400**, nombrándola | 0 escrituras |
| 11 | **línea inexistente** | **400/404**, nombrándola | 0 escrituras |
| 12 | **plan borrador** | 200 **sin causa** | evento `secuencia_jornada`, 0 novedades |
| 13 | **plan publicado sin causa** | **400** | 0 escrituras |
| 13b | **plan publicado con causa** | 200 | `secuencia_jornada_en_plan_publicado` + 1 novedad |
| 14 | **concurrencia** | una sola aplicación coherente | **verificar desarmando el lock** |
| 15 | **rollback** | nada aplicado | comprobado **desde conexión independiente** |
| 16 | **idempotencia** | replay con `Idempotent-Replay: true` | **un solo lote** de eventos |
| 17 | **otro tenant** | **404** | 0 escrituras en la otra organización |
| 18 | **permisos insuficientes** | **403** | 0 escrituras |
| — | **A: 1→3, B: 2→1, C: 3→2** | 200 | **las tres transiciones reconstruibles** |
| — | no toca `programada_para`, día, plan, zona, prioridad, estado | — | afirmado sobre el efecto |
| — | **0 efectos externos** | — | instrumento **probado antes** de leer su cero |
| — | `makemigrations --check` | **limpio** | — |

---

## H · Gaps que requieren decisión empresarial

| # | Gap | Sección |
|:--:|---|:--:|
| **G-1** | **`SECUENCIA_SIN_CAMBIO` (B-1 de E4)** sigue sin firma, y **condiciona** la respuesta de E5 al lote sin cambios | §6 |
| **G-2** | **¿Enviar todas las líneas o solo las modificadas?** Decisión de contrato | §2 |
| **G-3** | **¿"El último gana" es aceptable?** Sin token de versión en `ProgramacionOrden`, no hay alternativa sin migración | §4 |
| **G-4** | **¿Se escriben eventos para las líneas sin cambio?** | §5 |
| **G-5** | **¿Una causa por lote o una por línea?** | §9 |
| **G-6** | **¿Extraer el helper compartido con E4**, aceptando repetir sus 30 pruebas? | §15 |

**[PENDIENTE]** Ninguna se decide aquí.

---

## I · Archivos que se modificarían en E5-B

| Archivo | Cambio previsto |
|---|---|
| `operaciones/programacion.py` | **+1 función** `secuenciar_jornada`; reutiliza `_empate_de`, `_validar_causa`, `_novedad_de`, `lineas_de_jornada` |
| `operaciones/serializers.py` | **+1** `SecuenciarJornadaSerializer` (con una lista de objetos) |
| `operaciones/views.py` | **+1** `SecuenciarJornadaView` |
| `operaciones/urls.py` | **+1 ruta** |
| `operaciones/tests/test_m09f_gobernanza.py` | **guarda de rutas** + el motivo por el que no es ruta de ejecución |
| `operaciones/tests/test_m03e5_jornada.py` | **nuevo** — la matriz del §18 |

```
migraciones previstas .... 0        modelos ......... 0
roles .................... 0        constraints ..... 0
M09 ...................... sin tocar
revisar_coherencia ....... sin tocar
E4 ....................... sin tocar   (salvo que se apruebe G-6)
```

---

## J · GO / NO-GO

# GO — condicionado a G-1 y G-2

**[DISEÑO]** Lo técnico está resuelto y **no exige ninguna migración**:

| | |
|---|---|
| unidad de operación | **resuelta**: `(org, dia)`, con el plan como autoridad |
| locks | **resueltos**: líneas ordenadas por `id` → plan; no cierra ciclo con E4 |
| auditoría | **resuelta**: alternativa C (lote compartido), única viable sin migración |
| idempotencia | **resuelta**: se reutiliza el mecanismo existente |
| atomicidad | **resuelta**: una transacción, patrón ya probado cuatro veces |
| permisos | **resueltos**: `EsJefeDeOperaciones`, 0 roles nuevos |

**Lo que falta es firma, no diseño:**

- **G-1** decide qué contesta E5 a un lote sin cambios — y **debería contestar lo
  mismo que E4**, cuya decisión sigue abierta;
- **G-2** decide la forma del contrato de entrada, y de ella depende cuánto puede
  verificar el servidor.

> **G-3, G-4, G-5 y G-6 no bloquean**: tienen un valor por defecto razonable y
> reversible, y se pueden confirmar durante E5-B.

**[RIESGO] Y el dato que no ha cambiado en seis pasos:** **0 planes y 0 líneas en
producción**, y las 3 órdenes reales clasifican como **contingencia**. E5
construiría la operación de conjunto para jornadas que **todavía no existen**.

> No es una objeción a E5 —la operación hace falta antes de que alguien pueda
> secuenciar de verdad— pero **el hueco más grande sigue siendo que nadie ha
> programado trabajo todavía**, y eso ninguna fase de M03-E lo resuelve.

---

```
código ......... 0     modelos ....... 0     migraciones ... 0
endpoints ...... 0     M09 ........... sin tocar     revisar_coherencia ... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
